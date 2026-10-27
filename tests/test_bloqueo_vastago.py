"""El bloqueo de vástago sin la física (plan bloqueo-de-vastago F1, D1–D3, D5–D7).

  - la ficha de cada ref con su fuente (Festo KP/KPE/KEC/KEC-S [B1] y las hojas [B2]), y la que
    está incompleta no carga;
  - el builder: la envolvente de la ficha y el agujero del vástago a su Ø EXACTO;
  - `servicio.bloqueo`: un cilindro sin él guarda lo de antes;
  - el ERC: verde con la faja a mano (FS 1,71), rojo con retención insuficiente, con una ficha
    sólo estática, sin su 3/2, con presión de liberación corta o un bloqueo inexistente; aviso con
    la liberación fuera de la cadena de la seta; verde a través de un relé que corta la seta; el
    deslizamiento medido es rojo; sin bloqueos, el ERC y la memoria de antes;
  - el modelo de la co-simulación sin MuJoCo: la cámara de liberación se descarga por su 3/2 y la
    sujeción entra tras el retardo de las mordazas; el resumen del escenario.
"""

from __future__ import annotations

import math

import pytest
from bloqueo_escena import desviador

from apolo.cosim.neumatica import crear_modelo_aire
from apolo.cosim.neumatica.camara import Camino
from apolo.cosim.neumatica.orificio import P_ATM_PA
from apolo.library.catalog import CATALOG, build_component
from apolo.library.neumatica.erc import erc
from apolo.library.neumatica.erc_bloqueo import reglas as reglas_bloqueo
from apolo.library.neumatica.ficha import parse_ficha_neumatica
from apolo.library.neumatica.lineas import analizar
from apolo.services import neumatica as SN
from apolo.services.aire_resultado import resumen_aire
from apolo.services.cosim_aire import ficha_plana
from apolo.services.electrico import modelo

REFS = ("BLOQ-VAST-12", "BLOQ-VAST-16", "BLOQ-VAST-20", "BLOQ-VAST-25",
        "BLOQ-VAST-16-S", "BLOQ-VAST-20-S", "BLOQ-VAST-25-S")


def filas(doc) -> list[dict]:
    return [r for r in SN.reglas(modelo(doc), doc) if r["regla"] == "bloqueo de vástago"]


# ── la ficha y el builder (D1) ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ref", REFS)
def test_la_ficha_de_cada_ref_con_su_fuente(ref):
    c = CATALOG[ref]
    f = c.neumatico
    assert f.tipo == "bloqueo_vastago" and f.funcion == "RL" and [p.id for p in f.puertos] == ["1"]
    assert "Festo" in f.fuente and "[B1]" in f.fuente
    assert f.modelo["normalmente_bloqueado"] is True
    # lo que ninguna ficha publica va a confirmar: el volumen de liberación y el retardo
    assert {"V_liberacion_cm3", "t_mecanico_ms"} <= set(f.a_confirmar)
    assert "B10d" not in f.modelo   # ninguna ficha leída lo publica (D7)
    assert c.specs["d_vastago_mm"] == f.modelo["d_vastago_mm"]
    assert c.specs["F_retencion_N"] == f.modelo["F_retencion_N"]


def test_las_cifras_de_la_ficha_festo():
    """[B1] págs. 10-13 y [B2]: KEC Ø16/20/25 1300/3200/8000 N, 3,8 bar; la -S, categoría 1 PL c."""
    for d, F, rosca, peso in ((16, 1300, "G1/8", 1.860), (20, 3200, "G1/4", 4.515), (25, 8000, "G3/8", 15.6)):
        for suf, dinamico, pmax in (("-S", True, 8), ("", False, 10)):
            c = CATALOG[f"BLOQ-VAST-{d}{suf}"]
            m = c.neumatico.modelo
            assert (m["d_vastago_mm"], m["F_retencion_N"], m["p_liberacion_min_bar"]) == (d, F, 3.8)
            assert (m["frenado_dinamico"], m["p_max_bar"], c.neumatico.puertos[0].rosca, c.weight) == (
                dinamico, pmax, rosca, peso)
            assert (m.get("categoria_iso13849"), m.get("PL"), m.get("certificado")) == (
                (1, "c", "IFA 1504155") if dinamico else (None, None, None))
    kpe = CATALOG["BLOQ-VAST-12"].neumatico.modelo
    assert (kpe["F_retencion_N"], kpe["p_liberacion_min_bar"], kpe["frenado_dinamico"]) == (600, 3, False)


def test_una_ficha_incompleta_no_carga():
    crudo = {"funcion": "RL", "simbolo": "bloqueo_vastago", "fuente": "x",
             "puertos": [{"id": "1", "rol": "entrada", "rosca": "G1/4"}],
             "modelo": {"tipo": "bloqueo_vastago", "d_vastago_mm": 20, "p_liberacion_min_bar": 3.8,
                        "p_min_bar": 3.8, "p_max_bar": 8, "normalmente_bloqueado": True,
                        "frenado_dinamico": True, "V_liberacion_cm3": 15, "t_mecanico_ms": 10}}
    with pytest.raises(ValueError, match="F_retencion_N"):
        parse_ficha_neumatica(crudo, "X")
    crudo["modelo"].update(F_retencion_N=3200, p_liberacion_min_bar=9)
    with pytest.raises(ValueError, match="la liberación va entre"):
        parse_ficha_neumatica(crudo, "X")


def test_el_builder_la_envolvente_y_el_agujero_del_vastago():
    sh = build_component("BLOQ-VAST-20-S")[0]
    p = CATALOG["BLOQ-VAST-20-S"].params
    bb = sh.bounding_box()
    assert (bb.max.X - bb.min.X, bb.max.Y - bb.min.Y) == pytest.approx((p["largo"] + p["VD"], p["ancho"]))
    L1 = p["largo"] + p["VD"]
    esperado = (p["ancho"] * p["alto"] * p["largo"] + math.pi * (p["B"] / 2) ** 2 * p["VD"]
                - math.pi * (p["d"] / 2) ** 2 * L1)
    assert sh.volume == pytest.approx(esperado, rel=1e-3)   # el agujero, del Ø exacto del vástago
    assert len(sh.solids()) == 1
    an = CATALOG["BLOQ-VAST-20-S"].anchors
    assert an["cara_carga"]["origin"] == [L1, 0.0, 0.0] and an["vastago"]["axis"] == [1.0, 0.0, 0.0]


# ── la declaración (D2) ──────────────────────────────────────────────────────────────────────


def test_un_cilindro_sin_bloqueo_guarda_el_servicio_de_antes():
    d, _cid = desviador(bloqueo=False)
    cil = next(x for x in modelo(d).dispositivos if x.designacion == "-MM1")
    assert cil.servicio == {"carrera_mm": 400}
    d, _cid = desviador()
    cil = next(x for x in modelo(d).dispositivos if x.designacion == "-MM1")
    assert cil.servicio == {"carrera_mm": 400, "bloqueo": "-RL1"}


# ── el ERC y la memoria (D6) ─────────────────────────────────────────────────────────────────


def test_verde_con_la_faja_a_mano():
    """F0: Ø63 a 6 bar empuja p·A = 0,6 · 3117 = 1870 N; el KEC-20-S retiene 3200 (FS 1,71)."""
    d, _cid = desviador()
    (r,) = filas(d)
    assert r["estado"] == "ok" and "FS = 1.71" in r["detalle"] and "cadena de la seta (-S0:11-12)" in r["detalle"]
    assert r["calc"]["fs"] == 1.71 and r["calc"]["sustitucion"].endswith("= 1870 N")
    assert any("categoría 1, PL c, certificado IFA 1504155" in h for h in r["calc"]["hipotesis"])
    assert any("B10d: la ficha no lo publica" in h for h in r["calc"]["hipotesis"])
    (mem,) = [x for x in SN.memoria(d) if x["regla"] == "bloqueo de vástago"]
    assert mem["estado"] == "ok" and mem["valor"]["F_N"] == pytest.approx(1870.4, abs=0.5)


def test_retencion_insuficiente_es_rojo():
    """Ø32 a 8 bar: 0,8 · 804,2 = 643 N contra los 600 N del KPE-12."""
    d, _cid = desviador(ref="BLOQ-VAST-12", cilindro="CIL-ISO15552-32", presion_frl=8.0)
    rojas = [r for r in filas(d) if r["estado"] == "error"]
    ret = next(r for r in rojas if "el vástago desliza" in r["detalle"])
    assert "retiene 600 N y el cilindro empuja 643 N a 8 bar" in ret["detalle"]
    assert ret["calc"]["fs"] == pytest.approx(0.93, abs=0.005)
    assert any("SOSTENER un vástago parado" in r["detalle"] for r in rojas)   # el KPE es sólo estático


def test_ficha_solo_estatica_es_rojo():
    d, _cid = desviador(ref="BLOQ-VAST-20")
    (r,) = filas(d)
    assert r["estado"] == "error" and "SOSTENER un vástago parado" in r["detalle"]
    assert "KEC-…-S" in r["recomendacion"]


def test_la_liberacion_fuera_de_la_cadena_de_la_seta_es_aviso():
    d, _cid = desviador(mando="directo")
    (r,) = filas(d)
    assert r["estado"] == "aviso" and "sin pasar por la seta" in r["detalle"] and "-QM3" in r["elementos"]


def test_a_traves_de_un_rele_que_corta_la_seta_es_verde():
    d, _cid = desviador(mando="rele")
    (r,) = filas(d)
    assert r["estado"] == "ok" and "cadena de la seta (-K1:11-14)" in r["detalle"]


def test_sin_su_3_2_propia_es_rojo():
    d, _cid = desviador(sin_valvula=True)
    (r,) = filas(d)
    assert r["estado"] == "error" and "no a la vía 2 de una 3/2 NC" in r["detalle"]


def test_presion_de_liberacion_corta_es_rojo():
    d, _cid = desviador(presion_frl=3.0)
    (r,) = [x for x in filas(d) if x["estado"] == "error"]
    assert "le llegan 3 bar y libera desde 3.8 bar" in r["detalle"]


def test_un_bloqueo_inexistente_o_sin_cilindro():
    d, _cid = desviador(declarar=False)
    (r,) = filas(d)
    assert r["estado"] == "aviso" and "ningún cilindro lo declara" in r["detalle"]
    m = modelo(desviador()[0])
    cil = next(x for x in m.dispositivos if x.designacion == "-MM1")
    cil.servicio["bloqueo"] = "-RL2"
    rr = reglas_bloqueo(analizar(m))
    assert rr[0]["estado"] == "error" and "¿Quisiste decir «-RL1»?" in rr[0]["detalle"]


def test_el_deslizamiento_medido_es_rojo():
    m = modelo(desviador()[0])
    rr = reglas_bloqueo(analizar(m), deslizados={"-RL1": {"seta_desvio": {"t_desliza_s": 0.95,
                                                                          "sobrerrecorrido_mm": 12.5}}})
    malo = next(r for r in rr if r["estado"] == "error")
    assert "«seta_desvio» el vástago DESLIZÓ a los 0.95 s" in malo["detalle"] and "12.5 mm" in malo["detalle"]


def test_sin_bloqueo_el_erc_y_la_memoria_de_antes():
    d, _cid = desviador(bloqueo=False)
    m = modelo(d)
    assert not filas(d)
    assert erc(m) == erc(m, seta=lambda v: (False, "x"), deslizados={"-RL1": {"e": {}}})
    assert not [x for x in SN.memoria(d) if x["regla"] == "bloqueo de vástago"]


# ── el modelo de la co-simulación sin MuJoCo (D4, D5) ────────────────────────────────────────


def _bloqueo():
    aire = {**ficha_plana(CATALOG["BLOQ-VAST-20-S"].neumatico), "cilindro": "-MM1"}
    return crear_modelo_aire("-RL1", "BLOQ-VAST-20-S", aire, {})


def test_la_camara_de_liberacion_se_descarga_y_muerde_tras_el_retardo():
    m = _bloqueo()
    m.iniciar(P_ATM_PA + 6e5)
    assert not m.bloqueado and m.F == 0.0
    escape = [Camino(P_ATM_PA, (0.8, 0.3, 0.5), (0.8, 0.3, 0.5))]   # la vía 2→3 de la 3/2 en reposo
    t, mordio = 0.0, None
    for _ in range(100):
        m.intercambio(0.002, escape, 0.1, 500.0, 50.0)
        t += 0.002
        if m.bloqueado and mordio is None:
            mordio = t
    assert m.salidas()["p_bar"] < 0.01 and m.F == pytest.approx(3200, rel=1e-3)
    assert mordio is not None and mordio >= 0.010   # las mordazas: 10 ms bajo p_lib
    assert m.salidas()["desliza"] is False
    m.intercambio(0.002, escape, 0.1, 3300.0, 50.0)   # más que la retención + los sellos: desliza
    assert m.desliza is True
    with pytest.raises(Exception, match="ningún cilindro lo declara"):
        crear_modelo_aire("-RL1", "BLOQ-VAST-20-S", ficha_plana(CATALOG["BLOQ-VAST-20-S"].neumatico), {})


def test_la_recta_del_muelle_contra_el_piston():
    m = _bloqueo()
    assert m.sujecion(P_ATM_PA) == 3200 and m.sujecion(P_ATM_PA + 3.8e5) == 0.0
    assert m.sujecion(P_ATM_PA + 1.9e5) == pytest.approx(1600)


def test_el_resumen_del_escenario_guarda_el_deslizamiento():
    res = {"trazas": {"analogicas": {"t": [0, 0.02], "senales": {
        "-MM1.pA_bar": [0, 1], "-MM1.x_mm": [0, 1], "-RL1.sobrerrecorrido_mm": [0, 3.5], "-RL1.F_N": [0, 3200]}},
        "discretas": {"-RL1.desliza": [[0.0, False], [0.02, True]]}}, "final": {"-RL1.desliza": True}}
    assert resumen_aire(res)["bloqueos"] == {"-RL1": {"deslizo": True, "sobrerrecorrido_mm": 3.5,
                                                      "F_max_N": 3200.0, "t_desliza_s": 0.02}}
    sin = {"trazas": {"analogicas": {"t": [0, 0.02], "senales": {"-MM1.pA_bar": [0, 1], "-MM1.x_mm": [0, 1]}}}}
    assert "bloqueos" not in resumen_aire(sin)
