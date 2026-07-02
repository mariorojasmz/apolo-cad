"""Sub-ensamblajes de primera clase (V5.2, Fase 0): grupos por command_ids,
derivación de feat.group, nesting, tolerancia e integración con el log."""

from __future__ import annotations

import pytest

from apolo.assembly.groups import (
    GroupError,
    assign_feature_groups,
    group_features,
    missing_members,
    register_group,
)
from apolo.doc.document import Document, DocumentError


def _box(doc, name, x=0.0):
    return doc.execute("create_box", {"name": name, "width": 50, "depth": 50, "height": 50,
                                      "position": {"x": x, "y": 0, "z": 0}})


def _cmd_of(doc, fid):
    return doc.scene[fid].command_id


# ------------------------------------------------------------- registro puro
def test_register_and_validations():
    groups: dict = {}
    register_group(groups, "g1", {"name": "Base", "members": ["c1", "c2"]})
    assert groups["Base"]["members"] == ["c1", "c2"]
    with pytest.raises(GroupError):  # nombre duplicado
        register_group(groups, "g2", {"name": "Base", "members": ["c3"]})
    with pytest.raises(GroupError):  # member en dos grupos
        register_group(groups, "g3", {"name": "Otro", "members": ["c2"]})
    with pytest.raises(GroupError):  # parent inexistente
        register_group(groups, "g4", {"name": "Hijo", "members": ["c9"], "parent": "NoExiste"})
    with pytest.raises(GroupError):  # sin members
        register_group(groups, "g5", {"name": "Vacio", "members": []})


# ------------------------------------------------------- comando + derivación
def test_create_group_derives_feature_group():
    doc = Document("t")
    a = _box(doc, "A")
    b = _box(doc, "B", 100)
    c = _box(doc, "C", 200)
    doc.execute("create_group", {"name": "Bastidor", "members": [_cmd_of(doc, a), _cmd_of(doc, b)]})
    assert doc.groups["Bastidor"]["members"] == [a, b]
    assert doc.scene[a].group == "Bastidor"
    assert doc.scene[b].group == "Bastidor"
    assert doc.scene[c].group is None


def test_group_survives_pattern_count_edit():
    # la membresía es por COMMAND_ID: las instancias nuevas de un patrón editado
    # caen dentro del grupo solas
    doc = Document("t")
    a = _box(doc, "A")
    pat = doc.execute("pattern_linear", {"feature": a, "count": 3,
                                         "spacing": {"x": 100, "y": 0, "z": 0}})
    doc.execute("create_group", {"name": "Fila", "members": [a, pat]})
    en_grupo = group_features(doc.scene, doc.groups, "Fila")
    assert len(en_grupo) == 3  # original + 2 copias
    doc.edit(pat, {"feature": a, "count": 5, "spacing": {"x": 100, "y": 0, "z": 0}})
    en_grupo = group_features(doc.scene, doc.groups, "Fila")
    assert len(en_grupo) == 5  # las 2 nuevas entraron solas


def test_nesting_recursive_and_direct_membership():
    doc = Document("t")
    a = _box(doc, "A")
    b = _box(doc, "B", 100)
    doc.execute("create_group", {"name": "Padre", "members": [a]})
    doc.execute("create_group", {"name": "Hijo", "members": [b], "parent": "Padre"})
    # recursivo: el padre incluye las piezas del hijo
    assert set(group_features(doc.scene, doc.groups, "Padre")) == {a, b}
    assert set(group_features(doc.scene, doc.groups, "Padre", recursive=False)) == {a}
    # feat.group = membresía DIRECTA
    assert doc.scene[b].group == "Hijo"


def test_parent_must_be_declared_before():
    doc = Document("t")
    a = _box(doc, "A")
    with pytest.raises(DocumentError):
        doc.execute("create_group", {"name": "Hijo", "members": [a], "parent": "NoDeclarado"})


def test_role_is_stored():
    doc = Document("t")
    a = _box(doc, "A")
    doc.execute("create_group", {"name": "Patas", "members": [a], "role": "estructura"})
    assert doc.groups["Patas"]["role"] == "estructura"


# --------------------------------------------------------- integridad tolerante
def test_missing_member_does_not_fail_and_is_reported():
    doc = Document("t")
    a = _box(doc, "A")
    b = _box(doc, "B", 100)
    doc.execute("create_group", {"name": "G", "members": [a, b]})
    doc.remove_commands([b])  # el comando desaparece; el grupo NO rompe el regenerate
    assert "G" in doc.groups
    gone = missing_members(doc.scene, doc.groups)
    assert gone == {"G": [b]}
    assert doc.scene[a].group == "G"


# --------------------------------------------------------------- log/persistencia
def test_roundtrip_apolo_and_undo_redo():
    doc = Document("t")
    a = _box(doc, "A")
    doc.execute("create_group", {"name": "G", "members": [a], "role": "estructura"})
    doc2 = Document.from_apolo_bytes(doc.to_apolo_bytes())
    assert doc2.groups["G"]["role"] == "estructura"
    assert doc2.scene[a].group == "G"
    doc.undo()
    assert doc.groups == {} and doc.scene[a].group is None
    doc.redo()
    assert doc.scene[a].group == "G"


def test_incremental_regenerate_preserves_groups():
    # crear >16 comandos (checkpoints) + grupo; editar un comando TEMPRANO fuerza
    # replay incremental desde checkpoint → los grupos deben sobrevivir idénticos
    doc = Document("t")
    fids = [_box(doc, f"P{i}", x=i * 100) for i in range(20)]
    doc.execute("create_group", {"name": "Fila", "members": [fids[5], fids[6]]})
    doc.edit(fids[0], {"name": "P0 editada", "width": 60, "depth": 50, "height": 50,
                       "position": {"x": 0, "y": 0, "z": 0}})
    assert doc.scene[fids[5]].group == "Fila"
    assert doc.scene[fids[6]].group == "Fila"
    assert doc.groups["Fila"]["members"] == [fids[5], fids[6]]


def test_group_schema_exposed():
    from apolo.commands.registry import command_schemas

    entry = command_schemas("create_group")
    assert entry and entry[0]["category"] == "ensamblaje"
    assert "members" in entry[0]["schema"]["properties"]


def test_double_membership_rejected_via_command():
    doc = Document("t")
    a = _box(doc, "A")
    doc.execute("create_group", {"name": "G1", "members": [a]})
    with pytest.raises(DocumentError):
        doc.execute("create_group", {"name": "G2", "members": [a]})


# ------------------------------------------------------------ transform_group (F1)
def _bbox(doc, fid):
    bb = doc.scene[fid].shape.bounding_box()
    return (round(bb.min.X, 3), round(bb.min.Y, 3), round(bb.min.Z, 3),
            round(bb.max.X, 3), round(bb.max.Y, 3), round(bb.max.Z, 3))


def test_transform_group_translates_all_members():
    doc = Document("t")
    a = _box(doc, "A")
    b = _box(doc, "B", 100)
    c = _box(doc, "C", 500)  # fuera del grupo
    doc.execute("create_group", {"name": "G", "members": [a, b]})
    b0_a, b0_c = _bbox(doc, a), _bbox(doc, c)
    doc.execute("transform_group", {"group": "G", "translate": {"x": 50, "y": 0, "z": 0}})
    assert _bbox(doc, a)[0] == pytest.approx(b0_a[0] + 50)
    assert _bbox(doc, c) == b0_c  # el de fuera NO se mueve


def test_transform_group_rotates_about_group_center():
    # dos cajas en x=0 y x=200; rotar 180° sobre Z alrededor del centro CONJUNTO
    # (x=100) las INTERCAMBIA de sitio — rotar cada una sobre sí misma no lo haría
    doc = Document("t")
    a = _box(doc, "A", 0)
    b = _box(doc, "B", 200)
    doc.execute("create_group", {"name": "G", "members": [a, b]})
    doc.execute("transform_group", {"group": "G", "rotate": {"x": 0, "y": 0, "z": 180}})
    bb_a = doc.scene[a].shape.bounding_box()
    assert (bb_a.min.X + bb_a.max.X) / 2 == pytest.approx(200, abs=1e-6)


def test_transform_group_roundtrip_identity():
    doc = Document("t")
    a = _box(doc, "A")
    doc.execute("create_group", {"name": "G", "members": [a]})
    b0 = _bbox(doc, a)
    doc.execute("transform_group", {"group": "G", "translate": {"x": 50, "y": -30, "z": 10},
                                    "rotate": {"x": 0, "y": 0, "z": 90}})
    doc.execute("transform_group", {"group": "G", "rotate": {"x": 0, "y": 0, "z": -90}})
    doc.execute("transform_group", {"group": "G", "translate": {"x": -50, "y": 30, "z": -10}})
    b1 = _bbox(doc, a)
    for v0, v1 in zip(b0, b1):
        assert v1 == pytest.approx(v0, abs=1e-6)


def test_transform_group_moves_internal_joint():
    doc = Document("t")
    a = _box(doc, "A")
    b = _box(doc, "B", 100)
    doc.execute("add_joint", {"name": "j1", "type": "giratoria", "parent": a, "child": b,
                              "origin": {"x": 50, "y": 0, "z": 0},
                              "axis": {"x": 0, "y": 0, "z": 1}})
    doc.execute("create_group", {"name": "G", "members": [a, b]})
    doc.execute("transform_group", {"group": "G", "translate": {"x": 0, "y": 200, "z": 0}})
    assert doc.joints["j1"]["origin"][1] == pytest.approx(200)
    assert doc.joints["j1"]["axis"] == [0, 0, 1] or doc.joints["j1"]["axis"][2] == pytest.approx(1)


def test_transform_group_rejects_boundary_joint():
    doc = Document("t")
    a = _box(doc, "A")
    b = _box(doc, "B", 100)
    doc.execute("add_joint", {"name": "j1", "type": "giratoria", "parent": a, "child": b,
                              "origin": {"x": 50, "y": 0, "z": 0},
                              "axis": {"x": 0, "y": 0, "z": 1}})
    doc.execute("create_group", {"name": "G", "members": [a]})  # b queda FUERA
    with pytest.raises(DocumentError, match="frontera"):
        doc.execute("transform_group", {"group": "G", "translate": {"x": 10, "y": 0, "z": 0}})


def test_transform_group_moves_nested_children():
    doc = Document("t")
    a = _box(doc, "A")
    b = _box(doc, "B", 100)
    doc.execute("create_group", {"name": "Padre", "members": [a]})
    doc.execute("create_group", {"name": "Hijo", "members": [b], "parent": "Padre"})
    doc.execute("transform_group", {"group": "Padre", "translate": {"x": 0, "y": 0, "z": 75}})
    assert _bbox(doc, b)[2] == pytest.approx(-25 + 75)  # caja centrada en z=0 → min -25


def test_transform_group_unknown_group():
    doc = Document("t")
    _box(doc, "A")
    with pytest.raises(DocumentError, match="No existe el grupo"):
        doc.execute("transform_group", {"group": "Nada", "translate": {"x": 1, "y": 0, "z": 0}})


def test_transform_group_accepts_expressions():
    doc = Document("t")
    doc.execute("set_variable", {"name": "paso", "expression": "120"})
    a = _box(doc, "A")
    doc.execute("create_group", {"name": "G", "members": [a]})
    doc.execute("transform_group", {"group": "G", "translate": {"x": "=paso/2", "y": 0, "z": 0}})
    assert _bbox(doc, a)[0] == pytest.approx(-25 + 60)


# ------------------------------------------------------------ exposición API (F2)
from fastapi.testclient import TestClient

import apolo.api.main as api


def _api_doc():
    doc = Document("grupos-api")
    a = doc.execute("create_box", {"name": "A", "width": 50, "depth": 50, "height": 50})
    b = doc.execute("create_box", {"name": "B", "width": 50, "depth": 50, "height": 50,
                                   "position": {"x": 200, "y": 0, "z": 0}})
    doc.execute("create_group", {"name": "MiGrupo", "members": [a], "role": "estructura"})
    api.DOC = doc
    return doc, a, b


def test_scene_payload_exposes_group():
    doc, a, b = _api_doc()
    client = TestClient(api.app)
    data = client.get("/api/scene").json()
    by_id = {f["id"]: f for f in data["features"]}
    assert by_id[a]["group"] == "MiGrupo"
    assert by_id[b]["group"] is None
    groups = data["document"]["groups"]
    assert groups and groups[0]["name"] == "MiGrupo" and groups[0]["role"] == "estructura"
    assert groups[0]["missing_members"] == []


def test_groups_endpoint():
    _api_doc()
    client = TestClient(api.app)
    r = client.get("/api/groups")
    assert r.status_code == 200
    assert r.json()["groups"][0]["name"] == "MiGrupo"


def test_render_isolate_accepts_group_name():
    doc, a, b = _api_doc()
    client = TestClient(api.app)
    r = client.get("/api/render.png", params={"isolate": "MiGrupo", "shade": False})
    assert r.status_code == 200
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_isolate_group_plus_id():
    doc, a, b = _api_doc()
    client = TestClient(api.app)
    r = client.get("/api/render.png", params={"isolate": f"MiGrupo,{b}", "shade": False})
    assert r.status_code == 200


def test_drawing_spec_isolate_accepts_group():
    _api_doc()
    client = TestClient(api.app)
    r = client.post("/api/drawing/spec", json={"isolate": ["MiGrupo"], "format": "svg"})
    assert r.status_code == 200
    assert b"<svg" in r.content[:200]


# ------------------------------------------------------- consumidores (F3)
def test_bom_by_group_splits_and_default_identical():
    from apolo.library.bom import bom_from_scene

    doc = Document("t")
    a = doc.execute("insert_component", {"component": "6207", "position": {"x": 0, "y": 0, "z": 0}})
    b = doc.execute("insert_component", {"component": "6207", "position": {"x": 100, "y": 0, "z": 0}})
    doc.execute("create_group", {"name": "Cola", "members": [a]})
    plain = bom_from_scene(doc.scene)
    assert len(plain) == 1 and plain[0]["cantidad"] == 2  # default: byte-idéntico
    assert "grupo" not in plain[0]
    grouped = bom_from_scene(doc.scene, by_group=True)
    assert len(grouped) == 2  # mismo rodamiento, grupos distintos → filas separadas
    grupos = sorted(((r.get("grupo") or "", r["cantidad"]) for r in grouped))
    assert grupos == [("", 1), ("Cola", 1)]


def test_assembly_steps_one_step_per_group():
    from apolo.drawing.assembly_manual import assembly_steps
    from apolo.library.catalog import CATALOG

    doc = Document("t")
    a = _box(doc, "Larguero A")
    b = _box(doc, "Larguero B", 100)
    c = _box(doc, "Motor X", 300)
    doc.execute("create_group", {"name": "Bastidor", "members": [a, b]})
    steps = assembly_steps(doc.scene, doc.commands, CATALOG)
    labels = [s["label"] for s in steps]
    assert "Bastidor" in labels
    bastidor = next(s for s in steps if s["label"] == "Bastidor")
    assert set(bastidor["ids"]) == {a, b}
    # el no agrupado sigue con la heurística de siempre
    assert any(c in s["ids"] for s in steps if s["label"] != "Bastidor")


# ------------------------------------------------------------- auto_group (F4)
def test_propose_groups_by_heuristic():
    from apolo.assembly.grouping import propose_groups
    from apolo.library.catalog import CATALOG

    doc = Document("t")
    larguero = _box(doc, "Larguero A36")
    motor = _box(doc, "Motorreductor X", 200)
    rod = doc.execute("insert_component", {"component": "6207", "position": {"x": 400, "y": 0, "z": 0}})
    misterio = _box(doc, "Zzqx", 600)  # sin señal → queda sin agrupar
    prop = propose_groups(doc.scene, doc.commands, CATALOG, doc.groups)
    by_name = {p["name"]: p for p in prop}
    assert by_name["Estructura"]["members"] == [larguero]
    assert by_name["Estructura"]["role"] == "estructura"
    assert by_name["Transmision"]["members"] == [motor]
    assert by_name["Rodamientos"]["members"] == [rod]
    assert all(misterio not in p["members"] for p in prop)


def test_auto_group_endpoint_dry_run_and_apply():
    from apolo.library.bom import bom_from_scene  # noqa: F401 (import sanity)

    doc = Document("auto-grp")
    a = doc.execute("create_box", {"name": "Larguero A36", "width": 50, "depth": 50, "height": 50})
    api.DOC = doc
    client = TestClient(api.app)
    r = client.post("/api/assembly/auto-group", json={"dry_run": True})
    assert r.status_code == 200
    assert r.json()["proposal"][0]["name"] == "Estructura"
    assert doc.groups == {}  # dry_run NO muta
    r2 = client.post("/api/assembly/auto-group", json={"dry_run": False})
    assert r2.status_code == 200 and r2.json()["created"] == 1
    assert doc.scene[a].group == "Estructura"
    # idempotencia: re-correr no duplica ni falla
    r3 = client.post("/api/assembly/auto-group", json={"dry_run": False})
    assert r3.status_code == 200 and r3.json()["created"] == 0


def test_auto_group_skips_already_grouped():
    from apolo.assembly.grouping import propose_groups
    from apolo.library.catalog import CATALOG

    doc = Document("t")
    a = _box(doc, "Larguero A36")
    doc.execute("create_group", {"name": "MiEstructura", "members": [a]})
    prop = propose_groups(doc.scene, doc.commands, CATALOG, doc.groups)
    assert all(a not in p["members"] for p in prop)
