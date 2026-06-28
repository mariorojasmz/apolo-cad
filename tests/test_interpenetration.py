"""Cierra el punto ciego: el chequeo de interferencias excluía los pares de junta
(contacto del conector), escondiendo cuerpos que se interpenetran. `interpenetration_report`
compara el solape en pose contra la pose de diseño y reporta el EXCESO."""

from apolo.doc.document import Document
from apolo.library.checks import (
    interference_report,
    interpenetration_report,
    joint_pairs,
)
from apolo.robotics.pose import posed_shapes


def test_detecta_cuerpos_que_se_cruzan_en_junta():
    """Dos losas gruesas en bisagra de eje CENTRAL: al plegar, los cuerpos se cruzan."""
    doc = Document("t")
    a = doc.execute("create_box", {"name": "A", "width": 200, "depth": 40, "height": 200, "position": {"x": -100}})
    b = doc.execute("create_box", {"name": "B", "width": 200, "depth": 40, "height": 200, "position": {"x": 100}})
    doc.execute("add_joint", {
        "name": "J", "type": "giratoria", "parent": a, "child": b,
        "origin": {"x": 0}, "axis": {"z": 1}, "lower": -170, "upper": 170,
    })
    posed, _ = posed_shapes(doc, {"J": 60})
    rep = interpenetration_report(doc.scene, posed, joint_pairs(doc))
    assert rep and rep[0]["volumen_mm3"] > 1000  # interpenetración real detectada
    assert rep[0]["tipo"] == "interpenetracion"
    # y el chequeo normal (que excluye el par de junta) la habría escondido:
    norm = interference_report(doc.scene, shapes_override=posed, exclude_pairs=joint_pairs(doc))
    assert not norm["interferencias"]


def test_no_marca_nudillo_simetrico_en_el_eje():
    """Un nudillo/pasador cilíndrico sobre el eje de giro es contacto legítimo: al
    girar es simétrico → el solape no cambia → no se reporta."""
    doc = Document("t")
    p = doc.execute("create_box", {"name": "P", "width": 100, "depth": 40, "height": 200})
    k = doc.execute("create_cylinder", {"name": "K", "radius": 8, "height": 210})
    doc.execute("add_joint", {
        "name": "JK", "type": "giratoria", "parent": p, "child": k,
        "origin": {"x": 0}, "axis": {"z": 1}, "lower": -170, "upper": 170,
    })
    posed, _ = posed_shapes(doc, {"JK": 45})
    assert interpenetration_report(doc.scene, posed, joint_pairs(doc)) == []


def test_sin_pose_no_hay_exceso():
    doc = Document("t")
    a = doc.execute("create_box", {"name": "A", "width": 100, "depth": 40, "height": 100, "position": {"x": -50}})
    b = doc.execute("create_box", {"name": "B", "width": 100, "depth": 40, "height": 100, "position": {"x": 50}})
    doc.execute("add_joint", {
        "name": "J", "type": "giratoria", "parent": a, "child": b,
        "origin": {"x": 0}, "axis": {"z": 1},
    })
    posed, _ = posed_shapes(doc, {})  # pose de diseño
    assert interpenetration_report(doc.scene, posed, joint_pairs(doc)) == []
