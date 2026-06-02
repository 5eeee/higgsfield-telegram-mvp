# Техническая документация — Earth Zoom In Telegram Bot

> Репозиторий: [github.com/5eeee/higgsfield-telegram-mvp](https://github.com/5eeee/higgsfield-telegram-mvp)  
> Автор: Владимир Кутомкин

## Связанные документы

| Документ | Содержание |
|----------|------------|
| [README.md](../README.md) | Обзор и архитектура |
| [docs/DEPLOY_GITHUB_VPS.md](DEPLOY_GITHUB_VPS.md) | Деплой на VPS |

## 1. Назначение

Telegram-бот: пользователь отправляет фото → Higgsfield API генерирует 8-секундное видео «космос → лицо» (эффект Earth Zoom In).

## 2. Стек

Python 3.11+ · aiogram 3 · aiohttp · Pillow · ffmpeg · Higgsfield API · pytest · Docker · GitHub Actions

## 3. Структура

```
src/
├── bot.py              # Handlers, точка входа
├── config.py           # Settings из .env
├── higgsfield_api.py   # DoP, Soul, upload
├── earth_zoom.py       # Motion, промпты, aspect
├── earth_cache.py      # Кэш Earth-кадров
├── keyboards.py, messages.py
tests/                  # 40 unit-тестов
scripts/                # smoke, preflight, launch
```

## 4. Архитектура

```
Telegram → bot.py → prepare (3:4) → Soul (cache) → DoP preview → polling → video → TG
```

Ключевой трюк: motion **Earth Zoom Out** с инвертированными keyframes (start=Earth, end=face).

## 5. Переменные окружения

| Переменная | Описание |
|------------|----------|
| `TELEGRAM_BOT_TOKEN` | Токен бота |
| `TELEGRAM_PROXY` | Прокси (если api.telegram.org недоступен) |
| `HF_API_KEY`, `HF_API_SECRET` | Higgsfield API |
| `HF_POLL_INTERVAL_SECONDS` | Интервал polling (3) |
| `HF_MAX_WAIT_SECONDS` | Таймаут рендера (420) |

## 6. Запуск

```powershell
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m src.bot
```

## 7. Тестирование

```powershell
python -m pytest tests/ -q
python scripts/smoke_full.py
python scripts/preflight.py
```

CI: `.github/workflows/ci.yml` — pytest на каждый push в main.

## 8. Production

GitHub → VPS (Docker Compose), секреты только в `.env` на сервере. См. [docs/DEPLOY_GITHUB_VPS.md](DEPLOY_GITHUB_VPS.md).

## 9. Параметры рендера

| Параметр | Значение |
|----------|----------|
| Duration | ~5–8 сек |
| Aspect | 3:4 portrait |
| Motion | Earth Zoom Out (инвертированный) |
| Model | dop-lite |
