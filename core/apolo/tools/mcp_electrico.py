"""Las tools MCP de LECTURA del tablero eléctrico (plan V8.1, D8): `get_circuit` y
`electrical_check`.

Cliente fino como el resto: sólo HTTP (`GET /api/electrico/…`). Viven fuera de `mcp_server.py`
(congelado por el trinquete de tamaño), que las registra con `mcp.tool()` al final de sus
tools; `_api` se busca en `mcp_server` en CADA llamada, así un test que parchea
`mcp_server._api` (o el golden, que parchea `httpx.Client`) también las ve. Los comandos que
declaran el tablero (`add_device`, `add_wire`, `add_cable`) no tienen tool propia: entran por
`run_command`/`run_batch` como el resto del registro.
"""

from __future__ import annotations

import json


def _api(method: str, path: str, **kwargs):
    from apolo import mcp_server

    return mcp_server._api(method, path, **kwargs)


def get_circuit(designacion: str | None = None) -> str:
    """Circuito del TABLERO ELÉCTRICO declarado (add_device/add_wire/add_cable): dispositivos
    con sus bornes y la RED de cada borne, redes con su tensión inferida (qué potencial puede
    llegar a cada una con todos los contactos cerrados), conductores y cables. `designacion`
    («-Q1», «=Faja1», «-M1») filtra a esos dispositivos y las redes y conductores que los
    tocan; úsalo para leer la designación que se asignó sola o para revisar un aparato antes
    de cablearlo. Read-only."""
    params = {"designacion": designacion} if designacion else {}
    return json.dumps(_api("GET", "/api/electrico/circuito", params=params).json(),
                      ensure_ascii=False)


def electrical_check() -> str:
    """ERC del tablero eléctrico: cortocircuitos, tensiones cruzadas (una bobina de 24 VDC en
    220 VAC), motores sin protección, puesta a tierra, bornes sueltos, colores IEC 60204-1 y
    parada de emergencia, cada regla con su norma. Devuelve {estado ok|aviso|error|sin_carril,
    errores, avisos, reglas}. delivery_check lo incluye y, en un lote, el contrato
    {"erc": "sin_errores"} lo exige antes de aceptar el cableado. Read-only."""
    return json.dumps(_api("GET", "/api/electrico/check").json(), ensure_ascii=False)


#: Las tools en el orden en que `mcp_server` las registra.
HERRAMIENTAS = (get_circuit, electrical_check)
