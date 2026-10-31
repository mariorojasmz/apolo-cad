"""La CABEZA de un tornillo de revolución sin hexágono (avellanado, cilíndrico): su eje, hacia
dónde mira y su Ø, leídos del SÓLIDO (plan hallazgos-del-revisor D7; plan
puerta-fuera-de-catalogo D3–D4). La usan la medida del tornillo de madera
(`services/calidad_tornillos_madera.py`, `calidad_pernos`) y el acceso por impronta
(`acceso_impronta.py`). Lee OCCT; nunca un `Document`.

El eje es el del cilindro más LARGO (el vástago); la cabeza, el extremo MÁS ANCHO (la punta es un
cono que cierra en el eje). Sin un extremo más ancho que el vástago: None (no se sabe dónde está
la cabeza).
"""

from __future__ import annotations

import math


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def cilindros(solid) -> list[dict]:
    """Caras cilíndricas: {r, p (punto del eje), eje (unitario), vs (vértices)}."""
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
            n = math.sqrt(dr.X() ** 2 + dr.Y() ** 2 + dr.Z() ** 2)
            out.append({"r": c.Radius(), "p": (loc.X(), loc.Y(), loc.Z()),
                        "eje": (dr.X() / n, dr.Y() / n, dr.Z() / n),
                        "vs": [(v.X, v.Y, v.Z) for v in f.vertices()]})
        except Exception:  # noqa: BLE001
            continue
    return out


def cabeza_de_revolucion(solid) -> dict | None:
    """{tope (punto del eje en la cara de arriba de la cabeza), afuera (unitario, de la punta
    hacia la cabeza), d (Ø del vástago), s (Ø de la cabeza), largo (total)} o None."""
    cils = cilindros(solid)
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
        return None
    if r_hi > r_lo:
        tope, afuera, s = tuple(p[k] + e[k] * t_hi for k in range(3)), e, 2.0 * r_hi
    else:
        tope, afuera, s = tuple(p[k] + e[k] * t_lo for k in range(3)), (-e[0], -e[1], -e[2]), 2.0 * r_lo
    return {"tope": tope, "afuera": afuera, "d": 2.0 * r, "s": s, "largo": t_hi - t_lo}


def es_avellanada(solid, cab: dict) -> bool:
    """¿La cabeza es AVELLANADA? Una cara cónica más ancha que el vástago (la punta también es
    un cono, pero cierra en el Ø del vástago)."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cone

    p, e, r = cab["tope"], cab["afuera"], cab["d"] / 2.0
    for f in solid.faces():
        try:
            if BRepAdaptor_Surface(f.wrapped).GetType() != GeomAbs_Cone:
                continue
            for v in f.vertices():
                w = _sub((v.X, v.Y, v.Z), p)
                t = _dot(w, e)
                if math.sqrt(max(0.0, _dot(w, w) - t * t)) > r + 0.3:
                    return True
        except Exception:  # noqa: BLE001
            continue
    return False
