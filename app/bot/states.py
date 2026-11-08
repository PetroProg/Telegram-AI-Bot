from aiogram.fsm.state import State, StatesGroup


class ChatCreateState(StatesGroup):
    waiting_for_model = State()
    waiting_for_title = State()


class ChatRenameState(StatesGroup):
    waiting_for_new_title = State()
