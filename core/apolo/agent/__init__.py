"""El chat de la app: un cliente HTTP más de la API (plan chat-cliente-igual).

`chat` (el turno), `herramientas` (las tools del MCP), `modelo` (el cliente de Anthropic) y
`eventos` (el SSE de la UI). Este paquete no re-exporta nada: importar `apolo.agent` no carga
ningún módulo, y ninguno llega a `apolo.state` ni a `apolo.api` (gate en
`tests/test_chat_http_capas.py`). `script_wrapper` es aparte: el proceso hijo de `sandbox.py`.
"""
