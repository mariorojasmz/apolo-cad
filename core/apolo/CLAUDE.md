# Backend de Apolo (`core/apolo/`)

Lo común del backend que no tiene paquete propio: MCP (`mcp_server.py`), agente de la app
(`agent/`), criterio de diseño (`design/`), sandbox de scripts y cinemática (`robotics/`). Cada
paquete con CLAUDE.md propio (`kernel`, `commands`, `doc`, `assembly`, `library`, `drawing`,
`fea`, `services`, `api`, `physics` —dos fases de lock—, `plc`, `cosim`) trae sus reglas; lo transversal (locks, log, flujo
de trabajo) está en el [CLAUDE.md raíz](../../CLAUDE.md). Este archivo carga en TODA lectura de
backend: se mantiene ≤ 10 KB.

## Reglas comunes

- **Toda caché por `id(shape)` guarda la REFERENCIA al shape y verifica `is` en el lookup**:
  Python recicla el id de un shape recolectado y otra pieza recibiría la entrada ajena (bug real
  de la suite). Patrón de `_RENDER_MESH_CACHE` (kernel) y `_HULL_CACHE` (`physics/hull.py`).
- **Un texto que el agente lee de un docstring pasa por `inspect.cleandoc`**: 3.13 quita la
  sangría al compilar y 3.11/3.12 no, así que el `__doc__` crudo cambia según la versión. Tools:
  `tools/fastmcp_limpio.py`; comandos: la description del schema de pydantic
  (`tests/test_docstrings_limpios.py`).

## MCP (`mcp_server.py`): cliente fino

- Sólo habla HTTP con la API: sin lógica de dominio ni imports de `doc`/`kernel`. Una tool nueva
  = endpoint en `api/` + wrapper (`mcp_server.py` está en el trinquete de tamaño: va a
  `tools/<tema>.py` con un `registrar(mcp, api)` que `mcp_server` llama al final, como
  `tools/mcp_electrico.py`, `tools/simulacion.py` y `tools/calidad.py` (`publication_gate`); una mutación recibe `_mutacion` en vez de `_api`,
  como `tools/cirugia.py`, y lo que corre como job sin ser mutación, `_submit_and_wait`
  (`tools/cosim.py`); ese módulo NUNCA importa `apolo.mcp_server`: con `-m` el servidor es
  `__main__` y la tool caería en otra copia) + su caso en `scripts/golden_mcp_casos.py` + su lugar
  en `tools/catalogo.py` (`CHAT` o `FUERA_DEL_CHAT` con el motivo; lo exige
  `tests/test_catalogo_chat.py`, donde una lectura nueva del chat lleva su muestra). El host MCP
  se reinicia para verla.
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
- Toda mutación que regenera (`run_command`, `edit_command`, `set_variable`, `run_batch`,
  `edit_batch`, `remove_commands`) SIEMPRE encola como job (`_mutacion` → `_submit_and_wait`) y espera
  `APOLO_MCP_WAIT_S` (90 s: bajo los 120 de httpx y los ~180 del host). Si no llega, devuelve un
  RECIBO `{job, seguir}`, no un error, y `get_job` re-pregunta sin riesgo. El camino seguro no
  puede ser opt-in: el agente no sabe cuánto tardará el regenerate. Un job fallido usa el mismo
  texto que el 400 (`_reject`); un resultado sin `features` (ya liviano: `remove?detail=diff`)
  pasa tal cual, sin `_scene_brief`. Servidor: [api](api/CLAUDE.md).
  [V6.5e](../../docs/plans/V6.5e-mcp-jobs-asincronos.md) ·
  [sandbox-caliente](../../docs/plans/sandbox-caliente.md)
- `edit_command`/`edit_batch` hacen PATCH por defecto (`merge=True`, superficial); el REST, no.
- `check_assembly`/`gravity_test` cuentan por defecto SÓLO la sujeción DECLARADA
  (`with_autodetect=False`, igual que la API y `delivery_check`); con autodetect el agente veía
  verde lo que la puerta de entrega marcaba rojo. `True` es exploración explícita.
- `render_view` fuerza `vtk_only` (sin caída a matplotlib). Las tools que producen archivos
  (`motion_gif`, `drawing_set`, `calc_report`, `drop_test`, exports…) los escriben a `path`;
  `calc_report`, `assembly_manual`, `drawing_set` y `drawing` van como job (`tools/entregable.py`:
  recibo → `get_job` lo guarda).

## Agente de la app (`agent/`) y criterio (`design/`)

- `agent/herramientas.py` da al chat las tools del MCP, sin copias: `definiciones()` sale de
  `mcp.list_tools()` en el orden del catálogo y `ejecutar()` corre `mcp.call_tool` en el hilo
  del chat apuntado a `tools/destino.py`; en modo propuesta lo que `muta` no corre. El MCP se
  importa perezoso restaurando el logger raíz (FastMCP lo reconfigura al construirse).
- El chat de la app (`agent/chat.py`, cliente de Anthropic en `agent/modelo.py`) **viene
  APAGADO** (D19: Apolo se usa por MCP; `APOLO_CHAT=1` lo prende). Es un cliente HTTP más de la
  API: ningún módulo de `agent/` llega a `apolo.state`, `apolo.api` ni `anyio`
  (`tests/test_chat_http_capas.py`); config leída en cada llamada, sin final silencioso (`aviso`).
  Detalle (token de documento, modo del turno, caché, SSE en espejo de `ui/src/chat/sse.ts`):
  [chat-cliente-igual](../../docs/plans/chat-cliente-igual.md).
- `design/guidelines.py` es la fuente ÚNICA del criterio de ingeniería: `design_brief()` (capa 1)
  va siempre en los dos clientes; `design_guidelines()` (capa 2), bajo demanda. Se edita ahí,
  nunca en las copias.
- Una sola guía (`design/instrucciones.py`): MCP = brief + `GUIA_TECNICA` (cómo se trabaja con
  el CAD por tools; cambiarla cambia el golden) + `AVISO_CONEXION`; chat (`system_prompt_chat()`)
  = brief + `GUIA_TECNICA` + `REGLAS_CHAT` (sólo lo de la app). Lo que ya dice un schema o un
  docstring no se repite. `tests/test_prompt_chat.py` impide que el prompt del chat nombre tools
  que el chat no tiene.

## Sandbox de scripts (`sandbox.py`, `sandbox_worker.py`)

- UN worker caliente por proceso (`subprocess.Popen`, nunca `multiprocessing`): importa build123d
  una vez; `SCRIPT_TIMEOUT_S` cuenta sólo la ejecución, el arranque tiene su propio límite. Se
  recicla tras error, timeout, crash y cada 500 scripts, y sale al ver EOF en stdin. El hijo no
  importa `kernel`/`doc`/`commands` (lo exige un test): lo liviano compartido va en `brep_io.py`.
  La API lo precalienta al arrancar (`APOLO_SANDBOX_PREWARM=0` lo apaga; la suite lo apaga en
  `conftest`). Lock: regla en la [raíz](../../CLAUDE.md).
- La forma vuelve en BRep y su TIPO imita lo que daba STEP (con ubicación propia → `Compound`;
  sin ella, compound de un sólido → `Solid`). Es empírico para build123d 0.10:
  `test_brep_equivale_a_step` lo vigila en un upgrade. Cambiar lo que entrega el worker = subir
  la `version` de `run_script`. [sandbox-caliente](../../docs/plans/sandbox-caliente.md)

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
