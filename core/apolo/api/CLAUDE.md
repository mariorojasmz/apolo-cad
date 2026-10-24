# API (`core/apolo/api/`)

`main.py` sólo COMPONE: app, CORS, registro de errores (middleware, handler y
`/api/client-errors`), arranque/apagado, `include_router` y la UI; además es la superficie de
compatibilidad de los tests (alias de sesión y re-exports por IDENTIDAD). Las rutas viven en
`routers/`; estado de sesión y arranque, en `session.py`; autosave, `autosave.py`; WebSocket,
`ws.py`; payload de escena con sus cachés, revs y briefs, `scene.py`; lo que comparten los
endpoints, `common.py` (`_expand_ids`, `_not_found`, `_state_or_error`, materialize,
`JOBS`/`_sync_or_job`, `PHYSICS_LOCK`, cajetín); coreografía del FEA, `fea_runs.py`; física
dos-locks, `sims.py`; jobs, `jobs.py`; log de errores, `errorlog.py`; guardia del documento,
`guardia_documento.py`. El dominio que lee un
`Document` es de [services](../services/CLAUDE.md) ([plan](../../../docs/plans/partir-api-main.md)).
Lo transversal (`STATE_LOCK`, log, regenerate, Windows) está en el
[CLAUDE.md raíz](../../../CLAUDE.md); el cliente MCP, en [core/apolo](../CLAUDE.md).

## Routers (`routers/`): dónde va una ruta

| router | rutas |
|---|---|
| `core` | escena (completa, filtrada, resumen, delta), documento, salud, schemas, `/ws`, notas y chat del agente, croquis, script de prueba, expresiones, criterio de diseño |
| `commands` | comando, lote con contrato (sync o job), edición, borrado, búsqueda en el log, preview fantasma, jobs y sus archivos, variables, undo/redo, variantes |
| `features` | visibilidad, boceto-guía, color, material, vertical, topología, grupos, masa, medida, cercanía |
| `render` | `render.png` y `pick` (misma cámara) |
| `projects` | proyectos, revisiones, importar/exportar (STEP, STL, `.apolo`) |
| `deliverables` | catálogo, BOM y costeo, lista de corte, nesting, memoria de cálculo, cotización, manual |
| `validation` | `/api/checks`, `verify`, puerta de entrega y de publicación, requisitos, stack-up, tensores y funciones declarados |
| `motion` | cinemática, juntas, estudios de movimiento y su GIF, URDF/SDF |
| `assembly` | mates, restricciones de riel, uniones, estructura, auto-grupo, DOF, gravedad, drop-test, dinámica y la serie de la marcha |
| `fea` | FEA de pieza y de ensamblaje, resultados guardados, fringes |
| `drawings` | lámina simple, desplegado de chapa, juego de planos, plano por intención, fits, roscas |
| `electrico` | circuito y ERC del tablero; el tablero armado que lee el panel (`/api/tablero`) |
| `cosim` | escenarios de prueba, co-simulación y `test_plc` (job en `COSIM_JOBS`), simulaciones por partes, sesión en vivo vuelta escenario (las terminadas, en `sims.SESIONES_GRABADAS`) |
| `cosim_vivo` | `WS /api/cosim/vivo`: la sesión en vivo (protocolo en su docstring) |
| `video` | grabación del visor: sesión (con guion y plan), cuadros, foto, tarjetas, rótulos, fallo y cierre que codifica (`media/grabacion.py`); E/S pura |
| `video_guion` | el guion de montaje + su plan del documento activo para «Grabar video» (lee la escena bajo `STATE_LOCK`) |

- Una ruta nueva va al router de su tema con `@router.<método>`; `main` no gana rutas (sólo
  `include_router`).
- **Orden**: Starlette sirve la PRIMERA ruta que casa (y su `Allow` en un 405). Las rutas que
  pueden casar la misma URL viven en el MISMO router y se declaran en su orden (p. ej.
  `GET /api/fea/group/{name}` antes que `GET /api/fea/{feature_id}/fringe.png`, o
  `GET /api/fea/group/fringe.png` lo atendería la pieza). Los pares, los paths con varios
  métodos y su orden los fija `tests/test_rutas_api.py`: una ruta nueva que se solape lo pone
  rojo hasta que decidas su orden y la anotes ahí.
- Capas (gate `tests/test_api_sesion.py`, `CAPAS_API`): un router importa de `common`, `scene`,
  `session`, `sims`, `fea_runs` y `apolo.services`; nunca de `main`, de otro router ni de
  `autosave`/`ws`/`jobs`/`guardia_documento` (lo que necesite de ellos lo re-exporta `common`).
  Nadie importa `main`.
  Un test que llama una ruta directo la toma de `main` (re-export por IDENTIDAD, D4).

## Extensiones (`apolo/extensiones.py`)

- `main` llama `extensiones.cargar()` ANTES de `include_router` (con las rutas del núcleo: un
  prefijo de extensión no puede ser un tramo `/api/<x>/` suyo) e incluye los routers de las
  extensiones DESPUÉS de los del núcleo y antes de la UI. Nada se carga al importar `apolo` y la
  suite corre con `APOLO_EXTENSIONES=0` (lo fija `tests/conftest.py` antes de importar):
  `test_extensiones.py` la prende con `extensiones_aisladas` (`apolo.pruebas`). Todo lo que nombra
  una extensión lleva su prefijo (`x.algo`, tool `x_algo`, `/api/x/…`) y un registro mutable NUEVO
  que una extensión toque entra a `extensiones._registros()`, o su rechazo no se deshace.
  [plan](../../../docs/plans/nucleo-abierto-extensiones-privadas.md) (F1a)
- Lo que una extensión puede importar del núcleo está declarado en `extensiones_api.py`
  (`SUPERFICIE`, re-exportada perezosa; `MODULOS`): quitar o renombrar algo de ahí sube
  `CONTRATO_EXTENSIONES` (`tests/test_extensiones_api.py`). La `webui` nunca rechaza (sin build o
  segunda UI → `aviso`), y el MCP por stdio registra sólo las tools de lo que su API publica
  cargado en `GET /api/extensiones`: un rechazo nuevo va en `cargar()`, nunca sólo en un proceso.
  [plan](../../../docs/plans/nucleo-abierto-extensiones-privadas.md) (F1c)
- Una ruta de extensión toca el documento SÓLO por `fachada.py` (re-exportada en `SUPERFICIE`):
  `mutar_documento` = `_sync_or_job` + `_state_or_error`, `leer_documento` bajo `STATE_LOCK`,
  `leer_ext`/`poner_ext` (clave `ext`). Un cambio del embudo de mutación lo hereda sola; lo que
  le falte a una extensión se suma ahí, no se le abre `common`. (F1d)

## Estado de sesión (`session.S`)

- El documento activo, el almacén, el proyecto y la salud viven en UN objeto,
  `session.S` (`doc`, `store`, `project_id`, `autosave_error`, `startup_error`). **El código
  nuevo de la API lee y swapea `S.<campo>`, jamás un global** (ni `global` para cambiar de
  proyecto): con la API en varios módulos, un global re-exportado se copia por valor y el
  módulo movido leería el documento viejo. Gate: `tests/test_api_sesion.py`.
- `api.DOC`/`STORE`/`PROJECT_ID`/`AUTOSAVE_ERROR`/`STARTUP_ERROR` siguen existiendo para los
  tests como ALIAS de `S` (la clase del módulo `main` los vuelve propiedades: leer, asignar y
  `monkeypatch` van a `S`). Nunca `from apolo.api.main import DOC`: congela el valor.
  [plan](../../../docs/plans/partir-api-main.md) (D3)

## Mutaciones y su retorno

- Toda mutación pasa por `_state_or_error`: devuelve `affected_command_ids` (el MCP lista sólo
  esos sólidos) y suma `aviso_estructura` cuando hay ≥ `MIN_SOLIDOS_SUJECION` sólidos y 0
  grounds: alarma ambiental en CADA mutación, nunca en lecturas.
  [V6.9](../../../docs/plans/V6.9-puerta-de-entrega.md) Si lo afectado tiene un `fasten` por
  conjuntos, suma `uniones_expandidas` (sólo entonces; si no, byte-idéntico).
  [mcp-sin-friccion](../../../docs/plans/mcp-sin-friccion.md) (D4)
- `_state_or_error(fn, armar=…)`: `armar` reemplaza la escena completa por un payload LIVIANO,
  armado bajo el mismo lock (`POST /api/commands/remove?detail=diff`: comandos, piezas y uniones
  que se fueron + `total_solidos`, 8.2 MB → 284 B a 200 piezas); sin él, byte-idéntico.
  `con_dependientes` arrastra fasten/ground y membresías de grupo en 1 undo
  (`services/cirugia.py`). [cirugia-liviana](../../../docs/plans/cirugia-liviana.md)
  `POST /api/undo|redo?detail=diff` usa el mismo `armar` con el diff del paso
  (`services/paso.py`: la foto se toma DENTRO del lock, antes de mover la pila).
- **Guardia del documento** (`guardia_documento.py`): con `X-Apolo-Documento` (token por objeto
  `Document`, publicado en `GET /api/health` → `documento`) una mutación sobre otro documento da
  409 sin aplicar nada. La verifican DENTRO de su `STATE_LOCK` y antes de tocar nada
  `_state_or_error`, el job de `_sync_or_job` y, con `_verificar_documento()` de `common`, cada
  mutación FUERA del embudo: **una mutación nueva fuera del embudo la llama**. Sin cabecera, nada
  cambia. [chat-cliente-igual](../../../docs/plans/chat-cliente-igual.md) (D3)
- **Sólo lectura** (extensión ausente): `_verificar_documento` también da 409 con el aviso de
  `doc.solo_lectura` (no lo pasan los resultados de FEA: metadato que el disco no verá);
  `_flush_body` no escribe ese documento y restaurar sobre él, o una revisión así, da 409. Escena
  y briefing llevan `solo_lectura` sólo si hay; `GET /api/health`, siempre (None).
  [plan](../../../docs/plans/nucleo-abierto-extensiones-privadas.md) (F1b)
- `PUT /api/commands/{id}` REEMPLAZA los params por defecto (`merge=false`); con `merge=true` es
  PATCH superficial (un sub-objeto `position`/`rotation` se reemplaza entero). El MCP manda
  `merge=true`; la UI elige por caso ([ui](../../../ui/CLAUDE.md)).
- `edit_batch` = N ediciones en UN regenerate atómico y 1 undo. `GET /api/schemas/{type}` evita
  volcar el schema completo.
- `POST /api/undo|redo?pasos=N`: `pasos` es `int` llano (con `Query(ge=1)` FastAPI daría su 422
  y no el 400 con el texto del documento). El documento publica `undo_labels`/`redo_labels`.
  [deshacer-con-etiqueta](../../../docs/plans/deshacer-con-etiqueta.md)
- `_materialize_insert_project` muta `S.doc.attachments`: corre DENTRO del lambda de
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
  requisitos + `ficha` (qué falta y qué está asumido) + notas (últimas 20 + `notas_truncadas`; una
  nota se corrige o borra por NÚMERO, `PUT|DELETE /api/agent/notes/{nota}`, y una de > 2000
  caracteres se rechaza, no se recorta: F6 de [puerta-de-publicacion](../../../docs/plans/puerta-de-publicacion.md)) +
  salud + variantes.

## Jobs asíncronos (`jobs.py`)

- Ninguna mutación larga vive dentro de una request: los lotes (`POST`/`PATCH
  /api/commands/batch`), `POST /api/commands`, `PUT /api/commands/{id}`, `POST /api/variables`
  y `POST /api/commands/remove` con `?async=true` → `202 {job_id}` y el MISMO closure del endpoint corre en un worker
  (`_sync_or_job`). Sin `?async`, byte-idéntico (la UI no se entera): por eso una ruta que encola
  conserva su `-> dict` como `response_model=dict` (sin él FastAPI cambia de serializador: `1e-7`
  → `1e-07`). Un id inexistente da 404 ANTES de encolar.
  [sandbox-caliente](../../../docs/plans/sandbox-caliente.md)
- `JobStore`: cola FIFO con UN worker (`STATE_LOCK` serializa igual y el orden importa), retiene
  los 20 terminados, en memoria. `GET /api/jobs/{id}?wait_s=0..30` = long-poll.
- La co-simulación va en `COSIM_JOBS` (`_job_cosim`), NUNCA en `JOBS`: dura minutos y dejaría
  esperando a las mutaciones; `GET /api/jobs/{id}` mira las dos. Su closure toma sus locks (snapshot
  bajo `STATE_LOCK`, worker fuera) y guarda el resultado sólo si `S.doc` sigue siendo el del
  snapshot. [V8.3](../../../docs/plans/V8.3-prueba-virtual.md) (D11)
- `POST /api/puerta-publicacion` (`?async=true`) también va en `COSIM_JOBS`: gravedad y marcha
  bajo `PHYSICS_LOCK`, insumos bajo `STATE_LOCK` (`services/puerta_publicacion.py`), y 409 si la
  firma del modelo cambia entre las tomas: un veredicto no mezcla dos modelos.
  [puerta-de-publicacion](../../../docs/plans/puerta-de-publicacion.md) (F1)
- Los entregables en archivo que tardan (memoria, manual, juego de planos, plano por intención)
  van en `ENTREGABLES_JOBS`
  (`_job_entregable`, `?async=true`), tampoco en `JOBS`: un job guarda JSON, así que el PDF queda
  en `ARCHIVOS` (en memoria, retención de 20) y el resultado trae `archivo` = `GET
  /api/archivos/{clave}`. Revalidan el proyecto en su primera toma del lock (`_mismo_proyecto`:
  409). Un entregable nuevo de minutos sigue el patrón. [manual-rapido](../../../docs/plans/manual-rapido.md) (F2)
- Lock HOJA: el `_cv` del store jamás se sostiene llamando al closure (que toma `STATE_LOCK`)
  ni al aviso `al_cambiar_estado`; el worker corre `fn()` sin lock propio y escribe el resultado
  después. `jobs.py` no importa FastAPI (`_describe_error` duck-tipea `status_code`/`detail`).
- Al pasar a corriendo y al terminar, WS `{"type": "job", "job_id", "estado"}` (cableado en
  `common.py`); best-effort: un aviso que lanza se traga. [modo-visor](../../../docs/plans/modo-visor.md) (D10)
- Guardia de proyecto: el job captura `S.project_id` al encolar y lo revalida DENTRO del RLock que
  ejecuta el lote; si el proyecto activo cambió → 409 y no aplica. `restore_revision` conserva el
  id (el lote aplica sobre lo restaurado, como en sync).
- Un 404 de job tras un reload NO significa «no aplicó» (los jobs viven en memoria; el autosave
  ya guardó): verificar con get_scene/health, nunca reintentar a ciegas. El 404 lo dice.
  [V6.5e](../../../docs/plans/V6.5e-mcp-jobs-asincronos.md)

## Lecturas a escala

- Ninguna lectura de rutina vuelca la escena: < 10 KB por lectura a 1000 piezas.
  `GET /api/scene/summary` (resumen por GRUPO) es la entrada a un proyecto grande;
  `get_scene(ids|name|limit|offset)` pagina briefs sin mallas armados en el SERVIDOR
  (`_scene_filtered`/`_feature_brief`, en la forma única `apolo/brief.py::brief_pieza`) y declara
  `total_filtrado`/`truncado` (sin caps silenciosos). [V6.5](../../../docs/plans/V6.5-mcp-a-escala.md)
- `get_scene()` sin params = payload completo con mallas, byte-idéntico: lo usa el viewport.
- **Modo corto = parámetro opt-in; sin él, byte-idéntico (la UI no lo pide, el MCP sí, por
  defecto)**: `undo|redo?detail=diff`, `GET /api/connectivity?ids&kind&resumen=si|auto`,
  `soundness {resumen}`, `/api/checks {grupo, solo_fallas, resumen, interference_desde,
  excluir_declaradas}`, `assembly/declare
  {resumen}` (propuesta y aplicada; sin cuerpo, la escena de siempre). `/api/schemas` (vista
  agente) publica `x-catalogo` en vez de un enum de > 50 refs; la vista persona conserva el
  enum (desplegable de la UI); `/api/schemas/{type}` no repite la `description` en la raíz del
  schema y `declare` aplicada escribe `fasten` por conjuntos (D8, D12).
  [mcp-sin-friccion](../../../docs/plans/mcp-sin-friccion.md)
- `_expand_ids` acepta NOMBRES de grupo en isolate/highlight/fit (render, pick, drawing_spec,
  manual); por eso los nombres de grupo no admiten comas. Un subgrupo vale también por su último
  tramo («Rodillos» → «Transportador/Rodillos», `assembly/groups.resolve_group`); de varios
  grupos → 400 con los candidatos. Quien resuelva grupos por su cuenta usa el mismo resolvedor.
- Los lotes de apariencia y conexiones (`POST /api/features/material|color`,
  `/api/connections/remove`) validan TODO antes de tocar nada: un id malo → 404 con sugerencia y
  CERO efectos parciales; un solo autosave. Las conexiones dejan un undo; color y material,
  ninguno (son metadatos de manifest: no entran a la pila).
- `GET /api/commands` (find_commands): búsqueda superficial (1 nivel de dict) de los comandos que
  crearon o referencian un feature; sin filtros → 400.

## Deltas de escena

- `_geom_rev(fid, shape)` (`scene.py`) = revisión por IDENTIDAD del shape (el regen incremental la conserva en
  lo no re-ejecutado). `scene_payload(known=…)` manda `same: true` + metadatos volátiles
  (id/rev/name/color/visible/group/is_guide/acabado/albedo) de lo que el cliente ya tiene (`POST /api/scene/delta`).
  Un metadato nuevo que el viewport deba ver va también en la entrada `same`: no sube el rev.
- Zonas de acabado: la pieza de un componente con zonas lleva `zonas: [{acabado, albedo, desde,
  hasta}]` (triángulos de SU malla o de la de su definición; también en `same`); las cachés
  teselan con `componente` y `_sin_zonas` saca los rangos con nombre de la malla. Sin zonas,
  byte-idéntico (`tests/test_seta_payload.py`). [seta-de-emergencia](../../../docs/plans/seta-de-emergencia.md)
- `SCENE_EPOCH` (uuid por proceso): si el cliente trae otro, se manda el payload COMPLETO (tras un
  restart los revs renacen en 1 y colisionarían). Cliente: [ui](../../../ui/CLAUDE.md).
  [V6.2](../../../docs/plans/V6.2-rendimiento.md) · [V6.2e](../../../docs/plans/V6.2e-fixes-revision.md)

## Locks: el trabajo pesado sale de `STATE_LOCK`

- Bajo `STATE_LOCK` sólo se EXTRAE (OCCT → datos puros: teselado, cascos, XML MuJoCo, STEP); el
  proceso pesado corre fuera con su lock (`RENDER_LOCK`, `PHYSICS_LOCK`, `FEA_LOCK`). Un endpoint
  nuevo de render o simulación sigue el patrón. `export_stl` y el HLR de los planos siguen bajo
  el lock (OCCT); su isométrica sombreada, no ([drawing](../drawing/CLAUDE.md)).
- La serie de la marcha del visor (`GET|POST /api/physics/dynamics/serie`) se cachea EN MEMORIA
  (`sims.MARCHAS`, lock hoja) por firma (log + materiales) y escenario (la petición sin `fps`).
  Toda dinámica exitosa, también la tool `simulate`, deja su escenario como el último del
  proyecto: el GET lo re-simula si el documento cambió. Trae `cadenas` y `fajas` (F3): se extraen
  en la MISMA adquisición que `prepare_dynamics` y se arman fuera de los locks; si fallan, la marcha
  sale igual con un aviso. [visor-realista](../../../docs/plans/visor-realista.md) (F2, F3)
- **WebSocket que acepta acciones** (`WS /api/cosim/vivo`): chequea `Origin` ANTES de aceptar y
  exige el token del documento por query (`?documento=`: el navegador no pone cabeceras en un WS);
  una sesión por API (`SESIONES`). Todo lo que sale va por UNA cola y UNA tarea que envía; las
  tareas van en un task group de anyio y la limpieza del `finally` NO hace `await` (con la tarea
  cancelada no correría: el worker quedaba huérfano). [V8.4](../../../docs/plans/V8.4-maquina-viva-en-pantalla.md) (F1)
- La grabación del visor (`/api/video/grabacion…`) no toma `STATE_LOCK`: es E/S pura y su lock
  (`media/grabacion.py`) es HOJA. Las sesiones viven en memoria (un reinicio las pierde; los
  cuadros quedan en `data/grabaciones/`); el cierre codifica dentro de la request, y si falla los
  cuadros QUEDAN para volver a cerrar. El plan del guion lo arma quien abre (el CLI sobre su
  copia, `video_guion` para el botón): `video.py` nunca lee el documento (lo vigila
  `test_la_grabacion_es_e_s_pura_sin_el_documento`). [video-realista](../../../docs/plans/video-realista.md) (D4, D5)
- `POST /api/agent/chat` no toma `STATE_LOCK`: el chat es un cliente HTTP de esta misma API
  (`agent/chat.py`); cupo lleno → 429. Sin `APOLO_CHAT=1` (leído en cada petición) → 503 ANTES
  de tomar cupo o llamar al modelo, y `GET /api/health` → `chat: false` (la UI oculta el panel).
  Un test del chat lo prende con `monkeypatch.setenv`. [D19](../../../docs/plans/chat-cliente-igual.md)
- Un `StreamingResponse` que reserva algo (el cupo del chat) lo suelta CERRANDO su generador en
  `stream_response` (`routers/core.py::_SseDelTurno`): Starlette no lo cierra y, tras un corte
  del cliente, queda colgado de un ciclo de referencias hasta que pase el GC (medido con
  uvicorn real). [chat-cliente-igual](../../../docs/plans/chat-cliente-igual.md) (F5a)

## Autosave y arranque

- Vive en `autosave.py`; los routers lo toman de `common` y `main` re-exporta por IDENTIDAD lo
  que usan los tests. Los
  tiempos (`_AUTOSAVE_DEBOUNCE`/`_AUTOSAVE_CEILING`) se parchean en `apolo.api.autosave`: en
  `main` no existen (el programador no los leería). Para ESPIAR el autosave, parchea
  `api._autosave_sched.schedule` (el objeto compartido), nunca `api._autosave`: `common`,
  `fea_runs` y los routers llaman al `_autosave` de su propio módulo.
- `_autosave()` no escribe: marca sucio y arma un flush único (`_AutosaveScheduler`, debounce
  500 ms, techo 3 s). `_flush_body` toma bytes + `pack()` + `S.store`/`S.project_id` bajo `STATE_LOCK`
  (snapshot atómico) y escribe la SQLite FUERA.
- Orden ÚNICO de locks `_flush_lock → STATE_LOCK`, jamás al revés (deadlock switch ↔ Timer);
  `_flush_lock` se sostiene todo el flush, reintentos incluidos. Cambiar de proyecto =
  `_project_switch()` (flush del actual + swap atómico bajo ambos locks).
- Durable: reintentos `_AUTOSAVE_RETRIES`; agotados (también si falla la serialización) →
  `S.autosave_error` en el payload + WS `autosave_failed`. La caché de geometría va aparte,
  best-effort. Flush FORZOSO en shutdown/restore.
- Arranque: abre `APOLO_PROJECT=<id>` si está, si no el reciente; corrupto → carga tolerante; si
  ni así abre, o el pedido no existe → `S.startup_error` + doc vacío con `S.project_id = None`
  (no crea un «Sin título» que pise el reciente). `project/new` y `project/open`
  (upload) crean id PROPIO. [varias-maquinas](../../../docs/plans/varias-maquinas-a-la-vez.md) (D3)
- `GET /api/health` = `check_integrity` + suprimidos + `autosave_pending`/`autosave_failed` +
  `startup_error` + `documento` (el token de la guardia) + `chat` + `dwg` ({disponible, aviso}:
  una capacidad que un cliente lee ANTES de pedir; la publicación la cruza con
  `Entregable.requiere`) + `pid`/`puerto`/`proyecto` (de quién es, con varias APIs a la vez); no
  tiene tool MCP. [V6.1](../../../docs/plans/V6.1-robustez-industrial.md)
- **Varios procesos comparten la SQLite y `errors.log`**: la base va en WAL con
  `BUSY_TIMEOUT_S` = 30 (`projects.py`; 5 s daban `database is locked` con 5 procesos) y cada
  `_conn` CIERRA su conexión. Una entrada del log es UNA línea `pid=… puerto=…` anexada con
  `apolo/anexar.py` (append atómico del sistema): nunca un `logging.FileHandler` ni `open('a')`,
  que en Windows pierden líneas entre procesos. El puerto, de `apolo/identidad.py`
  (`APOLO_PORT` o el `--port` de uvicorn). [varias-maquinas](../../../docs/plans/varias-maquinas-a-la-vez.md) (F0)
- **Candado por proyecto** (`candado.py`, tabla `project_leases`): abrir, crear y restaurar
  toman el del proyecto y sueltan el que se deja (`cambio_a`/`tras_crear`, DENTRO de
  `_project_switch`); uno de otro proceso vivo → 409 «El proyecto 74 está abierto en el puerto
  8102 (pid 1234)», también al borrar. Un cambio de documento activo nuevo usa esos dos. Dueño
  `host:pid:puerto`, fijo por proceso (la suite reabre sin 409). Muerto = latido ≥ 30 s o, en
  esta máquina, pid inexistente (el `--reload` mata al worker sin shutdown). El latido (hilo
  daemon, 10 s) NO toma `STATE_LOCK`. `_flush_body` escribe sólo si `asegurar` lo deja (nunca
  roba uno ajeno, aunque venza); si no, `autosave_error`. Un almacén sin `tomar_candado` (los
  falsos de los tests) no usa candados. [varias-maquinas](../../../docs/plans/varias-maquinas-a-la-vez.md) (D4)

## Tests de la API

- Los tests no ejecutan el lifespan → no tocan `data/apolo.db`. Patrón:
  `api.DOC = Document("t"); TestClient(api.app)`; el arranque real vive en
  `session.initialize_store(db_path)` (`api.initialize_store`).
- `apolo/pruebas.py` (plugin de pytest que viaja en la wheel; `tests/conftest.py` lo carga con
  `pytest_plugins`, una extensión igual) devuelve `S` a como estaba y cancela el Timer del
  autosave al terminar cada test: un test no hereda el documento de otro. Fixtures con STORE:
  `_flush_autosave()` antes de leer disco.
- El mismo plugin (autouse, sesión) redirige `logs/errors.log` a tmp: sin él la tortura
  escribía errores FALSOS en el log que se lee al «revisa» (commit `3e935f4`).
- Ese conftest no alcanza a OTRO proceso: un test que levanta APIs reales (uvicorn, la flota de
  `tests/test_flota.py`) les pasa `APOLO_DB` y `APOLO_LOGS` (`paths.logs_dir()`) a tmp.

## Dominio en `services`, coreografía en la API

- Los mapas por pieza de los planos (fits, datum, GD&T, tolerancias), los datos de instalación,
  el stack-up, las aserciones, la puerta de entrega, las reglas de ingeniería y FEA y la
  preparación del FEA son de [services](../services/CLAUDE.md), con sus reglas; un 400/404 de
  dominio llega como `ServiceError` y `_http_error` (`fea_runs.py`) lo traduce con su texto
  EXACTO. Los endpoints INYECTAN `expand=_expand_ids` (toma `STATE_LOCK`, que services no puede
  nombrar). `main` re-exporta por IDENTIDAD los nombres viejos que usan los tests
  (`_piece_dim_tols`…) y deja envoltorios sobre el documento activo (`_fea_rules()`,
  `_suggest_ids(m)` en `main`; `_stackup_rules()` en `common`, porque la memoria también lo usa).
  El juego de planos en PDF y DWG toma sus kwargs de `sheet_set_maps(doc)`.
- **FEA** (`fea_runs.py`: `_fea_static_run`/`_fea_assembly_run`): la coreografía es de la API
  —(a) bajo `STATE_LOCK` la preparación de `services/fea_setup.py` + el tmp dir (lo crea y lo
  borra la API, también si la preparación falla) + el STEP; (b) solve FUERA del lock; (c)
  persistir—. `ids` acotado → hipótesis de ALCANCE; `nota` del analista → hipótesis. Persiste con
  `_persist_fea_if_same_project` (si se abrió otro proyecto durante el solve → `guardado: false` +
  `aviso`); el campo en memoria (`_LAST_FEA_FIELD`) vale sólo para su documento y su dueño
  (`_LAST_FEA_OWNER`) se parchea en `apolo.api.fea_runs`. Empotramiento, carga y convergencia:
  [services](../services/CLAUDE.md); malla y solver: [fea](../fea/CLAUDE.md).
- **Stack-up**: el `PUT /api/stackup` hace ROLLBACK si la cadena no evalúa (persistirla
  envenenaba GET y la memoria para siempre); la evaluación aislada por cadena es de
  [services](../services/CLAUDE.md). [V7.3](../../../docs/plans/V7.3-stackup-cadenas-cotas.md)
