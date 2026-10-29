---
estado: en curso
nota: F1 mergeada (2026-10-28; create_belt_conveyor v7, criterio 9; el motriz NMRV sobresale 222,6 mm contra 776,4 del coaxial); F2 primera corrida APROBADA con 12 puestos pero la familia 24/36 no regenera y la re-revisión marcó dos MEDIA de la plantilla; F1b (D7–D12, criterio 10) lanzada; después se repite F2
descripcion: La faja ofrece motorreductor sinfín de eje hueco calzado en el tambor (motor a lo largo del larguero) y tensor de placa ranurada, con la carrera del tensor calculada y el carro al inicio
---

# Faja compacta: motor pegado al larguero y tensor liviano

## Estado y origen

Mario, mirando la «Mesa de sorteo manual 12 puestos» en el visor (2026-10-28):
- «¿amerita tan grande el «Faja central · Tensor de carro (2)»?» — es un UCT205-150 (317 × 199 mm,
  4,8 kg) en una faja liviana.
- «¿se podría apegar el motor al larguero? … dale elegancia y optimiza el espacio si es que se
  puede».

Hoy `create_belt_conveyor` sólo sabe montar un motorreductor coaxial (helicoidal o de ejes
paralelos) sobre una base de dos brazos y una ménsula soldada a la pata, con acople y guarda de
acople (F1b D9 de [faja-larga-en-tramos](faja-larga-en-tramos.md)): sobresale ~450 mm del
larguero. El catálogo ya tiene la familia NMRV (`31_motorreductores_sinfin.yaml`, eje hueco de
salida con `bore_d`), que la plantilla no ofrece.

La re-revisión a ciegas de la clasificadora (MEDIA) además midió en el tensor 75 mm de carrera
por lado con el carro CENTRADO, contra 103,5 mm que pide el 1 % de estiramiento de un lazo de
20,7 m más 20 mm de montaje.

## Decisiones (para vetar)

- **D1. Motorreductor de eje hueco en el tambor motriz** (`motor` acepta las refs NMRV): el
  reductor se calza en el extremo del eje motriz (eje vivo sobre sus dos chumaceras, como hoy)
  con chaveta; el motor queda **acostado a lo largo del larguero, hacia la cola**, por fuera del
  larguero y bajo el nivel de la banda; el par lo toma un **brazo de reacción** atornillado al
  larguero con buje elástico, anclaje desfasado del eje (criterio de la raíz: «Anti-giro de un
  shaft-mount»). Sin acople, base, brazos, ménsula ni guarda de acople. El extremo libre del eje
  hueco lleva su tapa. Va del lado opuesto a `lado_abierto` (con «ninguno», +Y como hoy).
- **D2. Calce y cuenta**: el `bore_d` del NMRV tiene que ser el `shaft_d` del tambor motriz; si
  no, error que nombra los NMRV que calzan. La relación sale de la velocidad de banda pedida (la
  relación de catálogo más cercana) y la cuenta de `rules_faja_motor` (η = 0,75 sinfín, ya
  reconocida) decide si el tamaño alcanza: si no, error con el tamaño siguiente. La plantilla no
  elige el tamaño sola: lo pide el modelador y la cuenta lo juzga.
- **D3. Tensor de placa ranurada** (`tensor: "placa-ranurada"`, opción por función para fajas
  livianas): chumacera de BRIDA de catálogo del Ø del eje de cola, apernada por ranuras a una
  placa soldada al larguero, y un perno empujador con contratuerca en una oreja soldada. El UCT
  queda para fajas cargadas. Sin pieza inventada: la placa y la oreja son chapa de la plantilla;
  chumacera, pernos y tuercas, de catálogo.
- **D4. Carrera calculada y carro al inicio**, para los dos tensores: carrera necesaria = 1 % del
  lazo + 20 mm de montaje (criterio de diseño; el 1 % es el estiramiento de servicio de una banda
  de tejido, a citar por F1 con su fuente o, sin ella, declarado como criterio). El tensor se
  elige con carrera ≥ esa (placa: la ranura se dimensiona; UCT: el de carrera suficiente, si no
  error) y el carro sale **al inicio de la carrera** (banda recién montada), no centrado.
- **D5. Criterio 9** (sello de entrada, `exec_faja.sellar`): D4 se aplica sólo a faja nueva; un
  log viejo (criterio ≤ 8) regenera igual. D1 y D3 son valores nuevos de `motor`/`tensor`: un log
  viejo no los trae. Sube la `version` de `create_belt_conveyor`.
- **D6. Todo pasa la puerta nueva**: las piezas nuevas declaran sus uniones y salen con
  `union.contacto_real` en OK (plan [uniones-que-tocan](uniones-que-tocan.md)), sondas ISO 13857
  y acceso de herramienta en verde. El test mide cuánto sobresale el conjunto motriz del larguero
  (meta: ≤ 200 mm, del orden de 150) y lo compara con el coaxial.

## Alternativas descartadas

- **Motor vertical bajo la cama** (sinfín con el motor hacia abajo): libera el costado pero choca
  con el retorno y obliga a subir la altura mínima de trabajo.
- **Elegir el NMRV solo**: el modelador elige y la cuenta juzga, como con los demás motores; una
  plantilla que cambia el motor sin que se lo pidan esconde el costo.

## Fases

- **F1 — plantilla (núcleo, M)**: D1–D6 con tests (NMRV-063 en el TAMBOR-102 de una faja de 4 m y
  de 12 m en dos tramos; calce que no coincide da error; tensor de placa con la ranura de la
  carrera calculada; UCT con el carro al inicio; un log v8 regenera igual; la puerta de cada
  variante sin FALLA nueva).
- **F2 — la mesa de sorteo (MCP, S)**: la «Mesa de sorteo manual 12 puestos» con NMRV y tensor de
  placa, revisada a ciegas y por la puerta. Hecha la primera corrida (2026-10-28): APROBADA con 12
  puestos, pero la familia (24/36) no regenera y la re-revisión marcó dos MEDIA de la plantilla →
  F1b.
- **F1b — lo que la familia y la re-revisión destaparon (núcleo, M)**, decisiones D7–D12 de abajo,
  con tests en una faja de 30 m (la de 36 puestos) y la de 10 m en dos tramos; después se repite F2.

## Ajuste F1b (2026-10-28, contrato; vetable por número)

Lo que salió de la F2: a 24 y 36 puestos la faja no regenera, y la re-revisión a ciegas marcó dos
MEDIA que vienen de la plantilla, no de la máquina.

- **D7. La plantilla no rechaza un motor por una carga que no conoce.** La cuenta del NMRV de F1
  usa 50 kg/m (la carga de diseño de la cama): en la mesa son ~14 kg/m reales (3,6×), pide 1,1 kW
  contra 0,25 kW de `engineering_check` y deja sin motor a 36 puestos. La plantilla elige la
  relación por la velocidad y sólo rechaza lo GEOMÉTRICO (el calce); la potencia la juzga la regla
  de la puerta con los requisitos reales (`rules_faja_motor`, que ya lo hace). Si no hay requisitos
  de carga, aviso con la carga supuesta, no error.
- **D8. La ranura del tensor de placa se dimensiona con la carrera que pida el lazo**, sin el tope
  de 165 mm, hasta lo que deje la geometría de la cola (el tope geométrico, medido y escrito); más
  allá, error que lo dice. Así entra un lazo de 59 m (306 mm) sin una toma de tensión que el
  catálogo no tiene.
- **D9. La vida L10 lee las rpm de la relación que eligió la plantilla** (hoy sale «sin evaluar»
  hasta que el modelador declara `rpm_salida` a mano), y el lazo se calcula con el mismo radio que
  la simulación (hoy 56,8 contra 60,8 mm: 7 % en la velocidad).
- **D10. η del sinfín por relación**, de la ficha del fabricante si el repo o `C:\t\normas` la
  tienen con fuente; si no, se queda en 0,75 declarado como criterio de diseño (no se inventa).
- **D11. Cada tramo del bastidor se sostiene solo** (re-revisión, MEDIA): hoy la punta de empalme
  de un tramo cuelga 2,5 m de 3 M12 a cortante; al desarmar vuelca sobre el montador. Una estación
  de patas a cada lado del empalme (o una por tramo que lo deje estable solo), con la cuenta de
  vuelco del tramo suelto.
- **D12. La banda se cambia sin desarmar la cama** (re-revisión, MEDIA; `consumibles.reemplazables`
  no lo vio): si algo atraviesa el lazo (soportes de cama, cama, retorno), la plantilla declara un
  **empalme de campo** (grapa mecánica de catálogo, en la BOM) y la regla de la puerta reconoce un
  lazo con empalme de campo como reemplazable; un lazo sin fin atravesado, sin empalme, es FALLA.
  Solo con `criterio: 10` (el sello lo pone a toda faja nueva; un log ≤ 9 regenera igual).

## Lo que este plan NO hace

- Motor en la cola ni tambor motorizado (motor dentro del tambor): son otros montajes.
- El voladizo de 342 mm de la cola y el techo de la guarda de cola (los otros dos MEDIA de la
  re-revisión): quedan vetables, fuera de esta fase.

## Riesgos

- **Guardas**: el motor a lo largo del larguero puede tapar el acceso a los pernos del larguero o
  quedar en el camino de una sonda; D6 lo mide.
- **Par de arranque en el brazo de reacción**: la cuenta lo dimensiona con el arranque directo
  (2 × nominal, el mismo criterio que la base de hoy).

## Bitácora

### F1 (2026-10-28)

Implementada en la rama del agente (worktree), sin mergear. `create_belt_conveyor` v7, sello en
criterio 9. Módulos nuevos por responsabilidad: `belt_conveyor_carrera.py` (D4), `belt_conveyor_placa.py`
(D3), `belt_conveyor_nmrv.py` (D1, geometría) y `belt_conveyor_nmrv_cuenta.py` (D2, puro). Tests:
`tests/test_belt_conveyor_compacta.py`.

**Decisiones del agente (vetables, por número):**

- **F1-1 (D2) `velocidad` VISIBLE** (m/s, vacío por defecto: un log viejo y el coaxial no la leen).
  El NMRV la exige: sin ella, error que la pide. La relación es la de la serie de catálogo NMRV
  (7,5…100, nueva `specs.relaciones_i` del YAML, mismo catálogo Motovario; sin geometría) cuya
  velocidad de banda queda más cerca de la pedida, con el `n_rpm` de la placa del motor y el Ø
  EXTERIOR del tambor (engomado).
- **F1-2 (D2) La carga de la cuenta** es la de diseño de la cama (50 kg/m, `belt_conveyor_cama`;
  criterio de diseño ya publicado): la plantilla no recibe la del encargo. η = 0,75 del sinfín (la de
  `rules_enriquecer`), margen 1,3 (`POWER_MARGIN`), CEMA slider-bed μ = 0,33. Si no alcanza: error
  con el NMRV siguiente que calza (o el que alcanza y no calza, y qué hacer).
- **F1-3 (D1) Calce por chaveta**: el barreno del builder `worm_gearmotor` tiene 1,5 mm de huelgo
  radial (no toca el eje: `union.contacto_real` lo daba «separadas»). La plantilla modela la chaveta
  DIN 6885 A (b de la ficha, h y t1 de la norma) fundida al eje motriz y corta el chavetero de la
  ficha (`chavetero_t`) en el cubo del reductor: el reductor arrastra el eje por la chaveta y la
  unión `motor_eje` (contacto) se toca. El builder no se tocó.
- **F1-4 (D1) La tapa del eje hueco** es la del builder (la tapa NMRV de su lado exterior, maciza):
  el eje entra hasta 3 mm antes de ella. Sin pieza nueva.
- **F1-5 (D1) Brazo de reacción a la PATA de cabeza**, no al larguero: bajo el eje el larguero
  tiene ~40 mm de canto libre y la placa porta-chumacera lo ocupa; la pata (soldada al larguero en
  ese punto) da un brazo de 150 mm. Chapa de 8 mm sobre los 6 pernos de la brida del reductor
  (M8x20 a sus roscas: 1,5·d en fundición), perno M12 por un buje elástico Ø20 a la rosca de un
  soporte de barra Ø40 soldado a la pata. Cuenta (4 m, NMRV-063, i = 20): par de arranque 184 N·m
  (2 × nominal, el criterio de la base del coaxial), 1,23 kN en el anclaje, σ del brazo 35,5 ≤ 150
  MPa, τ del cordón 19,1 ≤ 144,6 MPa, corte del perno 1,2 ≤ 32,4 kN.
- **F1-6 (D1) Costado −Y** (operarios a +Y): el reductor es el ESPEJO del builder (motor del otro
  lado del sinfín: la posición de montaje se pide al comprarlo); la brida siempre al larguero y el
  motor siempre hacia la cola. El coaxial sigue a +Y (como desde la v4).
- **F1-7 (D1) La caja de bornes** del builder queda 20 mm sobre la cara de la banda (el cuerpo del
  motor, 18 mm por debajo): se pide lateral al comprar; el builder no se tocó.
- **F1-8 (D3) La placa CORRE sobre espárragos**, no va soldada: D3 decía «apernada por ranuras a una
  placa soldada al larguero», pero el larguero es un tubo cerrado y la tuerca de un perno que pasa
  por la ranura de una placa soldada quedaría dentro del tubo o apretada contra él (lo que la F1c
  sacó de toda la plantilla). La placa ranurada (20 mm) lleva la UCF a rosca (M10x25, enganche 11
  mm, la punta no la pasa), dos ranuras del lado de la cabeza por donde pasan dos espárragos
  M10x35 ISO 13918 soldados al larguero (tuerca por fuera) y tapa la ranura del eje del larguero en
  toda la carrera. El perno empujador (M12, a rosca en una oreja de 16 mm soldada al larguero, con
  contratuerca) va DECLARADO en su unión, como el resto de la tornillería de la plantilla: modelado,
  la puerta lo leía como un perno que tiene que enroscar en la placa que empuja (FALLA de rosca en
  barra) y le probaba la llave contra la cara del larguero (FALLA de acceso). Carrera máxima de la
  placa: 165 mm (el perno de catálogo de 200).
- **F1-9 (D4) La fuente del 1 %** es la que ya cita la puerta (`calidad/tensor.py`: estiramiento de
  servicio de una banda de PVC de 2 capas 0,5–1 %, CEMA y fabricantes), y la cuenta ES la del
  control `tensor.carrera` (`carrera_requerida`): «1 % del lazo + 20 mm» es lo que el tensor tiene
  que RECUPERAR de lazo; la carrera del tensor es eso entre el factor del tambor de cola (cos θ₁ +
  cos θ₂ ≈ 2). Medido: lazo de 4 m = 8351 mm → 103,5 mm de lazo → 51,8 mm de tensor (la placa
  sale con 55; la UCT205-150 sobra). El «103,5» del contrato coincide con el de la faja de 4 m; la
  mesa de sorteo (lazo 20,7 m) pide 227 mm de lazo = 113,5 mm de tensor, dentro de la UCT205-150
  con el carro al inicio (centrado sólo daba 75).
- **F1-10 (D4) El carro al inicio sin tocar el catálogo**: el builder `take_up_unit` recibe
  `avance` (0 = la geometría de siempre, el test congela su volumen) que corre el MARCO; su origen
  sigue en el agujero del soporte (el eje del tambor). `calidad_tensores_lazo._centro` lee ese
  origen en una UCT instanciada (la caja ya no está centrada en el tambor). `Cotas.x_tc` es el
  centro de la carrera (−half hasta el criterio 8): la ranura del larguero, el marco, la placa
  porta-tensor, la guarda de cola y la punta de la cama se miden desde ahí.
- **F1-11 (D4) UCT que no alcanza**: error que dice cuánto pide el lazo y sugiere la placa ranurada
  (si entra en sus 165 mm) o acortar la faja (14 m: 151,8 > 150 → la placa da 155).
- **F1-12 (D3) La puerta reconoce la placa ranurada**: `services/calidad_tensores` suma un tensor
  «plantilla» por placa (la carrera, de las cotas del comando, como `_plantilla_motriz`; eje X;
  centro = la chumacera). El perno empujador no se mide (`tensor.agarre` NO_APLICA).
- **F1-13 (D6) Dos defectos latentes que la puerta destapó al cambiar la envolvente** (corregidos
  sólo con el criterio 9; lo sellado antes regenera igual):
  (a) con la guarda inferior cortada en el soporte del rodillo de retorno, entre el fondo de la
  guarda del rodillo y el ala de la guarda inferior quedaba un paso (< 10 mm, sr 11 mm < 80) al
  extremo del rodillo: la FALLA sale ya con el criterio 8 en una faja sin motor (el coaxial la
  tapaba por la envolvente de sus sondas). Ahora las paredes de la guarda del rodillo siguen,
  fuera del ancho de la banda, hasta su mejilla y suben hasta el ala de la guarda inferior.
  (b) con el carro de la UCT al inicio, la ventana de su marco dejaba ver la ranura del larguero
  (31 mm: un brazo según ISO 13857 tabla 4) en toda la carrera de ficha, y una sonda con el brazo
  doblado llegaba por ahí a la cuña de cola (NMRV a −Y, operarios a +Y). Con el carro centrado el
  soporte tapaba el medio (quedaban dos ventanas de 22 mm sobre la ranura). Ahora la ranura del
  larguero y de la placa porta-tensor se corta con la carrera que pide el lazo (55 mm en la de 4
  m), no con los 150 de ficha: el soporte del carro la tapa entera hasta 56 mm de carrera. Lo que
  la UCT trae de más no se usa (vetable: en una faja larga con la UCT, la ranura vuelve a asomar
  por la ventana; ahí la placa ranurada, que tapa la suya en toda la carrera, es la del lado de los
  operarios).

**Medido:**

- **Cuánto sobresale el conjunto motriz** de la cara exterior del larguero (escena, 4 m): NMRV-063
  **222,6 mm** contra **776,4 mm** del coaxial MOTOR-150-EH (acople, base y guarda): −71 %. La meta
  del plan (≤ 200, del orden de 150) NO se cumple con las dos chumaceras de D1: desde el larguero,
  placa porta-chumacera 12 + brida e inserto de la UCF 55 + 3 de huelgo + medio reductor del builder
  (63, brida de salida incluida) + medio motor IEC 90 (87,5). Sin la chumacera exterior (el
  reductor apoyado en sus rodamientos, brazo de reacción igual) bajaría a ~160: queda vetable para
  F2 o un plan propio (D1 pedía las dos).
- **Cuenta NMRV** (4 m, 0,5 m/s): i = 20 → 85,5 rpm → 0,509 m/s; F = 738 N; P = 0,65 kW ≤ 1,1 kW
  (FS 1,69). 12 m a 0,25 m/s: i = 40, 0,97 kW ≤ 1,1. NMRV-050 a 0,5 m/s en 4 m: error «usa el
  NMRV-063»; NMRV-090 (Ø35) en el TAMBOR-102: error «calzan NMRV-050, NMRV-063».
- **Lo sellado con el 8** regenera igual (piezas, uniones, volumen y notas medidos con el código de
  antes: 4 m, 12 m abierta a −y, sin tensor).
- **La puerta (D6)**, entera en proceso (gravedad y marcha reales), con los requisitos y las
  funciones del testigo de la faja y sin sus justificaciones: la faja del criterio 8 da una sola
  FALLA, `diseno.sin_sobrantes` (tapas y guardas que el testigo justifica). Con la F1 dan lo mismo,
  y ninguna pieza nueva sobra: criterio 9 por defecto (UCT), sin motor, NMRV-063 (UCT), NMRV con
  operarios a +y (motor a −Y), NMRV + placa ranurada, placa ranurada, coaxial con operarios a +y,
  y la de 12 m con NMRV-063 a 0,25 m/s y placa ranurada (155 mm). `union.contacto_real` OK en
  todas (113 uniones en la de NMRV + placa). Un test lo congela para NMRV + placa
  (`test_d6_la_puerta_del_nmrv_con_placa_sin_falla_nueva`, ~60 s).

**No cubierto en la F1**: la F2 (la mesa de sorteo por MCP); la meta de ≤ 200 mm (ver lo
medido); la carga del encargo en la cuenta del NMRV (F1-2); el agarre del perno empujador, que la
puerta no mide (declarado); la ranura de la UCT en una faja larga con el lado abierto (F1-13 b).
