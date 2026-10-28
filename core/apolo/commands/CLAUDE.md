# Comandos (`core/apolo/commands/`)

El registro schema-driven: `models.py` (fachada de los params pydantic = schema de UI, diálogos
y tools del agente; viven en `models_*.py` por familia), `escena.py` (`Feature`, `DEFINITIONS`,
`_require`/`_instanced`…: la capa de abajo), `exec_*.py` (executors por familia), `registry.py`
(el shim, el `REGISTRY`, el despacho y los schemas), `spec.py` (`CommandSpec` + `run_executor`, el
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
- **Params estrictos** (`strict.py`): la ENTRADA de un cliente (las cuatro puertas de
  `Document`; también el `preview` con que el chat ensaya sus propuestas) rechaza la clave que el
  modelo no declara, con su ruta, las válidas y «¿quisiste decir…?»; el REPLAY la ignora (`extra="ignore"` explícito) y un edit sólo
  rechaza las que el cliente INTRODUCE (la UI reenvía los params guardados). Los modelos NO fijan
  `extra`: cambiaría el JSON Schema publicado. Quitar o renombrar un campo exige upcaster; un
  campo nuevo entra con un default que reproduce lo anterior (trinquete D12:
  `tests/test_contrato_comandos.py`); si lo NUEVO debe nacer con otro valor, el sello de entrada
  (`CommandSpec.al_crear`) se lo pone sólo al comando que nace (`join_bolted.criterio`,
  `create_belt_conveyor.cierres`).
- **`models.py` es FACHADA** ([partir-nucleo-congelado](../../../docs/plans/partir-nucleo-congelado.md)
  F2): los params viven por familia —`models_base` (`Vec3`, `Rot3`, `_floor_to_int`, listas de
  catálogo), `models_basicos` (primitivas, patrones, colocación, `set_variable`),
  `models_maquinas` (conveyor, weldment, frame, script, brazo), `models_chapa`,
  `models_modificar` (caras, taladro, circular, espejo, ebanistería), `models_croquis` (croquis,
  barrido, loft, superficies) y `models_ensamblaje` (juntas, mates, restricciones, grupos,
  `insert_project`, ground)— y la fachada sólo re-exporta por IDENTIDAD, para siempre
  (`tests/test_rutas_viejas.py`, lista cerrada). Un modelo nuevo va a su familia (o a un
  `models_<tema>.py` nuevo, como `models_rodillos.py`) y se re-exporta en la fachada; una familia
  importa `Vec3`/`Rot3` de `.models_base`, nunca de `.models` (ciclo).
- **`registry.py` se partió igual** (mismo plan, F3 y F4): capas `escena` ← `exec_*` ←
  `registry`. `escena` (`Feature`, `DEFINITIONS`, `_require`, `_instanced`, `_orient_axis`,
  `_resolve_sel`), `exec_basicos` (primitivas, booleana, patrones, espejo, borrar, duplicar,
  `set_variable`), `exec_colocacion` (`_world_move`/`_world_place`, transform, center_in,
  distribute, attach, snap_to, `_planar_face_frame`), `exec_modificar` (caras,
  fillet/chamfer/shell, `_drill_tool`, drill_hole, add_joinery), `exec_croquis` (sketch_*,
  barrido, loft, superficies, thicken, revolve, extrude_poly, import_step), `exec_ensamblaje`
  (`_register_joint`, `_joint_drag`, juntas, mates, restricciones, ground, grupos,
  `_transform_point`/`_transform_dir`, transform_group), `exec_insertar` (`insert_project` y su
  precheck) y `exec_biblioteca` (run_script, brazo, conveyor + `_publish_axis_anchor`,
  weldment/frame + `_emit_weldment_parts`, chapa). Un `exec_*` puede importar de otro `exec_*`
  (sin ciclos) pero nunca de `registry` (params de la fachada `.models`). `registry.py` sólo
  DEFINE `REGISTRY`, `_validate_model`, `validate_params`, `execute_command`, `_schema_entry` y
  `command_schemas` (lo exige `tests/test_rutas_viejas.py`): un executor nuevo va a su `exec_*`
  y aquí sólo se importa. `registry` re-exporta cada nombre movido por IDENTIDAD, para siempre
  (lista cerrada en `tests/test_rutas_viejas.py`; los blobs viejos de la caché nombran
  `apolo.commands.registry.Feature`). `execute_command`/`validate_params` se quedan en
  `registry` y `execute_command` lee `run_executor` (de `spec`) por el módulo `registry`: los
  tests parchean `registry_mod.run_executor`. Mover un executor byte a
  byte deja su huella igual: nunca se actualiza `VERSIONES` por un corte.
- Los imports perezosos `from .registry import …` DENTRO de executors ajenos (`cilindro.py`,
  `exec_faja.py`, `tablero.py`…) no se tocan: son parte de su huella D11.
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
  refactor). La lógica de los dos trinquetes vive en `apolo/contrato_comandos.py` (viaja en la
  wheel; el test sólo guarda `CAMPOS`/`VERSIONES`). Un comando de EXTENSIÓN («x.algo», kind `scene`/`vars`) sigue la misma regla, con esas funciones; una
  ref de su catálogo suma el `epoch_catalogo` sólo a la firma de quien la nombra en sus params
  (`spec.REFS_DE_EXTENSION`; un compuesto, todas). [plan](../../../docs/plans/nucleo-abierto-extensiones-privadas.md) (A4)
- Errores de OCCT accionables: fillet/chamfer nombran la arista más corta seleccionada; `shell`
  pre-valida `2·espesor ≥ dimensión menor` antes de OCCT (condición necesaria, sin falsos
  positivos). No blindar geometría fina (radio vs caras vecinas): el `try/except` de OCCT es la
  red. [V6.1](../../../docs/plans/V6.1-robustez-industrial.md)

- `add_program` (V8.3 D3) es del carril: lo compila `electrico_programa.py` contra los bornes de
  SU PLC (caché por fuente + bornes) y un PLC lleva uno solo; varias tareas = varios PROGRAM en
  la misma fuente con `ciclos`. [V8.3](../../../docs/plans/V8.3-prueba-virtual.md)
- `add_cable.por` (V8.5 F4) es carril: el evaluador resuelve sus piezas (`modelo.Paso`) y el
  recorrido del cable de campo NO es geometría de escena: lo calcula al leer
  `services/cables_campo.py` (por qué, en el plan). [V8.5](../../../docs/plans/V8.5-tablero-3d.md)
- El aire va en el MISMO carril (V8.9 D1): `add_device` acepta refs neumáticas (designación de
  dos letras de su ficha `neumatico`, que gana a la eléctrica en una electroválvula) y `add_tubo`
  une PUERTOS; los evalúa `neumatica_eval.py` (un borne no es un puerto, ni al revés: se nombra
  el medio). `servicio` (sólo cilindros) alimenta el ERC neumático. Params en
  `models_neumatica.py`. [V8.9](../../../docs/plans/V8.9-neumatica.md)

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
- `insert_component(orientacion)` (`exec_componente.py`, params en `models_componente.py`):
  orienta UPN/IPE/L por ejes del mundo (U `largo`+`abre_hacia`, I `largo`+`canto`, L `alas`);
  excluye `rotation` ≠ 0 y sólo da giros rectos. v2 por las anclas de perfil abierto.
  [plan](../../../docs/plans/perfiles-con-acuerdo.md)
- `insert_component.criterio` (oculto, como el de `join_bolted`): 2 = la tornillería de largo a
  medida usa `length` (serie del catálogo o error con la lista) y lo deja en `cut_length`; 1 (log
  viejo) lo ignora como antes. Un dato que el criterio viejo ignoraba en silencio también se
  re-sella al EDITARLO (`CommandSpec.al_editar`, `doc/sello.py`): el modelador edita, no recrea.
  [defectos](../../../docs/defectos.md) (F6)
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
  (a = 0.707·cateto). `a`/`b` aceptan CONJUNTOS (`exec_uniones.py`): raíz de patrón = sus
  copias `{raíz}_{n}` (sin la fuente), `+` y corte `(…)[i:j:k]`; una unión `{name}[k]` por
  instancia, re-expandida en cada regenerate. Dos piezas sueltas = el dict de siempre (un log
  viejo regenera igual). [plan](../../../docs/plans/uniones-en-lote.md)
- `join_bolted` (`exec_union.py`) taladra AMBAS piezas EN SITIO, inserta la fijación de catálogo
  y declara el `fasten` `jb_{cmd_id}`. Contacto y patrón por solape de cajas (borde ≥ 1.5·d, paso
  ≥ 2.5·d, n·m ≤ 100, asientos planos ≥ 50 % de la huella). Campo OCULTO `criterio`: 1 (log
  viejo, sin el campo) = V6.5b/c tal cual (largo por la caja); 2 = taller (`union_taller.py`:
  rayo por el eje, base = la más gruesa, perno/remache ciego/tornillo para madera por
  `library/fijacion.py`); 3 = el 2 con el largo de CATÁLOGO o error
  accionable, sin el respaldo silencioso a 200 mm ([puerta-de-publicacion](../../../docs/plans/puerta-de-publicacion.md));
  4 = el 3 con acceso por detrás en el ala de un perfil ABIERTO (la otra ala re-cruza el eje,
  pero el hueco se abre al costado → perno + tuerca, no remache); 5 (todo comando nuevo) = el 4
  que, ya taladrado, rechaza un agujero a < 1,2·d0 del canto REAL (`library/borde_agujero.py`); 6 (todo
  comando nuevo, V8.9 F7b) = el 5 que, si una pieza YA trae sus agujeros en la huella (anclas
  «*agujero*»: pies y brida del cilindro), atornilla por ellos (`union_agujeros.py`). Un criterio
  nuevo, no un cambio del viejo: el que cambia qué inserta `join_bolted` es un número más. Lo pone el SELLO de entrada (`CommandSpec.al_crear`,
  `doc/sello.py`), con `madera` = las piezas de madera al crear: el replay y los edits no sellan,
  por eso no hubo `version` ni epoch. Cambiar el criterio 1 rompe logs guardados. v2 (F3f de
  puerta-sin-sobrediseno): el `fasten` de un remache declara su Ø («Ø4.8»), en todo criterio; misma
  geometría, pero el checkpoint de la caché guarda los fasteners: un dato que cambia lo que el
  executor deja en `RegenState` también sube la `version`.
  [V6.5b](../../../docs/plans/V6.5b-mcp-accion-con-contrato.md) ·
  [union-en-perfil-hueco](../../../docs/plans/union-en-perfil-hueco.md)

## Super-comandos de máquina

- `create_drive_roller` es de eje FIJO: un tambor MOTRIZ real necesita eje vivo + chumaceras.
- `create_take_up(eje_fit=…)` anota el asiento en el nombre («Ø35 g6»): eje fijo → g6/h6, nunca
  k6 (lo verifica [library](../library/CLAUDE.md)). [V7.2b](../../../docs/plans/V7.2b-barrida-residuos.md)
- `create_take_up(coronado_mm)`: coronado trapezoidal del rodillo (centro recto ½ de la cara,
  conos en ¼ por punta, baja en el RADIO); 0 = el cilindro de siempre, por eso sigue en v1.
- `create_chain` es RELACIONAL: lee las anclas VIVAS de dos piñones ya colocados (orden del log:
  un piñón movido DESPUÉS, o por `add_mate`, no la arrastra; la regla lo avisa), asienta cada
  rodillo en un diente y comparte `mesh_key` entre lazos iguales (`kernel/shapes.place_matrix`
  coloca sin copiar el BRep). Executors nuevos van en `exec_*.py`: `registry.py` no crece.
  [plan](../../../docs/plans/cadenas-pinones.md)
- `create_chain(fase="auto")` (v2) es la ÚNICA vez que la cadena muta otra pieza: gira sobre su
  eje el piñón que aún no carga otra cadena (lo sabe por los `fasten` contacto de las cadenas
  previas), nunca uno cargado, porque desarmaría su otro lazo. `eslabones` fijo tolera
  +0.05 mm sobre el exacto; `=centros_cadena(p, za, zb, L)` lo calcula para colocar los piñones
  antes. Default = v1. [plan](../../../docs/plans/plantilla-rodillos-cadena.md)
- `create_hoist_chain` (`exec_izaje.py`) es la cadena ABIERTA de izaje: valida todo (rayo de la
  varilla, hueco del ancla) ANTES de mutar —una carga tolerante no deshace media cadena—, taladra
  la pieza de amarre y cuelga anclas y tuercas con `fija`; la FK la reconoce por su `mesh_key`
  «izaje|…» y sus anclas por `{id}_pasador_a|b` (renombrarlos la deja rígida). Geometría en
  `library/izaje*.py`: la huella D11 no la ve. [plan](../../../docs/plans/cadena-de-izaje.md)
- `create_roller_conveyor` es COMPUESTO (`composite=True`): corre executors del registro con
  ids `{cmd}_{sufijo}` (command_id sintético, como `insert_project`: la puerta revisa
  interferencias ENTRE sus piezas). Cotas en `library/rodillos_cadena*.py` (motriz, guardas,
  pies, reglas de `engineering_check`), receta en `receta_rodillos_*.py`: la huella D11 no las
  ve, así que cambiar su geometría con los mismos params es subir su `version` a mano (v2 = F4,
  v3 = F5). F6 entra por el campo OCULTO `taller` que el sello pone a todo comando nuevo (como
  `cierres`), sin bump: tocar la rama `taller=False` cambia los logs v3 guardados. F7, por el
  oculto `eje` («hexagonal», sellado con `taller`; un log F6 lee «roscado»): las ranuras se cortan
  con `add_joinery` «rebaje» (en sitio: conserva el id del larguero) y el eje sale de un
  `boolean_op` con el sufijo `eje` (`receta_rodillos_eje.py`). F8, por el oculto `pie` («base»,
  sellado con `taller`; un log F7 lee «disco»): pie de base de anclaje atornillado al concreto, sin
  placa de piso ni soldadura (nada zincado se suelda). Una
  regla que busque un tipo en el log recorre `comandos_efectivos` (lo hace la de cadenas).
  `create_extrude_poly` extruye hacia la normal del polígono: la receta lo pasa ANTIHORARIO
  (`receta_rodillos_guardas._antihorario`), si no la chapa sale corrida un espesor.
  [plan](../../../docs/plans/plantilla-rodillos-cadena.md)
- `create_belt_conveyor` (v6, `exec_faja.py`) también es COMPUESTO: sus piezas llevan el
  command_id del comando (la puerta de publicación las cruza, D13b) y corre `fasten`/`ground`
  del plan con ids `{cmd}_u_…`/`{cmd}_g_…`. Cotas y plan en `library/belt_conveyor*.py`: la
  huella D11 no los ve (cambiar su geometría = subir su `version` a mano). Un `tensor`
  trotadora de un log v3 se monta como la UCT del mismo eje. Campo OCULTO `cierres` (v5: guardas
  inferiores, placas de cierre, techo de cola hasta la cama): el sello lo pone en True al comando
  que nace; un log v4 no lo trae y regenera idéntico (`tests/test_belt_conveyor_v5.py`): tocar
  la rama `cierres=False` cambia los logs v4 guardados.
  [puerta-de-publicacion](../../../docs/plans/puerta-de-publicacion.md). v6: `tramo_max` VISIBLE
  (el sello pone 6000) parte el bastidor en tramos empernados y el oculto `criterio` 6 suma
  rodillos de retorno y pernos pasantes con buje; sin ellos (log v5), una pieza y la v5 idéntica
  (`tests/test_belt_conveyor_v6.py`). F1b: `lado_abierto` VISIBLE (cubre-ranura + pared sólo en la
  cabeza, medido con las sondas) y el sello en criterio 7 (pie con tuerca soldada y contratuerca,
  base del motor a tope con su cuenta en `Plan.calculos`); tocar la rama 6 cambia fajas ya
  selladas (`tests/test_belt_conveyor_f1b.py`). F1c: el sello en criterio 8 (lo de taller,
  `library/belt_conveyor_*taller.py`): cada unión `perno` con sus agujeros, ninguna tuerca dentro
  de un tubo (rosca en placa, pasante con buje o espárrago soldado), paños ≤ 3 m y el largo en la
  nota; sus posiciones de perno son UNA cuenta para la pieza y el larguero
  (`tests/test_belt_conveyor_f1c.py`). [faja-larga-en-tramos](../../../docs/plans/faja-larga-en-tramos.md)
- `layout_tablero` (`tablero.py`, V8.5 D1) es de ESCENA, lee el carril (`lee_carril`) y es
  COMPUESTO (corre `fasten`/`add_joint`); su spec va en `SPECS_ELECTRICO`, junto al carril que
  lee, no en `registry.py`. Las cajas salen de `library/electrico/armado.py` y la geometría de
  `tablero_geom.py`: la huella D11 no las ve (cambiar su geometría = subir su `version`). La
  puerta es junta giratoria + una `fija` por mando (la FK no arrastra); D5 se verifica en el
  executor (cajas cada 1° + vecinos con OCCT) y un choque es `CommandError` con la cifra.
  [V8.5](../../../docs/plans/V8.5-tablero-3d.md)
- `create_pneumatic_cylinder` (`cilindro.py`, V8.9 D5; `create_cylinder` ya es la primitiva) es
  COMPUESTO (corre `add_joint`/`fasten`) y va en `SPECS_CILINDRO`. Marco local y piezas en
  `cilindro_geom.py` + `library/builders_neumatica.py` (la huella D11 no los ve: cambiar su
  geometría = subir su `version`; si cambia la forma de una ref, también `GEOM_CACHE_EPOCH`). Ejes
  por `eje`/`puertos` del mundo (la FK sólo mueve ejes alineados), nunca Euler. El vástago
  `{cmd}_vastago` viene con la ref: BOM y lista de corte lo saltan (`library/incluidas.py`, por
  los sufijos `_cuerpo`/`_vastago`: renombrarlos lo cobra y lo manda a fabricar).
  [V8.9](../../../docs/plans/V8.9-neumatica.md)
- Bastidores con ingletes (`create_weldment`/`create_frame`): [library](../library/CLAUDE.md).
  `insert_project`: [doc](../doc/CLAUDE.md).

## Expresiones (`expressions.py`)

- `=expr` acepta ternario `a if c else b` (PEREZOSO: la rama no tomada no se evalúa),
  comparadores encadenados y `and`/`or` (colapsan a 1.0/0.0); sin strings, listas, `in`, `is` ni
  lambda. [V6.4](../../../docs/plans/V6.4-parametrico-profundo.md)
- `sin/cos/tan` toman GRADOS desde siempre: no se cambia (rompe logs). `avisos_expresion` avisa el
  argumento con `…pi/180` (`resolve_expression` → `aviso`, `POST /api/variables` →
  `avisos_expresion`); un aviso nuevo de «se evalúa pero dice otra cosa» va ahí.
  [trabas-de-modelado](../../../docs/plans/trabas-de-modelado.md) (D1)
