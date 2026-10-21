"""Medición de la red de mando de ~60 nodos (plan V8.3 F3): µs por paso con la LU en caché y µs al
refactorizar. Lo corre `test_cosim_red_rendimiento.py` en un SUBPROCESO con BLAS de un hilo (el
worker de F4 lo arranca así: en una matriz de 62 × 62 los hilos de OpenBLAS sólo agregan
sincronización), y también se puede correr suelto: `python -B tests/cosim_red_medir.py`.

Imprime un JSON {"nodos", "incognitas", "paso_us", "refactorizar_us"}: el MEJOR de varios lotes
(la laptop varía ±30 % por turbo y térmica, F0).
"""

from __future__ import annotations

import json
import time

CIRCUITOS = 20


def entrada_60_nodos() -> dict:
    """20 circuitos de bobina: +24 → marcha (NA) ∥ retención (NA) → bobina → 0 V, cada uno con su
    conductor de ida y su entrada de PLC: 3 nodos por circuito + el «+» = 61 nodos, 40 contactos."""
    ramas, cargas = [], []
    for k in range(CIRCUITOS):
        s, km = f"-S{k}", f"-K{k}"
        ramas += [
            {"id": f"w{k}a", "tipo": "conductor", "de": "-T1:L+", "a": f"{s}:13", "seccion_mm2": 0.75, "largo_m": 2.0},
            {"id": f"{s}:13-14", "tipo": "contacto", "de": f"{s}:13", "a": f"{s}:14", "contacto": "NA",
             "actuador": f"{s}.mano"},
            {"id": f"{km}:13-14", "tipo": "contacto", "de": f"{s}:13", "a": f"{s}:14", "contacto": "NA",
             "actuador": f"{km}.bobina"},
            {"id": f"w{k}b", "tipo": "conductor", "de": f"{s}:14", "a": f"{km}:A1", "seccion_mm2": 0.75, "largo_m": 2.0},
            {"id": f"w{k}c", "tipo": "union", "de": f"{km}:A2", "a": "-T1:M"},
            {"id": f"w{k}d", "tipo": "union", "de": f"{km}:A1", "a": f"-A1:I{k}"},
        ]
        cargas += [
            {"id": f"{km}:A1-A2", "tipo": "bobina", "bornes": [f"{km}:A1", f"{km}:A2"], "modo": "impedancia",
             "S_VA": 2.4, "Un_V": 24},
            {"id": f"-A1:I{k}-1M", "tipo": "entrada", "bornes": [f"-A1:I{k}", "-T1:M"], "modo": "impedancia",
             "R_ohm": 7500},
        ]
    return {"ramas": ramas, "cargas": cargas,
            "fuentes": [{"id": "-T1", "tipo": "DC", "U_V": 24, "polos": {"-T1:L+": "+", "-T1:M": "-"}}]}


def _mejor(f, n: int, lotes: int) -> float:
    mejor = float("inf")
    for _ in range(lotes):
        t = time.perf_counter()
        for i in range(n):
            f(i)
        mejor = min(mejor, (time.perf_counter() - t) / n)
    return mejor * 1e6


def medir(n: int = 400, lotes: int = 15) -> dict:
    from apolo.cosim.red import armar

    red = armar(entrada_60_nodos()).mando
    estados = {f"-S{k}.mano": k % 3 == 0 for k in range(CIRCUITOS)}
    red.paso(estados)
    tensiones = (24.0, 23.5)

    def paso(i):
        red.paso(estados, {"-T1": tensiones[i & 1]})

    alterna = [dict(estados), {**estados, "-S1.mano": not estados["-S1.mano"]}]

    def refactorizar(i):
        red.paso(alterna[i & 1])

    antes = red.factorizaciones
    paso_us = _mejor(paso, n, lotes)
    assert red.factorizaciones == antes, "un paso sin conmutar refactorizó"
    ref_us = _mejor(refactorizar, max(50, n // 4), lotes)
    assert red.factorizaciones > antes
    return {"nodos": red.sis.n, "incognitas": red.sis.N, "paso_us": paso_us, "refactorizar_us": ref_us}


if __name__ == "__main__":
    print(json.dumps(medir()))
