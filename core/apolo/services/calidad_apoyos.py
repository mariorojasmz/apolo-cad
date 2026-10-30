"""Los apoyos a tierra que se COMPRAN y su reacción (plan hallazgos-del-revisor-en-la-puerta, D6): el
insumo de `apoyo.capacidad` (`library/calidad/apoyos.py`, donde está el criterio de qué es un
apoyo de compra y de dónde sale su capacidad) y su detector en `puerta_hechos`. El llamador
sostiene STATE_LOCK.

La reacción es la de la lámina de instalación (`installation_data`: `anchor_loads` con la masa de
toda la máquina y la `carga_kg` de los requisitos, sin la tornillería anclada). Se calcula SÓLO si
algún anclaje es un apoyo de compra: una máquina sin pies ni garruchas no paga la masa.
"""

from __future__ import annotations

from apolo.library.calidad.apoyos import (
    CATEGORIAS,
    capacidad_de_ficha,
    capacidad_del_nombre,
    clase_de_rol,
)
from apolo.library.designacion_comercial import es_comercial

#: lo que la evidencia dice además de la hipótesis del reparto
_HIPOTESIS_CARGA = ("la carga de los requisitos (carga_kg) se reparte con el peso en el COG; un "
                    "canto cargado no se evalúa (no hay requisito de carga excéntrica)")


def apoyo_de_compra(feat, catalog) -> dict | None:
    """{clase, ref, capacidad_kg, fuente_capacidad} si la pieza es un apoyo que se compra; None si
    no (una pieza fabricada, o un perfil de catálogo que hace de pata)."""
    nombre = getattr(feat, "name", "") or ""
    ref = getattr(feat, "component", None) or None
    comp = catalog.get(ref or "") if ref else None
    if comp is not None:
        clase = CATEGORIAS.get(comp.category or "")
        if clase is None:
            return None
        cap = capacidad_de_ficha({**(getattr(comp, "params", None) or {}), **(comp.specs or {})})
        fuente = f"ficha {ref}"
        if cap is None:
            cap, fuente = capacidad_del_nombre(nombre), "su designación"
    else:
        clase = clase_de_rol(nombre)
        if clase is None or not es_comercial(nombre):
            return None
        cap, fuente = capacidad_del_nombre(nombre), "su designación"
    return {"clase": clase, "ref": ref, "capacidad_kg": cap,
            "fuente_capacidad": fuente if cap is not None else None}


def apoyos_de_compra(doc) -> dict:
    """{apoyos: [{id, nombre, clase, ref, reaccion_kg, capacidad_kg, fuente_capacidad}],
    hipotesis, carga_kg, masa_kg} de cada apoyo de compra ANCLADO; `apoyos` vacío si no hay."""
    from apolo.library.catalog import CATALOG

    from .installation_data import installation_data

    candidatos = {}
    for g in doc.grounds.values():
        fid = g.get("feature") if isinstance(g, dict) else None
        feat = doc.scene.get(fid) if fid else None
        if feat is None or getattr(feat, "is_guide", False):
            continue
        a = apoyo_de_compra(feat, CATALOG)
        if a is not None:
            candidatos[fid] = {"id": fid, "nombre": getattr(feat, "name", fid), **a}
    if not candidatos:
        return {"apoyos": []}
    datos, _ = installation_data(doc)
    anclaje = datos.get("anclaje") or {}
    reaccion = {f["id"]: f["carga_kg"] for f in anclaje.get("apoyos") or []}
    filas = [{**c, "reaccion_kg": reaccion[fid]} for fid, c in candidatos.items()
             if fid in reaccion]
    return {"apoyos": filas, "carga_kg": datos.get("carga_kg"), "masa_kg": datos.get("masa_kg"),
            "hipotesis": f"{anclaje.get('hipotesis', '')}; {_HIPOTESIS_CARGA}".lstrip("; ")}


def elementos(datos: dict | None) -> dict:
    """{clase: n} de los apoyos de compra anclados (el detector de `puerta_hechos`)."""
    if datos is None:
        return {"sin_detectar": 1}
    out: dict[str, int] = {}
    for f in datos.get("apoyos") or []:
        out[f["clase"]] = out.get(f["clase"], 0) + 1
    return out
