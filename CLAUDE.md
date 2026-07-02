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
.\.venv\Scripts\python.exe -m pytest tests -q     # 644 tests
cd ui ; npm run build             # bundle de la UI (tsc + vite)
```

- **MCP `apolo-cad`** (`.mcp.json`) = cliente fino stdio→HTTP; **62 tools**. Requiere la
  API arriba. **El host MCP debe reiniciarse** para ver tools/firmas nuevas (registra al
  arrancar); la API sin `--reload` también se reinicia tras cambios de código.
- **Estado actual (2026-07-01)**: 644 tests · 62 tools MCP · 43 comandos · catálogo 217
  refs · roadmaps V1–V4 completos · Frente A (motor de cálculo + memoria + requisitos),
  Frente B (costeo + cotización) y Frente C (uniones curadas, UI de entregables,
  export STL/glTF) cerrados. Proyecto vivo de referencia: `faja-paqueteria-4m` (id 38,
  72 sólidos, memoria de cálculo **APROBADO**).
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

### Comandos / modelado (43 comandos)
- Primitivas + croquis restringido (solver scipy) + sweep/loft/hélice (lazo cerrado,
  `is_frenet`) + chapa metálica con **desplegado DXF/SVG** (bend allowance, taladros
  proyectados al blank) + `add_joinery` (espiga/dado/dowel/rebaje — corta EN SITIO,
  conserva ids) + patrones (`count` por `=expr`; `pattern_group` arraya TODAS las
  features de un comando, rechaza fuentes con juntas) + `center_in`/`distribute`
  (colocación relacional, se reevalúa al regenerar) + `duplicate_feature`.
- **Super-comandos**: `create_conveyor` (RODILLOS), `create_belt_conveyor` (BANDA),
  `create_weldment`/`create_frame` (bastidores con lista de corte), `create_sheet_metal`,
  `create_take_up` (tensor de cola trotadora: eje fijo + perno tensor Allen horizontal
  que atraviesa el eje roscado + soporte C soldado al larguero), `create_drive_roller`
  (idem con eje largo — OJO: eje FIJO, para tambor MOTRIZ real usa eje vivo + chumaceras),
  `create_robot_arm`. Un super-comando debe documentar su MONTAJE en el description.
- `fasten`/`ground` (conectividad, `wants_connectivity`): `fasten` acepta dimensionamiento
  opcional `size`/`qty` (perno) y `throat_mm`/`length_mm` (soldadura; `throat` ES la
  garganta, a=0.707·cateto).

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
- **Interferencias**: `check_interference` (booleanas OCCT; excluye pares de junta,
  `same_command_pairs` y hardware tornillería/rodamientos) + `interpenetration_report`
  (exceso vs pose de diseño en pares con junta).

### Ingeniería / negocio (Frentes A/B)
- **`library/engineering/`** (puro): `belt` (banda-sobre-cama μ=0.33 + par de arranque
  1.6× — el μ=0.06 de rodadura queda SOLO para rodillos), `bolts` (ISO 898-1/EN 1993-1-8),
  `welds`, `bearings` (L10, `C_kN` de specs), `buckling` (Euler K=2, inercia mínima),
  `stability` (COG vs casco de apoyos), `loads` (`hanging_load_kg`: carga de una unión =
  masa que pierde tierra al quitar su arista; redundante → None), `mass`
  (`get_mass_properties`: catálogo pesa por FICHA, a-medida volumen×densidad), `report`
  (`structure_engineering_check` UNIVERSAL: pernos/soldaduras/L10/pandeo/vuelco; uniones
  sin dimensionar se AGREGAN en una regla-resumen; redundante+dimensionada = **ok** con
  nota honesta — la redundancia es favorable y no accionable).
- **Reglas de conveyor** (`library/rules.py`): 12 reglas; `detect_conveyor` se enriquece
  con VARIABLES del proyecto + nombres + specs de catálogo (reconoce
  `motorreductores_sinfin`; η=0.75 sinfín vs 0.85 helicoidal); las reglas numéricas llevan
  bloque `calc` {titulo, entradas, formula, sustitucion, resultado, criterio, fs}.
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
paso (secuencia derivada del log; `isolate` para sub-ensamblajes). Detector de solapes:
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
  Patrón: `api.DOC = Document("t"); TestClient(api.app)`.

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
  `open_project(id)` recupera.
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
los grandes no ocupan). IA-nativa/API-first **9.5** ⭐ (el moat) · kernel OCCT 6 ·
paramétrico 5 · croquis 3 (el eslabón más débil) · ensamblaje 4.5 (soundness/gravity es
único) · planos 6 (sistema pro A-G) · simulación 3 (analítico con FS + MuJoCo, sin FEA)
· entregables de negocio 6 (memoria+cotización) · interop 5.5 · rendimiento 4 ·
robustez 3 · CAM 0 (deliberado) · colaboración 1 · ecosistema 1. Vs AutoCAD: nuestros
planos se DERIVAN del paramétrico (él es lienzo 2D manual — otra categoría). Medir
progreso por PROFUNDIDAD del vertical, no por paridad de features.

## Pendientes (follow-ups vivos, todo por demanda)

- **Cinemática/ensamblaje**: multi-mate acoplado por sólido (hoy 1 mate/hijo), conectores
  por ancla/arista, master-slider "Apertura %", easing/exportar vídeo del motion.
- **Validación**: agrupar mitades A/B de bisagra en el scan; voladizo real del eje motriz
  (cantilever); par de apriete (`torque`) en specs de tornillería.
- **Geometría/catálogo**: cola de milano e ingletes; canteado; G2 chapa (cutouts
  rectangulares, K-factor por material); G3 ingletes reales en weldments; chaveta
  modelada en bores; prisioneros/pernos de chumacera como refs para BOM; más familias
  bajo demanda.
- **Física**: cascos convexos en drop_test (hoy AABB), export SDF sin juntas, sim en
  tiempo real.
- **Ingeniería/negocio**: campo `funcion`/rol estructurado por pieza (grafo de
  conocimiento), reordenar el manual de ensamblaje por grafo de soporte (hoy orden del
  log), explosionada en render 3D, UCFL 204/207/208 contra datasheet, L10 con reparto
  real (hoy parejo), unificación fina de reglas de flecha con carga puntual.
- **UI**: refactor del interior de `Viewport.tsx` (picking/box-select/medición/sección/
  gizmo a módulos), picker de 2 sólidos para `add_joinery`, ventanas flotantes/auto-hide
  de Dockview, editar sweep/loft/chapa/mate desde Propiedades, nodo «Uniones» en el árbol.
- **Perf**: carga inicial (OPEN) en frío, debounce de autosave.
- **Limpieza**: proyectos basura id 26/27 y `perf-test-batch` (borrar desde la UI).

## Fuera de alcance deliberado

CAM, FEA real grado Fusion (aplazado hasta que el negocio lo pida — el analítico cubre
~80 % por ~5 % del coste), PCB/electrónica, nube multiusuario, diseño generativo.
Referencia de librerías candidatas (con licencias) para futuras adopciones: ver
`docs/devlog.md` § "Catálogo de librerías candidatas".
