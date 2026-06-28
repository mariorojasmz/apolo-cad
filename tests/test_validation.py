import json

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.agent import build_tools
from apolo.agent.agent import run_validation_tool
from apolo.doc import Document
from apolo.library import (
    conveyor_engineering_check,
    interference_report,
    recommend_motor,
    recommend_roller,
)
from apolo.sandbox import ScriptError, run_script_to_shape

SCRIPT_OK = "result = Box(100, 50, 20)"
SCRIPT_WITH_VARS = "result = Cylinder(V['R'], V['R'] * 2)"


# ------------------------------------------------------------------- sandbox
def test_sandbox_runs_script():
    shape = run_script_to_shape(SCRIPT_OK)
    assert shape.volume == pytest.approx(100 * 50 * 20, rel=1e-6)


def test_sandbox_uses_project_variables():
    shape = run_script_to_shape(SCRIPT_WITH_VARS, {"R": 30})
    bb = shape.bounding_box()
    assert bb.max.Z - bb.min.Z == pytest.approx(60, abs=1e-3)


def test_sandbox_reports_runtime_error():
    with pytest.raises(ScriptError, match="falló"):
        run_script_to_shape("result = Box(1, 1, no_existe)")
    with pytest.raises(ScriptError, match="result"):
        run_script_to_shape("x = Box(1, 1, 1)")
    with pytest.raises(ScriptError, match="sintaxis"):
        run_script_to_shape("result = (")


def test_run_script_command_and_cache():
    doc = Document()
    fid = doc.execute("run_script", {"name": "Pieza", "code": SCRIPT_OK})
    assert doc.scene[fid].shape.volume == pytest.approx(100000, rel=1e-6)
    # la regeneración (undo/redo, edición) usa la caché: debe ser casi instantánea
    import time

    t0 = time.time()
    doc.regenerate()
    assert time.time() - t0 < 1.0


# --------------------------------------------------------------------- reglas
def test_engineering_check_acceptance_case():
    """El criterio de la fase: 2 m, paquetes de 15 kg / 400 mm a 0.5 m/s."""
    conveyor = {"largo": 2000, "ancho": 600, "paso": 100, "rodillo": "RODILLO-50", "motor": "MOTOR-037"}
    checks = conveyor_engineering_check(conveyor, 15, 400, 0.5, 300)
    estados = {c["regla"]: c["estado"] for c in checks}
    assert estados["apoyo del paquete"] == "ok"
    assert estados["capacidad de rodillo"] == "ok"
    assert estados["ancho útil"] == "ok"
    assert estados["motorización"] == "ok"


def test_engineering_check_detects_problems():
    conveyor = {"largo": 2000, "ancho": 600, "paso": 250, "rodillo": "RODILLO-50", "motor": "ninguno"}
    checks = conveyor_engineering_check(conveyor, 200, 400, 0.5)
    by_rule = {c["regla"]: c for c in checks}
    assert by_rule["apoyo del paquete"]["estado"] in ("aviso", "error")
    assert by_rule["capacidad de rodillo"]["estado"] == "error"
    assert "RODILLO" in by_rule["capacidad de rodillo"]["recomendacion"]
    assert by_rule["motorización"]["estado"] == "aviso"


def test_recommendations():
    assert recommend_motor(15, 2000, 400, 0.5) == "MOTOR-037"
    assert recommend_roller(15, 400, 100) == "RODILLO-50"
    assert recommend_roller(400, 400, 200) == "RODILLO-80"


# -------------------------------------------------------------- interferencias
def test_interference_clean_conveyor():
    from apolo.library.checks import same_command_pairs

    doc = Document()
    doc.execute("create_conveyor", {"largo": 1500, "ancho": 500, "altura": 700})
    # los rodillos realistas llevan eje pasante que entra en los largueros (montaje de
    # rodamiento, contacto intencionado); el chequeo real excluye parejas del mismo
    # super-comando (igual que /api/checks y el scan de motion).
    report = interference_report(doc.scene, exclude_pairs=same_command_pairs(doc))
    assert report["interferencias"] == []


def test_interference_detects_overlap():
    doc = Document()
    doc.execute("create_box", {"width": 100, "depth": 100, "height": 100})
    doc.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": 50, "z": 30}})
    report = interference_report(doc.scene)
    assert len(report["interferencias"]) == 1
    assert report["interferencias"][0]["volumen_mm3"] == pytest.approx(50 * 100 * 70, rel=1e-3)


# -------------------------------------------------------------- tools del agente
def test_agent_tools_include_validators():
    names = {t["name"] for t in build_tools()}
    assert {"test_script", "check_interference", "engineering_check", "render_view"} <= names


def test_run_validation_tool_test_script():
    doc = Document()
    out = json.loads(run_validation_tool(doc, "test_script", {"code": SCRIPT_OK}))
    assert out["ok"] and out["volume_mm3"] == pytest.approx(100000, rel=1e-6)
    out = json.loads(run_validation_tool(doc, "test_script", {"code": "result = None"}))
    assert out["ok"] is False


def test_run_validation_tool_engineering_from_doc():
    doc = Document()
    doc.execute("set_variable", {"name": "L", "expression": "2000"})
    doc.execute("create_conveyor", {"largo": "=L", "ancho": 600, "paso": 100, "motor": "MOTOR-037"})
    out = json.loads(
        run_validation_tool(
            doc, "engineering_check", {"carga_kg": 15, "largo_paquete_mm": 400, "velocidad_m_s": 0.5}
        )
    )
    assert out["conveyor"]["largo"] == 2000  # expresión resuelta
    assert all(c["estado"] == "ok" for c in out["checks"] if c["regla"] != "velocidad")


def test_run_validation_tool_render_returns_image():
    doc = Document()
    doc.execute("create_box", {})
    content = run_validation_tool(doc, "render_view", {"view": "iso"})
    assert isinstance(content, list)
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/png"
    assert len(content[0]["source"]["data"]) > 1000


# ------------------------------------------------------------------- API HTTP
@pytest.fixture()
def client():
    api.DOC = Document("f4-test")
    return TestClient(api.app)


def test_checks_endpoint(client):
    client.post(
        "/api/commands",
        json={"type": "create_conveyor", "params": {"largo": 2000, "ancho": 600, "paso": 100, "motor": "MOTOR-037"}},
    )
    r = client.post(
        "/api/checks",
        json={"carga_kg": 15, "largo_paquete_mm": 400, "ancho_paquete_mm": 300, "velocidad_m_s": 0.5},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["interferencias"]["interferencias"] == []
    assert {c["regla"] for c in data["ingenieria"]} >= {"apoyo del paquete", "motorización"}


# ----------------------------------------- V1: validador universal (faja a mano)
def _belt_doc():
    """Faja de banda HECHA A MANO (sin create_conveyor): largueros + 2 tambores +
    rodillos de catálogo + MOTOR-075."""
    d = Document()
    d.execute("insert_component", {"component": "PERFIL-4080", "name": "Larguero +Y",
                                   "length": 3000, "position": {"y": 310, "z": 700}, "rotation": {"y": 90}})
    d.execute("insert_component", {"component": "PERFIL-4080", "name": "Larguero -Y",
                                   "length": 3000, "position": {"y": -310, "z": 700}, "rotation": {"y": 90}})
    d.execute("create_cylinder", {"name": "Tambor motriz", "radius": 40, "height": 540,
                                  "position": {"x": 1500, "z": 710}, "rotation": {"x": 90}})
    d.execute("create_cylinder", {"name": "Tambor reenvio", "radius": 40, "height": 540,
                                  "position": {"x": -1500, "z": 710}, "rotation": {"x": 90}})
    for x in (-1400, 1400):
        d.execute("insert_component", {"component": "RODILLO-50", "name": "Rodillo", "length": 540,
                                       "position": {"x": x, "z": 640}, "rotation": {"x": 90}})
    d.execute("insert_component", {"component": "MOTOR-075", "name": "Motor",
                                   "position": {"x": 1500, "y": 500, "z": 710}})
    return d


def test_detect_conveyor_manual_belt():
    from apolo.library.rules import detect_conveyor

    conv = detect_conveyor(_belt_doc().scene)
    assert conv is not None
    assert conv["tipo"] == "banda"
    assert conv["tambor_d"] == pytest.approx(80, abs=1)
    assert conv["rpm_motor"] == 60 and conv["torque_Nm"] == 120
    assert conv["motor"] == "MOTOR-075" and conv["rodillo"] == "RODILLO-50"
    # escena vacía o sin motor → no es faja
    assert detect_conveyor(Document().scene) is None


def test_belt_speed_rule_warns_below_target():
    from apolo.library.rules import conveyor_engineering_check, detect_conveyor

    conv = detect_conveyor(_belt_doc().scene)
    checks = {c["regla"]: c for c in conveyor_engineering_check(conv, 50, 400, 0.333, 300)}
    # MOTOR-075 (60 rpm) + Ø80 → ~0.25 m/s (15 m/min), por debajo de 0.333 (20 m/min)
    assert checks["velocidad de banda"]["estado"] == "aviso"
    assert checks["apoyo del paquete"]["estado"] == "ok"  # soporte continuo por banda
    assert checks["par del motor"]["estado"] == "ok"


def test_torque_rule_errors_on_overload():
    from apolo.library.rules import conveyor_engineering_check, detect_conveyor

    conv = detect_conveyor(_belt_doc().scene)
    checks = {c["regla"]: c for c in conveyor_engineering_check(conv, 2000, 400, 0.333)}
    assert checks["par del motor"]["estado"] == "error"


def test_api_checks_detects_manual_conveyor(client):
    for part in [
        {"type": "insert_component", "params": {"component": "PERFIL-4080", "length": 3000,
                                                "position": {"y": 310, "z": 700}, "rotation": {"y": 90}}},
        {"type": "create_cylinder", "params": {"name": "Tambor motriz", "radius": 40, "height": 540,
                                               "position": {"x": 1500, "z": 710}, "rotation": {"x": 90}}},
        {"type": "insert_component", "params": {"component": "RODILLO-50", "length": 540,
                                                "position": {"x": -1400, "z": 640}, "rotation": {"x": 90}}},
        {"type": "insert_component", "params": {"component": "MOTOR-075", "position": {"x": 1500, "y": 500, "z": 710}}},
    ]:
        client.post("/api/commands", json=part)
    data = client.post("/api/checks", json={"carga_kg": 50, "largo_paquete_mm": 400, "velocidad_m_s": 0.333}).json()
    reglas = {c["regla"] for c in data["ingenieria"]}
    assert "velocidad de banda" in reglas  # detectó la faja a mano
    assert not any("No hay ningún transportador" in c["detalle"] for c in data["ingenieria"])


def test_run_script_via_api(client):
    r = client.post("/api/commands", json={"type": "run_script", "params": {"code": SCRIPT_OK}})
    assert r.status_code == 200
    assert len(r.json()["features"]) == 1
    bad = client.post("/api/commands", json={"type": "run_script", "params": {"code": "result = ("}})
    assert bad.status_code == 400
    assert "sintaxis" in bad.json()["detail"]
