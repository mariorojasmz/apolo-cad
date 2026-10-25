"""La acometida en la co-simulación (plan datos-de-corte-y-acometida, D6–D7; F1c).

  - `Icc_kA` y `X_R` son ajustes de la red: cambian la Zk y la hipótesis deja de decir «SUPUESTA»;
  - `esquema` y `RA_ohm` son ajustes OPCIONALES de una red (también de la que no trae esquema):
    la lista de esquemas con el «TN» heredado, mayúsculas normalizadas, `RA_ohm` sólo con TT; el
    `esquema` de una ficha se valida con la misma lista; un log con «TN» regenera igual;
  - en el tablero: TN-S da la misma traza que TN; TT con RA = 100 Ω y un corto franco L → PE
    dispara el diferencial de 30 mA y no el ITM C6; IT y TT sin RA rechazan el corto a PE con su
    motivo; sin esquema, la entrada de la red es la de siempre.
"""

from __future__ import annotations

import json

import pytest
from tablero_electrico import dev

from apolo.cosim.fallas import aplicar
from apolo.cosim.modelos import crear_modelo
from apolo.cosim.red.entrada import EntradaInvalida, leer_entrada
from apolo.cosim.tablero import Tablero
from apolo.doc.document import Document, DocumentError
from apolo.library.catalog import CATALOG
from apolo.library.electrico.acometida import ESQUEMAS, esquema_de, normalizar_esquema, ra_de
from apolo.library.electrico.ajustes import OPCIONALES, validar_ajustes
from apolo.library.electrico.ficha import parse_ficha
from apolo.library.electrico.modelo import Conductor, ModeloElectrico, dispositivo_desde_ficha
from apolo.services.cosim_red import entrada_red

DT = 0.002
RED_1F, RED_3F = "RED-1F-220V-60HZ", "RED-3F-220V-60HZ"  # con esquema TN / sin esquema


def _modelo(ref: str) -> dict:
    return CATALOG[ref].electrico.modelo


# ── Icc y X/R: ya son ajustes (D6) ───────────────────────────────────────────────────────────


def test_icc_y_xr_ajustados_cambian_la_zk_y_no_dicen_supuesta():
    m = _modelo(RED_1F)
    assert validar_ajustes({"Icc_kA": 3, "X_R": 0.5}, m, RED_1F) == {"Icc_kA": 3, "X_R": 0.5}
    de_catalogo = crear_modelo("-G1", RED_1F, m)
    ajustada = crear_modelo("-G1", RED_1F, m, {"Icc_kA": 3, "X_R": 0.5})
    z = 220 / 3000 / 2  # 1F+N: el lazo U/Icc, mitad en L
    r = z / (1 + 0.5 ** 2) ** 0.5
    assert ajustada.Z == pytest.approx(complex(r, 0.5 * r))
    assert abs(ajustada.Z) == pytest.approx(2 * abs(de_catalogo.Z))  # 3 kA en vez de 6
    assert any("SUPUESTA" in h for h in de_catalogo.hipotesis)
    h = " ".join(ajustada.hipotesis)
    assert "SUPUESTA" not in h and "3 kA declarada en los ajustes" in h and "también ajustada" in h
    solo_icc = " ".join(crear_modelo("-G1", RED_1F, m, {"Icc_kA": 3}).hipotesis)
    assert "X/R = 1.5, la del catálogo" in solo_icc


# ── esquema y RA_ohm: ajustes opcionales de una red (D6) ─────────────────────────────────────


def test_el_esquema_se_normaliza_y_vale_tambien_en_la_red_que_no_lo_trae():
    assert OPCIONALES["red"].keys() == {"esquema", "RA_ohm"}
    for ref in (RED_1F, RED_3F):
        for crudo, canon in (("tn-s", "TN-S"), (" TN-C-S ", "TN-C-S"), ("it", "IT"), ("TN", "TN")):
            assert validar_ajustes({"esquema": crudo}, _modelo(ref), ref) == {"esquema": canon}
    assert validar_ajustes({"esquema": "tt", "RA_ohm": 100}, _modelo(RED_3F), RED_3F) == {
        "esquema": "TT", "RA_ohm": 100.0}
    assert esquema_de(_modelo(RED_1F), {}) == "TN" and esquema_de(_modelo(RED_1F), {"esquema": "IT"}) == "IT"
    assert esquema_de(_modelo(RED_3F), {}) is None and ra_de(_modelo(RED_3F), {}) is None


@pytest.mark.parametrize("ajustes,mensaje", [
    ({"esquema": "TNS"}, r"«TNS» no es válido; esquemas: TN-S, TN-C-S, TT, IT .*¿Quisiste decir: TN-S\?"),
    ({"esquema": "TN-C"}, r"el PE llega separado del neutro: TN-C-S"),
    ({"esquema": 3}, r"el esquema de tierra es un texto"),
    ({"RA_ohm": 100}, r"esquema es TN: declara también esquema «TT» o quita RA_ohm"),  # la ficha dice TN
    ({"esquema": "IT", "RA_ohm": 100}, r"el esquema es IT"),
    ({"esquema": "TT", "RA_ohm": 0}, r"un número > 0"),
    ({"esquema": "TT", "RA_ohm": True}, r"un número > 0"),
    ({"esquema_tierra": "TT"}, r"no tiene el ajuste «esquema_tierra».*¿Quisiste decir: esquema\?"),
])
def test_esquema_fuera_de_la_lista_y_ra_sin_tt_son_error_con_que_corregir(ajustes, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        validar_ajustes(ajustes, _modelo(RED_1F), RED_1F)


def test_ra_sin_esquema_y_el_esquema_en_otra_cosa_que_una_red():
    with pytest.raises(ValueError, match="esquema es sin declarar"):
        validar_ajustes({"RA_ohm": 50}, _modelo(RED_3F), RED_3F)
    with pytest.raises(ValueError, match="no tiene el ajuste «esquema»"):
        validar_ajustes({"esquema": "TT"}, _modelo("ITM-C6-2P"), "ITM-C6-2P")
    with pytest.raises(ValueError, match="TN-S, TN-C-S, TT, IT"):
        normalizar_esquema("TN-X")
    assert ESQUEMAS == ("TN-S", "TN-C-S", "TT", "IT")


def _ficha_red(**modelo):
    return {"funcion": "G", "simbolo": "red_1f_n", "montaje": "campo",
            "bornes": [{"id": "L", "rol": "potencia"}, {"id": "N", "rol": "potencia"}, {"id": "PE", "rol": "tierra"}],
            "fuentes": [{"polos": {"L": "L", "N": "N", "PE": "PE"}, "tension": "220 VAC 60 Hz"}],
            "modelo": {"tipo": "red", "sistema": "1F+N", "U_V": 220, "f_Hz": 60, "Icc_kA": 6, "X_R": 1.5, **modelo}}


def test_el_esquema_de_una_ficha_se_valida_con_la_misma_lista():
    assert parse_ficha(_ficha_red(esquema="tn-c-s"), "X").modelo["esquema"] == "TN-C-S"
    assert parse_ficha(_ficha_red(esquema="TN"), "X").modelo["esquema"] == "TN"  # heredado
    assert parse_ficha(_ficha_red(esquema="TT", RA_ohm=30), "X").modelo["RA_ohm"] == 30
    with pytest.raises(ValueError, match=r"modelo\.esquema: el esquema de tierra «TN-C» no es válido"):
        parse_ficha(_ficha_red(esquema="TN-C"), "X")
    with pytest.raises(ValueError, match=r"modelo\.RA_ohm: .*el esquema es TN-S"):
        parse_ficha(_ficha_red(esquema="TN-S", RA_ohm=30), "X")
    for ref, c in CATALOG.items():  # el catálogo no cambia su `modelo`: el «TN» queda «TN»
        if c.electrico is not None and c.electrico.modelo.get("tipo") == "red":
            assert c.electrico.modelo.get("esquema") in (None, "TN"), ref


def test_un_log_con_tn_heredado_o_en_minusculas_regenera_igual():
    d = Document()
    d.execute_many([dev(RED_1F, "-G1", "+RED", ajustes={"esquema": "TN"}),
                    dev(RED_3F, "-G2", "+RED", ajustes={"esquema": "tt", "RA_ohm": 80})])
    with pytest.raises(DocumentError, match="no es válido; esquemas"):
        d.execute("add_device", dev(RED_1F, "-G3", "+RED", ajustes={"esquema": "TN-C"})["params"])
    abierto = Document.from_apolo_bytes(d.to_apolo_bytes(), tolerant=True)
    assert abierto.regen_suppressed == []
    ajustes = {x.designacion: x.ajustes for x in abierto.electrico.dispositivos}
    assert ajustes == {"-G1": {"esquema": "TN"}, "-G2": {"esquema": "TT", "RA_ohm": 80.0}}
    assert [c["params"]["ajustes"] for c in abierto.commands] == [{"esquema": "TN"},
                                                                 {"esquema": "tt", "RA_ohm": 80}]


# ── la co-simulación (D7) ────────────────────────────────────────────────────────────────────


def _d(des: str, ref: str, **kw):
    return dispositivo_desde_ficha(des, ref, CATALOG[ref].electrico, ubicacion="+TAB1", **kw)


def _w(*puntos: str) -> Conductor:
    return Conductor(tuple(puntos), seccion_mm2=2.5)


def tablero(ajustes_red: dict | None = None, ref_red: str = RED_1F, ref_dif: str = "DIF-2P-25A-30MA-A",
            ref_itm: str = "ITM-C6-2P") -> Tablero:
    """La red (1F+N) con sus `ajustes` → diferencial 2P → ITM 2P → carga resistiva de 1 A."""
    m = ModeloElectrico(
        (_d("-G1", ref_red, ajustes=ajustes_red), _d("-F1", ref_dif), _d("-Q1", ref_itm)),
        (_w("-G1:L", "-F1:1"), _w("-G1:N", "-F1:N1"), _w("-F1:2", "-Q1:1"), _w("-F1:N2", "-Q1:3")))
    e = entrada_red(m)
    e["cargas"].append({"id": "carga", "tipo": "otra", "bornes": ["-Q1:2", "-Q1:4"], "modo": "impedancia",
                        "R_ohm": 220.0})
    return Tablero(e, list(m.dispositivos))


def correr(tab: Tablero, segundos: float, trazas: list | None = None) -> dict:
    for _ in range(round(segundos / DT)):
        tab.paso(DT)
        if trazas is not None:
            trazas.append(json.dumps(tab.senales(), sort_keys=True, default=str))
    return tab.senales()


def _red(tab: Tablero) -> dict:
    return next(f for f in tab.entrada["fuentes"] if f["dispositivo"] == "-G1")


def test_tn_s_y_tn_c_s_dan_la_misma_traza_que_tn():
    trazas = {}
    for esquema in (None, "TN-S", "tn-c-s"):
        tab = tablero({"esquema": esquema} if esquema else None)
        t: list = []
        correr(tab, 0.02, t)
        aplicar(tab, {"falla": "corto", "a": "-Q1:2", "b": "-G1:PE", "R_ohm": 1000.0})
        s = correr(tab, 0.1, t)
        assert s["-F1.disparado"] and not s["-Q1.disparado"], esquema
        assert _red(tab)["pe_a_neutro"] is True and "R_tierra_ohm" not in _red(tab)
        trazas[esquema] = t
    assert trazas[None] == trazas["TN-S"] == trazas["tn-c-s"]


def test_tt_con_ra_100_y_un_corto_franco_l_a_pe_dispara_el_diferencial_y_no_el_itm_c6():
    tab = tablero({"esquema": "TT", "RA_ohm": 100})
    red = _red(tab)
    assert (red["pe_a_neutro"], red["esquema"], red["R_tierra_ohm"]) == (False, "TT", 100.0)
    assert any("RA de la instalación + RB" in h and "optimista" in h for h in tab.hipotesis)
    s = correr(tab, 0.1)
    assert s["-F1.cerrado"] and s["-F1.I_residual_mA"] < 0.1  # sana: 1 A que vuelve por el N
    aplicar(tab, {"falla": "corto", "a": "-Q1:2", "b": "-G1:PE"})  # franco (1 mΩ)
    tab.paso(DT)
    residual = tab.modelos["-F1"].salidas()["I_residual_mA"]
    assert residual == pytest.approx(2200.0, rel=0.02)  # 220 V / 100 Ω: la limita el lazo, no la red
    s = correr(tab, 0.1)
    assert s["-F1.disparado"] and s["-F1.causa"] == "diferencial"
    assert not s["-Q1.disparado"] and s["-Q1.cerrado"]  # 3,2 A no mueven un C6


def test_tt_en_la_red_sin_esquema_de_catalogo():
    m = ModeloElectrico((_d("-G1", RED_3F, ajustes={"esquema": "TT", "RA_ohm": 50}),), ())
    e = entrada_red(m)
    assert e["fuentes"][0]["R_tierra_ohm"] == 50.0 and leer_entrada(e).fuentes[0].R_tierra_ohm == 50.0
    tab = Tablero(e, list(m.dispositivos))
    assert "-G1:PE" in tab.pot_red.dom.puntos and tab.pot_red.dom.puntos["-G1:PE"] >= 0  # nodo, no tierra
    aplicar(tab, {"falla": "corto", "a": "-G1:L1", "b": "-G1:PE"})
    tab.paso(DT)
    v_pe = abs(tab.pot.U("-G1:PE"))
    assert v_pe == pytest.approx(220 / 3 ** 0.5, rel=0.02)  # el PE sube a la fase: 2,5 A por 50 Ω


@pytest.mark.parametrize("ajustes,motivo", [
    ({"esquema": "IT"}, "en IT el primer defecto a masa no da corriente de falla"),
    ({"esquema": "TT"}, r"en TT declara RA_ohm"),
])
def test_it_y_tt_sin_ra_rechazan_el_corto_a_pe_con_su_motivo(ajustes, motivo):
    tab = tablero(ajustes)
    assert _red(tab)["pe_a_neutro"] is False and "R_tierra_ohm" not in _red(tab)
    for a, b in (("-Q1:2", "-G1:PE"), ("-G1:PE", "-F1:1")):
        with pytest.raises(ValueError, match=f"«-G1:PE» no es un punto de las redes: .*{motivo}"):
            aplicar(tab, {"falla": "corto", "a": a, "b": b})
    s = correr(tab, 0.05)
    assert s["-F1.cerrado"] and s["-Q1.cerrado"]  # el corto no entró


def test_tt_sin_ra_avisa_en_la_entrada():
    e = entrada_red(ModeloElectrico((_d("-G1", RED_1F, ajustes={"esquema": "TT"}),), ()))
    assert any("red TT sin RA_ohm" in a for a in e["avisos"])


def test_sin_esquema_la_entrada_de_la_red_es_la_de_siempre():
    e = entrada_red(ModeloElectrico((_d("-G1", RED_3F),), ()))
    assert set(e["fuentes"][0]) == {"id", "tipo", "polos", "U_V", "dispositivo", "ideal", "sistema",
                                    "pe_a_neutro", "f_Hz"}
    assert e["fuentes"][0]["pe_a_neutro"] is False and not e["avisos"]
    with pytest.raises(ValueError, match=r"«-G1:PE» no es un punto de las redes \(un PE sólo entra"):
        aplicar(Tablero(e, []), {"falla": "corto", "a": "-G1:L1", "b": "-G1:PE"})


def test_el_formato_plano_valida_el_lazo_de_tierra():
    f = {"id": "-G1", "tipo": "AC", "sistema": "1F+N", "U_V": 220, "ideal": False,
         "polos": {"-G1:L": "L", "-G1:N": "N", "-G1:PE": "PE"}}
    e = leer_entrada({"fuentes": [{**f, "esquema": "TT", "R_tierra_ohm": 10}]})
    assert leer_entrada(json.loads(json.dumps(e.como_dict()))) == e
    for mal, msg in (({"R_tierra_ohm": 10, "pe_a_neutro": True}, "sin «pe_a_neutro»"),
                     ({"R_tierra_ohm": -1}, "debe ser > 0"), ({"esquema": 1}, "es un texto")):
        with pytest.raises(EntradaInvalida, match=msg):
            leer_entrada({"fuentes": [{**f, **mal}]})
