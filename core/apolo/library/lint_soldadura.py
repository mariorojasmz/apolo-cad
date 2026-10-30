"""Lint pre-entrega «soldadura imposible» (F6 de la puerta de publicación): un `fasten` tipo
soldadura entre piezas que no se pueden soldar entre sí no se fabrica. Una pieza de madera,
caucho, PVC, vidrio o cartón no se suelda; acero (o inox) con aluminio tampoco por fusión. Es
error de MODELO: la unión es otra (perno, pegado, contacto) o el material está mal.

Puro: recibe la escena y los fasteners (dicts), nunca un `Document`. El material sale de
`materials.resolve_material` con el VERTICAL (`default`): sin él (quien no tiene el documento) se
asume acero, para que una palabra de carpintería del nombre no invente una madera.
"""

from __future__ import annotations

from .materials import _norm, resolve_material
from .rules import _check

#: familias que se sueldan por fusión, y con quién
_FAMILIA = {"acero": "ferroso", "acero inoxidable": "ferroso", "aluminio": "aluminio"}
#: lo que no se suelda (un metal sin tabla —latón, zinc— o un material desconocido no se acusa)
_NO_SOLDABLE = ("madera", "copaiba", "haya", "radiata", "eucalipto", "caucho", "pvc", "vidrio",
                "carton", "cable")


def motivo_no_soldable(mat_a: str, mat_b: str) -> str | None:
    """Por qué no se sueldan dos materiales, o None si se puede (o no se sabe)."""
    na, nb = _norm(mat_a), _norm(mat_b)
    for mat, n in ((mat_a, na), (mat_b, nb)):
        if n in _NO_SOLDABLE:
            return f"«{mat}» no se suelda"
    fa, fb = _FAMILIA.get(na), _FAMILIA.get(nb)
    if fa and fb and fa != fb:
        return f"{mat_a} con {mat_b} no se sueldan por fusión"
    return None


def soldadura_imposible_lint(scene: dict, fasteners: dict, catalog: dict, *,
                             default: str | None = None) -> list[dict]:
    """ERROR por cada soldadura declarada entre materiales que no se sueldan (formato `_check`,
    con `piezas`). Lista vacía si todas son posibles."""
    vertical = default or "acero"
    malas: list[str] = []
    piezas: list[str] = []
    for f in (fasteners or {}).values():
        if f.get("kind") != "soldadura":
            continue
        fa, fb = scene.get(f.get("a")), scene.get(f.get("b"))
        if fa is None or fb is None:
            continue
        ma = resolve_material(fa, catalog, vertical)
        mb = resolve_material(fb, catalog, vertical)
        motivo = motivo_no_soldable(ma, mb)
        if motivo is None:
            continue
        malas.append(f"{fa.name} ↔ {fb.name} ({motivo})")
        piezas += [f.get("a"), f.get("b")]
    if not malas:
        return []
    ejemplo = "; ".join(malas[:6]) + ("…" if len(malas) > 6 else "")
    regla = _check(
        "pre-entrega · soldadura imposible", "error",
        f"{len(malas)} soldadura(s) entre materiales que no se sueldan: {ejemplo}.",
        "Cambia la unión a perno, pegado o contacto (fasten kind) o corrige el material de la "
        "pieza (set_material) si está mal resuelto: así no se puede fabricar.",
    )
    regla["piezas"] = list(dict.fromkeys(piezas))
    return [regla]
