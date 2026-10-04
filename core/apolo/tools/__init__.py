"""Lo común a los clientes IA de las tools de Apolo (MCP por stdio y chat de la app).

`destino`: a qué API habla el cliente fino en ESTE hilo. El catálogo de tools del chat
(`catalogo.py`) llega con la F4 del plan chat-cliente-igual. Nada de aquí importa `apolo.api`
ni `apolo.state`: las tools son clientes HTTP, no tocan el documento.
"""
