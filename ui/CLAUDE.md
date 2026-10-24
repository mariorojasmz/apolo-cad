# UI de Apolo (React + three.js + Dockview)

Las convenciones técnicas de la UI (viewport, store, sync, layout) están al final, en
«Convenciones técnicas»; el lado servidor de lo que consume (deltas de escena, `merge` del PUT),
en [core/apolo/api](../core/apolo/api/CLAUDE.md). Lo transversal (worktrees, flujo de trabajo)
está en el [CLAUDE.md raíz](../CLAUDE.md).

**Todo texto que lee un usuario va de TÚ, en español neutro latinoamericano**: sin voseo, sin
usted, sin españolismos. Vale para los strings de la UI, los mensajes de error de la API que
llegan a pantalla y los prompts de agentes que le hablan al usuario. Gate `src/tuteoNeutro.test.ts`:
lo interno se declara en su `EXCEPCIONES` con la razón, o con `// voseo-interno` al final de la línea.

## Calidad visual: sobria, clara, «como lo haría Apple» (Mario, 2026-10-23)

La persona pide por MCP o al agente y EVALÚA en el visor: cada resultado que el agente lee tiene
que poder verse ahí. Un panel nuevo:
- responde UNA pregunta arriba (un veredicto), y el detalle se revela a pedido;
- usa sólo los tokens del tema (claro y oscuro); jerarquía por peso y tamaño del texto, no por
  cajas, bordes ni colores nuevos;
- anima sólo lo que orienta (encuadre, abrir, plegar: ≈ 250–400 ms, aceleración suave) y respeta
  `prefers-reduced-motion`; nada parpadea ni rebota;
- se cierra con una revisión de diseño A CIEGAS: capturas en claro y oscuro, ancho y angosto, que
  juzga un subagente sin contexto con la rúbrica del plan. [V8.5](../docs/plans/V8.5-tablero-3d.md) D13–D14

Las piezas viven en `src/diseno/` (`<Veredicto>`, `<ItemsAtencion>`, `<EstadoVacio>`, `<Deslizador>`,
`cifra()`, `movimiento.ts`) y los tokens en `styles.css` `:root` (`--fs-*`/`--fw-*` con nombre, `--sp-*`
de 4 px, `--mov-*` y `--curva-suave`, a 0 con movimiento reducido); `diseno/tokens.test.ts` rebota un
color, tamaño o duración suelto en su CSS. Las capturas salen del muestrario (`ui/muestrario.html`,
sólo con `npm run dev`; `?ancho=420` para angosto). Hoy sólo hay tema oscuro (A12 de V8.5).

## Texto y ayuda: la pantalla se explica sola

**Nunca un texto para tapar una interfaz confusa**: si hay que explicar cómo funciona la
pantalla, primero se arregla el rótulo, el botón o el control.

### Cada texto contesta una pregunta, y cada pregunta tiene su lugar

| Pregunta | Nivel | Pieza | Visible | Tope |
|---|---|---|---|---|
| — (se entiende sola) | N0 | un buen rótulo o botón | — | — |
| ¿Qué tengo que hacer aquí? | N1 | `<Pista>` (pista bajo el campo o la acción) | siempre | 1 frase, ≤ 120 caracteres |
| ¿Qué significa esto? | N2 | `<Ayuda>` (ⓘ junto a la palabra) | a pedido | ≤ 3 frases, ≤ 60 palabras |
| ¿Cómo es por dentro? | N3 | `<VerDetalle>` (plegable en el lugar) | a pedido, plegado | con viñetas |
| ¿Cómo funciona esta pantalla? | N3 | «Cómo funciona» del panel (modal) | a pedido | ≤ 150 palabras, una por panel |

Se decide en ese orden: la primera respuesta que cierra, cierra. Un **error caro** (borrar
piezas, restaurar una revisión, aplicar una variante que regenera todo) no se advierte con un
párrafo: se confirma (`useConfirmar`, una sola pieza de confirmación para todo). La primera
vez en un panel la cubre `<EstadoVacio>` (qué va a aparecer + la acción), no un tour.

Existen `<Pista>`, `<Ayuda>` (ⓘ `type="button"`, abre en el flujo), `<VerDetalle>` (`<details>`
nativo) y `textoTecnico` (backticks → `<code>`) en `src/ui/`, y `forms/Campo.tsx` (rótulo +
unidad + ⓘ + pista de campo) ([plan](../docs/plans/texto-agente-vs-persona.md)). `<EstadoVacio>`
está en `src/diseno/`; `useConfirmar` todavía NO existe: se propone en un plan antes de crearla.

- **Presupuesto**: sin contar datos ni rótulos, el texto de ayuda visible por defecto de un
  panel o diálogo no pasa de ~40 palabras. **Una explicación, un lugar**: si el panel lo dice,
  el resto no lo repite.
- **El texto de los schemas es para el AGENTE, no para la persona.** Las `description` de los
  modelos pydantic de comandos son largas a propósito (el agente las necesita completas, con
  nombres de parámetros). La UI pide la vista PERSONA (`GET /api/schemas?vista=persona`): cada
  comando trae su `pista` (una frase escrita para la persona) y su `detalle` limpio, que va
  plegado en «Detalle técnico»; los campos traen `x-unidad` y, donde uno anula a otro, `x-pista`.
  La pista vive en `core/apolo/commands/pistas.py` (gate `tests/test_pistas.py`: 1 frase, ≤ 120
  caracteres, vocabulario y tuteo); el servidor quita las versiones del roadmap («V6.8-E»). El
  tipo `CommandSchema` no tiene `description`: `tsc` impide pintar el texto del agente.
- **Excepción de parámetros**: la ⓘ de un campo de comando lleva su texto operativo COMPLETO
  aunque pase el tope (es la documentación del parámetro); lo que se acorta es la pista.
- La **ⓘ se abre en el flujo**, no flota (se cortaría en los paneles de Dockview con
  `overflow`). ⚠️ **Nunca dentro de un `<label>`**: se come el clic del control.
- **`title=` sólo repite lo que ya se ve** (el nombre de un ícono del ribbon o del viewport).
  Lo que el usuario necesita —el motivo de un botón deshabilitado, un costo, qué hace el
  comando— va visible: en una tableta el `title` no existe.
- **Lo técnico suma detalle a pedido, no a la vista**: ids de pieza (`c45_2`), command ids,
  rutas, nombres de parámetros y JSON van en `<VerDetalle>`. Excepción deliberada: el árbol y
  el buscador muestran el id porque el usuario lo usa para hablar con el agente.

### Qué dice cada texto

| Texto | Dice | No dice |
|---|---|---|
| Botón | verbo + objeto: «Crear grupo», «Guardar revisión» | «Aceptar», «Continuar», «OK» |
| Estado | qué está pasando y qué te toca, en una frase | el mecanismo («para liberar el lock») |
| Estado vacío | qué va a aparecer aquí + la acción para empezar | «No hay datos» a secas |
| Error | qué pasó + qué hacer ahora | el stack, el código HTTP, la variable |
| Confirmación | título con el verbo, la consecuencia en una frase, el botón repite el verbo | «¿Estás seguro?» a secas |
| `placeholder` | un ejemplo del valor, inventado | el rótulo, instrucciones, datos reales de un cliente |

**Nunca en pantalla**: versiones del roadmap (V6.8-E, V7.2b) ni la historia («desde que…»,
«porque el backend…»); nombres de comandos o parámetros (`drill_hole`, `en_cara`), variables
de entorno, rutas o claves fuera de un `<VerDetalle>`; una instrucción de editar un archivo o
llamar a la API a mano (es la señal de que falta el control en la UI: se escala); un estado
crudo (`in_progress`, `suppressed`): se mapea a su etiqueta.

### Una cosa, un nombre

Cada concepto tiene UN nombre en toda la interfaz. La tabla se mantiene acá y se respeta en revisión:

| Concepto | Se dice | No se dice |
|---|---|---|
| un objeto 3D del modelo | **pieza** | sólido, feature, cuerpo |
| el dibujo 2D con restricciones | **croquis** | sketch, dibujo |
| las cajas rápidas para tantear volúmenes | **boceto** | maqueta (y no es un croquis) |
| la articulación que deja mover piezas | **junta** | articulación, joint |
| perno, soldadura o contacto declarado entre dos piezas | **unión** | fijador, fastener |
| piezas que se mueven y se listan juntas | **grupo** | conjunto; «sub-ensamblaje» sólo en la ⓘ |
| una foto guardada del proyecto | **revisión** | versión, snapshot |
| un juego de valores de las variables | **variante** | configuración |
| una operación del historial | **comando** | operación, acción |
| un paso de Deshacer/Rehacer (puede ser un lote de comandos) | **cambio** | paso, acción |
| una hoja del juego de planos | **lámina** | hoja, página |
| la lista de piezas y compras | **BOM** (sigla del oficio, se acepta) | lista de materiales en un rótulo |
| lo que se pierde / lo que sale de una lista | **Eliminar** / **Quitar** | Borrar, Remover |
| el correo · la acción del mouse | **correo** · **haz clic** / **toca** | email, mail · pulsa, click, ratón |
| el cuadro eléctrico con sus aparatos | **tablero** | gabinete, panel eléctrico (un «panel» es de Apolo) |
| pulsador, seta, selector o seccionador que maneja la persona | **mando** | control, botonera (si no es el aparato) |
| un valor con nombre que mide la simulación (`-M1.rpm`) | **señal** | variable, tag, canal |
| la situación que se simula (condiciones, cajas, acciones) | **escenario** | caso, prueba |
| la simulación que manejas mientras corre | **sesión viva** | sesión en vivo, modo en vivo, live |
| las curvas de las señales en el tiempo (con disparo) · la señal anclada en grande | **osciloscopio** · **multímetro** | tendencias, gráfico · medidor, display |

La interfaz habla en **plural** («te avisamos»). Los nombres internos del código no aparecen
en la vista del usuario. Registro: tuteo neutro latinoamericano, sin voseo ni usted; nada de
inglés en rótulos ni `aria-label` (salvo las siglas de la tabla).

### Por tipo de pantalla

| Tipo en Apolo | Visible | A pedido | Nunca |
|---|---|---|---|
| Lista (árbol, historial, revisiones) | título, «Nuevo …», buscador, estado vacío con acción | ⓘ en el rótulo del filtro | párrafo sobre la lista |
| Ficha (Propiedades) | nombre, material, datos con rótulo | ⓘ; `<VerDetalle>` para ids y params crudos | JSON a la vista |
| Formulario (diálogo de comando, Requisitos) | rótulos claros; pista sólo donde la gente se equivoca | ⓘ del parámetro; validación al salir del campo | la descripción del agente entera arriba; pista en todos los campos |
| Proceso con decisión (Validar, delivery check, FEA) | el veredicto y qué te toca, en una frase; la decisión arriba con su costo | `<VerDetalle>` con el porqué; «Cómo funciona» | la decisión explicada en vez de mostrada |
| Tablero (BOM con costos, Física, Cinemática) | cifra + rótulo; el vacío dice por qué | ⓘ con qué mide | párrafo de metodología |
| Viewport y ribbon | ícono + rótulo corto | `title=` con el nombre | la descripción del comando en `title=` |
| Chat (Asistente IA) | el `placeholder` dice qué se puede pedir, con un ejemplo | — | párrafo de bienvenida |

### Los gates (`cd ui ; npm test`)

- **`src/textoDeAyuda.test.ts`** mide los literales (`subtitle=`, `hint=`, `<Pista>`, `<Ayuda>`)
  contra los topes de arriba, y la historia fuera de un comentario: «plan NNN» y la versión
  del roadmap («V6.8-E»). No ve el texto dinámico que llega de los schemas.
- **Trinquete**: su `EXCEPCIONES` declara cuántas violaciones le quedan a cada archivo. Falla si
  el número sube (texto nuevo que no cumple) y también si baja sin actualizarlo. La lista sólo
  se achica, en el mismo commit que limpia.
- **`src/tuteoNeutro.test.ts`** recorre `src/` entero y rebota voseo (también con pronombre
  pegado: «revisala»), «usted» y españolismos inconfundibles («pulsa», «ratón»). Lo que se
  enumera son las excepciones, con su razón; una excepción que ya no hace falta también falla.
- Los dos son copia de un estándar común a otros proyectos del titular: al actualizarlos, traer
  la versión nueva y re-aplicar sólo el bloque «Configuración del proyecto».
- **`src/tamanoArchivos.test.ts`**: ningún `.ts`/`.tsx` de `src/` pasa de 500 líneas; los que ya
  pasan, congelados en su `EXCEPCIONES` (trinquete: el número sólo baja).
- Los `*.test.ts` están fuera de `tsconfig.json` (usan `node:fs`; la app no carga los tipos de
  Node): vitest los corre sin chequeo de tipos.
- Dos archivos de `src/` cuyos nombres sólo difieren en mayúsculas (`HistorialCambios.tsx` y
  `historialCambios.ts`) rompen `npm run build` en Windows (TS1261) aunque vitest pase: la lógica
  pura lleva otro nombre (`deshacer.ts`, `variantes.ts`).

### Limpiar lo que ya existe

Por panel, no todo de una: leer cada pantalla entera y clasificar cada texto en **jerga**
(nombres internos a la vista), **sobra** (describe la pantalla o explica el sistema),
**confuso**, **falta** (acción irreversible sin confirmar, info sólo en `title=`, vacío sin
acción), **inconsistente** (una cosa con varios nombres) o **registro**. Primero lo que
**miente** (texto que contradice lo que la pantalla hace) y lo que **evita un error caro**
escondido. El estándar es el criterio, no la lista: la lista envejece con la primera fase.

## Convenciones técnicas

### Desarrollo y verificación

- Preview: configs `ui-dev`/`ui-preview` en `.claude/launch.json`; el build de producción lo
  sirve la API en :8000. `npm run dev` + StrictMode remonta el viewport y lo rompe: usar
  `vite preview` (`ui-preview`). Gates: `npm test` (vitest) y `npm run build` (tsc + vite).
- El screenshot automatizado del viewport se agota por el rAF continuo: verificar por DOM o por el
  hook `window.__apolo` (`meshIds`, `builds`, `sombraRecalculos`, `store`). El rAF se PAUSA en una pestaña de fondo
  (lo que fija el animate loop, como `g.visible`, queda viejo) y un `await requestAnimationFrame`
  desde la tool de JavaScript del navegador cuelga: para la lógica del overlay, leer estado
  expuesto a `window` (`ctx.handles.children`, params), no la visibilidad.

### Shell y paneles

- Dockview: el viewport es el centro fijo y bloqueado que NUNCA se re-monta; el layout se
  persiste y `resetLayout` no destruye el viewport.
- Dos modos de pantalla (`visor/estado.ts`, por defecto **Visor**): el visor MAXIMIZA el grupo del
  viewport (`dockApi.ts::setModoVisor`, mismo canvas) y la capa `visor/CapaVisor.tsx` pone encima
  cajones, barra de paneles, ficha y avisos. ⚠️ Dockview serializa el maximizado y
  `exitMaximizedGroup()` no dispara `onDidLayoutChange`: nunca se persiste maximizado
  (`guardarLayout`). Algo nuevo para el visor va a la capa, no al ribbon ni a la StatusBar
  (no se montan). [plan](../docs/plans/modo-visor.md)
- Panel nuevo = `dock/paneles.ts` `NUCLEO` (componente, título, rótulo e ícono; de ahí salen
  Dockview, la StatusBar y los cajones del visor) + `HERRAMIENTAS_NUCLEO` si se conmuta (StatusBar y
  «Más» del visor). Un id que llega como texto (layout guardado, cajón) pasa por `esPanel`, y el
  layout guardado se poda al restaurar (`dock/podarLayout.ts`): Dockview monta un panel que el
  bundle no trae con un componente vacío y React revienta.
- **Extensión de la UI** (paquete privado, se compone al COMPILAR): su `ui/` se copia en
  `src/extensiones/<nombre>/` (ignorado por git) con un `index.ts` cuyo `export default` es una
  `Extension` (`extensiones/tipos.ts`; paneles con id `<nombre>.<panel>`). `extensiones/registro.ts`
  la recoge con `import.meta.glob` y la valida: no se edita ningún archivo del núcleo y los gates la
  recorren. Lo que crezca entra como campo OPCIONAL de `Extension`. Un proyecto en sólo lectura
  (falta una extensión) se lee con `state/soloLectura.ts`.
  [plan](../docs/plans/nucleo-abierto-extensiones-privadas.md) (D4, D5)
- Feedback de carga global: `guard`/`runTracked` + `BUSY_TEXT` (store).
- Otros paneles accionan el viewport por `CustomEvent` (`"apolo:fit"` con `{id}` o `{ids}`,
  `"apolo:export-gltf"`) para no acoplar el store a three.js. Un panel que SEÑALA una pieza usa
  `viewport/pedirEncuadre.ts` con `animar` (vuela, `vuelo.ts`, con contexto alrededor de una pieza
  chica) y `seleccionar` (contorno); sin ellos, `apolo:fit` salta como siempre. El glTF se exporta en el cliente
  (`viewport/exportGltf.ts`); STEP/STL, por endpoint.

### Layout

- Toda región scrollable/flex necesita altura ACOTADA (`minmax(0,1fr)`): una fila implícita
  `auto` crece hasta el hijo más alto y desborda. Los `grid-row` numéricos se rompen al cambiar
  `grid-template-rows` (reindexar). `overflow: hidden auto` mata la barra horizontal fantasma.

### Sync con el servidor

- `api.editCommand` (PUT) REEMPLAZA los params por defecto (`merge=false`): un edit PARCIAL
  (`{width}`) borra los hermanos y la caja colapsa al default del schema. Los edits de cota de
  `create_box` pasan `merge=true`; los forms schema-driven mandan todos los campos (ahí reemplazar
  es inocuo).
- Manipulación directa (`store.ts::pumpEdit`): estirones y cotas van por `editCommandSilent`, una
  cola por command_id donde el ÚLTIMO gana (1 en vuelo + 1 pendiente). La escena de la respuesta
  se aplica SÓLO si no hay una edición más nueva en cola (`!editPending.has(id)`); si no, el
  preview parpadea a un tamaño viejo. El preview optimista (malla escalada +
  `rebuildOverlayFromMesh`) se mantiene hasta la última respuesta. Los transforms
  (mover/rotar/subir-Z) son deltas: cola SERIALIZADA (`enqueueSilent`), y ahí cada escena sí se
  aplica.
- `document_changed` llega por CADA comando, incluidos los propios: `connectWs` espera 250 ms
  (debounce) y no refresca si `busy || syncing > 0`. Al depurar un parpadeo hay DOS caminos que
  aplican escena (respuesta de `editCommand` + refresh del WS): revisar ambos (commit `e2e15d8`).
- El refresh es por DELTA: `mergeSceneDelta` hereda la geometría de las piezas `same` y el
  viewport diffea por `rev` (sólo reconstruye la pieza cambiada; la apariencia se rehace en sitio
  con `applyAppearance`). Cada RECONEXIÓN del WS fuerza un refresh completo (el `epoch` del
  servidor pudo cambiar).
- El refresh NO-completo es un cambio externo (agente, chat autónomo): publica en `window`
  `apolo:cambios-externos` (`state/cambiosExternos.ts`; no publica con otro epoch u otro
  proyecto) y el visor marca esas piezas. Una acción propia que no aplique la escena de su
  respuesta saldría marcada como del agente. [plan](../docs/plans/modo-visor.md)
- Los avisos `{"type": "job"}` del WS se validan en `state/eventosWs.ts` y `connectWs` los publica
  en `window` (`apolo:job`; `apolo:ws-reconectado` en cada reconexión); `visor/trabajando.ts` lleva
  los jobs corriendo. Todo job cuenta como del agente porque la UI nunca manda `?async`: si algún
  día encola uno, se filtra ahí por su `job_id` o saldría «el agente está trabajando».

### Viewport

- Contorno de selección por `EffectComposer` (`RenderPass` → `OutlinePass` → `OutlinePass` verde
  del destello de los cambios del agente, `destello.ts` → `OutputPass`), no
  `renderer.render` directo. El RT del composer DEBE ser `HalfFloatType` + `samples: 4`:
  HalfFloat preserva el HDR lineal para que `OutputPass` aplique ACES + sRGB una sola vez (three no
  tonemapea al renderizar a un RT), y `samples` conserva el MSAA. Las mallas seleccionadas se
  recolectan cada frame desde `selectionRef` (robusto a reconstrucciones). El ViewCube se dibuja
  tras `composer.render()` (`autoClear=false`).
- `Viewport.tsx` orquesta; el render y el bucle viven en `pipeline.ts` (tareas por frame con
  `antesDeComponer`) y la interacción en `interaccion/` (`instalarX(ctx) → limpieza`, `Ctx`
  explícito en `interaccion/ctx.ts`). La sombra de contacto (`sombraContacto.ts`) NO se calcula
  por frame: algo nuevo que mueva mallas fuera de un arrastre o de la gravedad la marca con
  `ctx.sombra.marcarSucia()`, o la sombra queda vieja. [piso-con-sombra](../docs/plans/piso-con-sombra.md)
- La máquina en marcha (`viewport/marcha/`): store propia (`estado.ts`), reproductor que mueve las
  mallas REALES con `T(t)·baseMatrix` en una tarea del bucle y `enVista.ts`, que lo arma DESPUÉS
  de los efectos de mallas y pose. La gravedad y el drop-test mueven las mismas mallas: cargar
  uno quita la marcha, y «Ver la marcha» limpia los dos.
  [visor-realista](../docs/plans/visor-realista.md) (F2)
- Una pose de la serie se interpola entre muestras como movimiento RÍGIDO (por tornillo,
  `serie.ts::poseEn`), nunca lerp de la posición + slerp de la rotación: con T = P(t)·P(0)⁻¹, un
  cuerpo que gira sobre un eje lejos del origen se sale de su eje a mitad de cada muestra.
  [V8.4](../docs/plans/V8.4-maquina-viva-en-pantalla.md) § F5
- En marcha, `marcha/transmision.ts` oculta la banda y la cadena del CAD y pone en `ctx.group` (con
  `raycast` no-op) la cinta con su ruta real (`faja.ts`: UV en mm, corre la TEXTURA) y los eslabones
  instanciados (`cadena.ts`). Cada pieza trae su propio material: las cadenas comparten instancias
  por ASPECTO (`claveAspecto`), no por objeto. Lo que la banda o la cadena arrastran sin junta (cola,
  retorno, piñón del motor) gira compuesto SOBRE la pose de su cuerpo. [visor-realista](../docs/plans/visor-realista.md) (F3)
- Fondo: `OutputPass` tonemapea también el color de limpiado → el canvas es TRANSPARENTE
  (`alpha: true`, clear alpha 0) y el fondo lo pinta el `<div>` por CSS. `BACKGROUND` /
  `BACKGROUND_CSS` (`scene-setup.ts`) son la fuente única.
- Material de una pieza = su ACABADO (`feat.acabado`, `feat.albedo`, resueltos en el servidor)
  sobre la tabla `viewport/acabados.json`, copia GENERADA de `library/apariencia.py`: no se
  edita a mano. Las muestras de color muestran el albedo. Relieves procedurales con UV de caja
  en mm (`relieve.ts`) y texturas de color y brillo (`textura.ts`; el cepillado pasa a
  `MeshPhysicalMaterial` por la anisotropía). [visor-realista](../docs/plans/visor-realista.md)
- Una pieza con `feat.zonas` (la seta roja sobre amarillo) es UNA malla con `geometry.groups` y
  un ARREGLO de materiales (`viewport/zonas.ts`; el albedo de cada zona ya viene resuelto): todo
  lo que lea o clone `mesh.material` acepta un arreglo (`materialesDe`, `liberarMaterial`).
  [seta-de-emergencia](../docs/plans/seta-de-emergencia.md)
- Calidad del visor (`calidad.ts`, store propia; el botón vive en `BarraVista`): «alta» = estudio
  procedural como IBL (`estudio.ts`) + GTAO + SMAA SIN MSAA (`calidadVista.ts`); «normal» =
  RoomEnvironment + MSAA ×4. El pipeline la sigue en caliente. El GTAO hace una SEGUNDA pasada de
  la escena y sólo dibuja `group` sin aristas: algo nuevo que deba oscurecerse va en `group`.
  [video-realista](../docs/plans/video-realista.md)
- `near`/`far` de la cámara se ajustan EN CADA CUADRO a la esfera de la máquina y al piso
  (`recorte.ts`, en el bucle de `pipeline.ts`): con un `near` fijo de 1 mm, a 6 m el buffer de
  profundidad sólo separa ~2 mm y la cama asomaba en manchas a través de una banda de 3–4 mm.
  Una cámara nueva que dibuje la escena (grabación, foto) pasa por el mismo ajuste.
- Grabación (`viewport/grabacion/`, `window.__apolo.grabar`): reloj VIRTUAL, el cuadro n vale
  n/fps. Por eso toda tarea de `antesDeComponer` usa el `ahora` que recibe, nunca
  `performance.now()`/`Date.now()`: si no, al grabar se mueve con el reloj real. El modo grabación
  para el bucle, fija 1920×1080, apaga contorno, destello, SMAA y ayudas (`pipe.ayudantes` + lo que
  pase Viewport) y acumula N muestras con jitter en vez del `RenderPass`. La foto se toma con
  `drawImage` en el MISMO hilo que el render (sin `preserveDrawingBuffer`).
  [video-realista](../docs/plans/video-realista.md) (F2)
- El guion del video (`grabacion/guionVista.ts`; «Grabar video» y `?grabar=<sesion>`, que abre
  la fábrica de publicaciones —fuera del núcleo— para grabar en un navegador sin ventana, vía
  `grabacion/registro.ts`) REPRODUCE el plan que manda
  la API (`planGuion.ts`): ninguna regla del guion (tiempos, fundidos, órbita, quién entra) se
  calcula aquí, se agrega en `services/plan_navegador.py`. Tarjetas y rótulos son PNG de la
  API. El montaje toca sólo lo visible y clona materiales; la marcha se carga al EMPEZAR su parte
  (`transmision.ts` sólo arma lo visible). [video-realista](../docs/plans/video-realista.md) (F3)
- Nivel MÁXIMO y «Foto realista» (`grabacion/trazado/`, carga con `import()`): `three-gpu-pathtracer`
  0.0.23 + `three-mesh-bvh` 0.7.8, versiones EXACTAS (`trazador.ts` usa su interior). Esa versión
  no sabe de instancias, arreglos de materiales (zonas), `bumpMap`, anisotropía ni recorte:
  algo nuevo en `group` con eso pasa por `sustitutos.ts` o se declara en el plan.
  [video-realista](../docs/plans/video-realista.md) (F4)
- Sin glow de hover ni tinte `emissive` de selección: el contorno basta. El tinte rojizo es SÓLO
  para guardado FALLIDO (`applyBlockedTint`, piezas en `blockedRef`); no hay tinte de
  «guardando» (en modelos grandes prendía en cada edición y parecía un spinner permanente).
- **Excepción acotada de color**: el color FÍSICO de un mando o un piloto (`vivo/mandos.ts::colorFisico`,
  del `specs.color` del catálogo; el emisivo de un piloto con pieza) y el color por dato con su
  leyenda (el osciloscopio, `vivo/paleta.ts`). Nunca un rojizo ni un verde de ESTADO. [V8.4](../docs/plans/V8.4-maquina-viva-en-pantalla.md) D9
- La máquina viva (`ui/src/vivo/`, nunca en `Viewport.tsx`): `sesion.ts` lee el `WS /api/cosim/vivo`
  y carga en `useMarcha` una serie `vivo: true` que CRECE EN SITIO (`serieViva.ts`, anillo de 60 s;
  jamás `cargar` por fotograma: rehace el reproductor); `enVista.ts` la arma con
  `reproductorVivo.ts` (el mismo reproductor siguiendo `reloj.ts`, más etiquetas `CSS2DRenderer` y
  mandos 3D). El clic en un mando 3D se toma en CAPTURA sobre el contenedor del canvas (antes que
  selección y órbita). Un pulsador se mantiene ≥ 150 ms (`PULSO_MIN_MS`): un clic más corto entra y
  sale en la misma ventana de 33 ms y el PLC no lo ve. Zustand: selectores PRIMITIVOS en el panel.
  [V8.4](../docs/plans/V8.4-maquina-viva-en-pantalla.md) (F2)
- Medir en vivo (F3): la historia de TODAS las señales vive fuera de React (`vivo/medicion.ts`, anillo
  `historia.ts`; `sesion.ts` le pasa cada fotograma y ahí avanza el disparo) y el osciloscopio la
  dibuja con su propio rAF a ≤ 30 fps (`dibujoOsciloscopio.ts`): nunca por un `set` de zustand por
  fotograma. UN CARRIL POR SEÑAL con su escala (sin ejes dobles), ≤ 8 señales, color de
  `vivo/paleta.ts` (la paleta categórica de datos, validada contra `--panel`) que sigue a la señal,
  no a su orden. Multímetro y osciloscopio van sobre el 3D (`Instrumentos.tsx`, montado por
  `BarraVivo`); el árbol en el panel «Señales» y el ST con valores en «PLC» (el texto sale del log,
  `add_program.fuente`; global `-K1.v`, local `-K1.Main.v`).
- «Simular falla» (`vivo/FallasVivas.tsx`, `FallasActivas.tsx` en la barra): lo que se ofrece sale
  SIEMPRE de `inicio.fallas`/`inicio.ramas`; `fallas.ts` sólo le pone nombre. La activa de un aparato
  llega en `<des>.averia` (textos); la de una RAMA no publica señal y se lleva por el ack de su evento
  (`conAckDeRama`). [cosim-fallas](../docs/plans/cosim-fallas.md) D7
- Agarrar y mover: el pointerdown selecciona y arma un `movePick` pendiente; el arrastre real
  empieza al superar `DRAG_THRESHOLD_PX = 5` (= umbral de `onClick`). Bajo el umbral es un clic:
  no mueve ni commitea.
- Tiradores de caja (`handles.ts::boxDimsFromBbox`): dims desde el BBOX, sanando cotas borradas
  (la caja se auto-sana al primer estirón vía `merge`). Excluye cajas ROTADAS (cota numérica que
  no cuadra con su eje → OBB pendiente) y PARAMÉTRICAS (cota `"=expr"`: no romper el vínculo).
  Las líneas guía van con `depthTest` off, `raycast` no-op y se liberan en el clear por
  `kind: "guide"`.

### Croquis (`panels/SketcherDialog.tsx`)

- Herramientas Arco (centro → inicio → fin), Spline (clics = puntos de control; cerrar como
  perfil o dejar abierta) y Elipse (centro + semiejes/rotación); panel DOF/redundantes/conflictivas.
- Arrastre de puntos con Seleccionar: dead-zone de 5 px + cola el-último-gana contra
  `POST /api/sketch/drag` (patrón `pumpEdit`, no una llamada por píxel); preview en verde mientras
  se arrastra y COMMIT de las posiciones resueltas al soltar. Motor:
  [kernel](../core/apolo/kernel/CLAUDE.md). [V6.6](../docs/plans/V6.6-croquis-vivo.md)

### Chat (`chat/`)

- El panel «Asistente IA» y su botón en la barra de paneles del visor existen sólo si
  `GET /api/health` → `chat` es true (`chat/activo.ts`, una store). `dock/dockApi.ts::aplicarChat`
  lo agrega o lo cierra, también de un layout guardado, y va AL FINAL de `onReady` (después del
  listener del layout; si no, el cierre no se guarda). Hoy viene apagado: Apolo se usa por MCP
  ([plan](../docs/plans/chat-cliente-igual.md), D19).
- El SSE de `/api/agent/chat` se lee SÓLO en `chat/sse.ts` (puro) y `chat/turno.ts` aplica cada
  evento al mensaje; el store sólo los encadena. Un evento nuevo del backend se agrega en `sse.ts`
  (tipo + `validar()`) con su caso en `sse.test.ts`; un `type` desconocido se ignora y uno roto se
  descarta a `logs/errors.log`. [plan](../docs/plans/chat-cliente-igual.md)
- `progreso` con `nuevo: true` empieza una nota de avance; sin la marca, los `progreso` seguidos
  se juntan (así se lee un backend que no marca). Una respuesta HTTP fallida del chat se lee en
  `chat/respuesta.ts`: muestra el `detail` de la API (ya viene en tuteo); el código, sólo de respaldo.
