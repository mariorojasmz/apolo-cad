"""Estado de sesión de la API: el documento activo, el almacén y la salud de operación.

UN objeto, `S`, en vez de cinco globals de módulo (D3 del plan
`docs/plans/partir-api-main.md`). Todo el código de la API lee y swapea `S.<campo>`; nadie
declara `global` para cambiar de proyecto. Por qué un objeto y no globals re-exportados: con
`main` partido en varios módulos, un `api.DOC = x` de un test escribiría en el `__dict__`
de `main` mientras el código movido seguiría leyendo el documento viejo.

Los swaps (abrir/crear/restaurar proyecto, arranque) ocurren bajo `STATE_LOCK` (y bajo
`_flush_lock` cuando hay switch, ver `autosave.py`). El arranque (`initialize_store`, movido
tal cual desde `main` en F5b) vive aquí porque es quien llena `S` por primera vez.
"""

from __future__ import annotations

import types
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from apolo.doc import Document
from apolo.state import STATE_LOCK

from .errorlog import log_error

if TYPE_CHECKING:  # el almacén se importa perezoso en el arranque (sqlite no carga con la API)
    from apolo.projects import ProjectStore


@dataclass(slots=True)
class Sesion:
    # el documento ACTIVO (lo que ven la UI, el agente y el MCP)
    doc: Document = field(default_factory=Document)
    # multiproyecto: el almacén se inicializa en startup (los tests no ejecutan
    # lifespan, así que no tocan la base de datos). Sin almacén no hay autosave.
    store: ProjectStore | None = None
    project_id: int | None = None
    # Salud de operación (V6.1): último fallo de autosave (Fix D) y fallo de arranque con
    # el proyecto reciente corrupto (Fix E). GET /api/health los expone; None = sano.
    autosave_error: str | None = None
    startup_error: str | None = None


S = Sesion()

#: nombre viejo de `apolo.api.main` → campo de `S`
_ALIAS = {
    "DOC": "doc",
    "STORE": "store",
    "PROJECT_ID": "project_id",
    "AUTOSAVE_ERROR": "autosave_error",
    "STARTUP_ERROR": "startup_error",
}


def _alias(campo: str) -> property:
    return property(lambda _mod: getattr(S, campo), lambda _mod, v: setattr(S, campo, v))


class _MainModule(types.ModuleType):
    """La clase de módulo de `apolo.api.main`: `api.DOC` & co. son PROPIEDADES sobre `S`.

    Leer, asignar y `monkeypatch.setattr(api, "DOC", d)` (y deshacerlo) van a `S.doc`. Una
    propiedad es un descriptor de datos: gana sobre el `__dict__` del módulo, así que una
    asignación jamás deja una copia suelta en `main` (PEP 562 `__getattr__` sólo cubre
    lecturas: `api.DOC = x` lo taparía para siempre). Lo instala `main` al importarse."""


for _nombre, _campo in _ALIAS.items():
    setattr(_MainModule, _nombre, _alias(_campo))
del _nombre, _campo


def initialize_store(db_path: str) -> None:
    """Inicializa el almacén y abre el proyecto reciente. Extraído del lifespan para
    testearlo SIN FastAPI (los tests no ejecutan el startup). Robustez (Fix E): el
    reciente se abre TOLERANTE (suprime comandos rotos en vez de negar la apertura); si
    ni así abre (ZIP roto), se deja STARTUP_ERROR + un doc VACÍO en memoria con
    PROJECT_ID=None (el autosave no-opea con None) y NO se crea un 'Sin título' que PISE
    al reciente como más nuevo. STORE.create solo cuando la BD está de verdad VACÍA."""

    from apolo.projects import ProjectStore

    S.store = ProjectStore(db_path)
    S.startup_error = None
    with STATE_LOCK:
        recent = S.store.most_recent_id()
        if recent is None:
            S.doc = Document()
            S.project_id = S.store.create(S.doc)
            return
        try:
            S.doc = S.store.load(recent, tolerant=True)
            S.project_id = recent
        except Exception as exc:
            S.startup_error = f"No se pudo abrir el proyecto reciente {recent}: {exc!r}"
            log_error("backend.startup", S.startup_error)
            S.doc = Document()
            S.project_id = None  # el autosave no-opea → NO se sobrescribe el reciente corrupto
