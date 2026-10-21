---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: F0 medida (D2 corregida: el teselado toma el lock pieza por pieza); faltan F1, F2 (portada de la memoria) y F3 (publicar generar de la piloto)
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
- **F3 (S, verificación)**: `publicar generar` de la piloto, con el tiempo total antes y después.
  Mario mira el PDF del manual.

## Lo que este plan NO hace

- No cambia la secuencia de montaje ni el texto del manual.
- No toca los planos de taller: sus vistas son HLR 2D, no fotos.

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
