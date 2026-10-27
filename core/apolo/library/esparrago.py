"""El ESPÁRRAGO: tornillería sin cabeza que se aprieta con su TUERCA (F3c de
puerta-sin-sobrediseno). El espárrago soldado de ISO 13918 (la tapa que no se perfora), el de
doble rosca o la varilla roscada no tienen hexágono: la puerta los daba por «no evaluados» en
acceso de herramienta, agarre, retención y largo comercial.

Cómo se reconoce: el catálogo no trae espárragos y la GEOMETRÍA de uno es la de un pasador o un
eje corto (un cilindro), así que el ROL lo dice (`es_esparrago`: el sustantivo que encabeza el
rol, anclado, como pide `services/CLAUDE.md`) y la geometría lo confirma (`geometria_esparrago`:
sin hexágono, todas sus caras cilíndricas coaxiales y de un mismo Ø salvo los chaflanes). Un
«Perno …» o «Tornillo …» sin cabeza modelada NO es un espárrago: le falta la cabeza (el modelo
está a medias) y la puerta lo sigue diciendo.

Puro sobre sólidos build123d (OCCT): nunca un `Document`.
"""

from __future__ import annotations

import math
import re

#: El rol EMPIEZA por uno de estos (tras el último « · »): «Espárrago soldado puente-tapa 1 (M10x30
#: A2, ISO 13918)», «Varilla roscada M12 del tensor». «Tope elástico … con espárrago M10» no.
_ROL_RE = re.compile(r"^\s*(esp[aá]rragos?|studs?|varillas?\s+roscadas?|barras?\s+roscadas?|"
                     r"threaded\s+rods?)\b", re.I)
_VARILLA_RE = re.compile(r"^\s*(varillas?|barras?|threaded)\b", re.I)
#: Largos nominales del espárrago roscado soldable (ISO 13918, tipo PD) y de los de doble rosca
#: comerciales (DIN 938/939): criterio de compra, a confirmar con el proveedor.
SERIE_ESPARRAGO_MM = (10, 12, 15, 16, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 90, 100,
                      110, 120, 130, 140, 150, 160, 180, 200)
_TOL_RADIO = 0.2  # fracción: el Ø de la rosca y el del vástago (un espárrago de vástago reducido)


def es_esparrago(nombre: str | None) -> bool:
    """¿El ROL de la pieza es un espárrago o una varilla roscada (no sólo los menciona)?"""
    from .materials import piece_role

    return bool(_ROL_RE.match(piece_role(nombre or "")))


def es_varilla(nombre: str | None) -> bool:
    """¿Es varilla (barra) roscada? Se corta a medida (DIN 976-1): no tiene serie de largos."""
    from .materials import piece_role

    return bool(_VARILLA_RE.match(piece_role(nombre or ""))) and es_esparrago(nombre)


def _cilindros(solid) -> list[tuple[float, tuple, tuple]]:
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder

    out = []
    for f in solid.faces():
        try:
            ad = BRepAdaptor_Surface(f.wrapped)
            if ad.GetType() != GeomAbs_Cylinder:
                continue
            c = ad.Cylinder()
            loc, dr = c.Axis().Location(), c.Axis().Direction()
            out.append((c.Radius(), (loc.X(), loc.Y(), loc.Z()), (dr.X(), dr.Y(), dr.Z())))
        except Exception:  # noqa: BLE001
            continue
    return out


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def geometria_esparrago(solid) -> dict | None:
    """{p0, p1 (los extremos sobre el eje), eje (p0 → p1, unitario), d, largo} si el sólido es un
    vástago SIN cabeza (ningún hexágono; caras cilíndricas coaxiales de un mismo Ø ±20 %); None
    si no."""
    from .fijadores_geom import reconocer_fijadores

    if reconocer_fijadores(solid):
        return None
    cils = _cilindros(solid)
    if not cils:
        return None
    r_max, p, e = max(cils, key=lambda c: c[0])
    n = math.sqrt(_dot(e, e))
    e = (e[0] / n, e[1] / n, e[2] / n)
    for r, q, f in cils:
        w = (q[0] - p[0], q[1] - p[1], q[2] - p[2])
        perp = [w[i] - e[i] * _dot(w, e) for i in range(3)]
        if (abs(abs(_dot(f, e)) / math.sqrt(_dot(f, f)) - 1.0) > 1e-3
                or math.sqrt(_dot(perp, perp)) > 0.3 or r < (1.0 - _TOL_RADIO) * r_max):
            return None
    ts = [_dot((v.X - p[0], v.Y - p[1], v.Z - p[2]), e) for v in solid.vertices()]
    if not ts:
        return None
    t0, t1 = min(ts), max(ts)
    if t1 - t0 < 2.0 * r_max:  # más corto que su Ø: una arandela o un casquillo, no un vástago
        return None
    return {"p0": tuple(p[i] + t0 * e[i] for i in range(3)),
            "p1": tuple(p[i] + t1 * e[i] for i in range(3)),
            "eje": e, "d": 2.0 * min(c[0] for c in cils), "largo": t1 - t0}
