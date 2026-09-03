"""
api/app.py — FastAPI application factory.

Creates and configures the FastAPI application instance, registers routers,
and wires startup/shutdown lifecycle hooks to the ProcessSupervisor.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import health as health_router
from api.routers import system as system_router
from core.settings import settings

logger = logging.getLogger(__name__)

_APP_DESCRIPTION = """
## AIO Media Server Manager API

Manages the lifecycle of your self-hosted media stack without relying on
individual Docker containers for each application.

### Quick links
- **[Health](/health)** — Service health check
- **[System info](/api/system/info)** — Paths, permissions, process status
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
    )

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
    app.include_router(system_router.router)

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
