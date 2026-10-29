"""Lo que la BOM lee de la pieza para COMPRAR y CORTAR sin leer su nombre (plan
bom-de-compra-fiel). Puro sobre la escena: `bom.bom_from_scene` lo llama por pieza.

- **D1. Chapa con ficha** (`Feature.chapa`): espesor, desarrollo y pliegues del MISMO
  `chapa_ficha.desarrollo` de la lista de corte (`cutlist_medida.fila_chapa`) y la norma del
  material (`norma_de_chapa`: la que nombra el material o la pieza, si no la del material
  genérico de la tabla `NORMA_CHAPA`).
- **D2. Perfil de catálogo cortable**: el largo exterior y el corte de cada extremo MEDIDOS
  (`cutlist_medida.medidas`, la medida de la lista de corte). Lo declarado (`cut_length`,
  `miter`) se contrasta: si coincide (± 1 mm, ± 0,5°) la fila conserva el largo declarado (la de
  siempre); si no, manda lo medido y la fila lo dice en `aviso`. Una copia de patrón (sin
  `miter`) agrupa con su original: la clave es la medida.
- **D3. La pieza que se fabrica**: dos piezas de la misma ref, largo y corte que difieren en su
  volumen (taladros u otra operación) no comparten fila (`VOL_REL`); las filas que quedan con la
  misma descripción llevan su `marca` (la pieza representante: `marcar`).
"""

from __future__ import annotations

import re

from .cutlist_medida import _TOL_L, es_perfil, fila_chapa, medidas, texto_angulos

#: volumen relativo bajo el cual dos piezas de la misma ref y corte son la MISMA (D3): el ruido de
#: OCCT entre copias es ~1e-9; un taladro Ø9 en un ángulo de 6 mm es ~6e-4 de su volumen
VOL_REL = 1e-4
_VOL_ABS = 1.0  # mm³

#: la norma de chapa del material GENÉRICO (D1): la de su límite elástico tabulado en
#: `materials.YIELD_MPA` (acero = A36, inoxidable = AISI 304, aluminio = 6061-T6)
NORMA_CHAPA = {
    "acero": "ASTM A36 (≈ EN 10025-2 S235JR)",
    "acero inoxidable": "ASTM A240 (AISI 304)",
    "aluminio": "ASTM B209 (6061-T6)",
}
_NORMA_RE = re.compile(r"\b(ASTM\s*A\d{2,4}|ASTM\s*B\d{2,4}|EN\s*10\d{3}(?:-\d)?|JIS\s*G\s*\d{4}|"
                       r"AISI\s*\d{3}L?|SAE\s*\d{4})\b", re.I)


def norma_de_chapa(material: str | None, nombre: str | None) -> str:
    """La norma de la chapa: la que nombra su material («acero S275JR» no, «acero ASTM A572»
    sí) o su pieza («… chapa e2 ASTM A1011»); si no, la del material genérico; '' si no se
    sabe (nunca inventada)."""
    for texto in (material, nombre):
        if texto and (m := _NORMA_RE.search(texto)):
            return re.sub(r"\s+", " ", m.group(1).upper())
    return NORMA_CHAPA.get((material or "").strip().lower(), "")


def campos_chapa(feat, material: str | None) -> dict | None:
    """{espesor_mm, desarrollo_mm, pliegues, norma, texto} de una pieza con ficha de chapa (D1),
    o None (sin ficha, varios sólidos o una ficha que no despliega: la fila de siempre)."""
    if not getattr(feat, "chapa", None):
        return None
    try:
        if len(list(feat.shape.solids())) > 1:
            return None
    except Exception:  # noqa: BLE001
        return None
    r = fila_chapa(feat, material)
    if r is None:
        return None
    (t, a, b), _firma, campos = r
    n = int(campos.get("pliegues") or 0)
    texto = f" — chapa e={t:g} mm, desarrollo {a:g}×{b:g} mm" + (
        f", {n} pliegue{'s' if n != 1 else ''}" if n else "")
    return {"espesor_mm": t, "desarrollo_mm": [a, b], "pliegues": n,
            "norma": norma_de_chapa(material, getattr(feat, "name", "")), "texto": texto}


def medida_perfil(feat, comp, memo: dict) -> dict | None:
    """{largo, clave, angulos (texto « ∠…» o ''), aviso} de un perfil de catálogo de UNA barra
    medida (D2), o None (no es perfil, varias barras o no se deja medir: la fila de siempre)."""
    if not es_perfil(comp):
        return None
    try:
        solidos = list(feat.shape.solids()) or [feat.shape]
    except Exception:  # noqa: BLE001
        return None
    if len(solidos) != 1:
        return None
    m = medidas(feat, comp, None, solidos, memo)[0]
    if m is None:
        return None
    (_t, _w, largo_medido), _firma, campos = m
    cut = getattr(feat, "cut_length", None)
    coincide = not cut or abs(float(cut) - largo_medido) <= _TOL_L
    largo = float(cut) if cut and coincide else largo_medido
    texto = texto_angulos(campos)
    # el aviso, sólo si la pieza DECLARÓ otra cosa (un inglete o un largo): la copia de un patrón
    # no hereda `miter` y no declaró «a escuadra»
    aviso = campos.get("aviso") if (getattr(feat, "miter", None) or not coincide) else None
    if campos.get("extremos"):  # despunte / especial: cada extremo por su forma
        clave = tuple((e["corte"], tuple(e["angulos"])) for e in campos["extremos"])
    elif campos.get("corte") == "inglete":  # el orden de los extremos no separa (copia girada)
        clave = tuple(sorted(float(a or 0.0) for a in (campos["angulo_1"], campos["angulo_2"])))
    else:
        clave = None
    return {"largo": largo, "clave": clave, "angulos": f" ∠{texto}" if texto else "",
            "aviso": aviso}


def volumen(feat) -> float | None:
    try:
        return float(feat.shape.volume)
    except Exception:  # noqa: BLE001
        return None


def variante(vistos: list[float], vol: float | None) -> int:
    """Índice de la variante geométrica (D3) de `vol` entre las ya vistas de su clave (agrega
    una nueva si ninguna coincide); 0 si no hay volumen."""
    if vol is None:
        return 0
    for i, v in enumerate(vistos):
        if abs(v - vol) <= max(_VOL_ABS, VOL_REL * max(abs(v), abs(vol))):
            return i
    vistos.append(vol)
    return len(vistos) - 1


def marcar(rows: list[dict], scene: dict) -> None:
    """D3: las filas que quedan con la misma ref, descripción, largo y material (piezas que
    difieren en taladros u otra operación) llevan su `marca` (la pieza representante, la de la
    lámina de plano) y la descripción la nombra. Muta las filas."""
    por: dict[tuple, list[dict]] = {}
    for r in rows:
        k = (r["ref"], r["descripcion"], r.get("longitud_mm"), r.get("material"), r.get("grupo"))
        por.setdefault(k, []).append(r)
    for filas in por.values():
        if len(filas) < 2:
            continue
        for r in filas:
            rep = r.get("_rep")
            nombre = getattr(scene.get(rep), "name", None) or rep
            r["marca"] = rep
            r["descripcion"] += f" · marca {rep} («{nombre}»)"
