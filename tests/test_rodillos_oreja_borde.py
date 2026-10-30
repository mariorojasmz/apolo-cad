"""Oreja del portamotor de `create_roller_conveyor` (v6): sus agujeros de perno a e ≥ 1,5·d0 del
canto (ranura, EN 1993-1-8 tabla 3.3), la medida de la puerta (`union.distancia_al_borde`).

Hasta la v5 las ranuras ABRÍAN al canto y la puerta medía e = 16,02 < 16,5 mm en dos máquinas
(un rodillos-cadena empernado y uno soldado de L2000 W400 H500): el ligamento entre la pared de
la ranura y el canto, junto a la boca, tiende a cero (el rayo de 70° lo vio). Ahora las ranuras
son cerradas y la oreja se dimensiona con el recorrido de tensado."""

from __future__ import annotations

import itertools
import math

import pytest

from apolo.commands.exec_rodillos_cadena import disposicion_de
from apolo.commands.models_rodillos_cadena import CreateRollerConveyorParams
from apolo.doc import Document
from apolo.library import rodillos_cadena as rc
from apolo.library.borde_agujero import E_RANURA
from apolo.library.rodillos_cadena_motriz import MONTAJE_MM, RANURA_OREJA, W_PERNO
from apolo.services.calidad_bordes import insumos_bordes
from apolo.services.calidad_pernos import _Escena, insumos_pernos

E_MIN = E_RANURA * RANURA_OREJA  # 16,5 mm


def _uw(p, a):
    """XZ (relativo al centro del tubo) → (û, ŵ)."""
    x, z = p
    return x * math.cos(a) - z * math.sin(a), x * math.sin(a) + z * math.cos(a)


def _disposiciones():
    for motor, v, rod, alt in itertools.product(
            ["MOTOR-037", "MOTOR-075", "MOTOR-150", "auto"], [None, 0.15, 0.25, 0.35],
            ["TUBOR-1.5", "TUBOR-2", "TUBOR-3"], [500, 750, 1000]):
        try:
            yield rc.disposicion(largo=2000, ancho_util=600, paso=120.65, rodillo=rod,
                                 altura=alt, carga_kg=200, motriz=True, motor=motor,
                                 velocidad_m_s=v, taller=True, mantenimiento=True)
        except ValueError:
            continue


def test_la_oreja_deja_e_minimo_en_todo_el_rango():
    """Puro: cada ranura cerrada, con su eje y sus extremos a ≥ 1,5·d0 del canto, y recorre
    −montaje … +tensado sobre la línea de centros (el perno no toca sus extremos)."""
    vistos = set()
    for d in _disposiciones():
        m = d.motriz
        a = math.radians(m.angulo_deg)
        o = m.oreja
        u_ext, w_sup, w_inf = o["u_ext"], o["w_sup"], o["w_inf"]
        vistos.add((m.motor, round(m.tensado_mm, 2)))
        for ran, signo in zip(o["ranuras"], (1.0, -1.0), strict=True):
            uc, wc = _uw(ran["centro"], a)
            r, mitad = ran["ancho"] / 2.0, ran["largo"] / 2.0
            assert ran["ancho"] == RANURA_OREJA
            # e3 (canto lateral) y e4 (canto del extremo): ligamento + d0/2
            assert u_ext - (abs(uc) + r) + r >= E_MIN
            assert w_sup - (wc + mitad) + r >= E_MIN
            assert w_inf + (wc - mitad) + r >= E_MIN
            # el perno corre de −montaje a +tensado dentro de la ranura
            _, wp = _uw(ran["perno"], a)
            assert wp == pytest.approx(signo * W_PERNO, abs=1e-6)
            assert wc - mitad < wp - MONTAJE_MM - r and wp + m.tensado_mm + r < wc + mitad
    assert len({mt for mt, _t in vistos}) >= 4 and max(t for _m, t in vistos) > 9.0


@pytest.fixture(scope="module")
def l2000():
    doc = Document("rodillos-oreja")
    doc.execute("create_roller_conveyor", {"largo": 2000, "ancho_util": 400, "altura": 500,
                                           "union": "soldado"})
    return doc


def test_la_puerta_mide_e_minimo_en_los_agujeros_de_la_oreja(l2000):
    """La máquina del defecto (L2000 W400 H500, sellada: `mantenimiento`, pernos modelados): los
    4 agujeros de las orejas, medidos como ranura, con e ≥ 1,5·d0. Antes: e = 16,02 mm."""
    esc = _Escena(l2000.scene)
    agujeros, _pasos = insumos_bordes(l2000, insumos_pernos(l2000, escena=esc), esc)
    orejas = [x for x in agujeros if "Oreja del portamotor" in (x.get("nombre") or "")]
    assert len(orejas) == 4
    for x in orejas:
        assert x["estado"] == "medido" and x["forma"] == "ranura", x
        assert x["e_min"] == pytest.approx(E_MIN) and x["e"] >= E_MIN and x["cumple"], x


def test_las_ranuras_de_la_oreja_son_cerradas(l2000):
    """La oreja rodea cada ranura: sobre la línea de centros, más allá de cada extremo hay
    material (antes el extremo de arriba de la A y el de abajo de la B abrían al canto)."""
    m = _motriz(l2000)
    a = math.radians(m.angulo_deg)
    pm = m.portamotor
    for s in ("m", "p"):
        oreja = l2000.scene[f"c1_oreja_{s}"].shape
        y = oreja.bounding_box().center().Y
        for ran in m.oreja["ranuras"]:
            xc, zc = ran["centro"]
            for signo in (1.0, -1.0):
                k = signo * (ran["largo"] / 2.0 + 3.0)
                q = (pm["x"] + xc + k * math.sin(a), y, pm["z"] + zc + k * math.cos(a))
                assert oreja.is_inside(q), (s, ran["frena"], signo)
            assert not oreja.is_inside((pm["x"] + xc, y, pm["z"] + zc))


def _motriz(doc):
    cmd = next(c for c in doc.commands if c["type"] == "create_roller_conveyor")
    return disposicion_de(CreateRollerConveyorParams.model_validate(cmd["params"])).motriz
