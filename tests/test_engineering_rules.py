"""Tests de las reglas de ingeniería nuevas (Frente A, Fase 4): chequeo
estructural universal (pernos/soldaduras/L10/pandeo/vuelco), `_check(calc=...)`
retrocompatible y rama banda-sobre-cama."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc.document import Document
from apolo.library.engineering.bolts import bolt_shear_capacity_n
from apolo.library.engineering.report import structure_engineering_check
from apolo.library.rules import _check, conveyor_engineering_check


def _box(doc, name, size=100, x=0.0, z=0.0):
    return doc.execute("create_box", {"name": name, "width": size, "depth": size,
                                      "height": size, "position": {"x": x, "y": 0, "z": z}})


def _structure(doc, **kw):
    return structure_engineering_check(
        doc.scene, doc.fasteners, doc.grounds, doc.joints, doc.mates, **kw
    )


def _rule(checks, prefix):
    return next((c for c in checks if c["regla"].startswith(prefix)), None)


# --------------------------------------------------------------- _check(calc)
def test_check_without_calc_is_byte_identical():
    assert _check("x", "ok", "d") == {"regla": "x", "estado": "ok", "detalle": "d"}


def test_check_with_calc_adds_key():
    c = _check("x", "ok", "d", calc={"titulo": "T", "fs": 2.0})
    assert c["calc"]["fs"] == 2.0


# ------------------------------------------------------------ uniones apernadas
def test_bolted_joint_exact_utilization():
    doc = Document("t")
    base = _box(doc, "Base", 100, z=50)
    motor = _box(doc, "Bloque colgante", 100, z=150)  # acero 7.85 kg
    doc.execute("ground", {"name": "g1", "feature": base})
    doc.execute("fasten", {"name": "f1", "a": base, "b": motor, "size": "M10", "qty": 2})
    checks = _structure(doc)
    rule = _rule(checks, "unión apernada")
    assert rule["estado"] == "ok"
    util_expected = 7.85 * 9.81 / (2 * bolt_shear_capacity_n("M10"))
    assert rule["calc"]["fs"] == pytest.approx(1.0 / util_expected, rel=0.02)


def test_bolted_joint_overloaded_is_error():
    doc = Document("t")
    base = _box(doc, "Base", 100, z=50)
    bloque = _box(doc, "Tanque", 1000, z=700)  # acero 1000³ = 7850 kg
    doc.execute("ground", {"name": "g1", "feature": base})
    doc.execute("fasten", {"name": "f1", "a": base, "b": bloque, "size": "M6", "qty": 1})
    rule = _rule(_structure(doc), "unión apernada")
    assert rule["estado"] == "error"


def test_bolted_joints_without_size_aggregate_warning():
    # las uniones sin métrica se AGREGAN en una regla-resumen (no un aviso por unión)
    doc = Document("t")
    base = _box(doc, "Base", 100, z=50)
    motor = _box(doc, "Motor", 100, z=150)
    tapa = _box(doc, "Tapa", 100, z=250)
    doc.execute("ground", {"name": "g1", "feature": base})
    doc.execute("fasten", {"name": "f1", "a": base, "b": motor})
    doc.execute("fasten", {"name": "f2", "a": motor, "b": tapa})
    checks = _structure(doc)
    assert _rule(checks, "unión apernada") is None  # sin reglas individuales
    rule = _rule(checks, "uniones apernadas sin dimensionar")
    assert rule["estado"] == "aviso"
    assert "2 unión" in rule["detalle"] and "f1" in rule["detalle"]


def test_parallel_fasteners_same_pair_combine_bolts():
    # dos `fasten` sobre el MISMO par = una unión con los pernos sumados (2+2=4)
    doc = Document("t")
    base = _box(doc, "Base", 100, z=50)
    motor = _box(doc, "Motor", 100, z=150)
    doc.execute("ground", {"name": "g1", "feature": base})
    doc.execute("fasten", {"name": "f1", "a": base, "b": motor, "size": "M10", "qty": 2})
    doc.execute("fasten", {"name": "f2", "a": base, "b": motor, "size": "M10", "qty": 2})
    rules = [c for c in _structure(doc) if c["regla"].startswith("unión apernada")]
    assert len(rules) == 2
    for r in rules:
        assert r["estado"] == "ok"
        assert "4× M10" in r["detalle"]


def test_redundant_path_is_ok_with_honest_detail():
    # el motor cuelga por DOS caminos distintos (dos vigas): la redundancia es
    # FAVORABLE y no accionable → "ok" con nota honesta (reparto indeterminado)
    doc = Document("t")
    base = _box(doc, "Base", 100, z=50)
    v1 = _box(doc, "Viga A", 100, x=-100, z=150)
    v2 = _box(doc, "Viga B", 100, x=100, z=150)
    motor = _box(doc, "Motor", 100, z=250)
    doc.execute("ground", {"name": "g1", "feature": base})
    doc.execute("fasten", {"name": "b1", "a": base, "b": v1, "size": "M10", "qty": 2})
    doc.execute("fasten", {"name": "b2", "a": base, "b": v2, "size": "M10", "qty": 2})
    doc.execute("fasten", {"name": "m1", "a": v1, "b": motor, "size": "M10", "qty": 2})
    doc.execute("fasten", {"name": "m2", "a": v2, "b": motor, "size": "M10", "qty": 2})
    checks = _structure(doc)
    m_rules = [c for c in checks if c["regla"] in ("unión apernada · m1", "unión apernada · m2")]
    assert len(m_rules) == 2
    assert all(c["estado"] == "ok" and "redundante" in c["detalle"] for c in m_rules)


# ------------------------------------------------------------------ soldaduras
def test_weld_undersized_is_error():
    doc = Document("t")
    base = _box(doc, "Base", 100, z=50)
    bloque = _box(doc, "Tolva", 1000, z=700)  # 7850 kg
    doc.execute("ground", {"name": "g1", "feature": base})
    doc.execute("fasten", {"name": "w1", "a": base, "b": bloque, "kind": "soldadura",
                           "throat_mm": 1, "length_mm": 10})
    rule = _rule(_structure(doc), "soldadura")
    assert rule["estado"] == "error"
    assert rule["calc"]["fs"] < 1


def test_weld_without_throat_aggregate_warning():
    doc = Document("t")
    base = _box(doc, "Base", 100, z=50)
    motor = _box(doc, "Motor", 100, z=150)
    doc.execute("ground", {"name": "g1", "feature": base})
    doc.execute("fasten", {"name": "w1", "a": base, "b": motor, "kind": "soldadura"})
    rule = _rule(_structure(doc), "soldaduras sin dimensionar")
    assert rule["estado"] == "aviso"
    assert "w1" in rule["detalle"]


# ---------------------------------------------------------------------- L10
def test_bearing_l10_from_catalog():
    doc = Document("t")
    doc.execute("insert_component", {"component": "UCP205", "position": {"x": 0, "y": 0, "z": 0}})
    checks = _structure(doc, carga_kg=100.0, rpm=100.0)
    rule = _rule(checks, "vida L10")
    assert rule["estado"] == "ok"
    # P = 100·9.81/1000/1 = 0.981 kN, C=14 → L10h = (14/0.981)³·1e6/6000
    expected = (14.0 / 0.981) ** 3 * 1e6 / 6000.0
    hours = float(rule["calc"]["resultado"].split("=")[1].strip().split(" ")[0].replace(",", ""))
    assert hours == pytest.approx(expected, rel=0.02)


def test_bearing_l10_without_rpm_is_warning():
    doc = Document("t")
    doc.execute("insert_component", {"component": "6207", "position": {"x": 0, "y": 0, "z": 0}})
    rule = _rule(_structure(doc, carga_kg=100.0), "vida L10")
    assert rule["estado"] == "aviso"


def test_bearing_l10_overloaded_is_error():
    doc = Document("t")
    doc.execute("insert_component", {"component": "6204", "position": {"x": 0, "y": 0, "z": 0}})
    # P = 20000·9.81/1000 = 196 kN ≫ C=12.7 → vida ínfima
    rule = _rule(_structure(doc, carga_kg=20000.0, rpm=500.0), "vida L10")
    assert rule["estado"] == "error"


# -------------------------------------------------------------------- pandeo
def test_slender_leg_buckling_error():
    doc = Document("t")
    doc.execute("create_box", {"name": "Pata esbelta", "width": 20, "depth": 20,
                               "height": 2000, "position": {"x": 0, "y": 0, "z": 1000}})
    doc.execute("create_box", {"name": "Tanque pesado", "width": 500, "depth": 500,
                               "height": 500, "position": {"x": 0, "y": 0, "z": 2250}})
    rule = _rule(_structure(doc), "pandeo")
    assert rule["estado"] == "error"
    assert rule["calc"]["fs"] < 2


def test_stout_leg_buckling_ok():
    doc = Document("t")
    doc.execute("create_box", {"name": "Pata 80x80x3", "width": 80, "depth": 80,
                               "height": 700, "position": {"x": 0, "y": 0, "z": 350}})
    rule = _rule(_structure(doc), "pandeo")
    assert rule["estado"] == "ok"


# --------------------------------------------------------------------- vuelco
def test_cog_outside_base_is_error():
    doc = Document("t")
    base = _box(doc, "Placa base", 100, z=50)
    doc.execute("create_box", {"name": "Contrapeso lejano", "width": 500, "depth": 500,
                               "height": 500, "position": {"x": 800, "y": 0, "z": 400}})
    doc.execute("ground", {"name": "g1", "feature": base})
    rule = _rule(_structure(doc), "estabilidad al vuelco")
    assert rule["estado"] == "error"


def test_cog_inside_base_is_ok():
    doc = Document("t")
    base = doc.execute("create_box", {"name": "Placa base", "width": 1000, "depth": 1000,
                                      "height": 20, "position": {"x": 0, "y": 0, "z": 10}})
    _box(doc, "Torre", 100, z=200)
    doc.execute("ground", {"name": "g1", "feature": base})
    rule = _rule(_structure(doc), "estabilidad al vuelco")
    assert rule["estado"] == "ok"
    assert rule["calc"]["fs"] > 1


def test_no_grounds_tipping_warning():
    doc = Document("t")
    _box(doc, "Caja", 100, z=50)
    rule = _rule(_structure(doc), "estabilidad al vuelco")
    assert rule["estado"] == "aviso"


# ------------------------------------------------------------- banda vs rodillos
def _p_req(checks) -> float:
    rule = _rule(checks, "motorización")
    m = re.search(r"P requerida = ([\d.]+) kW", rule["calc"]["resultado"])
    return float(m.group(1))


def test_belt_on_bed_needs_more_power_than_rollers():
    base = {"largo": 4000, "ancho": 600, "altura": 800, "paso": 300,
            "rodillo": "RODILLO-50", "motor": "MOTOR-150", "tambor_d": 114,
            "rpm_motor": 58, "torque_Nm": 156}
    rodillos = conveyor_engineering_check({**base, "tipo": "rodillos"}, 30, 600, 0.35)
    banda = conveyor_engineering_check({**base, "tipo": "banda"}, 30, 600, 0.35)
    assert _p_req(banda) > _p_req(rodillos)
    assert _rule(banda, "arrastre de banda") is not None
    assert _rule(rodillos, "arrastre de banda") is None
    assert _rule(banda, "par de arranque") is not None


# ------------------------------------------------------------------- endpoint
def test_checks_endpoint_returns_estructura():
    api.DOC = Document("checks-test")
    base = _box(api.DOC, "Base", 100, z=50)
    motor = _box(api.DOC, "Motor", 100, z=150)
    api.DOC.execute("ground", {"name": "g1", "feature": base})
    api.DOC.execute("fasten", {"name": "f1", "a": base, "b": motor, "size": "M10", "qty": 4})
    client = TestClient(api.app)
    r = client.post("/api/checks", json={"carga_kg": 10, "largo_paquete_mm": 400})
    assert r.status_code == 200
    data = r.json()
    assert "interferencias" in data and "ingenieria" in data
    assert isinstance(data["estructura"], list)
    assert any(c["regla"].startswith("unión apernada") for c in data["estructura"])


# ------------------------------------------------- V5.10: normas del vertical
_BASE_BANDA = {"largo": 4000, "ancho": 600, "altura": 800, "paso": 300,
               "rodillo": "RODILLO-50", "motor": "MOTOR-150", "tambor_d": 114,
               "rpm_motor": 58, "torque_Nm": 156, "tipo": "banda"}


def test_slider_bed_candado_retro_y_cita_cema():
    # sin `soporte` → default cama: MISMOS kW que siempre + cita CEMA (solo texto)
    checks = conveyor_engineering_check(dict(_BASE_BANDA), 30, 600, 0.35)
    # ancla absoluta: n_paq=3, banda 13.44 kg → F=334.9 N → P=0.179 kW
    assert _p_req(checks) == pytest.approx(0.18, abs=0.005)
    arr = _rule(checks, "arrastre de banda")
    assert "CEMA" in arr["calc"]["norma"] and "slider bed" in arr["calc"]["norma"]
    assert "CEMA" in _rule(checks, "motorización")["calc"]["norma"]
    assert "DIN 22101" in _rule(checks, "par de arranque")["calc"]["norma"]


def test_soporte_rodillos_usa_iso5048():
    cama = conveyor_engineering_check(dict(_BASE_BANDA), 30, 600, 0.35)
    idlers = conveyor_engineering_check({**_BASE_BANDA, "soporte": "rodillos",
                                         "q_ro_kg_m": 1.5}, 30, 600, 0.35)
    arr = _rule(idlers, "arrastre de banda")
    assert "ISO 5048" in arr["calc"]["norma"]
    assert "C(L)" in arr["calc"]["entradas"]
    assert "interpolado" in arr["calc"]["entradas"]["C(L)"]  # L=4 m < 80 m
    # la rodadura sobre idlers pide MUCHA menos potencia que el deslizamiento
    assert _p_req(idlers) < _p_req(cama)
    assert "ISO 5048" in _rule(idlers, "motorización")["calc"]["norma"]


def test_eytelwein_presente_y_honesto():
    checks = conveyor_engineering_check(dict(_BASE_BANDA), 30, 600, 0.35)
    eyt = _rule(checks, "adherencia del tambor motriz")
    assert eyt is not None
    assert eyt["calc"]["fs"] is None                 # sin t2_n no se inventa FS
    assert "T2_min" in eyt["calc"]["resultado"]
    assert "Eytelwein" in eyt["calc"]["norma"]
    assert eyt["estado"] == "aviso"                  # sin tensor detectado
    # con tensor declarado → ok informativo
    ok = conveyor_engineering_check({**_BASE_BANDA, "tiene_tensor": True}, 30, 600, 0.35)
    assert _rule(ok, "adherencia del tambor motriz")["estado"] == "ok"
    # con t2_n explícito → FS real
    fs = conveyor_engineering_check({**_BASE_BANDA, "t2_n": 500.0}, 30, 600, 0.35)
    assert _rule(fs, "adherencia del tambor motriz")["calc"]["fs"] is not None


def test_eytelwein_mu_engomado_vs_liso():
    from apolo.library.engineering.iso5048 import eytelwein_t2_min_n

    lis = conveyor_engineering_check(dict(_BASE_BANDA), 30, 600, 0.35)
    eng = conveyor_engineering_check({**_BASE_BANDA, "tambor_engomado": True}, 30, 600, 0.35)
    t2_lis = float(re.search(r"T2_min = ([\d.]+) N",
                             _rule(lis, "adherencia")["calc"]["resultado"]).group(1))
    t2_eng = float(re.search(r"T2_min = ([\d.]+) N",
                             _rule(eng, "adherencia")["calc"]["resultado"]).group(1))
    assert t2_eng < t2_lis  # el lagging agarra más → exige menos T2
    assert "0.35" in _rule(eng, "adherencia")["calc"]["entradas"]["μ tambor"]
    assert "0.25" in _rule(lis, "adherencia")["calc"]["entradas"]["μ tambor"]


def test_enrich_deriva_senales_de_la_escena():
    from apolo.library.rules import _enrich_conveyor

    doc = Document("t-senales")
    _box(doc, "Mesa desliz. 2mm A36", 100)
    _box(doc, "Tambor motriz (engomado, eje vivo)", 100, x=200)
    _box(doc, "Tensor de cola · Perno tensor", 100, x=400)
    base = _enrich_conveyor({"tipo": "banda", "largo": 4000}, doc.scene, {})
    assert base["soporte"] == "cama"
    assert base["tambor_engomado"] is True
    assert base["tiene_tensor"] is True
