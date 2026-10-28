---
estado: en curso
nota: contrato escrito por Claude con el criterio delegado (2026-10-28, vetable por número); falta F1 (tramos, retorno, placas de cama con acceso) y F2 (la clasificadora de 12 puestos por MCP con su revisor a ciegas)
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
