"""Registro persistente de errores para las sesiones de prueba.

Todo error del backend (excepciones, comandos rechazados) y del cliente
(errores JS reportados vía POST /api/client-errors) se acumula en
logs/errors.log para revisarlo y parchear después.

Varios procesos de la API escriben el MISMO archivo (plan `varias-maquinas-a-la-vez`, D7): cada
entrada es UNA línea que dice de quién es (`pid=… puerto=…`) y se anexa con UNA escritura
atómica (`apolo.anexar`), sin handle abierto ni `logging`: con un `FileHandler` por proceso,
cinco procesos perdían el 27 % de las líneas en Windows (F0 del plan).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from apolo import identidad, paths
from apolo.anexar import anexar_linea

LOG_DIR = paths.logs_dir()
LOG_FILE = LOG_DIR / "errors.log"


def _sello() -> str:
    """Fecha (formato de siempre, `2026-10-20 15:28:15,123`) + de quién es la entrada."""
    ahora = datetime.now()
    puerto = identidad.puerto()
    return (f"{ahora:%Y-%m-%d %H:%M:%S},{ahora.microsecond // 1000:03d} | "
            f"pid={identidad.pid()} puerto={puerto if puerto is not None else '?'}")


def _escribir(texto: str) -> None:
    """Anexa una entrada. Registrar un error jamás tumba a quien lo registra: si el disco
    falla, avisa por stderr (como hacía `logging`)."""
    try:
        ruta = Path(LOG_FILE)  # se lee en cada llamada: la suite la redirige (conftest)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        anexar_linea(ruta, f"{_sello()} | {texto}")
    except Exception as exc:  # pragma: no cover — disco lleno, permisos
        print(f"apolo: no se pudo escribir {LOG_FILE}: {exc!r}", file=sys.stderr)


def log_error(source: str, message: str, **context) -> None:
    parts = [source, message]
    if context:
        parts.append(json.dumps(context, ensure_ascii=False, default=str))
    _escribir(" | ".join(parts))


def read_log() -> str:
    if not LOG_FILE.exists():
        return ""
    return LOG_FILE.read_text(encoding="utf-8")


def clear_log() -> None:
    if LOG_FILE.exists():
        LOG_FILE.write_text("", encoding="utf-8")


def session_marker(label: str) -> None:
    _escribir(f"===== {label} · {datetime.now().isoformat(timespec='seconds')} =====")
