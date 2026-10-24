"""Trazos de esquema para una lámina (plan puntos-de-extension-entregables, D6): lo que necesita
una extensión que dibuja esquemas (eléctricos, neumáticos) con el motor de láminas del núcleo,
sin que el núcleo sepa de símbolos.

Dos estilos, para `Line`, `Circle` y `Polygon` de `sheet.py`, que los tres exportadores (SVG, PDF
y DXF) dibujan igual:

- `SIMBOLO`: trazo negro sin relleno (el cuerpo de un símbolo y la línea de conexión);
- `LLENO`: negro relleno (el punto de unión de dos conductores, una punta de flecha).

Grosor (criterio de diseño, sobre la serie de anchos de línea de ISO 128): un esquema se dibuja
con UN solo ancho para símbolos y conexiones, como pide la práctica de IEC 61082-1; se usa
0,35 mm, el ancho medio de la serie, legible en A3 y en una copia reducida a A4. El punto de
unión mide `D_UNION_MM` de diámetro (≈ 3,5 veces el trazo: se distingue de un cruce sin unión
aun reducido). Las láminas mecánicas no usan estos estilos y no cambian de aspecto.

El color es el negro de las aristas visibles del núcleo (`NEGRO`), no uno nuevo.

Un tercer estilo, sólo para `Line` (plan V8.9 F5, el esquema ISO 1219):

- `PILOTAJE`: el mismo trazo, CORTADO (la línea de pilotaje y la envolvente de un conjunto, que
  ISO 1219-1 dibuja a trazos). Trazos de 12·d y huecos de 3·d con d = el grosor (el tipo de línea
  02 de ISO 128-20, criterio de diseño); en DXF, el tipo de línea `APOLO_TRAZOS` en la capa del
  esquema, que se crea sólo si la lámina lo usa.
"""

from __future__ import annotations

from .sheet import Circle, Line, Polygon, SheetModel

SIMBOLO = "simbolo"
LLENO = "simbolo_lleno"
PILOTAJE = "simbolo_trazos"
ESTILOS = (SIMBOLO, LLENO, PILOTAJE)
TRAZO_X_GROSOR, HUECO_X_GROSOR = 12.0, 3.0  # ISO 128-20, tipo 02 (trazos): 12·d y 3·d
TIPO_LINEA_DXF = "APOLO_TRAZOS"

NEGRO = "#16181d"  # el de las aristas visibles y el texto de los exportadores
GROSOR_SIMBOLO_MM = 0.35
D_UNION_MM = 1.2

CAPA_DXF = "ESQUEMA"  # (capa, color ACI 7 = negro/blanco, continua, 0,35 mm)
LINEWEIGHT_DXF = 35  # 1/100 mm


def pt(mm: float) -> float:
    """mm → puntos tipográficos (el PDF de matplotlib mide los grosores en pt)."""
    return mm * 72.0 / 25.4


def conductor(model: SheetModel, x1: float, y1: float, x2: float, y2: float) -> Line:
    """Una línea de conexión (o un trazo recto de un símbolo), con el grosor del esquema."""
    linea = Line(x1, y1, x2, y2, SIMBOLO)
    model.lines.append(linea)
    return linea


def pilotaje(model: SheetModel, x1: float, y1: float, x2: float, y2: float) -> Line:
    """Una línea a trazos del esquema (pilotaje, envolvente), con el grosor del esquema."""
    linea = Line(x1, y1, x2, y2, PILOTAJE)
    model.lines.append(linea)
    return linea


def trazos_mm() -> tuple[float, float]:
    """(trazo, hueco) en mm de la línea `PILOTAJE`."""
    return TRAZO_X_GROSOR * GROSOR_SIMBOLO_MM, HUECO_X_GROSOR * GROSOR_SIMBOLO_MM


def circulo(model: SheetModel, x: float, y: float, r: float, lleno: bool = False) -> Circle:
    """Un círculo de símbolo (un motor, una lámpara, un borne): sin relleno salvo `lleno`."""
    c = Circle(x, y, r, LLENO if lleno else SIMBOLO)
    model.circles.append(c)
    return c


def punto_union(model: SheetModel, x: float, y: float, d: float = D_UNION_MM) -> Circle:
    """El punto de unión de conductores: un círculo negro relleno de diámetro `d`."""
    return circulo(model, x, y, d / 2.0, lleno=True)


def poligono(model: SheetModel, puntos: list[tuple[float, float]], lleno: bool = False) -> Polygon:
    """Un contorno cerrado de símbolo (una bobina, un fusible, una flecha `lleno`)."""
    if len(puntos) < 3:
        raise ValueError("un polígono de símbolo necesita al menos 3 puntos")
    p = Polygon([list(puntos)], LLENO if lleno else SIMBOLO)
    model.polygons.append(p)
    return p
