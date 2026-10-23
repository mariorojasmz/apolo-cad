"""La tool MCP de la extensión falsa: `prueba_hola` corre el comando `prueba.hola` como mutación
(job con recibo, igual que `run_command`). Firma de `Extension.tools_mcp`:
`registrar(mcp, api, mutacion, esperar)`."""

from __future__ import annotations


def registrar(mcp, api, mutacion, esperar) -> None:
    @mcp.tool()
    def prueba_hola(lado: float = 50) -> str:
        """Crea una caja de prueba de la extensión falsa de la suite (comando prueba.hola)."""
        return mutacion("POST", "/api/commands", {"type": "prueba.hola", "params": {"lado": lado}},
                        "diff")


def registrar_con_punto(mcp, api, mutacion, esperar) -> None:
    @mcp.tool(name="prueba.hola")
    def hola() -> str:
        """Nombre con punto: la API de Anthropic no lo acepta (A7)."""
        return "no"
