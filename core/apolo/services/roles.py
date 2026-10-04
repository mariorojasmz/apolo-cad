"""Roles de pieza que el sistema LEE del NOMBRE (la excepción a «nombres por rol, no por
medida»: CLAUDE.md raíz § Paramétrico). Fuente única: el FEA de ensamblaje busca la cama
que recibe la carga y la lámina de instalación, la altura de trabajo y las piezas de
servicio, con los MISMOS patrones."""

from __future__ import annotations

import re

# rol de superficie de carga (recibe el producto): la cama/mesa/deck del transportador
BED_RE = re.compile(r"\b(cama|mesa|bed|deck|tablero|placa\s*sup|superficie\s*de\s*carga)\b", re.I)
# piezas que se EXTRAEN para mantenimiento → su ancho es la holgura de servicio a dejar
# libre a un costado (V7.6 fase C, lámina de instalación)
SERVICE_RE = re.compile(r"\b(motorreductor|motor|tambor|rodillo\s+de\s+cola)\b", re.I)
