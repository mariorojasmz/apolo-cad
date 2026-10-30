"""Plan maquinas-grandes F2 (D2, D3).

D2: `Rayos.estado` («¿está dentro?» por la paridad de dos rectas oblicuas, el clasificador sólo si
duda) da EXACTAMENTE el estado del `BRepClass3d_SolidClassifier` armado por consulta, el de
siempre: dentro, fuera, sobre una cara, una arista o un vértice, a 1e-7 de una cara, en un hueco
cerrado, en un tubo, en una chapa con ventanas, en un sólido al revés y en los sólidos de los
testigos. Cuando las dos rectas difieren decide el clasificador.

D3: los agujeros de una forma se miden UNA vez por corrida (`calidad_agujeros.agujeros_de_corrida`,
memo de `engineering/memo_corrida` por `is`); fuera de una corrida, siempre; una forma nueva o
movida en sitio se mide de nuevo.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest
from build123d import Box, Cylinder, Location, Pos, Rotation, Solid, Sphere
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_IN, TopAbs_ON, TopAbs_OUT

from apolo.kernel import rayo as rayo_mod
from apolo.kernel.rayo import Rayos

TESTIGOS = Path(__file__).parent / "data" / "testigos"


def _occt(solid, p):
    return BRepClass3d_SolidClassifier(solid.wrapped, gp_Pnt(*p), 1e-6).State()


def _puntos(solid, n_azar: int, semilla: int = 7) -> list[tuple]:
    """Al azar en la caja (algo agrandada) + vértices, medios de arista y centros de cara (los
    rasantes) + uno a 1e-7 y a 1e-5 de cada centro de cara, hacia los dos lados."""
    bb = solid.bounding_box()
    lo, hi = (bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)
    rnd = random.Random(semilla)
    pts = [tuple(rnd.uniform(lo[k] - 2, hi[k] + 2) for k in range(3)) for _ in range(n_azar)]
    pts += [(v.X, v.Y, v.Z) for v in solid.vertices()]
    for e in solid.edges():
        q = e @ 0.5
        pts.append((q.X, q.Y, q.Z))
    for f in solid.faces():
        c = f.center()
        pts.append((c.X, c.Y, c.Z))
        try:
            n = f.normal_at(c)
        except Exception:  # noqa: BLE001
            continue
        for d in (1e-7, -1e-7, 1e-5, -1e-5, 0.3, -0.3):
            pts.append((c.X + d * n.X, c.Y + d * n.Y, c.Z + d * n.Z))
    return pts


def _chapa_con_ventanas():
    chapa = Box(200, 120, 3)
    for x in (-60, 0, 60):
        chapa -= Pos(x, 0, 0) * Box(30, 40, 10)
    return chapa - Pos(0, 45, 0) * Cylinder(4, 10)


SOLIDOS = {
    "caja": lambda: Box(10, 20, 30),
    "caja girada": lambda: Pos(3, 4, 5) * Rotation(10, 20, 30) * Box(100, 20, 30),
    "tubo redondo": lambda: Cylinder(10, 40) - Cylinder(8, 40),
    "tubo rectangular": lambda: Rotation(0, 90, 0) * (Box(40, 20, 300) - Box(36, 16, 300)),
    "chapa con ventanas": _chapa_con_ventanas,
    "hueco cerrado": lambda: Box(20, 20, 20) - Box(6, 6, 6),
    "esfera": lambda: Sphere(15),
    "taladrada": lambda: Pos(3, 4, 5) * Rotation(10, 20, 30) * (Box(100, 20, 30) - Cylinder(5, 50)),
}


@pytest.mark.parametrize("nombre", sorted(SOLIDOS))
def test_la_paridad_da_lo_mismo_que_el_clasificador(nombre):
    (solid,) = SOLIDOS[nombre]().solids()
    r = Rayos(solid)
    distintos = [p for p in _puntos(solid, 300) if r.estado(p) != _occt(solid, p)]
    assert distintos == []


def test_los_puntos_de_la_frontera_los_decide_el_clasificador():
    (solid,) = Box(10, 10, 10).solids()
    r = Rayos(solid)
    assert r.estado((5, 0, 0)) == TopAbs_ON       # cara
    assert r.estado((5, 5, 0)) == TopAbs_ON       # arista
    assert r.estado((5, 5, 5)) == TopAbs_ON       # vértice
    assert r.estado((5 - 1e-7, 0, 0)) == TopAbs_ON  # dentro de la tolerancia de OCCT
    assert r.dentro((0, 0, 0)) and not r.dentro((5, 0, 0)) and not r.dentro((9, 0, 0))


def test_un_punto_limpio_no_arma_el_clasificador():
    (solid,) = Box(10, 10, 10).solids()
    r = Rayos(solid)
    assert r.estado((1, 2, 3)) == TopAbs_IN
    assert r.estado((1, 2, 30)) == TopAbs_OUT
    assert r._clasif is None


def test_un_hueco_cerrado_es_fuera():
    (solid,) = (Box(20, 20, 20) - Box(6, 6, 6)).solids()
    r = Rayos(solid)
    assert r.estado((0, 0, 0)) == TopAbs_OUT == _occt(solid, (0, 0, 0))
    assert r.estado((8, 0, 0)) == TopAbs_IN


def test_un_solido_al_reves_lo_decide_el_clasificador():
    inv = Solid(Box(10, 10, 10).wrapped.Reversed())
    r = Rayos(inv)
    for p in ((0, 0, 0), (30, 0, 0), (1, 2, 3), (100, -50, 7)):
        assert r.estado(p) == _occt(inv, p)


def test_si_las_dos_rectas_difieren_decide_el_clasificador(monkeypatch):
    (solid,) = Box(10, 10, 10).solids()
    r = Rayos(solid)
    votos = iter([(2, True), (2, False)])
    monkeypatch.setattr(r, "_voto", lambda *a: next(votos))
    llamadas = []
    original = r._occt
    monkeypatch.setattr(r, "_occt", lambda p: llamadas.append(p) or original(p))
    assert r.estado((1, 2, 3)) == TopAbs_IN
    assert llamadas == [(1, 2, 3)]


def test_si_el_intersector_falla_decide_el_clasificador(monkeypatch):
    (solid,) = Box(10, 10, 10).solids()
    r = Rayos(solid)

    def falla(*a):
        raise RuntimeError("OCCT")

    monkeypatch.setattr(r, "_voto", falla)
    assert r.estado((1, 2, 3)) == TopAbs_IN
    assert r.estado((1, 2, 30)) == TopAbs_OUT
    assert r._clasif is not None


def test_tramos_no_cambia():
    (solid,) = (Cylinder(10, 40) - Cylinder(8, 40)).solids()
    r = Rayos(solid)
    tr = r.tramos((-20, 0, 0), (1, 0, 0), 0, 40)
    assert [(round(a, 3), round(b, 3)) for a, b in tr] == [(10.0, 12.0), (28.0, 30.0)]


def test_los_solidos_de_los_testigos():
    from apolo.doc import Document

    doc = Document.from_apolo_bytes((TESTIGOS / "mensula_atornillada.apolo").read_bytes())
    vistos = 0
    for f in doc.scene.values():
        if f.shape is None or getattr(f, "is_guide", False):
            continue
        for solid in f.shape.solids():
            r = Rayos(solid)
            pts = _puntos(solid, 40, semilla=vistos)
            assert [p for p in pts if r.estado(p) != _occt(solid, p)] == []
            vistos += 1
    assert vistos >= 3


def test_las_rectas_son_unitarias_y_oblicuas():
    for d in rayo_mod._RECTAS:
        assert abs(sum(c * c for c in d) - 1.0) < 1e-12
        assert min(abs(c) for c in d) > 0.3


# ── D3: los agujeros de una forma, una vez por corrida ──────────────────────────────────────


def _contar(monkeypatch):
    from apolo.services import calidad_agujeros as ca

    n = {"n": 0}
    original = ca.agujeros_de

    def contado(shape, colisos=True):
        n["n"] += 1
        return original(shape, colisos)

    monkeypatch.setattr(ca, "agujeros_de", contado)
    return ca, n


def _placa():
    return Box(100, 60, 5) - Pos(-30, 0, 0) * Cylinder(4.5, 10) - Pos(30, 0, 0) * Cylinder(4.5, 10)


def test_fuera_de_una_corrida_se_mide_siempre(monkeypatch):
    ca, n = _contar(monkeypatch)
    s = _placa()
    a, b = ca.agujeros_de_corrida(s), ca.agujeros_de_corrida(s)
    assert a == b and len(a) == 2 and n["n"] == 2


def test_en_una_corrida_una_vez_por_forma_y_por_is(monkeypatch):
    from apolo.library.engineering.memo_corrida import memo_de_corrida

    ca, n = _contar(monkeypatch)
    s, otra = _placa(), _placa()  # misma geometría, otra forma: otra entrada
    with memo_de_corrida():
        a = ca.agujeros_de_corrida(s)
        a[0]["d"] = -1.0  # quien la recibe la ensucia: el memo no
        b = ca.agujeros_de_corrida(s)
        c = ca.agujeros_de_corrida(otra)
    assert n["n"] == 2
    assert b == c == ca.agujeros_de(s)


def test_una_forma_movida_en_sitio_se_mide_de_nuevo(monkeypatch):
    from apolo.library.engineering.memo_corrida import memo_de_corrida

    ca, n = _contar(monkeypatch)
    s = _placa()
    with memo_de_corrida():
        a = ca.agujeros_de_corrida(s)
        s.move(Location((0, 0, 50)))
        b = ca.agujeros_de_corrida(s)
    assert n["n"] == 2
    assert [x["p"][2] for x in b] == [pytest.approx(x["p"][2] + 50) for x in a]


def test_el_memo_sigue_al_documento(monkeypatch):
    """La puerta pide los agujeros tres veces (lints, reglas, `union.agujeros`): con el memo, una
    vez por pieza; si una pieza cambia de forma, se mide la nueva."""
    from apolo.doc import Document
    from apolo.library.engineering.memo_corrida import memo_de_corrida

    ca, n = _contar(monkeypatch)
    doc = Document.from_apolo_bytes((TESTIGOS / "mensula_atornillada.apolo").read_bytes())
    sin_memo = [ca.agujeros_atribuidos(doc), ca.insumos_agujeros(doc)]
    n["n"] = 0
    with memo_de_corrida():
        con_memo = [ca.agujeros_atribuidos(doc), ca.insumos_agujeros(doc)]
        una = n["n"]
        ca.agujeros_atribuidos(doc)
        assert n["n"] == una  # tercera vez: nada nuevo
        fid = next(iter(con_memo[0]))
        f = doc.scene[fid]
        f.shape = Pos(0, 0, 0) * f.shape  # otra forma (copia ubicada): se mide de nuevo
        ca.agujeros_atribuidos(doc)
        assert n["n"] == una + 1
    assert con_memo == sin_memo
    assert una > 0
