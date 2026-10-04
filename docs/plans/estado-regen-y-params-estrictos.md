---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: F0 (golden; base fuera del repo, en %TEMP%\apolo-golden), F1 (RegenState, epoch 5), F2 y F3 (despacho único: los 53 executors reciben ExecContext), F4 (entrada estricta, pydantic>=2.12) y F5 (versión por comando) hechas y sin mergear; falta F6; implementación delegada sin aprobación previa del contrato — revisar D1–D13 (D11 y D12 son extras vetables)
descripcion: Si tú o el agente mandan un parámetro que no existe, Apolo lo rechaza y sugiere el correcto (antes lo ignoraba en silencio); tus proyectos guardados regeneran idénticos
---

# Un parámetro que no existe se rechaza con su corrección, y tus proyectos guardados regeneran idénticos

## Estado y origen

Pedido de Mario (2026-10-03), sobre la lista de pendientes de la auditoría de arquitectura:
«me voy a ir por muchas horas, ejecuta todo los planes pendientes al final revisamos». Por eso el
contrato se implementa **sin aprobación previa**: las decisiones D1–D13 quedan para que las vete al
volver, y nada se mergea a `main` hasta entonces (rama de integración `worktree-auditoria-refactors`).

Viene de la auditoría de arquitectura del núcleo event-sourced del mismo día (la que fijó el
trinquete de 500 líneas, `tests/test_tamano_archivos.py`). Encontró cinco problemas en
`commands/` y `doc/`; este plan toma cuatro:

- el estado de regeneración posicional,
- el despacho por flags,
- los params no estrictos,
- la clave de la caché de geometría.

El quinto (partir `registry.py`) va en un plan aparte; aquí sólo sale de `registry.py` lo que una
fase reescribe de todos modos.

Evidencia: el propio código se describe como «explosión combinatoria»
(`core/apolo/commands/registry.py:2257-2258`); el bump v4 de `GEOM_CACHE_EPOCH` llegó con meses de
atraso (`core/apolo/doc/geomcache.py:42-47`); el agente manda parámetros inexistentes que Apolo
ignora sin avisar (medido abajo).

## El problema / lo que hay hoy

### 1. El estado de regeneración es una 8-tupla posicional

`(scene, variables, joints, mates, constraints, fasteners, grounds, groups)` se arma, se desarma o
se mide en 14 sitios:

| dónde | qué |
|---|---|
| `core/apolo/doc/document.py:65-79` | `_copy_state` desarma y rearma por posición |
| `document.py:117` | `_regen_ckpts: dict[int, tuple]` |
| `document.py:156` y `:439-440` | sanidad: `len(st) == 8 and isinstance(st[0], dict)` |
| `document.py:244-245` | desarme desde el checkpoint |
| `document.py:249-251` | 8 dicts vacíos en orden |
| `document.py:260-264` | `execute_command` con 12 argumentos posicionales |
| `document.py:275-277` | captura del checkpoint |
| `document.py:279-281` | poda: 6 posicionales |
| `document.py:305-311` | volcado a `self` |
| `document.py:355` | siembra del open caliente |
| `core/apolo/doc/geomcache.py:157-158` | `pack` toma `state[0]` |
| `geomcache.py:208-218` | `unpack` valida `len(state) == 8` |
| `tests/test_geomcache.py:69` | `len(state) == 8` |

La firma de `execute_command` (`registry.py:2222-2235`) pone `attachments` ENTRE `joints` y `mates`:
otro orden que el de la tupla. Los 12 argumentos son dicts del mismo tipo: un cruce no lanza nada,
produce geometría equivocada. La raíz y `core/apolo/assembly/CLAUDE.md` documentan la «8-tupla»
como contrato.

### 2. El despacho elige la firma del executor por flags

`CommandSpec` (`registry.py:2037-2052`) tiene `kind` más 8 booleanos `wants_*`. `execute_command`
(`registry.py:2246-2278`) es una cadena de 11 ramas con 11 formas de llamada (9 posicionales, con
`cmd_id` en la 2.ª, 3.ª o 4.ª posición; 2 keyword-only). 15 de los 53 executors salen de la forma
por defecto `(scene, cmd_id, model)`. La precedencia es implícita (`pattern_group` funciona sólo
porque `joints and mates` se evalúa antes que `joints`, `:2263-2266`); una combinación de flags sin
rama propia cae en silencio en la primera que coincida, y nada lo valida al registrar.

### 3. Los params no son estrictos ni versionados

Ningún modelo fija `extra`: `_validate_model` (`registry.py:2184-2191`) DESCARTA en silencio toda
clave desconocida y usa el default.

Medido sobre `data/apolo.db` (abierta con `mode=ro`), validando cada comando con `extra="forbid"`
por llamada y sus variables resueltas:

| | documentos | comandos | con claves desconocidas |
|---|---:|---:|---:|
| proyectos | 25 | 2004 (+309 en el snapshot embebido del 53) | 8 (+6 en el snapshot) |
| revisiones | 97 | 21 850 | 96 |
| **total** | 122 | 23 854 | **104 (0,44 %)** |

- **`pattern_linear.name`**: 102 veces en 17 documentos (el proyecto 38 `faja-paqueteria-4m`, testigo
  del benchmark, y 16 revisiones). `pattern_linear` no tiene `name`: las copias se nombran solas
  (`registry.py:329`). El agente cree que nombra las copias, y no pasa nada.
- **`create_box.material`**: 2 veces, en el proyecto 65. El material es metadato (`set_material`),
  no param, y los tests lo copian (`tests/test_v65c_fixes.py:25-29`).
- Fuera de eso: 0 comandos que fallen la validación por otra causa, 0 tipos desconocidos.

Consecuencias: un typo del agente pasa verde con el default; renombrar un campo cambia en silencio
lo que hacen los logs viejos; no hay upcasters. Aparte, la validación de refs depende del catálogo
VIVO (`models.py:190-195`; el executor indexa `CATALOG[ref]`, `registry.py:1757`).

### 4. La caché de geometría no sabe qué executor cambió

`_cmd_sig` (`document.py:58-62`) es sha1(firma previa + id + params): no incluye el tipo ni una
versión del código. La vigencia depende de `GEOM_CACHE_EPOCH` (a mano) y de las versiones de
build123d, OCP y Apolo: un cambio en UN executor obliga a subir el epoch, que invalida TODOS los
proyectos. La tabla `geom_cache` guarda UNA fila por proyecto (`core/apolo/projects.py:48-53`) con el
checkpoint del último comando, y el open caliente exige que las firmas cacheadas sean PREFIJO del
log (`document.py:340-342`): la granularidad posible es por proyecto, no por entrada.

## Lo que se revisó antes de escribir esto

- **pydantic 2.13.4 (el del `.venv`) acepta `extra=` por llamada**: `Model.model_validate(raw,
  extra="forbid")` reporta en UNA pasada las claves de más en todos los niveles (`pos.q`, dentro de
  un `Vec3 | None`, `lst.0.k`), tipo `extra_forbidden`. Los `"=expr"` sin resolver dan
  `float_parsing` y se filtran. Las claves ignoradas no entran a `model_fields_set` (lo usa
  `drill_hole`, `registry.py:662`). → La entrada estricta NO toca los modelos ni el JSON Schema. El
  pin es `pydantic>=2.6` y hay que subirlo.
- **La UI devuelve enteros los params guardados** (`ui/src/forms/SchemaForm.tsx:569`, `:239-245`):
  editar c45 del 38 desde Propiedades reenviaría su `name`. → Sólo se rechaza la clave que el
  cliente INTRODUCE (D7).
- **Los tests parchean y espían el despacho** (`spec.executor` en caliente:
  `tests/test_geomcache.py:303-317`, `tests/test_torture.py:96-115`; espías de
  `apolo.doc.document.execute_command`). → El despacho lee `spec.executor` en cada llamada, y el
  regenerate sigue llamando una vez por comando a `document.execute_command`.
- **`commands` no puede importar `doc`** (`document.py:20` importa `registry`). → `RegenState` vive
  en `commands/`.
- **`transform_group` muta juntas y restricciones en sitio** (`registry.py:1423-1443`). → `copy()`
  conserva el `deepcopy` de todo lo que no es la escena, como `_copy_state`.
- **`insert_project` embebe un `.apolo`** cuyo replay corre executors que los params del anfitrión no
  nombran (`registry.py:1511-1519`). → La versión de un executor tiene que alcanzar al anfitrión (D9).
- **`ProjectStore.load` ESCRIBE la caché** (`projects.py:129-139`) y `paths.db_path()` crea
  carpetas. → El golden abre la SQLite por URI `mode=ro` y no usa ninguno de los dos.
- **Trinquetes**: `registry.py` 2299, `document.py` 1084, `models.py` 1509, `agent/agent.py` 606.
  Ninguno puede crecer: el código nuevo va a módulos nuevos, y F2 (que achica `registry.py`) va
  antes que F4.

## Decisiones (para vetar)

- **D1. Un golden de los proyectos guardados es el gate de cada fase.** `scripts/golden_regen.py`
  regenera en frío cada documento de una COPIA congelada de `data/apolo.db` y guarda una huella por
  documento: por feature (id, nombre, `command_id`, volumen, área, bbox, n.º de caras y aristas,
  `mesh_key`, `matrix`, anclas); juntas, mates, restricciones, fijadores, anclajes y grupos en JSON
  canónico; variables resueltas, `regen_suppressed`, integridad (sin «degradado») y la ÚLTIMA FIRMA
  del log. Cada fase compara contra la base de F0: cero diferencias, firmas incluidas.
  *Porqué*: «byte-idéntico para logs válidos», y los 1391 tests no cubren los 122 documentos reales.
- **D2. `RegenState` reemplaza a la tupla en todos lados.** Dataclass con `slots` y 8 campos con
  nombre, en `core/apolo/commands/state.py`; `copy()` = puerto 1:1 de `_copy_state`; el blob de la
  caché la guarda como dict POR NOMBRE (`to_plain`/`from_plain`). `GEOM_CACHE_EPOCH` 4 → 5, con su
  motivo: la ÚNICA invalidación del plan. *Porqué*: cruzar dos dicts pasa a ser un `AttributeError`
  al escribir el código, no geometría equivocada.
- **D3. Una sola convención: `executor(ctx: ExecContext, cmd_id, params)`.** `ExecContext(state,
  attachments)` expone los dicts VIVOS (`ctx.scene`, `ctx.joints`…) y `ctx.resolved_variables()`. Los
  helpers puros conservan sus argumentos. *Porqué*: una sola forma de llamada; agregar contexto deja
  de exigir un flag y una rama.
- **D4. Sin adaptadores generados desde los flags.** Los 15 executors con flags migran juntos en F2
  y los 8 `wants_*` se borran ahí; los 38 de forma `(scene, cmd_id, model)` pasan por UN adaptador
  de transición (`convention="scene"`) que F3 elimina. *Porqué*: 15 ediciones bajo el golden son
  menos riesgo que mantener la cadena de 11 ramas durante la migración.
- **D5. `CommandSpec` y el despacho salen de `registry.py`** a `core/apolo/commands/spec.py`
  (`__post_init__` que valida `kind`, `convention`, `version ≥ 1`; `run_executor(spec, ctx, cmd_id,
  model)` que lee `spec.executor` en cada llamada). En `registry.py` quedan `REGISTRY`,
  `validate_params` y un `execute_command(state, cmd_id, cmd_type, params, attachments=None)`
  delgado. Un test exige que cada executor reciba exactamente `(ctx, cmd_id, p)`.
- **D6. Entrada estricta y replay tolerante, con el MISMO modelo.** Entrada con `extra="forbid"` por
  llamada, contando sólo `extra_forbidden` (`core/apolo/commands/strict.py`), en las cuatro puertas
  de `Document` (`execute`, `edit`, `execute_many`, `edit_many` → cubren REST, lotes, jobs, preview y
  MCP) y en `validate_actions` del agente. El regenerate valida con `extra="ignore"` EXPLÍCITO. Los
  modelos no cambian. *Porqué*: «mutaciones estrictas, carga tolerante» ya es la regla de la casa.
- **D7. Sólo se rechaza lo que el cliente introduce.** Un edit rechaza
  `unknown_keys(nuevos) − unknown_keys(guardados)`, por ruta: una clave vieja ya guardada pasa y se
  queda. *Porqué*: la UI reenvía los params guardados.
- **D8. El rechazo enseña.** `CommandError` (→ 400, mismo texto en sync y en job) con el comando, la
  ruta de cada clave desconocida, las claves válidas de ese nivel y «¿quisiste decir…?» (difflib);
  `material` → `set_material`, `color` → `set_color`. En tuteo neutro.
- **D9. `CommandSpec.version: int = 1` entra a la firma SÓLO si es ≠ 1**: con todo en v1, `_cmd_sig`
  queda byte-idéntica. Subir la versión de X invalida sólo los proyectos que contienen X. Los
  comandos COMPUESTOS (`composite=True`; hoy `insert_project`) llevan en su firma el resumen de TODAS
  las versiones ≠ 1.
- **D10. La regla del epoch queda escrita así** (raíz § Log, `commands/CLAUDE.md`, `doc/CLAUDE.md`):
  cambiaste la geometría de UN executor con los mismos params → sube su `version`; algo compartido y
  puedes nombrar todos sus usuarios → sube la versión de cada uno; algo que no puedes acotar (kernel,
  builders, YAML del catálogo, `Feature`, `RegenState`, formato del blob) → bump de
  `GEOM_CACHE_EPOCH`; la etapa final del regenerate (mates, grupos, visibilidad) → nada (no se cachea).
- **D11. Trinquete de versiones (extra, vetable).** `tests/test_contrato_comandos.py` guarda
  `{tipo: (version, sha1 del código del executor)}`: si el código cambió y la versión no, falla y
  obliga a elegir (subir la versión, o actualizar sólo el hash si fue un refactor).
- **D12. Ningún campo desaparece sin upcaster (extra, vetable).** El mismo archivo guarda las rutas
  de campos de cada comando: quitar o renombrar un campo falla con un mensaje que pide conservarlo o
  escribir un upcaster.
- **D13. Los logs guardados no se tocan.** Las 104 claves viejas se quedan y el replay las sigue
  ignorando; `pattern_linear` no gana `name` ni `create_box` gana `material`.

## Alternativas descartadas

- `NamedTuple` para el estado: sigue permitiendo desarmar por posición.
- `RegenState` en `doc/`: import circular con `document.py:20`.
- `extra="forbid"` en los modelos + recorrido que limpie en el replay: los 104 comandos dependerían
  de ese recorrido y el JSON Schema publicado cambiaría.
- `model_validator(mode="before")` con flag: cambia la base de ~60 clases de `models.py`.
- Estricto sólo en la capa API: deja afuera al agente de la app y al preview.
- Limpiar la clave vieja al editar: reescribe el log en silencio.
- Versión por registro + upcasters desde ya: cambia el formato del log por cero renombres pendientes.
- Versión automática (hash del código) en la firma: un comentario invalidaría la caché.
- Adaptadores generados desde los flags para los 53 executors.
- Caché con varios checkpoints: otra decisión, fuera de este plan.

## Fases

Cada fase la implementa un subagente opus en su worktree. Desde un worktree:
`$env:PYTHONPATH = "$PWD\core"` y `python -B`. Ninguna fase toca `ui/`.

**Gate común de F1 a F5**: pytest completo verde; golden contra la base de F0 con cero
diferencias; `tests/test_tamano_archivos.py` verde (números que bajan, actualizados en el mismo
commit); ningún archivo nuevo de más de 500 líneas.

- **F0 — mide (sólo lectura, S · `scripts/`, `tests/`).** `scripts/golden_regen.py` (≤ 300 líneas):
  `--freeze DESTINO` (copia con la API de backup de `sqlite3` desde `file:…?mode=ro` a
  `$env:TEMP\apolo-golden\`; la SQLite de Mario nunca se abre en escritura), `--db COPIA --out
  base.json [--revisions]` (huella de D1 con `Document.from_apolo_bytes(tolerant=True)` en frío;
  limpia `DEFINITIONS` y la caché de `doc/subproject.py` antes de cada documento; no importa
  `ProjectStore` ni `paths`), `--compare A B` (diff legible, código ≠ 0 si difiere), `--scan-keys`.
  `tests/test_golden_regen.py`: dos documentos en una SQLite de `tmp_path`; huellas idénticas → sin
  diff; un param cambiado → diff. Verifica: dos corridas seguidas dan cero diferencias; bitácora con
  cantidad de documentos, tiempo, suprimidos y la tabla de `--scan-keys`.
- **F1 — `RegenState` (M · `commands`, `doc`).** `commands/state.py`; los sitios de la tabla en
  `document.py`; `pack`/`unpack` por nombre y epoch 5; `execute_command(state, cmd_id, cmd_type,
  params, attachments=None)` con el cuerpo de ramas intacto; tests de aislamiento de `copy()`,
  shape compartido (`is`) y blob v4 → `unpack` None; «8-tupla» → `RegenState` en los CLAUDE.md.
- **F2 — despacho único (M · `commands`).** `ExecContext` en `state.py`; `CommandSpec` +
  `run_executor` en `spec.py`; migra los 15 executors con flags y borra los 8 `wants_*`; test de
  firmas. `registry.py` baja ≈ 60 líneas.
- **F3 — los 38 restantes (M, mecánica · `commands`).** `scene` → `ctx.scene`; se borran
  `convention` y la rama `scene`. `registry.py` no crece.
- **F4 — entrada estricta (M · `commands`, `doc`, `agent`, `core/pyproject.toml`).**
  `commands/strict.py` (D6–D8); `validate_params(…, strict=False, previous=None)`; `_validate_model`
  con `extra` explícito; las cuatro puertas y `validate_actions`; pin de pydantic; trinquete de rutas
  (D12). Tests `tests/test_params_estrictos.py` (anidadas, listas, `Optional`, lote revertido sin undo
  fantasma, edit con y sin merge, caso c45 → 200, log viejo regenera igual, preview, agente, texto
  con sugerencia y puntero a `set_material`). Los tests que mandaban claves inexistentes se corrigen
  como bug del TEST (al menos `tests/test_v65c_fixes.py:25-29`), listados en la bitácora.
- **F5 — versión por comando (S · `commands`, `doc`, `tests`, CLAUDE.md).** `CommandSpec.version` y
  `composite`; etiqueta en `_cmd_sig` (D9); trinquete D11. Tests: `version=2` por monkeypatch cambia
  las firmas desde su primer comando y no las de un proyecto que no lo usa; `insert_project` cambia
  con cualquier versión ≠ 1; un blob v1 se descarta en el open. Regla D10 en los CLAUDE.md.
- **F6 — verifica (S).** Golden COMPLETO (proyectos y revisiones) sobre una copia FRESCA de la base;
  `pytest -m torture`. **Ajuste por la delegación**: el E2E no usa la API de Mario ni su base; corre
  con una API levantada desde el worktree de integración en el puerto 8001 sobre una COPIA de
  `data/apolo.db` puesta en el `data/` del worktree (ignorado por git): abrir el 38 dos veces (frío
  con epoch 5, luego caliente con 0 replays), editar c45 → OK, `run_command` de `pattern_linear` con
  `name` → 400 con las claves válidas, `run_batch` con `create_box.material` → el job falla con el
  mismo texto y el puntero a `set_material`. Al cerrar: conteos de «Estado actual», backlog,
  bitácora y frontmatter.

## Lo que este plan NO hace

- No parte `registry.py` (Feature/DEFINITIONS, colocación, helpers vectoriales duplicados en
  `assembly/mates.py` y `robotics/urdf.py`, juntas, `join_bolted`, `transform_group`/`insert_project`,
  super-comandos): va al plan de partición. Aquí sólo sale el bloque de despacho (D5).
- No cambia el formato del `.apolo` ni del log, ni reescribe comandos guardados (D13).
- No agrega `name` a `pattern_linear` ni `material` a `create_box` (va al backlog como decisión).
- No escribe upcasters (0 renombres pendientes).
- No toca la dependencia del catálogo vivo (las refs no se borran; va al backlog).
- No revisa claves dentro de los campos libres `sketch: dict` ni de `overrides`.
- No publica `additionalProperties: false` en los schemas.
- No hace la caché más fina que por proyecto ni agrega un hash del catálogo a `_versions()`.
- No unifica `SubprojectState` (`doc/subproject.py:33-43`) con `RegenState`.

## Riesgos

- **`copy()` comparte por error un dict mutable** → puerto 1:1 de `_copy_state`, test de
  aislamiento campo por campo y el golden.
- **El golden da falso verde o falso rojo** → test con diferencia inyectada; doble corrida en F0;
  copia congelada; `DEFINITIONS` y caché de subproyectos limpias antes de cada documento.
- **El golden escribe la SQLite de Mario** → sólo URI `mode=ro`, sin `ProjectStore` ni `paths`, sobre
  una copia.
- **La estrictez rompe clientes** (el agente manda `pattern_linear.name` por costumbre) → D8, D7 y
  revisar `logs/errors.log` en el «revisa» siguiente.
- **Usuarios de PyPI con pydantic viejo** → subir el pin.
- **Los parches de los tests se saltan el despacho nuevo** → `run_executor` lee `spec.executor` en
  cada llamada.
- **El número del trinquete choca entre fases o con el plan de partir `main.py`** → orden F2 → F4,
  número actualizado en el mismo commit, rebase justo antes de cada merge.
- **D11 molesta en los refactors** → el mensaje distingue las dos salidas; es vetable.
- **La partición futura mueve `Feature`** (el pickle del blob resuelve
  `apolo.commands.registry.Feature`) → ese plan bumpea el epoch o deja un re-export.
- **Se olvida subir una versión al cambiar un helper compartido** → la regla D10 en la raíz y en
  `commands/CLAUDE.md`.

## Bitácora

**2026-10-03 — F0, mide.** `scripts/golden_regen.py` (300 líneas) y `tests/test_golden_regen.py`
(4 tests: dos corridas sobre la misma base → sin diferencias; un `width` cambiado en un proyecto
→ el diff nombra ESE documento, su `volume` y su `last_sig`, y no los otros; `--freeze` no toca
el origen y la copia da la misma huella; `--scan-keys` encuentra `pattern_linear.name`).

- **Copia congelada**: `%TEMP%\apolo-golden\copia-f0.db` (API de backup desde `file:…?mode=ro`;
  25 proyectos, 97 revisiones). SHA-256 y mtime de `data/apolo.db` idénticos antes y después
  (`1119258C…`, 13:10:35); sin `-wal`/`-shm`.
- **Base**: `%TEMP%\apolo-golden\base-f0-a.json` (7,3 MB, fuera del repo). Corrió sobre una copia
  del código de `725aedf` (`%TEMP%\apolo-golden\code-f0`, con `PYTHONPATH` a esa carpeta), para
  que escribir F1 en el worktree mientras corría no la contaminara.
- **Números**: 122 documentos · 23 854 comandos · 6 738 sólidos · 1 257,8 s (21 min) · 0 errores
  · integridad limpia en los 122. Suprimidos en UN documento: la revisión 60 (60 entradas:
  `create_take_up` y `create_drive_roller` con «Voladizo mínimo 45 mm» y, en cascada, 58
  `fasten` que apuntaban a sus piezas). Es un log viejo que el executor de hoy rechaza; la carga
  tolerante lo abre igual. Los más lentos: revisiones 83 y 84 (189 y 171 s), proyecto 67 (145 s),
  proyecto 66 (91 s), revisión 103 (78 s).
- **Determinismo**: segunda corrida (`base-f0-b.json`, ya con el script recortado a 300 líneas:
  prueba de paso que el recorte no cambió la huella) → `--compare`: **sin diferencias**.
- **`--scan-keys`** (12,5 s; reproduce la tabla de «El problema» §3):

  | | documentos | comandos | con claves desconocidas | fallan por otra causa | tipo desconocido |
  |---|---:|---:|---:|---:|---:|
  | proyectos | 25 | 2 004 | 8 | 0 | 0 |
  | snapshots embebidos | 2 | 618 | 12 | 0 | 0 |
  | revisiones | 97 | 21 850 | 96 | 0 | 0 |

  | clave desconocida | veces | documentos |
  |---|---:|---:|
  | `pattern_linear.name` | 114 | 18 |
  | `create_box.material` | 2 | 1 |

  El snapshot embebido cuenta POR INSTANCIA: el 53 inserta dos veces el 38 (618 = 2 × 309 y
  12 = 2 × 6); por eso aquí son 114 = 102 + 12 y 18 documentos (el 53 entra por sus snapshots).

**Desvíos de F0**: la huella es un SUPERCONJUNTO de D1 (además: `component`, `cut_length`, `miter`,
`material`, `group`, `visible`, `is_guide` y el orden de la escena), sin costo y con más poder de
detección. Los floats se redondean a 10 cifras significativas (y |x| < 1e-9 → 0): inmune al
ruido de último bit, sensible a cualquier cambio real (1e-6 mm en una cota de 4 m). Los tiempos
van en `meta`, que `--compare` ignora. `--src` es explícito porque desde un worktree el
`data/apolo.db` por defecto no existe. Conteo de tests de la raíz: 1391 → 1395.

**2026-10-03 — F1, `RegenState`.** `core/apolo/commands/state.py` (72 líneas): dataclass con
`slots` y los 8 campos con nombre, en el orden de la vieja tupla; `copy()` es el puerto 1:1 de
`_copy_state` (que se borra); `to_plain`/`from_plain` por nombre (`from_plain` exige EXACTAMENTE
los 8 campos, todos dicts). Los 14 sitios de la tabla: en `document.py`, `_regen_ckpts` tipado,
`_ckpts_ok` y `check_integrity` validan `RegenState` con escena dict, `regenerate` arranca de
`ckpts[resume].copy()` o de `RegenState()`, ejecuta, captura `state.copy()`, poda con
`_prune_or_raise(state, tolerant, suppressed)` y vuelca por nombre; el open caliente siembra el
`RegenState` del blob. En `geomcache.py`, `pack` copia con `ckpt.copy()` y guarda
`state.to_plain()`; `unpack` reconstruye con `from_plain` (otro formato → `ValueError` → None).
`execute_command(state, cmd_id, cmd_type, params, attachments=None)` desarma el estado en
locales al entrar y deja las 11 ramas intactas. `GEOM_CACHE_EPOCH` 4 → 5, con su línea en el
historial. «8-tupla» → `RegenState` en la raíz y en `assembly/`; `doc/` gana una línea (el blob
guarda el estado por nombre; cambiar sus campos = bump) y `commands/` nombra `state.py`.

- **Tests**: `tests/test_regen_state.py` (9): campos y orden; un campo inventado lanza
  `AttributeError`; `copy()` aísla campo por campo (Feature distinta, variables propias, los seis
  restantes en copia profunda, mutación anidada incluida); el shape se comparte por `is` (también
  en copia de copia y entre el checkpoint y la escena); `to_plain`/`from_plain` ida y vuelta y
  rechazo de 6 formas malas; `execute_command` con la firma nueva; un blob v4 (epoch 4 + tupla)
  → `unpack` None, también con el epoch de hoy o sin `groups`, y el open con ese warm da el
  documento correcto; un checkpoint con tupla en memoria → `check_integrity` lo marca y el edit
  siguiente replaya completo. `tests/test_geomcache.py`: `isinstance(state, RegenState)`.
- **Golden** (`%TEMP%\apolo-golden\golden-f1.json`, código del worktree, 1 452,9 s) contra la
  base de F0: **sin diferencias** en los 122 documentos, firmas incluidas.
- **Suite**: 1404 tests (1391 + 4 de F0 + 9 de F1): 1403 pasan y 1 se salta, 497 s.
  De la tortura extendida se corrieron las 7 que tocan caché y regenerate (`geomcache`,
  `big_model_cold`, `fuzz_strict`): verdes; la completa queda para F6. **Líneas**: `document.py`
  1084 → 1060 y `registry.py` 2299 → 2286 (trinquete actualizado); `geomcache.py` 228 → 231.

**Desvíos de F1**: `_try_warm` rechaza un estado que no sea `RegenState` (antes lo sembraba y
`_ckpts_ok` lo descartaba en el regenerate siguiente: mismo efecto, un paso antes y explícito).
`execute_command` mantiene la cadena de ramas leyendo de locales, no de `state.campo`, para que
el cuerpo quede literalmente igual (F2 lo reemplaza).

**2026-10-03 — F2, despacho único.** `ExecContext(state, attachments)` en `commands/state.py`
(frozen, slots; una propiedad por campo del `RegenState` que devuelve el dict VIVO, y
`resolved_variables()`). `commands/spec.py` (55 líneas): `CommandSpec` con `__post_init__` que
rechaza `kind`/`convention` inválidos y un executor no invocable, y `run_executor` que lee
`spec.executor` en cada llamada. `execute_command` queda en 3 líneas (valida, arma el contexto,
despacha). Los 15 executors con forma propia —los 14 con flags y `set_variable` (`kind="vars"`
le pasaba las variables crudas)— migran a `(ctx, cmd_id, p)` con `convention="ctx"`; los 8
`wants_*` y la cadena de 11 ramas se borran. Los helpers (`_register_joint`, `_joint_drag`,
`_insert_project_precheck`) conservan sus argumentos. Los 38 restantes van por el adaptador
`convention="scene"` (default).

- **Tests**: `tests/test_despacho_unico.py` (11): firma exacta por convención para los 53, los
  15 migrados son `ctx`, no queda `wants_*` (ni como atributo ni como kwarg aceptado),
  `CommandSpec` valida al registrar, un executor parcheado se ve en el despacho, `ExecContext`
  entrega los dicts vivos (identidad, frozen, adjuntos `{}` por defecto), `run_executor`,
  `run_script` sigue viendo `V[...]` e `import_step` sus adjuntos. `test_T9` de la tortura
  llamaba a `_exec_insert_project` con la firma kwargs: ahora le pasa un `ExecContext`.
- **Golden** (`%TEMP%\apolo-golden\golden-f2.json`, código del worktree, 1 434,1 s) contra la
  base de F0: **sin diferencias** en los 122 documentos, firmas incluidas.
- **Suite**: 1539 tests (1528 de la base de integración + 11): 1538 pasan y 1 se salta. Ruff
  limpio. **Líneas**: `registry.py` 2286 → 2229 (trinquete actualizado); `state.py` 72 → 126.

**Desvíos de F2**: la validación `version ≥ 1` de D5 llega con el campo, en F5. El adaptador de
transición es el DEFAULT (`convention="scene"`) y los 15 migrados lo declaran: así la F2 no
toca las 38 entradas que la F3 reescribe de todos modos.

**2026-10-03 — F3, los 38 restantes.** Migración MECÁNICA con un script sobre el AST, no con
reemplazo de texto: en cada executor registrado con `convention="scene"` cambia
`scene: Scene` → `ctx: ExecContext` y cada `Name` `scene` de lectura del cuerpo → `ctx.scene`;
aborta si la firma no era exactamente `(scene, cmd_id, p)`, si un nombre `scene` se ASIGNA o
si una función anidada o lambda declara un parámetro `scene`. 97 ediciones (38 firmas, 59
usos; `boolean_op` el que más, 5). Los helpers (`_require`, `_instanced`, `_world_move`,
`_exec_snap_face`, que no está registrado) conservan su `scene`. Se borran `convention`,
`CONVENTIONS` y la rama del adaptador: `run_executor` queda en una línea. Una sola línea pasó
de 100 columnas (`create_cylinder`) y se rehizo sin sumar líneas.

- **`registry.py` no crece**: al soltar `convention="ctx"`, las entradas del `REGISTRY` que
  caben en una línea (≤ 100 columnas) o en tres se compactan: 2229 → 2212 (trinquete
  actualizado). `spec.py` 55 → 44.
- **Tests**: `tests/test_despacho_unico.py` (10): los 53 reciben EXACTAMENTE `(ctx, cmd_id,
  p)`; `CommandSpec` rechaza `wants_*` y `convention` (TypeError) y un `kind` inválido.
- **Golden** (`%TEMP%\apolo-golden\golden-f3.json`, 1 215,9 s) contra la base de F0: **sin
  diferencias** en los 122 documentos, firmas incluidas.
- **Suite**: 1538 tests (los 11 de F2 pasan a 10): 1537 pasan y 1 se salta. Ruff limpio.

**Desvíos de F3**: ninguno de contrato. Los executors migrados en F2 conservan sus alias
locales (`scene = ctx.scene` donde se usa muchas veces); los 38 de F3 usan `ctx.scene` en
línea, que es lo que permitió no sumar líneas.

**2026-10-03 — F4, entrada estricta.** `core/apolo/commands/strict.py` (175 líneas):
`unknown_paths(model, params)` valida con `extra="forbid"` POR LLAMADA y se queda sólo con los
`extra_forbidden` (todas las rutas en una pasada: raíz, anidadas, en listas, dentro de un
`X | None`); `reject_unknown(spec, params, previous)` resta las rutas que ya estaban guardadas
(D7) y lanza `CommandError` con `rejection_text` (D8). `validate_params(…, strict=False,
previous=None)` y `_validate_model` con `extra="ignore"` EXPLÍCITO. Las puertas: `execute` y
`edit` por `validate_params(strict=True)` (el edit con `previous` = los params guardados);
`execute_many` revisa las claves de TODAS las acciones antes del snapshot (sólo claves: las
variables que el lote define aún no existen, y no se reintroduce `validate_params` en el
bucle); `edit_many`, dentro del try (rollback total, sin undo fantasma); el preview pasa por
el `execute_many` de su copia; `validate_actions` del agente, con `strict=True`.

- **Texto del rechazo** (el c45 del 38 mandado como entrada nueva):
  `Parámetro desconocido en pattern_linear (no se aplicó nada):` /
  `- «name» no existe. Válidos en ese nivel: feature, count, spacing.` Con typo:
  `«widht» no existe; ¿quisiste decir «width»?`; con metadato: `«material»: el material no es
  un parámetro; asígnalo con set_material a la pieza ya creada.` Mismo texto en sync y en job
  (test).
- **Pin `pydantic>=2.12`**: `extra=` en las funciones de validación llegó en 2.12.0 (changelog
  oficial, #12233; 2.13.0 sólo arregla la igualdad con `extra` en tiempo de ejecución, que
  aquí no se usa). Probado instalando 2.12.0 en una carpeta temporal: misma detección (649
  rutas, mismo hash) y `test_params_estrictos` + `test_contrato_comandos` verdes.
- **Trinquete D12** (`tests/test_contrato_comandos.py`): `CAMPOS` declara las 649 rutas de los
  53 comandos (`strict.field_paths`); falla si una desaparece (pide conservarla o un upcaster)
  o si aparece una sin declarar; `python tests/test_contrato_comandos.py` imprime el literal.
- **Hallazgo**: `snap_to` anota `cara: "EdgeSelector | None"` con un string → el modelo queda
  INCOMPLETO hasta su primera validación y su anotación es un `ForwardRef`. `field_paths` y
  `model_at` hacen `model_rebuild()` antes de leer campos: sin eso el trinquete no veía 22
  rutas de `snap_to` (la detección no lo sufría: valida, y validar completa el modelo).
- **Tests corregidos como bug del TEST** (mandaban claves que el comando nunca tuvo y el
  replay ignoraba): `tests/test_v65c_fixes.py:25-29` (`create_box.material` ×2: el acero ya
  era el default, la escena no cambia); `tests/test_physics.py:81` (`create_box.length`: la
  mesa quedaba de 400×100 en vez de la 1000×400 que el test describe → `width`/`depth`);
  `tests/test_jobs.py::test_command_error_in_job_is_400` (`fillet.feature_id`: el 400 venía
  de la clave mal escrita, no del executor; ahora `feature` y verifica que el error nombra la
  pieza). `tests/test_golden_regen.py::_doc_b` no era un bug: necesita un log VIEJO con
  `pattern_linear.name`, que ahora inyecta en el log después de crear el comando.
- **Cómo se encontraron**: un plugin de pytest FUERA del repo envolvió `rejection_text` y anotó
  cada rechazo con su test; fuera de `test_params_estrictos`, sólo saltó el de `test_jobs`
  (que pasaba igual, porque el 400 lo daba la clave). Los otros cuatro fallaban a la vista.
- **Tests**: `tests/test_params_estrictos.py` (18: detección en todos los niveles, `=expr` sin
  resolver, campos libres, texto con sugerencia y punteros, REST, lote revertido sin undo
  fantasma, lote con sus propias variables, job con el mismo texto, preview, c45 → 200 por
  PUT/merge/PATCH, edit y edit_many que introducen una clave, log viejo que regenera igual,
  agente) y `tests/test_contrato_comandos.py` (3).
- **Golden** (`%TEMP%\apolo-golden\golden-f4.json`, código congelado en `code-f4`, 1 011,7 s)
  contra la base de F0: **sin diferencias** en los 122 documentos, firmas incluidas.
- **Suite**: 1649 tests (1628 de la base + 21): 1648 pasan y 1 se salta. Ruff limpio.
  **Líneas**: `registry.py` 2212 → 2211 (trinquete actualizado); `document.py` 1060 = 1060
  (los docstrings de `execute_many`/`edit_many`/`edit` se reescribieron más cortos);
  `agent.py` 606 =.

**Desvíos de F4**: `CommandError` se mudó a `commands/errors.py` (re-exportado por `registry`,
mismo objeto): `strict.py` lo lanza y `registry.py` importa `strict.py`; sin el mudado, import
circular. Un tipo desconocido en un lote no lo mira la entrada estricta: lo sigue reportando el
regenerate con el texto de siempre. Los punteros de `material`/`color` valen en cualquier nivel.

**2026-10-03 — F5, versión por comando.** `CommandSpec.version: int = 1` (`__post_init__`
rechaza lo que no sea un entero ≥ 1, `bool` incluido) y `composite: bool = False` (`True` sólo
en `insert_project`). `spec.version_tag(registro, tipo)` da `""` si el comando está en v1, si
no `"|v:tipo@N"`; un compuesto lleva las ≠ 1 de TODO el registro, ordenadas. `_cmd_sig` hace
`h.update(version_tag(...).encode())`: con todo en v1 es `update(b"")`, que no mueve el sha1 →
firma byte-idéntica a la histórica (un test la recalcula con la fórmula vieja, y el golden).
Regla D10 escrita en la raíz (§ Log de comandos), `commands/CLAUDE.md` y `doc/CLAUDE.md`; el
comentario del epoch en `geomcache.py` deja de pedir un bump por UN executor.

- **Trinquete D11** (`tests/test_contrato_comandos.py`): `VERSIONES = {tipo: (version,
  huella)}`, huella = sha1 (16 hex) de `inspect.getsource` del executor con los saltos de línea
  normalizados. Falla si el código cambió y la versión no, si la versión subió sin declararse,
  si bajó, o si un comando aparece o desaparece; el mensaje da las dos salidas (subir la
  versión, o sólo la huella si fue un refactor). Un test con un registro falso recorre cada
  salida.
- **Tests**: `tests/test_version_comandos.py` (11): en v1 la firma es la fórmula histórica;
  `version=2` por monkeypatch cambia las firmas DESDE el primer comando de ese tipo (las
  anteriores quedan iguales) y no las de un proyecto que no lo usa; `insert_project` cambia con
  cualquier versión ≠ 1 (`|v:fillet@3`) y un `create_box` no; un blob empacado en v1 se
  descarta en el open (replay frío de los 5 comandos) mientras el proyecto sin cilindros sigue
  abriendo caliente (0 replays); `version` 0, −1, `True`, 1.5 y "2" se rechazan al registrar.
  `tests/test_contrato_comandos.py` suma 2 (D11).
- **Golden** (`%TEMP%\apolo-golden\golden-f5.json`, código congelado en `code-f5`, 885,5 s)
  contra la base de F0: **sin diferencias** en los 122 documentos, firmas incluidas.
- **Suite**: 1662 tests (1649 + 13): 1661 pasan y 1 se salta, 393 s. Ruff limpio.
  **Líneas**: `document.py` 1060 = 1060 (el comentario del bloque de firmas se compactó);
  `registry.py` 2211 =; `spec.py` 44 → 68.

**Desvíos de F5**: la huella de D11 es la de la función del executor, no la de sus helpers
(declarado en el test; un helper compartido es la regla D10). `version_tag` vive en `spec.py` y
recibe el registro (`spec.py` no importa `registry.py`).
