"""Cotas PURAS del bastidor EMPERNADO y de la tornillería modelada del transportador de rodillos
por cadena (`create_roller_conveyor`, plan `docs/plans/plantilla-rodillos-cadena.md`, F9: E11,
E15 y E18). Sin `Document` ni OCCT; la receta está en `commands/receta_rodillos_bastidor.py`.

E11 — `union: "empernado"`: el bastidor se desarma en largueros + patas + travesaños.
- Cada pata lleva soldada una PLACA DE CABEZA (con su placa de pie y la tuerca del pie: lo
  soldado queda dentro de la pata, que se transporta entera) atornillada al ala horizontal del
  larguero con 2 pernos M10 por fuera del tubo (la llave entra junto a él, bajo la placa).
- Cada travesaño lleva soldada una OREJA en cada extremo atornillada a la cara interior de la
  pata con 2 pernos M10 pasantes; dentro de la pata, un BUJE soldado por perno: el tubo hueco no
  se aplasta al apretar (E15, la misma regla que el portamotor).

E18 — toda unión `perno` de la plantilla con `mantenimiento` lleva su largo: modelada (perno +
tuerca de catálogo, el largo de `fijacion.largo_perno`, estricto) o, si no se modela, con la
designación en la nota («M6x12 DIN 933»).
"""

from __future__ import annotations

from .catalog import CATALOG
from .engineering.bolts import clearance_hole_mm
from .fijacion import largo_perno

PERNO = "M10"                 # pernos del bastidor y de las orejas
PLACA_CABEZA_T = 8.0          # placa de cabeza de la pata
PLACA_CABEZA_DX = 60.0        # media placa a lo largo del larguero
PERNO_CABEZA_DX = 42.0        # pernos a ±42 del eje de la pata: por fuera del tubo y de la llave
PERNO_CABEZA_DY = 38.0        # del alma hacia afuera: zona plana del ala (talón + t + r1)
OREJA_T = 6.0                 # oreja del travesaño (la misma chapa del portamotor)
OREJA_DX = 30.0
OREJA_DZ = 62.0
PERNO_TRAV_DZ = 45.0          # pernos de la oreja a ±45 del eje del travesaño
BUJE_RE = 8.0                 # buje Ø16 dentro de la pata, del agujero al otro lado
# E16: pestañas del cárter (al pie de su pared interior, atornilladas a la base con M6)
PESTANA_T, PESTANA_X, PESTANA_Y = 3.0, 40.0, 20.0


def d_de(size: str) -> float:
    from .engineering.bolts import nominal_diameter_mm

    return nominal_diameter_mm(size)


def paso(size: str = PERNO) -> float:
    """Ø del agujero de paso (ISO 273, serie media)."""
    return clearance_hole_mm(size)


def largo(size: str, agarre: float) -> float:
    """El largo de CATÁLOGO del perno DIN 933 con su tuerca DIN 934 (≥ 2 hilos fuera)."""
    return largo_perno(size, agarre, estricto=True)


def largo_minimo(size: str, minimo: float) -> float:
    """El largo de catálogo del PERNO-HEX más corto ≥ `minimo` (ValueError si no hay)."""
    from .largos_perno import largo_comercial

    L = largo_comercial(f"PERNO-HEX-{size}", minimo)
    if L is None:
        raise ValueError(f"ningún perno {size} de catálogo llega a {minimo:.0f} mm")
    return float(L)


def designacion(size: str, largo_mm: float, norma: str = "DIN 933") -> str:
    return f"{size}x{largo_mm:g} {norma}"


def pata_t() -> float:
    return float(CATALOG["TUBO-2X2"].specs["wall"])


def pata_w() -> float:
    return float(CATALOG["TUBO-2X2"].specs["width"])


def cabeza(est_x: float, y_cara: float, lado: float, z_bajo_larguero: float) -> dict:
    """Placa de cabeza de la pata bajo el ala horizontal (`lado` −1 = larguero −Y: el ala va
    hacia −Y desde `y_cara`, la cara interior del alma) y sus 2 pernos."""
    ala = float(CATALOG["ANG-75X6"].specs["leg"])
    t_ala = float(CATALOG["ANG-75X6"].specs["t"])
    y0, y1 = sorted((y_cara, y_cara + lado * (ala - 3.0)))
    yp = y_cara + lado * PERNO_CABEZA_DY
    return {"x0": est_x - PLACA_CABEZA_DX, "x1": est_x + PLACA_CABEZA_DX, "y0": y0, "y1": y1,
            "z0": z_bajo_larguero - PLACA_CABEZA_T, "z1": z_bajo_larguero,
            "pernos": [(est_x - PERNO_CABEZA_DX, yp), (est_x + PERNO_CABEZA_DX, yp)],
            "agarre": PLACA_CABEZA_T + t_ala, "z_ala": z_bajo_larguero + t_ala}


def oreja_travesano(est_x: float, z: float) -> dict:
    return {"x0": est_x - OREJA_DX, "x1": est_x + OREJA_DX, "z0": z - OREJA_DZ, "z1": z + OREJA_DZ,
            "pernos": [(est_x, z - PERNO_TRAV_DZ), (est_x, z + PERNO_TRAV_DZ)],
            "agarre": OREJA_T + pata_w()}
