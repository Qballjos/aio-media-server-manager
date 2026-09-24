"""FastAPI application factory: routers, proxy headers, and lifecycle hooks."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routers import applications as applications_router
from api.routers import auth as auth_router
from api.routers import backups as backups_router
from api.routers import catalog as catalog_router
from api.routers import diagnostics as diagnostics_router
from api.routers import health as health_router
from api.routers import homepage as homepage_router
from api.routers import integrations as integrations_router
from api.routers import logs as logs_router
from api.routers import settings as settings_router
from api.routers import system as system_router
from api.routers import updates as updates_router
from api.routers import wizard as wizard_router
from api.routers import vpn as vpn_router
from api.routers import cloudflare_tunnel as cloudflare_tunnel_router
from core.settings import settings

logger = logging.getLogger(__name__)

_APP_DESCRIPTION = """
## AIO Media Server Manager API

Manages the lifecycle of your self-hosted media stack without relying on
individual Docker containers for each application.

### Quick links
- **[Health](/health)** — Service health check
- **[Auth](/api/auth/status)** — Session status and setup
- **[Homepage](/api/homepage)** — Household launcher and widgets
- **[Catalog](/api/catalog)** — Available applications and ports
- **[Applications](/api/applications)** — Process status and lifecycle
- **[System info](/api/system/info)** — Paths, permissions, system status
"""


def create_app() -> FastAPI:
    """Construct and return the FastAPI application."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        logger.info(
            "FastAPI application starting on %s:%d",
            settings.api_host,
            settings.api_port,
        )
        if settings.cloudflare_tunnel_enabled:
            from core.cloudflare_tunnel import cloudflare_tunnel

            result = await cloudflare_tunnel.start()
            if result.get("status") == "error":
                logger.warning("Cloudflare Tunnel did not start: %s", result.get("detail"))
        from core.diagnostics import diagnostics

        diagnostics.install_logging_hook()
        from core.app_prefs import autostart_for
        from applications.catalog import ApplicationCatalog
        from core.supervisor import ProcessSupervisor

        supervisor = ProcessSupervisor.get()
        boot_catalog = ApplicationCatalog()
        started = False
        for plugin in boot_catalog.all_plugins():
            if not plugin.manifest.daemon or not plugin.is_installed():
                continue
            if not autostart_for(plugin.name, default=True):
                continue
            try:
                await supervisor.start(
                    name=plugin.name,
                    cmd=plugin.start_command(),
                    cwd=plugin.working_directory(),
                    env=plugin.extra_env(),
                    log_dir=settings.config_dir / "logs",
                )
                started = True
            except Exception as err:
                logger.warning("Autostart skipped for %s: %s", plugin.name, err)
        if started:
            from core.integrations.lifecycle import schedule_full_wiring

            asyncio.create_task(schedule_full_wiring())
        from core.update_schedule import scheduler_loop

        asyncio.create_task(scheduler_loop())
        yield
        logger.info("FastAPI application shutting down.")

    app = FastAPI(
        title="AIO Media Server Manager",
        description=_APP_DESCRIPTION,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        root_path=settings.root_path or "",
        lifespan=lifespan,
    )

    trusted = [item.strip() for item in settings.trusted_proxies.split(",") if item.strip()]
    if settings.cloudflare_tunnel_enabled and "127.0.0.1" not in trusted:
        trusted.append("127.0.0.1")
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
    app.include_router(homepage_router.router)
    app.include_router(auth_router.router)
    app.include_router(catalog_router.router)
    app.include_router(applications_router.router)
    app.include_router(integrations_router.router)
    app.include_router(logs_router.router)
    app.include_router(system_router.router)
    app.include_router(settings_router.router)
    app.include_router(updates_router.router)
    app.include_router(wizard_router.router)
    app.include_router(backups_router.router)
    app.include_router(vpn_router.router)
    app.include_router(cloudflare_tunnel_router.router)
    app.include_router(diagnostics_router.router)

    # Mount frontend dist if built
    frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

    return app


# Module-level singleton used by uvicorn
app = create_app()
