"""Video delivery happy-path + fallback: the bot must actually send the video."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import src.bot as bot_module


@pytest.fixture
def mock_message():
    msg = AsyncMock()
    msg.answer_video = AsyncMock()
    msg.answer = AsyncMock()
    return msg


@pytest.fixture
def mock_status_message():
    status = AsyncMock()
    status.edit_text = AsyncMock()
    status.delete = AsyncMock()
    return status


def test_deliver_video_downloads_and_sends_bytes(mock_message, mock_status_message) -> None:
    fake_bytes = b"\x00\x01\x02fakevideo"

    async def fake_download(url: str, total_timeout_seconds: int = 240) -> bytes:
        return fake_bytes

    with patch.object(bot_module, "_download_video_bytes", side_effect=fake_download):
        asyncio.run(
            bot_module._deliver_video(
                message=mock_message,
                status_message=mock_status_message,
                video_url="https://cdn.example/video.mp4",
            )
        )

    mock_message.answer_video.assert_awaited_once()
    kwargs = mock_message.answer_video.call_args.kwargs
    assert "video" in kwargs
    assert not isinstance(kwargs["video"], str)
    assert kwargs.get("supports_streaming") is True
    caption = kwargs.get("caption", "")
    assert "Earth Zoom In" in caption


def test_deliver_video_fallback_to_url_when_download_fails(
    mock_message, mock_status_message
) -> None:
    async def fake_download(url: str, total_timeout_seconds: int = 240) -> bytes:
        raise RuntimeError("network down")

    with patch.object(bot_module, "_download_video_bytes", side_effect=fake_download):
        asyncio.run(
            bot_module._deliver_video(
                message=mock_message,
                status_message=mock_status_message,
                video_url="https://cdn.example/video.mp4",
            )
        )

    mock_message.answer_video.assert_awaited_once()
    kwargs = mock_message.answer_video.call_args.kwargs
    assert kwargs["video"] == "https://cdn.example/video.mp4"
