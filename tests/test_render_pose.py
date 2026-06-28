"""render_scene_png acepta `shapes_override` para renderizar una POSE cinemática
(lo usan /api/render.png?joints=... y la tool MCP render_view)."""

from apolo.doc.document import Document
from apolo.kernel.render import render_scene_png
from apolo.robotics.pose import posed_shapes


def test_render_con_pose_difiere_de_la_estatica():
    doc = Document("t")
    a = doc.execute("create_box", {"name": "A", "width": 100, "depth": 100, "height": 100})
    b = doc.execute("create_box", {"name": "B", "width": 100, "depth": 100, "height": 100, "position": {"x": 200}})
    doc.execute("add_joint", {
        "name": "J", "type": "giratoria", "parent": a, "child": b,
        "origin": {"x": 100}, "axis": {"z": 1}, "lower": -120, "upper": 120,
    })
    base = render_scene_png(doc.scene, "iso")
    posed, _ = posed_shapes(doc, {"J": 60})
    moved = render_scene_png(doc.scene, "iso", shapes_override=posed)
    assert len(base) > 1000 and len(moved) > 1000
    assert base != moved  # la pose cambia la imagen
