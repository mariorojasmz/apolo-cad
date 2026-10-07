---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: contrato escrito, espera el visto bueno de Mario (vetos por número de decisión); F0 medida, F1–F4 sin empezar
descripcion: Deshacer y Rehacer dicen qué cambio van a revertir (al pasar el puntero y en una lista de los últimos cambios), y desde la lista se deshacen varios de una vez
---

# Deshacer y Rehacer te dicen qué van a revertir, y hasta dónde

## Estado y origen

Pedido de Mario (2026-10-06), textual: «para que el deshacer y Rehacer indiquen con un texto lo
que se va hacer, por que creo que movi algo y no me di cuenta y queria deshacer pero no sabia
hasta que punto deshacer, asi que si al pasar el puntero a esos botones dice lo que va hacer,
ayuda mucho.»

El caso real: un arrastre accidental en el viewport (un clic que pasó los 5 px de
`DRAG_THRESHOLD_PX` agrega un `transform`) y, para encontrarlo, deshacer a ciegas sin saber
cuántos pasos hay entre ese movimiento y el estado actual.

## El problema / lo que hay hoy

- **La pila no sabe qué es cada paso.** Una entrada de undo es un snapshot del documento
  (`commands`, `hidden`, `seq`, caché de regen: `core/apolo/doc/document.py:108-117`), sin
  descripción. Se apila en tres sitios copiados entre sí: `_mutate` (`document.py:471-475`),
  `execute_many` (`:544-547`) y `edit_many` (`:584-587`). `undo`/`redo` (`:897-930`) son espejos.
- **La API sólo publica booleanos**: `document_payload()` manda `can_undo`/`can_redo`
  (`core/apolo/api/scene.py:59-60`); `POST /api/undo` y `/api/redo` deshacen de a uno
  (`core/apolo/api/routers/commands.py:338-345`).
- **La UI pinta un ícono con `title="Deshacer"`** (`ui/src/panels/TopBar.tsx:57-62`); Ctrl+Z /
  Ctrl+Y van al mismo `undo()` (`ui/src/viewport/shortcuts.ts:71-72`).
- **El MCP tampoco dice qué deshizo**: `undo`/`redo` devuelven el brief de siempre
  (`core/apolo/mcp_server.py:357-360`, `:710-713`), con `puede_deshacer` booleano.
- **Qué entra a la pila y qué no** (medido con un script sobre `Document`, ver Bitácora F0):
  sólo los cambios al LOG de comandos. Color, material, visibilidad, boceto-guía, requisitos,
  notas y variantes guardadas son metadatos de manifest y **no apilan undo**
  (`set_color`/`set_material`/`set_visibility`, `document.py:699-715` y `:863-870`). Por eso un
  «Deshacer: color de 5 piezas» no puede existir: deshacer no revierte colores.
- **Trampa encontrada al medir**: `hidden` viaja en el snapshot pero ocultar no apila undo →
  ocultas la pieza A, deshaces el último comando (B) y **A vuelve a aparecer**. Una etiqueta que
  dijera «Deshacer: Caja «B»» mentiría por omisión.

## Lo que se revisó antes de escribir esto

- **Los trinquetes de tamaño**: `document.py` congelado en 1059 líneas y `mcp_server.py` en 1429
  (`tests/test_tamano_archivos.py:54,60`); `ui/src/state/store.ts` en 916
  (`ui/src/tamanoArchivos.test.ts:43`). Ninguno puede crecer → el descriptor va a un módulo
  nuevo y en `document.py` se unifican las tres copias del apilado y los espejos undo/redo
  (baja líneas en vez de subirlas).
- **Todas las puertas de mutación** pasan por `_mutate`, `execute_many` o `edit_many`:
  comando suelto, edición (también la coalescente de Propiedades, `commands.py:216-220`), lote
  con contrato, borrado de comandos/conexiones/variables, `apply_configuration`, plantillas de
  proyecto nuevo e `import_step`. Etiquetar en el punto donde se apila cubre todas esas rutas,
  la UI, el MCP y el chat sin tocar una firma.
- **Hay nombres legibles para todo**: cada `CommandSpec` trae `title` en español («Caja»,
  «Taladro», «Mover / Rotar», «Variable») y cada campo su `title` («Posición», «Ancho (X)»),
  limpios de versiones en la vista persona (`commands/vista_persona.py`). 34 de los 53 comandos
  llevan `name`; de los 19 restantes, 17 referencian una pieza (`feature`, `features`)
  cuyo nombre está en la escena, y `transform_group`/`pattern_group`, un grupo por nombre
  (`group`, `source`). Nunca hace falta mostrar un `type` crudo (regla de
  [ui](../../ui/CLAUDE.md): nada de `drill_hole` en pantalla).
- **El costo**: describir un paso es un diff del log por id (antes vs después). En el proyecto 38
  (425 comandos) cuesta 0,5–0,7 ms; el `deepcopy` del snapshot que ya se paga en cada mutación
  cuesta 15–32 ms. Sumar la etiqueta cuesta < 5 % de lo que ya cuesta apilar.
- **La regla de `title=`** ([ui](../../ui/CLAUDE.md) § Texto): «`title=` sólo repite lo que ya
  se ve; en una tableta el `title` no existe». Mario pidió el texto al pasar el puntero; para
  cumplir las dos cosas, el mismo texto tiene que estar también a la vista en algún lado.
- **`TopBar` se monta en los dos modos** (Visor y Completo, `ui/src/App.tsx:41`): lo que se
  agregue ahí se ve siempre, sin tocar la capa del visor.

## Decisiones (para vetar)

- **D1. La etiqueta se DERIVA del diff del log en el único punto donde se apila**
  (`_push_undo`), no la pasa cada endpoint. Cubre todas las puertas presentes y futuras, no se
  desfasa y no cambia ninguna firma. Única intención explícita: `apply_configuration` (el diff
  diría «Variable «largo_total»: 4000 → 3200»; «Aplicar variante «3.2m»» se entiende mejor).
- **D2. La etiqueta vive en la entrada de la pila, en memoria** (clave `etiqueta` del snapshot).
  No va al `.apolo`, al manifest ni al log: el historial no se persiste hoy y sigue sin
  persistirse. No cambia firmas de regenerate → **sin bump de `GEOM_CACHE_EPOCH` ni de versión**.
- **D3. El texto se arma en el backend, en un módulo puro nuevo `core/apolo/doc/pasos.py`**, y
  la UI sólo antepone «Deshacer: » / «Rehacer: ». Una sola fuente para UI, MCP y chat.
- **D4. Gramática de la etiqueta** (≤ 120 caracteres; nombres de más de 40, cortados con «…»):

  | el paso | la etiqueta |
  |---|---|
  | un comando nuevo | `Caja «Soporte motor»` · `Taladro «Placa base»` · `Insertar proyecto «Faja A»` |
  | `transform` (mover/rotar) | `Mover «Guarda tambor motriz»` · `Rotar «…»` · `Mover y rotar «…»` |
  | variable nueva / editada | `Variable «L» = 3200` · `Variable «L»: 2000 → 3200` |
  | un comando editado | `Editar Caja «Soporte motor»: Posición` · `…: Ancho (X), Alto (Z) y 2 más` |
  | un comando eliminado | `Eliminar Caja «Soporte motor»` |
  | lote del mismo tipo | `Mover ×3: «Guarda», «Tapa» y «Motor»` · `Eliminar ×4: «A», «B» y 2 más` |
  | lote mixto | `Lote de 33 comandos: 12 nuevos, 21 editados` |
  | variante | `Aplicar variante «3.2m (prueba paramétrica)»` |
  | edición que no cambió nada | `Editar Caja «Soporte motor» (sin cambios)` |

  El nombre sale, en orden: del `name` del comando; si referencia una pieza, del nombre de esa
  pieza (en la escena de después o, si se eliminó, en la de antes); si creó piezas, de la
  primera («y N más» si son varias); si nada aplica, va sólo el título. Vocabulario de
  [ui](../../ui/CLAUDE.md): «pieza», «variante», «comando», nunca ids ni `type`.
- **D5. La API publica dos listas aditivas en `document`**: `undo_labels` y `redo_labels`
  (la más próxima primero, ≤ 50 por `_UNDO_CAP`). `can_undo`/`can_redo` no cambian; un cliente
  viejo no se entera.
- **D6. Deshacer o rehacer N cambios de una vez, con UN regenerate**: `POST /api/undo?pasos=N`
  (y `redo`). Restaura el snapshot destino —que trae su propia caché de regen, replay ≈ 0— y
  pasa los intermedios a la otra pila con sus etiquetas. Contrato: «deshacer 3» deja el
  documento y las dos pilas idénticos a tres «deshacer» seguidos (test de equivalencia).
  Peek-then-commit como hoy: si la restauración revienta, las pilas quedan intactas. Sin
  `pasos`, byte-idéntico a hoy.
- **D7. En la UI, las dos cosas**: `title` y `aria-label` del botón dicen el próximo cambio
  («Deshacer: Mover «Guarda tambor motriz»», lo pedido) **y** un botón ▾ junto a cada uno abre la
  lista de cambios (visible y tocable en tableta, como pide la regla de `title=`). En la lista,
  al pasar sobre el k-ésimo se marcan del 1 al k y el pie dice «Deshacer 3 cambios»; el clic
  deshace esos k (patrón de Word/Excel). La lista se cierra sola si llega una escena nueva (el
  agente cambió el historial mientras mirabas). Ctrl+Z / Ctrl+Y siguen de a un paso.
- **D8. Un paso del historial se llama «cambio»** y entra a la tabla «Una cosa, un nombre» de
  [ui](../../ui/CLAUDE.md) (no «paso», no «acción»). «Comando» sigue siendo la fila del log: un
  cambio puede ser un lote de 33 comandos.
- **D9. MCP sin parámetros nuevos**: `undo`/`redo` devuelven además `deshecho`/`rehecho` con la
  etiqueta del cambio revertido (el agente sabe qué deshizo). El brief de cada mutación NO gana
  la etiqueta: serían tokens en cada llamada para algo que sólo importa al deshacer. El golden
  cambia sólo en los casos `deshacer` y `rehacer`; el helper va a `apolo/brief.py` y
  `mcp_server.py` cambia dos líneas en sitio (no crece).
- **D10. Describir nunca hace fallar una mutación**: cualquier excepción del descriptor →
  `Cambio en el modelo` (test con el descriptor parcheado para lanzar).
- **D11. Edición coalescente**: al coalescer (arrastres en Propiedades) se RECALCULA la etiqueta
  de la entrada de arriba contra su snapshot: el primer ajuste pudo ser Ancho y el último Alto.
- **D12. Deshacer y rehacer ya no tocan la visibilidad**: restauran el log y dejan `hidden` como
  está, igual que con colores y materiales. Hoy deshacer re-muestra en silencio lo que ocultaste
  después (ver El problema), y la etiqueta prometería algo que no es todo lo que pasa. El
  rollback de una mutación fallida no cambia (ahí `hidden` es el mismo antes y después). Si se
  veta, va al [backlog](../backlog.md) y la etiqueta convive con la trampa.

## Alternativas descartadas

- **Que cada endpoint o cliente pase la etiqueta** (`etiqueta=` en `execute`/`edit`/…): más de
  quince llamadores en cinco routers, el MCP y el chat tendrían que inventar el texto y una ruta nueva sin etiqueta
  quedaría «sin descripción». Se desfasa sola.
- **Calcular el diff al leer, sin guardarlo**: costaría O(pasos × comandos) en cada payload
  (cada delta del WS) y perdería el nombre de las piezas eliminadas: la escena de antes ya no
  existe.
- **Etiquetar en la UI desde `document.commands`**: la UI ve el log actual, no las pilas; no
  sabría qué hay para rehacer.
- **Tooltip propio flotante**: no resuelve la tableta y en Dockview se corta; la lista ▾ ya da
  lo visible.
- **Hacer deshacibles color, material y visibilidad**: es otro problema (meter metadatos a la
  pila cambia qué significa deshacer y el costo del snapshot). Fuera de este plan.
- **Historial persistente o panel de historial dockeable**: más de lo pedido.

## Fases

Cada fase la implementa un subagente en worktree (`model: "opus"`, en segundo plano) con los
tests como gate; la sesión principal revisa el diff contra este contrato y re-corre las suites.

- **F0 — Medir (sólo lectura). HECHA.** Costo del diff, qué apila undo, trampa de `hidden`.
  Números en la Bitácora.
- **F1 — Documento (`doc`). M. Depende de: nada.**
  - `core/apolo/doc/pasos.py` (puro): `describir(cmds_antes, cmds_despues, escena_antes,
    escena_despues, intencion=None) -> str`, con la gramática de D4. Títulos de comando y de
    campo desde el `REGISTRY`, sin versiones del roadmap (el regex de `vista_persona`).
  - `Document`: `_push_undo(snap, escena_antes, intencion=None)` reemplaza las tres copias del
    apilado; `_mover(origen, destino, pasos)` reemplaza los espejos `undo`/`redo` y los extiende
    a N pasos (D6); `undo(pasos=1)`/`redo(pasos=1)`; propiedades `undo_labels`/`redo_labels`;
    `apply_configuration` pasa su intención; el coalescer recalcula (D11); deshacer conserva
    `hidden` (D12). `_undo`/`_redo`/`_UNDO_CAP` siguen existiendo (los leen siete archivos de tests).
  - **Verifica**: `tests/test_pasos.py` (una aserción por fila de D4, nombres cortados,
    pieza eliminada nombrada desde la escena de antes, fallback de D10) y en
    `tests/test_document.py` la equivalencia «deshacer N» ≡ N × «deshacer» (documento y pilas),
    la ida y vuelta de etiquetas undo → redo → undo, `pasos` fuera de rango → `DocumentError`,
    peek-then-commit con N, el tope de 50 y D12. `document.py` ≤ 1059 líneas (si baja, se baja
    el trinquete). pytest completo + ruff.
- **F2 — API y MCP (`api`, `mcp`). S. Depende de F1.**
  - `document_payload()` suma `undo_labels`/`redo_labels`; `POST /api/undo|redo` aceptan
    `pasos` (query, ≥ 1; fuera de rango → 400 con «Sólo hay N cambios para deshacer»).
  - `brief.py`: helper que agrega `deshecho`/`rehecho` (omitido si el payload no trae listas:
    «opcionales omitidos, nunca `null`»); `mcp_server.py` lo usa en `undo`/`redo` sin crecer.
  - **Verifica**: test de API (listas tras crear/editar/eliminar/lote/variante, `?pasos=3`,
    400 fuera de rango, sin `pasos` byte-idéntico); golden con el `escena()` de
    `scripts/golden_mcp_casos.py` llevando las listas, diff revisado y
    `python scripts/golden_mcp.py --congelar`; pytest completo + ruff.
- **F3 — UI (`ui`). M. Depende de F2.**
  - `types.ts` (`undo_labels?`, `redo_labels?`), `api.ts` (`undo(pasos)`), `store.ts`
    (`undo: (pasos?) =>`, en la misma línea: no crece), `TopBar.tsx` (`title`/`aria-label` +
    los ▾), componente nuevo `panels/HistorialCambios.tsx` y lógica pura
    `panels/historialCambios.ts` (texto del pie, «1 cambio» / «N cambios», título del botón).
  - **Verifica**: vitest de la lógica pura; `tuteoNeutro`, `textoDeAyuda` y
    `tamanoArchivos` en verde; `npm test` + `npm run build`; en `ui-preview` contra una API
    sobre una COPIA de la base: mover una pieza, leer el `title`, abrir la lista, deshacer 3 de
    una vez, rehacer 1 (`read_page` + captura).
- **F4 — Verificación y documentación. S. Depende de F3.**
  - E2E de Mario sobre el 38 (o su copia): mover algo, ver qué dice el botón, deshacer hasta ahí.
  - CLAUDE.md: [doc](../../core/apolo/doc/CLAUDE.md) (la entrada de la pila lleva `etiqueta`;
    N pasos = un regenerate; deshacer no toca la visibilidad), [api](../../core/apolo/api/CLAUDE.md)
    (`?pasos`), [ui](../../ui/CLAUDE.md) («cambio» en la tabla de nombres) y los conteos de
    «Estado actual» de la raíz. Frontmatter y Bitácora de este plan.

## Lo que este plan NO hace

- No vuelve deshacibles color, material, visibilidad, boceto-guía, notas, requisitos ni
  variantes guardadas: no están en la pila y por eso nunca aparecen en la lista.
- No persiste el historial: al reabrir un proyecto la pila nace vacía, como hoy.
- No distingue quién hizo el cambio (tú o el agente).
- No cambia Ctrl+Z / Ctrl+Y (de a un paso) ni agrega un aviso tras deshacer.
- No agrega parámetros a las tools MCP ni etiquetas a los lotes escritas por el agente.

## Riesgos

| riesgo | mitigación |
|---|---|
| El golden MCP se pone rojo | deliberado y acotado a `deshacer`/`rehacer`; se revisa el diff antes de congelar |
| `document.py`, `mcp_server.py` o `store.ts` crecen y rompen el trinquete | F1 unifica el apilado y los espejos (baja líneas); MCP y store cambian en sitio |
| La lista se desactualiza: el agente apila un cambio entre que la abres y haces clic, y «deshacer 3» deshace otro | la lista se cierra al llegar una escena nueva; el servidor valida el rango |
| Una etiqueta engaña (p. ej. el nombre de la pieza cambió en el mismo lote) | se nombra con la escena de después y, si no está, la de antes; lote mixto cae al conteo honesto |
| El descriptor revienta con un comando raro | D10: `Cambio en el modelo`, la mutación sigue |
| Costo en logs grandes o en el arrastre coalescente | medido: 0,5–0,7 ms con 425 comandos, frente a 15–32 ms del snapshot |

## Bitácora

### F0 — medición (2026-10-06)

- **Costo** (lectura de `data/apolo.db` en modo sólo lectura, 20 repeticiones):

  | proyecto | comandos | `deepcopy` del log (ya se paga) | diff por id |
  |---|---|---|---|
  | 38 `faja-paqueteria-4m` | 425 | 15–32 ms | 0,5–0,7 ms |
  | 67 `perezosa-copaiba-v2-x` | 139 | 4,8 ms | 0,19 ms |
  | 53 `layout-planta-demo` | 17 | 0,6 ms | 0,03–0,08 ms |

- **Qué apila undo**, con un script sobre `Document` (cajas A y B, ocultar A, deshacer):
  `A visible` pasa de `False` a `True` al deshacer B → `hidden` del snapshot se restaura (D12).
  `set_color` y `set_material` no cambian el largo de `_undo` → no son deshacibles.
- De paso: [api](../../core/apolo/api/CLAUDE.md) decía que los lotes de color y material dejan
  «un solo undo»; no dejan ninguno. Se corrigió en el mismo commit que este plan.
