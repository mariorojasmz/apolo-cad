"""El comando de la extensión falsa: `prueba.hola` crea una caja (y dos que el núcleo rechaza)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from apolo.extensiones_api import CommandSpec, Feature, make_box


class HolaParams(BaseModel):
    """Caja de prueba de la extensión falsa de la suite: comprueba que un comando de extensión
    entra al registro y regenera como cualquier otro."""

    name: str = Field("Hola", title="Nombre")
    lado: float = Field(50, gt=0, le=10000, title="Lado", description="mm")


def _exec_hola(ctx, cmd_id: str, p: HolaParams) -> None:
    ctx.scene[cmd_id] = Feature(cmd_id, p.name, make_box(p.lado, p.lado, p.lado), cmd_id)


SPECS = [CommandSpec("prueba.hola", "Hola (prueba)", "prueba", HolaParams, _exec_hola)]


def sin_prefijo() -> CommandSpec:
    return CommandSpec("hola", "Hola sin prefijo", "prueba", HolaParams, _exec_hola)


def electrico() -> CommandSpec:
    return CommandSpec("prueba.cable", "Cable de prueba", "prueba", HolaParams, _exec_hola,
                       kind="electrico")
