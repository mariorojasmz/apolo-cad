# Servicios de dominio (`core/apolo/services/`)

La lógica que LEE un `Document` y que comparten sus clientes: mapas por pieza de los planos,
datos de la lámina de instalación, evaluación de las cadenas de cotas, aserciones `verify` y
contrato `expect`, insumos de la puerta de entrega, reglas de ingeniería y FEA. Nació al partir
`api/main.py` ([plan](../../../docs/plans/partir-api-main.md)). Lo transversal (locks, log,
fronteras) está en el [CLAUDE.md raíz](../../../CLAUDE.md); lo común del backend, en
[core/apolo](../CLAUDE.md); el transporte que los llama, en [api](../api/CLAUDE.md).

## Reglas de la capa

- Capas: kernel/commands/doc/library/drawing/fea/assembly/robotics ← `services` ← `api` y
  `agent`. Cada función recibe `doc` EXPLÍCITO y jamás lee un global de sesión: `_piece_dim_tols`
  medía con el `DOC` activo aunque recibiera su `doc`, y los tests lo tapaban con `api.DOC = doc`.
- Sin `fastapi`, `apolo.api` ni `apolo.agent` (el agente no puede importar la API); un 400/404
  es un error de dominio (`ValueError`, `CommandError`) que traduce la API. Sin locks: el
  llamador sostiene `STATE_LOCK`. Lo hace cumplir `tests/test_capas_services.py` (AST, también
  los imports perezosos).
- Los imports pesados quedan DENTRO de la función (gmsh, VTK, matplotlib…): importar la API no
  los carga (`tests/test_api_opcionales.py`).
- Nombres públicos sin `_`. `api/main.py` re-exporta POR IDENTIDAD los nombres viejos que usan
  los tests (`_piece_dim_tols`, `_feature_fit_maps`, `_installation_data`…); `_stackup_rules()`,
  `_fea_rules()` y `_suggest_ids(m)` quedan como envoltorios sobre el documento activo.
- Lo que sólo el transporte sabe hacer se INYECTA, no se importa: `expand` (nombres de grupo →
  fids; en la API es `_expand_ids`, que toma `STATE_LOCK`) entra como argumento keyword.

## Mapas por pieza para los planos (`drawing_maps.py`)

- **Fits por pieza**: `feature_fit_maps` da {feature_id → {Ø → clase}} desde el NOMBRE
  («… Ø35 g6») + `drill_hole.fit`, y cada lámina rotula EL SUYO (`sheet_set(piece_fits=)`). El
  conjunto usa `scene_fit_map` (`hole_fit_map` = el mismo sobre toda la escena), que OMITE un Ø
  en conflicto: mejor ausente que equivocado. `drawing_spec` lo computa sobre la escena EFECTIVA
  (aislar un eje da su fit). [V7.2c](../../../docs/plans/V7.2c-fixes-re-auditoria.md)
- **Datum funcional**: `piece_datum_sides` deriva los lados de montaje de los FASTENERS
  declarados (soldadura > perno > contacto; eje = solape mínimo de bboxes); PROHIBIDO inferir por
  nombre. Devuelve LISTA por peso: la cara que atraviesa un perno es ⊥ a la vista de sus círculos,
  así que cada vista usa el primer lado que proyecte como borde.
  [V7.5](../../../docs/plans/V7.5-e22-datum-funcional.md)
- **GD&T**: `piece_datum_frame` = A (cara de mayor peso) + B/C sólo si son ORTOGONALES; el
  `motivo` va a la leyenda (sin él, el marco es decorativo). `piece_pos_tols`: t =
  `bolt_pattern_budget(flotante=)`; el Ø del perno sale de la tabla ISO 273 INVERTIDA (Ø13.5 es el
  paso de un M12) y el sólido en el eje es respaldo. Sin perno identificable NO hay marco: una
  tolerancia inventada es peor que su ausencia (el taller la fabrica).
- **Tolerancia justificada**: `piece_dim_tols` sale de los eslabones `{id, eje}` de las cadenas
  DECLARADAS, medidos sobre SU `doc`; sólo bandas SIMÉTRICAS (un fit asimétrico viaja en su
  callout); varias cadenas → gana la más estricta; una cadena inválida no tumba el juego.
- `sheet_set_maps(doc)` arma los 10 kwargs de `sheet_set` que salen del documento, comunes al
  juego en PDF y en DWG; el cajetín, los colores del viewport y el `shaded` del PDF los pone el
  endpoint. Un mapa nuevo para las láminas se suma AQUÍ, no en cada endpoint.

## Instalación (`installation_data.py`)

- `installation_data` excluye la tornillería (`lints._is_bolt`) de los apoyos (los pernos de
  anclaje como grounds diluían la carga por apoyo 5×), lee las claves del catálogo sin distinguir
  mayúsculas (`potencia_kW`) y devuelve `({}, {})` sin grounds. Reparto de carga en
  [library](../library/CLAUDE.md); la lámina, en [drawing](../drawing/CLAUDE.md).
  [V7.6](../../../docs/plans/V7.6-e2-fino.md)

## Stack-up (`stackup_eval.py`)

- `evaluate_stackups` aísla cada cadena (una mala = `{error}`, nunca tumba GET ni la memoria);
  pieza FALTANTE = error sin veredicto, jamás parcial; «cerrada por construcción» sólo si el
  fasten lo creó un comando `join_bolted` (no por nombre `jb_*`); un perno manual = holgura
  informativa, sin veredicto. El rollback del PUT es del endpoint ([api](../api/CLAUDE.md)).
  [V7.3](../../../docs/plans/V7.3-stackup-cadenas-cotas.md)

## Aserciones (`assertions.py`, `lookup.py`)

- `verify_checks(doc, scene, …)` es la fuente ÚNICA de `/api/verify` y del contrato `expect`
  (`contract_verify` → callback de `execute_many`/`edit_many`; el rollback es de
  [api](../api/CLAUDE.md)). [V6.5b](../../../docs/plans/V6.5b-mcp-accion-con-contrato.md)
- `$k` resuelve a los FEATURE_IDS del comando k, 1-INDEXADO (`$1` = primera acción; `$0` lo
  explica el error). Multi-sólido expande en `ids`; en un campo singular → error accionable,
  nunca elige uno. Una clave desconocida en una aserción → error «no reconocida» con las válidas;
  «sin piezas» nombra los tokens que no resolvieron. [V6.5c](../../../docs/plans/V6.5c-fixes-revision.md)
- «¿Quisiste decir…?» (`suggest_ids`: difflib sobre fids + command_ids + grupos + substring de
  nombre) en los 404 por id y en los selectores de verify/expect; un command_id multi-sólido
  sugerido → sus fids hijos, nunca él mismo.
- `distancia`/`sin_interferencia` aceptan `joint_values` POR ASERCIÓN y se evalúan con el
  mecanismo POSADO (`pose_fn` inyectado en `library/verify.run_verify`, que sigue pura). `pose_fn`
  valida los nombres de junta ANTES de posar: la FK ignora desconocidos y el typo pasaría verde.
  En pose la interferencia suma `interpenetration_report`; caché por pose (N aserciones = 1 FK);
  todo-cero = pose de diseño. [V6.8](../../../docs/plans/V6.8-mcp-fluidez.md)
- `extra_exclude_pairs/ids` son las exclusiones de la puerta de entrega; `None` deja los
  contratos intactos.

## Puerta de entrega (`delivery_inputs.py`, `assertions.delivery_poses`)

- `delivery_inputs(doc)` arma los kwargs de `library.delivery.delivery_report` salvo la gravedad
  (opt-in: la simula la API con su lock). Excluye lo DECLARADO (par con fasten, tornillería a
  medida por `_is_bolt`) con las MISMAS exclusiones en diseño y en las poses de REPOSO
  (`delivery_poses`: extremos + dwells); el porqué, en [library](../library/CLAUDE.md).
  [V6.9](../../../docs/plans/V6.9-puerta-de-entrega.md)

## Reglas de ingeniería y FEA (`engineering_rules.py`, `fea_rules.py`)

- `/api/checks` y la memoria comparten SÓLO lo idéntico (`requirement_inputs`,
  `inherit_inclination`, `structure_rules` = estructura universal + FEA). Sus diferencias son
  deliberadas y quedan en cada endpoint: velocidad con `or` (checks) vs `is not None` (memoria),
  lints sólo en checks, stack-up y «alcance de la memoria» sólo en la memoria. No las unifiques.
- `conveyor_params_from_doc` es de los tres clientes (checks, memoria, tool `engineering_check`
  del agente, que la importa con su nombre viejo).
- `fea_rules`: VIGENCIA por volumen (>0.1 % de cambio, o pieza borrada → aviso «re-ejecuta»); el
  de ensamblaje por volumen CONJUNTO de `piezas_fids`. Tabla por pieza con tope 8 filas, 5 si
  hay historial de convergencia (el calc_report imprime ≤ 12); `hipotesis` va a la memoria.

## Roles por nombre (`roles.py`)

- `BED_RE` (cama/mesa: recibe la carga del FEA y da la altura de trabajo de la instalación) y
  `SERVICE_RE` (piezas que se extraen: holgura de servicio). Un matcher por nombre nuevo lleva
  guarda de bracket/anclaje y un test con el nombre REAL ([drawing](../drawing/CLAUDE.md)).
