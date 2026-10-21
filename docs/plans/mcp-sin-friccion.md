---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: contrato escrito el 2026-10-21 (hito H de docs/hitos.md) con la fricción que midieron cinco verificaciones por MCP; nada implementado
descripcion: El agente gasta menos contexto y se equivoca menos por MCP: respuestas cortas, errores que dicen cómo seguir y propuestas de estructura que no sueldan lo que se atornilla
---

# El agente trabaja por MCP sin respuestas gigantes ni errores mudos

## Estado y origen

Hito H de [docs/hitos.md](../hitos.md). Mario delegó en Claude el orden de los hitos. La fricción
sale de sesiones NUEVAS de Claude que trabajaron sólo por MCP contra la flota, el 2026-10-21:
- la ola 5 sobre la piloto: [cirugia-liviana](cirugia-liviana.md) F3,
  [perfiles-con-acuerdo](perfiles-con-acuerdo.md) F4,
  [acceso-de-herramienta](acceso-de-herramienta.md) F3,
  [flecha-de-bastidor](flecha-de-bastidor.md) F3 y [uniones-en-lote](uniones-en-lote.md) F4;
- el transportador de 3 m de [plantilla-rodillos-cadena](plantilla-rodillos-cadena.md) F3.

Cada punto de abajo tiene la llamada exacta en la bitácora de su plan. El contexto es el recurso
escaso del agente (raíz § MCP: «Escala»): cada KB de respuesta se paga en cada llamada siguiente.

## El problema / lo que hay hoy

| # | qué | medido |
|---|---|---|
| 1 | `undo` devuelve el brief de TODA la escena (`brief.py::brief_paso`) | 52,7 KB en la piloto; borrar con `remove_commands` cuesta 0,6 KB |
| 2 | `run_batch(detail="summary")` devuelve todos los sólidos | 40 KB (297 sólidos) |
| 3 | `check_assembly` lista los ids sujetos dos veces | 7–25 KB |
| 4 | `get_connections` no se puede filtrar | 57–70 KB |
| 5 | `engineering_check` saca una regla por unión apernada; sólo las vigas se agrupan | 70 KB: el agente tuvo que filtrar con Grep |
| 6 | `get_command_schemas("insert_component")` trae el enum entero del catálogo | 11 KB |
| 7 | `check_interference()` global corta a 400 parejas sin decir cuántas faltan | `truncado: true` sin conteo |
| 8 | `remove_commands` sin dependientes da 400 y no sugiere `con_dependientes=true` | — |
| 9 | `run_batch` no dice cuántas uniones expandió un `fasten` por conjuntos | hubo que leer `get_connections` (#4) |
| 10 | `render_view(isolate=[nombre de subgrupo de la plantilla])` da «ningún id existe» | los subgrupos que documenta `create_roller_conveyor` no resuelven como grupo |
| 11 | `render_view(show_axes=true)` encuadra también el origen | la pieza queda diminuta |
| 12 | `delivery_check` no informa su tiempo | ~53 s sin dato |
| 13 | la propuesta de `declare_structure` suelda eje ↔ larguero, tuerca ↔ larguero y guarda ↔ motorreductor, y deja pata ↔ larguero como contacto | 420 uniones, 114 a revisar, ~38 KB: no sirve tal cual |

## Decisiones (para vetar)

- **D1. Toda respuesta que lista sólidos o uniones tiene un modo corto por defecto.** El modo
  corto da un conteo, un resumen por grupo y los ids sólo de lo que CAMBIÓ o de lo que FALLÓ. El
  detalle va a pedido (`detail="full"`, `ids=…`, paginado). Aplica a 1, 2, 3, 4 y 5. `undo` y
  `redo` devuelven el diff del paso, como `remove_commands`. Cambia lo que ve el cliente MCP:
  golden re-congelado y revisado.
- **D2. Filtros donde hoy no hay.** `get_connections(ids=, kind=, resumen=)` y
  `engineering_check(grupo=, solo_fallas=)`. Las reglas repetidas por patrón (las 40 uniones
  apernadas de los ejes) se agrupan en UNA línea con el conteo y el peor caso, como las vigas.
- **D3. Schemas sin enums gigantes.** Un campo `ref` del catálogo publica «ver `get_catalog`»
  más la categoría, no las 362 refs. La validación (con «¿quisiste decir…?») sigue en la entrada.
- **D4. Los errores dicen cómo seguir.** El 400 de `remove_commands` con dependientes sugiere
  `con_dependientes=true` y lista los dependientes. `check_interference` truncado dice cuántas
  parejas faltan y cómo acotar. `run_batch` cuenta las uniones que expandió cada `fasten`.
  `delivery_check` informa su tiempo por regla.
- **D5. Nombres de subgrupo resuelven.** `render_view`, `get_scene` y las demás tools que aceptan
  nombres de grupo resuelven también los subgrupos que crea un super-comando, con el mismo
  `_expand_ids`. `show_axes` no cambia el encuadre: los ejes se dibujan en una esquina.
- **D6. `declare_structure` propone con criterio de taller** (raíz § Criterio: «lo desmontable
  va atornillado»):
  - eje ↔ larguero con perno o tuerca → perno;
  - tuerca ↔ cualquier cosa → parte de su perno, nunca soldadura;
  - guarda ↔ lo que gira → nunca, y guarda ↔ soporte → perno;
  - pata ↔ larguero con la pata a tope → soldadura (marco), salvo que haya placa con pernos.

  Lo dudoso sigue «a revisar», pero el default de la propuesta ya no suelda lo desmontable.
  Cuenta como bien: la propuesta de la piloto acierta lo que la estructura declarada a mano tiene
  (la verificación de uniones-en-lote F4, § Bitácora).

## Alternativas descartadas

- **Subir los topes de respuesta del MCP**: el problema es el contexto del agente, no el
  transporte.
- **Una tool por consulta resumida** (`get_connections_resumen`…): el MCP es thin. Mejor un
  parámetro en la tool que ya existe.

## Fases

- **F0 (S, sólo lectura)**: medir el tamaño de la respuesta de cada tool de la tabla en la piloto
  74 y en el transportador de 3 m (proyecto 79), sobre una COPIA de la base. Listar qué cliente
  (MCP, UI, publicación, tests) depende de cada forma de respuesta antes de acortarla.
- **F1 (M, `api` + `mcp` + `services`)**: D1, D2 y D3. Golden revisado. Cada tool de la tabla cae
  ≥ 5× en el caso de la piloto o queda justificada.
- **F2 (S, `api` + `mcp` + `commands`)**: D4 y D5.
- **F3 (M, `services` + `assembly`)**: D6. Test: la propuesta en la piloto coincide con la
  estructura declarada en ≥ 95 % de las uniones, y cero soldaduras en pares desmontables.
- **F4 (S, verificación por MCP)**: repetir con una sesión nueva sobre la flota la verificación
  de uniones-en-lote F4 y la de plantilla F3. Medir contexto total y llamadas antes y después.

## Lo que este plan NO hace

- No cambia la UI: si una respuesta de la API que usa la UI se acorta, la UI pide el modo
  completo (F0 lo lista).
- No agrega tools.

## Riesgos

- **Un cliente dependía de la forma larga** (la publicación, un test, la UI). Mitigación: el
  inventario de F0 y el modo completo a pedido.
- **El golden cambia mucho de una vez.** Mitigación: una tool por commit, con el diff revisado.

## Bitácora
