# Devlog histórico de Genix Apolo CAD

> Copia ÍNTEGRA del CLAUDE.md al 2026-07-01, antes de su poda (~62k tokens → ~20k).
> Aquí vive la NARRATIVA completa de cada feature (qué se hizo, cómo se verificó,
> cirugías de modelos paso a paso). El CLAUDE.md vigente conserva instrucciones,
> convenciones y gotchas; la historia nueva se registra en git log y, si amerita
> narrativa larga, se APPENDEA aquí.

# Genix Apolo CAD

CAD paramétrico 3D para maquinaria industrial/robótica cuyo **diferenciador es el
diseño asistido por IA** (agente-nativo, también manual). Vertical del MVP:
transportadores / manejo de materiales. Stack: **Python (build123d/OCCT) + FastAPI +
React/three.js**.

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
- **Criterio de ingeniería por defecto (NO solo ejecutar al pie de la letra)**: el agente
  diseña como un ingeniero/estructurista (el usuario es el CLIENTE) y asume lo obvio —que la
  pieza se sujete, que se pueda montar/desmontar con pernos, que la forma sirva a su función
  (una guarda envolvente, no una caja recta)— sin esperar a que se lo pidan. Vale para CUALQUIER
  objeto (máquina, mueble, estructura). Fuente ÚNICA en `core/apolo/design/guidelines.py`
  (`design_brief()` resumen + `design_guidelines()` decálogo completo): se inyecta SIEMPRE en las
  instrucciones del MCP y en el `SYSTEM_PROMPT` del chat (capa 1), y el detalle/ejemplos se
  consultan bajo demanda con el tool MCP `get_design_guidelines` / `GET /api/design-guidelines`
  (capa 2). Cada regla mapea a CÓMO verificarla en Apolo (gravity_test/check_interference/
  cut_list/render_view) → el principio rector es: un 3D solo vale si es FABRICABLE y se SOSTIENE
  en el mundo real. (2026-06-30; tool MCP 54→55; `tests/test_design_guidelines.py`.)

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
  no cubre aún multivista ni etiquetas (siguen en matplotlib con la malla fina).
  **(2026-06-29) CÁMARA DE ÁNGULO LIBRE en `render_view` (`azimuth`/`elevation`)**: los 4 presets
  (iso/frente/lateral/planta) no bastan para inspeccionar una cara/detalle en ángulo arbitrario (p. ej. el
  `iso` mira casi a lo largo del eje de un rodillo → inútil). Ahora `render_view`/`/api/render.png` aceptan
  `azimuth`/`elevation` (GRADOS, convención de `view_init` de matplotlib) que **anulan** el ángulo del preset
  `view` (override PARCIAL: dar solo uno conserva el otro). Implementación de bajo coste porque AMBOS motores
  ya piensan en `(elev, azim)`: NEW `render.py::resolve_angles(view, azimuth, elevation)` = fuente única que
  parte de `VIEW_ANGLES[view]` y sustituye lo que se pase; la usan `apply_camera` (matplotlib) y
  `render_scene_vtk` (VTK) → MISMO punto de vista en las dos vías. Threaded por `render_scene_png`/`_draw_view`,
  `/api/render.png` (query `azimuth`/`elevation`) y el tool MCP `render_view`. Aplica a **vista única**; en
  **multivista** (`views`) se ignora. **`pick` NO cambia** (los params son opcionales; al no pasarlos, usa el
  preset → coherencia render↔pick intacta).
  **(2026-06-29) `render_view` es VTK PURO** (decisión del usuario: que la captura limpia se encargue de TODO,
  sin generar la imagen matplotlib con cuadrícula). El tool MCP `render_view` **perdió** `views`/`labels`/
  `shaded`/`proportional` (cosas exclusivas de matplotlib o que VTK ignora) y ahora SIEMPRE envía `shade=true`
  + el flag nuevo **`vtk_only=true`** del endpoint: exige VTK, ignora multivista/etiquetas y **no cae a
  matplotlib** (sin OpenGL → **503 claro**, nunca una imagen con rejilla). El endpoint `/api/render.png`
  CONSERVA matplotlib para el resto (fallback normal cuando `vtk_only` no se pide, multivista/labels por HTTP,
  y la plomería interna que NO pasa por el endpoint: `pick` píxel→3D, GIFs de física en `physics/anim.py`, la
  iso sombreada embebida en planos). O sea: matplotlib no se borró (es load-bearing) — solo se le cerró la
  puerta al tool MCP. Combínalo con `isolate`/`fit_ids`/`zoom` para fotografiar una pieza de cerca desde
  cualquier ángulo. Verificado: 526 tests (`resolve_angles` unit, VTK ≠ preset, multivista ignora az/el,
  endpoint `vtk_only` 200/503) + e2e por HTTP sobre la faja (rodillo a `azimuth=-72/elevation=18` oblicuo
  imposible con preset; `vtk_only=true` da VTK limpio y la multivista por HTTP sigue saliendo en matplotlib).
  **Límite/follow-up**: [RESUELTO 2026-06-29 → roll/pan añadidos y labels portados a VTK; ver nota de "CÁMARA
  MÁS LIBRE" abajo. Queda solo la MULTIVISTA en matplotlib, follow-up deliberado.]
  **(2026-06-29) `pick_point` a ÁNGULO LIBRE** (cierra el lazo ver→identificar→editar): `pick_point`
  (`kernel/pick.py`, píxel→pieza/cara por snap al candidato más cercano) ahora acepta `azimuth`/`elevation`
  y, sobre todo, **proyecta como el render VTK** — antes usaba matplotlib en PERSPECTIVA + caja CÚBICA
  (descuadraba el píxel vs lo que se ve). Fix: `ax.set_proj_type("ortho")` + `proportional=True` (proporciones
  reales como VTK) + `figsize` con el aspecto de la ventana VTK (0.78) + reenvío de `azimuth`/`elevation` a
  `apply_camera`/`resolve_angles`. Reusa la maquinaria de matplotlib (handedness ya probada por los tests) →
  bajo riesgo. Plumbing: `/api/pick` y el tool MCP `pick_point` ganan `azimuth`/`elevation` y **pierden
  `proportional`** (ahora siempre real, coherente con `render_view`). Uso: pasa al pick los MISMOS
  `view`/`azimuth`/`elevation`/`fit_ids`/`zoom` del `render_view`. Verificado e2e por HTTP sobre la faja a
  `azimuth=-120/elevation=20` (no-preset): pick(0.5,0.5) con fit en el motor → `c134` (guarda que lo envuelve,
  la pieza al frente); pick en la zona de la banda → `c354` (mesa) → discrimina por posición y coincide con
  la imagen. **Límite honesto**: consistencia APROXIMADA (matplotlib-orto vs VTK difieren en el margen de
  encuadre/escala) — fiable para IDENTIFICAR la pieza/cara, no sub-píxel; exactitud total = follow-up con la
  matriz de cámara VTK. `pick` aún no honra `isolate`/`section` (proyecta toda la escena; pasa los mismos
  `fit_ids`). Sin OpenGL el render cae a matplotlib (persp+cubo) y el pick orto no casaría con esa imagen
  degradada (borde raro). 528 tests (`test_pick.py`: separación a ángulo libre + dict válido).
  **Reiniciar API + host MCP** (el host re-registra `render_view`/`pick_point` con la firma nueva — `render_view`
  sin `views`/`labels`/`shaded`/`proportional` y `pick_point` sin `proportional`, ambos con `azimuth`/`elevation`;
  la API en `--reload` ya sirve `azimuth`/`elevation`/`vtk_only`).
  **(2026-06-29) MEDIR DESDE LA IMAGEN — cota sobre el render VTK** (cierra el "ver→medir"; el agente ya no
  infiere dimensiones de bboxes): `render_view(measure=[idA, idB])` dibuja una COTA — línea + etiqueta "X mm"
  del **gap mínimo OCCT** entre dos piezas — ENCIMA del render. Reusa `measure_distance` (que ya devuelve
  `dist_mm`+`punto_a`/`punto_b`), sin geometría nueva. NEW `render_vtk.py::_dimension_actors(p1,p2,label,scale)`
  (línea `vtkLineSource` + esferas en extremos + etiqueta `vtkBillboardTextActor3D` que siempre mira a la
  cámara con fondo blanco para legibilidad). `render_scene_vtk(..., dimension={"p1","p2","label"})` la pinta en
  una **2.ª capa de renderer** (`SetNumberOfLayers(2)`, `overlay.SetActiveCamera(cam)` comparte vista,
  `PreserveColorBufferOn`+`PreserveDepthBufferOff`) → la cota se ve SIEMPRE encima, sin ocluirse, a cualquier
  ángulo. El endpoint `/api/render.png` gana `measure="a,b"`: calcula `measure_distance` sobre las shapes
  RENDERIZADAS (override si hay pose `joints`) y pasa la `dimension`; id inexistente → 404; **solo vía VTK**
  (multivista/matplotlib lo ignoran). Tool MCP `render_view(measure=[idA,idB])`. Pillow NO se usó (es opcional);
  todo VTK-nativo. Verificado e2e por HTTP sobre la faja: `measure=c412_rodillo,c413_rodillo` → cota "3692 mm"
  a lo largo de la banda, encima de la geometría, valor == `/api/measure`. 530 tests (`test_render_vtk.py`
  dimensión, `test_api.py` measure 200 + 404). **Límite/follow-up**: v1 = gap entre DOS piezas enteras; medir
  contra una CARA (`face_a/face_b`, ya en `/api/measure`), centro-a-centro, cotas L×A×H de una pieza, y barra de
  escala global = follow-ups. **Reiniciar host MCP** para `render_view` con `measure`.
  **(2026-06-29) BORDES NÍTIDOS + PICK EXACTO** (2 follow-ups del motor VTK). **(a) Aristas de feature**:
  NEW `render_vtk.py::_edges_actor(vertices, triangles)` (`vtkFeatureEdges`, ángulo 35° = creases+borde,
  color casi negro, `SetResolveCoincidentTopologyToPolygonOffset` anti z-fighting). En el loop de mallas, por
  pieza visible/resaltada, se añade su actor de aristas (NO en los fantasmas atenuados). Flag `edges` (def.
  **True**) en `render_scene_vtk`/`/api/render.png`/`render_view` → separa visualmente piezas adyacentes del
  MISMO color y da look técnico (como el web). Opt-out con `edges=False`. **(b) Pick EXACTO**: `pick_point`
  dejó la proyección matplotlib-aproximada y ahora usa la **matriz de cámara VTK** (`_vtk_projector`:
  `GetCompositeProjectionTransformMatrix` sobre la MISMA cámara que el render — `_setup_camera` extraído y
  COMPARTIDO por render y pick). Es matriz pura: NO llama `Render()` → **sin contexto OpenGL** (verificado).
  Si VTK no está, cae a matplotlib-orto (que coincide con el render-fallback de matplotlib). Plumbing: el bloque
  de cámara de `render_scene_vtk` se extrajo a `_setup_camera(ren, bmins, bmaxs, *, view, azimuth, elevation,
  zoom)`; `_H=0.78` (aspecto ventana) compartido. Verificado: pick del centro con fit en una pieza → su
  centroide a **dist_norm 0.0** (sub-píxel exacto; antes el matplotlib-aprox erraba a la pieza vecina), y sigue
  discriminando por posición. 532 tests (`test_render_vtk.py` edges-toggle, `test_pick.py` `_vtk_projector`
  centra el bbox). e2e sobre la faja: aristas nítidas en las guardas/agujeros del motor; pick exacto. **Reiniciar
  host MCP** para `render_view(edges=...)`.
  **(2026-06-29) RAYOS-X / TRANSPARENCIA + VIDRIO + COHERENCIA isolate/section EN EL PICK** (2 follow-ups del
  motor VTK). **(a) Rayos-X (`xray`, def. False) + vidrio**: hasta ahora lo no-resaltado salía gris opaco-fantasma
  y el VIDRIO salía gris opaco (la puerta lo notaba, la faja no). Ahora `render_scene_vtk`/`/api/render.png`/
  `render_view` aceptan `xray=True`: lo NO resaltado se vuelve translúcido EN SU COLOR (no gris, no oculto) →
  ves una pieza INTERNA en su contexto sin cortar (con `highlight_ids`: la resaltada sólida, el resto translúcido
  a color; sin highlight, TODO translúcido). El **vidrio sale SIEMPRE translúcido** (op 0.34) vía
  `_is_glass(feat)` (material override o nombre `vidrio|cristal|glass|templado`, espejo del `isGlass` del web).
  Cuando hay translucidez se activa **depth peeling** (`ren.SetUseDepthPeeling` + `rw.SetAlphaBitPlanes(1)` +
  `SetMultiSamples(0)`) → transparencia orden-independiente CORRECTA (capas bien superpuestas); sin translucidez
  se conserva MSAA 8. El peeling exige MSAA 0 → para no perder antialiasing en translúcidos se activa **FXAA**
  (`ren.SetUseFXAA(True)`, AA de post-proceso screen-space) → bordes nítidos también en xray/vidrio (2026-06-29).
  Las aristas (`edges`) se omiten en lo muy tenue (op ≤ 0.25). **OJO de uso**: el rayos-X solo es legible ACOTADO
  (`isolate`/`highlight` a 2-3 piezas); con toda la escena translúcida los colores se mezclan en una sopa turbia
  — para ENTENDER geometría, el default es render sólido + `isolate` (nítido) y `section` para ver dentro. **(b) Coherencia isolate/section en el `pick`**: `pick_point` ya no proyecta SIEMPRE toda la
  escena; acepta `isolate`/`section` (cableados en `/api/pick` y el tool `pick_point`) y resuelve las shapes UNA
  vez con `_resolved_shapes` (filtra a las piezas aisladas — forzando mostrarlas como el render aislado — y/o
  recorta con `_clip_to_section` usando el MISMO centro que el render) → pasa los MISMOS `isolate`/`section`/`fit`/
  `zoom`/`azimuth`/`elevation` del `render_view` y el píxel coincide con lo aislado/seccionado que ves. Verificado
  e2e: rayos-X del motor (contexto translúcido a color, depth-peeling capando bien); vidrio de la puerta id 28
  translúcido (se ve el travesaño de madera A TRAVÉS); pick aislado del motor c126 / vidrio c42 → `dist_norm 0.0`
  (exacto), section devuelve pieza válida del corte. 538 tests (`test_render_vtk.py` xray/glass, `test_pick.py`
  `_resolved_shapes`/isolate/section, `test_api.py` xray + pick honra isolate/section). **Reiniciar host MCP**
  para `render_view(xray=...)` y `pick_point(isolate=,section=)`.
  **(2026-06-29) CÁMARA MÁS LIBRE (roll/pan) + LABELS PORTADOS A VTK** (2 follow-ups del motor VTK). **(a)
  Roll + pan**: `_setup_camera` (compartida render↔pick) gana `roll` (grados, gira sobre el eje de visión =
  3.er GDL rotacional vía `cam.Roll`) y `pan=[px,py]` (desplaza el FOCO en el plano de vista, fracción de la
  semialtura: +px→derecha, +py→arriba — en orto la distancia del ojo es irrelevante, así que pan ES la
  'posición de cámara' lateral). Cableados en `render_scene_vtk`/`/api/render.png`/`render_view` y en
  `_vtk_projector`/`pick_point`/`/api/pick` (mismo `_setup_camera` → el pick coincide con el roll/pan del
  render). matplotlib (fallback sin OpenGL + multivista): `apply_camera` gana `roll` (`view_init(roll=)`, mpl
  ≥3.6, try/except defensivo); `pan` es solo-VTK. NOTA arquitectura: azimuth/elevation YA son la ÓRBITA
  (cualquier dirección sobre la esfera) → azimuth+elevation+roll+zoom+fit/pan cubren TODA la cámara de
  inspección; una 'posición de ojo' arbitraria no añade nada en ortográfica (solo dirección+roll+escala+foco
  importan), por eso NO se expuso un free-eye redundante. **(b) Labels en VTK** (re-expuestos en `render_view`,
  ahora VTK-nativos = captura limpia, no la rejilla matplotlib que motivó quitarlos): `labels=True` rotula el
  id de cada pieza con `_label_actor` (billboard post-it). **GOTCHA**: el billboard de texto en el renderer
  PRINCIPAL crashea VTK off-screen (access violation en `Render()`); se pintan en la **capa overlay** (la misma
  que la cota — `vtkBillboardTextActor3D` ahí sí funciona) → bonus: los rótulos nunca se ocluyen. El endpoint
  ahora manda a VTK toda VISTA ÚNICA shaded/vtk_only INCLUIDOS labels (antes labels forzaba matplotlib); solo la
  MULTIVISTA (`views`) sigue en matplotlib (`vtk_only`+`views` → 400 claro). **DECISIÓN multivista**: NO se
  porta a VTK (no la echo en falta: ángulo libre + roll + varias llamadas + el sistema de `drawing` la cubren;
  los viewports en mosaico añadirían complejidad/aspecto/coste de test por poco valor) — follow-up si hace
  falta. 544 tests (`test_render_vtk.py` roll/pan/labels, `test_pick.py` `_vtk_projector` pan, `test_render_frame.py`
  roll mpl, `test_api.py` labels/roll/pan + vtk_only+views→400). e2e sobre la faja: roll 25° (máquina ladeada),
  pan (primer plano desplazado), labels (ids legibles sobre las piezas), pick con roll coherente. **Reiniciar
  host MCP** para `render_view(labels=,roll=,pan=)` y `pick_point(roll=,pan=)`. **GOTCHA que costó depurar**:
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
- **FRENTE A — MOTOR DE CÁLCULO + MEMORIA DE CÁLCULO + REQUISITOS (2026-07-01)**: el agente pasa de
  "modelador que verifica" a INGENIERO que calcula y justifica con factores de seguridad. **(1) NEW
  paquete `library/engineering/`** (funciones PURAS, frontera library⟂doc; `structural.py` intacto):
  `belt` (banda sobre cama deslizante μ=0.33 + par de arranque 1.6× — MUY distinto del μ=0.06 de
  rodadura que queda SOLO para rodillos), `bolts` (ISO 898-1 + EN 1993-1-8: As por métrica M6–M24,
  grados 4.6/8.8/10.9/12.9, αv 0.6/0.5), `welds` (τ=F/(a·L) vs 0.6·σy; `throat_mm` ES la garganta,
  a=0.707·cateto), `bearings` (L10 ISO 281, objetivo 20 000 h / mínimo 5 000), `buckling` (Euler K=2
  conservador + inercia MÍNIMA del tubo), `stability` (casco convexo 2D + margen del COG), `loads`
  (**`hanging_load_kg`**: la carga de una unión = masa que PIERDE tierra al quitar su arista del grafo
  de conectividad; unión redundante → None → aviso honesto, no un número inventado), `mass`
  (masa/COM/bbox por pieza: catálogo pesa por FICHA, a-medida por volumen×densidad de
  `resolve_material` — **NO toca `_link_physics`**, que calibra URDF/MuJoCo; divergencia documentada).
  **(2) Catálogo**: `C_kN` (capacidad dinámica, nominal NSK/NTN ±10%) en los 41 rodamientos + 15
  chumaceras UCP/UCF/UCFL; `grado: "8.8"` estructurado en pernos. **(3) `fasten` dimensionable**:
  params opcionales `size` ("M10")/`qty`/`throat_mm`/`length_mm` (retrocompatible; sin ellos la unión
  se reporta "no verificable"). **(4) Reglas**: `_check(calc=...)` — las reglas numéricas llevan bloque
  `calc` {titulo, entradas, formula, sustitucion, resultado, criterio, fs} (formato viejo byte-idéntico
  sin calc); reglas nuevas "arrastre de banda" y "par de arranque"; rama banda-sobre-cama en
  motorización/par (peso REAL de la banda de la escena o `estimate_belt_kg`; `inclinacion_deg`). NEW
  `engineering/report.py::structure_engineering_check` (UNIVERSAL, no exige faja ni carga): uniones
  apernadas (utilización vs capacidad; varios fasten del MISMO par suman sus pernos), soldaduras, vida
  L10 (reparto parejo, hipótesis declarada), pandeo de la pata más esbelta, vuelco (COG vs huella de
  los grounds); las uniones SIN dimensionar se AGREGAN en una regla-resumen por tipo (una faja real
  declara >100 — un aviso por unión ahogaría el reporte). `POST /api/checks` devuelve clave nueva
  **`estructura`** (siempre; `ingenieria` intacta). `detect_conveyor` reconoce la categoría
  `motorreductores_sinfin` y `_enrich_conveyor` lee `potencia_kW` de las SPECS del candidato (no solo
  el nombre); torque derivado con **η=0.75 si es sinfín** (vs 0.85 helicoidal). **(5) Requisitos**:
  `Document.requirements` (metadato de manifest, espejo EXACTO de motion — ni log ni checkpoints;
  `set_requirements` valida claves numéricas de convención: carga_kg, largo/ancho/alto_paquete_mm,
  velocidad_m_s, inclinacion_deg, temperatura_c + texto libre producto/entorno/normativa/notas);
  GET/PUT `/api/requirements`; `/api/checks` y la memoria CAEN a los requisitos guardados (los params
  explícitos GANAN) → `engineering_check()` funciona SIN argumentos. **(6) MEMORIA DE CÁLCULO**: NEW
  `drawing/calc_report.py` (espejo de assembly_manual; A4 por defecto): portada (render + BASES DE
  DISEÑO + índice de verificaciones con estado + **VEREDICTO** APROBADO/CON AVISOS/NO CONFORME) + 1
  página por verificación (entradas → fórmula → sustitución → resultado → criterio → **FS**) + hoja de
  cualitativas; `GET /api/calc-report.pdf` (params opcionales, 400 claro si faltan carga/largo) + tool
  `calc_report(path,...)`. **Tools MCP 55→59** (`get_mass_properties`, `get_requirements`,
  `set_requirements`, `calc_report`; `engineering_check` pasó sus params a opcionales y devuelve
  {ingenieria, estructura}). **Verificado E2E en la faja id 38**: los requisitos SOBREVIVEN al
  reinicio (autosave SQLite); 12/12 reglas de ingeniería OK (NMRV-090 reconocido: motorización FS
  12.3, par 270 N·m, arranque FS 8.85); estructura limpia (L10/pandeo FS 1729/vuelco FS 4.0 + 2
  avisos agregados honestos); unión de prueba M8×2 → regla CUANTITATIVA FS 713 (y undo limpio);
  memoria de 13 páginas "APROBADO CON AVISOS" (`planos/faja-4m-memoria.pdf`); `gravity_test` 72/0 y
  colisiones idénticas (physics intacta). 630 tests (+71: test_engineering, test_mass_properties,
  test_engineering_rules, test_requirements, test_calc_report). **Reiniciar API + host MCP** para las
  4 tools nuevas y las firmas cambiadas. **Límite honesto**: carga de pernos solo en uniones
  no-redundantes (camino múltiple = indeterminado sin FEA → aviso); L10 con reparto parejo; pandeo/
  vuelco heurísticos por bbox+nombre (hipótesis declaradas en cada regla); doble fuente de densidad
  (mass.py usa materials.py; _link_physics sigue por categoría) — unificar es follow-up. Follow-ups:
  frente B (costo en catálogo → BOM costeado → cotización), campo `funcion`/rol estructurado,
  export STL/glTF (plan en `docs/checklist-cad-ia.md`).
  **(2026-07-01, Frente C) Regla de redundancia refinada + faja 38 APROBADA**: una unión DIMENSIONADA
  en camino de carga redundante reporta **"ok" con nota honesta** (antes "aviso"): la redundancia es
  FAVORABLE estructuralmente y no es accionable — en una máquina bien arriostrada casi todo camino es
  múltiple y la memoria jamás saldría limpia (test renombrado `test_redundant_path_is_ok_with_honest_detail`).
  Las 119 uniones de la faja id 38 se CURARON en un solo `edit_batch` (merge): **58 reclasificadas a
  `contacto`** (la autodetección había declarado "soldadura" donde no la hay: banda↔mesa/travesaños
  [desliza], perno de anclaje↔placa [la unión real es pie_placa_*], internos del tensor, drum_banda
  [fricción], tensor↔larguero salvo el soporte C), **20 pernos dimensionados** (pie_placa/pie_pata/
  rod_men M12×1, chum_mensula M14×2 [UCP207 N=17], nmrv_eje M10×2 [= prisioneros; el par va por
  CHAVETA — agent_note], nmrv_brazo RECLASIFICADO a perno M10×6 [brida]) y **41 soldaduras con
  garganta** (pata↔travesaño 3/140, larguero↔travesaño 3/120, mesa/repisa↔travesaño 3/80, ménsulas
  4/100, soporte C del tensor 4/100, drum_eje 4/110, disco_pata 4/120). Resultado: `engineering_check`
  **12/12 ingeniería + 64/64 estructura, 0 avisos** → memoria regenerada **VEREDICTO: APROBADO**
  (planos/faja-4m-memoria.pdf). Revisión guardada. **Lección**: curar la conectividad auto-detectada
  (reclasificar lo que no es soldadura) es tan importante como dimensionar — un fastener "soldadura"
  entre la banda y la mesa es un error de MODELO, no un pendiente de cálculo.
- **FRENTE C — CIERRE DE PENDIENTES (2026-07-01)**: **(1) Fix crítico de repo**: la regla genérica
  `data/` del `.gitignore` ignoraba también `core/apolo/library/data/` — el CATÁLOGO YAML COMPLETO
  (32 archivos, 217 refs) NUNCA se había versionado (el repo público de GitHub no podía cargar);
  acotada a `/data/` (SQLite de la raíz) y el catálogo entró al repo. **(2) Follow-ups menores**:
  requisitos ganan `moneda`/`tipo_cambio` (el `/api/quote.pdf` los usa de default; `fx` es SOLO
  presentación sobre USD y se declara en las notas); `cost_por_m` REFERENCIAL en las 53 refs
  cortables de perfiles/tubos (peso/m × USD/kg × 1.8, generado del propio catálogo);
  `_link_physics` UNIFICADO a `resolve_material`+`density()` de materials.py (fin de la doble
  fuente de densidad; gates: tests de robotics/physics/stability verdes + `gravity_test` de la
  faja 72/0 idéntico); `GET /api/export/stl` + tool MCP **`export_stl`** (STL binario de los
  visibles, tolerance en mm; tools 61→62 — **reiniciar host MCP**). **(3) UI web** (solo-frontend):
  panel **«Requisitos»** nuevo (bases de diseño con GET/PUT + botones **Memoria de cálculo (PDF)**
  [deshabilitado con hint si faltan carga/largo] y **Cotización (PDF)** con margen/impuesto/moneda/
  tipo_cambio), registrado en dock/StatusBar/íconos (8 toggles); **BOM con toggle «Costos»**
  (columnas USD/ud · USD total · fuente + totales catálogo/fabricación + ítem más costoso);
  ChecksPanel se PRE-LLENA desde los requisitos guardados; menú Archivo gana **Exportar STL**
  (endpoint) y **Exportar glTF** (CLIENT-side vía `viewport/exportGltf.ts` + GLTFExporter de
  three.js sobre las mallas del viewport — cero backend, patrón CustomEvent como "apolo:fit").
  Verificado e2e en `ui-preview` sobre la faja id 38: panel carga/guarda requisitos, BOM costeado
  cuadra con `/api/costing.json` ($1 685.97 tras el fix de material de la ménsula), 0 errores de
  consola. **GOTCHA zombie-socket reconfirmado**: un `multiprocessing.spawn` huérfano (hijo de un
  uvicorn muerto) retuvo :8000 sirviendo código VIEJO — un "reinicio" que no verifica el dueño real
  del socket VALIDA EN FALSO (el gate de gravedad hubo que repetirlo); detectar con
  `Get-NetTCPConnection` + `Win32_Process` (busca el `--multiprocessing-fork` con parent muerto).
  El trabajo quedó COMMITEADO en serie lógica (catálogo+previo · engineering+memoria · costeo+
  endpoints · docs · faja APROBADO · menores · UI).
- **Retorno compacto en set_material/set_visibility/set_vertical (2026-07-01)**: esas tools MCP
  volcaban el payload CRUDO de `scene_payload` (CON mallas: ~957 KB en la faja de 72 sólidos) o el
  brief sin `affected` (que cae a "todos"). Fix en dos capas: los endpoints
  `/api/features/{id}/visibility|material` y `/api/features/visibility` (bulk) ahora DEVUELVEN el/los
  `command_id` afectados desde el lambda de `_state_or_error` (aditivo: el payload completo sigue para
  la UI), y en el cliente MCP `set_material` pasa por `_scene_brief` (diff → solo la pieza + total) y
  `set_vertical` por `_scene_brief(summary)` (afecta a toda la escena → lista corta sin mallas).
  Medido en vivo: 956 786 → **350 bytes** por mutación. Tests en `test_mcp_brief.py` (endpoints
  adjuntan affected + brief recorta). **Reiniciar API + host MCP** para verlo por MCP.
- **FRENTE B — COSTO + BOM COSTEADO + COTIZACIÓN (2026-07-01)**: monetiza el Frente A (el vertical
  del negocio es COTIZAR transportadores). **(1) NEW `library/costing.py`** (puro, sobre
  `bom_from_scene` — misma agrupación del BOM): 3 fuentes de costo DECLARADAS por fila
  (`costo_fuente`): `specs.cost` del catálogo (USD/ud; en cortables `cost_por_m` USD/m, o `cost`
  interpretado por metro) → estimación de hardware sin precio (peso × USD/kg del material ×
  `HW_FACTOR`=3, piso $0.5) → fabricación a medida (peso × USD/kg × `FAB_FACTOR`=2.5 corte+
  soldadura+acabado+merma). `costed_bom` (filas BOM + costo_ud/costo_total/fuente),
  `costing_totals` (por categoría, catálogo vs fabricación, **ítem más costoso**), `scene_costing`.
  **(2) `materials.py`**: `COST_PER_KG_USD` (10 materiales, referencial LatAm) + `cost_per_kg()`.
  **(3) Catálogo**: `cost` REFERENCIAL (comentado "actualizar con proveedor") en NMRV-030..130
  ($120-1200), MOTOR-037/075/150/150-EH ($380-750), UCP/UCF/UCFL 204-208 ($8-23), PERNO-M10..M20
  ($0.35-1.6), rodamientos serie 6200 ($4-12); el resto cae a estimación. **(4) Endpoints/tools**:
  `GET /api/costing.json` + tool **`get_costing`** (responde "¿qué pieza es la más cara?");
  `GET /api/quote.pdf?margin_pct&tax_pct&currency` + tool **`quotation(path,...)`** → NEW
  `drawing/quote.py`: COTIZACIÓN PDF A4 multipágina (resumen económico: desglose por categoría,
  catálogo vs fabricación, margen %, impuesto % opcional, **PRECIO DE VENTA**, ítem más costoso,
  notas comerciales honestas [precios referenciales, validez 15 días, no incluye
  transporte/instalación] + detalle de partidas paginado con la FUENTE de cada precio; reusa
  `_table_sheet` de sheetset + cajetín). **Tools MCP 59→61.** **Verificado E2E en la faja id 38**:
  costo directo **$1 671.96** (fabricación $1 100.16 = 322 kg × factores + catálogo $571.80; más
  caro = NMRV-090 $520; 29 partidas, 0 sin costo); cotización a margen 25% → venta **$2 089.95**
  (matemática verificada), PDF de 3 páginas `planos/faja-4m-cotizacion.pdf`. 639 tests
  (`test_costing.py`). **Reiniciar API + host MCP** para `get_costing`/`quotation`. **Límite
  honesto**: precios y factores REFERENCIALES (las notas de la cotización lo declaran) — para
  cotizar en firme se actualizan `cost` en YAML/`COST_PER_KG_USD` con el proveedor; la mano de
  obra de ENSAMBLE no se modela aparte (va dentro de FAB_FACTOR). Follow-ups: `cost_por_m` real
  en perfiles/tubos, moneda por proyecto (hoy etiqueta por llamada), UI de cotización.
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

- **NOMBRES POR ROL, no por medida (convención, 2026-06-29)**. El nombre de una pieza describe su **ROL/función**
  («Larguero (+Y)», «Travesaño inferior», «Pata», «Reductor»), **NUNCA una dimensión MUTABLE** (sección 80x40x3,
  Ø50, 2mm…) que ya vive en la geometría/variables. Razón: el nombre que copia una cota la **duplica**, y al
  reparametrizar (cambiar `sec_larg_w`, etc.) el nombre queda MINTIENDO sin que nadie lo note. La medida es un dato
  DERIVADO: la UI del árbol la **muestra EN VIVO** (calculada del bbox), el BOM/lista-de-corte/planos la calculan de
  la geometría — nadie la lee del nombre. **EXCEPCIÓN**: identificadores ESTABLES de placa/función que el sistema sí
  lee y que NO cambian al reparametrizar — **grado de material** («A36», que `resolve_material` usa para inferir
  acero) y **specs de nameplate** (motor «1.5HP 1750rpm», reductor «1:30») — pueden quedar en el nombre hasta que se
  capturen como propiedad/variable (follow-up: `pot_motor_kW` variable + `set_material` por pieza para sacar A36 del
  nombre). Al renombrar piezas estructurales para validación, conserva las palabras de ROL que lee el detector
  (`larguero`/`travesaño`/`pata`/`motor`…) y el grado de material. **Árbol del modelo**: agrupa por ROL (no por
  comando) — une piezas iguales creadas por comandos distintos (un travesaño suelto + un patrón de travesaños
  iguales caían en grupos separados); y muestra la medida del bbox «L × A × H mm» en cada fila/grupo, siempre actual.
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

## Estado: V1·V2·V3·V4 COMPLETADAS + pulido post-V4 + FAJA DE BANDA + CATÁLOGO DE NORMAS (2026-06-15) + RESTRICCIÓN RIEL-CARRETE (A1·riel) + CATÁLOGO DE CARPINTERÍA + FIX VALIDACIÓN/INTERPENETRACIÓN + EBANISTERÍA + HERRAJE PULIDO + RENDER CON POSE (MCP) + MATES ÁNGULO/PARALELO + LOTE=1 REGENERATE + REGENERATE INCREMENTAL + MESH CACHEADO + VIDRIO TRANSLÚCIDO + HERRAJE PUERTA CORREDIZA REAL (U-100/D-100) (2026-06-17) + ERGONOMÍA MCP (retorno diff · edit PATCH · schema único · encuadre render) + PATTERN_GROUP (arrayar grupos, 36 comandos, 2026-06-23) + EDIT_BATCH + VARIABLES ON-CHANGE (ergonomía MCP, 2026-06-24) + AUTORÍA AGENTE-NATIVA: PERCEPCIÓN (multivista/etiquetas/sección) + MEDICIÓN + PÍXEL→3D + PREVIEW + INTENCIÓN (center_in/distribute) + N-GDL (add_constraint) (2026-06-24) + SISTEMA DE PLANOS PROFESIONAL A–G (cotas+normas · corte+nesting · detalle/cortes/rayado · cajetín+revisiones · juego de planos · DXF lineweight/PDF multipágina/A0-A4 · planos por INTENCIÓN · pulido de encuadre: escalas intermedias + globos en fila · DESPIECE ACOTADO POR PIEZA: tabla L×A×E + detalle de tabla con mortajas + cotas de montaje · PLAN PRO DE PLANOS COMPLETO 5/5 [juego completo · acota solo · herraje en lámina · explosionada · GD&T · fix layout iso/cajetín · COLOR tipo Inventor: iso sombreada] · PLANO DE ENSAMBLAJE PRO: norma en BOM/cédula · NOTAS DE MONTAJE · cotas de interfaz/pitch · cross-ref globo→hoja · MANUAL DE ENSAMBLAJE paso a paso [secuencia del log + render acumulado con highlight fantasma + cámara estable]) (48 tools · 39 comandos, 2026-06-24) · MATERIALES POLÍMEROS (pvc/caucho/carton, 2026-06-25) · VALIDACIÓN DE ENSAMBLAJE / SOUNDNESS (conectividad: ground/fasten + chequeo estático + autodetección, Fase 0+1; SIM DE GRAVEDAD de toda la máquina con casco convexo [gravity_test/exclude → "ver qué se cae"], Fase 2; UI panel "Montaje" [validar/gravedad] + CAÍDA ANIMADA EN EL VIEWPORT 3D [mallas reales, no GIF] + UNIONES DECLARADAS + PRUEBA EXACTA [auto-declarado por grafo de soporte dirigido; tools MCP declare_structure/get_connections/delete_connection], Fase 3; 2026-06-26 → 54 tools · 41 comandos) · RENDER VTK (sombreado suave como el web, anti-rayas) + ISOLATE en render_view (sin mutar doc, fuerza-mostrar) (2026-06-26) · SUPER-COMANDO `create_take_up` (tensor de cola trotadora: rodillo+rodamientos+seeger+eje fijo+perno pasante; componentes SEPARADOS+mapeados [soporte C + PERNO-Mxx]) + SUPER-COMANDO `create_drive_roller` (rodillo motriz: take-up un lado + eje largo Ø35 al reductor; reusa helpers de take_up.py, 43 comandos, 2026-06-27) · TENSOR REAL de tornillo (perno horizontal que atraviesa el eje roscado + soporte C de una pieza soldado al larguero; `dir_tensor`) + doc de montaje en los rodillos, instalados Ø35 en faja-paqueteria-4m (2026-06-27) · PERNO TENSOR ALLEN (socket_cap DIN 912) + CINEMÁTICA DEL TENSADO (junta prismática j_tensor_cola) (2026-06-27) · ESTUDIOS DE MOVIMIENTO CON NOMBRE (varias cinemáticas reproducibles por separado: Document.motion dict[str,list]; UI chips por estudio con ▶ propio + lista de juntas con scroll acotado; migración lista→dict; faja id 38 con «Levantar mesa» + «Tensar cola») (2026-06-28) · ÁRBOL DEL MODELO REDISEÑADO (filas 1 línea + buscador + iconos lucide + acciones al hover + agrupación por subsistema) + SCROLLBARS TEMÁTICOS + SISTEMA DE VENTANAS ACOPLABLES estilo VS 2022 (Dockview 7: acoplar/redimensionar/pestañas/persistencia; viewport centro fijo bloqueado) (solo-frontend, 2026-06-29) · CÁMARA DE ÁNGULO LIBRE en render_view (azimuth/elevation) + render_view VTK PURO (vtk_only, sin captura matplotlib por MCP) + pick_point a ÁNGULO LIBRE (orto+real como VTK) + COTA SOBRE EL RENDER (render_view measure=[a,b] dibuja línea+«X mm» del gap OCCT en capa overlay) + BORDES NÍTIDOS (aristas de feature, def. on) + PICK EXACTO (matriz de cámara VTK, sub-píxel) + RAYOS-X/TRANSPARENCIA (xray: contexto translúcido a color, depth-peeling) + VIDRIO TRANSLÚCIDO EN VTK + COHERENCIA isolate/section EN EL PICK + CÁMARA MÁS LIBRE (roll + pan, render↔pick) + LABELS PORTADOS A VTK (billboard en capa overlay) (2026-06-29) · VALIDACIÓN DE INGENIERÍA UNIVERSAL DE LA FAJA (detect_conveyor enriquecido por VARIABLES del proyecto + nombres: reconoce motor/tambor/rpm/eje a-medida; chequeos estructurales NUEVOS: flecha del bastidor [viga 5wL⁴/384EI vs L/250] + flexión del eje; library/structural.py + materials E/σy; 10/10 reglas OK en faja id 38) (2026-06-29) · TRANSMISIÓN POR FAJA DE POTENCIA (builder v_pulley = polea en V/sheave sección A/B + familia POLEA-V comercial, catálogo 191→197; faja id 38 convertida de acople directo a faja en V: motorreductor reubicado abajo+outboard a C=260mm, 2 poleas Ø110 1:1 [conserva 0.348 m/s], lazo de faja vertical + guarda envolvente, eje de salida; 0 colisiones nuevas) (2026-06-29) · CRITERIO DE INGENIERÍA POR DEFECTO (decálogo de diseño-para-fabricación general —máquinas/muebles/estructuras— en `design/guidelines.py`; capa 1 inyectada SIEMPRE en instrucciones MCP + SYSTEM_PROMPT del chat, capa 2 tool MCP `get_design_guidelines`/`GET /api/design-guidelines`; el agente diseña como ingeniero/estructurista, asume soportes/pernos/forma-conforme sin que se lo pidan; 54→55 tools, 2026-06-30) · ACOPLE DIRECTO NMRV (faja en V DESCARTADA por capacidad —insuficiente en el lado lento/alto par—; tambor de eje VIVO + chumaceras + **motorreductor sinfín-corona NMRV de eje hueco montado sobre el eje** + brazo de torque; faja id 38) + FAMILIA PARAMÉTRICA DE MOTORREDUCTORES NMRV (builder `worm_gearmotor` + `data/31_motorreductores_sinfin.yaml`, 8 tamaños NMRV-030..130 de eje hueco, categoría `motorreductores_sinfin`; catálogo 197→205) (2026-06-30) · FRENTE A: MOTOR DE CÁLCULO (library/engineering/: pernos ISO 898-1 · soldaduras · vida L10 · pandeo Euler · vuelco COG-vs-huella · banda-sobre-cama μ=0.33 + par de arranque · carga por grafo de conectividad) + `fasten` dimensionable (size/qty/throat/length) + `get_mass_properties` + REQUISITOS DE PROYECTO (Document.requirements, checks sin args) + MEMORIA DE CÁLCULO PDF (calc_report: bases de diseño + fórmula/sustitución/FS por verificación + veredicto; 55→59 tools, 2026-07-01) + FRENTE B: COSTEO Y COTIZACIÓN (library/costing.py: BOM costeado con fuente por fila [catálogo referencial · hardware estimado · fabricación peso×material×factor] + `get_costing` + COTIZACIÓN PDF `quotation` con margen/impuesto/precio de venta; cost referencial en NMRV/MOTOR/chumaceras/pernos/6200; 59→61 tools, 2026-07-01) · 639 tests · catálogo 217 refs (chumaceras UCP de pie + UCF/UCFL de brida, realistas, 2026-07-01)

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
> 218 tests. **Follow-up**: easing, exportar vídeo/GIF, ~~multi-estudio~~ ✅ (2026-06-28), física/gravedad
> (vía export URDF→PyBullet).
>
> **Bloque #6·multi-estudio ✅ (2026-06-28). Estudios de movimiento CON NOMBRE.** A raíz de que la faja
> `faja-paqueteria-4m` (id 38) tiene ya DOS mecanismos con juntas (la **mesa que se levanta** + el **tensor
> del rodillo de cola** `j_tensor_cola`) pero el sistema solo soportaba UN motion study (`Document.motion`
> era una lista única) → el usuario veía un solo «▶ Reproducir» enterrado que siempre animaba la mesa, sin
> poder reproducir las cinemáticas por separado. `Document.motion` pasó de `list[dict]` a **`dict[str,
> list[dict]]`** (nombre→fotogramas); `set_motion(name, keyframes)` (lista vacía → borra) + `delete_motion(name)`;
> **migración** en `from_apolo_bytes` (lista vieja → `{"Estudio 1": [...]}`, cubre SQLite/revisiones/.apolo).
> API: `GET /api/motion`→`{studies:[{name,keyframes,duration}]}`, `PUT {name,keyframes}`, `DELETE {name}`,
> `POST /api/motion/scan {name,steps}`. `robotics/motion.py` SIN cambios (sigue tomando una lista). UI
> (`KinematicsPanel.tsx`): la sección «Animación» única se volvió **«Estudios de movimiento»** con una fila de
> **chips** (uno por estudio: nombre · nº fotogramas · **▶ propio** · ✕) + «➕ Nuevo estudio» (borrador hasta
> capturar el 1.er fotograma); el editor (capturar/borrar fotograma, 💥 comprobar recorrido) opera sobre el
> **estudio activo**; el bucle `requestAnimationFrame` usa los keyframes del estudio que se reproduce
> (`playingStudy`). **Fix de layout** (causa de «único botón que alcanzo a ver»): la lista de juntas `.kin-grid`
> va en `.kin-joints` con **altura acotada + scroll** (max-height 240px) → los controles de Estudios quedan
> siempre a la vista. El «estudio activo» es estado de UI (no se persiste cuál); los estudios sí. 520 tests
> (`test_motion.py`: named studies + migración lista→dict). En la faja id 38 quedan creados **«Levantar mesa»**
> (4 fotogramas, mesa) y **«Tensar cola»** (`j_tensor_cola` 0→12). Solo-UI+API aditivo → `cd ui; npm run build`
> + recargar; el `--reload` de la API ya sirve los endpoints nuevos.
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
- **A2 · Motion study**: easing, exportar vídeo/GIF, ~~multi-estudio~~ ✅ (2026-06-28, estudios con nombre). `[follow-up B6]`

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
  - **Validación de ingeniería UNIVERSAL — enriquecida por VARIABLES + chequeos estructurales (2026-06-29)**.
    A raíz de que la faja real `faja-paqueteria-4m` (id 38) está HECHA A MANO (motor/tambor/eje a-medida,
    `component=null`) y `detect_conveyor` solo miraba specs de catálogo → caía a `_detect_by_name` y perdía
    motor/rpm/Ø-tambor/par. Ahora `detect_conveyor(scene, variables)` y `_detect_by_name(scene, variables)`
    pasan por **`_enrich_conveyor`**, que RELLENA lo que falta con las **variables del proyecto** y los
    nombres: `tambor_d` (var `diam_tambor` o el mayor cilindro rodillo/tambor/polea), `rpm_motor` (var
    `rpm_salida`, o `rpm_motor/ratio_red`), **motor a-medida** (`motor="documento"` + potencia parseada del
    nombre — entre candidatos motor/reductor toma el de mayor HP/kW legible, así el "Motor 1.5HP" gana al
    "Reductor 1:30" sin potencia → `motor_kW`; deriva `torque_Nm`=P·η/ω), `eje_d` (var `diam_eje` o Ø del
    nombre), y **`frame`** (`_frame_from_scene`: sección del larguero [ancho Y × alto Z, pared de `esp_larg`/
    nombre], material vía `resolve_material`, **vano** = mayor hueco entre patas, longitud, y peso transportado
    de banda+mesa+estructura por volumen×densidad). 2 chequeos nuevos en `conveyor_engineering_check`:
    **flecha del bastidor** (larguero = viga simplemente apoyada, carga repartida `5wL⁴/384EI`, admisible
    L/250) y **flexión del eje** del tambor (`σ=32·(F·L/4)/πd³`, carga radial ≈ 2× fuerza de arrastre, admisible
    σy/2 — estimación). NEW `library/structural.py` (puro: `rect_tube_inertia_mm4`, `beam_udl_deflection_mm`,
    `shaft_bending_stress_mpa`) + `materials.py` gana `young_modulus`/`yield_strength` (E y σy por material,
    reusan `_norm`). La motorización acepta el motor a-medida (`motor_kW`, sin `CATALOG["documento"]`). Cableado:
    `/api/checks` y el tool del agente pasan `DOC.variables_resolved` a `detect_conveyor`. 551 tests
    (`test_structural.py`, `test_validation.py`: enriquecido por vars / chequeos estructurales / flecha-error).
    **Verificado e2e en la faja id 38**: las 10 reglas OK — velocidad 0.348 m/s, motor 1.119 kW (del "1.5HP"),
    par 155.7 N·m ≥ 7.5, **flecha 0.21 mm ≪ 6.41 admisible** (vano 1603 mm, tubo 40×80×3 acero), eje Ø30 a 17 MPa
    ≪ 125. **Límite honesto**: la flexión del eje es estimación (carga radial aproximada, apoyo ≈ ancho); el
    voladizo REAL del eje motriz (cantilever al reductor) y leer densidad/material del catálogo (no por nombre)
    quedan de follow-up. Las variables se identifican por nombre convencional (`diam_tambor`, `rpm_salida`…) — el
    super-comando y las fajas del agente los usan; degrada con elegancia si faltan.
  - **Transmisión por FAJA DE POTENCIA (poleas en V) + conversión de la faja id 38 (2026-06-29)**. A pedido del
    usuario, la faja pasó de **motorreductor de acople DIRECTO al eje** a **transmisión por faja en V con 2 poleas**.
    **Catálogo**: builder NEW `builders.py::v_pulley` (polea en V/sheave = disco con N canales trapezoidales en V por
    revolución + taladro; sección A `groove_top≈13/pitch15`, B `≈17/19`) + familia YAML `POLEA-V` en `85_transmision.yaml`
    (6 refs comerciales sección A/B, Ø en pulgadas, ISO 4183) → **catálogo 191→197**. La FAJA en V no es ítem de
    catálogo (consumible cortado a medida): se modela como **lazo racetrack** (run_script) entre los 2 centros.
    **Diseño (buenas prácticas)**: poleas Ø110 (sección B) **1:1** (el reductor sigue reduciendo → conserva 0.348 m/s;
    la faja solo TRANSMITE y desplaza el reductor fuera del eje); **distancia entre centros C=260 mm** (≈2.4·Ø, dentro
    del rango V-belt); motorreductor reubicado **abajo (−260 Z) y outboard (+Y)** para que su eje de salida alinee con
    la polea conducida sin chocar larguero/bastidor; faja VERTICAL; **guarda envolvente** (shell) sobre poleas+faja;
    eje de salida Ø28 conectando reductor→polea motriz. **Cirugía MCP** sobre id 38 (event-sourced, paramétrico):
    `edit_batch` bajó el conjunto (reductor c124 + barreno c125 del eje-hueco + motor c126 + bornes c127 + cubierta
    c128, todos anclados a `drum_cz`/`larg_inner_y`); `set_visibility_bulk` ocultó lo obsoleto del acople directo
    (brazo de torque c129 + guardas c134/c140/c143 → la guarda de faja las reemplaza); `run_batch` insertó las 2 poleas
    (`POLEA-VB-4`) + faja + guarda; `create_cylinder` el eje de salida. Verificado: render lateral (faja vertical entre
    poleas) + rayos-X 3/4 (conjunto con guarda) + `check_interference` → **0 colisiones nuevas** (lo que sale es
    intencional: motor↔reductor acople preexistente, faja↔poleas asiento, eje↔guarda paso). **LECCIONES**: (1) **añadir
    YAML nuevo NO recarga el worker** (uvicorn `--reload` vigila `.py`, no `.yaml`) → tras editar el YAML hay que tocar
    un `.py` para forzar la recarga del catálogo, si no `insert_component` da "componente desconocido". (2) Reubicar un
    sub-conjunto hecho a mano **cascada por sus dependencias acopladas**: mover el reductor rompió el `drill_hole` c125
    (eje hueco) a coords fijas → incluirlo en el mismo `edit_batch`. (3) Las ediciones por API se autoguardan en SQLite
    → tras la recarga del worker, `open_project(38)` restaura la cirugía. **Follow-ups**: borrar (no solo ocultar) las 4
    piezas obsoletas con `/api/commands/remove`; base regulable real para tensar; renombrar el eje c413 («largo al
    reductor» ya no aplica); engineering_check podría validar la relación de poleas/longitud de faja.
    **Retoques tras revisión del usuario (2026-06-29)**: (a) **guardas obsoletas BORRADAS** (no solo ocultas):
    el brazo de torque + las 3 guardas del acople directo eran booleanas con **barrenos y fijadores
    auto-declarados** colgando → borrar el sub-grafo COMPLETO requirió primero `DELETE /api/fasteners/{name}`
    de los 15 fijadores que las referenciaban, luego `/api/commands/remove` de las 13 (cajas+cortes+barrenos+
    booleanas); quedó SOLO la guarda de faja. (b) **El motorreductor flotaba** (relocado sin apoyo). 1.er intento = bancada de
    4 patas al PISO → el usuario lo corrigió con una foto de referencia: el soporte NO va FUERA del bastidor en
    el piso, va **colgado del propio bastidor**. Fix final: **ménsula de motor atornillada al larguero** (placa
    vertical bolted al larguero +Y + repisa horizontal bajo el motorreductor); `fasten` ménsula↔larguero (soldadura)
    + reductor/motor↔ménsula (perno) → el conjunto se sujeta por la ménsula→larguero→patas→piso. `gravity_test`
    pasó de **6 caídas a 0** («todo sujeto a tierra»). De paso se declararon las uniones de los **rodillos de
    retorno** (ménsula↔larguero soldada + rodillo↔ménsula con perno) que el grafo dirigido no ancla por «colgar»,
    y se borró un fijador OBSOLETO reductor↔eje-del-tambor (del acople directo, ya no aplica con la faja).
    **Nota mecánica**: en transmisión por faja la polea va por FUERA del rodamiento (correcto), así que el motor
    queda al costado del extremo motriz — pero **soportado por la ménsula del bastidor**, no por patas propias.
    **REDISEÑO PROFESIONAL del accionamiento (2026-06-29)**: el usuario rechazó (con foto de referencia) los
    soportes pobres («apenas pegan, colisionan, sin ingeniería ni estética») y pidió la disposición real: **motor
    DEBAJO de la mesa, dentro del bastidor, y faja de potencia en DIAGONAL**. Rehecho: (1) motorreductor reubicado
    **transversal bajo la mesa** (eje a lo largo de Y, a `x≈3340` para librar la pata de cabecera, `z≈585` bajo la
    banda de retorno), corrido a `y≈155-410` para librar la línea de postes; (2) **faja en V DIAGONAL** (~30°) —
    el `run_script` del lazo pasó de vertical a un **racetrack orientado**: 2 cilindros en los centros + un `Box`
    girado `Rotation(0,-ang,0)` sobre el eje de la línea (`ang=atan2(Δz,Δx)`); ambas poleas en el plano `y=555`
    (por fuera del rodamiento); (3) **guarda diagonal** (shell `Box` orientado con el mismo ángulo, sigue la faja);
    (4) **sub-bastidor de motor REAL** (run_script `Sub-bastidor de motor (cuna)`): **4 postes** que cuelgan de los
    largueros + **2 travesaños** + **placa base** = cuna rígida y simétrica bajo la mesa (reemplaza la ménsula que
    apenas tocaba); `fasten` postes↔largueros (soldadura) + reductor/motor↔cuna (perno). Verificado:
    `check_interference` → **0 colisiones del soporte** (lo que sale es interno del motorreductor —acople/cubierta/
    bornes— y la faja asentando en las poleas, intencional); `gravity_test` → **0 caídas** (la cuna→largueros→patas→
    piso). **Lección de diseño**: para un accionamiento creíble, el motor va bajo la cama con la faja en diagonal y
    un sub-bastidor que cuelga de AMBOS largueros (no una ménsula a un lado); el racetrack de la faja debe
    orientarse al ángulo real de la línea de centros, no asumir vertical/horizontal.
    **Afinado por revisión del usuario (2026-06-29)**: (a) el motor estaba lejos del tambor (lado mid-span de la
    pata de cabecera) → reubicado al OTRO lado de la pata, **junto al rodillo motriz** (`x3340→3650`, faja más
    corta C≈258 mm); el sub-bastidor se reconstruyó con los postes librando el eje de salida y el tambor (colisión
    eje↔poste de 3237 mm³ eliminada). (b) **patas más gruesas**: `sec_pata 50→63.5` (HSS 2.5″, `esp_pata 3`) — elegí
    2.5″ sobre 3″ como ingeniero porque 3″ obligaba a placas base de 150 (la de 120 fue dimensionada para 2″) y
    apretaba el motor contra el tambor; a 2.5″ el roce pata↔arandela de anclaje queda en **5.2 mm³** (contacto
    despreciable, no interpenetración). 0 colisiones del soporte, `gravity_test` 0 caídas. **Lección**: engrosar un
    miembro cascada a su herraje (las patas a las arandelas de anclaje) y a las holguras vecinas (el motor a la pata/
    tambor) — hay que reposicionar en consecuencia, no solo cambiar la sección. **Follow-up**: placas base a 150 +
    pernos recolocados para patas ≥3″; base regulable (rieles ranurados) en la cuna para tensar la faja.
    **Patas 3″ + PIES NIVELADORES (2026-06-29)**: el usuario pidió patas de 3″ y reguladores de altura en la base.
    Truco de ingeniería que evitó el rework de placas/pernos: en vez de pelear con la placa de 120 vs la pata de
    76, **elevé la base de la pata 60 mm** (`pata_alto = larg_bot - placa_thk - 60`, `pata_cz = placa_thk + 60 +
    pata_alto/2`) y metí el **pie nivelador** en ese hueco (run_script `Pies niveladores`: vástago roscado Ø24 +
    tuerca de regulación hexagonal + contratuerca por pata, `RegularPolygon(22,6)` extruido). Al elevar la pata,
    su base (z70) queda POR ENCIMA de los pernos de anclaje (z≤30) → el roce pata↔perno de 419 mm³ **desaparece**
    sin tocar las placas ni los pernos. La altura de trabajo no cambia (el tope de la pata sigue en `larg_bot`; el
    pie absorbe el ajuste). `fasten` pie↔placa (perno) + pie↔pata (perno) ×6; `gravity_test` 0 caídas (83/83).
    **Lección**: a veces el fix elegante NO es modificar lo que estorba (placa/pernos) sino **reposicionar** la
    pieza (elevarla sobre el componente nuevo) para que el conflicto se disuelva — y de paso añade la función
    pedida (regulación de altura). (c) **Largueros a HSS
    4″×2″** (101.6×50.8×3, medida comercial Perú): editar las variables `sec_larg_w`/`sec_larg_h` (80/40→101.6/
    50.8) cascadeó limpio — el larguero crece hacia abajo, las patas se acortan (734 mm) y la altura de trabajo
    (mesa 846-848) queda intacta. **Lección**: borrar piezas auto-declaradas exige limpiar antes sus fijadores;
    una pieza relocada necesita su propio apoyo declarado para no «caer» en la prueba de gravedad.
    **GUARDA con criterio de ingeniería (2026-06-30)**: la guarda de la faja en V (run_script `c613`) pasó de
    una caja rectangular a **silueta redondeada de estadio** (dos casquetes r75 en los centros de polea + banda
    tangente a `atan2(Δz,Δx)`, hueca pared 6 mm) — la forma clásica de guarda de poleas. Tras crítica del usuario
    («un protector NO va completamente cerrado; la cara interior no va; falta soporte al bastidor; tiene que ser
    montable/desmontable con pernos»): (1) **cara interior (-Y) ABIERTA** — el `inner` que se resta se desplaza/
    ensancha en Y (`stad(R-t, yc=549, yw=70)` vs outer `557/66`) para que el vacío rebase el dorso → deja pared
    perimetral + tapa exterior, dorso abierto (se monta contra la máquina y deja entrar los ejes); (2) **3 orejas
    de montaje** (bosses con agujero M10) en el borde trasero a r88 de cada centro (caja girada `Rotation(0,-φ,0)`
    al ángulo radial); (3) **agujero de paso de eje** Ø44 en la tapa exterior para el eje de la conducida (antes lo
    interpenetraba); (4) **3 ménsulas** (run_script `c660` = standoff blocks) soldadas 2 al larguero +Y / 1 a la
    **cuna** del motor; (5) **3 pernos M10** (run_script `c661`, cabeza Allen) guarda→ménsulas = desmontable.
    **Conectividad corregida**: la autodetección había declarado la guarda **soldada a poleas/faja/eje (¡rotan!)**
    — se borraron (`delete_connection auto_f_107/112/114/116/118`) y se declaró `fasten` solo a estructura estática
    (ménsulas↔larguero/cuna soldadura, guarda/pernos↔ménsulas perno). Verificado: `check_interference` solo
    contactos intencionales (soldadura ménsula↔cuna 8.1 cm³ confirma que la cuna es sólida ahí, no flota);
    `gravity_test` exacto → 85 a tierra, 0 caídas (la guarda cuelga del bastidor). **Lección**: un protector se
    abre al lado máquina, se SOPORTA al bastidor con ménsulas y se ATORNILLA (no es una cápsula cerrada flotante);
    y NUNCA fijarlo a piezas que giran (poleas/faja/eje) — la autodetección por contacto AABB lo hace mal, hay que
    corregirlo. **Follow-up**: ménsulas como L-angle real (hoy bloques), pernos de catálogo `PERNO-M10` para BOM.
    **SOPORTE DE MOTOR compacto apoyado en las patas (2026-06-30)**: la «cuna» (run_script `c642`) era un cradle
    de **ancho completo colgando de AMBOS largueros** (4 postes + 2 travesaños + placa, 11.8M mm³) — sobredimensionado,
    cuando la **pata de cabecera c45_2 está a 26 mm** del motorreductor y baja DIRECTO al piso. Rediseñado a un
    soporte compacto (**6.87M mm³, −42 %**): **viga transversal soldada a AMBAS patas de cabecera** (c45_2 +Y / c49_2
    −Y) + 2 brazos cantiléver bajo el motorreductor + placa de montaje. **Conectividad**: borradas las soldaduras
    cuna↔larguero (`delete_connection cuna_larguero_pY/nY`), declaradas cuna↔c45_2 / cuna↔c49_2 (soldadura);
    motor/reductor↔cuna (perno) sobreviven al editar `c642` en sitio. `check_interference` → soldadura a cada pata
    24.6 cm³ (apoyo sólido real); `gravity_test` exacto → 85 a tierra, 0 caídas (descarga por cuna→patas→piso, mejor
    camino de carga que colgar de los largueros). **Lección**: si una pieza existente (pata al piso) está al lado,
    APÓYATE en ella en vez de duplicar estructura colgante; el camino de carga corto al suelo es más rígido y liviano.
    **NO bajé el motor** (lo pidió el usuario por miedo a que la faja al pandear lo roce): verificado por render
    lateral que **la faja corre en el plano y≈555 y el cuerpo del motor está en y≈155 → ~270 mm de separación EN Y**,
    así que el pandeo (unos mm en Z) no puede alcanzarlo; además bajar el motorreductor movería la polea motriz →
    forzaría rehacer faja+guarda y restaría altura libre. **Lección**: antes de «mover para dar holgura», confirmar el
    eje real del conflicto (aquí el huelgo es en Y, no en Z) — mover en Z no resuelve una separación en Y.
    **TREN MOTRIZ CEÑIDO — plano de faja adentro, ejes acortados, guarda re-encajada (2026-06-30)**: tras revisión
    del usuario (3 críticas válidas). (a) **Soporte inferior de la guarda flotando**: al rediseñar la cuna (compacta),
    la ménsula inferior de la guarda (`c660` b3, anclada a la cuna vieja de ancho completo) quedó EN EL AIRE — el grafo
    de conectividad seguía declarando `c660↔c642` (gravity pasaba) pero la geometría ya no tocaba; **lección**: al mover/
    encoger una pieza, revisar las que se anclaban a ella, no fiarse de que gravity pase (la unión declarada sobrevive
    al editar in situ aunque la geometría se separe). (b) **Eje motriz `c413_eje` muy largo** (`largo_eje_motor 230` →
    y610, 55 mm pasado la polea, con agujero de paso en la tapa): el eje DEBE cruzar el larguero para llevar la polea
    AFUERA (la faja libra el bastidor y se alinea con la motriz), pero el muñón pasado la polea era injustificado →
    `largo_eje_motor 230→160` (termina en y540, DENTRO de la guarda) → se quitó el agujero de la tapa. (c) **Espacio
    larguero↔polea excesivo** (52 mm cara-a-cara): la polea va afuera del larguero por la holgura de faja, pero 52 mm
    sobraba → **plano de faja y555→y520** (huelgo 16 mm). Cascada coordinada por `edit_batch`: poleas `c610`/`c611`
    (y555→520), faja `c612` (cy 555→520), eje reductor `c614` (acortado a y405-535), eje motriz `c413` (acortado), y
    luego guarda `c613` recentrada+**angostada** (cy 526, ancho 66→48, dorso abierto rim y502 libra el larguero 490.8 por
    11 mm) + ménsulas `c660`/pernos `c661` reposicionados (2 a larguero arriba, 1 que ahora SÍ baja a la cuna). C (entre
    centros) intacto → faja/velocidad sin cambio (solo se desplazó en Y). Verificado: `c642↔c660` 2.8 cm³ (ménsula inf
    apoyada en la cuna, ya no flota), `c413_eje↔c613` ELIMINADO, polea↔larguero sin colisión; `gravity_test` 85 a tierra
    0 caídas. **Lección**: acercar una transmisión al bastidor reduce voladizo de ejes (mejor mecánica) pero obliga a
    angostar la guarda para que su dorso abierto libre el larguero — mover el plano de faja cascada a poleas+faja+ambos
    ejes+guarda+ménsulas, todo por el mismo offset en Y.
    **VUELTA A ACOPLE DIRECTO — motorreductor de eje hueco sobre el eje (2026-06-30)**: el análisis de capacidad
    de la faja en V (a pedido del usuario) reveló que era **insuficiente**: la faja iba en el lado LENTO/alto par
    (58 rpm, 0.34 m/s, ~170 N·m → tensión efectiva ~3 100 N); una sola faja B da ~600-900 N → harían falta ~6-8
    fajas. Raíz: **las fajas en V trabajan en alta velocidad/bajo par**; a 0.34 m/s la potencia por faja es ínfima.
    Decisión del usuario: **acople directo** (elimina la faja de raíz). Cirugía event-sourced grande (borrado atómico
    del sub-grafo por `POST /api/commands/remove` con piezas+fijadores JUNTOS para no dejar refs colgando —usar `curl`,
    NO hay tool MCP de remove): (1) **borradas** la transmisión por faja (2 poleas, faja, guarda, ménsulas, pernos, eje
    de salida) + cuna + **el super-comando `create_drive_roller`** (c413) con sus ~40 fijadores. El drive_roller se
    descartó porque modela **eje FIJO + take-up** (el rodillo gira sobre el eje, sujeto por perno tensor) — INCOMPATIBLE
    con accionamiento directo, que exige **eje VIVO** (gira con el tambor para que el reductor lo mueva) y el take-up va
    en la COLA, no en la cabecera. (2) **Reconstruido el tambor motriz** por run_script: `c669` tambor Ø114 engomado
    (barreno Ø44) + `c670` **eje vivo Ø40** + `c671` **2 chumaceras** (housings con barreno, atornilladas a los largueros
    en el hueco tambor↔larguero). (3) **Motorreductor sinfín-corona NMRV de eje hueco** `c672` (a partir de FOTO de
    referencia del usuario —era un NMRV, no un helicoidal en línea—: caja de corona con **barreno pasante Ø48** + **brida
    de salida con círculo de pernos** + **tapa NMRV** + **motor PERPENDICULAR** [tornillo sin fin a 90°, eje X, offset
    abajo] + ventilador + bornes) montado SOBRE el eje vivo del tambor + `c673`
    **brazo de torque** anclado al larguero +Y (anti-giro). Conectividad: tambor→eje→chumaceras→largueros→patas→piso;
    reductor→eje (chaveta) + brazo→larguero. **La cola (`c412`) conserva el tensado** (accionamiento en cabecera, tensado
    en cola = estándar). Verificado: `check_interference` solo intencionales (brazo↔reductor 75.6cm³, brazo↔larguero
    11.6cm³, eje↔larguero +Y 0.7cm³ = **agujero de paso** donde el eje cruza el bastidor hacia el reductor outboard);
    `gravity_test` 70 a tierra, 0 caídas. **68 sólidos** (antes 85). **Lecciones**: (a) una faja en V va en el lado RÁPIDO
    (motor→reductor), NUNCA en el lado lento (reductor→tambor) — ahí van cadena o acople directo; (b) un **tambor MOTRIZ
    necesita eje VIVO + rodamientos fijos** (chumaceras), no el eje-fijo+take-up del super-comando `create_drive_roller`
    (ese sirve para rodillos LIBRES/de tensión, no para el motriz); (c) el eje del tambor cruza el larguero (axis a media
    altura del bastidor) → agujero de paso, no es colisión; (d) **el usuario reconoce el HARDWARE por foto** — pidió
    el NMRV real (motor a 90°, eje hueco con brida+tapa) en vez del helicoidal en línea que asumí → modelar el tipo
    correcto de motorreductor importa. **OJO ingeniería**: el sinfín-corona rinde **~0.7-0.8** (vs ~0.95 del helicoidal)
    → baja el par disponible en el eje; conviene revalidar `engineering_check` (con esa η el margen de par sigue holgado
    para 1.5HP·1:30 en esta faja). **Follow-up**: chaveta modelada, `create_drive_roller` podría ganar un modo
    «eje vivo + chumaceras». [Chumaceras de catálogo ✅ 2026-07-01, ver abajo.]
    **FAMILIA PARAMÉTRICA DE MOTORREDUCTORES NMRV (2026-06-30)**: a pedido del usuario (que quería «descargar todos los
    modelos» de motorreductores) se optó por la vía escalable del catálogo en vez de acumular STEP pesados/estáticos
    (los STEP de fabricante están tras login/configurador/licencia y NO son paramétricos; se reservan para importar la
    pieza EXACTA al cotizar). NEW builder **`worm_gearmotor`** (`builders.py`): sinfín-corona NMRV = caja de corona con
    **eje HUECO pasante** (barreno en Y local, para montaje directo sobre el eje del tambor) + **brida de salida con
    círculo de pernos + tapa NMRV** + **motor PERPENDICULAR** (a 90°) con ventilador y bornes; envolvente escala de
    `center_distance`. NEW familia **`data/31_motorreductores_sinfin.yaml`** (categoría **`motorreductores_sinfin`**,
    añadida a `CATEGORIES`): 8 tamaños **NMRV-030/040/050/063/075/090/110/130**. **Ø del eje hueco (bore, tol H8) +
    chavetero (b×t) VERIFICADOS** contra el catálogo oficial **Motovario «NMRV/NMRVpower» (rev0 2017, pág.102)** vía
    WebSearch+WebFetch→pypdf (030→Ø14, 040→Ø18, 050→Ø25, 063→Ø25, 075→Ø28, 090→Ø35, 110→Ø42, 130→Ø45; coincidían exacto).
    Envolvente de caja/brida y frame IEC **representativo** (escala del tamaño): la tabla del fabricante los codifica por
    letras que no mapean 1:1 al modelo simplificado; para geometría 100% fiel de un tamaño, importar el STEP del proveedor.
    **Catálogo 197→205 refs**; 557 tests (`test_catalog_datadriven.py::test_worm_gearmotor_nmrv` + conteo). Aparecen solos en la UI/BOM/
    agente (enum dinámico). **Lección**: para una biblioteca reutilizable, familia paramétrica > pila de STEP (livianas,
    editables, con BOM); el STEP es para la compra puntual. **Follow-up**: familia helicoidal en línea propia (hoy los
    `motor` MOTOR-* la cubren), variantes de montaje (patas/brida), importar STEP oficial al cotizar.
    **USADA en la faja id 38 (2026-06-30)**: el motorreductor NMRV hecho a mano (`c672`, run_script) se REEMPLAZÓ por el
    componente de catálogo **`insert_component NMRV-090`** (`c682`) montado sobre el eje del tambor. Como el eje hueco del
    NMRV-090 es Ø35 (= rodamiento 6207, el original), el eje vivo del tambor `c670` se ajustó **Ø40→Ø35** para calzar el
    bore; el brazo de torque `c673` se reubicó (el NMRV-090 es más grande que el modelo a mano). **insert_component coloca
    el ORIGEN LOCAL del builder en `position`** (no el centro del bbox) → como el `worm_gearmotor` tiene el barreno en el
    origen (eje Y local), basta insertar en (x_tambor, y, z_tambor) rot=0 y el bore cae sobre el eje. Se eligió NMRV-090
    (2.2 kW) sobre NMRV-063/075 (1.1-1.5 kW, más ajustado a 1.5HP) porque su bore Ø35 = eje/rodamiento estándar del tambor
    (evita eje escalonado); holgado por el bajo rendimiento del sinfín. `check_interference` solo intencionales (brazo↔NMRV
    junta anti-giro, brazo↔larguero), bore libra el eje; `gravity_test` 70 a tierra, 0 caídas. **68 sólidos.**
    **Fix de proporciones del builder (2026-06-30)**: la 1.ª versión del `worm_gearmotor` hacía la caja de corona un
    **cubo 2.4×cd** (inflada ~50 %); corregido a **caja `Hw=1.7×cd` (plano X-Z) × `Hy=1.3×cd` (axial, más PLANA en el eje)**
    + brida `1.7×cd`, tapa `0.95×cd` (cotas de cuerpo del catálogo pág.101: NMRV-090 ~130-140 mm, no 216). El NMRV-090 de
    la faja bajó de 20.2M→11.4M mm³ (−44 %) al regenerar. Reposicionado (Y=605) para librar la pata de cabecera c45_2 (el
    motor Ø180 proyecta -X sobre ella) y eje acortado a y635 (no toca la tapa maciza). **Lección**: una caja de reductor
    no es un cubo — es ~1.7×cd en el plano de la corona y más plana en el eje; el motor IEC suele ser más grande que la
    caja del sinfín (es normal).
    **Motores a frame IEC real (2026-06-30)**: se ajustó `motor_d`/`motor_len` al cuerpo IEC TEFC aprox en AMBAS familias
    de motorreductores — NMRV sinfín (`31_...yaml`: IEC63→Ø120, 71→Ø140, 80→Ø160, 90→Ø175, 100→Ø195, 132→Ø260, 160→Ø315;
    largos 215-545) y helicoidal (`30_motorreductores.yaml`: MOTOR-037→IEC71, 075→IEC80, 150→IEC90). Antes estaban ~20-30 %
    chicos. **Gotcha reconfirmado**: editar solo YAML NO recarga el worker de uvicorn (vigila `.py`) — hubo que tocar
    `builders.py` para que el catálogo relea las cotas nuevas. En la faja el NMRV-090 (c682) regeneró con motor Ø195 y se
    reubicó a Y=610 (9 mm de la pata de cabecera c45_2, que el motor mayor casi rozaba); `check_interference` solo
    intencionales, `gravity_test` 70 a tierra 0 caídas.
    **BRIDA/DISCO DE REACCIÓN anti-giro (2026-06-30, corrección de diseño del usuario)**: el `c673` era un **bloque**
    (`Box`) que hacía de brazo de torque pero estaba MAL UBICADO — atravesaba el eje vivo `c670` (colisión ~2.5 cm³) y se
    enterraba en la caja. Rediseñado a la solución de manual para motorreductor de eje hueco: un **disco de reacción
    atornillado a la BRIDA de salida del NMRV** (run_script `c673`, id estable → fasteners `nmrv_brazo`/`brazo_larguero`
    sobreviven). Geometría: disco Ø160×16 coaxial con el eje, asentado sobre la cara de la brida (-Y) con **6 pernos en el
    círculo de la brida** (r≈65) + **barreno central Ø46** por el que el eje Ø35 **pasa sin tocar** (5.5 mm de holgura →
    fin de la colisión con el eje); una **pata baja al larguero** `c93` y se atornilla **POR DEBAJO del eje** (z728-768, el
    eje en z773+) dando el brazo de palanca que absorbe el par y lo transfiere al bastidor. `check_interference`: las 2
    únicas interferencias de `c673` son intencionales (`↔c682` pernos a la brida, `↔c93` pata al larguero); `gravity_test`
    70 a tierra, 0 caídas. **Lección**: el anti-giro de un shaft-mount NO es un bloque que cruza el eje — es una brida/plato
    de reacción atornillado a la salida con el barreno librando el eje y el anclaje al bastidor DESFASADO del eje (palanca).
    **PUNTAL A LA PATA + ménsulas que LAPAN (2026-07-01, corrección del usuario)**: el usuario notó 2 apoyos malos.
    (a) **`c673`**: la «pata al larguero» se HUNDÍA en el larguero (colisión 6.9 cm³) y el larguero (tubo de pared fina,
    en voladizo 300 mm más allá de la pata de cabecera) es un apoyo pobre para reaccionar el par. Rediseñado: se quitó la
    pata y se añadió un **puntal DIAGONAL** del disco a la **pata de cabecera `c45_2`** (columna maciza a piso) → triangula
    la reacción del motor directo a la columna (camino de carga corto y rígido). El puntal se rutea **por DEBAJO del larguero**
    (z<744, así libra el tubo aunque su Y lo cruce) desde el borde inferior del disco (x3795) hasta el cuerpo superior de la
    pata (x3520). Se construye orientando un `Box` esbelto con `Rotation(0, ry, rz)` donde `rz=atan2(Δy,Δx)` (rumbo) y
    `ry=-atan2(Δz,√(Δx²+Δy²))` (cabeceo) — fórmula verificada por bbox en `test_script`. Fastener `brazo_larguero`
    (c673↔c93) BORRADO, `disco_pata` (c673↔c45_2 soldadura) declarado. (b) **`c685`**: las ménsulas de chumacera tenían una
    **pared metida 3 mm en el costado** del larguero (colisión 11.2 cm³ ×2 = «apoya mal»). Rehechas a una **repisa que LAPA
    bajo el larguero** (cara superior de la repisa a 0.6 mm bajo la cara inferior del tubo → **0 colisión**, apoyo plano) +
    pestaña corta contra el alma **por debajo del eje** (z≤770 < eje 773.5, sin tocar el eje). La chumacera **apoya** en la
    repisa (coplanar, 31 mm³). **Lección**: para reaccionar par o cargar un voladizo, triangular a una **columna** (pata a
    piso) es más rígido que colgar de un tubo de pared fina; y una ménsula debe **lapar/apoyarse en cara plana**, no
    enterrar un canto en el costado del perfil. Verificado: `check_interference` solo intencionales (`c45_2↔c673` 1.7 cm³
    puntal soldado a la pata; chumacera↔repisa 31 mm³), `gravity_test` **72 a tierra, 0 caídas**. Revisión 66.
    **Follow-up**: pernos de catálogo `PERNO-M10` (hoy cilindros) + buje de goma en el anclaje.
    **REDUCCIÓN DE ANCHO 700→600 mm — reparametrización en cascada (2026-07-01)**: el usuario pidió bajar `ancho_banda`
    de 700 a 600 y que «el resto» siguiera. `larg_inner_y = ancho_banda/2 + holgura_lado` ya propagaba el bastidor
    (patas/largueros/travesaños/placas/pernos/mesa), pero MUCHAS piezas tenían valor fijo. **Regla de oro reconfirmada**:
    los comandos **`create_*` y los super-comandos aceptan `=expr`** → se ataron y CASCADEAN a futuro; los **`run_script`
    NO ven las variables del proyecto** (`NameError`) → van con valor fijo (hay que reeditarlos si cambia el ancho).
    **Atados a variable (cascada)**: `long_tambor="ancho_banda+60"` (760→660); banda `belt_out/in_*` (c111-c117)
    `height/depth="=ancho_banda"`(+2 el interior); repisas `c367/368` borde interior `=ancho_banda/2-20` (tapa la mesa);
    eje motriz `c670` `height="=635+larg_inner_y"`, `y="=(635-larg_inner_y)/2"` (−390→635, +Y fijo al NMRV); **tensor de
    cola `c412`** (super-comando) `ancho_banda="=long_tambor"` (760→660: rodillo/eje/rodamientos/soportes se angostan y los
    soportes vuelven a topar el larguero en 390); chumaceras `c686/687` `y="=±(larg_inner_y-33)"` (bore ±357, collar a 1 mm
    del larguero); rodillo de retorno `c120/c121` body `=ancho_banda`, eje `=2*(larg_inner_y-5)` (muñón sigue llegando a las
    ménsulas). **Fijos a 600 (run_script)**: tambor `c669` (`Cylinder 760→660`, bore `800→700`); ménsulas `c685`; disco+puntal
    `c673` (el puntal se re-apuntó a la pata movida — la pata `c45_2` cascó a y377-453 y el `P2` fijo del puntal ya no la
    alcanzaba); pies niveladores `c647` (`ly 460→415` = nuevo centro de placa). Verificado: 0 colisiones nuevas (solo
    intencionales: repisa↔travesaño, rodillo↔ménsula, puntal↔pata), `gravity_test` 72/0, `engineering_check` OK (flecha del
    bastidor 0.07 mm, menor por menos carga). Revisión 67. **Lección**: al reparametrizar, lo `create_*`/super-comando con
    `=expr` cascada solo; lo `run_script` hay que reeditarlo a mano (y OJO con lo que dependía de una pieza que SÍ se movió,
    p. ej. un puntal que apunta a una pata). **Follow-up**: convertir tambor/ménsulas/disco/pies a `create_*`+`=expr` para
    que un futuro cambio de ancho cascade 100%.
    **Builder `motor` rediseñado a HELICOIDAL EN LÍNEA (2026-06-30)**: la familia helicoidal (MOTOR-037/075/150/150-EH)
    dejó de ser el cubo genérico + motor perpendicular; ahora es un **motorreductor coaxial tipo SEW R / NORD**: motor IEC
    (cilindro aleteado) + ventilador + caja de bornes + campana + **caja reductora coaxial + eje de salida coaxial** en el
    extremo opuesto, con **patas** (foot-mounted). Eje común = X local. Así las 2 familias se distinguen: NMRV = sinfín a
    90° (eje hueco), MOTOR-* = helicoidal en línea (eje macizo saliente). **Gotchas resueltos** (2 iteraciones): (a)
    `Rotation(...) * Cylinder` PELADO (sin `Pos(...)` delante) da `ValueError: other must be a list of Locations` — todo
    builder debe empezar cada término con `Pos(...) *`; (b) una pieza que solo TOCA por una línea/cara tangente (la caja
    de bornes apoyada en el tope del cilindro del motor) NO fusiona → el `+` devuelve `ShapeList` (sin `.bounding_box`/
    `.volume`) y rompe `insert_component`/`place` con el mismo `ValueError` — hay que SOLAPAR 3-8 mm cada junta (ventilador↔
    motor, campana↔caja/motor, eje↔caja, bornes hundida en el cilindro). El super-comando `create_conveyor` sigue colgando
    el motor bajo el larguero (rotación 0,0,90); cambia su orientación pero no rompe (proyectos viejos: id 18). 557 tests.
    **Follow-up**: chavetero modelado en el bore del NMRV; variantes de montaje (brida B5) para ambas familias.
    **CHUMACERAS DE PIE UCP realistas + cambio en la faja (2026-07-01, a pedido del usuario «lo más realista posible»)**:
    la familia `chumaceras` era básica (`CHUM-6204/05/06` = un anillo sobre una placa plana) y la faja usaba `c671`
    (2 CAJAS con barreno hechas a mano). Rehecho el builder **`pillow_block`** a una chumacera de PIE tipo **UCP** real:
    **cuerpo fundido acampanado** (`make_revolution` recortado en Y con `&` para no salir del ancho del inserto) + **base
    de 2 patas obround con agujeros RANURADOS** + **campana del rodamiento** (cilindro eje Y) + **inserto con collar
    saliente y 2 PRISIONEROS** (set screws radiales) + **grasera** (niple) arriba; barreno del eje pasante. Marco canónico:
    eje del rodamiento a lo largo de Y, base abajo, **ORIGEN en el centro del barreno** (se inserta directo sobre el eje).
    Nueva firma `pillow_block(d,H,H1,L,J,A,N,Bi,s)` (9 cotas comerciales). Familia YAML **`UCP`** en `95_chumaceras.yaml`
    con **5 medidas comerciales UCP204/205/206/207/208** (Ø20/25/30/35/40); cotas H/H1/L/J/A/N/Bi/s **verificadas** contra
    tablas UCP publicadas (FYH/NTN/AUbearing/Mechforged, cruzadas 2 fuentes vía WebSearch/WebFetch). **Catálogo 205→207**
    (chumaceras 3→5). `carga_kg`+`weight` reales por variante. **GOTCHA build123d confirmado**: en builders todo término
    rotado empieza con `Pos(0,0,0)*Rotation(...)*...` (si no, `ValueError: other must be a list of Locations`); las piezas
    de un mismo sólido deben SOLAPAR (la base obround, el flare y la campana se solapan). **Cambio en la faja id 38**: la
    chumacera UCP de pie monta con base HORIZONTAL, pero el eje pasa junto a la cara interior del larguero (sin superficie
    horizontal debajo) → se añadió una **ménsula (repisa + pared) soldada al larguero** (`c685`, run_script, 2 lados) sobre
    la que asientan **2× `UCP207`** (`c686` +Y, `c687` −Y a rot z=180 para que el collar mire outboard) con el barreno sobre
    el eje Ø35. Cirugía event-sourced: `run_batch` (ménsula+2 UCP) → `POST /api/commands/remove` de `c671`+sus 3 fasteners
    (`eje_chumaceras`/`chum_larg_pY`/`chum_larg_nY`, juntos para no dejar refs colgando) → `run_batch` de 6 fasteners nuevos
    (eje↔chumacera contacto ×2, chumacera↔ménsula perno ×2, ménsula↔larguero soldadura ×2). Verificado: `check_interference`
    solo intencionales (ménsula↔larguero ~11 cm³ = cordón de soldadura, buen apoyo; sin colisión chumacera↔tambor/eje);
    `gravity_test` **72 a tierra, 0 caídas** (eje→chumaceras→ménsulas→largueros→patas→piso). Revisión 65. **Lección**: una
    chumacera de PIE (UCP) necesita base horizontal → si el eje corre junto a un alma vertical del bastidor, va sobre ménsula
    soldada (o usar chumacera de BRIDA UCF/UCFL, que aperna a cara vertical). **Follow-up**: prisioneros
    y pernos de base como refs de catálogo para BOM, chavetero.
    **CHUMACERAS DE BRIDA UCF/UCFL (2026-07-01, continuación pedida por el usuario)**: familia de brida para atornillar a
    una cara **VERTICAL** (eje perpendicular al plano de montaje) — lo correcto cuando el eje corre junto a un alma vertical
    del bastidor (evita la ménsula que necesita la UCP de pie). Un builder ÚNICO **`flange_bearing(d, flange, size_w, size_h,
    bolt_span, N, Bi, s)`** cubre ambas: `flange="cuadrada"` → **UCF** (brida cuadrada, 4 pernos en las esquinas) ·
    `flange="oval"` → **UCFL** (brida oval/estadio, 2 pernos en el eje largo). Reusa el inserto (collar + 2 prisioneros +
    grasera + barreno) de la UCP; marco canónico: eje del rodamiento a lo largo de Y, **ORIGEN en el barreno**, brida en +Y
    (cara de montaje), cubo+inserto hacia −Y. **GOTCHA loader**: `param_keys` lee del **variant**, NO de `specs_common` →
    `flange` debe ir en CADA variante (KeyError si solo en specs_common). Dos familias nuevas en `95_chumaceras.yaml` (misma
    categoría `chumaceras`): **UCF204-208** (cotas verificadas KG/NTN: lado 86-130, pernos 63.5-102, M10-M14) y **UCFL204-208**
    (205/206 verificadas; 204/207/208 del patrón de la serie — envolvente representativa). **Catálogo 207→217** (chumaceras
    5→15: UCP + UCF + UCFL). Verificado por render (UCF cuadrada 4 pernos + UCFL oval 2 pernos, ambas con cubo/collar/
    prisioneros/grasera). 559 tests (`test_catalog_v2.py` UCF207/UCFL207, `test_catalog_datadriven.py` conteos). La faja id 38
    sigue con UCP de pie sobre ménsula (no se re-cambió); si se quisiera el montaje más limpio SIN ménsula, una UCFL/UCF
    apernada a la cara interior del larguero sería la vía. **GOTCHA reload reconfirmado (Windows)**: uvicorn `--reload` va por
    CONTENIDO (un `touch` sin cambio no dispara), y editar solo `.yaml` no recarga; además quedó un huérfano
    `multiprocessing.spawn` (hijo de un worker muerto) reteniendo el socket :8000 → se localizó con `Get-NetTCPConnection`/
    `Win32_Process` y se mató; reinicio SIN `--reload` para estabilidad. **Follow-up**: UCFL 204/207/208 contra datasheet,
    prisioneros/pernos como refs para BOM, chavetero.
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

- **UI·Árbol del modelo rediseñado ✅ (2026-06-29)** (a raíz de «¿se puede mejorar el árbol del modelo?», como
  experto UX). El árbol (`panels/Tree.tsx`) tenía 4 problemas: nombres que **envolvían a 2–3 líneas** (con 82
  sólidos se veían ~10), el dato repetido (`50x50x2 A36`) dominaba y enterraba lo distintivo, **sin buscador**,
  agrupación **solo por comando** (plana), ojo emoji (`👁`/`—`) y la columna `cN` como ruido. Rediseño **solo-frontend
  aditivo**: (1) **filas de una línea** con ellipsis + tooltip de nombre completo (~3× más piezas visibles); (2)
  **buscador** arriba (filtra por nombre/id/referencia, auto-expande coincidencias); (3) **iconos lucide**
  consistentes (`Eye`/`EyeOff`, icono por tipo vía `iconFor`, icono por subsistema); (4) **acciones al hover**
  (Enfocar/Aislar/Eliminar) en vez del único «borrar» fijo; (5) **`cN` tenue** (solo al pasar el cursor); (6) los
  **hijos de un grupo muestran solo el sufijo** distintivo «(2)/(3)…» (la base va en la cabecera). **Agrupación por
  SUBSISTEMA** en 2 niveles (subsistema → grupo de comando → piezas): el subsistema de cada grupo se deriva, en
  orden, de (a) **super-comando** (`CMD2SUB`: take_up/drive_roller→Rodillos, weldment/frame→Estructura), (b)
  **categoría de catálogo** (`CAT2SUB`, voto dominante; usa el `catalog` ya cargado en el store), (c) **palabra
  clave del NOMBRE** (`NAME2SUB` regex: pata/larguero/travesaño→Estructura, rodillo/tambor/eje→Rodillos,
  motor/reductor→Transmisión, banda/mesa→Banda y mesa, perno/tornillo/`\bm\d`→Tornillería, etc.) — **clave para
  máquinas hechas a MANO** (esta faja: 64/82 piezas sin `component` de catálogo → antes todo caía en «A medida»), y
  (d) como último recurso el **primer token** del nombre (bucket dinámico auto-nombrado). Orden de render: ORDER
  fijo conocido → buckets dinámicos (por nº de piezas) → «A medida»/«Otros» al final. Verificado e2e en `ui-preview`
  (build prod, StrictMode-safe) sobre la faja id 38: distribución sensata (Estructura 22 · Transmisión 5 · Rodillos
  24 · Banda y mesa 7 · Tornillería 21 · Guardas 1 · «Caja»/«Brazo» dinámicos 1+1 = 82), buscador «tensor»→11,
  acciones de fila presentes, 0 errores de consola. CSS nuevo en `styles.css` (`.tree-search`/`.sub-head`/
  `.count-badge`/`.row-actions`/`.lvl1`/`.lvl2`/`.fid` tenue). **Límite honesto**: la clasificación por nombre es
  heurística (regex de palabras clave); piezas mal nombradas caen a un bucket por su 1.er token o a «A medida».
  **Colapsar todo (2026-06-29)**: botón `ChevronsDownUp` en la cabecera del árbol (`collapseAll`) que pliega de UNA
  vez TODOS los nodos (subsistemas + grupos de comando: añade todos los `sub:`/`cmd:` keys al set `collapsed`) → deja
  solo la lista de subsistemas; se deshabilita cuando ya está todo colapsado (feedback) y se rehabilita al expandir
  algo. Solo colapsar (no hay expand-all, a pedido del usuario). **Solo
  frontend** → `cd ui; npm run build` + recargar; sin reiniciar API/MCP. **Follow-up**: sección «Uniones ·
  cinemática» (juntas/mates/fasteners/grounds) como nodo del árbol + navegación por teclado (era el tier 3 del plan).

- **UI·Scrollbars temáticos + árbol redimensionable ✅ (2026-06-29, Fase 1)** (a raíz de «los scroll bar son feos,
  no combinan; quita el horizontal del árbol y deja redimensionar ese lado»). Solo-frontend. (1) **Scrollbars
  finos integrados** (antes TODAS nativas): `::-webkit-scrollbar` (thumb `--panel3`→`--muted` al hover, track
  transparente, 10px) + `scrollbar-width:thin; scrollbar-color` (Firefox), globales en `styles.css`. (2) **Sin barra
  horizontal en el árbol**: `.tree { overflow: hidden auto }` (y `.kin-joints`) — causa raíz: con `overflow-y:auto`
  el otro eje (`visible`) se computa `auto` por spec → cualquier desborde sub-píxel sacaba la barra. (3) **Árbol
  redimensionable por el borde**: nuevo `panels/Workspace.tsx` con `useSplitter({axis:"x", storageKey:"apolo.tree.w"})`
  (mismo patrón que RightDock/BottomDock) → columna `--tree-w` en `.workspace` + `SplitHandle`. *Nota*: la Fase 2
  (Dockview) sustituyó este `Workspace`/splitter manual, pero los scrollbars y el `overflow` son permanentes.

- **UI·Sistema de ventanas acoplables estilo VS 2022 (Dockview) ✅ (2026-06-29, Fase 2)** (a raíz de «como VS 2022:
  acoplar paneles en varios lados, redimensionar por borde, mover, pestañas»; investigado en web). Motor: **`dockview-react`
  7.0.2** (MIT, cero deps de terceros, tema por CSS vars) — elegido sobre rc-dock/react-mosaic/flexlayout tras
  comparativa (cobertura VS + licencia + mantenimiento). Alcance de esta iteración: **acoplar + redimensionar +
  pestañas + persistencia** (sin flotantes ni auto-hide; Dockview los soporta → follow-up). Arquitectura:
  - NEW `dock/DockShell.tsx`: `<DockviewReact>` ocupa la fila workspace; registry id→componente para
    viewport/tree/properties/chat + los 7 paneles-herramienta (cada uno envuelto en `.dock-pane` que llena el panel,
    conservando su scroll interno). Tema base `themeAbyss` remapeado a los tokens de Apolo vía
    `.apolo-dock .dockview-theme-abyss { --dv-color-abyss*: var(--bg/--panel/--accent…) }`. **onReady**: restaura
    `localStorage["apolo.layout.v1"]` con `api.fromJSON` (try/catch → si falla, layout por defecto), persiste con
    `onDidLayoutChange` (debounce 300ms → `api.toJSON()`), y sincroniza `dockPanels` al store (resaltado de StatusBar).
  - NEW `dock/dockApi.ts`: singleton del `DockviewApi` + helpers `togglePanel`/`resetLayout`/`buildDefaultLayout`/
    `lockViewport`/`syncDockPanels`. Layout por defecto: **viewport (centro) · árbol (izq) · propiedades+chat (pestañas, der)**.
  - **VIEWPORT = centro fijo bloqueado** (`vp.group.locked=true` + `tabComponent:"locked"` sin botón cerrar +
    `renderer:"always"`) → **nunca se re-monta** (verificado: tras docking/reset el `<canvas>` es el MISMO nodo →
    contexto WebGL intacto). **GOTCHA crítico resuelto**: `resetLayout` hacía `api.clear()`, que destruía el viewport →
    su cleanup de three.js lanzaba `this.traverse is not a function` (bug LATENTE, nunca antes ejecutado porque el
    viewport jamás se desmontaba) y el crash en el unmount vaciaba el dock. Fix: `resetLayout` cierra todo MENOS el
    viewport y re-acopla alrededor (no lo destruye). El bug de `dispose` queda latente (inalcanzable: la pestaña no
    cierra y no se desmonta) → follow-up blindarlo.
  - Migración del shell: `App.tsx` renderiza `<DockShell/>` (grid de 4 filas, sin la del bottom-dock); **borrados**
    `RightDock.tsx`/`BottomDock.tsx`/`Workspace.tsx`; el store perdió `bottomPanel`/`setBottomPanel`/`showHistory`/
    `toggleHistory` y ganó `dockPanels`/`setDockPanels`; los 7 paneles dejaron el auto-gate `if(bottomPanel!==x)return null`
    y refrescan **al montar** (Dockview los monta solo cuando están presentes; `renderer` por defecto `onlyWhenVisible`);
    StatusBar conmuta vía `togglePanel` + botón **«Restablecer layout»**. Modales/overlays siguen fuera del dock.
  - Verificado e2e en `ui-preview` sobre faja id 38: layout por defecto (Árbol·Vista 3D·Propiedades+Asistente IA en
    pestañas), toggle de StatusBar acopla/cierra paneles con resaltado reactivo, **resize por sash** (247→327px),
    **persistencia** (toJSON guardado; tras recargar restaura «Cinemática»), pestaña del viewport SIN cerrar, reset
    preserva el canvas (mismo nodo), 0 errores de consola. **Límite honesto**: el screenshot del capturador agota
    tiempo por el rAF continuo del viewport (verificado por DOM, no por imagen); drag-to-dock con guías (mover una
    pestaña a otra zona) es función nativa de Dockview no simulable por script — probar en vivo. **Solo frontend +
    1 dependencia** → `cd ui; npm run build` + recargar; sin reiniciar API/MCP. **Follow-ups**: ventanas flotantes,
    auto-hide/pin (Dockview los trae), blindar el `dispose` del viewport.
  - **Fix de fila muerta + limpieza de CSS (2026-06-29)**: tras la migración quedaba una **barra muerta de 28px**
    entre el dock y la StatusBar. Causa: `.statusbar { grid-row: 5 }` (resto del layout viejo de 5 filas) apuntaba a
    una fila implícita, dejando VACÍA la fila 4 (`--status-h`) del nuevo grid de 4 filas. Fix: `.statusbar` →
    `grid-row: 4`; el dock recuperó esos 28px (gap dock↔status = 0). **Lección**: los `grid-row` numéricos explícitos
    son frágiles al cambiar el `grid-template-rows` — al quitar una fila hay que reindexar los hijos posteriores.
    Borrado además el CSS muerto de la migración: `.bottomdock`/`.dock-head`/`.dock-body` y `.right-dock` (sus
    componentes ya no existen; verificado que no se usan en ningún `.tsx`).
  - **Fix overlay del viewport vs ViewCube (2026-06-29)**: la barra de vistas/herramientas (`.viewport-overlay`:
    ISO/Frente/Lateral/Planta/Alambre/Mover/Rotar/Medir/Sección) estaba en `top:8 right:8` — la MISMA esquina donde
    `viewcube.ts` dibuja el mini-cubo (top-right del canvas, 96px + margen 10, vía `setScissor`/`setViewport`) → los
    botones semi-opacos TAPABAN el cubo. Fix: `.viewport-overlay` → `left:8px` (arriba-IZQUIERDA), dejando el ViewCube
    despejado en su esquina convencional (Fusion/Inventor/SolidWorks). El cubo siempre se dibujaba; solo había que
    liberarle la esquina (sin tocar su código). Top-left estaba libre (status=abajo-izq, rotate-panel=arriba-centro).
    Verificado por DOM (`cubeZoneClear:true`). Solo-CSS.

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
- ~~**`engineering_check` no detecta la faja de banda**~~ ✅ RESUELTO 2026-06-29 (ver "Validación de ingeniería
  universal" abajo): la detección se enriquece con las VARIABLES del proyecto + nombres (reconoce el motor
  a-medida, el tambor, las rpm, el eje y el bastidor de tubo).
- ~~**Ampliar análisis**: deflexión de viga del bastidor, voladizo de tambores~~ ✅ 2026-06-29 (flecha del
  larguero como viga simplemente apoyada + flexión del eje del tambor). Follow-up: voladizo real (cantilever)
  del eje motriz hacia el reductor; leer densidad/material de catálogo en vez de heurística por nombre. `[V1]`

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

## V5.2b — `insert_project`: proyecto dentro de proyecto (2026-07-02)

Cierra el ítem (2) del Tier 1: layouts multi-máquina. Comando nº 46, construido
directamente sobre los grupos de V5.2.

**Decisiones de diseño** (el detalle operativo vive en CLAUDE.md § Sub-ensamblajes):

- **Snapshot embebido, NO enlace vivo**: la capa API materializa `project_id` →
  attachment (.apolo del origen, content-addressed SHA256[:16]) igual que
  `/api/import`. Tres doctrinas a la vez: el `.apolo` del layout es AUTOCONTENIDO,
  `commands/` no conoce `projects.py`, y los tests no tocan SQLite. Refresh explícito
  = `edit_command {"attachment": ""}` (mismo hash si el origen no cambió → no-op).
- **Sandbox replay** (`doc/subproject.py`): `from_apolo_bytes(regenerate=False)` +
  pisar los `set_variable` con los overrides ANTES del único regenerate → namespaces
  de variables aislados por construcción; `"=expr"` en overrides resuelve contra el
  ANFITRIÓN (resolve_params es recursivo — gratis). Caché por (digest, overrides),
  cap 8 FIFO: N instancias iguales = 1 replay. `MAX_DEPTH=3` (los snapshots anidados
  son autocontenidos; ciclo A-en-A imposible por copia + guard en la API).
- **Emisión prefijada**: fids y command_ids sintéticos `{cmd}_{orig}` (preservan la
  exclusión intra-comando de check_interference y la membresía de grupos); juntas y
  rail-constraints viajan con origin/axis transformados; fasteners con su
  dimensionamiento; grounds bajo `keep_grounds` (editable); grupos internos del origen
  = grupos REALES de A anidados `"{name}/{grupo}"` bajo el raíz. **Mates BAKED**: la
  pose ya la resolvió el sandbox; re-registrarlos exigiría transformar refs
  declarativas (frágil) y pagar solve_mates por instancia en cada regenerate, para
  nada — la instancia es rígida y "editar B se hace en B".
- Dispatch: flag nuevo `wants_all` (firma kwargs total), sin tocar `wants_groups`.
- Fixes de paso en document.py: `preview()` no copiaba attachments (afectaba también
  a previsualizar import_step) y el regenerate pisaba `feat.material` de executor.
- Cero endpoints nuevos, cero tools MCP nuevas, cero cambios de UI (schema-driven).

**Verificación**: 30 tests nuevos (706 total) — prefijado, overrides, transform del
grupo raíz con juntas, keep_grounds, undo/redo, round-trip autocontenido, recursión
y MAX_DEPTH, caché e instancing de mallas, colisión de nombres con rollback, API
(materialización con FakeStore, refresh, auto-referencia 400, batch, isolate por
nombre, preview sin mutar). E2E real: `layout-planta-demo` (id 53) = 2 instancias de
`faja-paqueteria-4m` (id 38) + mesa transfer a-medida; 149/149 sujetas (grounds
importados), 0 interferencias entre instancias, gravity limpio, BOM `by_group` con
subtotales por instancia/sub-ensamblaje, manual paginado por grupos, refresh no-op
verificado por hash. Hallazgo del E2E: el 38 es solo PARCIALMENTE paramétrico (el
conjunto motriz usa literales `Pos(3806,…)` en run_scripts → flota al encoger
`largo_total` — mismo comportamiento editando la variable en el propio 38; queda
task pendiente de atarlo a variables). De paso: `GET /api/bom` ganó `by_group` (la
función ya lo soportaba; el endpoint no lo exponía) y el filtro `diff` del MCP ahora
matchea command_ids sintéticos por prefijo.

## V5.1 — Croquis robusto: PlaneGCS (2026-07-02)

Cierra el ítem (1) del Tier 1 — el eslabón más débil del kernel (croquis 3→5).

**La premisa de F11 quedó obsoleta**: en 2026-06-11 se eligió el solver scipy propio
porque PlaneGCS no tenía wheels Windows fiables. Hoy `planegcs` 0.8.0 (PyPI,
2026-06-22) trae wheel cp313-win_amd64 de 397 KB (LGPL-2.1, bindings del solver del
Sketcher de FreeCAD). El spike GO/NO-GO (5 criterios) pasó completo: exactitud +
subrestringido cerca del boceto, slot con tangencias exacto, redundante detectada con
tag, conflictivas identificadas, DOF correcto, y la cadena de 24 puntos con ángulos
(donde scipy cae en mínimos locales) resuelta en 5.6 ms. Nota API: `SolveStatus.Success`
y `Converged` son AMBOS "resuelto" (como en FreeCAD).

**Arquitectura**: `sketch_solver.py` = FACHADA (SketchError, TOLERANCE, _index_sketch,
describe_constraint, _pick_engine) → `sketch_gcs.py` (default) | `sketch_scipy.py`
(fallback VIVO: sin wheel la instalación no rompe; override `APOLO_SKETCH_SOLVER`;
los tests parametrizan AMBOS motores → el fallback se ejercita en cada CI). El
veredicto `ok` lo da un VERIFICADOR geométrico común en sketch_gcs (mismas fórmulas
y escalas que scipy) — independiente del status del solver. `coincident` no fusiona
params (la salida necesita ambos ids; sketch_geom hace union-find aguas abajo);
`fix` pasa de suave (peso 10) a exacto (params fijos); arcos vía `add_arc_cse` con
arc-rules automáticas (sustituyen la `_arc_equal` implícita); arco cw = canónico ccw
con start/end intercambiados.

**Salida ampliada (aditiva)**: `dof` (grados de libertad restantes), `redundantes` y
`conflictivas` (descripciones legibles vía tag→describe_constraint). 6 tipos nuevos
SOLO-GCS: tangent (línea↔curva, curva↔curva), symmetric, equal_radius, concentric,
midpoint, distance_point_line; `radius` acepta ARCOS. UI: herramienta Arco (3 clics,
render por polilínea muestreada), 6 botones nuevos, panel DOF/redundantes/conflictivas
(verificado en preview por DOM). SKETCH_DOC actualizado (fuente única agente/UI).

**Bug pre-existente corregido** (sketch_geom.py): si `_chain_loop` recorre un arco EN
REVERSA, el `ccw` efectivo debe invertirse — sin el fix el punto medio del
ThreePointArc caía del lado equivocado (tapa abombada hacia DENTRO). Nunca se vio
porque el único test con arco encadenaba hacia adelante.

**Verificación**: los 13 tests de test_sketcher.py INTACTOS y verdes en ambos motores
(contrato de compatibilidad); +22 en test_sketch_gcs.py (tangencias/slot con área
analítica, arco cw, simetría, concéntrico, midpoint, dist punto-línea, radius de arco,
DOF 0/1/2, redundante, conflictiva, zigzag de 24 pts con dof=0, tipo nuevo en scipy →
error claro, endpoint con claves nuevas, extrude del slot). 728 tests. Ningún proyecto
guardado contenía comandos sketch_* (riesgo de compatibilidad .apolo = cero,
verificado offline contra la BD). E2E vivo por MCP: `biela-colisos-demo` — test_sketch
iterativo devolvió ok/dof=0/sin redundantes a la primera; extrude 84 704.6 mm³ =
analítico exacto (120·50 + π·25² − 2π·12²)·12; render limpio. Pendientes declarados:
arrastre en vivo con soft-constraints, elipses/B-splines, cotas driven.

## V5.3 — Modelado directo básico: delete_faces + push_face (2026-07-03)

Cierra el ítem (3) del Tier 1: el STEP de fabricante deja de ser un ladrillo.

**Spike GO/NO-GO** (patrón V5.1): Defeaturing GO (fillet/barreno/STEP round-trip
curados a volumen exacto en ~40 ms; gotcha: cara incurable → OCCT devuelve el sólido
INTACTO sin error — se detecta comparando nº de caras + volumen). Prisma+booleana GO
(± exactos, cara con agujero extiende el agujero, STEP con caras REVERSED manejado
con `BRepClass3d_SolidClassifier` — nunca `normal_at` a ciegas). `SetOffsetOnFace`
NO-GO definitivo (StdFail_NotDone o sólido vacío en todas las variantes de OCP
7.8.1) → sin `offset_face`; resize de barreno = receta delete+redrill; pendiente.

**Kernel** `kernel/direct.py` (wrappers OCCT puros, frontera de topology.py):
`remove_faces` (Defeaturing + validación + detección de no-op), `push_pull` (solo
PLANE; prisma comparte el borde exacto de la cara → booleana robusta; semántica
honesta: paredes rectas), `expand_tangent` (BFS por aristas compartidas). Lección de
diseño descubierta por los tests: dos tramos de fillet que se encuentran en una
esquina viva NO son G1 entre sí → la cadena expande por tangencia **o mismo radio**
(BRepAdaptor cylinder/sphere/torus-menor), y las caras PLANAS nunca entran (el fillet
es tangente a sus caras base por construcción — sin ese corte la cadena se fuga al
sólido entero). Comandos `delete_faces` (flag `tangentes`) y `push_face` (±distance
con `=expr`), patrón fillet (mutación en sitio + make_unique → mates/juntas
sobreviven; guarda contra mode="todas"). Cero cambios de UI (SelectorField universal
con picker), cero tools MCP.

**Verificación**: 13 tests nuevos (741 total) — volúmenes analíticos SIEMPRE (nunca
conteos de caras: el resultado de Defeaturing puede variar entre versiones OCCT),
cadena tangente desde una cara, errores accionables, paramétrico `=h_extra`,
roundtrip .apolo con STEP (el log re-resuelve el selector), instancing, API HTTP.
E2E vivo (`pieza-proveedor-demo`): soporte nativo con fillet r6 + 2 barrenos →
export STEP → import (volumen idéntico 138 636.4) → cirugía en UN batch: quitar el
anillo de fillet (tangentes desde 1 cara), MOVER un barreno (delete+redrill) y
alargar con `push_face distance="=extra"` → 377 716.8 mm³ = analítico exacto; editar
la variable 25→10 re-ejecutó todo el log de modelado directo → 236 073.0 = exacto.
Fuera de alcance declarado: move_face real, push-pull con extensión de caras
inclinadas, offset de B-splines, hole recognition.

## V5.4 — Ajustes y tolerancias ISO 286 en cotas y asientos (2026-07-03)

Cierra el ítem (4) del Tier 1: un plano de Apolo ya sirve para MECANIZAR y el
agente RECOMIENDA/VERIFICA los ajustes de asiento.

**Decisión tablas-vs-fórmulas**: tablas transcritas de ISO 286-1 (IT5–IT11 ×
13 franjas 1–500 mm + desviaciones fundamentales de eje g/f/h/k/m/n/p) y los
AGUJEROS derivados con las reglas exactas de la norma (H→EI=0; G/F espejo;
JS ±IT/2; K/M/N/P grados 6–7 → ES = −ei + Δ, Δ = ITn−IT(n−1) — verificada
contra 5 valores publicados independientes). Sin fórmula i=0.45·∛D (redondeos
frágiles). 22 spot-checks parametrizados cubren todas las letras y franjas. El
bore de rodamiento/inserto NO es ISO 286: ISO 492 clase Normal (0/−t).

**Dónde vive el fit**: taladros en `drill_hole.fit` ("H7", validador exige clase
de agujero; anotación pura — geometría al nominal); ejes por NOMBRE («Eje motriz
Ø35 h7», la convención ya bendecida del grado de material); catálogo `bore_fit:
H8` en el NMRV. **Planos**: la capa API arma el mapa Ø→fit automático (drill_hole
∪ nombres) + override `hole_fits` del spec; `_hole_callouts` matchea por distancia
≤0.11 (el Ø de vista viene redondeado a 0.1) y rotula CON límites: "Ø35 h7
(0/-0.025)". Retro byte-idéntico sin fits. **Asientos**: `_fit_checks` en
report.py — pares por fastener/junta/mate concéntrico + Ø nominal coincidente;
`SEAT_RECOMMENDATIONS` por tipo de montaje (inserto UC → h7 desliza, fijan
prisioneros; prensado anillo giratorio → k6); estados honestos (sin fit = aviso
con receta; k6 en inserto = ERROR con recomendación); hipótesis de montaje
declarada en el detalle. Tool `get_fit` + `GET /api/fits` (64→65). Expresiones
`=fit_max(...)` y GD&T declarados FUERA.

**Verificación**: 43 tests nuevos (784 total). E2E vivo en la faja real (id 38):
eje motriz renombrado «Ø35 h7» → regla "asiento ISO 286 · UCP207" OK con calc
(juego −12…+25 µm, transición); cambiado a k6 → ERROR "el inserto UC debe
DESLIZAR… cambia a h7"; lámina del eje+chumaceras con callout "Ø35 h7 (0/-0.025)"
automático desde el nombre; h7 restaurado (es el fit correcto — queda declarado).
BONUS: la regla detectó sola los 6207 del tensor de cola y avisa que su eje no
declara ajuste — la detección generaliza. Matiz honesto documentado: la hipótesis
por categoría (rodamientos → anillo giratorio) no distingue el tensor de EJE FIJO
(ahí el anillo interior es estacionario → g6/h6, no k6); como es AVISO con la
hipótesis declarada, no engaña — refinamiento pendiente (leer "eje fijo" del
nombre).

## V5.5 — Chapa avanzada: multi-pliegue, cutouts en pestañas, K por material (2026-07-03) — TIER 1 COMPLETO

Último ítem del Tier 1. `create_sheet_metal` gana `flaps: list[FlapSpec]` (pestaña por
lado con `child` de un nivel — C/Z/hem, interior/exterior — y `holes`/`cutouts`
propios) y `k_factor: float | None` (None = por material: acero 0.40, inox 0.45,
alu/latón 0.35, resuelto en la capa API con `resolve_material` — patrón del BOM).

**Decisión clave — convención u,v**: `u` corre a lo largo del pliegue ALINEADA AL EJE
MUNDIAL (0=centro, como los holes de base — sin pitfalls de espejo); `v` se mide desde
el BORDE LIBRE de la pestaña, la única métrica en que el 3D plegado y el desarrollo
coinciden EXACTO sin conocer el radio. Proyección al flat: offset del padre desde su
línea de pliegue = `BA_p + (altura−OSSB_p) − v`; del hijo = `strip_total − v`. Feature
que invade la zona de pliegue → ValueError con el dominio válido en el mensaje.

**Arquitectura**: un solo camino — la vía simple (lados/altura/angulo) se NORMALIZA a
flaps; el muro se construye canónico en el marco local (hijo pivota sobre el borde
libre, cutters de holes/cutouts restados en local) y UNA transformación rígida por
lado lo coloca. Retro verificada con test de igualdad EXACTA (ring/lines/circles) del
flat clásico vs su equivalente en flaps, y acero=0.40 == el default viejo 0.4 (el
único proyecto guardado con chapa resuelve a acero → blank byte-idéntico). El pliegue
hijo queda vivo (sin fillet — fallback ya aceptado en G2; el desarrollo lleva su radio
igual). Fuera de alcance: child >1 nivel, hem 180°, ingletes/alivios, cutouts en base.

**Verificación**: 16 tests nuevos (800 total) con anclas numéricas a mano (blank C
197.79646; pliegue hijo by1+36.39823; holes padre/hijo; esquinas del cutout). E2E vivo
por MCP en `guarda-banda-demo`: guarda en C 600×180 e=2, pestañas h=80 con hem h=12
interior, 3 ventilaciones 60×20 + 2 barrenos Ø9 de montaje; DXF exportado y parseado
con ezdxf: blank 600×349.59292 EXACTO vs cálculo a mano, cutouts/círculos/4 líneas de
pliegue en posición exacta; K vivo: `set_material` inox → blank 350.22124 (delta
+0.62832 = 4·Δk·t·π/2, exacto) y label «K=0.45»; sección del render confirma el perfil
C con hems. Revisión 70 guardada.

## V5.6 — FEA estático lineal integrado (2026-07-03) — primer ítem del Tier 2

La memoria de cálculo pasa de solo fórmulas de norma a ESFUERZOS REALES: tool
`fea_static` (66ª) analiza UNA pieza con malla tetraédrica P2 + elasticidad lineal y
devuelve σ_vm máx con ubicación, desplazamiento, FS = σy/σ_vm, hipótesis declaradas y
un FRINGE von Mises en PNG (el agente VE dónde está el esfuerzo).

**Stack (spike GO en 5/5 criterios)**: gmsh 4.15.2 (wheel win_amd64, malla desde STEP
con su OCC embebido — puente SIEMPRE por archivo, nunca punteros nativos entre builds
de OCCT) + scikit-fem 12.0.2 (solver puro Python BSD, solo numpy/scipy) + meshio.
sfepy y CalculiX = NO-GO: sin wheels de Windows (la trampa PyBullet de V4). Spike:
viga en voladizo 100×10×10 → δ = 0.2005 mm vs 0.2000 analítico (err 0.3 %), σ_vm a
media luz 30.3 vs 30.0 MPa (1.1 %), 10 ciclos gmsh initialize/finalize estables, STEP
real de Apolo malla OK. Los P1 tienen shear-locking a flexión → **ElementTetP2**
obligatorio (el spike lo demuestra).

**Arquitectura**: paquete propio `core/apolo/fea/` (mesher/solver/static/fringe) con
extra pip `[fea]` y patrón `_require_fea` (espejo de MuJoCo). Patrón DOS LOCKS: bajo
STATE_LOCK se resuelven material/selectores de caras (FaceDesc: centro+área puros) y
se exporta el STEP; el mallado+solve corre FUERA (solo `FEA_LOCK`, gmsh es
single-instance global) → el análisis no serializa al server. Match cara OCCT ↔
superficie gmsh por centro (1e-3·diag) + área (±1 %); sin match → 400 con candidatas.
Persistencia: metadato `Document.fea` (manifest, como motion/requirements) con
`volumen_mm3` → `_fea_rules()` inyecta la página en /api/checks y la memoria, y si la
geometría cambió >0.1 % degrada a AVISO "re-ejecutar". `has_yield()` nuevo: material
sin σy tabulado exige `yield_mpa` explícito (caer a 250 en silencio = mentir en el FS).

**Gotchas cazados**: `gmsh.initialize(interruptible=False)` obligatorio (instala
handler de SIGINT y los endpoints sync de FastAPI corren en threadpool → 500 "signal
only works in main thread"); la fuente de VTK no tiene 'σ' (títulos ASCII); paredes
delgadas disparan la cuenta de tets.

**Verificación**: 15 tests (815 total) — voladizo anclado, tracción 25 MPa/0.0125 mm
±3 %, presión≡compresión, peso propio vs qL⁴/8EI, cap de tets, 400 sin deps (corre
SIEMPRE con monkeypatch), staleness, manifest round-trip, fringe PNG cacheado sin
re-solve. E2E vivo en la faja id 38: pata HSS 76.2×76.2×3 con F=800 N (masa real
325.5 kg + carga viva repartida en 6 patas) + peso propio → σ_vm 1.5 MPa, δ 0.0032 mm
(≡ FL/EA analítico 0.0031), FS 170 "ok" (a la pata la gobierna el PANDEO, no el
esfuerzo — la regla de Euler ya lo cubre aparte); fringe correcto (compresión uniforme
+ concentración en la base); memoria PDF con la verificación "14. FEA estático lineal
· Pata A36 OK" (fórmula/sustitución/FS/hipótesis). Nota de rendimiento: el HSS de
pared 3 mm costó 112 s (14.6k tets P2) — `mesh_size_mm` es el control; documentado.

## V5.7 — Roscas: cosméticas en plano + specs BOM (2026-07-03)

El defecto de entregable más frecuente del Tier 2: un taladro roscado salía como
"Ø8" a secas (el taller no sabía que iba machuelado) y el 3D era incorrecto (el
agujero pre-machuelado debe ser la BROCA Ø6.8). `drill_hole` gana `thread`
("M8", "M10x1.25"): el 3D taladra a la broca de machuelado PUBLICADA (DIN 336 —
para pasos finos difiere de d−p: M10×1.25 → 8.8, no 8.75), `diameter` se ignora
documentado, y fit⊕thread son excluyentes (sistemas de tolerancia distintos; la
rosca interior va 6H fija).

**threads.py** (patrón fits.py, puro): COARSE M3–M36 + FINE comunes,
`parse_thread` (normaliza "m8x1.25"→"M8" porque 1.25 ES el grueso),
`thread_spec` (área resistente REUSA la tabla ISO 898-1 de bolts.py — fuente
única; el resto por As=(π/4)(d−0.9382p)², verificado <1 % contra la tabla),
`format_thread_label` → "4×M8 - 6H (broca Ø6.8)".

**Plano**: `SheetModel` ganó la primitiva `Arc` (no existía — solo
Line/Label/Circle/Polygon/Image) con render en los 3 exportadores: SVG path A
fino 0.25 (el flip h−y PRESERVA la orientación visual → sweep=0), DXF capa
nueva ROSCA (ACI 3, lineweight 13 — trazo fino ISO 6410), PDF patches.Arc. El
cosmético es el arco de 3/4 de vuelta (0→270°) al Ø NOMINAL sobre cada círculo
de broca. Mapa automático `_hole_thread_map` (espejo de `_hole_fit_map`) +
override `hole_threads` en el drawing spec; en `_hole_callouts` thread se
evalúa ANTES que fit; kwargs nuevos default None → firmas y tests V5.4
INTACTOS. La CÉDULA del juego gana filas de machuelos vía `_thread_schedule`
(agrupa por designación con piezas y norma) y se FUERZA aunque no haya herraje
(la lista de machuelos es dato de compra/taller). `GET /api/threads` para
consulta; MCP sin tool nueva (run_command cubre la escritura — el executor
resuelve la broca solo).

**Verificación**: 31 tests nuevos (846 total; retro fits/drawing intactos) con
las 16 brocas publicadas parametrizadas. E2E vivo por MCP en
`placa-roscada-demo`: placa 150×100×15 con 4×M8 + Ø20 H7 — volumen quitado
6891.4 vs 6891.6 mm³ teórico (broca Ø6.8 EXACTA); SVG con ambos callouts
("4×M8 - 6H (broca Ø6.8)" y "Ø20 H7 (+0.021/0)" conviviendo); DXF con 4 ARCs
r=2.0 (esc 1:2) 0→270° en capa ROSCA; juego de planos con página CÉDULA
forzada: "M8 · Rosca interior M8 - 6H (broca Ø6.8) · rosca · 4 · Placa de
montaje A36 · ISO 262"; GET /api/threads 200/400 con lista de soportadas.
Revisión 71. Pendiente declarado: coherencia fasten size ↔ taladro roscado.

## V5.8 — Weldments con ingletes reales (2026-07-03)

El pendiente G3 de larga data: `create_weldment`/`create_frame` construían las
esquinas a TOPE y la lista de corte no decía nada del ángulo — un taller que
fabrica un marco visto lo rehace a 45°. Parámetro nuevo `esquinas:
"tope"|"inglete"` con default "tope" RETRO-SEGURO (los logs guardados regeneran
byte-idéntico; los 16 tests históricos quedaron intactos, con test candado).

**Decisión geométrica clave**: el corte es el plano BISECTOR de los dos miembros
pasando por el NODO (`library/miter.py`, puro) — ambos comparten exactamente el
mismo plano (casado perfecto), generaliza a cualquier θ/φ, y trae una propiedad
ancla EXACTA para tests: como el plano pasa por un punto del eje y el centroide
de la sección está en el eje, **V(miembro ingleteado) = A·span** para cualquier
ángulo (verificado a 0.0000 % en el smoke). El miembro se construye en el marco
local (extrusión Z, tools Box 3·L al bisector) ANTES del place; `base_key` con
formato propio `|mtr|α@φ|` jamás colisiona con un recto. `direction_frame`
extraída de `direction_to_euler` (kernel/matrix) = fuente única del frame local
para que el azimut del corte case con la colocación.

**Construcción del weldment caja** (documentada en el description = montaje):
marcos superior e inferior picture-frame a 45° (miembros a longitud EXTERIOR =
ancho/fondo — la punta cae sola en la esquina porque los nodos son las
intersecciones de centrolíneas) + 4 postes A TOPE ENTRE los marcos (alto−2·sec)
+ anillos intermedios a tope (soportes ocultos). `frame_from_edges`: bisectriz
solo en nodos de GRADO 2; colineal (tol 2°) → corte recto en el nodo; α>75° o
grado ≥3 → tope (coping fuera de alcance). `Feature.miter` → BOM ("Perfil 40x40
L=800 mm ∠45°/45°", clave de agrupación con el ángulo para no mezclar con
rectos) + lista de corte (campos corte/angulo_1/angulo_2, celda "800×… ∠45°/45°"
en el juego, 2 columnas nuevas al final del CSV). `cut_length` pasa a significar
longitud EXTERIOR en ingleteados (lo que el taller corta y compra).

**Verificación**: 13 tests nuevos (859 total) — candado retro, BOM inglete
4×800∠45/45 + 4×600∠45/45 + 4×820, ancla V=A·760==A·(800−40), bbox del conjunto
EXACTO 800×600×900, intermedios siguen a tope, no-interferencia (los planos
compartidos cara-cara los excluye same_command_pairs), schema enum, cercha
triangular con α por fórmula desde las direcciones (60° en el fixture 1000/800),
grado 3 → tope, colineal → recto con contacto exacto en el nodo. Hallazgo
lateral: el perfil T-slot siempre descompuso en 5 sólidos (núcleo+aletas) en
cut_list — comportamiento histórico, no regresión. E2E vivo por MCP en
`bastidor-inglete-demo` (revisión 72): render del marco picture-frame con los 4
ingletes visibles y de la cercha con bisectrices 60°; interferencias vacías; BOM
y juego de planos con ∠45°/45°.

## V5.9 — Export DWG (2026-07-03)

El entregable "político": los clientes AutoCAD piden DWG, no DXF. No hay writer
DWG en pip; la vía del ecosistema no-Autodesk (FreeCAD incluido) es el ODA File
Converter (gratuito, instalación manual — el usuario lo instaló en la sesión:
27.1.0) invocado por `ezdxf.addons.odafc`, que ya venía con el ezdxf 1.4.4.

**`drawing/dwg.py`** (patrón de dependencia externa opcional, como MuJoCo/FEA):
`_discover()` cubre el gotcha real — el instalador de ODA usa carpeta VERSIONADA
(`C:\Program Files\ODA\ODAFileConverter 27.1.0\`) y el default de ezdxf apunta a
la carpeta sin versión → glob de `ODA\*\ODAFileConverter.exe` + set de
`ezdxf.options` (la más nueva si hay varias). Sin conversor → `DwgError` amable
con la URL de opendesign.com (400 en la API). `dxf_to_dwg_bytes` convierte por
archivos temporales con un Lock propio (proceso externo, una conversión a la
vez); default R2018 = AC1032 (AutoCAD 2018+).

**Superficie**: `format="dwg"` en el drawing por intención (la tool MCP `drawing`
lo pasa tal cual — CERO tools nuevas), `GET /api/sheetmetal/{id}/flat.dwg`
(desplegado de chapa para el taller AutoCAD) y `GET /api/drawingset.dwg` = ZIP
con un DWG por lámina (DWG no es multipágina; decisión declarada). Solo
docstrings en MCP.

**Verificación**: 9 tests (868 total) — contrato SIEMPRE (400 con
"opendesign.com" en spec/flat/set sin ODA, descubrimiento de carpeta versionada
con árbol fake forzando la ruta inexistente primero) + conversión real (magic
AC10, round-trip `odafc.readfile` con capas). E2E vivo por MCP en
bastidor-inglete-demo: `drawing {format:"dwg"}` → 115 KB AC1032; round-trip →
las 7 capas de Apolo sobreviven (VISIBLE/OCULTA/MARCO/COTAS/EJES/CORTE/ROSCA) y
3073 entidades; `drawingset.dwg` → ZIP con 20 láminas DWG todas AC1032;
`flat.dwg` de la guarda de chapa → 200 AC1032. Curiosidad de la sesión: los
tests "reales" pasaron a la primera porque el usuario instaló ODA mientras se
escribía el código — el test del árbol fake hubo que blindarlo contra un ODA
real presente (apuntar primero a ruta inexistente para forzar el glob).

## V5.10 — Normas del vertical: memoria NORMATIVA (2026-07-03) — primer ítem del Tier 3

Las reglas de conveyor pasaban de honestas a defendibles: ahora citan NORMA. El
matiz técnico que gobierna el ítem: **ISO 5048/DIN 22101 aplican a banda sobre
RODILLOS (idlers, f≈0.02 + coeficiente C(L))**; una banda sobre CAMA deslizante
—la construcción de la faja 38— se rige por fricción de deslizamiento, y el
μ=0.33 que ya usábamos ES el factor slider-bed que publica CEMA. El método se
elige POR CONSTRUCCIÓN (señal `soporte` derivada del modelo: pieza cama/mesa →
CEMA; rodillos portantes → ISO 5048), así los números históricos de la faja NO
cambian — solo ganan cita.

**`engineering/iso5048.py`** (patrón fits: docstring con norma + tablas +
funciones puras): tabla C(L) con los valores ampliamente publicados (C(80)=1.92
… C(1000)=1.09; la zona L<80 m marcada como interpolación REFERENCIAL — en
fajas cortas dominan las resistencias secundarias), resistencia principal
F_H = f·L·g·(q_RO+q_RU+(2q_B+q_G)cosδ), elevación, F_U = C·F_H+F_St, potencia,
y Euler-Eytelwein (e^{μα}, T2_min, FS). Anclas a mano en tests: F_H=1549.98 N,
F_U=2758.96 N, P=4.869 kW, e^{0.35π}=3.003, T2_min=499.3 N.

**Regla NUEVA "adherencia del tambor motriz (Euler-Eytelwein)"**: el tambor
solo transmite F_U si el ramal flojo lleva T2 ≥ F_U/(e^{μα}−1). μ por el NOMBRE
del tambor (engomado/lagging → 0.35; liso → 0.25), α=180°. Honestidad patrón
hanging_load: el modelo no declara la tensión real del tensor → se reporta la
T2 MÍNIMA requerida con fs=None (con `t2_n` explícito sí hay FS); ok
informativo si hay tensor detectado, aviso si no. `_enrich_conveyor` deriva
soporte/tambor_engomado/tiene_tensor/q_ro_kg_m del modelo — CERO campos nuevos
en requirements.

**Memoria**: el dict `calc` gana campo opcional `norma` → `_section_page`
pinta "NORMA DE REFERENCIA" (retro gratis: sin norma no aparece) y la portada
lista "Normas aplicadas: CEMA · Euler-Eytelwein…" bajo BASES DE DISEÑO.

**Verificación**: 19 tests nuevos (887 total) — C(L) contra publicados +
monotonía, anclas a mano, candado retro (los MISMOS 0.18 kW del fixture
slider-bed histórico), rama rodillos → ISO 5048 con P distinta, Eytelwein
μ 0.35/0.25 y honestidad fs=None, señales derivadas de escena por nombres,
NORMA en labels de la memoria y ausencia sin norma. E2E vivo en la faja 38:
motorización cita CEMA slider-bed con 0.18 kW idénticos (soporte="cama" por la
mesa — el corazón del ítem), Eytelwein ok con μ=0.35 y T2_min=167.1 N (tensor
de cola detectado), memoria PDF con 4 páginas "NORMA DE REFERENCIA" y portada
"Normas aplicadas". El veredicto "APROBADO CON AVISOS" es PRE-existente (los
avisos de asiento del 6207 del tensor, hallazgo bonus de V5.4) — la regla
nueva no lo empeora.

## V6.1 — Robustez industrial: «nada tumba el documento» (2026-07-04) — inicia el roadmap V6

**Giro de rumbo (el POR QUÉ)**: el usuario pidió máxima ambición pro y avisó que había
estado confiando en rumbos fáciles. Diagnóstico acordado: el roadmap V5 (completitud de
FLUJO del vertical) se agotó; lo que quedaba era cosmética. Se abre el roadmap V6 «Apolo
industrial», que ataca los ejes de madurez más débiles del propio CLAUDE.md — empezando
por el menos vistoso y más pro: **robustez (3/10)**. Contrato del ítem: tras CUALQUIER
fallo (excepción OCCT, comando inválido, .apolo corrupto, fuzzing de undo/redo, autosave
caído) el documento queda ÍNTEGRO Y VERIFICABLE, nunca a medias. Filosofía NO negociable:
**primero la suite de tortura (roja), después los fixes que la ponen verde.**

**Diseño del plan**: `docs/plans/V6.1-robustez-industrial.md` partió de dos exploraciones
exhaustivas del código y traía un mapa de 9 áreas frágiles + 2 bugs de PÉRDIDA DE DATOS con
evidencia de líneas.

**Fase 0 — la vara de medir**. `Document.check_integrity() → list[str]` (READ-ONLY puro):
features↔comando vivo (directo o sintético `{cmd}_{orig}` de insert_project), contrato de
instancia `mesh_key⇔matrix` (mesh_key ∉ DEFINITIONS = `"degradado: "`, NO error — el
fallback de render lo cubre), refs de juntas/mates/constraints/fasteners/grounds, parents
y ciclos de grupos, ckpts bien formados, seq monótono, variables coherentes. Flag
`document._STRICT` (env `APOLO_STRICT=1`): tras cada mutación, violaciones no-degradadas →
rollback + DocumentError. `GET /api/health` expone `ok/issues/degraded/suppressed_commands/
autosave_failed/startup_error/…`.

**Fase 1 — la tortura, primero ROJA**. `tests/test_torture.py` (T1–T14 acotados + 4
extendidos `@pytest.mark.torture`). `pytest.ini`: marker `torture` + `addopts = -m "not
torture"` (compuerta: `--collect-only` sigue dando los 887 originales — 908 con los
acotados). Mapa canónico al correrla: **13 rojos / 8 verdes**. Los rojos mapean 1:1 a los
fixes: T3→peek-then-commit, T4→checkpoints blindados, T5→regenerate atómico,
T6-seq→guardia de seq, T7×2→carga tolerante, T8-lru→LRU, T9→precheck de insert_project,
T10×2→autosave durable, T11→startup sano, T12→project/new, T13→WS resiliente. Verdes
esperados: T1 (pin de oro del fuzz undo/redo), T2 (la atomicidad de replay-loop ya la daba
el commit-al-final), T6×4 (corruptor de ZIP/JSON), T8-render (el fallback ya existía),
T14 (health ya construido en Fase 0). **Discrepancia documentada (Compuerta 2)**: el modo
«param inexistente» del corruptor sale VERDE porque pydantic IGNORA claves extra a
propósito (forward-compatible); el contrato real de schema drift es un VALOR inválido bajo
el schema de hoy, así que T6-param-drift envenena `width=-5` (no una clave extra).

**Fase 2 — fixes de `doc/` (regla: el camino sano byte-idéntico)**. `regenerate(tolerant=
False)` reescrito ATÓMICO: todo en LOCALES, `variables_resolved` calculado ANTES de tocar
`self`, y UN bloque final de asignaciones que no puede lanzar → si algo revienta (executor,
ref colgando, mates, `resolve_all`) `self` queda intacto. `tolerant=True` (solo cargas)
SUPRIME el comando roto (`regen_suppressed` [{command_id,type,error}]) y poda huérfanos
—`_prune_or_raise` estricto lanza / tolerante elimina en memoria— sin tocar JAMÁS el log.
El snapshot de undo gana la caché de regen (`"regen"`), que `_restore` repone ANTES de
regenerar → rollback resume del último checkpoint del log viejo (replay ~0) e inmune a un
fallo repetido; `undo/redo` peek-then-commit (no sacan de la pila hasta saber que la
restauración sobrevivió); `_UNDO_CAP=50`. Blindaje `_ckpts_ok()`: ckpts corruptos →
replay completo, nunca se lanza por la caché. Guardia de seq en `from_apolo_bytes`
(`max(seq, len(commands), max c-id)`). Sutileza descubierta: los faults en el bucle de
replay son atómicos SIN el fix (revientan antes de la asignación); el bug de atomicidad
solo se OBSERVA con `resolve_all` (que en el código viejo iba DESPUÉS de asignar la escena)
→ T5 se escribió como regenerate directo con escena que debe quedar vieja.

**Fase 3 — fixes de `registry`/`api`**. DEFINITIONS pasa de FIFO ciego a **LRU**:
`register_definition` toca (reinserta) una clave existente, `touch_definition` la llama el
render en cada HIT → una definición con instancias vivas que se sigue renderizando no la
desaloja un registro nuevo. `insert_project` gana `_insert_project_precheck`: computa TODOS
los nombres/ids prospectivos (grupo raíz + internos, juntas, constraints, fasteners,
grounds, fids) y choca contra el estado presente ANTES de emitir la primera pieza — un solo
CommandError con la lista, sin depender del rollback. Autosave durable: reintentos
`(0,0.1,0.5)` s; agotados → `AUTOSAVE_ERROR` en el payload + WS `autosave_failed` (el
cliente SE ENTERA de que memoria≠disco). Startup extraído a `initialize_store(db_path)`
(testeable sin FastAPI): reciente corrupto → tolerante; si ni así abre → `STARTUP_ERROR` +
doc vacío con `PROJECT_ID=None`, NO crea «Sin título» que pise el reciente. **Bug E2
(pérdida de datos)**: `project/new` y `project/open`(upload) creaban DOC nuevo sin tocar
`PROJECT_ID` → el siguiente autosave SOBRESCRIBÍA el proyecto anterior; ahora crean id
propio. WS: `_safe_send` con try/except que desecha al cliente muerto. Cargas por id/upload/
restore pasan `tolerant=True` y capturan `DocumentError`→400 (antes: 500 opaco). UI: chip
de «Sin guardar» / «N suprimidos» en StatusBar (`npm run build` verde).

**Fase 4 — baseline de perf** (`scripts/perf_baseline.py`, read-only sobre la BD, mediana
de 3). Contra los proyectos REALES: `open_frio_faja38 = 1.96 s` (72 sólidos, 309 comandos),
`scene_payload_layout53 = 1.3 ms` (149 sólidos, 1.11 MB de payload), `autosave = 4.6 ms`,
`fuzz_100ops = 1.49 s`. Commiteado en `docs/perf_baseline.json` como vara de V6.2.

**Fase 5 — E2E vivo** (TestClient con lifespan real contra una COPIA de la BD vía
`APOLO_DB` — protege los proyectos del usuario del autosave y esquiva el zombie-socket del
:8000). **14/14 OK**: health verde al arrancar; faja 38 → 72 sólidos con `suppressed==[]`;
layout 53 → 149 sólidos; re-guardado de la faja con CONTENIDO idéntico (el ZIP crudo difiere
solo por el timestamp que `writestr` embebe — el commands.json/manifest.json son idénticos);
upload truncado → 400 con el DOC intacto; upload con un create_box envenenado → 200
tolerante con el comando reportado; BD copia read-only → `autosave_failed` encendido →
permisos restaurados → flag limpio; health verde al final.

**Resultado**: mapa ROJO→VERDE completo. **915 tests** (887 + 21 de tortura acotada + 7
convencionales) + 6 de tortura extendida (`-m torture`, ~37 s: replay frío de 400 sólidos
0.4 s, scene_payload 0.2 s, fuzz 1000×3 semillas con STRICT, evicción de 600 defs). Sin
regresiones: el camino sano quedó byte-idéntico (los 887 originales verdes). Desviaciones
documentadas: T6-param-drift (valor inválido, no clave extra) y el E2E vía TestClient sobre
copia de BD en vez de uvicorn suelto (más seguro para los proyectos reales del usuario).
Madurez robustez 3→6.

**Cierre — Fix H (área oportunista del plan, completada 2026-07-04):** el plan dejó
Fix H («mensajes OCCT opacos en fillet/chamfer/shell») como opcional. Se cerró para
NO dejar V6.1 a medias: `radio/distancia/espesor > 0` ya lo garantiza pydantic
(`gt=0`), así que el valor añadido es (a) enriquecer el `CommandError` de
fillet/chamfer con el TOPE real —la longitud de la arista más corta seleccionada— y
(b) un **pre-check barato de shell por bbox**: si `2·espesor ≥ dimensión menor` la
pieza quedaría sin cavidad → se rechaza con mensaje claro ANTES de llamar a OCCT.
El pre-check es una condición NECESARIA (cero falsos positivos: solo rechaza lo que
igual saldría vacío). Sin blindar geometría fina (radio vs. caras adyacentes) para
no arriesgar falsos positivos — el `try/except` de OCCT sigue de red. +2 tests
(917 total). Con esto V6.1 queda cerrado al 100 %.

## V5.11 — Superficies básicas (boundary/fill/thicken): CIERRA el Tier 2 (2026-07-04)

Último ítem bloqueante del Tier 2 del roadmap V5 (estaba "POR DEMANDA"). Motivación pro:
Apolo solo hacía sólidos y chapa desplegable; no podía modelar geometría de doble
curvatura (chutes, tolvas, deflectores, guardas curvas) más que aproximándola. El combo
real es **superficie de contorno → thicken → pared de chapa fabricable**.

**Exploración previa (3 agentes en paralelo)** confirmó que build123d 0.10.0/OCP 7.8.1 ya
trae todo lo geométrico (nada de kernel nuevo de fondo, solo cablearlo schema-driven) y
—lo importante— produjo un **inventario de suposiciones de sólido** que una Face de volumen
0 rompe: BOM/masa/costeo (filas de peso 0), proyección de secciones (`projection.py`:
`not half.solids()` → tumba la vista), FEA (exige volumen 3D). Serialización, malla/render
y export STEP/STL son agnósticos a la topología → funcionan solos (el log regenera, no
guarda geometría).

**Fase 0 (spike, firmas reales leídas en la fuente instalada)** fijó 3 desviaciones del
plan: `Face.make_surface_patch` toma tuplas de 3 `(Edge, Face, ContinuityLevel.C1)` (no de
2); `thicken(both=True)` engruesa `amount` COMPLETO a cada lado (espesor total 2×, no
±t/2); la continuidad G1 falla en paredes perpendiculares (`Geom_RectangularTrimmedSurface::
V1==V2`) — geométricamente correcto (un parche plano no puede ser tangente a muros
verticales) → el comando lo captura con error accionable. Adyacencia arista→cara con
`TopExp.MapShapesAndAncestors_s` + `list(TopTools_ListOfShape)` (iterable en Python).

**Entregado**: `kernel/surface.py` (funciones puras `boundary_surface`/
`fill_surface_from_edges`/`thicken_surface`, reusan `path_from_points` de sweep.py) +
`is_surface` en `kernel/shapes.py` (caras y 0 sólidos). 3 comandos schema-driven
(categoría "superficies", sin wants_* flags — las `=expr` se resuelven arriba):
`boundary_surface` (contorno de curvas, `points` → parche no plano, `holes` → lazos
interiores), `fill_surface` (parche sobre aristas de un sólido, `tangent` G1 opcional,
emite Feature NUEVA sin mutar el target) y `thicken` (superficie → sólido, muta en sitio
como fillet/shell). **Decisión de ingeniería**: una superficie desnuda es geometría de
CONSTRUCCIÓN — `is_surface` la EXCLUYE de BOM (`bom.py`, cascada a costeo), masa
(`mass.py`) y sección (`projection.py` filtra a sólidos, avisa si no queda ninguno); FEA
(`api/main.py`) la rechaza pidiendo thicken. Línea de receta en `design/guidelines.py`
(capa 2) para que el agente sepa que existe.

**Verificación E2E (stack HTTP real, TestClient)**: deflector curvo de doble curvatura (2
rectas + 2 arcos spline + punto de forma) → en escena con volumen 0 y MESH (renderiza) →
excluido del BOM → la sección SVG no truena con la superficie presente (200, 21.5 KB) →
`thicken 3mm` → sólido de 281 914 mm³ que YA entra al BOM → STEP del conjunto 93 KB. 21
tests nuevos (`tests/test_surfaces.py`; áreas exactas, thicken paramétrico con `=esp`,
both duplica, rechazos accionables, exclusión de construcción, sección robusta con y sin
sólidos). 938 tests (48→51 comandos, 66 tools MCP sin cambio — MCP es THIN, run_command
genérico). **Tier 2 CERRADO** → el roadmap V5 queda 100 % en lo bloqueante; el resto del
Tier 3 (Blender/PDM/plantillas por empresa) es por demanda. Siguiente ítem pro: V6.1 ya
está hecho → sigue V6.2 rendimiento.

---

## V6.2 — Rendimiento «Apolo industrial» (2026-07-09)

Segundo ítem del roadmap V6. Cuatro frentes, un commit por fase, tortura + health verdes
tras cada uno; baseline regenerado (`docs/perf_baseline.json`, host Mario-LapTrab).

**A · Open frío → caliente (caché BREP por firma).** Abrir un proyecto replayaba el log
completo (faja 38: 701 comandos, ~3 s en proceso caliente, ~23 s en frío). Nueva caché
(`doc/geomcache.py`) persiste el ESTADO regenerado —la 8-tupla final + las definiciones
canónicas de la escena— indexado por la firma acumulada del log; `from_apolo_bytes(warm=)`
reanuda del checkpoint (replay ~0) si la firma cacheada es PREFIJO del log, con
`check_integrity` cinturón-y-tirantes (si hay violaciones no-degradadas, descarta y replaya
frío). Vive SOLO en la SQLite local (tabla `geom_cache`), JAMÁS en el `.apolo` (la geometría
nunca se guarda; un `.apolo` lo sube el usuario → despicklearlo = RCE). Kill-switch
`APOLO_GEOM_CACHE=0`. **Gotcha BinTools (destapado por el baseline de la Fase E)**: el primer
diseño pickleaba el wrapper build123d, que lleva estado (`joints`/`children`) y NO
round-trip-ea → `unpack` fallaba en la faja y CAÍA a replay frío SIN avisar (los tests
sintéticos de primitivas no tienen wrappers frágiles → pasaban en verde; el open «caliente»
de 3.2 s era en realidad un frío enmascarado). Peor: `serialize_shape` del TopoDS crudo
SIEMPRE da bytes, pero `deserialize_shape` revienta por-shape de forma caprichosa —unos
round-trip-ean crudos, otros solo tras `BRepBuilderAPI_Copy` (aplana refs de geometría), y
la copia ROMPE a los primeros—. Solución (`_serialize_robust`): por shape, intenta crudo y
VERIFICA deserializando (el fallo de BinTools salta al LEER); si no, intenta la copia y
verifica; si ninguno, None → pack cae → replay frío. Resultado real: faja 38 open frío
3–23 s → **caliente 0.036 s** (unpack de 82 shapes = 17 ms), Δvolumen ~7e-12, integridad e
instancing limpios. Escritura cableada al autosave (Fase D la mueve al flush).

**B · Deltas de `scene_payload` + reuso de mallas.** El refresh por WS bajaba
`GET /api/scene` COMPLETO (~1.1 MB) y el viewport reconstruía TODAS las mallas three.js.
`_geom_rev(fid, shape)` = revisión por IDENTIDAD del shape (el regen incremental la preserva
para lo NO re-ejecutado; editar el comando *i* re-ejecuta *i*..fin → esos rev suben, por eso
un edit temprano reconstruye la cola, no «solo la pieza»). `scene_payload(known={revs,defs})`
manda `same:true` + solo metadatos volátiles para lo que el cliente ya tiene; `POST
/api/scene/delta` lo usa el refresh. UI: `mergeSceneDelta` hereda la geometría anterior; el
viewport diffea por `rev` (`builtRef` Map) → reconstruye solo lo cambiado, la apariencia se
rehace en sitio (`applyAppearance`); pool `shared` de instancias persiste con disposal por
uso. Medido: layout 53 delta sin cambios **1.1 MB → 31 KB (2.8 %)**. E2E (browser, DB
scratch aislada, hook `window.__apolo`): append → +1 build, 10 mallas reusadas (mismas
instancias); recolor → 0 builds, material intercambiado.

**C · Dos-locks render/física.** `render_view` teselaba + corría VTK bajo STATE_LOCK;
`gravity_test`/`drop_test` corrían el bucle mj_step bajo el lock → un render o sim larga
congelaba TODO. Regla de oro: bajo STATE_LOCK se EXTRAE geometría (OCCT → datos PUROS);
fuera solo arrays. `extract_render_scene` (STATE_LOCK, con `_RENDER_MESH_CACHE`) +
`render_snapshot_vtk` (RENDER_LOCK); `prepare_stability`/`prepare_drop` (XML MuJoCo horneado,
STATE_LOCK) + `simulate_*` (PHYSICS_LOCK). Render byte-IDÉNTICO al anterior verificado en 6
configs (normal/highlight/xray/labels/bbox+axes/fit). Concurrencia (torture, Event): mutación
durante gravity de 2 s = 5 ms, durante render de 2 s = 491 ms (< 1 s); el render termina 200
pese a que la mutación invalida los shapes (snapshot = datos puros). Follow-up: `export_stl`,
`drawing_spec` (su HLR es OCCT, no sale del lock).

**D · Autosave con debounce + pack en el flush.** `_autosave()` escribía inline tras cada
mutación. `_AutosaveScheduler`: marca sucio + arma un flush ÚNICO (debounce 500 ms, techo
3 s); `_do_flush` toma `to_apolo_bytes()` + `pack()` BAJO STATE_LOCK y escribe SQLite FUERA
(durabilidad V6.1 intacta: reintentos, `AUTOSAVE_ERROR` + WS; la caché de geometría es
best-effort aparte). Flush FORZOSO en shutdown, cambio de proyecto (open/new/create),
save_revision y restore. `GET /api/health` → `autosave_pending`. Tests V6.1 adaptados
(`_flush_autosave()` fuerza antes de leer disco; fixtures con STORE hacen
`_autosave_sched.cancel()` en teardown; dobles pasan a `save_raw`). Ráfaga de 20 mutaciones =
1 escritura.

**Cierre**: 971 tests (+11 tortura). Madurez rendimiento 4→6. El detalle por línea vive en
CLAUDE.md § Rendimiento (V6.2).

---

## V6.2e — Correcciones de la revisión adversarial de V6.2 (2026-07-09)

Una revisión adversarial de los 4 commits de V6.2 encontró 2 ALTOS + 5 MEDIOS. Cerrados
antes de sellar V6.2.

**Fix 1 (ALTA) — Flush del autosave atómico.** `_do_flush` capturaba `STORE/PROJECT_ID`
FUERA del `STATE_LOCK` que serializa `DOC` → interleaving: el Timer de A lee `project_id=A`,
se preempta, el usuario abre B (swap de DOC/PROJECT_ID), el Timer reanuda y hace
`save_raw(A, bytes_de_B)` → corrupción cruzada SILENCIOSA. Fix: (a) capturar STORE/PROJECT_ID
DENTRO del mismo `STATE_LOCK` del snapshot (`_flush_body`); (b) `_flush_lock` sostenido TODO
el flush (reintentos incluidos) → sin carrera de bytes viejos pisando nuevos; (c) el cambio
de proyecto usa `_project_switch()` — flush del doc actual + swap ATÓMICO bajo
`_flush_lock`+`STATE_LOCK`, ORDEN ÚNICO GLOBAL `_flush_lock → STATE_LOCK` (jamás al revés →
sin deadlock switch↔Timer); (d) fallo de SERIALIZACIÓN también enciende `AUTOSAVE_ERROR`+WS
(antes moría en el excepthook del Timer con dirty limpio); (e) `pending()` = sucio O flush en
vuelo. Tests: corrupción cruzada (nombre por-save), fallo de serialización, no-deadlock con
Events + timeouts.

**Fix 2 (ALTA) — Epoch de proceso para los revs.** `_GEOM_REVS` vive en el proceso pero el
navegador lo sobrevive; tras un restart del API los revs renacen en 1 y COLISIONAN con los
del cliente → el delta respondería `same:true` con geometría VIEJA para siempre. Fix:
`SCENE_EPOCH = uuid4` por proceso en el payload; el cliente lo devuelve en el delta y, si no
coincide, el server manda el payload COMPLETO; `connectWs` fuerza refresh completo en cada
reconexión (`onopen` tras `onclose`).

**Fix 3 (MEDIA) — Equivalencia warm≠frío con mates.** `pack` empacaba el estado
POST-finalización (`solve_mates` aplicados), pero la cola del regenerate ejecuta PRE-mates →
un `center_in`/`near` en la cola (o tras el open) veía geometría desplazada. Fix: `pack`
empaca el checkpoint ORGÁNICO del último comando (`_regen_ckpts[len-1]`, capturado dentro del
bucle, pre-finalización). **Fix 4**: `pack` → None si `regen_suppressed` (doc tolerante no se
cachea). **Fix 5**: `from_apolo_bytes` envuelve el regenerate SEMBRADO en try/except → si
LANZA (no solo si viola integridad) descarta y replay frío (cubre `duplicate`). **Fix 6**:
`ProjectStore.load` PUEBLA la caché en el open frío (~40 ms) — un proyecto que solo se abre
nunca la poblaría vía el flush post-mutación. **Fix 7**: `is_guide` va en la entrada `same`
del delta (toggle de guía es metadato) + en `mergeSceneDelta`.

**Bajas**: `load_geom_cache` en try/except (una página corrupta no tumba el open sano);
`mergeSceneDelta` descarta una entrada `same` sin prev; comentario de footgun en el wrapper
`render_scene_vtk`. Follow-ups anotados en CLAUDE.md § Pendientes (applyAppearance×tinte, GIF
compose fuera del lock, RenderSnapshot Vector→ndarray, etc.).

**Cierre**: baseline sin cambios de números (verificado). Suite + tortura verdes. V6.2 SELLADO.

## V6.3 — Ensamblaje pro: multi-mate, conectores por ancla, reporte de DOF (2026-07-09)

Tercer ítem del roadmap V6. Madurez ensamblaje 4.5→6. Cuatro fases con commits separados;
suite 981→1019 tests + 12→15 torturas, todo verde; `GET /api/health` sano.

**Fase 0 — residuo de V6.2e (autosave).** `_fire` limpiaba `dirty` ANTES de adquirir
`_flush_lock`. En la carrera con un `_project_switch` que ganara el lock primero, `take_pending`
veía `dirty=False` y NO persistía el doc VIEJO → las últimas mutaciones (<=3 s) se evaporaban
(lost update; `pending()` parpadeaba a False). Fix: `_fire` ya no limpia dirty; el clear ocurre
DENTRO de `_flush_lock` (en `_run`, que sigue flusheando incondicionalmente — el switch ya
consumió dirty vía take_pending → es una reescritura del proyecto ACTUAL, inocua). Test de
carrera con Events forzando el interleaving.

**Fase A — multi-mate por sólido.** El grafo hijo→padres pasa de ÁRBOL (1 mate/hijo) a DAG
multi-padre; se quita la guarda de mates.py y se generaliza `_mate_ancestors` a multi-padre
(lazos cerrados A↔B siguen rechazados como ciclo — fuera de alcance). `solve_mates` en dos
caminos: 1 mate/hijo → camino cerrado exacto `_solve_one` INTACTO (pose determinista bit-a-bit;
ningún test de pose existente cambia); ≥2 → `_solve_multi`, que resuelve la pose 6-DOF por
`scipy.least_squares` (`x_scale='jac'`) sobre `[tx,ty,tz, rotvec]`. Residuos por tipo
(`_mate_residuals`) CONSISTENTES con `_desired_current_frames` (a residuo 0 coinciden con el
camino cerrado — probado con frames sintéticos), pero cada mate restringe SOLO sus GDL naturales
(coincidente/distancia = along + normal anti-paralela; concéntrico = 2 puntos del eje a la recta,
deja deslizar/girar; paralelo = cross; ángulo = escalar; angulares escalados ×L del bbox). GOTCHA
clave de convergencia: la rotación se parametriza SOBRE EL CENTRO de B, no sobre el origen del
mundo — con el origen, si B está lejos, rotar lo desplaza enormemente y el solver cambia posición
por giro sin converger. Orden topológico Kahn determinista. Conflicto (costo > 1e-3 tras 1
reintento con perturbación FIJA) → MateError nombrando los mates y su residuo → en estricto,
rollback. Interference/soundness ya no asumían 1/hijo (interference excluye por junta+
same_command, no por mate; connectivity itera mates.values()).

**Fase B — conectores por ancla y arista circular.** (1) ARISTAS CIRCULARES: `{"entidad":
"arista", ...selector...}` resuelve el borde de un barreno/tapa a (centro, eje del círculo) vía
BRepAdaptor_Curve→gp_Circ. (2) ANCLAS con nombre: `Feature.anchors` (dict MUNDO), publicadas por
los executors al colocar el componente y RE-calculadas en cada regenerate (sin estado que
envejezca): chumaceras UCP/UCF/UCFL→"centro" (eje del rodamiento Y, origen en el barreno), NMRV
worm_gearmotor→"bore", create_belt_conveyor→"eje_motriz"/"eje_cola" (tambores), create_conveyor→
ejes de los rodillos extremos. `connector_of` acepta la Feature y gana el modo `{"mode":"ancla",
"name":...}`. TODO camino que mueve el shape tras el executor transforma las anclas
(`kernel.matrix.transform_anchors`, REEMPLAZA nunca muta — los checkpoints comparten la referencia
por el shallow copy): `_solve_one`, `_solve_multi`, `transform_group`, `insert_project`.
`get_topology` las lista (MCP thin: el hueco es de LECTURA). Bump `GEOM_CACHE_EPOCH` 2→3 (un ckpt
viejo restauraría Features sin anclas). E2E medido: chumacera UCP205 mateada concéntrica por ancla
'centro' contra un eje cilíndrico → su centro cae exacto sobre el eje (200,·,300) y el ancla viaja
con la pieza (no stale); pin concéntrico al borde de un barreno → se centra en él.

**Fase C — reporte de DOF.** `assembly/dof.py::dof_report(scene,joints,mates,grounds)` puro (sin
Document/OCCT): por sólido, 6 GDL menos ground (−6)/junta (fija−6, gir/cont/pris−5)/mates
(coincidente−3, distancia−3, concéntrico−4, paralelo−2, ángulo−1); estado fijo/parcial/libre/
sobre_restringido + `restringido_por`. Conteo Grübler HEURÍSTICO — no ve redundancia geométrica
(coincidente+concéntrico = 7 removidos se marca sobre_restringido aunque sea válido); los
conflictos REALES los rechaza el solver de mates en la mutación, así que un doc regenerado no trae
`overconstrained` del solver (parámetro opcional para completitud). Las juntas, que en el resto de
Apolo son solo visualización, aquí SÍ cuentan como restricción (lectura útil). `GET /api/assembly/
dof` + tool `get_dof` (67 tools) + bloque expandible en AssemblyPanel (junto a soundness). E2E:
`get_dof` sobre la faja 38 (82 sólidos, 15 juntas, 25 grounds) → 81 piezas, 256 GDL, 41 libres, 0
sobre-restringidas, grounds→fijo, sin crash. Consistencia con soundness: una pieza floating sin
nada = 6 GDL (libre).

**Cierre**: baseline sin regenerar (nada toca los caminos medidos). Un servidor del usuario corría
en :8000 con código viejo → la verificación de la UI se apoyó en `npm run build` (tsc estricto
verde) + `test_api_dof_endpoint` + el bloque replica los patrones existentes; el render de la
Fase B se sustituyó por la medición numérica (más fuerte que un render). Plan movido a
`docs/plans/done/`.

## V6.3d — Correcciones de la revisión de V6.3 (2026-07-10)

La revisión de V6.3 encontró **1 bug real de corrección** + correcciones menores + saldar el E2E
por MCP que se había sustituido por medición numérica (zombie-socket). Todo cerrado:

**Fix 1 — `_world_move` no transformaba las anclas (EL bug).** `commands/registry.py::_world_move`
reasignaba `feat.shape` y, si era instancia, `feat.matrix`, pero NUNCA `feat.anchors` → tras un
`transform`/`center_in`/`distribute`/`attach` el conector por ancla quedaba STALE en la pose
original y un mate concéntrico por ancla mateaba con un frame viejo (la chumacera acababa 100 mm
fuera del eje). Fix: la matriz mundo rígida `w = T·T(c)·R·T(-c)` (c = centro del bbox = el MISMO
que usa `move_rotated_about_center`) hoy se calcula también cuando `matrix is None` si hay anclas,
y se aplica `transform_anchors(w, feat.anchors)` (REEMPLAZA, nunca muta — contrato de checkpoints).

**Fix 2 — copias sin anclas.** `duplicate_feature`, `pattern_linear`, `pattern_circular` y
`pattern_group` creaban copias SIN `anchors` (ausente, no stale) → una chumacera duplicada/arrayada
perdía su «centro» y no podía matearse por ancla. Fix: transformar las anclas de la fuente con el
offset/rotación de cada copia (`transform_anchors` con la matriz de traslación o
`axis_rotation_about_point`). **`mirror` queda EXCLUIDO deliberadamente** (reflejar un frame invierte
la mano del eje) — anotado en CLAUDE.md § Pendientes.

**Fix 3 — docs.** `mcp.list_tools()` en el venv da **66 tools** (CLAUDE.md decía 67); tests reales
1028 con los nuevos (decía 1019). `dof_report` (docstring + `nota` del payload) ahora declara que
las piezas de un `insert_project` traen sus mates internos BAKED (no re-registrados) → se reportan
«libre» aunque en el donante estuvieran acopladas. § Pendientes gana: divergencia anti-paralela del
multi-mate (los residuos de paralelo/concéntrico aceptan ejes invertidos; al borrar un mate la pieza
puede «saltar» 180°), tolerancia angular ×L en hijos muy grandes, y contaminación del `EdgeSelector`
compartido (modos ancla/entidad aparecen en fillet/chamfer — error claro, no silencioso).

**Fix 4 — `test_guias_excluidas` con dientes.** No creaba ninguna guía (no probaba la rama
`dof.py:54-55`). Ahora crea 2 cajas, marca una con `set_sketch_guide` y assert que NO aparece en el
reporte de DOF.

**Fix 5 — E2E real por MCP (deuda del criterio V5).** Se investigó el «zombie» de :8000: NO era un
huérfano — el uvicorn `--reload` vivo (con su hijo `multiprocessing.spawn` de anaconda, padre vivo)
era el dueño legítimo del puerto y ya había recargado el código nuevo. Verificado EN VIVO por tools
MCP `apolo-cad` sobre un proyecto nuevo: (1) chumacera UCP205 insertada en (0,-300,0) → ancla centro
[0,-300,0]; `transform +Z 300` → `get_topology` reporta ancla [0,-300,**300**] (Fix 1 PROBADO en
vivo, no stale); (2) 2ª chumacera insertada FUERA del eje (z=0) + `add_mate` concéntrico por ancla →
saltó a x≈0, z=300 SOBRE el eje (Y = grado libre del concéntrico); (3) `get_dof` → eje libre (6 GDL),
cada chumacera parcial con **2 GDL** y `restringido_por: mate:m_chumX`, 0 sobre-restringidas; (4)
`render_view` iso confirma el eje atravesando el barreno de ambas chumaceras. Proyecto 38 del usuario
restaurado al terminar.

**Verificación**: `pytest tests -q` 1028 (1027 pass + 1 skip) verde · `pytest -m torture` 15 verde ·
sin cambios de firma → host MCP no requiere reinicio · tests nuevos en `test_anchors.py` (Fix 1/2:
transform mueve ancla, rotación gira el eje, repro rígido transform+mate, center_in, undo/redo,
duplicate/pattern heredan y matean). Ensamblaje se mantiene en 6.

## V6.4 — Paramétrico profundo: condicionales + faja 38 paramétrica + tablas de diseño (2026-07-10)

Cuarto ítem de V6 (paramétrico 5→6.5). Tres frentes: MOTOR (pequeño), CIRUGÍA del proyecto real 38
(el grueso), PRODUCTO (tablas de diseño sobre `configurations`).

**Fase A — condicionales en expresiones (`feat: V6.4a`, commit f948b89).** `expressions.py` gana
`ast.IfExp` (ternario PEREZOSO — solo evalúa la rama tomada, una `1/0` en la rama no tomada no
revienta), `ast.Compare` (`< <= > >= == !=`, encadenados `a<b<c` con corto-circuito, colapsan a
1.0/0.0; `in`/`is` validados y rechazados por adelantado) y `ast.BoolOp` (`and`/`or`). Fuera:
strings/listas/atributos/índices/lambda. `GET /api/expression-grammar` + hint del VariablesDialog.
El caso `x if 1 else 2` pasa de prohibido a permitido en el test de seguridad.

**Fase B — cirugía de la faja 38.** Red de seguridad primero: `save_revision` id 75 verificada en la
BD. Auditoría read-only del log (script solo-JSON, sin importar apolo): **cierre de dependencias
CONSERVADOR** — KEEP = structural ∪ productoras-de-pieza-viva, fixpoint sumando inputs de boolean y
mutadores sobre KEEP. Reveló que la clasificación ingenua marca como muertos los INPUTS de los
boolean_op vivos (c38/c41/c42… alimentan largueros/patas): borrarlos rompería el modelo. El cierre
correcto dio **373 comandos muertos, TODOS en el rango de ids 701–1098** (el tramo de escombro de
drag&drop de la UI), ninguno produce pieza viva, ningún `delete_feature` muerto resucita algo, cero
refs vivas→muertas. **Poda atómica (`POST /api/commands/remove`, 373 ids): 701→328 comandos, las 82
piezas con volúmenes+bboxes BIT-IDÉNTICOS**, integridad limpia. (No podé c765/c1099 —«basura viva»
que el plan mencionaba— por ser piezas vivas; quedan como follow-up conservador.)

Reparametrización: (1) posiciones del conjunto motriz `edit_batch` (c670 eje, c682 NMRV, c686/687
chumaceras, c412 take-up → `=long_centros`/`=drum_cz`; verificado exacto con `resolve_expression`,
0 movimiento). (2) **Los 6 run_scripts reescritos para leer `V[...]`** — CLAUDE.md:464 estaba
DESACTUALIZADO («run_script NO ve variables»): el sandbox SÍ inyecta `V = resolve_all(vars)` (y
`test_script` también). Diagnóstico clave por sonda (`largo_total=3200`): TODA la región motriz
(extremo + última pata) traslada RÍGIDAMENTE `Δx = long_centros−3806` → los scripts complejos
(c673 disco, c703/c704 ménsula motor) se parametrizan con un shift uniforme en x (a nivel de
coordenada `Pos(x+dx,…)*shape` — el `Pos(dx,…)*result` peló ShapeList de partes disjuntas), los
simples (c669 tambor, c685 ménsulas, c647 pies) por sustitución directa. Cada reescritura validada
en seco con `test_script` (volumen/bbox idénticos) antes de aplicar; tras aplicar, las 82 piezas
bit-idénticas al baseline 4000.

**E2E de aceptación (el caso que fallaba)**: `largo_total=3200` → long_centros=3006, y TODO el
conjunto motriz sigue (tambor 3006, eje 3006, NMRV 2810.8, chumaceras 3006, ménsulas 3006, disco/
ménsula-motor/tornillería −800) — antes de V6.4b el tambor/disco/ménsulas se quedaban en 3806
partiendo el conjunto. `check_interference` idéntico a 4000 (27 contactos pre-existentes, 0 nuevos).
`ancho_banda=500` topa un límite PRE-EXISTENTE de c339 (Ménsula rodillo retorno, `depth`≤0 — no
regresión, el regenerate atómico lo rechaza). Restaurado a 4000/600 (82 piezas idénticas al original),
`save_revision` id 76 «V6.4 paramétrica».

**Fase C — tablas de diseño (`feat: V6.4c`).** `Document.set_configuration(name, values)` edita una
variante con `{var: expr}` EXPLÍCITO sin aplicarla (valida existencia/parseo/ciclos); `PUT
/api/configurations/{name}`; payload `configuration_values` alimenta la grilla variables×variantes
del VariablesDialog (celdas editables → PUT, ▸ aplica). Tools MCP `save_configuration`/
`apply_configuration` (66→68 — reiniciar host MCP para verlas). Puente requisitos→variables EXPLÍCITO
(botón «→ var» en RequirementsPanel = crea el `set_variable`): NUNCA implícito (`=req.x`) porque los
requisitos son metadato FUERA del log → geometría stale. E2E sobre la faja: variantes «4m estándar»
(4000) y «3.2m compacta» (3200); alternar por API salta el modelo completo (tambor 3806↔3006).

**Verificación**: `pytest tests -q` 1039 verde · `pytest -m torture` 15 verde · `npm run build`
(tsc+vite) verde. Paramétrico 5→6.5.

## V6.5 — MCP a escala: ergonomía del agente para miles de piezas (2026-07-10)

**Doctrina.** El ingeniero digital (agente IA) es quien PRODUCE los entregables → su interfaz
de percepción/acción ES infraestructura de producción. Estaba calibrada para ~82 piezas; el
objetivo: trabajar proyectos de MILES de piezas sin ahogarse en contexto ni entrar en bucles.
Diagnóstico del propio agente: (1) su recurso escaso es el CONTEXTO — cada byte de retorno
compite con el razonamiento; (2) no «ve» geometría, la calcula — cada cálculo hecho a mano es
un bucle en potencia. Principio rector: **el agente declara INTENCIÓN y consume RESÚMENES; el
kernel calcula las respuestas exactas.** Regla de presupuesto: ninguna lectura de rutina supera
~10 KB en un proyecto de 1000 piezas. El MCP sigue THIN: la única tool NUEVA es `verify`; el
resto GENERALIZA tools existentes (compat byte-idéntica sin params nuevos).

**Fase A — lectura acotada y resumida (`feat: V6.5a`).** `GET /api/scene` gana `ids` (CSV de
feature_ids o NOMBRES de grupo, vía `_expand_ids`) / `name` (substring) / `limit` (def. 200) /
`offset` → BRIEF ligero SIN mallas (`_scene_filtered` + `_feature_brief`, mismos campos que el
`_scene_brief` del cliente MCP), con `total_solidos`/`total_filtrado`/`truncado` (sin caps
silenciosos). Sin params = payload completo con mallas byte-idéntico (compat viewport: hay tests
del delta que dependen de él). `GET /api/scene/summary` (`scene_summary_dict`) = resumen por
GRUPO de nivel superior (n_piezas + masa + bbox conjunto RECURSIVO + sub_grupos por nombre) +
«(sin grupo)» + totales + variables — la vista de ENTRADA a un proyecto grande. `get_topology`
gana `only` (caras|aristas|anclas) y `min_mm` (poda micro-fillets/taladros). `get_bom` expone
`by_group` (el endpoint ya lo soportaba). **Cifras medidas** (modelo sintético 1041 piezas por
`pattern_group`, dos grupos): brief filtrado al grupo de trabajo (49 piezas) = **9.4 KB**;
`summary` completo = **0.45 KB**; sin filtrar, la escena serían cientos de KB con mallas.

**Fase B — consultas espaciales (`feat: V6.5b`).** `near` generalizado (`kernel/measure.py`,
helper único `_aabb_gap` con el punto como AABB degenerado): además de `point`, acepta `feature`
(«¿qué RODEA a X?» — distancia AABB-AABB al resto, excluyendo X) y `box` («¿qué hay en esta
REGIÓN?»); `radius`+`limit`. Barrido O(n) sobre AABBs — NO se construyó índice espacial (medir
primero; follow-up si duele a 5000). `interference_report` gana `focus` (parejas donde participa
AL MENOS un id, O(k·n)) — difiere de `only` (que restringe AMBOS extremos): `focus` CONSERVA las
colisiones del subconjunto contra el resto de la escena. `POST /api/checks` lo expone como
`interference_ids` (expandido con `_expand_ids`) → `check_interference(ids=...)` valida la zona
de trabajo, no la máquina entera. Test: `focus` == subconjunto EXACTO de la global.

**Fase C — verbos de intención y aserciones (`feat: V6.5c`).** Comando nuevo `snap_to`
(schema-driven → UI + agente gratis): `{feature, target, lado:±x|±y|±z, gap (=expr ok), alinear:
[ejes]}` → traslada `feature` para que su cara de bbox enfrentada quede a `gap` mm del `lado` del
bbox de `target` (gap=0 = a ras), centrando en los ejes de `alinear`. Es «junto a B hacia d con
gap g» en UNA llamada sin aritmética del agente. **Relacional** (patrón `center_in`: se reevalúa
al regenerar con el MISMO `_world_move` → conserva matrix/anclas): si el target se mueve o cambia
de tamaño, la pieza lo sigue. NO reemplaza los mates: bbox-a-bbox; para caras arbitrarias/
cilíndricas siguen los mates (documentado en el `description`). Tool nueva `verify` (`POST
/api/verify`, READ-ONLY; `library/verify.py` PURO con `expand`/`interference_fn` inyectados para
no cruzar la frontera de capas): lote de aserciones `distancia`/`volumen`/`bbox`/
`sin_interferencia`/`existe` → `[{check, ok, actual, esperado}]`. Mata el patrón «6 measure
sueltos + aritmética mental»: el agente declara las invariantes ANTES y las verifica DESPUÉS en
una llamada. `id`/`grupo`/`ids` aceptan nombres de grupo. 68→69 tools (reiniciar host MCP).

**Fase D — dry-run con datos (`feat: V6.5d`).** `preview` gana `data=true`: además del PNG
(default, compat), devuelve `{fantasmas:[{name,bbox,volumen_mm3}], colisiones_nuevas:[...]}` — las
colisiones SOLO de los fantasmas (reusa la interferencia acotada de la Fase B, `focus` a los ids
nuevos, excluyendo hardware/parejas por diseño vía un shim `SimpleNamespace(scene=...)`). El
agente prueba N colocaciones y compromete 1 SIN mutar el documento ni generar escombro de log (la
lección de los ~400 comandos podados en V6.4). Test: el documento queda INTACTO (firma del log
idéntica); comando inválido → 400 sin efectos.

**Fase E — doctrina de jerarquía + cierre.** `ESCALA_DOCTRINE` en `design/guidelines.py`, inyectada
en `design_brief()` (capa 1, SIEMPRE en instrucciones MCP + SYSTEM_PROMPT) y expuesta en
`design_guidelines()`: «en proyectos grandes entra por `get_scene(summary=true)`, trabaja por
GRUPOS, valida con `check_interference(ids=...)`, ensaya con `preview(data=true)` y comprueba con
`verify`, no con aritmética mental; estructura con create_group/auto_group o divide en
sub-proyectos». **Verificación**: `pytest tests -q` **1077 verde** (+38 nuevos: escala/espaciales/
snap_to/verify/preview) · `pytest -m torture` 15 verde · imports/health verdes. Roadmap: croquis
vivo → V6.6, FEA de ensamblaje → V6.7. IA-nativa/API-first sigue 9.5, el moat, ahora más profundo.

## V6.4d — Remate de la revisión de V6.4 (2026-07-10)

La revisión adversarial de V6.4 (a/b/c) aprobó lo sustantivo pero halló **residuos entre plan y
ejecución**; este remate los cierra. Ejecutado sobre el proyecto 38 VIVO (API+MCP) con revisión
previa «pre V6.4d» (id 78) por seguridad.

**Fix 5a (código + test) — guías huérfanas.** `Document.from_apolo_bytes` ahora poda las entradas
de `sketch_guides` (metadato = command_ids) cuyo comando ya no existe en el log. Se eligió la ruta
de CARGA, NO `remove_commands`, porque `sketch_guides` NO viaja en los snapshots de undo
(`_snapshot`/`_restore` llevan commands/hidden/seq/regen, no el metadato): podarlo en la mutación
lo perdería al deshacer el remove. Conserva el criterio `_cmd_alive` (id directo o sintético
`{cmd}_{orig}` de insert_project). Test nuevo: una guía-huérfana sintética `c9999` se poda en el
round-trip, la viva sobrevive.

**Fix 2 — las 15 juntas dejan de ser 100 % literales.** `get_command` reveló los 80 campos
literales. Por `edit_batch` (atómico, 1 undo), enviando el `origin` completo (un sub-objeto se
reemplaza entero): `j_trav1..5` x→`100+k*(long_centros-200)/4`, z→`z_mesa_bot-sec_trav/2`;
`j_mesa1..4` z→`z_mesa_bot+esp_mesa/2`; `j_tensor_cola` z→`drum_cz`. Cada candidata se verificó con
`resolve_expression` ANTES de atar. **Reconciliación honesta**: `j_trav2/4` x resolvían a
1001.5/2804.5 (los literales 1001/2804 eran REDONDEOS de los centros reales de sección) — se
ataron a la fórmula porque el origen de una junta prismática-z es un ancla cinemática que mueve 0
geometría de pieza (confirmado: el `edit_batch` devolvió 0 sólidos afectados) y 1001.5/2804.5 =
centro EXACTO del travesaño hijo. `j_mesa1..4` x (centros redondeados, sin fórmula exacta) se
dejaron LITERALES + anotadas (regla resolver-exacto: no inventar una falsa).

**Fix 3 — residuos dimensionales.** `belt_out_tail/drive` (c111/c112) radius 59→`rad_tambor+
esp_banda`, `belt_in` (c115/c116) 57→`rad_tambor`, `rodillo_body` (c120) 25→`diam_rodillo/2` (todos
EXACTOS, geometría byte-idéntica → 0 sólidos afectados). Las z=707 (rodillo retorno c120/c121) y
z=737.5 (su ménsula c339-342) se dejaron literales: son alturas CONSTANTES entre las dos variantes
y la z de la ménsula no tiene expresión limpia (mantener rodillo↔ménsula consistentes).

**Fix 4 — poda de basura viva.** `POST /api/commands/remove` de `c1099` («Boceto» 200×200×45, era
guía) + sus 14 transforms (c1100-c1113, el patrón sistémico de drag&drop con literales) + `c765`
(«Viga trazada» flotante, 7 sólidos). Conteo confirmado ANTES mirando la escena: 82→74 sólidos,
328→312 comandos. `check_integrity` limpio; ni mates ni grupos referenciaban las basuras (grep del
log lo confirmó antes de podar).

**Fix 6 — E2E de cierre.** `apply_configuration("3.2m compacta")` (long_centros 3806→3006): las
juntas SIGUEN — `j_trav5` a 2906 (centro del último travesaño, dentro del bastidor que ahora acaba
en x=3103), `j_trav2/3/4` a 801.5/1503/2204.5; el conjunto motriz (tambor, motor, chumaceras) se
corre −800. `check_interference`: EXACTAMENTE las mismas 20 parejas de contacto intencional que en
4m → **0 colisiones nuevas**. Render limpio (sin la basura podada). Vuelta a «4m estándar»
(4000/600, 74 sólidos) + revisión «V6.4d» (id 79).

**Fix 5b (datos) — verificado + limpio durable.** La carga con el Fix 5a ya había limpiado sola
las 25 guías-huérfanas de V6.4b (podadas al recargar el worker con `--reload` + autosave); tras el
Fix 4 quedó 1 nueva (`c1099`). Script offline (API detenida): el manifest crudo tenía 1
guía-huérfana → tras la carga 0, sólidos/comandos intactos → re-guardado durable (registro
principal del proyecto 38 limpio).

**Fix 1 — baseline re-medido.** `scripts/perf_baseline.py` (API detenida) contra el proyecto 38
podado: `faja_comandos` 701→312, `faja_solidos` 82→74, `open_frio_faja_s` 3.15→~1.8. `nota`
actualizada con la fuente (log PODADO de V6.4) en ASCII para no romper el `print` en consola cp1252.

**Menores.** `GET /api/expression-grammar` documenta ahora que `and`/`or` colapsan a 1.0/0.0 (el
idiom `x or 5` NO devuelve 5). Las tools MCP `save/apply_configuration` se estrenaron en vivo en el
Fix 6. **Verificación**: `pytest tests -q` **1078 verde** (+1 nuevo: guía huérfana) · `pytest -m
torture` 15 verde · `GET /api/health` limpio (0 issues) tras cada mutación.
