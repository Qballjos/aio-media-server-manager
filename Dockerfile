# syntax=docker/dockerfile:1
# Single AIO appliance image — all apps run as supervised processes inside this container.

FROM node:24-alpine AS frontend
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
COPY logo-aio-media-manager.png ./public/logo-aio-media-manager.png
RUN npm run build

FROM node:24-bookworm-slim AS nodebin

FROM eclipse-temurin:25-jre-noble AS jre

FROM python:3.13-slim-bookworm AS py313

FROM python:3.14-slim-bookworm
ARG TARGETARCH
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    AMM_CONFIG_DIR=/config \
    AMM_DOWNLOAD_DIR=/data/downloads \
    AMM_MEDIA_DIR=/data/media \
    AMM_API_HOST=0.0.0.0 \
    AMM_API_PORT=8080 \
    JAVA_HOME=/opt/java \
    AMM_CHILD_PYTHON=/usr/local/bin/python3.13 \
    PATH="/opt/java/bin:${PATH}"

COPY --from=jre /opt/java/openjdk /opt/java
COPY --from=py313 /usr/local /opt/python3.13
COPY --from=nodebin /usr/local/bin/node /usr/local/bin/node
COPY --from=nodebin /usr/local/lib/node_modules /usr/local/lib/node_modules

RUN printf '%s\n' \
        '#!/bin/sh' \
        'export LD_LIBRARY_PATH=/opt/python3.13/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}' \
        'exec /opt/python3.13/bin/python3.13 "$@"' \
        > /usr/local/bin/python3.13 \
    && chmod +x /usr/local/bin/python3.13

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
        libxslt1.1 \
        libjpeg62-turbo \
        libncurses6 \
        libfontconfig1 \
        fonts-liberation \
        chromium \
        xvfb \
        mariadb-server \
        unrar-free \
        par2 \
        p7zip-full \
        build-essential \
        python3-dev \
        ${ICU_PKG} \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && ln -sf /usr/local/lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack \
    && corepack enable

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

VOLUME ["/config", "/data", "/downloads", "/media"]
EXPOSE 8080
CMD ["python", "main.py"]
