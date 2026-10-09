---
estado: en curso
nota: aprobado 2026-10-08; la F0 espera la máquina piloto (transportador de rodillos motorizado, nuevo); F3 no depende de ella; preguntas de tienda, licencias e idioma sin contestar
descripcion: Una máquina terminada sale de Apolo como paquete listo para la tienda (gratis y completo) y con un video MP4 de cómo se construyó, con texto y música
---

# Una máquina terminada sale lista para la tienda, con su video de cómo se armó

## Estado y origen

Pedido de Mario (2026-10-08). Quiere subir muchas máquinas a su propia tienda web, la mayoría
gratis y algunas de pago a bajo precio, y automatizar:

> «Que apolo pueda importar el proyecto terminado, y todo los archivos a la pagina web»
>
> «Necesito generar video de como se creo ese proyecto en apolo, ese video lo voy a colgar en
> youtube, la pagina web podra referenciar el video. Pero el video se tiene que generar de forma
> automatica, como por ahora no metendre audio, el video podra tener una musica de fondo
> interesante y texto explicando.»

Mario aprobó el plan entero el mismo día («dale con la #2 y apruebo el plan»). El piloto
**no** es la faja `faja-paqueteria-4m` (proyecto 38): vive en la laptop y su log arrastra 48
scripts y varias cirugías. Es una máquina nueva, la #2 de la lista que se le propuso: un
transportador de rodillos motorizado, más su versión por gravedad como producto gratis. Se
modela en esta PC con un log limpio y ordenado para el video (bastidor → rodillos → transmisión
→ guardas), con grupos por etapa.

Hay dos pendientes que este plan cubre
de paso: el «clip de 40-60 s» que [lanzamiento](../lanzamiento.md) § 6 exige antes de lanzar y
el «MP4 del estudio de movimiento» del [backlog](../backlog.md) § Ideas (hoy sólo hay GIF).

## Lo que hay hoy

Medido sobre `main` en `7a61bd7`, salvo donde se indica.

**El paquete ya existe a medias, pero como benchmark.** `scripts/benchmark_package.py` (418
líneas, cliente HTTP puro) saca 26 artefactos del 38 en 125 s: planos PDF, DWG, GA, cutlist,
nesting, memoria, BOM, costeo, cotización, manual, STEP y 3 renders
([paquete 2026-07-24](../benchmark/faja-paqueteria-4m/2026-07-24/paquete.md)). Le falta todo lo
de tienda: qué es gratis y qué es de pago, ficha, licencia, aviso, el `.apolo`, el zip, los
hashes y el control de versiones. Además incluye cosas que no se publican, como la cotización
con margen e IVA.

**No hay MP4 ni nada que reconstruya el modelo a mitad de camino.**
- No hay ffmpeg, imageio ni moviepy en el código ni en `core/pyproject.toml`. Los GIF los arma
  Pillow (`robotics/anim.py:82-83`).
- En esta PC (MARIO-PCPRINCIP) hay `ffmpeg 7.1` en `C:\ffmpeg\bin` y Pillow 12.3.
- No existe una «escena tras los primeros k comandos».
  `Document.from_apolo_bytes(data, regenerate=False)` (`doc/document.py:970`) ya permite un
  documento en memoria sin tocar el DOC global (precedente: `doc/subproject.py:72-77`).
- Recorrer k en orden ascendente sobre un mismo doc reutiliza los checkpoints
  (`_REGEN_STRIDE=16`, `document.py:130`, `:256`). Trampa: `_ckpts_ok` descarta las claves
  ≥ len(commands) (`:141`).

**El render VTK no sirve tal cual para video:**
- La ventana mide `size_px × size_px·0.78` (`kernel/render_vtk.py:24`, `:474`): no es 16:9 y
  con 720 da un alto impar (561), que H.264 yuv420p rechaza.
- El fondo es un degradado (`:419-421`), así que rellenar los lados hasta 16:9 deja costuras
  visibles.
- Los colores salen de la paleta por ÍNDICE de escena (`api/scene.py:286-290`): en una escena
  parcial, la misma pieza cambia de color entre fotogramas.
- El encuadre usa el bbox de la escena del momento (`render_vtk.py:466-469`): la cámara
  saltaría a medida que crece el modelo. El precedente de fijar la cámara con la unión de
  bboxes es `robotics/anim.py:59-63`.
- Cada `render_snapshot_vtk` crea su ventana y vuelve a teselar, así que un video a 30 fps
  costaría fotogramas × escena (`core/apolo/CLAUDE.md`, GIF).
- `render_vtk.py` (537 líneas) y `document.py` (1059) están congelados en
  `tests/test_tamano_archivos.py`: lo nuevo va en módulos aparte.

**Texto para los rótulos ya existe:**
- `doc/pasos.py:211` `describir(cmds_antes, cmds_despues, escena_antes, escena_despues)`, que
  rotula el undo.
- `assembly_steps` del manual (`drawing/assembly_manual.py:53`).
- Los grupos del proyecto y `CommandSpec.title`.
- Los comandos no llevan etiqueta propia (`{id,type,params}`, `document.py:507`).

**Metadatos de tienda: no hay.** El manifest (`document.py:937-957`) no tiene título público,
descripción, licencia, precio ni versión del diseño. `agent_notes` (`:93`) son notas internas que
hoy viajan dentro del `.apolo`.

**El 38 no está en esta PC.** `data/apolo.db` se creó hoy (19:23) y sólo tiene «Sin título». Las
mediciones del 38 ([sandbox-caliente](sandbox-caliente.md)) se hicieron en Mario-LapTrab: 450
comandos (223 `fasten`, 48 `run_script`, 39 `set_variable`) y 129 sólidos.

## Lo que se revisó antes de escribir esto

- **Fondo degradado + aspecto fijo 0.78.** Descartan componer el render 4:3 sobre un lienzo
  16:9: el video necesita su propio render 16:9.
- **Los dos archivos congelados por tamaño.** El renderer de video y el recorrido por prefijos
  van en módulos nuevos (`kernel/render_vivo.py`, `doc/prefijos.py`).
- **`JobStore`: un solo worker FIFO, en memoria y con resultado dict** (`api/jobs.py:29-88`), y
  `_sync_or_job` toma STATE_LOCK. Un video de minutos dentro de la API bloquearía los lotes y la
  UI. Eso decide D1.
- **`benchmark_package.py` ya resuelve el «traer los entregables».** Se extrae y se comparte;
  no se reescribe.
- **El prefijo usa los params FINALES** (las ediciones son en sitio, `document.py:582`). El
  video muestra el ORDEN DE CONSTRUCCIÓN del diseño terminado, no los intentos. La historia real
  no se puede reconstruir: el undo vive sólo en memoria (≤ 50) y las revisiones son irregulares.

## Decisiones (para vetar)

- **D1 — v1 corre en un proceso aparte (CLI), no como endpoint ni job de la API.** El video tarda
  minutos y la API tiene un solo worker de jobs más STATE_LOCK: Apolo se congelaría mientras
  renderiza. El CLI lee la API como cliente (igual que el benchmark) y reconstruye el video en su
  propio proceso a partir del `.apolo` que baja de `GET /api/project/file`, sin locks
  compartidos. Exponerlo como tool MCP (un job que lanza ese mismo proceso) queda para v2.
- **D2 — El video muestra el orden de construcción del diseño final.** Se reproducen los
  prefijos del log con los params finales y se saltan los comandos que no cambian la geometría
  (`set_variable`, `fasten`, mates…). No se muestran intentos fallidos ni deshacer: es la
  historia limpia, la que se puede enseñar. Un super-comando (`create_conveyor` crea bastidor,
  rodillos y patas en UN comando) no aparece de golpe: sus features se revelan escalonadas, en
  orden de creación y agrupadas por rol (sufijo o nombre de la pieza).
- **D3 — Dos pasos con un guion editable en medio.** `publicar guion` escribe `guion.json`
  (etapas, texto de cada rótulo, duraciones, tarjeta de cifras, cierre) y un `ficha.yaml`
  borrador. `publicar generar` renderiza. El texto inicial es determinista (nombres de grupo y
  pieza, `pasos.describir`, cifras de la BOM y los requisitos). Pulirlo lo hace Mario o Claude
  en una sesión, editando el JSON. El pipeline **no** llama a la API de Claude: sin clave, sin
  costo por video y reproducible.
- **D4 — Las etapas salen de los grupos del proyecto.** Los pasos visuales consecutivos se
  agrupan por grupo o rol de la pieza que crean. Las etapas cortas se fusionan hasta que el video
  quede en ~60-90 s (configurable: `--duracion 50` da el clip de lanzamiento). Si una pieza no
  tiene grupo, se agrupa por tipo de comando.
- **D5 — Un render VTK VIVO por video** (`kernel/render_vivo.py`):
  - escena persistente 1920×1080;
  - actores incrementales: se agregan, quitan o reemplazan por `id(shape)`, sin volver a
    teselar todo en cada fotograma;
  - cámara fijada al bbox FINAL, con una órbita lenta continua;
  - colores fijados con la escena FINAL;
  - las piezas nuevas se resaltan y el resaltado se desvanece.

  Lo compartido con `render_vtk.py` (luces, material, fondo) se extrae para que los dos rendericen
  igual, y `render_vtk.py` baja de sus 537 líneas. **Condicional a la F0**: si un
  `render_snapshot_vtk` a 1920 cuesta < 0,15 s por fotograma, D5 se cae y basta con un parámetro
  de aspecto.
- **D6 — Pillow dibuja los textos y ffmpeg sólo codifica y mezcla.** Pillow hace portada,
  rótulos, tarjeta de cifras, cierre y miniatura. ffmpeg recibe los fotogramas por stdin
  (`rawvideo`), sin miles de PNG en disco. No se usa `drawtext`: escapes y fuentes distintas en
  cada sistema. La fuente por defecto es `ImageFont.load_default(size)` (FreeType de Pillow) y
  `--fuente` permite otra TTF.
- **D7 — ffmpeg es un binario externo, no una dependencia pip.** Se busca en el PATH o en
  `APOLO_FFMPEG`; si no está, el error dice cómo instalarlo. Formato YouTube: H.264 High,
  yuv420p, 30 fps, CRF 18, AAC 48 kHz, `-movflags +faststart`. Sin música sale un video mudo
  válido.
- **D8 — La música la pone Mario, con su licencia; el pipeline jamás la busca ni la descarga.**
  `--musica pista.mp3` desde una carpeta propia fuera del repo. El pipeline la recorta a la
  duración, hace fade-in de 1 s y fade-out de 3 s y la normaliza a −14 LUFS (`loudnorm`).
  `ficha.yaml` registra la pista, la fuente y la atribución, y esta va a la descripción de
  YouTube. Recomendación: la biblioteca de audio de YouTube Studio, que no genera reclamos de
  Content ID en YouTube.
- **D9 — El paquete no depende de ninguna tienda.** Cada máquina deja:
  - una carpeta versionada;
  - `ficha.json` (título, slug, versión, licencias, nivel, precio, etiquetas, cifras, lista de
    archivos con sha256, URL del video, vacía hasta subirlo);
  - dos zips: `-gratis` y `-completo`.

  Subirlo a la tienda es un adaptador aparte que se escribe cuando Mario elija la plataforma.
  Así Apolo no se ata a WooCommerce, Shopify ni ninguna otra.
- **D10 — Qué va gratis y qué de pago** (recomendación; decide Mario):
  - **Gratis**: renders, video, plano de conjunto GA en PDF, BOM resumida, STEP. Sirve de gancho
    y es lo que la gente busca en GrabCAD.
  - **Completo**: juego de planos PDF y DWG, lista de corte y nesting, manual de ensamblaje,
    memoria de cálculo y el `.apolo` paramétrico. Esto último es el diferencial: cambiar el largo
    y regenerar todo.
- **D11 — Nunca se publican la cotización, el costeo ni los JSON de validación crudos.** Los
  precios son internos y locales. La validación (sin interferencias, estable con gravedad,
  `delivery_check` verde) se resume en lenguaje humano en el `LEEME`: es argumento de venta, no
  un volcado.
- **D12 — El `.apolo` publicado sale saneado.** Va sin `agent_notes`; la F0 inventaría qué más
  trae (attachments, nombres) y fija la lista.
- **D13 — Puerta de calidad: sólo se publica con `delivery_check` en verde.** `--forzar` existe,
  pero deja «con observaciones» en la ficha y en el `LEEME`. Es la doctrina de Apolo: no se
  entrega en rojo.
- **D14 — Los datos de tienda van en `ficha.yaml` junto a la publicación, no en el manifest.**
  Título, descripción, precio y licencia son datos de negocio, no de diseño: no cambian la
  geometría ni el formato del `.apolo`. Las publicaciones viven fuera de git (video de 20-40 MB)
  en `paths.publicaciones_dir()`: `data/publicaciones` en un checkout y
  `APOLO_HOME/publicaciones` si Apolo se instaló con pip. Cada versión va en su carpeta y nunca
  se pisa.
- **D15 — YouTube se sube a mano en v1.** El pipeline deja `youtube.txt` con título,
  descripción con link a la tienda, capítulos, etiquetas y créditos de la música, más la
  `miniatura.png` (1280×720, < 2 MB). Capítulos: el primero en 00:00, al menos 3 y de ≥ 10 s cada
  uno (si no, YouTube los ignora); las etapas se fusionan para cumplirlo. Por qué no
  automatizarlo: un proyecto sin verificar en la API de YouTube sube los videos bloqueados en
  privado hasta pasar una auditoría.

Preguntas que sólo Mario contesta (no bloquean F0–F3):
1. Plataforma de la tienda. Para ventas baratas e internacionales, conviene una con
   *merchant of record* (Lemon Squeezy, Gumroad, Payhip), que cobra y declara los impuestos de
   cada país.
2. Licencias. Recomendación: gratis = CC BY-NC 4.0 (atribución y sin revender los archivos);
   pago = licencia personal (fabricar las máquinas sí, redistribuir los archivos no). No soy
   abogado: valídalo con uno.
3. Idioma. v1 = español; la versión en inglés sería traducir `guion.json` y volver a generar.

## Alternativas descartadas

- **Grabar la pantalla de la UI** (Playwright): depende de ventanas, resolución y tiempos; no es
  reproducible y se rompe con cualquier cambio de UI.
- **Job en la API en v1**: un solo worker FIFO + STATE_LOCK congela a Mario durante minutos (D1).
- **`drawtext` de ffmpeg**: escapes frágiles y fuentes distintas en Windows y Linux (D6).
- **moviepy / imageio-ffmpeg**: dependencias pesadas para lo que es un pipe a ffmpeg (D7).
- **Pedirle los textos a la API de Claude dentro del pipeline**: clave, costo y resultados no
  reproducibles. El guion editable consigue lo mismo (D3).
- **Metadatos de tienda en el manifest**: mezcla negocio con diseño y cambia el formato (D14).
- **Historia real (undo y revisiones)**: no existe completa y mostraría los errores (D2).
- **Fotogramas con matplotlib** (como `physics/anim.py`): peor calidad que VTK y más lento.

## Fases

**F0 — Mide** (sólo lectura · S · depende de la máquina piloto terminada, con `delivery_check`
en verde)
1. Health de la máquina piloto: comandos, sólidos, suprimidos. Como referencia de escala, medir
   lo mismo en el 38 cuando llegue su `.apolo` ([sandbox-caliente](sandbox-caliente.md): 450
   comandos y 129 sólidos).
2. Recorrer los prefijos ascendentes fuera de la API (`from_apolo_bytes(regenerate=False)`, con
   `python -B`). Medir cuántos comandos cambian el conjunto de sólidos o un shape (los «pasos
   visuales») y el tiempo total.
3. Medir el costo por fotograma 1920×1080: `extract_render_scene + render_snapshot_vtk` contra
   un prototipo de ventana viva que sólo mueve la cámara. Con eso se cierra D5.
4. Codificar 300 fotogramas sintéticos 1080p por stdin con ffmpeg (CRF 18): tiempo y MB.
5. Inventariar lo privado que trae el `.apolo` (D12) y los grupos del 38: cuántas etapas salen
   (D4).

Se verifica con la tabla en la Bitácora, D5 cerrada y una estimación del tiempo total del
video.

**F1 — Prefijos y guion** (`doc` + `services` · M · depende de F0)
- `doc/prefijos.py`: `iter_prefijos(doc, cortes)` produce `(k, escena, cambios)` sin tocar el
  DOC global, reutilizando los checkpoints y sin hacer crecer `document.py`.
- `services/construccion.py`:
  - `etapas(doc)`: pasos visuales → etapas (D2, D4);
  - `guion(doc, etapas)`: el `guion.json` editable (D3).

Se verifica con tests sobre un proyecto sintético chico:
- el prefijo k da la misma escena (ids, bbox, volumen) que regenerar `commands[:k]` desde cero;
- se saltan los comandos no visuales;
- un log con `run_script` e `insert_project` recorre sin romper.

**F2 — Render vivo** (`kernel` · M · depende de F0, en paralelo con F1). `kernel/render_vivo.py`
según D5, más la extracción de lo compartido de `render_vtk.py` (su número en el trinquete
baja). Se verifica con tests:
- tamaño par 16:9;
- colores estables entre prefijos;
- la cámara no se mueve al crecer la escena;
- un render existente sale idéntico antes y después de la extracción.

**F3 — Composición y codificación** (`apolo/media/` nuevo, que nunca recibe un `Document` · M ·
independiente, con fotogramas sintéticos; en paralelo con F1 y F2)
- `composicion.py`: portada, rótulo inferior, tarjeta de cifras, cierre y miniatura (D6).
- `codificar.py`: ffmpeg por stdin y música (D7, D8).

Se verifica con tests de composición (sin ffmpeg) y de codificación: duración, códec, tamaño par
y audio presente o ausente según `--musica`. Los de codificación se saltan si falta ffmpeg; en CI
Linux se instala ffmpeg con apt para que corran.

**F4 — Publicación** (`apolo/publicacion/` + `scripts/publicar.py` + `paths` · M/L · depende de
F1 a F3)
- Extraer de `benchmark_package.py` el cliente de entregables a un módulo compartido: el
  benchmark sigue produciendo lo mismo y los dos scripts no divergen.
- `publicar guion` y `publicar generar` (D3).
- Puerta de calidad (D13), saneo (D12), niveles gratis y completo (D10, D11).
- `LEEME.md` humano (qué es, cifras, validación resumida, cómo abrir el `.apolo`), `LICENCIA`,
  `AVISO` de responsabilidad, `youtube.txt` y miniatura (D15), zips, sha256 y carpeta versionada
  (D14).

Se verifica con un test E2E sobre un proyecto chico con la API de tests: la estructura del
paquete, ningún archivo prohibido dentro de los zips, hashes que cuadran y una segunda versión
que no pisa la primera.

**F5 — Verifica** (S · depende de F4)
- E2E con la faja: tiempos de `guion` y de `generar`.
- Mario ve el video y revisa los dos zips.
- Clip de lanzamiento con `--duracion 50`.
- Las reglas durables van al CLAUDE.md que corresponda; se actualizan los conteos y el backlog
  (sale el MP4).

Gate de cada fase: pytest completo y `ruff check core tests scripts`.

## Lo que este plan NO hace

- Subir a la tienda: el adaptador se escribe cuando Mario elija plataforma (D9).
- Subir a YouTube por API (D15).
- Voz en off, subtítulos SRT, video vertical para Shorts o TikTok y versión en inglés automática.
  El layout queda parametrizado para que el vertical sea un preset después.
- Exponer la publicación por la API o el MCP (v2, D1).
- Publicar variantes de la misma máquina (3, 4 y 5 m) desde sus configuraciones. Es el candidato
  natural de v2: lo paramétrico es lo que nadie más vende.
- La página web de la tienda.

## Riesgos

| riesgo | mitigación |
|---|---|
| El replay del 38 fuera de la API es lento (`run_script` en otro proceso) | La F0 lo mide; el sandbox caliente ya bajó el costo; los prefijos ascendentes reutilizan checkpoints |
| Un script con `import apolo` recompila `.pyc` y recarga la API `--reload` (blanquea el DOC) | Siempre `python -B`; el CLI lo avisa al arrancar |
| Una pieza cambia de color o la cámara salta entre fotogramas | Colores y cámara se fijan con la escena FINAL (D5); test en F2 |
| Un booleano reasigna ids y una pieza «desaparece y aparece» | Los actores se comparan por `id(shape)`, no por nombre |
| Reclamo de Content ID o música sin licencia | Sólo pistas que pone Mario, registradas en la ficha (D8) |
| Se filtra algo privado en el `.apolo` público | Saneo con lista fijada en la F0 (D12); test: los zips no contienen lo prohibido |
| Responsabilidad legal por planos de maquinaria | `AVISO` en cada paquete: no certificado, verificar con un ingeniero local, guardas obligatorias; licencias validadas por un abogado |
| ffmpeg ausente en la máquina o en el CI de Windows | Error claro con instrucciones; tests con skip en Windows y ffmpeg instalado en CI Linux |

## Bitácora

(vacía: se llena al cerrar cada fase)
