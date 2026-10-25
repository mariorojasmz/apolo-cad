"""Las variables de cada PLC en el `inicio` de la sesión viva (plan pedidos-de-extensiones D12;
`services/variables_plc.py`): las mismas rutas y en el mismo orden que `PLC.variables()` (la
escritura de la señal del fotograma), con el `tipo` y el `escribible` de `Compilado.simbolos`, que
son los de `PLC.escribir`; globales, PROGRAM, CONSTANT, `AT` y bloques; sin PLC, sin clave."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apolo.plc import PLC, compilar
from apolo.services.variables_plc import plcs, rutas_de_senal, variables

FUENTE = """
VAR_GLOBAL
  consigna : INT := 5;
  limite : REAL;
  entrada AT %IX0.0 : BOOL;
  salida AT %QX0.0 : BOOL;
  tabla : ARRAY[1..3] OF INT;
END_VAR
VAR_GLOBAL CONSTANT
  MAXIMO : INT := 10;
END_VAR
FUNCTION_BLOCK Contador
VAR_INPUT pulso : BOOL; END_VAR
VAR_OUTPUT n : INT; END_VAR
n := n + 1;
END_FUNCTION_BLOCK
PROGRAM Main
VAR
  Cuenta : INT;
  t1 : TON;
  c1 : Contador;
END_VAR
VAR CONSTANT
  paso : INT := 2;
END_VAR
Cuenta := Cuenta + paso;
salida := entrada;
t1(IN := entrada, PT := T#1s);
c1(pulso := entrada);
END_PROGRAM
PROGRAM Aux
VAR
  modo : DINT;
  activo : BOOL;
END_VAR
activo := consigna > 0;
END_PROGRAM
"""


@pytest.fixture(scope="module")
def compilado():
    return compilar(FUENTE)


def test_las_rutas_son_las_de_las_senales_y_en_su_orden(compilado):
    assert rutas_de_senal(compilado) == list(PLC(compilado).variables())
    assert [v["ruta"] for v in variables(compilado)] == list(PLC(compilado).variables())


def test_tipo_y_escribible(compilado):
    por_ruta = {v["ruta"]: (v["tipo"], v["escribible"]) for v in variables(compilado)}
    assert por_ruta == {
        "consigna": ("INT", True), "limite": ("REAL", True),
        "entrada": ("BOOL", False), "salida": ("BOOL", False),       # AT %IX / %QX
        "tabla": ("ARRAY[1..3] OF INT", True),
        "maximo": ("INT", False),                                     # CONSTANT global
        "Main.cuenta": ("INT", True), "Main.paso": ("INT", False),    # CONSTANT del PROGRAM
        "Aux.modo": ("DINT", True), "Aux.activo": ("BOOL", True),
    }
    # un bloque y sus miembros no son señal: no salen
    assert not [r for r in por_ruta if r.startswith(("Main.t1", "Main.c1"))]


def test_escribible_es_lo_que_acepta_plc_escribir(compilado):
    plc = PLC(compilado)
    for v in variables(compilado):
        ruta = v["ruta"] + ("[1]" if v["tipo"].startswith("ARRAY") else "")
        valor = True if v["tipo"].endswith("BOOL") else 1
        try:
            plc.escribir(ruta, valor)
            acepto = True
        except ValueError:
            acepto = False
        assert acepto == v["escribible"], v


def test_un_plc_por_designacion_y_sin_plc_sin_nada(compilado):
    progs = [SimpleNamespace(plc="-K1", compilado=compilado),
             SimpleNamespace(plc="-K2", compilado=None),        # sin compilar: no hay tabla
             SimpleNamespace(plc="-K3", compilado=compilar("PROGRAM P VAR x : INT; END_VAR x := 1; END_PROGRAM"))]
    out = plcs(progs)
    assert [p["designacion"] for p in out] == ["-K1", "-K3"]
    assert out[1]["variables"] == [{"ruta": "P.x", "tipo": "INT", "escribible": True}]
    assert plcs([]) == [] and plcs(None) == []


def test_el_inicio_lleva_plcs_solo_si_hay(compilado):
    from apolo.api.routers.cosim_vivo import _inicio

    def inicio(programas):
        snap = SimpleNamespace(avisos=[], hipotesis=[], dinamica=SimpleNamespace(cuerpos=[]),
                               programas=programas)
        prep = {"snap": snap, "vis": None, "proyecto": 1, "nombre": "base", "firma": "2:x"}
        return _inicio(prep, {"senales": []}, {"max_s": 10, "ritmo": 1.0}, None)

    assert "plcs" not in inicio([])
    ini = inicio([SimpleNamespace(plc="-A1", compilado=compilado, nombre="prog")])
    assert ini["version"] == 1   # agregar una clave no sube la versión (D2)
    assert ini["plcs"] == [{"designacion": "-A1", "variables": variables(compilado)}]
