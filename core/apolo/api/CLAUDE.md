# API (`core/apolo/api/`)

Transporte HTTP/WS (`main.py`), jobs asíncronos (`jobs.py`) y log de errores (`errorlog.py`).
`main.py` además arma mapas que consumen otros paquetes (planos, `insert_project`, FEA, stack-up):
sus reglas están aquí, al final. Lo transversal (`STATE_LOCK`, log, regenerate, Windows) está en
el [CLAUDE.md raíz](../../../CLAUDE.md); el cliente MCP, en [core/apolo](../CLAUDE.md).

## Mutaciones y su retorno

- Toda mutación pasa por `_state_or_error`: devuelve `affected_command_ids` (el MCP lista sólo
  esos sólidos) y suma `aviso_estructura` cuando hay ≥ `MIN_SOLIDOS_SUJECION` sólidos y 0
  grounds: alarma ambiental en CADA mutación, nunca en lecturas.
  [V6.9](../../../docs/plans/V6.9-puerta-de-entrega.md)
- `PUT /api/commands/{id}` REEMPLAZA los params por defecto (`merge=false`); con `merge=true` es
  PATCH superficial (un sub-objeto `position`/`rotation` se reemplaza entero). El MCP manda
  `merge=true`; la UI elige por caso ([ui](../../../ui/CLAUDE.md)).
- `edit_batch` = N ediciones en UN regenerate atómico y 1 undo. `GET /api/schemas/{type}` evita
  volcar el schema completo.
- `_materialize_insert_project` muta `DOC.attachments`: corre DENTRO del lambda de
  `_state_or_error` (bajo `STATE_LOCK`), nunca antes.
- Lo mismo toda búsqueda en el log que decide la mutación (variable por nombre, comando dueño
  de una junta/mate): va DENTRO del closure (`_state_or_error` deja pasar `HTTPException`, así
  que el 404/400 sale de ahí). Buscar antes y mutar después = TOCTOU.

## Lotes con contrato (`expect`)

- `run_batch`/`edit_batch` aceptan `expect` = aserciones de `verify`, evaluadas con el MISMO
  `_verify_checks` que `/api/verify`. Si alguna falla tras el regenerate → `ContractError` y
  `execute_many`/`edit_many` revierten el lote CONSUMIENDO el snapshot (sin undo fantasma; doc
  bit-idéntico): el callback `verify(scene, created)` corre DENTRO del try. Sin `expect`, todo
  byte-idéntico. [V6.5b](../../../docs/plans/V6.5b-mcp-accion-con-contrato.md)
- `$k` resuelve a los FEATURE_IDS del comando k, 1-INDEXADO (`$1` = primera acción; `$0` lo
  explica el error). Multi-sólido expande en `ids`; en un campo singular → error accionable,
  nunca elige uno. Una clave desconocida en una aserción → error «no reconocida» con las válidas;
  «sin piezas» nombra los tokens que no resolvieron. [V6.5c](../../../docs/plans/V6.5c-fixes-revision.md)
- Un 404 por id (near, measure, get_topology, edit_command, mass, selectores de verify/expect)
  trae «¿quisiste decir…?» (`_suggest_ids`: difflib sobre fids + command_ids + grupos + substring
  de nombre); un command_id multi-sólido sugerido → sus fids hijos.
- `distancia`/`sin_interferencia` aceptan `joint_values` POR ASERCIÓN y se evalúan con el
  mecanismo POSADO (`pose_fn` inyectado en `library/verify.run_verify`, que sigue pura). `pose_fn`
  valida los nombres de junta ANTES de posar: la FK ignora desconocidos y el typo pasaría verde.
  En pose la interferencia suma `interpenetration_report`; caché por pose (N aserciones = 1 FK);
  todo-cero = pose de diseño. [V6.8](../../../docs/plans/V6.8-mcp-fluidez.md)
- `_verify_checks(extra_exclude_pairs/ids)` son las exclusiones del delivery check; `None` deja
  los contratos intactos.
- `open_project` devuelve `briefing` (`_open_briefing`, < 10 KB): resumen por grupo + variables +
  requisitos + notas (últimas 20 + `notas_truncadas`) + salud + variantes.

## Jobs asíncronos (`jobs.py`)

- Ninguna mutación larga vive dentro de una request: `POST`/`PATCH /api/commands/batch?async=true`
  → `202 {job_id}` y el MISMO closure del endpoint corre en un worker (`_sync_or_job`). Sin
  `?async`, byte-idéntico (la UI no se entera). Hoy sólo los lotes lo tienen.
- `JobStore`: cola FIFO con UN worker (`STATE_LOCK` serializa igual y el orden importa), retiene
  los 20 terminados, en memoria. `GET /api/jobs/{id}?wait_s=0..30` = long-poll.
- Lock HOJA: el `_cv` del store jamás se sostiene llamando al closure (que toma `STATE_LOCK`); el
  worker corre `fn()` sin lock propio y escribe el resultado después. `jobs.py` no importa
  FastAPI (`_describe_error` duck-tipea `status_code`/`detail`).
- Guardia de proyecto: el job captura `PROJECT_ID` al encolar y lo revalida DENTRO del RLock que
  ejecuta el lote; si el proyecto activo cambió → 409 y no aplica. `restore_revision` conserva el
  id (el lote aplica sobre lo restaurado, como en sync).
- Un 404 de job tras un reload NO significa «no aplicó» (los jobs viven en memoria; el autosave
  ya guardó): verificar con get_scene/health, nunca reintentar a ciegas. El 404 lo dice.
  [V6.5e](../../../docs/plans/V6.5e-mcp-jobs-asincronos.md)

## Lecturas a escala

- Ninguna lectura de rutina vuelca la escena: < 10 KB por lectura a 1000 piezas.
  `GET /api/scene/summary` (resumen por GRUPO) es la entrada a un proyecto grande;
  `get_scene(ids|name|limit|offset)` pagina briefs sin mallas armados en el SERVIDOR
  (`_scene_filtered`/`_feature_brief`: mismos campos que el `_scene_brief` del MCP) y declara
  `total_filtrado`/`truncado` (sin caps silenciosos). [V6.5](../../../docs/plans/V6.5-mcp-a-escala.md)
- `get_scene()` sin params = payload completo con mallas, byte-idéntico: lo usa el viewport.
- `_expand_ids` acepta NOMBRES de grupo en isolate/highlight/fit (render, pick, drawing_spec,
  manual); por eso los nombres de grupo no admiten comas.
- Los lotes de apariencia y conexiones (`POST /api/features/material|color`,
  `/api/connections/remove`) validan TODO antes de tocar nada: un id malo → 404 con sugerencia y
  CERO efectos parciales; un solo autosave y un solo undo.
- `GET /api/commands` (find_commands): búsqueda superficial (1 nivel de dict) de los comandos que
  crearon o referencian un feature; sin filtros → 400.

## Deltas de escena

- `_geom_rev(fid, shape)` = revisión por IDENTIDAD del shape (el regen incremental la conserva en
  lo no re-ejecutado). `scene_payload(known=…)` manda `same: true` + metadatos volátiles
  (id/rev/name/color/visible/group/is_guide) de lo que el cliente ya tiene (`POST /api/scene/delta`).
  Un metadato nuevo que el viewport deba ver va también en la entrada `same`: no sube el rev.
- `SCENE_EPOCH` (uuid por proceso): si el cliente trae otro, se manda el payload COMPLETO (tras un
  restart los revs renacen en 1 y colisionarían). Cliente: [ui](../../../ui/CLAUDE.md).
  [V6.2](../../../docs/plans/V6.2-rendimiento.md) · [V6.2e](../../../docs/plans/V6.2e-fixes-revision.md)

## Locks: el trabajo pesado sale de `STATE_LOCK`

- Bajo `STATE_LOCK` sólo se EXTRAE (OCCT → datos puros: teselado, cascos, XML MuJoCo, STEP); el
  proceso pesado corre fuera con su lock (`RENDER_LOCK`, `PHYSICS_LOCK`, `FEA_LOCK`). Un endpoint
  nuevo de render o simulación sigue el patrón. `export_stl` y `drawing_spec` siguen bajo el lock
  (su HLR es OCCT).

## Autosave y arranque

- `_autosave()` no escribe: marca sucio y arma un flush único (`_AutosaveScheduler`, debounce
  500 ms, techo 3 s). `_flush_body` toma bytes + `pack()` + STORE/PROJECT_ID bajo `STATE_LOCK`
  (snapshot atómico) y escribe la SQLite FUERA.
- Orden ÚNICO de locks `_flush_lock → STATE_LOCK`, jamás al revés (deadlock switch ↔ Timer);
  `_flush_lock` se sostiene todo el flush, reintentos incluidos. Cambiar de proyecto =
  `_project_switch()` (flush del actual + swap atómico bajo ambos locks).
- Durable: reintentos `_AUTOSAVE_RETRIES`; agotados (también si falla la serialización) →
  `AUTOSAVE_ERROR` en el payload + WS `autosave_failed`. La caché de geometría va aparte,
  best-effort. Flush FORZOSO en shutdown/restore.
- Arranque: reciente corrupto → carga tolerante; si ni así abre → `STARTUP_ERROR` + doc vacío con
  `PROJECT_ID=None` (no crea un «Sin título» que pise el reciente). `project/new` y `project/open`
  (upload) crean id PROPIO.
- `GET /api/health` = `check_integrity` + suprimidos + `autosave_pending`/`autosave_failed` +
  `startup_error`; no tiene tool MCP. [V6.1](../../../docs/plans/V6.1-robustez-industrial.md)

## Tests de la API

- Los tests no ejecutan el lifespan → no tocan `data/apolo.db`. Patrón:
  `api.DOC = Document("t"); TestClient(api.app)`; el arranque real vive en
  `initialize_store(db_path)`.
- Fixtures con STORE: `_flush_autosave()` antes de leer disco y `_autosave_sched.cancel()` en el
  teardown.
- `tests/conftest.py` (autouse, sesión) redirige `logs/errors.log` a tmp: sin él la tortura
  escribía errores FALSOS en el log que se lee al «revisa» (commit `3e935f4`).

## Mapas que viven en `main.py` para otros paquetes

- **Fits por pieza** (planos): `_feature_fit_maps` da {feature_id → {Ø → clase}} desde el NOMBRE
  («… Ø35 g6») + `drill_hole.fit`, y cada lámina rotula EL SUYO (`sheet_set(piece_fits=)`). El
  conjunto usa `_scene_fit_map` (`_hole_fit_map` = el mismo sobre toda la escena), que OMITE un Ø
  en conflicto: mejor ausente que equivocado. `drawing_spec` lo computa sobre la escena EFECTIVA
  (aislar un eje da su fit). [V7.2c](../../../docs/plans/V7.2c-fixes-re-auditoria.md)
- **Datum funcional**: `_piece_datum_sides` deriva los lados de montaje de los FASTENERS
  declarados (soldadura > perno > contacto; eje = solape mínimo de bboxes); PROHIBIDO inferir por
  nombre. Devuelve LISTA por peso: la cara que atraviesa un perno es ⊥ a la vista de sus círculos,
  así que cada vista usa el primer lado que proyecte como borde.
  [V7.5](../../../docs/plans/V7.5-e22-datum-funcional.md)
- **GD&T**: `_piece_datum_frame` = A (cara de mayor peso) + B/C sólo si son ORTOGONALES; el
  `motivo` va a la leyenda (sin él, el marco es decorativo). `_piece_pos_tols`: t =
  `bolt_pattern_budget(flotante=)`; el Ø del perno sale de la tabla ISO 273 INVERTIDA (Ø13.5 es el
  paso de un M12) y el sólido en el eje es respaldo. Sin perno identificable NO hay marco: una
  tolerancia inventada es peor que su ausencia (el taller la fabrica).
- **Tolerancia justificada**: `_piece_dim_tols` sale de los eslabones `{id, eje}` de las cadenas
  DECLARADAS; sólo bandas SIMÉTRICAS (un fit asimétrico viaja en su callout); varias cadenas →
  gana la más estricta; una cadena inválida no tumba el juego.
- **Instalación**: `_installation_data` excluye la tornillería (`lints._is_bolt`) de los apoyos
  (los pernos de anclaje como grounds diluían la carga por apoyo 5×), lee las claves del catálogo
  sin distinguir mayúsculas (`potencia_kW`) y devuelve `({}, {})` sin grounds.
  [V7.6](../../../docs/plans/V7.6-e2-fino.md)
- **FEA**: el endpoint deriva el empotramiento de los `grounds` y la carga de
  `requirements.carga_kg` sobre la cama/mesa (`_BED_RE`) o de `loads` explícitos; vigencia por
  volumen conjunto (`DOC.fea["group:<nombre>"]`); re-correr con otro `mesh_size` mueve el run
  previo a `convergencia` (tope 3); `ids` acotado → hipótesis de ALCANCE; `nota` del analista →
  hipótesis. Persiste con `_persist_fea_if_same_project` (si se abrió otro proyecto durante el
  solve → `guardado: false` + `aviso`). Malla y solver: [fea](../fea/CLAUDE.md).
- **Stack-up**: `_evaluate_stackups` aísla cada cadena (una mala = `{error}`, nunca tumba GET ni
  la memoria); pieza FALTANTE = error sin veredicto, jamás parcial; el PUT hace ROLLBACK si la
  cadena no evalúa; «cerrada por construcción» sólo si el fasten lo creó un comando `join_bolted`
  (no por nombre `jb_*`); un perno manual = holgura informativa, sin veredicto.
  [V7.3](../../../docs/plans/V7.3-stackup-cadenas-cotas.md)
