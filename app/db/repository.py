import uuid
from typing import Optional, List, Tuple
from sqlalchemy import select, func, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import User, Chat, Message, ModelCatalog


async def get_or_create_user(
    session: AsyncSession,
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None
) -> User:
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            id=user_id,
            username=username,
            first_name=first_name,
            is_allowed=True
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    else:
        # Update username/first_name if changed
        if user.username != username or user.first_name != first_name:
            user.username = username
            user.first_name = first_name
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
    await session.refresh(chat)

    # Set as active chat automatically
    await set_active_chat(session, user_id, chat.id)
    return chat


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
    user_stmt = select(User).where(User.id == user_id)
    user_res = await session.execute(user_stmt)
    user = user_res.scalar_one_or_none()
    if user and user.active_chat_id == chat_id:
        user.active_chat_id = None

    del_stmt = delete(Chat).where(Chat.id == chat_id)
    await session.execute(del_stmt)
    await session.commit()


async def add_message(
    session: AsyncSession,
    chat_id: uuid.UUID,
    role: str,
    content: str,
    has_image: bool = False
) -> Message:
    msg = Message(
        chat_id=chat_id,
        role=role,
        content=content,
        has_image=has_image
    )
    session.add(msg)
    # Touch chat updated_at
    touch_stmt = update(Chat).where(Chat.id == chat_id).values(updated_at=func.now())
    await session.execute(touch_stmt)
    await session.commit()
    await session.refresh(msg)
    return msg


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
        # OpenRouter NVIDIA Nemotron 3.5 Lightning Free
        ModelCatalog(
            id="nvidia/nemotron-3.5-lightning:free",
            provider="openrouter",
            display_name="⚡ Nemotron 3.5 Lightning (Free)",
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
    await session.commit()
