import math
import uuid
from typing import List, Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.db.models import Chat, ModelCatalog


def get_chats_pagination_keyboard(
    chats: List[Chat],
    page: int,
    total_count: int,
    active_chat_id: Optional[uuid.UUID] = None,
    page_size: int = 5
) -> InlineKeyboardMarkup:
    total_pages = max(1, math.ceil(total_count / page_size))
    buttons = []

    # Chat rows (1-tap activate + gear for settings)
    for chat in chats:
        prefix = "✅ " if active_chat_id and chat.id == active_chat_id else "💬 "
        model_name = chat.model.display_name.split()[0] if chat.model else "🤖"
        title_text = f"{prefix}{chat.title[:22]} ({model_name})"
        buttons.append([
            InlineKeyboardButton(text=title_text, callback_data=f"chat:quick_activate:{chat.id}:{page}"),
            InlineKeyboardButton(text="⚙️", callback_data=f"chat:view:{chat.id}"),
        ])

    # Navigation buttons
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"chats:page:{page - 1}"))
    nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"chats:page:{page + 1}"))

    if nav_row:
        buttons.append(nav_row)

    # Action row
    buttons.append([
        InlineKeyboardButton(text="➕ Новый диалог", callback_data="chat:new"),
        InlineKeyboardButton(text="🗑 Удалить...", callback_data="chats:delete_menu:1"),
        InlineKeyboardButton(text="✖️ Закрыть", callback_data="menu:close"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_delete_select_keyboard(
    chats: List[Chat],
    page: int,
    total_count: int,
    page_size: int = 5
) -> InlineKeyboardMarkup:
    total_pages = max(1, math.ceil(total_count / page_size))
    buttons = []

    for chat in chats:
        buttons.append([
            InlineKeyboardButton(text=f"❌ Удалить «{chat.title[:20]}»", callback_data=f"chat:delete_confirm:{chat.id}")
        ])

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"chats:delete_menu:{page - 1}"))
    nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"chats:delete_menu:{page + 1}"))

    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton(text="⬅️ К списку чатов", callback_data="chats:list")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_active_chat_keyboard(chat_id: uuid.UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗑 Удалить этот чат", callback_data=f"chat:delete_confirm:{chat_id}"),
            InlineKeyboardButton(text="🧹 Очистить контекст", callback_data=f"chat:clear:{chat_id}")
        ],
        [
            InlineKeyboardButton(text="🔄 Сменить модель", callback_data=f"chat:change_model:{chat_id}"),
            InlineKeyboardButton(text="📁 Все чаты", callback_data="chats:list")
        ],
        [
            InlineKeyboardButton(text="✖️ Закрыть", callback_data="menu:close")
        ]
    ])


def get_chat_actions_keyboard(chat_id: uuid.UUID, is_active: bool) -> InlineKeyboardMarkup:
    buttons = []

    # Activate button
    if not is_active:
        buttons.append([
            InlineKeyboardButton(text="✍️ Продолжить диалог (Выбрать)", callback_data=f"chat:activate:{chat_id}")
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text="✅ Текущий активный чат", callback_data="noop")
        ])

    # Second row: History & Change Model
    buttons.append([
        InlineKeyboardButton(text="📜 История", callback_data=f"chat:history:{chat_id}"),
        InlineKeyboardButton(text="🔄 Сменить модель", callback_data=f"chat:change_model:{chat_id}")
    ])

    # Third row: Rename & Clear context
    buttons.append([
        InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"chat:rename:{chat_id}"),
        InlineKeyboardButton(text="🧹 Очистить контекст", callback_data=f"chat:clear:{chat_id}")
    ])

    # Fourth row: Delete & Back
    buttons.append([
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"chat:delete_confirm:{chat_id}"),
        InlineKeyboardButton(text="⬅️ К списку чатов", callback_data="chats:list")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_delete_confirm_keyboard(chat_id: uuid.UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❌ Да, удалить навсегда", callback_data=f"chat:delete:{chat_id}"),
            InlineKeyboardButton(text="Отмена", callback_data=f"chat:view:{chat_id}")
        ]
    ])


def get_models_selection_keyboard(
    models: List[ModelCatalog],
    action: str = "create",
    chat_id: Optional[uuid.UUID] = None
) -> InlineKeyboardMarkup:
    buttons = []
    for model in models:
        prefix = f"chat:set_model:{chat_id}:{model.id}" if action == "change" else f"model:select:{model.id}"
        buttons.append([
            InlineKeyboardButton(text=model.display_name, callback_data=prefix)
        ])

    back_callback = f"chat:view:{chat_id}" if action == "change" and chat_id else "chats:list"
    buttons.append([
        InlineKeyboardButton(text="⬅️ Отмена", callback_data=back_callback)
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
