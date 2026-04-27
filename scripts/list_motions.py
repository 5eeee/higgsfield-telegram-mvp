"""List Higgsfield DoP motion presets (id, name, description).

Run: python scripts/list_motions.py [filter_substring]
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiohttp
from dotenv import load_dotenv

load_dotenv()

from src.config import load_settings
from src.higgsfield_api import HIGGSFIELD_BASE_URL


async def main() -> None:
    needle = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    settings = load_settings()
    headers = {"Authorization": settings.hf_auth_header, "Accept": "application/json"}
    url = f"{HIGGSFIELD_BASE_URL}/v1/motions"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            motions = await resp.json()

    print(f"Total motions: {len(motions)}")
    for m in motions:
        name = m.get("name", "")
        if needle and needle not in name.lower():
            continue
        print(f"- {m.get('id')} | {name} | {m.get('description', '')[:80]}")

    # dump full catalog to json for reference
    out = Path(__file__).resolve().parent.parent / "assets" / "motions_catalog.json"
    out.write_text(json.dumps(motions, indent=2, ensure_ascii=False))
    print(f"\nSaved full catalog -> {out}")


if __name__ == "__main__":
    asyncio.run(main())
