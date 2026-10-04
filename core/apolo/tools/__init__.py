"""Lo común a los clientes IA de las tools de Apolo (MCP por stdio y chat de la app).

`destino`: a qué API habla el cliente fino en ESTE hilo. `catalogo`: qué tools del MCP ve el
chat (y cuáles no, con el motivo). Nada de aquí importa `apolo.api` ni `apolo.state`: las
tools son clientes HTTP, no tocan el documento.
"""
