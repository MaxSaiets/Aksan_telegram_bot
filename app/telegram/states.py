"""FSM states for the Telegram bot."""
from aiogram.fsm.state import State, StatesGroup


class VideoUpload(StatesGroup):
    """
    States for the video upload flow:
      waiting_video   → user pressed "Відправити відео", waiting for a video message
      waiting_confirm → video received, asking user to confirm or cancel
    """
    waiting_video   = State()
    waiting_confirm = State()


class PhotoUpload(StatesGroup):
    """State for collecting multiple photos before a code message."""

    waiting_photos = State()
