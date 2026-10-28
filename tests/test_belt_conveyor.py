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

    def cuenta(rol):
        return sum(n.split(" · ")[-1].startswith(rol) for n in names)

    assert cuenta("Larguero") == 2
    assert sum(n == "Faja de banda · Tambor motriz" for n in names) == 1
    assert sum(n == "Faja de banda · Tambor de cola" for n in names) == 1
    # F1c (criterio 8): la cama en paños ≤ 3 m (2 de 1,9 m), cada uno con sus soportes de punta
    assert cuenta("Banda") == 1 and cuenta("Cama de deslizamiento") == 2
    assert cuenta("Pata") == 4 and cuenta("Placa de la pata") == 4 and cuenta("Pie nivelador") == 4
    assert cuenta("Travesaño") == 2
    assert cuenta("Soporte de cama") == 8 and cuenta("Placa del soporte de cama") == 16
    assert cuenta("Chumacera motriz") == 2 and cuenta("Placa porta-chumacera motriz") == 2
    assert cuenta("Tensor de carro") == 2 and cuenta("Tapa del tensor") == 2
    assert cuenta("Placa porta-tensor") == 2  # F1c (D11): el marco, a rosca en su placa
    assert cuenta("Tapa del eje motriz") == 1  # el otro extremo va al acople del motor
    assert cuenta("Motorreductor") == 1 and cuenta("Acople flexible") == 1
    assert cuenta("Base del motor") == 1 and cuenta("Ménsula del motor") == 1
    assert cuenta("Brazo de la base del motor") == 2
    assert cuenta("Guarda lateral") == 4 and cuenta("Guarda del tambor") == 2  # F1c: paños
    assert cuenta("Guarda del acople") == 1
    # v5 (cierres): guarda inferior en 2 tramos por lado y las placas de cierre de los largueros
    assert cuenta("Guarda inferior") == 4 and cuenta("Placa de cierre del larguero") == 4
    # v6 (faja-larga-en-tramos): 4 m entre tambores pasan los 3 m libres del ramal de retorno →
    # un rodillo de retorno con sus dos soportes y su guarda; el bastidor (4,3 m), en un tramo
    assert cuenta("Rodillo de retorno") == 1 and cuenta("Soporte del rodillo de retorno") == 2
    assert cuenta("Guarda del rodillo de retorno") == 1 and cuenta("Placa de empalme") == 0
    # F1b (criterio 7): tuerca soldada y contratuerca en cada pie
    assert cuenta("Tuerca soldada del pie") == 4 and cuenta("Contratuerca del pie") == 4
    assert len(d.scene) == 89


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
    assert {"TUBO-4X2", "TUBO-2X2", "TAMBOR-102", "TAMBOR-102-RET", "MOTOR-150-EH",
            "UCT205-150", "UCF205", "PIE-M12-50"} <= refs
    # los largueros: el largo entre tambores + el voladizo motriz (Ø/2 + engomado + banda + 40)
    # + el de cola (medio marco del tensor UCT205-150 + 15) + media carrera (75: desde el
    # criterio 9 de faja-compacta el carro sale al inicio y el marco va corrido hacia la cola)
    rows = {(r["ref"], r["longitud_mm"]): r["cantidad"] for r in bom_from_scene(d.scene)}
    assert rows[("TUBO-4X2", 4349.3)] == 2


def test_belt_conveyor_bom_separa_banda_y_cama():
    d, _ = _belt_doc()
    custom = [r for r in bom_from_scene(d.scene) if r["ref"] in ("A-MEDIDA", "COMPRA")]
    rows = {r["descripcion"].split(" · ")[-1]: r["cantidad"] for r in custom}
    # la banda se COMPRA (F6): categoría de compra; la cama se fabrica
    cats = {r["descripcion"].split(" · ")[-1]: r["categoria"] for r in custom}
    camas = [k for k in cats if k.startswith("Cama de deslizamiento")]
    assert cats["Banda"] == "bandas" and {cats[k] for k in camas} == {"a medida"}
    # piezas a medida DISTINTAS del mismo super-comando → filas separadas (no colapsan); F1c: la
    # cama en dos paños, una fila por paño
    assert rows["Banda"] == 1
    assert sorted(camas) == ["Cama de deslizamiento (paño 1)", "Cama de deslizamiento (paño 2)"]
    assert all(rows[k] == 1 for k in camas)


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
    # feature_mass redondea a 4 decimales
    assert fm["masa_kg"] == pytest.approx(belt.shape.volume * density("pvc"), abs=1e-4)
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


# ----------------------------------------------- v4: montaje, uniones y tensor (puerta de publicación)
#: El default y una variante de otro largo, ancho y altura (con el tensor de la v3 en el log).
VARIANTES = [{}, {"largo": 2500, "ancho_banda": 450, "altura": 750, "tensor": "TENSOR-TROT-25"}]


@pytest.fixture(scope="module", params=range(len(VARIANTES)), ids=["default", "variante"])
def faja_v4(request):
    return _belt_doc(**VARIANTES[request.param])


def test_v4_sin_choques_internos_ni_siquiera_entre_lo_declarado(faja_v4):
    """D13b de la puerta: la v3 chocaba por dentro (motor ↔ larguero 392 599 mm³, cama ↔ guardas,
    ejes por los largueros sin barreno…). La v4 no tiene NINGUNA pareja con volumen común, sin
    excluir nada (ni `same_command_pairs` ni las uniones declaradas): los ejes pasan por barrenos
    con holgura y los asientos (eje en el inserto, cubo del acople) son contactos de volumen 0."""
    d, _ = faja_v4
    r = interference_report(d.scene)
    assert not r["truncado"]
    assert [(i["a"], i["b"], i["volumen_mm3"]) for i in r["interferencias"]] == []


def test_v4_declara_sus_uniones_y_anclajes(faja_v4):
    """Todo lo que la plantilla toca entre sus piezas va DECLARADO por ella (perno lo
    desmontable, soldadura el marco, contacto los apoyos): cada pieza tiene unión y camino de
    carga a tierra por los pies niveladores, sin autodetección."""
    from apolo.assembly.connectivity import build_graph, soundness_report

    d, cid = faja_v4
    unidas = {f[k] for f in d.fasteners.values() for k in ("a", "b")}
    assert set(d.scene) <= unidas
    assert sorted(g["feature"] for g in d.grounds.values()) == [f"{cid}_foot{k}" for k in range(1, 5)]
    assert all(g["command_id"].startswith(f"{cid}_g_") for g in d.grounds.values())
    rep = soundness_report(build_graph(d.scene, d.joints, d.mates, d.fasteners, d.grounds))
    assert rep["floating"] == [] and rep["n_grounded"] == len(d.scene)
    tipos = {f["name"].split(f"{cid}_", 1)[1]: f["kind"] for f in d.fasteners.values()}
    guarda1 = next(k for k in tipos if k.startswith("guarda1") and k.endswith("_larg"))
    assert tipos[guarda1] == tipos["guarda_m_larg1"] == "perno"  # resguardos: con perno
    # se cambian sin cortar (F1c: el marco del tensor, a rosca en su placa porta-tensor)
    assert tipos["chum_m1_placa"] == tipos["tensor1_placa"] == "perno"
    assert tipos["larg_pata1"] == tipos["chum_m1_placa_sold"] == "soldadura"
    assert tipos["cama_sop1"] == tipos["sop1_m_larg"] == "perno"  # nada soldado abraza la banda
    assert tipos["banda_motriz"] == tipos["chum_m1_eje"] == "contacto"
    pernos = [f for f in d.fasteners.values() if f["kind"] == "perno"]
    soldaduras = [f for f in d.fasteners.values() if f["kind"] == "soldadura"]
    assert all(f.get("size") and f.get("qty") for f in pernos)
    assert all(f.get("throat_mm") and f.get("length_mm") for f in soldaduras)


def test_v4_bastidor_de_acero_explicito_no_por_el_nombre(faja_v4):
    """«larguero» es palabra de madera en la heurística del nombre: la memoria tomaba los
    largueros como madera (flecha 253,8 mm, NO CONFORME). La plantilla pone el material."""
    from apolo.library.materials import resolve_material
    from apolo.library.rules import _frame_from_scene

    d, cid = faja_v4
    for suf in ("rail1", "rail2", "leg1", "brace1", "sop1"):
        f = d.scene[f"{cid}_{suf}"]
        assert f.material and "acero" in f.material and "acero" in resolve_material(f)
    frame = _frame_from_scene(d.scene, {})
    assert "acero" in frame["material"]
    # el vano es el de las patas (por su ROL tras « · »), no el largo del larguero
    xs = sorted({round(d.scene[f"{cid}_leg{k}"].shape.bounding_box().center().X, 1)
                 for k in range(1, 5)})
    assert frame["span_mm"] == pytest.approx(xs[-1] - xs[0], abs=0.2)


def test_v4_tensor_de_carro_con_carrera_para_el_lazo(faja_v4):
    """El tensor de la plantilla es la unidad tensora de carro UCT de catálogo (tornillo
    estándar, carrera de ficha 150 mm), que reconoce la puerta: cubre 1 %·lazo + 20 mm. Un log
    con el tensor trotadora de la v3 regenera con la UCT del mismo eje."""
    from apolo.library.calidad.tensor import carrera_requerida
    from apolo.services.calidad_tensores import lazos

    d, cid = faja_v4
    (lz,) = lazos(d)
    assert {t["id"] for t in lz["tensores"]} == {f"{cid}_tensor1", f"{cid}_tensor2"}
    assert all(t["tipo"] == "catalogo" and t["carrera_mm"] == 150 for t in lz["tensores"])
    assert max(t["carrera_mm"] for t in lz["tensores"]) >= carrera_requerida("banda",
                                                                             lz["largo_mm"])
    assert d.scene[f"{cid}_tensor1"].component == "UCT205-150"


def test_v4_ejes_vivos_en_chumaceras_por_fuera_de_los_largueros():
    """Ningún eje entra al larguero sin barreno: el motriz cruza el alma por un barreno de
    Ø eje + 6 y apoya en dos UCF por fuera; el de cola, por la ranura de la carrera del tensor."""
    d, cid = _belt_doc()
    rail = d.scene[f"{cid}_rail2"].shape
    tm = d.scene[f"{cid}_tambor_motriz"].shape.bounding_box()
    y_out = rail.bounding_box().max.Y
    assert tm.max.Y > y_out and tm.min.Y < -y_out  # el eje atraviesa los dos largueros
    for suf in ("chum_m1", "chum_m2"):
        c = d.scene[f"{cid}_{suf}"]
        assert c.component == "UCF205" and abs(c.shape.bounding_box().center().Y) > y_out
    motor = d.scene[f"{cid}_motor"].shape.bounding_box()
    assert motor.min.Y > y_out  # el motorreductor no cruza el larguero: va por fuera, en su base


def test_v4_sin_tensor_la_cola_va_en_chumaceras_y_no_hay_tensado():
    from apolo.services.calidad_tensores import lazos

    d, cid = _belt_doc(tensor="ninguno")
    assert d.scene[f"{cid}_chum_c1"].component == "UCF205"
    assert interference_report(d.scene)["interferencias"] == []
    (lz,) = lazos(d)
    assert lz["tensores"] == []  # honesto: sin tensor, la puerta no lo inventa


def test_v4_un_log_v3_regenera_con_la_geometria_nueva():
    """Los params de un log v3 (trotadora, cola de eje fijo) regeneran en v4 sin error: la
    trotadora se monta como su UCT y el tambor de cola de eje fijo queda en el carro."""
    p = {"largo": 4000, "ancho_banda": 600, "altura": 900, "tensor": "TENSOR-TROT-25",
         "tambor_cola": "TAMBOR-102-COLA", "motor": "MOTOR-150-EH", "guardas": True}
    d = Document.from_apolo_bytes(_belt_doc(**p)[0].to_apolo_bytes())  # el log, releído
    assert d.commands[0]["params"]["tensor"] == "TENSOR-TROT-25"
    assert d.scene["c1_tensor1"].component == "UCT205-150"
    assert d.scene["c1_tambor_cola"].component == "TAMBOR-102-COLA"
    assert interference_report(d.scene)["interferencias"] == []
