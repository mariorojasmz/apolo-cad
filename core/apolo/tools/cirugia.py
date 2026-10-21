"""La tool MCP `remove_commands` (plan cirugia-liviana, D1 y D3): borrar comandos del log sin
volcar la escena.

Cliente fino: `POST /api/commands/remove?detail=diff` por el embudo de mutaciones del servidor
(`_mutacion` de `mcp_server.py`: job con recibo). Vive fuera de `mcp_server.py` (congelado por el
trinquete de tamaño), que la registra al final con `registrar(mcp, mutacion)`. NO importa
`apolo.mcp_server`: con `python -m apolo.mcp_server` el servidor es `__main__` y el import
cargaría una segunda copia (`tests/test_mcp_registro.py`). `mutacion` busca el `_mutacion` del
servidor en CADA llamada, así un test que parchea `_api` o `_submit_and_wait` también la ve.
"""

from __future__ import annotations


def registrar(mcp, mutacion) -> None:
    """Registra `remove_commands` en `mcp` (el del servidor que corre). `mutacion(method, path,
    body, detail, params=...)` es su `_mutacion`, buscado en cada llamada."""

    @mcp.tool()
    def remove_commands(
        ids: list[str], con_dependientes: bool = False, detail: str = "diff"
    ) -> str:
        """Borra comandos del log por command_id (cirugía: quitar una pieza, un sub-ensamblaje o
        uniones) en UN cambio atómico, deshacible con UN undo. Si queda una referencia rota (un
        fijador, anclaje, junta o mate que nombra una pieza borrada) no borra NADA y el error dice
        cuál estorba, lista los dependientes y cuáles arrastraría `con_dependientes=true`. Éste
        borra además los fasten y ground que nombran las piezas de esos comandos y los quita de
        sus grupos, sin buscarlos con find_commands; la
        respuesta los lista en `dependientes` y `grupos_editados` (un grupo que quedaría vacío no
        se toca: lo dice `avisos`). Juntas y mates nunca se arrastran: bórralos tú si sobran.
        `detail`: "diff" (def.) responde corto —`comandos_borrados`, `piezas_borradas`,
        `uniones_borradas` y `total_solidos`—; "full" lista toda la escena. Si tarda, recibes un
        RECIBO {"job": id}: recógelo con get_job(id) y NO reenvíes el borrado."""
        body: dict = {"ids": ids}
        if con_dependientes:
            body["con_dependientes"] = True
        params = None if detail == "full" else {"detail": "diff"}
        return mutacion("POST", "/api/commands/remove", body, detail, params=params)
