---
estado: en curso
nota: F1 (D1–D7) hecha y verificada con su suite, sin mergear (COSIM_EPOCH 9: los escenarios guardados quedan vencidos al mergear); quedan F2 (D8, velocidad de llegada del vástago), F3 (D9, sensores por designación) y F4 (D10, casco de un sólido cóncavo), cada una con su F0 de medida
descripcion: el agente que modela por MCP tropieza menos: avisos y errores que dicen la llamada que arregla, uniones que se encuentran por su comando, aserciones acotadas «hasta» un instante y respuestas cortas al cambiar una variable
---

# El agente modela sin tropezar con las tools

## Estado y origen

- Los modeladores por MCP que corrigieron la faja con desviador neumático
  ([V8.9](V8.9-neumatica.md) F7, correcciones 2 a 4) anotaron diez trabas, cada una con la
  llamada que la reproduce ([backlog](../backlog.md) § «Tools del agente al modelar», medidas el
  2026-10-26). Ninguna bloqueó: se esquivaron, y cada esquive es una vuelta más de contexto. El
  encargo: que el agente tropiece menos, porque eso abarata cada máquina.
- Este plan junta las diez. D1–D7 entran en una fase (F1); D8–D10 son más grandes y quedan como
  contrato de fases futuras.

## Lo que hay hoy (medido)

Cada traba con su reproducción, leída del transcript del modelador y repetida sobre el código.

| # | Llamada | Lo que pasa | Causa |
|---|---|---|---|
| 1 | `resolve_expression("tan(pend_rod*pi/180)")` | 0,0009 en vez de 0,052 | `sin/cos/tan` toman GRADOS (`commands/expressions.py:38`); la gramática lo dice en una `note` larga que el agente no leyó |
| 2 | `join_bolted` del pie MS1 a la bancada, después `get_connections(ids=["c1959"])` | `[]`; `simulate` deja «FUERA» los 2 pernos y 2 tuercas | el fijador `jb_c1959` existe (a = pie, b = bancada), pero `filtrar` sólo mira `a`/`b` y el token `c1959` resuelve a la TORNILLERÍA del comando; `clasificar` no sabe que esa tornillería cuelga de la unión (`gravity_test` sí: `sujetas`, F7b). Pasa con todo `join_bolted`, no sólo con agujeros de fábrica |
| 3a | `fasten(size="M5")` | el comando lo acepta (repetido: M3, M4, M5 y M6 dan ok); no hay 400 en los transcripts | el schema dice «M6–M24» y la tabla ISO 898-1 (`engineering/bolts.py`) empieza en M6: `engineering_check` da «métrica fuera de tabla». El agente lo esquivó escribiendo «M5x16 DIN 912» en la nota |
| 3b | un lote con `fasten(nota=<150 caracteres>)` | 400 «nota: String should have at most 120 characters» | `max_length=120` sin consumidor que lo pida: la BOM BUSCA en la nota (`tornilleria_declarada._lo_declarado`), no la imprime |
| 4 | aserción «caja_1.x_mm > 2495 nunca desde pulsar -S1 + 6 s y antes» | 400 «el ancla … es «<acción> <dispositivo>»» | `siempre`/`nunca` sólo tienen «desde»; la ventana termina al final de la corrida |
| 5 | `set_variable(name="paso_rod", expression="66")` | ~6 kB por llamada | `_scene_brief` manda TODAS las variables cuando la operación tocó un `set_variable` |
| 6 | `edit_command("c1756", {"component": "VAL-52-MONO-G14"})` | 400 «… es el componente VAL-52-MONO-G14, no VAL-52-MONO-G18: liga el dispositivo a la pieza que lo representa» | el `add_device` que liga esa pieza sigue con la ref vieja; el error no dice qué comando ni qué campo |
| 7 | `edit_command("c1714", {"ubicacion": "+TAB1"})` | 400 «… faltan 102 mm de placa» | el `layout_tablero` no entra con su `reserva` de riel (20 %); el error no dice que bajarla en el mismo lote alcanza |
| 8 | cilindro con `servicio.velocidad_m_s` = el pico | falla «caudal de la válvula»; la energía de impacto se aprueba con la de régimen | un solo dato sirve a dos cuentas; no hay señal ni aserción para la velocidad AL LLEGAR a la tapa |
| 9 | mover la variable de posición de una fotocelda | 13 escenarios reescritos a mano | `acoples.sensores` guarda `origen`/`direccion` en coordenadas fijas |
| 10 | `run_script` con `result=[techo, lateral, lateral]` y `simulate(escenario="desvio")` | la caja se queda en x 1635 | lo midió la corrección 2, ANTES de F7b; F7b ya pone un casco por SÓLIDO (`tests/test_v89_f7b_mecanica.py::test_una_pieza_de_varios_solidos_tiene_un_casco_por_solido`). Queda abierto el caso de UN sólido cóncavo (la U fundida) |

## Lo que se revisó antes de escribir esto

- `commands/expressions.py` (las trigonométricas en grados desde el principio) y el endpoint
  `/api/expression-grammar` (`api/routers/core.py`): ya decía «Ángulos en grados» en `note`. No
  alcanza: hace falta un aviso donde el agente MIRA (el valor que acaba de pedir).
- `services/conexiones.filtrar` y `piezas_pedidas`: un command_id resuelve a SUS piezas, y las de
  un `join_bolted` son la tornillería, que no es `a` ni `b` de su propio fijador.
- `physics/dinamica_cuerpos.clasificar` y `physics/stability.py` (`sujetas`): la regla de
  `gravity_test` (F7b, defecto 4) es la que falta en la dinámica.
- `commands/models_uniones.py` (`size` con patrón `^M\d{1,2}$`: M5 entra) y
  `library/engineering/report_uniones.py` (el aviso «fuera de tabla (M6–M24)»).
- `cosim/aserciones.py` y `cosim/veredicto.py`: el ancla, el margen `+ N ms` (`tras_ms`) y la
  ventana de `siempre`/`nunca`.
- `brief.py::_scene_brief` (el bloque `variables`) y `tools/recibo.job_result`.
- `commands/electrico_eval._pieza` (el 400 de la traba 6) y `commands/tablero.plan` +
  `library/electrico/colocacion.colocar` (la de la 7).

## Decisiones (para vetar)

- **D1. Las trigonométricas siguen en GRADOS; avisar donde el agente mira.** Cambiar la
  convención rompería todo log que ya las usa (puertas, plegados, cuñas). La gramática gana una
  clave `angulos` corta y explícita («tan(30) = 0,577; no conviertas con pi/180») y
  `expressions.avisos_expresion(expr)` detecta un argumento de `sin/cos/tan` que divide por 180
  algo que lleva `pi` (`tan(a*pi/180)`, `sin(pi/180*a)`): `resolve_expression` lo devuelve en
  `aviso` y `POST /api/variables` en `avisos_expresion` (los pasa el brief del MCP). Sólo cuando
  hay aviso: sin él, la respuesta es byte-idéntica. No es error: el valor se calcula igual.
- **D2. La tornillería de un `join_bolted` es parte de SU unión, también al leer y al simular.**
  (a) `get_connections(ids=…)` encuentra una unión también por el COMANDO que la declaró: un
  token que es el command_id de un `join_bolted`, o una pieza que ese comando insertó (perno,
  tuerca), trae su `jb_<cmd>` (`conexiones.filtrar`: el fijador casa si su `command_id` es el de
  un token o el de una pieza pedida). Los fijadores de una plantilla llevan command_id sintético
  (`{cmd}_u_…`) y los de `fasten` el suyo, que no es el de ninguna pieza: sólo cambia lo de
  `join_bolted`. (b) La dinámica y la co-simulación reciben `sujetas` = la tornillería de cada
  `join_bolted` declarado (`delivery_inputs.tornilleria_join_bolted`, la MISMA que usa
  `gravity_test`): una pieza de tornillería es ESTÁTICA si una de sus dos piezas lo es, y viaja
  con el CUERPO si una de ellas se mueve (los pernos del empujador van con el vástago); si no,
  queda fuera como hoy. Cambia el MJCF de toda máquina con `join_bolted` → **`COSIM_EPOCH` 9**.
- **D3. `fasten` admite M3–M5 en la cuenta y la nota no se corta a 120.** La tabla ISO 898-1 de
  áreas resistentes suma M3 (5,03 mm²), M4 (8,78) y M5 (14,2): `engineering_check` calcula el
  cortante en vez de «fuera de tabla», y el schema de `fasten.size` dice «M3–M24». `join_bolted`
  sigue en M6–M24 (es lo que tiene ficha DIN 933 en el catálogo: error de siempre). La nota de
  `fasten` y de `ground` pasa de 120 a 500 caracteres: el tope no tenía consumidor (la BOM busca
  patrones en ella) y el agente escribe ahí el porqué. Un log viejo (notas ≤ 120) valida igual.
  La rosca M3/M4 de `threads.thread_spec` pasa a la tabla (5,03 y 8,78 en vez de la fórmula 5,0 y
  8,8): 0,02 mm², sin geometría.
- **D4. `siempre`/`nunca` se acotan con «hasta <ancla> [+ N s|ms]».** «caja_1.x_mm > 2495 nunca
  hasta pulsar -S1 + 6 s» = la ventana [0, t(pulsar -S1) + 6 s]; con «desde A … hasta B …»,
  [t(A) + m, t(B) + m']. En objeto: `hasta` (ancla) y `hasta_tras_ms`. Un ancla de `hasta` que
  no ocurrió FALLA con su motivo (como «desde»), una ventana que termina antes de empezar es error
  al evaluar, y «… y antes» (lo que escribió el agente) es error al declarar que dice cómo se
  escribe. `hasta` va sólo con `siempre`/`nunca` (`dentro_de` ya tiene su Δ). Ancla nueva = los
  dos módulos (`aserciones.py`, `veredicto.py`) con caso verde y rojo; ningún escenario guardado
  la usa, así que no vence nada por sí sola (la época sube por D2).
- **D5. Una mutación que tocó variables devuelve SÓLO las que tocó y las que dependen de ellas.**
  `_scene_brief` (detail `diff`/`summary`, con afectados) filtra `variables` a las de los
  `set_variable` afectados más las que las nombran en su expresión (cierre transitivo), y declara
  `variables_omitidas` (convención de `paso.recortar`: nunca un recorte silencioso). `detail=
  "full"` y las consultas siguen trayéndolas todas. Vale para `set_variable`, `run_batch` y
  `edit_command` sobre una variable.
- **D6. Cambiar el componente de una pieza ligada NO religa solo: el error dice la llamada.** La
  ref de un dispositivo decide bornes, puertos, ficha y modelo de la co-simulación; cambiarla por
  un efecto lateral de editar la pieza cambiaría el ERC y los escenarios sin que nadie lo pida. El
  400 nombra el `add_device` y da el `edit_batch` exacto: el `component` de la pieza y la `ref`
  del dispositivo en el mismo lote.
- **D7. «No entra en el tablero» sugiere la reserva que sí entra.** Si la colocación falla y una
  reserva menor (0,15 → 0,10 → 0,05 → 0, en ese orden, la primera que entra) la resuelve, el
  error lo dice con la llamada (`edit_batch` con el cambio que lo llenó + `{"command_id":
  "<layout>", "params": {"reserva": R}}`) y recuerda que la reserva es el riel libre para
  ampliaciones (A13). No baja la reserva sola: es criterio de diseño del tablero.
- **D8 (F2). La velocidad de RÉGIMEN y la de LLEGADA son dos datos y la llegada se mide.**
  `servicio.velocidad_m_s` sigue siendo la de régimen (caudal de la válvula, tiempo de ciclo) y
  entra `servicio.velocidad_llegada_m_s` (energía de impacto contra la amortiguación de la ficha)
  con default = la de régimen (un log viejo da el mismo ERC). La co-simulación publica
  `-MM1.v_llegada_m_s`: la velocidad del vástago en el instante en que toca un tope (discreta, un
  valor por llegada), afirmable con «-MM1.v_llegada_m_s <= 0,5 siempre»; la memoria del aire usa
  la medida del escenario nominal vigente y, sin él, la declarada. `COSIM_EPOCH` sube (señal
  nueva).
- **D9 (F3). Un sensor del escenario se acopla por su PIEZA, no por coordenadas.** Si el
  dispositivo está ligado a su pieza 3D (`add_device.pieza`) o el acople dice `{"pieza": <id>}`,
  `origen` y `direccion` salen de las anclas de la pieza (el haz de la fotocelda del catálogo) al
  armar el snapshot; las coordenadas fijas siguen valiendo (los escenarios guardados no cambian).
  Mover la pieza cambia la firma del documento y vence el resultado, que es lo correcto.
- **D10 (F4). Un sólido cóncavo se descompone en cascos propios, sin librería nueva.** Medir
  primero (F0) si la traba sigue con la U de VARIOS sólidos tras F7b (el test de F7b dice que no)
  y cuánto frena una U de UN sólido. Si frena: `physics/hull.py` descompone el sólido por sus
  caras planas en losas convexas (paredes de chapa y perfiles: el caso real), con tope de cascos
  por pieza y aviso si no puede; un sólido sin caras planas sigue con su casco.

## Alternativas descartadas

- D1: radianes por defecto o funciones nuevas `sind`/`sinr` — lo primero rompe logs guardados; lo
  segundo duplica la gramática y el agente seguiría eligiendo mal. Un ERROR en vez de aviso —
  `x*pi/180` puede ser deliberado (un ángulo en grados a partir de un dato en radianes no lleva
  esa forma, pero no hay cómo probarlo): el aviso no frena a quien sabe.
- D2: que `join_bolted` declare un `fasten` de contacto por cada perno y tuerca (lo que hizo el
  modelador a mano) — cambiaría las uniones de todo log viejo al regenerar (BOM de tornillería
  declarada, puertas, conteos). Leerlo donde se simula, como `gravity_test`, no toca el log.
- D3: subir el catálogo DIN 933 a M5 para `join_bolted` — refs nuevas, builders y largos de
  catálogo; nadie lo pidió. Quitar el tope de la nota — un tope generoso evita un log inflado por
  error.
- D4: una ventana nueva «antes_de <ancla>» — duplica la de `siempre`/`nunca`; «hasta» compone
  con «desde» y se lee igual que se dice.
- D5: un `detail="mínimo"` sólo para `set_variable` — el agente tendría que pedirlo; el problema
  es el default. Mandar sólo la variable tocada — se pierde lo que cambió por arrastre, que es
  justo lo que el agente quiere verificar.
- D6: religar automáticamente cuando hay un solo dispositivo ligado a la pieza — ver D6; además
  el cambio inverso (editar la ref) seguiría sin religar la pieza.
- D7: bajar la reserva sola hasta que entre — un criterio de diseño no se negocia en silencio.
- D8: derivar la llegada de la traza analógica — a 50 Hz se pierde el pico del último
  milímetro. Una ventana genérica «al llegar» — más gramática para un solo uso.
- D9: `origen: "=x_fotocelda"` en el escenario — sigue a la variable, no a una pieza movida a
  mano, y repite en el escenario la geometría que el modelo ya tiene.
- D10: CoACD/V-HACD — librería nueva (instalación, licencia) para un caso que hoy es de chapa
  plana.

## Fases

| fase | qué | paquete | tamaño | depende de | se verifica con |
|---|---|---|---|---|---|
| F1 | D1–D7 | commands, services, physics, cosim, library, api, tools/brief | M | — | un test por traba con su reproducción (rojo antes); suite completa; golden del MCP re-congelado a propósito; `COSIM_EPOCH` 9 con su huella |
| F2 | D8: F0 mide el pico y la llegada en la 77 con desviador; el dato nuevo, la señal y la memoria | commands (models_neumatica), cosim/neumatica, services/neumatica | M | F1 | el escenario nominal de la 77 publica la llegada y la memoria la usa; un log viejo da el mismo ERC |
| F3 | D9: F0 mide cuántos escenarios guardados repiten la pose de su sensor; el acople por pieza | services/cosim_snapshot, cosim/escenario | S | — | mover la variable de la fotocelda no obliga a tocar ningún escenario y el resultado queda vencido |
| F4 | D10: F0 reproduce la U de un sólido; si frena, la descomposición | physics/hull | M | — | la U de un sólido deja pasar la caja; los cascos de lo demás, idénticos |

## Lo que este plan NO hace

- No cambia la convención de grados ni el log de ningún proyecto.
- No agrega refs de catálogo (pernos M3–M5 de `join_bolted`).
- No religa dispositivos ni baja reservas por su cuenta.
- La traba «las cajas en cola se llaman `caja_0…`» queda en el backlog: es la convención de la
  dinámica (índice 0) y cambiarla vence todos los escenarios que las nombran.

## Riesgos

- D2b cambia lo que choca en la dinámica (los pernos ahora son geometría estática): una caja
  que pasaba rozando una cabeza de perno puede frenarse. Mitigación: `COSIM_EPOCH` 9 deja los
  resultados guardados vencidos (AMARILLO), nunca verdes con el motor viejo.
- D5 saca del brief variables que un cliente pudiera leer tras una mutación. Mitigación: sólo el
  MCP usa `_scene_brief`; la UI lee el REST, que no cambia; `detail="full"` las trae todas.
- D4 suma gramática: un texto viejo que dijera «hasta» en una señal. Mitigación: «hasta» sólo se
  lee como palabra suelta en la ventana, después de la ventana `siempre`/`nunca`.

## Bitácora

### F1 (D1–D7) — 2026-10-26

Hecho (base `7141104`), un test por traba con su reproducción (`tests/test_trabas_de_modelado.py`,
`tests/test_cosim_aserciones_hasta.py`):

- **D1.** `expressions.avisos_expresion` + `ANGULOS`; `resolve_expression` suma `aviso`,
  `/api/expression-grammar` la clave `angulos` y `POST /api/variables` `avisos_expresion` (el
  brief del MCP lo pasa: `tools/recibo.job_result`). Sólo con aviso: sin él, byte-idéntico.
- **D2.** (a) `conexiones.filtrar` casa el fijador también por el command_id del token o de una
  pieza pedida. Medido sobre la faja con desviador v2: `get_connections(ids=["c1959"])` trae
  `jb_c1959` (y los cuatro `torn_jb_c1959[k]` que el modelador declaró a mano para esquivarlo).
  (b) `clasificar(sujetas=)` y los cuatro llamadores de `prepare_dynamics` (`api/sims.py` ×2,
  `services/cosim_snapshot.py` con su `prever`, `services/marcha_ejemplo.py`). Medido sobre la
  misma máquina, SIN los `fasten` de contacto a mano: 21 piezas fuera de la simulación antes (20
  pernos y tuercas de seis `join_bolted` + `c119`), 1 después (`c119`, que no es tornillería); los
  pernos de la placa de la guía (`c1859`) viajan con el cuerpo del vástago.
- **D3.** `TENSILE_AREA_MM2` suma M3 5,03 · M4 8,78 · M5 14,2 (ISO 898-1); el schema de
  `fasten.size` dice «M3–M24» y el aviso de `report_uniones`, «fuera de tabla (M3–M24)». La nota
  de `fasten` y de `ground` admite 500 caracteres. **Lo que el F0 encontró**: `fasten(size="M5")`
  no da 400 en el comando (M3, M4, M5 y M6 se aceptan; el patrón es `^M\d{1,2}$`) y en los
  transcripts no hay ninguna llamada con `size="M5"`: el modelador leyó «M6–M24» en el schema y
  escribió la métrica en la nota. Lo que sí faltaba era la tabla (el cortante «fuera de tabla»).
  El 400 real de esa corrección fue la nota de 150 caracteres.
- **D4.** «hasta» en `aserciones._de_texto`/`leer_asercion` y en `veredicto.evaluar_una`; «… y
  antes» es error que da la forma correcta. Texto canónico: el margen de `hasta` en s si es
  entero («+ 6 s»), si no en ms.
- **D5.** `brief.variables_tocadas` (cierre por los nombres de la expresión, sin `re`: `brief.py` no importa nada, `test_mcp_destino.py`) y `variables_omitidas`.
  Sólo filtra si las variables traen `command_id` (el payload real siempre; el falso del golden
  no, y queda igual). Medido con las 60 variables de la faja con desviador v2: `set_variable` de
  `paso_rod` 5 709 B → 311 B; de `largo_total` (arrastra 8) 5 709 → 1 163 B.
- **D6.** `electrico_eval._pieza(…, cmd_id)` (lo pasan los dos llamadores del carril; el del
  tablero no): el 400 suma «cambia también la ref del dispositivo c1680 EN EL MISMO LOTE:
  edit_batch([<tu cambio de c1756>, {"command_id": "c1680", "params": {"ref": "…G14"}}])». El
  campo de la pieza depende de su comando (`component` en `insert_component`, `ref` en el
  cilindro): por eso el primer elemento queda como «tu cambio».
- **D7.** `colocacion.reserva_que_entra` (pura) y `tablero.plan(…, cmd_id)`: el error suma la
  mayor reserva de 0,15/0,10/0,05/0 que entra, con el `edit_batch` (si el cambio es una edición) o
  el `edit_command` previo (si se agrega un dispositivo: `run_batch` no admite ediciones, lo
  probó el modelador con «Comando desconocido: edit_command»). `colocar` no cambia su texto (un
  test lo ancla con `$`).

Vigencia: **`COSIM_EPOCH` 9** (D2b cambia el MJCF de toda máquina con `join_bolted`; D4 entra en
el mismo salto) con su huella. `layout_tablero` sigue en v2 y sólo cambia su huella D11 (pasa
`cmd_id` a `plan`, misma geometría). Ningún executor de geometría cambió: sin `version` ni
`GEOM_CACHE_EPOCH`. Un log viejo regenera igual (notas ≤ 120 validan con el tope nuevo; nada se
agrega al log). Golden del MCP re-congelado: cambian sólo las descripciones de `run_command`,
`set_variable`, `resolve_expression` y `set_scenario`; ninguna salida de llamada.

Suite completa (`-n 4`, en el worktree): antes 6 280 pasan, 10 saltadas, exit 0; después 6 311
pasan, 11 saltadas, exit 0 (el primer intento dio 1 falla: `brief.py` importaba `re` y su gate de
pureza lo prohíbe). `ruff check core tests scripts` limpio.
