"""`CommandSpec` y el despacho único de un executor (plan `estado-regen-y-params-estrictos`, D5).

Antes el despacho vivía en `registry.py` como una cadena de 11 ramas elegidas por 8 flags
`wants_*` (9 formas posicionales con `cmd_id` en la 2.ª, 3.ª o 4.ª posición y 2 keyword-only).
La precedencia era implícita y una combinación de flags sin rama propia caía en silencio en la
primera que coincidiera. Hoy hay UNA forma para los 53: `executor(ctx: ExecContext, cmd_id, p)`
(lo exige `tests/test_despacho_unico.py`). Un executor que necesita más contexto lo lee de
`ctx`; si no está, se agrega una propiedad a `ExecContext`, nunca un flag ni una rama.

`run_executor` lee `spec.executor` en CADA llamada: los tests parchean el executor en caliente
(`tests/test_torture.py::_fault_on`, `tests/test_geomcache.py`) y el parche tiene que verse.
"""

from __future__ import annotations

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

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"{self.type}: kind '{self.kind}' inválido (válidos: {KINDS})")
        if not callable(self.executor):
            raise ValueError(f"{self.type}: el executor no es invocable")


def run_executor(spec: CommandSpec, ctx: ExecContext, cmd_id: str, model: Any) -> None:
    """Ejecuta el executor de `spec` con los params YA validados (`model`)."""
    spec.executor(ctx, cmd_id, model)
