"""`cerca` con `medir: "superficie"` (plan `docs/plans/fea-chapa-empernada.md`, F3: D5 y D6).

`cerca` elige por distancia al CENTRO de cada cara o arista (`obj.center()`: en una cara curva,
el punto en la mitad de su dominio uv, el mismo que publica `get_topology`). En el alma del
larguero c1442 del proyecto 72, un punto SOBRE la cara exterior a 28 mm del eje del Ø40 eligió
el cilindro de un Ø17 vecino. `medir: "superficie"` mide a la cara o arista misma (OCCT) y
desempata por el centro; el default NO cambia: un log viejo no trae la clave y resuelve igual
(raíz: «un log viejo regenera igual»).
"""
import importlib.util
import math

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.commands.registry import REGISTRY, CommandError
from apolo.commands.strict import rejection_text, unknown_paths
from apolo.doc import Document, DocumentError
from apolo.kernel.selectors import SelectorError, resolve_edges, resolve_faces

_ERRS = (CommandError, DocumentError)  # execute envuelve según el punto de fallo
_FEA_OK = (importlib.util.find_spec("gmsh") is not None
           and importlib.util.find_spec("skfem") is not None)
requires_fea = pytest.mark.skipif(not _FEA_OK, reason="extra [fea] no instalado")


def _placa_con_taladros():
    """El alma de c1442 en chico: placa 1000×100×6 (x 0..1000, y 0..100, z 0..6) con un Ø40
    en (100, 50) y un Ø17 vecino en (140, 50). Larga a propósito, como el alma de 4 m: el
    centro de sus caras grandes queda lejos de los taladros."""
    from build123d import Box, Cylinder, Pos

    return (Pos(500, 50, 3) * Box(1000, 100, 6)
            - Pos(100, 50, 3) * Cylinder(20, 20)
            - Pos(140, 50, 3) * Cylinder(8.5, 20))


def _tipo(f) -> str:
    return str(f.geom_type).rsplit(".", 1)[-1].upper()


def _cilindro(shape, r):
    (f,) = [f for f in shape.faces() if _tipo(f) == "CYLINDER" and abs(f.radius - r) < 1e-6]
    return f


def _plana_en_z(shape, z):
    (f,) = [f for f in shape.faces() if _tipo(f) == "PLANE" and abs(f.center().Z - z) < 1e-6]
    return f


def _mismas(a: list, b: list) -> bool:
    return len(a) == len(b) and all(x.is_same(y) for x, y in zip(a, b))


def _centro_viejo(objs, point, count=1):
    """El `cerca` de antes de F3, copiado tal cual: la referencia de «resuelve igual»."""
    def d2(o):
        c = o.center()
        return (c.X - point[0]) ** 2 + (c.Y - point[1]) ** 2 + (c.Z - point[2]) ** 2
    return sorted(objs, key=d2)[:count]


# ------------------------------------------------------------------ caras: el caso del alma
def test_punto_sobre_la_cara_plana_junto_a_un_taladro_vecino():
    """El caso de c1442: el punto está SOBRE la cara superior, a 28 mm del eje del Ø40 y a
    3.5 mm del borde del Ø17. Al centro gana el cilindro del Ø17 (su centro uv queda a
    ~4.6 mm, en el muro del taladro); a la superficie, la cara que el punto toca."""
    shape = _placa_con_taladros()
    p = [128.0, 50.0, 6.0]
    assert math.dist(p[:2], (100, 50)) == pytest.approx(28.0)
    sup = _plana_en_z(shape, 6.0)
    o17 = _cilindro(shape, 8.5)

    assert _mismas(resolve_faces(shape, {"mode": "cerca", "point": p}), [o17])
    assert _mismas(resolve_faces(shape, {"mode": "cerca", "point": p, "medir": "centro"}), [o17])
    assert _mismas(resolve_faces(shape, {"mode": "cerca", "point": p, "medir": "superficie"}),
                   [sup])


def test_punto_sobre_el_taladro_elige_el_taladro_con_los_dos_criterios():
    """El punto de Mario: SOBRE la superficie del Ø40 (arriba del eje, a media placa)."""
    shape = _placa_con_taladros()
    p = [100.0, 70.0, 3.0]
    o40 = _cilindro(shape, 20.0)
    for medir in (None, "centro", "superficie"):
        sel = {"mode": "cerca", "point": p, **({"medir": medir} if medir else {})}
        assert _mismas(resolve_faces(shape, sel), [o40]), medir


def test_sin_medir_resuelve_como_el_cerca_de_antes():
    """Un selector viejo (sin la clave) elige EXACTAMENTE lo mismo que el código de antes, en
    caras y aristas, con count 1 y 3, en puntos sobre caras, aristas, taladros y fuera."""
    shape = _placa_con_taladros()
    caras, aristas = list(shape.faces()), list(shape.edges())
    puntos = [[128, 50, 6], [100, 70, 3], [0, 0, 0], [995, 50, 6], [140, 58.5, 1],
              [500, -20, 40], [120, 50, 6], [131.5, 50, 3]]
    for p in puntos:
        for n in (1, 3):
            sel = {"mode": "cerca", "point": p, "count": n}
            assert _mismas(resolve_faces(shape, sel), _centro_viejo(caras, p, n)), (p, n)
            assert _mismas(resolve_edges(shape, sel), _centro_viejo(aristas, p, n)), (p, n)


# ------------------------------------------------------------------------------ aristas
def _caja():
    """Caja 100×60×40 centrada (x ±50, y ±30, z ±20)."""
    from build123d import Box

    return Box(100, 60, 40)


def test_aristas_a_la_superficie():
    """Punto SOBRE la arista larga (X, en y=30 z=20) cerca de su extremo: al centro gana la
    arista corta en Z del extremo (punto medio a 20.6 mm contra 45); a la superficie, la que
    el punto toca."""
    shape = _caja()
    p = [45.0, 30.0, 20.0]
    (centro,) = resolve_edges(shape, {"mode": "cerca", "point": p})
    (sup,) = resolve_edges(shape, {"mode": "cerca", "point": p, "medir": "superficie"})
    assert centro.length == pytest.approx(40) and abs(centro.tangent_at(0).Z) == pytest.approx(1)
    assert sup.length == pytest.approx(100) and abs(sup.tangent_at(0).X) == pytest.approx(1)
    c = sup.center()
    assert (c.Y, c.Z) == pytest.approx((30, 20))


def test_arista_entre_dos_caras_desempata_el_centro():
    """El punto está SOBRE la arista de la cara +Y con la superior: distancia 0 a las dos y
    gana la de centro más cercano (+Y, a 49.2 mm; la superior, a 54.1). Al centro habría
    ganado max_x, que el punto ni toca."""
    shape = _caja()
    p = [45.0, 30.0, 20.0]
    (centro,) = resolve_faces(shape, {"mode": "cerca", "point": p})
    assert centro.center().X == pytest.approx(50)  # max_x
    dos = resolve_faces(shape, {"mode": "cerca", "point": p, "count": 2, "medir": "superficie"})
    assert [f.center().Y for f in dos] == pytest.approx([30, 0])
    assert [f.center().Z for f in dos] == pytest.approx([0, 20])


def test_medir_invalido_es_error_claro_en_todo_modo():
    shape = _caja()
    for sel in ({"mode": "cerca", "point": [0, 0, 0], "medir": "superficial"},
                {"mode": "cara", "face": "tope", "medir": "borde"}):
        with pytest.raises(SelectorError, match="medir='.*' no existe.*centro.*superficie"):
            resolve_faces(shape, sel)
        with pytest.raises(SelectorError, match="medir="):
            resolve_edges(shape, sel)
    # None es el default (un dict de la API puede traer la clave en null)
    assert len(resolve_faces(shape, {"mode": "cerca", "point": [0, 0, 20], "medir": None})) == 1


# ------------------------------------------- consumidores: sin `medir` resuelve como antes
_LARGA = {"name": "Placa larga", "width": 1000, "depth": 100, "height": 6}  # x ±500, z ±3
_P_EXTREMO = [495.0, 0.0, 3.0]  # SOBRE la cara superior, a 5 mm del extremo +X


def _bbox(doc, fid):
    bb = doc.scene[fid].shape.bounding_box()
    return (bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z)


def _con_medir(sel: dict, medir):
    return {**sel, "medir": medir} if medir else dict(sel)


def _mate(medir):
    doc = Document("mate-medir")
    a = doc.execute("create_box", _LARGA)
    b = doc.execute("create_box", {"name": "Taco", "width": 40, "depth": 40, "height": 20,
                                   "position": {"x": 0, "y": 300, "z": 200}})
    doc.execute("add_mate", {
        "name": "m1", "type": "coincidente", "feature_a": a, "feature_b": b,
        "ref_a": _con_medir({"mode": "cerca", "point": _P_EXTREMO}, medir),
        "ref_b": {"mode": "cara", "face": "base"}})
    return doc, b


def test_mate_sin_medir_resuelve_como_antes():
    """Al centro, el punto sobre la cara superior junto al extremo elige la cara EXTREMO
    (centro a 5.8 mm, la superior a 495): el taco se apoya en el extremo. Sin la clave es
    exactamente eso; con superficie, se apoya arriba. El mate guardado no gana la clave."""
    viejo, b = _mate(None)
    centro, _ = _mate("centro")
    sup, _ = _mate("superficie")
    assert _bbox(viejo, b) == _bbox(centro, b)
    assert _bbox(viejo, b)[0] == pytest.approx(500, abs=1e-3)  # contra la cara extremo
    assert _bbox(sup, b)[2] == pytest.approx(3, abs=1e-3)       # sobre la cara superior
    assert "medir" not in viejo.mates["m1"]["ref_a"]
    assert sup.mates["m1"]["ref_a"]["medir"] == "superficie"


def _snap(medir):
    doc = Document("snap-medir")
    a = doc.execute("create_box", _LARGA)
    b = doc.execute("create_box", {"name": "Taco", "width": 40, "depth": 40, "height": 20,
                                   "position": {"x": 0, "y": 300, "z": 200}})
    doc.execute("snap_to", {
        "feature": b, "target": a, "cara": {"mode": "cara", "face": "base"},
        "cara_target": _con_medir({"mode": "cerca", "point": _P_EXTREMO}, medir)})
    return doc, b


def test_snap_to_sin_medir_resuelve_como_antes():
    viejo, b = _snap(None)
    centro, _ = _snap("centro")
    sup, _ = _snap("superficie")
    assert _bbox(viejo, b) == _bbox(centro, b)
    assert _bbox(viejo, b)[0] == pytest.approx(500, abs=1e-3)
    assert _bbox(sup, b)[2] == pytest.approx(3, abs=1e-3)


def _fillet(medir):
    doc = Document("fillet-medir")
    fid = doc.execute("create_box", {"name": "Bloque", "width": 100, "depth": 60, "height": 40})
    doc.execute("fillet", {"feature": fid, "radius": 5,
                           "edges": _con_medir({"mode": "cerca", "point": [45, 30, 20]}, medir)})
    return doc.scene[fid].shape.volume


def test_fillet_sin_medir_resuelve_como_antes():
    """Al centro se redondea la arista corta (40 mm) del extremo; a la superficie, la larga
    (100 mm) que el punto toca. Volumen quitado = (1 − π/4)·r²·L."""
    viejo, centro, sup = _fillet(None), _fillet("centro"), _fillet("superficie")
    lleno = 100 * 60 * 40
    quita = (1 - math.pi / 4) * 25
    assert viejo == centro
    assert lleno - viejo == pytest.approx(quita * 40, rel=1e-4)
    assert lleno - sup == pytest.approx(quita * 100, rel=1e-4)


# ------------------------------------------------------------------- params estrictos
def test_strict_acepta_medir_y_rechaza_un_valor_invalido():
    model = REGISTRY["fillet"].model
    ok = {"feature": "x", "edges": {"mode": "cerca", "point": [0, 0, 0], "medir": "superficie"}}
    assert unknown_paths(model, ok) == set()
    typo = {"feature": "x", "edges": {"mode": "cerca", "point": [0, 0, 0], "medr": "superficie"}}
    paths = unknown_paths(model, typo)
    assert paths == {("edges", "medr")}
    assert "¿quisiste decir «edges.medir»?" in rejection_text("fillet", model, paths)

    doc = Document("strict-medir")
    fid = doc.execute("create_box", {"name": "Bloque", "width": 100, "depth": 60, "height": 40})
    doc.execute("fillet", {"feature": fid, "radius": 5, "edges": ok["edges"]})
    with pytest.raises(_ERRS, match="medir"):
        doc.execute("fillet", {"feature": fid, "radius": 2, "edges": {
            "mode": "cerca", "point": [-45, -30, 20], "medir": "superficial"}})


# ------------------------------------------------------------------------------- FEA
def _client(doc):
    api.DOC = doc
    return TestClient(api.app)


def _placa_con_taladro():
    """Placa 100×100×6 centrada (z ±3) con un Ø20 pasante: el punto de carga está SOBRE el
    muro del taladro, en el lado +Y (no es el centro uv que publica get_topology)."""
    doc = Document("fea-medir")
    fid = doc.execute("create_box", {"name": "Placa acero", "width": 100, "depth": 100,
                                     "height": 6})
    doc.execute("drill_hole", {"feature": fid, "position": {"x": 20, "y": 0, "z": 10},
                               "axis": "-z", "diameter": 20})
    return doc, fid, [20.0, 10.0, 0.0]


def test_fea_carga_con_medir_invalido_es_400():
    doc, fid, p = _placa_con_taladro()
    r = _client(doc).post("/api/fea/static", json={
        "feature_id": fid, "fixed": {"mode": "cara", "face": "min_x"},
        "loads": [{"selector": {"mode": "cerca", "point": p, "medir": "borde"},
                   "force_n": [0, 0, -500]}], "save": False})
    assert r.status_code == 400, r.text
    assert "medir='borde' no existe" in r.json()["detail"]


@requires_fea
def test_fea_carga_sobre_un_taladro_con_superficie():
    doc, fid, p = _placa_con_taladro()
    sel = {"mode": "cerca", "point": p, "medir": "superficie"}
    (cara,) = resolve_faces(doc.scene[fid].shape, sel)
    assert _tipo(cara) == "CYLINDER" and cara.radius == pytest.approx(10)
    r = _client(doc).post("/api/fea/static", json={
        "feature_id": fid, "fixed": {"mode": "cara", "face": "min_x"},
        "loads": [{"selector": sel, "force_n": [0, 0, -500]}],
        "mesh_size_mm": 12.0, "save": False})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["fs"] is not None and res["fs"] > 0
    assert 0 < res["desplazamiento_max_mm"] < 10
