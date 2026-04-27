"""One-off smoke: create DoP job with two input images -> poll once.

Run: python scripts/smoke_hf.py
"""
from __future__ import annotations

import asyncio
import os
import sys

MINI_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010101000100010000ffdb004300010101010101010101010101"
    "01010101010101010101010101010101010101010101010101010101010101010101010101"
    "010101010101010101010101010101010101010101010101ffc0000b080001000101011100"
    "ffc40014000100000000000000000000000000000008ffc4001410010000000000000000"
    "00000000000000ffda0008010100003f00d2cf20ffd9"
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from src.config import load_settings
    from src.higgsfield_api import HiggsfieldAPI

    settings = load_settings()
    api = HiggsfieldAPI(
        auth_header=settings.hf_auth_header,
        dop_model=settings.hf_dop_model,  # type: ignore[arg-type]
        request_timeout_seconds=settings.hf_http_timeout_seconds,
        upload_timeout_seconds=settings.hf_upload_timeout_seconds,
    )

    print("1) upload single frame...")
    url = await api.upload_image_bytes(MINI_JPEG, "image/jpeg")
    print("   public_url:", url[:80], "...")

    print(f"2) create DoP (model={settings.hf_dop_model}, motion={settings.hf_motion_name})...")
    cr = await api.create_video_request(
        start_image_url=url,
        end_image_url=None,
        prompt=settings.hf_main_prompt,
        motion_id=settings.hf_motion_id,
        motion_strength=settings.hf_motion_strength,
        duration_seconds=5,
    )
    print("   request_id:", cr.request_id, "status:", cr.status)

    print("3) status once...")
    st = await api.get_status(cr.request_id)
    print("   status:", st.status)
    print("   payload keys:", list(st.payload.keys())[:20])
    print("   video_url:", st.video_url)


if __name__ == "__main__":
    asyncio.run(main())
