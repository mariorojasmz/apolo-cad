---
estado: en curso
nota: F0 medida (2026-10-30, bitácora) con ajustes a D1–D4 y a las verificaciones de F1–F2. MERGEADAS F4 (D5 = join_bolted criterio 8, D6 = $k en conjuntos), F1 (D1 movimiento.coherente, registro v28, D1c afinado y vetable), F2 (D2 union.contacto_no_cuelga, v30; D2c vetable = la nota del fasten declara la unión de tubería roscada o tri-clamp) y F3 (D4a la cinta sigue la banda modelada; D3a la catenaria de banda modular es tensado reconocido con Intralox, v31; la parte térmica queda SIN_EVALUAR justificable hasta tener la fuente del α)
descripcion: La puerta frena una pieza atornillada al bastidor que gira con un eje, un peso colgado de un simple contacto y la banda modular tensada por catenaria, y join_bolted deja de poner una cabeza dentro de un tubo
---

# La puerta ve lo fijo que gira y lo que cuelga de un contacto

## Estado y origen

Mario (2026-10-29), al ver en el visor una lavadora de bandejas de ~720 piezas simulando: «creo que
el motor está girando?, también su lado de chumacera?». Tenía razón, y la puerta de publicación
(registro v21) la había dejado pasar. Después pidió: «veo que sí amerita su plan para mejorar».

La máquina tomó 8 rondas de corrección. En ellas, lo que la puerta NO vio y vieron Mario o el
revisor a ciegas fue esto:

- **Lo fijo que gira (ronda 4).** La junta del eje motriz tenía como hija `fija` a la chumacera
  del lado opuesto, empernada a su ménsula. Además, un `contacto` chaveta ↔ reductor con
  `arrastrar` metía la carcasa del motorreductor en lo que gira. Al simular giraban motor y
  chumacera.
- **Lo que cuelga de un contacto (ronda 6).** Dos cuchillas de aire de 22 kg (56 kg con su
  ducto) colgaban sólo de una unión `contacto` (una abrazadera rápida), a ~555 mm de su centro de
  masa. La sujeción declarada las daba por sujetas.
- **La catenaria (todas las rondas).** La banda modular de acetal se tensa por su peso, con una
  zona de comba libre después de la rueda motriz, como piden los fabricantes. Sale SIN_EVALUAR en
  `transmision_flexible.tension` (tensor.reconocido / carrera / agarre: 0 de 1 lazos). Su
  animación tampoco sigue la comba modelada: `publicado.sustitutos_fieles` FALLA porque la cinta
  animada entra 50,8 mm en un larguero y el sólido de la banda, 0 mm.
- **`join_bolted` (ronda 8).** Una unión bajo un tubo cerrado dejó la cabeza del perno DENTRO
  del tubo (z 1904–1913), algo que no se puede montar. Con una chapa en Z falla con «falta cara
  PLANA ⊥ al eje X», porque el contacto se busca por solape de cajas. Y `fasten` rechaza `$k`
  dentro de un conjunto (`a: "$1+$2"`, 400).

## El problema / lo que hay hoy

- La FK mueve SÓLO los hijos declarados de cada junta (`robotics/pose.py::posed_shapes`), y
  `add_joint(arrastrar=true)` hace flood por los fijadores declarados, también los `contacto`
  (`commands/CLAUDE.md` § Juntas). Nada compara lo que mueve una junta con lo que está empernado o
  soldado a algo que no se mueve. `delivery_inputs.uniones_entre_juntas`
  (`services/delivery_inputs.py:49`) ya calcula los `fasten` cuyas piezas mueven juntas DISTINTAS,
  pero sólo para no tapar choques en pose; no lo juzga como contradicción.
- `loads.hanging_load_kg` (`library/engineering/loads.py:45`) da la masa que pierde tierra al
  quitar una unión, sin distinguir el tipo. La sujeción declarada (`check_assembly`, la puerta de
  entrega) cuenta un `contacto` como camino a tierra, igual que un perno o una soldadura. Un
  contacto transmite compresión (lo que APOYA), no tracción (lo que CUELGA).
- El tensor reconocido (`services/calidad_tensores.py`) son take-up, catálogo con `carrera_mm`,
  plantilla o metadato `tensores`. La catenaria de una banda modular no es ninguno de los cuatro.
- `join_bolted` busca el asiento por solape de cajas y exige una cara plana en el plano de apilado
  (`commands/exec_union.py:119`, `exigir_asiento`). No comprueba que la cabeza y la tuerca queden
  fuera del material.

## Lo que se revisó antes de escribir esto

- `services/calidad_ejes_giro.py` (hallazgos-del-revisor F5, mergeada hoy) ya sabe qué perno es
  EJE de una junta de giro: coaxial ± 1 mm y toca sus dos cuerpos. Ese perno no es una
  contradicción, es el pivote, así que D1 lo reusa en vez de reinventarlo.
- `services/calidad_contacto.py` y `kernel/contacto.py` miden la línea o el área de contacto de
  dos piezas: D2 toma de ahí dónde está el apoyo.
- `library/ruta_faja_modelo.py` y `fidelidad_faja.py`: la cinta animada es la línea media de la
  sección del sólido de la banda, con una comba = mín(CEMA 2 %, w·l²/8T, holgura) sólo en los
  tramos rectos del retorno. Una catenaria modelada más honda que eso queda fuera de la regla.
- `hallazgos-del-revisor-en-la-puerta` (en curso) no toca juntas, contactos colgantes ni
  catenaria: no hay solape.

## Decisiones (para vetar)

- **D1. Una unión RÍGIDA no une dos piezas que se mueven distinto.** Ítem nuevo
  `movimiento.coherente` (familia función):
  - un `fasten` perno o soldadura entre dos piezas que la FK mueve con juntas de movimiento
    distintas (`uniones_entre_juntas`, juntas giratoria/continua/prismática; las `fija` cuentan
    con su padre) FALLA con las dos piezas y la junta;
  - salvo que el perno sea el EJE de esa junta (`calidad_ejes_giro`) o el par se toque como
    pivote en la pose de diseño (la misma excepción `_se_tocan` de `uniones_entre_juntas`);
  - un `contacto` entre piezas que se mueven distinto no falla, porque es deslizamiento.

  Es el modo de falla «el modelo dice que gira algo que está atornillado al bastidor». No agrega
  piezas: se corrige la junta.
- **D2. Un `contacto` no sostiene lo que cuelga.** Ítem nuevo `union.contacto_no_cuelga`
  (familia estructura). Una unión `contacto` cuya carga colgada (`hanging_load_kg`) es > 0 y en
  la que el centro de masa de lo colgado queda DEBAJO del apoyo (zona de contacto medida, con una
  tolerancia que fija la F0) FALLA. Corrige: un apoyo debajo, una ménsula o un perno.

  Lo que apoya encima de un contacto (una bandeja sobre sus zapatas, un tanque sobre sus
  largueros) no cambia. Sin carga colgada (unión redundante) no se juzga.
- **D3. La catenaria de una banda modular es un tensado reconocido.** En
  `transmision_flexible.tension`, un lazo de banda modular (ref o designación de banda modular)
  con una zona libre después del motriz cumple si la comba modelada absorbe el alargamiento:
  térmico α·ΔT·L, más el de servicio que dé el fabricante. Necesita el α del material de la ficha
  y el ΔT de los requisitos.

  La F0 busca la fuente citable (guía de diseño de un fabricante de banda modular). Sin una
  fuente citable, la regla sigue SIN_EVALUAR justificable, como hoy: no se inventa un criterio.
- **D4. La animación sigue la comba modelada.** En `ruta_faja_modelo`, en el tramo de catenaria
  reconocido por D3, la cinta animada es la línea media del sólido (no la comba CEMA 2 %). Así
  `publicado.sustitutos_fieles` deja de fallar en una banda modular bien modelada.
- **D5. `join_bolted` no deja herraje dentro del material.** Un criterio nuevo (el 7, que el
  sello pone a todo comando nuevo):
  - rechaza con error accionable la cabeza, la tuerca o la arandela que caigan dentro del sólido
    o del hueco CERRADO de una pieza (rayo por el eje, como `union_taller`);
  - busca el asiento por la cara de contacto real (`kernel/contacto.py`) cuando el solape de
    cajas no da una cara plana (perfil Z, pieza rotada).

  Nunca cambia el criterio 6 (logs guardados).
- **D6. `fasten` acepta `$k` dentro de un conjunto** (`a: "$1+$2"`, `exec_uniones.py` y
  `apolo/batch.py`). Es un arreglo acotado, sin versión: hoy es un 400.

## Alternativas descartadas

- **Pedirle al modelador que simule y mire**: ya estaba en el brief y no lo vio en 3 rondas; lo
  vio Mario. Lo que la puerta no mide, reaparece.
- **Que `arrastrar` no siga los `contacto`**: cambia el replay de logs viejos (por eso nació en
  False) y no cubre la `fija` puesta a mano, que fue la mitad del caso.
- **Prohibir el `contacto` en toda carga**: una bandeja apoyada en zapatas ES un contacto
  correcto. El modo de falla es la tracción.

## Fases

Cada fase sube `VERSION_REGISTRO` con su línea en `calidad/historial_registro.py` y trae su
defecto sembrado.

- **F0 (S, sólo lectura): medir.**
  - Sobre los testigos públicos, los `.apolo` de máquinas reales del escritorio y la laptop
    (máquinas con juntas: mezcladora, puertas plegables, escalera de tijera, mesa plegable, la
    lavadora en sus rondas 3 y 8), contar cuántas uniones fallarían con D1 y D2 y cuáles son
    falsos positivos.
  - Para D3: la fuente citable del alargamiento y la comba de una banda modular, y cómo saber
    que una banda es modular sin nombre.
  - Para D4: por qué la cinta animada de la lavadora entra 50,8 mm en el larguero.
  - Para D5: reproducir los dos casos de `join_bolted` en un test.
- **F1 (M, `services` + `calidad`): D1.** Depende de F0. Verificación: la lavadora de la ronda 3
  falla por la chumacera −Y hija de la junta del eje y por la carcasa arrastrada; la de la ronda
  8 pasa; los testigos y una puerta plegable no cambian.
- **F2 (M, `library/engineering` + `services/calidad_contacto` + `calidad`): D2.**
  Independiente de F1. Verificación: la ronda 6 falla por las dos cuchillas y la 8 pasa; ninguna
  bandeja ni tanque apoyado falla.
- **F3 (M, `services/calidad_tensores` + `library/ruta_faja_modelo`): D3 y D4.** Depende de la
  fuente de la F0; sin fuente, sólo D4. Verificación: la banda modular de la lavadora sale con
  tensión OK (o SIN_EVALUAR justificable) y `sustitutos_fieles` OK.
- **F4 (S–M, `commands/union_taller` + `exec_union` + `exec_uniones`): D5 y D6.**
  Independiente. Verificación: un `join_bolted` bajo un tubo cerrado da error con la salida; uno
  sobre una chapa en Z atornilla; `fasten(a="$1+$2")` corre en un lote; los logs con criterio 6
  regeneran idénticos.

F1, F2 y F4 pueden ir en paralelo (máx. 3 agentes por PC); F3 tras la F0.

## Lo que este plan NO hace

- No acelera la puerta ni las tools en máquinas de ~700 piezas (`delivery_check`,
  `engineering_check` y `check_interference` acotado se cortaron por tiempo en 4 rondas): eso es
  un plan propio que se mide aparte.
- No cambia el revisor a ciegas ni la receta de la fábrica (eso vive fuera del núcleo).
- No toca el acceso de limpieza (cajón, túnel que no abre): no hay una medida general que no sea
  sobrediseño; queda para el revisor.

## Riesgos

- **D1 tumba mecanismos legítimos** (una bisagra modelada con su pasador como «perno», un brazo
  con buje): la excepción del eje de giro y del pivote que se toca los cubre. La F0 mide los
  falsos positivos antes de F1.
- **D2 confunde «cuelga» con «apoya» en piezas inclinadas o laterales**: la F0 fija la tolerancia
  y los casos (pieza colgada al costado de un poste); ante la duda, SIN_EVALUAR justificable, no
  FALLA.
- **D3 sin fuente**: queda como hoy (SIN_EVALUAR justificable), sin inventar el criterio.

## Bitácora

### F0 (2026-10-30)

Sólo lectura. Prototipos en `scripts/medir_lo_fijo_que_gira.py` (D1 y D2, sin tocar el núcleo:
carga cada `.apolo` con `Document.from_apolo_bytes`); reproductores de D5 y D6 en
`tests/test_lo_fijo_reproductores.py` (sintéticos, `xfail(strict=True)` lo que la F4 debe dar).

**Fuentes.** Los 4 testigos públicos y 32 `.apolo` de máquinas reales (fuera del árbol público):
la lavadora de bandejas en sus 9 estados (`modelado`, `correccion1`…`8`), escalera de tijera,
mesa plegable de madera, silla plegable, elevador de cajas, dos variantes de la mezcladora, tanque
agitador, faja de motor central, rodillos por cadena y 14 sin juntas (mesas, estantería, rack,
tolva, plataforma, carro, clasificadora…) para D2. **Faltó** la puerta plegable (id 28): no hay
`.apolo` exportado fuera de la base de uso. La silla plegable no tiene juntas (el plegado no está
modelado): sólo cuenta para D2. Las rondas de la lavadora del escritorio son las mismas (mismos
bytes) que las del repo de producción.

#### D1 — `movimiento.coherente`

Candidatas = `fasten` perno/soldadura/pegado entre piezas que mueven juntas distintas
(`uniones_entre_juntas` sin `_se_tocan`) más el par padre-hijo de una junta de movimiento con unión
rígida. «Como está» = D1 tal cual (excepciones `_se_tocan`, eje de `calidad_ejes_giro` y par de
junta). «Propuesto» = sin `_se_tocan`: excepción por eje o por **prueba de pose relativa** (cada
junta distinta movida 3° o 3 mm: la distancia no crece más de 0,1 mm sobre la de diseño y el
volumen común no crece más de 5 mm³).

| máquina | candidatas | como está | propuesto | reales | falsos positivos del propuesto |
|---|---|---|---|---|---|
| lavadora `modelado` | 12 | 4 | 8 | 8 | 0 |
| lavadora `correccion1` | 23 | 4 | 2 | 2 | 0 |
| lavadora `correccion2` y `3` | 24 / 21 | 4 / 4 | 1 / 1 | 1 / 1 | 0 |
| lavadora `correccion4`…`8` | 20 c/u | 4 c/u | 0 | 0 | 0 |
| escalera de tijera | 6 | 2 | 0 | 0 | 0 |
| mesa plegable | 16 | 0 | 6 | 0 | 6 |
| elevador de cajas | 6 | 4 | 0 | 0 | 0 |
| mezcladora (recipiente) | 1 | 0 | 1 | 0 | 1 |
| tanque agitador | 2 | 0 | 2 | 0 (discutible) | 2 |
| faja motor central, rodillos por cadena, mezcladora `final2` | 1 / 20 / 0 | 0 | 0 | 0 | 0 |
| testigos y máquinas sin juntas | 0 | 0 | 0 | 0 | 0 |

- **Reales (12 casos).** `modelado`: 8 resortes a gas modelados rígidos, quietos y empernados a
  la puerta que gira (al abrir, la puerta entra 8–11 cm³ en ellos). `correccion1`: la **carcasa del
  motorreductor** arrastrada por la junta del eje motriz (empernada a su brazo de reacción quieto;
  626 mm³ al girar 3°) y la **chumacera −Y** hija `fija` del eje, empernada a su ménsula
  (6 355 mm³). `correccion2` y `3`: la chumacera −Y. La carcasa arrastrada está en la
  `correccion1`, no en la 3.
- **D1 «como está» no ve NINGUNO de los 12**: todo par empernado o soldado se toca (lo exige
  `union.contacto_real`), así que la excepción `_se_tocan` de `uniones_entre_juntas` los anula.
  Sus 4 + 2 + 4 avisos son falsos positivos: puertas de la lavadora a 0,12 mm de su bisagra de una
  pieza, el brazo trasero de la escalera a 10,8 mm del larguero (pasador de cierre de lazo) y los
  pernos de amarre de las cadenas del elevador a 0,5 mm.
- **La excepción por eje no aportó**: `calidad_ejes_giro` no halló eje en la lavadora (los
  pasadores de puertas y resortes se declaran con `fasten` sin perno modelado); en la escalera los
  2 que marca ya los cubría la pose.
- **Falsos positivos del propuesto (9).** Mesa plegable: 2 pares de palas de la bisagra B (las
  dos palas tienen cara cilíndrica coaxial con la junta; el solape de los nudillos crece 251 mm³
  al girar) y 4 compases de rodilla (el perno cierra un lazo que la FK no representa: mover sólo
  la junta del brazo lo separa 2,96 mm). Mezcladora: el aro del recipiente empernado a la caja de
  compuerta, en una junta prismática de servicio (`retiro_recipiente`: el perno se quita antes).
  Tanque: la tapa empernada a la bisagra de una pieza quieta (al abrir, la atraviesa 1 058 mm³).
  Esto último es una incoherencia de modelo, pero no «algo fijo que gira».
- **Firma que separa los reales**: en la chumacera y la carcasa, la pieza que se MUEVE tiene una
  cara cilíndrica coaxial con la junta (un alojamiento arrastrado). En la bisagra de una pieza, la
  coaxial es la QUIETA; en las palas, lo son las dos.
- Hueco a sembrar en la F1: una brida (UCF) hija del eje y empernada cara a cara: girar en el
  plano de su cara no separa ni solapa, así que la prueba de pose la deja pasar. No hay ningún
  caso en el corpus; lo cierran los agujeros fuera del eje (los de `union.agujeros`).

#### D2 — `union.contacto_no_cuelga`

Grafo DECLARADO de la puerta; zona = la sección OCCT del par (`kernel/contacto._seccion`, por
cercanía o el par de puntos más cercanos). En la columna «crudas», CM a > 5 mm bajo la zona. En el
resto, la propuesta (`propuesta()` del script): sin tornillería (`lints._is_bolt`), lo colgado
≥ 0,5 kg y tolerancia de 25 mm. «Apoya» pide el CM sobre la zona o una zona que lo ABRAZA (a su
altura y sobre su vertical: una rueda en su eje, un resguardo en su boca). Lo demás es «costado».

| máquina | contacto con carga | cuelgan (crudas, 5 mm) | juzgadas | cuelga | costado | reales |
|---|---|---|---|---|---|---|
| lavadora `modelado`…`2` | 7 / 7 / 91 | 0 / 0 / 48 | 7 | 0 | 0 | 0 |
| lavadora `correccion3`…`5` | 127 / 118 / 118 | 61 | 30–34 | 7 | 11 | 6 |
| lavadora `correccion6` | 121 | 63 | 33 | 9 | 12 | 6 |
| lavadora `correccion7` y `8` | 114 | 60 | 26 | 6 | 12 | 3 |
| mesa inox con poza | 3 | 3 | 1 | 1 | 0 | 0 |
| tolva piramidal | 48 | 24 | 2 | 0 | 0 | 0 |
| las otras 25 (testigos incluidos) | 0–156 | 0–12 | 0 | 0 | 0 | 0 |

- **Ronda 6, el caso del plan**: las 2 cuchillas superiores (22,1 kg, CM 53 mm bajo la abrazadera
  y 265 mm al costado) y 4 ductos (34–56 kg, hasta 815 mm bajo la boca del soplador) cuelgan de
  un `contacto`. Ya estaban así desde la `correccion3`.
- **La ronda 8 NO pasa**: el ducto exterior (2) (33,9 kg), el ducto superior (2) (12,2 kg) y el
  ramal (2) (13,4 kg) cuelgan del soplador. La copia (2) no tiene unión cuchilla ↔ ducto:
  `f_ab_cuch_sup` y `f_ab_cuch_inf` sólo unen la (1). Es real, aunque sea de modelo.
- **Falso positivo físico: la unión ROSCADA declarada `contacto`.** Válvula de drenaje (6,8 kg),
  rebose (13,9 kg) y línea de enjuague (5,1 kg) en la lavadora; válvula de desagüe (1,9 kg) en la
  mesa con poza. Además van a «costado» 11 barras de rociado y el interruptor de nivel. `fasten`
  no tiene un tipo que diga «roscada, aguanta tracción».
- Lo que la propuesta quita: casi todo lo crudo es tornillería declarada `contacto` (89 de 127
  en la ronda 3; 156 de 156 en la plataforma) y cosas de < 0,5 kg (silenciadores, aparatos en
  riel DIN, insertos, anclajes de expansión de 0,14 kg).

#### D3 — fuente de la catenaria

- **En el repo no hay nada citable**: ni ficha de banda modular en el catálogo, ni cita en docs o
  devlog. Sólo `rules_faja_estructura` (eje cuadrado) y la comba CEMA 2 % de `ruta_faja`.
- **Fuente encontrada**: Intralox, *Installation, Maintenance, and Troubleshooting Guide —
  Modular Plastic Conveyor Belts* (2024). En la p. 15, fig. 17, la comba de catenaria va justo
  después de la rueda motriz y se ajusta entre 1″ y 6″ (25,4–152 mm) a la temperatura de
  operación. En el rodaje la banda alarga del 0,5 % al 1 % de su largo total. En la p. 143, una
  comba excesiva por dilatación térmica puede pedir tensor.
- El α térmico y la fórmula de dilatación están en el *Engineering Manual* de Intralox (PDF
  > 10 MB, no se pudo leer aquí): **se pide esa fuente** (o la guía de Habasit o Rexnord) para la
  parte térmica.
- La comba modelada de la lavadora baja ≈ 120 mm (sección: w de −208 a −326 mm): dentro del
  rango.
- **Banda modular sin nombre**: la medida que sirve es el motriz.
  - Ruedas dentadas MÁS ANGOSTAS que la mitad del ancho, varias sobre un eje de sección CUADRADA
    en su vano (caras planas paralelas al eje; hoy sólo se lee «cuadrado 60» del nombre).
  - El material de la banda es un polímero (acetal, PP, PE).
  - Hay una zona libre de retorno después del motriz.
  - Sin ficha de catálogo (no hay familia de banda modular), ésa es la única detección no
    nominal.

#### D4 — por qué la cinta entra 50,8 mm en un larguero

- **Reproducido** en las rondas 3 y 6: entra 50,8 mm en los largueros de lavado y secado (−Y) en
  v = −566,1. Es la mitad del canto de 101,6 mm: el plano corta la pared del tubo. En la ronda 8
  los cruces bajan a 2,0–6,3 mm (13 piezas), pero `sustitutos_fieles` sigue fallando.
- Causa raíz, en cadena:
  1. **La sección de la banda no es un lazo.** El sólido «Banda modular de acetal» corta en el
     plano medio en 17 caras SIN hueco: una C abierta de 244 puntos y tramos de ≈ 52 mm de la
     catenaria, que se tocan pero no se funden. `seccion_plano.lazo_de_banda` da None y
     `ruta_modelo` no corre.
  2. **El respaldo es el casco convexo** (`ruta_faja`), y su envolvente toma como «tambor» lo
     redondo que cubre ≥ 50 % del ancho. Eso incluye la barra de enjuague de ½″ (c274): la cinta
     la abraza en (527, −74), al lado del larguero. Las ruedas dentadas, más angostas, no cuentan.
  3. **Comba CEMA 2 % en vez de la catenaria modelada** (≈ 120 mm de bajada).
- **D4 así como está no alcanza**: «en el tramo de catenaria, la línea media del sólido» supone
  una sección cerrada. Con la sección unida en un lazo, `ruta_modelo` ya sigue la catenaria (no es
  un tramo recto, no recibe comba CEMA).

#### D5 — `join_bolted`, reproducido

- **Cabeza dentro de un tubo cerrado.** Ménsula maciza de 80 mm bajo un TUBO-2X2: la base es la
  ménsula (la más gruesa) y el tubo la pieza agregada. `_medir` toma el par (pared de abajo del
  tubo, ménsula) y asienta la cabeza en la cara INTERIOR de esa pared: el perno M10×100 llega a
  z = 89,6 y la cabeza (k = 6,4) queda en z 83,2–89,6, dentro del hueco (83,2–127,6).
  `exigir_asiento` la acepta porque la cara interior es plana.
- **Chapa en Z.** Alma x ∈ [0, 3] y alas opuestas; placa contra la cara x = 0. El solape de cajas
  pone el contacto en x = −37 (el canto del ala de arriba) y falla con «falta cara PLANA ⊥ al
  eje X en el plano de contacto».

#### D6 — `$k` en un conjunto, reproducido

`fasten(a="$1+$2", b="$3")` en `execute_batch` da «'$1' (en '$1+$2') no es una pieza…».
`batch._REF_RE` hace `fullmatch` del valor entero, así que «$1+$2» llega literal a
`exec_uniones.resolver_conjunto`. El arreglo es resolver cada término del conjunto.

#### Ajustes que piden los datos (vetables)

- **D1a.** Quitar la excepción `_se_tocan`: anula el modo de falla entero (0 de 12). En su lugar,
  la prueba de pose relativa: 12 de 12 reales y 0 falsos positivos en la lavadora, la escalera y
  el elevador.
- **D1b.** No falla el par en que las DOS piezas tienen cara cilíndrica coaxial (± 1 mm) con la
  junta: las palas de una bisagra (quita 2 de la mesa).
- **D1c.** El perno de una junta de SERVICIO (sin actuador ni escenario: `calidad_juntas`) en un
  par que no gira coaxial es AVISO justificable («se quita para abrir o retirar»), no FALLA. Quita
  como falla la mezcladora (1), el tanque (2) y los compases (4). Si Mario prefiere que el tanque
  falle (bisagra en dos palas), D1c se limita a las prismáticas.
- **D1d.** FALLA segura y con texto propio: la pieza que se mueve con la junta y es coaxial con
  ella está empernada a algo quieto («alojamiento arrastrado»: chumacera, carcasa). Son 4 de los
  12 reales.
- **D2a.** No se juzga la tornillería (`lints._is_bolt`) ni lo colgado < 0,5 kg.
- **D2b.** La tolerancia es 25 mm bajo la cota más baja de la zona. Apoya el CM sobre la zona o
  una zona que lo abraza. Lo de costado es SIN_EVALUAR justificable.
- **D2c.** Tipo nuevo `roscado` en `fasten`: rígido, transmite tracción y la BOM no compra
  tornillería por él. Se suma al `Literal` y un log viejo regenera igual. Sin él, las uniones
  roscadas (4 cuelga y 12 costado en la ronda 8) obligan a mentir el tipo. La alternativa es que
  la evidencia diga «si es roscada, decláralo `pegado`».
- **D3a.** Con la fuente de Intralox, la regla puede ser: zona libre tras el motriz con comba
  modelada de 25,4 a 152 mm, que absorbe el alargamiento de rodaje (1 % de L). La parte térmica
  (α·ΔT·L) queda SIN_EVALUAR hasta tener el Engineering Manual.
- **D4a.** D4 pasa a ser «la sección de la banda se une en un lazo»: fundir las caras del corte
  o los sólidos de la banda antes de cortar. El casco convexo sólo toma como tambor lo que tiene
  junta o toca el sólido de la banda; una barra de enjuague no es tambor.
- **Verificaciones.** La F1 usa la `correccion1` (carcasa y chumacera), la 3 (chumacera), el
  `modelado` (resortes a gas) y la 8 (pasa). La F2 usa la ronda 6 (cuchillas y ductos); la 8 sólo
  pasa con la unión cuchilla ↔ ducto de la copia (2) agregada. Si no, que la F2 la dé por buena
  como FALLA real.

### F4 (2026-10-30)

D5 y D6. Sin `VERSION_REGISTRO` (no toca la puerta) ni testigos.

- **D5 es el criterio 8, no el 7** (decisión, vetable): el 7 lo tomó la madera de
  hallazgos-del-revisor F4 (D7) antes que esta fase. El sello pone 8 a todo `join_bolted` nuevo; los
  logs con 1–7 regeneran idénticos (el criterio viaja en los params). Vive en
  `commands/union_montable.py`, enchufado en `union_taller.criterio_taller` sólo con `criterio ≥ 8`:
  - `asiento_real`: primero el asiento por las cajas, como el 7. Sólo si ahí falta la cara plana,
    la huella sale de `kernel/contacto.zona_de_contacto` (función nueva: la caja de los tramos de la
    sección OCCT, o de la cercanía con un hueco ≤ tol), si esa zona es un plano ⊥ a un eje del
    mundo (≤ 0,6 mm de espesor). Una pieza girada en ángulo sigue con el error de siempre: la
    tornillería de `join_bolted` sólo se orienta por ejes del mundo.
  - `exigir_herraje_fuera`, ya medido el eje y antes de taladrar: la cabeza (alto `cabeza_k` hacia
    afuera de la pieza agregada) dentro del sólido de la agregada, la base o una vecina; la cabeza
    en un hueco CERRADO de la agregada (el rayo vuelve a entrar en ella más allá de la cabeza, salvo
    que el hueco se abra a un costado, el `_abierto_al_costado` del criterio 4), y la arandela o la
    tuerca dentro de la agregada. Lo de detrás de la base ya lo cubría el acceso (remache ciego).
    Los agujeros previos del criterio 6 (pies MS1, brida) no se juzgan: el rayo pasaría por el
    agujero.
- **Sin `version` de `join_bolted`** (decisión): la regla «misma geometría con los MISMOS params»
  no aplica. El criterio 8 es un valor nuevo de los params (otra clave de caché) y los 1–7 dan la
  misma geometría; `_exec_join_bolted` no cambió, así que su huella D11 tampoco.
  `test_d5_placa_sobre_placa_queda_igual_que_el_criterio_7` verifica que, donde el 7 ya
  atornillaba, el 8 inserta lo mismo.
- **D6** en `apolo/batch.py`: un valor con forma de conjunto (`+` o paréntesis, la sintaxis de
  `exec_uniones.resolver_conjunto`) resuelve cada término `$k`/`$k_sufijo`, y `check_refs` los
  revisa antes de tocar el documento. No toca una expresión (`=…`), un texto con espacios dentro
  de un término ni la referencia de siempre a un id con `+` (`$1_+A1-K1`: es conjunto sólo con
  dos o más `$k`). `exec_uniones.py` no cambió: el conjunto llega ya resuelto.
- Tests: `tests/test_lo_fijo_reproductores.py` sin los «hoy» ni los `xfail`, más la regresión del
  6 y el 7 en los dos casos de D5 (la cabeza sigue en el tubo y regenera igual; el perfil Z sigue
  con «falta cara PLANA»). Seis tests que fijaban el vigente en 7 pasan a 8.

### F1 (2026-10-30)

`movimiento.coherente` (familia función, registro v28): criterio puro en
`library/calidad/movimiento.py`, insumo en `services/calidad_movimiento.py`, conectado en
`puerta_publicacion.reunir` (tras las fuentes) y en `puerta_hechos` (`juntas_de_movimiento`: sin
juntas giratoria, continua ni prismática, NO_APLICA). `uniones_entre_juntas` gana `tocan=False`
(por defecto, la entrega sigue igual) y `calidad_juntas.clasificar` acepta la prismática. Los pernos
y sus ejes de giro se miden UNA vez por corrida (`pernos_y_ejes`, memo del `contexto` compartido con
la fuente mecánica): el eje sólo se mira si alguna candidata no sale OK por geometría.

Orden de la regla (D1a, D1b y D1d tal como se aprobaron): eje → OK; las dos coaxiales (bisagra) →
OK; la que se mueve es coaxial y la otra está quieta (alojamiento arrastrado) → FALLA aunque la pose
pase; la prueba de pose relativa (3° o 3 mm) pasa → OK; sin medida → SIN_EVALUAR; si no pasa, D1c.

- **D1c afinado (vetable).** Tal como estaba («perno de una junta de servicio en un par que no gira
  coaxial → aviso») soltaba los 8 resortes a gas del `modelado`: las puertas de la lavadora son
  juntas de servicio (los resortes son piezas a medida, no actuadores de catálogo). Los datos
  separan los dos grupos: en el `modelado` la pose METE la puerta en el resorte (8–11 cm³); en los
  compases de la mesa y el aro del recipiente de la mezcladora, la pose sólo las SEPARA (2,96 y
  3 mm, volumen común 0). Queda: en una junta de servicio es AVISO justificable si la pose sólo
  separa (el perno se quita para mover o cierra un lazo) o si la pieza QUIETA es la coaxial (la
  bisagra de una pieza del tanque, que sí solapa 1 058 mm³); lo demás FALLA. Una junta accionada
  FALLA siempre. Regla de la justificación: «unión rígida entre piezas que se mueven distinto».

| máquina | resultado | casos |
|---|---|---|
| lavadora `modelado` | FALLA | 8 resortes a gas (servicio, solapan 8–11 cm³) |
| lavadora `correccion1` | FALLA | carcasa del motorreductor y chumacera −Y (alojamiento arrastrado) |
| lavadora `correccion2` y `3` | FALLA | chumacera −Y (alojamiento arrastrado) |
| lavadora `correccion4`…`8` | OK | 20 candidatas c/u, todas coherentes |
| mesa plegable (final y rondas 1–3) | SIN_EVALUAR | 4 palas OK (bisagra); 4 compases aviso (sólo separan) |
| mezcladora (recipiente) | SIN_EVALUAR | aro ↔ caja de compuerta, aviso (prismática de servicio, separa) |
| tanque agitador (final y v14) | SIN_EVALUAR | tapa ↔ bisagra de una pieza ×2, aviso (bisagra en la quieta) |
| escalera de tijera (final y rondas), elevador, mezcladora `final2`, faja de motor central, rodillos por cadena, silla plegable | OK | — |
| testigos | NO_APLICA | sin juntas de movimiento: sólo versión + ítem |

- **Defectos sembrados**: `brazo_fijo_que_gira` (caso básico: un brazo hijo `fija` de un eje que
  gira, empernado a la placa base: la pose lo separa o lo mete) y `brida_cara_a_cara` (el hueco de
  la F0: la brida coaxial hija del eje, empernada cara a cara, pasa la pose y falla como alojamiento
  arrastrado). Tests en `tests/test_movimiento_coherente.py`.
- **Costo**: el insumo mide 1,5–27 s en la lavadora fuera de la puerta (sin el memo, con el eje
  medido aparte); en la puerta los pernos ya los midió la fuente mecánica.

### F2 (2026-10-30)

`union.contacto_no_cuelga` (familia estructura, registro v29): criterio puro en
`library/calidad/cuelga.py`, insumo en `services/calidad_cuelga.py` (módulo propio: no mide lo que
`calidad_contacto` ya mide, sólo pide la zona a `kernel/contacto.zona_de_contacto` y, con un toque
en un punto, los dos puntos más cercanos), conectado en `puerta_publicacion.reunir` (cronómetro
`cuelga`) y en `puerta_hechos` (`uniones_contacto`: sin contactos declarados, NO_APLICA).
`library/engineering/loads.py` gana `piezas_colgadas` (CUÁLES cuelgan; `hanging_load_kg` las pesa
con la misma cuenta). D2a y D2b tal como se aprobaron: sin tornillería, ≥ 0,5 kg, 25 mm, la zona
que abraza el CM apoya, lo de costado es aviso justificable (regla «carga al costado de un
contacto»). No se juzgan además el par con otra unión o una junta, la unión redundante y la de una
cadena de su comando (`de_cadena`).

- **D2c (decisión, vetable): sin tipo nuevo en `fasten`.** La unión de tubería que transmite
  tracción se DECLARA en la nota del contacto, como el sellado sanitario de `higiene.limpiable`:
  roscada («roscada», «se desenrosca», «NPT», «BSP») o con abrazadera sanitaria de férula
  («tri-clamp», DIN 32676, ISO 2852: con presión nominal, aguanta la tracción del tubo). La
  abrazadera de unión rápida de ducto (anillo con palanca, sin norma) NO cuenta: es el defecto de
  las cuchillas. Motivos: un tipo `roscado` tocaba el `Literal`, `connectivity.FASTEN_KINDS`, el
  dimensionado, la BOM, el montaje y el criterio de uniones por un caso que el modelador YA
  escribe en la nota (las 14 notas de tubería de la lavadora dicen «roscada BSP», «NPT» o
  «tri-clamp DIN 32676»); un log viejo regenera igual porque no cambia nada del comando. Por el
  nombre de la pieza no se adivina: el catálogo no tiene tubería ni válvulas. La F0 pedía sólo la
  rosca; el tri-clamp se suma porque el rebose y las barras de rociado de la lavadora (los
  «falsos positivos físicos» de la F0) van con tri-clamp, no roscados.
- **Ante la duda, SIN_EVALUAR**: sin zona medida (las piezas no se tocan) el caso sale sin medir
  (lo juzga también `union.contacto_real`), y lo de costado, aviso; nunca FALLA.
- **`diseno.sin_sobrantes` no cambia**: el apoyo que se agregue debajo para corregir sostiene a
  una vecina más lejos que él del piso, y la sujeción de la voraz ya lo declara necesario.

Corpus (`.apolo` de las máquinas de producción y del escritorio, cargados con
`Document.from_apolo_bytes`; «juzgados» = contactos con carga que pasan los filtros):

| máquina | juzgados | resultado | casos |
|---|---|---|---|
| lavadora `modelado`, `correccion1` y `2` | 7 | OK | — |
| lavadora `correccion3`…`6` | 30–34 | FALLA | 2 cuchillas superiores (22,1 kg, CM 53 mm bajo la abrazadera) y 4 ductos (34,3 y 55,8 kg, hasta 815 mm bajo la boca del soplador) |
| lavadora `correccion7` y `8` | 26 | FALLA | ducto exterior (2) 33,9 kg, ducto superior (2) 12,2 kg, ramal (2) 13,4 kg: a la copia (2) le falta la unión cuchilla ↔ ducto (falla real, la de la F0) |
| mesa inox con poza 1200 (final, rondas 1–4, copias del escritorio) y 2000 | 1 | FALLA | válvula de desagüe 1,9–2,0 kg colgada de la poza: su contacto no tiene nota; declarada «roscada» pasa (probado) |
| mesa inox con poza 1200 `modelado` | 1 | SIN_EVALUAR | desagüe al costado (aviso) |
| elevador de cajas `modelado` y `revisor` | 1 | SIN_EVALUAR | la cadena de izaje a mano no toca su piñón (sin zona) |
| tolva piramidal (6 rondas) | 1–2 | OK | apoya |
| escalera de tijera, estanterías de madera, mesas plegable, inox, de soldadura y de trabajo, mesas de bolas, carros, clasificadora, elevador (resto), mezcladoras, tanque agitador, plataforma, rack, soporte de paneles, fajas y rodillos (≈ 230 `.apolo`) | 0 | OK | sólo tornillería, livianas (< 0,5 kg) o redundantes |
| testigos | — | OK (faja 12 y rodillos 116 contactos) o NO_APLICA (ménsulas) | sólo versión + ítem |

- Ninguna bandeja, tanque ni mesa apoyada falla. La válvula de drenaje, las 3 uniones americanas
  y el interruptor de nivel de la lavadora ya tenían su rosca en la nota; el rebose y las 10 barras
  de rociado, su tri-clamp DIN 32676.
- **Defecto sembrado** `caja_colgada_de_un_contacto` (una caja de 2,3 kg bajo la placa de la
  ménsula atornillada, CM 40 mm bajo el contacto). Tests en `tests/test_contacto_no_cuelga.py`.
- **Costo**: 0,8–2,2 s en la lavadora (≈ 36 s la primera medida en frío de la `correccion3`), <
  0,2 s en el resto.

### F3 (2026-10-30)

D3a y D4a, registro v29. La fuente es la guía de instalación de Intralox (2024), p. 15, fig. 17
y «Break-in period»: la comba va tras la rueda motriz, de 1″ a 6″ (25,4–152 mm) a la temperatura
de operación; en el rodaje la banda alarga del 0,5 % al 1 %, y si alarga de más se retiran filas
(URL en `library/catenaria_banda.FUENTE`). El α térmico no se buscó: queda pedido.

**D4a, la cinta sigue la banda modelada.** Eran tres eslabones, no uno:

1. **La sección no era un lazo.** En las rondas 3 a 5 la banda es HUECA por dentro: dos pieles de
   ≈ 3 mm, a 9 mm una de otra, que sólo se cierran en los cantos (el corte de los cantos sí es un
   lazo de 15 mm). En las 6 a 8, además, la catenaria son 16 tramos de ≈ 52 mm que se tocan en una
   esquina. `seccion_plano.lazo_de_banda` ahora cierra el corte (`cerrar`: crecer δ, fundir y
   encoger δ, con δ de 0,5, 2, 5 y 10 mm, el primero que deja TODO el corte en una cara con hueco)
   cuando hay más de una cara o ninguna tiene hueco. Con una sola cara con hueco (la banda de
   `create_belt_conveyor`) no cambia nada. La línea media sale del lazo de 15 mm. Con el lazo, la
   catenaria no es un tramo recto y no recibe la comba CEMA: no hizo falta más código para eso.
2. **Con el lazo, la cinta entraba 2,6 mm en las zapatas de retorno.** `_vano` tomaba el primer
   punto de cada apoyo y la comba nacía ahí, aunque la zapata fuera plana y de 40 mm. Ahora, una
   zapata cuya cara plana mide más que `APOYOS_PEGADOS_MM` (30 mm) apoya en sus dos bordes. En un
   rodillo los bordes coinciden y todo queda igual.
3. **En el casco convexo**, `PiezaPlano.tambor` deja fuera lo redondo que no tiene junta ni toca
   la banda (`marcha_visual._toca`, ≤ 1 mm). La barra de enjuague ya no es tambor. Con el lazo
   cerrado, la lavadora no llega al casco, pero el respaldo queda corregido.

**D3a, la catenaria es tensado reconocido** (`services/calidad_catenaria.py`; lo puro en
`library/catenaria_banda.py` y `library/calidad/catenaria.py`). Sólo se mide al correr la puerta y
sólo en una banda sin otro tensor. Decisiones, vetables:

- **Modular sin nombre**: el material es acetal, PE, PP o PA. La mueve una junta de giro accionada
  (`calidad_juntas`) paralela al eje de la banda, cuyo cuerpo es un eje que la cruza con sección
  cuadrada (16·A/P² = 1 ± 0,05, sin importar cómo esté girado). Lleva ≥ 2 ruedas coaxiales más
  angostas que la mitad del ancho y que llegan a la cara de adentro del lazo: los anillos de
  retención y la chaveta no cuentan. Si dos juntas lo cumplen, no se adivina.
- **La zona tras la motriz**: desde cada punta del arco de contacto se sigue la línea media hasta
  la primera pieza que la toca (el corte de lo que cruza el plano medio) o hasta un giro neto hacia
  afuera de más de 5° en 100 mm (un desvío por encima). Los primeros 30 mm no cuentan: el modelo
  quiebra al salir de la rueda. La comba es lo más que cae bajo la cuerda, y gana el lado que más
  cuelga. Fuera de 25,4–152 mm, o sin zona, todo sigue como hoy.
- **«Absorbe el 1 %»**: la comba sola no lo absorbe (de 141 a 152 mm sobre 626 mm guarda 13 mm de
  los 185 del rodaje). Por eso la guía manda retirar filas. El criterio medible es que la banda
  pueda colgar LIBRE hasta el tope de 152 mm, que es el punto en que se retiran filas. FALLA si
  algo entra en la parábola de 152 mm más de lo que ya entra la banda modelada (+1 mm). La
  evidencia dice cuánto guarda la comba y cuánto se retira por filas.
- **Térmica**: con `temperatura_c` fuera de 10–30 °C, la carrera queda SIN_EVALUAR justificable
  (falta el α para α·ΔT·L). Sin temperatura declarada, o a temperatura ambiente, no entra.
- El rodaje se calcula con el largo de la LÍNEA MEDIA. `largo_de_banda` (área y volumen) cuenta
  las dos pieles de una banda hueca: 37,3 m en vez de ≈ 18,7 m. Ese largo no se tocó: lo usa el
  resto del control.

| ronda de la lavadora | `sustitutos_fieles` (antes → ahora) | `transmision_flexible.tension` |
|---|---|---|
| `correccion3` | FALLA (50,8 mm en el larguero, casco) → OK (sección, desvío 34 mm ≤ comba) | SIN_EVALUAR, como antes (el retorno sale recto de la motriz: no hay comba) |
| `correccion6` | FALLA (50,8 mm) → OK | SIN_EVALUAR → reconocido OK (comba de 141,4 mm en 626 mm, 5 ruedas); carrera SIN_EVALUAR justificable: libre hasta 152 mm (guarda 13 mm; 172 de los 185 mm del rodaje se retiran por filas), pero trabaja a 65 °C y falta el α |
| `correccion8` | FALLA (2,0–6,3 mm, 13 piezas) → OK | igual que la 6 |

La marcha completa (la de la puerta, con la simulación) tarda 40–43 s por ronda. Los insumos del
tensor tardan 2–2,4 s con la catenaria.

- **Testigos de faja, idénticos**: la faja de `create_belt_conveyor` (testigo público) y dos fajas
  de paquetería hechas a mano (motor en cabeza y central) dan la MISMA cinta, los mismos vanos, la
  misma fidelidad y los mismos ítems del tensor con el código de antes y el de ahora. La comparación
  se hizo punto por punto contra un `git archive` del `main` de partida. La faja 38 no se pudo
  correr: vive sólo en la base de uso.
- **Defecto sembrado** en `tests/test_catenaria_banda.py`, sobre una banda modular sintética (eje
  cuadrado, tres ruedas, dos anillos, desvío y conducida). Una bandeja de goteo 20 mm bajo la comba
  hace FALLAR la carrera. También están ahí el OK, el SIN_EVALUAR en caliente y los «como antes»
  (comba de más o de menos, eje redondo, una rueda con anillos). No va en
  `test_defectos_sembrados`: ningún testigo lleva banda modular, y el ítem general ya tiene
  defectos allí.
- Sin `version` ni `GEOM_CACHE_EPOCH`: no cambia la geometría de ningún comando. La serie de la
  marcha se cachea en memoria por firma del documento y se rehace al reiniciar.
