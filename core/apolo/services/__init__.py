"""Servicios de dominio: la lógica que LEE un `Document` y que comparten sus clientes (la
API hoy; el agente, cuando la necesite) — mapas por pieza de los planos, datos de la lámina
de instalación, evaluación de las cadenas de cotas.

Capas (plan `docs/plans/partir-api-main.md`, D2):
kernel/commands/doc/library/drawing/fea/assembly/robotics ← services ← api y agent. Cada
función recibe `doc` EXPLÍCITO y jamás lee un global de sesión; no importa `fastapi`,
`apolo.api` ni `apolo.agent`; no toma locks (el llamador sostiene `STATE_LOCK`); conserva
perezosos los imports pesados; lanza errores de dominio, nunca `HTTPException`. Lo hace
cumplir `tests/test_capas_services.py`; las reglas, en el `CLAUDE.md` de este paquete.

El paquete no importa sus módulos: cada llamador importa el que usa.
"""
