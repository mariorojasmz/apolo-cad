"""Correr un escenario de la co-simulación sobre un documento, en DOS fases (plan
pedidos-de-extensiones-iii, D1–D4): la API que una extensión usa para su propia prueba virtual
(re-exportada en `extensiones_api.SUPERFICIE`).

- `preparar_corrida(doc, escenario, programas=…)`: bajo el `STATE_LOCK` del llamador (en una ruta
  de extensión, dentro de `leer_documento`). Sólo EXTRAE: el snapshot que el worker necesita. Un
  escenario que el núcleo no toma es `EscenarioRechazado`, con el texto EXACTO del 400/404 que
  daría `POST /api/cosim/run`.
- `correr_corrida(preparada)`: FUERA de todo lock. El worker en su proceso (`cosim.proceso`, que
  pone las corridas en fila con `COSIM_LOCK`); devuelve su JSON tal cual (trazas, eventos, final,
  hipótesis, resumen con la huella). Si el worker no devuelve resultado: `CorridaFallida`.

Es el mismo camino que los pasos (a) y (b) de la API (`api/routers/cosim.py::_correr`), sin lo que
es de la API: veredicto de aserciones, guardar el resultado, vigencia ni PLC de afuera (D2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import ServiceError


class CorridaError(Exception):
    """Una corrida que no se pudo preparar o correr; `motivo` = el texto del núcleo."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


class EscenarioRechazado(CorridaError):
    """El núcleo no toma el escenario sobre ese documento (el 400/404 de la API, con su texto)."""

    def __init__(self, motivo: str, status_code: int = 400) -> None:
        super().__init__(motivo)
        self.status_code = status_code


class CorridaFallida(CorridaError):
    """El worker de la co-simulación no devolvió un resultado (se cayó, falló o pasó el tiempo)."""


@dataclass(frozen=True)
class CorridaPreparada:
    """Lo que `correr_corrida` necesita, en datos puros: nada del documento viaja después."""

    nombre: str | None      # el escenario guardado, o None si vino en memoria
    escenario: dict         # el dict del escenario (D12 de V8.3)
    snapshot: Any           # `cosim.datos.CosimSnapshot`: opaco para la extensión


def preparar_corrida(doc, escenario, *, programas: list[dict] | None = None) -> CorridaPreparada:
    """El snapshot de `escenario` (nombre de uno guardado o el dict) sobre `doc`. Bajo el
    `STATE_LOCK` del llamador. `programas` pone otros ST encima, por PLC, sin guardarlos (como
    `test_plc`). `EscenarioRechazado` si el núcleo no lo toma."""
    from . import escenarios as E
    from .cosim_snapshot import snapshot_cosim

    try:
        nombre, esc = E.resolver(doc, escenario)
        snap = snapshot_cosim(doc, esc, programas=programas)
    except ServiceError as exc:
        raise EscenarioRechazado(str(exc.detail), exc.status_code) from exc
    return CorridaPreparada(nombre, esc, snap)


def correr_corrida(preparada: CorridaPreparada, *, timeout_s: float | None = None) -> dict:
    """El resultado del worker para una corrida preparada. FUERA de todo lock; espera su turno
    tras las demás corridas. `CorridaFallida` si el worker no devuelve resultado."""
    from apolo.cosim.proceso import CosimError, correr_en_proceso

    try:
        return correr_en_proceso(preparada.snapshot, timeout_s=timeout_s)
    except CosimError as exc:
        raise CorridaFallida(str(exc)) from exc
