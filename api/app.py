"""
api/app.py — FastAPI application factory.

Creates and configures the FastAPI application instance, registers routers,
and wires startup/shutdown lifecycle hooks to the ProcessSupervisor.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pathlib import Path
from fastapi.staticfiles import StaticFiles

from api.routers import applications as applications_router
from api.routers import auth as auth_router
from api.routers import backups as backups_router
from api.routers import catalog as catalog_router
from api.routers import health as health_router
from api.routers import integrations as integrations_router
from api.routers import logs as logs_router
from api.routers import system as system_router
from api.routers import wizard as wizard_router
from api.routers import vpn as vpn_router
from core.settings import settings

logger = logging.getLogger(__name__)

_APP_DESCRIPTION = """
## AIO Media Server Manager API

Manages the lifecycle of your self-hosted media stack without relying on
individual Docker containers for each application.

### Quick links
- **[Health](/health)** — Service health check
- **[Auth](/api/auth/status)** — Session status and setup
- **[Catalog](/api/catalog)** — Available applications and ports
- **[Applications](/api/applications)** — Process status and lifecycle
- **[System info](/api/system/info)** — Paths, permissions, system status
"""


def create_app() -> FastAPI:
    """Construct and return the FastAPI application."""

    app = FastAPI(
        title="AIO Media Server Manager",
        description=_APP_DESCRIPTION,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        root_path=settings.root_path or "",
    )

    trusted = [item.strip() for item in settings.trusted_proxies.split(",") if item.strip()]
    if trusted:
        from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

        hosts = "*" if "*" in trusted else trusted
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=hosts)

    # ------------------------------------------------------------------
    # CORS — allow all origins in development; tighten in production.
    # ------------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Routers
    # ------------------------------------------------------------------
    app.include_router(health_router.router)
    app.include_router(auth_router.router)
    app.include_router(catalog_router.router)
    app.include_router(applications_router.router)
    app.include_router(integrations_router.router)
    app.include_router(logs_router.router)
    app.include_router(system_router.router)
    app.include_router(wizard_router.router)
    app.include_router(backups_router.router)
    app.include_router(vpn_router.router)

    # Mount frontend dist if built
    frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    @app.on_event("startup")
    async def on_startup() -> None:
        logger.info(
            "FastAPI application starting on %s:%d",
            settings.api_host,
            settings.api_port,
        )

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        logger.info("FastAPI application shutting down.")

    return app


# Module-level singleton used by uvicorn
app = create_app()
