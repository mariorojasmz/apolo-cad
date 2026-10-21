---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: F0+F1 mergeadas a main el 2026-10-21 (respuestas cortas y filtros); F2 (D4, D5) implementada en rama, sin mergear; faltan F3 (D6) y F4 (verificación por MCP)
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

### F0 (2026-10-21): tamaño de cada respuesta y quién depende de su forma

Medido EN PROCESO: las tools reales del MCP con `_api` apuntado a un `TestClient` de la API,
sobre una COPIA de `data/apolo.db` (`APOLO_DB` a la copia, cada corrida desde una copia fresca).
#1 = `undo` de un `create_box` recién hecho; #2 = `run_batch(detail="summary")` con la acción
`create_roller_conveyor` del 79 (297 sólidos) sobre cada proyecto; el resto, la tool sin
argumentos. Bytes de la salida de la tool (lo que entra al contexto del agente).

| # | tool | piloto 74 (201 sólidos) | transportador 79 (297) |
|---|---|---|---|
| 1 | `undo` / `redo` | 47 002 / 47 163 B | 89 061 / 89 220 B |
| 2 | `run_batch(detail="summary")` | 37 288 B | 36 694 B |
| 3 | `check_assembly` | 3 779 B | 9 365 B |
| 4 | `get_connections` (264 / 392 uniones) | 39 712 B | 86 241 B |
| 5 | `engineering_check` (59 / 159 reglas) | 30 284 B | 69 532 B |
| 6 | `get_command_schemas("insert_component")` | 9 947 B (5 173 son el enum de 362 refs) | igual |
| 7 | `check_interference()` | 102 B (`truncado` sin conteo: es D4, F2) | 102 B |

Los números de la tabla del plan (52,7 KB del undo, 57–70 KB de conexiones) son de las sesiones
de la ola 5, sobre otras versiones de los proyectos; el orden de magnitud coincide.

**Inventario de clientes de cada forma** (antes de acortar):

- `POST /api/undo|redo` — UI `ui/src/api.ts` (`undo`/`redo` → `SceneOut`, escena completa con
  mallas, y `deshacer.test.ts` fija las rutas); MCP `undo`/`redo` (`brief_paso`); el chat de la
  app, por las mismas tools; `scripts/e2e_mcp.py` (tras `undo` lee `variables` con la variable
  y `puede_rehacer`); tests `test_api_deshacer.py`.
- `POST /api/commands/batch` — UI (escena completa); MCP `run_batch` vía `_scene_brief` (y
  `run_command`, `edit_*`, `set_variable`, que comparten el brief); el chat sólo mira si el
  lote se aplicó (`agent/chat.py`, `_LOTES`), no los sólidos; tests `test_mcp_brief.py`,
  `test_jobs_mutaciones.py`.
- `POST /api/assembly/soundness` — UI `AssemblyPanel.tsx`; `scripts/benchmark_package.py` (REST);
  MCP `check_assembly`; `e2e_mcp.py` lee `n_grounded`, `n_total`, `n_floating`, `isolated`; la
  puerta de entrega y la gravedad llaman a `soundness_report` directo, no a la ruta.
- `GET /api/connectivity` — UI `store.ts` + `AssemblyPanel.tsx` (lista entera);
  `tools/estructura.py::declare_structure(aplicar=true)` (cuenta `grounds`/`fasteners` y la
  devuelve en `detalle`); `benchmark_package.py`; MCP `get_connections`; el prompt del revisor
  (`design/revision.py`) la nombra.
- `POST /api/checks` — UI `ChecksPanel` (`api.ts`: interferencias + ingeniería + estructura);
  `benchmark_package.py`; MCP `engineering_check` y `check_interference`; `e2e_mcp.py` cuenta
  estados sobre las listas.
- `GET /api/schemas` — la UI pide `?vista=persona` (el desplegable de `SchemaForm.tsx` sale del
  `enum`); el agente (MCP y chat) usa la vista agente y `/api/schemas/{type}`.
- La publicación (`core/apolo/publicacion/`) sólo usa `/api/delivery-check`: no depende de
  ninguna.

Conclusión: todas las rutas las consume la UI con la forma larga → el modo corto entra como
PARÁMETRO opt-in de la API (sin él, byte-idéntico) y lo pide el MCP. La UI no cambia.

### F1 (2026-10-21): D1, D2 y D3

Medido igual que F0, con el código de la rama (`detail`/filtros por defecto de cada tool):

| # | tool | 74 antes → después | × | 79 antes → después | × |
|---|---|---|---|---|---|
| 1 | `undo` / `redo` | 47 002 → 219 B | 215 | 89 061 → 217 B | 410 |
| 2 | `run_batch(detail="summary")` | 37 288 → 704 B | 53 | 36 694 → 702 B | 52 |
| 3 | `check_assembly` | 3 779 → 109 B | 35 | 9 365 → 109 B | 86 |
| 4 | `get_connections` | 39 712 → 6 535 B | 6,1 | 86 241 → 7 265 B | 11,9 |
| 5 | `engineering_check` | 30 284 → 5 523 B | 5,5 | 69 532 → 8 390 B | 8,3 |
| 6 | `get_command_schemas("insert_component")` | 9 947 → 5 530 B | 1,8 | igual | 1,8 |
| 7 | `check_interference()` | 102 B, sin cambio (F2) | — | 102 B | — |

A pedido, en la piloto: `undo(detail="full")` 47 002 B, `check_assembly(detail="full")` 3 779 B,
`get_connections(resumen=false)` 39 712 B, `get_connections(kind="perno")` 1 280 B,
`engineering_check(detail="full")` 30 284 B, `(grupo="flecha de viga")` 914 B,
`(solo_fallas=true)` 1 396 B.

**Justificadas** (< 5×): #6 — lo que queda (5,5 KB) es la documentación de los parámetros
(anclas de perfil abierto, `orientacion`, Vec3/Rot3), que el agente necesita para llamar bien;
recortarla sería D3 de otro plan. #7 es D4 (F2).

Decisiones tomadas al implementar:

- **El modo corto vive en el servidor, opt-in** (`services/paso.py`, `conexiones.py`,
  `reglas_cortas.py`): el HTTP también adelgaza (el undo ya no viaja con mallas) y el chat lo
  recibe igual. La excepción es #2: el brief de mutación ya era del cliente (`brief.py`); con más
  de 40 sólidos afectados, "diff" y "summary" dan `por_comando` en vez de la lista. Vale para todas
  las mutaciones que usan el brief, no sólo `run_batch` (D1: "toda respuesta que lista sólidos").
- **Patrón = el nombre con los números → `*`**, el mismo para reglas y uniones. Para uniones se
  probó primero la raíz de pieza de `estructura.py`: la piloto daba 84 filas y 16 KB (cada cadena
  es su propio comando, c65…c83), 2,5×; por patrón de nombre, 6,5 KB.
- **`engineering_check(grupo=)` filtra por FAMILIA de regla** (la parte antes de « · »:
  «unión apernada», «flecha de viga»…), no por grupo de piezas: las reglas no llevan ids y lo que
  el agente filtró con Grep en las verificaciones era una familia (flecha-de-bastidor F3).
- **El peor caso** de una línea agrupada = estado más grave (error > aviso > ok) y, a igual
  estado, el menor `calc.fs`. Sólo las reglas en «error» conservan `calc`/`hipotesis`/`no_aplica`.
- **`get_connections(resumen=None)` = auto**: resume con más de 40 uniones (como
  `declare_structure` con sus 60 acciones); con un filtro chico vuelve la lista con nombres.
  `ids` acepta piezas, grupos y command_ids (sus piezas `{cmd}_n`); un token que no resuelve da
  404 con «¿quisiste decir…?». `kind="anclaje"` = sólo los anclajes.
- **`check_assembly` corto** quita `grounded`, `floating` (duplicaba `floating_detail`) y
  `components`; suma `n_isolated` y `n_componentes`. Las listas de lo que flota se recortan a 40
  con `_omitidas` (sin anclajes, flota TODO).
- **`undo`/`redo` diff**: comandos quitados/restaurados/editados por id, piezas nuevas/borradas
  por nombre, `piezas_editadas` = las de los comandos editados (no se compara geometría), uniones
  por nombre y tipo, `variables` = sólo las que cambiaron (el e2e lee la variable de ahí). Con
  `pasos` > 1 la etiqueta es la lista de las N.
- **D3** sólo toca enums de más de 50 refs del catálogo: `insert_component.component` (362) y
  `add_device.ref` (69); los de 41 rodamientos o 16 tubos se quedan (útiles y chicos). El
  `«componente desconocido»` de insert_component ganó el «¿quisiste decir…?» que add_device ya
  tenía. La vista persona y `command_schemas()` no cambian (la UI arma el desplegable del enum).
- Trinquetes: `routers/commands.py` iba a pasar de 500 → las filas de `find_commands` salieron a
  `services/busqueda_log.py`; `mcp_server.py` bajó de 1392 a 1388 (recibo/resultado de job a
  `tools/recibo.py`, opcionales de `fea_assembly` en un dict) aunque 5 tools ganaron parámetros.
- Golden re-congelado en un commit por tool (o par de tools que comparten servicio), con casos
  nuevos para cada modo a pedido y cada filtro (161 → 168 llamadas).
- Los tiempos de la tabla de F0 incluyen la contención del autosave: un undo que llega mientras
  se vacía el autosave de la mutación anterior espera el pack de la caché de geometría (se vio un
  undo de 3,8 s que, repetido, tarda 0,05 s).

Fuera de F1 (anotado para después): `declare_structure(aplicar=true)` sigue devolviendo la lista
entera de conexiones en `detalle` (es D6/F3, que rehace esa tool); `engineering_check` calcula
también la interferencia global de `/api/checks` (≈ 16 s de los ≈ 18 s en la piloto) aunque no
la devuelve: un flag para saltarla es barato y no estaba en el contrato.

### F2 (2026-10-21): D4 y D5

Medido como F0 (tools reales del MCP contra la API en proceso, copia de `data/apolo.db`):

| tool | piloto 74 (201 sólidos) | transportador 79 (297) |
|---|---|---|
| `check_interference()` | 102 → 532 B: 400 de 468 parejas, faltan 68, y los 6 grupos con sus piezas | 102 → 676 B: 400 de 698, faltan 298, y los 6 subgrupos de la plantilla |
| `delivery_check()` (`tiempos_s`) | 9,6 s: interferencias 7,1 · acceso de herramienta 2,5 · el resto < 0,05 | 14,2 s: interferencias 9,8 · acceso 4,3 |
| `remove_commands([c11])` sin dependientes | 400 de 755 B: los 6 `fasten` que arrastraría `con_dependientes`, el grupo que editaría y el patrón `c57`, que no arrastra | — |
| `run_batch(create_roller_conveyor 3 m, "summary")` | 1 579 B; `uniones_expandidas` = 300 uniones en 10 filas (984 B) | 1 557 B (964 B) |
| `render_view(isolate=["Bastidor"])` | — (la piloto no tiene subgrupos) | antes 400 «ningún id existe»; ahora la foto en 1,1 s; `get_scene(ids=["Bastidor"])` 806 B |

La puerta de entrega no se trunca en ninguna de las dos (excluye los pares con `fasten`): los
~53 s de la verificación de la plantilla F3 eran con `con_gravedad`. Lo caro es la interferencia
y el acceso de herramienta.

Decisiones tomadas al implementar:

- **El 400 del borrado** (`services/cirugia.py::como_seguir`, tras el rollback, bajo el mismo
  lock) va con y sin `con_dependientes` y en los dos modos: la ruta no la usa la UI. Lista lo que
  `con_dependientes` arrastraría y, aparte, los comandos que NO arrastra y nombran lo borrado. Esa
  segunda lista salió de medir: en la piloto el borrado de la fuente de un patrón falla en el
  PATRÓN (`c57`), no en una unión; sugerir sólo `con_dependientes` habría sido engañoso. Cada
  lista se recorta a 8 con «… y N más»; un id inexistente deja el error tal cual.
- **Interferencia truncada**: `interference_report` declara `parejas_candidatas` y
  `parejas_sin_revisar` SÓLO al truncar (sin recorte, el dict de siempre); `/api/checks` suma
  `como_acotar` con los grupos de primer nivel o, si hay una sola raíz sin miembros (una plantilla),
  con sus subgrupos (en la 79 la raíz era la máquina entera). `verify` y `preview(data)` también
  dicen cuántas faltan; la puerta lo pone en su aviso.
- **Fasten por conjuntos**: lo cuenta `_state_or_error` para toda mutación (`run_batch`,
  `run_command`, ediciones), no sólo `run_batch`: `uniones_expandidas` aparece sólo si lo afectado
  tiene un `fasten` con conjunto (incluidas las de una plantilla, por prefijo `{cmd}_`). La UI no
  la lee y sin conjuntos la respuesta es byte-idéntica. `tools/recibo.py` la pasa al brief.
- **`tiempos_s`** va siempre en `/api/delivery-check` (la UI no la usa; la publicación lee sólo
  veredicto, bloqueantes, avisos y resumen).
- **Subgrupos** (`assembly/groups.resolve_group`): un token que no es grupo ni pieza resuelve al
  ÚNICO subgrupo cuyo último tramo es ese («Bastidor» → «Transportador de rodillos/Bastidor»); de
  varios grupos → 400 con los candidatos. Lo usan `_expand_ids` (render, pick, get_scene, verify,
  check_interference, planos, manual) y `get_connections`. El 400 de `isolate` vacío ahora nombra
  lo que no resolvió y sugiere.
- **`show_axes`**: medido antes, VTK ya encuadraba con el bbox explícito (`ResetCamera(bounds)`)
  y los ejes NO cambiaban el encuadre: el problema real era que salían del origen, a menudo fuera
  de cuadro. Ahora es un triedro en la esquina inferior izquierda (renderer propio en la capa
  overlay con la orientación de la cámara): fuera de esa esquina, la foto es idéntica pixel a
  pixel. El respaldo matplotlib sigue con los ejes del origen (el MCP no lo usa).
- Trinquete: `mcp_server.py` 1388 → 1382 (`export_step` y `export_stl` escriben con
  `entregable.escribir`) aunque cinco docstrings crecieron. Golden: 168 → 172 llamadas (lote con
  conjuntos, borrado que dice cómo seguir, interferencia truncada, puerta con tiempos) y 6
  descripciones.

Fuera de F2 (anotado para después): `check_interference` sigue corriendo TODO `/api/checks`
(ingeniería y estructura incluidas: 23 s en un transportador de 1 m, 15–25 s en la 74/79) para
devolver sólo la interferencia — el mismo flag que falta en `engineering_check`; el 400 de
`isolate` de planos y manual sigue con el texto viejo (ya resuelve subgrupos); el render
matplotlib dibuja los ejes del origen.
