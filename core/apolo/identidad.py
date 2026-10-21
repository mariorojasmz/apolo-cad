"""Identidad del proceso: pid y puerto de la API que corre aquí.

Con varios procesos de la API a la vez (plan `docs/plans/varias-maquinas-a-la-vez.md`, D7), el
`errors.log` compartido y `GET /api/health` dicen de quién es cada cosa. El puerto no lo sabe la
app (uvicorn no se lo pasa): sale de `APOLO_PORT` (lo fijan `apolo` y la flota) o del `--port`
de la línea de comandos de uvicorn, que el worker de `--reload` hereda (multiprocessing copia
`sys.argv`). Sin ninguno de los dos, `None`: quien tenga una petición a mano usa la suya.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: el puerto por defecto de uvicorn cuando su línea de comandos no trae `--port`
_PUERTO_UVICORN = 8000


def pid() -> int:
    return os.getpid()


def _puerto_de_argv(argv: list[str]) -> int | None:
    for i, arg in enumerate(argv):
        valor = None
        if arg == "--port" and i + 1 < len(argv):
            valor = argv[i + 1]
        elif arg.startswith("--port="):
            valor = arg.split("=", 1)[1]
        if valor is not None:
            try:
                return int(valor)
            except ValueError:
                return None
    if argv and "uvicorn" in (Path(argv[0]).stem, Path(argv[0]).parent.name):
        return _PUERTO_UVICORN
    return None


def puerto(argv: list[str] | None = None) -> int | None:
    """El puerto en que escucha esta API: `APOLO_PORT`, si no el `--port` de uvicorn, si no
    `None`. Se lee en cada llamada (un test lo fija con `monkeypatch.setenv`)."""
    env = os.environ.get("APOLO_PORT", "").strip()
    if env:
        try:
            return int(env)
        except ValueError:
            return None
    return _puerto_de_argv(sys.argv if argv is None else argv)
