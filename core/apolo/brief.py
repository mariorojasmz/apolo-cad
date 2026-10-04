"""Brief de escena para el agente: el payload de la API sin mallas, recortado a lo afectado.

Funciones PURAS (dict → dict): sin HTTP, sin `Document`, sin `mcp`. Las usa el cliente fino del
MCP (`mcp_server.py` las re-exporta con el mismo nombre: los tests y los clientes las importan
de ahí) y las usará el chat de la app (plan chat-cliente-igual). Los campos espejan los de
`_feature_brief` del servidor (`api/main.py`): un campo nuevo va en los dos.
"""

from __future__ import annotations


def _one_or_many(one: str | None, many: list[str] | None, campo: str = "feature") -> list[str]:
    """Normaliza los params excluyentes `x` (uno) / `xs` (lote) a una lista (V6.8-A)."""
    if bool(one) == bool(many):
        raise ValueError(f"Pasa exactamente uno de los dos: `{campo}` (uno) o `{campo}s` (lote)")
    return [one] if one else list(many)


def _scene_brief(payload: dict, detail: str = "diff") -> dict:
    """Resumen sin mallas (las mallas son para el viewport, no para el agente).

    detail controla qué sólidos se listan tras una mutación:
      - "full"    → todos los sólidos de la escena (con bbox).
      - "diff"    → solo los del/los comando(s) afectado(s) por esta operación
                    (`affected_command_ids`). Si no hay afectados (consultas), lista
                    todos. Es el default: evita volcar cientos de sólidos al editar uno.
      - "summary" → solo id/nombre/comando de los afectados (sin bbox/volumen).
    Siempre incluye `total_solidos` (conteo de la escena) y `solidos_mostrados`.
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

    if detail == "summary":
        solidos = [
            {"id": f["id"], "nombre": f["name"], "comando": f["command_id"]} for f in shown
        ]
    else:
        solidos = [
            {
                "id": f["id"],
                "nombre": f["name"],
                "visible": f["visible"],
                "bbox": f["bbox"],
                "volumen_mm3": f["volume_mm3"],
                "componente": f["component"],
                "comando": f["command_id"],
                **({"grupo": f["group"]} if f.get("group") else {}),
                **({"boceto": True} if f.get("is_guide") else {}),
            }
            for f in shown
        ]
    # `variables` es verboso (~33 entradas) y se repetía en CADA mutación. Lo incluimos
    # solo cuando aporta: vista completa, consulta (sin afectados) o cuando la operación
    # tocó alguna variable (su command_id es un set_variable). Las mutaciones de geometría
    # —el caso común— ya no lo arrastran. Para verlas siempre, usar get_scene.
    var_ids = {c["id"] for c in doc.get("commands", []) if c.get("type") == "set_variable"}
    include_vars = detail == "full" or not affected or bool(affected & var_ids)
    out = {
        "proyecto": doc.get("name"),
        "configuraciones": doc.get("configurations"),
        "puede_deshacer": doc.get("can_undo"),
        "puede_rehacer": doc.get("can_redo"),
        "total_solidos": total,
        "solidos_mostrados": len(solidos),
        "solidos": solidos,
    }
    if include_vars:
        out["variables"] = doc.get("variables")
    if payload.get("aviso_estructura"):  # alarma ambiental (V6.9-B): 0 anclajes declarados
        out["aviso_estructura"] = payload["aviso_estructura"]
    return out
