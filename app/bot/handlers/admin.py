import html
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.core.config import settings
from app.db import repository
from app.db.session import async_session_factory
from app.services.weekly_report import (
    WEEKDAY_SHORT_RU,
    compute_next_report_time,
    format_weekly_report,
)

logger = logging.getLogger(__name__)
router = Router(name="admin")


@router.message(Command("stats"))
async def handle_stats_command(message: Message):
    """Owner-only command to view prompt usage statistics for the last 7 days."""
    owner_ids = {uid for uid in (settings.owner_user_id, settings.REPORT_CHAT_ID) if uid is not None}
    if not owner_ids or not message.from_user or message.from_user.id not in owner_ids:
        await message.answer("⛔ Команда доступна только владельцу бота.")
        return

    tz = ZoneInfo(settings.REPORT_TIMEZONE)
    now_utc = datetime.now(timezone.utc)
    start_utc = now_utc - timedelta(days=7)

    async with async_session_factory() as session:
        stats = await repository.get_prompt_stats(
            session=session,
            start_dt=start_utc,
            end_dt=now_utc,
        )

    footer_note = None
    if settings.WEEKLY_REPORT_ENABLED:
        next_run = compute_next_report_time(
            now_local=now_utc.astimezone(tz),
            target_day=settings.WEEKLY_REPORT_DAY,
            target_hour=settings.WEEKLY_REPORT_HOUR,
            target_minute=settings.WEEKLY_REPORT_MINUTE,
        )
        weekday_ru = WEEKDAY_SHORT_RU[next_run.weekday()]
        footer_note = (
            f"\n⏰ <i>Следующий автоотчёт: {weekday_ru}, "
            f"{next_run.strftime('%d.%m.%Y %H:%M')} ({html.escape(settings.REPORT_TIMEZONE)})</i>"
        )
    else:
        footer_note = "\n⏸ <i>Автоотправка еженедельных отчётов отключена в настройках.</i>"

    chunks = format_weekly_report(
        stats=stats,
        period_start=start_utc,
        period_end=now_utc,
        tz_name=settings.REPORT_TIMEZONE,
        title="📊 <b>Статистика за последние 7 дней</b>",
        footer_note=footer_note,
    )

    for chunk in chunks:
        await message.answer(chunk, parse_mode="HTML")
