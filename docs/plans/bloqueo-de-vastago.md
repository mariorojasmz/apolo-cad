---
estado: en curso
nota: F0 y F1 hechas en la rama wip/bloqueo-de-vastago (2026-10-26, suite completa verde, sin mergear): falta revisarla y mergearla; después F2 (la faja con desviador por MCP con BLOQ-VAST-20-S y su 3/2 en la cadena de la seta), F3 (símbolo ISO 1219 y fila propia en el panel) y F4 (cilindro con bloqueo integrado; ficha con tiempos y B10d)
descripcion: el cilindro lleva un bloqueo de vástago de catálogo que muerde el vástago por resorte cuando la seta le quita el aire; la co-simulación lo frena y lo sostiene (o lo ve deslizar) y el ERC revisa su retención, que bloquee sin aire y que la seta lo corte
---

# El vástago queda quieto al pulsar la seta: bloqueo de vástago de catálogo

## Estado y origen

- Lo pidió la sesión orquestadora del 2026-10-26 por un problema REAL, medido en la
  co-simulación de la faja con desviador neumático ([amortiguador-externo](amortiguador-externo.md)
  F2): cilindro ISO 15552 Ø63 × 800 (vástago Ø20) con una 5/3 de centro a escape. Con la seta a
  media carrera la válvula va al centro y las dos cámaras escapan, pero la A escapa más lento
  (regulador -RZ1 con C 1,4 contra -RZ2 con C 2,4) y el aire que queda lleva la placa hasta el tope
  a 0,716 m/s, 8,5 s después de la seta. Es movimiento con fuerza tras una parada de emergencia.
- La solución de mercado es un **bloqueo de vástago**: una unidad de sujeción que muerde el
  vástago por resorte y lo libera con aire. Sin aire (seta, corte, fuga) bloquea.
- Plan fuera del roadmap (slug solo). Toca `library` (catálogo, builder, ficha, ERC, memoria),
  `commands` (un campo del `servicio`), `cosim` (un modelo de aire y el acople con MuJoCo) y
  `services` (el snapshot, el resumen del escenario y el ERC con la red eléctrica): por eso hay plan.

## Lo que hay hoy (medido)

- El catálogo no trae ningún bloqueo de vástago, ni la ficha `neumatico:` un tipo para él
  (`library/neumatica/ficha_tipos.TIPOS`).
- `cosim/neumatica/cilindro.py`: el vástago sólo siente la fuerza neumática media y la fricción
  de los sellos (`frictionloss` de la junta, que pone el snapshot); nada lo retiene con las cámaras
  desbalanceadas.
- `cosim/acople.py` ya sabe trabar una junta sin vibrar: el `atasco` de un motor es fricción seca
  (`dof_frictionloss`), no un par explícito (V8.3 D8). Es el camino para la sujeción.
- El ERC eléctrico sólo pide que haya seta con motores (`library/electrico/erc._parada_emergencia`);
  nadie mira QUÉ corta la seta. `library/electrico/redes.Llegada.via` ya dice por qué contactos
  llega cada potencial a un borne: con eso se puede saber si una bobina la corta la seta.

## Lo que se revisó antes de escribir esto

Fichas oficiales, bajadas a `C:\t\normas\neumatica\bloqueo\` y extraídas con `pdftotext`:

- **[B1] Festo, «Clamping cartridges/units KP/KPE/KEC/KEC-S»** (hoja de grupo 2020/09,
  `https://www.landefeld.com/shop/media/festo/gruppendatenblaetter/kp-kpe-kec_en.pdf`: el PDF de
  Festo que sirve el distribuidor). Lo que cambió la solución:
  - todas sujetan por RESORTE y liberan con aire («Clamping via spring force, compressed air to
    release»), en los dos sentidos;
  - **KEC** (Ø16/20/25): retención estática 1300 / 3200 / 8000 N, presión mínima de liberación
    3,8 bar, trabajo 3,8–10 bar, puerto G1/8 / G1/4 / G3/8, patrón de agujeros ISO 15552 (TG
    38 / 56,5 / 89 = Ø40 / Ø63 / Ø100), «not suitable for dynamic operation», «not certified for
    use in safety-related control systems»;
  - **KEC-…-S**: las mismas cifras con trabajo 3,8–8 bar y prueba 10 bar, «Holding and stopping a
    movement», **categoría 1 de EN ISO 13849-1, PL c, certificado IFA 1504155**, «not a complete
    safety solution»; el sobrerrecorrido «must be determined by the customer» y se acorta con un
    escape rápido en su puerto;
  - **KPE** (Ø4–32): KPE-12 600 N, liberación 3 bar, M5, sólo estático, sin certificar;
  - la nota que descarta la alternativa más barata: «Blocking off the compressed air supply at
    both ends (e.g. with a 5/3-way valve) does not provide any safety»; y «may only be released
    when the forces on the round material are balanced»;
  - las cotas (B f8, E, L1, L2, VD, TG, RT, MM) se leyeron SIN su dibujo: B 35/45/55 coincide con
    el centrado ISO 15552 de Ø40/Ø63/Ø100 y TG con su patrón; lo demás va en `a_confirmar`.
- **[B2] Festo, hojas de artículo 527493 (KEC-20) y 538242 (KEC-16-S)** (2020/09, mismo sitio):
  confirman 3200 / 1300 N, 3,8 bar, 4515 / 1860 g, G1/4 / G1/8, −20…80 / −10…60 °C, «Kat. 1, PLc».
- **[B3] SMC, catálogo CNA2 (cilindro con bloqueo)** (`https://content2.smcetech.com/pdf/CNA2.pdf`):
  Ø63 2160 N de retención, desbloqueo ≥ 0,25 MPa y bloqueo desde ≤ 0,20 MPa, hasta 1000 mm/s
  dentro de su energía admisible; «there is a momentary lag … a time delay occurs before
  stopping» y la válvula de liberación con ≥ 50 % del área efectiva de la del cilindro y más
  cerca de él. Es la alternativa del cilindro con bloqueo integrado (F4).
- Ninguna de las tres publica el **tiempo de bloqueo ni el de liberación** ni un **B10d**: dicen
  que el retardo depende de la válvula de liberación, el tubo y la carga. De ahí D4.
- Del código: `cosim/neumatica/red.py` arma la cadena de cada cámara (`_camara`) caminando los
  tubos hasta una vía de trabajo de válvula; la misma caminata sirve para la línea de liberación.
  `services/cosim_aire.dispositivos` arma la ficha plana de cada aparato de aire: ahí se le dice al
  bloqueo cuál es su cilindro. `library/neumatica/erc.py` tiene 492 líneas: la regla nueva va en su
  propio módulo.

## Decisiones (para vetar)

- **D1. Familia del catálogo «bloqueo de vástago», ficha `neumatico:` de tipo nuevo
  `bloqueo_vastago`.** `library/data/135_bloqueos_vastago.yaml` (categoría
  `bloqueos_vastago`), siete refs por FUNCIÓN: `BLOQ-VAST-16-S`, `-20-S`, `-25-S` (del orden de
  Festo KEC-…-S: frenan un movimiento, categoría 1), `BLOQ-VAST-16`, `-20`, `-25` (del orden de
  KEC: sólo sostienen) y `BLOQ-VAST-12` (del orden de KPE-12: sólo sostiene, sin patrón ISO
  15552). La ficha (`ficha_tipos.REQUERIDOS["bloqueo_vastago"]`, completa o no carga) lleva Ø del
  vástago, retención estática, presión mínima de liberación, presiones de trabajo,
  `normalmente_bloqueado`, `frenado_dinamico`, volumen de la cámara de liberación y retardo
  mecánico; opcionales: `categoria_iso13849`, `PL`, `certificado`, `B10d`, `holgura_axial_mm`,
  `cilindro_D_mm`. Puerto `1` de liberación (rol `entrada`, la rosca de la ficha). Designación
  **-RL** (provisoria, a confirmar con IEC 81346-2, como las demás del aire). Builder propio
  (`library/builders_bloqueo.py`): cuerpo prismático E × E × L2, el centrado Ø B × VD y el
  agujero pasante del Ø EXACTO del vástago (contacto intencional, nunca holgura inventada); anclas
  `vastago` (eje), `cara_cilindro` y `cara_carga`. Con `cost`: no (no hay precio con fuente).
- **D2. Se declara en el `servicio` del cilindro: `servicio.bloqueo` = la designación del
  dispositivo de bloqueo** («-RL1»). El bloqueo es un `add_device` aparte (tiene aire, numeración
  y lugar en el esquema). Default `None` = sin bloqueo: un log viejo regenera igual y su `servicio`
  guarda las mismas claves (`model_dump` sin `None`). El evaluador del carril no puede validar la
  designación (el bloqueo puede declararse después); lo hace el ERC con «¿quisiste decir…?».
- **D3. La liberación es una 3/2 NC monoestable PROPIA, con la bobina en la cadena de la seta.**
  El tubo va de su vía 2 al puerto 1 del bloqueo; su vía 1, aguas abajo del corte con escape; su
  escape 3, con silenciador (o un escape rápido, F2). Al cortar la bobina (seta, corte de energía)
  el muelle la devuelve a 2→3 y el bloqueo muerde. Liberar desde la red (sin válvula) no cumple:
  la seta no lo descarga. La co-simulación rechaza (`ModeloIncompleto`) una línea de liberación que
  no llega a la vía de trabajo de una válvula (p. ej. la de alimentación); que esa válvula sea una
  3/2 NC propia lo juzga el ERC (D6).
- **D4. Co-simulación: una cámara de liberación y una fricción seca en la junta.**
  - La cámara de liberación es de volumen FIJO (`V_liberacion_cm3` de la ficha + los tubos de su
    línea), con la misma politrópica, los mismos caminos de ISO 6358 y los mismos 8 sub-pasos que
    una cámara del cilindro (`cosim/neumatica/bloqueo.py`). El retardo del bloqueo SALE del
    escape real por la 3/2 y su silenciador (lo que dicen las tres fichas), no de una cifra.
  - Fuerza de sujeción F(p) = F_ret · (1 − p / p_lib), recortada a [0, F_ret]: el muelle contra
    el pistón de liberación (el corte de la ficha [B1]), lineal entre 0 y la presión mínima de
    liberación. Hipótesis declarada en el resultado; no pide una «presión de bloqueo» que Festo no
    publica (la de SMC, 0,20 MPa, es de otro producto).
  - El retardo mecánico de las mordazas (`t_mecanico_ms`, criterio de diseño en `a_confirmar`):
    la sujeción entra cuando la presión ya bajó de p_lib durante ese tiempo; sale en el acto al
    volver la presión.
  - A MuJoCo va como **fricción de Coulomb** sobre la junta del vástago (`dof_frictionloss` =
    sellos + F(p)), por `AcopleMecanico.control`: la lección del atasco (V8.3 D8). Con la fuerza
    neumática residual bajo la retención la junta se traba y |v| → 0; si la supera, desliza con
    la diferencia.
  - **Mientras muerde, la restricción de fricción de esa junta se endurece** (`dof_solref` 2 ms
    —≥ 2·Δt— y `dof_solimp` d = 0,9995; al soltar vuelve la de la junta). Medido en el banco: con
    la de MuJoCo por defecto (20 ms, d 0,95) la fricción seca es BLANDA y el vástago se arrastraba a
    ~40 mm/s con 600 N contra 3200 N de sujeción (69 mm en 1,5 s); endurecida, 0,04 mm en 1,5 s.
    Criterio de simulación declarado en la hipótesis del resultado.
  - Señales: `-RL1.p_bar`, `-RL1.F_N` (la sujeción que aplica), `-RL1.bloqueado` (mordazas
    cerradas), `-RL1.desliza` (bloqueado y |F neumática| > F) y `-RL1.sobrerrecorrido_mm` (lo que
    anduvo el vástago desde que mordió: el dato que Festo pide medir en la puesta en marcha).
- **D5. El deslizamiento es un evento del escenario y la verificación lo marca.**
  `services/aire_resultado.resumen_aire` guarda por bloqueo `{deslizo, t_desliza_s?,
  sobrerrecorrido_mm, F_max_N}` en `resultado.aire.bloqueos` (sólo si hay bloqueos: el compacto de
  siempre sin ellos). El ERC marca ROJO el bloqueo que deslizó en un escenario VIGENTE y sano.
- **D6. ERC y memoria: regla «bloqueo de vástago»** (`library/neumatica/erc_bloqueo.py`, puro):
  - `servicio.bloqueo` que no es un dispositivo de tipo `bloqueo_vastago` (error, con la parecida);
  - el Ø del vástago de la ficha ≠ el del cilindro (error);
  - **retención estática ≥ 1,0 × la fuerza máxima del cilindro** (error): F = p · A de avance (la
    mayor) a la presión MÁXIMA que le llega (la regulada; sin FRL, la máxima de la ficha del
    cilindro). El factor 1,0 es el de la ficha [B1] («dynamic forces … must not exceed the static
    holding force»); el FS sale en el `calc`;
  - **normalmente bloqueado** (error si la ficha dice que no: sin aire no sostendría);
  - **frenado dinámico** (error si la ficha es sólo estática): su liberación la corta la seta en
    marcha, así que muerde un vástago en movimiento; la ficha [B1] dice que el KEC no es para eso;
  - presión que llega ≥ la mínima de liberación (error: muerde a medias y arrastra);
  - **la liberación es una 3/2 NC propia** (error si no) y **la corta la seta**: «ok» si toda
    llegada de tensión a su bobina pasa por el NC de una seta o por un contacto de un aparato que
    sólo se energiza a través de ella (`library/electrico/cadena_seta.py`, sobre `Llegada.via`);
    «aviso» si la bobina se alimenta sin pasar por la seta (p. ej. de una salida del PLC: depende
    del programa, no es la cadena cableada que pide la categoría 1);
  - el deslizamiento medido (D5, error);
  - la memoria suma la fila de la retención con su `calc` y la hipótesis de ISO 13849 (D7). Sin
    ningún `servicio.bloqueo` ni dispositivo de bloqueo, ERC y memoria dan lo de antes.
- **D7. ISO 13849, lo que dice la ficha y nada más.** La KEC-S es un componente probado para
  categoría 1, PL c, con el certificado IFA 1504155 [B1][B2]; la KEC y la KPE no están
  certificadas. El **B10d no lo publica ninguna ficha leída**: queda en `a_confirmar` y la memoria
  lo dice. No se calcula el PL del lazo (la seta, la 3/2 y su cableado son de la OBRA).
- **D8. Vigencia.** `COSIM_EPOCH` queda en **9**: un escenario sin bloqueo no cambia de huella (el
  acople no toca la fricción si nadie la pide; se prueba con el banco del empujador). Sí cambia la
  huella del código (`tests/test_cosim_epoch.py`). `GEOM_CACHE_EPOCH` no sube (builder y refs
  nuevos). Ninguna `version` de comando: `add_device` es del carril; `CAMPOS` suma
  `servicio.bloqueo`. Un documento que declara un bloqueo cambia su log y su firma: sus
  escenarios vencen (lo correcto).
- **D9. Esquema ISO 1219: provisorio.** El bloqueo sale como aparato suelto con su designación y
  el rectángulo genérico de `drawing/neumatica/composicion._suelto`; su símbolo de ISO 1219-1 (la
  unidad de sujeción) va en F3, a confirmar con la norma.
- **D10. En 3D va entre la tapa delantera del cilindro y su brida** (KEC: patrón TG de ISO 15552 y
  centrado Ø B): el vástago tiene que ser más largo en L1 (a confirmar con el fabricante del
  cilindro). Colocarlo en la faja es F2, por MCP.

## Alternativas descartadas

- **5/3 de centro cerrado** (las dos cámaras bloqueadas): la ficha [B1] dice que no da seguridad;
  una fuga o la compresibilidad dejan mover el vástago.
- **Válvulas de retención pilotadas en las dos cámaras**: misma objeción, más tubos y ninguna
  ficha que publique la retención.
- **Cilindro con bloqueo integrado** (SMC CNA2, Festo DSBC-C) en vez de un accesorio: es la mejor
  pieza para una máquina nueva, pero reemplaza el cilindro ya diseñado; queda como F4 (otra ref de
  cilindro con la misma ficha de bloqueo).
- **El bloqueo como campo del `servicio` sin dispositivo** (el patrón del amortiguador): no
  tendría puerto, ni línea de liberación, ni lugar en el esquema; la co-simulación no podría saber
  cuándo pierde el aire.
- **El bloqueo como `servicio` del propio dispositivo de bloqueo** («qué cilindro muerde»): el
  `servicio` sólo vale en un cilindro y el ERC lee al cilindro; un campo del cilindro es más corto
  para el PATCH de `edit_command`.
- **Umbral binario de presión** («bloquea bajo p_b»): pide una cifra que Festo no publica; la
  recta muelle-pistón usa sólo las dos de la ficha.
- **Imponer x = cte en MuJoCo al bloquear**: perdería el deslizamiento, que es lo que se quiere ver.
- **Una fuerza explícita contraria a v** (`qfrc_applied`): vibra cerca de v = 0 (la lección del
  atasco, V8.3 D8).
- **Un tiempo de bloqueo fijo de ficha**: ninguna lo publica; el retardo depende del escape, que
  la co-simulación ya calcula.
- **Liberar desde la red con un presostato que pare el PLC**: la seta no descarga la línea.

## Fases

| fase | qué | paquete | tamaño | depende de | se verifica con |
|---|---|---|---|---|---|
| F0 | leer las fichas Festo y SMC y hacer la cuenta de la faja a mano (sólo lectura) | — | S | — | § Bitácora F0 |
| F1 | D1–D8: familia, builder, ficha, `servicio.bloqueo`, modelo y acople en la co-simulación, resumen del escenario, regla del ERC con la cadena de la seta, memoria | library, commands, cosim, services | L | F0 | `tests/test_bloqueo_vastago.py` y `tests/test_bloqueo_vastago_cosim.py`; suite completa y ruff |
| F2 | la faja con desviador: un modelador por MCP pone `BLOQ-VAST-20-S` entre el Ø63 y su brida, su 3/2 NC con silenciador en la cadena de la seta y `servicio.bloqueo`; re-corre `seta_desvio` | modelo (MCP), sin código | M | F1 mergeada | el vástago queda quieto tras la seta (|v| ≈ 0, sobrerrecorrido medido), ERC verde, revisión a ciegas |
| F3 | el símbolo ISO 1219-1 del bloqueo en el esquema y su fila en el panel «Neumática» | drawing, services, ui | M | F1 | `test_simbolos_iso1219.py`, vitest, revisión de diseño |
| F4 | cilindro con bloqueo integrado (SMC CNA2 / Festo DSBC-C) como ref; una ficha que publique tiempos de bloqueo y B10d; quitar lo confirmado de `a_confirmar` | library (YAML) | S | — | el test de la ficha con la nueva fuente |

## Lo que este plan NO hace

- Calcular el PL del lazo de la seta (ISO 13849-1): la seta, la 3/2 y el cableado son de la obra;
  sólo se dice la categoría que la ficha certifica.
- Simular el desgaste de las mordazas (el sobrerrecorrido que crece con los frenados, [B1]).
- Escape rápido en el puerto del bloqueo (la ficha lo recomienda): el catálogo no lo trae; F2 lo
  puede sumar si el sobrerrecorrido medido lo pide.
- Juzgar el sobrerrecorrido: se mide y se publica (Festo pide medirlo en obra).
- Precio: las refs no traen `cost` (sin fuente).

## Riesgos

| riesgo | mitigación |
|---|---|
| La recta F(p) y el retardo mecánico no son de ficha | hipótesis en el resultado y `a_confirmar`; el retardo dominante es el escape, que sí se calcula |
| La fricción blanda de MuJoCo deja un arrastre mínimo con la fuerza bajo la retención | el test exige |v| < 1 mm/s y < 1 mm de corrimiento tras el bloqueo; si la física lo infla, se mide |
| La cadena de la seta por `Llegada.via` no ve la lógica de un relé de seguridad | un aparato cuyas cargas (bobina o entrada) sólo llegan por la seta cuenta como cortado; lo demás, «aviso», nunca «ok» inventado |
| El vástago del cilindro no alcanza con el bloqueo intercalado | D10: lo dice la nota de la ref; F2 lo resuelve con el fabricante |
| Cotas leídas sin su dibujo | `a_confirmar`; la interfaz (TG, Ø B, Ø del vástago) es coherente con ISO 15552 |

## Bitácora

### F0 — las fichas y la cuenta a mano (2026-10-26)

- Fichas [B1]–[B3] leídas (§ Lo que se revisó). Ninguna publica tiempos de bloqueo ni B10d.
- La faja (Ø63 × 800, vástago Ø20, red a 6 bar, 25,4 kg de masa móvil con la placa):
  - fuerza máxima del cilindro: p · A = 0,6 MPa · 3117 mm² = **1870 N** (a 8 bar, el tope de la
    KEC-S, 2494 N);
  - `BLOQ-VAST-20-S` (KEC-20-S): 3200 N ⇒ FS = 3200 / 1870 = **1,71** ≥ 1,0; a 8 bar, 1,28;
  - en la seta a 0,716 m/s: E = ½ · 25,4 · 0,716² = 6,5 J; con la fuerza residual bajo 1870 N la
    neta que frena es ≥ 1330 N ⇒ ≤ 4,9 mm de frenado una vez que muerde (más lo que anda mientras
    se descarga la liberación: lo mide la co-simulación);
  - `BLOQ-VAST-16-S` (1300 N) no entra en un Ø63 (ni el Ø del vástago ni la retención: 0,70).

### F1 — familia, declaración, co-simulación y ERC (2026-10-26, base baba86d)

En un worktree propio (laptop). Sin API, sin `data/`, sin UI.

**Lo hecho** (D1–D8 tal cual, salvo lo que dice «cambió»):
- Ficha: `ficha_tipos` gana el tipo `bloqueo_vastago` (designación RL, puerto 1 `entrada`) y
  `ficha._coherencia` exige p_mín ≤ p_lib < p_máx. Catálogo `135_bloqueos_vastago.yaml` (7 refs,
  462 → 469) con [B1]/[B2] citadas por página; builder `builders_bloqueo.py` registrado en
  `loader.py`.
- Declaración: `ServicioCilindro.bloqueo` (default `None`; `CAMPOS` lo suma). `services/cosim_aire`
  le pone a la ficha plana del bloqueo el `cilindro` que lo nombra.
- Co-simulación: `cosim/neumatica/bloqueo.py` (`BloqueoVastago` en `MODELOS_AIRE`), su cámara en
  `RedAire` (la caminata `_camara(des, "1")`), `RedAire.frenos` y la sujeción como fricción en
  `AcopleMecanico.control`; `Corrida.intercambio` pasa `frenos`.
- Cambió (D4): la restricción de fricción se endurece mientras muerde (§ D4). Primer intento sin
  endurecer: el vástago bajo 600 N residuales contra 3200 N de sujeción se arrastró 69 mm en 1,5 s
  (~40 mm/s). La causa: la fricción seca de MuJoCo es una restricción BLANDA (solref 20 ms, d 0,95)
  y el arrastre escala con (1 − d)·tc; el atasco del motor (V8.3) nunca lo midió con carga
  sostenida. Endurecida sólo en esa junta y sólo mientras muerde: 0,04 mm en 1,5 s.
- `services/aire_resultado.resumen_aire` guarda `bloqueos` (sólo con bloqueos);
  `services/neumatica.reglas` pasa `seta` (la cadena de `library/electrico/cadena_seta.py`) y
  `deslizados` (escenarios vigentes, sin los de ajustes de prueba) al ERC; la memoria suma la fila
  de la retención.
- ERC: `library/neumatica/erc_bloqueo.py` (la regla), `bloqueo.py` (la cuenta); `erc.py` llega a
  496 líneas con el gancho.

**Medido** en el banco (`tests/bloqueo_escena.py`: Ø63 × 400, placa de 250 × 150 × 40, 5/3 de
centro a escape, escape de la A con C 0,15 y de la B con C 0,6, red a 6 bar, seta a 0,9 s con el
vástago a ~243 mm y avanzando):
- sin bloqueo: el vástago sigue hasta el tope (400 mm) con la A todavía a ~4 bar (el caso real);
- con `BLOQ-VAST-20-S`: muerde a 0,932 s (32 ms: los 22 ms de la 3/2, el escape de la liberación y
  los 10 ms de las mordazas), a 244,5 mm; |v| < 1 mm/s después y 0,04 mm de arrastre en 1,5 s
  aunque la A empuja hasta 880 N;
- con la sujeción bajada a 150 N (prueba): `desliza` se enciende y el vástago sigue andando;
- 5 escenarios sin bloqueo (empujador sano, corte de aire, biestable, presostato y el desviador
  con la seta) dan la MISMA huella, finales, hipótesis, avisos y eventos que en baba86d (corridos
  con un `git archive` de la base): `COSIM_EPOCH` sigue en 9; sólo cambia la huella del código.
- ERC del banco: verde (FS 1,71, la corta la seta por -S0:11-12); por un relé -K1 que la seta
  corta, verde; con la bobina directo de la fuente, aviso; KEC sin -S, rojo; 3 bar en la red, rojo
  (y la regla de presión de siempre); sin 3/2, rojo; Ø32 a 8 bar con el KPE-12, rojo (643 contra
  600 N).
- Tests: `tests/test_bloqueo_vastago.py` (24 casos: fichas, builder, declaración, ERC verde/rojo/aviso,
  memoria, el modelo sin MuJoCo, el resumen) y `tests/test_bloqueo_vastago_cosim.py` (5: sin
  bloqueo al tope, con bloqueo quieto, retención insuficiente desliza, sin bloqueo la junta
  intacta, bit a bit). Ajustados a propósito: los conteos del catálogo (462 → 469 en tres tests y
  463 → 470 el de la extensión), el conjunto de anclas por familia (`test_catalog_cadenas`), el
  inventario de modelos de aire (`test_cosim_modelos_catalogo`, que ahora pasa el `cilindro`),
  `CAMPOS` de `add_device` y la huella de `test_cosim_epoch`.
- La primera corrida de la suite dio esos 6 rojos esperados (conteos, anclas, el modelo de aire
  sin `cilindro`). Suite completa (laptop, `-n 4`, `PYTHONPATH` del worktree, `--basetemp
  C:\t\bt-bloqueo`): exit 0, sin FAILED. `ruff check core tests scripts`: limpio. Ningún archivo
  pasa de 500 líneas (`erc.py` 496).
- Vigencia: `COSIM_EPOCH` 9 (medido arriba), `GEOM_CACHE_EPOCH` igual (builder y refs nuevos),
  ninguna `version` de comando.
