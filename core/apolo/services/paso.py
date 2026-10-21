"""La respuesta corta de deshacer y rehacer: qué cambió en el paso (plan mcp-sin-friccion, D1).

`POST /api/undo|redo?detail=diff` responde con el DIFF del paso en vez de la escena con mallas,
como el borrado liviano de `cirugia.py`: los comandos que se fueron, volvieron o cambiaron, las
piezas y uniones que aparecieron o desaparecieron, las variables que cambiaron y el total. Sin
`detail`, la escena completa de siempre (la UI).

`foto` se toma ANTES de mover la pila y `diff_paso` DESPUÉS, bajo el mismo `STATE_LOCK` que
sostiene el llamador. Puro: lee un `Document` explícito, sin locks.
"""

from __future__ import annotations

import copy

from .cirugia import foto as foto_cirugia
from .cirugia import piezas_de

#: Cuántos elementos lista cada clave antes de recortar y declarar `<clave>_omitidas`.
MAX_LISTA = 40

#: El cambio que se acaba de deshacer encabeza la pila de rehacer, y viceversa.
_PILA = {"deshecho": "redo_labels", "rehecho": "undo_labels"}


def foto(doc) -> dict:
    """Lo que `diff_paso` compara: la foto del borrado (piezas, uniones, grupos) más el log por
    id y las variables resueltas."""
    out = foto_cirugia(doc)
    out["comandos"] = {c["id"]: copy.deepcopy(c) for c in doc.commands}
    out["variables"] = _variables(doc)
    return out


def _variables(doc) -> dict:
    """{nombre: {name, expression, value}}: la forma de `variables` en la escena (sin el
    command_id, que no cambia al deshacer)."""
    out: dict[str, dict] = {}
    for c in doc.commands:
        if c["type"] == "set_variable":
            nombre = c["params"]["name"]
            out[nombre] = {"name": nombre, "expression": c["params"]["expression"]}
    for nombre, v in out.items():
        v["value"] = doc.variables_resolved.get(nombre)
    return out


def recortar(out: dict, clave: str, items: list, maximo: int = MAX_LISTA) -> None:
    """Pone `items` en `out[clave]` (si hay) recortado a `maximo`; lo que sobra se declara en
    `<clave>_omitidas` (sin recortes silenciosos)."""
    if not items:
        return
    out[clave] = items[:maximo]
    if len(items) > maximo:
        out[f"{clave}_omitidas"] = len(items) - maximo


def diff_paso(doc, antes: dict, clave: str, pasos: int = 1) -> dict:
    """D1: la respuesta corta de un deshacer (`clave="deshecho"`) o rehacer (`"rehecho"`).

    `clave` lleva la etiqueta del cambio revertido (la lista de las `pasos` etiquetas si son
    varios; se omite sin etiqueta). Comandos `quitados`/`restaurados`/`editados` por id; piezas
    `nuevas`/`borradas` con nombre y `piezas_editadas` = las de los comandos editados (también
    por prefijo `{cmd}_`); uniones por nombre y tipo; `variables` = sólo las que cambiaron. Cada
    lista se recorta a `MAX_LISTA` con su `_omitidas`."""
    ahora = foto(doc)
    out: dict = {}
    etiquetas = list(getattr(doc, _PILA[clave]) or [])
    if etiquetas:
        out[clave] = etiquetas[0] if pasos <= 1 else etiquetas[:pasos]
    cmds_antes, cmds_ahora = antes["comandos"], ahora["comandos"]
    editados = [cid for cid, c in cmds_ahora.items()
                if cid in cmds_antes and cmds_antes[cid] != c]
    recortar(out, "comandos_quitados", [cid for cid in cmds_antes if cid not in cmds_ahora])
    recortar(out, "comandos_restaurados", [cid for cid in cmds_ahora if cid not in cmds_antes])
    recortar(out, "comandos_editados", editados)
    piezas_antes, piezas_ahora = antes["piezas"], ahora["piezas"]
    recortar(out, "piezas_nuevas", [{"id": fid, "nombre": n} for fid, n in piezas_ahora.items()
                                    if fid not in piezas_antes])
    recortar(out, "piezas_borradas", [{"id": fid, "nombre": n} for fid, n in piezas_antes.items()
                                      if fid not in piezas_ahora])
    tocadas = piezas_de(doc, editados) & set(piezas_antes)
    recortar(out, "piezas_editadas", [{"id": fid, "nombre": piezas_ahora[fid]}
                                      for fid in piezas_ahora if fid in tocadas])
    recortar(out, "uniones_nuevas", [{"nombre": n, "tipo": t}
                                     for t, n in sorted(ahora["uniones"] - antes["uniones"])])
    recortar(out, "uniones_borradas", [{"nombre": n, "tipo": t}
                                       for t, n in sorted(antes["uniones"] - ahora["uniones"])])
    vars_antes, vars_ahora = antes["variables"], ahora["variables"]
    cambiadas = [v for n, v in vars_ahora.items() if vars_antes.get(n) != v]
    cambiadas += [{"name": n, "borrada": True} for n in vars_antes if n not in vars_ahora]
    recortar(out, "variables", cambiadas)
    out["total_solidos"] = len(doc.scene)
    out["puede_deshacer"] = doc.can_undo
    out["puede_rehacer"] = doc.can_redo
    return out
