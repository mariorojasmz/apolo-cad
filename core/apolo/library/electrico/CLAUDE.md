# Eléctrico (`core/apolo/library/electrico/`)

La ficha eléctrica de una ref, el ERC y el tablero 3D (colocación, ruteo, cables), todo puro.
Lo de catálogo y BOM en general: [library](../CLAUDE.md); los modelos de la co-simulación:
[cosim](../../cosim/CLAUDE.md).

## La ficha de una ref

- **Nunca una cifra de memoria**: cada bloque con datos lleva `fuente` (el documento leído) o la
  clave en `a_confirmar` SIN valor. La COMPLETITUD se valida al cargar, con error.
- `electrico.modelo` (V8.3 D7): `tipo` elige el modelo de la co-simulación; cada cifra cita su
  norma o «criterio de diseño» en el YAML y lo que fija el instalador es un rango [mín, máx]
  (AJUSTE obligatorio). Reglas: [cosim](../../cosim/CLAUDE.md).
- `electrico.datos` (`ficha_datos.py`): lo que lee quien VERIFICA (poder de corte `{U_V: kA}` con
  la clave = tope del rango de la ficha, `T_max_C`), FUERA de `modelo`: no vence firmas ni es
  ajuste. `REQUERIDOS` por tipo + `T_max_C` en toda ref de tablero.
  [plan](../../../../docs/plans/datos-de-corte-y-acometida.md)
- `electrico.direcciones` (`ficha_direcciones.py`): cómo llama el FABRICANTE a cada E/S, fuera de
  `modelo`. Opcional pero COMPLETO (todo borne que el ST alcanza por dirección), con `fuente` del
  manual o «direcciones» en `a_confirmar`. El ST de Apolo sigue con `%IX`/`%IW0`.
  [plan](../../../../docs/plans/plc-en-el-lazo.md) (D3)
- `electrico.puertos` (`ficha_puertos.py`): conectores de DATOS de serie (`rj45`), fuera de
  `bornes` y de `modelo`: ni la red, ni el ERC, ni la firma los ven (el `puertos` del
  `Dispositivo` es el del aire). Una ref gana puerto sólo si su línea de referencia lo trae de
  serie. [plan](../../../../docs/plans/plc-en-el-lazo.md) (D12)
- `tablero:` (V8.5 A2–A4, `ficha_tablero.py`): cómo se MONTA (cara de apoyo, `puerta`, `acopla_a`,
  riel, canaleta, `bornes`). Lo leen la colocación y el ruteo, no el builder: agregarlo no es
  bump. Una ref de puerta nueva lo trae o la colocación la rechaza. Un aparato que va en un
  RECORTE de la puerta declara `tablero.puerta.recorte_mm` [ancho, alto] (sin él, la huella de su
  caja) y usa el builder `panel_puerta` (marco delante, cuerpo menor que el recorte: una caja entera chocaría con la
  chapa).
  [V8.5](../../../../docs/plans/V8.5-tablero-3d.md)

## Modelo y ERC

- **Un campo nuevo de `Dispositivo`** (`modelo.py`) obliga a decidir: entra a la firma de los
  escenarios (`EN_FIRMA` de `tests/test_firma_dispositivo.py`: vence todo resultado con tablero)
  o va a `services/escenarios.FUERA_DE_FIRMA` (no es física o sale de lo que el log ya firma).
  Quién mueve un bloque auxiliar es UNA regla, `acoples.py` (la lee la co-simulación; la
  colocación conserva su regla de montaje). [plan](../../../../docs/plans/pedidos-de-extensiones.md) (F2)
- ERC del camino de la protección (`erc_seguridad.py`, reglas en su docstring): «PE en cadena»
  por el grafo de conductores (un aparato es PASO si sacar su PE deja a otro sin tierra) y
  «canales del STO» por `modelo.STO_canales` (toda ref con `STO: true` lo trae; fuera de la firma:
  `services/escenarios.FUERA_DE_FIRMA_MODELO`). La categoría del lazo es de la OBRA: ajuste
  opcional `STO_categoria` del variador; sin ella, aviso; con 3 o 4, error.

## Tablero 3D: colocación, ruteo y cables

Los tres son PUROS y deterministas, con las reglas en el docstring del módulo y cada cifra en su
dataclass de criterio (sale en el resultado). Una regla nueva va ahí con su caso en el test:

| módulo | cifras en | test | lo que tiene que seguir dando |
|---|---|---|---|
| `colocacion*.py` (D2/D8) | `Reglas` → `Layout.supuestos` | `test_colocacion_tablero.py` | la piloto (`tests/data/tablero_piloto.json`) entra en el 500 × 400 |
| `ruteo.py` (D3/A8), `bornes_pos.py` (D4) | `Criterio` → `Ruteo.criterio` | `test_ruteo_tablero.py` | largos de placa de la piloto a ±5 % del ruteo a mano (`A_MANO`) |
| `cable_campo.py` (F4) | `CriterioCampo` | `test_cables_campo.py` | el cable del motor de la piloto, punto a punto contra el armado a mano |

- La cara de cada borne sale de la familia por `modelo.tipo` o de `tablero.bornes` de la ref,
  con su `fuente`.
- En la puerta, lo que pasa de una celda toma ⌈ancho/paso⌉ × ⌈alto/paso⌉ contiguas y va PRIMERO
  (`colocacion_puerta.bloque`).
- Todo lo del tablero es caja alineada (`armado.py`: del `Layout` a cajas, puerta en −Y;
  `recorrido_puerta.py`: el recorrido de la puerta): una pieza nueva del armado entra como `Caja`,
  o el recorrido no la ve. [V8.5](../../../../docs/plans/V8.5-tablero-3d.md)
