# Genix Apolo CAD

CAD paramétrico 3D para maquinaria industrial/robótica cuyo **diferenciador es el
diseño asistido por IA** (agente-nativo, también manual). Vertical del MVP:
transportadores / manejo de materiales. Stack: **Python (build123d/OCCT) + FastAPI +
React/three.js**. IA: Claude API en la nube vía `APOLO_MODEL` (por defecto
`claude-opus-4-8`).

## Arquitectura (principios que NO se negocian)

- **API-first / IA-nativa**: toda operación es un comando sobre un kernel headless.
  UI, agente-chat y MCP son clientes iguales de la misma API HTTP.
- **Documento = log de comandos** (event-sourced). `.apolo` = ZIP (manifest v2 +
  commands.json + attachments/). La geometría nunca se guarda → archivos de KB,
  autosave barato, undo/redo por snapshots.
- **Schema-driven**: los JSON Schemas pydantic del `REGISTRY` generan a la vez la
  toolbar, los diálogos, el panel Propiedades y las **tools del agente**. Una sola
  fuente de verdad.
- **Expresiones**: cualquier campo numérico acepta `"=expresión"` con variables del
  proyecto (motor AST en `commands/expressions.py`). Las variables son comandos
  `set_variable` en la cabecera del log; cambiarlas regenera todo.
- **Selectores declarativos** de aristas/caras (todas/direccion/cara/longitud/cerca)
  para evitar nombrado topológico frágil.
- **Plantillas de máquina = super-comandos** del registro (p. ej. `create_conveyor`),
  no scripts: así heredan edición paramétrica, undo, BOM y exposición al agente gratis.

## Escala — mandato de arquitectura

Este proyecto se desarrolla **para crecer a gran escala** (muchas líneas de código,
muchos comandos, muchos módulos, modelos grandes, varios clientes). Por tanto:

- **La arquitectura y la estructura deben ser escalables y mantenibles SIEMPRE.** No se
  aceptan atajos que hipotequen el crecimiento: nada de módulos monolíticos gigantes,
  responsabilidades mezcladas, ni acoplamientos que impidan añadir comandos/clientes.
- **Si para hacerlo bien hace falta refactorizar, se refactoriza** — no se parchea encima
  de una base que ya no da. Preferir la solución correcta y duradera a la rápida y frágil.
- Mantener las fronteras limpias: `kernel` (geometría pura) ⟂ `commands/registry`
  (operaciones+schemas) ⟂ `doc` (log/estado) ⟂ `api` (transporte) ⟂ `agent`/`mcp`
  (clientes IA) ⟂ `ui`. Una capa no debe filtrarse en otra.
- Antes de añadir una función grande, evaluar si la estructura actual la soporta con
  elegancia; si no, refactorizar primero y construir después.
- Cada módulo nuevo: responsabilidad única, testeable de forma aislada, sin estado global
  fuera de los puntos ya establecidos (p. ej. `STATE_LOCK`). Acompañar de tests.

## Ejecutar y probar

```powershell
.\start-apolo.ps1                 # levanta API+UI en http://127.0.0.1:8000 (-OpenBrowser, -Reload, -Port)
.\.venv\Scripts\python.exe -m pytest tests -q     # 305 tests
cd ui ; npm run build             # bundle de la UI
```
- MCP `apolo-cad` (`.mcp.json`) = cliente fino stdio→HTTP; **47 tools**. Núcleo de escritura
  mínimo (run_command/run_batch con `$k` + edit_command + undo/redo + set_variable cubren TODO el
  registro; NO hay tool por comando). `render_view` devuelve imagen (visión). Requiere la API arriba.
  **Tier 1 lectura/introspección (2026-06-15)**: `get_command(id)` (params actuales), dry-run sin tocar
  el doc (`test_sketch`, `test_script` → `/api/script/test`), `engineering_check(conveyor=...)`
  predictivo (campo `conveyor` en `ChecksIn`), `get_mates`/`get_motion`, `get_agent_notes`/
  `add_agent_note` (memoria de sesión, `/api/agent/notes`, tope 30), `list_revisions`/`restore_revision`,
  y `_scene_brief` ahora expone `puede_deshacer/puede_rehacer`. La auditoría (workflow) confirmó que el
  diseño thin schema-driven es correcto; el hueco era LECTURA, no escritura. **Tier 2 percepción
  geométrica (2026-06-15)**: `get_topology(id)` (`GET /api/features/{id}/topology`, `kernel/topology.py`)
  enumera caras (tipo plano/cilíndrico, centro, normal/eje, radio, área) y aristas (longitud, dirección,
  radio) para que el agente ELIJA el selector declarativo (sin modo de selección por id); `render_view`
  gana `highlight_ids`/`show_axes`/`show_bbox` (query `highlight` CSV en `/api/render.png`) + `set_visibility`/
  `set_visibility_bulk` (aislar antes de renderizar); `resolve_expression`/`get_expression_grammar`
  (`/api/resolve-expression`, `/api/expression-grammar`, read-only, reusan `eval_expression` +
  `ALLOWED_FUNCS/CONSTANTS`). Todo read-only, no muta el documento. **El proceso MCP del host
  debe reiniciarse para ver tools nuevas** (registra al arrancar).
- **Ergonomía MCP (2026-06-23)** — 4 mejoras tras construir por MCP la clasificadora de sorteo manual
  (164 piezas) y chocar con fricción de la plataforma (no del modelo). (1) **Retorno compacto**: las
  mutaciones (`run_command`/`run_batch`/`edit_command`) ganan `detail` y por defecto devuelven `"diff"`
  (solo los sólidos de los `affected_command_ids` + `total_solidos`), no los N de la escena — antes
  cada lote volcaba toda la escena y saturaba el contexto del agente; `"full"`/`"summary"` disponibles;
  consultas y afectado-vacío → todos. `_state_or_error` adjunta `affected_command_ids` (captura el retorno
  del lambda; `Document.edit` ahora DEVUELVE el id), `scene_payload` expone `total_features`. (2)
  **`edit_command` PATCH**: `Document.edit(merge=False)` sigue REEMPLAZANDO (UI/tests intactos, envían
  params completos), pero la tool MCP fusiona por defecto (`merge=True`) y el REST opt-in `?merge=true`
  — merge SUPERFICIAL (un sub-objeto position/rotation se reemplaza entero). Fin del footgun "editar un
  campo resetea el resto a su default". (3) **Schema de uno**: `GET /api/schemas/{type}` +
  `get_command_schemas(command_type=...)` para no volcar ~77 KB (404 si no existe). (4) **Encuadre de
  render**: `render_view`/`render_scene_png` ganan `fit_ids` (primer plano de unas piezas), `zoom` (>1
  acerca) y `proportional` (ejes ceñidos al bbox con `set_box_aspect` REAL en vez del cubo `(1,1,1)` que
  aplastaba máquinas largas y bajas a una astilla). 378 tests (`test_mcp_brief.py`, `test_render_frame.py`
  + casos en `test_api.py`/`test_document.py`/`test_commands.py`). **Reiniciar API y proceso MCP del host**
  para que las tools registren los params nuevos.
- **Ergonomía MCP — lote de ediciones + recorte de `variables` (2026-06-24)** — 2 mejoras tras rediseñar
  por MCP las 4 hojas de la puerta plegable con **28 `edit_command`** seguidos (la demora fue plataforma, no
  modelo). (5) **`edit_batch`** (tool MCP nueva, **38→39 tools**): edita N comandos en UN lote ATÓMICO = **un
  solo `regenerate()` y un solo paso de undo** (antes: N round-trips + N regenerates en bucle). Núcleo
  `Document.edit_many(edits, merge=False)` (espejo de `execute_many`: snapshot → aplicar todo → 1 regenerate →
  1 undo; rollback total si falla; NO pre-valida por comando, valida el regenerate final → permite editar un
  `set_variable` + su uso en el mismo lote). REST `PATCH /api/commands/batch` (`EditBatchIn`, opt-in
  `?merge=true`; convive con el `POST` de creación). La tool MCP fusiona por defecto (`merge=True`). NO necesita
  `$k` (edita ids existentes). (6) **`variables` solo si cambió**: `_scene_brief` (cliente MCP) dejaba SIEMPRE
  el bloque de las ~33 variables (~2 KB) en cada mutación; ahora lo OMITE salvo que `detail="full"`, sea consulta
  (sin `affected`), o algún `affected_command_id` sea un `set_variable` (inspecciona `document.commands`, que NO
  se devuelve al agente). `get_scene` y lecturas siguen trayéndolas completas. Las mutaciones de geometría —el
  caso común— ya no las arrastran. 398 tests (`test_document.py::test_edit_many_*`, `test_api.py::test_edit_batch_*`,
  `test_mcp_brief.py`). **Reiniciar API y proceso MCP del host** para registrar `edit_batch`.
- **Autoría agente-nativa "a gusto": percepción + intención + preview (2026-06-24)** — 5 fases para que el
  agente cree 3D cómodo (no solo verifique). El cuello de botella no era MCP sino la ALTURA de los comandos
  (coordenadas a ciegas) y que la percepción era de solo-salida. **39→43 tools, 36→39 comandos, 416 tests.**
  Todo aditivo (params opt-in / endpoints / comandos / tools nuevos). **F1 · Percepción** (`kernel/render.py`,
  `/api/render.png`, `render_view`): `views` (≥2 vistas en UNA imagen, subplots), `labels` (rotula ids sobre el
  render con `ax.text` 3D), `section` ∈ {x,y,z} (recorta cada sólido con semicaja booleana —técnica de
  `drawing/projection.py`— para VER DENTRO). Pieza 0: `apply_camera` extraída (única fuente de la cámara →
  la comparten render y pick). **(2026-06-26) `shade` en `/api/render.png` + `render_view`** (en el tool MCP
  `shaded=True` por DEFECTO): pasa `colors=_feature_colors()` → render SOMBREADO A COLOR por pieza (igual que el
  viewport web) en vez de la paleta por índice apagada → capturas legibles para que el AGENTE se auto-revise
  visualmente. Aditivo (reusa lo de los planos). **Reiniciar host MCP** para el default nuevo.
  **(2026-06-26) `isolate` en `/api/render.png` + `render_view`** (CSV de ids / lista): renderiza SOLO esas
  piezas filtrando una COPIA de la escena (mismo patrón que `drawing_spec`/`assembly_manual`), **sin tocar
  `DOC` ni la visibilidad** — la forma LIMPIA de fotografiar una pieza/sub-conjunto de cerca (combínalo con
  `zoom`). Sustituye el antipatrón de `set_visibility_bulk` ocultar→render→restaurar (mutaba el doc en vivo,
  3 llamadas + parpadeo en la web + riesgo de dejar piezas ocultas si fallaba). **`isolate` FUERZA mostrar las
  piezas nombradas aunque estén ocultas** (`ignore_visibility=True` en render; 2026-06-26: arregla "aíslo una
  pieza oculta → escena vacía") → ves exactamente lo que pides, read-only. `test_api.py::test_render_isolate_*`.
  **Reiniciar host MCP** para que el tool registre el param `isolate` (la API en `--reload` ya lo sirve).
  **(2026-06-26) Calidad de render — fin de las "rayas"**: el render sombreado mostraba bandas de brillo a lo
  largo de cilindros (tambores/ejes). Causa: malla GRUESA (`shape.tessellate(1.2, 0.6)` ≈ 10 caras/vuelta) +
  sombreado plano por faceta de matplotlib. Fix en `kernel/render.py::_draw_view`: teselado FINO
  `tessellate(0.5, 0.25)` (~25 caras/vuelta) + bordes de triángulo a grosor 0 (`edgecolors=color,
  linewidths=0`). **OJO**: `edgecolors="none"` + `shade=True` revienta matplotlib (`_shade_colors` sombrea un
  array de bordes vacío → ValueError en `section`/`labels`) — por eso bordes del color de la pieza con
  `linewidths=0`, NO `"none"`. Queda el límite de fondo de matplotlib (ordena por pieza, no por píxel → leve
  transparencia de piezas internas); para imagen impecable, el viewport web (three.js). Más fino = más
  triángulos (coste asumible en ~90 piezas). Cubierto por `test_render_frame.py` (section/labels).
  **(2026-06-26) RENDER PRO con VTK — capturas como el viewport web**: matplotlib sombrea cara plana por
  faceta → SIEMPRE deja bandas en cilindros (afinar la malla solo las adelgaza). El arreglo de verdad es otro
  motor: NEW `kernel/render_vtk.py::render_scene_vtk` (VTK off-screen, ya instalado, sin dependencia nueva)
  con **normales interpoladas** (`vtkPolyDataNormals` feature angle 35° = el `toCreasedNormals` del viewport
  three.js) + buffer de profundidad real + `vtkLightKit` + proyección ortográfica → sombreado SUAVE, sin
  rayas, sin transparencias falsas, fondo claro limpio. Reusa `VIEW_ANGLES`/`PALETTE`/`_clip_to_section` de
  `render.py` para coincidir en vista/cámara/sección/colores; soporta isolate(escena filtrada)/highlight/fit/
  zoom/section/show_axes/show_bbox/pose(`shapes_override`). El endpoint `/api/render.png` (y por tanto
  `render_view`) usa VTK cuando `shade` y NO hay `views`/`labels`; esos dos y cualquier fallo de VTK (sin
  contexto OpenGL) caen a matplotlib (try/except → fallback robusto, nunca 500). `proportional` se ignora en
  VTK (siempre proporciones reales). Tests `test_render_vtk.py` (se auto-saltan sin OpenGL). **Límite**: VTK
  no cubre aún multivista ni etiquetas (siguen en matplotlib con la malla fina). **GOTCHA que costó depurar**:
  un `python.exe` huérfano (hijo de un uvicorn muerto) **retenía el handle del socket :8000** y servía código
  viejo → mis cambios "no aparecían" aunque el worker `--reload` recargara; se detecta con
  `Get-NetTCPConnection -LocalPort 8000` (el OwningProcess NO es el worker real) y se cura matando al huérfano
  o con el reinicio limpio (matar TODOS los python del venv). Es el mismo gotcha de Windows ya documentado abajo.
  **F2 · Medición + píxel→3D** (visión como ENTRADA): `kernel/measure.py`
  (`measure_distance` vía OCCT `BRepExtrema_DistShapeShape` — NO existía medición de gap; `features_near`),
  `kernel/pick.py` (`pick_point(view,u,v)` = snap a geometría: proyecta centros con la MISMA cámara y devuelve
  la pieza/cara más cercana al píxel normalizado [0,1]). Endpoints `POST /api/measure`, `GET /api/near`,
  `GET /api/pick`; tools `measure`/`near`/`pick_point`. **F3 · Preview reversible** (`Document.preview`,
  `POST /api/commands/preview`, tool `preview`): ghost-render de una propuesta sobre una COPIA del doc (reusa la
  caché de regenerate → incremental, no rebuild en frío) SIN tocar el real; equivocarse sale gratis. **F4 ·
  Colocación por intención** (comandos `center_in`, `distribute`): centrar A en B / repartir N piezas parejo
  entre dos coords (aceptan `=expr`); mueven en sitio (`_world_move`) y se REEVALÚAN al regenerar → siguen los
  cambios (relacional, no coord fija). NOTA: `align/place_on_face` ya lo cubre `add_mate` (cara→cara). **F5 ·
  Multi-restricción / N-GDL** (`assembly/constraints.py`, comando `add_constraint`): `solve_constraints` pasó de
  1-GDL por restricción (`minimize_scalar`) a **N-D global** (`least_squares` sobre TODAS las juntas dependientes
  a la vez); tipos `punto_en_recta`(=riel)/`punto_en_plano`/`punto_coincidente`/`distancia`. Compatible: el riel
  1-GDL de la puerta sigue resolviendo. `add_constraint` usa `wants_constraints=True` (sin nueva rama de
  despacho). **Límite honesto**: arranque degenerado (ancla a 180° exactos del objetivo → gradiente cero) no
  converge; usar continuación (como hacen los keyframes de la puerta). Tests: `test_render_frame.py`(+4),
  `test_measure.py`, `test_pick.py`, `test_api.py`(preview/measure/pick), `test_document.py`(preview),
  `test_relational.py`, `test_constraints.py`(+3). **Reiniciar API y proceso MCP del host** para registrar las
  tools nuevas. Plan vivo de las 5 fases (con follow-ups: datums, mirror_about_plane, IK, anotaciones de cota).
- **`pattern_group` — arrayar un GRUPO (2026-06-23)**. Comando nuevo (categoría `modificar`, 35→36 comandos):
  arraya **TODAS las features de un comando** `source` (un `command_id`: super-comando, `insert_component`,
  STEP con split, u otro patrón), no solo una como `pattern_linear`. Lineal (`count`/`spacing`) + **rejilla
  2D** (`count2`/`spacing2`); `count`/`count2` aceptan `=expresión` (`_floor_to_int`). `_exec_pattern_group`
  (registry.py) reusa `linear_copy` + `multiply`/`translation`; ids de copia `{cmd_id}_{i}_{k}_{suffix}`
  (namespace propio, sin colisión); conserva `component`/`cut_length` (BOM). **Solo geometría**: si la fuente
  está referenciada por una junta/mate, **se rechaza con `CommandError`** (decisión del usuario; no produce
  copias "muertas"). Para ello el comando declara `wants_joints=True, wants_mates=True` y se añadió en
  `execute_command` una **rama combinada** `elif spec.wants_joints and spec.wants_mates:` (aditiva; ningún
  comando previo activa ambos). Tope anti-OCCT `_PATTERN_GROUP_MAX=2000` sólidos. Se usa por
  `run_command(type="pattern_group", ...)` (sin tool MCP dedicada, como `pattern_linear`). **Límite conocido**:
  opera por `command_id` (la unidad de agrupación del log); cajas sueltas con `create_box` individuales NO
  comparten command_id → agruparlas primero (super-comando/boolean/attach) o es follow-up un "grupo explícito".
  387 tests (`tests/test_commands.py`, `tests/test_document.py`).
- **`render_view` con POSE cinemática (2026-06-17)**: `render_view(joint_values={...})` →
  `/api/render.png?joints=<JSON>` resuelve las restricciones de riel (`solve_constraints`) + `posed_shapes`
  y renderiza el FOTOGRAMA POSADO (read-only). `render_scene_png` ganó `shapes_override` (espejo de
  `interference_report`). Cierra el hueco de que el agente no podía VER un mecanismo plegado/en pose por MCP
  (antes había que reconstruir el doc en frío). Pasar solo los drivers; los dependientes se resuelven solos.
- Planos por HTTP: `/api/drawing.svg|dxf|pdf?sheet=A3&section=true&bom=true&dims=<ids>`.
- **Sistema de planos PROFESIONAL — en curso por fases (plan aprobado 2026-06-24)**. El módulo `drawing/`
  (compositor `SheetModel` → SVG/PDF/DXF, HLR vía build123d) se está subiendo a nivel taller/ingeniería en
  7 fases (A cotas+normas · B detalle/cortes/rayado · C cajetín+revisiones · D lista de corte+nesting+cédula
  de herraje [mayor ROI] · E juego de planos+BOM enriquecido · F salida: DXF por capas/lineweight, PDF
  multipágina+fuentes, A0–A4 · G planos por INTENCIÓN agente-nativo). Orden A→D→B→C→E→F, G entretejida.
  **Cerrado**: cimiento `library/materials.py` (densidad acero/aluminio/madera/vidrio + **pvc/caucho/carton**
  [2026-06-25: polímeros/goma/bulto, con inferencia por nombre banda PVC→pvc, engomado/lagging→caucho] +
  patrón de rayado + `resolve_material`) y **Fase A** (`drawing/dimensions.py`: `linear_dim` con líneas testigo+flechas+tolerancia,
  `baseline_dims` desde datum, `center_mark`; integrado en `sheet.py` → cotas con FLECHAS + marcas de centro
  en agujeros; tipo de línea `center`/eje-punto en los 3 exportadores, capa `EJES` en DXF). **Fase D**
  (`library/cutlist.py`: `cut_list` agrupa por (material,espesor,ancho,largo) descomponiendo COMPOUNDS en
  `shape.solids()` —una hoja=2 largueros cuenta 2 tablas—; `cut_list_totals` por material; `hardware_schedule`
  = catálogo NO cortable; `cut_list_csv`. `library/nesting.py`: `nest_1d` (FFD barras), `nest_2d` (estantería
  tableros/vidrio), `waste_*`, `nesting_sheet_1d/2d`→`SheetModel`. Endpoints `/api/cutlist.json|csv`,
  `/api/nesting.svg|dxf|json`; tools MCP `cut_list`, `nesting`). **Fase B** (vistas pro): `section_projection`
  generalizado a **ejes x/y/z + offset** (CORTE A-A/B-B/C-C) seccionando **POR FEATURE** → cada cara lleva su
  MATERIAL; **rayado por material** en los 3 exportadores (SVG patterns madera/vidrio/acero, PDF matplotlib
  `hatch`, DXF `add_hatch` ANSI31 escala/color); `detail_view` (recorte circular robusto por distancia
  punto-segmento, amplía ×scale) + burbuja **DETALLE A** en `compose_sheet` (param `detail`); `Polygon.material`.
  `compose_sheet(section=bool|str)` retrocompatible (True→x). **Fase C** (`drawing/titleblock.py`: cajetín
  pro —nº plano, **bloque de revisiones**, material, acabado, tolerancia gral, hoja N/M, símbolo de diedro,
  dibujó/revisó/aprobó, peso, logo—; `compose_sheet(meta=...)`; material/peso AUTO de `cutlist.scene_weight_kg`/
  `dominant_material`; revisiones surtidas de las **revisiones SQLite** vía `_drawing_meta`). **Fase E**
  (`drawing/sheetset.py` `sheet_set`: **conjunto** con BOM + **1 lámina por pieza** aislada/acotada
  (escena sintética de 1 sólido vía `_pick_solid`) + **cédula** corte/herraje; `pdf.sheets_to_pdf`
  **multipágina** (`PdfPages`); `bom_from_scene` enriquecido con `material`; endpoint `/api/drawingset.pdf`,
  tool MCP `drawing_set`). **Fase F** (DXF **lineweight por capa** + `$LWDISPLAY`; PDF **fuentes embebidas**
  Type42 + metadatos; láminas **A0–A4**; **barra de escala** gráfica + **rejilla de zonas** A–D/1–8 en el marco).
  **Fase G** (planos por INTENCIÓN — el moat): `compose_sheet(datum_dims=...)` traza **cotas de posición desde
  el datum** (base) en el alzado vía `baseline_dims`; endpoint **`POST /api/drawing/spec`** + tool MCP
  **`drawing(spec)`**: UNA spec declarativa `{sheet, section:"x"/"y"/"z", detail:{...}, dims:[ids],
  datum_dims:[ids], bom, isolate:[ids] (filtra la escena SIN tocar visibilidad), format:"pdf/svg/dxf", meta}` →
  el motor compone el plano pro. `format="svg"` sin path devuelve el SVG (para `show_widget` inline).
  **SISTEMA DE PLANOS PRO COMPLETO (A–G)**. 447 tests (`test_titleblock.py`, `test_sheetset.py`,
  `test_export.py`, `test_drawing_spec.py`). 4 tools MCP nuevas (cut_list, nesting, drawing_set, drawing →
  **43→47 tools**). Todo aditivo/retrocompatible. **Reiniciar API + proceso MCP del host** para servir los
  planos/tools nuevos.
- **Pulido de encuadre de lámina (2026-06-24)** — tras inspeccionar visualmente una lámina por-pieza (la Hoja 1
  de la puerta) se vieron 2 defectos de layout y se arreglaron en `drawing/sheet.py`. (1) **Escalas intermedias**:
  `STANDARD_SCALES` saltaba 1:20→1:50, dejando piezas altas/angostas diminutas (una hoja de 2008 mm caía a 1:50 =
  40 mm en celda de 98 mm). Añadidas las normalizadas ISO permitidas **1:2.5 / 1:4 / 1:25 / 1:40** → `_pick_scale`
  ahora llena la celda (la hoja pasó a **1:25**, ~80 mm). (2) **Globos del BOM en FILA, no radiales**: se colocaban
  radialmente desde el centro de la planta, así que en una planta delgada se apelotonaban e invadían el rótulo
  «PLANTA» y la cota de ancho de abajo. Ahora van en una **fila ordenada por X, por encima de la planta** (sobre las
  cotas de tamaño, `ring_y = ry+rh+8+planta_dim_rows*6.5`, dos sub-filas alternas para no tocarse) → el rótulo/cotas
  quedan libres debajo. Verificado rasterizando el `SheetModel` a PNG (`scripts/_rasterize_hoja1.py`; no hay
  pdftoppm/fitz, así que se renderiza vía `pdf._figure`→`savefig`). 448 tests (`test_drawing.py::test_pick_scale_intermediate`,
  aserción de globos-sobre-planta en `test_drawing_pro.py`). Aditivo. **Reiniciar API + MCP** para verlo en el endpoint vivo.
- **Despiece acotado por pieza — plano de ENSAMBLAJE fabricable (2026-06-24)**. A raíz de la crítica del usuario
  («tu plano solo dice alto/largo/fondo + descripción; eso sirve para 1 objeto, no para una hoja de 5 tablas»): un plano
  de conjunto que solo da el bbox no se puede construir. Se añadió a `compose_sheet` (`drawing/sheet.py`, todo aditivo;
  el camino `bom=True` quedó byte-idéntico vía el helper extraído `_draw_table_with_balloons`): (1) **`cutlist=True`** →
  tabla **DESPIECE** con la medida **L×A×E de CADA tabla** (usa `library/cutlist.py::cut_list`, que parte el union de
  largueros en `shape.solids()` → larguero ×2, travesaño ×3, vidrio ×1) y **globos en el ALZADO** (columna a la derecha,
  no en la planta-astilla). (2) **`member_detail={member,pick:[t,w,l],locate:[ids],scale,name}`** → vista de **DETALLE de
  UNA tabla** (aísla un sólido del union con `sheetset._pick_solid`, lo proyecta con `project_views` y lo coloca en el
  cuadrante de la planta —que en una pieza plana es una astilla inútil—) con la **posición de cada mortaja/bisagra acotada
  desde la base** (`baseline_dims` sobre el Z-centro de los features `locate`). Las cotas de **ubicación** de los travesaños
  ya las daba `datum_dims`; el **corte B-B** (`section:"y"`) muestra el traslape de 36 mm + vidrio detrás. Plumado en
  `DrawingSpecIn`/`drawing_spec` (`api/main.py`) y el tool MCP `drawing`. **OJO**: los features de `locate` (bisagras) deben
  estar en la escena (inclúyelos en `isolate`; `cut_list` los excluye del despiece por ser herraje no cortable, así que NO
  ensucian la tabla, pero sí se ven en el alzado y el detalle resuelve su posición). Verificado en vivo sobre la Hoja 1 de
  la puerta (id 28): tabla DESPIECE + detalle del larguero con mortajas a 50/1005/1958 + alzado con bisagras/globos + corte
  B-B. 451 tests (`test_drawing_pro.py`: cutlist/bom-intacto/member_detail; `test_api.py`). **Límite honesto**: el acotado
  es del bbox/posición de features (no lee aún las cotas del log paramétrico), 1 hoja a la vez (no el juego completo de
  todas las piezas), y la mortaja se acota por la POSICIÓN de la bisagra (no hay corte físico de mortaja). Follow-ups: juego
  de planos de todas las piezas, cotas de montaje en X, vista explosionada, leer cotas del log paramétrico, cédula de
  herraje en la lámina. **Reiniciar API + MCP** para servir los campos nuevos.

- **Plan PRO de planos — 5 fases (aprobado 2026-06-24)**: cerrar los 5 huecos para planos nivel
  SolidWorks/Inventor en el vertical. (1) Juego de planos completo · (2) Acotado automático · (3) Vista
  explosionada · (4) Cédula de herraje + BOM en la lámina · (5) GD&T ligero. Orden 1→2→4→3→5, fase por
  fase con checkpoint visual. Plan en `.claude/plans/acota-primero-una-hoja-pure-lobster.md`.
  - **Fase 1 ✅ (2026-06-24) · Juego de planos completo (paquete de fabricación)**. `sheet_set`
    (`drawing/sheetset.py`) enriquecido: el **conjunto** pasó de `bom` (sin dims) a **`cutlist`** (tabla
    DESPIECE L×A×E + globos en el alzado); **LISTA DE CORTE** y **CÉDULA DE HERRAJE** ahora son **páginas
    separadas** (la cédula usa `hardware_schedule`, catálogo no cortable: bisagras/correderas/tornillos);
    el **`template`** (carpinteria/weldment/chapa/generico) por fin se usa (carpinteria/generico incluyen
    la cédula de herraje). El endpoint `/api/drawingset.pdf` y el tool `drawing_set` heredan todo sin
    cambios. Verificado: juego de 14 páginas de la puerta id 28 (conjunto + 11 piezas + corte + herraje),
    rasterizado por página (`scripts/_render_juego.py`). 452 tests (`test_sheetset.py`). **Pendiente para
    Fase 2**: la lámina por pieza solo lleva overall L×A×E + Ø de agujeros (falta posición de agujeros y
    uniones, que es el acotado automático). Aditivo. **Reiniciar API+MCP** para el juego nuevo en vivo.
  - **Fase 2 ✅ (2026-06-24) · Acotado automático ("acota solo")**. NEW `drawing/autodim.py::auto_hole_dims`:
    para una pieza, acota la **posición (x,y) de cada agujero** desde la esquina datum, leyendo la GEOMETRÍA
    (los círculos que `_collect_circles`/HLR ya detectan en la vista) — sin que el usuario liste ids. El Ø ya lo
    rotulaba `_hole_callouts` (agrupa `n×Ød`) y `center_mark` marca centros; juntos dan "Ø + dónde". Dedup por
    valor; escaleras X por debajo / Y a la izquierda (tras las cotas generales). Cubre **taladros, clavijas y
    tornillos** (todo lo circular). Wire: flag **`auto_dims`** en `compose_sheet` (en el bucle de vistas, tras
    los callouts); las **láminas por pieza del juego** (`sheet_set`) pasaron de `dims_features` a `auto_dims`
    (las cotas generales L×A×E ya salen solas del bucle de vistas). Verificado con una placa 120×80 + 5
    agujeros: rotuló `4×Ø9`+`Ø24` y acotó posiciones 20/60/100 (X) y 20/40/60/80 (Y) automáticamente
    (`scripts/_placa_autodim.png`). 453 tests (`test_drawing_pro.py::test_auto_dims_holes_position`). **Límite
    honesto**: hoy acota POSICIÓN de agujeros (geometría); las posiciones de mortajas/dados (cortes, no círculos)
    desde el LOG de comandos quedan como follow-up. Aditivo.
  - **Fase 4 ✅ (2026-06-24) · Cédula de herraje + BOM en la lámina del conjunto**. Flag **`hardware`** en
    `compose_sheet`: bajo el DESPIECE dibuja la tabla **CÉDULA DE HERRAJE** (`hardware_schedule`: catálogo no
    cortable — Ref/Descripción/Cant/Peso). El helper `_draw_table_with_balloons` ganó `top_y` (apilar) y devuelve
    su borde inferior; la cédula se ancla a `top_y=despiece_bottom-5` sin globos (`anchor_view="none"`). El
    **conjunto** del juego (`sheet_set`) lo usa (`cutlist=True, hardware=True`) → la lámina de conjunto es
    autocontenida (despiece + herraje + globos + iso + pesos en el cajetín); la **página de cédula dedicada**
    sigue para el listado completo. Plumado en `DrawingSpecIn`/`drawing_spec` (+`hardware`/`auto_dims`) y el tool
    `drawing`. Verificado en la puerta id 28: DESPIECE 11 filas + CÉDULA (BIS-H-75-A/B ×12, CORR-D100 ×2) en la
    misma lámina (`scripts/_conjunto_herraje.png`). 454 tests (`test_drawing_pro.py::test_hardware_table_on_conjunto`).
    **Follow-up**: cross-reference "→ hoja k" de cada globo a su lámina de pieza (hoy no enlaza). Aditivo.
  - **Fase 3 ✅ (2026-06-24) · Vista explosionada**. NEW `drawing/explode.py::explode_scene(scene, axis, factor)`:
    COPIA de la escena con los sólidos separados a lo largo de un eje (clona shapes con
    `move_rotated_about_center`, NO toca el documento). Por defecto **amplía** la separación desde el centro
    (`factor`×); si las piezas son casi **coplanares** en el eje, las reparte por **orden** con hueco uniforme
    (≈1.8× la mayor). Param **`explode={axis,factor}`** en `compose_sheet` (rama antes de la iso): proyecta la
    escena explosionada **ortográfica** (alzado, o planta si eje=Y → así `world_to_view` puede situar los globos)
    en el cuadrante iso, con **línea de explosión** (eje-punto) + **globos de secuencia** 1..n ordenados por el
    eje. Plumado en `DrawingSpecIn`/`drawing_spec` y el tool `drawing`. Verificado: panel de 4 capas explosionado
    en Z con globos 1-4 + centerline (`scripts/_explode_demo.png`). 456 tests (`test_explode.py`). **Límite**:
    iso real no admite situar puntos (`project_to_viewport` proyecta aristas, no puntos) → se usa ortográfica;
    piezas coplanares estrictas usan el reparto por orden. Aditivo.
  - **Fase 5 ✅ (2026-06-24) · Anotaciones / GD&T ligero**. NEW primitivas en `drawing/dimensions.py` (emiten
    Line+Label con kinds existentes, sin tocar exportadores): **`notes_block`** (bloque de NOTAS numeradas),
    **`surface_finish`** (símbolo ✓ con Ra), **`datum_flag`** (letra en recuadro + triángulo), **`feature_control_frame`**
    (marco de control GD&T `[símbolo | tol | datum…]`). `linear_dim` ya soportaba `tol` (±). Wire: flag **`notes`**
    en `compose_sheet` (bloque auto-colocado en el hueco medio-izquierdo) + spec/tool `drawing`. Los símbolos
    (acabado/datum/FCF) son toolkit a colocar por coordenada. Verificado: brida con NOTAS + ✓Ra3.2 + datum A +
    FCF [POS|0.2|A|B] (`scripts/_anotaciones_demo.png`). 459 tests (`test_annotations.py`). **PLAN PRO DE PLANOS
    COMPLETO (5/5 fases)**. Aditivo. **Nota**: GD&T es más útil en metal que en madera (de ahí que fuese la última).
  - **Fix de layout cuadrante iso vs cajetín (2026-06-24)** — el usuario detectó que en las láminas por pieza la
    isométrica (y su rótulo) se solapaba con el cajetín (180×40) + bloque de revisiones (abajo-derecha).
    Arreglo en `compose_sheet`: (1) la banda vertical del **cuadrante iso se acota POR ENCIMA** de la zona
    cajetín+revisiones (`tb_top` calculado del nº de revisiones; `iso_cell_h`/centro recolocados) → la iso/
    explosión/detalle ya no bajan al cajetín; (2) los rótulos del cuadrante iso (ISOMÉTRICA/EXPLOSIONADA/DETALLE/
    CORTE) pasaron a ir **encima** de la vista (`rect[1]+rect[3]+3`); (3) **`show_iso=False`** nuevo flag: las
    **láminas por pieza** del juego omiten la isométrica (3 vistas ortográficas bastan) → evita el solape
    lateral/iso en piezas-pin y deja el cajetín limpio. Verificado en la pieza-pin y el conjunto de la puerta.
    460 tests (`test_sheetset.py::test_per_part_sheet_omits_iso`). Aditivo.
  - **Verificación por detector de solapes (2026-06-24)** — a raíz del "¿seguro que nada se pisa?": NEW
    `scripts/_check_overlaps.py` estima la caja de cada Label y reporta pares de TEXTO que se pisan. Reveló 6
    solapes RESIDUALES (no el cajetín, ya resuelto): la 1.ª cota de POSICIÓN automática (`auto_hole_dims`, a
    `ry-13`) pisaba el rótulo de vista (`ry-14.5`) en plantas/perfiles con agujeros (los pines tienen sección
    circular → también auto-cotan). Fix: `base_offset` de `auto_hole_dims` 14→20. Tras el fix, las 14 páginas
    del juego + casos sintéticos (brida/explode/notas/conjunto) → **0 solapes**. **Honesto**: el detector es
    una aproximación sobre los casos probados, NO una prueba para todo input posible.
  - **Planos a COLOR tipo Inventor — isométrica sombreada (2026-06-24)** — a pedido del usuario. Opción
    **`shaded`** en `compose_sheet`/`sheet_set`/spec/`drawing`/`drawing_set`: embebe un **render 3D sombreado a
    color** (el de `kernel/render.py::render_scene_png`, paleta por pieza + `shade=True`) en el cuadrante de la
    isométrica, en vez del alambre — las vistas ortográficas siguen en línea limpia (como Inventor: solo el
    pictórico va sombreado). Piezas nuevas: `render_scene_png(clean=True)` (sin ejes/grid/título, fondo
    transparente, `pad_inches=0`) para embeber limpio; primitiva **`Image(x,y,w,h,png)`** en el `SheetModel`
    (coords mm, origen abajo-izq) + `SheetModel.images`; los exportadores **SVG** (`<image>` base64) y **PDF**
    (`ax.imshow` + restaurar aspecto/límites) la sirven; **DXF la omite** (es solo-línea). El tamaño de la caja
    respeta el aspecto del PNG (leído del header IHDR). Verificado en el conjunto de la puerta
    (`scripts/_shaded_demo.png`): cada pieza en su color, sin solapes, cajetín limpio. 462 tests
    (`test_shaded.py`). Aditivo. **Reiniciar API+MCP** para servir `shaded` en vivo.
    - **Fix color = viewport web (2026-06-24)**: el usuario notó que el color del sombreado NO coincidía con
      el 3D del web. Causa: `render_scene_png` usaba **solo `PALETTE[i]`** (paleta por índice), ignorando
      (1) los **`DOC.colors`** asignados por el usuario y (2) que el web indexa la paleta sobre TODAS las
      features (incl. ocultas) y el render solo las visibles → índices desfasados. Fix: `render_scene_png` y
      `_draw_view` ganan `colors: dict|None` (id→hex); `color = colors.get(id) or PALETTE[i]`. La API expone
      `_feature_colors()` = `{id: DOC.colors.get(id) or PALETTE[i] for i,f in enumerate(DOC.scene.values())}`
      (IDÉNTICO a `scene_payload`) y lo pasa a `sheet_set`/`compose_sheet` (param `colors`, threaded). Verificado
      en la puerta (86/86 piezas con color): el iso del plano sale madera marrón + vidrio gris + travesaños de
      color, igual que el web. **Límite**: el vidrio sale gris OPACO (el web lo hace translúcido por material);
      translucidez en el render = follow-up. **Reiniciar API+MCP** para el color correcto en vivo.
    - **Color también en las láminas por pieza (2026-06-24)**: a pedido del usuario, cada lámina de pieza del
      juego (`sheet_set`) ahora lleva su **iso sombreada en el color de la pieza** (`show_iso=shaded`,
      `colors={"P": colors.get(rep_id)}`). Como el render es una IMAGEN acotada (no se extiende como el alambre
      que se omitió por solape), es seguro. El rótulo "ISOMÉTRICA · sombreado" se **omite cuando hay perfil**
      (`if "lateral" not in placed`) — en las piezas el perfil ocupa esa banda; en el conjunto (sin perfil) sí se
      rotula. Verificado: juego sombreado completo (12 imágenes: conjunto + 11 piezas) con **0 solapes** (detector).
  - **Plano de ENSAMBLAJE pro — 4 mejoras (2026-06-24)**. A raíz de la pregunta del usuario «¿cómo abordamos
    los planos para piezas de ensamblaje?» (con un plano explosionado estilo Inventor de referencia). Principio:
    *un plano de conjunto acota para MONTAR, no para fabricar*. Todo aditivo/retrocompatible. **F1 · Norma en el
    BOM/cédula**: el dato `norma` YA existía en el catálogo (`specs.norma`: DIN 912 / ISO 15 / ASTM A500 / EN
    10056…) pero no se volcaba; ahora `hardware_schedule`/`bom_from_scene` lo exponen y la **CÉDULA DE HERRAJE**
    gana columna **Norma**. Backfill: `EN 1935` (norma de bisagras de eje único) en las familias de bisagra
    (`100_bisagras.yaml`: BIS / BIS-PIANO / BIS-H / BIS-RES; la cazoleta euro queda sin norma a propósito). **F2 ·
    NOTAS DE MONTAJE** (`compose_sheet(assembly_notes=...)`): bloque titulado aparte de las NOTAS generales, apilado
    bajo ellas (reusa `notes_block`, que devuelve su borde inferior). Convención del param: `None`=off · `[]`=auto-
    semilla del herraje (`_assembly_notes_auto`: «Apretar N× REF (norma) según par de norma» + remite a la
    explosionada; **no inventa pares de apriete** — el catálogo no los lleva, follow-up `torque` en specs) · `[..]`
    =explícitas. **F3 · Cotas de INTERFAZ / patrón de montaje** (`compose_sheet(interface_dims=...)`,
    `autodim.py::mounting_pattern_dims`): pitch **centro-a-centro** entre agujeros + luz total del patrón (para
    taladrar la placa de acople), distinto de `auto_hole_dims` (posición desde el datum, para FABRICAR). Robustez en
    vistas cargadas/a escala pequeña: clustering de centros casi coincidentes (`merge_tol`), descarta pitches
    minúsculos en mm Y, sobre todo, los que en **PAPEL** caen más juntos que `min_paper` (a 1:25 un pitch de 25 mm =
    1 mm de lámina → la etiqueta se pisaría; en ese caso deja solo la luz total). **Es OPT-IN, NO va por defecto en
    el conjunto del juego**: un conjunto de 86 piezas superpone decenas de círculos de herraje en el alzado y el
    pitch auto-detectado satura; brilla en placas/bridas simples. **F4 · Cross-reference globo→hoja**
    (`compose_sheet(sheet_refs=...)`): columna **Hoja** en el DESPIECE que apunta a la lámina de detalle de cada
    pieza; `sheet_set` calcula el mapa `{_rep → nº de hoja}` (mismo orden que el bucle por-pieza: conjunto=1, piezas
    2..N) y lo pasa al conjunto. Plumbing: `DrawingSpecIn` + handler `drawing_spec` ganan `assembly_notes` e
    `interface_dims`; el tool MCP `drawing` (dict opaco) los documenta sin cambiar de firma → **no requiere reiniciar
    el host MCP** (solo recargar la API). Verificado e2e por HTTP sobre la puerta id 28 (Norma EN 1935 + NOTAS DE
    MONTAJE + juego PDF) y por el **detector de solapes** (14 páginas + sintéticos → 0 solapes, incl. interface_dims
    forzado en el conjunto tras la robustez de papel). 472 tests (`test_catalog_normas.py`, `test_drawing_pro.py`,
    `test_annotations.py`, `test_interface_dims.py`, `test_sheetset.py`). `scripts/_conjunto_ensamblaje.png`.
    **Follow-ups**: par de apriete real (campo `torque`), globo partido ítem/hoja, cotas centro-a-centro funcionales
    (eje↔eje) auto, más normas de carpintería.
  - **MANUAL DE ENSAMBLAJE paso a paso (2026-06-24)**. A raíz de la crítica del usuario («tu conjunto de
    ensamblaje es un chiste; ¿no se puede crear uno PRO que explique el armado paso a paso?»): el plano de
    conjunto (GA: despiece+cédula+globos, UNA lámina) lista piezas pero NO explica el montaje. Nuevo módulo
    `drawing/assembly_manual.py` (`assembly_manual`/`assembly_steps`) = instructivo estilo Inventor/IKEA, PDF
    MULTIPÁGINA: **portada con la secuencia** (tabla de contenidos) + **1 lámina por PASO**. Cada paso muestra el
    render 3D **acumulado** (las piezas NUEVAS del paso resaltadas a color, lo ya montado en **gris fantasma** —
    reusa `render_scene_png(highlight_ids=...)` que atenúa lo no resaltado a alpha 0.18) con **cámara ESTABLE**
    (param nuevo `render_scene_png(frame_bbox=...)` → encuadra el modelo COMPLETO en cada paso, así las piezas
    aparecen en su sitio final) + la lista de piezas/herraje del paso (con norma, vía `bom_from_scene` del subset)
    + la instrucción auto. **La SECUENCIA se DERIVA del modelo** (el moat agente-nativo): orden del **log de
    comandos** (`Document.commands` = cómo se armó) + **agrupación** (herraje por familia de catálogo; a medida por
    token inicial del nombre, p. ej. Marco/H1/Vidrio/Tornillería), ordenada por primera aparición. Endpoint
    `GET /api/assembly-manual.pdf`; tool MCP **`assembly_manual(path, sheet)`** (47→48 tools). Verificado en la
    puerta id 28: **14 páginas** (portada + 13 pasos: Marco → refuerzos de hojas → vidrios → parteluces →
    tiradores → bastidores → bisagras → riel → correderas → tornillería), render ~38 s (< timeout MCP), highlight
    fantasma correcto (`scripts/_manual_cover.png`, `_manual_step5.png`). 475 tests (`test_assembly_manual.py`).
    **Límite honesto**: la secuencia sigue el ORDEN DE MODELADO (log), que no siempre es el ideal de armado (en la
    puerta los «refuerzos» salen antes que el «bastidor» de la hoja porque se modelaron así); la agrupación es
    heurística por nombre/familia. Follow-ups: reordenar por dependencia de juntas (hijo después del padre),
    glosar cada hoja como sub-ensamblaje, explosionar las piezas nuevas del paso, numerar globos por paso.
    **Reiniciar API + host MCP** (tool nueva typed → el host debe re-registrarla).
    - **`isolate` en el manual (2026-06-25)**: el endpoint `/api/assembly-manual.pdf` y el tool MCP
      `assembly_manual` ganan `isolate` (CSV de ids / lista) + `title` → manual paso a paso de un
      **SUB-ENSAMBLAJE** (p. ej. UNA hoja: sus 5 tablas + vidrio + 6 medias-bisagras) sin tocar el
      documento. La función `assembly_manual(scene, ...)` ya operaba sobre cualquier subconjunto; solo se
      filtró la escena en el endpoint (espejo del `isolate` de `drawing_spec`). Verificado en la Hoja 1 de
      la puerta: 5 páginas (portada + 4 pasos: Refuerzos → Vidrio → Bastidor → Bisagras), render 0.9 s
      (`scripts/_leaf_cover.png`, `_leaf_slast.png` con las 6 bisagras resaltadas). 476 tests. Para UNA
      hoja también valen los planos 2D por `drawing(isolate=[...])`: medidas (`cutlist`+`datum_dims`) y
      ensamblaje (`explode`+`hardware`+`assembly_notes`) — `scripts/_hoja1_medidas.png`/`_hoja1_ensamblaje.png`.

## Convenciones y lecciones aprendidas

- **OCCT no es thread-safe**: TODO acceso al documento pasa por `apolo.state.STATE_LOCK`
  (RLock). Notificar por WebSocket solo DESPUÉS de construir el payload.
- Los tests no ejecutan el lifespan de FastAPI → no tocan la DB SQLite (`data/apolo.db`).
- **GOTCHA cirugía + `--reload` (2026-06-27)**: con la API en `--reload`, correr CUALQUIER script Python
  que `import apolo.*` (p. ej. validar medidas offline) recompila `.pyc` en `core/apolo/__pycache__`, que el
  watcher de uvicorn detecta → **recarga el worker → blanquea el DOC activo en memoria** ("0 sólidos",
  nombre vacío) AUNQUE no hayas editado código fuente. El borrado/edición SÍ se autoguardó en SQLite, así que
  basta `open_project(id)` para recuperar el estado post-operación. Para cirugía por HTTP intercalada con
  scripts offline: hazla toda por MCP/HTTP y deja la validación offline para ANTES de empezar, o `open_project`
  tras cada recarga. (Mismo síntoma que el zombie-socket, distinta causa.)
- **Rendimiento — un lote = UN regenerate (2026-06-17)**. `Document.regenerate()` replaya TODO el log
  (re-ejecuta todas las booleanas/fillets OCCT), así que un comando suelto ya es O(log). Antes un LOTE
  hacía N regeneraciones (O(N²) en booleanas → lotes de ~20 superaban el timeout de 120 s del MCP).
  Ahora `Document.execute_many(actions)` (lo usa `batch.py::execute_batch`) hace UN solo snapshot +
  UN solo `regenerate()` al final: lote **atómico** (o todo o nada) y **1 paso de undo**. No pre-valida
  por comando — el regenerate final valida en orden con las variables en construcción (así `set_variable`
  + uso en el mismo lote funciona; NO reintroducir `validate_params` en el bucle). Medido: 24 inserciones
  25 s (antes >120 s).
- **Rendimiento — regenerate INCREMENTAL (Fase 2, 2026-06-17)**. `regenerate()` ya no replaya todo el
  log: calcula una **firma acumulada por comando** (`_cmd_sig` = sha1(prev+id+params)), detecta el primer
  comando que cambió vs el regenerate anterior, **reanuda desde el checkpoint de estado más cercano** y
  re-ejecuta solo la cola. Checkpoints (`_regen_ckpts`) cada `_REGEN_STRIDE`=16 comandos + el último,
  guardados con `_copy_state` (shallow-copy de cada Feature, **compartiendo la referencia del shape OCCT**
  — seguro porque NINGÚN ejecutor muta el shape in-place, solo reasigna `feat.shape`). El commit de la
  caché es al final, solo si el regenerate completo (incl. validaciones + `solve_mates` + `resolve_all`)
  tuvo éxito → rollback seguro. `solve_mates`/`resolve_all` se ejecutan SIEMPRE post-loop (baratos). Editar
  una variable invalida desde el bloque de vars (conservador, correcto, poco frecuente). Medido en la puerta
  (244 comandos): edición/append **~1 s vs 13 s** de rebuild completo (~12×). Equivalencia incremental==full
  verificada en `tests/test_document.py::test_incremental_regenerate_equals_full` (append/edición media/
  edición de variable/undo/redo).
- **Rendimiento — mesh/render cacheado por shape (Fase 3, 2026-06-17)**. `scene_payload` ya no re-tesela
  todo cada request: `_cached_render(shape)` (en `api/main.py`) cachea **mesh + volumen + bbox por
  IDENTIDAD del shape OCCT** (`id(shape)` + referencia fuerte; cap 2048, clear al desbordar). Como el
  regenerate incremental conserva la MISMA referencia de shape para lo no cambiado, **solo se re-tesela la
  feature que cambió**; el resto es cache-hit. (Además el lookup de `command_type` pasó de O(features×comandos)
  a un dict O(1).) Medido en la puerta (244 comandos): **append/edición 0.15 s** (era ~1.1 s tras solo la
  Fase 2, y 13 s sin nada) → interactivo. La carga inicial (OPEN) sigue ~18 s (rebuild completo en frío +
  teselar todo) — una vez, no interactivo. **Follow-up**: persistir/paralelizar mesh en la carga; checkpoint
  por-comando para undo-del-último instantáneo; autosave con debounce si llega a notarse.
- **Disciplina paramétrica**: si una cota no cuelga de una variable/expresión, no sigue
  los cambios. Las piezas colocadas con coordenadas FIJAS se rompen al reparametrizar
  (lo confirmó la prueba de la faja: motor y fotocélula con coords fijas chocaron al
  ensanchar la banda; el resto, en `=expr`, cascadeó limpio).
- Componentes de catálogo: `position` = centro del bbox. Perfiles se extruyen en Z
  (rotar 90° sobre Y → larguero en X; sobre X → eje en Y para rodillos).
- `pattern_linear`/`pattern_circular` usan `count` ENTERO fijo (no expresión): al alargar
  un modelo, el conteo de copias no se recalcula solo. Limitación conocida (ver roadmap).
- `engineering_check` valida solo el super-comando `create_conveyor`, no máquinas hechas
  a mano. La validación universal de choques es `check_interference` (booleanas OCCT).
- Flujo de trabajo con el usuario: testea la UI a mano; errores en `logs/errors.log`; al
  decir "revisa", leer/agrupar por causa raíz/parchear/limpiar el log.
- **Mantenimiento de este CLAUDE.md (responsabilidad del agente, NO esperar al usuario)**:
  actualízalo por tu cuenta y de forma ESTRATÉGICA cuando cierres trabajo relevante —feature
  nueva, módulo, lección aprendida, cambio de arquitectura, conteo de tests/catálogo—. Es la
  fuente de verdad viva del proyecto. Sé conciso, coloca cada cosa en su sección, no dupliques
  y no anotes detalles efímeros de una conversación. Es preferible un commit del doc junto al
  del código a un doc que se queda atrás.
- **Punto ciego de `check_interference`/motion-scan — RESUELTO (2026-06-17)**. Excluían los pares
  padre-hijo de junta (contacto legítimo del conector), escondiendo interpenetración entre dos
  cuerpos que comparten junta (dos hojas en una bisagra, hoja↔jamba en un pivote). Ahora
  `checks.py::interpenetration_report(scene, posed, joint_pairs)` cierra el hueco: para cada par
  de junta compara el solape en pose contra el de la **pose de diseño** (junta=0 = contacto
  intencional = línea base) y reporta solo el **EXCESO** (tol 50 mm³). Cableado en `scan_collisions`
  y en `/api/checks` (con `joint_values`). Distingue contacto del conector (no crece) de cuerpos
  cruzándose (crece). Un nudillo/pasador simétrico sobre el eje no se marca; dos losas en bisagra de
  eje central que se cruzan al plegar, sí. 340 tests (`tests/test_interpenetration.py`).
  Para una verificación ad-hoc offline sigue valiendo medir la intersección booleana directa
  (`doc.commands=log; doc.regenerate()` —usa ids guardados— + `posed_shapes`).
- **Bisagras de pliegue/pivote**: pivotar sobre el eje CENTRAL de una hoja gruesa mete su cara en
  el cuerpo vecino. El eje de giro va en la **CARA hacia la que pliega** (bisagra tipo libro):
  offset `±esp/2` en el `origin` de la junta. Se halla empíricamente midiendo el solape.
- **Contención de layout (UI)**: toda región scrollable/flex necesita altura ACOTADA
  (`minmax(0,1fr)`). Un grid con fila implícita `auto` crece hasta el hijo más alto y desborda
  sobre el vecino (bug real: el `.right-dock` con el chat se montaba sobre el dock inferior).
- **Lazo cerrado vs árbol abierto**: la FK de Apolo es un árbol (padre→hijo). Los mecanismos de
  lazo cerrado (puerta plegable = pivote + corredera de riel + bisagra a la vez) se resuelven con
  **`add_rail_constraint`** (`assembly/constraints.py`): marca una junta como DEPENDIENTE y resuelve
  su valor (búsqueda 1D acotada, scipy) para que un punto ancla siga una recta; el driver es la otra
  junta. `POST /api/constraints/solve` (read-only) lo aplica en vivo (arrastre en la UI). La FK
  reutilizable de un punto vive en `robotics/pose.py::feature_location`.

## Estado: V1·V2·V3·V4 COMPLETADAS + pulido post-V4 + FAJA DE BANDA + CATÁLOGO DE NORMAS (2026-06-15) + RESTRICCIÓN RIEL-CARRETE (A1·riel) + CATÁLOGO DE CARPINTERÍA + FIX VALIDACIÓN/INTERPENETRACIÓN + EBANISTERÍA + HERRAJE PULIDO + RENDER CON POSE (MCP) + MATES ÁNGULO/PARALELO + LOTE=1 REGENERATE + REGENERATE INCREMENTAL + MESH CACHEADO + VIDRIO TRANSLÚCIDO + HERRAJE PUERTA CORREDIZA REAL (U-100/D-100) (2026-06-17) + ERGONOMÍA MCP (retorno diff · edit PATCH · schema único · encuadre render) + PATTERN_GROUP (arrayar grupos, 36 comandos, 2026-06-23) + EDIT_BATCH + VARIABLES ON-CHANGE (ergonomía MCP, 2026-06-24) + AUTORÍA AGENTE-NATIVA: PERCEPCIÓN (multivista/etiquetas/sección) + MEDICIÓN + PÍXEL→3D + PREVIEW + INTENCIÓN (center_in/distribute) + N-GDL (add_constraint) (2026-06-24) + SISTEMA DE PLANOS PROFESIONAL A–G (cotas+normas · corte+nesting · detalle/cortes/rayado · cajetín+revisiones · juego de planos · DXF lineweight/PDF multipágina/A0-A4 · planos por INTENCIÓN · pulido de encuadre: escalas intermedias + globos en fila · DESPIECE ACOTADO POR PIEZA: tabla L×A×E + detalle de tabla con mortajas + cotas de montaje · PLAN PRO DE PLANOS COMPLETO 5/5 [juego completo · acota solo · herraje en lámina · explosionada · GD&T · fix layout iso/cajetín · COLOR tipo Inventor: iso sombreada] · PLANO DE ENSAMBLAJE PRO: norma en BOM/cédula · NOTAS DE MONTAJE · cotas de interfaz/pitch · cross-ref globo→hoja · MANUAL DE ENSAMBLAJE paso a paso [secuencia del log + render acumulado con highlight fantasma + cámara estable]) (48 tools · 39 comandos, 2026-06-24) · MATERIALES POLÍMEROS (pvc/caucho/carton, 2026-06-25) · VALIDACIÓN DE ENSAMBLAJE / SOUNDNESS (conectividad: ground/fasten + chequeo estático + autodetección, Fase 0+1; SIM DE GRAVEDAD de toda la máquina con casco convexo [gravity_test/exclude → "ver qué se cae"], Fase 2; UI panel "Montaje" [validar/gravedad] + CAÍDA ANIMADA EN EL VIEWPORT 3D [mallas reales, no GIF] + UNIONES DECLARADAS + PRUEBA EXACTA [auto-declarado por grafo de soporte dirigido; tools MCP declare_structure/get_connections/delete_connection], Fase 3; 2026-06-26 → 54 tools · 41 comandos) · RENDER VTK (sombreado suave como el web, anti-rayas) + ISOLATE en render_view (sin mutar doc, fuerza-mostrar) (2026-06-26) · SUPER-COMANDO `create_take_up` (tensor de cola trotadora: rodillo+rodamientos+seeger+eje fijo+perno pasante; componentes SEPARADOS+mapeados [soporte C + PERNO-Mxx]) + SUPER-COMANDO `create_drive_roller` (rodillo motriz: take-up un lado + eje largo Ø35 al reductor; reusa helpers de take_up.py, 43 comandos, 2026-06-27) · TENSOR REAL de tornillo (perno horizontal que atraviesa el eje roscado + soporte C de una pieza soldado al larguero; `dir_tensor`) + doc de montaje en los rodillos, instalados Ø35 en faja-paqueteria-4m (2026-06-27) · 527 tests · catálogo 191 refs

> **Resumen vivo**: V1+V2 (12 fases, abajo) ✅ · V3 (7 bloques, diseño de máquina pro) ✅ · V4
> (T1·T2·V2·V1·G1·G2·G3·F1·F1·A, sistema) ✅. **Pulido post-V4**: lavado de cara UI (ribbon + lucide),
> realismo de catálogo (motor/tambor/rodillo con eje; CATALOG 57), ergonomía "CAD pro" (atajos, menú
> contextual, hover, encuadre, aislar, duplicar). Detalle de cada bloque en sus secciones; pendientes
> vivos en "Pendientes (follow-ups)".

**V1+V2 — las 12 fases originales:**
F1 esqueleto IA-nativo · F2 paramétrico (variables/expresiones) · F3 biblioteca+BOM+
transportador · F4 agente validador (sandbox, reglas, interferencias, visión) · F5
planos 2D (HLR, SVG/DXF/PDF) · F6 robótica (juntas, brazo 4 ejes, URDF/SDF) · F7
modelado (fillet/chamfer/shell/drill/patrones/espejo/revolve/extrude + import STEP) ·
F8 ensamblajes (instancias compartidas, mates, colisión en pose) · F9 producto (proyectos
SQLite, autosave, revisiones, configuraciones, colores) · F10 IA-first (servidor MCP,
modo auto, memoria del agente) · F11 sketcher restringido (solver scipy propio) ·
F12 planos pro (callouts Ø, CORTE A-A, globos+BOM, cotas por sólido).

---

# Hoja de ruta V3 — de "maqueta" a "diseño de máquina profesional"

Definida con el usuario (2026-06-13) tras construir una faja de banda completa por MCP y
evaluar honestamente la brecha con software de alta gama (Fusion/SolidWorks/Inventor/NX).

## Principio rector

NO perseguir paridad función-por-función con los incumbentes (20–30 años, cientos de
ingenieros, kernels Parasolid/ACIS). El moat de Apolo **no es el kernel** (OCCT, igual que
FreeCAD) sino la **arquitectura agente-nativa, API-first, command-log, schema-driven**, que
los monolitos antiguos no pueden retrofitear barato. Estrategia = **cuña**: ser el mejor
CAD agente-nativo para un vertical (transportadores/manejo de materiales), interoperable
por STEP, manejable por humano O por IA; y como **backend headless (API+MCP)** que otras
herramientas/agentes invocan. Eso es viable y diferenciado; "reemplazar a SolidWorks" no.

## Madurez — LÍNEA BASE (2026-06-17) · referencia para "¿cómo va madurando Apolo?"

> Cuando el usuario pregunte cómo madura Apolo, COMPARAR contra esta tabla (escala vs. un
> incumbente maduro = 10) y reportar qué subió. Veredicto base: **MVP coherente y bien
> arquitecturado en su nicho**, kernel nivel FreeCAD, con una capacidad agente-nativa que
> NINGÚN grande tiene; ~**5–15 % de la superficie de funciones** de Fusion/SolidWorks. No es
> reemplazo general de SW (ni lo intenta) — es una **cuña**.

| Dimensión | Nivel | Nota |
|---|---|---|
| **IA-nativa / API-first / command-log / schema-driven** | **9** ⭐ | El moat. Authoring completo por agente (MCP); adelante de todos. |
| Kernel B-rep / booleanas (OCCT) | 6 | Nivel FreeCAD; bajo Parasolid/ACIS en booleanas duras/blends/ensamblajes enormes. |
| Modelado paramétrico (features) | 4–5 | Buena amplitud + expresiones + selectores declarativos; sin superficies/NURBS ni modelado directo. |
| Croquis restringido (solver scipy propio) | 3 | El eslabón más flojo del modelado manual. |
| Ensamblaje / restricciones | 3–4 | Mates por cara + juntas/FK + motion + riel lazo-cerrado + ángulo/paralelo; sin multi-GDL acoplado ni grandes ensamblajes. |
| Planos 2D | 4 | HLR, SVG/DXF/PDF, cortes, globos+BOM, cotas; sin GD&T pro. |
| Simulación | 2 | Checks analíticos + drop-test MuJoCo (AABB); **sin FEA/CFD**. |
| Interop (STEP/IGES por OCCT) | 5 | Lo esencial. |
| Rendimiento / escala | 4 | Regenerate incremental O(N) (edición 13 s→0.15 s); no probado a miles de piezas. |
| Robustez (casos límite) | 3 | Joven vs 20–30 años de los grandes. |
| CAM | 0 | Fuera de alcance deliberado. |
| Colaboración / PLM / nube | 1 | Revisiones SQLite locales; sin multiusuario. |
| Ecosistema (plugins/docs/comunidad) | 1 | Incipiente. |

**Cómo medir el progreso (no por paridad con SW):** profundidad del vertical (catálogo + validación de
ingeniería REAL + planos fabricables), robustez del kernel en los casos del nicho, y explotación del moat
(agentes externos usando Apolo headless). Subir CAM/FEA/PLM/superficies NO es el objetivo. Evidencia de la
línea base: un agente construyó por MCP una puerta plegable (cinemática de lazo cerrado, catálogo, ebanistería)
y refactorizó el motor a regeneración incremental, todo por API.

## Los 7 bloques que faltan (priorizados por valor para máquinas)

> **Estado**: Bloque #1 ✅ (2026-06-13). Catálogo data-driven (YAML en `library/data/`,
> `loader.py` + `builders.py` genéricos), familias paramétricas (`param_keys`+
> `weight_formula`), 4 familias nuevas → 42 componentes. Desacoplados `CreateConveyorParams`,
> `rules.py`, `conveyor.py`. **Para añadir partes**: editar/crear un `*.yaml` en
> `library/data/` (prefijo numérico ordena); builder genérico nuevo en `builders.py` solo si
> la geometría no existe.
>
> **Bloque #7 ✅ (2026-06-13). Viewport PBR.** Render profesional, solo frontend (backend
> intacto, 189 tests verdes). Módulos nuevos en `ui/src/viewport/`: `scene-setup.ts`
> (renderer ACES+sRGB+shadowMap, luces, suelo `ShadowMaterial`+`updateGround`/shadow
> camera), `environment.ts` (IBL con RoomEnvironment+PMREM, sin assets→CSP-safe),
> `materials.ts` (tabla material→metalness/roughness desde `specs.material` del catálogo;
> albedo=`feat.color`; default para piezas a medida), `meshes.ts` (geometryFrom con
> `toCreasedNormals` 35°→curvas suaves+cantos vivos; `buildMesh` recibe `catalogByRef`;
> cast/receiveShadow), `viewcube.ts` (widget de esquina, clic→reorienta vía `setViewDir`).
> `Viewport.tsx` orquesta. **Follow-up**: extraer picking/box-select/medición/sección/
> cinemática/gizmo (siguen en `Viewport.tsx`).
>
> **Bloque #2 ✅ (2026-06-13). Mates persistentes.** Comando `add_mate` (categoría
> `ensamblaje`, flag `wants_mates`) que crea una relación de ensamblaje nombrada entre dos
> piezas por sus CARAS, almacenada como las juntas (`Document.mates`, regenerada del log) y
> **re-resuelta en `regenerate`** → al editar la pieza base, la mateada se recoloca sola
> (arregla el defecto "coords fijas se rompen"). Solver en `core/apolo/assembly/mates.py`
> (paquete nuevo, espejo de `robotics/`): `connector_of` (cara plana→centro+normal;
> cilíndrica→punto en eje+eje vía OCCT BRepAdaptor), `solve_mates` (orden topo hijo→padre,
> transform frame-a-frame), `register_mate` (validación tipo junta: 1 mate por hijo, sin
> ciclos). Tipos: `coincidente`, `distancia` (acepta `=expr`), `concentrico` (tornillo en
> agujero), + `flip`. Helpers en `kernel/matrix.py` (`frame`/`invert_rigid`/
> `euler_from_matrix`/`translation_of`). API `GET/DELETE /api/mates`; panel `MatesPanel.tsx`
> ("Ensamblaje") + grupo en Toolbar; creación schema-driven con picking de caras. 201 tests.
> **Follow-up**: conectores por ancla/arista, mate paralelo/ángulo, multi-restricción.
>
> **Bloque #4 ✅ (2026-06-13). Sweep / Loft.** Comandos `sketch_sweep` (perfil de croquis
> barrido por una trayectoria 3D de puntos `[x,y,z]`, recta o spline) y `sketch_loft`
> (transición entre ≥2 secciones de croquis a distintas z), categoría `croquis`. Geometría en
> `core/apolo/kernel/sweep.py` (`path_from_points`→Polyline/Spline, `make_sweep` con
> `Transition.RIGHT` para seguir esquinas vivas + perfil orientado a la tangente inicial,
> `make_loft`). Reutiliza `sketch_to_face`. Models `SketchSweepParams`/`LoftSection`/
> `SketchLoftParams`; `path` y `z` aceptan `=expr`. UI: el SketcherDialog gana ops **Barrer**
> (textarea de trayectoria + suave) y **Transición** (acumulador de secciones + ruled). 211
> tests. **Follow-up**: path como croquis/wire dibujado, `Helix`, sweep multisección, editar
> sweep/loft desde Propiedades.
>
> **Bloque #6 ✅ (2026-06-13). Motion study.** Línea de tiempo que anima las juntas (ver la
> máquina funcionar) + escaneo de colisiones a lo largo del recorrido. Reutiliza la cinemática:
> el FK ya es client-side y barato (cambiar `jointValues` re-posa el viewport). `Document.motion`
> = fotogramas `{t, values:{junta:valor}}`, persistido en el manifest (patrón configurations) +
> autosave; `set_motion` valida/ordena. `core/apolo/robotics/motion.py`: `values_at` (interp.
> lineal) + `scan_collisions` (muestrea el recorrido y reusa `posed_shapes`+`interference_report`
> +`joint_pairs`). API `GET/PUT /api/motion`, `POST /api/motion/scan`. UI: sección **Animación**
> dentro de KinematicsPanel (capturar fotograma desde los sliders, lista, ▶ Reproducir con bucle
> `requestAnimationFrame` que interpola y hace `setJointValues` bulk, 💥 Comprobar recorrido).
> 218 tests. **Follow-up**: easing, exportar vídeo/GIF, multi-estudio, física/gravedad
> (vía export URDF→PyBullet).
>
> **Bloque #5 ✅ (2026-06-13). Soldadura / weldments.** Comando `create_weldment` (super-comando
> tipo conveyor, categoría biblioteca): bastidor rectangular ancho×fondo×alto + perfil del
> catálogo → 4 postes + perímetros sup/inf + N anillos intermedios, miembros recortados a tope
> (sin solape), **lista de corte automática vía BOM** (miembros = instancias de catálogo con
> cut_length) y cordones de soldadura opcionales (esferas en nodos). Generador en
> `library/weldment.py` (`weldment_parts`, espejo de `conveyor.py`); `_exec_create_weldment` en
> registry; `CreateWeldmentParams` con enum dinámico de perfiles. Mejora general:
> `checks.same_command_pairs(doc)` (parejas de features del mismo command_id) unido en
> `/api/checks` y en el scan de motion → los miembros/cordones de un super-comando no se
> auto-reportan como interferencia (beneficia también a conveyor/brazo). 226 tests. **Follow-up**:
> esqueleto de aristas arbitrario + ingletes en ángulo + cordones realistas (sweep/fillet).
>
> **Bloque #3 ✅ (2026-06-14). Chapa metálica + desplegado.** Comando `create_sheet_metal`
> (super-comando, categoría biblioteca): bandeja paramétrica = base ancho×fondo de `espesor` +
> pestañas (flanges) seleccionables en los 4 lados (frente/atras/izquierda/derecha) con altura,
> ángulo y radio. Generaliza soporte en L (1 pestaña), canal en U (2) y bandeja (4). 3D con
> **pliegue vivo** (cajas unidas, robusto; el radio alimenta el desplegado, no el 3D). Función
> estrella: **desplegado a plano (flat pattern)** con *bend allowance* estándar
> (`BA=(π/180)·θ·(r+K·t)`, `θ=180−ángulo`, K-factor), contorno en cruz + líneas de plegado,
> exportable a **DXF/SVG para corte láser** reutilizando `SheetModel`+`sheet_to_dxf/svg`.
> `library/sheetmetal.py` (`bend`, `sheet_metal_solid`, `flat_pattern`); `_exec_create_sheet_metal`
> en registry; `SheetMetalParams`; endpoints `GET /api/sheetmetal/{fid}/flat.dxf|svg`
> (lookup por `feat.command_id`); tool MCP `export_flat_pattern`; botón "Patrón plano" en
> Properties. 243 tests. **Follow-up**: pliegue radiado en 3D, cutouts/taladros proyectados al
> blank, ingletes/alivios de esquina, pliegues en cascada, tabla de K-factor por material.
>
> **🏁 Roadmap V3 COMPLETO (7/7 bloques).** Pendiente solo la mejora transversal `pattern_*`
> por expresión. Fuera de alcance deliberado: CAM, FEA real, PCB, nube multiusuario.

| # | Bloque | Por qué importa en máquinas | Esfuerzo |
|---|--------|------------------------------|----------|
| 1 ✅ | **Catálogo de partes estándar** (data-driven YAML + familias paramétricas) | Una máquina es 60–70 % piezas de catálogo. El mayor salto de realismo/utilidad, bajo riesgo | Medio (continuo) |
| 2 ✅ | **Mates/juntas persistentes** (restricciones de ensamblaje que sobreviven a cambios, no coordenadas fijas) | Corazón de un ensamblaje real; arregla la limitación de "coords fijas se rompen" | Alto |
| 3 ✅ | **Chapa metálica** (pestañas, plegados, desplegado a plano DXF/SVG) | Guardas, cárteres, soportes, tolvas | Alto |
| 4 ✅ | **Sweep / loft** (barridos por trayectoria) | Bandas envolventes reales, mangueras, cable, perfiles propios | Medio |
| 5 ✅ | **Soldadura / weldments** (estructura de perfil con cordones y despiece) | Bastidores soldados (el vertical) | Medio |
| 6 ✅ | **Motion study** (línea de tiempo que anima las juntas; ya existen juntas+FK) | Verificar que el mecanismo funciona sin chocar | Medio-alto |
| 7 ✅ | **Viewport profesional** (materiales PBR, sombras, IBL, ViewCube) | Es lo que hace que "se vea" pro; cambia la percepción al instante | Medio |

---

# Hoja de ruta V4 — mejoras pendientes del SISTEMA

> Recogida tras construir por MCP una faja de banda con mesa de deslizamiento (2026-06-15) y
> chocar con límites REALES de la plataforma (no del modelo). Son límites de **Apolo**, no de
> ninguna máquina concreta. Priorizadas por valor/coste. Las marcadas `[follow-up Bn]` ya
> estaban anotadas en el bloque n de V3.

## Transversales (afectan a todo, máximo apalancamiento)

- **T1 ✅ (2026-06-15) · `pattern_*` con `count` por `=expresión`** (p. ej.
  `=(largo-2*paso)/paso + 1`). `PatternLinearParams`/`PatternCircularParams` mantienen `count: int`
  (ge=2/le=200) y ganan un `field_validator("count", mode="before")` = `_floor_to_int` en
  `commands/models.py`: el pipeline ya resolvía `=expr`→float antes de pydantic, y este before-
  validator lo trunca a int (13.33→13). Executors, `expressions.py`, `document.py` y la UI
  **intactos** (el form ya trataba `integer` como texto y conserva los `=...`). Si la expresión
  resuelve <2 → error de rango (sin clamping silencioso). 247 tests. Ahora al reparametrizar, el
  nº de copias cascadea solo (verificado por MCP: variable 4→7 → 4→7 instancias).
- **T2 ✅ (2026-06-15) · Exclusión de hardware en `check_interference`**: la tornillería y los
  rodamientos asentados en su alojamiento ya NO se reportan como interferencia. `checks.py` gana
  `hardware_ids(doc)` (features cuya categoría de catálogo ∈ `{tornilleria, rodamientos}`) e
  `interference_report(..., exclude_ids=...)` que las saca del análisis; cableado en `/api/checks`,
  `scan_collisions` y el `check_interference` del agente. Una chumacera (categoría propia) SÍ se
  chequea. Tradeoff: el hardware normalizado queda fuera del chequeo (convención estándar). 263
  tests. Verificado por MCP: tornillo embebido en chumacera → 0 interferencias.

## Geometría / modelado

- **G1 ✅ (2026-06-15) · Sweep en lazo CERRADO + Helix.** `kernel/sweep.py`: `path_from_points`
  gana `closed` (auto-cierre si primer≈último) → `Polyline(close=)`/`Spline(periodic=)`; nuevo
  `helix_path(radius, pitch, turns, lefthand)` con `Helix` (resortes/roscas, altura=pitch·turns);
  `make_sweep(face, path, is_frenet)` recibe el path YA construido y pasa `is_frenet` (estabiliza el
  perfil en lazos/hélices — el ancho no gira). `SketchSweepParams`: `path` opcional + `closed` +
  `helix` (HelixSpec, acepta `=expr`) + model_validator (path≥2 o helix). UI SketcherDialog: toggles
  "cerrada (lazo)"/"hélice" + inputs radio/paso/vueltas. 272 tests. Verificado por MCP: banda en
  lazo de un solo sólido + resorte helicoidal. **Follow-up que queda**: path como croquis/wire
  dibujado, sweep multisección, y convención de orientación del perfil ancho (hoy el lado del perfil
  cae en el binormal del lazo; para una banda ancha, dibujar el perfil en consecuencia).
- **G2 ✅ parcial (2026-06-15) · Chapa: taladros + pliegue radiado.** `create_sheet_metal` gana
  `holes` (lista de taladros en la base, x/y centrados + Ø, aceptan `=expr`): se cortan en el 3D
  (cilindros booleana en `sheet_metal_solid`) Y se proyectan al DESPLEGADO como `Circle(kind="corte")`
  en `flat_pattern` (centro de base→blank), saliendo en capa CORTE del DXF/SVG para corte láser.
  Pliegue **radiado en 3D** best-effort: `_fillet_bends` selecciona la arista cóncava por lado
  (`filter_by(Axis)` + `filter_by_position`) y aplica `fillet(radio)`; si falla (radio grande,
  esquinas de 4 lados) cae al pliegue vivo (try/except) — nunca rompe, y el desplegado ya
  incorporaba el radio. `drawing/svg.py`+`dxf.py` despachan `Circle` por `kind`. 277 tests.
  Verificado por MCP: bandeja con 3 taladros → 3 círculos en capa CORTE del flat. **Follow-up G2**:
  cutouts rectangulares, taladros en pestañas (mapeo con bend allowance), radiado robusto vía
  `make_brake_formed`, tabla de K-factor por material. `[follow-up B3]`
- **G3 ✅ parcial (2026-06-15) · Weldments: esqueleto de aristas arbitrario.** Comando nuevo
  `create_frame` ("Esqueleto", categoría biblioteca): `nodes` (3D, aceptan `=expr`) + `edges`
  (pares de índices) → un miembro de perfil por arista en CUALQUIER dirección, recortado a tope
  (`L-2·sección`), lista de corte (BOM agrupa por longitud) y cordones (esferas) en los nodos.
  Geometría en `library/frame.py::frame_from_edges` (reusa `WeldmentPart`/`_section`/`build_component`);
  orientación Z→dirección con `kernel/matrix.py::direction_to_euler` (frame Gram-Schmidt +
  `euler_from_matrix`). `_exec_create_frame` reusa `_emit_weldment_parts` (loop extraído, compartido
  con el bastidor rectangular — instancias por `base_key` + matriz). Hereda la exclusión de
  interferencia por `same_command_pairs`. UI: `SchemaForm` gana un **textarea para `list[list[number]]`**
  (genérico para nodes/edges, acepta `=expr`). 284 tests. Verificado por MCP: pórtico con cubierta a
  dos aguas (6 miembros + 5 cordones, 0 interferencias). **Follow-up G3**: ingletes a inglete reales
  (corte angular en nodos), cordones realistas (sweep/fillet en la junta), unificar la caja
  `create_weldment` sobre `frame_from_edges`, editor visual de esqueleto. `[follow-up B5]`
- **G4 · Editar sweep/loft/chapa desde el panel Propiedades** (hoy se re-crean).

## Ensamblaje / cinemática

- **A1 · Mates**: conectores por ancla/arista, ~~mate paralelo/ángulo~~ ✅ (2026-06-17), multi-restricción. `[follow-up B2]`
  - **A1·orientación ✅ (2026-06-17) · Mates `paralelo` y `angulo`.** `assembly/mates.py`: dos tipos nuevos en
    `_desired_current_frames` que ORIENTAN la normal de B (paralela a la de A, o a `value` grados vía Rodrigues
    `_rotate_about`) SIN mover su posición (desired origin = b_origin). `MATE_TYPES`/`models.py` ampliados →
    aparecen solos en el desplegable de la UI/agente. 349 tests (`tests/test_mates_orientacion.py`). **Queda**:
    multi-restricción real (un hijo con ≥2 mates resueltos simultáneamente; hoy 1 mate por hijo, árbol).
  - **A1·riel ✅ (2026-06-17) · Restricción riel-carrete (lazo cerrado).** Comando `add_rail_constraint`
    (categoría ensamblaje, `wants_constraints`): un punto ancla del hijo de una junta queda cautivo sobre
    una recta; esa junta pasa a DEPENDIENTE y su valor se resuelve (1D acotada, `scipy.minimize_scalar`)
    en cada pose, con la otra junta de driver. Resuelve el lazo que el árbol de FK no podía (puerta
    plegable top-hung: pivote+corredera). `assembly/constraints.py` (`register_constraint`/`solve_constraints`,
    espejo de `mates.py`); `robotics/pose.py::feature_location` (FK de un punto, sin teselar); thread de
    `constraints` por `execute_command`/`regenerate`; endpoints `GET/POST /api/constraints[/solve]`/`DELETE`
    + cableado en el motion-scan. UI: dependientes marcadas «auto · riel» (bloqueadas), `driveJoint` resuelve
    en vivo al arrastrar el driver (throttle 40 ms). Verificado: 0.000 mm fuera del riel de 0→60° (tope del
    mecanismo a ~62°). 332 tests (`tests/test_constraints.py`). **Follow-up**: multi-restricción/N-GDL,
    solver de lazo genérico, editor visual de restricciones.
- **A2 · Motion study**: easing, exportar vídeo/GIF, multi-estudio. `[follow-up B6]`

## Validación / ingeniería (analítico, barato)

- **V1 ✅ (2026-06-15) · `engineering_check` universal** (fajas hechas a mano, no solo el
  super-comando). `rules.py` (puro) gana `detect_conveyor(scene)` que infiere la faja de sus PIEZAS
  (≥1 motorreductor + ≥1 perfil + (rodillos de catálogo O tambores=cilindros sin componente con
  "tambor" en el nombre)) → dict con `tipo` (banda/rodillos), `tambor_d` (de bbox), `rpm_motor`/
  `torque_Nm` (specs del motor), ancho/largo/altura/paso. `conveyor_engineering_check` se amplía
  (retrocompatible) con reglas nuevas gated por esos campos: **velocidad de banda** real
  (`rpm·π·Ø/60000`, avisa si < objetivo), **par del motor** (par_req=F·r vs torque), apoyo continuo
  si `tipo==banda`, y **geometría** (altura de trabajo). Helpers `band_speed_m_s`/`required_force_n`.
  Fallback `_conveyor_params_from_doc → detect_conveyor` en `/api/checks` y el agente. 267 tests.
  Verificado por MCP en la faja con mesa: detecta y avisa 15 m/min vs 20 objetivo (el diagnóstico
  que antes era manual). **Follow-up**: deflexión de viga del bastidor, voladizo de tambores.
- **V2 ✅ (2026-06-15) · Catálogo ampliado** (data-driven): +4 builders en `library/builders.py`
  (`pillow_block`, `endstop`, `leveling_foot`, `tensioner`) + 4 familias YAML
  (`95_chumaceras`, `96_topes`, `97_pies_niveladores`, familia TENSOR en `85_transmision`) → 12
  componentes nuevos (CHUM-6204/05/06, TOPE-M6/8/10, PIE-M8/10/12, TENSOR-40/50/60). Categorías
  nuevas en `catalog.py`. Aparecen solos en BOM/UI/agente (enums dinámicos). CATALOG: 42→54.
  **Follow-up V2 (continuo)**: añadir más familias según haga falta (cadenas, sprockets, bridas).

- **Realismo de catálogo ✅ (2026-06-15)** (a raíz de "la faja se ve básica"): los builders de
  `library/builders.py` ahora fusionan más sólidos en UNA Feature para parecer reales — **`motor`**
  = reductor + motor + EJE de salida + caja de bornes + patas (params nuevos con default, escala con
  `box_size`; sin tocar el YAML salvo lo existente); **`roller`** dejó de ser alias de `cylinder` →
  tubo + EJE pasante con muñones (`shaft_d`); **`drum`** NUEVO (tambor/polea: cuerpo + eje pasante +
  lagging opcional) con familia YAML `22_tambores.yaml` (TAMBOR-80/100/120) y categoría `tambores`.
  CATALOG 54→57. Como el doc es log de comandos, **al regenerar, las inserciones existentes recogen
  la geometría nueva** (la faja id 18 estrenó ejes en rodillos y motor detallado sin reconstruirse).
  Lección: el eje del rodillo sobresale → toca el larguero en `create_conveyor` (montaje real); el
  chequeo correcto excluye `same_command_pairs` (test_validation actualizado). 294 tests.
  Reconstrucción del modelo id 18 por MCP: **banda = lazo envolvente** (racetrack hueco por booleanas
  Ø86−Ø80, ya no dos planchas), tambores → TAMBOR-80, **ejes Ø25 que entran en las chumaceras** (fin
  del "rodillo flotante"), tornillos asentados (cabeza a ras), acople motor↔tambor. Las
  "interferencias" que quedan son contactos INTENCIONADOS (eje-en-rodamiento, banda-sobre-mesa,
  acople) — confirman que las piezas por fin se conectan. **Follow-up**: lagging visible distinto,
  cutouts/chaveta del acople, idlers de carga, unificar tambores hechos a mano sobre el builder.

## Física (motor aparte — el bloque grande)

- **F1 ✅ parcial (2026-06-15) · Gravedad / drop-test de producto.** Vía FUERTE (motor embebido).
  **Motor = MuJoCo (Apache, `mujoco>=3.9`), NO PyBullet**: PyBullet no publica wheel para Python
  3.13 y compilar requiere MSVC → se pivotó a MuJoCo (mismo alcance). Análisis read-only (como
  `check_interference`), NO muta el documento. Paquete nuevo `core/apolo/physics/` (espejo de
  `robotics/`): `sim.py::drop_test(scene, products, seconds, gravity, fps)` arma un mundo MJCF
  (suelo + cada sólido visible como caja ESTÁTICA por su AABB + productos como cajas DINÁMICAS con
  freejoint), simula con `mj_step` (timestep 0.004, mm↔m ×0.001) y muestrea `fps` fotogramas →
  `{frames:[{t, poses:{prodN: mat4×4 mm}}], resting:{prodN:[x,y,z]}, settled, products}`;
  `anim.py::render_drop_gif` reutiliza la teselación matplotlib de `kernel/render.py` (escena
  estática atenuada + cajas de producto por fotograma) → GIF (Pillow). API `POST /api/physics/drop`
  (JSON) y `POST /api/physics/drop.gif` (image/gif); tool MCP `drop_test(products, path, seconds,
  gravity)` que guarda el GIF y devuelve reposo+settled. Extra opcional `[project.optional-
  dependencies] physics = ["mujoco>=3.9","pillow>=10"]`; el server lo importa perezosamente (501/400
  claro si falta). 293 tests (9 nuevos, `pytest.importorskip("mujoco")`). Verificado e2e por HTTP
  sobre la faja id 18: 3 cajas 200×150×120 (5 kg) soltadas a z=1100..1500 caen y se asientan
  estables (settled, GIF de 26 fotogramas). **Limitación honesta (AABB)**: la colisión usa el
  bounding-box de cada sólido, así que la mesa de deslizamiento en U se vuelve una caja maciza hasta
  su borde-guía (z=790) y el producto reposa en z≈850 en vez de sobre la cara real de la banda
  (z=752).
  - **F1·A ✅ (2026-06-15) · Reproducción animada en el VIEWPORT** (solo-frontend, sin tocar el
    backend; cierra "se sentirá nativo"). Panel **Física** (`bottomPanel:"fisica"`) donde se definen
    cajas de producto (lista editable w/d/h/x/y/z/mass) y se sueltan: `POST /api/physics/drop` →
    se reproducen las poses por fotograma en el viewport PBR. Módulo nuevo
    `ui/src/viewport/products.ts` (mandato de escala: NO engordar `Viewport.tsx`): `buildProductMeshes`
    (`BoxGeometry` centrada = la pose la coloca), `interpolatePose` (lerp traslación + slerp rotación;
    `Matrix4.set` FILA-mayor — el endpoint devuelve row-major, ≠ `feat.matrix` columna-mayor),
    `createDropAnimator` (stop-and-rest; lee play/speed por `getState()` → CERO re-render de React),
    `disposeProducts`. Cajas = overlay efímero en `ctx.scene` (NO `ctx.group` → fuera del raycast de
    selección/box-select); el `tick()` corre en el rAF loop existente. Estado efímero en store
    (`physicsResult/Playing/Speed/Token`, NO persistido; `clearPhysics()` en
    adoptScene/openProject/newProject/refresh y al cerrar el panel). Botón "Exportar GIF"
    (`fetch→blob→download`, porque `drop.gif` es POST). Build UI verde (tsc + vite). Test visual a
    mano (el `:8000` lo ocupa el server real y la ventana de Chrome no soporta tab-grouping del MCP).
  - **Follow-up F1 restante**: cascos convexos de colisión (no AABB) + inercia real del CAD (ya hay
  `robotics/model.py::_link_physics`); densidad/masa por categoría de catálogo; sim en tiempo
  real (acoplamiento continuo); y la vía DÉBIL (export SDF de escena SIN juntas — hoy `urdf/sdf`
  exige juntas) como alternativa sin dependencia. Ver sección "Gravedad / física" abajo.

## UI / arquitectura

- **UI·Lavado de cara ✅ (2026-06-15) · shell estilo CAD pro** (solo-frontend, lucide-react). El
  shell pasó de flex-column saturado a **grid de filas** `header / ribbon / workspace / bottomdock /
  statusbar` (`.app` en `styles.css`). Piezas: **Ribbon** (`panels/Ribbon.tsx`, sustituye Toolbar —
  borrada) con pestañas Crear/Croquis/Modificar/Ensamblar/Biblioteca/Robótica, sigue schema-driven
  (`schemas.filter(category)`) + recupera la categoría `croquis` que la toolbar vieja no mostraba;
  **StatusBar** (`panels/StatusBar.tsx`) con los 6 toggles de panel (antes en el TopBar) + `mm · N
  sólidos`; **BottomDock** (`panels/BottomDock.tsx`) redimensionable que envuelve los 6 paneles SIN
  tocarlos (cada uno se auto-gestiona por `bottomPanel`); **RightDock** (`panels/RightDock.tsx`)
  Propiedades + splitter + Chat; **TopBar** adelgazado (marca/proyecto/env-tabs/undo-redo/menú
  Archivo). Nuevos `ui/icons.tsx` (mapa comando→lucide + `iconFor`/FALLBACK; nunca rompe si falta un
  icono) y `ui/Splitter.tsx` (`useSplitter` pointer-events + `SplitHandle`, persiste en localStorage).
  Tema: tokens retro-compatibles (valores + nuevos `--radius/--sp/--shadow/--accent-soft`), sombras en
  modales/tarjetas, overlay del viewport tipo glass. **Bug del chat resuelto**: `.right-dock` ya no
  reparte 50/50; `chat-input` con `flex:0 0 auto` + `minmax(120px,1fr)` en la fila del chat → el input
  SIEMPRE visible (verificado e2e en build de producción con la faja id 18: ribbon cambia pestañas,
  StatusBar abre el dock con BOM, input del chat a la vista, 3D renderiza). Build verde (tsc+vite).
  **Avance de U1**: se extrajeron RightDock/BottomDock/StatusBar/Ribbon y los helpers `ui/*`; el
  interior de `Viewport.tsx` (picking/box-select/medición/sección/cinemática/gizmo) **sigue
  pendiente**. **Caveat dev (preexistente, no del facelift)**: `npm run dev` con `<React.StrictMode>`
  remonta el viewport Three.js dos veces y lo rompe; el build de PRODUCCIÓN (lo que se sirve en :8000)
  va bien. Para previsualizar usar `vite preview` (se añadió `preview.proxy` en `vite.config.ts` y las
  configs `ui-dev`/`ui-preview` en `.claude/launch.json`). Follow-up opcional: hacer el viewport
  StrictMode-safe o envolverlo en un ErrorBoundary.

- **UI·Ergonomía "CAD pro" ✅ (2026-06-15)** (a raíz de "¿hay atajos?, ¿cómo borro?"). Capa nueva
  mayormente frontend + 2 toques de backend. **Atajos de teclado** (`viewport/shortcuts.ts`,
  `installShortcuts` con un único keydown en window que lee handlers por getter): Supr=borrar,
  Esc=cascada (cancela pick→menú→gizmo→deselección→modal), Ctrl+Z/Y, Ctrl+A, Ctrl+D=duplicar, F=encuadrar,
  Inicio/0·1·2·3=vistas, W=alambre, M/R=gizmo, H/Alt+H/I=ocultar/mostrar todo/aislar, L=medir, S=sección,
  Ctrl+S=revisión, flechas/RePág·AvPág=empujar (Shift=fino), ?/F1=ayuda. Guards: ignora si foco en
  input o modal abierto (solo Esc cierra) y si gizmo-drag/box-select. **Pre-resaltado al pasar el cursor**
  (`viewport/hover.ts`, emisivo sutil ≠ selección). **Menú contextual** (`panels/ContextMenu.tsx` + store
  `contextMenu`) en viewport y árbol (Eliminar/Duplicar/Ocultar/Aislar/Centrar/Mostrar todo). **Encuadrar
  a selección / doble-clic enfoca / encuadre-al-abrir / zoom-al-cursor** (`frameBox`/`fitTo` en
  Viewport; `controls.zoomToCursor`; `CustomEvent("apolo:fit")` desacopla el store del three.js).
  **Aislar/ocultar/mostrar-todo** vía endpoint nuevo `POST /api/features/visibility` (lote) +
  `store.bulkVisibility`. **🗑 por fila en el Árbol + doble-clic enfoca + clic-derecho**; botones
  **Eliminar/Ocultar/Aislar en Propiedades**; **⌨ en StatusBar** + **overlay de ayuda**
  (`panels/ShortcutsHelp.tsx`). Backend: comando **`duplicate_feature`** (clon con desfase, es comando
  del log → undo/replay) + el endpoint de visibilidad en lote; acciones de store nuevas
  (`clearSelection/selectAll/deleteSelection/duplicateSelection/nudgeSelection/hideSelection/isolate/
  showAll`, todas vía `runBatch`). 297 tests (3 nuevos). Verificado e2e en navegador: ?/Esc, Ctrl+A
  (39 sólidos), menú contextual y overlay OK. **Nota**: las operaciones múltiples (`runBatch`) son
  ahora ATÓMICAS y **1 solo paso de undo** (ver "Rendimiento" abajo); antes eran N pasos (limitación v1, resuelta).

- **UI·Rotación precisa "CAD pro" ✅ (2026-06-17)** (a raíz de «rotar es muy simple, quiero 45/90/180 y ángulo
  exacto»). El rotar era solo arrastrar el gizmo `TransformControls` (sin snap ni numérico). Añadido en
  `viewport/Viewport.tsx` un **panel de rotación** (barra arriba-centro, aparece en modo Rotar): selector de
  **eje X/Y/Z** (color CAD rojo/verde/azul), botones de **ángulo directo −90/−45/+45/+90/+180**, **entrada
  numérica + Aplicar** (Enter), y **Snap del gizmo Off/15/45/90°** (`gizmo.setRotationSnap`, default 45). Los
  botones/numérico mandan un `transform` con `rotate` sobre el **eje elegido** (rotación sobre el centro del
  sólido, igual que el gizmo). Además **lectura de ángulo EN VIVO** al arrastrar el anillo (HUD en la barra de
  estado vía `objectChange`, sin re-render). Verificado e2e: el panel renderiza con todos los controles y +90°
  rota un sólido libre exactamente 50×72→72×50 (1 comando `rotate z=90`). **Caveat**: rotar un sólido que es
  RAÍZ de junta (p. ej. una jamba) no aplica; los botones operan sobre el sólido seleccionado tal cual. Pendiente
  opcional: rotar respecto a una arista/cara elegida (alinear), no solo al centro.

- **UI·Dimensiones de la selección ✅ (2026-06-17)** (a raíz de «multiselecciono con Ctrl+clic pero no veo la
  dimensión que ocupa»). La multiselección solo mostraba lista + volumen. Ahora la **caja envolvente global**
  (ancho X × fondo Y × alto Z) + **diagonal** se calcula del union de bboxes de los sólidos seleccionados y se
  muestra en **`Properties.tsx`** (rama `selection.length > 1`: filas «Dimensiones (conjunto)» y «Diagonal») y,
  compacta (`▢ W × D × H mm`), en la **barra de estado del viewport** (`Viewport.tsx`, también para 1 sólido).
  Todo cliente, sin comandos. Verificado e2e: 2 vidrios → `781 × 8 × 1808 mm`, diagonal 1969.49, en panel y barra.

- **UI·Feedback de carga ✅ (2026-06-25)** (a raíz de «cuando le doy a algo y demora, no sale nada que esté
  cargando, no sé si está cargando o no pasa nada»). Diagnóstico: la arquitectura ya estaba bien pero el feedback
  era **write-only** — el store envuelve casi todo async en `guard()` (`state/store.ts`) que ya seteaba `busy`,
  pero **casi ningún componente lo leía**; solo Validar/Física/Chat tenían feedback local (y ni pasaban por
  `guard`). Solución en 3 capas, todo frontend, aditivo. **(1) Núcleo**: `guard()` pasó de booleano a **CONTADOR**
  (`pendingCount`/`blockingCount` de módulo) → no se apaga el indicador si hay awaits solapados; nuevo estado
  `busyLabel` (texto amistoso derivado del prefijo de la etiqueta técnica vía mapa `BUSY_TEXT`, la técnica se
  conserva para el log de errores) y `blocking` (operaciones que reemplazan la escena). `guard(set, fn, opts)`
  acepta `{label, blocking}`; **`runTracked(label, fn, opts)`** público para componentes que llaman `api.*` directo
  (Validar/Física/BOM/Ensamblaje/Cinemática/Plano/Configuraciones). Acciones de proyecto pesadas (open/create/
  restore/duplicate por id) movidas al store con `blocking:true` (HomeScreen ya no duplica un `busy` local).
  **(2) Indicadores globales** (montados en `App.tsx`): `panels/TopProgress.tsx` (barra indeterminada fija arriba,
  siempre visible si `busy`), badge spinner+`busyLabel` en `StatusBar.tsx`, `panels/BusyOverlay.tsx` (overlay
  bloqueante "Abriendo proyecto…" para `blocking`), overlay `.viewport-busy` en `Viewport.tsx`, clase `.app.busy`
  (cursor progress). **(3) Por acción**: submit del comando con spinner+desactivado (`forms/SchemaForm.tsx` prop
  `busy`, lo pasan CommandDialog/Properties), undo/redo desactivados en `busy` (TopBar), spinner sobre la lámina
  del plano (DrawingDialog `onLoad`/`onError`), skeleton en BOM/Ensamblaje, botones desactivados durante
  check/scan (Cinemática) y en Variables/Configuraciones/Library/Chat-aceptar. Primitiva reutilizable
  `ui/Spinner.tsx` (Loader2 + `@keyframes apolo-spin`); CSS nuevo en `styles.css` (spin/indeterminate/shimmer +
  `.topprogress`/`.busy-overlay`/`.busy-badge`/`.viewport-busy`/`.skeleton`, con `prefers-reduced-motion`).
  a11y: `aria-busy`/`role=status`/`aria-live`. Verificado e2e (vite preview→API viva): top bar + badge
  "Comprobando…" + viewport-busy en Validar (read-only), "Generando plano…" en Planos, skeleton en BOM, overlay
  "Abriendo proyecto…" al abrir proyecto, y el contador SIEMPRE vuelve a 0 (idle limpio, 0 errores de consola).
  Build verde (tsc+vite). **Solo frontend** → rebuild de la UI (`npm run build`) y recargar; sin reiniciar API/MCP.

- **U1 · Refactor `Viewport.tsx`** (resto): extraer picking/box-select/medición/sección/cinemática/
  gizmo a módulos propios (ya se extrajeron el render PBR, la física de producto, el shell de UI y los
  atajos/hover/menú contextual). `[follow-up B7]`

## FEA — aplazado (bajo demanda del negocio)

- Ampliar `engineering_check` analítico cubre ~80 % por ~5 % del coste; el FEA visual grado
  Fusion (mallado + solver) es la frontera real, no abordar hasta que el negocio lo pida.

## Orden recomendado de ataque (V4)

1. ~~**T1** (pattern por expresión)~~ ✅ hecho 2026-06-15 — reparametrización ya 100% automática.
2. ~~**T2 + V2** (exclusión de hardware + catálogo)~~ ✅ hecho 2026-06-15.
3. ~~**V1** (validador universal)~~ ✅ hecho 2026-06-15.
4. ~~**G1** (sweep cerrado + Helix)~~ ✅ + ~~**G2** (chapa: taladros + radiado)~~ ✅ + ~~**G3** (weldment esqueleto)~~ ✅ hecho 2026-06-15. Geometría de alto nivel cubierta (quedan follow-ups finos por bloque).
5. ~~**F1** (física — drop-test con MuJoCo, no PyBullet)~~ ✅ parcial 2026-06-15 + ~~**F1·A** (reproducción
   animada en el viewport)~~ ✅ 2026-06-15. Follow-ups vivos: cascos convexos, inercia real, tiempo real.

**🏁 Roadmap V4: T1·T2·V2·V1·G1·G2·G3·F1·(F1·A) cerrados.** No quedan bloques nuevos — solo follow-ups (abajo).

**🏁 Super-comando `create_take_up` — tensor de cola tipo TROTADORA (2026-06-26).** Conjunto reutilizable
(rodillo de cola tensable) como UNA entrada del log, paramétrico, para enchufar en el extremo de cola de una
faja. Esquema trotadora de **eje fijo, SIN chumacera** (decisión del usuario): rodillo = tubo HUECO (bore = Ø
ext. del rodamiento), por DEFECTO **bare** (acero desnudo — un rodillo de cola no se engoma; el lagging es del
tambor motriz) y `engomado` opcional **a todo el ancho** (sin el escalón de los extremos que tenía la 1.ª versión
al heredar el 92% del builder de tambor); **eje FIJO** pasante que sobresale `voladizo` por lado con **agujero
transversal** en cada extremo; **2 rodamientos de catálogo** (el ref FIJA el Ø del eje = su bore) alojados en los
extremos + **2 seeger** de retención; **2 soportes en «C» con perno vertical pasante** (reusa el builder `take_up`)
que tensan al girar. `library/take_up.py::take_up_parts` (frame canónico: eje del rodillo a lo largo de Y,
centrado en el origen → al insertarlo basta `position`=(cola, 0, altura del eje)); reusa `build_component` (rodamiento),
`take_up` (soporte) y `_emit_weldment_parts`. `CreateTakeUpParams` (enum de `rodamientos`; `diam_rodillo`/`ancho_banda`/
`perno_d`/`voladizo`/`engomado`, aceptan `=expr`) + `_exec_create_take_up` en el registro (categoría biblioteca,
**41→42 comandos**). Se usa por `run_command(type="create_take_up", ...)` (sin tool MCP dedicada, como los otros
super-comandos). **(2026-06-26) COMPONENTES SEPARADOS Y MAPEADOS** (pedido del usuario: que el BOM diga qué perno
comprar): cada soporte se emite separado — **soporte en «C» a medida** (`espesor_soporte`, def 9.5mm=3/8" A36) +
**perno de catálogo `PERNO-Mxx`** (cabeza hex DIN 933 8.8) que **ROSCA DIRECTO en el agujero del eje** (el eje hace
de tuerca; el usuario quitó la tuerca soldada), cabeza apoyada en el ala superior. La «C» da **`holgura_eje`** mm de
recorrido al eje POR LADO (def 20); el **eje Ø = bore del rodamiento** (def **6207 → Ø35**). Builders nuevos
`hex_bolt`/`hex_nut` (`_hex_prism` con `RegularPolygon`+`extrude`) + familias YAML `108_pernos.yaml`(`pernos`)/
`109_tuercas.yaml`(`tuercas`), M10/12/16/20 (la tuerca queda en catálogo pero el tensor ya no la usa). Params:
`perno` (enum `pernos`) + `espesor_soporte` + `holgura_eje`; rodillo de cola por DEFECTO **bare** (engomado=False) y
el lagging a TODO el ancho (sin escalón — bug "caída" que reportó el usuario). 10 sólidos
(rodillo+eje+2×rodamiento+2 seeger+2 soporte+2 perno; sin tuerca). El perno usa un **largo COMERCIAL** (se
redondea al stock DIN 933 más cercano por arriba, `_STD_BOLT_LEN`; el nombre lleva el tamaño, p. ej.
`PERNO-M16×80`) — lo justo para cruzar la «C» y roscar en el eje, sin sobresalir de más; su vástago se
modela al largo elegido con `hex_bolt(...)(L)` DIRECTO — **gotcha**:
`build_component(ref, L)` ignora `L` si el componente no es `cuttable`, así que el perno salía siempre al
largo por defecto (50 mm) hasta construirlo a mano. 519 tests. **Catálogo 183→191 refs.** Verificado en el
proyecto vivo `take-up-cola` (id 40) por VTK. **OJO**: añadir YAML nuevo requiere que el worker recargue (lo dispara
el cambio .py); si el proyecto activo queda en blanco tras recargar, reabrir con `open_project`. Proyecto vivo
`rodillo-tensor-cola` (id 40). **Pendiente**: proporciones del soporte, fijación real al larguero.

**🏁 Super-comando `create_drive_roller` — rodillo MOTRIZ (2026-06-27).** Hermano de `create_take_up`: mismo
esquema trotadora pero ASIMÉTRICO — take-up (soporte «C» + perno) en UN lado y un EJE LARGO en el otro
(`largo_eje_motor`, def 250) para acoplar el motorreductor; eje Ø35 (6207), acero desnudo por defecto. Refactor:
`library/take_up.py` extrajo helpers compartidos (`_roller_body`, `_bearing_seeger_parts`, `_take_up_side`,
`_common`) que usan AMBOS generadores → cero duplicación (decisión del usuario: comando aparte, no meter un modo
en take_up). `CreateDriveRollerParams` + `_exec_create_drive_roller` (categoría biblioteca, **42→43 comandos**).
8 sólidos (rodillo+eje+2×6207+2 seeger+1 soporte+1 perno). Proyecto vivo `rodillo-motriz`. 524 tests
(`test_take_up.py`: tail+drive). **Nota honesta**: el take-up por perno-pasante asume eje FIJO; en un tambor
motriz de eje VIVO (que gira) el perno bloquearía el giro → para fidelidad mecánica, el lado motriz iría con
soporte deslizante o eje muerto + drum motorizado. El usuario lo eligió así a sabiendas (geometría consistente
con la cola). **Reiniciar API** (`--reload`) para servir el comando; reabrir proyecto si queda en blanco.

**🔧 Tensor REAL de tornillo + doc de montaje en los rodillos (2026-06-27).** Al instalar los rodillos en
`faja-paqueteria-4m` (id 38) el usuario corrigió el mecanismo del tensor (estaba mal en 2 intentos: perno
vertical, y luego longitudinal pero que solo *empujaba*). El correcto, explicado por el usuario (con croquis
aprobados): **perno HORIZONTAL a lo largo de la banda, cabeza al exterior, que ATRAVIESA el eje** (el eje tiene
HILO ahí = hace de tuerca); al girarlo el eje viaja sobre el perno → hacia la cabeza = **jala el rodillo = TENSA**
(empuja = afloja). Un **solo soporte en «C»** por lado: el **alma soldada al larguero** (al interior del bastidor)
y las **2 aletas** capturan el eje; el perno pasa por las 2 aletas + el eje. Implementado en `library/take_up.py`
(`_take_up_side` rehecho: 2 aletas normales a X con agujero de paso + alma normal a Y con agujero para el eje;
perno `hex_bolt` orientado con `Ry(±90)` de Z a ±X, cabeza al exterior; `_shaft_with_holes` taladra el agujero
transversal del eje). Param nuevo **`dir_tensor`** (cola=-1=-X, cabeza=+1=+X); `holgura_eje` queda EN DESUSO (el
recorrido lo da el claro entre aletas). Los `description` de `CreateTakeUpParams`/`CreateDriveRollerParams` ahora
traen sección **CÓMO MONTAR** (orientación eje Y / perno X / cabeza exterior / alma soldada al larguero / eje
motriz→reductor) — la causa raíz del error fue que el super-comando documentaba el "qué" pero no el "cómo montar".
En la faja se instaló con **ejes Ø35 (rodamiento 6207)** (pedido del usuario; `edit_command` rodamiento→6207). El
solape soporte↔larguero (~5–10 cm³) es el **cordón de soldadura** (intencional). Como el doc es event-sourced y
los ids de pieza no cambian, reabrir regenera con el tensor nuevo sin tocar la conectividad. 527 tests
(`test_take_up.py`: perno longitudinal / dir_tensor / agujero del eje). **Lección**: un super-comando reutilizable
debe documentar su MONTAJE/orientación, no solo qué es. **Reiniciar API + host MCP** para servir `dir_tensor`.

**🔧 Tensor al INTERIOR + ensanche paramétrico del bastidor (2026-06-27).** El usuario afinó: el soporte en «C»
va DENTRO del bastidor (estética trotadora), con el **alma soldada a la cara INTERIOR del larguero** y la «C»
abriendo hacia adentro — no asomando por fuera. Geom: `_take_up_side` ahora pone el alma en el borde exterior
(`y_alma = sgn*(half+voladizo)`) para que tope la cara interior del larguero; `_CW` 50→35 (cabe en el hueco);
`voladizo` por defecto 40 (= el hueco rodillo↔larguero). Para que el soporte quepa DENTRO hace falta hueco entre
el rodillo y el larguero, así que se ensanchó el bastidor: variable **`holgura_lado` 30→70** (larg_inner_y
350→420). **GOTCHA — la faja estaba llena de coordenadas FIJAS** que rompían el ensanche (el clásico "coords
fijas se rompen al reparametrizar"): hubo que hacer paramétricos (atándolos a `larg_cy`/`larg_inner_y`) los
**8 taladros del pie** (placa anclaje), **c90/c91** (agujero del eje), el **tren motriz completo** (motor/reductor/
guardas/brazo/cubierta: el larguero +Y se les metió encima al ensanchar; ahora `y=larg_inner_y+offset`), y los
**pernos de anclaje** (`c144-146` base `=larg_cy-40` + `c149` spacing2 `=-2*larg_cy`). Tras eso el ensanche
regenera limpio y el tren motriz/anclajes siguen al bastidor solos si vuelve a cambiar el ancho. Verificado:
soporte dentro del bastidor, 0 colisiones nuevas (lo que queda es soldadura soporte↔larguero + acople eje↔reductor
+ eje↔guardas, todo intencional). Revisión 60. **Lección**: reparametrizar un modelo "armado a mano" cascada por
todas sus coords fijas; conviene atar las piezas a las variables del bastidor desde el inicio.
**Pulido final (rev 61)**: bastidor aún más ancho (`holgura_lado` 100, larg_inner_y 450) por pedido del usuario
("los ejes están muy cerca"); **largueros sin agujeros salvo UNO** para el eje motriz (Ø38 en el larguero +Y;
borrado el agujero -Y `c91`, anuladas las ranuras de cola `c92`/`c94` moviendo el tool de corte fuera del sólido
— el boolean cut tolera tool no-intersectante y devuelve el target); soporte corrido adentro (`voladizo` 65) para
que el alma TOPE la cara interior del larguero sin solaparse (fin de la "colisión" soporte↔larguero).
**(rev 62)** ménsulas de rodillos de retorno (`c339-342`) y repisas de mesa (`c367/368`) hechas paramétricas
(`depth`/`y` atadas a `larg_inner_y`) para que sigan al bastidor y lleguen al larguero al ensanchar.
**Lección operativa**: para anular un corte booleano obsoleto sin romper el id del sólido final (referenciado por
juntas/fasteners), mover el TOOL fuera del sólido (el `boolean_op` cut tolera tool no-intersectante y devuelve el
target) en vez de borrar el comando.
**(rev 63) alma SÓLIDA**: el usuario no quería agujero en el soporte donde el eje lo alcanzaba. Ahora el **eje se
queda corto del alma** (`_EJE_GAP`=16 mm), el **perno se corrió hacia adentro** (`_PERNO_OFF`=28, ya no en la punta
del eje) y las **aletas son más largas** (`_AL`=45, van del alma hacia adentro) → el perno captura el eje ENTRE las
aletas y el **alma queda sólida** (sin agujero de paso del eje). `voladizo` mín pasó a `_AL` (default 50). El eje ya
no solapa el soporte (verificado en la faja). Holgura del bastidor a 100 (rodillos con más aire).
**🔩 Perno tensor ALLEN + cinemática del tensado (2026-06-27).** (1) **Allen**: el perno tensor pasó de hex DIN 933
a **Allen DIN 912** (cabeza cilíndrica con hexágono interior, se gira con llave Allen). NEW builder
`builders.py::socket_cap(d)` (cabeza Ø1.5d, alto≈d, hueco hex AF≈0.85d; deriva todo de d) + en BUILDERS; la familia
`108_pernos.yaml` (refs `PERNO-Mxx`) pasó a `builder: socket_cap`/`param_keys:[d]`/norma DIN 912; `take_up.py`
arma el perno con `socket_cap(bolt_d)(L)` (nombre "Perno tensor Allen"). (2) **Cinemática del tensor de cola** (en
la faja id 38): junta **`prismatica`** `j_tensor_cola` (parent larguero `c93`, child `c412_eje`, eje −X = hacia la
aleta del lado de la cabeza, 0–12 mm) + 5 **`fija`** (`c412_rodillo`/`rod1`/`rod2`/`seeger1`/`seeger2`→`c412_eje`)
para que rodillo y rodamientos SIGAN al eje (el hijo arrastra lo unido a él). Driblar 0→12 emula apretar el perno:
eje+rodillo se atraen a la aleta de la cabeza (verificado con `render_view(joint_values=...)`). Se hizo en el
rodillo de COLA (tensor real); el motriz va fijo al reductor. 528 tests. **Reiniciar API+host MCP** por el builder nuevo.

**🏁 Faja de banda — super-comando `create_belt_conveyor` + catálogo (2026-06-15).** Tras proponer la BOM
de una faja de banda (4 m · 600 mm · 1–15 kg; motorreductor eje hueco 2 HP, cama de acero, SIN chumaceras,
tensión tipo trotadora) se cerró la brecha de catálogo y se añadió el super-comando. **Catálogo 57→69**:
2 builders geométricos nuevos en `library/builders.py` — `rect_tube` (tubo estructural rectangular HUECO de
acero; pareja de `profile`/aluminio; geometría en `kernel/shapes.py::make_rect_tube`) y `take_up` (tensor
tipo trotadora: bloque deslizante con alojamiento de eje + perno) — y 5 categorías/familias YAML nuevas:
`tubos_estructurales` (TUBO-4X2/3X2/2X2), `tensores_trotadora` (TENSOR-TROT-20/25), `variadores`
(VFD-1K5-220), `tableros` (TABLERO-5040), `mandos` (ESTOP-40/BOTONERA-2); + variantes `TAMBOR-102` /
`TAMBOR-102-COLA` (Ø101.6 motriz engomado / cola eje fijo) y `MOTOR-150-EH` (eje hueco, ~188 rpm). El
super-comando vive en `library/belt_conveyor.py` (`belt_conveyor_parts`, espejo de `conveyor.py` pero para
BANDA: 2 tambores de extremo + banda envolvente "racetrack" hueca + cama de deslizamiento + bastidor de tubo
4×2 + patas/pies/travesaños + tensor trotadora + motor eje hueco + guardas), `CreateBeltConveyorParams`
(enums dinámicos por categoría) y `_exec_create_belt_conveyor` (reusa `_emit_weldment_parts`). **OJO:
`create_conveyor` es de RODILLOS; `create_belt_conveyor` es de BANDA** (no confundir). Mejora transversal de
BOM (`library/bom.py`): las piezas a medida agrupan por `(command_id, nombre)` — antes solo por
`command_id`, lo que colapsaba banda+cama de un super-comando en una sola fila. 322 tests
(`tests/test_belt_conveyor.py`). Verificado e2e por MCP (proyecto "faja-banda-supercomando": 21 piezas, 0
interferencias, render OK, BOM con las piezas nuevas). **Rodillo de cola perfeccionado (2026-06-16, mecánica precisa confirmada con foto del usuario)**: el
tensado tipo trotadora es **eje fijo Ø25 que SOBRESALE del bastidor (`stub:90`) + soporte en «C» + tornillo
M16 VERTICAL que PASA por un agujero transversal del eje** (no empuja: pasa y, al girar, tensa); uno por
lado. `take_up` rehecho a soporte en «C» (dos alas + alma) con perno M16 vertical (`param_keys`
shaft_d/bolt_d/arm/plate_t/width); `TAMBOR-102-COLA` gana `shaft_hole_d:16.5`/`hole_inset:22` → el builder
`drum` perfora un agujero transversal en cada extremo del eje (perpendicular, alineado con el M16 del tensor
vía `hole_inset_mm` en specs). El super-comando coloca los 2 tensores en el extremo del eje (mirror por lado)
y ya NO usa placas ranuradas. 21 piezas. (Iteración previa de empuje horizontal descartada.) Limitación honesta:
sin `set_visibility` por MCP no se aísla la cola para un primer plano; se ve mejor con zoom en la UI.
**Follow-ups**: acople motor↔eje en la cabeza (el eje motriz aún no sobresale a juego con el eje hueco);
`engineering_check` no detecta esta faja (`detect_conveyor` busca categoría `perfiles`, no
`tubos_estructurales`); editar la faja desde Propiedades; longitud desarrollada de la banda en BOM; builder
realista de hongo para ESTOP (hoy es caja); flats anti-giro en el eje de cola.

**🏁 Catálogo desde NORMAS (2026-06-15).** Poblado con dimensiones de norma reales (generadas + verificadas
por workflow con WebSearch). **Catálogo 69→148 refs.** 4 builders geométricos nuevos en `library/builders.py`:
`round_tube` (tubo redondo hueco), `angle` (ángulo L de lados iguales), `channel` (canal U/UPN prismático),
`i_beam` (viga I/IPE prismático). Familias YAML: `70_rodamientos.yaml` ampliado a **ISO 15 completo** (series
6000/6200/6300/6400, 41 refs); `15_tubos_estructurales.yaml` ampliado a **ASTM A500** HSS cuadrado/rect (16
refs, medida nominal en pulgadas→mm, pared comercial por sección); `12_tubos_circulares.yaml` NUEVO (round HSS
A500, 10 refs); `13_perfiles_abiertos.yaml` NUEVO (1 archivo con 3 familias/3 builders: 8 ángulos L EN 10056,
7 UPN DIN 1026, 7 IPE EN 10365 = 22 refs). El peso lo calcula `weight_formula` desde el ÁREA de la sección
(acero 7.85e-6 kg/mm³) → solo se codifican las COTAS de norma. Categorías nuevas: `tubos_circulares`,
`perfiles_abiertos`. 328 tests (`tests/test_catalog_normas.py`). **Caveats honestos**: perfiles abiertos
prismáticos (sin radios de acuerdo → peso ~3-5% bajo; UPN sin conicidad de ala); HSS lleva UN espesor
representativo por medida (no toda la gama de calibres); paredes de tubo redondo típicas (verificar con
proveedor/grado). **Licencia**: las cotas de norma son hechos (libres en YAML); BOLTS / FreeCAD-library
(LGPL/GPL) solo como referencia, no se copió código. **OJO**: al ampliar `tubos_estructurales`, `TUBO-4X2`
pasó de pared 3.0 a 4.8 mm (3/16" A500) → la faja de banda regenera con larguero algo más pesado.

**🏁 Catálogo de CARPINTERÍA / herraje (2026-06-17).** Cuña oportunista (no cambia el vertical de
transportadores; reusa el catálogo data-driven). **Catálogo 148→169 refs.** 7 builders nuevos en
`library/builders.py`: `butt_hinge` (bisagra de pala/libro: 2 palas + nudillo segmentado + pasador +
agujeros), `piano_hinge` (continua, cortable, kg/m), `euro_hinge` (cazoleta Ø35 de mueble), `pull_handle`
(tirador de barra), `knob` (pomo por revolución), `wood_screw` (tirafondo avellanado por revolución),
`drawer_slide` (corredera telescópica, cortable). 4 categorías/archivos YAML nuevos: `100_bisagras`
(BIS pala 50/63/75/100, BIS-PIANO 32/40, BIS-EURO 26/35 = 8), `101_tiradores` (TIR 96/128/160/192 +
POMO 25/30/35 = 7), `102_correderas` (CORR-12/17), `103_tornilleria_madera` (TIRAFONDO ×4). PBR:
`materials.ts` gana `acero inoxidable`/`latón`/`níquel satinado` (y, 2026-06-17, **vidrio translúcido**:
`isGlass(feat)` por `specs.material` o nombre `/vidrio|cristal|glass/` → material `transparent` opacity 0.3,
`depthWrite:false`, sin sombra opaca; aplica a ventana y a centros de hoja glazed). 337 tests
(`tests/test_catalog_carpinteria.py`). El herraje de pliegue de la puerta plegable se puede sustituir por
estas refs. **Retrofit verificado (2026-06-17)**: en `puerta-plegable-bifold` se cambiaron las 20 bisagras
hechas a mano por 10 de catálogo (`BIS-75` en pliegues, `BIS-63` en pivotes), orientadas con barril vertical
(`rotation rx=90` al insertar) y fijadas a su hoja; 0 colisiones de madera, plegado y restricciones de riel
intactos. **Lección**: una bisagra de catálogo es UN solo sólido (ambas palas), así que fijada a una hoja NO
se reparte entre las dos como las medias-bisagras a mano → durante el plegado la pala lejana no sigue al panel
vecino (artefacto a ángulos grandes; el cerrado es perfecto). Para articulación fiel hacen falta medias-bisagras
(split). **Retrofit FIEL (2026-06-17)**: la puerta se rehízo con `BIS-H` split (20 medias-bisagras, A+B por
junta, cada mitad fija a su cuerpo) → en el plegado **las bisagras se doblan** (verificado: en k1 la mitad
A=−66° y B=+56°, abren 122°; madera sin choques). 30 juntas. **OJO operativo**: cada comando regenera toda la
escena, así que cargas grandes por HTTP secuencial (20 inserciones/juntas) **superan el timeout de 180 s** del
cliente aunque el servidor termine — usar timeout largo (≥540 s) y/o lotes pequeños. **Caveat**: los dos
barriles A/B son coaxiales (se ven como uno) pero NO son par de junta → el scan los marca como contacto
hardware (intencional, como rodillo-en-riel); agrupar mitades de una misma bisagra es follow-up.
**Follow-up**: cerraduras/picaportes, bisagras de resorte, imanes/topes; canteado; cut-list/nesting; coste.

**🏁 Uniones de ebanistería (2026-06-17).** Comando `add_joinery` (categoría `modificar`): corta la
geometría de encaje por booleana **EN SITIO** (muta `feat.shape` + `make_unique()`, conserva ids → no rompe
juntas/restricciones). 3 tipos: **espiga_mortaja** (añade la espiga width×height×depth a A por unión + resta la
mortaja con holgura a B → encajan), **dado** (canal/ranura en B), **dowel** (`count` taladros Ø=width a paso
`spacing` en A y B + clavijas insertadas como features nuevas). Params: `position` (centro de junta, mundo) +
`axis` de inserción (±X/Y/Z); la dirección A→B se autodetecta por los centroides. `AddJoineryParams` +
`_exec_add_joinery` (helpers `obox`/`cyl_axis` orientan la caja/cilindro al eje). 343 tests
(`tests/test_joinery.py`): la espiga encaja con holgura (<50 mm³), el dado solo corta B, el dowel añade N
clavijas. **Caveat**: la selección de A/B en la UI es por id (form genérico) — falta un picker de 2 sólidos
como el de mates (follow-up). M-T modela un tenón recto (sin hombros en inglete); no hay cola de milano aún.

**🏁 Herraje pulido (2026-06-17).** Catálogo 169→179. 4 builders nuevos en `library/builders.py`:
`butt_hinge_half` (MEDIA bisagra: una pala + barril, `side`±1; se insertan A+B coaxiales fijas a cada panel →
**articulación fiel**, resuelve el trade-off del retrofit de un solo sólido), `spring_hinge` (bisagra de
resorte/soft-close: caja de resorte central), `mortise_lock` (cerradura de embutir: cuerpo+faceplate+pestillo+
bombín), `magnetic_catch` (cierre magnético: carcasa + 2 imanes). Familias: `BIS-H` (75/100 × A/B = 4) y
`BIS-RES` (75/100) en `100_bisagras`; `104_cerraduras` (CERR-EMB-S/L); `105_imanes_topes` (IMAN-CHICO/GRANDE).
2 categorías nuevas (`cerraduras`, `imanes_topes`). 345 tests. **Lección de geometría**: en un builder, una
pieza TANGENTE (pala al ras del barril) sale `Compound` y una DISJUNTA (placa con hueco) sale `ShapeList` (sin
`.volume`) → siempre **solapar 0.5–1 mm** las piezas de un mismo sólido, o modelar solo la pieza principal.

**🏁 Herraje de puerta corrediza/colgante REAL — Ducasse U-100 / D-100 (2026-06-17).** Catálogo 179→183.
A partir de fichas reales (Promart, leídas por WebFetch) se añadieron 2 builders en `library/builders.py`:
`door_rail` (riel en **U** abierto por abajo, cortable kg/m — `35×35×1.5`, sección ~153 mm²) y `door_carriage`
(corredera colgante de **4 ruedas** + perno; ruedas en la parte ALTA para rodar en el canal). Familias:
`106_rieles_corredera` (RIEL-U100/U80, `rieles_corredera`) y `107_correderas_colgantes` (CORR-D100/D80,
`correderas_colgantes`), con specs reales (capacidad **100 kg**, hoja ≤ 150 cm, espesor puerta ≥ 20 mm, ranura
**9×15 mm**, fijación cada 500 mm). 2 categorías nuevas. 355 tests (`test_door_sliding_hardware`).
**Chequeo de ingeniería** del sistema sobre la puerta id 28: par (2 hojas) = **35.4 kg** (bastidor 7.7 + **vidrio
10** por hoja) << 100 kg; hoja 49 cm << 150 cm; 35 mm ≥ 20 mm → **holgado**. Caveat honesto: el D-100 es sistema
**corredizo** (1 hoja), aquí se usa para el borde de ataque del bifold; el plegado lo dan las bisagras.
**Retrofit en la puerta id 28**: se reemplazó el riel-caja y los 2 carretes ad-hoc por **instancias de
catálogo** (RIEL-U100 cortado a la luz 1970 mm + 2× CORR-D100) y se cortó la **ranura 9×15** en el canto de las
hojas de ataque con `add_joinery` tipo **dado** (en sitio, conserva id). Plegado y restricciones **intactos**,
0 colisiones nuevas, BOM con las refs reales (RIEL-U100 2.36 kg, CORR-D100 ×2).
**Lección de cirugía de modelo (command-log)**: para canjear sub-ensamblajes en un modelo VIVO sin romper
juntas/restricciones/motion, **borra el sub-grafo COMPLETO de comandos** (no solo la feature: un carrete era
`create×2 → boolean_op → transform → add_joint`; faltó el `transform` y el regenerate falló por shape ausente)
con el endpoint nuevo **`POST /api/commands/remove {ids}`** (expone `Document.remove_commands`, atómico con
rollback), y reinserta. Las restricciones de riel anclan por **coordenadas** (línea + punto en la hoja), no por
la feature del carrete → sobreviven al canje. NO uses `boolean_op` para tallar una hoja existente: **consume el
target y reasigna el id** (rompería todas las juntas que la referencian); usa `add_joinery` (muta en sitio).
**OJO**: reiniciar el server (sin `--reload`) es obligatorio para cargar builders/YAML nuevos del catálogo.
**GOTCHA de reinicio (Windows)**: al matar uvicorn puede quedar un **socket LISTENING zombie** atribuido a un
PID que ya no existe (handle heredado por un proceso hijo); `netstat`/`taskkill` no lo sueltan y el rebind da
**WinError 10048**. Solución: matar TODOS los `python.exe` del venv (incluido el hijo que retiene el handle) →
el puerto se libera → arrancar fresco. (Mata también los procesos MCP; el host los relanza, y entretanto se
opera por HTTP.)

**🏁 Puerta plegable — holguras reales a 4 mm (medidas del usuario, 2026-06-17).** El usuario midió su puerta:
**4 mm** de holgura, y la quiere en los TRES sitios — entre hojas, piso (abajo) y top (arriba). Aplicado a la
puerta id 28 con 4 variables + barril fino, **sin tocar correderas/restricciones**:
- **Entre hojas** (`hueco=4`): el gap lo fija la variable `hueco`, y su MÍNIMO es el **Ø del barril** de la
  bisagra split (vive en el hueco; gap ≥ Ø barril, si no el canto interpenetra el nudillo — medido 292 mm³ a
  `hueco=8` con Ø11). Iteración: Ø11→Ø7 (hueco 8) → **Ø7→Ø3** (hueco 4) en `100_bisagras.yaml` (BIS-H 75=Ø3,
  100=Ø4). Barril fino = piano/oculto, normal en plegables de poca luz. Las hojas regeneran con la bisagra
  nueva sin recolocarse (mismas instancias).
- **Piso y top a 4 mm SIN mover el riel/marco/ventana**: el riel/correderas/restricciones se colocaron con z
  FIJO, así que NO se puede bajar `floor_gap` a secas (descuadra). Truco: mantener `riel_bot` (=2016) constante
  ajustando la ALTURA de hoja → `floor_gap=4` + `riel_gap=4` + **`bh=2008`** (= 2016 − 4 − 4). Así la hoja
  crece 8 mm (fondo a 4, top a 2012, 4 mm bajo el riel) y TODO lo de arriba (riel, correderas, restricciones,
  travesaño, ventana, dintel) queda fijo. Las bisagras cuelgan de `=doorZc+bh/2-250 = leaf_top-250` → cascadean
  solas. **Verificado**: 4.0 mm exactos en los 4 gaps, 0 colisión madera/vidrio/nudillo (cerrado y plegado 60°),
  riel/corredera en su sitio (Z sin cambio).
**Lección**: (1) el barril de la bisagra es el tope físico del cierre entre hojas — para menos luz, barril más
fino (o mortajar). (2) Con herraje de z fijo, para cambiar holguras verticales sin descuadrar, mantén constante
el datum del herraje (`riel_bot`) y absorbe el cambio en la dimensión libre (`bh`), no en el offset base. El eje
de pliegue (junta, axis vertical) no depende de Ø barril ni de z → cinemática/keyframes sobreviven.

**🏁 Puerta plegable — plegado total / apilado (2026-06-17).** La puerta `puerta-plegable-bifold` (id 28)
pliega ahora **hasta apilarse casi plana** (θ2 hasta −168°), no solo al V de ~56°. También se quitaron los
carretes 1 y 4 (sobre el pivote de jamba → redundantes con la bisagra; solo quedan los deslizantes 2 y 3).
**Lección reutilizable (mecanismos bifold/top-hung)**: el ángulo del PIVOTE es **no monótono** (sube y baja
al plegar), así que NO sirve de driver — topa a mitad. Maneja el plegado por el **recorrido del carro** (la
posición del borde de ataque sobre el riel, monótona) y resuelve **(θ_pivote, θ_pliegue) numéricamente**
(`scipy.least_squares`, 2 incógnitas / residuo = carro a (x_target, y=0, z_riel), con continuación para seguir
la rama) por fotograma → keyframes del plegado completo. El **barril offset a la cara** (`origin.y=±esp/2`)
permite que las dos hojas se apilen planas SIN interpenetrarse (verificado: 0 mm³ hoja-hoja y hoja-jamba en
todo el recorrido). [Esto es lo que haría nativo un **master-slider "Apertura %"** — follow-up de plataforma.]
**Refinamiento (2026-06-17)**: hojas a **35 mm** (antes 40) y **centro de VIDRIO** (8 mm) en vez de tablero de
madera — el bastidor (4 miembros) se une en `Hoja N` y el vidrio es una feature aparte **fija a la hoja**
(`fix_vidrioN`), no unida (para que sea vidrio, no madera). Re-resuelto el plegado con esa geometría: 0 mm³ de
solape **madera Y vidrio** en todo el recorrido. **Lección**: un panel de material distinto (vidrio en marco de
madera) va como feature separada fija a la hoja, no en la unión; el espesor cuelga de `esp_hoja` y cascadea,
pero los keyframes del plegado (solve 2D) hay que **recalcularlos** porque el offset del barril es `±esp_hoja/2`.

## Pendientes para madurar Apolo (backlog por área — todo por demanda)

> Ritual al retomar uno: "Procede a crear el plan, con el siguiente recomendado" → plan →
> backend+UI+tests+e2e+CLAUDE.md. **Rendimiento / escala ✅ HECHO (2026-06-17)**: lote=1 regenerate
> (atómico) + regenerate incremental + mesh cacheado por shape (ver "Convenciones"); edición en modelo
> pesado 13 s → 0.15 s. Follow-ups de perf: carga inicial (OPEN) en frío, checkpoint por-comando para
> undo-del-último instantáneo, debounce de autosave.

### 🔗 Cinemática / ensamblaje
- **Multi-restricción acoplada / N-GDL**: hoy 1 mate por hijo (árbol) y la restricción de riel es 1-GDL.
  Falta un solver de lazo genérico (un sólido con ≥2 mates simultáneos). `[A1]`
- **Prismático sobre riel como mate de primera clase** (deslizamiento como mate de ensamblaje, no solo la
  restricción cinemática `add_rail_constraint`).
- **Conectores de mate por ancla/arista** (hoy solo cara plana/cilíndrica en `assembly/mates.py::connector_of`).
- **Relabel del campo `value` del mate** (mm para distancia/concéntrico vs GRADOS para ángulo, según el tipo).

### 🧩 Validación de ensamblaje por gravedad / "soundness" (iniciativa nueva 2026-06-26)
> Objetivo del usuario (programador que aprende a construir máquinas): ver en 3D si la máquina está **bien
> armada** — que el eje esté capturado, que un rodillo/guarda/motor **se caiga** si no está sujeto. NO es FEA
> (no mide si el acero se dobla); es **conectividad física** + dinámica de cuerpos rígidos. Plan formal en
> `.claude/plans/validacion-ensamblaje-gravedad.md` (4 fases, aprobado).
- **Fase 0+1 ✅ (2026-06-26) · Conectividad + chequeo estático de soundness.** Cimiento: la sujeción es ahora
  un DATO de primera clase. Comandos nuevos **`ground`** (ancla una pieza al piso) y **`fasten`** (fijador
  rígido A↔B: perno/soldadura/pegado/contacto), categoría `ensamblaje`, event-sourced (undo/replay), flag
  `wants_connectivity` en `CommandSpec` + rama de dispatch; `Document.fasteners`/`grounds` se threadean por el
  regenerate incremental (tupla de estado 5→7 en `_copy_state`/checkpoints; se reconstruyen del log, NO van al
  manifest) con validación de integridad referencial. **OJO de nomenclatura**: `attachments`/`wants_attachments`
  YA significan "ficheros STEP" (import_step) — la conectividad usa `fasten`/`ground`/`connectivity`, no
  "attachment". Análisis PURO en **`assembly/connectivity.py`** (`build_graph` + `soundness_report`: grafo
  no-dirigido de juntas∪mates∪fasteners, semilla = grounds; una pieza "flota" si no tiene camino a tierra;
  `isolated` = sin ninguna unión) — determinista, sin física, el 80% del valor. **`assembly/autodetect.py`**
  (`detect_connections`): propone uniones desde la GEOMETRÍA (anclajes a piso por `min.z≤piso`; contactos por
  solape de AABB) para poblar modelos sin conectividad (como la faja de 92 piezas) — heurística, propone-no-impone.
  Endpoints `POST /api/assembly/soundness` (`with_autodetect` superpone contactos efímeros), `POST /api/assembly/
  autodetect`, `GET /api/connectivity`. Tools MCP **`check_assembly`**, **`autodetect_connections`** (50 tools;
  **el host MCP debe reiniciarse para registrarlas**). Verificado en `faja-paqueteria-4m`: 0 uniones declaradas →
  92/92 flotan; autodetect → 25 anclajes (6 placas+19 pernos)+156 contactos. **Límite honesto**: el grafo de
  contacto es NO-DIRIGIDO → no distingue "el rodillo sostiene la banda" de "la banda sostiene al rodillo" (un
  contacto AABB no sabe quién aguanta a quién), por eso el cierre con autodetect da 0 flotantes; el veredicto fino
  ("el motor/rodillo se cae") lo da declarar las uniones REALES (lo que el tool ya habilita) o la **Fase 2**
  (sim de gravedad con cascos convexos), que resuelve holder-vs-held automáticamente. 490 tests
  (`tests/test_connectivity.py`).
- **Fase 2 ✅ (2026-06-26) · Simulación de gravedad de TODA la máquina (ver qué se cae).** La máquina es el
  sujeto (no un producto que cae): las piezas con sujeción declarada hasta el piso se modelan ESTÁTICAS, el
  resto son cuerpos rígidos DINÁMICOS que caen, con **colisión por CASCO CONVEXO** (no AABB). **`physics/hull.py`**
  (`hull_vertices`: tesela el shape → `scipy.ConvexHull` → vértices para `<mesh>` de MuJoCo, que hace el casco;
  **cacheado con REFERENCIA fuerte al shape**, no solo `id()` — sin la ref el shape se recolecta y Python reusa
  el id → otra pieza recibe el casco equivocado; bug real visto en la suite). **`physics/stability.py`**
  (`stability_test`): grounded (de `connectivity`) → estáticas; resto → `<body><freejoint>` con masa de
  `_link_physics`; corre gravedad, reporta `fell` (desplazamiento del COM > 15 mm) vs `estables` + poses por
  fotograma (formato drop_test → **reusa `anim.render_drop_gif`** con la escena estática de fondo). Params
  `with_autodetect` (usa el contacto geométrico como estructura) y **`exclude`** (trata una pieza como NO sujeta:
  "¿y si le falta el tornillo?"). **Resuelve lo que el chequeo estático no podía**: una pieza no-sujeta que REPOSA
  sobre algo firme NO cae (la física decide holder-vs-held); una que cuelga en el aire, sí. Endpoints
  `POST /api/assembly/stability[.gif]`; tool MCP **`gravity_test`** (51 tools; guarda GIF opcional). Verificado en
  vivo sobre la faja: `exclude` de los 4 rodillos de retorno → caen 682.8 mm al piso (88 estáticas, 4 dinámicas);
  GIF generado. 494 tests (`tests/test_stability.py`). **Límite honesto**: el casco CONVEXO rellena concavidades
  (la banda en lazo se vuelve un bloque sólido; una pieza no-sujeta que penetra una estática al inicio puede
  saltar) — fiel para ejes/rodillos/apoyos, aproximado para cavidades. **El host MCP debe reiniciarse** para
  `check_assembly`/`autodetect_connections`/`gravity_test`.
- **Fase 3 ✅ parcial (2026-06-26) · UI del panel "Montaje".** Panel nuevo `ui/src/panels/AssemblyPanel.tsx`
  (bottomPanel `ensamblaje`, toggle en StatusBar "Montaje", icono `Anchor`): botón **Validar** (soundness →
  lista de piezas flotantes/sueltas, clic resalta en el viewport), **Prueba de gravedad** (stability → lista de
  las que caen con su caída en mm) y **Ver caída** (GIF inline). La **selección** (árbol/viewport) actúa de
  `exclude` ("tratar como sueltas → ¿se caen?"). Toggle "auto-detectar uniones". Solo-frontend: `api.ts`
  (soundness/stability/stabilityGif), `types.ts` (SoundnessOut/StabilityOut/StabilityRequest), registro en
  `BottomDock`/`StatusBar`/`icons`. Build verde (tsc+vite). **Reconstruir la UI (`cd ui; npm run build`) y
  recargar** :8000; no requiere reiniciar API/MCP.
- **Fase 3 · caída ANIMADA en el viewport 3D (2026-06-26)**. Reemplaza el GIF lento (matplotlib re-dibujaba
  ~90 piezas/fotograma) por reproducción instantánea de las **MALLAS REALES** en el viewport. Backend:
  `stability_test` añade `com` a cada product; `POST /api/assembly/stability` gana `include_frames` (devuelve
  `frames` solo si se pide — la lista de validación sigue ligera). Frontend: módulo nuevo `ui/src/viewport/gravity.ts`
  (`createGravityAnimator`: anima `ctx.meshes` reales con `mesh.matrix = P(t)·translation(-com)·baseMatrix`,
  reusa `interpolatePose`; al limpiar/recambiar RESTAURA las mallas vía `userData.p0/q0`) — NO usa cajas overlay
  (sin fantasma). Estado `gravity*` en el store (espejo de `physics*`, efímero, `clearGravity` en open/new/refresh/
  adopt); efecto `[gravityResult, gravityToken]` + tick en el rAF loop de `Viewport.tsx`. Panel "Montaje":
  "Prueba de gravedad" → `api.gravitySim` (`include_frames`) → `resetJointValues()` (gravedad/cinemática
  excluyentes) → `setGravityResult` (anima en 3D); controles ▶/⏸/↻ Repetir/Limpiar; el GIF pasó a "Exportar GIF"
  (opcional, lento). Tipos `GravityProduct`/`GravityResult` (NO reusa `DropResult`: su product exige x/y/z/mass).
  Matemática validada (P(0)=translation(com) ⇒ no salta en t=0). Build verde; backend verificado e2e (frames keyed
  por id, com correcto). Solo-frontend+backend aditivo → `cd ui; npm run build` + recargar; sin reiniciar API/MCP.
- **Fase 3 · UNIONES DECLARADAS + prueba de gravedad EXACTA (modo "SolidWorks") (2026-06-26)**. Para que la
  prueba sea exacta de un clic (sin re-seleccionar sospechosos): se declaran UNA vez las uniones reales y la
  prueba usa solo esas (`with_autodetect=false`). Backend: **`assembly/autodetect.py::detect_structure`** —
  auto-declarado INTELIGENTE por **grafo de soporte DIRIGIDO**: clasifica cada contacto en `soporte` (apilado:
  cima del inferior ≈ base del superior, solape vertical ~nulo) vs `mismo_nivel`/soldadura lateral (co-extensión
  vertical: el miembro bajo cabe en el rango z del otro, sin exigir centros cercanos — clave para travesaños
  soldados al COSTADO de patas altas) vs **colgado/espurio** (toca solo por arriba sin nada debajo → NO se
  declara). Calcula el grounding dirigido (alcanzable hacia arriba desde el piso) y emite `ground`(piso) +
  `fasten` SOLO entre piezas sujetas → lo colgante (rodillos de retorno) queda suelto → la prueba exacta lo
  tira. Endpoints nuevos `POST /api/assembly/declare` (auto-declara en lote vía `execute_batch`, idempotente,
  dedup), `DELETE /api/fasteners/{name}` y `/api/grounds/{name}` (réplica de `delete_mate`). UI (panel Montaje):
  **editor de uniones** (lista grounds+fasteners con ✕; "Auto-declarar estructura"; manual "Anclar al piso"=1
  sel / "Unir piezas"=2 sel) + botones **"Prueba de gravedad EXACTA"** (declaradas) y "aproximada"
  (autodetección). Store: estado `connectivity` + `refreshConnectivity`/`declareStructure`/`deleteFastener`/
  `deleteGround`/`groundSelection`/`fastenSelection`; `api.ts`/`types.ts` (ConnectivityOut/FastenerRow/GroundRow).
  Verificado e2e en la faja id 38: auto-declarar → 25 anclajes + 152 fijadores, 0 rodillos declarados → prueba
  EXACTA tira **solo los 4 rodillos** (682.8mm). **Límite honesto**: la clasificación es heurística (AABB); para
  casos límite (cruces de bbox sin tocarse, mismo-nivel ambiguo) está el editor (borrar/añadir uniones). 498 tests
  (`test_autodetect_structure.py`, `test_api.py::test_assembly_declare_and_delete`). **Tools MCP nuevas (51→54)**:
  `declare_structure` (auto-declara inteligente), `get_connections` (lista uniones declaradas), `delete_connection`
  (borra una por nombre) → flujo completo por chat: `declare_structure()` + `gravity_test(with_autodetect=False)`.
  El resto ya era usable por el diseño thin (`run_command` crea ground/fasten). **El host MCP debe reiniciarse**
  para registrar las 3 tools. **Queda**: cinemática (banda corriendo). Aditivo → `cd ui; npm run build` + recargar.

### ✅ Validación / motor
- **Agrupar las dos mitades A/B de cada bisagra** (barriles coaxiales) para que el scan no las marque como
  contacto (hoy intencional pero ruidoso, como rodillo-en-riel).
- **`engineering_check` no detecta la faja de banda**: `rules.py::detect_conveyor` busca categoría `perfiles`,
  no `tubos_estructurales` (el bastidor real de la faja).
- **Ampliar análisis**: deflexión de viga del bastidor, voladizo de tambores. `[V1]`

### 🖥️ UI / deuda técnica
- **Refactor de `Viewport.tsx` (U1)**: extraer picking/box-select/medición/sección/cinemática/gizmo a
  módulos (ya se extrajeron render PBR, física, shell, atajos/hover/menú). Mandato de escala. `[B7]`
- **Picker de 2 sólidos para `add_joinery`** (hoy por id en el form genérico; como el picker de mates).
- **Master-slider "Apertura %"** para manejar un mecanismo entero con un control (resuelve el lazo).
- **Editar sweep/loft/chapa/mate/restricción desde Propiedades** (G4 — hoy se re-crean).
- **Auditar el resto de docks** (BOM/Validaciones/Física/Ensamblaje) por el bug de contención de layout.

### 🧱 Geometría / catálogo
- **Ebanistería**: cola de milano, hombros en inglete (M-T hoy es tenón recto).
- **Herraje — detalle real**: rosca en tirafondos, mecanismo de 4 barras en la cazoleta europea, balines en correderas.
- **Canteado** (edge-banding) + **cut-list/nesting** + **coste/pies-tabla**.
- **Chapa (G2)**: cutouts rectangulares, taladros en pestañas, K-factor por material, radiado robusto.
- **Weldments (G3)**: ingletes a inglete reales, cordones realistas, editor de esqueleto, unificar
  `create_weldment` sobre `frame_from_edges`.

### 🌍 Física (follow-ups F1)
- **Cascos convexos de colisión** (hoy AABB → una mesa en U se vuelve caja maciza; el producto reposa en
  z≈850 en vez de sobre la cara real de la banda z=752). El límite honesto más visible del drop-test.
- **Inercia/densidad reales del CAD** (ya existe `robotics/model.py::_link_physics`; hoy F1 usa densidad fija ~600 kg/m³).
- **Export SDF de escena SIN juntas** (hoy `urdf/sdf` exige juntas) → simular en Gazebo/PyBullet/MuJoCo externos.
- **Inmediato (no-código)**: confirmar a mano la reproducción del drop-test F1·A (`:8000` → panel **Física** →
  **Soltar**); la verificación automatizada quedó bloqueada por el entorno.

### 🚪 Pendientes del modelo puerta plegable (`puerta-plegable-bifold`, id 28)
- **Hojas a "5 tablas" + bisagras en travesaños** ✅ (2026-06-24): a pedido del usuario, cada hoja pasó del marco
  lapeado de 2 capas a **5 tablas**: 2 largueros (lados, traseros, 18 mm, altura completa) + 3 travesaños
  (arriba/medio/abajo, delanteros, 18 mm, ancho completo) **traslapados** sobre los largueros → en los cantos hay
  **36 mm** (larguero atrás + travesaño delante). **Las 3 bisagras por unión van EN esos travesaños** (36 mm), así
  al plegar no chocan (verificado: `avisos_pose: []` a 41°/−87° y 49°/−106°). **Un solo vidrio por hoja DETRÁS**
  de las 5 tablas (y[−18,−10], en el fondo). Cirugía (command-log, root c85/c87/c89/c91 intacto): el root de la hoja
  pasó a unión de **solo los 2 largueros** (compound de 2 cajas disjuntas — OCCT lo acepta); los back-rails-sup
  (c40/c47/c54/c61) se **repurposaron como travesaño medio** (fijo a la hoja, junta nueva `fix_tmedN`); los back-rails-inf
  y los largueros-delanteros viejos (12 cajas: c41/c48/c55/c62 + c353‑c360) se **ocultaron** (`set_visibility`,
  cruft a limpiar); el vidrio (c42/c49/c56/c63) se reubicó atrás; los travesaños sup/inf (c337/c338…) ya estaban en
  el tope/base, solo se renombraron. **Bisagras movidas** a las alturas de los travesaños cambiando el z de su
  `insert_component`: top `doorZc+bh/2−250 → −lm/2` (1762→1962), bottom `+250 → +lm/2` (254→54); las del medio
  (1008) ya coincidían. Se añadió la **3.ª bisagra a los pivotes de jamba** (c373‑c376, antes tenían 2). Revisión 28
  (antes) / 29 (después). 86 sólidos. Lección: editar `position` por MCP la REEMPLAZA entera → hay que reenviar x,y;
  y la unión de 2 sólidos disjuntos da un compound válido (sirve de root cinemático). Pendiente de limpieza: borrar
  las 12 cajas ocultas (mejor con `POST /api/commands/remove` que oculto), y bajar el travesaño sup unos cm si se
  quiere despegado del tope.
- **Hojas "tablas traslapadas" + vidrio único** ✅ (2026-06-24): las 4 hojas eran DESIGUALES (1‑2 con peinazos de
  ancho completo finos al fondo, 53 mm; 3‑4 con peinazos cortos de espesor completo, 36 mm) y cada una llevaba DOS
  vidrios partidos por un peinazo central. Rediseñadas idénticas según el prototipo del usuario `armado-hoja-tablas`
  (id 35): marco de **dos capas traslapadas** (atrás: 2 largueros enteros + 2 peinazos cortos; delante: 2 peinazos
  enteros + 2 largueros cortos → las uniones de cada capa montan sobre la otra) + **un solo vidrio central** (296×1806×8).
  Capas a `esp_hoja/2`=18 (atrás `y=-esp_hoja/4`, delante `y=+esp_hoja/4`); hoja total 36 mm sin tocar holguras/mecanismo.
  Plegado y restricciones intactos (`avisos_pose: []`). **Lección command-log**: para añadir miembros a una hoja que es
  RAÍZ de junta (c85/c87/c89/c91), la **capa trasera** se mete en la unión existente (editando sus cajas) y la **capa
  delantera** se cuelga con junta **`fija`** a la hoja — NO se mete en la unión (ésta no puede referenciar cajas creadas
  después en el log). Se reaprovecharon el "vidrio sup" y el "peinazo central" como peinazos delanteros (renombrados →
  dejan de ser vidrio en PBR). Revisión 26 (antes) / 27 (después). 74 sólidos. Contactos de herraje residuales
  (intencionales): trolley↔peinazo del sup ~15 cm³ (montaje), bisagra↔larguero del ~3.1 cm³ (mortaja).
- **Riel + carretes = herraje REAL** ✅ (2026-06-17): RIEL-U100 + 2× CORR-D100 de catálogo + ranura 9×15 (ver arriba).
- **Planos de fabricación del marco** ✅ (2026-06-18) — paquete completo para maderera en `planos/`:
  `marco-fabricacion.md` (hoja de corte + ubicación de uniones desde datum + notas), `lista-de-corte.csv`,
  `piezas/P1–P4.{pdf,dxf}` (plano POR PIEZA con espigas en línea continua + mortajas en oculto, `hidden=true` aislado),
  `marco-conjunto-globos.pdf` (alzado + 7 globos). Técnica de aislado: `set_visibility` (solo flag `hidden`, no ensucia
  el log) → `/api/drawing.*?dims=<ids>` → restaurar. **Fix**: el BOM del plano (`drawing/sheet.py`) ahora respeta la
  visibilidad (`bom_scene = visibles si no include_hidden`) → el despiece y los globos del plano = lo dibujado.
  `project_views` ya filtra por visible vía `_scene_compound`; `include_hidden` solo añade LÍNEAS ocultas (útil para
  ver mortajas en el plano por pieza). **Carpintería de unión** ✅: 10 espigas-mortajas (`add_joinery espiga_mortaja`):
  4 esquinas (riel 70×70→poste, espiga 23×43×45) + 6 parteluces (montante 50×42→riel, espiga 17×16×30), holgura 0.3/cara,
  encaje 0 overlap verificado; cotas diseñadas por workflow (3 carpinteros + juez) y validadas por workflow adversarial
  (geometría correcta; el gap era datos de PROCESO: posición de mortajas desde datum, mano izq/der, refuerzo de parteluz
  con clavija — todo en `marco-fabricacion.md`). **Comando nuevo `add_joinery` tipo `rebaje`** (corte de caja EN SITIO en
  B, conserva id — NO usar `boolean_op` que reasigna id y rompe juntas): para galces de vidrio. El galce de la ventana
  (rebaje 10×9 + junquillo 12×10, ~6.1 m) está **especificado y acotado** pero aún NO cortado en el 3D (cambio coordinado
  grande: 10 rebajes + redimensionar 4 vidrios + 16 junquillos). Pendiente: planos de hojas/herraje, **exportar STEP**.
  **Variante ATORNILLADA (2026-06-18, a pedido del usuario — la espiga-mortaja era cara de tratar a mano)**: se
  quitaron las 10 espigas (vuelve a junta a tope, largos 2010/309) y se modelaron **14 tornillos** con
  `add_joinery dowel` (8 esquina Ø6×100 + 6 parteluz Ø4.5×90). **Truco clave**: `dowel` perfora el taladro EN SITIO
  en A y B (conserva ids — los postes c33/c34 son raíces de las juntas de pivote de la puerta, no se pueden
  reasignar) e inserta un pin = el tornillo. Verificado: 0 colisión (tornillo en su taladro), la puerta SIGUE
  plegando (roots c33/c34 intactos). Los taladros se ven en el plano por pieza (`hidden=true`). Lección: para
  añadir tornillos/taladros a piezas que son raíz de junta, usa `dowel`/`rebaje` (en sitio), NUNCA `boolean_op`.
- **Herraje de cierre**: falta colocar tirador/cerradura/imán (ya en catálogo) en el borde de ataque.
- **Cotas confirmadas por el usuario**: holguras **4 mm** (entre hojas/piso/top), hoja **35 mm** + vidrio 8 mm,
  y **marco 7×7 cm en TODO**: `prof`/`jamba`=70 (jambas+dintel) **+ `beam_h`=70** (travesaño), bajado de 120/90/90
  — la madera tornillo gruesa es dura de tratar. Al adelgazar `jamba` la luz subió 1970→2010 y las hojas/riel
  cascadearon; al bajar `beam_h` la ventana creció ~20 mm. 0 colisiones. **OJO al adelgazar el marco**: el
  travesaño usa DOS variables (`prof`=fondo, `beam_h`=alto) — cambiar solo `prof` deja el alto en 9 cm.
- **Acabado**: madera sin veta; **vidrio ya translúcido en viewport** (opacity 0.3) — para fotorrealismo (transmisión/refracción real) → render externo (Blender).
- **Limpieza**: proyectos basura `id 26/27` (puerta vieja) y `perf-test-batch` — borrar desde la UI.

---

## Orden recomendado de ataque (V3, histórico)

1. Catálogo de partes estándar ampliado (realismo+utilidad, bajo riesgo).
2. Mates/juntas persistentes (robustez paramétrica de ensamblajes).
3. Viewport PBR (percepción — el cambio más visible).
4. Sweep + weldments (bandas reales y bastidores soldados).
5. Motion study con física embebida (ver moverse + caer producto, todo de una).

## Gravedad / física — "no nativo" NO es peor

La dinámica de cuerpos rígidos (gravedad, producto cayendo) es SIEMPRE un motor aparte,
también en Fusion (la geometría OCCT y la física son matemáticas distintas). Dos vías,
ninguna rompe nada:
- **Acoplamiento débil**: ya exportamos URDF/SDF → simular en PyBullet/Gazebo/MuJoCo.
  Funciona hoy (limitación: `export sdf/urdf` exige juntas → escena estática sin juntas aún no
  exporta; follow-up F1).
- **Acoplamiento fuerte**: embebido en F1 ✅ vía **MuJoCo** (no PyBullet: sin wheel para Py3.13).
  Headless por ahora (drop-test → GIF + reposo); transmitir poses al viewport en tiempo real
  (`applyKinematicPoses`) es el siguiente paso → se sentirá nativo.
Gotchas reales (confirmados en F1): geometría de colisión = **AABB hoy** (no B-rep ni casco convexo;
por eso una mesa en U se vuelve maciza), masa/inercia se calculan del CAD con OCCT (`_link_physics`,
aún sin cablear: F1 usa densidad fija ~600 kg/m³ para el producto), tuning del solver, modelo mental
distinto. Viable y estándar.

## "Resistencia" (FEA) — aplazado por decisión del usuario

- **Analítico** (deflexión de viga, par, capacidad): barato; ampliar `engineering_check`
  cubre ~80 % de las decisiones reales por ~5 % del coste.
- **FEA visual grado Fusion** (mapa de tensiones): mallado + solver FE; módulo mayor. Es
  la frontera real. No abordar hasta que el negocio lo pida.

## Catálogo de librerías candidatas (con licencia)

Aviso comercial: GPL contamina código cerrado al enlazar. Preferir permisivas
(MIT/BSD/Apache/zlib) o LGPL (ok con enlace dinámico). Blender/CalculiX/etc. GPL se usan
como **proceso externo** para evitar contaminación. Verificar licencia vigente al adoptar.

- **Kernels/CAD**: OpenCASCADE/OCCT (LGPL, en uso), build123d/CadQuery (Apache),
  Manifold (Apache — booleanas de malla rápidas), CGAL (GPL/comercial), OpenVDB (MPL).
- **Malla**: trimesh (MIT), Open3D (MIT), libigl (MPL2), meshio (MIT), gmsh (GPL).
- **Física/dinámica**: PyBullet/Bullet (zlib — opción por defecto), MuJoCo (Apache),
  Project Chrono (BSD — multicuerpo + flujo GRANULAR, ideal para manejo de materiales),
  Drake (BSD), ODE (BSD).
- **Cinemática/robótica**: Pinocchio (BSD), ikpy (verificar), KDL/Orocos (LGPL),
  Ruckig (MIT — trayectorias).
- **Solvers de restricciones**: scipy (BSD, en uso), PlaneGCS de FreeCAD (LGPL —
  candidato a reemplazar el solver propio por robustez), libslvs/SolveSpace (GPL),
  NLopt (LGPL), SymPy (BSD).
- **FEA (futuro)**: CalculiX (GPL), code_aster (GPL), FEniCS/DOLFINx (LGPL),
  sfepy (BSD), GetFEM (LGPL).
- **Render/viz**: three.js (MIT, en uso), Filament/Google (Apache — candidato a viewport
  PBR), Babylon.js (Apache), VTK/PyVista (BSD/MIT — resultados FEA), Blender/bpy (GPL,
  como proceso externo para fotorrealista).
- **Formatos/interop**: OCCT data exchange (STEP/IGES, en uso), assimp (BSD),
  ifcopenshell (LGPL), pygltflib (MIT).
- **Ingeniería**: pint (BSD — unidades), NumPy/SciPy (en uso), FreeCAD Fasteners/Gears
  workbench (GPL — referencia de fórmulas de tornillería/engranajes).

## Fuera de alcance deliberado

CAM, FEA real grado Fusion (aplazado), PCB/electrónica, nube multiusuario, diseño
generativo topológico. Backlog opcional bajo demanda: empaquetado Tauri, plantillas AGV.
