# Как подключить Higgsfield credentials

## Важно

Для работы API нужны credentials в формате `key_id:key_secret` или пара `HF_API_KEY` + `HF_API_SECRET`.
Email/пароль от веб-кабинета сам по себе не используется напрямую в заголовке API.
Автоматически "сгенерировать" API ключ только по email/паролю через этот MVP нельзя: ключи создаются в кабинете Higgsfield Cloud.

См. официальные источники:

- [How to use API](https://docs.higgsfield.ai/how-to/introduction)
- [Client libraries](https://docs.higgsfield.ai/how-to/sdk)

## Шаги

1. Зайдите в Higgsfield Cloud.
2. Получите API credentials.
3. Откройте `.env` и задайте:

```env
HF_API_KEY=...
HF_API_SECRET=...
```

или

```env
HF_KEY=key_id:key_secret
```

4. Проверьте, что выбран корректный `HF_MODEL_ID` (в MVP используется `higgsfield-ai/dop/standard`).
5. Выполните preflight:

```bash
python -m src.preflight
```

6. Перезапустите бота.

## Диагностика

- `401 Unauthorized`: неверные ключи или отозванный доступ.
- `429`: превышены лимиты/квоты.
- `5xx`: временная ошибка провайдера, повторите позже.
