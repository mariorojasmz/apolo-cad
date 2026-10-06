"""Garruchas de catálogo (plan `docs/plans/garruchas-catalogo.md`, F1).

24 refs reales (Blickle LH-ALTH / -ST / BH-ALTH y Colson Colombia serie 44/45 PU) con el
builder `caster` de `library/builders_rodaje.py`. Lo que se prueba es el CONTRATO del marco
canónico (origen = centro de la cara superior de la placa, apoyo al piso en z = −altura, rueda en
x = −avance) porque es lo que el agente usa para colocarlas: `position` = cara de montaje.
"""

from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path

import pytest
from build123d import Box, Pos

from apolo.assembly.grouping import CAT2SUB
from apolo.doc import Document
from apolo.library.builders_rodaje import caster
from apolo.library.catalog import CATALOG, CATEGORIES, build_component, component_anchors, refs_in_category
from apolo.library.checks import FEA_HARDWARE_CATS, HARDWARE_CATS
from apolo.library.loader import merge_builders

BLICKLE = [
    "LH-ALTH-100K-3", "LH-ALTH-125K-3", "LH-ALTH-150K", "LH-ALTH-200K",
    "LH-ALTH-100K-3-ST", "LH-ALTH-125K-3-ST", "LH-ALTH-150K-ST", "LH-ALTH-200K-ST",
    "BH-ALTH-100K-3", "BH-ALTH-125K-3", "BH-ALTH-150K", "BH-ALTH-200K",
]
COLSON = [
    f"COLSON-{n}X2-PU-{s}" for s in ("45-A", "45-A-FT", "44-A") for n in (4, 5, 6, 8)
]
TODAS = BLICKLE + COLSON

# pares (giratoria, con freno total) del mismo Ø
PARES_FRENO = [
    ("LH-ALTH-100K-3", "LH-ALTH-100K-3-ST"), ("LH-ALTH-125K-3", "LH-ALTH-125K-3-ST"),
    ("LH-ALTH-150K", "LH-ALTH-150K-ST"), ("LH-ALTH-200K", "LH-ALTH-200K-ST"),
] + [(f"COLSON-{n}X2-PU-45-A", f"COLSON-{n}X2-PU-45-A-FT") for n in (4, 5, 6, 8)]

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=None)
def _shape(ref: str):
    shape, _ = build_component(ref)
    return shape


def _specs(ref: str) -> dict:
    return CATALOG[ref].specs


# ------------------------------------------------------------------ carga del catálogo
def test_las_24_refs_cargan_en_su_categoria():
    assert sorted(refs_in_category("garruchas")) == sorted(TODAS)
    assert CATEGORIES[-1] == "garruchas"  # al final: no reordena la UI ni el enum
    for ref in TODAS:
        comp = CATALOG[ref]
        assert comp.category == "garruchas"
        assert comp.weight > 0, ref
        assert comp.cuttable is False, ref
        assert "cost" not in comp.specs, f"{ref}: sin precio publicado del MISMO modelo (D4)"
        assert comp.specs["carga_kg"] > 0, ref
        assert comp.specs["no_publicado"].strip(), ref
        assert comp.name.startswith("Garrucha "), ref
        assert _shape(ref).volume > 0, ref


def test_specs_por_marca():
    for ref in BLICKLE:
        s = _specs(ref)
        assert s["fabricante"] == "Blickle"
        assert s["carga_estatica_kg"] > s["carga_kg"], ref
        assert "radio_giro" not in s, f"{ref}: Blickle no publica radio de giro (D3)"
    for ref in COLSON:
        s = _specs(ref)
        assert s["fabricante"].startswith("Colson Colombia")
        assert "carga_estatica_kg" not in s, ref
        if s["tipo"] == "fija":
            assert "radio_giro" not in s, ref  # una fija no gira
            continue
        # el avance es DERIVADO del radio de giro publicado: e = √(R² − (b/2)²) − D/2
        e = math.sqrt(s["radio_giro"] ** 2 - (s["rueda_b"] / 2) ** 2) - s["rueda_d"] / 2
        assert math.isclose(e, s["avance"], abs_tol=0.1), (ref, e)


# ------------------------------------------------------------------ marco canónico
@pytest.mark.parametrize("ref", TODAS)
def test_bbox_cara_de_montaje_en_el_origen_y_apoyo_a_menos_altura(ref):
    s = _specs(ref)
    bb = _shape(ref).bounding_box()
    assert math.isclose(bb.max.Z, 0.0, abs_tol=0.5), ref
    assert math.isclose(bb.min.Z, -s["altura"], abs_tol=0.5), ref
    assert bb.max.X - bb.min.X >= s["placa_l"] - 0.01, ref
    assert bb.max.Y - bb.min.Y >= s["placa_w"] - 0.01, ref


@pytest.mark.parametrize("ref", TODAS)
def test_apoyo_al_piso_bajo_la_rueda(ref):
    """La franja de 3 mm sobre el piso sólo toca la rueda: centrada en x = −avance (gira) o 0."""
    s = _specs(ref)
    h = s["altura"]
    franja = _shape(ref) & (Pos(0, 0, -h + 1.5) * Box(2000, 2000, 3))
    fb = franja.bounding_box()
    esperado = 0.0 if s["tipo"] == "fija" else -s["avance"]
    assert math.isclose((fb.min.X + fb.max.X) / 2, esperado, abs_tol=0.5), ref
    assert math.isclose((fb.min.Y + fb.max.Y) / 2, 0.0, abs_tol=0.5), ref
    assert math.isclose(fb.min.Z, -h, abs_tol=0.5), ref


@pytest.mark.parametrize("ref", TODAS)
def test_agujeros_y_ranuras_pasantes_a_media_placa(ref):
    """Centros de agujero y AMBOS extremos de la ranura (Blickle 75–80) fuera del sólido; la
    placa junto al agujero sí es material (el corte no se comió la placa)."""
    s = _specs(ref)
    shape = _shape(ref)
    z = -s["placa_t"] / 2
    ax = s["agujeros_x"] / 2
    for sx in (1, -1):
        for sy in (1, -1):
            for y in {s["agujeros_y_min"] / 2, s["agujeros_y_max"] / 2}:
                assert not shape.is_inside((sx * ax, sy * y, z)), (ref, sx, sy, y)
            y_material = s["agujeros_y_max"] / 2 + s["agujero_d"] / 2 + 2.0
            assert shape.is_inside((sx * ax, sy * y_material, z)), (ref, "placa")
    if ref in BLICKLE:
        assert s["agujeros_y_min"] < s["agujeros_y_max"]  # ranura real, no agujero redondo


@pytest.mark.parametrize("giratoria,freno", PARES_FRENO)
def test_el_pedal_del_freno_sobresale_detras_de_la_rueda(giratoria, freno):
    s = _specs(freno)
    bb_g = _shape(giratoria).bounding_box()
    bb_f = _shape(freno).bounding_box()
    assert bb_f.min.X < bb_g.min.X - 5.0, (giratoria, freno)
    assert bb_f.min.X < -s["avance"] - s["rueda_d"] / 2  # más allá del borde trasero de la rueda


# ------------------------------------------------------------------ el builder rechaza lo imposible
_BASE = dict(tipo="giratoria", rueda_d=125, rueda_b=40, altura=165, placa_l=140, placa_w=110,
             placa_t=5, agujeros_x=105, agujeros_y_min=75, agujeros_y_max=80, agujero_d=11,
             avance=45)


def test_builder_rechaza_tipo_desconocido():
    with pytest.raises(ValueError, match="tipo desconocido"):
        caster(**{**_BASE, "tipo": "loca"})(None)


def test_builder_rechaza_fija_con_avance():
    with pytest.raises(ValueError, match="fija"):
        caster(**{**_BASE, "tipo": "fija", "avance": 30})(None)


def test_builder_rechaza_altura_sin_lugar_para_la_horquilla():
    # 125 + 5 + 5 = 135 → gap 5 < 6
    with pytest.raises(ValueError, match="horquilla"):
        caster(**{**_BASE, "altura": 135})(None)
    caster(**{**_BASE, "altura": 136})(None)  # gap 6: justo cabe


def test_merge_builders_rechaza_nombre_repetido():
    a = {"caster": object(), "box": object()}
    assert set(merge_builders(a, {"otro": object()})) == {"caster", "box", "otro"}
    with pytest.raises(ValueError, match="caster"):
        merge_builders(a, {"caster": object()})


# ------------------------------------------------------------------ integración con el resto
def test_ancla_placa_subsistema_y_fea():
    anclas = component_anchors(CATALOG["COLSON-5X2-PU-45-A-FT"])
    assert anclas == {"placa": {"origin": [0.0, 0.0, 0.0], "axis": [0.0, 0.0, 1.0]}}
    assert CAT2SUB["garruchas"] == "Estructura"
    tree = (ROOT / "ui" / "src" / "panels" / "Tree.tsx").read_text(encoding="utf-8")
    assert re.search(r'\bgarruchas:\s*"Estructura"', tree), "Tree.tsx: CAT2SUB sin garruchas"
    assert "garruchas" in FEA_HARDWARE_CATS
    assert "garruchas" not in HARDWARE_CATS


def test_insert_component_pone_la_cara_de_montaje_en_position():
    doc = Document()
    fid = doc.execute("insert_component", {
        "component": "COLSON-5X2-PU-45-A-FT", "position": {"x": 300, "y": 0, "z": 160},
    })
    feat = doc.scene[fid]
    bb = feat.shape.bounding_box()
    assert math.isclose(bb.max.Z, 160.0, abs_tol=0.5)
    assert math.isclose(bb.min.Z, 160.0 - 169.9, abs_tol=0.5)
    placa = feat.anchors["placa"]
    assert all(math.isclose(a, b, abs_tol=1e-6) for a, b in zip(placa["origin"], (300, 0, 160)))
    assert all(math.isclose(a, b, abs_tol=1e-6) for a, b in zip(placa["axis"], (0, 0, 1)))
