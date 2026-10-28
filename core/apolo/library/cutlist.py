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
from collections import defaultdict
from functools import lru_cache

from .bom import _base_name
from .catalog import CATALOG
from .cutlist_medida import es_perfil, fila_chapa, fila_perfil, texto_angulos, texto_corte
from .designacion_comercial import (
    categoria_de_compra, designacion, es_comercial, nombre_de_compra, norma_del_nombre,
)
from .incluidas import vastagos_incluidos
from .material_compra import descripcion, factor_peso, material_de_compra
from .material_compra import norma as norma_de_compra
from .materials import resolve_material
from .peso_ficha import partes_de_cilindros, peso_de_ficha

# Pieza COMERCIAL a-medida: se COMPRA, no se corta ni mecaniza — no le corresponde lámina de
# fabricación ni fila de lista de corte. Rol de compra (lo que sigue al último " · ": "Tensor de
# cola · Seeger retención" es COMPRA pero "Tensor de cola · Eje fijo (roscado p/ perno)" NO) o
# norma comercial con designación («Anillo seeger DIN 472-52»). Fuente única, la de la BOM:
# `designacion_comercial` (categoría y nombre de compra incluidos).


def _is_purchased_custom(feat) -> bool:
    """Pieza a-medida (sin componente de catálogo) que se COMPRA (`es_comercial`)."""
    if getattr(feat, "component", None) and CATALOG.get(feat.component):
        return False  # el catálogo ya se enruta por `cuttable`
    return es_comercial(getattr(feat, "name", "") or "")


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


@lru_cache(maxsize=256)
def _seccion_catalogo(ref: str) -> tuple[float, float]:
    """(espesor, ancho) de la sección de un perfil cortable del catálogo: lo construye LARGO
    (1 m) para que el largo no se cuele entre los dos lados (un UPN-120 a 100 mm daba 55×100)."""
    from .catalog import build_component

    shape, _ = build_component(ref, 1000.0)
    return _dims_sorted(shape)[:2]


def _inclinado(comp, f) -> tuple | None:
    """(espesor, ancho, largo) de un perfil de catálogo INCLINADO (una riostra de create_brace,
    un miembro de create_frame): la caja no es su largo; lo es `cut_length` (el exterior) y la
    sección, la de su ficha. None si va alineado a los ejes (la caja de siempre)."""
    cut = getattr(f, "cut_length", None)
    if comp is None or not comp.cuttable or not cut:
        return None
    try:
        largo_caja = _dims_sorted(f.shape)[2]
    except Exception:  # noqa: BLE001 — sin forma medible: la caja de siempre
        return None
    if abs(largo_caja - float(cut)) <= 1.0:
        return None
    return (*_seccion_catalogo(comp.ref), round(float(cut), 1))


def _medidas(f, comp, mat, solidos: list, memo: dict) -> list:
    """Por sólido: (dims, firma, campos) MEDIDOS (perfil de catálogo o chapa con ficha) o None
    (la caja de siempre). `cutlist_medida` dice qué se mide y cómo. Las instancias INTACTAS de
    una misma definición (`mesh_key` + `matrix`: copias rígidas) comparten la medida de la
    primera en `memo` (largo y cortes no cambian al moverla ni al reflejarla, D5)."""
    if getattr(f, "chapa", None) and len(solidos) == 1:
        return [fila_chapa(f, mat)]
    if es_perfil(comp):
        from apolo.kernel.corte_barra import medir_barras

        seccion = _seccion_catalogo(comp.ref)
        clave = f.mesh_key if getattr(f, "mesh_key", None) and f.matrix is not None else None
        barras = memo.get(clave) if clave else None
        if barras is None:
            barras = medir_barras(f.shape, seccion)
            if clave:
                memo[clave] = barras
        return [fila_perfil(f, seccion, m) if m else None for m in barras]
    return [None] * len(solidos)


def cut_list(scene: dict, default_material: str | None = None) -> list[dict]:
    """Piezas a CORTAR (a-medida + catálogo cortable), agrupadas por
    ``(material, espesor, ancho, largo)`` y su corte. Cada Feature se descompone en sus sólidos.
    Un perfil de catálogo da su largo EXTERIOR y el corte de cada extremo MEDIDOS; una chapa
    plegada, su espesor y su desarrollo (`cutlist_medida`).
    `default_material` = el del vertical (guarda de `resolve_material`; None = desconocido)."""
    groups: dict[tuple, dict] = {}
    memo: dict = {}
    con_su_ref = vastagos_incluidos(scene)  # V8.9 F2: el vástago se compra con su cilindro
    for sid, f in scene.items():
        if not getattr(f, "visible", True) or sid in con_su_ref:
            continue
        comp = CATALOG.get(getattr(f, "component", None) or "")
        if comp is not None and not comp.cuttable:
            continue  # herraje no cortable → cédula
        if _is_purchased_custom(f):
            continue  # herraje/consumible a-medida (pernos, pies, banda) → COMPRA, no corte
        mat = resolve_material(f, CATALOG, default_material)
        miter = getattr(f, "miter", None)
        mtr = tuple(miter) if miter else None  # (α1, α2) — separa recto de ingleteado
        solidos = _solids(f.shape)
        medidas = _medidas(f, comp, mat, solidos, memo)
        for i, solid in enumerate(solidos):
            medida = medidas[i] if i < len(medidas) else None
            if medida is not None:
                (t, w, l), firma, campos = medida
            else:
                t, w, l = _inclinado(comp, f) or _dims_sorted(solid)
                firma, campos = mtr, {"corte": "inglete" if mtr else "recto",
                                      "angulo_1": mtr[0] if mtr else None,
                                      "angulo_2": mtr[1] if mtr else None}
            key = (mat, t, w, l, firma)
            g = groups.get(key)
            if g is None:
                g = groups[key] = {
                    "material": mat, "espesor_mm": t, "ancho_mm": w, "largo_mm": l,
                    "cantidad": 0, "nombre": f.name, "_rep": sid, **campos,
                }
                if len(solidos) > 1:
                    g["_solido"] = i  # qué sólido de `_rep` dibuja la lámina de la fila
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
            # una ref que pesa por carrera (cilindro, V8.9) va por ref + carrera, como en la BOM
            cut = getattr(f, "cut_length", None) if (comp.specs or {}).get("peso_por_mm_kg") else None
            key_ref = f"{ref}|{cut:g}" if cut else ref
            mat, ficha_otra = material_de_compra(f, comp)  # set_material gana, como en la BOM
            if ficha_otra:
                key_ref = f"{key_ref}|{mat.lower()}"
            g = groups.get(key_ref)
            if g is None:
                g = groups[key_ref] = {
                    "ref": comp.ref, "nombre": comp.name + (f" carrera {cut:g} mm" if cut else ""),
                    "categoria": comp.category,
                    "material": (comp.specs or {}).get("material", ""),
                    "norma": (comp.specs or {}).get("norma", ""),
                    "cantidad": 0, "peso_ud_kg": round(peso_de_ficha(comp, cut), 3), "_rep": sid,
                }
                if ficha_otra:
                    g["nombre"] = descripcion(g["nombre"], mat, ficha_otra)
                    g.update(material=mat, material_ficha=ficha_otra,
                             norma=norma_de_compra(g["norma"], ficha_otra),
                             peso_ud_kg=round(g["peso_ud_kg"] * factor_peso(mat, ficha_otra), 3))
            g["cantidad"] += 1
        elif _is_purchased_custom(f):
            # herraje/consumible a-medida: se agrupa y cuenta EXACTAMENTE como el BOM
            # (nombre base sin sufijo de instancia, +1 por feature, peso del feature) →
            # las filas de COMPRA de la cédula coinciden con las del BOM (consistencia
            # BOM↔cédula, C4): 24 pernos = 24, no 24 filas ni 16 «pies» por sólido.
            nombre = _base_name(getattr(f, "name", "") or "")
            base = designacion(nombre) or nombre_de_compra(nombre)  # como la BOM (F6)
            key = f"custom:{base.lower()}"
            try:
                w_ud = round(float(f.shape.volume) * density(resolve_material(f, CATALOG)), 3)
            except Exception:
                w_ud = 0.0
            g = groups.get(key)
            if g is None:
                g = groups[key] = {
                    "ref": "COMPRA", "nombre": base,
                    "categoria": categoria_de_compra(base),
                    "material": resolve_material(f, CATALOG), "norma": norma_del_nombre(nombre),
                    "cantidad": 0, "peso_ud_kg": w_ud, "_rep": sid,
                }
            g["cantidad"] += 1
    rows = list(groups.values())
    for r in rows:
        r["peso_total_kg"] = round(r["peso_ud_kg"] * r["cantidad"], 3)
    rows.sort(key=lambda r: (r["categoria"], r["ref"]))
    return rows


def scene_weight_kg(scene: dict, include_hidden: bool = False) -> float:
    """Peso total de los sólidos visibles: catálogo (peso/ud o kg/m × largo) + a-medida
    (volumen × densidad del material). `include_hidden=True` suma también los ocultos
    (la memoria de cálculo: la visibilidad es vista, no diseño)."""
    from .materials import density, resolve_material

    total = 0.0
    partes = partes_de_cilindros(scene)  # V8.9: el vástago de un cilindro no pesa dos veces
    for fid, f in scene.items():
        if not include_hidden and not getattr(f, "visible", True):
            continue
        comp = CATALOG.get(getattr(f, "component", None) or "")
        if fid in partes:
            total += partes[fid]
        elif comp is not None:
            total += peso_de_ficha(comp, getattr(f, "cut_length", None))
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
    for r in rows:  # corte y ángulos: los mismos textos que los planos (`cutlist_medida`)
        w.writerow([r["material"], r["espesor_mm"], r["ancho_mm"], r["largo_mm"],
                    r["cantidad"], r["area_m2_ud"], r["area_m2_total"], r["nombre"],
                    texto_corte(r), texto_angulos(r)])
    if totals:
        w.writerow([])
        w.writerow(["TOTALES por material", "", "", "", "piezas", "", "área m²", "largo m"])
        for m, t in totals.items():
            w.writerow([m, "", "", "", t["piezas"], "", t["area_m2"], t["largo_m"]])
    return buf.getvalue()
