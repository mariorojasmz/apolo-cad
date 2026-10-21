"""`POST /api/assembly/declare` en modo propuesta (plan `uniones-en-lote`, D3).

`aplicar=false` devuelve lo que se declararía —acciones en el formato de un lote, con
`a_revisar` en lo que gira, y un resumen por raíz de patrón— sin tocar el documento. Sin cuerpo
sigue aplicando como siempre (la UI y la guardia del documento lo llaman así).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document


def _box(doc, name, x, z, w, h, y=0.0, d=100.0):
    return doc.execute("create_box", {"name": name, "width": w, "depth": d, "height": h,
                                      "position": {"x": x, "y": y, "z": z}})


@pytest.fixture()
def bastidor():
    """Base en el piso, dos largueros encima y un travesaño entre ellos que GIRA (hijo de una
    junta giratoria del larguero 1): sin las juntas, la autodetección lo soldaría."""
    doc = Document("declarar-propuesta")
    base = _box(doc, "Base", x=150, z=10, w=300, h=20)
    l1 = _box(doc, "Larguero 1", x=25, z=120, w=50, h=200)
    _box(doc, "Larguero 2", x=275, z=120, w=50, h=200)
    cross = _box(doc, "Travesaño", x=150, z=120, w=210, h=40)
    doc.execute("add_joint", {"name": "giro", "type": "giratoria", "parent": l1, "child": cross,
                              "axis": {"x": 1}})
    api.DOC = doc
    return TestClient(api.app), doc, base, cross


def _proponer(client) -> dict:
    r = client.post("/api/assembly/declare", json={"aplicar": False})
    assert r.status_code == 200, r.text
    return r.json()


def test_propuesta_no_muta_y_respeta_las_juntas(bastidor):
    client, doc, base, cross = bastidor
    antes = (len(doc.commands), len(doc._undo), dict(doc.fasteners), dict(doc.grounds))
    prop = _proponer(client)
    assert (len(doc.commands), len(doc._undo), dict(doc.fasteners), dict(doc.grounds)) == antes

    assert prop["aplicar"] is False
    grounds = [a for a in prop["acciones"] if a["type"] == "ground"]
    fasten = [a for a in prop["acciones"] if a["type"] == "fasten"]
    assert [g["params"]["feature"] for g in grounds] == [base]
    assert (prop["n_grounds"], prop["n_fasteners"]) == (len(grounds), len(fasten))

    # lo que gira (hijo de la junta) no se suelda: contacto + a_revisar con su motivo
    con_cross = [a for a in fasten if cross in (a["params"]["a"], a["params"]["b"])]
    assert con_cross and prop["n_a_revisar"] == len(con_cross)
    for a in con_cross:
        assert a["params"]["kind"] == "contacto" and a["a_revisar"] is True
        assert "junta móvil 'giro'" in a["motivo"]
        assert a["params"]["nota"].startswith("a revisar: ")
        assert len(a["params"]["nota"]) <= 120
    # lo que no gira sigue soldado, sin marca
    resto = [a for a in fasten if a not in con_cross]
    assert resto and all("a_revisar" not in a and "motivo" not in a for a in resto)


def test_aplicar_declara_lo_mismo_y_nombra_lo_que_hay_que_revisar(bastidor):
    client, doc, _, cross = bastidor
    prop = _proponer(client)
    n_undo = len(doc._undo)
    r = client.post("/api/assembly/declare", json={"aplicar": True})
    assert r.status_code == 200
    revisar = [a["params"]["name"] for a in prop["acciones"] if a.get("a_revisar")]
    assert r.json()["a_revisar"] == revisar
    for a in prop["acciones"]:
        tabla = doc.grounds if a["type"] == "ground" else doc.fasteners
        declarado = tabla[a["params"]["name"]]
        assert {k: declarado[k] for k in a["params"]} == a["params"]
    assert len(doc._undo) == n_undo + 1  # un lote = un undo
    # idempotente: ya no queda nada que proponer
    assert _proponer(client)["acciones"] == []


def test_sin_cuerpo_aplica_como_siempre(bastidor):
    client, doc, _, _ = bastidor
    r = client.post("/api/assembly/declare")
    assert r.status_code == 200 and "features" in r.json()
    assert doc.grounds and doc.fasteners


def test_las_acciones_entran_tal_cual_a_un_lote(bastidor):
    """`a_revisar`/`motivo` van fuera de `params`: el lote del agente las ignora."""
    client, doc, _, _ = bastidor
    prop = _proponer(client)
    r = client.post("/api/commands/batch", json={"actions": prop["acciones"]})
    assert r.status_code == 200, r.text
    assert len(doc.fasteners) == prop["n_fasteners"] and len(doc.grounds) == prop["n_grounds"]


def test_resumen_agrupa_por_raiz_y_omite_lo_declarado_en_lote():
    doc = Document("declarar-patron")
    base = _box(doc, "Base", x=500, z=10, w=1000, h=20)
    poste = _box(doc, "Poste", x=50, z=120, w=40, h=200)
    patron = doc.execute("pattern_linear", {"feature": poste, "count": 4,
                                            "spacing": {"x": 100, "y": 0, "z": 0}})
    api.DOC = doc
    client = TestClient(api.app)

    prop = _proponer(client)
    filas = {(f["a"], f["b"]): f for f in prop["resumen"]}
    copias = filas[tuple(sorted((base, patron)))]
    # poste a tope sobre la base: marco soldado (criterio de taller, D6 de mcp-sin-friccion)
    assert copias["n"] == 3 and copias["kind"] == "soldadura" and "a_revisar" not in copias
    assert "Base" in copias["ejemplo"]["nombres"]
    assert any(n.startswith("Poste") for n in copias["ejemplo"]["nombres"])
    assert filas[tuple(sorted((base, poste)))]["n"] == 1  # la fuente no es de la raíz
    assert prop["resumen"][0]["n"] == 3  # de mayor a menor

    # declarar la fila en UN fasten por conjunto → la propuesta ya no la repite
    doc.execute("fasten", {"name": "postes", "a": base, "b": patron, "kind": "soldadura"})
    prop2 = _proponer(client)
    pares = {frozenset((a["params"]["a"], a["params"]["b"]))
             for a in prop2["acciones"] if a["type"] == "fasten"}
    assert pares == {frozenset((base, poste))}
    assert not any(a["params"]["name"].startswith("postes") for a in prop2["acciones"])
