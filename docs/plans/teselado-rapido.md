---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: F0 y F1 en main (primer render_view de la piloto 218 s → 21 s; manual en frío 226 s → 46 s); F2 en main (2026-10-21: la piloto 74 y el layout 53 ya tienen caché de geometría y abren en 0,2 s; D3 descartado); falta F3
descripcion: La primera foto, el primer manual o el primer render de una máquina con cadenas sale en segundos, no en minutos
---

# La primera foto de una máquina con cadenas sale en segundos

## Estado y origen

Lo encontró [manual-rapido](manual-rapido.md) F0 (2026-10-21, § Bitácora). Teselar en frío la
piloto 74 (201 piezas, 19 cadenas) cuesta **~280 s**:
- las cadenas tardan 9–18 s cada una y los piñones ~2 s;
- de los ~12 s de una cadena, `BRepMesh` es 0,7 s: el resto es el Python de `Shape.tessellate`,
  que crea un `Vector` por nodo;
- armar el `polydata` de VTK en bucles Python sumaba hasta 38 s (manual-rapido F1 ya lo pasó a
  numpy).

Lo pagan el primer `render_view` del MCP, el manual en frío, la portada de la memoria (347 s en
frío, F0) y el video VTK de respaldo. El visor no lo paga: dibuja la malla de la DEFINICIÓN una
sola vez y la instancia con su matriz.

## El problema / lo que hay hoy

- **El render tesela por pieza, no por definición.** `kernel/render_comun.teselar`
  (`render_comun.py:48-59`) cachea por `id(shape)`. Dos piezas que instancian la misma
  definición (`Feature.mesh_key` + `matrix`) son dos shapes y se teselan dos veces. El payload
  del visor, en cambio, usa `api/scene._definition_mesh(key)` (`scene.py:95`): una malla por
  definición y una matriz por instancia.
- **La caché vive sólo en memoria y por proceso.** Se pierde al reiniciar la API (o con
  `--reload`) y no la comparten la API y los procesos de la flota.
- **`Shape.tessellate` de build123d es lento** por su Python: un `Vector` por nodo.
  manual-rapido F0 midió que un bucle propio sobre `Poly_Triangulation` baja de ~12 s a ~6 s por
  cadena.

## Decisiones (para vetar)

- **D1. El render usa la malla de la DEFINICIÓN.** Una pieza con `mesh_key` y `matrix` toma la
  malla de su definición, teselada UNA vez y transformada por su matriz al dibujar: en VTK, un
  `vtkTransform` por actor o un actor por instancia sobre el mismo `polydata`. Sirve para
  `render_view`, el manual, la memoria, el GIF y el video VTK. Es lo que ya hace el visor y lo
  que hace el GLB de la tienda.
- **D2. Extracción propia de la triangulación.** Se lee `Poly_Triangulation` de cada cara con
  `BRep_Tool.Triangulation_s`, a numpy y con la ubicación de la cara, en lugar de
  `Shape.tessellate`. Se usa la misma deflexión (0,5 / 0,25) y se compara contra build123d en un
  test: mismos triángulos con tolerancia, mismo orden de caras (lo que necesitan las zonas de
  [seta-de-emergencia](seta-de-emergencia.md)).
- **D3. La malla de render se persiste en la caché de geometría.** Va por definición y firma,
  junto al estado que ya guarda `doc/geomcache.py` (open caliente). Así un reinicio de la API o
  un proceso de la flota no re-teselan. Cambia el formato del blob: se sube `GEOM_CACHE_EPOCH`
  con su motivo. Se mide en F0 si el tamaño lo justifica; si pesa demasiado, se descarta D3 y
  quedan D1 + D2. **Descartada en la F2** (§ Bitácora): el blob va sin malla.
- **D4. La malla de eslabones no se simplifica.** Un LOD que dibujara la cadena como un sólido
  liso cambiaría lo que se ve en el manual y en las fotos de la tienda. Primero se mide cuánto
  dan D1–D3.

## Alternativas descartadas

- **Mallar las cadenas más grueso (más deflexión):** se ven facetadas de cerca y se pierde
  precisión en las fotos.
- **Paralelizar el teselado en hilos:** OCCT y la caché comparten estado (raíz § Concurrencia).

## Fases

- **F0 (S, sólo lectura)**, sobre una COPIA de la base con la piloto 74 y la faja 73:
  - cuántas definiciones distintas hay y cuántas instancias (las 19 cadenas, ¿comparten
    definición?);
  - el tiempo de D1 sólo, D2 sólo y los dos;
  - el tamaño de las mallas de render en el blob (D3).
- **F1 (M, `kernel` + `api`)**: D1 y D2. Tests:
  - render idéntico al de hoy, PNG con tolerancia de píxel, en una escena con instancias;
  - las zonas de la seta siguen;
  - el primer `render_view` de la piloto, antes y después.
- **F2 (S, `doc`)**: D3, si F0 lo justifica. Epoch y test de open caliente con malla de render.
- **F3 (S, verificación)**: el manual y la memoria de la piloto en frío, antes y después.

## Lo que este plan NO hace

- No toca el teselado del visor: ya es por definición.
- No simplifica la geometría de las cadenas (D4).

## Riesgos

- **La triangulación propia se aparta de la de build123d** en orientación de caras o normales.
  Mitigación: el test de D2 compara contra build123d y contra el PNG de hoy.
- **Una instancia con escala o espejo en la matriz** necesita normales correctas. Mitigación:
  F0 lista si hay matrices con determinante negativo; si las hay, se tratan aparte.

## Bitácora

### F0 — medición (2026-10-21)

Sobre una copia de `data/apolo.db` (backup de sqlite) con `APOLO_DB`; scripts en el scratchpad,
no en el repo. Cada modo corrió en su PROPIO proceso: la malla queda guardada en el shape y un
segundo teselado no paga `BRepMesh`. Ninguna cara traía malla al abrir.

- **Definiciones e instancias.**
  - Piloto 74: 201 piezas, 136 instancias de **13 definiciones**. Las cadenas son **20**, no 19
    (19 «rodillo a rodillo» + la motriz), y comparten **3 definiciones**: 10 + 9 rodillo a
    rodillo (dos fases) y la motriz. Las 40 tuercas M12, los 20 piñones, los 20 rodillos y los
    20 ejes son una definición cada uno.
  - Faja 73: 117 piezas, 32 instancias de 13 definiciones, sin cadenas.
  - **Ninguna matriz tiene determinante negativo ni escala** (en las dos). El espejo se trata
    igual (invierte el orden de los triángulos) y lo prueba un test; no hay caso real.
  - En la 74, 98 instancias comparten el TShape con su definición (`place_matrix`); en la 73,
    ninguna (el open caliente deserializa cada forma aparte).
- **Tiempo de teselar las piezas visibles** a resolución de render, hasta numpy:

  | | hoy | D1 sólo | D2 sólo | D1 + D2 |
  |---|---|---|---|---|
  | piloto 74 | 176 s | 29,8 s | 35,9 s | **8,6 s** |
  | faja 73 | 20,2 s | — | — | **4,6 s** |

  «Hoy» = `Shape.tessellate` + la conversión a numpy que ya hace `render_comun._xyz`. Con D1 + D2
  sólo se teselan 3 cadenas (1,6; 2,0 y 3,2 s); el resto de la piloto suma ~2 s.
- **De qué está hecha una cadena** (56 700 nodos, 690 caras): `BRepMesh` 0,4 s, `faces()` 0,1 s,
  los nodos con `poly.Node(i).Coord()` 0,6 s y los triángulos con `poly.Triangle(i).Get()` 0,5 s.
  Recorrer `poly.Triangles()` cuesta 2,7 s: de ahí salían los «~6 s por cadena» de
  manual-rapido F0. La F1 usa `Triangle(i)`.
- **D2 contra build123d**: en las 318 piezas de las dos máquinas, los mismos vértices (≤ 1e-9 mm)
  y los mismos triángulos, en el mismo orden.
- **D1 contra la malla propia de cada instancia**: en 101 de las 136 instancias de la 74 (las 20
  cadenas incluidas) es la misma malla (desvío ≤ 2,3e-13 mm). En las otras 35 de la 74 y en 30
  de las 32 de la 73 los vértices son los mismos, pero `BRepMesh` elige otra diagonal en algunos
  cuadriláteros (de 4/228 a 1438/2534 triángulos): la superficie es la misma y en una cara curva
  cambia apenas el sombreado. Es lo que ya ve el visor. El test de PNG lo mide con tolerancia.
- **D3, tamaño**: las mallas únicas (las definiciones más las piezas sin definición) en
  float32/int32 pesan 5,9 MB en la 74 (78 mallas; 1,3 MB con zlib) y 2,8 MB en la 73 (98 mallas;
  0,7 MB con zlib). El blob de la caché de geometría de la 73 pesa hoy 2,4 MB: D3 lo duplicaría
  en crudo o le sumaría un 30 % comprimido, para ahorrar ≤ 5 s por reinicio en la 73 y ≤ 9 s en
  la 74. **La piloto 74 no tiene caché de geometría**: `pack` devuelve None porque BinTools no
  serializa las 10 cadenas c66…c96 (`serialize_robust` da None), así que abre en frío (12 s)
  siempre. Las dos cosas quedan para decidir en la F2.

**Lo que dice la F0 de las decisiones**: D1, D2 y D4 se sostienen. D3 no se contradice, pero con
D1 + D2 el frío ya baja a segundos: la F2 decide con estos números (y antes tendría que arreglar
la caché de la 74).

### F1 — D1 y D2 (2026-10-21)

- **`kernel/malla_render.py`** (nuevo): `triangular` (D2: `Poly_Triangulation` → numpy con la
  ubicación de cada cara, `Shape.mesh` con la misma deflexión, orden de `faces()`, triángulos
  invertidos en las caras REVERSED y los triángulos por cara contados en la misma llamada),
  `malla_local` (caché por identidad del shape de la definición, con `is`), `malla_instancia`
  (D1: la malla local por la matriz; con determinante negativo invierte los triángulos) y
  `definicion_de(feat, definiciones, forma)` (sólo si la forma que se dibuja es la de la pieza:
  una pose o una sección se teselan solas).
- **`render_comun`**: `teselar`, `teselar_zonas` y `teselar_con_zonas` aceptan
  `(definicion, matriz)`; la caché por `id(shape)` guarda numpy (vértices y triángulos de sólo
  lectura) y siempre los triángulos por cara. `_xyz` deja pasar un arreglo numpy y sigue
  convirtiendo listas de puntos (las cajas del GIF de la dinámica). `mesh.agrupar_por_zona`
  acepta triángulos numpy y devuelve numpy (con una lista, la lista de siempre).
- **Las definiciones llegan como DATO** (el kernel no importa `commands`):
  `services/definiciones.definiciones_de(escena)` da una FOTO `{mesh_key: shape}` de las
  instancias de la escena. **Decisión**: un servicio y no `DEFINITIONS` directo, porque la
  publicación (video VTK) no puede importar `commands` (`tests/test_capas_publicacion.py`) y
  porque la foto protege del desalojo de la LRU. La pasan `render_view`
  (`routers/render.py`), el GIF del estudio (`routers/motion.py`), el GIF de la dinámica
  (`api/sims.py` → `extraer_gif_dinamica`), el manual (`routers/deliverables.py` →
  `extraer_manual(definiciones=)`, que la guarda en `ManualExtraido.definiciones`) y el video
  VTK de la publicación (`EscenaViva(definiciones=)`, `extraer_piezas(definiciones=)`).
  `assembly_manual` acepta `definiciones` (sin ella, como antes).
- **Fuera de la F1**: la portada de la memoria y el respaldo matplotlib de `render_view` siguen
  con `Shape.tessellate` (`render.render_scene_png`): es la F2 de manual-rapido.
- Dos tests cambiaron sólo la forma de leer un vértice (`v[i][2]` en vez de `v[i].Z`): la malla
  de render es numpy (`test_seta_emergencia`, `test_manual_rapido`).
- **Tests** (`tests/test_teselado_rapido.py`, 14):
  - D2 = `Shape.tessellate` (mismos vértices, mismos triángulos en el mismo orden, mismos
    triángulos por cara que `triangulos_por_cara`) en una caja, un sólido con agujero (caras
    REVERSED), una esfera, un compuesto de copias colocadas (caras con ubicación) y la seta;
    sobre una forma ya mallada más fina usa esa malla, como build123d;
  - D1: en una escena de 7 piezas (3 placas, 2 ejes y 2 setas), `triangular` corre 3 veces, una
    por definición; cada instancia tiene los nodos y la superficie de la malla propia de la
    pieza; una pose, una definición desalojada o una pieza taladrada no usan la definición;
  - un espejo invierte los triángulos y el volumen firmado de la malla sigue positivo (normales
    hacia afuera);
  - las zonas de la seta salen en cada instancia con los mismos rangos que sin D1;
  - el PNG de `render_view` y el de la `EscenaViva` del manual contra el teselado de main (pieza
    por pieza con `Shape.tessellate`), también tras un open caliente: medido, ≤ 0,009 % de
    píxeles distintos y en 1 nivel de 255; el test exige ≤ 0,1 % de píxeles con más de 16;
  - `GET /api/render.png` tesela 3 mallas para las 7 piezas.
- **Medido** por el endpoint con `TestClient`, sobre copias frescas de la base, piloto 74 (la PC
  compartida con otras sesiones; el open en frío, 70–87 s, no cuenta):

  | | antes (main) | después |
  |---|---|---|
  | primer `render_view` | 217,8 s | **21,3 s** |
  | segundo `render_view` | 12,9 s | 10,5 s |
  | manual en frío | 225,8 s | **46,0 s** |

  El PNG de la piloto antes y después difiere en el 0,056 % de los píxeles, en 2 niveles de 255
  como mucho. El segundo `render_view` ya no tesela: lo que queda es VTK sobre 1,3 M triángulos.

### F2 — la caché de la piloto y D3 (2026-10-21)

Sobre copias de `data/apolo.db` (backup de sqlite, una por medición) con scripts en el
scratchpad; cada open en su propio proceso. La PC estaba cargada por otras sesiones: los tiempos
en frío varían ±50 %.

- **Por qué la piloto no tenía caché.** Las cadenas de `create_chain` son la FUSIÓN de 30+ copias
  colocadas de un rodillo y unas placas (`cadena_por_rodillos`). BinTools las escribe, pero al
  leerlas `ReadGeometry` pide un índice de curva que no está en la tabla
  (`Standard_OutOfRange NCollection_IndexedMap::FindKey`), cruda y tras `BRepBuilderAPI_Copy`.
  Pasa en las versiones 1, 2 y 4 del formato (4 = la actual); la **VERSION_3 la lee bien**. No es
  una cara ni la ubicación: cada una de las 690 caras round-trip-ea sola, la definición (sin
  ubicación) falla igual, y el mismo lazo SIN fundir (un `Compound`) pasa siempre. Depende de la
  fusión de forma caprichosa: con las capas reales de ASA 40, una recta de 8 eslabones falla y una
  de 12 no. Una pieza que no se empaca deja al proyecto entero sin caché.
- **Encuesta** (74, 73, 38, 28, 53 y 72; 799 piezas): la VERSION_3 round-trip-ea todas, con las
  mismas caras en el mismo orden (área y centro por índice: las zonas de acabado van por índice).
  El **layout 53 tampoco tenía caché**: una pieza sólo la lee la VERSION_3.
- **La cura** (`brep_io.serialize_robust(cache_geometria=True)`, sólo desde `geomcache.pack`):
  crudo → copia → VERSION_3, verificando cada uno. Va al final: lo que ya se empacaba sale con los
  mismos bytes. El sandbox no la pide (su respaldo es STEP; cambiarlo cambiaría lo que entrega
  `run_script`). **Sin bump de epoch**: el mismo `unpack` lee las dos versiones (BinTools lee la
  suya de la cabecera) y un blob v6 sigue valiendo; lo que antes fallaba no tenía caché.
- **Open** (`ProjectStore.load`, 3 seguidos sobre la misma copia):

  | | antes | después |
  |---|---|---|
  | piloto 74 | 4,8–7,2 s, siempre frío (sin caché) | 1.º frío + `pack` 14,5 s; luego **0,21 s** |
  | layout 53 | 10,9–12,8 s, siempre frío | 1.º 13,1 s; luego **0,10–0,14 s** |
  | faja 73 | 0,2–2,3 s caliente | igual (mismo blob, 2 370 571 B) |

  Blob: 7 845 819 B en la 74 y 2 761 610 B en la 53. `pack` de la 74: 1,2–4,0 s; antes gastaba
  1,9–2,5 s para devolver None, y lo repetía en cada flush del autosave (sin caché guardada, la
  marca `_GEOM_MARK` nunca quedaba).
- **D3, descartado.** Tras un open caliente, teselar las piezas visibles a resolución de render
  (D1 + D2) cuesta 2,9–4,8 s en la 74 y 2,0–3,8 s en la 73: es lo único que D3 ahorraría, una vez
  por proceso y proyecto. En contra:
  - poblarla: el `pack` del open frío corre ANTES de todo render, así que la malla sólo entraría
    teselando dentro de `pack` (segundos bajo `STATE_LOCK` en el autosave) o con un camino nuevo
    render → SQLite que cruza `kernel`, `api` y `doc`;
  - el tamaño: +1,3 MB con zlib sobre los 7,8 MB de la 74 (F0) y el empaque en cada flush.

  Medido además lo que ya pasaba sin querer: BinTools guarda por defecto la triangulación que
  tenga la forma, así que un autosave DESPUÉS de un render metía la malla en el blob: 19,8 MB en
  la 74 (`pack` 2,2 s) y 9,3 MB en la 73, para teselar en 2,35 s y 0,63 s en vez de 2,9 y 2,0. Por
  coherencia con el descarte, el blob va **sin malla** (`cache_geometria=True`): pesa lo mismo
  haya habido render o no.
- **Queda anotado, no se hace**: en la 74, 98 instancias comparten el TShape con su definición y
  el blob guarda cada una entera (las 20 cadenas son ~5 MB de los 7,8). Guardarlas como
  (definición, matriz) bajaría el blob y el `pack`, y el open caliente volvería a compartir el
  TShape como el frío. Cambia el formato del blob (epoch).
- **Tests** (`tests/test_geomcache_cadenas.py`, 5): el síntoma (la cadena no round-trip-ea por el
  camino del sandbox y sí con `cache_geometria`); un documento con cadena se empaca y el open
  caliente re-ejecuta 0 comandos y da las mismas firmas, escena, matrices, volúmenes, bbox y
  caras en el mismo orden que el frío; `ProjectStore` la puebla en el open frío y el segundo es
  caliente; tras teselar, el blob pesa lo mismo y sus formas no traen triangulación; sin
  `cache_geometria` los bytes son los de `serialize_shape`.
