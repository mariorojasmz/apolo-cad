"""Modelado directo (V5.3): delete_faces (Defeaturing con curación) y push_face
(prisma+booleana sobre cara plana) — sobre sólidos nativos e importados de STEP.

Los asserts son de VOLUMEN con tolerancia (nunca conteos de caras/aristas: el
resultado exacto del Defeaturing puede variar entre versiones OCCT)."""

from __future__ import annotations

import io
import math
import os
import tempfile
from pathlib import Path

import pytest

from apolo.doc.document import Document, DocumentError

V0 = 50.0 * 40.0 * 30.0  # caja de referencia


def _box(doc, **kw):
    params = {"width": 50, "depth": 40, "height": 30}
    params.update(kw)
    return doc.execute("create_box", params)


def _filleted_box_doc():
    """Caja con fillet r=5 en las 4 aristas verticales (caras CYLINDER fáciles
    de seleccionar por 'cerca' en las esquinas)."""
    doc = Document()
    b = _box(doc)
    doc.execute("fillet", {"feature": b, "edges": {"mode": "direccion", "direction": "z"},
                           "radius": 5})
    return doc, b


def _fillet_corner_points():
    """Centros aproximados de las 4 caras cilíndricas del fillet (esquinas)."""
    return [[25 - 5 * 0.3, 20 - 5 * 0.3, 0], [-25 + 1.5, 20 - 1.5, 0],
            [25 - 1.5, -20 + 1.5, 0], [-25 + 1.5, -20 + 1.5, 0]]


def _step_bytes_of(shape) -> bytes:
    from apolo.kernel import export_step_file

    fd, raw = tempfile.mkstemp(suffix=".step")
    os.close(fd)
    tmp = Path(raw)
    export_step_file([shape], str(tmp))
    data = tmp.read_bytes()
    tmp.unlink(missing_ok=True)
    return data


# --------------------------------------------------------------- delete_faces
def test_delete_fillet_restores_box():
    doc, b = _filleted_box_doc()
    assert doc.scene[b].shape.volume < V0
    # las 4 caras del fillet: cerca de una esquina con count no sirve (están en
    # esquinas opuestas) → una llamada por esquina, o tangentes; aquí: 4 llamadas
    # en un batch atómico
    actions = [
        {"type": "delete_faces", "params": {"feature": b,
         "faces": {"mode": "cerca", "point": pt, "count": 1}}}
        for pt in [[24, 19, 0], [-24, 19, 0], [24, -19, 0], [-24, -19, 0]]
    ]
    doc.execute_many(actions)
    assert doc.scene[b].shape.volume == pytest.approx(V0, rel=1e-6)


def test_delete_hole_restores_full_volume():
    doc = Document()
    b = _box(doc)
    doc.execute("drill_hole", {"feature": b, "position": {"x": 0, "y": 0, "z": 15},
                               "axis": "-z", "diameter": 10, "depth": 0})
    assert doc.scene[b].shape.volume == pytest.approx(V0 - math.pi * 25 * 30, rel=1e-4)
    doc.execute("delete_faces", {"feature": b,
                                 "faces": {"mode": "cerca", "point": [5, 0, 0], "count": 1}})
    assert doc.scene[b].shape.volume == pytest.approx(V0, rel=1e-6)


def test_delete_tangent_chain_from_one_face():
    # fillet en las aristas del TOPE = cadena tangente (4 cilindros + 4 esferas
    # de esquina); seleccionando UNA cara con tangentes=true se cura todo
    doc = Document()
    b = _box(doc)
    doc.execute("fillet", {"feature": b, "edges": {"mode": "cara", "face": "tope"},
                           "radius": 5})
    v_fillet = doc.scene[b].shape.volume
    assert v_fillet < V0
    doc.execute("delete_faces", {"feature": b, "tangentes": True,
                                 "faces": {"mode": "cerca", "point": [0, 20, 15], "count": 1}})
    assert doc.scene[b].shape.volume == pytest.approx(V0, rel=1e-6)


def test_delete_structural_face_fails_clearly():
    doc = Document()
    b = _box(doc)
    with pytest.raises(DocumentError, match="quitar|curar"):
        doc.execute("delete_faces", {"feature": b,
                                     "faces": {"mode": "cara", "face": "tope"}})
    assert doc.scene[b].shape.volume == pytest.approx(V0, rel=1e-9)  # rollback


def test_delete_all_faces_rejected():
    doc = Document()
    b = _box(doc)
    with pytest.raises(DocumentError, match="delete_feature"):
        doc.execute("delete_faces", {"feature": b, "faces": {"mode": "todas"}})


# ------------------------------------------------------------------ push_face
def test_push_face_pull_and_push():
    doc = Document()
    b = _box(doc)
    doc.execute("push_face", {"feature": b, "face": {"mode": "cara", "face": "tope"},
                              "distance": 10})
    assert doc.scene[b].shape.volume == pytest.approx(50 * 40 * 40, rel=1e-6)
    doc.execute("push_face", {"feature": b, "face": {"mode": "cara", "face": "tope"},
                              "distance": -20})
    assert doc.scene[b].shape.volume == pytest.approx(50 * 40 * 20, rel=1e-6)


def test_push_face_non_planar_rejected():
    doc = Document()
    c = doc.execute("create_cylinder", {"radius": 10, "height": 30})
    # ojo: el centroide de la cara cilíndrica cae en la costura (-r, 0, 0)
    with pytest.raises(DocumentError, match="(?i)plana"):
        doc.execute("push_face", {"feature": c,
                                  "face": {"mode": "cerca", "point": [-10, 0, 0], "count": 1},
                                  "distance": 5})


def test_push_face_with_hole_extends_hole():
    doc = Document()
    b = _box(doc)
    doc.execute("drill_hole", {"feature": b, "position": {"x": 0, "y": 0, "z": 15},
                               "axis": "-z", "diameter": 10, "depth": 0})
    doc.execute("push_face", {"feature": b, "face": {"mode": "cara", "face": "tope"},
                              "distance": 10})
    expected = 50 * 40 * 40 - math.pi * 25 * 40  # el agujero se extiende con la cara
    assert doc.scene[b].shape.volume == pytest.approx(expected, rel=1e-6)


def test_push_face_selector_must_resolve_one():
    doc = Document()
    b = _box(doc)
    with pytest.raises(DocumentError, match="EXACTAMENTE"):
        doc.execute("push_face", {"feature": b, "face": {"mode": "direccion", "direction": "z"},
                                  "distance": 5})


def test_push_face_parametric_expression():
    doc = Document()
    doc.execute("set_variable", {"name": "h_extra", "expression": "10"})
    b = _box(doc)
    doc.execute("push_face", {"feature": b, "face": {"mode": "cara", "face": "tope"},
                              "distance": "=h_extra"})
    assert doc.scene[b].shape.volume == pytest.approx(50 * 40 * 40, rel=1e-6)
    var = next(c["id"] for c in doc.commands if c["type"] == "set_variable")
    doc.edit(var, {"name": "h_extra", "expression": "20"})
    assert doc.scene[b].shape.volume == pytest.approx(50 * 40 * 50, rel=1e-6)


# --------------------------------------------------- STEP + roundtrip + varios
def test_step_import_defeature_roundtrip():
    # el log re-resuelve el selector al regenerar: corazón del diseño declarativo.
    # Donante: caja con el anillo de fillet del TOPE (cadena tangente completa).
    src = Document()
    sb = _box(src)
    src.execute("fillet", {"feature": sb, "edges": {"mode": "cara", "face": "tope"},
                           "radius": 5})
    data = _step_bytes_of(src.scene[sb].shape)

    doc = Document()
    digest = doc.add_attachment(data)
    fid = doc.execute("import_step", {"attachment": digest, "name": "Proveedor"})
    doc.execute("delete_faces", {"feature": fid, "tangentes": True,
                                 "faces": {"mode": "cerca", "point": [0, 20, 15], "count": 1}})
    assert doc.scene[fid].shape.volume == pytest.approx(V0, rel=1e-4)
    doc.execute("push_face", {"feature": fid, "face": {"mode": "cara", "face": "tope"},
                              "distance": 10})
    expected = 50 * 40 * 40
    assert doc.scene[fid].shape.volume == pytest.approx(expected, rel=1e-4)

    doc2 = Document.from_apolo_bytes(doc.to_apolo_bytes())
    assert doc2.scene[fid].shape.volume == pytest.approx(expected, rel=1e-4)


def test_delete_faces_clears_instancing():
    doc = Document()
    b = _box(doc)
    doc.execute("drill_hole", {"feature": b, "position": {"x": 0, "y": 0, "z": 15},
                               "axis": "-z", "diameter": 10, "depth": 0})
    doc.execute("delete_faces", {"feature": b,
                                 "faces": {"mode": "cerca", "point": [5, 0, 0], "count": 1}})
    feat = doc.scene[b]
    assert feat.mesh_key is None and feat.matrix is None  # make_unique


# ------------------------------------------------------------------- API HTTP
from fastapi.testclient import TestClient  # noqa: E402

import apolo.api.main as api  # noqa: E402


def test_api_push_face_with_cerca_selector():
    api.DOC = Document("v53-api")
    client = TestClient(api.app)
    r = client.post("/api/commands", json={"type": "create_box",
                                           "params": {"width": 50, "depth": 40, "height": 30}})
    fid = r.json()["features"][0]["id"]
    r = client.post("/api/commands", json={
        "type": "push_face",
        "params": {"feature": fid,
                   "face": {"mode": "cerca", "point": [0, 0, 15], "count": 1},
                   "distance": 10},
    })
    assert r.status_code == 200
    assert r.json()["features"][0]["volume_mm3"] == pytest.approx(50 * 40 * 40, rel=1e-6)
