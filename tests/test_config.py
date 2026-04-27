"""Tests for the simplified Earth Zoom In config."""
import os

import pytest

from src.config import load_settings

_ENV_KEYS = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_PROXY",
    "HF_API_KEY",
    "HF_API_SECRET",
    "HF_KEY",
    "HF_POLL_INTERVAL_SECONDS",
    "HF_MAX_WAIT_SECONDS",
    "HF_HTTP_TIMEOUT_SECONDS",
    "HF_UPLOAD_TIMEOUT_SECONDS",
]


@pytest.fixture(autouse=True)
def clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.config.load_dotenv", lambda *args, **kwargs: None)
    for key in _ENV_KEYS:
        os.environ.pop(key, None)


def test_combined_hf_key_parsing() -> None:
    os.environ["TELEGRAM_BOT_TOKEN"] = "t"
    os.environ["HF_KEY"] = "key123:secret456"

    settings = load_settings()

    assert settings.telegram_proxy is None
    assert settings.hf_api_key == "key123"
    assert settings.hf_api_secret == "secret456"
    assert settings.hf_auth_header == "Key key123:secret456"
    assert settings.hf_poll_interval_seconds == 3
    assert settings.hf_max_wait_seconds == 420


def test_requires_hf_credentials() -> None:
    os.environ["TELEGRAM_BOT_TOKEN"] = "t"
    with pytest.raises(ValueError):
        load_settings()


def test_requires_telegram_token() -> None:
    os.environ["HF_KEY"] = "a:b"
    with pytest.raises(ValueError):
        load_settings()


def test_separate_key_and_secret() -> None:
    os.environ["TELEGRAM_BOT_TOKEN"] = "t"
    os.environ["HF_API_KEY"] = "id"
    os.environ["HF_API_SECRET"] = "sec"
    settings = load_settings()
    assert settings.hf_api_key == "id"
    assert settings.hf_api_secret == "sec"
