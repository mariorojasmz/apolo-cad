---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: implementación delegada por Mario sin aprobación previa; F7 (modelo por defecto, D11), F8 (D14) y F10 (D15) esperan SU decisión y no se implementan en la delegación. F3 y F5a esperan a partir-api-main F6c, estado-regen F4 y texto-agente F5
descripcion: El asistente de la app usa las mismas herramientas que el agente por MCP (puerta de entrega, gravedad, verify, render nítido, lotes con contrato), te avisa cuando se corta y cuesta menos por mensaje
---

# El asistente de la app trabaja con las mismas herramientas que el agente por MCP, y te avisa si se corta

## Estado y origen

Pedido de Mario (2026-10-03), sobre la lista de pendientes de la auditoría de arquitectura:
«me voy a ir por muchas horas, ejecuta todo los planes pendientes al final revisamos». Por eso el
contrato se implementa **sin aprobación previa**, con una excepción deliberada: las fases que dependen
de una decisión de producto o de costo de Mario (**F7 en la elección del modelo, F8 y F10**) no se
implementan hasta que él decida. Nada se mergea a `main` hasta su revisión (rama de integración
`worktree-auditoria-refactors`).

Lo disparó la auditoría del 2026-10-03: el principio de la raíz «UI, agente-chat y MCP son clientes
iguales de la misma API HTTP» no se cumple para el chat. El chat corre dentro del servidor, toca el
`Document` directo y reimplementa a mano 9–10 tools que la API y el MCP ya tienen; esas copias
divergieron, la guía que recibe contradice el brief de ingeniería, el historial pierde lo que hicieron
las tools y el cliente de Anthropic manda ~130 KB sin caché en cada vuelta. Corre junto con
[partir-api-main](partir-api-main.md), [estado-regen-y-params-estrictos](estado-regen-y-params-estrictos.md)
y [texto-agente-vs-persona](texto-agente-vs-persona.md), que lo condicionan (§ Fases).

## El problema / lo que hay hoy

Medido sobre la rama de integración (base `c933db8`).

1. **El chat corre dentro del servidor y muta el documento directo**: `agent/agent.py:15-16` importa
   `REGISTRY`, `validate_params` y `Document`; `execute_actions_now` llama a `execute_batch(doc, …)`
   (`:32-35`); `undo_last` hace `doc.undo()` (`:536`); el autosave y el WS los dispara el agente vía
   `hooks` (`api/main.py:4897-4902`, `agent/hooks.py`), no el endpoint.
2. **Reimplementa tools que divergieron**:

| Tool | Chat | API / MCP | Consecuencia |
|---|---|---|---|
| `check_interference` | `agent.py:346-366` | `main.py:1945` (`ids`/`focus`), `:1952-1956` (pose) | sin zona acotada ni interpenetración en pose |
| `engineering_check` | `agent.py:190-211`, `:368-396` (carga, largo, velocidad obligatorios) | `main.py:1960-2016` (requisitos guardados, estructura, FEA, lints) | valida sólo la faja |
| `render_view` | `agent.py:398-419`: matplotlib DENTRO de `STATE_LOCK` | VTK, isolate, section, xray, measure | rompe la regla de dos locks |
| `execute_commands` | `agent.py:501-532` | `expect`, `aviso_estructura`, jobs, `insert_project` | sin contrato ni alarma; `insert_project` por id no funciona |
| `get_document` | `agent.py:249-278`: log entero + bbox | `get_scene` paginado y `summary` | vuelca la escena |
| `get_catalog` | catálogo entero | `category`/`names_only` | |
| `save_note` | recorta, tope 500 | `POST /api/agent/notes` no recorta | |
| `test_sketch` | resuelve `=expr` | `/api/sketch/solve` no | el MCP no prueba croquis paramétricos |

3. **Lista paralela escrita a mano**: `build_tools` arma 9/10 tools; el MCP tiene 79. El brief nombra
   tools que el chat NO tiene (`gravity_test`, `check_assembly`, `delivery_check`, `verify`,
   `preview(data=true)`, `run_batch`/`edit_batch` con `expect`, `get_scene(summary)`…). Los 53 schemas
   van embebidos en la descripción de `propose_commands`/`execute_commands` (~130 KB por request).
4. **La guía se contradice**: `prompts.py:40-42` «usa attach» vs brief «snap_to»; `:95` «usa
   get_document» vs «NO vuelques la escena»; `:88-90` cierre con check_interference vs
   «delivery_check, no entregues en ROJO»; sin `expect`; `mcp_server.py:45` «set_visibility para
   aislar» vs `:534-538` y la raíz «isolate».
5. **El MCP también duplica**: guía repetida en docstrings (`run_batch`, `edit_batch`, `get_job`,
   `verify`); dos briefs de pieza (`_scene_brief` del cliente emite `"componente": null`;
   `_feature_brief` del servidor lo omite).
6. **El historial pierde las tools**: `ChatMessage.content: str`; la UI manda sólo texto.
7. **Cliente de Anthropic**: sin `cache_control`; `max_tokens=16000` con pensamiento adaptativo;
   final silencioso ante `max_tokens`/`refusal`/`pause_turn`/vueltas agotadas; modelo por defecto
   `claude-opus-4-8` leído al importar; el modo autónomo se inserta en `messages[0]`.
8. **La UI** muestra el nombre crudo de la tool en los chips (`ChatPanel.tsx:50`); `store.ts`
   congelado en 972 líneas.

## Lo que se revisó antes de escribir esto

- **FastMCP 1.27.2**: `call_tool` es público, valida con el mismo `arg_model` y corre la función sync
  EN el hilo que lo llama; errores como `ToolError`; `list_tools()` da name, description,
  inputSchema, outputSchema → D1.
- **`FastMCP.__init__` configura el logger RAÍZ** (`logging.basicConfig`): importarlo en la API
  cambiaría el logging → D4.
- **Starlette 1.2.1** itera el `StreamingResponse` sync con un `next()` por hilo (anyio, 40 fichas);
  un ContextVar fijado dentro del generador se pierde entre `next()` → D2, D3, D4.
- **Tests que parchean el MCP por nombre** (`_api`, `APOLO_URL`, `APOLO_MCP_WAIT_S`) → D17.
- **Cada cambio de proyecto crea un `Document` NUEVO** → token por objeto (D3).
- **Guardia de jobs** (`_sync_or_job`): patrón a extender → D3.
- **Planes vecinos**: partir-api-main mueve `_state_or_error`/`_sync_or_job` y los endpoints;
  texto-agente D1 congela la huella de `build_tools`; estado-regen F4 endurece `validate_actions` →
  orden de fases y D7.
- **Anthropic** (según la referencia de la skill claude-api citada por el planificador; F0 lo verifica
  contra el SDK instalado): `claude-opus-5-5` es el Opus vigente; effort por defecto `medium`;
  `display: "updates"` (beta) para no quedar mudo entre tools; pensamiento preservado; `refusal` con
  `stop_details`; `fallbacks: "default"` (beta). El venv tiene `anthropic` 0.109.1 (pin `>=0.40`).

## Decisiones (para vetar)

- **D1 (vetable). La tabla única es el registro del MCP**: las 79 `@mcp.tool` son LA fuente; las
  definiciones del chat se GENERAN de `mcp.list_tools()` y el chat ejecuta con `mcp.call_tool()`. Sin
  `ToolDef` paralela. *Porqué*: el MCP queda byte-idéntico por construcción y el chat recibe los mismos
  errores y conversiones que Claude Code. La `ToolDef` declarativa va con el plan que parta
  `mcp_server.py`.
- **D2. El chat ejecuta por HTTP contra la API local, en su hilo**: un `Destino` (URL loopback del
  socket que atendió la request o `APOLO_URL_INTERNA`; `httpx.Client(timeout=120, trust_env=False)`;
  cabecera de guardia) fijado en un `threading.local` mientras corre cada tool
  (`tools/destino.py`). El MCP stdio sigue con `APOLO_URL`.
- **D3. La guardia del documento vive en el servidor y es atómica**: token por objeto `Document`;
  cabecera opcional `X-Apolo-Documento` verificada DENTRO del `STATE_LOCK` de `_state_or_error` y de
  `_sync_or_job`; token distinto → 409 sin aplicar nada; sin cabecera, byte-idéntico. `GET
  /api/health` suma `documento`. `AgentHooks` desaparece.
- **D4. El deadlock queda imposible por diseño**: (a) nada de `apolo.agent` importa `apolo.state`
  (gate AST); (b) semáforo `APOLO_CHAT_MAX` (4) → 429 si está lleno; (c) nunca `anyio.from_thread`
  (un `asyncio.run` privado en el hilo del chat); (d) `apolo.mcp_server` se importa perezoso,
  restaurando el logger raíz.
- **D5. Subconjunto curado en `tools/catalogo.py` con gate de completitud**: cada tool MCP está en
  `CHAT` (`muta`, `ocultar`, `etiqueta`) o en `FUERA_DEL_CHAT` (con motivo): fuera las que cambian de
  proyecto/revisión, las que sólo producen archivos (escritura arbitraria en el servidor) y
  `fea_assembly` (minutos). Se ocultan `path`/`fringe_path` opcionales.
- **D6. Mismas tools en los dos modos; el modo lo hace cumplir el código**: en propuesta, una tool que
  muta devuelve `is_error`; el modo viaja en el turno actual del usuario (append-only), no en
  `messages[0]`.
- **D7. `propose_commands` es la única tool exclusiva del chat**, validada con `preview(actions,
  data=true)` por HTTP; `validate_actions` se borra.
- **D8. El chat deja de embeber los 53 schemas** y los pide con `get_command_schemas(command_type)`.
- **D9. Una sola guía: `design/instrucciones.py`** (`GUIA_TECNICA`, `AVISO_CONEXION`,
  `instrucciones_mcp()` byte-idéntica, `system_prompt_chat()` = `design_brief()` + `GUIA_TECNICA` +
  `REGLAS_CHAT`). El prompt viejo se tría frase por frase. Gate: el prompt no nombra tools que el chat
  no tiene ni tools viejas.
- **D10 (vetable). Lo huérfano del prompt viejo entra a `GUIA_TECNICA`** (también al MCP, aditivo y
  listado) y se corrige `mcp_server.py:45` (aislar = `isolate`). Si se veta: va sólo a `REGLAS_CHAT`.
- **D11 (vetable, DECISIÓN DE MARIO). Modelo por defecto y effort**: el planificador propone
  `claude-opus-5-5` leído en cada llamada, `output_config.effort` explícito (`medium`) y `max_tokens`
  64 000. **No se implementa en la delegación**: en F7 sólo se hace configurable sin cambiar el default.
- **D12. Caché de prompt**: `tools` en orden fijo; `cache_control` en el último bloque de `system`;
  nada volátil antes del último breakpoint; `done` lleva `uso`.
- **D13. Ningún final silencioso**: `max_tokens`, `refusal` y vueltas agotadas → evento SSE `aviso`
  en tuteo; `pause_turn` → se reanuda; nunca se ejecuta una tool de una respuesta que no terminó en
  `tool_use`.
- **D14 (vetable, DECISIÓN DE MARIO). Respaldo por rechazo** con `fallbacks: "default"` (beta). **No se
  implementa en la delegación (F8).**
- **D15 (vetable, DECISIÓN DE MARIO). El historial conserva las tools entre turnos, guardado en la
  UI** (evento `turno`, `ChatMessage.content: str | list[dict]`). **No se implementa en la delegación
  (F10).**
- **D16 (vetable). Una sola forma del brief de pieza** (`apolo/brief.py` puro); el único cambio de
  SALIDA del MCP del plan (`componente: null` → omitido), registrado en el golden.
- **D17. Lo que un test parchea no se mueve**: `_api`, `_submit_and_wait`, `APOLO_URL`,
  `APOLO_MCP_WAIT_S` se quedan en `mcp_server.py`.
- **D18 (vetable). Los endpoints igualan lo que el chat hacía mejor**: `/api/sketch/solve` resuelve
  `=expr`; `POST /api/agent/notes` recorta y aplica el tope de 500 (cambia el MCP para notas largas).

## Alternativas descartadas

- `ToolDef` declarativa ya, generando los 79 wrappers de FastMCP: 79 reescrituras para cero cambio
  visible; va con la partición de `mcp_server.py`.
- Llamar las funciones del MCP directo: se saltea la validación de FastMCP.
- `anyio.from_thread.run(mcp.call_tool, …)`: deadlock.
- Chat async: las tools del MCP son sync.
- Transporte en proceso sin HTTP: no sería un cliente igual.
- ContextVar para el destino: se pierde entre `next()`.
- Guardia en el cliente: TOCTOU que mutaría el proyecto nuevo.
- Sostener `STATE_LOCK` en el chat durante la llamada: deadlock.
- Historial guardado en el servidor: estado en el proceso.
- Recortar el historial: invalida pensamiento preservado y caché.
- Dos sets de tools por modo: rompe el prefijo de caché.
- Darle al chat las 79 tools: escritura arbitraria de archivos.
- Tool search con `defer_loading`: más beta; se revisa si F0 mide un costo alto.
- Subir las 40 fichas de anyio: tapa el síntoma.
- `role: "system"` a mitad de conversación: depende del modelo.

## Fases

Cada fase la implementa un subagente opus en su worktree (`git merge worktree-auditoria-refactors
--ff-only`; `$env:PYTHONPATH = "$PWD\core"`; `python -B`). **Gate común**: pytest completo; golden MCP
de F1 sin diferencias salvo cambio deliberado listado; `ruff check core tests scripts`; trinquetes
(`agent.py`, `mcp_server.py` sólo bajan; `main.py` y `store.ts` no crecen; nuevos ≤ 500); si toca
`ui/`: `npm test` + `npm run build`. El E2E usa una API levantada desde el worktree de integración en
:8001 sobre una COPIA de `data/apolo.db`, nunca la API de Mario.

- **F0 — mide (sólo lectura, S).** Tamaños de `build_tools`, `SYSTEM_PROMPT`, `list_tools()` y el
  subconjunto D5; keywords de JSON Schema de FastMCP; spikes desde el scratchpad: (1) `TestClient`
  anidado, (2) ContextVar de middleware leído por endpoint `def`, (3) `asyncio.run(mcp.call_tool)`
  desde un hilo de anyio respeta un `threading.local`, (4) importar `apolo.mcp_server` en la API y el
  logger raíz; mutaciones alcanzadas por el subconjunto; triage de `prompts.py`; inventario de guía
  duplicada en docstrings MCP; firma de `messages.stream` en el SDK instalado. Si un spike falla, se
  para.
- **F1 — golden del MCP (M · `tests/`, `scripts/`).** `scripts/golden_mcp.py --congelar|--comparar`,
  `tests/data/mcp_golden/`, `tests/test_mcp_golden.py` PERMANENTE: (a) instructions, (b)
  `list_tools()` canónico, (c) por tool al menos una `call_tool` contra `httpx.MockTransport` con
  peticiones registradas y salida (incluye 400 con `detail`, job en error, 404 de job, conexión
  rechazada). Verde 3 veces; rojo al cambiar un default, un docstring o el orden de params.
- **F2 — MCP: destino inyectable, instructions y brief fuera (S).** `tools/__init__.py`,
  `tools/destino.py`, `brief.py`, `design/instrucciones.py`; `_api` consulta `destino.actual()`;
  `tests/test_mcp_destino.py`. Golden idéntico; los tests que parchean el MCP sin editar.
- **F3 — guardia del documento y endpoints igualados (M · `api`).** `api/guardia_documento.py`;
  llamada en `_state_or_error`, `_sync_or_job` y mutaciones fuera del embudo; `health.documento`; D18.
  **Depende de partir-api-main F6c.**
- **F4 — catálogo y adaptador (M).** `tools/catalogo.py`, `agent/herramientas.py`;
  `tests/test_catalogo_chat.py` (catálogo ∪ fuera = 79; tools con `path` fuera u ocultas;
  definiciones deterministas; cada tool que no muta no cambia el documento; logger raíz intacto).
- **F5a — el motor HTTP en paralelo (M).** `agent/chat.py`, `agent/eventos.py`, flag temporal
  `APOLO_CHAT_HTTP=1`; tests con falso `anthropic` (todo `tool_use` con resultado; modo propuesta
  bloquea mutaciones; proyecto cambiado → 409; ninguna llamada con `STATE_LOCK` tomado; mismos bytes de
  `tools` en los dos modos; append-only); tortura con uvicorn real y `APOLO_CHAT_MAX`. **Depende de
  F3, F4, partir F6c, estado-regen F4 y texto-agente F5.**
- **F5b — corte y limpieza (M).** Se borra el flag y `agent/agent.py`; gate AST de capas de clientes;
  lista cerrada de tests editados (`test_agent.py`, `test_autonomous.py`, `test_validation.py`,
  `test_variables.py`, el caso del agente de `test_params_estrictos.py` si existe).
- **F6 — una sola guía (S).** `REGLAS_CHAT` + `system_prompt_chat()`, triage aplicado, D10.
- **F7 — higiene del cliente de Anthropic (M).** `agent/modelo.py` con D12 y D13; modelo leído en
  cada llamada vía `APOLO_MODEL` **sin cambiar el default** (D11 espera a Mario); pin de `anthropic` a la
  mínima versión verificada en F0. Tests con el falso capturando kwargs.
- **F8 — respaldo por rechazo (S).** **Espera la decisión de Mario (D14).**
- **F9 — UI: avisos, progreso y etiquetas (S · `ui`).** `ui/src/chat/sse.ts` puro + test; `store.ts`
  baja; `ChatPanel.tsx` con `aviso`, `progreso` y chips con `etiqueta`; gates de texto.
- **F10 — historial con tools (M).** **Espera la decisión de Mario (D15).**
- **F11 — una sola forma del brief (S, vetable por D16).** Golden (c) actualizado con el diff.
- **F12 — verifica (S).** pytest completo y `-m torture`; API en :8001 sobre una copia de la base con
  un script MCP por stdio; `APOLO_CHAT_MAX=1` → 429. **Para Mario**, con credencial y en la UI: modo
  propuesta y autónomo en el 38, cambio de proyecto a mitad, `done.uso.cache_read > 0`, errors.log
  limpio.

## Lo que este plan NO hace

- No cambia nombres, params, docstrings ni salidas de las tools MCP (salvo D16) ni sus instructions
  (salvo D10).
- No parte `mcp_server.py` ni introduce la `ToolDef` declarativa.
- No poda la guía duplicada en los docstrings MCP (F0 deja el inventario).
- No agrega tools MCP.
- No valida nombres de junta en `/api/checks` ni en `render.png` (posible hueco: va al backlog).
- No implementa compactación ni context editing; no sube el SDK a 1.x ni usa Tool Runner.
- No cambia cómo se aceptan las tarjetas, los locks, el autosave ni los jobs.
- No autentica el loopback (API local).

## Riesgos

- **Deadlock o threadpool agotado** → D4 y la tortura con uvicorn real.
- **El semáforo no se libera si el cliente corta el stream** → `finally` del generador + test de corte.
- **Los spikes de F0 fallan** → la fase se detiene y se vuelve al contrato.
- **Un upgrade de `mcp` cambia `call_tool` o `ToolError`** → golden de F1 y test de destino.
- **Anthropic rechaza un JSON Schema de FastMCP** → F0 inspecciona; normalizador en
  `agent/herramientas.py`.
- **Costo de ~63 tools** → F0 mide; caché D12; si no cierra, se achica el catálogo.
- **Inyección de prompt desde resultados de tools** → en modo propuesta el código bloquea mutaciones;
  sin tools de archivo ni de proyecto.
- **`render_view` sin OpenGL devuelve 503** → igual que el MCP.
- **El import del MCP ensucia el logging de la API** → D4(d) y su test.
- **Choques en la rama de integración** → orden: F0–F2 y F4 en cualquier momento; F3 tras partir
  F6c; F5a tras F3, F4, estado-regen F4 y texto-agente F5.

## Bitácora

_(vacía: se llena al cerrar cada fase)_
