---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: F0–F2, F4, F6 y F7 hechas (spikes verdes, golden del MCP, destino inyectable, catálogo de 63 tools + adaptador, guía única que el chat viejo ya usa, cliente de Anthropic con caché y avisos; adaptador y cliente todavía sin cablear al chat), sin mergear. D11 (defaults de modelo, effort y max_tokens: F7 los dejó configurables sin cambiarlos), F8 (D14) y F10 (D15) esperan la decisión de Mario. F3 y F5a esperan a partir-api-main F6c, estado-regen F4 y texto-agente F5
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
  `test_variables.py`, el caso del agente de `test_params_estrictos.py` si existe, y el test
  transitorio `test_las_reglas_sirven_tambien_al_chat_viejo` de `test_prompt_chat.py`, que F6 dejó).
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

### F0 — medición (2026-10-03, sólo lectura; scripts en el scratchpad de la sesión, fuera del repo)

Base `3b9184f`; `mcp` 1.27.2, `anthropic` 0.109.1, `starlette` 1.2.1, `anyio` 4.13.0, `httpx`
0.28.1. Tokens ≈ bytes UTF-8 / 3.5 (estimación: no se llamó a la API para contarlos).

**Tamaños.**

| qué | tools | bytes | ≈ tokens |
|---|---|---|---|
| `build_tools(auto=False)` | 9 | 152 876 (`propose_commands` sola: 149 294) | 43 700 |
| `build_tools(auto=True)` | 10 | 153 154 | 43 800 |
| `SYSTEM_PROMPT` | — | 10 730 (de ellos `design_brief()` 3 761) | 3 070 |
| instructions del MCP | — | 4 900 | 1 400 |
| `list_tools()` como definiciones Anthropic (name+description+input_schema) | 79 | 65 870 | 18 800 |
| `list_tools()` completo (con `outputSchema`) | 79 | 77 821 | — |
| subconjunto D5 tentativo (fuera: 3 de proyecto, 3 de revisión, 9 de archivo, `fea_assembly`; `path`/`fringe_path` opcionales ocultos) | 63 | 52 776 | 15 100 |

Hoy cada vuelta del chat manda ≈ 164 KB (≈ 47 k tokens) sin caché; con el subconjunto + brief el
prefijo baja a ≈ 57 KB + la guía, cacheable (D12). El «~130 KB» del contrato era corto: son 153 KB.

**JSON Schema que emite FastMCP** (79 `inputSchema`): sólo `type`, `properties`, `required`,
`title`, `default`, `anyOf` (69, siempre `X | null`), `items` y `additionalProperties` (`true` en
`dict`, `{type: number}` en `dict[str, float]`); tipos string/number/integer/boolean/object/array/
null. Sin `$ref`/`$defs`/`oneOf`/`allOf`/`enum`/`format`. Raíz siempre `{type: object, title,
properties[, required]}`. Nada que Anthropic rechace: el normalizador de `agent/herramientas.py`
puede limitarse a quitar `title` si F4 lo quiere más corto. `outputSchema` en 77 tools (`-> str` →
`{result: string}`, por eso `call_tool` devuelve la TUPLA `(contenido, estructurado)`); `render_view`
y `preview` no lo tienen (devuelven la lista de bloques).

**Spikes** — los cuatro pasan:
1. **TestClient anidado**: un endpoint `def` y un `StreamingResponse` sync que, atendiendo a un
   `TestClient`, hacen otra request al mismo app con un `TestClient` nuevo (endpoint interno con un
   RLock global): OK, sin deadlock, también dentro de `with TestClient(app)`.
2. **ContextVar de middleware**: un middleware ASGI puro (y `@app.middleware("http")`) que fija un
   ContextVar → lo lee el endpoint `def` y CADA `next()` del generador sync (TestClient y uvicorn
   real). Lo que se pierde es lo FIJADO DENTRO del generador: un `set` en un `next()` no llega al
   siguiente aunque corra en el mismo hilo (`dentro_previo=None` siempre). → el destino por llamada
   va en `threading.local`, fijado y usado dentro del MISMO `next()` (D2 confirmada).
3. **`asyncio.run(mcp.call_tool)` desde un hilo de anyio**: la función sync de la tool corre en el
   hilo que llama y ve su `threading.local`; 6 streams concurrentes en uvicorn real, 5 llamadas
   cada uno, cero cruces (6 hilos distintos).
4. **Import de `apolo.mcp_server` en la API**: confirma el daño — raíz `WARNING`/sin handlers →
   `INFO` + `RichHandler` (y `httpx` empieza a loguear cada request). La receta «snapshot de
   handlers+nivel → import → restaurar» lo neutraliza, y un 2.º import (cacheado) no reconfigura.
   Costo del primer import ≈ 2.5 s (arrastra `mcp`, `rich`, `sse_starlette`, `pydantic_settings`;
   ningún `apolo.*` pesado): el import perezoso lo paga la primera request del chat.

**Mutaciones que alcanza el subconjunto D5** (rastreo tool → ruta → endpoint):
- Por `_state_or_error`: `run_command`, `edit_command`, `undo`, `redo`, `set_variable`,
  `set_material`, `set_color`, `set_vertical`, `set_visibility`, `set_visibility_bulk`,
  `save_configuration`, `apply_configuration`, `declare_structure`, `delete_connection`,
  `auto_group` (sin `dry_run`). Por `_sync_or_job` (+ `_state_or_error`): `run_batch`, `edit_batch`.
- **FUERA del embudo** (F3 las guarda una por una): `add_agent_note` (`POST /api/agent/notes`),
  `set_motion` (`PUT /api/motion`), `set_stackup` (`PUT /api/stackup`), `set_requirements`
  (`PUT /api/requirements`) — las cuatro `STATE_LOCK` + `_autosave()` a mano — y `fea_static`
  (`POST /api/fea/static`, persiste por `_persist_fea_if_same_project`, que ya trae su propia
  guardia por `(PROJECT_ID, DOC)`).
- El resto del subconjunto (lecturas, `render_view`, `preview`, `delivery_check`, `scan_motion`,
  `drawing` sin `path`, `gravity_test` sin `path`) no muta.

**Triage de `agent/prompts.py`** (destino de cada frase; F6 lo aplica):

| líneas | frase (resumida) | destino |
|---|---|---|
| 3-4 | «Eres el asistente de diseño de Genix Apolo CAD…» | `REGLAS_CHAT` |
| 7 | mm, Z arriba, grados | `GUIA_TECNICA` (mm/Z ya están; suma «grados») |
| 8-10 | primitivas CENTRADAS; `rotation` intrínseca XYZ sobre el centro, antes de la traslación | `GUIA_TECNICA` (huérfana) |
| 11-13 | perfiles extruidos en Z; `rotation.y=90` → X, `rotation.x=90` → Y | `GUIA_TECNICA` (huérfana) |
| 14-15 | los comandos crean features con id; el usuario las ve en el árbol | borrar (duplica «log de comandos editable») |
| 18-21 | variables, `"=expresión"`, ejemplos y lista de funciones | `GUIA_TECNICA` sólo los ejemplos; la lista se borra (vieja: sin condicionales) → `get_expression_grammar` |
| 22-27 | DISEÑA PARAMÉTRICO: `set_variable` primero en el MISMO lote, usables en él | `GUIA_TECNICA` (la regla 9 del brief no dice lo del lote) |
| 30-34 | catálogo, `insert_component` (ref + longitud si es cortable), prefiere catálogo | borrar lo de preferir (regla 8); `GUIA_TECNICA` la forma de `insert_component` |
| 35-37 | transportador de rodillos = SIEMPRE `create_conveyor` | `GUIA_TECNICA`, ampliada a `create_belt_conveyor` (super-comandos) |
| 37-39 | rodillo por capacidad (Ø50→35 kg…), paso ≤ largo/3 | borrar (lo calcula `engineering_check`; números duplicados que pueden divergir) |
| 40-42 | «usa `attach`» | borrar: CONTRADICE el brief (`snap_to`), que ya lo dice |
| 45-49 | sintaxis de los selectores con ejemplo | `GUIA_TECNICA` (las instructions sólo nombran los modos) |
| 50-52 | fillet/chamfer/shell/drill_hole EN SITIO (conservan id); detalle de `drill_hole` | `GUIA_TECNICA` lo de EN SITIO; el detalle se borra (está en el schema) |
| 53-56 | `create_revolve`/`create_extrude_poly` antes que `run_script`; r ≥ 0, antihorario | `GUIA_TECNICA` (huérfana) |
| 57 | `pattern_circular`, `mirror_feature` | borrar (schemas) |
| 58-59 | STEP → botón «Importar STEP» | `REGLAS_CHAT` (es de la UI) |
| 62-66 | croquis: puntos aproximados + restricciones, lazo cerrado, círculos = agujeros, cotas `=expr` | `GUIA_TECNICA` |
| 67-68 | valida con `test_sketch` antes | borrar (duplica las instructions) |
| 69-70 | ancla un punto con `fix`, orienta con horizontal/vertical | `GUIA_TECNICA` |
| 73-74 | `create_robot_arm`, panel Cinemática, URDF/SDF | `REGLAS_CHAT` sólo «panel Cinemática»; el resto, schema |
| 75-77 | `add_joint`: un sólido es hijo de UNA junta; origen en mundo | `GUIA_TECNICA` (huérfana) |
| 79 | «Validación: tu sello de calidad» | borrar (regla 10) |
| 80-84 | `engineering_check` antes de proponer una faja; resume al usuario | borrar lo primero (instructions); `REGLAS_CHAT` «resume el resultado de la validación» |
| 85-87 | geometría nueva: `test_script` hasta que funcione | borrar (instructions) |
| 88-90 | tras aceptar: `check_interference`/`render_view` | borrar: CONTRADICE el cierre con `delivery_check` del brief |
| 91-92 | las tools de validación no modifican, llámalas cuanto quieras | `REGLAS_CHAT`, reescrita para D6 (en propuesta lo que muta da error) |
| 95 | «usa `get_document`» | borrar: CONTRADICE «NO vuelques la escena» y la tool desaparece |
| 96-99 | `propose_commands` con TODO el lote; tarjetas; nada corre hasta aceptar | `REGLAS_CHAT` (D7) |
| 100-102 | `"$k"` 1-based con ejemplo | `GUIA_TECNICA` sólo «1-indexado» (el `$k` ya está) |
| 103-104 | medidas razonables y decirlo | `REGLAS_CHAT` («dilo» no está en el brief) |
| 105-106 | idioma del usuario, breve: qué, dimensiones, por qué | `REGLAS_CHAT` |
| 108-111 | ejemplo del marco 40×40 | `GUIA_TECNICA` (ejemplo de orientación de perfiles; F6 decide si paga sus bytes) |
| 116-119 | «Criterio de ingeniería…» + `design_brief()` | se conserva por construcción (`system_prompt_chat()`) |

Además `mcp_server.py:45` («combínalo con set_visibility para aislar») y el docstring de
`set_visibility` («útil para aislar antes de render_view») contradicen a `render_view` («prefiérelo
a set_visibility») y a la raíz → D10.

**Guía duplicada en docstrings del MCP** (inventario; este plan NO la poda):
- `run_batch` y `edit_batch`: el contrato `expect` + «ahórrate mutar→leer→undo» (= `ACCION_DOCTRINE`)
  y el párrafo del JOB/recibo, repetido en las dos y en `get_job`.
- `get_job`: «NUNCA reintentes el lote a ciegas» (= el `detail` del 404 de la API y «NO reenvíes»
  de `run_batch`/`edit_batch`).
- `get_scene` («a ESCALA… NO vuelques la escena… summary entra por aquí») y `check_interference`
  («tu zona, no la máquina entera») = `ESCALA_DOCTRINE`.
- `verify` («sin ojímetro») = `ESCALA_DOCTRINE`; su párrafo EN POSE repite el de `run_batch`/`edit_batch`.
- `delivery_check` («NO ENTREGUES EN ROJO») = regla 10 + la línea extra del brief.
- `get_design_guidelines` («el usuario es el CLIENTE y tú el INGENIERO») = `DESIGN_PRINCIPLE`.
- Las instructions repiten docstrings: `engineering_check(conveyor=…)`, `test_sketch`/`test_script`,
  `get_topology` → selector, `get_command`.
- `render_view` ↔ `set_visibility` ↔ instructions `:45`: contradicción (arriba).

**SDK `anthropic` 0.109.1**: `messages.stream` acepta `cache_control` (raíz, `ephemeral` con `ttl`
5m/1h), `output_config` (`effort` low…max) y `thinking`; NO `betas` ni `fallbacks`.
`beta.messages.stream` suma `betas`, `fallbacks` (tipado sólo como lista de
`{model, max_tokens, output_config, speed, thinking}`), `context_management`, `mcp_servers`.
`stop_reason` incluye `pause_turn` y `refusal`; `Message.stop_details` existe. Los tipos se quedan
atrás de la API: `thinking.display` sólo tipa `summarized|omitted` y el literal de modelos no trae
`claude-opus-5-5` (acepta `str`). Pero con un transporte falso (`httpx.MockTransport`, sin llamar a
la API) el SDK manda TAL CUAL `display: "updates"`, `fallbacks: "default"`, `betas` en la cabecera
`anthropic-beta`, `cache_control` en la raíz y en el bloque de `system`, y `output_config`. → 0.109.1
sirve en tiempo de ejecución para F7/F8; F7 fija el pin en `>=0.109.1` (la mínima verificada aquí).

### F1 — golden del MCP (2026-10-03)

- `scripts/golden_mcp.py` (motor + CLI `--congelar|--comparar`), `scripts/golden_mcp_casos.py`
  (respuestas canónicas por ruta + casos), `tests/data/mcp_golden/` (`instructions.txt` 4.9 KB,
  `list_tools.json` 93 KB, `llamadas.json` 100 KB) y `tests/test_mcp_golden.py` (permanente: cada
  tool tiene caso, golden idéntico, siguen los cuatro caminos de error del contrato).
- **Cobertura: 79/79 tools, 118 `call_tool`** reales (validación de FastMCP incluida) con las
  ramas de params de cada una (`get_scene` ×4, `render_view` con los 17 params, `near` ×4, …).
  Errores: 400 con `detail`, 500 sin JSON, job en error (en `run_batch` y en `get_job`), 404 de
  job, conexión rechazada, el `ValueError` de `_one_or_many`, `near` sin argumentos y
  `get_command` inexistente; recibo con espera 0 en `run_batch`/`edit_batch` y job
  corriendo → ok en el long-poll.
- **Inyección**: se reemplaza `httpx.Client` (atributo del módulo) por una fábrica que agrega el
  `MockTransport` y registra los kwargs del cliente (`base_url`, `timeout`). No depende de cómo
  `_api` arma la petición: el mismo golden mide antes y después de F2.
- **Determinismo**: `APOLO_URL` y `APOLO_MCP_WAIT_S` fijados por caso; las tools que escriben
  archivos corren en una carpeta temporal con nombres pelados (sin rutas: igual en Windows y
  Linux) y del archivo queda su sha256. Verde 3 veces seguidas, y otra con `APOLO_URL` y
  `APOLO_MCP_WAIT_S` hostiles en el entorno, otro cwd y sin `PYTHONPATH` (el script antepone el
  `core/` de su propio árbol).
- **Rojo comprobado** (y revertido): default `get_bom(by_group=True)` → schema y query; docstring
  de `undo` → `description`; `measure(b, a, …)` → orden de `properties`. Se compara el TEXTO
  canónico: `dict ==` ignora el orden y no habría cazado el tercero.
- **Desviación**: las cabeceras omiten, además de `user-agent`, `accept-encoding` y
  `content-length`: dependen de la instalación y la versión de httpx (brotli/zstd, separadores
  del JSON), no de Apolo; el cuerpo se registra entero. El golden sí fija la salida de `mcp` y
  `pydantic`: un upgrade que cambie el schema lo pone rojo a propósito (el test imprime las
  versiones y cómo re-congelar).
- Suite: 1393 passed + 1 skipped (1394 recolectados; el commit de F1 dice «1394 passed»: contó
  el skip).

### F2 — destino inyectable, brief e instructions fuera del MCP (2026-10-03)

- `tools/__init__.py` (6 líneas) y `tools/destino.py` (66): `Destino(base_url, abrir)`,
  `Destino.http(base_url, cabeceras)` (la config de D2: `timeout=120`, `trust_env=False`,
  cabeceras fijas), `apuntar()` (context manager: anida y restaura aunque el bloque lance) y
  `actual()` sobre un `threading.local`.
- `brief.py` (84, puro: sólo importa `__future__`): `_scene_brief` y `_one_or_many` movidos al
  pie de la letra (comparado por AST contra `HEAD`) y re-exportados por identidad desde
  `mcp_server` (D17).
- `design/instrucciones.py` (42): `GUIA_TECNICA`, `AVISO_CONEXION` e `instrucciones_mcp()` =
  `design_brief() + "\n\n" + GUIA_TECNICA + " " + AVISO_CONEXION`, byte-idéntica. La
  contradicción set_visibility ↔ isolate queda anotada en el código para F6 (D10).
- `_api` consulta `destino.actual()`: con destino abre `d.abrir()` y nombra `d.base_url` en el
  error de conexión; sin destino, `httpx.Client(base_url=APOLO_URL, timeout=120)` como antes (el
  golden registra esos kwargs: siguen idénticos). `_api`, `_submit_and_wait`, `APOLO_URL` y
  `APOLO_MCP_WAIT_S` se quedan en `mcp_server.py`.
- `mcp_server.py` 1517 → **1429** líneas (trinquete actualizado en el mismo commit).
- `tests/test_mcp_destino.py` (12): `call_tool` va al destino del hilo con su cabecera;
  `run_batch` encola y hace el long-poll en el MISMO destino; dos hilos a la vez sin cruces;
  anidar y restaurar; un 400 por destino da el mismo texto que por stdio; la conexión
  rechazada nombra el destino; config de `Destino.http`; re-export por identidad; instructions
  compuestas; `brief.py` puro y `tools/` sin imports de `apolo` (AST).
- Golden de F1 **idéntico** tras F2, y `test_jobs`, `test_mcp_defaults`, `test_autonomous` y
  `test_mcp_brief` (los que parchean `_api`/`APOLO_URL`/`APOLO_MCP_WAIT_S`) pasan sin editarse.
- Suite: 1405 passed + 1 skipped; `ruff check core tests scripts` limpio.

### F4 — catálogo y adaptador (2026-10-03)

- `tools/catalogo.py` (138 líneas, puro): `EnChat(etiqueta, muta, ocultar)`; **63 tools en
  `CHAT`** (22 mutan, 41 leen) en orden fijo por bloques (leer el modelo · modelar · ensayar y
  validar · ingeniería y fabricación) y **16 en `FUERA_DEL_CHAT`** con motivo: 3 de proyecto,
  3 de revisión, 9 que sólo escriben un archivo en el servidor (exports, PDFs, `drop_test` y
  `motion_gif`, que exigen ruta) y `fea_assembly` (minutos). Ocultos: `gravity_test.path`,
  `drawing.path`, `fea_static.fringe_path`. Es exactamente el subconjunto tentativo de F0.
  `fea_static` cuenta como mutación (guarda su resumen en el proyecto); `auto_group` también,
  aunque su `dry_run` no mute (conservador: en propuesta se propone `create_group`); `get_job`
  no muta.
- `agent/herramientas.py` (217): `definiciones()` = `mcp.list_tools()` en el orden del catálogo,
  la descripción TAL CUAL (FastMCP ya la limpia: `cleandoc` midió 0 bytes de diferencia), el
  schema sin `title` (sólo en posiciones de schema: un PARÁMETRO llamado `title` sobrevive) y
  sin los ocultos, copiado sin tocar el dict que FastMCP sirve a los clientes MCP; más
  `propose_commands` al final (sólo la declaración, con `reason` obligatorio porque la tarjeta
  lo muestra; su ejecución es F5a). `ejecutar(nombre, entrada, destino, modo)` devuelve el
  cuerpo del `tool_result` (`{"content": [...]}` + `"is_error": True`): `ToolError` → el MISMO
  texto que ve un cliente MCP; texto → bloque `text`, imagen → `image` base64; una tool fuera,
  desconocida, que muta en modo propuesta o con un param oculto → `is_error` SIN llamar a la API
  (FastMCP IGNORA en silencio las claves extra: sin el veto, un `path` colado escribiría en el
  servidor). `propose_commands` o un modo inválido → `ValueError` (error de programación, no del
  modelo). `etiqueta(nombre)` para el chip. Import perezoso del MCP bajo lock, restaurando nivel
  y handlers del logger raíz.
- **Definiciones: 64 tools, 48 887 bytes** (≈ 14 k tokens; `propose_commands` 1 018) contra
  152 876 del chat de hoy (−68 %). Quitar `title` ahorra ≈ 5 KB sobre el subconjunto crudo.
- `tests/test_catalogo_chat.py` (64): catálogo ∪ fuera = las tools del MCP sin solape; todo
  `path`/`*_path` fuera u oculto; lo oculto existe y es opcional; motivo en cada fuera; gate de
  capas (AST); etiquetas por el `faltas()` de `test_pistas.py` (mismo gate de texto, tuteo y
  vocabulario) y sin repetirse; definiciones en orden, sin ocultos ni `title`, sin mutar el
  schema del MCP y con el MISMO sha256 en otro proceso (otro `PYTHONHASHSEED`), proceso donde
  además se comprueba que importar `herramientas` no importa el MCP y que `definiciones()` deja
  intactos el logger raíz y el nivel efectivo de `httpx`; `ejecutar` contra un transporte falso
  (destino y cabecera, imagen, mismo error que el MCP en 400 / validación / error del cliente
  fino, modo, oculto, fuera y desconocido sin tocar la API); y **las 41 lecturas, cada una con
  su muestra, contra la API real** (`TestClient` prestado sin entrar, para no correr el
  lifespan): ni el documento (contenido del `.apolo`, piezas, undo/redo) ni el autoguardado
  cambian (espía en `api._autosave_sched.schedule`, el patrón de partir-api-main). Comprobado
  que pone rojo una mutación mal clasificada (`set_color` como lectura) y que sin la
  restauración el import deja el raíz en INFO + RichHandler. Con OpenGL aquí `render_view` y
  `pick_point` corren; sin él (503) se saltan después de verificar que no mutaron.
- **Para F6**: los docstrings de `drawing`, `gravity_test` y `fea_static` nombran el param
  oculto (y `drawing` sin `path` responde «pasa path=... para guardar»): el modelo puede
  intentarlo y recibe `is_error` con «repite la llamada sin ese parámetro». No se tocan aquí
  (golden del MCP).
- `mcp_server.py` (1429) y `agent/agent.py` (606) sin tocar; golden del MCP idéntico.
- Suite: 1606 passed + 1 skipped (1607 recolectados, 10 min); `ruff check core tests scripts`
  limpio. La muestra de `test_script` cuesta ≈ 9 s (el sandbox levanta su proceso).

### F6 — una sola guía (2026-10-03)

- `design/instrucciones.py` (101 líneas): `REGLAS_CHAT` y `system_prompt_chat()` =
  `design_brief()` + `GUIA_TECNICA` + `REGLAS_CHAT` (separados por `"\n\n"`, sin
  `AVISO_CONEXION`). `agent/prompts.py` queda en `SYSTEM_PROMPT = system_prompt_chat()` (120 → 7
  líneas). `test_design_guidelines.py` pasa sin editarse.
- **Tamaños**: prompt del chat 10 730 → **7 974 bytes** (−26 %); instructions del MCP 4 900 →
  **6 151** (+1 251, D10); `GUIA_TECNICA` 1 013 → 2 264; `REGLAS_CHAT` 1 945.
- **A `REGLAS_CHAT`** (sólo lo de la app): quién es y con quién habla (panel Asistente IA, el
  proyecto abierto); modos (D6: propuesta por defecto, lo que cambia el documento devuelve error,
  para cambiar geometría `propose_commands` y nunca pasos manuales; modo auto: aplica, verifica,
  corrige y resume); cómo empezar (leer el modelo por el resumen por grupo y las notas del
  proyecto); archivos (el chat no escribe: planos en la pestaña Planos, memoria y cotización en
  Requisitos, el BOM en su panel, STEP/STL/glTF en el menú Archivo; si una tool ofrece `path` o
  `fringe_path`, se llama sin ellos — cierra la nota de F4 sobre `drawing`, `gravity_test` y
  `fea_static`); STEP por Archivo → «Importar STEP…»; panel Cinemática; cómo responder (idioma de
  la persona, breve: qué, medidas, por qué; medida razonable y decirlo; resumir lo validado;
  tuteo neutro y las palabras de la tabla de `ui/CLAUDE.md`).
- **A `GUIA_TECNICA`, que llega también al MCP (D10)** — cada frase añadida:
  1. «ángulos en grados» (L7).
  2. «'$k' … (1-indexado: '$1' es la primera acción)» (L100-102); en esa frase «sólidos» pasa a
     «piezas».
  3. El ejemplo de selector `{"mode": "direccion", "direction": "z"} = las aristas paralelas a Z`
     (L45-49).
  4. «Colocación: rotation gira la pieza (XYZ intrínseca) alrededor de su centro y después
     position la traslada» (L8-10; comprobado en `kernel/shapes.py::place` y en `Rotation` de
     build123d, `Intrinsic.XYZ` por defecto).
  5. «Los perfiles (create_structural_profile y los de catálogo) se extruyen a lo largo de Z:
     rotation.y=90 los alinea con X y rotation.x=90, con Y» (L11-13).
  6. «Variables: con las dimensiones principales, define primero las variables (set_variable al
     inicio del MISMO lote: las acciones siguientes ya las usan) y deriva el resto con
     '=expresión'» (L22-27).
  7. «un transportador se hace con su super-comando —create_conveyor (rodillos) o
     create_belt_conveyor (banda)—, que genera la máquina entera y queda editable como un todo,
     no pieza por pieza» (L35-37, ampliada a la banda).
  8. «Lo de catálogo (get_catalog) se inserta con insert_component (referencia + length si es
     cortable)» (L30-34).
  9. «Antes que run_script, prueba create_revolve, create_extrude_poly (puntos en sentido
     ANTIHORARIO: en horario la extrusión sale descentrada) o, para perfiles con cotas exactas, un
     croquis (sketch_extrude/sketch_revolve …)» (L53-56 y el «cuándo» de L62).
  10. «ancla un punto con fix y orienta con horizontal/vertical para que no flote» (L69-70).
  11. «fillet/chamfer/shell/drill_hole modifican la pieza EN SITIO (conserva su id)» (L50-52).
  - **D10**: «combínalo con set_visibility para aislar» → «isolate la aísla sin tocar el
    documento». Los docstrings de `set_visibility`/`set_visibility_bulk` («útil para aislar»)
    siguen igual: el plan no poda docstrings (queda en el inventario de F0).
  - El párrafo «Antes de escribir, PRUEBA… get_command(id)…» pasa al final para que
    `AVISO_CONEXION` siga cerrando un párrafo general en el MCP.
- **Desviaciones del triage** (la regla manda: lo que ya dice un schema se borra; F0 las mandó a
  `GUIA_TECNICA`, pero el schema de hoy las cubre):
  - L18-21, ejemplos de `=expresión`: el docstring de `set_variable` trae `'=NOMBRE'` y
    `'=L/2 - 40'`.
  - L62-66, formato del croquis: `SKETCH_DOC` (la description de `sketch` en los cuatro
    `sketch_*`) ya dice puntos aproximados + solver, lazo cerrado, círculos = agujeros y
    `'=expresión'`. Queda sólo el «cuándo» (perfiles con cotas exactas, en la frase 9).
  - L75-77, `add_joint`: su docstring dice «Cada sólido solo puede ser hijo de UNA junta» y
    `origin` dice «punto del eje, coords. mundo».
  - L53-56, «r ≥ 0, sin auto-intersecciones»: están en los schemas de `create_revolve` y
    `create_extrude_poly`. «Antihorario» sí queda, comprobado: un polígono horario (h = 40) sale
    con Z en [−60, −20] en vez de [−20, 20], contra su schema («centrado en el origen»). **Posible
    bug del ejecutor** (`registry.py::_exec_create_extrude_poly` no normaliza el sentido): al
    backlog, aquí no se toca `commands/`.
  - L108-111, el marco 40×40: no paga sus bytes. La orientación ya está en las frases 4-5,
    `create_frame`/`create_weldment` arman marcos con esquinas, y el ejemplo enseñaba coordenadas
    literales (contra la regla 9).
  - L58-59: «Importar STEP» ya no es un botón de la barra superior sino un ítem del menú Archivo
    (`TopBar.tsx`); el texto nuevo lo dice así.
- **Decisión: `SYSTEM_PROMPT` SÍ cambia ya.** Entre F6 y F5a el chat viejo (`agent/agent.py`, con
  `get_document`, `execute_commands`, `undo_last`, `save_note`) corre con el prompt nuevo. Alcanza
  porque: (1) el prompt viejo ya llevaba el brief, que nombra ~10 tools que el chat viejo no tiene
  (`get_scene`, `verify`, `preview`, `run_batch`, `edit_batch`, `delivery_check`, `near`,
  `get_topology`, `auto_group`, `get_design_guidelines`); la guía suma 4 (`get_command_schemas`,
  `resolve_expression`, `get_expression_grammar`, `get_command`) y a cambio se van 3
  contradicciones (`attach` vs `snap_to`, «usa `get_document`» vs «no vuelques la escena», cierre
  con `check_interference` vs `delivery_check`); (2) `REGLAS_CHAT` nombra una sola tool,
  `propose_commands`, que existe en los dos chats, y dice lo demás sin nombres (leer el modelo y
  las notas, deshacer, ejecutar en modo auto): el chat viejo lo resuelve con sus tools, que se
  describen solas, y su recordatorio de modo auto en `messages[0]` sigue nombrando
  `execute_commands`; (3) una tool ausente no corta el stream: la rama «tool desconocida» de
  `chat_stream` devuelve `is_error`. Costo aceptado: alguna vuelta perdida si el modelo intenta
  una tool del brief que el chat viejo no tiene (ya pasaba). Gate transitorio
  `test_las_reglas_sirven_tambien_al_chat_viejo`: el chat viejo usa este prompt y cada tool de
  `REGLAS_CHAT` existe en él. **Lo borra la F5b** con `agent.py` (añadido a su lista; si no, falla
  por import).
- `tests/test_prompt_chat.py` (9 tests, 142 líneas): brief y `GUIA_TECNICA` en los dos clientes,
  `REGLAS_CHAT` sólo en el chat y `AVISO_CONEXION` sólo en el MCP; `SYSTEM_PROMPT` =
  `system_prompt_chat()`; el prompt no nombra tools fuera del catálogo (salvo las de archivo que
  `REGLAS_CHAT` explique) ni las cuatro viejas; todo identificador con verbo (`get_…`, `create_…`)
  es una tool del chat o un comando del registro; D10 (sin `set_visibility`, con `isolate`); tuteo
  con los detectores de `test_pistas.py` (voseo, «usted», españolismos) y las palabras de la tabla;
  mismos bytes en otro proceso (otro `PYTHONHASHSEED`). Comprobado que se pone rojo con
  `open_project`, con `calc_report` sin explicar, con `get_document`, con `get_scenes`, con
  `set_visibility` en la guía, con «revisá» y con una tool nueva en las reglas.
- Golden del MCP re-congelado SÓLO por el diff deliberado de (a) `instructions.txt`;
  `list_tools.json` y `llamadas.json`, idénticos.
- `mcp_server.py` (1429) y `agent/agent.py` (606) sin tocar; `core/apolo/CLAUDE.md` con la guía
  única (6.7 KB).
- Suite: 1626 passed + 1 skipped (1627 recolectados); `ruff check core tests scripts` limpio.
  Ojo al medir: editar `design/instrucciones.py` con la suite corriendo pone rojo
  `test_bytes_estables_en_otro_proceso` (el proceso de pytest tiene el texto viejo y la sonda
  lee el nuevo); pasó en la corrida limpia.

### F7 — cliente de Anthropic: caché y ningún final silencioso (2026-10-03)

Con la restricción de la sesión principal: **D11 sin decidir** → ni el modelo por defecto ni un
effort por defecto cambian; sólo se vuelven configurables. Referencia usada: la skill
`claude-api` (caché, stop reasons, thinking/effort) y el SDK instalado, no la memoria.

- `agent/modelo.py` (177 líneas; el plan pedía ≤ 120: ≈ 45 son el docstring y los comentarios
  que documentan las variables y el protocolo del ejecutor, ≈ 15 los textos de los avisos; la
  lógica ronda las 100). Sin estado global, no importa nada de `apolo` y `anthropic` se importa
  perezoso. **No está cableado al endpoint** (F5a): el chat vivo sigue en `agent/agent.py`.
  - `config()` lee **en cada llamada** `APOLO_MODEL` (default `claude-opus-4-8`, el de hoy),
    `APOLO_MAX_TOKENS` (16000, el de hoy), `APOLO_EFFORT` (sin valor NO se manda
    `output_config`: rige el default del modelo; con valor, uno de low…max) y
    `APOLO_CHAT_VUELTAS` (20 llamadas por turno). Un valor inválido cierra el turno con `error`
    sin llamar a la API.
  - `conversar(convo, system, tools, ejecutar, cliente=None)` = el bucle de un turno. Agrega a
    `convo` cada respuesta y cada lote de resultados (append-only) y cede `text`, `progreso`,
    `aviso`, `error`, los eventos del ejecutor y SIEMPRE, al final, `done` con `uso`.
  - **Ejecutor inyectado** (lo escribe la F5a sobre `herramientas.ejecutar()`): un generador
    que cede eventos para la UI y RETORNA `({tool_use_id: cuerpo del tool_result}, seguir)`;
    `seguir=False` cierra el turno sin otra vuelta (la propuesta); `modelo.Corte` cierra con
    `error` (proyecto cambiado). Una tool sin cuerpo → `is_error` (nunca un `tool_use` huérfano
    que dé 400).
- **D12**: `system` = un bloque con `cache_control` (render tools → system → messages: cachea
  tools + system) + `cache_control` en la raíz (automático) para la conversación: 2 de 4
  breakpoints, ambos de 5 min (el orden de TTL no se rompe). Las tools van tal cual, en el orden
  recibido. Los kwargs salvo `messages` se arman una vez por turno: idénticos byte a byte en
  cada vuelta y entre turnos iguales (test). `done.uso` = `{input, output, cache_read,
  cache_creation}` sumados de todas las llamadas del turno (`cache_*` en `None` cuenta 0).
- **D13**: `aviso {motivo, mensaje}` ante `max_tokens` (+ `max_tokens`), `refusal` (+
  `categoria` y `explicacion` de `stop_details`; la categoría también en el texto),
  `model_context_window_exceeded`, cualquier razón desconocida y las vueltas agotadas («Llegué
  al tope de N pasos sin terminar…»). `pause_turn` → otra llamada con el turno del asistente
  reenviado, sin mensaje nuevo (cuenta como vuelta: no hay bucle infinito). Las tools de una
  respuesta que no terminó en `tool_use` NO corren y van al historial como `is_error` («No se
  ejecutó…»): el historial queda válido para seguir. En las vueltas agotadas, las tools de la
  última respuesta SÍ corrieron (terminó en `tool_use`) y el aviso lo cuenta. Textos en tuteo
  neutro, pasados por `faltas()` de `test_pistas.py`.
- **`display: "updates"`** sólo para los modelos que la referencia documenta (Fable 5.1,
  Mythos 5.1, Fable 5, Opus 5.5, Sonnet 5.5), por `beta.messages.stream(betas=
  ["thinking-display-updates-2026-08-18"])`; sus notas no vacías salen como `progreso` (F9 las
  pinta). Con el default (Opus 4.8) se omite y la llamada va a `messages.stream`, como hoy.
- **Credenciales**: las resuelve el SDK (`anthropic.Anthropic()` sin argumentos: variable,
  token o perfil de `ant auth login`). Si no resolvió ninguna (`api_key`, `auth_token` y
  `credentials` vacíos) → el mensaje de hoy («Falta la variable de entorno
  ANTHROPIC_API_KEY…») sin llamar (sin esa guarda el SDK lanzaría `TypeError`). Un
  `AuthenticationError` (401) conserva el texto de hoy, «Error del API de Claude: …», como todo
  `APIError`: decirle «falta la variable» a una credencial que existe pero fue rechazada sería
  falso.
- **Pin `anthropic>=0.40` → `>=0.88.0`** (no `>=0.109.1` como anticipó la F0: aquella era la
  versión probada, no la mínima). Evidencia — CHANGELOG del SDK: `cache_control` raíz en 0.83.0,
  effort en 0.75.0, adaptativo en 0.78.0, `stop_details` en 0.88.0; código en los tags: 0.87.0
  NO tiene `Message.stop_details`, 0.88.0 sí, y en 0.88.0 `messages.stream` acepta
  `cache_control`/`output_config`/`thinking`, `beta.messages.stream` acepta `betas` y
  `_transform_typeddict` deja pasar las claves sin tipar (`display: "updates"`). La credencial
  por perfil llega en 0.98.0; se lee con `getattr`, así que de 0.88 a 0.97 cae a las variables.
  **Sin tope superior**: el CI instala la última (1.x); según la guía de upgrade de la skill,
  `modelo.py` no usa nada que 1.x quitó (`temperature`/`top_p`/`top_k`, `output_format` como
  dict, objetos de `httpx`), y el test contra el SDK elige `httpx` o `httpx2` según la mayor
  instalada. En este venv sólo se probó 0.109.1.
- `tests/test_chat_modelo.py` (27): cliente FALSO que guarda los kwargs serializados al llamar
  (cache en `system` y en la raíz, orden de claves con `messages` al final, mismos bytes por
  vuelta y entre turnos, append-only); config leída en cada llamada y valores inválidos; avances
  sólo en los modelos documentados; cada `stop_reason` → su aviso sin correr las tools;
  refusal con y sin categoría; `pause_turn`; vueltas agotadas (con 3 y el default 20); `uso`
  sumado; ejecutor (eventos, tool sin cuerpo, `seguir=False`, `Corte`); credenciales (sin
  ninguna, cliente armado sin argumentos, 401); y el **SDK instalado** con
  `httpx.MockTransport` (SSE de verdad, sin red) en los dos caminos (`/v1/messages` y
  `?beta=true` con su cabecera). Gates: textos por `faltas()`, módulo sin imports de `apolo`.
- **Para D11 (Mario)**: modelo por defecto (hoy `claude-opus-4-8`; el plan propone
  `claude-opus-5-5`, que además prende `display: "updates"` solo), effort (hoy sin
  `output_config`; Opus 5.5 tiene default `medium`, Opus 4.8 `high`) y `max_tokens` (hoy 16000;
  el plan propone 64 000, ya en streaming). Cambiarlos = editar `MODELO`/`MAX_TOKENS` y, si se
  quiere un effort fijo, un default en `config()`; o fijar las variables de entorno sin tocar
  código.
- `core/apolo/CLAUDE.md` gana la línea de `agent/modelo.py`. `agent.py` (606) y `mcp_server.py`
  (1429) sin tocar; golden del MCP sin cambios.
- Suite: 1663 passed + 1 skipped (1664 recolectados); `ruff check core tests scripts` limpio;
  trinquete de tamaño y `test_claude_md.py` verdes.
