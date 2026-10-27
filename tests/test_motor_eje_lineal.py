"""Un motor rotativo mueve una junta PRISMÁTICA por su transmisión (plan motor-a-eje-lineal F2).

El elevador mínimo de `elevador_escena.py` (plataforma de ~141 kg en una prismática vertical,
NMRV-090 i = 40 por variador, piñón de d0 = 61,09 mm): sube con su carga a v = ω·r, el sensor de
nivel por junta la ve y el PLC la para; sin par la gravedad la baja (reversible) o la retiene
(irreversible). Sin transmisión declarada, el snapshot y el MJCF son los de siempre."""

from __future__ import annotations

import math

import pytest

pytest.importorskip("mujoco")

from elevador_escena import D0_MM, JUNTA, NIVEL_MM, PROGRAMAS, elevador, escenario, transmision  # noqa: E402

from apolo.cosim.corrida import Corrida  # noqa: E402
from apolo.cosim.escenario import EscenarioInvalido, leer_escenario  # noqa: E402
from apolo.cosim.planificador import correr  # noqa: E402
from apolo.services.cosim_snapshot import snapshot_cosim  # noqa: E402
from apolo.services.errors import ServiceError  # noqa: E402

G = 9.81
R_M = D0_MM / 2000.0


@pytest.fixture(scope="module")
def doc():
    return elevador()


def _correr(doc, esc):
    snap = snapshot_cosim(doc, esc, programas=PROGRAMAS)
    return snap, correr(snap)


def _en(serie_t, serie, t):
    """El valor de la serie en el primer instante ≥ t."""
    return next(v for tt, v in zip(serie_t, serie) if tt >= t - 1e-9)


@pytest.fixture(scope="module")
def subida(doc):
    return _correr(doc, escenario(8.0, tr=transmision(irreversible=True)))


def test_sube_con_su_carga_a_omega_por_r(subida):
    snap, r = subida
    j = r["mecanica"]["juntas"][JUNTA]
    a = r["trazas"]["analogicas"]
    v = _en(j["t"], j["qd"], 3.0)                                  # mm/s, en régimen
    rpm = _en(a["t"], a["senales"]["-M1.rpm_salida"], 3.0)        # el eje de salida
    assert v == pytest.approx(rpm * 2 * math.pi / 60 * D0_MM / 2, rel=5e-3)
    assert 130 < v < 150                       # ≈ ωs(60 Hz)/i · r = 4,71 · 30,5 mm, con su deslizamiento
    masa = next(c["masa_kg"] for c in snap.dinamica.cuerpos if c["junta"] == JUNTA)
    par = _en(a["t"], a["senales"]["-M1.par_salida_Nm"], 3.0)
    assert par == pytest.approx(masa * G * R_M, rel=0.02)  # la carga llega al eje: T = m·g·r


def test_el_sensor_de_nivel_por_junta_la_para(subida):
    _snap, r = subida
    j = r["mecanica"]["juntas"][JUNTA]
    disc = r["trazas"]["discretas"]
    t_nivel = next(t for t, v in disc["-B1.activo"] if v)
    t_paro = next(t for t, v in disc["-K1.vfd_marcha"] if t > 0.31 and not v)
    assert _en(j["t"], j["q"], t_nivel) == pytest.approx(NIVEL_MM - 10, abs=8)
    assert 0 < t_paro - t_nivel < 0.05          # el PLC corta en el scan que la ve
    q_final = j["q"][-1]
    assert NIVEL_MM < q_final < NIVEL_MM + 80   # la rampa de 0,8 s la pasa un poco
    # irreversible: sin tensión no baja
    assert abs(q_final - _en(j["t"], j["q"], 6.0)) < 0.5


def test_sin_par_la_gravedad_la_baja_y_el_sinfin_la_retiene(doc):
    _s, rev = _correr(doc, escenario(2.0, marcha=False))
    q = rev["mecanica"]["juntas"][JUNTA]["q"]
    assert q[-1] < -50 and all(b <= a + 1e-6 for a, b in zip(q, q[1:]))
    _s, irr = _correr(doc, escenario(2.0, marcha=False, tr=transmision(irreversible=True)))
    assert abs(irr["mecanica"]["juntas"][JUNTA]["q"][-1]) < 0.5


def test_el_pinon_sale_del_modelo():
    d = elevador(pinon=True)
    pin = next(fid for fid, f in d.scene.items() if getattr(f, "component", None) == "PINON-08B-1-Z15")
    snap = snapshot_cosim(d, escenario(0.5, tr={"pinon": pin}), programas=PROGRAMAS)
    assert any("d0 = 61.09 mm de su ficha" in h for h in snap.hipotesis)
    assert f'gear="{1 / R_M:.12g}"' in snap.dinamica.xml
    c = Corrida(snap)
    assert c.acople.friccion_de(JUNTA, 10.0) == pytest.approx(10.0 / R_M, rel=1e-9)  # el atasco, en N


@pytest.mark.parametrize("tr, texto", [
    ({"diametro_primitivo_mm": 61.09}, "pide «fuente»"),
    ({"diametro_primitivo_mm": 61.09, "avance_mm": 5, "fuente": "x"}, "UNA fuente"),
    ({"avance_mm": -5, "fuente": "x"}, "> 0"),
    ({"pinon": "c1", "radio": 3}, "no reconocida"),
    ({"avance_mm": 5, "fuente": "x", "irreversible": "si"}, "true o false"),
])
def test_la_transmision_mal_declarada(tr, texto):
    with pytest.raises(EscenarioInvalido, match=texto):
        leer_escenario(escenario(1.0, tr=tr))


def test_los_400_contra_el_documento(doc):
    with pytest.raises(ServiceError, match="PRISMÁTICA.*transmision"):
        snapshot_cosim(doc, escenario(1.0, tr=False), programas=PROGRAMAS)
    col = next(fid for fid, f in doc.scene.items() if f.name == "Columna")
    with pytest.raises(ServiceError, match="no trae diámetro primitivo"):
        snapshot_cosim(doc, escenario(1.0, tr={"pinon": col}), programas=PROGRAMAS)
    with pytest.raises(ServiceError, match="no es una pieza"):
        snapshot_cosim(doc, escenario(1.0, tr={"pinon": "c999"}), programas=PROGRAMAS)


def test_sin_transmision_todo_como_antes():
    """Un escenario viejo (motor a una junta de giro, sin `transmision`): la lectura no suma la
    clave, el `<velocity>` sale sin `gear` y el acople lee con gear 1 (la huella de siempre: la
    bitácora del plan la compara con los resultados guardados)."""
    from cosim_lazo_banco import escenario_variador, faja_variador

    esc = escenario_variador(0.5)
    assert "transmision" not in leer_escenario(esc).motores["-M1"]
    snap = snapshot_cosim(faja_variador(), esc)
    assert "<velocity" in snap.dinamica.xml and "gear=" not in snap.dinamica.xml.split("<actuator>")[1]
    c = Corrida(snap)
    assert [g for *_x, g, _r in c.acople.motores] == [1.0] and c.acople.gear_dof == {}
