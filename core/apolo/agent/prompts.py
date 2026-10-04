"""System prompt del chat de la app. Sale de la guía única (`design/instrucciones.py`, plan
chat-cliente-igual F6): el mismo criterio de ingeniería y la misma guía técnica que recibe el
MCP, más las reglas propias de la app. Se edita allá, nunca aquí."""

from apolo.design.instrucciones import system_prompt_chat

SYSTEM_PROMPT = system_prompt_chat()
