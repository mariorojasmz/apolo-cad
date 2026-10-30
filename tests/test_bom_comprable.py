"""Cada fila de la BOM alcanza para comprar o cortar la pieza, y una compra en varios sólidos es una
fila (plan hallazgos-del-revisor-en-la-puerta, F2: D4 y D5).

Los casos de máquinas reales (escalera de tijera, mesa plegable, mesa de bolas) leen el `.apolo`
final de un repo hermano del checkout (`<repos>/*/maquinas/<slug>/<slug>.apolo`), fuera del repo
público y sólo lectura: sin él, se saltan.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apolo.doc.document import Document
from apolo.library.bom import bom_from_scene
from apolo.library.bom_comprable import motivo
from apolo.library.bom_compra import norma_de_madera, norma_de_material
from apolo.library.calidad.comprable import bom_comprable
from apolo.library.calidad.item import FALLA, OK, SIN_EVALUAR
from apolo.library.calidad.registro import REGISTRO, VERSION_REGISTRO, Entrada
from apolo.library.costing import scene_costing
from apolo.library.cutlist import cut_list, hardware_schedule
from apolo.library.designacion_comercial import codigo_de_fabricante, se_pide_por_largo
from apolo.services.calidad_bom import insumo_bom

TESTIGOS = Path(__file__).parent / "data" / "testigos"


def _real(slug: str) -> Document:
    raiz = Path(__file__).resolve().parents[1]
    for anc in (raiz, *raiz.parents):
        hallados = sorted(anc.glob(f"*/maquinas/{slug}/{slug}.apolo"))
        if hallados:
            return Document.from_apolo_bytes(hallados[0].read_bytes())
    pytest.skip(f"sin el .apolo real de {slug} (fuera del repo)")


def _bom(doc: Document) -> list[dict]:
    return bom_from_scene(doc.scene, doc.default_material())


# ---------------------------------------------------------------- D4: el criterio por fila

@pytest.mark.parametrize("fila,falla", [
    # compra: norma, designación medida o código de fabricante
    ({"ref": "COMPRA", "descripcion": "Bola de transferencia Ø25,4", "norma": ""}, True),
    ({"ref": "COMPRA", "descripcion": "Perno M10x25 DIN 933", "norma": "DIN 933"}, False),
    ({"ref": "COMPRA", "descripcion": "Pie", "norma": "", "codigo": "Ganter GN 343.1"}, False),
    ({"ref": "COMPRA", "descripcion": "Banda", "norma": "", "designacion": "Banda sin fin…"},
     False),
    # la compra que se pide por largo, con su largo
    ({"ref": "COMPRA", "descripcion": "Varilla roscada M8 DIN 976-1", "norma": "DIN 976",
      "longitud_mm": None}, True),
    ({"ref": "COMPRA", "descripcion": "Varilla roscada M8 DIN 976-1", "norma": "DIN 976",
      "longitud_mm": 482.0}, False),
    # a medida: metal y madera con norma; caucho, lona o cable, no
    ({"ref": "A-MEDIDA", "material": "acero zincado", "norma": "", "longitud_mm": 25}, True),
    ({"ref": "A-MEDIDA", "material": "acero", "norma": "ASTM A36", "longitud_mm": 25}, False),
    ({"ref": "A-MEDIDA", "material": "madera de pino", "norma": "", "longitud_mm": 400}, True),
    ({"ref": "A-MEDIDA", "material": "madera pino C16 (EN 338)", "norma": "EN 338 C16",
      "longitud_mm": 400}, False),
    ({"ref": "A-MEDIDA", "material": "caucho", "norma": "", "longitud_mm": 90}, False),
    ({"ref": "A-MEDIDA", "material": "lona poliéster (densidad asimilada a madera)", "norma": "",
      "longitud_mm": 560}, False),
    ({"ref": "A-MEDIDA", "material": "cable", "norma": "", "longitud_mm": None}, False),
    ({"ref": "A-MEDIDA", "material": "acero", "norma": "ASTM A36", "longitud_mm": 300,
      "espesor_mm": 2}, True),  # chapa sin desarrollo
    # catálogo: la ref es el código; la cortable, con su largo
    ({"ref": "PIE-M12-50", "longitud_mm": None}, False),
    ({"ref": "TUBO-2X2", "longitud_mm": None}, True),
    ({"ref": "TUBO-2X2", "longitud_mm": 658.0}, False),
])
def test_d4_el_criterio_de_cada_fila(fila, falla):
    assert bool(motivo(fila)) is falla, motivo(fila)


@pytest.mark.parametrize("nombre,codigo", [
    ("Pie nivelador M16x50 carga ≥1000 kg tipo Ganter GN 343.1 o eq.", "Ganter GN 343.1"),
    ("Pie nivelador (compra, Ganter GN 343.1)", "Ganter GN 343.1"),
    ("Pie nivelador (compra, ref. 34312)", "34312"),
    # sin la marca de compra, un paréntesis no es un código; una sigla de norma no es una marca
    ("Taco (Tornillo 4x40)", ""), ("Pie (compra, AISI 304)", ""), ("Piñón tipo B", ""),
    ("Bola de transferencia Ø25,4 esp. M8x15 cap. min. 25 kg", ""),
])
def test_d4_el_codigo_de_fabricante_declarado(nombre, codigo):
    assert codigo_de_fabricante(nombre) == codigo


@pytest.mark.parametrize("material,norma", [
    ("madera pino radiata cepillado, seco 12 %, clase C16 (EN 338)", "EN 338 C16"),
    ("madera: triplay de pino 18 mm, encolado exterior (EN 636-2)", "EN 636-2"),
    ("madera HDF EN 622-5", "EN 622-5"), ("pino radiata C24", "EN 338 C24"),
    ("madera laminada GL24h", "EN 14080 GL24h"),
    # sin norma: nada (ni «seca en 12 %», ni el «D10» de un tarugo)
    ("madera de pino", ""), ("madera de haya (tarugo D10)", ""), ("madera seca en 12 %", ""),
])
def test_d4_la_bom_lee_la_norma_que_escribe_la_madera(material, norma):
    assert norma_de_madera(material) == norma
    assert norma_de_material(material, "Larguero", "barra") == norma


def test_d4_la_varilla_de_compra_sale_con_su_largo_medido():
    d = Document("varilla")
    for i in range(2):
        d.execute("create_cylinder", {"name": f"Varilla roscada M8 DIN 976-1 ({i + 1})",
                                      "radius": 4, "height": 482, "axis": "y",
                                      "position": {"x": 100 * i}})
    d.execute("create_cylinder", {"name": "Varilla roscada M8 DIN 976-1", "radius": 4,
                                  "height": 300, "axis": "y", "position": {"x": 400}})
    filas = [r for r in _bom(d) if r["descripcion"].startswith("Varilla")]
    assert sorted((r["longitud_mm"], r["cantidad"]) for r in filas) == [(300.0, 1), (482.0, 2)]
    assert all(motivo(r) is None for r in filas)
    assert se_pide_por_largo("Varilla roscada M8 DIN 976-1") and not se_pide_por_largo("Perno M8")


def test_d4_la_banda_sin_fin_de_la_faja_lleva_su_designacion():
    d = Document.from_apolo_bytes((TESTIGOS / "faja.apolo").read_bytes())
    (banda,) = [r for r in _bom(d) if r["categoria"] == "bandas"]
    assert banda["descripcion"] == "Faja de banda · Banda"  # la fila de siempre
    assert banda["designacion"].startswith("Banda sin fin de PVC, ancho 600 mm")
    assert f"lazo {banda['longitud_mm']:g} mm" in banda["designacion"]
    assert motivo(banda) is None


# ---------------------------------------------------------------- D5: una compra, una fila

def _bisagras(d: Document, n: int, join_bolted: bool = False) -> list[str]:
    """`n` bisagras de compra de dos medias hojas de catálogo, cada una su grupo «(compra)»."""
    hojas = []
    for i in range(n):
        a = d.execute("insert_component", {"component": "BIS-H-100-A", "name": f"Hoja A ({i})",
                                           "position": {"x": 200 * i}})
        b = d.execute("insert_component", {"component": "BIS-H-100-B", "name": f"Hoja B ({i})",
                                           "position": {"x": 200 * i}})
        d.execute("create_group", {"name": f"Bisagra de pala 100 (compra) ({i + 1})",
                                   "members": [a, b]})
        hojas += [a, b]
    return hojas


def test_d5_un_grupo_de_compra_es_una_fila_en_bom_costeo_cedula_y_no_en_el_corte():
    d = Document("bisagras")
    _bisagras(d, 3)
    d.execute("create_box", {"name": "Panel", "width": 600, "depth": 300, "height": 18,
                             "position": {"z": -20}})
    filas = _bom(d)
    (g,) = [r for r in filas if r.get("grupos_compra")]
    assert (g["ref"], g["descripcion"], g["cantidad"], g["norma"]) == (
        "COMPRA", "Bisagra de pala 100", 3, "EN 1935")  # la norma común de sus hojas
    assert g["categoria"] == "bisagras" and len(g["incluye"]) == 2
    assert g["peso_unitario_kg"] == pytest.approx(0.24) and motivo(g) is None
    assert not [r for r in filas if r["ref"].startswith("BIS-H")]  # las hojas no salen sueltas
    costeo = scene_costing(d.scene, d.default_material())["rows"]
    assert [r["cantidad"] for r in costeo if r.get("grupos_compra")] == [3]
    assert not [r for r in costeo if r["ref"].startswith("BIS-H")]
    ced = hardware_schedule(d.scene)
    assert [(r["nombre"], r["cantidad"]) for r in ced] == [("Bisagra de pala 100", 3)]
    assert [r["nombre"] for r in cut_list(d.scene)] == ["Panel"]


def test_d5_sin_la_marca_de_compra_el_grupo_no_cambia_nada():
    d = Document("bisagras sueltas")
    a = d.execute("insert_component", {"component": "BIS-H-100-A", "name": "Hoja A"})
    b = d.execute("insert_component", {"component": "BIS-H-100-B", "name": "Hoja B"})
    d.execute("create_group", {"name": "Bisagras", "members": [a, b]})
    assert sorted(r["ref"] for r in _bom(d)) == ["BIS-H-100-A", "BIS-H-100-B"]


def test_d5_un_grupo_taladrado_por_join_bolted_hacia_fuera_falla():
    d = Document("placa comprada")
    p = d.execute("create_box", {"name": "Placa (compra, Ganter GN 1)", "width": 120,
                                 "depth": 80, "height": 8, "position": {"z": 14}})
    base = d.execute("create_box", {"name": "Base", "width": 120, "depth": 80, "height": 10,
                                    "position": {"z": 5}})
    d.execute("create_group", {"name": "Soporte tipo Ganter GN 2 (compra)", "members": [p]})
    ins = insumo_bom(d)
    assert ins["grupos_compra"] == 1 and not ins["grupos_invalidos"]
    d.execute("join_bolted", {"a": p, "b": base, "size": "M8", "count": 2})
    ins = insumo_bom(d)
    (g,) = ins["grupos_invalidos"]
    assert g["grupo"] == "Soporte tipo Ganter GN 2 (compra)" and g["piezas"] == [p]
    r = bom_comprable({"bom": ins})
    assert r["estado"] == FALLA and p in r["piezas"] and "join_bolted" in r["detalle"]


# ---------------------------------------------------------------- el ítem

def test_el_item_esta_en_el_registro_con_su_version():
    assert VERSION_REGISTRO == "28"
    (e,) = [e for e in REGISTRO if isinstance(e, Entrada) and e.id == "bom.comprable"]
    assert e.familia == "proceso"


def test_el_item_falla_nombra_la_pieza_y_sin_insumo_no_aprueba():
    ins = {"filas": 3, "grupos_compra": 0, "grupos_invalidos": [], "incompletas": [
        {"pieza": "c7", "descripcion": "Bola", "ref": "COMPRA", "cantidad": 100,
         "motivo": "compra sin norma"}]}
    r = bom_comprable({"bom": ins})
    assert r["estado"] == FALLA and r["piezas"] == ["c7"] and "«Bola»" in r["detalle"]
    assert bom_comprable({"bom": {**ins, "incompletas": []}})["estado"] == OK
    assert bom_comprable({})["estado"] == SIN_EVALUAR
    assert bom_comprable({"bom": {"error": "x"}})["estado"] == SIN_EVALUAR


@pytest.mark.parametrize("testigo", ["faja", "mensula", "mensula_atornillada", "rodillos"])
def test_los_testigos_tienen_una_bom_que_compra(testigo):
    d = Document.from_apolo_bytes((TESTIGOS / f"{testigo}.apolo").read_bytes())
    ins = insumo_bom(d)
    assert ins["incompletas"] == [] and ins["grupos_invalidos"] == []


# ---------------------------------------------------------------- máquinas reales

def test_real_la_varilla_de_la_escalera_sale_con_482_mm():
    d = _real("escalera-tijera-3")
    (v,) = [r for r in _bom(d) if r["descripcion"].startswith("Varilla roscada")]
    assert (v["longitud_mm"], v["cantidad"], v["norma"]) == (482.0, 6, "DIN 976")
    assert motivo(v) is None


def test_real_la_bisagra_de_la_mesa_plegable_es_una_fila_de_cuatro():
    d = _real("mesa-plegable-madera-1200")
    antes = [r for r in _bom(d) if r["ref"].startswith("BIS-H")]
    assert sum(r["cantidad"] for r in antes) == 8  # 4 + 4 medias bisagras
    hojas = ["c49", "c50", "c51", "c52", "c53", "c54", "c55", "c56"]
    grupo = next(c for c in d.commands if c["type"] == "create_group"
                 and c["params"]["name"] == "Bisagras")
    resto = [m for m in grupo["params"]["members"] if m not in hojas]
    d.edit(grupo["id"], {"members": resto}, merge=True)
    for i in range(4):
        d.execute("create_group", {"name": f"Bisagra de pala 100 (compra) ({i + 1})",
                                   "members": hojas[2 * i:2 * i + 2], "parent": "Bisagras"})
    filas = _bom(d)
    assert not [r for r in filas if r["ref"].startswith("BIS-H")]
    (g,) = [r for r in filas if r.get("grupos_compra")]
    assert (g["cantidad"], g["norma"]) == (4, "EN 1935") and motivo(g) is None


def test_real_la_bola_de_la_mesa_de_bolas_falla_hasta_tener_designacion():
    d = _real("mesa-bolas-600")
    falla = {m["descripcion"] for m in insumo_bom(d)["incompletas"]}
    assert any(x.startswith("Bola de transferencia") for x in falla)
    for c in d.commands:
        nombre = (c.get("params") or {}).get("name") or ""
        if nombre.startswith("Bola de transferencia"):
            c["params"]["name"] = nombre + " tipo Alwayse 9020-08"
    d.regenerate()
    falla = {m["descripcion"] for m in insumo_bom(d)["incompletas"]}
    assert not any(x.startswith("Bola de transferencia") for x in falla)
