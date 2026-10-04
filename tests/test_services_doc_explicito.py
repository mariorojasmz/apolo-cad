"""Lo que vive en `services/` mide sobre el `doc` que RECIBE, nunca sobre el documento activo
de la API (plan `docs/plans/partir-api-main.md`, D6).

El bug que esto ata: `_piece_dim_tols(doc)` (entonces en `api/main.py`) medía cada eslabón con
`_stackup_link_from_feature`, que leía el `DOC` GLOBAL y no su `doc`. Los tests lo tapaban
asignando `api.DOC = doc` antes de llamar; con otro documento abierto, la lámina de un
proyecto salía sin la tolerancia que su cadena exige. Aquí el documento activo es OTRO a
propósito.
"""

from __future__ import annotations

import pytest

import apolo.api.main as api
from apolo.doc import Document


@pytest.fixture
def otro_doc_activo(monkeypatch):
    monkeypatch.setattr(api, "DOC", Document("activo-sin-piezas"))


def _con_cadena() -> tuple[Document, str]:
    doc = Document("analizado")
    fid = doc.execute("create_box", {"name": "Placa", "width": 400, "depth": 100,
                                     "height": 10})
    doc.stackups = {"largo": {"eslabones": [{"id": fid, "eje": "x", "tol": {"pm": 0.35}}]}}
    return doc, fid


def test_piece_dim_tols_mide_sobre_su_doc(otro_doc_activo):
    from apolo.services.drawing_maps import piece_dim_tols

    doc, fid = _con_cadena()
    assert piece_dim_tols(doc)[fid]["X"][0] == pytest.approx(0.35)


def test_evaluate_stackups_mide_sobre_su_doc(otro_doc_activo):
    from apolo.services.stackup_eval import evaluate_stackups

    doc, _fid = _con_cadena()
    (cadena,) = evaluate_stackups(doc, "declared")
    assert "error" not in cadena and cadena["nominal_close_mm"] == pytest.approx(400.0)
