"""Puerta de publicación F6 — sondas con el brazo DOBLADO (ISO 13857 tablas 4 y 6; plan
puerta-de-publicacion, Bitácora F6): el campo puro del brazo (`library/seguridad/alcance.py`) y la
mano que sale de él (`services/calidad_codo.py`), sobre geometría sintética.

La escena «caja con un muro»: una caja de 400 mm abierta por +X, con techo; adentro, un muro a
x = 200 que llega hasta z = 300 (100 mm bajo el techo). El peligro está DETRÁS del muro, abajo:
ninguna recta desde fuera llega (el techo tapa lo que pasa por encima del muro), pero un brazo
que entra por +X, pasa la mano por encima del muro y la baja, sí (el hueco de la F6).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from apolo.library.seguridad.alcance import CampoAlcance, muestrear_triangulos

PELIGRO = (150.0, 200.0, 60.0)


def _cara(lo, hi):
    """Triángulos (xyz, tri) de las 6 caras de la caja [lo, hi]."""
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    v = np.array([(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], float)
    q = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    tri = [t for a, b, c, d in q for t in ((a, b, c), (a, c, d))]
    return v, np.array(tri)


def _placas(hueco_mm: float = 100.0, cerrada: bool = False):
    """Las placas de la caja con el muro: [(lo, hi)]. `hueco_mm`: del tope del muro al techo;
    `cerrada`: también la cara +X."""
    t = 3.0
    placas = [((0, 0, -t), (400, 400, 0)),            # piso de la máquina
              ((0, 0, 400), (400, 400, 400 + t)),      # techo
              ((-t, 0, 0), (0, 400, 400)),             # cara −X
              ((0, -t, 0), (400, 0, 400)),             # cara −Y
              ((0, 400, 0), (400, 400 + t, 400)),      # cara +Y
              ((200, 0, 0), (200 + t, 400, 400 - hueco_mm))]  # el muro
    if cerrada:
        placas.append(((400, 0, 0), (400 + t, 400, 400)))
    return placas


def _campo(placas) -> CampoAlcance:
    pts = np.concatenate([muestrear_triangulos(*_cara(lo, hi)) for lo, hi in placas])
    lo = np.min([p[0] for p in placas], axis=0)
    hi = np.max([p[1] for p in placas], axis=0)
    return CampoAlcance(pts, (tuple(lo), tuple(hi)), z_piso=-200.0)


# ------------------------------------------------------------------ muestreo de superficies
def test_muestreo_cubre_el_triangulo_y_no_explota_en_los_finos():
    xyz = np.array([[0, 0, 0], [300, 0, 0], [40, 120, 0],          # uno normal
                    [0, 0, 50], [4000, 0, 50], [1000, 3, 50]], float)  # uno largo y fino
    tri = np.array([[0, 1, 2], [3, 4, 5]])
    pts = muestrear_triangulos(xyz, tri, paso=5.0)
    rng = np.random.default_rng(0)
    for a, b, c in xyz[tri]:
        u = rng.random((4000, 2))
        u[u.sum(1) > 1] = 1 - u[u.sum(1) > 1]
        q = a + (b - a) * u[:, :1] + (c - a) * u[:, 1:]
        d = np.min(np.linalg.norm(q[:, None, :] - pts[None, :, :], axis=2), axis=1)
        assert d.max() <= 5.0 * 0.75  # ninguna zona sin muestra a más de 3/4 del paso
    assert len(pts) < 4000  # el fino da ~perímetro/paso, no (largo/paso)²


# ------------------------------------------------------------------ el campo del brazo
def test_caja_cerrada_no_se_alcanza_por_dentro():
    c = _campo(_placas(cerrada=True))
    assert c.profundidad((300, 200, 200)) is None
    assert c.profundidad((100, 200, 100)) is None
    assert c.profundidad((600, 200, 200)) == 0.0  # fuera de la grilla = fuera de la máquina


def test_detras_del_muro_se_llega_doblando_el_brazo():
    c = _campo(_placas())
    # delante del muro, en línea recta desde +X
    assert c.profundidad((300, 200, 200)) == pytest.approx(100, abs=10)  # desde x = 400
    # detrás del muro, abajo: el brazo entra por +X, el antebrazo baja por encima del muro
    p = c.profundidad((150, 200, 200))
    assert p is not None and 250 < p < 850


def test_un_hueco_de_dedo_no_deja_pasar_el_brazo():
    c = _campo(_placas(hueco_mm=15.0))  # 15 mm entre el muro y el techo: tabla 4, < 20
    assert c.profundidad((150, 200, 200)) is None
    assert c.profundidad((300, 200, 200)) is not None


# ------------------------------------------------------------------ la mano (OCCT)
def _escena(hueco_mm: float):
    from build123d import Box, Pos

    from apolo.services.calidad_sondas import Trazador

    def caja(lo, hi):
        return Pos(*[(lo[k] + hi[k]) / 2 for k in range(3)]) * Box(
            *[hi[k] - lo[k] for k in range(3)])

    solidos = {f"placa{k}": [caja(lo, hi)] for k, (lo, hi) in enumerate(_placas(hueco_mm))}
    solidos["rodillo"] = [Pos(*PELIGRO) * Box(40, 40, 40)]
    lo = (-3.0, -3.0, -3.0)
    hi = (403.0, 403.0, 403.0)
    return solidos, Trazador(solidos), (lo, hi)


@pytest.mark.parametrize("hueco,alcanza", [(100.0, True), (15.0, False)])
def test_la_mano_llega_detras_del_muro_solo_con_el_brazo_doblado(hueco, alcanza):
    from apolo.services.calidad_codo import campo_alcance, sondas_con_codo
    from apolo.services.calidad_sondas import evaluar_peligro

    solidos, tr, caja = _escena(hueco)
    peligro = {"id": "giro:rodillo", "piezas": ["rodillo"],
               "objetivos": [(PELIGRO[0], PELIGRO[1], PELIGRO[2] + 21.0)]}
    rectas, _ = evaluar_peligro(tr, peligro, caja, -3.0, 64)
    assert not any(s["alcanza"] for s in rectas)  # el hueco de las rectas
    campo = campo_alcance(solidos, caja, -3.0)
    sondas, _ = sondas_con_codo(tr, campo, peligro, 64)
    llegan = [s for s in sondas if s["alcanza"]]
    assert bool(llegan) is alcanza
    if alcanza:
        s = llegan[0]
        assert s["via"] == "brazo doblado" and s["distancia_mm"] <= 850
        assert s["codo"][0] < 200  # la muñeca ya pasó el muro
        assert math.dist(s["codo"], peligro["objetivos"][0]) <= 230
