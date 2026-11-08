import asyncio
import io
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, BufferedInputFile
from aiogram.enums import ChatAction

from app.core.config import settings
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


async def send_response_safely(message: Message, response_text: str):
    """
    Sends message to Telegram. If longer than 4096 characters, sends a short
    summary preview and attaches the full response as a .md document.
    """
    if len(response_text) <= 4096:
        try:
            await message.answer(response_text, parse_mode="Markdown")
        except Exception:
            # Fallback to plain text if markdown parse fails
            await message.answer(response_text)
    else:
        preview = response_text[:300] + "...\n\n📄 _Полный ответ превысил лимит Telegram (4096 симв.) и прикреплен в файле ниже:_"
        try:
            await message.answer(preview, parse_mode="Markdown")
        except Exception:
            await message.answer(preview)

        # Create .md file in-memory
        file_bytes = response_text.encode("utf-8")
        doc = BufferedInputFile(file=file_bytes, filename="response.md")
        await message.answer_document(document=doc, caption="💾 Полный ответ в формате Markdown")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_user_text(message: Message, bot: Bot):
    user_id = message.from_user.id
    user_text = message.text.strip()

    async with async_session_factory() as session:
        active_chat = await repository.get_active_chat(session, user_id)
        if not active_chat:
            await message.answer(
                "⚠️ У тебя нет активного диалога.\n"
                "Нажми **💬 Мои чаты** или **➕ Новый чат**, чтобы начать общение!",
                parse_mode="Markdown"
            )
            return

        chat_id = active_chat.id
        model = active_chat.model
        sys_prompt = active_chat.system_prompt

        # 1. Save user message
        await repository.add_message(session, chat_id, role="user", content=user_text)

        # 2. Fetch context (sliding window of last 10 messages)
        history = await repository.get_chat_context(session, chat_id, limit=settings.DEFAULT_CONTEXT_LIMIT)

    # Format history turns
    turns = [ChatTurn(role=m.role, content=m.content) for m in history]

    # 3. Start typing indicator loop
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

        # 5. Save assistant response
        async with async_session_factory() as session:
            await repository.add_message(session, chat_id, role="assistant", content=response_text)

        # 6. Send to user
        await send_response_safely(message, response_text)

    except Exception as e:
        logger.exception("Error generating response")
        await message.answer(f"❌ **Ошибка при обращении к нейросети:**\n`{str(e)}`", parse_mode="Markdown")
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

        # Save user message
        await repository.add_message(session, chat_id, role="user", content=caption, has_image=True)

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

    stop_event = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(bot, message.chat.id, stop_event))

    try:
        response_text = await provider_manager.generate(
            model=model,
            messages=turns,
            system_prompt=sys_prompt,
            has_image=True
        )

        async with async_session_factory() as session:
            await repository.add_message(session, chat_id, role="assistant", content=response_text)

        await send_response_safely(message, response_text)

    except Exception as e:
        logger.exception("Error processing photo with model")
        await message.answer(f"❌ **Ошибка при обработке фото:**\n`{str(e)}`", parse_mode="Markdown")
    finally:
        stop_event.set()
        await typing_task
