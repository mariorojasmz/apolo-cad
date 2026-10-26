"""El método de IEC 60890:1987 tabulado por ABB (plan V8.5 F3, D6): `library/electrico/iec60890.py`
y las reglas puras del calentamiento (`calentamiento.py`) y de los prensaestopas (`prensaestopas.py`).

- El EJEMPLO RESUELTO de la guía (ABB SACE, Electrical installation handbook Vol. 1, 2.ª ed. 2004,
  Annex B, págs. 302–305): envolvente aislada de pared, sin aberturas ni tabiques, 2000 × 1440 ×
  840 mm, P = 784 W → Ae = 8,75 m², Δt₀,₅ = 23,8 K y Δt₁,₀ = 29,8 K (la guía redondea k a 0,112 y
  trunca el producto: la interpolación lineal da 23,9 y 30,0; se exige ≤ 1 %).
- Las tablas: monótonas, la T7 y la T11 empalman en 1,25 m², los dos dudosos tal cual (decisión).
- Lo que el método no cubre se RECHAZA (rama chica con aberturas, fuera de tabla), nunca se
  extrapola.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from apolo.library.electrico import calentamiento as cal
from apolo.library.electrico import iec60890 as m
from apolo.library.electrico.prensaestopas import Opcion, Placa, Salida, colocar, elegir

EJEMPLO = m.Envolvente(alto_mm=2000, ancho_mm=1440, fondo_mm=840)  # de pared: el fondo cubierto


def test_el_ejemplo_resuelto_de_la_guia():
    r = m.calentamiento(EJEMPLO, 784.0)
    assert r.Ae_m2 == pytest.approx(8.75, abs=0.01)
    assert {c.nombre: round(c.Ae_m2, 2) for c in r.caras} == {
        "techo": 1.69, "frente": 2.59, "fondo": 1.44, "lateral 1": 1.51, "lateral 2": 1.51}
    assert r.rama.startswith("Ae > 1.25") and r.x == 0.804 and r.d == 1.0
    assert r.tipo == 3  # «separate enclosure for wall-mounting» = columna 3 (pág. 305)
    assert r.k == pytest.approx(0.112, abs=0.001)          # «k results 0.112 (value interpolated)»
    assert r.f == pytest.approx(2.107, abs=0.001)          # f = 2^1,35 / (1,44 · 0,84)
    assert r.c == pytest.approx(1.255, abs=0.001)          # «c results to be equal to 1.255»
    assert r.dt_media_K == pytest.approx(23.8, rel=0.01)
    assert r.dt_arriba_K == pytest.approx(29.8, rel=0.01)
    # con el k redondeado de la guía, su cifra exacta
    assert 0.112 * 784 ** 0.804 == pytest.approx(23.8, abs=0.05)
    # 35 °C de ambiente: 59 y 65 °C (pág. 305)
    assert round(35 + r.dt_media_K) == 59 and round(35 + r.dt_arriba_K) == 65


def test_las_tablas_son_monotonas_y_empalman():
    def baja(xs):
        return all(a >= b for a, b in zip(xs, xs[1:]))

    def sube(xs):
        return all(a <= b for a, b in zip(xs, xs[1:]))

    assert baja([k for _, k in m.T7_K]) and baja([k for _, k in m.T11_K])
    assert m.T7_K[0] == (1.25, 0.524) and m.T11_K[-1] == (1.25, 0.524)
    assert sube([c for _, c in m.T12_C])
    for col in range(5):
        assert sube([fila[col] for fila in m.T8_C])
    for fila in m.T9_K:
        assert baja(fila)
    for j in range(len(m.T9_AE)):
        assert baja([fila[j] for fila in m.T9_K])
    for fila in m.T10_C:
        assert sube(fila)
    # los dos dudosos de la guía se conservan (yerran hacia MÁS calor: docstring del módulo)
    assert m.T8_C[m.T8_F.index(11)][2] == 1.549
    assert m.T9_K[m.T9_ENTRADA.index(300)][m.T9_AE.index(6)] == 0.115


def test_la_rama_chica_y_su_reparto():
    r = m.calentamiento(m.Envolvente(400, 500, 200), 100.0)
    assert r.rama.startswith("Ae ≤") and r.Ae_m2 == pytest.approx(0.564)
    assert r.k == pytest.approx(0.960 + (0.9 - 0.960) * (0.564 - 0.55) / 0.05)
    assert r.g == pytest.approx(0.8) and r.c == pytest.approx(1.156)
    assert r.dt_media_K == pytest.approx(r.k * 100 ** 0.804)
    assert r.h_arriba == 0.75  # Δt0,75 = Δt1,0 (pág. 296)
    assert r.delta_a(0.2) == r.dt_media_K and r.delta_a(0.75) == r.dt_arriba_K == r.delta_a(1.0)
    assert r.delta_a(0.625) == pytest.approx((r.dt_media_K + r.dt_arriba_K) / 2)
    # el techo cubierto baja Ae y sube el calentamiento
    cubierto = m.calentamiento(m.Envolvente(400, 500, 200, techo_cubierto=True), 100.0)
    assert cubierto.Ae_m2 == pytest.approx(0.564 - 0.07) and cubierto.dt_media_K > r.dt_media_K


def test_lo_que_el_metodo_no_cubre_se_rechaza():
    with pytest.raises(m.FueraDeDominio, match="no tiene esa rama"):
        m.calentamiento(m.Envolvente(400, 500, 200, entrada_aire_cm2=100), 100.0)
    with pytest.raises(m.FueraDeDominio, match="T7"):  # Ae > 11,5 sin aberturas: no se extrapola
        m.calentamiento(m.Envolvente(2200, 2500, 1200), 500.0)
    with pytest.raises(m.FueraDeDominio, match="T11"):
        m.calentamiento(m.Envolvente(150, 150, 80), 10.0)
    with pytest.raises(m.FueraDeDominio, match="tabiques"):
        m.calentamiento(m.Envolvente(2000, 1440, 840, tabiques=4), 100.0)


def test_con_aberturas_y_la_entrada_minima():
    con = m.calentamiento(m.Envolvente(2000, 1440, 840, entrada_aire_cm2=300), 784.0)
    assert con.x == 0.715 and con.rama.startswith("Ae > 1.25 m², con aberturas")
    assert con.dt_media_K < m.calentamiento(EJEMPLO, 784.0).dt_media_K
    entrada = m.entrada_minima(EJEMPLO, 784.0, 20.0)
    assert entrada in m.T9_ENTRADA
    assert m.calentamiento(m.Envolvente(2000, 1440, 840, entrada_aire_cm2=entrada), 784.0).dt_arriba_K <= 20.0
    assert m.entrada_minima(m.Envolvente(400, 500, 200), 100.0, 5.0) is None  # la rama chica no tiene aberturas


def test_el_tipo_de_instalacion_por_las_caras_cubiertas():
    t = m.tipo_instalacion
    assert t(m.Envolvente(1, 1, 1, fondo_cubierto=False)) == 1
    assert t(m.Envolvente(1, 1, 1, fondo_cubierto=False, laterales_cubiertos=1)) == 2
    assert t(m.Envolvente(1, 1, 1)) == 3
    assert t(m.Envolvente(1, 1, 1, laterales_cubiertos=1)) == 4
    assert t(m.Envolvente(1, 1, 1, laterales_cubiertos=2, techo_cubierto=True)) == 4
    assert t(m.Envolvente(1, 1, 1, laterales_cubiertos=2)) == 5


# ── reglas del calentamiento del tablero ──────────────────────────────────────────────────


def test_la_corriente_de_un_conductor_por_sus_bornes():
    itm = {"tipo": "itm", "In_A": 16}
    assert cal.corriente_de_borne("itm", itm, {}, "potencia", "carga") == ("limite", 16.0)
    assert cal.corriente_de_borne("itm", itm, {}, "potencia", "linea") == ("alimenta", 16.0)
    gm = {"tipo": "guardamotor", "Ir_A": [4.0, 6.3]}
    assert cal.corriente_de_borne("guardamotor", gm, {}, "potencia", "carga") == ("limite", 6.3)
    assert cal.corriente_de_borne("guardamotor", gm, {"Ir_A": 5.0}, "potencia", "carga") == ("limite", 5.0)
    assert cal.corriente_de_borne("fuente", {"I_salida_A": 5}, {}, "mando", "carga") == ("limite", 5.0)
    assert cal.corriente_de_borne("piloto", {"I_mA": 18}, {}, "mando", None) == ("otra", 0.018)
    assert cal.corriente_de_borne("plc", {"DO_A": 0.5}, {}, "mando", None) is None  # su alimentación
    assert cal.corriente_de_borne(None, {}, {}, "tierra", None) == ("tierra", 0.0)
    # la línea de dos protecciones: la suma; con un límite, el menor; tierra, 0; nada, None
    assert cal.corriente_conductor([None, ("alimenta", 16.0), ("alimenta", 2.0), ("otra", 25.0)]) == 18.0
    assert cal.corriente_conductor([("limite", 16.0), ("otra", 13.0), ("limite", 5.0)]) == 5.0
    assert cal.corriente_conductor([("tierra", 0.0), ("limite", 16.0)]) == 0.0
    assert cal.corriente_conductor([None, None]) is None
    w, motivo = cal.perdidas_conductor(cal.Conductor("c", 2.5, 1000.0, 16.0))
    assert w == pytest.approx(16 ** 2 * 7.98 / 1000) and motivo is None
    assert cal.perdidas_conductor(cal.Conductor("c", 3.0, 1000.0, 1.0))[1].startswith("sección")
    assert cal.perdidas_conductor(cal.Conductor("c", 1.0, 1000.0, None)) == (0.0, "sin corriente asignada")


def test_si_se_pasa_sugiere_el_caudal_y_con_el_ventilador_cumple():
    env = m.Envolvente(400, 500, 200)
    aparatos = [cal.AparatoTermico("-T2", 0.9, 50.0), cal.AparatoTermico("-X0", 0.2, 105.0),
                cal.AparatoTermico("-T1", 0.5, None)]
    ev = cal.evaluar(env, 157.0, aparatos, 35.0)
    assert [x.designacion for x in ev.pasan] == ["-T2"] and ev.sin_tmax == ("-T1",)
    assert ev.peor.designacion == "-T2"
    s = ev.sugerencia
    assert s.dt_admisible_K == 15.0 and s.entrada_cm2 is None  # rama chica: sin aberturas naturales
    rho = 101325.0 / (287.05 * (35 + 273.15))
    assert s.caudal_m3h == pytest.approx(157.0 / (rho * 1005.0 * 15.0) * 3600, abs=0.05)
    ok = cal.evaluar(env, 157.0, aparatos, 35.0, ventilacion_m3h=math.ceil(s.caudal_m3h))
    assert not ok.pasan and ok.T_arriba_C <= 50.0 and ok.calor.rama.startswith("ventilación forzada")
    caliente = cal.evaluar(env, 157.0, aparatos, 55.0)
    assert caliente.sugerencia.refrigeracion  # el ambiente ya pasa la máxima: ventilar no alcanza


# ── prensaestopas ─────────────────────────────────────────────────────────────────────────

LAPP = [Opcion("M16", "M16x1,5", 4, 10, 19), Opcion("M20", "M20x1,5", 6, 13, 25), Opcion("M25", "M25x1,5", 8, 17, 30),
        Opcion("M32", "M32x1,5", 9, 21, 36), Opcion("M40", "M40x1,5", 16, 28, 46)]


def test_el_prensaestopas_por_el_diametro_del_cable():
    assert elegir(LAPP, 9.8)[0].ref == "M16"   # la menor rosca cuyo rango lo contiene
    assert elegir(LAPP, 11.5)[0].ref == "M20"
    assert elegir(LAPP, 20.0)[0].ref == "M32"
    assert elegir(LAPP, 28.0)[0].ref == "M40"
    o, motivo = elegir(LAPP, 30.0)
    assert o is None and "más grueso" in motivo
    o, motivo = elegir(LAPP, 3.0)
    assert o is None and "más delgado" in motivo
    assert elegir(LAPP, None) == (None, "su ref no da el Ø exterior del cable")


def test_los_prensaestopas_no_se_enciman_ni_salen_de_la_placa():
    placa = Placa(-200, 200, -60, 60)
    salidas = [Salida("a", "-W1", 9.8, -190, 40), Salida("b", "-W2", 7.7, -190, 40),
               Salida("c", "-W3", 11.5, -190, 40), Salida("d", "-W9", 35.0, 0, 0)]
    r = colocar(salidas, LAPP, placa)
    con = [p for p in r.prensas if p.ref]
    assert [p.cable for p in r.prensas] == ["a", "b", "c", "d"]  # el orden de entrada
    assert r.prensas[-1].ref is None and "más grueso" in r.prensas[-1].motivo
    xs = sorted(con, key=lambda p: p.x)
    for p, q in zip(xs, xs[1:]):
        assert q.x - p.x >= 19 / 2 + 10 + 19 / 2 - 1e-6
    assert all(-200 <= p.x <= 200 and p.y <= 60 - 9.5 + 1e-6 for p in con) and not r.avisos
    lleno = colocar([Salida(str(i), f"-W{i}", 20.0, 0, 0) for i in range(12)], LAPP, placa)
    assert lleno.avisos and "no entran" in lleno.avisos[0]


def test_los_modulos_son_puros():
    raiz = Path(__file__).resolve().parents[1] / "core" / "apolo" / "library" / "electrico"
    for nombre in ("iec60890.py", "calentamiento.py", "prensaestopas.py"):
        arbol = ast.parse((raiz / nombre).read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ImportFrom) and nodo.level == 0:
                assert nodo.module in ("__future__", "bisect", "dataclasses"), (nombre, nodo.module)
            if isinstance(nodo, ast.Import):
                assert all(a.name in ("math",) for a in nodo.names), nombre
