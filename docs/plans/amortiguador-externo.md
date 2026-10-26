---
estado: en curso
nota: F0, F1, F1b mergeadas (2026-10-26) y F2 hecha por MCP sobre la faja con desviador: dos AMORT-HID-M20-15-T en un bloque macizo atornillado, red a 5 bar, 34 de 58,8 J por golpe y 15 de 25 golpes/min; 16 escenarios en verde y 15 cajas/min cuadra (12 de 12). NO subió la capacidad: el límite pasó a ser el retroceso del vástago en la parada de emergencia (válvula 5/2 monoestable, 0,95 de 1,0 m/s). Mario decidió quedarse en 15 cajas/min (2026-10-26); 18/min pediría una 5/3 de centro cerrado o un cilindro de más de 1 m/s. F3 no hace falta; F4 (segunda ficha con energía por hora y cotas) sigue
descripcion: el cilindro que llega rápido frena en un amortiguador hidráulico de catálogo al final de su carrera; el ERC y la memoria revisan su energía por ciclo y por hora con la fórmula de su ficha, en vez de obligar a estrangular la velocidad
---

# El cilindro llega rápido y frena en un amortiguador de catálogo

## Estado y origen

- Lo pidió la sesión orquestadora del 2026-10-26 a partir de un problema REAL: la faja con
  desviador neumático ([V8.9](V8.9-neumatica.md) F7: cilindro ISO 15552 Ø63 × 800 y una placa de
  unos 25 kg de masa móvil) no llega con holgura a 15 cajas/min. Para no pasar la energía que
  admite la amortiguación interna del cilindro (11,4 J el Ø63, SMC C96) hubo que estrangular la
  velocidad: ciclo de 3,5 s y unas 14,8 cajas/min como máximo.
- La solución de mercado es un **amortiguador hidráulico externo** al final de carrera, en los
  dos sentidos: la carga llega rápido y el amortiguador absorbe la energía. El catálogo no lo
  tenía y la regla de energía (`library/neumatica/calculo.energia_impacto`, `erc._impacto`) sólo
  conocía `E_amortiguacion_J` del cilindro.
- Plan fuera del roadmap (slug solo). Toca `library` (catálogo, builder, cálculo), `commands`
  (un campo del `servicio`) y `services` (el ERC y la memoria del aire ven el catálogo, la
  capacidad nominal y la escena): por eso hay plan.

## Lo que hay hoy (medido)

- `erc._impacto` (`library/neumatica/erc.py`) y `memoria._impacto` (`library/neumatica/memoria.py`)
  comparan ½·m·v² con `E_amortiguacion_J` de la ficha del cilindro: una sola energía para los dos
  extremos y ninguna forma de decir que un extremo frena afuera.
- V8.9 D3: «la amortiguación no se simula; se verifica». La co-simulación lleva el vástago hasta
  el tope de su junta prismática; la memoria toma el pico de velocidad de los escenarios vigentes
  (`services/neumatica.lecturas`, F7b).
- [trabas-de-modelado](trabas-de-modelado.md) D8 (F2, contrato futuro): la velocidad de LLEGADA
  (`servicio.velocidad_llegada_m_s` y la señal `-MM1.v_llegada_m_s`) será un dato distinto de la
  de régimen. Este plan no la implementa: deja UN punto donde leerla (`cilindros.v_choque`).
- El caso de la faja, a mano con la ficha (§ Bitácora F1): Ø63 a 6 bar empuja 1870 N al avance
  y 1682 N al retroceso; 25,4 kg (0,43 + 0,0025·800 de la masa móvil Festo + 23 kg de placa).

## Lo que se revisó antes de escribir esto

- La ficha oficial **SMC «Shock Absorber RB Series»** (EMC-RB-01A-UK,
  `https://content2.smcetech.com/pdf/RB.pdf`, bajada a `C:\t\normas\neumatica\rb\` y extraída con
  `pdftotext`). Trae: energía máxima por ciclo, carrera, rango de velocidad de choque (0,05–5 m/s),
  frecuencia máxima a energía máxima, empuje máximo admisible, fuerzas del resorte, peso, cotas y
  par de apriete; y el **método de selección**: E = E1 + E2, E1 = ½·m·v², E2 = F1·S (carrera de
  cilindro horizontal), masa equivalente Me = 2·E/v², con un ejemplo resuelto (50 kg, 0,3 m/s,
  Ø40 a 0,5 MPa → 11,7 J sobre un RB2015) que el test reproduce. Su nota 1: la velocidad de
  choque es **2·v̄** si v̄ sale del tiempo de carrera.
- La ficha NO publica la energía por HORA del RB: da la frecuencia máxima a energía máxima. La
  tabla gemela de la serie RBL (mismas energías y frecuencias) dice que la frecuencia crece en
  proporción al bajar la energía ⇒ E_h,máx = E_máx·n_máx·60. Se usa DERIVADA y en `a_confirmar`.
- Las letras de la tabla de cotas (D, L, LL, h1 del tope) se leyeron sin su dibujo (el PDF no se
  pudo rasterizar sin instalar nada): en `a_confirmar`, como las del ISO 6432 de V8.9 [F5]. La
  rosca, la carrera y la tuerca (entrecaras 19/27/36, entre vértices 21,9/31,2/41,6 = 2/√3 ·
  entrecaras) son coherentes entre sí.
- `neumatica_eval._servicio` es la puerta de entrada del `servicio`; `services/neumatica.reglas`
  sólo recibía el modelo del carril (sin catálogo, requisitos ni escena): hubo que pasarle `doc`.
- `tests/test_contrato_comandos.py` (CAMPOS) exige declarar los dos campos nuevos; la huella D11
  de `add_device` no cambia (el evaluador del carril no entra en ella).

## Decisiones (para vetar)

- **D1. Familia del catálogo `amortiguador_hidraulico`, ficha en `specs` validada al cargar.**
  `library/data/134_amortiguadores.yaml` (categoría `amortiguadores`), tres tamaños de la tabla
  SMC RB (M14×1,5 carrera 12, M20×1,5 carrera 15, M27×1,5 carrera 25), cada uno sin y con
  contratuerca de tope («-T», la opción S de SMC): seis refs `AMORT-HID-…`. Cada ref lleva
  `carrera_mm`, `E_max_J`, `E_max_hora_J`, `n_max_ciclos_min`, `F_max_N`, `v_min_m_s`,
  `v_max_m_s`, `rosca`, fuerzas del resorte, par de la tuerca, agujero roscado previo, `fuente`
  y `a_confirmar`. `neumatica/amortiguador.parse_ficha` la valida en el loader: incompleta, no
  carga. Builder propio (`library/builders_amortiguador.py`): cuerpo roscado liso del Ø nominal,
  vástago extendido, dos tuercas con 10 mm de chapa entre ellas (criterio de modelo) y la
  contratuerca de tope; anclas `extremo_vastago`, `rosca`, `fondo` y `tope`. Sin bloque
  `neumatico:` (no tiene puertos de aire ni lugar en el esquema ISO 1219) y sin `cost` (no hay
  precio con fuente). Porqué: es una pieza mecánica de compra; su dato de cálculo es su ficha.
- **D2. Se declara en el `servicio` del cilindro, un campo por extremo.**
  `servicio.amortiguador_avance` (frena al final del avance, vástago afuera) y
  `servicio.amortiguador_retroceso` (al final del retroceso), cada uno una ref de la familia de D1.
  Default `None` = la amortiguación del cilindro, como antes: un log viejo regenera igual y su
  `servicio` guarda las mismas claves (`model_dump` sin `None`). El evaluador del carril rechaza
  una ref que no es de la familia, con «¿quisiste decir…?» y la lista. La pieza 3D se inserta
  aparte (`insert_component`) y el ERC avisa si la ref declarada no está en la escena (regla
  «amortiguador sin pieza», sólo si la escena tiene piezas). Porqué: es el dato que el ERC ya lee
  del cilindro; dos extremos fijos caben en dos campos planos.
- **D3. La regla por ciclo es la fórmula de la ficha.** En un extremo con amortiguador:
  E = ½·m·v² + F·S ≤ E máx por ciclo, con m = masa móvil de la ficha del cilindro + carga
  declarada, F = p·A al avance o p·A anular al retroceso (teórica, a la presión que le llega: la
  ficha usa el empuje del cilindro), S = la carrera del amortiguador. Además F ≤ F máx admisible y
  v ≤ v máx (error), v < v mín (aviso) y E < 5 % de la máxima (aviso: la ficha pide un tamaño
  menor). Ese extremo deja la regla «energía al fin de carrera» del cilindro; el otro la sigue
  (su texto nombra el extremo). Masa equivalente y fuerza sobre el soporte (≈ 2·E/S, la ficha) se
  publican como dato, no se juzgan (su máximo es un gráfico; el operador de la fórmula del soporte
  no sale en el texto extraído).
- **D4. Velocidad de choque: la medida, luego la de llegada, luego 2·v̄.** La memoria usa el pico
  medido en la co-simulación vigente (instantáneo: la velocidad real al llegar). Sin medida: la
  de llegada declarada cuando exista (`velocidad_llegada_m_s`, trabas-de-modelado D8) y, con sólo
  la de régimen (que el schema define como carrera / tiempo de avance), **2·v̄** como pide la
  nota 1 de la ficha. Un solo punto: `cilindros.v_choque`.
- **D5. Frecuencia y por hora, con los ciclos que el modelo tenga.** Un choque por extremo y por
  ciclo. n ≤ la frecuencia máxima de la ficha, TAL CUAL (error encima): así la compara el
  ejemplo de selección de SMC RB («n = 20 < 25» con 11,7 J de 58,8), aunque la nota de la serie
  RBL diga que puede crecer al bajar la energía. Y E·n·60 ≤ E máx por hora (derivada = E máx ·
  n máx · 60: con las dos anteriores en verde nunca pasa sola; queda como dato para una ficha que
  la publique aparte, F4). Un error en cualquiera sugiere las refs del catálogo que SÍ entran con
  esas cifras (`amortiguador.entran`, una por capacidad), o dice que ninguna. n = `servicio.ciclos_min` si el cilindro declara su cadencia (el dato más
  propio, el mismo de la demanda de aire); si no, `requirements.paquetes_por_minuto` (un ciclo por
  paquete, declarado); sin ninguno, SIN EVALUAR: el ERC lo dice en el detalle de la fila del ciclo
  (no cuenta como aviso: un dato que falta no es un defecto, como «ningún cilindro declara su
  velocidad»), la memoria lo suma a su «alcance» y el panel lo muestra como `sin_evaluar`.
- **D6. El amortiguador NO se simula (V8.9 D3 sigue).** Se verifica por energía, como lo hace el
  catálogo; la hipótesis va visible en cada cálculo. La huella de la co-simulación no cambia:
  `COSIM_EPOCH` queda en 9.
- **D7. Vigencia.** `GEOM_CACHE_EPOCH` NO sube: el builder y las refs son nuevos y ninguna
  geometría existente cambia. Ninguna `version` de comando sube: `add_device` es del carril y su
  huella D11 no cambió (la suite lo prueba); CAMPOS suma los dos campos. Editar el `servicio` de
  un proyecto cambia su log ⇒ vence los escenarios de ESE proyecto (lo correcto).

## Alternativas descartadas

- D1/D2: el amortiguador como dispositivo del carril (`add_device` con una ficha `neumatico:` de
  tipo nuevo, ligado al cilindro) — pide designación, puertos que no tiene y un lugar en el
  esquema ISO 1219; más superficie para el mismo dato.
- D2: una lista `amortiguadores: [{ref, extremo}]` — más anidada para el PATCH de `edit_command`
  y admite dos en el mismo extremo; los extremos son dos y fijos.
- D2: deducir el amortiguador de la escena (qué pieza toca el empujador al final) — geometría
  frágil para un dato que el diseñador SABE; queda la regla que avisa si falta la pieza.
- D4: la velocidad de régimen tal cual (como la regla de la amortiguación del cilindro) — la
  ficha pide 2·v̄ cuando la velocidad sale del tiempo de carrera; un escenario la reemplaza.
- D5: escalar la frecuencia máxima con la energía (n_máx · E_máx / E, la nota de la serie RBL) —
  la ficha del RB no lo dice y su ejemplo de selección compara n con n máx sin escalar; F4 lo
  puede abrir con una ficha que lo publique.
- D5: sólo `paquetes_por_minuto` — ignoraría la cadencia que el cilindro ya declara (un desviador
  que actúa en una de cada tres cajas cicla menos que la capacidad).
- D6: simular el frenado (una fuerza del amortiguador en sus últimos S mm de la junta) — cambia
  la dinámica, la huella y el epoch; la verificación por energía es lo que hace el catálogo. Queda
  como F3 si F2 muestra que hace falta.

## Fases

| fase | qué | paquete | tamaño | depende de | se verifica con |
|---|---|---|---|---|---|
| F0 | leer la ficha SMC RB y hacer la cuenta de la faja a mano (sólo lectura) | — | S | — | § Bitácora F0 |
| F1 | D1–D7: familia, builder, campos del servicio, regla por ciclo y por hora en el ERC, la memoria y el panel | library, commands, services | M | F0 | `tests/test_amortiguador_externo.py` (el ejemplo de la ficha, límite verde/rojo, por hora, sin evaluar, un servicio sin amortiguador da lo mismo); suite completa y ruff |
| F2 | la faja con desviador: un modelador por MCP inserta los dos amortiguadores (ménsula + `join_bolted`), declara el `servicio`, abre el regulador y corre el escenario nominal a 15 cajas/min | modelo (MCP), sin código | M | F1 mergeada; mejor tras trabas-de-modelado F2 (la llegada medida) | el escenario nominal pasa 15 cajas/min con holgura, `electrical_check` y la memoria en verde, revisión a ciegas |
| F3 | sólo si F2 lo pide: el frenado en la co-simulación (D6 alternativa) | cosim/neumatica | M | F2 | `COSIM_EPOCH` 10 con su huella; la llegada medida baja a 0 en S mm |
| F4 | una segunda ficha oficial que publique la energía por hora y el dibujo de cotas (ACE serie MC u otra); quitar lo confirmado de `a_confirmar` | library (YAML) | S | — | el test de la ficha con la nueva fuente |

## Lo que este plan NO hace

- Choque vertical (±m·g·S), giratorio o de carga libre: la ficha los trae, el cilindro de la
  faja empuja en horizontal. Se dice en la hipótesis.
- Juzgar la masa equivalente máxima (la ficha la da en un gráfico) ni la fuerza sobre el soporte.
- Colocar el amortiguador solo, ni dimensionar su ménsula.
- Simular el frenado (D6) ni la velocidad de llegada (trabas-de-modelado D8).
- Precio: las refs no traen `cost` (sin fuente).

## Riesgos

| riesgo | mitigación |
|---|---|
| 2·v̄ es conservador con un cilindro regulado (velocidad casi constante) y puede dar rojo donde no lo es | un escenario vigente mide el pico y lo reemplaza (D4); la hipótesis lo dice |
| La energía por hora es derivada, no publicada | `a_confirmar` + F4 |
| Las cotas leídas sin dibujo | `a_confirmar`; la rosca (la cota de interfaz) y la tuerca son coherentes |
| En 3D el empujador toca el vástago del amortiguador en la pose extendida (contacto intencional) y la puerta de entrega podría verlo como interferencia | F2 lo mide; si pasa, un `fasten` de contacto declarado |
| Un amortiguador declarado y no modelado no se compra | regla «amortiguador sin pieza» (aviso) |

## Bitácora

### F0 — la ficha y la cuenta a mano (2026-10-26)

- SMC RB leída (§ Lo que se revisó). Tabla usada: RB1412 / RB2015 / RB2725 = 19,6 / 58,8 / 147 J
  por ciclo, 45 / 25 / 10 ciclos/min, 814 / 1961 / 2942 N, carrera 12 / 15 / 25 mm.
- La faja (Ø63 × 800 a 6 bar, 23 kg de placa, régimen declarado 0,7 m/s ⇒ choque 1,4 m/s):
  E1 = ½·25,43·1,4² = 24,9 J. Al avance con el M27: E2 = 1870·0,025 = 46,8 J, E = 71,7 J de
  147 J y, a 15 ciclos/min, 64 512 J/h de 88 200. Al retroceso con el M20: E2 = 1682·0,015 =
  25,2 J, E = 50,1 J de 58,8 J, 45 134 J/h. El M20 al AVANCE pasaría la energía (53 J) pero
  dejaría el empuje a 5 % de su máximo (1870 de 1961 N; a 6,3 bar ya no): por eso el M27 adelante.

### F1 — familia, declaración y regla (2026-10-26)

- Hecho: D1–D7 tal cual. Archivos: `library/neumatica/amortiguador.py` (ficha + `choque` +
  `por_hora`, puro), `library/builders_amortiguador.py`, `library/data/134_amortiguadores.yaml`,
  `library/loader.py` (registro y validación), `library/neumatica/cilindros.py` (`amortiguadores`,
  `v_choque`, `fuerza_extremo`, `ritmo`, `choques`: UNA cuenta para ERC y memoria),
  `erc.py` (reglas «amortiguador externo» y «amortiguador sin pieza»; `_impacto` salta el extremo
  cubierto), `memoria.py`, `commands/models_neumatica.py` + `neumatica_eval.py` (los campos y su
  validación), `services/neumatica.py` (catálogo, capacidad, escena), `services/electrico.py` y
  `services/neumatica_panel.py` (pasan `doc`; el panel no repite la fila del ERC y muestra
  `sin_evaluar`).
- Intento fallido: la comparación en el límite exacto (19,6 J · 45 · 60) daba rojo por el
  redondeo binario (52 920,000000000004); las comparaciones con la ficha llevan una tolerancia
  relativa de 1e-9.
- Primer texto del ERC con los dos extremos cubiertos decía «Ningún cilindro declara su
  velocidad» en la regla de la amortiguación del cilindro: ahora dice que frenan afuera.
- La primera corrida de la suite dio 5 rojos esperados: los conteos del catálogo (456 → 462 refs:
  `test_catalogo_electrico`, `test_catalog_datadriven`, dos de `test_extensiones`) y el conjunto de
  anclas por familia (`test_catalog_cadenas`). Actualizados a propósito con su comentario.
- Suite de F1, primera entrega (laptop, `-n 4`, `PYTHONPATH` del worktree, `--basetemp C:\t\bt-amort`): exit 0, sin
  FAILED. `ruff check core tests scripts`: limpio. Ningún archivo pasa de 500 líneas (`erc.py`
  483).

### F1b — la frecuencia máxima (revisión de la sesión principal, 2026-10-26)

- La revisión encontró el hueco: la energía por hora se derivaba de la frecuencia máxima, pero no
  se verificaba que la cadencia la respetara. Con la faja a 15 ciclos/min, el M27 al avance (10
  ciclos/min) salía VERDE y la F0 lo recomendaba. Causa raíz: se tomó E_h,máx como el límite
  completo, y con E ≤ E máx y n ≤ n máx esa cuenta queda implicada: el límite que manda es la
  frecuencia.
- Hecho: `amortiguador.frecuencia` (n ≤ n máx tal cual, D5) en el ERC (la fila del extremo dice
  «n de n máx ciclos/min» y, en rojo, las refs que entran), la memoria (una fila más por extremo:
  ciclo, frecuencia, hora) y el panel («recibe 15 golpes por minuto y admite 10», con la ref que
  entra); sin ciclos, SIN EVALUAR como la energía por hora. Tests: verde en el límite y rojo
  encima en la función, el ERC, la memoria y el panel.
- **La faja recalculada a 15 ciclos/min (dato para la F2; no se elige por la persona).** Ø63 ×
  800, 25,43 kg (0,43 + 0,0025·800 + 23), choque 1,4 m/s (2·0,7 de régimen, D4), F = p·A al avance
  (3117,2 mm²) y p·A anular al retroceso (2803,1 mm²):

  | p (bar) | extremo | ref | E por ciclo (J) | empuje (N) | frecuencia | E por hora (J/h) | resultado | choque máx. por energía (régimen ×½) |
  |---|---|---|---|---|---|---|---|---|
  | 6 | avance | M14-12 | 47,4 / 19,6 | 1870 / 814 (230 %) | 15 / 45 | 42 629 / 52 920 | rojo: energía y empuje | — |
  | 6 | avance | **M20-15** | 53,0 / 58,8 (90 %) | 1870 / 1961 (**95,4 %**) | 15 / 25 | 47 679 / 88 200 | verde | 1,55 m/s (0,78) |
  | 6 | avance | M27-25 | 71,7 / 147 | 1870 / 2942 (64 %) | **15 / 10** | 64 512 / 88 200 | rojo: frecuencia | 2,81 m/s (1,40) |
  | 6 | retroceso | M14-12 | 45,1 / 19,6 | 1682 / 814 | 15 / 45 | — | rojo: energía y empuje | — |
  | 6 | retroceso | **M20-15** | 50,1 / 58,8 (85 %) | 1682 / 1961 (85,8 %) | 15 / 25 | 45 134 / 88 200 | verde | 1,62 m/s (0,81) |
  | 6 | retroceso | M27-25 | 67,0 / 147 | 1682 / 2942 | **15 / 10** | 60 271 / 88 200 | rojo: frecuencia | 2,87 m/s (1,44) |
  | 5 | avance | **M20-15** | 48,3 / 58,8 (82 %) | 1559 / 1961 (79,5 %) | 15 / 25 | 43 471 / 88 200 | verde | 1,67 m/s (0,83) |
  | 5 | retroceso | **M20-15** | 45,9 / 58,8 (78 %) | 1402 / 1961 (71,5 %) | 15 / 25 | 41 350 / 88 200 | verde | 1,72 m/s (0,86) |
  | 4 | avance | **M20-15** | 43,6 / 58,8 (74 %) | 1247 / 1961 (63,6 %) | 15 / 25 | 39 262 / 88 200 | verde | 1,78 m/s (0,89) |
  | 4 | retroceso | **M20-15** | 41,7 / 58,8 (71 %) | 1121 / 1961 (57,2 %) | 15 / 25 | 37 566 / 88 200 | verde | 1,82 m/s (0,91) |

  Lectura de las cifras:
  - A 15 ciclos/min, del catálogo de hoy sólo el **M20-15 entra en los dos extremos**, y a 6, 5 y
    4 bar. El M27 queda fuera por frecuencia a cualquier presión; el M14, por energía y empuje.
  - A 6 bar el M20 al avance entra con el empuje al 95,4 % de su máximo: el límite del empuje es
    1961 / 311,7 = **6,29 bar**. Una deriva del regulador de +0,3 bar lo saca de ficha. Su energía
    queda al 90 %, con choque máximo 1,55 m/s (0,78 m/s de régimen con la regla 2·v̄; la medida
    de un escenario puede dar más margen, D4).
  - Bajar la presión a 5 bar deja el empuje al 79,5 % y sube el choque admisible a 1,67 m/s; a
    4 bar, 63,6 % y 1,78 m/s. Pero también baja la fuerza y la velocidad que da el cilindro (la
    relación de carga y el tiempo de ciclo los revisa la F2 con su escenario).
  - Bajar la velocidad sin bajar la presión no mejora el empuje (95,4 % a 6 bar con cualquier v):
    sólo da margen de energía.
  - Para no depender del margen de empuje haría falta una ref de más empuje y ≥ 15 ciclos/min
    (el catálogo no la tiene: F4 puede sumarla con su ficha).

### F2 — la faja con desviador por MCP (2026-10-26)

Modelador `claude -p` + revisor a ciegas + una corrección (38 min de sesiones, 12 USD). Medido por la
API de la flota:

| | avance | retroceso |
|---|---|---|
| amortiguador | AMORT-HID-M20-15-T | AMORT-HID-M20-15-T |
| E/ciclo (choque 2·v̄ = 0,84 m/s) | 33,7 / 58,8 J | 31,3 / 58,8 J |
| empuje a 5 bar | 1559 / 1961 N | 1402 / 1961 N |
| golpes/min | 15 / 25 | 15 / 25 |
| E/hora | 30 294 / 88 200 J/h | 28 173 / 88 200 J/h |

- La red baja a 5 bar (a 6 bar el empuje del M20 quedaba al 95 %); la caja de 15 kg pasa con su
  escenario propio.
- El ciclo NO bajó (3,44 s antes y después): abrir los reguladores de escape saca de ficha al
  vástago en `seta_desvio`, donde la 5/2 monoestable lo hace volver a 0,92–0,95 m/s (máx. 1,0 del
  cilindro). A 18/min el flujo no cuadra (5 trabados). Mario: «nos quedamos en 15 cajas por minuto».
- El revisor confirmó una ALTA (escuadras soldadas de 10 mm sin cartela, FS 1,16 a fatiga): la
  corrección puso un bloque macizo A36 con 2 pernos M10 (σ ≈ 3 MPa).
- Pendiente del ERC (backlog): la velocidad de choque usa 2·v̄ aunque haya un escenario corrido
  con el pico medido (0,867 m/s → 34,3 J, igual en ficha); D4 dice «la medida primero».

