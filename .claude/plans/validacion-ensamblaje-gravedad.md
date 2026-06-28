# Plan — Validación de ensamblaje por física (gravedad / "soundness" del montaje)

> Estado: **APROBADO. Fase 0+1 ✅, Fase 2 ✅ y Fase 3 (UI + caída animada en viewport) ✅ (2026-06-26).**
> Pendiente de Fase 3: solo la cinemática (juntas en tambores → ver la banda correr).
> UI: panel "Montaje" (`ui/src/panels/AssemblyPanel.tsx`: validar soundness + prueba de gravedad + ▶/⏸/↻/Limpiar
> + Exportar GIF; la selección = `exclude`) + **caída animada en el viewport 3D sobre las MALLAS REALES**
> (`ui/src/viewport/gravity.ts`, estado `gravity*` en store, backend `com`+`include_frames`). Build verde, 494 tests.
>
> **Fase 2 entregada** (494 tests): `physics/hull.py` (casco convexo cacheado con ref fuerte al shape),
> `physics/stability.py` (`stability_test`: grounded→estático, resto→dinámico que cae, colisión por casco;
> params `with_autodetect`/`exclude`), endpoints `/api/assembly/stability[.gif]` (GIF reusa `render_drop_gif`),
> tool MCP `gravity_test`, `tests/test_stability.py`. Verificado en vivo: rodillos de retorno `exclude`→ caen
> 682.8 mm. La física resuelve holder-vs-held (lo que el grafo estático no podía). Límite: casco convexo rellena
> concavidades.
> Autor: agente. Fecha: 2026-06-26. Proyecto piloto: `faja-paqueteria-4m` (id 38).
>
> **Fase 0+1 entregada** (490 tests): comandos `ground`/`fasten` (event-sourced, `wants_connectivity`),
> `Document.fasteners`/`grounds` threadeados por el regenerate incremental, `assembly/connectivity.py`
> (grafo + `soundness_report`), `assembly/autodetect.py` (propuestas por geometría), endpoints
> `/api/assembly/{soundness,autodetect}` + `/api/connectivity`, tools MCP `check_assembly`/
> `autodetect_connections`, `tests/test_connectivity.py`. Verificado en vivo sobre la faja.
> **Aprendizaje de la Fase 1**: el grafo de contacto AABB es no-dirigido (no sabe quién sostiene a quién)
> → el cierre da 0 flotantes; el veredicto fino lo dará declarar uniones reales o la Fase 2 (sim dirigida).

## 1. Objetivo (en palabras del usuario)

Un sistema que ayude a alguien que **aprende a construir máquinas** a ver en 3D **si la máquina está
bien armada**: que el eje del rodillo esté **capturado** y no se salga, que un rodillo de apoyo **se
caiga** si no está sujeto, que una guarda **se caiga** si le falta el tornillo, que el motor **se caiga**
si solo estaba flotando. En una frase: *emular la gravedad sobre toda la máquina y ver qué se cae.*

**Esto NO es FEA.** No mide tensiones ni deformación (¿se dobla/rompe el acero?). Mide **conectividad
física**: ¿cada pieza tiene una cadena de sujeción hasta el piso? Es **dinámica de cuerpos rígidos** +
un **análisis de grafo de uniones**. FEA sigue fuera de alcance (decisión vigente del proyecto).

## 2. El problema de raíz (evidencia)

`faja-paqueteria-4m` tiene **0 juntas, 0 mates, 0 restricciones**. Las 92 piezas están *colocadas* en
coordenadas correctas pero el sistema **no sabe que están unidas**: nada declara "el motor está
atornillado al bastidor" ni "el eje va dentro del rodamiento". Hoy no existe un **grafo de
conectividad**. Sin él, ni un análisis estático ni una simulación de gravedad pueden razonar sobre qué
sostiene a qué. Ese es el cimiento que falta y el núcleo de este plan.

## 3. Modelo conceptual

Cada pieza es uno de cuatro estados respecto al soporte:

1. **Anclada a tierra** (`ground`): fijada al piso (placas de anclaje). Nunca cae.
2. **Sujeta** a otra pieza por **junta** (`add_joint`), **mate** (`add_mate`) o **fijador** (`fasten`:
   perno/soldadura/pegado). Hereda soporte transitivamente.
3. **Solo apoyada** (contacto, sin fijador): la gravedad la sostiene por normal/fricción. Frágil:
   puede deslizar/caer. Se reporta como AVISO, no como OK.
4. **Flotando**: nada la sujeta → cae.

**Validación = encontrar toda pieza sin camino de sujeción hasta tierra.** El grafo lo decide de forma
exacta; la simulación lo hace visible.

## 4. Arquitectura (fronteras limpias — mandato del proyecto)

| Capa | Módulo | Responsabilidad |
|---|---|---|
| Datos (event-sourced) | `doc/document.py` | Almacena `fasteners` y `grounds` (espejo de `mates`/`constraints`), persiste en manifest, thread por `regenerate`. |
| Comandos + schema | `commands/registry.py`, `commands/models.py` | Comandos nuevos `ground`, `fasten` (flag `wants_connectivity`). |
| Análisis puro | `assembly/connectivity.py` **(NUEVO)** | Construye el grafo (juntas+mates+fasteners+grounds+contactos) y el **reporte de soundness**. Determinista, sin OCCT pesado, testeable aislado. |
| Detección geométrica | `assembly/autodetect.py` **(NUEVO)** | Propone uniones desde la geometría (perno-pasante, eje-en-agujero, cara-contra-cara, apoyo-en-piso). Devuelve propuestas; NO muta. |
| Física | `physics/stability.py` **(NUEVO)** | Mundo MuJoCo de TODA la máquina desde el grafo; corre gravedad; desplazamiento por pieza. Espejo de `physics/sim.py`. |
| Geometría de colisión | `physics/hull.py` **(NUEVO)** | Casco convexo por sólido (teselado → vértices) para colisión fiel (no AABB). |
| Masas/inercia | `robotics/model.py::_link_physics` (REUSO) | Masa por volumen×densidad de catálogo; ya existe. |
| Transporte | `api/main.py` | Endpoints REST nuevos (abajo). |
| Clientes IA | `mcp_server.py` | Tools MCP nuevas (abajo). |
| UI | `ui/src/panels/*` | Panel de soundness + modo gravedad en `PhysicsPanel`; resaltado en viewport. |

**Nomenclatura:** NO usar "attachment" (en el código = ficheros STEP de `import_step`). Las uniones
de ensamblaje se llaman **`fastener`** (fijador rígido A↔B) y **`ground`** (ancla a tierra). El grafo
total = juntas ∪ mates ∪ fasteners ∪ grounds (∪ contactos detectados).

**Dos niveles, no uno:** el chequeo **estático** (grafo) corre siempre, es instantáneo y exacto; la
**simulación** física es a demanda y pesada. Nunca esperar a MuJoCo para saber que algo flota.

## 5. Fases

### Fase 0 — Modelo de conectividad (cimiento)
- **Datos:** `Document.fasteners: dict`, `Document.grounds: dict`; threading por `regenerate` y
  `execute_command` (flag nuevo `wants_connectivity`, rama de dispatch aditiva); persistencia en el
  manifest `.apolo` (espejo de `mates`/`constraints`).
- **Comandos** (`registry.py` + `models.py`): 
  - `ground {feature, [normal], [nota]}` — ancla una pieza a tierra.
  - `fasten {a, b, kind: "perno"|"soldadura"|"pegado", [at], [nota]}` — fijador rígido A↔B.
  - Categoría `ensamblaje`. Editables/undo/replay como todo comando.
- **Tests:** `tests/test_connectivity.py` — crear ground/fasten, persistencia, undo, rechazo de
  self-fasten / pieza inexistente.
- **Aceptación:** se pueden declarar uniones y sobreviven a regenerate/undo/guardar-abrir.

### Fase 1 — Chequeo estático de soundness (el 80% del valor, sin física)
- `assembly/connectivity.py`:
  - `build_graph(scene, joints, mates, fasteners, grounds) -> Graph`.
  - `soundness_report(graph) -> {grounded:[...], floating:[...], resting_only:[...], components:[...]}`
    (componentes conexos; una pieza es "grounded" si su componente toca un `ground`).
- `assembly/autodetect.py`:
  - `detect_connections(scene) -> {fasteners:[...], grounds:[...], contacts:[...]}` por geometría:
    - **perno-pasante**: una pieza tipo tornillo cuyo bbox cruza 2 piezas → las une.
    - **eje-en-agujero**: cilindro dentro de un agujero/rodamiento coaxial → acople.
    - **cara-contra-cara**: gap 0 entre caras planas (vía `kernel/measure.py`) → apoyo/fijador candidato.
    - **apoyo-en-piso**: `bbox.min.z ≈ 0` → propuesta de `ground`.
  - Devuelve PROPUESTAS (con confianza); el usuario/agente confirma → emite `ground`/`fasten`.
- **Endpoints:** `POST /api/assembly/soundness`, `POST /api/assembly/autodetect`.
- **MCP:** `check_assembly` (soundness), `autodetect_connections` (propuestas).
- **UI:** panel de soundness (reusar/ampliar `ChecksPanel.tsx` o nuevo `AssemblyPanel.tsx`): lista de
  piezas flotantes/solo-apoyadas con **clic→resaltar** en viewport; botón "Auto-detectar uniones".
- **Tests:** `tests/test_soundness.py` — pieza suelta→floating; con fastener→grounded; cadena
  transitiva; autodetect de perno-pasante y apoyo-en-piso.
- **Aceptación (sobre la faja real):** el reporte dice EXACTAMENTE qué piezas flotan y por qué; tras
  auto-detectar + confirmar, la mayoría queda "grounded" y solo restan las uniones que faltan de verdad.

### Fase 2 — Simulación de gravedad de toda la máquina (lo visual)
- `physics/hull.py`: teselado de cada `shape` → casco convexo (scipy `ConvexHull` o qhull) → `<geom
  type="mesh">` MuJoCo. Cae la limitación AABB (eje-en-alojamiento, rodillo-en-larguero fieles).
- `physics/stability.py` (espejo de `sim.py`):
  - Construye MJCF de la máquina: piezas `ground` → estáticas; fijadores → cuerpos fusionados o
    `equality`/`weld`; juntas → su GDL (`hinge`/`slide`); piezas libres → `freejoint` (caen).
  - Masa/inercia desde `_link_physics`. Corre gravedad N segundos.
  - Devuelve **desplazamiento por pieza** (mm respecto a su pose de diseño) + flag `cayo` por umbral.
- **Endpoints:** `POST /api/assembly/stability`, `POST /api/assembly/stability.gif`.
- **MCP:** `gravity_test` (corre la sim, devuelve qué se movió/cayó + guarda GIF).
- **UI:** modo "Prueba de gravedad (máquina)" en `PhysicsPanel.tsx`; reproducción en viewport
  (reusar el animador de `viewport/products.ts`), piezas caídas resaltadas en rojo.
- **Tests:** `tests/test_stability.py` (`importorskip mujoco`) — pieza libre se desplaza > umbral;
  pieza grounded/fasten no se mueve; casco convexo captura un eje en su alojamiento.
- **Aceptación:** soltar gravedad sobre la faja y VER caer lo no sujeto; coincide con el reporte
  estático de la Fase 1.

### Fase 3 — Cinemática + pulido agente-nativo
- Juntas en los tambores → *motion study* para ver la banda "correr" (opcional, ya existe el motor de
  motion; solo faltan las juntas en este modelo).
- Reporte unificado "Validar máquina" (soundness + interferencias + gravedad) en un botón.
- Actualizar `CLAUDE.md`, memoria del agente, y exponer todo como tools MCP coherentes.

## 6. Decisiones técnicas
- **Casco convexo, no AABB** (salto de fidelidad real; resuelve lo que ya topamos en el drop-test).
- **Estático + físico** (dos niveles): exacto-rápido vs visual-pesado.
- **Auto-detección con confirmación** (propone, no impone): imprescindible para rescatar los 92
  sólidos sin re-modelar; declarar a mano todo sería inviable.
- **Event-sourced**: `ground`/`fasten` son comandos (undo/replay/editar), una sola fuente de verdad.
- **Reuso**: `_link_physics` (masa), `kernel/measure.py` (gaps para autodetect), `physics/anim.py`
  (GIF), `viewport/products.ts` (animación), patrón `constraints.py` (registro de relación).

## 7. Límites honestos
- Rigidez/resistencia (¿se dobla/rompe?) = **FEA**, fuera de alcance (vigente).
- Casco **convexo** aproxima cavidades cóncavas (mejor que AABB, no exacto).
- Soporte solo-por-fricción es intrínsecamente frágil en simulación → se reporta como AVISO.
- Auto-detección es heurística → siempre con confirmación.

## 8. Orden de entrega
**Fase 0 → Fase 1** (entrega de valor inmediato y exacto sobre la faja) **→ Fase 2** (lo visual) **→
Fase 3** (cinemática + pulido). Cada fase: backend + tests + (UI/MCP donde aplique) + e2e + CLAUDE.md.

## 9. Riesgos
- Teselado→casco convexo de 92 sólidos puede ser pesado para la sim/GIF (mitigar: cachear hulls por
  identidad de shape, como el mesh; limitar fps/segundos).
- Mapear fijadores a `weld`/`equality` en MuJoCo requiere tuning (alternativa robusta: fusionar
  piezas fijadas en un solo cuerpo rígido antes de simular).
- Autodetect con falsos positivos/negativos → por eso es propuesta-con-confirmación, no automática.
