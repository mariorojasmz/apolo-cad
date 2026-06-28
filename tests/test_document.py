import copy
import math

import pytest

from apolo.doc import Document, DocumentError


def _fingerprint(doc):
    """Huella de la escena: ids + volumen redondeado (invariante a comparar)."""
    return sorted((fid, round(f.shape.volume, 2)) for fid, f in doc.scene.items())


def _full_rebuild(doc):
    """Reconstruye el mismo log en un Document nuevo (caché vacía → regenerate
    completo desde cero), para comparar contra el resultado incremental."""
    fresh = Document(doc.name)
    fresh.commands = copy.deepcopy(doc.commands)
    fresh.hidden = set(doc.hidden)
    fresh._seq = doc._seq
    fresh.regenerate()
    return fresh


def test_incremental_regenerate_equals_full():
    """El regenerate INCREMENTAL produce exactamente la misma escena que el
    rebuild completo, tras append, edición en medio, edición de variable, undo/redo.
    Log largo (>_REGEN_STRIDE) para ejercitar varios checkpoints."""
    doc = Document()
    first = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100})
    for i in range(20):
        doc.execute("create_box", {"width": 50, "depth": 50, "height": 50, "position": {"x": (i + 1) * 70}})
    var_cmd = doc.execute("set_variable", {"name": "R", "expression": "10"})
    doc.execute("create_cylinder", {"radius": "=R", "height": 40, "position": {"y": 300}})

    assert _fingerprint(doc) == _fingerprint(_full_rebuild(doc))            # append/construcción

    doc.edit(first, {"width": 220, "depth": 120, "height": 80})
    assert _fingerprint(doc) == _fingerprint(_full_rebuild(doc))            # edición en medio

    doc.edit(var_cmd, {"name": "R", "expression": "25"})
    assert _fingerprint(doc) == _fingerprint(_full_rebuild(doc))            # edición de variable

    doc.undo()
    assert _fingerprint(doc) == _fingerprint(_full_rebuild(doc))            # undo
    doc.redo()
    assert _fingerprint(doc) == _fingerprint(_full_rebuild(doc))            # redo


def _box_size(doc, cid):
    bb = doc.scene[cid].shape.bounding_box()
    return (round(bb.max.X - bb.min.X), round(bb.max.Y - bb.min.Y), round(bb.max.Z - bb.min.Z))


def test_edit_replace_resets_omitted_to_default():
    """Sin merge (default): los campos omitidos vuelven a su default Pydantic."""
    doc = Document()
    cid = doc.execute("create_box", {"width": 80, "depth": 120, "height": 60})
    ret = doc.edit(cid, {"width": 200})
    assert ret == cid  # edit ahora devuelve el command_id
    assert _box_size(doc, cid) == (200, 100, 100)  # depth/height → default 100


def test_edit_merge_keeps_other_params():
    """Con merge=True: PATCH, conserva los params no enviados."""
    doc = Document()
    cid = doc.execute("create_box", {"width": 80, "depth": 120, "height": 60})
    assert doc.edit(cid, {"width": 200}, merge=True) == cid
    assert _box_size(doc, cid) == (200, 120, 60)


def test_edit_merge_validates_combined():
    """El merge se valida; un valor inválido NO muta el comando (rollback de validación)."""
    from apolo.commands.registry import CommandError

    doc = Document()
    cid = doc.execute("create_box", {"width": 80, "depth": 120, "height": 60})
    with pytest.raises((CommandError, DocumentError)):
        doc.edit(cid, {"width": -1}, merge=True)
    assert doc.commands[-1]["params"]["width"] == 80  # intacto


def test_edit_merge_shallow_replaces_subobject():
    """Merge SUPERFICIAL: un sub-objeto (position) se reemplaza entero, no se fusiona."""
    doc = Document()
    cid = doc.execute(
        "create_box",
        {"width": 100, "depth": 100, "height": 100, "position": {"x": 10, "y": 20, "z": 30}},
    )
    doc.edit(cid, {"position": {"x": 5}}, merge=True)
    bb = doc.scene[cid].shape.bounding_box()
    assert round((bb.max.X + bb.min.X) / 2) == 5
    assert round((bb.max.Y + bb.min.Y) / 2) == 0  # y vuelve a 0 (no se conserva el 20)


def test_edit_many_equals_sequential_and_single_undo():
    """edit_many produce la MISMA escena que aplicar los edits uno a uno, y es UN solo
    paso de undo (un solo undo revierte TODO el lote)."""
    doc = Document()
    a = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100})
    b = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": 200}})
    c = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": 400}})
    touched = doc.edit_many(
        [
            {"command_id": a, "params": {"width": 200, "depth": 100, "height": 100}},
            {"command_id": b, "params": {"width": 100, "depth": 300, "height": 100, "position": {"x": 200}}},
            {"command_id": c, "params": {"width": 100, "depth": 100, "height": 250, "position": {"x": 400}}},
        ]
    )
    assert touched == [a, b, c]

    seq = Document()
    a2 = seq.execute("create_box", {"width": 100, "depth": 100, "height": 100})
    b2 = seq.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": 200}})
    c2 = seq.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": 400}})
    seq.edit(a2, {"width": 200, "depth": 100, "height": 100})
    seq.edit(b2, {"width": 100, "depth": 300, "height": 100, "position": {"x": 200}})
    seq.edit(c2, {"width": 100, "depth": 100, "height": 250, "position": {"x": 400}})
    assert _fingerprint(doc) == _fingerprint(seq)            # lote == secuencial

    doc.undo()                                               # UN solo undo revierte los 3
    assert _box_size(doc, a) == (100, 100, 100)
    assert _box_size(doc, b) == (100, 100, 100)
    assert _box_size(doc, c) == (100, 100, 100)


def test_edit_many_atomic_rollback():
    """Si una edición del lote falla en el regenerate, se revierte TODO (o todo o nada)."""
    from apolo.commands.registry import CommandError

    doc = Document()
    a = doc.execute("create_box", {"width": 80, "depth": 120, "height": 60})
    b = doc.execute("create_box", {"width": 80, "depth": 120, "height": 60, "position": {"x": 300}})
    with pytest.raises((CommandError, DocumentError)):
        doc.edit_many(
            [
                {"command_id": a, "params": {"width": 200, "depth": 120, "height": 60}},
                {"command_id": b, "params": {"width": -1, "depth": 120, "height": 60}},  # inválido
            ]
        )
    # rollback total: ni 'a' (válido) queda editado
    assert doc.commands[0]["params"]["width"] == 80
    assert doc.commands[1]["params"]["width"] == 80
    assert _box_size(doc, a) == (80, 120, 60)


def test_edit_many_missing_id_rolls_back():
    """Un command_id inexistente en el lote → DocumentError y nada cambia."""
    doc = Document()
    a = doc.execute("create_box", {"width": 80, "depth": 120, "height": 60})
    with pytest.raises(DocumentError):
        doc.edit_many(
            [
                {"command_id": a, "params": {"width": 200, "depth": 120, "height": 60}},
                {"command_id": "cZ", "params": {"width": 50}},  # no existe
            ]
        )
    assert _box_size(doc, a) == (80, 120, 60)


def test_edit_many_codependent_variable_and_use():
    """Editar un set_variable + un comando que lo usa en el MISMO lote (sin pre-validar;
    el regenerate valida con la variable ya en su nuevo valor)."""
    doc = Document()
    var = doc.execute("set_variable", {"name": "R", "expression": "10"})
    cyl = doc.execute("create_cylinder", {"radius": "=R", "height": 40})
    doc.edit_many(
        [
            {"command_id": var, "params": {"name": "R", "expression": "30"}},
            {"command_id": cyl, "params": {"radius": "=R", "height": 80}},
        ]
    )
    bb = doc.scene[cyl].shape.bounding_box()
    assert round(bb.max.X - bb.min.X) == 60   # diámetro = 2*R = 60
    assert round(bb.max.Z - bb.min.Z) == 80


def test_edit_many_merge_vs_replace():
    """merge=True conserva los params no enviados; merge=False (default) los resetea."""
    doc = Document()
    a = doc.execute("create_box", {"width": 80, "depth": 120, "height": 60})
    b = doc.execute("create_box", {"width": 80, "depth": 120, "height": 60, "position": {"x": 300}})
    doc.edit_many(
        [{"command_id": a, "params": {"width": 200}}, {"command_id": b, "params": {"width": 200}}],
        merge=True,
    )
    assert _box_size(doc, a) == (200, 120, 60) and _box_size(doc, b) == (200, 120, 60)
    doc.edit_many([{"command_id": a, "params": {"width": 150}}])  # merge=False
    assert _box_size(doc, a) == (150, 100, 100)  # depth/height → default 100


def test_preview_does_not_mutate():
    """preview aplica acciones sobre una COPIA: devuelve la escena resultante y los ids
    nuevos sin tocar el documento real."""
    doc = Document()
    doc.execute("create_box", {"width": 100, "depth": 100, "height": 100})
    before = len(doc.commands)
    scene, new_ids = doc.preview(
        [{"type": "create_box", "params": {"width": 50, "position": {"x": 300}}}]
    )
    assert len(new_ids) == 1
    assert len(scene) == 2            # la copia ve las 2 cajas
    assert len(doc.scene) == 1        # el documento real, intacto
    assert len(doc.commands) == before


def test_pattern_group_regenerates_after_source_edit():
    """pattern_group reproduce las features del comando fuente y se regenera (incremental
    == rebuild completo) al editar la fuente; las copias reflejan el nuevo tamaño."""
    doc = Document()
    box = doc.execute("create_box", {"width": 50, "depth": 50, "height": 50})
    grp = doc.execute("pattern_group", {"source": box, "count": 3, "spacing": {"x": 200}})
    assert _fingerprint(doc) == _fingerprint(_full_rebuild(doc))
    doc.edit(box, {"width": 120, "depth": 50, "height": 50})
    assert _fingerprint(doc) == _fingerprint(_full_rebuild(doc))
    copies = [f for f in doc.scene.values() if f.command_id == grp]
    assert copies and all(round(f.shape.volume) == 120 * 50 * 50 for f in copies)


def test_undo_redo_cycle():
    doc = Document()
    a = doc.execute("create_box", {})
    b = doc.execute("create_cylinder", {})
    assert set(doc.scene) == {a, b}
    doc.undo()
    assert set(doc.scene) == {a}
    doc.undo()
    assert doc.scene == {}
    assert not doc.can_undo
    doc.redo()
    doc.redo()
    assert set(doc.scene) == {a, b}
    with pytest.raises(DocumentError):
        doc.redo()


def test_parametric_edit_regenerates_downstream():
    doc = Document()
    box = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100})
    cyl = doc.execute("create_cylinder", {"radius": 10, "height": 300})
    doc.execute("boolean_op", {"operation": "cut", "target": box, "tools": [cyl]})
    before = next(iter(doc.scene.values())).shape.volume

    doc.edit(cyl, {"radius": 30, "height": 300})
    after = next(iter(doc.scene.values())).shape.volume
    assert after < before
    expected = 100**3 - math.pi * 30**2 * 100
    assert math.isclose(after, expected, rel_tol=1e-3)


def test_edit_failure_rolls_back():
    doc = Document()
    box = doc.execute("create_box", {})
    cyl = doc.execute("create_cylinder", {"radius": 10, "height": 300})
    doc.execute("boolean_op", {"operation": "cut", "target": box, "tools": [cyl]})
    # editar el cilindro para que no toque la caja produce un corte sin efecto,
    # pero moverlo fuera no es error; en cambio borrar la referencia sí:
    with pytest.raises(DocumentError):
        doc.edit("c999", {"radius": 5})
    assert len(doc.commands) == 3


def test_visibility_toggle_persists():
    doc = Document()
    fid = doc.execute("create_box", {})
    doc.set_visibility(fid, False)
    data = doc.to_apolo_bytes()
    doc2 = Document.from_apolo_bytes(data)
    assert doc2.scene[fid].visible is False


def test_apolo_roundtrip():
    doc = Document("mi proyecto")
    doc.execute("create_structural_profile", {"profile": "40x40", "length": 800})
    doc.execute("create_box", {"width": 10, "depth": 20, "height": 30, "position": {"x": 100}})
    data = doc.to_apolo_bytes()

    doc2 = Document.from_apolo_bytes(data)
    assert doc2.name == "mi proyecto"
    assert [c["id"] for c in doc2.commands] == [c["id"] for c in doc.commands]
    for fid in doc.scene:
        assert math.isclose(doc2.scene[fid].shape.volume, doc.scene[fid].shape.volume, rel_tol=1e-9)
    # la numeración continúa sin colisiones tras abrir
    new_id = doc2.execute("create_box", {})
    assert new_id not in [c["id"] for c in doc.commands]


def test_invalid_apolo_bytes():
    with pytest.raises(DocumentError):
        Document.from_apolo_bytes(b"esto no es un zip")
