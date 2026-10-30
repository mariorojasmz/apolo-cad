# Backend de Apolo (`core/apolo/`)

Lo común del backend sin paquete propio: MCP (`mcp_server.py`), agente de la app (`agent/`),
criterio (`design/`), sandbox de scripts y cinemática (`robotics/`). Cada paquete con CLAUDE.md
propio trae sus reglas (índice y lo transversal en el [CLAUDE.md raíz](../../CLAUDE.md)). Carga
en TODA lectura de backend: ≤ 10 KB.

## Reglas comunes

- **Toda caché por `id(shape)` guarda la REFERENCIA al shape y verifica `is` en el lookup**:
  Python recicla el id de un shape recolectado y otra pieza recibiría la entrada ajena. Patrón:
  `_RENDER_MESH_CACHE` (kernel), `_HULL_CACHE` (`physics/hull.py`).
- **Un texto que el agente lee de un docstring pasa por `inspect.cleandoc`**: 3.13 quita la
  sangría al compilar y 3.11/3.12 no, así que el `__doc__` crudo cambia según la versión. Tools:
  `tools/fastmcp_limpio.py`; comandos: la description del schema de pydantic
  (`tests/test_docstrings_limpios.py`).

## MCP (`mcp_server.py`): cliente fino

- Sólo habla HTTP con la API: sin lógica de dominio ni imports de `doc`/`kernel`. Una tool nueva
  = endpoint en `api/` + wrapper en `tools/<tema>.py` (nunca en línea en `mcp_server.py`, que
  guarda la infraestructura, el bloque «modelado» y los registradores), registrada EN SU LUGAR
  (el orden de `list_tools()` es el del golden): el tema la devuelve y `mcp_server` la re-exporta
  con `globals().update(<tema>.registrar(...))`
  ([partir-nucleo-congelado](../../docs/plans/partir-nucleo-congelado.md) D5). `registrar`
  recibe `_api` como lambda TARDÍA (mutación: `_mutacion`, ver `tools/cirugia.py`; job que no
  muta: `_submit_and_wait`, `tools/cosim.py`) y NUNCA importa `apolo.mcp_server` (con `-m` es
  `__main__`: la tool caería en otra copia). Más su caso en `scripts/golden_mcp_casos.py` y su
  lugar en `tools/catalogo.py` (`CHAT` o `FUERA_DEL_CHAT` con motivo: `tests/test_catalogo_chat.py`;
  una lectura nueva del chat lleva su muestra). El host MCP se reinicia para verla.
- **Golden** (`tests/test_mcp_golden.py`): congela instructions, `list_tools()` y una
  `call_tool` real por tool (peticiones y salida) contra un transporte falso. Cambiar lo que ve
  un cliente MCP —docstring, default, orden de params, salida— lo pone rojo; si es deliberado,
  revisa el diff y `python scripts/golden_mcp.py --congelar`.
  [chat-cliente-igual](../../docs/plans/chat-cliente-igual.md)
- **E2E por stdio** (`python -B scripts/e2e_mcp.py --puerto N --proyecto 38`): cliente `mcp`
  real contra una API levantada SOBRE UNA COPIA de la base (rehúsa el :8000 sin `--forzar`).
- `_api` habla con el destino que el hilo fijó (`tools/destino.py`, `threading.local`: el chat
  de la app) o, si no hay, con `APOLO_URL`. Lo que un test parchea por nombre (`_api`,
  `_submit_and_wait`, `APOLO_URL`, `APOLO_MCP_WAIT_S`) no sale de `mcp_server.py`; lo que se
  saca se re-exporta con el mismo nombre. Las instructions salen de `design/instrucciones.py`.
- El brief de UNA pieza tiene una sola forma, `brief.py::brief_pieza` (puro; opcionales omitidos,
  nunca `null`): la usan `_scene_brief` (MCP) y `_feature_brief` (servidor); un campo nuevo va
  ahí (`tests/test_mcp_brief.py`). Con `detail="diff"` lista sólo los sólidos de
  `affected_command_ids`, también por PREFIJO (command_id sintético `{cmd}_{orig}` de
  `insert_project`); `variables` viaja sólo si se tocó un `set_variable`, y sólo las tocadas y
  sus dependientes (`variables_omitidas`, [trabas-de-modelado](../../docs/plans/trabas-de-modelado.md)
  D5). Pasa al agente `contrato` y `aviso_estructura` ([api](api/CLAUDE.md)).
- Toda mutación que regenera (`run_command`, `edit_command`, `set_variable`, `run_batch`,
  `edit_batch`, `remove_commands`) SIEMPRE encola como job (`_mutacion` → `_submit_and_wait`;
  nunca opt-in: el agente no sabe cuánto tardará) y espera `APOLO_MCP_WAIT_S` (bajo los timeouts
  de httpx y del host). Si no llega, devuelve un RECIBO `{job, seguir}`, no un error, y `get_job`
  re-pregunta sin riesgo. Un job fallido usa el texto del 400 (`_reject`); un resultado sin
  `features` (`remove?detail=diff`) pasa tal cual. Servidor: [api](api/CLAUDE.md).
  [V6.5e](../../docs/plans/V6.5e-mcp-jobs-asincronos.md) ·
  [sandbox-caliente](../../docs/plans/sandbox-caliente.md)
- `edit_command`/`edit_batch` hacen PATCH por defecto (`merge=True`, superficial); el REST, no.
- `check_assembly`/`gravity_test` cuentan por defecto SÓLO la sujeción DECLARADA
  (`with_autodetect=False`, como la API y `delivery_check`); `True` es exploración explícita.
- `render_view` fuerza `vtk_only` (sin caída a matplotlib). Las tools que producen archivos los
  escriben a `path`; `calc_report`, `assembly_manual`, `drawing_set` y `drawing` van como job
  (`tools/entregable.py`: recibo → `get_job` lo guarda), y también las lecturas `delivery_check`,
  `check_interference` y `engineering_check` (`get_job` las da como la tool por su `tipo`:
  `validacion.de_job`).

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
- `design/guidelines.py` es la fuente ÚNICA del criterio: `design_brief()` (capa 1) va siempre
  en los dos clientes; `design_guidelines()` (capa 2), bajo demanda. Se edita ahí, nunca en copias.
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
  La API lo precalienta (`APOLO_SANDBOX_PREWARM=0` lo apaga, como la suite). Lock: en la
  [raíz](../../CLAUDE.md).
- La forma vuelve en BRep y su TIPO imita lo que daba STEP (con ubicación propia → `Compound`;
  sin ella, compound de un sólido → `Solid`). Es empírico para build123d 0.10:
  `test_brep_equivale_a_step` lo vigila en un upgrade. Cambiar lo que entrega el worker = subir
  la `version` de `run_script`. [sandbox-caliente](../../docs/plans/sandbox-caliente.md)

## Cinemática (`robotics/`)

- La FK (`pose.py::posed_shapes`) mueve SÓLO los hijos declarados de cada junta, sin flood por
  fijadores: un cuerpo rígido multi-pieza se completa con juntas `fija` o con
  `add_joint(arrastrar=true)` ([commands](commands/CLAUDE.md)). La cadena de izaje no es rígida:
  `pose_izaje.py` la rehace desde sus anclas posadas ([plan](../../docs/plans/cadena-de-izaje.md)).
- `posed_shapes` IGNORA nombres de junta desconocidos: quien reciba `joint_values` del agente
  los valida contra `DOC.joints` antes (lo hacen `set_motion` y el `pose_fn` de los contratos);
  si no, un typo pasa verde como «pose de diseño». [V6.8](../../docs/plans/V6.8-mcp-fluidez.md)
- Signo: `Rotation(0,v,0)` de build123d gira HORARIO en XZ. `get_kinematics` publica la
  convención en `sentido`: se lee, no se calibra con renders.
- GIF del estudio (`anim.py`, tool `motion_gif`): `extract_motion_frames` bajo `STATE_LOCK`,
  `render_motion_gif` fuera, bajo `RENDER_LOCK`. La cámara se fija a la UNIÓN de los bbox de todo
  el recorrido (si no, el mecanismo «respira»); `fit_ids` explícito gana. El teselado no se cachea
  entre fotogramas (cada pose crea shapes nuevos).
