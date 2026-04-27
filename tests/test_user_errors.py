from src.bot import _user_visible_error
from src.messages import (
    ERROR_TEXT,
    NOT_ENOUGH_CREDITS_TEXT,
    NSFW_BLOCKED_TEXT,
    TIMEOUT_TEXT,
)


def test_user_visible_maps_credits() -> None:
    exc = Exception("Failed to create request: HTTP 403: Not enough credits")
    assert _user_visible_error(exc) == NOT_ENOUGH_CREDITS_TEXT


def test_user_visible_maps_nsfw() -> None:
    exc = Exception("Generation failed with status nsfw (payload={})")
    assert _user_visible_error(exc) == NSFW_BLOCKED_TEXT


def test_user_visible_maps_timeout() -> None:
    exc = Exception("Generation timeout after 300 seconds")
    assert _user_visible_error(exc) == TIMEOUT_TEXT


def test_user_visible_default() -> None:
    exc = Exception("something else")
    assert _user_visible_error(exc) == ERROR_TEXT
