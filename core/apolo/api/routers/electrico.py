"""Rutas del tablero eléctrico (plan V8.1, D8): el circuito y su chequeo (ERC); y el tablero ARMADO
que lee el panel «Tablero» del visor (plan V8.5 D13, D15: `services/tablero_panel.py`, la misma
fuente que `get_circuit tablero=true`).

Lecturas: bajo `STATE_LOCK` se lee el `ModeloElectrico` que dejó el último regenerate y se
analiza (datos puros, ~1 ms en la faja piloto). El dominio es de `services/electrico.py`; los
comandos que lo declaran (`add_device`, `add_wire`, `add_cable`) entran por `/api/commands`
como cualquier otro.
"""

from __future__ import annotations

from fastapi import APIRouter

from apolo.services.electrico import chequeo, circuito
from apolo.services.errors import ServiceError
from apolo.services.tablero_panel import panel, paneles, tableros
from apolo.state import STATE_LOCK

from ..fea_runs import _http_error
from ..session import S

router = APIRouter()


@router.get("/api/electrico/circuito")
def get_circuit(designacion: str | None = None, tablero: bool = False) -> dict:
    """El circuito del tablero: dispositivos con sus bornes y la red de cada uno, redes con su
    tensión inferida, conductores y cables. `designacion` («-Q1», «=Faja1») filtra a esos
    dispositivos y lo que los toca; una ubicación («+TAB1»), a lo que está en ella; un cable
    («-W4»), a sus hilos y los aparatos que tocan. `tablero=true` suma `tableros`: lo que ve la persona en el
    panel de cada tablero armado (veredicto, ítems, largos, llenado, calentamiento), sin los
    recorridos 3D. Read-only."""
    with STATE_LOCK:
        try:
            out = circuito(S.doc, designacion)
            return {**out, "tableros": paneles(S.doc)} if tablero else out
        except ServiceError as exc:
            raise _http_error(exc) from exc


@router.get("/api/electrico/check")
def electrical_check() -> dict:
    """ERC del tablero (cortocircuitos, tensiones cruzadas, motores sin protección, tierra,
    bornes sueltos, colores IEC 60204-1, parada de emergencia) con su resumen y las reglas que
    corrieron sin hallazgos (`revisadas`). Read-only."""
    with STATE_LOCK:
        return chequeo(S.doc)


@router.get("/api/tablero")
def get_tableros() -> dict:
    """Los tableros armados (`layout_tablero`) del documento: [{ubicacion, comando, armado}]. Vacío
    = el panel muestra su estado vacío. Read-only."""
    with STATE_LOCK:
        return {"tableros": tableros(S.doc)}


@router.get("/api/tablero/{ubicacion}")
def get_tablero(ubicacion: str) -> dict:
    """El panel de un tablero armado («+TAB1» o «TAB1»): veredicto, ítems con las piezas que
    señalan, la junta de la puerta y el detalle con el recorrido de cada conductor en mm de mundo.
    Read-only (el ruteo se recalcula al leer, ~60 ms en la faja piloto)."""
    with STATE_LOCK:
        try:
            return panel(S.doc, ubicacion)
        except ServiceError as exc:
            raise _http_error(exc) from exc
