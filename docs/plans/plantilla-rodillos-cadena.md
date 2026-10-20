---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: F0 (inventario de la piloto) y F1 (create_chain v2, fase auto y eslabones) hechas; faltan F2 (el super-comando) y F3 (verificación por MCP)
descripcion: Un transportador de rodillos por cadena sale completo con una sola orden, ya con las correcciones de la piloto
---

# Un transportador de rodillos por cadena con una sola orden

## Estado y origen

Mario quiere sacar muchas máquinas para su tienda ([publicacion-tienda](publicacion-tienda.md)).
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

## Lo que este plan NO hace

- Transportadores por faja o por gravedad sin motor (otra plantilla, si hace falta).

## Riesgos

- Plantilla rígida que no sirve para variaciones → todo por variables y con piezas editables
  después (como `create_conveyor`).

## Bitácora

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
- **`n_rod` par** (los piñones van en dos familias de `n_rod/2`). Con la fase automática basta
  UNA familia ×`n_rod`: la cadena gira los alternos.
- **Centros de la motriz**: `= centros_cadena(12.7, 30, 15, 48)` en vez de 159.034.
- **Las 224 uniones** van en conjuntos.
