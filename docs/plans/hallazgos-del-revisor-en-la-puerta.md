---
estado: en curso
nota: contrato APROBADO por Mario (2026-10-29) y revisado por el escritorio (R1–R4). F0 medida (90 hallazgos, 27 los gana una D, ninguna cae; ajustes vetables a D1, D3, D4, D6 y D7 con criterio 4d/3d). F5 MERGEADA (registro v22). F1 en curso; F2–F4 y F6–F7 sin lanzar
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

### Revisión del escritorio (2026-10-29)

Nada en vuelo choca con las D. Ajustes, vetables:

- **R1 (D1).** `materials.known_material()` ya existe (2026-10-29, `fdfa5b5`/`00360ca`): concreto,
  acetal, PE-UHMW, PP y PA están tabulados, y `set_material` devuelve `aviso_material` cuando el
  material cae a la densidad del acero. `material.conocido` usa ESA función, no otra lista. Los
  números de línea citados arriba de `materials.py` se movieron.
- **R2 (D4).** Una fila a medida con OTRO material asignado ya sale «en acero inoxidable (la ref de
  catálogo es de acero ASTM A500 Gr.B: pedir la equivalente)» (`material_compra.py`) y alcanza
  para comprar. `bom.comprable` la acepta tal cual. Un revisor a ciegas marcó tres veces esa
  misma fila como «BOM que no compra inox», pero leyó la ficha del catálogo, no la BOM: no es un
  hallazgo para la puerta.
- **R3 (D9), más evidencia.** Una lavadora de bandejas de ~645 piezas (6 rondas en el escritorio)
  repitió los dos modos de D9: tubos de patas y postes abiertos arriba en zona húmeda (ronda 5,
  BAJA), y el tanque y el túnel de secado que no se abrían para limpiar (rondas 4 y 5, ALTA). Lo
  segundo es ACCESO de limpieza, no rendija: D9 NO lo suma (sin una medida general que no sea
  sobrediseño), queda para el revisor.
- **R4 (orden).** F0 y F5 arrancan ya (F5 no depende de la F0). F3 y F6 van cuando una de las dos
  vuelva (máx. 3 agentes contando el modelador de la flota); F1 → F2 y F4 esperan la F0.

### F0 (2026-10-29)

Sólo lectura, sobre `main` en `66b503a`, núcleo sin extensiones. Se midió:

- la puerta (`scripts/testigos.py` en proceso) y la BOM sobre el `.apolo` final de los 9 pilotos
  (fuera del repo) y sobre los 4 testigos públicos de `tests/data/testigos/`;
- las D candidatas con `scripts/medir_reglas_candidatas.py` (nuevo, sólo lectura) sobre los 9
  finales, los 4 testigos y las 36 rondas intermedias (`modelado`, `correccion1..3`), para ver si
  la regla habría frenado el hallazgo EN la ronda en que el revisor lo encontró.

La faja 38 y la puerta plegable 28 son de la base de uso: en su lugar van los testigos públicos
(faja, ménsula, ménsula atornillada, rodillos). **Ninguno es de madera**: D7 no tiene testigo sano
de madera, y la puerta plegable 28 sigue pendiente para F4.

**La puerta de hoy (registro v21, núcleo).** 8 de 9 pilotos siguen APROBADOS. La mesa de bolas cae
por `entrega.semaforo` e `ingenieria.reglas`: «barreno sin perno» en las 4 tapas de pata Ø13
(el espárrago del pie articulado modelado a mano no cuenta como tornillería). Con la v19 + la
extensión había pasado. No se investigó: queda para quien toque el lint. De los testigos, faja y
ménsulas APROBADOS y rodillos NO: los 4 IGUAL a lo congelado (`scripts/testigos.py --en-proceso`).

**Hallazgos.** Los revisores dieron 90 ALTA y MEDIA (15 ALTA) en las 4 rondas de los 9 pilotos, no
≈ 60. Grupo (a) = ya lo cubre `main`; (b) = lo cubre una D tal como está escrita, verificado con la
medida de la ronda cuando la D es medible; (c) = propio de la máquina o de un modo sin D. Los `#`
son el orden de los reportes (máquina alfabética; revisor, rerevisor1..3).

| grupo | n | hallazgos |
|---|---|---|
| (a) `main` hoy | 2 | #32, #42: «pedir la equivalente» en inox ya alcanza (R2, `material_compra.py`) |
| D1 (+D2) | 1 | #89 haya pesada como acero: la silla final da 4 piezas en FALLA |
| D3 / D4 | 10 | #13 varilla sin largo (sigue en `main`); #21 y #52 madera sin clase; #33 y #71 metal sin grado; #25, #29, #57 y #60 compra sin norma ni código; #48 kit de compra que sale A-MEDIDA |
| D5 | 1 | #61 bisagra en 2 sólidos = 4 + 4 medias, compás de 5 filas |
| D6 | 1 | #70 pie de compra sin carga nominal (la ronda 2 de la Ø28 da 4 en FALLA); #29 también la gana |
| D7 | 6 | #18 (3,75d), #58 (3,5d), #59 (2,5d), #85 (2d, ronda 2 de la silla) a la testa; #23 (1,9d al canto) y #84 |
| D8 | 1 | #9: la ronda 2 de la escalera da 8 de 8 pernos de giro con tuerca simple |
| D9 | 7 | #30, #31, #34, #35, #36, #39, #40 (todos de la mesa inox; R3 suma la lavadora) |
| (c) | 61 | ver abajo |

De los 61 del grupo (c), 27 se REPITEN en máquinas distintas sin ninguna D que los mida:

| modo repetido | n | máquinas | hallazgos |
|---|---|---|---|
| cálculo estructural ausente (madera, pórtico sin riostra) | 8 | 5 | #2, #20, #28, #43, #51, #80, #83, #88 |
| tirafondo o tornillo EN TESTA (eje a lo largo de la veta) como unión o como eje | 7 | 2 | #1, #3, #5, #73, #74, #75, #78 |
| pie nivelador: carrera real, rosca enganchada, sin contratuerca ni rótula | 5 | 3 | #24, #44, #63, #66, #67 |
| lo que pliega no declara su junta ni prueba la pose plegada | 4 | 3 | #0, #7, #49, #87 |
| arandela chica o ninguna sobre la madera | 2 | 2 | #22, #55 |
| eje de giro sin traba en una máquina SIN juntas (D8 no aplica) | 1 | 1 | #76 (y #73, #78) |

Huecos de ítems que ya existen (también en c):

- #53, `estructura.vuelco` sin la carga de esquina de los requisitos;
- #69, D6 con la carga centrada: 197 kg × 1,5 < 350 kg, y el revisor usó el canto cargado;
- #8, el taco antideslizante pegado no es «desgaste» para `consumibles.reemplazables`;
- #68, el tornillo Allen encerrado no lo evalúa `union.acceso_herramienta`;
- #26, la BOM del tubo HSS no dice la pared;
- #37, ranura de 8 mm, sobre el umbral de 3 mm de D9.

Los demás son propios: función, plegado, desagüe, borne de masa y holguras.

**Falsos positivos posibles.** Piezas o filas que FALLARÍAN y ningún revisor marcó, en los 9 finales
y en los 4 testigos públicos:

| D | testigos | pilotos finales | medida |
|---|---|---|---|
| D1 con `known_material` | 0 | 4 (todas TP) | si además exige `YIELD_MPA` (texto de D1), cae la faja (banda PVC) y 19 piezas de los pilotos (caucho, nylon, HDPE, PP) |
| D4 sin D3 | faja 33 filas, rodillos 27, ménsulas 1 y 2 | 181 filas | D4 depende de D3 |
| D4 con D3 | faja 1 (la «Banda» de la plantilla, sin designación) | 97 filas | 18 tienen la norma ESCRITA en el material («clase C16 (EN 338)», «EN 636») y hoy la BOM no la lee; 48 de madera sin clase (el modo de #21/#52: TP); 10 de material no metálico ni madera (caucho, lona, inserto zincado); 13 compras con designación comercial pero sin norma ni código que el revisor aceptó (tuerca de barril M8, taco S6, pies higiénicos, sifón 1½″, regatones PE, pie «tipo Ganter GN 343.1»); 8 TP de compra o largo |
| D6 | 0 si lee `carga_kg`; faja 4 si sólo lee `capacidad_kg` | 16 sin capacidad | 4 pies de la mesa de bolas (TP); 4 pies de la poza y 6 regatones PE que nadie marcó; 2 tacos de pared que no son apoyo. La Ø28 final cumple (1000 kg en el nombre) |
| D7 norma cargada | sin madera | 154 de 158 agujeros | a3,t = max(7d, 80 mm) y a4,t = 4d rechazan todo nudo de mueble, también los que el revisor aceptó |
| D7 4d testa / 3d canto | sin madera | 108 de 158 | 66 en nudos marcados (#18, #58, #59, el cabezal de #3) y 42 sin marcar. Sin marcar: escalera, tirafondos Ø8 del peldaño a 2,65d del canto, tornillos Ø6 de bisagra a 2,25d y pernos M6 de zapata a 2,5d de la testa; silla, M10 a 2,25d del canto en un listón de 45 mm. Aparte: 32 tornillos EN TESTA en la escalera y 18 en el modelado de la silla, todos marcados. No se miden 128 tornillos de madera de catálogo sin hexágono (estantería 80, mesa plegable 44, silla 4); #23 vive ahí |
| D8 | 0 | 0 de 8 ejes (los 8 con DIN 985) | 11 juntas de giro sin perno coaxial modelado (bisagras y compases de catálogo) y la silla sin ninguna junta: no evaluables, nunca OK |

**Propuestas (vetables).** Ninguna D queda sin hallazgo: no cae ninguna. Se ajustan antes de su
fase:

- **D1**: sólo `known_material` (densidad), como dice R1. La resistencia se exige donde un
  cálculo la usa, no en la puerta; si no, la faja cae por la banda de PVC.
- **D3**:
  - la norma va por FORMA de producto: el tubo inox es ASTM A554, no la A240 de la chapa;
  - el grado o la norma que el modelador escribe en el material o en el nombre gana («A36»,
    «A572 Gr.50», «EN 338 C16»). Hoy la mesa Ø28, que declara A36 y A572, sale con la norma vacía.
- **D4**:
  - a medida: exige norma sólo al metal y a la madera; el caucho, la lona y el plástico, sólo D1;
  - compra: norma, o código de fabricante declarado. La forma «tipo Marca código» y
    «(compra, Marca código)» la lee el mismo matcher, así la Ø28 pasa;
  - las 13 filas comerciales sin código se arreglan con un nombre;
  - la «Banda» de `create_belt_conveyor` lleva su designación (tipo, capas, ancho × lazo), o la
    faja testigo cae.
- **D6**:
  - lee `carga_kg` (la clave de `97_pies_niveladores`, `110_garruchas` y `40_patas`) además de
    `capacidad_kg`;
  - aplica sólo a pie, pata, garrucha, rueda y regatón;
  - el caso de canto cargado (#69) pide la carga excéntrica de los requisitos: sin ella se
    declara la hipótesis.
- **D7: criterio 4d a la testa / 3d al canto.** Son los mínimos de extremo y borde DESCARGADOS de
  EN 1995-1-1 tabla 8.4 (a3,c = 4d, a4,c = 3d), aplicados a todo extremo como criterio de diseño
  declarado, no como cita del extremo cargado. Mide:
  - los tornillos de madera sin hexágono (si no, #23 no se ve);
  - el tornillo EN TESTA como modo propio: medido, gana 7 hallazgos y no tiene falso positivo en
    los testigos.

  Los 42 agujeros sin marcar violan de verdad ese mínimo y se arreglan con menor Ø o listón más
  ancho. Se re-mide sobre la puerta plegable 28 antes de mergear F4.
- **D8**: queda como está (gana #9). Los 3 de la silla (#73, #76, #78) los gana sólo si lo que pliega
  declara su junta, que es el modo repetido de #0, #7, #49 y #87: plan aparte.
- **D9**: no medible antes de F6. El umbral de 3 mm deja pasar #37 (8 mm).
- Fuera de este plan, por tamaño: el cálculo de piezas de madera y la rigidez de pórticos (8
  hallazgos en 5 máquinas, el bloque repetido más grande) y el pie nivelador (5 en 3) piden su
  propio plan. La arandela sobre madera (EN 1995-1-1 §10.4.3) cabe en F4 si sale barata.

### F5 (2026-10-29)

Entró D8 ampliando `union.retencion` (registro **v22**), sin ítem nuevo:

- `library/ejes_giro.py` (puro): las reglas de nombre, la recta y qué traba.
- `services/calidad_ejes_giro.py`: qué perno o pasador es eje de una junta.
- `calidad/agarre.py`: la retención de ese eje (`_con_giro`, `_pasador`).
- `calidad_pernos.py`: cada tramo «tuerca» del insumo lleva `autoblocante`.

Cómo se reconoce, medido donde se puede:

- **Eje de la junta.** Perno de `calidad_pernos` (eje de la geometría) paralelo y a ≤ 1 mm de la
  recta de una junta `giratoria`/`continua`, que toca su cuerpo padre Y su cuerpo hijo (pieza +
  juntas `fija`). Tocar = lo cruza, es del cuerpo, o el cuerpo tiene material a 1,2·d del eje
  dentro del largo del perno (anillo de 8 rayos). Así entra el brazo que gira sobre un BUJE (el
  codo de la escalera) y no el perno coaxial en la punta del eje fijo de un rodillo.
- **Traba.** Tuerca autoblocante por la ficha (`specs.tipo`/`norma`: `TUERCA-AB-*` de
  `join_bolted(tuerca="din985")`) o por el ROL anclado de una tuerca a medida (DIN 985 / 982 /
  980, ISO 7040 / 7042 / 10511…). Contratuerca = dos tuercas en el eje a ≤ 1 mm, por geometría.
  Pasador de aletas o anillo de retención por el rol anclado, tocando la caja del perno.
- **Tirafondo.** Ficha `tornilleria_madera` o rol «Tirafondo…», «Tornillo para madera…», DIN 571:
  FALLA siempre como eje.
- **Pasador o bulón sin cabeza** (rol anclado) y tornillo de madera sin llave: los que
  `calidad_pernos` no mide entran por sus caras cilíndricas coaxiales y tocan los cuerpos por caja.

Decisiones, vetables:

- La altura de la tuerca NO decide que sea autoblocante: una DIN 985 mide ≈ 1·d y una tuerca alta
  DIN 6330 también. Decide la ficha o el nombre.
- Una tuerca fundida en el sólido del perno es autoblocante sólo si lo dice el nombre del perno.
  Si no, es una tuerca simple y FALLA (no SIN_EVALUAR): se ve y nada dice que trabe.
- Un pasador o bulón con retén y sin tuerca ni rosca deja de ser «nada lo retiene», pero sólo si
  es eje de una junta. Fuera de una junta, el veredicto no cambia.
- Sin junta declarada no hay eje. Un pivote que cierra un lazo (el tirante trasero de la escalera,
  fijo con `fija` porque la FK es un árbol) o un modelo sin juntas (la silla final) no se juzga.

Cifras:

- **Escalera de tijera real** (repo de máquinas): 5 juntas de giro, 50 pernos, 4 ejes (pivotes
  delanteros y codos). Pasan por su «Tuerca autoblocante DIN 985» a medida. Con la tuerca renombrada
  a DIN 934, falla el pivote que la lleva (`tests/test_puerta_eje_giro.py`, se salta sin el
  archivo).
- **Falsos positivos.** Barrido de los 19 `.apolo` de `C:\t\maq` (hasta 21 juntas de giro, como
  los rodillos con cadena y la lavadora) y de los 9 pilotos: 0 ejes fuera de la escalera.
- **Costo.** Marcar los ejes de la escalera: 0,09 s; sin juntas, 0.
- **Testigos.** Sólo cambió `version_registro` 21 → 22, ningún ítem.
- **Defecto sembrado.** `pivote_sin_traba` (ménsula atornillada + `join_bolted` DIN 934 +
  junta coaxial) atrapa `union.retencion`; sin la junta, la misma unión pasa.
- **Suite completa** en el worktree (escritorio, sin `-n`): exit 0, sin FAILED. `ruff check` limpio y
  `test_negocio_fuera` en verde.
