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


# ================================================================ V5.8 ingletes
def _bom_key(doc):
    return {(r["ref"], r["longitud_mm"]): r for r in bom_from_scene(doc.scene)}


def test_weldment_retro_candado_default_tope():
    # SIN el parámetro nuevo: BOM byte-idéntico al histórico (logs viejos regeneran igual)
    d = Document()
    d.execute("create_weldment", {"ancho": 800, "fondo": 600, "alto": 900,
                                  "perfil": "PERFIL-4040", "cordones": False})
    rows = _bom_key(d)
    assert rows[("PERFIL-4040", 900.0)]["cantidad"] == 4
    assert rows[("PERFIL-4040", 720.0)]["cantidad"] == 4
    assert rows[("PERFIL-4040", 520.0)]["cantidad"] == 4
    assert all("∠" not in r["descripcion"] for r in rows.values())


def test_weldment_inglete_bom():
    d = Document()
    d.execute("create_weldment", {"ancho": 800, "fondo": 600, "alto": 900,
                                  "perfil": "PERFIL-4040", "cordones": False,
                                  "esquinas": "inglete"})
    rows = _bom_key(d)
    # marcos a longitud EXTERIOR con ∠45/45; postes A TOPE entre marcos
    assert rows[("PERFIL-4040", 800.0)]["cantidad"] == 4
    assert "∠45°/45°" in rows[("PERFIL-4040", 800.0)]["descripcion"]
    assert rows[("PERFIL-4040", 600.0)]["cantidad"] == 4
    assert rows[("PERFIL-4040", 820.0)]["cantidad"] == 4  # alto − 2·sec
    assert "∠" not in rows[("PERFIL-4040", 820.0)]["descripcion"]


def test_weldment_inglete_volumen_ancla():
    # V(miembro ingleteado) = A·span EXACTO (plano bisector por el nodo del eje)
    from apolo.library.catalog import build_component

    A = build_component("PERFIL-4040", 1000)[0].volume / 1000.0
    d = Document()
    d.execute("create_weldment", {"ancho": 800, "fondo": 600, "alto": 900,
                                  "perfil": "PERFIL-4040", "cordones": False,
                                  "esquinas": "inglete"})
    lx = next(f for f in d.scene.values() if "Larguero X (marco" in f.name)
    ty = next(f for f in d.scene.values() if "Travesaño Y (marco" in f.name)
    assert lx.shape.volume == pytest.approx(A * 760, rel=1e-4)   # span = 800 − sec
    assert lx.shape.volume == pytest.approx(A * (800 - 40), rel=1e-4)  # doble check 45/45
    assert ty.shape.volume == pytest.approx(A * 560, rel=1e-4)
    assert lx.miter == (45.0, 45.0)


def test_weldment_inglete_bbox_exterior_exacto():
    d = Document()
    d.execute("create_weldment", {"ancho": 800, "fondo": 600, "alto": 900,
                                  "perfil": "PERFIL-4040", "cordones": False,
                                  "esquinas": "inglete"})
    xs, ys, zs = [], [], []
    for f in d.scene.values():
        bb = f.shape.bounding_box()
        xs += [bb.min.X, bb.max.X]; ys += [bb.min.Y, bb.max.Y]; zs += [bb.min.Z, bb.max.Z]
    assert max(xs) - min(xs) == pytest.approx(800, abs=0.01)  # la punta llega a la esquina
    assert max(ys) - min(ys) == pytest.approx(600, abs=0.01)
    assert max(zs) - min(zs) == pytest.approx(900, abs=0.01)


def test_weldment_inglete_intermedios_a_tope():
    d = Document()
    d.execute("create_weldment", {"ancho": 800, "fondo": 600, "alto": 1200,
                                  "perfil": "PERFIL-4040", "anillos_intermedios": 1,
                                  "cordones": False, "esquinas": "inglete"})
    rows = _bom_key(d)
    assert rows[("PERFIL-4040", 720.0)]["cantidad"] == 2   # anillo intermedio a tope
    assert rows[("PERFIL-4040", 520.0)]["cantidad"] == 2
    assert rows[("PERFIL-4040", 800.0)]["cantidad"] == 4   # marcos sup/inf a inglete


def test_weldment_inglete_no_interference():
    d = Document()
    d.execute("create_weldment", {"ancho": 800, "fondo": 600, "alto": 900,
                                  "perfil": "PERFIL-4040", "cordones": True,
                                  "esquinas": "inglete"})
    report = interference_report(d.scene, exclude_pairs=same_command_pairs(d))
    assert report["interferencias"] == []


def test_weldment_schema_esquinas_enum():
    from apolo.commands.registry import REGISTRY

    schema = REGISTRY["create_weldment"].model.model_json_schema()
    assert schema["properties"]["esquinas"]["enum"] == ["tope", "inglete"]
    assert schema["properties"]["esquinas"]["default"] == "tope"


def test_weldment_cutlist_angulos():
    from apolo.library.cutlist import cut_list

    d = Document()
    d.execute("create_weldment", {"ancho": 800, "fondo": 600, "alto": 900,
                                  "perfil": "PERFIL-4040", "cordones": False,
                                  "esquinas": "inglete"})
    rows = cut_list(d.scene)
    ing = [r for r in rows if r["corte"] == "inglete"]
    rectos = [r for r in rows if r["corte"] == "recto"]
    # el T-slot descompone en varios sólidos por miembro (histórico) — lo que
    # importa: TODA fila de marco lleva 45/45 y las de postes van rectas con None
    assert ing and all(r["angulo_1"] == 45.0 and r["angulo_2"] == 45.0 for r in ing)
    assert rectos and all(r["angulo_1"] is None for r in rectos)
