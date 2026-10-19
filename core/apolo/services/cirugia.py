"""Cirugía de modelo: qué arrastra borrar comandos y qué se fue con ellos (plan cirugia-liviana).

`dependientes` (D2) decide, sobre el log, qué más tocar para que el borrado no deje referencias
colgando: los `fasten` y `ground` que nombran una pieza de los comandos borrados se van con ellos,
y los grupos que listan un comando borrado lo pierden como miembro. Juntas y mates NO se
arrastran: definen el mecanismo y quitarlos es decisión del agente (el error estricto del
documento los nombra). Un grupo que quedaría vacío no se toca (`register_group` exige un
miembro y otro comando puede nombrarlo): lo dice un aviso.

`foto` + `diff_borrado` (D1) arman la respuesta liviana de `POST /api/commands/remove?detail=diff`:
las piezas y uniones que desaparecieron y el total, sin la escena con mallas.

Puro: lee un `Document` explícito, sin locks (el llamador sostiene `STATE_LOCK`).
"""

from __future__ import annotations

#: Comandos que sólo DECLARAN una relación sobre piezas → se van con ellas (D2), y sus claves.
ARRASTRABLES: dict[str, tuple[str, ...]] = {"fasten": ("a", "b"), "ground": ("feature",)}

#: Uniones del documento que la respuesta liviana compara antes/después: (atributo, tipo).
_UNIONES = (("fasteners", "fijador"), ("grounds", "anclaje"), ("joints", "junta"),
            ("mates", "mate"), ("constraints", "restriccion"))


def piezas_de(doc, command_ids) -> set[str]:
    """Feature ids que crearon esos comandos, también los prefijados `{cmd}_{orig}` de un
    `insert_project` (misma regla que el brief `detail="diff"`)."""
    ids = set(command_ids)
    return {fid for fid, f in doc.scene.items()
            if f.command_id in ids or any(f.command_id.startswith(c + "_") for c in ids)}


def dependientes(doc, ids: list[str]) -> dict:
    """D2: lo que hay que borrar y editar además de `ids` para no dejar referencias colgando.

    Devuelve `{"ids": pedidos + arrastrados (sin repetir, en orden), "dependientes": [{id, tipo,
    nombre}], "ediciones": {cmd_grupo: params}, "grupos_editados": [{grupo, quitados}],
    "avisos": [str]}`. No valida que `ids` existan: eso lo dice el documento al borrar."""
    pedidos = list(dict.fromkeys(ids))
    piezas = piezas_de(doc, pedidos)
    fuera = set(pedidos)
    arrastrados: list[dict] = []
    for c in doc.commands:
        claves = ARRASTRABLES.get(c["type"])
        params = c.get("params") or {}
        if claves and c["id"] not in fuera and any(params.get(k) in piezas for k in claves):
            arrastrados.append({"id": c["id"], "tipo": c["type"], "nombre": params.get("name", "")})
            fuera.add(c["id"])
    ediciones: dict[str, dict] = {}
    grupos: list[dict] = []
    avisos: list[str] = []
    for c in doc.commands:
        params = c.get("params") or {}
        if c["type"] != "create_group" or c["id"] in fuera:
            continue
        miembros = list(params.get("members") or [])
        quitados = [str(m) for m in miembros if str(m) in fuera]
        if not quitados:
            continue
        nombre = params.get("name", c["id"])
        quedan = [m for m in miembros if str(m) not in fuera]
        if not quedan:
            avisos.append(f"El grupo «{nombre}» quedaría vacío: no se tocó (bórralo si sobra)")
            continue
        ediciones[c["id"]] = {**params, "members": quedan}
        grupos.append({"grupo": nombre, "quitados": quitados})
    return {"ids": [*pedidos, *(d["id"] for d in arrastrados)], "dependientes": arrastrados,
            "ediciones": ediciones, "grupos_editados": grupos, "avisos": avisos}


def foto(doc) -> dict:
    """Lo que la respuesta liviana compara: piezas {id: nombre}, uniones {(tipo, nombre)} y
    grupos. Se toma ANTES de borrar, bajo el mismo lock."""
    return {"piezas": {fid: f.name for fid, f in doc.scene.items()},
            "uniones": {(tipo, n) for attr, tipo in _UNIONES for n in getattr(doc, attr)},
            "grupos": set(doc.groups)}


def diff_borrado(doc, antes: dict, borrados: list[str]) -> dict:
    """D1: la respuesta corta de un borrado — comandos borrados, piezas y uniones que
    desaparecieron (y grupos, si alguno se fue) + `total_solidos`. Sin escena ni mallas."""
    ahora = foto(doc)
    out: dict = {
        "comandos_borrados": list(borrados),
        "piezas_borradas": [{"id": fid, "nombre": nombre} for fid, nombre in antes["piezas"].items()
                            if fid not in ahora["piezas"]],
        "uniones_borradas": [{"nombre": n, "tipo": t}
                             for t, n in sorted(antes["uniones"] - ahora["uniones"])],
    }
    grupos = sorted(antes["grupos"] - ahora["grupos"])
    if grupos:
        out["grupos_borrados"] = grupos
    out["total_solidos"] = len(doc.scene)
    return out
