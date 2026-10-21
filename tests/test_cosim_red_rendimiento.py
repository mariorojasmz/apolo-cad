"""Rendimiento de la red de mando (plan V8.3 F3; marco V8 D3 y la medición de F0): con ~60 nodos,
≤ 50 µs por paso con la LU en caché y ≤ 150 µs al refactorizar por la conmutación de un contacto.

La medición (`cosim_red_medir.py`) corre en un SUBPROCESO con BLAS de un hilo, como el worker de
F4: en una matriz de 62 × 62 los hilos de OpenBLAS sólo agregan sincronización (medido: getrs con
dos lados derechos, 18 µs con un hilo y 130 µs con los de fábrica). La cota estricta va en
`-m torture` (la laptop varía ±30 %, F0); la suite normal exige 10 veces menos, para cazar una
regresión de orden (refactorizar en cada paso, resolver con `np.linalg.solve`) sin falsos rojos.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

MEDIR = Path(__file__).with_name("cosim_red_medir.py")


def medir() -> dict:
    env = {**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
    res = subprocess.run([sys.executable, "-B", str(MEDIR)], capture_output=True, text=True, env=env,
                         timeout=300)
    assert res.returncode == 0, res.stderr[-2000:]
    return json.loads(res.stdout.strip().splitlines()[-1])


def test_red_de_60_nodos_cabe_en_el_intercambio():
    m = medir()
    assert 55 <= m["nodos"] <= 65
    assert m["paso_us"] <= 500.0, m
    assert m["refactorizar_us"] <= 1500.0, m


@pytest.mark.torture
def test_red_de_60_nodos_cota_estricta():
    m = medir()
    assert m["paso_us"] <= 50.0, m
    assert m["refactorizar_us"] <= 150.0, m
