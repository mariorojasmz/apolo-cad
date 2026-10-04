"""`CommandSpec` y el despacho único de un executor (plan `estado-regen-y-params-estrictos`, D5).

Antes el despacho vivía en `registry.py` como una cadena de 11 ramas elegidas por 8 flags
`wants_*` (9 formas posicionales con `cmd_id` en la 2.ª, 3.ª o 4.ª posición y 2 keyword-only).
La precedencia era implícita y una combinación de flags sin rama propia caía en silencio en la
primera que coincidiera. Hoy hay UNA forma: `executor(ctx: ExecContext, cmd_id, p)`.

TRANSICIÓN (F2 → F3): los executors que todavía reciben la escena pelada
`(scene, cmd_id, p)` declaran `convention="scene"` y pasan por UN adaptador; la F3 los migra
a `ctx.scene` y borra el campo y la rama.

`run_executor` lee `spec.executor` en CADA llamada: los tests parchean el executor en caliente
(`tests/test_torture.py::_fault_on`, `tests/test_geomcache.py`) y el parche tiene que verse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel

from .state import ExecContext

KINDS = ("scene", "vars")  # "scene" muta la escena; "vars" muta las variables (set_variable)
CONVENTIONS = ("ctx", "scene")  # "scene" = adaptador de transición (lo borra la F3)


@dataclass
class CommandSpec:
    type: str
    title: str
    category: str
    model: type[BaseModel]
    executor: Callable[..., None]
    kind: str = "scene"
    convention: str = "scene"

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"{self.type}: kind '{self.kind}' inválido (válidos: {KINDS})")
        if self.convention not in CONVENTIONS:
            raise ValueError(
                f"{self.type}: convention '{self.convention}' inválida (válidas: {CONVENTIONS})"
            )
        if not callable(self.executor):
            raise ValueError(f"{self.type}: el executor no es invocable")


def run_executor(spec: CommandSpec, ctx: ExecContext, cmd_id: str, model: Any) -> None:
    """Ejecuta el executor de `spec` con los params YA validados (`model`)."""
    if spec.convention == "scene":  # transición: la F3 la borra
        spec.executor(ctx.scene, cmd_id, model)
    else:
        spec.executor(ctx, cmd_id, model)
