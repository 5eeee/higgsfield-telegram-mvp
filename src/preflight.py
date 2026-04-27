from __future__ import annotations

import asyncio
import uuid

import aiohttp

from src.config import load_settings
from src.higgsfield_api import HIGGSFIELD_BASE_URL


async def _check_telegram(token: str, proxy: str | None) -> tuple[bool, str]:
    url = f"https://api.telegram.org/bot{token}/getMe"
    # First HTTPS handshake can be slow on some networks/VPN paths.
    timeout = aiohttp.ClientTimeout(total=60)
    connector = None
    if proxy:
        from aiohttp_socks import ProxyConnector

        connector = ProxyConnector.from_url(proxy)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        try:
            async with session.get(url) as response:
                try:
                    payload = await response.json(content_type=None)
                except Exception:  # noqa: BLE001
                    payload = {"raw_text": await response.text()}
        except Exception as exc:  # noqa: BLE001
            return False, f"network error: {exc!r}"

    if response.status != 200 or not payload.get("ok"):
        return False, f"HTTP {response.status}: {payload}"

    result = payload.get("result", {})
    username = result.get("username", "<unknown>")
    bot_id = result.get("id", "<unknown>")
    return True, f"ok (id={bot_id}, username=@{username})"


async def _check_higgsfield(auth_header: str) -> tuple[bool, str]:
    random_request = str(uuid.uuid4())
    url = f"{HIGGSFIELD_BASE_URL}/requests/{random_request}/status"
    headers = {"Authorization": auth_header, "Accept": "application/json"}

    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(url, headers=headers) as response:
                try:
                    payload = await response.json(content_type=None)
                except Exception:  # noqa: BLE001
                    payload = {"raw_text": await response.text()}
        except Exception as exc:  # noqa: BLE001
            return False, f"network error: {exc!r}"

    if response.status == 401:
        return False, "unauthorized (invalid key/secret)"

    if response.status >= 500:
        return False, f"server error while checking auth (HTTP {response.status}, payload={payload})"

    # For a random request_id, authorized credentials usually return 200/400/404.
    return True, f"auth accepted (HTTP {response.status})"


async def main() -> None:
    try:
        settings = load_settings()
    except ValueError as exc:
        print(f"Configuration: FAIL - {exc}")
        raise SystemExit(1)

    if settings.telegram_proxy:
        print(f"Telegram proxy: {settings.telegram_proxy}")

    telegram_ok, telegram_message = await _check_telegram(
        settings.telegram_bot_token,
        settings.telegram_proxy,
    )
    hf_ok, hf_message = await _check_higgsfield(settings.hf_auth_header)

    print(f"Telegram:   {'OK' if telegram_ok else 'FAIL'} - {telegram_message}")
    print(f"Higgsfield: {'OK' if hf_ok else 'FAIL'} - {hf_message}")

    if not telegram_ok or not hf_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
