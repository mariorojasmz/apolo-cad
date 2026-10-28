---
estado: en curso
nota: contrato escrito por Claude (2026-10-27, decisiones delegadas por Mario, vetables por número); F0 hecha (mapa del código, abajo); F1 mergeada (registro v16, D1/D2/D6); F2 implementada (registro v17, D3/D4), falta revisarla y mergearla; faltan F3 (aviso del tirador), F4 (las máquinas por MCP: el elevador da 5 resguardos sin lengüeta, 3 son finales de carrera con ref de resguardo) y F5 (Mario las ve)
descripcion: Lo que se mueve en la realidad se mueve en el modelo: la puerta rechaza la cadena hecha a mano, la unión falsa que tapa un choque y el resguardo sin junta, y en el visor «Puerta abierta» abre la puerta
---

# Lo que se mueve en la máquina también se mueve en el modelo, y la puerta lo verifica

## Estado y origen

Mario, mirando el elevador vertical de la tanda nocturna en el visor (2026-10-27):

- sobre las cadenas: «es un problema que puede suceder en el futuro?, es algo que te puedes
  olvidar colocar bien en otras maquinas?, o se puede validar con codigo deteminista?»;
- sobre la puerta de carga: «oculte la puerta para ver por dentro, ya que la puerta como se
  abre?, entendi que son los botones del panel mando de pero, al darle no pasaba nada, es
  normal?»;
- y el porqué: «cuando afinemos y este seguro, te voy a mandar a crear varias maquinas y no
  tendre el tiempo de revisar a detalle cada uno».

Y una condición: «recuerda no llegar a sobrediseño». Las decisiones se delegan a Claude
(«procede según tus criterios»): quedan escritas y vetables por número.

## El problema (lo que hay hoy)

Medido sobre el elevador aprobado con la puerta v15 (`C:\t\maq\elevador-vertical-cajas-2n`,
631 comandos):

1. **Cadena hecha a mano.** Cada cadena de izaje eran 3 tramos rectos de `CADENA-08B-1` por
   `insert_component` (c43–c45, c328–c330). No envolvían el piñón: el ramal superior terminaba
   25,4 mm por debajo del eje motriz. La puerta no lo vio, porque las cadenas sólo se cuentan
   cuando salen de `create_chain`:
   - `services/puerta_hechos.py:113-114`;
   - `services/calidad_tensores.py:162`;
   - `library/engineering/transmision_rules.py:46`.

   Una cadena por `insert_component` es invisible, y `transmision_flexible.tension` sale
   NO_APLICA por `aplica_si` (`library/calidad/registro.py:148-152`).
2. **Unión falsa que tapa un choque.** Los tramos no siguen a la junta `j_plataforma`. En la
   pose de +1500 mm la plataforma chocaba con ellos y el modelador declaró 3 `fasten contacto`
   (c541, c778, c779) que él mismo anotó como «ARTEFACTO DE REPRESENTACIÓN, no es unión física».
   Funcionan porque `exclusiones_declaradas` (`services/delivery_inputs.py:25-33`) saca de las
   interferencias el par de TODO `fasten`, de cualquier `kind`, también en las poses (:154).
3. **Resguardo sin junta.** Las puertas de carga c89 y c90 cuelgan de bisagras BIS-100 y las
   cierran -B11/-B12 (`RESG-2NC` con bloqueo), pero no tienen junta. Nadie verificó que abran
   sin chocar.
4. **El visor no muestra lo que hace el mando.** El panel Mandos manda
   `{"accion":"abrir","dispositivo":"-B11"}` (`ui/src/vivo/sesion.ts:184-197`). El modelo
   `Resguardo` de la co-simulación sólo cambia sus contactos
   (`core/apolo/cosim/modelos/seguridad.py:41-58`) y nada se mueve en el 3D: Mario apretó
   «Puerta abierta» y creyó que no pasaba nada. Sí pasaba: -T2 cortó la marcha y -S3 pidió
   rearme.
5. **Sin tirador.** Las puertas no tienen de dónde tomarlas, aunque el catálogo tiene tiradores
   (`library/data/101_tiradores.yaml`: TIR-96…192, POMO-25…35).
6. **Evidencia engañosa de `diseno.sin_sobrantes`.** En la faja de motor central, la puerta dijo
   que las capotas de los tambores (c70, c71, 10,3 kg) y las placas de transferencia (c423, c426,
   4,1 kg) sólo hacían falta como «apoyo» de otras guardas. Se quitaron, y las sondas llegaban
   igual a las cuñas: hubo que alargar las bandejas de retorno (+9,7 kg). El ahorro real fue de
   3,8 kg, no de 15. La causa: `Prueba.probar` (`services/calidad_sobrantes.py:267-288`) corta en
   «es un apoyo de» ANTES de correr las sondas, así que no dice si la candidata también tapa un
   peligro.

## Lo que se revisó antes de escribir esto (F0, mapa del código)

- **Ítem nuevo de la puerta.**
  - La forma es `Entrada(id, titulo, modo_de_falla, norma, familia, aplica_si, evaluar)`
    (`library/calidad/entrada.py:43-52`); el agregador `_de_entrada` está en
    `registro.py:315-328`.
  - Los insumos se arman en `services/puerta_publicacion.py:244-291` (`_reunir`), y los hechos
    en `services/puerta_hechos.py:98`.
  - El defecto sembrado va en `tests/test_defectos_sembrados.py`.
- **Qué mueve cada junta.**
  - La FK de `robotics/pose.py` (`feature_location` :51-82, `posed_shapes` :85-108) sube por
    `by_child` y no se propaga por los fijadores.
  - `enclavamientos.junta_movil(doc, fid)` (`services/enclavamientos.py:68-77`) devuelve la
    primera junta no `fija` de la cadena de `fid`: es lo que mueve a esa pieza.
  - `scan_collisions` (`robotics/motion.py:39-80`) no excluye pares con `fasten`, pero la puerta
    de entrega sí lo hace en sus poses (`services/assertions.py:182-251` + `delivery_inputs.py:154`).
- **De dónde sale una cadena.** `Feature` guarda `command_id`, `component` y `mesh_key`
  (`commands/escena.py:21-44`), pero no el tipo de comando. `create_chain` da `mesh_key`
  «cadena|…» y `create_hoist_chain` «izaje|…» (`exec_transmision.py:85-88`,
  `library/izaje_geom.py:52-53`). Un `insert_component` de CADENA-* tiene la misma ref: se
  distingue por el tipo del comando en `doc.commands` o por el prefijo de `mesh_key`.
- **Resguardo → hoja → junta.** No hay un vínculo directo, pero existe uno inferido:
  1. `device.pieza` (el interruptor);
  2. su lengüeta, por designación o cercanía (`enclavamientos.py:136-171`);
  3. `junta_movil(lengüeta)` (:99-107).

  Lo usa la F2b de [mandos-de-seguridad](mandos-de-seguridad.md) para verificar que la lengüeta
  entra en la ranura con el resguardo cerrado.
- **Visor.** Ya existe cómo mover una junta para mostrarla: `setJointValue` +
  `applyKinematicPoses` (`ui/src/state/store.ts:79-82`, `ui/src/viewport/poses.ts:61,103`), con
  precedente en `PanelTablero.tsx` (≈24-58, la puerta del tablero). Lo que falta es que
  `MandoVivo` (`ui/src/vivo/protocolo.ts:31-46`) traiga la junta del resguardo.

## Decisiones (para vetar)

Criterio común, contra el sobrediseño: **una regla es FALLA sólo si no agrega piezas** (exige
el comando correcto, una junta, quitar un parche) **o si una norma con fuente pide la pieza**.
Lo que pediría una pieza sin norma es AVISO justificable por escrito.

- **D1 — Toda cadena de rodillos sale de su comando.** Ítem nuevo
  `transmision_flexible.de_su_comando`, FALLA. Una feature con ref CADENA-* que no viene de
  `create_chain` ni de `create_hoist_chain` (tipo del comando en `doc.commands`) es una cadena
  hecha a mano: no envuelve sus piñones, no sigue a su junta y queda fuera del chequeo de
  tensión. No agrega piezas: cambia cómo se modela. **Las bandas quedan fuera de v1**: no hay
  ref de catálogo CORREA-*/BANDA-* que distinga un tramo hecho a mano (las bandas se detectan
  por rol, `calidad_tensores.py:116-131`) y no hay un caso medido.
- **D2 — En una pose, una unión no tapa el choque entre piezas que se mueven distinto.**
  `exclusiones_declaradas` sigue valiendo en la pose de reposo. En las demás poses, el par de un
  `fasten` cuyas dos piezas mueven juntas distintas (`junta_movil` distinto y alguna no `fija`)
  deja de excluirse.
  - Un contacto real a fin de carrera (un tope) se separa en las otras poses y no da choque.
  - Una unión «artefacto» deja ver el choque que tapaba, y falla el ítem de poses que ya
    existe.
  - Esto es mejor que una FALLA nueva por cada unión entre cuerpos móviles, que rechazaría el
    tope legítimo.
  - Los `fasten` que declaran los super-comandos de cadena (`{id}_p1`, `{id}_pasador_a`…) no
    cuentan: la cadena sigue a su pieza por la FK de izaje.
- **D3 — Un resguardo con interruptor abre su junta.**
  - Ítem nuevo `seguridad.resguardo_abre`, FALLA, para cada `add_device` con
    `modelo.tipo == resguardo`.
  - Hallar su junta por la cadena que ya existe (interruptor → lengüeta → `junta_movil`), sin
    param nuevo en `add_device`: una sola fuente, la que ya usa la F2b.
  - Sin junta (o con una `fija`) es FALLA, porque nadie puede verificar que abre.
  - Con junta, sus extremos `lower`/`upper` entran como poses de la verificación de
    interferencias, sin que el modelador los declare en `doc.motion`.

  Una junta no es una pieza: no hay sobrediseño. Un resguardo FIJO, que se quita con
  herramienta y no tiene interruptor, no entra.
- **D4 — En el visor, «Puerta abierta» abre la puerta.** El servidor resuelve la junta de cada
  resguardo (D3) y la manda en `MandoVivo` (`junta`, `abierto`, `cerrado`: los valores de
  `upper`/`lower`). Al accionar, la UI hace `setJointValue` como `PanelTablero`. Un resguardo sin
  junta muestra su estado como hoy (no inventa movimiento).
- **D5 — Tirador: AVISO justificable, no FALLA.**
  - Regla de la batería de entrega «resguardo sin tirador»: una hoja con junta (D3) que no tiene
    fijada una ref TIR-* o POMO-* (junta `fija` o `fasten`) da un AVISO.
  - Se levanta justificándolo por escrito: «se toma del borde plegado», «abre con llave».
  - No es FALLA porque no se encontró una norma que pida un tirador de catálogo, y un borde
    plegado basta. Antes de implementar, la F3 busca la fuente: ISO 14120 sobre la operación de
    los resguardos móviles.
- **D6 — La prueba de sobrantes dice la verdad de una guarda que también apoya.** En
  `Prueba.probar`, cuando la candidata es «apoyo de» otra, se corren igual las sondas sin ella,
  dejando en su lugar lo que apoya (como si se fijara a otra cosa: la pregunta de quien
  rediseña). Ajuste en la revisión de la F1: el agente quitaba también lo apoyado y eso daba
  `tambien_tapa` casi siempre, por el peligro que tapa la pieza apoyada. La evidencia agrega `tambien_tapa: <peligro>` o `solo_apoyo: true`. No cambia
  el estado del ítem: sólo la evidencia, que es lo que lee quien rediseña.
- **D7 — Versiones.** `VERSION_REGISTRO` 15 → 16 (D1, D2) y 16 → 17 (D3); `VERSION_BATERIA` 5 → 6
  (las poses de cada resguardo, D3) y 6 → 7 (D5),
  cada una con su línea. D6 no cambia veredictos.

## Alternativas descartadas

- **Param `junta` nuevo en `add_device`**: duplicaría la cadena interruptor → lengüeta → junta
  que la F2b ya usa, y dos fuentes divergen. Si la inferencia falla en una máquina real, se
  agrega como ajuste.
- **FALLA para toda unión entre cuerpos que se mueven distinto**: rechaza el tope legítimo de
  fin de carrera (D2 lo resuelve sin falso positivo).
- **Exigir un tirador de catálogo**: es sobrediseño sin norma (D5).
- **Regla «guarda que sólo sostiene otra guarda» (FALLA)**: la propuse a Mario y la medición de
  la faja la tumbó. La guarda «de apoyo» también tapaba accesos (problema 6), así que lo que
  hacía falta era corregir la evidencia (D6).

## Fases

- **F0 — Mapa del código** (sólo lectura). Hecha: § Lo que se revisó.
- **F1 — Cadena, uniones y evidencia** (`library/calidad`, `services`; S). D1, D2 y D6, con
  `VERSION_REGISTRO` 16.
  - Tests: un defecto sembrado por regla (cadena por `insert_component` → FALLA; unión
    «artefacto» → el choque aparece en la pose; tope legítimo → sin falso positivo; guarda de
    apoyo que tapa → `tambien_tapa`).
  - Re-congelar los testigos.
  - Gate: suite completa + ruff.
- **F2 — El resguardo abre** (`services`, `cosim`/protocolo, `ui/src/vivo`; M). Depende de F1
  sólo por la versión del registro.
  - D3, con sus poses, y D4, con la junta en `MandoVivo` y `setJointValue` al accionar.
  - Tests: resguardo sin junta → FALLA; con junta que choca a `upper` → FALLA; con junta libre →
    OK; vitest del mando que mueve la junta.
  - Gate: suite + `npm test` + `npm run build`.
- **F3 — Tirador** (`library/delivery*`; S). D5: primero la fuente normativa, después la regla
  con `VERSION_BATERIA` 6 y su defecto sembrado.
- **F4 — Las máquinas** (MCP, sin código). Primero el elevador: cadenas por `create_hoist_chain`
  (en curso), después las puertas con junta y tirador (brief escrito). Luego se pasan por la
  puerta v16 el tanque, la mezcladora y la faja. Cada vuelta con su costo y su tiempo.
- **F5 — Mario lo ve en el visor**: «Puerta abierta» abre la puerta, la cadena envuelve el
  piñón y sigue a la plataforma.

## Lo que este plan NO hace

- Bandas y correas hechas a mano (D1, fuera de v1).
- Animar en el visor la cadena que sigue a la plataforma: es la F3 de
  [cadena-de-izaje](cadena-de-izaje.md).
- Cambiar la plantilla `create_belt_conveyor` (backlog: las tapas que la norma no pide).

## Riesgos

- **Que la inferencia interruptor → lengüeta → junta falle en una máquina real** (un actuador
  que no es lengüeta, una corredera). Mitigación: la F2 la prueba en las 3 máquinas con tablero
  antes de mergear; si falla, ajuste con param explícito.
- **D2 hace aparecer choques en máquinas ya aprobadas.** Es lo buscado, pero puede revelar
  uniones legítimas mal declaradas. Mitigación: la F4 pasa las 4 máquinas y cada choque nuevo se
  lee antes de corregir.
- **Poses extra (D3) alargan la puerta.** Un resguardo suma 2 poses; se mide en la F2 contra los
  segundos de la puerta del elevador.

## Bitácora

- **F0 (2026-10-27):** mapa del código hecho por un agente de sólo lectura (≈ 9 min). Corrigió
  dos supuestos de la propuesta a Mario: el catálogo SÍ tiene tiradores, y no hay ref de catálogo
  para bandas.
- **Medición de D6 (2026-10-27):** en la faja de motor central se quitaron 16,5 kg de guardas
  «de apoyo» y hubo que agregar 12,6 kg para volver a tapar las cuñas. Neto: 280,5 → 276,7 kg y
  1251,93 → 1240,68 USD, con la puerta aprobada y la entrega en VERDE. La prueba «una a la vez»
  no ve que la capota también tapa.
- **F1 (2026-10-27, agente en worktree):** registro v16.
  - D1: `library/calidad/cadenas.py` (la `Entrada` y su criterio) + `services/calidad_cadenas.py`
    (detector: tipo del comando por `command_id`, con prefijo para los sintéticos, o `mesh_key`
    «cadena|»/«izaje|»). Las 14 cadenas del testigo `rodillos` (create_chain DENTRO de un
    compuesto) salen de su comando por el `mesh_key`.
  - D2: en `services/assertions._en_pose` (sólo la puerta de entrega en pose; el chequeo de
    diseño y `check_interference(excluir_declaradas)` no cambian). Además de `junta_movil`
    distinta, el par se libera sólo si la POSE mueve distinto sus cadenas de juntas: en un estudio
    de dos juntas, la pose que sólo mueve la otra deja el tope tocando como en diseño. Se excluyen
    el par padre-hijo de una junta y los `fasten` de un super-comando de cadena (por tipo o por el
    command_id de una pieza «cadena|»/«izaje|»).
  - D6: `services/calidad_sobrantes_apoyo.py`, etapa «apoyo» en `por_etapa`. Medido en el testigo
    faja con una placa colgada de la guarda de cola: sobrantes 35 275 / 36 030 ms sin D6 y
    36 928 / 36 380 ms con D6 (apoyo: 2 pruebas, 1 107 / 1 127 ms; corta en la primera recta que
    llega, ≈ 0,58 s). El caso caro es `solo_apoyo` (ninguna recta llega y corre el brazo doblado):
    7,4 s por candidata en la tapa del tensor. Sin apoyos (el testigo tal cual), 0 ms.
  - Testigos re-congelados sólo por la versión y el ítem nuevo (NO_APLICA en faja y ménsulas, OK
    en rodillos, que además estaba en v14).
- **Ajuste de D2 (2026-10-27, al pasar las 4 máquinas por v16):** la mezcladora dio un choque
  falso a 95°: las dos mitades de la bisagra de la tapa, unidas por su pasador, se tocan en todo el
  recorrido. Un par que ya se TOCA en la pose de diseño (≤ 0,05 mm) sigue excluido en las poses
  (`delivery_inputs._se_tocan`); la unión «artefacto» tapa un choque que en diseño no existe, y
  ésa sigue contando. Riesgo que queda: un artefacto entre piezas que ya se tocan en diseño.
- **F2 (2026-10-27, agente en worktree):** registro v17.
  - D3: `services/resguardos.py` es la única resolución (interruptor = `pieza` → lengüeta de
    `enclavamientos.emparejar` → `junta_movil` de la lengüeta o, si no tiene, la del interruptor;
    la misma junta para los dos = no abre). Ítem en `library/calidad/resguardos.py`; sus poses
    (`lower`/`upper` ≠ 0) entran en `assertions.delivery_poses` acotadas con `ids` a lo que mueve
    la junta (exacto: lo demás está como en diseño). CERRADO = 0 si está en el recorrido; ABIERTO
    = el extremo más lejano (los −180…180 por defecto de `add_joint` dan 180).
  - **Ajuste a la inferencia, medido en las 3 máquinas con tablero:** sin lengüeta emparejada no
    hay junta (`sin_lengueta`). En el elevador, -B13/-B14 (cadena floja, RESG-2NC sobre la
    plataforma) salían OK «abriendo» por `j_plataforma` a 1580 mm, y el visor habría subido la
    plataforma al tocar «Puerta abierta». Resultado: elevador 5 de 5 FALLA `sin_lengueta` (-B11/-B12
    son cajas «compra» con un actuador-caja, no las refs de catálogo; -B13/-B14/-B15 son finales de
    carrera con la ref de un resguardo: el catálogo no tiene interruptor de posición); mezcladora
    -B1 OK por `j_tapa_carga` (0 → 100), -B4 (recipiente) FALLA `sin_junta`; tanque -B1 OK por
    `j_tapa_boca` (0 → 105).
  - Segundos de las poses de la puerta de entrega: mezcladora 0,69 → 1,13 s (+1 pose, que choca
    en 2 pares: lo lee la F4), tanque 0,01 → 0,48 s (+1 pose, sin choques). En el elevador, una
    puerta hipotética (junta en c89) cuesta 0,77 s acotada contra 7,0 s global.
  - D4: `juntas_vivo` (bajo el lock de `_preparar`) + `juntas_en_tabla` (pura, en `_inicio`): el
    mando trae `junta`, `abierto`, `cerrado`. La UI (`ui/src/vivo/juntaResguardo.ts`) la mueve en
    `sesion.accionar` con `setJointValue`, sin animar (cada cambio de `jointValues` rearma el
    reproductor vivo), y la devuelve al cerrar o reabrir la sesión.
  - Testigos re-congelados sólo por la versión y el ítem nuevo (NO_APLICA en los cuatro).
- **Revisión de la F2 (2026-10-27):** el agente midió que el elevador usaba la ref RESG-2NC para
  sus finales de carrera (-B13/-B14 de cadena floja, -B15 de sobrecarrera): con D3 fallaban sin
  arreglo posible. Se agregó al catálogo el interruptor de POSICIÓN `FC-2NC-RODILLO` (mismos
  contactos y modelo de la co-simulación, `actuador: rodillo`, sin `specs.actuador`) y D3 aplica
  sólo al resguardo de actuador `separado`; sin resguardos así, el ítem no aplica. Las poses
  nuevas cambian la entrega: `VERSION_BATERIA` 5 → 6 (el tirador de D5 pasa a 7).
