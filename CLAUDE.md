# Genix Apolo CAD

CAD paramétrico 3D para maquinaria industrial/robótica cuyo **diferenciador es el
diseño asistido por IA** (agente-nativo, también manual). Vertical del MVP:
transportadores / manejo de materiales. Stack: **Python (build123d/OCCT) + FastAPI +
React/three.js**. IA: Claude API en la nube vía `APOLO_MODEL` (por defecto
`claude-opus-4-8`).

> **Historia detallada**: la narrativa completa de cada feature (verificaciones E2E,
> cirugías de modelos, decisiones de diseño con contexto) vive en `docs/devlog.md` y en
> `git log`. Este archivo conserva SOLO instrucciones, mapa del sistema, convenciones y
> lecciones — lo que hace falta para trabajar, no la crónica.

## Arquitectura (principios que NO se negocian)

- **API-first / IA-nativa**: toda operación es un comando sobre un kernel headless.
  UI, agente-chat y MCP son clientes iguales de la misma API HTTP.
- **Documento = log de comandos** (event-sourced). `.apolo` = ZIP (manifest v2 +
  commands.json + attachments/). La geometría nunca se guarda → archivos de KB,
  autosave barato, undo/redo por snapshots.
- **Schema-driven**: los JSON Schemas pydantic del `REGISTRY` generan a la vez la
  toolbar, los diálogos, el panel Propiedades y las **tools del agente**. Una sola
  fuente de verdad. El MCP es THIN: núcleo de escritura mínimo (`run_command`/`run_batch`
  con `$k` + `edit_command`/`edit_batch` + undo/redo cubren TODO el registro; NO hay tool
  por comando) — auditado: los huecos siempre han sido de LECTURA, no de escritura.
- **Expresiones**: cualquier campo numérico acepta `"=expresión"` con variables del
  proyecto (motor AST en `commands/expressions.py`). Las variables son comandos
  `set_variable` en la cabecera del log; cambiarlas regenera todo.
- **Selectores declarativos** de aristas/caras (todas/direccion/cara/longitud/cerca)
  para evitar nombrado topológico frágil.
- **Plantillas de máquina = super-comandos** del registro (p. ej. `create_conveyor`),
  no scripts: heredan edición paramétrica, undo, BOM y exposición al agente gratis.
- **Criterio de ingeniería por defecto**: el agente diseña como ingeniero/estructurista
  (el usuario es el CLIENTE) y asume lo obvio —sujeción, montaje/desmontaje con pernos,
  forma conforme a la función— sin esperar a que se lo pidan. Fuente ÚNICA en
  `core/apolo/design/guidelines.py` (`design_brief()` + `design_guidelines()`): capa 1
  inyectada SIEMPRE en instrucciones MCP y `SYSTEM_PROMPT`; capa 2 bajo demanda
  (`get_design_guidelines` / `GET /api/design-guidelines`). Un 3D solo vale si es
  FABRICABLE y se SOSTIENE.

## Escala — mandato de arquitectura

Este proyecto se desarrolla **para crecer a gran escala**. Por tanto: nada de módulos
monolíticos ni responsabilidades mezcladas; si para hacerlo bien hace falta refactorizar,
se refactoriza. Fronteras limpias: `kernel` (geometría pura) ⟂ `commands/registry`
(operaciones+schemas) ⟂ `doc` (log/estado) ⟂ `library` (catálogo/cálculo, funciones
puras que NUNCA reciben `Document`) ⟂ `api` (transporte) ⟂ `agent`/`mcp` (clientes IA)
⟂ `ui`. Cada módulo nuevo: responsabilidad única, testeable aislado, sin estado global
fuera de los puntos establecidos (`STATE_LOCK`), con tests.

## Ejecutar y probar

```powershell
.\start-apolo.ps1                 # API+UI en http://127.0.0.1:8000 (-OpenBrowser, -Reload, -Port)
.\.venv\Scripts\python.exe -m pytest tests -q     # 1089 tests (tortura extendida: -m torture)
cd ui ; npm run build             # bundle de la UI (tsc + vite)
```

- **MCP `apolo-cad`** (`.mcp.json`) = cliente fino stdio→HTTP; **69 tools**. Requiere la
  API arriba. **El host MCP debe reiniciarse** para ver tools/firmas nuevas (registra al
  arrancar); la API sin `--reload` también se reinicia tras cambios de código.
- **Estado actual (2026-07-11)**: 1089 tests (+15 tortura vía `-m torture`) · 69 tools MCP ·
  52 comandos · catálogo 217 refs. Roadmaps **V1–V5 completos** y **V6 «Apolo industrial»
  CERRADO** (V6.1 robustez 3→6 · V6.2 rendimiento 4→6 · V6.3 ensamblaje 4.5→6 · V6.4
  paramétrico 5→6.5 · V6.5 MCP a escala); detalle por ítem en su sección del Mapa/
  Convenciones. Proyectos de referencia: `faja-paqueteria-4m` (id 38, 74 sólidos, 312
  comandos, 100 % paramétrica, memoria APROBADO, eje motriz «Ø35 h7»), `layout-planta-demo`
  (id 53, 149 sólidos) y `guarda-banda-demo` (chapa en C con hems, DXF verificado).
- Preview de la UI en desarrollo: configs `ui-dev`/`ui-preview` en `.claude/launch.json`
  (el build de producción lo sirve la API en :8000; `npm run dev` + StrictMode rompe el
  viewport — usar `vite preview`).

## Mapa del sistema (qué existe y dónde)

### Kernel / percepción del agente
- **Render**: `kernel/render_vtk.py` (motor PRO: sombreado suave, aristas de feature,
  depth-peeling para xray/vidrio, FXAA) + `kernel/render.py` (matplotlib: fallback sin
  OpenGL, multivista `views`, GIFs, iso de planos; `resolve_angles` = fuente única de
  cámara para ambos). Tool `render_view` es **VTK puro** (`vtk_only`): cámara libre
  (`azimuth`/`elevation`/`roll`/`pan`), `isolate` (filtra copia de escena SIN mutar doc,
  fuerza-mostrar), `highlight_ids`, `xray` (translúcido a color — legible solo ACOTADO a
  2-3 piezas), `section` x/y/z, `labels` (billboards en capa overlay), `measure=[a,b]`
  (cota del gap OCCT dibujada encima), `fit_ids`/`zoom`, `joint_values` (pose cinemática).
- **Pick**: `kernel/pick.py` píxel→pieza/cara EXACTO (matriz de cámara VTK compartida con
  el render, sin contexto OpenGL); honra `isolate`/`section` — pasa los MISMOS params del
  `render_view` para que el píxel coincida con lo que ves.
- **Medición/consulta**: `kernel/measure.py` (`measure_distance` gap OCCT), `near`,
  `kernel/topology.py` (`get_topology`: caras/aristas con geometría descriptiva para
  ELEGIR el selector declarativo), `resolve_expression`/`get_expression_grammar`,
  dry-run `test_sketch`/`test_script`, `Document.preview` (ghost sin tocar el doc).
- **Ergonomía MCP**: mutaciones devuelven retorno compacto `detail="diff"` (solo sólidos
  de `affected_command_ids` + `total_solidos`; `_state_or_error` captura el retorno del
  lambda) — aplica también a `set_visibility`/`set_material` (957 KB → 350 bytes);
  `variables` solo si cambió; `edit_command` hace PATCH (merge superficial: un sub-objeto
  position/rotation se reemplaza ENTERO); `edit_batch` = N ediciones en UN regenerate
  atómico y 1 undo; `GET /api/schemas/{type}` para no volcar los ~77 KB de schemas.
- **Lectura a ESCALA (V6.5)**: ninguna lectura de rutina vuelca la escena entera.
  `get_scene(summary=true)` (`GET /api/scene/summary`) = resumen por GRUPO (n_piezas/masa/
  bbox conjunto/sub-grupos + «(sin grupo)» + totales + variables) — la vista de ENTRADA a un
  proyecto grande; `get_scene(ids|name|limit|offset)` filtra por grupos/nombres y pagina un
  brief SIN mallas (declara `total_filtrado`/`truncado`, sin caps silenciosos). `get_topology
  (only, min_mm)` poda micro-fillets/taladros; `get_bom(by_group)`; `near(feature|box)` (AABB-
  AABB, «qué rodea a X»/«qué hay en la región»); `check_interference(ids=...)` acotada O(k·n)
  (`focus` en `interference_report`); `verify` (aserciones en lote, `library/verify.py` puro,
  inyecta expand+interference_fn); `preview(data=true)` (fantasmas+colisiones sin PNG). Los
  briefs filtrados los arma el SERVIDOR (`_scene_filtered`/`_feature_brief`, mismos campos que
  `_scene_brief` del MCP) reusando `_expand_ids`; `get_scene()` sin params = payload completo
  con mallas byte-idéntico (compat viewport). Presupuesto: <10 KB/lectura a 1000 piezas.

### Comandos / modelado (52 comandos)
- **Superficies básicas (V5.11, `kernel/surface.py`)**: `boundary_surface` (Face de un
  contorno cerrado de curvas — `Face.make_surface`/BRepOffsetAPI_MakeFilling; `points` la
  levantan a parche NO plano, `holes` = lazos interiores), `fill_surface` (parche sobre
  aristas de un sólido — tapar huecos/bordes; `tangent` = continuidad G1 via
  `make_surface_patch`, solo en continuación suave: falla en paredes perpendiculares con
  aviso) y `thicken` (superficie → sólido de pared; `both` engruesa a CADA lado = espesor
  total 2×; muta en sitio). Para chutes/tolvas/deflectores/guardas curvas: boundary/fill +
  thicken. Una superficie DESNUDA (`is_surface` en `kernel/shapes.py`: caras y 0 sólidos)
  es geometría de CONSTRUCCIÓN — EXCLUIDA de BOM/masa/costeo y de la vista de sección
  (`projection.py` filtra a sólidos); FEA la rechaza pidiendo `thicken`. Gotcha: el log
  regenera, no serializa geometría → sin cambios de persistencia.
- **Modelado directo (V5.3, `kernel/direct.py`)**: `delete_faces` (OCCT Defeaturing:
  borra caras y CURA extendiendo las vecinas — quitar fillets/barrenos/bosses de un
  STEP; flag `tangentes` expande a la cadena de caras CURVAS tangentes **o de mismo
  radio** — dos tramos de fillet en esquina viva NO son G1; las planas nunca entran
  a la expansión o la cadena se fuga al sólido) y `push_face` (prisma+booleana sobre
  UNA cara PLANA; ±distance con `=expr`; paredes nuevas RECTAS — no extiende caras
  inclinadas vecinas; normal EXTERIOR verificada con clasificador de sólido, nunca
  `normal_at` a ciegas: las caras STEP vienen REVERSED). Gotchas: cuando OCCT no
  puede curar devuelve el sólido INTACTO (no-op detectado por caras+volumen → error);
  mover un barreno = `delete_faces` + `drill_hole` nuevo; `SetOffsetOnFace` (resize
  radial de barrenos) NO funciona en OCP 7.8.1 (spike NO-GO) — pendiente.
- **Croquis 2D con PlaneGCS (V5.1)**: `kernel/sketch_solver.py` es una FACHADA de dos
  motores — `sketch_gcs.py` (el solver del Sketcher de FreeCAD, pip `planegcs`, wheel
  cp313; default) y `sketch_scipy.py` (fallback VIVO si no hay wheel; override env
  `APOLO_SKETCH_SOLVER=scipy|planegcs`; los tests parametrizan ambos). GCS aporta
  `dof`/`redundantes`/`conflictivas` en el retorno del solve (iterar hasta dof=0) y
  6 tipos nuevos SOLO-GCS: tangent, symmetric, equal_radius, concentric, midpoint,
  distance_point_line (+ `radius` ahora acepta ARCOS). El veredicto `ok` lo da un
  VERIFICADOR geométrico común (mismas fórmulas en ambos motores). OJO sketch_geom:
  si el lazo recorre un arco en reversa, el ccw efectivo se invierte (bug corregido).
  SketcherDialog: herramienta Arco (3 clics: centro→inicio→fin) + botones nuevos +
  panel DOF/redundantes/conflictivas. Arrastre en vivo (soft-constraints) PENDIENTE.
- **Chapa avanzada (V5.5, `library/sheetmetal.py`)**: `create_sheet_metal` acepta
  `flaps` (lista de FlapSpec: pestaña por lado con `child` de un nivel — perfiles
  C/Z/hem, `direccion` interior/exterior — + `holes`/`cutouts` propios) y `k_factor`
  None = **K por material** (`K_FACTOR_BY_MATERIAL`: acero 0.40, inox 0.45, alu/latón
  0.35; resuelto en la capa API con `resolve_material`). Convención de features en
  pestaña: `u` a lo largo del pliegue ALINEADA AL EJE MUNDIAL (0=centro), `v` desde el
  BORDE LIBRE (métrica en que 3D y desplegado coinciden sin conocer el radio); feature
  que invade la zona de pliegue → rechazo con el dominio válido. Proyección al flat:
  offset padre = `BA_p+(altura−OSSB_p)−v`, hijo = `strip_total−v`. La vía simple
  (lados/altura) se NORMALIZA a flaps → un solo camino, flat byte-idéntico (test de
  igualdad exacta). Gotcha: el pliegue HIJO queda vivo (sin fillet, fallback G2).
- Primitivas + croquis restringido + sweep/loft/hélice (lazo cerrado,
  `is_frenet`) + chapa metálica con **desplegado DXF/SVG** (bend allowance, taladros
  proyectados al blank) + `add_joinery` (espiga/dado/dowel/rebaje — corta EN SITIO,
  conserva ids) + patrones (`count` por `=expr`; `pattern_group` arraya TODAS las
  features de un comando, rechaza fuentes con juntas) + `center_in`/`distribute`/`snap_to`
  (colocación relacional, se reevalúa al regenerar; `snap_to` V6.5 = «junto a B hacia ±eje
  con gap g / a ras», bbox-a-bbox + `alinear` para centrar en los otros ejes — para caras
  arbitrarias/cilíndricas están los mates) + `duplicate_feature`.
- **Super-comandos**: `create_conveyor` (RODILLOS), `create_belt_conveyor` (BANDA),
  `create_weldment`/`create_frame` (bastidores con lista de corte; `esquinas=
  "tope"|"inglete"` V5.8 — inglete: corte por el plano BISECTOR del nodo en
  `library/miter.py` (V exacto = A·span, ancla de tests), weldment = marcos sup/inf
  45° picture-frame + postes A TOPE entre marcos, frame = bisectriz solo en nodos
  grado 2 (colineal→recto, α>75° o grado≥3→tope); `Feature.miter` → BOM/lista de
  corte con "∠45°/45°" y `cut_length` = longitud EXTERIOR), `create_sheet_metal`,
  `create_take_up` (tensor de cola trotadora: eje fijo + perno tensor Allen horizontal
  que atraviesa el eje roscado + soporte C soldado al larguero), `create_drive_roller`
  (idem con eje largo — OJO: eje FIJO, para tambor MOTRIZ real usa eje vivo + chumaceras),
  `create_robot_arm`. Un super-comando debe documentar su MONTAJE en el description.
- `fasten`/`ground` (conectividad, `wants_connectivity`): `fasten` acepta dimensionamiento
  opcional `size`/`qty` (perno) y `throat_mm`/`length_mm` (soldadura; `throat` ES la
  garganta, a=0.707·cateto).

### Sub-ensamblajes (grupos de primera clase, V5.2 — 2026-07-01)
- **Grupos por COMMAND_IDs** (`assembly/groups.py` + comando `create_group` {name,
  members, parent, role}): la unidad estable del log es el comando (los feature_ids
  pueden desaparecer al editar counts) → TODAS las piezas presentes/futuras de esos
  comandos pertenecen. Anidables (`parent` debe declararse ANTES → ciclos imposibles);
  un comando vive en UN grupo; integridad TOLERANTE (member borrado → `missing_members`,
  no falla). Campo DERIVADO `feat.group` asignado al final de cada regenerate;
  checkpoints del incremental = 8-tupla (…, groups). Dispatch: flag `wants_groups` =
  firma kwargs `(scene, cmd_id, model, *, groups, joints, mates, constraints)`.
- **`transform_group`**: mueve/rota el grupo ENTERO (recursivo) como cuerpo rígido
  sobre el centro del bbox CONJUNTO (`move_rotated_about` en kernel/shapes.py — la
  rotación por pieza de `_world_move` es incorrecta para grupos); las juntas/
  restricciones INTERNAS viajan con él; una junta/mate que CRUZA la frontera →
  CommandError claro (verificado en la faja: mover "Rodillos" se rechaza por
  `j_tensor_cola` hacia el larguero — correcto).
- **isolate/highlight/fit aceptan NOMBRES de grupo** (`_expand_ids` en api/main.py,
  cableado en render/pick/drawing_spec/assembly-manual; los nombres no admiten comas).
  `GET /api/groups` + tools `get_groups`/`auto_group` (62→64 — reiniciar host MCP).
- **`auto_group`** (`assembly/grouping.py::propose_groups` + POST
  `/api/assembly/auto-group` con dry_run): la heurística de subsistemas del árbol
  portada a backend (fuente única); idempotente; sin señal → sin grupo. El **manual de
  ensamblaje** pagina por grupos cuando existen (faja: 13 pasos heurísticos → 6 = sus
  sub-ensamblajes); **BOM** con `by_group=True` separa filas y da subtotales por grupo
  (default byte-idéntico); **árbol UI** renderiza los grupos reales como nivel 1 (+
  botón "crear grupo desde selección", acciones seleccionar/aislar rama) con fallback
  heurístico para lo no agrupado. V5.2b pendiente: `role` consumido por las reglas,
  drag&drop del árbol.
- **`insert_project` (V5.2b — 2026-07-02)**: instancia un PROYECTO guardado completo
  como sub-ensamblaje (layouts multi-máquina). SNAPSHOT embebido: la capa API
  materializa `project_id`→attachment (`_materialize_insert_project`, espejo de
  `/api/import`; auto-referencia → 400) → el `.apolo` del layout es AUTOCONTENIDO.
  Executor `wants_all` (firma kwargs total) + sandbox replay en `doc/subproject.py`
  (caché por digest+overrides cap 8, `MAX_DEPTH=3`; `from_apolo_bytes(regenerate=False)`
  para pisar `set_variable` ANTES del replay → namespaces aislados). Emite TODO
  prefijado: fids/command_ids sintéticos `{cmd}_{orig}` (preserva `same_command_pairs`
  y membresía), juntas/constraints con origin/axis transformados, fasteners con
  dimensionamiento, grounds (param `keep_grounds`), grupos internos REALES anidados
  `"{name}/{grupo}"` bajo el raíz `name`; los MATES llegan BAKED (no se re-registran).
  `overrides` = parametricidad por instancia (`=expr` resuelve contra variables del
  ANFITRIÓN); refresh = `edit_command {"attachment": ""}` (content-addressed → no-op si
  el origen no cambió). **Editar B se hace ABRIENDO B**, no desde el layout. OJO: el
  override solo cascadea lo que el DONANTE ató a variables (el 38 tiene run_scripts con
  literales → conjunto motriz flotante al encoger; es gap del donante, no del comando).
  `GET /api/bom?by_group=true` expone los subtotales por grupo/instancia.

### Ensamblaje / cinemática / validación física
- **Mates** (`assembly/mates.py`): coincidente/distancia/concéntrico/paralelo/ángulo,
  re-resueltos en `regenerate`. **MULTI-MATE (V6.3a)**: un sólido puede ser hijo de ≥2 mates
  (grafo hijo→padres = DAG multi-padre; lazos A↔B rechazados como ciclo). Solver de DOS
  caminos: 1 mate/hijo → camino cerrado exacto `_solve_one` (pose determinista, INTACTO); ≥2
  → `_solve_multi` (least_squares 6-DOF, rotación sobre el CENTRO de B — sobre el origen no
  converge si B está lejos; residuos por tipo `_mate_residuals` consistentes con
  `_desired_current_frames`, cada mate restringe solo sus GDL naturales). Conflicto (costo >
  1e-3 tras 1 reintento con perturbación fija) → MateError nombrando los mates → rollback.
  **Conectores (V6.3b)**: cara plana/cilíndrica, ARISTA CIRCULAR (`{"entidad":"arista"}` →
  centro+eje del círculo) o ANCLA con nombre (`{"mode":"ancla","name":...}` → `Feature.anchors`,
  frames MUNDO publicados por los executors: chumacera→"centro", NMRV→"bore", faja→
  "eje_motriz"/"eje_cola"; se re-calculan en cada regenerate y toda transformación las mueve —
  `kernel.matrix.transform_anchors`, REEMPLAZA nunca muta; `get_topology` las lista). **Riel
  lazo-cerrado** (`add_rail_constraint`) + **N-GDL** (`add_constraint`: least_squares global;
  punto_en_recta/plano/coincidente/distancia). FK de un punto: `robotics/pose.py`.
- **Reporte de DOF (V6.3c, `assembly/dof.py`)**: `dof_report(scene,joints,mates,grounds)` puro
  (sin Document/OCCT) — por sólido, 6 GDL menos ground (−6)/junta (fija−6, gir/cont/pris−5)/
  mates (coincidente−3, distancia−3, concéntrico−4, paralelo−2, ángulo−1); estado fijo/parcial/
  libre/sobre_restringido. Conteo Grübler HEURÍSTICO (no ve redundancia geométrica; el
  sobre_restringido por conteo puede ser benigno — los conflictos REALES los rechaza el solver
  de mates). `GET /api/assembly/dof` + tool `get_dof` + bloque en AssemblyPanel. Las juntas,
  que en el resto son solo visualización, aquí SÍ cuentan como restricción.
- **Estudios de movimiento CON NOMBRE**: `Document.motion: dict[str, list]` (metadato de
  manifest), `set_motion`/`delete_motion`, scan de colisiones por recorrido.
- **Conectividad/soundness** (`assembly/connectivity.py` + `autodetect.py`): grafo
  juntas∪mates∪fasteners con semilla `grounds`; `detect_structure` = grafo de soporte
  DIRIGIDO (auto-declara ground/fasten inteligente); `soundness_report` (qué flota).
- **Física (MuJoCo)**: `gravity_test` (piezas sujetas=estáticas, resto cae; casco
  CONVEXO con caché por referencia fuerte al shape), `drop_test` (producto, AABB),
  animación en el viewport con las mallas reales.
- **FEA estático lineal (V5.6, `core/apolo/fea/`)**: tool `fea_static` (una PIEZA:
  malla tet P2 gmsh + elasticidad lineal scikit-fem; extra pip `[fea]` — sfepy/CalculiX
  NO-GO sin wheels) → σ_vm máx + FS=σy/σ_vm + fringe PNG; resumen persiste en
  `Document.fea` (metadato manifest) → página en la memoria con aviso de VIGENCIA si el
  volumen cambió. Gotchas: `gmsh.initialize(interruptible=False)` (endpoints sync =
  threadpool, signal solo va en main thread); patrón DOS LOCKS (STATE_LOCK resuelve
  selectores/STEP, el solve corre FUERA con `FEA_LOCK` propio — gmsh es single-instance
  global); paredes delgadas (HSS) disparan tets → minutos (la pata 76×76×3 = 112 s;
  `mesh_size_mm` es el control); σ_vm pegado al empotramiento = concentración numérica
  (`max_en_encastre` lo marca); material sin σy tabulado exige `yield_mpa`
  (`has_yield`, no se miente con defaults).
- **Interferencias**: `check_interference` (booleanas OCCT; excluye pares de junta,
  `same_command_pairs` y hardware tornillería/rodamientos) + `interpenetration_report`
  (exceso vs pose de diseño en pares con junta).

### Ingeniería / negocio (Frentes A/B)
- **`library/engineering/`** (puro): `belt` (banda-sobre-cama μ=0.33 + par de arranque
  1.6× — el μ=0.06 de rodadura queda SOLO para rodillos), `bolts` (ISO 898-1/EN 1993-1-8),
  `welds`, `bearings` (L10, `C_kN` de specs), **`fits` (ISO 286, V5.4)**: TABLAS IT5-11
  + desviaciones de eje 1–500 mm (agujeros derivados por reglas de la norma; K-P solo
  grados 6-7), `fit_limits`/`fit_check`/`bearing_seat_check` (bore ISO 492 Normal) +
  `SEAT_RECOMMENDATIONS` por tipo de montaje (inserto UC → eje h7 DESLIZA; prensado
  anillo giratorio → k6); regla `asiento ISO 286 · {ref}` en report.py detecta pares
  eje↔rodamiento (fastener/junta/mate concéntrico + Ø coincidente): sin fit → aviso,
  k6 en inserto UC → ERROR. El fit del EJE va en el NOMBRE («Eje motriz Ø35 h7»), el
  del taladro en `drill_hole.fit` (H7); el plano rotula "Ø35 h7 (0/-0.025)" automático
  (mapa de la capa API + override `hole_fits` del drawing spec); consulta: tool
  `get_fit` / `GET /api/fits` (65 tools — reiniciar host MCP). **`threads` (ISO
  261/262, V5.7)**: `drill_hole.thread` ("M8", "M10x1.25") taladra a la BROCA de
  machuelado PUBLICADA (M8→Ø6.8, `diameter` se ignora; fit⊕thread excluyentes — la
  rosca interior es 6H fija) y el plano rotula "4×M8 - 6H (broca Ø6.8)" + arco
  cosmético ISO 6410 (3/4 de vuelta al Ø nominal, `Arc` en SheetModel, capa DXF
  ROSCA fina); la CÉDULA del juego gana filas de machuelos (y se fuerza aunque no
  haya herraje); consulta `GET /api/threads`; roscas EXTERIORES fuera de alcance
  (por nombre, como los fits). `buckling` (Euler K=2, inercia mínima),
  `stability` (COG vs casco de apoyos), `loads` (`hanging_load_kg`: carga de una unión =
  masa que pierde tierra al quitar su arista; redundante → None), `mass`
  (`get_mass_properties`: catálogo pesa por FICHA, a-medida volumen×densidad), `report`
  (`structure_engineering_check` UNIVERSAL: pernos/soldaduras/L10/pandeo/vuelco; uniones
  sin dimensionar se AGREGAN en una regla-resumen; redundante+dimensionada = **ok** con
  nota honesta — la redundancia es favorable y no accionable).
- **Reglas de conveyor** (`library/rules.py`): 13 reglas; `detect_conveyor` se enriquece
  con VARIABLES del proyecto + nombres + specs de catálogo (reconoce
  `motorreductores_sinfin`; η=0.75 sinfín vs 0.85 helicoidal); las reglas numéricas llevan
  bloque `calc` {titulo, entradas, formula, sustitucion, resultado, criterio, fs,
  norma?}. **Normativas (V5.10)**: el método de arrastre se elige POR CONSTRUCCIÓN
  (`soporte` derivado del modelo: cama/mesa → CEMA slider-bed μ=0.33, números
  HISTÓRICOS intactos; rodillos portantes → ISO 5048/DIN 22101 en
  `engineering/iso5048.py` con C(L) — L<80 m es interpolación referencial de la
  tabla); regla "adherencia del tambor motriz" (Euler-Eytelwein: T2_min =
  F_U/(e^{μα}−1), μ 0.35 engomado/0.25 liso por NOMBRE del tambor, fs solo con
  `t2_n` declarado — no se inventa la tensión del tensor); la memoria pinta "NORMA
  DE REFERENCIA" por verificación y "Normas aplicadas" en portada.
- **Requisitos** (`Document.requirements`, metadato de manifest espejo de motion):
  carga_kg, largo/ancho/alto_paquete_mm, velocidad_m_s, inclinacion_deg, temperatura_c,
  tipo_cambio (numéricas validadas) + producto/entorno/normativa/notas/moneda.
  `/api/checks`, memoria y cotización CAEN a ellos (params explícitos ganan) →
  `engineering_check()` funciona SIN argumentos.
- **Entregables**: `drawing/calc_report.py` (MEMORIA DE CÁLCULO A4: bases de diseño +
  fórmula/sustitución/FS por verificación + VEREDICTO) · `library/costing.py` (BOM
  costeado, 3 fuentes DECLARADAS por fila: specs.cost / estimación peso×material×3 /
  fabricación peso×material×2.5) · `drawing/quote.py` (COTIZACIÓN: margen/impuesto/
  moneda+fx de presentación/precio de venta/ítem más costoso/notas honestas).
- **Benchmark de entregables (V7.1)**: `scripts/benchmark_package.py` (cliente HTTP PURO —
  no importa `apolo.*`, NO dispara el reload que blanquea el DOC) regenera el paquete
  completo de un proyecto a `docs/benchmark/<proy>/<fecha>/` cronometrando cada artefacto;
  `docs/benchmark/rubrica-v1.md` (anclas duras, versionada) lo califica = test de regresión
  de CALIDAD. Correrlo + re-calificar tras cada V7.x. Testigo faja 38: `.../faja38/2026-07-10/`.

### Planos 2D (sistema PRO completo, fases A–G)
`drawing/` (compositor `SheetModel` → SVG/PDF/DXF, HLR): cotas con flechas/tolerancia/
baseline, cortes A-A/B-B/C-C por feature con rayado por material, vista de detalle,
cajetín pro con revisiones, **juego de planos** (`sheet_set`: conjunto con DESPIECE
L×A×E + globos + cédula de herraje con norma + 1 lámina por pieza con acotado AUTOMÁTICO
de agujeros + lista de corte), nesting 1D/2D, explosionada, GD&T ligero, notas de
montaje, cotas de interfaz, iso SOMBREADA a color (= colores del viewport), **planos por
INTENCIÓN** (`POST /api/drawing/spec` / tool `drawing`), **manual de ensamblaje** paso a
paso (secuencia derivada del log; `isolate` para sub-ensamblajes), **export DWG (V5.9,
`drawing/dwg.py`)**: DXF→DWG R2018 (AC1032) vía ODA File Converter con
`ezdxf.addons.odafc` — format="dwg" en el spec, `flat.dwg` de chapa y
`GET /api/drawingset.dwg` = ZIP con un DWG por lámina (DWG no es multipágina); sin ODA
→ 400 amable con la URL de descarga; `_discover()` busca la carpeta VERSIONADA del
instalador (`ODA\ODAFileConverter 27.x\`) y fija `ezdxf.options`. Detector de solapes:
`scripts/_check_overlaps.py`.

### Catálogo (data-driven, 217 refs)
- YAML en `library/data/` (prefijo numérico ordena) + builders genéricos en
  `library/builders.py`. **Para añadir partes: editar/crear YAML**; builder nuevo solo si
  la geometría no existe. `param_keys` lee del VARIANT (no de specs_common); el loader
  vuelca cualquier clave extra del variant a `specs`.
- Familias clave: rodamientos ISO 15 (41, con `C_kN`), chumaceras UCP/UCF/UCFL (15,
  cotas comerciales verificadas), motorreductores helicoidales (builder `motor`, coaxial
  SEW/NORD) y **NMRV sinfín-corona** (builder `worm_gearmotor`, eje hueco, bores
  verificados contra Motovario), perfiles/tubos HSS-A500/UPN/IPE/ángulos (con
  `cost_por_m`), poleas en V, herraje de carpintería (bisagras/split, correderas
  U-100/D-100 reales, cerraduras), pernos DIN 912/933, tensores trotadora.
- **Biblioteca paramétrica > pila de STEP**: los STEP de fabricante solo para la compra
  puntual. `cost`/`cost_por_m`/`COST_PER_KG_USD` son REFERENCIALES (comentados en YAML;
  actualizar con proveedor para cotizar en firme).

### UI web (React + three.js + Dockview)
- Shell: grid header/ribbon/workspace/statusbar; **Dockview** (viewport = centro fijo
  bloqueado que NUNCA se re-monta; layout persistido; `resetLayout` NO destruye el
  viewport). Paneles: árbol (agrupado por SUBSISTEMA, buscador, 1 línea/fila),
  Propiedades, Chat, Historial, **Requisitos** (bases de diseño + memoria/cotización
  PDF), BOM (con toggle **Costos**), Validar (pre-llenado de requisitos), Cinemática
  (estudios con chips), Ensamblaje, Física, Montaje (soundness + gravedad animada en el
  viewport). Viewport PBR (IBL, sombras, vidrio translúcido, ViewCube), atajos de
  teclado, menú contextual, feedback de carga global (`guard`/`runTracked` + BUSY_TEXT).
- Registro de un panel nuevo: `dock/dockApi.ts` TOOL_PANELS + `DockShell.tsx` COMPONENTS
  + `StatusBar.tsx` PANELS + `icons.tsx` PANEL_ICONS.
- Export: STEP/STL por endpoint; **glTF client-side** (`viewport/exportGltf.ts`,
  GLTFExporter sobre las mallas — patrón CustomEvent como `"apolo:fit"`).

## Convenciones y lecciones aprendidas

### Núcleo / rendimiento
- **OCCT no es thread-safe**: TODO acceso al documento pasa por `apolo.state.STATE_LOCK`
  (RLock). Notificar por WebSocket solo DESPUÉS de construir el payload.
- **Un lote = UN regenerate**: `execute_many`/`edit_many` = atómico + 1 undo; NO
  reintroducir `validate_params` en el bucle (el regenerate final valida en orden →
  permite `set_variable` + uso en el mismo lote).
- **Regenerate incremental**: firma acumulada por comando + checkpoints cada 16 (shallow
  copy compartiendo la referencia del shape OCCT — seguro porque ningún ejecutor muta el
  shape in-place). Editar una variable invalida desde el bloque de vars. `scene_payload`
  cachea mesh por IDENTIDAD del shape. Estado en checkpoints = 7-tupla (scene, variables,
  joints, mates, constraints, fasteners, grounds); los METADATOS de manifest (motion,
  requirements, colors, hidden, notas) NO van ahí ni al log.
- Los tests no ejecutan el lifespan de FastAPI → no tocan la SQLite (`data/apolo.db`).
  Patrón: `api.DOC = Document("t"); TestClient(api.app)`. El arranque real vive en
  `initialize_store(db_path)` (extraído del lifespan para testearlo sin FastAPI).

### Rendimiento (V6.2 — mide contra `docs/perf_baseline.json`, host-dependiente)
- **Open caliente por caché de geometría** (`doc/geomcache.py`): `pack(doc)`/`unpack(blob)`
  persisten el ESTADO regenerado (8-tupla final + definiciones canónicas de la escena)
  indexado por la firma acumulada del log. `from_apolo_bytes(warm=...)` reanuda del
  checkpoint si la firma cacheada es PREFIJO del log (replay ~0) + `check_integrity`
  cinturón-y-tirantes → si hay violaciones no-degradadas, descarta y replaya frío. Vive
  SOLO en la SQLite local (tabla `geom_cache`), JAMÁS en el `.apolo` (geometría nunca se
  guarda + pickle de origen subido = RCE). Kill-switch `APOLO_GEOM_CACHE=0`. Perderla solo
  cuesta un replay (nunca es autoritativa). Gotcha BinTools: `serialize_shape` SIEMPRE da
  bytes pero `deserialize_shape` revienta por-shape de forma caprichosa (unos round-trip-ean
  crudos, otros solo tras `BRepBuilderAPI_Copy`, la copia rompe a los primeros) → `pack`
  serializa el TopoDS CRUDO (no el wrapper build123d, que lleva joints frágiles) y VERIFICA
  cada shape deserializando: crudo→copia→None (`_serialize_robust`). Faja 38: frío 3–23 s →
  caliente 0.04 s. V6.2e: `pack` empaca el checkpoint ORGÁNICO del último comando
  (`_regen_ckpts[len-1]`, PRE-finalización), NO el estado post-mates — si no, la cola
  ejecutaría contra geometría desplazada por los mates y los selectores de posición diferirían
  del frío; devuelve None si `regen_suppressed` (doc tolerante no se cachea) o si el ckpt no
  existe. `from_apolo_bytes` con `warm`: si el regenerate sembrado LANZA (no solo si viola
  integridad) → descarta y replay frío. `ProjectStore.load` PUEBLA la caché en el open frío
  (~40 ms) — un proyecto que solo se abre nunca la poblaría vía el flush.
- **Deltas de `scene_payload`** (`api/main.py`): `_geom_rev(fid, shape)` = revisión por
  IDENTIDAD del shape (el regen incremental la preserva para lo NO re-ejecutado; editar el
  comando *i* re-ejecuta *i*..fin → esos rev suben). `scene_payload(known={"revs","defs"})`:
  las features cuya geometría el cliente ya tiene van `same:true` + solo metadatos volátiles
  (id/rev/name/color/visible/group). `POST /api/scene/delta` lo usa el refresh por WS.
  `known=None` = payload completo + `rev` aditivo. `is_guide` va también en la entrada `same`
  (V6.2e Fix 7: el toggle de guía es metadato, rev estable). V6.2e Fix 2: `SCENE_EPOCH`
  (uuid por PROCESO) en el payload; el cliente lo devuelve en el delta y, si no coincide
  (restart del API → los revs renacieron en 1 y colisionarían), el server manda el payload
  COMPLETO; `connectWs` fuerza refresh completo en cada RECONEXIÓN. UI: `mergeSceneDelta`
  (store) hereda la geometría anterior; el viewport diffea por `rev` (builtRef Map) → solo
  reconstruye la pieza cambiada, la apariencia se rehace en sitio (`applyAppearance`). Hook E2E
  `window.__apolo` (meshIds/builds/store). Layout 53: 1.1 MB → 31 KB sin cambios.
- **Dos-locks render/física** (`RENDER_LOCK` en `render_vtk.py`, `PHYSICS_LOCK` en
  `api/main.py`): regla de oro — bajo STATE_LOCK se EXTRAE geometría (OCCT: teselado/cascos
  → datos PUROS); fuera solo se procesan arrays. `render_scene_vtk` → `extract_render_scene`
  (STATE_LOCK, con `_RENDER_MESH_CACHE` por id(shape)) + `render_snapshot_vtk` (RENDER_LOCK).
  `stability_test`/`drop_test` → `prepare_*` (XML MuJoCo horneado, STATE_LOCK) + `simulate_*`
  (bucle mj_step, PHYSICS_LOCK); wrappers para compat. Mutación durante render/gravity < 1 s.
  Follow-up: `export_stl`, `drawing_spec` (su HLR es OCCT, no puede salir del lock).
- **Autosave debounced** (`_AutosaveScheduler` en `api/main.py`): `_autosave()` ya NO escribe
  inline — marca sucio + arma un flush ÚNICO (debounce 500 ms, techo 3 s). `_flush_body` toma
  `to_apolo_bytes()` + `pack()` + STORE/PROJECT_ID BAJO STATE_LOCK (snapshot atómico) y escribe
  SQLite FUERA (durabilidad V6.1 intacta: reintentos, `AUTOSAVE_ERROR` + WS — también ante
  fallo de SERIALIZACIÓN; la caché de geometría es best-effort aparte). V6.2e Fix 1: ORDEN
  ÚNICO DE LOCKS `_flush_lock → STATE_LOCK` (jamás al revés → sin deadlock switch↔Timer);
  `_flush_lock` se sostiene TODO el flush (reintentos incluidos) → sin carrera de bytes viejos
  pisando nuevos; el cambio de proyecto usa `_project_switch()` (flush del doc actual + swap
  ATÓMICO bajo ambos locks → sin corrupción cruzada A/B). `pending()` = sucio O flush en vuelo.
  Flush FORZOSO en shutdown/restore; `GET /api/health` → `autosave_pending`. Tests:
  `_flush_autosave()` antes de leer disco; fixtures con STORE hacen `_autosave_sched.cancel()`
  en teardown. Ráfaga de 20 mutaciones = 1 escritura.

### Robustez / integridad (V6.1 — «nada tumba el documento»)
- **`Document.check_integrity() → list[str]`** (READ-ONLY puro, no muta ni cachés):
  invariantes accionables (features↔comando vivo, refs de juntas/mates/fasteners/grounds,
  parents/ciclos de grupos, ckpts bien formados, seq monótono, variables coherentes). Una
  entrada con prefijo `"degradado: "` NO es error (instancing perdido por evicción de
  DEFINITIONS; el fallback de render lo cubre). `GET /api/health` la expone
  (`ok/issues/degraded/suppressed_commands/autosave_failed/startup_error`); sin tool MCP.
- **Modo estricto** (`document._STRICT`, env `APOLO_STRICT=1`): tras cada mutación, si hay
  violaciones NO-degradadas → rollback + DocumentError. La tortura lo activa por
  monkeypatch del ATRIBUTO (se lee como global del módulo, no se captura en local).
- **`regenerate(tolerant=False)` es ATÓMICO**: todo se construye en LOCALES y solo al
  final, en UN bloque que no puede lanzar, se vuelca a `self` (si algo revienta —executor,
  ref colgando, mates, `resolve_all`— `self` queda INTACTO). `tolerant=True` (SOLO cargas)
  SUPRIME el comando roto → `regen_suppressed` [{command_id,type,error}] y poda huérfanos;
  el LOG jamás se toca. Las MUTACIONES cargan SIEMPRE estrictas.
- **El snapshot de undo incluye la caché de regen** (`"regen"`): `_restore` la repone
  ANTES de regenerar → el rollback resume del último checkpoint del log viejo (replay ~0)
  e inmune a un fallo repetido. `undo/redo` son peek-then-commit (no sacan de la pila hasta
  saber que la restauración sobrevivió). `_UNDO_CAP=50` (los snapshots retienen shapes).
  Blindaje: ckpts corruptos → replay completo, NUNCA se lanza por culpa de la caché.
- **Carga tolerante SOLO en rutas de carga** (arranque, open by id, upload, restore):
  `from_apolo_bytes(..., tolerant=True)` / `ProjectStore.load(..., tolerant=True)`; el
  payload lleva `suppressed_commands` + la UI un chip. Guardia de seq en `from_apolo_bytes`
  (`max(seq, len(commands), max c-id)`) → sin colisión de ids aunque el log tenga huecos.
- **Autosave durable** (`_autosave`): reintentos `(0,0.1,0.5)` s; agotados → `AUTOSAVE_ERROR`
  en el payload + WS `autosave_failed` (el cliente SE ENTERA de que memoria ≠ disco).
  Arranque sano: reciente corrupto → tolerante; si ni así abre → `STARTUP_ERROR` + doc
  vacío con `PROJECT_ID=None` (NO crea «Sin título» que pise el reciente). `project/new` y
  `project/open` (upload) crean id PROPIO (antes: el autosave pisaba el proyecto anterior).
- **Tortura** en `tests/test_torture.py`: acotados sin marca (corren siempre), extendidos
  `@pytest.mark.torture` (`pytest -m torture`; el `addopts = -m "not torture"` los excluye
  por defecto — el conteo normal no baja). Baseline de perf en `docs/perf_baseline.json`
  (regenerado con `scripts/perf_baseline.py`, máquina-dependiente).
- **Errores accionables de OCCT** (Fix H): fillet/chamfer nombran el TOPE (arista más
  corta seleccionada) al fallar; `shell` pre-valida por bbox (`2·espesor ≥ dimensión
  menor` → rechazo limpio ANTES de OCCT, condición NECESARIA sin falsos positivos). La
  positividad ya la da pydantic (`gt=0`); no se blinda geometría fina (radio vs. caras
  vecinas) para no arriesgar falsos positivos — el `try/except` de OCCT queda de red.

### Paramétrico / modelado
- **Disciplina paramétrica**: cota que no cuelga de variable/expresión NO sigue los
  cambios. Los `create_*`, super-comandos Y `run_script` cascadean: el `run_script` SÍ ve
  las variables del proyecto vía `V["nombre"]` (el sandbox inyecta `V = resolve_all(vars)`;
  `test_script` también) → escríbelo con `V[...]`, no con literales (el gap de la faja 38
  era de AUTORÍA, no de mecánica — corregido en V6.4b). GOTCHA del shift: `Pos(...)*result`
  falla si `result` es una ShapeList (partes disjuntas = lista); traslada a nivel de
  coordenada (`Pos(x+dx,...)*shape`) o compón un Compound. Al reparametrizar, ojo con
  piezas que dependían de OTRA que sí se movió (un puntal que apunta a una pata).
- **Expresiones con CONDICIONALES (V6.4a)**: los campos `=expr` aceptan ternario
  `a if cond else b` (PEREZOSO — la rama no tomada no se evalúa), comparadores
  `< <= > >= == !=` (encadenados) y `and`/`or` — para tablas de diseño
  («`=3 if largo_total>3500 else 2`»). Sin strings/listas/`in`/`is`/lambda.
- **Tablas de diseño (variantes, V6.4c)**: `Document.configurations = {variante: {var: expr}}`
  (metadato de manifest). `save_configuration` captura el snapshot ACTUAL; `set_configuration`
  (`PUT /api/configurations/{name}`) edita una variante con `{var: expr}` EXPLÍCITO SIN
  aplicarla (valida existencia/parseo/ciclos); `apply_configuration` reescribe las variables y
  regenera TODO (un solo undo). Payload `configuration_values` alimenta la grilla variables×
  variantes del VariablesDialog (celdas editables → PUT). Tools MCP `save_configuration`/
  `apply_configuration`. Puente requisitos→variables EXPLÍCITO (botón «→ var» en Requisitos =
  crea el `set_variable`): NUNCA implícito (`=req.x`) porque los requisitos son metadato FUERA
  del log → un puente implícito no cambiaría las firmas del regenerate = geometría stale.
- **Nombres por ROL, no por medida** («Larguero (+Y)», nunca «80x40x3»): la medida es
  dato derivado (árbol/BOM la calculan en vivo). EXCEPCIÓN: grado de material («A36») y
  nameplate («1.5HP 1750rpm») que el sistema LEE del nombre.
- Componentes de catálogo: `position` = centro del bbox; **`insert_component` de un
  builder con origen propio coloca el ORIGEN LOCAL en `position`** (p. ej. el barreno del
  NMRV). Perfiles se extruyen en Z (rotar 90° sobre Y → larguero en X).
- **Builders**: todo término empieza con `Pos(...) *` (un `Rotation(...)*shape` pelado da
  `ValueError: other must be a list of Locations`); piezas de un MISMO sólido deben
  SOLAPAR 0.5–8 mm (tangentes → Compound; disjuntas → ShapeList sin `.volume`);
  `build_component(ref, L)` ignora `L` si el componente no es `cuttable`.
- Caja orientada en el espacio: `Rotation(0, ry, rz)` con `rz=atan2(Δy,Δx)` (rumbo) y
  `ry=-atan2(Δz,√(Δx²+Δy²))` (cabeceo) — verificada por bbox en `test_script`.

### Cirugía de modelos (event-sourced)
- Para canjear sub-ensamblajes: **borrar el sub-grafo COMPLETO de comandos** con
  `POST /api/commands/remove` (atómico; incluir piezas + FIJADORES juntos para no dejar
  referencias colgando; primero `DELETE /api/fasteners/{name}` de los auto-declarados).
- **NUNCA `boolean_op` para tallar una pieza referenciada por juntas**: consume el target
  y reasigna el id → usa `add_joinery` (muta EN SITIO, conserva id). Para taladros en
  raíces de junta: `dowel`/`rebaje`.
- Para ANULAR un corte booleano obsoleto sin romper ids: mover el TOOL fuera del sólido
  (cut tolera tool no-intersectante).
- Editar `position` por REST la REEMPLAZA entera (reenviar x,y,z); la tool MCP
  `edit_command` fusiona (merge) por defecto.
- Lotes grandes por HTTP secuencial superan el timeout de 180 s del cliente aunque el
  servidor termine → lotes (`run_batch`/`edit_batch`) o timeout ≥540 s.

### Ingeniería mecánica (lecciones de diseño)
- Bisagra de pliegue: el eje va en la **CARA hacia la que pliega** (offset ±esp/2), no en
  el centro; el Ø del barril es el tope físico del cierre entre hojas.
- Mecanismos de lazo cerrado (bifold): el ángulo del pivote NO es monótono → manejar por
  el recorrido del carro y resolver (θ1,θ2) con `least_squares` + continuación.
- Una **faja en V va en el lado RÁPIDO** (motor→reductor), nunca en el lado lento/alto
  par (ahí: cadena o acople directo). Un **tambor MOTRIZ necesita eje VIVO + chumaceras**
  (el take-up de eje fijo es para rodillos libres/de cola; accionamiento en cabecera,
  tensado en cola). El anti-giro de un shaft-mount es un **disco de reacción atornillado
  a la brida** con el barreno librando el eje y anclaje DESFASADO (palanca).
- Una **guarda** se abre al lado máquina, se SOPORTA al bastidor con ménsulas y se
  ATORNILLA (desmontable); NUNCA fijarla a piezas que giran (la autodetección por
  contacto lo hace mal — corregirlo).
- Camino de carga: apóyate en una **columna** cercana (pata a piso) antes que colgar de
  un tubo de pared fina; una ménsula debe **lapar/apoyar en cara plana**, no enterrar un
  canto. Chumacera de PIE (UCP) exige base horizontal (si el eje corre junto a un alma
  vertical: ménsula soldada, o chumacera de BRIDA UCF/UCFL).
- Antes de «mover para dar holgura», confirmar el EJE real del conflicto (un huelgo en Y
  no se arregla moviendo en Z). A veces el fix es REPOSICIONAR la pieza (elevarla sobre
  el componente nuevo), no modificar lo que estorba.
- **Curar la conectividad auto-detectada** es tan importante como dimensionarla: un
  fastener "soldadura" entre la banda y la mesa es un error de MODELO (reclasificar a
  `contacto` con `edit_batch`). Al mover/encoger una pieza, revisar las que se anclaban a
  ella (la unión declarada sobrevive aunque la geometría se separe — gravity valida en
  falso).
- Engrosar un miembro cascada a su herraje y holguras vecinas: reposicionar, no solo
  cambiar la sección.

### Entorno / operación (Windows)
- **Editar solo YAML NO recarga el worker** (`--reload` vigila `.py` y va por CONTENIDO):
  tocar un `.py` o reiniciar. Sin `--reload`, reiniciar SIEMPRE tras cambios.
- **Zombie-socket :8000**: un `multiprocessing.spawn` huérfano (hijo de un uvicorn
  muerto) retiene el handle y sirve código VIEJO — un "reinicio" sin verificar el dueño
  real VALIDA EN FALSO. Detectar: `Get-NetTCPConnection -LocalPort 8000` + buscar en
  `Win32_Process` el `--multiprocessing-fork` con parent muerto; matarlo (o todos los
  python del venv).
- **Cirugía + `--reload`**: cualquier script offline que `import apolo.*` recompila
  `.pyc` → recarga el worker → blanquea el DOC en memoria. El autosave SQLite ya guardó:
  `open_project(id)` recupera. Dos ediciones `.py` seguidas = dos reloads: si el 2º
  interrumpe el load del startup (KeyboardInterrupt a medio regenerate), el fallback
  CREA un proyecto "Sin título" vacío y lo deja como reciente — reabrir el real y
  borrar el basura desde la UI.
- Fotografiar piezas = `render_view(isolate=…, zoom)`, NO ocultar/restaurar en vivo.
- Flujo con el usuario: él testea la UI a mano; los errores caen en `logs/errors.log`;
  al decir «revisa» → leer, agrupar por causa raíz, parchear y limpiar el log.

### UI
- **Contención de layout**: toda región scrollable/flex necesita altura ACOTADA
  (`minmax(0,1fr)`); una fila implícita `auto` crece hasta el hijo más alto y desborda.
  Los `grid-row` numéricos son frágiles al cambiar `grid-template-rows` (reindexar).
  `overflow: hidden auto` para matar la barra horizontal fantasma.
- `npm run dev` + StrictMode remonta el viewport y lo rompe → `vite preview` (config
  `ui-preview`). El screenshot automatizado del viewport se agota por el rAF continuo:
  verificar por DOM/snapshot (además el rAF se PAUSA en pestaña de fondo → `g.visible` que
  fija el animate loop queda stale, y `await requestAnimationFrame` en `preview_eval` cuelga;
  para verificar lógica de overlay, leer `ctx.handles.children`/params vía `preview_eval`
  exponiendo `ctx`+`useStore` a `window`, no la visibilidad).
- **`editCommand` de la UI (PUT `/api/commands/{id}`) por defecto REEMPLAZA los params, no
  mergea** (el default REST es `merge=false`; solo la tool MCP hace PATCH). Un edit PARCIAL
  —estirón de caja `{width}`, cota exacta `{height}`— BORRA los params hermanos (height/name/
  position caen al default del schema → la caja colapsa y `isAxisAligned` falla → los tiradores
  del overlay no reconstruyen). Los edits de cota de `create_box` pasan `merge=true`
  (`api.editCommand(id, params, transient, merge)`); los forms schema-driven mandan todos los
  campos → replace es inocuo ahí.
- **Sync de manipulación directa (coalescing, `store.ts::pumpEdit`)**: los estirones/cotas commitean
  con `editCommandSilent` (cola por command_id, el ÚLTIMO gana: 1 en vuelo + 1 pendiente). GOTCHA:
  la escena que devuelve el servidor se aplica SOLO si NO hay una edición más nueva en cola
  (`!editPending.has(id)`); si se aplicara la respuesta INTERMEDIA, el preview PARPADEARÍA a un tamaño
  viejo antes de llegar al final. El preview optimista (mesh escalado + `rebuildOverlayFromMesh`) se
  mantiene hasta la respuesta ÚLTIMA. Los transforms (mover/rotar/subir-Z) van por cola SERIALIZADA
  (`enqueueSilent`, son deltas) → ahí cada escena SÍ se aplica (estado acumulado correcto, sin parpadeo).
- **WebSocket `document_changed` DEBE debouncearse (`store.ts::connectWs`)**: el servidor emite
  `document_changed` por CADA comando (incluidos los NUESTROS) → un `refresh()` por evento reproducía
  cada tamaño intermedio (2º camino del PARPADEO, INDEPENDIENTE de `pumpEdit`; el `if (!busy)` viejo NO
  lo frenaba porque el sync silencioso mantiene `busy=false`). Fix: debounce 250 ms + gate
  `if (s.busy || s.syncing > 0) return` (no refrescar mientras haya ediciones silenciosas propias en
  vuelo — su respuesta ya trae la escena final; los cambios EXTERNOS del agente/MCP/otro cliente se
  refrescan al calmarse). Lección: al depurar «flicker» de sync hay DOS caminos que aplican escena
  (respuesta de `editCommand` + refresh del WS) — revisar AMBOS.
- **Tinte rojizo = SOLO guardado FALLIDO** (`Viewport.tsx::applyBlockedTint`): tiñe únicamente piezas
  en `blockedRef` (guardado que falló y se reintenta → aviso de «no está en disco»). Se RETIRÓ el
  tinte «guardando» de 400 ms (`saveTintFid`/`withSaveTint`): en modelos grandes el regen supera 400 ms
  y prendía en CADA edición → parecía un spinner de carga permanente que el usuario no quería.
- **Agarrar-y-mover con DEAD-ZONE (`Viewport.tsx`, `movePick`)**: al hacer pointerdown sobre un
  sólido se SELECCIONA y se arma un `movePick` PENDIENTE (`active:false`); el arrastre real (mover
  la pieza + `transform`) solo se activa al superar `DRAG_THRESHOLD_PX = 5` px (= umbral de
  `onClick`). Bajo el umbral, el pointerup es solo un CLIC → no mueve ni comitea (antes: cualquier
  temblor de 1-2 px movía la pieza, porque el commit-guard era 0.01 mm en MUNDO, no en pantalla).
- **Overlay de tiradores de caja (`handles.ts::boxDimsFromBbox`)**: la puerta ya NO es
  `isAxisAligned` contra params — deriva las dims del BBOX y sana cotas borradas (cajas víctimas
  del bug de replace recuperan tiradores y se auto-sanan al primer estirón vía el merge). Excluye
  cajas ROTADAS (param numérico que no cuadra con su eje → OBB pendiente) y PARAMÉTRICAS (cota
  `"=expr"` → no romper el vínculo con variables). Añade LÍNEAS GUÍA punteadas (rectángulo de base
  + eje vertical central, `guideLines()` en Viewport, `depthTest` off, `raycast` no-op, geometría
  disposada en el clear por `kind:"guide"`) para leer la caja en el espacio (estilo TinkerCad).
- **Contorno de selección (silueta, estilo TinkerCad)**: el viewport renderiza por un
  `EffectComposer` (`Viewport.tsx`, NO `renderer.render` directo): `RenderPass` → `OutlinePass`
  (silueta cian `visibleEdgeColor` — SOLO el contorno proyectado de la pieza, no las aristas
  interiores que ve la cámara) → `OutputPass`. Reemplazó el viejo tinte `emissive` de selección
  (`applySelection`, borrado) y el pre-resaltado de HOVER (`hover.ts`, borrado — el glow emissive
  al pasar el cursor «prendía» la pieza; el contorno de selección ya basta). Las mallas
  seleccionadas se recolectan CADA frame en el animate
  (`selMeshes` desde `selectionRef` → robusto a reconstrucciones). Gotcha crítico: el RT del
  composer DEBE ser `HalfFloatType` + `samples:4` — HalfFloat preserva el HDR lineal para que
  `OutputPass` aplique ACES+sRGB al final (sin doble tone-mapping: three NO tonemapea al renderizar
  a un RT ≠ null), y `samples:4` conserva el MSAA que el composer perdería si no. El ViewCube sigue
  dibujándose tras `composer.render()` (autoClear=false). El tinte rojizo de "guardando" (`applySaveTint`)
  es INDEPENDIENTE (clona material + emissive) y coexiste con el contorno. GOTCHA del FONDO: el
  `OutputPass` tonemapea TODO el frame incluido el color de limpiado (el render directo NO lo hacía) →
  el fondo salía teñido de gris. Solución: el canvas es TRANSPARENTE (`alpha:true` + `setClearColor(
  BACKGROUND, 0)`) y el color de fondo lo pinta el `<div>` contenedor por CSS (`mount.style.background
  = BACKGROUND_CSS`) → el fondo NO pasa por el tone-mapping y queda EXACTO (0x1b1e24 = rgb(27,30,36)).
  `BACKGROUND`/`BACKGROUND_CSS` en `scene-setup.ts` = fuente única. Las mallas OPACAS se dibujan sobre
  la transparencia (verificado: centro opaco, esquinas alpha 0 → se ve el CSS).

### Mantenimiento de este CLAUDE.md (responsabilidad del agente)
Actualízalo al cerrar trabajo relevante, pero **CONCISO**: una entrada nueva = 2-6
líneas (qué existe, dónde vive, el gotcha si lo hay) en la sección que corresponda del
mapa/convenciones + actualizar los conteos de "Estado actual". La NARRATIVA larga
(verificación E2E, decisiones con contexto, cirugías) va en el mensaje de COMMIT y, si
amerita, se appendea a `docs/devlog.md`. No duplicar: si una lección ya existe, afinarla
en su sitio. Este archivo se carga en CADA sesión — cada línea cuesta contexto.

## Objetivo final — doctrina de RESULTADOS (usuario, 2026-07-10)

Apolo **NO persigue paridad de herramientas** con SolidWorks/Inventor: esas son
herramientas PARA HUMANOS (manipulación manual) y ese costo nos lo ahorramos. El objetivo
final es que el **ingeniero digital (agente IA) entregue RESULTADOS iguales o MEJORES que
lo que un despacho competente TERMINA en SW/Inventor**: 3D validado + juego de planos de
taller + memoria de cálculo + BOM/cotización + manual. La vara es el ENTREGABLE terminado
(calidad Y tiempo), no la lista de features. Corolarios:
- Una función solo importa si mejora un entregable final; las que existen para trabajo
  manual humano NO se portan.
- La madurez se mide con **benchmarks de entregables** (misma máquina: paquete Apolo vs
  paquete terminado a mano en SW/Inventor), no solo por ejes de features.
- Donde el incumbente no entrega nada INTEGRADO (memoria de cálculo con normas,
  cotización, validación de sujeción/gravedad) Apolo ya supera; donde el humano pule a
  mano (el último kilómetro del plano: soldadura ISO 2553, tolerancias generales ISO
  2768, acabados, criterio de acotado) Apolo debe cerrar la brecha con CRITERIO
  automático — es exactamente donde un agente con guidelines brilla.

## Madurez — línea base (act. 2026-07-10, escala vs incumbente maduro = 10)
Cuando el usuario pregunte cómo madura Apolo, comparar contra esto Y contra la doctrina
de RESULTADOS de arriba. Veredicto por FEATURES: como CAD GENERAL ~10-15 % de SW/Inventor
(kernel nivel FreeCAD — una CUÑA, no un reemplazo); como herramienta del VERTICAL cubre
~80 % del flujo autónomo — categoría que los grandes no ocupan. Ejes: IA-nativa/API-first
**9.5** (el moat) · kernel OCCT 6.5 · paramétrico 6.5 (V6.4: condicionales + faja 38 100 %
paramétrica + tablas de diseño) · croquis 5 (PlaneGCS; falta arrastre
en vivo) · ensamblaje 6 (V6.3: multi-mate + conectores por ancla/arista + reporte de DOF;
soundness/gravity sigue siendo único) · planos 6.5 · simulación 4.5 (analítico+MuJoCo+FEA
lineal; falta contacto/no-lineal) · negocio 6.5 · interop 6 · rendimiento 6 (V6.2) ·
robustez 6 (V6.1) · CAM 0 (deliberado) · colaboración/ecosistema 1.
Veredicto por RESULTADOS (**MEDIDO** en V7.1 + re-auditoría, **re-calificado tras V7.1c** —
benchmark testigo de la faja 38 vs la rúbrica-v1 de nivel despacho;
`docs/benchmark/faja-paqueteria-4m/2026-07-11/calificacion.md`, base honesta = el 62 %
re-auditado, no la autocalificación 67 %; producido de punta a punta por API en ~7 min
autónomo — la métrica de TIEMPO es ~10³× a favor, estimado): global del paquete ≈ **68 %**
de nivel despacho (era 62 %). Memoria de cálculo = **80 %** (V7.1c: lee del MODELO — 6 patas,
2 largueros, eje Ø35, L10 con la tensión de banda (T1+T2)/2; falta citar norma en las 15
verif. cuantitativas para subir E3.3) · BOM/cotización = **75 %** (fiel, pesos exactos,
fuentes/márgenes declarados) · 3D validado = **81 %** (V7.1c: 24 pernos de anclaje —patrón
c1114 paramétrico— y c704 declarado → **0 flotantes**) · **planos de taller = 53.6 %** (V7.1c
subió E2.1/E2.6: compras fuera de la lista de corte y de las láminas —juego 32→22 pág—,
títulos reales, cédula = BOM; SIGUE siendo la brecha top: falta el último kilómetro ISO
2553/2768/acabados/datums) · manual = **50 %** (paginado por sub-ensamblajes; falta orden por
grafo de soporte) · **FEA firmable ~45 %** (falta ensamblaje/contacto) · render comercial
~50 % (por demanda). La brecha top sigue siendo planos → **V7.2 «último kilómetro» es LA
prioridad** (memoria-lee-del-modelo YA cerrada en V7.1c).

## Hoja de ruta V6 — «Apolo industrial» (doctrina 2026-07-04)

El roadmap V5 (completitud de FLUJO del vertical) está **agotado**: lo que quedaba
(superficies básicas, render bonito, plantillas de plano) es POR DEMANDA, no bloqueante.
V6 ataca los ejes de MADUREZ más débiles del propio CLAUDE.md, empezando por el menos
vistoso y más pro. Criterio de «hecho» = el de V5 **+ la tortura y el health quedan
verdes**. Un ítem por vez, con plan formal.
- **V6.1 Robustez** — **HECHO (2026-07-04)**: «nada tumba el documento» (`check_integrity`
  + `APOLO_STRICT` + health + tortura + regenerate atómico + carga tolerante + autosave
  durable). 3→6. Detalle: § Robustez/integridad.
- **V6.2 Rendimiento** — **HECHO (2026-07-09)**: caché BREP (open 3–23 s→0.04 s) + deltas
  de escena (1.1 MB→31 KB) + dos-locks + autosave debounced. 4→6. Detalle: § Rendimiento.
- **V6.3 Ensamblaje pro** — **HECHO (2026-07-09)**: multi-mate (DAG multi-padre) +
  conectores por ancla/arista circular + reporte de DOF. 4.5→6. Detalle: § Ensamblaje.
- **V6.4 Paramétrico profundo** — **HECHO (2026-07-10, remate V6.4d)**: expresiones con
  condicionales + faja 38 100 % paramétrica (log 701→312, juntas con expresiones, tren
  motriz sigue a `largo_total`) + tablas de diseño (variantes E2E «4m»↔«3.2m»). 5→6.5.
  Detalle: § Paramétrico/modelado y follow-ups en Pendientes.
- **V6.5 MCP a escala** — **HECHO (2026-07-10)**: lectura acotada/paginada + summary por
  grupo + `near`/interferencia acotada + `snap_to`/`verify` + preview con datos; rutina
  < 10 KB a 1000 piezas. Detalle: § Lectura a ESCALA.
- **V6.5b MCP: acción con contrato** — PLANEADO (`docs/plans/V6.5b-mcp-accion-con-
  contrato.md`, ejecutar DESPUÉS de V7.2 — ambos tocan api/main.py): `expect` en
  run_batch/edit_batch (aserciones de `verify` con rollback atómico si fallan),
  comando `join_bolted` (taladros alineados + pernos de catálogo + fasten en 1),
  errores 404 con «¿quisiste decir…?», briefing compacto en `open_project`.
- **V6.6 Croquis vivo** — arrastre soft-constraints, splines/elipses. 5→6.5.
- **V6.7 FEA de ensamblaje (bonded)**. 4.5→5.5.

## Hoja de ruta V7 — «Resultados sobre el incumbente» (doctrina 2026-07-10, tras V6)

Ejecuta la doctrina de RESULTADOS: cerrar los entregables donde el paquete Apolo aún
pierde contra el terminado a mano en SW/Inventor. Definir cada ítem con plan formal al
cerrar V6; orden tentativo por impacto en el entregable:
- **V7.1 Benchmark testigo** — **HECHO (2026-07-10)**. Paquete completo de la faja 38 por
  API en 411.9 s autónomo (24/24 artefactos, `docs/benchmark/faja38/2026-07-10/`),
  calificado contra `rubrica-v1.md` con spot-checks; la RE-AUDITORÍA (regla 3) corrigió la
  autocalificación 67 %→**62 %** y cazó: memoria con defaults contra el modelo (8 patas vs
  6, Ø30 vs 35, L10 sin tensión de banda), lista de corte con compras, 5 placas con 3/4
  pernos, `c704` flotante. Detalle: calificacion.md + devlog.
- **V7.1c Fixes de la re-auditoría** — **HECHO (2026-07-11)**. Brechas 9-13 cerradas, 62 %→
  **68 %** (re-calificado en `docs/benchmark/faja-paqueteria-4m/2026-07-11/`): la memoria lee
  del MODELO por ROL (`_LEG_RE`/`_LARG_RE`/`_EJE_RE`, L10 con `(T1+T2)/2`); cirugía 38 (24
  pernos paramétricos + `c704` declarado → 0 flotantes); compras fuera de lista de corte y
  láminas (juego 32→22 pág, por `_PURCHASE_RE`); script endurecido (exit≠0, gate `--expect`,
  `--out` por slug, `--checks`). Detalle: calificacion.md 2026-07-11 + devlog.
- **V7.2 Último kilómetro del plano** — **EN CURSO (Opus, plan
  `docs/plans/V7.2-ultimo-kilometro-plano.md`)**: símbolos de soldadura ISO 2553 en el GA
  (los datos throat/length YA existen en `DOC.fasteners`; gotcha: el drawing layer no los
  recibe — cablearlos), ISO 2768-mK en cajetín, acabados ISO 1302 por proceso inferido +
  Ra 1.6 en asientos con fit (las primitivas GD&T existen SIN cablear en
  `dimensions.py:131-172`), acotado por FUNCIÓN (datum = cara de montaje + diagnóstico de
  callouts ausentes en ménsulas). Objetivo medible: E2 2.14→≥2.85 (~71 %), global ~73-75 %.
- **V7.2b Barrida de residuos baratos** (tras V7.2; juntos suben el global a ~78-80 %):
  (1) manual por GRAFO DE SOPORTE (no orden del log; chumaceras antes que el motor que
  soportan) + texto específico por paso + fusionar pasos huérfanos de 1 pieza — manual
  50 %→~75 %; (2) citar NORMA en las 15 verificaciones cuantitativas de la memoria (hoy
  4/15, E3.3) — memoria 80 %→~85-90 %; (3) lints pre-entrega: «barreno sin perno» y
  «pieza sin grupo NI unión declarada» (habrían cazado solos los defectos del 38);
  (4) E1 residual: pernos de anclaje → catálogo DIN 933, fit ISO 286 del eje del tensor
  para sus 6207 (mata los 2 avisos vivos de la memoria).
- **V7.3 Stack-up de cadenas de cotas** (análogo a TolAnalyst pero automático): el
  agente verifica que la suma de tolerancias de la cadena cierra el ajuste declarado.
  Natural DESPUÉS de V7.2 (usa los datums/fits que V7.2 cablea).
- **V7.4 FEA firmable** (absorbe V6.7 si no se hizo): ensamblaje bonded + reporte
  integrado a la memoria. FEA firmable hoy ≈45 %.
- Orden V7.3 vs V7.4: decidir por demanda del negocio al cerrar V7.2b.

## Hoja de ruta V5 — AGOTADA (completitud de flujo del vertical)
Doctrina (usuario): el ingeniero del vertical **nunca necesita SW/Inventor** — completitud de
FLUJO (~40 funciones agente-nativas: comando schema-driven + lectura MCP + verificable), no
paridad de 3000. **Todo V5 está HECHO** — Tier 1: croquis PlaneGCS · sub-ensamblajes +
insert_project · modelado directo · ISO 286 · chapa avanzada. Tier 2: superficies · FEA lineal ·
roscas · ingletes · export DWG. Tier 3: normas CEMA/ISO 5048. El detalle de cada ítem vive en su
sección del Mapa y en git/devlog. Lo que resta del Tier 3 (render fotorrealista, PDM, plantillas
de plano por empresa) es POR DEMANDA. Criterio de "hecho": usable por chat/MCP + schema-driven +
tests + E2E real; un ítem por vez con plan formal.

## Pendientes (follow-ups vivos, por demanda)
- **Cinemática/ensamblaje**: LAZOS CERRADOS de mates (A↔B, hoy rechazados como ciclo — el
  multi-mate V6.3 solo abre DAG multi-padre); master-slider "Apertura %", exportar vídeo del
  motion; anclas en más familias de catálogo (por demanda); DOF con residuo del solver
  persistido (hoy el `overconstrained` del solver no se guarda: el conteo Grübler es el signal
  en vivo, pues el solver ya rechaza los conflictos reales en la mutación).
- **V6.3d (follow-ups anotados de la revisión)**: (1) **`mirror` no propaga anclas** —
  reflejar un frame invierte la mano del eje; se omite deliberadamente (duplicate/pattern SÍ
  las heredan desde V6.3d Fix 2). (2) **Divergencia anti-paralela del multi-mate**: los
  residuos de `paralelo`/`concentrico` aceptan ejes INVERTIDOS (solo penalizan la
  colinealidad, no el sentido); el camino cerrado 1-mate SÍ fija el sentido → al BORRAR un
  mate de un hijo multi-mate la pieza puede «saltar» 180°. (3) **Tolerancia angular ×L** en
  hijos muy grandes (~4 m): el residuo angular escala con el brazo → afinar el peso relativo
  posición/ángulo del `least_squares` por tamaño del sólido. (4) **`EdgeSelector` compartido**:
  los modos `ancla`/`entidad` (conectores de mate) contaminan el schema de `fillet`/`chamfer`/
  etc. donde no aplican — hoy dan error CLARO (no silencioso); separar el schema por demanda.
- **Validación**: agrupar mitades A/B de bisagra; voladizo real del eje motriz; `torque` en tornillería; coherencia `fasten size` ↔ taladro roscado cercano.
- **Geometría/catálogo**: cola de milano/ingletes de CARPINTERÍA; canteado; chapa (child >1 nivel, hem 180°, alivios, editor de flaps); coping/notching grado ≥3; chaveta en bores; más familias.
- **Física**: cascos convexos en drop_test (hoy AABB), export SDF, sim en tiempo real.
- **Ingeniería/negocio**: `funcion`/rol por pieza, manual reordenado por grafo de soporte, explosionada 3D, L10 con reparto real.
- **UI**: refactor de `Viewport.tsx` (picking/medición/sección/gizmo a módulos), picker 2 sólidos para `add_joinery`, editar sweep/loft/chapa/mate desde Propiedades.
- **V6.4 (follow-ups anotados)**: (1) el **drag&drop del viewport emite `transform` con literales** — patrón sistémico que generó los ~400 comandos de escombro que V6.4b podó; hacer que el arrastre limpie/coalesca sus transforms o emita paramétrico (fuera de alcance de V6.4). (2) **import/export CSV** de la tabla de diseño. (3) **`ancho_banda` < ~540 rompe c339** (Ménsula rodillo retorno: su `depth` se vuelve ≤0 — límite pre-existente del modelo, no de V6.4; parametrizar la ménsula con piso mínimo). (4) run_scripts del motriz (c673/c703/c704) siguen `largo_total` (shift x) pero NO la ANCHURA (`ancho_banda`/`larg_inner_y` en sus coords y) ni `drum_cz` (z) — por demanda. (5) **V6.4d — cotas que quedan LITERALES a propósito** (la regla resolver-exacto-antes-de-atar lo exige): `j_mesa1..4` x (550/1452/2354/3255 = centros de sección REDONDEADOS; la fórmula de centro da 550.75/1452.25/… no-exacta → literal; benigno: la x de una junta prismática-z es ancla cinemática, mueve 0 pieza). `c120/c121` z=707 (rodillo de retorno) y `c339-342` z=737.5 (su ménsula): alturas del conjunto de retorno, CONSTANTES entre las dos variantes (no cuelgan de `largo_total`); la z de la ménsula no tiene expresión limpia → ambas literales para no divergir rodillo↔ménsula. Atar por demanda si se parametriza la altura.
- **V6.5 (follow-ups anotados de la revisión, sin código)**: (1) `get_scene(summary=true)`
  cuenta piezas ocultas/superficies/guías DENTRO de cada grupo, que el total global excluye → la
  masa por grupo puede descuadrar contra el total. (2) `near` con `limit` recorta sin declarar
  `truncado`. (3) `get_topology(only=...)` con un `only` inválido devuelve dict vacío en silencio
  (no error). (4) MCP `get_scene(ids=[])` (lista VACÍA, falsy) cae al brief completo — no es «cero
  piezas». (5) el bucle de `focus` en `interference_report` (checks.py) itera O(n²) en Python con
  skip barato; reestructurar a focus×resto cuando duela a miles de piezas. (6) NO hay índice
  espacial: `near`/interferencia son barridos O(n) sobre AABBs (medir antes de construir R-tree).
- **Perf**: absorbido por V6.2 (medir contra `docs/perf_baseline.json`).
- **V6.2e (follow-ups anotados de la revisión)**: `applyAppearance` × tinte de bloqueo — si
  una malla tintada (guardado fallido) recibe un cambio de apariencia externo, invalidar la
  entrada del mapa de tinte antes de reemplazar el material (hoy: material stale al
  desbloquear; caso estrecho); GIF de física — el bucle de compose matplotlib sigue bajo
  STATE_LOCK (la sim ya salió); `RenderSnapshot` guarda `Vector` de build123d (convertir a
  `np.ndarray` por pureza/perf); `duplicate_project` corre sin `STATE_LOCK` (pre-existente);
  wrapper `render_scene_vtk` toma RENDER_LOCK sosteniendo STATE_LOCK (footgun sin call sites,
  solo tests); snap-back del preview optimista cuando el guardado falla.

## Fuera de alcance deliberado

CAM, FEA grado Fusion (multicuerpo/contacto/no-lineal — el estático lineal de pieza ya
existe en V5.6; el resto aplazado hasta que el negocio lo pida), PCB/electrónica, nube
multiusuario, diseño generativo.
Referencia de librerías candidatas (con licencias) para futuras adopciones: ver
`docs/devlog.md` § "Catálogo de librerías candidatas".
