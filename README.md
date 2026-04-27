# Earth Zoom In Telegram Bot

MVP Telegram-бот, повторяющий **Higgsfield Earth Zoom In** 1-в-1 через
официальный API. Один сценарий — один UX. Кинематографическое приближение
из космоса через атмосферу и город прямо к лицу пользователя.

Референс, на который настроен бот:
[higgsfield.ai/s/28TKrUxP9Bk](https://higgsfield.ai/s/28TKrUxP9Bk)

## Что делает

1. Пользователь присылает **любое фото** (как картинку или как файл).
2. Бот сразу запускает рендер — никаких меню, FSM, выбора пресетов.
3. Через ~1–2 минуты приходит видео:
   - **8 секунд** (как в референсе)
   - **Вертикаль 3:4** (как в референсе)
   - **Start frame**: фотореалистичная Земля из космоса (Soul-generated
     фотографическая Земля с атмосферой, континентами, облаками)
   - **End frame**: оригинальное фото пользователя **без искажений**
   - **Траектория**: Earth → атмосфера → континенты → город сверху → лицо

## Архитектура

```
Пользователь ─── фото ───▶ Telegram Bot API (polling)
                                   │
                                   ▼
                        src/bot.py: _run_earth_zoom_in
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        ▼                          ▼                          ▼
   prepare (3:4)              Soul (cache)                DoP preview
  crop+resize+JPEG95    photorealistic Earth          image2video/dop
                        (pre-generated pool)            start=Earth
                                                         end=face
                                                  motion=Earth Zoom Out
                                                   duration=8, 3:4
                                   │
                                   ▼
                            status polling (3s)
                                   │
                                   ▼
                        download bytes + send to TG
```

### Ключевой трюк

В каталоге `/v1/motions` нет пресета "Earth Zoom In" — есть только
`Earth Zoom Out` (motion trained на траектории face→orbit→Earth). Мы
**инвертируем роли кадров**: `start=Earth, end=user_face`. Motion движется
по своей обученной траектории, но keyframes поменялись местами, и
получается чистый Earth → face zoom-in. Финальный кадр = буквально
`end_image`, т.е. оригинальная фотография пользователя.

Это — точная копия recipe, который Higgsfield Studio использует на сайте.

## GitHub и круглосуточный бот на VPS

Код в **GitHub**, а работа 24/7 — на **VPS в США/Европе** (Docker), без привязки к ноутбуку.  
Пошагово: [docs/DEPLOY_GITHUB_VPS.md](docs/DEPLOY_GITHUB_VPS.md).

Кратко: `git push` в репозиторий → на сервере `git pull` и `docker compose up -d --build`.  
Секреты (`TELEGRAM_BOT_TOKEN`, Higgsfield) задаются **только** в `.env` на сервере.

При каждом push в `main` GitHub Actions гоняет `pytest` (см. `.github/workflows/ci.yml`).

## Установка (локально)

```powershell
git clone https://github.com/YOUR_USER/YOUR_REPO.git
cd higgsfield-telegram-mvp
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# впиши TELEGRAM_BOT_TOKEN + HF_API_KEY + HF_API_SECRET

python -m src.bot
```

### `.env`

```
TELEGRAM_BOT_TOKEN=...
HF_API_KEY=...
HF_API_SECRET=...
# Если api.telegram.org недоступен (регион/фаервол):
# TELEGRAM_PROXY=socks5://127.0.0.1:1080

HF_POLL_INTERVAL_SECONDS=3
HF_MAX_WAIT_SECONDS=420
HF_HTTP_TIMEOUT_SECONDS=60
HF_UPLOAD_TIMEOUT_SECONDS=120
```

## Параметры рендера (см. `src/earth_zoom.py`)

| Параметр | Значение | Комментарий |
|---|---|---|
| Duration (API) | **5 c** (≈5.37 с на выходе) | публичный DoP; эталон 8 с в веб-UI — другой пайп |
| Aspect | **3:4 portrait** | |
| Motion | **Earth Zoom Out** (`46fa79e3-efce-41e8-95bc-1dc5a1a30795`) | `start_end_frame` |
| Motion strength | **0.75** | снижает «плывшую» середину |
| Model | **dop-lite** | HD 960×1280 в наших тестах API |
| Enhance prompt | **False** (по умолчанию) | длинный явный prompt в `earth_zoom.py` |

## Earth background кеш

Soul (`text2image`) на Higgsfield имеет очередь 3–5 минут для фоновой
генерации. Чтобы пользователь не ждал 6 мин на каждый ролик, бот держит
pool Earth-шотов в `earth_cache.json` — хэдер: `[{url, created_at}]`.

Self-healing: при каждом запросе кеш сначала проверяет, что URL всё ещё
живой (HEAD-check с fallback на Range-GET). Мёртвые URL удаляются,
пустой кеш = одна генерация Soul → в кеш → в рендер.

## Тестирование

```powershell
python -m pytest tests/ -q          # 40 unit-тестов
python scripts/smoke_full.py        # живой E2E прогон
python scripts/preflight.py         # проверка API доступов
python scripts/scrape_share.py URL  # вытащить mp4 из Higgsfield share
```

## Структура

```
src/
  bot.py             # Handlers (photo / document / text), no FSM
  config.py          # Settings + .env loader (минимум параметров)
  higgsfield_api.py  # API client: DoP, Seedance, Kling, Minimax, Soul
                     # (лишние движки остались на будущее, бот использует DoP)
  earth_zoom.py      # Ссылки на motion UUID, промпты, duration/aspect
  earth_cache.py     # Кеш Earth-шотов с self-healing
  keyboards.py       # Единственная reply-кнопка
  messages.py        # RU-тексты
  states.py          # (пустой, FSM не используется)

tests/               # 40 тестов
scripts/
  smoke_full.py      # E2E прогон (реальный Higgsfield)
  scrape_share.py    # HTML scraper для higgsfield.ai/s/<id>
  preflight.py       # проверка API доступов
  ...

docs/                # Заметки по API probing
motions_full.json    # Дамп /v1/motions (может пригодиться для будущих режимов)
```

## История эволюции

- **v1** — dual-frame DoP Earth→face с motion Earth Zoom In: не было такого motion
- **v2** — single-frame face→Earth + локальный реверс: корректное лицо в конце, но медленно
- **v3** — Seedance 2.0 "VFX рулетка" из 14 эффектов: быстро, но мимо ТЗ
- **v4** — 121 motion-пресетов с категориями, 4 движка, флагман Earth Zoom In
- **v5 (текущая)** — только Earth Zoom In, настроен под эталон с higgsfield.ai,
  без меню и FSM, просто «прислал фото → получил ролик»
