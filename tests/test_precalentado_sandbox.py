"""La API precalienta el worker del sandbox al arrancar (plan sandbox-caliente, D7).

El arranque llama a `sandbox.prewarm()` (un hilo, idempotente) ANTES de abrir el proyecto
reciente, salvo con `APOLO_SANDBOX_PREWARM=0`, que es como corre la suite (`conftest.py`).
Se corre el handler de `startup` de verdad, con `prewarm` e `initialize_store` falsos: ni
worker real ni SQLite.
"""

from __future__ import annotations

import asyncio
import os

import pytest

import apolo.api.main as api
import apolo.sandbox as sandbox
from apolo.api.ws import WS


@pytest.fixture
def arranque(monkeypatch, tmp_path):
    """Corre el `startup` de la API y devuelve en qué orden llamó a lo que importa."""
    llamadas: list[str] = []
    monkeypatch.setattr(sandbox, "prewarm", lambda: llamadas.append("prewarm"))
    monkeypatch.setattr(api, "initialize_store", lambda path: llamadas.append("store"))
    monkeypatch.setattr(api, "session_marker", lambda *a, **k: None)
    monkeypatch.setattr(WS, "loop", WS.loop)  # el startup captura un loop que aquí se cierra
    monkeypatch.setenv("APOLO_DB", str(tmp_path / "apolo.db"))  # `db_path` crea su carpeta

    def correr() -> list[str]:
        llamadas.clear()
        asyncio.run(api._capture_loop())
        return list(llamadas)

    return correr


def test_la_suite_corre_sin_precalentar():
    assert os.environ.get("APOLO_SANDBOX_PREWARM") == "0"


@pytest.mark.parametrize("valor", [None, "1"])
def test_el_arranque_precalienta_antes_de_abrir_el_reciente(arranque, monkeypatch, valor):
    if valor is None:
        monkeypatch.delenv("APOLO_SANDBOX_PREWARM", raising=False)  # el default: encendido
    else:
        monkeypatch.setenv("APOLO_SANDBOX_PREWARM", valor)
    assert arranque() == ["prewarm", "store"]


def test_con_la_variable_en_0_no_precalienta(arranque, monkeypatch):
    monkeypatch.setenv("APOLO_SANDBOX_PREWARM", "0")
    assert arranque() == ["store"]
