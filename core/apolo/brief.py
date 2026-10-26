"""Brief de escena para el agente: el payload de la API sin mallas, recortado a lo afectado.

Funciones PURAS (dict → dict): sin HTTP, sin `Document`, sin `mcp`. Las usa el cliente fino del
MCP (`mcp_server.py` las re-exporta con el mismo nombre: los tests y los clientes las importan
de ahí) y las usará el chat de la app (plan chat-cliente-igual). La forma de UNA pieza es
`brief_pieza`, la única: la arman también el servidor (`api/scene.py::_feature_brief`, lectura
filtrada) y el cliente MCP (`_scene_brief`, tras una mutación), así que se ven igual (D16).
"""

from __future__ import annotations


def brief_pieza(
    fid: str,
    nombre: str,
    visible: bool,
    bbox,
    volumen_mm3: float,
    comando: str,
    componente: str | None = None,
    grupo: str | None = None,
    boceto: bool = False,
) -> dict:
    """La forma ÚNICA del brief sin malla de una pieza (D16 del plan chat-cliente-igual).

    Orden fijo de claves; los opcionales se OMITEN cuando no aplican (nunca `null`). Un campo
    nuevo va aquí y en los dos llamadores (`_scene_brief` lee el payload de la API;
    `_feature_brief`, la `Feature`)."""
    out = {
        "id": fid,
        "nombre": nombre,
        "visible": visible,
        "bbox": bbox,
        "volumen_mm3": volumen_mm3,
        "comando": comando,
    }
    if componente:
        out["componente"] = componente
    if grupo:
        out["grupo"] = grupo
    if boceto:
        out["boceto"] = True
    return out


def _one_or_many(one: str | None, many: list[str] | None, campo: str = "feature") -> list[str]:
    """Normaliza los params excluyentes `x` (uno) / `xs` (lote) a una lista (V6.8-A)."""
    if bool(one) == bool(many):
        raise ValueError(f"Pasa exactamente uno de los dos: `{campo}` (uno) o `{campo}s` (lote)")
    return [one] if one else list(many)


#: Con más sólidos afectados que esto, "diff" y "summary" resumen por comando (mcp-sin-friccion D1).
MAX_SOLIDOS = 40


def _por_comando(shown: list[dict], affected: set[str]) -> list[dict]:
    """Los sólidos afectados por comando afectado (los de command_id sintético `{cmd}_…` van
    con su `cmd`): `{comando, n, ejemplo, grupos?}`, en el orden en que aparecen."""
    filas: dict[str, dict] = {}
    for f in shown:
        cid = f["command_id"]
        raiz = cid if cid in affected else next(
            (a for a in sorted(affected) if cid.startswith(a + "_")), cid)
        fila = filas.setdefault(raiz, {"comando": raiz, "n": 0,
                                       "ejemplo": {"id": f["id"], "nombre": f["name"]}})
        fila["n"] += 1
        if f.get("group"):
            fila.setdefault("grupos", {})
            fila["grupos"][f["group"]] = fila["grupos"].get(f["group"], 0) + 1
    return list(filas.values())


def _scene_brief(payload: dict, detail: str = "diff") -> dict:
    """Resumen sin mallas (las mallas son para el viewport, no para el agente).

    detail controla qué sólidos se listan tras una mutación:
      - "full"    → todos los sólidos de la escena (con bbox).
      - "diff"    → solo los del/los comando(s) afectado(s) por esta operación
                    (`affected_command_ids`). Si no hay afectados (consultas), lista
                    todos. Es el default: evita volcar cientos de sólidos al editar uno.
      - "summary" → solo id/nombre/comando de los afectados (sin bbox/volumen).
    Siempre incluye `total_solidos` (conteo de la escena) y, si lista, `solidos_mostrados`. Con más de
    `MAX_SOLIDOS` afectados, "diff" y "summary" no listan: dan `solidos_afectados` y
    `por_comando` (D1 de mcp-sin-friccion).
    """
    doc = payload.get("document", {})
    feats = payload.get("features", [])
    total = payload.get("total_features", len(feats))
    affected = set(payload.get("affected_command_ids") or [])

    if detail == "full" or (detail == "diff" and not affected):
        shown = feats
    else:
        # prefijo: las piezas de un insert_project llevan command_id sintético
        # '{cmd}_{cmd_origen}' — también son "del comando afectado"
        shown = [
            f for f in feats
            if f["command_id"] in affected
            or any(f["command_id"].startswith(a + "_") for a in affected)
        ]

    out = {
        "proyecto": doc.get("name"),
        "configuraciones": doc.get("configurations"),
        "puede_deshacer": doc.get("can_undo"),
        "puede_rehacer": doc.get("can_redo"),
        "total_solidos": total,
    }
    if affected and detail != "full" and len(shown) > MAX_SOLIDOS:
        # D1 de mcp-sin-friccion: una plantilla de 297 sólidos no se lista pieza a pieza
        out["solidos_afectados"] = len(shown)
        out["por_comando"] = _por_comando(shown, affected)
        out["seguir"] = ("lista sus piezas con get_scene(name=…) o get_scene(ids=[grupo]); "
                         "detail='full' trae la escena entera")
    else:
        if detail == "summary":
            solidos = [
                {"id": f["id"], "nombre": f["name"], "comando": f["command_id"]} for f in shown
            ]
        else:
            solidos = [
                brief_pieza(
                    f["id"], f["name"], f["visible"], f["bbox"], f["volume_mm3"],
                    f["command_id"], componente=f.get("component"), grupo=f.get("group"),
                    boceto=f.get("is_guide"),
                )
                for f in shown
            ]
        out["solidos_mostrados"] = len(solidos)
        out["solidos"] = solidos
    # `variables` es verboso (~33 entradas) y se repetía en CADA mutación. Lo incluimos
    # solo cuando aporta: vista completa, consulta (sin afectados) o cuando la operación
    # tocó alguna variable (su command_id es un set_variable). Las mutaciones de geometría
    # —el caso común— ya no lo arrastran. Para verlas siempre, usar get_scene.
    var_ids = {c["id"] for c in doc.get("commands", []) if c.get("type") == "set_variable"}
    include_vars = detail == "full" or not affected or bool(affected & var_ids)
    if include_vars:
        out["variables"] = doc.get("variables")
        # trabas-de-modelado D5 (~6 kB por set_variable); sin `command_id` no se sabe cuáles
        if detail != "full" and affected and any("command_id" in v for v in out["variables"] or []):
            tocadas = variables_tocadas(out["variables"] or [], affected)
            omitidas = len(out["variables"] or []) - len(tocadas)
            if omitidas:
                out["variables"] = tocadas
                out["variables_omitidas"] = omitidas
    if payload.get("aviso_estructura"):  # alarma ambiental (V6.9-B): 0 anclajes declarados
        out["aviso_estructura"] = payload["aviso_estructura"]
    return out


def _nombres(expr: str) -> set:
    """Los identificadores de una expresión (sin `re`: este módulo no importa nada)."""
    limpio = "".join(c if c.isalnum() or c == "_" else " " for c in expr)
    return {t for t in limpio.split() if not t[0].isdigit()}


def variables_tocadas(variables: list, afectados: set) -> list:
    """Las variables de los `set_variable` afectados y las que dependen de ellas (las que las
    nombran en su expresión, en cadena), en el orden del documento (plan trabas-de-modelado, D5:
    lo que cambió y lo que arrastró, sin las ~30 que no se movieron)."""
    nombres = {v.get("name") for v in variables if v.get("command_id") in afectados}
    cambio = True
    while cambio:
        cambio = False
        for v in variables:
            if v.get("name") not in nombres and nombres & _nombres(str(v.get("expression", ""))):
                nombres.add(v.get("name"))
                cambio = True
    return [v for v in variables if v.get("name") in nombres]


def brief_apertura(payload: dict) -> dict:
    """Lo que devuelve `open_project` (V8.9 F7b, defecto 11: abrir la faja del desviador, 208
    sólidos, devolvía 63 kB y la regla de lectura es < 10 KB): la cabecera de `_scene_brief` +
    el `briefing` (resumen por GRUPO, variables, requisitos, notas). Con más de `MAX_SOLIDOS`
    sólidos no los lista uno a uno (`solidos_omitidos` + cómo seguir), y las variables van una
    sola vez (en `briefing.resumen`)."""
    out = _scene_brief(payload)
    if "briefing" in payload:
        out["briefing"] = payload["briefing"]
        if "variables" in (payload["briefing"].get("resumen") or {}):
            out.pop("variables", None)
    if len(out.get("solidos") or []) > MAX_SOLIDOS:
        out["solidos_omitidos"] = len(out.pop("solidos"))
        out.pop("solidos_mostrados", None)
        out["seguir"] = ("el resumen por grupo va en `briefing.resumen`; lista piezas con "
                         "get_scene(name=…) o get_scene(ids=[grupo])")
    return out


#: El cambio que se acaba de deshacer encabeza la pila de rehacer, y viceversa.
_PILA_DEL_PASO = {"deshecho": "redo_labels", "rehecho": "undo_labels"}


def brief_paso(payload: dict, clave: str) -> dict:
    """Brief tras deshacer (`clave="deshecho"`) o rehacer (`"rehecho"`): `_scene_brief` + la
    etiqueta del cambio revertido, para que el agente sepa qué deshizo (D9 del plan
    deshacer-con-etiqueta). Va primero: tras deshacer no hay afectados y el brief lista toda la
    escena. Sin la lista en el payload (una API vieja) o vacía, la clave se OMITE (nunca `null`).
    El brief de las demás mutaciones no lleva etiquetas: serían tokens en cada llamada."""
    out = _scene_brief(payload)
    etiquetas = (payload.get("document") or {}).get(_PILA_DEL_PASO[clave])
    return {clave: etiquetas[0], **out} if etiquetas else out
