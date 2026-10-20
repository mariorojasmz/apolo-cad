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
    for ref, cat in [("VFD-1K5-220", "variadores"), ("VFD-2K2-220", "variadores"),
                     ("TABLERO-5040", "tableros"), ("ESTOP-40", "mandos"), ("BOTONERA-2", "mandos")]:
        c = CATALOG[ref]
        assert c.category == cat
        shp, cut = build_component(ref)
        assert cut is None and shp.volume > 0
    assert CATALOG["VFD-1K5-220"].specs["potencia_kW"] == 1.5
    vfd = CATALOG["VFD-2K2-220"]
    assert vfd.specs["potencia_kW"] == 2.2 and vfd.specs["proteccion"] == "STO"
    bb = build_component("VFD-2K2-220")[0].bounding_box()
    # cabe en el TABLERO-5040 (500 x 200 x 400) con aire para el cableado
    assert bb.size.X <= 500 - 100 and bb.size.Y <= 200 - 30 and bb.size.Z <= 400 - 100


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
    assert rows[("TUBO-4X2", 4201.6)] == 2  # 4000 + 2·(50.8 + 6 engomado + 4 + 40) voladizos


def test_belt_conveyor_bom_separa_banda_y_cama():
    d, _ = _belt_doc()
    custom = [r for r in bom_from_scene(d.scene) if r["ref"] == "A-MEDIDA"]
    rows = {r["descripcion"].split(" · ")[-1]: r["cantidad"] for r in custom}
    # piezas a medida DISTINTAS del mismo super-comando → filas separadas (no colapsan)
    assert rows["Banda"] == 1
    assert rows["Cama de deslizamiento"] == 1


def test_belt_conveyor_banda_es_pvc_en_bom_y_masa():
    # la faja piloto de V8.2 (3000×500×800): la «Banda» caía a acero (~99 kg de lazo); por su
    # ROL es PVC (~18 kg). La cama, que sólo comparte «banda» con el prefijo, sigue de acero
    from apolo.library.engineering.mass import feature_mass
    from apolo.library.materials import density

    d, cid = _belt_doc(largo=3000, ancho_banda=500, altura=800)
    belt = d.scene[f"{cid}_banda"]
    assert belt.name == "Faja de banda · Banda"
    fm = feature_mass(belt, default_material=d.default_material())
    assert fm["material"] == "pvc"
    assert fm["masa_kg"] == pytest.approx(belt.shape.volume * density("pvc"), rel=1e-6)
    assert 15.0 < fm["masa_kg"] < 20.0
    rows = {r["descripcion"]: r for r in bom_from_scene(d.scene, d.default_material())}
    assert rows["Faja de banda · Banda"]["material"] == "pvc"
    assert rows["Faja de banda · Banda"]["peso_unitario_kg"] == pytest.approx(fm["masa_kg"], abs=1e-3)
    assert rows["Faja de banda · Cama de deslizamiento"]["material"] == "acero"
    # sólo la banda cambió: ninguna otra pieza de la faja resuelve a polímero
    assert [r["descripcion"] for r in rows.values() if r["material"] in ("pvc", "caucho")] == [
        "Faja de banda · Banda"]
    # set_material sigue mandando y null vuelve al automático (PVC por rol)
    d.set_material(belt.id, "caucho")
    assert feature_mass(d.scene[belt.id])["material"] == "caucho"
    d.set_material(belt.id, None)
    assert feature_mass(d.scene[belt.id])["material"] == "pvc"


def test_belt_conveyor_memoria_pesa_solo_el_lazo():
    # `banda_kg` (arrastre sobre cama de la memoria) sumaba TODA la faja: cada pieza se llama
    # «Faja de banda · …». Ahora cuenta sólo el ROL banda/cinta/faja
    from apolo.commands.registry import Feature
    from apolo.library.engineering.mass import feature_mass
    from apolo.library.rules import _enrich_conveyor, detect_conveyor
    from build123d import Box

    d, cid = _belt_doc(largo=3000, ancho_banda=500, altura=800)
    conv = detect_conveyor(d.scene, {})
    assert conv["banda_kg"] == pytest.approx(feature_mass(d.scene[f"{cid}_banda"])["masa_kg"], abs=0.01)
    # a mano (nombres del 38): la banda cuenta; la cama que la MENCIONA, no
    scene = {"b": Feature("b", "Banda PVC 2mm 700 (lazo cerrado)", Box(1000, 700, 2), "c1"),
             "c": Feature("c", "Cama de la banda", Box(1000, 700, 20), "c2")}
    assert _enrich_conveyor({"tipo": "banda"}, scene, {})["banda_kg"] == pytest.approx(1.96, abs=0.01)


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
    # eje motriz = altura - (r + engomado) - espesor = 900 - (50.8 + 6) - 4
    assert drum_z() == pytest.approx(900 - 56.8 - 4, abs=1.0)
    d.edit(cid, {"largo": 4000, "ancho_banda": 600, "altura": 1100})
    assert drum_z() == pytest.approx(1100 - 56.8 - 4, abs=1.0)


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


def _pieza(d, sufijo):
    return next(f for f in d.scene.values() if f.name.endswith(sufijo))


@pytest.mark.parametrize("tambor", ["Tambor motriz", "Tambor de cola"])
def test_belt_conveyor_banda_abraza_el_tambor_sin_atravesarlo(tambor):
    """La banda abraza el Ø EXTERIOR del tambor, engomado incluido: el TAMBOR-102 motriz mide
    Ø101.6 + 2×6 de lagging = Ø113.6 y la banda se hacía con Ø101.6 (se metía 6 mm). El chequeo
    de interferencias no lo veía: excluye los pares del mismo comando."""
    d, _ = _belt_doc()
    banda, t = _pieza(d, "Banda").shape, _pieza(d, tambor).shape
    cruce = banda & t
    assert (cruce.volume if cruce is not None else 0.0) == pytest.approx(0.0, abs=1.0)  # se tocan
    # y la abraza de verdad: el interior de la banda no queda separado del tambor
    bb_t = t.bounding_box()
    hueco = banda.bounding_box()
    assert bb_t.max.Z <= hueco.max.Z


def test_belt_conveyor_ramal_de_carga_plano_con_tambor_engomado():
    """El ramal de carga queda a la altura de trabajo sobre los DOS tambores aunque sólo el
    motriz esté engomado: cada eje baja lo que crece su tambor."""
    d, _ = _belt_doc()
    sup = lambda s: _pieza(d, s).shape.bounding_box().max.Z  # noqa: E731
    assert sup("Banda") == pytest.approx(900, abs=0.5)
    assert sup("Tambor motriz") == pytest.approx(900 - 4, abs=0.5)
    assert sup("Tambor de cola") == pytest.approx(900 - 4, abs=0.5)
