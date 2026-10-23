---
estado: implementado   # implementado | en curso | sin verificar | descartado
nota: F0–F3 en main (2026-10-19): Viewport.tsx 1631 → 429 líneas, sombra de contacto sobre un piso de estudio; falta mirarla de cerca en el piloto (74), no bloquea
descripcion: La máquina se apoya en el piso con una sombra de contacto suave en el visor, y el visor queda partido en módulos que se pueden seguir mejorando
---

# La máquina se apoya en el piso: sombra de contacto en el visor

## Estado y origen

Mario, al ver el piloto (proyecto 74) con los acabados nuevos de
[visor-realista](visor-realista.md) F1, preguntó si el piso con sombra «es también mejora» y
pidió: «sí, escribe el plan y lánzalo» (2026-10-19). Es el pendiente que dejó visor-realista F1
(§ Bitácora F1, «Pendiente de F1 — piso con sombra de contacto»): sin sombra de contacto la
máquina parece flotar sobre el fondo oscuro, y eso pesa en las capturas, el video de la máquina y
la primera impresión del visor.

## El problema / lo que hay hoy

- **El piso** es un plano XY con `ShadowMaterial({ opacity: 0.25 })` que sólo recibe la sombra de
  la luz direccional (`ui/src/viewport/scene-setup.ts:50-58`, luz en `LIGHT_OFFSET = (1500,
  -1000, 2000)`, `PCFSoftShadowMap` de 2048²). Esa sombra cae DESPLAZADA (la luz viene de lado) y
  con borde duro: bajo las patas no hay oscurecimiento, así que el ojo no lee el apoyo.
- **`Viewport.tsx` tiene 1631 líneas** y está congelado en el trinquete
  (`ui/src/tamanoArchivos.test.ts:44`). Un solo `useEffect` de montaje va de la línea 319 a la
  ~1146 y mezcla: renderer y cámara, el `EffectComposer` con sus passes (`:530-544`), el
  `resize`, el bucle `animate` con `requestAnimationFrame` (`:621-632`), la selección por clic
  (`:637`), agarrar-mover / estirar / recuadro (`:674-1078`) y la ergonomía (menú, doble clic,
  hover, encuadre; `:1078-1140`). Arriba hay geometría del gizmo de rotación y su overlay
  (`:43-231`); abajo, funciones puras de sección y cinemática (`:1518-1631`). Un pase nuevo no
  cabe sin partirlo primero.
- Trampas conocidas del visor ([ui](../../ui/CLAUDE.md) § Desarrollo y verificación): `npm run
  dev` + StrictMode remonta el viewport y lo rompe (se verifica con `vite preview` o con la UI
  servida por la API en :8000); la captura automática se agota con el rAF continuo; el rAF se
  pausa en una pestaña de fondo. Se verifica por DOM o por el hook `window.__apolo`
  (`Viewport.tsx:467`).

## Lo que se revisó antes de escribir esto

- `scene-setup.ts` ya separa «el aspecto» (renderer, luces, suelo) de la interacción: el pase de
  contacto es aspecto y va al lado, no dentro del componente.
- El composer ya encadena `RenderPass` → `OutlinePass` → destello → `OutputPass`
  (`Viewport.tsx:530-544`). La sombra de contacto NO es un pase de post-proceso: es una TEXTURA
  que se calcula aparte y se dibuja en un plano de la escena, así que entra sin tocar la cadena
  del composer.
- La técnica estándar de three.js para esto (el ejemplo oficial `webgl_shadow_contact` y el
  `ContactShadows` de drei, MIT) es: cámara ORTOGRÁFICA bajo la máquina mirando hacia arriba,
  render de PROFUNDIDAD de la escena a un render target pequeño, desenfoque horizontal +
  vertical, y un plano con esa textura en el piso. No requiere dependencias nuevas: todo es
  `three` (ya en el bundle).

## Decisiones (para vetar)

- **D1. Partir `Viewport.tsx` por responsabilidad, como refactor PURO** (cero cambio de
  comportamiento), hasta dejarlo ≤ 500 líneas y sacarlo del trinquete. Módulos en
  `ui/src/viewport/`:
  - `gizmoRot.ts`: geometrías, materiales y pose del gizmo de rotación y la flecha de eje
    (`:43-231`).
  - `pipeline.ts`: renderer, cámara, controles, composer y passes, `resize`, y el bucle de
    render con un punto de enganche explícito «antes de componer» (lo usa D2).
  - `interaccion/`: selección por clic, agarrar-mover/estirar/recuadro y ergonomía, cada uno
    una función `instalarX(ctx): () => void` que devuelve su limpieza. Reciben un `Ctx`
    EXPLÍCITO (escena, cámara, controles, grupo, refs que necesitan); nada de cierres sobre
    variables sueltas del `useEffect`.
  - `poses.ts`: `sectionPlanes`, `attachGizmo`, `computePoses`, `applyKinematicPoses` (puras o
    casi).
  Por qué refactor puro primero y separado: el viewport es frágil (StrictMode, rAF, picking) y
  mezclar el movimiento de código con el pase nuevo haría imposible saber cuál rompió qué.
- **D2. Sombra de contacto con la técnica de three.js** (cámara ortográfica bajo la escena →
  profundidad a un RT de 512² → blur H+V → plano con la textura), en un módulo propio
  `sombraContacto.ts`. El plano se apoya en el `min.z` del bbox de la escena visible (el piso de
  la máquina) y cubre el bbox en XY con un margen. Opacidad y radio de desenfoque como
  constantes con nombre, calibradas a ojo en el piloto (F3).
- **D3. Se recalcula sólo cuando cambia algo**, nunca por frame: una bandera `sucia` que
  levantan la reconstrucción de mallas, la pose cinemática, la física (drop/gravedad), el
  cambio de visibilidad o sección y el FIN de un arrastre; durante un arrastre, como mucho a
  10 Hz. En reposo el costo es cero (se dibuja el plano con la textura ya hecha).
- **D4. La sombra direccional se queda** para la sombra propia (una pieza sobre otra); el piso
  sigue recibiéndola, pero con menos opacidad para que la de contacto mande bajo las patas. El
  valor sale de la calibración de F3.
- **D5. Sin control nuevo en la UI**: la sombra va siempre encendida, como el piso. Si el piso
  se oculta (sección, vista desde abajo), la sombra se oculta con él.

## Alternativas descartadas

- **Sombra direccional más grande o más suave**: sigue desplazada (la luz viene de lado); poner
  la luz cenital mata el relieve de las piezas.
- **SSAO / GTAO del composer**: oscurece rincones de la propia máquina, no el apoyo en el piso,
  y cuesta por frame.
- **Sombra horneada en el GLB o en el video**: cada salida tiene su motor; esto es del visor.
- **Hacer el pase sin partir el archivo** (subir el trinquete): la regla del repo es que su
  número sólo baja.

## Fases

- **F0 (S, sólo lectura)**: mapa de `Viewport.tsx`: qué variables y refs comparte cada bloque
  del `useEffect` de montaje (lo que tendrá el `Ctx`), y una línea base: cuántas mallas y qué
  devuelve `window.__apolo` en el piloto. Va en la bitácora.
- **F1 (L, `ui/src/viewport`)**: D1. Depende de F0. Se verifica con `npm test` (vitest, incluido
  el trinquete con `Viewport.tsx` fuera o ≤ 500) y `npm run build`; tests unitarios nuevos para
  lo que quedó puro (`poses.ts`, pose del gizmo).
- **F2 (M, `ui/src/viewport`)**: D2–D5 en `sombraContacto.ts`, enganchado al punto «antes de
  componer» de `pipeline.ts`. Depende de F1. Tests unitarios: el encuadre de la cámara
  ortográfica a partir de un bbox, la altura del plano y la lógica de la bandera `sucia` (no se
  recalcula en reposo; sí tras reconstruir mallas o mover una pose). `npm test` + `npm run
  build`.
- **F3 (S, verificación, sesión principal)**: UI reconstruida y servida por la API en :8000 (o
  `ui-preview`). En el piloto (74) y en la faja en chapa C (73): capturas antes/después, la
  máquina apoyada (sombra oscura bajo patas y placas), interacción intacta (seleccionar,
  arrastrar, medir, sección, pose cinemática) y que en reposo no haya recálculo (contador en
  `window.__apolo`). Calibrar las constantes de D2/D4 y anotarlas.

## Lo que este plan NO hace

- No cambia el render VTK (fotos, GIF, video) ni el GLB de la vista web: cada uno tiene su motor.
- No agrega reflejos en el piso, piso con textura ni fondo de estudio: sólo el apoyo.
- No toca la lógica de interacción: F1 la MUEVE sin cambiarla.

## Riesgos

| riesgo | mitigación |
|---|---|
| El refactor rompe una interacción que ningún test cubre | F1 es movimiento puro, revisado como tal en el diff; F3 recorre las interacciones a mano en el navegador |
| Un cierre del `useEffect` gigante dependía de una variable que ahora vive en otro módulo | el `Ctx` explícito de D1; F0 lista qué comparte cada bloque antes de moverlo |
| El pase cuesta en máquinas grandes | D3: recálculo sólo al cambiar; RT de 512²; F3 mide en la 73 (117 sólidos) y el piloto (201) |
| La sombra se ve mal con la máquina inclinada o con piezas bajo el piso | el plano va en el `min.z` visible; F3 lo mira en las dos máquinas |

## Bitácora

### F0 (2026-10-19)

Mapa de `ui/src/viewport/Viewport.tsx` (1631 líneas) leído entero, sin tocar código. El `useEffect`
de montaje (`:319-1146`) tiene diez bloques; lo que comparte cada uno es lo que tendrá el `Ctx`:

| bloque | líneas | crea | lee de otros bloques o del componente |
|---|---|---|---|
| A. pipeline | 320-354 | renderer, scene, camera, controls, luces (`dir`), suelo, IBL, ViewCube, grid, ejes, `group`, gizmo (`TransformControls`) | `mountRef` |
| B. gizmo: snap + listeners | 356-455, 473-523 | `snapIndex`, `snapOffsets`, `ctrlHeld`, `snapMarker`, `onModKey`, `commitGizmo` | gizmo, controls, camera, renderer, `featuresRef`, `isGizmoDraggingRef`, `liveAngleRef`, `lastAxisRef`, `setVcb` |
| C. ctx + `window.__apolo` | 457-471 | `handlesGroup`, `ctx` | `builtRef`/`sharedRef`/`buildKeyRef` (los vacía), `buildCountRef` |
| D. composer | 525-545 | `composerRT`, `composer`, `outlinePass`, `destello`, `selMeshes` | scene, camera, renderer |
| E. resize | 547-556 | `resize`, `observer` | `mount`, camera, renderer, composer |
| F. bucle `animate` | 558-635 | `frame`, `dragHideHandles`, `updateHandleSprites`, `rebuildOverlayFromMesh`, `tinted`/`applyBlockedTint` | `dropAnimRef`, `gravityAnimRef`, `blockedRef`, `selectionRef`, `ctx.meshes`, `ctx.handles`, outline, destello, ViewCube |
| G. selección por clic | 637-672 | `raycaster`, `downAt`, `onDown`, `onClick` | gizmo, ViewCube, renderer, camera, `group`, `setViewDir` (cierre del PRIMER render) |
| H. agarrar/estirar/rotar/recuadro + hover | 674-1076 | `movePick`, `stretchPick`, `rotatePick`, `protractor`, `boxStart`, `hoveredHandle` | `raycaster`, `handlesGroup`, `ctx.meshes`, `featuresRef`, `blockedRef`, `scene`, **`dragHideHandles` (lo escribe; lo lee F)**, `isDraggingObjRef`, `isBoxSelectingRef`, controls, gizmo, `liveAngleRef`, `boxRef`, `mount`, `rebuildOverlayFromMesh` (F) |
| I. ergonomía | 1078-1109 | `pickAt`, `onContext`, `onDblClick`, `onFitEvent`, export glTF | `raycaster`, `ctx.meshes`, `group`, `frameBox`/`fitTo` (cierres del PRIMER render) |
| J. limpieza | 1110-1145 | — | todo lo anterior, en este orden: rAF → observer → listeners → `snapMarker` → transportador → glTF → animadores → productos → gizmo → IBL → ViewCube → outline → destello → composer → renderer → canvas → `ctxRef` |

Trampas para el `Ctx`: (1) `dragHideHandles` es un `let` que escriben los arrastres (H) y lee el
bucle (F): pasa a ser un objeto `{ current }` explícito. (2) `raycaster` es UNO compartido por G,
H e I. (3) `setViewDir`, `frameBox` y `fitTo` son funciones del cuerpo del componente que el efecto
captura en el PRIMER render; funcionan porque leen `ctxRef`/`selectionRef`, así que el `Ctx` las
lleva tal cual (no hace falta refrescarlas). (4) Los listeners del gizmo (`dragging-changed`,
`objectChange`) nunca se quitan: los libera `gizmo.dispose()`; se mantiene.

Fuera del montaje: geometría y pose del gizmo de rotación (`:36-221`), `VIEWS` y `axisLetter`
(`:223-233`), los efectos de reconstrucción de mallas, gizmo, pose cinemática, medición, física y
gravedad (`:1148-1323`), encuadre y atajos (`:1325-1418`), VCB y rotación exacta (`:1420-1446`), el
JSX (`:1462-1515`) y las funciones de `poses` (`:1518-1631`).

Línea base en el piloto: NO se midió en esta fase. La API de :8000 la está usando Mario y este
subagente no la toca; el hook expone hoy `meshIds()`, `builds()` y `store` (`Viewport.tsx:467`).
La línea base (mallas y `builds()` en el 74 y la 73) queda para F3, antes de mirar la sombra.

### F1 (2026-10-19)

Refactor puro de `Viewport.tsx`: **1631 → 418 líneas**, fuera de `EXCEPCIONES` de
`ui/src/tamanoArchivos.test.ts`. Las líneas se movieron con un script que copia rangos VERBATIM
del original y después se comparó línea a línea (recortada) cada módulo nuevo contra el
original: lo único distinto son los encabezados, los `export`, las firmas nuevas y
`dragHideHandles = …` → `ocultarTiradores.current = …`.

| módulo (`ui/src/viewport/`) | líneas | qué tiene (líneas del original) |
|---|---|---|
| `pipeline.ts` | 149 | renderer, escena, cámara, controles, luces, suelo, IBL, ViewCube, grid, gizmo (`:320-354`), composer y passes (`:525-545`), `resize` (`:547-556`), bucle y su limpieza |
| `gizmoRot.ts` | 226 | flechas de rotación, materiales, `buildOverlay`, guías (`:36-221`) y `actualizarTiradores` (antes `updateHandleSprites`, `:563-587`) |
| `poses.ts` | 123 | `sectionPlanes`, `attachGizmo`, `computePoses`, `applyKinematicPoses` (`:1518-1631`) |
| `mallas.ts` | 94 | `sincronizarMallas`: el diff de mallas por `rev` (`:1159-1215`) |
| `tinteBloqueo.ts` | 29 | tinte de guardado fallido (`:601-619`) |
| `medicion.ts` | 26 | el overlay de la medida (`:1247-1264`) |
| `camara.ts` | +25 | `VIEWS` y `encuadrar` (antes el cuerpo de `frameBox`) |
| `interaccion/ctx.ts` | 49 | `VistaCtx` (el `Ctx` de antes, lo que guarda `ctxRef`) y `CtxInteraccion` |
| `interaccion/gizmo.ts` | 197 | snap y HUD del gizmo, `commitGizmo` (`:356-455`, `:473-523`), `axisLetter`, `aplicarVcb` |
| `interaccion/seleccion.ts` | 51 | clic, «elegir punto» y clic en el ViewCube (`:640-672`) |
| `interaccion/manipular.ts` | 392 | agarrar-mover, estirar, rotar por flechas, cono Z y recuadro (`:588-600`, `:674-778`, `:828-1070`) |
| `interaccion/hoverTiradores.ts` | 59 | hover de los tiradores (`:779-827`) |
| `interaccion/ergonomia.ts` | 50 | menú contextual, doble clic, `apolo:fit` y export glTF (`:1079-1109`) |

**El `Ctx`** (`interaccion/ctx.ts`): `CtxInteraccion = VistaCtx` (scene, camera, controls,
gizmo, renderer, group, meshes, dir, ground, handles) + `mount`, `viewCube`, UN `raycaster`,
`boxRef`, `liveAngleRef`, `featuresRef`, `blockedRef`, `lastAxisRef`, las tres banderas
`isGizmoDraggingRef`/`isBoxSelectingRef`/`isDraggingObjRef`, `ocultarTiradores` (`{ current }`,
el antiguo `let dragHideHandles` que escribe la manipulación y lee el bucle), `setVcb` y los
cierres del primer render `setViewDir`/`frameBox`/`fitTo`. Cada módulo es
`instalarX(ctx) → limpieza`.

**El punto de enganche** (`pipeline.ts`): `antesDeComponer(tarea)`. El bucle hace
`controls.update()` → tareas en orden de registro → contorno de selección + destello →
`composer.render()` → ViewCube, que es exactamente el orden de antes con las tareas = drop-test,
gravedad, tinte y tiradores. La sombra de F2 se registra como una tarea más, al final.

Orden de limpieza conservado: `pipe.detener()` (rAF + observer) → limpiezas de
`interaccion/` (gizmo: teclas + `snapMarker`; selección; manipulación: punteros + transportador;
ergonomía: menú, doble clic, `apolo:fit`, glTF) → animadores → productos → `pipe.dispose()`
(gizmo, IBL, ViewCube, outline, destello, composer, renderer, canvas) → `ctxRef = null`.

Decisiones y diferencias (ninguna cambia el comportamiento):

- `handlesGroup` entra a la escena ANTES que el `snapMarker` (antes, después): el gizmo se
  instala con el `Ctx` ya armado. Ninguno es raycasteable por el otro ni comparte `renderOrder`.
- `meshes` lo crea el pipeline (el bucle lo necesita para el contorno); es el mismo `Map` que
  `ctx.meshes`.
- La lógica repetida de puntero → NDC (siete copias) se dejó tal cual: deduplicarla sería
  cambiar código, no moverlo. Queda para cuando alguien toque la manipulación.
- Tests nuevos: `poses.test.ts` (8: sección, poses encadenadas, vuelta a cero, gizmo) y
  `gizmoRot.test.ts` (7: anclaje de las flechas según la cámara, eje del arco, overlay de una
  pieza no-caja, escala constante de los tiradores). La caja con tiradores de estirón usa
  `<canvas>` y no corre en node: queda para F3. vitest 208 → 223, `npm run build` verde.

### F2 (2026-10-19)

`ui/src/viewport/sombraContacto.ts` (266 líneas), con la técnica de `webgl_shadow_contact` y sólo
`three` (sin dependencias nuevas). `Viewport.tsx` queda en 429 líneas.

- **D2.** Cámara ortográfica EN el plano mirando hacia +Z (`rotation.x = π`: derecha = +X,
  arriba de la imagen = −Y → la geometría del plano lleva la V invertida; un test proyecta las
  esquinas y comprueba que el UV coincide). Profundidad a un RT de 512², blur H+V dos veces (radio
  y 0,4 · radio) con un `FullScreenQuad`, y un `MeshBasicMaterial` negro con esa textura en un plano
  en `min.z − 0,25 mm` del bbox de `group` (el suelo direccional queda en `min.z − 0,5`).
  Encuadre CUADRADO (lado mayor + margen) para que el desenfoque sea igual en X que en Y.
  Diferencias con el ejemplo: el material de profundidad lleva test de profundidad (bajo una
  pata gana lo más cercano al piso, no lo último dibujado) y `DoubleSide` (chapas y superficies
  abiertas). El pase dibuja sólo `group` y las luces: oculta el resto de la escena (grid, suelo,
  gizmo, overlays, cajas del drop-test y el propio plano) y restaura visibilidad, fondo, color de
  limpiado, render target y `shadowMap.autoUpdate` (apagado durante el pase para no rehacer el
  mapa de la luz). Las luces no se apagan: cambiaría el estado de luces de todos los materiales.
- **Constantes** (calibrar en F3): `OPACIDAD_CONTACTO = 0.7`, `OSCURIDAD = 1`, `RADIO_BLUR = 3.5`,
  `MARGEN_FRACCION = 0.15` / `MARGEN_MIN_MM = 150`, `ALCANCE_FRACCION = 0.5` / `ALCANCE_MIN_MM = 100`
  (hasta qué altura «ve» la sombra: la mitad del alto de la máquina), `INTERVALO_MIN_MS = 100`.
- **D3.** `crearProgramador`: nace sucia; `toca(ahora, continuo)` da `true` si está sucia o hay
  algo continuo, nunca dos veces en menos de 100 ms (lo pedido en el hueco queda PENDIENTE, no se
  pierde) y hace una pasada final al terminar lo continuo. **Qué la marca sucia**: el efecto de
  mallas (`fijarPlanos(planes)`: reconstrucción, visibilidad, shading, sección), el de pose
  cinemática, el de física (drop-test) y el de gravedad. **Continuo** (≤ 10 Hz): arrastre directo
  (`isDraggingObjRef`), gizmo (`isGizmoDraggingRef`) y la caída por gravedad corriendo
  (`gravityPlaying`). El slider de juntas marca en cada cambio y el tope de 100 ms lo deja en
  10 Hz. En reposo la tarea es una comparación por frame.
- **D4.** `scene-setup.ts::OPACIDAD_SOMBRA_DIRECCIONAL = 0.15` (antes 0,25 a pelo).
- **D5.** Sin control nuevo. `plano.visible = calculada && ground.visible`; el plano mira hacia
  +Z, así que desde abajo no se ve. Decisión propia: el suelo NO se oculta hoy con la sección
  (el plan lo suponía), así que con sección activa la sombra sigue, pero de lo que se ve: el
  material de profundidad usa los mismos planos de corte (`fijarPlanos`).
- **Enganche.** Una tarea más de `pipe.antesDeComponer`, la última (después de animadores, tinte
  y tiradores): las mallas ya están en su pose del frame. `ctx.sombra` está en `VistaCtx`
  (los efectos la marcan); `window.__apolo.sombraRecalculos()` cuenta los recálculos para F3.
- Tests: `sombraContacto.test.ts` (13: encuadre y alcance, cámara mirando hacia arriba,
  frustum, UV ↔ proyección, programador en reposo / pendiente / 10 Hz / pasada final, y con un
  renderer falso: no recalcula en reposo, sí tras `fijarPlanos` o `marcarSucia`, qué está visible
  al dibujar la profundidad y que todo se restaura, plano en el `min.z`, oculto con el suelo y sin
  piezas). vitest 223 → 236, `npm run build` verde. No se miró en un navegador (la API de :8000 es
  de Mario): el aspecto, el costo en la 73 y el 74 y la calibración son F3.
- `ui/CLAUDE.md` § Viewport: una línea con el reparto de módulos y la trampa de la sombra (algo
  nuevo que mueva mallas tiene que marcarla sucia).

### F3 (2026-10-19): verificación en el navegador y piso de estudio

UI servida por la API en :8000, faja en chapa C (proyecto 73, 117 piezas).
- **D3 se cumple**: `window.__apolo.sombraRecalculos()` = 3 al cargar y no sube en reposo ni al
  girar o acercar la cámara.
- **Hallazgo**: la sombra funcionaba pero casi no se veía. Es negra y el fondo del visor es casi
  negro (`#1b1e24`): sin un piso visible no hay contra qué leerla. Diagnóstico equivocado del
  plan: suponía que el problema era la sombra desplazada; era la falta de piso.
- **Piso de estudio** (`scene-setup.ts::crearPisoEstudio`): disco `#4a515c` bajo la máquina,
  radio 1,6 × la mitad del lado mayor + 400 mm, opaco al centro y desvanecido al borde
  (`smoothstep`), `renderOrder -2`. Lo coloca `updateGround` con el suelo.
- **Grilla**: sobre el disco claro, sus líneas oscuras (`0x2c313b`) dejaban un parche negro. Ahora
  son claras semitransparentes (`0xb4bccb`, opacidad 0,06, sin escribir profundidad): con 0,14 se
  veía demasiado.
- Constantes de la sombra sin cambios (`OPACIDAD_CONTACTO 0.7`, `RADIO_BLUR 3.5`). Falta mirarla de
  cerca en el piloto (74) con la cadena y los rodillos; no bloquea.
