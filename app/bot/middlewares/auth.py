import html
import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject, User

from app.core.config import settings

logger = logging.getLogger(__name__)


class WhitelistMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user: User = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        allowed = settings.allowed_users_set
        # If whitelist is configured and user is not in it
        if allowed and user.id not in allowed:
            logger.warning(f"Unauthorized access attempt from user_id: {user.id} (@{user.username})")

            action_preview = "неизвестное действие"
            if hasattr(event, "message") and event.message:
                if event.message.text:
                    action_preview = event.message.text[:200]
                elif event.message.photo:
                    action_preview = "[фото]"
                else:
                    action_preview = "[сообщение]"
                await event.message.answer("⛔ Доступ ограничен. Этот бот работает в приватном режиме.")
            elif hasattr(event, "callback_query") and event.callback_query:
                action_preview = f"callback: {event.callback_query.data or ''}"
                await event.callback_query.answer("⛔ Доступ ограничен.", show_alert=True)

            owner_id = settings.owner_user_id
            bot: Bot = data.get("bot")
            if owner_id and bot:
                username_str = f"@{html.escape(user.username)}" if user.username else "без username"
                full_name = html.escape(user.full_name or "Неизвестно")
                alert_text = (
                    "🚨 <b>Попытка постороннего доступа к боту</b>\n\n"
                    f"👤 <b>Имя:</b> {full_name}\n"
                    f"🔗 <b>Username:</b> {username_str}\n"
                    f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                    f"💬 <b>Действие:</b> <code>{html.escape(action_preview)}</code>"
                )
                try:
                    await bot.send_message(chat_id=owner_id, text=alert_text, parse_mode="HTML")
                except Exception as e:
                    logger.warning(f"Failed to send unauthorized access alert to owner {owner_id}: {e}")
            return

        return await handler(event, data)
