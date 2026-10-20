---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: contrato aprobado (Mario, 2026-10-19: «escribe el plan y lánzalo»); faltan F0–F2 (un subagente) y F3 (verificación en el navegador)
descripcion: La máquina se apoya en el piso con una sombra de contacto suave en el visor, y el visor queda partido en módulos que se pueden seguir mejorando
---

# La máquina se apoya en el piso: sombra de contacto en el visor

## Estado y origen

Mario, al ver el piloto (proyecto 74) con los acabados nuevos de
[visor-realista](visor-realista.md) F1, preguntó si el piso con sombra «es también mejora» y
pidió: «sí, escribe el plan y lánzalo» (2026-10-19). Es el pendiente que dejó visor-realista F1
(§ Bitácora F1, «Pendiente de F1 — piso con sombra de contacto»): sin sombra de contacto la
máquina parece flotar sobre el fondo oscuro, y eso pesa en las capturas, el video de la tienda y
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

- No cambia el render VTK (fotos, GIF, video) ni el GLB de la tienda: cada uno tiene su motor.
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
