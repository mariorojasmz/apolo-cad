"""La estructura propuesta de un documento (plan uniones-en-lote, D3).

`propuesta_estructura` arma, sobre el grafo de soporte de `assembly.autodetect.detect_structure`
(con las juntas del documento: lo que gira no se suelda, D2), las acciones `ground`/`fasten` que
faltan declarar, listas para un lote. Es la fuente única de `POST /api/assembly/declare`: con
`aplicar` el endpoint las ejecuta; sin él, las devuelve para que el agente las corrija y las
aplique él, idealmente en pocas órdenes con los CONJUNTOS de `fasten` (D1).

Cada acción lleva `{type, params}` (el formato de `run_batch`); la que hay que revisar suma
`a_revisar: true` y su `motivo` FUERA de `params` (un lote ignora esas claves). `resumen` agrupa
las uniones por la raíz de sus piezas (la copia `c57_3` del patrón `c57` → `c57`, la misma regla
de `commands/exec_uniones.py`): cada fila es candidata a UN `fasten` en lote.

Puro: lee un `Document` explícito, sin locks (el llamador sostiene `STATE_LOCK`).
"""

from __future__ import annotations

_NOTA_MAX = 120  # `FastenParams.nota` / `GroundParams.nota`
_A_REVISAR = "a revisar: "


def raiz(scene: dict, fid: str) -> str:
    """La raíz de patrón de una pieza: su comando si ella es la copia `{comando}_{n}` (lo que
    un `fasten` en lote expande con esa raíz); si no, el propio id."""
    cmd = getattr(scene.get(fid), "command_id", None)
    sufijo = fid[len(cmd) + 1:] if cmd and fid.startswith(cmd + "_") else ""
    return cmd if sufijo.isdigit() else fid


def propuesta_estructura(doc) -> dict:
    """`{acciones, resumen}`: lo que `declare` aplicaría, sin repetir lo ya declarado.

    Idempotente como el endpoint de siempre: omite anclajes de piezas ya ancladas y pares ya
    unidos (también los de un `fasten` en lote, que el documento guarda expandidos), y nombra
    `auto_g_N`/`auto_f_N` sin chocar con los nombres existentes."""
    from apolo.assembly.autodetect import detect_structure

    det = detect_structure(doc.scene, joints=doc.joints)
    nombres = set(doc.fasteners) | set(doc.grounds)
    anclados = {g["feature"] for g in doc.grounds.values()}
    pares = {frozenset((f["a"], f["b"])) for f in doc.fasteners.values()}

    def unico(prefijo: str) -> str:
        i = 1
        while f"{prefijo}{i}" in nombres:
            i += 1
        nombres.add(f"{prefijo}{i}")
        return f"{prefijo}{i}"

    acciones: list[dict] = []
    for g in det["grounds"]:
        if g["feature"] in anclados:
            continue
        anclados.add(g["feature"])
        acciones.append({"type": "ground", "params": {
            "name": unico("auto_g_"), "feature": g["feature"],
            "nota": (g.get("reason") or "")[:_NOTA_MAX]}})
    for f in det["fasteners"]:
        par = frozenset((f["a"], f["b"]))
        if par in pares:
            continue
        pares.add(par)
        motivo = f.get("reason") or ""
        revisar = bool(f.get("a_revisar"))
        accion: dict = {"type": "fasten", "params": {
            "name": unico("auto_f_"), "a": f["a"], "b": f["b"], "kind": f["kind"],
            "nota": ((_A_REVISAR if revisar else "") + motivo)[:_NOTA_MAX]}}
        if revisar:
            accion["a_revisar"] = True
            accion["motivo"] = motivo
        acciones.append(accion)
    return {"acciones": acciones, "resumen": resumen(doc, acciones)}


def resumen(doc, acciones: list[dict]) -> list[dict]:
    """Las uniones propuestas agrupadas por (tipo, revisar, raíz de cada lado), de mayor a
    menor: `{kind, a, b, n, a_revisar?, ejemplo}`. `a`/`b` son raíces; `ejemplo` nombra el
    primer par con los nombres de las piezas."""
    grupos: dict[tuple, dict] = {}
    for acc in acciones:
        if acc["type"] != "fasten":
            continue
        p = acc["params"]
        ra, rb = sorted((raiz(doc.scene, p["a"]), raiz(doc.scene, p["b"])))
        a, b = (p["a"], p["b"]) if raiz(doc.scene, p["a"]) == ra else (p["b"], p["a"])
        revisar = bool(acc.get("a_revisar"))
        clave = (p["kind"], revisar, ra, rb)
        if clave not in grupos:
            fila: dict = {"kind": p["kind"], "a": ra, "b": rb, "n": 0}
            if revisar:
                fila["a_revisar"] = True
            fila["ejemplo"] = {"a": a, "b": b, "nombres": [_nombre(doc, a), _nombre(doc, b)]}
            grupos[clave] = fila
        grupos[clave]["n"] += 1
    return sorted(grupos.values(), key=lambda g: (-g["n"], g["kind"], g["a"], g["b"]))


def _nombre(doc, fid: str) -> str:
    feat = doc.scene.get(fid)
    return getattr(feat, "name", fid) if feat is not None else fid
