import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document, DocumentError
from apolo.projects import ProjectStore


@pytest.fixture()
def store(tmp_path):
    return ProjectStore(tmp_path / "test.db")


# ------------------------------------------------------------------- almacén
def test_store_crud_roundtrip(store):
    doc = Document("Línea 2")
    doc.execute("create_conveyor", {"largo": 1500, "ancho": 500, "altura": 700})
    pid = store.create(doc)

    projects = store.list_projects()
    assert len(projects) == 1
    assert projects[0]["name"] == "Línea 2" and projects[0]["pieces"] == len(doc.scene)

    loaded = store.load(pid)
    assert len(loaded.scene) == len(doc.scene)
    assert loaded.name == "Línea 2"

    doc.execute("create_box", {})
    store.save(pid, doc)
    assert store.load(pid).scene.keys() == doc.scene.keys()

    dup = store.duplicate(pid)
    assert "copia" in store.load(dup).name
    store.delete(dup)
    assert len(store.list_projects()) == 1


def test_store_revisions_restore(store):
    doc = Document("Rev test")
    doc.execute("create_box", {"width": 100})
    pid = store.create(doc)
    rev1 = store.save_revision(pid, doc, "antes del cilindro")

    doc.execute("create_cylinder", {})
    store.save(pid, doc)

    revs = store.list_revisions(pid)
    assert len(revs) == 1 and revs[0]["note"] == "antes del cilindro"

    back_pid, back_doc = store.load_revision(rev1)
    assert back_pid == pid
    assert len(back_doc.scene) == 1  # solo la caja


# ----------------------------------------------------------- configuraciones
def test_configurations_save_apply_cascade():
    doc = Document()
    var = doc.execute("set_variable", {"name": "L", "expression": "2000"})
    doc.execute("create_conveyor", {"largo": "=L", "ancho": 600, "altura": 750, "paso": 100})
    doc.save_configuration("2 metros")

    doc.edit(var, {"name": "L", "expression": "3000"})
    doc.save_configuration("3 metros")
    rodillos_3m = len([f for f in doc.scene.values() if "Rodillo" in f.name])

    doc.apply_configuration("2 metros")
    rodillos_2m = len([f for f in doc.scene.values() if "Rodillo" in f.name])
    assert rodillos_2m == rodillos_3m - 10  # 19 vs 29
    assert doc.variables_resolved["L"] == 2000

    # un solo undo deshace el cambio de variante completo
    doc.undo()
    assert doc.variables_resolved["L"] == 3000

    with pytest.raises(DocumentError, match="No existe"):
        doc.apply_configuration("nada")


def test_configurations_and_colors_survive_apolo():
    doc = Document()
    doc.execute("set_variable", {"name": "a", "expression": "10"})
    fid = doc.execute("create_box", {})
    doc.save_configuration("base")
    doc.set_color(fid, "#ff8800")

    doc2 = Document.from_apolo_bytes(doc.to_apolo_bytes())
    assert doc2.configurations == {"base": {"a": "10"}}
    assert doc2.colors == {fid: "#ff8800"}


def test_color_validation():
    doc = Document()
    fid = doc.execute("create_box", {})
    doc.set_color(fid, "#aabbcc")
    doc.set_color(fid, None)
    assert doc.colors == {}
    with pytest.raises(DocumentError):
        doc.set_color("nope", "#fff")


# ------------------------------------------------------------------- API HTTP
@pytest.fixture()
def client(tmp_path):
    api.DOC = Document("api-f9")
    api.STORE = ProjectStore(tmp_path / "api.db")
    api.PROJECT_ID = api.STORE.create(api.DOC)
    yield TestClient(api.app)
    api._autosave_sched.cancel()  # V6.2d: sin Timers huérfanos que disparen en otra prueba
    api.STORE = None
    api.PROJECT_ID = None


def test_autosave_on_mutation(client):
    client.post("/api/commands", json={"type": "create_box", "params": {}})
    api._flush_autosave()  # V6.2d: el autosave es debounced → forzarlo antes de leer disco
    saved = api.STORE.load(api.PROJECT_ID)
    assert len(saved.scene) == 1  # el autosave persistió la caja


def test_projects_api_flow(client):
    first_id = api.PROJECT_ID
    r = client.post("/api/projects", json={"name": "Celda", "template": "brazo"})
    assert r.status_code == 200
    assert len(r.json()["features"]) == 5  # plantilla de brazo
    assert api.PROJECT_ID != first_id

    listing = client.get("/api/projects").json()
    assert {p["name"] for p in listing} >= {"api-f9", "Celda"}

    # reabrir el primero
    r = client.post(f"/api/projects/{first_id}/open")
    assert r.status_code == 200 and r.json()["document"]["name"] == "api-f9"

    # no se puede borrar el abierto
    assert client.delete(f"/api/projects/{first_id}").status_code == 400

    # renombrar
    r = client.patch("/api/projects/current", json={"name": "Renombrado"})
    assert r.json()["document"]["name"] == "Renombrado"
    api._flush_autosave()  # V6.2d: el autosave es debounced → forzarlo antes de leer disco
    assert api.STORE.load(first_id).name == "Renombrado"


def test_revisions_api(client):
    client.post("/api/commands", json={"type": "create_box", "params": {}})
    rev = client.post("/api/revisions", json={"note": "v1"}).json()
    client.post("/api/commands", json={"type": "create_cylinder", "params": {}})
    assert len(client.get("/api/scene").json()["features"]) == 2

    r = client.post(f"/api/revisions/{rev['id']}/restore")
    assert len(r.json()["features"]) == 1
    revs = client.get("/api/revisions").json()
    assert revs[0]["note"] == "v1"


def test_configurations_api(client):
    client.post("/api/variables", json={"name": "L", "expression": "500"})
    client.post("/api/commands", json={"type": "create_box", "params": {"width": "=L"}})
    client.post("/api/configurations", json={"name": "corta"})
    client.post("/api/variables", json={"name": "L", "expression": "900"})
    client.post("/api/configurations", json={"name": "larga"})

    r = client.post("/api/configurations/corta/apply")
    bbox = r.json()["features"][0]["bbox"]
    assert bbox["max"][0] - bbox["min"][0] == pytest.approx(500, abs=1e-3)
    assert set(r.json()["document"]["configurations"]) == {"corta", "larga"}

    assert client.delete("/api/configurations/corta").status_code == 200
    assert client.post("/api/configurations/corta/apply").status_code == 400


def test_color_api(client):
    r = client.post("/api/commands", json={"type": "create_box", "params": {}})
    fid = r.json()["features"][0]["id"]
    r = client.post(f"/api/features/{fid}/color", json={"color": "#ff0066"})
    assert r.json()["features"][0]["color"] == "#ff0066"
    r = client.post(f"/api/features/{fid}/color", json={"color": None})
    assert r.json()["features"][0]["color"] != "#ff0066"
