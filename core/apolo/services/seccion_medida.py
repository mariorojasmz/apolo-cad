"""La SECCIÓN de una pieza que no es de catálogo, medida de su geometría (plan
puerta-fuera-de-catalogo, D7). El llamador sostiene STATE_LOCK (OCCT).

Una pieza es viga o columna calculable si su sección es CONSTANTE a lo largo de su eje largo (el
de su caja, alineada con el mundo) y es una de las que se reconocen:
- **rectángulo macizo** b×h (tablero, montante, travesaño, plancha): su volumen es el de su caja
  (± 3 %; un taladro de tornillo no cambia la sección de forma relevante);
- **tubo rectangular** b×h×t o **tubo redondo** Ø×t (run_script, chapa cerrada) y la **barra
  redonda**: A e I medidas en cortes coinciden con las de esa forma.

Se mide con LOSAS finas (2 mm) perpendiculares al eje en 25, 50 y 75 % del largo: área = volumen
de la losa / espesor e inercias por el tensor de inercia de la losa (S = tr(M)/2·1 − M). Constante
= las tres losas iguales (± 3 %), cada una con la extensión transversal de la pieza (± 1 mm) y el
volumen del tramo CENTRAL (25–75 %) igual a A·L/2 (± 3 %: los taladros de tornillo no lo mueven,
una perforación sí; los extremos —un inglete, unas tapas— no cuentan). Lo que no cumple vuelve con
su `motivo`: la regla sale SIN_EVALUAR justificable, nunca NO_APLICA callada. Una pieza INCLINADA
(misma área, el centro de la losa se corre) vuelve con `inclinada`: como un perfil inclinado, no
es viga ni columna de esta regla (`no_aplica` con su motivo).
"""

from __future__ import annotations

import math

TOL_SECCION = 0.03
TOL_EXTENSION_MM = 1.0
VOLUMEN_MIN, VOLUMEN_MAX = 0.97, 1.03  # el tramo central (25–75 %) contra A·L/2
TOL_TUBO = 0.08  # I del tubo medido contra la fórmula de aristas vivas (las esquinas plegadas)
_ESTACIONES = (0.25, 0.5, 0.75)
_LOSA_MM = 2.0


def _tensor(forma):
    """(volumen, centro (x, y, z), S = ∫ r_i r_j dV respecto al centro)."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    p = GProp_GProps()
    BRepGProp.VolumeProperties_s(forma.wrapped, p)
    m, c = p.MatrixOfInertia(), p.CentreOfMass()
    mat = [[m.Value(i, j) for j in (1, 2, 3)] for i in (1, 2, 3)]
    tr = (mat[0][0] + mat[1][1] + mat[2][2]) / 2.0
    s = [[(tr if i == j else 0.0) - mat[i][j] for j in range(3)] for i in range(3)]
    return p.Mass(), (c.X(), c.Y(), c.Z()), s


def _losa(shape, eje: int, x: float, lo, hi):
    from build123d import Box, Pos

    centro = [(lo[k] + hi[k]) / 2.0 for k in range(3)]
    centro[eje] = x
    dims = [hi[k] - lo[k] + 4.0 for k in range(3)]
    dims[eje] = _LOSA_MM
    return shape.intersect(Pos(*centro) * Box(*dims))


def _estacion(shape, eje: int, x: float, lo, hi, trans: tuple[int, int]) -> dict | str:
    try:
        corte = _losa(shape, eje, x, lo, hi)
        vol, c, s = _tensor(corte) if corte is not None else (0.0, None, None)
    except Exception as exc:  # noqa: BLE001 — una forma que no se corta no se mide
        return f"no se pudo cortar la sección ({type(exc).__name__})"
    if vol <= 1e-6:
        return "la sección se vacía a lo largo del eje (hueco o pieza partida)"
    bb = corte.bounding_box()
    blo, bhi = (bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)
    out = {"area": vol / _LOSA_MM, "i": {}, "c": {}, "ext": {}, "centro": {}}
    for k in trans:
        out["i"][k] = s[k][k] / _LOSA_MM
        out["c"][k] = max(bhi[k] - c[k], c[k] - blo[k])
        out["ext"][k] = bhi[k] - blo[k]
        out["centro"][k] = c[k]
    return out


def _volumen_central(shape, eje: int, lo, hi) -> float:
    """El volumen de la pieza entre el 25 y el 75 % de su largo: sin los extremos (un inglete,
    una tapa), con lo que perfora o vacía el tramo que flecta."""
    from build123d import Box, Pos

    centro = [(lo[k] + hi[k]) / 2.0 for k in range(3)]
    dims = [hi[k] - lo[k] + 4.0 for k in range(3)]
    dims[eje] = (hi[eje] - lo[eje]) / 2.0
    corte = shape.intersect(Pos(*centro) * Box(*dims))
    return _tensor(corte)[0] if corte is not None else 0.0


def _parecido(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol * max(abs(a), abs(b), 1e-9)


def _clasificar(area: float, i: dict, d: dict, trans) -> tuple[str, dict] | str:
    """(forma, datos) o el motivo. `d`: extensión transversal por eje del mundo."""
    from apolo.library.engineering.secciones import seccion_rect_hueca

    a_, b_ = trans
    da, db = d[a_], d[b_]
    if _parecido(area, da * db, TOL_SECCION):
        return f"rectángulo macizo {da:.0f}×{db:.0f} mm", {"rect": True, "dmin": min(da, db)}
    if _parecido(da, db, 0.01):
        diam = (da + db) / 2.0
        if _parecido(area, math.pi / 4 * diam ** 2, TOL_SECCION):
            return f"barra redonda Ø{diam:.0f} mm", {"circ": True, "dmin": diam}
        resto = diam ** 2 - 4.0 * area / math.pi
        if resto > 0:
            t = (diam - math.sqrt(resto)) / 2.0
            i_tubo = math.pi / 64 * (diam ** 4 - (diam - 2 * t) ** 4)
            if all(_parecido(i[k], i_tubo, TOL_SECCION) for k in trans):
                return f"tubo redondo Ø{diam:.1f}×{t:.1f} mm", {"circ": True, "dmin": diam}
    disc = (da + db) ** 2 - 4.0 * area
    if disc > 0:
        t = ((da + db) - math.sqrt(disc)) / 4.0
        if 0 < t < min(da, db) / 2.0:
            ref = seccion_rect_hueca(da, db, t)  # ancho en a_, alto en b_
            if _parecido(i[b_], ref.i_x_mm4, TOL_TUBO) and _parecido(i[a_], ref.i_y_mm4, TOL_TUBO):
                return (f"tubo rectangular {da:.0f}×{db:.0f}×{t:.1f} mm",
                        {"tubo_rect": True, "dmin": min(da, db)})
    return ("sección no reconocida: ni rectángulo macizo ni tubo rectangular o redondo (abierta, "
            "compuesta o perforada)")


def _medir(shape, eje: int, lo, hi) -> dict:
    trans = tuple(k for k in range(3) if k != eje)
    largo = hi[eje] - lo[eje]
    d = {k: hi[k] - lo[k] for k in trans}
    try:
        n_solidos = len(shape.solids())
    except Exception:  # noqa: BLE001
        n_solidos = 1
    if n_solidos > 1:
        return {"motivo": f"{n_solidos} sólidos en una pieza (un marco o un conjunto): no es UNA "
                          "viga ni UNA columna"}
    estaciones = []
    for f in _ESTACIONES:
        e = _estacion(shape, eje, lo[eje] + f * largo, lo, hi, trans)
        if isinstance(e, str):
            return {"motivo": e}
        estaciones.append(e)
    areas = [e["area"] for e in estaciones]
    a_med = sorted(areas)[1]
    if any(abs(e["centro"][k] - estaciones[0]["centro"][k]) > TOL_EXTENSION_MM
           for e in estaciones for k in trans) and all(_parecido(x, a_med, TOL_SECCION) for x in areas):
        return {"motivo": "inclinada (su caja no mide su largo)", "inclinada": True}
    var = (not all(_parecido(x, a_med, TOL_SECCION) for x in areas)
           or any(not _parecido(e["i"][k], estaciones[1]["i"][k], TOL_SECCION)
                  for e in estaciones for k in trans))
    if var or any(abs(e["ext"][k] - d[k]) > TOL_EXTENSION_MM for e in estaciones for k in trans):
        return {"motivo": "la sección cambia a lo largo del eje"}
    try:
        central = _volumen_central(shape, eje, lo, hi) / (a_med * largo / 2.0)
    except Exception:  # noqa: BLE001
        return {"motivo": "su volumen no se puede medir"}
    if not VOLUMEN_MIN <= central <= VOLUMEN_MAX:
        return {"motivo": (f"sección no constante: entre el 25 y el 75 % del largo el volumen es "
                           f"{central:.0%} del de su sección (agujeros, perforación o cambios de "
                           "sección)")}
    clase = _clasificar(a_med, estaciones[1]["i"], d, trans)
    if isinstance(clase, str):
        return {"motivo": clase}
    forma, datos = clase
    med = estaciones[1]
    return {"forma": forma, "area": a_med, "largo": largo, "ext": d,
            "i": dict(med["i"]), "w": {k: med["i"][k] / med["c"][k] for k in trans},
            "i_min": min(med["i"].values()), **datos}


def medir_seccion(f, eje: int, caja) -> dict:
    """La sección de la pieza `f` a lo largo del eje del mundo `eje` (0, 1, 2) con su caja
    `((lo), (hi))`: {forma, area, largo, ext {eje: mm}, i {eje: mm⁴} (la inercia respecto al eje
    del mundo `k`… medida como ∫ r_k² dA: la que rige la flexión con la carga en `k`), w, i_min,
    rect|circ|tubo_rect, dmin} o {motivo}. Una vez por forma en la corrida (`memo_corrida`)."""
    from apolo.library.engineering.memo_corrida import por_forma

    shape = getattr(f, "shape", None)
    if shape is None:
        return {"motivo": "sin geometría"}
    lo, hi = caja
    return por_forma(f"seccion_medida_{eje}", shape, lambda: _medir(shape, eje, lo, hi))


__all__ = ["medir_seccion"]
