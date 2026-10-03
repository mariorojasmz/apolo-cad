# Poda del CLAUDE.md — inventario bloque por bloque (F0 a)

Anexo de [poda-claude-md.md](poda-claude-md.md). Es el mapa para los que mueven (F1–F3): cada
bloque del `CLAUDE.md` raíz con su tipo y su destino exacto. Nadie movió nada todavía.

## Cómo se midió

- Archivo: `CLAUDE.md` del worktree `poda-claude-md` en `78c30dd` (= `main`), 1539 líneas.
- Bytes en **UTF-8 con LF y sin BOM** (la vara de D1). KB = bytes / 1024.
- Un **bloque** = cada viñeta de nivel superior (`- ` en columna 0, con sus líneas indentadas),
  cada párrafo, cada bloque de código y cada lista numerada. Un encabezado se suma al primer
  bloque que lo sigue; las líneas en blanco, al bloque anterior. Así la suma de bloques es
  exactamente el archivo.
- **Suma de la columna KB (valores redondeados a 1 decimal): 124,7 KB · tamaño del archivo: 125,07 KB (128 075 bytes UTF-8 con LF y sin BOM; 129 617 en disco con BOM y CRLF). Suma exacta de los bytes de los 198 bloques: 128 075 = el archivo.**
- `líneas` son las del archivo actual. `sección` = sección › subsección donde vive hoy.
- `destino`: archivo + sección propuesta; con varios destinos, el % del bloque que va a cada uno.
  «borrar» siempre lleva el motivo.
- `nota`: deriva verificada (con `archivo:línea`), qué es derivable (y qué grep lo encuentra) y
  cuánto queda tras comprimir en formato D5 («Queda: kernel ~40 %» = de ese bloque queda ~40 %
  en el anidado de kernel; lo que sale es crónica que ya vive en su plan/devlog/commit, o algo
  derivable del código). Sin «Queda», el bloque se muda casi entero.

## Estructura propuesta de cada destino

Secciones en el orden en que aparecen en la tabla, con los bloques que reciben. F1/F3 pueden
reordenar, no repartir distinto sin anotarlo aquí.

- **`CLAUDE.md`**: Encabezado (#1, #2) · Arquitectura (#3, #4, #5, #6, #7, #8, #9) · Escala (#10) · Ejecutar y probar (#11, #13, #15, #121) · Distribución (#12) · Estado actual (#14) · Gestión de los CLAUDE.md (#16, #17, #18, #19, #20) · Planes (#21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33) · Sesiones concurrentes (#34, #35, #36, #37, #38, #39, #40, #41, #42, #43, #44, #45, #46) · Publicación (#47) · Índice de CLAUDE.md por paquete (#48) · Log de comandos y regenerate (#84, #108, #109, #111, #117, #119, #125) · Reglas transversales (encabezado) (#106) · Concurrencia y locks (#107, #113) · Paramétrico y modelado (#123, #126, #129) · Cirugía de modelos (#130, #131, #132, #133, #134) · Criterio de diseño (lecciones) (#135, #136, #137, #138, #139, #140, #141, #142) · Windows y operación (#143, #144, #145, #146, #147) · Doctrina de resultados (#157, #158, #159, #160) · Fuera de alcance (#198).
- **`core/apolo/kernel/CLAUDE.md`**: Render y percepción (#49, #50, #51) · Superficies (#58) · Modelado directo (#59) · Croquis (#60).
- **`core/apolo/commands/CLAUDE.md`**: Mapa de comandos (#62) · Super-comandos (#63) · Conectividad (#64) · join_bolted (#65) · transform_group (#67) · Colocación declarativa (#74) · add_joint (#75) · Errores accionables de OCCT (#122) · Expresiones (#124).
- **`core/apolo/doc/CLAUDE.md`**: insert_project (#70) · Caché de geometría (#111) · Integridad y robustez (#115, #116, #117, #118, #119) · Variantes (#125).
- **`core/apolo/assembly/CLAUDE.md`**: Cinemática y contratos en pose (#57, #73, #76) · Grupos (#66, #69) · Mates (#71, #72) · Conectividad (#77) · Física (#79).
- **`core/apolo/library/CLAUDE.md`**: Chapa (#61) · Puerta de entrega (#78) · Interferencias (#82) · Ingeniería (#83, #91, #92) · Stack-up (#84) · Reglas de conveyor (#85) · Requisitos (#86) · Materiales (#99) · Catálogo (#100, #101, #102, #127) · Builders (#128).
- **`core/apolo/drawing/CLAUDE.md`**: Entregables (#87) · Mapa (#89) · Último kilómetro (#90) · Manual de ensamblaje (#91, #98) · Fit por pieza, proceso y matchers (#93) · Datum, GD&T y tolerancias (#94, #95, #96) · Instalación (#97).
- **`core/apolo/fea/CLAUDE.md`**: FEA de pieza (#80) · FEA de ensamblaje (#81).
- **`core/apolo/api/CLAUDE.md`**: Retorno de mutaciones (#52) · Lotes con contrato (#53, #57) · Jobs asíncronos (#54) · Lecturas a escala (#55, #56, #68) · Tests de la API (#110) · Deltas de escena (#112) · Render y física fuera del lock (#113) · Autosave (#114, #120).
- **`ui/CLAUDE.md`**: Desarrollo y verificación (#15, #149) · Croquis (SketcherDialog) (#60) · Shell y paneles (#103, #104, #105) · Sync de escena (#112) · Layout (#148) · Sync con el servidor (#150, #151, #152) · Viewport (#153, #154, #155, #156).
- **`docs/roadmap.md`**: V6 (#162, #163, #164, #165, #166, #167, #168, #169, #170, #171, #172, #173, #174) · Fuera de versión (#175) · V7 (#176, #177, #178, #179, #180, #181, #182, #183, #184) · V5 (#185).
- **`docs/benchmark/README.md`**: Cómo se corre (#88) · Serie de calificaciones y reserva (#161).
- **`docs/backlog.md`**: Ensamblaje y cinemática (#69, #186) · Validación (#188) · Geometría y catálogo (#189) · Física (#190) · Ingeniería y negocio (#191) · UI (#192).
- **`docs/devlog.md`**: 2026-08-03 cura del 38 (#78).
- **`docs/plans/V6.2e-fixes-revision.md`**: nota (ya lista 3); bitácora el resto (#197).
- **`docs/plans/V6.3-ensamblaje-pro.md`**: nota (ya está) (#186).
- **`docs/plans/V6.3d-fixes-revision.md`**: nota/bitácora (ya está) (#187).
- **`docs/plans/V6.4-parametrico-profundo.md`**: nota: (1)(2)(4) ya están (#193).
- **`docs/plans/V6.4d-remate-revision.md`**: bitácora: (3)(5) (#193).
- **`docs/plans/V6.5-mcp-a-escala.md`**: nota (1)(2) ya; bitácora (3)-(6) (#194).
- **`docs/plans/V6.5e-mcp-jobs-asincronos.md`**: nota (1) ya; bitácora (2)(3) (#195).
- **borrar**: ya en plan V7.2b + devlog:3582 (#92) · nada pendiente (#196).

## Inventario

| # | líneas | KB | sección | resumen | tipo | destino | nota |
|---:|---|---:|---|---|---|---|---|
| 1 | 1-8 | 0,4 | Genix Apolo CAD | Qué es Apolo, stack y modelo de IA por defecto | mapa | `CLAUDE.md` § Encabezado | `claude-opus-4-8` verificado en `core/apolo/agent/agent.py:20`. Queda: raíz ~90 %. |
| 2 | 9-13 | 0,3 | Genix Apolo CAD | Aviso: la historia vive en devlog y git | cultura | `CLAUDE.md` § Encabezado | comprimir: lo repite #18; queda una frase. Queda: raíz ~40 %. |
| 3 | 14-17 | 0,2 | Arquitectura (principios que NO se negocian) | API-first: UI, chat y MCP son clientes iguales | regla-transversal | `CLAUDE.md` § Arquitectura |  |
| 4 | 18-20 | 0,2 | Arquitectura (principios que NO se negocian) | Documento = log de comandos; .apolo sin geometría | regla-transversal | `CLAUDE.md` § Arquitectura |  |
| 5 | 21-27 | 0,6 | Arquitectura (principios que NO se negocian) | Schema-driven, MCP thin, lotes con contrato `expect` | regla-transversal | `CLAUDE.md` § Arquitectura | comprimir: el detalle de `expect` vive en #53 (api). Queda: raíz ~70 %. |
| 6 | 28-30 | 0,2 | Arquitectura (principios que NO se negocian) | Expresiones `=expr`; variables en la cabecera del log | regla-transversal | `CLAUDE.md` § Arquitectura |  |
| 7 | 31-32 | 0,1 | Arquitectura (principios que NO se negocian) | Selectores declarativos de aristas/caras | regla-transversal | `CLAUDE.md` § Arquitectura |  |
| 8 | 33-34 | 0,2 | Arquitectura (principios que NO se negocian) | Plantillas de máquina son super-comandos, no scripts | regla-transversal | `CLAUDE.md` § Arquitectura |  |
| 9 | 35-42 | 0,5 | Arquitectura (principios que NO se negocian) | Criterio de ingeniería por defecto; fuente única guidelines.py | regla-transversal | `CLAUDE.md` § Arquitectura | comprimir a 2 líneas; nombres derivables (`grep "def design_brief"` → `core/apolo/design/guidelines.py:222`). Queda: raíz ~60 %. |
| 10 | 43-52 | 0,6 | Escala — mandato de arquitectura | Escala: fronteras limpias entre paquetes, sin estado global | regla-transversal | `CLAUDE.md` § Escala |  |
| 11 | 53-60 | 0,3 | Ejecutar y probar | Cómo levantar la API, correr pytest y el build | regla-transversal | `CLAUDE.md` § Ejecutar y probar | «1370 tests» verificado: `pytest --collect-only` = 1370 en 110 archivos. |
| 12 | 61-73 | 1,1 | Ejecutar y probar › Distribución (público desde 2026-08-08) | Distribución: PyPI, registro MCP, paths.py, planegcs, release.py | mapa | `CLAUDE.md` § Distribución | la frase «antes ganaba SIEMPRE la empaquetada…» es crónica (commit `3e935f4`); marcador de planegcs verificado en `core/pyproject.toml:44`. Queda: raíz ~70 %. |
| 13 | 74-76 | 0,3 | Ejecutar y probar › Distribución (público desde 2026-08-08) | MCP apolo-cad: cliente fino, 79 tools, reiniciar host | regla-transversal | `CLAUDE.md` § Ejecutar y probar | 79 verificado: 79 × `@mcp.tool` en `core/apolo/mcp_server.py`. |
| 14 | 77-83 | 0,6 | Ejecutar y probar › Distribución (público desde 2026-08-08) | Estado actual: conteos y proyectos de referencia | mapa | `CLAUDE.md` § Estado actual | conteos verificados: 1370 tests, 79 tools, 53 = `len(REGISTRY)`, 231 = `len(load_catalog())`. La lista V6.1–V6.5 sale → `docs/roadmap.md`. Queda: raíz ~60 %. |
| 15 | 84-88 | 0,3 | Ejecutar y probar › Distribución (público desde 2026-08-08) | Preview de la UI en desarrollo y tests vitest | regla-paquete | `ui/CLAUDE.md` § Desarrollo y verificación (80 %) + `CLAUDE.md` § Ejecutar y probar (20 %) | configs verificadas en `.claude/launch.json:11,18`. Duplica #149 (StrictMode): una explicación, un lugar. Queda: ui ~80 %. |
| 16 | 89-93 | 0,2 | Gestión de los CLAUDE.md | Claude es dueño de los CLAUDE.md | cultura | `CLAUDE.md` § Gestión de los CLAUDE.md |  |
| 17 | 94-96 | 0,3 | Gestión de los CLAUDE.md | Topes de tamaño; aviso de que la raíz pesa ~130 KB | cultura | `CLAUDE.md` § Gestión de los CLAUDE.md | obsoleto tras F3: se borra «⚠️ Hoy la raíz pesa ~130 KB… próximo plan»; la meta pasa a «anidados ≤ 35 KB» + gate `tests/test_claude_md.py`. Queda: raíz ~60 %. |
| 18 | 97-100 | 0,3 | Gestión de los CLAUDE.md | Una línea = qué hacer + link al porqué | cultura | `CLAUDE.md` § Gestión de los CLAUDE.md |  |
| 19 | 101-103 | 0,2 | Gestión de los CLAUDE.md | Nivel más específico gana; sólo lo no derivable | cultura | `CLAUDE.md` § Gestión de los CLAUDE.md | F3: generalizar «lo de la UI va en ui/CLAUDE.md» a cada paquete (enlaza al índice). |
| 20 | 104-106 | 0,1 | Gestión de los CLAUDE.md | Un solo formato de instrucciones: CLAUDE.md | cultura | `CLAUDE.md` § Gestión de los CLAUDE.md |  |
| 21 | 107-113 | 0,4 | Planes (`docs/plans/`) | Cuándo un cambio necesita plan | cultura | `CLAUDE.md` § Planes |  |
| 22 | 114-117 | 0,3 | Planes (`docs/plans/`) | Nombre del plan = versión del roadmap | cultura | `CLAUDE.md` § Planes |  |
| 23 | 118-125 | 0,3 | Planes (`docs/plans/`) | Frontmatter del plan: estado, nota, descripción | cultura | `CLAUDE.md` § Planes |  |
| 24 | 126-129 | 0,2 | Planes (`docs/plans/`) | Título del plan dicho como lo diría el usuario | cultura | `CLAUDE.md` § Planes |  |
| 25 | 130-141 | 0,8 | Planes (`docs/plans/`) | Secciones del plan en orden fijo | cultura | `CLAUDE.md` § Planes |  |
| 26 | 142-142 | 0,0 | Planes (`docs/plans/`) | Rótulo «Reglas» | cultura | `CLAUDE.md` § Planes |  |
| 27 | 143-147 | 0,4 | Planes (`docs/plans/`) | Contrato aprobado antes; reservar la versión en main | cultura | `CLAUDE.md` § Planes |  |
| 28 | 148-149 | 0,1 | Planes (`docs/plans/`) | El estado es el frontmatter, no la carpeta | cultura | `CLAUDE.md` § Planes | verificado: `docs/plans/` ya no tiene `done/`. |
| 29 | 150-151 | 0,1 | Planes (`docs/plans/`) | La `nota:` se actualiza al mergear y publicar | cultura | `CLAUDE.md` § Planes |  |
| 30 | 152-153 | 0,2 | Planes (`docs/plans/`) | Plan sin commits en tres semanas se triá | cultura | `CLAUDE.md` § Planes |  |
| 31 | 154-156 | 0,2 | Planes (`docs/plans/`) | Documentar el razonamiento: bitácora, regla, commit | cultura | `CLAUDE.md` § Planes |  |
| 32 | 157-159 | 0,1 | Planes (`docs/plans/`) | Índice de planes sólo generado por script | cultura | `CLAUDE.md` § Planes |  |
| 33 | 160-166 | 0,5 | Planes (`docs/plans/`) | Reparto contrato/implementación con subagentes en worktree | cultura | `CLAUDE.md` § Planes |  |
| 34 | 167-171 | 0,2 | Sesiones concurrentes: worktree para escribir código | Varias sesiones a la vez: aislar con worktree | cultura | `CLAUDE.md` § Sesiones concurrentes | F3 agrega aquí la regla de la bitácora F0 (b): la raíz que leen subagentes y worktrees es la de `main`. |
| 35 | 172-173 | 0,1 | Sesiones concurrentes: worktree para escribir código | Toda sesión que escribe código usa EnterWorktree | cultura | `CLAUDE.md` § Sesiones concurrentes |  |
| 36 | 174-176 | 0,2 | Sesiones concurrentes: worktree para escribir código | EnterWorktree nace de origin/main: merge main --ff-only | cultura | `CLAUDE.md` § Sesiones concurrentes |  |
| 37 | 177-182 | 0,5 | Sesiones concurrentes: worktree para escribir código | Python en worktree prueba el principal: PYTHONPATH + -B | cultura | `CLAUDE.md` § Sesiones concurrentes |  |
| 38 | 183-184 | 0,2 | Sesiones concurrentes: worktree para escribir código | Subagentes que editan van con isolation worktree | cultura | `CLAUDE.md` § Sesiones concurrentes |  |
| 39 | 185-186 | 0,1 | Sesiones concurrentes: worktree para escribir código | Revisar lo staged antes de commitear | cultura | `CLAUDE.md` § Sesiones concurrentes |  |
| 40 | 187-189 | 0,2 | Sesiones concurrentes: worktree para escribir código | Editar siempre dentro del worktree; cómo rescatarlo | cultura | `CLAUDE.md` § Sesiones concurrentes |  |
| 41 | 190-190 | 0,1 | Sesiones concurrentes: worktree para escribir código | Un comando git por llamada dentro del worktree | cultura | `CLAUDE.md` § Sesiones concurrentes |  |
| 42 | 191-193 | 0,2 | Sesiones concurrentes: worktree para escribir código | npm ci en el worktree; suites de a una | cultura | `CLAUDE.md` § Sesiones concurrentes |  |
| 43 | 194-199 | 0,3 | Sesiones concurrentes: worktree para escribir código | Rebasar justo antes del merge, siempre ff-only | cultura | `CLAUDE.md` § Sesiones concurrentes |  |
| 44 | 200-202 | 0,2 | Sesiones concurrentes: worktree para escribir código | main avanza: el conflicto lo resuelve el agente | cultura | `CLAUDE.md` § Sesiones concurrentes |  |
| 45 | 203-212 | 0,6 | Sesiones concurrentes: worktree para escribir código | Borrar node_modules; robocopy ante «Filename too long» | cultura | `CLAUDE.md` § Sesiones concurrentes |  |
| 46 | 213-216 | 0,2 | Sesiones concurrentes: worktree para escribir código | No borrar un worktree que es cwd de sesión viva | cultura | `CLAUDE.md` § Sesiones concurrentes |  |
| 47 | 217-223 | 0,3 | Publicación | Publicación sólo desde main con release.py | cultura | `CLAUDE.md` § Publicación |  |
| 48 | 224-225 | 0,0 | Mapa del sistema (qué existe y dónde) | Encabezado «Mapa del sistema» | mapa | `CLAUDE.md` § Índice de CLAUDE.md por paquete | lo reemplaza el índice de anidados (+~1,3 KB nuevos en la proyección). |
| 49 | 226-234 | 0,7 | Mapa del sistema (qué existe y dónde) › Kernel / percepción del agente | Render VTK/matplotlib y parámetros de render_view | mapa | `core/apolo/kernel/CLAUDE.md` § Render y percepción | la lista de params es derivable (firma de `render_view` en `core/apolo/mcp_server.py`, `grep vtk_only`). Queda: render.py = fallback, `resolve_angles` fuente única de cámara, xray legible sólo con 2-3 piezas. Queda: kernel ~40 %. |
| 50 | 235-237 | 0,2 | Mapa del sistema (qué existe y dónde) › Kernel / percepción del agente | Pick exacto: pasar los mismos params que render_view | regla-paquete | `core/apolo/kernel/CLAUDE.md` § Render y percepción | Queda: kernel ~80 %. |
| 51 | 238-241 | 0,3 | Mapa del sistema (qué existe y dónde) › Kernel / percepción del agente | Medición, topología y dry-runs para elegir selectores | derivable | `core/apolo/kernel/CLAUDE.md` § Render y percepción | derivable: `def measure_distance` (`kernel/measure.py:11`), `def feature_topology` (`kernel/topology.py:108`); queda 1 línea con el para qué. Queda: kernel ~40 %. |
| 52 | 242-247 | 0,5 | Mapa del sistema (qué existe y dónde) › Kernel / percepción del agente | Retorno compacto detail=diff; edit_command hace PATCH superficial | regla-paquete | `core/apolo/api/CLAUDE.md` § Retorno de mutaciones | crónica «957 KB → 350 bytes» sale. El «merge superficial: position se reemplaza entera» se repite en #133 y #150: una explicación, un lugar. Queda: api ~60 %. |
| 53 | 248-264 | 1,5 | Mapa del sistema (qué existe y dónde) › Kernel / percepción del agente | Lotes con contrato expect: rollback, $k 1-indexado, sugerencias | regla-paquete | `core/apolo/api/CLAUDE.md` § Lotes con contrato | crónica V6.5c («antes: sin piezas silencioso») → ya en `docs/plans/V6.5c-fixes-revision.md`. Verificados `_suggest_ids` (`api/main.py:619`) y `_open_briefing` (`api/main.py:884`). Queda: api ~50 %. |
| 54 | 265-284 | 1,8 | Mapa del sistema (qué existe y dónde) › Kernel / percepción del agente | Jobs asíncronos: recibo, lock hoja, 404 tras reload, guardia | regla-paquete | `core/apolo/api/CLAUDE.md` § Jobs asíncronos | verificado `_RETENTION = 20` (`api/jobs.py:29`) y `APOLO_MCP_WAIT_S` 90 (`mcp_server.py:29`). ⚠️ la mitad cliente vive en `core/apolo/mcp_server.py` (fuera de `api/`). Queda: api ~60 %. |
| 55 | 285-296 | 1,1 | Mapa del sistema (qué existe y dónde) › Kernel / percepción del agente | Lecturas acotadas: summary por grupo, paginación, <10 KB | regla-paquete | `core/apolo/api/CLAUDE.md` § Lecturas a escala | lista de params derivable de las firmas de tools; queda la regla «ninguna lectura de rutina vuelca la escena» + `get_scene()` sin params byte-idéntico (viewport). Queda: api ~50 %. |
| 56 | 297-305 | 0,8 | Mapa del sistema (qué existe y dónde) › Kernel / percepción del agente | Material/color y conexiones en lote; find_commands | mapa | `core/apolo/api/CLAUDE.md` § Lecturas a escala | queda «valida TODO antes de tocar (cero efectos parciales)»; «fin de las ~90 llamadas» es crónica → `docs/plans/V6.8-mcp-fluidez.md`. Queda: api ~40 %. |
| 57 | 306-315 | 0,8 | Mapa del sistema (qué existe y dónde) › Kernel / percepción del agente | Cinemática por MCP; aserciones evaluadas en pose | regla-paquete | `core/apolo/assembly/CLAUDE.md` § Cinemática y contratos en pose (60 %) + `core/apolo/api/CLAUDE.md` § Lotes con contrato (40 %) | trampa clave: junta desconocida → error (posed_shapes ignora nombres). Este bloque contradice a #76: aquí `motion_gif` sí es tool (correcto). Queda: assembly ~60 %, api ~50 %. |
| 58 | 316-327 | 1,0 | Mapa del sistema (qué existe y dónde) › Comandos / modelado (53 comandos) | Superficies: construcción fuera de BOM; tangent sólo suave | regla-paquete | `core/apolo/kernel/CLAUDE.md` § Superficies | «(53 comandos)» del encabezado verificado (`len(REGISTRY)` = 53), derivable. Queda: kernel ~50 %. |
| 59 | 328-338 | 0,9 | Mapa del sistema (qué existe y dónde) › Comandos / modelado (53 comandos) | Modelado directo: caras STEP REVERSED, no-op de OCCT | regla-paquete | `core/apolo/kernel/CLAUDE.md` § Modelado directo | `SetOffsetOnFace` NO-GO verificado como comentario en `core/apolo/kernel/direct.py:15`. Queda: kernel ~70 %. |
| 60 | 339-365 | 2,2 | Mapa del sistema (qué existe y dónde) › Comandos / modelado (53 comandos) | Croquis PlaneGCS/scipy, spline/elipse, arrastre y su UI | regla-paquete | `core/apolo/kernel/CLAUDE.md` § Croquis (65 %) + `ui/CLAUDE.md` § Croquis (SketcherDialog) (35 %) | deriva menor: «wheel cp313» — hoy el marcador es `python_version >= '3.12'` y no-Darwin (`core/pyproject.toml:44`). «npm run build limpio; la prueba la hace el usuario» → ya en la nota de `docs/plans/V6.6-croquis-vivo.md`. Queda: kernel ~55 %, ui ~50 %. |
| 61 | 366-376 | 0,9 | Mapa del sistema (qué existe y dónde) › Comandos / modelado (53 comandos) | Chapa: flaps, K por material, convención u/v en pestaña | regla-paquete | `core/apolo/library/CLAUDE.md` § Chapa | valores de K derivables (`K_FACTOR_BY_MATERIAL`, `core/apolo/library/sheetmetal.py:36`). Queda: library ~70 %. |
| 62 | 377-384 | 0,7 | Mapa del sistema (qué existe y dónde) › Comandos / modelado (53 comandos) | Primitivas, patrones y colocación relacional | mapa | `core/apolo/commands/CLAUDE.md` § Mapa de comandos | lista derivable de `REGISTRY`; quedan: add_joinery corta EN SITIO, pattern_group rechaza fuentes con juntas, snap_to se reevalúa. Queda: commands ~40 %. |
| 63 | 385-395 | 0,9 | Mapa del sistema (qué existe y dónde) › Comandos / modelado (53 comandos) | Super-comandos de máquina; documentar el MONTAJE | mapa | `core/apolo/commands/CLAUDE.md` § Super-comandos | queda la regla del description de montaje y «create_drive_roller = eje FIJO». Queda: commands ~50 %. |
| 64 | 396-398 | 0,2 | Mapa del sistema (qué existe y dónde) › Comandos / modelado (53 comandos) | fasten/ground: dimensionado; throat ES la garganta | regla-paquete | `core/apolo/commands/CLAUDE.md` § Conectividad |  |
| 65 | 399-413 | 1,3 | Mapa del sistema (qué existe y dónde) › Comandos / modelado (53 comandos) | join_bolted: barrenos de paso, tuerca, caras planas | regla-paquete | `core/apolo/commands/CLAUDE.md` § join_bolted | crónica «19 de 24 pernos» → ya en `docs/plans/V6.5b-mcp-accion-con-contrato.md`. Queda: commands ~50 %. |
| 66 | 414-422 | 0,7 | Mapa del sistema (qué existe y dónde) › Sub-ensamblajes (grupos de primera clase, V5.2 — 2026-07-01) | Grupos por command_id, anidables, campo derivado feat.group | regla-paquete | `core/apolo/assembly/CLAUDE.md` § Grupos | firma `wants_groups` derivable (`core/apolo/commands/registry.py:2051`); «8-tupla» coherente con #109. Queda: assembly ~70 %. |
| 67 | 423-428 | 0,4 | Mapa del sistema (qué existe y dónde) › Sub-ensamblajes (grupos de primera clase, V5.2 — 2026-07-01) | transform_group rota sobre el bbox conjunto | regla-paquete | `core/apolo/commands/CLAUDE.md` § transform_group | «verificado en la faja…» es crónica. `move_rotated_about` en `core/apolo/kernel/shapes.py:157`. Queda: commands ~60 %. |
| 68 | 429-431 | 0,3 | Mapa del sistema (qué existe y dónde) › Sub-ensamblajes (grupos de primera clase, V5.2 — 2026-07-01) | isolate/highlight/fit aceptan nombres de grupo | regla-paquete | `core/apolo/api/CLAUDE.md` § Lecturas a escala | deriva: «(62→64 — reiniciar host MCP)» es un conteo viejo (hoy 79 tools) → borrar. Queda: api ~50 %. |
| 69 | 432-440 | 0,7 | Mapa del sistema (qué existe y dónde) › Sub-ensamblajes (grupos de primera clase, V5.2 — 2026-07-01) | auto_group; manual, BOM y árbol por grupos | mapa | `core/apolo/assembly/CLAUDE.md` § Grupos (80 %) + `docs/backlog.md` § Ensamblaje y cinemática (20 %) | pendiente sin plan («V5.2b pendiente: role… drag&drop») → `docs/backlog.md`; «13 pasos → 6» es crónica. Queda: assembly ~40 %. |
| 70 | 441-458 | 1,4 | Mapa del sistema (qué existe y dónde) › Sub-ensamblajes (grupos de primera clase, V5.2 — 2026-07-01) | insert_project: snapshot embebido, editar B abriendo B | regla-paquete | `core/apolo/doc/CLAUDE.md` § insert_project | ⚠️ la materialización vive en `core/apolo/api/main.py:1063`; enlazar desde api. Queda: doc ~60 %. |
| 71 | 459-474 | 1,4 | Mapa del sistema (qué existe y dónde) › Ensamblaje / cinemática / validación física | Mates: multi-mate DAG, solver de dos caminos, conectores | regla-paquete | `core/apolo/assembly/CLAUDE.md` § Mates | Queda: assembly ~60 %. |
| 72 | 475-481 | 0,6 | Mapa del sistema (qué existe y dónde) › Ensamblaje / cinemática / validación física | Reporte de DOF: conteo heurístico de Grübler | mapa | `core/apolo/assembly/CLAUDE.md` § Mates | tabla de GDL derivable de `core/apolo/assembly/dof.py:32`. Queda: assembly ~50 %. |
| 73 | 482-493 | 1,0 | Mapa del sistema (qué existe y dónde) › Ensamblaje / cinemática / validación física | Estudios de movimiento; FK sólo mueve hijos declarados | regla-paquete | `core/apolo/assembly/CLAUDE.md` § Cinemática y contratos en pose | ⚠️ la FK vive en `core/apolo/robotics/pose.py` (robotics no está en D2). Crónica «(2026-08-01)… antes se aceptaban» → plan V6.8. Queda: assembly ~70 %. |
| 74 | 494-508 | 1,3 | Mapa del sistema (qué existe y dónde) › Ensamblaje / cinemática / validación física | snap_to cara-a-cara y drill_hole por cara | regla-paquete | `core/apolo/commands/CLAUDE.md` § Colocación declarativa | Queda: commands ~60 %. |
| 75 | 509-518 | 0,8 | Mapa del sistema (qué existe y dónde) › Ensamblaje / cinemática / validación física | add_joint arrastrar: default False y flood por fijadores | regla-paquete | `core/apolo/commands/CLAUDE.md` § add_joint | verificado `wants_all=True` de add_joint en `core/apolo/commands/registry.py` (bloque de registro, ~l. 2122). Queda: commands ~60 %. |
| 76 | 519-528 | 0,9 | Mapa del sistema (qué existe y dónde) › Ensamblaje / cinemática / validación física | GIF del estudio de movimiento: cámara fija al recorrido | regla-paquete | `core/apolo/assembly/CLAUDE.md` § Cinemática y contratos en pose | **deriva**: «sin tool MCP (reiniciar host para añadirla)» es FALSO — `motion_gif` existe (`core/apolo/mcp_server.py:961`). ⚠️ código en `core/apolo/robotics/anim.py`. Queda: assembly ~40 %. |
| 77 | 529-531 | 0,3 | Mapa del sistema (qué existe y dónde) › Ensamblaje / cinemática / validación física | Conectividad y soundness: grafo con semilla de grounds | mapa | `core/apolo/assembly/CLAUDE.md` § Conectividad | Queda: assembly ~80 %. |
| 78 | 532-550 | 1,5 | Mapa del sistema (qué existe y dónde) › Ensamblaje / cinemática / validación física | delivery_check: semáforo, exclusiones unificadas, alarma ambiental | regla-paquete | `core/apolo/library/CLAUDE.md` § Puerta de entrega (75 %) + `docs/devlog.md` § 2026-08-03 cura del 38 (25 %) | verificados `MIN_SOLIDOS_SUJECION = 5` (`library/delivery.py:24`) y `EXCESS_TOL_MM3 = 50.0` (`library/checks.py:94`). «El 38 se CURÓ (2026-08-03)» no aparece en ningún archivo de `docs/` → narrativa sin casa → devlog. Queda: library ~50 %. |
| 79 | 551-553 | 0,2 | Mapa del sistema (qué existe y dónde) › Ensamblaje / cinemática / validación física | Física MuJoCo: gravity_test con cascos, drop_test | mapa | `core/apolo/assembly/CLAUDE.md` § Física | ⚠️ código en `core/apolo/physics/` (fuera de D2). Queda: assembly ~80 %. |
| 80 | 554-566 | 1,1 | Mapa del sistema (qué existe y dónde) › Ensamblaje / cinemática / validación física | FEA de pieza: gmsh no interrumpible, FEA_LOCK, guardar si mismo proyecto | regla-paquete | `core/apolo/fea/CLAUDE.md` § FEA de pieza | verificados `interruptible=False` (`fea/mesher.py:74`), `FEA_LOCK` (`fea/mesher.py:22`), `_persist_fea_if_same_project` (`api/main.py:3311`). Queda: fea ~70 %. |
| 81 | 567-613 | 4,1 | Mapa del sistema (qué existe y dónde) › Ensamblaje / cinemática / validación física | FEA bonded de ensamblaje: fragment, guarda de cuerpo rígido | regla-paquete | `core/apolo/fea/CLAUDE.md` § FEA de ensamblaje | mezcla ~60 % crónica (E2E faja 38, brechas 2+3, auditoría V7.4b) → ya en `docs/devlog.md:3772,3832` y planes V7.4/V7.4b. Verificado `MAX_PIECES = 25` (`fea/mesher.py:25`). Queda: fea ~35 %. |
| 82 | 614-617 | 0,2 | Mapa del sistema (qué existe y dónde) › Ensamblaje / cinemática / validación física | check_interference: exclusiones de juntas y tornillería | regla-paquete | `core/apolo/library/CLAUDE.md` § Interferencias |  |
| 83 | 618-643 | 2,1 | Mapa del sistema (qué existe y dónde) › Ingeniería / negocio (Frentes A/B) | library/engineering: banda, pernos, fits, roscas, pandeo, report | regla-paquete | `core/apolo/library/CLAUDE.md` § Ingeniería | deriva: «(65 tools — reiniciar host MCP)» es conteo viejo (hoy 79) → borrar. Quedan μ por construcción, fit del eje en el NOMBRE, k6 en UC = ERROR, broca publicada. Queda: library ~50 %. |
| 84 | 644-665 | 2,0 | Mapa del sistema (qué existe y dónde) › Ingeniería / negocio (Frentes A/B) | Stack-up peor caso+RSS; cadenas como metadato, no comando | regla-paquete | `core/apolo/library/CLAUDE.md` § Stack-up (85 %) + `CLAUDE.md` § Log de comandos y regenerate (15 %) | deriva: «53 comandos, 72 tools» — tools hoy 79. La invariante «metadato ≠ comando: rompería los checkpoints» es transversal → raíz. Queda: library ~50 %, raíz ~50 %. |
| 85 | 666-677 | 0,9 | Mapa del sistema (qué existe y dónde) › Ingeniería / negocio (Frentes A/B) | Reglas de conveyor: método de arrastre por construcción | regla-paquete | `core/apolo/library/CLAUDE.md` § Reglas de conveyor | «13 reglas» ≈ derivable: 13 nombres distintos de `_check(` en `core/apolo/library/rules.py`. Queda: library ~60 %. |
| 86 | 678-682 | 0,4 | Mapa del sistema (qué existe y dónde) › Ingeniería / negocio (Frentes A/B) | Requisitos del proyecto como metadato; checks caen a ellos | regla-paquete | `core/apolo/library/CLAUDE.md` § Requisitos | Queda: library ~80 %. |
| 87 | 683-687 | 0,4 | Mapa del sistema (qué existe y dónde) › Ingeniería / negocio (Frentes A/B) | Memoria, costeo con 3 fuentes declaradas, cotización | mapa | `core/apolo/drawing/CLAUDE.md` § Entregables | Queda: drawing ~60 %. |
| 88 | 688-695 | 0,6 | Mapa del sistema (qué existe y dónde) › Ingeniería / negocio (Frentes A/B) | Benchmark de entregables: cliente HTTP puro, rúbrica vigente | regla-paquete | `docs/benchmark/README.md` § Cómo se corre | 1 línea de link desde la doctrina de la raíz. |
| 89 | 696-710 | 1,2 | Mapa del sistema (qué existe y dónde) › Planos 2D (sistema PRO completo, fases A–G) | Sistema de planos: compositor, juego, DWG por ODA | mapa | `core/apolo/drawing/CLAUDE.md` § Mapa | verificados `_discover` (`drawing/dwg.py:35`) y `scripts/_check_overlaps.py` (existe). Queda: drawing ~50 %. |
| 90 | 711-734 | 2,2 | Mapa del sistema (qué existe y dónde) › Planos 2D (sistema PRO completo, fases A–G) | Último kilómetro V7.2: soldadura, ISO 2768, acabados, datum | regla-paquete | `core/apolo/drawing/CLAUDE.md` § Último kilómetro | **obsoleto**: el GOTCHA «la rama sierra exige component.category… (fix en V7.2b)» ya no aplica (`infer_process` en `drawing/process.py:117`, con `_is_revolution` en `:71`) y contradice #91. Testigo/porcentajes → `docs/benchmark/README.md`. Queda: drawing ~40 %. |
| 91 | 735-756 | 2,0 | Mapa del sistema (qué existe y dónde) › Planos 2D (sistema PRO completo, fases A–G) | V7.2b: manual por grafo de soporte, normas, lints, proceso | regla-paquete | `core/apolo/drawing/CLAUDE.md` § Manual de ensamblaje (55 %) + `core/apolo/library/CLAUDE.md` § Ingeniería (45 %) | **deriva**: «Norma en las 15 verificaciones» vs «16» de #180 (hay 16 entradas `"norma"` de cálculo: 10 en `library/rules.py:521-927`, 6 en `library/engineering/report.py:113-494`); «eje→0.6·σy (ASME B106.1M)» quedó viejo — `library/rules.py:927` cita 0.5·σy. Queda: drawing ~40 %, library ~35 %. |
| 92 | 757-770 | 1,3 | Mapa del sistema (qué existe y dónde) › Planos 2D (sistema PRO completo, fases A–G) | V7.2b live: eje del tensor g6, re-benchmark 74 % | crónica | `core/apolo/library/CLAUDE.md` § Ingeniería (20 %) + borrar — ya en plan V7.2b + devlog:3582 (80 %) | **obsoleto**: «`_hole_fit_map` es GLOBAL por Ø» lo superó V7.2c (`_feature_fit_maps`, `api/main.py:4604`). Queda 1 línea: eje fijo → g6 vía `create_take_up.eje_fit`. Queda: library ~50 %. |
| 93 | 771-801 | 2,9 | Mapa del sistema (qué existe y dónde) › Planos 2D (sistema PRO completo, fases A–G) | V7.2c: fit por pieza, revolución≠sierra, matchers por nombre | regla-paquete | `core/apolo/drawing/CLAUDE.md` § Fit por pieza, proceso y matchers | crónica de la re-auditoría → `docs/plans/V7.2c-fixes-re-auditoria.md`. ⚠️ los mapas de fit viven en `api/main.py:4604,4634`. Queda: drawing ~40 %. |
| 94 | 802-819 | 1,4 | Mapa del sistema (qué existe y dónde) › Planos 2D (sistema PRO completo, fases A–G) | Datum por cara funcional desde fasteners | regla-paquete | `core/apolo/drawing/CLAUDE.md` § Datum, GD&T y tolerancias | cirugía del modelo 38 = crónica (plan V7.5). Queda la trampa de la Feature sintética sin `material`. Queda: drawing ~40 %. |
| 95 | 820-838 | 1,6 | Mapa del sistema (qué existe y dónde) › Planos 2D (sistema PRO completo, fases A–G) | GD&T: marco sólo con perno identificable; ISO 273 invertida | regla-paquete | `core/apolo/drawing/CLAUDE.md` § Datum, GD&T y tolerancias | Queda: drawing ~50 %. |
| 96 | 839-852 | 1,1 | Mapa del sistema (qué existe y dónde) › Planos 2D (sistema PRO completo, fases A–G) | Tolerancia justificada por cadena; ISO 13920 en soldados | regla-paquete | `core/apolo/drawing/CLAUDE.md` § Datum, GD&T y tolerancias | Queda: drawing ~50 %. |
| 97 | 853-868 | 1,3 | Mapa del sistema (qué existe y dónde) › Planos 2D (sistema PRO completo, fases A–G) | Lámina de instalación: carga elástica por apoyo, excluir pernos | regla-paquete | `core/apolo/drawing/CLAUDE.md` § Instalación | `anchor_loads` en `library/engineering/installation.py:16`; testigo → benchmark. Queda: drawing ~50 %. |
| 98 | 869-879 | 0,9 | Mapa del sistema (qué existe y dónde) › Planos 2D (sistema PRO completo, fases A–G) | Manual: par de apriete calculado; orden por z de base | regla-paquete | `core/apolo/drawing/CLAUDE.md` § Manual de ensamblaje | «E5 3.00 → 3.625» → `docs/benchmark/README.md`. Queda: drawing ~50 %. |
| 99 | 880-889 | 0,7 | Mapa del sistema (qué existe y dónde) › Materiales (`library/materials.py`) | Materiales: especies antes que «madera»; MOR y FS ≥ 4 | regla-paquete | `core/apolo/library/CLAUDE.md` § Materiales | Queda: library ~80 %. |
| 100 | 890-894 | 0,3 | Mapa del sistema (qué existe y dónde) › Catálogo (data-driven, 231 refs) | Catálogo YAML + builders genéricos; param_keys del variant | regla-paquete | `core/apolo/library/CLAUDE.md` § Catálogo | «231 refs» verificado (`len(load_catalog())`). |
| 101 | 895-900 | 0,5 | Mapa del sistema (qué existe y dónde) › Catálogo (data-driven, 231 refs) | Familias clave del catálogo con conteos | derivable | `core/apolo/library/CLAUDE.md` § Catálogo | derivable: conteos por categoría salen de `load_catalog()` / YAML en `library/data/`; queda 1 línea (NMRV = builder `worm_gearmotor`). Queda: library ~30 %. |
| 102 | 901-904 | 0,2 | Mapa del sistema (qué existe y dónde) › Catálogo (data-driven, 231 refs) | Biblioteca paramétrica > STEP; costos referenciales | regla-paquete | `core/apolo/library/CLAUDE.md` § Catálogo |  |
| 103 | 905-913 | 0,7 | Mapa del sistema (qué existe y dónde) › UI web (React + three.js + Dockview) | Shell Dockview y paneles de la UI | mapa | `ui/CLAUDE.md` § Shell y paneles | lista de paneles derivable de `TOOL_PANELS` (`ui/src/dock/dockApi.ts:19`). Queda: ui ~50 %. |
| 104 | 914-915 | 0,1 | Mapa del sistema (qué existe y dónde) › UI web (React + three.js + Dockview) | Registrar un panel nuevo: cuatro lugares | regla-paquete | `ui/CLAUDE.md` § Shell y paneles | verificados `TOOL_PANELS` (`dockApi.ts:19`) y `PANEL_ICONS` (`ui/src/ui/icons.tsx:58`). |
| 105 | 916-918 | 0,2 | Mapa del sistema (qué existe y dónde) › UI web (React + three.js + Dockview) | Export glTF client-side por CustomEvent | mapa | `ui/CLAUDE.md` § Shell y paneles | Queda: ui ~80 %. |
| 106 | 919-920 | 0,0 | Convenciones y lecciones aprendidas | Encabezado «Convenciones y lecciones» | mapa | `CLAUDE.md` § Reglas transversales (encabezado) | pasa a encabezar las secciones transversales de la raíz. |
| 107 | 921-923 | 0,2 | Convenciones y lecciones aprendidas › Núcleo / rendimiento | OCCT no es thread-safe: todo bajo STATE_LOCK | regla-transversal | `CLAUDE.md` § Concurrencia y locks |  |
| 108 | 924-926 | 0,2 | Convenciones y lecciones aprendidas › Núcleo / rendimiento | Un lote = un regenerate; no validar en el bucle | regla-transversal | `CLAUDE.md` § Log de comandos y regenerate |  |
| 109 | 927-932 | 0,5 | Convenciones y lecciones aprendidas › Núcleo / rendimiento | Regenerate incremental: checkpoints, 8-tupla, metadatos fuera del log | regla-transversal | `CLAUDE.md` § Log de comandos y regenerate | verificados `_REGEN_STRIDE = 16` (`doc/document.py:143`) y la 8-tupla (deriva corregida en `3e935f4`). Queda: raíz ~80 %. |
| 110 | 933-938 | 0,4 | Convenciones y lecciones aprendidas › Núcleo / rendimiento | Tests sin lifespan; conftest redirige errors.log | regla-paquete | `core/apolo/api/CLAUDE.md` § Tests de la API | verificado `tests/conftest.py:14` (autouse, sesión). Queda: api ~80 %. |
| 111 | 939-962 | 2,2 | Convenciones y lecciones aprendidas › Rendimiento (V6.2 — mide contra `docs/perf_baseline.json`, host-dependiente) | Caché de geometría: bump de epoch, serialización robusta | regla-paquete | `core/apolo/doc/CLAUDE.md` § Caché de geometría (85 %) + `CLAUDE.md` § Log de comandos y regenerate (15 %) | verificados `GEOM_CACHE_EPOCH = 4` (`doc/geomcache.py:48`) y `_regen_ckpts[len-1]` (`:139`). La regla del bump es TRANSVERSAL (cualquier executor/builder) → 1 línea en la raíz. Queda: doc ~50 %, raíz ~50 %. |
| 112 | 963-975 | 1,2 | Convenciones y lecciones aprendidas › Rendimiento (V6.2 — mide contra `docs/perf_baseline.json`, host-dependiente) | Deltas de escena por identidad de shape; SCENE_EPOCH | regla-paquete | `core/apolo/api/CLAUDE.md` § Deltas de escena (70 %) + `ui/CLAUDE.md` § Sync de escena (30 %) | Queda: api ~60 %, ui ~60 %. |
| 113 | 976-982 | 0,6 | Convenciones y lecciones aprendidas › Rendimiento (V6.2 — mide contra `docs/perf_baseline.json`, host-dependiente) | Dos-locks: extraer bajo STATE_LOCK, procesar fuera | regla-transversal | `CLAUDE.md` § Concurrencia y locks (30 %) + `core/apolo/api/CLAUDE.md` § Render y física fuera del lock (70 %) | follow-up export_stl/drawing_spec ya está en la nota de `docs/plans/V6.2-rendimiento.md`. Queda: raíz ~80 %, api ~50 %. |
| 114 | 983-995 | 1,1 | Convenciones y lecciones aprendidas › Rendimiento (V6.2 — mide contra `docs/perf_baseline.json`, host-dependiente) | Autosave debounced; orden único _flush_lock → STATE_LOCK | regla-paquete | `core/apolo/api/CLAUDE.md` § Autosave | verificado `class _AutosaveScheduler` (`api/main.py:160`). Queda: api ~60 %. |
| 115 | 996-1002 | 0,6 | Convenciones y lecciones aprendidas › Robustez / integridad (V6.1 — «nada tumba el documento») | check_integrity read-only; health la expone | regla-paquete | `core/apolo/doc/CLAUDE.md` § Integridad y robustez | «sin tool MCP» para health: correcto (no hay tool health en `mcp_server.py`). Queda: doc ~60 %. |
| 116 | 1003-1005 | 0,3 | Convenciones y lecciones aprendidas › Robustez / integridad (V6.1 — «nada tumba el documento») | Modo estricto APOLO_STRICT; monkeypatch del atributo | regla-paquete | `core/apolo/doc/CLAUDE.md` § Integridad y robustez | verificado `doc/document.py:27-29`. |
| 117 | 1006-1010 | 0,4 | Convenciones y lecciones aprendidas › Robustez / integridad (V6.1 — «nada tumba el documento») | regenerate es atómico: locales y volcado final | regla-transversal | `CLAUDE.md` § Log de comandos y regenerate (50 %) + `core/apolo/doc/CLAUDE.md` § Integridad y robustez (50 %) | Queda: raíz ~80 %, doc ~80 %. |
| 118 | 1011-1015 | 0,4 | Convenciones y lecciones aprendidas › Robustez / integridad (V6.1 — «nada tumba el documento») | Snapshot de undo incluye la caché; undo peek-then-commit | regla-paquete | `core/apolo/doc/CLAUDE.md` § Integridad y robustez | verificado `_UNDO_CAP = 50` (`doc/document.py:119`). Queda: doc ~70 %. |
| 119 | 1016-1019 | 0,3 | Convenciones y lecciones aprendidas › Robustez / integridad (V6.1 — «nada tumba el documento») | Carga tolerante sólo en rutas de carga | regla-transversal | `CLAUDE.md` § Log de comandos y regenerate (40 %) + `core/apolo/doc/CLAUDE.md` § Integridad y robustez (60 %) | Queda: doc ~80 %. |
| 120 | 1020-1024 | 0,5 | Convenciones y lecciones aprendidas › Robustez / integridad (V6.1 — «nada tumba el documento») | Autosave durable: reintentos, AUTOSAVE_ERROR, STARTUP_ERROR | regla-paquete | `core/apolo/api/CLAUDE.md` § Autosave | verificado `_AUTOSAVE_RETRIES` (`api/main.py:90`). Queda: api ~70 %. |
| 121 | 1025-1028 | 0,3 | Convenciones y lecciones aprendidas › Robustez / integridad (V6.1 — «nada tumba el documento») | Tortura con marca; baseline de perf | regla-transversal | `CLAUDE.md` § Ejecutar y probar | verificado `-m "not torture"` en `pytest.ini:3`. Queda: raíz ~60 %. |
| 122 | 1029-1034 | 0,4 | Convenciones y lecciones aprendidas › Robustez / integridad (V6.1 — «nada tumba el documento») | Errores accionables de OCCT: fillet, chamfer, shell | regla-paquete | `core/apolo/commands/CLAUDE.md` § Errores accionables de OCCT | el código vive en `core/apolo/commands/registry.py:472-531` (no en kernel). Queda: commands ~70 %. |
| 123 | 1035-1043 | 0,7 | Convenciones y lecciones aprendidas › Paramétrico / modelado | Disciplina paramétrica; run_script ve V[...] | regla-transversal | `CLAUDE.md` § Paramétrico y modelado | «corregido en V6.4b» es crónica → sale. Queda: raíz ~70 %. |
| 124 | 1044-1047 | 0,3 | Convenciones y lecciones aprendidas › Paramétrico / modelado | Expresiones con ternario, comparadores y and/or | regla-paquete | `core/apolo/commands/CLAUDE.md` § Expresiones | Queda: commands ~80 %. |
| 125 | 1048-1056 | 0,8 | Convenciones y lecciones aprendidas › Paramétrico / modelado | Variantes: configurations; nunca puente implícito requisito→variable | regla-paquete | `core/apolo/doc/CLAUDE.md` § Variantes (75 %) + `CLAUDE.md` § Log de comandos y regenerate (25 %) | Queda: doc ~60 %, raíz ~50 %. |
| 126 | 1057-1059 | 0,2 | Convenciones y lecciones aprendidas › Paramétrico / modelado | Nombres por rol, no por medida | regla-transversal | `CLAUDE.md` § Paramétrico y modelado |  |
| 127 | 1060-1062 | 0,2 | Convenciones y lecciones aprendidas › Paramétrico / modelado | Componentes de catálogo: position y origen local | regla-paquete | `core/apolo/library/CLAUDE.md` § Catálogo |  |
| 128 | 1063-1066 | 0,3 | Convenciones y lecciones aprendidas › Paramétrico / modelado | Builders: Pos(...) primero; solapar 0.5–8 mm | regla-paquete | `core/apolo/library/CLAUDE.md` § Builders |  |
| 129 | 1067-1073 | 0,5 | Convenciones y lecciones aprendidas › Paramétrico / modelado | Caja orientada: el cabeceo se invierte con Δx<0 | regla-transversal | `CLAUDE.md` § Paramétrico y modelado | se queda en la raíz: aplica al escribir run_script por MCP, sin Read de ningún paquete. Queda: raíz ~60 %. |
| 130 | 1074-1077 | 0,3 | Convenciones y lecciones aprendidas › Cirugía de modelos (event-sourced) | Cirugía: borrar el sub-grafo completo de comandos | regla-transversal | `CLAUDE.md` § Cirugía de modelos | Queda: raíz ~80 %. |
| 131 | 1078-1080 | 0,2 | Convenciones y lecciones aprendidas › Cirugía de modelos (event-sourced) | Nunca boolean_op sobre una pieza con juntas | regla-transversal | `CLAUDE.md` § Cirugía de modelos |  |
| 132 | 1081-1082 | 0,1 | Convenciones y lecciones aprendidas › Cirugía de modelos (event-sourced) | Anular un corte moviendo el tool fuera | regla-transversal | `CLAUDE.md` § Cirugía de modelos |  |
| 133 | 1083-1084 | 0,1 | Convenciones y lecciones aprendidas › Cirugía de modelos (event-sourced) | position por REST se reemplaza entera | regla-transversal | `CLAUDE.md` § Cirugía de modelos | repite #52 y #150: dejar una sola explicación (raíz) y enlazar. |
| 134 | 1085-1089 | 0,3 | Convenciones y lecciones aprendidas › Cirugía de modelos (event-sourced) | Lotes grandes por HTTP: usar run_batch/edit_batch | obsoleto | `CLAUDE.md` § Cirugía de modelos | **obsoleto parcial**: «el timeout ≥540 s quedó OBSOLETO» ya no aporta (V6.5e: jobs con recibo, `_sync_or_job` en `api/main.py:1115`); queda 1 línea. Queda: raíz ~40 %. |
| 135 | 1090-1092 | 0,2 | Convenciones y lecciones aprendidas › Ingeniería mecánica (lecciones de diseño) | Bisagra de pliegue: eje en la cara hacia la que pliega | regla-transversal | `CLAUDE.md` § Criterio de diseño (lecciones) | lecciones de diseño para sesiones que modelan por MCP (sin Read): no están en `design/guidelines.py` (grep «lado rápido», «eje vivo» = 0). Queda: raíz ~60 %. |
| 136 | 1093-1094 | 0,2 | Convenciones y lecciones aprendidas › Ingeniería mecánica (lecciones de diseño) | Lazo cerrado: manejar por el recorrido del carro | regla-transversal | `CLAUDE.md` § Criterio de diseño (lecciones) | Queda: raíz ~60 %. |
| 137 | 1095-1099 | 0,4 | Convenciones y lecciones aprendidas › Ingeniería mecánica (lecciones de diseño) | Faja en V lado rápido; tambor motriz eje vivo; anti-giro | regla-transversal | `CLAUDE.md` § Criterio de diseño (lecciones) | Queda: raíz ~60 %. |
| 138 | 1100-1102 | 0,2 | Convenciones y lecciones aprendidas › Ingeniería mecánica (lecciones de diseño) | Guarda: abrir al lado máquina, soportar, atornillar | regla-transversal | `CLAUDE.md` § Criterio de diseño (lecciones) | parcialmente en `design/guidelines.py:46,68` (guarda envolvente); lo de «nunca fijarla a piezas que giran» no. Queda: raíz ~60 %. |
| 139 | 1103-1106 | 0,3 | Convenciones y lecciones aprendidas › Ingeniería mecánica (lecciones de diseño) | Camino de carga: columna antes que tubo fino; UCP horizontal | regla-transversal | `CLAUDE.md` § Criterio de diseño (lecciones) | Queda: raíz ~60 %. |
| 140 | 1107-1109 | 0,2 | Convenciones y lecciones aprendidas › Ingeniería mecánica (lecciones de diseño) | Confirmar el eje real del conflicto antes de mover | regla-transversal | `CLAUDE.md` § Criterio de diseño (lecciones) | Queda: raíz ~60 %. |
| 141 | 1110-1114 | 0,4 | Convenciones y lecciones aprendidas › Ingeniería mecánica (lecciones de diseño) | Curar la conectividad auto-detectada | regla-transversal | `CLAUDE.md` § Criterio de diseño (lecciones) | Queda: raíz ~60 %. |
| 142 | 1115-1117 | 0,1 | Convenciones y lecciones aprendidas › Ingeniería mecánica (lecciones de diseño) | Engrosar un miembro cascada al herraje vecino | regla-transversal | `CLAUDE.md` § Criterio de diseño (lecciones) | Queda: raíz ~60 %. |
| 143 | 1118-1120 | 0,2 | Convenciones y lecciones aprendidas › Entorno / operación (Windows) | Editar sólo YAML no recarga el worker | regla-transversal | `CLAUDE.md` § Windows y operación |  |
| 144 | 1121-1125 | 0,4 | Convenciones y lecciones aprendidas › Entorno / operación (Windows) | Zombie-socket :8000: cómo detectarlo y matarlo | regla-transversal | `CLAUDE.md` § Windows y operación |  |
| 145 | 1126-1131 | 0,5 | Convenciones y lecciones aprendidas › Entorno / operación (Windows) | Script offline + --reload blanquea el DOC; recuperar | regla-transversal | `CLAUDE.md` § Windows y operación |  |
| 146 | 1132-1132 | 0,1 | Convenciones y lecciones aprendidas › Entorno / operación (Windows) | Fotografiar piezas con render_view(isolate), no ocultar | regla-transversal | `CLAUDE.md` § Windows y operación |  |
| 147 | 1133-1135 | 0,2 | Convenciones y lecciones aprendidas › Entorno / operación (Windows) | Flujo «revisa»: leer errors.log, agrupar, parchear, limpiar | cultura | `CLAUDE.md` § Windows y operación |  |
| 148 | 1136-1140 | 0,3 | Convenciones y lecciones aprendidas › UI | Contención de layout: alturas acotadas con minmax | regla-paquete | `ui/CLAUDE.md` § Layout |  |
| 149 | 1141-1146 | 0,5 | Convenciones y lecciones aprendidas › UI | vite preview, no dev; verificar viewport por DOM | regla-paquete | `ui/CLAUDE.md` § Desarrollo y verificación | **deriva de herramienta**: `preview_eval` ya no existe en el harness (hoy `mcp__Claude_Browser__javascript_tool`); 0 menciones en el código. Queda: ui ~60 %. |
| 150 | 1147-1153 | 0,6 | Convenciones y lecciones aprendidas › UI | editCommand de la UI reemplaza params: usar merge=true | regla-paquete | `ui/CLAUDE.md` § Sync con el servidor | **deriva**: «`isAxisAligned` falla → los tiradores no reconstruyen» describe el mecanismo VIEJO; hoy la puerta es `boxDimsFromBbox` (`ui/src/viewport/handles.ts:92`) e `isAxisAligned` (`handles.ts:82`) no tiene llamadas (código muerto). Queda: ui ~80 %. |
| 151 | 1154-1160 | 0,7 | Convenciones y lecciones aprendidas › UI | pumpEdit: el último gana; aplicar sólo la respuesta final | regla-paquete | `ui/CLAUDE.md` § Sync con el servidor | Queda: ui ~80 %. |
| 152 | 1161-1168 | 0,8 | Convenciones y lecciones aprendidas › UI | WS document_changed con debounce y gate de syncing | regla-paquete | `ui/CLAUDE.md` § Sync con el servidor | verificado debounce 250 ms (`ui/src/state/store.ts:428`). Queda: ui ~80 %. |
| 153 | 1169-1172 | 0,4 | Convenciones y lecciones aprendidas › UI | Tinte rojizo sólo para guardado fallido | regla-paquete | `ui/CLAUDE.md` § Viewport | verificado: `saveTintFid`/`withSaveTint` ya no existen (0 menciones). Queda: ui ~60 %. |
| 154 | 1173-1177 | 0,5 | Convenciones y lecciones aprendidas › UI | Agarrar-y-mover con dead-zone de 5 px | regla-paquete | `ui/CLAUDE.md` § Viewport | verificado `DRAG_THRESHOLD_PX` (`ui/src/viewport/Viewport.tsx:677`). Queda: ui ~80 %. |
| 155 | 1178-1184 | 0,7 | Convenciones y lecciones aprendidas › UI | Tiradores desde el bbox; excluye rotadas y paramétricas | regla-paquete | `ui/CLAUDE.md` § Viewport | Queda: ui ~80 %. |
| 156 | 1185-1204 | 1,8 | Convenciones y lecciones aprendidas › UI | Contorno por EffectComposer; HalfFloat; fondo por CSS | regla-paquete | `ui/CLAUDE.md` § Viewport | **obsoleto**: «El tinte rojizo de "guardando" (`applySaveTint`) es INDEPENDIENTE… coexiste» — `applySaveTint` tiene 0 menciones en `ui/src` (retirado, ver #153) → borrar esa frase. Queda: ui ~70 %. |
| 157 | 1205-1212 | 0,6 | Objetivo final — doctrina de RESULTADOS (usuario, 2026-07-10) | Doctrina de resultados: entregable terminado, no paridad | cultura | `CLAUDE.md` § Doctrina de resultados |  |
| 158 | 1213-1214 | 0,1 | Objetivo final — doctrina de RESULTADOS (usuario, 2026-07-10) | Una función importa si mejora un entregable | cultura | `CLAUDE.md` § Doctrina de resultados |  |
| 159 | 1215-1216 | 0,2 | Objetivo final — doctrina de RESULTADOS (usuario, 2026-07-10) | La madurez se mide con benchmarks de entregables | cultura | `CLAUDE.md` § Doctrina de resultados | + link a `docs/benchmark/README.md`. |
| 160 | 1217-1222 | 0,4 | Objetivo final — doctrina de RESULTADOS (usuario, 2026-07-10) | Dónde Apolo ya supera y dónde cerrar con criterio | cultura | `CLAUDE.md` § Doctrina de resultados |  |
| 161 | 1223-1305 | 7,2 | Madurez — línea base (act. 2026-07-10, escala vs incumbente maduro = 10) | Madurez: ejes por features y serie de calificaciones 62→82,8 % | crónica | `docs/benchmark/README.md` § Serie de calificaciones y reserva | la narrativa de cada corrida ya vive en `docs/devlog.md:3938-4226`; el README queda con la serie, los ejes y la RESERVA (generalización). 1 línea en la raíz (doctrina). |
| 162 | 1306-1312 | 0,5 | Hoja de ruta V6 — «Apolo industrial» (doctrina 2026-07-04) | Hoja de ruta V6: doctrina y criterio de hecho | crónica | `docs/roadmap.md` § V6 |  |
| 163 | 1313-1315 | 0,2 | Hoja de ruta V6 — «Apolo industrial» (doctrina 2026-07-04) | V6.1 robustez hecha | crónica | `docs/roadmap.md` § V6 | plan `V6.1-robustez-industrial.md`. |
| 164 | 1316-1317 | 0,2 | Hoja de ruta V6 — «Apolo industrial» (doctrina 2026-07-04) | V6.2 rendimiento hecho | crónica | `docs/roadmap.md` § V6 | plan `V6.2-rendimiento.md`. |
| 165 | 1318-1319 | 0,2 | Hoja de ruta V6 — «Apolo industrial» (doctrina 2026-07-04) | V6.3 ensamblaje pro hecho | crónica | `docs/roadmap.md` § V6 | plan `V6.3-ensamblaje-pro.md`. |
| 166 | 1320-1323 | 0,3 | Hoja de ruta V6 — «Apolo industrial» (doctrina 2026-07-04) | V6.4 paramétrico profundo hecho | crónica | `docs/roadmap.md` § V6 | plan `V6.4-parametrico-profundo.md`. |
| 167 | 1324-1326 | 0,2 | Hoja de ruta V6 — «Apolo industrial» (doctrina 2026-07-04) | V6.5 MCP a escala hecho | crónica | `docs/roadmap.md` § V6 | plan `V6.5-mcp-a-escala.md`. |
| 168 | 1327-1332 | 0,5 | Hoja de ruta V6 — «Apolo industrial» (doctrina 2026-07-04) | V6.5b acción con contrato hecho | crónica | `docs/roadmap.md` § V6 | plan `V6.5b-mcp-accion-con-contrato.md`. |
| 169 | 1333-1337 | 0,4 | Hoja de ruta V6 — «Apolo industrial» (doctrina 2026-07-04) | V6.5c fixes de la revisión hecho | crónica | `docs/roadmap.md` § V6 | plan `V6.5c-fixes-revision.md`. |
| 170 | 1338-1341 | 0,4 | Hoja de ruta V6 — «Apolo industrial» (doctrina 2026-07-04) | V6.5e jobs asíncronos hecho | crónica | `docs/roadmap.md` § V6 | plan `V6.5e-mcp-jobs-asincronos.md`. |
| 171 | 1342-1346 | 0,4 | Hoja de ruta V6 — «Apolo industrial» (doctrina 2026-07-04) | V6.6 croquis vivo hecho | crónica | `docs/roadmap.md` § V6 | plan `V6.6-croquis-vivo.md`. |
| 172 | 1347-1347 | 0,1 | Hoja de ruta V6 — «Apolo industrial» (doctrina 2026-07-04) | V6.7 absorbido por V7.4 | crónica | `docs/roadmap.md` § V6 | sin archivo de plan propio: la línea apunta a V7.4. |
| 173 | 1348-1362 | 1,3 | Hoja de ruta V6 — «Apolo industrial» (doctrina 2026-07-04) | V6.8 fluidez MCP: E2E camastro 70 y test del 71 | crónica | `docs/roadmap.md` § V6 | narrativa ya en `docs/plans/V6.8-mcp-fluidez.md:245` (cierre E2E). |
| 174 | 1363-1374 | 0,9 | Hoja de ruta V6 — «Apolo industrial» (doctrina 2026-07-04) | V6.9 puerta de entrega: E2E 71/70/38 | crónica | `docs/roadmap.md` § V6 | narrativa ya en `docs/plans/V6.9-puerta-de-entrega.md`; la cura del 38 (2026-08-03) va al devlog (ver #78). |
| 175 | 1375-1383 | 0,7 | Hoja de ruta V6 — «Apolo industrial» (doctrina 2026-07-04) | Harness de auto-mejora: en plan | pendiente | `docs/roadmap.md` § Fuera de versión | el GOTCHA «workspace del ejecutor FUERA del repo» ya está en `docs/plans/harness-automejora.md:59`; nota del plan al día. |
| 176 | 1384-1388 | 0,3 | Hoja de ruta V7 — «Resultados sobre el incumbente» (doctrina 2026-07-10, tras V6) | Hoja de ruta V7: doctrina | crónica | `docs/roadmap.md` § V7 |  |
| 177 | 1389-1394 | 0,5 | Hoja de ruta V7 — «Resultados sobre el incumbente» (doctrina 2026-07-10, tras V6) | V7.1 benchmark testigo 62 % | crónica | `docs/roadmap.md` § V7 | plan `V7.1-benchmark-testigo.md` + devlog:3166. |
| 178 | 1395-1400 | 0,5 | Hoja de ruta V7 — «Resultados sobre el incumbente» (doctrina 2026-07-10, tras V6) | V7.1c fixes re-auditoría 68 % | crónica | `docs/roadmap.md` § V7 | plan `V7.1c-fixes-re-auditoria.md`. |
| 179 | 1401-1412 | 1,1 | Hoja de ruta V7 — «Resultados sobre el incumbente» (doctrina 2026-07-10, tras V6) | V7.2 último kilómetro del plano | crónica | `docs/roadmap.md` § V7 | plan `V7.2-ultimo-kilometro-plano.md` + devlog:3294. |
| 180 | 1413-1423 | 1,0 | Hoja de ruta V7 — «Resultados sobre el incumbente» (doctrina 2026-07-10, tras V6) | V7.2b barrida de residuos 74 % | crónica | `docs/roadmap.md` § V7 | plan `V7.2b-barrida-residuos.md`; ver deriva «15 vs 16» en #91. |
| 181 | 1424-1440 | 1,6 | Hoja de ruta V7 — «Resultados sobre el incumbente» (doctrina 2026-07-10, tras V6) | V7.2c fixes re-auditoría 77 % | crónica | `docs/roadmap.md` § V7 | plan `V7.2c-fixes-re-auditoria.md` + devlog:3608. |
| 182 | 1441-1450 | 0,9 | Hoja de ruta V7 — «Resultados sobre el incumbente» (doctrina 2026-07-10, tras V6) | V7.3 stack-up de cadenas de cotas | crónica | `docs/roadmap.md` § V7 | plan `V7.3-stackup-cadenas-cotas.md`. |
| 183 | 1451-1465 | 1,4 | Hoja de ruta V7 — «Resultados sobre el incumbente» (doctrina 2026-07-10, tras V6) | V7.4 FEA firmable y V7.4b cierre | crónica | `docs/roadmap.md` § V7 | planes V7.4/V7.4b + devlog:3772. «tool fea_assembly (72→73)» conteo viejo. |
| 184 | 1466-1474 | 0,7 | Hoja de ruta V7 — «Resultados sobre el incumbente» (doctrina 2026-07-10, tras V6) | V7.5 datum funcional y barrenos UCP | crónica | `docs/roadmap.md` § V7 | **obsoleto**: el «hallazgo colateral: peso de cajetín ~16×» ya se corrigió (`docs/devlog.md:3924`). |
| 185 | 1475-1484 | 0,8 | Hoja de ruta V5 — AGOTADA (completitud de flujo del vertical) | Hoja de ruta V5 agotada | crónica | `docs/roadmap.md` § V5 | sólo V5.11 tiene plan; el resto vive en devlog. |
| 186 | 1485-1491 | 0,5 | Pendientes (follow-ups vivos, por demanda) | Pendientes de cinemática: lazos cerrados, master-slider, MP4 | pendiente | `docs/plans/V6.3-ensamblaje-pro.md` § nota (ya está) (50 %) + `docs/backlog.md` § Ensamblaje y cinemática (50 %) | **obsoleto parcial**: «falta MP4 y tool MCP» — la tool `motion_gif` existe (`core/apolo/mcp_server.py:961`); sólo falta MP4. |
| 187 | 1492-1501 | 0,9 | Pendientes (follow-ups vivos, por demanda) | Follow-ups V6.3d: mirror sin anclas, salto 180°, EdgeSelector | pendiente | `docs/plans/V6.3d-fixes-revision.md` § nota/bitácora (ya está) | los 4 ya figuran en `docs/plans/V6.3d-fixes-revision.md`: (1) y (2) en su `nota:`, (2)-(4) en las líneas 50-55 → borrar de la raíz. |
| 188 | 1502-1502 | 0,2 | Pendientes (follow-ups vivos, por demanda) | Validación: bisagra A/B, voladizo, torque, fasten↔roscado | pendiente | `docs/backlog.md` § Validación | posible obsoleto: «`torque` en tornillería» — E5 ya calcula el par (`tightening_torque_nm`, `library/engineering/bolts.py:157`); confirmar si falta la VERIFICACIÓN. |
| 189 | 1503-1503 | 0,2 | Pendientes (follow-ups vivos, por demanda) | Geometría/catálogo: carpintería, chapa, coping, chaveta | pendiente | `docs/backlog.md` § Geometría y catálogo |  |
| 190 | 1504-1504 | 0,1 | Pendientes (follow-ups vivos, por demanda) | Física: cascos en drop_test, SDF, tiempo real | pendiente | `docs/backlog.md` § Física |  |
| 191 | 1505-1505 | 0,1 | Pendientes (follow-ups vivos, por demanda) | Ingeniería/negocio: rol por pieza, explosionada 3D, L10 | pendiente | `docs/backlog.md` § Ingeniería y negocio | **obsoleto parcial**: «manual reordenado por grafo de soporte» ya existe (`order_by_support`, `drawing/assembly_manual.py:111`). |
| 192 | 1506-1506 | 0,2 | Pendientes (follow-ups vivos, por demanda) | UI: refactor de Viewport, picker de 2 sólidos, edición | pendiente | `docs/backlog.md` § UI |  |
| 193 | 1507-1507 | 1,3 | Pendientes (follow-ups vivos, por demanda) | Follow-ups V6.4: transform literal, CSV, c339, literales del 38 | pendiente | `docs/plans/V6.4-parametrico-profundo.md` § nota: (1)(2)(4) ya están (45 %) + `docs/plans/V6.4d-remate-revision.md` § bitácora: (3)(5) (55 %) | (3) y (5) son del modelo 38 (c339, j_mesa, c120/c121): van a la bitácora de V6.4d. |
| 194 | 1508-1515 | 0,8 | Pendientes (follow-ups vivos, por demanda) | Follow-ups V6.5: masa por grupo, near sin truncado, R-tree | pendiente | `docs/plans/V6.5-mcp-a-escala.md` § nota (1)(2) ya; bitácora (3)-(6) | verificado vigente: `near_endpoint` no declara `truncado` (`api/main.py:1565-1611`); (3) es comportamiento documentado (`kernel/topology.py:116`). |
| 195 | 1516-1522 | 0,6 | Pendientes (follow-ups vivos, por demanda) | Follow-ups V6.5e: async a run_command, sin cancelar ni progreso | pendiente | `docs/plans/V6.5e-mcp-jobs-asincronos.md` § nota (1) ya; bitácora (2)(3) | verificado vigente: `_sync_or_job` sólo en run_batch/edit_batch (`api/main.py:1169,1203`). |
| 196 | 1523-1523 | 0,1 | Pendientes (follow-ups vivos, por demanda) | Perf absorbido por V6.2 | obsoleto | borrar — nada pendiente | **obsoleto**: no nombra ningún pendiente. |
| 197 | 1524-1532 | 0,7 | Pendientes (follow-ups vivos, por demanda) | Follow-ups V6.2e: tinte vs apariencia, GIF física, locks | pendiente | `docs/plans/V6.2e-fixes-revision.md` § nota (ya lista 3); bitácora el resto | verificados vigentes: drop.gif compone bajo `STATE_LOCK` (`api/main.py:3245`) y `duplicate_project` sin lock (`api/main.py:1719`). |
| 198 | 1533-1539 | 0,4 | Fuera de alcance deliberado | Fuera de alcance deliberado; librerías candidatas | cultura | `CLAUDE.md` § Fuera de alcance | link verificado: `docs/devlog.md:2142`. |

## Derivas y obsoletos verificados contra el código

| # | Qué dice el CLAUDE.md | Qué dice el código | Corrección (D6) |
|---:|---|---|---|
| 76 | GIF del motion: «sin tool MCP (reiniciar host para añadirla)» | `def motion_gif` existe en `core/apolo/mcp_server.py:961` | borrar la frase; en #186 dejar sólo «falta MP4» |
| 68, 83, 84, 183 | «62→64», «65 tools», «53 comandos, 72 tools», «72→73» | 79 × `@mcp.tool` en `core/apolo/mcp_server.py` | borrar los conteos intermedios (son crónica); el único conteo vive en «Estado actual» |
| 90 | GOTCHA: la rama «sierra» de `infer_process` exige `component.category` y los weldment no lo traen | `infer_process` (`core/apolo/drawing/process.py:117`) ya tiene `_is_revolution` (`:71`) y la rama esbelta de V7.2b; #91 dice lo contrario («YA traían component») | borrar el gotcha |
| 91 | «Norma en las **15** verificaciones»; «eje → 0.6·σy (ASME B106.1M)» | 16 entradas `"norma"` de cálculo (10 en `library/rules.py:521-927`, 6 en `library/engineering/report.py:113-494`); `rules.py:927` cita «0.5·σy (más estricto que ASME B106.1M)» | 16; 0.5·σy (lo que ya dice #93) |
| 92 | «`_hole_fit_map` es GLOBAL por Ø nominal» | V7.2c lo reemplazó por `_feature_fit_maps` (`core/apolo/api/main.py:4604`) y `_scene_fit_map` (`:4634`) | borrar (crónica de un bug cerrado) |
| 150 | «la caja colapsa y `isAxisAligned` falla → los tiradores no reconstruyen» | la puerta es `boxDimsFromBbox` (`ui/src/viewport/handles.ts:92`); `isAxisAligned` (`handles.ts:82`) no tiene llamadas: código muerto | dejar sólo «PUT reemplaza: usar `merge=true`»; el código muerto es tarea aparte |
| 156 | «El tinte rojizo de "guardando" (`applySaveTint`) es INDEPENDIENTE… coexiste con el contorno» | `applySaveTint`, `saveTintFid`, `withSaveTint`: 0 menciones en `ui/src` (retirado, #153) | borrar la frase |
| 149 | verificar el overlay con `preview_eval` | la tool ya no existe en el harness (hoy `mcp__Claude_Browser__javascript_tool`); 0 menciones en el código | nombrar «la tool de JS del navegador», sin nombre propio |
| 60 | planegcs «wheel cp313» | marcador `python_version >= '3.12' and platform_system != 'Darwin'` (`core/pyproject.toml:44`); #12 lo dice bien | una sola mención, la de #12 |
| 184 | «hallazgo colateral: peso de cajetín en láminas multi-sólido mal (~16×), tarea aparte» | corregido el mismo día (`docs/devlog.md:3924`) | borrar |
| 191 | pendiente «manual reordenado por grafo de soporte» | hecho en V7.2b: `order_by_support` (`core/apolo/drawing/assembly_manual.py:111`) | borrar del backlog |
| 188 | pendiente «`torque` en tornillería» | E5 ya calcula el par: `tightening_torque_nm` (`core/apolo/library/engineering/bolts.py:157`) | confirmar si lo pendiente es la VERIFICACIÓN del par; si no, borrar |
| 196 | «Perf: absorbido por V6.2» | no nombra ningún pendiente | borrar |
| 134 | «El "timeout ≥540 s" quedó OBSOLETO para el MCP…» | V6.5e: lotes como jobs (`_sync_or_job`, `core/apolo/api/main.py:1115`) | dejar «usa `run_batch`/`edit_batch`» |
| 17 | «⚠️ Hoy la raíz pesa ~130 KB… podarla es el próximo plan» | — | se vuelve falso al cerrar F3 |
| `ui/CLAUDE.md:3-4` | «las convenciones de la UI siguen por ahora en el raíz… se mudan en el plan de poda» | — | se vuelve falso al cerrar F1 |

**Verificado y correcto** (no hay que tocarlo): 1370 tests (`pytest --collect-only`, 110 archivos)
· 79 tools · 53 comandos (`len(REGISTRY)`) · 231 refs (`len(load_catalog())`) · 8-tupla de
checkpoints · `_REGEN_STRIDE = 16` (`doc/document.py:143`) · `GEOM_CACHE_EPOCH = 4`
(`doc/geomcache.py:48`) · `_UNDO_CAP = 50` (`doc/document.py:119`) · `MIN_SOLIDOS_SUJECION = 5`
(`library/delivery.py:24`) · `EXCESS_TOL_MM3 = 50.0` (`library/checks.py:94`) · `MAX_PIECES = 25`
(`fea/mesher.py:25`) · `_RETENTION = 20` (`api/jobs.py:29`) · `APOLO_MCP_WAIT_S` 90
(`mcp_server.py:29`) · debounce WS 250 ms (`ui/src/state/store.ts:428`) · health sin tool MCP
(correcto) · de 176 identificadores citados (grep sobre `core/`, `ui/src`, `tests/`, `scripts/`)
existen todos salvo 5: 3 que el propio CLAUDE.md da por borrados (`saveTintFid`, `withSaveTint`,
`applySelection`) y 2 derivas de la tabla (`applySaveTint`, `preview_eval`) · los 16 endpoints
citados existen en `core/apolo/api/main.py`. Pendientes que siguen
vigentes: `near` no declara `truncado` (`api/main.py:1565-1611`), `drop.gif` compone bajo
`STATE_LOCK` (`api/main.py:3245`), `duplicate_project` sin lock (`api/main.py:1719`), `?async`
sólo en lotes (`api/main.py:1169,1203`).

## Lo que la compresión saca de los bloques mixtos, y dónde vive

D4 exige destino para todo. Lo que un bloque pierde al comprimirse es una de estas tres cosas:

- **Crónica que ya tiene casa** (verificado): FEA bonded y su auditoría → `docs/devlog.md:3772,3832`
  + planes V7.4/V7.4b · V7.2 → `devlog:3294` · V7.2b → `devlog:3477,3582` · V7.2c →
  `devlog:3608,3679` · V7.5 → `devlog:3883` · V7.6 A/B/C → `devlog:4033,4076,4111` · E5 →
  `devlog:4148` · segundo testigo → `devlog:4183` · V6.6 → `devlog:4227` · V6.8 (E2E camastro 70)
  → `docs/plans/V6.8-mcp-fluidez.md:245` · V6.9 (E2E 71/70/38) → `docs/plans/V6.9-puerta-de-entrega.md`
  · gotcha del harness → `docs/plans/harness-automejora.md:59` · `GEOM_CACHE_EPOCH` v4,
  `ui_dist`, `_persist_fea_if_same_project`, `conftest` de errors.log → commit `3e935f4` ·
  tinte/dead-zone/debounce de la UI → commit `e2e15d8`.
- **Crónica SIN casa** → `docs/devlog.md`: la cura del 38 a VERDE (2026-08-03, 8 `fasten` contacto
  estilo c704; revisión 103 = estado previo) — no aparece en ningún archivo de `docs/` (#78).
- **Derivable**: listas de parámetros de tools (firmas en `core/apolo/mcp_server.py`), firmas de
  executors (`wants_*` en `core/apolo/commands/registry.py:2050-2052`), tablas de GDL
  (`assembly/dof.py:32`), valores de K (`library/sheetmetal.py:36`), conteos de familias
  (`load_catalog()`), lista de paneles (`ui/src/dock/dockApi.ts:19`).

Al marcar el inventario en F1, quien mueve un bloque con «Queda: … %» confirma que lo que deja
afuera cae en una de las tres; si no, lo agrega al devlog.

## Totales

### Por tipo

| tipo | KB | % |
|---|---:|---:|
| regla-paquete | 63,7 | 51 % |
| crónica | 23,0 | 18 % |
| regla-transversal | 11,2 | 9 % |
| cultura | 10,2 | 8 % |
| mapa | 9,5 | 8 % |
| pendiente | 6,2 | 5 % |
| derivable | 0,8 | 1 % |
| obsoleto | 0,4 | 0 % |
| **total** | **125,1** | 100 % |

`obsoleto` pesa poco como bloque entero porque casi todo lo obsoleto vive DENTRO de bloques
mixtos (tabla de derivas: 20 fragmentos en 19 bloques de la raíz, más `ui/CLAUDE.md:3-4`).
`crónica` cuenta sólo los bloques que son crónica pura; de los bloques que van a los anidados
(71 KB crudos) salen ~31 KB al comprimir: crónica con casa, derivable y redacción (ver arriba).

### Por destino (KB crudos que recibe, antes de comprimir)

| destino | KB que recibe (crudo) |
|---|---:|
| `CLAUDE.md` | 24,0 |
| `docs/roadmap.md` | 15,1 |
| `core/apolo/drawing/CLAUDE.md` | 14,1 |
| `core/apolo/library/CLAUDE.md` | 10,9 |
| `core/apolo/api/CLAUDE.md` | 9,5 |
| `ui/CLAUDE.md` | 8,6 |
| `docs/benchmark/README.md` | 7,8 |
| `core/apolo/commands/CLAUDE.md` | 6,4 |
| `core/apolo/assembly/CLAUDE.md` | 6,2 |
| `core/apolo/doc/CLAUDE.md` | 5,6 |
| `core/apolo/fea/CLAUDE.md` | 5,2 |
| `core/apolo/kernel/CLAUDE.md` | 4,6 |
| `docs/backlog.md` | 1,1 |
| `borrar` | 1,1 |
| `docs/plans/V6.3d-fixes-revision.md` | 0,9 |
| `docs/plans/V6.5-mcp-a-escala.md` | 0,8 |
| `docs/plans/V6.4d-remate-revision.md` | 0,7 |
| `docs/plans/V6.2e-fixes-revision.md` | 0,7 |
| `docs/plans/V6.4-parametrico-profundo.md` | 0,6 |
| `docs/plans/V6.5e-mcp-jobs-asincronos.md` | 0,6 |
| `docs/devlog.md` | 0,4 |
| `docs/plans/V6.3-ensamblaje-pro.md` | 0,3 |
| **total** | **125,1** |

## Proyección de tamaños tras F1–F3

«Tras comprimir» = bytes × fracción × lo que queda en formato D5 (columna `nota`). «Fijo» en la
raíz = índice de anidados (~1,3 KB) + la regla nueva de la bitácora F0 (b) (~0,35 KB); en los
anidados, encabezado y link (~0,25 KB); en `ui/CLAUDE.md`, lo que ya tiene (9,2 KB) menos el
aviso de las líneas 3-4.

| archivo | crudo (KB) | tras comprimir (KB) | + fijo (KB) | proyección (KB) | tope |
|---|---:|---:|---:|---:|---:|
| `CLAUDE.md` | 24,0 | 20,4 | 1,6 | **22,0** | 30 |
| `core/apolo/kernel/CLAUDE.md` | 4,6 | 2,5 | 0,2 | **2,8** | 35 |
| `core/apolo/commands/CLAUDE.md` | 6,4 | 3,7 | 0,2 | **3,9** | 35 |
| `core/apolo/doc/CLAUDE.md` | 5,6 | 3,4 | 0,2 | **3,6** | 35 |
| `core/apolo/assembly/CLAUDE.md` | 6,2 | 3,6 | 0,2 | **3,9** | 35 |
| `core/apolo/library/CLAUDE.md` | 10,9 | 6,5 | 0,2 | **6,7** | 35 |
| `core/apolo/drawing/CLAUDE.md` | 14,1 | 6,3 | 0,2 | **6,6** | 35 |
| `core/apolo/fea/CLAUDE.md` | 5,2 | 2,2 | 0,2 | **2,4** | 35 |
| `core/apolo/api/CLAUDE.md` | 9,5 | 5,3 | 0,2 | **5,6** | 35 |
| `ui/CLAUDE.md` | 8,6 | 6,1 | 9,0 | **15,1** | 35 |

**La raíz queda en ~22 KB (tope 30)** y ningún anidado pasa de ~15 KB (tope 35). Si al escribirla
la raíz pasara de 30 KB, comprimir más, en este orden: (1) Sesiones concurrentes #34-46 (3,1 KB):
la receta de robocopy (#45) y el rescate de ediciones fuera del worktree (#40) a un
`docs/worktrees.md` enlazado; (2) Planes #21-33 (3,5 KB): la plantilla (#23-25) a
`docs/plans/README.md`; (3) Criterio de diseño #135-142 (2,0 KB): a una línea por lección;
(4) Distribución #12 (1,1 KB): sólo el «cómo publicar» y la regla de `paths.py`.

## Hallazgos para F1–F3 (riesgos del plan)

1. **D2 deja código sin anidado que lo cubra.** El mapa documenta código fuera de los 8 paquetes:
   `core/apolo/mcp_server.py` (archivo suelto en `core/apolo/`: la mitad cliente de los jobs,
   `_scene_brief`, la alarma ambiental), `core/apolo/robotics/` (FK `pose.py`, GIF `anim.py`: #73,
   #76), `core/apolo/physics/` (#79), `core/apolo/design/` (#9), `scripts/` (#88) y `tests/`
   (#110, #121). Una sesión que edita `robotics/anim.py` no carga `assembly/CLAUDE.md`. Propuesta:
   un `core/apolo/robotics/CLAUDE.md` chico (o mover #73/#76 allí) y que la raíz diga «para
   `mcp_server.py`, lee `core/apolo/api/CLAUDE.md`».
2. **No está medido si un anidado carga al leer un archivo de una SUBcarpeta suya.** La prueba de
   F0 (b) mostró que llega el canario de la subcarpeta, pero el de la carpeta padre ya estaba en
   contexto. Si los ancestros no cargan, `library/engineering/*.py` no ve `library/CLAUDE.md`.
   Medirlo antes de F1 (un canario, un Read).
3. **Reglas cuyo punto de cambio está en otro paquete.** El bump de `GEOM_CACHE_EPOCH` se olvida
   al editar un executor (`commands/`, `kernel/`, `library/builders.py`), no al leer
   `doc/geomcache.py` → va a la raíz (así quedó en #111). Igual: los mapas de fit y datum son
   features de `drawing/` que viven en `api/main.py` (#92-97); la materialización de
   `insert_project` vive en `api/main.py:1063` (#70). Regla para F1: la explicación va donde se
   hace el cambio y el otro anidado lleva sólo el link.
4. **Dos `nota:` de planes apuntan a la sección «Pendientes» que se va**: V6.2e («Menores en
   Pendientes V6.2e») y V6.3d («ver Pendientes V6.3d»). F2 las reescribe. Hay ~80 menciones de
   `CLAUDE.md` en `docs/` (historia: no se tocan), pero `docs/devlog.md:2836` remite a «CLAUDE.md
   § Pendientes» como lugar vivo.
5. **El verificador de D7 puede leer la raíz vieja.** Según F0 (b), subagentes y sesiones en
   worktree leen el `CLAUDE.md` raíz del ÁRBOL PRINCIPAL (el archivo en disco, que no es
   necesariamente `main`). Este mismo subagente recibió como raíz una versión con «1355 tests · 217
   refs · 7-tupla», distinta del `CLAUDE.md` de `main` (`78c30dd`, «1370 · 231 · 8-tupla»). F4
   tiene que correr D7 con el árbol principal ya actualizado (después del merge), o desde un clon
   de la rama que no sea worktree; si no, mide la raíz equivocada.
6. **Código muerto de paso**: `isAxisAligned` (`ui/src/viewport/handles.ts:82`) sin llamadas. Fuera
   del alcance de este plan.
