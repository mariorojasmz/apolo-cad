# Library (`core/apolo/library/`)

Catálogo, builders, materiales, chapa y cálculo (`engineering/`). Lo transversal, en la
[raíz](../../../CLAUDE.md); lo común del backend, en [core/apolo](../CLAUDE.md). Subpaquetes:
[electrico](electrico/CLAUDE.md) y [neumatica](neumatica/CLAUDE.md).

## Catálogo y builders

- **Una ref de catálogo es un EJEMPLO, no una orden de compra** (se reemplaza por la equivalente
  del proveedor local): marcas que CUMPLEN la norma y se consiguen fácil, diseño fácil de
  construir; la ficha dice lo que hay que respetar para reemplazarla (función, norma, cota de interfaz, rating: In, Icu, B10d, Ø, presión…) y
  `specs.linea_referencia` sólo cita «del orden de».
- **Una ref con bloques `electrico.*`, `tablero:` o `neumatico:`**: antes de escribirla, lee con
  `Read` su `electrico/ficha*.py` o `neumatica/ficha.py` (carga el CLAUDE.md del subpaquete); el
  loader rechaza la ficha incompleta.
- Para agregar partes: YAML en `data/` (el prefijo numérico ordena); builder nuevo sólo si la
  geometría no existe. `param_keys` lee del VARIANT (no de `specs_common`); el loader vuelca toda
  clave extra del variant a `specs`. Editar sólo YAML no recarga el worker (raíz).
- `builders.py` es FACHADA: re-exporta por identidad y guarda `BUILDERS` (orden fijo,
  `tests/test_rutas_viejas.py`: sólo se agrega al final). Un builder nuevo va a su
  `builders_<familia>.py` (+ su entrada en `BUILDERS`) o a un módulo con registro propio, que
  `loader.py` une rechazando nombres repetidos.
  [partir-nucleo-congelado-ii](../../../docs/plans/partir-nucleo-congelado-ii.md)
- Biblioteca paramétrica > STEP de fabricante (sólo para la compra puntual). `cost`,
  `cost_por_m` y `COST_PER_KG_USD` son REFERENCIALES. Una ref ELÉCTRICA lleva siempre `cost` (sin
  él, «sin precio», nunca estimada por peso: `tests/test_cotizacion_electrica_f4.py`), y también
  una pieza a medida de ROL eléctrico (`piezas_electricas.es_rol_electrico`, con guarda contra la
  clavija de madera y la toma de fuerza). Un cable modelado en 3D es material `cable`, no se cobra
  (lo cobra su `add_cable`) y su largo en la BOM es el RECORRIDO (`recorrido_mm`), no el bbox.
  [V8.1](../../../docs/plans/V8.1-modelo-electrico.md) (F4, F4c)
- La BOM es para COMPRAR: la banda (rol) cerrada sale por su LAZO (`banda_lazo.py`) y la
  tornillería a medida con su largo NOMINAL (`largo_tornilleria.py`; fuera de serie, el inmediato
  superior con `aviso`), una fila por largo. La comercial modelada A MANO
  (`designacion_comercial.es_comercial`: rol de compra o norma con designación en la CABEZA del
  rol, nunca una de plano/perfil ni en un rol que se fabrica —«Eje … (con anillos DIN 471)»—) es
  ref `COMPRA` de la categoría de compra en BOM, costeo y cédula (una fuente), con su norma, sin
  medida de corte salvo largo nominal o lazo y, con norma, UNA fila por designación + largo +
  material (con `ubicaciones`). Lo que una unión `perno` DECLARA y nadie modeló lo suma
  `tornilleria_declarada.py` (sin duplicar lo modelado, también la tuerca tras una arandela; no la
  del comando de OTRA unión). La arandela de catálogo (`arandelas`) no cubre un perno declarado y
  `_is_bolt` la cuenta como herraje. La compra la DECLARA el modelador (`compra_declarada`:
  «(compra)», «de compra», «tipo Marca código»), nunca se adivina por el rol. Con OTRO material
  asignado (`set_material`, `fasten.material_tornilleria` o la nota) se compra la EQUIVALENTE en
  ese material (`material_compra.py`). [defectos](../../../docs/defectos.md) (F6)
- El aire en `library/`: la BOM (`bom_electrico._racores`) suma un racor por extremo de tubo en
  un puerto ROSCADO (`specs.racor_rosca`/`racor_tubo_mm`) y lee un tubo SIN largo hacia un
  silenciador como roscado directo. El cilindro (`builders_neumatica.py`) lee sus cotas de los
  `params` de la ref (fuente en el YAML) y las de los accesorios ISO 15552 de
  `neumatica/montajes.py`: nunca una cota de interfaz en el builder. El vástago viene con su ref
  (`incluidas.py` lo saca de BOM y corte). Peso de una ref: `peso_ficha.peso_de_ficha` (cilindro
  ENTERO: `weight` + `peso_por_mm_kg` × carrera); quien SUMA piezas pasa `partes_de_cilindros` o
  cuenta el vástago dos veces. [V8.9](../../../docs/plans/V8.9-neumatica.md)
- `position` = centro del bbox; un builder con origen propio coloca su ORIGEN LOCAL en
  `position` (barreno del `worm_gearmotor`, cara de montaje del `caster`:
  [plan](../../../docs/plans/garruchas-catalogo.md)). Los perfiles se extruyen en Z (rotar 90° en
  Y → larguero en X).
- Builders: `Polygon(*pts)` CENTRA sus puntos (`align=None` para coordenadas absolutas). Todo
  término empieza con `Pos(...) *` (un `Rotation(...) * shape` pelado da `ValueError`); las partes de un mismo sólido SOLAPAN 0.5–8 mm (tangentes →
  Compound; disjuntas → ShapeList sin `.volume`); `build_component(ref, L)` ignora `L` si no es
  `cuttable`.
- **Zonas de acabado** (`zonas.py`; `builders_mandos.ZONADOS`): el builder da `{zona: forma}` y el
  loader las une en UN sólido (una Feature, una fila de BOM, una masa) con la zona de cada cara
  por ÍNDICE de `faces()` (`kernel/zonas.py`: la caché pierde el TShape y conserva el orden);
  `zona_por_cara` valida n.º de caras y volumen (taladrada → sin zonas). `fijo` = color de norma
  que `set_color` no pinta. [plan](../../../docs/plans/seta-de-emergencia.md). La zona de color
  (`builders_mandos.ZONA_DE_COLOR`) lleva el acabado de su `specs.color`
  (`apariencia.ACABADO_DE_COLOR`, donde entra un color nuevo) y `fijo`, o la ref no carga.
  [pedidos-ii](../../../docs/plans/pedidos-de-extensiones-ii.md) (D-a)
- **Aparatos de tablero** (`builders_aparatos.py` + `aparatos_forma.py`, por zonas): la forma de
  su familia DENTRO de la envolvente `width` × `depth` × `height` (la colocación lee los params,
  `ficha_tablero.FAMILIAS_APARATO`). Se construyen UNA vez por proceso (`unir_zonas(memo=True)`):
  el sólido se comparte, nunca se muta. Un detalle nuevo son caras: mide construir + teselar; nada
  de booleanas en paralelo (orden de caras). [plan](../../../docs/plans/aparatos-de-tablero-realistas.md)
- Un param nuevo de un builder existente entra con el default que reproduce la geometría de antes
  y un test que la congela (volumen, caras, bbox): así no es bump.
  [mandos-de-seguridad](../../../docs/plans/mandos-de-seguridad.md)
- Anclas que dependen de los params de la ref (un piñón: `eje`, `hilera_k`, `fase`) van POR
  FAMILIA (`loader.ANCLAS` → `Component.anchors`); `_CATEGORY_ANCHORS`, sólo las fijas por
  categoría. ASA 40 y BS 08B son de 1/2″ pero NO intercambiables: la serie va en `specs.serie` y
  quien combina piezas la compara. [plan](../../../docs/plans/cadenas-pinones.md)
- Ingletes (`miter.py`, `weldment.py`, `frame.py`): corte por el plano BISECTOR del nodo.
  Weldment = marcos sup/inf a 45° + postes a tope; frame = bisectriz sólo en nodos de grado 2
  (colineal → recto; α > 75° o grado ≠ 2 → tope). `Feature.miter` → BOM «∠45°/45°» y
  `cut_length` = longitud EXTERIOR. [devlog § V5.8](../../../docs/devlog.md)
- **La lista de corte MIDE** (`cutlist_medida.py`): perfil → largo exterior y corte por extremo
  (`kernel/corte_barra.py`; lo declarado sólo se contrasta: `aviso`); chapa →
  `chapa_ficha.desarrollo` (el mismo del desplegado, el CSV y los planos).
  [plan](../../../docs/plans/lista-de-corte-medida.md) La BOM lee la MISMA medida
  (`bom_compra.py`; misma ref con otros taladros → otra fila con su `marca`). A medida: gana la
  norma declarada; si no, la de su FORMA (`norma_de_material`); la madera, la de su material; sin
  base («acero zincado»), ninguna. Cada fila alcanza para comprar o cortar (`bom_comprable.py`,
  `bom.comprable`) y un grupo «(compra)» es UNA fila en BOM, costeo y cédula (`compra_grupos.py`;
  su nombre sin comas). [bom-de-compra-fiel](../../../docs/plans/bom-de-compra-fiel.md) (D3–D5)

## Materiales (`materials.py`)

- `resolve_material`: override → catálogo → heurística por nombre → default del VERTICAL
  (`set_vertical('carpinteria')` = madera; si no, acero). Quien tiene el documento pasa
  `doc.default_material()`: con el vertical CONOCIDO la palabra de carpintería no decide (BOM,
  masa, costeo, corte, planos vía `meta["material_vertical"]` y apariencia); `None` =
  desconocido, la heurística vieja. Polímero, caucho (rol anclado: «Engomado…», «Recubrimiento
  del tambor») y vidrio miran el ROL. [defectos](../../../docs/defectos.md) (F6)
- `_norm` devuelve la primera clave que sea SUBCADENA: las especies van ANTES de `"madera"`.
- Un material sin densidad tabulada se pesa como ACERO: fuera de la puerta sólo avisa
  (`aviso_material`), en la puerta FALLA `material.conocido`. Una especie nueva entra con la cita
  de cada cifra en los dicts, `HATCH`, `lint_soldadura._NO_SOLDABLE` y `apariencia`.
  [hallazgos-del-revisor](../../../docs/plans/hallazgos-del-revisor-en-la-puerta.md) (D1, D2)
- La heurística muerde: «larguero» es palabra de madera (`_WOOD_WORDS`). Quien re-resuelve el
  material de una pieza ya resuelta le pasa el `material` que ya tiene.
  [V7.5](../../../docs/plans/V7.5-e22-datum-funcional.md)
- Un matcher de ROL mira `piece_role(nombre)` (tras el último « · », o el anterior si ese es una
  especificación), nunca el nombre entero: «Faja de banda · Pata (1)» contiene «banda». Rol
  `banda` → PVC salvo metal explícito. [devlog § banda PVC](../../../docs/devlog.md)
- En madera `YIELD_MPA` tabula el MOR (rotura): el criterio es FS ≥ 4 (σ_adm = MOR/4), no ≥ 1.5.
- **Cómo se VE un material** (`apariencia.py`, fuente única de los dos renderizadores): un
  material nuevo lleva su acabado (`tests/test_apariencia.py`); tras editar la tabla,
  `python -B scripts/acabados_ui.py --escribir` regenera la copia del visor. El color asignado
  (`Document.colors`) define el albedo SÓLO en un acabado `pintable` (pintado, caucho, PVC,
  madera, cartón); en un metal manda la tabla. Acero liso por rol: cadena → pavonado,
  eje/piñón → mecanizado, rodillo/tambor (y su tubo) → galvanizado. La `textura` es SÓLO del
  visor (no va a VTK). [visor-realista](../../../docs/plans/visor-realista.md)

## Chapa (`sheetmetal.py`)

- `k_factor=None` = K POR MATERIAL (`K_FACTOR_BY_MATERIAL`), resuelto en la API con
  `resolve_material`.
- Features en pestaña: `u` a lo largo del pliegue ALINEADA AL EJE MUNDIAL (0 = centro), `v` desde
  el BORDE LIBRE (3D y desplegado coinciden sin conocer el radio). Invadir la zona de pliegue se
  rechaza con el dominio válido. Al flat: offset padre = `BA_p + (altura − OSSB_p) − v`, hijo =
  `strip_total − v`.
- La vía simple (lados/altura) se NORMALIZA a `flaps` (flat byte-idéntico). `child` de un nivel;
  el pliegue hijo queda vivo (sin fillet). [devlog § V5.5](../../../docs/devlog.md)

## Ingeniería (`engineering/`)

- **Un cálculo NO filtra por `visible`**: ocultar es estado de vista (`Document.hidden`). Las
  masas van con `include_hidden=True`; la puerta de entrega y la BOM aún filtran
  ([backlog](../../../docs/backlog.md) § Validación).
- Toda verificación cuantitativa lleva bloque `calc` {titulo, entradas, formula, sustitucion,
  resultado, criterio, fs, norma}: norma real o «criterio de diseño», nunca una cita inventada.
  Eje: σ_adm = 0.5·σy (más estricto que ASME B106.1M); flecha L/240 (AISC).
  [V7.2b](../../../docs/plans/V7.2b-barrida-residuos.md) · [V7.2c](../../../docs/plans/V7.2c-fixes-re-auditoria.md)
- Fits ISO 286 (`fits.py`): K-P sólo grados 6-7; el bore de rodamiento es ISO 492, no 286.
  `SEAT_RECOMMENDATIONS` por montaje: inserto UC → eje h7 que DESLIZA; anillo giratorio prensado
  → k6; eje FIJO (p. ej. el tensor) → g6/h6. La regla «asiento ISO 286» (`report_ajustes.py`)
  detecta pares eje ↔ rodamiento (fastener/junta/mate concéntrico + Ø coincidente): sin fit →
  aviso; k6 en inserto UC → ERROR. [devlog § V5.4](../../../docs/devlog.md)
- El fit del EJE va en el NOMBRE («Eje motriz Ø35 h7») y el del taladro en `drill_hole.fit`; los
  planos los rotulan solos ([services](../services/CLAUDE.md)).
- Roscas (`threads.py`): `drill_hole.thread` taladra a la broca de machuelado PUBLICADA (M8 →
  Ø6.8; `diameter` se ignora); fit y thread son excluyentes (rosca interior 6H fija). Roscas
  exteriores, fuera de alcance (por nombre). [devlog § V5.7](../../../docs/devlog.md)
- Fijación de taller (`fijacion.py`, puro; criterios de `join_bolted` en
  [commands](../commands/CLAUDE.md)): perno DIN 933 con L ≥ agarre + tuerca + 2 pasos (largo de
  catálogo o error); sin acceso por detrás (el ala de un perfil abierto SÍ lo tiene) → remache
  ciego DIN 7337 (más grande que M8 = error); base de madera → DIN 571 con ≥ 2/3 dentro y la
  punta ≥ 2 mm antes de la cara de atrás. Sus tablas son espejo de
  `112_fijacion_ciega.yaml`/`113_tirafondos_hex.yaml`. Madera = `materials.es_madera` sobre
  `resolve_material_vertical`. [union-en-perfil-hueco](../../../docs/plans/union-en-perfil-hueco.md)
- Remache ciego: `fasten.size` es el Ø del cuerpo («Ø4.8») y se dimensiona a cortante en
  `report_uniones` (`remaches.py`, forma de EN 1993-1-8, criterio declarado). Pandeo de COLUMNAS
  de catálogo: `columna.py` (Euler/Johnson, K de AISC); qué es columna, en
  [services](../services/CLAUDE.md).
- Pernos (`bolts.py`): broca de paso ISO 273 serie media (M12 → Ø13.5); par de apriete
  `tightening_torque_nm` con `TORQUE_K` por condición. [devlog § E5](../../../docs/devlog.md)
- `loads.hanging_load_kg`: carga de una unión = la masa que pierde tierra al quitar su arista
  (redundante → None). `mass`: catálogo por FICHA, a medida volumen × densidad.
- `report.structure_engineering_check`: las uniones sin dimensionar se AGREGAN en una
  regla-resumen; redundante + dimensionada = ok con nota. `report.py` es orquestador y ruta vieja:
  una verificación nueva va a su módulo `report_*`
  ([plan](../../../docs/plans/partir-nucleo-congelado-ii.md) D3).
- Viga continua (`viga_continua.py`, Hermite exacto): cargas y flechas + hacia ABAJO, reacciones
  + hacia ARRIBA (negativa = tracción, no se recorta). Secciones (`secciones.py`) en ejes LOCALES
  del builder (`i_x` = canto en Y): tabla de norma si los params calzan; HSS A500 con t =
  0.93·t_nom y r = 2t (el `rect_tube_*` de `structural.py` es arista viva y nominal); perfil
  ranurado → `None` (`SIN_SECCION`), jamás la inercia del macizo. Un ángulo L flecta LIBRE por sus
  ejes principales (`angulo_libre`); criterio en `viga_bastidor.py` (vano L/240, voladizo
  2·Lv/240, σ ≤ 0.6·fy). [flecha-de-bastidor](../../../docs/plans/flecha-de-bastidor.md)
- Instalación (`installation.anchor_loads`): reparto ELÁSTICO por apoyo; N > 3 es hiperestático
  y la hipótesis se DECLARA; un R_i negativo es TRACCIÓN, jamás cero. [V7.6](../../../docs/plans/V7.6-e2-fino.md)

## Stack-up (`engineering/stackup.py`)

- Motor PURO peor caso + RSS de una cadena 1D. Cada eslabón con tolerancia de UNA fuente: `{pm}`,
  `{fit: "h7"}` (banda ISO 286 asimétrica, `fit_limits`), `{iso2768: "m"}` o `{lim: [lo, hi]}`;
  veredicto contra `{min_mm | max_mm | entre}`.
- Las cadenas DECLARADAS son metadato (raíz § Metadato ≠ comando). Un eslabón `{id, eje}` mide el
  bbox VIVO; `nominal_mm: "=expr"` sigue las variables. Evaluación y cadenas auto:
  [services](../services/CLAUDE.md); rollback del PUT: [api](../api/CLAUDE.md).
  [V7.3](../../../docs/plans/V7.3-stackup-cadenas-cotas.md)
- `bolt_pattern_budget(flotante=)`: perno + TUERCA (pasante) → holgura completa; perno fijo → la
  mitad. Declarar flotante sin tuerca sería optimista.

## Reglas de conveyor (`rules.py`) y requisitos

- `rules.py` es orquestador de `conveyor_engineering_check` y ruta vieja. Una regla nueva va a su
  bloque `rules_faja_*` con el estado en `ContextoFaja` (lo producido vuelve por `return`);
  `tests/test_reglas_faja_congeladas.py` congela tres salidas.
  [plan](../../../docs/plans/partir-nucleo-congelado-ii.md) (F3)
- `detect_conveyor` se enriquece con VARIABLES, nombres y specs (`motorreductores_sinfin`: η 0.75
  vs 0.85 helicoidal; sin `rpm_salida` de ficha, las rpm salen de la relación de la PLACA en el
  nombre, «i = 40», `relacion_motor.py`; lo declarado gana:
  [faja-compacta](../../../docs/plans/faja-compacta.md) F1b). Un transportador de rodillos a
  mano lo reconoce `rodillos_a_mano.py` por catálogo y geometría, sólo con motorreductor; su
  capacidad sale de lo MEDIDO (`rodillos_a_mano_medida.py`: eje con el Ø que TRABAJA —el menor
  del vano—, apoyos —también el ala a tope de un eje de rosca hembra con su perno DECLARADO: quien
  llame a `detect_conveyor` le pasa `doc.fasteners`—, rodamientos de catálogo o nombrados con su
  serie): L10 + σ del eje + desalineación eje↔tubo (≤ 10′) y el motor con el método de la
  plantilla; sin un dato real, AVISO con el motivo, nunca una capacidad inventada.
  [defectos](../../../docs/defectos.md) (F6)
- El Ø del tambor de una faja a mano es el MEDIDO de lo redondo y largo (`diametro_tambor.py`: lo
  motriz primero, sin ejes, tapas ni guardas), nunca el lado menor de la caja de un «tambor».
- «Ancho útil» (`ancho_util.py`): rodillos = ancho − 2 largueros; BANDA = el ancho MEDIDO de la
  banda y, si es menor, la luz entre guías laterales sobre ella (sus largueros van por fuera).
- Método de arrastre POR CONSTRUCCIÓN (`soporte` derivado del modelo): cama/mesa → CEMA
  slider-bed μ = 0.33 + arranque 1.6× (`engineering/belt.py`); rodillos portantes → ISO 5048/DIN
  22101 (`iso5048.py`; L < 80 m es interpolación referencial). El μ = 0.06 es SÓLO para rodillos.
- Adherencia del tambor motriz (Euler-Eytelwein): μ 0.35 engomado / 0.25 liso por NOMBRE del
  tambor; FS sólo con `t2_n` declarado. `tiene_tensor` NO sale del nombre: lo pone
  `services/engineering_rules.inherit_tensor` con el tensor RECONOCIDO. [devlog § V5.10](../../../docs/devlog.md)
- **Puerta de publicación** (`calidad/`, puro; insumos en [services](../services/CLAUDE.md)): cada
  control devuelve `item.Item` (OK | FALLA | SIN_EVALUAR | NO_APLICA, con evidencia). Largos de
  perno: `largos_perno.py`. [puerta-de-publicacion](../../../docs/plans/puerta-de-publicacion.md)
- `calidad/registro.py` es LA regla (D1, D14): ítems GENERALES por modo de falla, nunca de un
  mecanismo; una máquina nueva suma un detector (`services/puerta_hechos.py`) o un evaluador, no
  un ítem. NO_APLICA sólo por `aplica_si`; los ids de F2/F3 entran por el `mapa` de su `Fuente`
  (servicio `(doc, contexto=)`, UNA vez por puerta; puede dar `riesgos`). Cambiar un ítem, umbral
  o `aplica_si` sube `VERSION_REGISTRO` con su línea en `calidad/historial_registro.py`. Los
  controles de lo existente: `puerta.py`. Una extensión suma los suyos (`Extension.puerta`, ids
  «prefijo.x») en `DE_EXTENSION`: quien corre la puerta entera pasa `vigente()` a `reunir` y a
  `evaluar`, y `version(registro)` los firma; `evaluar(registro=None)` es sólo el núcleo.
  [plan](../../../docs/plans/nucleo-abierto-extensiones-privadas.md) (F1d)
- `interfaz.nombres_por_funcion` (`calidad/nombres.py`; `ENTRADA` importa de `calidad/entrada.py`,
  nunca de `registro.py`: ciclo): aprueba SÓLO el rótulo DECLARADO con la tabla CERRADA de tipos
  y no se justifica; su insumo se lee UNA vez en `delivery_inputs` y la regla de
  `delivery_check` usa el mismo criterio, que `semaforo_entrega` descarta.
  [nombres-por-funcion](../../../docs/plans/nombres-por-funcion.md)
- Un AVISO se corrige o se JUSTIFICA por escrito (`calidad/justificadas.py`, metadato
  `justificadas`: regla exacta, ≥ 20 caracteres de porqué), nunca se calla con una pieza; un ERROR
  jamás. Lo leen `semaforo_entrega`, `erc`, `vida.reglas` y `no_aplica_justificado` (por texto,
  sección o piezas: `no_aplica_piezas`); un control nuevo que bloquee avisos lo lee igual. Nada se
  recorta en silencio: el PUT dice cuántas borró (`modo="agregar"` suma por (regla, pieza)), un
  `porque` > 600 se rechaza y `pieza` acepta las designaciones del ERC. `diseno.sin_sobrantes` (`calidad/sobrantes.py`) juzga lo que mide
  `services/calidad_sobrantes.py`. [plan](../../../docs/plans/puerta-sin-sobrediseno.md) (D5–D11)
- La banda de `create_belt_conveyor` abraza el radio EXTERIOR de cada tambor (con `lagging_mm`) y
  cada eje baja lo que crece su tambor. Un choque DENTRO de un super-comando no lo ve
  `interference_report(exclude_pairs=same_command_pairs)`: el super-comando lo prueba SIN
  exclusiones (`tests/test_belt_conveyor.py`) y la puerta lo mira. Toda pieza nueva de
  `belt_conveyor_*.py` entra con su `Plan.union` (cada unión que toca, pies anclados) y el
  bastidor con material de ficha (`Feature.material`: «larguero» sería madera). Toda pieza o cota
  nueva de un resguardo se mide con la puerta en varias variantes, también una GRANDE (> 12 M
  voxeles: el voxel crece y aparecen ventanas). Una placa que cierra un tubo es «Placa de
  cierre…» (estructura, soldada); «Tapa…» sería guarda. [defectos](../../../docs/defectos.md)
- La faja EN MARCHA (`ruta_faja_modelo.py`, puro): la cinta es la línea media de la SECCIÓN del
  sólido de la banda (sin lazo cerrado, el casco de `ruta_faja.py`); `fidelidad_faja.py` la prueba
  contra el modelo y una que falla no se publica. Comba = mín(CEMA 2 %, w·l²/8T de la tracción
  MEDIDA, holgura con lo de abajo), sólo en tramos rectos del retorno.
- `Document.requirements` (metadato): `/api/checks`, la memoria y la cotización CAEN a ellos (un
  param explícito gana). Se validan en `requisitos.py` (la CARGA no valida: un manifest viejo
  abre tal cual). Lo ASUMIDO entra `{"valor", "asumido"}` y se guarda PLANO + lista `asumidos`:
  todo lector de `requirements[k]` ve un escalar. [revision-de-taller](../../../docs/plans/revision-de-taller.md) (D1)

## Validación: interferencias, lints y puerta de entrega

- `interference_report`: candidata = pareja que PUEDE interferir según el prefiltro EXACTO de
  `interferencias_filtro.py`: un descarte nuevo ahí es exacto y entra con su caso en
  `tests/test_interferencias_escala.py`. El chequeo GLOBAL (puerta de entrega, `verify`) pasa
  `tope=tope_global(scene)`, no el `MAX_PAIRS` fijo. [defectos](../../../docs/defectos.md) (F6)
- `check_interference` excluye pares de junta, `same_command_pairs` y `HARDWARE_CATS`;
  `interpenetration_report` mide el EXCESO sobre la pose de diseño en pares con junta.
  `HARDWARE_CATS` NO se amplía (interferencia, corte y lints): el FEA usa `FEA_HARDWARE_CATS`.
  Revisa ≤ `MAX_PAIRS` por página (`desde`, orden estable); si recorta lo declara
  (`parejas_sin_revisar`, `desde_siguiente`) y la puerta lo dice.
- `lints.predelivery_lints`: «barreno de paso Ø7-22 sin perno en su eje» y «pieza sin grupo NI
  unión declarada» (excluye guías, superficies y herraje). Reconoce tornillería a medida por
  NOMBRE (`_is_bolt`) y, por la MISMA medida de `union.agujeros` (inyectada:
  `services/calidad_agujeros.agujeros_atribuidos`), la que un `fasten` perno declara sin modelar.
  Todo matcher por nombre nuevo lleva guarda de anclaje/plurales y un test con el nombre REAL.
  «Soldadura imposible» (`lint_soldadura.py`) es el único lint ERROR (bloqueante en `delivery.py`);
  sin `material_vertical`, asume acero.
- Perfiles abiertos: `r1`/`r2`/`pendiente_ala` son datos de NORMA que el builder no lee (sin
  bump); `acuerdos.py` deriva la zona plana y `lint_asiento.py` lee los taladros de la GEOMETRÍA,
  no de los comandos (`join_bolted` corta sin `drill_hole`). Su marco sale de las ANCLAS por
  familia (`perfiles_abiertos.py`) o, sin ellas, del bbox. Una función de anclas que declara
  `specs` los recibe del loader. [plan](../../../docs/plans/perfiles-con-acuerdo.md)
- `delivery.py` es un agregador PURO → VERDE/AMARILLO/ROJO: interferencias en diseño + sujeción
  DECLARADA (sin autodetect) + lints + integridad/suprimidos + colisión en las poses de REPOSO
  (el tránsito, `scan_motion`; insumos: [services](../services/CLAUDE.md)) + gravedad opt-in. ERC,
  acceso de herramienta y escenarios entran SÓLO si existen. Las reglas de una extensión
  (`Extension.entrega`, `entrega_extension.py`) van al final con `id` y `origen`; sólo con ellas
  sale `version_bateria` (`VERSION_BATERIA` sube si cambia un chequeo del núcleo).
  [plan](../../../docs/plans/puntos-de-extension-entregables.md)
- **¿Entra la lengüeta?** (`enclavamiento.py`, puro; lectura en `services/enclavamientos.py`): con
  el resguardo cerrado la lengüeta está en su ranura (`specs.insercion_min_mm` ≤ profundidad ≤
  fondo, sección dentro de la ranura) y, con junta, abierto está fuera; si no, ROJO. Marco SÓLO de
  las anclas `ranura`/`punta` + `fijacion_1/2` y las cotas del builder, nunca del bbox.
  [mandos-de-seguridad](../../../docs/plans/mandos-de-seguridad.md) (F2b)
- **Lo declarado unido se toca** (`calidad/contacto.py`: `union.contacto_real` y su regla ROJA;
  medido en `services/calidad_contacto.py`): soldadura con cordón eficaz ≥ max(30, 6·a) (EN
  1993-1-8 §4.5.2) sobre la línea de contacto de `kernel/contacto.py`, apoyo sin punto, perno que
  cruza su hueco. El MISMO largo dimensiona el cordón (`report_uniones`) y lo propone
  `declare_structure`. Lo de una cadena no se mide. [uniones-que-tocan](../../../docs/plans/uniones-que-tocan.md)
- Lo que no puede correr va en `no_aplica`: jamás cuenta verde. Un asiento ≤ `EXCESS_TOL_MM3` se
  tolera y se DECLARA (`contactos_tolerados`). Tornillería flotante = AVISO, no ROJO.
- Exclusiones UNIFICADAS diseño + pose: par con fasten = contacto firmado; tornillería a medida =
  asentada.
- **¿Entra la llave?** (`acceso_herramienta.py`): la tuerca/cabeza se reconoce por GEOMETRÍA
  (`fijadores_geom.py`: 3 pares de caras a 60°), no por catálogo; sus fantasmas
  (`fantasmas_herramienta.py`) se cruzan con los vecinos. La pieza de asiento NO se excluye
  entera: los fantasmas arrancan a 1 mm del asiento. Ninguna libre = ROJO, sólo boca = aviso,
  sin hexágono = no evaluado. Varios hexágonos coaxiales en un sólido son varios fijadores
  (`reconocer_fijadores`). Sin hexágono: un remache (`herramienta: remachadora`) se lee por su
  cilindro mayor con la remachadora coaxial; un DIN 571 (`llave: true`) es tornillería de llave;
  un DIN 603 lo aprieta su tuerca, como el espárrago
  ([rodillos F9](../../../docs/plans/plantilla-rodillos-cadena.md)).
  [plan](../../../docs/plans/acceso-de-herramienta.md)
- `MIN_SOLIDOS_SUJECION` también dispara `aviso_estructura` ([api](../api/CLAUDE.md),
  [V6.9](../../../docs/plans/V6.9-puerta-de-entrega.md)).
- **Seguridad y reparabilidad** (`seguridad/`, `reparabilidad.py`; OCCT en
  `services/calidad_*.py`): peligros ISO 12100, sondas ISO 13857 (banda y rodillo portante liso no
  son peligro), guarda atornillada, desgaste sin soldar y desmontable, banda montable (sin fin y
  ATRAVESADA por algo más que sus tambores falla, salvo su empalme de campo `empalmes_banda` unido a ella). `seguridad.electrico` se descarta (es `riesgos.electrico`).
  Lo que se alcanza doblando el brazo: `alcance.py` + `services/calidad_codo.py` (la mano ≤ 230
  mm, `sondas.veredicto`). Umbrales: [plan](../../../docs/plans/puerta-de-publicacion.md) § F3 y
  § F6. Con el sentido de marcha conocido sólo se sondea la cuña de ENTRADA de cada tambor
  (`seguridad/cuna_entrada.py`; el sentido, en `services/calidad_cunas.py`: escenario >
  requisito `sentido_transporte` > plantilla; `reversible` o sin fuente, las dos), nunca del
  nombre ni del giro de la junta. [plan](../../../docs/plans/puerta-sin-sobrediseno.md) (D3–D4)
- **Peligro = lo ACCIONADO** (F3b): una junta de giro sin motor, cilindro, resorte ni escenario
  que la mueva es de SERVICIO (`services/calidad_juntas.py`) y no es peligro, pero se mueve
  (`moviles`). Acople y salida del motorreductor sí (`seguridad/transmision_rigida.py`).
  Resguardo = la guarda que paró una sonda o la declarada en `funciones` (`resguardo`), no toda
  «tapa»; el piso es el apoyo de lo anclado. El extremo de eje LISO que sobresale ≤ ½·d no es
  peligro (`seguridad/extremo_eje.py`, OSHA 1910.219(c)(4); medido en
  `services/calidad_extremos.py`); chavetero, prisionero, tuerca o más saliente, sí; un COLISO es
  agujero por su ANCHO. Máquina ANCLADA (`calidad_seguridad.piso_solido`) → piso SÓLIDO: ninguna
  sonda nace ni pasa por debajo (`sondas.cruce_piso`), es pared del brazo y el hueco piso ↔ panel
  lo decide la tabla 4; sobre ruedas, el brazo llega por debajo.
- **Lo declarado se fabrica** (F3c): `union.agujeros` (`calidad/agujeros.py`, medido en
  `services/calidad_agujeros.py`) pide a cada pieza a medida de un `fasten` perno (o de un
  anclaje con pernos en su nota) los agujeros de su métrica en la zona de la unión; lo de catálogo
  o «(compra…)» no se juzga. El ESPÁRRAGO (`esparrago.py`) se mide desde su base con su tuerca;
  un «Perno…» sin cabeza modelada sigue sin evaluar. El factor de servicio fuera de un
  transportador sale de `potencia_absorbida_kw`/`par_salida_nm` contra el FS de su servicio
  (`engineering/servicio.py`: AGMA por `tipo_carga` y `horas_dia`).
- **Distancia al borde de un agujero de perno** (`borde_agujero.py`): la MISMA medida para la
  puerta (`calidad/bordes.py`) y `join_bolted`. Chapa (EN 1993-1-8 tabla 3.3): canto = donde la
  pieza tiene el espesor de la chapa (no la esquina de un tubo, el talón de un ángulo ni un eje);
  el agujero de otro perno es paso; una barra maciza (t ≥ 1,5·d0, W ≤ 1,25·t) es `barra` y,
  roscada, se juzga su rosca. MADERA (`medir_madera`): testa ≥ 4·d y canto ≥ 3·d por la veta,
  criterio de diseño con los mínimos DESCARGADOS de EN 1995-1-1 tabla 8.4 (nunca citado como el
  extremo cargado); el tornillo que rosca en la testa falla aparte. Se mide la geometría, no la
  huella. Una ranura de perno ABIERTA al canto no cumple (junto a la boca el ligamento → 0): va
  cerrada, a ≥ 1,5·d0 (oreja de `rodillos_cadena_motriz.py`). [hallazgos-del-revisor](../../../docs/plans/hallazgos-del-revisor-en-la-puerta.md) (D7)
- **El eje de una junta de giro va trabado** (`ejes_giro.py`, en `agarre.retencion`; medido en
  `services/calidad_ejes_giro.py`): eje = coaxial ± 1 mm Y toca sus dos cuerpos. Sin junta
  declarada no se juzga. [plan](../../../docs/plans/hallazgos-del-revisor-en-la-puerta.md) (D8)
