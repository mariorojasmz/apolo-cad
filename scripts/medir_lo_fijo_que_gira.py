"""Cuántas uniones fallarían con los ítems CANDIDATOS del plan lo-fijo-que-gira-y-lo-que-cuelga
(F0): sólo lectura, nada se escribe en los `.apolo`.

    python -B scripts/medir_lo_fijo_que_gira.py <a.apolo> [<b.apolo> …] [--json salida.json]

Por cada `.apolo` (cargado con `Document.from_apolo_bytes`):

- **D1** `movimiento.coherente`: las uniones RÍGIDAS (`fasten` perno, soldadura o pegado, también
  la de un `join_bolted`) entre dos piezas que la FK mueve con juntas de movimiento distintas
  (`delivery_inputs._juntas_que_mueven`, sin los `fasten` de un super-comando de cadena). Por cada
  una, las excepciones candidatas:
  - `se_tocan`: la de `uniones_entre_juntas` (distancia ≤ 0,05 mm en la pose de diseño);
  - `eje`: un perno o pasador que es EJE de una de las juntas distintas (`calidad_ejes_giro`) y
    las dos piezas están en el cuerpo padre, el cuerpo hijo o son ese eje;
  - `pivote_en_pose`: con cada junta distinta movida un poco (3° o 3 mm, dentro de sus límites)
    las dos piezas se siguen tocando (≤ 0,1 mm) y su volumen común no crece más de
    `_TOL_VOL_MM3`: giran o deslizan una sobre otra, no están empernadas a algo quieto.
  También el par padre-hijo de una junta de movimiento con una unión rígida (`par_de_junta`).
- **D2** `union.contacto_no_cuelga`: las uniones `contacto` con carga colgada
  (`loads.hanging_load_kg` sobre el grafo DECLARADO de la puerta), el centro de masa de lo colgado
  contra la zona de contacto medida (la sección OCCT de `kernel/contacto.py`): `cuelga` (CM bajo
  la zona más que la tolerancia), `apoya` (CM sobre la zona) o `costado` (entre las dos cotas).
  Un par con otra unión rígida no cuelga del contacto: no se juzga. `propuesto` es la clase con
  lo que la F0 propone para F2: sin tornillería (`lints._is_bolt`), lo colgado ≥ `KG_MIN`, la
  tolerancia `TOL_PROPUESTA_MM` y la zona que ABRAZA el CM (lo envuelve a su altura y sobre su
  vertical) cuenta como apoyo.

Resultados y lectura: la bitácora del plan (§ F0).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / "core") not in sys.path:  # mide ESTE árbol (en un worktree el venv apunta al principal)
    sys.path.insert(0, str(RAIZ / "core"))

RIGIDAS = ("perno", "soldadura", "pegado")
MOVIL = ("giratoria", "continua", "prismatica")
_PASO = {"giratoria": 3.0, "continua": 3.0, "prismatica": 3.0}
_TOCA_POSE_MM = 0.1
_TOL_VOL_MM3 = 5.0
TOL_CUELGA_MM = (0.0, 5.0, 25.0)  # tolerancias que se miden para D2
TOL_PROPUESTA_MM = 25.0  # la que la F0 propone (vetable)
KG_MIN = 0.5             # lo colgado más liviano no se juzga (silenciadores, insertos: vetable)


def _nombre(doc, fid) -> str:
    f = doc.scene.get(fid)
    return getattr(f, "name", None) or str(fid)


# ------------------------------------------------------------------ D1
def _uniones_rigidas_entre_juntas(doc) -> dict[frozenset, dict]:
    """`uniones_entre_juntas` SIN la excepción `_se_tocan` (se mide aparte), con todas las
    uniones del par y su tipo."""
    import apolo.services.delivery_inputs as DI

    orig = DI._se_tocan
    DI._se_tocan = lambda _d, _p: False
    try:
        crudas = DI.uniones_entre_juntas(doc)
    finally:
        DI._se_tocan = orig
    por_par: dict[frozenset, list] = {}
    for nombre, f in doc.fasteners.items():
        por_par.setdefault(frozenset((f["a"], f["b"])), []).append((nombre, f.get("kind", "perno")))
    out = {}
    for par, u in crudas.items():
        tipos = por_par.get(par, [])
        if any(k in RIGIDAS for _n, k in tipos):
            out[par] = {**u, "uniones": tipos}
    return out


def _pares_de_junta_rigidos(doc) -> dict[frozenset, dict]:
    """El par padre-hijo de una junta de MOVIMIENTO que además lleva una unión rígida."""
    por_par: dict[frozenset, list] = {}
    for nombre, f in doc.fasteners.items():
        por_par.setdefault(frozenset((f["a"], f["b"])), []).append((nombre, f.get("kind", "perno")))
    out = {}
    for j in (doc.joints or {}).values():
        if j.get("type") not in MOVIL:
            continue
        par = frozenset((j["parent"], j["child"]))
        tipos = por_par.get(par, [])
        if any(k in RIGIDAS for _n, k in tipos):
            out[par] = {"juntas": ((j["name"],), ()), "uniones": tipos, "par_de_junta": True}
    return out


def _valor_de_prueba(j: dict) -> float:
    paso = _PASO.get(j.get("type"), 3.0)
    up, lo = j.get("upper"), j.get("lower")
    if j.get("type") != "continua" and up is not None and float(up) <= 0.0 and lo is not None \
            and float(lo) < 0.0:
        return -min(paso, abs(float(lo)))
    if j.get("type") != "continua" and up is not None and float(up) > 0.0:
        return min(paso, float(up))
    return paso


def _comun(sa, sb) -> float:
    try:
        inter = sa & sb
        return float(inter.volume) if inter is not None else 0.0
    except Exception:  # noqa: BLE001 — OCCT caprichoso: sin dato
        return math.nan


def _pivote_en_pose(doc, par, juntas: set[str]) -> dict:
    """¿Las dos piezas se siguen tocando sin solaparse más al mover cada junta distinta?"""
    from apolo.kernel.measure import measure_distance
    from apolo.robotics.pose import feature_location

    a, b = sorted(par)
    fa, fb = doc.scene[a], doc.scene[b]
    base = _comun(fa.shape, fb.shape)
    try:
        d0 = float(measure_distance(fa.shape, fb.shape)["dist_mm"])
    except Exception:  # noqa: BLE001
        d0 = math.nan
    out = {"comun_diseno_mm3": round(base, 1), "dist_diseno_mm": round(d0, 2), "poses": []}
    pivote = relativo = True
    for jn in sorted(juntas):
        j = doc.joints[jn]
        v = _valor_de_prueba(j)
        vals = {jn: v}
        try:
            la = feature_location(doc.joints, vals, a)
            lb = feature_location(doc.joints, vals, b)
            sa = la * fa.shape if la is not None else fa.shape
            sb = lb * fb.shape if lb is not None else fb.shape
            d = float(measure_distance(sa, sb)["dist_mm"])
        except Exception as exc:  # noqa: BLE001
            out["poses"].append({"junta": jn, "error": repr(exc)[:120]})
            pivote = relativo = False
            continue
        c = _comun(sa, sb)
        no_solapa = math.isnan(c) or c <= base + _TOL_VOL_MM3
        sigue = d <= _TOCA_POSE_MM and no_solapa
        # relativo: la distancia de diseño no crece (una bisagra con holgura de 0,12 mm sigue a
        # 0,12 mm al girar)
        sigue_rel = (math.isnan(d0) or d <= d0 + _TOCA_POSE_MM) and no_solapa
        pivote, relativo = pivote and sigue, relativo and sigue_rel
        out["poses"].append({"junta": jn, "valor": v, "dist_mm": round(d, 2),
                             "comun_mm3": round(c, 1), "pivote": sigue, "pivote_rel": sigue_rel})
    out["pivote"], out["pivote_rel"] = pivote, relativo
    out["coaxial"] = _coaxiales(doc, (a, b), juntas)
    return out


def _coaxiales(doc, piezas, juntas: set[str]) -> dict:
    """{pieza: [juntas]} de las piezas del par con una cara cilíndrica coaxial (± 1 mm) con una
    junta distinta: el barril de una bisagra, el alojamiento de un rodamiento."""
    from apolo.library import ejes_giro as E
    from apolo.services.calidad_pernos import _cilindros

    out = {}
    for fid in piezas:
        try:
            cils = [c for s in doc.scene[fid].shape.solids() for c in _cilindros(s)]
        except Exception:  # noqa: BLE001
            continue
        for jn in sorted(juntas):
            j = doc.joints[jn]
            if j.get("type") not in ("giratoria", "continua"):
                continue
            o, e = E.vec(j.get("origin")), E.unit(E.vec(j.get("axis")))
            if e is not None and any(E.coaxial(c["p"], c["eje"], o, e) for c in cils):
                out.setdefault(fid, []).append(jn)
    return out


def _ejes(doc):
    """{junta: {"cuerpos": padre ∪ hijo, "ejes": {fid del perno o pasador}}} de las juntas de giro
    con eje medido."""
    from apolo.services.calidad_ejes_giro import juntas_de_giro, marcar_ejes
    from apolo.services.calidad_pernos import _Escena, insumos_pernos

    juntas = {j["nombre"]: j for j in juntas_de_giro(doc)}
    if not juntas:
        return {}
    esc = _Escena(doc.scene)
    pernos = insumos_pernos(doc, escena=esc)
    pasadores = marcar_ejes(doc, pernos, esc)
    out = {n: {"padre": j["padre"], "hijo": j["hijo"], "ejes": set()} for n, j in juntas.items()}
    for p in list(pernos) + list(pasadores):
        g = p.get("giro")
        if g and g["junta"] in out:
            out[g["junta"]]["ejes"].add(p["fid"])
    return out


def _por_eje(par, juntas: set[str], ejes: dict) -> str | None:
    for jn in sorted(juntas):
        e = ejes.get(jn)
        if not e or not e["ejes"]:
            continue
        lados = []
        for fid in par:
            if fid in e["ejes"]:
                lados.append("eje")
            elif fid in e["padre"]:
                lados.append("padre")
            elif fid in e["hijo"]:
                lados.append("hijo")
        if len(lados) == 2 and set(lados) != {"padre"} and set(lados) != {"hijo"}:
            return jn
    return None


def d1(doc) -> dict:
    from apolo.services.delivery_inputs import _juntas_que_mueven, _se_tocan

    candidatas = {**_uniones_rigidas_entre_juntas(doc), **_pares_de_junta_rigidos(doc)}
    if not candidatas:
        return {"filas": []}
    ejes = _ejes(doc)
    filas = []
    for par, u in candidatas.items():
        a, b = sorted(par)
        ja, jb = _juntas_que_mueven(doc, a), _juntas_que_mueven(doc, b)
        distintas = {j for j in set(ja) ^ set(jb) if doc.joints.get(j, {}).get("type") in MOVIL}
        if u.get("par_de_junta"):
            distintas = set(u["juntas"][0])
        fila = {"a": a, "b": b, "nombre_a": _nombre(doc, a), "nombre_b": _nombre(doc, b),
                "uniones": u["uniones"], "juntas_a": list(ja), "juntas_b": list(jb),
                "par_de_junta": bool(u.get("par_de_junta")),
                "se_tocan": _se_tocan(doc, par), "eje": _por_eje(par, distintas, ejes)}
        fila.update(_pivote_en_pose(doc, par, distintas))
        fila["d1_como_esta"] = not (fila["se_tocan"] or fila["eje"] or fila["par_de_junta"])
        fila["d1_propuesto"] = not (fila["eje"] or fila["pivote_rel"])
        # la pieza coaxial con la junta que se mueve CON ella y envuelve a su hijo: un
        # alojamiento arrastrado (la chumacera hija del eje); la quieta: el barril de una bisagra
        movil = {f for f in (a, b) if set(ja if f == a else jb) & distintas}
        fila["coaxial_que_se_mueve"] = sorted(set(fila["coaxial"]) & movil)
        fila["coaxial_quieta"] = sorted(set(fila["coaxial"]) - movil)
        filas.append(fila)
    return {"filas": filas, "juntas_con_eje": sorted(j for j, e in ejes.items() if e["ejes"])}


# ------------------------------------------------------------------ D2
def _zona(sa, sb) -> tuple | None:
    """La caja de la zona de contacto (sección OCCT; con hueco ≤ 0,5 mm, por cercanía; si no,
    el par de puntos más cercanos)."""
    from apolo.kernel import contacto as K
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    try:
        tramos = K._seccion(sa, sb) or K._por_cercania(sa, sb, 0.5)
    except Exception:  # noqa: BLE001
        tramos = []
    if tramos:
        cajas = [t["caja"] for t in tramos]
        return tuple(min(c[i] for c in cajas) if i < 3 else max(c[i] for c in cajas)
                     for i in range(6))
    dss = BRepExtrema_DistShapeShape(sa.wrapped, sb.wrapped)
    if not dss.IsDone() or dss.NbSolution() < 1 or dss.Value() > 0.5:
        return None
    p, q = dss.PointOnShape1(1), dss.PointOnShape2(1)
    return (min(p.X(), q.X()), min(p.Y(), q.Y()), min(p.Z(), q.Z()),
            max(p.X(), q.X()), max(p.Y(), q.Y()), max(p.Z(), q.Z()))


def d2(doc) -> dict:
    from apolo.assembly.connectivity import build_graph
    from apolo.library.catalog import CATALOG
    from apolo.library.engineering.loads import _reachable_without, alcanzables
    from apolo.library.engineering.mass import feature_mass

    graph = build_graph(doc.scene, doc.joints, doc.mates, doc.fasteners, doc.grounds)
    if not graph["grounded_seed"]:
        return {"filas": [], "sin_tierra": True}
    antes = alcanzables(graph)
    por_par: dict[frozenset, list] = {}
    for f in doc.fasteners.values():
        por_par.setdefault(frozenset((f["a"], f["b"])), []).append(f.get("kind", "perno"))
    juntas = {frozenset((j["parent"], j["child"])) for j in (doc.joints or {}).values()}
    masas: dict[str, dict] = {}

    def masa(fid):
        if fid not in masas:
            masas[fid] = feature_mass(doc.scene[fid], CATALOG, doc.default_material())
        return masas[fid]

    filas, redundantes, rigido_tambien, vistos = [], 0, 0, set()
    for nombre, f in sorted(doc.fasteners.items()):
        a, b = f["a"], f["b"]
        if f.get("kind") != "contacto" or a not in doc.scene or b not in doc.scene:
            continue
        par = frozenset((a, b))
        if par in vistos:
            continue
        vistos.add(par)
        if any(k != "contacto" for k in por_par[par]) or par in juntas:
            rigido_tambien += 1
            continue
        cuelga = antes - _reachable_without(graph["adj"], graph["grounded_seed"], a, b)
        if not cuelga:
            redundantes += 1
            continue
        kg = sum(masa(x)["masa_kg"] for x in cuelga)
        cm = [sum(masa(x)["masa_kg"] * masa(x)["com_mm"][k] for x in cuelga) / kg if kg else 0.0
              for k in range(3)]
        colgada = a if a in cuelga else b
        apoyo = b if colgada == a else a
        zona = _zona(doc.scene[a].shape, doc.scene[b].shape)
        fila = {"union": nombre, "colgada": colgada, "nombre_colgada": _nombre(doc, colgada),
                "apoyo": apoyo, "nombre_apoyo": _nombre(doc, apoyo), "piezas": len(cuelga),
                "kg": round(kg, 2), "cm": [round(c, 1) for c in cm]}
        if zona is None:
            fila["clase"] = {str(t): "sin_zona" for t in TOL_CUELGA_MM}
            filas.append(fila)
            continue
        dz_bajo = cm[2] - zona[2]   # < 0: el CM está bajo la cota más baja de la zona
        dz_sobre = cm[2] - zona[5]  # > 0: el CM está sobre la cota más alta
        dh = math.hypot(max(zona[0] - cm[0], 0.0, cm[0] - zona[3]),
                        max(zona[1] - cm[1], 0.0, cm[1] - zona[4]))
        ab = doc.scene[apoyo].shape.bounding_box()
        fila.update({"zona": [round(z, 1) for z in zona], "dz_bajo_mm": round(dz_bajo, 1),
                     "dz_sobre_mm": round(dz_sobre, 1), "dh_mm": round(dh, 1),
                     "alto_zona_mm": round(zona[5] - zona[2], 1),
                     "apoyo_debajo": (ab.min.Z + ab.max.Z) / 2.0 < (zona[2] + zona[5]) / 2.0})
        fila["clase"] = {str(t): ("cuelga" if dz_bajo < -t else "apoya" if dz_sobre >= -t
                                  else "costado") for t in TOL_CUELGA_MM}
        # lo que la F0 propone para F2: la zona ABRAZA el CM (lo envuelve a su altura y sobre su
        # vertical: una rueda en su eje, una tapa en su boca) → apoya; tornillería y lo liviano
        # no se juzgan
        fila["abraza"] = zona[2] <= cm[2] <= zona[5] and dh <= 1.0
        filas.append(fila)
    from apolo.library.lints import _is_bolt

    for fila in filas:
        fila["tornilleria"] = any(_is_bolt(doc.scene[x], CATALOG)
                                  for x in (fila["colgada"], fila["apoyo"]))
        fila["propuesto"] = propuesta(fila)
    return {"filas": filas, "redundantes": redundantes, "con_otra_union": rigido_tambien}


def propuesta(fila: dict) -> str | None:
    """La clase de D2 con lo que propone la F0 (None: no se juzga). La tolerancia sólo afloja
    «cuelga»; «apoya» pide el CM SOBRE la zona (lo de al lado, con el CM a la altura del
    contacto, queda «costado»: SIN_EVALUAR)."""
    if fila.get("tornilleria") or fila["kg"] < KG_MIN:
        return None
    if "dz_bajo_mm" not in fila:
        return "sin_zona"
    if fila.get("abraza"):
        return "abraza"
    if fila["dz_bajo_mm"] < -TOL_PROPUESTA_MM:
        return "cuelga"
    return "apoya" if fila["dz_sobre_mm"] >= 0.0 else "costado"


# ------------------------------------------------------------------ CLI
def medir(ruta: Path) -> dict:
    from apolo.doc import Document

    doc = Document.from_apolo_bytes(ruta.read_bytes())
    nombre = ruta.name if ruta.parent.name != "rondas" else f"{ruta.parent.parent.name}/{ruta.name}"
    tipos: dict[str, int] = {}
    for j in (doc.joints or {}).values():
        tipos[j.get("type")] = tipos.get(j.get("type"), 0) + 1
    return {"apolo": nombre, "piezas": len(doc.scene), "juntas": tipos,
            "contactos": sum(1 for f in doc.fasteners.values() if f.get("kind") == "contacto"),
            "suprimidos": len(getattr(doc, "regen_suppressed", []) or []),
            "d1": d1(doc), "d2": d2(doc)}


def resumen(m: dict) -> str:
    f1 = m["d1"]["filas"]
    f2 = m["d2"]["filas"]
    cl = {t: sum(1 for f in f2 if f["clase"][str(t)] == "cuelga") for t in TOL_CUELGA_MM}
    co = sum(1 for f in f2 if f["clase"][str(TOL_CUELGA_MM[1])] == "costado")
    prop = {}
    for f in f2:
        if f.get("propuesto"):
            prop[f["propuesto"]] = prop.get(f["propuesto"], 0) + 1
    return (f"{m['apolo']}: {m['piezas']} piezas, juntas {m['juntas']} · D1 rígidas entre juntas "
            f"{len(f1)}: como está {sum(f['d1_como_esta'] for f in f1)}, propuesto "
            f"{sum(f['d1_propuesto'] for f in f1)} · D2 contactos {m['contactos']} con carga "
            f"{len(f2)}: cuelga {cl} costado {co} · propuesto {prop}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("apolos", nargs="+")
    ap.add_argument("--json", help="escribe el detalle aquí")
    a = ap.parse_args(argv)
    todo = []
    for r in a.apolos:
        m = medir(Path(r))
        todo.append(m)
        print(resumen(m), flush=True)
    if a.json:
        Path(a.json).write_text(json.dumps(todo, ensure_ascii=False, indent=1, default=str),
                                encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
