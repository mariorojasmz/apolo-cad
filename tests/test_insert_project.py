"""insert_project (V5.2b): instanciar un PROYECTO dentro de otro.

Unit (Document puro, sin SQLite): el donante se construye en código y su
`to_apolo_bytes()` es el snapshot; la materialización se puentea con
`host.add_attachment(bytes)` (mismo patrón que los tests de import_step).
API: `api.DOC = Document(...)` + un FakeStore monkeypatcheado en `api.STORE`.
"""

from __future__ import annotations

import pytest

from apolo.doc import subproject
from apolo.doc.document import Document, DocumentError


# ------------------------------------------------------------------- donante
def _build_donor(l_expr: str = "200") -> tuple[bytes, dict]:
    """Donante rico: variable + 4 sólidos + mate + junta + fijador dimensionado +
    anclaje + grupos ANIDADOS + material override."""
    doc = Document("mini-maquina")
    doc.execute("set_variable", {"name": "L", "expression": l_expr})
    base = doc.execute("create_box", {"name": "Base", "width": "=L", "depth": 50, "height": 10})
    torre = doc.execute("create_box", {
        "name": "Torre", "width": 20, "depth": 20, "height": 80,
        "position": {"x": 0, "y": 0, "z": 60},
    })
    panel = doc.execute("create_box", {
        "name": "Panel", "width": 30, "depth": 5, "height": 30,
        "position": {"x": -60, "y": 0, "z": 30},
    })
    rodillo = doc.execute("create_cylinder", {
        "name": "Rodillo", "radius": 10, "height": 60, "axis": "y",
        "position": {"x": 50, "y": 0, "z": 30},
    })
    # mate coincidente: posa la Torre sobre el tope de la Base (min.Z de Torre = 5)
    doc.execute("add_mate", {
        "name": "m_torre", "type": "coincidente", "feature_a": base, "feature_b": torre,
        "ref_a": {"mode": "cara", "face": "tope"}, "ref_b": {"mode": "cara", "face": "base"},
    })
    doc.execute("add_joint", {
        "name": "j_rodillo", "type": "giratoria", "parent": base, "child": rodillo,
        "origin": {"x": 50, "y": 0, "z": 30}, "axis": {"x": 0, "y": 1, "z": 0},
        "lower": 0, "upper": 360,
    })
    doc.execute("fasten", {
        "name": "f_torre", "a": base, "b": torre, "kind": "perno", "size": "M10", "qty": 4,
    })
    doc.execute("ground", {"name": "g_base", "feature": base})
    doc.execute("create_group", {"name": "Estructura", "members": [base, torre], "role": "estructura"})
    doc.execute("create_group", {"name": "Paneles", "members": [panel], "parent": "Estructura"})
    doc.set_material(torre, "aluminio")
    return doc.to_apolo_bytes(), {
        "base": base, "torre": torre, "panel": panel, "rodillo": rodillo,
    }


@pytest.fixture(scope="module")
def donor():
    return _build_donor()


def _host_with(donor_bytes: bytes, **params) -> tuple[Document, str, str]:
    host = Document("layout")
    digest = host.add_attachment(donor_bytes)
    cid = host.execute("insert_project", {"attachment": digest, "name": "M1", **params})
    return host, digest, cid


# --------------------------------------------------------------- emisión básica
def test_basic_emission_prefixed(donor):
    data, ids = donor
    host, _, cid = _host_with(data)
    assert len(host.scene) == 4
    fid_base = f"{cid}_{ids['base']}"
    assert fid_base in host.scene
    feat = host.scene[fid_base]
    assert feat.command_id == f"{cid}_{ids['base']}"
    assert feat.name == "M1 · Base"
    # el material del origen viaja (set_material del donante)
    assert host.scene[f"{cid}_{ids['torre']}"].material == "aluminio"


def test_root_and_internal_groups(donor):
    data, ids = donor
    host, _, cid = _host_with(data)
    assert sorted(host.groups) == ["M1", "M1/Estructura", "M1/Paneles"]
    # raíz: solo los comandos del origen SIN grupo interno (el rodillo)
    assert host.groups["M1"]["members"] == [f"{cid}_{ids['rodillo']}"]
    assert host.groups["M1/Estructura"]["parent"] == "M1"
    assert host.groups["M1/Estructura"]["role"] == "estructura"
    assert host.groups["M1/Paneles"]["parent"] == "M1/Estructura"
    # feat.group derivado
    assert host.scene[f"{cid}_{ids['base']}"].group == "M1/Estructura"
    assert host.scene[f"{cid}_{ids['panel']}"].group == "M1/Paneles"
    assert host.scene[f"{cid}_{ids['rodillo']}"].group == "M1"


def test_mates_are_baked(donor):
    data, ids = donor
    host, _, cid = _host_with(data)
    assert host.mates == {}  # el mate del origen NO se re-registra
    # ...pero su pose SÍ llegó resuelta: la Torre apoya en el tope de la Base (z=5)
    bb = host.scene[f"{cid}_{ids['torre']}"].shape.bounding_box()
    assert bb.min.Z == pytest.approx(5, abs=1e-3)


def test_joints_fasteners_grounds_prefixed(donor):
    data, ids = donor
    host, _, cid = _host_with(data)
    j = host.joints["M1/j_rodillo"]
    assert j["parent"] == f"{cid}_{ids['base']}" and j["child"] == f"{cid}_{ids['rodillo']}"
    f = host.fasteners["M1/f_torre"]
    assert f["size"] == "M10" and f["qty"] == 4  # el dimensionamiento viaja
    assert host.grounds["M1/g_base"]["feature"] == f"{cid}_{ids['base']}"


# ----------------------------------------------------------------- paramétrico
def test_override_changes_geometry(donor):
    data, ids = donor
    host, _, cid = _host_with(data, overrides={"L": 300})
    bb = host.scene[f"{cid}_{ids['base']}"].shape.bounding_box()
    assert bb.max.X - bb.min.X == pytest.approx(300, abs=1e-3)


def test_override_unknown_lists_variables(donor):
    data, _ = donor
    host = Document("layout")
    digest = host.add_attachment(data)
    with pytest.raises(DocumentError, match="no es una variable.*L"):
        host.execute("insert_project", {"attachment": digest, "name": "M1",
                                        "overrides": {"largo_x": 3000}})


def test_override_expr_uses_host_variables(donor):
    data, ids = donor
    host = Document("layout")
    digest = host.add_attachment(data)
    host.execute("set_variable", {"name": "gran", "expression": "350"})
    cid = host.execute("insert_project", {"attachment": digest, "name": "M1",
                                          "overrides": {"L": "=gran"}})
    bb = host.scene[f"{cid}_{ids['base']}"].shape.bounding_box()
    assert bb.max.X - bb.min.X == pytest.approx(350, abs=1e-3)


def test_two_instances_distinct_overrides(donor):
    data, ids = donor
    host = Document("layout")
    digest = host.add_attachment(data)
    c1 = host.execute("insert_project", {"attachment": digest, "name": "A"})
    c2 = host.execute("insert_project", {"attachment": digest, "name": "B",
                                         "overrides": {"L": 400},
                                         "position": {"x": 800, "y": 0, "z": 0}})
    assert len(host.scene) == 8
    w1 = host.scene[f"{c1}_{ids['base']}"].shape.bounding_box()
    w2 = host.scene[f"{c2}_{ids['base']}"].shape.bounding_box()
    assert w1.max.X - w1.min.X == pytest.approx(200, abs=1e-3)
    assert w2.max.X - w2.min.X == pytest.approx(400, abs=1e-3)


# ------------------------------------------------------- colocación y transform
def test_instance_placement_transforms_joint(donor):
    data, ids = donor
    host = Document("layout")
    digest = host.add_attachment(data)
    cid = host.execute("insert_project", {
        "attachment": digest, "name": "M1",
        "position": {"x": 500, "y": 0, "z": 0}, "rotation": {"x": 0, "y": 0, "z": 90},
    })
    # origin de la junta (50,0,30) girado z=90 → (0,50,30), + traslación (500,0,0)
    o = host.joints["M1/j_rodillo"]["origin"]
    assert o[0] == pytest.approx(500, abs=1e-6)
    assert o[1] == pytest.approx(50, abs=1e-6)
    assert o[2] == pytest.approx(30, abs=1e-6)
    # eje (0,1,0) girado z=90 → (-1,0,0)
    a = host.joints["M1/j_rodillo"]["axis"]
    assert a[0] == pytest.approx(-1, abs=1e-9) and a[1] == pytest.approx(0, abs=1e-9)


def test_transform_group_moves_instance(donor):
    data, ids = donor
    host, _, cid = _host_with(data)
    before = host.scene[f"{cid}_{ids['rodillo']}"].shape.bounding_box().min.Y
    host.execute("transform_group", {"group": "M1", "translate": {"x": 0, "y": 250, "z": 0}})
    after = host.scene[f"{cid}_{ids['rodillo']}"].shape.bounding_box().min.Y
    assert after - before == pytest.approx(250, abs=1e-6)
    # la junta interna viajó (nada cruza la frontera por construcción)
    assert host.joints["M1/j_rodillo"]["origin"][1] == pytest.approx(250, abs=1e-6)


# ------------------------------------------------------------------- anclajes
def test_keep_grounds_false_and_edit(donor):
    data, _ = donor
    host, _, cid = _host_with(data, keep_grounds=False)
    assert host.grounds == {}
    host.edit(cid, {"keep_grounds": True}, merge=True)
    assert "M1/g_base" in host.grounds
    host.edit(cid, {"keep_grounds": False}, merge=True)
    assert host.grounds == {}


# -------------------------------------------------------------- ciclo de vida
def test_edit_override_regenerates(donor):
    data, ids = donor
    host, _, cid = _host_with(data)
    host.edit(cid, {"overrides": {"L": 320}}, merge=True)
    bb = host.scene[f"{cid}_{ids['base']}"].shape.bounding_box()
    assert bb.max.X - bb.min.X == pytest.approx(320, abs=1e-3)


def test_remove_cleans_everything(donor):
    data, _ = donor
    host, _, cid = _host_with(data)
    host.remove_commands([cid])
    assert host.scene == {} and host.groups == {} and host.joints == {}
    assert host.fasteners == {} and host.grounds == {}


def test_undo_redo(donor):
    data, _ = donor
    host, _, _ = _host_with(data)
    host.undo()
    assert host.scene == {} and host.groups == {}
    host.redo()
    assert len(host.scene) == 4 and "M1" in host.groups


def test_roundtrip_self_contained(donor):
    data, _ = donor
    host, _, cid = _host_with(data, overrides={"L": 250})
    raw = host.to_apolo_bytes()
    fresh = Document.from_apolo_bytes(raw)  # sin BD: el snapshot va en attachments/
    assert sorted(fresh.scene) == sorted(host.scene)
    assert sorted(fresh.groups) == sorted(host.groups)
    assert "M1/j_rodillo" in fresh.joints


def test_name_collision_rolls_back(donor):
    data, _ = donor
    host, digest, _ = _host_with(data)
    with pytest.raises(DocumentError, match="Ya existe un grupo"):
        host.execute("insert_project", {"attachment": digest, "name": "M1",
                                        "position": {"x": 999, "y": 0, "z": 0}})
    assert len(host.scene) == 4  # rollback total: solo la primera instancia


# ----------------------------------------------------------------- recursión
def _chain(levels: int) -> bytes:
    """Nivel 0 = caja simple; cada nivel superior instancia al anterior."""
    doc = Document("n0")
    doc.execute("create_box", {"name": "N0", "width": 10, "depth": 10, "height": 10})
    data = doc.to_apolo_bytes()
    for i in range(1, levels):
        parent = Document(f"n{i}")
        digest = parent.add_attachment(data)
        parent.execute("insert_project", {"attachment": digest, "name": f"Nivel{i}"})
        data = parent.to_apolo_bytes()
    return data


def test_nested_instance_and_roundtrip():
    data = _chain(2)  # B contiene A
    host = Document("layout")
    digest = host.add_attachment(data)
    cid = host.execute("insert_project", {"attachment": digest, "name": "Anidado"})
    assert len(host.scene) == 1  # la caja del nivel 0, doblemente prefijada
    fid = next(iter(host.scene))
    assert fid.startswith(f"{cid}_")
    fresh = Document.from_apolo_bytes(host.to_apolo_bytes())
    assert sorted(fresh.scene) == sorted(host.scene)


def test_max_depth_exceeded():
    data = _chain(4)
    subproject._CACHE.clear()  # forzar el replay completo (sin atajos de caché)
    host = Document("layout")
    digest = host.add_attachment(data)
    with pytest.raises(DocumentError, match="profundidad"):
        host.execute("insert_project", {"attachment": digest, "name": "Profundo"})


# --------------------------------------------------------------- caché/instancing
def test_cache_and_mesh_sharing(donor):
    data, ids = donor
    subproject._CACHE.clear()
    host = Document("layout")
    digest = host.add_attachment(data)
    c1 = host.execute("insert_project", {"attachment": digest, "name": "A"})
    c2 = host.execute("insert_project", {"attachment": digest, "name": "B",
                                         "position": {"x": 500, "y": 0, "z": 0}})
    assert len(subproject._CACHE) == 1  # mismos overrides → un solo replay
    k1 = host.scene[f"{c1}_{ids['base']}"].mesh_key
    k2 = host.scene[f"{c2}_{ids['base']}"].mesh_key
    assert k1 is not None and k1 == k2  # ambas instancias comparten la malla


# -------------------------------------------------------------------- errores
def test_attachment_missing(donor):
    host = Document("layout")
    with pytest.raises(DocumentError, match="materializado"):
        host.execute("insert_project", {"attachment": "cafe0123cafe0123", "name": "M1"})


def test_corrupt_snapshot():
    host = Document("layout")
    digest = host.add_attachment(b"esto no es un zip")
    with pytest.raises(DocumentError, match="Snapshot inv"):
        host.execute("insert_project", {"attachment": digest, "name": "M1"})


def test_invalid_names_rejected(donor):
    data, _ = donor
    host = Document("layout")
    digest = host.add_attachment(data)
    from apolo.commands.registry import CommandError

    for bad in ("con,coma", "con/slash", " arranca-espacio"):
        with pytest.raises(CommandError):
            host.execute("insert_project", {"attachment": digest, "name": bad})


def test_requires_source():
    from apolo.commands.registry import CommandError

    host = Document("layout")
    with pytest.raises(CommandError, match="project_id"):
        host.execute("insert_project", {"name": "M1"})


# ------------------------------------------------------------- exposición API
from fastapi.testclient import TestClient

import apolo.api.main as api


class _FakeStore:
    def __init__(self, data: dict[int, bytes]):
        self.data = data

    def load_bytes(self, project_id: int) -> bytes:
        if project_id not in self.data:
            raise KeyError(f"No existe el proyecto {project_id}")
        return self.data[project_id]

    def save_raw(self, project_id, name, pieces, data):  # V6.2d: el flush debounced escribe aquí
        pass

    def save_geom_cache(self, project_id, sig, blob):
        pass


@pytest.fixture()
def api_env(donor):
    data, ids = donor
    old = (api.DOC, api.STORE, api.PROJECT_ID)
    api.DOC = Document("layout-api")
    api.STORE = _FakeStore({38: data})
    api.PROJECT_ID = 99
    yield TestClient(api.app), ids
    api._autosave_sched.cancel()  # V6.2d: sin Timers huérfanos
    api.DOC, api.STORE, api.PROJECT_ID = old


def test_api_materializes_project_id(api_env):
    client, _ = api_env
    r = client.post("/api/commands", json={
        "type": "insert_project", "params": {"project_id": 38, "name": "Faja A"},
    })
    assert r.status_code == 200
    cmd = api.DOC.commands[-1]
    digest = cmd["params"]["attachment"]
    assert digest and digest in api.DOC.attachments  # la API embebió el snapshot


def test_api_refresh_reembeds(api_env, donor):
    client, ids = api_env
    r = client.post("/api/commands", json={
        "type": "insert_project", "params": {"project_id": 38, "name": "Faja A"},
    })
    cid = r.json()["affected_command_ids"][0]
    old_digest = api.DOC.commands[-1]["params"]["attachment"]
    # el origen cambió (L=300); refresh = attachment vacío con merge
    api.STORE.data[38] = _build_donor("300")[0]
    r = client.put(f"/api/commands/{cid}", params={"merge": "true"},
                   json={"params": {"attachment": ""}})
    assert r.status_code == 200
    new_digest = next(c for c in api.DOC.commands if c["id"] == cid)["params"]["attachment"]
    assert new_digest != old_digest
    bb = api.DOC.scene[f"{cid}_{ids['base']}"].shape.bounding_box()
    assert bb.max.X - bb.min.X == pytest.approx(300, abs=1e-3)


def test_api_self_reference_rejected(api_env):
    client, _ = api_env
    r = client.post("/api/commands", json={
        "type": "insert_project", "params": {"project_id": 99, "name": "Yo"},
    })
    assert r.status_code == 400
    assert "sí mismo" in r.json()["detail"]


def test_api_unknown_project_400(api_env):
    client, _ = api_env
    r = client.post("/api/commands", json={
        "type": "insert_project", "params": {"project_id": 12345, "name": "Nada"},
    })
    assert r.status_code == 400


def test_api_batch_two_instances(api_env):
    client, _ = api_env
    r = client.post("/api/commands/batch", json={"actions": [
        {"type": "insert_project", "params": {"project_id": 38, "name": "Faja A"}},
        {"type": "insert_project", "params": {"project_id": 38, "name": "Faja B",
                                              "position": {"x": 900, "y": 0, "z": 0}}},
    ]})
    assert r.status_code == 200
    assert len(api.DOC.scene) == 8
    assert {"Faja A", "Faja B"} <= set(api.DOC.groups)


def test_api_render_isolate_instance_name(api_env):
    client, _ = api_env
    client.post("/api/commands", json={
        "type": "insert_project", "params": {"project_id": 38, "name": "Faja A"},
    })
    r = client.get("/api/render.png", params={"isolate": "Faja A", "shade": False})
    assert r.status_code == 200
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_api_preview_does_not_mutate(api_env):
    client, _ = api_env
    n_cmds = len(api.DOC.commands)
    r = client.post("/api/commands/preview", json={"actions": [
        {"type": "insert_project", "params": {"project_id": 38, "name": "Ghost"}},
    ]})
    assert r.status_code == 200
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(api.DOC.commands) == n_cmds  # el documento real no cambió
