"""La cuña de ENTRADA de cada tambor que la banda abraza (plan puerta-sin-sobrediseno, D3–D4):
matemática PURA sobre la línea media del lazo (`library/ruta_faja_modelo.py`).

El arrastre (ISO 12100, anexo B: atrapamiento) está donde la banda LLEGA al tambor y convergen;
en la cuña de salida se separan. Con el sentido de transporte conocido:

1. **El lazo en el sentido de marcha** (`lazo_en_marcha`): el ramal SUPERIOR es el tramo recto
   más largo de la línea media cuya normal hacia afuera mira arriba (ángulo < 60° con la
   vertical); avanza en el sentido de transporte, así que el lazo se recorre con esa orientación
   (la línea media sale antihoraria: se invierte si el ramal superior va al revés).
2. **La llegada a cada tambor** (`llegada`): recorriendo el lazo en marcha, el primer punto del
   tramo en contacto con el tambor (centro a ≤ r + t/2 + `TOL_CONTACTO_MM` de la línea media).
   Vale igual para un tambor que el lazo envuelve (cabeza, cola, motriz) y para un desvío por
   fuera: manda la banda, nunca el giro de la junta (un desvío gira al revés que el motriz).
3. **El borde del arco** (`borde_de_entrada`): de los bordes del arco de contacto que mide
   `services/calidad_sondas.cunas`, el más cercano en ángulo a la llegada.

Lo que no se puede decidir (sin ramal superior, eje de tambores vertical, sentido que no sigue el
ramal superior, tambor sin tramo de contacto) devuelve None con el motivo: el llamador toma las
dos cuñas, como sin sentido.
"""

from __future__ import annotations

import math

import numpy as np

from ..ruta_faja_modelo import TOL_CONTACTO_MM, rectos

#: Coseno mínimo entre la normal del ramal superior y la vertical (60°).
COS_ARRIBA = 0.5
#: Coseno mínimo entre el sentido declarado y el ramal superior (60°).
COS_SENTIDO = 0.5
#: Dos bordes a menos de esto (grados) de diferencia con la llegada: no se elige.
AMBIGUO_DEG = 2.0


def _unit(v) -> np.ndarray | None:
    a = np.asarray(v, float)
    n = float(np.hypot(*a)) if a.shape == (2,) else float(np.linalg.norm(a))
    return a / n if n > 1e-9 else None


def lazo_en_marcha(media, sentido_uw, arriba_uw) -> tuple[np.ndarray | None, str]:
    """(lazo de la línea media en el sentido de marcha, "") o (None, motivo). `media`: la línea
    media ANTIHORARIA (N, 2); `sentido_uw` y `arriba_uw`: el sentido de transporte y la vertical
    del mundo proyectados en el plano (u, w) de la sección (sin normalizar: su largo dice cuánto
    del vector cae en el plano)."""
    media = np.asarray(media, float)
    if len(media) < 3:
        return None, "sin línea media del lazo"
    arriba = np.asarray(arriba_uw, float)
    if float(np.hypot(*arriba)) < COS_ARRIBA:
        return None, "el eje de los tambores es casi vertical: no hay ramal superior"
    sentido = np.asarray(sentido_uw, float)
    if float(np.hypot(*sentido)) < COS_SENTIDO:
        return None, "el sentido declarado es casi paralelo al eje de los tambores"
    arriba, sentido = _unit(arriba), _unit(sentido)
    q, tramos = rectos(media)
    mejor = None
    for i, j in tramos:
        t = _unit(q[j] - q[i])
        if t is None:
            continue
        normal = np.array([t[1], -t[0]])  # hacia afuera de un lazo antihorario
        largo = math.dist(q[i], q[j])
        if float(normal @ arriba) >= COS_ARRIBA and (mejor is None or largo > mejor[0]):
            mejor = (largo, t)
    if mejor is None:
        return None, "la sección de la banda no tiene un ramal superior recto"
    avance = float(mejor[1] @ sentido)
    if abs(avance) < COS_SENTIDO:
        return None, "el sentido declarado no sigue el ramal superior (más de 60° entre ellos)"
    return (media.copy() if avance > 0 else media[::-1].copy()), ""


def _densa(lazo: np.ndarray, paso: float) -> np.ndarray:
    """El lazo cerrado con ningún tramo más largo que `paso` (mismos vértices, en orden)."""
    sig = np.roll(lazo, -1, axis=0)
    partes = np.maximum(1, np.ceil(np.hypot(*(sig - lazo).T) / paso).astype(int))
    out = [lazo[k] + (sig[k] - lazo[k]) * (s / m)
           for k, m in enumerate(partes) for s in range(m)]
    return np.array(out)


def llegada(lazo, centro, radio: float, espesor: float,
            tol: float = TOL_CONTACTO_MM) -> np.ndarray | None:
    """El punto (u, w) donde el lazo (en marcha) LLEGA al tambor de `centro` y `radio`: el primero
    del tramo en contacto más largo. None si no lo toca o lo toca entero. Los tramos rectos
    llegan con sus dos extremos solos: se densifican a ≤ r/10 para que un tambor que la banda
    apenas abraza (un desvío) también tenga vértices en contacto."""
    lazo = _densa(np.asarray(lazo, float), max(1.0, radio / 10.0))
    toca = np.hypot(*(lazo - np.asarray(centro, float)).T) <= radio + espesor / 2.0 + tol
    if not np.any(toca) or np.all(toca):
        return None
    n = len(lazo)
    mejor = None
    for k in range(n):
        if not toca[k] or toca[k - 1]:
            continue
        largo = 0
        while largo < n and toca[(k + largo) % n]:
            largo += 1
        if mejor is None or largo > mejor[1]:
            mejor = (k, largo)
    return lazo[mejor[0]].copy() if mejor is not None else None


def _dif(a: float, b: float) -> float:
    return abs((a - b + math.pi) % (2.0 * math.pi) - math.pi)


def borde_de_entrada(bordes: list[float], theta_llegada: float) -> int | None:
    """El índice del borde del arco (ángulos en rad) más cercano a la llegada, o None si no hay
    bordes o los dos más cercanos quedan a menos de `AMBIGUO_DEG` uno del otro."""
    if not bordes:
        return None
    d = sorted((_dif(b, theta_llegada), k) for k, b in enumerate(bordes))
    if len(d) > 1 and d[1][0] - d[0][0] < math.radians(AMBIGUO_DEG):
        return None
    return d[0][1]
