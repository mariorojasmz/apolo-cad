"""El interruptor diferencial (plan datos-de-corte-y-acometida, D8–D10; F1b).

  - el modelo solo: no dispara a ½ IΔn, dispara dentro de las bandas de IEC 61008-1 a IΔn, 2 IΔn y
    5 IΔn, el contador vuelve a cero si la residual baja, rearmar con la falla presente vuelve a
    disparar, `abrir`/`cerrar`;
  - en el tablero: en una red 1F+N TN un corto de 1 kΩ de la fase aguas abajo a PE dispara el de
    30 mA y no el ITM C2, y el de 300 mA no dispara; una carga 3F+N equilibrada (o no) tras un 4P
    no dispara, y un corto a PE sí; los fasores llegan con su signo (de LÍNEA a CARGA);
  - el catálogo: las 8 refs, `de` = lado línea en todo camino `proteccion` de un diferencial, y
    `clase_residual` validada;
  - la regla del ERC «tipo de diferencial» (D10), verde y roja.
"""

from __future__ import annotations

import pytest

from apolo.cosim.fallas import aplicar
from apolo.cosim.modelos import ModeloIncompleto, crear_modelo
from apolo.cosim.modelos.diferencial import BANDAS_S, K, t_disparo
from apolo.cosim.tablero import Tablero
from apolo.library.catalog import CATALOG
from apolo.library.electrico.erc import erc
from apolo.library.electrico.ficha import parse_ficha
from apolo.library.electrico.modelo import Conductor, ModeloElectrico, dispositivo_desde_ficha
from apolo.services.cosim_red import entrada_red

DT = 0.002
#: La residual de un aparato SANO no es cero exacto: la conductancia mínima de cada nodo de la red
#: (0,1 µS a tierra, `cosim/red/mna.py`) deja ~22 µA por nodo a 220 V; lejos de 15 mA (½ IΔn).
PISO_mA = 0.1
DIFERENCIALES = sorted(r for r, c in CATALOG.items()
                       if c.electrico is not None and c.electrico.modelo.get("tipo") == "diferencial")


def dif(ref: str = "DIF-2P-25A-30MA-A", des: str = "-F1"):
    return crear_modelo(des, ref, CATALOG[ref].electrico.modelo)


def hasta_disparo(m, fasores, tope_s: float = 1.0) -> float | None:
    """Segundos hasta que dispara con esos fasores constantes (None si no dispara en `tope_s`)."""
    for k in range(1, round(tope_s / DT) + 1):
        if m.paso(DT, {"I_fasores": fasores})["disparado"]:
            return k * DT
    return None


# ── el modelo ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("x,tope", BANDAS_S)
def test_dispara_dentro_de_la_banda_de_la_norma(x, tope):
    m = dif()
    fuga = x * m.IDn
    t = hasta_disparo(m, [complex(2.0 + fuga, 0.0), complex(-2.0, 0.0)])  # la carga vuelve, la fuga no
    assert t is not None and 0 < t <= tope
    s = m.salidas()
    assert s["disparado"] and not s["cerrado"] and s["causa"] == "diferencial"


def test_no_dispara_a_medio_idn_ni_bajo_el_umbral():
    for x in (0.5, K - 0.01):
        m = dif()
        assert hasta_disparo(m, [x * m.IDn, 0.0], tope_s=2.0) is None
        assert m.salidas()["I_residual_mA"] == pytest.approx(x * 30.0)
    m = dif()
    assert hasta_disparo(m, [K * m.IDn, 0.0]) == pytest.approx(t_disparo(K))  # en el umbral, sí


def test_tiempos_en_el_medio_de_cada_banda_y_deterministas():
    assert (t_disparo(1.0), t_disparo(1.99), t_disparo(2.0), t_disparo(5.0), t_disparo(40.0)) == (
        0.15, 0.15, 0.075, 0.02, 0.02)
    assert t_disparo(0.5) is None
    assert hasta_disparo(dif(), [0.2, 0.0]) == hasta_disparo(dif(), [0.2, 0.0]) == pytest.approx(0.02)


def test_si_la_residual_baja_el_contador_vuelve_a_cero():
    m = dif()
    for _ in range(round(0.1 / DT)):          # 100 ms de 30 mA (dispararía a los 150)
        m.paso(DT, {"I_fasores": [0.030]})
    m.paso(DT, {"I_fasores": [0.0]})          # un paso sin fuga
    assert hasta_disparo(m, [0.030], tope_s=0.148) is None  # vuelve a contar desde cero
    assert hasta_disparo(m, [0.030], tope_s=0.004) is not None  # y a los 150 ms dispara


def test_rearmar_con_la_falla_presente_vuelve_a_disparar_y_abrir_cerrar():
    m = dif()
    assert hasta_disparo(m, [0.2]) == pytest.approx(0.02)
    assert m.paso(DT, {"I_fasores": [0.2]})["I_residual_mA"] == 0.0  # abierto: no ve nada
    m.accionar("rearmar")
    assert m.salidas()["cerrado"] and m.salidas()["causa"] == ""
    assert hasta_disparo(m, [0.2]) == pytest.approx(0.02)  # disparo libre: vuelve a abrir
    m.accionar("rearmar")
    m.accionar("abrir")
    assert not m.paso(DT, {"I_fasores": [0.2]})["cerrado"] and not m.disparado
    m.accionar("cerrar")
    assert m.salidas()["cerrado"]


def test_las_hipotesis_dicen_lo_que_no_se_simula():
    h = " ".join(dif("DIF-4P-40A-30MA-B").hipotesis)
    assert f"{K:g} × IΔn" in h
    assert "componente continua" in h and "fuga natural" in h and "clase B" in h


def test_polos_y_clase_mal_declarados():
    base = dict(CATALOG["DIF-2P-25A-30MA-A"].electrico.modelo)
    with pytest.raises(ModeloIncompleto, match="es 2 o 4"):
        crear_modelo("-F1", "X", {**base, "polos": 3})
    with pytest.raises(ModeloIncompleto, match="falta «IDn_mA»"):
        crear_modelo("-F1", "X", {k: v for k, v in base.items() if k != "IDn_mA"})
    crudo = {"funcion": "F", "simbolo": "dif", "montaje": "campo",
             "bornes": [{"id": "1", "rol": "potencia"}], "modelo": {**base, "clase_residual": "K"},
             "a_confirmar": ["Inc_kA", "Inc_con", "Im_A"], "fuente": "criterio de diseño: prueba"}
    with pytest.raises(ValueError, match=r"modelo\.clase_residual: «K» no es válido; opciones: AC, A, F, B"):
        parse_ficha(crudo, "X")
    crudo["modelo"]["clase_residual"] = "b"
    assert parse_ficha(crudo, "X").modelo["clase_residual"] == "B"


# ── el catálogo ──────────────────────────────────────────────────────────────────────────────


def test_las_8_refs_y_sus_caminos_van_de_linea_a_carga():
    assert len(DIFERENCIALES) == 8
    for ref in DIFERENCIALES:
        f = CATALOG[ref].electrico
        lado = {b.id: b.lado for b in f.bornes}
        prot = [c for c in f.caminos if c.tipo == "proteccion"]
        assert len(prot) == f.modelo["polos"], ref  # el N también pasa por el toroide
        assert all(lado[c.de] == "linea" and lado[c.a] == "carga" for c in prot), ref
        assert {c.de for c in prot} >= {"1", "N1"}, ref
        # honestas: ninguna cifra de ficha sin su documento; lo no verificado, SIN valor
        assert set(f.a_confirmar) | set(f.datos) >= {"Inc_kA", "Inc_con", "Im_A", "T_max_C"}, ref
        assert not set(f.a_confirmar) & set(f.datos) and f.fuente, ref
        assert CATALOG[ref].specs["IDn_mA"] == f.modelo["IDn_mA"], ref


# ── en el tablero ────────────────────────────────────────────────────────────────────────────


def _d(des: str, ref: str, **kw):
    return dispositivo_desde_ficha(des, ref, CATALOG[ref].electrico, ubicacion="+TAB1", **kw)


def _w(*puntos: str) -> Conductor:
    return Conductor(tuple(puntos), seccion_mm2=2.5)


def tablero_1f(ref_dif: str, R_carga: float = 220.0) -> Tablero:
    """RED-1F-220V-60HZ (TN) → diferencial 2P → ITM C2 2P → carga resistiva de 1 A."""
    m = ModeloElectrico(
        (_d("-G1", "RED-1F-220V-60HZ"), _d("-F1", ref_dif), _d("-Q1", "ITM-C2-2P")),
        (_w("-G1:L", "-F1:1"), _w("-G1:N", "-F1:N1"), _w("-F1:2", "-Q1:1"), _w("-F1:N2", "-Q1:3")))
    e = entrada_red(m)
    e["cargas"].append({"id": "carga", "tipo": "otra", "bornes": ["-Q1:2", "-Q1:4"], "modo": "impedancia",
                        "R_ohm": R_carga})
    return Tablero(e, list(m.dispositivos))


def tablero_3f_n(ref_dif: str = "DIF-4P-40A-30MA-A", fases=("2", "4", "6")) -> Tablero:
    """RED-3F-380-220V-60HZ (TN) → diferencial 4P → una carga de 100 Ω de cada fase al N."""
    m = ModeloElectrico(
        (_d("-G1", "RED-3F-380-220V-60HZ"), _d("-F1", ref_dif)),
        (_w("-G1:L1", "-F1:1"), _w("-G1:L2", "-F1:3"), _w("-G1:L3", "-F1:5"), _w("-G1:N", "-F1:N1")))
    e = entrada_red(m)
    for b in fases:
        e["cargas"].append({"id": f"carga{b}", "tipo": "otra", "bornes": [f"-F1:{b}", "-F1:N2"],
                            "modo": "impedancia", "R_ohm": 100.0})
    return Tablero(e, list(m.dispositivos))


def correr(tab: Tablero, segundos: float) -> dict:
    for _ in range(round(segundos / DT)):
        tab.paso(DT)
    return tab.senales()


def test_1f_tn_corto_de_1k_a_pe_dispara_el_de_30ma_y_no_el_itm():
    tab = tablero_1f("DIF-2P-25A-30MA-A")
    s = correr(tab, 0.1)
    assert s["-F1.cerrado"] and s["-Q1.cerrado"] and s["-F1.I_residual_mA"] < PISO_mA  # 1 A que vuelve
    aplicar(tab, {"falla": "corto", "a": "-Q1:2", "b": "-G1:PE", "R_ohm": 1000.0})
    s = correr(tab, 0.1)
    assert s["-F1.disparado"] and s["-F1.causa"] == "diferencial"
    assert not s["-Q1.disparado"] and s["-Q1.cerrado"]
    assert tab.modelos["-F1"]._t == 0.0 and s["-F1.I_residual_mA"] == 0.0  # abierto ya no ve


def test_1f_tn_el_de_300ma_no_dispara_con_el_mismo_corto():
    tab = tablero_1f("DIF-2P-25A-300MA-A")
    correr(tab, 0.02)
    aplicar(tab, {"falla": "corto", "a": "-Q1:2", "b": "-G1:PE", "R_ohm": 1000.0})
    s = correr(tab, 0.5)
    assert not s["-F1.disparado"] and s["-F1.cerrado"]
    assert s["-F1.I_residual_mA"] == pytest.approx(220.0, rel=0.01)  # 220 V / 1 kΩ: bajo 0,75 × 300


def test_3f_n_equilibrada_y_desequilibrada_tras_un_4p_no_dispara():
    for fases in (("2", "4", "6"), ("2",), ("2", "6")):
        tab = tablero_3f_n(fases=fases)
        s = correr(tab, 0.3)
        assert not s["-F1.disparado"] and s["-F1.I_residual_mA"] < PISO_mA, fases
        corrientes = [abs(tab._fasor(True, rid)) for _, rid in tab.diferenciales[0][2]]
        assert max(corrientes) == pytest.approx(2.2, rel=0.02), fases  # sí circula corriente


def test_3f_n_un_corto_a_pe_tras_el_4p_dispara():
    tab = tablero_3f_n()
    correr(tab, 0.02)
    aplicar(tab, {"falla": "corto", "a": "-F1:4", "b": "-G1:PE", "R_ohm": 1000.0})
    s = correr(tab, 0.2)
    assert s["-F1.disparado"] and s["-F1.causa"] == "diferencial"


def test_el_tablero_indexa_el_diferencial_aparte_y_mueve_sus_contactos():
    tab = tablero_1f("DIF-2P-25A-30MA-A")
    assert [d for d, *_ in tab.diferenciales] == ["-F1"] and [d for d, *_ in tab.protecciones] == ["-Q1"]
    assert {rid for _, rid in tab.diferenciales[0][2]} == {"-F1:1-2", "-F1:N1-N2"}
    assert tab.estados()["-F1.cerrado"] is True
    tab.modelos["-F1"].accionar("abrir")
    assert tab.estados()["-F1.cerrado"] is False
    s = correr(tab, 0.02)
    assert abs(tab._fasor(True, "-F1:1-2")) < 1e-3 and not s["-F1.disparado"]


# ── ERC: «tipo de diferencial» (D10) ─────────────────────────────────────────────────────────


def _variador_tras(ref_dif: str | None) -> ModeloElectrico:
    disp = [_d("-G1", "RED-3F-220V-60HZ"), _d("-U1", "VFD-2K2-220")]
    if ref_dif is None:
        return ModeloElectrico(tuple(disp), (_w("-G1:L1", "-U1:L1"), _w("-G1:L2", "-U1:L2"),
                                             _w("-G1:L3", "-U1:L3")))
    disp.append(_d("-F1", ref_dif))
    return ModeloElectrico(tuple(disp), (
        _w("-G1:L1", "-F1:1"), _w("-G1:L2", "-F1:3"), _w("-G1:L3", "-F1:5"),
        _w("-F1:2", "-U1:L1"), _w("-F1:4", "-U1:L2"), _w("-F1:6", "-U1:L3")))


def _regla(m) -> list[dict]:
    return [r for r in erc(m) if r["regla"] == "tipo de diferencial"]


def test_erc_variador_tras_un_diferencial_clase_a_avisa():
    (r,) = _regla(_variador_tras("DIF-4P-40A-30MA-A"))
    assert r["estado"] == "aviso" and r["elementos"] == ["-U1", "-F1"]
    assert "clase A" in r["detalle"] and "clase B" in r["recomendacion"]
    assert r["norma"] == "criterio de diseño"


def test_erc_variador_tras_un_diferencial_clase_b_pasa():
    (r,) = _regla(_variador_tras("DIF-4P-40A-300MA-B"))
    assert r["estado"] == "ok" and r["elementos"] == ["-F1"]


def test_erc_sin_diferencial_la_regla_no_da_fila():
    assert _regla(_variador_tras(None)) == []
