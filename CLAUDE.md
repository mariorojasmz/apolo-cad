# Genix Apolo CAD

CAD paramétrico 3D para maquinaria industrial/robótica cuyo **diferenciador es el
diseño asistido por IA** (agente-nativo, también manual). Vertical del MVP:
transportadores / manejo de materiales. Stack: **Python (build123d/OCCT) + FastAPI +
React/three.js**. IA: Claude API en la nube vía `APOLO_MODEL` (por defecto
`claude-opus-4-8`).

Este archivo tiene sólo lo transversal: principios, cultura de trabajo y reglas que valen en
todo el repo. El detalle de cada paquete está en su propio CLAUDE.md (índice más abajo); la
historia, en el plan de cada versión, en `docs/devlog.md` y en `git log`.

## Arquitectura (principios que NO se negocian)

- **API-first / IA-nativa**: toda operación es un comando sobre un kernel headless.
  UI, agente-chat y MCP son clientes iguales de la misma API HTTP.
- **Documento = log de comandos** (event-sourced). `.apolo` = ZIP (manifest v2 +
  commands.json + attachments/). La geometría nunca se guarda → archivos de KB,
  autosave barato, undo/redo por snapshots.
- **Schema-driven**: los JSON Schemas pydantic del `REGISTRY` generan a la vez la
  toolbar, los diálogos, el panel Propiedades y las **tools del agente**. Una sola
  fuente de verdad. El MCP es THIN: `run_command`/`run_batch` (con `$k`) +
  `edit_command`/`edit_batch` + undo/redo cubren TODO el registro; NO hay tool por comando
  (los huecos auditados siempre fueron de LECTURA, no de escritura). Los lotes aceptan
  **contrato** (`expect`): aserciones que deben cumplirse tras el regenerate o el lote se
  revierte entero ([api](core/apolo/api/CLAUDE.md)).
- **Expresiones**: cualquier campo numérico acepta `"=expresión"` con variables del
  proyecto (motor AST en `commands/expressions.py`). Las variables son comandos
  `set_variable` en la cabecera del log; cambiarlas regenera todo.
- **Selectores declarativos** de aristas/caras (todas/direccion/cara/longitud/cerca)
  para evitar nombrado topológico frágil.
- **Plantillas de máquina = super-comandos** del registro (p. ej. `create_conveyor`),
  no scripts: heredan edición paramétrica, undo, BOM y exposición al agente gratis.
- **Criterio de ingeniería por defecto**: el agente diseña como ingeniero/estructurista
  (el usuario es el CLIENTE) y asume lo obvio —sujeción, montaje/desmontaje con pernos,
  forma conforme a la función— sin esperar a que se lo pidan. Fuente ÚNICA:
  `core/apolo/design/guidelines.py` ([core/apolo](core/apolo/CLAUDE.md)). Un 3D sólo vale si
  es FABRICABLE y se SOSTIENE.

## Escala — mandato de arquitectura

Este proyecto se desarrolla **para crecer a gran escala**. Por tanto: nada de módulos
monolíticos ni responsabilidades mezcladas; si para hacerlo bien hace falta refactorizar,
se refactoriza. Fronteras limpias: `kernel` (geometría pura) ⟂ `commands/registry`
(operaciones+schemas) ⟂ `doc` (log/estado) ⟂ `library` (catálogo/cálculo, funciones
puras que NUNCA reciben `Document`) ⟂ `services` (dominio que LEE un `Document`: `doc`
explícito, sin transporte ni locks) ⟂ `api` (transporte) ⟂ `agent`/`mcp` (clientes IA)
⟂ `ui`. Cada módulo nuevo: responsabilidad única, testeable aislado, sin estado global
fuera de los puntos establecidos (`STATE_LOCK`), con tests.

**Un archivo de código tiene ≤ 500 líneas**: los que ya pasan quedan congelados en los
trinquetes `tests/test_tamano_archivos.py` y `ui/src/tamanoArchivos.test.ts` (su número sólo
baja); partir un archivo grande se hace con un plan.

## Ejecutar y probar

```powershell
.\start-apolo.ps1                 # API+UI en http://127.0.0.1:8000 (-OpenBrowser, -Reload, -Port)
.\.venv\Scripts\python.exe -m pytest tests -q     # 1830 tests (tortura extendida: -m torture)
cd ui ; npm test                  # vitest: gates de texto y de tamaño
npm run build                     # bundle de la UI (tsc + vite)
```

- **CI** (`.github/workflows/ci.yml`, en push a `main` y en PR): pytest en Linux 3.11–3.13 y
  Windows 3.13, vitest + build de la UI, build + `twine check` del paquete y
  `ruff check core tests scripts` (reglas en `[tool.ruff]` de `core/pyproject.toml`; ruff viene
  en el extra `dev`).
- Tortura: los casos extendidos llevan `@pytest.mark.torture` y `pytest.ini` los excluye por
  defecto. Baseline de rendimiento: `docs/perf_baseline.json` (`scripts/perf_baseline.py`,
  depende de la máquina).
- **MCP `apolo-cad`** (`.mcp.json`) = cliente fino stdio→HTTP: requiere la API arriba. El host
  registra al arrancar → reinícialo para ver tools o firmas nuevas; la API sin `--reload` también
  se reinicia tras cambiar código.
- Preview de la UI: configs `ui-dev`/`ui-preview` de `.claude/launch.json` (cuál, en
  [ui/CLAUDE.md](ui/CLAUDE.md)). `scripts/` y `tests/` no tienen CLAUDE.md propio: sus reglas
  están aquí o en el paquete que prueban.

### Distribución (público desde 2026-08-08)

Repo **github.com/mariorojasmz/apolo-cad** (MIT) · paquete **PyPI `apolo-cad`** (entry points
`apolo` / `apolo-mcp`) · ficha en el **registro oficial MCP** (`io.github.mariorojasmz/apolo-cad`).

- `apolo/paths.py` es la fuente ÚNICA de rutas: en un checkout todo resuelve al repo
  (`ui_dist()` prefiere `ui/dist`); instalado, los datos van a `APOLO_HOME` (~/.apolo) y la UI
  sale del paquete (`apolo/webui`, la stagea `scripts/stage_ui.py`).
- **`planegcs` va con marcador de entorno** (wheels sólo cp312/cp313 win+linux x86_64; fuera de
  ahí el croquis cae a scipy): como dependencia dura rompía la instalación en macOS y Py3.11.
- Publicar: § Publicación.

### Estado actual (2026-10-05)

1830 tests (+18 de tortura vía `-m torture`) · 63 tests vitest · 79 tools MCP · 53 comandos ·
catálogo 231 refs. Hojas de ruta V1–V7 cerradas ([roadmap](docs/roadmap.md)); en curso:
[chat-cliente-igual](docs/plans/chat-cliente-igual.md) (espera decisiones de Mario); en plan: [harness-automejora](docs/plans/harness-automejora.md).
Proyectos de referencia: `faja-paqueteria-4m` (id 38, testigo del benchmark, 100 %
paramétrica), la puerta plegable de carpintería (id 28, segundo testigo), `layout-planta-demo`
(id 53, dos fajas 38 por `insert_project`) y `guarda-banda-demo` (chapa en C con hems).

## Índice de los CLAUDE.md anidados

**Cómo cargan** (medido en la F0 del [plan de poda](docs/plans/poda-claude-md.md), § Bitácora):
un CLAUDE.md anidado entra al contexto cuando la sesión LEE con `Read` un archivo de su carpeta
o de cualquier subcarpeta (`library/CLAUDE.md` cubre `library/engineering/`;
`core/apolo/CLAUDE.md`, todo el backend). `Grep` y `Glob` NO lo cargan. → **Antes de editar en
un paquete, lee con `Read` un archivo de ese paquete.** Lo transversal se queda aquí: llega
también a quien sólo busca o trabaja por MCP.

| archivo | qué cubre |
|---|---|
| [core/apolo](core/apolo/CLAUDE.md) | backend común: MCP cliente fino (`mcp_server.py`), agente y criterio (`agent/`, `design/`), cinemática (`robotics/`: FK, GIF), física (`physics/`), cachés por `id(shape)` |
| [kernel](core/apolo/kernel/CLAUDE.md) | render, pick, medición; superficies; modelado directo; croquis (dos motores) |
| [commands](core/apolo/commands/CLAUDE.md) | firma de executor (`ExecContext`), colocación, juntas y `fasten`, `join_bolted`, super-comandos, expresiones |
| [doc](core/apolo/doc/CLAUDE.md) | integridad y undo, metadatos de manifest, variantes, caché de geometría, `insert_project` |
| [assembly](core/apolo/assembly/CLAUDE.md) | mates y anclas, DOF, grupos, conectividad |
| [library](core/apolo/library/CLAUDE.md) | catálogo y builders, materiales, chapa, ingletes, ingeniería y normas, stack-up, reglas de conveyor, interferencias, lints, puerta de entrega |
| [drawing](core/apolo/drawing/CLAUDE.md) | planos y entregables: último kilómetro (soldadura, tolerancias, Ra, datum, GD&T), proceso, manual, instalación, DWG |
| [fea](core/apolo/fea/CLAUDE.md) | FEA estático de pieza y bonded de ensamblaje |
| [services](core/apolo/services/CLAUDE.md) | dominio que lee un `Document` (reglas de la capa): mapas por pieza de los planos, datos de instalación, stack-up, aserciones y contrato `$k`, puerta de entrega, reglas de ingeniería y FEA, preparación del FEA, roles por nombre |
| [api](core/apolo/api/CLAUDE.md) | routers (dónde va una ruta y su orden), mutaciones, lotes con contrato, jobs, lecturas a escala, deltas, autosave, tests de la API, la coreografía de locks del FEA |
| [ui](ui/CLAUDE.md) | texto para el usuario —también errores de la API y prompts— (tuteo neutro, gates), preview, paneles, sync, viewport, croquis |

Una regla va donde se hace el CAMBIO, no donde vive el código que la sufre; el otro paquete
sólo lleva el link (por eso el bump de `GEOM_CACHE_EPOCH` está aquí y no en `doc/`).

## Gestión de los CLAUDE.md

**Claude es el dueño de los `CLAUDE.md`**: decide qué convención, decisión o trampa durable
merece persistirse y actualiza el archivo que corresponde sin que se lo pidan.

- **Se cargan en cada sesión: cada línea cuesta.** Topes en bytes UTF-8 con LF: raíz ≤ 30 KB,
  cada anidado ≤ 35 KB (`core/apolo/CLAUDE.md` ≤ 10 KB: carga en toda lectura de backend). Los
  hace cumplir `tests/test_claude_md.py`, que además rebota links relativos rotos
  (`python tests/test_claude_md.py` imprime los tamaños); la poda de julio, sin gate, volvió de
  76 a 125 KB ([plan de poda](docs/plans/poda-claude-md.md)). Nada entra con historia.
- **Una línea = qué hacer + link al porqué.** La historia (fecha, qué se rompió, quién lo
  reportó, la verificación E2E) vive en el plan que la parió, en el commit o en
  `docs/devlog.md`; aquí se cita, no se repite. Al cerrar trabajo, actualizar los conteos de
  «Estado actual».
- **Nivel más específico gana; podar > acumular.** Lo de un paquete va en su CLAUDE.md (índice
  arriba); lo transversal, aquí. Una explicación, un lugar: el otro archivo enlaza, no repite.
  Lo obsoleto se corrige o se borra en el momento. Sólo lo **no derivable del código**:
  decisiones, restricciones, convenciones tácitas, trampas.
- **Un solo formato de instrucciones para agentes**: `CLAUDE.md`. Nada en `.cursor/`,
  `.github/instructions/` ni similares: divergen solos.
- Un cambio a un CLAUDE.md se verifica con una sesión FRESCA después del merge (§ Sesiones
  concurrentes explica por qué no sirve un subagente).

## Planes (`docs/plans/`)

**Cuándo hay plan**: si el cambio toca más de un paquete (`kernel`, `commands`, `doc`,
`library`, `api`, `mcp`, `ui`…), cambia el formato del `.apolo`, del log de comandos o de la
SQLite (un log viejo tiene que seguir regenerando igual), toma una decisión difícil de
revertir o no entra en una sesión. Un fix acotado va directo, con un buen mensaje de commit.

**Forma**: `docs/plans/V<versión>-slug.md` (p. ej. `V7.6-e2-fino.md`). La versión del roadmap
ES el número del plan: ya está citada en commits, benchmarks y [docs/roadmap.md](docs/roadmap.md).
Un plan fuera del roadmap va con slug solo (`harness-automejora.md`). Frontmatter:

```yaml
---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: una línea con lo que falta DE VERDAD (una fase, una medición, un clic de Mario) o «sin pendientes»
descripcion: una línea con lo que cambia para quien usa Apolo
---
```

Título `# V<versión> — <el resultado, dicho como lo diría el usuario>` («El agente valida el
lote antes de aplicarlo», no «Refactor de verify»). Secciones en este orden; la que no
aplica se omite:

1. **Estado y origen**: quién lo pidió, con su frase textual, y qué evidencia lo disparó.
2. **El problema / lo que hay hoy**: medido, con `archivo:línea` o la consulta. Sin evidencia no entra.
3. **Lo que se revisó antes de escribir esto**: lo que se leyó del código y cambió la solución.
4. **Decisiones (para vetar)**: D1…Dn, cada una en negrita con su porqué. Mario veta por número.
5. **Alternativas descartadas** y por qué.
6. **Fases**: F0 mide (sólo lectura) … Fn verifica. Cada una: qué hace, qué paquete, tamaño
   S/M/L, de qué depende y cómo se verifica.
7. **Lo que este plan NO hace.**
8. **Riesgos**: riesgo y su mitigación.
9. **Bitácora**, al cerrar cada fase: qué se hizo, qué reveló cada intento fallido, la causa
   raíz del diagnóstico equivocado y los números medidos.

**Reglas**:
- **El contrato se escribe y se aprueba ANTES de implementar.** La versión se reserva
  mergeando el archivo a `main` apenas se aprueba: dos planes con la misma versión mergean
  limpio y git no avisa. Tras cada rebase, verificar que siga única; tomada ⇒ renombrar.
  Quien detecta el choque con su plan ya implementado no renumera: los duplicados se citan
  por slug.
- **El estado es el frontmatter, nunca la carpeta**: nada se mueve a `done/` (la carpeta se
  eliminó el 2026-10-03).
- ⚠️ **La `nota:` se actualiza al MERGEAR y al PUBLICAR, no sólo al implementar.** Una nota
  que nombra una rama o un worktree caduca sola.
- **Sin commits en tres semanas, se decide**: `implementado` con nota de qué quedó fuera,
  `descartado` apuntando a quién lo cubrió, o `en curso` con dueño escrito.
- **Se documenta el razonamiento, no sólo el cambio**: en la bitácora del plan, en el CLAUDE.md
  que corresponda (la regla durable, en una línea) y en el commit (qué se creía, qué pasó, qué
  se aprendió; no un changelog).
- Si algún día hay un índice de planes, se GENERA del frontmatter con un script y jamás se
  edita a mano.

**Reparto contrato / implementación**: la sesión principal escribe el contrato, lo hace
aprobar y revisa. Cada fase la implementa un subagente con `isolation: "worktree"`,
`model: "opus"` y en segundo plano, con un prompt autocontenido: base git a verificar,
CLAUDE.md a respetar, alcance estricto, tests como único gate y sin mergear. Al volver: leer
el diff contra el contrato, **re-correr las suites uno mismo** (pytest y, si tocó `ui/`,
`npm test` + `npm run build`), rechazar lo que no cumple y sólo entonces rebase y merge.

## Sesiones concurrentes: worktree para escribir código

Varias sesiones trabajan el repo a la vez; sin aislar comparten árbol e index (renames a
medio stagear, commits que arrastran trabajo ajeno).

- Toda sesión que **escriba código** arranca con `EnterWorktree` (nombre = tema). Sólo
  lectura no lo necesita.
- ⚠️ **`EnterWorktree` nace de `origin/main`**: si no se pushea seguido, nace atrás. Primer
  comando: `git merge main --ff-only`. Y `git merge main` antes de cada tanda de cambios, no
  sólo al final.
- ⚠️ **Python en un worktree prueba el checkout PRINCIPAL**: el `.venv` es el del árbol
  principal y su instalación editable apunta a SU `core/` → pytest da verde sobre código que
  no es el tuyo. En el worktree: `$env:PYTHONPATH = "$PWD\core"` antes de correr pytest (y
  `-B`, o el `.pyc` recompila el principal y recarga la API con `--reload`). Tampoco levantes
  la API desde un worktree: `paths.repo_root()` sería el worktree y arrancaría con un `data/`
  vacío.
- ⚠️ **La raíz que rige es la del checkout principal, tal como estaba al arrancar** (medido,
  [plan de poda](docs/plans/poda-claude-md.md) § Bitácora): un subagente recibe el CLAUDE.md
  raíz que cargó la sesión padre al ARRANCAR, no el archivo actual; las sesiones y subagentes
  en un worktree (también con `isolation: "worktree"`) leen la raíz del checkout PRINCIPAL (los
  anidados sí, del worktree). → Un cambio a la raíz en un worktree no rige hasta mergearse;
  para verificarlo, mergea y abre una sesión fresca con `claude -p` desde el árbol principal.
- Subagentes que editan en paralelo: `isolation: "worktree"`. ⚠️ Nunca un subagente sin
  aislamiento que haga `EnterWorktree`: su shell sigue al worktree de la sesión padre.
- Antes de cada commit: `git diff --cached --name-only`; lo ajeno se saca con
  `git restore --staged`.
- **Editar SIEMPRE dentro del worktree**: una ruta absoluta al árbol principal compila, pasa
  tests y no aparece en el `git status` del worktree. Si pasó: `git -C <principal> diff >
  patch`, `git apply` en el worktree, `git restore` en el principal.
- Dentro de un worktree, **un comando git por llamada**: sin `&&`, bucles ni `$(…)`.
- El worktree no trae `ui/node_modules`: `npm ci` en `ui/` si se toca la UI. **No omitir los
  tests**: son el único gate. Las suites se corren de a una; dos en paralelo dan timeouts
  falsos.
- **Rebasar justo antes de proponer el merge**, en un solo comando. El `--ff-only` es la red
  y jamás se cambia por `--no-ff` sin decirlo (mergearía código no probado contra la rama
  nueva):
  ```powershell
  git -C <worktree> rebase main; if ($?) { git -C <principal> merge <rama-del-worktree> --ff-only }
  ```
- ⚠️ **`main` avanza también entre que el agente rebasa y Mario pega el comando.** Un
  `CONFLICT` lo resuelve el agente, no Mario: rebasa de nuevo, corre los tests y vuelve a dar
  el comando.
- **Quien instaló dependencias las borra al terminar**: en Windows, la ruta larga de
  `node_modules` hace explotar `git worktree remove` con *Filename too long*. Si igual falla,
  git pudo desregistrar el worktree y dejar la carpeta: borrarla así y después
  `git worktree prune`:
  ```powershell
  $v = Join-Path $env:TEMP 'vacia'; New-Item -ItemType Directory -Force $v | Out-Null
  robocopy $v '<ruta-del-worktree>' /MIR /NFL /NDL /NJH /NJS | Out-Null
  Remove-Item '<ruta-del-worktree>' -Recurse -Force
  ```
  `robocopy` devuelve exit code ≠ 0 aun cuando funciona: encadenar con `;`, nunca con `if ($?)`.
- **Antes de borrar un worktree, probar que no sea el cwd de una sesión viva**: renombrar la
  carpeta y devolverle el nombre; si falla, está ocupada. Ni git ni la antigüedad lo
  detectan. Borrar con `git worktree remove` sin `--force`.

## Publicación

**Toda publicación (PyPI `apolo-cad`, registro MCP) sale de `main`, desde el árbol
principal, con `scripts/release.py`. Nunca desde un worktree ni una rama**: el paquete
publicado quedaría con código que no está en ninguna rama. Flujo: mergear → verificar
(pytest + `npm test` + `npm run build`) → `scripts/release.py --version X.Y.Z` desde la raíz:
sincroniza pyproject + `server.json` (los DOS `version`) + las cifras de los 3 README e
imprime los comandos con credenciales (build/twine/mcp-publisher), que lanza una persona.

## Reglas transversales

### Concurrencia y locks

- **OCCT no es thread-safe**: TODO acceso al documento pasa por `apolo.state.STATE_LOCK`
  (RLock). Notifica por WebSocket sólo DESPUÉS de construir el payload.
- **Dos locks**: bajo `STATE_LOCK` sólo se EXTRAE (OCCT → datos puros: teselado, cascos, XML
  MuJoCo, STEP); el trabajo pesado (VTK, `mj_step`, gmsh) corre FUERA con su propio lock
  (`RENDER_LOCK`, `PHYSICS_LOCK`, `FEA_LOCK`). El orden de locks es único y nunca se invierte
  (autosave: `_flush_lock → STATE_LOCK`). Un endpoint nuevo de render o simulación sigue el
  patrón. [V6.2](docs/plans/V6.2-rendimiento.md) · detalle en [api](core/apolo/api/CLAUDE.md).

### Log de comandos y regenerate

- **Un lote = UN regenerate**: `execute_many`/`edit_many` son atómicos y dejan 1 undo. No
  reintroducir `validate_params` en el bucle: el regenerate final valida en orden, lo que
  permite `set_variable` + su uso en el mismo lote.
- **Regenerate incremental**: firma acumulada por comando + checkpoint cada 16 comandos
  (`_REGEN_STRIDE`) en copias superficiales que COMPARTEN el shape OCCT → **ningún executor
  muta un shape in-place**. Checkpoint = `RegenState` (`commands/state.py`: scene, variables,
  joints, mates, constraints, fasteners, grounds, groups, por NOMBRE; `copy()` aísla todo menos
  el shape); editar una variable invalida desde el bloque de vars.
- **Regenerate atómico**: construye en locales y vuelca a `self` al final. La carga tolerante
  (suprime el comando roto, nunca toca el log) va SÓLO en rutas de carga; las mutaciones son
  estrictas. Un log viejo regenera igual: un param nuevo entra con un default que reproduce lo
  anterior (p. ej. `add_joint(arrastrar=False)`). [doc](core/apolo/doc/CLAUDE.md)
- **Params estrictos al entrar, tolerantes al regenerar**: una clave que el comando no declara se
  RECHAZA (con su corrección) y el replay la IGNORA; quitar o renombrar un campo exige upcaster.
  [commands](core/apolo/commands/CLAUDE.md)
- **Metadato ≠ comando**: motion, requirements, stackups, configurations, fea, colores,
  materiales, ocultos y notas viven en el manifest, FUERA del log y de los checkpoints. Un dato así es metadato con
  endpoint, no comando: en el log rompería la invariante de checkpoints
  ([V7.3](docs/plans/V7.3-stackup-cadenas-cotas.md)). Nunca un puente IMPLÍCITO metadato →
  geometría (`=req.x`): no cambia las firmas → geometría vieja; el puente es un `set_variable`
  explícito ([V6.4](docs/plans/V6.4-parametrico-profundo.md)).
- ⚠️ **Cambiaste la geometría con los MISMOS params → versión o epoch**: la caché de geometría
  se indexa por los params, no por el código; si no decides, un open caliente sirve geometría
  vieja (la v4 del epoch llegó con meses de atraso). Según lo que tocaste:
  - UN executor → sube su `version` en el `CommandSpec` (invalida sólo los proyectos que lo
    usan; `insert_project`, compuesto, lleva todas);
  - algo compartido cuyos usuarios puedes nombrar → sube la `version` de cada uno;
  - algo que no puedes acotar (kernel, builders, YAML del catálogo, `Feature`, `RegenState`,
    formato del blob) → bump de `GEOM_CACHE_EPOCH` (`core/apolo/doc/geomcache.py`) con su motivo;
  - la etapa final del regenerate (mates, grupos, visibilidad) → nada: no se cachea.

  `tests/test_contrato_comandos.py` falla si el código de un executor cambia sin decidir. Un
  upgrade de PyPI invalida solo; un checkout, no. [commands](core/apolo/commands/CLAUDE.md)

### Paramétrico y modelado

- **Disciplina paramétrica**: una cota que no cuelga de una variable o expresión NO sigue los
  cambios. `run_script` (y `test_script`) ve las variables del proyecto como `V["nombre"]`:
  escríbelo con `V[...]`, no con literales. `Pos(...) * result` falla si `result` es una
  ShapeList (partes disjuntas): traslada a nivel de coordenada o compón un Compound. Al
  reparametrizar, revisa las piezas que dependían de otra que se movió.
  [V6.4](docs/plans/V6.4-parametrico-profundo.md)
- **Nombres por ROL, no por medida** («Larguero (+Y)», nunca «80x40x3»): la medida es un dato
  derivado que el árbol y la BOM calculan en vivo. Excepción: lo que el sistema LEE del nombre
  —grado de material («A36»), nameplate («1.5HP 1750rpm»), fit del eje («Ø35 h7»,
  [library](core/apolo/library/CLAUDE.md)).
- **Caja orientada**: `Plane(origin=centro, x_dir=dirección, z_dir=normal) * Box(...)` con ejes
  explícitos, no `Rotation(0, ry, rz)`: con Δx < 0 (rumbo ≈ 180°) el orden de rotaciones
  invierte el cabeceo y la caja cae en la diagonal OPUESTA del MISMO bbox (bbox y measure dan
  «bien»). Valida la orientación con un render aislado + interferencia, no con el bbox.
- **Fotografiar una pieza** = `render_view(isolate=…, zoom)`; nunca ocultar/restaurar en vivo.

### Cirugía de modelos (event-sourced)

- Canjear un sub-ensamblaje: **borrar el sub-grafo COMPLETO de comandos** con
  `POST /api/commands/remove` (atómico; piezas + FIJADORES juntos para no dejar referencias
  colgando; antes, `DELETE /api/fasteners/{name}` de los auto-declarados).
- **NUNCA `boolean_op` para tallar una pieza referenciada por juntas**: consume el target y
  reasigna el id → usa `add_joinery` (muta EN SITIO, conserva el id); para taladros en raíces de
  junta, `dowel`/`rebaje`.
- Anular un corte booleano obsoleto sin romper ids: mover el TOOL fuera del sólido (el cut
  tolera un tool que no interseca).
- `position` editado por REST (`PUT`, `merge=false` por defecto) se REEMPLAZA entero: reenvía
  x, y, z. La tool MCP `edit_command` hace PATCH superficial (un sub-objeto
  `position`/`rotation` igual se reemplaza entero). [api](core/apolo/api/CLAUDE.md)
- Muchas ediciones = un lote (`run_batch`/`edit_batch`, con `expect`), nunca N llamadas
  sueltas: el MCP los encola como job con recibo; un script REST propio sin `?async` queda
  expuesto al timeout del cliente.

### Criterio de diseño (lecciones de proyectos reales)

No están en `design/guidelines.py`; valen al modelar por MCP.

- Bisagra de pliegue: eje en la CARA hacia la que pliega (offset ±esp/2), no al centro; el Ø
  del barril es el tope del cierre.
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
- Antes de «mover para dar holgura», confirma el EJE real del conflicto; a veces el fix es
  reposicionar la pieza, no tocar lo que estorba.
- **Cura la conectividad auto-detectada**: una «soldadura» banda ↔ mesa es error de MODELO
  (→ `contacto` con `edit_batch`). Al mover o encoger una pieza, revisa las que se anclaban a
  ella: la unión declarada sobrevive a la separación y gravity valida en falso.
- Engrosar un miembro cascada a su herraje y holguras vecinas: reposiciona, no sólo cambies la
  sección.

### Windows y operación

- **Editar sólo YAML NO recarga el worker** (`--reload` vigila los `.py` por contenido): toca un
  `.py` o reinicia. Sin `--reload`, reinicia siempre tras un cambio.
- **Zombie-socket :8000**: un `multiprocessing.spawn` huérfano (hijo de un uvicorn muerto)
  retiene el puerto y sirve código VIEJO; un «reinicio» sin verificar el dueño real VALIDA EN
  FALSO. Detectar: `Get-NetTCPConnection -LocalPort 8000` + buscar en `Win32_Process` el
  `--multiprocessing-fork` con el padre muerto; matarlo (o todos los python del venv).
- **Script offline + `--reload`**: un script que haga `import apolo.*` recompila `.pyc` →
  recarga el worker → blanquea el DOC en memoria (el autosave ya guardó: `open_project(id)`
  recupera). Si un segundo reload corta la carga del arranque, queda un «Sin título» vacío como
  reciente → reabre el real y borra el basura desde la UI.
- **Flujo «revisa»**: Mario prueba la UI a mano y los errores caen en `logs/errors.log`; al
  decir «revisa» → leer, agrupar por causa raíz, parchear y limpiar el log.

## Doctrina de RESULTADOS (usuario, 2026-07-10)

Apolo **NO persigue paridad de herramientas** con SolidWorks/Inventor: son herramientas para la
manipulación HUMANA y ese costo nos lo ahorramos. La meta es que el **agente entregue RESULTADOS
iguales o mejores que lo que un despacho competente TERMINA en SW/Inventor** —3D validado +
juego de planos de taller + memoria de cálculo + BOM/cotización + manual—, en calidad y en tiempo.

- Una función sólo importa si mejora un entregable final; lo que existe para el trabajo manual
  humano no se porta.
- La madurez se mide con **benchmarks de entregables** (misma máquina: paquete Apolo vs el
  terminado a mano), no por lista de features.
- Donde el incumbente no entrega nada integrado (memoria con normas, cotización, validación de
  sujeción y gravedad) Apolo ya supera; donde el humano pule a mano (el último kilómetro del
  plano), Apolo cierra la brecha con CRITERIO automático.

## Roadmap, madurez y pendientes

- **Hojas de ruta V5–V7**, una línea por versión con link a su plan: [docs/roadmap.md](docs/roadmap.md).
- **Madurez**: cuando Mario pregunte cómo madura Apolo, compara contra
  [docs/benchmark/README.md](docs/benchmark/README.md) (ejes por features, serie medida, rúbrica
  vigente y la reserva del segundo testigo) y contra la doctrina de arriba.
- **Pendientes**: la `nota:` de cada plan es la fuente; lo que no tiene plan está en
  [docs/backlog.md](docs/backlog.md). Antes de tomar uno, verifícalo contra el código.
- **Narrativa** (E2E, cirugías, decisiones con contexto): [docs/devlog.md](docs/devlog.md) y `git log`.

## Fuera de alcance deliberado

CAM, FEA de contacto o no lineal (el estático lineal de pieza y el bonded de ensamblaje sí
existen: [fea](core/apolo/fea/CLAUDE.md)), PCB/electrónica, nube multiusuario y diseño
generativo. Librerías candidatas (con licencias) para futuras adopciones: `docs/devlog.md`
§ «Catálogo de librerías candidatas (con licencia)».
