"""Deltas de scene_payload (V6.2b): rev por feature + payload delta.

Contrato: el ``rev`` sube cuando la GEOMETRÍA de una feature cambia y NO cuando solo
cambia un metadato (renombre/color/visibilidad); un delta al día no reenvía mallas ni
definiciones; el payload COMPLETO (known=None) conserva el contrato de cobertura.
"""

from __future__ import annotations

import json

import pytest

import apolo.api.main as api
from apolo.doc import Document


@pytest.fixture()
def doc10():
    """10 cajas + una instancia (patrón) sobre un DOC aislado, con revs limpios."""
    old = api.DOC
    api._GEOM_REVS.clear()  # los fids se reutilizan (c1, c2…) entre docs → aislar
    doc = Document("delta")
    doc.execute_many([
        {"type": "create_box", "params": {"name": f"b{i}", "width": 30 + i, "depth": 20,
                                          "height": 10, "position": {"x": i * 60}}}
        for i in range(10)
    ])
    api.DOC = doc
    yield doc
    api.DOC = old
    api._GEOM_REVS.clear()


def _known(payload: dict) -> dict:
    return {
        "revs": {f["id"]: f["rev"] for f in payload["features"]},
        "defs": list(payload["definitions"].keys()),
    }


def test_full_payload_has_rev(doc10):
    payload = api.scene_payload()
    assert all(isinstance(f["rev"], int) and f["rev"] >= 1 for f in payload["features"])
    assert all("same" not in f for f in payload["features"])  # sin known → nunca 'same'


def test_delta_up_to_date_sends_no_geometry(doc10):
    full = api.scene_payload()
    delta = api.scene_payload(known=_known(full))
    # todas 'same', sin malla (ni siquiera la clave) ni definiciones nuevas
    assert all(f.get("same") is True and f.get("mesh") is None for f in delta["features"])
    assert delta["definitions"] == {}
    # metadatos VOLÁTILES siempre presentes (cambian sin tocar geometría)
    assert all({"color", "visible", "group", "name"} <= f.keys() for f in delta["features"])
    # bbox/volumen NO se reenvían (el cliente los conserva) → delta mínimo
    assert all("bbox" not in f and "volume_mm3" not in f for f in delta["features"])


def test_rev_rises_on_geometry_edit_not_on_metadata(doc10):
    full = api.scene_payload()
    known = _known(full)
    target = doc10.commands[3]["id"]
    rev0 = next(f["rev"] for f in full["features"] if f["id"] == target)

    # 1) renombrar/recolorear NO cambia la geometría → rev estable, feature 'same'
    doc10.colors[target] = "#ff0000"
    d1 = api.scene_payload(known=known)
    f1 = next(f for f in d1["features"] if f["id"] == target)
    assert f1["rev"] == rev0 and f1.get("same") is True
    assert f1["color"] == "#ff0000"  # el metadato SÍ viaja

    # 2) editar la geometría (ancho) → rev sube y llega la geometría (la caja pasa a ser
    #    una instancia nueva: malla propia O definición fresca en el delta)
    doc10.edit(target, {"width": 999, "depth": 20, "height": 10}, merge=True)
    d2 = api.scene_payload(known=known)
    f2 = next(f for f in d2["features"] if f["id"] == target)
    assert f2["rev"] > rev0 and not f2.get("same")
    assert f2["mesh"] is not None or f2["mesh_key"] in d2["definitions"]


def test_deleted_feature_pruned_from_revs(doc10):
    api.scene_payload()  # siembra revs de las 10
    assert len(api._GEOM_REVS) == 10
    doc10.remove_commands([doc10.commands[0]["id"]])
    api.scene_payload()
    assert len(api._GEOM_REVS) == 9  # el fid borrado se podó


def test_delta_endpoint_roundtrip(doc10):
    from fastapi.testclient import TestClient

    client = TestClient(api.app)
    full = client.get("/api/scene").json()
    body = _known(full)
    delta = client.post("/api/scene/delta", json=body).json()
    assert all(f.get("same") is True for f in delta["features"])
    assert delta["definitions"] == {}


def test_delta_nochange_is_tiny_vs_full():
    """Layout sintético (~150 sólidos): el delta sin cambios pesa mucho menos que el full
    (< 60 KB vs ~1.1 MB). Assert holgado (margen), no exacto."""
    old = api.DOC
    api._GEOM_REVS.clear()
    try:
        doc = Document("layout")
        doc.execute("create_conveyor", {"largo": 3000, "ancho": 500, "altura": 700, "paso": 150})
        seed = doc.execute("create_box", {"width": 60, "depth": 40, "height": 30, "position": {"y": 1500}})
        doc.execute("pattern_group", {"source": seed, "count": 80, "spacing": {"x": 90}})
        api.DOC = doc
        full = api.scene_payload()
        full_bytes = len(json.dumps(full).encode())
        delta = api.scene_payload(known=_known(full))
        delta_bytes = len(json.dumps(delta).encode())
        # el delta sin cambios es una fracción del full (solo metadatos, 0 mallas)
        assert delta["definitions"] == {}
        assert delta_bytes < 60_000
        assert delta_bytes < full_bytes * 0.4
    finally:
        api.DOC = old
        api._GEOM_REVS.clear()
