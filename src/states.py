"""FSM states — empty for the Earth Zoom In single-flow bot.

We intentionally don't use FSM: any incoming photo triggers a render, full
stop. Kept as a stub so tests/imports don't break.
"""
from aiogram.fsm.state import StatesGroup


class GenerationStates(StatesGroup):
    """Kept for backward-compat with older tests."""
