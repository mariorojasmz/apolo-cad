"""Las validaciones de sujeción del MCP cuentan por defecto SOLO lo declarado.

`check_assembly` y `gravity_test` defaulteaban a `with_autodetect=True` (todo lo que se toca
cuenta como fijo) mientras la API y `delivery_check` usan lo DECLARADO: el agente veía verde
lo que la puerta de entrega después marcaba en rojo. Decisión de Mario (2026-10-03): default
False; True queda como exploración explícita.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mcp")  # el cliente MCP necesita el paquete mcp


class _Resp:
    def __init__(self, data):
        self._data = data
        self.content = b""

    def json(self):
        return self._data


@pytest.fixture
def cuerpos(monkeypatch):
    import apolo.mcp_server as mcp_server

    enviados: list[dict] = []

    def fake(method, path, json=None, **kw):
        enviados.append({"path": path, "json": json})
        return _Resp({})

    monkeypatch.setattr(mcp_server, "_api", fake)
    return mcp_server, enviados


def test_check_assembly_cuenta_solo_lo_declarado(cuerpos):
    mcp_server, enviados = cuerpos
    mcp_server.check_assembly()
    assert enviados[-1]["path"] == "/api/assembly/soundness"
    assert enviados[-1]["json"]["with_autodetect"] is False


def test_gravity_test_cuenta_solo_lo_declarado(cuerpos):
    mcp_server, enviados = cuerpos
    mcp_server.gravity_test()
    assert enviados[-1]["path"] == "/api/assembly/stability"
    assert enviados[-1]["json"]["with_autodetect"] is False


def test_autodetect_sigue_disponible_explicito(cuerpos):
    mcp_server, enviados = cuerpos
    mcp_server.check_assembly(with_autodetect=True)
    assert enviados[-1]["json"]["with_autodetect"] is True
