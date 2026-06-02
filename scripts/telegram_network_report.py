"""Print Telegram Bot API reachability (direct, local ports). Run: python scripts/telegram_network_report.py"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv


async def main() -> None:
    load_dotenv()
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN missing in .env")
        return

    from src.telegram_proxy_probe import (
        _all_proxy_candidates,
        _getme_ok,
        discover_local_telegram_proxy,
    )

    print("--- Direct HTTPS (no proxy) ---")
    try:
        import aiohttp

        url = f"https://api.telegram.org/bot{token}/getMe"
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15),
        ) as session:
            async with session.get(url) as response:
                body = await response.json(content_type=None)
        print("  status:", response.status, "ok:", body.get("ok"))
    except Exception as exc:  # noqa: BLE001
        print("  FAIL:", exc)

    print("--- Local proxy autodiscovery (same as bot startup) ---")
    found = await discover_local_telegram_proxy(token, per_try_timeout=3.0)
    print("  picked:", found)

    print("--- Sample of candidate URLs tried (first 12) ---")
    for u in list(_all_proxy_candidates())[:12]:
        ok = await _getme_ok(token, u, timeout_total=3.0)
        print(" ", u, "->", "OK" if ok else "no")


if __name__ == "__main__":
    asyncio.run(main())
