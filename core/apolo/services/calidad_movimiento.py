"""Insumos de `movimiento.coherente` (plan lo-fijo-que-gira-y-lo-que-cuelga, D1 y F0 D1a–D1d):
cada unión RÍGIDA (`fasten` perno, soldadura o pegado) entre dos piezas que la FK mueve con juntas
de movimiento distintas, con lo que el control puro (`library/calidad/movimiento.py`) necesita
para juzgarla. El llamador sostiene STATE_LOCK.

**Candidatas.** Los pares de `delivery_inputs.uniones_entre_juntas(tocan=False)` (sin las uniones
de un super-comando de cadena) y el par padre-hijo de una junta de movimiento que además lleva una
unión rígida. Las juntas `fija` cuentan con su padre (`_juntas_que_mueven`). La excepción
`_se_tocan` de la entrega NO vale aquí: todo par empernado se toca (`union.contacto_real`) y la
F0 midió que anulaba los 12 casos reales.

**Por par**, medido:
- `juntas`: las juntas de movimiento que mueven a una y no a la otra;
- `quietas`: las piezas del par que ninguna junta de movimiento mueve;
- `coaxial_mueve` / `coaxial_quieta`: la pieza con una cara cilíndrica coaxial (± 1 mm,
  `ejes_giro.coaxial`) con una junta de giro distinta, según se mueva con ella o no (el
  alojamiento arrastrado de una chumacera; el barril de una bisagra de una pieza);
- `pose`: la prueba de pose RELATIVA (D1a): cada junta distinta movida `PASO` (grados o mm, dentro
  de sus límites); `sigue` si la distancia no crece más de `TOCA_MM` sobre la de diseño y el
  volumen común no crece más de `TOL_VOL_MM3` (giran o deslizan una sobre otra; `solapa` si es
  el volumen el que crece). None: no se pudo medir;
- `servicio`: todas sus juntas son de SERVICIO (`calidad_juntas.clasificar`, también la
  prismática);
- `eje`: la junta cuyo EJE (perno o pasador de `calidad_ejes_giro`) une las dos piezas: sólo se
  mide si alguna candidata no salió OK por geometría, y con lo que ya midió la fuente mecánica
  (`pernos_y_ejes`, memo de la corrida);
- `lazo` (sólo si lo hay): el par se une en el pivote que CIERRA un lazo declarado con
  restricciones (`calidad_lazos.py`, D4 de plegables-en-la-puerta), con su estado medido; con
  él no se corre la prueba de pose (mover una junta sin resolver el lazo lo abre).
"""

from __future__ import annotations

import math

RIGIDAS = ("perno", "soldadura", "pegado")
MOVIMIENTO = ("giratoria", "continua", "prismatica")
GIRO = ("giratoria", "continua")
PASO = 3.0          # lo que se mueve cada junta en la prueba (grados o mm)
TOCA_MM = 0.1       # la distancia puede crecer esto sobre la de diseño
TOL_VOL_MM3 = 5.0   # y el volumen común, esto


def juntas_de_movimiento(doc) -> dict:
    """{tipo: n} de las juntas que mueven piezas (el detector de `puerta_hechos`)."""
    out: dict[str, int] = {}
    for j in (doc.joints or {}).values():
        if j.get("type") in MOVIMIENTO:
            out[j["type"]] = out.get(j["type"], 0) + 1
    return out


def _candidatas(doc) -> dict[frozenset, dict]:
    """{par: {uniones, tipos, par_de_junta, juntas (de la de junta)}} de los pares rígidos."""
    from .delivery_inputs import de_cadena, uniones_entre_juntas

    es_de_cadena = de_cadena(doc)
    por_par: dict[frozenset, list] = {}
    for nombre, f in sorted(doc.fasteners.items()):
        if f.get("a") in doc.scene and f.get("b") in doc.scene:
            por_par.setdefault(frozenset((f["a"], f["b"])), []).append((nombre, f))

    def rigidas(par):
        return [(n, f.get("kind", "perno")) for n, f in por_par.get(par, [])
                if f.get("kind", "perno") in RIGIDAS]

    out = {}
    for par in uniones_entre_juntas(doc, tocan=False):
        if rigidas(par):
            out[par] = {"uniones": rigidas(par), "par_de_junta": None}
    for nombre, j in sorted((doc.joints or {}).items()):
        par = frozenset((j.get("parent"), j.get("child")))
        if j.get("type") not in MOVIMIENTO or par in out or len(par) != 2:
            continue
        if rigidas(par) and not any(es_de_cadena(f) for _n, f in por_par.get(par, [])):
            out[par] = {"uniones": rigidas(par), "par_de_junta": nombre}
    return out


def _valor_de_prueba(j: dict) -> float:
    up, lo = j.get("upper"), j.get("lower")
    if j.get("type") != "continua":
        if up is not None and float(up) > 0.0:
            return min(PASO, float(up))
        if lo is not None and float(lo) < 0.0:
            return -min(PASO, abs(float(lo)))
    return PASO


def _comun(sa, sb) -> float:
    try:
        inter = sa & sb
        return float(inter.volume) if inter is not None else 0.0
    except Exception:  # noqa: BLE001 — OCCT caprichoso: sin dato
        return math.nan


def prueba_de_pose(doc, a: str, b: str, juntas) -> dict | None:
    """D1a: {dist_diseno_mm, comun_diseno_mm3, poses: [{junta, valor, dist_mm, comun_mm3,
    sigue}], sigue} o None si no se pudo medir."""
    from apolo.kernel.measure import measure_distance
    from apolo.robotics.pose import feature_location

    fa, fb = doc.scene[a], doc.scene[b]
    try:
        d0 = float(measure_distance(fa.shape, fb.shape)["dist_mm"])
    except Exception:  # noqa: BLE001 — sin distancia no hay prueba
        return None
    base = _comun(fa.shape, fb.shape)
    out = {"dist_diseno_mm": round(d0, 2), "comun_diseno_mm3": round(base, 1), "poses": []}
    sigue = True
    for jn in sorted(juntas):
        v = _valor_de_prueba(doc.joints[jn])
        try:
            la = feature_location(doc.joints, {jn: v}, a)
            lb = feature_location(doc.joints, {jn: v}, b)
            sa = la * fa.shape if la is not None else fa.shape
            sb = lb * fb.shape if lb is not None else fb.shape
            d = float(measure_distance(sa, sb)["dist_mm"])
        except Exception:  # noqa: BLE001 — una pose que no se arma: no se pudo medir
            return None
        c = _comun(sa, sb)
        solapa = not (math.isnan(c) or math.isnan(base)) and c > base + TOL_VOL_MM3
        ok = d <= d0 + TOCA_MM and not solapa
        sigue = sigue and ok
        out["poses"].append({"junta": jn, "valor": v, "dist_mm": round(d, 2),
                             "comun_mm3": None if math.isnan(c) else round(c, 1), "sigue": ok,
                             "solapa": solapa})
    out["sigue"] = sigue
    return out


def _coaxiales(doc, fid: str, juntas) -> list[str]:
    """Las juntas de giro de `juntas` con las que `fid` tiene una cara cilíndrica coaxial."""
    from apolo.library import ejes_giro as E

    from .calidad_pernos import _cilindros

    try:
        cils = [c for s in doc.scene[fid].shape.solids() for c in _cilindros(s)]
    except Exception:  # noqa: BLE001 — sin topología: no es coaxial
        return []
    out = []
    for jn in sorted(juntas):
        j = doc.joints[jn]
        if j.get("type") not in GIRO:
            continue
        try:
            o, e = E.vec(j.get("origin")), E.unit(E.vec(j.get("axis")))
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        if e is not None and any(E.coaxial(c["p"], c["eje"], o, e) for c in cils):
            out.append(jn)
    return out


def pernos_y_ejes(doc, contexto=None) -> tuple:
    """(escena, pernos, pasadores) de `calidad_ejes_giro.marcar_ejes`: con el `contexto` de la
    corrida se mide UNA vez para la fuente mecánica y este ítem (por `is` del documento: una
    copia sin una pieza no reusa lo del original)."""
    from .calidad_ejes_giro import marcar_ejes
    from .calidad_pernos import _Escena, insumos_pernos

    def medir():
        esc = _Escena(doc.scene)
        pernos = insumos_pernos(doc, escena=esc)
        return doc, esc, pernos, marcar_ejes(doc, pernos, esc)

    if contexto is None:
        return medir()[1:]
    memo = contexto.una_vez(f"pernos_y_ejes:{id(doc)}", medir)
    return (memo if memo[0] is doc else medir())[1:]


def _ejes(doc, contexto) -> dict[str, dict]:
    """{junta: {padre, hijo, ejes: {fid}}} de las juntas de giro con su eje medido."""
    from .calidad_ejes_giro import juntas_de_giro

    juntas = {j["nombre"]: j for j in juntas_de_giro(doc)}
    if not juntas:
        return {}
    _esc, pernos, pasadores = pernos_y_ejes(doc, contexto)
    out = {n: {"padre": j["padre"], "hijo": j["hijo"], "ejes": set()} for n, j in juntas.items()}
    for p in list(pernos) + list(pasadores):
        g = p.get("giro")
        if g and g["junta"] in out:
            out[g["junta"]]["ejes"].add(p["fid"])
    return out


def _por_eje(par, juntas, ejes: dict) -> str | None:
    """La junta cuyo eje une el par: una pieza es el eje o las dos están en sus dos cuerpos."""
    for jn in sorted(juntas):
        e = ejes.get(jn)
        if not e or not e["ejes"]:
            continue
        lados = ["eje" if f in e["ejes"] else "padre" if f in e["padre"] else
                 "hijo" if f in e["hijo"] else None for f in par]
        if None not in lados and set(lados) not in ({"padre"}, {"hijo"}):
            return jn
    return None


def movimiento(doc, contexto=None) -> dict:
    """El insumo de `movimiento.coherente` (formato en `library/calidad/movimiento.py`)."""
    from .calidad_juntas import clasificar
    from .delivery_inputs import _juntas_que_mueven

    from .calidad_lazos import par_de_lazo, pivotes

    clases = clasificar(doc, MOVIMIENTO)
    lazos = pivotes(doc)
    casos = []
    for par, u in _candidatas(doc).items():
        a, b = sorted(par)
        ja, jb = _juntas_que_mueven(doc, a), _juntas_que_mueven(doc, b)
        mov = {j for j in set(ja) | set(jb) if doc.joints.get(j, {}).get("type") in MOVIMIENTO}
        distintas = ({u["par_de_junta"]} if u["par_de_junta"] else
                     {j for j in set(ja) ^ set(jb) if j in mov})
        if not distintas:
            continue
        de = {a: {j for j in ja if j in mov}, b: {j for j in jb if j in mov}}
        coax = {f: _coaxiales(doc, f, distintas) for f in (a, b)}
        con = {f for f in (a, b) if coax[f]}
        se_mueve = {f for f in (a, b) if de[f] & distintas}
        lazo = par_de_lazo(doc, a, b, de, lazos) if lazos else None
        casos.append({
            **({"lazo": lazo} if lazo else {}),
            "a": a, "b": b, "nombre_a": getattr(doc.scene[a], "name", a),
            "nombre_b": getattr(doc.scene[b], "name", b),
            "uniones": [n for n, _k in u["uniones"]],
            "tipos": sorted({k for _n, k in u["uniones"]}),
            "par_de_junta": u["par_de_junta"], "juntas": sorted(distintas),
            "quietas": sorted(f for f in (a, b) if not de[f]),
            "coaxial_mueve": sorted(con & se_mueve), "coaxial_quieta": sorted(con - se_mueve),
            "servicio": all(not clases.get(j, {"accionada": True})["accionada"] for j in distintas),
            "pose": None if lazo else prueba_de_pose(doc, a, b, distintas)})
    from apolo.library.calidad.movimiento import resuelto_sin_eje

    if any(not resuelto_sin_eje(c) for c in casos):  # el eje, sólo si hace falta (lo caro)
        ejes = _ejes(doc, contexto)
        for c in casos:
            c["eje"] = _por_eje((c["a"], c["b"]), c["juntas"], ejes)
    medidos = [{k: p[k] for k in ("nombre", "estado", "motivo", "motores", "poses") if k in p}
               for p in lazos if "estado" in p]
    return {"juntas": juntas_de_movimiento(doc), "casos": casos,
            **({"lazos": medidos} if medidos else {})}
