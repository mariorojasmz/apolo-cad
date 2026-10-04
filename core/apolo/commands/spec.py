"""`CommandSpec` y el despacho único de un executor (plan `estado-regen-y-params-estrictos`, D5).

Antes el despacho vivía en `registry.py` como una cadena de 11 ramas elegidas por 8 flags
`wants_*` (9 formas posicionales con `cmd_id` en la 2.ª, 3.ª o 4.ª posición y 2 keyword-only).
La precedencia era implícita y una combinación de flags sin rama propia caía en silencio en la
primera que coincidiera. Hoy hay UNA forma para los 53: `executor(ctx: ExecContext, cmd_id, p)`
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

KINDS = ("scene", "vars")  # "scene" muta la escena; "vars" muta las variables (set_variable)


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


def version_tag(registry: Mapping[str, CommandSpec], cmd_type: str) -> str:
    """Lo que las versiones aportan a la firma de un comando del log (D9): "" si todo lo que
    le concierne está en v1 (firma byte-idéntica a la histórica). Un comando compuesto lleva
    las versiones ≠ 1 de TODO el registro: reproduce executors que sus params no nombran."""
    spec = registry.get(cmd_type)
    if spec is None:
        return ""
    pares = registry.items() if spec.composite else [(cmd_type, spec)]
    tags = [f"{t}@{s.version}" for t, s in sorted(pares, key=lambda par: par[0]) if s.version != 1]
    return "|v:" + ",".join(tags) if tags else ""
