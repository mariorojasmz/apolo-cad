# Backend de Apolo (`core/apolo/`)

Lo común del backend que no tiene paquete propio: MCP (`mcp_server.py`), agente de la app
(`agent/`), criterio de diseño (`design/`), cinemática (`robotics/`) y física (`physics/`). Cada
paquete con CLAUDE.md propio (`kernel`, `commands`, `doc`, `assembly`, `library`, `drawing`,
`fea`, `api`) trae sus reglas; lo transversal (locks, log, flujo de trabajo) está en el
[CLAUDE.md raíz](../../CLAUDE.md). Este archivo carga en TODA lectura de backend: se mantiene ≤ 10 KB.

## Reglas comunes

- **Toda caché por `id(shape)` guarda la REFERENCIA al shape y verifica `is` en el lookup**:
  Python recicla el id de un shape recolectado y otra pieza recibiría la entrada ajena (bug real
  de la suite). Patrón de `_RENDER_MESH_CACHE` (kernel) y `_HULL_CACHE` (`physics/hull.py`).

## MCP (`mcp_server.py`): cliente fino

- Sólo habla HTTP con la API: sin lógica de dominio ni imports de `doc`/`kernel`. Una tool nueva
  = endpoint en `api/` + wrapper aquí; el host MCP se reinicia para verla.
- El brief sin mallas (`_scene_brief`) espeja los campos de `_feature_brief` del servidor: un
  campo nuevo va en los dos. Con `detail="diff"` lista sólo los sólidos de
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
- `render_view` fuerza `vtk_only` (sin caída a matplotlib). Las tools que producen archivos
  (`motion_gif`, `drawing_set`, `calc_report`, `drop_test`, exports…) los escriben a `path`.

## Agente de la app (`agent/`) y criterio (`design/`)

- `design/guidelines.py` es la fuente ÚNICA del criterio de ingeniería: `design_brief()` (capa 1)
  se inyecta en las instrucciones del MCP y en `SYSTEM_PROMPT` (`agent/prompts.py`);
  `design_guidelines()` (capa 2) va bajo demanda. Se edita ahí, nunca en las copias.

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
