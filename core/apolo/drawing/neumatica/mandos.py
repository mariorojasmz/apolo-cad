"""Los mandos de una válvula en el esquema ISO 1219-1 (plan V8.9 F5, D11): lo que mueve el
carrete, dibujado al costado de la caja de la posición que ese mando provoca.

Cada mando ocupa un ancho a lo largo de X, hacia AFUERA de la válvula (`lado` −1 izquierda, +1
derecha), centrado en la altura de la caja; varios mandos de un lado se apilan hacia afuera en el
orden dado (el primero, pegado a la caja). Medidas: criterio de dibujo proporcionado a la caja de
12 × 10 mm. Lo que es interpretación de la figura de la norma (no leída en esta fase) está
marcado «a confirmar» en cada uno.
"""

from __future__ import annotations

from .trazo import Lapiz

#: Ancho que ocupa cada mando hacia afuera (mm).
ANCHOS = {"bobina": 4.0, "manual": 4.0, "muelle": 6.0, "pilotaje": 7.0, "palanca": 6.0,
          "retencion": 6.0}
MANDOS = tuple(ANCHOS)


def _u(x_borde: float, lado: int, u: float) -> float:
    return x_borde + lado * u


def bobina(lz: Lapiz, x_borde: float, lado: int, y0: float, h: float) -> tuple[float, float]:
    """Mando electromagnético (ISO 1219-1: rectángulo con una diagonal). Devuelve el punto bajo la
    bobina (para el rótulo de su borne)."""
    w, alto = ANCHOS["bobina"] - 0.5, min(h * 0.7, 7.0)
    yb = y0 + (h - alto) / 2
    xa, xb = _u(x_borde, lado, 0.0), _u(x_borde, lado, w)
    x0, x1 = min(xa, xb), max(xa, xb)
    lz.rect(x0, yb, x1 - x0, alto)
    lz.linea(x0, yb, x1, yb + alto)
    return ((x0 + x1) / 2, yb)


def manual(lz: Lapiz, x_borde: float, lado: int, y0: float, h: float) -> None:
    """Accionamiento manual auxiliar: pulsador (tramo horizontal con un semicírculo afuera).
    A confirmar con la figura de ISO 1219-1 (general: barra; pulsador: semicírculo)."""
    yc = y0 + h / 2
    lz.linea(_u(x_borde, lado, 0.0), yc, _u(x_borde, lado, 2.6), yc)
    xc = _u(x_borde, lado, 2.6)
    a1, a2 = (90.0, 270.0) if lado < 0 else (-90.0, 90.0)
    lz.arco(xc, yc, 1.2, a1, a2, n=6)


def muelle(lz: Lapiz, x_borde: float, lado: int, y0: float, h: float) -> None:
    """Retorno por muelle (zigzag)."""
    w = ANCHOS["muelle"] - 0.6
    x = min(_u(x_borde, lado, 0.0), _u(x_borde, lado, w))
    lz.muelle(x, y0 + h / 2, w, min(h * 0.6, 5.0))


def pilotaje(lz: Lapiz, x_borde: float, lado: int, y0: float, h: float) -> None:
    """Pilotaje neumático: la línea de pilotaje (a trazos) que entra a un triángulo HUECO (aire;
    el lleno es hidráulico) apuntando a la válvula. A confirmar con ISO 1219-1."""
    yc = y0 + h / 2
    punta, base = _u(x_borde, lado, 0.0), _u(x_borde, lado, 2.4)
    lz.poligono([(punta, yc), (base, yc + 1.4), (base, yc - 1.4)])
    lz.linea(base, yc, _u(x_borde, lado, ANCHOS["pilotaje"] - 0.2), yc, trazos=True)


def palanca(lz: Lapiz, x_borde: float, lado: int, y0: float, h: float) -> None:
    """Palanca manual (tramo oblicuo con una bola en la punta). A confirmar con ISO 1219-1."""
    yc = y0 + h / 2
    lz.linea(_u(x_borde, lado, 0.0), yc, _u(x_borde, lado, 4.4), yc + 3.0)
    lz.circulo(_u(x_borde, lado, 4.9), yc + 3.35, 0.6)


def retencion(lz: Lapiz, x_borde: float, lado: int, y0: float, h: float) -> None:
    """Enclavamiento (retención de posición): una barra con muescas en V y el trinquete. A
    confirmar con ISO 1219-1."""
    yc = y0 + h / 2
    w = ANCHOS["retencion"] - 0.6
    xs = [_u(x_borde, lado, t * w) for t in (0.0, 0.2, 0.35, 0.5, 0.65, 0.8, 1.0)]
    lz.polilinea([(xs[0], yc), (xs[1], yc), (xs[2], yc + 1.4), (xs[3], yc), (xs[4], yc + 1.4),
                  (xs[5], yc), (xs[6], yc)])
    lz.linea(xs[3], yc + 2.6, xs[3], yc + 0.6)


DIBUJO = {"bobina": bobina, "manual": manual, "muelle": muelle, "pilotaje": pilotaje,
          "palanca": palanca, "retencion": retencion}


def dibujar(lz: Lapiz, mandos, x_borde: float, lado: int, y0: float, h: float) -> dict:
    """Apila `mandos` hacia afuera desde `x_borde`; devuelve {«bobina»: punto bajo la bobina}."""
    marcas: dict = {}
    u = 0.0
    for tipo in mandos:
        if tipo not in DIBUJO:
            raise ValueError(f"mando desconocido «{tipo}»; mandos: {', '.join(MANDOS)}")
        x = _u(x_borde, lado, u)
        out = DIBUJO[tipo](lz, x, lado, y0, h)
        if tipo == "bobina":
            marcas["bobina"] = out
        u += ANCHOS[tipo]
    return marcas


def ancho(mandos) -> float:
    return sum(ANCHOS[t] for t in mandos)
