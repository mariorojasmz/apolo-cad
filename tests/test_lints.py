"""Lints pre-entrega (V7.2b, frente C): barreno sin perno + pieza sin grupo ni unión."""

from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.library.lints import predelivery_lints


def _lints(doc):
    return predelivery_lints(doc.scene, doc.commands, doc.fasteners, doc.grounds,
                             doc.joints, doc.mates)


def _regla(checks, prefix):
    return next((c for c in checks if c["regla"].startswith(prefix)), None)


def test_hole_without_bolt_warns():
    """Placa con 4 barrenos y solo 3 pernos → 1 aviso de barreno sin perno."""
    doc = Document()
    placa = doc.execute("create_box", {"name": "Placa de anclaje", "width": 120,
                                       "depth": 80, "height": 12, "position": {"z": 6}})
    holes = [(-40, -25), (40, -25), (-40, 25), (40, 25)]
    for x, y in holes:
        doc.execute("drill_hole", {"feature": placa, "position": {"x": x, "y": y, "z": -6},
                                   "axis": "z", "diameter": 13, "depth": 0})
    for x, y in holes[:3]:  # solo 3 de los 4 barrenos reciben perno
        doc.execute("insert_component", {"component": "PERNO-HEX-M12",
                                         "position": {"x": x, "y": y, "z": 0}})
    doc.execute("ground", {"name": "g1", "feature": placa})  # aísla el lint de barreno
    checks = _lints(doc)
    r = _regla(checks, "pre-entrega · barreno sin perno")
    assert r is not None and r["estado"] == "aviso"
    assert "1 barreno" in r["detalle"]              # exactamente el 4º queda sin perno
    assert _regla(checks, "pre-entrega · pieza sin grupo") is None  # placa aterrizada


def test_hole_with_amedida_bolt_no_warning():
    """Un perno MODELADO a-medida (no catálogo, nombre «Perno…», como los de anclaje de
    la faja 38) en el eje del barreno cuenta como fijado → sin aviso (era falso positivo)."""
    doc = Document()
    placa = doc.execute("create_box", {"name": "Placa de anclaje A36", "width": 120,
                                       "depth": 80, "height": 12, "position": {"z": 6}})
    doc.execute("drill_hole", {"feature": placa, "position": {"x": 30, "y": 20, "z": -6},
                               "axis": "z", "diameter": 14, "depth": 0})
    doc.execute("create_box", {"name": "Perno anclaje M12 + arandela", "width": 18,
                               "depth": 18, "height": 60, "position": {"x": 30, "y": 20, "z": 20}})
    doc.execute("ground", {"name": "g1", "feature": placa})
    assert _regla(_lints(doc), "pre-entrega · barreno sin perno") is None


def test_loose_part_warns():
    """Una pieza sin grupo NI unión declarada → 1 aviso."""
    doc = Document()
    base = doc.execute("create_box", {"name": "Base", "width": 200, "depth": 200,
                                      "height": 20, "position": {"z": 10}})
    doc.execute("ground", {"name": "g1", "feature": base})
    doc.execute("create_box", {"name": "Chatarra suelta", "width": 60, "depth": 60,
                               "height": 60, "position": {"x": 500, "z": 400}})
    checks = _lints(doc)
    r = _regla(checks, "pre-entrega · pieza sin grupo")
    assert r is not None and r["estado"] == "aviso"
    assert "Chatarra" in r["detalle"] and "1 pieza" in r["detalle"]


def test_hole_lint_resolves_parametric_position():
    """Los barrenos posicionados por «=expresión» (modelos paramétricos como la faja 38)
    se resuelven con el `resolve` inyectado — antes reventaban /api/checks con 500."""
    from apolo.commands.expressions import resolve_params

    doc = Document()
    doc.execute("set_variable", {"name": "hx", "expression": "40"})
    placa = doc.execute("create_box", {"name": "Placa", "width": 120, "depth": 80,
                                       "height": 12, "position": {"z": 6}})
    doc.execute("drill_hole", {"feature": placa, "position": {"x": "=hx", "y": 0, "z": -6},
                               "axis": "z", "diameter": 13, "depth": 0})
    doc.execute("ground", {"name": "g1", "feature": placa})
    resolve = lambda p: resolve_params(p, doc.variables_resolved)  # noqa: E731
    checks = predelivery_lints(doc.scene, doc.commands, doc.fasteners, doc.grounds,
                               doc.joints, doc.mates, resolve=resolve)
    r = _regla(checks, "pre-entrega · barreno sin perno")
    assert r is not None and "x≈40" in r["detalle"]     # expresión resuelta a 40
    # sin resolver, el barreno paramétrico se SALTA en vez de reventar
    assert _lints(doc) == [] or _regla(_lints(doc), "pre-entrega · barreno sin perno") is None


def test_healthy_model_no_lints():
    """Modelo sano (todo unido, sin barrenos huérfanos) → 0 avisos."""
    doc = Document()
    base = doc.execute("create_box", {"name": "Base", "width": 200, "depth": 200,
                                      "height": 20, "position": {"z": 10}})
    motor = doc.execute("create_box", {"name": "Motor", "width": 100, "depth": 100,
                                       "height": 100, "position": {"z": 90}})
    doc.execute("ground", {"name": "g1", "feature": base})
    doc.execute("fasten", {"name": "f1", "a": base, "b": motor, "size": "M10", "qty": 4})
    assert _lints(doc) == []


def test_lints_flow_through_checks_endpoint():
    """El endpoint /api/checks incluye los lints pre-entrega en `estructura`."""
    api.DOC = Document("lints-api")
    base = api.DOC.execute("create_box", {"name": "Base", "width": 200, "depth": 200,
                                          "height": 20, "position": {"z": 10}})
    api.DOC.execute("ground", {"name": "g1", "feature": base})
    api.DOC.execute("create_box", {"name": "Suelta", "width": 60, "depth": 60,
                                   "height": 60, "position": {"x": 500, "z": 400}})
    client = TestClient(api.app)
    data = client.post("/api/checks", json={}).json()
    assert any(c["regla"].startswith("pre-entrega") for c in data["estructura"])
