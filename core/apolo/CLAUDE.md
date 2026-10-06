# Backend de Apolo (`core/apolo/`)

Lo común del backend que no tiene paquete propio: MCP (`mcp_server.py`), agente de la app
(`agent/`), criterio de diseño (`design/`), cinemática (`robotics/`) y física (`physics/`). Cada
paquete con CLAUDE.md propio (`kernel`, `commands`, `doc`, `assembly`, `library`, `drawing`,
`fea`, `services`, `api`) trae sus reglas; lo transversal (locks, log, flujo de trabajo) está en el
[CLAUDE.md raíz](../../CLAUDE.md). Este archivo carga en TODA lectura de backend: se mantiene ≤ 10 KB.

## Reglas comunes

- **Toda caché por `id(shape)` guarda la REFERENCIA al shape y verifica `is` en el lookup**:
  Python recicla el id de un shape recolectado y otra pieza recibiría la entrada ajena (bug real
  de la suite). Patrón de `_RENDER_MESH_CACHE` (kernel) y `_HULL_CACHE` (`physics/hull.py`).

## MCP (`mcp_server.py`): cliente fino

- Sólo habla HTTP con la API: sin lógica de dominio ni imports de `doc`/`kernel`. Una tool nueva
  = endpoint en `api/` + wrapper aquí + su caso en `scripts/golden_mcp_casos.py` + su lugar en
  `tools/catalogo.py`: en `CHAT` (`muta`, `etiqueta`, `ocultar` las rutas de archivo) o en
  `FUERA_DEL_CHAT` con el motivo — si falta, `tests/test_catalogo_chat.py` falla. Una lectura
  nueva del chat lleva además su muestra en ese test (se corre contra la API y no debe mutar).
  El host MCP se reinicia para verla.
- **Golden** (`tests/test_mcp_golden.py`): congela instructions, `list_tools()` y una
  `call_tool` real por tool (peticiones y salida) contra un transporte falso. Cambiar lo que ve
  un cliente MCP —docstring, default, orden de params, salida— lo pone rojo; si es deliberado,
  revisa el diff y `python scripts/golden_mcp.py --congelar`.
  [chat-cliente-igual](../../docs/plans/chat-cliente-igual.md)
- **E2E por stdio** (`python -B scripts/e2e_mcp.py --puerto N --proyecto 38`): un cliente `mcp`
  real contra una API levantada; recorre lecturas, `preview`, un lote con contrato que falla y
  `set_variable` + `undo`, deja el proyecto como estaba y sale con 1 si un paso falla. Siempre
  contra una API sobre una COPIA de la base (rehúsa el :8000 sin `--forzar`).
- `_api` habla con el destino que el hilo fijó (`tools/destino.py`, `threading.local`: el chat
  de la app) o, si no hay, con `APOLO_URL`. Lo que un test parchea por nombre (`_api`,
  `_submit_and_wait`, `APOLO_URL`, `APOLO_MCP_WAIT_S`) no sale de `mcp_server.py`; lo que se
  saca se re-exporta con el mismo nombre. Las instructions salen de `design/instrucciones.py`.
- El brief de UNA pieza tiene una sola forma, `brief.py::brief_pieza` (puro; opcionales omitidos,
  nunca `null`): la arman `_scene_brief` (MCP) y `_feature_brief` (servidor); un campo nuevo va
  ahí. `tests/test_mcp_brief.py` exige el mismo texto. Con `detail="diff"` lista sólo los sólidos de
  `affected_command_ids`, también por PREFIJO (las piezas de un `insert_project` llevan
  command_id sintético `{cmd}_{orig}`); `variables` viaja sólo si la operación tocó un
  `set_variable`. Pasa al agente `contrato` y `aviso_estructura` ([api](api/CLAUDE.md)).
- `run_batch`/`edit_batch` SIEMPRE encolan como job (`_submit_and_wait`) y esperan
  `APOLO_MCP_WAIT_S` (90 s: bajo los 120 de httpx y los ~180 del host). Si no llega, devuelven un
  RECIBO `{job, seguir}`, no un error, y `get_job` re-pregunta sin riesgo. El camino seguro no
  puede ser opt-in: el agente no sabe cuánto tardará el lote. Un job fallido usa el mismo texto
  que el 400 (`_reject`). Servidor: [api](api/CLAUDE.md).
  [V6.5e](../../docs/plans/V6.5e-mcp-jobs-asincronos.md)
- `edit_command`/`edit_batch` hacen PATCH por defecto (`merge=True`, superficial); el REST, no.
- `check_assembly`/`gravity_test` cuentan por defecto SÓLO la sujeción DECLARADA
  (`with_autodetect=False`, igual que la API y `delivery_check`); con autodetect el agente veía
  verde lo que la puerta de entrega marcaba rojo. `True` es exploración explícita.
- `render_view` fuerza `vtk_only` (sin caída a matplotlib). Las tools que producen archivos
  (`motion_gif`, `drawing_set`, `calc_report`, `drop_test`, exports…) los escriben a `path`.

## Agente de la app (`agent/`) y criterio (`design/`)

- `agent/herramientas.py` da al chat las tools del MCP, sin copias: `definiciones()` sale de
  `mcp.list_tools()` en el orden del catálogo y `ejecutar()` corre `mcp.call_tool` en el hilo
  del chat apuntado a `tools/destino.py`; en modo propuesta lo que `muta` no corre. El MCP se
  importa perezoso restaurando el logger raíz (FastMCP lo reconfigura al construirse).
- `agent/modelo.py` es el cliente de Anthropic del chat: config LEÍDA en cada
  llamada (`APOLO_MODEL`, `APOLO_MAX_TOKENS`, `APOLO_EFFORT`, `APOLO_CHAT_VUELTAS`; los defaults
  esperan D11), caché en el último bloque de `system` + el automático, conversación append-only
  y ningún final silencioso: `aviso` ante `max_tokens`/`refusal`/vueltas agotadas.
- `agent/chat.py` (con `APOLO_CHAT_HTTP=1` hasta la F5b de
  [chat-cliente-igual](../../docs/plans/chat-cliente-igual.md)) es un cliente HTTP más de la
  propia API: lee el token de `GET /api/health` al empezar y lo manda en `X-Apolo-Documento` (un
  409 corta el turno); el modo va en el ÚLTIMO mensaje de la persona, nunca en `messages[0]`;
  cupo `APOLO_CHAT_MAX` → 429. Ningún módulo nuevo de `agent/` llega a `apolo.state`,
  `apolo.api` ni `anyio` (gate transitivo en `tests/test_chat_http.py`); eventos SSE en
  `agent/eventos.py`, en espejo de `ui/src/chat/sse.ts`.
- `design/guidelines.py` es la fuente ÚNICA del criterio de ingeniería: `design_brief()` (capa 1)
  va siempre en los dos clientes; `design_guidelines()` (capa 2), bajo demanda. Se edita ahí,
  nunca en las copias.
- Una sola guía (`design/instrucciones.py`): MCP = brief + `GUIA_TECNICA` (cómo se trabaja con
  el CAD por tools; cambiarla cambia el golden) + `AVISO_CONEXION`; chat (`system_prompt_chat()`,
  que es `SYSTEM_PROMPT`) = brief + `GUIA_TECNICA` + `REGLAS_CHAT` (sólo lo de la app). Lo que ya
  dice un schema o un docstring no se repite. `tests/test_prompt_chat.py` impide que el prompt
  del chat nombre tools que el chat no tiene.
- El chat viejo (`chat_stream`, sin el flag; lo borra la F5b) queda ATADO al documento activo
  al empezar: la API le inyecta `AgentHooks` (`agent/hooks.py`: `alive`/`after_mutation`/
  `notify`) y cada mutación revalida `alive()` DENTRO de `STATE_LOCK` (`mutation_guard`). Si se
  abrió otro proyecto o se restauró una revisión, no aplica nada y el stream cierra con un
  evento `error`. El agente NO importa `apolo.api` (api → agent, nunca al revés).

## Cinemática (`robotics/`)

- La FK (`pose.py::posed_shapes`) mueve SÓLO los hijos declarados de cada junta, sin flood por
  fijadores: un cuerpo rígido multi-pieza se completa con juntas `fija` o con
  `add_joint(arrastrar=true)` ([commands](commands/CLAUDE.md)).
- `posed_shapes` IGNORA nombres de junta desconocidos: quien reciba `joint_values` del agente
  los valida contra `DOC.joints` antes (lo hacen `set_motion` y el `pose_fn` de los contratos);
  si no, un typo pasa verde como «pose de diseño». [V6.8](../../docs/plans/V6.8-mcp-fluidez.md)
- Signo: `Rotation(0,v,0)` de build123d gira HORARIO en XZ (+v en una junta Y = el respaldo
  sube). `get_kinematics` publica la convención en `sentido`: se lee, no se calibra con renders.
- GIF del estudio (`anim.py`, `POST /api/motion.gif`, tool `motion_gif`): `extract_motion_frames`
  (FK + teselado) bajo `STATE_LOCK` → snapshots puros → `render_motion_gif` fuera, bajo
  `RENDER_LOCK`. La cámara se fija a la UNIÓN de los bbox de todo el recorrido (si no, cada
  fotograma se re-encuadra y el mecanismo «respira»); `fit_ids` explícito gana. El teselado no
  se cachea entre fotogramas (cada pose crea shapes nuevos): costo ≈ steps × escena.

## Física (`physics/`)

- Dos fases: `prepare_*` (XML MuJoCo horneado, OCCT, bajo `STATE_LOCK`) y `simulate_*` (bucle
  `mj_step` sobre datos puros, bajo `PHYSICS_LOCK`); `stability_test`/`drop_test` son wrappers
  de compatibilidad. [V6.2](../../docs/plans/V6.2-rendimiento.md)
- `gravity_test`: piezas sujetas = estáticas, el resto cae, con casco CONVEXO por sólido.
  `drop_test` usa AABB.
