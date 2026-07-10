"""V6.5c · verify: aserciones numéricas en lote (distancia/volumen/bbox/sin_interferencia/
existe) — el agente declara invariantes y las comprueba en UNA llamada, no con aritmética
mental encadenando measures."""

from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.library.verify import run_verify


def _scene():
    """A (100³ en 0), B (100³ en x=300, gap 200), grupo G = {A,B}."""
    doc = Document("verify")
    a = doc.execute("create_box", {"name": "Caja A", "width": 100, "depth": 100, "height": 100})
    b = doc.execute("create_box", {"name": "Caja B", "width": 100, "depth": 100, "height": 100,
                                   "position": {"x": 300}})
    doc.execute("create_group", {"name": "G", "members": [a, b]})
    return doc, a, b


def _run(doc, checks):
    api.DOC = doc
    return TestClient(api.app).post("/api/verify", json={"checks": checks}).json()


def test_distancia_pass_and_fail():
    doc, a, b = _scene()
    out = _run(doc, [
        {"tipo": "distancia", "a": a, "b": b, "max": 250},   # 200 ≤ 250 → ok
        {"tipo": "distancia", "a": a, "b": b, "min": 250},   # 200 ≥ 250 → falla
        {"tipo": "distancia", "a": a, "b": b, "entre": [150, 250]},  # ok
    ])
    res = out["resultados"]
    assert res[0]["ok"] is True and res[0]["actual"] == 200.0
    assert res[1]["ok"] is False
    assert res[2]["ok"] is True
    assert out["ok"] is False  # el lote falla si alguna falla


def test_volumen_id_and_group():
    doc, a, b = _scene()
    out = _run(doc, [
        {"tipo": "volumen", "id": a, "entre": [900000, 1100000]},   # 1e6
        {"tipo": "volumen", "grupo": "G", "min": 1900000},          # 2e6 (suma del grupo)
    ])
    res = out["resultados"]
    assert res[0]["ok"] is True and abs(res[0]["actual"] - 1e6) < 1
    assert res[1]["ok"] is True and res[1]["n_piezas"] == 2


def test_bbox_axis():
    doc, a, b = _scene()
    out = _run(doc, [
        {"tipo": "bbox", "id": a, "eje": "x", "entre": [99, 101]},   # A mide 100 en x
        {"tipo": "bbox", "grupo": "G", "eje": "x", "entre": [399, 401]},  # de -50 a 350 = 400
    ])
    res = out["resultados"]
    assert res[0]["ok"] is True
    assert res[1]["ok"] is True and abs(res[1]["actual"] - 400.0) < 0.5


def test_sin_interferencia_pass_and_fail():
    doc, a, b = _scene()
    # sin choques → ok
    ok = _run(doc, [{"tipo": "sin_interferencia", "ids": ["G"]}])["resultados"][0]
    assert ok["ok"] is True and ok["actual"] == 0
    # añadir una caja que solapa A → falla y reporta la colisión
    c = doc.execute("create_box", {"name": "Choque", "width": 40, "depth": 40, "height": 40,
                                   "position": {"x": 20}})
    bad = _run(doc, [{"tipo": "sin_interferencia", "ids": [a]}])["resultados"][0]
    assert bad["ok"] is False and bad["actual"] >= 1
    assert bad["colisiones"] and {bad["colisiones"][0]["a"], bad["colisiones"][0]["b"]} == {a, c}


def test_existe_id_and_name():
    doc, a, b = _scene()
    out = _run(doc, [
        {"tipo": "existe", "id": a},
        {"tipo": "existe", "id": "no_existe"},
        {"tipo": "existe", "name": "caja"},   # substring case-insensitive → A y B
        {"tipo": "existe", "name": "zzz"},
    ])
    res = out["resultados"]
    assert res[0]["ok"] is True
    assert res[1]["ok"] is False
    assert res[2]["ok"] is True and res[2]["actual"] == 2
    assert res[3]["ok"] is False


def test_unknown_type_and_bad_ref_dont_crash_batch():
    doc, a, b = _scene()
    out = _run(doc, [
        {"tipo": "distancia", "a": a, "b": "fantasma", "max": 10},  # ref inválida
        {"tipo": "marciano"},                                       # tipo desconocido
        {"tipo": "existe", "id": a},                                # sigue funcionando
    ])
    res = out["resultados"]
    assert res[0]["ok"] is False and "inexistente" in res[0]["error"]
    assert res[1]["ok"] is False and "desconocido" in res[1]["error"]
    assert res[2]["ok"] is True


def test_run_verify_pure_is_read_only():
    """La función pura no muta la escena (la firma del log queda intacta)."""
    doc, a, b = _scene()
    before = list(doc.commands)
    out = run_verify(
        doc.scene,
        [{"tipo": "distancia", "a": a, "b": b, "max": 250}],
        expand=lambda v: v if isinstance(v, list) else [v],
        interference_fn=lambda focus: [],
    )
    assert out[0]["ok"] is True
    assert doc.commands == before  # read-only
