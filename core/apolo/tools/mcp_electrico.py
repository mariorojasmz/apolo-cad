"""Las tools MCP de LECTURA del tablero eléctrico (plan V8.1, D8): `get_circuit` y
`electrical_check`.

Cliente fino como el resto: sólo HTTP (`GET /api/electrico/…`). Viven fuera de `mcp_server.py`
(congelado por el trinquete de tamaño), que las registra al final con `registrar(mcp, api)`,
como `simulacion.py`. NO importa `apolo.mcp_server`: con `python -m apolo.mcp_server` el
servidor es `__main__` y el import cargaría una segunda copia (`tests/test_mcp_registro.py`).
`api` busca el `_api` del servidor en CADA llamada, así un test que parchea `mcp_server._api`
(o el golden, que parchea `httpx.Client`) también las ve. Los comandos que declaran el tablero
(`add_device`, `add_wire`, `add_cable`) no tienen tool propia: entran por
`run_command`/`run_batch` como el resto del registro.
"""

from __future__ import annotations

import json


def registrar(mcp, api) -> None:
    """Registra `get_circuit` y `electrical_check`, en ese orden, en `mcp` (el del servidor que
    corre). `api(method, path, **kw)` es su `_api`, buscado en cada llamada."""

    @mcp.tool()
    def get_circuit(designacion: str | None = None, tablero: bool = False) -> str:
        """Circuito del TABLERO ELÉCTRICO declarado (add_device/add_wire/add_cable): dispositivos
        con la RED de cada borne, redes con su tensión inferida (contactos cerrados), conductores
        y cables. `designacion` («-Q1», «=Faja1») filtra a esos dispositivos y lo que los toca
        (lee la designación asignada sola). `tablero=true` suma `tableros`: lo que la persona ve
        del tablero armado en el visor (veredicto, ítems, largos, llenado). Read-only."""
        params = {"designacion": designacion} if designacion else {}
        if tablero:
            params["tablero"] = "true"
        return json.dumps(api("GET", "/api/electrico/circuito", params=params).json(),
                          ensure_ascii=False)

    @mcp.tool()
    def electrical_check() -> str:
        """ERC del tablero eléctrico: cortocircuitos, tensiones cruzadas (una bobina de 24 VDC en
        220 VAC), motores sin protección, puesta a tierra, bornes sueltos, colores IEC 60204-1 y
        parada de emergencia, cada regla con su norma. Devuelve {estado ok|aviso|error|sin_carril,
        errores, avisos, reglas}. delivery_check lo incluye y, en un lote, el contrato
        {"erc": "sin_errores"} lo exige antes de aceptar el cableado. Read-only."""
        return json.dumps(api("GET", "/api/electrico/check").json(), ensure_ascii=False)
