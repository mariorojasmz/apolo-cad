"""`create_roller_conveyor` F6: lo que el revisor de taller ciego halló en la piloto de rodillos
por gravedad (plan `docs/plans/plantilla-rodillos-cadena.md`, § Bitácora F6, E1–E5).

- E1: los anclajes de cada placa de piso, de compra y por FUERA de la placa de la pata (entran el
  taladro y el dado);
- E2: contratuerca en el vástago de cada pie nivelador;
- E3: el eje trabado contra el ala entre la tuerca interior y la exterior, y el rodillo con juego
  axial acotado por los separadores;
- E4: el 6201 como línea de compra (2 por rodillo);
- E5: todo entra por el campo oculto `taller` que pone el sello de entrada; un log sin él
  regenera igual que la v3.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict

import pytest

from apolo.commands.registry import REGISTRY
from apolo.doc import Document
from apolo.library import rodillos_cadena as rc
from apolo.library.bom import bom_from_scene
from apolo.library.catalog import CATALOG
from apolo.library.delivery import VERDE, delivery_report
from apolo.library.rodillos_cadena_pies import ACCESO_ANCLAJE, ANCLAJE_REF, PLACA_PISO
from apolo.library.rodillos_cadena_reglas import reglas_rodillos_cadena
from apolo.services.delivery_inputs import delivery_inputs
from banco_guardas import interferencias_sin_tope

#: la piloto que revisó el revisor (rodillos por gravedad) y la de 3 m con cadena de F3–F5
LIBRE = {"largo": 1500, "ancho_util": 400, "paso": 75, "motriz": "libre"}
CADENA_3M = {"largo": 3000, "velocidad_m_s": 0.25, "carga_kg": 200}
LIBRE_3M = {"largo": 3000, "ancho_util": 400, "paso": 75, "motriz": "libre"}
#: E5: lo que da la v3 (sin `taller`), congelado ANTES de F6 (piezas, uniones y anclajes)
HUELLA_V3 = {"libre": (132, 168, "a9572ea8b195b3ea"), "cadena": (330, 430, "658a7ec8797884cd")}  # cadena: +1 unión (v4 de uniones-que-tocan)


def _doc(params: dict) -> Document:
    """La plantilla de F6 (un log con `taller` y sin `eje` ni `pie`: el M12 trabado y el disco
    soldado a la placa de piso). La de F7 (eje hexagonal) en `test_plantilla_rodillos_f7`; la de F8
    (pie con base de anclaje), en `test_plantilla_rodillos_f8`."""
    doc = Document("rodillos-f6")
    doc.execute("create_roller_conveyor", {"eje": "roscado", "pie": "disco", "motor": "MOTOR-037", "mantenimiento": False, **params})
    return doc


@pytest.fixture(scope="module")
def libre():
    return _doc(LIBRE)


@pytest.fixture(scope="module")
def cadena():
    return _doc(CADENA_3M)


@pytest.fixture(scope="module")
def libre_3m():
    return _doc(LIBRE_3M)


@pytest.fixture(params=["libre", "cadena", "libre_3m"])
def maquina(request):
    return request.getfixturevalue(request.param)


def _bb(doc, fid):
    b = doc.scene[fid].shape.bounding_box()
    return (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)


def _de(doc, prefijo: str) -> list[str]:
    """La pieza fuente y las copias de su patrón (`c1_sep_m`, `c1_sep_ms_3`…)."""
    return sorted(f for f in doc.scene if f == prefijo or f.startswith(prefijo + "s_"))


def _por_x(doc, prefijo: str) -> dict:
    return {round((_bb(doc, f)[0] + _bb(doc, f)[3]) / 2.0, 3): _bb(doc, f)
            for f in _de(doc, prefijo)}


def _bom(doc) -> dict:
    out = defaultdict(int)
    for fila in bom_from_scene(doc.scene, doc.default_material()):
        out[fila["ref"]] += fila["cantidad"]
    return out


def _huella(doc) -> tuple:
    piezas = sorted([fid, f.name, f.component or ""] for fid, f in doc.scene.items())
    uniones = sorted([u["name"], u["kind"], u["a"], u["b"], u.get("nota", "")]
                     for u in doc.fasteners.values())
    anclajes = sorted([g["feature"], g.get("nota", "")] for g in doc.grounds.values())
    s = json.dumps([piezas, uniones, anclajes], ensure_ascii=False)
    return len(piezas), len(uniones), hashlib.sha256(s.encode()).hexdigest()[:16]


# ------------------------------------------------------------------ E5: el sello
def test_el_comando_nuevo_nace_con_taller_y_el_campo_no_se_publica(libre):
    assert libre.commands[0]["params"]["taller"] is True  # el sello de entrada
    spec = REGISTRY["create_roller_conveyor"]
    assert "taller" not in spec.model.model_json_schema()["properties"]  # criterio de Apolo
    assert spec.version == 6  # entra por los params; v6 = oreja cerrada (v5: F9)
    viejo = _doc({**LIBRE, "taller": False})  # lo que el cliente trae se respeta
    assert viejo.commands[0]["params"]["taller"] is False


@pytest.mark.parametrize("caso, params", [("libre", LIBRE), ("cadena", CADENA_3M)])
def test_sin_el_sello_mismas_piezas_y_cotas_que_la_v3(caso, params):
    doc = _doc({**params, "taller": False})
    assert doc.check_integrity() == []
    assert _huella(doc) == HUELLA_V3[caso]
    placa = _bb(doc, "c1_placa_piso_m_e0")
    assert (placa[3] - placa[0], placa[4] - placa[1]) == pytest.approx((PLACA_PISO, PLACA_PISO))
    a2 = params.get("ancho_util", 500) / 2.0
    assert _bb(doc, "c1_larg_m")[4] == pytest.approx(-a2 - rc.HOLGURA_BASTIDOR)


# ------------------------------------------------------------------ E1: anclajes
def test_los_anclajes_quedan_fuera_de_la_placa_de_la_pata_y_en_la_bom(maquina):
    placas = sorted(f for f in maquina.scene if f.startswith("c1_placa_") and "piso" not in f)
    anclas = sorted(f for f in maquina.scene if f.startswith("c1_ancla_"))
    assert len(anclas) == 2 * len(placas) and _bom(maquina)[ANCLAJE_REF] == len(anclas)
    for placa in placas:
        sufijo = placa.removeprefix("c1_placa_")
        p = _bb(maquina, placa)
        for j in (0, 1):
            a = _bb(maquina, f"c1_ancla_{sufijo}{j}")
            ax, ay = (a[0] + a[3]) / 2.0, (a[1] + a[4]) / 2.0
            # el eje del anclaje, a ≥ ACCESO_ANCLAJE por fuera del borde de la placa de la pata
            fuera = max(p[0] - ax, ax - p[3], p[1] - ay, ay - p[4])
            assert fuera >= ACCESO_ANCLAJE - 1e-6, (placa, fuera)
            # apoya en la placa de piso y entra en el concreto
            piso = _bb(maquina, f"c1_placa_piso_{sufijo}")
            assert piso[0] < ax < piso[3] and a[2] < 0.0
        assert any(u["kind"] == "contacto" and {u["a"], u["b"]} == {f"c1_ancla_{sufijo}0",
                                                                    f"c1_placa_piso_{sufijo}"}
                   for u in maquina.fasteners.values())
    assert all("anclajes de expansión M12" in g["nota"] for g in maquina.grounds.values())


def test_entran_el_taladro_y_el_dado_sobre_cada_anclaje(libre):
    """Un cilindro de Ø50 (el porta-brocas SDS-plus del rotomartillo; el dado de la tuerca AF 19
    es menor) sobre cada anclaje, de su tuerca hacia arriba, no toca ninguna pieza."""
    from build123d import Cylinder, Pos

    tope = max(_bb(libre, f)[5] for f in libre.scene if f.startswith("c1_ancla_"))
    for f in (x for x in libre.scene if x.startswith("c1_ancla_")):
        a = _bb(libre, f)
        acceso = Pos((a[0] + a[3]) / 2.0, (a[1] + a[4]) / 2.0, tope + 151.0) * Cylinder(25.0, 300.0)
        for otra, feat in libre.scene.items():
            if otra != f:
                comun = acceso & feat.shape
                assert comun is None or float(comun.volume) < 1e-3, (f, otra)


# ------------------------------------------------------------------ E2: contratuerca
def test_cada_pie_lleva_su_contratuerca_contra_la_tuerca_soldada(maquina):
    pies = sorted(f for f in maquina.scene if f.startswith("c1_pie_"))
    rosca = CATALOG[maquina.scene[pies[0]].component].specs["rosca"]
    for pie in pies:
        sufijo = pie.removeprefix("c1_pie_")
        contra, tuerca = _bb(maquina, f"c1_contra_pie_{sufijo}"), _bb(maquina, f"c1_tuerca_pie_{sufijo}")
        assert contra[5] == pytest.approx(tuerca[2])  # apretada contra la tuerca soldada
        assert contra[2] > _bb(maquina, pie)[2]  # sobre el disco: queda rosca para nivelar
    assert _bom(maquina)[f"TUERCA-M{rosca:g}"] == 2 * len(pies)  # soldada + contratuerca


def test_engineering_check_publica_el_recorrido_con_la_contratuerca():
    params = {"largo": 3000, "ancho_util": 500, "paso": 95.25, "rodillo": "TUBOR-2",
              "altura": 750, "carga_kg": 200, "motriz": "cadena", "motor": "MOTOR-037",
              "velocidad_m_s": 0.25}
    pie = {r["regla"]: r for r in reglas_rodillos_cadena({**params, "taller": True}, 25, 400,
                                                         0.25, 400)}["pies niveladores"]
    assert pie["estado"] == "ok" and "contratuerca" in pie["detalle"]
    assert "contratuerca" in pie["calc"]["entradas"]["recorrido"]
    v3 = {r["regla"]: r for r in reglas_rodillos_cadena(params, 25, 400, 0.25, 400)}
    assert "contratuerca" not in json.dumps(v3["pies niveladores"], ensure_ascii=False)


# ------------------------------------------------------------------ E3 y E4: eje y 6201
def test_el_eje_queda_trabado_y_el_rodillo_con_juego_acotado(maquina):
    ym, yp = _bb(maquina, "c1_larg_m")[4], _bb(maquina, "c1_larg_p")[1]  # caras interiores
    t = float(CATALOG[rc.LARGUERO].specs["t"])
    tubos = _por_x(maquina, "c1_tubo")
    capas = {k: _por_x(maquina, f"c1_{k}") for k in (
        "tuerca_im", "tuerca_ip", "tuerca_m", "tuerca_p", "sep_m", "sep_p", "rod_m", "rod_p")}
    assert all(len(c) == len(tubos) for c in capas.values())
    for x in tubos:
        # tuerca interior contra la cara interior del ala y la exterior contra la de afuera
        assert capas["tuerca_im"][x][1] == pytest.approx(ym)
        assert capas["tuerca_ip"][x][4] == pytest.approx(yp)
        assert capas["tuerca_m"][x][4] == pytest.approx(ym - t)
        assert capas["tuerca_p"][x][1] == pytest.approx(yp + t)
        # el separador arranca en la tuerca interior y deja ≤ 2 mm al aro del 6201
        assert capas["sep_m"][x][1] == pytest.approx(capas["tuerca_im"][x][4])
        juego_m = capas["rod_m"][x][1] - capas["sep_m"][x][4]
        juego_p = capas["sep_p"][x][1] - capas["rod_p"][x][4]
        assert 0.0 < juego_m <= 2.0 and 0.0 < juego_p <= 2.0
        assert juego_m == pytest.approx(rc.JUEGO_AXIAL) == pytest.approx(juego_p)
    notas = {u["name"].rsplit("[", 1)[0]: u for u in maquina.fasteners.values()}
    assert "trabado" in notas["c1_eje_larg_m"]["nota"] and notas["c1_eje_larg_m"]["kind"] == "perno"
    assert notas["c1_tuerca_im"]["kind"] == notas["c1_sep_m"]["kind"] == "contacto"


def test_el_6201_es_una_linea_de_compra_y_la_tapa_lo_aloja(maquina):
    n = len(_de(maquina, "c1_tubo"))
    assert _bom(maquina)[rc.RODAMIENTO] == 2 * n
    s = CATALOG[rc.RODAMIENTO].specs
    for lado in ("m", "p"):
        rod, tapa = _bb(maquina, f"c1_rod_{lado}"), _bb(maquina, f"c1_tapa_{lado}")
        assert tapa[1] - 1e-6 <= rod[1] and rod[4] <= tapa[4] + 1e-6  # dentro del alojamiento
        assert rod[5] - rod[2] == pytest.approx(float(s["D"]))
    tapas = [f for f in bom_from_scene(maquina.scene, maquina.default_material())
             if "Tapa con alojamiento" in f["descripcion"]]
    assert tapas and all(f["ref"] == "A-MEDIDA" for f in tapas)


def test_lo_que_gira_no_toca_lo_fijo_del_lado_de_la_cadena(cadena):
    """El separador pasa por dentro del buje y del piñón (agujero Ø20): 2 mm de holgura."""
    sep = cadena.scene["c1_sep_p"].shape
    for gira in ("c1_buje", "c1_pinon", "c1_tapa_p"):
        assert sep.distance_to(cadena.scene[gira].shape) >= rc.JUEGO_AXIAL - 1e-6, gira
    assert sep.distance_to(cadena.scene["c1_buje"].shape) == pytest.approx(
        rc.HUECO_GIRA_R - rc.SEPARADOR_EJE_D / 2.0, abs=0.01)
    tuerca = cadena.scene["c1_tuerca_ip"].shape
    assert tuerca.distance_to(cadena.scene["c1_pinon"].shape) >= 3.0


# ------------------------------------------------------------------ sin interferencias
@pytest.mark.parametrize("nombre", ["libre", "cadena"])
def test_sin_interferencias_ni_siquiera_con_la_tornilleria(nombre, request):
    doc = request.getfixturevalue(nombre)
    assert doc.check_integrity() == []
    formas = {f: x.shape for f, x in doc.scene.items()}
    assert interferencias_sin_tope(formas, set()) == []


def test_tres_metros_todo_sigue_a_las_estaciones(cadena, libre_3m):
    for doc in (cadena, libre_3m):
        patas = [f for f in doc.scene if f.startswith("c1_pata_")]
        assert len(patas) == 6  # 3 estaciones
        assert len([f for f in doc.scene if f.startswith("c1_ancla_")]) == 12
        assert len([f for f in doc.scene if f.startswith("c1_contra_pie_")]) == 6
        assert len(doc.grounds) == 6


def test_la_puerta_de_entrega_da_verde_con_la_llave_en_cada_tuerca(libre):
    rep = delivery_report(**delivery_inputs(libre, expand=lambda v: []))
    assert rep["veredicto"] == VERDE and rep["avisos"] == [] and rep["bloqueantes"] == []
    # 18 rodillos × 4 tuercas + 4 soldadas + 4 contratuercas + 8 anclajes
    assert "acceso de herramienta (88 fijador(es))" in rep["resumen"]["chequeos_ok"]


@pytest.mark.torture
def test_la_piloto_libre_verde_con_gravedad():
    from fastapi.testclient import TestClient

    import apolo.api.main as api

    api.DOC = Document("rodillos-f6-gravedad")
    client = TestClient(api.app)
    r = client.post("/api/commands", json={"type": "create_roller_conveyor", "params": LIBRE})
    assert r.status_code == 200, r.text
    assert api.DOC.commands[0]["params"]["taller"] is True
    rep = client.post("/api/delivery-check", json={"con_gravedad": True}).json()
    assert rep["veredicto"] == VERDE and rep["avisos"] == [], rep
    assert "gravedad" in rep["resumen"]["chequeos_ok"]
