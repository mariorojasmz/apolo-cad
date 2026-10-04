# Servicios de dominio (`core/apolo/services/`)

La lógica que LEE un `Document` y que comparten sus clientes: mapas por pieza de los planos,
datos de la lámina de instalación, evaluación de las cadenas de cotas. Nació al partir
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
  los tests (`_piece_dim_tols`, `_feature_fit_maps`, `_installation_data`…); `_stackup_rules()`
  queda como envoltorio sobre `stackup_rules(doc)` del documento activo.

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

## Roles por nombre (`roles.py`)

- `BED_RE` (cama/mesa: recibe la carga del FEA y da la altura de trabajo de la instalación) y
  `SERVICE_RE` (piezas que se extraen: holgura de servicio). Un matcher por nombre nuevo lleva
  guarda de bracket/anclaje y un test con el nombre REAL ([drawing](../drawing/CLAUDE.md)).
