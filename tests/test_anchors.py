"""Conectores por ancla y arista circular (V6.3b).

Las anclas de conexión con nombre (`Feature.anchors`, coords MUNDO) las publican los
executors al colocar el componente (chumacera→"centro", NMRV→"bore", faja→"eje_motriz"/
"eje_cola"); se re-calculan solos en cada regenerate y viajan con la pieza en TODO camino
que la mueva (mates, transform_group, insert_project). Un mate puede referenciar un ancla
(`{"mode":"ancla","name":...}`) o una arista CIRCULAR (`{"entidad":"arista", ...}`).
"""
import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document


# --------------------------------------------------------------- publicación
def test_chumacera_publica_ancla_centro():
    d = Document()
    ch = d.execute("insert_component", {"component": "UCP205",
                                        "position": {"x": 100, "y": 50, "z": 30}})
    anc = d.scene[ch].anchors
    assert set(anc) == {"centro"}
    assert anc["centro"]["origin"] == pytest.approx([100, 50, 30])   # centro del barreno = pose
    assert anc["centro"]["axis"] == pytest.approx([0, 1, 0])          # eje del rodamiento (Y)


def test_nmrv_publica_ancla_bore():
    d = Document()
    n = d.execute("insert_component", {"component": "NMRV-040", "position": {"x": 0, "y": 0, "z": 0}})
    anc = d.scene[n].anchors
    assert set(anc) == {"bore"}
    assert anc["bore"]["axis"] == pytest.approx([0, 1, 0])


def test_faja_publica_ejes_motriz_y_cola():
    d = Document()
    d.execute("create_belt_conveyor", {"largo": 3000, "ancho_banda": 500, "altura": 700})
    ejes = {name: f.anchors for f in d.scene.values() if f.anchors for name in f.anchors}
    assert "eje_motriz" in ejes and "eje_cola" in ejes
    motriz = next(f.anchors["eje_motriz"] for f in d.scene.values()
                  if f.anchors and "eje_motriz" in f.anchors)
    cola = next(f.anchors["eje_cola"] for f in d.scene.values()
                if f.anchors and "eje_cola" in f.anchors)
    assert motriz["origin"][0] > 0 > cola["origin"][0]  # motriz en +X, cola en -X


def test_conveyor_rodillos_publican_ejes_extremos():
    d = Document()
    d.execute("create_conveyor", {"largo": 2000, "ancho": 600, "altura": 700, "paso": 150})
    names = {name for f in d.scene.values() if f.anchors for name in f.anchors}
    assert names == {"eje_motriz", "eje_cola"}


# ------------------------------------------------------------- mate por ancla
def test_mate_concentrico_por_ancla_centro():
    """Chumacera mateada concéntrica por el ancla 'centro' contra un eje cilíndrico → su
    centro cae SOBRE el eje del cilindro (se mide)."""
    d = Document()
    eje = d.execute("create_cylinder", {"name": "eje", "radius": 17.5, "height": 600,
                                        "axis": "y", "position": {"x": 200, "y": 0, "z": 300}})
    ch = d.execute("insert_component", {"component": "UCP205", "name": "chumA",
                                        "position": {"x": -500, "y": 0, "z": 0}})
    d.execute("add_mate", {"name": "m1", "type": "concentrico", "feature_a": eje, "feature_b": ch,
                           "ref_a": {"mode": "cerca", "point": [217.5, 0, 300]},
                           "ref_b": {"mode": "ancla", "name": "centro"}})
    a = d.scene[ch].anchors["centro"]
    assert a["origin"][0] == pytest.approx(200, abs=1e-2)   # el centro cae sobre el eje (x=200)
    assert a["origin"][2] == pytest.approx(300, abs=1e-2)   # ...y a la altura del eje (z=300)
    assert a["axis"] == pytest.approx([0, 1, 0], abs=1e-6)  # eje Y, colineal con el cilindro


def test_mate_ancla_inexistente_error():
    from apolo.doc import DocumentError

    d = Document()
    eje = d.execute("create_cylinder", {"name": "eje", "radius": 10, "height": 200, "axis": "y"})
    ch = d.execute("insert_component", {"component": "UCP205", "position": {"x": -500}})
    with pytest.raises(DocumentError, match="ancla|no publica"):
        d.execute("add_mate", {"name": "m", "type": "concentrico", "feature_a": eje,
                               "feature_b": ch, "ref_a": {"mode": "cerca", "point": [10, 0, 0]},
                               "ref_b": {"mode": "ancla", "name": "no_existe"}})


# ---------------------------------------------------------- arista circular
def test_mate_concentrico_por_arista_circular():
    """Mate concéntrico al BORDE (arista circular) de un barreno → el pin se centra en él."""
    d = Document()
    placa = d.execute("create_box", {"name": "placa", "width": 120, "depth": 120, "height": 15})
    d.execute("drill_hole", {"feature": placa, "position": {"x": 30, "y": 20, "z": -7.5},
                             "axis": "z", "diameter": 10, "depth": 0})
    pin = d.execute("create_cylinder", {"name": "pin", "radius": 4.9, "height": 80, "axis": "z",
                                        "position": {"x": -300, "y": 0, "z": 0}})
    d.execute("add_mate", {"name": "m", "type": "concentrico", "feature_a": placa, "feature_b": pin,
                           "ref_a": {"entidad": "arista", "mode": "cerca", "point": [30, 20, 7.5]},
                           "ref_b": {"mode": "cerca", "point": [-304.9, 0, 0]}})
    bb = d.scene[pin].shape.bounding_box()
    assert (bb.min.X + bb.max.X) / 2 == pytest.approx(30, abs=1e-2)
    assert (bb.min.Y + bb.max.Y) / 2 == pytest.approx(20, abs=1e-2)


def test_arista_no_circular_error():
    from apolo.doc import DocumentError

    d = Document()
    a = d.execute("create_box", {"name": "A", "width": 100, "depth": 100, "height": 40})
    b = d.execute("create_box", {"name": "B", "width": 40, "depth": 40, "height": 40,
                                 "position": {"x": 300}})
    with pytest.raises(DocumentError, match="CIRCULAR|circular"):
        d.execute("add_mate", {"name": "m", "type": "concentrico", "feature_a": a, "feature_b": b,
                               "ref_a": {"entidad": "arista", "mode": "cara", "face": "tope"},
                               "ref_b": {"mode": "cerca", "point": [280, 0, 0]}})


# ------------------------------------------------- supervivencia a transforms
def test_anclas_regeneran_en_su_sitio():
    """Las anclas se RE-CALCULAN en cada regenerate (no envejecen): editar la pose las mueve."""
    d = Document()
    ch = d.execute("insert_component", {"component": "UCP205", "position": {"x": 0}})
    cmd = d.commands[0]["id"]
    d.edit(cmd, {"component": "UCP205", "position": {"x": 100, "y": 20, "z": 5}})
    assert d.scene[ch].anchors["centro"]["origin"] == pytest.approx([100, 20, 5])


def test_anclas_viajan_con_transform_group():
    d = Document()
    ch = d.execute("insert_component", {"component": "UCP205", "position": {"x": 0, "y": 0, "z": 0}})
    grp_cmd = d.commands[0]["id"]
    d.execute("create_group", {"name": "soporte", "members": [grp_cmd]})
    d.execute("transform_group", {"group": "soporte", "translate": {"x": 50, "y": 0, "z": 10}})
    assert d.scene[ch].anchors["centro"]["origin"] == pytest.approx([50, 0, 10])


def test_anclas_viajan_con_mate_y_no_stale():
    """Tras matear, el ancla queda transformada (no en su pose original)."""
    d = Document()
    eje = d.execute("create_cylinder", {"name": "eje", "radius": 17.5, "height": 600,
                                        "axis": "y", "position": {"x": 200, "y": 0, "z": 300}})
    ch = d.execute("insert_component", {"component": "UCP205", "position": {"x": -500}})
    antes = list(d.scene[ch].anchors["centro"]["origin"])
    d.execute("add_mate", {"name": "m", "type": "concentrico", "feature_a": eje, "feature_b": ch,
                           "ref_a": {"mode": "cerca", "point": [217.5, 0, 300]},
                           "ref_b": {"mode": "ancla", "name": "centro"}})
    despues = d.scene[ch].anchors["centro"]["origin"]
    assert despues != pytest.approx(antes)  # se movió con la pieza


# --------------------------------------------------------- warm/frío geomcache
def test_anclas_sobreviven_warm_cold():
    from apolo.doc.geomcache import pack, unpack

    d = Document()
    d.execute("insert_component", {"component": "UCP205", "position": {"x": 100, "y": 50, "z": 30}})
    apolo = d.to_apolo_bytes()
    warm = unpack(pack(d))
    assert warm is not None
    hot = Document.from_apolo_bytes(apolo, warm=warm)
    cold = Document.from_apolo_bytes(apolo)
    for fid in cold.scene:
        assert hot.scene[fid].anchors == cold.scene[fid].anchors
    ch = next(fid for fid, f in cold.scene.items() if f.anchors)
    assert cold.scene[ch].anchors["centro"]["origin"] == pytest.approx([100, 50, 30])


# --------------------------------------------------------------- get_topology
def test_topology_lista_anclas():
    api.DOC = Document("anchor-topo")
    client = TestClient(api.app)
    r = client.post("/api/commands", json={"type": "insert_component",
                                           "params": {"component": "UCP205",
                                                      "position": {"x": 10, "y": 20, "z": 30}}})
    fid = r.json()["features"][0]["id"]
    topo = client.get(f"/api/features/{fid}/topology").json()
    assert "anchors" in topo
    assert "centro" in topo["anchors"]
    assert topo["anchors"]["centro"]["origin"] == pytest.approx([10, 20, 30])


# ----------------------------------------- V6.3d Fix 1: _world_move transforma anclas
def _bbc(shape) -> list[float]:
    bb = shape.bounding_box()
    return [(bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2]


def test_transform_mueve_ancla():
    """EL bug de la revisión: `transform` reasignaba el shape pero NO el ancla → el conector
    quedaba stale en la pose original. Fix 1: el ancla viaja con el shape."""
    d = Document()
    ch = d.execute("insert_component", {"component": "UCP205", "position": {"x": 0, "y": 0, "z": 0}})
    assert d.scene[ch].anchors["centro"]["origin"] == pytest.approx([0, 0, 0])
    d.execute("transform", {"feature": ch, "translate": {"x": 100, "y": 50, "z": 25}})
    assert d.scene[ch].anchors["centro"]["origin"] == pytest.approx([100, 50, 25])
    assert d.scene[ch].anchors["centro"]["axis"] == pytest.approx([0, 1, 0])  # eje intacto (sin giro)


def test_transform_con_rotacion_gira_el_eje_del_ancla():
    """Una rotación de 90° sobre Z lleva el eje del ancla de Y a −X (R·axis)."""
    d = Document()
    ch = d.execute("insert_component", {"component": "UCP205", "position": {"x": 0, "y": 0, "z": 0}})
    d.execute("transform", {"feature": ch, "rotate": {"x": 0, "y": 0, "z": 90}})
    assert d.scene[ch].anchors["centro"]["axis"] == pytest.approx([-1, 0, 0], abs=1e-9)


def test_transform_luego_mate_por_ancla_ensambla_rigido():
    """Repro exacto de la revisión: insert (0,0,0) → transform +100/+50/+25 → mate concéntrico
    por ancla contra un eje en x=300. Sin Fix 1 el solver matea con un frame STALE y la
    chumacera queda 100 mm fuera del eje; con el fix el conjunto queda rígido y centrado."""
    d = Document()
    eje = d.execute("create_cylinder", {"name": "eje", "radius": 17.5, "height": 600,
                                        "axis": "y", "position": {"x": 300, "y": 0, "z": 300}})
    ch = d.execute("insert_component", {"component": "UCP205", "position": {"x": 0, "y": 0, "z": 0}})
    off0 = [c - a for c, a in zip(_bbc(d.scene[ch].shape),
                                  d.scene[ch].anchors["centro"]["origin"])]  # bbox − ancla (rígido)
    d.execute("transform", {"feature": ch, "translate": {"x": 100, "y": 50, "z": 25}})
    d.execute("add_mate", {"name": "m", "type": "concentrico", "feature_a": eje, "feature_b": ch,
                           "ref_a": {"mode": "cerca", "point": [317.5, 0, 300]},
                           "ref_b": {"mode": "ancla", "name": "centro"}})
    a = d.scene[ch].anchors["centro"]["origin"]
    assert a[0] == pytest.approx(300, abs=1e-2) and a[2] == pytest.approx(300, abs=1e-2)  # sobre el eje
    off1 = [c - av for c, av in zip(_bbc(d.scene[ch].shape), a)]
    assert off1 == pytest.approx(off0, abs=1e-6)  # rígido: sin Fix 1, off1 = off0 + (100,50,25)


def test_center_in_mueve_ancla():
    """center_in comparte `_world_move` (traslación pura): el ancla se desplaza EXACTO lo que
    el shape."""
    d = Document()
    cont = d.execute("create_box", {"name": "cont", "width": 400, "depth": 400, "height": 400,
                                    "position": {"x": 150, "y": 60, "z": 20}})
    ch = d.execute("insert_component", {"component": "UCP205", "position": {"x": 0, "y": 0, "z": 0}})
    a0, c0 = list(d.scene[ch].anchors["centro"]["origin"]), _bbc(d.scene[ch].shape)
    d.execute("center_in", {"feature": ch, "into": cont, "axes": ["x", "y", "z"]})
    a1, c1 = d.scene[ch].anchors["centro"]["origin"], _bbc(d.scene[ch].shape)
    assert [a1[i] - a0[i] for i in range(3)] == pytest.approx([c1[i] - c0[i] for i in range(3)])


def test_ancla_correcta_tras_undo_redo_transform():
    d = Document()
    ch = d.execute("insert_component", {"component": "UCP205", "position": {"x": 0, "y": 0, "z": 0}})
    d.execute("transform", {"feature": ch, "translate": {"x": 100, "y": 50, "z": 25}})
    assert d.scene[ch].anchors["centro"]["origin"] == pytest.approx([100, 50, 25])
    d.undo()
    assert d.scene[ch].anchors["centro"]["origin"] == pytest.approx([0, 0, 0])
    d.redo()
    assert d.scene[ch].anchors["centro"]["origin"] == pytest.approx([100, 50, 25])


# --------------------------------- V6.3d Fix 2: duplicate/pattern heredan anclas
def test_duplicate_hereda_ancla_y_matea_en_su_sitio():
    """Una chumacera duplicada conserva su ancla 'centro' (desplazada por el offset) → puede
    matearse por ancla en su nueva posición. Sin Fix 2 la copia no tenía anclas → el mate por
    ancla lanzaba 'no publica un ancla'."""
    d = Document()
    ch = d.execute("insert_component", {"component": "UCP205", "position": {"x": 0, "y": 0, "z": 0}})
    dup = d.execute("duplicate_feature", {"feature": ch, "offset": {"x": 300, "y": 0, "z": 0}})
    assert d.scene[dup].anchors["centro"]["origin"] == pytest.approx([300, 0, 0])
    assert d.scene[dup].anchors["centro"]["axis"] == pytest.approx([0, 1, 0])
    eje = d.execute("create_cylinder", {"name": "eje", "radius": 17.5, "height": 400, "axis": "y",
                                        "position": {"x": 300, "y": 0, "z": 200}})
    d.execute("add_mate", {"name": "m", "type": "concentrico", "feature_a": eje, "feature_b": dup,
                           "ref_a": {"mode": "cerca", "point": [317.5, 0, 200]},
                           "ref_b": {"mode": "ancla", "name": "centro"}})
    a = d.scene[dup].anchors["centro"]["origin"]
    assert a[0] == pytest.approx(300, abs=1e-2) and a[2] == pytest.approx(200, abs=1e-2)


def test_pattern_linear_hereda_anclas():
    """Cada copia del patrón hereda el ancla desplazada por su offset."""
    d = Document()
    d.execute("insert_component", {"component": "UCP205", "position": {"x": 0, "y": 0, "z": 0}})
    d.execute("pattern_linear", {"feature": d.commands[0]["id"], "count": 3,
                                 "spacing": {"x": 250, "y": 0, "z": 0}})
    con_ancla = [f for f in d.scene.values() if f.anchors and "centro" in f.anchors]
    xs = sorted(f.anchors["centro"]["origin"][0] for f in con_ancla)
    assert xs == pytest.approx([0, 250, 500])
    assert all(f.anchors["centro"]["axis"] == pytest.approx([0, 1, 0]) for f in con_ancla)


def test_pattern_circular_hereda_anclas():
    """Un patrón circular gira cada copia sobre el eje: el ORIGIN del ancla rota con ella y su
    AXIS también (aquí eje Z → el eje Y del ancla gira a −X a 90°)."""
    d = Document()
    d.execute("insert_component", {"component": "UCP205", "position": {"x": 100, "y": 0, "z": 0}})
    d.execute("pattern_circular", {"feature": d.commands[0]["id"], "count": 4, "total_angle": 360,
                                   "axis_dir": "z", "axis_point": {"x": 0, "y": 0, "z": 0}})
    con_ancla = [f for f in d.scene.values() if f.anchors and "centro" in f.anchors]
    assert len(con_ancla) == 4
    # la copia a 90° tiene su origin en (0,100,·) y su eje girado de (0,1,0) a (−1,0,0)
    a90 = next(f.anchors["centro"] for f in con_ancla
               if f.anchors["centro"]["origin"][1] == pytest.approx(100, abs=1e-6))
    assert a90["origin"][0] == pytest.approx(0, abs=1e-6)
    assert a90["axis"] == pytest.approx([-1, 0, 0], abs=1e-9)
