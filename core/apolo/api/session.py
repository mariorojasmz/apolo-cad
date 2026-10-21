"""Estado de sesión de la API: el documento activo, el almacén y la salud de operación.

UN objeto, `S`, en vez de cinco globals de módulo (D3 del plan
`docs/plans/partir-api-main.md`). Todo el código de la API lee y swapea `S.<campo>`; nadie
declara `global` para cambiar de proyecto. Por qué un objeto y no globals re-exportados: con
`main` partido en varios módulos, un `api.DOC = x` de un test escribiría en el `__dict__`
de `main` mientras el código movido seguiría leyendo el documento viejo.

Los swaps (abrir/crear/restaurar proyecto, arranque) ocurren bajo `STATE_LOCK` (y bajo
`_flush_lock` cuando hay switch, ver `autosave.py`). El arranque (`initialize_store`, movido
tal cual desde `main` en F5b) vive aquí porque es quien llena `S` por primera vez; a su lado,
`prewarm_sandbox`, para testear el arranque sin FastAPI.
"""

from __future__ import annotations

import os
import types
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from apolo.doc import Document
from apolo.state import STATE_LOCK

from . import candado
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


def prewarm_sandbox() -> bool:
    """Arranque: levanta el worker del sandbox en un hilo, sin frenar el startup (plan
    sandbox-caliente, D7), para que la primera edición no pague el import de build123d. Va
    ANTES de `initialize_store`: si el reciente tiene scripts, su replay espera al worker que ya
    está arrancando. ``APOLO_SANDBOX_PREWARM=0`` lo apaga (la suite lo apaga en
    `tests/conftest.py`: perezoso). Devuelve si lo pidió."""
    if os.environ.get("APOLO_SANDBOX_PREWARM") == "0":
        return False
    from apolo import sandbox

    sandbox.prewarm()
    return True


def _fallo_de_arranque(mensaje: str) -> None:
    """Arranque sin proyecto: `startup_error` + doc VACÍO con `project_id=None` (el autosave
    no-opea con None: no pisa nada ni crea un «Sin título»). Bajo `STATE_LOCK`."""
    S.startup_error = mensaje
    log_error("backend.startup", mensaje)
    S.doc = Document()
    S.project_id = None


def initialize_store(db_path: str) -> None:
    """Inicializa el almacén y abre el proyecto del arranque. Extraído del lifespan para
    testearlo SIN FastAPI (los tests no ejecutan el startup).

    Qué abre: `APOLO_PROJECT=<id>` si está (plan varias-maquinas-a-la-vez, D3: cada proceso de
    una flota abre SU máquina); si no, el reciente. Robustez (Fix E): se abre TOLERANTE
    (suprime comandos rotos en vez de negar la apertura); si ni así abre (ZIP roto), o el
    pedido no existe, se deja STARTUP_ERROR + un doc VACÍO en memoria con PROJECT_ID=None y NO
    se crea un 'Sin título' que PISE al reciente como más nuevo. STORE.create sólo cuando la BD
    está de verdad VACÍA y nadie pidió un proyecto. Toma el candado del que abre (D4): si lo
    tiene otro proceso vivo, mismo fallo de arranque con su mensaje."""

    from apolo.projects import ProjectStore

    S.store = ProjectStore(db_path)
    S.startup_error = None
    if S.store.journal_mode.lower() != "wal":  # D2: p. ej. una carpeta de red
        log_error("backend.startup", f"La base {db_path} no quedó en WAL "
                  f"(journal_mode={S.store.journal_mode}): varios procesos a la vez pueden "
                  "dar 'database is locked'. Ponla en un disco local.")
    pedido = os.environ.get("APOLO_PROJECT", "").strip()
    with STATE_LOCK:
        if pedido:
            try:
                objetivo = int(pedido)
            except ValueError:
                _fallo_de_arranque(f"APOLO_PROJECT={pedido!r} no es un id de proyecto")
                return
            if not S.store.exists(objetivo):
                _fallo_de_arranque(f"No existe el proyecto {objetivo} (APOLO_PROJECT)")
                return
            cual = f"{objetivo} (APOLO_PROJECT)"
        else:
            objetivo = S.store.most_recent_id()
            if objetivo is None:
                S.doc = Document()
                S.project_id = S.store.create(S.doc)
                candado.tomar(S.store, S.project_id)  # id nuevo: nadie más lo tiene
                return
            cual = f"reciente {objetivo}"
        try:  # D4: el candado ANTES de cargar; si es de otro proceso vivo, no se abre
            candado.tomar(S.store, objetivo)
        except candado.ProyectoOcupado as exc:
            _fallo_de_arranque(f"No se abrió el proyecto {cual}: {exc.detail}")
            return
        try:
            S.doc = S.store.load(objetivo, tolerant=True)
            S.project_id = objetivo
        except Exception as exc:
            # el autosave no-opea → NO se sobrescribe el proyecto corrupto
            candado.soltar(S.store, objetivo)
            _fallo_de_arranque(f"No se pudo abrir el proyecto {cual}: {exc!r}")
