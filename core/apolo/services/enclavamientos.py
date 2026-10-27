"""El enclavamiento de cada resguardo en el 3D (plan mandos-de-seguridad, F2b): con el resguardo
CERRADO la lengüeta está dentro de la ranura de su interruptor y, si la hoja tiene junta, con el
resguardo ABIERTO está fuera. El cálculo es puro (`library/enclavamiento.py`); aquí se leen las
piezas, se emparejan y se posan. El llamador sostiene `STATE_LOCK`.

Piezas: un INTERRUPTOR es una pieza de catálogo cuya ficha nombra su actuador
(`specs.actuador`); una LENGÜETA, una pieza cuya ref es el actuador de alguna ficha del catálogo.

Emparejamiento (en este orden):
1. por DESIGNACIÓN: la del dispositivo que liga al interruptor (`add_device … pieza`) o, sin
   carril, la que lleva su nombre («Interruptor de tapa -B1»); la lengüeta cuyo nombre la lleva
   («Lengüeta -B1») es la suya, si es UNA sola;
2. el resto, por CERCANÍA: de menor a mayor distancia entre la punta y la boca de la ranura (la
   menor de la pose de diseño y los extremos de la junta de la lengüeta), cada pieza una vez.
   Si otra pieza libre queda a menos de `AMBIGUO_MM` más que la elegida, sale un aviso que las
   nombra (el par se evalúa igual): ponle la designación a la lengüeta.

Poses: la de diseño y los extremos (`lower`, `upper`) de la junta MÓVIL de la que cuelga la
lengüeta (la primera no `fija` subiendo por su cadena), con la FK del servidor
(`robotics/pose.feature_location`, las anclas se posan con la misma `Location` que la forma).
CERRADO = la de diseño si la lengüeta entra en ella, si no el primer extremo en que entra;
ABIERTO = el valor de la junta más lejano al cerrado. Sin junta, la apertura no se verifica (y
si la lengüeta está unida a una pieza que gira y no cuelga de su junta, aviso: el modelo no la
mueve al abrir).
"""

from __future__ import annotations

import re

#: Margen (mm) con que una segunda candidata hace AMBIGUO el emparejamiento por cercanía.
AMBIGUO_MM = 20.0
#: El mínimo de inserción cuando la ficha del interruptor no lo trae (mm): criterio de diseño,
#: el de `RESG-2NC` (`specs.insercion_min_mm`).
INSERCION_MIN_DEFECTO = 12.0
REGLA = "enclavamiento del resguardo"
_DESIGNACION = re.compile(r"(?<![\w-])-[A-Z]{1,3}\d+(?![\d])")


def _actuadores() -> dict[str, str]:
    """{ref de actuador: ref del interruptor que lo nombra} de todo el catálogo."""
    from apolo.library.catalog import CATALOG

    return {str(c.specs["actuador"]): ref for ref, c in CATALOG.items()
            if isinstance(getattr(c, "specs", None), dict) and c.specs.get("actuador")}


def piezas(doc) -> tuple[dict, dict]:
    """({fid interruptor: (ref, ref del actuador, inserción mínima)}, {fid lengüeta: ref})."""
    from apolo.library.catalog import CATALOG

    actuadores = _actuadores()
    cuerpos, lenguetas = {}, {}
    for fid in sorted(doc.scene):
        f = doc.scene[fid]
        ref = getattr(f, "component", None)
        if not ref or getattr(f, "is_guide", False):
            continue
        specs = getattr(CATALOG.get(ref), "specs", None) or {}
        if specs.get("actuador"):
            minimo = float(specs.get("insercion_min_mm") or INSERCION_MIN_DEFECTO)
            cuerpos[fid] = (ref, str(specs["actuador"]), minimo)
        elif ref in actuadores:
            lenguetas[fid] = ref
    return cuerpos, lenguetas


def junta_movil(doc, fid: str) -> dict | None:
    """La primera junta no `fija` subiendo por la cadena de `fid`, o None."""
    by_child = {j["child"]: j for j in doc.joints.values()}
    vistas, j = set(), by_child.get(fid)
    while j is not None and j["name"] not in vistas:
        vistas.add(j["name"])
        if j["type"] != "fija":
            return j
        j = by_child.get(j["parent"])
    return None


def _posadas(doc, fid: str, valores: dict) -> dict:
    """Las anclas de `fid` en la pose `valores` (la misma FK que posa la forma)."""
    from build123d import Pos

    from apolo.robotics.pose import feature_location

    anclas = getattr(doc.scene[fid], "anchors", None) or {}
    loc = feature_location(doc.joints, valores, fid) if valores else None
    if loc is None:
        return anclas
    out = {}
    for nombre, a in anclas.items():
        o, e = [float(x) for x in a["origin"]], [float(x) for x in a["axis"]]
        p0 = (loc * Pos(*o)).position
        p1 = (loc * Pos(*(o[i] + e[i] for i in range(3)))).position
        out[nombre] = {"origin": (p0.X, p0.Y, p0.Z), "axis": (p1.X - p0.X, p1.Y - p0.Y, p1.Z - p0.Z)}
    return out


def _poses(doc, lengueta: str) -> tuple[dict | None, list[float]]:
    j = junta_movil(doc, lengueta)
    if j is None:
        return None, [0.0]
    vals = [0.0]
    for v in (float(j.get("lower", 0.0)), float(j.get("upper", 0.0))):
        if all(abs(v - w) > 1e-9 for w in vals):
            vals.append(v)
    return j, vals


def _marcos(doc, cuerpo, lengueta, junta, v):
    from apolo.library.enclavamiento import marco_lengueta, marco_ranura

    vals = {junta["name"]: v} if junta is not None else {}
    return marco_ranura(_posadas(doc, cuerpo, vals)), marco_lengueta(_posadas(doc, lengueta, vals))


def _distancia(doc, cuerpo, lengueta) -> float:
    import math

    junta, vals = _poses(doc, lengueta)
    mejor = math.inf
    for v in vals:
        mr, ml = _marcos(doc, cuerpo, lengueta, junta, v)
        if mr is not None and ml is not None:
            mejor = min(mejor, math.dist(mr[0], ml[0]))
    return mejor


def _designacion(doc, fid: str, por_pieza: dict) -> str | None:
    if fid in por_pieza:
        return por_pieza[fid]
    hallada = _DESIGNACION.findall(getattr(doc.scene[fid], "name", "") or "")
    return hallada[0] if len(hallada) == 1 else None


def emparejar(doc, cuerpos: dict, lenguetas: dict) -> tuple[list, list[dict]]:
    """([(interruptor, lengüeta)], avisos de ambigüedad). Reglas en el docstring del módulo."""
    from .electrico import modelo

    por_pieza = {d.pieza: d.designacion for d in modelo(doc).dispositivos if d.pieza}
    libres_c = {c for c in cuerpos}
    libres_l = {fid for fid in lenguetas}
    pares, avisos = [], []
    for c in sorted(cuerpos):
        des = _designacion(doc, c, por_pieza)
        if not des:
            continue
        suyas = [lg for lg in sorted(libres_l) if lenguetas[lg] == cuerpos[c][1]
                 and des in _DESIGNACION.findall(getattr(doc.scene[lg], "name", "") or "")]
        if len(suyas) == 1:
            pares.append((c, suyas[0]))
            libres_c.discard(c)
            libres_l.discard(suyas[0])
    dist = sorted((_distancia(doc, c, lg), c, lg) for c in libres_c for lg in libres_l
                  if lenguetas[lg] == cuerpos[c][1])
    for d, c, lg in dist:
        if c not in libres_c or lg not in libres_l:
            continue
        cerca = [(c2, l2) for d2, c2, l2 in dist if d2 < d + AMBIGUO_MM]
        rivales = sorted({l2 for c2, l2 in cerca if c2 == c and l2 != lg and l2 in libres_l}
                         | {c2 for c2, l2 in cerca if l2 == lg and c2 != c and c2 in libres_c})
        pares.append((c, lg))
        libres_c.discard(c)
        libres_l.discard(lg)
        if rivales:
            avisos.append({"estado": "aviso", "piezas": [c, lg, *rivales], "detalle": (
                f"emparejamiento ambiguo: la lengüeta {lg} se tomó como la de {c} por cercanía "
                f"({d:.0f} mm), pero {', '.join(rivales)} queda a menos de {AMBIGUO_MM:g} mm más. "
                "Ponle a cada lengüeta la designación de su interruptor en el nombre "
                "(«Lengüeta -B1»)")})
    return pares, avisos


def _nombre(doc, fid: str, des: str | None = None) -> str:
    f = doc.scene[fid]
    return f"{des + ' ' if des else ''}{fid} «{f.name or fid}»"


def evaluar_par(doc, cuerpo: str, lengueta: str, minimo: float, des: str | None = None) -> list[dict]:
    """Las filas del par: la del resguardo cerrado y la del abierto."""
    from apolo.library import enclavamiento as E

    junta, vals = _poses(doc, lengueta)
    quien = f"{_nombre(doc, cuerpo, des)} con su lengüeta {_nombre(doc, lengueta)}"
    estados = {}
    for v in vals:
        mr, ml = _marcos(doc, cuerpo, lengueta, junta, v)
        if mr is None or ml is None:
            sin = cuerpo if mr is None else lengueta
            return [{"estado": "aviso", "piezas": [cuerpo, lengueta], "detalle": (
                f"{quien}: {sin} no tiene las anclas del interruptor (ranura/punta y fijaciones): no se "
                "puede verificar que la lengüeta entre. Insértala de nuevo con insert_component")}]
        estados[v] = (E.insercion(mr, ml, minimo), E.fuera(mr, ml))
    cerrados = [v for v in vals if estados[v][0]["estado"] == E.INSERTADA]
    j = f"junta {junta['name']}" if junta is not None else ""
    if not cerrados:
        r = estados[0.0][0]
        extra = f" (tampoco entra en los extremos de la {j})" if len(vals) > 1 else ""
        return [{"estado": "error", "piezas": [cuerpo, lengueta], "medida": r, "detalle": (
            f"{quien}: con el resguardo cerrado la lengüeta no entra en la ranura: {E.texto(r)}{extra}. "
            "El interruptor no cierra sus NC: la máquina no arranca, o se puentea el enclavamiento. "
            f"Mueve la lengüeta (o el interruptor) hasta que entre {minimo:g}–{r['fondo_mm']:g} mm, "
            "alineada con la ranura (se mide de las anclas `ranura` y `punta`)")}]
    vc = 0.0 if 0.0 in cerrados else cerrados[0]
    filas = [{"estado": "ok", "piezas": [cuerpo, lengueta], "medida": estados[vc][0],
              "detalle": f"{quien}: cerrado, {E.texto(estados[vc][0])}"
                         + (f" ({j} = {vc:g})" if vc != 0.0 else "")}]
    if junta is None:
        filas.append(_sin_junta(doc, quien, cuerpo, lengueta))
        return filas
    vo = max(vals, key=lambda v: abs(v - vc))
    if vo == vc:
        filas.append({"estado": "no_aplica", "piezas": [cuerpo, lengueta],
                      "detalle": f"{quien}: la {j} no tiene recorrido: la apertura no se verifica"})
    elif estados[vo][1]:
        filas.append({"estado": "ok", "piezas": [cuerpo, lengueta],
                      "detalle": f"{quien}: abierto ({j} = {vo:g}), la lengüeta sale de la ranura"})
    else:
        filas.append({"estado": "error", "piezas": [cuerpo, lengueta], "medida": estados[vo][0], "detalle": (
            f"{quien}: con el resguardo abierto ({j} = {vo:g}) la lengüeta sigue en la ranura "
            f"({estados[vo][0]['profundidad_mm']:.1f} mm adentro): el interruptor no ve la apertura. "
            "Revisa el eje de la junta o la posición del interruptor")})
    return filas


def _sin_junta(doc, quien: str, cuerpo: str, lengueta: str) -> dict:
    """Fila de la apertura sin junta en la lengüeta: aviso si está unida a lo que gira."""
    for fa in doc.fasteners.values():
        otra = fa["b"] if fa["a"] == lengueta else fa["a"] if fa["b"] == lengueta else None
        jm = junta_movil(doc, otra) if otra in doc.scene else None
        if jm is not None:
            return {"estado": "aviso", "piezas": [cuerpo, lengueta, otra], "detalle": (
                f"{quien}: la lengüeta está unida a {otra}, que se mueve con la junta {jm['name']}, y no "
                "cuelga de ella: al abrir, el modelo no la mueve y la apertura no se verifica. Cuélgala "
                f"de la junta (add_joint fija con padre {otra}, o arrastrar=true en {jm['name']})")}
    return {"estado": "no_aplica", "piezas": [cuerpo, lengueta],
            "detalle": f"{quien}: la hoja del resguardo no tiene junta declarada: la apertura no se verifica"}


def regla(doc) -> list[dict] | None:
    """Las filas `{estado ok|aviso|error|no_aplica, piezas, detalle[, medida]}` de cada
    interruptor de resguardo y cada lengüeta de la escena, o None si no hay ninguno (la puerta
    da lo de siempre)."""
    cuerpos, lenguetas = piezas(doc)
    if not cuerpos and not lenguetas:
        return None
    from .electrico import modelo

    por_pieza = {d.pieza: d.designacion for d in modelo(doc).dispositivos if d.pieza}
    pares, ambiguos = emparejar(doc, cuerpos, lenguetas)
    filas = []
    for c, lg in pares:
        filas += evaluar_par(doc, c, lg, cuerpos[c][2], _designacion(doc, c, por_pieza))
    filas += ambiguos
    con_par = {x for par in pares for x in par}
    for c in sorted(set(cuerpos) - con_par):
        filas.append({"estado": "aviso", "piezas": [c], "detalle": (
            f"{_nombre(doc, c, _designacion(doc, c, por_pieza))} ({cuerpos[c][0]}) no tiene su lengüeta "
            f"{cuerpos[c][1]} modelada: no se puede verificar que entre en la ranura con el resguardo "
            f"cerrado. Insértala en la hoja del resguardo (insert_component ref={cuerpos[c][1]})")})
    for lg in sorted(set(lenguetas) - con_par):
        filas.append({"estado": "aviso", "piezas": [lg], "detalle": (
            f"la lengüeta {_nombre(doc, lg)} ({lenguetas[lg]}) no tiene interruptor que la reciba: "
            "inserta su interruptor o bórrala")})
    return filas
