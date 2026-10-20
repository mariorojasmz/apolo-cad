"""Perfiles abiertos con orientación declarativa y anclas por familia (plan perfiles-con-acuerdo,
F3: D3 y D4).

D3: `insert_component(orientacion=…)` traduce ejes del mundo a rotación (U: largo + abre_hacia;
I: largo + canto; L: alas); sin ella, la `rotation` de siempre (un log viejo regenera igual).
D4: los perfiles publican anclas (`cara_alma_interior`, `zona_plana`…) que sobreviven al taladro
(que borra `Feature.matrix`) y que el lint de asiento usa como marco antes que el bbox."""

import itertools

import pytest
from build123d import CenterOf

from apolo.doc.errors import DocumentError
from apolo.doc import Document
from apolo.kernel.matrix import compose_place
from apolo.library.acuerdos import inicio_zona_plana_alma
from apolo.library.catalog import CATALOG
from apolo.library.lint_asiento import asiento_zona_plana_lint
from apolo.library.perfiles_abiertos import rotacion_por_orientacion

DIRS = ["+x", "-x", "+y", "-y", "+z", "-z"]
EJE = {"x": 0, "y": 1, "z": 2}


def _vec(d):
    v = [0.0, 0.0, 0.0]
    v[EJE[d[-1]]] = -1.0 if d.startswith("-") else 1.0
    return v


def _insertar(ref, length=500, **extra):
    doc = Document()
    fid = doc.execute("insert_component", {"component": ref, "length": length, **extra})
    return doc, fid


def _geo(feat):
    bb = feat.shape.bounding_box()
    c = feat.shape.center(CenterOf.MASS)
    lo, hi = (bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)
    dims = [hi[i] - lo[i] for i in range(3)]
    off = [(c.X, c.Y, c.Z)[i] - (lo[i] + hi[i]) / 2 for i in range(3)]
    return dims, off


def _plana(m):
    return [v for fila in m for v in fila]


# --------------------------------------------------------------------------- D4: anclas
def test_anclas_del_canal():
    """UPN-100 sin girar (alma en −X, abre hacia +X, h en Y): caras del alma y límites de la
    zona plana a s = 17.87 de cada canto, con el eje hacia el centro."""
    doc, fid = _insertar("UPN-100")
    a = doc.scene[fid].anchors
    assert {"cara_alma_interior", "dorso_alma", "zona_plana", "zona_plana_1",
            "zona_plana_2"} <= set(a)
    assert a["cara_alma_interior"]["origin"] == pytest.approx([-25 + 6, 0, 0], abs=1e-9)
    assert a["cara_alma_interior"]["axis"] == pytest.approx([1, 0, 0], abs=1e-9)
    assert a["dorso_alma"]["origin"] == pytest.approx([-25, 0, 0], abs=1e-9)
    assert a["dorso_alma"]["axis"] == pytest.approx([-1, 0, 0], abs=1e-9)
    s = inicio_zona_plana_alma(CATALOG["UPN-100"].specs)
    assert s == pytest.approx(17.87, abs=0.01)
    assert a["zona_plana_1"]["origin"] == pytest.approx([-19, -(50 - s), 0], abs=1e-9)
    assert a["zona_plana_1"]["axis"] == pytest.approx([0, 1, 0], abs=1e-9)
    assert a["zona_plana_2"]["origin"] == pytest.approx([-19, 50 - s, 0], abs=1e-9)
    assert a["zona_plana_2"]["axis"] == pytest.approx([0, -1, 0], abs=1e-9)
    assert a["zona_plana"] == a["cara_alma_interior"]  # simétrica: el centro de la cara


def test_anclas_de_la_viga_y_del_angulo():
    doc, fid = _insertar("IPE-100")
    a = doc.scene[fid].anchors
    assert a["cara_alma_interior"]["origin"] == pytest.approx([2.05, 0, 0], abs=1e-9)
    assert a["cara_alma_opuesta"]["axis"] == pytest.approx([-1, 0, 0], abs=1e-9)
    s = inicio_zona_plana_alma(CATALOG["IPE-100"].specs)
    assert a["zona_plana_2"]["origin"][1] == pytest.approx(50 - s)  # tf + r1 = 12.7
    assert s == pytest.approx(12.7)
    doc, fid = _insertar("ANG-50X5")
    a = doc.scene[fid].anchors
    assert a["talon"]["origin"] == pytest.approx([-25, -25, 0], abs=1e-9)
    assert a["talon"]["axis"] == pytest.approx([0, 0, 1], abs=1e-9)
    # ala 1 hacia +x (cara interior en y = −20, normal +y); zona plana [12, 46.5] del talón
    assert a["cara_ala_1"]["origin"] == pytest.approx([2.5, -20, 0], abs=1e-9)
    assert a["zona_plana_ala_1"]["origin"] == pytest.approx([-25 + 29.25, -20, 0], abs=1e-9)
    assert a["zona_plana_ala_2"]["axis"] == pytest.approx([1, 0, 0], abs=1e-9)


def test_las_anclas_sobreviven_al_taladro_y_al_movimiento():
    """Taladrar borra `Feature.matrix` (geometría única) pero no las anclas; un transform las
    arrastra con la pieza."""
    doc, fid = _insertar("UPN-100", length=1000)
    antes = doc.scene[fid].anchors
    doc.execute("drill_hole", {"feature": fid, "axis": "x", "diameter": 13.5, "depth": 0,
                               "position": {"x": -30, "y": 0, "z": 0}})
    assert doc.scene[fid].matrix is None
    assert doc.scene[fid].anchors == antes
    doc.execute("transform", {"feature": fid, "translate": {"x": 100, "y": 0, "z": 0}})
    assert doc.scene[fid].anchors["dorso_alma"]["origin"] == pytest.approx([75, 0, 0])


def test_mate_contra_la_zona_plana():
    """Una placa se asienta por mate `coincidente` en el centro de la zona plana del alma."""
    doc, fid = _insertar("UPN-100", orientacion={"largo": "x", "abre_hacia": "-y"},
                         position={"x": 0, "y": 0, "z": 300})
    placa = doc.execute("create_box", {"name": "Placa de asiento", "width": 40, "depth": 8,
                                       "height": 40, "position": {"x": 400, "y": -400}})
    doc.execute("add_mate", {"name": "placa_alma", "type": "coincidente", "feature_a": fid,
                             "feature_b": placa, "ref_a": {"mode": "ancla", "name": "zona_plana"},
                             "ref_b": {"mode": "cara", "face": "max_y"}})
    bb = doc.scene[placa].shape.bounding_box()
    zona = doc.scene[fid].anchors["zona_plana"]["origin"]
    assert bb.max.Y == pytest.approx(zona[1], abs=1e-6)  # contra la cara interior del alma
    assert ((bb.min.X + bb.max.X) / 2, (bb.min.Z + bb.max.Z) / 2) == pytest.approx(
        (zona[0], zona[2]), abs=1e-6)


# ---------------------------------------------------------------------- D3: orientación
@pytest.mark.parametrize("largo,abre", [(lg, ab) for lg in "xyz" for ab in DIRS if ab[-1] != lg])
def test_canal_abre_hacia(largo, abre):
    """El canal queda a lo largo de `largo` y abre hacia `abre_hacia`: el centroide se corre
    hacia el alma (lado contrario) y el ancla `cara_alma_interior` apunta a `abre_hacia`."""
    doc, fid = _insertar("UPN-100", orientacion={"largo": largo, "abre_hacia": abre})
    f = doc.scene[fid]
    dims, off = _geo(f)
    assert dims[EJE[largo]] == pytest.approx(500)
    v = _vec(abre)
    i = EJE[abre[-1]]
    assert dims[i] == pytest.approx(50) and off[i] * v[i] < -1  # alma del lado opuesto
    assert f.anchors["cara_alma_interior"]["axis"] == pytest.approx(v, abs=1e-9)


@pytest.mark.parametrize("largo,canto", [(lg, c) for lg in "xyz" for c in "xyz" if c != lg])
def test_viga_canto(largo, canto):
    doc, fid = _insertar("IPE-100", orientacion={"largo": f"-{largo}", "canto": canto})
    dims, _ = _geo(doc.scene[fid])
    assert dims[EJE[largo]] == pytest.approx(500) and dims[EJE[canto]] == pytest.approx(100)


@pytest.mark.parametrize("d1,d2", [(a, b) for a, b in itertools.permutations(DIRS, 2)
                                   if a[-1] != b[-1]])
def test_angulo_alas(d1, d2):
    """Las alas salen del talón hacia `alas`: el centroide se corre hacia el talón en ambas
    direcciones y el ala 1 tiene su cara interior mirando hacia el ala 2."""
    doc, fid = _insertar("ANG-50X5", length=300, orientacion={"alas": [d1, d2]})
    f = doc.scene[fid]
    dims, off = _geo(f)
    for d in (d1, d2):
        i = EJE[d[-1]]
        assert dims[i] == pytest.approx(50) and off[i] * _vec(d)[i] < -1
    assert f.anchors["cara_ala_1"]["axis"] == pytest.approx(_vec(d2), abs=1e-9)
    largo = ({"x", "y", "z"} - {d1[-1], d2[-1]}).pop()
    assert dims[EJE[largo]] == pytest.approx(300)


def test_orientacion_equivale_a_su_rotacion():
    """La orientación es SÓLO una rotación: misma matriz y misma geometría que dar el euler."""
    ori = {"largo": "x", "abre_hacia": "-z"}
    rot = rotacion_por_orientacion("channel", ori)
    d1, a = _insertar("UPN-120", position={"x": 10, "y": 20, "z": 30}, orientacion=ori)
    d2, b = _insertar("UPN-120", position={"x": 10, "y": 20, "z": 30},
                      rotation=dict(zip("xyz", rot, strict=True)))
    assert _plana(d1.scene[a].matrix) == pytest.approx(_plana(d2.scene[b].matrix))
    assert d1.scene[a].anchors == d2.scene[b].anchors
    assert _plana(d1.scene[a].matrix) == pytest.approx(_plana(compose_place((10, 20, 30), rot)))


def test_sin_orientacion_la_rotacion_de_siempre():
    """Default None: la pose es la de `rotation` (un log viejo regenera igual)."""
    doc, fid = _insertar("ANG-50X5", rotation={"x": 0, "y": -90, "z": -90},
                         position={"x": 5, "y": 0, "z": 0})
    esperada = compose_place((5, 0, 0), (0, -90, -90))
    assert _plana(doc.scene[fid].matrix) == pytest.approx(_plana(esperada))
    # y el log reabre igual
    doc2 = Document.from_apolo_bytes(doc.to_apolo_bytes())
    assert _plana(doc2.scene[fid].matrix) == pytest.approx(_plana(doc.scene[fid].matrix))


@pytest.mark.parametrize("ref,ori,frag", [
    ("TUBO-2X2", {"largo": "x", "abre_hacia": "+y"}, "sólo vale para perfiles abiertos"),
    ("UPN-100", {"largo": "x", "canto": "z"}, "faltan: abre_hacia; no aplica: canto"),
    ("UPN-100", {"largo": "x", "abre_hacia": "-x"}, "perpendiculares"),
    ("IPE-100", {"largo": "z", "canto": "z"}, "perpendiculares"),
    ("ANG-50X5", {"alas": ["+x", "-x"]}, "perpendiculares"),
    ("ANG-50X5", {"alas": ["+x", "+y"], "largo": "y"}, "perpendicular a las dos alas"),
])
def test_orientacion_invalida(ref, ori, frag):
    doc = Document()
    with pytest.raises(DocumentError) as exc:
        doc.execute("insert_component", {"component": ref, "length": 500, "orientacion": ori})
    assert frag in str(exc.value)


def test_orientacion_excluye_rotation_y_claves_desconocidas():
    doc = Document()
    with pytest.raises(Exception) as exc:
        doc.execute("insert_component", {"component": "UPN-100", "rotation": {"x": 90},
                                         "orientacion": {"largo": "x", "abre_hacia": "+y"}})
    assert "se excluyen" in str(exc.value)
    with pytest.raises(Exception) as exc:
        doc.execute("insert_component", {"component": "UPN-100",
                                         "orientacion": {"largo": "x", "abre": "+y"}})
    assert "abre_hacia" in str(exc.value)  # «¿quisiste decir…?» de params estrictos


# --------------------------------------------------------- lint de asiento por las anclas
def _lint(doc, bbox=False):
    out = asiento_zona_plana_lint(doc.scene, CATALOG, bbox=bbox)
    return out[0]["detalle"] if out else None


def _upn_taladrado(e, length=1000, **extra):
    """UPN-100 sin girar (alma en −X, h en Y) con Ø13.5 por el alma a `e` del canto superior."""
    doc, fid = _insertar("UPN-100", length=length, name="Larguero (+Y)")
    doc.execute("drill_hole", {"feature": fid, "axis": "x", "diameter": 13.5, "depth": 0,
                               "position": {"x": -30, "y": 50 - e, "z": 0}, **extra})
    return doc, fid


@pytest.mark.parametrize("e", [20, 26, 30])
def test_anclas_y_bbox_dicen_lo_mismo(e):
    """En pose recta el marco de las anclas y el del bbox (F2) dan el MISMO veredicto."""
    doc, _ = _upn_taladrado(e)
    assert _lint(doc) == _lint(doc, bbox=True)
    assert (_lint(doc) is not None) is (e == 20)


def test_recorte_ambiguo_se_lee_por_las_anclas():
    """UPN-100 de 100 mm de largo: h y L miden igual y el bbox no los distingue (F2 lo
    saltaba); las anclas sí."""
    doc, _ = _upn_taladrado(20, length=100)
    assert _lint(doc, bbox=True) is None
    assert "a 20.0 mm del canto del ala; mínimo 24.6" in _lint(doc)


@pytest.mark.parametrize("e,avisa", [(20, True), (30, False)])
def test_perfil_inclinado_se_lee_por_las_anclas(e, avisa):
    """Larguero inclinado 30° (una faja inclinada): el bbox no sirve, las anclas sí."""
    doc, fid = _upn_taladrado(e)
    doc.execute("transform", {"feature": fid, "rotate": {"x": 0, "y": 0, "z": 30}})
    assert _lint(doc, bbox=True) is None
    r = _lint(doc)
    assert (r is not None) is avisa
    if avisa:
        assert "a 20.0 mm del canto" in r


def test_angulo_orientado_por_anclas():
    """ANG-50X5 orientado con alas [+z, −y]: Ø9 por el ala vertical a 14 mm del talón."""
    doc, fid = _insertar("ANG-50X5", length=500, orientacion={"alas": ["+z", "-y"]})
    talon = doc.scene[fid].anchors["talon"]["origin"]  # (·, 25, −25)
    for e, frag in ((14, "a 14.0 mm del talón; mínimo 16.5"), (25, None)):
        d = Document.from_apolo_bytes(doc.to_apolo_bytes())
        d.execute("drill_hole", {"feature": fid, "axis": "y", "diameter": 9, "depth": 0,
                                 "position": {"x": 0, "y": talon[1] - 10, "z": talon[2] + e}})
        r = _lint(d)
        assert (r is None) if frag is None else (frag in r)
        assert r == _lint(d, bbox=True)


def test_espejo_sin_anclas_cae_al_bbox():
    """Una copia por espejo no hereda anclas: se lee por el bbox, como en F2."""
    doc, fid = _upn_taladrado(20)
    copia = doc.execute("mirror_feature", {"feature": fid, "plane": "yz", "offset": 200})
    assert not doc.scene[copia].anchors
    doc.scene[fid].visible = False
    assert "a 20.0 mm del canto" in _lint(doc)
