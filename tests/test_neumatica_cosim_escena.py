"""La co-simulación del aire en una escena física (plan V8.9 F3, D3/D4/D6/D7/D8).

El banco (`neumatica_escena.py`): un Ø32 de `create_pneumatic_cylinder` con su empujador frente a
una caja en una mesa, su circuito de aire en el carril y la bobina de la válvula mandada por un
pulsador. Se verifica:
  - la caja sale empujada por el vástago, que avanza y vuelve con la válvula, con sus señales de
    D7 (posición, bobina, presiones, fuerza, consumo del FRL);
  - el determinismo bit a bit (D9 de V8.3), también en el worker aparte;
  - los 400 de D3/D8 (sin presión de red, sin acople del cilindro, acople a otra junta);
  - los eventos y fallas de D8: corte de aire, presión de red, fuga, válvula pegada, bobina
    cortada; el accionamiento manual, la válvula de corte, la biestable y el detector en la junta.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")

from cosim_lazo_banco import cambios, en, serie  # noqa: E402
from neumatica_escena import CAJA_X, CARRERA, empujador, escenario  # noqa: E402

from apolo.cosim.planificador import correr  # noqa: E402
from apolo.services.cosim_snapshot import snapshot_cosim  # noqa: E402
from apolo.services.errors import ServiceError  # noqa: E402


@pytest.fixture(scope="module")
def mono():
    return empujador()


def _correr(doc_cid, **kw):
    d, cid = doc_cid
    return correr(snapshot_cosim(d, escenario(cid, **kw)))


@pytest.fixture(scope="module")
def base(mono):
    return _correr(mono)


def test_la_caja_sale_empujada_y_el_vastago_vuelve(base):
    r = base
    assert cambios(r, "-QM2.bobina14") == [[0.0, False], [0.2, True], [1.2, False]]
    pos = cambios(r, "-QM2.posicion")
    assert [v for _, v in pos] == ["12", "14", "12"]
    assert 0.2 < pos[1][0] <= 0.2 + 0.014 + 1e-9  # conmuta con el t_on de la ficha (14 ms)
    x = serie(r, "-MM1.x_mm")
    # el tope de la junta es blando (solreflimit): el vástago llega a ~4 m/s (válvula G1/8 sin
    # regulación de caudal) y lo pasa un poco antes de asentar
    assert max(v for _, v in x) == pytest.approx(CARRERA, abs=2.0)
    assert en(r, "-MM1.x_mm", 2.0) == pytest.approx(0.0, abs=1.0)  # volvió con el muelle de la 5/2
    assert en(r, "-MM1.pA_bar", 1.0) == pytest.approx(6.0, abs=0.01)   # A con la regulada del FRL
    assert en(r, "-MM1.F_N", 1.0) == pytest.approx(482.5, abs=1.0)     # p·A − p_atm·a (6 bar, Ø32/12)
    caja = r["mecanica"]["resumen"]["productos"]["p_caja"]
    # empujada más allá de la carrera, casi derecho (a ~4 m/s sale despedida de la mesa: el vuelo
    # y la caída son caóticos, el desvío lateral exacto cambia de una máquina a otra)
    assert caja["posicion_final_mm"][0] > CAJA_X + CARRERA
    assert abs(caja["posicion_final_mm"][1]) < 0.05 * caja["posicion_final_mm"][0]
    assert en(r, "caja.x_mm", 0.2) == pytest.approx(CAJA_X, abs=0.5)   # quieta hasta que la toca
    # el aire del ciclo: avance + retroceso, contado una vez (en reposo no hay caudal)
    consumo = r["final"]["-AZ1.consumo_NL"]
    assert 1.6 < consumo < 2.6
    assert r["final"]["-AZ1.Q_Nl_min"] == 0.0 and r["final"]["-AZ1.p_bar"] == pytest.approx(6.0)
    assert any(h.startswith("aire: componentes en serie") for h in r["hipotesis"])
    assert any("fricción de los sellos" in h for h in r["hipotesis"])
    assert "aire" in r["resumen"]["costo_us_por_intercambio"]


def test_determinismo_bit_a_bit_y_en_el_worker(mono, base):
    from apolo.cosim.proceso import correr_en_proceso

    d, cid = mono
    snap = snapshot_cosim(d, escenario(cid))
    assert correr(snap)["resumen"]["huella"] == base["resumen"]["huella"]
    res = correr_en_proceso(snap, timeout_s=600)
    assert res["resumen"]["huella"] == base["resumen"]["huella"]
    assert res["proceso"]["modulos_pesados"] == []


def test_los_400_del_aire(mono):
    d, cid = mono
    with pytest.raises(ServiceError, match=r"condiciones\.presion_red_bar"):
        snapshot_cosim(d, escenario(cid, presion=None))
    esc = escenario(cid)
    esc["acoples"]["cilindros"] = {}
    with pytest.raises(ServiceError, match=rf'acoples\.cilindros = {{"-MM1": {{"junta": "{cid}_vastago"}}}}'):
        snapshot_cosim(d, esc)
    esc["acoples"]["cilindros"] = {"-MM1": {"junta": f"{cid}_jf_empujador"}}
    with pytest.raises(ServiceError, match="no es una junta prismática"):
        snapshot_cosim(d, esc)
    esc["acoples"]["cilindros"] = {"-QM2": {"junta": f"{cid}_vastago"}, "-MM1": {"junta": f"{cid}_vastago"}}
    with pytest.raises(ServiceError, match="«-QM2» no es un cilindro"):
        snapshot_cosim(d, esc)


def test_corte_de_aire_descarga_las_camaras(mono):
    r = _correr(mono, duracion=1.6, eventos=[{"t": 0.8, "tipo": "corte_de_aire"}])
    assert en(r, "-MM1.pA_bar", 0.7) == pytest.approx(6.0, abs=0.01)
    assert en(r, "-MM1.pA_bar", 1.5) < 0.05 and en(r, "-AZ1.p_bar", 1.5) == pytest.approx(0.0, abs=1e-6)
    assert en(r, "-MM1.x_mm", 1.5) > CARRERA - 5   # sin aire nada lo retira: queda donde estaba


def test_presion_de_red_mas_baja_que_la_regulada(mono):
    r = _correr(mono, duracion=1.2, eventos=[{"t": 0.0, "tipo": "presion_de_red", "bar": 3.0}])
    assert en(r, "-AZ1.p_bar", 1.0) == pytest.approx(3.0)
    assert en(r, "-MM1.F_N", 1.0) == pytest.approx(3e5 * 0.032 ** 2 * 3.14159265 / 4 - 0.0, rel=0.03)


def test_una_fuga_en_la_camara_consume_en_reposo(mono):
    r = _correr(mono, duracion=1.2, eventos=[{"t": 0.6, "tipo": "fuga", "puerto": "-MM1:A", "C": 0.05}])
    assert en(r, "-AZ1.Q_Nl_min", 1.0) > 5.0           # con la válvula en 14 la toma alimenta la fuga
    assert 4.0 < en(r, "-MM1.pA_bar", 1.0) < 6.0
    assert any("tobera ideal" in h for h in r["hipotesis"])


def test_fuga_en_un_puerto_que_no_es_de_camara(mono):
    d, cid = mono
    with pytest.raises(ServiceError, match="no es un puerto de la cámara de un cilindro"):
        snapshot_cosim(d, escenario(cid, eventos=[{"t": 0.5, "tipo": "fuga", "puerto": "-AZ1:2", "C": 0.05}]))


def test_valvula_pegada_y_bobina_cortada(mono):
    r = _correr(mono, duracion=1.0, eventos=[{"t": 0.1, "tipo": "falla", "dispositivo": "-QM2", "falla": "pegada"}])
    assert cambios(r, "-QM2.posicion") == [[0.0, "12"]] and cambios(r, "-QM2.bobina14")[1] == [0.2, True]
    assert max(v for _, v in serie(r, "-MM1.x_mm")) < 1.0
    assert r["final"]["-QM2.averia"] == "pegada 12"
    r = _correr(mono, duracion=1.0, eventos=[{"t": 0.1, "tipo": "falla", "dispositivo": "-QM2",
                                             "falla": "bobina_cortada"}])
    assert cambios(r, "-QM2.bobina14") == [[0.0, False]] and max(v for _, v in serie(r, "-MM1.x_mm")) < 1.0


def test_accionamiento_manual(mono):
    r = _correr(mono, duracion=2.0, pulsar_s=0, acciones=[
        {"t": 0.2, "accion": "accionar_manual", "dispositivo": "-QM2", "valor": "14"},
        {"t": 1.0, "accion": "accionar_manual", "dispositivo": "-QM2", "valor": "0"}])
    assert cambios(r, "-QM2.bobina14") == [[0.0, False]]   # sin tensión: lo movió la mano
    assert en(r, "-MM1.x_mm", 0.8) == pytest.approx(CARRERA, abs=1.0)
    assert en(r, "-MM1.x_mm", 1.9) == pytest.approx(0.0, abs=1.0)


def test_cerrar_el_corte_descarga_la_linea(mono):
    r = _correr(mono, duracion=1.0, pulsar_s=0, acciones=[
        {"t": 0.3, "accion": "cerrar", "dispositivo": "-QM1"}])
    assert cambios(r, "-QM1.abierta") == [[0.0, True], [0.3, False]]
    assert en(r, "-MM1.pB_bar", 0.2) == pytest.approx(6.0, abs=0.01) and en(r, "-MM1.pB_bar", 0.9) < 0.05


def test_biestable_conserva_y_el_detector_lee_la_junta():
    d, cid = empujador("VAL-52-BI-G18")
    sensores = {"-B1": {"junta": f"{cid}_vastago", "en_mm": CARRERA, "ventana_mm": 2}}
    r = correr(snapshot_cosim(d, escenario(cid, 2.0, pulsar_s=0.1, sensores=sensores, acciones=[
        {"t": 1.2, "accion": "pulsar", "dispositivo": "-S3", "durante_s": 0.1}])))
    assert [v for _, v in cambios(r, "-QM2.posicion")] == ["12", "14", "12"]
    assert en(r, "-MM1.x_mm", 1.0) == pytest.approx(CARRERA, abs=1.0)   # sin tensión, conserva
    assert en(r, "-MM1.x_mm", 1.95) == pytest.approx(0.0, abs=1.0)
    # el detector conmuta al llegar el pistón (el rebote contra el tope a ~4 m/s puede hacerlo
    # titilar unos ms, como a un reed real) y suelta al retroceder
    act = cambios(r, "-B1.activo")
    assert act[0] == [0.0, False] and act[1][1] is True and 0.3 < act[1][0] < 0.6
    assert act[-1][1] is False and act[-1][0] > 1.2
    assert [v for t, v in act if 0.6 < t < 1.2] == []          # firme mientras está afuera
