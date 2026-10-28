"""Executor de `create_brace` (plan uniones-que-tocan, D3/D3b): un miembro de perfil entre dos
piezas, con cada extremo cortado como se une (`library/miembro.py`) y sus dos soldaduras
declaradas con el cordón MEDIDO (`kernel/contacto.py`, el mismo que juzga `union.contacto_real`).

Una sola pieza (`cmd_id`, con la ref de catálogo, `cut_length` exterior y `miter` = el ángulo de
cada extremo: BOM y lista de corte) y los `fasten` `{cmd_id}_a` / `{cmd_id}_b` (soldadura pieza ↔
miembro) registrados aquí, como `create_chain`: no corre otros executors (no es compuesto). La
huella D11 cubre sólo `_exec_create_brace`: cambiar la geometría de `library/miembro.py` con los
mismos params es subir su `version`.
"""

from __future__ import annotations

from .errors import CommandError
from .models_miembro import CreateBraceParams
from .spec import CommandSpec
from .state import ExecContext


def _exec_create_brace(ctx: ExecContext, cmd_id: str, p: CreateBraceParams) -> None:
    from apolo.assembly.connectivity import ConnectivityError, register_fastener
    from apolo.kernel.contacto import medir_contacto
    from apolo.library.calidad.contacto import TOL_MM, largo_eficaz, largo_minimo
    from apolo.library.miembro import Extremo, miembro_entre

    from .registry import Feature

    extremos = {}
    for lado, e in (("a", p.a), ("b", p.b)):
        if e.pieza is None and e.union != "inglete":
            raise CommandError(f"extremo {lado}: falta `pieza` (sólo un inglete contra un miembro "
                               "que aún no existe va sin pieza)")
        pieza = None
        if e.pieza is not None:
            f = ctx.scene.get(e.pieza)
            if f is None or getattr(f, "shape", None) is None:
                raise CommandError(f"extremo {lado}: la pieza '{e.pieza}' no existe (o no tiene "
                                   "forma) en este punto del log")
            pieza = f.shape
        extremos[lado] = Extremo(e.punto.tuple(), e.union, pieza,
                                 e.hacia.tuple() if e.hacia is not None else None)
    try:
        m = miembro_entre(p.perfil, extremos["a"], extremos["b"], p.giro)
    except (ValueError, KeyError) as exc:
        raise CommandError(f"{p.name}: {exc}") from exc
    ctx.scene[cmd_id] = Feature(cmd_id, p.name, m.shape, cmd_id, component=p.perfil,
                                cut_length=m.cut_length,
                                miter=m.angulos if any(m.angulos) else None)  # a escuadra: recto
    minimo = largo_minimo(p.garganta_mm)
    for lado, e in (("a", p.a), ("b", p.b)):
        if e.pieza is None:
            continue
        cordon = medir_contacto(ctx.scene[e.pieza].shape, m.shape, TOL_MM)
        if cordon["cordon_mm"] <= 0:
            raise CommandError(
                f"{p.name}: el extremo {lado} no asienta en '{e.pieza}' ({cordon['forma']}, a "
                f"{cordon['dist_mm']:g} mm): acerca su punto a la cara que lo recibe")
        try:
            register_fastener(ctx.fasteners, cmd_id, {
                "name": f"{cmd_id}_{lado}", "a": e.pieza, "b": cmd_id, "kind": "soldadura",
                "throat_mm": p.garganta_mm, "length_mm": cordon["cordon_mm"],
                "nota": f"{p.name}: extremo {lado} ({e.union}) soldado a todo su perímetro"
                        + ("" if largo_eficaz(cordon["cordon_mm"], p.garganta_mm) >= minimo else
                           f"; cordón corto ({cordon['cordon_mm']:g} mm < {minimo:g})"),
            })
        except ConnectivityError as exc:
            raise CommandError(str(exc)) from exc


SPECS_MIEMBRO = [
    CommandSpec("create_brace", "Riostra / miembro entre piezas", "biblioteca", CreateBraceParams,
                _exec_create_brace),
]
