"""`create_roller_conveyor` F8: el pie anclado SIN soldar (plan
`docs/plans/plantilla-rodillos-cadena.md`, § Bitácora F8, E10).

Tres revisores de taller a ciegas objetaron el anclaje de F5–F7: el disco del pie nivelador
(acero ZINCADO) iba soldado a una placa de piso anclada (humos de zinc, cordón poroso) y, una vez
soldado, la altura no se re-nivela sin amolar. F8: con `anclaje`, el pie es uno con BASE DE
ANCLAJE (`PIE-BA-*`) anclado directo al concreto con los anclajes de expansión de F6 por sus 2
agujeros; sin placa de piso y sin soldadura al pie. Entra por el campo oculto `pie` que pone el
sello: un log F7 regenera igual.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from apolo.commands.registry import REGISTRY
from apolo.doc import Document
from apolo.library import rodillos_cadena as rc
from apolo.library.bom import bom_from_scene
from apolo.library.catalog import CATALOG, build_component
from apolo.library.delivery import VERDE, delivery_report
from apolo.library.rodillos_cadena_pies import ACCESO_ANCLAJE, ANCLAJE_REF, familias, pila
from apolo.library.rodillos_cadena_reglas import reglas_rodillos_cadena
from apolo.services.delivery_inputs import delivery_inputs
from banco_guardas import interferencias_sin_tope

LIBRE = {"largo": 1500, "ancho_util": 400, "paso": 75, "motriz": "libre"}
LIBRE_3M = {"largo": 3000, "ancho_util": 400, "paso": 75, "motriz": "libre"}
CADENA_3M = {"largo": 3000, "velocidad_m_s": 0.25, "carga_kg": 200}
#: lo que da F7 (`taller` + `eje` hexagonal, sin `pie`), congelado con el código de 7b8f891 ANTES
#: de F8: piezas, uniones y anclajes y la huella geométrica (volumen y caja de cada pieza)
HUELLA_F7 = {"libre": ((180, 216, "8ed34ff4fd67ae75"), "cbca8e7c8720adef"),
             "cadena": ((408, 507, "a4631ed75cc301e3"), "0b97be18ce16c990")}


def _doc(params: dict) -> Document:
    doc = Document("rodillos-f8")
    doc.execute("create_roller_conveyor", dict(params))
    return doc


@pytest.fixture(scope="module")
def libre():
    return _doc(LIBRE)


@pytest.fixture(scope="module")
def libre_3m():
    return _doc(LIBRE_3M)


@pytest.fixture(scope="module")
def cadena():
    return _doc(CADENA_3M)


@pytest.fixture(params=["libre", "libre_3m", "cadena"])
def maquina(request):
    return request.getfixturevalue(request.param)


def _bb(doc, fid):
    b = doc.scene[fid].shape.bounding_box()
    return (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)


def _de(doc, prefijo: str) -> list[str]:
    return sorted(f for f in doc.scene if f.startswith(prefijo))


def _huella(doc) -> tuple:
    piezas = sorted([fid, f.name, f.component or ""] for fid, f in doc.scene.items())
    uniones = sorted([u["name"], u["kind"], u["a"], u["b"], u.get("nota", "")]
                     for u in doc.fasteners.values())
    anclajes = sorted([g["feature"], g.get("nota", "")] for g in doc.grounds.values())
    s = json.dumps([piezas, uniones, anclajes], ensure_ascii=False)
    return len(piezas), len(uniones), hashlib.sha256(s.encode()).hexdigest()[:16]


def _geom(doc) -> str:
    filas = []
    for fid, f in sorted(doc.scene.items()):
        b = f.shape.bounding_box()
        filas.append([fid, round(float(f.shape.volume), 1)]
                     + [round(v, 2) for v in (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)])
    return hashlib.sha256(json.dumps(filas).encode()).hexdigest()[:16]


def _bom(doc) -> dict:
    return {f["ref"]: f["cantidad"] for f in bom_from_scene(doc.scene, doc.default_material())}


# ------------------------------------------------------------------ el sello
def test_el_comando_nuevo_nace_con_el_pie_de_base_y_el_campo_no_se_publica(libre):
    p = libre.commands[0]["params"]
    assert (p["pie"], p["eje"], p["taller"]) == ("base", "hexagonal", True)
    spec = REGISTRY["create_roller_conveyor"]
    assert "pie" not in spec.model.model_json_schema()["properties"]
    assert spec.version == 3  # entra por los params (cambia la firma): no hace falta subirla
    # un log F7 (con `taller` y `eje`, sin `pie`) lee «disco»; lo explícito se respeta
    assert spec.model.model_validate({**LIBRE, "taller": True, "eje": "hexagonal"}).pie == "disco"
    assert "pie" not in _doc({**LIBRE, "taller": False}).commands[0]["params"]
    with pytest.raises(Exception, match="taller"):
        _doc({**LIBRE, "taller": False, "pie": "base"})


@pytest.mark.parametrize("caso, params", [("libre", LIBRE), ("cadena", CADENA_3M)])
def test_un_log_f7_regenera_las_mismas_piezas_y_cotas(caso, params):
    doc = _doc({**params, "pie": "disco"})  # F7: sin `pie`
    assert doc.check_integrity() == []
    assert (_huella(doc), _geom(doc)) == HUELLA_F7[caso]


# ------------------------------------------------------------------ la ficha y la pila (puro)
@pytest.mark.parametrize("disco, base", list(zip(familias(), familias(True))))
def test_cada_pie_de_base_tiene_la_rosca_el_recorrido_y_la_carga_de_su_disco(disco, base):
    sd, sb = CATALOG[disco].specs, CATALOG[base].specs
    for k in ("rosca", "altura", "carga_kg", "disco_t"):
        assert sb[k] == sd[k], k
    assert sb["cotas_verificadas"] is False and sb["anclaje"] == ANCLAJE_REF
    assert float(sb["agujero_d"]) == float(CATALOG[ANCLAJE_REF].specs["df"])
    # del centro del agujero al canto de la base, ≥ 1,5 · Ø del agujero (EN 1993-1-8 tabla 3.3)
    canto = min((sb["base_l"] - sb["paso_agujeros"]) / 2.0, sb["base_b"] / 2.0)
    assert canto >= 1.5 * sb["agujero_d"]
    # la base cabe en el espesor que fija el anclaje
    assert sb["disco_t"] <= CATALOG[ANCLAJE_REF].specs["tfix_max"]
    p, q = pila(base, True, True, True), pila(disco, True, True)
    assert p.base and p.z_disco == 0.0 and q.z_disco > 0.0  # sin placa de piso
    assert p.recorrido == q.recorrido and p.z_pata0 == pytest.approx(q.z_pata0 - q.z_disco)
    # sin anclaje no cambia nada: el disco al piso
    assert pila(disco, False, True, True) == pila(disco, False, True)


def test_el_pie_de_base_es_un_solido_con_sus_dos_agujeros():
    s = CATALOG["PIE-BA-M8-30"].specs
    forma, _ = build_component("PIE-BA-M8-30", None)
    assert len(forma.solids()) == 1
    b = forma.bounding_box()
    assert (b.max.X - b.min.X, b.max.Y - b.min.Y, b.max.Z - b.min.Z) == pytest.approx(
        (s["base_l"], s["base_b"], s["altura"] + s["disco_t"]))
    import math

    lleno = (s["base_l"] * s["base_b"] * s["disco_t"] + math.pi * (s["rosca"] / 2.0) ** 2 * s["altura"])
    agujeros = 2.0 * math.pi * (s["agujero_d"] / 2.0) ** 2 * s["disco_t"]
    assert float(forma.volume) == pytest.approx(lleno - agujeros, rel=1e-3)


# ------------------------------------------------------------------ E10: sin placa de piso ni soldadura
def test_sin_placa_de_piso_ni_soldadura_al_pie(maquina):
    assert not [f for f in maquina.scene if "placa_piso" in f]
    pies = _de(maquina, "c1_pie_")
    assert pies and all(maquina.scene[f].component in familias(True) for f in pies)
    for u in maquina.fasteners.values():
        if set(pies) & {u["a"], u["b"]}:
            assert u["kind"] == "contacto", u["name"]
    # lo que ancla es la base del pie, apoyada en el piso
    assert sorted(g["feature"] for g in maquina.grounds.values()) == pies
    assert all("sin soldar" in g["nota"] and "sin tocar el anclaje" in g["nota"]
               for g in maquina.grounds.values())
    assert all(_bb(maquina, f)[2] == pytest.approx(0.0) for f in pies)
    # la tuerca del vástago sigue soldada a la placa de la pata: las dos, de acero negro
    notas = [u["nota"] for u in maquina.fasteners.values() if u["name"].startswith("c1_tuerca_placa_")]
    assert notas and all("negra (sin zincar)" in n and "acero negro" in n for n in notas)


def test_cada_base_lleva_sus_dos_anclajes_de_catalogo_fuera_de_la_placa_de_la_pata(maquina):
    pies, anclas = _de(maquina, "c1_pie_"), _de(maquina, "c1_ancla_")
    assert len(anclas) == 2 * len(pies) and _bom(maquina)[ANCLAJE_REF] == len(anclas)
    assert sum(n for r, n in _bom(maquina).items() if r in familias(True)) == len(pies)
    for pie in pies:
        sufijo = pie.removeprefix("c1_pie_")
        s = CATALOG[maquina.scene[pie].component].specs
        b, placa = _bb(maquina, pie), _bb(maquina, f"c1_placa_{sufijo}")
        cx, cy = (b[0] + b[3]) / 2.0, (b[1] + b[4]) / 2.0
        assert placa[3] - placa[0] == pytest.approx(s["paso_agujeros"] - 2.0 * ACCESO_ANCLAJE)
        xs = []
        for j in (0, 1):
            a = _bb(maquina, f"c1_ancla_{sufijo}{j}")
            ax, ay = (a[0] + a[3]) / 2.0, (a[1] + a[4]) / 2.0
            xs.append(ax - cx)
            assert ay == pytest.approx(cy) and a[2] < 0.0  # por el agujero, al concreto
            # el eje del anclaje, a ≥ ACCESO_ANCLAJE por fuera del borde de la placa de la pata
            fuera = max(placa[0] - ax, ax - placa[3], placa[1] - ay, ay - placa[4])
            assert fuera >= ACCESO_ANCLAJE - 1e-6
            assert any(u["kind"] == "contacto" and {u["a"], u["b"]} == {f"c1_ancla_{sufijo}{j}", pie}
                       for u in maquina.fasteners.values())
        assert sorted(xs) == pytest.approx([-s["paso_agujeros"] / 2.0, s["paso_agujeros"] / 2.0])


def test_entran_el_taladro_y_el_dado_sobre_cada_anclaje(libre):
    """Un cilindro de Ø50 (el porta-brocas SDS-plus; el dado AF 19 es menor) sobre cada anclaje,
    de su tuerca hacia arriba, no toca ninguna pieza (la cifra de F6)."""
    from build123d import Cylinder, Pos

    tope = max(_bb(libre, f)[5] for f in libre.scene if f.startswith("c1_ancla_"))
    for f in _de(libre, "c1_ancla_"):
        a = _bb(libre, f)
        acceso = Pos((a[0] + a[3]) / 2.0, (a[1] + a[4]) / 2.0, tope + 151.0) * Cylinder(25.0, 300.0)
        for otra, feat in libre.scene.items():
            if otra != f:
                comun = acceso & feat.shape
                assert comun is None or float(comun.volume) < 1e-3, (f, otra)


def test_el_techo_sigue_en_altura_y_la_pila_cierra(maquina):
    assert {round(_bb(maquina, f)[5], 3) for f in _de(maquina, "c1_tubo")} == {750.0}
    for pata in _de(maquina, "c1_pata_"):
        sufijo = pata.removeprefix("c1_pata_")
        p, pie = _bb(maquina, pata), _bb(maquina, f"c1_pie_{sufijo}")
        placa, tuerca = _bb(maquina, f"c1_placa_{sufijo}"), _bb(maquina, f"c1_tuerca_pie_{sufijo}")
        contra = _bb(maquina, f"c1_contra_pie_{sufijo}")
        assert placa[5] == pytest.approx(p[2]) and tuerca[5] == pytest.approx(placa[2])
        assert contra[5] == pytest.approx(tuerca[2]) and contra[2] > pie[2]
        for i in (0, 1):  # el pie, coaxial con la pata
            assert (pie[i] + pie[i + 3]) / 2.0 == pytest.approx((p[i] + p[i + 3]) / 2.0)


def test_engineering_check_dice_que_se_re_nivela_sin_tocar_el_anclaje():
    params = {"largo": 3000, "ancho_util": 500, "paso": 95.25, "rodillo": "TUBOR-2",
              "altura": 750, "carga_kg": 200, "motriz": "cadena", "motor": "MOTOR-037",
              "velocidad_m_s": 0.25, "taller": True, "eje": "hexagonal"}
    f8 = {r["regla"]: r for r in reglas_rodillos_cadena({**params, "pie": "base"}, 25, 400, 0.25,
                                                        400)}["pies niveladores"]
    assert f8["estado"] == "ok" and "sin tocar el anclaje" in f8["detalle"]
    assert f8["calc"]["entradas"]["pie"].startswith("PIE-BA-")
    f7 = {r["regla"]: r for r in reglas_rodillos_cadena(params, 25, 400, 0.25, 400)}
    assert "placas de piso" in f7["pies niveladores"]["detalle"]


# ------------------------------------------------------------------ estaciones, interferencias, puerta
def test_tres_metros_todo_sigue_a_las_estaciones(cadena, libre_3m):
    for doc in (cadena, libre_3m):
        assert len(_de(doc, "c1_pata_")) == 6  # 3 estaciones
        assert len(_de(doc, "c1_ancla_")) == 12 and len(_de(doc, "c1_pie_")) == 6
        assert len(_de(doc, "c1_contra_pie_")) == 6 and len(doc.grounds) == 6


@pytest.mark.parametrize("nombre", ["libre", "libre_3m", "cadena"])
def test_sin_interferencias_ni_siquiera_con_la_tornilleria(nombre, request):
    doc = request.getfixturevalue(nombre)
    assert doc.check_integrity() == []
    formas = {f: x.shape for f, x in doc.scene.items()}
    assert interferencias_sin_tope(formas, set()) == []


def test_la_puerta_de_entrega_da_verde_con_la_llave_en_cada_tuerca(libre):
    rep = delivery_report(**delivery_inputs(libre, expand=lambda v: []))
    assert rep["veredicto"] == VERDE and rep["avisos"] == [] and rep["bloqueantes"] == []
    # 4 tuercas soldadas + 4 contratuercas + 8 anclajes de las bases
    assert "acceso de herramienta (16 fijador(es))" in rep["resumen"]["chequeos_ok"]


def test_la_masa_estimada_queda_del_lado_seguro(cadena):
    from apolo.library.engineering.mass import scene_mass_properties

    real = scene_mass_properties(cadena.scene, include_hidden=True)["total"]["masa_kg"]
    d = rc.disposicion(3000, 500, 95.25, "TUBOR-2", 750, 200, True, "MOTOR-037", 0.25, True, True,
                       "hexagonal", "base")
    assert d.pies.base and d.pies.masa_kg >= real


@pytest.mark.torture
@pytest.mark.parametrize("params", [LIBRE, CADENA_3M])
def test_verde_con_gravedad(params):
    from fastapi.testclient import TestClient

    import apolo.api.main as api

    api.DOC = Document("rodillos-f8-gravedad")
    client = TestClient(api.app)
    r = client.post("/api/commands", json={"type": "create_roller_conveyor", "params": params})
    assert r.status_code == 200, r.text
    assert api.DOC.commands[0]["params"]["pie"] == "base"
    rep = client.post("/api/delivery-check", json={"con_gravedad": True}).json()
    assert rep["veredicto"] == VERDE and rep["avisos"] == [], rep
    assert "gravedad" in rep["resumen"]["chequeos_ok"]
