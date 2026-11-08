import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
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
            if hasattr(event, "message") and event.message:
                await event.message.answer("⛔ Доступ ограничен. Этот бот работает в приватном режиме.")
            elif hasattr(event, "callback_query") and event.callback_query:
                await event.callback_query.answer("⛔ Доступ ограничен.", show_alert=True)
            return

        return await handler(event, data)
