"""Registro persistente de errores para las sesiones de prueba.

Todo error del backend (excepciones, comandos rechazados) y del cliente
(errores JS reportados vía POST /api/client-errors) se acumula en
logs/errors.log para revisarlo y parchear después.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[3] / "logs"
LOG_FILE = LOG_DIR / "errors.log"

_logger: logging.Logger | None = None


def get_logger() -> logging.Logger:
    global _logger
    if _logger is None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger("apolo.errors")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
            logger.addHandler(handler)
        _logger = logger
    return _logger


def log_error(source: str, message: str, **context) -> None:
    parts = [source, message]
    if context:
        parts.append(json.dumps(context, ensure_ascii=False, default=str))
    get_logger().info(" | ".join(parts))


def read_log() -> str:
    if not LOG_FILE.exists():
        return ""
    return LOG_FILE.read_text(encoding="utf-8")


def clear_log() -> None:
    if LOG_FILE.exists():
        LOG_FILE.write_text("", encoding="utf-8")


def session_marker(label: str) -> None:
    get_logger().info(f"===== {label} · {datetime.now().isoformat(timespec='seconds')} =====")
