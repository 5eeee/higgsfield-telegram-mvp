"""Single reply keyboard — only Earth Zoom In entry point."""
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

EARTH_ZOOM_BUTTON_TEXT = "🌍 Сделать Earth Zoom In"


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=EARTH_ZOOM_BUTTON_TEXT)]],
        resize_keyboard=True,
        one_time_keyboard=False,
    )
