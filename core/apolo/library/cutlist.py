"""Despiece de fabricación: lista de corte + cédula de herraje (Fase D de planos pro).

A diferencia del BOM (que agrupa por comando/nombre), la **lista de corte** agrupa por
``(material, espesor, ancho, largo)`` para juntar piezas físicamente idénticas aunque
tengan nombres distintos (p. ej. los 8 largueros de las 4 hojas). Separa lo que se
**CORTA** (a-medida + catálogo cortable) de lo que se **COMPRA** (herraje no cortable).

Clave: una Feature puede ser un COMPOUND (unión de varios sólidos — p. ej. una hoja =
2 largueros). Se itera ``shape.solids()`` para contar cada tabla física por separado.
"""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict

from .bom import _base_name
from .catalog import CATALOG
from .materials import resolve_material

# ROL de COMPRA (herraje/consumible a-medida): pieza que se COMPRA, no se corta ni
# mecaniza — no le corresponde lámina de fabricación ni fila de lista de corte. El rol
# es lo que sigue al último " · " del nombre (convención rol-primero, tolerando el
# prefijo de sub-ensamblaje "Grupo · Rol"). Así "Tensor de cola · Seeger retención" es
# COMPRA pero "Tensor de cola · Eje fijo (roscado p/ perno)" NO (el eje se fabrica,
# solo MENCIONA el perno).
_PURCHASE_RE = re.compile(
    r"^(pernos?|tornill\w*|arandelas?|tuercas?|esp[áa]rragos?|prisioneros?|"
    r"pies?\s+nivelador\w*|nivelador\w*|seegers?|circlips?|bandas?|correas?)\b", re.I)


def _role(name: str) -> str:
    return (name or "").split("·")[-1].strip()


def _purchase_category(role: str) -> str:
    r = role.lower()
    if re.match(r"^(pernos?|tornill|arandela|tuerca|esp[áa]rrago|prisionero|seeger|circlip)", r):
        return "tornillería"
    if re.match(r"^(pies?\s+nivelador|nivelador)", r):
        return "niveladores"
    if re.match(r"^(banda|correa)", r):
        return "banda / correa"
    return "compra"


def _is_purchased_custom(feat) -> bool:
    """Pieza a-medida (sin componente de catálogo) cuyo ROL es de COMPRA."""
    if getattr(feat, "component", None) and CATALOG.get(feat.component):
        return False  # el catálogo ya se enruta por `cuttable`
    return bool(_PURCHASE_RE.match(_role(getattr(feat, "name", "") or "")))


def _solids(shape) -> list:
    try:
        ss = list(shape.solids())
    except Exception:
        ss = []
    return ss or [shape]


def _dims_sorted(solid) -> tuple[float, float, float]:
    """(espesor, ancho, largo) = extensiones del bbox en orden ascendente."""
    bb = solid.bounding_box()
    return tuple(sorted((  # type: ignore[return-value]
        round(bb.max.X - bb.min.X, 1),
        round(bb.max.Y - bb.min.Y, 1),
        round(bb.max.Z - bb.min.Z, 1),
    )))


def cut_list(scene: dict) -> list[dict]:
    """Piezas a CORTAR (a-medida + catálogo cortable), agrupadas por
    ``(material, espesor, ancho, largo)``. Cada Feature se descompone en sus sólidos."""
    groups: dict[tuple, dict] = {}
    for sid, f in scene.items():
        if not getattr(f, "visible", True):
            continue
        comp = CATALOG.get(getattr(f, "component", None) or "")
        if comp is not None and not comp.cuttable:
            continue  # herraje no cortable → cédula
        if _is_purchased_custom(f):
            continue  # herraje/consumible a-medida (pernos, pies, banda) → COMPRA, no corte
        mat = resolve_material(f, CATALOG)
        miter = getattr(f, "miter", None)
        mtr = tuple(miter) if miter else None  # (α1, α2) — separa recto de ingleteado
        for solid in _solids(f.shape):
            t, w, l = _dims_sorted(solid)
            key = (mat, t, w, l, mtr)
            g = groups.get(key)
            if g is None:
                g = groups[key] = {
                    "material": mat, "espesor_mm": t, "ancho_mm": w, "largo_mm": l,
                    "cantidad": 0, "nombre": f.name, "_rep": sid,
                    "corte": "inglete" if mtr else "recto",
                    "angulo_1": mtr[0] if mtr else None,
                    "angulo_2": mtr[1] if mtr else None,
                }
            g["cantidad"] += 1
    rows = list(groups.values())
    for r in rows:
        r["area_m2_ud"] = round(r["ancho_mm"] * r["largo_mm"] / 1e6, 4)
        r["area_m2_total"] = round(r["area_m2_ud"] * r["cantidad"], 4)
        r["largo_total_mm"] = round(r["largo_mm"] * r["cantidad"], 1)
    rows.sort(key=lambda r: (r["material"], r["espesor_mm"], -r["largo_mm"]))
    return rows


def cut_list_totals(rows: list[dict]) -> dict[str, dict]:
    """Totales por material: nº de piezas, área (m²) y largo lineal total (m)."""
    tot: dict[str, dict] = defaultdict(lambda: {"piezas": 0, "area_m2": 0.0, "largo_m": 0.0})
    for r in rows:
        t = tot[r["material"]]
        t["piezas"] += r["cantidad"]
        t["area_m2"] += r["area_m2_total"]
        t["largo_m"] += r["largo_total_mm"] / 1000.0
    return {
        m: {"piezas": v["piezas"], "area_m2": round(v["area_m2"], 3), "largo_m": round(v["largo_m"], 2)}
        for m, v in tot.items()
    }


def hardware_schedule(scene: dict) -> list[dict]:
    """Cédula de herraje: piezas de COMPRA — componentes de catálogo NO cortables
    (bisagras, tornillos, correderas, rodamientos...) agrupados por referencia + el
    herraje/consumible modelado A-MEDIDA (pernos, pies niveladores, banda) agrupado por
    nombre. Todo lo que se COMPRA va aquí (o al BOM), NUNCA a la lista de corte."""
    from .materials import density

    groups: dict[str, dict] = {}
    for sid, f in scene.items():
        if not getattr(f, "visible", True):
            continue
        ref = getattr(f, "component", None)
        comp = CATALOG.get(ref or "")
        if comp is not None and not comp.cuttable:
            g = groups.get(ref)
            if g is None:
                g = groups[ref] = {
                    "ref": comp.ref, "nombre": comp.name, "categoria": comp.category,
                    "material": (comp.specs or {}).get("material", ""),
                    "norma": (comp.specs or {}).get("norma", ""),
                    "cantidad": 0, "peso_ud_kg": round(comp.weight, 3), "_rep": sid,
                }
            g["cantidad"] += 1
        elif _is_purchased_custom(f):
            # herraje/consumible a-medida: se agrupa y cuenta EXACTAMENTE como el BOM
            # (nombre base sin sufijo de instancia, +1 por feature, peso del feature) →
            # las filas de COMPRA de la cédula coinciden con las del BOM (consistencia
            # BOM↔cédula, C4): 24 pernos = 24, no 24 filas ni 16 «pies» por sólido.
            base = _base_name(getattr(f, "name", "") or "")
            key = f"custom:{base.lower()}"
            try:
                w_ud = round(float(f.shape.volume) * density(resolve_material(f, CATALOG)), 3)
            except Exception:
                w_ud = 0.0
            g = groups.get(key)
            if g is None:
                g = groups[key] = {
                    "ref": "COMPRA", "nombre": base,
                    "categoria": _purchase_category(_role(base)),
                    "material": resolve_material(f, CATALOG), "norma": "",
                    "cantidad": 0, "peso_ud_kg": w_ud, "_rep": sid,
                }
            g["cantidad"] += 1
    rows = list(groups.values())
    for r in rows:
        r["peso_total_kg"] = round(r["peso_ud_kg"] * r["cantidad"], 3)
    rows.sort(key=lambda r: (r["categoria"], r["ref"]))
    return rows


def scene_weight_kg(scene: dict) -> float:
    """Peso total de los sólidos visibles: catálogo (peso/ud o kg/m × largo) + a-medida
    (volumen × densidad del material)."""
    from .materials import density, resolve_material

    total = 0.0
    for f in scene.values():
        if not getattr(f, "visible", True):
            continue
        comp = CATALOG.get(getattr(f, "component", None) or "")
        if comp is not None:
            cut = getattr(f, "cut_length", None)
            total += comp.weight * (cut / 1000.0) if (comp.cuttable and cut) else comp.weight
        else:
            try:
                total += float(f.shape.volume) * density(resolve_material(f, CATALOG))
            except Exception:
                continue
    return round(total, 3)


def dominant_material(scene: dict) -> str:
    """Material más frecuente entre los sólidos visibles (para el cajetín)."""
    from collections import Counter

    from .materials import resolve_material

    c: Counter = Counter()
    for f in scene.values():
        if getattr(f, "visible", True):
            c[resolve_material(f, CATALOG)] += 1
    return c.most_common(1)[0][0] if c else ""


def cut_list_csv(rows: list[dict], totals: dict | None = None) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(["Material", "Espesor(mm)", "Ancho(mm)", "Largo(mm)", "Cant",
                "Área ud(m²)", "Área total(m²)", "Pieza", "Corte", "Ángulos"])
    for r in rows:
        angs = ""
        if r.get("corte") == "inglete":  # α None en un extremo = ese lado recto
            angs = "/".join(f"{a:g}°" if a is not None else "0°"
                            for a in (r.get("angulo_1"), r.get("angulo_2")))
        w.writerow([r["material"], r["espesor_mm"], r["ancho_mm"], r["largo_mm"],
                    r["cantidad"], r["area_m2_ud"], r["area_m2_total"], r["nombre"],
                    r.get("corte", "recto"), angs])
    if totals:
        w.writerow([])
        w.writerow(["TOTALES por material", "", "", "", "piezas", "", "área m²", "largo m"])
        for m, t in totals.items():
            w.writerow([m, "", "", "", t["piezas"], "", t["area_m2"], t["largo_m"]])
    return buf.getvalue()
