---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: contrato escrito; falta que Mario lo apruebe o vete decisiones (D1–D7)
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
  de medición, corre la prueba de sesión fresca (D7) y el pytest completo. Verifica: test en
  verde y al menos 18 de 20 preguntas correctas.

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

(vacía hasta cerrar F0)
