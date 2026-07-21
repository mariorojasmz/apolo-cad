"""V7.3 — cadenas de cotas por la API: metadato persistente, eslabones por id/=expr,
cadena auto de pernos y sección en la memoria."""

from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc.document import Document


def _client(name: str = "stackup") -> TestClient:
    api.DOC = Document(name)
    return TestClient(api.app)


def test_set_stackup_persists_and_survives_roundtrip():
    api.DOC = Document("su-persist")
    api.DOC.set_stackup("hueco", [
        {"nombre": "ranura", "nominal_mm": 25, "sentido": 1, "tol": {"iso2768": "m"}},
        {"nombre": "placa", "nominal_mm": 24, "sentido": -1, "tol": {"iso2768": "m"}},
    ], {"entre": [0.5, 1.5]})
    # metadato: NO entra al log
    assert not api.DOC.commands
    blob = api.DOC.to_apolo_bytes()
    doc2 = Document.from_apolo_bytes(blob)
    assert "hueco" in doc2.stackups
    assert doc2.stackups["hueco"]["requisito"] == {"entre": [0.5, 1.5]}


def test_put_and_get_stackup_evaluates_worst_case_and_rss():
    client = _client("su-eval")
    r = client.put("/api/stackup", json={
        "name": "hueco",
        "eslabones": [
            {"nombre": "ranura", "nominal_mm": 25, "sentido": 1, "tol": {"iso2768": "m"}},
            {"nombre": "p1", "nominal_mm": 8, "sentido": -1, "tol": {"iso2768": "m"}},
            {"nombre": "p2", "nominal_mm": 8, "sentido": -1, "tol": {"iso2768": "m"}},
            {"nombre": "p3", "nominal_mm": 8, "sentido": -1, "tol": {"iso2768": "m"}},
        ],
        "requisito": {"entre": [0.5, 1.5]},
    })
    assert r.status_code == 200, r.text
    g = client.get("/api/stackup").json()
    ch = next(c for c in g["cadenas"] if c["name"] == "hueco")
    assert ch["nominal_close_mm"] == 1.0
    assert ch["ok_peor_caso"] is False and ch["ok_rss"] is True
    assert g["ok"] is False  # una cadena que no cierra en peor caso baja el ok global


def test_nominal_expression_follows_variables():
    client = _client("su-expr")
    client.post("/api/commands", json={"type": "set_variable", "params": {"name": "gap", "expression": "3"}})
    client.put("/api/stackup", json={
        "name": "c", "eslabones": [
            {"nombre": "var", "nominal_mm": "=gap*10", "sentido": 1, "tol": {"pm": 0.1}},
        ]})
    ch = next(c for c in client.get("/api/stackup").json()["cadenas"] if c["name"] == "c")
    assert ch["nominal_close_mm"] == 30.0  # 3*10, resuelto contra la variable


def test_link_by_feature_id_measures_live_bbox():
    client = _client("su-bbox")
    client.post("/api/commands", json={"type": "create_box", "params": {
        "name": "Placa", "width": 120, "depth": 80, "height": 12}})
    client.put("/api/stackup", json={
        "name": "esp", "eslabones": [{"id": "c1", "eje": "z", "sentido": 1, "tol": {"pm": 0.1}}],
        "requisito": {"entre": [11, 13]}})
    ch = next(c for c in client.get("/api/stackup").json()["cadenas"] if c["name"] == "esp")
    assert ch["nominal_close_mm"] == 12.0  # el alto real de la caja, medido del bbox
    assert ch["ok_peor_caso"] is True


def test_auto_bolt_chain_join_bolted_is_closed_by_construction():
    client = _client("su-auto")
    client.post("/api/commands/batch", json={"actions": [
        {"type": "create_box", "params": {"name": "Base", "width": 200, "depth": 150, "height": 12}},
        {"type": "create_box", "params": {"name": "Tapa", "width": 200, "depth": 150,
                                          "height": 10, "position": {"x": 0, "y": 0, "z": 11}}},
        {"type": "join_bolted", "params": {"a": "c1", "b": "c2", "size": "M12", "patron": [2, 2]}},
    ]})
    auto = [c for c in client.get("/api/stackup", params={"scope": "auto"}).json()["cadenas"]]
    assert auto and all(c.get("cerrada_por_construccion") for c in auto)


def test_manual_bolt_fastener_is_informative_not_a_false_failure():
    """Un perno DECLARADO a mano (fasten con size, sin join_bolted) → informativo (holgura
    de paso disponible), SIN veredicto: fabricar la demanda de posición sería inventar, y
    no debe bajar el ok global ni ensuciar la memoria."""
    client = _client("su-manual")
    client.post("/api/commands/batch", json={"actions": [
        {"type": "create_box", "params": {"name": "A", "width": 100, "depth": 100, "height": 20}},
        {"type": "create_box", "params": {"name": "B", "width": 100, "depth": 100, "height": 20,
                                          "position": {"x": 0, "y": 0, "z": 20}}},
        {"type": "fasten", "params": {"name": "w", "a": "c1", "b": "c2", "kind": "perno",
                                      "size": "M12"}},
    ]})
    g = client.get("/api/stackup").json()
    auto = [c for c in g["cadenas"] if c["tipo"] == "auto-perno"]
    assert auto and all(c.get("informativo") for c in auto)
    assert all("holgura_mm" in c for c in auto)
    assert g["ok"] is True  # informativos NO bajan el ok global


# ------------------------------------------- cierre de la auditoría V7.3 (Fable)
def test_invalid_chain_is_not_persisted_and_does_not_poison_get():
    """Una cadena que NO evalúa (tol desconocida) → 400 y NO se guarda; las cadenas
    buenas siguen evaluando (antes: quedaba persistida y GET reventaba para siempre,
    ocultando TODAS las cadenas y borrando la sección de la memoria en silencio)."""
    client = _client("su-poison")
    r = client.put("/api/stackup", json={"name": "buena", "eslabones": [
        {"nombre": "a", "nominal_mm": 10, "sentido": 1, "tol": {"pm": 0.1}}]})
    assert r.status_code == 200
    r = client.put("/api/stackup", json={"name": "mala", "eslabones": [
        {"nombre": "x", "nominal_mm": 10, "sentido": 1, "tol": {"foo": 1}}]})
    assert r.status_code == 400 and "no se guardó" in r.json()["detail"]
    assert "mala" not in api.DOC.stackups  # rollback: la mala NO persiste
    g = client.get("/api/stackup")
    assert g.status_code == 200  # el endpoint NO quedó envenenado
    assert any(c["name"] == "buena" for c in g.json()["cadenas"])


def test_invalid_edit_of_existing_chain_rolls_back_to_previous():
    """Editar una cadena BUENA con una versión mala → 400 y la versión previa SOBREVIVE."""
    client = _client("su-rollback")
    client.put("/api/stackup", json={"name": "c", "eslabones": [
        {"nombre": "a", "nominal_mm": 10, "sentido": 1, "tol": {"pm": 0.1}}]})
    r = client.put("/api/stackup", json={"name": "c", "eslabones": [
        {"nombre": "a", "nominal_mm": "=variable_inexistente", "sentido": 1, "tol": {"pm": 0.1}}]})
    assert r.status_code == 400
    ch = next(c for c in client.get("/api/stackup").json()["cadenas"] if c["name"] == "c")
    assert ch.get("error") is None and ch["nominal_close_mm"] == 10.0  # la previa vive


def test_partial_chain_missing_piece_gives_error_not_false_verdict():
    """Una cadena con pieza inexistente NO se evalúa parcial (el cierre de una cadena
    incompleta no significa nada): entrada de error + el ok global baja."""
    client = _client("su-partial")
    client.post("/api/commands", json={"type": "create_box", "params": {
        "name": "P", "width": 100, "depth": 50, "height": 10}})
    # se declara con las 2 piezas... pero una desaparece (simulado: id fantasma directo
    # en el metadato, como quedaría tras borrar el comando)
    api.DOC.set_stackup("parcial", [
        {"id": "c1", "eje": "z", "sentido": 1, "tol": {"pm": 0.1}},
        {"id": "c_fantasma", "eje": "z", "sentido": 1, "tol": {"pm": 0.1}},
    ], {"entre": [9, 11]})
    g = client.get("/api/stackup").json()
    ch = next(c for c in g["cadenas"] if c["name"] == "parcial")
    assert "error" in ch and "c_fantasma" in ch["error"]
    assert "ok_peor_caso" not in ch  # SIN veredicto parcial
    assert g["ok"] is False  # una declarada no verificable baja el ok global
    # y en la memoria aparece como AVISO (patrón vigencia-FEA), no silencio
    rules = api._stackup_rules()
    aviso = next(r for r in rules if "parcial" in r["regla"])
    assert aviso["estado"] == "aviso" and "no se pudo evaluar" in aviso["detalle"]


def test_get_stackup_invalid_scope_is_400():
    client = _client("su-scope")
    r = client.get("/api/stackup", params={"scope": "typo"})
    assert r.status_code == 400 and "all | declared | auto" in r.json()["detail"]


def test_memoria_includes_stackup_section():
    client = _client("su-mem")
    client.post("/api/commands", json={"type": "create_box", "params": {
        "name": "Placa", "width": 120, "depth": 80, "height": 12}})
    client.put("/api/stackup", json={
        "name": "esp", "eslabones": [{"id": "c1", "eje": "z", "sentido": 1, "tol": {"pm": 0.1}}],
        "requisito": {"entre": [11, 13]}})
    api.DOC.set_requirements({"carga_kg": 50, "largo_paquete_mm": 300})
    r = client.get("/api/calc-report.pdf")
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF" and len(r.content) > 2000
