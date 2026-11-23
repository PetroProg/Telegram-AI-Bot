import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat

from app.core.config import settings
from app.core.logger import setup_logger
from app.db.session import init_db, async_session_factory
from app.db.repository import seed_default_models
from app.bot.middlewares.auth import WhitelistMiddleware
from app.bot.handlers import start, chats, admin, messages
from app.services.weekly_report import weekly_report_loop

logger = logging.getLogger("main")


async def main():
    setup_logger()
    logger.info("Initializing Telegram AI Bot backend...")

    if not settings.BOT_TOKEN:
        logger.error("BOT_TOKEN is empty! Please set BOT_TOKEN in .env file.")
        sys.exit(1)

    # 1. Initialize DB tables & seed models
    try:
        logger.info("Connecting to database and running schema setup...")
        await init_db()
        async with async_session_factory() as session:
            await seed_default_models(session)
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.exception(f"Failed to initialize database: {e}")
        sys.exit(1)

    # 2. Setup Bot & Dispatcher
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # 3. Setup Middlewares
    dp.update.middleware(WhitelistMiddleware())

    # 4. Include Routers
    dp.include_router(start.router)
    dp.include_router(chats.router)
    dp.include_router(admin.router)
    dp.include_router(messages.router)

    report_stop_event = asyncio.Event()
    report_task = None

    logger.info("Starting bot long polling...")
    try:
        base_commands = [
            BotCommand(command="start", description="Перезапустить бота и меню"),
            BotCommand(command="chats", description="Список диалогов (выбор в 1 клик)"),
            BotCommand(command="new", description="Создать новый диалог"),
            BotCommand(command="current", description="Активный чат и настройки"),
            BotCommand(command="clean", description="Очистить экран Telegram (память сохраняется)"),
            BotCommand(command="clear", description="Очистить контекст и сообщения чата"),
            BotCommand(command="delete", description="Удалить чат"),
            BotCommand(command="help", description="Справка"),
        ]
        await bot.set_my_commands(base_commands)

        owner_chat_ids = {
            uid for uid in (settings.owner_user_id, settings.REPORT_CHAT_ID) if uid is not None
        }
        owner_commands = [
            *base_commands,
            BotCommand(command="stats", description="Статистика промптов за 7 дней"),
        ]
        for owner_chat_id in owner_chat_ids:
            try:
                await bot.set_my_commands(
                    owner_commands,
                    scope=BotCommandScopeChat(chat_id=owner_chat_id),
                )
            except Exception as e:
                logger.warning("Failed to set owner commands menu for chat_id=%s: %s", owner_chat_id, e)
        await bot.delete_webhook(drop_pending_updates=True)

        if settings.WEEKLY_REPORT_ENABLED:
            report_task = asyncio.create_task(weekly_report_loop(bot, report_stop_event))

        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if report_task is not None:
            report_stop_event.set()
            try:
                await asyncio.wait_for(report_task, timeout=5.0)
            except asyncio.TimeoutError:
                report_task.cancel()
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down...")
