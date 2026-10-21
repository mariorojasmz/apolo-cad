---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: sin pendientes de código: F4 verificada por MCP (2026-10-21): la estructura de la piloto redeclarada con 27 órdenes en 2 llamadas, 264 uniones idénticas, sujeción, gravedad y puerta igual de verdes; la propuesta de `declare_structure` no sirve tal cual — en el hito H
descripcion: El agente declara de una vez cómo se une cada pieza repetida («cada eje a su larguero») y la detección automática ya no suelda cadenas a la guarda
---

# Declarar las uniones de las piezas repetidas en una sola orden

## Estado y origen

En la piloto (proyecto 2), `declare_structure` declaró tipos de unión falsos (cadenas soldadas a
la guarda, entre otros). Hubo que borrar 419 comandos (c105–c523) por `POST
/api/commands/remove` y declarar a mano 226 uniones con un script REST que expandía los ids de
patrón uno por uno (`c57_1`…`c57_19`). Fue la parte más cara del modelado. Mario preguntó
«¿tienes mejoras para el MCP?»; esta fue la 4.

## El problema / lo que hay hoy

- `fasten` une dos piezas; una máquina con 20 rodillos × 10 uniones = 200 `fasten`.
- La autodetección decide el TIPO por contacto: lo que gira y toca algo sale «soldadura».
- El patrón (`c57_k`) no se puede nombrar como conjunto en una unión.

## Decisiones (para vetar)

- **D1. `fasten` acepta PATRONES en `a` y `b`**: `a: "c57"` (raíz del patrón) + `b: "c9"` =
  una unión por instancia; `a` y `b` del mismo patrón se emparejan por índice (eje k ↔ tuerca k).
  Un solo comando en el log, que se expande al regenerar (sigue el patrón cuando cambia
  `n_rod`). Un log viejo no cambia: el modo nuevo sólo se activa con una raíz de patrón.
- **D2. La autodetección no suelda lo que gira**: una pieza con junta, o de catálogo de
  transmisión (cadena, piñón, rodamiento), nunca recibe `soldadura`; propone `contacto` o
  `perno` y lo marca `a_revisar`.
- **D3. `declare_structure` en modo propuesta**: devuelve la lista sin aplicarla (`aplicar:
  false` por defecto en el MCP); el agente la corrige y la aplica en un lote.

## Fases

- **F0 (S, sólo lectura)**: sobre una copia del proyecto 2 sin uniones, contar cuántas propone
  hoy la autodetección y cuántas son de tipo falso.
- **F1 (M, `commands` + `assembly`)**: D1 con tests (cambiar `n_rod` re-expande).
- **F2 (S, `assembly`)**: D2.
- **F3 (S, `api` + MCP + golden)**: D3.
- **F4 (S, verificación)**: redeclarar la estructura del proyecto 2 con < 30 órdenes.

## Lo que este plan NO hace

- No cambia `ground` ni la puerta de entrega.

## Riesgos

- Emparejar por índice patrones de distinto largo → error accionable con los dos conteos.

## Bitácora

### F0 (2026-10-19)

Sobre la piloto local: proyecto **74** (`transportador-rodillos-cadena-2m`, 341 comandos, 201
piezas; 224 `fasten` + 4 `ground` declarados a mano, más los 40 contactos que declara
`create_chain`). Leída en sólo lectura, copia del log sin `fasten`/`ground` y `detect_structure`
(lo que aplica hoy `declare_structure`):

- Propone 4 anclajes y **460 uniones: 444 soldaduras y 16 contactos**.
- **154 soldaduras tocan una pieza de catálogo que gira** (cadena o piñón); 12 de ellas son una
  cadena o un piñón soldados a una guarda (el síntoma que originó el plan).
- Contra las 264 uniones declaradas (224 + 40 de cadena): propone los 264 pares, pero **218 con
  tipo distinto** (160 soldadura→contacto, 44 soldadura→perno, 12 contacto→soldadura, 2
  contacto→perno): acierta el tipo en 46 de 264 (17 %). Suma además 196 pares que nadie declaró
  (194 soldaduras).

Medición repetible: `detect_structure(copia.scene)` sobre `Document.from_apolo_bytes(blob,
tolerant=True)` con el log filtrado; nunca se escribió en la base.

### F1 (2026-10-19)

`fasten` acepta CONJUNTOS en `a`/`b` (executor en `commands/exec_uniones.py`, schema en
`models_uniones.py`: salieron de `registry.py`/`models.py`, que bajan en el trinquete). Tests en
`tests/test_uniones_en_lote.py` (cambiar `n_rod` re-expande, deshacer, `.apolo`, conteos
distintos, log viejo).

Decisiones propias (vetables):

- **La raíz cubre las COPIAS** `{raíz}_{n}` del comando, no la fuente: el executor sólo ve la
  escena, no el log, y la fuente es otra pieza. Para todas, `'c11+c57'` (es lo que hizo a mano
  la piloto: `r0` usa `c11`, `r1…r19` usan `c57_k`).
- Gramática: término = pieza o raíz; `+` concatena (también piezas sueltas: `c84+c85` ↔
  `c756+c757` empareja patas con placas); corte a la Python sobre el conjunto ENTERO, con
  paréntesis si hay `+` (`(c15+c61)[::2]`): sin el corte no se expresan los piñones de la
  piloto, que alternan entre dos patrones (`c16+c62` ↔ `(c15+c61)[::2]`, `c63+c64` ↔
  `(c15+c61)[1::2]`). Cuenta para la F4: los 10 tipos de unión por rodillo = 11 órdenes, y las
  24 sueltas se agrupan con `+`.
- Nombre de cada unión expandida `{name}[k]` (k desde 0; los corchetes no caben en un nombre
  de usuario: sin colisiones) y el dict lleva además `conjunto` e `indice`. Dos piezas sueltas
  registran el dict de siempre, byte-idéntico (test).
- `fasten` **sigue en v1**, sólo cambia la huella: con los params de un log viejo el resultado
  es idéntico, y una raíz en `a`/`b` antes dejaba un fijador colgante que el regenerate estricto
  rechaza (nunca llegó a una caché).
- Límites: una raíz sin copias (count = 1) no se distingue de un id inexistente — sola cae al
  fijador colgante (error del regenerate), en un conjunto da error accionable; un patrón cuyo
  count baja a 1 rompe el regenerate. `pattern_group` (`{cmd}_{i}_{k}_{sufijo}`) no es raíz: el
  error nombra sus piezas.

### F2 (2026-10-19)

`detect_structure(..., joints=None, catalog=None)` no propone `soldadura` con una pieza que gira
(`assembly/autodetect.py::piezas_que_giran`): catálogo de `transmision`, `rodamientos`,
`rodillos` o `tambores`, o hija de una junta móvil (y lo que cuelga de ella por juntas `fija`).
La baja a `contacto` con `a_revisar: true` y el motivo en `reason`. Se eligió `contacto` y no
`perno`: es la propuesta más débil y el agente decide.

En la piloto: **0 soldaduras con pieza que gira** (las 154 pasan a contacto + `a_revisar`);
quedan 198 tipos distintos de lo declarado, sobre todo tapas, ejes y tuercas, que no son de una
categoría giratoria (los rodillos de la piloto son tubo `TUBOR-2` + revolve). Para la **F3**:
`/api/assembly/declare` hoy pasa sólo la escena — debe pasar `joints=S.doc.joints` (la parte
del catálogo ya rige sin cambios) y conservar `a_revisar` en la propuesta.

### F3 (2026-10-19)

`POST /api/assembly/declare` acepta `{aplicar}` (sin cuerpo = `true`: la UI y la guardia del
documento siguen igual). La propuesta y lo aplicado salen de `services/estructura.py::
propuesta_estructura`, que pasa `joints=doc.joints`; con `aplicar=false` no muta y devuelve
`{aplicar, n_grounds, n_fasteners, n_a_revisar, acciones, resumen}`. La tool
`declare_structure(aplicar=False, completo=False)` sale de `mcp_server.py` (trinquete: 1421 →
1406) a `tools/estructura.py` con `registrar(mcp, api)`; en el golden pasa al final de
`list_tools()` (orden de registro) y gana dos casos (aplicar, lista omitida). Tests en
`tests/test_declarar_propuesta.py`.

Decisiones propias (vetables):

- Las acciones tienen el formato de `run_batch`; `a_revisar: true` y `motivo` (el `reason`
  entero) van FUERA de `params`: el lote las ignora y el agente puede reenviar la propuesta tal
  cual o corregida (test).
- La nota de una unión a revisar empieza con `a revisar: ` (cabe en los 120 de `nota`): aplicada
  sin corregir, la marca sobrevive en `get_connections`. Aplicada, la respuesta suma
  `a_revisar` [nombres] sólo si hay alguna (si no, el payload es el de siempre).
- `resumen`: las uniones agrupadas por (tipo, revisar, raíz de cada lado), de mayor a menor,
  con un `ejemplo` nombrado; la raíz es la regla de `exec_uniones` (copia `{cmd}_{n}` de su
  comando), así cada fila es candidata a UN `fasten` por conjunto. No se arma el `fasten`
  sugerido: el resumen no sabe si la fila cubre TODAS las copias del patrón (lo verifica el
  agente; la F4 dirá si hace falta).
- Con más de 60 acciones la tool omite la lista (`acciones_omitidas` + `seguir`) y deja el
  resumen; `completo=true` la trae entera (la piloto proponía 460 uniones ≈ 100 KB). El recorte
  es del cliente MCP: la API devuelve siempre todo.
- Sigue en `CHAT` como `muta` (con `aplicar=true` cambia el documento).

### F4 (2026-10-21): verificación por MCP — PASA

**Cómo** (ola 5, 2026-10-21): una sesión NUEVA `claude -p --model opus` con sólo las tools `apolo-cad` + lectura del repo, contra una API de la flota en :8100 con el proyecto 78 (copia de la piloto 74). Una sesión para cinco verificaciones: 53 min, 114 turnos, USD 5,28.
- 27 órdenes (< 30): un `remove_commands` de 228 ids (~11 KB) y un `run_batch` de 26 (4 `ground`, `fasten` por conjuntos `c11+c57`, `(c15+c61)[::2]`…), aceptado a la primera.
- Después: 264 uniones con los mismos tipos y el mismo emparejamiento piñón ↔ buje; `check_assembly` 201/201, `gravity_test` 0 caen, `delivery_check` VERDE.
- `declare_structure`: la propuesta (420 uniones, 114 a revisar, ~38 KB) suelda eje ↔ larguero, tuerca ↔ larguero y guarda ↔ motorreductor, y deja pata ↔ larguero como contacto; ya no suelda piñones ni cadenas. Fricción: `run_batch` no dice cuántas uniones expandió; `get_connections` 57–70 KB sin filtro; `check_assembly` lista los 201 ids dos veces. Hito H.
