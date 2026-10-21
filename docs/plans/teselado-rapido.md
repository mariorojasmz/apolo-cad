---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: contrato escrito el 2026-10-21 (hito G de docs/hitos.md); nada implementado
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
