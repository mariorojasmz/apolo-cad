# Comandos (`core/apolo/commands/`)

El registro schema-driven: `models.py` (params pydantic = schema de UI, diálogos y tools del
agente), `registry.py` (executors + `REGISTRY`), `spec.py` (`CommandSpec` + `run_executor`, el
despacho), `state.py` (`RegenState`, el estado con nombre que `execute_command` muta y el
regenerate guarda como checkpoint; `ExecContext`, lo que recibe un executor), `strict.py` (la
entrada estricta de params), `errors.py` (`CommandError`) y `expressions.py` (motor de `=expr`). Lo transversal (locks, log, regenerate, cirugía de modelos) está en el
[CLAUDE.md raíz](../../../CLAUDE.md); lo común del backend, en [core/apolo](../CLAUDE.md).

## Al agregar o cambiar un comando

- Todo executor es `_exec_x(ctx: ExecContext, cmd_id, p)`: `ctx.scene`, `ctx.joints`,
  `ctx.fasteners`… son los dicts VIVOS (se mutan en sitio), `ctx.attachments` los adjuntos y
  `ctx.resolved_variables()` las variables evaluadas. Ningún flag elige la firma (lo exige
  `tests/test_despacho_unico.py`): si un comando necesita más contexto, es una propiedad de
  `ExecContext`, no un flag ni una rama en el despacho.
  [plan](../../../docs/plans/estado-regen-y-params-estrictos.md)
- **Params estrictos** (`strict.py`): la ENTRADA de un cliente (las cuatro puertas de `Document`
  y `validate_actions` del agente) rechaza la clave que el modelo no declara, con su ruta, las
  válidas y «¿quisiste decir…?»; el REPLAY la ignora (`extra="ignore"` explícito) y un edit sólo
  rechaza las que el cliente INTRODUCE (la UI reenvía los params guardados). Los modelos NO fijan
  `extra`: cambiaría el JSON Schema publicado. Quitar o renombrar un campo exige upcaster; un
  campo nuevo entra con un default que reproduce lo anterior (trinquete D12:
  `tests/test_contrato_comandos.py`).
- La `description` del modelo es para el AGENTE (larga a propósito, con nombres de params); la
  persona lee la PISTA de `pistas.py` (vista `?vista=persona`, `vista_persona.py`): un comando
  nuevo sin pista rompe `tests/test_pistas.py` ([ui](../../../ui/CLAUDE.md)). Un super-comando reutilizable
  documenta ahí su MONTAJE (orientación, tensado, soldadura), no sólo qué es.
- **Versión del executor** (`CommandSpec.version`): si cambia la geometría que produce con los
  MISMOS params, sube SU `version` (entra a la firma del regenerate sólo si es ≠ 1 → invalida la
  caché sólo de los proyectos que lo usan); si cambiaste un helper compartido, la de cada
  comando que lo usa; lo que no puedes acotar (kernel, builders, catálogo, `Feature`) es bump de
  `GEOM_CACHE_EPOCH` (regla completa en la [raíz](../../../CLAUDE.md)). Un comando que reproduce
  OTROS executors va con `composite=True` (hoy `insert_project`). El trinquete D11
  (`tests/test_contrato_comandos.py`) guarda versión + huella del código de cada executor: si el
  código cambia y la versión no, falla y obliga a decidir (subirla, o sólo la huella si fue un
  refactor).
- Errores de OCCT accionables: fillet/chamfer nombran la arista más corta seleccionada; `shell`
  pre-valida `2·espesor ≥ dimensión menor` antes de OCCT (condición necesaria, sin falsos
  positivos). No blindar geometría fina (radio vs caras vecinas): el `try/except` de OCCT es la
  red. [V6.1](../../../docs/plans/V6.1-robustez-industrial.md)

## Modelado y colocación

- `add_joinery` (espiga/dado/dowel/rebaje) corta EN SITIO y conserva ids: es la vía para tallar
  una pieza con juntas (nunca `boolean_op`, ver raíz § cirugía).
- `pattern_group` arraya TODAS las features de un comando; rechaza fuentes con juntas o mates.
- `center_in`/`distribute`/`snap_to` son RELACIONALES: se reevalúan en cada regenerate.
  `snap_to` bbox-a-bbox (`alinear` centra en los otros ejes) o CARA-A-CARA (`cara` + `cara_target`
  planas, `gap`, `deslizar` {u,v}): rotación MÍNIMA con normales anti-paralelas vía
  `_world_place` (axis-angle, misma convención que `Shape.rotate`). Caras cilíndricas → mates.
  [V6.8](../../../docs/plans/V6.8-mcp-fluidez.md)
- `drill_hole` por cara (`cara` + `en_cara` {u,v}, excluyente con `position`): entra por ese
  punto y avanza por −normal; un `axis` explícito gana (se detecta con `model_fields_set`).
  Frame de cara (`_planar_face_frame`): u = eje de MAYOR extensión, signo hacia la componente
  mundial dominante +; v = n × u.
- Trampas: la cara «tope» (bbox) de una barra INCLINADA es su extremo cuesta arriba; para la
  cara superior usa `cerca` con un punto encima. Un taladro OBLICUO arranca EN el punto de
  entrada y deja sin remover la cuña cuesta arriba (⅔·r³·tanθ).
- `transform_group` mueve el grupo como cuerpo rígido sobre el centro del bbox CONJUNTO
  (`kernel/shapes.py::move_rotated_about`; la rotación por pieza de `_world_move` es incorrecta
  para grupos). Juntas y mates internos viajan; uno que CRUZA la frontera → `CommandError`.

## Juntas y conectividad

- `add_joint(arrastrar)` va por defecto en **False**: True cambiaría el replay de logs viejos y
  chocaría con juntas `fija` manuales posteriores. Hace flood por el grafo de FIJADORES
  declarados hasta ese punto del log (cada lado excluye el nodo contrario), materializa
  `jf_<junta>_<fid>` y publica `arrastre` {arrastrados, frontera, avisos} en la junta. La disputa
  es VIRAL: nada disputado se arrastra (aviso); lo ya hijo de otra junta o anclado a tierra se
  omite con aviso. [V6.8](../../../docs/plans/V6.8-mcp-fluidez.md)
- `fasten`: `size`/`qty` dimensionan un perno; `throat_mm` ES la garganta de la soldadura
  (a = 0.707·cateto).
- `join_bolted` taladra barrenos de PASO (ISO 273 serie media) en AMBAS piezas EN SITIO, inserta
  perno HEX DIN 933 + tuerca DIN 934 de catálogo y declara el `fasten` `jb_{cmd_id}`. Contacto
  AUTO por solape de cajas (`_join_bolted_geometry`, puro: el patrón se recentra si una pieza
  crece). Exige caras PLANAS ⊥ al eje en contacto y asientos (≥ 50 % de la huella), borde
  ≥ 1.5·d, paso ≥ 2.5·d, n·m ≤ 100; largo = grip + tuerca 0.8·d + 3 filetes, redondeado a
  comercial. Pieza rotada/no prismática o separadas → error que pide mates o `snap_to`, nunca
  pernos flotantes. [V6.5b](../../../docs/plans/V6.5b-mcp-accion-con-contrato.md) ·
  [V6.5c](../../../docs/plans/V6.5c-fixes-revision.md)

## Super-comandos de máquina

- `create_drive_roller` es de eje FIJO: un tambor MOTRIZ real necesita eje vivo + chumaceras.
- `create_take_up(eje_fit=…)` anota el asiento en el nombre («Ø35 g6»): eje fijo → g6/h6, nunca
  k6 (lo verifica [library](../library/CLAUDE.md)). [V7.2b](../../../docs/plans/V7.2b-barrida-residuos.md)
- Bastidores con ingletes (`create_weldment`/`create_frame`): [library](../library/CLAUDE.md).
  `insert_project`: [doc](../doc/CLAUDE.md).

## Expresiones (`expressions.py`)

- `=expr` acepta ternario `a if c else b` (PEREZOSO: la rama no tomada no se evalúa),
  comparadores encadenados y `and`/`or` (colapsan a 1.0/0.0); sin strings, listas, `in`, `is` ni
  lambda. [V6.4](../../../docs/plans/V6.4-parametrico-profundo.md)
