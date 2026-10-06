---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: contrato escrito; espera que Mario vete D1–D10 antes de implementar
descripcion: Aplicar una variante cambia sólo las variables que la distinguen; ya no revierte en silencio los cambios de diseño que hiciste después de guardarla
---

# Una variante cambia sólo sus variables; el resto del diseño queda como está

## Estado y origen

Pedido de Mario (2026-10-06), tras una cirugía del proyecto 38 (`faja-paqueteria-4m`): «una
variante guardada hace meses revierte EN SILENCIO cualquier cambio de diseño posterior en
variables que no tienen nada que ver con la variante». Pidió que una variante guarde SÓLO las
variables que la distinguen, con migración de las viejas, «o al menos un AVISO al aplicar».

Evidencia del mismo día: «3.2m compacta» y «4m estandar» se crearon el 2026-07-10 como foto
completa. Hoy se cambió `sec_pata` 76.2 → `sec_larg_h` y las fórmulas de `pata_alto`/`pata_cz`
(garruchas). Aplicar cualquiera de las dos habría vuelto a la pata de 3″ y a la altura vieja,
chocando con las garruchas nuevas. Se arregló a mano borrándolas y recreándolas con
`PUT {largo_total}` sobre el estado actual — y **la trampa sigue armada** (ver F0 abajo).

## El problema / lo que hay hoy

- `Document.save_configuration` guarda `dict(self.variables_raw)`: TODAS las variables
  (`core/apolo/doc/document.py:653-657`).
- `set_configuration` sobre un nombre nuevo parte de `self.variables_raw` completo
  (`document.py:672`); el test lo fija como contrato: «el resto hereda lo actual»
  (`tests/test_product.py:179`).
- `apply_configuration` reescribe cada `set_variable` cuyo nombre esté en la variante
  (`document.py:687-692`) → con una foto completa, reescribe las 37.
- Nadie avisa qué cambió: el MCP devuelve el brief normal (`mcp_server.py:577-582`) y la UI
  aplica con un clic (`ui/src/panels/VariablesDialog.tsx:143-144`).

**F0 medido hoy** (lectura de `data/apolo.db`, sin abrir proyectos):

| dónde | qué hay |
|---|---|
| proyecto 38 | 37 variables; 2 variantes, **37 claves cada una** («4m estandar» y «3.2m (prueba paramétrica)»). Difieren entre sí y del modelo SÓLO en `largo_total` |
| resto de proyectos | ninguno tiene variantes |
| revisiones | 12 de 102 llevan variantes (todas fotos completas) |

El arreglo a mano no desarmó la trampa: el `PUT` sobre un nombre nuevo volvió a sembrar las 37
variables del momento. El próximo cambio de diseño queda expuesto igual que el de hoy.

## Lo que se revisó antes de escribir esto

- **El trinquete de tamaño** (`tests/test_tamano_archivos.py`): `document.py` está congelado en
  1060 líneas y `mcp_server.py` en 1429; ninguno puede crecer. → La lógica va a un módulo puro
  nuevo (`doc/variantes.py`) y `Document` sólo delega (el bloque actual baja de ~47 líneas).
- **Forma del metadato**: `configurations` = `{variante: {variable: expresión}}` lo leen la
  escena (`api/scene.py:62-63`), el briefing (`scene.py:277-278`), el resumen
  (`routers/core.py:68`), el brief MCP (`brief.py:100`) y la UI (`types.ts:116-117`). Si la forma
  no cambia, ninguno se rompe.
- **Un Apolo viejo y una variante rala**: su `apply` sólo reescribe las claves presentes
  (`document.py:691`) → aplica bien una variante con 1 clave. La compatibilidad hacia atrás sale
  gratis si no se toca `FORMAT_VERSION` (`document.py:25`).
- **Cómo lo hace una tabla de diseño de SolidWorks**: las columnas son los parámetros de la
  tabla; lo que no está en la tabla es común a todas las configuraciones. Es el modelo al que
  apunta el pedido.
- **El bug inverso**: si «3.2m» guarda `{largo_total, n_patas}` y «4m» sólo `{largo_total}`,
  aplicar 3.2m y volver a 4m deja `n_patas` de la 3.2m. E1.4 («aplicar y volver») lo detectaría.
  Por eso D2: todas las variantes tienen las mismas columnas.
- **Migración con bandera**: no hay forma fiable de distinguir una foto vieja de una tabla nueva
  por su contenido (un proyecto de 1 variable da una foto de 1 clave). Hace falta una marca en el
  manifest.
- `scripts/benchmark_package.py` no usa variantes (verifica `largo_total=4000` directo); el
  golden MCP sí (`scripts/golden_mcp_casos.py:115-116, 247-248`).

## Decisiones (para vetar)

- **D1 — Una variante guarda sólo las COLUMNAS de la tabla de diseño.** La forma
  `{variante: {variable: expresión}}` no cambia; cambia lo que entra. Columnas = las claves de
  las variantes. Lo que no es columna no lo toca ninguna variante. *Por qué*: es el modelo de
  tabla de diseño; sin cambiar la forma no se rompe ningún lector.
- **D2 — Tabla rectangular: todas las variantes tienen las mismas columnas.** Agregar una
  columna (en cualquier variante) la agrega a las DEMÁS con la expresión ACTUAL de esa variable.
  *Por qué*: hasta ese momento, aplicar cualquier variante dejaba esa variable en su valor
  actual; el relleno reproduce exactamente lo que cada una hacía. Sin relleno, «aplicar y volver»
  no vuelve (el bug inverso).
- **D3 — `save_configuration(name, variables=None)` («Nueva variante desde la actual»)** guarda
  el valor actual de las columnas existentes ∪ `variables`. Sin columnas y sin `variables` →
  error accionable: «Dinos qué variables distinguen a esta variante (p. ej. `largo_total`)». Un
  nombre que ya existe se sobrescribe, como hoy.
- **D4 — `set_configuration(name, values)` sobre un nombre NUEVO parte de las columnas** (con su
  valor actual), no de todas las variables. Una clave nueva en `values` = columna nueva (D2). La
  validación resuelve `{**variables_raw, **variante}`: con la variante rala hay que completar con
  el resto para que una expresión de la variante que nombra otra variable resuelva.
- **D5 — Migración al CARGAR, con bandera `configurations_format: 2` en el manifest.** Sin
  bandera = fotos viejas. Columnas de la migración: las variables cuyo valor **difiere entre al
  menos dos variantes**; si hay una sola variante, las que difieren del valor actual del log. Se
  descartan las claves de variables que ya no existen. Determinista e idempotente; se persiste en
  el siguiente autosave. *Por qué*: conserva exactamente el salto ENTRE variantes y elimina sólo
  el «volver a la foto», que es el bug. Proyecto 38 queda con `{largo_total}` en las dos.
  Alcanza también a las revisiones y a los `.apolo` sueltos, que un script sobre la SQLite no
  tocaría. Un Apolo viejo lee el archivo nuevo y aplica bien (ver «Lo que se revisó»).
- **D6 — `apply_configuration` devuelve `cambios`**: `[{variable, antes, despues}]`, sólo las
  que cambian de expresión, y `aviso` si una columna nombra una variable que ya no existe (se
  ignora). El MCP lo pasa en su salida. Es el AVISO que pidió Mario: con D1 no hay variables
  «ajenas», pero el agente y la persona ven qué movió el clic.
- **D7 — Quitar una columna**: `DELETE /api/configuration-columns/{variable}` la saca de TODAS
  las variantes (sigue siendo variable del proyecto). Prefijo propio para no solaparse con
  `/api/configurations/{name}/…` (`tests/test_rutas_api.py`).
- **D8 — MCP: `save_configuration(name, values=None)`**, UN parámetro más. Sin `values` → POST
  (D3, captura las columnas); con `values` → PUT (D4: crea o edita sin aplicar). Así el agente
  crea la primera variante (`values={"largo_total": "4000"}`) y edita celdas sin `curl`. Borrar
  variante o columna sigue sin tool (UI y REST): el MCP es fino y no hubo pedido. *Vetable*: si
  quieres que el agente borre, se suma `delete_configuration(name)`.
- **D9 — UI (`VariablesDialog`)**: la tabla de variantes muestra SÓLO las filas que son columna
  (hoy muestra todas las variables, `VariablesDialog.tsx:154`); «Agregar variable a la tabla»
  (lista con las que no están; usa el PUT → D2); ✕ por fila «Quitar de la tabla» (D7); la
  primera variante pide elegir la variable que la distingue; la celda que difiere del modelo se
  resalta y la columna que coincide entera con el modelo se marca «actual» (se calcula en el
  cliente, sin API nueva). Texto según `ui/CLAUDE.md`: «variante», tuteo, gates.
- **D10 — Rúbrica: aclarar E1.4 en `rubrica-v2.md`, no abrir v3.** Se suma al procedimiento:
  «aplicar una variante cambia sólo las variables de su tabla (se lee en `cambios`)». *Por qué*:
  endurece sin mover anclas ni pesos, y las corridas históricas no cambian de nota (sus
  variantes eran fotos del diseño vigente, así que ya cumplían). Si prefieres v3, se abre.

## Alternativas descartadas

- **Sólo el aviso, sin cambiar el modelo**: sin columnas no hay definición de «propia»; con una
  foto de 37 claves el aviso listaría todo lo que cambió desde julio, cada vez, y se ignoraría.
- **Diff contra la primera variante o contra una «base»**: depende del orden y de cuál se llame
  base; borrar la base cambia el significado de las demás.
- **Fecha por variable y avisar si cambió después de guardar la variante**: más estado, y sigue
  revirtiendo; sólo lo anuncia.
- **Subir `FORMAT_VERSION` a 3**: un Apolo viejo dejaría de abrir el archivo ENTERO por un
  metadato. La bandera degrada bien.
- **Forma nueva `{variante: {"values": …, "propias": […]}}`**: rompe escena, brief, golden y UI
  sin ganar nada sobre la tabla rectangular.
- **Script único sobre `data/apolo.db`**: no alcanza revisiones restauradas ni `.apolo` sueltos
  (el paquete es público en PyPI).
- **Podar la columna al borrar la variable**: los metadatos no viajan en el undo; deshacer el
  borrado no devolvería la columna. Se ignora al aplicar (D6) y se quita con ✕ (D7).

## Fases

| fase | qué | paquete | tamaño | depende de | se verifica con |
|---|---|---|---|---|---|
| F0 | Medir variantes en la SQLite y revisiones | — | S | — | hecha: tabla de arriba |
| F1 | `doc/variantes.py` puro (columnas, relleno, guardar, editar, diff, migración) + `Document` delega + bandera en el manifest | doc | M | — | pytest; trinquete de `document.py` baja |
| F2 | API: `variables` en el POST, `cambios`/`aviso` en el apply, `DELETE /api/configuration-columns/{v}`; MCP `save_configuration(values)` y `cambios` en la salida; golden re-congelado | api, mcp | M | F1 | pytest (rutas, guardia, golden, catálogo) |
| F3 | `VariablesDialog` + `api.ts` (D9) | ui | M | F2 | `npm test` + `npm run build` + preview por DOM |
| F4 | E2E sobre COPIA de la base: abrir 38 → migra a `{largo_total}`; cambiar una variable ajena; aplicar 3.2m y volver → la ajena intacta y el resto bit-idéntico; rúbrica E1.4, `doc/CLAUDE.md`, devlog, bitácora | doc, docs | S | F1–F3 | API en otro puerto + `scripts/e2e_mcp.py` |

**F1 en detalle** — tests nuevos en `tests/test_variantes.py`:
- regresión del caso 38: guardar variante, cambiar una variable que no es columna, aplicar → no
  se revierte;
- relleno D2 al agregar columna; «aplicar A, aplicar B» vuelve bit-idéntico;
- primera variante sin `variables` → error con el texto accionable;
- migración: 2 variantes que difieren en 1 variable → 1 columna; 1 variante → diff contra el
  log; variantes idénticas → sin columnas; clave de variable borrada → fuera; manifest con
  bandera → intacto (idempotente); ida y vuelta `.apolo` conserva la bandera.

Se reescriben los tests que fijan la semántica vieja: `test_product.py:56-218`,
`test_open_briefing.py:34`, `test_guardia_documento.py:45`.

Reparto: la sesión principal revisa; cada fase la implementa un subagente (`opus`, worktree
aislado, segundo plano) con prompt autocontenido. Al volver: diff contra este contrato y re-correr
las suites una por una.

## Lo que este plan NO hace

- No agrega `useConfirmar` (confirmar antes de aplicar): `ui/CLAUDE.md` pide un plan propio para
  crearlo. La columna «actual» y la celda resaltada muestran qué va a cambiar.
- No vincula variantes y variables («variante activa» que se actualiza sola al editar una
  variable): una variante sigue siendo explícita, como hoy.
- No hace CSV de variantes (pendiente de V6.4, fuera de alcance).
- No toca el log de comandos ni la geometría: un log viejo regenera igual. No hay bump de caché.

## Riesgos

| riesgo | mitigación |
|---|---|
| Con ≥ 2 variantes guardadas en fechas distintas, una variable de diseño que cambió entre ambas queda como columna y la trampa sigue para ésa | `cambios` la muestra al aplicar; la UI la enseña como fila y se quita con ✕ |
| Un Apolo viejo guarda el archivo y pierde la bandera → se re-migra | con ≥ 2 variantes, sólo se pierde una columna cuyos valores ya eran iguales en todas (inocuo) |
| Romper a quien llama `save_configuration(name)` sobre un proyecto sin variantes | el error dice exactamente qué pasar; el docstring del MCP lo explica |
| `document.py` o `mcp_server.py` crecen y el trinquete rebota | la lógica vive en `doc/variantes.py`; el docstring del MCP se reescribe sin sumar líneas |
| El briefing de un proyecto grande crece | las variantes ralas pesan poco (38: 2 × 1 clave contra 2 × 37 hoy) |

## Bitácora

- **F0 (2026-10-06)**: lectura de `data/apolo.db` en modo sólo lectura. Resultado en la tabla de
  «El problema». Hallazgo: el arreglo a mano de hoy volvió a guardar fotos completas porque el
  `PUT` sobre un nombre nuevo parte de todas las variables.
