"""Try common local SOCKS/HTTP ports when TELEGRAM_PROXY is unset (Clash, v2ray, etc.)."""
from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import sys

import aiohttp

logger = logging.getLogger("earth-zoom-bot")

# Typical local ports (Clash HTTP 7890, v2ray SOCKS 10808, …)
PROBE_CANDIDATES: tuple[str, ...] = (
    "http://127.0.0.1:7890",
    "http://127.0.0.1:7897",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:8888",
    "http://127.0.0.1:10809",
    "socks5://127.0.0.1:1080",
    "socks5://127.0.0.1:10808",
    "socks5://127.0.0.1:7891",
    "socks5://127.0.0.1:1090",
    "socks5://127.0.0.1:7890",
)


def _listening_loopback_ports_windows() -> list[int]:
    """Parse ``netstat`` for TCP LISTEN on 127.0.0.1 (local VPN/Clash ports)."""
    if sys.platform != "win32":
        return []
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        r = subprocess.run(
            ["netstat", "-an"],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=flags,
            check=False,
        )
    except OSError:
        return []
    ports: set[int] = set()
    for line in (r.stdout or "").splitlines():
        if "LISTENING" not in line.upper():
            continue
        m = re.search(r"127\.0\.0\.1:(\d+)", line)
        if m:
            p = int(m.group(1))
            if 1 <= p <= 65535:
                ports.add(p)
    return sorted(ports)


def _all_proxy_candidates() -> tuple[str, ...]:
    """netstat-based URLs first, then static list; dedupe; cap length."""
    seen: set[str] = set()
    ordered: list[str] = []

    for p in _listening_loopback_ports_windows()[:32]:
        for url in (f"http://127.0.0.1:{p}", f"socks5://127.0.0.1:{p}"):
            if url not in seen:
                seen.add(url)
                ordered.append(url)
    for url in PROBE_CANDIDATES:
        if url not in seen:
            seen.add(url)
            ordered.append(url)
    return tuple(ordered[:56])


async def _getme_ok(token: str, proxy: str, *, timeout_total: float) -> bool:
    from aiohttp_socks import ProxyConnector

    url = f"https://api.telegram.org/bot{token}/getMe"
    timeout = aiohttp.ClientTimeout(total=timeout_total)
    try:
        connector = ProxyConnector.from_url(proxy)
    except Exception:  # noqa: BLE001
        return False
    try:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.get(url) as response:
                try:
                    payload = await response.json(content_type=None)
                except Exception:  # noqa: BLE001
                    return False
    except Exception:  # noqa: BLE001
        return False
    return response.status == 200 and bool(payload.get("ok"))


async def discover_local_telegram_proxy(
    token: str,
    *,
    per_try_timeout: float = 3.5,
) -> str | None:
    """Return first working ``http://`` or ``socks5://`` on localhost, or ``None``."""

    async def try_one(proxy: str) -> str | None:
        if await _getme_ok(token, proxy, timeout_total=per_try_timeout):
            return proxy
        return None

    candidates = _all_proxy_candidates()
    tasks = [asyncio.create_task(try_one(p)) for p in candidates]
    picked: str | None = None
    try:
        for fut in asyncio.as_completed(tasks):
            try:
                result = await fut
            except asyncio.CancelledError:
                continue
            if result:
                picked = result
                for t in tasks:
                    if not t.done():
                        t.cancel()
                break
        if picked:
            logger.info(
                "Auto-picked local proxy for Bot API (no TELEGRAM_PROXY / HTTPS_PROXY)",
            )
        return picked
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
