---
estado: en curso
nota: contrato aprobado por Mario el 2026-10-23 (lo pidió como «Simular falla» en la máquina viva); F0 medida; F1a (backend) mergeada: fallas en modelos, red y escenario, COSIM_EPOCH sin cambio; F1b (UI «Simular falla» en Mandos y la falla activa en la barra) mergeada; faltan la revisión de diseño a ciegas y F3 (verificar sobre una copia de la 77, Mario lo juzga)
descripcion: en la co-simulación un aparato puede fallar a propósito (contacto soldado, seta trabada, cable cortado, corto) en un escenario o en la máquina viva, para ver si la máquina para igual
---

# La máquina se prueba con un aparato que falla

## Estado y origen

- La co-simulación (V8.3, V8.4) prueba la máquina cuando todo funciona y ante eventos del mundo
  (atasco, fase perdida, caída de red, cable cortado, sensor pegado). Falta lo que más importa
  para saber si una parada es confiable: que un APARATO falle (un contactor que queda soldado, un
  contacto que no abre, una salida de PLC que queda prendida) y ver si la máquina igual corta el
  par.
- Quien evalúa lo hace en el visor (`ui/CLAUDE.md` § Calidad visual): la falla se tiene que poder
  simular también en la sesión viva y VERSE.
- Lo pidió Mario (2026-10-23) junto con «Simular falla» en la máquina viva.

## Lo que hay hoy

Rutas relativas a `core/apolo/`, medidas sobre `93bcd73`.

- **Eventos del mundo** (`cosim/escenario.py:41`, `:177-183`; aplicados en
  `cosim/agenda.py:129-154`): `atasco`, `corte_de_fase`, `caida_de_red`, `cable_cortado` (abre una
  rama: `red/nodal.py:109-118`) y `sensor_pegado` (`Sensor.forzar`, `cosim/modelos/mandos.py:205`).
- `RedNodal.cortocircuito(id, a, b, R)` existe (`red/nodal.py:120-130`, también en la de
  potencia, `red/potencia.py:169-170` y `:217`) y NINGÚN evento lo usa.
- No se puede simular: un contactor soldado, un contacto suelto pegado, un mando trabado, una
  protección que no dispara, una entrada o salida de PLC pegada, un canal del STO pegado.
- Los contactos se mueven por actuador (`«-K1.bobina»`, `«-S0.mano»`): la red los lee de
  `Tablero.estados()` (`cosim/tablero.py:218-241`) y los cierra en `RedNodal._cerrados`
  (`red/nodal.py:138-140`), que usan las dos redes (`red/potencia.py:214`).
- En vivo un evento entra sin hora (`cosim/vivo.py:71-74` → `leer_evento_vivo` →
  `Agenda.inyectar`, `agenda.py:42`) y queda en la grabación; en la UI sólo hay «Provocar
  atasco» (`ui/src/vivo/EventosVivos.tsx`, dentro de `PanelMandos.tsx:121`).
- El `inicio` del WS lista `dispositivos` [{designacion, tipo, ref, pieza?}]
  (`cosim/vivo_fotograma.py:102-104`), sin lo que cada uno puede sufrir.
- La señal `falla` ya existe y es del variador (`-T1.falla`, `cosim/modelos/variador.py:218`).
- La tool `set_scenario` documenta los eventos (`tools/cosim.py:110`; golden del MCP).
- El ancla «desde <evento> <arg>» de las aserciones ya casa el segundo token contra los datos
  del evento (`cosim/aserciones.py:129-134`).

## Lo que se revisó antes de escribir esto

- Que un contactor soldado deba arrastrar sus auxiliares: los contactos de un aparato siguen a
  su actuador (`«-K1.bobina»`); forzar el aparato los mueve a todos, que es el comportamiento de
  los contactos espejo (IEC 60947-4-1 Anexo F) que una realimentación necesita. Para UN contacto
  que falla solo (el NC de un canal) hace falta una falla de RED, no del aparato.
- Que un mando trabado y un contacto pegado son fallas distintas: la primera afecta a todos los
  contactos del mando a la vez; la segunda, a uno.
- `tests/test_cosim_epoch.py` y `tests/test_cosim_worker.py` (huella y determinismo bit a bit).

## Decisiones (para vetar)

- **D1 — Un modelo declara las fallas que sabe tomar.**
  - `Modelo.FALLAS: dict[str, str]` (nombre → qué valor pide, o `""`), como `ACCIONES`;
    `fallar(nombre, valor=None)` y `reparar(nombre)` en la base (`modelos/base.py`), con
    `_falla_<nombre>` por modelo.
  - Una falla que el modelo no declara es error accionable con la lista de las que sí.
  - Sin falla activa, el modelo da EXACTAMENTE las mismas salidas de hoy.
- **D2 — Las fallas de cada aparato** (lo razonable para su modelo, nada más):
  | modelo | fallas |
  |---|---|
  | contactor, relé | `soldado` (sigue cerrado sin bobina), `no_cierra` (inducido trabado o bobina abierta: no consume) |
  | seta, pulsador, selector, seccionador | `trabado` (la mano no mueve sus contactos; valor opcional: la posición en que queda) |
  | sensor | `pegado` (true/false; `sensor_pegado` queda como alias), `sin_salida` |
  | ITM, guardamotor, relé térmico, fusible | `no_dispara`, `abierto` (disparado o fundido solo) |
  | PLC (E/S) | `entrada_pegada` {borne, valor}, `salida_pegada` {borne, valor}, `detenido` (salidas a 0) |
  | variador | `canal_sto_pegado` {canal: S1 \| S2} (lee 24 V sin tenerlos), `falla_interna` |
  | fuente | `sin_salida` |
  | piloto | `fundido` |
  | red, motor | ninguna nueva: la red ya tiene fase perdida, caída y corte; el motor recibe las suyas por la red |
- **D3 — Fallas de la red, no de un aparato.**
  - `abierto` en una rama (= `cable_cortado`, que queda como alias).
  - `pegado` en UN contacto {rama, cerrado}: el contacto queda como se dice y el resto del
    aparato sigue a su actuador. Va como máscara en `RedNodal._cerrados` (la usan las dos redes)
    y entra a las firmas que deciden refactorizar (`RedNodal._firma`, `RedPotencia._firma_actual`,
    `Tablero._firma_potencia`): si no, la red no se re-resolvería.
  - `corto` {a, b, R_ohm?} entre dos puntos, también a PE, sobre el `cortocircuito` existente.
- **D4 — UN evento de escenario, `falla`.**
  - Formas: `{"t", "tipo": "falla", "dispositivo": "-K1", "falla": "soldado"}`,
    `{"tipo": "falla", "rama": "-K1:13-14", "falla": "pegado", "valor": true}` y
    `{"tipo": "falla", "falla": "corto", "a": "-X1:1", "b": "-X1:PE"}`; `valor` y `duracion_s`
    opcionales (con duración se repara sola).
  - Se valida al declarar (claves) y en `agenda.validar` (el dispositivo o la rama existen y
    admiten esa falla), con «¿quisiste decir…?».
  - Los eventos de hoy siguen y dan la misma huella.
- **D5 — La traza la registra y se puede anclar.** La agenda deja
  `{"evento": "falla", dispositivo | rama, falla}` en `eventos`; «desde falla -K1» y «falla.fin»
  sirven de ancla sin cambiar `aserciones.py`. Cada aparato con una falla activa publica
  `<des>.averia` (texto: las activas), que en vivo viaja en `textos`. No se llama `falla`: ese
  nombre es del variador.
- **D6 — En vivo, el mismo evento.**
  - `{"evento": {"tipo": "falla", …}}` por el WS, sin hora; `"quitar": true` la repara (en vivo no
    hay reverso sin duración).
  - El `inicio` gana `fallas`: [{designacion, tipo, fallas: [{falla, pide}]}] y `ramas`: los ids
    de contactos y conductores que se pueden pegar o cortar.
  - La grabación las incluye: la sesión vuelta escenario reproduce la falla.
- **D7 — «Simular falla» en la máquina viva.**
  - En el panel «Mandos», debajo de «Eventos»: elegir dispositivo (o rama), la falla y su valor
    si lo pide, y «Simular» (`ui/src/vivo/FallasVivas.tsx`).
  - En la barra de la sesión, una línea «Falla activa: contacto soldado en -K1» con «Quitar»;
    con varias, la cuenta y la lista al pedirla.
  - Los rótulos de cada falla viven en la UI (`vivo/fallas.ts`, tuteo, gates de texto); sin
    colores de estado (tokens del tema, `ui/CLAUDE.md` § Calidad visual).
  - `abrirSesion(escenario, {fallas})` abre la sesión con fallas ya puestas (las manda al llegar
    el `inicio`), para que otro panel ofrezca «Probar en vivo».
- **D8 — `COSIM_EPOCH` sube sólo si cambia la huella de un escenario sin fallas.** Un escenario
  viejo no tiene `falla` y su hash no cambia; si los de referencia (la 77 y los de los tests) dan
  la misma huella, sólo se actualiza la `HUELLA` de `test_cosim_epoch.py`, como en V8.4 F1. Si
  alguno cambia, sube a 5.
- **D9 — MCP: sin tool nueva.** El agente declara la falla en el escenario (`set_scenario`
  documenta `falla`; el golden cambia a propósito). `get_circuit` no cambia.
- **D10 — Límite.** Una falla es la que se pide, en la hora que se pide: no hay azar, tasas ni
  probabilidades (eso es otro análisis). Lo que el modelo de un aparato no tiene (p. ej. que un
  variador detecte la discrepancia entre sus dos canales) no se inventa: va como hipótesis del
  resultado.

## Alternativas descartadas

- **Forzar señales en vez de fallas de aparato** («-K1.cerrado = true»): la red no la vería
  (los contactos leen el actuador, no la señal) y no distingue un aparato trabado de un contacto
  pegado.
- **Un evento por cada falla** (`contactor_soldado`, `salida_pegada`…): multiplica las claves del
  escenario y del ancla; con uno solo, una falla nueva es una línea del modelo.
- **Fallas al azar** (inyección estadística): no es determinista y rompe la huella de las
  trazas.

## Fases

- **F0 — Medir** (sólo lectura): hecha, ver «Lo que hay hoy».
- **F1 — Fallas en el motor** (`cosim/` + `services/escenarios` + `tools/cosim.py` · M/L ·
  depende de F0): D1–D6, D8, D9. Tests: cada falla en su modelo (verde y rojo), contacto pegado
  en las dos redes, el evento en lote y en vivo con la misma huella, la grabación vuelta
  escenario, los escenarios sin fallas con la huella de antes.
- **F2 — «Simular falla» en la UI** (`ui/src/vivo/` · M · depende de F1): D7, con su preview y la
  revisión de diseño a ciegas (claro y oscuro, ancho y angosto).
- **F3 — Verifica** (S): sobre una COPIA de la 77, un escenario con la seta y un contacto pegado
  y otro con el contactor soldado; en la sesión viva, simular la falla, apretar la seta y ver el
  resultado. Mario lo juzga.

## Lo que este plan NO hace

- Calcular confiabilidad (tasas, MTTF, probabilidad de falla): sólo la prueba con la falla puesta.
- Fallas mecánicas nuevas (el atasco ya existe; un eje roto o una banda cortada, en otro plan).
- Aparatos nuevos del catálogo.

## Riesgos

| riesgo | mitigación |
|---|---|
| Tocar los modelos cambia resultados viejos | sin falla, salidas idénticas; huella de los escenarios de referencia antes y después (D8) |
| Un contacto pegado no re-resuelve la red | la máscara entra a las tres firmas (D3), con su test en mando y en potencia |
| La UI ofrece fallas que el modelo no toma | la lista sale del `inicio` (D6), no de la UI |

## Bitácora

### F1a (2026-10-23) — hecha, sin mergear

Backend (D1–D6, D8–D10) sobre `0a61be6`. Suite completa verde en el escritorio (4837 pasan,
10 saltan; `-m "not torture"`) y `ruff` limpio. Queda la revisión y el merge; después, F1b (UI).
- **D9**: el docstring de `set_scenario` documenta `falla` (formas, la lista por aparato,
  `quitar`, el ancla y `averia`); el golden cambia sólo en esa descripción
  (`list_tools.json`), revisado y re-congelado.

- **Fallas por modelo** (`Modelo.FALLAS`, `fallar`/`reparar`, `_falla_<n>`/`_reparar_<n>`; `pide`
  sale de `modelos/base.PIDE`, un vocabulario corto que la UI lee: `""`, `bool`, `bool?`,
  `posicion?`, `unidad?`, `borne,valor`, `canal`). Las de D2, todas; la red y el motor, ninguna.
- **Decisiones de F1a** (dentro del contrato, para vetar):
  - `trabado` = la mano acciona y el mecanismo no se mueve (la acción se acepta y no cambia
    nada; un pulsador trabado tampoco vuelve por resorte). El potenciómetro de una botonera no
    lo alcanza la traba.
  - `abierto` de una protección = dispara sola con causa «avería»; mientras dura no se rearma ni
    se repone y, reparada, queda disparada hasta que la rearmen (un disparo de verdad).
  - `falla_interna` del variador = falla «interna» que no se rearma mientras dura.
  - `detenido` del PLC: el planificador (`corrida._plc`) pasa el programa a STOP; reparado,
    arranque en caliente si el escenario está en RUN.
  - `no_cierra` y `fundido` sacan la bobina o la lámpara de la red (`abre_su_carga`: R_off en el
    mando por `cargas`, `R_ohm` en la potencia), así «no consume» vale también para la fuente.
  - `canal_sto_pegado` deja una hipótesis en el resultado: el modelo no detecta la discrepancia
    entre canales (D10).
  - `sensor_pegado` y `cable_cortado` siguen por su camino de siempre (sin `averia`): así sus
    escenarios dan la misma huella; `falla` con `pegado`/`abierto` hace lo mismo y además lo
    publica.
  - `quitar: true` también vale en lote: la grabación de una sesión lo trae y tiene que
    reproducirse.
  - El `inicio` publica `fallas` [{designacion, tipo, fallas: [{falla, pide, opciones?}]}] (con
    `opciones`: posiciones, bornes, canales, unidades) y `ramas` [{id, tipo, red, dispositivo?}].
    No publica puntos para el corto (D7 no lo ofrece en la UI).
  - `tipos.valores_iniciales` suma `<des>.averia = ""` para tipar las aserciones al declarar.
- **D8, `COSIM_EPOCH` sigue en 4**: 9 escenarios del banco (`cosim_lazo_banco`: marcha, seta,
  atasco, corte de fase, cable cortado, cajas, sensor pegado, caída de red, atasco parcial) dan
  la MISMA huella antes y después; sólo se actualizó la `HUELLA` de `test_cosim_epoch.py`. La 77
  no se midió aquí (el brief prohíbe tocar `data/`): va en F3, sobre su copia.
- Tests: `tests/test_cosim_fallas_modelos.py` (24: cada falla con su gemelo sano) y
  `tests/test_cosim_fallas.py` (32: lote y vivo con la faja del banco, contacto pegado en mando
  y en potencia, cortos en el mando y entre fases —dispara el magnético—, `quitar`, la grabación
  vuelta escenario con la misma huella, el rechazo en el snapshot con su pista, la avería tipada
  al declarar, la huella determinista).
- Para F1b: la UI lee del `inicio` `fallas` (con `pide` y `opciones`) y `ramas`; manda
  `{"evento": {"tipo": "falla", …}}` y `{…, "quitar": true}`; la falla activa llega como texto
  en `<des>.averia` por `textos` («» al quitarla). Sin conductores con largo, `ramas` trae sólo
  contactos (los hilos ideales no se cortan).

### F1b (2026-10-23) — hecha, sin mergear

UI (D7) sobre `34463e7`, sólo `ui/`. `npm test` 477 → 490 (13 nuevos en `vivo/fallas.test.ts`) y
`npm run build` verdes. Rama `wip/cosim-fallas-f1b`.
- `vivo/fallas.ts` (puro): rótulos y frases de cada falla de D2/D3 (una desconocida sale con su
  nombre legible), los campos por `pide`, el evento, las activas y su `quitar`.
  `vivo/FallasVivas.tsx` va en «Mandos» debajo de «Eventos»; `vivo/FallasActivas.tsx`, como primera
  línea de la barra. `abrirSesion(escenario, {reemplazar, fallas})` las manda al llegar el `inicio`.
- Muestrario: «Mandos · simular falla» y «Barra de la sesión viva · fallas activas» con un `inicio`
  de ejemplo (contactor, seta, pulsador, sensor, PLC con analógica, variador con STO, guardamotor,
  fuente, piloto, tres contactos y un cable); simular y quitar imitan al servidor
  (`?fallas=0|1|3`, `?lista=1`).
- **Decisiones de F1b** (para vetar):
  - Si la falla elegida (con el mismo borne, canal o unidad) ya está puesta, el botón pasa a
    «Quitar la falla»: no hay un segundo control para reparar en el panel.
  - Las fallas de RAMA no publican `averia` (son de la red): la UI las lleva por el ack de su
    evento (`conAckDeRama`, `useVivo.ramasEnFalla`). Se pierden si se recarga la página a mitad.
  - Un valor opcional (`bool?`, `posicion?`, `unidad?`) arranca en «Como está ahora» / «Todas» y
    no se manda; el sensor pegado arranca en «Detectando siempre»; el contacto pegado, «Cerrado».
  - Un borne `AI…` pide su cuenta (número) en vez del nivel: el catálogo no distingue analógicas,
    la UI lo deduce del nombre que da `plc_es` (`AI0`…).
  - «Reiniciar» y «Abrir de nuevo» reponen las fallas con que se ABRIÓ la sesión, no las puestas
    después a mano.
  - La barra con fallas toma ancho (`min(520px, 100% − 32 px)`); sin ellas sigue como estaba.
  - El aviso usa `<IconoSeveridad severidad="aviso">` (el ámbar del tema), sin colores nuevos.
- Pendiente:
  - Backend (hueco, no bloquea): el catálogo no publica la escala de la analógica (`AI_escala`) ni
    las ramas en falla (una sesión que se reabre en otra pestaña no las ve); el `inicio` tampoco
    trae las fallas ya puestas.
  - Sin test de `abrirSesion` con fallas (pide un WebSocket falso y `sesion.ts` arrastra la store
    de la app): se probó la lógica pura y el muestrario a mano.
  - Hoy sólo hay tema oscuro (A12 de V8.5): «claro y oscuro» de la revisión queda en oscuro.
  - La revisión de diseño a ciegas (ancho y angosto) y F3 sobre una copia de la 77.
- **Revisión a ciegas (2026-10-24, en la rama `wip/cable-visor`, bitácora F4b de
  [V8.5](V8.5-tablero-3d.md)):** «Simular falla» dejaba el estado al pie en gris («Esta falla ya está
  puesta.») → va junto al botón que la quita, con el ícono de aviso; en la barra angosta con varias
  fallas «Quitar todas» caía sola a la izquierda → las dos acciones van juntas a la derecha; las
  fallas de la lista empezaban en minúscula → mayúscula inicial por CSS (la de una sola sigue tras
  «Falla activa:»). Quedan, de toda la app: los botones de ícono de la barra, sus pestañas y el «×1,00».
