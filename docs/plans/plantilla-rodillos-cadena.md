---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: F0–F3 hechas (2026-10-21): un transportador de 3 m sale con 1 orden en 7 min (piloto a mano: 1 h 10 min), VERDE; el revisor ciego halló 2 ALTA (guardas abiertas abajo y del lado motor) y 3 MEDIA (sin param de velocidad, tensado de la motriz ~8 mm, lazos sin tensado) — hito I
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
- **F4 (M, `commands` + `library`)**: los defectos que el revisor de taller ciego halló en la
  plantilla (§ Bitácora F3), con el contrato de abajo. `create_roller_conveyor` sube a v2.

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
y cero interferencias. Los defectos de la plantilla van al hito I de [hitos](../hitos.md) y a
[defectos](../defectos.md).
