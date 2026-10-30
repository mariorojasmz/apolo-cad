"""`create_roller_conveyor`: el anclaje al piso se elige por el espesor que fija (2026-10-29).

Un transportador de rodillos por gravedad necesitó 25 mm de calza bajo la base de los pies y el
anclaje de la plantilla (M12×115) sólo fija 20 mm: la ETA cuenta la calza o el mortero en tfix.
`calza_mm` declara ese espesor y `anclaje_ref` («auto» por defecto) toma el M12 más corto cuyo
tfix cubre base + calza, o valida el que se pida. Sin los campos, la plantilla de siempre.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from apolo.doc.errors import DocumentError
from apolo.commands.registry import REGISTRY
from apolo.doc import Document
from apolo.library.bom import bom_from_scene
from apolo.library.calidad.agarre import evaluar_perno
from apolo.library.calidad.item import OK
from apolo.library.catalog import CATALOG
from apolo.library.delivery import VERDE, delivery_report
from apolo.library.rodillos_cadena_pies import (
    ANCLAJE_REF,
    PLACA_PISO_T,
    anclajes,
    elegir_anclaje,
    familias,
)
from apolo.services.delivery_inputs import delivery_inputs
from banco_guardas import interferencias_sin_tope

LIBRE = {"largo": 1500, "ancho_util": 400, "paso": 75, "motriz": "libre"}
#: la plantilla ANTES de este cambio (código de 93e1d91): piezas, uniones y anclajes, y la suma
#: de volumen y de las 6 cotas de la caja de cada pieza
HUELLA = {"base": ((176, 212, "2e25259503a588a5"),
                   [10469859.28, 127349.36, -9527.6, 103850.38, 136650.64, 9527.6, 112421.42]),
          "disco": ((180, 216, "8ed34ff4fd67ae75"),
                    [12154585.42, 129949.36, -9927.6, 104060.38, 140050.64, 9927.6, 112631.42])}


def _doc(params: dict) -> Document:
    doc = Document("rodillos-anclaje")
    doc.execute("create_roller_conveyor", {"motor": "MOTOR-037", "mantenimiento": False, **params})
    return doc


@pytest.fixture(scope="module")
def calzado():
    return _doc({**LIBRE, "calza_mm": 25})


def _huella(doc) -> tuple:
    piezas = sorted([fid, f.name, f.component or ""] for fid, f in doc.scene.items())
    uniones = sorted([u["name"], u["kind"], u["a"], u["b"], u.get("nota", "")]
                     for u in doc.fasteners.values())
    ancl = sorted([g["feature"], g.get("nota", "")] for g in doc.grounds.values())
    s = json.dumps([piezas, uniones, ancl], ensure_ascii=False)
    return len(piezas), len(uniones), hashlib.sha256(s.encode()).hexdigest()[:16]


def _geom(doc) -> list[float]:
    v, c = 0.0, [0.0] * 6
    for f in doc.scene.values():
        b = f.shape.bounding_box()
        v += float(f.shape.volume)
        for i, x in enumerate((b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)):
            c[i] += x
    return [v, *c]


def _bom(doc) -> dict:
    return {f["ref"]: f["cantidad"] for f in bom_from_scene(doc.scene, doc.default_material())}


# ------------------------------------------------------------------ la ficha (puro)
def test_los_anclajes_m12_son_una_familia_con_su_fuente():
    refs = anclajes()
    assert refs[0] == ANCLAJE_REF and len(refs) >= 3
    for r in refs:
        s = CATALOG[r].specs
        # el largo = lo que asoma + tfix + hef (la relación de la ficha HST3), mismo hef y agujero
        assert float(s["length"]) == float(s["sobre"]) + float(s["tfix_max"]) + float(s["hef"])
        assert (s["hef"], s["df"], s["par_instalacion_nm"]) == (70, 14, 60)
        assert r == ANCLAJE_REF or "ETA" in s["fuente"]
    # el agujero de la base de cada pie es el del anclaje
    assert {float(CATALOG[p].specs["agujero_d"]) for p in familias(True)} == {14.0}


def test_auto_sin_calza_es_el_anclaje_de_siempre():
    """Sin calza, lo que fija la plantilla (cada base de pie y la placa de piso) cabe en el
    M12×115: «auto» lo elige y un log viejo regenera igual. Un anclaje M12 MÁS CORTO en el
    catálogo cambiaría esto: sería otro default."""
    for e in [PLACA_PISO_T, *(float(CATALOG[p].specs["disco_t"]) for p in familias(True))]:
        assert elegir_anclaje(e) == ANCLAJE_REF


def test_elegir_por_el_espesor_que_fija():
    assert elegir_anclaje(39.0) == "ANCLA-EXP-M12-145"  # 14 de base + 25 de calza
    assert elegir_anclaje(30.0) == "ANCLA-EXP-M12-125"
    assert elegir_anclaje(14.0, "ANCLA-EXP-M12-165") == "ANCLA-EXP-M12-165"  # lo pedido, si cubre
    with pytest.raises(ValueError, match="fija hasta 20 mm.*ANCLA-EXP-M12-145"):
        elegir_anclaje(39.0, ANCLAJE_REF)
    with pytest.raises(ValueError, match="ningún anclaje"):
        elegir_anclaje(500.0)
    with pytest.raises(ValueError, match="usa auto"):
        elegir_anclaje(10.0, "PERNO-HEX-M12")


# ------------------------------------------------------------------ un log viejo regenera igual
@pytest.mark.parametrize("pie", ["base", "disco"])
def test_sin_los_campos_la_plantilla_de_siempre(pie):
    doc = _doc({**LIBRE, "pie": pie})
    assert "anclaje_ref" not in doc.commands[0]["params"]  # el sello no los pone
    assert "calza_mm" not in doc.commands[0]["params"]
    assert _huella(doc) == HUELLA[pie][0]
    v, *c = _geom(doc)
    assert v == pytest.approx(HUELLA[pie][1][0], rel=1e-6)
    assert c == pytest.approx(HUELLA[pie][1][1:], abs=0.5)
    spec = REGISTRY["create_roller_conveyor"]
    assert spec.version == 6  # el anclaje no la sube (v6 = la oreja del portamotor)
    props = spec.model.model_json_schema()["properties"]
    assert props["anclaje_ref"]["enum"] == ["auto", *anclajes()]


# ------------------------------------------------------------------ con calza
def test_con_calza_cada_anclaje_fija_base_mas_calza(calzado):
    anclas = sorted(f for f in calzado.scene if f.startswith("c1_ancla_"))
    pies = sorted(f for f in calzado.scene if f.startswith("c1_pie_"))
    assert anclas and len(anclas) == 2 * len(pies)
    bom = _bom(calzado)
    assert bom.get("ANCLA-EXP-M12-145") == len(anclas) and ANCLAJE_REF not in bom
    for f in anclas:
        feat = calzado.scene[f]
        assert feat.component == "ANCLA-EXP-M12-145"
        s = CATALOG[feat.component].specs
        pie = calzado.scene[f"c1_pie_{f.removeprefix('c1_ancla_')[:-1]}"]
        base_t = float(CATALOG[pie.component].specs["disco_t"])
        assert float(s["tfix_max"]) >= base_t + 25.0
        # asienta sobre la base y baja lo que pide su ficha (sobre, tfix y hef: al concreto)
        b = feat.shape.bounding_box()
        assert b.min.Z == pytest.approx(base_t - (float(s["length"]) - float(s["sobre"])), abs=0.01)
    notas = [u["nota"] for u in calzado.fasteners.values() if u["name"].startswith("c1_ancla_")]
    assert notas and all("25 mm de calza" in n and "tfix 50 de ANCLA-EXP-M12-145" in n
                         for n in notas)
    assert all("25 mm de calza" in g["nota"] for g in calzado.grounds.values())


def test_con_calza_sin_interferencias_y_la_puerta_en_verde(calzado):
    assert calzado.check_integrity() == []
    formas = {f: x.shape for f, x in calzado.scene.items()}
    assert interferencias_sin_tope(formas, set()) == []
    rep = delivery_report(**delivery_inputs(calzado, expand=lambda v: []))
    assert rep["veredicto"] == VERDE and rep["avisos"] == [] and rep["bloqueantes"] == []


def test_el_largo_del_anclaje_nuevo_es_de_catalogo_en_la_puerta():
    insumo = {"fid": "a", "nombre": "Anclaje", "ref": "ANCLA-EXP-M12-145", "cabeza": "hex",
              "d": 12.0, "paso": 1.75, "largo": 120.0, "tramos": [], "mas_alla": []}
    e, txt, _ = evaluar_perno(insumo)["largo"]
    assert e == OK and "M12×145" in txt, txt


def test_el_anclaje_pedido_que_no_alcanza_se_rechaza_con_los_que_si():
    with pytest.raises(DocumentError, match="ANCLA-EXP-M12 fija hasta 20 mm.*ANCLA-EXP-M12-145"):
        _doc({**LIBRE, "calza_mm": 25, "anclaje_ref": ANCLAJE_REF})
    with pytest.raises(DocumentError, match="anclaje: true"):
        _doc({**LIBRE, "anclaje": False, "calza_mm": 5})
    with pytest.raises(Exception, match="anclaje_ref"):
        _doc({**LIBRE, "anclaje_ref": "ANCLA-NO-EXISTE"})
    doc = _doc({**LIBRE, "anclaje_ref": "ANCLA-EXP-M12-165"})
    assert _bom(doc).get("ANCLA-EXP-M12-165") == 8
