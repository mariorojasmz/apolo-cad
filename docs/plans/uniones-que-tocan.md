---
estado: en curso
nota: contrato escrito por Claude con el criterio delegado (2026-10-28, vetable por número); falta F1 (regla de la puerta + comando de riostra + criterio de diseño) y F2 (la plataforma de mantenimiento corregida con el comando, por MCP)
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
