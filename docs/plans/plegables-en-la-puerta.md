---
estado: en curso
nota: contrato aprobado por Claude (delegado por Mario, 2026-10-30); falta todo desde la F0. La escalera de la F5 espera la F5 de puerta-fuera-de-catalogo (raíz del patrón)
descripcion: La puerta revisa que lo que se pliega se pliegue de verdad en el modelo, recorra sin chocar, quede del tamaño pedido y se trabe abierto
---

# La puerta revisa que lo plegable se pliegue y se trabe

## Estado y origen

Contrato escrito y aprobado por Claude con la delegación de Mario (2026-10-30: «crea los planes, los apruebas tú y lo implementas, te doy permiso»); las D siguen vetables por él.

Lo manda a plan aparte [puerta-fuera-de-catalogo](puerta-fuera-de-catalogo.md) § «Lo que se revisó»
(contrato aprobado por Mario el 2026-10-30): «productos plegables (juntas no declaradas,
sobre-centro) se repiten en […] 3 máquinas, pero […] piden su propio análisis de mecanismo: van con
plan aparte». Rigen sus dos reglas: la calidad en código determinista y la regla general. Aquí
«plegable» es **cualquier mecanismo con una posición de uso y una de guardado** (se pliega, se cierra,
se recoge), no una familia: escalera, mesa, silla, tapa abatible, rampa.

Evidencia: la tanda de 15 máquinas re-evaluada con la puerta v32 trae 3 plegables (escalera de tijera
de 7 peldaños, mesa plegable de madera de 1,8 m, silla plegable alta), cada una con su piloto mínimo
anterior (escalera de 3 peldaños, mesa de 1,2 m, silla baja). **Ninguna de las tres aprueba**, y el
revisor a ciegas no pudo revisar el plegado en ninguna: «no pude posar la escalera cerrada», «el
modelo no tiene juntas (`get_kinematics` vacío)».

## El problema / lo que hay hoy

### Lo que vio el revisor y lo que dijo la puerta

1. **Se pliega en la ficha, no en el modelo.**
   - Mesa de 1,2 m, revisor, ALTA: el compás era una pletina recta empernada a pata y larguero y
     «`get_kinematics` devuelve joints=[] […] la pata no se puede plegar».
   - Escalera de 3 peldaños, revisor, ALTA: tirante rígido empernado a los dos tramos, «la escalera
     no se pliega sin desarmar las tuercas con llave».
   - Silla alta: sin juntas en las tres re-revisiones. El modelador probó el plegado «moviendo los
     grupos y corriendo `check_interference`» y reportó que «queda abierto» contra el brazo, «el
     hallazgo principal» (modelado). La puerta v32 da `movimiento.coherente` **NO_APLICA** («sin
     juntas que muevan piezas»): no sabe que la silla debía plegarse.
2. **Lo que pliega junto no está unido a lo que lo pliega.** `movimiento.coherente` FALLA en dos:
   - escalera de 7: 8 uniones peldaño trasero ↔ larguero (c152_3–c152_6): al mover `j_plegado` 3°
     el peldaño se queda y el larguero entra en él (8 133–10 181 mm³). Causa, del modelador:
     «`add_joint` con un hijo copia de patrón rompe la familia […] da “No existe c152_3”. Tuve que
     borrar esas juntas» (modelado). Es el modo 7 de puerta-fuera-de-catalogo (su D9);
   - mesa de 1,8 m: 4 «alojamiento arrastrado» brazo superior del compás ↔ buje separador (c301–c304
     ↔ c375–c378). Hipótesis a confirmar en la F0: el buje está en el pivote que CIERRA el lazo del
     compás, que no es una junta del árbol, así que la regla de la bisagra no lo ve coaxial.
3. **La posición de uso no se traba.**
   - Escalera de 3, re-revisión 1, ALTA: el tirante con gancho sale «levantando el tirante unos
     21 mm […] No tiene seguro ni traba».
   - Escalera de 3, re-revisión 3, MEDIA: «el codo queda alineado con los dos pivotes […] no hay
     sobre-centro. Si el tirante trabaja a compresión […] la escalera se pliega».
   - Los modeladores lo resolvieron a mano y bien: sobre-centro de 2° con pasador tope a 0,12 mm
     (escalera de 7, modelado), pletina tope doblada 2,3° «igual al ángulo de sobrecentro de la
     rodilla» (mesa de 1,8 m, corrección 3), calzo de tope de apertura y el peso de la persona (silla
     baja, modelado). Ningún ítem de la puerta lo pide ni lo mide.
4. **El pivote del pliegue no es un pivote.** Mesa de 1,8 m, re-revisión 2, MEDIA: remaches ciegos
   DIN 7337 como pivotes del compás: «prensa las chapas: la articulación queda dura o […] se ovaliza».

### Lo que hay en el código (`main` 29ca3925)

- **Ningún requisito dice que algo se pliega.** `requisitos.py` tiene `higienico` como interruptor
  de ítems (`library/requisitos.py:66-69`) y las numéricas de `:23-33`; nada sobre posiciones.
- **Las juntas de servicio existen** (`services/calidad_juntas.py:1-17`): una bisagra que mueve la
  mano. Su límite por defecto es ±180 (`commands/models_ensamblaje.py:41-42`): no dicen dónde está
  el tope.
- **`movimiento.coherente`** (`library/calidad/movimiento.py:11-31`) juzga uniones rígidas entre
  piezas que mueven juntas distintas, con la prueba de pose de 3° o 3 mm
  (`services/calidad_movimiento.py:36-38,95`). Sin juntas, NO_APLICA (`movimiento.py:159`). El lazo
  que la FK no representa («el compás de una mesa plegable», `movimiento.py:27-28`) es aviso
  justificable sólo si la pose SEPARA; la regla del alojamiento arrastrado va antes y falla.
- **El lazo cerrado ya se puede declarar**: `add_constraint` `punto_coincidente`
  (`commands/models_ensamblaje.py:109-131`, `assembly/constraints.py:78-84`) y `solve_constraints`
  resuelve las juntas dependientes (`constraints.py:93-141`). El punto de referencia es FIJO en el
  mundo (`constraints.py:51-56,78`): cierra un lazo contra la pieza raíz, no entre dos cuerpos que se
  mueven. Si el solver no converge, deja los valores libres sin avisar (`constraints.py:140-141`).
- **Las poses de reposo ya se revisan**: `delivery_poses` posa los fotogramas extremos y las
  esperas de cada estudio y busca choques (`services/assertions.py:214-237`); el TRÁNSITO «se valida
  con scan_motion», que la puerta no corre (`robotics/motion.py:39-79`). Sin estudios, no aplica
  (`assertions.py:239-240`).
- **El fotograma no admite etiqueta**: `set_motion` rechaza toda clave que no sea `t` o `values`
  (`doc/metadatos.py:104-109`).
- **El eje de giro ya se exige trabado** (autoblocante, contratuerca o retén) y no tirafondo
  (`library/ejes_giro.py:7-17`); un remache ciego no está en la lista, y la tornillería de remachadora
  no entra a la medición de pernos (`services/calidad_pernos.py:71-72`).
- **La FK sólo posa ejes alineados con X, Y o Z** (`robotics/pose.py:3-6`).

## Lo que se revisó antes de escribir esto

- Los reportes de modelado, corrección, revisor y re-revisión de las 3 plegables y de sus 3 mínimos,
  y el ítem `movimiento.coherente` de la puerta v32 de las 15.
- `tensores` es el precedente de «se declara, la puerta lo mide» (`doc/document.py:75`, REST en
  `api/routers/validation.py:202-218`), pero no tiene tool del MCP; `set_motion` sí, y recibe
  `list[dict]` (`tools/introspeccion.py:201`): una clave nueva en el fotograma no cambia su firma.
- La pose de diseño puede ser la de uso o la de guardado: el modelo no lo dice hoy.
- La resistencia de la traba (pandeo del compás: «FS ≈ 1,2», mesa de 1,8 m, revisor MEDIA) y del
  pivote (bisagra de barril Ø4 que «lleva el cortante», escalera de 7, re-revisión 1, ALTA) es
  cálculo de pieza: va con la F4 de puerta-fuera-de-catalogo, no aquí.

## Decisiones (para vetar)

- **D1. Un requisito dice que el producto tiene posición de uso y de guardado**: `plegable` (sí/no,
  por defecto no), como `higienico`. Con él aplican los ítems de este plan; sin él, NO_APLICA como
  hoy. Lo pide la ficha del encargo (`COMO_FICHA`) junto a `desarmable`. Porqué: la puerta no puede
  adivinar por el nombre que «Silla plegable» se pliega (nombres por rol, no por palabra), y sin
  requisito la silla sin juntas pasa.
- **D2. Las posiciones son fotogramas etiquetados de un estudio de movimiento**: el fotograma acepta
  `posicion: "uso" | "guardado"` (`set_motion` deja de rechazar esa clave; un manifest viejo no la
  tiene y abre igual). Con `plegable`, el ítem nuevo `plegado.posiciones` pide al menos un estudio con
  las dos posiciones, sus valores dentro de los límites de cada junta y al menos una junta que cambie
  entre ellas. Sin eso → FALLA «el producto se pliega en la ficha y no en el modelo» (silla alta,
  mesa de 1,2 m, escalera de 3).
- **D3. El plegado recorre sin chocar y el guardado mide lo pedido.** La puerta corre
  `scan_collisions` sobre el tramo uso → guardado del estudio (pasos acotados; la F0 mide el costo con
  `process_time`) además de las poses de reposo que ya revisa la entrega; un choque en el tránsito
  FALLA con el instante y el par. Publica la caja del guardado; con el requisito nuevo
  `espesor_plegado_mm` (en `NUMERICAS`), la menor dimensión de esa caja mayor que lo pedido → FALLA
  (la silla alta, que «queda abierta» contra el brazo).
- **D4. El lazo del mecanismo se declara y su pivote cuenta como eje.** El pivote que cierra un lazo
  (el compás contra el faldón, el tirante contra la pata delantera) se declara con `add_constraint`
  `punto_coincidente`, no con un `fasten` rígido. `movimiento.coherente` toma ese punto y la normal del
  pivote como un eje más: una pieza coaxial con él (el buje separador) es bisagra, no alojamiento
  arrastrado. Si `solve_constraints` no cierra el lazo en una pose (residuo > 0,5 mm), esa pose sale
  SIN_EVALUAR, nunca OK. Los peldaños copia de patrón de la escalera dependen de la D9 de
  puerta-fuera-de-catalogo (la raíz del patrón acepta `add_joint`).
- **D5. La posición de uso se traba en los dos sentidos de cada junta que pliega.** El fotograma de
  `uso` declara sus `trabas`: `[{junta, sentido: "+"|"-", tipo, piezas, nota}]`, y la puerta mide
  cada una (ítem nuevo `plegado.traba`):
  - `tope`: con la junta movida 3° o 3 mm en ese sentido desde el uso (la prueba de pose de
    `calidad_movimiento`), el volumen común con la pieza tope crece más que `TOL_VOL_MM3` (lo
    bloquea);
  - `sobre_centro`: la rodilla del lazo pasa la recta de sus dos pivotes extremos al menos el ángulo
    de D6, hacia el lado de su tope, y ese tope existe (se mide como `tope`). Los pivotes salen de los
    orígenes de las juntas posados y del punto de la restricción de D4;
  - `retenida` (pasador, gancho, cerrojo): la pieza de retención existe y toca el pasador o el gancho,
    reconocida por el rol de los retenes de `ejes_giro` (pasador de aletas, clip R, anillo); un gancho
    sin retén FALLA (la escalera de 3);
  - `peso` (la persona sentada cierra la tijera): AVISO justificable por escrito, no OK.

  Una junta que pliega con un sentido sin traba declarada, o con la traba que la medida no confirma,
  FALLA. Las juntas que no cambian entre uso y guardado no cuentan.
- **D6. El sobre-centro mínimo es 2°** (criterio de diseño: los dos modeladores que lo resolvieron
  usaron 2° y 2,3° y el revisor pidió «2–3°»). La F0 busca fuente (EN 131-1/-2 para escaleras,
  EN 1730 para mesas, fichas de compás plegable); si no la hay, queda escrito en el código como
  criterio de diseño.
- **D7. Un remache ciego no es eje de giro**: `ejes_giro` lo agrega a lo que no es pivote (como el
  tirafondo), con la salida de mercado en el mensaje (remache de hombro, perno de hombro ISO 7379 con
  tuerca autoblocante). Vale para todo eje de junta, no sólo plegables.
- **D8. Cada fase que cambia lo que la puerta decide sube el registro**, con su línea en
  `historial_registro.py`; una máquina aprobada con un registro anterior vuelve a correr la puerta
  antes de publicarse (D10 de puerta-fuera-de-catalogo).

## Alternativas descartadas

- **Detectar el plegable por el nombre** («plegable», «tijera», «compás»): frágil y contra la regla
  de leer por rol; el requisito lo dice el encargo.
- **Un metadato `trabas` aparte, como `tensores`**: separa la traba de la pose que traba y necesita
  tool nueva del MCP; `set_motion` ya existe y su firma no cambia.
- **Detectar la traba sin declararla** (buscar cualquier contacto en el uso): un contacto de diseño
  no dice en qué sentido bloquea ni distingue tope de sobre-centro; declarar y medir es lo que hace el
  tensor.
- **Simular la carga con MuJoCo para ver si se cierra**: caro, y la rodilla en sobre-centro es
  geometría pura; queda para cuando la co-simulación lo necesite.
- **Una tolerancia para que `movimiento.coherente` deje pasar el buje del compás**: taparía el caso
  real de la chumacera arrastrada; el pivote del lazo, declarado, es la información que falta.

## Fases

- **F0 — medir** (sólo lectura, S). Las 3 plegables y sus 3 mínimos: confirmar la hipótesis del buje
  (D4), cuántas juntas pliegan, qué trabas tendrían que declarar y qué decidiría D5 con ellas; el
  ángulo de rodilla medido en la escalera de 7 y la mesa de 1,8 m; el costo de `scan_collisions` por
  paso en la mesa de 1,8 m; fuentes de D6. Ajusta D1–D7 (vetable).
- **F1 — posiciones** (`library/requisitos`, `doc`, `services`, `library/calidad`, M). D1, D2, D3 +
  tests: manifest viejo sin `posicion` abre igual; `set_motion` acepta `posicion` y sigue rechazando lo
  demás; silla sin juntas FALLA con `plegable`; choque en tránsito y espesor de guardado. Cambia el
  formato del fotograma (clave opcional): sin bump de la caché de geometría (el estudio es metadato).
  Registro +1.
- **F2 — el lazo en `movimiento.coherente`** (`services`, `library/calidad`, S). D4 + tests con el
  compás de la mesa de 1,8 m (fixture) y la chumacera arrastrada que sigue fallando. Independiente de
  F1. Registro +1.
- **F3 — trabas** (`doc`, `services`, `library/calidad`, L). D5, D6 + tests: tope que bloquea y que
  no, sobre-centro de 2° y de 0°, gancho con y sin retén, `peso` justificado. Depende de F1 (la pose de
  uso) y de F2 (el punto del lazo). Registro +1.
- **F4 — remache ciego** (`library`, S). D7 + test. Independiente. Registro +1.
- **F5 — verificar** (S). Puerta del último registro sobre las 3 plegables, comparada con la F0 por
  ítem; la escalera de 7 después de la F5 de puerta-fuera-de-catalogo; una plegable re-hecha desde el
  encargo con la receta, para ver si el revisor ya puede posar el plegado.

F2 y F4 corren en paralelo con F1 (hasta 3 agentes a la vez); F3 espera a F1 y F2.

## Lo que este plan NO hace

- La resistencia de la traba, del pivote y de la bisagra del pliegue (pandeo del compás, cortante
  del pasador): F4 de puerta-fuera-de-catalogo o plan propio cuando ésta mida piezas sueltas.
- Puntos de pellizco y atrapamiento al plegar (EN 12520, ISO 13854): seguridad, plan aparte con su
  fuente.
- La masa que una persona pliega y carga (la escalera de 7 pesa 43 kg contra los 25 de EN 1005-2,
  re-revisión 1): requisito futuro.
- Lazos entre dos cuerpos que se mueven (el punto de `add_constraint` es fijo en el mundo) y juntas
  con eje fuera de X, Y o Z: SIN_EVALUAR justificable.
- Corregir las plegables de la tanda: es producción, después de la F5.

## Riesgos

- **El modelador no declara `plegable`** y todo sale NO_APLICA: la ficha del encargo lo pregunta y el
  revisor lo marca; la F5 mide si una plegable re-hecha lo declara sola.
- **El tránsito es caro** (`scan_collisions` hace interferencia OCCT por paso bajo `STATE_LOCK`):
  pasos acotados y medidos en la F0; si no entra en el presupuesto de la puerta, el tránsito pasa a
  `delivery_check` y la puerta lee su resultado.
- **Un tope por contacto de asiento da falso «bloquea»**: el crecimiento de volumen se mide sobre el
  de diseño con la tolerancia de la prueba de pose; tests con tope a 0,12 mm (el de la escalera) y
  con tope ausente.
- **`solve_constraints` no converge en silencio**: D4 lo convierte en SIN_EVALUAR; test con un lazo
  imposible.
- **Máquinas aprobadas que dejan de aprobar** (toda plegable sin trabas declaradas): es lo buscado;
  la F0 da el antes y la F5 el después.
