---
estado: en curso
nota: contrato derivado de un plan aprobado por Mario el 2026-10-24; F1 mergeada (A1 superficie de lectura eléctrica en `MODULOS`, A2 `Extension.costeo`, A3 `Extension.entrega` en `delivery_check`; sin extensiones, todo byte-idéntico); F2 en curso (trazos de esquema y panel ancho)
descripcion: una extensión de entregables lee el modelo eléctrico por una superficie declarada, suma filas al costeo y a la cotización y pone ítems en la puerta de entrega, sin tocar el núcleo
---

# Una extensión de entregables lee lo eléctrico, cobra lo suyo y lo exige al entregar

## Estado y origen

- Una extensión que produce entregables sobre el modelo eléctrico (esquemas, memoria de cálculo,
  manual) necesita tres cosas que el núcleo no le da. Lo midió la F0 de un plan de entregables
  eléctricos que vive fuera del núcleo (aprobado por Mario el 2026-10-24); este plan cuenta sólo
  los puntos GENÉRICOS que pide, sin lo que hace la extensión con ellos.
- Es la misma forma que la F1d de [núcleo abierto](nucleo-abierto-extensiones-privadas.md):
  `ext` del manifest, la fachada, `Extension.puerta` y el motor de láminas en `MODULOS`.

## Lo que hay hoy

Rutas relativas a `core/apolo/`, medidas sobre `5a78cc9`.

- **Lectura eléctrica:** `extensiones_api.MODULOS` (l. 80-123) declara el motor de láminas y lo de
  la fábrica de videos, pero nada del modelo eléctrico. Una extensión que lee el modelo
  (`services/electrico.modelo`), sus redes (`library/electrico/redes.analizar`), el tablero armado
  y ruteado (`services/tablero.armados`, `ruteos`, `largos`), los cables de campo
  (`services/cables_campo.recorridos`, `largos`), la R y la X de un conductor
  (`cosim/red/conductores.py:36-58`) o el catálogo (`library/catalog.CATALOG`) lo hace por fuera del
  contrato: un refactor del núcleo la rompe sin aviso.
- **Costeo:** `services/cobros.costeo(doc)` (l. 135-151) es la fuente única de
  `GET /api/costing.json` (`api/routers/deliverables.py:60`) y de la cotización
  (`deliverables.py:272`, `drawing/quote.py:151`). Suma la escena, el tablero
  (`bom_filas.filas_extra`) y los avisos de cobro. Una extensión no puede sumar una fila (p. ej.
  horas de un servicio): `costed_bom` (`library/costing.py:115`) costea cada fila por su ref y una
  ref desconocida queda sin precio.
- **Puerta de entrega:** `library/delivery.py::delivery_report` (l. 82) agrega una lista FIJA de
  chequeos; `services/delivery_inputs.py::delivery_inputs` (l. 46) arma sus kwargs. La consumen
  `POST /api/delivery-check` (`api/routers/validation.py:178-205`) y la puerta de publicación
  (`services/puerta_publicacion.reunir`, l. 165-179). Una extensión no puede poner un ítem: un
  hallazgo suyo que debería dar ROJO (un conductor subdimensionado) no llega al semáforo.
- La puerta de entrega no tiene número de versión; la de publicación sí (`VERSION_REGISTRO` +
  «+nombre.version_puerta» de cada extensión, `library/calidad/registro.version`).

## Lo que se revisó antes de escribir esto

- `extensiones_puntos.sumar_puerta` (l. 162-202): valida al cargar (prefijo, tipos, nada
  repetido), registra en `registro.DE_EXTENSION` con su `version_puerta` y el rechazo se deshace
  porque el registro está en `extensiones._registros()`. Los dos puntos nuevos copian esa forma.
- Las filas del costeo llevan `origen` (`library/bom_electrico.py:47`, `"electrico"`); el resumen
  de la cotización separa «Componentes comprados» (`catalogo_usd`) de «Fabricación a medida»
  (`fabricacion_usd`, `costing.costing_totals`). Una fila de servicio sumada a cualquiera de las dos
  mentiría en el resumen.
- `delivery_report` ya tiene secciones opcionales que, sin datos, no aparecen (eléctrico, acceso de
  herramienta, escenarios): «sin extensiones, idéntico» se logra igual.

## Decisiones (para vetar)

- **D1 — Superficie de lectura eléctrica en `MODULOS`** (A1). Se agregan, con los nombres que
  existen hoy (un test lo exige):
  - `apolo.services.electrico`: `modelo`, `chequeo`;
  - `apolo.library.electrico.redes`: `analizar` y su resultado `Analisis`;
  - `apolo.library.electrico.modelo`: los tipos del modelo (`ModeloElectrico`, `Dispositivo`,
    `Borne`, `Camino`, `Carga`, `Fuente`, `Hilo`, `Conductor`, `Paso`, `Cable`, `Programa`, `Red`);
  - `apolo.services.tablero`: `ruteos`, `largos`, `armados` y el tipo `Tablero`;
  - `apolo.services.cables_campo`: `recorridos`, `largos` y el tipo `CableCampo`;
  - `apolo.cosim.red.conductores`: `resistencia`, `reactancia`, `r20_ohm_km`, `LAMBDA_OHM_M` y
    `TEMPERATURA_DEFECTO_C` (una caída de tensión necesita la λ y la temperatura que usa la
    co-simulación, no otras);
  - `apolo.library.catalog`: `CATALOG`.

  Agregar nombres no sube `CONTRATO_EXTENSIONES` (regla de `extensiones_api.py`).
- **D2 — `Extension.costeo`: filas extra del costeo y la cotización** (A2).
  - **Qué declara:** una lista de `FuenteCosteo(id="prefijo.x", filas=fn)` (o una función sin
    argumentos que la da: perezoso, como `puerta`) y `version_costeo` (entero ≥ 1).
  - **`filas(doc)`** corre bajo el `STATE_LOCK` del llamador y da filas
    `{descripcion, cantidad, unidad, costo_unit, fuente}` y, opcional, `categoria` (por defecto
    «servicios»). Ninguna otra clave.
  - **Al cargar** se valida lo declarable: `FuenteCosteo`, id con prefijo, `filas` llamable, nada
    repetido con otra extensión, `version_costeo` entero. Lo que no cumple rechaza la extensión
    entera (todo o nada).
  - **Al costear** se valida cada fila: textos no vacíos, `cantidad` finita > 0, `costo_unit`
    finito ≥ 0 (sin `bool`). Una fila mala o una función que lanza NO tumba el costeo ni se cobra:
    sale un aviso de cobro («fila de extensión descartada», con el motivo). Lo dudoso se dice donde
    se cobra (regla de `services/cobros.py`).
  - **Dónde entra:** en `costeo(doc)`, AL FINAL de las filas, ya costeadas
    (`costo_ud_usd` = `costo_unit`, `costo_total_usd` = `costo_unit × cantidad`,
    `costo_fuente` = `fuente`), con `ref` = el id de la fuente y `origen: "extension:<nombre>"`.
    `costed_bom` no las re-costea.
  - **Totales:** van a `extensiones_usd` (ni comprado ni fabricado) y suman al `total_usd`; la
    cotización muestra la línea «Otros conceptos» y la columna «Cant» lleva la unidad. El dict
    del costeo suma `extensiones: {nombre: version_costeo}`.
  - **Sin extensiones con costeo, todo es byte-idéntico** (filas, totales, cotización).
- **D3 — `Extension.entrega`: ítems de la puerta de entrega** (A3).
  - **Qué declara:** una lista de `ReglaEntrega(id="prefijo.x", titulo, evaluar)` (o una función
    que la da) y `version_entrega` (entero ≥ 1). Validado al cargar como `puerta`: tipo, id con
    prefijo, título no vacío, `evaluar` llamable, nada repetido.
  - **`evaluar(doc)`** corre en `delivery_inputs` bajo el lock del llamador y da `None` (no aplica
    a este documento: no aparece, como el eléctrico sin carril) o una lista de hallazgos
    `{estado: ok | aviso | error, detalle, piezas?}`. `error` → bloqueante (ROJO), `aviso` →
    AMARILLO, sin hallazgos malos → `chequeos_ok`. Cada entrada lleva `id` y `origen`.
  - **Una regla que lanza o da otra forma** → aviso «no se pudo evaluar» con el motivo: nunca
    verde, nunca tumba la puerta.
  - **Versión de la batería:** el núcleo nombra la suya, `VERSION_BATERIA = 1`
    (`library/delivery.py`; sube si cambia un chequeo del núcleo). Con reglas de extensión, el
    resultado suma `version_bateria` = «1+nombre.version_entrega»; sin ellas no aparece.
  - **Entra en las dos puertas**: `delivery_check` y la puerta de publicación (que agrega el mismo
    `delivery_report`), porque las dos leen `delivery_inputs`.
  - **Sin extensiones, el semáforo es idéntico.**
- **D4 — La extensión falsa de la suite usa los tres** (`tests/ext_prueba/`): lee el modelo
  eléctrico por `MODULOS`, cobra una fila de prueba y pone una regla de entrega que bloquea si su
  nota del manifest lo pide; más variantes que no cargan (sin prefijo, repetida, no es del tipo,
  versión inválida).
- **D5 — `GET /api/extensiones` suma `costeo` y `entrega`** (los ids que aportó cada extensión),
  como hoy `puerta`.

### Una extensión que dibuja esquemas (F2)

Una extensión que dibuja esquemas (eléctricos, neumáticos) con el motor de láminas necesita dos
cosas más. Hoy los exportadores (`drawing/svg.py`, `pdf.py`, `dxf.py`) dibujan todo `Circle` como
globo (relleno claro, borde azul) y todo `Polygon` como cara de corte (relleno gris o rayado): no
hay un círculo negro sin relleno ni un punto de unión negro, y el prototipo de la extensión los
tuvo que hacer con segmentos. Y en el modo Visor un panel de extensión abre en el cajón derecho de
400 px: una lámina no se lee.

- **D6 — Trazos de esquema en los tres exportadores**, en un módulo aparte
  (`drawing/esquema.py`; `sheet.py` está congelado por el trinquete de tamaño y no crece).
  - Dos estilos (`kind`) que valen para `Line`, `Circle` y `Polygon`: `simbolo` (trazo negro, sin
    relleno: el cuerpo de un símbolo y la línea de conexión) y `simbolo_lleno` (negro relleno: el
    punto de unión, una punta de flecha). Ayudas: `conductor`, `circulo`, `punto_union` y
    `poligono`.
  - **Grosor: criterio de diseño declarado.** El núcleo no tiene una convención de esquemas (en
    lo mecánico usa 0,5 / 0,25 / 0,7 mm en SVG y DXF). Un esquema va con UN ancho para símbolos y
    conexiones, como es práctica de IEC 61082-1; se toma 0,35 mm de la serie de ISO 128 (legible
    en A3 y en copia reducida a A4) y un punto de unión de 1,2 mm de diámetro (≈ 3,5 veces el
    trazo). En el PDF el grosor se convierte a puntos. El negro es el de las aristas visibles
    (`#16181d`), no un color nuevo.
  - **DXF:** capa `ESQUEMA` (ACI 7, continua, 0,35 mm) que sólo se crea si la lámina la usa; lo
    lleno lleva además un sombreado sólido.
  - **Lo de antes no cambia de aspecto:** un test congela la firma del SVG, de los artistas del
    PDF y de las entidades del DXF de una lámina con todos los estilos anteriores, sacada del
    código previo a la F2.
  - No hay símbolos de norma ni cajetín de esquema en el núcleo: son de la extensión.
- **D7 — Panel ancho en la UI:** `PanelDeExtension.ancho?: "lamina"`. En el modo Visor el cajón
  derecho de ese panel abre al ancho de una lámina (`min(960 px, todo el visor)`) en vez de
  400 px; en Completo los paneles-herramienta ya van debajo del viewport a todo el ancho y no
  cambia nada. El registro rechaza otro valor. La extensión de prueba del muestrario lo usa con
  la lámina de la extensión falsa en SVG en línea (la misma que exporta el núcleo; un test exige
  que esté al día). Sólo tokens del tema; ningún color nuevo.
- **D8 — `MODULOS` suma `apolo.drawing.esquema`** (estilos, grosores y ayudas) y los dos
  exportadores que faltaban, `apolo.drawing.svg` (`sheet_to_svg`, lo que muestra el panel) y
  `apolo.drawing.dxf` (`sheet_to_dxf`). Agregar no sube `CONTRATO_EXTENSIONES`.

## Alternativas descartadas

- **Que la extensión devuelva filas sin costear y el núcleo las costee por su ref:** una hora de
  servicio no tiene ref de catálogo; el costo lo sabe la extensión y la `fuente` lo declara.
- **Sumar las filas de extensión a `catalogo_usd`:** el resumen diría «Componentes comprados» por
  un servicio.
- **Rechazar la extensión si una fila sale mal al costear:** a esa hora ya cargó; tumbaría el
  costeo de un documento por un dato. El aviso de cobro lo dice donde se cobra.
- **Un punto genérico «hook de la puerta de entrega» que reciba los kwargs:** daría a la extensión
  el poder de cambiar los chequeos del núcleo; sólo suma los suyos.

## Fases

- **F1 — Los tres puntos** (`extensiones*.py`, `library/costing.py`, `library/delivery.py`, dos
  módulos chicos nuevos en `library/`, `services/cobros.py`, `services/delivery_inputs.py`,
  `drawing/quote.py`, la extensión falsa y sus tests · M · sin dependencias).
  - **Se verifica:** con la suite completa y `ruff` limpio; los tests nuevos prueban cada punto con
    la extensión falsa cargada, cada rechazo (todo o nada) y que sin extensiones el costeo y el
    semáforo son los de siempre.
- **F2 — Trazos de esquema y panel ancho** (`drawing/esquema.py` nuevo, los tres exportadores,
  `extensiones_api.py`, la extensión falsa; `ui/src/extensiones/`, `dock/`, `visor/` y el
  muestrario · S/M · sin dependencias): D6–D8.
  - **Se verifica:** suite completa, `ruff` limpio, `npm test` y `npm run build`; los tests
    nuevos prueban cada estilo en SVG, PDF y DXF, que la lámina mecánica sale idéntica, que el
    registro de la UI acepta `ancho: "lamina"` y rechaza otro valor, y una captura del muestrario
    con el panel ancho.

## Lo que este plan NO hace

- No implementa ningún entregable eléctrico: sólo los puntos por donde una extensión los
  engancha.
- No cambia el formato del `.apolo`, del log ni de la SQLite.
- No suma tools MCP ni cambia el golden.
- No dibuja símbolos de norma ni un cajetín de esquema (F2 sólo da los trazos).
- Los datos de ficha y de acometida que pidió el mismo plan van en su propio plan.

## Riesgos

- **Una extensión que lee lo eléctrico queda atada a la forma de esos tipos:** sólo se declaran
  NOMBRES; un campo que cambie lo ve su CI contra la ref fijada del núcleo (como F1d).
- **Una regla de entrega lenta alarga `delivery_check`:** corre con `_cronometro` y aparece en
  `tiempos_s.por_regla` como «extensiones».
- **Un costeo de extensión que lanza siempre:** el aviso de cobro lo dice en cada cotización; no
  se esconde.

## Bitácora

### F1 (2026-10-24): los tres puntos

**Hecho** (sobre `5a78cc9`):

1. **D1 — lectura eléctrica en `MODULOS`** (`core/apolo/extensiones_api.py`): siete módulos con
   los nombres de D1. La extensión falsa los usa en `tests/ext_prueba/electrico.py` (modelo, redes,
   catálogo, R y X de cada conductor, ruteo del tablero y cables de campo) y el gate de imports de
   `test_extensiones_api.py` lo acepta tal cual. `CONTRATO_EXTENSIONES` sigue en 1.
2. **D2 — `Extension.costeo`** (`library/costeo_extension.py`, puro): `FuenteCosteo`,
   `DE_EXTENSION` y `fila()` (valida y costea). `extensiones_puntos.sumar_costeo` valida al cargar;
   `services/cobros.filas_de_extensiones` las corre bajo el lock y `costeo(doc)` las suma al final.
   `costing.costed_bom` salta las que traen `origen` «extension:» y `costing_totals` las lleva a
   `extensiones_usd` (sólo si hay). La cotización suma «Otros conceptos» (también con `fx`) y la
   unidad en «Cant».
3. **D3 — `Extension.entrega`** (`library/entrega_extension.py`, puro): `ReglaEntrega`,
   `DE_EXTENSION`, `hallazgos()` (valida) y `version()`. `services/delivery_inputs.reglas_de_extensiones`
   las corre (con su cronómetro «extensiones») y `delivery_report` las pone al final (sección 10)
   con `id` y `origen`; `VERSION_BATERIA = 1` y `version_bateria` sólo con reglas.
4. **D5** — `GET /api/extensiones` suma `costeo` y `entrega`
   (`tests/test_extensiones_coherencia.py` actualizado).

**Decidido por el agente (vetable):**

- **Las filas de una fuente se validan al costear, no al cargar**: dependen del documento. Al
  cargar se valida lo declarable (tipo, id, llamable, versión); una fila mala es un aviso de cobro
  «fila de extensión descartada» (cuenta 0 en `monto_en_riesgo_usd`), nunca un 500.
- **`categoria` opcional, «servicios» por defecto**; `cantidad` admite decimales (horas) y sale
  entera si lo es.
- **`ref` de la fila = el id de su fuente** («prueba.revision»): la cotización necesita una ref y
  así se sabe de dónde salió.
- **Una regla de entrega que da `None` no aparece** (como el eléctrico sin carril), no va a
  `no_aplica`: «no aplica» no es «no pudo correr».
- **`version_bateria` aparece con cualquier extensión que tenga reglas**, aunque ninguna aplique
  a ese documento: la batería cambió.
- **D1 suma, además de lo pedido, `Analisis`, los tipos `Tablero` y `CableCampo`, `LAMBDA_OHM_M` y
  `TEMPERATURA_DEFECTO_C`**: son el resultado de lo que se lee o lo que una caída de tensión
  necesita para dar lo mismo que la co-simulación.

**Números (F1):** suite 5118 → 5152 (pasan 5142, se saltan 10; los 27 de tortura, aparte). Los 34
nuevos: 25 en `tests/test_extensiones_entregables.py` y 9 en `tests/test_extensiones_api.py` (uno
por módulo y por nombre de `SUPERFICIE` nuevos). `ruff check core tests scripts` limpio; ningún
archivo pasa de 500 líneas (`delivery.py` 354, `extensiones.py` 408, `extensiones_puntos.py` 355).

### F2 (2026-10-24): trazos de esquema y panel ancho

**Hecho** (sobre `72f7c01`):

1. **D6** — `core/apolo/drawing/esquema.py` (66 líneas): `SIMBOLO`/`LLENO`, `NEGRO`,
   `GROSOR_SIMBOLO_MM` 0,35, `D_UNION_MM` 1,2 y las ayudas `conductor`, `circulo`, `punto_union` y
   `poligono`. `svg.py`, `pdf.py` y `dxf.py` los dibujan (PDF: grosor en pt; DXF: capa `ESQUEMA`
   y sombreado sólido para lo lleno). `tests/test_trazos_esquema.py` congela la firma de una
   lámina con todos los estilos anteriores (SVG exacto, artistas del PDF, entidades y capas del
   DXF) sacada del código de `72f7c01` antes de tocar los exportadores, y prueba cada estilo en
   los tres formatos.
2. **D7** — `PanelDeExtension.ancho?: "lamina"` (`ui/src/extensiones/tipos.ts`, validado en
   `registro.ts`), llega a `PANELES` (`componerPaneles.ts`) y el cajón derecho del visor abre con
   `cajon-lamina` (`visor/cajones.ts::claseCajon`, `--cv-lamina-ancho` en `cajones.css`). El cajón
   sin estado sale a `visor/MarcoCajon.tsx`; el muestrario lo arma con la extensión de prueba
   (`diseno/muestrario/extensionPrueba.tsx`), que muestra en línea `lamina-prueba.svg`.
3. **D8** — `MODULOS` suma `apolo.drawing.esquema`, `apolo.drawing.svg` y `apolo.drawing.dxf`; la
   extensión falsa los usa en `tests/ext_prueba/esquema.py` (una A4 de potencia de prueba: tres
   fases con puntos de unión, protector, contacto, relé con flecha llena y motor).

**Decidido por el agente (vetable):**

- **`Line` también lleva el estilo `simbolo`**: el contrato pedía círculo y polígono, pero un
  esquema con símbolos a 0,35 mm y conexiones a 0,5 (el «visible») no tiene un solo ancho.
- **Los nombres de los estilos son `simbolo` y `simbolo_lleno`** (no «unión»): lo lleno sirve
  también para una punta de flecha; el punto de unión es `punto_union()`.
- **La capa `ESQUEMA` del DXF sólo existe si la lámina la usa**: así un DXF mecánico es idéntico
  (capas incluidas).
- **El SVG del muestrario es un archivo generado** (`python -B tests/ext_prueba/esquema.py`) y un
  test de la suite de Python exige que coincida con lo que exporta el núcleo: lo que se ve en el
  muestrario es lo que dibuja el exportador.
- **El panel encaja la lámina entera en el cajón** (SVG a 100 % × 100 %, sin deformar): zoom y
  arrastre son del visor de láminas de la extensión, no del núcleo.
- **El cajón ancho conserva el `top` del cajón derecho** (bajo el ViewCube): a 960 px tapa el
  centro del 3D pero deja ver el cubo.

**Números (F2):** suite 5152 → 5162 (7 en `tests/test_trazos_esquema.py` y 3 en
`tests/test_extensiones_api.py`, uno por módulo nuevo de `MODULOS`); vitest 515 → 520 (2 del
registro, 1 de `componerPaneles`, 2 de los cajones). `ruff check core tests scripts` limpio;
`npm run build` verde. Ningún archivo pasa de 500 líneas (`svg.py` 113, `pdf.py` 134, `dxf.py`
102, `extensiones_api.py` 163); `sheet.py` no se tocó.
