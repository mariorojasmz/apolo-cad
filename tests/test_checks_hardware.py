"""T2: la tornillería/rodamientos asentados en su alojamiento se excluyen del
chequeo de interferencias (convención estándar para piezas normalizadas)."""
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.library.checks import hardware_ids, interference_report


def _scene_with_bolt_in_overlap():
    """Caja A solapa caja B (choque real) + tornillo embebido en ambas."""
    d = Document()
    a = d.execute("create_box", {"width": 100, "depth": 100, "height": 100})
    b = d.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": 50}})
    bolt = d.execute("insert_component", {"component": "DIN912-M8", "position": {"x": 10}})
    return d, a, b, bolt


def test_hardware_ids_detects_fasteners():
    d, a, b, bolt = _scene_with_bolt_in_overlap()
    hw = hardware_ids(d)
    assert bolt in hw
    assert a not in hw and b not in hw


def test_interference_excludes_hardware():
    d, a, b, bolt = _scene_with_bolt_in_overlap()
    # sin exclusión: se reportan A-B y el tornillo contra A y/o B
    full = interference_report(d.scene)
    assert any(bolt in (c["a"], c["b"]) for c in full["interferencias"])
    # con exclude_ids=hardware: solo queda el choque real A-B, el tornillo desaparece
    clean = interference_report(d.scene, exclude_ids=hardware_ids(d))
    assert not any(bolt in (c["a"], c["b"]) for c in clean["interferencias"])
    assert any({c["a"], c["b"]} == {a, b} for c in clean["interferencias"])


def test_api_checks_excludes_seated_fastener():
    api.DOC = Document("hw-test")
    client = TestClient(api.app)
    client.post("/api/commands", json={"type": "create_box", "params": {
        "width": 100, "depth": 100, "height": 100}})
    # chumacera real (NO es hardware: se chequea) + tornillo embebido (sí excluido)
    client.post("/api/commands", json={"type": "insert_component", "params": {
        "component": "UCP205", "position": {"x": 0, "z": 60}}})
    client.post("/api/commands", json={"type": "insert_component", "params": {
        "component": "DIN912-M8", "position": {"x": 0, "z": 60}}})
    checks = client.post("/api/checks", json={}).json()["interferencias"]
    # el tornillo (DIN912-M8) no debe aparecer en ninguna interferencia
    bolt_ids = {fid for fid, f in api.DOC.scene.items() if f.component == "DIN912-M8"}
    assert not any(c["a"] in bolt_ids or c["b"] in bolt_ids for c in checks["interferencias"])
