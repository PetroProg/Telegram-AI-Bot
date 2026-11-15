import uuid
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from app.bot.states import ChatCreateState, ChatRenameState
from app.bot.keyboards.inline import (
    get_chats_pagination_keyboard,
    get_chat_actions_keyboard,
    get_delete_confirm_keyboard,
    get_delete_select_keyboard,
    get_models_selection_keyboard
)
from app.bot.ui import (
    add_temp_message_id,
    cleanup_menus_and_reset_state,
    track_menu_message,
)
from app.db.session import async_session_factory
from app.db import repository

router = Router(name="chats")


@router.callback_query(F.data == "noop")
async def cb_noop(query: CallbackQuery):
    await query.answer()


@router.callback_query(F.data == "menu:close")
async def cb_menu_close(query: CallbackQuery, state: FSMContext):
    await state.update_data(last_menu_msg_id=None)
    try:
        await query.message.delete()
    except Exception:
        pass
    await query.answer()


@router.callback_query(F.data == "chats:list")
async def cb_chats_list(query: CallbackQuery):
    async with async_session_factory() as session:
        user = await repository.get_or_create_user(session, query.from_user.id)
        chats, total = await repository.list_user_chats(session, user.id, page=1, page_size=5)

    if not chats:
        async with async_session_factory() as session:
            models = await repository.get_active_models(session)
        await query.message.edit_text(
            "📭 У тебя пока нет созданных диалогов.\nВыбери модель для первого чата:",
            reply_markup=get_models_selection_keyboard(models, action="create")
        )
        return

    kb = get_chats_pagination_keyboard(chats, page=1, total_count=total, active_chat_id=user.active_chat_id)
    await query.message.edit_text(
        "📁 **Твои диалоги:**\nНажми на чат для выбора в 1 клик или ⚙️ для настроек:",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await query.answer()


@router.callback_query(F.data.startswith("chats:page:"))
async def cb_chats_page(query: CallbackQuery):
    page = int(query.data.split(":")[2])
    async with async_session_factory() as session:
        user = await repository.get_or_create_user(session, query.from_user.id)
        chats, total = await repository.list_user_chats(session, user.id, page=page, page_size=5)

    kb = get_chats_pagination_keyboard(chats, page=page, total_count=total, active_chat_id=user.active_chat_id)
    await query.message.edit_text(
        "📁 **Твои диалоги:**\nНажми на чат для выбора в 1 клик или ⚙️ для настроек:",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await query.answer()


@router.callback_query(F.data.startswith("chat:quick_activate:"))
async def cb_chat_quick_activate(query: CallbackQuery):
    parts = query.data.split(":")
    chat_id = uuid.UUID(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 1

    async with async_session_factory() as session:
        await repository.set_active_chat(session, query.from_user.id, chat_id)
        chat = await repository.get_chat(session, chat_id)
        chats, total = await repository.list_user_chats(session, query.from_user.id, page=page, page_size=5)

    kb = get_chats_pagination_keyboard(chats, page=page, total_count=total, active_chat_id=chat_id)
    try:
        await query.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass
    chat_title = chat.title if chat else "чат"
    await query.answer(f"✅ Активен: {chat_title}")


@router.callback_query(F.data.startswith("chats:delete_menu:"))
async def cb_chats_delete_menu(query: CallbackQuery):
    page = int(query.data.split(":")[2])
    async with async_session_factory() as session:
        chats, total = await repository.list_user_chats(session, query.from_user.id, page=page, page_size=5)

    if not chats:
        await query.answer("У тебя нет созданных чатов.", show_alert=True)
        return

    kb = get_delete_select_keyboard(chats, page=page, total_count=total)
    await query.message.edit_text("🗑 **Выбери диалог, который хочешь удалить:**", reply_markup=kb, parse_mode="Markdown")
    await query.answer()


@router.callback_query(F.data.startswith("chat:view:"))
async def cb_chat_view(query: CallbackQuery):
    chat_id = uuid.UUID(query.data.split(":")[2])
    async with async_session_factory() as session:
        chat = await repository.get_chat(session, chat_id)
        if not chat:
            await query.answer("Чат не найден", show_alert=True)
            return

        user = await repository.get_or_create_user(session, query.from_user.id)
        messages = await repository.get_chat_context(session, chat_id, limit=10)

    is_active = (user.active_chat_id == chat.id)
    text = (
        f"💬 **Диалог:** `{chat.title}`\n"
        f"🤖 **Модель:** {chat.model.display_name if chat.model else chat.model_id}\n"
        f"📊 **Сообщений в памяти:** {len(messages)}/10\n"
        f"📅 **Создан:** {chat.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"Статус: {'🟢 **Активен сейчас**' if is_active else '⚪ Не активен'}"
    )

    kb = get_chat_actions_keyboard(chat.id, is_active=is_active)
    await query.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await query.answer()


@router.callback_query(F.data.startswith("chat:activate:"))
async def cb_chat_activate(query: CallbackQuery):
    chat_id = uuid.UUID(query.data.split(":")[2])
    async with async_session_factory() as session:
        await repository.set_active_chat(session, query.from_user.id, chat_id)
        chat = await repository.get_chat(session, chat_id)

    await query.answer(f"✅ Чат '{chat.title}' выбран активным!")
    kb = get_chat_actions_keyboard(chat_id, is_active=True)
    await query.message.edit_reply_markup(reply_markup=kb)


@router.callback_query(F.data.startswith("chat:history:"))
async def cb_chat_history(query: CallbackQuery):
    chat_id = uuid.UUID(query.data.split(":")[2])
    async with async_session_factory() as session:
        chat = await repository.get_chat(session, chat_id)
        messages = await repository.get_chat_context(session, chat_id, limit=6)

    if not messages:
        await query.answer("История этого чата пуста.", show_alert=True)
        return

    text = f"📜 **История чата «{chat.title}» (последние сообщения):**\n\n"
    for msg in messages:
        role_icon = "👤" if msg.role == "user" else "🤖"
        preview = msg.content[:150] + ("..." if len(msg.content) > 150 else "")
        text += f"{role_icon} **{msg.role.capitalize()}:**\n{preview}\n\n"

    kb = get_chat_actions_keyboard(chat_id, is_active=False)
    await query.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await query.answer()


@router.callback_query(F.data.startswith("chat:change_model:"))
async def cb_chat_change_model(query: CallbackQuery):
    chat_id = uuid.UUID(query.data.split(":")[2])
    async with async_session_factory() as session:
        models = await repository.get_active_models(session)

    kb = get_models_selection_keyboard(models, action="change", chat_id=chat_id)
    await query.message.edit_text("🔄 **Выберите новую модель для этого чата:**", reply_markup=kb, parse_mode="Markdown")
    await query.answer()


@router.callback_query(F.data.startswith("chat:set_model:"))
async def cb_chat_set_model(query: CallbackQuery):
    parts = query.data.split(":")
    chat_id = uuid.UUID(parts[2])
    model_id = ":".join(parts[3:])

    async with async_session_factory() as session:
        await repository.update_chat_model(session, chat_id, model_id)
        chat = await repository.get_chat(session, chat_id)
        user = await repository.get_or_create_user(session, query.from_user.id)

    await query.answer("✅ Модель успешно изменена!")
    is_active = (user.active_chat_id == chat_id)
    kb = get_chat_actions_keyboard(chat_id, is_active=is_active)
    text = (
        f"💬 **Диалог:** `{chat.title}`\n"
        f"🤖 **Модель:** {chat.model.display_name if chat.model else chat.model_id}\n\n"
        "Модель успешно обновлена!"
    )
    await query.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data.startswith("chat:clear:"))
async def cb_chat_clear(query: CallbackQuery):
    chat_id = uuid.UUID(query.data.split(":")[2])
    async with async_session_factory() as session:
        message_ids = await repository.get_chat_telegram_message_ids(session, chat_id)
        await repository.clear_chat_history(session, chat_id)

    # Physically delete stored messages in Telegram
    for mid in message_ids:
        try:
            await query.bot.delete_message(chat_id=query.message.chat.id, message_id=mid)
        except Exception:
            pass

    await query.answer("🧹 Все сообщения и контекст очищены!", show_alert=True)
    # Refresh view
    await cb_chat_view(query)


@router.callback_query(F.data.startswith("chat:delete_confirm:"))
async def cb_chat_delete_confirm(query: CallbackQuery):
    chat_id = uuid.UUID(query.data.split(":")[2])
    kb = get_delete_confirm_keyboard(chat_id)
    await query.message.edit_text("⚠️ **Ты уверен, что хочешь удалить этот диалог?**\nВсе сообщения будут стёрты безвозвратно.", reply_markup=kb, parse_mode="Markdown")
    await query.answer()


@router.callback_query(F.data.startswith("chat:delete:"))
async def cb_chat_delete(query: CallbackQuery):
    chat_id = uuid.UUID(query.data.split(":")[2])
    async with async_session_factory() as session:
        await repository.delete_chat(session, query.from_user.id, chat_id)

    await query.answer("🗑 Чат успешно удален!")
    await cb_chats_list(query)


# --- FSM: Создание чата ---

@router.callback_query(F.data == "chat:new")
async def cb_chat_new(query: CallbackQuery, state: FSMContext):
    await state.clear()
    async with async_session_factory() as session:
        models = await repository.get_active_models(session)

    await query.message.edit_text(
        "🧠 **Шаг 1 из 2:** Выберите нейросеть для нового диалога:",
        reply_markup=get_models_selection_keyboard(models, action="create"),
        parse_mode="Markdown"
    )
    await query.answer()


@router.callback_query(F.data.startswith("model:select:"))
async def cb_model_selected(query: CallbackQuery, state: FSMContext):
    model_id = query.data.replace("model:select:", "")
    await state.update_data(chosen_model_id=model_id)
    await add_temp_message_id(state, query.message.message_id)
    await state.set_state(ChatCreateState.waiting_for_title)

    await query.message.edit_text(
        "✏️ **Шаг 2 из 2:** Введи название для нового диалога:\n\n"
        "_Например: «Кодинг на Python», «Изучение немецкого» или «Анализ новостей»_",
        parse_mode="Markdown"
    )
    await query.answer()


@router.message(ChatCreateState.waiting_for_title)
async def fsm_chat_title_received(message: Message, bot: Bot, state: FSMContext):
    title = message.text.strip()[:64]
    data = await state.get_data()
    model_id = data.get("chosen_model_id")
    await cleanup_menus_and_reset_state(bot, message.chat.id, state, trigger_message_id=message.message_id)

    async with async_session_factory() as session:
        chat = await repository.create_chat(
            session=session,
            user_id=message.from_user.id,
            model_id=model_id,
            title=title
        )
        model_name = chat.model.display_name if chat.model else chat.model_id
        chat_id = chat.id
        chat_title = chat.title

    text = (
        f"🎉 **Ваш чат успешно создан и активирован!**\n\n"
        f"📌 Название: `{chat_title}`\n"
        f"🤖 Модель: {model_name}\n\n"
        "Напиши сообщение или отправь фото, чтобы начать общение!"
    )
    kb = get_chat_actions_keyboard(chat_id, is_active=True)
    sent = await message.answer(text, reply_markup=kb, parse_mode="Markdown")
    await track_menu_message(state, sent)


# --- FSM: Переименование чата ---

@router.callback_query(F.data.startswith("chat:rename:"))
async def cb_chat_rename(query: CallbackQuery, state: FSMContext):
    chat_id = uuid.UUID(query.data.split(":")[2])
    await state.update_data(renaming_chat_id=str(chat_id))
    await add_temp_message_id(state, query.message.message_id)
    await state.set_state(ChatRenameState.waiting_for_new_title)

    await query.message.edit_text("✏️ Введи новое название для этого чата:", parse_mode="Markdown")
    await query.answer()


@router.message(ChatRenameState.waiting_for_new_title)
async def fsm_rename_received(message: Message, bot: Bot, state: FSMContext):
    new_title = message.text.strip()[:64]
    data = await state.get_data()
    chat_id = uuid.UUID(data.get("renaming_chat_id"))
    await cleanup_menus_and_reset_state(bot, message.chat.id, state, trigger_message_id=message.message_id)

    async with async_session_factory() as session:
        await repository.rename_chat(session, chat_id, new_title)
        chat = await repository.get_chat(session, chat_id)
        user = await repository.get_or_create_user(session, message.from_user.id)
        chat_title = chat.title if chat else new_title
        is_active = (user.active_chat_id == chat_id)

    kb = get_chat_actions_keyboard(chat_id, is_active=is_active)
    sent = await message.answer(f"✅ Чат успешно переименован в `{chat_title}`!", reply_markup=kb, parse_mode="Markdown")
    await track_menu_message(state, sent)
