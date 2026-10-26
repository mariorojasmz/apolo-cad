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

`get_circuit(tablero=true)` resume el panel de cada tablero (`resumen_tableros`: sólo elige
claves del mismo JSON del REST, que no cambia); el panel entero va con `completo=true`
([pedidos-de-extensiones-ii](../../../docs/plans/pedidos-de-extensiones-ii.md) D5).
"""

from __future__ import annotations

import json

#: Lo que un ítem del panel lleva para la cámara del visor y no para el agente.
_SOLO_VISOR = ("piezas", "decimales")
SEGUIR = ("get_circuit() da el circuito (dispositivos, redes, conductores); "
          "get_circuit(tablero=true, completo=true), el panel entero de cada tablero")


def _item(it: dict) -> dict:
    out = {k: v for k, v in it.items() if k not in _SOLO_VISOR}
    if not out.get("conductores"):
        out.pop("conductores", None)
    if out.get("unidad") == "":
        out.pop("unidad")
    return out


def resumen_tablero(p: dict) -> dict:
    """El panel de UN tablero (`services/tablero_panel.panel`) en lo que el agente necesita: el
    veredicto, cuántas cosas tiene, cada ítem con su motivo y los conductores que toca. Sólo
    elige claves (la regla del veredicto y de los ítems es del servicio); un tablero sin armar
    pasa tal cual (ya es corto)."""
    if not p.get("armado"):
        return p
    det = p.get("detalle") or {}
    gab = p.get("gabinete") or {}
    return {
        "ubicacion": p.get("ubicacion"), "comando": p.get("comando"), "armado": True,
        "gabinete": {k: gab[k] for k in ("ref", "medidas_mm") if k in gab},
        "veredicto": p.get("veredicto"),
        "cuentas": {**{k: len(det.get(k) or []) for k in ("aparatos", "conductores", "canaletas")},
                    "cables_de_campo": len(det.get("cables") or [])},
        "items": [_item(it) for it in p.get("items") or []],
        "bien": [_item(it) for it in det.get("bien") or []],
    }


def resumen_tableros(circuito: dict) -> dict:
    """`get_circuit(tablero=true)`: el resumen de cada tablero y el `resumen` del circuito, sin
    las listas del circuito (~30 KB → ~2 KB en la piloto: plan pedidos-de-extensiones-ii D5)."""
    return {"tableros": [resumen_tablero(p) for p in circuito.get("tableros") or []],
            "resumen": circuito.get("resumen"), "seguir": SEGUIR}


def registrar(mcp, api) -> None:
    """Registra `get_circuit` y `electrical_check`, en ese orden, en `mcp` (el del servidor que
    corre). `api(method, path, **kw)` es su `_api`, buscado en cada llamada."""

    @mcp.tool()
    def get_circuit(designacion: str | None = None, tablero: bool = False, completo: bool = False) -> str:
        """Circuito del TABLERO ELÉCTRICO declarado (add_device/add_wire/add_cable): dispositivos
        con la RED de cada borne, redes con su tensión inferida (contactos cerrados), conductores
        y cables. `designacion` («-Q1», «=Faja1») filtra a esos dispositivos y lo que los toca
        (lee la designación asignada sola); una ubicación («+TAB1») da lo que está en ella y un
        cable («-W4»), sus hilos y los aparatos que tocan. `tablero=true` da, EN VEZ del circuito,
        un RESUMEN de cada tablero armado (veredicto, cuentas, lo que pide atención con su motivo
        y los `conductores` que toca, lo que cumple) más el `resumen` del circuito; `completo=true`
        da el circuito entero y el panel entero de cada tablero, como lo ve la persona en el visor
        (canaletas con su llenado, cada conductor con su largo: pesa decenas de KB). Con circuito
        de AIRE (add_device neumático + add_tubo) el circuito suma `neumatica` {lineas con su
        presión, tubos} y los `puertos` de cada aparato de aire. Read-only."""
        params = {"designacion": designacion} if designacion else {}
        if tablero or completo:
            params["tablero"] = "true"
        out = api("GET", "/api/electrico/circuito", params=params).json()
        if tablero and not completo:
            out = resumen_tableros(out)
        return json.dumps(out, ensure_ascii=False)

    @mcp.tool()
    def electrical_check() -> str:
        """ERC del tablero eléctrico: cortocircuitos, tensiones cruzadas (una bobina de 24 VDC en
        220 VAC), motores sin protección, puesta a tierra, bornes sueltos, colores IEC 60204-1 y
        parada de emergencia, cada regla con su norma; con tablero armado y cables de campo, sus
        reglas (canaletas, largos, lo que gira), las piezas de seguridad sin circuito y la altura
        de los mandos; con circuito de aire, el ERC neumático (`medio: "aire"`: válvula de corte con
        escape ISO 4414, puertos libres, presión de trabajo, caudal, pandeo e impacto del cilindro).
        Devuelve {estado ok|aviso|error|sin_carril, errores, avisos, reglas,
        revisadas}: `revisadas` = las reglas que corrieron sin hallazgos (no salen en `reglas`).
        delivery_check lo incluye y, en un lote, el contrato
        {"erc": "sin_errores"} lo exige antes de aceptar el cableado. Read-only."""
        return json.dumps(api("GET", "/api/electrico/check").json(), ensure_ascii=False)
