---
estado: en curso
nota: F1 mergeada (create_hoist_chain); el elevador de la tanda nocturna la estrena reemplazando sus 6 tramos rectos a mano (2026-10-27); F2a (regla de capacidad de la cadena, FS 7 de iwis, el pasador dimensionado por ella) implementada en su rama, sin mergear; F2b (aleta K1/K2) y F3 (co-simulación, cadena floja como efecto físico, la cadena en el visor) sin empezar
descripcion: Una plataforma cuelga de una cadena de rodillos que pasa por sus piñones, con sus dos amarres atornillados de verdad, y la cadena sigue a la plataforma en cada pose sin choques
---

# La plataforma cuelga de su cadena, amarrada de verdad, y la cadena la sigue cuando sube

## Estado y origen

Medido el 2026-10-27 al modelar por MCP un elevador vertical de cajas (dos cadenas 08B-1, cada
una por un piñón motriz arriba y uno loco abajo, con los dos extremos amarrados a la
plataforma). La sesión principal delegó el contrato y la implementación con criterio propio
(«decide con criterio, deja decisiones vetables escritas»); las D quedan vetables por número.

## El problema (lo que hay hoy)

- `create_chain` (`commands/exec_transmision.py`) sólo arma un LAZO CERRADO entre dos piñones:
  no hay cadena abierta con dos extremos ni eslabón de amarre.
- El elevador (`C:\t\maq\elevador-vertical-cajas-2n`, proyecto 1, 503 comandos) lo resolvió a
  mano con 6 tramos rectos de catálogo (`insert_component CADENA-08B-1` + `length`: ramal
  superior, inferior y de retorno por cadena, c43–c45 y c328–c330), 4 horquillas por
  `run_script` (c513–c516), 4 pasadores cilíndricos, 8 pernos, 4 resortes, 4 tuercas, 12
  taladros y 38 uniones y juntas a mano (84 comandos en total, contados por la verificación de
  abajo).
- Los tramos rectos no siguen a la junta `j_plataforma` (la FK, `robotics/pose.py`, sólo mueve
  cuerpos rígidos): a +1500 mm el pasador del amarre inferior cae donde el modelo deja el ramal
  superior quieto, y el modelador lo tapó con `fasten` «contacto» c541, declarado por él mismo
  como «ARTEFACTO DE REPRESENTACIÓN, no es unión física».
- Un revisor de taller encontró dos veces «la cadena no está unida a la plataforma»: no había
  forma nativa de declarar el amarre (los pasadores eran `fasten perno` contra un tramo recto
  con «interferencia intencional»).

## Lo que se revisó antes de escribir esto

- `library/transmision.py` (480 líneas): la matemática del lazo cerrado (casco convexo de los
  asientos, `_tramo` con flecha, `capas_cadena`). La del lazo abierto es otra (un extremo libre,
  sin cierre), pero reusa `capas_cadena`, `diametro_primitivo` y la idea del casco convexo.
- `builders_transmision.cadena_por_rodillos(cerrada=False)` ya arma una cadena abierta por
  centros de rodillo: placas interiores en los pares (0,1), (2,3)… Con N pasos IMPAR las dos
  puntas quedan con eslabón interior, que es por donde entra un pasador.
- `robotics/pose.py::posed_shapes` es la única FK del servidor: la usan render, `verify` con
  `joint_values`, `scan_motion`, el GIF y las poses de reposo de la puerta de entrega. Un gancho
  ahí cubre a todos.
- `services/marcha_visual.py` reconoce una cadena por `mesh_key` «cadena|…» con 9 partes: un
  prefijo nuevo no la confunde (y no se anima en el visor: F3).
- `exec_transmision.engranar` ya gira un piñón libre (el único caso en que una cadena muta otra
  pieza); `_lleva_cadena` sabe si un piñón carga otra cadena por sus `fasten` contacto.
- `join_bolted` taladra EN SITIO con `_drill_tool` y pone tuercas DIN 934 de catálogo
  (`TUERCA-M8`): el mismo patrón sirve para la varilla del ancla.

## Decisiones (para vetar)

- **D1 — Comando nuevo `create_hoist_chain` («Cadena de izaje»), no un modo de
  `create_chain`.** Otra matemática (abierta, sin cierre), otras piezas (anclas, tuercas,
  taladros, juntas) y otra clave de geometría; `create_chain` queda byte a byte: un log viejo
  regenera idéntico sin subir su `version` ni tocar su executor ni su `mesh_key`.
- **D2 — Params**: `name`, `cadena` (simple), `pinones` (lista ORDENADA de A a B, 1–6),
  `pieza_a`, `pieza_b` (vacío = la de A), `extremo_a`/`extremo_b` (centro del pasador, mundo,
  acepta `=expr`), `sentido` (auto | horario | antihorario), `eslabones` (impar; vacío = el mayor
  impar que no pasa de B), `fase` (auto | tal_cual, default auto: es un comando nuevo).
- **D3 — La cadena gira alrededor de todos sus piñones en el MISMO sentido** (lazo abierto por
  la pieza: elevador, mesa elevadora, contrapeso por un piñón). `sentido: auto` = el camino de
  paso más corto, que es el que no se cruza. Una cadena en serpentina (sentidos alternados)
  queda fuera.
- **D4 — Rodillos a paso EXACTO desde el pasador A**: en línea por los tramos, al llegar a un
  piñón el siguiente es el punto de su círculo de paso a un paso del último y desde ahí de a un
  diente (cuerda = p exacta); se sale por el último asiento que la recta al objetivo dejaría
  afuera (el casco convexo, como el lazo cerrado). N impar. Lo que la cadena queda corta de B
  (< 2 pasos) lo toma el ANCLA B: su pasador va en el último rodillo y la varilla queda más
  afuera; se publica en el nombre como «ajuste». Así no hay eslabones estirados.
- **D5 — El amarre es una ANCLA de horquilla roscada derivada de la norma de la cadena**
  (ISO 606 / ANSI B29.1, cotas de la ficha del catálogo): mejillas = las capas de las placas
  exteriores (mismo espesor t y alto h2: la sección del eslabón exterior que reemplaza, resiste
  lo que la cadena), ranura = el ancho sobre placas interiores, agujero = perno d2 + 0,2 (el
  pasador es el perno del eslabón de unión con clip, el «candado», que viene con la cadena), yugo
  de espesor = Ø de la varilla, varilla lisa como la tornillería del catálogo. Cadena ↔ ancla no
  se tocan por construcción. Es pieza A MEDIDA (la hace el taller: así sale en la BOM), no de
  catálogo.
- **D6 — Varilla por la rotura**: la menor métrica con Rp0,2 de una 8.8 (ISO 898-1, 640 MPa) ×
  As ≥ la rotura mínima de la cadena (ASA 40, 08B y 10B → M8; 12B → M10): rompe antes la cadena,
  que es la que se inspecciona. Largo = hasta 2 filetes más allá de tuerca + contratuerca DIN 934,
  redondeado a 5 mm. El ajuste de tensado de cada ancla es el hueco yugo ↔ placa (≥ 1 mm o
  error); el desgaste de largo plazo es del tensor del piñón loco.
- **D7 — El comando taladra la pieza de amarre EN SITIO** (Ø de paso ISO 273 media, por el eje
  de la varilla, medido con un rayo OCCT desde el pasador alejándose de la cadena) y pone tuerca +
  contratuerca. Si el rayo no encuentra material (un agujero viejo en ese eje) o el pasador queda
  muy cerca de la placa, error que dice cuánto mover.
- **D8 — Uniones declaradas, nunca contacto en el amarre**: `{id}_pasador_a|b` = perno cadena ↔
  ancla; `{id}_amarre_a|b` = perno ancla ↔ pieza (size de la varilla, qty 1); `{id}_p1…` =
  contacto cadena ↔ cada piñón (como `create_chain`: la cadena apoya en él). Ancla y tuercas
  cuelgan de su pieza con juntas `fija` `{id}_jf_…` (la FK sólo mueve hijos declarados).
- **D9 — En pose la FK REHACE la cadena** (`robotics/pose_izaje.py`, llamado al final de
  `posed_shapes`): desde los pasadores de las anclas posadas, mismo N; el ramal que se mueve se
  mueve y el largo se conserva. El efecto poligonal deja unas centésimas entre el último rodillo
  y el ancla B: se cierran en el último tramo recto (≤ 1 mm; más es un aviso: la pieza se mueve
  fuera de los ramales). Los piñones FIJOS ruedan con la cadena (giran lo que corrieron sus
  rodillos asentados, módulo un diente); uno que la FK ya mueve no se toca. En pose la cadena
  va en piezas sueltas (`unir=False`, ~10× más barato); en el diseño, UN sólido.
- **D10 — Clave `izaje|ref|N|sentido|A|B|piñones`** (`izaje_geom.clave`): dos cadenas con los
  mismos números en su marco (las dos de un elevador) comparten la geometría, y la FK rehace la
  pose desde la clave sola, sin campos nuevos en `Feature` (sin bump de `GEOM_CACHE_EPOCH`).
- **D11 — Comando nuevo en v1, sin tool MCP nueva** (`run_command` lo cubre), con pista y su
  contrato en `test_contrato_comandos`. La huella D11 sólo ve el executor: cambiar la geometría
  de `library/izaje*.py` con los mismos params es subir su `version` a mano.
- **D12 — Validar TODO antes de mutar**: una carga tolerante suprime el comando entero; si el
  executor hubiera puesto la cadena y fallado en el ancla, quedaba media cadena en la escena (lo
  mostró la primera verificación sobre el elevador).
- **D13 — FS ≥ 7 sobre la rotura mínima de la ficha, de iwis** (fabricante, leído: abajo en la
  bitácora). Ninguna norma de máquina con la cifra es de lectura pública: EN 1570-1, ANSI MH29.1
  y ASME B20.1 son de pago, y la guía de aplicación de la MHIA para elevadores de material
  (la que acompaña a la B20.1) no da factor para la cadena. El mismo 7 lo pide el Código de
  California (Title 8 § 3093.53) al medio de suspensión de un elevador de acceso especial: se
  cita como coincidencia, no como norma aplicable.
- **D14 — Carga desigual entre cadenas con el Ku de Tsubaki** (tabla 4.3: 2 cadenas 0,6; 4 cadenas
  0,36); una n que la tabla no trae toma la de la n tabulada inmediata inferior (mayor:
  conservador). El impacto de arranque y frenado (el K de Tsubaki, que pide la inercia del motor)
  no se calcula: se declara en las hipótesis.
- **D15 — Lo que cuelga = el cuerpo móvil de la pieza de amarre** (se sube por las `fija` hasta la
  primera junta que mueve y se suma su hijo con todo lo que cuelga de él por juntas: lo que la FK
  mueve junto) + la carga útil `carga_kg` + el peso propio de la cadena ENTERA (conservador). Sin
  junta que mueva, el grafo de conectividad sin las cadenas de izaje: si lo unido a la pieza toca
  tierra, AVISO sin cifra. Con dos cuerpos en una cadena (contrapeso) manda el extremo más cargado
  y la carga útil se suma a los dos (conservador).
- **D16 — El pasador lo dimensiona la regla, por vínculo explícito**: la cadena es la pieza con
  `mesh_key` «izaje|», y sus pasadores, las uniones `{id}_pasador_a|b` con el `command_id` de esa
  pieza y `a` = la cadena (más su `{id}_amarre_a|b` hacia la pieza). Sólo una regla que CALCULÓ el
  FS saca sus pasadores de «sin dimensionar»; si no corrió o no pudo determinar la carga, siguen
  ahí. La regla va en `vida.reglas` (ningún ítem nuevo ni cambio del registro: sin bump de
  `VERSION_REGISTRO`; la batería de entrega no lee reglas de ingeniería: sin bump de
  `VERSION_BATERIA`).

## Alternativas descartadas

- **Un `insert_component` de cadena recta que «siga» a la junta con un `fasten`**: un tramo
  recto no envuelve el piñón ni conserva el largo; es exactamente lo que falló.
- **Hacer la cadena hija de la junta de la plataforma**: un cuerpo rígido; el ramal de retorno
  bajaría con la plataforma en vez de subir.
- **Aleta K1/K2 en F1**: sus cotas (altura de la aleta, agujero) son de FABRICANTE, no de ISO
  606 ni de ANSI B29.1; sin fuente leída en esta fase. Además no da ajuste: con dos cadenas hay
  que igualarlas, y eso lo da la varilla roscada. Va a F2 con su fuente.
- **El ancla de catálogo con largo de varilla fijo**: la varilla depende del espesor de la placa
  y del ajuste; una ref por largo multiplicaría el catálogo sin dato de mercado.

## Fases

**F1 — Geometría, uniones y que siga a la junta** (`library`, `commands`, `robotics` · M · hecha):
`library/izaje.py` (matemática pura), `library/izaje_geom.py` (cadena, ancla, clave),
`commands/models_izaje.py` + `exec_izaje.py`, `robotics/pose_izaje.py` + el gancho en
`pose.py`, pista y contrato. Se verifica con `tests/test_cadena_izaje.py` y en una copia en
memoria del elevador.

**F2 — Regla de capacidad y aleta** (`library/engineering`, `services` · M · depende de F1):
tensión por cadena = carga ÷ cadenas con su factor (criterio con FUENTE leída: norma de mesas
elevadoras / elevadores de carga, jamás inventada) contra la rotura del catálogo; abrazamiento y
z mínimos como la regla de `create_chain`; `amarre: aleta_k1|aleta_k2` con cotas de fabricante
declaradas en `no_publicado`. Partida en **F2a** (la regla de capacidad y el pasador dimensionado
por ella; decisiones D13–D16) y **F2b** (la aleta K1/K2; abrazamiento y z mínimos).

**F3 — La cadena viva** (`cosim`, `physics`, `ui` · L · depende de F1): la cadena como tendón
en la co-simulación (lo que la plataforma cuelga de ella), la cadena floja como efecto físico
(el interruptor de cadena floja del elevador), el giro del motriz acoplado a la plataforma en el
estudio de movimiento y la cadena en el visor (la FK del visor es del cliente y mueve cuerpos
rígidos: hoy la cadena de izaje queda en su pose de diseño ahí).

## Lo que este plan NO hace

- No cambia `create_chain` ni su `mesh_key`: los lazos cerrados regeneran idénticos.
- No hace cadenas dobles, en serpentina ni sobre la hilera 2 de un piñón doble-simple.
- No modela el resorte de cadena floja ni la leva del interruptor: siguen siendo piezas del
  modelo (F3 hace el efecto).
- No anima la cadena de izaje en el visor ni en el GIF de la UI (F3); sí en el servidor.

## Riesgos

| riesgo | mitigación |
|---|---|
| Cadenas de ~330 pasos: fundir cuesta ~4,5 s | Una vez por clave (las dos cadenas iguales comparten) y la caché de geometría; en pose, piezas sueltas (0,4 s) y memo por números |
| Un piñón que la FK mueve (eje con junta) y la cadena que lo envuelve | Ese piñón no se gira en la pose; acoplar motriz ↔ plataforma es F3 |
| La placa ya trae un agujero en el eje de la varilla (modelos a mano) | Error accionable que lo dice; la verificación del elevador quitó los 12 taladros viejos |
| La tuerca apoyada en la placa da astillas de volumen común (0,17 mm³) | Es herraje (`HARDWARE_CATS`): la puerta no la cuenta; se anota |

## Bitácora

### F1 (2026-10-27): implementada en su rama

- Archivos: `library/izaje.py`, `library/izaje_geom.py`, `commands/models_izaje.py`,
  `commands/exec_izaje.py`, `robotics/pose_izaje.py` (+ 5 líneas en `pose.py`), pista,
  registro y `tests/test_cadena_izaje.py` (8 tests). `create_chain` sin tocar.
- **Lo que corrigieron los intentos**:
  - Salir del piñón por el último asiento ANTES del punto de salida de la tangente metía un
    rodillo 2,3 mm dentro del círculo de paso (la sagita de casi un diente). El criterio bueno es
    el del casco convexo: se sigue asentando mientras el asiento siguiente quede afuera de la
    recta al objetivo.
  - El signo de ese criterio se probó al revés primero (sólo asentaba un rodillo): afuera es la
    derecha si la cadena gira antihorario, la izquierda si horario, no «del lado opuesto al
    centro» (con 180° de abrazamiento todo el arco está del lado del centro).
  - En pose el último rodillo quedaba a ±0,07 mm del ancla B (efecto poligonal: cada piñón se
    lleva un largo que depende de la fase) y rozaba el agujero del pasador (0,03 mm³): se cierra
    en el último tramo (D9).
  - En pose los rodillos corridos chocaban con los dientes quietos (160–1660 mm³ contra cada
    piñón, declarados como contacto): los piñones fijos ahora ruedan con la cadena.
  - La primera corrida sobre el elevador dejó la cadena SIN anclas: el executor creaba la
    cadena y después fallaba el rayo (la placa del modelo a mano tenía un Ø22 en el eje), y la
    carga tolerante no deshace lo ya puesto (D12).
- **Elevador con el comando nuevo** (copia en memoria de `C:\t\maq\elevador-vertical-cajas-2n`,
  proyecto 1, sólo lectura): se quitaron 84 comandos del amarre a mano (6 tramos rectos, 4
  horquillas, 4 pasadores, 16 pernos/resortes/tuercas, 4 taladros sobre ellos y 50 uniones,
  juntas y taladros que los nombran, entre ellos el artefacto c541) más los 12 taladros viejos de las placas c29/c331, y se agregaron 2
  `create_hoist_chain` ([c33, c38] y [c326, c327], amarre A en c29, B en c331, pasadores donde
  los tenía el modelador).
  - Regenera sin suprimidos (18–36 s el modelo entero, según la carga de la PC). Cada cadena:
    331 eslabones, 4203,7 mm (antes, tres tramos sueltos), las dos con la MISMA geometría; ancla
    A M8×50 con 18 mm de ajuste, ancla B M8×55 con 25 mm (la cadena queda 20,9 mm corta de la B
    nominal: la toma el ancla); 8 asientos en cada piñón.
  - Uniones: pasador y varilla son `perno` (M8 la varilla), contacto sólo cadena ↔ piñón.
  - Choques cadena/anclas contra todo el modelo en 0, 750, 1500 y 1580 mm: CERO salvo la
    astilla de 0,17 mm³ tuerca B ↔ placa c331 (herraje). El artefacto «contacto» c541 ya no hace
    falta: el pasador inferior a +1500 no encuentra el ramal superior porque el ramal superior
    se acortó.
  - `posed_shapes` a 1500 mm: 0,59 s (0,09 s la segunda vez, memo). Puerta de entrega:
    interferencias OK y poses declaradas OK; sus dos hallazgos que nombran las cadenas son de la
    verificación (ids `c9001` inyectados a mano por encima de `_seq` y el `layout_tablero` que
    quedó antes de ellas en el log), no del comando.
  - BOM: «Cadena BS 08B-1 L=4203.7 mm (331 eslabones)» × 2 y las 4 anclas como piezas a medida.

### F2a (2026-10-27): implementada en su rama

- Archivos: `library/engineering/izaje_capacidad.py` (la regla, pura), `services/izaje_rules.py`
  (lo que cuelga de cada cadena y los pasadores verificados), el gancho en
  `services/engineering_rules.structure_rules` (corre ANTES del chequeo estructural) y el
  parámetro `uniones_verificadas` de `report.structure_engineering_check` →
  `report_uniones._fastener_checks`. Tests: `tests/test_cadena_izaje_capacidad.py` (6).
- **Fuentes leídas** (D13, D14):
  - iwis, «Tensile Testing»
    (https://www.iwis.com/en-en/expertise-technology/testing-analysis/drive-systems-testing/tensile-strength):
    «as a rule of thumb, it is recommended to calculate with a safety factor of 7 based on the
    breaking force» → FS 7.
  - CCR Title 8 § 3093.53 (https://dir.ca.gov/Title8/3093_53.html): «The factor of safety of the
    suspension means shall be not less than 7 based on the manufacturer's rated breaking
    strength» (elevador de acceso especial; para una cadena de rodillos como medio de
    accionamiento con cables, 8). Coincidencia, no norma aplicable a un elevador de material.
  - U.S. Tsubaki, «The Complete Guide to Chain» (https://www.ustsubaki.com/pdf/the-complete-guide.pdf),
    pág. 36, tabla 4.3: Ku = 0,6 con 2 cadenas y 0,36 con 4 («When you use two or four chains in a
    hanging application or shuttle traction setup, the tension of each chain is not equal»). Su
    selección de cadena colgante compara contra la «carga máxima admisible» de su catálogo, no
    contra la rotura con un FS: por eso el FS sale de iwis.
  - Revisadas sin la cifra: la tabla de Tsubaki para cadenas de hojas AL/BL (FS 12 y 9: es para
    cadena de hojas, no de rodillos), la guía de aplicación de VRC de la MHIA (2004, la que
    acompaña a la ASME B20.1: no trae factor de la cadena) y los resúmenes públicos de EN 1570-1.
    PDFs en `C:\t\normas` (`tsubaki-complete-guide-to-chain.pdf`, `tsubaki-ca-selection-1.pdf`,
    `vrc-guidelines-cisco-eagle.pdf`).
- **Medido**:
  - Fixture de `test_cadena_izaje` (una cadena 08B-1, plataforma de 31,9 kg con sus placas,
    anclas y tuercas): T = 31,9·9,81·1 + 1,66·9,81 = 329 N → FS 54,1, ok. Con 300 kg de carga
    útil: T = 3 272 N → FS 5,4, error.
  - Copia del elevador (`elevador-vertical-cajas-2n-cadenas2.apolo`, 314 piezas, carga_kg 50, dos
    cadenas c793/c794): cuerpo móvil «Placa respaldo plataforma» 70,1 kg, T = (70,1 + 50)·9,81·0,6
    + 2,88·9,81 = 735 N → FS 24,2, ok en las dos. Los 4 pasadores salen verificados y la regla
    «uniones apernadas sin dimensionar» desaparece: era la FALLA de `union.dimensionadas`.
