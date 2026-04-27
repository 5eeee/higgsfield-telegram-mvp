"""End-to-end smoke: Earth Zoom In tuned to match the Higgsfield reference.

Generates a synthetic selfie, picks Earth from cache (or generates via Soul
if cache empty), fires DoP dual-frame render, saves first/mid/last frames.
"""
from __future__ import annotations

import asyncio
import io
import sys
import time
from pathlib import Path

import aiohttp
import imageio.v3 as iio
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

from src.bot import _prepare_image_portrait  # noqa: E402
from src.config import load_settings  # noqa: E402
from src.earth_cache import get_or_generate_earth_url  # noqa: E402
from src.earth_zoom import (  # noqa: E402
    DURATION_SECONDS,
    EARTH_ZOOM_DOP_ENHANCE_PROMPT,
    EARTH_ZOOM_IN_DOP_PROMPT,
    EARTH_ZOOM_OUT_MOTION_ID,
    EARTH_ZOOM_OUT_MOTION_STRENGTH,
)
from src.higgsfield_api import FINAL_STATUSES, HiggsfieldAPI  # noqa: E402


def _synthetic_face(path: Path) -> None:
    """Synthetic 'person-in-context' portrait: room, body, face.

    The Higgsfield reference (28TKrUxP9Bk) lands on a real photo of a person
    in their apartment — not a headshot. We reproduce the layout so DoP has
    something non-trivial to interpolate toward (walls, table, body, face).
    """
    img = Image.new("RGB", (1152, 1536), (220, 215, 205))
    d = ImageDraw.Draw(img)
    # Floor (wood tones)
    d.rectangle((0, 1050, 1152, 1536), fill=(170, 135, 95))
    # Rear wall darker band
    d.rectangle((0, 600, 1152, 1050), fill=(200, 195, 185))
    # Window (bright rectangle)
    d.rectangle((700, 350, 1100, 800), fill=(230, 235, 250))
    d.rectangle((700, 350, 1100, 800), outline=(120, 120, 120), width=6)
    d.line((900, 350, 900, 800), fill=(120, 120, 120), width=6)
    d.line((700, 575, 1100, 575), fill=(120, 120, 120), width=6)
    # Table
    d.rectangle((120, 1050, 800, 1150), fill=(235, 230, 225))
    d.rectangle((140, 1150, 180, 1400), fill=(170, 140, 110))
    d.rectangle((700, 1150, 740, 1400), fill=(170, 140, 110))
    # Body (dark jacket)
    d.rectangle((380, 780, 720, 1120), fill=(35, 35, 40))
    # Head + face
    d.ellipse((450, 560, 650, 810), fill=(225, 205, 185))
    # Cap
    d.ellipse((440, 540, 660, 640), fill=(245, 245, 245))
    d.arc((440, 540, 660, 680), start=0, end=180, fill=(245, 245, 245), width=40)
    # Eyes + mouth
    d.ellipse((488, 675, 520, 705), fill=(40, 40, 40))
    d.ellipse((580, 675, 612, 705), fill=(40, 40, 40))
    d.arc((500, 740, 600, 790), start=0, end=180, fill=(60, 30, 30), width=4)
    img.save(path, quality=94)


async def main() -> None:
    settings = load_settings()
    outdir = REPO_ROOT / "smoke_out"
    outdir.mkdir(exist_ok=True)
    face_path = outdir / "face_portrait.jpg"
    _synthetic_face(face_path)

    api = HiggsfieldAPI(
        auth_header=settings.hf_auth_header,
        request_timeout_seconds=settings.hf_http_timeout_seconds,
        upload_timeout_seconds=settings.hf_upload_timeout_seconds,
    )

    print("[1/4] Uploading face (3:4 portrait)...")
    face_bytes, _ = _prepare_image_portrait(face_path.read_bytes())
    face_url = await api.upload_image_bytes(face_bytes, "image/jpeg")
    print(f"    face: {face_url[:80]}")

    print("[2/4] Picking Earth from cache (or generating one)...")
    earth_url = await get_or_generate_earth_url(
        hf_api=api,
        poll_interval_seconds=settings.hf_poll_interval_seconds,
        max_wait_seconds=settings.hf_max_wait_seconds,
    )
    print(f"    earth: {earth_url[:80]}")

    print(f"[3/4] DoP dual-frame render (duration={DURATION_SECONDS}s, 3:4)...")
    t0 = time.monotonic()
    create = await api.create_video_request(
        start_image_url=earth_url,
        end_image_url=face_url,
        prompt=EARTH_ZOOM_IN_DOP_PROMPT,
        motion_id=EARTH_ZOOM_OUT_MOTION_ID,
        motion_strength=EARTH_ZOOM_OUT_MOTION_STRENGTH,
        duration_seconds=DURATION_SECONDS,
        enhance_prompt=EARTH_ZOOM_DOP_ENHANCE_PROMPT,
    )
    print(f"    request: {create.request_id}")
    last = None
    while True:
        r = await api.get_status(create.request_id)
        elapsed = int(time.monotonic() - t0)
        if r.status != last:
            print(f"    [{elapsed:3}s] {last} -> {r.status}")
            last = r.status
        if r.status in FINAL_STATUSES:
            break
        if elapsed > settings.hf_max_wait_seconds:
            raise SystemExit("TIMEOUT")
        await asyncio.sleep(settings.hf_poll_interval_seconds)
    if r.status != "completed" or not r.video_url:
        raise SystemExit(f"FAILED: {r.payload!r}")

    print(f"[4/4] Download + inspect frames (render={elapsed}s)...")
    async with aiohttp.ClientSession() as s:
        async with s.get(r.video_url) as rr:
            video_bytes = await rr.read()
    video_path = outdir / "earth_zoom_in_8s.mp4"
    video_path.write_bytes(video_bytes)
    frames = list(iio.imiter(video_path))
    meta = iio.immeta(video_path, exclude_applied=False)
    print(f"    meta: duration={meta.get('duration')}s size={meta.get('size')} frames={len(frames)}")
    for label, idx in [("first", 0), ("q1", len(frames)//4),
                       ("mid", len(frames)//2), ("q3", 3*len(frames)//4),
                       ("last", len(frames)-1)]:
        Image.fromarray(frames[idx]).save(outdir / f"ezin_v2_{label}.jpg", quality=92)
    print(f"    ✅ SMOKE PASSED in {elapsed}s — saved {video_path}")


if __name__ == "__main__":
    asyncio.run(main())
