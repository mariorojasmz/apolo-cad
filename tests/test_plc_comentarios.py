"""Comentarios del ST en el árbol, sin tocar lo compilado (plan plc-en-el-lazo, D2) y la superficie
del PLC para extensiones (D1).

  - `tokenizar(fuente, comentarios=lista)` junta cada comentario de los tres estilos con su línea,
    columna, línea de cierre y estilo; los tokens son los MISMOS que sin juntar;
  - `parsear` los deja en `Unidad.comentarios` (vacío por defecto);
  - el `Compilado` (`fuente_py`, `mapa_lineas`, `tags` y el resto) es idéntico juntándolos o no,
    sobre los programas de `test_plc_*`, el del banco y el sintético de rendimiento.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from apolo import extensiones, extensiones_api
from apolo.plc import ErrorCompilacion, compilar
from apolo.plc import parser as P
from apolo.plc.ast_st import Comentario, Unidad
from apolo.plc.errores import ErrorSintaxis
from apolo.plc.lexer import tokenizar
from apolo.plc.parser import parsear
from cosim_lazo_banco import PROGRAMA
from test_plc_rendimiento import programa_sintetico

TESTS = Path(__file__).resolve().parent

FUENTE = (
    "(* cabecera\n"
    "   de dos líneas *)\n"
    "PROGRAM Main // al final de la línea\r\n"
    "VAR x : INT; /* en medio */ y : BOOL; END_VAR\n"
    "x := x + (*dentro de una expresión*) 1;\n"
    "//\n"
    "END_PROGRAM\n"
    "// sin fin de línea"
)


def corpus() -> list[str]:
    """Los programas ST literales de los `test_plc_*` (todo texto con END_PROGRAM), el del banco
    de la co-simulación y el sintético del gate de rendimiento."""
    out = []
    for ruta in sorted(TESTS.glob("test_plc_*.py")):
        for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) and "END_PROGRAM" in nodo.value:
                out.append(nodo.value)
    return [*dict.fromkeys(out), PROGRAMA, programa_sintetico()]


def test_los_tres_estilos_con_linea_columna_fin_y_estilo():
    coms: list[Comentario] = []
    tokenizar(FUENTE, coms)
    assert coms == [
        Comentario(" cabecera\n   de dos líneas ", 1, 1, 2, "(*"),
        Comentario(" al final de la línea", 3, 14, 3, "//"),  # sin el «\r» de Windows
        Comentario(" en medio ", 4, 14, 4, "/*"),
        Comentario("dentro de una expresión", 5, 10, 5, "(*"),
        Comentario("", 6, 1, 6, "//"),
        Comentario(" sin fin de línea", 8, 1, 8, "//"),
    ]


def test_los_tokens_son_los_mismos_juntando_o_no():
    for fuente in [FUENTE, *corpus()]:
        try:
            solos = tokenizar(fuente)
        except ErrorSintaxis as e:  # un programa de los tests de errores: el mismo error
            with pytest.raises(ErrorSintaxis) as otro:
                tokenizar(fuente, [])
            assert str(otro.value) == str(e)
            continue
        assert tokenizar(fuente, []) == solos


@pytest.mark.parametrize(("fuente", "linea", "col", "falta"), [
    ("PROGRAM M\n  (* sin cerrar\nEND_PROGRAM", 2, 3, "*)"),
    ("PROGRAM M /* tampoco", 1, 11, "*/"),
])
def test_un_comentario_sin_cerrar_es_error_con_su_lugar(fuente, linea, col, falta):
    coms: list[Comentario] = []
    with pytest.raises(ErrorSintaxis) as e:
        tokenizar(fuente, coms)
    err = e.value.error
    assert (err.linea, err.columna) == (linea, col)
    assert f"comentario sin cerrar: falta «{falta}»" in err.mensaje
    assert coms == []  # el que no cierra no se junta
    with pytest.raises(ErrorCompilacion, match="sin cerrar"):
        compilar(fuente)


def test_parsear_los_deja_en_la_unidad_y_por_defecto_va_vacia():
    assert Unidad().comentarios == []
    u = parsear(FUENTE)
    assert [c.estilo for c in u.comentarios] == ["(*", "//", "/*", "(*", "//", "//"]
    assert [p.nombre for p in u.pous] == ["Main"]
    assert parsear("PROGRAM M END_PROGRAM").comentarios == []


def _sin_juntar(fuente, comentarios=None, _orig=tokenizar):
    return _orig(fuente)


def _compilado(fuente: str):
    try:
        c = compilar(fuente)
    except ErrorCompilacion as e:
        return ("error", str(e))
    return (c.fuente_py, c.mapa_lineas, c.tags, c.programas, c.rutas, c.entradas, c.salidas,
            c.pous_py, repr(c.disposiciones))


def test_el_compilado_es_identico_con_y_sin_comentarios(monkeypatch):
    programas = corpus()
    assert len(programas) >= 20 and any("(*" in p for p in programas)
    con = [_compilado(f) for f in programas]
    monkeypatch.setattr(P, "tokenizar", _sin_juntar)
    assert parsear(FUENTE).comentarios == []  # de verdad no los juntó
    sin = [_compilado(f) for f in programas]
    assert con == sin
    assert sum(1 for c in con if c[0] != "error") >= 10


def test_la_superficie_del_plc_esta_en_el_contrato_de_extensiones():
    """D1: los nombres existen (lo exige `test_extensiones_api.py`) y agregar no sube el contrato."""
    m = extensiones_api.MODULOS
    assert {"apolo.plc", "apolo.plc.parser", "apolo.plc.ast_st", "apolo.plc.tipos",
            "apolo.plc.direcciones"} <= set(m)
    assert "Comentario" in m["apolo.plc.ast_st"] and "Unidad" in m["apolo.plc.ast_st"]
    assert set(m["apolo.plc"]) == {"compilar", "PLC", "Compilado", "ErrorCompilacion", "ErrorST",
                                   "FallaPLC", "RUN", "STOP", "SIN_TENSION"}
    assert extensiones.CONTRATO_EXTENSIONES == 1
