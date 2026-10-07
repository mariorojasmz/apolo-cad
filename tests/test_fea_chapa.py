"""FEA de la chapa empernada (plan `docs/plans/fea-chapa-empernada.md`, F1).

D4: el FEA encuentra la cara de un taladro — `FaceDesc` usa el CENTROIDE (el mismo que da
gmsh), no el punto en la mitad del dominio uv que build123d da por defecto en una cara curva.
D3: todo fallo de `gmsh.model.mesh.generate` es un `FeaError` (400 en la API) que nombra la
pieza y da salidas, nunca un 500 crudo.

Los fallos de malla se SIMULAN con un `generate` monkeypatcheado que nombra superficies
reales del modelo vivo: la geometría que hoy falla en gmsh (la chapa plegada con esquinas)
mallará tras F2 y no sirve de test permanente. Los numéricos exigen el extra [fea].
"""
import importlib.util

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.fea import FeaError

_FEA_OK = (importlib.util.find_spec("gmsh") is not None
           and importlib.util.find_spec("skfem") is not None)
requires_fea = pytest.mark.skipif(not _FEA_OK, reason="extra [fea] no instalado")

ACERO = dict(e_mpa=200000.0, yield_mpa=250.0, density_kg_mm3=7.85e-6, material="acero")


def _placa(tmp_path, hueco=(50.0, 50.0), r=20.0, nombre="placa.step"):
    """Placa 100×100×6 (x, y ∈ [0, 100], z ∈ [0, 6]) con un taladro pasante de radio `r`.
    Con malla de 10 mm son ~900 tets: el solve P2 tarda ~1 s (a 3000 tets, ~11 s)."""
    from build123d import Box, Cylinder, Pos, export_step

    shape = Pos(50, 50, 3) * Box(100, 100, 6) - Pos(hueco[0], hueco[1], 3) * Cylinder(r, 20)
    step = str(tmp_path / nombre)
    export_step(shape, step)
    return step, shape


def _caras(shape, pred):
    from apolo.fea.mesher import FaceDesc

    return [FaceDesc.from_face(f) for f in shape.faces() if pred(f)]


def _es(f, tipo):
    return str(f.geom_type).rsplit(".", 1)[-1].upper() == tipo


# ---------------------------------------------------------- D4: la cara de un taladro
@requires_fea
def test_carga_en_el_taladro_resuelve(tmp_path):
    """Taladro Ø40: el centro uv del cilindro queda a r = 20 mm del eje y el match (tol
    1e-3·diag ≈ 0.14 mm) no lo encontraba → «No encontré en la malla la cara». Con el
    centroide el descriptor cae en el eje, como en gmsh, y el análisis resuelve."""
    from apolo.fea.static import run_static_analysis

    step, shape = _placa(tmp_path)
    taladro = _caras(shape, lambda f: _es(f, "CYLINDER"))
    assert len(taladro) == 1
    assert taladro[0].center == pytest.approx((50.0, 50.0, 3.0), abs=1e-6)
    assert taladro[0].tipo == "cilindro"
    res, _ = run_static_analysis(
        step, pieza="Placa con taladro",
        fixed=_caras(shape, lambda f: abs(f.center().X) < 1e-6),
        loads=[{"descs": taladro, "force_n": [0.0, 0.0, -500.0]}],
        mesh_size_mm=10.0, **ACERO)
    assert res["fs"] is not None and res["fs"] > 0
    assert 0 < res["desplazamiento_max_mm"] < 10


@requires_fea
def test_carga_en_cara_plana_con_taladro_descentrado(tmp_path):
    """La cara superior con un agujero DESCENTRADO: su centroide (50.81, 50.65) no es el
    centro del rectángulo; el descriptor lo da y la malla la encuentra. (En una cara PLANA
    build123d 0.10 ya daba el centroide por defecto: este caso guarda que el cambio no la
    rompa; el que fallaba es el curvo, abajo.)"""
    from apolo.fea.static import run_static_analysis

    step, shape = _placa(tmp_path, hueco=(25.0, 30.0), r=10.0)
    tope = _caras(shape, lambda f: abs(f.center().Z - 6.0) < 1e-6)
    assert len(tope) == 1 and tope[0].tipo == "plano"
    assert tope[0].center[:2] == pytest.approx((50.81, 50.65), abs=0.01)
    res, _ = run_static_analysis(
        step, pieza="Placa descentrada",
        fixed=_caras(shape, lambda f: abs(f.center().X) < 1e-6),
        loads=[{"descs": tope, "pressure_mpa": 0.05}],
        mesh_size_mm=10.0, **ACERO)
    assert res["fs"] is not None and res["desplazamiento_max_mm"] > 0


@requires_fea
def test_carga_en_cara_curva_con_agujero(tmp_path):
    """Un eje Ø30 con un taladro transversal: la cara cilíndrica exterior (con agujeros) es
    curva y su punto uv queda a 15 mm del centroide → hoy tampoco casaba."""
    from build123d import Cylinder, Pos, Rot, export_step

    from apolo.fea.static import run_static_analysis

    shape = Cylinder(15, 100) - Pos(0, 0, 20) * Rot(0, 90, 0) * Cylinder(4, 40)  # z ∈ [-50, 50]
    step = str(tmp_path / "eje.step")
    export_step(shape, step)
    manto = _caras(shape, lambda f: _es(f, "CYLINDER") and f.area > 5000)
    assert len(manto) == 1
    res, _ = run_static_analysis(
        step, pieza="Eje con pasador",
        fixed=_caras(shape, lambda f: abs(f.center().Z + 50.0) < 1e-6),
        loads=[{"descs": manto, "force_n": [300.0, 0.0, 0.0]}],
        mesh_size_mm=10.0, **ACERO)
    assert res["fs"] is not None and res["desplazamiento_max_mm"] > 0


# ------------------------------------------------- D3: el fallo de malla nombra la pieza
def _superficies_de_pieza(gmsh, nombre_grupo: str) -> list[int]:
    """Superficies que bordean SÓLO los volúmenes del physical group `nombre_grupo`."""
    vols: set[int] = set()
    for dim, tag in gmsh.model.getPhysicalGroups(3):
        if gmsh.model.getPhysicalName(dim, tag) == nombre_grupo:
            vols |= {int(v) for v in gmsh.model.getEntitiesForPhysicalGroup(dim, tag)}
    propias = []
    for _, s in gmsh.model.getEntities(2):
        ups, _ = gmsh.model.getAdjacencies(2, s)
        if ups.size and {int(v) for v in ups} <= vols:
            propias.append(int(s))
    return propias


def _falla_con(monkeypatch, elegir):
    """Sustituye `gmsh.model.mesh.generate` por uno que lanza el error de gmsh nombrando dos
    superficies REALES del modelo vivo (las que elige `elegir(gmsh)`)."""
    import gmsh

    def _generate(dim=3):
        a, b = elegir(gmsh)[:2]
        raise Exception(f"Invalid boundary mesh (overlapping facets) on surface {a} surface {b}")

    monkeypatch.setattr(gmsh.model.mesh, "generate", _generate)


def _dos_cajas(tmp_path):
    """Dos cajas 100×20×20 pegadas en x = 100: «Raíz» (b1, x 0..100) y «Punta» (b2)."""
    from build123d import Box, Pos, export_step

    from apolo.fea.mesher import PieceMesh

    b1 = Pos(50, 0, 0) * Box(100, 20, 20)
    b2 = Pos(150, 0, 0) * Box(100, 20, 20)
    s1 = str(tmp_path / "b1.step"); export_step(b1, s1)
    s2 = str(tmp_path / "b2.step"); export_step(b2, s2)
    pieces = [PieceMesh(key="b1", step_path=s1, name="Raíz"),
              PieceMesh(key="b2", step_path=s2, name="Punta")]
    fixed = _caras(b1, lambda f: abs(f.center().X) < 1e-6)
    load = _caras(b2, lambda f: abs(f.center().X - 200.0) < 1e-6)
    return pieces, fixed, load


@requires_fea
def test_fallo_de_malla_del_ensamblaje_nombra_la_pieza(tmp_path, monkeypatch):
    from apolo.fea.mesher import mesh_assembly

    pieces, fixed, load = _dos_cajas(tmp_path)
    _falla_con(monkeypatch, lambda g: _superficies_de_pieza(g, "piece_1"))
    with pytest.raises(FeaError) as ei:
        mesh_assembly(pieces, fixed, {"load_0": load}, str(tmp_path / "x.msh"), mesh_size_mm=8.0)
    msg = str(ei.value)
    assert "«Punta» (b2)" in msg and "Raíz" not in msg and "b1" not in msg
    assert "8 mm" in msg and "overlapping facets" in msg
    assert "plano" in msg and "mm²" in msg
    # las tres salidas: excluir, analizarla sola con fea_static, otra malla
    assert "excluye" in msg and "fea_static" in msg and "mesh_size_mm" in msg


@requires_fea
def test_fallo_de_malla_de_una_pieza_nombra_la_pieza_y_el_radio(tmp_path, monkeypatch):
    from apolo.fea.mesher import mesh_step

    step, _ = _placa(tmp_path)

    def _cilindro_y_plano(g):
        tipos = {int(t): g.model.getType(2, t) for _, t in g.model.getEntities(2)}
        return ([t for t, k in tipos.items() if k == "Cylinder"][:1]
                + [t for t, k in tipos.items() if k == "Plane"][:1])

    _falla_con(monkeypatch, _cilindro_y_plano)
    with pytest.raises(FeaError) as ei:
        mesh_step(step, {}, str(tmp_path / "x.msh"), mesh_size_mm=5.0, pieza="Placa de prueba")
    msg = str(ei.value)
    assert "«Placa de prueba»" in msg and "5 mm" in msg
    assert "cilindro r ≈ 20 mm" in msg and "plano" in msg
    assert "mesh_size_mm" in msg


@requires_fea
@pytest.mark.parametrize("ensamblaje", [True, False])
def test_fallo_sin_superficies_lleva_el_texto_de_gmsh(tmp_path, monkeypatch, ensamblaje):
    import gmsh

    from apolo.fea.mesher import mesh_assembly, mesh_step

    def _generate(dim=3):
        raise Exception("PLC Error: A segment and a facet intersect at point")

    monkeypatch.setattr(gmsh.model.mesh, "generate", _generate)
    pieces, fixed, load = _dos_cajas(tmp_path)
    with pytest.raises(FeaError) as ei:
        if ensamblaje:
            mesh_assembly(pieces, fixed, {"load_0": load}, str(tmp_path / "x.msh"),
                          mesh_size_mm=8.0)
        else:
            mesh_step(pieces[0].step_path, {}, str(tmp_path / "x.msh"), mesh_size_mm=8.0,
                      pieza="Raíz")
    msg = str(ei.value)
    assert "PLC Error: A segment and a facet intersect at point" in msg
    assert "mesh_size_mm" in msg
    if ensamblaje:
        assert "fea_static" in msg and "excluye" in msg
    else:
        assert "«Raíz»" in msg


# ----------------------------------------------------------------------- por la API
def _client(doc):
    api.DOC = doc
    return TestClient(api.app)


@requires_fea
def test_api_assembly_fallo_de_malla_400_con_la_pieza(monkeypatch):
    doc = Document("chapa-asm")
    pata = doc.execute("create_box", {"name": "Pata A36", "width": 30, "depth": 30,
                                      "height": 100, "position": {"z": 50}})       # z 0..100
    cama = doc.execute("create_box", {"name": "Cama mesa A36", "width": 30, "depth": 30,
                                      "height": 20, "position": {"z": 110}})       # z 100..120
    doc.execute("create_group", {"name": "Estructura", "members": [pata, cama]})
    doc.grounds["g1"] = {"feature": pata}

    def _de_la_cama(g):  # caras de la cama: tope (z 120) y laterales (z 110)
        return [int(t) for _, t in g.model.getEntities(2)
                if g.model.occ.getCenterOfMass(2, t)[2] > 105.0]

    _falla_con(monkeypatch, _de_la_cama)
    r = _client(doc).post("/api/fea/assembly", json={"group": "Estructura", "carga_kg": 50,
                                                     "mesh_size_mm": 10.0, "save": False})
    assert r.status_code == 400, r.text
    detalle = r.json()["detail"]
    assert f"«Cama mesa A36» ({cama})" in detalle and "Pata" not in detalle
    assert "fea_static" in detalle and "mesh_size_mm" in detalle


@requires_fea
def test_api_static_fallo_de_malla_400_con_la_pieza(monkeypatch):
    doc = Document("chapa-static")
    fid = doc.execute("create_box", {"name": "Viga acero", "width": 100, "depth": 10,
                                     "height": 10})
    _falla_con(monkeypatch, lambda g: [int(t) for _, t in g.model.getEntities(2)])
    r = _client(doc).post("/api/fea/static", json={
        "feature_id": fid, "fixed": {"mode": "cara", "face": "min_x"},
        "loads": [{"selector": {"mode": "cara", "face": "max_x"}, "force_n": [0, 0, -100]}],
        "mesh_size_mm": 5.0, "save": False})
    assert r.status_code == 400, r.text
    assert "«Viga acero»" in r.json()["detail"]


@requires_fea
def test_api_static_carga_en_taladro_por_cerca():
    """El caso del 72 en chico: carga sobre un taladro con `cerca` y el centro que publica
    get_topology (el punto uv, el que mide `cerca`) → el kernel elige el cilindro y el FEA
    lo encuentra en la malla (antes: 400 «No encontré en la malla la cara»)."""
    doc = Document("chapa-taladro")
    fid = doc.execute("create_box", {"name": "Placa acero", "width": 100, "depth": 100,
                                     "height": 6})
    doc.execute("drill_hole", {"feature": fid, "cara": {"mode": "cara", "face": "tope"},
                               "en_cara": {"u": 20, "v": 0}, "diameter": 20})
    client = _client(doc)
    topo = client.get(f"/api/features/{fid}/topology", params={"only": "caras"}).json()
    cilindros = [c for c in topo["faces"] if "CYLINDER" in c["tipo"]]
    assert len(cilindros) == 1
    r = client.post("/api/fea/static", json={
        "feature_id": fid, "fixed": {"mode": "cara", "face": "min_x"},
        "loads": [{"selector": {"mode": "cerca", "point": cilindros[0]["center"]},
                   "force_n": [0, 0, -500]}],
        "mesh_size_mm": 12.0, "save": False})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["fs"] is not None and res["fs"] > 0
    assert 0 < res["desplazamiento_max_mm"] < 10
