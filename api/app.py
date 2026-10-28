"""FastAPI application factory: routers, proxy headers, and lifecycle hooks."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from api.routers import applications as applications_router
from api.routers import auth as auth_router
from api.routers import backups as backups_router
from api.routers import branding as branding_router
from api.routers import catalog as catalog_router
from api.routers import downloads as downloads_router
from api.routers import diagnostics as diagnostics_router
from api.routers import health as health_router
from api.routers import homepage as homepage_router
from api.routers import integrations as integrations_router
from api.routers import logs as logs_router
from api.routers import notifications as notifications_router
from api.routers import recyclarr as recyclarr_router
from api.routers import settings as settings_router
from api.routers import system as system_router
from api.routers import updates as updates_router
from api.routers import usenet as usenet_router
from api.routers import wizard as wizard_router
from api.routers import vpn as vpn_router
from api.routers import cloudflare_hostnames as cloudflare_hostnames_router
from api.routers import cloudflare_tunnel as cloudflare_tunnel_router
from core import branding as branding_mod
from core.settings import settings
from core.version import app_version

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
        from core.diagnostics import diagnostics

        diagnostics.install_logging_hook()
        # uvicorn serves nothing until lifespan yields; boot apps in the background so the
        # dashboard is reachable while the VPN handshakes and apps come up.
        boot = asyncio.create_task(_boot_apps(), name="aio-boot")
        yield
        if not boot.done():
            boot.cancel()
        logger.info("FastAPI application shutting down.")

    async def _boot_apps() -> None:
        started_all: list = []
        try:
            started_all = await _boot_apps_in_order()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("App boot failed; start apps from the dashboard.")
        from core.integrations.lifecycle import vpn_isolation_loop
        from core.update_schedule import scheduler_loop

        from core.downloads_pause import resume_when_due_loop
        from core.notifications import notifications_loop

        asyncio.create_task(vpn_isolation_loop())
        asyncio.create_task(scheduler_loop())
        asyncio.create_task(resume_when_due_loop())
        asyncio.create_task(notifications_loop())
        if settings.cloudflare_tunnel_enabled:
            from core.integrations.lifecycle import start_cloudflare_tunnel_last

            asyncio.create_task(start_cloudflare_tunnel_last(started_all))

    async def _boot_apps_in_order() -> list:
        # Boot order: the VPN, then FlareSolverr, qBittorrent, SABnzbd, then the rest, Cloudflare last.
        from core.app_prefs import autostart_for
        from applications.catalog import ApplicationCatalog
        from core.supervisor import ProcessSupervisor
        from core.vpn import VPN_TUNNELED_APPS, VpnIsolationError, vpn_manager

        if settings.vpn_enabled:
            result = await asyncio.to_thread(vpn_manager.start)
            if result.get("status") == "error" or not result.get("tunnel_up"):
                logger.warning(
                    "VPN did not come up; qBittorrent, Prowlarr, and FlareSolverr wait for the tunnel. %s",
                    result.get("detail") or result.get("status"),
                )
                from core.integrations.lifecycle import enforce_vpn_isolation

                await enforce_vpn_isolation()

        supervisor = ProcessSupervisor.get()
        boot_catalog = ApplicationCatalog()
        from core.integrations.lifecycle import (
            _LISTEN_BEFORE_ARR,
            _wait_listeners,
            boot_autostart_order,
            hold_for_tunnel,
        )

        pending = []
        held: list[str] = []
        for plugin in boot_catalog.all_plugins():
            if not plugin.manifest.daemon or not plugin.is_installed():
                continue
            if not plugin.supports_current_arch():
                logger.info(
                    "Autostart skipped for '%s': no build for this CPU architecture.",
                    plugin.name,
                )
                continue
            if not autostart_for(plugin.name, default=True):
                continue
            if plugin.name in VPN_TUNNELED_APPS:
                try:
                    await asyncio.to_thread(vpn_manager.assert_can_start_tunneled_app, plugin.name)
                except VpnIsolationError:
                    held.append(plugin.name)
                    continue
            pending.append(plugin)
        if held:
            logger.warning("%s will start once the VPN tunnel is up.", ", ".join(held))
            hold_for_tunnel(held)
        by_name = {plugin.name: plugin for plugin in pending}
        ordered = [by_name[name] for name in boot_autostart_order([plugin.name for plugin in pending])]
        started = False
        started_all: list = []
        phase = 0
        started_phase: list = []
        for plugin in ordered:
            if plugin.name in _LISTEN_BEFORE_ARR:
                plugin_phase = 0
            elif plugin.name == "prowlarr":
                plugin_phase = 1
            else:
                plugin_phase = 2
            if plugin_phase > phase and started_phase:
                await _wait_listeners(started_phase)
                started_phase = []
            phase = plugin_phase
            try:
                await supervisor.start(
                    name=plugin.name,
                    cmd=plugin.start_command(),
                    cwd=plugin.working_directory(),
                    env=plugin.extra_env(),
                    log_dir=settings.config_dir / "logs",
                )
                started = True
                started_all.append(plugin)
                if plugin_phase < 2:
                    started_phase.append(plugin)
            except Exception as err:
                logger.warning("Autostart skipped for %s: %s", plugin.name, err)
        if started:
            from core.integrations.lifecycle import schedule_full_wiring

            asyncio.create_task(schedule_full_wiring(wait_for_apps=True))
        return started_all

    app = FastAPI(
        title="AIO Media Server Manager",
        description=_APP_DESCRIPTION,
        version=app_version(),
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
    app.include_router(downloads_router.router)
    app.include_router(auth_router.router)
    app.include_router(catalog_router.router)
    app.include_router(applications_router.router)
    app.include_router(recyclarr_router.router)
    app.include_router(integrations_router.router)
    app.include_router(logs_router.router)
    app.include_router(system_router.router)
    app.include_router(settings_router.router)
    app.include_router(branding_router.router)
    app.include_router(updates_router.router)
    app.include_router(usenet_router.router)
    app.include_router(wizard_router.router)
    app.include_router(backups_router.router)
    app.include_router(vpn_router.router)
    app.include_router(cloudflare_tunnel_router.router)
    app.include_router(cloudflare_hostnames_router.router)
    app.include_router(diagnostics_router.router)
    app.include_router(notifications_router.router)

    @app.middleware("http")
    async def _no_cache_spa_shell(request, call_next):
        """Keep index.html fresh so browsers pick up new hashed JS after updates."""
        response = await call_next(request)
        path = request.url.path or "/"
        content_type = response.headers.get("content-type", "")
        if path == "/" or path.endswith(".html") or "text/html" in content_type:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon_ico():
        # Safari requests this before it trusts a <link rel="icon">, and it will not follow a redirect.
        payload = branding_mod.favicon_ico()
        if payload is None:
            raise HTTPException(status_code=404, detail="Favicon is not available.")
        body, media_type = payload
        return Response(content=body, media_type=media_type, headers={"Cache-Control": "public, max-age=3600"})

    # Mount frontend dist if built
    frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

    return app


# Module-level singleton used by uvicorn
app = create_app()
