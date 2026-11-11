"""Rotating, levelled application log (replaces print-based output)."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import LOG_PATH

_LOGGER_NAME = "updatescripts"
# Keep library-style silence until the application configures its file handler.
logging.getLogger(_LOGGER_NAME).addHandler(logging.NullHandler())


def setup_logging() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if getattr(logger, "_configured", False):
        return logger
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.DEBUG)
    handler = RotatingFileHandler(
        LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.propagate = False
    logger._configured = True  # type: ignore[attr-defined]
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)
