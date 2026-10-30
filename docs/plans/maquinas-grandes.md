---
estado: en curso
nota: F0 medida (2026-10-30, bitácora). Contrato aprobado por el escritorio con la delegación de Mario (2026-10-29 «tú toma las decisiones a partir de ahora»); D1–D6 siguen vetables por Mario. F1 (D1) implementada en su rama, sin mergear (lavadora: replay 348 → 80 s, editar c86 → 54 s, 723/723 piezas y 649 fijadores iguales). F2 (D2+D3) implementada en su rama sobre la F1, sin mergear (lavadora, CPU: barreno sin perno 103 → 3,4 s, delivery_check 172 → 66 s, puerta sin sobrantes 595 → 261 s, completa 1221 → 889 s; salida IGUAL); F3–F4 sin lanzar
descripcion: En una máquina de ~700 piezas, editar el principio del log, delivery_check, check_interference, engineering_check y la puerta terminan en minutos y sin cortarse por tiempo, con los mismos resultados
---

# Las herramientas terminan a tiempo en una máquina de 700 piezas

## Estado y origen

Una lavadora de bandejas de ~720 piezas (723 sólidos, 1477 comandos) pasó 8 rondas de
corrección. Lo que dicen los reportes del modelador y del revisor de esas rondas:

- `delivery_check` «se cortó por tiempo» en las rondas 4 a 8 (la 4, cinco veces; la 5 a la 8, dos
  veces cada una). Sin su semáforo, el modelador cerró con un plan B (`check_assembly`,
  `gravity_test`, `verify`).
- `check_interference` acotado a 2–3 ids o grupos y `engineering_check` también se cortaron (rondas
  6 y 7, y los revisores 4 a 8). Por eso no hubo verificación numérica de pernos, soldaduras, L10,
  flechas ni pandeo.
- Editar o borrar un comando del principio tardó «10–15 min» en la ronda 2, «30–90 min» en la 4,
  «10–50 min» en la 5 y «entre 1 y 3,5 horas» en la 8. Un `remove_commands` de 4 comandos tardó
  ~1,5 h y `delete_connection` dio timeout aunque sí borró.
- La puerta tardó «50 a 90 min» al modelar. En la ronda 1 «no termina en 20 h» y bloqueó el
  servidor. Su última corrida (`puerta.json`, registro v21) anota `total` 1692 s: `sobrantes`
  980, `fuentes.mecanica` 260 y `entrega` 236.

[puerta-rapida](puerta-rapida.md) F1 ya bajó `sin_sobrantes` (1615 → 421 s en la ronda 1). Su F2,
el «Trazador compartido», quedó por decidir con un perfil nuevo. El plan
[lo-fijo-que-gira](lo-fijo-que-gira-y-lo-que-cuelga.md) excluye esto a propósito («No acelera la
puerta ni las tools en máquinas de ~700 piezas… plan propio que se mide aparte»). Este es ese
plan.

La regla es la de puerta-rapida: **ningún resultado cambia**. Ni la geometría, ni los veredictos,
ni lo que dice la evidencia. Sólo se deja de recalcular lo que ya se sabe, se calcula lo mismo de
forma más barata con prueba de igualdad, o se deja de calcular lo que la tool no pidió.

## El problema / lo que hay hoy

Lo medí OFFLINE con `scripts/medir_maquinas_grandes.py` (sin la API ni la base), en el escritorio
(i7-9700K, 8 hilos, 32 GB). Usé el `.apolo` final y el de la ronda 4, con 2 a 4 medidas a la vez:
`process_time` ≈ pared, porque el trabajo es de un hilo. Tabla completa en la Bitácora (F0).

| qué | pared (s) | lo que manda |
|---|---|---|
| replay frío (1477 comandos) | 365–369 | `join_bolted`: 40 comandos, 305 s (83 %), ~7,6 s cada uno |
| editar `c86` (posición 117: re-ejecuta 1259 comandos) | 326–341 | lo mismo |
| `scene_payload` tras esa edición | 23–28 | teselar 723 piezas nuevas; cajas 7 s |
| `/api/checks` (lo que corren `check_interference` Y `engineering_check`) | 23 + 46 + 93 ≈ 160 | interferencia global + estructura + lints, SIEMPRE las tres |
| ·· interferencia acotada a `c53,c88` (lo que el agente pidió) | 7 | cajas de 624 piezas: 6,9 s |
| `delivery_check` (sin gravedad) | 209–279 | lints 102–123 · poses 48–78 · uniones que tocan 26–41 · interferencias 18 · acceso 14 |
| puerta sin gravedad ni marcha | 1833 | `sobrantes` 1025 · `fuentes.mecanica` 315 · `entrega` 239 · `fuentes.seguridad` 129 |

Cuatro causas explican casi todo:

1. **La caja de una forma se recalcula cada vez y es cara.** `Shape.bounding_box()` de build123d
   0.10 es `optimal=True` por defecto. Primero hace `BRepTools.Clean` (borra la malla) y luego
   `BRepBndLib.AddOptimal` sobre la geometría exacta: ~13 ms por pieza en esta máquina.
   `join_bolted` (`commands/union_taller.py:145-165`, `_en_camino`) recorre TODA la escena
   pidiendo la caja de cada pieza para buscar obstáculos detrás. Son 40 comandos × ~500 piezas =
   19 874 cajas, **290 s de los 365 del replay**. Esas mismas formas no cambian entre un
   `join_bolted` y el siguiente. Las cajas son también el 73 % de `structure_rules` (33,6 de
   46 s: `mass._bbox`, `vigas_rules._caja`, `contacto`), 65 s de `delivery_check` (41 s en las
   poses: `interference_report` pide 624 cajas por pose) y 299 s de la puerta (152 s en
   `vigas_rules._caja`, dentro de la ingeniería de cada candidata de `sobrantes`).
   Escala O(join_bolted × piezas): crece con el cuadrado del tamaño de la máquina.
2. **El clasificador de punto de OCCT se construye por punto.** `Rayos.dentro`
   (`kernel/rayo.py:99-109`), `Rayos.tramos` y `Filtro._alguno_dentro`
   (`library/interferencias_filtro.py:101-111`) arman un `BRepClass3d_SolidClassifier` nuevo en
   cada consulta. `colisos_de` (`services/calidad_colisos.py:92-133`) lo llama por cada par de caras
   planas paralelas enfrentadas. Los 4 «Resguardo de toma de soplador» (170 caras planas, 14 365
   pares cada uno) hacen 225 consultas de ~104 ms: **24 s por pieza, 96 de los 105 s** de
   `agujeros_atribuidos`. Eso es el lint «barreno sin perno» de `delivery_check` y de
   `/api/checks`. La puerta lo corre TRES veces con un `_Medidor` nuevo cada vez: el lint de la
   entrega (`delivery_inputs.py:220-226`), el de `reglas_de_ingenieria`
   (`calidad_mecanica.py:46-49`) e `insumos_agujeros` (`calidad_mecanica.py:83`).
3. **`/api/checks` lo calcula todo para cualquier pregunta.** `check_interference(ids=…)` y
   `engineering_check` llaman a la MISMA ruta (`tools/validacion.py:37`, `:69`), y
   `run_checks` (`api/routers/validation.py:68-160`) siempre corre la interferencia, las reglas de
   estructura y los lints. Pedir la interferencia de 2 piezas (7 s) cuesta ~160 s.
4. **Las lecturas largas son síncronas y su trabajo queda huérfano.** `delivery_check`,
   `check_interference` y `engineering_check` usan `_api` con el `httpx` de 120 s
   (`mcp_server.py:44`), no `_submit_and_wait`. A ~160–280 s se cortan siempre. El handler sigue
   corriendo con `STATE_LOCK` tomado, el agente reintenta y cada reintento encola otro tanto
   detrás. La puerta, además, sostiene `STATE_LOCK` durante TODO `reunir`
   (`validation.py:264-268`), ~30 min en esta máquina. Offline, la edición de `c86` cuesta 5,5 min
   + 0,5 de payload. Los «1–3,5 h» de los reportes son, por inferencia, esa espera por el lock:
   cuadra con lo medido, pero no la medí en la API.

## Lo que se revisó antes de escribir esto

- `doc/document.py:183-281` (regenerate): reanuda en el checkpoint anterior al primer cambio, así
  que editar `c86` re-ejecuta 1259 de 1372 comandos de escena. Los checkpoints cuestan 0,27 s (87
  copias) y `_snapshot` 0,01 s: no son el problema. `RegenState.copy` comparte los shapes, así
  que una caja memoizada por forma sigue sirviendo entre regenerates para lo que no se re-ejecutó.
- `build123d.geometry.BoundBox.from_topo_ds`: `Clean_s` + `AddOptimal_s`. Ninguno de los dos
  depende de la malla, porque el `Clean` la borra antes de medir.
- `commands/union_taller.py`, `services/calidad_agujeros.py`, `services/calidad_colisos.py`,
  `kernel/rayo.py`, `library/interferencias_filtro.py`, `services/delivery_inputs.py`,
  `services/calidad_mecanica.py`, `api/routers/validation.py`, `api/common.py::_state_or_error`,
  `api/autosave.py::_flush_body` (el `pack` de la caché de geometría tarda 0,8–1 s: no pesa) y
  `tools/validacion.py`, `tools/introspeccion.py`.
- **cProfile no ve el trabajo de un constructor de OCP** (`BRepClass3d_SolidClassifier(...)` no
  es un evento `c_call`): en los lints atribuía 12 s de 93. Por eso el script cuenta las cajas por
  llamador y los perfiles finos usan contadores con `process_time`.
- Prototipos fuera del repo, que fijan las decisiones:
  - **D1**: `Shape.bounding_box` memoizada por identidad (`is`) durante un replay frío completo.
    Da **78,8 s de pared (61,3 de CPU) contra 365 s**, con 19 318 aciertos y 3351 fallos. Las 723
    piezas salen IGUALES una a una (nombre, comando, volumen a 1e-6, caja a 1e-6, n.º de caras),
    también los `fasteners`, contra el documento del replay sin memo.
  - **D2**: sobre los 900 puntos que `colisos_de` clasifica en los 4 resguardos, la paridad de
    cortes con `IntCurvesFace` (el `Rayos.cortes` ya cargado, recta oblicua) da **0 distintos de
    900** en **1,7 s contra 97,9 s**. El clasificador cargado UNA vez por sólido (`Perform` por
    punto) da 900/900 iguales, pero sólo baja a 47 s; en 600 puntos al azar dentro de las cajas
    de las 20 piezas con más caras, 0 distintos (15 contra 24 s).

## Decisiones (para vetar)

- **D1. La caja de una forma se calcula UNA vez por forma.** Va en `kernel/caja.py`: `caja(shape)`
  devuelve la misma `BoundBox` que `shape.bounding_box()`. La clave es `id(shape)` y guarda
  `weakref` a la forma, su `wrapped`, su `TShape` y una copia de su `Location`. El acierto exige
  `is` en la forma, en `wrapped` y en `TShape`, y la `Location` igual (`IsEqual`) (raíz:
  `core/apolo/CLAUDE.md`). Ojo: `move`/`locate` de build123d 0.10 mueven el MISMO `wrapped` en
  sitio (lo medí). Por eso se compara la `Location` y no basta la identidad. El `weakref` no
  retiene formas viejas: el callback borra la entrada. En un acierto se sigue
  llamando a `BRepTools.Clean` (0,8 s en 22 669 llamadas), así que ningún teselado posterior ve
  otro estado de malla. Los llamadores CALIENTES medidos pasan a `caja()`:
  `union_taller._en_camino`, `exec_modificar._exec_drill_hole`,
  `checks.interference_report`, `mass._bbox`, `vigas_rules._caja`, `kernel/contacto._toca_caja` y
  `_caja_comun`, `calidad_agujeros._caja`, `drawing/process._sorted_dims`,
  `calidad_seguridad._caja` y `kernel/mesh.bbox_payload`. Un test de texto impide volver a `.bounding_box()` en esos módulos.
  *Por qué*: es el 83 % del replay y el 73 % de la estructura, y la geometría sale idéntica pieza a
  pieza (prototipo). No cambia la salida de ningún executor: **sin `version` ni
  `GEOM_CACHE_EPOCH`**, y lo dice el commit. *Vetable*: parchear `Shape.bounding_box` de
  build123d entero. Lo descarto (ver Alternativas).
- **D2. «¿Este punto está dentro?» por paridad de cortes, con el clasificador sólo si hay duda.**
  `Rayos.dentro` cuenta los cortes de DOS rectas oblicuas distintas desde el punto (el
  `IntCurvesFace` cargado una vez por sólido). Si coinciden, ésa es la respuesta. Si difieren, o
  algún corte cae a < 1e-4 del punto (rasante), decide el `BRepClass3d_SolidClassifier`, cargado
  una vez por sólido y con `Perform` por punto. Lo usan `Rayos.dentro`, `Rayos.tramos` y
  `Filtro._alguno_dentro`. *Por qué*: 57× en el prototipo y 0 distintos. La doble recta y la caída
  al clasificador cubren lo rasante que el prototipo no ejercitó.
- **D3. Los agujeros de una forma se miden una vez por corrida.** `agujeros_de(shape)` se
  memoiza por `is` en el memo de la corrida (`engineering/memo_corrida.py`, el que abre
  `memo_de_geometria`; fuera de una corrida no memoiza). Así la puerta no paga tres veces la misma
  pieza. *Por qué*: con D2 el costo baja a pocos segundos, pero sigue siendo 3× trabajo idéntico.
  Es el patrón que puerta-rapida D3 ya usa.
- **D4. `/api/checks` corre sólo lo que se le pide.** Hay un campo nuevo `partes` (subconjunto de
  `interferencias`, `ingenieria`, `estructura`, `lints`). Si falta, se corre todo y la respuesta es
  byte-idéntica (la UI no cambia). `check_interference` pide `["interferencias"]` y
  `engineering_check` pide lo demás. Lo que no se pidió no aparece en la respuesta, no sale con
  `null`. *Por qué*: con D1, pedir la interferencia de 2 piezas pasa de ~160 s a ~1 s. El golden
  MCP cambia (las peticiones) y se re-congela a propósito.
- **D5. `delivery_check`, `check_interference` y `engineering_check` van como job con recibo.**
  Usan `?async=true` en las dos rutas y `esperar`/`_submit_and_wait` en el MCP, como
  `publication_gate`. Si no hay respuesta en `APOLO_MCP_WAIT_S`, devuelven el RECIBO, nunca
  «se cortó». Una lectura idéntica en curso (misma ruta, mismo cuerpo y misma `firma_documento`)
  devuelve el job que ya corre en vez de encolar otro: un reintento no apila trabajo huérfano
  sobre `STATE_LOCK`. Cola: `COSIM_JOBS`, la de las lecturas largas, donde ya vive la puerta.
  *Vetable*: una cola propia de lecturas, para que un `delivery_check` no espere detrás de una
  puerta de 30 min. *Por qué*: aunque D1–D3 bajen las cifras, una máquina de 1500 piezas vuelve a
  pasar los 120 s, y hoy un timeout DEJA el trabajo corriendo con el lock. Sin `?async`, las rutas
  quedan byte-idénticas.
- **D6. Nada cambia de criterio, de orden ni de umbral.** `VERSION_REGISTRO`, `VERSION_BATERIA`
  y las versiones de executor no suben. El gate de cada fase es la IGUALDAD de la salida (sin
  `ms`/`tiempos_s`) antes y después, en los testigos y en la lavadora, no una tolerancia.

## Alternativas descartadas

- **Parchear `Shape.bounding_box` de build123d para todo el proceso**: alcanza también al
  sandbox, a los tests y a quien llame con otra `tolerance`, y es magia que un upgrade de
  build123d rompe en silencio. Migrar los llamadores medidos es explícito y deja un test que lo
  vigila.
- **`bounding_box(optimal=False)`**: es 30× más barata, pero da cajas MÁS GRANDES (con la
  tolerancia y los polos de las B-spline). Cambia qué piezas «tocan la zona», las candidatas de
  interferencia y las cotas que se leen de la caja. Cambia veredictos.
- **Replay por dependencias** (re-ejecutar sólo lo que depende del comando editado): es la única
  palanca que baja un replay de verdad, pero toca el corazón del log, y los executors leen la
  escena entera (`join_bolted` busca obstáculos en TODA la escena; un selector `cerca` mira
  posiciones). Tras D1 el replay entero cuesta ~80 s: sin una medida nueva que lo pida, no.
- **No re-ejecutar un renombre** (`edit_command(c86, {name})`): el nombre lo leen comandos
  posteriores (el rol de `join_bolted`, el criterio de uniones) y puede cambiar su resultado.
- **Correr la puerta fuera de `STATE_LOCK`** (un proceso aparte sobre una copia del `.apolo`): es
  el arreglo de fondo del bloqueo de 30 min, pero cambia la coreografía de la API y de sus clientes.
  Primero se mide la puerta tras D1–D3; si sigue > 10 min, plan propio.
- **Bajar la resolución de algo** (voxeles, rayos, pares): cambia veredictos.

## Fases

- **F0 (hecha)**: la medición de arriba y la Bitácora. `scripts/medir_maquinas_grandes.py` queda
  como herramienta. Mide etapas, cajas por llamador y `--cache` para abrir en caliente sin
  replay.
- **F1 — D1** (`kernel/caja.py` nuevo + los llamadores medidos en `commands/`, `kernel/`,
  `library/`, `drawing/`, `services/`; M). Tests: `caja()` contra `bounding_box()` (misma caja,
  validación por forma, `wrapped`, `TShape` y `Location`, recalcula tras `move`/`locate` en
  sitio, el `weakref` suelta la forma, `Clean` en el acierto) y
  el test de texto de los módulos migrados. **Gate**: (a) suite completa verde; (b)
  `scripts/testigos.py --en-proceso` sin re-congelar; (c) la lavadora con el script: replay
  frío **≤ 120 s** (prototipo: 79 s), editar `c86` **≤ 120 s**, `checks_estructura` **≤ 20 s**,
  y las 723 piezas idénticas pieza a pieza (método del prototipo) contra un replay de `main`
  antes de F1.
- **F2 — D2 + D3** (`kernel/rayo.py`, `library/interferencias_filtro.py`,
  `services/calidad_agujeros.py`, `engineering/memo_corrida.py`; M). Tests: la paridad contra el
  clasificador en escenas sintéticas con tubos, chapa con ventanas y puntos rasantes a una arista
  y a un vértice, más la caída al clasificador cuando las dos rectas difieren. El memo, con su
  caso `is`. **Gate**: (a) suite; (b) testigos iguales; (c) la lavadora: `lint_agujeros_atribuidos`
  **≤ 10 s**, `entrega` **≤ 90 s** y la puerta sin sobrantes **≤ 300 s**, con
  `delivery_report` y `reunir` IGUALES salvo tiempos.
- **F3 — D4 + D5** (`api/routers/validation.py`, `api/common.py`, `tools/validacion.py`,
  `tools/introspeccion.py`, golden MCP; M). Tests: `partes` (sin él, byte-idéntico; con él, sólo
  lo pedido), el job y su recibo, la deduplicación (dos POST iguales = un job; otro cuerpo u otra
  firma = otro) y el golden re-congelado a propósito. **Gate**: suite + `npm test`/`npm run
  build` si toca `ui/` (no debería) + E2E por stdio (`scripts/e2e_mcp.py`) contra una API sobre
  una COPIA de la base con la lavadora cargada: `check_interference(ids=[2 piezas])` < 15 s y
  `delivery_check()` da el semáforo o un recibo, nunca un error de timeout.
- **F4 — volver a medir** (sólo lectura; S). `medir_maquinas_grandes.py` y `medir_sobrantes.py`
  sobre la lavadora tras F1–F3. Con ese perfil se decide la F2 de puerta-rapida (el `Trazador`
  compartido: hoy codo 380 s y apoyo 375 s de los 983 de `sobrantes`, con 172 candidatas; D1 ya
  ataca los ~150 s de cajas de `vigas_rules` en su ingeniería) y si el
  `scene_payload` de una mutación por MCP (23–28 s, de los que las cajas eran 7) pide un modo
  sin mallas.

F1 y F2 tocan archivos distintos y pueden ir en paralelo. F3 no depende de ellas. F4 va al final.

## Lo que este plan NO hace

- No cambia qué es candidata de la puerta, ni un umbral, ni un ítem (D6).
- No saca la puerta de `STATE_LOCK` ni la corre en otro proceso (ver Alternativas): se decide con
  la medida de F4.
- No acelera `run_script` (27 s de pared en 100 comandos, casi todo esperando al worker) ni
  `drill_hole` más allá de su caja: son el resto del replay tras D1, ~60 s.
- No toca la gravedad ni la marcha de la puerta (corren fuera de `STATE_LOCK`, con
  `PHYSICS_LOCK`; 13 y 34 s en `puerta.json`).

## Riesgos

- **Una caja memoizada de una forma mutada en sitio** → la validación compara `wrapped`,
  `TShape` y `Location`. La raíz prohíbe a los executors mutar un shape, pero `move`/`locate`
  mueven en sitio y un test los cubre. Una mutación de la GEOMETRÍA dentro del mismo `TShape` (no
  la hace ningún executor) no se detectaría: el test de texto de D1 limita `caja()` a lecturas.
- **La memo retiene formas y crece la RAM** → `weakref` con callback. El script ya anota `rss_mb`
  por etapa: 510 MB tras el replay, 790 MB tras edición y payload. F1 lo compara.
- **La paridad falla en un caso rasante** que el prototipo no ejercitó → dos rectas y una distancia
  mínima a los cortes; si dudan, el clasificador de siempre. Más los tests con aristas y vértices.
- **cProfile engaña con OCCT** → las cifras de F1–F4 salen de `process_time` por etapa y del
  conteo por llamador, no del perfil.
- **Medir con la PC cargada** → antes/después en la misma sesión y con `process_time`, como en
  puerta-rapida.

## Bitácora

### F0 (2026-10-30)

Escritorio (i7-9700K, 8 hilos, 32 GB). `.apolo` final de la lavadora (723 sólidos, 1477
comandos: 393 `drill_hole`, 291 `fasten`, 139 `insert_component`, 100 `run_script`, 40
`join_bolted`…), cargado offline. Dos a cuatro medidas a la vez. El replay y la edición dieron lo
mismo con y sin perfilador (365–373 s): el tiempo está en C++.

| etapa | pared s | CPU s | cajas (n / s) | nota |
|---|---|---|---|---|
| replay frío | 365–369 | 326–330 | 22 669 / 304 | `_en_camino` 19 874 cajas / 290 s; `join_bolted` 40 × ~7,6 s = 305 s (83 %); `drill_hole` 28 s; `run_script` 27 s de pared (4,5 de CPU: el worker) |
| replay por tercios del log | 46 · 190 · 132 | | | la escena crece 284 → 508 → 723 |
| `_snapshot` antes de editar | 0,01 | | | |
| editar `c86` (`run_script`, pos. 117; 1259 re-ejecutados) | 326–349 | 325–328 | 22 573 / 292 | |
| `scene_payload` tras editar | 23–35 | 29–33 | 723 / 7 | 22 MB; la segunda, 0,01 s (malla en caché) |
| `to_apolo_bytes` · `geomcache.pack` · `undo` | 0,01 · 0,8–1,0 · 0,1–0,5 | | | blob 16,6 MB |
| interferencia global | 23–27 | 26–27 | 624 / 6,9 | 624 sólidos, 371 parejas |
| interferencia acotada `c53,c88` | 7–9 | 7,3 | 624 / 6,9 | 6 parejas |
| `structure_rules` (520 reglas) | 46–59 | 45–46 | 22 371 / 33,6 | `mass._bbox` 21 s · `vigas_rules._caja` 7,1 · `contacto` 5,6; `VolumeProperties` 9 s |
| lints (`predelivery_lints`) | 93–148 | 92–94 | 2819 / 6,4 | `agujeros_atribuidos` 93 s; los otros tres lints < 0,1 s |
| `delivery_check` (`delivery_inputs` + `delivery_report`) | 209–279 | 203–208 | 29 007 / 65,6 | lints 102–123 · poses 48–78 · uniones que tocan 26–41 · interferencias 18 · acceso 14; VERDE |
| puerta sin gravedad ni marcha | 1833 | 1613 | | `sobrantes` 1025 · `fuentes.mecanica` 315 · `entrega` 239 · `fuentes.seguridad` 129 · `fabricabilidad` 59 · `hechos` 38 |
| puerta sin sobrantes (abierta en caliente) | 670 | 668 | 61 032 / 167 | `interference_report` 42 s · `vigas_rules._caja` 21 · `calidad_agujeros._caja` 19 · `process._sorted_dims` 14 · `contacto` 22 |
| `sobrantes` (`medir_sobrantes.py --sin-perfil`) | 983 | 958 | | 172 candidatas (104 sobran, 68 necesarias, 2 vueltas): codo 380 · apoyo 375 · ingeniería 181 · rectas 45 |
| puerta completa sin gravedad ni marcha (abierta en caliente) | 1569 | 1571 | 155 329 / 299 | `sobrantes` 913 · `fuentes.mecanica` 252 · `entrega` 222; `vigas_rules._caja` 75 722 cajas / 152 s, casi todas en la ingeniería de cada candidata |

Ronda 4 (`rondas/correccion4.apolo`: 630 sólidos, 1319 comandos, 26 `join_bolted`), mismo
script: replay 241 s (cajas 12 423 / 193 s, el 80 %), estructura 42 s (cajas 31 s), lints 96 s
(`agujeros_atribuidos` 96 s), `delivery_check` 189 s (cajas 62 s). Entre las dos rondas, las cajas
del replay crecen con `join_bolted` × piezas (12 423 → 22 669) y el resto casi no se mueve.

Dentro de `agujeros_atribuidos` (105 s): 139 piezas medidas, y 4 «Resguardo de toma de soplador»
(170 caras planas, 248 caras) hacen el 98 %, 23–24 s cada una. En una de ellas, `colisos_de` =
23,5 s: 225 llamadas a `Rayos.dentro` = 23,4 s, `abertura` 0. La banda modular (166 caras planas)
cuesta 3,5 s, pero la medida la salta por ser banda. Una segunda corrida con otro `_Medidor` vuelve
a costar 105 s: nada se reutiliza.

Prototipos (fuera del repo): D1, replay frío con caja memoizada, 78,8 s de pared y 723/723 piezas
y los fijadores iguales. D2, paridad 1,7 s contra 97,9 s con 0/900 distintos; clasificador
cargado una vez, 47,4 s, 900/900 iguales y 0/600 distintos al azar.

Causa de los «1–3,5 h» por edición: offline la edición cuesta ~6 min (replay + payload). El resto
no es cómputo de la edición. Es, por inferencia, la cola de `STATE_LOCK` detrás de lecturas
huérfanas (`/api/checks` ~160 s y `delivery_check` ~210–280 s, cortadas a los 120 s y
reintentadas) y de la puerta (~30 min con el lock). No lo medí en la API: F3 lo verifica por
E2E.

### F1 (2026-10-30)

`kernel/caja.py::caja(shape)`: la `BoundBox` de `bounding_box()` con memo por `id(shape)`,
`weakref` con callback y acierto validado por `is` de la forma, `wrapped` y `TShape` más
`Location.IsEqual` contra la copia guardada (`w.Location()` ya devuelve copia; `TopLoc_Location`
no tiene constructor de copia en OCP). En el acierto llama a `BRepTools.Clean` y devuelve una
`BoundBox` nueva (copia del `Bnd_Box`): quien la recibe no ensucia el memo. Sin lock propio: el
dict es atómico bajo el GIL y toda carrera da un fallo, nunca una caja ajena. Migrados SÓLO los
llamadores de D1 (`_en_camino`, `_exec_drill_hole`, `interference_report`, `mass._bbox`,
`vigas_rules._caja`, `contacto._toca_caja` y `_caja_comun`, `calidad_agujeros._caja`,
`process._sorted_dims`, `calidad_seguridad._caja`, `mesh.bbox_payload`);
`tests/test_caja_memo.py` les impide volver a `.bounding_box()`. `drill_hole` cambió de huella y
no de versión (misma geometría): sólo la huella en `test_contrato_comandos.py`. Sin
`GEOM_CACHE_EPOCH`.

Lavadora final, escritorio, misma sesión. Antes = `main` (ad8b1a6) en el checkout principal; las
tres corridas en paralelo (cada una de un hilo), por eso manda el CPU:

| etapa | antes pared / CPU s | F1 pared / CPU s | cajas que se calculan (n / s) |
|---|---|---|---|
| replay frío | 347,7 / 322,7 | 79,6–80,2 / 61,0–62,6 | 1167 / 19,6 (antes 22 669 / 304) |
| editar `c86` (1259 re-ejecutados) | 326–349 (F0) | 53,8 / 59,1 | 1105 / 19,2 |
| `scene_payload` tras editar | 23–35 (F0) | 15,6 / 21,9 | 7 / 0,0 |
| interferencia global · acotada `c53,c88` | 23–27 · 7–9 (F0) | 15,9 · 0,27 | 6 · 0 |
| `structure_rules` | 46–59 (F0) | 15,2 / 15,1 | 18 021 / 2,9 (caras y aristas de `contacto`, que no se repiten) |
| lints (`agujeros_atribuidos`, F2) | 93–148 (F0) | 82,7 / 82,2 | 2304 / 0,2 |
| `delivery_check` | 209–279 (F0) | 140,3 / 145,6 | 20 145 / 8,8; VERDE como antes |

- **Igualdad** (método del prototipo, contra el replay de `main`): 723/723 piezas iguales (nombre,
  comando, volumen a 1e-6, caja a 1e-6, n.º de caras), los 649 `fasteners` iguales y 0
  suprimidos en los dos.
- RSS tras el replay: 513 MB (F0: 510); 790 MB tras edición y payload, como en la F0.
- Gate: replay ≤ 120 s ✔ (80), editar `c86` ≤ 120 s ✔ (54), `checks_estructura` ≤ 20 s ✔ (15).
  `scripts/testigos.py --en-proceso`: los cuatro IGUAL, sin re-congelar.
- Lo que queda del replay (~60 s de CPU): las cajas que sí cambian (19,6 s: la pieza recién
  taladrada), `drill_hole`, `run_script` y las booleanas de `join_bolted`; fuera de este plan.

### F2 (2026-10-30)

- **D2** (`kernel/rayo.py`): `Rayos.estado(p)` cuenta los cortes de dos rectas oblicuas enteras
  (t ∈ [−L, L], L desde una caja holgada) con el `IntCurvesFace` ya cargado. Una recta es limpia
  si ningún corte está sobre la frontera de su cara (`State` ≠ IN: arista o vértice), ninguno es
  tangente, ninguno cae a < 1e-4 del punto ni de otro corte y las transiciones de OCCT alternan
  entrar/salir empezando por entrar (un corte perdido o doble, o un sólido al revés, no alternan).
  Dos rectas limpias que coinciden deciden; una recta sin cortes sólo da «fuera» si el sólido está
  bien orientado (una recta por el centro de su caja empieza entrando). Si no, el
  `BRepClass3d_SolidClassifier` cargado una vez (`Load` + `Perform`, tolerancia 1e-6). Lo usan
  `dentro`, `tramos` y `Filtro._alguno_dentro` (un `Rayos` por sólido en el `_datos` de cada forma);
  `calidad_extremos._dentro_de` guarda su `Rayos` por sólido entre las consultas de un extremo (antes
  armaba uno por punto). Una regla en `kernel/CLAUDE.md`.
- **D3** (`services/calidad_agujeros.agujeros_de_corrida`): `agujeros_de` por `memo_corrida.por_forma`
  (`is`), con el mismo `wrapped` y su `Location` (`move`/`locate` en sitio miden de nuevo); cada
  llamada recibe copias de los dicts. Fuera de una corrida, como siempre.
- Tests: `tests/test_rayo_paridad.py` (estado igual al clasificador por consulta en caja, caja
  girada, tubos redondo y rectangular, chapa con ventanas, hueco cerrado, esfera, pieza taladrada y
  los sólidos de `mensula_atornillada`: 300 puntos al azar + vértices, medios de arista, centros de
  cara y a ±1e-7, ±1e-5 y ±0,3 de cada cara; frontera, sólido al revés, rectas que difieren,
  intersector que falla; el memo por `is`, movida en sitio, copia que se ensucia y el documento con
  una pieza cambiada). Sin versión de executor ni `GEOM_CACHE_EPOCH` (misma salida), sin
  `VERSION_REGISTRO`.

Lavadora final, escritorio, abierta en caliente (`final.geom` de la F0), en la misma sesión. Antes
= el árbol de la F1 (5154d65) exportado aparte; las corridas en paralelo (de a 4, cada una de un
hilo): manda el CPU.

| etapa | antes (F1) CPU s | F2 CPU s | igualdad |
|---|---|---|---|
| `agujeros_atribuidos` (lint «barreno sin perno») | 108,4 (con la carga del catálogo) · 103,2 dentro de los lints | 3,4 (`medir_maquinas_grandes.py`) | 57 KB de salida IGUAL |
| `/api/checks` lints | 103,2 | 3,3 | IGUAL |
| interferencia global | 19,8 | 17,8 | IGUAL |
| `delivery_check` (sin gravedad) | 171,6 (lints 107,4) | 65,6–69,2 (lints 3,7) | IGUAL, VERDE |
| puerta sin gravedad, marcha ni sobrantes | 595,4 (`entrega` 210 · `fuentes.mecanica` 266) | 260,8 (`entrega` 90 · `fuentes.mecanica` 23) | 42 ítems IGUALES |
| puerta completa sin gravedad ni marcha | 1220,7 (`sobrantes` 692 · `fuentes.mecanica` 256 · `entrega` 206) | 889,2 (`sobrantes` 714 · `fuentes.mecanica` 22 · `entrega` 84) | 42 ítems IGUALES |

La igualdad compara la salida entera (`delivery_report`, los lints, `interference_report`, los
insumos de `agujeros_atribuidos` y `evaluar` de la puerta con su evidencia), sin los campos de
tiempo (`ms`, `ms_*`). Gate: `lint_agujeros_atribuidos` ≤ 10 s ✔ (3,4), `entrega` ≤ 90 s ✔ (66–69),
puerta sin sobrantes ≤ 300 s ✔ (261). `scripts/testigos.py --en-proceso`: los cuatro IGUAL, sin
re-congelar. Lo que queda de la puerta es `sobrantes` (~700 s, intacto: codo y apoyo, F4 y la F2
de puerta-rapida) y `fuentes.seguridad` (~100 s).
