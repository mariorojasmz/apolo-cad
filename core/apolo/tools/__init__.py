"""Lo común a los clientes IA de las tools de Apolo (MCP por stdio y chat de la app).

`destino`: a qué API habla el cliente fino en ESTE hilo. `catalogo`: qué tools del MCP ve el
chat (y cuáles no, con el motivo). `simulacion`: la tool `simulate`; `mcp_server.py` la
registra en SU `mcp` con `registrar(mcp, api)` (sin importar `apolo.mcp_server`: con `-m` el
servidor es `__main__`). Nada de aquí importa `apolo.api`, `apolo.state` ni `apolo.mcp_server`:
las tools son clientes HTTP, no tocan el documento.
"""
