# HANDOFF — Traspaso a sesión nueva (2026-07-04)

## Qué es esto
Mini-informe para arrancar una sesión nueva de Genix Apolo CAD. La sesión anterior
(modelo Fable 5) diseñó el plan V6.1; esta sesión (modelo Opus 4.8) lo EJECUTA.

## Dinámica de trabajo acordada con el usuario
- **Fable 5** (muy potente, caro) → diseña planes.
- **Opus 4.8** (menos potente) → ejecuta.
- El plan detallado está en [`docs/plans/V6.1-robustez-industrial.md`](V6.1-robustez-industrial.md)
  — **LÉELO ENTERO, incluida la sección final "GUÍA PARA EL EJECUTOR"** antes de tocar nada.
  Trae compuertas, trampas del código y firmas exactas para que no tengas que
  redescubrir el terreno.

## Estado del proyecto a hoy
- **887 tests verdes**, 66 tools MCP, 48 comandos, catálogo 217 refs.
- **Completado**: Tier 1 (V5.1–V5.5), Tier 2 casi todo (V5.6 FEA, V5.7 roscas,
  V5.8 ingletes, V5.9 DWG — solo queda "superficies básicas", por demanda),
  V5.10 normas del vertical (primer Tier 3).
- **Último commit**: `ecb4afd` (V5.10). El árbol está LIMPIO (todo commiteado).
- Toda la narrativa detallada de cada release está en `docs/devlog.md` y `git log`.

## El giro de rumbo (importante — el POR QUÉ del plan V6.1)
El usuario dijo que había estado confiando ciegamente y se preocupó de que se
estuvieran escogiendo rumbos fáciles. Pidió explícitamente **máxima ambición pro**.
Diagnóstico acordado: el roadmap V5 se agotó y los ítems que quedaban (render bonito,
plantillas de plano) eran cosmética. Se abre un **roadmap V6 "Apolo industrial"** que
ataca los ejes de madurez más débiles del propio CLAUDE.md, empezando por el menos
vistoso y más pro: **robustez (3/10)**.

## Lo que hay que hacer: V6.1 Robustez industrial
Contrato: **nada debe tumbar el documento**. Tras cualquier fallo (excepción OCCT,
comando inválido, .apolo corrupto, fuzzing de undo/redo) el documento queda íntegro y
verificable. Filosofía: **PRIMERO la suite de tortura (tests rojos), DESPUÉS los
fixes que la ponen verde.**

Dos exploraciones exhaustivas encontraron 9 áreas frágiles + 2 bugs nuevos de PÉRDIDA
DE DATOS (uno serio: `/api/project/new` sobrescribe el proyecto anterior en SQLite).
Todo el mapa con evidencia de líneas de código está en el plan.

Orden: Fase 0 (check_integrity + health) → Fase 1 (tortura roja) → Fase 2 (fixes doc)
→ Fase 3 (fixes API) → Fase 4 (perf baseline) → Fase 5 (E2E vivo) → Fase 6 (docs +
roadmap V6 + 2 commits).

## Cómo empezar la sesión nueva
1. Lee `docs/plans/V6.1-robustez-industrial.md` completo.
2. Lee el `CLAUDE.md` del repo (convenciones que NO se negocian).
3. Arranca por la Fase 0. Respeta las compuertas del plan (no avances si no pasan).
4. Entorno: `.\.venv\Scripts\python.exe -m pytest tests -q` para la suite;
   `.\start-apolo.ps1` para la API. Proyectos de referencia: faja id 38, layout id 53.

## Roadmap V6 completo (para contexto — se documenta en CLAUDE.md al cerrar V6.1)
- V6.1 Robustez industrial ← ESTE (robustez 3→6)
- V6.2 Rendimiento (open frío con caché BREP, deltas de payload, dos-locks; 4→6)
- V6.3 Ensamblaje pro (multi-mate por sólido, conectores por ancla, DOF; 4.5→6)
- V6.4 Paramétrico profundo (faja 38 100% paramétrica testigo, tablas de diseño; 5→6.5)
- V6.5 Croquis vivo (arrastre soft-constraints, splines/elipses; 5→6.5)
- V6.6 FEA de ensamblaje bonded (4.5→5.5)

## Pendientes menores del usuario (recordatorios)
- Proyectos basura "Sin título" (id 26, 27, 46, 60) y `perf-test-batch` — borrar
  desde la UI.
- ODA File Converter 27.1.0 está instalado (para el DWG de V5.9).
