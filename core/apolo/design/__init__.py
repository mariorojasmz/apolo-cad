"""Criterio de diseño de Apolo: el conocimiento de ingeniería que cualquier
agente debe aplicar POR DEFECTO al diseñar en el CAD (máquinas, muebles,
estructuras, lo que sea). Fuente única de verdad; la sirve la API
(`GET /api/design-guidelines`), el tool MCP `get_design_guidelines` y el prompt
del agente de chat (todos clientes de este mismo módulo)."""

from __future__ import annotations

from .guidelines import (
    DESIGN_PRINCIPLE,
    DESIGN_RULES,
    design_brief,
    design_guidelines,
)

__all__ = [
    "DESIGN_PRINCIPLE",
    "DESIGN_RULES",
    "design_brief",
    "design_guidelines",
]
