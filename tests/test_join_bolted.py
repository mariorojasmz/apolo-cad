"""V6.5b · frente B — super-comando join_bolted (unión atornillada en UN comando).

Taladra barrenos de paso alineados en AMBAS piezas + inserta la tornillería DIN 933 de
catálogo + declara el fijador dimensionado, con criterio de ingeniería integrado
(broca ISO 273, distancia al borde ≥1.5·d, patrón centrado en la huella, largo comercial).
"""

import pytest

from apolo.doc import Document
from apolo.library.checks import hardware_ids, interference_report


def _two_plates(doc, wa=200, wb=200):
    """A (z∈[0,10]) y B (z∈[10,20]) en contacto, huella wa×wb×100 en el plano XY."""
    a = doc.execute("create_box", {"name": "Placa A", "width": wa, "depth": 100, "height": 10,
                                   "position": {"x": 0, "y": 0, "z": 5}})
    b = doc.execute("create_box", {"name": "Placa B", "width": wb, "depth": 100, "height": 10,
                                   "position": {"x": 0, "y": 0, "z": 15}})
    return a, b


def test_join_bolted_drills_both_and_inserts_bolts():
    doc = Document("jb")
    a, b = _two_plates(doc)
    vol_a0 = doc.scene[a].shape.volume
    vol_b0 = doc.scene[b].shape.volume
    doc.execute("join_bolted", {"a": a, "b": b, "size": "M12", "count": 3})

    # ids conservados (taladro EN SITIO)
    assert a in doc.scene and b in doc.scene
    # ambas piezas perdieron material (3 barrenos de paso)
    assert doc.scene[a].shape.volume < vol_a0
    assert doc.scene[b].shape.volume < vol_b0
    # 3 pernos insertados como herraje de catálogo
    bolts = [f for f in doc.scene.values() if f.component == "PERNO-HEX-M12"]
    assert len(bolts) == 3
    # fijador dimensionado declarado
    fast = list(doc.fasteners.values())
    assert len(fast) == 1 and fast[0]["kind"] == "perno"
    assert fast[0]["size"] == "M12" and fast[0]["qty"] == 3
    assert {fast[0]["a"], fast[0]["b"]} == {a, b}


def test_join_bolted_edge_distance_respected():
    doc = Document("jb-edge")
    a, b = _two_plates(doc)
    doc.execute("join_bolted", {"a": a, "b": b, "size": "M10", "count": 2})
    bolts = [f for f in doc.scene.values() if f.component == "PERNO-HEX-M10"]
    xs = sorted(f.shape.bounding_box().center().X for f in bolts)
    # huella x = [-100,100]; edge = 1.5*10 = 15 → primer/último perno dentro de [-85, 85]
    assert xs[0] >= -85 - 0.5 and xs[-1] <= 85 + 0.5


def test_join_bolted_pattern_too_tight_errors():
    doc = Document("jb-tight")
    # placa angosta: huella y = 100 mm; 6 pernos M20 (edge 30) no caben
    a = doc.execute("create_box", {"name": "A", "width": 60, "depth": 100, "height": 10, "position": {"z": 5}})
    b = doc.execute("create_box", {"name": "B", "width": 60, "depth": 100, "height": 10, "position": {"z": 15}})
    with pytest.raises(Exception) as exc:
        doc.execute("join_bolted", {"a": a, "b": b, "size": "M20", "patron": [2, 3]})
    assert "muy pequeña" in str(exc.value) or "borde" in str(exc.value)


def test_join_bolted_no_contact_errors():
    doc = Document("jb-nocontact")
    a = doc.execute("create_box", {"name": "A", "width": 200, "depth": 100, "height": 10, "position": {"z": 5}})
    b = doc.execute("create_box", {"name": "B", "width": 200, "depth": 100, "height": 10, "position": {"z": 100}})
    with pytest.raises(Exception) as exc:
        doc.execute("join_bolted", {"a": a, "b": b, "size": "M12", "count": 2})
    assert "separadas" in str(exc.value) or "contacto" in str(exc.value)


def test_join_bolted_grid_pattern():
    doc = Document("jb-grid")
    a, b = _two_plates(doc)
    doc.execute("join_bolted", {"a": a, "b": b, "size": "M10", "patron": [3, 2]})
    bolts = [f for f in doc.scene.values() if f.component == "PERNO-HEX-M10"]
    assert len(bolts) == 6  # rejilla 3×2


def test_join_bolted_edit_count_regenerates():
    doc = Document("jb-editcount")
    a, b = _two_plates(doc)
    cid = doc.execute("join_bolted", {"a": a, "b": b, "size": "M10", "count": 2})
    assert len([f for f in doc.scene.values() if f.component == "PERNO-HEX-M10"]) == 2
    doc.edit(cid, {"a": a, "b": b, "size": "M10", "count": 4})
    assert len([f for f in doc.scene.values() if f.component == "PERNO-HEX-M10"]) == 4


def test_join_bolted_recenter_when_a_moves():
    """Paramétrico: mover A recentra el patrón sobre la nueva huella al regenerar."""
    doc = Document("jb-recenter")
    a, b = _two_plates(doc)
    cid = doc.execute("join_bolted", {"a": a, "b": b, "size": "M10", "count": 2})
    xs0 = sorted(round(f.shape.bounding_box().center().X, 1)
                 for f in doc.scene.values() if f.component == "PERNO-HEX-M10")
    # mueve A a x∈[0,200]; la huella con B (x∈[-100,100]) pasa a [0,100] → patrón se recentra
    doc.edit(a, {"name": "Placa A", "width": 200, "depth": 100, "height": 10,
                 "position": {"x": 100, "y": 0, "z": 5}})
    xs1 = sorted(round(f.shape.bounding_box().center().X, 1)
                 for f in doc.scene.values() if f.component == "PERNO-HEX-M10")
    assert xs1 != xs0 and min(xs1) >= 0  # el patrón migró a la nueva huella (x ≥ 0)


def test_join_bolted_bolts_excluded_from_interference():
    doc = Document("jb-interf")
    a, b = _two_plates(doc)
    doc.execute("join_bolted", {"a": a, "b": b, "size": "M12", "count": 2})
    hw = hardware_ids(doc)
    bolt_ids = {fid for fid, f in doc.scene.items() if f.component == "PERNO-HEX-M12"}
    assert bolt_ids <= hw  # todos los pernos son herraje
    clean = interference_report(doc.scene, exclude_ids=hw)
    assert not any(c["a"] in bolt_ids or c["b"] in bolt_ids for c in clean["interferencias"])


def test_join_bolted_bom_lists_bolts_as_catalog():
    doc = Document("jb-bom")
    a, b = _two_plates(doc)
    doc.execute("join_bolted", {"a": a, "b": b, "size": "M12", "count": 4})
    from apolo.library.bom import bom_from_scene

    bom = bom_from_scene(doc.scene)
    row = next((r for r in bom if r.get("ref") == "PERNO-HEX-M12"), None)
    assert row is not None and row["cantidad"] == 4


def test_join_bolted_same_piece_errors():
    doc = Document("jb-same")
    a, _ = _two_plates(doc)
    with pytest.raises(Exception) as exc:
        doc.execute("join_bolted", {"a": a, "b": a, "size": "M10", "count": 2})
    assert "distinta" in str(exc.value) or "a ≠ b" in str(exc.value)
