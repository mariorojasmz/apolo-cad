"""Lista de materiales (BOM) calculada desde la escena.

Las piezas de catálogo se agrupan por referencia + longitud de corte; las
piezas a medida (geometría propia) se agrupan por el comando que las creó.
"""

from __future__ import annotations

import csv
import io
import re

from apolo.kernel.shapes import is_surface

from .catalog import CATALOG
from .materials import density, resolve_material

# sufijos de instancia que añaden los patrones/espejos/copias: " (2)", " (1,2)",
# " (espejo)", " (copia)". Se quitan para agrupar piezas idénticas en una fila.
_INSTANCE_SUFFIX = re.compile(r"\s*\((?:espejo|copia|\d+(?:,\s*\d+)*)\)")


def _base_name(name: str) -> str:
    return _INSTANCE_SUFFIX.sub("", name or "").strip()


def bom_from_scene(scene: dict, default_material: str = "acero",
                   by_group: bool = False) -> list[dict]:
    """BOM agrupado por referencia+corte (catálogo) o firma geométrica (a medida).
    Con `by_group=True` (V5.2) cada fila lleva además su `grupo` (sub-ensamblaje) y
    las piezas iguales de grupos DISTINTOS salen en filas separadas — para subtotales
    por sub-ensamblaje. El default es byte-idéntico al histórico."""
    rows: dict[tuple, dict] = {}
    for sid, feat in scene.items():
        if is_surface(feat.shape):
            continue  # superficie desnuda = geometría de construcción, no es pieza (dale thicken)
        grp = getattr(feat, "group", None) if by_group else None
        component = getattr(feat, "component", None)
        if component and component in CATALOG:
            comp = CATALOG[component]
            cut = getattr(feat, "cut_length", None)
            miter = getattr(feat, "miter", None)
            mtr = tuple(miter) if miter else None  # ingleteado ≠ recto del mismo largo
            key = (component, round(cut, 1) if cut else None, mtr, grp) if by_group else (
                component, round(cut, 1) if cut else None, mtr)
            if key not in rows:
                unit_weight = (
                    comp.weight * (cut / 1000.0) if comp.cuttable and cut else comp.weight
                )
                angs = ""
                if mtr:  # α None en un extremo = ese lado recto (0°)
                    angs = " ∠" + "/".join(f"{a:g}°" if a is not None else "0°" for a in mtr)
                rows[key] = {
                    "ref": comp.ref,
                    "descripcion": comp.name + (f" L={cut:g} mm" if cut else "") + angs,
                    "categoria": comp.category,
                    "material": (comp.specs or {}).get("material", ""),
                    "norma": (comp.specs or {}).get("norma", ""),
                    "cantidad": 0,
                    "longitud_mm": cut,
                    "peso_unitario_kg": round(unit_weight, 3),
                    "peso_total_kg": 0.0,
                    "_rep": sid,  # pieza representante (globos en lámina)
                    **({"grupo": grp} if by_group else {}),
                }
            rows[key]["cantidad"] += 1
        else:
            mat = resolve_material(feat, CATALOG, default_material)
            base = _base_name(feat.name)
            vol = None
            dims = None
            try:
                vol = float(feat.shape.volume)
                bb = feat.shape.bounding_box()
                dims = tuple(sorted((
                    round(bb.max.X - bb.min.X, 1),
                    round(bb.max.Y - bb.min.Y, 1),
                    round(bb.max.Z - bb.min.Z, 1),
                )))
            except Exception:
                pass
            # agrupa por firma geométrica (nombre base sin sufijo de instancia +
            # material + volumen + bbox): patrones, espejos y copias idénticos colapsan
            # en una fila con su cantidad, sin confundir piezas DISTINTAS.
            key = ("__custom__", base, mat, round(vol, 1) if vol is not None else None, dims)
            if by_group:
                key = key + (grp,)
            if key not in rows:
                rows[key] = {
                    "ref": "A-MEDIDA",
                    "descripcion": base,
                    "categoria": "a medida",
                    "material": mat,
                    "norma": "",
                    "cantidad": 0,
                    "longitud_mm": dims[-1] if dims else None,
                    "peso_unitario_kg": round(vol * density(mat), 3) if vol is not None else None,
                    "peso_total_kg": None,
                    "_rep": sid,
                    **({"grupo": grp} if by_group else {}),
                }
            rows[key]["cantidad"] += 1

    out = []
    for row in rows.values():
        if row["peso_unitario_kg"] is not None:
            row["peso_total_kg"] = round(row["peso_unitario_kg"] * row["cantidad"], 3)
        out.append(row)
    out.sort(key=lambda r: (r["categoria"], r["ref"], r["longitud_mm"] or 0))
    return out


def bom_to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\n")
    writer.writerow(["Ref", "Descripción", "Categoría", "Cantidad", "Longitud (mm)", "Peso ud (kg)", "Peso total (kg)"])
    total = 0.0
    for r in rows:
        writer.writerow([
            r["ref"], r["descripcion"], r["categoria"], r["cantidad"],
            r["longitud_mm"] if r["longitud_mm"] is not None else "",
            r["peso_unitario_kg"] if r["peso_unitario_kg"] is not None else "",
            r["peso_total_kg"] if r["peso_total_kg"] is not None else "",
        ])
        total += r["peso_total_kg"] or 0
    writer.writerow(["", "", "", "", "", "TOTAL", round(total, 3)])
    return buf.getvalue()
