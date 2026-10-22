---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: F0–F3 implementadas; F4 medida el 2026-10-21 en el escritorio por túnel SSH (3 en paralelo 90 s vs 213 s en serie, +0,5 GB, cero locks, 409 ok) — lo juzga Mario
descripcion: Varios agentes modelan máquinas distintas a la vez, cada una en su propio proceso de la API, sin pisarse ni perder guardados
---

# Cinco agentes modelan cinco máquinas a la vez sin pisarse

## Estado y origen

Mario preguntó (2026-10-20): «apolo cad trabaja una máquina a la vez, o sea que si quiero 5
proyectos al mismo tiempo, no lo soporta? ¿qué se tendría que cambiar?». Tras la investigación
eligió la opción A, «varios procesos de la API», y pidió este plan.

La regla vigente del CLAUDE.md raíz (§ Planes) es «una máquina a la vez»: la API tiene UN
documento activo y `open_project` lo cambia para todos. Hoy eso obliga a modelar en serie. La
ola 5 de [tanda-pos-piloto](tanda-pos-piloto.md) son 11 verificaciones por MCP, y la regla las
obliga a correr de a una.

## El problema / lo que hay hoy

- **Un documento por proceso.** El estado está en `S.doc` (`core/apolo/api/session.py:34`).
  Hay 288 referencias en 19 archivos de `core/apolo` y 328 en `tests/`. Lo cubre un único
  `STATE_LOCK` (`core/apolo/state.py`, 248 usos).
- **El arranque abre «el más reciente»** (`session.py:102`, `ProjectStore.most_recent_id`,
  `projects.py:184`). Dos procesos arrancados a la vez abren el MISMO proyecto.
- **La SQLite no está preparada para varios procesos.** `ProjectStore._conn`
  (`projects.py:57-60`) abre con `sqlite3.connect(self.path)`. Va sin `journal_mode=WAL` y con el
  `timeout` por defecto de 5 s. En el modo rollback, un escritor bloquea a todos los lectores, y
  el autosave escribe los bytes `.apolo` (≤ 23 KB en `data/`) más su `geom_cache` (hasta
  4,3 MB, media 1,1 MB; medido en F0: los 8,2 MB de [cirugia-liviana](cirugia-liviana.md) son el
  payload de escena con mallas, no lo que se guarda). Con varios procesos guardando a la vez, la
  espera pasa de esos 5 s y el autosave falla con `database is locked` (F0: 2 fallos con 5
  procesos; ninguno con 2): queda en `autosave_error` y el cambio se pierde si no se reintenta.
- **Nadie impide que dos procesos abran el mismo proyecto.** Cada uno guarda con
  `UPDATE projects … WHERE id=?` (`projects.py:87-94`): gana el último que escribe y el trabajo
  del otro desaparece sin aviso.
- **El MCP apunta a un puerto fijo.** `.mcp.json` fija `APOLO_URL=http://127.0.0.1:8000` y
  `mcp_server.py:25` lo lee una vez. El host lanza UN proceso MCP stdio por sesión, y sus
  subagentes (herramienta `Agent`) usan ESE mismo proceso: no basta con cambiar el puerto «para
  un subagente» (confirmado en F0, ver Bitácora).
- **Los puertos 8001–8007 ya están ocupados en la PC de Mario** (F0): los escuchan Docker
  (`com.docker.backend`) y WSL (`wslrelay`), y otras sesiones tienen MCP por SSE en
  `localhost:8001/8002/8005`. Una flota con puertos fijos chocaría.
- **Lo que ya existe y sirve:** `start-apolo.ps1 -Port` (`start-apolo.ps1:31-32`) ya levanta la
  API en otro puerto, y cada proceso sirve su propia UI. `paths.db_path()` acepta `APOLO_DB`. La
  guardia `X-Apolo-Documento` (`api/guardia_documento.py`) protege a un cliente contra un cambio
  de documento DENTRO de un proceso, pero no entre procesos.

## Lo que se revisó antes de escribir esto

- La alternativa de varios documentos en un solo proceso (ver Alternativas). Tocaría los 288
  usos de `S.doc`, la UI y cientos de tests, y no ganaría paralelismo: Python tiene el GIL y
  OCCT no es thread-safe, así que los regenerates de 5 documentos seguirían en fila dentro de
  un proceso. Con procesos separados, cada uno tiene su intérprete y su OCCT.
- Lo que cada proceso hace por su cuenta y no choca:
  - el worker del sandbox (`sandbox.py`, uno por proceso, con su `SANDBOX_LOCK`);
  - los locks de render, física y FEA (son de proceso);
  - el WebSocket (cada UI se conecta a su puerto).
- Lo que comparten de verdad:
  - la SQLite (`projects`, `revisions`, `geom_cache`);
  - `logs/errors.log` (`api/errorlog.py:17`);
  - las salidas en `data/` (publicaciones, renders, exportaciones). F0 lo inventaría.

## Decisiones (para vetar)

- **D1. Un proceso de la API por máquina abierta («flota»).** El código del documento único no
  cambia: `S.doc` sigue siendo uno por proceso. Por qué: es el cambio más chico que da
  paralelismo real (un núcleo por máquina) y no toca la UI ni el MCP.
- **D2. SQLite en WAL con `busy_timeout`.** `_conn` fija `PRAGMA journal_mode=WAL` (persiste en el
  archivo; basta con hacerlo una vez en `__init__`) y `sqlite3.connect(…, timeout=30)`. Por qué:
  en WAL los lectores no esperan al escritor, y los escritores esperan en fila en vez de
  fallar. WAL es compatible con una base vieja; deja `apolo.db-wal` y `apolo.db-shm` al lado
  (en `data/`, ya gitignorado). Sólo sirve en disco local, no en una carpeta de red.
- **D3. `APOLO_PROJECT=<id>` elige qué abre el arranque.** Si está, `initialize_store` abre ese
  proyecto en vez del reciente. Si no existe, deja `startup_error` y un documento vacío con
  `project_id=None`, como el caso del reciente corrupto (`session.py:89-114`). Nunca crea un
  «Sin título». Por qué: sin esto, los 5 procesos abren el mismo proyecto.
- **D4. Candado por proyecto en la base.** Va en una tabla nueva:
  `project_leases(project_id PRIMARY KEY, dueno TEXT, latido_at TEXT)`, creada con
  `CREATE TABLE IF NOT EXISTS`, así que una base vieja sigue sirviendo. El dueño es
  `host:pid:puerto`.
  - Abrir, crear o restaurar un proyecto toma su candado. Cambiar de proyecto suelta el
    anterior, y el shutdown lo suelta también.
  - Si el candado es de otro proceso con un latido de menos de 30 s, abrir da **409** con el
    mensaje «El proyecto 74 está abierto en el puerto 8002 (pid 1234)».
  - Si el latido tiene 30 s o más, el dueño murió y el candado se toma.
  - Cada proceso late cada 10 s, desde un hilo daemon.
  - El autosave verifica que el candado siga siendo suyo antes de escribir. Si lo perdió, no
    escribe y deja `autosave_error`.

  Por qué: es la única forma de que «el último que guarda gana» no borre trabajo en silencio.
  También vale para el `:8000` de siempre.
- **D5. Cada modelador es una sesión `claude -p` propia, con su `--mcp-config`.** Un script
  `scripts/flota.py` hace tres cosas:
  1. levanta N procesos de la API en N puertos LIBRES desde una base (por defecto `:8100`,
     `--puerto-base` la cambia), saltando los que ya escuchan, cada uno con su `APOLO_PROJECT`,
     su `APOLO_PORT` y sin `--reload` (corregido en F0: `:8001…:8007` están tomados por
     Docker/WSL en la PC de Mario);
  2. verifica que el dueño real de cada puerto sea el pid que lanzó (la trampa del
     zombie-socket, raíz § Windows);
  3. escribe `data/flota/mcp-<puerto>.json` con su `APOLO_URL`.

  Tiene `arrancar`, `estado` y `parar`. El orquestador lanza a cada modelador con
  `claude -p --mcp-config data/flota/mcp-8101.json --strict-mcp-config`. Por qué: los
  subagentes de una sesión comparten su proceso MCP, así que la separación tiene que estar en
  el proceso de la sesión, no en el subagente.
- **D6. `:8000` no cambia.** Sigue siendo la sesión de Mario (UI + MCP por defecto); la flota usa
  los puertos libres desde `:8100` (D5). Mario puede abrir `http://127.0.0.1:8101` para ver en
  vivo la máquina del agente 2.
- **D7. Identidad visible.** `GET /api/health` agrega `pid`, `puerto` y `proyecto`
  (`{id, nombre}`), y cada línea de `errors.log` lleva `pid` y `puerto`. El puerto sale de
  `APOLO_PORT` (lo fijan `apolo` y la flota) o del `--port` de la línea de comandos de uvicorn;
  si no se sabe, `/api/health` usa el de la petición. Por qué: con 5 procesos escribiendo el
  mismo log, el flujo «revisa» necesita saber de quién es cada error. El log sigue siendo un
  archivo; cada entrada es UNA escritura de una línea con un append ATÓMICO del sistema: en
  Windows, un handle abierto sólo con `FILE_APPEND_DATA`; en POSIX, `O_APPEND`. Corregido en
  F0: «abrir en `'a'` y escribir» NO basta en Windows (el CRT emula el append con seek + write):
  con 5 procesos × 3000 líneas se perdió el 13 % (el `FileHandler` de hoy, el 27 %).
- **D8. Tope de la flota medido, no supuesto.** `flota.py arrancar` rechaza levantar más procesos
  que `min(núcleos lógicos / 2, RAM libre / RSS medido en F0)`, salvo con `--forzar`. Por qué:
  el costo real de un proceso más es la RAM (intérprete + OCCT + build123d + worker del
  sandbox, por duplicado), y se conoce sólo midiendo. F0: ~0,8 GB en reposo y ~0,9 GB con el
  74 abierto (pico 893 MB); en la PC de Mario (12 núcleos lógicos, 15,7 GB, 4,5 GB libres al
  medir) el tope da `min(6, 5) = 5`.
- **D9. La regla «una máquina a la vez» del CLAUDE.md raíz se reescribe en F3**, no antes: «una
  máquina por proceso; varias, con `scripts/flota.py`». Hasta que F3 mergee, la regla vieja
  rige.

## Alternativas descartadas

- **Varios documentos en un solo proceso.** `S.doc` pasaría a ser un diccionario por proyecto,
  cada request diría su proyecto, y habría un lock, un WebSocket y un autosave por documento.
  Usa menos RAM, porque las librerías se cargan una vez. Pero toca `api`, `mcp`, `ui` y cientos
  de tests, y no paraleliza: con el GIL y OCCT, que no es thread-safe, los regenerates siguen
  en fila. Sólo valdría para una UI con pestañas de proyectos, que nadie pidió.
- **N entradas `apolo-cad-1…5` en `.mcp.json`.** Pondría 83 × 5 = 415 tools en el orquestador,
  y cada prompt tendría que nombrar su servidor. Además, un subagente podría llamar al
  servidor de otro.
- **Una tool MCP `usar_puerto(n)`.** Los subagentes comparten el proceso MCP: el cambio de
  puerto de uno movería a todos.
- **Una SQLite por proceso (`APOLO_DB` distinta).** Evita los bloqueos, pero rompe
  `insert_project` (que lee otro proyecto de la misma base) y deja proyectos repartidos en
  varios archivos.

## Fases

- **F0 (S, sólo lectura + scratchpad)**: medir antes de tocar nada.
  1. El RSS de un proceso de la API en reposo, con el piloto 74 abierto y durante un
     regenerate completo, contando el worker del sandbox.
  2. El CPU y el tiempo de ese regenerate.
  3. Reproducir `database is locked` con dos procesos que guardan en bucle sobre una COPIA de
     `data/apolo.db` (script en el scratchpad).
  4. Inventariar los archivos de nombre fijo que la API escribe en `data/` y `logs/`.
  5. Confirmar si dos subagentes de una sesión comparten el proceso MCP: comparar el pid del
     proceso `apolo.mcp_server` visto desde cada uno.

  Si algo contradice este plan, se corrige el plan antes de F1.
- **F1 (S, `projects` + `api/session` + `api/errorlog`)**: D2, D3 y D7. Tests:
  - dos procesos (`multiprocessing`) guardan 200 veces el mismo archivo sin un solo `locked`;
  - `APOLO_PROJECT` abre el pedido;
  - un id inexistente deja `startup_error` sin crear nada;
  - `/api/health` trae pid, puerto y proyecto;
  - varios procesos anexan al mismo `errors.log` sin perder ni mezclar una línea (agregado en
    F0).
  Depende de F0.
- **F2 (M, `projects` + `api`)**: D4. Tests:
  - abrir un proyecto con un candado vivo de otro dueño da 409 con el mensaje;
  - un candado con latido viejo se toma;
  - cambiar de proyecto suelta el anterior;
  - un autosave sin candado no escribe y deja `autosave_error`;
  - el `:8000` de siempre sigue abriendo y guardando igual.
  Golden: los proyectos de `data/` abren igual. Depende de F1.
- **F3 (S, `scripts` + `start-apolo.ps1` + CLAUDE.md raíz)**: D5, D6, D8 y D9. Tests del script:
  - arranca 2 procesos en puertos libres con proyectos de una copia de la base;
  - `estado` los ve;
  - `parar` los mata y suelta sus candados;
  - el tope de D8 rechaza un N excesivo.
  Depende de F2.
- **F4 (S, verificación)**: tres modeladores `claude -p` a la vez, cada uno sobre una COPIA de un
  proyecto de referencia (38, 28 y 72), con una tarea chica y la misma para los tres. Se mide:
  - el tiempo total contra los mismos tres en serie;
  - el RSS pico de la máquina;
  - cero `database is locked` en `errors.log`;
  - que abrir desde `:8000` un proyecto tomado por la flota dé el 409.
  Lo juzga Mario.

## Lo que este plan NO hace

- No permite que dos agentes editen la MISMA máquina a la vez: el candado de D4 lo impide.
- No es multiusuario ni remoto: todo sigue en `127.0.0.1` y en la misma PC.
- No hace una UI con pestañas de proyectos.
- No cambia el contrato del MCP ni de ningún comando.

## Riesgos

- **RAM**: cada proceso duplica intérprete, OCCT y su worker del sandbox. Mitigación: el tope
  de D8 con el RSS medido en F0.
- **Un candado huérfano tras un crash** bloquea el proyecto. Mitigación: el latido vence a
  los 30 s y el candado se toma; `flota.py parar` suelta los suyos.
- **WAL en una carpeta sincronizada o de red** (OneDrive, SMB) se corrompe. Mitigación: la base
  vive en `data/` local o en `APOLO_HOME` (`~/.apolo`); el arranque avisa si la ruta es de red.
- **Un `.py` editado con la flota arriba**: la flota va sin `--reload`, así que cada proceso
  sirve el código con que arrancó. Mitigación: `flota.py parar` + `arrancar` tras un merge,
  igual que la regla de reiniciar la API.
- **Costo de tokens**: cinco sesiones `claude -p` son cinco contextos frescos. Es lo buscado
  (raíz § Planes: modelar dentro de una sesión larga cuesta más); el orquestador sólo lee sus
  reportes.

## Bitácora

### F0 — medición (2026-10-20)

Todo sobre COPIAS de `data/apolo.db` en el scratchpad (`APOLO_DB`), con APIs de prueba en
`:8111` (muertas al terminar; `Get-NetTCPConnection` sin nada escuchando) y el código del
worktree (`PYTHONPATH`, `-B`). `:8000` y la base real no se tocaron.

1. **RSS de un proceso de la API** (árbol completo con `psutil`: el `python.exe` del venv es un
   lanzador que arranca el intérprete real, y el worker del sandbox va igual):

   | momento | API | worker del sandbox | lanzadores | árbol |
   |---|---|---|---|---|
   | reposo (doc vacío, sandbox precalentado) | 409 MB | 366 MB | 2 × 4 MB | 783 MB |
   | tras abrir el 74 (frío) | 505 MB | 366 MB | 8 MB | 879 MB |
   | tras abrir el 74 (caliente) | 515 MB | 366 MB | 8 MB | 890 MB |
   | pico durante el open | | | | 893 MB |

   El worker del sandbox es casi la mitad del costo y no crece con el proyecto (el 74 no tiene
   scripts). Con la caché de geometría apagada, el proceso suelto mide 383 MB tras importar y
   430 MB de pico regenerando.
2. **CPU y tiempo del regenerate del 74** (201 sólidos, 341 comandos):
   - regenerate puro en proceso, sin caché: 5,5 s de pared y 9,4 s de CPU el primero (OCCT usa
     más de un núcleo), 2,4 s / 3,1 s el segundo (cachés de proceso calientes);
   - `POST /api/projects/74/open` completo por HTTP: 43,5 s de pared y 43,7 s de CPU en frío
     (puebla la `geom_cache`), 17,9 s / 17,9 s en caliente. El payload es de 8 MB con mallas: lo
     que domina el open no es el regenerate sino armar la escena teselada. No es de este plan.
3. **`database is locked`**: script `repro_locked.py` (scratchpad), cada vuelta = lo que hace un
   autosave (UPDATE de `projects` con 20 KB + INSERT OR REPLACE de `geom_cache` con 4 MB) más dos
   lecturas de otro proceso.

   | `_conn` | procesos × vueltas | `locked` | peor operación |
   |---|---|---|---|
   | hoy (rollback, 5 s) | 2 × 200 | 0 | 2,1 s |
   | hoy (rollback, 5 s) | 5 × 100 | **2** (los dos en `save_raw`) | 8,6 s |
   | D2 (WAL, 30 s) | 2 × 200 | 0 | 7,3 s |
   | D2 (WAL, 30 s) | 5 × 100 | 0 | 3,7 s |

   Se reproduce con la flota de 5, no con 2. En WAL una espera llegó a 7,3 s: el `timeout=30`
   hace falta, WAL solo con 5 s no bastaría. El `-wal`/`-shm` desaparece al cerrar la última
   conexión.
4. **Archivos de nombre fijo** que escribe la API: sólo `logs/errors.log` (todos los procesos al
   mismo archivo) y `data/apolo.db` (más `-wal`/`-shm` con D2). Lo demás no choca:
   `data/grabaciones/<uuid>`, temporales con `mkdtemp`/`mkstemp` (sandbox, FEA, DWG, STEP/STL),
   exportaciones y renders sólo a la ruta que pasa el cliente, y `data/publicaciones/<slug>/<v>`
   por máquina (dos procesos sólo chocarían en la misma máquina, que D4 impide).
   `logs/uvicorn-restart*.log` no los escribe la API. **El log sí pierde líneas**
   (`log_concurrente.py`, 5 procesos × 3000 líneas de 300 B): el `FileHandler` de hoy dejó
   10 976 de 15 000 (27 % perdido), abrir en `'a'` y escribir 13 102 (13 %), un handle con
   `FILE_APPEND_DATA` 15 000 sanas. → D7 corregido.
5. **¿Comparten el proceso MCP los subagentes?** Sí. El árbol de procesos lo muestra sin tocar
   `:8000`: la sesión que lanzó esta fase (`claude.exe` pid 496, arrancada 16:14:57) tiene UN
   `python -m apolo.mcp_server` (2636 → 26796, arrancado 16:14:59), y este subagente corre DENTRO
   de ese `claude.exe` (su shell cuelga de 496) con las tools `apolo-cad` disponibles y sin
   proceso MCP propio. Ninguna otra sesión tiene uno. Comparar el pid «visto desde cada
   subagente» habría exigido llamar una tool que habla con `:8000`; no hizo falta.
6. **Hallazgo que corrige D5/D6**: `:8001…:8007` ya escuchan en la PC de Mario (Docker y WSL),
   y otras sesiones usan `localhost:8001/8002/8005` para sus MCP por SSE. La flota elige
   puertos LIBRES desde `:8100`.

Correcciones al contrato antes de F1: el tamaño de lo que guarda el autosave (§ El problema),
los puertos de D5/D6, el append atómico de D7 y su test en F1, y los números de D8.

### F1 — WAL, `APOLO_PROJECT` e identidad (2026-10-20)

- **D2** (`core/apolo/projects.py`): `__init__` pone `PRAGMA journal_mode=WAL` una vez y guarda
  el modo resultante en `journal_mode`; si no quedó en WAL (carpeta de red), el arranque lo
  anota en `errors.log`. `_conn` pasó a ser un context manager: `timeout=BUSY_TIMEOUT_S` (30 s),
  transacción y **cierre** de la conexión. Antes se cerraba recién en el GC (lo sufría
  `scripts/perf_baseline.py` con su `ignore_cleanup_errors`); con WAL, una conexión viva retiene
  el `-wal`. Nuevo `exists(id)`.
- **D3** (`api/session.py`): `APOLO_PROJECT` manda sobre el reciente. Si no es número o no
  existe, `_fallo_de_arranque` deja `startup_error`, doc vacío y `project_id=None`, sin crear
  nada; en una base vacía tampoco crea el «Sin título». El mensaje del reciente corrupto no
  cambió.
- **D7**: `apolo/identidad.py` (pid; puerto de `APOLO_PORT` o del `--port` de uvicorn, con 8000
  si uvicorn no trae `--port`) y `apolo/anexar.py` (append atómico: `FILE_APPEND_DATA` por
  ctypes en Windows, `O_APPEND` en POSIX; los saltos de línea se escapan como `\n`).
  `errorlog.py` dejó `logging`: cada entrada es `fecha | pid=… puerto=… | origen | mensaje |
  json`. `GET /api/health` suma `pid`, `puerto` (si el proceso no lo sabe, el de la petición) y
  `proyecto` = `{id, nombre}`; `project_id` sigue. `apolo` (cli) fija `APOLO_PORT`;
  `start-apolo.ps1` no hizo falta tocarlo (pasa `--port`).
- **Tests**: `tests/test_sqlite_varios_procesos.py` (dos procesos × 200 guardados del mismo
  proyecto sin un `locked`, ~30 s, casi todo el import de los hijos; WAL + busy_timeout; base
  vieja en rollback que pasa a WAL; un lector no espera a una transacción EXCLUSIVE abierta;
  ninguna conexión queda viva), `tests/test_arranque_e_identidad.py` (APOLO_PROJECT pedido,
  inexistente, en base vacía, no numérico; health con pid, puerto y proyecto; el puerto desde
  la línea de comandos; pid y puerto en cada línea del log) y `tests/test_errorlog.py` (4
  procesos × 1500 líneas sin perder ni mezclar una). `conftest` ya no toca handlers de
  `logging`.
- **En vivo**, sobre una copia y en `:8111`/`:8112` (muertas al terminar): con
  `APOLO_PROJECT=74` el health dio `{pid, puerto: 8111, proyecto: {id: 74, nombre:
  "transportador-rodillos-cadena-2m"}}` y 201 sólidos, y el pid es del árbol lanzado; con 999,
  `ok: false`, `startup_error` y la copia siguió con sus 30 proyectos. La copia quedó en WAL.

### F2 — candado por proyecto (2026-10-20)

- **Almacén** (`core/apolo/projects.py`): tabla `project_leases` con `CREATE TABLE IF NOT
  EXISTS` (una base vieja la gana sola) y `latido_at` en UTC de ancho fijo, comparado como texto
  en SQL. Cada operación es UNA sentencia condicional en su transacción (upsert con `WHERE`, o
  `UPDATE … WHERE dueno=?`): dos procesos no ganan el mismo candado. `tomar_candado` (libre, mío
  o latido ≥ 30 s), `asegurar_candado` (el del autosave: mío o libre, **nunca** uno ajeno aunque
  venza: si otro lo tuvo, éste lo perdió), `robar_candado` (compare-and-swap), `latir`,
  `soltar`, `candado`, `candado_vivo_ajeno`. `delete` borra el candado del proyecto.
- **API** (`core/apolo/api/candado.py`, capa nueva sobre `errorlog`; los routers lo toman de
  `common`): dueño `host:pid:puerto` fijado UNA vez por proceso (recalcula sólo si cambia el
  pid), así la suite, con cientos de almacenes y TestClient en un proceso, reabre sin 409.
  `cambio_a` envuelve la carga y el swap DENTRO de `_project_switch` (open por id y restore):
  toma antes de cargar, suelta el nuevo si la carga lanza y el anterior si sale bien;
  `tras_crear` para crear, `project/new` y `project/open` (upload). `initialize_store` toma el
  del que abre; tomado por otro vivo → el mismo fallo de arranque de D3 con el mensaje. El
  shutdown para el latido y suelta. `_flush_body` llama `asegurar` dentro de cada reintento,
  justo antes de `save_raw`; si es ajeno no escribe, deja `autosave_error` («No se guardó: este
  proceso perdió el candado…») y avisa por WS. El latido (hilo daemon cada 10 s, lo arranca el
  `startup` de `main`) **no toma `STATE_LOCK`**: un regenerate de 40 s dejaría vencer el candado.
- **Decisiones fuera de la letra del contrato**:
  1. *Pid muerto en la misma máquina = dueño muerto*, aunque su latido sea fresco
     (`OpenProcess` + `GetExitCodeProcess` en Windows; `os.kill(pid, 0)` en POSIX, que en
     Windows mandaría un CTRL_C). Sin esto el `:8000` con `--reload` se rompía: el reloader mata
     al worker con `TerminateProcess`, sin shutdown, y el nuevo (otro pid) encontraba el candado
     del muerto con latido fresco → arranque sin proyecto. Un pid reciclado sólo cuesta esperar
     los 30 s.
  2. *Borrar* un proyecto con candado vivo de otro proceso da el mismo 409: su autosave haría
     `UPDATE` sobre una fila que ya no existe y perdería el trabajo sin aviso.
  3. *Un candado ausente lo toma el autosave* (`asegurar`): los tests fijan `PROJECT_ID` sin
     abrir por el endpoint, y en un proceso real con latido no ocurre.
  4. *Un almacén sin `tomar_candado`* (los falsos de la tortura y de `insert_project`) no usa
     candados: todo no-op, escribe como siempre.
- **Tests** (`tests/test_candado_proyecto.py`, 17): la tabla en una base vieja; las
  operaciones del almacén; borrar suelta; dueño fijo por proceso; el texto del mensaje; 409 con
  el mensaje exacto y nada cambia; latido de 30 s se toma; pid muerto de esta máquina se toma;
  cambiar de proyecto (y `project/new`) suelta el anterior; un open que falla no deja candado ni
  suelta el actual; restaurar una revisión de un proyecto ajeno → 409; borrar uno ajeno → 409;
  el autosave sin candado no escribe y deja `autosave_error` (y health lo publica); el latido
  renueva; el `:8000` de siempre abre, guarda y re-arranca sin 409; arranque con el proyecto
  tomado → `startup_error`; **dos procesos reales**: un hijo abre A con `initialize_store` y
  late, éste recibe el 409 con el pid y el puerto del hijo, B abre, y al matar al hijo sin
  soltar A se toma enseguida (~20 s, casi todo el import del hijo). Ojo medido: el `python.exe`
  de un venv en Windows es un lanzador con OTRO pid; el pid que vale es el que informa el hijo.
- **Golden**: los 30 proyectos de una COPIA de `data/apolo.db` abiertos por
  `POST /api/projects/{id}/open`, uno tras otro, con el código de `main` y con el de F2 (cada uno
  sobre su copia): los 30 dan 200 con los mismos features (1857), el mismo log y los mismos
  suprimidos. Al terminar, sólo el último abierto conserva candado: cada cambio soltó el anterior.
- **En vivo**, sobre otra copia, dos uvicorn reales en `:8100` (A, `APOLO_PROJECT=74`) y `:8101`
  (B, 38), muertos al terminar (`Get-NetTCPConnection` sin nada en 8100–8200): B abre 74 → 409
  «El proyecto 74 está abierto en el puerto 8100 (pid 30196)», con el pid real de A; B abre 28 →
  200 y suelta el 38; el latido de A avanza; un `set_variable` en A llega al disco sin
  `autosave_failed`; A muerto con `taskkill /F` (sin shutdown) → B abre 74 al instante (pid
  muerto). Un tercero SIN `APOLO_PROJECT` (como el `:8000`) abre el reciente (74, cuyo dueño B
  también murió a la fuerza) y guarda.

### F3 — `scripts/flota.py` (2026-10-20)

- **`scripts/flota.py`** (`arrancar`, `estado`, `parar`; `--dir` cambia `data/flota/`) y
  **`scripts/flota_so.py`** (lo que se le pregunta al sistema). Stdlib pura: `psutil` no es
  dependencia de Apolo (en el venv llega por `ipython`, en el CI no), y **no importa `apolo`**:
  `import apolo.projects` tardó 19,5 s en frío. Los candados se leen y borran con SQL directo
  sobre `project_leases`; los tests lo cruzan con `ProjectStore`.
  - *arrancar*: valida el tope, que los ids existan y no se repitan; elige puertos LIBRES desde
    `--puerto-base` (8100): ni escuchados (`netstat -ano` por la dirección remota `0.0.0.0:0`,
    porque el estado «LISTENING» viene traducido; `/proc` en Linux; `lsof` en el resto) ni
    imposibles de abrir en exclusiva (atrapa los rangos que reserva Hyper-V/WSL), nunca el 8000
    (D6) ni uno de la flota. Lanza `python -B -m uvicorn` sin `--reload`, con `APOLO_PROJECT`,
    `APOLO_PORT`, `APOLO_DB` y `PYTHONPATH=<repo>/core`, la salida a `data/flota/api-<puerto>.log`
    y, en Windows, fuera del job de la terminal si el job lo deja (`CREATE_BREAKAWAY_FROM_JOB`).
    Espera `/api/health` (300 s): sin `startup_error`, con SU proyecto, y el dueño real del
    puerto = EXACTAMENTE el pid de health, que cuelga del lanzador (snapshot Toolhelp por
    ctypes). Escribe `mcp-<puerto>.json` (servidor `apolo-cad`, `APOLO_URL` de su puerto, el
    python de la flota). Si uno falla, mata los que lanzó en esa llamada: todo o nada.
  - *estado*: cada entrada con lo que dice HOY su health (el proyecto puede haber cambiado por
    `open_project`): `vivo`, `colgado` (el pid vive y no responde), `caído` o `ajeno` (responde
    otro pid o escucha más de uno: zombie-socket).
  - *parar*: mata el árbol (lanzador → API → worker del sandbox; en Windows `taskkill /T /F`,
    sin shutdown; en POSIX SIGTERM, 5 s, SIGKILL) sólo si sigue siendo nuestro (un pid muerto
    pudo reciclarse), espera que suelte el puerto, borra los candados del dueño `*:pid:puerto`
    y comprueba que no quede ninguno; sólo entonces lo saca de `flota.json` y borra su mcp.
- **Tope (D8)**: `min(núcleos lógicos // 2 − vivos de la flota, RAM libre // 900 MiB)` (el pico
  de F0, 893 MB, redondeado hacia arriba; con 0,9 GiB exactos los 4,5 GB de F0 daban 4, no 5).
  La RAM libre ya descuenta a los vivos; el CPU, no: por eso se restan. Excedido → exit 2.
- **Fuera de la letra**: `paths.logs_dir()` acepta `APOLO_LOGS` (como `APOLO_DB`). Sin él, el
  409 que provoca el test lo escribía en el `logs/errors.log` real (el conftest sólo redirige el
  proceso de la suite). `start-apolo.ps1` no se tocó: un `-Project` tendría que fijar
  `$env:APOLO_PROJECT` en la sesión de PowerShell de Mario y deshacerlo al salir; la flota ya lo
  cubre.
- **Tests** (`tests/test_flota.py`, 16, ~1 min): el tope (cálculo, rechazo sin lanzar con exit
  2, el real + 1), el zombie y el proceso ajeno, puertos que saltan 8000/escuchados/evitados,
  el árbol, un id inexistente o repetido, `APOLO_LOGS`, soltar sólo los candados de un dueño, y
  **dos uvicorn reales** sobre una base NUEVA en tmp con un puerto tapado a propósito: arrancan
  saltándolo, el dueño real de cada puerto es su pid de health, `estado` (y su `--json`) los ve,
  abrir desde A el proyecto de B da el 409 exacto (y queda en el log de la prueba firmado por
  A), abrir uno libre suelta el anterior, los mcp-*.json son válidos y `parar` mata los árboles,
  libera los puertos y deja la tabla sin candados. **Todo o nada**: si el segundo arranca con
  startup_error (su proyecto lo tiene un dueño vivo), mueren los dos, no queda lota.json
  ni mcp-*.json y el candado del primero se suelta (el test pescó un mcp escrito antes de
  saber si los demás arrancaban: ahora se escriben al final; y, en la suite completa, un dueño de
  prueba SIN latido vencía a los 30 s mientras la máquina cargada arrancaba los hijos: el test
  late cada 5 s, como un proceso real). Un finalizer los mata aunque algo falle
  (probado corriendo sólo los primeros: no quedó nada en 8100–8200).
- **En vivo**, sobre una COPIA de `data/apolo.db` en el scratchpad (backup de sqlite, 30
  proyectos) con el sandbox precalentado: `arrancar 74 38 28 72` → exit 2 («caben 2 … 2,2 GB
  libres»); `arrancar 38 28 --forzar` → `:8100` y `:8101` en 37 s, vivos tras salir la CLI;
  `:8100` abre 28 → 409 «El proyecto 28 está abierto en el puerto 8101 (pid 24820)»;
  `scripts/e2e_mcp.py --puerto 8100 --proyecto 38` pasa 26/27 (el que falla es su `list_tools`,
  que espera 79 tools y hay 83: desfase previo del script, no de la flota); `parar` → los dos
  parados, candados `[38]` y `[28]` sueltos, tabla vacía y nada escuchando en 8100–8200.
- **Raíz (D9)**: la regla «Una máquina a la vez» pasó a «una máquina por proceso; varias, con
  `scripts/flota.py`».

### F4 (2026-10-21): tres modeladores a la vez — en el escritorio, por túnel SSH

Las APIs corrieron en la PC de escritorio (`apolo-cad-pruebas`, `scripts/flota.py arrancar 38 28
72` sobre una COPIA de la base de la laptop) y los tres `claude -p --model opus` en la laptop, cada
uno con su `--mcp-config` a `127.0.0.1:820x` por un túnel `ssh -L`. La tarea fue la misma para los
tres: una placa de identificación atornillada en el lado de operación, validada con render,
interferencia y puerta.

| | en paralelo | en serie |
|---|---|---|
| faja 38 | 80 s | 69 s |
| puerta 28 | 59 s | 79 s |
| faja de chapa 72 | 90 s | 65 s |
| **total de pared** | **90 s** | **213 s** (×2,4) |
| costo | 2,10 USD | 1,82 USD |

- **RAM:** cada API ocupa ~0,5 GB. La RAM usada del escritorio pasó de 19,9 GB (lo de Mario) a
  un pico de 20,45 GB: sobra para muchos más.
- **Locks:** cero `database is locked` en `logs/errors.log`.
- **El candado da 409:** abrir el 28 desde la API que tiene el 38 responde 409.
- **Lo que halló la tarea** (los tres usaron `join_bolted`):
  - en un tubo cerrado (la 38) la cabeza del perno quedó DENTRO del tubo: no se puede montar.
    Corresponde remache o autorroscante;
  - en la C de chapa (la 72) midió el grip con la caja del perfil (50 mm), no con el alma de 3 mm:
    M6×60;
  - la tuerca quedó del lado visible de la placa;
  - no ofrece tornillo para madera (la puerta);
  - `delivery_check` avisa que los pernos que inserta el propio `join_bolted` «no tienen unión
    declarada»;
  - `$k` empieza en `$1`: dos de tres usaron `$0` y el primer lote falló.

  Van al hito J de [hitos](../hitos.md).
- Lo juzga Mario (el contrato de F4).
