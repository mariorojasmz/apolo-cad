---
estado: en curso
nota: contrato aprobado por Claude (delegado por Mario, 2026-10-30); F0, F1 (catálogo y ficha en la BOM) y F3 (sin compra doble) mergeadas; falta la F2 (evaluador) y la F4 (verificar)
descripcion: La puerta revisa que cada pie nivelador se pueda enroscar, quede trabado y nivele lo que pide el piso, y el catálogo trae los pies que el mercado vende
---

# La puerta revisa que el pie nivelador nivele de verdad

## Estado y origen

Contrato escrito y aprobado por Claude con la delegación de Mario (2026-10-30: «crea los planes, los apruebas tú y lo implementas, te doy permiso»); las D siguen vetables por él.

Lo manda a plan aparte [puerta-fuera-de-catalogo](puerta-fuera-de-catalogo.md) § «Lo que se revisó»
(contrato aprobado por Mario el 2026-10-30): «Pie nivelador (contratuerca, carrera real, rosca
enganchada) […] pide su propio análisis de mecanismo: van con plan aparte». Rigen las dos reglas de
ese plan: la calidad va en código determinista, no en la memoria del agente, y la regla es general
(un pie nivelador es un componente de catálogo con su evaluador, como el tensor), no de una familia
de máquinas.

Evidencia: la misma tanda de 15 máquinas (modelado → revisor a ciegas → puerta → hasta 3 rondas de
corrección → re-revisión a ciegas), re-evaluada con la puerta v32. **9 de las 15 llevan pie
nivelador** y en **6** el revisor a ciegas levantó un hallazgo MEDIA sobre el pie que la puerta no
mide. La puerta v32 sólo mira su capacidad (`apoyo.capacidad`), y no en todas.

## El problema / lo que hay hoy

### Lo que vio el revisor (y la puerta no)

| máquina (pie) | hallazgo | reporte |
|---|---|---|
| mesa de ensamble atornillada de 1,2 m (`PIE-M10-40`) | el vástago M10 entra sólo en la rosca de una placa de 8 mm (unos 5 hilos), sin contratuerca; la BOM no trae ninguna tuerca M10 | re-revisión 1, MEDIA |
| ídem | carrera real: la ficha prometía +0/+40 mm; con placa y contratuerca sube ≈ +4 mm (+12 sin contratuerca) y baja −20 | re-revisión 2, MEDIA |
| mesa de ensamble soldada de 1,2 m (6 × `PIE-M12-50`) | placa de 6,35 mm con taladro Ø10,2 roscado: enganche 0,53·d (3,6 hilos), sin tuerca soldada ni contratuerca | re-revisión 1, MEDIA |
| mesa de trabajo soldada de 1,2 m (`PIE-M10-40`) | placa base 50×50×10 MACIZA, sin taladro: el pie no se puede enroscar (interferencia 217,9 mm³); sin contratuerca | re-revisión 1, MEDIA |
| ídem | la BOM compra `PIE-M10-40` sin largo de espiga ni carga admisible | re-revisión 3, BAJA |
| mesa inox de 2 m (pie higiénico a mano) | rosca engranada 21 mm; dejando 1·d de enganche el pie sube ≈ 11 mm, y un piso de cocina con 1–2 % de pendiente pide 20–40 mm en 2 m | re-revisión 1, MEDIA |
| ídem | el espárrago M10 del pie se compra DOS veces: una línea «Espárrago M10 DIN 267 (unión declarada sin pieza modelada)» ×4 sin largo, además del pie que ya lo trae | revisor, re-revisión 1 y 3 |
| ídem | pie y buje de soldar sin número de artículo (el buje sale «a medida») | re-revisión 3, MEDIA |
| mesa de bolas de 1 m (pie a mano M12×200) | sin código de compra; «la carrera de regulación de 750–900 depende de ese largo de rosca»; el revisor calcula a mano 32 de 36 mm de rosca enganchada | revisor (MEDIA), re-revisión 1 |
| mesa de soldadura Ø16 de 2 m (pie articulado a mano) | el pie va en dos líneas de compra (base y husillo) sin norma; «no hay categoría de pies» que respalde el largo de 110 mm | re-revisión 1, MEDIA |
| mesa de soldadura Ø28 de 2 m (pie articulado M16 a mano) | «la carrera real de nivelación del pie» no se pudo verificar: compra sin ficha | revisor (límites) |

El modelador lo dice desde el otro lado: «Pie nivelador M12 con 150 mm de carrera (el catálogo llega a
50 mm)» (mesa de bolas, modelado) y «Falta en el catálogo: un pie nivelador higiénico de inox con su
buje de soldar» (mesa inox, modelado).

### Lo que hay en el código (`main` 29ca3925)

1. **El catálogo es chico y no trae lo que se compra.** `97_pies_niveladores.yaml:5-15`: tres pies
   `PIE-M8-30`, `PIE-M10-40`, `PIE-M12-50`, acero zincado, vástago de 30–50 mm, 120–350 kg; y los
   `PIE-BA-*` de base de anclaje (`:24-36`) con `cotas_verificadas: false`. Ni articulado, ni inox
   higiénico, ni M16, ni vástago largo. El builder es un cilindro sobre un disco
   (`builders_estructura.py:53-61`): sin hexágono de llave ni tuerca de bloqueo. Resultado: 5 de las
   9 máquinas modelaron el pie a mano (mesas de bolas, inox, inox con poza, Ø16, Ø28).
2. **La puerta sólo mira la capacidad, y sólo del pie anclado.** `apoyo.capacidad`
   (`library/calidad/apoyos.py:9-29`) juzga reacción × 1,5 ≤ capacidad; su insumo recorre sólo
   `doc.grounds` (`services/calidad_apoyos.py:57-60`). En la mesa inox de 2 m el ítem sale NO_APLICA
   con 4 pies en el modelo (puerta v32: 0 apoyos).
3. **La rosca del pie no la mide nadie.** `tipo_de_tornilleria` devuelve None para toda ref de
   catálogo que no sea perno o tornillo de madera (`services/calidad_pernos.py:68-74`), y desde v29
   un pie a mano tampoco es tornillería aunque nombre su espárrago (`library/lints.py:51-52`). Así
   ningún ítem de `union.*` ve el enganche, la contratuerca ni el largo del vástago.
4. **Las plantillas ya saben hacerlo, pero sólo para sí mismas.** `create_belt_conveyor` arma la pila
   tuerca soldada + contratuerca y exige enganche ≥ 0,8·d contra la tuerca
   (`library/belt_conveyor_pies.py:4-19,29,51-64`); `create_roller_conveyor` calcula carga por pie y
   recorrido «vástago − tuerca − contratuerca» en su `engineering_check`
   (`library/rodillos_cadena_reglas.py:166-201`, `library/rodillos_cadena_pies.py:107-135`). Una
   mesa modelada a mano no pasa por ninguna de las dos.
5. **Dos criterios de enganche.** Contra una tuerca la plantilla pide 0,8·d (altura de la tuerca
   normal, DIN 934; `belt_conveyor_pies.py:29`); `agarre.retencion` pide 1·d en acero y 1,5·d en
   aluminio o fundición contra una rosca en la pieza (`library/calidad/agarre.py:29-31,46`). Las dos
   valen, cada una para su caso; hoy no hay una fuente que las elija.
6. **La traba ya se sabe reconocer en otro lugar.** El eje de una junta de giro tiene que ir trabado:
   autoblocante, contratuerca (dos tuercas a tope ≤ 1 mm) o retén (`library/ejes_giro.py:7-17,29`).
   El pie no usa esa medida.
7. **La compra doble viene de la unión declarada.** `tornilleria_declarada` compra el fijador de
   una unión `perno` sin pieza modelada por su nota («espárrago» → espárrago;
   `library/tornilleria_declarada.py:8-12`); el vástago del pie no cuenta como fijador modelado, así
   que la unión pie ↔ buje compra un espárrago que ya viene con el pie.
8. **La interferencia del pie en su rosca es exactamente el anillo de rosca.** Mesa Ø28: M16 en
   taladro Ø14, 12 mm → π/4·(16² − 14²)·12 = 565,5 mm³, los 565,5 que reporta el revisor. Mesa inox:
   M10 en Ø8,5, 21 mm → 457,7 mm³, los 457,7 del revisor. Es medible, no hace falta una excepción por
   nombre (la D6 de puerta-fuera-de-catalogo los pone como casos que NO fallan).

## Lo que se revisó antes de escribir esto

- Los 9 juegos de reportes (modelado, correcciones, revisor y re-revisiones) de las máquinas con pie
  y la puerta v32 de las 15 (`apoyo.capacidad` por máquina: 3 con `PIE-M*` de catálogo, 1 con
  `PIE-BA-*` de plantilla, 5 a mano).
- `services/criterio_uniones.py:11-14,112-117` ya propone `contacto` pie ↔ placa («la unión es su tuerca»)
  y `soldadura` a la tuerca del nivelador: el modelo de uniones no cambia.
- `calidad/tensor.py:1-45` es el modelo del evaluador enchufable: reconoce el mecanismo, mide su
  carrera y re-evalúa el agarre en los dos extremos (`evaluar_perno(desplazar=…)`,
  `agarre.py:75-78`). El pie es el mismo problema con el eje vertical.
- D3 de puerta-fuera-de-catalogo (clasificar por rol) saca al pie con «espárrago» en el nombre de la
  tornillería; D6 (interferencia declarada) necesita reconocer la rosca engranada. Este plan se apoya
  en la primera y le da a la segunda la medida.
- `registro.py` tiene 479 líneas y `calidad_pernos.py` 464 (tope 500): todo lo nuevo va en módulos
  propios.

## Decisiones (para vetar)

- **D1. El pie nivelador es un apoyo regulable por rosca y lo juzga su propio evaluador**, puro
  (`library/calidad/pie_nivelador.py`) con su insumo (`services/calidad_pies.py`), enchufable como el
  tensor. Se reconoce por la categoría `pies_niveladores` del catálogo o por el ROL de la pieza
  (`apoyos.clase_de_rol` = pie; `services/roles.py:26`) con la geometría que lo confirma: un vástago
  cilíndrico coaxial y una base de Ø mayor en un extremo. Vale para TODO pie, anclado o no. Lo que no
  se reconoce sale SIN_EVALUAR **justificable**. Los pies de las plantillas (faja, rodillos) pasan
  por el mismo evaluador; su regla propia queda como cálculo de diseño de su `engineering_check`.
  Porqué: la puerta es general; si cada plantilla trae su regla, la mesa a mano nunca la tiene.
- **D2. La rosca existe y engancha en TODO el recorrido.** Sobre el eje del vástago se mide qué lo
  recibe (la misma medición de tramos y rosca de `calidad_pernos`):
  - una **tuerca** (soldada o suelta) → enganche ≥ su altura entera, y la tuerca es de altura normal
    (m ≥ 0,8·d: DIN 934 / ISO 4032); es el criterio de la plantilla de faja;
  - una **rosca en la pieza** (placa, buje) → enganche ≥ k·d de `agarre` (1·d acero, 1,5·d
    aluminio o fundición; VDI 2230, criterio de taller), con una sola fuente
    (`agarre.rosca_enganchada`);
  - **material en el eje** (r = 0 dentro de la pieza que debería tener la rosca) → FALLA «no se puede
    enroscar: falta el taladro roscado o la tuerca» (mesa de trabajo soldada).

  El enganche se juzga con el pie en el extremo ALTO de su carrera (D4), no en la pose de diseño.
- **D3. El pie va trabado**: contratuerca a tope (≤ 1 mm, la medida de `ejes_giro`) contra la tuerca
  o la pieza que lleva la rosca, tuerca autoblocante, o la tuerca de bloqueo que su ficha declare
  incluida. Sin traba → FALLA (mesas de ensamble atornillada y soldada, mesa de trabajo soldada).
  Porqué: con vibración o al arrastrar la mesa el pie gira y desnivela; los tres revisores lo vieron.
- **D4. La carrera real se mide y se compara con lo que pide el piso.** De la geometría, con el pie
  en su pose: **sube** = lo que el vástago puede salir sin bajar del enganche de D2 (con la
  contratuerca puesta); **baja** = lo que puede entrar hasta que la base toque la contratuerca o la
  tuerca, o la punta toque lo que tiene encima (tubo cerrado, placa, cubierta). La evidencia y la
  ficha publican «−baja / +sube». Lo pedido sale del requisito nuevo `nivelacion_mm` (en
  `requisitos.NUMERICAS`); sin él, del desnivel admisible de un piso terminado con la mayor luz entre
  pies (DIN 18202 Tabla 3, a leer en la F0; si no se puede citar, criterio de diseño escrito como
  tal). Sube o baja por debajo de lo pedido → FALLA.
- **D5. El catálogo trae los pies que el mercado vende.** `97_pies_niveladores.yaml` gana rosca
  M8–M20, la serie de largos de vástago de fabricante, base articulada (con su ángulo), inox AISI 304
  higiénico con su buje de soldar, hexágono de llave (SW), tuerca de bloqueo incluida o no y carga
  estática; cada cifra con fuente de ficha de fabricante citada en el YAML, y `cotas_verificadas:
  false` donde no se verifique. El builder modela el hexágono y la tuerca de bloqueo si la ficha los
  trae. Los 6 refs actuales quedan (ids estables). Porqué: 5 de 9 modeladores hicieron el pie a mano
  porque el catálogo no lo tenía, y a mano no hay ficha que medir.
- **D6. La fila de compra de un pie de catálogo lleva su ficha**: rosca × largo del vástago, base,
  articulación, material y carga (la re-revisión 3 de la mesa de trabajo soldada no lo podía pedir
  con «PIE-M10-40» pelado).
- **D7. La rosca del pie no se compra aparte**: una unión entre un pie y la pieza que lleva su rosca
  no genera fila de tornillería en `tornilleria_declarada` (el vástago del pie ES el fijador, como hoy
  «eje roscado» → ninguno). Una tuerca soldada o una contratuerca modeladas siguen comprándose.
- **D8. La interferencia del pie en su rosca la explica el evaluador**: publica el par pie ↔
  tuerca/pieza como «rosca engranada» con el volumen del anillo π/4·(d² − d_broca²)·enganche
  (broca de ISO 2306). `union.interferencia_declarada` (D6 de puerta-fuera-de-catalogo) lo toma de
  ahí; un volumen mayor que el anillo (el vástago atraviesa material) es la FALLA de D2.
- **D9. Cada fase que cambia lo que la puerta decide sube el registro**, con su línea en
  `historial_registro.py`; una máquina aprobada con un registro anterior vuelve a correr la puerta
  antes de publicarse (D10 de puerta-fuera-de-catalogo).

## Alternativas descartadas

- **Una regla de pie por plantilla** (como hoy faja y rodillos): la mesa a mano, que es la mayoría
  de la tanda, nunca la tendría.
- **Que el modelador declare la carrera en el nombre**: el nombre miente (la mesa de ensamble
  prometía +40 y daba +4); la carrera se mide de la geometría.
- **Tratar el vástago como un espárrago en `union.retencion`**: la retención de un perno no mira
  carrera ni traba, y D3 de puerta-fuera-de-catalogo saca al pie de la tornillería por rol.
- **Exigir siempre pie con base de anclaje o disco soldado**: depende de la instalación (piso,
  anclado, móvil); eso ya lo pide la ficha del encargo.
- **Descargar fichas STEP de fabricante**: la biblioteca es paramétrica (familia + builder), como el
  resto del catálogo.

## Fases

- **F0 — medir** (sólo lectura, S). Hecha (Bitácora). Las 9 máquinas con pie: por pie, cómo está modelado (catálogo o a
  mano), qué recibe la rosca, enganche, contratuerca, carrera medida y qué decidirían D2–D4; por qué
  la mesa inox de 2 m no tiene apoyos en `apoyo.capacidad`; si el reconocimiento geométrico de D1
  encuentra los 5 pies a mano. Fuentes: DIN 18202 Tabla 3, DIN 934 / ISO 4032 (altura m), ISO 2306
  (broca), fichas de fabricante de pies articulados e higiénicos (largos, SW, carga estática). Ajusta
  D1–D8 (vetable).
- **F1 — catálogo** (`library`, M). D5, D6 + tests de la familia y de la fila de BOM. Toca el YAML
  y el builder: bump de `GEOM_CACHE_EPOCH` con su motivo. Registro +1 sólo si cambia lo que decide
  `bom.comprable`.
- **F2 — evaluador** (`library/calidad`, `services`, L). D1–D4, D8 + tests con fixtures sacadas de
  la F0: placa delgada sin contratuerca (mesa de ensamble atornillada), 0,53·d (ensamble soldada),
  placa maciza (mesa de trabajo soldada), carrera corta (mesa inox), pie articulado M16 con
  contratuerca que pasa (mesa Ø28), y los pies de `create_belt_conveyor` y `create_roller_conveyor`
  que siguen pasando (el testigo 38 entre ellos). Depende de la F0 y, para el reconocimiento por rol,
  de la F2 de puerta-fuera-de-catalogo. Registro +1.
- **F3 — la rosca no se compra dos veces** (`library`, S). D7 + test con la unión pie ↔ buje de la
  mesa inox. Registro +1 si cambia `bom.comprable`.
- **F4 — verificar** (S). Puerta del último registro sobre las 9; comparación por pie con la F0; las
  plantillas siguen aprobando.

F1 y F3 son independientes entre sí y de F2 (hasta 3 agentes a la vez); F2 espera a la F0.

## Lo que este plan NO hace

- La capacidad del pie: ya la juzga `apoyo.capacidad`; aquí sólo se amplía a qué pies ve (D1).
- El acceso de llave a la contratuerca: lo cubre `union.acceso_herramienta` cuando la contratuerca
  es tornillería de catálogo; si la F0 encuentra que no la ve, se anota como fix aparte.
- Garruchas, regatones y patas sin rosca: no regulan.
- Corregir las mesas de la tanda: es producción, después de la F4.

## Riesgos

- **Mesas aprobadas que dejan de aprobar** (las tres de trabajo, la inox): es lo buscado; la F0 da
  el antes y la F4 el después, y cada umbral queda vetable.
- **El pie a mano no se reconoce** (un `run_script` que funde vástago y base con otra pieza): sale
  SIN_EVALUAR justificable, nunca OK; la F0 cuenta cuántos de los 5 caen ahí.
- **La carrera hacia arriba la limita algo que el rayo del eje no ve** (una tapa fuera del eje): se
  mide con la caja del vástago extendida, no con un rayo; tests con tubo abierto y tubo con tapa.
- **El default de DIN 18202 sobre-exige una mesa chica**: la luz entre pies lo escala; con
  `nivelacion_mm` declarado manda el requisito.
- **Regresión en las plantillas** (faja, rodillos): sus pies son tests de la F2 desde el primer
  commit.

## Bitácora

### F0 — medir (2026-10-30)

Las 9 máquinas con pie medidas en el eje del vástago (núcleo 9ce35728, modelos en su estado final),
fuentes de norma y fichas de fabricante. Lo que cambia del contrato (aprobado por Claude con la
delegación de Mario; vetable):

- **D1**: el reconocimiento geométrico exige el ROL pie **y** un vástago cilíndrico convexo con base
  coaxial: sin el rol, las garruchas de un carro y los caladrillos (cilindros cóncavos) de una pata
  de madera pasan la prueba. Con rol + geometría se reconocen los 5 pies a mano y los 3 de catálogo
  redondos; el de base de anclaje (base placa), sólo por la categoría del catálogo.
- **D2** (se reescribe):
  - el enganche es la rosca en la pieza **más** la tuerca a tope del lado de la carga (la mesa Ø28,
    que el contrato daba como «pasa», falla con la regla escrita: 12 < 16 mm de placa sola);
  - una tuerca alta (DIN 6334) se juzga como rosca en pieza (k·d), no por su altura entera;
  - m ≥ 0,8·d admite la igualdad (DIN 934 M10 = 8,0 mm);
  - se juzga en la **pose de diseño**, y la carrera de D4 sale del mismo umbral (juzgar en el
    extremo alto, que a su vez depende del umbral, era circular);
  - la «placa maciza» de la mesa de trabajo soldada era un falso positivo del revisor (el taladro
    lo hace otro comando): el caso «material en el eje» se prueba con fixture sintético.
- **D3**: cuentan como traba la contratuerca a tope de **la pila** (tuerca, placa o tapa que recibe
  la rosca), la traba fundida al pie (hexágono de bloqueo del sólido) y el parche DIN 267-28
  declarado en la nota de la unión. Con la regla escrita, cuatro mesas fallaban sin razón.
- **D4**: Δ = DIN 18202 Tabla 2 fila 1 (ángulo) + Tabla 3 fila 3 (planitud del piso terminado) a la
  diagonal entre pies (12,5–14,3 mm en la tanda). FALLA si sube + baja < Δ; AVISO si un sentido
  < Δ/2. `nivelacion_mm` declarado manda.
- **D5**: las familias del YAML salen de fichas leídas (GN 343.2 de espárrago, LV.A de Elesa —su
  carga es de ROTURA: se aplica factor—, GN 20 higiénico M12–M24); las designaciones que usaron tres
  mesas («GN 343.1» con espárrago, «GN 343.7» higiénico M10) no existen así: el catálogo lo evita.
- **D7**: se mantiene con test sintético: en los modelos finales no hay compra doble sólo porque 8 de
  9 escribieron «incluido» o usaron `contacto`, y la mesa inox por un error de clasificación.
- **D8**: la broca sale de `threads.COARSE` (DIN 336, la que ya usa el núcleo); la fórmula reproduce
  las cinco interferencias reportadas (174,3 / 199,3 / 217,9 / 457,7 / 565,5 mm³). En 4 de 9 la
  rosca no tiene solape (agujero ≥ d): no hay anillo y la rosca se reconoce por el nombre o por la
  tuerca de catálogo.

**Fix que va a la F2 de puerta-fuera-de-catalogo** (no a este plan): `es_nombre_de_tornilleria`
lee «espárrago» dentro de «(compra: …)» y saca los 4 pies de la mesa inox de `installation_data`: 0
apoyos en `apoyo.capacidad` y sin lámina de instalación.

**Sin medir**: el acceso de llave a la contratuerca; ISO 2306 (se usa DIN 336); la carga de GN 20.

### F1 — catálogo (2026-10-30)

- **D5**: `97_pies_niveladores.yaml` gana 38 refs de 4 familias, cada cifra con su ficha citada
  en el YAML: `PIE-ART-*` (16, del orden de Ganter GN 343.2: d1 32–60, M8–M20, l1 de la serie
  por rosca, SW 12–24, tuerca ISO 4032 incluida, carga ADMISIBLE de la ficha / g),
  `PIE-TP-*` (11, Elesa LV.A) y `PIE-TPX-*` (5, LV.A-SST inox): su carga es de ROTURA y la de
  servicio es rotura / **4** (criterio de diseño: fluencia del tecnopolímero, el mismo FS 4 del
  MOR de la madera), tuerca aparte; `PIE-HIG-*` (6, Ganter GN 20 tipo A, M12–M24, vástago libre
  hasta 200 mm) con `cotas_verificadas: false`: sin dibujo, qué mide cada columna es lectura
  nuestra (vástago libre = l1 − l3) y la carga es ambigua entre los tipos A y B (se toma la
  menor por rosca); sin buje de soldar. Los 6 refs de siempre quedan con sus ids y su carga, y
  ganan `base`, `tuerca_incluida: false` y `cotas_verificadas: false` en sus specs.
- **Builder** (`leveling_foot`): parámetros nuevos con default 0 (cuerpo de la base, hexágono de
  llave, tuerca de bloqueo a MEDIA rosca); sin ellos la forma es la de antes byte a byte, y un
  test congela volumen, caras y caja de los 6 refs: **sin bump** de `GEOM_CACHE_EPOCH`.
- **D6**: la fila de BOM de un pie lleva la ficha (`library/pies_ficha.py`) en la descripción
  («— M10 × 40 mm, disco Ø75 fijo, acero zincado, carga 200 kg/pie, sin tuerca de bloqueo») y en
  `ficha`. `bom.comprable` no cambia (una ref de catálogo ya alcanzaba): **sin bump de registro**.
- `create_roller_conveyor` elegía su pie entre TODA la categoría por carga y se llevaba un
  articulado: `rodillos_cadena_pies.familias` sólo mira los de disco fijo / placa de anclaje
  (`specs.base`), su pila de siempre; elige lo mismo que antes (sin subir su `version`).
- Para la F2: `fijadores_geom.reconocer_fijadores` no ve dos hexágonos coaxiales de entrecaras
  DISTINTO en un sólido (el de llave y la tuerca del `PIE-ART`): la tuerca incluida se lee de la
  ficha (`tuerca_incluida`, `tuerca_m`, `tuerca_sw`), no de la geometría.

### F3 — la rosca no se compra dos veces (2026-10-31)

`library/tornilleria_declarada.py`: una unión `perno` declarada sin pieza modelada entre un pie
nivelador y cualquier otra pieza no compra fijador si la métrica de la unión es la del vástago (o
el vástago no la dice). El pie se reconoce por la ficha (categoría `pies_niveladores`, métrica de
`rosca`) o por el ROL anclado del nombre («Pie nivelador…», «Pie articulado nivelador…»,
«Nivelador…», «Leveling foot»: `_es_pie_nivelador`); «Pie de amigo», «Pata…», «Placa del pie
nivelador» o «Espárrago … del pie» no son pie. Decisiones tomadas en la fase:

- no se usa `apoyos.clase_de_rol` tal cual: su clase «pie» incluye cualquier «Pie …» (una pata), y
  quitar el perno de una pata atornillada sería una compra de menos; se exige «nivelador»;
- una unión de OTRA métrica que el vástago sigue comprando (los pernos de anclaje de la base de
  un `PIE-BA-*`: M12 por agujeros Ø14 de un pie M10);
- la tuerca que la nota declara (contratuerca, tuerca soldada) sigue comprándose si nadie la
  modeló; modelada sale por su fila de la BOM, como siempre;
- **registro sin subir**: `bom.comprable` juzga `bom_from_scene` (`services/calidad_bom.insumo_bom`)
  y no ve las filas declaradas (sólo BOM, CSV y costeo, por `services/bom_filas.filas_extra`): la
  puerta no cambia.

Tests: `tests/test_pie_nivelador_rosca.py` (antes/después sintético pie ↔ buje con «espárrago
M10», pie de catálogo ↔ placa, anclaje M12 de un `PIE-BA`, otra métrica en el nombre, perno común
de un «Pie de amigo», contratuerca declarada y modelada, reconocimiento por rol y por ficha).
