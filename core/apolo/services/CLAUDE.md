# Servicios de dominio (`core/apolo/services/`)

La lógica que LEE un `Document` y que comparten sus clientes (planos, instalación, stack-up,
`verify` y `expect`, insumos de las puertas, reglas de ingeniería y FEA). Nació al partir
`api/main.py` ([plan](../../../docs/plans/partir-api-main.md)). Lo transversal, en el
[CLAUDE.md raíz](../../../CLAUDE.md); lo común del backend, en [core/apolo](../CLAUDE.md); el
transporte que los llama, en [api](../api/CLAUDE.md).

## Reglas de la capa

- Capas: kernel/commands/doc/library/drawing/fea/assembly/robotics ← `services` ← `api` y
  `agent`. Cada función recibe `doc` EXPLÍCITO y jamás lee un global de sesión.
- Sin `fastapi`, `apolo.api` ni `apolo.agent`; un 400/404 es un error de dominio (`ValueError`,
  `CommandError` o `ServiceError(status_code, detail)` de `errors.py`, con el texto EXACTO que
  verá el cliente) que traduce la API. Sin locks: el llamador sostiene `STATE_LOCK`. Lo hace
  cumplir `tests/test_capas_services.py` (AST, también los imports perezosos).
- Los imports pesados (gmsh, VTK, matplotlib…) quedan DENTRO de la función
  (`tests/test_api_opcionales.py`).
- Nombres públicos sin `_` (los alias viejos de `main`: [api](../api/CLAUDE.md)). Lo que sólo el
  transporte sabe hacer se INYECTA como keyword, no se importa: `expand` (nombres de grupo → fids;
  en la API, `_expand_ids`, que toma `STATE_LOCK`).

## Mapas por pieza para los planos (`drawing_maps.py`)

- **Fits por pieza**: `feature_fit_maps` da {feature_id → {Ø → clase}} desde el NOMBRE
  («… Ø35 g6») + `drill_hole.fit`, y cada lámina rotula EL SUYO (`sheet_set(piece_fits=)`). El
  conjunto usa `scene_fit_map`, que OMITE un Ø en conflicto (mejor ausente que equivocado);
  `drawing_spec` lo computa sobre la escena EFECTIVA. [V7.2c](../../../docs/plans/V7.2c-fixes-re-auditoria.md)
- **Datum funcional**: `piece_datum_sides` deriva los lados de montaje de los FASTENERS
  declarados (soldadura > perno > contacto; eje = solape mínimo de bboxes); PROHIBIDO inferir por
  nombre. Devuelve LISTA por peso: cada vista usa el primer lado que proyecte como borde.
  [V7.5](../../../docs/plans/V7.5-e22-datum-funcional.md)
- **GD&T**: `piece_datum_frame` = A (cara de mayor peso) + B/C sólo si son ORTOGONALES; el
  `motivo` va a la leyenda. `piece_pos_tols`: t = `bolt_pattern_budget(flotante=)`; el Ø del
  perno sale de la tabla ISO 273 INVERTIDA y el sólido en el eje es respaldo. Sin perno
  identificable NO hay marco: una tolerancia inventada es peor que su ausencia.
- **Tolerancia justificada**: `piece_dim_tols` sale de los eslabones `{id, eje}` de las cadenas
  DECLARADAS, medidos sobre SU `doc`; sólo bandas SIMÉTRICAS (un fit asimétrico viaja en su
  callout); varias cadenas → la más estricta; una inválida no tumba el juego.
- `sheet_set_maps(doc)` arma los kwargs de `sheet_set` que salen del documento, comunes a PDF y
  DWG (cajetín, colores y `shaded` los pone el endpoint). Un mapa nuevo para las láminas va AQUÍ.

## Instalación, stack-up y aserciones

- `installation_data` excluye la tornillería (`lints._is_bolt`) de los apoyos, lee las claves del
  catálogo sin distinguir mayúsculas (`potencia_kW`) y devuelve `({}, {})` sin grounds. Reparto
  en [library](../library/CLAUDE.md); lámina en [drawing](../drawing/CLAUDE.md).
  [V7.6](../../../docs/plans/V7.6-e2-fino.md)
- `evaluate_stackups` aísla cada cadena (una mala = `{error}`, nunca tumba GET ni la memoria);
  pieza FALTANTE = error sin veredicto, jamás parcial; «cerrada por construcción» sólo si el
  fasten lo creó un `join_bolted` (no por nombre `jb_*`); un perno manual = holgura informativa,
  sin veredicto.
  [V7.3](../../../docs/plans/V7.3-stackup-cadenas-cotas.md)
- `verify_checks(doc, scene, …)` (`assertions.py`) es la fuente ÚNICA de `/api/verify` y del
  contrato `expect` (`contract_verify` → callback de `execute_many`/`edit_many`; rollback en
  [api](../api/CLAUDE.md)). [V6.5b](../../../docs/plans/V6.5b-mcp-accion-con-contrato.md)
- `$k` resuelve a los FEATURE_IDS del comando k, 1-INDEXADO (`$0` lo explica el error), también
  los de command_id sintético `{k}_…`. `$k_<sufijo>` = `{cmd k}_<sufijo>` (`apolo/batch.py`, en
  params y aserciones): el hijo de un compuesto (`$5_gabinete` de un `layout_tablero`).
  Multi-sólido expande en `ids`; en un campo singular → error accionable, nunca elige uno. Clave
  desconocida → «no reconocida» con las válidas; «sin piezas» nombra los tokens que no
  resolvieron. [V6.5c](../../../docs/plans/V6.5c-fixes-revision.md)
- «¿Quisiste decir…?» (`lookup.suggest_ids`: fids + command_ids + grupos + nombre) en los 404 por
  id y en los selectores de verify/expect; un command_id multi-sólido sugerido → sus fids hijos.
- `distancia`/`sin_interferencia` aceptan `joint_values` POR ASERCIÓN con el mecanismo POSADO
  (`pose_fn` inyectado en `library/verify.run_verify`, que sigue pura); `pose_fn` valida los
  nombres de junta ANTES de posar (la FK ignora desconocidos). En pose la interferencia suma
  `interpenetration_report`; caché por pose; todo-cero = pose de diseño.
  [V6.8](../../../docs/plans/V6.8-mcp-fluidez.md)
- `extra_exclude_pairs/ids` son las exclusiones de la puerta de entrega; `None` deja los
  contratos intactos.

## Puerta de entrega (`delivery_inputs.py`, `assertions.delivery_poses`)

- `delivery_inputs(doc)` arma los kwargs de `library.delivery.delivery_report` salvo la gravedad
  (la simula la API con su lock). Excluye lo DECLARADO con las MISMAS exclusiones en diseño y en
  las poses de REPOSO (`delivery_poses`: extremos + dwells; porqué en [library](../library/CLAUDE.md)),
  salvo el `fasten` entre piezas que la pose mueve con juntas distintas (`uniones_entre_juntas`,
  sin los de un super-comando de cadena). [V6.9](../../../docs/plans/V6.9-puerta-de-entrega.md) ·
  [lo-que-se-mueve](../../../docs/plans/lo-que-se-mueve.md) (D2)
- La junta que abre un resguardo con interruptor es UNA función, `resguardos.resguardos` (sin
  lengüeta emparejada no hay junta): la leen `seguridad.resguardo_abre`, las poses de la entrega
  (`lower`/`upper` ≠ 0, acotadas a lo que la junta mueve) y el vivo (`juntas_en_tabla`). (D3, D4)
- La tornillería que insertó un `join_bolted` con su fijador no es «sin unión declarada»
  (`declarada_por_join_bolted`, por el TIPO del comando) ni «aislada» en `check_assembly` (el
  endpoint suma `aristas_tornilleria_join_bolted`).
  [union-en-perfil-hueco](../../../docs/plans/union-en-perfil-hueco.md) (D5) ·
  [bom-de-compra-fiel](../../../docs/plans/bom-de-compra-fiel.md) (D6)

## Puerta de publicación (`calidad_*.py`, `puerta_publicacion.py`, `puerta_hechos.py`)

- Miden los INSUMOS de los controles puros de `library/calidad/` (formato en sus docstrings): lo
  que cruza el eje de cada perno (rayos OCCT, por SÓLIDO, eje y cabeza de la geometría) y los lazos con sus tensores
  RECONOCIDOS (take-up, catálogo con `carrera_mm`, plantilla, metadato `tensores`), nunca por
  nombre. Lo no medible sale SIN_EVALUAR, jamás OK. Todo lazo de `create_chain` lleva su medida de
  centros. Un perno DIN 603 se lee por su cara plana de apoyo (`_cabeza_de_coche`). Los bordes
  (`calidad_bordes.py`) se miden con la MISMA `_Escena` del agarre.
  [puerta-de-publicacion](../../../docs/plans/puerta-de-publicacion.md) (F2)
- `puerta_publicacion.reunir` arma TODOS los insumos bajo el lock del llamador (gravedad y marcha,
  la API fuera); `puerta_hechos.py` son los DETECTORES por tipo general (D14: una familia nueva
  suma su clase ahí) con el MISMO criterio que su control (`vigas` = lo que
  `vigas_rules.detectar_vigas` calcula como viga: un riel o las patas de un tanque no son vigas →
  NO_APLICA, no SIN_EVALUAR). Partes móviles,
  resguardos y consumibles leen `calidad_seguridad.analisis`, calculado UNA vez por corrida en el
  `Contexto`; `firma_modelo` es la firma única que comparte con la fábrica de publicaciones
  (fuera del núcleo). Las reglas de la memoria salen de `memoria_reglas.py` (también el PDF).
- La catenaria de una banda modular es tensor reconocido sin mirar el nombre
  (`calidad_catenaria.py`; criterio en `library/catenaria_banda.py`), sólo si no actúa otro.
  [lo-fijo-que-gira](../../../docs/plans/lo-fijo-que-gira-y-lo-que-cuelga.md) (D3a)
- **¿Sobra una pieza?** (`calidad_sobrantes.py`): candidatas = guardas + piezas posteriores a la
  PRIMERA corrida de la puerta (`doc.puerta_primera`); prueba voraz sobre una copia SUPERFICIAL
  (`doc_sin`) con los controles que pueden empeorar, de lo barato a lo caro, reutilizando el
  `analisis`, las sondas y el campo de la corrida (`contexto`: `f3.sondas`, `compartido`) y
  rehaciendo sólo la zona quitada (`CampoAlcance.libre_sin`/`sin_zona`, `BandaEmpujable.sin`).
  Un apoyo redundante NO sobra, pero corre las sondas sin él y sin lo que sostiene
  (`tambien_tapa`/`solo_apoyo` en la evidencia, sin cambiar el estado: `calidad_sobrantes_apoyo.py`,
  [lo-que-se-mueve](../../../docs/plans/lo-que-se-mueve.md) D6). Un control nuevo que una pieza pueda empeorar entra ahí. Lo
  eléctrico (`del_carril`) no es «agregado»; un objetivo de enganche descartado por caer en una
  holgura ≤ 4 mm (`calidad_sondas.fuera_de_holguras`) se re-sondea si se quita una de sus
  paredes. `reunir` abre `mass.memo_de_geometria` y los memos de `engineering/memo_corrida.py`
  (sólo lo puro e inmutable, la forma por `is`). Todo atajo da IGUAL al recalculado y entra con
  su test de igualdad. [plan](../../../docs/plans/puerta-sin-sobrediseno.md) (D5–D9) ·
  [puerta-rapida](../../../docs/plans/puerta-rapida.md)
- `movimiento.coherente` (`calidad_movimiento.py`) juzga los pares rígidos de
  `uniones_entre_juntas(tocan=False)` con la prueba de pose relativa y la firma coaxial; el
  pivote que cierra un lazo declarado (`punto_coincidente` + su `axis`) es un eje más si el lazo
  cierra en cada pose (`calidad_lazos.py`, sin pose relativa: abriría el lazo;
  [plegables](../../../docs/plans/plegables-en-la-puerta.md) D4). Pernos y
  ejes de giro se miden UNA vez por corrida (`pernos_y_ejes`, memo del `contexto`): un control
  nuevo los pide ahí. Lo colgado de un `contacto` (`calidad_cuelga.py`) sale de
  `loads.piezas_colgadas` sobre el grafo DECLARADO; la unión de tubería que tira se declara en la
  nota del `fasten`, nunca por nombre.
  [lo-fijo-que-gira](../../../docs/plans/lo-fijo-que-gira-y-lo-que-cuelga.md) (D1, D2)
- `plegado.traba` (`calidad_trabas.py`) mide desde la pose de USO con los lazos resueltos: el
  tope mueve la junta SIN resolver el lazo (como la prueba de pose); el tirante resuelve por
  continuación y corta en el primer paso que no cierra (sin solución, el solver gasta todas sus
  evaluaciones). [plegables](../../../docs/plans/plegables-en-la-puerta.md) (D5, D6)
- **Un ítem general nuevo = su defecto sembrado** en `tests/test_defectos_sembrados.py` (mutación
  mínima de un testigo bueno que lo pone en FALLA) o una exención con su porqué. Los testigos
  (`tests/data/testigos/`, públicos y sintéticos) congelan el veredicto por ítem: un cambio que
  lo mueve se re-congela A PROPÓSITO con `scripts/testigos.py --en-proceso --congelar`.

## Escenarios de prueba (`escenarios.py`, `cosim_snapshot.py`)

- La vigencia de un resultado es `firma_documento` (log sin lo que sólo organiza, `SIN_FISICA`,
  + materiales + las fichas del tablero armado: el color no cuenta; versión «2:», la 1 con
  `firmas_v1`: [V8.5](../../../docs/plans/V8.5-tablero-3d.md) F5b) + `hash_escenario` +
  `COSIM_EPOCH` ([cosim](../cosim/CLAUDE.md)); vencido = AMARILLO, nunca rojo ni verde. El
  snapshot toma los programas del carril y `programas=` los pisa por PLC (`test_plc`).
  [V8.3](../../../docs/plans/V8.3-prueba-virtual.md) (D12, D14)
- `resultado_compacto` guarda `electrico` (`medidas_electricas.py`) sólo con motores o un disparo;
  sus `referencias(doc)` las arma la API al tomar el snapshot, nunca el worker. Sin `electrico`
  sigue vigente: quien lo lee usa `cifras`. [pedidos-de-extensiones](../../../docs/plans/pedidos-de-extensiones.md) (F4)
- Los `ajustes` de PRUEBA de un escenario (`escenario_ajustes.py`) se validan como en
  `add_device` y se aplican a una COPIA del modelo del tablero en el snapshot, nunca a
  `doc.electrico` ni a `firma_documento`; entran sólo al hash de SU escenario y el resultado los
  lista. Quien publica cifras «del proyecto» trata ese escenario como uno de falla
  (`neumatica._sano`). [plan](../../../docs/plans/cotizacion-identificada-y-ajustes-por-escenario.md) (D5–D7)
- El balance de producto (`flujo_producto.py`) es UNA regla para las dos puertas (`evaluar` y
  `regla_entrega`). El ritmo nominal (`requirements.paquetes_por_minuto`) se GUARDA como número al
  declarar (`poner`), nunca se lee del requisito al correr.
  [balance-de-producto](../../../docs/plans/balance-de-producto.md)
- Una sesión en vivo vuelta escenario (`sesion_viva.py`) da por lote la huella de la sesión: la
  cola de productos con las instancias de la SESIÓN (`fijar_cola`), lo que pase de
  `cosim.escenario.DURACION_MAX_S` por tramo inicial (`hasta_s`); otra firma o una base borrada o
  cambiada se rechazan. Las aserciones se SUGIEREN (sólo las que pasan sobre esa corrida,
  `cosim/sugeridas.py`), nunca se guardan solas.
  [V8.4](../../../docs/plans/V8.4-maquina-viva-en-pantalla.md) (F4)
- Una extensión corre un escenario por `corrida_escenario.py` (`preparar_corrida` bajo el lock,
  `correr_corrida` fuera; sus errores llevan el texto del núcleo): un paso nuevo de la corrida de
  la API que deba ver la extensión va en los dos. [pedidos-iii](../../../docs/plans/pedidos-de-extensiones-iii.md) (D1)

## Tablero, aire y cobros (`tablero*.py`, `neumatica*.py`, `cobros.py`)

- Lo que dibujó un `layout_tablero` (`tablero.dibujados`) cuenta en la ESCENA con su ref, como una
  `pieza`: la BOM del carril y «pieza sin ligar» lo saltan; un consumidor nuevo que cobre o cuente
  dispositivos usa esa función. La pieza 3D de un aparato (la explícita gana; si no, la dibujada)
  es `tablero.piezas_3d` (la API la suma al vivo, `piezas_en_tabla`: ni el worker ni la firma la
  ven).
  [V8.5](../../../docs/plans/V8.5-tablero-3d.md) · [pedidos-de-extensiones](../../../docs/plans/pedidos-de-extensiones.md) (D15)
- El ruteo del tablero NO se cachea: `tablero.ruteos(doc)` es la única cuenta de largos (BOM,
  `circuito`) y reglas del ERC (`tablero_reglas.py`). La puerta y la placa vienen con el gabinete
  (`tablero.incluidas` → `bom_from_scene(incluidas=)`, `scene_costing(incluidas=)`): un
  consumidor nuevo de la BOM de compra la pasa.
- Lo que VE la persona (panel «Tablero») y lo que lee el agente (`get_circuit tablero=true`) es
  UNA función, `tablero_panel.panel`: hallazgos de los selectores del ERC y veredicto con la regla
  de `ui/src/diseno/atencion.ts::veredictoDe` (cambiar una es cambiar las dos); textos para la
  persona, lo crudo en `tecnico`. Calentamiento (`tablero_calor.evaluacion`) y prensaestopas
  (`tablero_prensas.del_tablero`) son la ÚNICA cuenta del panel, el ERC y la BOM; sus ítems los
  redacta `tablero_atencion.py`.
- El nombre de un aparato para la persona sale de `nombres_aparatos.Nombres` (rótulo con su
  `origen`, estados, grupo, rearme), nunca de otra tabla ni de la designación sola; en una frase,
  minúscula y con artículo: `con_designacion(des, frase=True, prep="de")` → «del cilindro de
  compuerta (-MM1)». [nombres-por-funcion](../../../docs/plans/nombres-por-funcion.md)
- Los cables de campo (`cables_campo.py`) no se cachean: `recorridos(doc, m, tableros)` es la
  ÚNICA cuenta de recorrido y largo (BOM, `circuito`, ERC y visor), sólo con `por`; lo que gira sale de
  `calidad_seguridad.analisis`. El panel los cuenta en `tablero_cables.py` sobre `vista`; el
  texto de `tecnico`, de las funciones del ERC.
- Un largo que calcula la BOM es también el de la co-simulación (`cosim_red.largos_calculados`):
  el declarado manda. El ERC de escena está en `erc_escena.py`; una regla que sólo da filas con
  hallazgo entra en `electrico.REVISA` (para salir en `revisadas` cuando pasa). «Aparato de campo
  sin pieza» (`electrico.campo_sin_pieza`: montaje `campo` sin pieza 3D) avisa SÓLO si la escena
  tiene piezas (un tablero solo no es un modelo a medias).
- El circuito de AIRE sale en la MISMA salida que lo eléctrico: `neumatica.py` arma la sección
  `neumatica` de `circuito`, los `puertos` y el ERC neumático AL FINAL de `_erc_completo`; sin
  aire, la salida de siempre (`tests/data/carril_v81_golden.json`). `neumatica.memoria` lee el
  tiempo de carrera del escenario NOMINAL (sin falla: una seta corta la carrera) y la velocidad
  del PICO de todos si pasa la declarada (de régimen); sólo vigentes. El panel «Neumática» es `neumatica_panel.panel` sobre ese MISMO ERC y memoria
  (cifras en `valor`: no rehace cuentas); el esquema, `neumatica_vista.py`.
  [V8.9](../../../docs/plans/V8.9-neumatica.md)
- Lo dudoso se dice DONDE se cobra: `costeo(doc)` es la fuente única de `/api/costing.json` y de
  la cotización (PDF y `X-Apolo-Avisos`); suma `avisos`/`monto_en_riesgo_usd` sólo si hay. La
  lectura acotada es `costeo_corto.acotar` sobre ese dict y el precio de la tool
  (`X-Apolo-Precio`), `drawing/quote.resumen_precio`. Avisos: dispositivo sin ligar a su pieza 3D
  y cable 3D que ningún `add_cable` cubre; nunca descuenta (ligar es del modelo). El ERC suma el
  mismo «cable 3D sin cobrar». [V8.1](../../../docs/plans/V8.1-modelo-electrico.md) (F4c)
- Las filas de `Extension.costeo` (`filas_de_extensiones`) entran AL FINAL ya costeadas (`origen`
  «extension:x», a `extensiones_usd`); una fila mal formada o una fuente que lanza no se cobra y
  lo dice un aviso. Sin ellas, byte-idéntico. [plan](../../../docs/plans/puntos-de-extension-entregables.md)

## Reglas de ingeniería y FEA (`engineering_rules.py`, `fea_rules.py`)

- `/api/checks` y la memoria comparten SÓLO lo idéntico (`requirement_inputs`,
  `inherit_inclination`, `structure_rules`). Sus diferencias son deliberadas (velocidad con `or`
  vs `is not None`, lints sólo en checks, stack-up y «alcance de la memoria» sólo en
  `memoria_reglas.py`): no las unifiques.
- `vigas_rules.beam_rules`: viga = perfil de catálogo cortable HORIZONTAL con ≥ 2 uniones
  perno/soldadura a vecinos de MENOR nivel (BFS desde los `ground`; una sola soldadura =
  empotramiento). Las cargas bajan por niveles, repartidas por igual (una viga baja sus
  reacciones); carga útil = puntual MÓVIL sobre las vigas que
  tocan `BED_RE` o, sin cama, las más altas; el requisito `carga_sobre` manda y cada nivel recibe
  la carga entera. Piezas de `create_conveyor` → `no_aplica`. Sin vigas → `[]`.
  [flecha-de-bastidor](../../../docs/plans/flecha-de-bastidor.md)
- La pieza A MEDIDA (sin ficha) que TRABAJA —recibe la carga útil o algo no-tornillería apoya en
  ella— también es viga o columna (`vigas_a_medida.py`, `columnas_a_medida.py`): sección MEDIDA en
  cortes (`seccion_medida.py`, memo de la corrida) y criterio de su material
  (`engineering/madera_calculo.py`: metal, E.010, EN 1995; nunca mezclados). Lo de una plantilla
  de máquina no entra (su regla manda); lo que trabaja y no se calcula sale `no_evaluada`
  (SIN_EVALUAR justificable), nunca callado; la inclinada y la que pisa el suelo, a `no_aplica`.
  [puerta-fuera-de-catalogo](../../../docs/plans/puerta-fuera-de-catalogo.md) (D7)
- `columnas_rules.columna_rules`: columna = perfil de catálogo VERTICAL apoyado abajo por
  perno/soldadura (o anclado), con la carga de `vigas_rules.cargas_que_bajan`. Base sólo
  atornillada o rol «columna»/«poste» sin sección → `no_evaluada` (SIN_EVALUAR en la puerta, se
  justifica). El rol «pata» es de `report_estructura`; el detector es `detectar_columnas`.
  [plan](../../../docs/plans/puerta-sin-sobrediseno.md) (F3f)
- `izaje_rules.hoist_rules` corre ANTES del chequeo estructural: sólo los pasadores de una cadena
  cuyo FS CALCULÓ salen de «sin dimensionar» (`uniones_verificadas`).
  [cadena-de-izaje](../../../docs/plans/cadena-de-izaje.md) (D13–D16)
- `conveyor_params_from_doc` es de los tres clientes (checks, memoria, tool `engineering_check`).
  Con un `create_roller_conveyor` (el último transportador del log) devuelve sus params con
  `plantilla`, validados con `library/rodillos_cadena_reglas.py` contra la ficha.
  [plan](../../../docs/plans/plantilla-rodillos-cadena.md) (D9)
- `fea_rules`: VIGENCIA por volumen (> 0.1 % de cambio o pieza borrada → «re-ejecuta»); el de
  ensamblaje por volumen CONJUNTO de `piezas_fids`; `hipotesis` va a la memoria.

## Preparación del FEA (`fea_setup.py`)

- Es la fase (a) del patrón dos-locks: validar, resolver material y selectores, derivar
  condiciones de borde y exportar los STEP al `tmp_dir` que pasa la API (el resto es de
  [api](../api/CLAUDE.md)).
- Honestidad: material sin σy tabulado exige `yield_mpa`; una superficie o un boceto-guía se
  rechazan.
- BONDED: el herraje (`FEA_HARDWARE_CATS`) sale de la malla y su peso entra como carga sustituta
  SÓLO en la rama automática (requisitos sobre la cama, `BED_RE`), no con `loads` explícitos.
  Empotramiento = base de las piezas con ground ∩ grupo, o `fixed_pieces`; sin ninguno → 400,
  nunca inventado. [V7.4](../../../docs/plans/V7.4-fea-firmable.md)
- `merge_convergence` corre como `before_save` (bajo el lock de la persistencia): re-correr el
  MISMO grupo con otro `mesh_size` pasa el previo al historial y el vigente reemplaza el de su
  misma malla.

## Cirugía (`cirugia.py`)

- `dependientes`: arrastra SÓLO `fasten`/`ground` que nombran una pieza borrada (también por
  prefijo `{cmd}_`) y la quita de los `members` de sus grupos; juntas y mates nunca. Un grupo que
  quedaría vacío no se toca: aviso. [cirugia-liviana](../../../docs/plans/cirugia-liviana.md)
- `como_seguir` arma el 400 de un borrado con referencias rotas: lo que `con_dependientes=true`
  arrastraría y lo que no, con ids y recortado. Lo que CREA un comando borrado (command_id
  `{cmd}_…`) no es dependiente. [mcp-sin-friccion](../../../docs/plans/mcp-sin-friccion.md) (D4, D11)

## Respuestas cortas para el agente (`paso.py`, `conexiones.py`, `reglas_cortas.py`)

- Modo corto: conteos + sólo lo que CAMBIÓ o FALLÓ; el detalle, a pedido. Una lista larga se
  recorta con `paso.recortar` y declara `<clave>_omitidas`: nunca un recorte silencioso.
  [mcp-sin-friccion](../../../docs/plans/mcp-sin-friccion.md) (D1, D2)
- «Repetido» = mismo nombre con los números por `*` (`reglas_cortas.patron`: una línea, `n`, el
  PEOR en `peor`). Una UNIÓN se agrupa por el PAR de patrones de sus piezas
  (`conexiones.patron_de`), no por su nombre. En corto lo «ok» va sin detalle salvo con `grupo`.
  `filtrar` encuentra una unión también por el COMANDO que la declaró.
  [trabas-de-modelado](../../../docs/plans/trabas-de-modelado.md) (D2)
- Un recorte o un error dice cómo seguir: la interferencia truncada suma `como_acotar`, un
  `fasten` por conjuntos se cuenta en `conexiones.expandidas` y la puerta anota segundos por
  regla (`delivery_inputs(tiempos=)`). `excluir_declaradas` usa
  `delivery_inputs.exclusiones_declaradas` (una sola fuente).

## Estructura propuesta (`estructura.py`)

- `propuesta_estructura` es la fuente ÚNICA de `POST /api/assembly/declare`: lo que propone es
  exactamente lo que aplica. Pasa `doc.joints` a `detect_structure` (lo que gira no se suelda) y
  deja `a_revisar`/`motivo` FUERA de `params` (un lote las ignora). La raíz del `resumen` sigue la
  regla de `commands/exec_uniones.py`. [uniones-en-lote](../../../docs/plans/uniones-en-lote.md)
- El TIPO lo decide `criterio_uniones.criterio` (puro: roles + contactos) con las reglas EN ORDEN
  de su docstring; la geometría sólo decide lo que ninguna regla toca. Una regla nueva va ahí con
  su caso en `tests/test_criterio_uniones.py`, y el fixture de la piloto
  (`tests/data/estructura_piloto74.json`) sigue ≥ 95 % y sin soldaduras desmontables. `kind`
  None = no se declara (`omitidas`), salvo que deje suelta una pieza que la geometría sujetaba:
  vuelve a revisar.
  [mcp-sin-friccion](../../../docs/plans/mcp-sin-friccion.md) (D6)
- No repite lo declarado (`unidas_por_lo_declarado`; los anclajes no unen): sobre una plantilla
  recién generada propone 0 (D7). Cada `fasten` propuesto lleva su dimensión (`dimensionado.py`):
  nada «sin dimensionar» (D8). Aplicada, `lote_compacto` ejecuta las MISMAS uniones que la
  propuesta (un `fasten` por conjunto verificado; las a revisar, sueltas). El corto
  (`estructura_corta.py`) expande un `fasten` por conjuntos con `pares_de_union` sólo si da
  exactamente los pares de la fila; ids sólo de `a_revisar`; aplicada, conteos
  (`aplicada_corta`), nunca la lista de conexiones.

## Video, vista 3D web y montaje

- Un rótulo sólo dice cifras leídas del documento, del catálogo o de un cálculo ya hecho
  (`datos_rotulos`); una plantilla nueva va en `rotulos.PLANTILLAS` con su test cifra por cifra, y
  la vista 3D (`cifras_grupo`) usa las MISMAS. `peso_roles` lo usan las etapas Y el video de la
  fábrica (fuera del núcleo). [vista-3d-web](../../../docs/plans/vista-3d-web.md) ·
  [video-montaje-pulido](../../../docs/plans/video-montaje-pulido.md)
- UNA secuencia de montaje para el manual (`pasos_manual`) y el video (`etapas_montaje`), SÓLO de
  lo declarado; sin estructura (`hay_grafo` falso), `order_by_support`. Las reglas están en el
  docstring de `montaje.py`: una nueva va ahí con su caso en `tests/test_montaje.py`. El acceso de
  herramienta NO impone orden. El título del paso va ENTERO.
  [video-montaje-pulido](../../../docs/plans/video-montaje-pulido.md) (F1b) ·
  [V8.9](../../../docs/plans/V8.9-neumatica.md)
- La `marcha` del guion cuenta en la duración y los capítulos, pero sólo la graba el navegador:
  todo render que no la anime usa `sin_marcha(g)`.
- La marcha de EJEMPLO (`marcha_ejemplo.py`) sale de la detección de la dinámica, nunca de otra;
  `probar` exige que una caja avance; lleva `sumideros` y la cola nace donde la caja no toca pieza
  (`_choca`). [puerta-de-publicacion](../../../docs/plans/puerta-de-publicacion.md) (F6)
- `linea_tiempo.py` y `plan_navegador.py` (el plan cuadro por cuadro que el visor sólo dibuja)
  viven aquí, no en la fábrica: una regla nueva del video va en `linea_tiempo.py` y la reciben VTK
  y el navegador. [video-realista](../../../docs/plans/video-realista.md) (D5)
- `extraer_marcha_visual` (`marcha_visual.py`) corre bajo el `STATE_LOCK` del llamador, en la
  misma adquisición que `prepare_dynamics`. Una cadena se reconoce por su `mesh_key`
  (`Transmision.clave` de `create_chain`: cambiar su formato la deja rígida,
  `tests/test_marcha_visual.py`) y sus piñones por las uniones `{cadena}_a|_b`. De la faja mide
  encuadres en SU marco (diestro: v = u×w) y la redondez (un tubo cuadrado no es tambor).
  [visor-realista](../../../docs/plans/visor-realista.md) (F3)
- La forma de la cinta y su prueba salen de cortes OCCT a lo ancho (`seccion_plano.py`);
  `marcha_ejemplo.fidelidad` lanza `MarchaInfiel` (quien la usa PARA). Un corte que no es UN lazo
  se cierra antes de caer al casco (`seccion_plano.cerrar`, ≤ 10 mm), y el casco sólo abraza lo
  redondo con junta o que toca la banda.
  [lo-fijo-que-gira](../../../docs/plans/lo-fijo-que-gira-y-lo-que-cuelga.md) (D4a)

## Roles por nombre (`roles.py`)

- `BED_RE` (cama/mesa: carga del FEA, altura de trabajo) y `SERVICE_RE` (piezas que se extraen).
  Un matcher por nombre nuevo lleva guarda de bracket/anclaje y un test con el nombre REAL
  ([drawing](../drawing/CLAUDE.md)).
- `rol_union` lee el SUSTANTIVO que encabeza cada tramo « · » (anclado: «Eje del rodillo» es eje,
  «Separador de guarda» es estructura), del último al primero y sin los tramos que nombran un
  grupo; el catálogo (tornillería, rodamientos, equipos, lo que gira) manda antes que el nombre.
  Una tapa sin otro rol es guarda salvo la de un rodillo o tambor (gira), un tubo o perfil
  (estructura) o la que aloja un rodamiento (`_rol_tapa`): ante la duda, guarda. El `cuerpo`
  conserva la numeración si la pieza ES ese tramo («Bandeja (tramo 1)») y la quita si es una
  parte («Guarda · extremo (+X)»). (D7)
