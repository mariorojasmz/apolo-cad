"""Rutas del tablero eléctrico (plan V8.1, D8): el circuito y su chequeo (ERC).

Lecturas: bajo `STATE_LOCK` se lee el `ModeloElectrico` que dejó el último regenerate y se
analiza (datos puros, ~1 ms en la faja piloto). El dominio es de `services/electrico.py`; los
comandos que lo declaran (`add_device`, `add_wire`, `add_cable`) entran por `/api/commands`
como cualquier otro.
"""

from __future__ import annotations

from fastapi import APIRouter

from apolo.services.electrico import chequeo, circuito
from apolo.services.errors import ServiceError
from apolo.state import STATE_LOCK

from ..fea_runs import _http_error
from ..session import S

router = APIRouter()


@router.get("/api/electrico/circuito")
def get_circuit(designacion: str | None = None) -> dict:
    """El circuito del tablero: dispositivos con sus bornes y la red de cada uno, redes con su
    tensión inferida, conductores y cables. `designacion` («-Q1», «=Faja1») filtra a esos
    dispositivos y lo que los toca. Read-only."""
    with STATE_LOCK:
        try:
            return circuito(S.doc, designacion)
        except ServiceError as exc:
            raise _http_error(exc) from exc


@router.get("/api/electrico/check")
def electrical_check() -> dict:
    """ERC del tablero (cortocircuitos, tensiones cruzadas, motores sin protección, tierra,
    bornes sueltos, colores IEC 60204-1, parada de emergencia) con su resumen. Read-only."""
    with STATE_LOCK:
        return chequeo(S.doc)
