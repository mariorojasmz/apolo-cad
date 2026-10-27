"""Capacidad de la cadena de IZAJE (plan `docs/plans/cadena-de-izaje.md`, F2a): la tensión de cada
cadena de `create_hoist_chain` contra la rotura de su ficha con FS ≥ 7 (iwis), y el pasador de cada
amarre dimensionado por esa regla (no «sin dimensionar»), sólo cuando la regla corrió.
"""

from __future__ import annotations

import pytest
from test_cadena_izaje import _elevador

from apolo.doc import Document
from apolo.library.engineering.izaje_capacidad import FS_MIN, FUENTES, KU_TSUBAKI, coeficiente_desigual
from apolo.library.engineering.report import structure_engineering_check
from apolo.services import engineering_rules
from apolo.services.engineering_rules import structure_rules
from apolo.services.izaje_rules import hoist_rules

SIN_DIM = "uniones apernadas sin dimensionar"


@pytest.fixture(scope="module")
def elevador():
    doc = Document("elevador-capacidad")
    return doc, _elevador(doc)


def _regla_izaje(reglas):
    mias = [r for r in reglas if r["regla"].startswith("capacidad de la cadena de izaje")]
    assert len(mias) == 1, [r["regla"] for r in reglas]
    return mias[0]


def _sin_dimensionar(reglas) -> str:
    return next((r["detalle"] for r in reglas if r["regla"] == SIN_DIM), "")


def test_ok_con_la_carga_del_elevador_y_la_memoria_cita_su_fuente(elevador):
    doc, ids = elevador
    reglas, verificados = hoist_rules(doc)
    r = _regla_izaje(reglas)
    cid = ids["cadena"]
    assert r["estado"] == "ok", r["detalle"]
    assert verificados == {f"{cid}_pasador_a", f"{cid}_pasador_b"}
    calc = r["calc"]
    # una cadena cuelga la plataforma (Ku = 1): T = masa·g + peso de la cadena, FS = 17 800 / T
    assert "Ku = 1" in calc["entradas"]["cadenas que lo cuelgan"]
    assert calc["fs"] >= FS_MIN
    assert "17.8 kN" in calc["entradas"]["cadena"]
    # la norma con su fuente: la cifra leída, la frase y la URL
    assert "iwis" in calc["norma"] and "FS ≥ 7" in calc["norma"]
    assert FUENTES["fs"]["cifra"] == FS_MIN
    assert any(FUENTES["fs"]["url"] in h and FUENTES["fs"]["frase"] in h for h in r["hipotesis"])
    assert r["fuentes"][0]["url"].startswith("https://www.iwis.com/")
    assert set(r["piezas"]) == {cid, ids["placa_a"], ids["placa_b"]}


def test_error_con_una_carga_que_pasa_la_rotura_entre_el_fs(elevador):
    doc, _ids = elevador
    # 17,8 kN / 7 = 2 543 N ≈ 259 kg: con 300 kg de carga útil el FS cae bajo 7
    r = _regla_izaje(hoist_rules(doc, 300.0)[0])
    assert r["estado"] == "error"
    assert r["calc"]["fs"] < FS_MIN
    assert "300 kg" in r["calc"]["entradas"]["carga útil"]
    assert "rotura" in r["recomendacion"]


def test_el_pasador_no_sale_sin_dimensionar_cuando_la_regla_corrio(elevador):
    doc, ids = elevador
    cid = ids["cadena"]
    reglas = structure_rules(doc, None, None)
    assert f"{cid}_pasador_a" not in _sin_dimensionar(reglas)
    assert f"{cid}_pasador_b" not in _sin_dimensionar(reglas)
    assert _regla_izaje(reglas)["estado"] == "ok"


def test_el_pasador_sale_sin_dimensionar_cuando_la_regla_no_corrio(elevador, monkeypatch):
    doc, ids = elevador
    cid = ids["cadena"]
    # el chequeo estructural solo, sin la regla de capacidad
    solo = structure_engineering_check(doc.scene, doc.fasteners, doc.grounds, doc.joints, doc.mates)
    assert f"{cid}_pasador_a" in _sin_dimensionar(solo)
    # y por structure_rules, si la regla de izaje no da nada
    import apolo.services.izaje_rules as mod

    monkeypatch.setattr(mod, "hoist_rules", lambda doc, carga=None: ([], set()))
    reglas = engineering_rules.structure_rules(doc, None, None)
    assert f"{cid}_pasador_b" in _sin_dimensionar(reglas)


def test_sin_junta_cuelga_por_el_grafo_y_si_toca_tierra_no_inventa_la_carga():
    doc = Document("izaje-sin-junta")
    ids = _elevador(doc)
    cid = ids["cadena"]
    doc.joints.pop("j_plataforma")  # sólo en memoria: la plataforma ya no cuelga de una junta
    r = _regla_izaje(hoist_rules(doc)[0])
    assert r["estado"] == "ok" and r["calc"]["fs"] >= FS_MIN  # lo unido a la placa, sin tierra
    doc.grounds["g_plataforma"] = {"name": "g_plataforma", "feature": ids["plataforma"]}
    reglas, verificados = hoist_rules(doc)
    r = _regla_izaje(reglas)
    assert r["estado"] == "aviso" and "calc" not in r
    assert not verificados  # el pasador vuelve a contar sin dimensionar
    solo = structure_engineering_check(doc.scene, doc.fasteners, doc.grounds, doc.joints,
                                       doc.mates, uniones_verificadas=verificados)
    assert f"{cid}_pasador_a" in _sin_dimensionar(solo)


def test_coeficiente_de_carga_desigual():
    assert coeficiente_desigual(2) == (KU_TSUBAKI[2], None)
    ku, nota = coeficiente_desigual(3)
    assert ku == KU_TSUBAKI[2] and "conservador" in nota
    assert coeficiente_desigual(6)[0] == KU_TSUBAKI[4]
