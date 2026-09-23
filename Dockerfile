# syntax=docker/dockerfile:1
# Single AIO appliance image — all apps run as supervised processes inside this container.

FROM node:22-alpine AS frontend
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
COPY logo-aio-media-manager.png ./public/logo-aio-media-manager.png
RUN npm run build

FROM python:3.14-slim-bookworm
ARG TARGETARCH
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    AMM_CONFIG_DIR=/config \
    AMM_DOWNLOAD_DIR=/downloads \
    AMM_MEDIA_DIR=/media \
    AMM_API_HOST=0.0.0.0 \
    AMM_API_PORT=8080

# Servarr/.NET self-contained builds need ICU, OpenSSL, and SQLite from the OS.
RUN apt-get update \
    && ICU_PKG=$(apt-cache search --names-only '^libicu[0-9]+$' | awk '{print $1}' | sort -V | tail -1) \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        iproute2 \
        openvpn \
        wireguard-tools \
        libssl3 \
        libgssapi-krb5-2 \
        zlib1g \
        libsqlite3-0 \
        sqlite3 \
        libxml2 \
        libncurses6 \
        libfontconfig1 \
        ${ICU_PKG} \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "${TARGETARCH:-amd64}" in \
      amd64) cfarch=amd64 ;; \
      arm64) cfarch=arm64 ;; \
      arm) cfarch=arm ;; \
      *) cfarch=amd64 ;; \
    esac; \
    curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${cfarch}" \
      -o /usr/local/bin/cloudflared; \
    chmod +x /usr/local/bin/cloudflared; \
    cloudflared --version

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
