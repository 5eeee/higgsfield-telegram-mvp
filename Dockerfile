# Run the Telegram bot on any VPS (US/EU) — no dependency on a dev laptop.
FROM python:3.11-slim

WORKDIR /app

# ffmpeg: optional but improves reverse-video when imageio path is not enough
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Long polling: one process, no port exposed
CMD ["python", "-m", "src.bot"]
