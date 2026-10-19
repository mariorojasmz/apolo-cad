---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: Sólo el plan; nada construido. Espera saldo de tokens
descripcion: Cada máquina publicada trae su modelo 3D liviano y un trozo de HTML para pegar en la tienda: el visitante la gira, la ve con etiquetas y, en el celular, a tamaño real en su taller
---

# El visitante de la tienda gira la máquina en 3D

## Estado y origen

Mario (2026-10-10): «la página web tienda, ¿puede tener una vista en 3D, como lo tiene Apolo?,
para que pueda ver bien?» y «si tengo miles de visitantes, ¿será un reto al servidor o el recurso
que corre es el navegador del usuario?». Se le recomendó un GLB con `<model-viewer>` (lo dibuja
el navegador del visitante; el servidor sólo entrega archivos estáticos) y respondió «sí, crea
el plan». Extiende [publicacion-tienda](publicacion-tienda.md).

## El problema / lo que hay hoy

- El paquete de `publicar generar` trae STEP, planos, BOM, `.apolo`, video y miniatura, pero
  nada para MIRAR la máquina en la web.
- La UI ya exporta glTF binario desde el menú Archivo (`ui/src/viewport/exportGltf.ts`,
  `GLTFExporter` de three.js), pero es del navegador: `publicar` corre en Python sin UI.
- El CAD está en mm y con Z arriba; glTF usa metros e Y arriba. Sin convertir, la realidad
  aumentada mostraría la máquina mil veces más grande o acostada.

## Decisiones (para vetar)

- **D1. GLB generado en el servidor** con el escritor glTF de OCCT (`RWGltf_CafWriter`, el que usa
  `build123d.export_gltf`): un nodo por GRUPO del documento (no por pieza), color de cada pieza,
  metros y Y arriba. Lo produce `publicar generar` junto a los demás entregables.
- **D2. Liviano por diseño**: teselado de vista (no de fabricación) y compresión meshopt con
  `gltfpack` (MIT, binario externo opcional, como ffmpeg). Presupuesto: ≤ 3 MB por máquina; si
  no se cumple, se baja la densidad del teselado y se dice en `generacion.json`.
- **D3. Trozo de HTML listo para pegar**: `vista-3d.html` con `<model-viewer>` (Apache 2.0) en una
  versión FIJA, `poster` = la miniatura que ya existe, el modelo se carga recién al tocar «Ver en
  3D», `ar` con los modos de Android y iPhone, y etiquetas (hotspots) por grupo con su cifra
  principal («Motorreductor 0.37 kW»), leídas del documento.
- **D4. Archivos estáticos, nunca Apolo**: el GLB y el HTML se suben a la tienda o a una CDN; la
  página no llama a la API de Apolo. La guía de subida va en `youtube.txt` o en un
  `LEEME-tienda.txt` del paquete.
- **D5. Sólo apariencia**: el GLB es una malla sin cotas ni planos; los nodos llevan nombres de
  grupo, no los de las piezas. No regala el diseño del paquete completo.
- **D6. Materiales**: los de la tabla única de [visor-realista](visor-realista.md) D5 cuando
  exista; mientras, el color del documento con metalness y roughness por defecto.

## Alternativas descartadas

- Incrustar el visor de Apolo: necesita el servidor de Apolo detrás y trae herramientas de CAD
  que el visitante no usa.
- Sketchfab u otro hosting 3D: depende de un tercero, de su marca y de sus límites; queda como
  opción del lado de Mario, no del paquete.

## Fases

- **F0 (S, sólo lectura + scratchpad)**: exportar la piloto (proyecto 2) con `export_gltf`;
  medir el tamaño crudo y con `gltfpack`; abrirla en un HTML local con `<model-viewer>`; verificar
  escala y eje en la realidad aumentada de un celular.
- **F1 (M, `publicacion` + `kernel`)**: D1 y D2 dentro de `publicar generar`, con test de unidades
  (bbox en metros) y de eje.
- **F2 (S, `publicacion`)**: D3 y D5 (HTML, hotspots por grupo con cifras del documento).
- **F3 (S, `publicacion`)**: el GLB y el HTML entran al zip gratis y al completo; `ficha.json`
  los nombra.
- **F4 (S, verificación)**: Mario pega el HTML en una página de prueba y la abre en su celular.

## Lo que este plan NO hace

- La máquina andando dentro del GLB (rodillos y cadenas girando): llega después de
  [visor-realista](visor-realista.md) F3, como animación glTF.
- La tienda misma (plataforma, pagos): sigue siendo pregunta abierta de publicacion-tienda.

## Riesgos

- iPhone necesita USDZ para la realidad aumentada → `<model-viewer>` lo genera solo a partir del
  GLB; se verifica en F0 y, si falla, se exporta USDZ aparte.
- Máquinas grandes que no entran en 3 MB → D2 avisa; nivel de detalle por grupo si hace falta.

## Bitácora

### F0 (2026-10-19)

Sólo lectura + scratchpad (ningún binario en git). La piloto es el proyecto **74**
(`transportador-rodillos-cadena-2m`, revisión 125: mismo log y manifest que el proyecto), 201
piezas en 6 grupos, todas visibles, con color explícito. Cargada con
`Document.from_apolo_bytes(tolerant=True)` desde la SQLite en modo `ro` (0 suprimidos). El kernel
no tiene export glTF: se usó `RWGltf_CafWriter` de OCP 7.8 (el de `build123d.export_gltf`) con un
documento XCAF propio armado como D1 (raíz → nodo por grupo → instancia por pieza), teselado de
vista del visor (0.4 mm / 0.3 rad) y compresión con `gltfpack` 1.3 (meshoptimizer, MIT) y
`@gltf-transform/cli` 4.5.1 (MIT; Draco vía `draco3dgltf` 1.5.9, Apache-2.0), ambos por npm en el
scratchpad.

**Medidas** (GLB de la piloto; «dibujados» = triángulos que pinta la GPU sumando instancias;
«en archivo» = los que se guardan una sola vez):

| variante | MB | gzip MB | tri dibujados | tri en archivo | mallas / primitivas |
|---|---|---|---|---|---|
| OCCT crudo, una primitiva por cara | 8.35 | — | 1 063 024 | 185 684 | 201 / 17 823 |
| OCCT crudo, `SetMergeFaces(True)` | 6.17 | 1.10 | 1 063 024 | 185 684 | 201 / 201 |
| crudo, teselado grueso (1.0 mm / 0.5 rad) | 3.68 | 0.69 | 672 234 | 117 294 | 201 / 201 |
| crudo sin normales | 3.90 | 1.03 | 1 063 024 | 185 684 | 201 / 201 |
| crudo con cada pieza copiada (sin instancias) | 33.00 | 5.82 | 1 063 024 | 1 063 024 | 201 / 201 |
| `gltfpack -noq` | 5.92 | 1.22 | 1 063 024 | 181 624 | 15 / 17 |
| `gltfpack` (sólo cuantiza) | 3.77 | 1.05 | 1 063 024 | 181 624 | 15 / 17 |
| `gltfpack -c` | 0.85 | 0.16 | 1 063 024 | 181 624 | 15 / 17 |
| `gltfpack -cc` | 0.77 | 0.14 | 1 063 024 | 181 624 | 15 / 17 |
| **`gltfpack -cc -kn`** (candidato) | **0.74** | **0.14** | 1 063 024 | 181 624 | 20 / 20 |
| `gltfpack -cc -kn -noq` | 1.90 | 0.71 | 1 063 024 | 181 624 | 20 / 20 |
| `gltfpack -cc -kn`, teselado grueso | 0.51 | 0.11 | 672 234 | 114 274 | 20 / 20 |
| `gltfpack -cc -kn`, sin normales | 0.45 | 0.24 | 1 063 024 | 181 624 | 20 / 20 |
| `gltfpack -cc -kn` sobre las copias | 0.77 | 0.16 | 1 063 024 | 188 296 | 22 / 22 |
| `gltfpack -cc -kn -si 0.25` | 0.28 | 0.14 | 265 988 | 45 492 | 20 / 20 |
| `gltfpack -cc -kn -si 0.1` | 0.16 | 0.08 | 121 182 | 20 922 | 19 / 19 |
| `gltf-transform quantize` | 4.57 | 1.38 | 1 063 024 | 181 624 | 201 / 201 |
| `gltf-transform meshopt` | 1.07 | 0.26 | 1 063 024 | 181 624 | 201 / 201 |
| `gltf-transform draco` | 2.33 | 1.70 | 1 063 024 | 1 063 024 | 201 / 201 |

- **Piezas repetidas**: las 201 piezas son 31 prototipos (Apolo ya construye instancias, cadenas y
  rodillos, con el MISMO TShape). Las cadenas mandan: el lazo «Cadena rodillo a rodillo» (19
  instancias de 46 k triángulos) más la cadena motriz (que cuelga del grupo Motorreductor) son el
  89 % de los triángulos dibujados y 5.47 de los 6.17 MB crudos. Por grupo, compartido → copiado:
  Cadenas 2.80 → 26.55 MB, Rodillos (160 piezas) 0.27 → 3.28 MB, Motorreductor 2.81 MB igual. Instanciar en el export ahorra el 81 % del crudo (33.0 → 6.17 MB) y 20 s de teselado
  (22.3 → 2.1 s), pero NO el tamaño final: `gltfpack` deduplica mallas iguales por su cuenta
  (0.74 vs 0.77 MB). `-mi` (`EXT_mesh_gpu_instancing`) no cambia nada con `-kn`.
- **Escala y ejes**: bbox del GLB [0, 0, −0.397]–[2.0, 0.77, 0.345] m frente a Apolo
  [0, −345, 0]–[2000, 397, 770] mm → X = x, Y = z, Z = −y, en metros, con las patas en Y = 0. Las
  201 piezas casan con su nodo a < 2 mm (10 piñones «desfasado» dan 6.8 mm por medir la caja de una
  caja girada, no por error), también tras `gltfpack`. `model-viewer` mide 2.000 × 0.770 × 0.742 m
  en las cuatro variantes de la página de prueba.
- **Tiempos** (esta PC): importar OCP/build123d 17 s en frío (una vez por proceso), regenerate
  8.4–10.6 s, teselado + XCAF + escritura 2.1 s (vista) / 1.6 s (grueso), `gltfpack` 0.5 s.
- **Colores**: son 8 materiales, no colores por vértice: no pesan. Las normales sí (37 % del
  crudo), pero sin ellas three.js sombrea plano y los tubos se ven facetados: se quedan.

**Trampas que encontró la F0** (las hereda la F1):

- Una forma UBICADA agregada con `AddShape(shape, False, False)` pierde la ubicación al escribir:
  en la primera pasada 150 de 152 piezas salieron en el origen. Va el prototipo con ubicación
  identidad (`shape.Located(TopLoc_Location())`) + `AddComponent(grupo, proto, shape.Location())`;
  los prototipos se reusan por `IsPartner` (mismo TShape).
- `TCollection_ExtendedString(nombre)` sin `isMultiByte=True` codifica dos veces el UTF-8
  («PiÃ±Ã³n»).
- El auto-nombrado de XCAF bautiza los nodos de instancia «=>[0:1:1:n]» y OCP 7.8.1 no expone
  `RWMesh_NameFormat`: se nombra cada etiqueta de componente con `TDataStd_Name`.
- Sin `SetMergeFaces(True)` el escritor emite una primitiva por cara (17 823 draw calls y 3 MB de
  JSON).
- `gltfpack` sin `-kn` funde y borra nodos de grupo («Bastidor», «Motorreductor» desaparecen):
  D1 y los hotspots de D3 necesitan `-kn` (cuesta 0.03 MB).
- Draco no comparte accessors entre instancias (guarda 1.06 M triángulos): 3× más grande que
  meshopt aquí. Confirma meshopt en D2.
- `<model-viewer>` 4.0.0 NO trae decodificador meshopt: sin
  `self.ModelViewerElement.meshoptDecoderLocation` el GLB de `gltfpack -c` no carga. Se fija
  `https://cdn.jsdelivr.net/npm/meshoptimizer@0.22.0/meshopt_decoder.js` (desde la 1.x el paquete
  ya no publica ese script clásico).
- En una pestaña oculta `<model-viewer>` no carga hasta ser visible (`loading` por defecto):
  como D3 pone `src` recién al tocar «Ver en 3D», la página usa `loading="eager"`.

**Lo que cambia en las decisiones**:

- **D1**: se confirma el escritor de OCCT, con las cuatro trampas de arriba. No hace falta
  `build123d.export_gltf` ni `trimesh`.
- **D2**: el presupuesto de 3 MB sobra (0.74 MB, 0.14 MB con gzip). El límite real son los
  **triángulos dibujados** (1.06 M, 89 % cadenas): para celular y Quick Look conviene un tope en
  triángulos (propuesta: ≤ 300 k), bajando primero la densidad de las cadenas (nivel de detalle por
  grupo, el «LOD» de Riesgos) y no la de toda la máquina; `-si 0.25` global llega a 266 k. Queda a
  la vista de Mario en el celular. La palanca de D2 pasa de «MB» a «triángulos».
- **D3**: el HTML lleva el `meshoptDecoderLocation` fijo y `loading="eager"`. Si Scene Viewer
  (realidad aumentada de Android por HTTP) no lee meshopt, D3 necesita un segundo GLB para la RA
  (Draco o sin comprimir; `<model-viewer>` sólo separa `ios-src`, así que en Android habría que
  cambiar `src` antes de abrir Scene Viewer) o servir por HTTPS para que la RA vaya
  por WebXR (three.js sí decodifica meshopt).

**Lo que falta que pruebe Mario** (la página, los 4 GLB y un `LEEME.txt` con los comandos
PowerShell están en `scratchpad\vista3d\web\` de la sesión de la F0): abrir
`vista-3d.html` en el celular por la red local, anotar tiempo de carga y medidas, y en la RA
(iPhone Quick Look con el USDZ que arma `<model-viewer>`; Android Scene Viewer con cada variante)
confirmar tamaño real, de pie sobre el piso, colores y fluidez con 1.06 M vs 266 k triángulos.
