"""Bastidor soldado / weldment (V3 bloque #5): generador de estructura de
perfiles con lista de corte (BOM) y cordones."""
import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.commands.registry import CommandError
from apolo.doc import Document, DocumentError
from apolo.library.bom import bom_from_scene
from apolo.library.checks import interference_report, same_command_pairs


def _members(doc):
    return [f for f in doc.scene.values() if f.name.startswith("Bastidor")]


def test_weldment_member_count():
    d = Document()
    d.execute("create_weldment", {"ancho": 800, "fondo": 600, "alto": 900,
                                  "perfil": "PERFIL-4040", "cordones": False})
    posts = [f for f in d.scene.values() if "Poste" in f.name]
    rails = [f for f in d.scene.values() if "Larguero" in f.name or "Travesaño" in f.name]
    assert len(posts) == 4
    assert len(rails) == 8  # 2 anillos (sup+inf) × 4 miembros


def test_weldment_cut_list():
    d = Document()
    d.execute("create_weldment", {"ancho": 800, "fondo": 600, "alto": 900,
                                  "perfil": "PERFIL-4040", "cordones": False})
    rows = {(r["ref"], r["longitud_mm"]): r["cantidad"] for r in bom_from_scene(d.scene)}
    assert rows[("PERFIL-4040", 900.0)] == 4    # postes
    assert rows[("PERFIL-4040", 720.0)] == 4    # largueros X: 800 - 2·40
    assert rows[("PERFIL-4040", 520.0)] == 4    # travesaños Y: 600 - 2·40


def test_weldment_intermediate_rings():
    d = Document()
    d.execute("create_weldment", {"ancho": 800, "fondo": 600, "alto": 1200,
                                  "perfil": "PERFIL-4040", "anillos_intermedios": 1, "cordones": False})
    rails = [f for f in d.scene.values() if "Larguero" in f.name or "Travesaño" in f.name]
    assert len(rails) == 12  # 3 anillos × 4


def test_weldment_beads_toggle():
    d = Document()
    d.execute("create_weldment", {"ancho": 800, "fondo": 600, "alto": 900,
                                  "perfil": "PERFIL-4040", "cordones": True})
    beads = [f for f in d.scene.values() if f.name.endswith("Cordón")]
    assert len(beads) == 8  # 4 esquinas × 2 anillos


def test_weldment_no_self_interference():
    """Los miembros/cordones del bastidor no deben reportarse como colisión."""
    d = Document()
    d.execute("create_weldment", {"ancho": 800, "fondo": 600, "alto": 900,
                                  "perfil": "PERFIL-4040", "cordones": True})
    report = interference_report(d.scene, exclude_pairs=same_command_pairs(d))
    assert report["interferencias"] == []


def test_weldment_parametric_edit():
    d = Document()
    cid = d.execute("create_weldment", {"ancho": 800, "fondo": 600, "alto": 900, "perfil": "PERFIL-4040"})
    post_z = lambda: next(f for f in d.scene.values() if "Poste" in f.name).shape.bounding_box().size.Z
    assert post_z() == pytest.approx(900, abs=1)
    d.edit(cid, {"ancho": 800, "fondo": 600, "alto": 1200, "perfil": "PERFIL-4040"})
    assert post_z() == pytest.approx(1200, abs=1)


def test_weldment_validations():
    d = Document()
    with pytest.raises((CommandError, DocumentError)):
        d.execute("create_weldment", {"ancho": 50, "fondo": 600, "alto": 900, "perfil": "PERFIL-4040"})
    with pytest.raises((CommandError, DocumentError)):
        d.execute("create_weldment", {"ancho": 800, "fondo": 600, "alto": 900, "perfil": "NO-EXISTE"})
    assert d.commands == []


def test_weldment_api_and_checks():
    api.DOC = Document("weld-test")
    client = TestClient(api.app)
    r = client.post("/api/commands", json={"type": "create_weldment", "params": {
        "ancho": 800, "fondo": 600, "alto": 900, "perfil": "PERFIL-4545", "cordones": True}})
    assert r.status_code == 200
    bom = client.get("/api/bom").json()
    assert any(row["ref"] == "PERFIL-4545" for row in bom)
    checks = client.post("/api/checks", json={}).json()
    assert checks["interferencias"]["interferencias"] == []  # same_command_pairs excluye
