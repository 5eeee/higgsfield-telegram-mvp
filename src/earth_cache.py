"""Earth background provider for the flagship Earth Zoom In scenario.

Strategy (in priority order):

1. **Asset upload** — ``assets/earth_reference.jpg`` is a photorealistic
   Earth sourced from the Higgsfield reference video
   (https://higgsfield.ai/s/28TKrUxP9Bk). We upload it once per process
   and reuse the resulting bucket URL. Zero queue time, production-safe.

2. **Persistent cache** — ``earth_cache.json`` stores previously uploaded
   asset URLs and any Soul-generated ones. Self-heals: dead URLs get
   dropped and replaced on demand.

3. **Soul fallback** — if the asset is missing AND the cache is empty,
   the bot falls back to calling Soul (which may queue for minutes on
   Higgsfield's end — last resort).
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from pathlib import Path

import aiohttp

from src.earth_zoom import (
    EARTH_IMAGE_QUALITY,
    EARTH_IMAGE_WIDTH_AND_HEIGHT,
    EARTH_SOUL_PROMPT,
)
from src.higgsfield_api import FINAL_STATUSES, HiggsfieldAPI, HiggsfieldAPIError

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = _REPO_ROOT / "earth_cache.json"
ASSET_PATH = _REPO_ROOT / "assets" / "earth_reference.jpg"

# 14 days — Higgsfield CDN URLs persist but we refresh periodically.
_CACHE_TTL_SECONDS = 14 * 24 * 3600


def _load_cache() -> list[dict]:
    if not CACHE_PATH.exists():
        return []
    try:
        raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []
        now = time.time()
        return [
            item for item in raw
            if isinstance(item, dict)
            and isinstance(item.get("url"), str)
            and now - float(item.get("created_at", 0)) < _CACHE_TTL_SECONDS
        ]
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        logger.warning("Failed to load earth cache: %s", exc)
        return []


def _save_cache(entries: list[dict]) -> None:
    try:
        CACHE_PATH.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Failed to save earth cache: %s", exc)


async def _url_is_alive(url: str) -> bool:
    """HEAD-check a CDN URL. Returns True on 2xx, False otherwise."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(
                url, timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status < 400:
                    return True
                if r.status in {403, 405}:
                    async with session.get(
                        url, timeout=aiohttp.ClientTimeout(total=10),
                        headers={"Range": "bytes=0-0"},
                    ) as rr:
                        return rr.status < 400
                return False
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logger.warning("Earth URL probe failed (%s): %s", url[:80], exc)
        return False


async def _upload_asset_earth(hf_api: HiggsfieldAPI) -> str:
    """Upload ``assets/earth_reference.jpg`` into Higgsfield and return URL."""
    if not ASSET_PATH.exists():
        raise HiggsfieldAPIError(
            f"Missing Earth asset at {ASSET_PATH} — "
            f"copy assets/earth_reference.jpg into the repo.",
        )
    logger.info("Uploading Earth asset from %s...", ASSET_PATH.name)
    url = await hf_api.upload_image_bytes(ASSET_PATH.read_bytes(), "image/jpeg")
    logger.info("Asset Earth uploaded: %s", url[:80])
    return url


async def _generate_soul_earth(
    hf_api: HiggsfieldAPI,
    poll_interval_seconds: int,
    max_wait_seconds: int,
) -> str:
    """Call Soul → poll → download → re-upload to user's bucket."""
    soul = await hf_api.create_soul_image_request(
        prompt=EARTH_SOUL_PROMPT,
        width_and_height=EARTH_IMAGE_WIDTH_AND_HEIGHT,
        quality=EARTH_IMAGE_QUALITY,
        batch_size=1,
        enhance_prompt=True,
    )
    started = time.monotonic()
    while True:
        result = await hf_api.get_status(soul.request_id)
        if result.status in FINAL_STATUSES:
            break
        if time.monotonic() - started > max_wait_seconds:
            raise HiggsfieldAPIError(
                f"Soul Earth generation timeout after {max_wait_seconds}s"
            )
        await asyncio.sleep(poll_interval_seconds)

    if result.status != "completed" or not result.image_url:
        raise HiggsfieldAPIError(
            f"Soul Earth failed: status={result.status}, payload={result.payload!r}",
        )

    async with aiohttp.ClientSession() as session:
        async with session.get(result.image_url) as response:
            if response.status >= 400:
                raise HiggsfieldAPIError(
                    f"Failed to fetch Earth CDN image: HTTP {response.status}"
                )
            earth_bytes = await response.read()
    return await hf_api.upload_image_bytes(earth_bytes, "image/jpeg")


async def get_or_generate_earth_url(
    hf_api: HiggsfieldAPI,
    poll_interval_seconds: int,
    max_wait_seconds: int,
) -> str:
    """Return a ready-to-use Earth URL using 3-tier strategy (asset, cache, Soul)."""

    # Tier 1 + 2: try existing cache entries first (asset-derived or Soul-derived).
    cache = _load_cache()
    random.shuffle(cache)
    surviving: list[dict] = []
    chosen: str | None = None
    for entry in cache:
        url = str(entry.get("url", ""))
        if not url:
            continue
        if await _url_is_alive(url):
            surviving.append(entry)
            if chosen is None:
                chosen = url
        else:
            logger.info("Dropping dead Earth URL from cache: %s", url[:80])

    if chosen:
        _save_cache(surviving)
        return chosen

    # Tier 1 (fresh): upload the bundled asset if we have it.
    if ASSET_PATH.exists():
        try:
            url = await _upload_asset_earth(hf_api)
            surviving.append({"url": url, "created_at": time.time(), "source": "asset"})
            _save_cache(surviving)
            return url
        except HiggsfieldAPIError as exc:
            logger.error("Asset upload failed, trying Soul fallback: %s", exc)

    # Tier 3: Soul fallback (slow — may queue for minutes).
    logger.info("Earth cache empty + no asset — generating via Soul (slow)...")
    url = await _generate_soul_earth(
        hf_api=hf_api,
        poll_interval_seconds=poll_interval_seconds,
        max_wait_seconds=max_wait_seconds,
    )
    surviving.append({"url": url, "created_at": time.time(), "source": "soul"})
    _save_cache(surviving)
    return url


async def preload_earth_url(
    hf_api: HiggsfieldAPI,
    poll_interval_seconds: int,
    max_wait_seconds: int,
) -> str:
    """One-time warm-up for bot startup. Guarantees a cached Earth URL exists."""
    return await get_or_generate_earth_url(
        hf_api=hf_api,
        poll_interval_seconds=poll_interval_seconds,
        max_wait_seconds=max_wait_seconds,
    )
