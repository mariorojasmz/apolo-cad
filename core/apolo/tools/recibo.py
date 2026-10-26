"""Recibo y resultado de una mutación por JOB (V6.5e), para `mcp_server.py`.

Salieron de `mcp_server.py` (congelado por el trinquete de tamaño) sin cambiar nada: el servidor
los re-exporta con el mismo nombre (`_job_receipt`, `_job_result`). Puros: sin HTTP ni
`apolo.mcp_server`.
"""

from __future__ import annotations

import json

from apolo.brief import _scene_brief


def job_receipt(job_id: str, estado: str = "corriendo") -> str:
    """El RECIBO de una mutación que no terminó dentro de la espera."""
    seguir = f"llama get_job('{job_id}') para recoger el resultado"
    return json.dumps({"job": job_id, "estado": estado, "seguir": seguir}, ensure_ascii=False)


def job_result(payload: dict, detail: str) -> dict:
    """Brief de un job = el de la vía síncrona; sin `features` (ya liviano) pasa tal cual. El
    contrato y las uniones que expandió cada fasten por conjuntos (mcp-sin-friccion D4) pasan.
    Con `detail="summary"` suma `comandos`: el id de comando de cada acción, EN ORDEN (los
    `affected_command_ids` del API: en un lote, `$k` = `comandos[k-1]`; en edit_batch, los
    editados), también de lo que no crea sólidos (add_device, fasten, set_variable)
    ([pedidos-de-extensiones-ii](../../../docs/plans/pedidos-de-extensiones-ii.md) D6)."""
    out = _scene_brief(payload, detail) if "features" in payload else dict(payload)
    if detail == "summary" and "features" in payload and payload.get("affected_command_ids"):
        out["comandos"] = list(payload["affected_command_ids"])
    for clave in ("contrato", "uniones_expandidas", "avisos_expresion"):
        if clave in payload:
            out[clave] = payload[clave]
    return out
