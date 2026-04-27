# GitHub + VPS: бот без привязки к ноутбуку

Код лежит в **GitHub**. Круглосуточный бот крутится на **VPS** (США/Европа), а не на вашем ПК.

## 1. Репозиторий на GitHub

1. Создайте пустой репозиторий на [github.com/new](https://github.com/new) (без README, если уже есть локальный коммит).

2. Локально (в папке проекта):

```bash
git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
git branch -M main
git push -u origin main
```

Замените `YOUR_USER/YOUR_REPO` на свои имя и репозиторий.

## 2. VPS: Docker (рекомендуется)

На сервере с **Ubuntu 22.04+** (Hetzner, DigitalOcean, AWS и т.д.):

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER   # перелогиньтесь
git clone https://github.com/YOUR_USER/YOUR_REPO.git
cd YOUR_REPO
cp .env.example .env
nano .env   # TELEGRAM_BOT_TOKEN, HF_API_KEY, HF_API_SECRET
docker compose up -d --build
docker compose logs -f
```

Секреты **только** в `.env` на сервере. Файл `.env` в репозиторий **не** коммитится.

## 3. Переменные окружения

См. `.env.example`. Обязательно:

- `TELEGRAM_BOT_TOKEN` — у [@BotFather](https://t.me/BotFather)
- `HF_API_KEY`, `HF_API_SECRET` — [Higgsfield Cloud](https://cloud.higgsfield.ai/)

На VPS обычно **не** нужен `TELEGRAM_PROXY` (прямой доступ к `api.telegram.org`).

## 4. CI в GitHub

При каждом push в `main` / `master` workflow **CI** запускает `pytest`. Это проверяет код, но **не** поднимает бота — бот всё равно на VPS.

## 5. Обновление бота после `git push`

На сервере:

```bash
cd YOUR_REPO
git pull
docker compose up -d --build
```

## 6. Один инстанс бота

Не запускайте **два** процесса с одним `TELEGRAM_BOT_TOKEN` (ноут + VPS) — будет `Conflict: getUpdates`. Остановите локальный `python -m src.bot` перед деплоем на VPS.
