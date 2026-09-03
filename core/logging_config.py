"""
core/logging_config.py — Centralised logging setup using colorlog.

Call configure_logging() once at application startup.  After that, every
module can obtain a logger with the standard:

    import logging
    logger = logging.getLogger(__name__)

The root handler uses colorlog so that log levels appear in colour in a
terminal, while a plain rotating file handler writes to
{config_dir}/logs/amm.log.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

try:
    import colorlog  # type: ignore
    _HAS_COLORLOG = True
except ImportError:  # pragma: no cover — colorlog is a hard dep but handle gracefully
    _HAS_COLORLOG = False

_CONFIGURED = False

# Colour map for levels
_LOG_COLORS: dict[str, str] = {
    "DEBUG": "cyan",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold_red",
}

_CONSOLE_FORMAT = (
    "%(log_color)s%(asctime)s  %(levelname)-8s%(reset)s "
    "%(blue)s%(name)s%(reset)s  %(message)s"
)
_FILE_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(
    level: str = "INFO",
    log_dir: Path | None = None,
) -> None:
    """
    Configure the root logger.

    Parameters
    ----------
    level:
        One of DEBUG / INFO / WARNING / ERROR / CRITICAL.
    log_dir:
        If provided, a rotating file handler is added that writes to
        ``{log_dir}/amm.log``.
    """
    global _CONFIGURED  # noqa: PLW0603
    if _CONFIGURED:
        return

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(numeric_level)

    # ----------------------------------------------------------------
    # Console handler
    # ----------------------------------------------------------------
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)

    if _HAS_COLORLOG:
        console_formatter = colorlog.ColoredFormatter(
            _CONSOLE_FORMAT,
            datefmt=_DATE_FORMAT,
            log_colors=_LOG_COLORS,
            secondary_log_colors={},
            reset=True,
            style="%",
        )
    else:
        console_formatter = logging.Formatter(
            "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
            datefmt=_DATE_FORMAT,
        )

    console_handler.setFormatter(console_formatter)
    root.addHandler(console_handler)

    # ----------------------------------------------------------------
    # Rotating file handler (optional)
    # ----------------------------------------------------------------
    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "amm.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MiB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(
            logging.Formatter(_FILE_FORMAT, datefmt=_DATE_FORMAT)
        )
        root.addHandler(file_handler)

    # Quieten chatty third-party libraries
    for noisy in ("uvicorn.access", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True
    logging.getLogger(__name__).debug(
        "Logging configured: level=%s, log_dir=%s", level, log_dir
    )


def get_logger(name: str) -> logging.Logger:
    """Convenience factory — equivalent to logging.getLogger(name)."""
    return logging.getLogger(name)
