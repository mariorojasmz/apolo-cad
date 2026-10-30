---
estado: en curso
nota: contrato APROBADO por Mario (2026-10-29) y revisado por el escritorio (R1–R4). F0 medida (90 hallazgos, 27 los gana una D; ajustes vetables a D1, D3, D4, D6 y D7 con criterio 4d/3d). MERGEADAS F5 (registro v22), F1 (v23), F3 (v24; el historial de versiones salió a calidad/historial_registro.py), F2 (v25, bom.comprable) y F4 (v26, distancias en madera). En curso (agente) - F6 (D9); sin lanzar - F7
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

### F1 (2026-10-29)

D1, D2 y D3 con los ajustes de la F0. Registro **v23** (la F5 entró antes con la v22: renumerado al mergear).

- **D1** `material.conocido` (familia proceso, `calidad/material.py`; su insumo es
  `fabricacion.desconocidos` de `services/puerta_hechos.py`): toda pieza a medida cuyo material,
  resuelto con el vertical como la BOM, no reconoce `known_material` FALLA con la lista. Sólo la
  densidad, como propuso la F0. Fuera de la puerta nada cambia. El defecto sembrado es la ménsula
  en «cedro».
- **D2** maderas tabuladas antes de «madera», con la cita junto a cada cifra en `materials.py`.
  Todas son madera limpia, la misma base que copaiba:

  | clave (también casa) | ρ kg/m³ | E MPa | MOR MPa | fuente |
  |---|---|---|---|---|
  | `haya` («fagus») | 717 | 11 900 | 103 | Wood Handbook FPL-GTR-190 (2010), tabla 5-3a «Beech, American» 12 %: G₁₂ 0,64 → ec. 4-12 |
  | `radiata` («pino radiata», «Pinus radiata») | 504 | 10 200 | 80,7 | FPL-GTR-190 tabla 5-5a: Gb 0,42 → ecs. 4-11 y 4-12 (el ejemplo del fresno del cap. 4 lo valida: 0,55 → 0,605) |
  | `eucalipto` («eucalypt») | 847 | 22 270 | 124,1 | Crespo et al. 2020, *Materials* 13(4):906, tabla 1 (E. globulus, EN 408, 10,2 % de humedad) |

  Lo que NO tiene fuente, dicho:
  - **Costo**: ningún valor citable. Las tres llevan el de la madera genérica (1,2 USD/kg,
    referencial) con esa nota, nunca el del acero por defecto.
  - **Haya europea**: la tabla no trae *Fagus sylvatica*. Se usa la americana, del mismo género.
  - **Eucalipto**: el Em de 22,3 GPa es de probetas limpias y queda muy por encima de una clase
    estructural (D40 de EN 338: 13 GPa). Es la misma base limpia de las demás. Vetable: si la
    flecha de una pieza de eucalipto decide, bajar a la clase.
  - El pino sin especie («madera de pino», 16 piezas de la silla) sigue siendo la madera
    genérica: no se asume radiata.
- **D3** `bom_compra.norma_de_material`, la misma función que ya usaba la chapa con ficha
  (`norma_de_chapa` la llama con forma «plancha»):
  - lo declarado gana: la norma del material o del nombre, con el grado aparte («ASTM A554 (AISI
    304)»), o un grado pelado («A36» → ASTM A36, «S355J2» → EN 10025-2 S355J2);
  - si no, la FORMA por el rol: tubo, inox ASTM A554 / acero ASTM A500 / aluminio B221; barra,
    inox ASTM A276; el resto, plancha A240 / A36 / B209;
  - el grado es el que usa el cálculo (`GRADO`: AISI 304, 6061-T6; A36);
  - un material calificado sin base («acero zincado») y lo no metálico quedan sin norma: la madera
    y lo comercial son de la F2 (D4).

Decisiones vetables:

- La forma sale del ROL (anclado, o «tubo 40x40…» / «barra cuadrada…» descrito), no de la
  geometría: un tubo a medida llamado «Pata» sale como plancha A36.
- El tubo de acero al carbono es «ASTM A500» sin grado: todos sus grados tienen Fy ≥ 250 MPa, el
  valor que usa el cálculo.

**Cifras** (los 9 finales, núcleo):
- `material.conocido` falla en 0 pilotos (la F0 contaba 4 tijeras de haya);
- la tijera pesa 0,63 kg y no 6,9: la BOM de la silla pasa de 33,5 a 8,41 kg;
- toda fila a medida de METAL sale con norma. Las mesas de bolas, inox, poza y soldadura quedan
  con 0 filas a medida sin norma; las que quedan sin norma son madera, lona e insertos zincados;
- en la Ø28, la plancha sale **ASTM A572 Gr.50**, el grado que declara su material, y faldones,
  nervios y orejetas salen ASTM A36. El texto de F1 decía «la plancha sale A36»: era de las
  rondas sin grado, y lo declarado gana (F0).

Testigos públicos re-congelados: sólo la versión 21 → 22 y `material.conocido` OK (faja 38
piezas a medida, rodillos 84, ménsulas 1 y 2). D3 movió a propósito tres congelados:
- la fila del eje «con anillos DIN 471» ahora lleva ASTM A36 (`test_bom_designacion`);
- la lámina 4 del manual chico nombra la norma de la tapa (`test_manual_rapido`);
- el costeo de la mesa de `test_cotizacion_notas`: con el campo `norma` vacío da la firma de
  antes (medido), y las cuatro firmas de hojas de la cotización no cambian. Los tests de la silla y de la Ø28 leen
`APOLO_PILOTOS` o `C:\t\maq`; sin el archivo, se saltan. Visto de paso, fuera de alcance: un
material «acero zincado … con anillo de nylon» (la DIN 985 de la silla) resuelve a poliamida
por el `\bnylon\b` de `_norm`.

### F3 (2026-10-29)

Entró `apoyo.capacidad` (familia estructura, registro **v24**: F5 y F1 entraron antes con la v22 y
la v23; al mergear, el historial de versiones salió del docstring a `calidad/historial_registro.py`
para que `registro.py` siga bajo 500 líneas), con los ajustes D6 de la F0:

- criterio puro en `library/calidad/apoyos.py` (con su `ENTRADA`, como `contacto.py`); la medida
  en `services/calidad_apoyos.py`, que es también el detector `apoyos_de_compra` de
  `puerta_hechos` (el `aplica_si`) y el insumo `apoyos_compra` de `reunir`;
- **qué es un apoyo de compra**: una ref de las categorías `pies_niveladores`, `garruchas`,
  `patas` o `ruedas`, o una pieza a mano que se compra (`es_comercial`: «Pie nivelador»,
  «Nivelador» o la marca «(compra)») cuyo rol, anclado al inicio, es pie, nivelador, pata,
  garrucha, rueda o regatón. Guarda: «Pie de amigo», «Pata de cabra» y «Rueda dentada / de cadena /
  motriz…» no son apoyos. Un perfil de catálogo que hace de «Pata» se fabrica y no entra (lo mide
  `estructura.pandeo`). Sólo los ANCLADOS: la reacción es la de `anchor_loads`;
- **reacción**: la de `installation_data` (masa de toda la máquina + `carga_kg` de los requisitos,
  peso en el COG, sin la tornillería anclada) × FS 1,5, declarado como criterio de diseño. La masa
  se calcula sólo si algún anclaje es un apoyo de compra;
- **capacidad**: `capacidad_kg` o `carga_kg` de la ficha (en la garrucha, la de rodadura, la menor)
  o, a mano, un «N kg» DENTRO del paréntesis de la compra («(compra, 1000 kg)») o detrás de
  «carga», «capacidad», «admisible» o «nominal» («carga estática ≥1000 kg», el nombre final de la
  Ø28). Acepta «1.000 kg»;
- sin capacidad → FALLA, salvo justificación por escrito con la regla «apoyo de compra sin capacidad
  declarada» (por pieza o para todos); una capacidad que no alcanza no se justifica; un apoyo a
  tracción no pide capacidad (es de `estructura.vuelco`);
- defecto sembrado `pie_sin_capacidad` (un pie «(compra)» anclado junto a la ménsula atornillada).
  Tests en `tests/test_apoyo_capacidad.py` (la Ø28 real, buscada en los repos hermanos, se salta
  sin el archivo).

Decisiones vetables:

- **Un «N kg» suelto en el nombre no es capacidad**: «Pie para la mesa de 500 kg (compra)» puede ser
  la carga de la mesa. Sólo cuenta en el paréntesis de la compra o tras una palabra de capacidad.
- **Sólo los apoyos anclados.** Los 4 pies de catálogo del testigo de rodillos se apoyan en la placa
  de piso, que es la anclada: no se evalúan (pendiente: seguir el camino de carga hasta el anclaje).
- **La carga excéntrica (#69) queda pendiente**: no hay requisito estructurado de carga de canto (la
  Ø28 lo escribe en `notas`). La evidencia DECLARA la hipótesis («un canto cargado no se evalúa»).
  Sumar `carga_canto_kg` a `requisitos.py` es otra fase (cambia también `estructura.vuelco`, #53).

Cifras:

- testigos: sólo cambian la versión y el ítem nuevo (faja OK con sus 4 PIE-M12-50, 224 kg pedidos
  ≤ 350; ménsulas y rodillos NO_APLICA), re-congelados a propósito;
- Ø28 real: con «(compra)» solo, 4 en FALLA (pide 296–297 kg); con «(compra, 1000 kg)», OK;
- los 9 finales: OK la Ø28; FALLA la mesa de bolas (4 pies, TP de #29), la poza (4 pies «Pie
  nivelador … inox» sin carga que nadie marcó) y la mesa plegable (4 regatones PE anclados: los
  otros 2 de la F0 no están anclados). Los 2 tacos de pared de la F0 ya no cuentan (no son apoyos).
  Esos 8 sin marcar se arreglan con la carga en el nombre o una justificación;
- la puerta de la Ø28 tarda ≈ 2,2 s en `reunir` (sin gravedad ni sobrantes).

### F2 (2026-10-29)

D4 y D5 con los ajustes de la F0. Registro **v25** (F4 sube en paralelo: quien mergee renumera).

- **D4** `bom.comprable` (familia proceso, `calidad/comprable.py`; el criterio por fila es
  `library/bom_comprable.motivo`, puro; el insumo, `services/calidad_bom.insumo_bom` sobre la MISMA
  BOM de `/api/bom` y del costeo):
  - compra: norma o designación (`norma_del_nombre`), la designación MEDIDA de la banda sin fin o el
    código de fabricante (`designacion_comercial.codigo_de_fabricante`: «tipo Marca código»,
    «(compra, Marca código)» —sólo junto a la marca— o «ref. código»; una sigla de norma no es
    marca). La que se pide por largo (`se_pide_por_largo`: varilla, barra, perfil, tubo, pletina,
    cable, cadena, listón), además su largo;
  - ref de catálogo: la ref es el código; la cortable, con su largo;
  - chapa con ficha: espesor y desarrollo;
  - a medida de METAL o MADERA (por la cabeza del material, antes del primer paréntesis: «lona …
    (densidad asimilada a madera)» es lona): su norma. Caucho, lona, plástico y cable no la piden.
- Lo que la BOM ahora lee (BOM, costeo y cédula: la misma fila):
  - la compra por largo lleva el nominal o, sin él, el MEDIDO (la clave de la fila lo incluye):
    la varilla M8 DIN 976-1 de la escalera sale con **482 mm** (antes, sin largo);
  - la madera, la norma que ESCRIBE su material (`bom_compra.norma_de_madera`, desde
    `norma_de_material`): «clase C16 (EN 338)» → «EN 338 C16», «EN 636-2», «EN 622-5»; una clase
    pelada es EN 338 (C/D) o EN 14080 (GL). Sólo el material, en mayúsculas y con clases reales: «seca
    en 12 %» o el «D10» de un tarugo no son norma;
  - la banda sin fin lleva `designacion`, `ancho_mm` y `espesor_mm` medidos de su lazo
    (`banda_lazo.campos_banda`: «Banda sin fin de PVC, ancho 600 mm × e=4 mm, lazo 8350.6 mm»),
    sin tocar la descripción ni la geometría de `create_belt_conveyor` (sin bump);
  - la compra con código lo lleva en `codigo`.
- **D5** `library/compra_grupos.py`: un grupo cuyo nombre (último tramo) lleva «compra» en un
  paréntesis se compra ENTERO. Sus miembros DIRECTOS no salen sueltos en BOM, costeo, cédula ni
  lista de corte; una fila por grupo igual (misma designación —el nombre sin la marca ni el sufijo
  «(n)»— y las mismas piezas por ref y volumen), con `grupos_compra` e `incluye`. Norma: la del
  nombre o, si todos sus sólidos son de catálogo con la misma norma, ésa (las medias bisagras: EN
  1935). Un grupo con un sólido taladrado por un `join_bolted` hacia una pieza de fuera falla
  `bom.comprable` con el motivo (se lee de los `fasten` de cada `join_bolted`); la BOM igual lo
  fusiona (la declaración manda; la puerta frena).
- Defecto sembrado `compra_sin_designacion` (una bola «(compra)» en la ménsula). Tests en
  `tests/test_bom_comprable.py` (escalera, mesa plegable y mesa de bolas reales: se saltan sin el
  archivo).

Decisiones vetables:

- **El nombre de un grupo no admite comas** (`create_group`): «(compra, Marca código)» no se puede
  escribir ahí; el código de un grupo va «tipo Marca código (compra)».
- **Un metal sin base es FALLA** («acero zincado»: los 4 insertos roscados de la silla). La F0 los
  contaba con lo no metálico; son piezas que se compran y piden «(compra)» con su código.
- **El costo de un grupo** se estima como el de toda compra a mano (peso total × material × 3), no
  como la suma de las fichas de sus sólidos: el precio es del kit, a cotizar.
- La banda: tipo = su material; las capas no se inventan (el sólido no las dice).
- La BOM fusiona un grupo «(compra)» aunque `join_bolted` lo taladre: la falla la da la puerta.

Cifras (`bom.comprable` sobre los 9 finales, núcleo):

- **70 filas en FALLA en 7 de 9** (pasan las dos mesas de soldadura; la Ø28 por «tipo Ganter GN
  343.1»):
  - 48 de madera sin norma ni clase (escalera 8, estantería 16, silla 24 con las tijeras y los
    tarugos de haya): el modo de #21/#52;
  - 4 de metal sin base (los insertos de la silla);
  - 18 compras sin norma ni código: la bola y el pie de la mesa de bolas (#25/#29), la tuerca de
    barril, los tacos S6, los 4 pies higiénicos, el sifón, los 5 del compás y 3 de regatones y
    deslizadores PE. Los del compás y la bisagra se arreglan con D5.
- Las 18 filas con la norma escrita en el material (mesa plegable 16, estantería 2) ya la leen.
- La bisagra de la mesa plegable, con 4 grupos «Bisagra de pala 100 (compra)»: UNA fila de 4 (EN
  1935) en vez de 4 + 4 medias bisagras.
- **Testigos**: sólo la versión 24 → 25 y `bom.comprable` OK (faja 46 filas, rodillos 45, ménsulas
  1 y 4), re-congelados a propósito.

### F4 (2026-10-29)

Entró D7 con el criterio que eligió la F0. Registro **v25**: F2 sube en paralelo, quien mergea
renumera. No hay ítem general nuevo: `union.distancia_al_borde` suma dos orígenes.

- **Una medida** (`library/borde_agujero.py`: `veta` y `medir_madera`) para la puerta y para
  `join_bolted`. Mide desde el eje, en el plano medio del tramo, hasta donde se acaba la madera:
  - **testa ≥ 4·d** y **canto ≥ 3·d**, con d el Ø del perno o del tornillo. Es un criterio de
    diseño con los mínimos DESCARGADOS de EN 1995-1-1 tabla 8.4 (a3,c = 4·d, a4,c = 3·d) aplicados
    a todo extremo. Nunca se cita como el mínimo del extremo cargado;
  - **tornillo en la testa**: eje a < 45° de la veta. Es criterio de diseño, apoyado en EN 1995-1-1
    §8.3.2(4), que niega carga axial a un clavo en la testa. No tengo la cláusula exacta de los
    tornillos, así que no se cita.
- **Puerta.** `services/calidad_bordes.py` saca la madera de la tabla 3.3 de chapas (antes se
  juzgaba con 1,2·d0). Dos controles en `calidad/bordes.py`, `borde.madera` y `borde.testa`. Cada
  falla nombra la pieza, el perno, el lado y la distancia medida y la pedida.
- **Tornillos de madera sin hexágono** (`services/calidad_tornillos_madera.py`): los 128 que la
  F0 dejó sin medir. Eje = su vástago; cabeza = el extremo más ancho (la avellanada). Sólo los
  mide la madera: ni agarre ni paso. El detector `tornilleria_madera` hace aplicar el ítem
  cuando el modelo sólo tiene esos tornillos (`hay_alguno`).
- **`join_bolted` criterio 7** (`commands/union_madera.py`, sello de todo comando nuevo):
  - el patrón automático en madera se aleja 4·d según la veta y 3·d de través, menos lo que la
    pieza sigue más allá de la huella;
  - si no cabe, el error de la huella dice «en madera (4·d según la veta, 3·d de través…)»;
  - después del taladro se mide como la puerta: un agujero bajo el mínimo (una muesca que la caja
    no ve) o el tornillo DIN 571 que roscaría en la testa es un error accionable.

  Los criterios 1–6 guardados regeneran igual. No hubo `version`: el criterio viaja en los params.
- **Defecto sembrado** `perno_en_la_testa_de_madera`: dos listones con un M6 a 2,5·d de su testa.
  Con la tabla de chapas pasaba.

Decisiones vetables:

- **Veta** = el eje de menor momento de inercia de la pieza. Si I_min > 0,8·I_medio (un tablero
  cuadrado, un taco) no hay veta reconocible y se pide 4·d hacia todo lado.
- **Testa y canto por dirección**: los rayos a ≤ 20° de la veta miden la testa y los de ≥ 70°, el
  canto. Las diagonales no cuentan.
- **Cuándo rosca en la testa**: con rosca medida, o con la punta en esa pieza y siendo tornillo o
  perno sin tuerca. Un perno con tuerca a lo largo de la veta sólo aprieta: sale `a_lo_largo`, se
  cuenta y no se juzga. Así queda el cabezal de la escalera, con tuerca de barril. El perno en un
  inserto roscado en la testa (silla, corrección 1, ALTA del revisor) sí falla.
- **El paso en madera** sigue siendo el 2,2·d0 de la chapa. Pendiente: a1/a2 de EN 1995-1-1.
- **El tornillo sin geometría reconocible** (`sin_geometria`) se cuenta y nunca bloquea.
- **La arandela sobre madera (§10.4.3) no entró**: no salió barata. Pide saber de qué lado está
  cada arandela, su Ø y su espesor frente a d, por pieza. Va con el cálculo de madera.

**Cifras** (núcleo, `.apolo` finales de los 4 pilotos de madera de los repos hermanos):

| piloto | agujeros en madera | fallan | en la testa | en nudos que marcó el revisor | sin marcar |
|---|---|---|---|---|---|
| escalera | 80 | 68 | 24 | 32 | 36 |
| estantería | 232 | 68 | 0 | 40 | 28 |
| mesa plegable | 88 | 30 | 0 | 22 | 8 |
| silla | 22 | 18 | 0 | 8 | 10 |
| **total** | **422** | **184** | **24** | **102** | **82** |

«Agujero» = un perno o tornillo en una pieza de madera. La F0 contaba 158 (sólo los de hexágono);
ahora entran los tornillos sin hexágono.

- **Marcados** (en alguna ronda):
  - escalera: los 24 tornillos del peldaño en la testa (#1, #5) y los 8 pernos del cabezal a 2·d
    de su testa (#3);
  - estantería: los pernos larguero-montante a 3,33–3,75·d (36, #18) y el tornillo de la escuadra
    a 2,38·d del canto (4, #23). El revisor midió 7,5 mm a la superficie del tornillo; el eje está
    a 9,5 mm;
  - mesa plegable: los travesaños a 3,5·d (16, #58) y la zapata a 2,5·d (6, #59);
  - silla: las tijeras (8, el nudo de #85, hoy a 2,75·d del canto).
- **Sin marcar**, todos bajo el mínimo de verdad, entre 2,25 y 3,56·d:
  - escalera: tornillos del peldaño a 2,65·d del canto del larguero (24), los de bisagra Ø6 a
    2,25·d (8) y los M6 de zapata a 2,54·d de la testa (4);
  - estantería: tornillos entrepaño-larguero a 2,38·d del canto (28);
  - mesa plegable: tornillos de las placas del compás, a 2,25–3·d (8);
  - silla: M10 a 2,25·d del canto de patas y separador (6) y tirafondos del travesaño a 3,56·d de
    la testa (4).

  Se arreglan con menor Ø, el agujero más adentro o un listón más ancho, como anticipó la F0.
- **Rondas**:
  - silla, modelado: `borde.testa` FALLA con 18 tornillos en la testa, entre ellos los 4
    tirafondos pivote (ALTA de la ronda 1);
  - silla, corrección 1: los 4 pernos en insertos de la testa del larguero (ALTA);
  - mesa plegable final: los M6 de la zapata a 2,5·d de la testa fallan;
  - estantería, modelado: sin tornillería, NO_APLICA.

  Tests en `tests/test_bordes_madera.py`; los de los pilotos se saltan sin el archivo.
- **Costo.** En la estantería (128 tornillos más), `insumos_bordes` pasa de 0,2 s a 5,0 s de CPU
  (`process_time`, con los hilos de OCCT); con cProfile mide ≈ 0,7 s.
- **Testigos**: sólo `version_registro` 24 → 25. Ninguno es de madera.
- **Puerta plegable 28**: no se re-midió. Está en la copia de uso, que esta fase no toca. Queda
  para quien mergee, como pidió la F0.
- **Suite completa** en el worktree (laptop, sin `-n`, ≈ 65 min): exit 0, sin FAILED. `ruff check`
  limpio; `test_negocio_fuera` y `test_claude_md` en verde (`library/CLAUDE.md` quedó a 35 815 de
  35 840 bytes: se podaron frases para que entre la regla de la madera).
