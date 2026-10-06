"""Un parámetro que no existe se rechaza con su corrección (plan estado-regen, F4: D6–D8).

Antes `_validate_model` descartaba en silencio toda clave desconocida: el agente mandaba
`pattern_linear.name` (102 veces en el proyecto 38) y `create_box.material` creyendo que hacían
algo. Hoy la ENTRADA de un cliente es estricta en las cuatro puertas de `Document` (execute,
edit, execute_many, edit_many → REST, lotes, jobs, preview y MCP; el chat de la app ensaya sus
propuestas con `preview`); el REPLAY sigue tolerante (`extra="ignore"` explícito), y un edit
sólo rechaza las claves que el cliente INTRODUCE (la UI reenvía los params guardados).
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.commands.registry import REGISTRY, CommandError, _validate_model, validate_params
from apolo.commands.strict import field_paths, model_at, ruta_txt, unknown_paths
from apolo.doc.document import Document


def _client(name: str) -> TestClient:
    api.DOC = Document(name)
    return TestClient(api.app)


def _box(name="A", **extra) -> dict:
    return {"type": "create_box", "params": {"name": name, "width": 50, "depth": 50,
                                             "height": 50, **extra}}


def _await_job(client, job_id, timeout=15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}", params={"wait_s": 5}).json()
        if job["estado"] in ("ok", "error"):
            return job
    raise AssertionError(f"el job {job_id} no terminó en {timeout}s")


def _doc_con_name_viejo() -> tuple[Document, str]:
    """El caso c45 del proyecto 38: un pattern_linear GUARDADO con `name` (log viejo)."""
    doc = Document("c45")
    doc.execute("create_box", {"name": "Rodillo", "width": 40, "depth": 40, "height": 40})
    fid = next(iter(doc.scene))
    doc.execute("pattern_linear", {"feature": fid, "count": 2, "spacing": {"x": 100}})
    cid = doc.commands[-1]["id"]
    doc.commands[-1]["params"]["name"] = "Rodillos"  # como quedó en los logs guardados
    doc.regenerate()
    return doc, cid


# ------------------------------------------------------------------ detección (strict.py)
def test_detecta_en_todos_los_niveles_en_una_pasada():
    model = REGISTRY["create_sheet_metal"].model
    paths = unknown_paths(model, {
        "nombre": "x",                                       # raíz
        "position": {"x": 1, "q": 2},                        # anidada
        "flaps": [{"lado": "frente", "zz": 1, "child": {"yy": 2}}],  # en listas
    })
    assert paths == {("nombre",), ("position", "q"), ("flaps", 0, "zz"),
                     ("flaps", 0, "child", "yy")}


def test_opcional_y_expresiones_sin_resolver():
    """Dentro de un `Vec3 | None` también se ve; un `=expr` sin resolver NO es clave de más
    (da `float_parsing`, que se filtra): la detección no necesita las variables."""
    drill = REGISTRY["drill_hole"].model
    assert unknown_paths(drill, {"feature": "f", "position": {"x": "=a", "qq": 1}}) == {
        ("position", "qq")}
    pattern = REGISTRY["pattern_linear"].model
    assert unknown_paths(pattern, {"feature": "f", "count": "=n", "spacing": {"x": "=p"}}) == set()


def test_campos_libres_no_se_revisan():
    """`sketch: dict` y `overrides: dict[str, float]` son libres a propósito (plan, «NO hace»)."""
    loft = REGISTRY["sketch_loft"].model
    assert unknown_paths(loft, {"sections": [{"sketch": {"lo_que_sea": 1}, "z": 0}]}) == set()
    ins = REGISTRY["insert_project"].model
    assert unknown_paths(ins, {"name": "L", "overrides": {"largo": 1}}) == set()


def test_ruta_y_modelo_de_cada_nivel():
    model = REGISTRY["create_sheet_metal"].model
    assert ruta_txt(("flaps", 0, "child", "k")) == "flaps[0].child.k"
    assert set(model_at(model, ("flaps", 0, "child")).model_fields) >= {"altura", "angulo"}
    assert set(model_at(model, ("position",)).model_fields) == {"x", "y", "z"}
    assert model_at(model, ("name",)) is None
    assert "flaps[].child.altura" in field_paths(model)


# ------------------------------------------------------------------ el rechazo enseña (D8)
def test_rechazo_nombra_comando_ruta_validas_y_sugiere():
    with pytest.raises(CommandError) as exc:
        validate_params("create_box", {"widht": 10}, {}, strict=True)
    msg = str(exc.value)
    assert "create_box" in msg and "no se aplicó nada" in msg
    assert "«widht» no existe; ¿quisiste decir «width»?" in msg
    assert "Válidos en ese nivel: name, width, depth, height, position, rotation." in msg


def test_material_y_color_apuntan_a_su_tool():
    with pytest.raises(CommandError) as exc:
        validate_params("create_box", {"material": "acero", "color": "#ff0000"}, {}, strict=True)
    msg = str(exc.value)
    assert msg.startswith("2 parámetros desconocidos en create_box")
    assert "«material»: el material no es un parámetro; asígnalo con set_material" in msg
    assert "«color»: el color no es un parámetro; asígnalo con set_color" in msg


def test_anidada_en_lista_sugiere_la_ruta_completa():
    with pytest.raises(CommandError) as exc:
        validate_params("create_sheet_metal", {"flaps": [{"lado": "frente", "child": {
            "altur": 30}}]}, {}, strict=True)
    assert "¿quisiste decir «flaps[0].child.altura»?" in str(exc.value)


def test_sin_strict_y_en_el_replay_se_ignora():
    """El replay valida con `extra="ignore"` EXPLÍCITO: la clave vieja no llega al modelo ni
    a `model_fields_set` (lo usa drill_hole para saber si `axis` fue explícito)."""
    m = _validate_model("pattern_linear", {"feature": "f", "spacing": {"x": 1}, "name": "x"})
    assert "name" not in m.model_fields_set and not hasattr(m, "name")
    validate_params("pattern_linear", {"feature": "f", "spacing": {"x": 1}, "name": "x"}, {})


# ------------------------------------------------------------------ puertas de Document
def test_execute_rechaza_por_rest_con_las_validas():
    client = _client("rest")
    r = client.post("/api/commands", json={"type": "pattern_linear", "params": {
        "feature": "x", "count": 2, "spacing": {"x": 10}, "name": "copias"}})
    assert r.status_code == 400
    assert "«name» no existe. Válidos en ese nivel: feature, count, spacing." in r.json()["detail"]
    assert api.DOC.commands == [] and api.DOC._undo == []


def test_lote_revertido_sin_tocar_nada_ni_undo_fantasma():
    client = _client("lote")
    assert client.post("/api/commands", json=_box("Previo")).status_code == 200
    antes = (list(api.DOC.commands), len(api.DOC._undo), api.DOC._seq, list(api.DOC.scene))
    r = client.post("/api/commands/batch", json={"actions": [
        _box("B"), _box("C", material="acero")]})
    assert r.status_code == 400
    assert "set_material" in r.json()["detail"]
    assert (list(api.DOC.commands), len(api.DOC._undo), api.DOC._seq, list(api.DOC.scene)) == antes


def test_lote_con_variables_que_el_propio_lote_define_sigue_pasando():
    """La entrada estricta mira CLAVES, no valores: `=ancho` aún no existe al revisarla."""
    client = _client("lote-vars")
    r = client.post("/api/commands/batch", json={"actions": [
        {"type": "set_variable", "params": {"name": "ancho", "expression": "80"}},
        {"type": "create_box", "params": {"name": "A", "width": "=ancho"}},
    ]})
    assert r.status_code == 200, r.text


def test_job_falla_con_el_mismo_texto_que_el_sync():
    client = _client("job")
    sync = client.post("/api/commands/batch", json={"actions": [_box("C", material="acero")]})
    r = client.post("/api/commands/batch", params={"async": "true"},
                    json={"actions": [_box("C", material="acero")]})
    assert r.status_code == 202
    job = _await_job(client, r.json()["job_id"])
    assert job["estado"] == "error" and job["http_status"] == 400
    assert job["error"] == sync.json()["detail"]
    assert api.DOC.commands == []


def test_preview_tambien_es_estricto():
    client = _client("preview")
    r = client.post("/api/commands/preview", json={
        "actions": [_box("C", material="acero")], "data": True})
    assert r.status_code == 400 and "set_material" in r.json()["detail"]
    assert api.DOC.commands == []


# ------------------------------------------------------------------ edits (D7)
def test_c45_edita_con_su_name_viejo_por_rest():
    """La UI reenvía los params guardados ENTEROS: el `name` viejo pasa y se queda."""
    doc, cid = _doc_con_name_viejo()
    api.DOC = doc
    client = TestClient(api.app)
    full = {**doc.commands[-1]["params"], "count": 3}
    assert client.put(f"/api/commands/{cid}", json={"params": full}).status_code == 200
    assert client.put(f"/api/commands/{cid}", params={"merge": "true"},
                      json={"params": {"count": 4}}).status_code == 200
    assert doc.commands[-1]["params"]["name"] == "Rodillos"  # el log no se reescribe (D13)
    assert len(doc.scene) == 4
    r = client.patch("/api/commands/batch", params={"merge": "true"},
                     json={"edits": [{"command_id": cid, "params": {"count": 2}}]})
    assert r.status_code == 200, r.text


def test_edit_rechaza_la_clave_que_el_cliente_introduce():
    doc, cid = _doc_con_name_viejo()
    snap = (list(doc.scene), len(doc._undo))
    for merge in (False, True):
        params = {"count": 3, "nombre": "x"}
        if not merge:
            params = {**doc.commands[-1]["params"], **params}
        with pytest.raises(CommandError, match="«nombre» no existe"):
            doc.edit(cid, params, merge=merge)
    assert (list(doc.scene), len(doc._undo)) == snap


def test_edit_many_rechaza_y_revierte_todo_el_lote():
    doc, cid = _doc_con_name_viejo()
    box = doc.commands[0]["id"]
    antes = ([dict(c["params"]) for c in doc.commands], len(doc._undo))
    with pytest.raises(CommandError, match="«spacing.w» no existe"):
        doc.edit_many([{"command_id": box, "params": {"width": 99}},
                       {"command_id": cid, "params": {"spacing": {"x": 1, "w": 2}}}], merge=True)
    assert ([dict(c["params"]) for c in doc.commands], len(doc._undo)) == antes
    assert doc.edit_many([{"command_id": cid, "params": {"count": 3}}], merge=True) == [cid]


# ------------------------------------------------------------------ el log viejo (D13)
def test_log_viejo_regenera_igual_que_sin_la_clave():
    viejo, _ = _doc_con_name_viejo()
    data = viejo.to_apolo_bytes()
    abierto = Document.from_apolo_bytes(data)
    limpio = Document("limpio")
    limpio.commands = [{**c, "params": {k: v for k, v in c["params"].items() if k != "name"
                                        or c["type"] != "pattern_linear"}}
                       for c in abierto.commands]
    limpio.regenerate()

    def huella(d: Document):
        out = []
        for f in d.scene.values():
            bb = f.shape.bounding_box()
            out.append((f.id, f.name, round(f.shape.volume, 6),
                        [round(v, 6) for v in (bb.min.X, bb.min.Y, bb.min.Z, bb.max.X)]))
        return out

    assert abierto.commands[-1]["params"]["name"] == "Rodillos"
    assert huella(abierto) == huella(limpio)
