"""Local Telegram proxy autodiscovery."""
from __future__ import annotations

import asyncio

import pytest

from src import telegram_proxy_probe as probe


def test_discover_returns_none_when_nothing_works(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no(_token: str, _proxy: str, *, timeout_total: float) -> bool:
        return False

    monkeypatch.setattr(probe, "_getme_ok", _no)
    assert asyncio.run(probe.discover_local_telegram_proxy("dummy-token")) is None


def test_discover_returns_matching_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _yes_for_10808(
        _token: str, proxy: str, *, timeout_total: float,
    ) -> bool:
        return "10808" in proxy

    monkeypatch.setattr(probe, "_getme_ok", _yes_for_10808)
    out = asyncio.run(probe.discover_local_telegram_proxy("dummy-token"))
    assert out == "socks5://127.0.0.1:10808"
