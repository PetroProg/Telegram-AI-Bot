from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        [
            KeyboardButton(text="💬 Мои чаты"),
            KeyboardButton(text="➕ Новый чат"),
        ],
        [
            KeyboardButton(text="ℹ️ Активный чат"),
            KeyboardButton(text="⚙️ Помощь"),
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
