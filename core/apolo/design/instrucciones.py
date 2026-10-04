"""Instrucciones de los clientes IA: UNA sola guía (plan chat-cliente-igual, D9).

El MCP las recibe enteras como `instructions` (`instrucciones_mcp()`, byte-idéntica a la de
antes de este módulo: lo congela `tests/test_mcp_golden.py`). El chat de la app recibirá
`design_brief()` + `GUIA_TECNICA` + sus reglas propias (F6), sin `AVISO_CONEXION`: corre dentro
de la API, nunca la encuentra apagada.
"""

from __future__ import annotations

from .guidelines import design_brief

#: Cómo se trabaja con el CAD por tools: unidades, log, `$k`, expresiones, cómo verificar y
#: cómo elegir selectores. Va a los dos clientes. OJO: «combínalo con set_visibility para
#: aislar» contradice a `render_view(isolate=…)`; lo corrige la F6 del plan (D10), que cambia
#: el golden a propósito.
GUIA_TECNICA = (
    "CAD paramétrico Genix Apolo. Unidades mm, eje Z arriba, primitivas centradas. "
    "El documento es un log de comandos: cada operación es editable y deshacible. "
    "Consulta get_command_schemas para los parámetros de cada comando; usa '$k' en lotes "
    "para referenciar sólidos creados en el mismo lote, y '=expresión' en campos numéricos "
    "para usar variables del proyecto (resuélvelas con resolve_expression y consulta la "
    "gramática con get_expression_grammar). Verifica tus montajes con check_interference y "
    "render_view (highlight_ids resalta una pieza; combínalo con set_visibility para aislar). "
    "Para elegir bien una arista/cara antes de fillet/chamfer/drill/add_mate, mira la geometría "
    "con get_topology(id) y traduce a un selector declarativo (cara/direccion/longitud/cerca). "
    "Antes de escribir, PRUEBA en seco con test_sketch/test_script (no tocan el "
    "documento) y valida una faja por sus parámetros con engineering_check(conveyor=...). "
    "get_command(id) devuelve los parámetros actuales de un comando para editarlo."
)

#: Sólo el MCP por stdio: la API puede no estar arrancada.
AVISO_CONEXION = (
    "Si una llamada falla con error de conexión, el servidor Apolo no está arrancado "
    "(uvicorn apolo.api.main:app --port 8000)."
)


def instrucciones_mcp() -> str:
    """`instructions` del servidor MCP: criterio de ingeniería SIEMPRE presente (capa 1, el
    detalle está en `get_design_guidelines`, capa 2) + la guía técnica + el aviso de conexión."""
    return design_brief() + "\n\n" + GUIA_TECNICA + " " + AVISO_CONEXION
