---
estado: en curso
nota: contrato de Claude con el aval del titular (2026-10-24: «procede según tu criterio»); medido sobre `7d28ae5`; F1 (la serie Ø22 con su agujero y su corte redondo) y F2 (lecturas livianas y el ERC que nombra el conductor) por implementar
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
