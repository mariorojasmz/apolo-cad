"""Ganchos que la API inyecta al chat del agente.

El chat corre minutos (varias vueltas del LLM) y entretanto el usuario puede abrir o crear
otro proyecto o restaurar una revisión: el documento capturado al empezar deja de ser el
activo. Sin guardia, el agente seguía mutando ese objeto HUÉRFANO mientras el autosave
guardaba el documento NUEVO → sus cambios se perdían en silencio y razonaba sobre estado
viejo. Además el agente importaba `apolo.api.main` (dependencia circular api ↔ agent):
ahora la API le pasa estos ganchos y el agente no conoce el transporte.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from apolo.state import STATE_LOCK

PROYECTO_CAMBIO = (
    "El proyecto activo cambió mientras trabajaba (se abrió otro proyecto o se restauró una "
    "revisión): me detuve sin aplicar más cambios. Abre el proyecto correcto y repite el pedido."
)


class ProjectChanged(Exception):
    """El documento del chat ya no es el activo: la mutación NO se aplicó."""


def _siempre_vivo() -> bool:
    return True


def _nada() -> None:
    return None


@dataclass(frozen=True)
class AgentHooks:
    """`alive()`: ¿el documento del chat sigue siendo el activo? (en las mutaciones se
    llama BAJO STATE_LOCK). `after_mutation()`: autosave, bajo el lock. `notify()`: aviso a
    los clientes, FUERA del lock. Los defaults (siempre vivo, no-ops) sirven a quien usa el
    agente sin API: tests y scripts."""

    alive: Callable[[], bool] = _siempre_vivo
    after_mutation: Callable[[], None] = _nada
    notify: Callable[[], None] = _nada


SIN_GANCHOS = AgentHooks()


def ensure_alive(hooks: AgentHooks) -> None:
    """Corta con ProjectChanged si el documento del chat ya no es el activo."""
    if not hooks.alive():
        raise ProjectChanged(PROYECTO_CAMBIO)


@contextlib.contextmanager
def mutation_guard(hooks: AgentHooks) -> Iterator[None]:
    """STATE_LOCK + revalidación del documento en la MISMA adquisición: check y mutación
    atómicos, sin TOCTOU (mismo patrón que la guardia de jobs `_sync_or_job` de la API).
    Nunca hagas `yield` del stream SSE dentro: cada `next()` puede correr en otro hilo."""
    with STATE_LOCK:
        ensure_alive(hooks)
        yield
