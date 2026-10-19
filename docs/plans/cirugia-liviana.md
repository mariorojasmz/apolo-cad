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

### F0 (2026-10-19)

- Medido OFFLINE sobre la piloto, que en la base local es el proyecto **74**
  (`transportador-rodillos-cadena-2m`, 201 piezas): blob copiado con `sqlite3 ?mode=ro`, API por
  `TestClient` sin lifespan (sin tocar `data/apolo.db` ni la API del :8000).
- Borrar el travesaño inferior de alimentación (`c90` + sus 2 fijadores `c736`/`c737`, el mismo
  patrón de 3 comandos de la piloto): **8 196 598 bytes** (8.2 MB) de respuesta, la escena
  completa con mallas. Borrar sólo `c90` → 400 «El fijador 'trav_inf_pata_my' referencia el
  sólido 'c90'…» (116 B): hay que buscar los fijadores a mano.

### F1 (2026-10-19)

- `POST /api/commands/remove?detail=diff` → `{comandos_borrados, piezas_borradas,
  uniones_borradas, [grupos_borrados], total_solidos, affected_command_ids}`; no arma la
  escena (`_state_or_error(fn, armar=…)`). Mismo caso de F0: **284 B**; sólo `c90` con
  `con_dependientes` → **494 B** (arrastra los 2 fijadores y lo quita del grupo «Patas y
  travesaños»). Sin `detail` → byte-idéntico (test contra el endpoint viejo copiado literal,
  con un `1e-7` que distingue serializadores). `detail` distinto de `diff` → 400.
- D2 en `services/cirugia.py` (`dependientes`): `fasten`/`ground` que nombran una pieza de los
  comandos borrados (también por prefijo `{cmd}_` de `insert_project`) + edición de `members`
  de los grupos, todo en UN cambio. Para eso `Document.remove_commands(ids, ediciones=None)`
  reemplaza params de otros comandos en el mismo `_mutate` (1 undo). Desvío de alcance:
  toca `doc/` además de `api` (sin eso el grupo quedaba en 2 undos o con `missing_members`).
  Para no crecer `document.py` (trinquete), `can_undo`/`can_redo` pasan a
  `property(lambda …)` como `undo_labels`; el trinquete baja a 1045.
- Decisiones propias: juntas y mates NO se arrastran (definen el mecanismo; el 400 estricto
  los nombra); un grupo que quedaría vacío NO se toca (`register_group` exige un miembro y un
  `transform_group` puede nombrarlo) y sale en `avisos`; sin `detail` pero con
  `con_dependientes`, la escena completa suma `dependientes`/`grupos_editados`/`avisos`. El
  endpoint acepta `?async=true` (`_sync_or_job`, `response_model=dict` para no cambiar de
  serializador).

### F2 (2026-10-19)

- Tool `remove_commands(ids, con_dependientes=False, detail="diff")` en `tools/cirugia.py`
  (fuera de `mcp_server.py` por el trinquete), registrada con `registrar(mcp, mutacion)`: va por
  `_mutacion` (job + recibo), con `detail="full"` pide la escena y la resume con `_scene_brief`.
  `_job_result` deja pasar tal cual un resultado sin `features` (el liviano), así `get_job` de un
  borrado devuelve lo mismo que la vía directa. `get_job` nombra `remove_commands` en su
  docstring. `mcp_server.py` queda en 1421 líneas (`run_batch` arma `body` en una línea).
- D3: `"remove_commands": _muta("Eliminando piezas")` en `CHAT`, tras `edit_batch`; 4 casos
  nuevos + `get_job` de un borrado en `scripts/golden_mcp_casos.py`. Golden re-congelado: el
  diff fue sólo la tool nueva, sus casos y el docstring de `get_job`.
- Test de punta a punta (tool → `TestClient` real) con dependientes: < 5 KB, la vara de F3.
  F3 (por MCP contra el proyecto 2 en vivo) queda para la sesión principal.
