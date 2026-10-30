"""Insumos de `union.contacto_no_cuelga` (plan lo-fijo-que-gira-y-lo-que-cuelga, D2 y F0 D2a–D2c):
cada `fasten` contacto con carga colgada, con lo que el control puro
(`library/calidad/cuelga.py`) necesita para juzgarlo. El llamador sostiene STATE_LOCK.

- **Grafo**: el DECLARADO de la entrega (`connectivity.build_graph`: juntas, mates, fijadores y
  anclajes); lo colgado de una unión es lo que pierde tierra al quitarla
  (`loads.piezas_colgadas`, la misma cuenta de `hanging_load_kg`).
- **No se juzgan** (`no_juzgadas`, por motivo): el par que además lleva otra unión o una junta (no
  cuelga del contacto), la cadena que asienta su comando (`delivery_inputs.de_cadena`), la unión
  redundante (nada pierde tierra), la tornillería (`lints._is_bolt`, de cualquiera de las dos) y
  lo colgado de menos de `KG_MIN`.
- **Por caso**: la masa y el centro de masa de TODO lo colgado (`mass.feature_mass`, con el
  material del vertical), la caja de la zona de contacto (`kernel/contacto.zona_de_contacto`; con
  un toque en un punto, el par de puntos más cercanos) y si la nota del `fasten` la declara unión
  de tubería que tira (roscada o tri-clamp, D2c: entonces no se mide la zona).
"""

from __future__ import annotations

from apolo.library.calidad.contacto import TOL_MM as TOL_CONTACTO_MM


def uniones_contacto(doc) -> dict:
    """{contacto: n} de los `fasten` contacto entre piezas de la escena (el detector de
    `puerta_hechos`)."""
    n = sum(1 for f in doc.fasteners.values() if f.get("kind") == "contacto"
            and f.get("a") in doc.scene and f.get("b") in doc.scene)
    return {"contacto": n} if n else {}


def _zona(sa, sb) -> list | None:
    """La caja de la zona de contacto; con un toque sin línea, la de los dos puntos más cercanos."""
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    from apolo.kernel.contacto import zona_de_contacto

    z = zona_de_contacto(sa, sb, TOL_CONTACTO_MM)
    if z is not None:
        return [round(v, 1) for v in z]
    dss = BRepExtrema_DistShapeShape(sa.wrapped, sb.wrapped)
    if not dss.IsDone() or dss.NbSolution() < 1 or dss.Value() > TOL_CONTACTO_MM:
        return None
    p, q = dss.PointOnShape1(1), dss.PointOnShape2(1)
    return [round(v, 1) for v in (min(p.X(), q.X()), min(p.Y(), q.Y()), min(p.Z(), q.Z()),
                                  max(p.X(), q.X()), max(p.Y(), q.Y()), max(p.Z(), q.Z()))]


def cuelga(doc) -> dict:
    """El insumo de `union.contacto_no_cuelga` (formato en `library/calidad/cuelga.py`)."""
    from apolo.assembly.connectivity import build_graph
    from apolo.library.calidad.cuelga import KG_MIN, traccion_declarada
    from apolo.library.catalog import CATALOG
    from apolo.library.engineering.loads import alcanzables, piezas_colgadas
    from apolo.library.engineering.mass import feature_mass
    from apolo.library.lints import _is_bolt

    from .delivery_inputs import de_cadena

    contactos = [(n, f) for n, f in sorted(doc.fasteners.items()) if f.get("kind") == "contacto"
                 and f.get("a") in doc.scene and f.get("b") in doc.scene]
    no_juzgadas: dict[str, int] = {}
    out = {"contactos": len(contactos), "casos": [], "no_juzgadas": no_juzgadas}
    if not contactos:
        return out
    graph = build_graph(doc.scene, doc.joints, doc.mates, doc.fasteners, doc.grounds)
    if not graph["grounded_seed"]:
        return {**out, "error": "el modelo no tiene anclajes a tierra: nada cuelga ni apoya"}
    antes = alcanzables(graph)
    es_de_cadena = de_cadena(doc)
    tipos: dict[frozenset, set] = {}
    for f in doc.fasteners.values():
        tipos.setdefault(frozenset((f.get("a"), f.get("b"))), set()).add(f.get("kind", "perno"))
    juntas = {frozenset((j.get("parent"), j.get("child"))) for j in (doc.joints or {}).values()}
    masas: dict[str, dict] = {}

    def masa(fid):
        if fid not in masas:
            masas[fid] = feature_mass(doc.scene[fid], CATALOG, doc.default_material())
        return masas[fid]

    def saltar(motivo):
        no_juzgadas[motivo] = no_juzgadas.get(motivo, 0) + 1

    vistos: set = set()
    for nombre, f in contactos:
        a, b = f["a"], f["b"]
        par = frozenset((a, b))
        if par in vistos:
            continue
        vistos.add(par)
        if tipos[par] != {"contacto"} or par in juntas:
            saltar("con_otra_union")
            continue
        if es_de_cadena(f):
            saltar("de_cadena")
            continue
        colgadas = piezas_colgadas(graph, a, b, antes)
        if not colgadas:
            saltar("redundante")
            continue
        if _is_bolt(doc.scene[a], CATALOG) or _is_bolt(doc.scene[b], CATALOG):
            saltar("tornilleria")
            continue
        kg = sum(masa(x)["masa_kg"] for x in colgadas)
        if kg < KG_MIN:
            saltar("liviana")
            continue
        cm = [sum(masa(x)["masa_kg"] * masa(x)["com_mm"][k] for x in colgadas) / kg
              for k in range(3)]
        colgada = a if a in colgadas else b
        apoyo = b if colgada == a else a
        caso = {"union": nombre, "colgada": colgada, "apoyo": apoyo,
                "nombre_colgada": doc.scene[colgada].name, "nombre_apoyo": doc.scene[apoyo].name,
                "piezas": len(colgadas), "kg": round(kg, 2), "cm": [round(c, 1) for c in cm],
                "traccion": traccion_declarada(f.get("nota")), "zona": None}
        if not caso["traccion"]:
            try:
                caso["zona"] = _zona(doc.scene[a].shape, doc.scene[b].shape)
            except Exception:  # noqa: BLE001 — OCCT no pudo: sin zona, SIN_EVALUAR
                caso["zona"] = None
        out["casos"].append(caso)
    return out
