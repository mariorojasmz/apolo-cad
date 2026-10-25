---
estado: en curso
nota: contrato de Claude con el aval del titular (2026-10-24: «aborda los puntos débiles … procede según tu criterio»); F0 medida sobre `1f01d0a`; sigue F2 (models), luego F1 (MCP, después de que entre V8.9 F6) → F3 → F4 → F5 → F6
descripcion: por fuera nada cambia —mismos comandos, mismas tools MCP, mismos proyectos y la misma caché de geometría—; por dentro los cuatro archivos más tocados del núcleo quedan en módulos de ≤ 500 líneas y dos sesiones ya no chocan en el mismo archivo
---

# Partir el núcleo congelado — registro, modelos, documento y MCP se tocan por partes, sin vencer la caché de nadie

## Estado y origen

- El titular, 2026-10-24: «aborda los puntos débiles … procede según tu criterio». El contrato
  es de Claude con ese aval; D1–D12 se pueden vetar por número.
- Evidencia: `tests/test_tamano_archivos.py:51-60` congela ocho archivos por encima del tope de
  500 líneas; cuatro son el núcleo por donde pasa casi todo cambio: `commands/registry.py`
  (1 912), `mcp_server.py` (1 366), `commands/models.py` (1 183) y `doc/document.py` (1 009).
  En 30 días hubo **61 commits** sobre esos cuatro (registry 23, mcp_server 32, document 19,
  models 6), varios el mismo día: por eso chocan las sesiones paralelas.
- La raíz (§ Escala): «partir un archivo grande se hace con un plan». Sigue el patrón de
  [partir-api-main](partir-api-main.md): cortar y pegar con un script, mover por nombre,
  re-exportar por identidad, una fase por bloque.
- Borrador medido por un sub-agente de sólo lectura; revisado y decidido por la sesión
  principal (§ Decisiones, al final).

## El problema / lo que hay hoy

Medido sobre `1f01d0a`.

- **`commands/registry.py` (1 912)** mezcla cinco cosas:
  - el tipo de la escena: `Feature` (`:95-125`), `DEFINITIONS` y su LRU (`:127-150`), `_require`,
    `_instanced`, `_orient_axis` (`:156-192`);
  - 48 executors con sus helpers (primitivas `:195-228`, colocación `:230-322`, patrones y
    borrado `:324-424`, modelado directo `:426-553`, frame de cara y taladro `:555-699`, patrón
    circular y espejo `:701-744`, croquis y superficies `:746-914`, juntas, mates y grupos
    `:916-1101`, `transform_group` `:1103-1207`, `insert_project` `:1209-1402`, `add_joinery`
    `:1404-1486`, brazo y script `:1488-1514`, attach y snap `:1516-1626`, transportador,
    bastidor, esqueleto y chapa `:1628-1733`);
  - el `REGISTRY` literal (`:1736-1846`, 62 comandos en un orden que la UI y los schemas
    publican);
  - el despacho y los schemas (`:1849-1912`).
  Lo importan ~90 archivos: `REGISTRY` (39), `CommandError` (28), `Feature` (13), `DEFINITIONS`
  (10), `validate_params` (10).
- **`mcp_server.py` (1 366)**: infraestructura (`_api`, `_reject`, `_submit_and_wait`,
  `_mutacion`: `:37-101`) y **76 tools** en línea (`:105-1346`) por secciones (consulta,
  modelado, validación, proyectos, introspección, topología, despiece, visibilidad,
  expresiones, FEA). Las otras 14 ya viven en `tools/` y se registran al final (`:1349-1357`),
  con `extensiones.registrar_tools(mcp, globals())` siempre último.
- **`commands/models.py` (1 183)**: 70 nombres de nivel superior (la base `_floor_to_int`,
  `Vec3`, `Rot3`, las listas de catálogo, y los params pydantic de todas las familias). Ya
  re-exporta `models_selectores`, `models_union` y, perezoso, `models_componente` (`:175-182`).
- **`doc/document.py` (1 009)**: una sola clase de 962 líneas que mezcla undo (`:87-109`,
  `:852-881`), regenerate incremental (`:111-277`), open caliente (`_try_warm`, `:279-311`),
  integridad (`check_integrity`, `:314-419`), modo estricto y mutaciones (`:421-636`),
  metadatos del manifest (`:638-849`) y persistencia `.apolo` (`:884-1009`).

## Lo que se revisó antes de escribir esto

- **La huella de un executor** (→ D3): `contrato_comandos.huella` (`:34-38`) es el sha1 de
  `inspect.getsource(fn)`: sólo el TEXTO de la función (CRLF normalizado), sin módulo ni línea.
  Mover una función byte a byte deja su huella igual (precedente: cadenas-pinones D8,
  `exec_rodillos.py:3-4`). **La huella no indexa la caché**: la firma (`_cmd_sig`) es params +
  `version` ≠ 1; sólo una `version` o `GEOM_CACHE_EPOCH` que suben vencen la caché de los
  usuarios.
- **Seis executors ajenos importan de `.registry` DENTRO de su cuerpo** (→ D2, D3):
  `cilindro.py:36`, `exec_faja.py:41`, `exec_rodillos_cadena.py:50`, `exec_transmision.py:324`,
  `exec_union.py:254`, `tablero.py:155`. Esas líneas son parte de sus huellas: `registry` debe
  seguir exportando esos nombres para siempre. Más imports perezosos fuera de executors:
  `exec_union.py:183`, `exec_transmision.py:289`, `union_taller.py:180,214`,
  `exec_componente.py:27`, `exec_rodillos.py:19`, `tablero.py:49`.
- **La caché de geometría picklea instancias de `Feature`** (`geomcache.py:123-158`): el blob
  nombra `apolo.commands.registry.Feature`. `unpack` nunca lanza (`None` → replay frío) y la caché
  no es autoritativa. Ningún otro pickle persiste.
- **Lo que los tests REASIGNAN** (→ D2): `docmod.execute_command` (8 sitios), `docmod.resolve_all`
  (2), `docmod._STRICT` (4), `registry_mod.run_executor` (5), `Document._restore` (1),
  `mcp_server._api`/`APOLO_URL`/`APOLO_MCP_WAIT_S` (~18). Lo leen `regenerate`,
  `check_integrity`, `_check_strict` y `execute_command`.
- **Los tests llaman tools como atributos del módulo** (`mcp_server.check_assembly()`,
  `gravity_test`, `get_connections`, `engineering_check`, `redo`, `undo`, `get_job`,
  `run_command`, `run_batch`, `edit_batch`, `set_variable`).
- **El golden MCP congela el ORDEN** (→ D5): `tests/data/mcp_golden/list_tools.json` (90, en
  orden de registro), comparado byte a byte por `test_mcp_golden.py`.
- **Ningún cuerpo de tool tiene un string multilínea que no sea docstring** (AST): re-indentar
  los cuerpos no cambia salidas; los docstrings pasan por `inspect.cleandoc`
  (`tools/fastmcp_limpio.py`).
- **Contrato con extensiones**: `extensiones_api.SUPERFICIE` nombra
  `apolo.commands.registry:Feature`, `apolo.commands.models:Vec3`, `apolo.doc.document:Document`;
  `MODULOS`, `apolo.doc.document: ("Document",)`. Quitar uno sube `CONTRATO_EXTENSIONES`.
- **`Document.preview` construye `Document(...)` por nombre** (`document.py:579`); las anotaciones
  `-> "Document"` (`:924`, `:1008`) son strings que ruff F821 revisa.
- **Ciclos**: hoy se evitan con imports perezosos hacia `.registry`; `models_*` importan
  `Vec3`/`Rot3` de `.models`.
- **Ningún archivo se busca por su ruta** ni hay `getmembers`/`vars()`/`dir()` sobre estos
  módulos. Precedente de mixins: `plc/compilador_expr.py:64`, `plc/compilador_sent.py:31`.
- Herramientas que ya existen: `scripts/golden_regen.py` (regenera en frío cada documento de una
  COPIA de la SQLite y guarda la última firma), `scripts/e2e_mcp.py`,
  `python tests/test_contrato_comandos.py`.

## Decisiones (para vetar)

- **D1 — Refactor PURO: cortar y pegar por script, sin «mejorar».** Cada fase escribe un script
  (en el scratchpad, no se commitea) que mueve definiciones de nivel superior (o métodos) por
  NOMBRE, en su orden original y byte a byte; otro compara el `inspect.getsource` de cada
  definición antes y después. Excepciones, lista CERRADA: (a) F1, los cuerpos de tool ganan 4
  espacios de sangría (se comparan docstring por `cleandoc` y el resto por `ast.dump`); (b) F5,
  `check_integrity` lee `resolve_all` por el módulo `document` (D2); (c) un `TYPE_CHECKING` para
  las anotaciones `"Document"`; (d) las líneas de import. Nada se renombra, se tipa ni se
  reordena por dentro.
- **D2 — Las rutas viejas siguen sirviendo, por IDENTIDAD, para siempre (shim).** `registry`,
  `models` y `document` re-exportan TODO nombre de nivel superior que hoy definen (88, 70 y 5);
  `mcp_server` re-exporta las 76 tools que hoy tiene en línea y conserva `_api`, `_reject`,
  `_submit_and_wait`, `_mutacion`, `_paso`, `APOLO_URL`, `APOLO_MCP_WAIT_S`, `_scene_brief`,
  `_one_or_many`, `_job_receipt`, `_job_result`. Lo que un test REASIGNA nunca se re-exporta por
  valor: el código que lo lee se queda en el módulo viejo (`execute_command` en `registry`;
  `regenerate` y `_check_strict` en `document`; `check_integrity` se muda pero lee
  `document.resolve_all` en cada llamada; las tools movidas reciben `_api`/`_submit_and_wait`/
  `_paso` como lambdas tardías). `SUPERFICIE` y `MODULOS` no se tocan: `CONTRATO_EXTENSIONES` no
  sube.
- **D3 — Sin bumps de vigencia, demostrado.** `VERSIONES` y `CAMPOS` de
  `tests/test_contrato_comandos.py` NO se editan en todo el plan: un rojo ahí significa que el
  corte movió un byte y se rehace (**nunca se actualiza la huella**, aunque el contrato lo permita
  para refactors). No se tocan las seis líneas `from .registry import …` dentro de executors
  ajenos. `GEOM_CACHE_EPOCH`, `COSIM_EPOCH` y toda `CommandSpec.version` quedan iguales.
  `Feature` muda de módulo: los blobs NUEVOS nombran la ruta nueva y los VIEJOS cargan por el
  re-export (un test lo prueba con un pickle que nombra `apolo.commands.registry`). La última
  firma de cada proyecto en `golden_regen` sale idéntica: las cachés calientes siguen vigentes.
- **D4 — Módulos nuevos planos dentro de su paquete** (`commands/exec_*.py`,
  `commands/models_*.py`, `commands/escena.py`, `doc/*.py`, `tools/*.py`): sin subpaquetes, no
  cambian los imports relativos ni el empaquetado.
- **D5 — `mcp_server.py` se corta por sección y en su lugar.** Cada bloque contiguo pasa a
  `tools/<tema>.py` con `registrar(mcp, _api[, _paso | _submit_and_wait]) -> dict[str, Callable]`
  (los parámetros se llaman como los nombres que usan los cuerpos, que viajan tal cual);
  `mcp_server` llama `globals().update(<tema>.registrar(...))` EN LA POSICIÓN del bloque: el orden
  de `list_tools()` queda idéntico. El bloque «modelado» (`run_command`, `run_batch`,
  `edit_command`, `edit_batch`, `get_job`, `undo`, `set_variable` y `_paso`, `:239-355`) se queda
  en línea.

  | módulo | tools (líneas de hoy) | ≈ líneas |
  |---|---|---:|
  | `tools/consulta.py` | get_scene … get_design_guidelines (`:104-237`, 10) | 150 |
  | *(en línea)* | modelado (`:239-355`, 7) | — |
  | `tools/validacion.py` | check_interference, engineering_check, render_view, preview (`:356-516`) | 180 |
  | `tools/proyectos.py` | list_projects … drop_test (`:518-631`, 10) | 130 |
  | `tools/introspeccion.py` | get_command … restore_revision (`:633-907`, 21; `redo` recibe `_paso`) | 295 |
  | `tools/topologia.py` | get_topology … pick_point (`:909-1088`, 10) | 195 |
  | `tools/fabricacion.py` | cut_list … drawing (`:1090-1214`, 7; recibe `_submit_and_wait`) | 145 |
  | `tools/visibilidad.py` | set_visibility, set_visibility_bulk (`:1216-1229`) | 30 |
  | `tools/calculo.py` | resolve_expression, get_expression_grammar, get_fit, fea_static, fea_assembly (`:1231-1346`) | 135 |
  | `mcp_server.py` | infraestructura + modelado + registradores + `main` | **≈ 260** |

  Ningún módulo de `tools/` importa `apolo.mcp_server` (`test_mcp_registro.py`); cada uno importa
  lo que nombran sus anotaciones (FastMCP las evalúa).
- **D6 — `models.py` queda como fachada sobre familias.** Las pistas del agente y de la UI no
  cambian; la fachada conserva su docstring, los re-exports explícitos (`# noqa: F401`) y el
  `__getattr__` perezoso de `models_componente`, e importa `models_base` PRIMERO (así
  `models_cilindro`, `models_faja`… siguen importando `Vec3`/`Rot3`/`_motor_refs` de `.models` sin
  tocarse). Las referencias adelantadas (`'SlideUV'`, `'FlapSpec'`) se resuelven en el módulo de
  su clase.

  | módulo | contenido | ≈ líneas |
  |---|---|---:|
  | `models_base.py` | `_floor_to_int`, `Vec3`, `Rot3`, `_roller_refs`/`_profile_refs`/`_motor_refs` (`:19-47`, `:185-200`) | 60 |
  | `models_basicos.py` | caja, cilindro, perfil, booleana, transform, patrones lineal y de grupo, borrar, duplicar, centrar, repartir, `ANCHOR_NAMES`, attach, snap_to, set_variable | 225 |
  | `models_maquinas.py` | conveyor, weldment, frame, run_script, robot_arm | 165 |
  | `models_chapa.py` | `SheetSide`, `Hole`, `FlapHole`, `FlapCutout`, `ChildFlap`, `FlapSpec`, `SheetMetalParams` (`:396-504`) | 120 |
  | `models_modificar.py` | fillet, delete_faces, push_face, chamfer, shell, `DRILL_AXES`, drill_hole, pattern_circular, mirror, `JOINERY_TYPES`, add_joinery | 225 |
  | `models_croquis.py` | revolve, extrude_poly, import_step, `SKETCH_DOC`, sketch_*, helix, loft, curvas, superficies, thicken (`:712-915`) | 220 |
  | `models_ensamblaje.py` | juntas, mates, riel, restricciones, grupo, transform_group, insert_project, ground (`:918-1122`) | 220 |
  | `models.py` | fachada | **≈ 85** |
- **D7 — `registry.py`: una base `escena.py` y executors por familia.** `registry.py` queda con el
  `REGISTRY` literal (mismo texto y orden), el despacho, los schemas y el shim. Capas:
  `escena` ← `exec_*` ← `registry`; ningún `exec_*` nuevo importa `registry`; los params se
  importan de la fachada `.models` (F2 y F3 son independientes). `run_executor`,
  `execute_command`, `validate_params`, `_validate_model` y `command_schemas` no se mueven. Los
  envoltorios perezosos de `exec_rodillos`/`exec_componente` y los seis imports dentro de
  executors ajenos siguen apuntando a `.registry` (D3).

  | módulo | contenido | ≈ líneas |
  |---|---|---:|
  | `escena.py` | `Feature`, `DEFINITIONS`, `_DEFINITIONS_CAP`, `register_definition`, `touch_definition`, `Scene`, `Joints`, `_ancestors`, `_require`, `_instanced`, `_orient_axis`, `_resolve_sel` | 125 |
  | `exec_basicos.py` | primitivas, booleana, patrones lineal/grupo/circular, espejo, borrar, duplicar, set_variable | 215 |
  | `exec_colocacion.py` | `_world_move`, `_world_place`, `_bbox_center`, transform, center_in, distribute, `_v_*`, `_planar_face_frame`, anclas, attach, snap | 300 |
  | `exec_modificar.py` | caras (delete/push/fillet/chamfer/shell), `_drill_tool`, drill_hole, add_joinery | 300 |
  | `exec_croquis.py` | sweep, loft, superficies, thicken, revolve, extrude_poly, sketch_*, import_step | 190 |
  | `exec_ensamblaje.py` | `_register_joint`, `_joint_drag`, juntas, mates, restricciones, ground, grupo, `_transform_*`, transform_group | 315 |
  | `exec_insertar.py` | `_insert_project_precheck`, `_exec_insert_project` | 210 |
  | `exec_biblioteca.py` | run_script, robot_arm, `_publish_axis_anchor`, conveyor, `_emit_weldment_parts`, weldment, frame, sheet_metal | 155 |
  | `registry.py` | imports, shim, `REGISTRY`, despacho y schemas | **≈ 310** |
- **D8 — `document.py`: mixins** (precedente en `plc/`):
  `class Document(EdicionDocumento, MetadatosDocumento, IntegridadDocumento, PersistenciaDocumento)`.
  Los métodos conservan nombre y sangría (`getsource` idéntico) y `Document.x` sigue existiendo
  para cada `x`. Se quedan en `document.py` los métodos que leen globals que los tests reasignan
  (D2) y `preview`, que construye `Document` por nombre.

  | módulo | contenido | ≈ líneas |
  |---|---|---:|
  | `doc/edicion.py` | `execute`, `execute_many`, `edit_many`, `edit`, `remove_commands`, `add_attachment` | 135 |
  | `doc/metadatos.py` | variantes, color, material, vertical, motion, stackup, fea, requisitos, visibilidad, boceto-guía (`:638-849`) | 230 |
  | `doc/integridad.py` | `check_integrity` (`:314-419`) | 125 |
  | `doc/persistencia.py` | `FORMAT_VERSION`, `_CID_RE`, `_try_warm`, `to_apolo_bytes`, `save`, `from_apolo_bytes`, `load` | 185 |
  | `document.py` | imports, `_STRICT`, `_cmd_sig`, re-exports; `__init__`, undo, regenerate, `_check_strict`, `_push_undo`, `_mutate`, `_vars_block_end`, `_append_record`, `preview` | **≈ 410** |
- **D9 — Orden y forma de las fases.** Lo más aislado y con el gate más fuerte primero. Cada fase
  saca su foto «antes» de SU base; ante un conflicto al rebasar, el script de corte se RE-EJECUTA
  sobre la base nueva (no se resuelve a mano). Las fases se mergean en serie (chocan en las líneas
  contiguas de `EXCEPCIONES` y en «Estado actual»).
- **D10 — Las reglas viajan con el código.** Cada fase baja el número de su archivo en
  `EXCEPCIONES` en el MISMO commit (y lo borra al quedar ≤ 500) y actualiza su CLAUDE.md:
  `core/apolo/CLAUDE.md` § MCP («una tool nueva va a `tools/<tema>.py` y se registra en su
  lugar», sin pasar de 10 KB); `commands/CLAUDE.md` (mapa de módulos y «los imports perezosos de
  executors ajenos apuntan a `.registry`: no se tocan, son parte de su huella»); `doc/CLAUDE.md`
  (mapa de módulos y qué se queda en `document.py` y por qué).
- **D11 — Gate permanente `tests/test_rutas_viejas.py`** (nace en la primera fase; cada fase suma
  su sección): listas CERRADAS de los nombres que cada ruta vieja sigue exportando y que cada uno
  es el MISMO objeto que en su casa nueva; las 76 tools siguen siendo atributos invocables de
  `apolo.mcp_server`; `dir(Document)` es el de hoy; un blob con `apolo.commands.registry.Feature`
  carga; un test prueba que el gate caza la falta de un nombre. `test_mcp_registro.FUERA_DEL_ARCHIVO`
  suma una tool de cada módulo nuevo de `tools/`.
- **D12 — Meta**: los cuatro ≤ 500 (`mcp_server` ≈ 260, `models` ≈ 85, `registry` ≈ 310,
  `document` ≈ 410) y fuera de `EXCEPCIONES`; ningún módulo nuevo pasa de 500 (el mayor ≈ 315).

**Decisiones de la revisión** (sesión principal, 2026-10-24): D8 con mixins; se re-exportan las 76
tools (otro cliente o script podría llamar cualquiera); `check_integrity` se muda leyendo
`resolve_all` por el módulo `document`; el orden de fases arranca por F2 (`models`, nada en curso
lo toca) y F1 (MCP) espera a que V8.9 F6 esté en `main` por si suma tools; `core/tests/test_mejoras_mcp.py`
(fuera de `testpaths`, no corre en el CI) se resuelve en una fase de salud aparte.

## Alternativas descartadas

- **Actualizar `VERSIONES` en bloque «porque es refactor»**: borra la prueba de que nada cambió.
- **Re-escribir los seis imports `from .registry` de los executors ajenos**: cambia seis huellas
  sin motivo de geometría.
- **`Feature.__module__ = "apolo.commands.registry"`** para que los blobs queden byte a byte:
  miente en `repr` e introspección; la caché no es autoritativa y lo viejo carga por el re-export.
- **Delegación en `Document`** (funciones libres + métodos de una línea): ~120 líneas de
  envoltorios para lo mismo.
- **Composición (`doc.meta.set_motion`)**: cambia la API pública del documento y de las
  extensiones.
- **Subpaquetes** (`commands/executors/`, `doc/document/`): cambian imports y empaquetado.
- **Re-exportar sólo las 11 tools que los tests llaman**: `globals().update` conserva la
  superficie entera por el mismo precio.
- **Re-congelar el golden MCP o regenerar algún snapshot**: prohibido; si cambia algo, el corte
  está mal.
- **Un solo merge «partir los cuatro»**: no se puede revisar.

## Fases

Común a todas: subagente opus en su worktree (`git merge main --ff-only` al empezar,
`$env:PYTHONPATH = "$PWD\core"` y `-B`); paso 1, foto «antes» desde su base (scratchpad);
paso 2, script de corte por nombre; paso 3, comparación de fuentes. **Gate común**: suite
completa, `ruff check core tests scripts`, cada módulo nuevo importado solo en un subproceso,
`test_tamano_archivos.py` con el número actualizado, `test_rutas_viejas.py`, `test_claude_md.py`, y
`git diff --exit-code tests/test_contrato_comandos.py tests/data/mcp_golden core/apolo/doc/geomcache.py`.
La sesión principal re-corre todo antes de integrar.

- **F1 — `mcp_server.py` → `tools/`** (M · ≈ 60 min · `mcp`): los ocho módulos de D5, cada uno con
  su `registrar` llamado en la posición de su bloque; sección MCP del gate de D11;
  `FUERA_DEL_ARCHIVO` crece; D10 en `core/apolo/CLAUDE.md` y en el docstring de `tools/__init__.py`.
  **Se verifica:** gate común; `test_mcp_golden` verde SIN `--congelar` (instructions,
  `list_tools` en el mismo orden y las 90 llamadas); `test_mcp_registro`;
  `test_docstrings_limpios`; la comparación de las 76 tools (0 distintas, 0 perdidas);
  `mcp_server.py` ≤ 500 y su entrada borrada.
- **F2 — `models.py` → familias** (M · ≈ 45 min · `commands`): los siete módulos de D6 y la
  fachada. **Se verifica:** gate común; el JSON de `command_schemas()`,
  `command_schemas_agente()` y `command_schemas_persona()` idéntico byte a byte a la foto
  «antes»; `rutas(REGISTRY)` igual a `CAMPOS` sin editarlo; los 70 nombres viejos de `models`
  importables y por identidad; `getsource` de cada clase movida idéntico; `models.py` fuera del
  trinquete.
- **F3 — `registry.py` I: base y modelado** (M · ≈ 60 min · `commands`): `escena.py`,
  `exec_basicos.py`, `exec_colocacion.py`, `exec_modificar.py` y el shim de lo movido;
  `registry.py` 1 912 → ≈ 1 100. **Se verifica:** gate común (`test_contrato_comandos` verde sin
  tocar `VERSIONES`; `{tipo: huella}` igual a la foto); `test_despacho_unico` (62); `-m torture`;
  schemas idénticos; `golden_regen.py` sobre una copia congelada de `data/apolo.db` (sólo
  lectura) sin diferencias, también en la última firma; **open caliente con un blob escrito por
  el código VIEJO** (de la tabla `geom_cache` de la copia: `from_apolo_bytes(warm=unpack(blob))`
  termina con CERO llamadas a `execute_command`).
- **F4 — `registry.py` II: croquis, ensamblaje, insertar y biblioteca** (M · ≈ 55 min ·
  `commands`): los cuatro módulos restantes de D7; `registry.py` ≈ 310 y su entrada borrada; D10
  en `commands/CLAUDE.md`. **Se verifica:** lo mismo que F3.
- **F5 — `document.py` → mixins** (M · ≈ 65 min · `doc`): los cuatro módulos de D8;
  `check_integrity` lee `resolve_all` por el módulo `document`; `TYPE_CHECKING` en
  `persistencia.py`; D10 en `doc/CLAUDE.md`. **Se verifica:** gate común; `-m torture`
  (`_STRICT`, `_boom_resolve_all`, atomicidad); `test_geomcache*`, `test_prefijos`,
  `test_deshacer_pasos`; `dir(Document)` y el `getsource` de cada método iguales a la foto;
  `golden_regen.py` sin diferencias; `to_apolo_bytes` de los proyectos 38, 28 y 53 (desde la
  copia) idénticos miembro a miembro; `document.py` ≤ 500 y su entrada borrada.
- **F6 — Cierre y punta a punta** (S · ≈ 40 min): API levantada desde el worktree, sin
  `--reload`, sobre una COPIA de `data/apolo.db`, en un puerto libre (nunca el 8000), corriendo
  `scripts/e2e_mcp.py --puerto N --proyecto 38`; abrir el 38 dos veces y anotar los tiempos (la
  1.ª, con la caché que dejó el código viejo, ya debe ser caliente); conteos y `nota:`.
  **Se verifica:** el E2E sale con 0; `EXCEPCIONES` ya no nombra ninguno de los cuatro; suite,
  `-m torture` y ruff verdes.

## Lo que este plan NO hace

- No cambia comportamiento, nombres, textos, schemas, tools ni el orden de nada.
- No toca los imports `from .registry` dentro de executors ajenos ni los envoltorios perezosos.
- No quita los shims ni migra importadores a las rutas nuevas.
- No toca `extensiones_api` (`SUPERFICIE`, `MODULOS`) ni `CONTRATO_EXTENSIONES`.
- No sube `GEOM_CACHE_EPOCH`, `COSIM_EPOCH` ni ninguna `version`; no cambia el `.apolo`, el log
  ni la SQLite.
- No parte `drawing/sheet.py` (882), `library/builders.py` (847), `library/rules.py` (903) ni
  `library/engineering/report.py` (555): plan aparte cuando haga falta.
- No toca `ui/`.

## Riesgos

| riesgo | mitigación |
|---|---|
| Un byte de más cambia una huella y alguien «la actualiza» | D3: prohibido editar `VERSIONES`; el script compara `getsource` antes del commit; rojo = rehacer el corte |
| Un re-export por valor de algo que un test reasigna vuelve el parche un no-op (verde en falso) | D2: lo que lee esos globals no se mueve; el gate de D11 comprueba identidades |
| Ciclo de imports: la API o el MCP no arrancan | capas de D7; cada módulo importado solo en un subproceso; sonda `-m` de `test_mcp_registro` |
| Cambia el orden de las tools | D5: bloques contiguos registrados en su posición; `list_tools.json` en orden |
| La sangría de los docstrings cambia la descripción en 3.11/3.12 | `FastMCPLimpio` aplica `cleandoc`; `test_docstrings_limpios`; CI en 3.11–3.13 |
| Una anotación de una tool movida no resuelve | importar en cada módulo lo que nombran sus firmas; el golden lo caza |
| Referencias adelantadas de pydantic o `$defs` renombrados | importar en la familia; snapshot de los tres schemas byte a byte |
| La caché vieja no carga por la ruta de `Feature` | re-export permanente; test de pickle con la ruta vieja; open caliente con un blob del código viejo (F3, F6) |
| Volver a un checkout anterior con blobs nuevos | no cargan → replay frío: cuesta tiempo, no se pierde nada |
| Conflictos con commits diarios sobre estos archivos | fases cortas; script re-ejecutable; rebase justo antes de proponer |
| `golden_regen` sobre toda la base tarda demasiado | se cronometra en F3; si pasa de ~15 min, los proyectos de referencia (38, 28, 53) y el banco |

## Bitácora

### F0 — medición (2026-10-24, base `1f01d0a`, sólo lectura)

- **Tamaños**: registry 1 912, mcp_server 1 366, models 1 183, document 1 009 (=
  `EXCEPCIONES`). Churn de 30 días: 23 / 32 / 6 / 19 commits (61 distintos).
- **Huella** = sha1 de `inspect.getsource(executor)`: independiente del archivo; la firma de la
  caché no la incluye. 48 executors viven en `registry.py`; seis ajenos importan de `.registry`
  dentro de su cuerpo.
- **Superficie importada**: `registry` 88 nombres (48 executors); `models` 70; `document` 5 más
  los globals reasignados; `mcp_server` 76 tools en línea y 14 fuera; 90 en el golden, en orden.
- **Pickle**: sólo `geomcache.pack` persiste instancias de `Feature`.
- **Sorpresa**: `core/tests/test_mejoras_mcp.py` está versionado pero cae fuera de
  `testpaths = tests` (no corre en el CI).
