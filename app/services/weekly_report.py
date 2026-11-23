import asyncio
import html
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence
from zoneinfo import ZoneInfo

from aiogram import Bot

from app.core.config import settings
from app.db import repository
from app.db.repository import UserPromptStat
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

TELEGRAM_MAX_MESSAGE_LENGTH = 4096
DEFAULT_GRACE_WINDOW = timedelta(hours=12)
DEFAULT_POLL_INTERVAL_SECONDS = 60

WEEKDAY_SHORT_RU = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


@dataclass(frozen=True)
class ReportWindow:
    report_key: str
    period_start_local: datetime
    period_end_local: datetime
    period_start_utc: datetime
    period_end_utc: datetime


def pluralize_prompts(count: int) -> str:
    """Return Russian plural form for 'промпт'."""
    n = abs(count) % 100
    n1 = n % 10
    if 11 <= n <= 19:
        return "промптов"
    if n1 == 1:
        return "промпт"
    if 2 <= n1 <= 4:
        return "промпта"
    return "промптов"


def compute_latest_report_window(
    now_local: datetime,
    target_day: int,
    target_hour: int,
    target_minute: int,
) -> ReportWindow:
    """
    Compute the most recent scheduled report boundary <= now_local and its 7-day window.
    Constructs local wall-clock datetimes explicitly so DST transitions stay aligned to target_hour:target_minute.
    """
    tz = now_local.tzinfo
    if tz is None:
        raise ValueError("now_local must be timezone-aware")

    days_since = (now_local.weekday() - target_day) % 7
    slot_date = now_local.date() - timedelta(days=days_since)
    slot_local = datetime(
        slot_date.year, slot_date.month, slot_date.day, target_hour, target_minute, tzinfo=tz
    )
    if slot_local > now_local:
        slot_date = slot_date - timedelta(days=7)
        slot_local = datetime(
            slot_date.year, slot_date.month, slot_date.day, target_hour, target_minute, tzinfo=tz
        )

    prev_date = slot_date - timedelta(days=7)
    start_local = datetime(
        prev_date.year, prev_date.month, prev_date.day, target_hour, target_minute, tzinfo=tz
    )

    return ReportWindow(
        report_key=slot_local.strftime("%Y-%m-%d"),
        period_start_local=start_local,
        period_end_local=slot_local,
        period_start_utc=start_local.astimezone(timezone.utc),
        period_end_utc=slot_local.astimezone(timezone.utc),
    )


def compute_next_report_time(
    now_local: datetime,
    target_day: int,
    target_hour: int,
    target_minute: int,
) -> datetime:
    """Compute the next scheduled report datetime strictly after now_local."""
    tz = now_local.tzinfo
    if tz is None:
        raise ValueError("now_local must be timezone-aware")

    days_until = (target_day - now_local.weekday()) % 7
    next_date = now_local.date() + timedelta(days=days_until)
    next_local = datetime(
        next_date.year, next_date.month, next_date.day, target_hour, target_minute, tzinfo=tz
    )
    if next_local <= now_local:
        next_date = next_date + timedelta(days=7)
        next_local = datetime(
            next_date.year, next_date.month, next_date.day, target_hour, target_minute, tzinfo=tz
        )
    return next_local


def is_window_due(
    now_local: datetime,
    window: ReportWindow,
    grace_window: timedelta = DEFAULT_GRACE_WINDOW,
) -> bool:
    """Return True if now_local falls inside [period_end, period_end + grace_window]."""
    elapsed = now_local.astimezone(timezone.utc) - window.period_end_utc
    return timedelta(0) <= elapsed <= grace_window


def _format_user_label(stat: UserPromptStat) -> str:
    if stat.username:
        return f"@{html.escape(stat.username)}"
    if stat.first_name:
        return f"{html.escape(stat.first_name)} (ID <code>{stat.user_id}</code>)"
    return f"ID <code>{stat.user_id}</code>"


def _split_lines_to_chunks(lines: Sequence[str], max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> List[str]:
    chunks: List[str] = []
    current_lines: List[str] = []
    current_len = 0

    for line in lines:
        line_len = len(line)
        extra = 1 if current_lines else 0
        if current_lines and current_len + extra + line_len > max_length:
            chunks.append("\n".join(current_lines))
            current_lines = [line]
            current_len = line_len
        else:
            current_lines.append(line)
            current_len += extra + line_len

    if current_lines:
        chunks.append("\n".join(current_lines))
    return chunks


def format_weekly_report(
    stats: Sequence[UserPromptStat],
    period_start: datetime,
    period_end: datetime,
    tz_name: str,
    title: str = "📊 <b>Еженедельный отчёт по боту</b>",
    footer_note: Optional[str] = None,
    max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH,
) -> List[str]:
    """Render usage statistics as one or more Telegram HTML messages."""
    tz = ZoneInfo(tz_name)
    start_str = period_start.astimezone(tz).strftime("%d.%m.%Y %H:%M")
    end_str = period_end.astimezone(tz).strftime("%d.%m.%Y %H:%M")

    lines: List[str] = [
        title,
        f"🗓 Период: {start_str} — {end_str} ({html.escape(tz_name)})",
        "",
    ]

    if not stats:
        lines.append("😴 За этот период промптов не было (0).")
    else:
        total_prompts = 0
        for idx, stat in enumerate(stats, start=1):
            total_prompts += stat.total_prompts
            label = _format_user_label(stat)
            count_part = f"<b>{stat.total_prompts}</b> {pluralize_prompts(stat.total_prompts)}"
            photo_part = f" (📸 фото: {stat.photo_prompts})" if stat.photo_prompts > 0 else ""
            lines.append(f"{idx}. {label} — {count_part}{photo_part}")

        lines.append("")
        lines.append(
            f"📈 <b>Всего:</b> {total_prompts} {pluralize_prompts(total_prompts)} "
            f"(пользователей: {len(stats)})"
        )

    if footer_note:
        lines.append(footer_note)

    return _split_lines_to_chunks(lines, max_length=max_length)


async def send_weekly_report_if_due(
    bot: Bot,
    now_utc: Optional[datetime] = None,
) -> bool:
    """
    Check whether the scheduled weekly report should be sent right now.
    Returns True if a report was sent during this call.
    """
    if not settings.WEEKLY_REPORT_ENABLED:
        return False

    target_chat_id = settings.effective_report_chat_id
    if not target_chat_id:
        logger.warning("Weekly report skipped: neither REPORT_CHAT_ID nor ALLOWED_USER_IDS is configured.")
        return False

    tz = ZoneInfo(settings.REPORT_TIMEZONE)
    current_utc = now_utc or datetime.now(timezone.utc)
    now_local = current_utc.astimezone(tz)

    window = compute_latest_report_window(
        now_local=now_local,
        target_day=settings.WEEKLY_REPORT_DAY,
        target_hour=settings.WEEKLY_REPORT_HOUR,
        target_minute=settings.WEEKLY_REPORT_MINUTE,
    )

    if not is_window_due(now_local, window):
        return False

    async with async_session_factory() as session:
        if await repository.has_weekly_report_run(session, window.report_key):
            return False

        stats = await repository.get_prompt_stats(
            session=session,
            start_dt=window.period_start_utc,
            end_dt=window.period_end_utc,
        )

    chunks = format_weekly_report(
        stats=stats,
        period_start=window.period_start_local,
        period_end=window.period_end_local,
        tz_name=settings.REPORT_TIMEZONE,
    )

    for chunk in chunks:
        await bot.send_message(
            chat_id=target_chat_id,
            text=chunk,
            parse_mode="HTML",
            request_timeout=15,
        )

    total_prompts = sum(s.total_prompts for s in stats)
    async with async_session_factory() as session:
        await repository.record_weekly_report_run(
            session=session,
            report_key=window.report_key,
            period_start=window.period_start_utc,
            period_end=window.period_end_utc,
            total_prompts=total_prompts,
        )

    logger.info(
        "Weekly report '%s' delivered to chat_id=%s (users=%d, prompts=%d).",
        window.report_key,
        target_chat_id,
        len(stats),
        total_prompts,
    )
    return True


async def weekly_report_loop(
    bot: Bot,
    stop_event: asyncio.Event,
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
) -> None:
    """Background loop that checks and delivers the scheduled weekly report."""
    tz = ZoneInfo(settings.REPORT_TIMEZONE)
    next_run = compute_next_report_time(
        now_local=datetime.now(tz),
        target_day=settings.WEEKLY_REPORT_DAY,
        target_hour=settings.WEEKLY_REPORT_HOUR,
        target_minute=settings.WEEKLY_REPORT_MINUTE,
    )
    logger.info(
        "Weekly report scheduler started. Next scheduled report: %s (%s).",
        next_run.strftime("%Y-%m-%d %H:%M"),
        settings.REPORT_TIMEZONE,
    )

    while not stop_event.is_set():
        try:
            await send_weekly_report_if_due(bot)
        except Exception as exc:
            logger.warning("Weekly report check/delivery failed: %s", exc)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_interval_seconds)
        except asyncio.TimeoutError:
            pass

    logger.info("Weekly report scheduler stopped.")
