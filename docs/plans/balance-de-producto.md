---
estado: en curso
nota: F1–F3 mergeadas (2026-10-26) y las trabas T1–T3 de la primera corrida real también (tope de duración coherente en 300 s, la caja retirada conserva su posición, el ritmo declarado tal cual; COSIM_EPOCH 8); F4 hecha fuera del árbol: la faja con desviador declara 15 cajas/min y su escenario de flujo cuadra (12 de 12 a la rampa, margen ≈ 0,05 s por ciclo); D9 (faja sin tablero = NO_APLICA) aceptada por Mario el 2026-10-26: se venden también diseños sólo mecánicos y el tablero lo pone el cliente
descripcion: un escenario de la co-simulación cuenta el producto que entra y el que sale por cada salida, avisa del que se traba o se cae, y la puerta exige ese balance al ritmo nominal en toda máquina que mueve producto
---

# Lo que entra a la máquina sale por donde tiene que salir, al ritmo de diseño

## Estado y origen

- Mario abrió en la máquina viva una faja con un desviador neumático: las cajas en serie llegan
  más rápido que el ciclo del empujador, la placa no termina de volver y una caja se traba contra
  ella (2026-10-26).
- Todos los escenarios de esa máquina pasaban: probaban UNA caja suelta. Ninguna prueba compara
  lo que entra con lo que sale, ni lo hace al ritmo de diseño.
- Mario delegó el criterio («procede según tu criterio»): lo vetable va como D numerada.

## Lo que hay hoy

Rutas relativas a `core/apolo/`, medidas sobre `b9d774f`.

- **Alimentación en serie**: `cada_s`, `cantidad`, `desde_s` de un producto
  (`physics/dinamica_peticion.py:217-242`, instancias en `:328-333`). La cola nace sólo con su
  lugar libre (`physics/dinamica_nacimiento.py`); la que no entra queda en
  `resumen.productos_sin_nacer`.
- **Sumideros**: planos `{punto_mm, normal}` sin nombre (`dinamica_peticion.py:260-267`,
  `cosim/escenario.py:360-377`). `Integrador._retirar` (`physics/dinamica_integrador.py:223-238`)
  saca del mundo el producto cuyo centro pasa CUALQUIERA, sin anotar cuál; la salida sólo dice
  `retirado_s` y `productos_retirados`.
- **Caída**: `salida_dinamica` marca `cayo` sólo con la posición FINAL (`:291-292`): una caja
  que cayó y siguió rodando, o que cayó sobre otra pieza, no se ve. Una caja quieta contra un
  obstáculo no se ve nunca.
- **Aserciones** (`cosim/aserciones.py`, `cosim/veredicto.py`): señal, comparación, valor y
  ventana sobre las trazas del tablero y el PLC. Ninguna señal habla del producto.
- **Ritmo de diseño**: `requirements.paquetes_por_minuto` YA existe (`library/requisitos.py:23-27`)
  y la marcha de ejemplo del video lo usa como ritmo de alimentación
  (`services/marcha_ejemplo.py:240-241`). Ningún escenario lo lee.
- **Puertas**: la de entrega (`library/delivery.py:307-315`) y la de publicación
  (`library/calidad/registro.py`, `funcion.escenarios`) sólo miran si los escenarios pasan.

## Lo que se revisó antes de escribir esto

- La co-simulación exige tablero (`services/cosim_snapshot.py:174-176`): una faja sin tablero no
  puede tener escenarios. Eso decide D9.
- El testigo público `faja` (sin tablero) aprueba entero y la suite exige que siga aprobando
  (`tests/test_testigos.py:39-46`).
- `tipos.revisar` y `_avisos_tablero` sólo miran designaciones con «-»/«=»: una señal
  `flujo.x` no choca con el tablero.
- La huella de la corrida (`cosim/trazas.huella`) se calcula con trazas, eventos y finales del
  tablero: lo que se agregue en `mecanica` no la toca.

## Decisiones (para vetar)

- **D1. El balance son SEÑALES del escenario, en el lenguaje de aserciones de siempre.** Con el
  bloque `flujo`, la corrida publica señales discretas `flujo.<x>` (cambios `[[t, v], …]`) que el
  veredicto lee como cualquier otra: `flujo.entraron`, `flujo.salieron`, `flujo.<sumidero>`,
  `flujo.perdidos`, `flujo.trabados`, `flujo.retenidos`, `flujo.sin_entrar`, `flujo.en_maquina`,
  `flujo.transito_max_s` y `flujo.cuadra` (booleana: el balance). Se escribe
  «flujo.cuadra al_final», «flujo.rampa == 6 al_final», «flujo.trabados > 0 nunca»,
  «flujo.transito_max_s <= 8 al_final». Sin ventanas ni anclas nuevas: todo lo de F6 (margen,
  «y se mantiene») vale igual. Una señal `flujo.*` que no existe (o un escenario sin `flujo`) es
  400 al declarar, con «¿quisiste decir…?».
- **D2. El bloque `flujo` del escenario**: `plazo_s` (obligatorio: el tránsito máximo de un
  producto), `quieto_s` (2 s por defecto, criterio de diseño), `zonas_espera`
  (`[{nombre, min_mm, max_mm}]`: donde un producto puede esperar quieto, p. ej. la acumulación
  ante el empujador) y `ritmo_por_min` (D7). Pide al menos un sumidero. **Sin el bloque, nada
  cambia**: no corre el rastreo, no hay señales y la salida y la huella son las de siempre.
- **D3. Un sumidero tiene `nombre`** (opcional; sin él, `sumidero_<k>`): sin espacios ni
  puntos (es parte de la señal: «fin_de_faja»), único y distinto de las señales fijas. Un
  sumidero es una SALIDA: lo que lo cruza cuenta como salido, nunca como perdido. Si el centro
  pasa dos planos a la vez, cuenta el primero de la lista (el orden de `_retirar` de siempre).
- **D4. Definiciones** (las del rastreo, todas con el estado simulado):
  - *entró*: nació en el mundo (a su hora o tarde, si la cola esperó);
  - *salió*: su centro pasó un sumidero;
  - *perdido*: su centro bajó a menos de (lado mayor / 2 + 20 mm) del piso (z = 0, el plano
    «piso» del MJCF), habiendo nacido más alto; es la caída a la planta;
  - *trabado*: su centro no se alejó más de 5 mm de un punto durante `quieto_s`, fuera de una
    zona de espera; se anota una vez, con el producto, el lugar (mm) y la hora (desde cuándo y
    cuándo se declaró);
  - *retenido*: no salió dentro de `plazo_s` desde que entró (sigue adentro o salió tarde);
  - *en tránsito*: entró a menos de `plazo_s` del final y sigue adentro: no es falla;
  - *sin entrar*: le tocó entrar y la cola no lo dejó hasta el final (`productos_sin_nacer`);
  - **cuadra** = entró al menos uno, sin perdidos, trabados, retenidos ni sin entrar.
  Lo que cae sobre otra pieza (no al piso) y se queda quieto sale como trabado: también es falla.
- **D5. El rastreo vive en el `Integrador`** (`physics/dinamica_flujo.py`, sin OCCT, en el
  worker), cada intercambio y vectorizado. No en la API sobre los fotogramas: van a 10 fps, el
  vivo no los guarda y «quieto» dependería del fps. Vale para el lote, el vivo y `simulate`.
- **D6. El ritmo nominal es `requirements.paquetes_por_minuto`** (la «capacidad nominal en
  productos por minuto»): ya existe y la marcha de ejemplo lo usa como ritmo. Una clave nueva
  (`capacidad_por_min`) serían dos fuentes que divergen.
- **D7. `flujo.ritmo_por_min` alimenta al ritmo**: periodo T = 60 / ritmo; con n series de
  productos, cada una entra cada n·T, desfasadas T (alternan). Con él, `cada_s` en un producto es
  error (dos ritmos). `"nominal"` se resuelve AL DECLARAR (`set_scenario` guarda el número; una
  corrida inline lo resuelve al tomar el snapshot): el número queda en el escenario (su hash lo
  cubre) y la puerta lo compara con la capacidad de HOY; subir la capacidad deja ese escenario
  por debajo (SIN_EVALUAR). Nunca un puente implícito requisito → corrida. El ritmo de un
  escenario es siempre Σ 60/`cada_s` de sus series (con o sin `ritmo_por_min`). La
  «separación mínima» es ese periodo: entran tan juntos como el ritmo pide; la separación física
  (v·T − largo) es su consecuencia.
- **D8. El margen es un DATO.** Un escenario de flujo a más del ritmo nominal y SIN la aserción
  `flujo.cuadra` es de margen: su balance sale en el resultado y en la evidencia de la puerta
  («a 36/min, +20 %: 9 entraron · 1 trabado»), nunca en el veredicto. Con la aserción, juzga
  como cualquiera (y cubre el nominal si pasa).
- **D9. La puerta de publicación suma `funcion.flujo_de_producto`** (familia función). Aplica si
  la máquina MUEVE PRODUCTO y se puede co-simular: productos en algún escenario, o bandas +
  tablero. Sin tablero es NO_APLICA con el porqué (la prueba de flujo es una co-simulación;
  igual que `riesgos.electrico`). Estados: sin `paquetes_por_minuto` → SIN_EVALUAR
  (`set_requirements`); sin escenario de flujo a ritmo ≥ nominal (−1 %) con `flujo.cuadra` →
  SIN_EVALUAR con la acción; sólo sin correr o vencidos → SIN_EVALUAR; uno vigente que no cuadra
  → FALLA con producto, lugar y hora; si no, OK. `VERSION_REGISTRO` 5 → 6.
  *Alternativa vetable*: también SIN_EVALUAR sin tablero; el testigo `faja` (y toda faja sin
  tablero) dejaría de aprobar y la acción («declara el tablero») no es del flujo.
- **D10. La puerta de entrega** lo suma SÓLO con escenarios declarados (V8.3 D14: sin ellos, lo
  de siempre) y si la máquina mueve producto: falta el escenario o la capacidad → aviso
  (AMARILLO), balance vigente roto → bloqueante (ROJO). `VERSION_BATERIA` 1 → 2.
- **D11. Respuesta.** El compacto de la corrida y el resultado guardado llevan `flujo` (el
  balance sin señales; listas recortadas a 10 con su total) y su texto `balance`
  («10 entraron · 6 rampa · 4 fin · 0 trabados»); `get_scenarios` lo muestra por escenario. La
  UI no tiene vista de resultados de escenarios (sólo el selector del vivo): no se crea una aquí.
- **D12. Vigencia.** `COSIM_EPOCH` NO sube: sin `flujo` el rastreo no corre y nada del
  resultado cambia (ni trazas ni veredicto); un escenario con `flujo` era 400 antes (clave
  desconocida), así que ningún resultado guardado describe otra cosa. Se actualiza la huella de
  `tests/test_cosim_epoch.py` y `physics/dinamica_flujo.py` entra a sus `ARCHIVOS`.
- **D13. El detalle de una aserción `flujo.*` que falla nombra las incidencias**: producto,
  lugar y hora del trabado, del perdido, del retenido y del que no entró.

## Alternativas descartadas

- **Contar en la API desde los fotogramas**: 10 fps, sin fotogramas en el vivo; el «quieto»
  dependería del fps.
- **Un lenguaje nuevo («balance cuadra»)**: el de señales ya da ventanas, anclas y tipos; un
  segundo lenguaje es otra cosa que mantener.
- **Inyectar el ritmo desde los requisitos al correr**: el resultado dependería de un metadato
  que su vigencia no mira (subir la capacidad no lo vencería). Se guarda el número.
- **Sumideros acotados (cajas) además de planos**: hoy alcanza con planos con nombre; entra
  cuando una máquina lo pida.
- **Perdido por la caja de la máquina**: el piso es inequívoco; lo que cae sobre otra pieza ya
  sale trabado.
- **`demorados` como falla**: una caja que entra unos ms tarde no es un atasco; el que no entra
  nunca (`sin_entrar`) sí. La demora sale como dato.

## Fases

- **F0** (lectura, hecha): lo de «Lo que hay hoy».
- **F1** (`cosim`, `physics`; M): sumideros con nombre, bloque `flujo` y ritmo (`cosim/flujo.py`),
  rastreo en el `Integrador` (`physics/dinamica_flujo.py`), señales en el `Lector` y el detalle
  del veredicto. Verifica: tests de lectura, de la dinámica (verde con dos sumideros, trabado,
  perdido, determinismo) y del veredicto.
- **F2** (`services`, `library/calidad`, `library/delivery`, `api`; M): el balance en el
  compacto, el resultado guardado y `get_scenarios`; `"nominal"` al declarar; las reglas de las
  dos puertas. Verifica: tests de la regla (sin escenario → SIN_EVALUAR, roto → FALLA/ROJO) y una
  corrida de punta a punta por la API.
- **F3**: suite completa, ruff, bitácora.
- **F4** (fuera de esta rama): la faja del desviador (escenario `desvio_en_serie`) declara su
  `flujo` con los sumideros «rampa» y «fin» y la aserción de balance; ver Bitácora.

## Lo que este plan NO hace

- No crea una vista de resultados de escenarios en la UI.
- No mide la separación física entre productos ni el rendimiento (productos/min que SALEN) como
  señal; `flujo.salieron` en una ventana lo da.
- No resuelve el desviador: lo hace visible.

## Riesgos

- **Falsos trabados de una caja que espera a propósito** (ante un tope, en una acumulación):
  `zonas_espera`; `quieto_s` se ajusta por escenario.
- **Falsos perdidos de un producto que nace en el piso**: sólo cuenta el que nació más alto que
  su lado mayor / 2 + 60 mm.
- **Costo del rastreo**: vectorizado sobre ≤ 200 productos; sólo con `flujo`.

## Bitácora

### F1 (cosim, physics) — 2026-10-26

- `cosim/flujo.py` (lectura del bloque, señales, texto del balance, incidencias),
  `physics/dinamica_flujo.py` (el rastreo) y sus ganchos en el `Integrador`: `nacio` en
  `_nacer` (y las que nacen en t = 0), `retirado` en `_retirar` (que ahora anota CUÁL sumidero:
  el primero de la lista, como el `any` de antes) y `medir` tras retirar, cada intercambio.
- **Primer intento, revelador**: el test verde con la entrada en x = −1300 dio 1 entró y 6 «sin
  entrar»: la guarda de cola (`e_c1_guarda_c`) ocupa ese lugar y la caja tardaba 11,9 s en
  despejarlo. El balance lo dijo solo (`sin_entrar` con la hora que les tocaba, el aviso de la
  cola con quién ocupa). Con la entrada en x = −1000: 7 entraron · 3 rampa · 2 fin · 0 trabados,
  2 en tránsito, tránsito máximo 4,85 s (2,4 m a 0,5 m/s).
- Obstáculo a 20 mm sobre la banda: la caja queda trabada a x ≈ 500 mm (cara del travesaño en
  570, la caja de 150 mm) y el balance da producto, lugar y hora; una caja nacida al costado cae al
  piso en < 1 s: perdida, no trabada.
- Vigencia (D12): la huella de 3 escenarios del banco (seta con cajas por variador, cajas con
  sumidero por variador y en directo) y su salida `mecanica` entera son IGUALES a las de
  `b9d774f` (corrido con el `core/` de la base exportado con `git archive`). `COSIM_EPOCH` sigue
  en 6; la huella de `tests/test_cosim_epoch.py` se actualizó con su porqué.

### F2 (services, library, api) — 2026-10-26

- `services/flujo_producto.py`: ritmo nominal, «nominal» → número (al declarar y en el
  snapshot), `mueve_producto`, `evaluar` (la regla) y `regla_entrega`. El compacto, el
  resultado guardado y `GET /api/escenarios` llevan el balance; las dos puertas, su regla.
- Testigos públicos re-congelados a propósito (`scripts/testigos.py --en-proceso --congelar`):
  `version_registro` 6 y `funcion.flujo_de_producto` NO_APLICA en los cuatro (ninguno tiene
  tablero ni productos en escenarios); la faja sigue aprobando entera.
- Defecto sembrado `balance_que_no_cuadra` sobre la faja: FALLA con el producto trabado.

### F3 (verificación) — 2026-10-26

- Suite completa del núcleo (`-n auto`, en esta máquina, con el `.venv` de pruebas): en `b9d774f`
  6212 pasan, 10 saltados, 0 fallan, exit 0; en la rama, 6247 pasan, 10 saltados, 0 fallan,
  exit 0 (+35: los tres `test_flujo_*` y el defecto sembrado). `ruff check core tests scripts`
  limpio. Sin cambios en `ui/` (no hay vista de resultados de escenarios: D11).
- Golden del MCP re-congelado: sólo cambia el docstring de `set_scenario` (documenta `flujo`).

### Trabas de flujo (fix acotado) — 2026-10-26

Tres trabas medidas al correr un escenario de flujo a 15 cajas/min. Decisiones:

- **T1. El tope de la corrida es el del escenario (300 s), en los dos lados.** `set_scenario`
  aceptaba hasta 300 s (`cosim/escenario.py`) y la dinámica cortaba en 60
  (`physics/dinamica_peticion.py`): un escenario de 100 s se guardaba y después era 400 al
  correr. A 15/min, 20 cajas no caben en 60 s. Medido con `time.process_time` sobre la faja del
  banco (`cosim_lazo_banco`, flujo a 15/min con sumidero, corrida en proceso):

  | banco | 60 s | 120 s | 180 s | 300 s |
  |---|---|---|---|---|
  | directo, CPU | 14,2 s | 28,7 s | 45,6 s | 83,2 s |
  | variador + PLC, CPU | — | 34,9 s | 54,8 s | — |
  | JSON del resultado (directo) | 2,4 MB | 6,4 MB | 12,1 MB | 28,2 MB (56 MB en memoria) |

  Lineal en CPU (0,24–0,31 s por segundo simulado). El tope de 60 s protege la dinámica SUELTA
  (`simulate` sin escenario): corre en el proceso de la API con `PHYSICS_LOCK` tomado (riesgo de
  V8.2) y su serie del visor crece con productos × duración. La co-simulación corre en su
  proceso (límite 1800 s), sin ese lock, como job con recibo. Por eso: los 60 s se quedan para
  `simulate` suelto, con la razón escrita; el snapshot de la co-simulación pasa el tope del
  escenario (`parse_peticion(…, duracion_max_s=)`, también a `cosim_bandas.prever`, que con un
  escenario de más de 60 s se callaba y la banda quieta no se rechazaba temprano). El JSON crece
  con cajas × duración (28 MB a 300 s y 75 cajas; la API guarda 8 corridas): se acepta, no hay
  un tope menor que lo justifique. La sesión en vivo vuelta escenario usa el mismo tope
  (`sesion_viva.duracion_lote_max_s`).
- **T2. El producto retirado conserva la posición en que salió.** `<producto>.x_mm/y_mm/z_mm` se
  dejaba de publicar al retirarlo y «caja_3.x_mm >= 3500 al_final» fallaba con la señal sin
  valor. Se eligió conservar la posición del retiro, no rechazar la aserción: es la misma
  `posicion_final_mm` que la dinámica ya daba (con `retirado_s`), así las dos salidas dicen lo
  mismo, y la aserción responde lo que pregunta (si la caja llegó). Rechazarla al declarar no se
  puede bien (no se sabe de antemano qué caja saldrá) y cambiaría la pregunta del agente por
  otra (`flujo.<sumidero>` cuenta, no nombra la caja).
- **T3. El ritmo que se muestra es el declarado.** `ritmo_por_min` salía de Σ 60/`cada_s` con
  `cada_s` redondeado a 6 decimales (18 → 18,000002). Con `ritmo_por_min` declarado, el bloque
  normalizado guarda ese número; sin él, Σ 60/`cada_s` se redondea a la milésima. La
  comparación con el nominal tiene ±1 %: ningún veredicto cambia.
- **Vigencia**: `COSIM_EPOCH` 7 → 8 por T2. Contra `c826389` (el `core/` de la base exportado):
  sin sumidero (cajas por variador, marcha en directo) la MISMA huella, finales y eventos; con
  sumidero (cajas por variador y en directo) cambian sólo la huella y los finales `*_mm` de las
  cajas que salieron. T1 y T3 no cambian ningún resultado guardado (un escenario de más de 60 s
  era 400; el ritmo no entra al snapshot).
- Verificación: suite completa del núcleo (`-n 4`, el `.venv` de pruebas) 6280 pasan, 10
  saltados, 0 fallan, exit 0; `ruff check core tests scripts` limpio. Golden del MCP re-congelado:
  sólo cambian los docstrings de `simulate` y de la tool que vuelve escenario una sesión viva (el
  tope de duración).

