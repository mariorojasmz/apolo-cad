"""V7.6 fase B (E2.3): la cota de una lámina rotula la tolerancia que EXIGE su cadena de
cotas declarada — no la genérica de ISO 2768 — y remite a la memoria; el conjunto soldado
declara ISO 13920 (la norma de weldments, que las de mecanizado no cubren)."""
import pytest

import apolo.api.main as api
from apolo.doc import Document
from apolo.drawing.sheet import compose_sheet


def _placa(doc, w=400.0):
    return doc.execute("create_box", {"name": "Placa", "width": w, "depth": 100, "height": 10})


# ------------------------------------------------------------- derivación (capa API)
def test_dim_tol_from_declared_chain():
    """Un eslabón {id, eje} de una cadena declarada da la tolerancia de ESA cota."""
    doc = Document("t")
    fid = _placa(doc)
    api.DOC = doc
    doc.stackups = {"largo del bastidor": {
        "eslabones": [{"id": fid, "eje": "x", "tol": {"pm": 0.35}}]}}
    tols = api._piece_dim_tols(doc)
    half, cadena, _fuente = tols[fid]["X"]
    assert half == pytest.approx(0.35) and cadena == "largo del bastidor"
    assert "Y" not in tols[fid]                      # solo el eje declarado


def test_dim_tol_strictest_chain_wins_and_asymmetric_skipped():
    """Varias cadenas sobre la misma cota → gana la MÁS ESTRICTA. Una banda asimétrica
    (fit ISO 286) NO se rotula en la cota general: viaja en su callout de Ø."""
    doc = Document("t")
    fid = _placa(doc)
    api.DOC = doc
    doc.stackups = {
        "holgada": {"eslabones": [{"id": fid, "eje": "x", "tol": {"pm": 0.9}}]},
        "estricta": {"eslabones": [{"id": fid, "eje": "x", "tol": {"pm": 0.2}}]},
        "asimetrica": {"eslabones": [{"id": fid, "eje": "y", "tol": {"fit": "h7"}}]},
    }
    tols = api._piece_dim_tols(doc)
    assert tols[fid]["X"][0] == pytest.approx(0.2) and tols[fid]["X"][1] == "estricta"
    assert "Y" not in tols[fid]                      # asimétrica → fuera de la cota general


def test_bad_chain_does_not_break_the_map():
    """Una cadena inválida no puede tumbar el juego de planos (patrón de aislamiento V7.3)."""
    doc = Document("t")
    fid = _placa(doc)
    api.DOC = doc
    doc.stackups = {
        "rota": {"eslabones": [{"id": "cNOEXISTE", "eje": "x", "tol": {"pm": 0.1}}]},
        "buena": {"eslabones": [{"id": fid, "eje": "x", "tol": {"pm": 0.4}}]},
    }
    assert api._piece_dim_tols(doc)[fid]["X"][0] == pytest.approx(0.4)


# ------------------------------------------------------------------ en la lámina
def test_sheet_dimension_carries_chain_tolerance_and_note():
    doc = Document("t")
    _placa(doc)
    base = compose_sheet(doc.scene, shop_notes=True)
    m = compose_sheet(doc.scene, shop_notes=True,
                      dim_tols={"X": (0.35, "largo del bastidor", "ISO 2768-m")})
    txt = [l.text for l in m.labels]
    assert "400 ±0.35" in txt                                    # la cota lleva SU banda
    assert "400" in [l.text for l in base.labels]                # antes: sin tolerancia
    assert any("cadena «largo del bastidor»" in t for t in txt)  # remite a la memoria


def test_iso13920_only_on_welded_assembly():
    """La nota de tolerancia de construcción soldada aparece SOLO si hay cordones."""
    doc = Document("t")
    a = _placa(doc)
    b = doc.execute("create_box", {"name": "Costilla", "width": 20, "depth": 100,
                                   "height": 60, "position": {"x": 120, "z": 35}})
    sin_sold = compose_sheet(doc.scene, shop_notes=True)
    assert not any("13920" in l.text for l in sin_sold.labels)
    doc.execute("fasten", {"name": "w1", "a": a, "b": b, "kind": "soldadura",
                           "throat_mm": 4, "length_mm": 100})
    con_sold = compose_sheet(doc.scene, shop_notes=True, fasteners=doc.fasteners)
    assert any("ISO 13920" in l.text for l in con_sold.labels)
