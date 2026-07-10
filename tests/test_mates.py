"""Mates persistentes (V3 bloque #2): relaciones de ensamblaje que se
re-resuelven en cada regeneración (a diferencia de attach, one-shot)."""
import math

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.commands.registry import CommandError
from apolo.doc import Document, DocumentError


def _two_boxes(d, bz=200):
    a = d.execute("create_box", {"name": "A", "width": 100, "depth": 100, "height": 40})
    b = d.execute("create_box", {"name": "B", "width": 40, "depth": 40, "height": 40,
                                 "position": {"x": 500, "y": 300, "z": bz}})
    return a, b


def _coincide(d, a, b, **extra):
    return d.execute("add_mate", {
        "name": "m1", "type": "coincidente", "feature_a": a, "feature_b": b,
        "ref_a": {"mode": "cara", "face": "tope"}, "ref_b": {"mode": "cara", "face": "base"},
        **extra,
    })


# ------------------------------------------------------------- tipos de mate
def test_coincidente_flush():
    d = Document()
    a, b = _two_boxes(d)
    _coincide(d, a, b)
    bb = d.scene[b].shape.bounding_box()
    assert bb.min.Z == pytest.approx(20, abs=1e-3)          # a ras del tope de A (z=+20)
    assert (bb.min.X + bb.max.X) / 2 == pytest.approx(0, abs=1e-3)  # centrado sobre A
    assert (bb.min.Y + bb.max.Y) / 2 == pytest.approx(0, abs=1e-3)


def test_mate_is_persistent():
    """El diferenciador frente a attach: editar A recoloca B sola."""
    d = Document()
    a, b = _two_boxes(d)
    _coincide(d, a, b)
    assert d.scene[b].shape.bounding_box().min.Z == pytest.approx(20, abs=1e-3)
    # subir A a alto 80 (tope z=+40) → B debe seguir pegada
    d.edit(d.commands[0]["id"], {"name": "A", "width": 100, "depth": 100, "height": 80})
    assert d.scene[b].shape.bounding_box().min.Z == pytest.approx(40, abs=1e-3)


def test_distancia_con_expresion():
    d = Document()
    d.execute("set_variable", {"name": "gap", "expression": "25"})
    a, b = _two_boxes(d)
    d.execute("add_mate", {
        "name": "m1", "type": "distancia", "feature_a": a, "feature_b": b,
        "ref_a": {"mode": "cara", "face": "tope"}, "ref_b": {"mode": "cara", "face": "base"},
        "value": "=gap",
    })
    assert d.scene[b].shape.bounding_box().min.Z == pytest.approx(45, abs=1e-3)  # 20 + 25
    # cambiar la variable propaga
    var = next(c["id"] for c in d.commands if c["type"] == "set_variable")
    d.edit(var, {"name": "gap", "expression": "10"})
    assert d.scene[b].shape.bounding_box().min.Z == pytest.approx(30, abs=1e-3)


def test_concentrico_tornillo_en_agujero():
    d = Document()
    placa = d.execute("create_box", {"name": "placa", "width": 120, "depth": 80, "height": 15})
    d.execute("drill_hole", {"feature": placa, "position": {"x": 0, "y": 0, "z": -7.5},
                             "axis": "z", "diameter": 8.5, "depth": 0})
    torn = d.execute("insert_component", {"component": "DIN912-M8", "position": {"x": 400}})
    d.execute("add_mate", {
        "name": "t1", "type": "concentrico", "feature_a": placa, "feature_b": torn,
        "ref_a": {"mode": "cerca", "point": [0, 4.25, 0]},
        "ref_b": {"mode": "cerca", "point": [400, 4, -5]},
    })
    bb = d.scene[torn].shape.bounding_box()
    assert (bb.min.X + bb.max.X) / 2 == pytest.approx(0, abs=1e-2)  # eje del tornillo en el agujero
    assert (bb.min.Y + bb.max.Y) / 2 == pytest.approx(0, abs=1e-2)


def test_flip_invierte_lado():
    d = Document()
    a, b = _two_boxes(d)
    _coincide(d, a, b, flip=True)
    # con flip sigue a ras (el giro es alrededor del eje normal) → mismo z
    assert d.scene[b].shape.bounding_box().min.Z == pytest.approx(20, abs=1e-3)


def test_mate_sobre_instancia():
    """Una instancia de catálogo (mesh_key+matrix) se recoloca y mantiene matrix."""
    d = Document()
    a = d.execute("create_box", {"name": "A", "width": 200, "depth": 200, "height": 40})
    perfil = d.execute("insert_component", {"component": "PERFIL-4040", "length": 100,
                                            "position": {"x": 600}})
    d.execute("add_mate", {
        "name": "m1", "type": "coincidente", "feature_a": a, "feature_b": perfil,
        "ref_a": {"mode": "cara", "face": "tope"}, "ref_b": {"mode": "cara", "face": "base"},
    })
    feat = d.scene[perfil]
    assert feat.matrix is not None  # sigue siendo instancia
    assert feat.shape.bounding_box().min.Z == pytest.approx(20, abs=1e-3)


# --------------------------------------------------------- integridad / validación
def test_borrar_referencia_falla_y_revierte():
    d = Document()
    a, b = _two_boxes(d)
    _coincide(d, a, b)
    n = len(d.commands)
    with pytest.raises(DocumentError):
        d.execute("delete_feature", {"feature": a})
    assert len(d.commands) == n          # rollback
    assert "m1" in d.mates


def test_validaciones():
    d = Document()
    a, b = _two_boxes(d)
    _coincide(d, a, b)
    with pytest.raises(DocumentError, match="existe"):
        _coincide(d, a, b)  # nombre duplicado
    # V6.3a: un 2º mate al mismo hijo YA se permite (multi-mate) — antes se rechazaba
    d.execute("add_mate", {"name": "m2", "type": "coincidente", "feature_a": a, "feature_b": b})
    assert "m2" in d.mates
    c = d.execute("create_box", {"name": "C", "width": 20, "depth": 20, "height": 20})
    with pytest.raises(DocumentError, match="consigo mismo"):
        d.execute("add_mate", {"name": "m3", "type": "coincidente", "feature_a": c, "feature_b": c})


def test_no_ciclo():
    d = Document()
    a = d.execute("create_box", {"name": "A"})
    b = d.execute("create_box", {"name": "B", "position": {"x": 200}})
    d.execute("add_mate", {"name": "m1", "type": "coincidente", "feature_a": a, "feature_b": b})
    with pytest.raises(DocumentError, match="ciclo"):
        d.execute("add_mate", {"name": "m2", "type": "coincidente", "feature_a": b, "feature_b": a})


def test_tipo_desconocido_rechazado():
    d = Document()
    a, b = _two_boxes(d)
    with pytest.raises((CommandError, DocumentError)):
        d.execute("add_mate", {"name": "m1", "type": "magia", "feature_a": a, "feature_b": b})


def test_roundtrip_preserva_mates():
    d = Document()
    a, b = _two_boxes(d)
    _coincide(d, a, b)
    d2 = Document.from_apolo_bytes(d.to_apolo_bytes())
    assert list(d2.mates.keys()) == ["m1"]
    assert d2.scene[b].shape.bounding_box().min.Z == pytest.approx(20, abs=1e-3)


# ========================================================= V6.3a — multi-mate
def test_residuos_consistentes_con_camino_cerrado():
    """Equivalencia (cada tipo, tol 1e-6): la POSE que produce el camino cerrado
    (`_desired_current_frames`) deja los residuos del solver multi-mate en ~0 → ambas
    semánticas coinciden a residuo cero. Se usan frames SINTÉTICOS (no geometría) para no
    depender de que el selector declarativo re-resuelva a la misma cara tras rotar B."""
    from apolo.assembly.mates import _desired_current_frames, _mate_residuals, _normalize

    a_o = (1.0, 2.0, 3.0)
    a_ax = _normalize((0.2, 0.3, 1.0))          # eje del padre arbitrario (no axial)
    b_o0 = (10.0, -5.0, 7.0)                     # conector ACTUAL de B (para paralelo/angulo)
    b_ax0 = _normalize((1.0, 0.4, 0.1))
    L = 40.0

    for tipo, value in [("coincidente", 0.0), ("distancia", 25.0),
                        ("concentrico", 12.0), ("paralelo", 0.0), ("angulo", 30.0)]:
        desired, _cur = _desired_current_frames(a_o, a_ax, b_o0, b_ax0, tipo, value, False)
        # el conector de B tras el camino cerrado = origen + eje Z del frame `desired`
        b_o = (desired[0][3], desired[1][3], desired[2][3])
        b_ax = (desired[0][2], desired[1][2], desired[2][2])
        r = _mate_residuals(a_o, a_ax, b_o, b_ax, tipo, value, False, L)
        assert max(abs(x) for x in r) < 1e-6, f"{tipo}: residuo no nulo {r}"


def test_multi_mate_placa_dos_coincidentes_ortogonales():
    """Una placa coincidente a un piso (+Z) Y a una pared (+X): se asienta en la esquina
    (z del piso, x de la pared); el deslizamiento libre (Y) queda en el guess."""
    d = Document()
    piso = d.execute("create_box", {"name": "piso", "width": 400, "depth": 400, "height": 20})
    pared = d.execute("create_box", {"name": "pared", "width": 20, "depth": 400, "height": 200,
                                     "position": {"x": -100, "z": 0}})
    placa = d.execute("create_box", {"name": "placa", "width": 100, "depth": 100, "height": 10,
                                     "position": {"x": 0, "y": 0, "z": 200}})
    d.execute("add_mate", {"name": "m_piso", "type": "coincidente", "feature_a": piso,
                           "feature_b": placa, "ref_a": {"mode": "cara", "face": "tope"},
                           "ref_b": {"mode": "cara", "face": "base"}})
    d.execute("add_mate", {"name": "m_pared", "type": "coincidente", "feature_a": pared,
                           "feature_b": placa, "ref_a": {"mode": "cara", "face": "max_x"},
                           "ref_b": {"mode": "cara", "face": "min_x"}})
    bb = d.scene[placa].shape.bounding_box()
    assert bb.min.Z == pytest.approx(10, abs=1e-2)   # a ras del tope del piso (z=+10)
    assert bb.min.X == pytest.approx(-90, abs=1e-2)  # a ras de la cara +X de la pared (x=-90)


def test_multi_mate_mensula_coincidente_y_concentrico():
    """Ménsula coincidente a una placa base + concéntrica a un pin vertical: se asienta en Z
    y su barreno queda centrado sobre el eje del pin (X,Y). La ménsula (B) es hijo de AMBOS."""
    d = Document()
    base = d.execute("create_box", {"name": "base", "width": 200, "depth": 200, "height": 20})
    pin = d.execute("create_cylinder", {"name": "pin", "radius": 5, "height": 120, "axis": "z",
                                        "position": {"x": 50, "y": 0, "z": 0}})
    mensula = d.execute("create_box", {"name": "mensula", "width": 60, "depth": 60, "height": 20,
                                       "position": {"x": 50, "y": 0, "z": 200}})
    d.execute("drill_hole", {"feature": mensula, "position": {"x": 50, "y": 0, "z": 190},
                             "axis": "z", "diameter": 10.5, "depth": 0})
    d.execute("add_mate", {"name": "m_seat", "type": "coincidente", "feature_a": base,
                           "feature_b": mensula, "ref_a": {"mode": "cara", "face": "tope"},
                           "ref_b": {"mode": "cara", "face": "base"}})
    d.execute("add_mate", {"name": "m_pin", "type": "concentrico", "feature_a": pin,
                           "feature_b": mensula,
                           "ref_a": {"mode": "cerca", "point": [55, 0, 60]},     # pared del pin
                           "ref_b": {"mode": "cerca", "point": [55.25, 0, 200]}})  # pared del barreno
    bb = d.scene[mensula].shape.bounding_box()
    assert bb.min.Z == pytest.approx(10, abs=1e-2)                       # asentada en la base
    assert (bb.min.X + bb.max.X) / 2 == pytest.approx(50, abs=1e-2)      # barreno sobre el pin
    assert (bb.min.Y + bb.max.Y) / 2 == pytest.approx(0, abs=1e-2)


def test_multi_mate_conflicto_imposible():
    """Dos 'distancia' contradictorias sobre el mismo hijo → MateError nombrando los mates."""
    d = Document()
    a, b = _two_boxes(d)
    d.execute("add_mate", {"name": "d1", "type": "distancia", "feature_a": a, "feature_b": b,
                           "ref_a": {"mode": "cara", "face": "tope"},
                           "ref_b": {"mode": "cara", "face": "base"}, "value": 10})
    with pytest.raises(DocumentError, match="d2|d1|satisfacer"):
        d.execute("add_mate", {"name": "d2", "type": "distancia", "feature_a": a, "feature_b": b,
                               "ref_a": {"mode": "cara", "face": "tope"},
                               "ref_b": {"mode": "cara", "face": "base"}, "value": 80})


def test_multi_mate_ciclo_multipadre_rechazado():
    """C con dos padres (A, B) es válido; cerrar el lazo (C→A) se rechaza como ciclo."""
    d = Document()
    a = d.execute("create_box", {"name": "A", "width": 200, "depth": 200, "height": 20})
    b = d.execute("create_box", {"name": "B", "width": 20, "depth": 200, "height": 200,
                                 "position": {"x": -120}})
    c = d.execute("create_box", {"name": "C", "width": 60, "depth": 60, "height": 10,
                                 "position": {"z": 150}})
    d.execute("add_mate", {"name": "m1", "type": "coincidente", "feature_a": a, "feature_b": c,
                           "ref_a": {"mode": "cara", "face": "tope"},
                           "ref_b": {"mode": "cara", "face": "base"}})
    d.execute("add_mate", {"name": "m2", "type": "coincidente", "feature_a": b, "feature_b": c,
                           "ref_a": {"mode": "cara", "face": "max_x"},
                           "ref_b": {"mode": "cara", "face": "min_x"}})  # C: dos padres, OK
    with pytest.raises(DocumentError, match="ciclo"):
        d.execute("add_mate", {"name": "m3", "type": "coincidente", "feature_a": c, "feature_b": a})


def test_multi_mate_regenera_tras_editar_padre():
    """Editar la geometría del padre re-resuelve el multi-mate (persistente)."""
    d = Document()
    piso = d.execute("create_box", {"name": "piso", "width": 400, "depth": 400, "height": 20})
    pared = d.execute("create_box", {"name": "pared", "width": 20, "depth": 400, "height": 200,
                                     "position": {"x": -100, "z": 0}})
    placa = d.execute("create_box", {"name": "placa", "width": 100, "depth": 100, "height": 10,
                                     "position": {"x": 0, "y": 0, "z": 200}})
    d.execute("add_mate", {"name": "m_piso", "type": "coincidente", "feature_a": piso,
                           "feature_b": placa, "ref_a": {"mode": "cara", "face": "tope"},
                           "ref_b": {"mode": "cara", "face": "base"}})
    d.execute("add_mate", {"name": "m_pared", "type": "coincidente", "feature_a": pared,
                           "feature_b": placa, "ref_a": {"mode": "cara", "face": "max_x"},
                           "ref_b": {"mode": "cara", "face": "min_x"}})
    assert d.scene[placa].shape.bounding_box().min.Z == pytest.approx(10, abs=1e-2)
    # subir el piso a alto 60 (tope z=+30) → la placa sigue asentada
    piso_cmd = d.commands[0]["id"]
    d.edit(piso_cmd, {"name": "piso", "width": 400, "depth": 400, "height": 60})
    assert d.scene[placa].shape.bounding_box().min.Z == pytest.approx(30, abs=1e-2)


def test_multi_mate_undo_redo():
    d = Document()
    piso = d.execute("create_box", {"name": "piso", "width": 400, "depth": 400, "height": 20})
    pared = d.execute("create_box", {"name": "pared", "width": 20, "depth": 400, "height": 200,
                                     "position": {"x": -100, "z": 0}})
    placa = d.execute("create_box", {"name": "placa", "width": 100, "depth": 100, "height": 10,
                                     "position": {"x": 0, "y": 0, "z": 200}})
    d.execute("add_mate", {"name": "m_piso", "type": "coincidente", "feature_a": piso,
                           "feature_b": placa, "ref_a": {"mode": "cara", "face": "tope"},
                           "ref_b": {"mode": "cara", "face": "base"}})
    d.execute("add_mate", {"name": "m_pared", "type": "coincidente", "feature_a": pared,
                           "feature_b": placa, "ref_a": {"mode": "cara", "face": "max_x"},
                           "ref_b": {"mode": "cara", "face": "min_x"}})
    assert d.scene[placa].shape.bounding_box().min.X == pytest.approx(-90, abs=1e-2)
    d.undo()  # quita m_pared → placa vuelve a 1 mate (solo el piso)
    assert "m_pared" not in d.mates
    d.redo()
    assert "m_pared" in d.mates
    assert d.scene[placa].shape.bounding_box().min.X == pytest.approx(-90, abs=1e-2)


# ----------------------------------------------------------------- API HTTP
def test_api_mates_crud():
    api.DOC = Document("mate-test")
    client = TestClient(api.app)
    a = client.post("/api/commands", json={"type": "create_box", "params": {"name": "A"}}).json()
    a_id = a["features"][0]["id"]
    client.post("/api/commands", json={"type": "create_box", "params": {"name": "B", "position": {"x": 300}}})
    b_id = next(f["id"] for f in client.get("/api/scene").json()["features"] if f["name"] == "B")
    r = client.post("/api/commands", json={"type": "add_mate", "params": {
        "name": "m1", "type": "coincidente", "feature_a": a_id, "feature_b": b_id,
        "ref_a": {"mode": "cara", "face": "tope"}, "ref_b": {"mode": "cara", "face": "base"}}})
    assert r.status_code == 200
    mates = client.get("/api/mates").json()
    assert [m["name"] for m in mates] == ["m1"]
    assert client.delete("/api/mates/m1").status_code == 200
    assert client.get("/api/mates").json() == []
    assert client.delete("/api/mates/nope").status_code == 404
