"""`CommandSpec` y el despacho único de un executor (plan `estado-regen-y-params-estrictos`, D5).

Antes el despacho vivía en `registry.py` como una cadena de 11 ramas elegidas por 8 flags
`wants_*` (9 formas posicionales con `cmd_id` en la 2.ª, 3.ª o 4.ª posición y 2 keyword-only).
La precedencia era implícita y una combinación de flags sin rama propia caía en silencio en la
primera que coincidiera. Hoy hay UNA forma para los 54: `executor(ctx: ExecContext, cmd_id, p)`
(lo exige `tests/test_despacho_unico.py`). Un executor que necesita más contexto lo lee de
`ctx`; si no está, se agrega una propiedad a `ExecContext`, nunca un flag ni una rama.

`run_executor` lee `spec.executor` en CADA llamada: los tests parchean el executor en caliente
(`tests/test_torture.py::_fault_on`, `tests/test_geomcache.py`) y el parche tiene que verse.

`version` (D9): la firma de un comando del log era sha1(previa + id + params), sin nada del
código, así que cambiar UN executor obligaba a subir `GEOM_CACHE_EPOCH` e invalidar TODOS los
proyectos. Hoy la versión entra a la firma (`version_tag`) SÓLO si es ≠ 1: con todo en v1 la
firma es la histórica, y subir la de X invalida sólo los proyectos que contienen X. Cuándo
subirla (regla D10): `commands/CLAUDE.md`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel

from .state import ExecContext

# "scene" muta la escena; "vars" muta las variables (set_variable); "electrico" es del CARRIL
# (V8.1 D1): fuera de la firma encadenada, se evalúa tras el regenerate (`doc/carril.py`).
KINDS = ("scene", "vars", "electrico")


@dataclass
class CommandSpec:
    type: str
    title: str
    category: str
    model: type[BaseModel]
    executor: Callable[[ExecContext, str, Any], None]
    kind: str = "scene"
    version: int = 1  # súbela si cambia la geometría que produce con los MISMOS params (D10)
    # Reproduce OTROS executors (insert_project): su firma lleva TODAS las versiones ≠ 1.
    composite: bool = False
    # Campos de primer nivel que son TEXTO aunque empiecen con «=» (no `=expr`): la designación
    # y las referencias IEC 81346 del carril eléctrico («=Faja1-Q1:2», plan V8.1 D4).
    literales: tuple[str, ...] = ()
    # Sello de ENTRADA (plan union-en-perfil-hueco): `(params, material_de) -> params` para un
    # comando NUEVO (no el replay ni un edit). Un campo cuyo default reproduce los logs viejos
    # entra aquí con el valor de hoy; `material_de(fid)` = el material que el documento le da
    # hoy a esa pieza (set_material/vertical: el regenerate no ve el manifest). Lo llama
    # `doc/sello.py`.
    al_crear: Callable[[dict, Callable[[str], str | None]], dict] | None = None
    # Sello de EDICIÓN: `(params_nuevos, params_previos) -> params` cuando un cliente edita el
    # comando (nunca el replay). Para que un dato que el criterio viejo ignoraba en silencio
    # (`insert_component.length` en un perno) no se siga ignorando al pedirlo: lo llama
    # `doc/sello.py::al_editar` desde `Document.edit`/`edit_many`.
    al_editar: Callable[[dict, dict], dict] | None = None

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"{self.type}: kind '{self.kind}' inválido (válidos: {KINDS})")
        if not callable(self.executor):
            raise ValueError(f"{self.type}: el executor no es invocable")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError(f"{self.type}: version '{self.version}' inválida (entero ≥ 1)")


def run_executor(spec: CommandSpec, ctx: ExecContext, cmd_id: str, model: Any) -> None:
    """Ejecuta el executor de `spec` con los params YA validados (`model`)."""
    spec.executor(ctx, cmd_id, model)


#: Ref del catálogo de una extensión → «extensión@epoch_catalogo» (plan
#: nucleo-abierto-extensiones-privadas, A4): `apolo.extensiones` la llena al cargar. Vacío (sin
#: extensiones) → ninguna firma cambia.
REFS_DE_EXTENSION: dict[str, str] = {}


def _cadenas(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _cadenas(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _cadenas(v)


def version_tag(registry: Mapping[str, CommandSpec], cmd_type: str, params=None) -> str:
    """Lo que las versiones aportan a la firma de un comando del log (D9): "" si todo lo que
    le concierne está en v1 (firma byte-idéntica a la histórica). Un comando compuesto lleva
    las versiones ≠ 1 de TODO el registro: reproduce executors que sus params no nombran.

    Con `params` y alguna extensión con catálogo (A4), suma el `epoch_catalogo` de cada
    extensión cuya ref nombran los params (un compuesto, el de TODAS: su replay puede insertar
    refs que sus params no nombran, p. ej. dentro del adjunto de un `insert_project`). Sin
    extensiones, la firma de siempre."""
    spec = registry.get(cmd_type)
    if spec is None:
        return ""
    pares = registry.items() if spec.composite else [(cmd_type, spec)]
    tags = [f"{t}@{s.version}" for t, s in sorted(pares, key=lambda par: par[0]) if s.version != 1]
    tag = "|v:" + ",".join(tags) if tags else ""
    if params is not None and REFS_DE_EXTENSION:
        epochs = (REFS_DE_EXTENSION.values() if spec.composite else
                  (REFS_DE_EXTENSION[c] for c in _cadenas(params) if c in REFS_DE_EXTENSION))
        if (epochs := sorted(set(epochs))):
            tag += "|ext:" + ",".join(epochs)
    return tag
