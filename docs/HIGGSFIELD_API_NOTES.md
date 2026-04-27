# Higgsfield Platform API — полевые заметки

Всё ниже — результат реального зондирования `platform.higgsfield.ai` из этого проекта + чтения официального SDK `higgsfield-ai/higgsfield-js` (commit на HEAD). Использовать только с валидными `HF_API_KEY:HF_API_SECRET`.

## 1) Авторизация

```
Authorization: Key {HF_API_KEY}:{HF_API_SECRET}
```

Получить ключи: https://cloud.higgsfield.ai/ → Settings → API Keys.

## 2) Ключевые endpoints

| Метод | URL | Назначение |
|-------|-----|------------|
| POST  | `/files/generate-upload-url` | Пресайн S3-подобной заливки. Возвращает `public_url` и `upload_url`. Потом PUT байт по `upload_url`. |
| GET   | `/v1/motions` | Список camera-motion пресетов. У каждого: `id` (UUID), `name`, `description`, `preview_url`, `start_end_frame`. |
| POST  | `/v1/image2video/dop` | Image-to-video (DoP) — каноничный endpoint SDK. |
| POST  | `/v1/text2image/soul` | Soul text-to-image. |
| GET   | `/requests/{id}/status` | Статус любой задачи (video/image). |

## 3) POST /v1/image2video/dop — точная схема

Тело **обёрнуто** в `params`:

```json
{
  "params": {
    "model": "dop-lite" | "dop-preview" | "dop-turbo",
    "prompt": "…",
    "input_images":      [{"type":"image_url","image_url":"https://…"}],
    "input_images_end":  [{"type":"image_url","image_url":"https://…"}],  // optional
    "motions": [{"id":"<uuid>","strength": 0.0..1.0}],
    "duration": 1..15,
    "enhance_prompt": false,
    "seed": 0..1000000
  }
}
```

Важные гвозди, выяснённые зондированием:

* `model` **не принимает** `dop-standard` на этом маршруте (`/v1/image2video/dop`). Доступны **только** `dop-lite`, `dop-preview`, `dop-turbo`. `dop-preview` — это «HQ»-уровень на этом endpoint (эквивалент `standard` с другого роутинга).
* `input_images` **max_length = 1**. Второй кадр (end_frame) передаётся отдельным полем `input_images_end` (тоже массив длиной 1).
* `motions[0].strength` **≤ 1.0**. Выше — 422. Рекомендуемое: 0.7–0.85 для минимальной деформации лица.
* Motion preset с флагом `start_end_frame: true` (например, Earth Zoom Out, UUID `46fa79e3-efce-41e8-95bc-1dc5a1a30795`) **интерполирует start → end** — это и есть механика «Earth Zoom In» в web UI Higgsfield (подаёшь start=Earth, end=face — камера «летит из космоса» и заканчивается на лице).

Response от POST:

```json
{
  "id": "<request_id>",
  "type": "image2video",
  "created_at": "...",
  "jobs": [{"id":"...","status":"queued","results":null}],
  "input_params": { ... эхо params ... }
}
```

Poll через `GET /requests/{id}/status`. Финальный payload:

```json
{
  "status": "completed",
  "request_id": "...",
  "video": { "url": "https://cloud-cdn.higgsfield.ai/…/x.mp4" }
}
```

Статусы: `queued`, `in_progress`, `completed`, `failed`, `nsfw`, `canceled`.

## 4) POST /v1/text2image/soul — схема

```json
{
  "params": {
    "prompt": "…",
    "width_and_height": "2048x1152" | "1152x2048" | "2048x1536" | "1536x2048" |
                       "1344x2016" | "2016x1344" | "960x1696" | "1696x960" |
                       "1152x1536" | "1536x1152" | "1088x1632" | "1632x1088" |
                       "1120x1680" | "1680x1120" | "1536x1536" | "2048x2048",
    "quality": "720p" | "1080p",
    "batch_size": 1 | 4,
    "enhance_prompt": true,
    "seed": 0..1000000
  }
}
```

Для **16:9** используется `2048x1152`. Для вертикального 9:16 — `1152x2048`. Точного `1280x720` нет — используется `2048x1152` и потом уменьшается на клиенте.

Финальный payload содержит `images: [{"url":"…"}]` или `image: {"url":"…"}`.

## 5) Как извлечь «промпт пресета»

**Нельзя.** Публично не отдаётся ни через `/v1/motions`, ни через `/requests/{id}/status`, ни через SDK. Преcет — это UUID камера-паттерна + возможно скрытые параметры на стороне сервера. Единственное публично доступное текстовое описание — поле `description` в `/v1/motions`, но оно маркетинговое, не технический prompt.

Способы приблизиться 1-в-1:

1. **Использовать сам пресет** (`motions:[{id}]`) — тогда «кинематика» заложена внутри.
2. **Дополнить prompt'ом**, описывающим *содержимое* (а не камеру): контекст, освещение, действия субъекта, сохранение лица.
3. Для дуал-кадра (`start_end_frame: true`) подавать оба `input_images` + `input_images_end` — камера интерполирует, а фиксированный end_frame гарантирует 1-в-1 лицо из референса.
4. `enhance_prompt: true` — эквивалент «Optimize Prompt» в UI (встроенный LLM-экспандер). Можно использовать для коротких prompt'ов.

## 6) Face preservation — практические правила

* Всегда подавать фото лица как **end_frame**, а не как единственный input — тогда последний кадр фиксирован.
* `motion_strength` 0.7–0.85. 1.0 даёт больше кинематики, но иногда деформирует.
* 16:9 (1280×720 или 2048×1152) — меньше артефактов на вертикальных лицах.
* Duration 5 сек — меньше «морфинга» между кадрами, чем 15.
* `enhance_prompt: false`, если промпт уже подробный и содержит явное требование "identity preserved / no morphing".

## 7) Подтверждённая визуальная проверка (2026-04-20)

Смоук на тестовой паре start=(20,30,80) / end=(200,200,220):
* первый кадр видео — mean RGB ≈ (50,55,98) — совпало со start;
* последний кадр — mean RGB ≈ (196,199,215) — совпало с end.

Это доказывает: сервер действительно использует `input_images_end`, и направление движения — **start → end** (т.е. Earth → face = Earth Zoom IN, как в web UI).
