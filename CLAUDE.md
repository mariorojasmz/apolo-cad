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
.\.venv\Scripts\python.exe -m pytest tests -q     # 915 tests (tortura extendida: -m torture)
cd ui ; npm run build             # bundle de la UI (tsc + vite)
```

- **MCP `apolo-cad`** (`.mcp.json`) = cliente fino stdio→HTTP; **64 tools**. Requiere la
  API arriba. **El host MCP debe reiniciarse** para ver tools/firmas nuevas (registra al
  arrancar); la API sin `--reload` también se reinicia tras cambios de código.
- **Estado actual (2026-07-04)**: 915 tests (+6 de tortura extendida vía `-m torture`) ·
  66 tools MCP · 48 comandos · catálogo 217 refs · roadmaps V1–V4 completos · Frentes
  A/B/C cerrados · **TIER 1 COMPLETO**: V5.1 (croquis PlaneGCS), V5.2 + V5.2b
  (sub-ensamblajes + `insert_project`), V5.3 (modelado directo), V5.4 (ajustes ISO 286) y
  V5.5 (chapa avanzada) cerrados · Tier 2: V5.6 (FEA estático lineal), V5.7 (roscas), V5.8
  (ingletes) y V5.9 (export DWG) cerrados — superficies básicas quedan POR DEMANDA · Tier
  3: V5.10 (normas del vertical — memoria NORMATIVA) cerrado · **ROADMAP V6 «Apolo
  industrial» iniciado: V6.1 robustez industrial CERRADO** (contrato «nada tumba el
  documento»: `check_integrity` + carga tolerante + atomicidad de regenerate + suite de
  tortura + `GET /api/health`; robustez 3→6). Proyectos de
  referencia: `faja-paqueteria-4m` (id 38, 72 sólidos, memoria **APROBADO**, eje motriz
  «Ø35 h7»), `layout-planta-demo` (id 53, 149 sólidos), `biela-colisos-demo` (croquis
  dof=0), `pieza-proveedor-demo` (STEP round-trip defeatureado) y `guarda-banda-demo`
  (chapa en C con hems, DXF verificado a mano).
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

### Comandos / modelado (48 comandos)
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
  features de un comando, rechaza fuentes con juntas) + `center_in`/`distribute`
  (colocación relacional, se reevalúa al regenerar) + `duplicate_feature`.
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
- **Mates** (`assembly/mates.py`): coincidente/distancia/concéntrico/paralelo/ángulo por
  caras, re-resueltos en `regenerate` (1 mate por hijo, árbol). **Riel lazo-cerrado**
  (`add_rail_constraint`) + **N-GDL** (`add_constraint`: least_squares global;
  punto_en_recta/plano/coincidente/distancia). FK de un punto: `robotics/pose.py`.
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

### Paramétrico / modelado
- **Disciplina paramétrica**: cota que no cuelga de variable/expresión NO sigue los
  cambios. Los `create_*` y super-comandos aceptan `=expr` y CASCADEAN; los `run_script`
  NO ven las variables del proyecto (van con valor fijo → reeditar a mano al
  reparametrizar). Al reparametrizar, ojo con piezas que dependían de OTRA que sí se
  movió (un puntal que apunta a una pata).
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
  verificar por DOM/snapshot.

### Mantenimiento de este CLAUDE.md (responsabilidad del agente)
Actualízalo al cerrar trabajo relevante, pero **CONCISO**: una entrada nueva = 2-6
líneas (qué existe, dónde vive, el gotcha si lo hay) en la sección que corresponda del
mapa/convenciones + actualizar los conteos de "Estado actual". La NARRATIVA larga
(verificación E2E, decisiones con contexto, cirugías) va en el mensaje de COMMIT y, si
amerita, se appendea a `docs/devlog.md`. No duplicar: si una lección ya existe, afinarla
en su sitio. Este archivo se carga en CADA sesión — cada línea cuesta contexto.

## Madurez — línea base (act. 2026-07-01, escala vs incumbente maduro = 10)

Cuando el usuario pregunte cómo madura Apolo, comparar contra esto y reportar qué subió.
Veredicto: como CAD GENERAL ~10-15 % de la superficie de SW/Inventor (kernel nivel
FreeCAD; es una CUÑA, no un reemplazo); como herramienta del VERTICAL cubre ~80 % del
flujo real (requisitos→3D validado→planos→memoria→cotización, autónomo — categoría que
los grandes no ocupan). IA-nativa/API-first **9.5** ⭐ (el moat) · kernel OCCT 6.5
(V5.3: modelado directo básico) ·
paramétrico 5 · croquis 5 (PlaneGCS: dof/redundantes/tangencias — subió de 3 en V5.1;
falta arrastre en vivo y elipses/splines) · ensamblaje 4.5 (soundness/gravity es
único) · planos 6.5 (sistema pro A-G + ajustes ISO 286 en callouts, V5.4) · simulación
4.5 (analítico con FS + MuJoCo + FEA estático lineal de pieza con fringe, V5.6 — lo que
separa de 6+ es contacto/no-lineal/multicuerpo)
· entregables de negocio 6.5 (memoria NORMATIVA CEMA/ISO 5048 + cotización, V5.10) ·
interop 6 (STEP/STL/DXF/SVG/glTF + DWG vía ODA, V5.9) · rendimiento 4 ·
robustez **6** (V6.1: contrato de integridad + carga tolerante + atomicidad + tortura —
subió de 3) · CAM 0 (deliberado) · colaboración 1 · ecosistema 1. Vs AutoCAD: nuestros
planos se DERIVAN del paramétrico (él es lienzo 2D manual — otra categoría). Medir
progreso por PROFUNDIDAD del vertical, no por paridad de features.

## Hoja de ruta V6 — «Apolo industrial» (doctrina 2026-07-04)

El roadmap V5 (completitud de FLUJO del vertical) está **agotado**: lo que quedaba
(superficies básicas, render bonito, plantillas de plano) es POR DEMANDA, no bloqueante.
V6 ataca los ejes de MADUREZ más débiles del propio CLAUDE.md, empezando por el menos
vistoso y más pro. Criterio de «hecho» = el de V5 **+ la tortura y el health quedan
verdes**. Un ítem por vez, con plan formal.
- **V6.1 Robustez industrial** — **HECHO (2026-07-04)**. Contrato «nada tumba el
  documento»: tras cualquier fallo (excepción OCCT, comando inválido, .apolo corrupto,
  fuzzing de undo/redo, autosave caído) el doc queda ÍNTEGRO Y VERIFICABLE. `check_integrity`
  + `APOLO_STRICT` + `GET /api/health` + suite de tortura (primero roja) + atomicidad de
  regenerate + carga tolerante + autosave durable + startup sano + LRU de DEFINITIONS +
  insert_project pre-validado + WS resiliente. Madurez robustez 3→6.
- **V6.2 Rendimiento** — open frío con caché BREP por firma, deltas de `scene_payload`,
  dos-locks para gravity/render, debounce del autosave medido contra
  `docs/perf_baseline.json`. Madurez 4→6.
- **V6.3 Ensamblaje pro** — multi-mate por sólido, conectores por ancla, reporte de DOF. 4.5→6.
- **V6.4 Paramétrico profundo** — faja 38 100 % paramétrica como caso testigo, tablas de
  diseño. 5→6.5.
- **V6.5 Croquis vivo** — arrastre soft-constraints, splines/elipses. 5→6.5.
- **V6.6 FEA de ensamblaje (bonded)**. 4.5→5.5.

## Hoja de ruta V5 — "Apolo completo, agente-primero" (doctrina 2026-07-01) — AGOTADA

**Doctrina actualizada por el usuario**: la meta es que un ingeniero especializado que
usa Apolo **nunca necesite SW/Inventor para terminar su trabajo** en el vertical. NO es
paridad de las ~3000 funciones de SW: es COMPLETITUD DE FLUJO de las ~40 que un
ingeniero de máquinas usa de verdad — y cada una nace agente-nativa (comando
schema-driven + tool/lectura MCP + verificable por el agente: el ingeniero la PIDE, no
la clickea). La cuña sigue siendo el vertical; dentro de él, Apolo lo es TODO.

Ordenado por frecuencia de bloqueo real (qué obliga hoy a abrir SW):
- **Tier 1 — bloqueantes diarios**: (1) ~~croquis robusto PlaneGCS~~ **HECHO V5.1**;
  (2) ~~sub-ensamblajes de primera clase~~ **HECHO V5.2/V5.2b** (grupos + insert_project);
  (3) ~~modelado directo básico~~ **HECHO V5.3** (delete_faces + push_face);
  (4) ~~ajustes/tolerancias ISO 286~~ **HECHO V5.4** (fits + asientos + callouts);
  (5) ~~chapa avanzada~~ **HECHO V5.5** (flaps con child + cutouts en pestañas + K por
  material). **TIER 1 COMPLETO (2026-07-03)** — lo siguiente sale del Tier 2.
- **Tier 2 — semanales**: superficies básicas (boundary/fill/thicken), ~~FEA estático
  lineal~~ **HECHO V5.6** (gmsh + scikit-fem, NO CalculiX/sfepy — sin wheels Windows;
  resultado a la memoria), ~~roscas~~ **HECHO V5.7** (thread en drill_hole + callout
  + cosmético ISO 6410 + cédula), ~~weldments con ingletes reales~~ **HECHO V5.8**
  (esquinas="inglete": bisector por nodo + ángulos en BOM/lista de corte), ~~export
  DWG~~ **HECHO V5.9** (ODA File Converter + odafc; juego = ZIP por lámina).
- **Tier 3 — consolidación**: render fotorrealista (Blender headless), PDM ligero
  multiusuario, plantillas de plano por empresa, ~~normas del vertical~~ **HECHO
  V5.10** (CEMA slider-bed / ISO 5048-DIN 22101 por construcción + Euler-Eytelwein →
  memoria NORMATIVA).

Criterio de "hecho" por ítem: usable por chat/MCP + schema-driven + tests + verificado
E2E en un modelo real. Un ítem por vez, con plan formal ("procede con V5.<n>").

## Pendientes (follow-ups vivos, todo por demanda)

- **Cinemática/ensamblaje**: multi-mate acoplado por sólido (hoy 1 mate/hijo), conectores
  por ancla/arista, master-slider "Apertura %", easing/exportar vídeo del motion.
- **Validación**: agrupar mitades A/B de bisagra en el scan; voladizo real del eje motriz
  (cantilever); par de apriete (`torque`) en specs de tornillería; coherencia
  `fasten size` ↔ taladro roscado cercano (requiere matching geométrico perno↔taladro).
- **Geometría/catálogo**: cola de milano e ingletes de CARPINTERÍA; canteado; chapa:
  child >1 nivel, hem 180°, alivios de esquina, editor de flaps en Propiedades;
  coping/notching de tubos en nodos grado ≥3 (el inglete grado 2 ya está, V5.8);
  chaveta modelada en bores; prisioneros/pernos de chumacera como refs para BOM; más
  familias bajo demanda.
- **Física**: cascos convexos en drop_test (hoy AABB), export SDF sin juntas, sim en
  tiempo real.
- **Ingeniería/negocio**: campo `funcion`/rol estructurado por pieza (grafo de
  conocimiento), reordenar el manual de ensamblaje por grafo de soporte (hoy orden del
  log), explosionada en render 3D, UCFL 204/207/208 contra datasheet, L10 con reparto
  real (hoy parejo), unificación fina de reglas de flecha con carga puntual.
- **UI**: refactor del interior de `Viewport.tsx` (picking/box-select/medición/sección/
  gizmo a módulos), picker de 2 sólidos para `add_joinery`, ventanas flotantes/auto-hide
  de Dockview, editar sweep/loft/chapa/mate desde Propiedades, nodo «Uniones» en el árbol.
- **Perf**: carga inicial (OPEN) en frío y debounce del autosave → absorbidos por el
  roadmap V6.2 (medir contra `docs/perf_baseline.json`).
- **Limpieza**: proyectos basura id 26/27 y `perf-test-batch` (borrar desde la UI).

## Fuera de alcance deliberado

CAM, FEA grado Fusion (multicuerpo/contacto/no-lineal — el estático lineal de pieza ya
existe en V5.6; el resto aplazado hasta que el negocio lo pida), PCB/electrónica, nube
multiusuario, diseño generativo.
Referencia de librerías candidatas (con licencias) para futuras adopciones: ver
`docs/devlog.md` § "Catálogo de librerías candidatas".
