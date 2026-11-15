from typing import List, Optional
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message


async def delete_messages_safely(bot: Bot, chat_id: int, message_ids: List[int]) -> None:
    """Deletes message IDs in Telegram, ignoring missing or >48h-old messages."""
    unique_ids = [mid for mid in dict.fromkeys(message_ids) if mid and mid > 0]
    if not unique_ids:
        return
    try:
        await bot.delete_messages(chat_id=chat_id, message_ids=unique_ids)
    except Exception:
        for mid in unique_ids:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=mid)
            except Exception:
                pass


async def cleanup_menus_and_reset_state(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    trigger_message_id: Optional[int] = None,
) -> None:
    """Deletes previous service menu, temporary FSM messages, and the trigger message."""
    data = await state.get_data()
    to_delete: List[int] = []

    last_menu_msg_id = data.get("last_menu_msg_id")
    if last_menu_msg_id:
        to_delete.append(last_menu_msg_id)

    temp_msg_ids = data.get("temp_msg_ids") or []
    to_delete.extend(temp_msg_ids)

    if trigger_message_id:
        to_delete.append(trigger_message_id)

    await state.clear()
    await delete_messages_safely(bot, chat_id, to_delete)


async def track_menu_message(state: FSMContext, message: Optional[Message]) -> None:
    """Saves the latest service menu message ID so it can be auto-cleaned later."""
    if message:
        await state.update_data(last_menu_msg_id=message.message_id)


async def add_temp_message_id(state: FSMContext, message_id: Optional[int]) -> None:
    """Appends an intermediate FSM message ID for cleanup when the flow completes."""
    if not message_id:
        return
    data = await state.get_data()
    temp_ids = list(data.get("temp_msg_ids") or [])
    temp_ids.append(message_id)
    await state.update_data(temp_msg_ids=temp_ids)
