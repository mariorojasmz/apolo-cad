"""El fotograma binario y el `inicio` de la sesión viva como CONTRATO (plan pedidos-de-extensiones,
D2): una extensión (un SCADA, un tablero de mando) los lee sin pasar por la UI. Cambiar la
cabecera, el orden de los bloques o el tipo (float32 LE) sube `vivo_fotograma.FORMATO` y se
re-congela aquí A PROPÓSITO; el `inicio` conserva `version: 1` (agregar claves no la sube; quitar
o renombrar, sí). Sin MuJoCo: el fotograma es sintético, armado con `struct` y no con el
empacador, para que una regresión del empacador o del lector no se tape sola."""

from __future__ import annotations

import math
import struct
from types import SimpleNamespace

import numpy as np

from apolo.cosim import vivo_fotograma as V

#: la cabecera congelada: índice → qué es (docstring de `vivo_fotograma.py`)
CABECERA = ("formato", "t", "factor", "nc", "np", "nj", "nb", "ns")
NAN = float("nan")


def _fotograma() -> tuple[list[float], bytes]:
    """1 cuerpo, 2 productos (uno sin nacer), 2 juntas, 1 banda y 3 señales (una sin valor)."""
    cab = [1.0, 2.5, 0.98, 1, 2, 2, 1, 3]
    cuerpos = [10.0, -20.0, 30.0, 0.0, 0.0, 0.7071067, 0.7071068]
    productos = [100.0, 200.0, 300.0, 0.0, 0.0, 0.0, 1.0] + [NAN] * 7
    juntas = [45.0, 12.5]
    bandas = [0.3]
    senales = [1.0, NAN, 220.0]
    plano = cab + cuerpos + productos + juntas + bandas + senales
    return plano, struct.pack(f"<{len(plano)}f", *plano)


def test_la_cabecera_y_el_formato_estan_congelados():
    assert V.FORMATO == 1
    assert V.CABECERA == len(CABECERA) == 8
    doc = V.__doc__
    assert "float32 little-endian; `FORMATO` = 1" in doc
    assert "[0] formato · [1] t (s virtuales) · [2] factor de tiempo real medido · [3] nc · [4] np · [5] nj" in doc
    assert "· [6] nb · [7] ns" in doc


def test_un_fotograma_sintetico_se_lee_bloque_por_bloque():
    plano, datos = _fotograma()
    assert len(datos) == 4 * len(plano)  # float32: 4 bytes por valor, sin relleno
    f = V.leer_fotograma(datos)
    assert set(f) == {"formato", "t", "factor", "cuerpos", "productos", "juntas", "bandas", "senales"}
    assert f["formato"] == V.FORMATO and f["t"] == 2.5
    assert math.isclose(f["factor"], 0.98, rel_tol=1e-6)
    assert f["cuerpos"].shape == (1, 7) and f["productos"].shape == (2, 7)
    np.testing.assert_allclose(f["cuerpos"][0], plano[8:15], rtol=1e-6)
    np.testing.assert_allclose(f["productos"][0], [100, 200, 300, 0, 0, 0, 1])
    assert np.isnan(f["productos"][1]).all()  # el que no nació viaja NaN
    np.testing.assert_allclose(f["juntas"], [45.0, 12.5])
    np.testing.assert_allclose(f["bandas"], [0.3], rtol=1e-6)
    assert f["senales"][0] == 1.0 and np.isnan(f["senales"][1]) and f["senales"][2] == 220.0
    assert f["senales"].dtype == np.dtype("<f4")


def test_el_lector_es_little_endian():
    """El mismo fotograma en big-endian NO se lee igual: el tipo es parte del contrato."""
    plano, datos = _fotograma()
    otro = struct.pack(f">{len(plano)}f", *plano)
    assert otro != datos
    assert np.frombuffer(datos, "<f4")[1] == 2.5


def test_el_inicio_conserva_su_version_y_sus_claves():
    from apolo.api.routers.cosim_vivo import _inicio

    snap = SimpleNamespace(avisos=["un aviso"], hipotesis=["una hipótesis"],
                           dinamica=SimpleNamespace(cuerpos=[]))
    prep = {"snap": snap, "vis": None, "proyecto": 7, "nombre": "marcha", "firma": "2:abc"}
    tabla = {"formato": V.FORMATO, "dt_s": 0.002, "cuerpos": [], "senales": ["-M1.rpm"]}
    ini = _inicio(prep, tabla, {"max_s": 600, "ritmo": 1.0}, 1234)
    assert ini["tipo"] == "inicio" and ini["version"] == 1
    assert {"proyecto", "escenario", "firma", "ventana_s", "max_s", "ritmo", "pid", "formato",
            "dt_s", "cuerpos", "senales", "fajas", "cadenas", "avisos", "hipotesis"} <= set(ini)
    assert ini["senales"] == ["-M1.rpm"] and ini["avisos"] == ["un aviso"]
