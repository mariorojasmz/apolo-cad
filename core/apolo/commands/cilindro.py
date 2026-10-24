"""Executor de `create_pneumatic_cylinder` (plan V8.9 D5, F2): el cilindro neumático en 3D.

Emite las piezas del plan (`cilindro_geom.plan`) como `{cmd}_{sufijo}` con el command_id del
comando (la puerta de publicación cruza sus pares, como en `create_belt_conveyor`), publica sus
anclas en coords mundo y corre del registro la junta PRISMÁTICA `{cmd}_vastago` (cuerpo →
vástago, 0..carrera, sin arrastrar), la junta `fija` `{cmd}_jf_empujador` (la FK mueve sólo los
hijos declarados) y los `fasten` internos `{cmd}_u_<sufijo>`: por eso es COMPUESTO.

- BOM: el cuerpo lleva la ref con `cut_length` = la carrera (UNA fila por ref + carrera); el
  vástago viene con la ref: ni se cobra ni se fabrica (`library/incluidas.py`, que lee los
  sufijos `_cuerpo`/`_vastago`); la brida, los pies y el empujador son piezas propias.
- Interferencia: el paso del vástago tiene holgura radial, el buje del empujador asienta en el
  hombro y los accesorios apoyan en la cara de su tapa: cero volumen común en todo el recorrido
  (`tests/test_cilindro_neumatico.py` lo recorre sin exclusiones).

La huella D11 cubre sólo `_exec_create_pneumatic_cylinder`: cambiar la geometría de
`cilindro_geom.py` o `library/builders_neumatica.py` con los mismos params es subir su
`version` a mano (y, si cambia la forma de una ref del catálogo, `GEOM_CACHE_EPOCH`).
"""

from __future__ import annotations

from pydantic import ValidationError

from .errors import CommandError
from .models_cilindro import CreatePneumaticCylinderParams
from .spec import CommandSpec, run_executor
from .state import ExecContext


def _exec_create_pneumatic_cylinder(ctx: ExecContext, cmd_id: str, p: CreatePneumaticCylinderParams) -> None:
    from apolo.kernel.matrix import transform_anchors
    from apolo.kernel.shapes import place_matrix

    from . import cilindro_geom as geom
    from .registry import REGISTRY, Feature

    pl = geom.plan(p)
    m = geom.matriz(p)
    fid = {pz.sufijo: f"{cmd_id}_{pz.sufijo}" for pz in pl.piezas}
    for pz in pl.piezas:
        ctx.scene[fid[pz.sufijo]] = Feature(
            fid[pz.sufijo], f"{p.name} · {pz.rol}", place_matrix(pz.forma, m), cmd_id,
            component=pz.component, cut_length=pz.cut_length, material=pz.material,
            anchors=transform_anchors(m, pz.anclas) or None,
        )
    eje = geom.eje_mundo(p)
    pasos = [("add_joint", "vastago", {
        "name": f"{cmd_id}_vastago", "type": "prismatica", "parent": fid["cuerpo"],
        "child": fid["vastago"], "origin": dict(zip("xyz", p.position.tuple())),
        "axis": dict(zip("xyz", eje)), "lower": 0, "upper": p.carrera})]
    pasos += [("add_joint", f"jf_{suf}", {
        "name": f"{cmd_id}_jf_{suf}", "type": "fija", "parent": fid["vastago"], "child": fid[suf]})
        for suf in pl.fijos_al_vastago]
    pasos += [("fasten", suf, {"name": f"{cmd_id}_{suf}", "a": fid[a], "b": fid[b], "kind": kind,
                               "size": size, "qty": qty, "nota": nota})
              for suf, a, b, kind, size, qty, nota in pl.uniones]
    for tipo, suf, params in pasos:
        spec = REGISTRY[tipo]
        try:
            run_executor(spec, ctx, f"{cmd_id}_{suf}", spec.model.model_validate(params, extra="forbid"))
        except (ValidationError, CommandError) as exc:
            raise CommandError(f"Cilindro {p.name} ({tipo} {suf}): {exc}") from exc


SPECS_CILINDRO = [
    CommandSpec("create_pneumatic_cylinder", "Cilindro neumático", "biblioteca",
                CreatePneumaticCylinderParams, _exec_create_pneumatic_cylinder,
                composite=True),  # corre add_joint/fasten (V8.9 D5)
]
