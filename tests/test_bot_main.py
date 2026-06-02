"""Guards against polling issues: webhook must be cleared before getUpdates."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.config import Settings


def test_main_awaits_delete_webhook_before_start_polling() -> None:
    import src.bot as bot_module

    settings = Settings(
        telegram_bot_token="test-token",
        telegram_proxy=None,
        hf_api_key="id",
        hf_api_secret="sec",
        hf_poll_interval_seconds=3,
        hf_max_wait_seconds=420,
        hf_http_timeout_seconds=60,
        hf_upload_timeout_seconds=120,
    )

    call_order: list[str] = []

    async def delete_webhook(**kwargs: object) -> None:
        call_order.append("delete_webhook")

    async def start_polling(*args: object, **kwargs: object) -> None:
        call_order.append("start_polling")

    mock_me = MagicMock()
    mock_me.username = "testbot"
    mock_me.id = 1

    mock_bot = MagicMock()
    mock_bot.get_me = AsyncMock(return_value=mock_me)
    mock_bot.delete_webhook = AsyncMock(side_effect=delete_webhook)
    mock_bot.set_my_commands = AsyncMock()

    mock_dp = MagicMock()
    mock_dp.start_polling = AsyncMock(side_effect=start_polling)

    async def stub_preload(**kwargs: object) -> str:
        call_order.append("preload_earth")
        return "https://cdn/asset-earth.jpg"

    with patch.object(bot_module, "load_settings", return_value=settings), \
         patch.object(bot_module, "discover_local_telegram_proxy", new_callable=AsyncMock) as mock_disc, \
         patch.object(bot_module, "Bot", return_value=mock_bot), \
         patch.object(bot_module, "AiohttpSession"), \
         patch.object(bot_module, "Dispatcher", return_value=mock_dp), \
         patch.object(bot_module, "MemoryStorage"), \
         patch.object(bot_module, "preload_earth_url", side_effect=stub_preload):
        mock_disc.return_value = None
        asyncio.run(bot_module.main())

    mock_bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=True)
    mock_bot.set_my_commands.assert_awaited_once()
    mock_dp.start_polling.assert_awaited_once_with(mock_bot)
    # Earth preload runs before polling starts so first user doesn't wait.
    assert call_order == ["preload_earth", "delete_webhook", "start_polling"]
    mock_bot.get_me.assert_awaited()
