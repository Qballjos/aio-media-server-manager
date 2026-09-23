# syntax=docker/dockerfile:1
# Single AIO appliance image — all apps run as supervised processes inside this container.

FROM node:25-alpine AS frontend
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    AMM_CONFIG_DIR=/config \
    AMM_DOWNLOAD_DIR=/downloads \
    AMM_MEDIA_DIR=/media \
    AMM_API_HOST=0.0.0.0 \
    AMM_API_PORT=8080

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        iproute2 \
        openvpn \
        wireguard-tools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN pip install --no-cache-dir poetry \
    && poetry install --only main --no-interaction --no-ansi --no-root

COPY core ./core
COPY api ./api
COPY applications ./applications
COPY main.py ./
COPY --from=frontend /ui/dist ./frontend/dist

VOLUME ["/config", "/downloads", "/media"]
EXPOSE 8080
CMD ["python", "main.py"]
