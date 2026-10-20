---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: F0–F3 hechas (2026-10-20): «Calidad alta» y acabados con textura; reloj virtual y codificación en la API (F2); F3 graba en el navegador el MISMO guion de montaje con rótulos, la máquina andando y la vuelta final (`publicar generar --render navegador`, botón «Grabar video»; 65 s de la 74 en 7 min en una Intel UHD), con encuadre por ángulo; el trazado de rayos usará three-gpu-pathtracer 0.0.23 (MIT); faltan F4 y F5
descripcion: El video de YouTube y de la tienda sale del visor con calidad de foto de catálogo (y trazado de rayos de noche), generado solo, sin instalar Blender
---

# El video de YouTube muestra la máquina como si fuera una foto

## Estado y origen

Mario, al ver el piloto con los acabados y la sombra de contacto (2026-10-20): «¿esto es lo más
real posible que se puede obtener? ¿no podemos llegar a un realismo como Unreal Engine 5?». Se le
explicaron dos capas: un visor mejorado en tiempo real y un render por trazado de rayos para la
tienda. Eligió el visor mejorado y descartó Blender: «no quiero bajar blender». Después precisó:
«justo quiero que la máquina se vea lo más realista posible para el video a youtube», y pidió:
«sí, escribe el plan y lánzalo».

La máquina y los videos se construyen en la PC de escritorio: i7 de 8 núcleos, 32 GB de RAM y
una RTX 4070 Ti. La laptop sólo desarrolla.

Requisito heredado de [publicacion-tienda](publicacion-tienda.md) (§ Estado y origen): «el video
se tiene que generar de forma automática». Un botón en el visor no basta: `publicar generar`
tiene que poder producirlo sin que nadie lo mire.

## El problema / lo que hay hoy

- **El video de la tienda lo dibuja VTK en el servidor.** Lo hacen `kernel/render_vivo.py` y
  `publicacion/video.py` (276 líneas), y lo codifica `media/codificar.py` con un ffmpeg EXTERNO
  (`APOLO_FFMPEG` o el PATH).
  - VTK sólo hace raster con sombreado simple: no tiene oclusión ambiental, ni entorno de luz,
    ni reflejos.
  - Sus colores salen de la tabla única de acabados (`library/apariencia.py`,
    [visor-realista](visor-realista.md) F1), pero sin su PBR completo.
- **El visor ya tiene lo más avanzado de Apolo:**
  - PBR de three.js 0.169 (`ui/package.json:17`), ACES (`scene-setup.ts:19`), sombras PCF y la
    sombra de contacto ([piso-con-sombra](piso-con-sombra.md));
  - IBL de `RoomEnvironment` (`viewport/environment.ts:9-11`): un cuarto sintético, sin
    softboxes ni recortes de luz que el metal pueda reflejar;
  - una cadena de passes de `RenderPass` → `OutlinePass` → destello → `OutputPass`
    (`viewport/pipeline.ts:93-106`), sin oclusión ambiental ni antialias temporal (sólo MSAA ×4
    en el target);
  - acabados lisos: un color, una rugosidad y un metalness por acabado, sin textura.
- **El visor ya reproduce la máquina andando** (visor-realista F2, `viewport/marcha/`) y la
  secuencia de montaje existe como servicio (video-tienda-pulido F1b, `services/montaje.py`).
  Falta que algo grabe eso cuadro por cuadro a una resolución fija.
- **Lo que pesa un video**: 60 s a 30 fps son 1 800 cuadros.
  - En raster, a ~0,1 s por cuadro, son minutos.
  - Con trazado de rayos, a 1–30 s por cuadro según la GPU y las muestras, son horas: F0 lo mide
    en la 4070 Ti.

## Lo que se revisó antes de escribir esto

- **Unreal Engine 5**: es una app nativa, y cada máquina tendría que exportarse a un proyecto de
  Unreal. Para un video offline, el trazado de rayos llega igual o más lejos. Descartado.
- **Blender Cycles**: el mejor resultado offline, pero Mario no quiere instalarlo. Descartado
  por decisión de Mario.
- **Un motor de trazado de rayos propio**: meses de trabajo para quedar por debajo de Cycles.
  Descartado.
- **`three-gpu-pathtracer`** (npm, autor gkjohnson): trazado de rayos progresivo en WebGL sobre
  la MISMA escena three.js del visor. Licencia (se espera MIT), versión compatible con three
  0.169 y su denoiser, a verificar en F0.
- **three trae passes propios** en `three/examples/jsm/postprocessing`: `GTAOPass` (oclusión
  ambiental), `SMAAPass` y `TAARenderPass`. No hace falta una dependencia nueva para el visor
  mejorado.
- **Grabar sin bajar nada**: Windows trae Edge (Chromium). Puede correr sin ventana
  (`--headless=new`) con la GPU de la máquina y abrir la UI de la API local en modo grabación. No
  hace falta bajar el Chromium de Playwright.
- **La física no cambia.** MuJoCo corre en el servidor sobre cascos convexos sacados de OCCT
  (`physics/`). El visor sólo DIBUJA las poses que la simulación ya calculó (visor-realista D4,
  «calcular ≠ mirar»). Mejorar cómo se ve no toca ni una masa, ni un contacto ni un paso de la
  simulación.

## Decisiones (para vetar)

- **D1. Visor mejorado, sin assets descargados.** Va en `pipeline.ts` y `environment.ts`, partidos
  en módulos si llegan al tope. Agrega:
  - `GTAOPass` (oclusión ambiental);
  - antialias SMAA en vivo y TAA al grabar;
  - un **estudio procedural**: una escena de softboxes emisivos (luz principal, de relleno y de
    contorno) que `PMREMGenerator` convierte en el IBL, en lugar de `RoomEnvironment`. Por qué:
    da los recortes de luz que leen el metal y no depende de un HDRI bajado (CSP, licencia,
    tamaño).

  Todo con un interruptor «calidad» (alta/normal) para PCs flojas.
- **D2. Acabados con textura procedural.** La tabla única (`library/apariencia.py`, regenera
  `acabados.json`) gana parámetros de textura:
  - galvanizado con lentejuelas;
  - acero cepillado (anisotropía);
  - goma de la banda con grano;
  - pintura con piel de naranja leve.

  Las texturas se generan en el navegador (ruido en canvas o shader) desde esos parámetros, sin
  imágenes en el repo. VTK sigue leyendo sólo color, rugosidad y metal. Por qué: las piezas
  lisas son lo que más delata un render.
- **D3. Reloj virtual para grabar.** En modo grabación, el bucle del visor no usa el tiempo real:
  avanza `1/fps` por cuadro y espera a que el cuadro esté listo (TAA acumulado, o las muestras del
  trazado de rayos). Va con un render target de resolución fija: 1920×1080 por defecto,
  3840×2160 opcional. Por qué: un cuadro lento no puede saltarse ni duplicarse.
- **D4. Los cuadros van a la API, que codifica.**
  1. `POST /api/video/grabacion` abre una sesión.
  2. `POST …/{sesion}/cuadro/{n}` sube cada PNG, que se guarda en `data/`.
  3. `POST …/{sesion}/cerrar` codifica con `media/codificar.py`: el mismo ffmpeg, la misma música
     (`--musica`, [video-tienda-pulido](video-tienda-pulido.md) D7) y el mismo CRF.

  No toma `STATE_LOCK`: es E/S pura. Por qué: un solo codificador para todos los videos.
- **D5. Lo que se graba es el MISMO guion del video de hoy.** Son las etapas y rótulos de
  `services/guion_video.py` y `services/montaje.py`, más la máquina andando (la serie de
  visor-realista F2/F3) y un giro final. El navegador lo pide a la API en JSON y lo reproduce.
  Los rótulos se dibujan en 2D sobre el cuadro, con el mismo texto y la misma regla de contraste
  (D4 de video-tienda-pulido). Por qué: no dos guiones que diverjan.
- **D6. Dos niveles de calidad.**
  - **Rápido**: visor mejorado + TAA; un video de 60 s en minutos.
  - **Máximo**: `three-gpu-pathtracer` en cada cuadro, con N muestras + denoiser; de noche.

  La foto «realista» del visor (botón) usa el nivel máximo. Mario (2026-10-20): con 1–2 h por
  video el máximo «no es viable ahora, pero igual lo quiero». Se implementa (F4) y queda
  disponible, pero no como nivel por defecto. Por qué: la miniatura de YouTube y
  las fotos de la tienda valen el tiempo; el video entero, según el saldo de GPU.
- **D7. Automático con el navegador que ya está.** `publicar generar --render navegador`:
  1. busca Edge o Chrome instalados (Edge viene con Windows);
  2. los lanza sin ventana con la GPU contra `http://127.0.0.1:<puerto>/?grabar=<sesion>`;
  3. espera el cierre de la sesión de D4.

  Sin navegador, avisa y cae a VTK. El botón «Grabar video» del visor hace lo mismo a la vista.
  Por qué: cumple «el video se tiene que generar de forma automática» sin bajar nada.
- **D8. VTK queda como respaldo, no se borra.** Sirve para `publicar generar` sin navegador o sin
  GPU, y para los renders de planos y del MCP (`render_view`). Por eso:
  - [visor-realista](visor-realista.md) F4 («la máquina andando» renderizada por VTK) queda
    **reemplazada** por la F3 de este plan;
  - video-tienda-pulido F2 (D3/D4: aspecto del video VTK) se reduce a lo que el respaldo
    necesita: aristas finas y cierre legible.

  Mario veta si prefiere mantenerlas.
- **D9. La física no se toca.** Este plan no cambia `physics/` ni la serie de la marcha: sólo
  cómo se dibuja. Un cambio de física que haga falta para que el video se vea bien va a su plan
  (V8.x).
- **D10. Se mide en la PC de escritorio.** Los tiempos que deciden el nivel por defecto (cuadros
  por segundo del rápido, segundos por cuadro del máximo) se toman en la 4070 Ti. La laptop sólo
  da la cota baja.

## Alternativas descartadas

- **Blender Cycles**: Mario no quiere instalarlo.
- **Unreal Engine 5**: app nativa, exportación por máquina, sin ventaja para un video offline.
- **Motor de trazado de rayos propio**: meses de trabajo para un resultado peor que el de una
  librería.
- **Grabar la pantalla (captura del escritorio)**: no da resolución fija, salta cuadros y graba
  lo que tape la ventana.
- **Chromium de Playwright**: es otra descarga de ~150 MB; Edge ya está instalado.
- **Un HDRI de Poly Haven**: es un asset descargado de 1–20 MB, con su licencia que cuidar. El
  estudio procedural se controla desde el código.

## Fases

- **F0 (S, sólo lectura + scratchpad)**. Se mide antes de tocar nada:
  1. Verificar la licencia y la versión de `three-gpu-pathtracer` compatible con three 0.169, y
     su denoiser.
  2. Prototipo en el scratchpad con la piloto (74): GTAO + estudio procedural, en fps a 1080p.
  3. Trazado de rayos de un cuadro, en segundos por cuadro y muestras hasta que se ve limpio.
  4. Que Edge sin ventana use la GPU (no SwiftShader).
  5. Cuánto tarda subir un PNG de 1080p a la API.

  Laptop primero; escritorio en F5 (o antes por `ssh escritorio` si se puede lanzar el navegador
  allá).
- **F1 (M, `ui` + `library`)**: D1 y D2. Visor mejorado con el interruptor de calidad; tabla de
  acabados con parámetros de textura y `acabados.json` regenerado. Gates:
  - vitest de los módulos nuevos;
  - fps medido en la piloto;
  - capturas antes y después.

  Depende de F0.
- **F2 (M, `api` + `ui` + `media`)**: D3 y D4. Reloj virtual, render target fijo, endpoints de
  grabación y codificación. Primer video: la piloto girando y andando (serie de visor-realista
  F2/F3), nivel rápido. Tests de la API (sesión, orden de cuadros, cierre, música) y de reloj
  virtual (N cuadros, ni uno saltado). Depende de F1 y de visor-realista F3 (cadenas y banda que
  avanzan).
- **F3 (M, `ui` + `api` + `publicacion`)**: D5 y D7.
  - El guion (montaje + rótulos + marcha + giro) se reproduce en el navegador.
  - `publicar generar --render navegador` lanza Edge sin ventana y cae a VTK si no hay.
  - Botón «Grabar video».

  Reemplaza visor-realista F4 (D8). Depende de F2.
- **F4 (M, `ui`)**: D6. Nivel máximo con `three-gpu-pathtracer` por cuadro y botón «Foto
  realista». Gate: misma pose → misma imagen con semilla fija; tiempo por cuadro medido.
  Depende de F2.
- **F5 (S, verificación en el escritorio)**. Video de 60 s de la piloto (montaje + marcha +
  giro), en los dos niveles y con la música de Mario. Se miden el tiempo total y el tiempo por
  cuadro en la 4070 Ti. Lo juzga Mario, en YouTube como no listado si quiere.

## Lo que este plan NO hace

- No toca la física (D9) ni la serie de la marcha.
- No borra VTK (D8).
- No sube nada a YouTube: eso lo hace Mario.
- No hace realidad virtual, ni un recorrido de cámara a mano, ni una edición de video con cortes
  libres: el guion manda.
- No cambia el GLB de la tienda ([vista-3d-tienda](vista-3d-tienda.md)), aunque D2 puede
  reusarse ahí después.

## Riesgos

- **Edge sin ventana cae a SwiftShader (render por CPU)** y el video tarda horas en el nivel
  rápido. Mitigación: F0 lo mide; el modo grabación lee `WEBGL_debug_renderer_info` y aborta con
  un mensaje claro si no hay GPU.
- **`three-gpu-pathtracer` no soporta algún material** (anisotropía, transmisión) o se rompe con
  three 0.169. Mitigación: F0 lo verifica; se fija la versión exacta y, si hace falta, se sube
  three con su propio test.
- **Ruido en el nivel máximo**: pocas muestras dan grano que parpadea entre cuadros. Mitigación:
  semilla fija, denoiser y muestras mínimas medidas en F0.
- **Disco**: 1 800 PNG de 1080p pesan ~5 GB, y en 4K ~20 GB. Mitigación: se borran al codificar
  (salvo `--conservar-cuadros`) y la sesión avisa del espacio libre al abrir.
- **Ruptura del visor de todos los días**: GTAO cuesta GPU. Mitigación: el interruptor de calidad
  (D1); en «normal» el visor queda como hoy.

## Bitácora

### F0 (2026-10-20): medido en la laptop

Laptop de desarrollo: i7-1355U con **Intel UHD integrada** (ANGLE D3D11), es decir la cota BAJA
(D10). Arnés temporal en el scratchpad, fuera del repo:
- la escena de la piloto (74, 201 piezas, 1,06 M triángulos) sale de una COPIA de
  `data/apolo.db` por TestClient (`POST /api/projects/74/open` + `GET /api/scene`);
- una página de vite arma el visor con los módulos REALES de `ui/src/viewport/` (`buildMesh`,
  `scene-setup`, `environment`, sombra de contacto, destello);
- el prototipo agrega GTAO, SMAA y el estudio procedural.

Mide a 1920×1080 con DPR 1:
- **ms sinc.**: ms por cuadro sincronizado con la GPU (un `readPixels` de 1 px tras cada
  cuadro, cámara orbitando);
- **fps rAF**: fps reales por `requestAnimationFrame` durante 3 s.

Los dos lanzados en Edge sin ventana (`--headless=new`, perfil temporal propio).

**1. `three-gpu-pathtracer`** (consultado con `npm view` y el README publicado en unpkg, sin
instalar nada):
- licencia MIT en todas las versiones;
- la última (0.0.27) pide `three >= 0.185` y WebGPU (`WebGPUPathTracer`);
- la 0.0.24 pide `>= 0.180`;
- **la última compatible con three 0.169 es la 0.0.23** (2024-06-07): WebGL2,
  `WebGLPathTracer`, peer `three >= 0.151` y `three-mesh-bvh >= 0.7.4`. La 0.7.x pide
  `three >= 0.151`; la 0.8.x, `>= 0.159`.
- Denoiser de la 0.0.23: `DenoiseMaterial`, un pase final basado en glslSmartDeNoise que también
  tonemapea. No trae OIDN.
- Materiales: sólo `MeshStandardMaterial` y `MeshPhysicalMaterial` (los del visor). Sin
  geometría instanciada ni buffers intercalados; todas las texturas con el mismo wrap y filtro.
- La anisotropía no figura en el README: F4 la verifica.
- Decisión para F4: fijar la 0.0.23 exacta, o subir three a ≥ 0.185 con su propio test. Subir
  three es un cambio grande: el visor entero cambia de versión.

**2. Visor mejorado** (GTAO + estudio + SMAA) en la piloto:

| variante | ms sinc. | fps sinc. | fps rAF |
|---|---|---|---|
| hoy (RoomEnvironment, MSAA ×4) | 41,4–48,7 | 20,5–24,1 | 33–34 |
| sólo estudio procedural (MSAA ×4) | 40,2 | 24,9 | 33,4 |
| hoy sin MSAA | 24,5 | 40,9 | 52,6 |
| estudio + SMAA (MSAA ×4) | 56,6 | 17,7 | 23,7 |
| estudio + GTAO (MSAA ×4) | 87,5 | 11,4 | 14,8 |
| estudio + GTAO + SMAA (MSAA ×4) | 108,5 | 9,2 | 13,3 |
| estudio + GTAO a media resolución + SMAA (MSAA ×4) | 91,2 | 11,0 | 14,8 |
| **estudio + GTAO + SMAA, SIN MSAA** | 49–61 | 16,5–20,4 | 19,6–25,8 |

Lectura:
- El estudio procedural no cuesta por cuadro: el PMREM se arma una vez.
- El costo de GTAO es su SEGUNDA pasada de la escena (normales + profundidad). Con 1 M de
  triángulos en una GPU integrada manda el vértice, no el píxel: bajar el GTAO a media
  resolución casi no ahorra.
- Lo que sí ahorra es quitar el MSAA ×4 del render target HalfFloat: SMAA lo reemplaza. Con eso,
  «alta» cuesta ~25–45 % más que hoy en la laptop (de 34 a ~20–26 fps rAF).
- Decisión para F1: «alta» = estudio + GTAO + SMAA sin MSAA; «normal» = hoy (MSAA ×4,
  RoomEnvironment).
- Intento descartado: compartir la profundidad del `RenderPass` con el GTAO para ahorrar la
  segunda pasada. El composer alterna dos render targets cuadro a cuadro, y adjuntar la misma
  `DepthTexture` a los dos es un lazo de lectura-escritura. Queda para cuando haga falta.

Capturas (1920×1080, el canvas sobre el fondo del visor), en el scratchpad de la sesión,
`f0/salida/`:
- vista general: `captura-hoy.png` y `captura-alta.png`;
- de cerca, motorreductor y transmisión: `captura-hoy-cerca.png`, `captura-alta-cerca.png` y
  `captura-alta-msaa0-cerca.png`.

Se ven así:
- el estudio da más contraste;
- el galvanizado de los rodillos deja de verse blanco lavado;
- la tornillería zincada lee reflejos;
- la oclusión oscurece el motor bajo el larguero y los rincones de la guarda.

**3. Trazado de rayos de un cuadro**: NO medido. Exige instalar `three-gpu-pathtracer`, y este
paso sólo podía consultar el paquete publicado. Va a F4 (en el escritorio, F5): segundos por
cuadro y muestras hasta que se ve limpio.

**4. Edge sin ventana usa la GPU**: sí. `WEBGL_debug_renderer_info` dice `ANGLE (Intel, Intel(R)
UHD Graphics … Direct3D11)`, no SwiftShader, con Edge 155 y `--headless=new`, sin banderas de
GPU. En el escritorio (4070 Ti) se confirma en F5.

**5. PNG de 1080p**:
- pesa 1,45–1,97 MB;
- `canvas.toBlob` tarda 230–730 ms en la laptop (más con más detalle);
- subirlo por HTTP local (POST a un servidor de vite como sustituto del endpoint de F2) tarda
  16–33 ms.

El cuello es CODIFICAR el PNG, no subirlo. A ~0,3–0,7 s por cuadro, 1 800 cuadros son 10–20 min
sólo de PNG en la laptop. F2 mide en el escritorio y, si pesa, prueba codificar fuera del bucle
o subir el RGBA crudo.

**Pendiente de F5 (escritorio, 4070 Ti)**: fps de «alta» a 1080p y 4K, el trazado de rayos por
cuadro y Edge sin ventana con la GPU NVIDIA.

### F1 (2026-10-20): visor mejorado y acabados con textura

**D1, visor mejorado** (`ui/src/viewport/`, módulos nuevos; `Viewport.tsx` no se tocó):
- `estudio.ts` (73 líneas): la sala gris en degradé y cuatro softboxes emisivos (principal del
  lado de `LIGHT_OFFSET`, relleno, contorno y cenital), en Z arriba.
- `environment.ts` (44): `crearEntorno` arma con PMREM el IBL de cada calidad la primera vez que
  se pide y lo cambia en caliente. «normal» = `RoomEnvironment`; «alta» = el estudio.
- `calidadVista.ts` (118): `GtaoMaquina`, un `GTAOPass` cuya pasada de normales sólo dibuja
  `group` (sin piso, grilla, gizmo, tiradores ni aristas). También tiene `SMAAPass` y el
  interruptor: en «alta» los dos pases prendidos y el render target SIN MSAA (lo que dijo F0);
  en «normal», MSAA ×4 y los pases apagados.
  - `ajustar` (≤ 3 Hz, sólo en «alta») escala el radio y el grosor del GTAO con la diagonal de
    la máquina (2 % y 1 %; mínimo 5 mm) y le pone una caja de recorte.
  - También copia los planos de sección al material de normales. Si no, con el corte puesto la
    oclusión saldría de la pieza entera.
- `calidad.ts` (58): store propia, con «alta» por defecto. Si nadie eligió y la GPU es integrada
  o por software, arranca en «normal»:
  - integradas o por software: Intel salvo Arc, SwiftShader, llvmpipe, Mali, Adreno…;
  - el nombre de la GPU sale de `WEBGL_debug_renderer_info`, que lee el pipeline al armarse;
  - la elección de la persona se recuerda en `localStorage` (con try/catch).
- `pipeline.ts` (149 → 180):
  - orden de pases: Render → GTAO → contorno → destello → Output → SMAA;
  - sigue a la store con `subscribe` y `calidad.ajustar` corre antes de componer;
  - `Pipeline.calidad` queda expuesto para F2.
- Botón: «Calidad alta / normal» en la barra del modo Completo, y el redondo «Calidad alta»
  (ícono de destellos) en el visor. Los dos leen la store directamente, no pasan por Viewport.
- TAA al grabar NO va aquí: es del reloj virtual de F2 (D3).

**D2, acabados con textura**:
- `library/apariencia.py`:
  - nuevo `Textura(tipo, escala_mm, variacion_color, variacion_rugosidad, anisotropia)` y
    `TIPOS_TEXTURA`;
  - `acabados.json` regenerado (con `tipos_textura`);
  - `apariencia()` (lo que lee VTK) NO cambia: sigue con color, rugosidad, metal y opacidad.
- Valores:

| acabado | textura |
|---|---|
| galvanizado | lentejuelas 80 mm: color 0,15, brillo 0,5 |
| inox cepillado | cepillado 30 mm: anisotropía 0,8 |
| acero mecanizado | cepillado 40 mm: anisotropía 0,45 |
| aluminio | cepillado 50 mm: anisotropía 0,5 |
| caucho | grano 4 mm, sólo brillo 0,25 |
| PVC de banda | grano 3 mm, sólo brillo 0,3 |
| hierro fundido | grano 10 mm |
| acero pintado | piel de naranja 12 mm, sólo brillo 0,15 (leve) |

  En lo pintable (pintura, goma, PVC) el color no varía: manda el que eligió la persona.
- `textura.ts` (141): genera en el navegador, con semilla fija, un `map` (factor de albedo) y
  un `roughnessMap` por acabado, con el `Ruido` periódico de `relieve.ts`.
  - Las lentejuelas son celdas de Voronoi: cada cristal tiene su tono y su brillo.
  - El color y la rugosidad del material se compensan por el promedio del mapa: el tono medio
    sigue siendo el de la tabla.
  - Con anisotropía, `materials.ts` usa `MeshPhysicalMaterial`, y las rayas van a lo largo de U
    de las UV de caja.
- Decisión propia: las texturas van en las DOS calidades. Cuestan una lectura de textura; lo
  caro es el GTAO, que sí se apaga en «normal».

**Medido con el pipeline REAL** (`crearPipeline` en el arnés de F0, piloto 74, 1920×1080,
Intel UHD, Edge sin ventana; fps rAF / fps sincronizando la GPU en cada cuadro):

| vista | normal | alta |
|---|---|---|
| general | 35,0 / 29,9 | 26,3 / 21,3 |
| de cerca (motorreductor) | 29,9 / 25,2 | 21,4 / 18,7 |

«Alta» cuesta ~25 % de los fps en la GPU integrada. Por eso la laptop arranca en «normal» y la
4070 Ti en «alta». En la GPU del escritorio lo mide F5.

Capturas, en el scratchpad de la sesión, `f0/salida/`: `captura-f1-normal.png`,
`captura-f1-alta.png`, `captura-f1-normal-cerca.png` y `captura-f1-alta-cerca.png` (las de
antes son las de F0). En «alta» el galvanizado de los rodillos muestra sus lentejuelas y la
oclusión marca el motor bajo el larguero.

Intento descartado: lentejuelas con variación de color 0,2. Se leían manchadas a 1 m; quedó en
0,15.

Tests:
- vitest 253 → 272 (+19): `calidad.test.ts` (11) y `textura.test.ts` (8);
- pytest: `test_apariencia.py` +19 (rango de la textura en cada uno de los 17 acabados, las
  cuatro de D2 y que VTK no reciba la textura);
- `npm run build` verde.

Sin verificar: la UI servida por la API (la de :8000 es de Mario). El arnés usa el pipeline real
pero no el componente `Viewport` ni el botón.

### F2 (2026-10-20): reloj virtual, grabación y codificación en la API

Medido en la laptop (i7-1355U, **Intel UHD integrada**: cota baja, D10). El video de prueba salió
del visor REAL servido por una API del worktree sobre una COPIA de `data/apolo.db` (puerto 8766,
grabaciones en el scratchpad), en el panel de navegador del escritorio.

**D4, API** (`api/routers/video.py`, router nuevo; sesiones en `media/grabacion.py`):
- `POST /api/video/grabacion` (ancho, alto, fps, `formato` jpeg|png, `cuadros`) abre la sesión y
  devuelve lo que ocuparán los cuadros y el disco libre: `aviso` si pasan del 50 % del libre, 507
  si no caben.
- `POST …/{sesion}/cuadro/{n}` con el JPEG o el PNG crudo de cuerpo. Pillow lee sólo la cabecera:
  formato o tamaño equivocado → 400 con el motivo. Pueden llegar desordenados; uno repetido → 409
  (es un error del reloj, no un reintento). Se escribe a `.parcial` y se renombra.
- `POST …/{sesion}/cerrar` (`musica`, `salida`, `conservar_cuadros`): exige 0…N−1 sin huecos
  (si no, 400 con cuáles faltan), los decodifica con Pillow hacia el MISMO `Codificador` del video
  de la tienda (BT.709, CRF 18) y mezcla la música con `mezclar_musica`. Borra los cuadros salvo
  `conservar_cuadros`. Si la codificación falla, los cuadros QUEDAN y la sesión pasa a «error»:
  se puede volver a cerrar.
- `GET …/{sesion}` da el estado (con `codificados` mientras codifica) y `DELETE` la descarta.
- Sin `STATE_LOCK`: E/S pura, con un lock hoja propio. Sesiones en memoria; los cuadros, en
  `data/grabaciones/<sesion>/` (`paths.grabaciones_dir`).

**D3, visor** (`ui/src/viewport/grabacion/`, módulos nuevos; `Viewport.tsx` sólo cambió las
tareas y publicó `window.__apolo.grabar`):
- `reloj.ts`: el cuadro n vale `n/fps`. `recorrerCuadros` dibuja en orden, de a uno, y deja hasta
  4 fotos codificándose y subiendo en paralelo. Al primer error para, espera a las que estaban en
  vuelo y lo relanza.
- `pipeline.ts`: las tareas reciben `ahora` (el reloj del cuadro) y nadie lee el reloj real;
  `modoGrabacion` fija el tamaño con DPR 1 (el canvas se ve escalado con `object-fit: contain`),
  para el bucle y deja fuera ViewCube y controles.
- `modo.ts` + `acumulado.ts`: «alta» forzada sin tocar la elección guardada; el `RenderPass` se
  reemplaza por un pase que promedia 16 muestras con corrimiento subpíxel (Halton 2,3) en un
  HalfFloat, por tandas de 4 (entre tandas suelta el hilo con `MessageChannel`, que no se frena
  con la pestaña de fondo). El mapa de sombras se rehace una vez por cuadro, no por muestra.
  Fuera grilla, ejes, gizmo, tiradores, medida, contorno, destello y SMAA.
- Decisión propia: no es el `TAARenderPass` de three. Ese acumula entre llamadas al composer, y
  repetir el composer repetiría el GTAO por muestra. El pase propio acumula aparte y el GTAO corre
  una vez sobre el promedio.
- `captura.ts`: el canvas es transparente, así que la foto se arma en un lienzo 2D (fondo del visor
  + `drawImage` en el mismo hilo del render) y `toBlob` codifica después.
- `guion.ts` + `encuadre.ts`: el giro (360° suavizado alrededor de Z, desde la dirección de la
  vista) y la marcha (`saltar(n/fps)` cada cuadro: tiempo absoluto, sin deriva). La cámara se
  acerca lo justo para que la caja de la máquina entre en el 16:9 durante todo el giro.
- Sin GPU (SwiftShader, llvmpipe) la grabación se niega con un mensaje, salvo `permitirSinGpu`.

**JPEG o PNG, medido** (Edge sin ventana, una captura real de la piloto a 1080p, 10 cuadros):

| formato | ms por cuadro | KB | PSNR tras H.264 CRF 18 |
|---|---|---|---|
| PNG | 113 | 1 684 | 46,2 dB |
| JPEG 0,95 | 42 | 352 | 43,5 dB |
| JPEG 0,98 | 40 | 510 | 43,9 dB |
| WebP 0,95 | 454 (88 con 4 en paralelo) | 224 | — |

- `toBlob` de PNG y JPEG no gana nada en paralelo: Chromium los codifica en serie.
- Decisión: JPEG 0,95 por defecto (2,7× más rápido, 5× menos disco: 1 800 cuadros ≈ 0,6 GB en
  vez de 3 GB) y PNG a pedido para cuando haga falta sin pérdida. Los −2,7 dB no se ven, y YouTube
  recodifica muy por debajo.
- El PNG de F0 (230–730 ms) era más lento que el de hoy (113 ms): otra captura y otra medición.

**Primer video**: la faja 73 girando y andando, con la marcha del brief (`j_eje_motriz` a
0,37 m/s y la banda `c119`) y `duracion_s: 10` (la de 3 s por defecto quedaba corta). Nivel
rápido: 1920×1080, 30 fps, 16 muestras.

| | |
|---|---|
| cuadros | 300 (10 s) |
| por cuadro (dibujar 16 muestras + foto + subida) | 0,55 s |
| cuadros | 165 s |
| codificar en la API | 13 s |
| total | 178 s |
| MP4 | 2,0 MB (H.264 High, BT.709, 300 fotogramas) |

- 4K (3840×2160, 15 cuadros): 0,58 s por cuadro, casi lo mismo que a 1080p. En la Intel UHD
  manda el vértice (16 pasadas de 1 M de triángulos), no el píxel.
- Al terminar, el visor vuelve a su tamaño, calidad, cámara y bucle; la carpeta de la sesión queda
  sólo con el `video.mp4`.
- El video y una tira de 4 cuadros quedaron en el scratchpad de la sesión (`f2-video/`). El arnés
  y la copia de la base se borraron.

Intentos fallidos:
- La primera prueba (1 s) usó el encuadre del visor tal cual: la máquina salía chica y corrida,
  porque la ventana era 4:3. De ahí `encuadre.ts`.
- `encuadre.ts` con 16 ángulos de prueba dejaba salirse una esquina un 1 % entre muestras; con 36
  (cada 10°), no.

Tests:
- pytest `test_video_grabacion.py` +28, con ffmpeg real; los que codifican se saltan sin él:
  sesión, defaults, parámetros, disco, cuadros desordenados, repetido, malos, 404, faltantes,
  orden de los colores decodificados, PNG, salida elegida, conservar, música, sin ffmpeg (503) y
  descartar.
- `test_rutas_api.py` anota `GET|DELETE /api/video/grabacion/{sesion}`; `test_api_sesion.py`
  cuenta 13 routers.
- vitest 291 → 314 (+23): `reloj.test.ts` 9, `grabador.test.ts` 5 (fetch simulado), `guion.test.ts`
  6 y `encuadre.test.ts` 3.

Sin verificar:
- el escritorio (4070 Ti, F5);
- la música en el flujo del navegador: la cubre el test de la API.
### F3 (2026-10-20): el guion en el navegador y `publicar generar --render navegador`

Medido en la laptop (Intel UHD integrada, cota baja, D10), con una API del worktree en :8766 sobre
una COPIA de `data/apolo.db` y Edge 155 sin ventana (`--headless=new`, perfil temporal dentro de
la carpeta de la sesión, borrado al final).

**D5, un solo guion** (decisión de arquitectura): el navegador no calcula NADA del guion.
`publicacion/plan_navegador.py` arma el plan cuadro por cuadro con las MISMAS funciones del video
de VTK (`linea_tiempo.tramos`, `reparto`, `apariciones`, `revelado`, `peso_roles`, órbita,
fundidos y opacidad del rótulo) y el visor (`grabacion/guionVista.ts`) sólo lo dibuja:
- montaje tanda por tanda sobre las mallas reales (`montaje.ts`: sólo lo visible; el resaltado
  clona el material, emisivo con el acento a 0,3 que se apaga en `RESALTE_S`);
- tarjetas (portada sobre la foto que sube el navegador, cifras, cierre) y rótulos como PNG de la
  API, dibujados con `media/composicion.py` (`media/tarjetas.py`); el compositor del cuadro
  (`captura.ts`) pone rótulo, fundido cruzado y fundido a negro con los valores del plan;
- el rótulo usa `opacidad_rotulo_legible` (`media/contraste.py`): 0,82 de opacidad dejaba el
  texto secundario a ~2,9:1 sobre una pieza blanca; con el panel a la opacidad mínima que da
  ≥ 4.5:1 sobre blanco y sobre negro, se lee sobre cualquier cuadro;
- **la marcha** es una clave opcional del guion (`{"duracion_s", "escenario"}`), una parte nueva
  después de las etapas (la máquina terminada andando, con la órbita lenta) que sigue andando en
  la vuelta final; cuenta en la duración y en los capítulos. El respaldo VTK la quita
  (`sin_marcha`). `publicar guion --marcha escenario.json [--marcha-s 8]`; el botón usa la última
  marcha simulada del proyecto. La serie se carga recién al empezar su parte (`transmision.ts`
  sólo arma lo visible).
- Sólo modo MONTAJE: el de diseño regenera prefijos del log y sigue siendo de VTK (el CLI avisa y
  cae a VTK).

**Fronteras**: `routers/video.py` sigue siendo E/S pura (el test de frontera ahora también mira
`tarjetas.py` y `contraste.py`). El plan lo arma quien abre la sesión: el CLI sobre su copia del
documento; el botón con `POST /api/video/guion` (router nuevo `video_guion.py`, bajo
`STATE_LOCK`). Rutas nuevas de la sesión: `…/plan`, `POST|GET …/foto`, `…/tarjeta/{parte}`,
`…/rotulo/{etapa}`, `…/fallo` (estado «fallida» con motivo `sin_gpu`|`error`); `cerrar` sin cuerpo
usa la música, la salida y `conservar_cuadros` que fijó quien abrió.

**D7**: `publicacion/navegador.py` busca Edge o Chrome (o `APOLO_NAVEGADOR`), lanza
`<url>/?grabar=<sesion>` y espera la sesión (corta si el navegador se cierra o no avanza en 300 s).
Sin navegador, sin GPU o sin WebGL → aviso y VTK. `--render vtk|navegador` (vtk por defecto hasta
medir F5) y `--conservar-cuadros`. Botón «Grabar video» en las dos barras del visor, con aviso de
avance, «Cancelar» y la ruta del MP4 en «Dónde quedó».

**Encuadre** (pedido de Mario a mitad de fase: «que la máquina llene más la pantalla»): en vez
de una distancia fija para toda la vuelta, `distanciasPorAngulo` (`encuadre.ts`) busca la mínima
cada 5° sobre los vértices de las mallas (≤ 6 000, con los 6 extremos de cada pieza), toma el
máximo en ±20° y promedia ±15°: ningún término queda más cerca que su ángulo, y la cámara se
acerca de costado y se aleja de punta sin tirones; margen 0,92. La prueba de cámara usa `near` = 1
(el `near` del visor, ajustado por cuadro en `recorte.ts`, empujaba la cámara lejos). Fracción del
ANCHO que ocupa la máquina en los cuadros 3D (medida con los puntos de las piezas, los mismos
azimuts del guion):

| piloto | antes (medio · mín · máx) | ahora |
|---|---|---|
| 73 (faja) | 43 % · 18 % · 57 % | 61 % · 26 % · 86 % |
| 74 (rodillos) | 43 % · 26 % · 53 % | 51 % · 29 % · 76 % |

El mínimo es la máquina de punta: una faja de 4 m vista por su cabeza no llena el ancho de un
16:9 sin salirse por arriba.

**Videos medidos** (1920×1080, 30 fps, 16 muestras, JPEG 0,95; con el encuadre anterior):

| | 74 montaje + giro | 73 montaje + marcha + giro |
|---|---|---|
| guion | 3 etapas, 65 s, 1 950 cuadros | 6 etapas + 8 s de marcha, 75 s, 2 250 cuadros |
| preparar (abrir + copia del documento + guion) | 31 s | 58 s |
| grabar y codificar | 425 s (0,22 s por cuadro) | 466 s (0,21 s por cuadro) |
| MP4 | 10,7 MB | 10,2 MB |

- La 74 no tiene juntas (`create_roller_conveyor` no las declara): sin modelar no hay marcha que
  simular, así que su video lleva montaje + giro. La marcha se probó en la 73 (`j_eje_motriz` a
  0,37 m/s y la banda `c119`, 23 s simulados).
- Más rápido que F2 (0,55 s por cuadro): durante el montaje se dibuja una parte de la máquina, y
  las tarjetas no pasan por la GPU.
- El botón, probado en el panel de navegador con la 73: guion + plan, foto, avance y «Cancelar»;
  el visor vuelve a su tamaño y a sus 117 piezas, y la sesión cancelada no deja carpeta.
- Videos y hojas de contacto en el scratchpad de la sesión (`f3/video74/`, `f3/video73/`,
  `f3/prueba73b/` con el encuadre nuevo).

Intentos fallidos:
- El resaltado a 0,55 lavaba de azul las tandas grandes (todo el bastidor entra junto): 0,3.
- `publicar guion --marcha` con un JSON escrito por `Set-Content -Encoding utf8` (PowerShell 5.1,
  con BOM) no se leía: ahora `utf-8-sig`.
- `publicar generar --render navegador` de punta a punta sobre la 73 se cortó ANTES del video:
  el manual de ensamblaje en PDF agotó su tiempo en `entregables` (la laptop estaba cargada con
  otras APIs de prueba). No es de esta fase; el camino del video del CLI lo cubren el arnés con
  Edge real (`navegador.renderizar`) y los tests.
- Un primer diseño leía el documento en `routers/video.py` para armar el plan: rompía la frontera
  E/S pura de D4 (`test_la_grabacion_es_e_s_pura_sin_el_documento`). De ahí el plan armado por
  quien abre y `video_guion.py`.

Tests:
- pytest `test_video_navegador.py` +19: marcha en el guion, plan (reparto, apariciones, fundidos,
  reloj de la marcha, sólo montaje), contraste del rótulo, rutas de la sesión con guion, guion del
  botón, fallo, cierre con lo que fijó quien abrió, CLI con un navegador simulado (perfil temporal
  borrado, miniatura con la foto), fallos `sin_gpu`/error y caída a VTK sin la marcha.
- vitest +6 archivos de prueba nuevos o ampliados: `planGuion` 6, `montaje` 4, `registro` 3,
  `grabador` +3, `encuadre` +3 (ninguna pieza sale del cuadro en ningún ángulo con TODOS sus
  vértices, sin tirones, llena más que la distancia fija; `near` del visor).

Sin verificar: el escritorio (4070 Ti, F5), la música en el flujo del navegador (la cubre el test
de la API) y el CLI de punta a punta con los entregables.
