---
estado: en curso
nota: F1 hecha (create_belt_conveyor v6, 2026-10-28; rama sin mergear al escribir esto); falta F2 (la clasificadora de 12 puestos por MCP con su revisor a ciegas). Decisión vetable de F1 en la Bitácora - el tramo se compara con el bastidor, así una faja de largo 6000 sale en 2 tramos
descripcion: Una faja de banda de más de 6 m sale en tramos empernados que se fabrican y transportan, con rodillos de retorno, y cada perno de la cama se puede apretar
---

# Una faja larga se fabrica en tramos, lleva rodillos de retorno y cada perno se puede apretar

## Estado y origen

Mario, al irse a dormir (2026-10-27): «necesito que escojas estratégicamente 3 máquinas de la lista
para implementar en apolo, mañana quiero verlo terminado. procede con pensamiento critico y buenas
practicas». Una de las tres es el piloto de la familia `clasificadora-manual` (12 puestos, faja de
10,2 m entre tambores). La puerta v17 la aprobó (33 OK), pero el revisor de taller a ciegas
encontró defectos que son de la PLANTILLA `create_belt_conveyor`, no del modelador:

- **ALTA**: el larguero es UNA barra de 10 474 mm (`verify` bbox de `c6_rail1`): no existe en el
  mercado (barra de 6 m) y la máquina no se desarma. Las «bridas de empalme» que puso el modelador
  cuelgan soldadas al mismo tubo: no dividen nada.
- **ALTA**: la cama de deslizamiento es UNA chapa de 9 997 × 620 × 6 mm: no sale de una plancha
  comercial (2,4 a 6 m) y tampoco se desarma.
- **MEDIA**: el ramal de retorno no tiene ningún rodillo en 8,3 m (entre x −4150 y 4180): cuelga en
  catenaria y roza.
- **MEDIA**: las placas de los soportes de cama van atornilladas (2 × M8) a la cara interior de un
  tubo rectangular CERRADO: la tuerca queda dentro del tubo, sin acceso de herramienta.

La familia `faja-plana` (280 variantes en la cola, largo hasta 6 m) tiene los dos últimos defectos
también: con 6 m el retorno ya pasa los 3 m libres.

## Lo que hay hoy

- `core/apolo/library/belt_conveyor_bastidor.py:47` `largueros`: una pieza por lado, del largo del
  bastidor. `:156` `cama`: una chapa entera; soportes cada ≤ 800 mm con placa de extremo
  «atornillada al alma del larguero» M8 × 2 (`:180`), declarada por `fasten` sin pieza (la BOM la
  cuenta por la unión dimensionada).
- `models_faja.py:58`: `largo` hasta 30 000 mm, sin tramos ni retorno.
- `exec_faja.py`: el sello de entrada `sellar` (`CommandSpec.al_crear`) ya sirve para que lo NUEVO
  nazca con un comportamiento y un log viejo regenere igual (así entró `cierres` en la v5).

## Decisiones (para vetar)

- **D1. Tramos.** Campo nuevo `tramo_max` (mm, opcional). Sin él (logs viejos), el bastidor sale en
  una pieza como hoy. Con él, el bastidor se parte en `N = ceil(largo_bastidor / tramo_max)` tramos
  IGUALES; cada tramo lleva sus dos largueros, su cama y sus soportes. En cada empalme, una placa de
  empalme soldada a la punta de cada larguero y las dos placas atornilladas entre sí (pernos con
  acceso por fuera del tubo), y una estación de patas bajo el empalme. *Porqué*: es como se fabrica
  y transporta un transportador largo; la junta con su pata no deja un voladizo en el empalme.
- **D2. Sello: `tramo_max = 6000` para toda faja NUEVA.** *Porqué*: 6 m es la barra comercial de
  tubo; una faja ≤ 6 m no cambia nada (un tramo), así la familia faja-plana sale igual que hoy. Un
  cliente puede pedir tramos más cortos (transporte).
- **D3. Rodillos de retorno.** Campo nuevo `retorno` (bool; el sello lo pone en `true`). Rodillos
  de catálogo bajo el ramal de retorno, con sus soportes atornillados a los largueros, cuando el
  ramal libre entre apoyos pasa 3000 mm; espaciados ≤ 3000 mm. *Porqué*: 3 m (10 ft) es el
  espaciamiento usual de rodillos de retorno (CEMA, fuente secundaria: verificar en F1 con la
  fuente que se cite en el código); por debajo de 3 m no cambia nada.
- **D4. Placa del soporte de cama con acceso.** Con el sello nuevo, la unión placa ↔ larguero deja
  de ser un perno con tuerca dentro del tubo cerrado: remache-tuerca (inserto roscado ciego) de
  catálogo si existe para esa métrica, o el perno pasante que cruza el tubo; decide F1 por lo que
  hay en el catálogo (`112_fijacion_ciega.yaml`) y lo escribe. Logs viejos: igual que hoy.
- **D5. Un solo campo de sello si alcanza.** Si `tramo_max`, `retorno` y la unión nueva pueden
  colgar de un único campo oculto de sello (como `cierres`), mejor que tres; F1 decide por la
  claridad del schema para el agente (lo que el agente necesita cambiar va visible: `tramo_max`).
- **D6. Versión.** Cambia la geometría con params nuevos → los logs viejos no los traen y regeneran
  igual; igual se sube la `version` del `CommandSpec` si `tests/test_contrato_comandos.py` lo pide.

## Alternativas descartadas

- **Que el modelador parta la faja a mano**: el larguero es interno al super-comando; la cirugía
  pierde la edición paramétrica (y `N_PUESTOS` dejaría de cambiar el largo).
- **Una faja por tramo con `insert_project`**: cada tramo tendría sus tambores; no es una faja.

## Fases

- **F1** (commands + library, M): D1–D6 con sus tests (tramos iguales, empalme con pata, sin
  interferencias, BOM con barras ≤ `tramo_max`; retorno con espaciamiento ≤ 3 m; unión con acceso;
  un log viejo regenera igual). Gate: suite completa + ruff.
- **F2** (MCP, S): la clasificadora de 12 puestos se corrige con la plantilla nueva y la revisa
  otro revisor a ciegas; la prueba de familia en 36 puestos.

## Lo que este plan NO hace

- No cambia la regla de la puerta sobre la carrera del tensor (el revisor pidió 1 % del lazo: el
  modelador elige el tensor con su cuenta).
- No hace que `add_device` repita dispositivos con una variable (las setas que crecen con
  `N_PUESTOS`): queda en el backlog.

## Riesgos

- **Cachés**: un open caliente de una faja vieja sirve geometría vieja si el executor cambia sin
  versión → D6 y `test_contrato_comandos`.
- **Tramos y estaciones**: la estación del empalme puede chocar con la estación por vano máximo
  (lo que vio la prueba de 36 puestos: patas sobre bridas) → las estaciones se calculan JUNTAS
  (empalmes primero, intermedias para el vano), con test.

## Bitácora

### F1 (2026-10-28): tramos, retorno y pernos pasantes — `create_belt_conveyor` v6

Hecho (commands + library; `tests/test_belt_conveyor_v6.py`):

- **D1** `library/belt_conveyor_tramos.py`: `N = ceil(largo_bastidor / tramo_max)` tubos IGUALES
  de `(largo − 2·10·(N−1))/N`; empalme = dos placas de 10 mm (una soldada a cada punta, cordón
  perimetral a 4 mm) que salen 45 mm del tubo por fuera y por debajo, unidas con 3 × M12x40 DIN
  933 + tuerca por fuera del tubo. La estación del empalme va bajo el tramo de la COLA, a 50 mm
  de la placa; `estaciones` pone primero las fijas (extremos + empalmes) y reparte las
  intermedias por vano entre fijas (`VANO_MAX`): ninguna pata sobre una placa (test). Cama, guardas
  laterales y largueros por tramo (`rail{i}_{k}`, `cama_{k}`, `guarda{i}_{k}`); con un tramo, los
  sufijos y la geometría de siempre. La guarda inferior cruza el empalme (se atornilla a un
  tramo): cortarla dejaba una ranura de 22 mm hacia el lazo. Un `tramo_max` que deja el empalme a
  < 400 mm de las patas de un extremo es error accionable.
  Medido: 10 200 mm entre tambores → bastidor 10 474 mm → con 6000, 2 tramos de 5227,15 mm y 5
  estaciones (−4906, −2514, −122, 2489, 5100); con 3000, 4 tramos. Sin interferencias (sin
  exclusiones) y todo a tierra por lo declarado.
- **D2** el sello pone `tramo_max = 6000` y `criterio = 6`. **Decisión (vetable)**: lo que se compara
  con la barra de 6 m es el BASTIDOR (largo + voladizos de chumaceras y tensor: +274 mm con los
  defaults), no el largo entre tambores: una faja de `largo` 6000 tiene largueros de 6274 mm, que
  no salen de una barra, así que sale en 2 tramos; con los defaults, un tramo hasta `largo` ≈
  5726. La de 4 m sale en un tramo, con los mismos largueros (4274,3), patas y soportes de la v5.
- **D3** `library/belt_conveyor_retorno.py`: rodillos cuando `largo` > 3000, vanos ≤ 3000
  contando desde los ejes de los tambores. Fuente del 3 m: Martin Engineering, *Foundations*
  («Belt conveyor idler spacing»), que remite a las tablas de CEMA (*Belt Conveyors for Bulk
  Materials*): retorno típico 3 m (10 ft); FUENTE SECUNDARIA, la tabla de CEMA no se verificó.
  Rodillo = el más chico del catálogo con capacidad ≥ 2 × el peso de banda (PVC) de un vano
  (RODILLO-50 en todas las variantes medidas). Su cara queda a 0,5 mm de la tangente exterior del
  ramal (inclinada: el motriz va engomado), así `ruta_faja*` lo cuenta como apoyo por afuera y el
  lazo sigue abrazando los dos tambores (test con `armar`). Soportes de chapa de 8 mm atornillados
  a la cara interior del larguero (2 × M8 pasantes con buje), entre dos soportes de cama y lejos
  de patas y empalmes; la guarda inferior se corta en cada soporte. 4 m → 1 rodillo; 6 m → 2;
  10,2 m → 4 (el reparto parejo de 3 caía sobre una pata y dejaba un vano > 3 m).
  **La cuña rodillo ↔ banda SÍ la sondea la puerta** (la trata como la de un tambor que la banda
  toca): con el rodillo solo, `riesgos.partes_moviles` pasaba a FALLA en la de 4 m (17 de 192
  sondas llegaban desde abajo). Se resguarda (con `guardas`): cajón de chapa bajo el rodillo,
  atornillado a sus soportes, con alas a 15 mm del ramal que siguen 330 mm (el `ALCANCE` de las
  guardas de los tambores); el muñón entra en un alojamiento CIEGO de 5 mm del soporte (por el
  barreno pasante una sonda tocaba la punta del eje que gira). Medido con la puerta (requisitos de
  `test_la_puerta_sobre_create_belt_conveyor`, sin funciones declaradas): 4 m v6 = 21 OK / 2
  FALLA, igual que la v5 (las dos de siempre: funciones sin declarar y sobrantes); 10,2 m v6 = 20
  OK / 3 FALLA, igual que la v5 (más el par de arranque del motor por defecto, que elige el
  modelador); la v6 de 10,2 m deja MENOS guardas sobrantes que la v5.
- **D4** el catálogo no tiene remache-tuerca y un remache ciego no se desarma (el soporte se
  suelta para cambiar la banda): perno PASANTE M8x70 DIN 933 + tuerca que cruza el larguero por un
  buje Ø14 soldado (modelado en el larguero: barreno Ø9 ISO 273). La cuenta pide el buje: precarga
  0,7·A_s·R_y ≈ 16,4 kN contra ≈ 2π·f_y·t²/4 ≈ 11,5 kN del alma de 4,8 mm (líneas de rotura, cota
  inferior; criterio de diseño). Los soportes extremos se corren lo necesario para que la tuerca
  no quede bajo el marco del UCT o la placa porta-chumacera (en la de 4 m no se movió ninguno).
- **D5** dos campos: `tramo_max` VISIBLE (el modelador pide tramos más cortos para el transporte)
  y `criterio` OCULTO (int, como `join_bolted`: 5 = la v5, 6 = retorno + pasantes; un número más
  para lo próximo, no otro bool).
- **D6** `version` 6 (huella y `CAMPOS` al día). Un log v5 (sin los campos) regenera con las
  mismas 108 piezas, 145 uniones y cotas medidas con el código de antes (test).

Gate: suite completa secuencial en la laptop, exit 0 (6835 pasan, 10 saltados, 0 fallas) + ruff
limpio.

Para F2: con el sello, la faja de 10,2 m sale en 2 tramos con 4 rodillos de retorno y la puerta
no suma ninguna FALLA nueva; el motor por defecto no arranca 10 m a plena carga (elige otro el
modelador).
