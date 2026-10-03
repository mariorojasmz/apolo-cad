"""Texto PARA LA PERSONA del registro de comandos: sólo datos.

La `description` de cada modelo pydantic es del AGENTE (larga a propósito, con nombres de
parámetros) y no se toca: la leen el MCP y el agente de la app. Lo que lee una persona
vive aquí y lo sirve la vista persona (`vista_persona.py`, `GET /api/schemas?vista=persona`).
Plan: docs/plans/texto-agente-vs-persona.md (D3–D5, D8). Gate: `tests/test_pistas.py`.

Cómo se escribe una pista (ui/CLAUDE.md § «Texto y ayuda»): una frase que termina en punto,
≤ 120 caracteres, tuteo neutro latinoamericano, dice lo que el comando HACE por la persona
y usa el vocabulario de «Una cosa, un nombre» (pieza, croquis, junta, unión, grupo…).
"""

from __future__ import annotations

#: Pestaña del ribbon por categoría del `REGISTRY`: orden y rótulo. `None` = sin pestaña
#: (las variables tienen su botón propio). Toda categoría nueva tiene que estar aquí: con la
#: lista escrita a mano en la UI, la de superficies quedó sin pestaña (D8).
PESTANAS: dict[str, dict | None] = {
    "crear": {"orden": 1, "rotulo": "Crear"},
    "croquis": {"orden": 2, "rotulo": "Croquis"},
    "superficies": {"orden": 3, "rotulo": "Superficies"},
    "modificar": {"orden": 4, "rotulo": "Modificar"},
    "ensamblaje": {"orden": 5, "rotulo": "Ensamblar"},
    "biblioteca": {"orden": 6, "rotulo": "Biblioteca"},
    "robotica": {"orden": 7, "rotulo": "Robótica"},
    "variables": None,
}

#: Pista de cada comando, por tipo (D4). Un tipo sin pista cae a la primera frase limpia de
#: su descripción (red de transición): el gate exige una por comando.
PISTAS: dict[str, str] = {}

#: Pista de campo, por «Modelo.campo», SÓLO donde un campo anula a otro o depende de otro
#: (D5). Ninguna más: la pista en todos los campos está prohibida por ui/CLAUDE.md.
PISTAS_CAMPO: dict[str, str] = {}
