"""Geometría del bloqueo de vástago (plan bloqueo-de-vastago D1, D10). Módulo propio, como cada
familia: `builders.py` está congelado por el trinquete de tamaño.

MARCO LOCAL: +X = el eje del vástago hacia la CARGA; el origen es el centro de la cara del lado
del CILINDRO (la que apoya en su tapa delantera). Un sólido: el cuerpo prismático `ancho` (Y) ×
`alto` (Z) × `largo` (X) y, si `B` > 0, el centrado cilíndrico Ø `B` × `VD` en la cara de la
carga; los dos atravesados por el agujero del vástago, de Ø `d` EXACTO: el vástago entra a ras
(contacto INTENCIONAL; la holgura real es la tolerancia f7–h7 de la ficha, no una cota del
modelo).

Las cotas son las de los `params` de cada ref (YAML, con su fuente). Ninguna es inventada aquí.
"""

from __future__ import annotations

from build123d import Box, Cylinder, Pos, Rotation


def _cil_x(r: float, x0: float, x1: float):
    return Pos((x0 + x1) / 2.0, 0, 0) * (Rotation(0, 90, 0) * Cylinder(r, x1 - x0))


def bloqueo_vastago(**params):
    p = dict(params)

    def build(length):
        L = float(p["largo"])
        forma = Pos(L / 2.0, 0, 0) * Box(L, float(p["ancho"]), float(p["alto"]))
        x1 = L
        if float(p.get("B") or 0) > 0 and float(p.get("VD") or 0) > 0:
            x1 = L + float(p["VD"])
            forma = forma + _cil_x(float(p["B"]) / 2.0, L - 0.5, x1)
        return forma - _cil_x(float(p["d"]) / 2.0, -1.0, x1 + 1.0)

    return build


def anclas(**p) -> dict:
    """Anclas LOCALES: `vastago` (el eje, hacia la carga), `cara_cilindro` (apoya en la tapa
    delantera del cilindro) y `cara_carga` (donde va la brida o la carga; el frente del centrado
    si lo hay)."""
    L = float(p["largo"])
    frente = L + (float(p.get("VD") or 0) if float(p.get("B") or 0) > 0 else 0.0)
    return {"vastago": {"origin": [0.0, 0.0, 0.0], "axis": [1.0, 0.0, 0.0]},
            "cara_cilindro": {"origin": [0.0, 0.0, 0.0], "axis": [-1.0, 0.0, 0.0]},
            "cara_carga": {"origin": [frente, 0.0, 0.0], "axis": [1.0, 0.0, 0.0]}}


BUILDERS = {"bloqueo_vastago": bloqueo_vastago}
ANCLAS = {"bloqueo_vastago": anclas}
