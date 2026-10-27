"""Matemática PURA de la cadena de IZAJE: una cadena de rodillos ABIERTA cuyos dos extremos se
amarran a una pieza (la plataforma) y que pasa por uno o más piñones (plan
`docs/plans/cadena-de-izaje.md`). Sin OCCT ni `Document`: la usan el comando
(`commands/exec_izaje.py`) y la cinemática (`robotics/pose_izaje.py`), que así rehacen la MISMA
cadena en el diseño y en cada pose.

MARCO (2D, el plano de las hileras): los piñones son círculos de paso (centro, radio d0/2,
dientes) y los extremos A y B son los centros de los pasadores de amarre. La cadena va de A a B
pasando por los piñones EN ORDEN y gira alrededor de todos en el MISMO sentido `sigma` (+1 =
antihorario, −1 = horario, alrededor de +Z del marco): es un lazo abierto por la pieza, como el
de un elevador (A → motriz arriba → ramal de retorno → loco abajo → B). Ángulos en radianes.

Rodillos: el primero en A y los demás a exactamente un paso del anterior. En un tramo recto van
en línea; al llegar a un piñón, el siguiente es el punto de su círculo de paso a un paso del
último (corta el círculo hacia adelante) y desde ahí siguen girando de a un diente (cuerda = p
exacta: d0 = p/sin(180°/z)). Se sale del piñón por el último asiento antes del punto de salida de
la tangente, como una cadena tensa real (el efecto poligonal queda en el tramo). Una cadena con
N pasos tiene N + 1 rodillos; N es IMPAR: las dos puntas son eslabones INTERIORES, que es por donde
entra el pasador del amarre (el eslabón exterior de la punta lo pone la horquilla).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Tolerancia numérica (mm) de las comparaciones de largo.
EPS_MM = 1e-6


@dataclass(frozen=True)
class Pinon:
    """Un piñón en el marco del plano: centro, radio de paso y dientes."""

    cx: float
    cy: float
    radio: float
    z: int


@dataclass(frozen=True)
class CadenaAbierta:
    """Los rodillos de una cadena abierta de A hacia B (marco del plano)."""

    puntos: tuple            # ((x, y), …), N + 1 rodillos; puntos[0] = A
    pasos: int               # N (impar)
    asentados: tuple         # por piñón, los índices de `puntos` sentados en él
    falta_mm: float          # lo que el último rodillo queda ANTES de B por el último tramo (< 0: lo pasa)
    largo_camino_mm: float   # el camino de paso de A a B (tangentes + arcos)

    @property
    def fin(self) -> tuple:
        return self.puntos[-1]


def _ang(v) -> float:
    return math.atan2(v[1], v[0])


def _rel(theta: float, theta0: float, sigma: int) -> float:
    """Ángulo recorrido de θ0 a θ en el sentido `sigma`, en [0, 2π)."""
    return (sigma * (theta - theta0)) % (2.0 * math.pi)


def _punto(p: Pinon, theta: float) -> tuple:
    return (p.cx + p.radio * math.cos(theta), p.cy + p.radio * math.sin(theta))


def entrada_desde(q, p: Pinon, sigma: int) -> float:
    """Ángulo del punto donde la recta que viene de `q` toca el círculo de `p` y sigue girando
    en el sentido `sigma`. ValueError si `q` está dentro del círculo."""
    d = math.dist(q, (p.cx, p.cy))
    if d <= p.radio + EPS_MM:
        raise ValueError(f"el punto ({q[0]:.1f}, {q[1]:.1f}) cae dentro del círculo de paso del piñón")
    alfa = _ang((q[0] - p.cx, q[1] - p.cy))
    return alfa + sigma * math.acos(p.radio / d)


def salida_hacia(p: Pinon, q, sigma: int) -> float:
    """Ángulo del punto donde la cadena deja el círculo de `p` girando en `sigma` hacia `q`."""
    d = math.dist(q, (p.cx, p.cy))
    if d <= p.radio + EPS_MM:
        raise ValueError(f"el punto ({q[0]:.1f}, {q[1]:.1f}) cae dentro del círculo de paso del piñón")
    beta = _ang((q[0] - p.cx, q[1] - p.cy))
    return beta - sigma * math.acos(p.radio / d)


def tangente_comun(pi: Pinon, pj: Pinon, sigma: int) -> float:
    """Ángulo (el mismo en los dos círculos) de la tangente EXTERIOR de `pi` a `pj` para una
    cadena que gira alrededor de los dos en el sentido `sigma`."""
    c = math.dist((pi.cx, pi.cy), (pj.cx, pj.cy))
    if c <= abs(pi.radio - pj.radio) + EPS_MM:
        raise ValueError("un piñón queda dentro del otro: sepáralos")
    gamma = _ang((pj.cx - pi.cx, pj.cy - pi.cy))
    return gamma - sigma * math.acos((pi.radio - pj.radio) / c)


def camino(a, pinones: list[Pinon], b, sigma: int) -> tuple[float, list[tuple[float, float]]]:
    """(largo del camino de paso de A a B, [(θ entrada, θ salida)] por piñón)."""
    angulos = []
    for i, p in enumerate(pinones):
        th_in = (entrada_desde(a, p, sigma) if i == 0
                 else tangente_comun(pinones[i - 1], p, sigma))
        th_out = (salida_hacia(p, b, sigma) if i == len(pinones) - 1
                  else tangente_comun(p, pinones[i + 1], sigma))
        angulos.append((th_in, th_out))
    largo, previo = 0.0, a
    for p, (th_in, th_out) in zip(pinones, angulos):
        largo += math.dist(previo, _punto(p, th_in)) + p.radio * _rel(th_out, th_in, sigma)
        previo = _punto(p, th_out)
    return largo + math.dist(previo, b), angulos


def sentido_mas_corto(a, pinones: list[Pinon], b) -> int:
    """El sentido de giro cuyo camino es el más corto (el lazo abierto sin cruces)."""
    largos = {}
    for s in (1, -1):
        try:
            largos[s] = camino(a, pinones, b, s)[0]
        except ValueError:
            continue
    if not largos:
        raise ValueError("ningún sentido de giro arma el camino: revisa los extremos y los piñones")
    return min(largos, key=lambda s: (round(largos[s], 6), -s))


def _corte_adelante(q, p: Pinon, paso: float, theta0: float, sigma: int) -> float:
    """Ángulo del punto del círculo de `p` a un paso de `q`, el que queda más adelante (en
    `sigma`) desde θ0. ValueError si el círculo de radio `paso` alrededor de `q` no lo corta."""
    dx, dy = q[0] - p.cx, q[1] - p.cy
    d = math.hypot(dx, dy)
    # ley del coseno: |q − c|² + R² − 2·|q − c|·R·cos φ = paso²
    if d < EPS_MM:
        raise ValueError("un rodillo cayó en el centro de un piñón")
    cosphi = (d * d + p.radio * p.radio - paso * paso) / (2.0 * d * p.radio)
    if cosphi > 1.0 + 1e-9 or cosphi < -1.0 - 1e-9:
        raise ValueError("la cadena no llega a asentar en el piñón (un paso no lo alcanza)")
    phi = math.acos(max(-1.0, min(1.0, cosphi)))
    base = _ang((dx, dy))
    candidatos = [base + phi, base - phi]
    return max(candidatos, key=lambda t: ((_rel(t, theta0, sigma) + math.pi) % (2.0 * math.pi)))


def _cruz(o, a, b) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _tapa(q, objetivo, asiento, sigma: int) -> bool:
    """¿El asiento siguiente queda AFUERA de la recta q → objetivo (a la derecha si la cadena
    gira antihorario, a la izquierda si horario)? Entonces la cadena tensa pasa por él: es un
    vértice del casco convexo de los asientos y el objetivo, como en el lazo cerrado
    (`transmision.rodillos_del_lazo`)."""
    return sigma * _cruz(q, objetivo, asiento) < -1e-9


def rodillos(a, pinones: list[Pinon], b, sigma: int, paso: float,
             pasos: int | None = None, sobra_mm: float = 1e-6) -> CadenaAbierta:
    """Los rodillos de la cadena de A hacia B. `pasos` = N fijo (impar) o None = el mayor impar
    con el que el último rodillo no pasa de B. ValueError si N no alcanza el último tramo o si
    lo pasa (la cadena sobra: quedaría floja)."""
    if not pinones:
        raise ValueError("la cadena de izaje pasa por al menos un piñón")
    if pasos is not None and (int(pasos) != pasos or pasos < 3 or pasos % 2 == 0):
        raise ValueError(f"eslabones = {pasos}: tiene que ser IMPAR y ≥ 3 (las dos puntas son "
                         "eslabones interiores, por donde entra el pasador del amarre)")
    largo, _angulos = camino(a, pinones, b, sigma)
    tope = pasos if pasos is not None else 10 ** 6
    puntos = [tuple(a)]
    asentados: list[tuple] = []
    q = tuple(a)

    def recta(desde, hacia, limite_mm: float) -> tuple:
        """Rodillos a paso exacto de `desde` hacia `hacia` mientras no pasen de `limite_mm`."""
        nonlocal q
        dx, dy = hacia[0] - desde[0], hacia[1] - desde[1]
        d = math.hypot(dx, dy)
        k = 1
        while len(puntos) - 1 < tope and k * paso <= limite_mm + EPS_MM:
            q = (desde[0] + dx * k * paso / d, desde[1] + dy * k * paso / d)
            puntos.append(q)
            k += 1
        return dx / d, dy / d

    for i, p in enumerate(pinones):
        th_in = entrada_desde(q, p, sigma)
        t_in = _punto(p, th_in)
        recta(q, t_in, math.dist(q, t_in))
        if len(puntos) - 1 >= tope:
            raise ValueError(f"{pasos} eslabones no alcanzan el piñón {i + 1}")
        if math.dist(q, t_in) < 1e-6:
            theta = th_in
            idx = [len(puntos) - 1]
        else:
            theta = _corte_adelante(q, p, paso, th_in, sigma)
            q = _punto(p, theta)
            puntos.append(q)
            idx = [len(puntos) - 1]
        diente = 2.0 * math.pi / p.z
        ultimo = i == len(pinones) - 1
        for _ in range(p.z):  # como mucho una vuelta
            if len(puntos) - 1 >= tope:
                break
            siguiente = _punto(p, theta + sigma * diente)
            objetivo = b if ultimo else _punto(pinones[i + 1], entrada_desde(q, pinones[i + 1], sigma))
            if not _tapa(q, objetivo, siguiente, sigma):
                break
            theta += sigma * diente
            q = siguiente
            puntos.append(q)
            idx.append(len(puntos) - 1)
        asentados.append(tuple(idx))
        if len(puntos) - 1 >= tope and i < len(pinones) - 1:
            raise ValueError(f"{pasos} eslabones no alcanzan el piñón {i + 2}")
    # último tramo, del último asiento hacia B
    desde = q
    d_b = math.dist(desde, b)
    if pasos is None:
        recta(desde, b, d_b)
        if (len(puntos) - 1) % 2 == 0:
            puntos.pop()
    else:
        recta(desde, b, d_b + 10.0 ** 9)
        if len(puntos) - 1 < pasos:
            raise ValueError(f"{pasos} eslabones no alcanzan el último tramo")
    fin = puntos[-1]
    adelante = (fin[0] - desde[0]) * (b[0] - desde[0]) + (fin[1] - desde[1]) * (b[1] - desde[1])
    falta = d_b - (adelante / d_b if d_b > 0 else 0.0)
    if falta < -sobra_mm:
        raise ValueError(
            f"con {pasos} eslabones la cadena pasa {-falta:.1f} mm de B (sobra cadena: quedaría "
            f"floja): usa eslabones = {pasos - 2 * math.ceil(-falta / (2 * paso))} o aleja B"
        )
    return CadenaAbierta(
        puntos=tuple(puntos), pasos=len(puntos) - 1, asentados=tuple(asentados),
        falta_mm=falta, largo_camino_mm=largo,
    )


def cerrar_en(c: CadenaAbierta, b) -> CadenaAbierta:
    """La misma cadena con el último rodillo EN `b` (el pasador del ancla B posada): los rodillos
    del último tramo recto se reparten por igual del último asiento a `b`. En una pose el efecto
    poligonal cambia unas centésimas el largo que se lleva cada piñón; en la máquina lo toma el
    giro del piñón, aquí ese tramo (`falta_mm` conserva lo que faltaba, para el aviso)."""
    j0 = c.asentados[-1][-1] if c.asentados and c.asentados[-1] else 0
    n = c.pasos - j0
    if n <= 0:
        return c
    q = c.puntos[j0]
    nuevos = [(q[0] + (b[0] - q[0]) * k / n, q[1] + (b[1] - q[1]) * k / n) for k in range(1, n + 1)]
    return CadenaAbierta(puntos=c.puntos[:j0 + 1] + tuple(nuevos), pasos=c.pasos, asentados=c.asentados,
                         falta_mm=c.falta_mm, largo_camino_mm=c.largo_camino_mm)
