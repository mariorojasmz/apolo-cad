"""`create_roller_conveyor`: el transportador de rodillos por cadena en UNA orden (plan
`docs/plans/plantilla-rodillos-cadena.md`, F2 / D1 y D3).

Las cotas son puras (`library/rodillos_cadena.py`) y se prueban sin OCCT; la máquina se arma
una vez por módulo (chica: 1 m, 10 rodillos) y se le exige lo que pidió la piloto: cero
interferencias entre piezas (ni siquiera las declaradas se solapan), puerta de entrega VERDE
con la llave entrando en las 20 tuercas, cadenas engranadas y la regla de cadenas viéndolas.
Los tres tamaños con gravedad (D3) van con `-m torture`: cuestan minutos.
"""

from __future__ import annotations

import math
import re

import pytest

from apolo.commands.exec_rodillos_cadena import comandos_efectivos
from apolo.commands.exec_transmision import medir_transmision
from apolo.commands.models_transmision import CreateChainParams
from apolo.commands.receta_rodillos_cadena import receta
from apolo.commands.registry import REGISTRY
from apolo.doc import Document
from apolo.doc.errors import DocumentError
from apolo.library import rodillos_cadena as rc
from apolo.library.catalog import build_component
from apolo.library.checks import hardware_ids
from apolo.library.delivery import VERDE, delivery_report
from apolo.library.transmision import (
    TOL_ESTIRADO_MM, centros_para_eslabones, estirado_lazo,
)
from apolo.services.delivery_inputs import delivery_inputs
from banco_guardas import interferencias_sin_tope


def _piloto(**kw) -> rc.Disposicion:
    p = dict(largo=2000, ancho_util=500, paso=95.25, rodillo="TUBOR-2", altura=750.4,
             carga_kg=100, motriz=True, motor="MOTOR-037")
    p.update(kw)
    return rc.disposicion(**p)


# ------------------------------------------------------------------ cotas (puras)
def test_el_paso_sale_de_la_cadena_1a1():
    assert rc.pasos_rodillo() == [95.25, 107.95, 120.65]
    for paso, n in zip(rc.pasos_rodillo(), rc.ESLABONES_RR):
        assert n % 2 == 0 and centros_para_eslabones(12.7, 15, 15, n) == pytest.approx(paso)


@pytest.mark.parametrize("ref", rc.MOTORES)
def test_las_medidas_del_motor_son_las_del_solido(ref):
    m = rc.motor_local(ref)
    b = build_component(ref)[0].bounding_box()
    assert (b.min.X, b.max.X) == pytest.approx((m.x_min, m.eje_fin), abs=1e-6)
    assert (b.min.Z, b.max.Z) == pytest.approx((m.z_pies, m.z_max), abs=1e-6)


def test_la_disposicion_de_la_piloto():
    d = _piloto()
    assert len(d.xs) == 20 and d.h_eje == pytest.approx(725.0)
    assert d.xs[0] == pytest.approx(d.largo - d.xs[-1])  # rodillos centrados
    assert d.eslabones_rr == 30
    assert [e.rol for e in d.estaciones] == ["alimentacion", "motriz"]
    assert d.estaciones[0].x == pytest.approx(d.largo - d.estaciones[1].x)  # mismo voladizo
    m = d.motriz
    assert m.eslabones % 2 == 0
    assert m.centros == pytest.approx(centros_para_eslabones(12.7, 30, 15, m.eslabones))
    assert math.hypot(d.xs[-1] - m.x, d.h_eje - m.z) == pytest.approx(m.centros)
    assert m.angulo_deg > 0  # inclinada hacia la alimentación
    # F4 (D7): corre sobre la línea de centros lo que pide el estirado de reemplazo (3 % / 2)
    assert m.tensado_mm == pytest.approx(0.015 * m.eslabones * 12.7)
    assert rc.holgura_motriz(d.paso, m.centros, m.angulo_deg) >= 5.0
    assert m.y + rc.motor_local(m.motor).x_min >= d.y_in_m + 15.0  # cabe entre las patas
    assert d.velocidad_m_s == pytest.approx(math.pi * 50.8 * 100 / 60000)
    assert d.potencia_req_kw < m.potencia_kw


@pytest.mark.parametrize("kw, texto", [
    ({"paso": 100}, "sólo cierran"),
    ({"ancho_util": 300}, "ancho_util mínimo"),
    ({"rodillo": "TUBOR-3"}, "entre tubos"),
    ({"carga_kg": 5000, "largo": 12000}, "motorreductor mayor"),
    ({"largo": 900}, "largo mínimo"),
    ({"altura": 300}, "altura"),
])
def test_lo_que_no_se_fabrica_falla_diciendo_que_cambiar(kw, texto):
    with pytest.raises(ValueError, match=texto):
        _piloto(**kw)


def test_un_bastidor_largo_lleva_estaciones_intermedias():
    d = _piloto(largo=6000, carga_kg=300)
    xs = [e.x for e in d.estaciones]
    assert len(xs) >= 4 and {e.rol for e in d.estaciones[1:-1]} == {"intermedia"}
    assert max(b - a for a, b in zip(xs, xs[1:])) <= d.vano_max + 1e-6
    assert d.vano_max <= rc.VANO_TOPE
    # mucha carga acorta el vano: flecha L/240 y σ ≤ 0.6·fy del ángulo libre
    assert rc.vano_maximo(10000, 0, 6000) < rc.VANO_TOPE
    libre = _piloto(largo=6000, carga_kg=10000, motriz=False, motor=None)
    assert len(libre.estaciones) > len(xs)


def test_la_receta_valida_y_sus_nombres_caben():
    d = _piloto()
    pasos, grupos = receta(d, "c12", "Transportador de rodillos", (100.0, -50.0, 0.0))
    ids = [f"c12_{suf}" for _, suf, _ in pasos]
    assert len(set(ids)) == len(ids)
    for tipo, _, params in pasos:
        REGISTRY[tipo].model.model_validate(params, extra="forbid")  # sin claves de más
        if tipo in ("fasten", "ground"):
            assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,39}", params["name"])
    con_piezas = {f"c12_{suf}" for tipo, suf, _ in pasos if tipo not in ("fasten", "ground",
                                                                         "drill_hole")}
    assert {m for ms in grupos.values() for m in ms} <= con_piezas
    assert sum(t == "create_chain" for t, _, _ in pasos) == len(d.xs)  # 19 lazos + la motriz


# ------------------------------------------------------------------ la máquina (OCCT)
@pytest.fixture(scope="module")
def chico():
    doc = Document("rodillos-cadena-chico")
    doc.execute("create_roller_conveyor", {"largo": 1000})
    return doc


def test_regenera_integro_y_determinista(chico):
    assert chico.check_integrity() == []
    assert len(chico.groups) == 7 and len(chico.grounds) == 4
    antes = {fid: f.shape.bounding_box().center() for fid, f in chico.scene.items()}
    chico.regenerate()
    assert chico.check_integrity() == []
    despues = {fid: f.shape.bounding_box().center() for fid, f in chico.scene.items()}
    assert antes.keys() == despues.keys()
    assert all((antes[k] - despues[k]).length < 1e-6 for k in antes)


def test_ninguna_pieza_se_mete_en_otra(chico):
    """Sin excluir lo declarado: ni las piezas unidas se solapan (tapas, buje y piñón, patas,
    guardas…). Sólo la tornillería (tuercas en la rosca) queda fuera, como en la puerta."""
    formas = {f: x.shape for f, x in chico.scene.items()}  # sin el tope de 400 parejas
    assert interferencias_sin_tope(formas, hardware_ids(chico)) == []


def test_la_puerta_de_entrega_da_verde(chico):
    rep = delivery_report(**delivery_inputs(chico, expand=lambda v: []))
    assert rep["veredicto"] == VERDE, rep
    assert rep["avisos"] == [] and rep["bloqueantes"] == []
    ok = rep["resumen"]["chequeos_ok"]
    # entra la llave en cada tuerca: las 4 soldadas de los pies (F5), sus 4 contratuercas y los 8
    # anclajes de expansión (F6); el eje hexagonal de F7 se calza, sin tuercas (con el M12 de F6
    # eran 40 más)
    assert "acceso de herramienta (16 fijador(es))" in ok
    assert "lints pre-entrega" in ok  # incluye el asiento en la zona plana del ángulo


def test_cada_cadena_engrana_sin_estirarse(chico):
    cadenas = [c for c in comandos_efectivos(chico.commands, chico.variables_resolved)
               if c["type"] == "create_chain"]
    assert len(cadenas) == 10
    for c in cadenas:
        t = medir_transmision(chico.scene, CreateChainParams.model_validate(c["params"]))
        estirado = estirado_lazo(t.paso, t.za, t.zb, t.centros, t.fase_a, t.fase_b, t.eslabones)
        assert estirado <= TOL_ESTIRADO_MM, c["id"]


def test_la_regla_de_cadenas_ve_las_de_la_plantilla(chico):
    from apolo.services.transmision_rules import chain_rules

    reglas = chain_rules(chico)
    nombres = [r["regla"] for r in reglas]
    assert any("Cadena motriz" in n for n in nombres)
    assert any("8 lazo(s) iguales" in n for n in nombres)  # los 9 rodillo a rodillo, en una
    assert all(r["estado"] != "error" for r in reglas)


def test_la_guarda_se_atornilla_a_la_rosca_de_cada_separador(chico):
    guarda = chico.scene["c1_guarda_cad"].shape
    for fid, f in chico.scene.items():
        if not re.fullmatch(r"c1_sep\d+", fid):
            continue
        b = f.shape.bounding_box()
        c = b.center()
        assert not guarda.is_inside((c.X, c.Y, b.max.Z + 1.0))  # el agujero de la guarda
        assert guarda.is_inside((c.X + 10.0, c.Y, b.max.Z + 1.0))
        assert not f.shape.is_inside((c.X, c.Y, b.max.Z - 5.0))  # la rosca M6 del separador


# (el tensado sobre ranuras de la base de F2 lo reemplazaron las orejas del portamotor, F4 D7:
# tests/test_plantilla_rodillos_f4.py)


# ------------------------------------------------------------------ edición y variantes
def test_libre_sin_transmision_y_simetrico():
    doc = Document("rodillos-libres")
    doc.execute("create_roller_conveyor", {"largo": 1000, "motriz": "libre"})
    nombres = " ".join(f.name for f in doc.scene.values())
    assert not re.search(r"Piñón|Cadena|Motorreductor|Guarda|motriz", nombres)
    assert "Pata (+Y, descarga)" in nombres
    m = doc.scene["c1_larg_m"].shape.bounding_box()
    p = doc.scene["c1_larg_p"].shape.bounding_box()
    assert m.min.Y == pytest.approx(-p.max.Y) and m.max.Y == pytest.approx(-p.min.Y)
    assert delivery_report(**delivery_inputs(doc, expand=lambda v: []))["veredicto"] == VERDE


def test_position_traslada_y_editar_regenera_todo():
    doc = Document("rodillos-edicion")
    doc.execute("create_roller_conveyor", {"largo": 1000, "motriz": "libre",
                                           "position": {"x": 300, "y": -100, "z": 50}})
    b = doc.scene["c1_pie_m_e0"].shape.bounding_box()  # F8: la base del pie, en el piso
    assert b.min.Z == pytest.approx(50.0)
    assert doc.scene["c1_larg_m"].shape.bounding_box().min.X == pytest.approx(300.0)
    n = len(doc.scene)
    doc.edit("c1", {"largo": 1500})
    assert len(doc.scene) > n and doc.check_integrity() == []
    doc.undo()
    assert len(doc.scene) == n


def test_dos_transportadores_y_el_nombre_es_unico():
    doc = Document("dos-transportadores")
    doc.execute("create_roller_conveyor", {"largo": 1000, "motriz": "libre", "name": "Entrada"})
    doc.execute("create_roller_conveyor", {"largo": 1000, "motriz": "libre", "name": "Salida",
                                           "position": {"x": 1200}})
    assert doc.check_integrity() == [] and {"Entrada", "Salida"} <= set(doc.groups)
    with pytest.raises(DocumentError, match="nombre único"):
        doc.execute("create_roller_conveyor", {"largo": 1000, "motriz": "libre",
                                               "name": "Entrada"})


def test_un_contrato_con_dolar_k_ve_sus_piezas():
    from apolo.services.assertions import contract_verify

    doc = Document("contrato")
    cb = contract_verify(doc, [{"tipo": "sin_interferencia", "ids": ["$1"]}],
                         expand=lambda v: [x for x in v if x in doc.scene])
    doc.execute_many([{"type": "create_roller_conveyor",
                       "params": {"largo": 1000, "motriz": "libre"}}], verify=cb)
    assert len(doc.scene) > 50


# ------------------------------------------------------------------ D3: tres tamaños con gravedad
@pytest.mark.torture
@pytest.mark.parametrize("params", [
    {"largo": 1000},
    {"largo": 2000, "altura": 750.4},
    {"largo": 3000, "velocidad_m_s": 0.25, "carga_kg": 200},  # la de F3, con las guardas de F4
    {"largo": 4000, "ancho_util": 800, "paso": 120.65, "rodillo": "TUBOR-3", "carga_kg": 400,
     "motor": "MOTOR-075", "altura": 900},
])
def test_tres_tamanos_verdes_con_gravedad(params):
    from fastapi.testclient import TestClient

    import apolo.api.main as api

    api.DOC = Document("rodillos-d3")
    client = TestClient(api.app)
    r = client.post("/api/commands", json={"type": "create_roller_conveyor", "params": params})
    assert r.status_code == 200, r.text
    rep = client.post("/api/delivery-check", json={"con_gravedad": True}).json()
    assert rep["veredicto"] == VERDE and rep["avisos"] == [], rep
    assert "gravedad" in rep["resumen"]["chequeos_ok"]
