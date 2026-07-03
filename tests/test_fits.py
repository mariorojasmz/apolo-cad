"""ISO 286 (V5.4): spot-checks contra límites PUBLICADOS de la norma.

Cada letra soportada y varias franjas nominales — si una tabla se transcribió
mal, alguno de estos valores revienta."""

from __future__ import annotations

import pytest

from apolo.library.engineering.fits import (
    SEAT_RECOMMENDATIONS,
    bearing_seat_check,
    fit_check,
    fit_limits,
    format_fit_label,
    parse_fit,
)


def _devs(nominal, fit):
    lim = fit_limits(nominal, fit)
    return lim["es_um"], lim["ei_um"]


# ------------------------------------------------------ valores publicados
@pytest.mark.parametrize("nominal,fit,es,ei", [
    (20, "H7", 21, 0),
    (35, "H8", 39, 0),
    (25, "H7", 21, 0),
    (10, "H7", 15, 0),
    (100, "H7", 35, 0),
    (25, "G7", 28, 7),      # EI = +7 (espejo de g), ES = EI + IT7
    (25, "F8", 53, 20),     # EI = +20 (espejo de f)
    (25, "K7", 6, -15),
    (25, "K6", 2, -11),
    (25, "M7", 0, -21),
    (25, "N7", -7, -28),
    (25, "P7", -14, -35),
    (20, "g6", -7, -20),
    (25, "k6", 15, 2),
    (25, "n6", 28, 15),
    (25, "p6", 35, 22),
    (35, "h7", 0, -25),
    (35, "h11", 0, -160),
    (100, "f7", -36, -71),
    (25, "m6", 21, 8),
    (450, "H7", 63, 0),
    (2, "H7", 10, 0),
])
def test_published_limits(nominal, fit, es, ei):
    got_es, got_ei = _devs(nominal, fit)
    assert got_es == pytest.approx(es, abs=0.01)
    assert got_ei == pytest.approx(ei, abs=0.01)


def test_js_symmetric():
    es, ei = _devs(60, "js6")
    assert es == pytest.approx(9.5) and ei == pytest.approx(-9.5)
    es, ei = _devs(60, "JS7")
    assert es == pytest.approx(15) and ei == pytest.approx(-15)


def test_range_borders():
    # 18 pertenece a la franja 10–18; 18.001 a la 18–30
    assert _devs(18, "H7")[0] == 18
    assert _devs(18.001, "H7")[0] == 21


def test_unsupported_raises():
    with pytest.raises(KeyError, match="inválido"):
        fit_limits(20, "z7")  # letra fuera del alfabeto ISO soportado → parse
    with pytest.raises(KeyError, match="IT12|no soportad"):
        fit_limits(20, "H12")
    with pytest.raises(KeyError, match="no soportad"):
        fit_limits(20, "K8")  # la regla Δ solo vale en grados 6–7
    with pytest.raises(KeyError, match="fuera de la tabla"):
        fit_limits(600, "H7")
    with pytest.raises(KeyError, match="inválido"):
        parse_fit("H")


def test_parse_fit():
    assert parse_fit("20 H7") == (20.0, "H", 7)
    assert parse_fit("H7") == (None, "H", 7)
    assert parse_fit("h7") == (None, "h", 7)
    assert parse_fit("js6") == (None, "js", 6)


# ---------------------------------------------------------------- fit_check
def test_h7_g6_is_clearance():
    r = fit_check(20, "H7", "g6")
    assert r["tipo"] == "juego"
    assert r["juego_min_um"] == pytest.approx(7)
    assert r["juego_max_um"] == pytest.approx(41)


def test_h7_p6_is_interference():
    r = fit_check(25, "H7", "p6")
    assert r["tipo"] == "apriete"
    assert r["juego_max_um"] == pytest.approx(-1)  # 21 − 22
    assert r["juego_min_um"] == pytest.approx(-35)  # 0 − 35


def test_h7_k6_is_transition():
    assert fit_check(25, "H7", "k6")["tipo"] == "transicion"


# ------------------------------------------------------------- asientos ISO 492
def test_seat_k6_press_fit_for_rotating_ring():
    r = bearing_seat_check(35, "k6", "rodamiento_anillo_giratorio")
    # bore 0/−12; k6 = +18/+2 → juego −30…−2 = apriete 2–30 µm
    assert r["tipo"] == "apriete"
    assert r["juego_min_um"] == pytest.approx(-30)
    assert r["juego_max_um"] == pytest.approx(-2)
    assert r["recomendado"] is True


def test_seat_h7_slides_in_uc_insert():
    r = bearing_seat_check(35, "h7", "chumacera_inserto")
    # bore 0/−12; h7 = 0/−25 → juego −12…+25 (transición suave)
    assert r["tipo"] == "transicion"
    assert r["juego_min_um"] == pytest.approx(-12)
    assert r["juego_max_um"] == pytest.approx(25)
    assert r["recomendado"] is True


def test_seat_k6_wrong_for_uc_insert():
    r = bearing_seat_check(35, "k6", "chumacera_inserto")
    assert r["recomendado"] is False
    assert r["tipo"] == "apriete"
    assert "h7" in r["tipico"] or r["tipico"] == "h7"


def test_seat_unknown_mount():
    with pytest.raises(KeyError, match="desconocido"):
        bearing_seat_check(35, "h7", "magico")


# ------------------------------------------------------------------ formato
def test_format_fit_label():
    assert format_fit_label(20, "H7") == "Ø20 H7 (+0.021/0)"
    assert format_fit_label(35, "h7") == "Ø35 h7 (0/-0.025)"
    assert format_fit_label(25, "k6") == "Ø25 k6 (+0.015/+0.002)"


# =====================================================================
# Integración V5.4: comando, planos, regla de asientos y API
# =====================================================================
from apolo.doc.document import Document
from apolo.commands.registry import CommandError


def test_drill_hole_fit_roundtrip_and_validation():
    doc = Document()
    b = doc.execute("create_box", {"width": 80, "depth": 60, "height": 20})
    doc.execute("drill_hole", {"feature": b, "position": {"x": 0, "y": 0, "z": 10},
                               "axis": "-z", "diameter": 20, "depth": 0, "fit": "H7"})
    cmd = next(c for c in doc.commands if c["type"] == "drill_hole")
    assert cmd["params"]["fit"] == "H7"
    doc2 = Document.from_apolo_bytes(doc.to_apolo_bytes())
    assert any(c["params"].get("fit") == "H7" for c in doc2.commands)
    with pytest.raises(CommandError, match="AGUJERO"):
        doc.execute("drill_hole", {"feature": b, "position": {"x": 20, "y": 0, "z": 10},
                                   "axis": "-z", "diameter": 10, "fit": "g6"})
    with pytest.raises(CommandError):
        doc.execute("drill_hole", {"feature": b, "position": {"x": 20, "y": 0, "z": 10},
                                   "axis": "-z", "diameter": 10, "fit": "Z9"})


def _plate_scene():
    doc = Document()
    b = doc.execute("create_box", {"width": 80, "depth": 60, "height": 20})
    doc.execute("drill_hole", {"feature": b, "position": {"x": 0, "y": 0, "z": 10},
                               "axis": "-z", "diameter": 20, "depth": 0, "fit": "H7"})
    return doc


def test_hole_callout_with_and_without_fit():
    from apolo.drawing import compose_sheet

    doc = _plate_scene()
    m = compose_sheet(doc.scene, hole_fits={20.0: "H7"})
    assert any("Ø20 H7 (+0.021/0)" in lab.text for lab in m.labels)
    # retro: sin hole_fits el callout clásico queda intacto
    m2 = compose_sheet(doc.scene)
    assert any(lab.text == "Ø20" for lab in m2.labels)
    assert not any("H7" in lab.text for lab in m2.labels)


def _seat_doc(shaft_name: str):
    doc = Document()
    ucp = doc.execute("insert_component", {"component": "UCP207"})
    eje = doc.execute("create_cylinder", {"name": shaft_name, "radius": 17.5,
                                          "height": 200, "axis": "y"})
    doc.execute("fasten", {"name": "f_asiento", "a": ucp, "b": eje, "kind": "contacto"})
    return doc


def _seat_rules(doc):
    from apolo.library.catalog import CATALOG
    from apolo.library.engineering.report import structure_engineering_check

    checks = structure_engineering_check(
        doc.scene, doc.fasteners, doc.grounds, doc.joints, doc.mates, catalog=CATALOG
    )
    return [c for c in checks if c["regla"].startswith("asiento ISO 286")]


def test_seat_rule_ok_with_h7():
    rules = _seat_rules(_seat_doc("Eje motriz Ø35 h7"))
    assert len(rules) == 1
    r = rules[0]
    assert r["estado"] == "ok" and "UCP207" in r["regla"]
    assert r["calc"]["resultado"].endswith("(transicion)")
    assert "h7" in r["calc"]["entradas"]["eje"]


def test_seat_rule_error_with_k6_on_insert():
    rules = _seat_rules(_seat_doc("Eje motriz Ø35 k6"))
    assert rules and rules[0]["estado"] == "error"
    assert "DESLIZAR" in rules[0]["detalle"]
    assert "h7" in rules[0]["recomendacion"]


def test_seat_rule_warns_without_fit():
    rules = _seat_rules(_seat_doc("Eje motriz Ø35"))
    assert rules and rules[0]["estado"] == "aviso"
    assert "no declara" in rules[0]["detalle"]
    assert "h7" in rules[0]["recomendacion"]


def test_seat_rule_ignores_unrelated_names():
    # «Larguero (+Y)» junto a una chumacera: sin Ø no hay par → sin regla
    doc = Document()
    ucp = doc.execute("insert_component", {"component": "UCP207"})
    lar = doc.execute("create_box", {"name": "Larguero (+Y)", "width": 200,
                                     "depth": 40, "height": 40})
    doc.execute("fasten", {"name": "f1", "a": ucp, "b": lar, "kind": "perno"})
    assert _seat_rules(doc) == []


# ------------------------------------------------------------------- API HTTP
from fastapi.testclient import TestClient

import apolo.api.main as api


def test_api_fits_endpoint():
    api.DOC = Document("t")
    client = TestClient(api.app)
    r = client.get("/api/fits", params={"nominal": 20, "hole": "H7", "shaft": "g6"})
    assert r.status_code == 200
    data = r.json()
    assert data["tipo"] == "juego"
    assert data["juego_min_um"] == pytest.approx(7)
    r = client.get("/api/fits", params={"nominal": 35, "shaft": "h7"})
    assert r.json()["lo_mm"] == pytest.approx(34.975)
    assert client.get("/api/fits", params={"nominal": 20, "hole": "Z9"}).status_code == 400
    assert client.get("/api/fits", params={"nominal": 20}).status_code == 400


def test_api_drawing_spec_auto_fit_and_override():
    api.DOC = _plate_scene()
    client = TestClient(api.app)
    # automático: el drill_hole con fit=H7 rotula el callout sin pedir nada
    r = client.post("/api/drawing/spec", json={"format": "svg"})
    assert r.status_code == 200
    assert "Ø20 H7 (+0.021/0)" in r.text
    # override del agente encima del auto
    r2 = client.post("/api/drawing/spec", json={"format": "svg", "hole_fits": {"20": "H8"}})
    assert "Ø20 H8" in r2.text and "H7" not in r2.text


def test_api_drawing_spec_shaft_fit_from_name():
    doc = Document()
    doc.execute("create_cylinder", {"name": "Eje motriz Ø35 h7", "radius": 17.5,
                                    "height": 200, "axis": "y"})
    api.DOC = doc
    client = TestClient(api.app)
    r = client.post("/api/drawing/spec", json={"format": "svg"})
    assert r.status_code == 200
    assert "Ø35 h7 (0/-0.025)" in r.text
