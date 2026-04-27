# MVP Runbook (Telegram + Higgsfield)

## 1) Что уже подключено

- Telegram бот подключается через `TELEGRAM_BOT_TOKEN`.
- Higgsfield подключается через `Authorization: Key <HF_API_KEY>:<HF_API_SECRET>`.
- Сценарий зафиксирован по ТЗ: `Earth zoom in`, `16:9`, длительность до 15 сек.

## 2) Быстрый запуск

```bash
pip install -r requirements.txt
python -m src.preflight
python -m src.bot
```

## 3) Переменные окружения

Минимально обязательно:

- `TELEGRAM_BOT_TOKEN`
- `HF_API_KEY`
- `HF_API_SECRET` (или `HF_KEY`)

Рекомендуемые параметры:

- `HF_MODEL_ID=higgsfield-ai/dop/standard`
- `HF_PROMPT=Earth zoom in`
- `HF_ASPECT_RATIO=16:9`
- `HF_DURATION_SECONDS=15`
- `HF_POLL_INTERVAL_SECONDS=6`
- `HF_MAX_WAIT_SECONDS=300`
- `HF_HTTP_TIMEOUT_SECONDS=60`

## 4) Что проверяет preflight

- валидность Telegram token через `getMe`;
- авторизацию Higgsfield через `requests/{id}/status`.

Если `preflight` возвращает `FAIL`, запускать прод-демо не рекомендуется.

## 5) Демо-видео для заказчика

Для записи используйте сценарий из `docs/VIDEO_RECORDING_GUIDE.md`.

Минимальный обязательный набор кадров:

1. `/start` и кнопка `Создать видео`;
2. отправка фото;
3. живое обновление статуса;
4. приход итогового видео;
5. негативный кейс (не фото).

## 6) Частые проблемы

- `401 Unauthorized` -> неверные HF credentials.
- timeout на Telegram/Higgsfield -> сетевые ограничения на хосте.
- `completed`, но без `video.url` -> нестандартный ответ модели, нужен разбор payload.
