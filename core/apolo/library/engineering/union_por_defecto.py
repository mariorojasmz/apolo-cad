"""Dimensión POR DEFECTO de una unión que se declara sin calcularla (plan mcp-sin-friccion, D8).

La propuesta de estructura (`services/dimensionado.py`) la escribe en cada `fasten` para que
nada quede «sin dimensionar» (no verificable), y `engineering_check` la contrasta con la carga
real: si no alcanza, pide subirla. Es criterio de diseño, no norma.

- Perno: (métrica, cantidad) según el rol que manda en el par; un eje roscado usa la mayor
  métrica normalizada que cabe en su Ø, una por lado (lo calcula el servicio). Las medidas son las
  que usa la plantilla de rodillos: guarda M6, portamotor M10.
- Soldadura: garganta a = 0.707·cateto; la longitud es el perímetro de la huella de contacto y,
  si no se puede medir, `longitud_mm`.
"""

from __future__ import annotations

#: (métrica, cantidad) del perno por el rol que manda en el par; «otro» = el resto.
PERNO = {"guarda": ("M6", 2), "chumacera": ("M12", 2), "equipo": ("M10", 4), "otro": ("M10", 2)}
#: Garganta del cordón y longitud de respaldo (mm).
SOLDADURA = {"garganta_mm": 3.0, "longitud_mm": 50.0}
#: Métricas ISO normalizadas que la tabla de pernos conoce (M6–M24).
METRICAS = (6, 8, 10, 12, 16, 20, 24)
