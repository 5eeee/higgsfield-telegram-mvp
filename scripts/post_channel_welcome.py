"""Post a welcome message with an inline button to the Telegram channel
and pin it. Bot must be admin in the channel with 'post messages' & 'pin' rights.

Run: python scripts/post_channel_welcome.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from src.config import load_settings

CHANNEL = "@test_bota_qwiak"
BOT_USERNAME = "testbotiid_bot"

CHANNEL_WELCOME = (
    "<b>🌍 Earth Zoom AI — MVP запущен</b>\n\n"
    "Премиум AI-бот, который превращает одно фото лица в cinematic-видео "
    "в стиле Earth zoom in: камера улетает в космос и показывает планету Земля.\n\n"
    "<b>Что внутри:</b>\n"
    "• выбор длительности 5 / 10 / 15 секунд\n"
    "• фиксированный сценарий Earth zoom in\n"
    "• живой статус генерации в одном сообщении\n"
    "• готовый ролик приходит прямо в чат\n\n"
    "Нажмите кнопку ниже и пришлите фото — бот сделает всё сам."
)

LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "earth-zoom-in-logo.png"


def _button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Открыть бота",
                    url=f"https://t.me/{BOT_USERNAME}?start=from_channel",
                )
            ]
        ]
    )


async def main() -> None:
    settings = load_settings()
    session = (
        AiohttpSession(proxy=settings.telegram_proxy)
        if settings.telegram_proxy
        else AiohttpSession()
    )
    bot = Bot(token=settings.telegram_bot_token, session=session)
    try:
        try:
            if LOGO_PATH.exists():
                sent = await bot.send_photo(
                    chat_id=CHANNEL,
                    photo=FSInputFile(str(LOGO_PATH)),
                    caption=CHANNEL_WELCOME,
                    parse_mode=ParseMode.HTML,
                    reply_markup=_button(),
                )
                print(f"Posted photo message_id={sent.message_id}")
            else:
                sent = await bot.send_message(
                    chat_id=CHANNEL,
                    text=CHANNEL_WELCOME,
                    parse_mode=ParseMode.HTML,
                    reply_markup=_button(),
                    disable_web_page_preview=True,
                )
                print(f"Posted text message_id={sent.message_id}")
        except TelegramAPIError as exc:
            print("Failed to post to channel:", exc)
            print(
                "Make the bot admin in the channel with 'post messages' rights, then re-run."
            )
            raise

        try:
            await bot.pin_chat_message(
                chat_id=CHANNEL,
                message_id=sent.message_id,
                disable_notification=True,
            )
            print("Pinned.")
        except TelegramAPIError as exc:
            print("Could not pin (needs 'pin messages' admin right):", exc)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
