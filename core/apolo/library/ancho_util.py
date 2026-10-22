"""Regla «ancho útil» del transportador (F6 de la puerta de publicación): cuánto ancho tiene el
paquete para pasar. Sale de `rules.py` (congelado por el trinquete de tamaño). Puro.

- **Rodillos**: los largueros van DENTRO del ancho del transportador → útil = ancho − 2 largueros
  − 4 mm de juego (el tubo del rodillo).
- **Banda**: el paquete corre SOBRE la banda y las guías van por fuera → útil = el ancho de la
  banda MEDIDO (`banda_lazo.ancho_de_banda`; sin banda reconocida, el `ancho` del transportador)
  y, si hay guías laterales que suben sobre la banda a los dos lados, el menor de los dos con la
  LUZ entre ellas (caja de cada guía: su cara interior, nunca una cota inventada). Restar los
  largueros a una banda de 500 con paquete de 400 daba «holgura justa 16 mm» (falso).
"""

from __future__ import annotations

import re

from .banda_lazo import ancho_de_banda, caras_laterales, es_banda

#: guías o guardas LATERALES por su rol (tras el último « · »): «Guarda lateral (1)», «Guía (2)»
_GUIA_RE = re.compile(r"^(gu[ií]as?|barandas?|guardas?\s+laterale?s?)\b", re.I)
_HOLGURA_OK = 40.0  # mm de holgura total para «ok»


def _caja(f):
    try:
        bb = f.shape.bounding_box()
    except Exception:  # noqa: BLE001
        return None
    return (bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)


def medir_banda(scene: dict) -> dict:
    """{ancho_banda_mm, luz_guias_mm?} de la banda de la escena (la de mayor volumen por ROL);
    {} si no hay banda. Supone la carga hacia +Z, como el resto de las reglas."""
    from .materials import piece_role

    bandas = [f for f in scene.values() if es_banda(getattr(f, "name", "")) and _caja(f)]
    if not bandas:
        return {}
    banda = max(bandas, key=lambda f: float(getattr(f.shape, "volume", 0.0) or 0.0))
    ancho = ancho_de_banda(banda.shape)
    if not ancho:
        return {}
    lo, hi = _caja(banda)
    lat = caras_laterales(banda.shape)
    if lat:  # eje del ancho = la normal de las caras laterales del lazo
        k = max((0, 1), key=lambda i: abs(lat[0][0][i]))
    else:
        k = 0 if hi[0] - lo[0] <= hi[1] - lo[1] else 1
    largo = 1 - k
    centro, tope = (lo[k] + hi[k]) / 2.0, hi[2]
    menos, mas = [], []
    for f in scene.values():
        if f is banda or not _GUIA_RE.match(piece_role(getattr(f, "name", "") or "")):
            continue
        caja = _caja(f)
        if caja is None or caja[1][2] <= tope + 1.0:
            continue  # no sube sobre la banda: no guía al paquete
        if caja[1][largo] < lo[largo] or caja[0][largo] > hi[largo]:
            continue  # no está a lo largo de esta banda
        if caja[1][k] <= centro:
            menos.append(caja[1][k])
        elif caja[0][k] >= centro:
            mas.append(caja[0][k])
    out = {"ancho_banda_mm": round(ancho, 1)}
    if menos and mas:
        out["luz_guias_mm"] = round(min(mas) - max(menos), 1)
    return out


def regla_ancho_util(conveyor: dict, ancho: float, ancho_paquete_mm: float, rail_w: float) -> dict:
    """La regla «ancho útil» en el formato de `rules._check`."""
    if conveyor.get("tipo") == "banda":
        banda = float(conveyor.get("ancho_banda_mm") or ancho)
        luz = conveyor.get("luz_guias_mm")
        util = min(banda, float(luz)) if luz else banda
        de_que = f"banda de {banda:g} mm" + (f", luz entre guías {float(luz):g} mm" if luz else "")
        detalle = f"{util:.0f} mm útiles ({de_que}) para paquete de {ancho_paquete_mm:g} mm."
        justa = "Usa una banda más ancha (≥ 40 mm de holgura total) o guías que centren el paquete."
        falta = (f"Usa una banda de ≥ {ancho_paquete_mm + _HOLGURA_OK:.0f} mm"
                 + (" y abre las guías laterales." if luz and float(luz) < banda else "."))
    else:
        util = ancho - 2 * rail_w - 4
        detalle = f"{util:.0f} mm útiles para paquete de {ancho_paquete_mm:g} mm."
        justa = "Deja ≥ 40 mm de holgura total o añade guías laterales."
        falta = f"Aumenta el ancho total a ≥ {ancho_paquete_mm + 2 * rail_w + 44:.0f} mm."
    if util >= ancho_paquete_mm + _HOLGURA_OK:
        return {"regla": "ancho útil", "estado": "ok", "detalle": detalle}
    if util >= ancho_paquete_mm:
        return {"regla": "ancho útil", "estado": "aviso",
                "detalle": f"Holgura justa: {util - ancho_paquete_mm:.0f} mm.", "recomendacion": justa}
    return {"regla": "ancho útil", "estado": "error",
            "detalle": f"El paquete de {ancho_paquete_mm:g} mm no cabe en {util:.0f} mm útiles.",
            "recomendacion": falta}
