---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: F0 y F1 mergeadas (2026-10-26): 8 familias, 39 refs, GEOM_CACHE_EPOCH 10; el tablero de la piloto y el de la faja con desviador no se mueven y su ERC y su firma no cambian. Falta F2 (seccionador de puerta, relé térmico, relé de seguridad, bloques auxiliares, prensaestopas y tope) y F3 (Mario lo ve en el visor y en el video)
descripcion: Los aparatos dentro del tablero (ITM, diferencial, contactor, guardamotor, PLC, fuente, relé, borne y variador) se ven como los de verdad —gris RAL 7035, bornes con tornillo, palanca, teclado— sin moverse de su lugar
---

# Los aparatos del tablero se ven como los de verdad

## Estado y origen

Mario evalúa las máquinas en el visor y en sus videos. Hoy los aparatos dentro
del tablero se ven como cubos de colores con sus medidas reales. Su decisión: «formas
paramétricas por familia», sin bajar STEP de fabricantes.

Este plan sigue al de la [seta de emergencia](seta-de-emergencia.md): usa sus zonas de acabado
(una pieza, un sólido, varias zonas de color) para el resto del tablero.

## El problema / lo que hay hoy

Medido en la F0 (bitácora):

- **62 refs van dentro de un tablero** (`electrico.montaje` din, placa o puerta). 44 eran
  `builder: box`: un cubo de un color, el de la paleta. Las de puerta ya tenían forma: la seta,
  los mandos Ø22 y el panel de operador.
- **Las máquinas de referencia** usan casi sólo cajas. La piloto (`tests/data/tablero_piloto.json`)
  tiene 12 aparatos. La faja con desviador (`C:\t\v89f7\faja-77-desviador.apolo`, `layout_tablero`
  c1639) tiene 14 aparatos y 47 conductores. Sus cajas son ITM 3P y 2P, fuente, PLC, variador,
  borne PE, relé de interfaz y seccionador de puerta.
- **Lo que depende de la caja**: la colocación lee `width` × `depth` × `height` de los params de
  una `box` (`electrico/colocacion_catalogo.py:26`). Lo que no es caja lo mide por el bbox del
  catálogo (`commands/tablero.py:_medir`). El armado pone el centro del bbox en el centro de su
  lugar (`commands/tablero_geom.matriz_catalogo`) y rechaza una forma con otras medidas. El ruteo
  y el calentamiento leen el `Layout`, no la forma.
- **Lo que no depende**: el ERC, la co-simulación y la firma de los escenarios leen la ficha
  eléctrica (`services/escenarios._fichas_electricas`), nunca la geometría ni el builder.

## Lo que se revisó antes de escribir esto

- [seta-de-emergencia](seta-de-emergencia.md): las zonas viajan por índice de cara, se validan
  por número de caras y volumen, y llegan al visor, a VTK y al GLB sin código nuevo. Este plan no
  toca ni el payload, ni el visor, ni el render.
- La memoria del proyecto: biblioteca paramétrica (builder + YAML), y las refs son EJEMPLOS que
  el fabricante reemplaza.
- `ficha_tablero.APOYO_POR_FAMILIA`: la cara de apoyo va por familia (builder). Una familia nueva
  sin su cara no se coloca.
- La regla de la raíz: geometría nueva con los mismos params es bump de `GEOM_CACHE_EPOCH`.

## Decisiones (para vetar)

- **D1. Un builder por familia, ocho familias** (`library/builders_aparatos.py`; las piezas
  comunes, en `library/aparatos_forma.py`):

  | familia | refs | lo que se ve |
  |---|---|---|
  | `interruptor_modular` | `ITM-*` (8), `DIF-*` (8, `tipo: diferencial`) | perfil DIN 43880, bornes por polo con su tornillo, palanca de puente en ON, junta entre polos, placa de datos, botón de prueba |
  | `contactor` | `CONT-9/12/18A-*` (6) | bornes de potencia + auxiliar arriba y abajo, bobina A1/A2 al frente, ranura del bloque auxiliar, ventana del indicador, placa |
  | `guardamotor` | `GM-*` sin el auxiliar (5) | bornes por polo, mando giratorio con barra de agarre, dial de ajuste, placa |
  | `rele_interfaz` | `RELE-INT-*` (2) | módulo angosto, dos bornes escalonados por lado, el relé enchufable al frente |
  | `borne_riel` | `BORNE-PASO-*`, `BORNE-PE-*`, `BORNE-FUS-*` (5; `tipo`) | perfil escalonado, un tornillo por lado, marcador blanco, franja amarilla del PE o portafusible negro |
  | `plc_compacto` | `PLC-14DI-10DO-24VDC` | borneras bajo tapas, franja de LEDs de E/S, LEDs de estado, puerto de red, ranuras arriba, placa |
  | `fuente_riel` | `FUENTE-*` (2) | perfil DIN 43880, entrada abajo y salida arriba, LED «DC OK», potenciómetro, ranuras |
  | `variador_compacto` | `VFD-*` (2) | teclado con pantalla, MARCHA verde, PARO rojo y perilla, tapa de bornes, ranuras |

  El ITM y el diferencial, y las tres clases de borne, comparten builder con un `tipo`. Un
  builder sirve a todas las refs de su familia: quien fabrica con otra línea cambia la ficha, no
  el código.
- **D2. La envolvente es EXACTAMENTE la caja de la ficha.** Cada builder recibe los mismos
  `width` × `depth` × `height` que tenía la caja, en el mismo marco: centrado, X a lo largo del
  riel, −Y apoya y Z arriba. El cuerpo toca las seis caras de la envolvente, o las toca un
  detalle (la palanca del ITM, el mando del guardamotor). Todo lo demás se talla hacia adentro:
  nada sale de la envolvente. Lo exige el test, con 1e-6 mm.
  - `ficha_tablero.FAMILIAS_APARATO` nombra las ocho familias (sólo los nombres: ese módulo no
    importa geometría). Apoyan por −Y y cuentan como caja (`FAMILIAS_CAJA`).
  - La colocación lee sus params como los de una `box`. Así nada se mide por OCCT, y el layout,
    el ruteo y el calentamiento dan lo mismo que antes.
  - Cada cota de un detalle es una fracción de las medidas de la ficha, con un tope en mm donde
    el detalle tiene tamaño propio: un tornillo no crece con el aparato. Ninguna coordenada es
    fija. Lo prueba un test que escala las tres medidas.
- **D3. Nivel de detalle: lo que se ve desde la puerta abierta a un metro.** Entran los bornes en
  su alojamiento con el tornillo, la palanca o el mando, la ventana, la placa de datos, el clip
  del riel y las ranuras de la cara de arriba (seis como máximo).
  - Fuera queda lo que sólo se ve de cerca o desde atrás: la ranura de la cabeza del tornillo,
    la boca del conductor, el texto de la placa, el perfil interior del clip y las ranuras de
    abajo. Un tornillo es un cilindro.
  - Por qué: cada detalle son caras, y las caras cuestan al construir y al teselar. La primera
    versión, con la boca del conductor y las ranuras de abajo, daba 1,5 a 3,5 veces las caras
    (bitácora F1).
- **D4. El acabado de cada zona va en el YAML**, con un ancla por familia. Los acabados nuevos
  salen de la «List of RAL colours» de Wikipedia (2026-10-26):
  - `plastico_ral7035`: el cuerpo de la aparamenta modular, gris luminoso RAL 7035 (#CBD0CC).
  - `plastico_antracita`: el variador y las tapas del PLC, antracita RAL 7016 (#373F43).
  - `pantalla`: la pantalla apagada del variador y la franja de LEDs del PLC. Es criterio de
    diseño, no un color de norma.
  - Los bornes van en `niquelado`; la palanca, el mando y el clip, en `plastico_negro`. El borne
    de paso va en `plastico_gris`, que es el RAL 7042 de la línea de referencia.
  - Van `fijo` los colores de norma o de función, que `set_color` no repinta: la placa blanca, el
    LED verde, MARCHA y PARO del variador y el verde-amarillo del borne PE.
  - Los moldeados no se pintan (no son `pintables`).
- **D5. Costo: una construcción por proceso, booleanas en una sola operación.**
  - Medido (bitácora): un aparato con sus detalles cuesta de 0,07 a 0,33 s de construir; antes
    era una caja. El tablero lo pediría en cada regenerate.
  - `unir_zonas(memo=True)`: los aparatos de tablero se construyen una vez por proceso y devuelven
    el mismo sólido. Es seguro porque ningún executor muta un shape en sitio (regla de la raíz).
  - Cada aparato hace UN corte con todas sus herramientas y UNA fusión: `kernel/zonas.fusionar_zonas`
    acepta una lista de formas por zona.
  - Las booleanas en paralelo de OCCT (2× más rápidas) no se usan. Nada garantiza que den el mismo
    orden de caras, y la zona de cada cara va por ese índice: un sólido de la caché de otro
    proceso se pintaría mal.
  - La seta y los mandos Ø22 siguen como estaban: ni memo ni otra fusión.
- **D6. Vigencia.**
  - `GEOM_CACHE_EPOCH` 9 → 10: builder + YAML de 39 refs con los mismos params, algo que no se
    acota a un executor.
  - `layout_tablero` no sube su `version`: su código no cambió, y la geometría del catálogo la
    invalida el epoch.
  - El ERC y la firma de los escenarios no cambian. Medido en las dos máquinas de referencia con
    main y con la rama: misma firma, mismo ERC y las mismas 35 cajas del tablero a 0,001 mm.
- **D7. Fuera de la F1**, para la F2: el seccionador de puerta (`SECC-*`, el aparato más visible
  de la puerta), el relé térmico (`RT-*`), el relé de seguridad (`RS-2C-24VDC`), los bloques
  auxiliares (`CONT-AUX-*`, `GM-AUX-*`), el tope DIN y los prensaestopas. Siguen siendo cajas.

## Alternativas descartadas

- **STEP del fabricante**: la decisión de Mario. Además pide licencia por ref, pesa MB por pieza y
  no trae zonas.
- **Un builder genérico, «caja con detalles»**: no da la silueta de cada familia (el escalón DIN
  43880 del ITM, el mando del guardamotor), que es lo que se reconoce de lejos.
- **Un builder por ref**: multiplica el código, y una ref es un ejemplo.
- **Textura o calcomanía sobre la caja**: VTK no la ve y no tiene relieve; el tornillo hundido es
  lo que la hace leer como aparato.
- **Memo en toda pieza por zonas**: cambiaría la seta y los mandos (TShape compartido en el GLB,
  ya probado en su plan). No hace falta para este plan.
- **Booleanas en paralelo**: ver D5.

## Fases

- **F0 (S, sólo lectura): medir.** Qué refs van en un tablero y con qué builder, cuáles usan las
  máquinas de referencia, cuánto cuestan hoy el regenerate y el teselado del tablero, y los
  renders de antes. Hecha.
- **F1 (M, `library` + `kernel/zonas`): D1–D6.** Los ocho builders, las zonas en el YAML, los
  acabados, el memo y la fusión por listas, el epoch, la colocación que lee los params y los
  tests. Hecha.
- **F2 (M, `library`): D7.** El seccionador de puerta, con su manija roja sobre placa amarilla
  si es de emergencia (IEC 60204-1 §5.3.3, a leer) o negra si no. También el relé térmico, el
  relé de seguridad, los bloques auxiliares, los prensaestopas y el tope, con las mismas reglas.
  Depende de F1.
- **F3 (S, verificación):** Mario ve en el visor el tablero de la faja con desviador y el de la
  piloto, con la puerta abierta. Se pasa el video del tablero y el GLB de la vista 3D. Sus ajustes
  de color o de detalle entran como D nuevas.

## Lo que este plan NO hace

- No cambia fichas eléctricas, ERC, co-simulación, colocación ni ruteo.
- No toca el payload de escena, el visor, VTK ni el GLB: las zonas ya viajan desde la seta.
- No cambia los mandos de puerta, que ya tenían forma.
- No dibuja los conductores entrando a cada borne (lo hace el ruteo con sus puntos).

## Riesgos

- **La primera construcción de cada ref** cuesta de 0,07 a 0,33 s, y su teselado para el visor
  de 0,03 a 0,25 s, una vez por proceso. Un tablero con nueve refs distintas suma ≈ 2 s y ≈ 1 s
  al primer open sin caché. Mitigación: D5. La caché de geometría y la de mallas de definición
  (`api/scene._DEF_MESH_CACHE`) evitan repetirlo, y F2 mide de nuevo.
- **El sólido memorizado se comparte**: una mutación en sitio lo corrompería para todos.
  Mitigación: la regla de la raíz lo prohíbe, y el test `test_una_construccion_por_proceso` deja
  dicho que es el mismo objeto.
- **Otro OCCT ordena distinto las caras**: la huella (número de caras + volumen) deja de calzar
  con la caché y la pieza se ve de un acabado, nunca con colores cambiados. Un upgrade invalida
  la caché solo (`_versions`).

## Bitácora

### F0 (2026-10-26): medición, sólo lectura

Scripts fuera del repo, en el scratchpad de la sesión.

- **Refs.** 62 con `montaje` din, placa o puerta. Por familia:
  - din `box` 42; placa `box` 2 (los variadores); placa `cylinder` 5 (los conductores);
  - puerta `box` 2 (los seccionadores), `mando_22` 8, `seta_emergencia` 2 y `panel_puerta` 1.
- **Máquinas.** La piloto tiene 12 aparatos: 7 cajas, 4 mandos y la seta. El desviador tiene 14:
  la piloto más `RELE-INT-24VDC` y un borne PE más, con 47 conductores. Sus familias: 8 cajas,
  4 `mando_22` y 1 seta.
- **Costo de hoy** (`time.process_time`, tablero armado solo, sin la máquina):

  | | regenerate (mediana de 3) | teselado del payload, 35 piezas | triángulos (aparatos) |
  |---|---|---|---|
  | piloto | 0,64 s (1.ª: 0,95) | 0,48 s | 5 171 (3 095) |
  | desviador | 0,81 s | 0,36 s | 5 183 (3 107) |

- **Renders de antes** en `C:\t\aparatos-capturas\*-antes.png`: una ref por familia aislada, y el
  tablero de la piloto sin puerta, de frente e iso.

### F1 (2026-10-26): ocho builders, zonas y vigencia

- **Kernel.** `fusionar_zonas` acepta una lista de formas por zona: una sola fusión. Una pieza sin
  listas pasa por el mismo camino que antes.
- **Library.**
  - `aparatos_forma.py`: perfil DIN 43880, alojamiento de borne con su tornillo, placa de datos,
    clip, ranuras y el corte en una operación.
  - `builders_aparatos.py`: las ocho familias, con su registro y `ZONADOS`. El loader une los
    `ZONADOS` de los mandos y de los aparatos y pasa `memo` a los aparatos.
  - `zonas.unir_zonas(memo=)`.
  - Tres acabados nuevos y `ui/src/viewport/acabados.json` regenerado con
    `scripts/acabados_ui.py`.
  - `ficha_tablero.FAMILIAS_APARATO` y la colocación que lee sus params.
- **YAML.** 39 refs dejan `builder: box`, con un ancla `zonas` por familia y archivo. Los
  diferenciales ganan `tipo: diferencial` y los bornes PE y portafusible, su `tipo`.
- **Primer intento descartado.** Tallaba la boca del conductor en la cara de arriba y de abajo, y
  las ranuras arriba y abajo sin tope. Las caras eran demasiadas:

  | ref | caras | construir | teselar |
  |---|---|---|---|
  | contactor | 175 → 115 | 0,97 → 0,33 s | 0,35 → 0,14 s |
  | variador | 267 → 77 | 0,72 → 0,20 s | 0,37 → 0,08 s |

  Las nueve refs de las máquinas pasaron de 3,9 a 1,8 s de construir y de 1,8 a 1,0 s de
  teselar. De ahí D3. Ninguna de las dos se ve desde la puerta.
- **Booleanas.** Un perfil de cProfile mostró que la fusión repetida sobre las mismas formas
  cuesta 10 ms y la primera, 270–425 ms: OCCT agrega p-curvas a las formas de entrada. Las
  opciones medidas: paralelo, 2× más rápido en el corte; OBB, sin ganancia. El paralelo se
  descartó (D5).
- **Vigencia** (script `vigencia.py` del scratchpad, con main y con la rama, sobre
  `faja-77-desviador.apolo` y `faja-77-tablero.apolo`): misma `firma_documento`, mismo
  `chequeo` (ERC) y las mismas 35 y 34 cajas del tablero a 0,001 mm.
- **Tests** (`tests/test_aparatos_tablero.py`):
  - las familias son las de `FAMILIAS_APARATO` y apoyan por −Y;
  - cada forma distinta da la envolvente exacta, un sólido y zonas que cubren caras y malla;
  - escalada ×1,3/×1,1/×1,2 y ×0,8/×0,9/×0,85, sigue exacta;
  - memo sí en los aparatos y no en la seta;
  - errores de tipo y medida;
  - la zona con lista;
  - la colocación sin `medir`;
  - el tablero de la piloto da los centros y medidas congelados en main
    (`tests/data/tablero_piloto_cajas.json`), y sus aparatos llegan con zonas.
- **Costo antes y después**: el mismo script, 6 regeneraciones, con main y con la rama en la
  misma sesión. Es `process_time`, con ruido de ±0,2 s.

  | | regenerate, 1.º del proceso | regenerate, mediana | teselado del payload, 35 piezas | triángulos (aparatos) |
  |---|---|---|---|---|
  | piloto, main | 1,02 s | 0,96 s | 0,61 s | 5 171 (3 095) |
  | piloto, rama | 2,19 s | 0,78 s | 1,38 s | 11 011 (8 935) |
  | desviador, main | 0,77 s | 0,91 s | 0,39 s | 5 183 (3 107) |
  | desviador, rama | 1,06 s* | 0,93 s | 1,27 s | 11 823 (9 747) |

  \* El desviador corre después de la piloto, en el mismo proceso: sus refs ya estaban hechas.

  - El regenerate de siempre no cambia: el memo deja la construcción en la primera vez.
  - La primera vez suma ≈ 1,2 s.
  - El teselado se cuenta aquí pieza por pieza. En la escena va una vez por definición, y su
    caché (`_DEF_MESH_CACHE`) dura todo el proceso.
  - Por ref, en frío: construir cuesta de 0,07 a 0,35 s y teselar, de 0,03 a 0,18 s. Los
    aparatos pasan de 12 triángulos a entre 364 y 1 980.
- **Suites**: pytest completo (`-n 4`), exit 0; `ruff check core tests scripts` limpio; `npm test`
  (574) y `npm run build` en verde, por `acabados.json`.
- **Renders** en `C:\t\aparatos-capturas\*-despues.png`: las doce refs y el tablero de la piloto,
  de frente e iso. Los de antes, en `*-antes.png`.
