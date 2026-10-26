"""Lo que comparten las verificaciones del chequeo estructural (`report.py`).

La gravedad, las categorías de catálogo con rodamiento interno y el nombre en
minúsculas de una pieza; vive aparte para que `report_uniones`, `report_estructura`
y `report_ajustes` no importen `report` (que los importa a ellos).
"""

from __future__ import annotations


G = 9.81


# categorías de catálogo con rodamiento interno (llevan C_kN en specs)
_BEARING_CATS = {"rodamientos", "chumaceras"}


def _name(f) -> str:
    return (getattr(f, "name", "") or "").lower()
