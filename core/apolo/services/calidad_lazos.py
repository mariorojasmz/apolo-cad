"""El pivote que CIERRA un lazo, como eje de `movimiento.coherente` (plan plegables-en-la-puerta,
D4 y su F0). El llamador sostiene STATE_LOCK.

La FK es un árbol: el compás de una mesa plegable (pata → brazo inferior → rodilla → brazo
superior → buje del tablero) cierra un LAZO que el árbol no representa, y su último pivote no es
una junta. Se declara con dos restricciones (`assembly/constraints.py`), cada una anclada al hijo
de su junta: `distancia` (la rodilla a `value` mm del pivote) y `punto_coincidente` (el extremo
del brazo EN el pivote); el `point` del `punto_coincidente` es el pivote y su `axis`, el eje.

**Qué es un pivote de lazo**: cada `punto_coincidente` sobre una junta de giro. Sus restricciones
son las de las juntas de su cadena (la suya y las que la mueven hacia arriba); los MOTORES, las
juntas de movimiento de esa cadena que ninguna restricción resuelve.

**Cuándo cuenta como eje** (`estado` OK), medido:
- el `axis` está DECLARADO (el comando lo trae en sus params: el default X del modelo no es el
  eje de nadie). Si falta, SIN_EVALUAR: el comando no cambia su contrato, la puerta lo pide;
- el lazo cierra en la pose de diseño (residuo ≤ `RESIDUO_LAZO_MM`, todas las juntas en 0);
- con cada motor movido la prueba de pose (`calidad_movimiento._valor_de_prueba`),
  `solve_constraints` lo vuelve a cerrar (residuo ≤ `RESIDUO_LAZO_MM`): si no, esa pose sale
  SIN_EVALUAR, nunca OK (el solver no avisa cuando no converge);
- hay al menos un motor (un lazo que nada mueve no prueba que gire).

**Por par** (`par_de_lazo`): las dos piezas de una unión rígida tienen una cara cilíndrica cuya
recta pasa a ≤ 1 mm del pivote; una se mueve con la junta del `punto_coincidente` y la otra no.
La OTRA tiene que ser la pieza raíz (ninguna junta de movimiento la mueve): el `point` de la
restricción es FIJO en el mundo, así que un lazo que cierra sobre una pieza que se mueve (la
escalera de tijera, con el tirante sobre el larguero trasero) no se representa → SIN_EVALUAR con
el porqué. Con el eje declarado, las dos caras tienen que ser coaxiales con él.
"""

from __future__ import annotations

from apolo.library.calidad.item import OK, SIN_EVALUAR

COAXIAL_MM = 1.0
PASOS_CONTINUACION = 6  # pasos del motor si el solve directo no cierra el lazo


def _axis_declarado(doc, con: dict) -> bool:
    """¿El comando que declaró la restricción trae `axis`? Un `insert_project` la trae del
    donante ya transformada: cuenta como declarada si la tiene."""
    cid = con.get("command_id")
    cmd = next((c for c in doc.commands if c.get("id") == cid), None)
    if cmd is None or cmd.get("type") != "add_constraint":
        return con.get("axis") is not None
    return (cmd.get("params") or {}).get("axis") is not None


def _residuo(joints, valores, propias) -> float:
    from apolo.assembly.constraints import _residual

    return max(_residual(joints, valores, c) for c in propias.values())


def _resolver(joints, propias, motor: str, valor: float) -> float:
    """El menor residuo (mm) con que `solve_constraints` cierra el lazo con `motor` = `valor`:
    por CONTINUACIÓN (`PASOS_CONTINUACION` pasos del motor desde la pose de diseño, cada uno
    arrancando de la solución del anterior) y, si no cierra, directo desde la pose de diseño.
    Cerca del punto muerto de la rodilla (el compás casi recto) un paso chico de la pata pide
    mucho giro del compás y el arranque directo desde 0 se queda en un mínimo local (la mesa de
    1,8 m: 5,99 mm con la pata a −3° y 2,2 s de CPU; por continuación, 0 mm y 0,4 s)."""
    from apolo.assembly.constraints import solve_constraints
    from apolo.library.calidad.movimiento import RESIDUO_LAZO_MM

    deps = {c["joint"] for c in propias.values()}
    previo: dict[str, float] = {}
    for k in range(1, PASOS_CONTINUACION + 1):
        previo = solve_constraints(joints, propias,
                                   {**{j: previo.get(j, 0.0) for j in deps},
                                    motor: valor * k / PASOS_CONTINUACION})
    mejor = _residuo(joints, previo, propias)
    if mejor <= RESIDUO_LAZO_MM:
        return mejor
    return min(mejor, _residuo(joints, solve_constraints(joints, propias, {motor: valor}), propias))


def _cerrar(doc, piv: dict) -> None:
    """Mide (en sitio) si el lazo de `piv` cierra en diseño y con cada motor movido."""
    from apolo.library.calidad.movimiento import RESIDUO_LAZO_MM

    from .calidad_movimiento import MOVIMIENTO, _valor_de_prueba
    from .delivery_inputs import _juntas_que_mueven

    if "estado" in piv:
        return
    joints = doc.joints or {}
    cadena = _juntas_que_mueven(doc, joints[piv["junta"]]["child"])
    propias = {n: c for n, c in (doc.constraints or {}).items() if c.get("joint") in cadena}
    deps = {c["joint"] for c in propias.values()}
    motores = [j for j in cadena if j not in deps and joints[j].get("type") in MOVIMIENTO]
    piv.update({"restricciones": sorted(propias), "motores": motores, "poses": []})
    if not piv["axis_declarado"]:
        piv.update(estado=SIN_EVALUAR, motivo=(
            f"la restricción {piv['nombre']} no declara el eje (`axis`) del pivote: declara su "
            "dirección (la de los agujeros) con add_constraint"))
        return
    try:
        r0 = _residuo(joints, {}, propias)
    except Exception as e:  # noqa: BLE001 — una restricción que no se puede evaluar
        piv.update(estado=SIN_EVALUAR, motivo=f"el lazo {piv['nombre']} no se pudo evaluar ({e})")
        return
    piv["residuo_diseno_mm"] = round(r0, 3)
    if r0 > RESIDUO_LAZO_MM:
        piv.update(estado=SIN_EVALUAR, motivo=(
            f"el lazo {piv['nombre']} no cierra en la pose de diseño (residuo {r0:.2f} mm > "
            f"{RESIDUO_LAZO_MM:g} mm): revisa el punto, el ancla o la distancia de sus "
            "restricciones"))
        return
    if not motores:
        piv.update(estado=SIN_EVALUAR, motivo=(
            f"ninguna junta libre mueve el lazo {piv['nombre']} (todas las de su cadena las "
            "resuelven sus restricciones)"))
        return
    for m in motores:
        v = _valor_de_prueba(joints[m])
        try:
            r = _resolver(joints, propias, m, v)
        except Exception as e:  # noqa: BLE001
            piv.update(estado=SIN_EVALUAR, motivo=f"con {m} = {v:g} el lazo no se resolvió ({e})")
            return
        piv["poses"].append({"junta": m, "valor": v, "residuo_mm": round(r, 3)})
        if r > RESIDUO_LAZO_MM:
            piv.update(estado=SIN_EVALUAR, motivo=(
                f"con {m} = {v:g} el lazo {piv['nombre']} no vuelve a cerrar (residuo {r:.2f} mm > "
                f"{RESIDUO_LAZO_MM:g} mm): esa pose no se puede evaluar"))
            return
    piv["estado"] = OK


def pivotes(doc) -> list[dict]:
    """[{nombre, junta, punto, eje, axis_declarado}] de los `punto_coincidente` sobre una junta
    de giro (sin medir: `par_de_lazo` cierra el lazo sólo si un par lo usa)."""
    from apolo.library import ejes_giro as E

    from .calidad_movimiento import GIRO

    out = []
    for nombre, con in sorted((doc.constraints or {}).items()):
        j = (doc.joints or {}).get(con.get("joint"))
        if con.get("tipo") != "punto_coincidente" or j is None or j.get("type") not in GIRO:
            continue
        try:
            punto, eje = E.vec(con.get("point")), E.unit(E.vec(con.get("axis") or (0, 0, 0)))
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        out.append({"nombre": nombre, "junta": con["joint"], "punto": punto, "eje": eje,
                    "axis_declarado": _axis_declarado(doc, con) and eje is not None})
    return out


def _cilindros(doc, fid: str) -> list[dict]:
    from .calidad_pernos import _cilindros as cils

    try:
        return [c for s in doc.scene[fid].shape.solids() for c in cils(s)]
    except Exception:  # noqa: BLE001 — sin topología: no toca el pivote
        return []


def _pasa(c: dict, piv: dict) -> bool:
    from apolo.library import ejes_giro as E

    eje = E.unit(c["eje"])
    return eje is not None and E.distancia_a_recta(piv["punto"], c["p"], eje) <= COAXIAL_MM


def par_de_lazo(doc, a: str, b: str, de: dict, piv_lista: list[dict]) -> dict | None:
    """{pivote, restricciones, estado: OK | SIN_EVALUAR, motivo} si el par (a, b) se une en un
    pivote de lazo; None si no. `de` = {fid: juntas de movimiento que lo mueven}."""
    from apolo.library import ejes_giro as E

    for piv in piv_lista:
        movil = [f for f in (a, b) if piv["junta"] in de[f]]
        if len(movil) != 1:
            continue
        cils = {f: [c for c in _cilindros(doc, f) if _pasa(c, piv)] for f in (a, b)}
        if not (cils[a] and cils[b]):
            continue
        otra = b if movil[0] == a else a
        _cerrar(doc, piv)
        out = {"pivote": piv["nombre"], "restricciones": piv["restricciones"],
               "motores": piv["motores"], "poses": piv["poses"]}
        if piv["estado"] != OK:
            return {**out, "estado": SIN_EVALUAR, "motivo": piv["motivo"]}
        if not all(any(E.coaxial(c["p"], c["eje"], piv["punto"], piv["eje"]) for c in cils[f])
                   for f in (a, b)):
            return {**out, "estado": SIN_EVALUAR, "motivo": (
                f"el eje declarado de {piv['nombre']} no es el de los agujeros del pivote: "
                "corrige su `axis`")}
        if de[otra]:
            return {**out, "estado": SIN_EVALUAR, "motivo": (
                f"el lazo {piv['nombre']} cierra sobre {otra}, que mueve "
                f"{', '.join(sorted(de[otra]))}: el punto de la restricción es fijo en el mundo; "
                "la cadena del lazo tiene que cerrar en un pivote de la pieza raíz")}
        return {**out, "estado": OK, "motivo": ""}
    return None
