"""El lápiz de los símbolos ISO 1219 (plan V8.9 F5, D11): dibuja en un marco LOCAL del símbolo
(mm, origen en su ancla, Y hacia arriba, espejo vertical opcional) sobre un `SheetModel`, con los
trazos de esquema del núcleo (`drawing/esquema.py`), y lleva la caja de lo que dibujó.

Un símbolo devuelve un `Simbolo`: su caja en la lámina y sus PUERTOS (el extremo del tramo que
sale del símbolo, con la dirección hacia la que sale), que es donde la composición conecta las
líneas. Los textos (designaciones) no son parte del símbolo: los pone la composición.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..esquema import LLENO, PILOTAJE, SIMBOLO
from ..sheet import Circle, Line, Polygon, SheetModel

ARRIBA, ABAJO = "arriba", "abajo"
#: Cabeza de flecha (criterio de diseño, proporcionada a la caja de 12 mm de la válvula).
CABEZA_LARGO, CABEZA_ANCHO = 1.8, 1.4


@dataclass(frozen=True)
class Puerto:
    x: float
    y: float
    dir: str  # ARRIBA | ABAJO: hacia dónde sale la línea


@dataclass
class Simbolo:
    tipo: str
    caja: tuple[float, float, float, float]  # x0, y0, x1, y1 en la lámina
    puertos: dict[str, Puerto] = field(default_factory=dict)
    #: puntos con nombre para la composición (p. ej. «bobina:14» → bajo la bobina, «atras»)
    marcas: dict[str, tuple[float, float]] = field(default_factory=dict)


class Lapiz:
    """Dibuja en el marco local (x, y) → lámina (ox + x, oy ± y)."""

    def __init__(self, model: SheetModel, ox: float, oy: float, espejo_y: bool = False):
        self.m, self.ox, self.oy, self.sy = model, ox, oy, (-1.0 if espejo_y else 1.0)
        self._x0 = self._y0 = math.inf
        self._x1 = self._y1 = -math.inf

    def p(self, x: float, y: float) -> tuple[float, float]:
        gx, gy = self.ox + x, self.oy + self.sy * y
        self._x0, self._x1 = min(self._x0, gx), max(self._x1, gx)
        self._y0, self._y1 = min(self._y0, gy), max(self._y1, gy)
        return gx, gy

    def dir(self, d: str) -> str:
        if self.sy > 0:
            return d
        return ABAJO if d == ARRIBA else ARRIBA

    # ── primitivas ────────────────────────────────────────────────────────────────────────
    def linea(self, x1: float, y1: float, x2: float, y2: float, trazos: bool = False) -> None:
        a, b = self.p(x1, y1), self.p(x2, y2)
        self.m.lines.append(Line(a[0], a[1], b[0], b[1], PILOTAJE if trazos else SIMBOLO))

    def polilinea(self, pts, trazos: bool = False, cerrada: bool = False) -> None:
        pts = list(pts) + ([pts[0]] if cerrada else [])
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            self.linea(x1, y1, x2, y2, trazos)

    def rect(self, x: float, y: float, w: float, h: float, trazos: bool = False) -> None:
        self.polilinea([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], trazos, cerrada=True)

    def poligono(self, pts, lleno: bool = False) -> None:
        self.m.polygons.append(Polygon([[self.p(x, y) for x, y in pts]], LLENO if lleno else SIMBOLO))

    def circulo(self, x: float, y: float, r: float, lleno: bool = False) -> None:
        cx, cy = self.p(x, y)
        self.p(x - r, y - r)
        self.p(x + r, y + r)
        self.m.circles.append(Circle(cx, cy, r, LLENO if lleno else SIMBOLO))

    def arco(self, cx: float, cy: float, r: float, a1: float, a2: float, n: int = 8) -> None:
        """Arco como polilínea (los arcos de la lámina son de la rosca, con otro trazo)."""
        pts = [(cx + r * math.cos(math.radians(a1 + (a2 - a1) * i / n)),
                cy + r * math.sin(math.radians(a1 + (a2 - a1) * i / n))) for i in range(n + 1)]
        self.polilinea(pts)

    def cabeza(self, x: float, y: float, ux: float, uy: float, lleno: bool = True) -> None:
        """Cabeza de flecha con la punta en (x, y) apuntando hacia (ux, uy) (unitario)."""
        bx, by = x - ux * CABEZA_LARGO, y - uy * CABEZA_LARGO
        nx, ny = -uy * CABEZA_ANCHO / 2, ux * CABEZA_ANCHO / 2
        self.poligono([(x, y), (bx + nx, by + ny), (bx - nx, by - ny)], lleno=lleno)

    def flecha(self, x1: float, y1: float, x2: float, y2: float) -> None:
        """Vía de paso (ISO 1219-1): línea con punta llena en (x2, y2)."""
        lx, ly = x2 - x1, y2 - y1
        n = math.hypot(lx, ly) or 1.0
        ux, uy = lx / n, ly / n
        self.linea(x1, y1, x2 - ux * CABEZA_LARGO * 0.6, y2 - uy * CABEZA_LARGO * 0.6)
        self.cabeza(x2, y2, ux, uy)

    def ajustable(self, cx: float, cy: float, largo: float = 8.0) -> None:
        """La flecha oblicua de «regulable» (ISO 1219-1) centrada en (cx, cy), a 45°."""
        d = largo / 2 / math.sqrt(2)
        self.flecha(cx - d, cy - d, cx + d, cy + d)

    def muelle(self, x: float, y: float, ancho: float, alto: float, horizontal: bool = True,
               picos: int = 4) -> None:
        """Muelle en zigzag desde (x, y): a lo largo de X (`horizontal`) o de Y."""
        pts = []
        for i in range(2 * picos + 1):
            t = i / (2 * picos)
            off = 0.0 if i in (0, 2 * picos) else (alto / 2 if i % 2 else -alto / 2)
            pts.append((x + t * ancho, y + off) if horizontal else (x + off, y + t * ancho))
        self.polilinea(pts)

    def puerto(self, x: float, y: float, d: str) -> Puerto:
        gx, gy = self.p(x, y)
        return Puerto(round(gx, 4), round(gy, 4), self.dir(d))

    def marca(self, x: float, y: float) -> tuple[float, float]:
        return (round(self.ox + x, 4), round(self.oy + self.sy * y, 4))

    def caja(self) -> tuple[float, float, float, float]:
        return (round(self._x0, 4), round(self._y0, 4), round(self._x1, 4), round(self._y1, 4))

    def simbolo(self, tipo: str, puertos: dict[str, Puerto], marcas: dict | None = None) -> Simbolo:
        return Simbolo(tipo, self.caja(), dict(puertos), dict(marcas or {}))
