# Hojas de ruta de Apolo (V5–V7)

Una línea por versión: qué entregó, cuándo y dónde está el detalle. La narrativa larga (contexto,
E2E, decisiones, desviaciones) vive en el plan de cada versión en [`plans/`](plans/) y, cuando no
hay plan, en el [devlog](devlog.md) y en el commit que se cita. **El estado vigente de un plan es
su frontmatter** (`estado:` / `nota:`), no esta tabla: si se contradicen, manda el plan. Los
pendientes que no caben en la `nota:` de su plan están en el [backlog](backlog.md); cómo se mide
la madurez está en el [benchmark](benchmark/README.md).

Las hojas V1–V4 son históricas: viven en el devlog (§ «Hoja de ruta V3» y § «Hoja de ruta V4»).

## V5 — completitud de flujo del vertical (agotada)

**Doctrina (usuario):** el ingeniero del vertical **nunca necesita SW/Inventor**. Se persigue la
completitud de FLUJO (~40 funciones agente-nativas: comando schema-driven + lectura MCP +
verificable), no la paridad con las 3000 funciones del incumbente. Criterio de «hecho»: usable
por chat/MCP + schema-driven + tests + E2E real; un ítem por vez con plan formal. Todo V5 está
HECHO (Tier 1, 2 y 3). Lo que resta del Tier 3 (render fotorrealista, PDM, plantillas de plano por
empresa) es POR DEMANDA, no bloqueante.

| versión | resultado en una línea | estado | plan |
|---|---|---|---|
| V5.1 | Croquis robusto con PlaneGCS: dof, redundantes, tangencias (Tier 1) | hecho 2026-07-02 | sin plan: devlog § V5.1 · commit `75224d2` |
| V5.2 | Sub-ensamblajes de primera clase: grupos por command_ids, `transform_group`, árbol/BOM/manual por grupos (Tier 1) | hecho 2026-07-02 | sin plan: commits `7f611d9`, `8ad19a2` |
| V5.2b | `insert_project`: proyecto dentro de proyecto, layouts multi-máquina (Tier 1) | hecho 2026-07-02 | sin plan: devlog § V5.2b · commit `e5603a5` |
| V5.3 | Modelado directo básico: `delete_faces` con curación + `push_face` (Tier 1) | hecho 2026-07-03 | sin plan: devlog § V5.3 · commit `fa0e2de` |
| V5.4 | Ajustes y tolerancias ISO 286 en cotas y asientos (Tier 1) | hecho 2026-07-03 | sin plan: devlog § V5.4 · commit `0ab80ea` |
| V5.5 | Chapa avanzada: flaps con hijo, cutouts en pestañas, K por material — **cierra el Tier 1** | hecho 2026-07-03 | sin plan: devlog § V5.5 · commit `ed57599` |
| V5.6 | FEA estático lineal de pieza (gmsh + scikit-fem P2) (Tier 2) | hecho 2026-07-03 | sin plan: devlog § V5.6 · commit `b737fe6` |
| V5.7 | Roscas métricas: broca de machuelado, callout + cosmético ISO 6410 (Tier 2) | hecho 2026-07-03 | sin plan: devlog § V5.7 · commit `760d3eb` |
| V5.8 | Ingletes reales en weldments: corte bisector, ángulos en BOM (Tier 2) | hecho 2026-07-03 | sin plan: devlog § V5.8 · commit `841cea4` |
| V5.9 | Export DWG vía ODA File Converter (Tier 2) | hecho 2026-07-03 | sin plan: devlog § V5.9 · commit `5352a68` |
| V5.10 | Normas del vertical: CEMA / ISO 5048 por construcción + Euler-Eytelwein (Tier 3) | hecho 2026-07-03 | sin plan: devlog § V5.10 · commit `ecb4afd` |
| V5.11 | Superficies básicas: boundary / fill / thicken — **cierra el Tier 2** | implementado 2026-07-04 | [V5.11](plans/V5.11-superficies-basicas.md) |

## V6 — «Apolo industrial» (cerrada)

**Doctrina (2026-07-04):** con V5 agotado (lo que quedaba era por demanda), V6 ataca los ejes de
MADUREZ más débiles, empezando por el menos vistoso y más pro. Criterio de «hecho» = el de V5
**+ la tortura y el health quedan verdes**. Un ítem por vez, con plan formal. Los saltos «a→b» de
la tabla son la nota del eje de madurez (escala: incumbente maduro = 10, ver
[benchmark](benchmark/README.md#madurez-por-features)).

| versión | resultado en una línea | estado | plan |
|---|---|---|---|
| V6.1 | Robustez: «nada tumba el documento» (`check_integrity`, `APOLO_STRICT`, health, tortura, regenerate atómico, carga tolerante, autosave durable). Robustez 3→6 | implementado 2026-07-04 | [V6.1](plans/V6.1-robustez-industrial.md) |
| V6.2 | Rendimiento: caché BREP (open 3–23 s → 0.04 s), deltas de escena (1.1 MB → 31 KB), dos-locks, autosave debounced. Rendimiento 4→6 | implementado 2026-07-09 | [V6.2](plans/V6.2-rendimiento.md) |
| V6.2e | Correcciones de la revisión de V6.2: flush del autosave atómico, epoch de escena, `is_guide` en deltas | implementado 2026-07-09 | [V6.2e](plans/V6.2e-fixes-revision.md) |
| V6.3 | Ensamblaje pro (fases a/b/c): multi-mate (DAG multi-padre), conectores por ancla/arista circular, reporte de DOF. Ensamblaje 4.5→6 | implementado 2026-07-09 | [V6.3](plans/V6.3-ensamblaje-pro.md) |
| V6.3d | Correcciones de la revisión de V6.3: anclas que siguen a la pieza al moverla, duplicarla o repetirla en patrón + E2E por MCP | implementado 2026-07-10 | [V6.3d](plans/V6.3d-fixes-revision.md) |
| V6.4 | Paramétrico profundo (fases a/b/c): expresiones con condicionales + faja 38 100 % paramétrica (log 701 → 312, juntas con expresiones, tren motriz sigue a `largo_total`) + tablas de diseño (variantes «4m» ↔ «3.2m»). Paramétrico 5→6.5. V6.4b no tiene plan propio: es la fase B de este plan | implementado 2026-07-10 | [V6.4](plans/V6.4-parametrico-profundo.md) |
| V6.4d | Remate de la revisión de V6.4: juntas y radios de la faja 38 atados a variables, guías huérfanas podadas al cargar | implementado 2026-07-10 | [V6.4d](plans/V6.4d-remate-revision.md) |
| V6.5 | MCP a escala: lectura acotada y paginada, summary por grupo, `near`/interferencia acotada, `snap_to`/`verify`, preview con datos; rutina < 10 KB a 1000 piezas | implementado 2026-07-10 | [V6.5](plans/V6.5-mcp-a-escala.md) |
| V6.5b | MCP con contrato: `expect` en `run_batch`/`edit_batch` con rollback atómico, super-comando `join_bolted`, 404 con «¿quisiste decir…?», briefing compacto en `open_project` | implementado 2026-07-11 | [V6.5b](plans/V6.5b-mcp-accion-con-contrato.md) |
| V6.5c | Correcciones de la revisión de V6.5b (implementadas por Fable): `$k` → feature_ids reales, `join_bolted` valida caras planas y pone tuerca DIN 934, errores accionables con sugerencia | implementado 2026-07-12 | [V6.5c](plans/V6.5c-fixes-revision.md) |
| V6.5e | MCP con jobs asíncronos: los lotes se encolan con recibo (`?async=true` → `202 {job_id}` + `get_job`); el cliente fino espera 90 s y devuelve el recibo en vez de quedar ciego (evidencia: perezosa 66) | implementado 2026-07-16 | [V6.5e](plans/V6.5e-mcp-jobs-asincronos.md) |
| V6.6 | Croquis vivo: spline + elipse en los dos motores, `POST /api/sketch/drag` y la UI del SketcherDialog; 18 tests parametrizados + build de UI limpio. Croquis 5→6.5 | implementado 2026-07-24 | [V6.6](plans/V6.6-croquis-vivo.md) |
| V6.7 | FEA de ensamblaje (bonded): **absorbido por V7.4** | — | sin plan propio: ver V7.4 |
| V6.8 | MCP fluidez: A lotes de apariencia/conexiones · B `find_commands` · C cinemática por MCP + contratos en pose · D arrastre de cuerpo rígido · E snap cara-a-cara + taladro por cara. E2E en el camastro 70: un `run_batch` con contrato de 14 aserciones verde a la primera (la sesión original: ~15 rondas y 4 lotes revertidos) | implementado 2026-08-02 | [V6.8](plans/V6.8-mcp-fluidez.md) |
| V6.9 | Puerta de entrega: `delivery_check` (semáforo VERDE/AMARILLO/ROJO), alarma ambiental `aviso_estructura` y «no entregues en ROJO» en el brief. Nace del test de generalización del camastro 71 (cremalleras flotantes, 0 sujeción declarada). E2E: 71 → ROJO · 70 → VERDE · 38 → AMARILLO (curado el 2026-08-03 → VERDE), cero falsos rojos | implementado 2026-08-02 | [V6.9](plans/V6.9-puerta-de-entrega.md) |

## Fuera de versión

| plan | resultado en una línea | estado | plan |
|---|---|---|---|
| Harness de auto-mejora | Loop maestro → ejecutor CIEGO → auditor → implementador sobre `claude -p` + una instancia B aislada (`-Port 8001` + `APOLO_DB` propio). Formaliza el test de generalización manual que originó V6.9; converge con 2 iteraciones sin mejora en las MEDIANAS (N ≥ 2 corridas por iteración); las mejoras llegan en una rama `exp/<slug>` y el merge lo aprueba el usuario | en plan (pedido 2026-08-02) | [harness-automejora](plans/harness-automejora.md) |
| Poda del CLAUDE.md | Cada sesión arranca con un CLAUDE.md raíz ≤ 30 KB; el detalle de cada paquete en su CLAUDE.md anidado | en curso (2026-10-03) | [poda-claude-md](plans/poda-claude-md.md) |

## V7 — «Resultados sobre el incumbente» (cerrada)

**Doctrina (2026-07-10, tras V6):** ejecutar la doctrina de RESULTADOS — la vara es el ENTREGABLE
terminado (3D validado + juego de planos + memoria de cálculo + BOM/cotización + manual), no la
lista de features. V7 cierra los entregables donde el paquete Apolo aún pierde contra el terminado
a mano en SW/Inventor, en orden de impacto en el entregable, cada ítem con plan formal. Cada ítem
se mide con el [benchmark de entregables](benchmark/README.md) (re-auditado, no autocalificado).
El devlog la da por cerrada el 2026-07-24 (cierre de V6.6: «todos los roadmaps V1–V7 cerrados»);
V6.8 y V6.9 llegaron después. Tras E5, los ejes del benchmark que siguen en 3.00 son E4
(BOM/cotización) y E6 (paquete/interop).

| versión | resultado en una línea | estado | plan |
|---|---|---|---|
| V7.1 | Benchmark testigo: paquete completo de la faja 38 por API en 411.9 s (24/24 artefactos), calificado con la rúbrica-v1; la re-auditoría corrige la autocalificación 67 % → **62 %** | implementado 2026-07-10 | [V7.1](plans/V7.1-benchmark-testigo.md) |
| V7.1c | Fixes de la re-auditoría: la memoria lee del modelo por ROL, cirugía del 38 (24 pernos paramétricos + `c704` declarado), compras fuera de la lista de corte (juego 32 → 22 páginas), script de benchmark endurecido. 62 → **68 %** | implementado 2026-07-11 | [V7.1c](plans/V7.1c-fixes-re-auditoria.md) |
| V7.2 | Último kilómetro del plano: soldadura ISO 2553, ISO 2768-mK, acabados ISO 1302, acotado por función. E2 2.14 → 2.86 (53.6 → 71.4 %), global 68 → **≈73 %** re-auditado | implementado 2026-07-11 | [V7.2](plans/V7.2-ultimo-kilometro-plano.md) |
| V7.2b | Barrida de residuos: manual por grafo de soporte, norma en las 16 verificaciones cuantitativas, lints pre-entrega, `infer_process` robusto, eje del tensor g6 (suite 1164 + tortura). 73 → **~74 %** re-auditado (autocalificación 77 % corregida); D.1 diferido y luego retirado | implementado 2026-07-14 | [V7.2b](plans/V7.2b-barrida-residuos.md) |
| V7.2c | Fixes de la re-auditoría: fit POR PIEZA en las láminas, revolución ≠ sierra, cola del manual, citas L/240 y 0.5·σy. 74 → **≈77 %** re-auditado (autocalificación 78 % corregida) | implementado 2026-07-18 | [V7.2c](plans/V7.2c-fixes-re-auditoria.md) |
| V7.3 | Stack-up de cadenas de cotas: peor caso + RSS con ISO 2768-1 e ISO 286; cadenas como metadato del manifest (no comando: rompería los checkpoints); en el 38 cierran 2 cadenas testigo. Global **77.6 % ≈ 78 %** | implementado 2026-07-20 | [V7.3](plans/V7.3-stackup-cadenas-cotas.md) |
| V7.4 | FEA firmable (absorbe V6.7): FEA bonded de sub-ensamblaje multi-material, FS por pieza, guarda de cuerpo rígido, integrado a la memoria. E2E 38: FS gobernante 93.5, δ 0.021 mm ≤ L/240. FEA firmable ≈45 % → ~70 % | implementado 2026-07-21 | [V7.4](plans/V7.4-fea-firmable.md) |
| V7.4b | Cierre de auditoría del FEA: 5 hallazgos (sustitución multi-material, hipótesis del herraje, exclusión del motor, estado con flecha, estimador de tets a 4×) | implementado 2026-07-22 | [V7.4b](plans/V7.4b-cierre-auditoria.md) |
| V7.5 | Datum «A» por cara funcional derivada de los fasteners + ménsula de chumacera del 38 atornillable (4 barrenos Ø15.5 a J=127 + M14×50 + tuercas). Mismo día: fix del peso del cajetín en láminas multi-sólido (devlog). Primera corrida con rúbrica-v2: **78.4 % v1-comparable / 78.2 % v2** | implementado 2026-07-22 | [V7.5](plans/V7.5-e22-datum-funcional.md) |
| Brecha 1 | Barrenos de la ménsula del motor (16 taladros paramétricos) + 3 bugs cazados por el contrato y el lint. E2.2 2.75 → 3.0; **≈78.6 % v1 / ≈78.5 % v2** | hecho 2026-07-22 | sin plan: devlog § Brecha 1 · commit `1b43f26` |
| Brechas 2+3 | Manual sin micro-pasos, convergencia de malla impresa en la memoria, chapa fina analizada como placa; D.1 retirado por decisión. E3.7 = 4; **v2 ≈78.8 %** | hecho 2026-07-23 | sin plan: devlog § Brechas 2+3 · commit `3687923` |
| V7.6 | E2 fino en tres fases: A GD&T funcional · B tolerancia justificada + ISO 13920 · C lámina de instalación. E2 75.0 → 83.0 %, **v2 ≈81.2 %** | implementado 2026-07-23 | [V7.6](plans/V7.6-e2-fino.md) |
| E5 | Manual con par de apriete calculado, llave por paso y orden intra-paso abajo → arriba. E5 3.00 → 3.625; **v2 ≈82.8 %** | hecho 2026-07-24 | sin plan: devlog § E5 · commit `9e9f10c` |
| Segundo testigo | Paquete sobre la puerta plegable (id 28): 3 defectos de generalización corregidos; el 82.8 % vale sobre un modelo BIEN DECLARADO | hecho 2026-07-24 | sin plan: [informe](benchmark/puerta-plegable-bifold/2026-07-24/informe-generalizacion.md) · devlog § SEGUNDO TESTIGO · commit `703bad4` |
