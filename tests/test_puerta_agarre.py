"""Puerta de publicación F2 — control de AGARRE de perno (plan puerta-de-publicacion D3, D9):
casos sanos y defectos SEMBRADOS sobre geometría real (join_bolted, pernos y tuercas de
catálogo, una C de chapa) y sobre insumos puros. También el sello del criterio 3 de join_bolted
(sin respaldo silencioso a 200 mm) y el reconocimiento de tornillería por nombre."""

import pytest

from apolo.commands.exec_union import CRITERIO_VIGENTE
from apolo.commands.registry import Feature
from apolo.doc import Document
from apolo.library import fijacion as fj
from apolo.library.calidad.agarre import controlar_agarre, evaluar_perno
from apolo.library.calidad.item import FALLA, NO_APLICA, OK, SIN_EVALUAR, aprobado
from apolo.library.catalog import CATALOG
from apolo.library.largos_perno import en_catalogo, en_serie, largos_catalogo
from apolo.library.lints import _is_bolt, es_nombre_de_tornilleria
from apolo.services.calidad_pernos import insumos_pernos


def _items(doc):
    return {i.id: i for i in controlar_agarre(insumos_pernos(doc))}


def _placas(doc, ta: float, tb: float, *, taladro_b: bool = False):
    """Placa A (abajo, z ∈ [0, ta]) y B encima; con `taladro_b`, B lleva un paso Ø11 en x=0."""
    a = doc.execute("create_box", {"name": "Placa A", "width": 120, "depth": 80, "height": ta,
                                   "position": {"z": ta / 2}})
    b = doc.execute("create_box", {"name": "Placa B", "width": 120, "depth": 80, "height": tb,
                                   "position": {"z": ta + tb / 2}})
    if taladro_b:
        doc.execute("drill_hole", {"feature": b, "position": {"z": ta + tb}, "axis": "-z",
                                   "diameter": 11})
    return a, b


def _perno(doc, z: float, **rot):
    """PERNO-HEX-M10 de catálogo (largo 50: el vástago baja desde la cara de asiento en z)."""
    return doc.execute("insert_component", {"component": "PERNO-HEX-M10",
                                            "position": {"z": z}, "rotation": rot})


# ── casos sanos ─────────────────────────────────────────────────────────────────────────


def test_join_bolted_pasa_los_tres_controles():
    doc = Document("ok")
    a, b = _placas(doc, 10, 8)
    cid = doc.execute("join_bolted", {"a": a, "b": b, "size": "M10", "count": 2})
    ins = insumos_pernos(doc)
    assert len(ins) == 2 and all(p["esperadas"] == [a, b] for p in ins)
    p = ins[0]
    # 18 de placas + 2 de la arandela DIN 125-A (bom-de-compra-fiel D5) + tuerca 8 + 2 hilos
    assert p["largo"] == pytest.approx(35) and p["d"] == 10 and p["cabeza"] == "hex"
    assert [t["rol"] for t in p["tramos"]] == ["pieza", "pieza", "pieza", "tuerca"]
    assert p["tramos"][2]["fid"] == f"{cid}_arandela1"
    items = _items(doc)
    assert {i.estado for i in items.values()} == {OK}, items
    assert items["agarre.retencion"].evidencia["evaluados"] == 2
    assert next(c for c in doc.commands if c["id"] == cid)["params"]["criterio"] == CRITERIO_VIGENTE == 6  # vigente (V8.9 F7b: agujeros previos)


def test_sin_tornilleria_no_aplica():
    doc = Document("vacio")
    _placas(doc, 10, 8)
    items = _items(doc)
    assert {i.estado for i in items.values()} == {NO_APLICA}
    assert not aprobado(items.values())


# ── defectos sembrados ──────────────────────────────────────────────────────────────────


def _c_con_eje(doc):
    """C de chapa (alas en y ∈ ±[47, 50]) con un bloque «roscado» entre las alas."""
    c = doc.execute("create_sheet_metal", {"name": "Soporte en C", "ancho": 100, "fondo": 100,
                                           "espesor": 3, "lados": ["frente", "atras"],
                                           "altura_pestana": 50})
    e = doc.execute("create_box", {"name": "Eje roscado", "width": 40, "depth": 50, "height": 30,
                                   "position": {"y": 5, "z": 25}})
    return c, e


def test_perno_que_entra_por_una_sola_aleta_falla():
    """El defecto del tensor de la faja publicada: el M10×50 cruza el ala +Y y engancha el eje
    roscado, pero la otra ala queda pasada la punta."""
    doc = Document("una-aleta")
    c, e = _c_con_eje(doc)
    doc.execute("insert_component", {"component": "PERNO-HEX-M10",
                                     "position": {"y": 50, "z": 25}, "rotation": {"x": -90}})
    (p,) = insumos_pernos(doc)
    assert [t["fid"] for t in p["tramos"]] == [c, e]
    assert any(m["fid"] == c for m in p["mas_alla"])
    r = evaluar_perno(p)
    assert r["retencion"][0] == OK  # engancha 15 mm en el eje roscado
    assert r["cruza"][0] == FALLA and "dos paredes" in r["cruza"][1]
    items = _items(doc)
    assert items["agarre.cruza"].estado == FALLA and items["agarre.cruza"].piezas
    assert not aprobado(items.values())


def test_tuerca_sin_hilo_fuera_falla_y_con_hilo_pasa():
    ok = Document("tuerca-ok")
    _placas(ok, 20, 10)
    _perno(ok, 30)
    ok.execute("insert_component", {"component": "TUERCA-M10", "position": {"z": -4}})
    r = evaluar_perno(insumos_pernos(ok)[0])
    assert r["retencion"][0] == OK and r["retencion"][2]["hilo_fuera_mm"] == pytest.approx(12)

    corto = Document("tuerca-corta")
    _placas(corto, 36, 10)
    _perno(corto, 46)
    corto.execute("insert_component", {"component": "TUERCA-M10", "position": {"z": -4}})
    r = evaluar_perno(insumos_pernos(corto)[0])
    assert r["retencion"][0] == FALLA and "no alcanza" in r["retencion"][1]
    assert _items(corto)["agarre.retencion"].estado == FALLA


@pytest.mark.parametrize(("espesor", "material", "estado"), [
    (12, None, OK),            # 12 ≥ 1·d en acero
    (12, "aluminio", FALLA),   # 12 < 1,5·d en aluminio
    (6, None, FALLA),          # agujero roscado corto en acero
])
def test_enganche_de_rosca_por_material(espesor, material, estado):
    doc = Document("rosca")
    a, b = _placas(doc, espesor, 8, taladro_b=True)
    if material:
        doc.set_material(a, material)
    _perno(doc, espesor + 8)
    (p,) = insumos_pernos(doc)
    r = evaluar_perno(p)
    assert r["retencion"][0] == estado, r["retencion"]
    assert r["retencion"][2]["enganche_mm"] == pytest.approx(espesor, abs=0.1)
    assert r["retencion"][2]["pieza_roscada"] == a


def _insumo(largo: float, **kw) -> dict:
    return {"fid": "p1", "nombre": "Perno", "ref": "PERNO-HEX-M10", "cabeza": "hex", "d": 10.0,
            "paso": 1.5, "largo": largo, "evaluable": True, "esperadas": [], "mas_alla": [],
            "tramos": [{"fid": "a", "nombre": "A", "t0": 0.0, "t1": 10.0, "rol": "pieza",
                        "material": "acero", "rosca": []},
                       {"fid": "n", "nombre": "Tuerca", "t0": 10.0, "t1": 18.0, "rol": "tuerca",
                        "material": "acero", "rosca": []}], **kw}


@pytest.mark.parametrize(("largo", "texto"), [
    (25, None), (27, "serie"), (160, "no está en el catálogo")])
def test_largo_de_la_serie_y_del_catalogo(largo, texto):
    e, txt, _ = evaluar_perno(_insumo(largo))["largo"]
    assert (e == OK) if texto is None else (e == FALLA and texto in txt), txt


def test_anclaje_de_expansion_va_por_su_ficha():
    """El anclaje de la placa de piso (F6 de plantilla-rodillos-cadena) mide 90 bajo la arandela
    y su ficha dice 115: no es un perno de la serie ISO, se compra por la ref (piloto de
    rodillos por gravedad v3: la puerta daba FALLA en union.largo_comercial)."""
    e, txt, _ = evaluar_perno(_insumo(90, ref="ANCLA-EXP-M12", d=12.0))["largo"]
    assert e == OK and "ANCLA-EXP-M12" in txt, txt


def test_largo_de_catalogo_por_ficha():
    assert en_serie(45) and not en_serie(47)
    assert largos_catalogo("PERNO-HEX-M10")[-1] == 150
    assert en_catalogo("DIN912-M8", 30) and not en_catalogo("DIN912-M8", 35)
    assert not en_catalogo("PERNO-HEX-M7", 30)  # sin ficha


def test_esperadas_que_no_cruza_y_no_evaluable():
    r = evaluar_perno(_insumo(25, esperadas=["a", "b"]))
    assert r["cruza"][0] == FALLA and "b" in r["cruza"][1]
    sin = evaluar_perno({"fid": "x", "evaluable": False, "motivo": "sin cabeza"})
    assert {v[0] for v in sin.values()} == {SIN_EVALUAR}


# ── el sello del criterio 3: sin respaldo silencioso a 200 mm ───────────────────────────


def _bloques(doc):
    a = doc.execute("create_box", {"name": "Bloque A", "width": 200, "depth": 100,
                                   "height": 100, "position": {"z": 50}})
    b = doc.execute("create_box", {"name": "Bloque B", "width": 200, "depth": 100,
                                   "height": 100, "position": {"z": 150}})
    return a, b


def test_join_bolted_nuevo_sin_largo_de_catalogo_da_error_accionable():
    assert CRITERIO_VIGENTE >= 3  # el 4 (F6: perfil abierto) conserva el largo estricto del 3
    doc = Document("sello")
    a, b = _bloques(doc)
    with pytest.raises(Exception) as exc:
        doc.execute("join_bolted", {"a": a, "b": b, "size": "M12", "count": 1})
    txt = str(exc.value)
    assert "216" in txt and "M12×200" in txt  # 200 + 2,5 de la arandela (D5) + 10 + 2 hilos
    with pytest.raises(ValueError):
        fj.largo_perno("M12", 200, estricto=True)
    assert fj.largo_perno("M12", 200) == 200  # criterio 2: el respaldo de siempre


def test_el_respaldo_de_200_de_un_log_viejo_regenera_y_la_puerta_lo_marca():
    doc = Document("legado-200")
    a, b = _bloques(doc)
    doc.execute("join_bolted", {"a": a, "b": b, "size": "M12", "count": 1, "criterio": 2})
    (p,) = insumos_pernos(doc)
    assert p["largo"] == pytest.approx(200)
    e, txt, _ = evaluar_perno(p)["retencion"]
    assert e == FALLA and "200 mm" in txt


# ── reconocimiento por nombre: un eje «roscado p/ perno» no es tornillería ─────────────


@pytest.mark.parametrize(("nombre", "es"), [
    ("Tensor de cola · Eje fijo Ø25 g6 (roscado p/ perno)", False),
    ("Eje fijo (roscado p/ perno)", False),
    ("Placa con agujero para perno M12", False),
    ("Tensor de cola · Perno tensor Allen PERNO-M16×90 (1)", True),
    ("Tornillería ménsula soporte motor", True),
    ("Juego de pernos M10", True),
    ("Tuerca M10 DIN 934", True),
])
def test_un_eje_que_nombra_su_perno_no_es_tornilleria(nombre, es):
    assert es_nombre_de_tornilleria(nombre) is es
    f = Feature("f", nombre, None, "c1")
    assert _is_bolt(f, CATALOG) is es


def test_el_eje_del_take_up_no_entra_como_perno():
    doc = Document("take-up")
    doc.execute("create_take_up", {})
    ids = {p["fid"] for p in insumos_pernos(doc)}
    assert ids == {"c1_perno1", "c1_perno2"}
