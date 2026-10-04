# API (`core/apolo/api/`)

Transporte HTTP/WS (`main.py`), jobs asíncronos (`jobs.py`) y log de errores (`errorlog.py`).
`main.py` además coreografía el FEA (al final); los mapas por pieza de los planos, los datos de
instalación, el stack-up, las aserciones `verify`/`expect`, los insumos de la puerta de entrega,
las reglas de ingeniería y FEA y la preparación del FEA son de [services](../services/CLAUDE.md)
(se está partiendo `main.py`: [plan](../../../docs/plans/partir-api-main.md)). Lo transversal
(`STATE_LOCK`, log, regenerate, Windows) está en el [CLAUDE.md raíz](../../../CLAUDE.md); el
cliente MCP, en [core/apolo](../CLAUDE.md).

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
  `services.assertions.verify_checks` que `/api/verify`. Si alguna falla tras el regenerate →
  `ContractError` y `execute_many`/`edit_many` revierten el lote CONSUMIENDO el snapshot (sin
  undo fantasma; doc bit-idéntico): el callback `verify(scene, created)` corre DENTRO del try.
  Sin `expect`, todo byte-idéntico. Cómo se resuelven `$k`, las poses y las sugerencias:
  [services](../services/CLAUDE.md). [V6.5b](../../../docs/plans/V6.5b-mcp-accion-con-contrato.md)
- Un 404 por id (near, measure, get_topology, edit_command, mass) sale de `_not_found`, que suma
  el «¿quisiste decir…?» de `services/lookup.py`.
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

## Lo que sigue en `main.py` para otros paquetes

- Los mapas por pieza de los planos (fits, datum, GD&T, tolerancias), los datos de instalación,
  el stack-up, las aserciones, la puerta de entrega, las reglas de ingeniería y FEA y la
  preparación del FEA se mudaron a [services](../services/CLAUDE.md), con sus reglas; un 400/404
  de dominio llega como `ServiceError` y `_http_error` lo traduce con su texto EXACTO; `main`
  re-exporta por IDENTIDAD los nombres
  viejos que usan los tests (`_piece_dim_tols`…), deja envoltorios sobre el documento activo
  (`_fea_rules()`, `_stackup_rules()`, `_suggest_ids(m)`) e INYECTA `expand=_expand_ids` (toma
  `STATE_LOCK`, que services no puede nombrar). El juego de planos en PDF y DWG toma sus kwargs
  de `sheet_set_maps(doc)`.
- **FEA** (`_fea_static_run`/`_fea_assembly_run`): la coreografía es de aquí —(a) bajo
  `STATE_LOCK` la preparación de `services/fea_setup.py` + el tmp dir (lo crea y lo borra la API,
  también si la preparación falla) + el STEP; (b) solve FUERA del lock; (c) persistir—. `ids`
  acotado → hipótesis de ALCANCE; `nota` del analista → hipótesis. Persiste con
  `_persist_fea_if_same_project` (si se abrió otro proyecto durante el solve → `guardado: false` +
  `aviso`); el campo en memoria (`_LAST_FEA_FIELD`) vale sólo para su documento. Empotramiento,
  carga y convergencia: [services](../services/CLAUDE.md); malla y solver: [fea](../fea/CLAUDE.md).
- **Stack-up**: el `PUT /api/stackup` hace ROLLBACK si la cadena no evalúa (persistirla
  envenenaba GET y la memoria para siempre); la evaluación aislada por cadena es de
  [services](../services/CLAUDE.md). [V7.3](../../../docs/plans/V7.3-stackup-cadenas-cotas.md)
