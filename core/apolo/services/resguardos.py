"""La junta que abre cada resguardo con interruptor (plan lo-que-se-mueve, D3 y D4): la ÚNICA
resolución que usan el ítem `seguridad.resguardo_abre` de la puerta de publicación
(`library/calidad/resguardos.py`), las poses de la puerta de entrega (`assertions.delivery_poses`)
y el visor (la `junta` de cada mando del `inicio` del vivo, `juntas_en_tabla`). El llamador
sostiene STATE_LOCK.

Resguardo = un `add_device` cuya ficha tiene `modelo.tipo == resguardo`. Un resguardo FIJO (se
quita con herramienta, sin interruptor) no es un dispositivo y no entra. Su junta sale de la cadena
que ya usa la F2b de mandos-de-seguridad (`enclavamientos.py`), sin param nuevo en `add_device`:
1. el interruptor = la `pieza` del dispositivo;
2. su lengüeta (el actuador), emparejada por designación o cercanía (`enclavamientos.emparejar`):
   sin ella no se sabe qué hoja cierra el interruptor (`sin_lengueta`, también si el interruptor se
   mueve: medido en el elevador, un RESG-2NC sobre la plataforma era un detector de cadena floja y
   su junta, la del carro, no la de una hoja);
3. la junta MÓVIL de la lengüeta (`enclavamientos.junta_movil`: la primera no `fija` subiendo por su
   cadena) o, si la lengüeta no tiene, la del interruptor (el interruptor en la hoja y la lengüeta
   en el marco). Si los dos se mueven con la MISMA junta, ésa no abre el resguardo: van juntos.

Sin junta o con sólo juntas `fija`, el resguardo no tiene junta que lo abra (`motivo`). CERRADO y
ABIERTO, en `extremos` (la hoja se modela cerrada: con `lower` 0, son `lower` y `upper`); las
poses de la puerta son sus `lower` y `upper` ≠ 0.
"""

from __future__ import annotations

#: El `modelo.tipo` de la ficha de un interruptor de resguardo. Los motivos sin junta y su frase:
#: `library/calidad/resguardos.MOTIVOS`.
TIPO = "resguardo"


def _cadena(doc, fid: str | None) -> bool:
    """¿`fid` cuelga de alguna junta (también una `fija`)?"""
    return fid is not None and any(j["child"] == fid for j in doc.joints.values())


def _resolver(doc, interruptor: str | None, lengueta: str | None) -> tuple[dict | None, str | None]:
    """(junta móvil que abre el resguardo, None) o (None, motivo)."""
    from .enclavamientos import junta_movil

    if not interruptor or interruptor not in doc.scene:
        return None, "sin_pieza"
    if not lengueta:
        return None, "sin_lengueta"
    jl, ji = junta_movil(doc, lengueta), junta_movil(doc, interruptor)
    if jl is not None and ji is not None and jl["name"] == ji["name"]:
        return None, "misma_junta"
    j = jl or ji
    if j is None:
        return None, "fija" if _cadena(doc, lengueta) or _cadena(doc, interruptor) else "sin_junta"
    return j, None

def extremos(junta: dict) -> tuple[float, float]:
    """(cerrado, abierto). La hoja se modela cerrada: con el 0 (la pose de diseño) dentro del
    recorrido, cerrado = 0 y abierto = el extremo más lejano (a igual distancia, `upper`: los
    -180…180 por defecto de `add_joint`); con el 0 fuera, cerrado = el extremo más cercano."""
    lo, hi = float(junta.get("lower", 0.0)), float(junta.get("upper", 0.0))
    if lo <= 0.0 <= hi:
        return 0.0, (hi if abs(hi) >= abs(lo) else lo)
    return (lo, hi) if abs(lo) <= abs(hi) else (hi, lo)


def resguardos(doc) -> list[dict]:
    """[{designacion, ref, interruptor, lengueta, junta, cerrado, abierto} | {…, junta: None,
    motivo}] de cada dispositivo resguardo del carril, en el orden del carril; [] sin ninguno."""
    from .electrico import modelo

    devs = [d for d in modelo(doc).dispositivos if (d.modelo or {}).get("tipo") == TIPO]
    if not devs:
        return []
    from .enclavamientos import emparejar, junta_movil, piezas

    cuerpos, lenguetas = piezas(doc)
    pares = dict(emparejar(doc, cuerpos, lenguetas)[0]) if cuerpos and lenguetas else {}
    out = []
    for d in devs:
        lg = pares.get(d.pieza) if d.pieza else None
        j, motivo = _resolver(doc, d.pieza, lg)
        fila = {"designacion": d.designacion, "ref": d.ref, "interruptor": d.pieza, "lengueta": lg,
                "junta": j["name"] if j else None}
        if j is None:
            fila["motivo"] = motivo
            jm = junta_movil(doc, d.pieza) if motivo == "sin_lengueta" else None
            if jm is not None:  # el interruptor va en algo que se mueve: ¿es de un resguardo?
                fila["se_mueve_con"] = jm["name"]
        else:
            fila["tipo_junta"] = j["type"]
            fila["cerrado"], fila["abierto"] = extremos(j)
        out.append(fila)
    return out


def movidas(doc, junta: str) -> list[str]:
    """Las piezas que mueve `junta` (cuelgan de ella por su cadena de padres)."""
    by_child = {j["child"]: j for j in doc.joints.values()}
    out = []
    for fid in doc.scene:
        j, vistas = by_child.get(fid), set()
        while j is not None and j["name"] not in vistas:
            if j["name"] == junta:
                out.append(fid)
                break
            vistas.add(j["name"])
            j = by_child.get(j["parent"])
    return out


def poses(doc, filas: list[dict] | None = None) -> list[dict]:
    """Las poses de la puerta de entrega de cada resguardo con junta: sus extremos `lower` y
    `upper` ≠ 0 (el 0 es la pose de diseño), `t` = «abierto», «cerrado» o «límite», con las piezas
    que mueve (`ids`: la interferencia se acota a ellas, exacto: lo que la junta no mueve está como
    en diseño)."""
    out = []
    for r in resguardos(doc) if filas is None else filas:
        if not r.get("junta"):
            continue
        j = doc.joints[r["junta"]]
        ids = movidas(doc, r["junta"])
        for v in dict.fromkeys((float(j.get("lower", 0.0)), float(j.get("upper", 0.0)))):
            if v == 0.0:
                continue
            t = "abierto" if v == r["abierto"] else "cerrado" if v == r["cerrado"] else "límite"
            out.append({"estudio": f"apertura del resguardo {r['designacion']} (junta {r['junta']})",
                        "t": t, "joint_values": {r["junta"]: v}, "ids": ids,
                        "resguardo": r["designacion"]})
    return out


def juntas_vivo(doc) -> dict[str, dict]:
    """{designación: {junta, abierto, cerrado}} de los resguardos con junta: lo que `juntas_en_tabla`
    suma a su mando del `inicio` del vivo (D4). Lo arma `_preparar` bajo el lock."""
    return {r["designacion"]: {"junta": r["junta"], "abierto": r["abierto"], "cerrado": r["cerrado"]}
            for r in resguardos(doc) if r.get("junta")}


def juntas_en_tabla(tabla: dict, juntas: dict[str, dict]) -> dict:
    """La tabla del vivo con `junta`, `abierto` y `cerrado` en el mando de cada resguardo que la
    tiene (la UI la mueve al accionarlo). Pura; sin juntas, la tabla tal cual. Claves AGREGADAS al
    `inicio`: sin `version` (`cosim/CLAUDE.md`)."""
    if not juntas or not tabla.get("mandos"):
        return tabla
    mandos = [{**m, **juntas[m["designacion"]]}
              if m.get("tipo") == TIPO and m.get("designacion") in juntas else m
              for m in tabla["mandos"]]
    return {**tabla, "mandos": mandos}


def elementos(filas: list[dict]) -> dict:
    """{con_junta: n, sin_junta: n} sin los ceros (el detector de `puerta_hechos`)."""
    n = sum(1 for r in filas if r.get("junta"))
    return {k: v for k, v in {"con_junta": n, "sin_junta": len(filas) - n}.items() if v}
