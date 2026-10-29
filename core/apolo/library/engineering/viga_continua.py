"""Viga continua sobre N apoyos: flecha, momento flector y reacciones (Euler-Bernoulli).

Para las vigas de un bastidor armado a mano ([flecha-de-bastidor](../../../../docs/plans/flecha-de-bastidor.md)
D3): un larguero con sus apoyos (uniones a lo que baja a tierra), voladizos en los extremos y
cargas puntuales y repartidas (peso propio, lo que cuelga, la carga útil). PURO y sin
dependencias: recibe números, nunca un `Document`.

Método: rigidez directa con elementos de viga de Hermite (EI constante). Con las cargas
repartidas como fuerzas nodales CONSISTENTES, los desplazamientos nodales son EXACTOS para
Euler-Bernoulli (no es una aproximación de malla); dentro de cada elemento se suma la solución
particular empotrada-empotrada, q·s²(h−s)²/(24·EI), así que la elástica y el momento también son
exactos en todo punto. La malla sólo fija DÓNDE se muestrea el máximo (≤ L/120 por elemento,
10 muestras por elemento: el error de ubicar el pico es < 1e-6 relativo).

Convenciones: x en mm desde el extremo izquierdo; cargas y flechas POSITIVAS HACIA ABAJO
(gravedad); momento positivo = flexión positiva (tracciona la fibra inferior, centro de vano);
reacciones positivas HACIA ARRIBA — una negativa es TRACCIÓN (el apoyo sujeta, no soporta) y se
publica tal cual, jamás se recorta a cero. Unidades: mm, N, N/mm, N·mm, EI en N·mm².
"""

from __future__ import annotations

import math
from dataclasses import dataclass

APOYO = "apoyo"  # restringe el desplazamiento (articulado / deslizante)
EMPOTRAMIENTO = "empotramiento"  # restringe desplazamiento y giro
G = 9.81

#: Elementos mínimos en el largo total y muestras por elemento (sólo ubican el máximo).
_ELEMENTOS = 120
_MUESTRAS = 10
_TOL_X = 1e-9  # relativa al largo: puntos más cercanos se funden


@dataclass(frozen=True)
class Apoyo:
    x_mm: float
    tipo: str = APOYO


@dataclass(frozen=True)
class CargaPuntual:
    x_mm: float
    p_n: float  # + hacia abajo


@dataclass(frozen=True)
class CargaRepartida:
    q_n_mm: float  # + hacia abajo
    desde_mm: float = 0.0
    hasta_mm: float | None = None  # None = hasta el extremo derecho


@dataclass(frozen=True)
class Tramo:
    """Trozo entre apoyos consecutivos (`vano`) o de un apoyo al extremo libre (`voladizo`)."""

    desde_mm: float
    hasta_mm: float
    tipo: str  # "vano" | "voladizo"
    flecha_max_mm: float  # la de mayor valor absoluto, con signo (+ abajo)
    flecha_x_mm: float

    @property
    def largo_mm(self) -> float:
        return self.hasta_mm - self.desde_mm


@dataclass(frozen=True)
class ResultadoViga:
    flecha_max_mm: float  # mayor |flecha| de toda la viga, con signo (+ abajo)
    flecha_x_mm: float
    momento_max_nmm: float  # mayor |M|, con signo
    momento_x_mm: float
    momento_positivo_nmm: float  # máximo M ≥ 0 (centro de vano)
    momento_negativo_nmm: float  # mínimo M ≤ 0 (sobre apoyos / empotramiento)
    reacciones_n: tuple[float, ...]  # por apoyo, en el ORDEN de entrada; + hacia arriba
    tramos: tuple[Tramo, ...]


def q_peso_propio_n_mm(kg_por_m: float) -> float:
    """Carga repartida (N/mm) del peso propio de un perfil de `kg_por_m`."""
    return float(kg_por_m) * G / 1000.0


def _validar(largo: float, ei: float, apoyos, puntuales, repartidas) -> None:
    if largo <= 0:
        raise ValueError("la viga necesita largo > 0")
    if ei <= 0:
        raise ValueError("la viga necesita EI > 0")
    tol = _TOL_X * largo
    for a in apoyos:
        if a.tipo not in (APOYO, EMPOTRAMIENTO):
            raise ValueError(f"tipo de apoyo desconocido: {a.tipo!r}")
        if not -tol <= a.x_mm <= largo + tol:
            raise ValueError(f"apoyo fuera de la viga: x = {a.x_mm} mm (largo {largo} mm)")
    xs = sorted(a.x_mm for a in apoyos)
    if any(b - a <= tol for a, b in zip(xs, xs[1:])):
        raise ValueError("dos apoyos en el mismo punto: declara uno solo")
    if not any(a.tipo == EMPOTRAMIENTO for a in apoyos) and len(apoyos) < 2:
        raise ValueError("viga inestable: necesita dos apoyos o un empotramiento")
    for c in puntuales:
        if not -tol <= c.x_mm <= largo + tol:
            raise ValueError(f"carga fuera de la viga: x = {c.x_mm} mm")
    for c in repartidas:
        hasta = largo if c.hasta_mm is None else c.hasta_mm
        if not (-tol <= c.desde_mm < hasta <= largo + tol):
            raise ValueError(f"carga repartida fuera de la viga: [{c.desde_mm}, {hasta}] mm")


def _malla(largo: float, quiebres) -> list[float]:
    """Nodos: los quiebres (extremos, apoyos, cargas) + subdivisión uniforme ≤ L/_ELEMENTOS."""
    tol = _TOL_X * largo
    pts: list[float] = []
    for x in sorted(min(max(float(x), 0.0), largo) for x in quiebres):
        if not pts or x - pts[-1] > tol:
            pts.append(x)
    if largo - pts[-1] > tol:
        pts.append(largo)
    else:
        pts[-1] = largo
    h_max = largo / _ELEMENTOS
    nodos = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        n = max(1, math.ceil((b - a) / h_max - 1e-9))
        nodos += [a + (b - a) * k / n for k in range(1, n + 1)]
    return nodos


def _nodo(nodos: list[float], x: float, largo: float) -> int:
    i = min(range(len(nodos)), key=lambda k: abs(nodos[k] - x))
    assert abs(nodos[i] - x) <= _TOL_X * largo * 2, "punto fuera de la malla"
    return i


def _resolver_banda(a: list[list[float]], b: list[float], banda: int) -> list[float]:
    """Gauss sin pivoteo para una matriz simétrica definida positiva de semibanda `banda`."""
    n = len(b)
    escala = max((abs(a[i][i]) for i in range(n)), default=1.0) or 1.0
    for k in range(n):
        piv = a[k][k]
        if abs(piv) <= 1e-12 * escala:
            raise ValueError("viga inestable: es un mecanismo con esos apoyos")
        for i in range(k + 1, min(n, k + banda + 1)):
            f = a[i][k] / piv
            if f == 0.0:
                continue
            for j in range(k, min(n, k + banda + 1)):
                a[i][j] -= f * a[k][j]
            b[i] -= f * b[k]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = b[i] - sum(a[i][j] * x[j] for j in range(i + 1, min(n, i + banda + 1)))
        x[i] = s / a[i][i]
    return x


def viga_continua(largo_mm: float, ei_nmm2: float, apoyos, cargas) -> ResultadoViga:
    """Resuelve una viga recta de EI constante sobre `apoyos` (lista de `Apoyo`) con `cargas`
    (`CargaPuntual` / `CargaRepartida`). Lanza ValueError si los datos no forman una viga
    estable (apoyos fuera, duplicados, un solo apoyo articulado…). Con un memo de corrida
    abierto (`memo_corrida`: la puerta de publicación), una vez por entradas: es pura y el
    resultado es inmutable (dataclasses congeladas y tuplas)."""
    from .memo_corrida import por_clave

    return por_clave("viga_continua", _viga_continua, largo_mm, ei_nmm2, tuple(apoyos),
                     tuple(cargas))


def _viga_continua(largo_mm: float, ei_nmm2: float, apoyos, cargas) -> ResultadoViga:
    largo, ei = float(largo_mm), float(ei_nmm2)
    apoyos = list(apoyos)
    puntuales = [c for c in cargas if isinstance(c, CargaPuntual)]
    repartidas = [c for c in cargas if isinstance(c, CargaRepartida)]
    if len(puntuales) + len(repartidas) != len(cargas):
        raise ValueError("carga de tipo desconocido (usa CargaPuntual o CargaRepartida)")
    _validar(largo, ei, apoyos, puntuales, repartidas)

    def _hasta(c: CargaRepartida) -> float:
        return largo if c.hasta_mm is None else float(c.hasta_mm)

    quiebres = [0.0, largo, *(a.x_mm for a in apoyos), *(c.x_mm for c in puntuales)]
    quiebres += [x for c in repartidas for x in (c.desde_mm, _hasta(c))]
    nodos = _malla(largo, quiebres)
    n_dof = 2 * len(nodos)

    # q por elemento (las repartidas empiezan y terminan en nodos)
    q_el = []
    for x0, x1 in zip(nodos, nodos[1:]):
        xm = (x0 + x1) / 2.0
        q_el.append(sum(c.q_n_mm for c in repartidas if c.desde_mm <= xm <= _hasta(c)))

    k = [[0.0] * n_dof for _ in range(n_dof)]
    f = [0.0] * n_dof
    for e, (x0, x1) in enumerate(zip(nodos, nodos[1:])):
        h = x1 - x0
        c = ei / h**3
        ke = [[12 * c, 6 * h * c, -12 * c, 6 * h * c],
              [6 * h * c, 4 * h * h * c, -6 * h * c, 2 * h * h * c],
              [-12 * c, -6 * h * c, 12 * c, -6 * h * c],
              [6 * h * c, 2 * h * h * c, -6 * h * c, 4 * h * h * c]]
        q = q_el[e]
        fe = [q * h / 2, q * h * h / 12, q * h / 2, -q * h * h / 12]
        dofs = (2 * e, 2 * e + 1, 2 * e + 2, 2 * e + 3)
        for i in range(4):
            f[dofs[i]] += fe[i]
            for j in range(4):
                k[dofs[i]][dofs[j]] += ke[i][j]
    for c in puntuales:
        f[2 * _nodo(nodos, c.x_mm, largo)] += c.p_n

    fijos: dict[int, int] = {}  # dof → índice del apoyo que lo fija (para la reacción)
    for idx, a in enumerate(apoyos):
        n = _nodo(nodos, a.x_mm, largo)
        fijos[2 * n] = idx
        if a.tipo == EMPOTRAMIENTO:
            fijos[2 * n + 1] = idx
    libres = [i for i in range(n_dof) if i not in fijos]
    kr = [[k[i][j] for j in libres] for i in libres]
    sol = _resolver_banda(kr, [f[i] for i in libres], banda=3)
    d = [0.0] * n_dof
    for i, v in zip(libres, sol):
        d[i] = v

    reac = [0.0] * len(apoyos)
    for dof, idx in fijos.items():
        if dof % 2 == 0:  # sólo las fuerzas; el momento de empotramiento sale en `momento`
            r = sum(k[dof][j] * d[j] for j in range(max(0, dof - 3), min(n_dof, dof + 4))) - f[dof]
            reac[idx] = -r  # r empuja hacia abajo → la reacción hacia arriba es −r

    # Elástica y momento exactos dentro de cada elemento
    muestras: list[tuple[float, float, float]] = []  # (x, flecha, momento)
    for e, (x0, x1) in enumerate(zip(nodos, nodos[1:])):
        h, q = x1 - x0, q_el[e]
        v1, t1, v2, t2 = d[2 * e: 2 * e + 4]
        for s_i in range(_MUESTRAS + 1):
            t = s_i / _MUESTRAS
            s = t * h
            v = ((1 - 3 * t * t + 2 * t**3) * v1 + h * (t - 2 * t * t + t**3) * t1
                 + (3 * t * t - 2 * t**3) * v2 + h * (-t * t + t**3) * t2
                 + q * s * s * (h - s) ** 2 / (24 * ei))
            curv = ((-6 + 12 * t) / h**2 * v1 + (-4 + 6 * t) / h * t1
                    + (6 - 12 * t) / h**2 * v2 + (-2 + 6 * t) / h * t2
                    + q * (2 * h * h - 12 * h * s + 12 * s * s) / (24 * ei))
            muestras.append((x0 + s, v, -ei * curv))

    def _pico(lo: float, hi: float, col: int) -> tuple[float, float]:
        sel = [m for m in muestras if lo - _TOL_X * largo <= m[0] <= hi + _TOL_X * largo]
        m = max(sel, key=lambda r: abs(r[col]))
        return m[col], m[0]

    xs_apoyo = sorted(a.x_mm for a in apoyos)
    tramos: list[Tramo] = []
    if xs_apoyo[0] > _TOL_X * largo:
        tramos.append(Tramo(0.0, xs_apoyo[0], "voladizo", *_pico(0.0, xs_apoyo[0], 1)))
    for a, b in zip(xs_apoyo, xs_apoyo[1:]):
        tramos.append(Tramo(a, b, "vano", *_pico(a, b, 1)))
    if largo - xs_apoyo[-1] > _TOL_X * largo:
        tramos.append(Tramo(xs_apoyo[-1], largo, "voladizo", *_pico(xs_apoyo[-1], largo, 1)))

    flecha, x_flecha = _pico(0.0, largo, 1)
    momento, x_momento = _pico(0.0, largo, 2)
    return ResultadoViga(
        flecha_max_mm=flecha,
        flecha_x_mm=x_flecha,
        momento_max_nmm=momento,
        momento_x_mm=x_momento,
        momento_positivo_nmm=max(0.0, max(m[2] for m in muestras)),
        momento_negativo_nmm=min(0.0, min(m[2] for m in muestras)),
        reacciones_n=tuple(reac),
        tramos=tuple(tramos),
    )
