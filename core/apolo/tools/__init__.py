"""Lo común a los clientes IA de las tools de Apolo (MCP por stdio y chat de la app).

`destino`: a qué API habla el cliente fino en ESTE hilo. `catalogo`: qué tools del MCP ve el
chat (y cuáles no, con el motivo). `simulacion`: la tool `simulate`, registrada en el `mcp`
de `mcp_server.py` (que la importa al final). Nada de aquí importa `apolo.api` ni
`apolo.state`: las tools son clientes HTTP, no tocan el documento.
"""
