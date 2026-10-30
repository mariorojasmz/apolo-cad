# Genix Apolo CAD

CAD paramétrico 3D para maquinaria industrial/robótica cuyo **diferenciador es el diseño
asistido por IA** (agente-nativo, también manual). Vertical del MVP: transportadores / manejo de
materiales. Stack: **Python (build123d/OCCT) + FastAPI + React/three.js**. IA: Claude por MCP
(`apolo-cad`); el chat de la app viene APAGADO (`APOLO_CHAT=1` lo prende;
[chat-cliente-igual](docs/plans/chat-cliente-igual.md) D19).

Aquí va sólo lo transversal; cada paquete tiene su CLAUDE.md (índice abajo) y la historia vive
en los planes, `docs/devlog.md` y `git log`.

## Arquitectura (principios que NO se negocian)

- **API-first / IA-nativa**: toda operación es un comando sobre un kernel headless.
  UI, agente-chat y MCP son clientes iguales de la misma API HTTP.
- **Documento = log de comandos** (event-sourced). `.apolo` = ZIP (manifest v2 +
  commands.json + attachments/). La geometría nunca se guarda → archivos de KB, autosave
  barato, undo/redo por snapshots.
- **Schema-driven**: los JSON Schemas pydantic del `REGISTRY` generan toolbar, diálogos, panel
  Propiedades y **tools del agente**: una sola fuente de verdad. El MCP es THIN:
  `run_command`/`run_batch` (con `$k`) + `edit_command`/`edit_batch` + undo/redo cubren TODO el
  registro; NO hay tool por comando. Los lotes aceptan **contrato** (`expect`): aserciones que
  deben cumplirse tras el regenerate o el lote se revierte entero ([api](core/apolo/api/CLAUDE.md)).
- **Expresiones**: todo campo numérico acepta `"=expresión"` con variables del proyecto (motor
  AST en `commands/expressions.py`); las variables son comandos `set_variable` en la cabecera
  del log y cambiarlas regenera todo.
- **Selectores declarativos** de aristas/caras, no nombrado topológico frágil.
- **Plantillas de máquina = super-comandos** del registro (`create_conveyor`), no scripts:
  heredan edición paramétrica, undo, BOM y exposición al agente.
- **Criterio de ingeniería por defecto**: el agente diseña como ingeniero (el usuario es el
  CLIENTE) y asume lo obvio —sujeción, montaje con pernos, forma conforme a la función— sin que
  se lo pidan. Fuente ÚNICA: `core/apolo/design/guidelines.py`. Un 3D sólo vale si es
  FABRICABLE y se SOSTIENE.

## Escala — mandato de arquitectura

El proyecto se desarrolla **para crecer a gran escala**: nada de módulos monolíticos ni
responsabilidades mezcladas; si hace falta refactorizar, se refactoriza. Fronteras limpias:
`kernel` (geometría pura) ⟂ `commands/registry` (operaciones+schemas) ⟂ `doc` (log/estado) ⟂
`library` (catálogo/cálculo, funciones puras que NUNCA reciben `Document`) ⟂ `services` (dominio
que LEE un `Document`: `doc` explícito, sin transporte ni locks) ⟂ `api` (transporte) ⟂
`agent`/`mcp` (clientes IA) ⟂ `ui`. Cada módulo nuevo: responsabilidad única, testeable aislado,
sin estado global fuera de los puntos establecidos (`STATE_LOCK`), con tests.

**Un archivo de código tiene ≤ 500 líneas**: los que ya pasan, congelados en los trinquetes
`tests/test_tamano_archivos.py` y `ui/src/tamanoArchivos.test.ts` (sólo bajan); partir uno
grande se hace con un plan.

## Ejecutar y probar

```powershell
.\start-apolo.ps1                 # API+UI en http://127.0.0.1:8000 (-OpenBrowser, -Reload, -Port)
.\.venv\Scripts\python.exe -m pytest tests -q -n auto
cd ui ; npm test                  # vitest
npm run build                     # bundle de la UI (tsc + vite)
```

- **CI** (`.github/workflows/ci.yml`, push a `main` y PR): pytest (Linux 3.11–3.13, Windows
  3.13), vitest + build de la UI, `twine check` y `ruff check core tests scripts` (reglas en
  `[tool.ruff]` de `core/pyproject.toml`; ruff en el extra `dev`).
- **En paralelo** (pytest-xdist, extra `dev`; cifras por máquina en el devlog 2026-10-24): sin
  `-n` pasa igual. Un módulo que no aguanta reparto (procesos en puertos, fixtures de módulo con
  orden) lleva `xdist_group` (como `test_flota.py`); `conftest.py` pone `--dist loadgroup`. Dos
  suites a la vez con el mismo usuario chocan al limpiar `pytest-of-<usuario>`: cada una con su
  `--basetemp`.
- **El reloj de pared, sólo como red gruesa** (con `-n auto` lo inflan los otros workers): un
  costo se mide con `time.process_time()` (en Windows, de a 15,6 ms: ≥ 100 ms de trabajo), «no
  espera» con `Event`s, un ritmo con lo que mide el productor (devlog 2026-10-25).
- Tortura: `@pytest.mark.torture`, excluida por `pytest.ini` (se corre con `-m torture`).
  Baseline de rendimiento (por máquina): `docs/perf_baseline.json` (`scripts/perf_baseline.py`).
- **MCP `apolo-cad`** (`.mcp.json`) = cliente fino stdio→HTTP: requiere la API arriba. El host
  registra al arrancar → reinícialo para ver tools o firmas nuevas (y la API sin `--reload`, tras
  cambiar código).
- Preview de la UI: [ui/CLAUDE.md](ui/CLAUDE.md). `scripts/` y `tests/` no tienen CLAUDE.md: sus
  reglas están aquí o en el paquete que prueban.

### Distribución

Repo **github.com/mariorojasmz/apolo-cad** (MIT) · **PyPI `apolo-cad`** (`apolo` / `apolo-mcp`) ·
**registro oficial MCP** (`io.github.mariorojasmz/apolo-cad`). `apolo/paths.py` es la fuente
ÚNICA de rutas: en un checkout todo resuelve al repo; instalado, los datos van a `APOLO_HOME`
(~/.apolo) y la UI sale del paquete (`apolo/webui`, la stagea `scripts/stage_ui.py`).

### Estado actual

**Las cifras (tests, refs, comandos, tools) no se escriben aquí: se miden** con
`python scripts/conteos.py` (`--rapido`: sin recolectar pytest). V1–V7 cerradas
([roadmap](docs/roadmap.md)); en curso [V8 — la máquina viva](docs/plans/V8-maquina-viva.md)
(tablero eléctrico, co-simulación, placas; cada V8.x con su contrato). Lo que falta de cada plan,
en la `nota:` de su frontmatter. Proyectos de referencia: `faja-paqueteria-4m` (id 38, testigo
del benchmark, 100 % paramétrica), la puerta plegable de carpintería (id 28, segundo testigo),
`layout-planta-demo` (id 53, dos 38 por `insert_project`) y `guarda-banda-demo` (chapa con hems).

## Índice de los CLAUDE.md anidados

Un CLAUDE.md anidado entra al contexto cuando la sesión LEE con `Read` un archivo de su carpeta
o de una subcarpeta (`core/apolo/CLAUDE.md` cubre todo el backend); `Grep` y `Glob` NO lo cargan
([plan de poda](docs/plans/poda-claude-md.md) § Bitácora). → **Antes de editar en un paquete,
lee con `Read` un archivo suyo.** Lo transversal se queda aquí: llega también a quien sólo busca
o trabaja por MCP.

| archivo | qué cubre |
|---|---|
| [core/apolo](core/apolo/CLAUDE.md) | backend común: MCP cliente fino, agente y criterio (`agent/`, `design/`), sandbox de scripts, cinemática (`robotics/`), cachés por `id(shape)` |
| [kernel](core/apolo/kernel/CLAUDE.md) | render, pick, medición, superficies, modelado directo, croquis |
| [commands](core/apolo/commands/CLAUDE.md) | executor (`ExecContext`), colocación, juntas y `fasten`, `join_bolted`, super-comandos, expresiones |
| [doc](core/apolo/doc/CLAUDE.md) | integridad y undo, metadatos de manifest, variantes, caché de geometría, `insert_project` |
| [assembly](core/apolo/assembly/CLAUDE.md) | mates y anclas, DOF, grupos, conectividad |
| [library](core/apolo/library/CLAUDE.md) | catálogo y builders, materiales, chapa, ingeniería y normas, stack-up, reglas de conveyor, interferencias, lints, puertas |
| [library/electrico](core/apolo/library/electrico/CLAUDE.md) | ficha eléctrica de una ref, `Dispositivo`, ERC de seguridad, tablero 3D |
| [library/neumatica](core/apolo/library/neumatica/CLAUDE.md) | ficha `neumatico:`, electroválvula, ERC del aire, cilindros |
| [drawing](core/apolo/drawing/CLAUDE.md) | planos y entregables: último kilómetro, proceso, manual, instalación, DWG |
| [fea](core/apolo/fea/CLAUDE.md) | FEA estático de pieza y bonded de ensamblaje |
| [physics](core/apolo/physics/CLAUDE.md) | MuJoCo: gravedad, caída y dinámica |
| [plc](core/apolo/plc/CLAUDE.md) | PLC virtual: compilador ST → Python seguro, scan determinista, bloques estándar |
| [cosim](core/apolo/cosim/CLAUDE.md) | co-simulación: modelos de dispositivo por `modelo.tipo` |
| [services](core/apolo/services/CLAUDE.md) | dominio que lee un `Document`: mapas de planos, aserciones y `$k`, insumos de las puertas, reglas de ingeniería y FEA, tablero, video, roles por nombre |
| [api](core/apolo/api/CLAUDE.md) | routers y su orden, mutaciones, lotes con contrato, jobs, lecturas a escala, deltas, autosave, locks del FEA |
| [ui](ui/CLAUDE.md) | texto para el usuario (también errores de la API y prompts: tuteo neutro, gates), paneles, sync, viewport |

Una regla va donde se hace el CAMBIO, no donde vive el código que la sufre; el otro paquete
sólo lleva el link (por eso el bump de `GEOM_CACHE_EPOCH` está aquí y no en `doc/`).

## Gestión de los CLAUDE.md

**Claude es el dueño de los `CLAUDE.md`**: decide qué convención, decisión o trampa durable se
persiste y actualiza el archivo que corresponde sin que se lo pidan.

- **Se cargan en cada sesión: cada línea cuesta.** Topes en bytes UTF-8 con LF: raíz ≤ 30 KB,
  cada anidado ≤ 35 KB (`core/apolo/CLAUDE.md` ≤ 10 KB). Los hace cumplir
  `tests/test_claude_md.py`, que además rebota links relativos rotos (como script imprime los
  tamaños).
- **Una línea = qué hacer + link al porqué**, sin historia. La historia (fecha, qué se rompió, quién lo
  reportó, la verificación E2E) vive en el plan, el commit o `docs/devlog.md`. Ninguna cifra que
  cambie por fase (conteos, fechas): chocaba en cada rebase; quien la necesite (la `nota:` de un
  plan, la bitácora) la copia de `python scripts/conteos.py`.
- **Nivel más específico gana; podar > acumular.** Lo de un paquete, en su CLAUDE.md; lo
  transversal, aquí. Una explicación, un lugar: el otro archivo enlaza. Lo obsoleto se corrige o
  se borra en el momento. Sólo lo **no derivable del código**: decisiones, restricciones,
  convenciones tácitas, trampas.
- **Un solo formato de instrucciones para agentes**: `CLAUDE.md`. Nada en `.cursor/`,
  `.github/instructions/` ni similares: divergen solos.
- Un cambio a un CLAUDE.md se verifica con una sesión FRESCA tras el merge (§ Sesiones
  concurrentes).
- **Las reglas de operación del titular** (cola de trabajo, tiempos medidos, máquinas) viven
  fuera del repo y llegan por un `CLAUDE.local.md` ignorado por git. El árbol público sólo lleva
  el núcleo: lo vigila `tests/test_negocio_fuera.py`
  ([núcleo abierto](docs/plans/nucleo-abierto-extensiones-privadas.md) D13–D15).

## Planes (`docs/plans/`)

**Cuándo hay plan**: si el cambio toca más de un paquete, cambia el formato del `.apolo`, del
log de comandos o de la SQLite (un log viejo tiene que seguir regenerando igual), toma una
decisión difícil de revertir o no entra en una sesión. Un fix acotado va directo, con un buen
mensaje de commit.

- **Antes de escribir un plan, lee [docs/plans/README.md](docs/plans/README.md)** (nombre,
  versión, frontmatter, secciones, reglas).
- **El contrato se escribe y se aprueba ANTES de implementar.** El estado es el frontmatter.
- ⚠️ **La `nota:` se actualiza al MERGEAR y al PUBLICAR, no sólo al implementar.** Una nota
  que nombra una rama o un worktree caduca sola.

**Reparto contrato / implementación**: la sesión principal escribe el contrato, lo hace
aprobar y revisa. Cada fase la implementa un subagente (`isolation: "worktree"`,
`model: "opus"`, segundo plano) con prompt autocontenido: base git a verificar, CLAUDE.md a
respetar, alcance estricto, tests como único gate y sin mergear. Al volver: diff contra el
contrato, **re-correr las suites uno mismo** (pytest y, si tocó `ui/`, `npm test` +
`npm run build`), rechazar lo que no cumple y sólo entonces rebase y merge.

**Estimar con tiempos medidos de Claude, no de un humano** (la tabla, en las reglas de operación
del titular).

**Modelar una máquina por MCP también se delega**: un subagente en segundo plano con brief
autocontenido (no puede preguntar a mitad: decide con criterio y lo reporta) y contexto fresco;
dentro de una sesión larga cada llamada relee todo su contexto (devlog 2026-10-30). ⚠️ **Una
máquina por proceso; varias, con `scripts/flota.py`** ([plan](docs/plans/varias-maquinas-a-la-vez.md)):
cada API tiene UN documento (`S.doc`) que `open_project` cambia para todos sus clientes, y los
subagentes comparten el MCP de su sesión → cada modelador extra es un `claude -p --mcp-config
data/flota/mcp-<puerto>.json --strict-mcp-config`.

**Antes de entregar una máquina la revisa OTRO subagente** de sólo lectura (segundo plano,
contexto fresco, a ciegas, con el modelador ya terminado) con el prompt de
[revisor-de-taller](docs/revisor-de-taller.md) (sale de `design/revision.py`); lo confirmado se
corrige y deja regla en [defectos](docs/defectos.md).

## Sesiones concurrentes: worktree para escribir código

Varias sesiones trabajan el repo a la vez; sin aislar comparten árbol e index (commits que
arrastran trabajo ajeno).

- Toda sesión que **escriba código** arranca con `EnterWorktree` (nombre = tema); sólo lectura,
  no.
- ⚠️ **`EnterWorktree` nace de `origin/main`** (atrás si no se pushea): primer comando
  `git merge main --ff-only`, y `git merge main` antes de cada tanda de cambios.
- ⚠️ **Python en un worktree prueba el checkout PRINCIPAL** (el `.venv` editable apunta a SU
  `core/`): antes de pytest, `$env:PYTHONPATH = "$PWD\core"` y `-B` (si no, el `.pyc` recompila
  el principal y recarga la API). Nunca levantes la API desde un worktree (`data/` vacío).
- ⚠️ **La raíz que rige es la del checkout principal, tal como estaba al arrancar**: los
  subagentes heredan la de la sesión padre y los worktrees leen la del PRINCIPAL (los anidados,
  del worktree). Un cambio a la raíz se verifica mergeado, con `claude -p` desde el árbol
  principal. [plan de poda](docs/plans/poda-claude-md.md) § Bitácora
- Subagentes que editan en paralelo: `isolation: "worktree"`. ⚠️ Nunca un subagente sin
  aislamiento que haga `EnterWorktree`: su shell sigue al worktree de la sesión padre.
- Antes de cada commit: `git diff --cached --name-only`; lo ajeno, `git restore --staged`.
- **Editar SIEMPRE dentro del worktree**: una ruta absoluta al principal pasa tests y no sale en
  su `git status` (si pasó: `diff` → `git apply` en el worktree → `git restore`).
- Dentro de un worktree, **un comando git por llamada**: sin `&&`, bucles ni `$(…)`.
- El worktree no trae `ui/node_modules`: `npm ci` en `ui/` si se toca la UI. **No omitir los
  tests**: son el único gate. Las suites, de a una (dos en paralelo dan timeouts falsos).
- **Rebasar justo antes de proponer el merge**, en un solo comando. El `--ff-only` es la red
  y jamás se cambia por `--no-ff` sin decirlo (mergearía código no probado):
  ```powershell
  git -C <worktree> rebase main; if ($?) { git -C <principal> merge <rama-del-worktree> --ff-only }
  ```
- Un `CONFLICT` al rebasar lo resuelve quien mergea: rebasa, corre los tests y mergea.
- **Borrar un worktree**: antes, probar que no sea el cwd de una sesión viva (renombrar la
  carpeta y devolverle el nombre: si falla, está ocupada) y que su rama no tenga commits fuera
  de `main`; luego `git worktree remove` sin `--force`. Con *Filename too long*: `robocopy
  <vacía> <ruta> /MIR` (sale ≠ 0 aun funcionando: `;`), `Remove-Item` y `git worktree prune`.

## Publicación

**Toda publicación (PyPI, registro MCP) sale de `main`, desde el árbol principal. Nunca desde
un worktree ni una rama** (quedaría código que no está en ninguna rama). Flujo: mergear →
verificar (pytest + `npm test` + `npm run build`) → `scripts/release.py --version X.Y.Z`:
sincroniza pyproject, los DOS `version` de `server.json` y las cifras de los 3 README, e imprime
los comandos con credenciales (build/twine/mcp-publisher), que lanza una persona.

## Reglas transversales

### Concurrencia y locks

- **OCCT no es thread-safe**: TODO acceso al documento pasa por `apolo.state.STATE_LOCK`
  (RLock). El WebSocket notifica sólo DESPUÉS de armar el payload.
- **Dos locks**: bajo `STATE_LOCK` sólo se EXTRAE (OCCT → datos puros: teselado, cascos, XML
  MuJoCo, STEP); el trabajo pesado (VTK, `mj_step`, gmsh) corre FUERA con su lock
  (`RENDER_LOCK`, `PHYSICS_LOCK`, `FEA_LOCK`). El orden de locks es único y nunca se invierte
  (autosave: `_flush_lock → STATE_LOCK`). Un endpoint nuevo de render o simulación sigue el
  patrón. [V6.2](docs/plans/V6.2-rendimiento.md) · [api](core/apolo/api/CLAUDE.md)
- **`SANDBOX_LOCK`** (`sandbox.py`) va siempre DESPUÉS de `STATE_LOCK`: `run_script` llega con
  él tomado y `POST /api/script/test` toma sólo el del sandbox; `sandbox.py` jamás importa
  `apolo.state`. [sandbox-caliente](docs/plans/sandbox-caliente.md)

### Log de comandos y regenerate

- **Un lote = UN regenerate**: `execute_many`/`edit_many` son atómicos y dejan 1 undo. No
  reintroducir `validate_params` en el bucle: el regenerate final valida en orden, lo que
  permite `set_variable` + su uso en el mismo lote.
- **Regenerate incremental**: firma acumulada por comando + checkpoint cada 16 comandos
  (`_REGEN_STRIDE`) en copias superficiales que COMPARTEN el shape OCCT → **ningún executor
  muta un shape in-place**. Checkpoint = `RegenState` (`commands/state.py`, por NOMBRE; `copy()`
  aísla todo menos el shape); editar una variable invalida desde el bloque de vars.
- **Regenerate atómico**: construye en locales y vuelca a `self` al final. La carga tolerante
  (suprime el comando roto, nunca toca el log) va SÓLO en rutas de carga; las mutaciones son
  estrictas. Un log viejo regenera igual: un param nuevo entra con el default que reproduce lo
  anterior (`add_joint(arrastrar=False)`). [doc](core/apolo/doc/CLAUDE.md)
- **Params estrictos al entrar, tolerantes al regenerar**: una clave que el comando no declara se
  RECHAZA (con su corrección) y el replay la IGNORA; quitar o renombrar un campo exige upcaster.
  [commands](core/apolo/commands/CLAUDE.md)
- **Metadato ≠ comando**: motion, requirements, stackups, configurations, fea, colores,
  materiales, ocultos y notas viven en el manifest, FUERA del log y de los checkpoints (en el log
  romperían su invariante: [V7.3](docs/plans/V7.3-stackup-cadenas-cotas.md)). Nunca un puente IMPLÍCITO metadato →
  geometría (`=req.x`): no cambia las firmas → geometría vieja; el puente es un `set_variable`
  explícito ([V6.4](docs/plans/V6.4-parametrico-profundo.md)).
- ⚠️ **Cambiaste la geometría con los MISMOS params → versión o epoch**: la caché de geometría
  se indexa por los params, no por el código (un open caliente serviría geometría vieja):
  - UN executor → sube su `version` en el `CommandSpec` (invalida sólo los proyectos que lo
    usan; `insert_project`, compuesto, lleva todas);
  - algo compartido cuyos usuarios puedes nombrar → sube la `version` de cada uno;
  - algo que no puedes acotar (kernel, builders, YAML del catálogo, `Feature`, `RegenState`,
    formato del blob) → bump de `GEOM_CACHE_EPOCH` (`core/apolo/doc/geomcache.py`) con su motivo;
  - la etapa final del regenerate (mates, grupos, visibilidad) → nada (no se cachea).

  `tests/test_contrato_comandos.py` falla si el código de un executor cambia sin decidir. Un
  upgrade de PyPI invalida solo; un checkout, no. [commands](core/apolo/commands/CLAUDE.md)

### Paramétrico y modelado

- **Disciplina paramétrica**: una cota que no cuelga de una variable o expresión NO sigue los
  cambios. En `run_script`/`test_script` las variables son `V["nombre"]`: úsalas, no literales.
  `Pos(...) * result` falla si `result` es una ShapeList (partes disjuntas): traslada por
  coordenada o compón un Compound. Al reparametrizar, revisa lo que dependía de lo que se movió.
  [V6.4](docs/plans/V6.4-parametrico-profundo.md)
- **Nombres por ROL, no por medida** («Larguero (+Y)», nunca «80x40x3»): el árbol y la BOM
  calculan la medida en vivo. Excepción: lo que el sistema LEE del nombre —grado («A36»),
  nameplate («1.5HP 1750rpm»), fit del eje («Ø35 h7», [library](core/apolo/library/CLAUDE.md)).
- **Caja orientada**: `Plane(origin=centro, x_dir=dirección, z_dir=normal) * Box(...)`, no
  `Rotation(0, ry, rz)`: con rumbo ≈ 180° invierte el cabeceo y la caja cae en la diagonal
  OPUESTA del MISMO bbox. Valida la orientación con render aislado + interferencia, no con bbox.
- **Foto de una pieza** = `render_view(isolate=…, zoom)`; nunca ocultar/restaurar en vivo.

### Cirugía de modelos (event-sourced)

- Canjear un sub-ensamblaje: **borrar el sub-grafo COMPLETO de comandos** con
  `remove_commands` (atómico, 1 undo; `con_dependientes=true` arrastra fijadores, anclajes y
  membresías de grupo; juntas y mates, no). [cirugia-liviana](docs/plans/cirugia-liviana.md)
- **NUNCA `boolean_op` para tallar una pieza referenciada por juntas**: consume el target y
  reasigna el id → usa `add_joinery` (muta EN SITIO, conserva el id); para taladros en raíces de
  junta, `dowel`/`rebaje`.
- Anular un corte booleano obsoleto sin romper ids: mover el TOOL fuera del sólido (el cut
  tolera que no interseque).
- `position` editado por REST (`PUT`, `merge=false`) se REEMPLAZA entero: reenvía x, y, z. La
  tool `edit_command` hace PATCH superficial (un sub-objeto `position`/`rotation` igual se
  reemplaza entero). [api](core/apolo/api/CLAUDE.md)
- Muchas ediciones = un lote (`run_batch`/`edit_batch`, con `expect`), nunca N llamadas
  sueltas: el MCP los encola como job con recibo; un script REST sin `?async` queda expuesto al
  timeout del cliente.

### Criterio de diseño (lecciones de proyectos reales)

No están en `design/guidelines.py`; valen al modelar por MCP.

- Bisagra de pliegue: eje en la CARA hacia la que pliega (offset ±esp/2), no al centro; el Ø
  del barril es tope del cierre.
- Lazo cerrado (bifold): el pivote no es monótono → maneja por el recorrido del carro y resuelve
  (θ1, θ2) con `least_squares` + continuación.
- **Faja en V en el lado RÁPIDO** (motor → reductor; en el lento, cadena o acople directo).
  **Tambor MOTRIZ = eje VIVO + chumaceras** (el take-up de eje fijo es para rodillos libres o de
  cola). Anti-giro de un shaft-mount = disco de reacción atornillado a la brida, anclaje DESFASADO.
- **Guarda**: abre al lado máquina, se SOPORTA con ménsulas y se ATORNILLA; nunca a piezas que
  giran (la autodetección por contacto lo hace mal: corrígelo).
- Camino de carga: apoya en una columna (pata a piso) antes que colgar de un tubo de pared fina;
  una ménsula LAPA en cara plana, no entierra un canto. Chumacera de PIE (UCP) = base horizontal;
  junto a un alma vertical, ménsula soldada o chumacera de BRIDA (UCF/UCFL).
- Antes de «mover para dar holgura», confirma el EJE real del conflicto: a veces el fix es
  reposicionar la pieza, no lo que estorba.
- **Cura la conectividad auto-detectada**: una «soldadura» banda ↔ mesa es error de MODELO
  (→ `contacto` con `edit_batch`). Al mover o encoger una pieza, revisa lo que se anclaba a ella:
  la unión declarada sobrevive a la separación y gravity valida en falso.
- Engrosar un miembro cascada a su herraje y holguras vecinas: reposiciona, no sólo la sección.

### Windows y operación

- **Editar sólo YAML NO recarga el worker** (`--reload` vigila los `.py`): toca un `.py` o
  reinicia; sin `--reload`, reinicia tras todo cambio.
- **Zombie-socket :8000**: un `--multiprocessing-fork` huérfano (padre uvicorn muerto) retiene
  el puerto y sirve código VIEJO: verifica el dueño tras reiniciar (`Get-NetTCPConnection
  -LocalPort 8000` + `Win32_Process`) y mátalo.
- **Script offline + `--reload`**: un `import apolo.*` recompila `.pyc` → recarga el worker →
  blanquea el DOC en memoria (`open_project(id)` lo recupera del autosave; un «Sin título» vacío
  que quede como reciente se borra desde la UI).
- **Flujo «revisa»**: Mario prueba la UI a mano y los errores caen en `logs/errors.log`; «revisa»
  → leer, agrupar por causa raíz, parchear y limpiar el log.

## Doctrina de RESULTADOS

Apolo **NO persigue paridad de herramientas** con SolidWorks/Inventor (son para la manipulación
HUMANA). La meta es que el **agente entregue RESULTADOS iguales o mejores que lo que un despacho
competente TERMINA en SW/Inventor** —3D validado + planos de taller + memoria de cálculo +
BOM/cotización + manual—, en calidad y en tiempo.

- Una función sólo importa si mejora un entregable final; lo que existe para el trabajo manual
  humano no se porta.
- La madurez se mide con **benchmarks de entregables** (misma máquina: paquete Apolo vs el
  terminado a mano), no por lista de features.
- **Una librería que se queda corta se reemplaza por una propia a la medida**: primero se mide
  dónde se queda corta (una F0); el costo en días no es el criterio, sí que mejore el entregable.
- Donde el incumbente no integra nada (memoria con normas, cotización, validación de sujeción y
  gravedad) Apolo ya supera; donde el humano pule a mano (el último kilómetro del plano), Apolo
  cierra la brecha con CRITERIO automático.

## Roadmap, madurez y pendientes

- **Hojas de ruta V5–V7**: [docs/roadmap.md](docs/roadmap.md).
- **Madurez**: si Mario pregunta cómo madura Apolo, compara contra
  [docs/benchmark/README.md](docs/benchmark/README.md) (ejes, serie medida, rúbrica vigente,
  segundo testigo) y contra la doctrina de arriba.
- **Pendientes**: la `nota:` de cada plan; lo que no tiene plan, [docs/backlog.md](docs/backlog.md).
  Antes de tomar uno, verifícalo contra el código.
- **Narrativa** (E2E, cirugías, decisiones con contexto): [docs/devlog.md](docs/devlog.md) y `git log`.

## Fuera de alcance deliberado

CAM, FEA de contacto o no lineal (el lineal de pieza y el bonded de ensamblaje sí:
[fea](core/apolo/fea/CLAUDE.md)), nube multiusuario y diseño generativo. Electricidad, control y
placas son [V8](docs/plans/V8-maquina-viva.md). Librerías candidatas con licencia: `docs/devlog.md`
§ «Catálogo de librerías candidatas (con licencia)».
