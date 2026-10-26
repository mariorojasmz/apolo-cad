"""Cifras de fichas oficiales y líneas de referencia corregidas (2026-10-26; bitácoras «Cifras de
fichas y líneas corregidas» de los planes datos-de-corte-y-acometida y mandos-de-seguridad).

Cada ref tocada carga con sus cifras y la `fuente` nombra la ficha de donde salen; lo que una cifra
resolvió ya no está en `a_confirmar`. Las líneas citadas son las que CUMPLEN la ref (una ref es un
ejemplo: `library/CLAUDE.md` § Catálogo): la seta de 1 NC no cita una de 1 NC + 1 NA, el variador
trifásico con STO no cita uno monofásico sin STO.
"""

from __future__ import annotations

import pytest

from apolo.library import CATALOG


def _f(ref):
    return CATALOG[ref].electrico


#: ref → (datos esperados, lo que la fuente tiene que nombrar)
ITM = {
    "ITM-C6-3P": ({240: 20.0, 415: 10.0}, {240: 15.0, 415: 7.5}, "A9F74306"),
    "ITM-C16-3P": ({240: 20.0, 415: 10.0}, {240: 15.0, 415: 7.5}, "A9F74316"),
    "ITM-C20-3P": ({240: 20.0, 415: 10.0}, {240: 15.0, 415: 7.5}, "A9F74320"),
    "ITM-C2-1PN": ({240: 50.0}, {240: 50.0}, "A9F74602"),
    "ITM-C6-1PN": ({240: 10.0}, {240: 7.5}, "A9F74606"),
}
DIF = {
    "DIF-2P-25A-30MA-A": ("A9R21225", 63, "50/60 Hz"),
    "DIF-2P-25A-300MA-A": ("A9R24225", 63, "50/60 Hz"),
    "DIF-2P-25A-30MA-B": ("A9Z61225", 63, "50 Hz"),
    "DIF-2P-25A-300MA-B": ("A9Z64225", 63, "50 Hz"),
    "DIF-4P-40A-30MA-A": ("A9R21440", 80, "50/60 Hz"),
    "DIF-4P-40A-300MA-A": ("A9R24440", 80, "50/60 Hz"),
    "DIF-4P-40A-30MA-B": ("A9Z61440", 80, "50 Hz"),
    "DIF-4P-40A-300MA-B": ("A9Z64440", 80, "50 Hz"),
}
T_MAX = {
    "GM-AUX-1NA1NC": (60, "3RV2901-1E"),
    "RELE-INT-24VDC": (70, "S38EN"),
    "RELE-INT-230V": (55, "S38EN"),
    "RS-2C-24VDC": (60, "3SK1111-1AB30"),
    "PLC-14DI-10DO-24VDC": (55, "6ES7214-1AG40-0XB0"),
    "VFD-1K5-220": (50, "MS300"),
    "VFD-2K2-220": (50, "MS300"),
    "BORNE-PASO-2.5": (105, "8WH1000-0AF00"),
    "BORNE-PASO-4": (105, "8WH1000-0AG00"),
    "BORNE-PE-2.5": (105, "8WH1000-0CF07"),
    "BORNE-PE-4": (105, "8WH1000-0CG07"),
    "BORNE-FUS-5X20": (105, "8WH1000-1GG08"),
    "COND-H05VK-0.75": (60, "IEC 60364-5-52"),
    "COND-H05VK-1": (60, "IEC 60364-5-52"),
    "COND-H07VK-1.5": (60, "IEC 60364-5-52"),
    "COND-H07VK-2.5": (60, "IEC 60364-5-52"),
    "COND-H07VK-4": (60, "IEC 60364-5-52"),
}


@pytest.mark.parametrize("ref", list(ITM))
def test_los_itm_traen_su_poder_de_corte_de_ficha(ref):
    icu, ics, ficha = ITM[ref]
    f = _f(ref)
    assert (f.datos["Icu_kA"], f.datos["Ics_kA"], f.datos["T_max_C"]) == (icu, ics, 70.0)
    assert f.a_confirmar == () and ficha in f.fuente and "download.se.com" in f.fuente


@pytest.mark.parametrize("ref", list(DIF))
def test_los_diferenciales_traen_inc_im_y_temperatura(ref):
    ficha, fusible, frecuencia = DIF[ref]
    f = _f(ref)
    assert {k: f.datos[k] for k in ("Inc_kA", "Im_A", "T_max_C")} == {"Inc_kA": 10.0, "Im_A": 1500.0, "T_max_C": 60.0}
    assert f"fusible gG de {fusible} A" in f.datos["Inc_con"] and "iC60N" in f.datos["Inc_con"]
    assert f.a_confirmar == () and ficha in f.fuente and "CA909006" in f.fuente
    specs = CATALOG[ref].specs
    assert specs["frecuencia_ficha"] == frecuencia
    # D-a: la clase B de la ficha es de 50 Hz; «apto a 60 Hz» queda a confirmar, nunca afirmado
    assert ("60 Hz" in specs.get("a_confirmar", "")) == (frecuencia == "50 Hz")


@pytest.mark.parametrize("ref", list(T_MAX))
def test_la_temperatura_sale_de_su_ficha_o_del_tipico_de_norma(ref):
    t, ficha = T_MAX[ref]
    f = _f(ref)
    assert f.datos["T_max_C"] == t and "T_max_C" not in f.a_confirmar and ficha in f.fuente
    if ref.startswith("COND-"):
        assert f.fuente.startswith("T_max_C típico de IEC 60364-5-52") and "no de la ficha" in f.fuente


def test_el_portafusible_trae_el_cartucho_y_anota_la_errata():
    f = _f("BORNE-FUS-5X20")
    assert {k: f.datos[k] for k in ("cartucho_U_V", "cartucho_Icn_A", "cartucho_Icn_x_In")} == {
        "cartucho_U_V": 250.0, "cartucho_Icn_A": 35.0, "cartucho_Icn_x_In": 10.0}
    assert f.a_confirmar == () and "Schurter" in f.fuente and "errata" in f.fuente


@pytest.mark.parametrize("ref, ficha", [("FUENTE-24VDC-2.5A", "HDR-60"), ("FUENTE-24VDC-5A", "EDR-120")])
def test_las_fuentes_dejan_la_temperatura_a_plena_carga_a_confirmar(ref, ficha):
    """D-b: la ficha Mean Well sólo da el tope CON desclasificación; la plena carga está en la curva."""
    f = _f(ref)
    assert "T_max_C" not in f.datos and f.a_confirmar == ("T_max_C",)
    assert ficha in f.fuente and "desclasificación" in f.fuente


# ── líneas de referencia corregidas ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("ref, si, no", [
    ("ESTOP-40", "XB5AS8442 (1 NC)", "XB5AS8445"),
    ("ESTOP-40-CAJA", "XB5AS8442 (1 NC)", "XB5AS8445"),
    ("ESTOP-40-2NC", "XB5AS8444 (2 NC)", "XB5AS8442"),
    ("ESTOP-40-CAJA-2NC", "XB5AS8444 (2 NC)", "XB5AS8442"),
    ("RESG-2NC", "XCSPA792 (2 NC", "XCSPA592"),
    ("RS-2C-24VDC", "3SK1111-1AB30", "XPSAC5121"),
    ("GM-AUX-1NA1NC", "GVAE11", "GVAN11"),
    ("VFD-1K5-220", "VFD7A5MS23ANSAA", "V20"),
    ("VFD-2K2-220", "VFD11AMS23ANSAA", "V20"),
])
def test_la_linea_citada_cumple_la_ref(ref, si, no):
    linea = CATALOG[ref].specs["linea_referencia"]
    assert linea.startswith("orden de ") and si in linea and no not in linea, linea


def test_el_rele_de_seguridad_cita_una_linea_con_rearme_vigilado():
    c = CATALOG["RS-2C-24VDC"]
    assert c.specs["rearme"] == c.electrico.modelo["rearme"] == "vigilado"
    assert "PNOZ" not in c.specs["linea_referencia"] and "monitored start-up Yes" in c.electrico.fuente


@pytest.mark.parametrize("ref, i_hd", [("VFD-1K5-220", 7.5), ("VFD-2K2-220", 11.0)])
def test_el_variador_es_trifasico_con_sto_y_su_corriente_es_la_de_la_ficha(ref, i_hd):
    c = CATALOG[ref]
    m = c.electrico.modelo
    assert m["I_salida_A"] == c.specs["corriente_A"] == i_hd  # servicio pesado: 150 % / 60 s
    assert (m["sobrecarga_pct"], m["sobrecarga_s"], m["STO"]) == (150, 60, True)
    assert c.specs["tension"] == "220V 3F" and "STO integrado" in c.specs["linea_referencia"]
    # la corriente de entrada no está en el catálogo leído: estimada, a confirmar
    assert c.electrico.a_confirmar == ("I_entrada_A",) and "I_entrada_A" in m
