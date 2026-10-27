---
estado: implementado
nota: F0–F2 y F4 hechas (2026-10-27) y verificadas en el elevador vertical y la mezcladora reales; COSIM_EPOCH sigue en 9. Pendientes, con su fase propia si hace falta: el freno de motor como pieza mecánica (F3) y el rendimiento de la transmisión (F5)
descripcion: en la co-simulación un motor rotativo mueve una junta prismática (elevador por cadena o cable, cremallera, correa, husillo) por su transmisión declarada; la plataforma sube con su carga a v = ω·r y los sensores de nivel la ven de verdad
---

# El motor sube la plataforma en la co-simulación: transmisión rotativo → lineal

## Estado y origen

- Lo pidió la sesión orquestadora del 2026-10-27 por un problema REAL, medido esa noche: un
  modelador por MCP armó un elevador vertical de cajas (plataforma en la junta PRISMÁTICA
  `j_plataforma`, izada por dos cadenas 08B con piñones Z15 desde un eje motriz movido por un
  motorreductor sinfín NMRV-050 i = 40 por variador).
- `set_scenario(... acoples.motores["-M1"].junta = "j_plataforma")` y `simulate` →
  «'placa' (motor de inducción) es para juntas de giro». Su rodeo: el motor gira la junta del EJE
  (`j_eje_motriz`) con un `atasco` de 31,5 N·m que imita la carga, y los sensores de nivel van como
  eventos `sensor_pegado` a las horas que dio la cinemática. Los 9 escenarios prueban la LÓGICA,
  no el posicionamiento ni la sobrecarrera reales: la plataforma no se mueve.
- Vale para toda máquina con un eje lineal accionado por un motor rotativo. Plan fuera del
  roadmap (slug solo); toca `physics` (el actuador), `cosim` (escenario y acople) y `services`
  (la transmisión contra el documento).

## El problema / lo que hay hoy (F0, medido)

- `physics/dinamica_motores.py:resolver_motores`: `giro = j["type"] != "prismatica"` y con
  `placa` y `not giro` lanza el error. El `<velocity>` de una placa está siempre en el espacio de
  la junta (rad/s, N·m); en una prismática no hay radio que lleve ω a v.
- `services/cosim_snapshot.py:_motores` arma cada motor del tablero como `placa` (D8 de V8.3:
  «Motor = placa SIEMPRE»), así que la fuente ideal en mm/s tampoco es salida.
- `cosim/acople.py:AcopleMecanico.leer` devuelve (ω, T) = (qvel, qfrc_actuator) de la junta: en
  una prismática serían m/s y N.
- Los sensores por junta (`{junta, en_mm, ventana_mm}`, `services/cosim_aire.acoples`) ya aceptan
  cualquier prismática de la simulación: con la plataforma quieta no tenían qué ver.
- El elevador (su base de la noche, leída en sólo lectura, proyecto 1): `j_plataforma` prismática +Z
  (−11 a 1580 mm), `j_eje_motriz` continua en X; piñón `c33` = `PINON-08B-1-Z15` con
  `d0: 61.09` en `111_cadenas_pinones.yaml`; -M1 `NMRV-050` i = 40, η 0,65; -T2 `VFD-1K5-220`
  (rampas 1 / 0,8 s, lenta 15 Hz); sensores inductivos -B1…-B6 con pieza (la leva `c53` viaja con
  la plataforma); freno de resorte -Y1 modelado como relé (sin efecto mecánico).

## Lo que se revisó antes de escribir esto

- `cosim/CLAUDE.md`: «Motor = placa SIEMPRE» (sin `forcelimited` no se escribe el tope) y «el
  atasco es `dof_frictionloss`, no `qfrc_applied`». Lo que lleve el motor a la prismática no puede
  romper ninguna de las dos.
- `physics/CLAUDE.md`: `<velocity>` CON tope necesita J ≥ kv·Δt; la inercia del rotor reflejada
  manda. En una prismática eso es una MASA equivalente (J·i²/r²: en el banco, ~15 600 kg para un
  NMRV-090 i = 40 con piñón de 61 mm, mucho más que la plataforma).
- MuJoCo: un actuador con transmisión `joint` y `gear` g aplica g·fuerza a la junta y mide
  longitud/velocidad g·q. Con g = 1/r el actuador vive en el EJE: el Kloss de la placa, su tope y
  su consigna quedan como están.
- El bloqueo de vástago (`acople.SOLREF_BLOQUEO`) ya resolvió cómo retener una junta con fricción
  seca sin que la carga se arrastre: la restricción de fricción endurecida.

## Decisiones (para vetar)

- **D1 — La transmisión se declara en el acople del escenario**:
  `acoples.motores["-M1"] = {junta, direccion_transporte, transmision}`. Es dato de la prueba,
  como la junta que mueve (F5 de V8.3: los acoples siguen en el escenario), y no toca el log ni el
  `.apolo`. Una prismática con motor y SIN transmisión es 400 con la forma y los piñones del
  documento (antes, el error sin salida).
- **D2 — `gear` = 1/r en el actuador nativo, no una restricción de igualdad**. El `<velocity>` (y
  el `<motor>` del modo par) lleva `gear`: v = ω·r y F = T/r EXACTOS, en el mismo actuador que la
  placa ya usa (sigue el «Motor = placa SIEMPRE»: el tope `forcelimited` se escribe igual). La
  armadura del rotor y el mínimo de inercia pasan a la junta ×gear². El acople lee el `gear` del
  MODELO (`actuator_gear`, una sola fuente) y devuelve ω = gear·v y T = F/gear al motor.
- **D3 — El radio sale del modelo cuando se puede**: `{"pinon": "<pieza>"}` lee el `d0` de la
  ficha de su componente (`PINON-*`); si no, `{"diametro_primitivo_mm", "fuente"}` (tambor,
  polea) o `{"avance_mm", "fuente"}` (husillo, r = avance/2π). Un número declarado exige su
  `fuente`: nunca una cifra sin origen. La hipótesis del resultado dice r y de dónde salió.
- **D4 — La fricción en N·m sigue en el eje**: la del reductor sin tensión (F2 de V8.3) y la de un
  `atasco` (`par_Nm`) llegan a la prismática como F = T·gear (`AcopleMecanico.friccion_de`).
- **D5 — `irreversible: true` retiene la junta sin tensión** (sinfín autoblocante): mientras
  k = 0, fricción seca = el tope nominal del motor reflejado a la junta, con la restricción
  endurecida del bloqueo (2 ms; con la de MuJoCo la carga se arrastraba, medido en el bloqueo).
  Por defecto REVERSIBLE: sin par la gravedad baja la plataforma, lo conservador. Con tensión
  manda el `<velocity>` (en la bajada frena él, no el sinfín: hipótesis, la corriente puede diferir).
- **D6 — Transmisión rígida y sin pérdidas** (cadena ≈ 0,97). Va en la hipótesis; un husillo
  trapecial (η 0,3–0,5) pide la F5.
- **D7 — Sin subir `COSIM_EPOCH`**: la capacidad es nueva (antes la clave era 400) y sin ella
  gear = 1 (×1 y /1 exactos, el MJCF sin `gear` en el `<velocity>`). Medido: los 9 escenarios
  guardados del elevador dan la MISMA huella que su resultado guardado. Se actualizó la huella de
  `tests/test_cosim_epoch.py` y `services/cosim_transmision.py` entró a sus `ARCHIVOS`.

Decisiones de la F4 (para vetar):

- **D8 — `inicial` va en `mecanica.juntas.<junta>`**, junto a `friccion`/`amortiguamiento`/
  `armadura` (el modelador lo intentó ahí sin que nadie se lo dijera), en las unidades y el signo de
  `set_motion`: mm o grados medidos DESDE la pose de diseño. Lo acepta también la dinámica suelta
  (`simulate`, `juntas.<j>.inicial`): es la misma petición. El MJCF sigue horneado en la pose de
  diseño; la junta arranca con su qpos.
- **D9 — Validado al declarar**: la forma, en `cosim/escenario_mecanica.py` (que sale de
  `escenario.py`: tamaño); contra el documento (junta que exista con «¿quisiste decir?», que se
  mueva, dentro de [lower, upper]; una continua, cualquier ángulo), en `escenarios.poner` y en el
  snapshot con UNA regla, `physics.dinamica_peticion.posicion_inicial`. La forma de
  `mecanica.juntas` se revisa ahora al declarar (antes, al correr, con las mismas reglas).
- **D10 — El aire no declara presión de arranque**: cada cámara arranca a la presión de lo que su
  válvula EN REPOSO le une (la `HIPOTESIS_ARRANQUE` de V8.9, que no dependía de la posición) y con el
  volumen de la posición inicial (la x del vástago sale del qpos en el primer intercambio). Un
  cilindro en reposo contra su tope tiene la cámara que lo sostiene a la presión de la línea y la
  otra a la atmósfera: no hay equilibrio que inventar (el tope absorbe la fuerza neta). Una cámara
  bloqueada (centro cerrado) arranca a la atmósfera, como en la pose de diseño. Descartado: una
  `presion_inicial` por cámara en el escenario (una cifra sin fuente para el caso que ya resuelve
  la válvula).
- **D11 — Lo que depende de que la junta arranque en 0, revisado**: los sensores por junta y las
  fotoceldas ya leen el estado (nada que hacer); el visor (serie, GIF) y el vivo dibujaban
  T = P(t)·P(0)⁻¹ con P(0) = el fotograma 0, que ahora no es la malla: la salida suma
  `poses_diseno` SÓLO con `inicial` y los tres la usan; las carreras del aire
  (`services/aire_resultado`) medían el avance desde x = 0: un cilindro que arranca extendido mide
  su primer retroceso desde el 98 % de donde arrancó. Los productos siguen en coordenadas del
  MUNDO (la hipótesis lo recuerda): uno sobre la plataforma se declara donde está al arrancar.
- **D12 — Sin subir `COSIM_EPOCH`**: antes `inicial` era 400 (clave desconocida en la petición) y
  sin él el `Integrador` no hace nada nuevo. `services/cosim_inicial.py` entra a `ARCHIVOS`.

## Alternativas descartadas

- **Igualdad `equality/joint polycoef`** entre una junta de giro del motor (el eje motriz) y la
  prismática: es una restricción BLANDA (solref) entre dos cuerpos: bajo 1,2 kN de carga se
  estira y oscila, pide un cuerpo/junta de giro que el modelo quizá no tiene y deja dos lugares
  donde poner el motor. El `gear` es exacto y no agrega grados de libertad.
- **Llevar la fuerza del motor a la prismática en Python** (`qfrc_applied` = T/r): un par
  explícito retenido un intercambio vibra en ω = 0 (la razón del atasco por fricción) y saca el
  motor del `<velocity>` nativo que V8.0 midió estable.
- **Declarar la transmisión en el documento** (un comando o metadato): cambiaría la firma de todos
  los resultados y es dato de la prueba; si un día el modelo la deduce sola (de `create_chain`),
  entra como sugerencia en el 400 de D1.

## Fases

- **F0 (medir, hecha)**: cómo arma hoy el snapshot motor y junta (arriba) y la máquina real.
- **F1 (physics + cosim + services, M, hecha)**: `radio_transmision_mm` en la petición de la
  dinámica y `gear` del actuador (`dinamica_peticion`, `_control`, `_motores`, `_modelo`);
  `cosim/transmision.py` (lectura pura) y `services/cosim_transmision.py` (radio desde el piñón,
  400s, hipótesis); el acople con gear y la retención irreversible; `atasco` en N·m del eje; el
  docstring de `set_scenario` (golden re-congelado).
- **F2 (tests, hecha)**: `tests/elevador_escena.py` (elevador mínimo) y
  `tests/test_motor_eje_lineal.py`: sube a ω·r con T = m·g·r, el sensor por junta la para, sin par
  la gravedad la baja y el sinfín la retiene, el piñón sale del modelo, 400s, y sin transmisión el
  MJCF y el acople de siempre.
- **F3 (pendiente)**: el freno de motor de resorte como efecto mecánico (fricción en la junta
  mientras su bobina no lo libera), ligado a la bobina del tablero (-Y1 del elevador es un relé).
- **F4 (physics + cosim + services, S/M, hecha)**: la posición inicial de una junta en el
  escenario (`mecanica.juntas.<j>.inicial`, D8–D12): `posicion_inicial` y el qpos del `Integrador`,
  `poses_diseno` en la salida (serie, GIF, vivo), `cosim/escenario_mecanica.py`,
  `services/cosim_inicial.py` (al declarar y en el snapshot, con su hipótesis), las carreras del
  aire desde arriba, los docstrings de `set_scenario` y `simulate` (golden re-congelado) y
  `tests/test_junta_inicial.py`.
- **F5 (pendiente)**: rendimiento de la transmisión (husillo trapecial) en el tope y la corriente.

## Lo que este plan NO hace

- No convierte los 9 escenarios del elevador: siguen con su rodeo (y vigentes). Rehacerlos con la
  transmisión es trabajo del modelador (bitácora: la receta medida).
- No publica una señal de posición de la junta para las aserciones: la posición se afirma con los
  sensores por junta («-B2.activo dentro_de 16 s desde pulsar -S11»).
- No mueve el eje motriz ni los piñones en el visor (su junta queda libre).

## Riesgos

- **La masa equivalente del rotor domina** (J·i²/r²): un `timestep` grande con un tope chico
  podría oscilar → el mínimo de inercia ×gear² lo cubre y avisa como en una de giro.
- **Retener con fricción seca** puede arrastrarse → la restricción endurecida del bloqueo; medido:
  < 0,001 mm en 3 s con 141 kg y en el elevador.
- **Un log viejo cambia de resultado** → gear 1 exacto y la huella de los 9 escenarios guardados.

## Bitácora

**F0–F2 (2026-10-27).** Base `92704e7`.

- Banco mínimo (plataforma de 141 kg, NMRV-090 i = 40, d0 61,09, VFD-2K2 rampas 1/0,8 s): sube a
  143,2 mm/s en régimen = ω·r con el ω del eje de salida (±0,5 %), T de salida = m·g·r (±2 %);
  -B1 (en 500 ± 10 mm) la ve a 4,25 s, el PLC corta en el mismo scan y la rampa la deja en
  550,7 mm. Reversible y sin marcha, cae (a ≈ 53 mm/s²: la masa reflejada del rotor, ~15 600 kg,
  frena la caída); irreversible, quieta (< 0,5 mm). En la primera prueba la subida tardaba 7 s en
  llegar a 95 mm/s: era la rampa de 10 s del variador por defecto, no la física.
- **Vigencia**: los 9 escenarios guardados del elevador (sin transmisión, con `atasco` en el eje)
  corridos con el código nuevo dan la MISMA huella que el resultado guardado de cada uno (9 de 9).
- **Elevador real** (copia en memoria del proyecto 1, por `extensiones_api.preparar_corrida` /
  `correr_corrida`): `subir_50kg` con `-M1 → j_plataforma`, `transmision {pinon: "c33",
  irreversible: true}`, sin el `atasco` del rodeo, una carga de 50 kg sobre el piso y los seis
  inductivos como sensores por junta (centro del sensor − centro de la leva c53, ventana ± 20 mm:
  -B1 −6,5, -B5 73,5, -B6 1413,5, -B2 1493,5, -B3 1573,5, -B4 −56,5). Hipótesis: «r = 30,545 mm
  (piñón c33 PINON-08B-1-Z15, d0 = 61,09 mm de su ficha)». Subir a 1,58 s; régimen 140,2 mm/s
  (motor 1753 rpm, par de salida 35,8 N·m = 119,5 kg × g × r: la plataforma pesa ~70 kg, no los
  55 que suponía el atasco de 31,5 N·m); -B6 (lenta) a 12,05 s, -B2 a 13,45 s: 1473 mm en 11,9 s
  desde la orden; para en 1477,4 mm y queda ahí (la carga sigue encima, -B3 nunca). Ida y vuelta
  (-S21 a 18 s): baja, -B5 lenta a 27,9 s, -B1 a 29,0 s, para en 8,2 mm y desbloquea la puerta 0.

**F4 (2026-10-27).** Base `7c38fb6`. Las dos máquinas, leídas en SÓLO LECTURA (copias en memoria
del proyecto 1 de cada `apolo.db`; nada se escribió).

- **Mezcladora** (`mezcladora-paletas-200l`, compuerta en `c68_vastago` 0–200 mm, dibujada ABIERTA
  en x = 0; la válvula en reposo la cierra): sus 7 escenarios con `inicial: 200` (cerrada), pasados
  por `escenarios.poner` y corridos: los 7 PASAN. El arranque ya no golpea: x(0) = 200,0 mm,
  pA = la línea, pB = 0 bar, |v| ≤ 0,002 m/s en los que no descargan. `ciclo_nominal` mide avance
  0,430 s y retroceso 0,506 s (la cota a mano: 0,464 / 0,540 s) y pico 0,562 m/s
  (`desacoplar_en_descarga`, 0,561). La memoria del aire con esos resultados: **energía al fin de
  carrera 20,61 J (4,29 kg a 3,10 m/s, ERROR) → 0,68 J (a 0,562 m/s, OK; admite 2,3 J)**; caudal
  pico de -QM1 1049 → 190 NL/min (aviso → OK) y el de -AZ1, igual. Los 21 J eran el artefacto del
  arranque abierto con la cámara B a la atmósfera.
- **Elevador** (`elevador-vertical-cajas-2n`): `bajar_desde_n1` = el `bajar` guardado sin el rodeo
  (sin `atasco` ni `sensor_pegado`), con `-M1 → j_plataforma` y `transmision {pinon: "c33",
  irreversible: true}`, los seis inductivos por junta (los centros de la F2, ± 20 mm), la carga de
  50 kg sobre el piso c26 a la cota de arranque y `inicial: 1477.4` (donde paró la subida medida en la
  F2, dentro de -B2). PASA sus 7 aserciones: -B2 activo a t = 0, rearme y -S11 → `bajar` a 1,58 s,
  -B6 a 2,35 s, -B5 (lenta) a 11,45 s, -B1 a 12,58 s; para en 8,1 mm (13,6 s: `desbloq0`; `desbloq1`
  nunca tras la orden), bajada a 147,7 mm/s, la carga termina apoyada (z = 278,1 mm). Trampa medida:
  con la carga declarada sobre la placa de respaldo (2,3 m) chocaba con la estructura de arriba y
  empujaba la plataforma 50 mm al arrancar; los productos van donde está la pieza AL ARRANCAR.
- **Banco** (`tests/test_junta_inicial.py`): desde 700 mm reversible baja y -B1 la ve a 510 ± 8 mm;
  irreversible queda (< 0,5 mm); el brazo giratorio arranca a 45° y la serie parte girada 45°; una
  continua acepta 400°; `inicial: 0` da la misma corrida muestra a muestra. El empujador con la
  válvula que lo saca en reposo: dibujado retraído sale a > 3 m/s (6,18 medido); arrancando a
  200 mm, |v| < 0,01 m/s y pA = 6 bar, pB = 0.
- **Vigencia**: con el código nuevo, los 7 escenarios guardados de la mezcladora y los 10 del
  elevador, SIN cambios, dan la MISMA huella que su resultado guardado (17 de 17).
