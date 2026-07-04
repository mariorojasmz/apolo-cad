"""Roscas métricas ISO 261/262 (V5.7): tabla, parseo, 3D a broca, callouts, cédula."""
import io
import math

import ezdxf
import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.library.engineering.threads import (
    format_thread_label, parse_thread, thread_designation, thread_spec,
)

# brocas de machuelado PUBLICADAS (DIN 336) — anclas del plan
PUBLICADAS = [
    ("M3", 2.5), ("M4", 3.3), ("M5", 4.2), ("M6", 5.0), ("M8", 6.8),
    ("M10", 8.5), ("M12", 10.2), ("M16", 14.0), ("M20", 17.5), ("M24", 21.0),
    ("M30", 26.5), ("M36", 32.0),
    ("M8x1", 7.0), ("M10x1.25", 8.8), ("M12x1.5", 10.5), ("M16x1.5", 14.5),
]


@pytest.mark.parametrize("size,broca", PUBLICADAS)
def test_tap_drills_published(size, broca):
    assert thread_spec(size)["broca_mm"] == broca


def test_pasos_gruesos():
    assert thread_spec("M8")["paso_mm"] == 1.25
    assert thread_spec("M12")["paso_mm"] == 1.75
    assert thread_spec("M20")["paso_mm"] == 2.5


def test_parse_thread_variants():
    assert parse_thread("M8") == ("M8", 8.0, None)
    assert parse_thread("m8") == ("M8", 8.0, None)
    assert parse_thread("M10x1.25") == ("M10", 10.0, 1.25)
    assert parse_thread("M10×1.25") == ("M10", 10.0, 1.25)
    assert parse_thread("M10 X 1.25") == ("M10", 10.0, 1.25)
    # paso explícito == grueso → canónica sin paso
    assert parse_thread("M8x1.25") == ("M8", 8.0, None)
    assert thread_designation("M8x1.25") == "M8"
    assert thread_designation("M10x1.25") == "M10x1.25"


def test_parse_thread_unknown_raises():
    for bad in ("M7", "M8x9", "8", "", "rosca"):
        with pytest.raises(KeyError):
            parse_thread(bad)
    # el mensaje lista lo soportado
    with pytest.raises(KeyError, match="M36"):
        parse_thread("M7")


def test_area_reuses_bolts():
    from apolo.library.engineering.bolts import TENSILE_AREA_MM2

    assert thread_spec("M8")["area_mm2"] == TENSILE_AREA_MM2["M8"]  # 36.6 exacto
    # M5 no está en bolts → fórmula ISO 898-1
    a5 = thread_spec("M5")["area_mm2"]
    assert a5 == pytest.approx(math.pi / 4 * (5 - 0.9382 * 0.8) ** 2, abs=0.1)
    # la fórmula reproduce la tabla con <1 % en M6–M24
    for size in ("M6", "M8", "M10", "M12", "M16", "M20", "M24"):
        spec = thread_spec(size)
        formula = math.pi / 4 * (spec["nominal_mm"] - 0.9382 * spec["paso_mm"]) ** 2
        assert formula == pytest.approx(TENSILE_AREA_MM2[size], rel=0.01)


def test_format_thread_label():
    assert format_thread_label("M8") == "M8 - 6H (broca Ø6.8)"
    assert format_thread_label("M8", 4) == "4×M8 - 6H (broca Ø6.8)"
    assert format_thread_label("M10x1.25") == "M10×1.25 - 6H (broca Ø8.8)"


# ------------------------------------------------------------------ 3D / comando
def _doc_placa(thread="M8", n=1, **extra):
    doc = Document("t-rosca")
    doc.execute("create_box", {"name": "Placa", "width": 150, "depth": 100, "height": 15})
    fid = next(iter(doc.scene))
    for i in range(n):
        doc.execute("drill_hole", {"feature": fid, "position": {"x": -45 + i * 30, "y": 0, "z": 15}, "thread": thread, **extra})
    return doc, fid


def test_drill_thread_drills_tap_size():
    doc, fid = _doc_placa("M8")
    quitado = 150 * 100 * 15 - doc.scene[fid].shape.volume
    assert quitado == pytest.approx(math.pi / 4 * 6.8**2 * 15, rel=0.01)
    assert quitado != pytest.approx(math.pi / 4 * 8**2 * 15, rel=0.05)


def test_thread_normalizado_en_modelo():
    # el log guarda el input CRUDO (event-sourcing); la normalización vive en el
    # modelo validado, que es lo que consume el executor y la capa API
    from apolo.commands.models import DrillHoleParams

    p = DrillHoleParams(feature="c1", position={"x": 0, "y": 0, "z": 0},
                        thread="m8x1.25")
    assert p.thread == "M8"
    # y la variante sucia igual taladra a la broca correcta
    doc, fid = _doc_placa("m8x1.25")
    quitado = 150 * 100 * 15 - doc.scene[fid].shape.volume
    assert quitado == pytest.approx(math.pi / 4 * 6.8**2 * 15, rel=0.01)


def test_fit_and_thread_mutually_exclusive():
    from apolo.doc import DocumentError

    doc = Document("t-excl")
    doc.execute("create_box", {"width": 50, "depth": 50, "height": 10})
    fid = next(iter(doc.scene))
    with pytest.raises((DocumentError, Exception), match="(?i)fit|rosca"):
        doc.execute("drill_hole", {"feature": fid, "position": {"x": 0, "y": 0, "z": 10}, "thread": "M8", "fit": "H7"})


def test_thread_counterbore_vs_broca():
    doc = Document("t-cb")
    doc.execute("create_box", {"width": 50, "depth": 50, "height": 10})
    fid = next(iter(doc.scene))
    with pytest.raises(Exception, match="(?i)caja|counterbore|mayor"):
        doc.execute("drill_hole", {"feature": fid, "position": {"x": 0, "y": 0, "z": 10}, "thread": "M8", "counterbore_d": 6.0, "counterbore_depth": 3})


# ------------------------------------------------------------- plano: callouts
def test_thread_callout_and_cosmetic_arcs():
    from apolo.drawing import compose_sheet

    doc, _ = _doc_placa("M8", n=4)
    model = compose_sheet(doc.scene, hole_threads={6.8: "M8"})
    labels = [lb.text for lb in model.labels]
    assert any("4×M8 - 6H (broca Ø6.8)" in t for t in labels), labels
    arcs = [a for a in model.arcs if a.kind == "thread"]
    assert len(arcs) >= 4  # uno por círculo (al menos en la vista de planta)
    assert all(a.a1 == 0.0 and a.a2 == 270.0 for a in arcs)
    # todos al MISMO radio (mismo grupo M8) y sobre el piso de legibilidad
    radios = {round(a.r, 3) for a in arcs}
    assert len(radios) == 1 and min(radios) >= 0.9


def test_thread_gana_sobre_fit_en_mismo_dia():
    from apolo.drawing import compose_sheet

    doc, _ = _doc_placa("M8")
    model = compose_sheet(doc.scene, hole_fits={6.8: "H7"}, hole_threads={6.8: "M8"})
    labels = " | ".join(lb.text for lb in model.labels)
    assert "M8 - 6H" in labels and "H7" not in labels


def test_dxf_rosca_layer_y_svg_path():
    from apolo.drawing import compose_sheet, sheet_to_dxf, sheet_to_svg

    doc, _ = _doc_placa("M8", n=2)
    model = compose_sheet(doc.scene, hole_threads={6.8: "M8"})
    dxf = sheet_to_dxf(model)
    d = ezdxf.read(io.StringIO(dxf.decode("utf-8", errors="ignore")))
    assert "ROSCA" in [ly.dxf.name for ly in d.layers]
    assert any(e.dxftype() == "ARC" and e.dxf.layer == "ROSCA" for e in d.modelspace())
    svg = sheet_to_svg(model)
    assert 'stroke-width="0.25"' in svg and " A " in svg  # arco fino con comando A


def test_retro_sin_threads_sin_arcos():
    from apolo.drawing import compose_sheet

    doc = Document("t-retro")
    doc.execute("create_box", {"width": 100, "depth": 80, "height": 10})
    fid = next(iter(doc.scene))
    doc.execute("drill_hole", {"feature": fid, "position": {"x": 0, "y": 0, "z": 10}, "diameter": 9})
    model = compose_sheet(doc.scene)
    assert model.arcs == []
    assert any("Ø9" in lb.text for lb in model.labels)


# --------------------------------------------------------------------- capa API
def test_api_hole_thread_map_y_cedula():
    api.DOC = Document("t-api-rosca")
    client = TestClient(api.app)
    client.post("/api/commands", json={"type": "create_box", "params": {
        "name": "Placa demo", "width": 150, "depth": 100, "height": 15}})
    fid = next(iter(api.DOC.scene))
    for i in range(4):
        r = client.post("/api/commands", json={"type": "drill_hole", "params": {
            "feature": fid, "position": {"x": -45 + i * 30, "y": 30, "z": 15},
            "thread": "M8"}})
        assert r.status_code == 200
    assert api._hole_thread_map(api.DOC) == {6.8: "M8"}
    sched = api._thread_schedule(api.DOC)
    assert sched[0]["designacion"] == "M8" and sched[0]["cantidad"] == 4
    assert "Placa demo" in sched[0]["piezas"][0]
    # el juego de planos incluye la CÉDULA (forzada por thread_rows aunque no haya herraje)
    from apolo.drawing import sheet_set

    pages = sheet_set(api.DOC.scene, thread_rows=api._thread_schedule(api.DOC))
    cedula = [p for p in pages if any("CÉDULA" in lb.text for lb in p.labels)]
    assert cedula, "el juego debe incluir la página CÉDULA con las roscas"
    textos = " | ".join(lb.text for lb in cedula[0].labels)
    assert "M8" in textos and "ISO 262" in textos
    r = client.get("/api/drawingset.pdf")
    assert r.status_code == 200 and len(r.content) > 1000


def test_api_threads_endpoint():
    api.DOC = Document("t-api-thr")
    client = TestClient(api.app)
    r = client.get("/api/threads", params={"size": "M8"})
    assert r.status_code == 200
    spec = r.json()
    assert spec["broca_mm"] == 6.8 and spec["paso_mm"] == 1.25
    assert client.get("/api/threads", params={"size": "M7"}).status_code == 400
