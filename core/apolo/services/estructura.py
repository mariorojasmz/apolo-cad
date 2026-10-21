"""La estructura propuesta de un documento (planes uniones-en-lote D3 y mcp-sin-friccion D6).

`propuesta_estructura` arma, sobre el grafo de soporte de `assembly.autodetect.detect_structure`
(qué se toca y qué carga a qué), las acciones `ground`/`fasten` que faltan declarar, listas para
un lote. El TIPO de cada unión lo decide el criterio de taller (`criterio_uniones.py`: lo
desmontable va atornillado, lo que gira no se suelda, la tuerca es parte de su perno, la guarda
no se fija a lo que gira); lo que el criterio no declara va en `omitidas`, salvo que sin esa
unión una pieza quede suelta (entonces se propone a revisar). Es la fuente única de `POST
/api/assembly/declare`: con `aplicar` el endpoint las ejecuta; sin él, las devuelve para que el
agente las corrija y las aplique él, idealmente en pocas órdenes con los CONJUNTOS de `fasten`.

Cada acción lleva `{type, params}` (el formato de `run_batch`); la que hay que revisar suma
`a_revisar: true` y su `motivo` FUERA de `params` (un lote ignora esas claves). `resumen` agrupa
las uniones por la raíz de sus piezas (la copia `c57_3` del patrón `c57` → `c57`, la misma regla
de `commands/exec_uniones.py`): cada fila es candidata a UN `fasten` en lote. El modo corto para
el agente está en `estructura_corta.py`.

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


def roles_de(doc) -> dict[str, tuple[str, str]]:
    """{id: (rol de unión, cuerpo)} de toda la escena (`roles.rol_union`); los tramos de nombre
    que nombran un grupo (la máquina de una plantilla) no cuentan como rol."""
    from apolo.library.catalog import CATALOG

    from .roles import rol_union

    maquinas = set(doc.groups) | {g.rsplit("/", 1)[-1] for g in doc.groups}
    out = {}
    for fid, feat in doc.scene.items():
        comp = CATALOG.get(getattr(feat, "component", None) or "")
        out[fid] = rol_union(getattr(feat, "name", ""), comp.category if comp else None,
                             comp.name if comp else None, maquinas)
    return out


def uniones_con_criterio(doc, det: dict) -> list[dict]:
    """Los candidatos de `det` con el tipo del criterio de taller (`kind` None = no se declara).
    Una omitida sin la cual alguna pieza sujeta quedaría suelta vuelve, a revisar."""
    from apolo.assembly.autodetect import piezas_que_giran
    from apolo.library.materials import piece_role

    from .criterio_uniones import criterio
    from .roles import BED_RE

    camas = {fid for fid, f in doc.scene.items() if BED_RE.search(piece_role(f.name))}
    roles = roles_de(doc)
    uniones = criterio({k: r for k, (r, _) in roles.items()}, det["fasteners"],
                       piezas_que_giran(doc.scene, doc.joints), camas,
                       cuerpos={k: c for k, (_, c) in roles.items() if c})
    for u in uniones:
        u["motivo"] = f"'{_nombre(doc, u['a'])}' ↔ '{_nombre(doc, u['b'])}'" + (
            f": {u['motivo']}" if u["motivo"] else "")
    _sin_piezas_sueltas(doc, det, uniones)
    return uniones


def _sin_piezas_sueltas(doc, det: dict, uniones: list[dict]) -> None:
    """Devuelve (a revisar) las omitidas que dejan suelta una pieza que la geometría sujetaba."""
    from apolo.assembly.connectivity import build_graph, soundness_report

    sujetas = {g["feature"] for g in det["grounds"]} | {
        x for f in det["fasteners"] for x in (f["a"], f["b"])}
    semillas = {g["feature"] for g in det["grounds"]}
    while True:
        aristas = [(u["a"], u["b"], u["kind"], "") for u in uniones if u["kind"]]
        grafo = build_graph(doc.scene, doc.joints, doc.mates, doc.fasteners, doc.grounds,
                            extra_edges=aristas, extra_grounds=semillas)
        sueltas = sujetas - set(soundness_report(grafo)["grounded"])
        volver = [u for u in uniones if u["kind"] is None and (u["a"] in sueltas or u["b"] in sueltas)]
        if not volver:
            return
        for u in volver:
            u["kind"], u["a_revisar"] = "contacto", True
            u["motivo"] += "; sin esta unión la pieza queda suelta: ¿cómo se sujeta?"


def propuesta_estructura(doc) -> dict:
    """`{acciones, resumen, omitidas}`: lo que `declare` aplicaría, sin repetir lo declarado.

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
    omitidas: list[dict] = []
    for u in uniones_con_criterio(doc, det):
        par = frozenset((u["a"], u["b"]))
        if par in pares:
            continue
        pares.add(par)
        if u["kind"] is None:
            omitidas.append({"a": u["a"], "b": u["b"], "motivo": u["motivo"]})
            continue
        revisar = bool(u["a_revisar"])
        accion: dict = {"type": "fasten", "params": {
            "name": unico("auto_f_"), "a": u["a"], "b": u["b"], "kind": u["kind"],
            "nota": ((_A_REVISAR if revisar else "") + u["motivo"])[:_NOTA_MAX]}}
        if revisar:
            accion["a_revisar"] = True
            accion["motivo"] = u["motivo"]
        acciones.append(accion)
    return {"acciones": acciones, "resumen": resumen(doc, acciones), "omitidas": omitidas}


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
