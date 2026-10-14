"""El chat de la app viene APAGADO (D19 del plan chat-cliente-igual: por ahora Apolo se usa por
MCP desde Claude). Sólo `APOLO_CHAT=1` lo prende, leído en cada petición; apagado, el endpoint
responde 503 sin tomar cupo ni tocar el modelo, y `GET /api/health` lo dice para que la UI
oculte el panel del asistente."""

from __future__ import annotations

import anthropic
import pytest

pytest.importorskip("mcp")  # el chat de la app usa las tools del MCP

from fastapi.testclient import TestClient  # noqa: E402

import apolo.api.main as api  # noqa: E402
from apolo.agent import chat  # noqa: E402
from apolo.doc import Document  # noqa: E402

PEDIDO = {"messages": [{"role": "user", "content": "hola"}], "auto": False}


@pytest.fixture
def cliente(monkeypatch):
    doc = Document("chat-apagado")
    doc.execute("create_box", {"name": "Base", "width": 100, "depth": 100, "height": 20})
    monkeypatch.setattr(api, "DOC", doc)
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: pytest.fail("llamó al modelo"))
    monkeypatch.setattr(chat, "abrir", lambda *a, **k: pytest.fail("abrió un turno"))
    return TestClient(api.app)


@pytest.mark.parametrize("valor", [None, "", "0", "si", "true", " 2 "])
def test_apagado_salvo_apolo_chat_1(cliente, monkeypatch, valor):
    if valor is None:
        monkeypatch.delenv("APOLO_CHAT", raising=False)
    else:
        monkeypatch.setenv("APOLO_CHAT", valor)
    monkeypatch.setenv("APOLO_CHAT_MAX", "1")
    chat.CUPO.tomar()  # el cupo está lleno: apagado responde 503, no 429
    try:
        r = cliente.post("/api/agent/chat", json=PEDIDO)
    finally:
        chat.CUPO.soltar()
    assert r.status_code == 503 and r.json()["detail"] == chat.APAGADO
    assert chat.CUPO.activos == 0
    assert chat.activo() is False
    assert cliente.get("/api/health").json()["chat"] is False


def test_prendido_con_apolo_chat_1_sin_reiniciar(cliente, monkeypatch):
    monkeypatch.delenv("APOLO_CHAT", raising=False)
    assert cliente.get("/api/health").json()["chat"] is False
    monkeypatch.setenv("APOLO_CHAT", " 1 ")  # se lee en cada petición
    assert chat.activo() is True
    assert cliente.get("/api/health").json()["chat"] is True
    turnos = []
    monkeypatch.setattr(chat, "abrir", lambda *a, **k: turnos.append(1) or (s for s in ()))
    r = cliente.post("/api/agent/chat", json=PEDIDO)
    assert r.status_code == 200 and turnos == [1]
