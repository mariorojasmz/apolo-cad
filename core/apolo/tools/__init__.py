"""Lo común a los clientes IA de las tools de Apolo (MCP por stdio y chat de la app).

`destino`: a qué API habla el cliente fino en ESTE hilo. `catalogo`: qué tools del MCP ve el
chat (y cuáles no, con el motivo). El resto son las tools, por tema, que `mcp_server.py`
registra en SU `mcp` con `registrar(mcp, _api, …)` EN EL LUGAR de su bloque (el orden de
`list_tools()` es el del golden): una tool nueva va al módulo de su tema, nunca en línea en
`mcp_server.py`. Los bloques que eran de `mcp_server.py` (`consulta`, `validacion`, `proyectos`,
`introspeccion`, `topologia`, `fabricacion`, `visibilidad`, `calculo`; plan
partir-nucleo-congelado, D5) devuelven sus tools por nombre y el servidor las re-exporta con
`globals().update(...)`. `_api`, `_mutacion`, `_submit_and_wait` y `_paso` llegan como lambdas
TARDÍAS (un test que parchea `mcp_server._api` llega aquí). Nada de aquí importa `apolo.api`,
`apolo.state` ni `apolo.mcp_server` (con `-m` el servidor es `__main__` y la tool caería en otra
copia): las tools son clientes HTTP, no tocan el documento.
"""
