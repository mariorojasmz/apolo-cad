"""Referencias `[=función][+ubicación]-dispositivo:borne` (plan V8.1 D4) y tensiones de placa
(`electrico/tension.py`). Puros: no cargan el catálogo."""

from __future__ import annotations

import math

import pytest

from apolo.library.electrico.referencias import (
    Referencia,
    ReferenciaError,
    formatear,
    parse_designacion,
    parse_referencia,
    sufijo_sugerencia,
    sugerir,
)
from apolo.library.electrico.tension import admite, parse_tension, tension_entre

# ── referencias ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("texto,esperada", [
    ("-K1:A1", Referencia("K1", "A1")),
    ("+TAB1-K1:A1", Referencia("K1", "A1", ubicacion="TAB1")),
    ("=Faja1-K1:A1", Referencia("K1", "A1", funcion="Faja1")),
    ("=Faja1+TAB1-Q2:2", Referencia("Q2", "2", funcion="Faja1", ubicacion="TAB1")),
    ("-T1:L+", Referencia("T1", "L+")),
    ("-T2:+10V", Referencia("T2", "+10V")),
    ("-K1:I0.0", Referencia("K1", "I0.0")),
    ("-X1:3.2", Referencia("X1", "3.2")),
    ("-K1", Referencia("K1")),
])
def test_ida_y_vuelta(texto, esperada):
    ref = parse_referencia(texto)
    assert ref == esperada
    assert formatear(ref) == str(ref) == texto
    assert parse_referencia(str(ref)) == ref


def test_designacion_y_producto():
    ref = parse_referencia("=Faja2+TAB1-K1:A1")
    assert ref.designacion == "=Faja2-K1" and ref.producto == "-K1"
    assert parse_designacion("=Faja2-K1").designacion == "=Faja2-K1"
    with pytest.raises(ReferenciaError, match="es una referencia, no una designación"):
        parse_designacion("-K1:A1")


@pytest.mark.parametrize("texto,pista", [
    ("K1:A1", "¿Quisiste decir «-K1:A1»?"),
    ("-K1 :A1", "lleva espacios"),
    ("-K1:A1:2", "más de un «:»"),
    ("-K1:", "termina en «:» sin borne"),
    ("", "referencia vacía"),
    ("+TAB1:A1", "le falta el dispositivo"),
    ("-1K:A1", "no es una referencia válida"),
])
def test_errores_dicen_la_forma_correcta(texto, pista):
    with pytest.raises(ReferenciaError) as exc:
        parse_referencia(texto)
    assert pista in str(exc.value)
    assert isinstance(exc.value, ValueError)


def test_extremo_de_conductor_exige_borne():
    with pytest.raises(ReferenciaError, match=r"le falta el borne: «-K1:<borne>»"):
        parse_referencia("-K1", exige_borne=True)


def test_quisiste_decir():
    disenos = ["-K1", "-K2", "-Q1", "-Q2", "-T1"]
    assert sugerir("-K3", disenos)[:2] == ["-K1", "-K2"]
    assert sufijo_sugerencia("-Q9", disenos) == " ¿Quisiste decir: -Q1, -Q2?"
    assert sufijo_sugerencia("-Z99", disenos) == ""
    # ids cortos: a igual parecido, primero los del mismo prefijo
    bornes = ["1", "2", "3", "A1", "A2", "13", "14"]
    assert sugerir("A3", bornes)[:2] == ["A1", "A2"]
    assert "A3" not in sugerir("A3", bornes + ["A3"])


# ── tensiones de placa ────────────────────────────────────────────────────────────────────


def test_parse_tension():
    t = parse_tension("24 VDC")
    assert (t.tipo, t.valores, t.fases) == ("DC", (24.0,), None)
    t = parse_tension("220 VAC 3F 60 Hz")
    assert (t.tipo, t.valores, t.fases, t.neutro, t.frecuencia_hz) == ("AC", (220.0,), 3, False, (60.0,))
    assert t.linea == 220 and t.fase == pytest.approx(220 / math.sqrt(3))
    t = parse_tension("380/220 VAC 3F+N 60 Hz")
    assert t.neutro and t.linea == 380 and t.fase == 220
    t = parse_tension("100-240 VAC")
    assert t.rango == (100.0, 240.0) and t.fases == 1
    assert parse_tension("24 VAC/DC").tipo == "UC" and parse_tension("230 V AC/DC").tipo == "UC"
    assert parse_tension("220/380 VAC 3F").valores == (220.0, 380.0)
    assert parse_tension("24,5 VDC").valores == (24.5,)


@pytest.mark.parametrize("texto,pista", [
    ("24 voltios", "tensión ilegible"),
    ("24 VDC 3F", "sólo vale en alterna"),
    ("24 VDC 60 Hz", "no lleva frecuencia"),
    ("30-10 VDC", "mín < máx"),
    ("380/200 VAC 3F+N", "√3"),
    ("", "vacía"),
])
def test_tension_ilegible(texto, pista):
    with pytest.raises(ValueError, match=pista):
        parse_tension(texto)


def test_tension_entre_polos():
    red = parse_tension("220 VAC 3F 60 Hz")
    assert tension_entre(red, "L1", "L2") == pytest.approx(220)
    assert tension_entre(red, "L1", "L1") == 0
    assert tension_entre(red, "L1", "PE") is None  # sin neutro no se infiere fase-tierra
    con_n = parse_tension("380/220 VAC 3F+N")
    assert tension_entre(con_n, "L2", "N") == pytest.approx(220, rel=0.01)  # 380/√3 = 219,4
    assert tension_entre(con_n, "L3", "L1") == pytest.approx(380)
    assert tension_entre(con_n, "L1", "PE") == pytest.approx(220, rel=0.01)  # TN supuesto
    dc = parse_tension("24 VDC")
    assert tension_entre(dc, "+", "-") == 24 and tension_entre(dc, "-", "+") == -24


def test_admite_con_la_tolerancia_de_iec_60204():
    bobina = parse_tension("24 VDC")
    assert admite(bobina, "DC", 24) and admite(bobina, "DC", 21.6) and not admite(bobina, "DC", 20)
    assert not admite(bobina, "AC", 24)  # alterna en una bobina de continua
    entrada = parse_tension("24 VDC")
    assert admite(entrada, "DC", -24) and not admite(entrada, "DC", -24, polar=True)
    motor = parse_tension("230/400 VAC 3F")
    assert admite(motor, "AC", 220) and admite(motor, "AC", 380)
    assert not admite(motor, "AC", 380, preferida=230)  # en triángulo sólo la menor
    fuente = parse_tension("100-240 VAC")
    assert admite(fuente, "AC", 220) and not admite(fuente, "AC", 380)
    piloto = parse_tension("24 VAC/DC")
    assert admite(piloto, "AC", 24) and admite(piloto, "DC", 24)
