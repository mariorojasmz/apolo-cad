---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: F0–F5 mergeadas a main el 2026-10-21 (create_roller_conveyor v3, re-verificada por el revisor ciego sin ALTA); F6 (campo oculto taller, E1–E5) en integ-noche, sin mergear; F7 (campo oculto eje «hexagonal» por el sello, E6–E9 vetables) implementada en su rama sobre integ-noche, sin mergear; F8 (campo oculto pie «base» por el sello: pie de base de anclaje sin placa de piso ni soldadura, E10 vetable) implementada en su rama sobre integ-f7, sin mergear; quedan las 4 preguntas a Mario
descripcion: Un transportador de rodillos por cadena sale completo con una sola orden, ya con las correcciones de la piloto
---

# Un transportador de rodillos por cadena con una sola orden

## Estado y origen

Mario quiere sacar muchas máquinas (detalle fuera del núcleo).
La piloto (proyecto 2, transportador de rodillos motorizado por cadena, 2 m) costó ~1 h 10 min y
~60 M tokens leídos, y aun así tuvo 4 defectos que vio Mario
([revision-de-taller](revision-de-taller.md)). Recomendación aceptada el 2026-10-10: lo que se
repite va en una plantilla, para que cada lección quede dentro una sola vez.

## El problema / lo que hay hoy

- Las plantillas de máquina son super-comandos (raíz § Arquitectura): existe `create_conveyor`
  (faja), no uno de rodillos.
- `create_chain` (cadenas-pinones F2) no resuelve dos cosas que la piloto hizo a mano: en lazos
  1:1 con piñones de dientes impares, desfasar medio diente (12° en Z15) los alternos para que la
  cadena no se abulte (y, medido en la F0, girar 3° el piñón motriz Z30 para la cadena motriz);
  y elegir la distancia entre centros exacta para un número par de
  eslabones (159.034 en vez de 159.035 hacía saltar de 48 a 50 eslabones).

## Decisiones (para vetar)

- **D1. `create_roller_conveyor`**: largo, ancho útil, paso, Ø de rodillo, altura, carga y
  `motriz: cadena | libre`. Genera bastidor de ÁNGULO con ala abajo hacia afuera (lección de la
  tuerca), patas en H soldadas con travesaño entre patas (lección de c88), SIN travesaños sin
  función (c89), ejes con tuerca accesible, piñones dobles, cadenas 1:1, motorreductor,
  guardas con separadores entre rodillos, uniones y tierra declaradas.
- **D2. `create_chain` aprende las dos cosas** (corregida por la F0, ver Bitácora):
  - `fase: "auto"` gira sobre su eje el piñón que todavía no lleva otra cadena (B si está
    libre; si no, A) lo justo para que la cadena engrane sin estirarse. En un lazo 1:1 a
    centros exactos eso da medio diente con z impar y cero con z par (prefiere esos dos
    valores); en otras relaciones barre un diente. Ya engranado, no toca nada. Default
    `"tal_cual"`, que es lo de siempre. Esto revierte, sólo cuando se pide, la alternativa
    que [cadenas-pinones](cadenas-pinones.md) había descartado («girar el piñón B»): asentar
    los rodillos en los asientos no basta, porque deja un eslabón estirado 1.27 mm.
  - `eslabones: N` (par) fija el largo. Si los piñones quedan más lejos que el centro exacto
    de N (más 0.05 mm de tolerancia), el comando falla y dice ese centro: lo recomienda. Para
    colocar los piñones ANTES, la expresión `centros_cadena(paso, z_a, z_b, eslabones)`
    calcula el exacto. Default `None`, que es lo de siempre (el menor par cuyo exacto es ≥
    los centros medidos).
- **D3. La plantilla pasa sus propios chequeos**: test que la genera con 3 tamaños y exige
  `delivery_check` VERDE con gravedad + [acceso-de-herramienta](acceso-de-herramienta.md) +
  [perfiles-con-acuerdo](perfiles-con-acuerdo.md) sin avisos.

## Fases

- **F0 (S, sólo lectura)**: inventario del log del proyecto 2 (qué comandos y qué variables lo
  arman) como receta de la plantilla.
- **F1 (S, `commands`)**: D2 en `create_chain` (sube su `version`), con la matemática pura en
  `library/transmision.py` y la función `centros_cadena` en `commands/expressions.py`.
- **F2 (L, `commands` + `library`)**: D1 como super-comando con sus tests.
- **F3 (S, verificación)**: generar por MCP un transportador de 3 m y medir tiempo y tokens
  contra la piloto.
- **F4 (M, `commands` + `library`)**: los defectos que el revisor de taller ciego halló en la
  plantilla (§ Bitácora F3), con el contrato de abajo. `create_roller_conveyor` sube a v2.
- **F5 (S, `commands` + `library`)**: pies niveladores (§ Bitácora F4b), contrato abajo; v3.
- **F6 (S, `commands` + `library`)**: los defectos de la PLANTILLA que el revisor ciego halló en
  la piloto de rodillos por gravedad (decisiones E1–E5 en § Bitácora F6); sin bump.
- **F7 (S, `commands` + `library`)**: el eje hexagonal que se calza, para cambiar un rodillo sin
  tocar tuercas, y su designación en la BOM (decisiones E6–E9 en § Bitácora F7); sin bump.
- **F8 (S, `commands` + `library`)**: el pie anclado sin soldar: pie nivelador con base de anclaje
  atornillado al concreto, sin placa de piso (decisión E10 en § Bitácora F8); sin bump.

### F4 — contrato

Porqué: el revisor ciego de F3 encontró 2 ALTA (guardas abiertas del lado motor y por debajo), 3
MEDIA y 1 BAJA en la máquina que la plantilla entrega «VERDE». La puerta no ve guardas ni
tensado: lo arregla la plantilla, que es donde vive la lección.

- **D4. Guarda de la transmisión cerrada (ISO 14120, aberturas ISO 13857 tabla 4).** Hoy es una
  bandeja abierta hacia −Y (el motor) y deja 72,4 mm abiertos entre su borde (h − 42) y la guarda
  de cadenas. Pasa a dos cajas que TELESCOPAN a lo largo de la línea de centros de la motriz:
  - **cárter móvil**, soldado a la base del motor (que es su piso): pared interior con barreno
    del eje y muescas para las patas del motor, pared exterior y dos extremos. Se mueve con el
    motor al tensar, así que el eje no necesita ranura en ninguna pared fija;
  - **guarda fija**, cuatro paredes por fuera del cárter (holgura 2–6 mm), desde encima del eje
    hasta bajo los tubos (h − Ø/2 − 3), atornillada (M6, desmontable con herramienta) al alma del
    larguero +Y. Su extremo +X sube hasta la guarda de cadenas y cierra el final del bastidor.
  - Criterio de abertura: rendija entre paredes ≤ 6.1 mm en todo el recorrido → ISO 13857
    tabla 4 pide ≥ 20 mm al peligro: el solape vertical se calcula con ese número más el
    recorrido. Eje en el barreno del cárter y patas en sus muescas: holgura 2 mm (e ≤ 4).
  - Nada de la guarda toca lo que gira (holgura ≥ 3 mm en todo el recorrido).
- **D5. Bandeja inferior de cadenas.** Perfil en C de chapa 2 bajo los lazos y piñones, de la
  alimentación a la guarda de la transmisión: fondo 5 mm bajo el ramal más bajo, pestaña
  interior hasta 3 mm bajo los tubos, pestaña exterior contra el alma del larguero +Y con 2 M6
  por tramo (roscas en el alma) y tapa en el extremo de alimentación hasta la guarda de cadenas.
  En tramos de ≤ 1 m que se sacan con herramienta sin desarmar nada más.
- **D6. Velocidad (`velocidad_m_s`, opcional).** Sin ella (logs viejos) el piñón del motor
  sigue siendo el Z30: la misma velocidad de hoy. Con ella, la plantilla elige el Z del piñón
  del motor entre los ASA 40 simples del catálogo (el del rodillo es el doble-simple Z15) que
  dé la velocidad más cercana dentro de ±10 % (el mismo criterio «0.9 × objetivo» de la
  velocidad de banda), que entre en el eje del motor y que arme la motriz sin chocar. Si
  ninguno, error que dice las velocidades que salen con ese motor y qué motor + piñón da la
  pedida. El motor sigue siendo el que diga `motor`: la plantilla no lo cambia sola.
  - FS de potencia publicados: motor (P_motor / P_requerida) y cadena (el primer lazo lleva el
    par nominal del motor, tabla ACA con servicio moderado). Ninguno < 1 (error); < 1.2 =
    aviso en `engineering_check`.
  - La «v = 0.32 m/s» que leyó el revisor es la de la CADENA (π·Ø primitivo·rpm), no la del
    producto: con TUBOR-2 y Z30 el producto va a 0.266 m/s.
- **D7. Ranuras de tensado alineadas con la línea de centros.** La base del motor ya no tiene
  ranuras horizontales (a 70° de la cadena: ~8 mm útiles). El travesaño portamotor se ATORNILLA a
  las caras interiores de las patas con orejas soldadas a sus extremos, de ranuras paralelas a la
  línea de centros (20° de la vertical): base, motor y cárter corren juntos sobre esa línea.
  - Recorrido: +b para tensar ≥ el estirado de reemplazo (3 % del largo de la cadena → 1.5 % en
    centros; criterio de diseño de los fabricantes de cadena de rodillos, Tsubaki/Renold) y −3 mm
    para montar el eslabón de unión. El motor sigue en vertical (montaje B3).
  - Una ranura de cada oreja abre arriba y la otra abajo: cada sentido lo frena una.
- **D8. Mismo travesaño en todas las estaciones.** Uno ENTRE las patas, a la altura del
  portamotor (con cadena) o a media pata (libre), igual en la alimentación, las intermedias y la
  motriz. Criterio de marco de taller: a media altura acorta la ménsula libre de cada pata sobre
  el travesaño (lo que gobierna el balanceo lateral de una H) y deja el piso libre para limpiar;
  el travesaño bajo (z = 150) dejaba 500 mm de pata en ménsula. La motriz no puede llevarlo alto
  (ahí va el motor) y no debe llevar dos (c89: nada sin función).
- **D9. `engineering_check` reconoce la plantilla.** Con un `create_roller_conveyor` en el log,
  `/api/checks` y la memoria validan contra la ficha (`requirements`): velocidad (±10 %), apoyo
  del paquete, capacidad del rodillo (2 × 6201 a L10 = 20 000 h por ISO 281 y eje M12 con
  σ ≤ 0.5·σy), carga de diseño (la ficha llena de paquetes contra `carga_kg`), motor y cadena
  (FS) y recorrido de tensado. Puro en `library/`; el endpoint sólo lo llama.
- **Tests (único gate)**: la plantilla de 3 m regenera con 0 interferencias (guardas incluidas,
  holgura a lo que gira en las dos puntas del recorrido); sujeción y gravedad verdes; una sonda de
  dedo Ø8 (ISO 13857: desde ahí entra el dedo hasta el nudillo) no alcanza cadena ni piñón desde
  abajo, desde el lado del motor ni desde afuera; `velocidad_m_s = 0.25` da 0.25 ± 10 %; las
  ranuras dan ≥ el recorrido pedido sobre la línea de centros; `engineering_check` la reconoce;
  un log v1 regenera con las mismas cotas de rodillos, cadenas y motor (cambian guardas, base,
  travesaños) y la `version` invalida su caché.

### F5 — contrato (niveladores)

Porqué: el revisor ciego de F4b halló placas base lisas, soldadas, con 2 anclajes y sin
nivelación. Un bastidor soldado de 3 m con 6 apoyos sobre concreto no se puede nivelar ni ajustar
a la altura de trabajo.

- **D10. Pie nivelador de catálogo en cada pata** (`97_pies_niveladores.yaml`, el mismo que usa
  `belt_conveyor.py`). La familia sale de la carga por pata: (masa de la máquina + carga de diseño)
  / patas × 1,5 de impacto, contra `carga_kg` del pie. La placa de la pata lleva la tuerca soldada
  (rosca del pie) y el disco apoya en el piso.
  - Con `anclaje: true` (default de los logs viejos = el comportamiento de hoy) se conservan los 2
    agujeros de anclaje en una placa de piso aparte bajo el disco. Así el bastidor se nivela y
    después se ancla.
  - La altura de trabajo sigue siendo `altura` con el pie a la mitad de su recorrido: la pata se
    acorta lo que mide el pie.
  - Recorrido de nivelación publicado (± mm) en `engineering_check` y en la memoria.
- **Tests**: el 3 m regenera con 0 interferencias; el techo del rodillo sigue en `altura`; cada
  pie con carga ≤ su `carga_kg`; gravedad verde (tortura); un log v2 sigue regenerando y la
  `version` sube a 3.

**Preguntas para Mario** (el revisor las dejó como pregunta; F4 NO las decide):
- ¿Los lazos rodillo a rodillo necesitan tensado? Hoy: ejes fijos con 1 M12 y eslabones exactos
  (sin recorrido). Opciones: tensor de patín por lazo, barrenos ranurados en el larguero o
  aceptar el cambio de cadena al 3 %.
- ¿Guía lateral del lado −Y (y en el +Y)? Depende del producto y de cómo se alimenta.
- ¿Riostra longitudinal (diagonal entre estaciones)? Depende del sitio (anclado o no, empujes).
- (nueva de F4) Por DENTRO, entre la brida del tubo y la cadena de la hilera 2 hay 1.5 mm: no
  cabe pared. Con la mano sobre los rodillos, entre dos tubos (44 mm) se llega a la cadena por
  el extremo. ¿Se acepta (los rodillos son la superficie de trabajo) o se pasan las cadenas por
  fuera del larguero, como un CDLR comercial?

## Lo que este plan NO hace

- Transportadores por faja o por gravedad sin motor (otra plantilla, si hace falta).

## Riesgos

- Plantilla rígida que no sirve para variaciones → todo por variables y con piezas editables
  después (como `create_conveyor`).

## Bitácora

### F8 (2026-10-28): el pie anclado sin soldar

**Origen**: tres revisores de taller a ciegas seguidos (pilotos de rodillos por gravedad hechos con
la plantilla) objetaron el anclaje del pie de F5–F7: con `anclaje: true` el disco del PIE-M*
(acero ZINCADO) va SOLDADO a una placa de piso anclada. Soldar zincado en obra da humos de zinc y
cordón poroso, y una vez soldado la altura no se re-nivela en servicio sin amolar.

**Decisión (vetable)** — numerada E10 porque la E8 ya es la compatibilidad de F7:
- **E10. Pie nivelador con base de anclaje, anclado directo al concreto.**
  - **Ref nueva**, familia `PIE-BA` en `97_pies_niveladores.yaml` junto a los PIE-M*: `PIE-BA-M8-30`,
    `PIE-BA-M10-40`, `PIE-BA-M12-50`, con la MISMA rosca, vástago (recorrido) y carga (120 / 200 /
    350 kg) que el PIE-M* de su métrica, sobre una base rectangular **190 × 80** (espesor el del
    disco: 10 / 12 / 14) con **2 agujeros Ø14 a 140 mm** sobre X. Solución de mercado: pie con base
    de fijación al piso, «del orden de» Elesa o Ganter; `cotas_verificadas: false` (no se
    contrastaron con una ficha). Canto de la base a 25 mm del agujero (≥ 1,5 · 14 = 21, EN 1993-1-8
    tabla 3.3); la base cabe en el tfix 20 del anclaje. Builder `leveling_foot_base`
    (`builders_fijacion.py`, origen en el centro del vástago como `leveling_foot`). `familias()`
    sigue dando sólo los PIE-M* (un log viejo elige igual); `familias(True)`, los de base.
  - **Anclaje**: los 2 `ANCLA-EXP-M12` de F6 por los agujeros de la base, apretados sobre ella
    (`contacto` anclaje ↔ pie); el `ground` es el pie, con la nota «sin soldar … se re-nivela con
    la contratuerca suelta, sin tocar el anclaje». Sin placa de piso y sin ninguna soldadura al pie
    (el criterio de uniones ya da `contacto` perno ↔ pie: regla 1).
  - **Acceso de taladro y dado, la cifra de F6** (`ACCESO_ANCLAJE` = 30 mm del eje del anclaje al
    borde de lo que hay encima): con la placa de la pata de 150 los anclajes de una base comercial
    quedarían debajo. La placa de la pata se achica a **140 − 2 · 30 = 80 mm** (`Pies.placa_pata`):
    sigue llevando el tubo 2×2 (50,8) con 14,6 mm por lado para el cordón. Un Ø50 sobre cada anclaje
    no toca nada (test).
  - **La tuerca del vástago sigue SOLDADA bajo la placa de la pata**, y la contratuerca sigue: la
    tuerca (DIN 934, «acero grado 8», negra) y la placa (chapa de acero negro) no son zincadas, así
    que esa soldadura está bien; la nota de la unión lo dice («tuerca negra (sin zincar) …»). Lo
    zincado (pie y anclajes) no se suelda.
  - **Nivelar**: se ancla la base, se gira el vástago con la contratuerca suelta (recorrido ±8,5 /
    ±12 / ±15 mm, el de F6) y se aprieta la contratuerca contra la tuerca soldada; en servicio se
    re-nivela igual, sin tocar los anclajes (docstrings de la receta, de `rodillos_cadena_pies`, el
    schema del comando y el detalle de la regla «pies niveladores»).
- **Compatibilidad: otro campo oculto, sin bump.** `pie: "disco" | "base"` (`SkipJsonSchema`,
  default «disco» = F5–F7). El sello lo pone en «base» junto con `eje="hexagonal"` a todo comando
  nuevo con `taller=True`; «base» sin `taller` es error (los anclajes de catálogo son de F6). Con
  `anclaje: false` el campo no cambia nada (el disco liso al piso). Un log F7 (`taller` + `eje`, sin
  `pie`) regenera idéntico: huella de piezas, uniones y anclajes y la geométrica congeladas con el
  código de 7b8f891. `version` sigue en 3 (el executor no cambió: D11 igual) y `CAMPOS` suma `pie`.

**Archivos**: `library/data/97_pies_niveladores.yaml` (la familia), `builders_fijacion.py`
(`leveling_foot_base`), `rodillos_cadena_pies.py` (`familias(base)`, `Pies.base`, `placa_pata`,
anclajes de la base, pila sin placa de piso, masa), `rodillos_cadena.py` (`pie`, `PIES`),
`rodillos_cadena_reglas.py` (el detalle), `commands/receta_rodillos_cadena.py` (`_pie`),
`models_rodillos_cadena.py` y `exec_rodillos_cadena.py` (el campo y el sello).

**Medido** (masa real del modelo; estimada sin el ×1,10):

| máquina | sólidos F7 → F8 | masa real F7 → F8 | estimada F8 | pie (carga por pie) |
|---|---|---|---|---|
| 1 m | 166 → 162 | 111,3 → 98,1 kg | 100,1 | PIE-BA-M8-30 (79 de 120) |
| 3 m de F3 | 408 → 402 | 237,4 → 217,6 kg | 223,5 | PIE-BA-M8-30 (111 de 120) |
| 4 m, TUBOR-3, 400 kg | 492 → 484 | 366,8 → 340,7 kg | 347,8 | PIE-BA-M10-40 (147 de 200) |
| 1,5 m libre (la piloto) | 180 → 176 | 95,9 → 82,7 kg | 85,9 | PIE-BA-M8-30 (73 de 120) |

- Ninguna métrica de pie cambió (la masa baja: sin la placa de piso de 260 × 150 × 10 y con la placa
  de la pata de 80). 0 interferencias sin tope y SIN excluir la tornillería (libre 1,5 m y 3 m, y
  cadena 3 m). Puerta VERDE sin avisos en la piloto: la llave entra en sus 16 fijadores (4 tuercas
  soldadas, 4 contratuercas, 8 anclajes). Gravedad VERDE (tortura) en la piloto libre y en el 3 m
  con cadena.

**Tests**: `tests/test_plantilla_rodillos_f8.py` (2 con `-m torture`). Fijados al disco (miden
F5–F7): el `_doc` de `test_plantilla_rodillos_f6`, el log F6 de `test_plantilla_rodillos_f7` y la
máquina de 3 m y el log v2 de `test_plantilla_rodillos_f5`. Recalibrados: el piso de `position.z`
en `test_plantilla_rodillos_cadena` (ahora la base del pie) y los conteos del catálogo (477 refs, 6
pies). El schema del comando sigue bajo los 7 500 bytes de D12.

**Fuera** (no se decidió): contrastar las cotas del PIE-BA con la ficha de un fabricante; la base
con los agujeros sobre X no choca con nada hoy, pero una estación pegada a otra máquina en X pediría
girarla 90°; las 4 preguntas a Mario.

### F7 (2026-10-28): eje hexagonal que se calza; el rodillo sale levantándolo

**Origen**: el piloto «rodillos por gravedad» hecho con la plantilla F6 aprueba la puerta, pero el
revisor de taller a ciegas vio que la E3 de F6 (eje roscado M12 de 472 mm trabado con tuerca
interior y exterior contra el ala, separador a 0,5 mm del 6201; 432 mm entre almas) hace que
cambiar UN rodillo lleve 10–15 min: soltar las tuercas exteriores no lo libera; hay que sostener las
interiores con llave y destornillar el eje ~50 vueltas entre tubos con 24 mm de luz. Y la BOM traía
el eje como «A-MEDIDA 472» liso, sin métrica ni largo de rosca: no se puede comprar ni mecanizar.

**Decisiones (vetables por número)**:
- **E6. Eje hexagonal calzado en una ranura abierta hacia arriba.**
  - **Eje**: barra hexagonal calibrada de **11 mm entrecaras** (EN 10278, h11; la de los rodillos
    de Ø50 de mercado), caras planas VERTICALES, con los dos extremos fresados a **doble plano de 8**
    en el largo que atraviesa el ala y asoma 6 mm por fuera (`rodillos_cadena_eje.py`).
  - **Ranura**: en cada rodillo, en el ala vertical de los dos largueros, taladro **Ø8,5** en el
    fondo + dos cortes de sierra hasta el canto (8,5 de ancho: 0,25 por lado). Taller con taladro de
    banco y sierra, sin láser ni punzonadora; en el modelo, `drill_hole` + `add_joinery` «rebaje»,
    que corta en sitio y conserva el id del larguero. El extremo apoya en sus dos aristas bajas
    sobre el arco del fondo y se centra solo: el eje queda **2,61 mm** sobre el centro del taladro.
  - **No gira**: las caras del doble plano quedan entre las paredes de la ranura (girarlo 3° ya
    choca: test). **No corre**: los hombros del hexágono quedan a 0,25 mm de la cara interior de
    cada ala. **Juego axial del rodillo**: dos separadores de tubo EN 10255 DN10 (Ø17,2 × 2:
    agujero 13,2 > esquinas del hexágono 12,7) del ala a 0,5 mm del aro interior → 1 mm en total
    (≤ 2 mm de F6).
  - **Rodamiento**: el 6201 (d 12) no admite el hexágono (esquinas Ø12,7). Lo de mercado es el
    rodamiento de **agujero hexagonal**: ref nueva **`6202-HEX11`** (contorno 6202 D35 × B11 con
    agujero hexagonal de 11, 2RS, C = 7,65 kN; builder `bearing_hex`; `cotas_verificadas: false`),
    de compra en la tapa (su alojamiento sale de la ficha: Ø35 × 11). El aro interior queda trabado
    por el hexágono (no gira sobre el eje). Buje y piñón se abren a Ø22 para librar su aro interior
    (Ø ≈ 21). No se ofrece en los tensores (`models_rodillos._bearing_refs`: sin `d` redondo).
  - **Resorte retráctil, comparado y descartado**: el eje de resorte (se empuja un extremo hacia
    adentro y el rodillo cae) también cambia un rodillo en segundos y no corta el canto del
    larguero, pero pide **agujeros hexagonales** en el ala (punzonadora o láser: el taller de
    ángulos no los hace con taladro) y un resorte + tope por rodillo (más piezas de compra y una que
    se fatiga). La ranura sale con taladro y sierra y no tiene piezas móviles. Lo que cuesta: la
    ranura recorta el ala vertical hasta 26,9 mm bajo el canto. Por la ranura, W del ángulo libre
    × **0,43**; la rigidez del tramo, × 0,78 (paso 75) a 0,84 (107,95), con flexibilidades en serie
    (`factores_ranura`, criterio de diseño). `vano_maximo` las aplica con el eje hexagonal: en las
    4 máquinas de abajo sigue mandando el tope de 1,8 m; con cargas grandes (4 000 kg) el vano baja.
  - **Con cadena, la misma ranura** (la cuenta, `tiro_vertical_cadena`): una cadena tira de cada
    piñón hacia el otro piñón de su lazo. Los lazos 1:1 tienen los dos piñones a la misma altura:
    tiro HORIZONTAL (coseno vertical 0), que toma la pared de la ranura (≤ 1,2 kN con 0,37 kW a
    0,32 m/s de cadena, sobre la cara del doble plano de 6 × 8 mm: ≈ 25 MPa). La motriz tira hacia
    el motor, que va DEBAJO: coseno vertical −0,94 (20° de la vertical), que asienta el eje en el
    fondo. Ninguna tracción tiene componente hacia arriba: la ranura abierta no deja salir el
    rodillo y no hace falta tapa ni el eje trabado de F6. Con cadena, cambiar un rodillo es además
    abrir sus dos lazos (eslabón de unión) y quitar la guarda; el eje ya no pide llave.
- **E7. BOM del eje.** El eje se fabrica de la barra: pieza A-MEDIDA nombrada «Eje del rodillo
  (barra hexagonal 11 EN 10278, extremos con doble plano 8)», con el largo de corte en la fila (456
  en la piloto, 601 con 500 de ancho útil). Sin tuercas de eje en la BOM: 2 × 6202-HEX11 por
  rodillo y los separadores. La norma va en la descripción: la columna «norma» es de lo que se
  compra (`designacion_comercial`: un rol «Eje…» se fabrica).
- **E8. Compatibilidad: otro campo oculto, sin bump.** `eje: "roscado" | "hexagonal"`
  (`SkipJsonSchema`, default «roscado» = F6). El sello (`exec_rodillos_cadena.sellar`) lo pone en
  «hexagonal» a todo comando nuevo junto con `taller=True`; un `taller=False` explícito deja el
  eje roscado y «hexagonal» sin `taller` es error (lo pide la tapa con alojamiento). Un log F6
  (`taller` sin `eje`) regenera idéntico: huella de piezas, uniones y anclajes y la geométrica
  (volumen y caja) congeladas con el código de 10cd6be. `version` sigue en 3 (el executor no
  cambió: D11 igual) y `CAMPOS` suma `eje`.
- **E9. Criterio de uniones** (`services/criterio_uniones.py`, para que la propuesta de estructura
  siga coincidiendo con la plantilla): regla 8, un eje HEXAGONAL ↔ estructura es `contacto` (se
  calza); regla 4b, el separador del eje contra el ala también es `contacto` (tope suelto).

**Archivos**: `library/rodillos_cadena_eje.py` (nuevo: cotas, secciones, asiento, W del hexágono,
factores de la ranura y el tiro de la cadena), `library/rodillos_cadena.py` (`eje`, `eje_hex`,
`rodamiento_de`, vano), `rodillos_cadena_pies.py` (masa estimada), `rodillos_cadena_reglas.py`
(capacidad con el hexágono y el 6202-HEX11), `builders_rodaje.py` (`bearing_hex`),
`data/70_rodamientos.yaml` (la ref), `commands/receta_rodillos_eje.py` (nuevo: ranuras, eje,
separadores y uniones), `receta_rodillos_cadena.py` (las ramas), `models_rodillos_cadena.py` y
`exec_rodillos_cadena.py` (el campo y el sello), `models_rodillos.py` (tensores sin la ref).

**Medido** (masa real del modelo; estimada sin el ×1,10):

| máquina | sólidos F6 → F7 | masa real F6 → F7 | estimada F7 | pie (carga por pie) | eje |
|---|---|---|---|---|---|
| 1 m | 206 → 166 | 112,2 → 111,3 kg | 113,4 | PIE-M8-30 (84 de 120) | 601 |
| 3 m de F3 | 528 → 408 | 240,1 → 237,4 kg | 243,5 | PIE-M8-30 (117 de 120) | 601 |
| 4 m, TUBOR-3, 400 kg | 636 → 492 | 370,0 → 366,8 kg | 374,2 | PIE-M10-40 (152 de 200) | 601 |
| 1,5 m libre (la piloto) | 252 → 180 | 97,3 → 95,9 kg | 99,2 | PIE-M8-30 (78 de 120) | 456 |

- Ninguna familia de pie cambió. 0 interferencias sin tope y SIN excluir la tornillería (libre
  1,5 m y cadena 3 m). Puerta VERDE sin avisos en la piloto: la llave entra en sus 16 fijadores
  (4 tuercas soldadas, 4 contratuercas y 8 anclajes: las 72 tuercas de eje de F6 ya no están).
  Gravedad VERDE (tortura) en la piloto libre y en el 3 m con cadena.
- El rodillo de la piloto (eje, tubo, tapas, rodamientos y separadores) sube 30 mm, hasta sacar el
  eje por encima del canto del larguero, sin tocar ninguna otra pieza; con cadena (con buje y
  piñón), sin tocar los largueros.

**Tests**: `tests/test_plantilla_rodillos_f7.py` (2 con `-m torture`). Fijados al eje roscado
(miden F6): `test_plantilla_rodillos_f6` (su `_doc`) y la plantilla de `test_mcp_sin_friccion_f5`
(la unión apernada eje ↔ larguero). Recalibrados: los 16 fijadores de la puerta
(`test_plantilla_rodillos_cadena`), el criterio de uniones con los dos ejes
(`test_criterio_uniones`), `banco_guardas` (el contacto en una arista da una ShapeList) y los
conteos del catálogo (474 refs, 42 rodamientos).

**Fuera** (no se decidió): contrastar las cotas del 6202-HEX11 con la ficha de un fabricante; la
concentración de tensiones en el fondo de la ranura (el arco de r 4,25 la suaviza); la regla
«flecha de bastidor» de la puerta sigue con la sección entera del catálogo (la plantilla ya
recorta su vano); las 4 preguntas a Mario.

### F6 (2026-10-28): eje trabado, 6201 de compra, contratuerca y anclajes accesibles

**Origen**: el revisor de taller ciego revisó la piloto de la familia «rodillos por gravedad»
(`motriz: libre`, L 1500, W 400, paso 75, `anclaje: true`) y halló cuatro defectos de la PLANTILLA
(valen también con cadena):
1. ALTA: los 2 anclajes de cada placa de piso quedaban bajo la placa de la pata (150 × 150, mismo
   X-Y): 26 mm libres, no entran el taladro ni el dado de la tuerca. Y la BOM no traía los anclajes
   (la placa tenía los Ø14, sin perno).
2. MEDIA: el eje (M12 liso en el modelo, una tuerca exterior por lado) no fijaba nada: 10 mm sin
   tuerca interior ni separador entre la tapa y el ala; el rodillo jugaba ±10 mm y el eje podía
   girar en el agujero.
3. MEDIA: el pie nivelador sin contratuerca: la altura no queda trabada antes de soldar el disco.
4. MEDIA: las tapas con 6201 salían A-MEDIDA y la BOM no traía los 6201.

**Decisiones (vetables por número)**:
- **E1. Anclajes por fuera de la placa de la pata, de compra.** La placa de piso se alarga en X a
  260 × 150 × 10 y los 2 anclajes van sobre X a ±105 mm del eje de la pata: **30 mm** del eje del
  anclaje al borde de la placa de la pata (`ACCESO_ANCLAJE`). La cifra: el dado de la tuerca AF 19
  pide 1,5 × 19 / 2 + 5 = 19,3 mm de radio y el porta-brocas SDS-plus del rotomartillo (Ø ≈ 50),
  25 + 5 de margen; manda el porta-brocas. Canto de la placa a 25 mm del taladro (≥ 1,5 · Ø14 = 21,
  EN 1993-1-8 tabla 3.3). Sobre X y no sobre Y: entre las patas va el motor.
  - Ref nueva `ANCLA-EXP-M12` en `108_pernos.yaml` (categoría `pernos`: es tornillería para la
    puerta y la BOM): anclaje de expansión M12 × 115 (espárrago, camisa, arandela Ø24 × 3, tuerca
    AF 19 × 10), taladro Ø12, agujero en la placa Ø14, hef 70, tfix ≤ 20, par 60 N·m. Ejemplo: «del
    orden de Hilti HST3 M12x115/20 o Fischer FAZ II 12/20», EAD 330232; `cotas_verificadas: false`
    (no se contrastaron con la ficha del fabricante). Builder nuevo `expansion_anchor`
    (`builders_fijacion.py`): origen en la cara de asiento, el espárrago baja 90 mm (placa +
    concreto).
  - Cada anclaje va en `contacto` con su placa (el perno en la pieza que atraviesa, como pide el
    criterio de taller); lo que ancla es el `ground` de la placa, con «2 anclajes de expansión M12»
    en su nota.
- **E2. Contratuerca del vástago** (`TUERCA-M{rosca}` del pie elegido: M8, M10 o M12 según la
  carga), bajo la tuerca soldada. Ocupa rosca: el recorrido pasa a vástago − 2 tuercas y el pie
  sigue a la mitad (PIE-M8-30: ±11,75 → ±8,5 mm; PIE-M10-40: ±16 → ±12). Lo publica la regla «pies
  niveladores».
- **E3. Eje trabado y juego axial acotado.** Tuerca interior `TUERCA-M12` contra la cara interior
  de cada ala (con la exterior, el eje queda apretado al ala: no gira ni corre) y separador de
  tubo Ø16 × 2 sobre el eje, de la tuerca interior hasta **0,5 mm** del aro INTERIOR del 6201
  (juego axial ≤ 0,5 mm por lado; Ø16 < hombro del aro interior). El lado sin cadena pasa de 10 a
  16 mm entre el tubo y el ala (tuerca 10 + separador 5,5 + juego 0,5): el larguero −Y (y el +Y en
  libre) se abre 6 mm. Del lado de la cadena el separador pasa por dentro del buje y del piñón:
  el agujero de los dos se abre a Ø20 (el piloto Ø12,7 del Z15 es «a maquinar»), 2 mm de holgura;
  la tuerca interior queda a 5,3 mm del piñón.
- **E4. 6201 de compra.** La tapa (A-MEDIDA, «Tapa con alojamiento de rodamiento 6201») lleva el
  asiento Ø32 × 10 en su cara de afuera y un hombro Ø26 que apoya sólo el aro exterior; el 6201 va
  como pieza del catálogo (`70_rodamientos.yaml`): la BOM trae 2 por rodillo.
- **E5. Compatibilidad: sello de entrada, sin bump.** Campo oculto `taller` (`SkipJsonSchema`,
  default False = la geometría de la v3) que `exec_rodillos_cadena.sellar` (`al_crear`) pone en
  True a todo comando NUEVO, como `cierres` de `create_belt_conveyor`. La `version` sigue en 3: el
  executor no cambió (huella D11 igual) y lo nuevo cambia los params, así que cambia la firma.

**Archivos**: `library/rodillos_cadena.py` (`taller`, holgura del lado sin cadena),
`rodillos_cadena_pies.py` (pila con contratuerca, placa de piso y anclajes, masa estimada),
`rodillos_cadena_reglas.py` (pasa `taller`; recorrido con contratuerca),
`commands/receta_rodillos_cadena.py` (`_tapas_taller`, `_traba_eje`, el piñón taladrado, el pie),
`models_rodillos_cadena.py` (`taller`), `exec_rodillos_cadena.py` (`sellar`), la ref y su builder.
Dos ajustes en `services/` para que la plantilla siga pasando sus propias pruebas de estructura:
- regla 4b de `criterio_uniones`: separador DEL EJE ↔ eje = `contacto` (la tuerca que lo toca no
  lo aprieta);
- `propuesta_estructura` no propone `ground` a la tornillería que entra en la losa junto a una pieza
  ya anclada (el perno de anclaje, como `z_piso` de la puerta).

**Medido** (masa real del modelo regenerado; estimada sin el ×1,10):

| máquina | sólidos v3 → F6 | masa real v3 → F6 | estimada F6 | pie (carga por pie F6) |
|---|---|---|---|---|
| 1 m | 134 → 206 | 105,7 → 112,2 kg | 113,8 | PIE-M8-30 (80 de 120) |
| 3 m de F3 | 330 → 528 | 229,9 → 240,1 kg | 244,6 | PIE-M8-30 (110 de 120) |
| 4 m, TUBOR-3, 400 kg | 396 → 636 | 390,4 → 403,8 kg | 409,3 | PIE-M10-40 (151 de 200) |
| 1,5 m libre (la piloto) | 132 → 252 | 90,7 → 97,3 kg | 99,8 | PIE-M8-30 (74 de 120) |

- Ninguna familia de pie cambió. 0 interferencias sin tope y SIN excluir la tornillería (libre
  1,5 m y cadena 3 m). Puerta VERDE sin avisos: la llave entra en los 88 fijadores de la piloto
  (72 tuercas de eje, 4 soldadas, 4 contratuercas, 8 anclajes) y en los 56 del 1 m. Un cilindro
  de Ø50 sobre cada anclaje no toca nada. Gravedad VERDE en la piloto (tortura) y la tortura D3,
  ya con el sello, VERDE en los 4 tamaños (31, 45, 66 y 83 s en esta máquina; sin anclaje, 45 s).
- Sin el sello, piezas, uniones y anclajes idénticos a la v3 (huella congelada antes de F6, y la
  geométrica de volumen y caja también).
- `check_interference` de «Rodillos» en el 3 m: 662 parejas candidatas (482 en la v3).

**Tests**: 23 en `tests/test_plantilla_rodillos_f6.py` (1 con `-m torture`). Recalibrados los que
fijaban la v3 sobre una plantilla recién generada: los 56 fijadores de la puerta (F2), un log v1
con `taller: False` explícito (F4), las parejas de D10 en `test_mcp_sin_friccion_f5` y los conteos
del catálogo (473 refs, 18 pernos). `CAMPOS` suma `taller`; `VERSIONES` no cambia.

**Fuera** (no se decidió): las 4 preguntas a Mario; el reparto de la carga por pata según el COM;
contrastar las cotas del anclaje con la ficha del fabricante.

### F5 (2026-10-21): v3 — pie nivelador de catálogo en cada pata

- Archivos:
  - `library/rodillos_cadena_pies.py` (nuevo, puro): la pila de la pata, `masa_estimada` y
    `elegir` (la familia);
  - `rodillos_cadena.py`: `disposicion(anclaje=True)` y el campo `pies`;
  - `rodillos_cadena_reglas.py`: la regla «pies niveladores», justo después de «carga de diseño»;
  - `commands/receta_rodillos_cadena.py`: `_pie` (placa de la pata, tuerca, pie y placa de piso);
  - `models_rodillos_cadena.py`: `anclaje: bool = True`;
  - `exec_rodillos_cadena.py`: `version=3`. La huella D11 no cambió: el executor es el mismo.
- Tests: 16 en `tests/test_plantilla_rodillos_f5.py` y 1 con `-m torture` (sin anclaje, 2 m,
  con gravedad). Se ajustaron los de F2 y F4 que fijaban lo de antes:
  - 24 fijadores en el acceso de herramienta (las 4 tuercas soldadas también se miden);
  - la placa que apoya en `position.z` es ahora la de piso;
  - el travesaño de `libre` va a media pata sobre la pila;
  - la regla nueva en el conjunto de D9;
  - `version >= 2`.
  También `test_contrato_comandos` (campo `anclaje`, v3) y `test_version_comandos`
  (`create_roller_conveyor@3`).
- **Cómo es la pata** (desde el piso, con el pie a la mitad del recorrido):
  1. placa de piso 150 × 150 × 10 con los 2 anclajes Ø14 de siempre (sólo con `anclaje`);
  2. disco del pie;
  3. vástago libre;
  4. tuerca DIN 934 de la rosca del pie, soldada bajo la placa de la pata;
  5. placa de la pata, con barreno de paso del vástago (ISO 273 media);
  6. tubo de la pata. El vástago sube por dentro: el TUBO-2X2 es hueco.
- **Recorrido** = vástago − tuerca: arriba, el vástago engrana la tuerca entera; abajo, el disco
  toca la tuerca. Se publica ± la mitad.
- **Medido** (masa real = `scene_mass_properties` del modelo regenerado):

  | máquina | masa real | estimada (sin margen) | patas | pie | carga por pie (real) | recorrido |
  |---|---|---|---|---|---|---|
  | 1 m | 105.7 kg | 105.8 kg | 4 | PIE-M8-30 | 77 de 120 kg | ±11.75 mm |
  | 3 m de F3 (`carga_kg` 200) | 229.9 kg | 230.1 kg | 6 | PIE-M8-30 | 108 de 120 kg | ±11.75 mm |
  | 4 m, TUBOR-3, `carga_kg` 400 | 421.3 kg | 421.6 kg | 8 | PIE-M10-40 | 154 de 200 kg | ±16 mm |
  | 1 m libre | 71.8 kg | 71.9 kg | 4 | PIE-M8-30 | 64 de 120 kg | ±11.75 mm |

  - La estimada (catálogo + chapa de las cotas) da lo mismo que el modelo, ±0.1 %. Se usa
    × 1.10 por la soldadura y la tornillería que el modelo no pesa: en el 3 m, 113 kg por pie.
  - 3 m: 0 interferencias sin tope y sin excluir lo declarado; el techo de los rodillos sigue
    en 750; la puerta da VERDE sin truncar.
  - Tortura D3 con gravedad, VERDE en los 4 tamaños: 52, 77, 145 y 253 s (F4: 49, 85, 114 y
    127). El de 4 m duplica: suma 24 sólidos al pie de 8 patas. Sin anclaje (2 m): 87 s.
- **Decisiones que tomó la implementación**:
  - **Tuerca BAJO la placa**, por fuera del tubo: se suelda y se inspecciona a la vista, y el
    recorrido es vástago − tuerca. Encima, dentro del tubo, perdería además el espesor de la
    placa.
  - **El disco se suelda a la placa de piso** al terminar de nivelar. Si sólo apoyara, el
    anclaje sujetaría la placa pero no el bastidor. Re-nivelar después pide amolar el cordón.
  - **Sin `anclaje`** el `ground` va en el pie (disco al piso) y no hay placa de piso.
  - **Las cotas se arman con la pila del pie MAYOR**: los chequeos de altura mínima y de
    portamotor quedan del lado seguro. Ya elegido el pie, las patas se alargan lo que baja la pila.
  - **Si ningún pie alcanza, va el mayor y la regla da error**, no la plantilla: así un log v2
    con mucha carga sigue regenerando (el mismo criterio del FS < 1 de la cadena en F4).
  - La regla usa la mayor de dos cargas: `carga_kg` de la plantilla o la ficha llena de
    paquetes. FS ≥ 1 = ok: el impacto ×1.5 ya es el margen.
  - Nombres por rol, con la estación de la pata: «Pie nivelador (−Y, alimentación)», «Tuerca
    soldada del pie (…)», «Placa de la pata (…)», «Placa de piso (…)».
- **Fuera** (no se decidió):
  - contratuerca de bloqueo del vástago: el catálogo no la trae y el contrato pide una sola
    tuerca;
  - reparto de la carga por pata según el COM (la pata de la motriz lleva el motor): el
    contrato pide reparto igual × 1.5;
  - las 4 preguntas a Mario siguen abiertas.

### F4 (2026-10-21): v2 — guardas cerradas, bandeja, velocidad, tensado y engineering_check

- Archivos:
  - `library/rodillos_cadena.py` queda de fachada (cotas del bastidor, `disposicion`);
  - `rodillos_cadena_motriz.py`: motor, piñón por velocidad, portamotor con orejas, recorrido;
  - `rodillos_cadena_guardas.py`: cárter, guarda fija y bandeja como polígonos XZ/YZ;
  - `rodillos_cadena_reglas.py`: las reglas de D9;
  - `commands/receta_rodillos_guardas.py`: las guardas pasadas a comandos.
  - `rules.conveyor_engineering_check` deriva a las reglas nuevas cuando el dict trae
    `plantilla` (927 líneas, una menos). `services/engineering_rules.conveyor_params_from_doc`
    devuelve también el último `create_roller_conveyor`. `/api/checks` y la memoria no cambiaron.
  - `create_roller_conveyor` v2 con `velocidad_m_s` opcional (huella nueva). La etiqueta de
    `insert_project` suma `create_roller_conveyor@2`.
- Tests: 15 en `tests/test_plantilla_rodillos_f4.py` y el banco `tests/banco_guardas.py`
  (sonda de dedo por rayos + interferencias sin el tope de 400 parejas). La tortura D3 suma la
  máquina de F3: los 4 tamaños dan VERDE con gravedad (49, 85, 114 y 127 s). Suite completa en
  el worktree: **4062 passed, 2 skipped**; ruff limpio.
- **Medido** sobre la máquina de F3 (3 m, ficha 0.25 m/s, paquetes de 400 mm y 25 kg,
  `carga_kg` 200):
  - 312 sólidos y 411 uniones; regenerate en 6.4 s.
  - Interferencias: 0 sin excluir lo declarado, sin tope de parejas. También 0 con el conjunto
    que corre en +3 mm y en −8.76 mm. Las guardas de D4/D5 quedan a ≥ 3 mm de toda cadena y
    piñón en las dos puntas. Los ramales de la motriz, medidos en 2D, tampoco las tocan.
  - Puerta: VERDE sin truncar. Son 367 parejas candidatas de 400 (2 m: 254; 4 m TUBOR-3: 364).
  - Sonda de dedo Ø8: ningún alcance desde abajo, desde el lado del motor (bajo los tubos) ni
    desde afuera. La grilla va a 3.5–4 mm en la transmisión y a 9 mm en el resto.
    - Controles: sin bandeja y sin guarda de la transmisión, la sonda llega a un lazo y a la
      motriz.
    - Sin el faldón llega a los lazos desde afuera: es un defecto nuevo de F2, ver abajo.
  - Tensado: 46 eslabones, +8.76 mm (1.5 % de 584 mm) y −3 mm. Las dos ranuras frenan a 1.5 mm
    del recorrido.
  - Velocidad: 0.25 da el Z30 (0.266 m/s, +6.4 %). 0.15 da el Z17 (0.151 m/s). 0.40 con
    MOTOR-037 da error con las velocidades que salen y «MOTOR-150 + piñón Z30 da 0.372 m/s, pero
    no cabe entre las patas: ancho_util mínimo 606».
  - `engineering_check`:
    - velocidad ok;
    - 4 rodillos bajo el paquete;
    - rodillo: 6.2 kg contra 37 kg de capacidad (FS 5.9);
    - carga de diseño 175 ≤ 200 kg;
    - motor FS 4.05;
    - **cadena FS 1.09 → aviso** (el que leyó el revisor);
    - tensado ok.
- **Decisiones que tomó la implementación**:
  - **Rendija de 5 mm** en las cuatro paredes. El solape sobre la línea de centros es 20 + b + 3
    + 2 (33.8 mm en la de 3 m).
    - La guarda fija arranca 3 mm + el recorrido de montaje sobre el eje del motor: es la única
      pared que el eje cruza y no lleva barreno.
    - El cárter sube hasta ahí más el solape. Tope: 3 mm bajo las cadenas 1:1 en la punta de
      montaje.
  - **Extremo +X del cárter** vertical al pie, para librar el riel de patas del motor (2 mm).
    Después sigue la línea de centros.
  - **Extremo +X de la guarda fija**: se pliega a 45° hasta una vertical dentro del bastidor y
    a ≥ 3 mm del último piñón. Lo cierra hasta la guarda de cadenas una **tapa** en YZ, con la
    muesca por donde baja la pestaña interior de la guarda.
  - **Orejas**: chapa de 6 que va de 75 mm arriba a 75 mm abajo del travesaño.
    - 2 M10 pasantes a la pata, los dos sobre el eje de la pata.
    - La ranura A abre arriba y frena el montaje; la B abre abajo y frena el tensado.
    - El tubo del portamotor se acorta 2 × 6 mm.
  - **Base del motor lisa** con 4 roscas M8 bajo los rieles. Su borde +Y queda a 1 mm de la
    oreja.
  - **D9, FS < 1 = error en `engineering_check`**, no en la plantilla. Si la plantilla lo
    rechazara, un log v1 con MOTOR-075/150 dejaría de regenerar: con Z30 la cadena da FS < 1.
    La plantilla sigue rechazando sólo potencia insuficiente, como en v1.
  - **D9, carga**: en la ficha, `carga_kg` es la de UN paquete (como en
    `conveyor_engineering_check`). «Lleno» = paquetes sin hueco. El motor se verifica con la
    mayor de las dos cargas.
  - **D6**: el piñón elegido tiene que armar también las guardas. Con el Z17 el extremo +X no
    libraba la cadena del último piñón: por eso el pliegue hacia afuera.
  - **Puerta de entrega**: `interference_report` corta en 400 parejas candidatas por caja.
    - La pestaña exterior original de la guarda de cadenas bajaba la caja a los tubos: se
      reemplazó por un **faldón** aparte, soldado a los separadores.
    - Las pestañas atornilladas (bandeja y guarda fija) suben sólo hasta bajo los tubos cuando
      la zona plana del ala deja el M6.
    - Con TUBOR-3 la bandeja va sin pestaña interior y con el borde bajo el extremo del tubo.
  - `create_extrude_poly` extruye hacia la normal del polígono: en sentido horario, la chapa
    salía corrida un espesor. La receta lo pasa antihorario.
- **Defecto nuevo** (lo halló la sonda, ya en [defectos](../defectos.md)): la guarda de cadenas
  de F2 dejaba por fuera 24 mm entre el canto del ala y la chapa. Sólo los separadores la
  cortaban, cada 8 pasos.
- **Fuera** (no se decidió):
  - las «Preguntas para Mario»;
  - el tope de 400 parejas de la puerta (hito H): una máquina más larga lo vuelve a pasar;
  - los M6 y M10 no tienen geometría, así que el acceso de herramienta no los evalúa;
  - el tiro de la cadena sobre el eje y la L10 de rodillos libres sin velocidad en la ficha
    quedan fuera de la capacidad del rodillo.

### F2 (2026-10-20): `create_roller_conveyor`, el super-comando

- Archivos:
  - `library/rodillos_cadena.py` (cotas PURAS: `disposicion`, `motor_local`, `pasos_rodillo`,
    `vano_maximo`, `holgura_motriz`; validaciones con el error que dice qué cambiar);
  - `commands/receta_rodillos_cadena.py` (las cotas → comandos del registro, en orden),
    `exec_rodillos_cadena.py` (executor, grupos, `SPECS_RODILLOS_CADENA` y
    `comandos_efectivos`), `models_rodillos_cadena.py` (params y guía de montaje);
  - `registry.py` sigue en 2147 líneas (un `CommandSpec` en una línea paga el import);
  - `pistas.py`, `design/instrucciones.py` (la guía MCP lo nombra; golden re-congelado);
  - `services/transmision_rules.py` recorre `comandos_efectivos`, y `services/assertions.py`
    resuelve `$k` también a los command_id sintéticos `{k}_…` (sirve a `insert_project`).
- **Cómo está hecho**: COMPUESTO (`composite=True`, como `insert_project`). El executor corre
  `insert_component`, `drill_hole`, `create_chain` (`fase: "auto"`, `eslabones`), `fasten` en
  conjuntos, `ground`… con ids `{cmd}_{sufijo}`. Así hereda las anclas, la fase y las uniones
  sin copiar geometría, y la puerta revisa interferencias ENTRE piezas (con un solo command_id
  `same_command_pairs` las excluiría todas, como en `create_conveyor`). Las cotas y la receta
  no entran a la huella D11: cambiarlas con los mismos params obliga a subir su `version`.
- Tests: 24 en `tests/test_plantilla_rodillos_cadena.py` y 3 con `-m torture` (D3: 1, 2 y 4 m
  con gravedad). También se tocaron `test_contrato_comandos` (campos y huella),
  `test_version_comandos` (los compuestos) y `test_despacho_unico` (58 comandos).
- **Medido** contra la piloto: copia de la base, proyecto 74, mismo proceso y sin caché.
  - Log: 341 comandos contra 1. Piezas: 201 contra 200.
  - Uniones: 160 / 46 / 58 contra 160 / 46 / 56 (contacto, perno, soldadura).
  - Regenerate: 2.2–3.2 s los dos.
  - Interferencias: cero, ni siquiera entre piezas unidas.
  - Puerta: VERDE sin avisos, con la llave entrando en las 40 tuercas. Con gravedad, en los
    tres tamaños: 27, 42 y 85 s.
  - Peor lazo: 0.006 mm de estirado.
- **Decisiones que tomó la implementación** (el plan no las fijaba):
  - **Cadena motriz tensable** (el defecto del revisor F0): va inclinada 20° hacia la
    alimentación y el motor corre ±20 mm en X sobre ranuras ABIERTAS de su base. Eso da
    ±6.8 mm de centros: más que medio eslabón, lo que pide quitar un par al gastarse.
    - Vertical, como la piloto, no se puede tensar con ranuras horizontales.
    - Hacia +X, el motor sale del bastidor.
    - `holgura_motriz` exige ≥ 5 mm contra la cadena que abraza el penúltimo piñón. Con los
      tres pasos y los tres motores quedan de 7.7 a 32 mm.
    - Los centros salen de `eslabones_pares`: el menor par cuyo exacto deja la caja de
      bornes 10 mm bajo los tubos.
  - **Pasos ofrecidos: 95.25, 107.95 y 120.65** (lazos de 30, 32 y 34). El de 82.55 (28) se
    cae: la motriz libra los 5 mm al penúltimo piñón sólo bajo 6°, y ahí la ranura casi no
    tensa (a 20° choca: −3.1 mm; a 10°, 3.4 mm). El 95.25 a 25° deja 3 mm: por eso 20°.
  - **Buje con brida** del Ø del tubo, soldada a su extremo, y cuello Ø40 para el cubo del
    piñón. El buje Ø40 de la piloto no tocaba el anillo del tubo, así que no se podía soldar.
    Holgura radial 0.5 sobre el eje fijo.
  - **Patas en H con UN travesaño** por estación, bajo (z = 150); en la motriz el travesaño
    es el portamotor. La alimentación de la piloto llevaba dos.
    - Placa base de 150 × 150 con 2 anclajes Ø14 en diagonal: la de 120 de la piloto no
      tenía barrenos.
    - Voladizo igual en los dos extremos.
    - Estaciones intermedias para que el vano no pase de min(1.8 m, flecha L/240 y
      σ ≤ 0.6·fy del ángulo LIBRE con `carga_kg` repartida).
  - **Guarda de cadenas** atornillada (M6 a una rosca de 15 mm) a separadores soldados sobre el
    canto del ala vertical, entre rodillos y cada ≤ 8 pasos. Su altura sale del mayor de: cadena
    + 3 mm, o tubo + 3 mm + pestaña.
  - **`carga_kg`** fija el vano y verifica el motor. El modelo:
    - rodadura 5 % y arranque ×1.5;
    - cada lazo con η 0.98, y el rodillo k recibe su parte a través de k lazos;
    - reductor 0.85.
  - **El motor va entre las patas, bajo los rodillos**. Si no cabe, el error da el
    `ancho_util` mínimo: 469 mm con MOTOR-037, 538 con MOTOR-075 y 606 con MOTOR-150.
  - Sólo `position`, sin `rotation`: para girarlo, `transform_group` sobre el grupo raíz
    (probado: sigue VERDE).
  - Grupo raíz sin miembros directos y un subgrupo por subsistema, como `insert_project`.
- **Intentos descartados**:
  - Motriz a 30°: la cadena pasaba a 42.9 mm del centro del penúltimo piñón y hacían falta
    46.6.
  - Rendimiento 0.98ⁿ (toda la potencia por todos los lazos): un bastidor de 6 m pedía un
    motor mayor que el real.
  - Buje cortado al fondo del CUBO: la placa de la hilera 2 del doble-simple baja más, y
    quedaban 11.2 mm³ de solape. Ahora corta al más bajo de los dos.
- **Pendiente** (fuera del alcance):
  - La regla de cadenas avisa dos cosas que hereda la piloto: piñón de 15 dientes (< 17; el
    doble-simple del catálogo es Z15) y motriz a 11.5 pasos (< 30).
  - Los lints que recorren el log no ven los barrenos de un compuesto. Los anclajes Ø14 sin
    perno no avisan, igual que en un `create_conveyor`.
  - Una plantilla dentro de un `insert_project` no se expande para la regla de cadenas.

### F1 (2026-10-20): `create_chain` v2, fase automática y eslabones fijos

- Archivos:
  - `library/transmision.py` (479 líneas): `estirado_lazo` y `giro_para_engranar`, puras;
  - `commands/exec_transmision.py` (345): `_eslabones`, `engranar` y `_lleva_cadena`;
  - `models_transmision.py` (115): `eslabones` y `fase`, con la guía en la descripción;
  - `expressions.py`: `centros_cadena`;
  - `registry.py`: sólo `version=2` en la misma línea.

  Tests: 21 en `tests/test_cadena_engrane.py`; los de siempre en `test_contrato_comandos` (v2,
  huella y campos nuevos). `test_version_comandos` congela la etiqueta de versiones de
  `insert_project`, que ahora incluye `create_chain@2`. Como la etiqueta lleva todas las
  versiones ≠ 1, la caché de todo proyecto con `insert_project` se invalida una vez.
- Suite completa en el worktree: **3296 passed, 2 skipped**. Ruff verde.
- **Cómo engrana.** El estirado es lo que el eslabón más largo de `rodillos_del_lazo` pasa del
  paso. Tolerancia: 0.05 mm.
  - En 1:1 se prueban primero la fase relativa 0 y la de medio diente.
  - Si no basta, se barre un diente en 96 pasos y se refina con 40 de sección áurea. Gana el
    menor estirado en centésimas de mm y, a igual estirado, el giro más chico.
  - El piñón se gira con `registry._world_place` sobre su ancla `eje` (shape, matriz y anclas a
    la vez), con el signo de su eje respecto del lazo, y se vuelve a medir.
  - «Libre» = ningún `fasten` contacto de una cadena previa lo tiene como `b`. Se prefiere B.
- **Medido sobre la piloto** (copia de la base, regenerada fuera de la API):
  - Sin tocar nada: 3.5 s, todo igual. El log no trae los params nuevos, así que no gira nada.
  - Quitando los giros a mano (12° de `c63` y 3° de `c94`), con `fase: "auto"` en las 20
    cadenas, `eslabones: 48` en la motriz y `c_motriz = centros_cadena(12.7, 30, 15, 48)`:
    peor estirado 0.006 mm, sin «cadena desfasada» y 3.3 s.
  - La motriz quedó con el Z30 a 3° de su conducido, el mismo número que la piloto puso a mano.
- **Decisiones que tomó la implementación**:
  - Con los dos piñones ya cargados, `auto` FALLA con el giro exacto que hace falta. Girar uno
    cargado desarmaría el lazo anterior, que se armó sobre su fase vieja.
  - Una cadena ya engranada (≤ 0.05 mm) no toca los piñones: los logs con el giro a mano siguen
    iguales con `auto`.
  - `eslabones` impar → error, que pide N ± 1. Un N de más se acepta: queda flecha y la regla la
    publica.
  - La regla «transmisión por cadena» no cambió. Tampoco avisa un lazo estirado con
    `tal_cual`: sería un aviso nuevo en proyectos viejos y el alcance era `commands`. Queda para
    la F2, que lo puede exigir en sus propios tests.
- **Intento descartado**: el primer criterio («el giro más chico que llega a la tolerancia»)
  dejaba los lazos justo en 0.05 mm (2.625° en la motriz). Se cambió a «el menor estirado en
  centésimas y después el giro más chico», que da 3.000°.

### F0 (2026-10-20): inventario del log de la piloto

Leído en sólo lectura de una COPIA de `data/apolo.db`: la piloto («proyecto 2» en la otra PC) es
aquí el proyecto 74, `transportador-rodillos-cadena-2m`, cuyas revisiones 122–125 son las
remotas 1–4. Último estado = la revisión 125 (largueros de ángulo L). Regenerado fuera de la API
con el código de `main` (`APOLO_GEOM_CACHE=0`): 5.4 s en frío, 201 piezas, nada suprimido.

**Cómo está armado** (341 comandos): 224 `fasten` (66 %), 41 `drill_hole`, 20 `create_chain`,
16 `insert_component`, 10 `pattern_linear`, 8 `set_variable`, 6 `create_box`, 6 `create_group`,
4 `ground`, 3 `create_revolve`, 2 `create_sheet_metal` y 1 `create_cylinder`.

- **Variables** (8): `largo` 2000, `paso` 95.25, `n_rod` 20, `h_eje` 725,
  `x0 = (largo − (n_rod−1)·paso)/2`, `x_motriz = x0 + (n_rod−1)·paso`, `c_motriz` 159.034 (a
  mano) y `z_motor = h_eje − c_motriz`.
- **Bastidor**: 2 × `ANG-75X6` de largo `=largo` (alas hacia afuera y abajo) y 40 barrenos Ø13
  (uno por eje y por lado, cada uno con su `drill_hole`).
- **Rodillo** (uno, arreglado ×20 con `pattern_linear` a `=paso`):
  - eje Ø12 × 608 (cilindro);
  - `TUBOR-2` × 500;
  - dos tapas con 6201 (`create_revolve`);
  - un buje del piñón (revolve);
  - `PINON-ASA40-DS-Z15`.
- **Tuercas**: `TUERCA-M12` a cada lado, también ×20.
- **Piñones en dos familias**:
  - el par (`c16`) arreglado ×10 a `=2*paso`;
  - el impar (`c63`, en `x0 + paso`) con `rotation.z = 12`, también ×10. Ese giro es el medio
    diente.
- **Cadenas**: 19 lazos 1:1 `CADENA-ASA40-1`, alternando la hilera 1 y la 2, más la cadena
  motriz.
  - La motriz va de `PINON-ASA40-1-Z30` (en el `MOTOR-037`) a la hilera 2 del último rodillo:
    48 eslabones, 0.37 kW a 50 rpm.
  - El piñón motriz lleva su propio giro a mano: `rotation.z = 3`.
  - La nota de [cadenas-pinones](cadenas-pinones.md) dice «20 lazos 1:1»: son 19 + la motriz.
- **Patas y travesaños**: 4 patas `TUBO-2X2` de `=h_eje − 65`, con placa base 120 × 120 × 10 y un
  `ground` cada una. Travesaños: superior e inferior en la alimentación y el portamotor en la
  motriz (el de c89 se quitó). La base del motor es de chapa de 8.
- **Guardas**: 3 separadores de 40 × 50 × 23 en `x0 + 1.5·paso`, cada `8·paso`. La guarda de
  las cadenas es de chapa a todo el `largo`; la de la transmisión, otra chapa.
- **Uniones**: 120 contactos, 58 soldaduras y 46 pernos. Son 40 de cada uno de: perno M12 eje ↔
  larguero, tuerca ↔ rosca, 6201 ↔ eje y tapa ↔ tubo. Luego 20 buje ↔ tubo y 20 piñón ↔ buje
  soldados, y el resto, patas, placas, motor y guardas. Están escritas una por una: un fasten
  por conjuntos ([uniones-en-lote](uniones-en-lote.md)) las reduce a unas 15.
- **Grupos** (6): Bastidor, Rodillos, Cadenas, Patas y travesaños, Motorreductor y Guardas.
- **Requisitos**: 100 kg, paquete 400 × 400 × 300, 0.27 m/s, cajas de cartón.

**Medido** (`rodillos_del_lazo` con las fases vivas de cada lazo; estirado = eslabón más largo
menos el paso de 12.7):
- Tal cual: los 19 lazos 1:1 dan de 12.700 a 12.706 mm (las fases relativas son 0° y 12°). La
  motriz da 12.701 a C = 159.034, contra un exacto de 159.03493 para 48 eslabones.
- Sin el giro de 12° en `c63`: los 19 lazos dan 13.970 (un tramo de 7 pasos sobre 7.5 p, el
  otro flojo) **y la motriz 13.337**. El giro de 3° del Z30 sólo vale con la fase de su piñón
  conducido: también la cadena motriz necesitó su fase, aunque no es 1:1.
- 159.035 > 159.03493 → 50 eslabones (exacto 171.952): el salto de 48 a 50 que vio la piloto.

**Correcciones al plan** (hechas arriba, en D2 y F1):
- «Medio diente en impares 1:1» no alcanza: la cadena motriz Z30 → Z15 también tuvo que
  engranar a mano. La fase automática gira el piñón LIBRE lo justo. En 1:1 prefiere 0 o medio
  diente, que son los valores exactos; en otras relaciones barre un diente.
- «Calcula y publica la distancia exacta»: como la cadena es relacional y los piñones ya están
  puestos, el comando la RECOMIENDA (falla con el exacto si no alcanza). Para colocar los
  piñones antes, la expresión `centros_cadena(…)`. La tolerancia de 0.05 mm sobre el exacto
  hace que 159.035 con `eslabones: 48` dé 48.

**Receta para la F2** (lo que la plantilla debe derivar y la piloto dejó a mano):
- **Cotas a mano** que no siguen a `largo` ni al ancho: patas de alimentación en `x = 200`,
  guarda de la transmisión en `x = 1907.5`, todas las Y (−297.5, 349.5, 292.2, ±255/307…),
  travesaños de 571.2, eje de 608 y tubo de 500. La plantilla las deriva del ancho útil y del
  largo.
- **El paso de rodillos no es libre**: con Z15, 95.25 (30 eslabones) o 107.95 (32); con Z14,
  76.2 o 101.6 (`L = z + 2t/p` par). D1 lo ofrece como lista y no como número.
  (2026-10-27: con `motriz: libre` el paso sí es libre, de Ø + 20 mm a 300 mm: `validar_paso`.)
- **`n_rod` par** (los piñones van en dos familias de `n_rod/2`). Con la fase automática basta
  UNA familia ×`n_rod`: la cadena gira los alternos.
- **Centros de la motriz**: `= centros_cadena(12.7, 30, 15, 48)` en vez de 159.034.
- **Las 224 uniones** van en conjuntos.

### F3 (2026-10-21): verificación por MCP — un transportador de 3 m en 7 min

Sesión nueva `claude -p --model opus` sobre la flota (:8100): proyecto 79
«transportador-rodillos-cadena-3m», ficha del encargo con `set_requirements`.
- **Órdenes:** 2 (`create_roller_conveyor` con `expect` sin interferencia: 297 sólidos, 30 rodillos,
  29 lazos + motriz, 3 estaciones; y el tablero de arranque directo en un `run_batch` de 44 acciones
  con `{"erc":"sin_errores"}`).
- **Resultado:** `delivery_check` VERDE con gravedad, sin avisos. 0 interferencias, 297/297 sujetas,
  0 caen, flecha de largueros 0,08 mm, ERC limpio.
- **Costo:** 6 min 56 s, 20 llamadas MCP, USD 2,02, ~150 k tokens de contexto. La piloto a mano: ~1 h
  10 min y ~60 M tokens leídos.
- **Fricción** (hito H): `engineering_check` no reconoce el transportador de la plantilla («no hay
  ningún transportador»), así que no valida la velocidad ni el motor contra lo pedido; respuestas
  de 40–70 KB; los nombres de subgrupo de la plantilla no resuelven en `render_view(isolate)`;
  `check_interference` global trunca a 400 parejas sin decir cuántas faltan.

**El revisor de taller a ciegas** (sesión nueva sólo con las tools de lectura del prompt de
[revisor-de-taller](../revisor-de-taller.md); 8,7 min, USD 1,65) encontró en la plantilla:
- **ALTA — guarda de la transmisión abierta hacia el lado del motor:** desde −Y se ven el piñón Z30
  y la cadena motriz; hay 72,4 mm de franja abierta en la entrada cadena–piñón.
- **ALTA — los 29 lazos y los piñones Z15 quedan al aire por debajo en los 3 m:** la guarda sólo
  tapa por arriba; los ramales inferiores van a 687 mm del piso (ISO 14120: todos los lados
  accesibles).
- **MEDIA — velocidad 0,32 m/s contra 0,25 de la ficha:** la plantilla no tiene param de
  velocidad. El FS de potencia es 1,09.
- **MEDIA — tensado útil de la cadena motriz de ~8 mm:** las ranuras van casi perpendiculares a la
  línea de centros (a ~70°).
- **MEDIA — los lazos rodillo a rodillo no se pueden tensar:** ejes fijos con 1 M12 y eslabones
  exactos. Es una pregunta al cliente.
- **BAJA:** los dos extremos resuelven distinto el travesaño (bajo en la alimentación, alto en la
  motriz); no hay riostra longitudinal; no hay guía lateral del lado −Y.

Bien según el revisor: el acceso a la tuerca M12 (35,4 mm), que el motor sale sin quedar atrapado
y cero interferencias. Los defectos de la plantilla van a su cola de trabajo (fuera del núcleo) y a
[defectos](../defectos.md).

### F4b (2026-10-21): re-verificación con el revisor de taller ciego

El mismo prompt de F3 (`docs/revisor-de-taller.md`, sólo lectura) sobre el proyecto 79 regenerado
con v2, en la flota (:8100): 7 min, 20 turnos, 1,17 USD.
- **Las 2 ALTA de F3 quedaron cerradas**: el revisor ve las guardas cerradas por la bandeja y la
  tapa, con 0 interferencias y gravedad estable. No halló ninguna ALTA nueva.
- `engineering_check` del 79: producto a 0,266 m/s ok, rodillo ok, motor FS 4,44 ok, tensado
  +8,8 / −3 mm ok, cadena FS 1,09 aviso, carga de diseño **error** (7 × 25 = 175 kg contra 150).
- **Las 5 MEDIA**:
  1. «La base del motor no tiene ojales: no se tensa». **Falso positivo**: el recorrido está en las
     orejas ranuradas del portamotor (D7). Los pernos y las ranuras no son sólidos y el revisor no
     los ve. La cadena motriz con 11,5 pasos entre centros y piñón Z15 (< 17) sí es real: queda
     como aviso.
  2. Travesaño de la alimentación soldado vs portamotor con orejas apernadas. Es lo que pide D7;
     es pregunta de criterio, no defecto.
  3. Carga de diseño 175 > 150 kg. Es de la FICHA del 79 (6 cajas acumuladas contra 7 que caben):
     la decide el cliente.
  4. «v = 0,32 m/s». Es la velocidad de la cadena, no la del producto (0,266): el revisor la leyó
     mal, como en F3.
  5. **Placas base lisas, sin pernos niveladores**: un bastidor soldado de 3 m con 6 apoyos sobre
     concreto no se puede nivelar ni ajustar a 750 mm. **Real**: queda como F5 candidata (patas
     con niveladores de catálogo).
