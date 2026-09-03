"""
main.py — AIO Media Server Manager entrypoint

Startup sequence:
  1. Configure logging
  2. Load and validate settings
  3. Create standard directory layout and validate storage
  4. Start the FastAPI server via uvicorn (in a background thread)
  5. Enter the asyncio event loop (keeps the supervisor alive)

Usage
-----
    python main.py
    # or
    uvicorn api.app:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading

import uvicorn

from core.logging_config import configure_logging
from core.settings import settings
from core.storage import StorageManager
from core.supervisor import ProcessSupervisor

# ---------------------------------------------------------------------------
# Logging must be configured before importing anything that uses it
# ---------------------------------------------------------------------------
configure_logging(
    level=settings.log_level,
    log_dir=settings.config_dir / "logs",
)

logger = logging.getLogger(__name__)

_BANNER = r"""
  ___  ___ ___   __  __         _ _        __  __
 / _ \|_ _/ _ \ |  \/  | ___ __| (_) __ _|  \/  | __ _ _ __
| | | || | | | || |\/| |/ _ / _` | |/ _` | |\/| |/ _` | '_ \
| |_| || | |_| || |  | |  __/ (_| | | (_| | |  | | (_| | | | |
 \___/|___\___/ |_|  |_|\___|\__,_|_|\__,_|_|  |_|\__,_|_| |_|

              AIO Media Server Manager  v0.1.0
"""


# ---------------------------------------------------------------------------
# uvicorn in a background thread so asyncio keeps the main thread
# ---------------------------------------------------------------------------

def _start_uvicorn() -> None:
    """Run uvicorn in a daemon thread so it doesn't block the event loop."""
    config = uvicorn.Config(
        app="api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
        # Use existing loop (lifespan managed externally)
        loop="none",
    )
    server = uvicorn.Server(config)
    # uvicorn.Server.run() blocks until the server stops
    server.run()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    logger.info(_BANNER)
    logger.info(
        "Starting AIO Media Manager | config=%s | downloads=%s | media=%s",
        settings.config_dir,
        settings.download_dir,
        settings.media_dir,
    )

    # ------------------------------------------------------------------
    # Initialise config dir and settings file
    # ------------------------------------------------------------------
    settings.initialise()

    # ------------------------------------------------------------------
    # Storage validation & layout creation
    # ------------------------------------------------------------------
    sm = StorageManager(settings)

    logger.info("Validating storage paths…")
    sm.validate_all()

    logger.info("Creating standard directory layout…")
    try:
        sm.create_standard_layout()
    except PermissionError as exc:
        logger.error(
            "Cannot create directory layout: %s — "
            "check that the process has write access to config/download/media directories.",
            exc,
        )
        # Non-fatal: continue startup; individual apps will fail if their dirs are missing

    # ------------------------------------------------------------------
    # API server (background thread)
    # ------------------------------------------------------------------
    logger.info(
        "Starting API server on %s:%d …", settings.api_host, settings.api_port
    )
    api_thread = threading.Thread(target=_start_uvicorn, daemon=True, name="uvicorn")
    api_thread.start()

    # ------------------------------------------------------------------
    # Keep the event loop alive (supervisor lives here)
    # ------------------------------------------------------------------
    supervisor = ProcessSupervisor.get()
    logger.info("Process supervisor ready. Waiting for events…")

    try:
        # Run forever — SIGTERM/SIGINT are caught by the supervisor and
        # will call loop.stop() after gracefully stopping all processes.
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass

    logger.info("Main loop exited. Goodbye.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
