---
estado: implementado
nota: F0–F2 hechas (2026-10-27) y verificadas en el elevador vertical real; COSIM_EPOCH sigue en 9. Fuera, con su fase propia si hace falta: el freno de motor como pieza mecánica (F3), la posición inicial de una junta en el escenario (F4) y el rendimiento de la transmisión (F5)
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
- **F4 (pendiente)**: la posición inicial de una junta en el escenario (`mecanica.juntas.q0`):
  hoy la plataforma arranca en la pose de diseño, así que «bajar desde el nivel 1» se prueba sólo
  como ida y vuelta.
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
