"""Keyboard tests — only the single reply keyboard remains."""
from src.keyboards import EARTH_ZOOM_BUTTON_TEXT, main_keyboard


def test_main_keyboard_has_earth_zoom_button() -> None:
    kb = main_keyboard()
    flat = [btn.text for row in kb.keyboard for btn in row]
    assert EARTH_ZOOM_BUTTON_TEXT in flat


def test_keyboard_resizes() -> None:
    kb = main_keyboard()
    assert kb.resize_keyboard is True


def test_earth_zoom_label_in_russian() -> None:
    assert "Earth Zoom In" in EARTH_ZOOM_BUTTON_TEXT
