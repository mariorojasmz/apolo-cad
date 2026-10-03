---
estado: implementado   # implementado | en curso | sin verificar | descartado
nota: sin pendientes (D7 aprobada 20/20; no medido: sesión arrancada dentro de un worktree)
descripcion: Cada sesión del agente arranca con un CLAUDE.md de ≤ 30 KB; el detalle de cada paquete se lee sólo al trabajar en él
---

# Poda del CLAUDE.md — cada sesión arranca leyendo sólo lo que necesita

## Estado y origen

Pedido de Mario (2026-10-03): «dale, arranca con el plan de poda del CLAUDE.md». Viene de
adoptar la cultura de Caronte (commit `1ac7eba`), cuya regla fija **raíz ≤ 30 KB, CLAUDE.md de
subpaquete ≤ 35 KB** («se cargan en cada sesión: cada línea cuesta»). Al adoptarla quedó
declarado en el propio CLAUDE.md que hoy pesa cuatro veces eso.

## El problema / lo que hay hoy

**125,1 KB** en UTF-8 (129,6 KB en disco con CRLF) = **4,2× la meta**. Medido por sección
(script `medir_claude.py`, se versiona en F4):

| Sección | KB | Qué es |
|---|---:|---|
| Mapa del sistema | 58,1 | qué existe y dónde, por paquete; mezcla trampas durables con firmas derivables del código y crónica («E2E faja 38», «testigo…») |
| — Planos 2D | 15,9 | |
| — Ensamblaje / cinemática / validación física | 13,5 | |
| — Comandos / modelado | 8,1 | |
| — Kernel / percepción del agente | 7,8 | |
| — Ingeniería / negocio | 6,4 | |
| — Sub-ensamblajes · catálogo · materiales · UI | 6,2 | |
| Convenciones y lecciones | 23,5 | las reglas durables (lo más valioso) mezcladas con historia; 6,2 KB son de UI |
| Madurez (benchmarks) | 7,2 | crónica: serie de calificaciones 62 % → 82,8 % |
| Hojas de ruta V5 / V6 / V7 | 15,1 | crónica: ya vive en los 26 planes con frontmatter |
| Pendientes | 5,6 | ya está, en buena parte, en la `nota:` de cada plan |
| Arquitectura, escala, ejecutar, distribución | 5,9 | se queda |
| Gestión, planes, worktrees, publicación | 8,0 | se queda (es la cultura recién adoptada) |
| Doctrina de resultados, fuera de alcance | 1,6 | se queda |

**Ya se podó una vez y volvió a crecer**: 177 KB (2026-07-01) → poda `b22f5e8` «CLAUDE.md a
dieta» → 76 KB (2026-07-15) → 107 KB (2026-08-01) → 125 KB hoy. 82 commits tocaron el archivo.
Sin un gate, la poda dura un mes.

**Deriva medida** (síntoma de un archivo demasiado grande para mantenerse): «217 refs» vs 231
reales y «7-tupla» vs la 8-tupla del código (corregidos en `3e935f4`); el GIF del motion figura
«sin tool MCP» y `motion_gif` existe (`core/apolo/mcp_server.py:961`).

## Lo que se revisó antes de escribir esto

- **Nadie lee el CLAUDE.md por programa**: grep en `*.py/*.ps1/*.ts/*.json/*.toml` sólo encuentra
  una mención en un comentario de `ui/src/textoDeAyuda.test.ts`. Moverlo no rompe herramientas.
- **El producto no depende de él**: la `design_brief()` del MCP y el `SYSTEM_PROMPT` del agente
  de la app son otra fuente (`core/apolo/design/guidelines.py`, `core/apolo/agent/prompts.py`).
  La poda cambia lo que leen las sesiones de desarrollo, no lo que ve un cliente.
- **La crónica ya tiene casa**: los 26 planes tienen frontmatter con `nota:` de pendientes
  (commit `1ac7eba`) y existe `docs/devlog.md` para la narrativa.
- **Cómo se cargan los CLAUDE.md anidados NO está confirmado.** Una consulta a la documentación
  (fuentes indirectas, sin acceso a la página oficial) dice que se cargan a pedido al leer
  archivos de su carpeta, sin certeza sobre `Grep`/`Glob`, subagentes ni worktrees. **D2 depende
  de eso, así que no se asume: F0 lo mide.**

## Decisiones (para vetar)

- **D1. Topes con gate desde el día 1**: raíz ≤ 30 KB y cada CLAUDE.md anidado ≤ 35 KB, en
  bytes UTF-8 con LF. Los hace cumplir `tests/test_claude_md.py`, que falla si se pasan. Sin
  trinquete: la poda deja todo dentro del tope. Porqué: la poda de julio sin gate volvió a crecer.
- **D2. El mapa va a CLAUDE.md por paquete**: `core/apolo/{kernel,commands,doc,assembly,library,
  drawing,fea,api}/CLAUDE.md`, y lo de UI a `ui/CLAUDE.md` (ya existe). Cada uno se lee sólo al
  trabajar en su paquete. Lo transversal se queda en la raíz: locks, invariantes del log,
  disciplina paramétrica, Windows, flujo de trabajo. **Condicionado a F0**: si los anidados no
  se cargan de forma confiable, el plan B es `docs/mapa/<paquete>.md`, con un índice en la raíz
  que diga «antes de tocar X, lee `docs/mapa/X.md`».
  *Ajuste tras F0 (ver Bitácora)*: se suma `core/apolo/CLAUDE.md` para lo común del backend
  que no tiene paquete propio (`mcp_server.py`, `agent/`, `design/`, `robotics/`, `physics/`).
  Como un anidado carga también al leer archivos de sus subcarpetas, este llega a toda sesión
  que lea backend: se mantiene chico (≤ 10 KB). Una regla va donde se hace el CAMBIO, no donde
  vive el código que la sufre: el bump de `GEOM_CACHE_EPOCH` queda en la raíz porque se olvida
  al editar un executor, no al leer `doc/geomcache.py`; el otro anidado lleva sólo el link.
- **D3. La crónica sale de la raíz**:
  - **Madurez** → `docs/benchmark/README.md`: la serie de calificaciones y la reserva.
  - **Hojas de ruta V5–V7** → `docs/roadmap.md`: una línea por versión con link a su plan.
  - **Narrativa sin casa** (no está en su plan ni en el devlog) → se agrega a `docs/devlog.md`.
  - **Pendientes** → la `nota:` del plan que corresponde. Lo que no tiene plan va a `docs/backlog.md`.
- **D4. Nada se borra sin destino.** Cada párrafo sale a un lugar con link. Sólo se borra lo
  **derivable del código** (una firma o un nombre de función que un grep encuentra) o lo
  **obsoleto verificado**. Lo no derivable (el porqué, la trampa, la decisión) queda en una línea.
- **D5. «Una línea = qué hacer + link al porqué»** también en los anidados: una trampa se
  escribe como regla más link al plan o commit. Un nombre de función se menciona sólo si es
  el punto de entrada.
- **D6. La deriva se corrige al mover**: los errores medidos más los que aparezcan, cada uno
  verificado contra el código.
- **D7. Verificación con una sesión fresca**: antes de mover nada se escriben unas 20
  preguntas cuya respuesta vive hoy en el CLAUDE.md. Por ejemplo: «¿por qué no usar
  `boolean_op` en una pieza con juntas?», «¿qué hay que hacer si un executor cambia la
  geometría con los mismos params?», «¿cómo se detecta el zombie-socket de :8000?». Después de
  la poda, un subagente sin contexto las responde trabajando como una sesión real. Si acierta
  menos de 18 de 20, la fase no cierra.

## Alternativas descartadas

- **Comprimir sin mover**: el mapa solo ocupa 58 KB; aun a la mitad, no entra en 30 KB.
- **Un único `docs/arquitectura.md` sin carga automática**: las trampas dejarían de estar en
  contexto justo cuando hacen falta, al tocar el paquete. Es el plan B, no el A.
- **`@import` desde la raíz**: lo importado se carga igual al arrancar, así que el costo por
  sesión no baja.
- **Borrar la historia**: casi toda ya vive en los planes, el devlog y git. Lo que no, se
  mueve; no se pierde.

## Fases

Cada fase la implementa un subagente opus en su worktree. La sesión principal revisa el diff
contra este contrato y vuelve a correr las verificaciones.

- **F0 — mide (sólo lectura, S).** Depende de: nada. Hace tres cosas:
  - **Inventario:** tabla párrafo por párrafo con tipo (regla / mapa / crónica / pendiente /
    derivable / obsoleto) y destino. La tabla tiene que sumar los 125 KB.
  - **Prueba de carga:** un CLAUDE.md con un token canario en una carpeta de prueba. Se abre
    una sesión `claude -p` fresca desde la raíz que lee un archivo de esa carpeta, primero
    con `Read` y después sólo con `Grep`, en el árbol principal y en un worktree. Se anota si
    el canario aparece y se borra la carpeta de prueba.
  - **Preguntas de D7:** se escriben con su respuesta esperada.

  Verifica: inventario completo y resultado de la carga anotado en la bitácora; ahí se
  confirma D2 o se pasa al plan B.
- **F1 — anidados (M).** Depende de F0. Mueve el mapa y las convenciones de cada paquete a su
  CLAUDE.md (o a `docs/mapa/`), en formato D5. Verifica: cada anidado ≤ 35 KB y ningún párrafo
  del mapa sin destino (el inventario de F0 queda marcado).
- **F2 — crónica (M).** Depende de F0. Arma `docs/roadmap.md`, `docs/benchmark/README.md` y
  `docs/backlog.md`, completa las notas de los planes y agrega al devlog. Verifica: un script
  confirma que cada link relativo existe.
- **F3 — raíz (M).** Depende de F1 y F2. Reescribe la raíz: lo transversal en formato D5, el
  índice de los anidados y el «Estado actual». Corrige la deriva (D6). Verifica: ≤ 30 KB.
- **F4 — gates (S).** Depende de F3. Agrega `tests/test_claude_md.py` (D1) junto con el script
  de medición y corre el pytest completo. Después de mergear F1–F4 a `main`, corre la prueba de
  sesión fresca (D7) con `claude -p` desde el árbol principal: un subagente de una sesión ya
  abierta NO sirve, porque recibe el CLAUDE.md que se cargó cuando arrancó esa sesión
  (medido en F0). Verifica: test en verde y al menos 18 de 20 preguntas correctas; si no,
  se corrige hacia adelante.
  `poda-claude-md-preguntas.md` (preguntas con respuesta esperada) **no se commitea hasta
  después de D7**: si estuviera en `main`, el verificador podría encontrarlo con un grep.

## Lo que este plan NO hace

- No cambia código del producto ni la `design_brief`, el `SYSTEM_PROMPT` o las instrucciones
  del MCP.
- No toca la memoria automática de Claude (`MEMORY.md`), aunque repite parte del contenido.
- No reescribe los planes viejos: sólo completa su `nota:`.
- No agrega la regla de 500 líneas por archivo. Es una pregunta aparte de Mario, y es código.

## Riesgos

- **Se pierde una trampa y una sesión futura repite el error.** Mitigación: D4, el inventario
  de F0 marcado y las preguntas de D7.
- **Los anidados no se cargan cuando hacen falta** (por ejemplo, una sesión que sólo hace
  grep). Mitigación: F0 lo mide antes de mover nada, lo transversal queda en la raíz, y está
  el plan B.
- **Otra sesión edita CLAUDE.md durante la poda.** Mitigación: rama corta y rebase justo antes
  del merge. Si hay conflicto, el cambio ajeno se vuelve a aplicar en su nuevo destino.
- **Una regla queda en la raíz y en un anidado, y las copias divergen.** Mitigación: «una
  explicación, un lugar»; la raíz enlaza, no repite.

## Bitácora

**2026-10-03 — aprobación.** Mario: «dale, aprobado; agrega también la regla de 500 líneas».
Sin vetos. La regla de 500 líneas va en un commit aparte (es código: trinquetes en pytest y
vitest), no en este plan.

**2026-10-03 — F0 (b), prueba de carga (medida, no supuesta).** Carpeta `tmp_canario/` con un
`CLAUDE.md` con token canario y una subcarpeta con otro, dentro de un worktree:

| Prueba | Resultado |
|---|---|
| `Grep` sobre la subcarpeta (incluso con match dentro del CLAUDE.md) | **no** carga el anidado |
| `Read` de un archivo de la carpeta | **sí**: llega `CANARIO-RAIZ-7Q2` como memoria |
| `Read` de un archivo de la subcarpeta | **sí**: llega `CANARIO-SUB-4K9` |
| Sesión dentro de un worktree | carga los anidados **del worktree** (las rutas de arriba eran del worktree) |
| Subagente sin aislamiento, cwd = el worktree | carga el CLAUDE.md raíz **del checkout principal**, una vez; no hereda los anidados ya cargados por la sesión padre |
| Subagente con `isolation: "worktree"` | igual: raíz del checkout principal, una vez |

Consecuencias:
- **D2 confirmada** (plan A): un CLAUDE.md por paquete llega a quien LEE un archivo del
  paquete, que es lo que hace toda sesión antes de editarlo. No llega a quien sólo busca con
  `Grep`: por eso lo transversal se queda en la raíz.
- **La raíz que leen los subagentes y las sesiones en worktree es la de `main`**: un cambio al
  CLAUDE.md raíz en un worktree no rige para nadie hasta mergearse. Va como regla en
  «Sesiones concurrentes» en F3.
- No hay doble carga de la raíz en un worktree (la del worktree no se suma a la del
  principal), así que no hace falta mitigar eso.
- **No medido**: una sesión de Claude Code ARRANCADA desde dentro de un worktree (no un
  subagente). Si en F4 aparece, se mide con la misma carpeta canario.

**2026-10-03 — F0 (a)(c) cerrada.** Inventario en `poda-claude-md-inventario.md`: 198 bloques,
128 075 bytes, igual al archivo. Por tipo (KB): regla de paquete 63,7 · crónica 23,0 · regla
transversal 11,2 · cultura 10,2 · mapa 9,5 · pendiente 6,2 · derivable 0,8 · obsoleto 0,4.
Proyección: raíz ~22 KB; anidados de core 2,4–6,7 KB; `ui/CLAUDE.md` ~15 KB. Las 20 preguntas
de D7 están escritas (archivo fuera de git, ver F4). Deriva verificada contra el código, se
corrige en F1–F3:
- «sin tool MCP» para el GIF de movimiento es falso (`mcp_server.py:961`).
- Cuatro conteos viejos de tools (hoy 79).
- «15 normas» son 16, y «0.6·σy» es 0.5 (`rules.py:927`).
- `_hole_fit_map` global lo reemplazó `api/main.py:4604`.
- `isAxisAligned` es código muerto (`handles.ts:82`); `applySaveTint` y `preview_eval` no existen.

Lo que F0 cambió del contrato:
1. **Un anidado carga también al leer un archivo de una subcarpeta suya** (medido: un `Read`
   en `tmpc2/hijo/` trajo el CLAUDE.md de `tmpc2/`, aunque `hijo/` no tenía uno). Así,
   `library/CLAUDE.md` cubre `library/engineering/`, y se puede tener un `core/apolo/CLAUDE.md`
   para lo común del backend (ajuste en D2).
2. **Los subagentes reciben el CLAUDE.md raíz que se cargó cuando arrancó la sesión padre**,
   no el archivo actual. El de F0 recibió el texto viejo («1355 tests · 217 refs · 7-tupla»)
   aunque `main` y el árbol principal ya tenían el corregido. Por eso D7 corre con `claude -p`
   y no con un subagente (ajuste en F4).
3. Las `nota:` de V6.2e y V6.3d y `docs/devlog.md:2836` apuntan a «§ Pendientes», que se va:
   F2 las redirige a `docs/backlog.md`.

**2026-10-03 — F1, anidados (commit `890db44`).** El mapa y las convenciones de paquete salen a
diez CLAUDE.md anidados en formato D5. Tamaños (UTF-8, LF): `core/apolo` 4,1 KB (tope 10) ·
`kernel` 3,9 · `commands` 5,0 · `doc` 5,4 · `assembly` 3,2 · `library` 9,0 · `drawing` 6,4 ·
`fea` 3,2 · `api` 11,0 · `ui` 14,9 (tenía 9,2) = 66 KB en total, ninguno cerca del tope de 35.
Sale lo derivable (listas de params, firmas `wants_*`, tabla de GDL, valores de K, conteos de
familias, lista de paneles) y los números de E2E. Deriva corregida: `motion_gif` sí es tool;
fuera los conteos viejos de tools; 16 normas, no 15; eje a 0.5·σy, no 0.6·σy; `_hole_fit_map`
ya no es global; gotcha muerto de `infer_process`; `isAxisAligned`, `applySaveTint` y
`preview_eval` fuera de la UI. **Desvíos del inventario**, por la regla «la regla va donde se
hace el CAMBIO»: la FK, el GIF del estudio y la física van a `core/apolo/CLAUDE.md` (no a
`assembly/`, porque el código vive en `robotics/` y `physics/`); los mapas de fit, datum, GD&T,
tolerancias e instalación van a `api/` (viven en `api/main.py`; `drawing/` sólo enlaza); la
validación de fotogramas a `doc/`; `anchor_loads`, el par de apriete y los ingletes a `library/`.

**2026-10-03 — F2, crónica (commit `d182ade`).** Nacen `docs/roadmap.md` (12,8 KB: una línea por
versión V5–V7 con link al plan, o devlog + commit si no hay plan), `docs/benchmark/README.md`
(9,2 KB: cómo se corre, ejes de madurez, serie 62 → 82,8 %, reserva y segundo testigo) y
`docs/backlog.md` (6,8 KB). Al devlog van la cura del 38 a VERDE y la historia del GIF (no tenían
casa); las `nota:` de V6.2e y V6.3d y `devlog:2836` apuntan ahora al backlog. **Desvío**: las
filas #193–#197 iban a la bitácora de V6.2e/V6.4d/V6.5/V6.5e; fueron a `docs/backlog.md` con link
al plan de origen, porque el contrato dice que a los planes viejos sólo se les completa la
`nota:`. Deriva corregida al mover: el manual por grafo de soporte ya existe y el par de apriete
ya se calcula (salen del backlog como pendientes); V7 figura cerrada; el peso del cajetín
multi-sólido se corrigió el mismo día.

**2026-10-03 — F3, raíz.** El CLAUDE.md raíz pasa de 125,3 KB (128 318 bytes en `890db44`, con BOM)
a **26,7 KB** (27 380 bytes UTF-8 con LF, sin BOM; 407 líneas). Por sección (KB): encabezado 0,6
· arquitectura 1,9 · escala 0,9 · ejecutar + distribución + estado 2,3 · índice de anidados 2,2
· gestión 1,5 · planes 3,6 · sesiones concurrentes 3,7 · publicación 0,5 · reglas transversales
7,7 (locks 0,7 · log y regenerate 2,0 · paramétrico 1,3 · cirugía 1,1 · criterio de diseño 1,6
· Windows 1,1) · doctrina 0,9 · punteros a roadmap/benchmark/backlog 0,7 · fuera de alcance 0,4.
Queda sólo lo que el inventario manda a la raíz; el mapa, las convenciones de paquete, la
madurez, las hojas de ruta y los pendientes se reemplazan por el índice y por punteros. Lo
nuevo: el índice con la regla de carga medida («antes de editar, lee con `Read` un archivo del
paquete»), los dos hechos de F0 en «Sesiones concurrentes» (los subagentes reciben la raíz del
arranque de la sesión padre; en un worktree rige la raíz del checkout principal → verificar con
`claude -p` tras el merge) y «Gestión» con los topes reales en vez del aviso de ~130 KB.
Conteos verificados contra el código: 1375 tests (111 archivos, `--collect-only` con el
`PYTHONPATH` del worktree) + 15 de tortura · 18 tests vitest (3 archivos) · 79 `@mcp.tool` · 53
comandos (`len(REGISTRY)`) · 231 `ref:` en el catálogo. Deriva corregida: 1370 → 1375 tests;
«FEA multicuerpo fuera de alcance» (el bonded de ensamblaje existe desde V7.4); «V6 cerrado»
→ V1–V7 cerradas; la frase de `ui_dist()` «antes ganaba SIEMPRE la empaquetada» era crónica;
regionalismos de la cultura («saltear», «se triá», «recién ahí», «acá») pasan a español neutro.
**Por encima de la proyección de ~22 KB**: las secciones de cultura (planes + sesiones, 7,3 KB)
quedaron enteras porque el contrato sólo permite comprimirlas si hace falta para el tope, y el
índice pesa 2,2 KB. Si el gate de F4 aprieta, la palanca siguiente es la del inventario: la
plantilla de planes a `docs/plans/README.md` (−1,5 KB) y la receta de robocopy a un doc aparte
(−0,6 KB). Ningún anidado se tocó en F3.

**2026-10-03 — F4 (gate).** `tests/test_claude_md.py` (stdlib, no importa `apolo`): raíz ≤ 30 KB,
`core/apolo/CLAUDE.md` ≤ 10 KB, otros anidados ≤ 35 KB, y todo link relativo de un CLAUDE.md
existe (agregado al contrato: la poda creó ~100 links y un link roto es una trampa perdida). El
script de medición es el mismo archivo (`python tests/test_claude_md.py` imprime los tamaños;
el `medir_claude.py` de F0 queda fuera del repo). Verificado que falla: un anidado de 35,2 KB
con un link roto dio los dos errores. Tamaños al cerrar: raíz 26,7 · `core/apolo` 4,1 · api
11,0 · assembly 3,2 · commands 5,0 · doc 5,4 · drawing 6,4 · fea 3,2 · kernel 3,9 · library
9,0 · ui 14,9 KB. Suite: 1379 tests (1375 + 4 del gate). Falta D7: corre con `claude -p`
después del merge a `main`.

**2026-10-03 — D7, sesión fresca: APROBADA, 20/20.** Mario mergeó `f3cde4e` a `main`. Se corrió
`claude -p` desde el árbol principal, sólo con `Read`/`Grep`/`Glob`, sin MCP y con prohibido
leer `docs/` y `.claude/`. El archivo de respuestas esperadas se sacó del árbol antes de correr.
Salida textual en [poda-claude-md-d7-respuestas.md](poda-claude-md-d7-respuestas.md).

Calificación contra [las respuestas esperadas](poda-claude-md-preguntas.md): **20 de 20
correctas en lo esencial** (el umbral era 18). Cinco omiten un detalle secundario: la 1 (avisar
por WebSocket después del payload), la 14 (el fit del eje va en el nombre), la 16 (la guardia
de proyecto del FEA), la 18 (`_project_switch`) y la 20 (debounce de 250 ms). Se verificó con
grep que las cinco reglas omitidas están en algún CLAUDE.md (raíz, `api`, `fea` o `library`):
la sesión no las mencionó, pero la poda no las perdió.

La sesión cargó, en orden, el CLAUDE.md global, la raíz y los 10 anidados. Esto confirma en una
sesión real lo que F0 midió con canarios. Las dos preguntas que el inventario marcaba en riesgo
pasaron:
- la 10 (FK, archivos en `robotics/`) la respondió desde `core/apolo/CLAUDE.md`;
- la 7 (bump de `GEOM_CACHE_EPOCH`) la respondió desde la raíz.

Un tropiezo operativo: la primera corrida falló con `OAuth session expired`. La CLI necesitaba
un `/login`, que hizo Mario, y no hubo cambio de plan.
