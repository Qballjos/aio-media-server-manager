"""
api/routers/catalog.py — Application Catalog & Port Management Endpoints

Lists available applications, port allocations, dependencies, and triggers installs.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from applications.catalog import ApplicationCatalog
from core.auth import auth_manager
from core.installer.arch import detect_system_arch
from core.integrations.lifecycle import finalize_application_install
from core.port_manager import PortManager
from core.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/catalog", tags=["Catalog"])

catalog = ApplicationCatalog(app_settings=settings)
port_manager = PortManager(app_settings=settings)


def _ensure_authenticated(request: Request) -> None:
    if not auth_manager.setup_required():
        auth_manager.authenticate_request(request)


@router.get("", summary="List application catalog")
async def list_catalog(request: Request) -> dict[str, Any]:
    """
    Returns the application catalog categorized by tier and category,
    including installation status, port, and architecture compatibility.
    """
    _ensure_authenticated(request)
    arch = detect_system_arch().value
    entries = catalog.entries()

    return {
        "host_architecture": arch,
        "applications": entries,
        "by_tier": catalog.by_tier(),
        "counts": catalog.counts(entries),
    }


@router.get("/ports", summary="List port allocations")
async def list_ports(request: Request) -> dict[str, Any]:
    """
    Returns active port allocations, collision checks, and suggested alternates.
    """
    _ensure_authenticated(request)
    for plugin in catalog.all_plugins():
        port_manager.register(plugin.name, plugin.port)
    allocations = []
    for plugin in catalog.all_plugins():
        alloc = port_manager.inspect(plugin.name, plugin.manifest.default_port)
        allocations.append(
            {
                "app_name": alloc.app_name,
                "port": alloc.port,
                "default_port": alloc.default_port,
                "in_use": alloc.in_use,
                "conflict": alloc.conflict,
                "suggested_port": alloc.suggested_port,
            }
        )

    return {
        "api_port": settings.api_port,
        "allocations": allocations,
    }


@router.get("/{name}", summary="Get application details")
async def get_application_details(name: str, request: Request) -> dict[str, Any]:
    """
    Returns manifest and status details for a specific application.
    """
    _ensure_authenticated(request)
    try:
        plugin = catalog.get(name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return plugin.catalog_entry()


@router.post("/{name}/install", summary="Install an application")
async def install_application(
    name: str,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """
    Triggers installation of the application in the background.
    """
    _ensure_authenticated(request)
    try:
        plugin = catalog.get(name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    if plugin.is_installed():
        return {
            "status": "already_installed",
            "message": f"Application '{name}' is already installed.",
            "version": plugin.installed_metadata().get("version"),
        }

    from core.diagnostics import diagnostics
    from core.maintenance import begin_install, end_install

    async def _do_install():
        begin_install()
        try:
            logger.info("Starting background install for '%s'...", name)
            plugin.install()
            logger.info("Background install for '%s' completed successfully.", name)
            try:
                await finalize_application_install(plugin)
            except Exception as err:
                logger.error("Post-install wiring failed for '%s': %s", name, err, exc_info=True)
        except Exception as err:
            logger.error("Failed to install '%s': %s", name, err, exc_info=True)

            diagnostics.record_exception(err, source=f"install:{name}")
        finally:
            end_install()

    background_tasks.add_task(_do_install)

    return {
        "status": "installing",
        "message": f"Installation started for '{plugin.manifest.display_name}'.",
    }
