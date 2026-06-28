"""Faja de banda (belt conveyor): piezas de catálogo nuevas y, más adelante, el
super-comando create_belt_conveyor. Fase 0 = base del catálogo (tubo estructural
de acero, tambores Ø101.6 motriz/cola, motorreductor de eje hueco)."""
import math

import pytest

from apolo.library.catalog import CATALOG, build_component, refs_in_category


def test_tubo_estructural_es_hueco_y_cortable():
    c = CATALOG["TUBO-4X2"]
    assert c.category == "tubos_estructurales"
    assert c.cuttable and c.default_length == 6000
    assert "acero" in c.specs["material"].lower()
    shape, cut = build_component("TUBO-4X2", 4000)
    assert cut == 4000
    bb = shape.bounding_box()
    # sección 101.6 × 50.8, extruida 4000 a lo largo de Z, centrada en el origen
    assert math.isclose(bb.max.X - bb.min.X, 101.6, abs_tol=0.5)
    assert math.isclose(bb.max.Y - bb.min.Y, 50.8, abs_tol=0.5)
    assert math.isclose(bb.max.Z - bb.min.Z, 4000, abs_tol=0.5)
    assert math.isclose((bb.min.Z + bb.max.Z) / 2, 0, abs_tol=0.5)
    # HUECO: el volumen es muy inferior al de la caja envolvente
    caja = bb.size.X * bb.size.Y * bb.size.Z
    assert shape.volume < 0.5 * caja


def test_tubo_peso_por_metro_acero():
    # 7.85e-6 kg/mm³ × área de sección (mm²) × 1000 mm = kg/m (TUBO-4X2 ASTM A500, pared 4.8)
    area = 101.6 * 50.8 - (101.6 - 2 * 4.8) * (50.8 - 2 * 4.8)
    assert CATALOG["TUBO-4X2"].weight == pytest.approx(7.85e-6 * area * 1000, rel=1e-3)


def test_tubos_presentes():
    refs = set(refs_in_category("tubos_estructurales"))
    assert {"TUBO-4X2", "TUBO-3X2", "TUBO-2X2"} <= refs  # los que usa la faja
    assert len(refs) >= 16  # familia ASTM A500 completa


def test_tambor_102_motriz_con_lagging_y_eje():
    shp, cut = build_component("TAMBOR-102", 650)
    assert cut == 650
    bb = shp.bounding_box()
    # cara 650 + 2 muñones (stub 40) en Z; el eje es el elemento más largo
    assert math.isclose(bb.max.Z - bb.min.Z, 650 + 2 * 40, abs_tol=1.0)
    # con lagging (6 mm) el Ø supera el nominal 101.6
    assert (bb.max.X - bb.min.X) > 101.6
    assert CATALOG["TAMBOR-102"].specs["eje_mm"] == 25


def test_tambor_102_cola_eje_fijo_sin_lagging():
    cola, _ = build_component("TAMBOR-102-COLA", 650)
    bb = cola.bounding_box()
    assert math.isclose(bb.max.X - bb.min.X, 101.6, abs_tol=0.6)  # sin lagging
    assert "eje fijo" in CATALOG["TAMBOR-102-COLA"].specs["tipo"]


def test_motor_eje_hueco_variante():
    c = CATALOG["MOTOR-150-EH"]
    assert c.category == "motorreductores"
    assert c.specs["rpm_salida"] == 188 and c.specs["potencia_kW"] == 1.5
    shp, cut = build_component("MOTOR-150-EH")
    assert cut is None and shp.volume > 0


def test_tensor_trotadora_tiene_alojamiento_de_eje():
    c = CATALOG["TENSOR-TROT-25"]
    assert c.category == "tensores_trotadora"
    assert c.specs["shaft_d"] == 25
    assert c.specs["bolt_d"] == 16  # tornillo tensor M16 (estilo trotadora)
    assert c.weight > 0
    shp, cut = build_component("TENSOR-TROT-25")
    assert cut is None and shp.volume > 0
    # soporte en «C» abierto + tornillo → volumen muy inferior al de su caja envolvente
    bb = shp.bounding_box()
    assert shp.volume < 0.6 * bb.size.X * bb.size.Y * bb.size.Z


def test_electrico_en_catalogo():
    for ref, cat in [("VFD-1K5-220", "variadores"), ("TABLERO-5040", "tableros"),
                     ("ESTOP-40", "mandos"), ("BOTONERA-2", "mandos")]:
        c = CATALOG[ref]
        assert c.category == cat
        shp, cut = build_component(ref)
        assert cut is None and shp.volume > 0
    assert CATALOG["VFD-1K5-220"].specs["potencia_kW"] == 1.5


# ----------------------------------------------- super-comando create_belt_conveyor
import apolo.api.main as api  # noqa: E402
from apolo.commands.registry import CommandError  # noqa: E402
from apolo.doc import Document, DocumentError  # noqa: E402
from apolo.library.bom import bom_from_scene  # noqa: E402
from apolo.library.checks import interference_report, same_command_pairs  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _belt_doc(**overrides):
    p = {"largo": 4000, "ancho_banda": 600, "altura": 900}
    p.update(overrides)
    d = Document()
    cid = d.execute("create_belt_conveyor", p)
    return d, cid


def test_belt_conveyor_genera_todas_las_piezas():
    d, _ = _belt_doc()
    names = [f.name for f in d.scene.values()]
    assert sum("Larguero" in n for n in names) == 2
    assert sum(n == "Faja de banda · Tambor motriz" for n in names) == 1
    assert sum(n == "Faja de banda · Tambor de cola" for n in names) == 1
    assert sum("Banda" in n for n in names) == 1
    assert sum("Cama de deslizamiento" in n for n in names) == 1
    assert sum("Pata" in n for n in names) == 4
    assert sum("Pie nivelador" in n for n in names) == 4
    assert sum("Tensor trotadora" in n for n in names) == 2
    assert sum("Motorreductor" in n for n in names) == 1
    assert sum("Guarda lateral" in n for n in names) == 2
    assert len(d.scene) == 21  # 2 largueros + 2 tambores + banda + cama + 4 patas + 4 pies + 2 travesaños + 2 tensores (C+M16) + motor + 2 guardas


def test_belt_conveyor_banda_es_lazo_hueco():
    d, _ = _belt_doc()
    belt = next(f for f in d.scene.values() if f.name.endswith("Banda"))
    bb = belt.shape.bounding_box()
    assert belt.shape.volume > 0
    # lazo hueco: volumen muy inferior al de su caja envolvente
    assert belt.shape.volume < 0.3 * bb.size.X * bb.size.Y * bb.size.Z


def test_belt_conveyor_bom_usa_piezas_nuevas():
    d, _ = _belt_doc()
    refs = {r["ref"] for r in bom_from_scene(d.scene)}
    assert {"TUBO-4X2", "TUBO-2X2", "TAMBOR-102", "TAMBOR-102-COLA",
            "MOTOR-150-EH", "TENSOR-TROT-25", "PIE-M12-50", "GUARDA-150"} <= refs
    # los largueros salen cortados al largo + voladizos
    rows = {(r["ref"], r["longitud_mm"]): r["cantidad"] for r in bom_from_scene(d.scene)}
    assert rows[("TUBO-4X2", 4189.6)] == 2  # 4000 + 2·(50.8 + 4 + 40) voladizos


def test_belt_conveyor_bom_separa_banda_y_cama():
    d, _ = _belt_doc()
    custom = [r for r in bom_from_scene(d.scene) if r["ref"] == "A-MEDIDA"]
    rows = {r["descripcion"].split(" · ")[-1]: r["cantidad"] for r in custom}
    # piezas a medida DISTINTAS del mismo super-comando → filas separadas (no colapsan)
    assert rows["Banda"] == 1
    assert rows["Cama de deslizamiento"] == 1


def test_belt_conveyor_sin_auto_interferencia():
    d, _ = _belt_doc()
    report = interference_report(d.scene, exclude_pairs=same_command_pairs(d))
    assert report["interferencias"] == []


def test_belt_conveyor_edicion_parametrica():
    d, cid = _belt_doc()
    def drum_z():
        bb = next(f for f in d.scene.values()
                  if f.name.endswith("Tambor motriz")).shape.bounding_box()
        return (bb.min.Z + bb.max.Z) / 2.0
    # zc = altura - r - espesor = 900 - 50.8 - 4
    assert drum_z() == pytest.approx(900 - 50.8 - 4, abs=1.0)
    d.edit(cid, {"largo": 4000, "ancho_banda": 600, "altura": 1100})
    assert drum_z() == pytest.approx(1100 - 50.8 - 4, abs=1.0)


def test_belt_conveyor_validaciones():
    d = Document()
    with pytest.raises((CommandError, DocumentError)):
        d.execute("create_belt_conveyor", {"largo": 150, "ancho_banda": 600, "altura": 900})
    with pytest.raises((CommandError, DocumentError)):
        d.execute("create_belt_conveyor", {"largo": 4000, "ancho_banda": 600, "altura": 900, "tubo": "NO-EXISTE"})
    assert d.commands == []


def test_belt_conveyor_opcionales_off():
    d, _ = _belt_doc(tensor="ninguno", motor="ninguno", guardas=False)
    names = [f.name for f in d.scene.values()]
    assert not any("Tensor" in n for n in names)
    assert not any("Motorreductor" in n for n in names)
    assert not any("Guarda" in n for n in names)


def test_belt_conveyor_api_y_checks():
    api.DOC = Document("belt-test")
    client = TestClient(api.app)
    r = client.post("/api/commands", json={"type": "create_belt_conveyor", "params": {
        "largo": 4000, "ancho_banda": 600, "altura": 900}})
    assert r.status_code == 200
    bom = client.get("/api/bom").json()
    assert any(row["ref"] == "TAMBOR-102" for row in bom)
    checks = client.post("/api/checks", json={}).json()
    assert checks["interferencias"]["interferencias"] == []
