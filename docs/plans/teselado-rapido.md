---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: F0 medida, sin mergear (teselar la piloto 176 s → 8,6 s con D1 + D2; 20 cadenas en 3 definiciones); faltan F1 (D1 + D2), F2 (D3, a decidir) y F3
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
  quedan D1 + D2.
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
