"""FEA de la chapa empernada (plan `docs/plans/fea-chapa-empernada.md`, F1 y F2).

D4: el FEA encuentra la cara de un taladro — `FaceDesc` usa el CENTROIDE (el mismo que da
gmsh), no el punto en la mitad del dominio uv que build123d da por defecto en una cara curva.
D3: todo fallo de `gmsh.model.mesh.generate` es un `FeaError` (400 en la API) que nombra la
pieza y da salidas, nunca un 500 crudo.
D2 (F2): la chapa plegada con pestañas ADYACENTES malla refinando localmente sus radios
(`fea/refine.py`) en dos etapas, sin cambiar la geometría; sin radios chicos, ningún campo.

Los fallos de D3 se SIMULAN con un `generate` monkeypatcheado que nombra superficies reales del
modelo vivo; los de F2 son reales (la bandeja con esquina falla sin refinar, gmsh 4.15.2): se
aserta éxito y cordura, no números de tets. Los numéricos exigen el extra [fea].
"""
import importlib.util
import math

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
    """Sustituye `gmsh.model.mesh.generate` por uno que lanza SIEMPRE el error de gmsh
    nombrando dos superficies REALES del modelo vivo (las que elige `elegir(gmsh)`).
    Devuelve la lista de llamadas (F2: cuántos intentos hubo)."""
    import gmsh

    llamadas = []

    def _generate(dim=3):
        llamadas.append(dim)
        a, b = elegir(gmsh)[:2]
        raise Exception(f"Invalid boundary mesh (overlapping facets) on surface {a} surface {b}")

    monkeypatch.setattr(gmsh.model.mesh, "generate", _generate)
    return llamadas


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


# ------------------------------------------- D2 (F2): la chapa plegada con esquinas malla
SIN_CAMPO = {"etapa": 0, "radios": 0, "r_min_mm": None}


def _bandeja(tmp_path, lados=("frente", "izquierda"), holes=(), nombre="bandeja.step"):
    """Bandeja de chapa 60×200×3 (base z 0..3, x ±30, y ±100), pestañas de 34 mm y `radio` 3:
    con dos ADYACENTES los radios se cortan en inglete y gmsh, sin refinar, falla de 8 a 35 mm
    (medido en la F2). La «frente» (cara exterior y = 100) lleva los taladros `holes`."""
    from build123d import export_step

    from apolo.library.sheetmetal import Flap, sheet_metal_solid

    flaps = [Flap(lado=lado, altura=34, holes=list(holes) if lado == "frente" else [])
             for lado in lados]
    shape = sheet_metal_solid(60, 200, 3, [], 0, 90, 3, flaps=flaps)
    step = str(tmp_path / nombre)
    export_step(shape, step)
    return step, shape


def _bandeja_empernada(tmp_path):
    """La bandeja con dos taladros Ø11 en la pestaña «frente», contra un alma de chapa 3 mm
    (y 100..103) con los taladros COINCIDENTES (mismo Ø y eje), cara a cara. Empotrada por la
    cara trasera del alma; la carga, en la cara inferior de la bandeja (voladizo de 200 mm)."""
    from build123d import Box, CenterOf, Cylinder, Pos, Rot, export_step

    step_b, bandeja = _bandeja(tmp_path, holes=[(-15.0, 12.0, 11.0), (15.0, 12.0, 11.0)])
    ejes = [f.center(CenterOf.MASS) for f in bandeja.faces()
            if _es(f, "CYLINDER") and abs(f.radius - 5.5) < 1e-6]
    assert len(ejes) == 2
    alma = Pos(0, 101.5, 20) * Box(100, 3, 50)
    for c in ejes:
        alma = alma - Pos(c.X, 101.5, c.Z) * Rot(90, 0, 0) * Cylinder(5.5, 10)
    step_a = str(tmp_path / "alma.step")
    export_step(alma, step_a)
    piezas = [{"key": k, "name": n, "step_path": s, "nu": 0.3, "volumen_mm3": v, **ACERO}
              for k, n, s, v in (("b", "Bandeja de chapa", step_b, bandeja.volume),
                                 ("a", "Alma C", step_a, alma.volume))]
    fijas = _caras(alma, lambda f: abs(f.center().Y - 103.0) < 1e-6)
    carga = _caras(bandeja, lambda f: abs(f.center().Z) < 1e-6)
    assert len(fijas) == 1 and len(carga) == 1
    return piezas, fijas, carga


@requires_fea
def test_bandeja_empernada_resuelve_con_refinamiento(tmp_path):
    """El mínimo que pidió Mario: chapa con pestañas adyacentes y r = 3, empernada con taladros
    coincidentes a otra chapa, en contacto. Sin refinar, esta geometría a 35 mm falla con
    «overlapping facets» en los dos radios de la esquina (medido en la F2 dejando `aplicar`
    sin efecto); con la etapa 1 resuelve y la hipótesis lo declara."""
    from apolo.fea.assembly import run_assembly_analysis

    piezas, fijas, carga = _bandeja_empernada(tmp_path)
    res, _ = run_assembly_analysis(piezas, grupo="bandeja", fixed=fijas,
                                   loads=[{"descs": carga, "force_n": [0.0, 0.0, -200.0]}],
                                   mesh_size_mm=35.0)
    assert res["n_piezas"] == 2
    assert res["fs"] is not None and math.isfinite(res["fs"]) and res["fs"] > 0
    assert 0 < res["desplazamiento_max_mm"] < 10
    ref = res["refinamiento"]
    assert ref["etapa"] >= 1 and ref["radios"] >= 2 and ref["r_min_mm"] == pytest.approx(3.0)
    h = [x for x in res["hipotesis"] if "malla refinada localmente" in x]
    assert h and f"etapa {ref['etapa']}" in h[0] and "3 mm" in h[0]
    assert "sin cambiar la geometría" in h[0]


@requires_fea
def test_bandeja_sola_malla_refinada(tmp_path):
    """`fea_static` de la bandeja a 35 mm (por `mesh_step`): con gmsh 4.15.2 bastan los ingletes
    (etapa 1). La etapa exacta depende de la versión/plataforma de gmsh: se aserta que malla
    refinada, no en qué vuelta."""
    from apolo.fea.static import run_static_analysis

    step, shape = _bandeja(tmp_path)
    res, _ = run_static_analysis(
        step, pieza="Bandeja de chapa",
        fixed=_caras(shape, lambda f: _es(f, "PLANE") and abs(f.center().Y - 100.0) < 1e-6),
        loads=[{"descs": _caras(shape, lambda f: abs(f.center().Z) < 1e-6),
                "force_n": [0.0, 0.0, -100.0]}],
        mesh_size_mm=35.0, **ACERO)
    ref = res["refinamiento"]
    assert ref["etapa"] in (1, 2) and ref["radios"] == 2
    assert ref["r_min_mm"] == pytest.approx(3.0)
    assert res["fs"] is not None and res["desplazamiento_max_mm"] > 0
    h = [x for x in res["hipotesis"] if "malla refinada localmente" in x]
    assert h and f"etapa {ref['etapa']}" in h[0]


@requires_fea
def test_etapa_2_si_la_1_no_alcanza(tmp_path, monkeypatch):
    """Camino determinista de la etapa 2: el primer `generate` falla nombrando dos radios
    reales; gmsh no re-malla el mismo modelo → se reconstruye y se refinan TODOS los radios."""
    import gmsh

    from apolo.fea import refine
    from apolo.fea.mesher import mesh_step

    step, _ = _bandeja(tmp_path)
    original = gmsh.model.mesh.generate
    fallos = _falla_con(monkeypatch, lambda g: sorted(refine.radios_chicos(g, 35.0 / 4)))
    falla = gmsh.model.mesh.generate
    # sólo el PRIMER intento falla; el segundo es el generate real
    monkeypatch.setattr(gmsh.model.mesh, "generate",
                        lambda dim=3: (original if fallos else falla)(dim))
    malla = mesh_step(step, {}, str(tmp_path / "b.msh"), mesh_size_mm=35.0, pieza="Bandeja")
    assert len(fallos) == 1
    assert malla["refinamiento"]["etapa"] == 2 and malla["n_tets"] > 0


@requires_fea
def test_etapa_2_real_entre_un_cuarto_y_medio_radio(tmp_path):
    """La bandeja de cuatro pestañas a 10 mm (r/size = 0.3): ningún radio < size/4, así que la
    etapa 1 no crea campo; con gmsh 4.15.2 la malla falla de verdad y la etapa 2 (radios <
    size/2) malla. Otra versión de gmsh podría mallarla sin campo (etapa 0): lo que se exige es
    que malle y que la etapa 1 nunca refine aquí."""
    from apolo.fea.mesher import mesh_step

    step, _ = _bandeja(tmp_path, lados=("frente", "atras", "izquierda", "derecha"))
    malla = mesh_step(step, {}, str(tmp_path / "b.msh"), mesh_size_mm=10.0, pieza="Bandeja")
    ref = malla["refinamiento"]
    assert ref["etapa"] in (0, 2) and malla["n_tets"] > 0
    if ref["etapa"] == 2:
        assert ref["radios"] == 4 and ref["r_min_mm"] == pytest.approx(3.0)


def _tets_sin_campo(step: str, size: float) -> int:
    """Tets de la malla de antes de F2: importar, tamaños por defecto y `generate`."""
    import gmsh

    gmsh.initialize(interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.occ.importShapes(step)
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMax", size)
        gmsh.option.setNumber("Mesh.MeshSizeMin", size / 3.0)
        gmsh.model.mesh.generate(3)
        return int(sum(len(t) for t in gmsh.model.mesh.getElements(3)[1]))
    finally:
        gmsh.finalize()


@requires_fea
def test_sin_radios_chicos_no_crea_campos(tmp_path, monkeypatch):
    """Dos cajas y una placa con un taladro Ø4 COMPLETO (r = 2 < size/4, pero da la vuelta: no
    es un radio de plegado): ningún campo, etapa 0 y la misma malla que antes de F2."""
    from apolo.fea import refine
    from apolo.fea.mesher import mesh_assembly, mesh_step

    def _prohibido(*_a, **_k):
        raise AssertionError("sin radios chicos no se crea ningún campo")

    monkeypatch.setattr(refine, "aplicar", _prohibido)
    pieces, fixed, load = _dos_cajas(tmp_path)
    malla = mesh_assembly(pieces, fixed, {"load_0": load}, str(tmp_path / "a.msh"),
                          mesh_size_mm=8.0)
    assert malla["refinamiento"] == SIN_CAMPO
    step, _ = _placa(tmp_path, r=2.0)
    malla = mesh_step(step, {}, str(tmp_path / "p.msh"), mesh_size_mm=10.0)
    assert malla["refinamiento"] == SIN_CAMPO
    assert malla["n_tets"] == _tets_sin_campo(step, 10.0)


@requires_fea
@pytest.mark.parametrize("con_radios", [True, False])
def test_fallo_persistente_como_mucho_dos_intentos(tmp_path, monkeypatch, con_radios):
    """Un `generate` que falla SIEMPRE: con radios chicos se reconstruye una vez (2 intentos),
    sin ellos no hay a qué reintentar (1); el error es el de D3, con su pieza."""
    from apolo.fea import refine
    from apolo.fea.mesher import PieceMesh, mesh_assembly

    if con_radios:
        piezas, fixed, load = _bandeja_empernada(tmp_path)
        pieces = [PieceMesh(key=p["key"], step_path=p["step_path"], name=p["name"])
                  for p in piezas]
        llamadas = _falla_con(monkeypatch, lambda g: sorted(refine.radios_chicos(g, 35.0 / 4)))
    else:
        pieces, fixed, load = _dos_cajas(tmp_path)
        llamadas = _falla_con(monkeypatch, lambda g: _superficies_de_pieza(g, "piece_1"))
    with pytest.raises(FeaError) as ei:
        mesh_assembly(pieces, fixed, {"load_0": load}, str(tmp_path / "a.msh"),
                      mesh_size_mm=35.0 if con_radios else 8.0)
    msg = str(ei.value)
    if con_radios:
        assert len(llamadas) == 2 and "«Bandeja de chapa» (b)" in msg and "Alma" not in msg
        assert "cilindro r ≈ 3 mm" in msg and "fea_static" in msg
    else:
        assert len(llamadas) == 1 and "«Punta» (b2)" in msg


@requires_fea
def test_ensamblaje_de_una_sola_pieza_malla(tmp_path):
    """`occ.fragment` de UN volumen devuelve `outmap` vacío: antes, «Ninguna pieza sobrevivió a
    la fragmentación»; ahora el volumen se asigna a su pieza sin fragmentar."""
    from build123d import Box, Pos, export_step

    from apolo.fea.mesher import PieceMesh, mesh_assembly

    caja = Pos(50, 0, 0) * Box(100, 20, 20)
    step = str(tmp_path / "caja.step")
    export_step(caja, step)
    malla = mesh_assembly(
        [PieceMesh(key="c1", step_path=step, name="Viga")],
        _caras(caja, lambda f: abs(f.center().X) < 1e-6),
        {"load_0": _caras(caja, lambda f: abs(f.center().X - 100.0) < 1e-6)},
        str(tmp_path / "a.msh"), mesh_size_mm=8.0)
    assert [(g["key"], g["name"], g["n_vols"]) for g in malla["piece_groups"]] == [
        ("c1", "piece_0", 1)]
    assert malla["n_tets"] > 0 and malla["shared_volumes"] == 0 and malla["absorbidas"] == []
