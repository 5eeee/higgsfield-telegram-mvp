from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    telegram_bot_token: str
    telegram_proxy: str | None

    hf_api_key: str
    hf_api_secret: str

    hf_poll_interval_seconds: int
    hf_max_wait_seconds: int
    hf_http_timeout_seconds: int
    hf_upload_timeout_seconds: int

    @property
    def hf_auth_header(self) -> str:
        return f"Key {self.hf_api_key}:{self.hf_api_secret}"


def _require(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None or not str(value).strip():
        raise ValueError(f"Missing required env var: {name}")
    return str(value).strip()


def _optional(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def load_settings() -> Settings:
    load_dotenv()
    combined_key = os.getenv("HF_KEY", "").strip()
    hf_api_key = os.getenv("HF_API_KEY", "").strip()
    hf_api_secret = os.getenv("HF_API_SECRET", "").strip()

    if combined_key and ":" in combined_key and (not hf_api_key or not hf_api_secret):
        hf_api_key, hf_api_secret = combined_key.split(":", maxsplit=1)

    if not hf_api_key or not hf_api_secret:
        raise ValueError(
            "Higgsfield credentials are missing. Set HF_API_KEY + HF_API_SECRET "
            "or HF_KEY=key_id:key_secret.",
        )

    return Settings(
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        telegram_proxy=_optional("TELEGRAM_PROXY"),
        hf_api_key=hf_api_key,
        hf_api_secret=hf_api_secret,
        hf_poll_interval_seconds=int(_require("HF_POLL_INTERVAL_SECONDS", "3")),
        hf_max_wait_seconds=int(_require("HF_MAX_WAIT_SECONDS", "420")),
        hf_http_timeout_seconds=int(_require("HF_HTTP_TIMEOUT_SECONDS", "60")),
        hf_upload_timeout_seconds=int(_require("HF_UPLOAD_TIMEOUT_SECONDS", "120")),
    )
