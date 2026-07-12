"""V6.5b · frente A — CONTRATO de verificación en lotes (`expect`).

Un lote con `expect` evalúa las aserciones tras el regenerate; si alguna falla, el lote
se revierte POR COMPLETO (doc intacto, sin entrada de undo fantasma). Los `$k` valen en
las aserciones (referencian lo creado por la k-ésima acción del lote).
"""

from fastapi.testclient import TestClient

import apolo.api.main as api
import apolo.doc.document as document
from apolo.doc.document import ContractError, Document


def _two_boxes_actions():
    # A en el origen, B en x=200 → gap = 150 mm (bboxes 50×50×50 centradas)
    return [
        {"type": "create_box", "params": {"name": "A", "width": 50, "depth": 50, "height": 50}},
        {"type": "create_box", "params": {"name": "B", "width": 50, "depth": 50, "height": 50,
                                          "position": {"x": 200, "y": 0, "z": 0}}},
    ]


# ------------------------------------------------------------------ API (endpoint real)
def test_contract_pass_commits_and_one_undo():
    api.DOC = Document("contract-ok")
    client = TestClient(api.app)
    r = client.post("/api/commands/batch", json={
        "actions": _two_boxes_actions(),
        "expect": [{"tipo": "distancia", "a": "$1", "b": "$2", "min": 100}],
    })
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["contrato"] == {"n_aserciones": 1, "ok": True}
    assert len(api.DOC.scene) == 2
    # un solo paso de undo para todo el lote
    assert api.DOC.can_undo
    api.DOC.undo()
    assert len(api.DOC.scene) == 0


def test_contract_fail_rolls_back_whole_batch():
    api.DOC = Document("contract-fail")
    client = TestClient(api.app)
    r = client.post("/api/commands/batch", json={
        "actions": _two_boxes_actions(),
        "expect": [{"tipo": "distancia", "a": "$1", "b": "$2", "max": 10}],  # 150 > 10 → falla
    })
    assert r.status_code == 400
    assert "Contrato incumplido" in r.json()["detail"]
    assert "medido 150" in r.json()["detail"]
    # el lote entero se revirtió: nada quedó y no hay nada que deshacer
    assert len(api.DOC.scene) == 0
    assert not api.DOC.can_undo


def test_contract_fail_keeps_prior_state_and_undo_stack():
    """Un lote con contrato fallido sobre un doc con estado previo lo deja BIT-IDÉNTICO
    (piezas previas + pila de undo intactas: sin entrada fantasma)."""
    api.DOC = Document("contract-prior")
    client = TestClient(api.app)
    client.post("/api/commands", json={
        "type": "create_box", "params": {"name": "C", "width": 50, "depth": 50, "height": 50}})
    assert len(api.DOC.scene) == 1 and api.DOC.can_undo
    commands_before = [dict(c) for c in api.DOC.commands]
    undo_len_before = len(api.DOC._undo)

    r = client.post("/api/commands/batch", json={
        "actions": [{"type": "create_box", "params": {"name": "D", "width": 50, "depth": 50,
                                                       "height": 50, "position": {"x": 200}}}],
        "expect": [{"tipo": "distancia", "a": "$1", "b": "c1", "max": 10}],  # 150 > 10 → falla
    })
    assert r.status_code == 400
    assert [c["id"] for c in api.DOC.commands] == [c["id"] for c in commands_before]
    assert len(api.DOC.scene) == 1  # solo C
    assert len(api.DOC._undo) == undo_len_before  # NO hay entrada de undo del lote fallido


def test_contract_dollar_ref_existe():
    api.DOC = Document("contract-existe")
    client = TestClient(api.app)
    r = client.post("/api/commands/batch", json={
        "actions": _two_boxes_actions(),
        "expect": [{"tipo": "existe", "id": "$1"}, {"tipo": "existe", "id": "$2"}],
    })
    assert r.status_code == 200, r.text
    assert r.json()["contrato"]["n_aserciones"] == 2


def test_contract_bad_ref_rolls_back():
    api.DOC = Document("contract-badref")
    client = TestClient(api.app)
    r = client.post("/api/commands/batch", json={
        "actions": _two_boxes_actions(),
        "expect": [{"tipo": "existe", "id": "$9"}],  # no existe la 9.ª acción
    })
    assert r.status_code == 400
    assert len(api.DOC.scene) == 0  # el lote se revirtió


def test_contract_in_edit_batch():
    """El contrato también aplica a edit_batch: tras estirar B, exige el gap resultante."""
    api.DOC = Document("contract-edit")
    client = TestClient(api.app)
    client.post("/api/commands/batch", json={"actions": _two_boxes_actions()})
    # B está en x=200 (gap 150). Editar B a x=60 dejaría gap = 60-50 = 10; exigimos min 100 → falla
    r = client.patch("/api/commands/batch", json={
        "edits": [{"command_id": "c2", "params": {"position": {"x": 60}}}],
        "expect": [{"tipo": "distancia", "a": "c1", "b": "c2", "min": 100}],
    }, params={"merge": "true"})
    assert r.status_code == 400
    assert "Contrato incumplido" in r.json()["detail"]
    # B quedó donde estaba (x=200): la edición se revirtió
    bb = api.DOC.scene["c2"].shape.bounding_box()
    assert bb.min.X > 150

    # ahora un edit que SÍ cumple el contrato
    r2 = client.patch("/api/commands/batch", json={
        "edits": [{"command_id": "c2", "params": {"position": {"x": 300}}}],
        "expect": [{"tipo": "distancia", "a": "c1", "b": "c2", "min": 100}],
    }, params={"merge": "true"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["contrato"]["ok"] is True


def test_contract_sin_interferencia_reentrant_lock():
    """`sin_interferencia` re-entra STATE_LOCK (interferencia acotada) DENTRO del lote:
    dos cajas solapadas violan el contrato y el lote se revierte."""
    api.DOC = Document("contract-interf")
    client = TestClient(api.app)
    r = client.post("/api/commands/batch", json={
        "actions": [
            {"type": "create_box", "params": {"name": "A", "width": 100, "depth": 100, "height": 100}},
            {"type": "create_box", "params": {"name": "B", "width": 100, "depth": 100, "height": 100,
                                              "position": {"x": 50}}},  # solapa a A
        ],
        "expect": [{"tipo": "sin_interferencia", "ids": ["$1", "$2"]}],
    })
    assert r.status_code == 400
    assert len(api.DOC.scene) == 0  # el lote se revirtió

    # ahora sin solape → el contrato de sin_interferencia se cumple
    r2 = client.post("/api/commands/batch", json={
        "actions": [
            {"type": "create_box", "params": {"name": "A", "width": 50, "depth": 50, "height": 50}},
            {"type": "create_box", "params": {"name": "B", "width": 50, "depth": 50, "height": 50,
                                              "position": {"x": 300}}},
        ],
        "expect": [{"tipo": "sin_interferencia", "ids": ["$1", "$2"]}],
    })
    assert r2.status_code == 200, r2.text
    assert r2.json()["contrato"]["ok"] is True


def test_no_expect_is_byte_identical():
    """Sin `expect` el retorno no lleva `contrato` (comportamiento previo)."""
    api.DOC = Document("contract-none")
    client = TestClient(api.app)
    r = client.post("/api/commands/batch", json={"actions": _two_boxes_actions()})
    assert r.status_code == 200
    assert "contrato" not in r.json()


# --------------------------------------------------------- Document puro (callback directo)
def test_execute_many_verify_callback_rollback():
    doc = Document("cb")

    def failing(scene, created):
        return [{"check": "x", "ok": False, "actual": 1, "esperado": {"max": 0}}]

    with __import__("pytest").raises(ContractError):
        doc.execute_many(_two_boxes_actions(), verify=failing)
    assert len(doc.scene) == 0 and not doc.can_undo


def test_contract_repeated_failure_no_corruption_strict(monkeypatch):
    """Tortura: un contrato fallido repetido en modo ESTRICTO no corrompe el documento."""
    monkeypatch.setattr(document, "_STRICT", True)
    doc = Document("strict")
    doc.execute("create_box", {"name": "seed", "width": 10, "depth": 10, "height": 10})

    def failing(scene, created):
        return [{"check": "x", "ok": False}]

    for _ in range(5):
        with __import__("pytest").raises(ContractError):
            doc.execute_many(
                [{"type": "create_box", "params": {"name": "t", "width": 10, "depth": 10, "height": 10}}],
                verify=failing,
            )
    assert doc.check_integrity() == []
    assert len(doc.scene) == 1  # solo la semilla
