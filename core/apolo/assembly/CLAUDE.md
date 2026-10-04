# Ensamblaje (`core/apolo/assembly/`)

Mates, restricciones, reporte de DOF, grupos (sub-ensamblajes) y conectividad/soundness:
funciones sobre la escena, sin geometría propia. La cinemática (FK, GIF del estudio) y la física
viven en [core/apolo](../CLAUDE.md); lo transversal (locks, log, flujo de trabajo), en el
[CLAUDE.md raíz](../../../CLAUDE.md).

## Mates (`mates.py`)

- Se re-resuelven en cada regenerate. Un sólido puede ser hijo de ≥ 2 mates (DAG multi-padre);
  un lazo A↔B se rechaza como ciclo.
- Dos caminos de solver: 1 mate por hijo → `_solve_one`, cerrado y exacto (pose determinista: no
  tocar); ≥ 2 → `_solve_multi` (least_squares 6-GDL con rotación sobre el CENTRO de B: sobre el
  origen no converge si B está lejos). Los residuos de `_mate_residuals` deben ser consistentes
  con `_desired_current_frames`, y cada mate restringe sólo sus GDL naturales. Costo >
  `_MATE_TOL` tras un reintento → `MateError` que nombra los mates → rollback.
- Conectores: cara plana/cilíndrica, arista circular (`{"entidad": "arista"}` → centro + eje) o
  ANCLA (`{"mode": "ancla", "name": …}` → `Feature.anchors`, frames MUNDO que publican los
  executors: chumacera «centro», NMRV «bore», faja «eje_motriz»/«eje_cola»). Toda transformación
  las mueve con `kernel/matrix.transform_anchors`, que REEMPLAZA y nunca muta; `get_topology`
  las lista.
- Riel de lazo cerrado (`add_rail_constraint`) y restricciones N-GDL (`constraints.py`:
  least_squares global; punto_en_recta/plano/coincidente/distancia).
- Trampas abiertas de la revisión (mirror no propaga anclas, sentido anti-paralelo en
  multi-mate, tolerancia angular ×L, `EdgeSelector` compartido):
  [V6.3d](../../../docs/plans/V6.3d-fixes-revision.md). [V6.3](../../../docs/plans/V6.3-ensamblaje-pro.md)

## Reporte de DOF (`dof.py`)

- `dof_report` es puro y HEURÍSTICO (conteo de Grübler: no ve redundancia geométrica); un
  «sobre_restringido» por conteo puede ser benigno: los conflictos reales los rechaza el solver
  de mates. Aquí las juntas SÍ cuentan como restricción (en el resto son visualización).

## Grupos (`groups.py`, `grouping.py`)

- Un grupo se define por COMMAND_IDS, no por feature_ids (que desaparecen al editar un `count`):
  toda pieza presente o futura de esos comandos pertenece. Un comando vive en UN grupo; `parent`
  se declara ANTES (ciclos imposibles); un miembro borrado queda en `missing_members` (tolerante).
- `feat.group` es DERIVADO: se asigna al final de cada regenerate; los grupos van en el
  checkpoint (`RegenState.groups`, [commands](../commands/CLAUDE.md)).
- `propose_groups` (`auto_group`, con `dry_run`) es la heurística de subsistemas del árbol
  portada al backend: idempotente; sin señal → sin grupo.
- Los consumen el manual (pagina por grupo), la BOM `by_group` (por defecto byte-idéntica) e
  isolate/highlight/fit por nombre ([api](../api/CLAUDE.md)). Commits `7f611d9`, `8ad19a2`.

## Conectividad (`connectivity.py`, `autodetect.py`)

- Grafo juntas ∪ mates ∪ fasteners con semilla `grounds`; `soundness_report` dice qué flota.
- `detect_structure` es el grafo de soporte DIRIGIDO (auto-declara ground/fasten); también ordena
  el manual de ensamblaje ([drawing](../drawing/CLAUDE.md)).
- La puerta de entrega y las interferencias: [library](../library/CLAUDE.md).
