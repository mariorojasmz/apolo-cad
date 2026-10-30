"""Plan maquinas-grandes F1 (D1): la caja óptima memoizada por forma (`kernel/caja.py`).

Misma `BoundBox` que `shape.bounding_box()`, recalculada tras `move`/`locate` EN SITIO (mueven el
mismo `wrapped`), tras cambiar `wrapped` o su `TShape`; el `weakref` suelta la forma; un acierto
sigue borrando la malla (`BRepTools.Clean`); la caja devuelta no ensucia el memo. Los llamadores
calientes medidos en la F0 no vuelven a `.bounding_box()` (test de texto) y un replay da las
mismas piezas y fijadores con y sin memo."""

from __future__ import annotations

import gc
import inspect
import math
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from build123d import Box, Cylinder, Location, Pos, Rotation

from apolo.kernel import caja as caja_mod
from apolo.kernel.caja import caja

TESTIGOS = Path(__file__).parent / "data" / "testigos"


def _t(bb) -> tuple:
    return (bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z)


def _pieza():
    return Pos(3, 4, 5) * Rotation(10, 20, 30) * (Box(100, 20, 30) - Cylinder(5, 50))


@pytest.mark.parametrize("hacer", [
    lambda: Box(10, 20, 30),
    _pieza,
    lambda: Pos(-40, 7, 2) * Rotation(0, 35, 0) * Cylinder(12, 80),
    lambda: Box(10, 10, 10) + Pos(30, 0, 0) * Box(10, 10, 10),  # dos sólidos disjuntos
])
def test_la_misma_caja_que_bounding_box_al_fallar_y_al_acertar(hacer):
    s = hacer()
    esperada = _t(s.bounding_box())
    assert _t(caja(s)) == esperada  # fallo: la calcula
    assert _t(caja(s)) == esperada  # acierto: la del memo


def test_cada_llamada_da_una_caja_nueva_que_no_ensucia_el_memo():
    s = _pieza()
    a = caja(s)
    b = caja(s)
    assert a is not b
    esperada = _t(b)
    a.min.X = -1e9  # quien la recibe la ensucia
    assert _t(caja(s)) == esperada


@pytest.mark.parametrize("mover", [
    lambda s: s.move(Location((50, 0, 0))),
    lambda s: s.locate(Location((0, 0, 0))),
    lambda s: s.locate(Location((10, -20, 30), (0, 0, 1), 45)),
])
def test_move_y_locate_en_sitio_la_recalculan(mover):
    s = _pieza()
    w = s.wrapped
    antes = _t(caja(s))
    mover(s)
    assert s.wrapped is w  # build123d 0.10 mueve el MISMO wrapped: la identidad no basta
    despues = _t(caja(s))
    assert despues == _t(s.bounding_box())
    assert despues != antes


def test_otro_wrapped_u_otro_tshape_la_recalculan():
    s = Box(10, 10, 10)
    caja(s)
    s.wrapped = Box(30, 10, 10).wrapped
    assert _t(caja(s)) == _t(s.bounding_box())
    assert caja(s).max.X == pytest.approx(15)
    s2 = Box(10, 10, 10)
    caja(s2)
    s2.wrapped.TShape(Box(50, 10, 10).wrapped.TShape())  # mismo wrapped, otro TShape
    assert caja(s2).max.X == pytest.approx(25)


def test_el_weakref_suelta_la_forma():
    caja_mod.vaciar_memo()
    formas = [_pieza() for _ in range(5)]
    for s in formas:
        caja(s)
    assert caja_mod.tamano_memo() == 5
    del formas, s
    gc.collect()
    assert caja_mod.tamano_memo() == 0


def test_un_acierto_sigue_borrando_la_malla():
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopLoc import TopLoc_Location

    s = _pieza()
    caja(s)  # fallo: queda en el memo

    def con_malla() -> int:
        return sum(1 for f in s.faces()
                   if BRep_Tool.Triangulation_s(f.wrapped, TopLoc_Location()) is not None)

    BRepMesh_IncrementalMesh(s.wrapped, 0.5)
    assert con_malla() > 0
    caja(s)  # acierto
    assert con_malla() == 0  # como `bounding_box()`


def test_un_id_reciclado_no_da_la_caja_ajena():
    """La regla de core/apolo/CLAUDE.md: el id de una forma muerta se recicla."""
    for _ in range(50):
        a = Box(10, 10, 10)
        caja(a)
        del a
        b = Pos(500, 0, 0) * Box(20, 20, 20)
        assert _t(caja(b)) == _t(b.bounding_box())
        del b


# ── los llamadores medidos en la F0 ─────────────────────────────────────────────────────────


def _llamadores():
    from apolo.commands import exec_modificar, union_taller
    from apolo.drawing import process
    from apolo.kernel import contacto, mesh
    from apolo.library import checks
    from apolo.library.engineering import mass
    from apolo.services import calidad_agujeros, calidad_seguridad, vigas_rules

    return [union_taller._en_camino, exec_modificar._exec_drill_hole,
            checks.interference_report, mass._bbox, vigas_rules._caja, contacto._toca_caja,
            contacto._caja_comun, calidad_agujeros._caja, process._sorted_dims,
            calidad_seguridad._caja, mesh.bbox_payload]


@pytest.mark.parametrize("fn", _llamadores(), ids=lambda f: f"{f.__module__}.{f.__name__}")
def test_los_llamadores_calientes_usan_la_caja_memoizada(fn):
    fuente = inspect.getsource(fn)
    assert ".bounding_box(" not in fuente, (
        f"{fn.__module__}.{fn.__name__} volvió a `.bounding_box()`: usa `kernel/caja.caja` "
        "(plan maquinas-grandes D1)")
    assert re.search(r"\bcaja(_optima)?\(", fuente)


def test_en_camino_ve_el_obstaculo_movido_en_sitio():
    """`join_bolted` busca obstáculos con la caja memoizada: un obstáculo movido EN SITIO entre
    dos uniones no puede seguir viéndose donde estaba."""
    from apolo.commands.union_taller import _en_camino

    obst = Pos(0, 0, 20) * Box(50, 50, 10)
    escena = {"o": SimpleNamespace(id="o", shape=obst)}
    h = {"stack": 2, "amin": [0, 0, -5], "amax": [0, 0, 5], "bmin": [0, 0, 5],
         "bmax": [0, 0, 10]}
    assert [f.id for f in _en_camino(escena, set(), h, [0.0], [0.0], 0, 1, 20.0)] == ["o"]
    obst.move(Location((0, 0, 500)))
    assert _en_camino(escena, set(), h, [0.0], [0.0], 0, 1, 20.0) == []


# ── replay: las mismas piezas y fijadores con y sin memo ────────────────────────────────────


def _sin_memo(monkeypatch):
    monkeypatch.setattr(caja_mod, "caja", lambda s: s.bounding_box())


def _firma(doc) -> dict:
    piezas = {}
    for fid, f in doc.scene.items():
        bb = f.shape.bounding_box()
        piezas[fid] = (f.name, f.command_id, round(f.shape.volume, 6),
                       tuple(round(x, 6) for x in _t(bb)), len(f.shape.faces()))
    return {"piezas": piezas, "fasteners": doc.fasteners, "suprimidos": doc.regen_suppressed}


def _replay(data: bytes) -> dict:
    from apolo.doc import Document

    return _firma(Document.from_apolo_bytes(data, tolerant=True))


def _maquina_chica() -> bytes:
    """Una ménsula con obstáculos detrás, dos `join_bolted` y taladros: lo que `_en_camino` y
    `drill_hole` piden a la caja."""
    from apolo.doc import Document

    doc = Document("caja-memo")
    c = doc.execute("create_sheet_metal", {"name": "Larguero C", "ancho": 600, "fondo": 150,
                                           "espesor": 3, "lados": ["frente", "atras"],
                                           "altura_pestana": 50})
    p1 = doc.execute("create_box", {"name": "Placa 1", "width": 120, "depth": 60,
                                    "height": 1.5, "position": {"x": -150, "z": -0.75}})
    p2 = doc.execute("create_box", {"name": "Placa 2", "width": 120, "depth": 60,
                                    "height": 1.5, "position": {"x": 150, "z": -0.75}})
    doc.execute("create_box", {"name": "Refuerzo", "width": 200, "depth": 100, "height": 10,
                               "position": {"x": -150, "z": 3 + 7 + 5}})
    for k in range(4):
        doc.execute("create_box", {"name": f"Otra {k}", "width": 40, "depth": 40, "height": 40,
                                   "position": {"x": -250 + 160 * k, "y": 300, "z": 20}})
    doc.execute("join_bolted", {"a": c, "b": p1, "size": "M6", "count": 2})
    doc.execute("drill_hole", {"feature": c, "diameter": 8, "position": {"x": 250, "z": 10},
                               "axis": "-z"})
    doc.execute("join_bolted", {"a": c, "b": p2, "size": "M6", "count": 2})
    return doc.to_apolo_bytes()


@pytest.mark.parametrize("fuente", ["maquina_chica", "faja", "mensula_atornillada"])
def test_el_replay_da_lo_mismo_con_y_sin_memo(fuente, monkeypatch):
    data = (_maquina_chica() if fuente == "maquina_chica"
            else (TESTIGOS / f"{fuente}.apolo").read_bytes())
    con = _replay(data)
    with monkeypatch.context() as m:
        _sin_memo(m)
        sin = _replay(data)
    assert con["piezas"].keys() == sin["piezas"].keys() and con["piezas"]
    for fid, (nombre, cmd, vol, bb, caras) in sin["piezas"].items():
        n2, c2, v2, b2, k2 = con["piezas"][fid]
        assert (n2, c2, k2) == (nombre, cmd, caras), fid
        assert math.isclose(v2, vol, abs_tol=1e-6) and b2 == bb, fid
    assert con["fasteners"] == sin["fasteners"]
    assert con["suprimidos"] == sin["suprimidos"]
