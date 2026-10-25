"""Las tools MCP de la extensión falsa: `prueba_hola` corre el comando `prueba.hola` como mutación
(job con recibo, igual que `run_command`) y `prueba_informe` pide su entregable como job con
`pedir_entregable` (lo guarda en `path` o da el recibo que `get_job` recoge). Firma de
`Extension.tools_mcp`: `registrar(mcp, api, mutacion, esperar)`."""

from __future__ import annotations


def registrar(mcp, api, mutacion, esperar) -> None:
    @mcp.tool()
    def prueba_hola(lado: float = 50) -> str:
        """Crea una caja de prueba de la extensión falsa de la suite (comando prueba.hola)."""
        return mutacion("POST", "/api/commands", {"type": "prueba.hola", "params": {"lado": lado}},
                        "diff")

    @mcp.tool()
    def prueba_informe(path: str) -> str:
        """Guarda en `path` el informe de texto de la extensión falsa de la suite (como job)."""
        from apolo.extensiones_api import pedir_entregable

        return pedir_entregable(api, esperar, "/api/prueba/informe.txt", {}, path)


def registrar_con_punto(mcp, api, mutacion, esperar) -> None:
    @mcp.tool(name="prueba.hola")
    def hola() -> str:
        """Nombre con punto: la API de Anthropic no lo acepta (A7)."""
        return "no"
