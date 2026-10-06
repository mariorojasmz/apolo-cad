---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: aprobado por Mario el 2026-10-06 sin vetos; fases F0–F6 en implementación
descripcion: El 3D ocupa toda la pantalla, los paneles se abren como cajones encima y ves al instante qué piezas cambió el agente
---

# El 3D ocupa toda la pantalla y ves qué cambió el agente

## Estado y origen

Pedido de Mario (2026-10-06), comparando la pantalla principal de Tinkercad con la de Apolo:
«quiero maximizar herramientas y espacio para poder visualizar mejor al objeto en 3d, ahora
apolo si te das cuenta en la captura, la mayor parte son ventanas y contenido, que son utiles
pero no son tanta prioridad como ver todo el escenario». Su forma de trabajar: «le pido a
claude (agente ia) y el por mcp lo diseña yo lo veo y le sigo pidiendo hasta tener el proyecto
terminado». Recordó que Apolo lo van a usar personas con poca experiencia en diseño 3D, y que
las modificaciones puntuales a mano llegarán después, con herramientas que todavía no existen.

Se armó un mockup clicable que Mario aprobó («Esta bueno, aprobado»):
[modo-visor-mockup.html](modo-visor-mockup.html), que también está publicado como artefacto
privado. Este plan es el contrato para llevarlo a la UI real.

## El problema / lo que hay hoy

- **El 3D ocupa ~35 % de la pantalla.** En la captura de Mario (1917×1041) el viewport mide
  ~1195×587 px. En el mockup, la réplica del layout actual da **33 %** y el visor **95 %**
  (medido a 1600×900). En Tinkercad, ~72 %.
- `App.tsx:31-34` monta siempre TopBar + Ribbon + DockShell + StatusBar. El layout por defecto
  (`dock/dockApi.ts:44-73`) pone el árbol a la izquierda y Propiedades + Asistente IA a la
  derecha. Los paneles-herramienta se apilan en pestañas BAJO el viewport
  (`dockApi.ts:115-132`).
- Hay **dos barras que repiten lo mismo**: las pestañas del panel inferior y la StatusBar
  (`panels/StatusBar.tsx:10-20`), que abre y cierra esos mismos paneles.
- **Dentro del 3D, una columna de 11 botones** (`viewport/Viewport.tsx:1499-1568`: ISO,
  Frente, Lateral, Planta, Alambre, Mover, Rotar, Escalar, Snap, Medir, Sección) tapa el
  modelo. La mitad sirve para editar a mano, algo que en este flujo hace el agente.
- **No hay forma de ver qué cambió el agente.** El refresh por WebSocket aplica el delta y
  el modelo cambia en silencio: con 80 piezas no se nota qué se tocó.

## Lo que se revisó antes de escribir esto

- **Dockview 7.0.2** ya trae `maximizeGroup` / `hasMaximizedGroup` / `exitMaximizedGroup`
  (`node_modules/dockview-core/dist/cjs/api/component.api.d.ts:573-575`) y permite ocultar la
  cabecera de un grupo (`tabsContainer.d.ts:79-80`, `header.hidden`). Por eso el visor no
  necesita un shell nuevo: se maximiza el grupo del viewport. Así el canvas no se re-monta, y
  re-montarlo rompe el contexto WebGL (ui/CLAUDE.md § Shell y paneles; `dockApi.ts:4-7`).
- **El refresh no-completo ya es, por construcción, un cambio externo.** El WS sólo refresca
  si `!busy && syncing === 0` (`state/store.ts:419-431`): las ediciones propias cierran con su
  propia respuesta. El otro llamador es el chat autónomo (`store.ts:920`). La reconexión llama
  `refresh(true)` (`store.ts:433`). `mergeSceneDelta` (`store.ts:353`) ya sabe qué piezas
  vienen `same` y cuáles traen geometría nueva. → Detectar los cambios del agente no requiere
  tocar la API.
- **Trinquetes de tamaño**: `viewport/Viewport.tsx` está congelado en 1791 líneas y
  `state/store.ts` en 947 (`ui/src/tamanoArchivos.test.ts:43-44`). Ninguno puede crecer, así
  que lo nuevo va en archivos propios y antes de tocarlos hay que extraer algo.
- **Regla de ui/CLAUDE.md § Viewport**: «Sin glow de hover ni tinte `emissive` de selección:
  el contorno basta». El destello de los cambios va por contorno, no por tinte (el mockup usa
  tinte por simplicidad).
- La **barra de selección** ya existe (`Viewport.tsx:1622-1643`: Duplicar, Ocultar, Aislar,
  Centrar, Eliminar), abajo al centro (`styles.css:307`). En el visor ese lugar lo ocupa la
  barra de paneles.
- El **ViewCube** se dibuja dentro del renderer principal, fijo arriba a la derecha (96 px,
  `viewport/viewcube.ts:8-9`, con scissor). Moverlo exige tocar el viewport; es más barato que
  el cajón derecho empiece debajo del cubo.
- **Masa y material por pieza**: ya existen en `GET /api/mass-properties?ids=…`
  (`core/apolo/api/routers/features.py:97`, de solo lectura). `FeatureOut` (`types.ts:6-24`)
  trae el bbox, pero no el peso.
- **Atajos** (`viewport/shortcuts.ts:67-85`): F encuadra, 0/Inicio va a ISO, 1-3 a las vistas,
  W alambre, H oculta, I aísla, L mide, S secciona. Siguen valiendo en los dos modos.
- **Jobs** (`core/apolo/api/jobs.py`): los lotes del MCP se encolan. `JobStore` no importa
  FastAPI y marca corriendo/terminado en `_mark_running` / `_finish` (`jobs.py:130-150`). De
  ahí se puede colgar el aviso «el agente está trabajando» sin acoplar el módulo al transporte.

## Decisiones (para vetar)

- **D1 — El visor es la pantalla por defecto; Completo queda a un clic.** Un selector
  **Visor | Completo** en la barra superior muestra el modo activo. En el mockup, un solo botón
  que decía «Modo completo» estando en el visor confundió: se leía como el modo actual. El
  modo se recuerda por navegador (`localStorage`, clave `apolo.pantalla.v1`, con try/catch).
  Porqué: el flujo de Mario es mirar y pedir, no operar paneles.
- **D2 — El visor maximiza el grupo del viewport de Dockview (`maximizeGroup`) y oculta su
  pestaña «Vista 3D».** No se crea un shell aparte. Porqué: el viewport no se re-monta y el
  layout de Completo queda tal cual al volver. Mientras el grupo está maximizado **no se
  persiste el layout**, para no guardar el estado maximizado en `apolo.layout.v1`.
- **D3 — En el visor no se montan Ribbon ni StatusBar; los paneles se abren como cajones
  flotantes sobre el 3D.** A la izquierda va el Árbol; a la derecha va uno solo a la vez,
  cualquiera de los demás. Los cajones alojan los **mismos componentes** de hoy (`Tree`,
  `Properties`, `BomPanel`, `ChecksPanel`, `HistoryPanel`, `ChatPanel`, …): no se reescribe
  ningún panel. Esc cierra el cajón abierto. El cajón derecho empieza debajo del ViewCube.
- **D4 — Barra de paneles flotante, abajo al centro:** Árbol · BOM · Validar · Historial ·
  Más ▾ (Variables, Requisitos, Cinemática, Ensamblaje, Física, Montaje, Boceto) · Asistente IA.
  Validar lleva el conteo de avisos **sólo si** hay un resultado reciente sin correr una
  validación nueva (lo confirma F0); si no, va sin conteo.
- **D5 — Controles de vista flotantes a la izquierda, como en Tinkercad:** Vista inicial,
  Encuadrar, Acercar, Alejar, y debajo las herramientas de **inspección**, que ya existen:
  Medir, Sección y Alambre. **Mover, Rotar, Escalar y Snap no aparecen en el visor**: editar a
  mano queda en Completo hasta que existan las herramientas nuevas. Las vistas
  Frente/Lateral/Planta se eligen en el ViewCube o con los atajos.
- **D6 — Barra de selección en el visor, arriba al centro:** Encuadrar, Aislar, Ocultar y
  **Copiar para el agente**. Sin botones de Duplicar ni Eliminar: lo destructivo se queda en
  Completo. Los atajos de teclado (Supr incluido) no cambian.
- **D7 — Ficha de pieza:** al seleccionar una pieza aparece una tarjeta chica a la derecha,
  debajo del ViewCube. Muestra nombre, id, medidas (del bbox), material y peso (de
  `/api/mass-properties?ids=`), y dos botones: «Copiar para el agente», que copia
  `«Nombre» (id)`, y «Ver todo», que abre Propiedades en el cajón. Porqué: Mario le habla al
  agente por fuera de la app, y el id es lo que el agente necesita (ui/CLAUDE.md: el árbol
  muestra el id por eso mismo).
- **D8 — Las piezas que cambió el agente se marcan.** Tras un refresh **no-completo**, las
  piezas nuevas o con geometría nueva (no `same`) se marcan con un **contorno verde que pulsa
  ~3 s**. Es un segundo `OutlinePass`, no tinte `emissive`, para respetar la regla del
  viewport. Además aparece el aviso «El agente cambió N piezas» con **Ver** (encuadra esas
  piezas y vuelve a pulsar) y **×**. Las eliminadas se cuentan en el texto. Las piezas nuevas
  llevan un punto verde en el árbol hasta el próximo cambio externo. La reconexión
  (`refresh(true)`) no marca nada.
- **D9 — El aviso NO lleva «Deshacer»** (el mockup sí lo tenía). Porqué: deshacer revierte el
  último lote del documento, y con el debounce de 250 ms del WS un aviso puede juntar dos lotes
  del agente. «Deshacer» en el aviso prometería revertir lo que describe y no lo haría. El botón
  de deshacer de la barra superior sigue ahí.
- **D10 — «El agente está trabajando…» en vivo.** Cuando un job pasa a corriendo y cuando
  termina, el servidor manda por WS `{"type": "job", "estado": "corriendo" | "ok" | "error"}`.
  `JobStore` recibe un callback y sigue sin importar FastAPI ni sostener `_cv` al llamarlo.
  La UI muestra el aviso en curso y, al terminar, deja el de D8. Porqué: un lote largo tarda
  segundos y hoy no hay ninguna señal de que algo está pasando. Va en su propia fase (F5) para
  poder vetarla sin tocar el resto.
- **D11 — El estado del visor vive en su propia store** (`ui/src/visor/estado.ts`: modo, cajón
  izquierdo y derecho, aviso de cambios, ids marcados), no en `state/store.ts`, que está
  congelado.
- **D12 — Antes de agregar nada a `Viewport.tsx` o a `store.ts` se extrae:** la columna de
  vista y la barra de selección pasan a componentes propios con variante visor/completo, y
  `mergeSceneDelta` pasa a `state/sceneDelta.ts` como función pura con test. Los trinquetes
  bajan en el mismo commit.
- **D13 — Texto**: tuteo neutro y los nombres de la tabla de ui/CLAUDE.md («pieza», no
  «sólido», en todo lo nuevo). Los gates `textoDeAyuda` y `tuteoNeutro` deciden.

## Alternativas descartadas

- **Un shell aparte para el visor (otro árbol de React sin Dockview)**: cambiar de modo
  re-montaría el viewport y perdería el contexto WebGL. Es el mismo fallo documentado con
  StrictMode.
- **Cajones como grupos flotantes de Dockview** (`addFloatingGroup`): se pueden arrastrar y
  redimensionar, que es justo lo que el visor quiere quitarle a una persona sin experiencia, y
  no controlamos su animación ni su posición.
- **Que el visor sólo esconda la StatusBar y el Ribbon dejando los paneles acoplados**: el 3D
  pasaría de 35 % a ~50 %, no al ~95 % del mockup.
- **Tinte `emissive` para el destello**, como en el mockup: choca con la regla del viewport y
  con el tinte rojizo que hoy significa «guardado fallido».
- **Marcar el origen en cada `document_changed` desde la API**: no hace falta. El refresh
  no-completo ya es externo por construcción (§ Lo que se revisó).

## Fases

Cada fase la implementa un subagente en worktree (§ Planes del CLAUDE.md raíz), con
`npm test` + `npm run build` como gates (y pytest en F5). El mockup es la referencia visual.

- **F0 — Medir (sólo lectura, ui, S).** (a) % del 3D en la app real en Completo, a 1917×1041 y
  a 1600×900. (b) Si `maximizeGroup` + `header.hidden` re-monta el viewport: contar `builds` en
  `window.__apolo` antes y después de alternar 5 veces. (c) Si, con el grupo maximizado, los
  paneles ocultos siguen montados; si siguen, el cajón duplicaría un panel y habría que
  decidir. (d) Qué devuelve `/api/mass-properties?ids=` para una pieza de catálogo y una a
  medida. (e) Si Validar tiene un conteo reciente sin correr nada (D4). Depende de: nada.
  Verifica: los números quedan en la bitácora.
- **F1 — Extraer sin cambiar conducta (ui, M).** La columna de `Viewport.tsx:1499-1568` pasa a
  `viewport/BarraVista.tsx` y la barra de selección (`1622-1643`) a
  `viewport/BarraSeleccion.tsx`. Las dos reciben por props el estado local que usan. Se baja
  el número de `Viewport.tsx` en el trinquete. Depende de F0. Verifica: gates y la UI
  idéntica a antes (screenshot de Completo).
- **F2 — Modo Visor | Completo (ui, M).** `visor/estado.ts` (modo persistido, D1, D11); el
  selector en `TopBar`; `App` sin Ribbon ni StatusBar en el visor; `dockApi.setModoVisor()`
  con maximizar, ocultar la cabecera y no persistir (D2); `BarraVista` variante visor con
  controles redondos e inspección (D5); `BarraSeleccion` variante visor arriba al centro
  (D6). Depende de F1. Verifica: 3D ≥ 90 % a 1600×900 en el visor; al volver a Completo el
  layout guardado es idéntico; `builds` no sube al alternar.
- **F3 — Cajones, barra de paneles y ficha (ui, M).** `visor/CapaVisor.tsx` (capa sobre el
  área del dock), `visor/Cajon.tsx`, `visor/BarraPaneles.tsx`, `visor/FichaPieza.tsx`
  (D3, D4, D7). Depende de F2. Verifica: cada panel abre con sus datos en su cajón, Esc cierra,
  el 3D no cambia de tamaño al abrir un cajón y la ficha muestra el peso del endpoint.
- **F4 — Cambios del agente (ui, M).** Extraer `mergeSceneDelta` a `state/sceneDelta.ts` con
  un test que devuelva los ids nuevos, cambiados y eliminados; bajar el número de `store.ts`;
  el refresh no-completo publica esos ids en `visor/estado.ts`; contorno verde pulsante en el
  viewport (un `OutlinePass` más, con lo mínimo dentro de `Viewport.tsx`), aviso con Ver y ×,
  y punto verde en el árbol (D8, D9). Depende de F2 (el aviso vive en la capa del visor).
  Verifica: test de `sceneDelta`; E2E con un `run_batch` por MCP sobre un proyecto de prueba,
  que marque sólo las piezas tocadas; una edición propia desde la UI no dispara el aviso.
- **F5 — «Trabajando…» en vivo (api + ui, S).** Callback en `JobStore`; `WS.notify_changed`
  con `{"type": "job", …}`; la UI muestra y cierra el aviso en curso (D10). Depende de F4.
  Verifica: test de `JobStore` (el callback se llama en corriendo y al terminar, sin `_cv`
  sostenido) y E2E con un lote asíncrono.
- **F6 — Verificar (S).** Mario pide un cambio por MCP con el visor abierto en la faja 38;
  se mide el % del 3D; gates verdes; ui/CLAUDE.md § Shell y paneles suma una línea (el shell
  tiene dos modos y el visor maximiza el grupo, no re-monta) y se actualizan los conteos de
  «Estado actual». Depende de F3–F5.

## Lo que este plan NO hace

- **Vista ortogonal**: la cámara del viewport es sólo perspectiva (`applyRotArrowPose` recibe
  una `PerspectiveCamera`). Cambiarla es otro plan.
- **Herramientas nuevas de edición a mano**: vienen después, como dijo Mario. Hasta entonces se
  edita en Completo.
- **Rediseñar los paneles por dentro**: BOM, Validar e Historial se ven igual, sólo que en un
  cajón.
- **Diseño para tablet o teléfono**, **tema claro** y **cambios al chat** (eso es
  [chat-cliente-igual](chat-cliente-igual.md)).

## Riesgos

- **`maximizeGroup` re-monta o pierde el contexto WebGL.** F0 lo mide antes de construir
  encima. Plan B: ocultar los grupos laterales con la API de visibilidad de Dockview.
- **Paneles montados dos veces** (ocultos en Dockview y abiertos en el cajón) → doble fetch o
  estado local duplicado. F0 (c) lo mide. Si pasa, el cajón sólo monta un panel que Dockview
  no tenga montado, o el visor cierra los paneles de Dockview y los repone al volver.
- **El layout de Completo se corrompe con el estado maximizado.** No se persiste mientras el
  visor está activo (D2), y F2 lo verifica.
- **Falsos positivos del destello.** Sólo marca el refresh no-completo. Si F0 encuentra otro
  llamador de `refresh()` que sea propio, se filtra ahí.
- **Trinquetes de `Viewport.tsx` y `store.ts`.** F1 y F4 extraen antes de agregar (D12). Si
  lo extraído no alcanza para lo nuevo, se extrae más; nunca se sube el número.
- **Un cajón tapa controles del 3D.** El cajón derecho empieza debajo del ViewCube y los
  controles de la izquierda se corren cuando se abre el Árbol, como en el mockup.

## Bitácora

### F0 — medido (2026-10-06, app real en :8000 con la faja 38, 84 piezas)

- **(a) % del 3D**: con el layout por defecto de un navegador nuevo, a 1917×1041, el viewport
  mide 639×851 = **27 %** (Dockview reparte el ancho entre el árbol y Propiedades). En la
  captura de Mario, con su layout, ~35 %.
- **(b) `maximizeGroup` no re-monta**: después de maximizar es el mismo `<canvas>`, sin
  `webglcontextlost`, y hay un solo canvas en la página. Maximizado y con la cabecera oculta,
  el viewport mide 1918×881 = **85 %**, todavía con el Ribbon y la StatusBar montados; sin
  ellos se espera ~96 %. Al salir vuelve a 639×851 con el mismo canvas.
- **(c) Los paneles ocultos siguen montados**: con el grupo maximizado, los `.dock-pane` del
  árbol y de Propiedades siguen en el DOM con ancho 0. Si un cajón aloja el mismo
  componente, hay dos instancias. **Se acepta**: Árbol, Propiedades y Asistente leen de la
  store y la copia oculta no recibe interacción. El costo es un fetch duplicado al montar en
  los paneles que lo hacen. Cerrar y reabrir los paneles al cambiar de modo perdería las
  posiciones que Mario haya armado.
- **⚠️ Trampa nueva**: Dockview serializa el maximizado (`"maximizedNode"` en
  `apolo.layout.v1`) y `exitMaximizedGroup()` **no** dispara `onDidLayoutChange`: tras salir,
  lo guardado sigue maximizado. → F2 no persiste mientras el grupo está maximizado, guarda
  explícitamente al salir y, al cargar en Completo, sale del maximizado si el JSON lo trae.
- **(d)** `GET /api/mass-properties?ids=c44` devuelve `material: "acero"`, `masa_kg: 2.5864`
  y `bbox_mm` por pieza. La ficha (D7) usa eso.
- **(e)** Validar no tiene un conteo barato: `ChecksPanel` corre a pedido (botón) y guarda el
  resultado en su estado local. → **D4 sin conteo** en la barra de paneles.
