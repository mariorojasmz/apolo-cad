"""Modelo de lámina: las constantes de formato (hojas ISO, margen, cajetín, escalas
normalizadas, qué acota cada vista) y las primitivas en mm (origen abajo-izquierda, Y hacia
arriba) que leen los exportadores SVG, PDF y DXF. Sale de `sheet.py` (plan
partir-nucleo-congelado-ii, F4), que lo re-exporta por IDENTIDAD.
"""

from __future__ import annotations

from dataclasses import dataclass, field


SHEETS = {
    "A0": (1189.0, 841.0), "A1": (841.0, 594.0), "A2": (594.0, 420.0),
    "A3": (420.0, 297.0), "A4": (297.0, 210.0),
}
MARGIN = 10.0
TITLE_W, TITLE_H = 160.0, 26.0
CELL_PAD = 17.0  # espacio reservado para cotas alrededor de cada vista
# escalas normalizadas (ISO 5455: preferidas + intermedias permitidas 1:2.5/1:4/1:25/1:40)
# en orden DESCENDENTE de factor → _pick_scale toma la MAYOR que entra en la celda
STANDARD_SCALES = [
    (1.0, "1:1"), (0.5, "1:2"), (0.4, "1:2.5"), (0.25, "1:4"), (0.2, "1:5"),
    (0.1, "1:10"), (0.05, "1:20"), (0.04, "1:25"), (0.025, "1:40"), (0.02, "1:50"),
    (0.01, "1:100"), (0.005, "1:200"),
]

# qué dimensiones reales (bbox 3D) acota cada vista: (horizontal, vertical)
VIEW_DIMS = {"alzado": ("X", "Z"), "planta": ("X", "Y"), "lateral": ("Y", "Z")}
VIEW_TITLES = {"alzado": "ALZADO", "planta": "PLANTA", "lateral": "PERFIL", "iso": "ISOMÉTRICA"}


@dataclass
class Line:
    x1: float
    y1: float
    x2: float
    y2: float
    kind: str  # visible | hidden | frame | dim


@dataclass
class Label:
    x: float
    y: float
    text: str
    size: float = 3.2
    anchor: str = "middle"  # start | middle | end
    rotation: float = 0.0


@dataclass
class Circle:
    x: float
    y: float
    r: float
    kind: str  # globo | dim


@dataclass
class Arc:
    """Arco de circunferencia (grados CCW desde +X). Hoy lo usa el cosmético de
    ROSCA (ISO 6410: 3/4 de vuelta en trazo fino al Ø nominal, capa DXF ROSCA)."""

    x: float
    y: float
    r: float
    a1: float
    a2: float
    kind: str = "thread"


@dataclass
class Polygon:
    rings: list[list[tuple[float, float]]]  # anillo 0 = contorno; resto = agujeros
    kind: str = "corte"
    material: str = ""  # para el rayado de sección por material (madera/vidrio/acero)


@dataclass
class Image:
    """Imagen raster (PNG) embebida — p. ej. un render 3D sombreado a color. Coords mm,
    origen abajo-izquierda (como el resto). Solo la sirven SVG/PDF; DXF (línea) la omite."""
    x: float
    y: float
    w: float
    h: float
    png: bytes


@dataclass
class SheetModel:
    width: float
    height: float
    lines: list[Line] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    circles: list[Circle] = field(default_factory=list)
    arcs: list[Arc] = field(default_factory=list)
    polygons: list[Polygon] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    hueco_iso: object = None  # isométrica sombreada reservada (fotos_planos.HuecoIso), sin dibujar

    def rect(self, x: float, y: float, w: float, h: float, kind: str = "frame") -> None:
        self.lines += [
            Line(x, y, x + w, y, kind), Line(x + w, y, x + w, y + h, kind),
            Line(x + w, y + h, x, y + h, kind), Line(x, y + h, x, y, kind),
        ]
