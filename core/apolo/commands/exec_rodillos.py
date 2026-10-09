"""Executors de los rodillos tipo trotadora (`create_take_up`, `create_drive_roller`).

Salieron de `registry.py` (congelado por el trinquete de tamaño) SIN cambiar su código: la
huella de `tests/test_contrato_comandos.py` es la misma (plan `cadenas-pinones`, D8). Sus
params están en `models_rodillos.py` y la geometría que comparten, en
`apolo/library/take_up.py`.
"""

from __future__ import annotations

from .errors import CommandError
from .models_rodillos import CreateDriveRollerParams, CreateTakeUpParams
from .state import ExecContext


def _emit_weldment_parts(*args, **kwargs) -> None:
    """El de `registry.py` (lo usan también bastidor, esqueleto y faja), importado al llamar:
    `registry` importa este módulo al cargarse y un import arriba sería circular."""
    from .registry import _emit_weldment_parts as emitir

    emitir(*args, **kwargs)


def _exec_create_take_up(ctx: ExecContext, cmd_id: str, p: CreateTakeUpParams) -> None:
    from apolo.library.take_up import take_up_parts

    try:
        parts = take_up_parts(
            p.diam_rodillo, p.ancho_banda, p.rodamiento, p.perno, p.espesor_soporte,
            p.voladizo, p.engomado, p.dir_tensor, eje_fit=p.eje_fit, coronado_mm=p.coronado_mm,
        )
    except (ValueError, KeyError) as exc:
        raise CommandError(f"Tensor de cola: {exc}") from exc
    _emit_weldment_parts(ctx.scene, cmd_id, p.name, parts, p.position.tuple(), p.rotation.tuple())


def _exec_create_drive_roller(ctx: ExecContext, cmd_id: str, p: CreateDriveRollerParams) -> None:
    from apolo.library.take_up import drive_roller_parts

    try:
        parts = drive_roller_parts(
            p.diam_rodillo, p.ancho_banda, p.rodamiento, p.perno, p.espesor_soporte,
            p.voladizo, p.largo_eje_motor, p.engomado, p.dir_tensor,
        )
    except (ValueError, KeyError) as exc:
        raise CommandError(f"Rodillo motriz: {exc}") from exc
    _emit_weldment_parts(ctx.scene, cmd_id, p.name, parts, p.position.tuple(), p.rotation.tuple())
