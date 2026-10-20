---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: F0 medida (corrigió D5–D7); faltan F1–F4
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
