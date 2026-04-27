"""Configure bot profile via Telegram Bot API (name, descriptions, commands).

Run: python scripts/setup_bot_profile.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import BotCommand

from src.config import load_settings

BOT_NAME = "Earth Zoom AI"

SHORT_DESCRIPTION = (
    "AI-бот, который превращает фото лица в эффектный Earth zoom in ролик."
)

LONG_DESCRIPTION = (
    "Earth Zoom AI превращает одно фото лица в короткое cinematic-видео в стиле "
    "Earth zoom in. Нажмите «Создать видео», выберите длительность (5/10/15 сек) "
    "и отправьте фото — бот покажет живой статус и пришлёт готовый ролик прямо в Telegram.\n\n"
    "Под капотом: Higgsfield API, фиксированный сценарий, максимум приватности."
)

COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="new", description="Новое видео Earth zoom in"),
    BotCommand(command="help", description="Как пользоваться"),
]


async def main() -> None:
    settings = load_settings()
    session = (
        AiohttpSession(proxy=settings.telegram_proxy)
        if settings.telegram_proxy
        else AiohttpSession()
    )
    bot = Bot(token=settings.telegram_bot_token, session=session)
    try:
        me = await bot.get_me()
        print(f"Bot: @{me.username} (id={me.id})")

        await bot.set_my_name(name=BOT_NAME)
        print(f"set_my_name -> OK ({BOT_NAME!r})")

        await bot.set_my_short_description(short_description=SHORT_DESCRIPTION)
        print("set_my_short_description -> OK")

        await bot.set_my_description(description=LONG_DESCRIPTION)
        print("set_my_description -> OK")

        await bot.set_my_commands(commands=COMMANDS)
        print("set_my_commands -> OK (/start /new /help)")

        print("\nDone. Аватар ставится вручную через BotFather -> /setuserpic.")
        print("Готовый PNG: assets/earth-zoom-in-logo.png")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
