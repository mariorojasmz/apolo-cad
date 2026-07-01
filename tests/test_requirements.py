"""Tests de los requisitos de proyecto (Frente A, Fase 5): bases de diseño
persistidas como metadato (espejo de motion) + fallback en /api/checks."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc.document import Document, DocumentError


REQ = {"carga_kg": 30, "largo_paquete_mm": 600, "ancho_paquete_mm": 400,
       "velocidad_m_s": 0.35, "producto": "paquetería", "entorno": "interior"}


def test_set_and_clear_requirements():
    doc = Document("t")
    doc.set_requirements(REQ)
    assert doc.requirements["carga_kg"] == 30.0
    assert doc.requirements["producto"] == "paquetería"
    doc.set_requirements({})
    assert doc.requirements == {}


def test_requirements_roundtrip_apolo():
    doc = Document("t")
    doc.set_requirements(REQ)
    doc2 = Document.from_apolo_bytes(doc.to_apolo_bytes())
    assert doc2.requirements["velocidad_m_s"] == 0.35
    assert doc2.requirements["entorno"] == "interior"


def test_old_project_without_requirements_is_empty():
    doc = Document("t")
    doc2 = Document.from_apolo_bytes(doc.to_apolo_bytes())
    assert doc2.requirements == {}


def test_numeric_validation():
    doc = Document("t")
    with pytest.raises(DocumentError):
        doc.set_requirements({"carga_kg": -5})
    with pytest.raises(DocumentError):
        doc.set_requirements({"velocidad_m_s": "rápido"})
    with pytest.raises(DocumentError):
        doc.set_requirements({"notas": {"no": "escalar"}})
    # la inclinación admite 0 y negativos (declive)
    doc.set_requirements({"inclinacion_deg": -3})
    assert doc.requirements["inclinacion_deg"] == -3.0


def test_requirements_endpoints():
    api.DOC = Document("req-test")
    client = TestClient(api.app)
    assert client.get("/api/requirements").json() == {"requirements": {}}
    r = client.put("/api/requirements", json={"fields": REQ})
    assert r.status_code == 200
    assert r.json()["requirements"]["carga_kg"] == 30.0
    assert client.get("/api/requirements").json()["requirements"]["producto"] == "paquetería"
    assert client.put("/api/requirements", json={"fields": {"carga_kg": 0}}).status_code == 400


def test_checks_fall_back_to_requirements():
    api.DOC = Document("req-checks")
    api.DOC.execute("create_box", {"name": "Caja", "width": 100, "depth": 100, "height": 100})
    api.DOC.set_requirements(REQ)
    client = TestClient(api.app)
    # sin params en el body: la ingeniería se calcula igual (usa los requisitos)
    r = client.post("/api/checks", json={})
    assert r.status_code == 200
    assert r.json()["ingenieria"] is not None  # carga+largo vinieron de los requisitos


def test_explicit_params_beat_requirements():
    api.DOC = Document("req-priority")
    api.DOC.set_requirements(REQ)
    client = TestClient(api.app)
    # carga explícita 0 (falsy) → no dispara ingeniería aunque haya requisitos...
    # pero el caso relevante: params explícitos sustituyen a los guardados
    r = client.post("/api/checks", json={"carga_kg": 99, "largo_paquete_mm": 500})
    assert r.status_code == 200
    # no hay transportador → aviso genérico; lo clave es que no explota y responde
    assert r.json()["ingenieria"][0]["regla"] == "transportador"
