---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: Sólo el plan; nada construido. Espera saldo de tokens (Mario, 2026-10-10)
descripcion: Borrar piezas desde el agente es una tool más y responde corto, así que corregir una máquina gasta menos
---

# Borrar y corregir piezas sin gastar de más

## Estado y origen

En la piloto (proyecto 2) el agente tuvo que borrar comandos por `POST /api/commands/remove` con
PowerShell: no hay tool MCP para eso, y la respuesta trae la escena COMPLETA con mallas
(`api/routers/commands.py:245-249` devuelve `_state_or_error(...)` sin filtro). Para borrar el
travesaño del centro (3 comandos) hubo que recortar la salida a mano. Es una ESCRITURA que el MCP
no cubre, contra la regla raíz de que el registro entero se maneja por tools. Mejora 5 de la
lista que pidió Mario.

## El problema / lo que hay hoy

- Sin tool `remove_commands`: cirugía = REST propio (sin job, sin recibo, sin golden).
- La respuesta completa de una mutación por REST puede pesar MB en una máquina de 200 piezas.

## Decisiones (para vetar)

- **D1. Tool `remove_commands(ids, detail="diff")`** por el embudo de mutaciones del MCP (`_mutacion`,
  job con recibo): devuelve las piezas que desaparecieron, las uniones que se fueron con ellas y
  `total_solidos`.
- **D2. Borrado con dependientes opcional**: `con_dependientes: true` agrega solo los `fasten`,
  `ground` y miembros de grupo que referencian los ids (hoy el agente los busca con
  `find_commands`), y el resultado los lista.
- **D3. Golden y catálogo del chat**: la tool entra a `tools/catalogo.py` (`muta`) y a
  `scripts/golden_mcp_casos.py` ([core/apolo](../../core/apolo/CLAUDE.md) § MCP).

## Fases

- **F0 (S, sólo lectura)**: medir el tamaño de la respuesta de `/api/commands/remove` en el
  proyecto 2 (una pieza).
- **F1 (S, `api`)**: `detail=diff` en el endpoint (sin él, byte-idéntico para la UI) y D2.
- **F2 (S, `mcp_server.py` + golden + catálogo)**: D1 y D3.
- **F3 (S, verificación)**: por MCP, borrar y restaurar una pieza del proyecto 2; respuesta < 5 KB.

## Lo que este plan NO hace

- No toca undo/redo (ya responden con `brief_paso`).

## Riesgos

- Un borrado con dependientes que arrastra de más → la lista va en la respuesta y es un undo.

## Bitácora
