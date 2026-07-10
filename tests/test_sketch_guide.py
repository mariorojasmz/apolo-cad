"""Boceto-guía (blockout, Fase 1): un sólido marcado como guía queda EXCLUIDO de
BOM, masa e interferencia; el flag se deriva por command_id, persiste en el .apolo y
se re-deriva en regenerate; endpoint HTTP expone is_guide."""

from __future__ import annotations

from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc.document import Document
from apolo.library.bom import bom_from_scene
from apolo.library.checks import interference_report
from apolo.library.engineering.mass import scene_mass_properties


def _two_overlapping_boxes() -> tuple[Document, str, str]:
    doc = Document("guide-test")
    a = doc.execute("create_box", {"name": "Caja A", "width": 100, "depth": 100, "height": 100})
    b = doc.execute("create_box", {"name": "Caja B", "width": 60, "depth": 60, "height": 60})
    return doc, a, b


def test_guide_flag_toggles_on_feature():
    doc, a, _ = _two_overlapping_boxes()
    assert doc.scene[a].is_guide is False
    doc.set_sketch_guide(a, True)
    assert doc.scene[a].is_guide is True and a in doc.sketch_guides
    doc.set_sketch_guide(a, False)
    assert doc.scene[a].is_guide is False and a not in doc.sketch_guides


def test_guide_excluded_from_mass():
    doc, a, _ = _two_overlapping_boxes()
    assert scene_mass_properties(doc.scene)["total"]["n_piezas"] == 2
    doc.set_sketch_guide(a, True)
    assert scene_mass_properties(doc.scene)["total"]["n_piezas"] == 1


def test_guide_excluded_from_bom():
    doc, a, _ = _two_overlapping_boxes()
    assert len(bom_from_scene(doc.scene)) == 2  # cajas de distinto tamaño → 2 filas
    doc.set_sketch_guide(a, True)
    assert len(bom_from_scene(doc.scene)) == 1  # la guía ya no es pieza


def test_guide_excluded_from_interference():
    doc, a, _ = _two_overlapping_boxes()
    assert interference_report(doc.scene)["interferencias"]  # A y B se solapan
    doc.set_sketch_guide(a, True)
    assert interference_report(doc.scene)["interferencias"] == []  # guía fuera del análisis


def test_guide_survives_roundtrip_and_regenerate():
    doc, a, _ = _two_overlapping_boxes()
    doc.set_sketch_guide(a, True)
    doc2 = Document.from_apolo_bytes(doc.to_apolo_bytes())
    assert a in doc2.sketch_guides and doc2.scene[a].is_guide is True
    doc2.regenerate()  # el flag es DERIVADO: se re-deriva al reproducir el log
    assert doc2.scene[a].is_guide is True


def test_orphan_sketch_guides_pruned_on_load():
    """Una guía-huérfana (command_id de un comando ya podado del log) es metadato benigno;
    la carga (from_apolo_bytes) la poda para que el manifest no acumule basura. La guía
    VIVA sobrevive; la huérfana desaparece (V6.4d Fix 5a)."""
    doc, a, _ = _two_overlapping_boxes()
    doc.set_sketch_guide(a, True)
    doc.sketch_guides.add("c9999")  # huérfana sintética: ningún comando la respalda
    doc2 = Document.from_apolo_bytes(doc.to_apolo_bytes())
    assert a in doc2.sketch_guides and doc2.scene[a].is_guide is True  # la viva sobrevive
    assert "c9999" not in doc2.sketch_guides  # la huérfana se podó


def test_endpoint_set_sketch_guide_and_scene_payload():
    doc, a, _ = _two_overlapping_boxes()
    api.DOC = doc
    client = TestClient(api.app)
    r = client.post(f"/api/features/{a}/sketch-guide", json={"guide": True})
    assert r.status_code == 200
    assert doc.scene[a].is_guide is True
    entry = next(f for f in client.get("/api/scene").json()["features"] if f["id"] == a)
    assert entry["is_guide"] is True
