"""Fase 3 · vista explosionada: separa las piezas sin tocar el documento + globos de secuencia."""

from apolo.doc import Document
from apolo.drawing import compose_sheet
from apolo.drawing.explode import explode_scene


def _zc(f) -> float:
    bb = f.shape.bounding_box()
    return (bb.min.Z + bb.max.Z) / 2


def test_explode_scene_separates_without_mutating():
    doc = Document()
    a = doc.execute("create_box", {"name": "a", "width": 100, "depth": 100, "height": 20, "position": {"z": 0}})
    doc.execute("create_box", {"name": "b", "width": 100, "depth": 100, "height": 20, "position": {"z": 60}})
    before = doc.scene[a].shape.bounding_box().min.Z
    exp = explode_scene(doc.scene, axis="z", factor=2.0)
    assert doc.scene[a].shape.bounding_box().min.Z == before  # el documento NO se muta
    zs = sorted(_zc(f) for f in exp.values())
    assert zs[-1] - zs[0] > 60  # más separados que en el modelo original (60)


def test_compose_explode_view_has_balloons_and_centerline():
    doc = Document()
    for i in range(3):
        doc.execute("create_box", {"name": f"capa{i}", "width": 200, "depth": 150, "height": 15,
                                    "position": {"z": i * 25}})
    model = compose_sheet(doc.scene, explode={"axis": "z", "factor": 2.0})
    texts = [l.text for l in model.labels]
    assert "VISTA EXPLOSIONADA" in texts
    assert "ISOMÉTRICA (sin escala)" not in texts  # la explosión sustituye la iso
    globos = [c for c in model.circles if c.kind == "globo"]
    assert len(globos) >= 3  # un globo de secuencia por capa
    assert any(l.kind == "center" for l in model.lines)  # línea de explosión (eje-punto)
