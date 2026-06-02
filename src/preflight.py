from __future__ import annotations

import asyncio
import uuid

import aiohttp

from src.config import load_settings
from src.telegram_proxy_probe import discover_local_telegram_proxy
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

    tg_proxy = settings.telegram_proxy
    tg_src = settings.telegram_proxy_source
    if not tg_proxy:
        discovered = await discover_local_telegram_proxy(settings.telegram_bot_token)
        if discovered:
            tg_proxy = discovered
            tg_src = "auto_local_probe"

    if tg_proxy:
        src = tg_src or "TELEGRAM_PROXY"
        print(f"Telegram proxy: {tg_proxy!r} (from {src})")
    else:
        print("Telegram proxy: (none — direct HTTPS; TG in-app MTProto does not apply)")

    telegram_ok, telegram_message = await _check_telegram(
        settings.telegram_bot_token,
        tg_proxy,
    )
    hf_ok, hf_message = await _check_higgsfield(settings.hf_auth_header)

    print(f"Telegram:   {'OK' if telegram_ok else 'FAIL'} - {telegram_message}")
    print(f"Higgsfield: {'OK' if hf_ok else 'FAIL'} - {hf_message}")

    if not telegram_ok:
        print(
            "\nTelegram недоступен: часто VPN в браузере не трогает Python. "
            "В настройках VPN найдите локальный HTTP/SOCKS порт и добавьте в .env, "
            "например: TELEGRAM_PROXY=socks5://127.0.0.1:1080\n"
            "См. раздел «Telegram: VPN и прокси» в README.md.",
        )

    if not telegram_ok or not hf_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
