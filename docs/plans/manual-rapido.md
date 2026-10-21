---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: F0, F1, F2 y F2b hechas; F2 y F2b sin mergear, sobre teselado-rapido F1 (piloto: manual 12 538 s → 425 s en frío; memoria 1 060 s → 52 s; juego de planos sombreado 1 301 s → 55 s; GA sombreado 986 s → 38 s; los cuatro van como job por MCP); falta F3 (publicar generar de la piloto)
descripcion: El manual de montaje de una máquina sale en segundos, no en 23 minutos, y mientras se arma Apolo no se congela
---

# El manual de montaje sale en segundos y no congela Apolo

## Estado y origen

Lo encontró video-tienda-pulido F3 (2026-10-20, § Bitácora): en `publicar generar` de la piloto
(proyecto 74), los entregables suman 3 693 s y **el manual de ensamblaje se lleva 1 381 s**.
Mario delegó en Claude el orden de los hitos ([docs/hitos.md](../hitos.md)); éste es el hito F,
«es el cuello de la publicación».

## El problema / lo que hay hoy

- **El render es matplotlib.** El manual tiene 12 fotos: la portada y 11 pasos. Todas salen de
  `kernel/render.render_scene_png` (`drawing/assembly_manual.py:457` y `:469`), que dibuja con
  matplotlib (`kernel/render.py:221`).
  - Hasta 177 piezas, cada foto tarda ≤ 30 s.
  - Desde que entran las 19 cadenas (196 piezas), tarda 180–290 s.
  - Las fotos suman 1 376 de los 1 381 s.
- **Todo eso corre BAJO `STATE_LOCK`.** `GET /api/assembly-manual.pdf`
  (`api/routers/deliverables.py:285-312`) llama a `assembly_manual` dentro del `with STATE_LOCK`.
  Mientras se arma el manual de la piloto, la API no atiende ninguna mutación ni lectura del
  documento durante ~23 min. Eso viola la regla de los dos locks (raíz § Concurrencia y locks:
  bajo `STATE_LOCK` sólo se EXTRAE; lo pesado va fuera con su propio lock).
- **La memoria de cálculo** también hace su foto de portada con matplotlib (256 s en total,
  bitácora de video-tienda F3).
- **Ya existe un render VTK rápido y persistente.** `kernel/render_vivo.EscenaViva`
  (`render_vivo.py:140`, con `mover` y `fotograma`) teesela UNA vez, saca un fotograma en
  ~8–40 ms y ya lo usan el video de la tienda y el GIF de la dinámica. `render_view` del MCP
  usa `render_snapshot_vtk` (`render_vtk.py:311`), con el patrón de los dos locks.

## Decisiones (para vetar)

- **D1. Las fotos del manual salen de VTK con una sola escena.**
  1. Bajo `STATE_LOCK` se extraen las mallas de TODAS las piezas del manual una sola vez, como
     hace el video.
  2. Fuera, bajo `RENDER_LOCK`, una `EscenaViva` dibuja la portada y cada paso.
  3. Para cada paso cambia sólo la visibilidad (lo acumulado), el resaltado (lo nuevo en su
     color, lo previo en gris) y la cámara, que es estable: es el mismo `frame_bbox` de hoy.

  Por qué: el teselado de las cadenas se paga una vez y no 12, y VTK dibuja en milisegundos lo
  que matplotlib dibuja en minutos.
- **D2. El endpoint sigue la regla de los dos locks.** `assembly_manual` se parte en tres:
  - `extraer_manual(doc, scene)`, bajo `STATE_LOCK`: secuencia (`pasos_manual`), mallas,
    colores, metadatos y filas de piezas, todo como datos puros;
  - `fotos_manual(snapshot)`, fuera, bajo `RENDER_LOCK`;
  - `componer_manual(...)`: las láminas `SheetModel`, puras.

  Lo mismo para la foto de portada de la memoria de cálculo.

  **Corregida por la F0** (§ Bitácora): teselar en frío las mallas de la piloto cuesta ~280 s,
  así que «las mallas bajo `STATE_LOCK`» de un tirón congelaba la API casi 5 min. La extracción
  queda en dos pasos: `extraer_manual` (secuencia, textos, cajetín y la foto id/shape de cada
  pieza, bajo UNA toma del lock) y `teselar_manual(ex, STATE_LOCK)`, que tesela tomando el lock
  PIEZA POR PIEZA (la mutación que llegue espera, como mucho, una pieza: ~12–20 s una cadena en
  frío). Las formas son las de la foto del primer paso (ningún executor muta un shape en sitio):
  el manual es el del documento tal como estaba al pedirlo.
- **D3. Mismo aspecto que `render_view`.** Usa la tabla de acabados de
  [visor-realista](visor-realista.md) F1 y las zonas de [seta-de-emergencia](seta-de-emergencia.md)
  cuando F3 las dé en VTK, sin aristas negras gruesas. El manual se ve como el resto de los
  entregables, no como un gráfico de matplotlib.
- **D4. Respaldo sin OpenGL.** Si VTK no puede abrir contexto (un servidor sin GPU ni OSMesa),
  el manual cae a matplotlib como hoy y lo dice en el log, igual que `render_view` sin
  `vtk_only` (`api/routers/render.py:175`). Por qué: el entregable no puede desaparecer.
- **D5. La secuencia y el texto no cambian.** `services/montaje.py` (F1b de video-tienda), las
  instrucciones, las filas y la tabla de contenidos quedan igual. Sólo cambian las imágenes y
  dónde corren.

## Alternativas descartadas

- **Bajar la resolución de matplotlib o simplificar las cadenas**: ahorra tiempo pero empeora
  el entregable, y el lock sigue tomado.
- **Paralelizar las 12 fotos de matplotlib en procesos**: es más complejo, multiplica la RAM
  y no arregla el lock.
- **Renderizar en el navegador** (video-realista): el manual se pide por la API, también desde
  el MCP, sin navegador.

## Fases

- **F0 (S, sólo lectura)**: medir sobre una COPIA de la base, con la piloto 74:
  - el tiempo de cada foto con matplotlib hoy;
  - lo mismo con `EscenaViva` en un prototipo del scratchpad;
  - cuánto tiempo se queda tomado `STATE_LOCK` hoy y con D2;
  - el mismo análisis para la portada de la memoria.
- **F1 (M, `drawing` + `kernel` + `api`)**: D1, D2, D4 y D5. Tests:
  - las láminas salen iguales en número y textos;
  - cada foto tiene píxeles del color de resaltado donde van las piezas nuevas;
  - `STATE_LOCK` queda libre mientras se dibujan las fotos (un test que muta durante el manual
    no espera);
  - el respaldo sin OpenGL funciona.

  Medir el manual de la piloto antes y después.
- **F2 (S, `drawing` + `api`)**: la portada de la memoria de cálculo por el mismo camino.
- **F2b (M, `drawing` + `api` + MCP)**: las isométricas SOMBREADAS de los planos por el mismo
  camino. Por qué (lo encontró F2, § Bitácora): el juego de planos con `shaded=true`
  (`drawing_set`, 16 fotos: 1 073 s de 1 237 en la piloto) y la hoja de conjunto GA sombreada
  (`drawing/spec`: 1 140 s de 1 246) dibujan con matplotlib BAJO `STATE_LOCK` y por MCP pasan
  los 120 s; los dos los pide `publicar generar`.
  - `compose_sheet(shaded=True)` deja RESERVADO el lugar de la isométrica (centro, caja máxima,
    rótulo) y la escena a fotografiar; las vistas de línea (HLR), las cotas, las tablas y el
    cajetín se componen como hoy, bajo el lock.
  - Las fotos se extraen en esa misma toma del lock, se teselan pieza por pieza (con las
    definiciones) y se dibujan fuera, bajo `RENDER_LOCK`, todas en UNA `EscenaViva` (cada foto
    cambia la cámara y lo visible); sin OpenGL, matplotlib sobre las mismas mallas con aviso.
    Luego se pegan en su lugar reservado.
  - Fondo BLANCO y recorte al modelo, como la isométrica de hoy (matplotlib transparente y
    `bbox_inches="tight"`): en el papel la pieza ocupa el cuadrante igual que antes, sin el
    degradado de `render_view`.
  - `GET /api/drawingset.pdf` y `POST /api/drawing/spec` aceptan `?async=true` →
    `ENTREGABLES_JOBS`; las tools `drawing_set` y `drawing` esperan como una mutación con recibo
    (`tools/entregable.py`). Sin `?async`, la respuesta de siempre (la publicación no cambia).

  Tests: las mismas láminas y textos que main en un caso chico (congelados antes del cambio);
  las fotos con píxeles de la máquina; `STATE_LOCK` libre mientras se dibuja; respaldo sin
  OpenGL; los jobs (éxito, 400 igual que directo, 409 si cambia el proyecto). Medir el juego y el
  GA de la piloto antes y después.
- **F3 (S, verificación)**: `publicar generar` de la piloto, con el tiempo total antes y después.
  Mario mira el PDF del manual.

## Lo que este plan NO hace

- No cambia la secuencia de montaje ni el texto del manual.
- No toca las vistas de línea de los planos (HLR 2D, siguen bajo el lock): F2b sólo mueve sus
  isométricas SOMBREADAS, que sí son fotos.

## Riesgos

- **VTK sin contexto en un servidor sin GPU.** Mitigación: D4.
- **Cambia el aspecto del PDF del manual de las máquinas ya publicadas.** Mitigación: el
  paquete publicado no se regenera solo; el aspecto nuevo entra en la próxima versión que
  publique Mario.

## Bitácora

### F0 — medición (2026-10-21)

Sobre una copia de `data/apolo.db` (backup de sqlite) con `APOLO_DB`, piloto 74 (201 piezas, 10
pasos de montaje: hoy son 10, no 11). Scripts en el scratchpad, no en el repo. Las corridas
compartieron la máquina (12 hilos; matplotlib usa uno): los números absolutos son de esta PC.

- **Hoy (matplotlib, todo bajo `STATE_LOCK`)**, por el endpoint con `TestClient`: portada (201
  piezas) **1 760 s**; pasos 1–5 (17–177 piezas) 16, 21, 66, 228 y 230 s; paso 6 (196 piezas,
  entran las 19 cadenas) **2 107 s**. Cada foto re-tesela todo lo que dibuja (`_draw_view` llama
  a `shape.tessellate` sin caché) y matplotlib ordena ~1,3 M triángulos. El lock queda tomado
  todo el manual. El total sale en la bitácora de F1 (la corrida sigue).
- **Prototipo con UNA `EscenaViva`** (sin zonas, resalte con el acento del video):
  - lo que iría bajo el lock sin teselar: `pasos_manual` 1,8 s + textos, cajetín y herraje
    10,0 s + `apariencias_render` 0,04 s;
  - **teselado en frío 277,7 s** (caliente 0,003 s): las 19 cadenas tardan 9–18 s cada una y los
    piñones ~2 s. De los ~12 s de una cadena, `BRepMesh` es 0,7 s: el resto es el Python de
    `Shape.tessellate` (un `Vector` por nodo; un bucle propio sobre `Poly_Triangulation` sólo
    baja a 6 s, no vale la pena aquí);
  - fotos: ventana 2,0 s, cada fotograma 0,3–4,6 s, pero crear los actores de las cadenas tardó
    hasta 38 s: el `polydata` de `render_comun` arma puntos y celdas en bucles Python.
- **Portada de la memoria**: matplotlib **2 322 s** bajo el lock hoy; con VTK, teselado frío
  347 s (lock) + render 81 s (los mismos bucles del `polydata`).

**Lo que contradice el plan**: D2 suponía una extracción barata; con el teselado en frío serían
~290 s de lock seguidos. Se corrige D2 (arriba): el teselado toma el lock pieza por pieza. Y la
F1 suma dos arreglos del `kernel` que la F0 señaló: `polydata` con numpy y la conversión
vértices → numpy cacheada por lista (la pedían la caja y el `polydata`), los dos con el mismo
PNG byte a byte. D1, D3, D4 y D5 quedan como estaban.

### F1 — el manual con una escena VTK y fuera del lock (2026-10-21)

- `drawing/manual_fotos.py`: `extraer_manual` (una toma del lock) → `teselar_manual(ex, candado)`
  (una toma por pieza) → `fotos_manual` (fuera; `_fotos_vtk` bajo `RENDER_LOCK`, o
  `_fotos_matplotlib` con aviso en el log) → `componer_manual` (puro). `assembly_manual` queda
  como atajo de las cuatro para quien es dueño del documento (tests); el endpoint
  `GET /api/assembly-manual.pdf` no lo usa. Los textos y la composición de cada lámina no
  cambiaron de lugar (`assembly_manual.py`).
- `kernel/render_vivo`: `PiezaViva.partes` y `extraer_piezas(zonas=True)` (las zonas de la seta,
  D3); `EscenaViva.mostrar(plenas, fantasmas)` cambia sólo la visibilidad de actores ya creados
  (el fantasma se crea la primera vez: el mismo gris de `render_vtk`, ahora
  `render_comun.GRIS_FANTASMA`/`OPACIDAD_FANTASMA`), y `png()`. El video no cambia: sin
  `zonas=True` y sin `mostrar`, todo es como antes.
- `kernel/render.render_mallas_png`: el respaldo matplotlib sobre las mallas ya teseladas, sin
  OCCT (D4: no vuelve a tomar el lock).
- `render_comun.polydata` con numpy y `_xyz` cacheado por lista: el mismo PNG byte a byte (se
  comparó con el de bucles sobre una escena con zonas).
- Las fotos tienen el aspecto de `render_view` (700 × 546 con el `size_px` de siempre): fondo
  degradado, acabados, zonas, aristas finas; lo ya montado en gris translúcido.
- Tests (`tests/test_manual_rapido.py`): las láminas de un caso chico salen con los MISMOS textos
  que en main (congelados antes del cambio); cada foto muestra lo nuevo en su color, lo montado
  sin su color y lo que falta, nada, y el color nuevo cae donde la cámara proyecta la pieza;
  `STATE_LOCK` se toma y se muta el documento mientras el endpoint dibuja; el teselado toma el
  candado una vez por pieza; sin OpenGL sale con matplotlib y lo dice; la seta llega partida
  por zona; `polydata` trae los mismos puntos y celdas. `test_montaje` espía ahora
  `extraer_manual`.

Medido por el endpoint sobre la misma copia (piloto 74), dos pedidos en un proceso:

| | antes | frío | caliente |
|---|---|---|---|
| total | 12 538 s (3 h 29 min) | 425 s | 56 s |
| `STATE_LOCK` | 12 492 s seguidos | 9 s + 201 tomas (la mayor, 19,8 s) | 5,5 s + 201 tomas de ~0 s |
| fotos | 12 485 s (11 fotos) | 38 s (`RENDER_LOCK`) | 36 s |

«Antes» se midió con la PC compartida (otras suites corrían a la vez): las fotos con las cadenas
tardaron 1 590–2 530 s cada una, más que los 180–290 s de la bitácora de video-tienda F3; la
proporción no cambia. En frío manda el teselado (353 s, repartidos en 201 tomas del lock): es
el Python de `Shape.tessellate` y lo paga también `render_view`. Queda como pendiente para
otro plan (mallar las cadenas con menos nodos o cachear la malla de render por firma, como la
caché de geometría); la F2 (portada de la memoria) lo heredará igual. «Caliente» = con la caché
de teselado de render llena en el proceso (tras un manual o un `render_view` de la máquina).
Los PDF (antes y después) quedaron en el scratchpad de la sesión, no en el repo.

### F2 — la portada de la memoria por el camino del manual, y la memoria como job (2026-10-21)

- `drawing/foto_escena.py` (nuevo): las fases del manual para UNA foto. `extraer_foto` (bajo el
  lock, sin teselar: colores, apariencias con zonas, la foto id/shape de lo visible y las
  definiciones de `services.definiciones.definiciones_de`) → `teselar_foto(ex, STATE_LOCK)` (una
  toma por pieza, con la malla de la definición) → `dibujar_foto` (fuera: `EscenaViva` bajo
  `RENDER_LOCK`, 620 × 484 con el aspecto de `render_view`; sin OpenGL, `render_mallas_png` sobre
  las mismas mallas y aviso en el log). `formas_de`, `definiciones_usadas` y `teselar_formas` los
  comparte ahora el manual (`manual_fotos.py` ya no los repite).
- `calc_report.peso_memoria`: el peso del cajetín (OCCT) se calcula bajo el lock y llega en
  `meta`; `calc_report(None, …)` compone fuera. Las reglas, los requisitos y el cajetín siguen
  extrayéndose en la misma toma de siempre: las secciones y los textos no cambian.
- **Job** (pedido por la ola 5 de verificación por MCP: `calc_report(path=…)` sobre la piloto
  daba «timed out» a los 120 s del httpx y nunca escribía el PDF): `GET /api/calc-report.pdf` y
  `GET /api/assembly-manual.pdf` aceptan `?async=true` → 202 + recibo en una cola PROPIA,
  `ENTREGABLES_JOBS` (`common._job_entregable`), para no retrasar mutaciones ni co-simulaciones.
  Un job guarda JSON: el PDF queda en `ARCHIVOS` (`jobs.Archivos`, en memoria, los últimos 20) y
  el resultado trae `archivo` = `GET /api/archivos/{clave}`. El job revalida el proyecto en su
  primera toma del lock (`_mismo_proyecto` → 409 si se abrió otro). Sin `?async`, la respuesta de
  siempre (la publicación no cambia). MCP: `tools/entregable.py` — `calc_report` y
  `assembly_manual` piden el job, esperan como una mutación (`_submit_and_wait`) y bajan el PDF a
  `path`; si tarda, el RECIBO, y `get_job(id)` (nuevo param `path`, oculto en el chat) lo guarda
  donde se pidió. **El manual también va por job**: en frío son 46 s en la piloto
  ([teselado-rapido](teselado-rapido.md) F1), pero 425 s antes de eso y en una PC cargada o una
  máquina mayor pasa los 120 s igual que la memoria. Golden re-congelado (revisado: `get_job` con
  `path`, dos docstrings y cinco llamadas nuevas: job ok, recibo, recoger con y sin `path`).
- Tests: `tests/test_memoria_rapida.py` (las 3 páginas de un caso chico con los MISMOS textos y
  cantidad de imágenes que en main, congelados antes del cambio; la portada con los colores de
  sus piezas; lo oculto no sale y sin nada visible no hay foto; la foto VTK de 400 × 312; el
  `STATE_LOCK` se toma y se muta mientras se dibuja; el teselado toma el candado una vez por
  pieza; sin OpenGL sale con matplotlib y lo dice) y `tests/test_entregables_job.py` (memoria y
  manual por job con el mismo PDF para bajar; un job fallido da el mismo 400 que en directo; el
  proyecto cambiado en cola da 409; archivo desconocido, 404; un lote en `JOBS` corre mientras la
  memoria dibuja).

Medido por el endpoint (`TestClient`) sobre copias de `data/apolo.db`, piloto 74, cada corrida en
su proceso (la PC compartida con otras sesiones):

| | antes (base) | después, frío | después, caliente |
|---|---|---|---|
| total | 1 060 s | **52 s** | 40 s |
| foto de portada | 1 018 s (matplotlib) | 7,6 s teselar + 9,3 s VTK | 0,2 + 6,5 s |
| `STATE_LOCK` | 1 060 s seguidos | ~35 s seguidos + 201 tomas (la mayor, 2,3 s) | ~33 s + 201 de ~0 s |

El PDF de la piloto sale con las mismas 11 páginas y el mismo texto (pypdf, página por página);
cambia sólo la foto. Lo que queda bajo el lock de un tirón ya no es la foto: son las reglas
(`structure_rules`, 28 s: conectividad, vuelco, uniones) y el peso. Queda anotado para otro plan.
F0 había medido la portada en 2 322 s con la PC más cargada; la proporción no cambia.

**Otros entregables que dibujan con matplotlib bajo `STATE_LOCK`** (no se tocan en F2; tiempo de
`render_scene_png` en la piloto, base, la PC compartida):

| entregable | dónde | foto(s) | tiempo |
|---|---|---|---|
| juego de planos con `shaded=true` (`GET /api/drawingset.pdf`, tool `drawing_set`; la publicación lo pide así) | `sheet.compose_sheet` (`shaded`) vía `sheetset`: el conjunto y CADA lámina por pieza | 16 (1 + 15 láminas) | 1 073 s de 1 237 (el conjunto, 916 s) |
| hoja de conjunto GA (`POST /api/drawing/spec` con `shaded`, la publicación) | `sheet.compose_sheet` | 1 | 1 140 s de 1 246 |
| `GET /api/render.png` en multivista o sin OpenGL (`render_view` del MCP exige VTK) | `routers/render.py` | 1 | no se mide: la publicación usa `vtk_only` |
| `POST /api/commands/preview` sin `data` (PNG del fantasma) | `routers/commands.py` | 1 | no es entregable |

Medidos en un proceso, el GA primero (el juego ya encontró las caras malladas por `BRepMesh`) y
con la suite completa corriendo a la vez: los números absolutos son altos (video-tienda F3 midió
462 y 231 s los dos entregables enteros), pero en los dos la foto es ~90 % del tiempo y todo va
bajo el lock. La cotización y la lámina de instalación no dibujan 3D. El juego de planos y el GA tampoco van
por job: con la piloto pasan los 120 s del MCP (`drawing_set`, `drawing`) igual que la memoria.

### F2b — las isométricas sombreadas de los planos fuera del lock, y los planos como job (2026-10-21)

- `drawing/fotos_planos.py` (nuevo): `compose_sheet(shaded=True, foto_diferida=True)` compone la
  lámina como siempre (HLR, cotas, tablas y cajetín, bajo el lock) y sólo RESERVA la isométrica
  en `model.hueco_iso` (`HuecoIso`: centro, caja, rótulo, dónde insertar imagen y rótulo para
  conservar el orden de antes, y la escena). `extraer` (misma toma del lock, sin teselar) →
  `revelar(…, STATE_LOCK)` (teselado pieza por pieza y dibujo fuera). `sheet_set(foto_diferida=)`
  marca en cada lámina por pieza su `origen` (la pieza del documento): su foto lleva la
  apariencia de esa pieza, sin zonas (el sólido puede ser sólo una parte del comando).
- **Una sola ventana**: las 16 fotos del juego salen de UNA `EscenaViva` (crear la ventana
  cuesta ~2 s, F0). Los ids llevan el prefijo de su foto (las láminas por pieza repiten el id
  sintético «P»); cada foto hace `encuadrar(bbox)` (nuevo en `kernel/render_vivo`) y `mostrar`
  sólo lo suyo.
- **Decisión: fondo blanco y recorte al modelo** (`EscenaViva(fondo=)`, nuevo; el video y el
  manual siguen con el degradado): la isométrica de matplotlib era transparente y recortada
  (`bbox_inches="tight"`); con el degradado de `render_view` y la esfera de `ResetCamera`, la
  máquina quedaba chica dentro de un recuadro gris. En la piloto, la máquina ocupaba el 59 % del
  ancho de la foto del GA (matplotlib encuadra un cubo) y ahora el 98 %: sale más grande en la
  misma caja de la lámina.
- Sin `foto_diferida` (`compose_sheet` llamado por quien es dueño del documento: tests,
  scripts) hace las tres fases de corrido, también con VTK. El respaldo sin OpenGL es
  matplotlib sobre las mismas mallas (`foto_escena._foto_matplotlib`), con aviso en el log.
- `GET /api/drawingset.pdf` y `POST /api/drawing/spec` aceptan `?async=true` →
  `_job_entregable` (`ENTREGABLES_JOBS`), revalidan el proyecto en su primera toma del lock
  (409) y, sin `?async`, responden lo de siempre (la publicación no cambia). En `drawing/spec`
  la foto sólo se dibuja para pdf y svg (el DXF no lleva imágenes: antes se dibujaba igual).
  MCP: `drawing_set` usa `entregable.pedir`; `drawing`, `entregable.plano` (con `path`, como
  `pedir`; sin él, el SVG en texto o `{ok, bytes, hint}` como antes). Golden re-congelado
  (revisado: tres docstrings, las rutas por job y dos llamadas nuevas: recibo del juego y
  `get_job` al `path` del recibo; las salidas de las llamadas viejas no cambian).
- Tests (`tests/test_planos_sombreados.py`, 15): el juego y el GA de un caso chico con las
  MISMAS láminas, textos en su orden y cantidad de imágenes que main (congelados antes del
  cambio en `tests/data/planos_sombreados_main.json`); el GA con las dos piezas a color y cada
  lámina por pieza sólo con la suya; el rótulo sobre la foto; lo oculto no sale y sin nada que
  fotografiar no hay foto ni rótulo; `STATE_LOCK` se toma y se muta mientras se dibuja (juego y
  GA); el teselado toma el candado una vez por pieza y hay UNA ventana; sin OpenGL, matplotlib y
  lo dice; `compose_sheet` sin diferir sigue dibujando; por job: el archivo para bajar (pdf y
  svg), el mismo 400 que en directo y 409 si cambia el proyecto.

Medido por el endpoint (`TestClient` con el arranque real) sobre copias de `data/apolo.db`,
piloto 74; «antes» con el código de la base (F2) desde una copia en el scratchpad, la PC
compartida con otra sesión y, el último tramo, con la suite corriendo:

| | antes | después |
|---|---|---|
| juego de planos sombreado (19 láminas, 16 fotos) | 1 301 s | **55 s** (53 s tras el GA) |
| `STATE_LOCK` del juego, la toma más larga | 1 294 s | 43 s (el HLR) |
| hoja GA sombreada | 986 s | **38 s** en frío, 32 s tras el juego |
| `STATE_LOCK` del GA, la toma más larga | 977 s | 28 s (el HLR) |

Los PDF de la piloto salen con las mismas páginas, el mismo texto (pypdf, página por página) y
la misma cantidad de imágenes; cambian sólo las fotos. Lo que queda bajo el lock de un tirón es
el HLR de las vistas de línea (OCCT), que este plan no toca.
