"""Los tornillos de MADERA sin hexágono, para medir sus distancias en la madera (plan
hallazgos-del-revisor-en-la-puerta, D7 y F4). El llamador sostiene STATE_LOCK.

`calidad_pernos` no los mide: sin cabeza hexagonal ni cilíndrica no reconoce su eje, y la F0
dejó 128 sin medir (la estantería entera va con ellos). Aquí entran:

- la ref de catálogo `tornilleria_madera` sin `llave` (el tornillo avellanado, `wood_screw`);
- un sólido a medida cuyo ROL es de tornillo de madera (`ejes_giro.es_tirafondo`: «Tirafondo…»,
  «Tornillo para madera…», DIN 571/96/7997) que `calidad_pernos` no midió.

Su eje es el de su cilindro más largo (el vástago) y la CABEZA, el extremo más ancho (la cabeza
avellanada; la punta es un cono que cierra en el eje): `t` = 0 en la cara alta de la cabeza. Lo
que el eje cruza se mide con los rayos de `calidad_pernos` (`insumo_perno` con esa geometría).
Sólo los usa la distancia en madera (`calidad_bordes`): ni el agarre ni el paso los juzgan, y un
tornillo sin cabeza reconocible se cuenta, nunca bloquea.
"""

from __future__ import annotations

import math


def es_tornillo_de_madera(feat, catalog) -> bool:
    """¿Tornillo de madera sin llave (catálogo) o tornillo de madera a medida por su rol?"""
    from apolo.library.ejes_giro import es_tirafondo

    comp = catalog.get(getattr(feat, "component", None) or "")
    if comp is not None:
        return comp.category == "tornilleria_madera" and not (comp.specs or {}).get("llave")
    return es_tirafondo(getattr(feat, "name", "") or "")


def geometria_avellanado(solid) -> dict | None:
    """{asiento, dir (hacia la punta), cabeza, d, s, largo, tuercas: []} del tornillo de
    cabeza avellanada (formato de `calidad_pernos.geometria_perno`) o None."""
    from .calidad_pernos import _add, _cilindros, _dot, _sub

    cils = _cilindros(solid)
    if not cils:
        return None
    vs = [(v.X, v.Y, v.Z) for v in solid.vertices()]

    def extension(c) -> float:
        ts = [_dot(_sub(v, c["p"]), c["eje"]) for v in c["vs"]]
        return max(ts) - min(ts) if ts else 0.0

    vastago = max(cils, key=extension)
    p, e, r = vastago["p"], vastago["eje"], vastago["r"]
    ts = [_dot(_sub(v, p), e) for v in vs]
    t_lo, t_hi = min(ts), max(ts)

    def radial(v, t) -> float:
        w = _sub(v, p)
        return math.sqrt(max(0.0, _dot(w, w) - t * t))

    tol = 0.05 * max(t_hi - t_lo, 1.0)
    r_lo = max((radial(v, t) for v, t in zip(vs, ts, strict=True) if t <= t_lo + tol), default=0.0)
    r_hi = max((radial(v, t) for v, t in zip(vs, ts, strict=True) if t >= t_hi - tol), default=0.0)
    if abs(r_hi - r_lo) < 0.3 or max(r_hi, r_lo) < r + 0.3:
        return None  # sin un extremo más ancho que el vástago: no se sabe dónde está la cabeza
    if r_hi > r_lo:
        asiento, dir_, s = _add(p, e, t_hi), (-e[0], -e[1], -e[2]), 2.0 * r_hi
    else:
        asiento, dir_, s = _add(p, e, t_lo), e, 2.0 * r_lo
    return {"asiento": asiento, "dir": dir_, "cabeza": "avellanada", "d": 2.0 * r, "s": s,
            "largo": t_hi - t_lo, "tuercas": []}


def insumos_tornillos_madera(doc, esc, medidos: set[str]) -> tuple[list[dict], int]:
    """(insumos con el formato de `calidad_pernos` y `madera_screw`, cuántos no se reconocen)
    de los tornillos de madera que `calidad_pernos` no midió (`medidos` = sus fids evaluables)."""
    from apolo.library.catalog import CATALOG

    from .calidad_pernos import insumo_perno

    out, sin_geometria = [], 0
    for fid, feat, solid, _mn, _mx, _r in list(esc.solidos):
        if fid in medidos or getattr(feat, "is_guide", False):
            continue
        if not es_tornillo_de_madera(feat, CATALOG):
            continue
        try:
            g = geometria_avellanado(solid)
        except Exception:  # noqa: BLE001 — geometría rara: se cuenta, nunca rompe la puerta
            g = None
        if g is None:
            sin_geometria += 1
            continue
        out.append(insumo_perno(esc, fid, feat, solid, "madera", [], CATALOG, geometria=g))
    return out, sin_geometria
