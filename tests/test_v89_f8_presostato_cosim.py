"""El presostato en la co-simulación (plan V8.9 F8): contacto que lee la presión de SU línea.

El banco (`presostato_escena.py`) es el empujador de F3 mandado por un PLC con el presostato
-BP1 (conmuta a 4 bar, histéresis 0,5 de la ficha) en I0.0:
  - el integral del contrato: el corte de aire abre el NA, el PLC lo ve y para la máquina
    (suelta la válvula y enclava la falla) antes de que el cilindro pierda fuerza;
  - en la cámara B, con la presión de red que baja y sube: la histéresis en la máquina entera;
  - en la toma (la entrada del FRL) lee la presión de red; con un ajuste de PRUEBA del escenario
    sobre la regulada el NA no cierra y la máquina no arranca;
  - el determinismo bit a bit de la corrida con presostato.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")

from cosim_lazo_banco import cambios, primer_cambio, serie  # noqa: E402
from presostato_escena import empujador_con_presostato, escenario  # noqa: E402

from apolo.cosim.planificador import correr  # noqa: E402
from apolo.services.cosim_snapshot import snapshot_cosim  # noqa: E402

CORTE = 1.0


@pytest.fixture(scope="module")
def alimentacion():
    return empujador_con_presostato("alimentacion")


@pytest.fixture(scope="module")
def corte(alimentacion):
    d, cid = alimentacion
    return correr(snapshot_cosim(d, escenario(cid, corte_s=CORTE)))


def test_el_corte_de_aire_abre_el_presostato_y_el_plc_para_antes_de_que_el_cilindro_pierda_fuerza(corte):
    r = corte
    # la marcha arranca con aire: el vástago sale y sostiene con toda la fuerza (6 bar en A)
    assert primer_cambio(r, "-K1.Main.en_marcha", True) == pytest.approx(0.21)
    F = serie(r, "-MM1.F_N")
    F0 = min(f for t, f in F if 0.8 <= t <= CORTE - 1e-9)
    assert F0 == pytest.approx(482.5, abs=1.0)
    # el presostato lee la línea de alimentación: abre en el intercambio del corte
    assert cambios(r, "-BP1.activo") == [[0.0, True], [CORTE, False]]
    # el PLC lo ve en su entrada y en su próximo scan (10 ms) para y enclava la falla
    t_in = primer_cambio(r, "-K1.%IX0.0", False, desde=0.5)
    t_falla = primer_cambio(r, "-K1.Main.falla_aire", True)
    t_para = primer_cambio(r, "-K1.Main.en_marcha", False, desde=0.5)
    assert CORTE < t_in <= CORTE + 0.01 and t_falla == t_para and t_falla <= CORTE + 0.02
    assert primer_cambio(r, "-QM2.bobina14", False, desde=0.5) <= t_falla + 0.01   # suelta la válvula
    # … antes de que el cilindro pierda fuerza: la cámara A se descarga por el FRL (sin
    # antirretorno, hipótesis de F3) en decenas de ms; cuando el PLC ya paró, todavía empuja
    F_en_falla = min(F, key=lambda tf: abs(tf[0] - t_falla))[1]
    t_media = next(t for t, f in F if t > CORTE and f < 0.5 * F0)
    assert F_en_falla > 0.75 * F0 and t_media > t_falla
    assert r["final"]["-K1.Main.falla_aire"] is True and r["final"]["-BP1.p_bar"] == 0.0
    assert any("-BP1: lee la línea de alimentación" in h for h in r["hipotesis"])
    assert any(h.startswith("-BP1: el contacto conmuta en el intercambio") for h in r["hipotesis"])


def test_sin_el_corte_nada_cambia_y_la_corrida_es_bit_a_bit(alimentacion, corte):
    d, cid = alimentacion
    r = correr(snapshot_cosim(d, escenario(cid, corte_s=None)))
    assert cambios(r, "-BP1.activo") == [[0.0, True]] and r["final"]["-K1.Main.falla_aire"] is False
    assert r["final"]["-BP1.p_bar"] == pytest.approx(6.0)
    otra = correr(snapshot_cosim(d, escenario(cid, corte_s=CORTE)))
    assert otra["resumen"]["huella"] == corte["resumen"]["huella"]


def test_un_presostato_pegado_no_avisa_el_corte(alimentacion):
    """La falla a propósito (cosim-fallas): pegado cerrado, el PLC no ve el corte y no para."""
    d, cid = alimentacion
    ev = [{"t": 0.5, "tipo": "falla", "dispositivo": "-BP1", "falla": "pegado"}]
    r = correr(snapshot_cosim(d, escenario(cid, 1.2, corte_s=CORTE, eventos=ev + [
        {"t": CORTE, "tipo": "corte_de_aire"}])))
    assert cambios(r, "-BP1.activo") == [[0.0, True]] and r["final"]["-BP1.averia"] == "pegado"
    assert r["final"]["-K1.Main.falla_aire"] is False and r["final"]["-K1.Main.en_marcha"] is True
    assert r["final"]["-BP1.p_bar"] == 0.0                      # lee la atmósfera, el contacto no se mueve


def test_en_la_camara_b_la_histeresis_con_la_presion_de_red():
    """Sin marcha el vástago queda retraído con B a la regulada; la red baja a 3,8 bar (entre los
    umbrales: sigue cerrado), a 3,0 (abre), sube a 3,8 (sigue abierto) y a 6 (cierra)."""
    d, cid = empujador_con_presostato("B")
    ev = [{"t": t, "tipo": "presion_de_red", "bar": bar} for t, bar in ((0.3, 3.8), (0.6, 3.0), (0.9, 3.8), (1.2, 6.0))]
    r = correr(snapshot_cosim(d, escenario(cid, 1.5, corte_s=None, eventos=ev, acciones=[])))
    act = cambios(r, "-BP1.activo")
    assert [v for _, v in act] == [True, False, True]
    assert 0.6 < act[1][0] < 0.9 and 1.2 < act[2][0] < 1.5
    p = dict(serie(r, "-BP1.p_bar"))
    pb = dict(serie(r, "-MM1.pB_bar"))
    assert all(abs(p[t] - pb[t]) < 1e-6 for t in p)                      # lee la cámara B
    assert min(v for t, v in p.items() if 0.45 <= t < 0.6) == pytest.approx(3.8, abs=0.01)  # entre umbrales
    # abre al BAJAR de 3,5 y cierra al LLEGAR a 4 (la muestra de antes del cambio, del lado de antes)
    antes_abrir = max(t for t in p if t < act[1][0])
    antes_cerrar = max(t for t in p if t < act[2][0])
    assert p[antes_abrir] >= 3.5 - 0.05 and p[antes_cerrar] < 4.0
    assert any("-BP1: lee la presión de la cámara B de -MM1" in h for h in r["hipotesis"])


def test_en_la_toma_lee_la_red_y_el_ajuste_de_prueba_sobre_la_regulada_no_arranca():
    d, cid = empujador_con_presostato("toma")
    r = correr(snapshot_cosim(d, escenario(cid, 0.6, corte_s=0.5)))
    assert cambios(r, "-BP1.activo") == [[0.0, True], [0.5, False]]
    d, cid = empujador_con_presostato("alimentacion")
    snap = snapshot_cosim(d, escenario(cid, 0.6, corte_s=None, ajustes={"-BP1": {"p_conmuta_bar": 7}}))
    r = correr(snap)
    assert cambios(r, "-BP1.activo") == [[0.0, False]]           # 6 bar regulados no llegan a 7
    assert cambios(r, "-K1.Main.en_marcha") == [[0.0, False]]    # sin aire «ok», la marcha no arranca
    assert any("p_conmuta_bar" in h and "PRUEBA" in h for h in r["hipotesis"])
