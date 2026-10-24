"""Cilindros, tratamiento del aire y accesorios en el esquema ISO 1219-1 (plan V8.9 F5, D11).

Todos se dibujan con el aire SUBIENDO (ISO 1219-2: fuente abajo, actuadores arriba): la vía de
entrada abajo y la de salida arriba; el cilindro, horizontal con el vástago a la derecha y sus
vías A (fondo) y B (vástago) hacia abajo. Medidas: criterio de dibujo; lo que interpreta la figura
de la norma (no leída en esta fase) está marcado «a confirmar».
"""

from __future__ import annotations

from ..sheet import SheetModel
from .trazo import ABAJO, ARRIBA, Lapiz, Simbolo

L_CIL, H_CIL = 44.0, 12.0  # cuerpo del cilindro
VASTAGO_FUERA = 12.0  # lo que asoma el vástago retraído
STUB_CIL = 3.0


# ── cilindros ────────────────────────────────────────────────────────────────────────────────
def cilindro(m: SheetModel, x0: float, y0: float, *, efecto: str = "doble",
             amortiguacion: str = "neumatica", iman: bool = False) -> Simbolo:
    """Cilindro con el cuerpo de (x0, y0) a (x0 + 44, y0 + 12), retraído (posición de reposo).

    - doble efecto: vías A (fondo) y B (vástago); simple efecto con muelle: sólo A y el muelle del
      lado del vástago;
    - amortiguación neumática regulable: los dos casquillos del émbolo y la flecha oblicua en cada
      tapa (ISO 1219-1); elástica o sin: sin símbolo (a confirmar);
    - émbolo magnético: un bloque lleno en el émbolo (a confirmar con la figura de ISO 1219-1)."""
    lz = Lapiz(m, x0, y0)
    yc = H_CIL / 2
    lz.rect(0, 0, L_CIL, H_CIL)
    xe = 9.0  # cara izquierda del émbolo
    lz.rect(xe, 0, 2.0, H_CIL)
    fin = L_CIL + VASTAGO_FUERA
    lz.linea(xe + 2.0, yc + 1.2, fin, yc + 1.2)
    lz.linea(xe + 2.0, yc - 1.2, fin, yc - 1.2)
    lz.linea(fin, yc - 1.2, fin, yc + 1.2)
    if iman:
        lz.poligono([(xe, H_CIL - 2.6), (xe + 2.0, H_CIL - 2.6), (xe + 2.0, H_CIL - 0.9),
                     (xe, H_CIL - 0.9)], lleno=True)
    if amortiguacion == "neumatica" and efecto == "doble":
        lz.rect(xe - 2.5, yc - 2.2, 2.5, 4.4)
        lz.rect(xe + 2.0, yc - 2.2, 2.5, 4.4)
        lz.ajustable(3.6, yc, 6.0)
        lz.ajustable(L_CIL - 4.0, yc, 6.0)
    if efecto == "simple_muelle":
        lz.muelle(xe + 2.4, yc, L_CIL - xe - 3.4, H_CIL - 3.0, picos=5)
    puertos = {}
    vias = (("A", 4.0),) if efecto == "simple_muelle" else (("A", 4.0), ("B", L_CIL - 4.0))
    for via, x in vias:
        lz.linea(x, 0, x, -STUB_CIL)
        puertos[via] = lz.puerto(x, -STUB_CIL, ABAJO)
    return lz.simbolo(f"cilindro_{efecto}", puertos, {
        "atras": lz.marca(xe + 1.0, H_CIL), "adelante": lz.marca(L_CIL - 7.0, H_CIL),
        "izquierda": lz.marca(0.0, yc), "derecha": lz.marca(fin, yc)})


# ── regulador de caudal, silenciador, escape, fuente ─────────────────────────────────────────
def regulador_caudal(m: SheetModel, cx: float, y1: float, *, invertido: bool = False) -> Simbolo:
    """Regulador de caudal unidireccional: estrangulación regulable en paralelo con una
    antirretorno, en su envolvente. La vía 1 en `y1` (abajo; arriba si `invertido`) y la 2 al otro
    extremo; el paso LIBRE de la antirretorno va de 1 a 2 (la ficha da el caudal libre de 1 a 2)."""
    lz = Lapiz(m, cx, y1, espejo_y=invertido)
    xl, xr = -3.2, 3.2
    lz.linea(0, 0, 0, 4.5)
    lz.linea(xl, 4.5, xr, 4.5)
    lz.linea(xl, 13.5, xr, 13.5)
    lz.linea(0, 13.5, 0, 20.0)
    lz.rect(-6.5, 2.0, 13.0, 16.0, trazos=True)
    # estrangulación: la línea se corta entre dos arcos enfrentados, y la flecha de regulable
    lz.linea(xl, 4.5, xl, 7.0)
    lz.linea(xl, 11.0, xl, 13.5)
    lz.arco(xl - 2.6, 9.0, 2.2, -65.0, 65.0, n=6)
    lz.arco(xl + 2.6, 9.0, 2.2, 115.0, 245.0, n=6)
    lz.ajustable(xl, 9.0, 7.0)
    # antirretorno: asiento en V (vértice abajo) y la bola; libre de abajo hacia arriba
    lz.linea(xr, 4.5, xr, 7.0)
    lz.polilinea([(xr - 1.6, 8.9), (xr, 7.0), (xr + 1.6, 8.9)])
    lz.circulo(xr, 8.9, 1.15)
    lz.linea(xr, 10.05, xr, 13.5)
    return lz.simbolo("regulador_caudal", {"1": lz.puerto(0, 0, ABAJO), "2": lz.puerto(0, 20.0, ARRIBA)})


def silenciador(m: SheetModel, x: float, y: float) -> Simbolo:
    """Silenciador colgado de una vía de escape en (x, y) (su vía 1 mira hacia arriba): tramo y
    rectángulo con dos divisiones. A confirmar con la figura de ISO 1219-1."""
    lz = Lapiz(m, x, y)
    lz.linea(0, 0, 0, -2.0)
    lz.rect(-2.0, -7.5, 4.0, 5.5)
    lz.linea(-2.0, -3.85, 2.0, -3.85)
    lz.linea(-2.0, -5.65, 2.0, -5.65)
    return lz.simbolo("silenciador", {"1": lz.puerto(0, 0, ARRIBA)})


def escape(m: SheetModel, x: float, y: float) -> Simbolo:
    """Escape a la atmósfera sin conexión: triángulo hueco con la punta hacia afuera (abajo)."""
    lz = Lapiz(m, x, y)
    lz.linea(0, 0, 0, -1.4)
    lz.poligono([(-1.7, -1.4), (1.7, -1.4), (0, -4.2)])
    return lz.simbolo("escape", {"1": lz.puerto(0, 0, ARRIBA)})


def fuente(m: SheetModel, x: float, y: float) -> Simbolo:
    """Fuente de presión neumática: círculo con el triángulo HUECO (aire) apuntando a la salida;
    la vía 2 arriba."""
    lz = Lapiz(m, x, y)
    lz.circulo(0, 0, 3.0)
    lz.poligono([(0, 2.0), (-1.6, -1.1), (1.6, -1.1)])
    lz.linea(0, 3.0, 0, 5.0)
    return lz.simbolo("fuente", {"2": lz.puerto(0, 5.0, ARRIBA)})


# ── tratamiento del aire (FRL) ───────────────────────────────────────────────────────────────
def filtro(lz: Lapiz, y: float) -> float:
    """Filtro: rombo con la línea A TRAZOS perpendicular al paso. Devuelve la y de salida."""
    lz.polilinea([(0, y), (4.0, y + 4.0), (0, y + 8.0), (-4.0, y + 4.0)], cerrada=True)
    lz.linea(-4.0, y + 4.0, 4.0, y + 4.0, trazos=True)
    return y + 8.0


def regulador_presion(lz: Lapiz, y: float) -> float:
    """Regulador de presión: caja con la vía de paso, muelle regulable a la derecha y el pilotaje
    (a trazos) desde la salida al costado opuesto. Devuelve la y de salida."""
    lz.rect(-4.0, y, 8.0, 9.0)
    lz.flecha(0, y, 0, y + 9.0)
    lz.muelle(4.0, y + 4.5, 5.0, 3.6)
    lz.ajustable(6.5, y + 4.5, 6.5)
    lz.polilinea([(0, y + 10.5), (-6.0, y + 10.5), (-6.0, y + 4.5), (-4.0, y + 4.5)], trazos=True)
    return y + 9.0


def manometro(lz: Lapiz, x: float, y: float) -> None:
    """Manómetro: círculo con la flecha oblicua, a la derecha del punto (x, y) de la línea."""
    lz.linea(x, y, x + 3.0, y)
    lz.circulo(x + 5.6, y, 2.6)
    lz.flecha(x + 4.1, y - 1.5, x + 7.1, y + 1.5)


def lubricador(lz: Lapiz, y: float) -> float:
    """Lubricador: rombo con una línea LLENA perpendicular al paso (a confirmar con ISO 1219-1)."""
    lz.polilinea([(0, y), (4.0, y + 4.0), (0, y + 8.0), (-4.0, y + 4.0)], cerrada=True)
    lz.linea(-2.2, y + 4.0, 2.2, y + 4.0)
    lz.linea(0, y + 4.0, 0, y + 6.0)
    return y + 8.0


def frl(m: SheetModel, cx: float, y1: float, *, lubricador_: bool = False) -> Simbolo:
    """Unidad de mantenimiento: filtro + regulador con manómetro (+ lubricador), en su envolvente
    a trazos (ISO 1219-1 dibuja la de un conjunto a trazo y punto: a confirmar). La vía 1 abajo en
    `y1`, la 2 arriba."""
    lz = Lapiz(m, cx, y1)
    lz.linea(0, 0, 0, 4.0)
    y = filtro(lz, 4.0)
    lz.linea(0, y, 0, y + 2.0)
    y = regulador_presion(lz, y + 2.0)
    lz.linea(0, y, 0, y + 6.0)
    manometro(lz, 0, y + 3.5)
    y += 6.0
    if lubricador_:
        y = lubricador(lz, y)
        lz.linea(0, y, 0, y + 2.0)
        y += 2.0
    lz.linea(0, y, 0, y + 4.0)
    lz.rect(-7.5, 2.0, 18.0, y + 2.0 - 2.0, trazos=True)
    return lz.simbolo("frl", {"1": lz.puerto(0, 0, ABAJO), "2": lz.puerto(0, y + 4.0, ARRIBA)})


# ── presostato y detector ────────────────────────────────────────────────────────────────────
def presostato(m: SheetModel, cx: float, y1: float) -> Simbolo:
    """Presostato: el pilotaje a trazos desde su vía 1 (abajo) a una caja con el contacto
    eléctrico y el muelle regulable. A confirmar con la figura de ISO 1219-1."""
    lz = Lapiz(m, cx, y1)
    lz.linea(0, 0, 0, 1.5)
    lz.linea(0, 1.5, 0, 4.0, trazos=True)
    lz.rect(-4.0, 4.0, 8.0, 8.0)
    lz.linea(-1.5, 5.5, -1.5, 7.2)
    lz.linea(-1.5, 7.2, 1.2, 9.6)
    lz.linea(-1.5, 9.4, -1.5, 10.8)
    lz.muelle(4.0, 8.0, 4.5, 3.0)
    lz.ajustable(6.2, 8.0, 6.0)
    return lz.simbolo("presostato", {"1": lz.puerto(0, 0, ABAJO)})


def detector(m: SheetModel, x: float, y: float) -> Simbolo:
    """Detector de fin de carrera sobre el cuerpo del cilindro en (x, y): el cuadrado con el
    rombo del detector de proximidad (IEC 60617, el uso de ISO 1219-2 en esquemas
    electroneumáticos; a confirmar)."""
    lz = Lapiz(m, x, y)
    lz.linea(0, 0, 0, 1.5)
    lz.rect(-2.5, 1.5, 5.0, 5.0)
    lz.polilinea([(0, 2.3), (1.7, 4.0), (0, 5.7), (-1.7, 4.0)], cerrada=True)
    return lz.simbolo("detector", {}, {"arriba": lz.marca(0, 6.5)})
