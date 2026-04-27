"""Unit tests for payload/parsing in HiggsfieldAPI without hitting the network."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import src.higgsfield_api as hfmod
from src.higgsfield_api import (
    HiggsfieldAPI,
    HiggsfieldAPIError,
    HiggsfieldRequestResult,
    SEEDANCE_ALLOWED_DURATIONS,
)


def test_video_url_extracted_when_present() -> None:
    result = HiggsfieldRequestResult(
        status="completed",
        request_id="abc",
        payload={"video": {"url": "https://cdn.example/video.mp4"}},
    )
    assert result.video_url == "https://cdn.example/video.mp4"


def test_video_url_none_for_missing_video_object() -> None:
    result = HiggsfieldRequestResult(
        status="completed",
        request_id="abc",
        payload={"images": [{"url": "https://cdn.example/image.jpg"}]},
    )
    assert result.video_url is None


def test_video_url_from_videos_array() -> None:
    result = HiggsfieldRequestResult(
        status="completed",
        request_id="abc",
        payload={"videos": [{"url": "https://cdn.example/out.mp4"}]},
    )
    assert result.video_url == "https://cdn.example/out.mp4"


def test_video_url_from_nested_results() -> None:
    result = HiggsfieldRequestResult(
        status="completed",
        request_id="abc",
        payload={"results": [{"video": {"url": "https://cdn.example/v2.mp4"}}]},
    )
    assert result.video_url == "https://cdn.example/v2.mp4"


def test_image_url_extracted_from_images_array() -> None:
    result = HiggsfieldRequestResult(
        status="completed",
        request_id="abc",
        payload={"images": [{"url": "https://cdn.example/earth.jpg"}]},
    )
    assert result.image_url == "https://cdn.example/earth.jpg"


def _fake_response(status: int, payload: dict) -> AsyncMock:
    response = AsyncMock()
    response.status = status
    response.json = AsyncMock(return_value=payload)
    response.text = AsyncMock(return_value="")
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    return response


class _FakeSession:
    """Minimal async ctx manager session that records sent JSON bodies."""

    def __init__(self, post_payload: dict, status: int = 200) -> None:
        self.post_payload = post_payload
        self.status = status
        self.calls: list[dict] = []

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def post(self, url: str, json: dict, headers: dict):  # noqa: A002 - match aiohttp API
        self.calls.append({"url": url, "json": json, "headers": headers})
        return _fake_response(self.status, self.post_payload)


def test_create_video_request_splits_start_and_end_into_separate_arrays() -> None:
    """Server enforces input_images max_length=1. End frame MUST go into input_images_end."""
    api = HiggsfieldAPI(auth_header="Key a:b", dop_model="dop-preview")
    session = _FakeSession(post_payload={"id": "req-123", "status": "queued"})

    with patch.object(hfmod.aiohttp, "ClientSession", return_value=session):
        result = asyncio.run(
            api.create_video_request(
                start_image_url="https://cdn/earth.jpg",
                end_image_url="https://cdn/face.jpg",
                prompt="cinematic",
                motion_id="46fa79e3-efce-41e8-95bc-1dc5a1a30795",
                motion_strength=0.8,
                duration_seconds=5,
            )
        )

    assert result.request_id == "req-123"
    call = session.calls[0]
    assert call["url"].endswith("/v1/image2video/dop")
    params = call["json"]["params"]
    assert params["model"] == "dop-preview"
    assert params["duration"] == 5
    assert params["input_images"] == [
        {"type": "image_url", "image_url": "https://cdn/earth.jpg"},
    ]
    assert params["input_images_end"] == [
        {"type": "image_url", "image_url": "https://cdn/face.jpg"},
    ]
    assert params["motions"] == [
        {"id": "46fa79e3-efce-41e8-95bc-1dc5a1a30795", "strength": 0.8},
    ]


def test_create_video_request_omits_end_when_not_provided() -> None:
    api = HiggsfieldAPI(auth_header="Key a:b", dop_model="dop-preview")
    session = _FakeSession(post_payload={"id": "x", "status": "queued"})

    with patch.object(hfmod.aiohttp, "ClientSession", return_value=session):
        asyncio.run(
            api.create_video_request(
                start_image_url="https://cdn/single.jpg",
                end_image_url=None,
                prompt="p",
                motion_id="46fa79e3-efce-41e8-95bc-1dc5a1a30795",
            )
        )

    params = session.calls[0]["json"]["params"]
    assert len(params["input_images"]) == 1
    assert "input_images_end" not in params


def test_create_video_request_clamps_strength_and_duration() -> None:
    api = HiggsfieldAPI(auth_header="Key a:b", dop_model="dop-turbo")
    session = _FakeSession(post_payload={"id": "x", "status": "queued"})

    with patch.object(hfmod.aiohttp, "ClientSession", return_value=session):
        asyncio.run(
            api.create_video_request(
                start_image_url="https://cdn/a",
                end_image_url=None,
                prompt="p",
                motion_id="11111111-1111-1111-1111-111111111111",
                motion_strength=5.0,  # over 1.0
                duration_seconds=99,  # over 15
            )
        )

    params = session.calls[0]["json"]["params"]
    assert params["motions"][0]["strength"] == 1.0
    assert params["duration"] == 15
    assert len(params["input_images"]) == 1
    assert "input_images_end" not in params


def test_create_soul_image_request_uses_params_wrapper() -> None:
    api = HiggsfieldAPI(auth_header="Key a:b")
    session = _FakeSession(post_payload={"id": "soul-1", "status": "queued"})

    with patch.object(hfmod.aiohttp, "ClientSession", return_value=session):
        asyncio.run(
            api.create_soul_image_request(
                prompt="earth from space",
                width_and_height="2048x1152",
                quality="1080p",
                batch_size=1,
            )
        )

    call = session.calls[0]
    assert call["url"].endswith("/v1/text2image/soul")
    params = call["json"]["params"]
    assert params["prompt"] == "earth from space"
    assert params["width_and_height"] == "2048x1152"
    assert params["quality"] == "1080p"
    assert params["batch_size"] == 1


def test_create_seedance_video_request_builds_expected_payload() -> None:
    api = HiggsfieldAPI(auth_header="Key a:b")
    session = _FakeSession(post_payload={"id": "sd-1", "status": "queued"})

    with patch.object(hfmod.aiohttp, "ClientSession", return_value=session):
        asyncio.run(
            api.create_seedance_video_request(
                input_image_url="https://cdn/face.jpg",
                prompt="run through rain",
                model="seedance_lite",
                duration_seconds=5,
                resolution="720",
                aspect_ratio="16:9",
                motions=[
                    {"id": "dc8d7d9c-ae0c-45fc-b780-7d470b171b45", "strength": 0.85},
                ],
                enhance_prompt=True,
            )
        )

    call = session.calls[0]
    assert call["url"].endswith("/v1/image2video/seedance")
    params = call["json"]["params"]
    assert params["model"] == "seedance_lite"
    assert params["duration"] == 5
    assert params["resolution"] == "720"
    assert params["aspect_ratio"] == "16:9"
    # NB: input_image is a SINGLE object, not an array (unlike DoP).
    assert params["input_image"] == {
        "type": "image_url",
        "image_url": "https://cdn/face.jpg",
    }
    assert params["motions"] == [
        {"id": "dc8d7d9c-ae0c-45fc-b780-7d470b171b45", "strength": 0.85},
    ]
    assert params["enhance_prompt"] is True
    # No start/end-frame shenanigans here — Seedance takes a single reference.
    assert "input_images" not in params
    assert "input_images_end" not in params


def test_create_seedance_video_request_rejects_invalid_duration() -> None:
    api = HiggsfieldAPI(auth_header="Key a:b")
    session = _FakeSession(post_payload={})

    with patch.object(hfmod.aiohttp, "ClientSession", return_value=session):
        with pytest.raises(HiggsfieldAPIError):
            asyncio.run(
                api.create_seedance_video_request(
                    input_image_url="https://cdn/x.jpg",
                    prompt="p",
                    duration_seconds=2,  # below allowed minimum of 3
                )
            )
    # Ensure no HTTP call was issued because validation happened client-side.
    assert session.calls == []


def test_seedance_allowed_durations_matches_server_literal() -> None:
    # Server FastAPI literal: 3, 4, 5, 6, 7, 8, 9, 10, 11 or 12.
    assert SEEDANCE_ALLOWED_DURATIONS == (3, 4, 5, 6, 7, 8, 9, 10, 11, 12)


def test_create_kling_video_request_payload_shape() -> None:
    api = HiggsfieldAPI(auth_header="Key a:b")
    session = _FakeSession(post_payload={"id": "klg-1", "status": "queued"})

    with patch.object(hfmod.aiohttp, "ClientSession", return_value=session):
        asyncio.run(
            api.create_kling_video_request(
                input_image_url="https://cdn/face.jpg",
                input_image_end_url="https://cdn/end.jpg",
                prompt="cinematic",
                model="kling-v2-1-master",
                duration_seconds=10,
                motions=[{"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "strength": 0.9}],
                negative_prompt="blurry",
            )
        )

    call = session.calls[0]
    assert call["url"].endswith("/v1/image2video/kling")
    params = call["json"]["params"]
    assert params["model"] == "kling-v2-1-master"
    assert params["duration"] == 10
    assert params["input_image"]["image_url"] == "https://cdn/face.jpg"
    assert params["input_image_end"]["image_url"] == "https://cdn/end.jpg"
    assert params["motions"][0]["id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert params["negative_prompt"] == "blurry"


def test_create_kling_video_request_rejects_invalid_duration() -> None:
    api = HiggsfieldAPI(auth_header="Key a:b")
    session = _FakeSession(post_payload={})
    with patch.object(hfmod.aiohttp, "ClientSession", return_value=session):
        with pytest.raises(HiggsfieldAPIError):
            asyncio.run(
                api.create_kling_video_request(
                    input_image_url="u", prompt="p", duration_seconds=7,
                )
            )
    assert session.calls == []


def test_create_minimax_video_request_payload_shape() -> None:
    api = HiggsfieldAPI(auth_header="Key a:b")
    session = _FakeSession(post_payload={"id": "mm-1", "status": "queued"})

    with patch.object(hfmod.aiohttp, "ClientSession", return_value=session):
        asyncio.run(
            api.create_minimax_video_request(
                input_image_url="https://cdn/face.jpg",
                input_image_end_url="https://cdn/end.jpg",
                prompt="cinematic",
                duration_seconds=6,
                resolution="1080",
            )
        )

    call = session.calls[0]
    assert call["url"].endswith("/v1/image2video/minimax")
    params = call["json"]["params"]
    assert params["duration"] == 6
    assert params["resolution"] == "1080"
    assert params["input_image"]["image_url"] == "https://cdn/face.jpg"
    assert params["input_image_end"]["image_url"] == "https://cdn/end.jpg"


def test_create_minimax_video_request_rejects_invalid_duration() -> None:
    api = HiggsfieldAPI(auth_header="Key a:b")
    session = _FakeSession(post_payload={})
    with patch.object(hfmod.aiohttp, "ClientSession", return_value=session):
        with pytest.raises(HiggsfieldAPIError):
            asyncio.run(
                api.create_minimax_video_request(
                    input_image_url="u", prompt="p", duration_seconds=3,
                )
            )
    assert session.calls == []


def test_create_seedance_video_request_clamps_motion_strength() -> None:
    api = HiggsfieldAPI(auth_header="Key a:b")
    session = _FakeSession(post_payload={"id": "sd-2", "status": "queued"})

    with patch.object(hfmod.aiohttp, "ClientSession", return_value=session):
        asyncio.run(
            api.create_seedance_video_request(
                input_image_url="https://cdn/x.jpg",
                prompt="p",
                motions=[{"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "strength": 9.0}],
            )
        )
    params = session.calls[0]["json"]["params"]
    assert params["motions"][0]["strength"] == 1.0


def test_create_video_request_raises_on_http_error() -> None:
    api = HiggsfieldAPI(auth_header="Key a:b", dop_model="dop-preview")
    session = _FakeSession(
        post_payload={"detail": "Not enough credits"},
        status=403,
    )
    with patch.object(hfmod.aiohttp, "ClientSession", return_value=session):
        with pytest.raises(HiggsfieldAPIError) as excinfo:
            asyncio.run(
                api.create_video_request(
                    start_image_url="u", end_image_url=None,
                    prompt="p", motion_id="22222222-2222-2222-2222-222222222222",
                )
            )
    assert "Not enough credits" in str(excinfo.value)
