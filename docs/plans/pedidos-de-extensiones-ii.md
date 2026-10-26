---
estado: en curso
nota: contrato de Claude con el aval del titular (2026-10-24: «procede según tu criterio»); medido sobre `7d28ae5`; F1 mergeada (la serie Ø22 con `specs.agujero` de ficha leída, builder `mando_22` con cuello, la puerta corta redondo, epoch 8, `layout_tablero` v2) y F2 mergeada (`get_circuit(tablero=true)` resumido 29 → 2 KB en la piloto, `completo=true` para el panel entero; `comandos` en el resumen de `run_batch`; el ERC nombra el conductor por sus puntos); el aviso de la co-simulación también nombra el conductor por sus puntos (D-f de F2); pendiente chico: los acabados de color de los mandos Ø22 (D-a de F1)
descripcion: los pulsadores, pilotos y selectores Ø22 dicen su agujero y la puerta 3D los corta redondos; get_circuit con tablero pesa poco, run_batch resumido devuelve los ids creados y el ERC nombra cada conductor por sus extremos
---

# Los mandos Ø22 se montan en su agujero y las lecturas del circuito no ahogan al agente

## Estado y origen

Segunda tanda de pedidos que una extensión de entregables eléctricos anotó en su bitácora
mientras se implementaba (la primera: [pedidos-de-extensiones](pedidos-de-extensiones.md)). La
extensión no toca el núcleo: anota y sigue con un parche de su lado (una exención en su test de
papeles, una limpieza al pasar el texto al papel). Con el aval del titular para proceder según
criterio, el contrato lo escribe Claude y las decisiones quedan para vetar por número.

Los pedidos:

1. La perforación de un pulsador o piloto Ø22 sale «serie Ø22» y no «Ø22,5»: el catálogo sólo
   declara el agujero de la seta (`specs.agujero`). Usar el Ø22,5 de la seta para toda la serie
   sería deducir un dato. Y la puerta 3D corta los demás mandos por la huella de su caja.
2. El ERC nombra «conductor 13», que es un índice interno del modelo; en el esquema ese conductor
   es -T2:V → -M1:V1.
3. `get_circuit(tablero=true)` devuelve ~30 KB.
4. `run_batch` con `detail="summary"` no devuelve los ids creados (traba del modelador: tiene que
   leer la escena para saber qué id tomó cada cosa).

## Lo que hay hoy

- `core/apolo/library/data/123_mandos_puerta.yaml`: los pulsadores, pilotos y selectores Ø22 son
  `builder: box` de 30 × 50 × 30 (`tablero.puerta: {delante_mm: 12, detras_mm: 38}`), con
  `specs.diametro: "Ø22"` y sin `specs.agujero`. La seta (`93_mandos.yaml`) sí lo trae
  (`agujero: "Ø22,5"`) y tiene builder con zonas (`builders_mandos.seta_emergencia`: cabeza,
  cuello Ø22 por el panel, portacontactos detrás).
- `core/apolo/commands/tablero_geom.py:16` `huecos_por_ref`: la puerta corta un círculo sólo si
  `familia == "seta_emergencia"`, con el Ø de `builders_mandos.AGUJERO_D` (22,5) que le pasa
  `commands/tablero.py:132`; lo demás se corta por la huella de su caja (o por
  `tablero.puerta.recorte_mm`).
- Un mando que hoy es una caja de 30 × 30 que atraviesa la chapa NO entra en un agujero Ø22,5: el
  corte redondo pide que el mando tenga cuello.
- `core/apolo/library/electrico/erc.py:361`, `erc_seguridad.py:126` y `redes.py:164–182`: los
  mensajes dicen `conductor {i + 1} ({etiqueta})`.
- `core/apolo/mcp_server.py:123` `run_batch(detail="summary")`: «solo id/nombre» de los sólidos;
  no dice qué comando creó cada acción del lote.
- `core/apolo/tools/mcp_electrico.py:24` `get_circuit(tablero=true)` suma `tableros` entero (lo
  que el visor muestra: veredicto, ítems, largos, llenado).

## Decisiones (para vetar)

- **D1. El agujero es un dato de la ficha, no del código.** Cada ref de la serie Ø22 de
  `123_mandos_puerta.yaml` lleva `specs.agujero: "Ø22,5"` con la fuente de la línea de referencia
  (IEC 60947-5-1 no fija el Ø; el 22,3–22,5 es el de las fichas de la serie). La puerta corta un
  círculo para TODA ref con `specs.agujero` (la seta incluida), leído de su ficha: se borra el
  caso especial por familia y el `AGUJERO_D` pasado desde el comando deja de ser la fuente (queda
  en `builders_mandos` como default del builder).
- **D2. Un mando Ø22 tiene cuello, como la seta.** Un builder `mando_22` en `builders_mandos.py`
  con las mismas zonas que la seta de puerta (frente delante de la chapa: bisel del pulsador,
  maneta del selector, lente del piloto; cuello Ø22 por el panel; portacontactos detrás) y las
  anclas `montaje` y `agujero`. Las medidas de relleno salen de `tablero.puerta`
  (`delante_mm`/`detras_mm`) y del orden de la línea de referencia, con `cotas_verificadas: false`
  como hoy. Sin el cuello, un corte redondo dejaría la caja de 30 × 30 cruzando la chapa: la
  interferencia que la puerta de entrega rechaza.
- **D3. Cambia la geometría con los mismos params → bump de `GEOM_CACHE_EPOCH`** (YAML del catálogo
  y un builder nuevo: no se puede acotar a un executor). La `version` de `layout_tablero` (el
  comando que arma la puerta) sube además, porque cambia su código.
- **D4. El ERC nombra el conductor por lo que se lee en el esquema.** El texto lleva sus extremos
  («-T2:V → -M1:V1») y su etiqueta si la tiene; el índice sale del texto y queda en un campo
  estructurado del problema (para quien lo use como clave). Una sola función en `redes.py` arma
  ese nombre; `erc.py` y `erc_seguridad.py` la usan.
- **D5. `get_circuit(tablero=true)` devuelve un resumen por tablero** (veredicto, conteos, lo que
  falla con su motivo) y el detalle entero sólo con un pedido explícito (`tablero="completo"` o un
  parámetro equivalente que decida la fase). El REST no cambia de forma: la poda es de la tool,
  que es la que el agente paga en contexto. Meta: ≤ 1/4 del tamaño de hoy en la piloto.
- **D6. `run_batch(detail="summary")` devuelve el id de comando de cada acción** (en orden, con la
  `$k` resuelta), además de lo que hoy devuelve. Lo mismo `edit_batch` si aplica. Es un dato que
  el log ya tiene: no hay que leer la escena.
- **D7. El golden MCP se re-congela a propósito** en la F2, con el diff mirado (las firmas y los
  docstrings que cambian), no a ciegas.

## Alternativas descartadas

- **Copiar el Ø22,5 de la seta a la serie en código** (`AGUJERO_D` para todo `diametro: "Ø22"`):
  deducir un dato es lo que la extensión se negó a hacer; el dato va en la ficha.
- **Cortar redondo y dejar la caja**: la caja cruza la chapa; la puerta de entrega lo marcaría
  como interferencia.
- **Partir `get_circuit` en dos tools**: el MCP es fino; un parámetro basta.

## Fases

- **F1 — La serie Ø22 con su agujero y su corte redondo** (`library` + `commands`, M). Ficha
  (`specs.agujero` con su fuente), builder `mando_22` con zonas y anclas, `huecos_por_ref` por
  ficha, bump de epoch y de la `version` del comando. Verifica: test de que toda ref con
  `specs.agujero` sale círculo en la puerta; test de que el mando no interfiere con la chapa en la
  piloto (`tests/data/tablero_piloto.json`); la colocación de la piloto sigue entrando en el
  500 × 400; suite completa.
- **F2 — Lecturas livianas y el ERC que nombra el conductor** (`library/electrico` + `tools`/`api`,
  M). D4–D7. Verifica: tamaño de `get_circuit(tablero=true)` en la piloto antes/después en la
  bitácora; `run_batch(detail="summary")` con `$k` devuelve los ids; los mensajes del ERC de la
  piloto sin «conductor N»; golden MCP re-congelado con su diff; suite completa.

F1 y F2 no comparten archivos: van en paralelo.

## Lo que este plan NO hace

- No verifica las cotas de los mandos con el fabricante (siguen `cotas_verificadas: false`).
- No cambia los papeles de la extensión: con el dato en la ficha, ella lo lee sola.
- No toca el REST de `/api/circuit` salvo lo que D6 necesite.

## Riesgos

- **Proyectos guardados con mandos Ø22 regeneran otra geometría** (es el propósito): el epoch lo
  invalida; un test congelado de la piloto que mida volúmenes se re-congela con el porqué.
- **Un agente que lee `conductor N` como clave**: D4 deja el índice en un campo estructurado.

## Bitácora

### F1 — La serie Ø22 con su agujero y su corte redondo

**D1.** Las 8 refs Ø22 de `123_mandos_puerta.yaml` (3 pulsadores, 2 selectores, 3 pilotos) llevan
`specs.agujero: "Ø22,5"`. El dato es de una ficha LEÍDA, no de la seta: las fichas de producto
Harmony XB5AA31, XB5AD21 y XB5AVB3 (schneider-electric.cn, bajadas el 2026-10-25) dan «安装直径
22.5 mm» (diámetro de montaje) y su hoja de recorte, que vale para «Pushbuttons, Switches and Pilot
Lights», «Ø22.5 mm recommended (Ø22.3 0+0.4)» y chapa de 1 a 6 mm. Va en la `fuente` compartida de
la serie (`&fuente_xb5`), con las fichas que se leyeron; las cotas siguen `cotas_verificadas: false`.
`huecos_por_ref(refs, catalogo)` corta un círculo para TODA ref con `specs.agujero`, con el Ø de
su ficha (`ficha_tablero.agujero_mm`, acepta coma o punto); se borró el caso por familia y
`commands/tablero.py` ya no pasa `AGUJERO_D` (queda en `builders_mandos` como default de
referencia).

**D2.** Builder `mando_22` en `builders_mandos.py` (312 líneas): marco de la seta de puerta
(origen en la cara de apoyo, +Z al operador, apoyo −Z en `APOYO_POR_FAMILIA`), bisel Ø30 × 8 y
delante el botón o la lente Ø24 o la maneta 8 × 24 hasta `delante`; cuello Ø22 por la chapa;
portacontactos `width` × `height` de z = −`panel_mm` (2, como la seta) a −`detras`. Anclas
`montaje` y `agujero` = las de la seta. La huella medida es la de la caja de antes (30 × 30 ×
(delante + detras): 50, 55 o 45), así que la colocación no cambia (`test_el_catalogo_da_lo_mismo_
que_el_fixture` sigue verde con el fixture congelado sin tocar). Volúmenes medidos: pulsador
40 625 mm³, selector 40 543, piloto 37 020 (la caja era 45 000 / 49 500 / 40 500).

**D3.** `GEOM_CACHE_EPOCH` 7 → 8 (motivo en `geomcache.py`) y `layout_tablero` v2 (su huella D11
no cambia: el cambio vive en `tablero_geom.py`).

- **D-a (vetable): el `mando_22` NO es ZONADO.** El verde, el azul y el ámbar no están en
  `apariencia.ACABADOS`, y sumarlos obliga a regenerar `ui/src/viewport/acabados.json` (fuera
  del alcance de la F1); un botón verde pintado de otro acabado engañaría. La pieza se ve de un
  acabado, como la caja de antes. Pendiente: los acabados de color de los mandos y sus `zonas`.
- **D-b: el loader verifica lo que el builder repite.** `delante`/`detras` son params del builder
  (lo parten) y también `tablero.puerta`: `ficha_tablero._puerta` rechaza que difieran. Y
  `verificar_agujero` rechaza al cargar una ref de puerta con `specs.agujero` y builder caja
  (`FAMILIAS_CAJA`): cruzaría la chapa del corte redondo. Regla en `library/CLAUDE.md`.
- **D-c: `panel_mm` 1–6 mm** (la «clamping thickness» de la ficha), no el 0,5–6 de la seta.
- **D-d: la seta no se tocó.** Su `specs.agujero` ya estaba; su ficha (XB5AS8445) no se releyó
  en esta fase. La misma hoja de recorte nombra las setas en su nota (2).
- **D-e: la v2 de `layout_tablero` entra en la firma de TODO compuesto** (`insert_project`,
  `create_belt_conveyor`, `create_roller_conveyor` llevan las versiones ≠ 1): con el bump del
  epoch el costo es el mismo (un replay frío por proyecto). `test_sin_el_comando_las_firmas_de_
  siempre` se ajustó a eso: la firma de un compuesto suma `layout_tablero@2` y nada más.

Tests: `tests/test_mando_22.py` (nuevo): toda ref con `specs.agujero` sale círculo con su Ø; el
agujero mal escrito no carga; una caja con agujero no carga; huella, origen y anclas de las 8
refs; por una chapa de 1,5 mm pasa sólo el cuello Ø22; en la piloto la puerta tiene 5 agujeros
redondos (S0, S1, S2, H1, H2; Q1 sigue en su recorte por la huella), ningún mando se mete en la
chapa (volumen común < 0,001 mm³) y el gabinete sigue siendo el TABLERO-5040. Cambiados:
`test_contrato_comandos.py` (layout_tablero v2, misma huella), `test_layout_tablero.py` (D-e) y
`test_colocacion_tablero.py::test_un_mando_de_puerta_sin_su_fondo_partido_no_se_coloca` (el
`mando_22` no es caja: sin `medir` no tiene cotas; el test le pasa la huella para seguir
probando lo mismo). Listas cerradas que suman lo nuevo: `test_catalog_cadenas.py` (las anclas por
familia suman `mando_22`) y `test_version_comandos.py` (la firma de `insert_project` suma
`layout_tablero@2`). Ningún test congelado de volúmenes cambió. Suite completa (`-n auto`, en el
worktree) exit 0; `ruff check core tests scripts` limpio.

### F2 — Lecturas livianas y el ERC que nombra el conductor (2026-10-25)

Hecho (base `cfd16b8`):

- **D4.** `library/electrico/redes.nombre_conductor(cond)` es el único nombre legible de un
  conductor: sus puntos en el orden de cableado y, si la tiene, su etiqueta entre corchetes (el
  hilo del cable y el nombre de la red): «-T2:V → -M1:V1 [-W1.2]». Lo usan los problemas de
  referencias de `redes.py`, «color del conductor» de `erc.py`, «PE en cadena» de
  `erc_seguridad.py`. Medido antes: `Conductor.etiqueta` ya era `" → ".join(puntos)`, así que
  el texto viejo era «conductor 13 (-X0:1 → … → -X0:2)»; ahora es «conductor -X0:1 → … → -X0:2
  [PE]». El número (1-based, el orden de `modelo.conductores`, el mismo que decía el texto) queda
  en `Problema.conductor` y en la clave `conductores: [n]` de la fila del ERC (sólo en las filas
  que nombran conductores: sin ellas, la fila es byte-idéntica). `Problema` lo lee sólo
  `erc._referencias`.
- **D5.** La tool `get_circuit` gana `completo: bool = False`. Con `tablero=true` (y sin
  `completo`) devuelve `{tableros: [resumen por tablero], resumen, seguir}`; con `completo=true`,
  el JSON del REST tal cual (circuito + paneles enteros). Sin `tablero`, lo de siempre. El REST
  no cambia. La poda (`tools/mcp_electrico.resumen_tableros`) sólo ELIGE claves del panel de
  `services/tablero_panel.panel`: el veredicto y los ítems siguen siendo del servicio.
- **D6.** `tools/recibo.job_result` suma `comandos` con `detail="summary"`: los
  `affected_command_ids` que el API ya devolvía, en el orden del lote (`execute_many` devuelve
  `created` en orden; `edit_many`, los editados en el orden de `edits`), así que `$k` =
  `comandos[k-1]`, también para lo que no crea sólidos (set_variable, fasten, add_device). Vale
  para toda mutación por job con `summary` (run_command da un id); sin `summary`, nada cambia.
- **D7.** Golden re-congelado mirando el diff: cambian las descripciones de `run_command`,
  `run_batch` y `get_circuit` y el schema de `get_circuit` (+`completo`); en las llamadas, las tres
  salidas `summary` de `run_batch`/`run_command` suman `comandos`, «circuito con el tablero
  armado» pasa a ser el resumen (el falso no trae tableros: `tableros: []`) y entran dos casos
  nuevos con un panel canónico (`_PANEL`): «resumido» (incluye un tablero sin armar, que pasa
  tal cual) y «completo».

Decisiones propias (vetables):

- **D-a. La forma del pedido explícito es un parámetro `completo: bool`**, no `tablero="completo"`:
  `tablero` sigue siendo booleano (un cliente que manda `true` no se rompe) y el schema no mezcla
  tipos. `completo=true` implica el tablero.
- **D-b. `tablero=true` resumido NO trae las listas del circuito** (dispositivos, redes,
  conductores, cables, `neumatica`), sólo su `resumen` de cuentas y un `seguir` que dice cómo
  pedirlas: el circuito solo ya pesa 17,7 KB en la piloto, más que la meta entera; el agente lo
  pide con `get_circuit()` cuando lo necesita.
- **D-c. El resumen de un tablero** = ubicación, comando, `gabinete` {ref, medidas_mm},
  `veredicto`, `cuentas` {aparatos, conductores, canaletas, cables_de_campo}, `items` y `bien`
  sin `piezas` ni `decimales` (son de la cámara y del formato del visor) y sin `conductores`
  vacíos. Los `conductores` de un ítem (ids de comando) y su `detalle`/`tecnico` (el motivo)
  quedan.
- **D-d. La etiqueta va entre corchetes** («[-W1.2, L1]»), no entre paréntesis: dentro de «PE en
  cadena» el nombre ya va entre paréntesis y quedaban anidados.
- **D-e. La fila del ERC lleva sólo el número** en `conductores`, no el id del comando: es lo que
  pidió D4 (la clave de quien leía «conductor N»); el id está en `get_circuit` junto a los mismos
  puntos.
- **D-f. El aviso de la co-simulación queda como estaba**: `services/cosim_red.py` también dice
  «conductor N (…)» cuando un punto no resuelve (el mismo hallazgo que el ERC ya nombra bien), pero
  está dentro de la huella de `tests/test_cosim_epoch.py`: cambiarlo es otra decisión (huella sin
  subir el epoch) fuera del alcance de D4. Pendiente chico: una línea con `nombre_conductor` y la
  huella al día.

Medido en la piloto (`tests/data/tablero_piloto.json` armada, bytes UTF-8 del JSON):

| lectura | antes | después |
|---|---|---|
| `get_circuit(tablero=true)` | 29 045 | 1 991 (6,9 %) |
| `get_circuit(tablero=true, completo=true)` | — | 29 045 (= REST) |
| `get_circuit()` | 17 672 | 17 672 |

Del total de antes: circuito 17,7 KB (dispositivos 6,9; conductores 6,1; redes 3,7) y
`tableros` 11,4 KB (de ellos, el detalle de conductores del panel 5,6).

El ERC de la piloto ya no dice «conductor N»: las tres filas de «PE en cadena» nombran
«conductor -X0:1 → -T1:PE → -T2:PE → -K1:PE → -X0:2 [PE]» con `conductores: [13]`.

Tests: `tests/test_lecturas_livianas.py` (nuevo: nombre, color, hilo de cable, referencia rota,
PE en cadena, piloto, `get_circuit` resumido/completo/sin tablero por la tool real contra la API
en proceso, `run_batch` y `edit_batch` con `summary` y sin él). Ningún test existente cambió.
