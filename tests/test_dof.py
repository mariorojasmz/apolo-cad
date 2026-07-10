"""Reporte de grados de libertad del ensamblaje (V6.3c) — conteo Grübler determinista."""
import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.assembly.dof import dof_report
from apolo.doc import Document


def _report(d: Document, **kw) -> dict:
    return dof_report(d.scene, d.joints, d.mates, d.grounds, **kw)


def _by_id(rep: dict) -> dict:
    return {f["id"]: f for f in rep["features"]}


def _two_boxes(d):
    a = d.execute("create_box", {"name": "A", "width": 100, "depth": 100, "height": 40})
    b = d.execute("create_box", {"name": "B", "width": 40, "depth": 40, "height": 40,
                                 "position": {"x": 300, "y": 0, "z": 200}})
    return a, b


# ------------------------------------------------------------- cuerpo libre / ground
def test_pieza_suelta_es_libre():
    """Consistencia con soundness: una pieza sin NADA = 6 GDL (libre, = 'floating')."""
    d = Document()
    a = d.execute("create_box", {"name": "A"})
    rep = _report(d)
    f = _by_id(rep)[a]
    assert f["dof"] == 6 and f["estado"] == "libre" and f["restringido_por"] == []
    assert rep["libres"] == 1 and rep["total_dof"] == 6


def test_ground_fija():
    d = Document()
    a = d.execute("create_box", {"name": "A"})
    d.execute("ground", {"name": "g", "feature": a})
    f = _by_id(_report(d))[a]
    assert f["dof"] == 0 and f["estado"] == "fijo"
    assert "tierra:g" in f["restringido_por"]


# ------------------------------------------------------------------- juntas
@pytest.mark.parametrize("tipo,dof_esp", [("fija", 0), ("giratoria", 1), ("continua", 1), ("prismatica", 1)])
def test_junta_por_tipo(tipo, dof_esp):
    d = Document()
    a = d.execute("create_box", {"name": "A"})
    b = d.execute("create_box", {"name": "B", "position": {"x": 200}})
    d.execute("add_joint", {"name": "j", "type": tipo, "parent": a, "child": b,
                            "axis": {"x": 0, "y": 0, "z": 1}, "lower": 0, "upper": 90})
    f = _by_id(_report(d))[b]
    assert f["dof"] == dof_esp
    assert f["estado"] == ("fijo" if dof_esp == 0 else "parcial")
    assert "junta:j" in f["restringido_por"]


# ------------------------------------------------------------------- mates
@pytest.mark.parametrize("tipo,dof_esp", [
    ("coincidente", 3), ("distancia", 3), ("concentrico", 2), ("paralelo", 4), ("angulo", 5)])
def test_mate_por_tipo(tipo, dof_esp):
    d = Document()
    a, b = _two_boxes(d)
    d.execute("add_mate", {"name": "m", "type": tipo, "feature_a": a, "feature_b": b,
                           "ref_a": {"mode": "cara", "face": "tope"},
                           "ref_b": {"mode": "cara", "face": "base"}, "value": 10})
    fa, fb = _by_id(_report(d))[a], _by_id(_report(d))[b]
    assert fb["dof"] == dof_esp and fb["estado"] == "parcial"
    assert "mate:m" in fb["restringido_por"]
    assert fa["dof"] == 6  # A (base) no lo restringe el mate


# ----------------------------------------------------------- cadena junta + mate
def test_cadena_junta_mas_mate():
    """Un hijo de junta giratoria (−5) + un mate paralelo (−2) → 7 removidos → sobre_restringido."""
    d = Document()
    a, b = _two_boxes(d)
    d.execute("add_joint", {"name": "j", "type": "giratoria", "parent": a, "child": b,
                            "axis": {"x": 0, "y": 0, "z": 1}})
    d.execute("add_mate", {"name": "m", "type": "paralelo", "feature_a": a, "feature_b": b,
                           "ref_a": {"mode": "cara", "face": "tope"},
                           "ref_b": {"mode": "cara", "face": "base"}})
    f = _by_id(_report(d))[b]
    assert f["estado"] == "sobre_restringido"
    assert "junta:j" in f["restringido_por"] and "mate:m" in f["restringido_por"]


# --------------------------------------------------------------- sobre-restringido
def test_sobre_restringido_por_conteo():
    """coincidente (−3) + concéntrico (−4) = 7 > 6 → sobre_restringido por conteo."""
    d = Document()
    a, b = _two_boxes(d)
    d.execute("add_mate", {"name": "m1", "type": "coincidente", "feature_a": a, "feature_b": b,
                           "ref_a": {"mode": "cara", "face": "tope"},
                           "ref_b": {"mode": "cara", "face": "base"}})
    # 2º mate concéntrico contra un cilindro (cara cilíndrica); B es hijo de ambos
    c = d.execute("create_cylinder", {"name": "C", "radius": 8, "height": 200, "axis": "z",
                                      "position": {"x": 300, "y": 0, "z": 20}})
    d.execute("drill_hole", {"feature": b, "position": {"x": 300, "y": 0, "z": 200},
                             "axis": "z", "diameter": 16.5, "depth": 0})
    d.execute("add_mate", {"name": "m2", "type": "concentrico", "feature_a": c, "feature_b": b,
                           "ref_a": {"mode": "cerca", "point": [308, 0, 20]},
                           "ref_b": {"mode": "cerca", "point": [308.25, 0, 200]}})
    rep = _report(d)
    f = _by_id(rep)[b]
    assert f["estado"] == "sobre_restringido" and f["dof"] == 0
    assert rep["sobre_restringidos"] >= 1


def test_sobre_restringido_por_residuo_del_solver():
    """El residuo que expone el solver (pasado en `overconstrained`) marca sobre_restringido
    aunque el conteo no llegue a 6 (una pieza con un solo mate)."""
    d = Document()
    a, b = _two_boxes(d)
    d.execute("add_mate", {"name": "m", "type": "coincidente", "feature_a": a, "feature_b": b,
                           "ref_a": {"mode": "cara", "face": "tope"},
                           "ref_b": {"mode": "cara", "face": "base"}})
    f = _by_id(_report(d, overconstrained={b}))[b]
    assert f["estado"] == "sobre_restringido"


# --------------------------------------------------------------- payload / API
def test_payload_contrato():
    d = Document()
    a = d.execute("create_box", {"name": "A"})
    d.execute("ground", {"name": "g", "feature": a})
    rep = _report(d)
    assert set(rep) == {"features", "total_dof", "libres", "sobre_restringidos", "resumen", "nota"}
    assert set(rep["features"][0]) == {"id", "name", "dof", "estado", "restringido_por"}
    assert isinstance(rep["resumen"], str) and "GDL" in rep["resumen"]
    assert "heurístico" in rep["nota"].lower() or "grübler" in rep["nota"].lower()


def test_guias_excluidas():
    """Un boceto-guía (blockout) NO es pieza del ensamblaje → cubre la rama dof.py:54-55."""
    d = Document()
    real = d.execute("create_box", {"name": "real"})
    guia = d.execute("create_box", {"name": "guia", "position": {"x": 300}})
    d.set_sketch_guide(guia, True)  # marca la 2ª caja como boceto-guía
    rep = _report(d)
    ids = {f["id"] for f in rep["features"]}
    assert ids == {real}  # la guía quedó fuera del reporte
    assert len(rep["features"]) == 1


def test_api_dof_endpoint():
    api.DOC = Document("dof-api")
    client = TestClient(api.app)
    a = client.post("/api/commands", json={"type": "create_box", "params": {"name": "A"}}).json()
    a_id = a["features"][0]["id"]
    client.post("/api/commands", json={"type": "create_box",
                                       "params": {"name": "B", "position": {"x": 200}}})
    r = client.get("/api/assembly/dof")
    assert r.status_code == 200
    payload = r.json()
    assert payload["total_dof"] == 12 and payload["libres"] == 2
    assert {f["id"] for f in payload["features"]} >= {a_id}
