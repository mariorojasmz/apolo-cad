"""Executor de `create_belt_conveyor` (faja de banda; plan puerta-de-publicacion, v4–v5).

Emite las piezas del plan (`library/belt_conveyor.py`) como `{cmd_id}_{sufijo}` (command_id del
comando: la puerta de entrega no revisa sus pares por `same_command_pairs`; la de publicación sí,
D13b) y corre `fasten` y `ground` del registro con las uniones y los anclajes del plan, con ids
`{cmd_id}_u_{sufijo}` / `{cmd_id}_g_{sufijo}` (como `create_roller_conveyor`): por eso es
COMPUESTO. La huella D11 cubre SÓLO esta función: si cambian las cotas o el plan
(`library/belt_conveyor*.py`) con los mismos params, sube su `version` a mano (regla D10).

v5 (F6 de la puerta: sondas con el brazo doblado): el campo oculto `cierres` agrega las placas
de cierre de los largueros y las guardas inferiores. `sellar` es el sello de entrada
(`CommandSpec.al_crear`, como `join_bolted.criterio`): todo comando NUEVO nace con
`cierres=True`; un log v4 no trae el campo → False → regenera con la misma geometría (el replay
y los edits no sellan; un cliente que manda `cierres=False` explícito lo conserva).

v6 (plan faja-larga-en-tramos, D1–D5): `tramo_max` (VISIBLE: el modelador puede pedir tramos más
cortos para el transporte) parte el bastidor en tramos iguales empernados; el campo oculto
`criterio` (6) suma los rodillos de retorno y el perno pasante con buje de los soportes de la
cama. El sello pone `tramo_max = 6000` y `criterio = 6` a toda faja NUEVA; un log de antes no
los trae → una pieza y criterio 5 → la misma geometría (`tests/test_belt_conveyor_v6.py`).

F1b (D7–D9): `lado_abierto` (VISIBLE, default «ninguno» = lo de antes) saca la pared de la guarda
lateral del costado de los operarios; el criterio 7 (el del sello desde la F1b; el 6 queda como
estaba en las fajas ya selladas) suma el pie de tuerca soldada y contratuerca y los brazos del
motor a tope contra la pata con su cuenta (`tests/test_belt_conveyor_f1b.py`).

F1c (D10–D14): el criterio 8 (el del sello desde la F1c; 5, 6 y 7 quedan como estaban) pone los
agujeros de cada unión, saca las tuercas de dentro de los tubos, parte cama y guardas laterales en
paños ≤ 3 m, calcula el espesor de la cama y escribe el largo de cada perno
(`tests/test_belt_conveyor_f1c.py`).
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import ValidationError

from .errors import CommandError
from .models_faja import CreateBeltConveyorParams
from .spec import run_executor
from .state import ExecContext

TRAMO_NUEVO = 6000.0   # barra comercial de tubo (D2)
CRITERIO_NUEVO = 8     # F1c: el 7 + agujeros, sin tuercas en tubos, paños y largos (D10–D14)


def sellar(params: dict, material_de: Callable[[str], str | None]) -> dict:
    """Sello de entrada de una faja NUEVA: con los cierres de la v5, los tramos de 6 m (barra
    comercial) y el criterio 8 (F1c) (lo que el cliente ya trae se respeta: un test puede
    pedir la v4 tal cual)."""
    params.setdefault("cierres", True)
    params.setdefault("tramo_max", TRAMO_NUEVO)
    params.setdefault("criterio", CRITERIO_NUEVO)
    return params


def _exec_create_belt_conveyor(ctx: ExecContext, cmd_id: str, p: CreateBeltConveyorParams) -> None:
    from apolo.kernel.matrix import compose_place, multiply
    from apolo.kernel.shapes import place
    from apolo.library.belt_conveyor import belt_conveyor_parts

    from .registry import REGISTRY, Feature, _publish_axis_anchor, register_definition

    try:
        plan = belt_conveyor_parts(
            p.largo, p.ancho_banda, p.altura, p.tambor_motriz, p.tambor_cola, p.tubo,
            None if p.tensor == "ninguno" else p.tensor,
            None if p.motor == "ninguno" else p.motor,
            p.espesor_banda, p.guardas, p.cierres, p.tramo_max, p.criterio, p.lado_abierto,
        )
    except (ValueError, KeyError) as exc:
        raise CommandError(f"Faja de banda: {exc}") from exc
    pos, rot = p.position.tuple(), p.rotation.tuple()
    cmd_matrix = compose_place(pos, rot)
    for part in plan.piezas:
        fid = f"{cmd_id}_{part.suffix}"
        matrix = None
        if part.base_key and part.base_shape is not None:
            register_definition(part.base_key, part.base_shape)
            matrix = multiply(cmd_matrix, compose_place(part.position, part.rotation))
        ctx.scene[fid] = Feature(
            fid, f"{p.name} · {part.name}", place(part.shape, pos, rot), cmd_id,
            component=part.component, cut_length=part.cut_length,
            mesh_key=part.base_key if matrix is not None else None, matrix=matrix,
            material=part.material,
        )
    _publish_axis_anchor(ctx.scene, f"{cmd_id}_tambor_motriz", "eje_motriz")
    _publish_axis_anchor(ctx.scene, f"{cmd_id}_tambor_cola", "eje_cola")
    pasos = [("fasten", f"u_{suf}", {"name": f"{cmd_id}_{suf}", "a": f"{cmd_id}_{a}",
                                     "b": f"{cmd_id}_{b}", "kind": kind, "nota": nota, **dim})
             for suf, a, b, kind, nota, dim in plan.uniones]
    pasos += [("ground", f"g_{suf}", {"name": f"{cmd_id}_{suf}", "feature": f"{cmd_id}_{pieza}",
                                      "nota": nota})
              for suf, pieza, nota in plan.anclajes]
    for tipo, suf, params in pasos:
        spec = REGISTRY[tipo]
        try:
            run_executor(spec, ctx, f"{cmd_id}_{suf}", spec.model.model_validate(params,
                                                                                extra="forbid"))
        except (ValidationError, CommandError) as exc:
            raise CommandError(f"Faja de banda ({tipo} {suf}): {exc}") from exc
