"""El balance de producto contado en la dinámica (plan balance-de-producto, D3–D5).

Una faja de 3 m (banda a z = 800, de x ≈ −1555 a 1561) con dos carriles de cajas y dos SALIDAS:
«rampa» (un plano oblicuo que sólo cruza el carril y = −120 antes del fin de la banda) y «fin»
(x = 1400). Sobre ella:
  - el balance cuadra: cada caja sale por SU salida, las que entraron hace poco van en tránsito;
  - un obstáculo sobre la banda traba una caja: el balance la nombra, con el lugar y la hora;
  - una caja que nace al costado de la banda cae al piso: perdida;
  - el mismo snapshot da el mismo balance (determinista) y sin `flujo` la salida no lo trae.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")

from apolo.doc.document import Document  # noqa: E402
from apolo.physics.dinamica import prepare_dynamics, simulate_dynamics  # noqa: E402

MOTOR = {"junta": "c1_eje_motriz", "modo": "velocidad", "v_superficie_m_s": 0.5,
         "direccion_transporte": [1.0, 0.0, 0.0]}
SUMIDEROS = [{"nombre": "rampa", "punto_mm": [900, 0, 0], "normal": [1, -6, 0]},
             {"nombre": "fin", "punto_mm": [1400, 0, 0], "normal": [1, 0, 0]}]
CAJA = {"dims_mm": [150, 120, 100], "masa_kg": 2.0}


def _faja(obstaculo: bool = False) -> Document:
    doc = Document("faja-flujo")
    doc.execute("create_belt_conveyor", {"largo": 3000, "ancho_banda": 500, "altura": 800})
    if obstaculo:  # un travesaño a 20 mm sobre la banda: la caja de 100 mm no pasa
        fid = doc.execute("create_box", {"name": "Obstáculo", "width": 60, "depth": 700, "height": 150,
                                         "position": {"x": 600, "y": 0, "z": 895}})
        doc.execute("ground", {"name": "g_obstaculo", "feature": fid})
    return doc


def _peticion(productos, duracion=14.0, **flujo) -> dict:
    return {"duracion_s": duracion, "fps": 5, "motores": [MOTOR], "productos": productos,
            "sumideros": SUMIDEROS, "flujo": {"plazo_s": 8.0, **flujo}}


def _correr(doc, pet) -> dict:
    snap = prepare_dynamics(doc.scene, doc.joints, doc.fasteners, doc.grounds, pet, mates=doc.mates)
    return simulate_dynamics(snap)


def _carriles() -> list[dict]:
    """Dos series alternadas a 30/min: −120 desde 0 s y +120 desde 2 s, cada una cada 4 s."""
    return [{"nombre": "izq", **CAJA, "posicion_mm": [-1000, -120, 850.5], "cada_s": 4.0},
            {"nombre": "der", **CAJA, "posicion_mm": [-1000, 120, 850.5], "cada_s": 4.0, "desde_s": 2.0}]


@pytest.fixture(scope="module")
def faja():
    return _faja()


@pytest.fixture(scope="module")
def verde(faja):
    return _correr(faja, _peticion(_carriles()))


def test_cada_caja_sale_por_su_salida_y_el_balance_cuadra(verde):
    fl = verde["flujo"]
    assert fl["sumideros"] == ["rampa", "fin"]
    # nacen a 0, 2, 4, 6, 8, 10 y 12 s (la de 14 s es la hora del final: no llega a entrar)
    assert fl["entraron"] == 7
    assert fl["por_sumidero"] == {"rampa": 3, "fin": 2}, fl
    assert sorted(fl["en_transito"]) == ["p_der_2", "p_izq_3"]
    assert not (fl["perdidos"] or fl["trabados"] or fl["retenidos"] or fl["sin_entrar"])
    assert fl["cuadra"] is True
    assert 2.0 < fl["transito_max_s"] < 8.0  # el carril largo: 2,7 m a 0,5 m/s
    s = fl["senales"]
    assert s["flujo.entraron"][0] == [0.0, 1] and s["flujo.entraron"][-1][1] == 7
    assert s["flujo.rampa"][-1][1] == 3 and s["flujo.fin"][-1][1] == 2
    assert s["flujo.cuadra"] == [[0.0, True]]
    assert s["flujo.en_maquina"][-1][1] == 2


def test_el_mismo_snapshot_da_el_mismo_balance(faja, verde):
    otra = _correr(faja, _peticion(_carriles()))
    assert otra["flujo"] == verde["flujo"]


def test_sin_flujo_la_salida_no_lo_trae(faja):
    pet = _peticion(_carriles()[:1], duracion=1.0)
    pet.pop("flujo")
    res = _correr(faja, pet)
    assert "flujo" not in res


def test_un_obstaculo_traba_la_caja_y_el_balance_la_nombra():
    doc = _faja(obstaculo=True)
    caja = {"nombre": "caja", **CAJA, "posicion_mm": [-1000, 0, 850.5]}
    fl = _correr(doc, _peticion([caja], duracion=8.0, quieto_s=1.5))["flujo"]
    assert fl["cuadra"] is False and fl["entraron"] == 1 and fl["salieron"] == 0
    (t,) = fl["trabados"]
    assert t["producto"] == "p_caja"
    # contra la cara de atrás del travesaño (x = 570): el centro de la caja a ~75 mm antes
    assert 450 < t["pos_mm"][0] < 560, t
    assert t["t"] == pytest.approx(t["desde_s"] + 1.5, abs=0.01)
    assert 2.0 < t["desde_s"] < 5.0  # 1,8 m a 0,5 m/s
    assert fl["senales"]["flujo.trabados"][-1] == [pytest.approx(t["t"]), 1]
    assert fl["senales"]["flujo.cuadra"][-1] == [pytest.approx(t["t"]), False]


def test_la_caja_que_cae_al_piso_es_perdida(faja):
    afuera = {"nombre": "afuera", **CAJA, "posicion_mm": [-500, 600, 850.5]}
    fl = _correr(faja, _peticion([afuera], duracion=2.0))["flujo"]
    (p,) = fl["perdidos"]
    assert p["producto"] == "p_afuera" and p["pos_mm"][2] < 95.0 and 0.2 < p["t"] < 1.0
    assert fl["cuadra"] is False and not fl["trabados"]  # quieta en el piso: perdida, no trabada
    assert fl["senales"]["flujo.en_maquina"][-1][1] == 0
