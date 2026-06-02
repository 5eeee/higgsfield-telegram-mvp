from __future__ import annotations

import asyncio
import io
import logging
import os
import shutil
import subprocess
import tempfile
import time
from typing import Any

import aiohttp
import imageio.v3 as iio
from PIL import Image, ImageOps
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    BufferedInputFile,
    Document,
    FSInputFile,
    Message,
)

from src.config import load_settings
from src.telegram_proxy_probe import discover_local_telegram_proxy
from src.earth_cache import get_or_generate_earth_url, preload_earth_url
from src.earth_zoom import (
    ASPECT_RATIO,
    ASPECT_TO_WH_PORTRAIT,
    DOP_MODEL,
    DURATION_SECONDS,
    EARTH_ZOOM_DOP_ENHANCE_PROMPT,
    EARTH_ZOOM_IN_DOP_PROMPT,
    EARTH_ZOOM_OUT_MOTION_ID,
    EARTH_ZOOM_OUT_MOTION_STRENGTH,
)
from src.higgsfield_api import (
    FINAL_STATUSES,
    HiggsfieldAPI,
    HiggsfieldAPIError,
    HiggsfieldRequestResult,
)
from src.keyboards import EARTH_ZOOM_BUTTON_TEXT, main_keyboard
from src.messages import (
    ASK_PHOTO_TEXT,
    DONE_TEXT,
    DOWNLOADING_TEXT,
    ERROR_TEXT,
    INVALID_MEDIA_TEXT,
    NOT_ENOUGH_CREDITS_TEXT,
    NSFW_BLOCKED_TEXT,
    SENDING_VIDEO_TEXT,
    STEP_EARTH_PICK_TEXT,
    STEP_PREPARING_TEXT,
    STEP_UPLOAD_FACE_TEXT,
    STEP_VIDEO_CREATE_TEXT,
    TIMEOUT_TEXT,
    VIDEO_CAPTION,
    WELCOME_TEXT,
    WORKING_TEXT,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("earth-zoom-bot")

router = Router()


def _ffmpeg_exe() -> str | None:
    """Prefer PATH ffmpeg; else bundled binary from ``imageio-ffmpeg`` (Windows-friendly).

    Without this, reversal falls back to imageio frame decode (~40 MB buffers,
    huge uploads through Telegram proxy).
    """
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


BOT_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="Как пользоваться ботом"),
    BotCommand(command="help", description="Справка"),
]


# --- Entry points ------------------------------------------------------------

@router.message(CommandStart())
@router.message(Command("help"))
async def handle_start(message: Message) -> None:
    await message.answer(
        WELCOME_TEXT,
        reply_markup=main_keyboard(),
        parse_mode=ParseMode.HTML,
    )


@router.message(F.text == EARTH_ZOOM_BUTTON_TEXT)
async def handle_button(message: Message) -> None:
    await message.answer(
        ASK_PHOTO_TEXT,
        reply_markup=main_keyboard(),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


# --- The heart of the bot: any photo triggers the render ---------------------

@router.message(F.photo)
async def handle_photo_message(message: Message, bot: Bot) -> None:
    largest = message.photo[-1]
    logger.info(
        "Photo received: file_id=%s size=%sx%s",
        largest.file_id, largest.width, largest.height,
    )
    await _run_earth_zoom_in(message=message, bot=bot, file_id=largest.file_id)


@router.message(F.document)
async def handle_document_message(message: Message, bot: Bot) -> None:
    doc: Document | None = message.document
    if doc is None:
        await message.answer(INVALID_MEDIA_TEXT)
        return
    if not _document_looks_like_image(doc):
        logger.info(
            "Rejected document: mime=%s name=%s",
            doc.mime_type, doc.file_name,
        )
        await message.answer(INVALID_MEDIA_TEXT)
        return
    logger.info(
        "Document as image: file_id=%s mime=%s name=%s",
        doc.file_id, doc.mime_type, doc.file_name,
    )
    await _run_earth_zoom_in(message=message, bot=bot, file_id=doc.file_id)


@router.message(F.text)
async def handle_text_fallback(message: Message) -> None:
    """Any plain text that isn't the main button → nudge user to send a photo."""
    # Don't answer to commands (handled above) or the main button (handled above).
    await message.answer(ASK_PHOTO_TEXT, parse_mode=ParseMode.HTML)


# --- Pipeline ----------------------------------------------------------------

async def _run_earth_zoom_in(
    message: Message, bot: Bot, file_id: str,
) -> None:
    settings = load_settings()
    status_message = await message.answer(WORKING_TEXT)

    hf_api = HiggsfieldAPI(
        auth_header=settings.hf_auth_header,
        dop_model=DOP_MODEL,
        request_timeout_seconds=settings.hf_http_timeout_seconds,
        upload_timeout_seconds=settings.hf_upload_timeout_seconds,
    )

    try:
        await _safe_edit(status_message, STEP_PREPARING_TEXT)
        telegram_file = await bot.get_file(file_id)
        if not telegram_file.file_path:
            raise HiggsfieldAPIError("Telegram returned empty file path")
        buf = io.BytesIO()
        await bot.download_file(telegram_file.file_path, destination=buf)
        raw_bytes = buf.getvalue()
        if not raw_bytes:
            raise HiggsfieldAPIError("Empty file from Telegram")

        face_bytes, face_mime = _prepare_image_portrait(raw_bytes)
        logger.info(
            "Prepared face image: %s bytes (%s)", len(face_bytes), face_mime,
        )

        await _safe_edit(status_message, STEP_UPLOAD_FACE_TEXT)
        face_url = await hf_api.upload_image_bytes(face_bytes, face_mime)
        logger.info("Face uploaded: %s", face_url[:80])

        await _safe_edit(status_message, STEP_EARTH_PICK_TEXT)
        earth_url = await get_or_generate_earth_url(
            hf_api=hf_api,
            poll_interval_seconds=settings.hf_poll_interval_seconds,
            max_wait_seconds=settings.hf_max_wait_seconds,
        )
        logger.info("Earth ready: %s", earth_url[:80])

        await _safe_edit(status_message, STEP_VIDEO_CREATE_TEXT)
        create = await hf_api.create_video_request(
            # "Earth Zoom Out" motion is learned for subject -> Earth.
            # We generate in that canonical direction and reverse the clip
            # right before delivery to get Earth -> subject.
            start_image_url=face_url,
            end_image_url=earth_url,
            prompt=EARTH_ZOOM_IN_DOP_PROMPT,
            motion_id=EARTH_ZOOM_OUT_MOTION_ID,
            motion_strength=EARTH_ZOOM_OUT_MOTION_STRENGTH,
            duration_seconds=DURATION_SECONDS,
            enhance_prompt=EARTH_ZOOM_DOP_ENHANCE_PROMPT,
        )
        logger.info(
            "DoP render started: %s (duration=%ss, aspect=%s)",
            create.request_id, DURATION_SECONDS, ASPECT_RATIO,
        )

        await _wait_and_deliver(
            message=message,
            status_message=status_message,
            hf_api=hf_api,
            request_id=create.request_id,
            poll_interval_seconds=settings.hf_poll_interval_seconds,
            max_wait_seconds=settings.hf_max_wait_seconds,
        )
    except HiggsfieldAPIError as exc:
        logger.error("Higgsfield API error: %s", exc, exc_info=True)
        await _safe_edit(status_message, _user_visible_error(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error: %s", exc)
        await _safe_edit(status_message, ERROR_TEXT)


async def _wait_and_deliver(
    message: Message,
    status_message: Message,
    hf_api: HiggsfieldAPI,
    request_id: str,
    poll_interval_seconds: int,
    max_wait_seconds: int,
) -> None:
    started_at = time.monotonic()
    spinner = ["⏳", "⌛", "🎬", "✨"]
    idx = 0
    last: str | None = None

    while True:
        result: HiggsfieldRequestResult = await hf_api.get_status(request_id)
        elapsed = int(time.monotonic() - started_at)

        if result.status != last:
            logger.info(
                "DoP status %s -> %s (elapsed=%ss)",
                last, result.status, elapsed,
            )
            last = result.status

        human = {
            "queued": "в очереди",
            "in_queue": "в очереди",
            "in_progress": "рендерится",
            "processing": "рендерится",
        }.get(result.status, result.status)

        text = (
            f"{spinner[idx % len(spinner)]} <b>Earth Zoom In</b>\n"
            f"Higgsfield DoP-lite • 5 сек • HD 3:4\n"
            f"Статус: {human}\n"
            f"Прошло: {elapsed} сек"
        )
        idx += 1
        await _safe_edit(status_message, text, parse_mode=ParseMode.HTML)

        if result.status in FINAL_STATUSES:
            if result.status != "completed":
                raise HiggsfieldAPIError(
                    f"Generation failed: status={result.status}, "
                    f"payload={result.payload!r}",
                )
            if not result.video_url:
                raise HiggsfieldAPIError("Completed request has no video URL")
            await _deliver_video(
                message=message,
                status_message=status_message,
                video_url=result.video_url,
            )
            return

        if elapsed > max_wait_seconds:
            raise HiggsfieldAPIError(
                f"Generation timeout after {max_wait_seconds} seconds"
            )
        await asyncio.sleep(poll_interval_seconds)


async def _send_video_with_retries(
    message: Message,
    video_url: str,
    *,
    local_path: str | None = None,
    video_bytes: bytes | None = None,
) -> bool:
    """Send reversed video: prefer FSInputFile from disk (streams), then bytes, then CDN URL.

    Local upload goes through the bot host twice if we buffer whole-file bytes in RAM.
    Using a temp file + FSInputFile reduces memory churn and lets aiohttp stream.
    Last resort: Telegram fetches ``video_url`` from Higgsfield (no bot upload —
    fastest when usable; URL points at unreversed asset).
    """
    size_mb = 0.0
    if local_path and os.path.isfile(local_path):
        size_mb = os.path.getsize(local_path) / 1024 / 1024
    elif video_bytes:
        size_mb = len(video_bytes) / 1024 / 1024

    # Attempt 1: upload from bot (file stream or RAM).
    if local_path or video_bytes:
        if local_path and os.path.isfile(local_path):
            video_arg: BufferedInputFile | FSInputFile = FSInputFile(
                local_path, filename="earth_zoom_in.mp4",
            )
            upload_label = "Video upload (file)"
        else:
            assert video_bytes is not None
            video_arg = BufferedInputFile(video_bytes, filename="earth_zoom_in.mp4")
            upload_label = "Video upload (bytes)"
        delivered = await _retry_telegram_network_call(
            label=upload_label,
            attempts=2,
            pause_seconds=8,
            sender=lambda: message.answer_video(
                video=video_arg,
                caption=VIDEO_CAPTION,
                parse_mode=ParseMode.HTML,
                supports_streaming=True,
                request_timeout=300,  # 5 min — enough for ~30 MB on slow uplinks
            ),
        )
        if delivered:
            logger.info("Video delivered via upload (%.1f MB)", size_mb)
            return True
        logger.warning("Upload failed repeatedly, falling back to URL send")

    # Attempt 2: URL fallback — Telegram fetches from Higgsfield CDN directly.
    delivered = await _retry_telegram_network_call(
        label="Video URL fallback",
        attempts=10,
        pause_seconds=8,
        sender=lambda: message.answer_video(
            video=video_url,
            caption=VIDEO_CAPTION,
            parse_mode=ParseMode.HTML,
            supports_streaming=True,
            request_timeout=90,
        ),
    )
    if delivered:
        logger.info("Video delivered via URL fallback")
        return True

    # Attempt 3: last resort — send the CDN URL as a plain message so the
    # user at least gets the link and the work isn't wasted.
    logger.error("All video send attempts failed, sending CDN link as text")
    delivered = await _retry_telegram_network_call(
        label="Text link fallback",
        attempts=10,
        pause_seconds=8,
        sender=lambda: message.answer(
            f"{VIDEO_CAPTION}\n\n"
            f"<a href=\"{video_url}\">Скачать видео напрямую с Higgsfield CDN</a>\n\n"
            f"<i>Не удалось доставить файл в Telegram — но ролик готов. "
            f"Нажми на ссылку выше, чтобы скачать.</i>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False,
        ),
    )
    return delivered


async def _deliver_video(
    message: Message, status_message: Message, video_url: str,
) -> None:
    logger.info("Preparing generated video from %s...", video_url[:80])
    await _safe_edit(status_message, DOWNLOADING_TEXT)

    local_path: str | None = None
    video_bytes: bytes | None = None

    try:
        local_path = _reverse_cdn_to_tempfile_ffmpeg(video_url)
        if local_path:
            sz = os.path.getsize(local_path)
            logger.info(
                "Video reversed via ffmpeg CDN pipe (%s MB)",
                round(sz / 1024 / 1024, 2),
            )
        else:
            video_bytes = await _download_video_bytes(video_url)
            logger.info("Downloaded %s bytes", len(video_bytes))
            reversed_bytes = _reverse_video_bytes(video_bytes)
            if reversed_bytes:
                video_bytes = reversed_bytes
                logger.info("Video reversed for Earth -> subject trajectory")
            fd, tmp_path = tempfile.mkstemp(suffix=".mp4", prefix="earth_rev_")
            os.close(fd)
            try:
                with open(tmp_path, "wb") as f:
                    f.write(video_bytes)
                local_path = tmp_path
                video_bytes = None
            except Exception:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("Prepare video failed, will try CDN URL send only: %s", exc)
        local_path = None
        video_bytes = None

    await _safe_edit(status_message, SENDING_VIDEO_TEXT)
    heartbeat = asyncio.create_task(_heartbeat_upload_progress(status_message))
    try:
        delivered = await _send_video_with_retries(
            message,
            video_url,
            local_path=local_path,
            video_bytes=video_bytes,
        )
    finally:
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass
        if local_path and os.path.isfile(local_path):
            try:
                os.remove(local_path)
            except OSError:
                pass
    if not delivered:
        # Don't throw — network may be flapping; user will retry.
        await _safe_edit(status_message, TIMEOUT_TEXT)
        return

    try:
        await status_message.delete()
    except Exception as exc:  # noqa: BLE001
        logger.debug("status delete noop: %s", exc)

    await _retry_telegram_network_call(
        label="Done message",
        attempts=6,
        pause_seconds=6,
        sender=lambda: message.answer(DONE_TEXT, reply_markup=main_keyboard()),
    )


# --- Helpers -----------------------------------------------------------------

def _document_looks_like_image(document: Document) -> bool:
    if document.mime_type and document.mime_type.startswith("image/"):
        return True
    if document.file_name:
        name = document.file_name.lower()
        return name.endswith((".jpg", ".jpeg", ".png", ".webp"))
    return False


def _user_visible_error(exc: BaseException) -> str:
    msg = str(exc).lower()
    if "not enough credits" in msg or ("403" in str(exc) and "credit" in msg):
        return NOT_ENOUGH_CREDITS_TEXT
    if "nsfw" in msg:
        return NSFW_BLOCKED_TEXT
    if (
        "timeout" in msg
        or "request timeout" in msg
        or "cannot connect" in msg
        or "telegramnetworkerror" in msg
    ):
        return TIMEOUT_TEXT
    return ERROR_TEXT


MIN_SIDE_PX = 1152    # DoP input minimum for HD output (matches Earth asset)
MAX_SIDE_PX = 2048    # cap to keep upload + Soul happy
TARGET_RATIO = 3 / 4  # portrait 3:4


def _prepare_image_portrait(raw_bytes: bytes) -> tuple[bytes, str]:
    """Crop the incoming photo to 3:4 portrait, preserving original quality.

    We no longer force a downscale to 1080x1440 — that threw away detail and
    made DoP output SD (816x1104). Instead:
      * EXIF-rotate
      * center-crop to 3:4 (bias toward the top so the face stays in-frame)
      * only upscale small images to MIN_SIDE_PX, only downscale huge ones
        to MAX_SIDE_PX. Anything in between is kept 1-to-1.
    """
    with Image.open(io.BytesIO(raw_bytes)) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        src_w, src_h = img.size
        src_ratio = src_w / src_h
        if src_ratio > TARGET_RATIO:
            new_w = int(round(src_h * TARGET_RATIO))
            left = (src_w - new_w) // 2
            img = img.crop((left, 0, left + new_w, src_h))
        else:
            new_h = int(round(src_w / TARGET_RATIO))
            top = max(0, (src_h - new_h) // 3)
            img = img.crop((0, top, src_w, top + new_h))

        cw, ch = img.size
        if cw < MIN_SIDE_PX:
            scale = MIN_SIDE_PX / cw
            img = img.resize(
                (int(round(cw * scale)), int(round(ch * scale))),
                Image.LANCZOS,
            )
        elif cw > MAX_SIDE_PX:
            scale = MAX_SIDE_PX / cw
            img = img.resize(
                (int(round(cw * scale)), int(round(ch * scale))),
                Image.LANCZOS,
            )

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=96, optimize=True, subsampling=0)
    return buf.getvalue(), "image/jpeg"


def _reverse_cdn_to_tempfile_ffmpeg(video_url: str) -> str | None:
    """Reverse MP4 by piping the Higgsfield CDN URL through ffmpeg.

    Avoids ``aiohttp`` reading the entire file into Python first, which cuts
    RAM and usually speeds up the handoff to Telegram (smaller ffmpeg output
    with ``ultrafast`` + ``+faststart`` for quicker in-app playback).
    """
    ffmpeg_bin = _ffmpeg_exe()
    if not ffmpeg_bin:
        return None
    out_path: str | None = None
    try:
        fd, out_path = tempfile.mkstemp(suffix=".mp4", prefix="earth_rev_")
        os.close(fd)
        cmd = [
            ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            video_url,
            "-vf",
            "reverse",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "26",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            out_path,
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=420,
            check=False,
        )
        if proc.returncode != 0:
            logger.warning(
                "ffmpeg CDN reverse failed (fallback to download): %s",
                (proc.stderr or "")[-500:],
            )
            try:
                os.remove(out_path)
            except OSError:
                pass
            return None
        if os.path.getsize(out_path) < 512:
            try:
                os.remove(out_path)
            except OSError:
                pass
            return None
        return out_path
    except Exception as exc:  # noqa: BLE001
        logger.warning("ffmpeg CDN reverse exception: %s", exc)
        if out_path and os.path.isfile(out_path):
            try:
                os.remove(out_path)
            except OSError:
                pass
        return None


async def _download_video_bytes(url: str, total_timeout_seconds: int = 240) -> bytes:
    timeout = aiohttp.ClientTimeout(total=total_timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            if response.status >= 400:
                raise HiggsfieldAPIError(
                    f"Failed to download video ({url[:80]}): HTTP {response.status}"
                )
            return await response.read()


def _reverse_video_bytes(video_bytes: bytes) -> bytes | None:
    """Reverse MP4 bytes in-memory using ffmpeg.

    The Higgsfield motion "Earth Zoom Out" is reliably generated as
    subject->Earth. We reverse that output to obtain Earth->subject, which
    matches the target UX and reference links.
    """
    if not video_bytes:
        return None

    in_path: str | None = None
    out_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as in_file:
            in_file.write(video_bytes)
            in_path = in_file.name
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as out_file:
            out_path = out_file.name

        ffmpeg_bin = _ffmpeg_exe()
        if ffmpeg_bin:
            cmd = [
                ffmpeg_bin,
                "-y",
                "-i",
                in_path,
                "-vf",
                "reverse",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "26",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                out_path,
            ]
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=120,
                check=False,
            )
            if proc.returncode != 0:
                logger.warning("ffmpeg reverse failed: %s", proc.stderr[-500:])
                return _reverse_with_imageio(in_path, out_path)
        else:
            logger.warning(
                "ffmpeg unavailable (PATH + imageio_ffmpeg); using imageio reverse fallback",
            )
            return _reverse_with_imageio(in_path, out_path)
        with open(out_path, "rb") as f:
            return f.read()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Reverse step failed, using original clip: %s", exc)
        return None
    finally:
        if in_path:
            try:
                os.remove(in_path)
            except OSError:
                pass
        if out_path:
            try:
                os.remove(out_path)
            except OSError:
                pass


def _reverse_with_imageio(in_path: str, out_path: str) -> bytes | None:
    """Fallback reverse when system ffmpeg isn't on PATH."""
    try:
        frames = list(iio.imiter(in_path))
        if not frames:
            return None
        iio.imwrite(out_path, frames[::-1], fps=30)
        with open(out_path, "rb") as f:
            return f.read()
    except Exception as exc:  # noqa: BLE001
        logger.warning("imageio reverse fallback failed: %s", exc)
        return None


async def _heartbeat_upload_progress(status_message: Message) -> None:
    """While Telegram uploads a large MP4 (slow via VPN proxy), reassure the user."""
    elapsed = 0
    extra = (
        "\n\n<i>Прошло {sec} сек. Большой файл — загрузка в Telegram через прокси/VPN "
        "может занять несколько минут.</i>"
    )
    try:
        while True:
            await asyncio.sleep(35)
            elapsed += 35
            await _safe_edit(
                status_message,
                SENDING_VIDEO_TEXT + extra.format(sec=elapsed),
                parse_mode=ParseMode.HTML,
            )
    except asyncio.CancelledError:
        raise


async def _retry_telegram_network_call(
    *,
    label: str,
    attempts: int,
    pause_seconds: int,
    sender: Any,
) -> bool:
    """Retry transient Telegram network failures without aborting the pipeline."""
    for attempt in range(1, attempts + 1):
        try:
            await sender()
            if attempt > 1:
                logger.info("%s succeeded on attempt %s/%s", label, attempt, attempts)
            return True
        except (
            TelegramNetworkError,
            TimeoutError,
            OSError,
        ) as exc:
            logger.warning("%s failed on attempt %s/%s: %s", label, attempt, attempts, exc)
            if attempt < attempts:
                await asyncio.sleep(pause_seconds)
    logger.error("%s failed after %s attempts", label, attempts)
    return False


async def _safe_edit(status_message: Message, text: str, **kwargs: Any) -> None:
    try:
        await status_message.edit_text(text, **kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.debug("edit_text noop: %s", exc)


# --- Entry point -------------------------------------------------------------

async def _wait_until_telegram_ok(bot: Bot) -> None:
    """Block until Bot API is reachable (get_me). Retries forever with backoff.

    Without this, `start_polling` crashes on first get_me() when
    `api.telegram.org` is blocked (e.g. RU) — the process exits and the bot
    "does not react". User can turn on VPN / set TELEGRAM_PROXY and wait.
    Catches proxy refused / aiohttp errors too (not only TelegramNetworkError).
    """
    attempt = 0
    while True:
        try:
            me = await bot.get_me()
            logger.info("Telegram API reachable: @%s (id=%s)", me.username, me.id)
            return
        except TelegramUnauthorizedError:
            raise
        except TelegramNetworkError as exc:
            attempt += 1
            wait_s = min(30, 5 * min(attempt, 6))
            logger.error(
                "No route to api.telegram.org (try %s). Set TELEGRAM_PROXY or "
                "system HTTPS_PROXY (SOCKS/HTTP, not MTProto in the TG app). "
                "VPS or full-tunnel VPN. Retrying in %s s. %s",
                attempt,
                wait_s,
                exc,
            )
            await asyncio.sleep(float(wait_s))
        except Exception as exc:  # noqa: BLE001
            attempt += 1
            wait_s = min(30, 5 * min(attempt, 6))
            hint = (
                " If TELEGRAM_PROXY: start the VPN app, check the port is LISTENING on 127.0.0.1, "
                "or remove TELEGRAM_PROXY and use VPN TUN so Python goes through the tunnel."
            )
            logger.error(
                "get_me failed (try %s).%s Retrying in %s s. %s",
                attempt,
                hint,
                wait_s,
                exc,
            )
            await asyncio.sleep(float(wait_s))


async def main() -> None:
    settings = load_settings()
    # Generous timeout so sending 20+ MB videos over slow links doesn't die.
    # aiogram default is 60 s — our videos sometimes need 3–5 minutes to upload.
    telegram_session_timeout = 600.0

    proxy_url = settings.telegram_proxy
    proxy_src = settings.telegram_proxy_source
    if not proxy_url:
        discovered = await discover_local_telegram_proxy(settings.telegram_bot_token)
        if discovered:
            proxy_url = discovered
            proxy_src = "auto_local_probe"

    if proxy_url:
        session = AiohttpSession(
            proxy=proxy_url, timeout=telegram_session_timeout,
        )
    else:
        session = AiohttpSession(timeout=telegram_session_timeout)
    bot = Bot(token=settings.telegram_bot_token, session=session)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    if proxy_url:
        src = proxy_src or "TELEGRAM_PROXY"
        logger.info("Bot API using proxy (from %s)", src)
    else:
        logger.info(
            "Bot API: no proxy in env (TELEGRAM_PROXY / HTTPS_PROXY / …) — direct HTTPS",
        )

    await _wait_until_telegram_ok(bot)

    # Warm up Earth cache so the first user doesn't pay the Soul queue penalty.
    hf_api = HiggsfieldAPI(
        auth_header=settings.hf_auth_header,
        dop_model=DOP_MODEL,
        request_timeout_seconds=settings.hf_http_timeout_seconds,
        upload_timeout_seconds=settings.hf_upload_timeout_seconds,
    )
    try:
        earth_url = await preload_earth_url(
            hf_api=hf_api,
            poll_interval_seconds=settings.hf_poll_interval_seconds,
            max_wait_seconds=settings.hf_max_wait_seconds,
        )
        logger.info("Earth preloaded: %s", earth_url[:80])
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Earth preload failed, will retry on first user request: %s", exc,
        )

    logger.info(
        "Earth Zoom In bot started (duration=%ss, aspect=%s, model=%s)",
        DURATION_SECONDS, ASPECT_RATIO, DOP_MODEL,
    )
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except TelegramNetworkError as exc:
        logger.warning(
            "delete_webhook failed — check VPN or TELEGRAM_PROXY in .env: %s", exc,
        )
    try:
        await bot.set_my_commands(BOT_COMMANDS)
    except TelegramNetworkError as exc:
        logger.warning("set_my_commands failed (continuing to poll): %s", exc)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
