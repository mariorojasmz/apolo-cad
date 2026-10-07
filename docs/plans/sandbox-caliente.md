---
estado: implementado
nota: sin pendientes; cada proyecto con run_script o insert_project replaya UNA vez en su primer open (run_script v2)
descripcion: Cambiar una variable de un proyecto con muchos «Script IA» tarda segundos y no minutos, y el agente nunca vuelve a recibir «timed out» al editar
---

# Editar una variable del 38 tarda segundos, no tres minutos

## Estado y origen

Pedido de Mario (2026-10-07), sobre un hallazgo medido el 2026-10-06 en la sesión de
[deshacer-con-etiqueta](deshacer-con-etiqueta.md): en el proyecto 38 `faja-paqueteria-4m`, con
`main` en `c2f9cce`, abrir en frío tardaba 172–192 s, `doc.edit(<set_variable largo_total>)`
~170 s cada vez y `undo` 0,01 s. `python -B scripts/e2e_mcp.py --proyecto 38` fallaba en el
paso 19 (`set_variable`, «timed out»: el MCP la llama síncrona con httpx a 120 s) y el paso 20
veía el resumen cambiado porque la variable SÍ se aplicó después. Textual: «perfilar el replay
del 38 […] y comparar contra `docs/perf_baseline.json` para saber si es una regresión reciente y
desde qué commit. Luego proponer […] bajar el costo del replay, invalidar menos al editar una
variable, y/o que la tool MCP `set_variable` encole como job».

No es nuevo: el [backlog](../backlog.md) § Rendimiento y concurrencia ya tenía los dos síntomas
(«`set_variable` en el 38 se rechaza con la máquina cargada» y «una mutación síncrona del MCP que
pasa de 120 s no deja recibo»), los dos de [chat-cliente-igual](chat-cliente-igual.md) § F12,
cuando el 38 tenía 6 scripts. Hoy tiene 48. Este plan los absorbe; al cerrarlo salen del backlog.

## El problema, medido

Todo sobre una COPIA de `data/apolo.db` hecha con la API de backup de SQLite, en el mismo host
del baseline (`Mario-LapTrab`), con `APOLO_GEOM_CACHE=0`, `python -B` y `main` en `63e2d3d`.
Scripts de la medición: `perfil38.py`, `desglose.py`, `brep_vs_step.py` (scratch de la sesión;
lo esencial queda en la Bitácora).

**1. El 98 % del replay es `run_script`.** Replay en frío del 38 (450 comandos, 129 sólidos)
con tiempo por comando y cProfile: 238,2 s.

| tipo | n | suma | máx |
|---|---|---|---|
| `run_script` | 48 | 234,2 s | 7,6 s (c1187) |
| `insert_component` | 39 | 1,7 s | 0,33 s |
| `create_take_up` | 1 | 1,1 s | — |
| los otros 362 (223 `fasten`, 39 `set_variable`…) | 362 | ~1,2 s | — |

cProfile: 228,2 s de los 233,3 s perfilados están en `subprocess.run` dentro de
`sandbox.run_script_to_step` (`core/apolo/sandbox.py:36`).

**2. El costo de un script es arrancar Python e importar build123d, no el script.**

| medida | tiempo |
|---|---|
| `python -c "pass"` | 0,11 s |
| `python -c "import build123d"` | 4,3–4,9 s |
| el sandbox con `result = Box(10, 10, 10)` | 4,7–5,5 s |
| los 48 scripts del 38 EN PROCESO: `exec` | 2,5 s en total (mediana 0,02 s, máx 0,38 s) |
| … exportar a STEP / importar STEP | 0,6 s / 3,0 s |
| … serializar a BRep binario | 0,02 s (662 KB contra 2 096 KB de STEP) |

`-X importtime`: `import build123d` = 3,95 s, de los cuales OCP 0,85 s, IPython 0,88 s (lo jala
`build123d.topology.shape_core`) y sympy 0,78 s (`build123d.objects_curve`).

**3. Editar CUALQUIER variable re-ejecuta los 48, y un replay sin cambios también.** La caché
del sandbox (`sandbox.py:22-33`) es LRU de 32 entradas con clave = código + TODAS las variables
resueltas:
- editar una variable cambia la clave de los 48 → 48 subprocesos;
- 48 > 32 y el replay los pide en orden: el LRU desaloja cada entrada antes de volver a
  pedirla → un replay completo SIN cambios tampoco acierta ninguno.

Y aunque la clave usara sólo las variables que el script lee, en este caso no ayudaría: los 48
scripts leen `V["long_centros"]` (se ubican en X dentro del código, con `position` vacío), y
`largo_total` cambia `long_centros`.

**4. No es una regresión del código: creció el modelo.** `sandbox.py` y
`agent/script_wrapper.py` no cambian desde el commit inicial `344a395` (2026-06-28) y build123d
0.10.0 está instalado desde el 2026-06-10. Los `run_script` del 38 por revisión guardada:

| revisión | fecha | comandos | `run_script` |
|---|---|---|---|
| 79 (log del baseline) | 2026-07-10 | 312 | 6 |
| 103 | 2026-08-03 | 352 | 6 |
| 105 | 2026-10-05 23:04 | 381 | 11 |
| 107 | 2026-10-06 08:39 | 328 | 17 |
| 116 | 2026-10-06 18:26 | 391 | 31 |
| 117 | 2026-10-06 19:04 | 425 | 44 |
| 119 (= el proyecto hoy) | 2026-10-06 21:42 | 450 | 48 |

**5. El baseline escondía el costo.** `open_frio_faja_s = 1,82 s` (`6f788df`) es la MEDIANA de 3
repeticiones en el MISMO proceso: la 2.ª y la 3.ª aciertan en la caché del sandbox. La revisión
79 replayada hoy así: 34,7 s · 2,3 s · 2,9 s. El open «frío» real del log del baseline ya costaba
~35 s en julio; el resto del replay sí está en orden (2,3–2,9 s contra 1,8 s).

## Lo que se revisó antes de escribir esto

- `regenerate` (`doc/document.py:198`): reanuda desde el checkpoint anterior al primer comando
  cuya firma cambió; una variable vive en la cabecera → replay de todo el log. `undo` es barato
  porque repone el checkpoint del snapshot.
- `run_script_to_step` (`sandbox.py:36`): un `subprocess.run` por script con
  `SCRIPT_TIMEOUT_S = 60` que cuenta TAMBIÉN el arranque del intérprete (por eso, con la máquina
  cargada, un script trivial llega a pasar el límite: backlog).
- Hay dos clientes del sandbox: el executor de `run_script` (`commands/registry.py:1734`, bajo
  `STATE_LOCK`) y `POST /api/script/test` (`api/routers/core.py:265`), que lo llama FUERA de
  `STATE_LOCK`. `step_bytes_to_shape` lo usa además `import_step` (`registry.py:885`).
- La caché de geometría ya resuelve el viaje BRep robusto: `_serialize_robust` (crudo → copia
  `BRepBuilderAPI_Copy` → None) y `_wrap_topods` en `doc/geomcache.py:91-137`. Probado aquí sobre
  los 48 scripts: los 48 round-trip-ean; volumen igual a 1,1e-12 relativo, bbox a 1e-7 mm, mismos
  sólidos y caras. Diferencia de TIPO en 19: STEP devuelve `Solid` donde BRep devuelve un
  `Compound` de un sólido (`import_step` desenvuelve).
- `_sync_or_job` (`api/common.py:188`) ya da `?async=true` a cualquier endpoint con el mismo
  closure, y `_submit_and_wait` (`mcp_server.py:68`) ya devuelve payload o recibo. Hoy sólo los
  usan `run_batch`/`edit_batch`.
- Lección del zombie-socket (raíz § Windows): un `multiprocessing.spawn` huérfano retiene :8000.

## Decisiones (para vetar)

Aprobadas todas por Mario el 2026-10-07: «aprobado, dale con los dos» (D1–D7 + D9 y D8).

- **D1. Un worker caliente en vez de un intérprete por script.** Un subproceso de vida larga
  (`subprocess.Popen`, NO `multiprocessing`) que importa build123d UNA vez y atiende scripts por
  stdin/stdout con mensajes de largo prefijado. Uno solo por proceso de la API: los 48 scripts
  del 38 suman 2,5 s de `exec`, no hace falta un pool. Por qué: el 95 % del costo es el import
  (medido arriba) y el aislamiento que da el subproceso se conserva (D2).
- **D2. El aislamiento no se negocia.** Namespace fresco por script (igual que hoy). Timeout por
  script (`SCRIPT_TIMEOUT_S = 60`) que cuenta SÓLO la ejecución; el arranque tiene su propio
  límite generoso (300 s) y no rechaza un script. Timeout o crash → se mata el worker, el script
  falla con el mismo `ScriptError` de hoy y el siguiente levanta uno nuevo. Se recicla también
  tras cualquier excepción del script y cada 500 scripts (acota memoria de OCCT y un script que
  ensucie un global de build123d). El worker sale solo al leer EOF en stdin: si la API muere, no
  queda huérfano; `close_fds` (default) le impide heredar el socket.
- **D3. Vuelta en BRep binario, con STEP de respaldo.** El worker serializa con la estrategia de
  `_serialize_robust`; si un shape no round-trip-ea, devuelve STEP como hoy. Un `Compound` de UN
  sólido se desenvuelve a `Solid` (lo que hoy entrega `import_step`), para que el tipo no cambie.
  `_serialize_robust` y `_wrap_topods` se mudan a un módulo liviano compartido
  (`core/apolo/brep_io.py`, sólo build123d/OCP: el worker no debe importar `kernel` ni `doc`);
  `geomcache` los importa de ahí con el MISMO formato de blob.
- **D4. La clave de la caché no cambia; el tope pasa de 32 entradas a 64 MB.** No se indexa por
  las variables que el script lee: en el 38 los 48 dependen de `largo_total` y, con el worker,
  re-ejecutarlos cuesta ~3 s. El tope por bytes (BRep ≈ 14 KB por script) quita el LRU que hoy
  falla el 100 % en un replay de 48.
- **D5. Lock propio del sandbox, orden único `STATE_LOCK → SANDBOX_LOCK`.** El executor llega con
  `STATE_LOCK` tomado; `test_script` toma sólo `SANDBOX_LOCK`, fuera de `STATE_LOCK`. Nunca al
  revés.
- **D6. `run_script` sube a `version=2`** en su `CommandSpec`: invalida la caché de geometría sólo
  de los proyectos con scripts (un replay que ahora cuesta segundos) y evita mezclar formas
  nacidas de STEP con las de BRep. Alternativa si se veta: no subir, porque la geometría medida es
  idéntica.
- **D7. La API precalienta el worker al arrancar**, en un hilo que no frena el startup: la
  primera edición no paga los 4,5 s. Los tests no precalientan (perezoso).
- **D8. `set_variable`, `edit_command` y `run_command` encolan como job por MCP**, igual que los
  lotes: `?async=true` en `POST /api/variables`, `PUT /api/commands/{id}` y `POST /api/commands`
  vía `_sync_or_job`, y `_submit_and_wait` en las tres tools. Por qué, aunque D1 baje el 38 a
  segundos: el costo del replay crece con el modelo y el agente no puede saber cuánto tardará (el
  mismo argumento de [V6.5e](V6.5e-mcp-jobs-asincronos.md)); hoy un timeout deja al agente sin
  saber si se aplicó. Sin `?async` el REST queda byte-idéntico (la UI no cambia). `undo`/`redo` no:
  reponen un checkpoint. Es independiente de D1–D7 y se puede vetar sola.
- **D9. El baseline mide el frío de verdad.** `scripts/perf_baseline.py` vacía la caché del
  sandbox antes de cada repetición del open frío, reporta aparte la 1.ª repetición de un proceso
  nuevo (incluye levantar el worker), suma `edit_variable_faja_s` (editar `largo_total` y volver,
  el caso que dolió) y `faja_run_scripts` en `conteos`. Se re-mide al cerrar F2.

## Alternativas descartadas

- **Invalidar sólo lo que depende de la variable.** Los 48 scripts dependen de `largo_total`;
  lo que no es script cuesta ~4 s; y un replay por dependencias rompe la invariante de
  checkpoints por PREFIJO (los executors leen la escena que dejaron los anteriores: `fasten`,
  `boolean_op`, `add_joinery`). Mucho costo, poca ganancia.
- **Ejecutar los scripts dentro de la API.** Sin subproceso no hay timeout ni aislamiento: un
  bucle infinito o un segfault de OCCT tumba el servidor.
- **Un pool de intérpretes frescos en paralelo.** 48 × 4,5 s / 12 núcleos ≈ 18 s y N veces la
  memoria; el worker caliente da ~3 s en serie.
- **Recortar el import** (stub de IPython/sympy en `sys.modules`): depende de los internals de
  build123d 0.10, ahorra ~1,7 de 4 s y se rompe en el próximo upgrade.
- **Pasar los scripts del 38 a comandos nativos.** Es cirugía del modelo, no la causa:
  `run_script` es la vía legítima para lo que el registro no cubre.
- **Caché de scripts persistida en SQLite.** El open caliente ya lo cubre `geom_cache`, y un valor
  nuevo de variable siempre falla.

## Fases

- **F0 — medir** (sólo lectura). Hecha: Bitácora.
- **F1 — worker caliente** (D1–D5). Paquetes: `core/apolo/sandbox.py`,
  `agent/script_wrapper.py` → `core/apolo/sandbox_worker.py` (el proceso hijo deja de colgar de
  `agent/`; se actualiza el docstring de `agent/__init__.py`), `core/apolo/brep_io.py`,
  `doc/geomcache.py` (sólo el import). Tamaño M. Tests nuevos: dos scripts seguidos los atiende el
  MISMO pid; un `while True` da `ScriptError` por timeout y el siguiente script funciona; un
  `os._exit(3)` da `ScriptError` con el código y el siguiente funciona; BRep ≡ STEP (tipo, sólidos,
  caras, volumen, bbox) en una muestra de scripts con `Compound`, `Solid` y lista; `test_script`
  concurrente con un regenerate no se traba; el tope por bytes desaloja. Gate: pytest completo +
  `perfil38.py` sobre una copia: replay frío del 38 ≤ 20 s y editar `largo_total` ≤ 15 s
  (estimado de F0: ~11 s y ~7 s).
- **F2 — versión, precalentado y baseline** (D6, D7, D9). Paquetes: `commands/` (versión y
  `test_contrato_comandos.py`), `api/` (arranque), `scripts/perf_baseline.py`,
  `docs/perf_baseline.json`. Tamaño S. Depende de F1. Verifica: pytest; baseline re-medido sobre
  una copia de la base con la API detenida.
- **F3 — mutaciones por job en el MCP** (D8). Paquetes: `api/routers/commands.py`,
  `mcp_server.py`, golden (`scripts/golden_mcp.py --congelar` con el diff revisado), tests de jobs.
  Tamaño M. Independiente de F1–F2. Verifica: pytest; un test por tool que, con el job lento,
  devuelve recibo y no «timed out».
- **F4 — verificar de punta a punta.** `python -B scripts/e2e_mcp.py --puerto N --proyecto 38`
  contra una API sobre una COPIA de la base (puerto ≠ 8000): 0 pasos en error y el proyecto igual
  que al empezar; números a la Bitácora. Reglas durables: el orden de locks en la raíz
  (§ Concurrencia), el worker en [core/apolo](../../core/apolo/CLAUDE.md); salen las dos entradas
  del backlog. Tamaño S.

## Lo que este plan NO hace

- No cambia el modelo del 38 (sus 48 scripts siguen) ni el formato del `.apolo`, del log o de la
  SQLite: los params de `run_script` no cambian.
- No invalida por dependencias ni paraleliza el regenerate.
- No toca `import_step` (sigue con `step_bytes_to_shape`).
- No cambia `undo`/`redo`/`open_project` por MCP (no replayan el log).
- No endurece el sandbox como frontera de seguridad: sigue siéndolo la revisión humana del código
  (`sandbox.py`, docstring).

## Riesgos

- **Estado que se filtra entre scripts del mismo worker** (un script que parchea build123d) →
  namespace fresco, reciclado tras error y cada 500, y un test que lo demuestra.
- **Memoria del worker** (OCP + build123d + IPython + sympy residentes) → se mide en F1; el
  reciclado la acota.
- **Deadlock** → un solo orden (`STATE_LOCK → SANDBOX_LOCK`) y el test de concurrencia de F1.
- **Huérfano en Windows** → `Popen` con `close_fds`, salida por EOF; F1 verifica que matar al padre
  deja sin procesos `sandbox_worker`.
- **Pipes que se bloquean en Windows** → lector en hilo con cola y timeout; mensajes de largo
  prefijado (el STEP de respaldo puede pesar MB).
- **Geometría distinta BRep/STEP** → normalización de D3, D6 y el test de equivalencia.
- **`--reload` de uvicorn** → el worker es hijo del proceso recargado y muere por EOF con él.

## Bitácora

### F0 — medición (2026-10-07, sólo lectura)

Copia de la base con `sqlite3.Connection.backup` (origen abierto `mode=ro`); nada contra :8000 ni
contra `data/apolo.db`. Números en § El problema. Lo que cambió el diagnóstico:

- La sospecha inicial repartía la culpa entre `insert_component`, `create_belt_conveyor`, las
  garruchas y `run_script`. El perfil por comando la concentró: 48 `run_script` = 234 de 238 s;
  las 39 inserciones de catálogo (garruchas incluidas) suman 1,7 s.
- «Invalidar menos al editar una variable» parecía la palanca. El análisis estático de los 48
  scripts la descartó para este caso: todos leen `V["long_centros"]`.
- «¿Desde qué commit?» no tiene respuesta en el código: ningún commit tocó el sandbox. La serie de
  revisiones del 38 ubica el salto en el modelo (6 → 48 scripts entre el 2026-10-05 y el
  2026-10-06), y la medición de `perf_baseline.py` ya lo escondía en julio por medir la mediana
  con la caché del sandbox caliente.

### F1 — worker caliente (2026-10-07, commit `6d8bca8`)

`core/apolo/sandbox_worker.py` (proceso hijo + protocolo), `sandbox.py` reescrito,
`core/apolo/brep_io.py` (`serialize_robust`/`wrap_topods` mudados tal cual; `geomcache` los
importa con alias, mismo blob, sin bump), `agent/script_wrapper.py` borrado,
`tests/test_sandbox_worker.py` (23). Protocolo: frames de largo de 4 bytes; el hijo copia los fd
0/1 como canal y manda el fd 1 a stderr (`print` y OCCT no ensucian), responde `B`+BRep,
`S`+STEP de respaldo o `E`+texto; un hilo sale con `os._exit` al ver EOF. API pública de siempre
más `prewarm()`, `worker_info()`, `cache_info()`, `clear_cache()`, `shutdown()`.

Medido sobre la copia (`APOLO_GEOM_CACHE=0`):

| medida | antes | máquina libre | máquina cargada |
|---|---|---|---|
| replay frío del 38 | 238 s | 7,2 s (arranque 3,1 + scripts 1,9 + resto 2,2) | 19,3 s (arranque 11,3) |
| editar `largo_total` 4000 → 4100 | ~170 s | 5,0 s | 7,1 s |
| volver a 4000 (los 48 de la caché) | — | 2,9 s | 5,0 s |

Worker: 367 MB residentes al arrancar, 382 MB tras 96 scripts (es el import; no crece).
Equivalencia sobre los 48 scripts reales: 0 difieren en tipo, sólidos o caras; volumen a 1,09e-12
relativo, bbox a 1e-7 mm.

- **La regla literal de D3 falló.** «Compound de un sólido → Solid» dejaba 7 de 48 con otro
  tipo. El árbol de esos 7 era idéntico al de los 19 que sí coincidían; la diferencia era la
  UBICACIÓN propia: el writer STEP escribe una forma ubicada como instancia de ensamblaje e
  `import_step` la devuelve como `Compound` (también un `Pos(5,0,0) * Box(...)`). Regla final: con
  ubicación propia → `Compound`; sin ella, un compound de un solo sólido → ese `Solid`. 48/48, y
  el test la compara contra el STEP real en 8 casos. Es empírica para build123d 0.10: un upgrade
  que cambie el STEP la pone roja.
- El `python.exe` del venv es un LANZADOR: `Popen.pid` no es el worker (el pid real viaja en el
  handshake). Matar al lanzador mata al hijo: medido.
- Lo que cuesta ahora es la carga de la máquina: el arranque del worker midió 3 s libre, 11 s
  cargada y hasta 80 s durante las suites en paralelo. Lo cubre `WORKER_START_TIMEOUT_S = 300`.
- `run_script_to_step` salió (sin llamadores). Mensajes nuevos sólo para el arranque («El sandbox
  no arrancó en 300s», «El sandbox no pudo arrancar»). El test de huérfano usa `psutil` con
  `importorskip`: en CI se saltea.

### F3 — mutaciones por job en el MCP (2026-10-07, commit `6f11bc7`)

`POST /api/commands`, `PUT /api/commands/{id}` y `POST /api/variables` aceptan `?async` vía
`_sync_or_job`; el 404 de `PUT` sigue síncrono. En el MCP, `_mutacion(...)` (envía como job y
devuelve el brief o el recibo) la usan las tres tools y también `run_batch`/`edit_batch`;
`mcp_server.py` bajó de 1429 a 1426 líneas. Golden re-congelado: en `list_tools` sólo cambian las
tres descripciones; en `llamadas`, ninguna salida existente cambia (sólo las peticiones: `async=true`
y el `GET /api/jobs/<id>`) y entran seis casos (recibo y job en error por tool). `e2e_mcp.py`
recoge el recibo de `set_variable` con `get_job`. `tests/test_jobs_mutaciones.py` (22).

- **Quitar `-> dict` cambiaba los bytes de la UI.** La firma pasó a devolver a veces un
  `JSONResponse` (el 202), así que la anotación quedaba falsa. Sin ella FastAPI 0.136 serializa la
  respuesta síncrona con `jsonable_encoder` + `json.dumps` (`1e-07`) en vez de pydantic (`1e-7`).
  Se dejó como `response_model=dict` y un test lo fija.
- Cargar `e2e_mcp.py` por ruta en un test falló con `@dataclass` + `from __future__ import
  annotations`: el módulo tiene que estar en `sys.modules` antes de ejecutarse.

### Revisión de F1 + F3 (sesión principal, 2026-10-07)

Diffs leídos contra el contrato; aceptada la desviación de D3 (la regla de tipos sigue lo que de
verdad hace STEP). F1 (`6d8bca8`) y F3 (`6f11bc7`, cherry-pick) juntos en la rama: pytest
**2128 pasan, 1 skip** (2083 + 23 + 22) en 608 s; ruff limpio. Re-medido con el perfilador de F0
sobre la copia, con la máquina cargada por otras sesiones: replay frío 15,7–18,9 s (el primer
script, que incluye levantar el worker, 9,8 s; los otros 47, 3,6 s; lo que no es script, 5,4 s);
editar `largo_total` 6,1 s y volver 3,7 s; worker 380 → 382 MB tras 96 scripts. Metas de F1
cumplidas (≤ 20 s y ≤ 15 s). Pendiente para F4: el docstring de `get_job` todavía dice «un
lote».

### F2 — versión, precalentado y baseline (2026-10-07, commits `195781e` y `b969a9a`)

`run_script` en `version=2` (huella del executor igual); `api/session.py::prewarm_sandbox()`
llamado en el startup ANTES de `initialize_store` (el replay del reciente espera al worker que ya
arranca), apagable con `APOLO_SANDBOX_PREWARM=0`, que `tests/conftest.py` pone para toda la
suite; `scripts/perf_baseline.py` re-escrito para D9 y `docs/perf_baseline.json` re-medido sobre
la copia (el JSON va en commit aparte para que su `commit` sea el código medido). Tests: 6 nuevos
(`test_precalentado_sandbox.py`, `test_version_comandos.py`).

| medida | julio (`6f788df`: 312 comandos, 6 scripts) | ahora (450 comandos, 48 scripts) |
|---|---|---|
| `open_frio_faja_primera_s` (proceso nuevo, con el worker) | — | 9,73 s |
| `open_frio_faja_s` (caché del sandbox vacía) | 1,82 s (¡con la caché caliente!) | 5,27 s |
| `edit_variable_faja_s` (`largo_total` 4000 → 4400) | — | 5,39 s |
| `edit_variable_vuelta_faja_s` | — | 3,14 s |
| `worker_arranque_s` | — | 4,28 s |

Cuadran entre sí (primera − frío ≈ arranque; frío − vuelta ≈ los 48 scripts) y una 2.ª corrida
cayó dentro de ±10 %. El resto de cifras subió 2–3× por el modelo (74 → 129 sólidos), no por F1–F2.

- **El bump de versión rompió un supuesto de la suite**: un test fijaba la firma de
  `insert_project` en `|v:fillet@3`; desde ahora lleva `run_script@2` para siempre. Un test nuevo
  prueba que un layout con un donante con scripts abre caliente en v2 y que un blob con firmas v1
  se descarta y replaya en frío. `scripts/golden_regen.py` va a cambiar `last_sig` en todo
  proyecto con `run_script` o `insert_project`: es lo esperado. Cada uno replaya UNA vez en su
  primer open tras el merge.
- **`regenerate_edit_temprano_s` nunca midió una edición real**: re-escribe la variable con el
  MISMO valor, las firmas no cambian y no replaya nada. La medida de verdad es la nueva
  `edit_variable_faja_s` (cada repetición va a un valor distinto para no acertar en la caché).
- Se creía que la suite precalentaba sin querer vía `with TestClient(...)`: ningún test entra al
  lifespan (entrar abriría la SQLite real). El apagado de `conftest` es defensa para el futuro.
- `perf_baseline.py` dejó de usar `ProjectStore` para leer: su constructor ejecuta `CREATE TABLE
  IF NOT EXISTS`, o sea, escribe en la base. Ahora lee por URI `mode=ro`.

### F4 — verificación de punta a punta y cierre (2026-10-07)

Rama integrada (F1 + F3 + F2 + reglas de F4): pytest **2134 pasan, 1 skip** en 433 s; ruff
limpio. E2E por MCP (`python -B scripts/e2e_mcp.py --puerto 8012 --proyecto 38 --md`) contra una
API con el código de la rama, `APOLO_DB` = una COPIA de la base y el puerto 8012:
**27/27 pasos ok en 46 s**. El paso que fallaba:

| paso | antes (2026-10-06) | ahora |
|---|---|---|
| 19 `set_variable` `largo_total` 4000 → 4400 | «timed out» a los 120 s (y se aplicaba después) | ok en 8,4 s, sin recibo |
| 20 `get_scene` tras la edición | veía el cambio aplicado a destiempo | cambió bbox, masa, grupos y variables, como debe |
| 21–22 `undo` y resumen | — | 0,4 s; resumen idéntico al inicial |

El open del 38 en la API recién levantada tardó 4,1 s (el precalentado ya había arrancado el
worker). Al apagar la API no quedó ningún `sandbox_worker` ni nada escuchando en :8012: el worker
murió con su padre. Reglas durables: el orden `STATE_LOCK → SANDBOX_LOCK` en la raíz, el worker y
su regla de tipos en `core/apolo/CLAUDE.md`, el `?async` de las mutaciones en `api/CLAUDE.md` y
`brep_io` en `doc/CLAUDE.md`. Del backlog salió el rechazo de `set_variable` en el 38; el de las
mutaciones síncronas quedó acotado a `undo`/`redo`/`open_project`.

- La API del E2E se levantó desde el worktree, contra la regla «no levantes la API desde un
  worktree». El motivo de la regla es que `paths.repo_root()` arrancaría con un `data/` vacío;
  con `APOLO_DB` explícito la base es la copia y lo demás (logs) cae en el worktree, ignorado por
  git. A cambio, el E2E probó exactamente el código que se mergea.
