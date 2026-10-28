---
estado: en curso
nota: F1 mergeada (2026-10-28, 16c2a9c; registro v19, create_brace con a_tope/boca_de_pescado/inglete, D1b el cordón medido dimensiona); falta F2 (la plataforma de mantenimiento corregida con create_brace, por MCP), medir la regla en la clasificadora de 480 piezas, y solapada/cartela
descripcion: Una unión declarada tiene que tocar de verdad: la puerta mide el contacto y el cordón, y un miembro inclinado sale cortado a ras de las caras que une
---

# Lo que se declara unido tiene que tocarse, y una riostra se corta a ras

## Estado y origen

Mario, mirando la «Plataforma de mantenimiento 1 m con escalera» en el visor (2026-10-28), con dos
fotos (el arriostre lateral y el pasamanos): «no se une de forma correcta, o me equivoco?, como
deberia unirse? … no solo quiero que se corrija, quiero que la fabrica se corrija para que no suceda
estas cosas, y no solo para esta maquina recuerda que varias pc van a fabricar estas maquinas».

La plataforma aprobó la puerta v17 (20 OK) y siete re-revisiones a ciegas; nadie lo vio.

## El problema

- `c77` «Arriostre lateral (+Y)» = `insert_component` TUBO-1X1 con `length: =Lab` y
  `rotation: {y: =ab}`: un tubo recto girado, con los extremos a escuadra. Medido: **ninguna
  pieza a menos de 3 mm** (`measure_distance` contra toda la escena). Igual en c78 y c79. Aun así,
  el modelo declara `S_arr_pY[0]` soldadura c77 ↔ c67 y `S_arr_pY[1]` c77 ↔ c69: soldaduras
  FANTASMA. El pasamanos de la escalera tiene lo mismo (el extremo pasa de largo del poste).
- La puerta y la entrega CREEN lo declarado: la conectividad, la sujeción, el dimensionado de
  la soldadura (`services/dimensionado.py` `_huella_mm`, por cajas) y `gravity_test` (que simula
  el grafo declarado) dan todo «sujeto». Ningún control mide que dos piezas soldadas se toquen,
  ni que el cordón tenga largo (en la tanda también salieron: la zanca en punta y el peldaño
  colgado de 5 mm, backlog 2026-10-28).
- Causa de modelado: no hay comando para un miembro inclinado ENTRE dos piezas; el modelador
  calcula a mano el largo y el giro de un tubo recto. `create_frame` trabaja por ejes (nodos) y
  corta a inglete o a tope EN EL NODO, no contra la cara de la pieza que recibe.

## Decisiones (para vetar)

- **D1. Regla `union.contacto_real` (FALLA)**: para cada `fasten` declarado,
  - `soldadura`: las dos piezas se tocan (distancia ≤ tolerancia de modelado) y la zona de contacto
    da un **largo de cordón** ≥ el mínimo (el mayor entre un mínimo absoluto y el que pide su
    garganta: EN 1993-1-8 §4.5.1 da 30 mm o 6·a como largo eficaz mínimo de un cordón de filete;
    F1 cita y usa la fuente). Un punto o una arista no es un cordón.
  - `contacto`/`pegado`: se tocan en un área (no un punto) salvo lo que gira (rodamiento, eje).
  - `perno`: las piezas que aprieta están a ≤ el largo de su tornillería (no hay un hueco de aire).
  La evidencia nombra el par, la distancia y el largo medido. Va en el registro (v19). Aplica a
  toda máquina: lo hace cumplir el mismo código en todas las PC.
- **D2. La entrega también**: `delivery_check` corre lo mismo (ROJO) para que el modelador lo vea
  ANTES de la puerta, con el mensaje que guía («usa `create_brace`», «corta el extremo a ras»).
- **D3. Comando `create_brace`** (super-comando, `commands` + `library`): un miembro de perfil de
  catálogo entre dos piezas `a` y `b` (con un punto sobre cada una, o un punto y una dirección), que
  corta cada extremo **a ras de la cara que recibe** (plano de la cara: tope a cara; con dos caras,
  el corte que asienta), conserva la ref de catálogo y deja en la BOM y la lista de corte el largo
  de corte y los ángulos de cada extremo; declara sus soldaduras (o pernos) con el largo de cordón
  medido. Paramétrico (expresiones) y editable. Sirve para riostras, diagonales, pasamanos que llegan
  a un poste y zancas.
- **D1b. Se valida el CORDÓN, no el contacto** (Mario, 2026-10-28: «¿que solo tenga contacto?, ¿no
  debería ser por rango de superficie unida?»): una soldadura de filete resiste f_w·a·L (EN 1993-1-8
  §4.5.3), así que lo que se mide es el LARGO de la línea de contacto (el perímetro del tubo apoyado en
  la cara). Ese largo medido es el que usa el dimensionado de la soldadura, en vez de la estimación por
  cajas (`services/dimensionado.py` `_huella_mm`), que daba por resistente una soldadura sin cordón.
- **D3b. La unión se genera por TIPO, determinista** (Mario: «¿no será más fácil tener código
  determinista para ciertas uniones de esquina?»): `a_tope` (miembro contra la cara de otro, extremo
  a ras), `inglete` (reusa `library/miter.py`) y `boca_de_pescado` (tubo redondo contra tubo
  redondo); cada tipo corta los extremos y declara la soldadura con su largo real. La medición de D1
  queda como red para lo que se haga a mano. Solapada y con cartela, después.
- **D4. Criterio de diseño** (`design/guidelines.py`, lo lee todo modelador por MCP): un miembro
  inclinado que une dos piezas se hace con `create_brace`; nunca girando un `insert_component` a mano.
- **D5. El chequeo es barato**: se mide sólo sobre los pares declarados (no N²) y con la distancia
  OCCT que ya existe; el largo del cordón sale de la zona de contacto (p. ej. puntos de la teselación
  de `a` a ≤ tol de `b`), con un tope de tiempo medido en la piloto grande (clasificadora, 480 piezas).

## Alternativas descartadas

- **Sólo corregir la plataforma**: la próxima máquina lo repite en otra PC; Mario lo pidió explícito.
- **Sólo una pasada del revisor a ciegas**: no lo vio en 7 rondas; tiene que ser determinista.

## Fases

- **F1** (library/calidad + services + commands + design, M–L): D1–D5 con tests (la plataforma de
  hoy da FALLA en c77/c78/c79 y el pasamanos; un `create_brace` entre dos tubos da contacto y cordón;
  los testigos y las plantillas siguen aprobando; lo que falle en una plantilla se corrige en la
  plantilla).
- **F2** (MCP, S): la plataforma de mantenimiento se corrige con `create_brace` y se revisa a ciegas;
  se re-corre la puerta de las otras dos máquinas de la tanda.

## Lo que este plan NO hace

- No hace rodar la caja en los rodillos por gravedad (juntas de rodillos libres y gravedad
  inclinada en `simulate`): es otro plan.

## Riesgos

- **Falsos positivos en uniones viejas** (plantillas, testigos): F1 corre la regla sobre todos los
  testigos y plantillas; un contacto real que la regla no ve se arregla en la regla, uno fantasma
  en la plantilla.
- **Costo**: D5; si una máquina grande pasa el tope, se mide y se acota.

## Bitácora

### 2026-10-28 · F1 implementada (rama del worktree, sin mergear)

Con el ajuste del contrato que pidió Mario a mitad de fase: **D1b** (la soldadura se valida y se
dimensiona por su largo de cordón MEDIDO) y **D3b** (cada extremo se genera por tipo de unión).

- **Medida** (`kernel/contacto.py`): distancia OCCT + línea de contacto = la SECCIÓN de los dos
  sólidos (con caras coincidentes da el borde de la zona común). Cordón = lo soldable: sin los
  lazos encerrados por otro (el interior de un tubo hueco), sin la costura del cilindro que une el
  lazo exterior con el interior en una boca de pescado. Con un hueco ≤ 0,5 mm no hay sección: las
  aristas que corren enteras a ≤ tol de la otra pieza (un buje pasante «a ras» en su agujero con
  0,1 mm, un cubo a 0,1 mm de su brida). Forma: separadas / contenida / punto / arista (una recta
  sobre una arista de una de las dos: el canto de un extremo a escuadra) / línea / perímetro.
- **D1** `union.contacto_real` (registro v19, familia estructura; `library/calidad/contacto.py`):
  soldadura con l_eff = l − 2a ≥ max(30 mm, 6·a), **EN 1993-1-8:2005 §4.5.2(1)–(2)** (el contrato
  citaba §4.5.1: el largo eficaz mínimo está en §4.5.2(2)); apoyo (`contacto`/`pegado`) que no sea
  punto ni esté separado —una ARISTA sí vale de apoyo (el separador sobre el eje hexagonal de los
  rodillos F7 apoya en un canto del hexágono), no de cordón—; lo que gira sólo tiene que tocar; la
  tornillería, a ≤ 2 mm (holgura de ISO 273 serie gruesa); una banda apoya en su cama por su comba
  (≤ 2 % del largo de la cama, CEMA, el tope de `ruta_faja_modelo.py`: la faja deja 2 mm); perno: el
  hueco ≤ el largo de su tornillería (nota «MxL», el perno de su `join_bolted`, o 200 mm). Lo que une
  una cadena (`create_chain`/`create_hoist_chain`) no se mide: lo asienta su comando, y su distancia
  a un piñón de ~1000 caras costaba ~5 s por par (120 s el testigo de rodillos). Defecto sembrado:
  `riostra_que_no_toca`.
- **D1b**: `services/calidad_contacto.cordones_medidos` → `structure_engineering_check(cordones=)`:
  el cordón se dimensiona (τ = F/(a·L)) con el MENOR entre lo declarado y lo medido, y uno medido en
  0 es ERROR («no hay soldadura que dimensionar»). `declare_structure` propone el cordón medido en
  vez de la huella de las cajas (`dimensionado._huella_mm` queda sólo si OCCT no puede medir). En
  los testigos y plantillas no cambió ningún veredicto por esto.
- **D2**: la entrega corre lo mismo (`delivery_inputs` → `uniones`; batería v7): un bloqueante con
  cada par, su cifra y «créalo con create_brace… corta el extremo a ras».
- **D3/D3b** `create_brace` (`commands/miembro.py`, `library/miembro.py`): perfil de catálogo entre
  dos piezas; cada extremo por su `union`: `a_tope` (plano de la cara PLANA que corta el eje
  viniendo del centro; curva → error que pide boca de pescado), `boca_de_pescado` (resta el sólido
  que recibe y queda el tramo del centro: copiado al cilindro) e `inglete` (bisector de
  `library/miter.py` con `hacia` = el otro extremo del vecino; el primero de un par va sin `pieza` y
  la soldadura la declara el segundo). Declara `{id}_a|_b` soldadura con el cordón medido; un extremo
  que no asienta es error con la cifra. `miter` = (α_a, α_b) y `cut_length` = el largo exterior; la
  lista de corte toma ese largo y la sección de la ficha para un perfil INCLINADO (la caja de una
  diagonal no es su largo; vale también para `create_frame`). Paramétrico (puntos con `=expr`).
  **Solapada y cartela no entran** (otra fase): hoy se resuelven a_tope contra una placa.
- **D4**: regla «uniones» de `design/guidelines.py` (lo declarado se toca; miembro inclinado =
  `create_brace`, nunca un `insert_component` girado).
- **La plataforma real** (su corrección 8, fuera del repo; 214 piezas, 243 uniones): `union.contacto_real` FALLA con 16 pares y la entrega pasa de VERDE a ROJO sólo por
  esto: `S_arr_pY[0..1]`, `S_arr_nY[0..1]` (c77/c78 «Arriostre lateral» ↔ postes c67/c69 y
  c68/c70) y `S_arr_tras[0..1]` (c79 ↔ c69/c70) **no se tocan, a 5,01–5,02 mm**;
  `S_bar_rieles_*` (pasamanos lateral ↔ poste de baranda) **tocan por una arista** de 5,4–6,4 mm;
  `S_pas_*[0]` (pasamanos de escalera ↔ poste inferior) **0,5 mm de cordón** y `S_pas_*[1]` (↔ poste
  superior) **un punto**; `S_pas_tras_esq*` (pasamanos trasero ↔ lateral) **4 mm**.
- **Testigos y plantillas**: los cuatro testigos sólo cambian versión y el ítem nuevo (OK, mensula
  NO_APLICA): re-congelados uno por uno. Barrido de la regla (todas OK tras los arreglos):
  `create_belt_conveyor` (por defecto, 2, 3 m×800, 6 y 12 m), `create_roller_conveyor` (1 m, 3 m,
  libre, roscado+disco, sin taller), `create_pneumatic_cylinder`, `layout_tablero` (piloto),
  `join_bolted`; y un elevador de 333 piezas (fuera del repo). Arreglos:
  1. **Plantilla** `create_roller_conveyor` **v4**: la pared interior de la guarda fija se declaraba
     soldada a la exterior (77 mm de luz: fantasma); ahora se suelda a sus dos extremos, que tocan
     las dos paredes. Misma geometría, pero el checkpoint guarda los fasteners: sube la versión y
     todo log la corrige (no hace falta sello).
  2. **Regla** (falsos positivos): la banda a 2 mm de su cama (comba), el piñón a 0,1 mm de su buje
     y los bujes pasantes del elevador (hueco ≤ tol: aristas cercanas), el separador sobre el eje
     hexagonal (la arista es apoyo), las uniones de cadena (no se miden).
- **D5 (costo, CPU de la regla sola, laptop)**: plataforma 2,4 s (243 uniones); testigo de rodillos
  3,3 s (219); elevador 3,1 s (333 piezas, 256 uniones); faja de 12 m 5,0 s (292); el peor,
  rodillos de 3 m **18 s** (402 piezas, 502 uniones: la sección con ejes hexagonales y piñones de
  ~126 caras). La piloto clasificadora de 480 piezas no está en esta máquina: queda por medir. La
  caché del kernel por par hace que la entrega, la puerta y la memoria de una corrida paguen una
  vez. Lo que se acotó: la distancia y la sección sólo con las caras de la caja común (rodillos de
  3 m: 45 s → 18 s) y las cadenas fuera.
- **Suite** (laptop, sin xdist): exit 0, ~6970 tests, 44 min; `ruff` limpio. Tests re-congelados a
  propósito: versión del registro 19 y de la batería 7, `create_roller_conveyor` v4 (sus huellas de
  F6/F7/F8 «cadena» suben una unión: la de la guarda), `REGISTRY` 64 comandos.
