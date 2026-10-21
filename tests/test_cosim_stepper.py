"""El stepper de la dinámica (plan V8.3 F4): `simulate_dynamics` partido en `Integrador` /
`intercambio` / `salida` SIN cambiar lo que calcula V8.2.

La referencia es el bucle cerrado de V8.2 copiado tal cual (`dinamica_v82_referencia.py`): con la
misma petición, la salida es IDÉNTICA (JSON igual salvo el tiempo de pared), con fuente ideal y
con motor por placa con arranque diferido y rampa, productos en serie y fotocelda. En la faja 73
lo midió la Bitácora de F4 (misma salida antes y después del corte).
"""

import json

import pytest

pytest.importorskip("mujoco")

from apolo.doc.document import Document  # noqa: E402
from apolo.physics.dinamica import prepare_dynamics, simulate_dynamics  # noqa: E402
from apolo.physics.dinamica_integrador import Integrador  # noqa: E402
from dinamica_v82_referencia import simulate_dynamics_v82  # noqa: E402

Z_CAJA = 800 + 50 + 0.5
PLACA = {"placa": {"potencia_kW": 0.75, "rpm": 1700, "polos": 4, "tk_tn": 2.6, "frecuencia_hz": 60,
                   "inercia_rotor_kgm2": 0.0026}, "reduccion": 28.3, "eta": 0.94, "frecuencia_hz": 60}


@pytest.fixture(scope="module")
def faja():
    doc = Document("faja-stepper")
    doc.execute("create_belt_conveyor", {"largo": 3000, "ancho_banda": 500, "altura": 800})
    return doc


def _peticion(motor: dict) -> dict:
    return {
        "con_autodeteccion": True, "duracion_s": 1.0, "fps": 40,
        "motores": [{"junta": "c1_eje_motriz", "modo": "velocidad", "direccion_transporte": [1, 0, 0], **motor}],
        "productos": [{"nombre": "caja", "dims_mm": [150, 120, 100], "masa_kg": 2.0, "cada_s": 0.3,
                       "posicion_mm": [-300, 0, Z_CAJA]}],
        "sensores": [{"nombre": "foto", "origen": [-150, -400, 850], "direccion": [0, 1, 0], "alcance_mm": 800}],
    }


def _sin_pared(res: dict) -> str:
    r = json.loads(json.dumps(res))
    r["resumen"].pop("t_pared_s")
    r["resumen"].pop("factor_tiempo_real")
    return json.dumps(r, sort_keys=True)


@pytest.mark.parametrize("motor", [{"v_superficie_m_s": 0.25},
                                   {**PLACA, "desde_s": 0.1, "rampa_s": 0.2}], ids=["ideal", "placa"])
def test_el_integrador_reproduce_simulate_dynamics_de_v82_bit_a_bit(faja, motor):
    snap = prepare_dynamics(faja.scene, faja.joints, faja.fasteners, faja.grounds, _peticion(motor),
                            mates=faja.mates)
    nuevo = simulate_dynamics(snap)
    assert _sin_pared(nuevo) == _sin_pared(simulate_dynamics_v82(snap))
    assert nuevo["sensores"]["foto"]["cuentas"] >= 1  # hubo cajas, banda y fotocelda de verdad


def test_avanzar_de_a_un_intercambio_es_el_bucle_de_v82(faja):
    snap = prepare_dynamics(faja.scene, faja.joints, faja.fasteners, faja.grounds,
                            _peticion({"v_superficie_m_s": 0.25}), mates=faja.mates)
    integ = Integrador(snap)
    vistos = []
    for _ in range(integ.n_int):
        integ.intercambio()
        vistos.append(integ.t)
    assert vistos[0] == pytest.approx(snap.timestep * snap.nstep)
    assert integ.hechos == integ.n_int == 500
    assert _sin_pared(integ.salida()) == _sin_pared(simulate_dynamics_v82(snap))


def test_el_control_reemplaza_a_los_motores_de_la_peticion(faja):
    """`control(d, t)` toma el lugar de `ControlMotores.aplicar`: sin él escribir nada, el
    `<velocity>` queda con su consigna inicial 0 y ganancia de la petición → la banda no arranca;
    con consigna, arranca. `fuerzas` corre después del arrastre (que borra `qfrc_applied`)."""
    snap = prepare_dynamics(faja.scene, faja.joints, faja.fasteners, faja.grounds,
                            _peticion({"v_superficie_m_s": 0.25}), mates=faja.mates)
    integ = Integrador(snap)
    a = integ.motores.ids[0]
    consigna = snap.motores[0].consigna
    dof = integ.juntas["c1_eje_motriz"][1]
    aplicadas = []

    def control(d, t):
        d.ctrl[a] = consigna if t >= 0.5 - 1e-9 else 0.0

    def fuerzas(d, t):
        aplicadas.append(float(d.qfrc_applied[dof]))

    for _ in range(integ.n_int):
        integ.intercambio(control=control, fuerzas=fuerzas)
    res = integ.salida()
    qd = res["juntas"]["c1_eje_motriz"]["qd"]
    t = res["juntas"]["c1_eje_motriz"]["t"]
    assert all(abs(v) < 1.0 for tt, v in zip(t, qd) if tt < 0.5)  # frenado con consigna 0
    assert abs(qd[-1]) > 10.0
    assert len(aplicadas) == integ.n_int and any(abs(x) > 0 for x in aplicadas)
