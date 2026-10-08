# syntax=docker/dockerfile:1
# Single AIO appliance image — all apps run as supervised processes inside this container.

# Vue dist is JS/CSS. Build it on the builder CPU, not under QEMU, or
# `npm ci` on linux/arm64 hangs for a long time on GitHub-hosted amd64 runners.
FROM --platform=$BUILDPLATFORM node:22-alpine AS frontend
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
COPY logo-aio-media-manager.png ./public/logo-aio-media-manager.png
RUN npm run build

FROM node:22-bookworm-slim AS nodebin

FROM eclipse-temurin:25-jre-noble AS jre

FROM python:3.13-slim-bookworm AS py313

# Userspace WireGuard for NAS kernels that have no wireguard module (typical on Synology).
# wg-quick falls back to this binary when `ip link add type wireguard` fails (exit 127 otherwise).
FROM --platform=$BUILDPLATFORM golang:1.25-bookworm AS wggo
ARG TARGETOS
ARG TARGETARCH
WORKDIR /src
# 0.0.20230223 fails on Go 1.23: golang.org/x/net still calls syscall.recvmsg.
RUN git -c advice.detachedHead=false clone --depth 1 --branch 0.0.20250522 https://github.com/WireGuard/wireguard-go.git . \
    && CGO_ENABLED=0 GOOS=${TARGETOS:-linux} GOARCH=${TARGETARCH:-amd64} \
        go build -trimpath -ldflags="-s -w" -o /wireguard-go .

FROM python:3.14-slim-bookworm
ARG TARGETARCH
ARG AMM_VERSION=0.1.0
ARG AMM_GIT_SHA=
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    POETRY_VIRTUALENVS_CREATE=false \
    AMM_CONFIG_DIR=/config \
    AMM_DOWNLOAD_DIR=/data/downloads \
    AMM_MEDIA_DIR=/data/media \
    AMM_API_HOST=0.0.0.0 \
    AMM_API_PORT=8080 \
    JAVA_HOME=/opt/java \
    AMM_CHILD_PYTHON=/usr/local/bin/python3.13 \
    AMM_VERSION=${AMM_VERSION} \
    AMM_GIT_SHA=${AMM_GIT_SHA} \
    PATH="/opt/java/bin:${PATH}" \
    WG_QUICK_USERSPACE_IMPLEMENTATION=/usr/bin/wireguard-go

COPY --from=jre /opt/java/openjdk /opt/java
COPY --from=py313 /usr/local /opt/python3.13
COPY --from=nodebin /usr/local/bin/node /usr/local/bin/node
COPY --from=nodebin /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=wggo /wireguard-go /usr/bin/wireguard-go

RUN printf '%s\n' \
        '#!/bin/sh' \
        'export LD_LIBRARY_PATH=/opt/python3.13/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}' \
        'exec /opt/python3.13/bin/python3.13 "$@"' \
        > /usr/local/bin/python3.13 \
    && chmod +x /usr/local/bin/python3.13

# Host packages vs catalog (both linux/amd64 and linux/arm64 unless noted):
#   *Arr/.NET (Sonarr, Radarr, Lidarr, Prowlarr, NeutArr, Recyclarr):
#     libicu*, libssl3, libgssapi-krb5-2, zlib1g, libsqlite3-0, sqlite3
#   SABnzbd / NZBGet: unrar (non-free RAR 5), par2cmdline-turbo, p7zip-full, python3.13, build-essential
#   Bazarr / Shelfmark / NeutArr (venv wheels): libxml2, libxslt1.1, libjpeg62-turbo,
#     libncurses6, python3.13, python3-dev, build-essential
#   Jellyfin / Plex: ffmpeg, libfontconfig1
#   Seerr: Node 22 (copied from nodebin)
#   Grimmory: JRE 25 (copied from jre), mariadb-server
#   Flaresolverr (x86_64 / amd64 image only): chromium, xvfb, fonts-liberation
#   Recyclarr: git (clones TRaSH Guides on sync)
#   VPN: iproute2, openvpn, wireguard-tools, iptables, wireguard-go (userspace fallback)
# Catalog app installs use GitHub zipballs/releases; Recyclarr still shells out to git.
# Official `unrar` lives in Debian non-free; unrar-free reports version 0.00 to SABnzbd.
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's/Components: main/Components: main contrib non-free non-free-firmware/' /etc/apt/sources.list.d/debian.sources; \
    else \
        echo "deb http://deb.debian.org/debian bookworm non-free non-free-firmware" > /etc/apt/sources.list.d/non-free.list; \
    fi \
    && apt-get update \
    && ICU_PKG=$(apt-cache search --names-only '^libicu[0-9]+$' | awk '{print $1}' | sort -V | tail -1) \
    && EXTRA="" \
    && if [ "${TARGETARCH:-amd64}" = "amd64" ]; then \
         EXTRA="fonts-liberation chromium xvfb"; \
       fi \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        ffmpeg \
        iproute2 \
        util-linux \
        acl \
        openvpn \
        wireguard-tools \
        iptables \
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
        mariadb-server \
        unrar \
        p7zip-full \
        build-essential \
        python3-dev \
        ${ICU_PKG} \
        ${EXTRA} \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && ln -sf /usr/local/lib/node_modules/corepack/dist/corepack.js /usr/local/bin/corepack \
    && corepack enable \
    && chmod +x /usr/bin/wireguard-go \
    && groupadd -g 910 ammvpn \
    && useradd -u 910 -g 910 -M -d /tmp/ammvpn -s /usr/sbin/nologin ammvpn \
    && mkdir -p /tmp/ammvpn \
    && chown 910:910 /tmp/ammvpn

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

# Faster SABnzbd/NZBGet PAR2 verify+repair (drop-in replacement for Debian par2).
# https://sabnzbd.org/wiki/installation/par2cmdline-turbo
ARG PAR2_TURBO_VERSION=1.4.0
RUN set -eux; \
    case "${TARGETARCH:-amd64}" in \
      amd64) par2arch=amd64 ;; \
      arm64) par2arch=arm64 ;; \
      arm) par2arch=armhf ;; \
      *) par2arch=amd64 ;; \
    esac; \
    curl -fsSL "https://github.com/animetosho/par2cmdline-turbo/releases/download/v${PAR2_TURBO_VERSION}/par2cmdline-turbo-${PAR2_TURBO_VERSION}-linux-${par2arch}.zip" \
      -o /tmp/par2cmdline-turbo.zip; \
    python -m zipfile -e /tmp/par2cmdline-turbo.zip /tmp/par2cmdline-turbo; \
    install -m 0755 /tmp/par2cmdline-turbo/par2 /usr/local/bin/par2; \
    ln -sfn /usr/local/bin/par2 /usr/bin/par2; \
    rm -rf /tmp/par2cmdline-turbo.zip /tmp/par2cmdline-turbo; \
    par2 --version

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
