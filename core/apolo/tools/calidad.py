"""Tool MCP `publication_gate` (plan puerta-de-publicacion, F1): la puerta de PUBLICACIÓN por la
API (`POST /api/puerta-publicacion`, como job: corre la gravedad y la marcha del video).

Cliente fino como el resto; vive fuera de `mcp_server.py` (trinquete de tamaño), que la registra al
final con `registrar(mcp, esperar)`: `esperar` es su `_submit_and_wait`, buscado en cada llamada (si
tarda más que la espera vuelve el RECIBO `{job, seguir}`). NO importa `apolo.mcp_server`
(`tests/test_mcp_registro.py`).
"""

from __future__ import annotations

import json

from .cosim import _recibo

#: Lo que el agente lee de cada ítem que no pasó (la evidencia completa, con `completo=true`).
_DEL_ITEM = ("id", "familia", "estado", "titulo", "detalle", "piezas")


def resumir(r: dict) -> dict:
    """Lo accionable: el veredicto, los conteos y SÓLO los ítems aplicables que no están OK."""
    pendientes = [{**{k: i.get(k) for k in _DEL_ITEM}, "piezas": (i.get("piezas") or [])[:12]}
                  for i in r.get("items", []) if i.get("estado") in ("FALLA", "SIN_EVALUAR")]
    out = {k: r.get(k) for k in ("aprobado", "conteos", "por_familia", "firma",
                                 "version_registro")}
    out["pendientes"] = pendientes
    if r.get("mantenimiento"):
        out["mantenimiento"] = r["mantenimiento"]
    out["segundos"] = (r.get("tiempos_s") or {}).get("total")
    return out


def registrar(mcp, esperar) -> None:
    """Registra `publication_gate` en `mcp` (el del servidor que corre)."""

    @mcp.tool()
    def publication_gate(completo: bool = False) -> str:
        """LA PUERTA DE PUBLICACIÓN: córrela ANTES de dar por terminada una máquina que va a la
        tienda (después de delivery_check en VERDE). Es más dura que la de entrega: un registro de
        ítems de calidad (estructura, función, montaje, seguridad, publicado, proceso), cada uno
        OK | FALLA | SIN_EVALUAR | NO_APLICA con su evidencia; se publica SÓLO si todo ítem
        aplicable está OK (SIN_EVALUAR bloquea igual que FALLA: «no se pudo ver» no es «está
        bien»). Corre la gravedad (obligatoria), las interferencias DENTRO de cada super-comando,
        el agarre de cada perno, el tensor y su carrera, la vida útil (L10 ≥ 20 000 h, factor de
        servicio ≥ 1,25…), la memoria de cálculo, el ERC y la marcha del video contra el modelo.
        Devuelve aprobado, conteos, por_familia y `pendientes` (cada ítem que falla o no se pudo
        evaluar, con la pieza y el porqué: corrige el MODELO, no el ítem). `completo=true` trae
        todos los ítems con su evidencia. Read-only; tarda (simula): si no llega, RECIBO {"job"}:
        get_job."""
        payload, job_id = esperar("POST", "/api/puerta-publicacion", {})
        if job_id:
            return _recibo(job_id)
        return json.dumps(payload if completo else resumir(payload), ensure_ascii=False)
