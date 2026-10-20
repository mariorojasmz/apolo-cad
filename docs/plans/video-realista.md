---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: contrato escrito y aprobado para lanzar el 2026-10-20 («escribe el plan y lánzalo»); D1–D10 vetables; nada implementado
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

  La foto «realista» del visor (botón) usa el nivel máximo. Por qué: la miniatura de YouTube y
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
