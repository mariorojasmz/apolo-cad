"""Los mandos de PUERTA de un tablero (plan V8.5 D2 regla 5, A7, D5 con la puerta cerrada).

Cuadrícula de `Reglas.paso_puerta_mm` desde arriba y desde el lado OPUESTO a la bisagra (el
primer centro a `borde_puerta_mm` de ese lado y de arriba), recorrida por filas. Cada mando toma
la primera celda libre donde lo de DETRÁS de la puerta (`Aparato.fondo`) deja ≥
`holgura_puerta_mm` sobre todo lo de la placa que cae en su huella (aparatos y canaletas): en
`w`, la cara exterior de la puerta está en `fondo_util + espesor_puerta`, así que su trasera
queda en esa cota menos lo de detrás. Orden: lo que ocupa VARIAS celdas primero (el panel de
operador: plan plc-en-el-lazo, D12), después Q (el seccionador), S (mandos), P (señalización),
el resto; dentro, por designación; un `orden` del override manda. Un mando con `posicion` fija
se valida igual (dentro de la placa, sin pisar otro mando, con holgura).

Lo más grande que una celda toma ⌈ancho/paso⌉ × ⌈alto/paso⌉ celdas contiguas y se centra en el
bloque; como va primero, toma el bloque de arriba lejos de la bisagra. Lo que cabe en una celda
se coloca exactamente como antes (un tablero sin panel se arma idéntico).

Puro (marco y tipos en `colocacion_modelo.py`); devuelve (colocados, problemas).
"""

from __future__ import annotations

import math

from .colocacion_modelo import Aparato, Colocado, Gabinete, Reglas, orden_natural, ordenar

_RANGO_FUNCION = {"Q": 0, "S": 1, "P": 2}

#: (u0, v0, u1, v1, w_frente, nombre): lo de la placa que puede quedar detrás de un mando.
Obstaculo = tuple[float, float, float, float, float, str]


def bloque(a: Aparato, r: Reglas) -> tuple[int, int]:
    """Las celdas (columnas, filas) que ocupa un aparato de puerta: ⌈ancho/paso⌉ × ⌈alto/paso⌉."""
    pu, pv = r.paso_puerta_mm
    return max(1, math.ceil(a.ancho / pu - 1e-9)), max(1, math.ceil(a.alto / pv - 1e-9))


def _clave_con(r: Reglas):
    def clave(a: Aparato) -> tuple:
        nx, ny = bloque(a, r)
        return (0 if nx * ny > 1 else 1, _RANGO_FUNCION.get(a.funcion, 3), orden_natural(a.designacion))
    return clave


def _falta(u0, v0, u1, v1, trasera: float, obstaculos: list[Obstaculo], holgura: float):
    """(lo que falta de holgura, contra qué) en esa huella; (≤ 0, None) si entra."""
    peor, contra = float("-inf"), None
    for ou0, ov0, ou1, ov1, frente, nombre in obstaculos:
        if ou0 < u1 and u0 < ou1 and ov0 < v1 and v0 < ov1:
            falta = frente + holgura - trasera
            if falta > peor:
                peor, contra = falta, nombre
    return peor, contra


def _ejes(gab: Gabinete, r: Reglas) -> tuple[list[float], list[float]]:
    """Los centros de las columnas (desde el lado opuesto a la bisagra) y de las filas (desde
    arriba) de la cuadrícula de la puerta."""
    pu, pv = r.paso_puerta_mm
    bu, bv = r.borde_puerta_mm
    W, H = gab.placa_ancho, gab.placa_alto
    us, k = [], 0
    while True:
        uc = W - bu - k * pu if gab.bisagra == "izquierda" else bu + k * pu
        if not 0 <= uc <= W:
            break
        us.append(uc)
        k += 1
    vs, k = [], 0
    while H - bv - k * pv >= 0:
        vs.append(H - bv - k * pv)
        k += 1
    return us, vs


def _centros(us: list[float], vs: list[float], nx: int, ny: int) -> list[tuple[float, float]]:
    """Los centros de cada bloque de nx × ny celdas contiguas, por filas (una celda: la celda)."""
    return [(sum(us[i:i + nx]) / nx, sum(vs[j:j + ny]) / ny)
            for j in range(len(vs) - ny + 1) for i in range(len(us) - nx + 1)]


def colocar_puerta(aps: list[Aparato], gab: Gabinete, r: Reglas, overrides: dict,
                   obstaculos: list[Obstaculo]) -> tuple[list[Colocado], list[str]]:
    exterior = gab.fondo_util + gab.espesor_puerta
    h = r.holgura_puerta_mm
    W, H = gab.placa_ancho, gab.placa_alto
    puestos: list[Colocado] = []
    problemas: list[str] = []

    def nuevo(a: Aparato, u0: float, v0: float, fila: str) -> Colocado:
        return Colocado(a.designacion, a.ref, "puerta", u0, v0, a.ancho, a.alto,
                        exterior - a.fondo, exterior + a.delante, fila, None, a.pieza)

    def libre(u0, v0, u1, v1) -> bool:
        return not any(p.solapa(u0, v0, u1, v1) for p in puestos)

    fijos = [a for a in aps if "posicion" in (overrides.get(a.designacion) or {})]
    for a in fijos:
        p = overrides[a.designacion]["posicion"]
        u0, v0 = float(p["u"]), float(p["v"])
        u1, v1 = u0 + a.ancho, v0 + a.alto
        if u0 < 0 or v0 < 0 or u1 > W or v1 > H:
            problemas.append(f"{a.designacion} en {{u: {u0:g}, v: {v0:g}}} sale de la puerta "
                             f"(placa útil {W:g}×{H:g})")
        elif not libre(u0, v0, u1, v1):
            problemas.append(f"{a.designacion} en {{u: {u0:g}, v: {v0:g}}} pisa otro mando de la puerta")
        falta, contra = _falta(u0, v0, u1, v1, exterior - a.fondo, obstaculos, h)
        if falta > 0:
            problemas.append(f"{a.designacion} en {{u: {u0:g}, v: {v0:g}}}: lo de detrás "
                             f"({a.fondo:g} mm) choca con {contra}: faltan {falta:.0f} mm de "
                             f"fondo (holgura {h:g})")
        puestos.append(nuevo(a, u0, v0, "fija"))
    pu, pv = r.paso_puerta_mm
    us, vs = _ejes(gab, r)
    n_celdas = len(us) * len(vs)
    for a in ordenar([a for a in aps if a not in fijos], overrides, clave=_clave_con(r)):
        nx, ny = bloque(a, r)
        celdas = _centros(us, vs, nx, ny)
        if not celdas:
            problemas.append(f"{a.designacion} ({a.ref}, {a.ancho:g}×{a.alto:g}) pide {nx}×{ny} celdas "
                             f"de {pu:g}×{pv:g} y la puerta tiene {len(us)}×{len(vs)}: dale una "
                             "`posicion` en overrides o un gabinete más grande")
            continue
        mejor = None  # (falta, contra) de la celda menos mala, para el mensaje
        for uc, vc in celdas:
            u0, v0 = uc - a.ancho / 2, vc - a.alto / 2
            u1, v1 = u0 + a.ancho, v0 + a.alto
            if u0 < 0 or v0 < 0 or u1 > W or v1 > H or not libre(u0, v0, u1, v1):
                continue
            falta, contra = _falta(u0, v0, u1, v1, exterior - a.fondo, obstaculos, h)
            if falta <= 0:
                puestos.append(nuevo(a, u0, v0, "puerta"))
                break
            if mejor is None or falta < mejor[0]:
                mejor = (falta, contra)
        else:
            if mejor is None:
                pide = f", pide {nx}×{ny} contiguas" if nx * ny > 1 else ""
                problemas.append(f"{a.designacion}: no queda celda libre en la puerta "
                                 f"({n_celdas} de {pu:g}×{pv:g} en {W:g}×{H:g}{pide})")
            else:
                problemas.append(f"{a.designacion}: no hay lugar en la puerta sin chocar con lo de "
                                 f"la placa; la mejor celda deja lo de detrás ({a.fondo:g} mm) sobre "
                                 f"{mejor[1]} y faltan {mejor[0]:.0f} mm de fondo (holgura {h:g})")
    return puestos, problemas
