---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: F0–F4 hechas en la rama wip/visor-para-evaluar (sin mergear); falta la revisión de diseño a ciegas (F6), que Mario pruebe «Abrir» y el clic con la puerta abierta en su faja con desviador, y la F5 (las ocultas pesan 241 MB de SVG a 400 piezas; componer una casilla nueva aún toma ~6 s de STATE_LOCK; las láminas por pieza del juego siguen bajo el lock)
descripcion: el visor muestra el veredicto de las pruebas de la máquina, encuadra el tablero de frente y a la vista, y los planos se calculan sin congelar Apolo
---

# El visor alcanza para evaluar la máquina: sus pruebas, su tablero y sus planos

## Estado y origen

Mario evalúa las máquinas EN EL VISOR (ui/CLAUDE.md § Calidad visual). Revisando la faja con
desviador neumático (2026-10-26) encontró tres huecos, que la sesión coordinadora pasó así:

1. Los escenarios sólo se eligen en «Mandos» para abrir la sesión viva: el visor no dice si la
   máquina pasa sus pruebas, cuándo se corrieron ni qué falló.
2. En «Tablero», «Abrir» mueve la cámara al tablero y abre la puerta, pero el encuadre lo deja
   DETRÁS del panel lateral y detrás de otras piezas: no se ve.
3. «Planos» pide `GET /api/drawing.svg` del modelo entero; tarda y congela el visor. Y, ampliado
   por Mario: «marcar una casilla demora, y quitarla demora otra vez». Tampoco hay cómo pedir el
   JUEGO de planos de taller desde el visor («no sabía cómo ver un plano de taller»).
4. Después, también de Mario: con la puerta del tablero ABIERTA no se puede elegir con clic ninguna
   pieza de toda la máquina (D16). Y el juego de taller en DXF, para no depender del ODA File
   Converter que pide el DWG (D12).

## El problema / lo que hay hoy

- **Pruebas.** `GET /api/escenarios` ya trae estado, fecha, `fallidas` y `balance`
  (`services/escenarios.py:291`), pero el único cliente de la UI es el selector de «Mandos»
  (`ui/src/vivo/PanelMandos.tsx:61`), que sólo usa el nombre. La corrida es `POST /api/cosim/run`
  con `?async=true` en `COSIM_JOBS`; la UI nunca la pide.
- **Encuadre.** `PanelTablero.tsx` pide `pedirEncuadre([gabinete], {animar: true})`;
  `interaccion/ergonomia.ts` arma la pose con `camara.destinoEncuadre`: centra la caja en el
  CANVAS ENTERO (el cajón del visor flota encima, `visor/cajones.css`: 300+ px a la derecha),
  conserva la dirección que traía la cámara (cualquiera) y no mira qué hay entre la cámara y el
  gabinete. En el banco de demostración (dos fajas y una de rodillos, tablero detrás de la faja
  larga) el gabinete quedaba tapado por el motor y la faja (captura 02).
- **Planos (F0, medido).** Banco = `create_belt_conveyor` 6 m + 3 m (con cierres) +
  `create_roller_conveyor`: **369 piezas** (`scratchpad/banco_planos.py`, no en el repo).
  `compose_sheet` en el proceso, `time.process_time` (CPU) ≈ pared:

  | lámina | antes: costo (todo bajo `STATE_LOCK`) | SVG |
  |---|---|---|
  | abrir (alzado + planta + perfil + iso) | **276,8 s** | 10 MB |
  | marcar «líneas ocultas» | **345,6 s** | **245 MB** |
  | marcar «BOM» (sin perfil) | 67,1 s | 10 MB |
  | marcar «corte A-A» (sin iso, más el corte) | 237,7 s | 2 MB |

  - `project_views` de las 4 vistas: 274,8 s; con ocultas, 331,4 s (las ocultas se DISCRETIZAN
    en Python: +20 %). El perfil (YZ) solo es ~210 s; alzado + planta + iso, ~65 s.
  - Cada casilla recalcula TODO: desmarcar «ocultas» vuelve a costar 277 s.
  - `GET /api/drawing.svg` hace todo eso bajo `STATE_LOCK` (`routers/drawings.py:29`, antes del
    cambio): el visor no puede leer ni mutar durante 1 a 6 minutos.
  - **Lo que la F0 no vio y salió en la verificación**: `project_to_viewport` es UNA llamada de
    OCCT que no suelta el GIL. Con el HLR fuera del lock pero en un hilo de la API, el proceso
    entero se congela igual: `GET /api/health` no respondió en 120 s y `GET /api/pruebas` tardó
    85 s mientras calculaba (la sonda dentro del proceso no lo veía: un hilo detenido por el GIL
    no mide su propia espera). El HLR tiene que salir del PROCESO, no sólo del lock (D6).
  - El juego de planos (`GET /api/drawingset.pdf`) en el banco: 57 láminas, **77,6 s** todo bajo
    `STATE_LOCK` (sin sombrear); ningún botón de la UI lo pide.
  - Vista rápida candidata: `GET /api/render.png?view=iso&shade=true&vtk_only=true` en frío,
    7,8 s de pared con 2,0 s de `STATE_LOCK` como máximo (teselado).

## Lo que se revisó antes de escribir esto

- `cosim/flujo.py::texto_balance` e `incidencias` (D11 de balance-de-producto): el texto
  «12 entraron · 12 rampa · 0 trabados» y el producto, lugar y hora ya existen; el panel los lee,
  no los rehace.
- `services/tablero_panel.py:293-297`: la puerta es una pieza (`{cmd}_puerta`) y una junta; el
  panel conoce las dos.
- `drawing/projection.py`: una pasada de `project_to_viewport` devuelve visibles Y ocultas;
  `include_hidden` sólo decide si se discretizan. La BOM quita el perfil; el corte quita la iso
  y suma otra pasada sobre la mitad cortada.
- `manual-rapido` F2b: el patrón «se compone bajo el lock con un hueco reservado y lo caro se
  hace fuera» y la cola `ENTREGABLES_JOBS`. El HLR no se había movido («sigue bajo el lock»,
  api/CLAUDE.md § Locks).
- `brep_io.serialize_robust`: el viaje de una forma a bytes BinTools que ya usan la caché de
  geometría y el sandbox; el worker de la co-simulación (`cosim/proceso.py`): `Popen`, pickle
  de ida, JSON de vuelta.

## Decisiones (para vetar)

**Pruebas**

- **D1. Un panel «Pruebas» en «Más», entre «Neumática» y «Mandos»**, sobre un servicio propio
  (`services/pruebas_panel.py`, `GET /api/pruebas` y `GET /api/pruebas/{nombre}`) que pone en
  palabras lo que decide `escenarios.estado`: el panel no tiene reglas (el patrón de «Tablero»).
- **D2. Semáforo con los íconos de severidad del tema**: pasa = cumple, falla = para corregir,
  vencido y sin aserciones = para revisar, sin correr = sin evaluar. Arriba, la frase del
  veredicto ES el resumen: «15 de 16 pasan · 1 vencido»; las filas, lo más grave primero.
- **D3. Al abrir una prueba**: lo que no cumplió con su cifra (el `detalle` del veredicto: «al
  final vale falso — caja 7 trabada») y el producto trabado, perdido, retenido o que no entró,
  con la pieza más cercana a su punto (a ≤ 30 cm; si no, la coordenada) y la hora. Clic en el
  producto → la cámara va a ese PUNTO con contexto (no a la pieza: una banda de 6 m no dice dónde).
- **D4. «Correr» encola la co-simulación** (`POST /api/cosim/run?async=true&origen=visor`, la
  cola de la co-simulación y sus locks de siempre) y muestra su avance: el worker no publica
  progreso, así que se ESTIMA con lo que tardó la última corrida (duración ÷ factor de tiempo
  real, que guarda el resultado) y nunca llega solo al 100 %. «Verla en vivo» abre «Mandos» y la
  sesión viva con ese escenario, lo mismo que su selector.
- **D5. Aspecto**: tokens del tema (`pruebas.css` entra a `diseno/tokens.test.ts`), la fila
  elegida abre su detalle DEBAJO, sin cajas; en el muestrario con datos de ejemplo.

**Planos**

- **D6. El HLR se calcula en PROCESOS aparte, uno por vista y a la vez** (`drawing/hlr_worker.py`,
  `hlr_proceso.py`, hasta 4, un núcleo libre para la API). Bajo `STATE_LOCK` sólo se EXTRAE: las
  formas visibles a bytes BinTools sin malla (1,5 s a 369 piezas) y el marco de las vistas (el bbox
  de las ORIGINALES: la copia sin malla daría otro y la lámina cambiaría). Sin el proceso, el
  HLR congela la API por el GIL (§ El problema). Si el worker no arranca, la misma función corre en
  el proceso con un aviso en el log (la lámina no desaparece). Mismo resultado byte a byte que
  antes, con y sin ocultas, BOM y corte (test).
- **D7. Una pasada da visibles y ocultas; se guardan las dos.** `drawing/hlr_cache.py` guarda las
  proyecciones por la IDENTIDAD de las formas visibles (con su referencia y `is`, regla de
  core/apolo) y `project_views`/`section_projection` la LEEN: «líneas ocultas» es un filtro, la
  BOM quita una vista, y sólo el corte pide otra pasada (con su propia entrada). Se calculan
  siempre las cuatro vistas de la lámina de conjunto aunque la BOM o el corte oculten una, para
  que apagar la casilla no pida nada. Costo: las ocultas se discretizan siempre (+20 % la primera
  vez).
- **D8. La lámina compuesta se guarda por la firma del documento** (`api/planos.py`, `LAMINAS`,
  en memoria): log, nombre/visibilidad/material de cada pieza, uniones, cajetín, hoja y casillas.
  Volver a una combinación ya vista es inmediato; el color no cuenta (la lámina de líneas no lo
  usa). Sólo `Pedido.calcular` llena la caché del HLR: las láminas por pieza del juego y la
  explosionada (escenas sintéticas) leen y no la ensucian.
- **D9. Un job de la persona lleva `origen=visor`**: viaja en el job y en su aviso por WS y el
  visor no lo cuenta como «el agente está trabajando». El closure publica su avance con
  `jobs.avance({hechas, total, fase})` (hilo-local del worker); `GET /api/jobs/{id}` lo devuelve
  en `progreso`. Sin `origen` ni avance, todo byte-idéntico.
- **D10. El diálogo pide `GET /api/drawing/lamina`**: lista al instante si ya está (o si sólo
  cambió una casilla: compone en el momento, sin HLR: de 1 a 9 s a 369 piezas, F5) o un job con su progreso («Calculando
  las vistas · 1 de 4 listas»). Mientras tanto muestra la lámina ANTERIOR (en gris, «el plano
  anterior») o, si no hay, la isométrica sombreada (`render.png`, unos segundos). Las descargas
  SVG/DXF/PDF se habilitan cuando la lámina está (ya sale de la caché).
- **D11. «Regenerar» se quita**: la lámina sigue a la firma del modelo; regenerar algo idéntico no
  aportaba (sólo vencía la caché del navegador).
- **D12. El juego de planos de taller entra al diálogo** con su nombre («Juego de planos de taller:
  una lámina por pieza, con la lista de corte y la cédula de herraje»), en PDF, en DXF (un ZIP con
  un DXF por lámina, `GET /api/drawingset.dxf`: no necesita el ODA File Converter) y, si
  `health.dwg.disponible`, en DWG; los tres como job (`?async=true&origen=visor`, `drawingset.dwg`
  gana el modo job) con su progreso (`sheet_set(avance=)`: «Lámina 12 de 57») y la descarga al
  terminar. Su conjunto lee el HLR de la caché (`planos.precalcular`, fuera del lock y en
  procesos); las láminas por pieza siguen bajo el lock (F5).

**Encuadre**

- **D13. Todo encuadre centra en lo que SE VE** (`viewport/areaLibre.ts`): el canvas menos lo que
  lo tapa de lado a lado, marcado con `data-tapa-vista` (hoy los cajones del visor; nunca una lista
  de paneles). La distancia crece lo que el área achica y el objetivo se corre para que la caja
  quede en su centro; con el área completa, la pose de siempre (test). En una pantalla angosta
  (lo libre < 30 %), el canvas entero.
- **D14. `frente`: mirar la cara grande de una pieza de frente.** La normal dominante sale de su
  malla (autovector mayor de Σ área·n·nᵀ: sirve con la pieza girada), hacia afuera de lo
  encuadrado. La caja crece lo que la pieza abre hacia la cámara (la puerta: su ancho por delante
  y un tercio a los lados).
- **D15. `despejar`: si algo tapa, otra vista; si no hay, atenuar.** Rayos de la cámara a 9 puntos
  de la caja; tapa lo que el rayo cruza FUERA de la caja y no es del mismo comando que lo
  encuadrado (los mandos de la puerta no tapan). Se prueban la vista pedida, ±30° de rumbo y 25°
  más alta; si todas están tapadas, la pedida (manda el frente) con lo que tapa al 12 % de
  opacidad, hasta el próximo encuadre o hasta cerrar el panel (`apolo:restaurar-atenuadas`).
  El panel «Tablero» pide `frente` + `despejar` al abrir la puerta y `despejar` en sus ítems.
  El frente sale de la pose de DISEÑO de la pieza (`userData.baseMatrix`): con la puerta ya
  abierta, la normal girada miraba desde el costado.
- **D16. Lo que la UI mueve se elige donde se VE, y en una pose apretar sobre una pieza la
  selecciona.** Lo encontró Mario: con la puerta del tablero abierta no se elegía NINGUNA pieza de
  la máquina. No era una tapa invisible (el rayo veía la puerta abierta): con una junta fuera de
  cero, `manipular.ts` mandaba el apretar sobre una pieza al RECUADRO; su `preventDefault` en el
  pointerdown suprime el mousedown, el clic de `seleccion.ts` veía un arrastre viejo y salía, y el
  recuadro de 0 px no elegía nada. Ahora `interaccion/alApretar.ts` decide (en pose o bloqueada:
  seleccionar, nunca recuadro), el recuadro mide las esquinas de la malla en su pose vista y todo
  pick pone al día la matriz de mundo antes del rayo (`piezasBajo`: una junta recién movida que
  todavía no se dibujó).

## Alternativas descartadas

- **Quitar sólo el lock (el HLR en un hilo)**: lo que proponía el pedido literal. Medido: el GIL
  congela la API igual (§ El problema). Por eso D6.
- **`camera.setViewOffset` para correr el centro de la proyección** (en vez de mover el
  objetivo): afecta a todo lo que dibuja con la cámara (selección, grabación a 1920 × 1080, el
  cubo de vistas) mientras el cajón está abierto. Correr el objetivo es local al encuadre.
- **Las ocultas como capa del SVG que el cliente prende y apaga**: obliga a meter el SVG en el
  DOM (10–245 MB) en vez de un `<img>`. Con la caché, cambiar la casilla ya es inmediato (otra
  URL ya compuesta) y la descarga sale igual que en pantalla.
- **HLR de polígonos (`HLRBRep_PolyAlgo`) como vista rápida**: más rápido pero aproximado y
  mallaría las formas (escribe en las caras). La vista rápida es la lámina anterior o la
  isométrica sombreada, que ya existen.
- **Una cola nueva para la lámina**: va en `ENTREGABLES_JOBS` (la de los entregables); un job
  igual en curso se reutiliza en vez de encolar otro.
- **Progreso real de la co-simulación**: cambiaría el protocolo del worker (huella y
  `COSIM_EPOCH`); la estimación por la corrida anterior basta para «¿falta mucho?».

## Fases

- **F0 (medición, hecha)**: el costo de «Planos» en el banco de 369 piezas (§ El problema).
- **F1 (`services` + `api` + `ui`, M, hecha)**: panel «Pruebas» (D1–D5), `origen` y avance de
  los jobs (D9). Tests: `tests/test_pruebas_panel.py`, `ui/src/pruebas/pruebas.test.ts`,
  `state/eventosWs.test.ts`.
- **F2 (`ui`, M, hecha)**: encuadre en el área libre, `frente` y `despejar` (D13–D15). Tests:
  `ui/src/viewport/encuadreLibre.test.ts`; verificación en el preview (capturas 02, 03, 05).
- **F3 (`drawing` + `api`, M, hecha)**: caché del HLR, HLR en procesos, lámina por firma, el
  endpoint del visor y el juego como job (D6–D8, D10, D12). Tests: `tests/test_planos_visor.py`.
- **F4 (`ui`, S, hecha)**: el diálogo «Planos» (D10–D12). Tests: `ui/src/panels/planos.test.ts`.
- **F5 (`drawing` + `api`, M, pendiente)**, con lo que midió la F3:
  - aligerar las ocultas: 245 MB de SVG a 369 piezas, 241 MB a 403 (el navegador las recibe pero
    no las muestra con gusto; su JSON de vuelta del worker se lee con el GIL tomado: parte de los
    8 s de la lectura más lenta al abrir). Medir qué aristas son (roscas, interiores de
    rodamientos) y si deduplicar o una tolerancia de discretización baja el tamaño sin cambiar la
    lámina visible;
  - componer una combinación nueva de casillas toma ~6 s de `STATE_LOCK` a 369 piezas (llevar las
    polilíneas de la caché al papel en Python): componer las vistas fuera del lock con el modelo ya
    extraído;
  - las láminas por pieza del juego siguen con su HLR bajo el lock (19 s de lectura más lenta con
    el conjunto ya calculado): la misma caché y los mismos procesos, pieza por pieza.
- **F4b (`ui` + `api`, S, hecha)**: el clic con la puerta abierta (D16) y el juego en DXF (D12).
  Tests: `ui/src/viewport/interaccion/alApretar.test.ts`, `encuadreLibre.test.ts` (frente con la
  puerta abierta), `tests/test_planos_visor.py` (el ZIP de DXF).
- **F6 (verificación, pendiente)**: revisión de diseño a ciegas de «Pruebas» y del diálogo
  «Planos» (capturas del muestrario, ancho y angosto); Mario abre el tablero de su faja con
  desviador y mira «Planos» en ella.

## Lo que este plan NO hace

- No cambia ninguna lámina: mismas vistas, cotas y textos (byte a byte, con test).
- No cambia la co-simulación ni su veredicto (`COSIM_EPOCH` igual) ni la geometría
  (`GEOM_CACHE_EPOCH` igual) ni el registro de comandos.
- No toca el texto de ninguna tool MCP (golden sin cambios): `origen` y `progreso` sólo
  aparecen cuando el visor los pide.

## Riesgos

- **El worker del HLR en una instalación sin `python -m` utilizable** (un empaquetado
  congelado): respaldo en el proceso con aviso en el log (D6), como el render sin OpenGL.
- **Memoria**: hasta 4 procesos con las formas del modelo y la caché de 4 escenas en la API (no
  se midió el pico). Mitigación: `PARALELO` y `TOPE` en sus módulos; medirlo en la F5.
- **Un documento que cambia mientras calcula**: la lámina se compone con lo nuevo (una vuelta
  más del pedido; si vuelve a cambiar, el HLR que falte se hace bajo el lock, como antes). Test.
- **Lo atenuado queda translúcido si el panel no avisa**: vuelve con el próximo encuadre; el
  panel «Tablero» avisa al cerrarse.

## Bitácora

### F0–F4 (2026-10-26)

Ver § El problema para la F0. Medido después de punta a punta contra una API real (uvicorn) con el
banco de 369 piezas; ANTES con el código de `baba86d` sobre una copia de la misma base. La
«lectura más lenta del visor» es la de una sonda en OTRO proceso que pide `GET /api/scene/summary`
cada segundo (lo que siente el visor: el lock y también el GIL). Otra sesión compartía la máquina:
el reloj de pared es la red gruesa; lo que importa es la proporción.

| paso | antes | después | lectura más lenta del visor, antes → después |
|---|---|---|---|
| abrir «Planos» (4 vistas) | 280,3 s | 229,6 s (un job; se ve la isométrica sombreada en ~8 s) | ~280 s → 8,1 s |
| marcar «líneas ocultas» | 345,6 s (F0) | 8,8 s | todo → 6,5 s |
| desmarcar «líneas ocultas» | ~277 s | 6,4 s (0 s la segunda vez) | todo → 7,7 s |
| marcar «BOM» | 77,1 s | 1,3 s | ~77 s → 0 s |
| desmarcar «BOM» | 289,4 s | 6,3 s (0 s la segunda vez) | ~289 s → 6,6 s |
| marcar «corte A-A» (otra pasada) | 237,7 s (F0) | 17,6 s | todo → 8,6 s |
| desmarcar el corte · volver a marcarlo | ~277 s · ~238 s | 0,0 s · 0,0 s | — → 0 s |
| juego de planos PDF (57 láminas) | 77,6 s sólo las láminas, todo bajo el lock | 102,4 s con el PDF, el conjunto ya calculado | ~78 s → 19,0 s |

En el visor real (proyecto de demostración: el banco + el tablero de la piloto, 403 piezas,
diálogo «Planos»): marcar «BOM» 1,4 s y desmarcarlo 0,1 s; marcar «líneas ocultas» 2,6 s (su SVG,
241 MB: F5).

- **Primer intento**: HLR sobre copias `BRepBuilderAPI_Copy` en un HILO con `HLR_LOCK`. Los tests y
  una sonda de lock en un hilo del mismo proceso daban verde (lock máximo 1,5 s mientras calculaba
  333 s). En el visor real, `GET /api/health` no respondió en 120 s y `GET /api/pruebas` tardó
  85 s. Causa raíz: el HLR de OCCT no suelta el GIL, y una sonda en un hilo no puede ver su propia
  detención. Se pasó a procesos (D6) y la sonda, a otro proceso.
- La copia viaja en BinTools sin malla (1,5 s bajo el lock a 369 piezas) y la lámina sale igual
  byte a byte con ocultas, BOM y corte; el marco se toma de las originales (la copia sin malla
  tiene otro bbox óptimo). Las 4 vistas en paralelo: el perfil solo tarda ~210 s, por eso abrir
  baja poco (280 → 230 s): lo que cambia es que el visor no se congela.
- Encuadre: en el banco de demostración el tablero quedaba tapado por el motor y la faja larga
  (captura 02); con `frente` + `despejar` se ve de frente, a la izquierda del cajón (03); con una
  mampara de 3 × 2 m delante, ninguna vista cercana está libre y la mampara se atenúa (05).
- Pruebas: el panel lee el estado y el balance de `escenarios`; su vacío dice qué va a aparecer y
  cómo empezar. «Correr» se probó con el job (cola de la co-simulación); el avance estimado se ve
  en el muestrario (06).
- D16 (el clic con la puerta abierta): reproducido en el preview (con la puerta a 110° el clic no
  elegía nada; un rayo de prueba sí veía la puerta abierta), arreglado y verificado: se eligen la
  puerta, sus mandos y cada aparato del interior (07).
