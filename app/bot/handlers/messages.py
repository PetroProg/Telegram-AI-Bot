import asyncio
import html
import io
import logging
from typing import Optional
from aiogram import Router, F, Bot
from aiogram.types import Message, BufferedInputFile
from aiogram.enums import ChatAction

from app.core.config import settings
from app.core.text_utils import clean_model_response, markdown_to_html
from app.db.session import async_session_factory
from app.db import repository
from app.providers.base import ChatTurn
from app.providers.manager import provider_manager

logger = logging.getLogger(__name__)
router = Router(name="messages")


async def keep_typing(bot: Bot, chat_id: int, stop_event: asyncio.Event):
    """Periodically sends typing chat action every 4 seconds until stop_event is set."""
    while not stop_event.is_set():
        try:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=4.0)
        except asyncio.TimeoutError:
            pass


async def edit_or_send_response(status_msg: Message, response_text: str) -> Optional[Message]:
    """
    Edits the temporary status message with the HTML-formatted response.
    If longer than 4096 characters, edits status_msg into a preview and attaches
    the full response as a .md document.
    """
    cleaned = clean_model_response(response_text)
    if not cleaned:
        cleaned = "(Пустой ответ от модели)"

    html_text = markdown_to_html(cleaned)

    if len(html_text) <= 4096:
        try:
            return await status_msg.edit_text(
                html_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception:
            try:
                return await status_msg.edit_text(cleaned[:4096])
            except Exception:
                return await status_msg.answer(cleaned[:4096])
    else:
        preview_html = (
            markdown_to_html(cleaned[:300] + "...")
            + "\n\n📄 <i>Полный ответ превысил лимит Telegram (4096 симв.) и прикреплен в файле ниже:</i>"
        )
        try:
            await status_msg.edit_text(
                preview_html,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception:
            try:
                await status_msg.edit_text(cleaned[:300] + "...")
            except Exception:
                pass

        file_bytes = cleaned.encode("utf-8")
        doc = BufferedInputFile(file=file_bytes, filename="response.md")
        return await status_msg.answer_document(document=doc, caption="💾 Полный ответ в формате Markdown")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_user_text(message: Message, bot: Bot):
    user_id = message.from_user.id
    user_text = message.text.strip()

    async with async_session_factory() as session:
        active_chat = await repository.get_active_chat(session, user_id)
        if not active_chat:
            await message.answer(
                "⚠️ У тебя нет активного диалога.\n"
                "Нажми <b>💬 Мои чаты</b> или <b>➕ Новый чат</b>, чтобы начать общение!",
                parse_mode="HTML"
            )
            return

        chat_id = active_chat.id
        model = active_chat.model
        sys_prompt = active_chat.system_prompt

        # 1. Save user message with telegram_message_id
        await repository.add_message(
            session, chat_id, role="user", content=user_text, telegram_message_id=message.message_id
        )
        try:
            await repository.log_prompt(
                session=session,
                user_id=user_id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                chat_id=chat_id,
                model_id=model.id if model else active_chat.model_id,
                has_image=False,
            )
        except Exception:
            await session.rollback()
            logger.exception("Failed to log text prompt for user_id=%s", user_id)

        # 2. Fetch context (sliding window of last 10 messages)
        history = await repository.get_chat_context(session, chat_id, limit=settings.DEFAULT_CONTEXT_LIMIT)

    # Format history turns
    turns = [ChatTurn(role=m.role, content=m.content) for m in history]

    # 3. Send live status message + start typing indicator loop
    status_msg = await message.answer("⏳ <i>Генерирую ответ...</i>", parse_mode="HTML")
    stop_event = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(bot, message.chat.id, stop_event))

    try:
        # 4. Generate response
        response_text = await provider_manager.generate(
            model=model,
            messages=turns,
            system_prompt=sys_prompt,
            has_image=False
        )

        # 5. Edit status message into formatted response
        sent_msg = await edit_or_send_response(status_msg, response_text)

        # 6. Save assistant response with its telegram_message_id
        bot_msg_id = sent_msg.message_id if sent_msg else status_msg.message_id
        async with async_session_factory() as session:
            await repository.add_message(
                session, chat_id, role="assistant", content=response_text, telegram_message_id=bot_msg_id
            )

    except Exception as e:
        logger.exception("Error generating response")
        err_html = f"❌ <b>Ошибка при обращении к нейросети:</b>\n<code>{html.escape(str(e))}</code>"
        try:
            await status_msg.edit_text(err_html, parse_mode="HTML")
        except Exception:
            await message.answer(f"❌ Ошибка при обращении к нейросети:\n{e}")
    finally:
        stop_event.set()
        await typing_task


@router.message(F.photo)
async def handle_user_photo(message: Message, bot: Bot):
    user_id = message.from_user.id
    caption = message.caption or "Опиши и проанализируй это изображение."

    async with async_session_factory() as session:
        active_chat = await repository.get_active_chat(session, user_id)
        if not active_chat:
            await message.answer(
                "⚠️ У тебя нет активного диалога.\n"
                "Создай чат через **➕ Новый чат**, чтобы отправить фото!",
                parse_mode="Markdown"
            )
            return

        chat_id = active_chat.id
        model = active_chat.model
        sys_prompt = active_chat.system_prompt

        # Save user message with telegram_message_id
        await repository.add_message(
            session, chat_id, role="user", content=caption, has_image=True, telegram_message_id=message.message_id
        )
        try:
            await repository.log_prompt(
                session=session,
                user_id=user_id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                chat_id=chat_id,
                model_id=model.id if model else active_chat.model_id,
                has_image=True,
            )
        except Exception:
            await session.rollback()
            logger.exception("Failed to log photo prompt for user_id=%s", user_id)

        history = await repository.get_chat_context(session, chat_id, limit=settings.DEFAULT_CONTEXT_LIMIT)

    # Download largest photo from Telegram
    photo_file = await bot.get_file(message.photo[-1].file_id)
    photo_bytes_io = io.BytesIO()
    await bot.download_file(photo_file.file_path, destination=photo_bytes_io)
    image_bytes = photo_bytes_io.getvalue()

    # Build turns
    turns = []
    for m in history[:-1]:
        turns.append(ChatTurn(role=m.role, content=m.content))
    # Last turn has the image
    turns.append(ChatTurn(role="user", content=caption, image_bytes=image_bytes))

    status_msg = await message.answer("⏳ <i>Анализирую изображение...</i>", parse_mode="HTML")
    stop_event = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(bot, message.chat.id, stop_event))

    try:
        response_text = await provider_manager.generate(
            model=model,
            messages=turns,
            system_prompt=sys_prompt,
            has_image=True
        )

        sent_msg = await edit_or_send_response(status_msg, response_text)
        bot_msg_id = sent_msg.message_id if sent_msg else status_msg.message_id

        async with async_session_factory() as session:
            await repository.add_message(
                session, chat_id, role="assistant", content=response_text, telegram_message_id=bot_msg_id
            )

    except Exception as e:
        logger.exception("Error processing photo with model")
        err_html = f"❌ <b>Ошибка при обработке фото:</b>\n<code>{html.escape(str(e))}</code>"
        try:
            await status_msg.edit_text(err_html, parse_mode="HTML")
        except Exception:
            await message.answer(f"❌ Ошибка при обработке фото:\n{e}")
    finally:
        stop_event.set()
        await typing_task
