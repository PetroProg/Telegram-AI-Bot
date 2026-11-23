from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.bot.keyboards.reply import get_main_reply_keyboard
from app.bot.keyboards.inline import (
    get_chats_pagination_keyboard,
    get_models_selection_keyboard,
    get_active_chat_keyboard,
    get_delete_confirm_keyboard,
    get_delete_select_keyboard
)
from app.bot.ui import cleanup_menus_and_reset_state, track_menu_message
from app.db.session import async_session_factory
from app.db import repository

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot, state: FSMContext):
    await cleanup_menus_and_reset_state(bot, message.chat.id, state, trigger_message_id=message.message_id)
    async with async_session_factory() as session:
        user = await repository.get_or_create_user(
            session=session,
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name
        )
        active_chat = await repository.get_active_chat(session, user.id)

    text = (
        f"👋 **Привет, {message.from_user.first_name}!**\n\n"
        "Я твой персональный AI-клиент с поддержкой изолированных диалогов и мультимодельности.\n\n"
        "✨ **Возможности:**\n"
        "• 🏴‍☠️ **AI Horde (Uncensored)** — полностью бесплатно и без цензуры\n"
        "• 🌐 **OpenRouter Free Tier** — свободные облачные модели без ограничений\n"
        "• 📸 **Gemini 2.0 Flash** — умный анализ изображений и фото\n"
        "• 📜 Изолированные сессии диалогов с сохранением контекста\n\n"
    )

    if active_chat:
        text += f"🎯 **Текущий активный чат**: `{active_chat.title}` ({active_chat.model.display_name})\n"
        text += "Можешь сразу писать вопрос или отправить картинку!"
    else:
        text += "💡 У тебя пока нет активного диалога. Нажми **➕ Новый чат**, чтобы начать!"

    # Not tracked: this message anchors the reply keyboard and must not be auto-deleted
    await message.answer(text, reply_markup=get_main_reply_keyboard(), parse_mode="Markdown")


@router.message(F.text == "💬 Мои чаты")
@router.message(Command("chats"))
async def handle_my_chats(message: Message, bot: Bot, state: FSMContext):
    await cleanup_menus_and_reset_state(bot, message.chat.id, state)  # keep trigger: deleting the reply-button message drops the reply keyboard in Telegram clients
    async with async_session_factory() as session:
        user = await repository.get_or_create_user(session, message.from_user.id)
        chats, total = await repository.list_user_chats(session, user.id, page=1, page_size=5)

    if not chats:
        async with async_session_factory() as session:
            models = await repository.get_active_models(session)
        sent = await message.answer(
            "📭 У тебя пока нет созданных диалогов.\nВыбери модель для первого чата:",
            reply_markup=get_models_selection_keyboard(models, action="create")
        )
        await track_menu_message(state, sent)
        return

    kb = get_chats_pagination_keyboard(chats, page=1, total_count=total, active_chat_id=user.active_chat_id)
    sent = await message.answer(
        "📁 **Твои диалоги:**\nНажми на чат для выбора в 1 клик или ⚙️ для настроек:",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await track_menu_message(state, sent)


@router.message(F.text == "➕ Новый чат")
@router.message(Command("new"))
async def handle_new_chat(message: Message, bot: Bot, state: FSMContext):
    await cleanup_menus_and_reset_state(bot, message.chat.id, state)  # keep trigger: deleting the reply-button message drops the reply keyboard in Telegram clients
    async with async_session_factory() as session:
        models = await repository.get_active_models(session)

    sent = await message.answer(
        "🧠 **Выберите модель для новой сессии:**\n\n"
        "За каждым диалогом закрепляется своя нейросеть. Модель можно будет изменить в любой момент.",
        reply_markup=get_models_selection_keyboard(models, action="create"),
        parse_mode="Markdown"
    )
    await track_menu_message(state, sent)


@router.message(F.text == "ℹ️ Активный чат")
@router.message(Command("current"))
async def handle_active_chat(message: Message, bot: Bot, state: FSMContext):
    await cleanup_menus_and_reset_state(bot, message.chat.id, state)  # keep trigger: deleting the reply-button message drops the reply keyboard in Telegram clients
    async with async_session_factory() as session:
        active_chat = await repository.get_active_chat(session, message.from_user.id)
        if not active_chat:
            sent = await message.answer("⚠️ У тебя сейчас нет выбранного активного чата. Выбери из списка: /chats")
            await track_menu_message(state, sent)
            return

        messages = await repository.get_chat_context(session, active_chat.id, limit=10)

    text = (
        f"🎯 **Активный диалог:**\n"
        f"📌 Название: `{active_chat.title}`\n"
        f"🤖 Модель: {active_chat.model.display_name if active_chat.model else active_chat.model_id}\n"
        f"💬 Сообщений в памяти: {len(messages)}/10\n"
        f"📅 Создан: {active_chat.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        "Выбери действие для этого чата:"
    )
    kb = get_active_chat_keyboard(active_chat.id)
    sent = await message.answer(text, reply_markup=kb, parse_mode="Markdown")
    await track_menu_message(state, sent)


@router.message(Command("clear"))
@router.message(Command("clear_chat"))
async def handle_clear_command(message: Message, bot: Bot):
    async with async_session_factory() as session:
        active_chat = await repository.get_active_chat(session, message.from_user.id)
        if not active_chat:
            await message.answer("⚠️ У тебя нет активного диалога для очистки. Выбери чат: /chats")
            return

        chat_id = active_chat.id
        chat_title = active_chat.title
        # 1. Fetch all message IDs belonging to this chat
        message_ids = await repository.get_chat_telegram_message_ids(session, chat_id)
        # 2. Clear from database
        await repository.clear_chat_history(session, chat_id)

    # 3. Physically delete all messages in Telegram
    deleted_count = 0
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=mid)
            deleted_count += 1
        except Exception:
            pass

    # Also delete the /clear command message itself
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except Exception:
        pass

    await message.answer(
        f"🧹 **Лента переписки и контекст диалога «{chat_title}» полностью очищены!**\n"
        f"Удалено сообщений: {deleted_count}.\n"
        "Можно продолжать общение с чистого листа ✨",
        reply_markup=get_main_reply_keyboard(),
        parse_mode="Markdown"
    )


@router.message(Command("delete"))
@router.message(Command("delete_chat"))
async def handle_delete_command(message: Message, bot: Bot, state: FSMContext):
    await cleanup_menus_and_reset_state(bot, message.chat.id, state, trigger_message_id=message.message_id)
    async with async_session_factory() as session:
        active_chat = await repository.get_active_chat(session, message.from_user.id)

    if active_chat:
        kb = get_delete_confirm_keyboard(active_chat.id)
        sent = await message.answer(
            f"⚠️ **Удалить текущий активный чат «{active_chat.title}»?**\nВсе сообщения этого диалога будут стёрты.",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        await track_menu_message(state, sent)
    else:
        async with async_session_factory() as session:
            chats, total = await repository.list_user_chats(session, message.from_user.id, page=1, page_size=5)

        if not chats:
            sent = await message.answer("📭 У тебя нет созданных чатов для удаления.")
            await track_menu_message(state, sent)
            return

        kb = get_delete_select_keyboard(chats, page=1, total_count=total)
        sent = await message.answer("🗑 **Выбери чат для удаления:**", reply_markup=kb, parse_mode="Markdown")
        await track_menu_message(state, sent)


async def _clear_physical_telegram_chat(
    bot: Bot,
    chat_id: int,
    up_to_message_id: int,
    max_scan: int = 200
) -> None:
    """Deletes recent Telegram messages in batches without touching DB context."""
    min_id = max(1, up_to_message_id - max_scan + 1)
    all_ids = list(range(up_to_message_id, min_id - 1, -1))

    for i in range(0, len(all_ids), 50):
        chunk = all_ids[i:i + 50]
        try:
            await bot.delete_messages(chat_id=chat_id, message_ids=chunk)
        except Exception:
            # Fallback to smaller chunks if a message in the batch is >48h old
            any_deleted = False
            for j in range(0, len(chunk), 10):
                sub = chunk[j:j + 10]
                try:
                    await bot.delete_messages(chat_id=chat_id, message_ids=sub)
                    any_deleted = True
                except Exception:
                    for mid in sub:
                        try:
                            await bot.delete_message(chat_id=chat_id, message_id=mid)
                            any_deleted = True
                        except Exception:
                            pass
            if not any_deleted:
                break


@router.message(F.text == "🫧 Очистить экран")
@router.message(Command("clean"))
async def handle_clean_screen(message: Message, bot: Bot, state: FSMContext):
    await state.clear()
    await _clear_physical_telegram_chat(
        bot=bot,
        chat_id=message.chat.id,
        up_to_message_id=message.message_id,
        max_scan=500,
    )

    async with async_session_factory() as session:
        active_chat = await repository.get_active_chat(session, message.from_user.id)

    if active_chat:
        text = (
            f"🫧 **Экран очищен!**\n"
            f"Активный диалог `{active_chat.title}` и его память сохранены."
        )
    else:
        text = "🫧 **Экран очищен!**\nВыбери или создай чат, чтобы начать общение."

    # Not tracked: this message anchors the reply keyboard and must not be auto-deleted
    await message.answer(text, reply_markup=get_main_reply_keyboard(), parse_mode="Markdown")


@router.message(F.text == "⚙️ Помощь")
@router.message(Command("help"))
async def handle_help(message: Message, bot: Bot, state: FSMContext):
    await cleanup_menus_and_reset_state(bot, message.chat.id, state)  # keep trigger: deleting the reply-button message drops the reply keyboard in Telegram clients
    text = (
        "📖 **Справка по боту:**\n\n"
        "• Отправь **текст** — бот ответит в контексте активного чата.\n"
        "• Отправь **фото** — бот проанализирует его с помощью Vision модели.\n"
        "• **🫧 Очистить экран** (`/clean`) — убрать сообщения из ленты Telegram (память ИИ сохраняется).\n"
        "• **/clear** — физически удалить сообщения диалога из Telegram и очистить контекст.\n"
        "• **/delete** — быстро удалить активный чат целиком.\n"
        "• Если ответ превышает 4096 знаков — бот автоматически пришлет его удобным `.md` файлом.\n"
        "• Для переключения между диалогами используй кнопку **💬 Мои чаты**.\n"
        "• Создавай сколько угодно изолированных чатов под разные задачи!\n"
    )
    await message.answer(text, reply_markup=get_main_reply_keyboard(), parse_mode="Markdown")
