"""Catálogo data-driven (V3 bloque #1): loader YAML, familias paramétricas y
builders geométricos genéricos. Verifica la migración 1:1 de los 14 componentes
originales y las 4 familias nuevas sembradas."""
import math

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.library.builders import BUILDERS
from apolo.library.catalog import (
    CATALOG,
    build_component,
    category_refs_sorted,
    refs_in_category,
)
from apolo.library.loader import eval_formula, load_catalog

# Tabla de referencia: los 14 componentes originales deben sobrevivir 1:1.
LEGACY = {
    "PERFIL-2020": (0.5, True, 1000, "perfiles"),
    "PERFIL-3030": (0.9, True, 1000, "perfiles"),
    "PERFIL-4040": (1.6, True, 1000, "perfiles"),
    "PERFIL-4080": (3.0, True, 1000, "perfiles"),
    "PERFIL-4545": (2.0, True, 1000, "perfiles"),
    "RODILLO-50": (1.9, True, 600, "rodillos"),
    "RODILLO-60": (2.9, True, 600, "rodillos"),
    "RODILLO-80": (5.7, True, 850, "rodillos"),
    "MOTOR-037": (11.0, False, None, "motorreductores"),
    "MOTOR-075": (16.0, False, None, "motorreductores"),
    "MOTOR-150": (24.0, False, None, "motorreductores"),
    "PATA-REG": (2.1, True, 600, "patas"),
    "GUARDA-150": (7.1, True, 1000, "guardas"),
    "FOTO-M18": (0.08, False, None, "sensores"),
}


# ------------------------------------------------------------------ migración
def test_legacy_components_migrated_1to1():
    for ref, (weight, cuttable, deflen, category) in LEGACY.items():
        c = CATALOG[ref]
        assert c.weight == weight, ref
        assert c.cuttable == cuttable, ref
        assert c.default_length == deflen, ref
        assert c.category == category, ref
        shape, cut = build_component(ref, c.default_length)
        assert shape.volume > 0


def test_legacy_order_preserved():
    # los 14 originales en el mismo orden que antes del refactor
    legacy_in_catalog = [r for r in CATALOG if r in LEGACY]
    assert legacy_in_catalog == list(LEGACY.keys())


# -------------------------------------------------------------------- loader
def test_loader_rejects_duplicate_ref(tmp_path):
    (tmp_path / "a.yaml").write_text(
        "category: x\ncomponents:\n"
        "  - {ref: DUP, name: A, builder: box, params: {width: 1, depth: 1, height: 1}, weight: 1}\n"
        "  - {ref: DUP, name: B, builder: box, params: {width: 1, depth: 1, height: 1}, weight: 1}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicada"):
        load_catalog(str(tmp_path))


def test_loader_rejects_unknown_builder(tmp_path):
    (tmp_path / "a.yaml").write_text(
        "category: x\ncomponents:\n  - {ref: R, name: A, builder: noexiste, weight: 1}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="builder desconocido"):
        load_catalog(str(tmp_path))


def test_eval_formula_safe():
    assert eval_formula("a * b + 2", {"a": 3, "b": 4, "txt": "x"}) == 14
    with pytest.raises(Exception):
        eval_formula("__import__('os')", {})


# ------------------------------------------------------------------ familias
def test_family_expands_to_variants():
    refs = refs_in_category("rodamientos")
    # ISO 15 completo: series 6000/6200/6300/6400 (Ø int 10-50 mm)
    assert len(refs) == 41
    assert {"6000", "6200", "6205", "6206", "6300", "6310", "6403", "6410"} <= set(refs)
    c = CATALOG["6205"]
    assert c.specs["d"] == 25 and c.specs["D"] == 52 and c.specs["B"] == 15
    assert c.specs["tipo"] == "rígido de bolas"  # spec_common heredada


def test_all_new_families_present():
    assert len(refs_in_category("tornilleria")) == 6
    assert len(refs_in_category("guias_lineales")) == 10  # 5 rieles + 5 carros
    assert len(refs_in_category("transmision")) == 14  # 5 poleas dentadas + 3 tensores + 6 poleas en V
    # V2: chumaceras, topes, pies niveladores
    assert len(refs_in_category("chumaceras")) == 3
    assert len(refs_in_category("topes")) == 3
    assert len(refs_in_category("pies_niveladores")) == 3
    # realismo: familia de tambores motrices/reenvío con eje
    assert len(refs_in_category("tambores")) == 5  # + Ø102 motriz y cola (faja de banda)
    assert len(refs_in_category("motorreductores")) == 4  # + MOTOR-150-EH
    # faja de banda: tensor trotadora + eléctrico (variador, tablero, mandos)
    assert len(refs_in_category("tensores_trotadora")) == 2
    assert len(refs_in_category("variadores")) == 1
    assert len(refs_in_category("tableros")) == 1
    assert len(refs_in_category("mandos")) == 2
    # familias de norma (ISO 15 / ASTM A500 / EN): tubos y perfiles
    assert len(refs_in_category("tubos_estructurales")) == 16  # ASTM A500 HSS cuadrado/rect
    assert len(refs_in_category("tubos_circulares")) == 10     # ASTM A500 round HSS
    assert len(refs_in_category("perfiles_abiertos")) == 22    # 8 L + 7 UPN + 7 IPE
    assert len(refs_in_category("rodamientos")) == 41          # ISO 15 completo (11+11+11+8)
    # carpintería / herraje (bisagras, tiradores, correderas, tirafondos, cerraduras, imanes)
    assert len(refs_in_category("bisagras")) == 14
    assert len(refs_in_category("tiradores")) == 7
    assert len(refs_in_category("correderas")) == 2
    assert len(refs_in_category("tornilleria_madera")) == 4
    assert len(refs_in_category("cerraduras")) == 2
    assert len(refs_in_category("imanes_topes")) == 2
    # herraje de puerta corrediza/colgante (Ducasse U-100 / D-100)
    assert len(refs_in_category("rieles_corredera")) == 2
    assert len(refs_in_category("correderas_colgantes")) == 2
    # tornillería comercial para tensores (DIN 933 / 934)
    assert len(refs_in_category("pernos")) == 4
    assert len(refs_in_category("tuercas")) == 4
    assert len(CATALOG) == 197  # +6 poleas en V (faja de potencia)


def test_door_sliding_hardware():
    """Riel U (cortable, perfil en U real) + corredera colgante de 4 ruedas (D-100)."""
    riel, _ = build_component("RIEL-U100", 1970)
    bb = riel.bounding_box()
    assert math.isclose(bb.max.X - bb.min.X, 1970, abs_tol=0.5)  # cortado a la luz
    # sección en U (~153 mm²), no maciza (35×35 macizo daría ~2.4e6 mm³)
    assert 2.5e5 < riel.volume < 4e5
    corr, _ = build_component("CORR-D100", CATALOG["CORR-D100"].default_length)
    cb = corr.bounding_box()
    assert math.isclose(cb.max.X - cb.min.X, 80, abs_tol=1.0)   # 80 mm a lo largo del riel
    assert corr.volume > 0 and CATALOG["CORR-D100"].specs["capacidad_kg"] == 100


# ----------------------------------------------------------- geometría nueva
@pytest.mark.parametrize(
    "ref,dx,dy,dz",
    [("6205", 52, 52, 15), ("DIN912-M8", 13, 13, 38), ("CARRO-25", 84, 48, 36), ("POLEA-80", 88, 88, 20)],
)
def test_new_geometry_bbox(ref, dx, dy, dz):
    shape, _ = build_component(ref, CATALOG[ref].default_length)
    bb = shape.bounding_box()
    assert shape.volume > 0
    assert math.isclose(bb.max.X - bb.min.X, dx, abs_tol=0.5)
    assert math.isclose(bb.max.Y - bb.min.Y, dy, abs_tol=0.5)
    assert math.isclose(bb.max.Z - bb.min.Z, dz, abs_tol=0.5)
    # centrado en el origen (eje Z)
    assert math.isclose((bb.min.Z + bb.max.Z) / 2, 0, abs_tol=0.5)


def test_realism_shafts_and_motor():
    # rodillo con eje pasante: el eje sobresale (Z = cara + 2·muñón), cuerpo Ø50
    shp, _ = build_component("RODILLO-50", 600)
    bb = shp.bounding_box()
    assert math.isclose(bb.max.Z - bb.min.Z, 600 + 2 * 25, abs_tol=0.5)
    assert math.isclose(bb.max.X - bb.min.X, 50, abs_tol=0.5)

    # tambor (polea motriz) con eje pasante + cuerpo Ø80
    shp, _ = build_component("TAMBOR-80", 500)
    bb = shp.bounding_box()
    assert math.isclose(bb.max.Z - bb.min.Z, 500 + 2 * 40, abs_tol=0.5)
    assert math.isclose(bb.max.X - bb.min.X, 80, abs_tol=0.5)

    # motorreductor enriquecido (box_size=140): eje de salida sale por -Y; patas bajo el reductor
    shp, _ = build_component("MOTOR-075")
    bb = shp.bounding_box()
    assert shp.volume > 0
    assert bb.min.Y < -70   # eje de salida más allá del costado del reductor
    assert bb.min.Z < -82   # patas por debajo de la caja del reductor


def test_rail_is_cuttable():
    c = CATALOG["RIEL-25"]
    assert c.cuttable and c.default_length == 1000
    shape, cut = build_component("RIEL-25", 500)
    assert cut == 500
    bb = shape.bounding_box()
    assert math.isclose(bb.max.X - bb.min.X, 500, abs_tol=1e-3)


def test_weight_formula_applied():
    # anillo macizo de acero: 7.85e-6 * 0.785 * (D^2 - d^2) * B
    expected = 7.85e-6 * 0.785 * (52 * 52 - 25 * 25) * 15
    assert CATALOG["6205"].weight == pytest.approx(expected, rel=1e-3)


# -------------------------------------------------------------- desacoplado
def test_recommendations_still_correct():
    from apolo.library.rules import recommend_motor, recommend_roller

    assert recommend_motor(50, 3000, 400, 0.33) == "MOTOR-037"
    assert recommend_roller(50, 400, 100) == "RODILLO-50"
    assert category_refs_sorted("rodillos", "capacidad_kg") == ["RODILLO-50", "RODILLO-60", "RODILLO-80"]


def test_conveyor_enums_dynamic_from_catalog():
    from apolo.commands.models import CreateConveyorParams

    sch = CreateConveyorParams.model_json_schema()
    assert sch["properties"]["rodillo"]["enum"] == refs_in_category("rodillos")
    assert sch["properties"]["motor"]["enum"] == ["ninguno"] + refs_in_category("motorreductores")


# ----------------------------------------------------------------- e2e API
def test_new_family_insertable_and_in_catalog():
    api.DOC = Document("dd-test")
    client = TestClient(api.app)
    refs = {i["ref"] for i in client.get("/api/catalog").json()}
    assert {"6205", "DIN912-M8", "RIEL-25", "POLEA-80"} <= refs
    r = client.post("/api/commands", json={"type": "insert_component", "params": {"component": "6205"}})
    assert r.status_code == 200
    feat = client.get("/api/scene").json()["features"][0]
    assert feat["component"] == "6205"
