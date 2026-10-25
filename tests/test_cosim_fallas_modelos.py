"""Las fallas de cada modelo de dispositivo (plan cosim-fallas D1, D2): cada una con su gemelo SIN
falla (las mismas entradas dan lo de siempre) y la falla con su efecto; `averia` aparece sólo en
el que falló. Con el catálogo real y el intercambio de 2 ms."""

from __future__ import annotations

import pytest

from apolo.cosim.modelos import MODELOS, crear_modelo
from apolo.cosim.modelos.base import PIDE
from apolo.library.catalog import CATALOG

DT = 0.002


def modelo(ref: str, des: str = "-X1", cantidad: int = 1, **ajustes):
    return crear_modelo(des, ref, CATALOG[ref].electrico.modelo, ajustes, cantidad=cantidad)


def gemelos(ref: str, **kw):
    return modelo(ref, **kw), modelo(ref, **kw)


def correr(m, segundos: float, entradas: dict) -> dict:
    out = {}
    for _ in range(round(segundos / DT)):
        out = m.paso(DT, entradas)
    return out


# ── la base: declarar, rechazar, publicar ────────────────────────────────────────────────────


def test_cada_tipo_declara_sus_fallas_con_lo_que_piden():
    con = {t for t, c in MODELOS.items() if c.FALLAS}
    assert con == set(MODELOS) - {"red", "motor"}  # D2: la red y el motor, ninguna nueva
    for t, c in MODELOS.items():
        for nombre, pide in c.FALLAS.items():
            assert pide in PIDE, (t, nombre, pide)
            assert hasattr(c, f"_falla_{nombre}") and hasattr(c, f"_reparar_{nombre}"), (t, nombre)


def test_una_falla_que_el_modelo_no_toma_dice_cuales_si():
    k = modelo("CONT-9A-24VDC", "-K1")
    with pytest.raises(ValueError, match="no admite la falla «trabado»; fallas: soldado, no_cierra"):
        k.fallar("trabado")
    with pytest.raises(ValueError, match="fallas: \\(ninguna\\)"):
        modelo("MOTOR-075", "-M1", conexion="triangulo").fallar("soldado")


def test_sin_falla_no_hay_averia_y_con_falla_la_publica_hasta_repararla():
    k = modelo("CONT-9A-24VDC", "-K1")
    assert k.publicadas() == k.salidas() and "-K1.averia" not in k.senales()
    k.fallar("soldado")
    assert k.senales()["-K1.averia"] == "soldado"
    k.reparar("soldado")
    assert k.senales()["-K1.averia"] == ""  # una vez que falló, «» al quedar sana


# ── contactor y relé ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ref", ["CONT-9A-24VDC", "CONT-9A-220VAC", "RELE-INT-24VDC"])
def test_contactor_soldado_sigue_cerrado_sin_bobina(ref):
    uc = CATALOG[ref].electrico.modelo["Uc_V"]
    sano, malo = gemelos(ref)
    for m in (sano, malo):
        assert correr(m, 0.2, {"U_bobina_V": uc})["cerrado"]
    malo.fallar("soldado")
    assert not correr(sano, 0.2, {"U_bobina_V": 0.0})["cerrado"]
    s = correr(malo, 0.2, {"U_bobina_V": 0.0})
    assert s["cerrado"] and s["estado"] == "cerrado"
    malo.reparar("soldado")  # reparado, abre solo si la bobina ya no está
    assert not correr(malo, 0.2, {"U_bobina_V": 0.0})["cerrado"]


def test_contactor_soldado_puesto_abierto_queda_cerrado_en_el_acto():
    k = modelo("CONT-9A-24VDC")
    k.fallar("soldado")
    assert k.cerrado and k.salidas()["cerrado"]


@pytest.mark.parametrize("ref", ["CONT-9A-24VDC", "CONT-9A-220VAC"])
def test_contactor_que_no_cierra_no_cierra_ni_consume(ref):
    uc = CATALOG[ref].electrico.modelo["Uc_V"]
    sano, malo = gemelos(ref)
    malo.fallar("no_cierra")
    assert malo.abre_su_carga and not sano.abre_su_carga
    s_sano, s_malo = correr(sano, 0.2, {"U_bobina_V": uc}), correr(malo, 0.2, {"U_bobina_V": uc})
    assert s_sano["cerrado"] and s_sano["I_bobina_A"] > 0
    assert not s_malo["cerrado"] and s_malo["I_bobina_A"] == 0.0 and s_malo["estado"] == "abierto"
    sano.fallar("no_cierra")  # cerrado: la bobina se corta y abre
    assert not correr(sano, 0.2, {"U_bobina_V": uc})["cerrado"]


# ── mandos ───────────────────────────────────────────────────────────────────────────────────


def test_seta_trabada_no_se_retiene():
    sano, malo = gemelos("ESTOP-40")
    malo.fallar("trabado")
    for m in (sano, malo):
        m.accionar("presionar")
    assert sano.actuadores() == {"mano": True}
    assert malo.actuadores() == {"mano": False} and malo.senales()["-X1.averia"] == "trabado"
    malo.reparar("trabado")
    malo.accionar("presionar")
    assert malo.actuadores() == {"mano": True}


def test_seta_trabada_en_una_posicion_y_una_accion_que_no_existe_sigue_siendo_error():
    s = modelo("ESTOP-40")
    s.fallar("trabado", True)
    s.accionar("liberar")
    assert s.actuadores() == {"mano": True}  # trabada presionada: no se libera
    with pytest.raises(ValueError, match="no admite «pulsar»"):
        s.accionar("pulsar")
    with pytest.raises(ValueError, match="true o false"):
        s.fallar("trabado", "sí")


def test_pulsador_trabado_no_vuelve_por_resorte_ni_cambia():
    sano, malo = gemelos("PULS-22-VERDE-NA")
    for m in (sano, malo):
        m.accionar("pulsar", {"actuador": None, "durante_s": 0.1})
    malo.fallar("trabado")
    assert not correr(sano, 0.2, {})["accionado"]
    assert correr(malo, 0.2, {})["accionado"]  # quedó apretado
    b = modelo("BOTONERA-2")
    b.fallar("trabado", {"marcha": True})
    b.accionar("girar", 0.7)  # el potenciómetro no lo alcanza la traba
    assert b.actuadores()["marcha"] and b.potenciometro == 0.7
    with pytest.raises(ValueError, match="no tiene el actuador «arranque»"):
        b.fallar("trabado", {"arranque": True})


def test_selector_trabado_en_su_posicion_y_seccionador_trabado():
    sano, malo = gemelos("SEL-22-3POS-2NA")
    pos = malo.posiciones
    malo.fallar("trabado", pos[-1])
    for m in (sano, malo):
        m.accionar("girar", pos[0])
    assert sano.posicion == pos[0] and malo.posicion == pos[-1]
    with pytest.raises(ValueError, match="no es una posición"):
        modelo("SEL-22-3POS-2NA").fallar("trabado", "Z")
    q = modelo("SECC-25A-3P")
    q.fallar("trabado")
    q.accionar("abrir")
    assert q.salidas()["cerrado"] and q.actuadores() == {"mano": True}  # no abre


# ── piloto, sensor y fuente ──────────────────────────────────────────────────────────────────


def test_piloto_fundido_no_enciende_ni_consume():
    sano, malo = gemelos("PILOTO-24V-VERDE")
    malo.fallar("fundido")
    assert sano.paso(DT, {"U_V": 24.0})["encendido"] and sano.I_A > 0
    s = malo.paso(DT, {"U_V": 24.0})
    assert not s["encendido"] and s["I_A"] == 0 and malo.abre_su_carga


def test_sensor_pegado_y_sin_salida():
    ok = {"detecta": False, "U_alim_V": 24.0}
    sano, pegado = gemelos("FOTO-M18")
    pegado.fallar("pegado", True)
    assert not correr(sano, 0.1, ok)["activo"] and correr(pegado, 0.1, ok)["activo"]
    pegado.reparar("pegado")
    assert not correr(pegado, 0.1, ok)["activo"]
    with pytest.raises(ValueError, match="true o false"):
        pegado.fallar("pegado")
    sano, muda = gemelos("FOTO-M18")
    muda.fallar("sin_salida")
    ve = {**ok, "detecta": True}
    assert correr(sano, 0.1, ve)["activo"] and not correr(muda, 0.1, ve)["activo"]


def test_fuente_sin_salida_cae_a_cero_con_la_entrada_bien():
    sano, malo = gemelos("FUENTE-24VDC-5A")
    e = {"U_entrada_V": 220.0, "I_carga_A": 1.0}
    malo.fallar("sin_salida")
    assert sano.paso(DT, e)["U_V"] == pytest.approx(24.0) and sano.ok
    s = malo.paso(DT, e)
    assert s["U_V"] == 0.0 and not s["ok"]


# ── protecciones ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ref,aj,I,t", [("GM-2.5-4A", {"Ir_A": 3.2}, 200.0, 0.1),
                                        ("ITM-C16-3P", {}, 300.0, 0.1), ("RT-2.5-4A", {"Ir_A": 3.2}, 30.0, 10.0)])
def test_proteccion_que_no_dispara(ref, aj, I, t):
    sano, malo = gemelos(ref, **aj)
    malo.fallar("no_dispara")
    assert correr(sano, t, {"I_A": I})["disparado"]
    s = correr(malo, t, {"I_A": I})
    assert not s["disparado"] and s["termico_pct"] > 50  # el bimetal calentó igual


def test_diferencial_que_no_dispara_mide_la_residual_igual():
    sano, malo = gemelos("DIF-2P-25A-30MA-A")
    malo.fallar("no_dispara")
    fuga = {"I_fasores": [complex(1.0, 0.2), complex(-0.95, -0.2)]}  # 50 mA que no vuelven
    assert correr(sano, 0.2, fuga)["disparado"]
    s = correr(malo, 0.2, fuga)
    assert not s["disparado"] and s["cerrado"] and s["I_residual_mA"] == pytest.approx(50.0)
    assert malo.senales()["-X1.averia"] == "no_dispara" and "-X1.averia" not in sano.senales()


def test_diferencial_abierto_solo_no_rearma_mientras_dura():
    sano, malo = gemelos("DIF-4P-40A-30MA-B")
    malo.fallar("abierto")
    assert sano.salidas()["cerrado"] and correr(sano, 0.1, {"I_fasores": [1.0, -1.0]})["cerrado"]
    s = malo.salidas()
    assert not s["cerrado"] and s["disparado"] and s["causa"] == "avería"
    malo.accionar("rearmar")
    assert malo.salidas()["disparado"]
    malo.reparar("abierto")
    assert malo.salidas()["disparado"]  # reparado, sigue disparado hasta que lo rearmen
    malo.accionar("rearmar")
    assert malo.salidas()["cerrado"]


def test_proteccion_abierta_sola_no_rearma_mientras_dura():
    sano, malo = gemelos("GM-2.5-4A", Ir_A=3.2)
    malo.fallar("abierto")
    assert sano.salidas()["cerrado"]
    s = malo.salidas()
    assert not s["cerrado"] and s["disparado"] and s["causa"] == "avería"
    malo.accionar("rearmar")
    assert malo.salidas()["disparado"]
    malo.reparar("abierto")
    assert malo.salidas()["disparado"]  # reparada, sigue disparada hasta que la rearmen
    malo.accionar("rearmar")
    assert malo.salidas()["cerrado"]


def test_fusible_que_funde_solo_por_unidad_y_que_no_funde():
    sano, malo = gemelos("BORNE-FUS-5X20", cantidad=2, cartucho_In_A=1.0)
    malo.fallar("abierto", 2)
    assert not sano.salidas()["disparado"]
    s = malo.senales()
    assert s["-X1.2.disparado"] and not s["-X1.1.disparado"] and s["-X1.averia"] == "abierto 2"
    malo.accionar("reponer", 2)
    assert malo.salidas()["2.disparado"]  # no se repone mientras dura
    malo.reparar("abierto", 2)
    malo.accionar("reponer", 2)
    assert not malo.salidas()["disparado"] and malo.averia == ""
    with pytest.raises(ValueError, match="la unidad va de 1 a 2"):
        malo.fallar("abierto", 3)
    sano, malo = gemelos("BORNE-FUS-5X20", cartucho_In_A=1.0)
    malo.fallar("no_dispara")
    assert correr(sano, 0.5, {"I_A": 10.0})["disparado"] and not correr(malo, 0.5, {"I_A": 10.0})["disparado"]


# ── PLC (E/S) ────────────────────────────────────────────────────────────────────────────────


def test_plc_entrada_y_salida_pegadas_y_detenido():
    base = {"L+": 24.0, "I0.0": 0.0, "salidas": {"Q0.0": True, "Q0.1": False}}
    sano, malo = gemelos("PLC-14DI-10DO-24VDC")
    malo.fallar("entrada_pegada", {"borne": "I0.0", "valor": True})
    malo.fallar("salida_pegada", {"borne": "Q0.1"})  # sin valor: queda conduciendo
    malo.fallar("entrada_pegada", {"borne": "AI0", "valor": 13824})
    a, b = correr(sano, 0.1, base), correr(malo, 0.1, base)
    assert not a["%IX0.0"] and b["%IX0.0"]
    assert not a["%QX0.1"] and b["%QX0.1"] and a["%QX0.0"] and b["%QX0.0"]
    assert a["%IW0"] == 0 and b["%IW0"] == 13824
    assert malo.averia == "entrada_pegada I0.0, salida_pegada Q0.1, entrada_pegada AI0"
    malo.reparar("entrada_pegada", {"borne": "I0.0"})
    assert not correr(malo, 0.1, base)["%IX0.0"] and malo.averia == "salida_pegada Q0.1, entrada_pegada AI0"
    with pytest.raises(ValueError, match="«Q0.9» no es un borne de salida"):
        malo.fallar("salida_pegada", {"borne": "Q0.9"})
    with pytest.raises(ValueError, match="pide \\{borne, valor\\}"):
        malo.fallar("entrada_pegada", True)
    sano.fallar("detenido")
    assert not correr(sano, 0.1, base)["%QX0.0"]  # la CPU detenida: las salidas caen
    sano.reparar("detenido")
    assert sano.reanudar and correr(sano, 0.1, base)["%QX0.0"]


# ── variador ─────────────────────────────────────────────────────────────────────────────────

RED = {"U_red_V": [220.0, 220.0, 220.0]}
MARCHA = {**RED, "S1": 24.0, "S2": 24.0, "DI1": 24.0, "AI1": 10.0}


def test_variador_con_un_canal_del_sto_pegado_sigue_con_par_si_corta_solo_ese():
    sano, malo = gemelos("VFD-2K2-220")
    for v in (sano, malo):
        correr(v, 2, MARCHA)
    malo.fallar("canal_sto_pegado", "S1")
    corta_s1 = {**MARCHA, "S1": 0.0}
    assert correr(sano, 0.05, corta_s1)["sto"]
    s = correr(malo, 0.05, corta_s1)
    assert not s["sto"] and s["par_habilitado"]  # el canal pegado lee 24 V sin tenerlos
    assert correr(malo, 0.05, {**MARCHA, "S1": 0.0, "S2": 0.0})["sto"]  # el otro canal sí corta
    assert any("discrepancia" in h for h in malo.hipotesis)  # D10: no se inventa
    with pytest.raises(ValueError, match="S1 o S2"):
        malo.fallar("canal_sto_pegado", {"canal": "S3"})


def test_variador_con_falla_interna_no_se_rearma_mientras_dura():
    sano, malo = gemelos("VFD-2K2-220")
    malo.fallar("falla_interna")
    assert correr(sano, 2, MARCHA)["f_Hz"] > 0
    s = correr(malo, 2, MARCHA)
    assert s["falla"] == "interna" and s["f_Hz"] == 0 and s["rele_falla"]
    malo.accionar("rearmar")
    assert correr(malo, 0.1, MARCHA)["falla"] == "interna"
    malo.reparar("falla_interna")
    malo.accionar("rearmar")
    assert correr(malo, 0.1, MARCHA)["falla"] == ""


# ── electroválvula (V8.9 F3, D8) ─────────────────────────────────────────────────────────────


def _valvula(ref: str):
    from apolo.services.cosim_aire import ficha_plana

    c = CATALOG[ref]
    return crear_modelo("-QM1", ref, {**c.electrico.modelo, "aire": ficha_plana(c.neumatico)})


def test_valvula_pegada_no_se_mueve_y_su_gemela_si():
    sano, malo = _valvula("VAL-52-MONO-G18"), _valvula("VAL-52-MONO-G18")
    assert malo.FALLAS == {"pegada": "posicion?", "bobina_cortada": ""}  # una bobina: nada que elegir
    assert malo.fallar("pegada") == "pegada 12"
    assert correr(sano, 0.05, {"U_14": 24.0})["posicion"] == "14"
    correr(malo, 0.05, {"U_14": 24.0})
    assert malo.publicadas() == {"posicion": "12", "bobina14": True, "manual": "0", "averia": "pegada 12"}
    malo.reparar("pegada")
    assert correr(malo, 0.05, {"U_14": 24.0})["posicion"] == "14" and malo.averia == ""
    with pytest.raises(ValueError, match="14, 12"):
        malo.fallar("pegada", "0")


def test_bobina_cortada_no_conmuta_ni_consume_y_su_gemela_si():
    sano, malo = _valvula("VAL-52-BI-G18"), _valvula("VAL-52-BI-G18")
    assert malo.FALLAS["bobina_cortada"] == "canal"
    malo.fallar("bobina_cortada", "14")
    assert malo.abre_bobina("14") and not malo.abre_bobina("12") and not sano.abre_bobina("14")
    assert correr(sano, 0.05, {"U_14": 24.0})["posicion"] == "14"
    s = correr(malo, 0.05, {"U_14": 24.0})
    assert s["posicion"] == "12" and s["bobina14"] is False
    assert correr(malo, 0.05, {"U_12": 24.0})["posicion"] == "12"   # la 12 sigue sana
    with pytest.raises(ValueError, match="pide la bobina"):
        malo.fallar("bobina_cortada")
    malo.reparar("bobina_cortada", "14")
    assert correr(malo, 0.05, {"U_14": 24.0})["posicion"] == "14"