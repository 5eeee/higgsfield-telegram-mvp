"""Compare a past Higgsfield render against the reference share."""
import asyncio
import sys
import io
from pathlib import Path

import aiohttp
import imageio.v3 as iio
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

from dotenv import load_dotenv
load_dotenv()

from src.config import load_settings
from src.higgsfield_api import HiggsfieldAPI


async def main() -> None:
    request_id = "f131f5bd-6a9c-46ab-9710-22e86a0d0c6d"
    settings = load_settings()
    api = HiggsfieldAPI(
        auth_header=settings.hf_auth_header,
        request_timeout_seconds=settings.hf_http_timeout_seconds,
        upload_timeout_seconds=settings.hf_upload_timeout_seconds,
    )
    status = await api.get_status(request_id)
    print(f"status: {status.status}")
    print(f"video: {status.video_url}")
    if not status.video_url:
        return

    outdir = Path("smoke_out")
    outdir.mkdir(exist_ok=True)
    video_path = outdir / "user_last_render.mp4"

    async with aiohttp.ClientSession() as s:
        async with s.get(status.video_url) as r:
            video_path.write_bytes(await r.read())

    meta = iio.immeta(video_path, exclude_applied=False)
    frames = list(iio.imiter(video_path))
    print(f"meta: duration={meta.get('duration')}s size={meta.get('size')} frames={len(frames)}")

    # Extract 7 evenly spaced frames to see the full trajectory.
    for i, idx in enumerate([0, len(frames)//6, len(frames)//3, len(frames)//2,
                              2*len(frames)//3, 5*len(frames)//6, len(frames)-1]):
        Image.fromarray(frames[idx]).save(outdir / f"user_f{i}.jpg", quality=92)
    print("saved 7 frames to smoke_out/user_f*.jpg")


asyncio.run(main())
