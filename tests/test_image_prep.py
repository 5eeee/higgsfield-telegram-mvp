"""Ensure input images are cropped to 3:4 portrait for Earth Zoom In.

We no longer force a fixed 1080x1440 downscale — the prep function keeps
the original resolution (bounded by MIN/MAX) so DoP can render at HD.
"""
from __future__ import annotations

import io

from PIL import Image

from src.bot import MAX_SIDE_PX, MIN_SIDE_PX, _prepare_image_portrait


def _make_image(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height), (120, 90, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _assert_portrait_bounded(out_bytes: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(out_bytes)) as im:
        w, h = im.size
    # Always 3:4 (±1 px rounding).
    assert abs((w / h) - (3 / 4)) < 0.01, (w, h)
    # Width inside [MIN, MAX].
    assert MIN_SIDE_PX <= w <= MAX_SIDE_PX, (w, h)
    return w, h


def test_crop_landscape_to_portrait() -> None:
    raw = _make_image(1920, 1080)
    out_bytes, mime = _prepare_image_portrait(raw)
    assert mime == "image/jpeg"
    _assert_portrait_bounded(out_bytes)


def test_square_to_portrait() -> None:
    raw = _make_image(1024, 1024)
    out_bytes, _ = _prepare_image_portrait(raw)
    _assert_portrait_bounded(out_bytes)


def test_tall_portrait_preserved() -> None:
    raw = _make_image(800, 1600)
    out_bytes, _ = _prepare_image_portrait(raw)
    _assert_portrait_bounded(out_bytes)


def test_extreme_ultrawide_centered() -> None:
    raw = _make_image(4000, 1000)
    out_bytes, _ = _prepare_image_portrait(raw)
    _assert_portrait_bounded(out_bytes)


def test_huge_input_downscaled_not_upscaled() -> None:
    """A 6000-wide photo must be downscaled, not blown up further."""
    raw = _make_image(6000, 8000)
    out_bytes, _ = _prepare_image_portrait(raw)
    w, _ = _assert_portrait_bounded(out_bytes)
    assert w <= MAX_SIDE_PX
