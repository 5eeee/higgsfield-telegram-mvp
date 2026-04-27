"""Scrape Higgsfield share page for embedded __NEXT_DATA__ or __next_f payload."""
import asyncio
import json
import re
import sys

import aiohttp

URL = sys.argv[1] if len(sys.argv) > 1 else "https://higgsfield.ai/s/28TKrUxP9Bk"


async def run() -> None:
    async with aiohttp.ClientSession() as s:
        async with s.get(URL, headers={"User-Agent": "Mozilla/5.0"},
                         timeout=aiohttp.ClientTimeout(total=15)) as r:
            html = await r.text()
    print(f"HTML {len(html)} bytes from {URL}")

    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                  html, re.S)
    if m:
        print("__NEXT_DATA__ found")
        print(json.dumps(json.loads(m.group(1)), ensure_ascii=False, indent=2))
        return

    blobs = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.S)
    if blobs:
        print(f"{len(blobs)} __next_f blobs")
        joined = "".join(b for b in blobs)
        # Unescape JS-style escapes
        joined = joined.encode("utf-8").decode("unicode_escape", errors="replace")
        # Search for motion/prompt hints
        for kw in ["prompt", "motion", "input_image", "duration", "model", "dop", "seedance", "kling"]:
            for hit in re.finditer(rf'("{kw}"\s*:\s*[^,{{}}\]]+)', joined):
                print(f"  {hit.group(1)[:200]}")
        return

    print("neither NEXT_DATA nor next_f — first 3000 chars:")
    print(html[:3000])


asyncio.run(run())
