from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Literal

import aiohttp

HIGGSFIELD_BASE_URL = "https://platform.higgsfield.ai"

# Canonical SDK-compatible endpoints (verified against higgsfield-js source +
# live FastAPI schema probing 2026-04-20).
DOP_VIDEO_ENDPOINT = f"{HIGGSFIELD_BASE_URL}/v1/image2video/dop"
SOUL_TEXT2IMAGE_ENDPOINT = f"{HIGGSFIELD_BASE_URL}/v1/text2image/soul"
SEEDANCE_VIDEO_ENDPOINT = f"{HIGGSFIELD_BASE_URL}/v1/image2video/seedance"
KLING_VIDEO_ENDPOINT = f"{HIGGSFIELD_BASE_URL}/v1/image2video/kling"
MINIMAX_VIDEO_ENDPOINT = f"{HIGGSFIELD_BASE_URL}/v1/image2video/minimax"

FINAL_STATUSES = {"completed", "failed", "nsfw", "canceled", "cancelled"}

DopModel = Literal["dop-lite", "dop-preview", "dop-turbo"]
SoulQuality = Literal["720p", "1080p"]
SeedanceModel = Literal["seedance_lite", "seedance_pro"]
SeedanceResolution = Literal["480", "720", "1080"]
SeedanceAspectRatio = Literal["auto", "1:1", "4:3", "3:4", "16:9", "9:16", "21:9"]
SEEDANCE_ALLOWED_DURATIONS = (3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
KlingModel = Literal["kling-v2-1", "kling-v2-1-master"]
KLING_ALLOWED_DURATIONS = (5, 10)
MinimaxResolution = Literal["512", "768", "1080"]
MINIMAX_ALLOWED_DURATIONS = (6, 10)

Engine = Literal["dop", "seedance", "kling", "minimax"]


def _format_http_error(status: int, payload: dict[str, Any]) -> str:
    detail = payload.get("detail")
    if isinstance(detail, str) and detail.strip():
        return f"HTTP {status}: {detail.strip()}"
    if isinstance(detail, list):
        return f"HTTP {status}: {detail!r}"
    raw_text = payload.get("raw_text")
    if isinstance(raw_text, str) and raw_text.strip():
        return f"HTTP {status}: {raw_text.strip()[:400]}"
    return f"HTTP {status} {payload!r}"


class HiggsfieldAPIError(Exception):
    pass


def _clean_motions(motions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize a motions list: trim UUIDs, clamp strength to [0.0, 1.0]."""
    out: list[dict[str, Any]] = []
    for motion in motions:
        motion_id = motion.get("id")
        if not motion_id:
            continue
        strength = max(0.0, min(1.0, float(motion.get("strength", 0.8))))
        out.append({"id": str(motion_id).strip(), "strength": strength})
    return out


@dataclass(slots=True)
class HiggsfieldRequestResult:
    status: str
    request_id: str
    payload: dict[str, Any]

    @property
    def video_url(self) -> str | None:
        return _extract_video_url(self.payload)

    @property
    def image_url(self) -> str | None:
        return _extract_image_url(self.payload)


def _extract_video_url(payload: dict[str, Any]) -> str | None:
    """Extract the first video URL from any shape of completed DoP payload."""
    video = payload.get("video")
    if isinstance(video, dict):
        raw_url = video.get("url")
        if isinstance(raw_url, str) and raw_url.strip():
            return raw_url.strip()

    videos = payload.get("videos")
    if isinstance(videos, list) and videos:
        first = videos[0]
        if isinstance(first, dict):
            raw_url = first.get("url")
            if isinstance(raw_url, str) and raw_url.strip():
                return raw_url.strip()
        if isinstance(first, str) and first.strip():
            return first.strip()

    results = payload.get("results")
    if isinstance(results, list) and results:
        for item in results:
            if isinstance(item, dict):
                nested = _extract_video_url(item)
                if nested:
                    return nested

    for key in ("video_url", "output_url", "result_url", "url"):
        raw = payload.get(key)
        if isinstance(raw, str) and raw.strip().startswith("http"):
            return raw.strip()

    result = payload.get("result")
    if isinstance(result, dict):
        nested = _extract_video_url(result)
        if nested:
            return nested
    return None


def _extract_image_url(payload: dict[str, Any]) -> str | None:
    """Extract the first image URL from any shape of completed Soul payload."""
    for key in ("image", "output_image"):
        item = payload.get(key)
        if isinstance(item, dict):
            raw = item.get("url")
            if isinstance(raw, str) and raw.strip():
                return raw.strip()

    for key in ("images", "outputs", "results"):
        items = payload.get(key)
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict):
                raw = first.get("url")
                if isinstance(raw, str) and raw.strip():
                    return raw.strip()
            if isinstance(first, str) and first.strip().startswith("http"):
                return first.strip()

    for key in ("image_url", "output_url", "url"):
        raw = payload.get(key)
        if isinstance(raw, str) and raw.strip().startswith("http"):
            return raw.strip()

    result = payload.get("result")
    if isinstance(result, dict):
        nested = _extract_image_url(result)
        if nested:
            return nested
    return None


class HiggsfieldAPI:
    def __init__(
        self,
        auth_header: str,
        dop_model: DopModel = "dop-lite",
        request_timeout_seconds: int = 60,
        upload_timeout_seconds: int = 120,
    ) -> None:
        self.auth_header = auth_header
        self.dop_model: DopModel = dop_model
        self.request_timeout_seconds = max(5, int(request_timeout_seconds))
        self.upload_timeout_seconds = max(10, int(upload_timeout_seconds))

    @staticmethod
    def _extract_request_id(payload: dict[str, Any]) -> str:
        for key in ("request_id", "id"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        raise HiggsfieldAPIError(f"Missing request_id in response: {payload}")

    @staticmethod
    async def _read_json_or_text(response: aiohttp.ClientResponse) -> dict[str, Any]:
        try:
            payload = await response.json(content_type=None)
            if isinstance(payload, dict):
                return payload
            return {"raw_payload": payload}
        except Exception:  # noqa: BLE001
            text = await response.text()
            return {"raw_text": text}

    def _json_headers(self) -> dict[str, str]:
        return {
            "Authorization": self.auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def upload_image_bytes(self, data: bytes, content_type: str) -> str:
        """Upload image bytes to Higgsfield storage and return public image URL."""
        if not data:
            raise HiggsfieldAPIError("Empty image bytes for upload")

        upload_endpoint = f"{HIGGSFIELD_BASE_URL}/files/generate-upload-url"
        timeout = aiohttp.ClientTimeout(total=self.upload_timeout_seconds)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                upload_endpoint,
                json={"content_type": content_type},
                headers=self._json_headers(),
            ) as response:
                response_payload = await self._read_json_or_text(response)
                if response.status >= 400:
                    raise HiggsfieldAPIError(
                        f"Failed to get upload URL: {_format_http_error(response.status, response_payload)}",
                    )

            public_url = response_payload.get("public_url")
            presigned_put = response_payload.get("upload_url")
            if not isinstance(public_url, str) or not public_url.strip():
                raise HiggsfieldAPIError(f"Missing public_url: {response_payload}")
            if not isinstance(presigned_put, str) or not presigned_put.strip():
                raise HiggsfieldAPIError(f"Missing upload_url: {response_payload}")

            async with session.put(
                presigned_put,
                data=data,
                headers={"Content-Type": content_type},
            ) as put_response:
                put_body = await put_response.text()
                if put_response.status >= 400:
                    raise HiggsfieldAPIError(
                        f"Failed to upload bytes: HTTP {put_response.status} {put_body[:500]}",
                    )

        return public_url.strip()

    async def create_video_request(
        self,
        start_image_url: str,
        end_image_url: str | None,
        prompt: str,
        motion_id: str,
        motion_strength: float = 0.75,
        duration_seconds: int = 5,
        enhance_prompt: bool = False,
        seed: int | None = None,
    ) -> HiggsfieldRequestResult:
        """Create DoP image-to-video request via canonical /v1/image2video/dop.

        When `end_image_url` is provided AND the preset supports `start_end_frame`
        (e.g. "Earth Zoom Out" preset), the camera interpolates from start_frame
        to end_frame — exactly how Higgsfield web UI renders "Earth Zoom In":

            start_frame = Earth from space   end_frame = person's face
            => camera dives from space and lands on the face (zoom IN)

        The server enforces `input_images` max_length=1 and expects the second
        frame in the separate `input_images_end` array (verified by probing the
        FastAPI pydantic schema on 2026-04-20 — see docs/HIGGSFIELD_API_NOTES.md).
        """
        strength = float(motion_strength)
        strength = max(0.0, min(1.0, strength))

        params: dict[str, Any] = {
            "model": self.dop_model,
            "prompt": prompt,
            "input_images": [{"type": "image_url", "image_url": start_image_url}],
            "duration": max(1, min(int(duration_seconds), 15)),
            "motions": [{"id": motion_id.strip(), "strength": strength}],
            "enhance_prompt": bool(enhance_prompt),
        }
        if end_image_url:
            params["input_images_end"] = [
                {"type": "image_url", "image_url": end_image_url},
            ]
        if seed is not None:
            params["seed"] = int(seed)

        timeout = aiohttp.ClientTimeout(total=self.request_timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                DOP_VIDEO_ENDPOINT,
                json={"params": params},
                headers=self._json_headers(),
            ) as response:
                response_payload = await self._read_json_or_text(response)
                if response.status >= 400:
                    raise HiggsfieldAPIError(
                        f"Failed to create DoP request: {_format_http_error(response.status, response_payload)}",
                    )

        request_id = self._extract_request_id(response_payload)
        status = str(response_payload.get("status", "queued")).lower()
        return HiggsfieldRequestResult(
            status=status, request_id=request_id, payload=response_payload
        )

    async def create_seedance_video_request(
        self,
        input_image_url: str,
        prompt: str,
        model: SeedanceModel = "seedance_lite",
        duration_seconds: int = 5,
        resolution: SeedanceResolution = "720",
        aspect_ratio: SeedanceAspectRatio = "16:9",
        motions: list[dict[str, Any]] | None = None,
        enhance_prompt: bool = True,
        seed: int | None = None,
    ) -> HiggsfieldRequestResult:
        """Create Seedance 2.0 image-to-video request via /v1/image2video/seedance.

        This is the "Cinematic VFX" family: ByteDance Seedance models that keep
        the face identity from ``input_image`` while fully animating the body
        and scene according to ``prompt`` (+ optional motion preset).

        * ``model``:
            - ``seedance_lite`` — ~25–50 s render, great for real-time flows.
            - ``seedance_pro`` — higher fidelity, ~1–2 min.
        * ``duration`` must be one of :data:`SEEDANCE_ALLOWED_DURATIONS` (3–12).
        * ``resolution``: ``480`` | ``720`` | ``1080``. Lower = faster.
        * ``motions``: same preset UUIDs as DoP (catalog at /v1/motions).

        Schema verified by FastAPI pydantic error probing 2026-04-20
        (see docs/HIGGSFIELD_API_NOTES.md).
        """
        if duration_seconds not in SEEDANCE_ALLOWED_DURATIONS:
            raise HiggsfieldAPIError(
                f"Seedance duration must be one of {SEEDANCE_ALLOWED_DURATIONS}, "
                f"got {duration_seconds}",
            )

        params: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "input_image": {"type": "image_url", "image_url": input_image_url},
            "duration": int(duration_seconds),
            "resolution": str(resolution),
            "aspect_ratio": str(aspect_ratio),
            "enhance_prompt": bool(enhance_prompt),
        }
        if motions:
            params["motions"] = [
                {
                    "id": str(m["id"]).strip(),
                    "strength": max(0.0, min(1.0, float(m.get("strength", 0.8)))),
                }
                for m in motions
                if m.get("id")
            ]
        if seed is not None:
            params["seed"] = int(seed)

        timeout = aiohttp.ClientTimeout(total=self.request_timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                SEEDANCE_VIDEO_ENDPOINT,
                json={"params": params},
                headers=self._json_headers(),
            ) as response:
                response_payload = await self._read_json_or_text(response)
                if response.status >= 400:
                    raise HiggsfieldAPIError(
                        f"Failed to create Seedance request: {_format_http_error(response.status, response_payload)}",
                    )

        request_id = self._extract_request_id(response_payload)
        status = str(response_payload.get("status", "queued")).lower()
        return HiggsfieldRequestResult(
            status=status, request_id=request_id, payload=response_payload
        )

    async def create_kling_video_request(
        self,
        input_image_url: str,
        prompt: str,
        model: KlingModel = "kling-v2-1",
        duration_seconds: int = 5,
        input_image_end_url: str | None = None,
        motions: list[dict[str, Any]] | None = None,
        negative_prompt: str | None = None,
        enhance_prompt: bool = True,
        seed: int | None = None,
    ) -> HiggsfieldRequestResult:
        """Create Kling v2.1 image-to-video request.

        * ``model``: ``kling-v2-1`` (balanced) | ``kling-v2-1-master`` (HQ).
        * ``duration_seconds``: 5 or 10 (server literal).
        * Supports ``input_image_end_url`` (start→end keyframe control) and
          ``motions`` from ``/v1/motions`` catalog (same UUIDs as DoP).
        """
        if duration_seconds not in KLING_ALLOWED_DURATIONS:
            raise HiggsfieldAPIError(
                f"Kling duration must be one of {KLING_ALLOWED_DURATIONS}, got {duration_seconds}",
            )

        params: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "input_image": {"type": "image_url", "image_url": input_image_url},
            "duration": int(duration_seconds),
            "enhance_prompt": bool(enhance_prompt),
        }
        if input_image_end_url:
            params["input_image_end"] = {
                "type": "image_url", "image_url": input_image_end_url,
            }
        if motions:
            params["motions"] = _clean_motions(motions)
        if negative_prompt:
            params["negative_prompt"] = str(negative_prompt)
        if seed is not None:
            params["seed"] = int(seed)

        return await self._post_request(KLING_VIDEO_ENDPOINT, params, "Kling")

    async def create_minimax_video_request(
        self,
        input_image_url: str,
        prompt: str,
        duration_seconds: int = 6,
        resolution: MinimaxResolution = "768",
        input_image_end_url: str | None = None,
        motions: list[dict[str, Any]] | None = None,
        enhance_prompt: bool = True,
        seed: int | None = None,
    ) -> HiggsfieldRequestResult:
        """Create Minimax (Hailuo) image-to-video request.

        * ``duration_seconds``: 6 or 10.
        * ``resolution``: ``512`` | ``768`` | ``1080``.
        """
        if duration_seconds not in MINIMAX_ALLOWED_DURATIONS:
            raise HiggsfieldAPIError(
                f"Minimax duration must be one of {MINIMAX_ALLOWED_DURATIONS}, got {duration_seconds}",
            )

        params: dict[str, Any] = {
            "prompt": prompt,
            "input_image": {"type": "image_url", "image_url": input_image_url},
            "duration": int(duration_seconds),
            "resolution": str(resolution),
            "enhance_prompt": bool(enhance_prompt),
        }
        if input_image_end_url:
            params["input_image_end"] = {
                "type": "image_url", "image_url": input_image_end_url,
            }
        if motions:
            params["motions"] = _clean_motions(motions)
        if seed is not None:
            params["seed"] = int(seed)

        return await self._post_request(MINIMAX_VIDEO_ENDPOINT, params, "Minimax")

    async def _post_request(
        self, url: str, params: dict[str, Any], engine_label: str,
    ) -> HiggsfieldRequestResult:
        timeout = aiohttp.ClientTimeout(total=self.request_timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                url,
                json={"params": params},
                headers=self._json_headers(),
            ) as response:
                response_payload = await self._read_json_or_text(response)
                if response.status >= 400:
                    raise HiggsfieldAPIError(
                        f"Failed to create {engine_label} request: "
                        f"{_format_http_error(response.status, response_payload)}",
                    )
        request_id = self._extract_request_id(response_payload)
        status = str(response_payload.get("status", "queued")).lower()
        return HiggsfieldRequestResult(
            status=status, request_id=request_id, payload=response_payload,
        )

    async def create_soul_image_request(
        self,
        prompt: str,
        width_and_height: str = "2048x1152",
        quality: SoulQuality = "1080p",
        batch_size: int = 1,
        enhance_prompt: bool = True,
        seed: int | None = None,
    ) -> HiggsfieldRequestResult:
        """Create Soul text-to-image request to produce a background (e.g. Earth)."""
        params: dict[str, Any] = {
            "prompt": prompt,
            "width_and_height": width_and_height,
            "quality": quality,
            "batch_size": 1 if batch_size not in (1, 4) else batch_size,
            "enhance_prompt": bool(enhance_prompt),
        }
        if seed is not None:
            params["seed"] = int(seed)

        timeout = aiohttp.ClientTimeout(total=self.request_timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                SOUL_TEXT2IMAGE_ENDPOINT,
                json={"params": params},
                headers=self._json_headers(),
            ) as response:
                response_payload = await self._read_json_or_text(response)
                if response.status >= 400:
                    raise HiggsfieldAPIError(
                        f"Failed to create Soul request: {_format_http_error(response.status, response_payload)}",
                    )
        request_id = self._extract_request_id(response_payload)
        status = str(response_payload.get("status", "queued")).lower()
        return HiggsfieldRequestResult(
            status=status, request_id=request_id, payload=response_payload
        )

    async def get_status(self, request_id: str) -> HiggsfieldRequestResult:
        status_url = f"{HIGGSFIELD_BASE_URL}/requests/{request_id}/status"
        timeout = aiohttp.ClientTimeout(total=self.request_timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                status_url,
                headers={"Authorization": self.auth_header, "Accept": "application/json"},
            ) as response:
                response_payload = await self._read_json_or_text(response)
                if response.status >= 400:
                    raise HiggsfieldAPIError(
                        f"Failed to fetch status: {_format_http_error(response.status, response_payload)}",
                    )

        status = str(response_payload.get("status", "unknown")).lower()
        return HiggsfieldRequestResult(
            status=status, request_id=request_id, payload=response_payload
        )

    async def wait_for_completion(
        self,
        request_id: str,
        poll_interval_seconds: int,
        max_wait_seconds: int,
    ) -> HiggsfieldRequestResult:
        started_at = time.monotonic()
        while True:
            status_result = await self.get_status(request_id)
            if status_result.status in FINAL_STATUSES:
                return status_result
            if time.monotonic() - started_at > max_wait_seconds:
                raise HiggsfieldAPIError(
                    f"Generation timeout after {max_wait_seconds} seconds",
                )
            await asyncio.sleep(poll_interval_seconds)
