---
estado: en curso
nota: contrato escrito (2026-10-29, laptop) sobre 9 pilotos de familia y APROBADO por Mario el mismo día («pushealo … para que la persona de escritorio lo revise e implemente»); el escritorio, dueño del núcleo, lo revisa, mergea el archivo y toma F0–F7
descripcion: Lo que el revisor a ciegas encuentra máquina tras máquina lo frena la puerta en el primer modelado, en vez de pagarlo ronda por ronda
---

# La puerta frena lo que el revisor de taller encuentra siempre

## Estado y origen

Pedido de Mario (2026-10-29), tras el lote de 9 pilotos de la laptop: «escribe el plan para pasar
los hallazgos repetidos del revisor a reglas de la puerta». Regla suya que lo enmarca: «defecto
visto → arregla la fábrica», determinista y para todas las PCs
([bom-de-compra-fiel](bom-de-compra-fiel.md) § Estado y origen).

Evidencia: 9 pilotos de familia (mesa inox lisa y con poza, mesa de bolas, mesa plegable de
madera, mesa de soldadura con grilla Ø16 y Ø28, silla plegable, escalera de tijera, estantería de
madera), modelados con la receta de pilotos (modelado → revisor a ciegas → puerta → hasta 3
rondas de corrección → re-revisión a ciegas) con la puerta v19. Las 9 terminaron con la puerta
APROBADA; **sólo 1 convergió** (sin ALTA ni MEDIA). Las otras 8 llegaron al tope de 3 rondas con
1 a 4 MEDIA abiertos. Las rondas de corrección y re-revisión fueron el 67 % del costo del lote y
el revisor trae hallazgos NUEVOS en cada ronda: el tope es lo que corta, no la convergencia.

## El problema / lo que hay hoy

Los reportes `rerevisor<n>-reporte.md` de `C:\t\maq\<slug>\` (sólo lectura) repiten, en máquinas
distintas, defectos que la puerta no mira. Agrupados por modo de falla:

1. **El material que el núcleo no conoce se calcula como acero, en silencio.** Silla plegable,
   tijeras de «haya»: la BOM da 6,9 kg por tijera (densidad 7 850 kg/m³; la haya pesa ~0,62 kg) y
   la silla entera 33,5 kg. `materials.density()` cae a `DEFAULT_DENSITY = 7.85e-6  # acero`
   (`library/materials.py:45`) y `yield_strength()` a `DEFAULT_YIELD = 250.0` (`:85`): una tijera
   de madera se dimensiona contra 250 MPa de acero. Las maderas tabuladas son sólo «copaiba» y
   «madera» genérica (`:24–26`). `has_yield()` existe para el FEA (`:197`), nadie más lo mira.
2. **Lo que se compra no alcanza para comprarlo.**
   - mesa de bolas: bola de transferencia y pie nivelador como ref «COMPRA», norma vacía, sin
     fabricante ni código;
   - mesa de soldadura Ø28: pie nivelador «COMPRA» sin norma ni **carga nominal**, con 500 kg de
     carga más 291 kg de mesa;
   - mesa con poza: el «kit de compra» del desagüe sale como «A-MEDIDA», con largo y sin norma;
   - mesa plegable: una bisagra modelada en 2 sólidos sale como 4 + 4 «medias bisagras», y cada
     compás de 5 sólidos sale como 5 filas COMPRA.

   La compra se DECLARA con «(compra)» en el nombre (`designacion_comercial.compra_declarada`),
   pero nada exige que traiga designación, y la BOM no sabe que varios sólidos son UNA compra.
3. **Filas de la BOM sin la medida para cortar o pedir.**
   - escalera: «Varilla roscada M8 DIN 976-1», cantidad 6 y `longitud_mm` null, cuando mide 482 mm
     en el modelo;
   - mesa de soldadura Ø28 y mesa inox: piezas a medida de «acero» sin grado (S235/S355) ni norma.
     La plancha de 1000×800×25 pesa 147 kg y es la cara de trabajo.

   [bom-de-compra-fiel](bom-de-compra-fiel.md) F1-a resolvió la norma sólo para la chapa CON ficha.
4. **Pernos y tornillos demasiado cerca de la testa o del canto, en madera.**
   - mesa plegable: perno M6 a 2,5d y a 3,5d de la testa;
   - silla: 12,7 mm de madera delante de un agujero Ø14,5;
   - estantería: tornillo 4×40 a 7,5 mm del canto de un larguero de 19 mm, con un solo tornillo
     por escuadra.

   `union.distancia_al_borde` usa la tabla 3.3 de EN 1993-1-8, que es de CHAPAS de acero
   (`library/borde_agujero.py`; «canto = donde la pieza tiene el espesor de la chapa»). La madera
   no tiene criterio.
5. **El eje de giro se afloja.**
   - escalera: pivotes y codo del tirante con tuerca simple DIN 934;
   - silla (ronda 1, ALTA): un tirafondo DIN 571 en la testa hacía de eje de la tijera; además,
     DIN 933 + DIN 934 sin traba.

   `union.retencion` (`library/calidad/agarre.py:111`) mira que la tuerca tenga hilo fuera, no que
   un eje que GIRA esté trabado. `join_bolted` ya ofrece `tuerca: "din985"`
   ([bom-de-compra-fiel](bom-de-compra-fiel.md) D5), pero nadie la exige donde gira.
6. **Equipo higiénico con rendijas.**
   - mesa inox (2 rondas): la soldadura de la repisa al larguero es de 240 mm en 1 100 mm de
     contacto, así que queda una rendija abierta de ~860 mm por lado;
   - la cubierta queda 3 mm sobre el tope abierto de la pata, y el agua entra al tubo cerrado
     abajo (EN 1672-2, NSF 2).

   No hay requisito «higiénico» ni ningún control (`grep higien|1672` en `core/apolo`: nada).

Los defectos de UNA máquina, como la riostra de la mesa de bolas, el juego de montaje de las
orejetas de la Ø28 o la geometría del rebosadero de la poza, quedan para su revisor: no son de
la fábrica.

## Lo que se revisó antes de escribir esto

- `library/calidad/registro.py` (registro v21): las Entradas y los ítems generales de F2/F3. La
  regla es la de `library/CLAUDE.md` § Puerta: ítems GENERALES por modo de falla. Una máquina
  nueva suma un detector, no un ítem; un ítem nuevo sube `VERSION_REGISTRO`.
- `p.fabricabilidad` (`calidad/puerta.py:271`) sólo pide un sólido cerrado con material y
  proceso RESUELTOS; un material resuelto por defecto pasa.
- [bom-de-compra-fiel](bom-de-compra-fiel.md) F1 (mergeada hoy):
  - ya cubre la chapa con espesor y norma, el corte medido, una fila por pieza fabricada, la
    tuerca una sola vez, las arandelas y `tuerca: din985`;
  - ya cubre las BOM de la tanda del escritorio. Este plan NO repite nada de eso;
  - los pilotos se modelaron ANTES de ese merge, por eso la F0 re-mide todo con `main`.
- `engineering/installation.anchor_loads` da la reacción de cada apoyo, y el catálogo ya publica
  `capacidad_kg` en algunas familias (`107_correderas_colgantes.yaml`, `20_rodillos.yaml`).
- `services/calidad_contacto.py` y `kernel/contacto.py` ya MIDEN la línea de contacto de dos
  piezas soldadas ([uniones-que-tocan](uniones-que-tocan.md)), y
  `services/calidad_juntas.py` sabe qué juntas giran.

## Decisiones (para vetar)

- **D1. Un material que el núcleo no conoce es FALLA, nunca acero.** Ítem nuevo
  `material.conocido` («Cada pieza tiene un material con densidad y resistencia tabuladas»):
  toda pieza a medida cuyo material resuelto no está en `DENSITY_KG_MM3` y `YIELD_MPA` falla, con
  la lista. Ni la masa ni el cálculo caen a los defaults del acero sin decirlo. Las ref de
  catálogo pesan por ficha y no se juzgan.
- **D2. Las maderas de las familias entran tabuladas con su fuente**: pino radiata, haya y
  eucalipto (densidad, E, MOR, costo referencial), con la cita de cada valor como copaiba, y
  antes que «madera» en los dicts (`_norm` toma la primera subcadena). Otra especie se agrega
  igual, nunca por defecto.
- **D3. La pieza a medida de acero lleva su grado en la BOM**: sin grado declarado, la norma del
  material genérico (`bom_compra.NORMA_CHAPA`, acero → ASTM A36 ≈ S235JR; inox → AISI 304 ASTM
  A240), igual que F1-a de la chapa pero para TODA pieza a medida. Un grado declarado en el
  nombre o el material gana. Nunca se inventa un grado distinto del que usa el cálculo.
- **D4. Ítem nuevo `bom.comprable`** («Cada fila de la BOM alcanza para comprar o cortar la
  pieza»). Por tipo de fila:
  - compra → norma o designación (`norma_del_nombre`) o código de fabricante;
  - barra, varilla o perfil → largo (el MEDIDO si no hay otro);
  - chapa → espesor y desarrollo;
  - a medida → material con norma (D3).

  Una fila incompleta FALLA y nombra la pieza.
- **D5. Una compra modelada en varios sólidos es UNA fila**: un grupo cuyo nombre lleva
  «(compra)» se compra entero (una fila por grupo igual: su designación, cantidad = grupos
  iguales). Sus sólidos no salen sueltos en la BOM, el costeo ni la cédula. Así quedan la bisagra
  de dos hojas, el compás y el kit de desagüe. Se declara con `create_group`, nunca se adivina por
  contacto.
- **D6. Ítem nuevo `apoyo.capacidad`** («Cada apoyo a tierra de compra resiste su reacción»):
  - con una pata, un pie nivelador, una garrucha o una rueda de compra (catálogo con
    `capacidad_kg`, o a mano con la capacidad en su designación: «(compra, 1000 kg)»), la
    reacción de `anchor_loads` × FS 1,5 (criterio de diseño) tiene que ser ≤ su capacidad;
  - sin capacidad conocida → FALLA, salvo que se JUSTIFIQUE por escrito
    (`calidad/justificadas.py`).
- **D7. Distancias en madera por EN 1995-1-1 §8.5–8.7** (tablas 8.2, 8.4 y 8.6), en el mismo
  `borde_agujero.py` (una medida para la puerta y para el criterio 5 de `join_bolted`):
  - con la pieza de madera (`materials.es_madera`), se mide la distancia del eje a la testa
    (a3,t / a3,c) y al canto (a4,t / a4,c) según el elemento: perno, tirafondo o tornillo ≤ 6 mm
    como clavo;
  - extremo cargado o no: lo decide la dirección de la carga de la unión (`loads`) y, sin ella,
    se asume cargado (el lado seguro).

  Si la F0 muestra que el mínimo de norma (p. ej. a3,t = max(7d, 80 mm) en pernos) rechaza
  uniones de mueble que el revisor dio por buenas, la alternativa vetable es un criterio de
  diseño declarado (4d a testa, 3d a canto), escrito como tal y nunca como cita de norma.
- **D8. `union.retencion` cubre el eje que gira** (mismo modo de falla: la tuerca se va). Un
  perno o pasador que es eje de una junta de giro (`services/calidad_juntas.py`; perno coaxial
  con la junta, ± 1 mm) cumple sólo si:
  - lleva tuerca autoblocante (DIN 985 / ISO 7040), contratuerca, pasador de aletas o anillo de
    retención;
  - y es un perno o pasador, no un tirafondo ni un tornillo de madera.

  En otro caso, FALLA. Se amplía el ítem existente en vez de sumar uno nuevo.
- **D9. Ítem nuevo `higiene.limpiable`, sólo en equipo higiénico.** Aplica con el requisito
  `higienico: true` (`Document.requirements`, validado en `requisitos.py`; la ficha del encargo
  lo declara). Entonces:
  - cada par soldado con contacto LINEAL medido (`calidad_contacto`) tiene que estar soldado en
    todo el contacto, salvo una holgura ≥ 3 mm que se limpia (EN 1672-2 / ISO 14159), o tiene
    que declarar su sellado sanitario;
  - todo tubo abierto de la estructura se cierra soldado.

  Sin el requisito, NO_APLICA: una mesa de taller no paga la regla.

## Alternativas descartadas

- **Más rondas de corrección** (subir el tope de 3): el revisor trae hallazgos nuevos en cada
  ronda; cada ronda (corrección + re-revisión) costó en promedio ¾ de un modelado y no converge.
- **Darle al modelador la lista en el brief y nada más**: ya está en las lecciones de modelado y
  se olvida. Lo que no mide la puerta reaparece; lo que mide, no.
- **Que el revisor a ciegas reciba los ítems de la puerta**: deja de ser a ciegas, y lo que hay
  que frenar es al modelador, no al revisor.
- **Un ítem por máquina** («bolas con código», «pie de mesa de soldadura»): rompe la regla de
  ítems generales por modo de falla.

## Fases

Cada fase sube `VERSION_REGISTRO` con su motivo en el docstring del registro y trae tests de
unidad y de un `.apolo` real (se saltan sin `C:\t\maq`, como en `test_bom_compra_fiel.py`).

- **F0 (S, sólo lectura): medir antes de tocar.**
  - Correr la puerta y la BOM de `main` sobre el `.apolo` final de los 9 pilotos y sobre los
    testigos (faja 38, puerta plegable 28).
  - Clasificar cada ALTA y MEDIA de TODAS las rondas (≈ 60) en tres grupos: ya cubierto por
    `main`, cubierto por una D de aquí, o propio de la máquina.
  - Contar cuántas piezas de los testigos fallarían con D1, D4, D6, D7 y D8 (los falsos positivos
    posibles).
  - Sale una tabla en la Bitácora. Una D que no gane ningún hallazgo se cae; una que tumbe un
    testigo sano se ajusta antes de F1.
- **F1 (M, `library/materials` + `calidad` + `services`): D1, D2, D3.** Depende de F0.
  Verificación: la silla da ~0,62 kg por tijera de haya; una pieza de «cedro» (sin tabular) falla
  `material.conocido`; la plancha de la Ø28 sale ASTM A36 en la BOM; los testigos sin cambio.
- **F2 (M, `library/bom*` + `designacion_comercial` + `calidad`): D4 y D5.** Depende de F1 (la
  norma de D3). Verificación:
  - la varilla de la escalera sale con 482 mm;
  - la bisagra de la mesa plegable sale como 4 filas y no 8;
  - la bola de la mesa de bolas falla `bom.comprable` hasta tener designación.
- **F3 (S, `library/engineering/installation` + `calidad`): D6.** Independiente de F1–F2 y puede
  ir en paralelo. Verificación: el pie nivelador de la Ø28 falla sin capacidad y pasa con
  «(compra, 1000 kg)»; un pie de catálogo con `capacidad_kg` pasa solo.
- **F4 (M, `library/borde_agujero` + `calidad/bordes` + `commands/union_taller`): D7.** Depende
  de F0 (el criterio a usar). Verificación: los pernos M6 de la mesa plegable a 2,5d de la testa
  fallan; una unión de la puerta plegable 28 que el revisor no marcó pasa (o la F0 justificó por
  qué no); `join_bolted` en madera rechaza la posición con el mínimo.
- **F5 (S, `calidad/agarre` + `services/calidad_juntas`): D8.** Independiente. Verificación: los
  pivotes DIN 934 de la escalera fallan; con `join_bolted(tuerca="din985")` pasan; el tirafondo
  como eje de la silla (de la ronda 1) falla.
- **F6 (M, `requisitos` + `services/calidad_contacto` + `calidad`): D9.** Independiente.
  Verificación: la mesa inox con `higienico: true` falla por la repisa (240 de 1 100 mm) y por el
  tope de pata; con soldadura continua pasa; la mesa de soldadura no aplica.
- **F7 (S, receta de pilotos): verificar con máquinas.** Repetir 2 pilotos del lote (uno de
  madera y uno de inox) con la puerta nueva, desde el encargo. Se mide:
  - cuántas rondas hacen falta para converger, contra 3 y sin converger;
  - el costo y los minutos de cada uno;
  - cuántos MEDIA del revisor quedan del tipo que ahora mide la puerta (meta: 0).

Tamaño: 6 fases de agente (≈ 40–65 min cada una con sus suites) más revisión y merge por lote.
F1→F2 y F0→F4 van en serie; F3, F5 y F6 pueden ir en paralelo (máx. 3 agentes por PC).

## Lo que este plan NO hace

- No toca los defectos de una sola máquina (riostra de portal, juego de montaje de orejetas,
  geometría del rebosadero): siguen siendo del revisor.
- No vuelve a hacer lo de [bom-de-compra-fiel](bom-de-compra-fiel.md) (chapa, corte medido,
  tuercas, arandelas).
- No cambia la receta de pilotos ni el revisor a ciegas (eso vive fuera del núcleo); F7 sólo la
  usa.
- No agrega rigidez lateral de pórticos ni FEA de ensamblaje a la puerta: no se repitió lo
  bastante para justificarlo (la F0 lo vuelve a contar).

## Riesgos

- **Las máquinas aprobadas en v19–v21 caen al subir el registro**: es lo buscado, pero
  re-publicar cuesta. Mitigación: la F0 cuenta cuántas caen y por qué; la fábrica re-corre sólo
  la puerta, y una corrección dirigida se arma con la lista de ítems en FALLA.
- **D7 vuelve imposible el mueble** si el mínimo de norma está pensado para estructuras: la F0 lo
  mide sobre la puerta plegable 28 y los pilotos de madera antes de elegir; la alternativa ya está
  escrita como vetable.
- **D5 fusiona lo que no es una compra** si alguien agrupa piezas fabricadas con «(compra)»: el
  grupo-compra sólo admite sólidos sin taladros de `join_bolted` hacia piezas de fuera del grupo
  (si no, falla con el motivo).
- **D1 tumba proyectos viejos con materiales de nombre libre**: la BOM y la masa siguen
  funcionando (con el default, como hoy). Sólo la puerta de publicación lo exige; el resto avisa.

## Bitácora
