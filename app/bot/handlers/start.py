from aiogram import Router, F
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
from app.db.session import async_session_factory
from app.db import repository

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
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
        "• 🏴‍☠️ **AI Horde (Qwen 2.5 72B)** — полностью бесплатно и без цензуры\n"
        "• 🌐 **OpenRouter Free Tier** — свободные облачные модели без ограничений\n"
        "• 📸 **Gemini 2.0 Flash** — умный анализ изображений и фото\n"
        "• 📜 Изолированные сессии диалогов с сохранением контекста\n\n"
    )

    if active_chat:
        text += f"🎯 **Текущий активный чат**: `{active_chat.title}` ({active_chat.model.display_name})\n"
        text += "Можешь сразу писать вопрос или отправить картинку!"
    else:
        text += "💡 У тебя пока нет активного диалога. Нажми **➕ Новый чат**, чтобы начать!"

    await message.answer(text, reply_markup=get_main_reply_keyboard(), parse_mode="Markdown")


@router.message(F.text == "💬 Мои чаты")
@router.message(Command("chats"))
async def handle_my_chats(message: Message, state: FSMContext):
    await state.clear()
    async with async_session_factory() as session:
        user = await repository.get_or_create_user(session, message.from_user.id)
        chats, total = await repository.list_user_chats(session, user.id, page=1, page_size=5)

    if not chats:
        async with async_session_factory() as session:
            models = await repository.get_active_models(session)
        await message.answer(
            "📭 У тебя пока нет созданных диалогов.\nВыбери модель для первого чата:",
            reply_markup=get_models_selection_keyboard(models, action="create")
        )
        return

    kb = get_chats_pagination_keyboard(chats, page=1, total_count=total, active_chat_id=user.active_chat_id)
    await message.answer("📁 **Твои диалоги:**\nВыбери чат для продолжения или настройки:", reply_markup=kb, parse_mode="Markdown")


@router.message(F.text == "➕ Новый чат")
@router.message(Command("new"))
async def handle_new_chat(message: Message, state: FSMContext):
    await state.clear()
    async with async_session_factory() as session:
        models = await repository.get_active_models(session)

    await message.answer(
        "🧠 **Выберите модель для новой сессии:**\n\n"
        "За каждым диалогом закрепляется своя нейросеть. Модель можно будет изменить в любой момент.",
        reply_markup=get_models_selection_keyboard(models, action="create"),
        parse_mode="Markdown"
    )


@router.message(F.text == "ℹ️ Активный чат")
@router.message(Command("current"))
async def handle_active_chat(message: Message):
    async with async_session_factory() as session:
        active_chat = await repository.get_active_chat(session, message.from_user.id)
        if not active_chat:
            await message.answer("⚠️ У тебя сейчас нет выбранного активного чата. Выбери из списка: /chats")
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
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")


@router.message(Command("delete"))
@router.message(Command("delete_chat"))
async def handle_delete_command(message: Message):
    async with async_session_factory() as session:
        active_chat = await repository.get_active_chat(session, message.from_user.id)

    if active_chat:
        kb = get_delete_confirm_keyboard(active_chat.id)
        await message.answer(
            f"⚠️ **Удалить текущий активный чат «{active_chat.title}»?**\nВсе сообщения этого диалога будут стёрты.",
            reply_markup=kb,
            parse_mode="Markdown"
        )
    else:
        async with async_session_factory() as session:
            chats, total = await repository.list_user_chats(session, message.from_user.id, page=1, page_size=5)

        if not chats:
            await message.answer("📭 У тебя нет созданных чатов для удаления.")
            return

        kb = get_delete_select_keyboard(chats, page=1, total_count=total)
        await message.answer("🗑 **Выбери чат для удаления:**", reply_markup=kb, parse_mode="Markdown")


@router.message(F.text == "⚙️ Помощь")
@router.message(Command("help"))
async def handle_help(message: Message):
    text = (
        "📖 **Справка по боту:**\n\n"
        "• Отправь **текст** — бот ответит в контексте активного чата.\n"
        "• Отправь **фото** — бот проанализирует его с помощью Vision модели.\n"
        "• Если ответ превышает 4096 знаков — бот автоматически пришлет его удобным `.md` файлом.\n"
        "• Для переключения между диалогами используй кнопку **💬 Мои чаты**.\n"
        "• Создавай сколько угодно изолированных чатов под разные задачи!\n"
    )
    await message.answer(text, parse_mode="Markdown")
