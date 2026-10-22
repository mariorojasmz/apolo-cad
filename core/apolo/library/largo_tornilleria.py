"""Largo de COMPRA de la tornillería de catálogo en la BOM (F6 de la puerta de publicación): un
perno se pide «M10×40», no «M10». Puro (lee el sólido y la ficha, nunca un `Document`).

La ficha `PERNO-HEX-*` / `PERNO-M*` / `REMACHE-*` / `TIRAFONDO-HEX-*` es de largo A MEDIDA (lo
fija quien la usa: `join_bolted`, el tensor), así que su fila salía sin largo y todos los largos de
una métrica colapsaban en una sola fila. El largo sale, en este orden:

0. del PARAM: `insert_component(length)` de una ficha de largo a medida lo deja en
   `Feature.cut_length` y la BOM lo usa sin pasar por aquí;
1. de la FICHA si es de largo fijo (`specs.length`: `DIN912-M8`, los tirafondos avellanados);
2. del NOMBRE que escribió el comando («Perno M8×20 DIN 933», «Perno tensor Allen
   PERNO-HEX-M12×80», «Remache ciego Ø4.8×10 DIN 7337»): el remache COLOCADO ya no mide lo que
   se compra (la cabeza ciega está recalcada). Si la geometría lo contradice, aviso;
3. de la GEOMETRÍA si tiene cabeza reconocible (`fijadores_geom`): hexagonal → del asiento de la
   cabeza a la punta; Allen → la extensión axial menos k = d (DIN 912). Un largo medido que no
   es de la serie normalizada se pide por el inmediato superior, con aviso.

Sin ninguno → None (la fila sale sin largo, como antes). La tornillería modelada A MANO (sin
ficha) se compra por el largo NOMINAL de su nombre (`largo_nominal_a_medida`); su norma la lee
`designacion_comercial.py`. Caché por `id(shape)` que guarda la
referencia y verifica `is` (regla de [core/apolo](../CLAUDE.md)).
"""

from __future__ import annotations

import re

#: categorías del catálogo cuya pieza se compra por su largo
CATEGORIAS = ("pernos", "tornilleria", "tornilleria_madera")
_LARGO_RE = re.compile(r"(?:\bM|Ø)\s*\d+(?:[.,]\d+)?\s*[x×]\s*(\d+(?:[.,]\d+)?)", re.I)
_CACHE: dict[int, tuple[object, float | None]] = {}
_CACHE_MAX = 4096


def _de_geometria(shape, specs: dict) -> float | None:
    from .fijadores_geom import reconocer_fijadores

    try:
        solidos = list(shape.solids())
    except Exception:  # noqa: BLE001
        return None
    if len(solidos) != 1:
        return None
    solido = solidos[0]
    cab = next((f for f in reconocer_fijadores(solido) if f.tipo in ("cabeza_hex", "allen")), None)
    if cab is None:
        return None
    hacia = (-cab.eje[0], -cab.eje[1], -cab.eje[2])  # del asiento hacia la punta
    largo = max(sum((c - b) * h for c, b, h in zip((v.X, v.Y, v.Z), cab.base, hacia, strict=True))
                for v in solido.vertices())
    if cab.tipo == "allen":  # `base` es la cara de ARRIBA de la cabeza
        # DIN 912: k = d (lo que modela `socket_cap`). NUNCA el `head_h` de la ficha: un tensor
        # dibuja un Allen con la ficha HEXAGONAL (k = 7,5 en M12) y daba 80 + 12 − 7,5 = 84,5
        alto = specs.get("d")
        if not alto:
            return None
        largo -= float(alto)
    return round(largo, 1) if largo > 0 else None


def _del_nombre(nombre: str) -> float | None:
    m = _LARGO_RE.search(nombre or "")
    return float(m.group(1).replace(",", ".")) if m else None


#: designación métrica con largo: «M12x150», «M12×1.5×60» (el último factor es el largo; el paso
#: fino, si lo hay, es menor que el Ø)
_DESIGNACION_RE = re.compile(r"(?<![A-Za-z])M\s*(\d+(?:[.,]\d+)?)((?:\s*[x×]\s*\d+(?:[.,]\d+)?)+)")


def largo_nominal_a_medida(feat) -> float | None:
    """Largo de COMPRA de tornillería MODELADA a mano (sin ficha; F6): el NOMINAL de la
    designación del nombre («Perno tensor de cola M12x150 DIN 933» → 150), no lo que mide el
    sólido (cuerpo + cabeza: 157,5). None si la pieza no es tornillería por su nombre
    (`lints.es_nombre_de_tornilleria`) o no trae designación con largo: entonces manda lo medido."""
    from .lints import es_nombre_de_tornilleria

    nombre = getattr(feat, "name", "") or ""
    if not es_nombre_de_tornilleria(nombre):
        return None
    m = _DESIGNACION_RE.search(nombre)
    if m is None:
        return None
    d = float(m.group(1).replace(",", "."))
    largo = float(re.split(r"[x×]", m.group(2))[-1].strip().replace(",", "."))
    return largo if largo > d else None


def _medido(feat, specs: dict) -> float | None:
    """El largo de la geometría (caché por `id(shape)` con verificación `is`)."""
    shape = getattr(feat, "shape", None)
    if shape is None or specs.get("herramienta") == "remachadora":
        return None
    hit = _CACHE.get(id(shape))
    if hit is not None and hit[0] is shape:
        return hit[1]
    largo = _de_geometria(shape, specs)
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[id(shape)] = (shape, largo)
    return largo


def largo_de_compra_con_aviso(feat, comp) -> tuple[float | None, str]:
    """(largo NOMINAL de compra, aviso) de la tornillería `feat` de la ficha `comp`; (None, '')
    si no es tornillería de largo o no se puede saber. Manda lo NOMINAL: la ficha fija, luego el
    nombre que escribió el comando («… M12×80»); la geometría sólo cuando falta (y, si no es un
    largo normalizado, el inmediato superior de la serie con aviso: 84,5 no se compra)."""
    if comp is None or comp.category not in CATEGORIAS:
        return None, ""
    specs = comp.specs or {}
    if specs.get("length") is not None:
        return float(specs["length"]), ""
    nombre = getattr(feat, "name", "") or ""
    nominal = _del_nombre(nombre)
    medido = _medido(feat, specs)
    if nominal is not None:
        aviso = ""
        if medido is not None and abs(medido - nominal) > 0.5:
            aviso = (f"el nombre dice {nominal:g} mm y la geometría mide {medido:g} mm: se pide "
                     f"el del nombre; revisa el modelo")
        largo, normal = _normalizado(nominal, comp, "el nombre dice")
        return largo, "; ".join(a for a in (aviso, normal) if a)
    if medido is None:
        return None, ""
    return _normalizado(medido, comp, "la geometría mide")


def _normalizado(largo: float, comp, fuente: str) -> tuple[float, str]:
    """(largo, aviso): el de la serie normalizada; si no lo es, el inmediato superior. Sólo
    pernos (ISO 4017/4762) y tornillo para madera (DIN 571): el remache ciego tiene su propia
    serie (DIN 7337: 14, 18…) y se pide por lo que dice."""
    from .largos_perno import en_serie, serie

    ref = comp.ref
    if comp.category == "tornilleria" or en_serie(largo, ref):
        return largo, ""
    arriba = next((s for s in serie(ref) if s >= largo), None)
    if arriba is None:
        return largo, f"{fuente} {largo:g} mm, más que la serie normalizada"
    return arriba, (f"{fuente} {largo:g} mm, que no es un largo normalizado: se pide el "
                    f"inmediato superior ({arriba:g} mm)")


def largo_de_compra(feat, comp) -> float | None:
    """Largo (mm) con el que se compra la tornillería `feat` de la ficha `comp`, o None si no
    es tornillería de largo o no se puede saber."""
    return largo_de_compra_con_aviso(feat, comp)[0]
