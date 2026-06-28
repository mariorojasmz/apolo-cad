import io

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document


@pytest.fixture()
def client():
    api.DOC = Document("api-test")
    return TestClient(api.app)


def test_schemas_listing(client):
    schemas = client.get("/api/schemas").json()
    types = {s["type"] for s in schemas}
    assert {"create_box", "create_structural_profile", "boolean_op", "pattern_linear"} <= types
    box = next(s for s in schemas if s["type"] == "create_box")
    assert "properties" in box["schema"] and box["title"]


def test_command_scene_and_edit_flow(client):
    r = client.post("/api/commands", json={"type": "create_box", "params": {"width": 50}})
    assert r.status_code == 200
    scene = r.json()
    assert len(scene["features"]) == 1
    feat = scene["features"][0]
    # instanciada: malla en definitions + matriz; o standalone: malla propia
    if feat["mesh_key"]:
        assert feat["matrix"] and scene["definitions"][feat["mesh_key"]]["positions"]
    else:
        assert feat["mesh"]["positions"] and feat["mesh"]["indices"]

    cmd_id = feat["command_id"]
    r = client.put(f"/api/commands/{cmd_id}", json={"params": {"width": 80, "depth": 100, "height": 100}})
    assert r.status_code == 200
    bbox = r.json()["features"][0]["bbox"]
    assert bbox["max"][0] - bbox["min"][0] == pytest.approx(80, abs=1e-3)

    assert client.post("/api/undo").status_code == 200
    assert client.post("/api/redo").status_code == 200


def test_invalid_command_returns_400(client):
    r = client.post("/api/commands", json={"type": "create_box", "params": {"width": -1}})
    assert r.status_code == 400
    assert "width" in r.json()["detail"]


def test_batch_with_placeholder_refs(client):
    r = client.post(
        "/api/commands/batch",
        json={
            "actions": [
                {"type": "create_structural_profile", "params": {"profile": "40x40", "length": 2000, "rotation": {"y": 90}}},
                {"type": "pattern_linear", "params": {"feature": "$1", "count": 2, "spacing": {"y": 960}}},
            ]
        },
    )
    assert r.status_code == 200
    assert len(r.json()["features"]) == 2


def test_batch_invalid_ref_rolls_back(client):
    r = client.post(
        "/api/commands/batch",
        json={
            "actions": [
                {"type": "create_box", "params": {}},
                {"type": "transform", "params": {"feature": "$9", "translate": {"x": 10}}},
            ]
        },
    )
    assert r.status_code == 400
    # el lote es ATÓMICO (un solo regenerate): el '$9' inválido revierte TODO,
    # así que la caja del primer comando tampoco queda → nada que deshacer
    doc = client.get("/api/document").json()
    assert not doc["can_undo"] and doc["commands"] == []


def test_edit_batch_atomic_single_undo(client):
    """PATCH /api/commands/batch edita varios comandos en un lote atómico (un solo undo)."""
    ids = []
    for x in (0, 200, 400):
        r = client.post("/api/commands", json={"type": "create_box", "params": {"width": 100, "position": {"x": x}}})
        ids.append(r.json()["affected_command_ids"][0])  # el id recién creado (features[] trae toda la escena)
    r = client.patch(
        "/api/commands/batch",
        json={"edits": [
            {"command_id": ids[0], "params": {"width": 200}},
            {"command_id": ids[1], "params": {"width": 250}},
        ]},
        params={"merge": "true"},
    )
    assert r.status_code == 200
    assert set(r.json()["affected_command_ids"]) == {ids[0], ids[1]}
    by_cmd = {f["command_id"]: f for f in client.get("/api/scene").json()["features"]}
    assert by_cmd[ids[0]]["bbox"]["max"][0] - by_cmd[ids[0]]["bbox"]["min"][0] == pytest.approx(200, abs=1e-3)
    # UN solo undo revierte AMBAS ediciones
    client.post("/api/undo")
    by_cmd = {f["command_id"]: f for f in client.get("/api/scene").json()["features"]}
    assert by_cmd[ids[0]]["bbox"]["max"][0] - by_cmd[ids[0]]["bbox"]["min"][0] == pytest.approx(100, abs=1e-3)
    assert by_cmd[ids[1]]["bbox"]["max"][0] - by_cmd[ids[1]]["bbox"]["min"][0] == pytest.approx(100, abs=1e-3)


def test_edit_batch_invalid_rolls_back(client):
    """Una edición inválida en el lote → 400 y NINGÚN cambio parcial."""
    r = client.post("/api/commands", json={"type": "create_box", "params": {"width": 80}})
    cid = r.json()["features"][0]["command_id"]
    r = client.patch(
        "/api/commands/batch",
        json={"edits": [
            {"command_id": cid, "params": {"width": 300}},
            {"command_id": cid, "params": {"width": -1}},  # inválido
        ]},
        params={"merge": "true"},
    )
    assert r.status_code == 400
    feat = client.get("/api/scene").json()["features"][0]
    assert feat["bbox"]["max"][0] - feat["bbox"]["min"][0] == pytest.approx(80, abs=1e-3)  # intacto


def test_preview_no_muta(client):
    """preview de una acción → PNG válido y el DOC global SIN cambios (commands/can_undo iguales)."""
    client.post("/api/commands", json={"type": "create_box", "params": {"width": 100}})
    before = client.get("/api/document").json()
    r = client.post(
        "/api/commands/preview",
        json={"actions": [{"type": "create_box", "params": {"width": 50, "position": {"x": 300}}}]},
    )
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG"
    after = client.get("/api/document").json()
    assert after["commands"] == before["commands"]      # log intacto
    assert after["can_undo"] == before["can_undo"]      # nada que deshacer por el preview


def test_measure_and_pick_endpoints(client):
    a = client.post("/api/commands", json={"type": "create_box", "params": {"width": 100}}).json()[
        "affected_command_ids"
    ][0]
    b = client.post(
        "/api/commands", json={"type": "create_box", "params": {"width": 100, "position": {"x": 300}}}
    ).json()["affected_command_ids"][0]
    m = client.post("/api/measure", json={"a": a, "b": b}).json()
    assert m["dist_mm"] == 200.0
    p = client.get("/api/pick", params={"u": 0.5, "v": 0.5, "view": "iso"}).json()
    assert p["feature_id"] in {a, b}
    n = client.get("/api/near", params={"point": "[0,0,0]", "radius": 60}).json()
    assert n["cercanas"] and n["cercanas"][0]["id"] == a


def test_render_isolate_does_not_mutate_document(client):
    client.post("/api/commands", json={"type": "create_box", "params": {"width": 100}})
    client.post("/api/commands", json={"type": "create_box", "params": {"width": 100, "position": {"x": 300}}})
    ids = [f["id"] for f in client.get("/api/scene").json()["features"]]
    assert len(ids) == 2

    full = client.get("/api/render.png")
    assert full.status_code == 200 and full.content[:4] == b"\x89PNG"

    iso = client.get("/api/render.png", params={"isolate": ids[0]})
    assert iso.status_code == 200 and iso.content[:4] == b"\x89PNG"
    assert iso.content != full.content  # aislar una pieza cambia el render

    # lo CLAVE: el aislado no tocó la visibilidad del documento
    assert all(f.visible for f in api.DOC.scene.values())

    bad = client.get("/api/render.png", params={"isolate": "no-existe"})
    assert bad.status_code == 400


def test_cutlist_and_nesting_endpoints(client):
    client.post("/api/commands", json={"type": "create_box", "params": {"name": "tabla", "width": 500, "depth": 18, "height": 100}})
    cl = client.get("/api/cutlist.json").json()
    assert cl["lista_de_corte"] and "totales" in cl and "herraje" in cl
    csv = client.get("/api/cutlist.csv")
    assert csv.status_code == 200 and "Material" in csv.text
    nj = client.get("/api/nesting.json", params={"mode": "2d", "stock_w": 2440, "stock_h": 1220}).json()
    assert "n_planchas" in nj and 0 <= nj["desperdicio_pct"] <= 100
    svg = client.get("/api/nesting.svg", params={"mode": "1d", "stock_w": 2440})
    assert svg.status_code == 200 and svg.text.lstrip().startswith("<svg")


def test_drawing_spec_endpoint(client):
    ids = []
    for x in (0, 300):
        r = client.post("/api/commands", json={"type": "create_box", "params": {"name": "tabla", "width": 100, "depth": 18, "height": 400, "position": {"x": x}}})
        ids.append(r.json()["affected_command_ids"][0])
    # intención: aislar una pieza, con corte y BOM, en SVG
    r = client.post("/api/drawing/spec", json={"sheet": "A3", "section": "x", "bom": True, "isolate": [ids[0]], "format": "svg"})
    assert r.status_code == 200 and r.text.lstrip().startswith("<svg")
    # PDF con cotas
    r2 = client.post("/api/drawing/spec", json={"format": "pdf", "dims": ids, "datum_dims": ids})
    assert r2.status_code == 200 and r2.content[:4] == b"%PDF"
    # DESPIECE (cutlist) + detalle de una tabla: la spec acepta los campos nuevos
    r3 = client.post("/api/drawing/spec", json={
        "format": "svg", "cutlist": True, "isolate": ids, "datum_dims": ids,
        "member_detail": {"member": ids[0], "locate": ids, "name": "tabla"},
    })
    assert r3.status_code == 200
    assert "DESPIECE" in r3.text and "DETALLE" in r3.text


def test_step_export(client):
    client.post("/api/commands", json={"type": "create_box", "params": {}})
    r = client.get("/api/export/step")
    assert r.status_code == 200
    assert b"ISO-10303-21" in r.content[:200]


def test_project_roundtrip_over_http(client):
    client.post("/api/commands", json={"type": "create_cylinder", "params": {"radius": 40}})
    apolo_bytes = client.get("/api/project/file").content

    client.post("/api/project/new", json={"name": "vacio"})
    assert client.get("/api/scene").json()["features"] == []

    r = client.post(
        "/api/project/open",
        files={"file": ("p.apolo", io.BytesIO(apolo_bytes), "application/zip")},
    )
    assert r.status_code == 200
    assert len(r.json()["features"]) == 1


def test_visibility_endpoint(client):
    r = client.post("/api/commands", json={"type": "create_box", "params": {}})
    fid = r.json()["features"][0]["id"]
    r = client.post(f"/api/features/{fid}/visibility", json={"visible": False})
    assert r.json()["features"][0]["visible"] is False


def test_bulk_visibility_endpoint(client):
    ids = []
    for _ in range(3):
        r = client.post("/api/commands", json={"type": "create_box", "params": {}})
        ids.append(r.json()["features"][-1]["id"])
    # ocultar dos de tres en una sola llamada (patrón "aislar")
    r = client.post("/api/features/visibility", json={"ids": ids[:2], "visible": False})
    assert r.status_code == 200
    vis = {f["id"]: f["visible"] for f in r.json()["features"]}
    assert vis[ids[0]] is False and vis[ids[1]] is False and vis[ids[2]] is True
    # mostrar todo
    r = client.post("/api/features/visibility", json={"ids": ids[:2], "visible": True})
    assert all(f["visible"] for f in r.json()["features"])


def test_script_test_endpoint(client):
    # dry-run read-only: no crea features
    r = client.post("/api/script/test", json={"code": "result = Box(100, 50, 20)"})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True and d["volume_mm3"] == pytest.approx(100 * 50 * 20, rel=1e-3)
    assert client.get("/api/scene").json()["features"] == []  # no tocó el documento
    bad = client.post("/api/script/test", json={"code": "result = ("})
    assert bad.status_code == 200 and bad.json()["ok"] is False


def test_checks_predictive_conveyor(client):
    # validación predictiva por params, con escena vacía (sin construir la faja)
    r = client.post("/api/checks", json={
        "carga_kg": 50, "largo_paquete_mm": 400, "velocidad_m_s": 0.3,
        "conveyor": {"largo": 3000, "ancho": 500, "altura": 750, "paso": 300,
                     "rodillo": "RODILLO-50", "motor": "MOTOR-075"},
    })
    assert r.status_code == 200
    ing = r.json()["ingenieria"]
    assert isinstance(ing, list) and len(ing) > 0


def test_agent_notes_endpoint(client):
    assert client.get("/api/agent/notes").json()["notes"] == []
    client.post("/api/agent/notes", json={"text": "nota 1"})
    r = client.post("/api/agent/notes", json={"text": "nota 2"})
    assert r.json()["notes"] == ["nota 1", "nota 2"]
    assert client.get("/api/agent/notes").json()["notes"] == ["nota 1", "nota 2"]


def test_topology_box(client):
    r = client.post("/api/commands", json={"type": "create_box", "params": {}})
    fid = r.json()["features"][0]["id"]
    topo = client.get(f"/api/features/{fid}/topology").json()
    assert topo["feature_id"] == fid
    faces, edges = topo["faces"], topo["edges"]
    # una caja: 6 caras planas (con normal) y 12 aristas rectas (con dirección)
    assert len(faces) == 6 and all(f["tipo"] == "PLANE" for f in faces)
    assert all("normal" in f and "center" in f and "area" in f for f in faces)
    assert len(edges) == 12 and all(e["tipo"] == "LINE" for e in edges)
    assert all("direction" in e and e["length"] > 0 for e in edges)


def test_topology_cylinder_and_404(client):
    r = client.post("/api/commands", json={"type": "create_cylinder", "params": {"radius": 40}})
    fid = r.json()["features"][0]["id"]
    topo = client.get(f"/api/features/{fid}/topology").json()
    tipos = {f["tipo"] for f in topo["faces"]}
    assert "CYLINDER" in tipos and "PLANE" in tipos  # lateral + tapas
    cyl = next(f for f in topo["faces"] if f["tipo"] == "CYLINDER")
    assert cyl["radius"] == pytest.approx(40, abs=1e-2) and "axis" in cyl
    assert client.get("/api/features/no-existe/topology").status_code == 404


def test_resolve_expression_endpoint(client):
    # constante pi
    r = client.get("/api/resolve-expression", params={"expr": "2*pi"}).json()
    assert r["ok"] is True and r["value"] == pytest.approx(2 * 3.14159265, abs=1e-4)
    # contra una variable de proyecto
    client.post("/api/variables", json={"name": "largo", "expression": "1000"})
    r = client.get("/api/resolve-expression", params={"expr": "largo/2 + 50"}).json()
    assert r["ok"] is True and r["value"] == pytest.approx(550.0)
    # expresión inválida → ok:false, sin 500
    bad = client.get("/api/resolve-expression", params={"expr": "nope*2"}).json()
    assert bad["ok"] is False and "error" in bad


def test_expression_grammar_endpoint(client):
    client.post("/api/variables", json={"name": "ancho", "expression": "500"})
    g = client.get("/api/expression-grammar").json()
    assert "sqrt" in g["functions"] and "pi" in g["constants"]
    assert "**" in g["operators"] and "ancho" in g["variables"]


def test_render_with_highlight(client):
    r = client.post("/api/commands", json={"type": "create_box", "params": {}})
    fid = r.json()["features"][0]["id"]
    resp = client.get(
        "/api/render.png",
        params={"highlight": fid, "show_axes": True, "show_bbox": True},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"


# --- mejora #3: schema de un solo comando ---
def test_schema_single_command(client):
    body = client.get("/api/schemas/create_box").json()
    assert body["type"] == "create_box" and "properties" in body["schema"]


def test_schema_single_unknown_404(client):
    assert client.get("/api/schemas/no_existe").status_code == 404


# --- mejora #1: retorno con command_ids afectados + total ---
def test_command_returns_affected_ids(client):
    body = client.post("/api/commands", json={"type": "create_box", "params": {"width": 50}}).json()
    assert body["affected_command_ids"] == [body["features"][0]["command_id"]]
    assert body["total_features"] == 1


def test_batch_returns_affected_ids(client):
    body = client.post(
        "/api/commands/batch",
        json={
            "actions": [
                {"type": "create_box", "params": {"width": 50}},
                {"type": "create_box", "params": {"width": 60, "position": {"x": 200}}},
            ]
        },
    ).json()
    assert len(body["affected_command_ids"]) == 2
    assert body["total_features"] == 2


def test_edit_returns_affected_id(client):
    cid = client.post(
        "/api/commands", json={"type": "create_box", "params": {"width": 50}}
    ).json()["features"][0]["command_id"]
    body = client.put(
        f"/api/commands/{cid}", json={"params": {"width": 80, "depth": 100, "height": 100}}
    ).json()
    assert body["affected_command_ids"] == [cid]


def test_set_variable_affected_is_var_command(client):
    client.post("/api/commands", json={"type": "create_box", "params": {"width": 50}})
    body = client.post("/api/variables", json={"name": "W", "expression": "100"}).json()
    aff = body["affected_command_ids"]
    assert len(aff) == 1
    assert all(f["command_id"] != aff[0] for f in body["features"])  # ninguna feature es la variable


def test_payload_has_total_features(client):
    client.post("/api/commands", json={"type": "create_box", "params": {"width": 50}})
    body = client.get("/api/scene").json()
    assert body["total_features"] == len(body["features"]) == 1


# --- mejora #2: edit con ?merge=true (PATCH) ---
def test_edit_merge_query_param(client):
    cid = client.post(
        "/api/commands", json={"type": "create_box", "params": {"width": 80, "depth": 120, "height": 60}}
    ).json()["features"][0]["command_id"]
    bbox = client.put(
        f"/api/commands/{cid}", params={"merge": "true"}, json={"params": {"width": 200}}
    ).json()["features"][0]["bbox"]
    assert bbox["max"][0] - bbox["min"][0] == pytest.approx(200, abs=1e-3)
    assert bbox["max"][1] - bbox["min"][1] == pytest.approx(120, abs=1e-3)  # depth conservado


# --- mejora #4: encuadre/proporción del render ---
def test_render_proportional_query(client):
    client.post(
        "/api/commands", json={"type": "create_box", "params": {"width": 4000, "depth": 100, "height": 100}}
    )
    resp = client.get("/api/render.png", params={"proportional": True, "zoom": 1.5})
    assert resp.status_code == 200 and resp.headers["content-type"] == "image/png"


def test_shape_render_cache_reuses_and_recomputes():
    """El caché de render (mesh/volumen/bbox) reutiliza por identidad de shape y
    recalcula para un shape distinto. Lo aprovecha scene_payload con el regenerate
    incremental (las features no cambiadas conservan la misma referencia de shape)."""
    from build123d import Box

    from apolo.api.main import _cached_render

    s = Box(10, 10, 10)
    a = _cached_render(s, want_mesh=True)
    b = _cached_render(s, want_mesh=True)
    assert a is b and "mesh" in a and a["volume"] == 1000.0  # mismo shape → mismo dict cacheado
    c = _cached_render(Box(20, 10, 10), want_mesh=True)
    assert c is not a and c["volume"] == 2000.0  # shape distinto → recálculo


def test_assembly_declare_and_delete(client):
    # base en el piso + caja apilada encima
    client.post("/api/commands", json={"type": "create_box", "params": {
        "name": "base", "width": 100, "depth": 100, "height": 20, "position": {"x": 50, "y": 0, "z": 10}}})
    client.post("/api/commands", json={"type": "create_box", "params": {
        "name": "encima", "width": 100, "depth": 100, "height": 180, "position": {"x": 50, "y": 0, "z": 110}}})

    assert client.post("/api/assembly/declare").status_code == 200
    conn = client.get("/api/connectivity").json()
    n_g, n_f = len(conn["grounds"]), len(conn["fasteners"])
    assert n_g >= 1 and n_f >= 1  # base anclada + base↔encima

    # idempotente: no duplica
    client.post("/api/assembly/declare")
    conn2 = client.get("/api/connectivity").json()
    assert len(conn2["grounds"]) == n_g and len(conn2["fasteners"]) == n_f

    # borrar un fijador
    fname = conn2["fasteners"][0]["name"]
    assert client.delete(f"/api/fasteners/{fname}").status_code == 200
    assert len(client.get("/api/connectivity").json()["fasteners"]) == n_f - 1

    # 404 al borrar inexistente
    assert client.delete("/api/grounds/no_existe").status_code == 404
