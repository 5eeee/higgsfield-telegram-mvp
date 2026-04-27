"""Earth cache smoke: no Soul roundtrip when a fresh, live entry is cached."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import src.earth_cache as earth_cache_mod


@pytest.fixture
def tmp_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "earth_cache.json"
    monkeypatch.setattr(earth_cache_mod, "CACHE_PATH", path)
    # Pretend every URL is alive by default so we don't hit the network.
    async def _alive(url: str) -> bool:
        return True
    monkeypatch.setattr(earth_cache_mod, "_url_is_alive", _alive)
    return path


def test_cache_hit_skips_soul(tmp_cache: Path) -> None:
    tmp_cache.write_text(json.dumps([
        {"url": "https://cdn/earth-1.jpg", "created_at": time.time()},
    ]), encoding="utf-8")

    hf_api = AsyncMock()
    url = asyncio.run(earth_cache_mod.get_or_generate_earth_url(
        hf_api=hf_api, poll_interval_seconds=1, max_wait_seconds=30,
    ))
    assert url == "https://cdn/earth-1.jpg"
    hf_api.create_soul_image_request.assert_not_called()


def test_expired_entries_are_dropped(
    tmp_cache: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    very_old = time.time() - (30 * 24 * 3600)  # 30 days ago
    tmp_cache.write_text(json.dumps([
        {"url": "https://cdn/old.jpg", "created_at": very_old},
    ]), encoding="utf-8")

    async def stub_generate(*args: object, **kwargs: object) -> str:
        return "https://cdn/fresh-new.jpg"

    monkeypatch.setattr(earth_cache_mod, "_generate_soul_earth", stub_generate)
    # Pretend no bundled asset so code path falls through to Soul.
    monkeypatch.setattr(earth_cache_mod, "ASSET_PATH", tmp_cache.parent / "no-asset.jpg")

    hf_api = AsyncMock()
    url = asyncio.run(earth_cache_mod.get_or_generate_earth_url(
        hf_api=hf_api, poll_interval_seconds=1, max_wait_seconds=30,
    ))
    assert url == "https://cdn/fresh-new.jpg"
    saved = json.loads(tmp_cache.read_text(encoding="utf-8"))
    urls = [item["url"] for item in saved]
    assert "https://cdn/fresh-new.jpg" in urls


def test_pool_rotation_returns_various_entries(tmp_cache: Path) -> None:
    pool = [
        {"url": f"https://cdn/earth-{i}.jpg", "created_at": time.time()}
        for i in range(5)
    ]
    tmp_cache.write_text(json.dumps(pool), encoding="utf-8")

    hf_api = AsyncMock()
    seen: set[str] = set()
    # After the first call the cache is reordered, but all 5 entries remain.
    for _ in range(100):
        url = asyncio.run(earth_cache_mod.get_or_generate_earth_url(
            hf_api=hf_api, poll_interval_seconds=1, max_wait_seconds=30,
        ))
        seen.add(url)
    assert seen == {p["url"] for p in pool}


def test_dead_urls_trigger_regeneration(
    tmp_cache: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_cache.write_text(json.dumps([
        {"url": "https://cdn/dead.jpg", "created_at": time.time()},
    ]), encoding="utf-8")

    async def _alive(url: str) -> bool:
        return False  # every cached URL is dead

    async def stub_generate(*args: object, **kwargs: object) -> str:
        return "https://cdn/freshly-made.jpg"

    monkeypatch.setattr(earth_cache_mod, "_url_is_alive", _alive)
    monkeypatch.setattr(earth_cache_mod, "_generate_soul_earth", stub_generate)
    monkeypatch.setattr(earth_cache_mod, "ASSET_PATH", tmp_cache.parent / "no-asset.jpg")

    url = asyncio.run(earth_cache_mod.get_or_generate_earth_url(
        hf_api=AsyncMock(), poll_interval_seconds=1, max_wait_seconds=30,
    ))
    assert url == "https://cdn/freshly-made.jpg"
    saved = json.loads(tmp_cache.read_text(encoding="utf-8"))
    urls = [item["url"] for item in saved]
    assert "https://cdn/dead.jpg" not in urls
    assert "https://cdn/freshly-made.jpg" in urls
