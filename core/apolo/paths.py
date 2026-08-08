"""Rutas de datos: idénticas en un checkout del repo y en una instalación `pip`.

En un CHECKOUT (desarrollo) todo vive junto al código, exactamente como siempre:

    <repo>/data/apolo.db   ·   <repo>/logs/   ·   <repo>/ui/dist

Instalado desde PyPI no hay repo donde escribir (site-packages es de solo lectura
por convención y se borra al desinstalar), así que los datos del usuario van a
`APOLO_HOME` (por defecto `~/.apolo`) y la UI se sirve del propio paquete.

La detección es por MARCADOR de checkout (`core/pyproject.toml`), no por heurística
de nombre: en site-packages ese archivo no existe y la rama de usuario entra sola.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_PKG = Path(__file__).resolve().parent  # …/core/apolo


@lru_cache(maxsize=1)
def repo_root() -> Path | None:
    """Raíz del repo si el código corre desde un checkout; `None` si está instalado."""
    root = _PKG.parents[1]  # …/core/apolo → …/core → <repo>
    return root if (root / "core" / "pyproject.toml").is_file() else None


@lru_cache(maxsize=1)
def home() -> Path:
    """Directorio de datos del usuario. Solo se usa FUERA de un checkout."""
    return Path(os.environ.get("APOLO_HOME") or Path.home() / ".apolo").expanduser()


def _base() -> Path:
    root = repo_root()
    return root if root is not None else home()


def data_dir() -> Path:
    """Carpeta de datos (la SQLite de proyectos). No se crea aquí."""
    return _base() / "data"


def logs_dir() -> Path:
    """Carpeta de logs (`errors.log` de las sesiones de prueba). No se crea aquí."""
    return _base() / "logs"


def db_path() -> str:
    """Ruta de la SQLite de proyectos; `APOLO_DB` manda siempre.

    Crea el directorio padre: sqlite no lo hace y fallaría en el primer arranque
    de una instalación limpia.
    """
    env = os.environ.get("APOLO_DB")
    path = Path(env).expanduser() if env else data_dir() / "apolo.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def ui_dist() -> Path | None:
    """Carpeta del bundle de la UI, o `None` si no hay (la API queda headless).

    Prioridad: UI empaquetada en la wheel > build del checkout. Así una instalación
    de PyPI sirve la UI incluida, y en desarrollo gana lo que acabas de compilar.
    """
    packaged = _PKG / "webui"
    if (packaged / "index.html").is_file():
        return packaged
    root = repo_root()
    if root is not None:
        built = root / "ui" / "dist"
        if (built / "index.html").is_file():
            return built
    return None
