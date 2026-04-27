"""Download the Higgsfield reference and dump 7 keyframes for side-by-side."""
import asyncio, sys, io
from pathlib import Path
import aiohttp
import imageio.v3 as iio
from PIL import Image

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

REF_URL = "https://d8j0ntlcm91z4.cloudfront.net/user_3CGdQRpXeEOT3tlk18GMgoqT0Co/hf_20260414_145814_3513f7a6-ec62-4afd-8bb4-d5138bdd47e3.mp4"

async def main() -> None:
    out = Path("smoke_out"); out.mkdir(exist_ok=True)
    dst = out / "ref_hf.mp4"
    async with aiohttp.ClientSession() as s:
        async with s.get(REF_URL) as r:
            dst.write_bytes(await r.read())
    meta = iio.immeta(dst, exclude_applied=False)
    frames = list(iio.imiter(dst))
    print(f"ref: duration={meta.get('duration')}s size={meta.get('size')} fps={meta.get('fps')} frames={len(frames)}")
    pts = [0, len(frames)//6, len(frames)//3, len(frames)//2,
           2*len(frames)//3, 5*len(frames)//6, len(frames)-1]
    for i, idx in enumerate(pts):
        Image.fromarray(frames[idx]).save(out / f"ref_{i}.jpg", quality=92)
    print("Saved 7 ref keyframes.")

asyncio.run(main())
