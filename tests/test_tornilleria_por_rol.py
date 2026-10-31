"""Tornillería por ROL e IMPRONTA (plan puerta-fuera-de-catalogo F2: D3, D4 y D5). Los casos son
los de la F0 (reporte en la Bitácora del plan): el tornillo de madera de la estantería medido
como PERNO-M3, la tuerca martillo de la estructura de paneles sin evaluar, el espárrago de un pie
nivelador, el «Eje» que no gira, la «Correa» de un techo y la arandela DIN 9021 con la norma tras
el complemento."""

from types import SimpleNamespace as N

import pytest

from apolo.doc import Document
from apolo.library.acceso_herramienta import tool_access_report
from apolo.library.calidad.agarre import controlar_agarre
from apolo.library.calidad.item import OK, SIN_EVALUAR
from apolo.library.calidad.puerta import acceso_herramienta
from apolo.library.calidad.registro import VERSION_REGISTRO
from apolo.library.catalog import CATALOG
from apolo.library.designacion_comercial import designacion, norma_del_nombre
from apolo.library.largos_perno import largos_catalogo, ref_para
from apolo.library.lints import _is_bolt
from apolo.library.seguridad.modelo import Pieza, clase_flexible
from apolo.library.seguridad.peligros import giratorias
from apolo.services.calidad_pernos import insumos_pernos, tipo_de_tornilleria
from apolo.services.roles import rol_union

TX_3X30 = "Tornillo para madera EN 14592 avellanado TX 3x30 (compra)"
#: el sólido del tornillo de la estantería de la F0 (c462): borde + cabeza cónica + cuerpo + punta,
#: con la cara de arriba de la cabeza en z = 0
_CODIGO = """d={d}; L={L}; dk={dk}; off=0.0
hk=(dk-d)/2
borde = Pos(0,0,off) * Cylinder(dk/2, 0.4, align=(Align.CENTER, Align.CENTER, Align.MAX))
cab = Pos(0,0,off-0.4) * Cone(d/2, dk/2, hk-0.4, align=(Align.CENTER, Align.CENTER, Align.MAX))
cuerpo = Pos(0,0,off-hk) * Cylinder(d/2, L-hk-2, align=(Align.CENTER, Align.CENTER, Align.MAX))
punta = Pos(0,0,off-(L-2)) * Cone(0.3, d/2, 2, align=(Align.CENTER, Align.CENTER, Align.MAX))
result = borde + cab + cuerpo + punta
"""


def _feat(nombre: str, ref: str | None = None):
    return N(name=nombre, component=ref)


# ── D3: el tipo sale del rol ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("nombre, tipo, es_herraje", [
    (TX_3X30, "madera", True),
    ("Tirafondo 6x60 DIN 571", "madera", True),
    ("Tornillo autorroscante 4,2x19", "madera", True),
    ("Perno del tablero DIN 933 M6x30", "perno", True),           # el hexagonal de siempre
    ("Perno M8 con tuerca", "perno", True),                       # la tuerca no encabeza
    ("Tornillería ménsula soporte motor", "perno", True),         # la c704 del 38
    ("Espárrago M12x80", "esparrago", True),
    ("Tuerca martillo M8 ranura 8 inox e4 int. sur", None, True),
    ("Arandela ancha perno M6", None, False),                     # F0 modo 3: no es perno
    ("Taco de nylon S6 para tornillo 4,5", None, False),
    # el pie de la mesa inox de 2 m: «espárrago» dentro del paréntesis de compra
    ("Pie nivelador higiénico M10 (compra: cuerpo AISI 304, espárrago M10x60 A2-70, base Ø60)",
     None, False),
    ("Pie nivelador articulado M12x200 disco 90 antideslizante (compra, 500 kg) · UE: Ganter "
     "GN 343 / Elesa LV.A, código a confirmar", None, False),
])
def test_tipo_de_tornilleria_por_el_rol(nombre, tipo, es_herraje):
    assert tipo_de_tornilleria(_feat(nombre), CATALOG) == tipo
    assert _is_bolt(_feat(nombre), CATALOG) is es_herraje


def test_el_pie_nivelador_es_un_apoyo_de_la_instalacion():
    """`installation_data` saltaba los 4 pies de la mesa inox por `_is_bolt` (apoyo.capacidad
    NO_APLICA y sin lámina de instalación)."""
    from apolo.services.installation_data import installation_data

    doc = Document("pies")
    nombre = "Pie nivelador higiénico M10 (compra: cuerpo AISI 304, espárrago M10x60 A2-70)"
    for k, (x, y) in enumerate(((0, 0), (800, 0), (0, 600), (800, 600))):
        f = doc.execute("create_box", {"name": f"{nombre} {k}", "width": 60, "depth": 60,
                                       "height": 80, "position": {"x": x, "y": y, "z": 40}})
        doc.execute("ground", {"name": f"piso_{k}", "feature": f})
    datos, _ = installation_data(doc)
    assert datos["anclaje"]["n_apoyos"] == 4


def test_la_norma_tras_un_complemento_de_lugar_designa_la_compra():
    n = "Arandela ancha del tablero DIN 9021 M6 6,4x18x1,6"
    assert norma_del_nombre(n) == "DIN 9021"
    assert designacion(n) == "Arandela ancha DIN 9021 M6 6,4x18x1,6"
    # un paréntesis o un «con» nombran OTRA pieza: la norma no es de ésta
    assert norma_del_nombre("Eje fijo del rodillo Ø17 h6 (topes axiales con anillos DIN 471)") == ""
    assert norma_del_nombre("Arandela del soporte (con perno DIN 933 M8)") == ""
    assert norma_del_nombre("Perno M10x25 DIN 933 del tensado") == "DIN 933"  # como siempre


def _pieza(i, nombre, **kw):
    rol, _ = rol_union(nombre, kw.pop("categoria", None))
    return Pieza(i, nombre, rol=rol, **kw)


def test_un_eje_que_no_gira_no_es_parte_movil():
    """La barra portarrollos de la mesa soldada se llamaba «Eje» y apoyaba en dos ménsulas."""
    piezas = {"e": _pieza("e", "Eje portarrollos"), "m1": _pieza("m1", "Ménsula delantera"),
              "m2": _pieza("m2", "Ménsula trasera")}
    uniones = [{"a": "e", "b": "m1", "kind": "contacto"}, {"a": "e", "b": "m2", "kind": "contacto"}]
    assert giratorias(piezas, [], uniones) == set()
    # el mismo eje en dos chumaceras sí gira
    piezas |= {"c1": _pieza("c1", "Chumacera UCP205 lado motor")}
    assert "e" in giratorias(piezas, [], uniones + [{"a": "e", "b": "c1", "kind": "contacto"}])


def test_la_correa_de_un_techo_no_es_transmision():
    assert rol_union("Correa delantera existente")[0] == "estructura"
    assert rol_union("Correa de techo C100x50")[0] == "estructura"
    assert rol_union("Correa en V A-42")[0] == "flexible"  # la de transmisión, como siempre
    correa = Pieza("c", "Correa trasera", rol="flexible", anclada=True)
    assert clase_flexible(correa) is None
    assert clase_flexible(Pieza("v", "Correa en V A-42", rol="flexible")) == "transmision"


# ── D5: la familia EN 14592 ──────────────────────────────────────────────────────────────


def test_familia_en14592_con_su_serie_y_su_ficha():
    for h in ("TX", "PZ"):
        for d in ("3", "3.5", "4", "4.5", "5", "6"):
            c = CATALOG[f"TORNILLO-MADERA-{h}-{d}"]
            s = c.specs
            assert s["norma"] == "EN 14592" and s["huella"] == h and s["rho_a_kg_m3"] == 350
            assert s["f_ax_k_mpa"] == (12.0 if d == "6" else 14.0)
            assert largos_catalogo(c.ref) == [float(x) for x in s["largos_mm"]]
    assert 75.0 not in largos_catalogo("TORNILLO-MADERA-TX-4")          # de 5 en 5 sin 75
    assert largos_catalogo("TORNILLO-MADERA-TX-3")[0] == 15.0
    # los 4 tirafondos de siempre, con su norma y huella (ids estables)
    for ref in ("TIRAFONDO-3x16", "TIRAFONDO-4x40", "TIRAFONDO-45x50", "TIRAFONDO-5x60"):
        assert CATALOG[ref].specs["norma"] == "DIN 7997" and CATALOG[ref].specs["huella"] == "PZ"
    assert ref_para(3.0, "avellanada", madera=True, huella="TX") == "TORNILLO-MADERA-TX-3"
    assert ref_para(4.5, "avellanada", madera=True, huella="PZ") == "TORNILLO-MADERA-PZ-4.5"
    assert ref_para(8.0, "hex", madera=True) == "TIRAFONDO-HEX-8"
    assert ref_para(3.0, "allen") == "PERNO-M3"  # el perno, como siempre


def test_el_tornillo_de_la_familia_se_inserta_por_su_largo_total():
    from apolo.commands.registry import CommandError
    from apolo.doc.errors import DocumentError

    doc = Document("familia")
    f = doc.execute("insert_component", {"component": "TORNILLO-MADERA-TX-4", "length": 45})
    bb = doc.scene[f].shape.bounding_box()
    assert bb.max.Z - bb.min.Z == pytest.approx(45.0, abs=0.05)  # la cabeza incluida
    assert doc.scene[f].cut_length == 45.0
    with pytest.raises((CommandError, DocumentError), match="no es un largo que se compre"):
        doc.execute("insert_component", {"component": "TORNILLO-MADERA-TX-4", "length": 75})


# ── el tornillo de madera a medida, medido como madera ───────────────────────────────────


def _estante(nombre=TX_3X30, L=30.0, d=3.0, dk=6.0, obstaculo=None):
    """Entrepaño 12 mm sobre un larguero 40 mm (madera) y un tornillo a medida con la cabeza a ras
    del entrepaño (z = 52)."""
    doc = Document("estante")
    larg = doc.execute("create_box", {"name": "Larguero", "width": 200, "depth": 19,
                                      "height": 40, "position": {"z": 20}})
    tab = doc.execute("create_box", {"name": "Entrepaño", "width": 200, "depth": 100,
                                     "height": 12, "position": {"z": 46}})
    for f in (larg, tab):
        doc.set_material(f, "madera")
    t = doc.execute("run_script", {"name": nombre, "code": _CODIGO.format(d=d, L=L, dk=dk),
                                   "position": {"x": 0, "y": 0, "z": 52}})
    if obstaculo is not None:
        doc.execute("create_box", {"name": "Travesaño superior", **obstaculo})
    return doc, t


def test_el_tornillo_de_madera_a_medida_tiene_el_largo_de_su_serie():
    doc, t = _estante()
    (p,) = [x for x in insumos_pernos(doc) if x["fid"] == t]
    assert p["madera_screw"] and p["cabeza"] == "avellanada" and p["huella"] == "TX"
    assert p["largo"] == pytest.approx(30.0, abs=0.05) and p["d"] == pytest.approx(3.0)
    items = {i.id: i for i in controlar_agarre([p])}
    assert items["agarre.largo"].estado == OK
    # retención del avellanado: ≥ 6·d de rosca del lado de la punta (EN 1995-1-1 § 8.7.2(3))
    assert items["agarre.retencion"].estado == OK
    # fuera de su serie falla nombrando la ficha de SU tipo, no PERNO-M3
    doc2, t2 = _estante(nombre="Tornillo para madera EN 14592 avellanado TX 3x29", L=29.0)
    (p2,) = [x for x in insumos_pernos(doc2) if x["fid"] == t2]
    caso = controlar_agarre([p2])[2].evidencia["casos"][0]
    assert caso["ref"] == "TORNILLO-MADERA-TX-3" and "PERNO" not in caso["detalle"]


# ── D4: el acceso por la impronta y por su perno ────────────────────────────────────────


def test_el_torx_se_evalua_por_su_impronta():
    doc, t = _estante()
    rep = tool_access_report(doc.scene, catalog=CATALOG)
    assert rep["no_evaluados"] == [] and rep["por_impronta"] == 1 and rep["ok"] == 1
    # una pared a 15 mm del eje tapa la mano del destornillador corto, no la hoja larga
    doc, t = _estante(obstaculo={"width": 10, "depth": 60, "height": 58,
                                 "position": {"x": 20, "z": 52 + 2 + 29}})
    rep = tool_access_report(doc.scene, catalog=CATALOG)
    assert rep["ok"] == 1 and rep["sin_herramienta"] == []
    # encima del tornillo, a 20 mm: ningún destornillador entra
    doc, t = _estante(obstaculo={"width": 80, "depth": 80, "height": 10,
                                 "position": {"z": 52 + 25}})
    rep = tool_access_report(doc.scene, catalog=CATALOG)
    (malo,) = rep["sin_herramienta"]
    assert malo["id"] == t and malo["tipo"] == "TX" and malo["bloquean"] == ["Travesaño superior"]
    assert acceso_herramienta({"acceso": rep})["estado"] == "FALLA"


def test_el_pz_de_catalogo_se_evalua_por_su_ficha():
    doc = Document("pz")
    tab = doc.execute("create_box", {"name": "Tablero", "width": 200, "depth": 100, "height": 18,
                                     "position": {"z": 9}})
    doc.set_material(tab, "madera")
    doc.execute("insert_component", {"component": "TORNILLO-MADERA-PZ-4", "length": 40,
                                     "position": {"z": 18}})  # origen = cara de la cabeza
    rep = tool_access_report(doc.scene, catalog=CATALOG)
    assert rep["por_impronta"] == 1 and rep["ok"] == 1 and rep["no_evaluados"] == []


def _paneles(con_perno: bool):
    doc = Document("paneles")
    riel = doc.execute("create_box", {"name": "Riel", "width": 200, "depth": 40, "height": 40,
                                      "position": {"z": 20}})
    tuerca = doc.execute("create_box", {"name": "Tuerca martillo M8 ranura 8 inox e4 int. sur",
                                        "width": 16, "depth": 10, "height": 6,
                                        "position": {"z": 30}})
    if con_perno:
        doc.execute("insert_component", {"component": "PERNO-HEX-M8", "length": 25,
                                         "position": {"z": 50}})
    return doc, riel, tuerca


def test_la_tuerca_martillo_se_evalua_por_su_perno():
    doc, _riel, tuerca = _paneles(con_perno=True)
    rep = tool_access_report(doc.scene, catalog=CATALOG)
    assert rep.get("por_su_perno") == 1
    assert all(e["id"] != tuerca for e in rep["no_evaluados"])


def test_lo_que_sigue_sin_evaluar_se_justifica_con_la_herramienta():
    doc, _riel, tuerca = _paneles(con_perno=False)
    rep = tool_access_report(doc.scene, catalog=CATALOG)
    assert [e["id"] for e in rep["no_evaluados"]] == [tuerca]
    assert acceso_herramienta({"acceso": rep})["estado"] == SIN_EVALUAR
    vago = [{"regla": "union.acceso_herramienta", "pieza": tuerca,
             "porque": "no aplica en esta máquina, se revisó"}]
    assert acceso_herramienta({"acceso": rep, "justificadas": vago})["estado"] == SIN_EVALUAR
    con = [{"regla": "union.acceso_herramienta", "pieza": tuerca,
            "porque": "la aprieta la llave Allen 6 del perno ISO 4762 desde la cara del panel"}]
    r = acceso_herramienta({"acceso": rep, "justificadas": con})
    assert r["estado"] == OK and r["evidencia"]["justificados"][0]["id"] == tuerca


def test_registro_v34():
    assert VERSION_REGISTRO == "36"
