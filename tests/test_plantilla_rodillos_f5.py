"""`create_roller_conveyor` v3: pie nivelador de catálogo en cada pata (plan
`docs/plans/plantilla-rodillos-cadena.md`, F5 — D10).

La máquina de prueba es la de F3/F4 (3 m, ficha de 0.25 m/s, paquetes de 400 mm y 25 kg). Lo
puro (pila del pie, familia por carga, regla de `engineering_check`) se prueba sin OCCT.
"""

from __future__ import annotations

import pytest

from apolo.commands.registry import REGISTRY
from apolo.doc import Document
from apolo.library import rodillos_cadena as rc
from apolo.library.catalog import CATALOG
from apolo.library.checks import hardware_ids
from apolo.library.engineering.mass import scene_mass_properties
from apolo.library.rodillos_cadena_pies import IMPACTO, PLACA_PISO_T, familias, pila
from apolo.library.rodillos_cadena_reglas import reglas_rodillos_cadena
from banco_guardas import interferencias_sin_tope

PARAMS_3M = {"largo": 3000, "velocidad_m_s": 0.25, "carga_kg": 200}
FICHA = {"carga_kg": 25, "largo_paquete_mm": 400, "ancho_paquete_mm": 400, "velocidad_m_s": 0.25}
REGLA = {"largo": 3000, "ancho_util": 500, "paso": 95.25, "rodillo": "TUBOR-2", "altura": 750,
         "carga_kg": 200, "motriz": "cadena", "motor": "MOTOR-037", "velocidad_m_s": 0.25}


def _disp(**kw) -> rc.Disposicion:
    p = dict(largo=3000, ancho_util=500, paso=95.25, rodillo="TUBOR-2", altura=750,
             carga_kg=200, motriz=True, motor="MOTOR-037", velocidad_m_s=0.25)
    p.update(kw)
    return rc.disposicion(**p)


def _bb(shape):
    b = shape.bounding_box()
    return (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)


@pytest.fixture(scope="module")
def tres():
    doc = Document("rodillos-3m-pies")
    doc.execute("create_roller_conveyor", PARAMS_3M)
    doc.set_requirements(dict(FICHA))
    return doc


# ------------------------------------------------------------------ la pila del pie (puro)
@pytest.mark.parametrize("ref", familias())
@pytest.mark.parametrize("anclaje", [True, False])
def test_el_pie_queda_a_la_mitad_de_su_recorrido(ref, anclaje):
    """Recorrido = vástago − tuerca: en la punta alta el vástago engrana la tuerca entera; en la
    baja el disco toca la tuerca. A la mitad, el disco queda a recorrido/2 de la tuerca."""
    p = pila(ref, anclaje)
    assert p.z_disco == (PLACA_PISO_T if anclaje else 0.0)
    disco_top = p.z_disco + p.disco_t
    tuerca0 = p.z_tuerca - p.tuerca_t / 2.0
    assert tuerca0 - disco_top == pytest.approx(p.recorrido / 2.0)
    assert p.recorrido == pytest.approx(p.vastago - p.tuerca_t)
    assert p.z_placa == pytest.approx(tuerca0 + p.tuerca_t)  # soldada bajo la placa
    assert p.z_pie - p.vastago / 2.0 == pytest.approx(disco_top)  # el vástago nace del disco
    assert p.barreno > p.rosca  # paso del vástago por la placa de la pata


def test_la_familia_sale_de_la_carga_por_pata():
    """La menor que lleva (masa + carga) / patas × 1.5; mucha carga sube de familia y, si
    ninguna alcanza, queda la mayor (la regla lo da en error, el log sigue regenerando)."""
    d = _disp()
    p = d.pies
    assert p.n == 2 * len(d.estaciones) == 6
    assert p.por_pie_kg == pytest.approx((p.masa_kg + 200) / 6 * IMPACTO)
    assert p.por_pie_kg <= p.capacidad_kg == CATALOG[p.ref].specs["carga_kg"]
    menores = familias()[:familias().index(p.ref)]
    assert all(CATALOG[r].specs["carga_kg"] < p.por_pie_kg for r in menores)
    pesado = _disp(carga_kg=600, motor="MOTOR-075", ancho_util=600, velocidad_m_s=None)
    assert familias().index(pesado.pies.ref) > familias().index(p.ref)
    nadie = _disp(carga_kg=2000, motor="MOTOR-150", ancho_util=700, velocidad_m_s=None)
    assert nadie.pies.ref == familias()[-1] and nadie.pies.por_pie_kg > nadie.pies.capacidad_kg


def test_la_altura_de_trabajo_no_cambia_y_la_pata_se_acorta():
    d = _disp()
    ala = float(CATALOG[rc.LARGUERO].specs["leg"])
    assert d.h_eje + d.d_rodillo / 2.0 == pytest.approx(750.0)
    assert d.pies.z_pata0 + d.pata_largo == pytest.approx(d.z_larguero - ala / 2.0)
    sin = _disp(anclaje=False)
    assert sin.pata_largo == pytest.approx(d.pata_largo + PLACA_PISO_T)  # sin placa de piso


def test_engineering_check_publica_la_carga_por_pie_y_el_recorrido():
    reglas = {r["regla"]: r for r in reglas_rodillos_cadena(REGLA, 25, 400, 0.25, 400)}
    pie = reglas["pies niveladores"]
    assert pie["estado"] == "ok" and pie["calc"]["fs"] >= 1.0
    d = _disp()
    assert f"±{d.pies.recorrido / 2.0:.1f} mm" in pie["detalle"]
    assert d.pies.ref in pie["detalle"] and "ancladas" in pie["detalle"]
    sin = {r["regla"]: r for r in reglas_rodillos_cadena({**REGLA, "anclaje": False}, 25, 400)}
    assert "directo al piso" in sin["pies niveladores"]["detalle"]
    # ninguno alcanza → error que dice qué hacer
    mucho = {r["regla"]: r for r in reglas_rodillos_cadena(
        {**REGLA, "carga_kg": 2000, "motor": "MOTOR-150", "ancho_util": 700, "velocidad_m_s": None},
        25, 400)}
    assert mucho["pies niveladores"]["estado"] == "error"
    assert mucho["pies niveladores"]["recomendacion"]


# ------------------------------------------------------------------ la máquina de 3 m (OCCT)
def test_tres_metros_sin_interferencias(tres):
    assert tres.check_integrity() == []
    formas = {f: x.shape for f, x in tres.scene.items()}
    assert interferencias_sin_tope(formas, hardware_ids(tres)) == []


def test_el_techo_del_rodillo_sigue_en_altura_y_el_pie_apoya(tres):
    d = _disp()
    tubos = [x for f, x in tres.scene.items() if f.startswith("c1_tubo")]
    assert {round(_bb(x.shape)[5], 3) for x in tubos} == {750.0}
    patas = [f for f in tres.scene if f.startswith("c1_pata_")]
    assert len(patas) == d.pies.n
    for f in patas:
        sufijo = f.removeprefix("c1_pata_")
        pata, pie = _bb(tres.scene[f].shape), _bb(tres.scene[f"c1_pie_{sufijo}"].shape)
        piso = _bb(tres.scene[f"c1_placa_piso_{sufijo}"].shape)
        tuerca = _bb(tres.scene[f"c1_tuerca_pie_{sufijo}"].shape)
        placa = _bb(tres.scene[f"c1_placa_{sufijo}"].shape)
        assert piso[2] == pytest.approx(0.0) and pie[2] == pytest.approx(piso[5])
        assert tuerca[5] == pytest.approx(placa[2]) and placa[5] == pytest.approx(pata[2])
        # el pie, coaxial con la pata
        for i in (0, 1):
            assert (pie[i] + pie[i + 3]) / 2.0 == pytest.approx((pata[i] + pata[i + 3]) / 2.0)
        assert tres.scene[f"c1_pie_{sufijo}"].component == d.pies.ref
        assert tres.scene[f"c1_pie_{sufijo}"].name.endswith(
            "Pie nivelador " + tres.scene[f].name.split("Pata ", 1)[1])


def test_cada_pie_lleva_menos_que_su_carga(tres):
    """Con la masa REAL del modelo (no la estimada) y la carga de la plantilla, × 1.5."""
    d = _disp()
    real = scene_mass_properties(tres.scene, include_hidden=True)["total"]["masa_kg"]
    assert d.pies.masa_kg >= real  # la estimada queda del lado seguro
    pies = [x for f, x in tres.scene.items() if f.startswith("c1_pie_")]
    por_pie = (real + PARAMS_3M["carga_kg"]) / len(pies) * IMPACTO
    for x in pies:
        assert por_pie <= CATALOG[x.component].specs["carga_kg"]


def test_uniones_y_anclajes_de_cada_pata(tres):
    assert len(tres.grounds) == 6
    assert all(g["feature"].startswith("c1_placa_piso_") for g in tres.grounds.values())
    tipos = {f["name"].removeprefix("c1_").rsplit("_", 2)[0]: f["kind"]
             for f in tres.fasteners.values() if "_e" in f["name"]}
    assert tipos["tuerca_placa"] == "soldadura" and tipos["pie_tuerca"] == "contacto"
    assert tipos["pie_piso"] == "soldadura" and tipos["placa_pata"] == "soldadura"


def test_sin_anclaje_el_disco_apoya_en_el_piso():
    doc = Document("rodillos-sin-anclaje")
    doc.execute("create_roller_conveyor", {"largo": 1000, "motriz": "libre", "anclaje": False})
    assert doc.check_integrity() == []
    assert not any(f.startswith("c1_placa_piso_") for f in doc.scene)
    assert all(g["feature"].startswith("c1_pie_") for g in doc.grounds.values())
    assert min(_bb(x.shape)[2] for x in doc.scene.values()) == pytest.approx(0.0)
    tubo = _bb(doc.scene["c1_tubo"].shape)
    assert tubo[5] == pytest.approx(750.0)
    formas = {f: x.shape for f, x in doc.scene.items()}
    assert interferencias_sin_tope(formas, hardware_ids(doc)) == []


def test_engineering_check_por_la_api(tres):
    from fastapi.testclient import TestClient

    import apolo.api.main as api

    api.DOC = tres
    rep = TestClient(api.app).post("/api/checks", json={"interference_ids": ["c1_motor"]}).json()
    reglas = {r["regla"]: r for r in rep["ingenieria"]}
    assert reglas["pies niveladores"]["estado"] == "ok"
    assert "±" in reglas["pies niveladores"]["detalle"]


# ------------------------------------------------------------------ log v2 y caché
def test_un_log_v2_sigue_regenerando_y_la_version_sube_a_3(monkeypatch):
    from apolo.doc.document import _cmd_sig

    doc = Document("v2")  # los params de un log v2: sin anclaje
    doc.execute("create_roller_conveyor", {"largo": 1000, "velocidad_m_s": 0.25})
    assert doc.check_integrity() == []
    assert any(f.startswith("c1_pie_") for f in doc.scene)
    assert any(f.startswith("c1_placa_piso_") for f in doc.scene)  # anclaje: True por defecto
    cmd = {"id": "c1", "type": "create_roller_conveyor", "params": {"largo": 1000}}
    assert REGISTRY["create_roller_conveyor"].version == 3
    v3 = _cmd_sig("", cmd)
    monkeypatch.setattr(REGISTRY["create_roller_conveyor"], "version", 2)
    assert _cmd_sig("", cmd) != v3


@pytest.mark.torture
def test_sin_anclaje_verde_con_gravedad():
    from fastapi.testclient import TestClient

    import apolo.api.main as api
    from apolo.library.delivery import VERDE

    api.DOC = Document("rodillos-f5")
    client = TestClient(api.app)
    r = client.post("/api/commands", json={"type": "create_roller_conveyor",
                                           "params": {"largo": 2000, "anclaje": False}})
    assert r.status_code == 200, r.text
    rep = client.post("/api/delivery-check", json={"con_gravedad": True}).json()
    assert rep["veredicto"] == VERDE and rep["avisos"] == [], rep
    assert "gravedad" in rep["resumen"]["chequeos_ok"]
