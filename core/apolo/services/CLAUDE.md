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
  es un error de dominio (`ValueError`, `CommandError` o `ServiceError(status_code, detail)` de
  `errors.py`, con el texto EXACTO que verá el cliente) que traduce la API. Sin locks: el
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
  explica el error), también los de command_id sintético `{k}_…` (`insert_project`,
  `create_roller_conveyor`). Multi-sólido expande en `ids`; en un campo singular → error accionable,
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
- La tornillería que insertó un `join_bolted` con su fijador declarado no es «sin unión
  declarada» (`declarada_por_join_bolted`, por el TIPO del comando, no por `jb_*`).
  [union-en-perfil-hueco](../../../docs/plans/union-en-perfil-hueco.md) (D5)

## Puerta de publicación (`calidad_pernos.py`, `calidad_tensores.py`, `calidad_mecanica.py`)

- Miden los INSUMOS de los controles puros de `library/calidad/` (formato en sus docstrings): lo
  que cruza el eje de cada perno (rayos OCCT, por SÓLIDO, eje y cabeza de la geometría) y los
  lazos con sus tensores RECONOCIDOS (take-up, catálogo con `carrera_mm`, plantilla, metadato
  `tensores`), nunca por nombre de pieza. Lo no medible sale SIN_EVALUAR, jamás OK. Todo lazo de
  `create_chain` lleva su medida de centros (D3b es de la cadena, no de la plantilla: F6). Los
  bordes de los agujeros (`calidad_bordes.py`) se miden sobre los insumos de agarre con la MISMA
  `_Escena` (sus `Rayos` se cargan una vez).
  [puerta-de-publicacion](../../../docs/plans/puerta-de-publicacion.md) (F2)
- `puerta_publicacion.reunir` arma TODOS los insumos del registro bajo el lock del llamador (la
  gravedad y la marcha las corre la API fuera, con los suyos); `puerta_hechos.py` son los
  DETECTORES de elementos por tipo general (D14: una familia de máquinas nueva suma su clase ahí)
  con el MISMO criterio que su control: partes móviles, resguardos y consumibles leen
  `calidad_seguridad.analisis`, que el `Contexto` de la corrida calcula UNA vez para detectores y
  fuente; `firma_modelo` es la firma única que comparte con la fábrica de publicaciones (fuera del
  núcleo: la lee del `.apolo`). Las reglas de la
  memoria salen de `memoria_reglas.py` (también el PDF). (F1)
- **¿Sobra una pieza?** (`calidad_sobrantes.py`, `diseno.sin_sobrantes`): candidatas = guardas +
  piezas posteriores a la PRIMERA corrida de la puerta (`doc.puerta_primera`, la anota el endpoint);
  prueba voraz sobre una copia SUPERFICIAL (`doc_sin`: sin regenerar, las formas compartidas) con
  los controles que pueden empeorar, de lo barato a lo caro, reutilizando el `analisis` y las
  sondas de la corrida (`contexto`: `f3.sondas`) y el campo de la muñeca rehecho sólo en la zona
  quitada (`CampoAlcance.libre_sin`, idéntico al entero: lo prueba su test). Un apoyo redundante NO
  sobra. Un control nuevo que una pieza pueda empeorar entra ahí. Lo eléctrico (`del_carril`: el
  `layout_tablero`, los dispositivos) no es «agregado»; un objetivo de enganche que las sondas
  sacaron por caer en una holgura ≤ 4 mm (`calidad_sondas.fuera_de_holguras`) se re-sondea si se
  quita una de sus dos paredes. El campo del codo y el teselado salen de F3 (`compartido` en
  `f3.sondas`), y `reunir` abre `mass.memo_de_geometria`: nada de eso se rehace por candidata.
  [plan](../../../docs/plans/puerta-sin-sobrediseno.md) (D5, D7, D9, F3c)
- Un detector de `puerta_hechos` usa el criterio de SU control: `vigas` = lo que
  `vigas_rules.detectar_vigas` calcula como viga (un riel o las patas de un tanque no son vigas:
  NO_APLICA, no SIN_EVALUAR). (F3c)
- **Un ítem general nuevo = su defecto sembrado** en `tests/test_defectos_sembrados.py` (una
  mutación mínima de un testigo bueno que lo pone en FALLA) o una exención con su porqué; si no, la
  suite se pone roja. Los testigos (`tests/data/testigos/`, públicos y sintéticos: D16) congelan el
  veredicto por ítem: un cambio que lo mueve se re-congela A PROPÓSITO con
  `scripts/testigos.py --en-proceso --congelar`. (F5)

## Escenarios de prueba (`escenarios.py`, `cosim_snapshot.py`)

- La vigencia de un resultado es `firma_documento` (log sin lo que sólo organiza, `SIN_FISICA`:
  `create_group` salvo con `transform_group` + materiales + las fichas del tablero armado: el
  carril, los programas y el YAML eléctrico cuentan, el color no; versión «2:», la 1 se lee con
  `firmas_v1`: [V8.5](../../../docs/plans/V8.5-tablero-3d.md) F5b) +
  `hash_escenario` + `COSIM_EPOCH` (regla en [cosim](../cosim/CLAUDE.md); sin el dato = versión 1);
  vencido = AMARILLO en la puerta, nunca rojo ni verde. El snapshot toma los programas del carril y `programas=` los pisa por PLC (`test_plc`).
  [V8.3](../../../docs/plans/V8.3-prueba-virtual.md) (D12, D14)
- `resultado_compacto` guarda `electrico` (ΔU de cada motor y disparos, `medidas_electricas.py`)
  sólo con motores o un disparo; sus referencias (`referencias(doc)`: U de la red, In, tras
  variador) las arma la API en la toma del snapshot, nunca el worker. Un resultado sin
  `electrico` sigue vigente: quien lo lee usa `cifras` (aviso «córrelo de nuevo»).
  [pedidos-de-extensiones](../../../docs/plans/pedidos-de-extensiones.md) (F4)
- Los `ajustes` de PRUEBA de un escenario (`escenario_ajustes.py`) se validan como en `add_device`
  y se aplican en una COPIA del modelo del tablero dentro del snapshot: nunca a `doc.electrico`
  (lo que leen manual y memoria) ni a `firma_documento`; entran sólo al hash de SU escenario y el
  resultado los lista (`ajustes_de_prueba`). Un lector de resultados que publica cifras «del
  proyecto» trata ese escenario como uno de falla (`neumatica._sano`).
  [plan](../../../docs/plans/cotizacion-identificada-y-ajustes-por-escenario.md) (D5–D7)
- El balance de producto (`flujo_producto.py`) es UNA regla para las dos puertas: `evaluar`
  (publicación, `funcion.flujo_de_producto`) y `regla_entrega` (entrega, sólo con escenarios).
  El ritmo nominal es `requirements.paquetes_por_minuto`; «nominal» se GUARDA como número al
  declarar (`poner`) y nunca se lee del requisito al correr: subir la capacidad deja el escenario
  por debajo, no lo cambia. [balance-de-producto](../../../docs/plans/balance-de-producto.md)
- Una sesión en vivo vuelta escenario (`sesion_viva.py`) tiene que dar por lote la huella de la
  sesión: la cola de productos queda con las instancias que tuvo la SESIÓN (`fijar_cola`: su pool
  sale de la duración de la BASE), más que el tope de un escenario (`cosim.escenario.DURACION_MAX_S`)
  se guarda por tramo inicial (`hasta_s`), y otra
  firma o una base borrada o cambiada se rechazan. Las aserciones se SUGIEREN (sólo las que pasan
  sobre esa corrida, `cosim/sugeridas.py`), nunca se guardan solas.
  [V8.4](../../../docs/plans/V8.4-maquina-viva-en-pantalla.md) (F4)
- Una extensión corre un escenario por `corrida_escenario.py` (en `extensiones_api.SUPERFICIE`):
  `preparar_corrida` bajo el lock del llamador, `correr_corrida` fuera; sus errores llevan el
  texto del núcleo. Un paso nuevo de la corrida de la API que también deba ver la extensión va en
  los dos. [pedidos-iii](../../../docs/plans/pedidos-de-extensiones-iii.md) (D1)

## Cobros dudosos (`cobros.py`)

- Lo que dibujó un `layout_tablero` (`tablero.dibujados`: cuerpo `{cmd}_d_<designación>`) cuenta
  en la ESCENA con su ref, como una `pieza`: la BOM del carril y «pieza sin ligar» lo saltan. Un
  consumidor nuevo del carril que cobre o cuente dispositivos usa esa misma función.
  [V8.5](../../../docs/plans/V8.5-tablero-3d.md) La pieza 3D de un aparato (la explícita gana; si
  no, la dibujada) es `tablero.piezas_3d`, para el panel y la tabla del `inicio` del vivo: la API
  la suma al armarlo (`piezas_en_tabla`), así que ni el worker ni la firma la ven.
  [pedidos-de-extensiones](../../../docs/plans/pedidos-de-extensiones.md) (D15)
- El ruteo del tablero NO se cachea (D12): `tablero.ruteos(doc)` recalcula `plan` del executor
  con las variables y la `lectura` del carril y rutea; largos (BOM, `circuito`) y reglas del ERC
  (`tablero_reglas.py`) salen de ahí, nunca de otra cuenta. La puerta (y la placa con
  `specs.placa_montaje`) viene con el gabinete: `tablero.incluidas` → `bom_from_scene(incluidas=)`
  y `scene_costing(incluidas=)`; un consumidor nuevo de la BOM de compra la pasa. (F2)
- Lo que VE la persona del tablero (panel «Tablero», `GET /api/tablero/{ubicacion}`) y lo que lee
  el agente (`get_circuit tablero=true`, que la tool resume eligiendo claves; entera con
  `completo=true`) es UNA función, `tablero_panel.panel`: los hallazgos salen
  de los selectores de `tablero_reglas.py` (los del ERC) y el veredicto, con la regla de
  `ui/src/diseno/atencion.ts::veredictoDe` (cambiar una es cambiar las dos). Sus textos son para
  la persona (sin comandos ni parámetros): el crudo va en `tecnico`. (F3b) El calentamiento
  (`tablero_calor.evaluacion`) y los prensaestopas (`tablero_prensas.del_tablero`) son la ÚNICA
  cuenta del panel, el ERC y la BOM; sus ítems los redacta `tablero_atencion.py`. (F3)
- El nombre de un aparato para la persona (paneles, tabla del vivo con `nombres_en_tabla`, junto a
  `piezas_en_tabla`) sale de `nombres_aparatos.Nombres`: rótulo con su `origen`, estados, grupo y
  rearme. Ni una tabla de tipos propia ni la designación sola.
  [nombres-por-funcion](../../../docs/plans/nombres-por-funcion.md)
- Los cables de campo (`cables_campo.py`, F4) tampoco se cachean: `recorridos(doc, m, tableros)`
  es la ÚNICA cuenta de su recorrido y su largo (BOM, `circuito`, ERC y `vista`, lo que dibuja el
  visor); sólo con `por`. Lo que gira sale de `calidad_seguridad.analisis` (sin el layout): no
  otro criterio. (F4) El panel los cuenta en `tablero_cables.py` sobre las filas de `vista` (con los
  `ruteos` que ya tiene); el texto crudo de `tecnico` sale de las funciones del ERC
  (`detalle_choque`, `detalle_incompleto`), no de otra redacción. (F4b)
- Un largo que la BOM calcula (ruteo, recorrido `por`) es también el de la co-simulación
  (`cosim_red.largos_calculados`): el declarado manda, nunca otra cuenta. El ERC que mira la
  escena (pieza de seguridad sin circuito, altura de los mandos) está en `erc_escena.py`; una
  regla del ERC que sólo da filas con hallazgo entra en `electrico.REVISA` para salir en
  `revisadas` cuando pasa. (F5b) «Aparato de campo sin pieza» (`electrico.campo_sin_pieza`,
  V8.9 F7b) avisa lo de montaje `campo` (y lo de aire que no es tubo) sin pieza 3D, SÓLO si la
  escena tiene piezas: un tablero solo, sin máquina en 3D, no es un modelo a medias.

- El circuito de AIRE (V8.9) sale en la MISMA salida que lo eléctrico: `neumatica.py` arma la
  sección `neumatica` de `circuito`, los `puertos` de cada aparato de aire y suma el ERC
  neumático (filas `medio: "aire"`) AL FINAL de `_erc_completo`; sin aire no suma nada (la
  salida de siempre, que congela `tests/data/carril_v81_golden.json`). La memoria del aire
  (`neumatica.memoria`) lee de `neumatica.lecturas` el tiempo de carrera del escenario NOMINAL
  (carrera completa, sin falla) y la velocidad del PICO de todos, si pasa la declarada (que es la
  de RÉGIMEN): una seta que corta la carrera no es el tiempo del cilindro (F7b). Sólo vigentes.
  Lo que VE la persona (panel «Neumática», `GET /api/neumatica`) es `neumatica_panel.panel` sobre
  ese MISMO ERC y esa memoria (las cifras de cada fila de la memoria van en `valor`: el panel no
  rehace cuentas); el esquema, la lámina de F5 en primitivas (`neumatica_vista.py`).
  [V8.9](../../../docs/plans/V8.9-neumatica.md)
- Lo dudoso se dice DONDE se cobra: `costeo(doc)` es la fuente única de `/api/costing.json` y de
  la cotización (PDF y cabecera `X-Apolo-Avisos` que lee la tool `quotation`). Suma `avisos` y
  `monto_en_riesgo_usd` sólo si hay (sin ellos, el dict de siempre). La lectura acotada
  (`?resumen`, `?categoria`) es `costeo_corto.acotar` sobre ese dict y el precio que devuelve la
  tool (`X-Apolo-Precio`), `drawing/quote.resumen_precio`, la cuenta de la hoja. Avisos: dispositivo sin ligar a su
  pieza 3D (monto = mín(dispositivos, piezas) × precio de la ref) y cable 3D que ningún add_cable
  cubre (lo liga con `piezas` o tiene los mismos hilos × sección en el nombre). Nunca descuenta:
  ligar es del modelo. El ERC suma el mismo «cable 3D sin cobrar» (`regla_cables`).
  [V8.1](../../../docs/plans/V8.1-modelo-electrico.md) (F4c)
- Las filas de `Extension.costeo` (`filas_de_extensiones`) entran AL FINAL ya costeadas (`origen`
  «extension:x», a `extensiones_usd`, ni compradas ni fabricadas); una fila sin la forma o una
  fuente que lanza no se cobra y lo dice un aviso de cobro. Sin ellas, byte-idéntico.
  [plan](../../../docs/plans/puntos-de-extension-entregables.md)

## Reglas de ingeniería y FEA (`engineering_rules.py`, `fea_rules.py`)

- `/api/checks` y la memoria comparten SÓLO lo idéntico (`requirement_inputs`,
  `inherit_inclination`, `structure_rules` = estructura universal + FEA). Sus diferencias son
  deliberadas y quedan en `/api/checks` y en `memoria_reglas.py` (la memoria): velocidad con `or` (checks) vs `is not None` (memoria),
  lints sólo en checks, stack-up y «alcance de la memoria» sólo en la memoria. No las unifiques.
- `vigas_rules.beam_rules` (flecha de viga, dentro de `structure_rules`): viga = perfil de
  catálogo cortable HORIZONTAL con ≥ 2 uniones perno/soldadura a vecinos de MENOR nivel (BFS
  desde los `ground`; una sola soldadura = empotramiento). Las cargas bajan por niveles,
  repartidas por igual; una viga baja sus reacciones. Carga útil = puntual MÓVIL sobre las vigas
  que tocan `BED_RE` o, sin cama, las más altas. Piezas de `create_conveyor` → `no_aplica` (D4).
  Sin vigas → `[]` (memoria intacta). [flecha-de-bastidor](../../../docs/plans/flecha-de-bastidor.md)
- `conveyor_params_from_doc` es de los tres clientes (checks, memoria, tool `engineering_check`
  del agente, que la importa con su nombre viejo). Con un `create_roller_conveyor` (el último
  transportador del log) devuelve sus params con `plantilla` y `conveyor_engineering_check` los
  valida con `library/rodillos_cadena_reglas.py` contra la ficha: los endpoints no cambian.
  [plan](../../../docs/plans/plantilla-rodillos-cadena.md) (D9)
- `fea_rules`: VIGENCIA por volumen (>0.1 % de cambio, o pieza borrada → aviso «re-ejecuta»); el
  de ensamblaje por volumen CONJUNTO de `piezas_fids`. Tabla por pieza con tope 8 filas, 5 si
  hay historial de convergencia (el calc_report imprime ≤ 12); `hipotesis` va a la memoria.

## Preparación del FEA (`fea_setup.py`)

- Es la fase (a) del patrón dos-locks, nada más: validar, resolver material y selectores, derivar
  condiciones de borde y exportar los STEP del ensamblaje al `tmp_dir` que le pasa la API. El
  tmp dir, el solve fuera del lock, la guardia de proyecto y el campo en memoria son de
  [api](../api/CLAUDE.md) (D8 del [plan](../../../docs/plans/partir-api-main.md)).
- Honestidad: material sin σy tabulado exige `yield_mpa` (en el ensamblaje, de respaldo); una
  superficie o un boceto-guía se rechazan.
- Ensamblaje BONDED: el herraje (`FEA_HARDWARE_CATS`) sale de la malla y su peso entra como carga
  sustituta SÓLO en la rama automática (la carga de los requisitos sobre la cama, `BED_RE`); con
  `loads` explícitos no (`substitute_applied`). Empotramiento = base de las piezas con ground ∩
  grupo, o `fixed_pieces`; sin ninguno → 400, nunca un empotramiento inventado. ν 0.33 aluminio,
  0.30 el resto. [V7.4](../../../docs/plans/V7.4-fea-firmable.md)
- `merge_convergence` corre como `before_save` (bajo el lock de la persistencia): re-correr el
  MISMO grupo con otro `mesh_size` pasa el run previo al historial (tope 3) y el vigente
  reemplaza la entrada de su misma malla.

## Cirugía (`cirugia.py`)

- `dependientes` (D2): arrastra SÓLO `fasten`/`ground` que nombran una pieza de los comandos
  borrados (también por prefijo `{cmd}_`) y quita esos comandos de los `members` de sus grupos;
  juntas y mates nunca (el error estricto los nombra). Un grupo que quedaría vacío no se toca:
  aviso. `foto` + `diff_borrado` arman la respuesta liviana.
  [cirugia-liviana](../../../docs/plans/cirugia-liviana.md)
- `como_seguir` arma el 400 de un borrado con referencias rotas (tras el rollback): lo que
  `con_dependientes=true` arrastraría y los comandos que no (juntas, mates, patrones y
  operaciones que nombran lo borrado, `fasten` por conjuntos), con sus ids y recortado. Un id inexistente deja el error tal cual. Lo que CREA un comando borrado (command_id `{cmd}_…`: los `fasten` internos de una plantilla) no es dependiente. [mcp-sin-friccion](../../../docs/plans/mcp-sin-friccion.md) (D4, D11)

## Respuestas cortas para el agente (`paso.py`, `conexiones.py`, `reglas_cortas.py`)

- Modo corto (D1/D2 de [mcp-sin-friccion](../../../docs/plans/mcp-sin-friccion.md)): conteos +
  sólo lo que CAMBIÓ o FALLÓ; el detalle, a pedido. Una lista larga se recorta con
  `paso.recortar` (`MAX_LISTA`) y declara `<clave>_omitidas`: nunca un recorte silencioso.
- «Repetido» = mismo nombre con los números cambiados por `*` (`reglas_cortas.patron`): agrupa
  reglas (una línea, `n`, el PEOR caso en `peor`). Una UNIÓN se agrupa por el PAR de patrones de
  sus piezas (`conexiones.patron_de`: sin los tramos de la máquina ni paréntesis), no por su
  nombre (`auto_f_*` mezclaba 163 contactos): el `resumen` de `get_connections` y, con
  `clave_de_reglas`, las reglas de cada unión (D9, D12). En corto lo «ok» va sin detalle salvo
  con `grupo`. `filtrar` encuentra una unión también por el COMANDO que la declaró (el token o
  el command_id de una pieza pedida: el `jb_<cmd>` por su join_bolted o su tornillería).
  [trabas-de-modelado](../../../docs/plans/trabas-de-modelado.md) (D2)
- Un recorte o un error dice cómo seguir (D4): la interferencia truncada suma `como_acotar`
  (`interferencias.py`: la llamada de la página siguiente, `desde`, y zonas que NO son lo ya
  pedido: D10), un `fasten` por conjuntos se cuenta en `conexiones.expandidas` y la puerta anota
  segundos por regla (`delivery_inputs(tiempos=)`). `excluir_declaradas` usa las exclusiones de la
  puerta (`delivery_inputs.exclusiones_declaradas`, una sola fuente).

## Estructura propuesta (`estructura.py`)

- `propuesta_estructura` es la fuente ÚNICA de `POST /api/assembly/declare`: lo que propone
  (`aplicar=false`) es exactamente lo que aplica. Pasa `doc.joints` a `detect_structure` (lo que
  gira no se suelda) y deja `a_revisar`/`motivo` FUERA de `params` (un lote las ignora). La raíz
  del `resumen` sigue la regla de `commands/exec_uniones.py` (copia `{cmd}_{n}` de su comando).
  [uniones-en-lote](../../../docs/plans/uniones-en-lote.md)
- El TIPO lo decide `criterio_uniones.criterio` (puro: roles + contactos, sin geometría) por el
  rol de las dos piezas, con las reglas EN ORDEN de su docstring; la geometría (`direction`) sólo
  decide lo que ninguna regla toca. Una regla nueva va ahí con su caso en
  `tests/test_criterio_uniones.py`, y el fixture de la piloto (`tests/data/estructura_piloto74.json`,
  `scripts/fixture_estructura.py`) debe seguir ≥ 95 % y sin soldaduras desmontables. `kind` None
  = no se declara (`omitidas`), salvo que deje suelta una pieza que la geometría sujetaba: vuelve a
  revisar. [mcp-sin-friccion](../../../docs/plans/mcp-sin-friccion.md) (D6)
- No repite lo declarado: omite todo par que las uniones declaradas YA unen, directo o en cadena
  (`unidas_por_lo_declarado`; los anclajes no unen). Sobre una plantilla recién generada propone 0
  (D7).
- Cada `fasten` propuesto lleva su dimensión (`dimensionado.py`, tabla en
  `library/engineering/union_por_defecto.py`): nada queda «sin dimensionar» (D8). Aplicada, el endpoint
  ejecuta `lote_compacto` (un `fasten` por conjunto verificado, con la menor dimensión de la fila;
  las uniones a revisar, sueltas): las MISMAS uniones que la propuesta.
- Corto (`estructura_corta.py`, `resumen=true` del endpoint): filas por patrón de nombre (sin
  paréntesis) con su dimensión y los `fasten` por conjuntos VERIFICADOS expandiéndolos con
  `pares_de_union` (nunca uno que no dé exactamente los pares de la fila); ids sólo de
  `a_revisar`. Aplicada, conteos (`aplicada_corta`, con `ordenes`), nunca la lista de conexiones.

## Video y vista 3D web (`construccion.py`, `rotulos.py`, `datos_rotulos.py`, `guion_video.py`, `cifras_grupo.py`)

- Un rótulo sólo dice cifras leídas del documento, del catálogo o de un cálculo ya hecho
  (`datos_rotulos`), nunca escritas a mano; una plantilla nueva va en `rotulos.PLANTILLAS` con
  su test cifra por cifra. Las etiquetas de la vista 3D (`cifras_grupo`) usan las MISMAS
  plantillas: no se escribe otra fórmula. [vista-3d-web](../../../docs/plans/vista-3d-web.md) El peso de un paso (`peso_roles`) lo usan las etapas Y
  el video de la fábrica (fuera del núcleo): no se duplica la fórmula.
  [video-montaje-pulido](../../../docs/plans/video-montaje-pulido.md)

## Secuencia de montaje (`montaje.py`, `montaje_video.py`)

- UNA secuencia para el manual (`pasos_manual` → `assembly_manual(stages=)`) y el video
  (`etapas_montaje` → guion con `"modo": "montaje"`, cada paso = tanda de ids); sale SÓLO de lo
  declarado (`fasten`/`ground`). Sin estructura (`hay_grafo` falso), el manual sigue con
  `order_by_support`. Las reglas (soldado primero, nivel desde el piso, la tuerca cierra, lo que
  tapa al final, se termina lo empezado) están en el docstring: una regla nueva va ahí con su
  caso en `tests/test_montaje.py`. El acceso de herramienta NO impone orden (si la llave entra
  con la máquina terminada, entra con menos piezas).
  [video-montaje-pulido](../../../docs/plans/video-montaje-pulido.md) (F1b). El título del paso va
  ENTERO (el manual lo mide; el video titula la etapa a `MAX_TITULO_GENERADO`): un tope aquí
  igualaba pasos distintos. [V8.9](../../../docs/plans/V8.9-neumatica.md) (últimos cortes)
- La `marcha` del guion (opcional) cuenta en `duracion_total` y en los capítulos, pero sólo la
  graba el navegador: todo render que no la anime usa `sin_marcha(g)`.
- La marcha de EJEMPLO de un transportador (`marcha_ejemplo.py`, la que arma la fábrica) sale de
  la detección de la dinámica (`detectar_bandas`, `superficie_banda`), nunca de otra; `probar` la
  simula y exige que una caja avance (detalle fuera del núcleo).
  Lleva `sumideros` (fin del tramo superior y bajo la banda) y la cola nace donde la caja no toca
  pieza (`_choca`): con placa de transferencia o el techo de la guarda de cola, las cajas se
  encimaban. [puerta-de-publicacion](../../../docs/plans/puerta-de-publicacion.md) (F6)
- `linea_tiempo.py` (tiempos y efectos del video) y `plan_navegador.py` (el plan cuadro por
  cuadro que el visor sólo dibuja) viven aquí y no en la fábrica de publicaciones (fuera del
  núcleo; las usa como API) y la API arma el plan del botón «Grabar video». Una
  regla nueva del video va en `linea_tiempo.py` y la reciben VTK y el navegador.
  [video-realista](../../../docs/plans/video-realista.md) (D5)

## La marcha en el visor (`marcha_visual.py`)

- `extraer_marcha_visual` corre bajo el `STATE_LOCK` del llamador, en la misma adquisición que
  `prepare_dynamics`. Una cadena se reconoce por su `mesh_key` (`Transmision.clave` de
  `create_chain`: cambiar su formato la deja rígida; `tests/test_marcha_visual.py` lo detecta) y sus
  piñones por las uniones `{cadena}_a|_b`. De la faja mide encuadres en SU marco (diestro: v = u×w)
  y la redondez (encuadre cuadrado que no crece girado 45°: un tubo cuadrado no es tambor).
  [visor-realista](../../../docs/plans/visor-realista.md) (F3)
- Además corta con OCCT (`seccion_plano.py`) la banda y lo que podría cruzar su cinta en planos a
  lo ancho: la forma de la cinta y su prueba salen de esas secciones, y `marcha_ejemplo.fidelidad`
  lanza `MarchaInfiel` (quien la usa PARA, nunca «sin marcha»; detalle fuera del núcleo).

## Roles por nombre (`roles.py`)

- `BED_RE` (cama/mesa: recibe la carga del FEA y da la altura de trabajo de la instalación) y
  `SERVICE_RE` (piezas que se extraen: holgura de servicio). Un matcher por nombre nuevo lleva
  guarda de bracket/anclaje y un test con el nombre REAL ([drawing](../drawing/CLAUDE.md)).
- `rol_union` (roles de unión) lee el SUSTANTIVO que encabeza cada tramo « · » (anclado al
  inicio: «Eje del rodillo» es eje, «Separador de guarda» es estructura), del último al primero y
  sin los tramos que nombran un grupo (la máquina de una plantilla); el catálogo de tornillería,
  rodamientos, equipos y lo que gira manda antes que el nombre. Una tapa sin otro rol es guarda
  salvo la de un rodillo o tambor (gira), un tubo o perfil (estructura) o la que aloja un
  rodamiento (`_rol_tapa`, F6): ante la duda, guarda (sólo pide pernos de más); el
  `cuerpo` conserva la numeración si la pieza ES ese tramo («Bandeja (tramo 1)» ≠ «(tramo 2)»:
  perno) y la quita si es una parte («Guarda · extremo (+X)»: soldadura con su pared). (D7)
