import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, List, Tuple
from sqlalchemy import select, func, delete, update, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import User, Chat, Message, ModelCatalog, PromptLog, WeeklyReportRun

_UNSET: Any = object()


@dataclass(frozen=True)
class UserPromptStat:
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    total_prompts: int
    photo_prompts: int


async def get_or_create_user(
    session: AsyncSession,
    user_id: int,
    username: Any = _UNSET,
    first_name: Any = _UNSET
) -> User:
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            id=user_id,
            username=None if username is _UNSET else username,
            first_name=None if first_name is _UNSET else first_name,
            is_allowed=True
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    else:
        changed = False
        if username is not _UNSET and user.username != username:
            user.username = username
            changed = True
        if first_name is not _UNSET and user.first_name != first_name:
            user.first_name = first_name
            changed = True
        if changed:
            await session.commit()
    return user


async def set_active_chat(session: AsyncSession, user_id: int, chat_id: Optional[uuid.UUID]):
    stmt = update(User).where(User.id == user_id).values(active_chat_id=chat_id)
    await session.execute(stmt)
    await session.commit()


async def get_active_chat(session: AsyncSession, user_id: int) -> Optional[Chat]:
    stmt = (
        select(Chat)
        .join(User, User.active_chat_id == Chat.id)
        .where(User.id == user_id)
        .options(selectinload(Chat.model))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_chat(
    session: AsyncSession,
    user_id: int,
    model_id: str,
    title: str,
    system_prompt: Optional[str] = None
) -> Chat:
    chat = Chat(
        user_id=user_id,
        model_id=model_id,
        title=title,
        system_prompt=system_prompt
    )
    session.add(chat)
    await session.commit()

    # Set as active chat automatically
    await set_active_chat(session, user_id, chat.id)
    # Return chat with eagerly loaded model relation
    return await get_chat(session, chat.id)


async def get_chat(session: AsyncSession, chat_id: uuid.UUID) -> Optional[Chat]:
    stmt = (
        select(Chat)
        .where(Chat.id == chat_id)
        .options(selectinload(Chat.model))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_user_chats(
    session: AsyncSession,
    user_id: int,
    page: int = 1,
    page_size: int = 5
) -> Tuple[List[Chat], int]:
    # Count total
    count_stmt = select(func.count()).select_from(Chat).where(Chat.user_id == user_id)
    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    # Fetch page
    offset = (page - 1) * page_size
    stmt = (
        select(Chat)
        .where(Chat.user_id == user_id)
        .order_by(Chat.updated_at.desc())
        .offset(offset)
        .limit(page_size)
        .options(selectinload(Chat.model))
    )
    result = await session.execute(stmt)
    chats = list(result.scalars().all())
    return chats, total


async def update_chat_model(session: AsyncSession, chat_id: uuid.UUID, model_id: str):
    stmt = update(Chat).where(Chat.id == chat_id).values(model_id=model_id)
    await session.execute(stmt)
    await session.commit()


async def rename_chat(session: AsyncSession, chat_id: uuid.UUID, new_title: str):
    stmt = update(Chat).where(Chat.id == chat_id).values(title=new_title)
    await session.execute(stmt)
    await session.commit()


async def clear_chat_history(session: AsyncSession, chat_id: uuid.UUID):
    stmt = delete(Message).where(Message.chat_id == chat_id)
    await session.execute(stmt)
    await session.commit()


async def delete_chat(session: AsyncSession, user_id: int, chat_id: uuid.UUID):
    # If active, unset active_chat_id
    await session.execute(
        update(User)
        .where(User.id == user_id, User.active_chat_id == chat_id)
        .values(active_chat_id=None)
    )
    # Delete the chat and all its messages (cascade)
    await session.execute(delete(Chat).where(Chat.id == chat_id))
    await session.commit()


async def add_message(
    session: AsyncSession,
    chat_id: uuid.UUID,
    role: str,
    content: str,
    has_image: bool = False,
    telegram_message_id: Optional[int] = None
) -> Message:
    msg = Message(
        chat_id=chat_id,
        role=role,
        content=content,
        has_image=has_image,
        telegram_message_id=telegram_message_id
    )
    session.add(msg)
    # Touch chat updated_at
    touch_stmt = update(Chat).where(Chat.id == chat_id).values(updated_at=func.now())
    await session.execute(touch_stmt)
    await session.commit()
    await session.refresh(msg)
    return msg


async def get_chat_telegram_message_ids(
    session: AsyncSession,
    chat_id: uuid.UUID
) -> List[int]:
    """Get all stored telegram message IDs for a chat to allow physical deletion in Telegram."""
    stmt = (
        select(Message.telegram_message_id)
        .where(Message.chat_id == chat_id, Message.telegram_message_id.isnot(None))
        .order_by(Message.created_at.asc())
    )
    result = await session.execute(stmt)
    return [mid for mid in result.scalars().all() if mid is not None]


async def get_chat_context(
    session: AsyncSession,
    chat_id: uuid.UUID,
    limit: int = 10
) -> List[Message]:
    """Retrieves the last N messages in ascending chronological order."""
    stmt = (
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    messages = list(result.scalars().all())
    messages.reverse()
    return messages


async def get_active_models(session: AsyncSession) -> List[ModelCatalog]:
    stmt = select(ModelCatalog).where(ModelCatalog.is_active == True).order_by(ModelCatalog.provider, ModelCatalog.display_name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def seed_default_models(session: AsyncSession):
    """Seed free models catalog if empty or missing defaults."""
    defaults = [
        # AI Horde (Free, Uncensored Qwen)
        ModelCatalog(
            id="horde/qwen-2.5-72b-uncensored",
            provider="horde",
            display_name="🏴‍☠️ Qwen 2.5 72B (Uncensored / Free)",
            supports_vision=False,
            is_active=True
        ),
        # OpenRouter Free Router (Auto-selects best available 100% free model)
        ModelCatalog(
            id="openrouter/free",
            provider="openrouter",
            display_name="🌐 OpenRouter Auto (100% Free)",
            supports_vision=False,
            is_active=True
        ),
        # OpenRouter Gemma 4 31B Free
        ModelCatalog(
            id="google/gemma-4-31b-it:free",
            provider="openrouter",
            display_name="💎 Gemma 4 31B (Google / Free)",
            supports_vision=False,
            is_active=True
        ),
        # Google Gemini (Supports Vision / Multimodal)
        ModelCatalog(
            id="gemini-2.0-flash",
            provider="gemini",
            display_name="📸 Gemini 2.0 Flash (Multimodal & Vision)",
            supports_vision=True,
            is_active=True
        ),
    ]

    for model in defaults:
        existing = await session.get(ModelCatalog, model.id)
        if not existing:
            session.add(model)

    # Retired models: move existing chats to the fallback model, then delete from the catalog
    retired_ids = ("nvidia/nemotron-3.5-lightning:free",)
    fallback_id = "openrouter/free"
    await session.flush()
    await session.execute(
        update(Chat).where(Chat.model_id.in_(retired_ids)).values(model_id=fallback_id)
    )
    await session.execute(delete(ModelCatalog).where(ModelCatalog.id.in_(retired_ids)))
    await session.commit()


async def log_prompt(
    session: AsyncSession,
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    chat_id: Optional[uuid.UUID] = None,
    model_id: Optional[str] = None,
    has_image: bool = False,
) -> PromptLog:
    """Record a user prompt event in append-only prompt_logs and sync user profile metadata."""
    user = await session.get(User, user_id)
    if user:
        if user.username != username:
            user.username = username
        if user.first_name != first_name:
            user.first_name = first_name

    entry = PromptLog(
        user_id=user_id,
        username=username,
        first_name=first_name,
        chat_id=chat_id,
        model_id=model_id,
        has_image=has_image,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def get_prompt_stats(
    session: AsyncSession,
    start_dt: datetime,
    end_dt: datetime,
) -> List[UserPromptStat]:
    """Aggregate prompt counts per user for the half-open interval [start_dt, end_dt)."""
    stmt = (
        select(
            PromptLog.user_id,
            User.username.label("current_username"),
            User.first_name.label("current_first_name"),
            func.max(PromptLog.username).label("snapshot_username"),
            func.max(PromptLog.first_name).label("snapshot_first_name"),
            func.count(PromptLog.id).label("total_prompts"),
            func.sum(case((PromptLog.has_image.is_(True), 1), else_=0)).label("photo_prompts"),
        )
        .outerjoin(User, User.id == PromptLog.user_id)
        .where(PromptLog.created_at >= start_dt, PromptLog.created_at < end_dt)
        .group_by(PromptLog.user_id, User.username, User.first_name)
        .order_by(func.count(PromptLog.id).desc(), PromptLog.user_id.asc())
    )
    result = await session.execute(stmt)
    stats: List[UserPromptStat] = []
    for row in result.all():
        stats.append(
            UserPromptStat(
                user_id=row.user_id,
                username=row.current_username or row.snapshot_username,
                first_name=row.current_first_name or row.snapshot_first_name,
                total_prompts=int(row.total_prompts or 0),
                photo_prompts=int(row.photo_prompts or 0),
            )
        )
    return stats


async def has_weekly_report_run(session: AsyncSession, report_key: str) -> bool:
    stmt = select(WeeklyReportRun.report_key).where(WeeklyReportRun.report_key == report_key)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def record_weekly_report_run(
    session: AsyncSession,
    report_key: str,
    period_start: datetime,
    period_end: datetime,
    total_prompts: int,
) -> None:
    existing = await session.get(WeeklyReportRun, report_key)
    if existing:
        return
    run = WeeklyReportRun(
        report_key=report_key,
        period_start=period_start,
        period_end=period_end,
        total_prompts=total_prompts,
    )
    session.add(run)
    await session.commit()
