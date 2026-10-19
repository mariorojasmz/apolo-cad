"""Lint pre-entrega «asiento fuera de la zona plana» (plan perfiles-con-acuerdo, F2/D2): un
taladro en el alma de un UPN/IPE o en el ala de un ángulo cuyo asiento pisa el acuerdo r1 del
perfil real → AVISO (AMARILLO en la puerta de entrega), aunque el modelo prismático lo dé por
bueno."""

from apolo.doc import Document
from apolo.library.delivery import AMARILLO, delivery_report
from apolo.library.lints import predelivery_lints

REGLA = "pre-entrega · asiento fuera de la zona plana"


def _asiento(doc):
    checks = predelivery_lints(doc.scene, doc.commands, doc.fasteners, doc.grounds,
                               doc.joints, doc.mates)
    return next((c for c in checks if c["regla"] == REGLA), None)


def _perfil(doc, ref, length=1000, rotation=None, name=""):
    params = {"component": ref, "length": length, "name": name}
    if rotation:
        params["rotation"] = rotation
    fid = doc.execute("insert_component", params)
    bb = doc.scene[fid].shape.bounding_box()
    return fid, bb


def _upn100_taladrado(e, entrada=-5, **extra):
    """UPN-100 de 1 m (alma en el lado −X, h en Y) con un taladro por el alma a `e` mm del
    canto superior del ala."""
    doc = Document()
    fid, bb = _perfil(doc, "UPN-100", name="Larguero (+Y)")
    hole = {"feature": fid, "position": {"x": bb.min.X + entrada, "y": bb.max.Y - e, "z": 0},
            "axis": "x", "diameter": 13.5, "depth": 0}
    hole.update(extra)
    doc.execute("drill_hole", hole)
    return doc, fid, bb


def test_upn100_a_20mm_avisa():
    """El caso de la piloto: zona plana desde 17.9 + radio 6.75 → mínimo 24.6 > 20."""
    doc, _, _ = _upn100_taladrado(20)
    r = _asiento(doc)
    assert r is not None and r["estado"] == "aviso"
    d = r["detalle"]
    assert "Larguero (+Y)" in d and "UPN-100" in d  # nombra la pieza
    assert "Ø13.5" in d                              # el taladro
    assert "a 20.0 mm del canto" in d                # la distancia
    assert "mínimo 24.6" in d                        # la mínima


def test_upn100_a_30mm_no_avisa():
    doc, _, _ = _upn100_taladrado(30)
    assert _asiento(doc) is None


def test_lado_inferior_tambien_cuenta():
    """La distancia es al canto MÁS CERCANO: a 20 mm del ala de abajo también avisa."""
    doc = Document()
    fid, bb = _perfil(doc, "UPN-100")
    doc.execute("drill_hole", {"feature": fid, "axis": "x", "diameter": 13.5, "depth": 0,
                               "position": {"x": bb.min.X - 5, "y": bb.min.Y + 20, "z": 0}})
    assert _asiento(doc) is not None


def test_perfil_girado_se_lee_por_su_seccion():
    """Larguero con h vertical (rotación 90° en X): la lectura sale del bbox, no de la pose."""
    doc = Document()
    fid, bb = _perfil(doc, "UPN-100", rotation={"x": 90})
    assert round(bb.max.Z - bb.min.Z) == 100  # h quedó en Z
    doc.execute("drill_hole", {"feature": fid, "axis": "x", "diameter": 13.5, "depth": 0,
                               "position": {"x": bb.min.X - 5, "y": 0, "z": bb.max.Z - 20}})
    assert _asiento(doc) is not None


def test_roscado_y_ciego_tambien_avisan():
    """El plan no los exime: lo que asienta sobre ellos pisa el mismo acuerdo."""
    doc, _, _ = _upn100_taladrado(20, thread="M12")
    assert _asiento(doc) is not None
    doc, _, _ = _upn100_taladrado(20, entrada=0, depth=3)  # ciego desde el dorso del alma
    assert _asiento(doc) is not None


def test_tuerca_coaxial_agranda_el_asiento():
    """Ø13.5 a 26 mm cabe (mínimo 24.6), pero la tuerca M12 (entrecaras 19) que asienta en la
    cara interior del alma pide 17.9 + 9.5 = 27.4 → aviso que nombra el herraje."""
    doc, _, bb = _upn100_taladrado(26)
    assert _asiento(doc) is None
    web_in = bb.min.X + 6  # cara interior del alma (tw = 6)
    doc.execute("create_box", {"name": "Tuerca M12", "width": 10, "depth": 19, "height": 19,
                               "position": {"x": web_in + 5, "y": bb.max.Y - 26, "z": 0}})
    r = _asiento(doc)
    assert r is not None and "cabeza/tuerca/arandela" in r["detalle"]
    assert "mínimo 27.4" in r["detalle"]


def test_herraje_lejos_del_perfil_no_cuenta():
    """Un perno en el MISMO eje pero sobre otra pieza (a 200 mm) no asienta en el alma."""
    doc, _, bb = _upn100_taladrado(26)
    doc.execute("create_box", {"name": "Tuerca M12", "width": 10, "depth": 19, "height": 19,
                               "position": {"x": bb.min.X - 200, "y": bb.max.Y - 26, "z": 0}})
    assert _asiento(doc) is None


def test_ipe_alma():
    """IPE-100: zona plana desde tf + r = 12.7; Ø11 a 15 mm → aviso; a 25 → nada."""
    for e, avisa in ((15, True), (25, False)):
        doc = Document()
        fid, bb = _perfil(doc, "IPE-100")
        doc.execute("drill_hole", {"feature": fid, "axis": "x", "diameter": 11, "depth": 0,
                                   "position": {"x": bb.min.X - 5, "y": bb.max.Y - e, "z": 0}})
        assert (_asiento(doc) is not None) is avisa, e


def test_taladro_en_el_ala_del_upn_no_es_del_alma():
    """Un taladro vertical por el ala (eje ∥ h) no es asiento del alma: este lint no lo juzga."""
    doc = Document()
    fid, bb = _perfil(doc, "UPN-100")
    doc.execute("drill_hole", {"feature": fid, "axis": "-y", "diameter": 9, "depth": 0,
                               "position": {"x": bb.max.X - 15, "y": bb.max.Y + 5, "z": 0}})
    assert _asiento(doc) is None


def _angulo(e, length=500):
    """ANG-50X5 (talón en −X/−Y): taladro Ø9 por el ala vertical a `e` mm del talón."""
    doc = Document()
    fid, bb = _perfil(doc, "ANG-50X5", length=length, name="Ménsula")
    doc.execute("drill_hole", {"feature": fid, "axis": "x", "diameter": 9, "depth": 0,
                               "position": {"x": bb.min.X - 5, "y": bb.min.Y + e,
                                            "z": (bb.min.Z + bb.max.Z) / 2}})
    return _asiento(doc)


def test_angulo_ala():
    """Zona plana del ala: [t + r1, leg − r2] = [12, 46.5]; con radio 4.5 el eje va de 16.5
    a 42 del talón."""
    r = _angulo(14)
    assert r is not None and "a 14.0 mm del talón; mínimo 16.5" in r["detalle"]
    assert _angulo(25) is None
    r = _angulo(44)
    assert r is not None and "máximo 42.0" in r["detalle"]


def test_angulo_corto_igual_al_ala():
    """Un clip de 50 mm de ANG-50X5 (las tres cotas = 50): el largo se distingue por el
    centroide, no por la cota."""
    assert _angulo(14, length=50) is not None
    assert _angulo(25, length=50) is None


def test_perfil_cerrado_y_placa_nunca_avisan():
    doc = Document()
    fid, bb = _perfil(doc, "TUBO-2X2")
    doc.execute("drill_hole", {"feature": fid, "axis": "x", "diameter": 9, "depth": 0,
                               "position": {"x": bb.min.X - 5, "y": bb.max.Y - 6, "z": 0}})
    placa = doc.execute("create_box", {"name": "Placa", "width": 100, "depth": 100,
                                       "height": 10, "position": {"x": 500}})
    doc.execute("drill_hole", {"feature": placa, "axis": "-z", "diameter": 13.5, "depth": 0,
                               "position": {"x": 500 + 50 - 8, "y": 0, "z": 10}})
    assert _asiento(doc) is None


def test_perfil_sin_taladros_no_avisa():
    doc = Document()
    _perfil(doc, "UPN-100")
    assert _asiento(doc) is None


def test_puerta_de_entrega_amarillo():
    """El aviso llega a delivery_check como AMARILLO (no bloquea)."""
    doc, _, _ = _upn100_taladrado(20)
    rep = delivery_report(n_solidos=1, interferencias=[], soundness={"has_ground": True},
                          lints=[_asiento(doc)], integridad=[], suprimidos=[], poses=None)
    assert rep["veredicto"] == AMARILLO
    assert any(a["regla"] == REGLA for a in rep["avisos"])
