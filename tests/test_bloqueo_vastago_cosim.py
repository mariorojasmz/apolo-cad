"""El bloqueo de vástago en la co-simulación con MuJoCo (plan bloqueo-de-vastago F1, D4, D5, D8).

El banco (`bloqueo_escena.py`) es el caso de la faja con desviador: Ø63 × 400 con una 5/3 de centro
a escape y el escape de la A más cerrado que el de la B. La seta se pulsa a media carrera:
  - SIN bloqueo, el aire que queda en la A lleva el vástago hasta el tope (lo de hoy);
  - CON el bloqueo (KEC-20-S, 3200 N), su 3/2 se suelta con la seta, la liberación se descarga y
    las mordazas muerden: el vástago queda quieto aunque la A siga con presión;
  - con una retención menor que la fuerza residual, desliza: la señal `desliza`, el resumen del
    escenario y el veredicto lo marcan;
  - sin bloqueo, el acople no toca la fricción de la junta (D8: la huella de antes; medido contra
    la base en la bitácora del plan).
"""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")

from bloqueo_escena import CARRERA, desviador, escenario  # noqa: E402
from cosim_lazo_banco import cambios, en, serie  # noqa: E402

from apolo.cosim.corrida import Corrida  # noqa: E402
from apolo.cosim.planificador import correr  # noqa: E402
from apolo.services.aire_resultado import resumen_aire  # noqa: E402
from apolo.services.cosim_snapshot import snapshot_cosim  # noqa: E402

SETA_S = 0.9


@pytest.fixture(scope="module")
def sin():
    d, cid = desviador(bloqueo=False)
    return correr(snapshot_cosim(d, escenario(cid, seta_s=SETA_S)))


@pytest.fixture(scope="module")
def con():
    d, cid = desviador()
    return correr(snapshot_cosim(d, escenario(cid, seta_s=SETA_S)))


def test_sin_bloqueo_el_aire_que_queda_lo_lleva_al_tope(sin):
    x_seta = en(sin, "-MM1.x_mm", SETA_S)
    assert 150 < x_seta < 300                                  # a media carrera
    assert sin["final"]["-MM1.x_mm"] == pytest.approx(CARRERA, abs=1.0)
    assert en(sin, "-MM1.pA_bar", 1.5) > 2.0                   # la A sigue con presión


def test_con_bloqueo_el_vastago_queda_quieto(con):
    (t_mordio,) = [t for t, v in cambios(con, "-RL1.bloqueado") if v is True and t > SETA_S]
    # la 3/2 suelta (22 ms de la ficha), la liberación se descarga y las mordazas cierran (10 ms)
    assert SETA_S + 0.022 < t_mordio < SETA_S + 0.06
    x_mordio = en(con, "-MM1.x_mm", t_mordio)
    tras = [(t, v) for t, v in serie(con, "-MM1.v_m_s") if t > t_mordio + 0.04]
    assert max(abs(v) for _t, v in tras) < 1e-3                # |v| ≈ 0 tras el bloqueo
    assert con["final"]["-MM1.x_mm"] == pytest.approx(x_mordio, abs=1.0)
    assert con["final"]["-MM1.x_mm"] < CARRERA - 100           # no llegó al tope
    assert en(con, "-MM1.pA_bar", 1.5) > 2.0 and en(con, "-MM1.F_N", 1.5) > 500   # aunque el aire empuja
    assert con["final"]["-RL1.F_N"] == pytest.approx(3200, rel=1e-3)
    assert con["final"]["-RL1.sobrerrecorrido_mm"] < 1.0
    assert cambios(con, "-RL1.desliza") == [[0.0, False]]
    # al arrancar muerde (sin aire en su línea) y la 3/2 lo libera en cuanto la seta da tensión
    assert cambios(con, "-RL1.bloqueado")[:2] == [[0.0, True], [0.02, False]]
    assert any("bloqueo de vástago: sujeción F = F_ret" in h for h in con["hipotesis"])
    bl = resumen_aire(con)["bloqueos"]["-RL1"]
    assert bl["deslizo"] is False and bl["F_max_N"] == pytest.approx(3200, rel=1e-3)


def test_retencion_insuficiente_desliza():
    d, cid = desviador()
    snap = snapshot_cosim(d, escenario(cid, seta_s=SETA_S))
    rl = next(x for x in snap.dispositivos if x.designacion == "-RL1")
    rl.modelo["aire"]["F_retencion_N"] = 150.0   # una sujeción menor que la fuerza residual
    r = correr(snap)
    des = cambios(r, "-RL1.desliza")
    assert any(v is True and t > SETA_S for t, v in des)
    assert r["final"]["-MM1.x_mm"] > en(r, "-MM1.x_mm", SETA_S) + 20   # siguió andando
    bl = resumen_aire(r)["bloqueos"]["-RL1"]
    assert bl["deslizo"] is True and bl["t_desliza_s"] > SETA_S and bl["sobrerrecorrido_mm"] > 20


def test_sin_bloqueo_el_acople_no_toca_la_junta():
    d, cid = desviador(bloqueo=False)
    c = Corrida(snapshot_cosim(d, escenario(cid, duracion=0.6, seta_s=0.5)))
    m = c.integ.m
    antes = (list(m.dof_frictionloss), [tuple(r) for r in m.dof_solref], [tuple(r) for r in m.dof_solimp])
    for k in range(c.integ.n_int):
        c.intercambio(k)
    assert c.aire.frenos == {}
    assert (list(m.dof_frictionloss), [tuple(r) for r in m.dof_solref], [tuple(r) for r in m.dof_solimp]) == antes


def test_determinista_bit_a_bit(con):
    d, cid = desviador()
    assert correr(snapshot_cosim(d, escenario(cid, seta_s=SETA_S)))["resumen"]["huella"] == con["resumen"]["huella"]
