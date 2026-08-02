# Harness de auto-mejora — loop maestro → ejecutor ciego → auditor → implementador

**Origen**: pedido del usuario (2026-08-02). Formaliza y AUTOMATIZA el ciclo que ya
ocurrió una vez a mano y demostró funcionar: el test de generalización del camastro
(sesión fresca + un solo prompt → proyecto 71) fue el «ejecutor», su auditoría fue el
«auditor», y las mejoras que ordenó son el plan V6.9. Este harness convierte ese ciclo
en un loop repetible donde el humano solo aprueba, no opera.

**Doctrina**: lo que se mide es el PRODUCTO tal como lo ve un cliente MCP ciego — el
ejecutor recibe únicamente el prompt + las tools/instrucciones que Apolo publica (el
`design_brief` inyectado en las instrucciones MCP ES parte del producto). Las mejoras
aterrizan en DOS lugares: el código de Apolo (rama del experimento) y el prompt (el
«manual de pedido» que un cliente real escribiría). La convergencia la declara un
scorecard con números, no una impresión.

**Decisión de plataforma** (verificada en esta máquina, CLI 2.1.141):
**Claude Code headless (`claude -p`)**, NO Claude Desktop, NO el Agent SDK (todavía).
- Cada `claude -p` es un PROCESO fresco: sesión virgen y cliente MCP re-registrado al
  arrancar → tras cambiar código de Apolo solo se reinicia la instancia B de la API
  (scriptable); **el paso «reinicia Claude Desktop y espérame» desaparece**.
- La transcripción queda en JSONL (`~\.claude\projects\<workspace>\<session>.jsonl`) →
  el auditor cuenta llamadas, errores y lotes revertidos con evidencia, no de memoria.
- El SDK queda como migración futura SI el loop pide paralelismo/orquestación fina; el
  diseño de roles es el mismo, migrar no tira nada.

**Criterio de hecho**: infraestructura (scripts + plantillas + runbook) + UNA campaña
completa con ≥2 iteraciones medidas y su serie de scorecards en `docs/experiments/`,
al menos una mejora de Apolo landeada en la rama con tests+tortura verdes, y CLAUDE.md
actualizado al cierre.

---

## Arquitectura de roles (4, con fronteras duras)

| Rol | Quién | Ve | No ve |
|---|---|---|---|
| **Orquestador** | Sesión Claude Code interactiva en el repo | Todo | — |
| **Ejecutor** | `claude -p` en workspace AISLADO | Prompt + tools MCP de la instancia B | El maestro, el repo, CLAUDE.md, este plan |
| **Auditor** | `claude -p` fresco (contexto limpio, sin sesgo del implementador) | Transcript del ejecutor + artefactos del run + artefactos del maestro + rúbrica | El código de las mejoras en curso |
| **Implementador** | El orquestador en la rama `exp/<slug>` | Todo | — |

El auditor NO es ciego (compara contra el maestro a propósito); el ejecutor SÍ.
Auditor ≠ implementador para que quien califica no califique su propio trabajo.

## A. Aislamiento — instancia B + workspace del ejecutor  `[barato — cero código de Apolo]`

Todo lo necesario ya existe (verificado en código):
- **Instancia B de la API**: `$env:APOLO_DB` (api/main.py:356) apunta la SQLite a un
  archivo del experimento y `start-apolo.ps1 -Port 8001` la levanta aparte. El maestro
  vive SOLO en la instancia A (8000, la del usuario) → **la caja negra es por
  construcción**: el ejecutor no puede abrir lo que su servidor no tiene.
- **Cliente MCP del ejecutor**: el server fino ya se configura por `APOLO_URL`
  (.mcp.json) → un config propio apuntando a `http://127.0.0.1:8001`.
- **Workspace del ejecutor FUERA del repo** (p. ej.
  `C:\Users\adminlocal\source\apolo-experiments\<slug>\workspace\`). GOTCHA que obliga
  a esto: el CLI carga CLAUDE.md del cwd Y de los directorios PADRE — un workspace
  dentro del repo heredaría todo el CLAUDE.md del proyecto (historia de los maestros,
  gotchas, roadmap) y contaminaría el experimento. Fuera del árbol, el ejecutor solo ve
  el prompt y las instrucciones MCP.
- **MCP en headless sin diálogo de confianza**: pasar el config explícito —
  `claude -p --mcp-config apolo-b.json --strict-mcp-config
  --allowedTools "mcp__apolo-cad__*"` (rutas ABSOLUTAS en el config: el
  `.venv\Scripts\python.exe` relativo del repo no resuelve desde el workspace).

Cinturón adicional anti-copia: el auditor verifica en el transcript que no hubo
llamadas sospechosas (list_projects/open_project sobre ids ajenos). Con la instancia
aislada es redundante — se deja porque es gratis.

## B. El ejecutor — corrida ciega y reproducible  `[medio]`

`scripts/experiment/run_executor.ps1` hace, por corrida:
1. Copia la DB semilla limpia a `data\experiments\<slug>-it<N>-run<k>.db` (una DB POR
   CORRIDA: cada resultado queda congelado y el auditor puede re-abrirlo después).
2. Levanta la instancia B contra esa DB (verificando el DUEÑO real del socket — gotcha
   zombie-socket :8001, mismo protocolo que el :8000 documentado en CLAUDE.md).
3. Lanza `claude -p "<prompt-vN>"` desde el workspace con: `--model` FIJO (misma
   familia toda la campaña — sin esto la varianza entre modelos ensucia la serie),
   `--max-turns` como presupuesto duro, `--output-format json` (da `session_id` →
   localiza el transcript JSONL), `--mcp-config/--strict-mcp-config/--allowedTools`.
4. Al terminar, EXPORTA los artefactos del run vía REST contra la instancia B:
   `get_scene(summary)`, BOM, masas, interferencias, renders (4 vistas fijas + iso),
   `delivery_check` cuando exista (V6.9), y copia el transcript a la carpeta del run.
5. Apaga la instancia B.

N corridas por iteración: **default 2, sube a 3 si los scorecards de las 2 difieren
más que el margen que la rúbrica declare** (los agentes son estocásticos; una corrida
única convierte suerte en «mejora»). Se compara la MEDIANA entre iteraciones.

## C. El auditor — scorecard con números y veredicto  `[medio]`

Invocación fresca (`claude -p` o subagente) con: la rúbrica versionada, el transcript
de cada run, los artefactos de cada run y los del MAESTRO (exportados una vez al abrir
la campaña, desde la instancia A). Produce `scorecard.json` por corrida + un
`veredicto.md` por iteración.

**Scorecard (schema fijo, versionado con la rúbrica)**:
- `proceso`: n_llamadas (total y por tool), n_errores de tool/API, n_lotes_revertidos
  (ContractError), n_turnos, tiempo de pared.
- `resultado`: n_sólidos, masa total, diff de BOM vs maestro, bbox global,
  interferencias, grounds/fasten DECLARADOS, semáforo `delivery_check` (cuando exista),
  y **checklist de fidelidad al prompt** (el auditor la deriva del prompt en la
  iteración 0 y queda congelada — la vara no se mueve entre iteraciones).
- `anticopia`: verificación del transcript (bool + evidencia).
- `juicio_visual`: renders lado a lado maestro/run con nota del auditor.

**Veredicto por iteración** (mediana de los runs vs iteración anterior):
- `MEJORAR`: lista RANKEADA de mejoras, cada una etiquetada `CODIGO` | `PROMPT` |
  `AMBOS`, con la evidencia del scorecard que la motiva.
- `CONVERGIDO`: **2 iteraciones consecutivas sin mejora medible en las medianas** (el
  «creo que ya no se puede mejorar» del usuario, vuelto criterio duro).
- `ABORTAR`: el experimento está mal planteado (prompt ambiguo, maestro con defecto) —
  se reporta al usuario, no se «arregla» en silencio.

La rúbrica (`rubrica-exp-v1.md`) la VALIDA el usuario en la iteración 0 y solo cambia
con nueva versión + razón escrita (mismo régimen que la rúbrica del benchmark V7.1).

## D. El implementador — rama del experimento  `[según hallazgos]`

- Rama `exp/<slug>` desde main al abrir la campaña; TODA la campaña vive ahí (pedido
  explícito del usuario: «con este nos quedamos hasta cumplir el objetivo»). El merge a
  main lo aprueba el usuario al cierre.
- Mejoras de CÓDIGO con el criterio de la casa: tests + tortura verdes antes de la
  siguiente iteración. Mejoras de PROMPT como `prompt-vN.md` versionado (el prompt es
  un entregable del experimento tanto como el código).
- **Regla de generalidad**: una mejora NO puede nombrar particulares del maestro
  («si es un camastro…») — debe ser una regla/tool/mensaje que sirva a cualquier
  proyecto. El overfitting al testigo es el riesgo n.º 1 documentado del benchmark.
- Tras cambios de código: reiniciar instancia B (la A del usuario no se toca). El
  ejecutor siguiente ya nace con MCP fresco — nada más que reiniciar.

## E. Protocolo de la campaña

```
0. PREPARACIÓN (con el usuario): maestro elegido → export de artefactos del maestro ·
   prompt-v1 · rúbrica validada · rama exp/<slug> · workspace + DB semilla · presupuesto
   (máx iteraciones / máx corridas).
1. EJECUTAR: N corridas ciegas (B).
2. AUDITAR: scorecards + veredicto (C).
3. Si MEJORAR → implementar en la rama (D) → reiniciar instancia B → volver a 1.
   Si CONVERGIDO → control de generalización: correr el prompt de una tarea DISTINTA
   (espejo del «segundo testigo» del benchmark) para verificar que las mejoras no son
   overfitting → informe final → usuario aprueba merge.
   Si ABORTAR → informe y parada.
```

Costo honesto a presupuestar: una corrida tipo camastro ≈ 30–60 min; una iteración
completa (2-3 corridas + auditoría + implementación) ≈ 3–4 horas de máquina. El loop es
autónomo pero no barato — el presupuesto lo fija el usuario en el paso 0.

## Persistencia (espejo de `docs/benchmark/`)

```
docs/experiments/<slug>/
  INDEX.md                  ← serie de iteraciones, veredictos, estado
  rubrica-exp-v1.md
  maestro/                  ← artefactos exportados del maestro (renders, BOM, scene)
  prompt-v1.md, prompt-v2.md, …
  it1/run1/  scorecard.json · transcript.jsonl · renders/ · artefactos/
  it1/veredicto.md
  it2/…
```

La DB de cada run queda en `data\experiments\` (fuera de git, como `data/apolo.db`).

## Qué hay que construir (orden; Apolo core: CERO cambios)

1. `scripts/experiment/new_campaign.ps1` — scaffold: carpeta del experimento +
   workspace externo con su `apolo-b.json` (rutas absolutas) + DB semilla + rama.
2. `scripts/experiment/run_executor.ps1` — el ciclo B completo (instancia B por run,
   `claude -p`, recolección de transcript + artefactos, apagado limpio).
3. Plantilla del prompt del AUDITOR + `scorecard.schema.json`.
4. `docs/experiments/README.md` — runbook del orquestador (cómo se corre el loop, qué
   aprueba el usuario y cuándo).

Estimación: 1 sesión de implementación; los tres cimientos (APOLO_DB, APOLO_URL,
-Port) ya existen y están verificados.

## Primera campaña propuesta (decisión del usuario en el paso 0)

- **Opción A — camastro-playa (70)**: baseline GRATIS (la corrida manual del
  2026-08-02 = iteración 0 ya auditada: 46 min, 0 errores de tool, pero cremalleras
  flotantes y 0 sujeción declarada). Sinergia directa: **la mejora n.º 1 de la
  iteración 1 sería implementar V6.9 dentro de la rama del experimento** — y el harness
  MIDE si `delivery_check` + la alarma ambiental cambian el resultado del ejecutor
  ciego. V6.9 dejaría de validarse solo con testigos estáticos: se validaría con el
  experimento vivo que lo originó.
- **Opción B — maestro nuevo preparado por el usuario** (su paso 0 original): más
  limpio como experimento, sin baseline previo.

## Riesgos declarados

- **Varianza estocástica** → N corridas + modelo fijo + mediana (nunca una corrida).
- **Overfitting al maestro** → regla de generalidad (D) + control final con tarea
  distinta (E).
- **Auditor complaciente** → rúbrica dura versionada con anclas numéricas + auditor
  separado del implementador + checklist de fidelidad congelada en iteración 0.
- **Atribución ambigua** (¿mejoró el código o el prompt?) → cada mejora va etiquetada;
  cuando la atribución importe, corrida A/B opcional (prompt viejo + código nuevo).
- **Costo** → presupuesto explícito del paso 0; el loop DECLARA gasto acumulado en
  INDEX.md tras cada iteración.

## NO hacer (anti-sobreingeniería)

- **NO Claude Desktop en el loop** — el reinicio manual mata la autonomía; Desktop
  queda como cliente del usuario, no del harness.
- **NO SDK todavía** — migrar solo si el CLI se queda corto (paralelismo real,
  orquestación programática fina); el diseño de roles sobrevive la migración.
- **NO tocar la instancia A (8000) ni `data/apolo.db`** — el harness vive en su puerto
  y sus DBs; los maestros del usuario son sagrados.
- **NO mejoras que nombren al maestro** — regla de generalidad (D).
- **NO auto-merge a main** — el merge final lo aprueba el usuario, siempre.
- **NO empezar por el SDK/paralelismo/dashboard** — primero UNA campaña completa con
  scripts simples; la infraestructura crece cuando el loop demuestre que la pide.
