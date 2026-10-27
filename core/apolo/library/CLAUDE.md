# Library (`core/apolo/library/`)

Catálogo, builders, materiales, chapa, bastidores y cálculo de ingeniería (`engineering/`). Lo
transversal (fronteras de paquete, locks, disciplina paramétrica) está en el
[CLAUDE.md raíz](../../../CLAUDE.md); lo común del backend, en [core/apolo](../CLAUDE.md).
Subpaquetes con CLAUDE.md propio: [electrico](electrico/CLAUDE.md) (ficha eléctrica, ERC,
tablero 3D) y [neumatica](neumatica/CLAUDE.md) (ficha `neumatico:`, ERC del aire, cilindros).

## Catálogo y builders

- **Una ref de catálogo es un EJEMPLO, no una orden de compra**: quien fabrica la reemplaza por
  la equivalente que consiga con su proveedor local. Al elegir o sumar una ref: marcas que CUMPLEN
  la norma y se consiguen fácil (comunes, no exóticas) y un diseño fácil de construir; la ficha
  dice lo que hay que respetar para reemplazarla (función, norma, cota de interfaz, rating: In,
  Icu, B10d, Ø, presión…) y `specs.linea_referencia` sólo cita «del orden de».
- **Una ref con bloques `electrico.*`, `tablero:` o `neumatico:`**: antes de escribirla, lee con
  `Read` su `electrico/ficha*.py` o `neumatica/ficha.py` (así carga el CLAUDE.md del subpaquete,
  con las reglas de cada bloque); el loader rechaza la ficha incompleta.
- Para agregar partes: editar/crear YAML en `data/` (el prefijo numérico ordena); builder nuevo
  sólo si la geometría no existe. `param_keys` lee del VARIANT (no de `specs_common`); el loader
  vuelca cualquier clave extra del variant a `specs`. Editar sólo YAML no recarga el worker (raíz).
- `builders.py` es FACHADA: re-exporta por identidad y guarda `BUILDERS` (orden fijo,
  `tests/test_rutas_viejas.py`: sólo se agrega al final). Un builder nuevo va a su familia
  `builders_<familia>.py` (+ su entrada en `BUILDERS`) o a un módulo con registro propio, que
  `loader.py` une rechazando nombres repetidos.
  [partir-nucleo-congelado-ii](../../../docs/plans/partir-nucleo-congelado-ii.md)
- Biblioteca paramétrica > STEP de fabricante (sólo para la compra puntual). `cost`,
  `cost_por_m` y `COST_PER_KG_USD` son REFERENCIALES: actualizar con proveedor para cotizar firme.
  Una ref ELÉCTRICA lleva siempre `cost` (sin él sale «sin precio», nunca estimada por peso:
  `tests/test_cotizacion_electrica_f4.py`), y una pieza a medida de ROL eléctrico (clavija, toma,
  prensaestopa: `piezas_electricas.es_rol_electrico`, con guarda contra la clavija de madera y la
  toma de fuerza) también. Un cable modelado en 3D es material `cable`, no se cobra (lo cobra su
  `add_cable`) y su largo en la BOM es el RECORRIDO (volumen / sección, `recorrido_mm`), no el
  bbox. [V8.1](../../../docs/plans/V8.1-modelo-electrico.md) (F4, F4c)
- La BOM es para COMPRAR: la banda (rol) cerrada sale por su LAZO (`banda_lazo.py`) y la
  tornillería de largo a medida con su largo NOMINAL (`largo_tornilleria.py`, orden de fuentes en
  su docstring; fuera de serie se pide el inmediato superior con `aviso`), una fila por largo. La
  comercial modelada A MANO (`designacion_comercial.es_comercial`: rol de compra o norma con
  designación en la CABEZA del rol, nunca una de plano/perfil ni en un rol que se fabrica —«Eje …
  (con anillos DIN 471)»—) es ref `COMPRA` en la categoría de compra del catálogo, en BOM, costeo
  y cédula (una fuente: el mismo módulo), con su norma y sin medida de corte salvo largo nominal o
  lazo; con norma, UNA fila por designación + largo + material y sus `ubicaciones` (nunca por
  pieza de origen). Lo que una unión `perno` DECLARA y nadie modeló lo suma
  `tornilleria_declarada.py` (sin duplicar lo modelado). [defectos](../../../docs/defectos.md) (F6)
- El aire en `library/`: la BOM (`bom_electrico._racores`) suma un racor por extremo de tubo en un
  puerto ROSCADO (rosca × Ø, `specs.racor_rosca`/`racor_tubo_mm`) y lee un tubo SIN largo hacia un
  silenciador como roscado directo (ni tubo ni racor). El cilindro (`builders_neumatica.py`) lee
  las cotas de los `params` de la ref (con su fuente en el YAML) y las de los accesorios ISO 15552
  de `neumatica/montajes.py`: nunca una cota de interfaz en el builder. El vástago viene con su
  ref: `incluidas.py` lo saca de la BOM y de la lista de corte por la escena sola. El peso de una
  ref es `peso_ficha.peso_de_ficha` (cilindro: `weight` + `peso_por_mm_kg` × carrera, el cilindro
  ENTERO); quien SUMA piezas pasa `partes_de_cilindros` (vástago = masa móvil de la ficha, cuerpo
  = el resto) o cuenta el vástago dos veces.
  [V8.9](../../../docs/plans/V8.9-neumatica.md)
- `position` = centro del bbox; un builder con origen propio coloca su ORIGEN LOCAL en
  `position` (p. ej. el barreno del NMRV, builder `worm_gearmotor`; la garrucha `caster`, la cara
  de montaje de la placa: [plan](../../../docs/plans/garruchas-catalogo.md)). Los perfiles se
  extruyen en Z (rotar 90° sobre Y → larguero en X).
- Builders: `Polygon(*pts)` CENTRA sus puntos (pasa `align=None` para coordenadas absolutas). Todo
  término empieza con `Pos(...) *` (un `Rotation(...) * shape` pelado da
  `ValueError: other must be a list of Locations`); las partes de un mismo sólido SOLAPAN
  0.5–8 mm (tangentes → Compound; disjuntas → ShapeList sin `.volume`); `build_component(ref, L)`
  ignora `L` si el componente no es `cuttable`.
- **Zonas de acabado** (`zonas.py`; builders de `builders_mandos.ZONADOS`): el builder da
  `{zona: forma}` y el loader las une en UN sólido (una Feature, una línea de BOM, una masa) con
  la zona de cada cara por ÍNDICE de `faces()` (`kernel/zonas.py`): la caché de geometría pierde
  el TShape y conserva el orden. `zona_por_cara` la valida por n.º de caras y volumen (taladrada
  → sin zonas). `fijo` = color de norma que `set_color` no pinta.
  [plan](../../../docs/plans/seta-de-emergencia.md). La zona de color de un builder
  (`builders_mandos.ZONA_DE_COLOR`: el `frente` del `mando_22`) lleva el acabado de su
  `specs.color` (`apariencia.ACABADO_DE_COLOR`, con el origen de cada tono) y `fijo`, o la ref no
  carga; un color nuevo entra en esa tabla. [pedidos-ii](../../../docs/plans/pedidos-de-extensiones-ii.md) (D-a)
- **Aparatos de tablero** (`builders_aparatos.py` + `aparatos_forma.py`, por zonas): la forma
  de su familia DENTRO de la envolvente exacta `width` × `depth` × `height` de la caja que eran
  (nada sale: la colocación lee los params, `ficha_tablero.FAMILIAS_APARATO`). Se construyen UNA
  vez por proceso (`unir_zonas(memo=True)`): su sólido se comparte, nunca se muta. Un detalle
  nuevo son caras: mide construir + teselar antes de sumarlo; nada de booleanas en paralelo
  (orden de caras). [plan](../../../docs/plans/aparatos-de-tablero-realistas.md)
- Un param nuevo de un builder existente entra con el default que reproduce la geometría de
  antes (la seta `bloques=1`) y un test que la congela (volumen, caras, bbox): así no es bump.
  El interruptor de resguardo y su lengüeta son DOS refs (se compran aparte) del mismo builder.
  [mandos-de-seguridad](../../../docs/plans/mandos-de-seguridad.md)
- Anclas que dependen de los params de cada ref (un piñón: `eje`, `hilera_k`, `fase`) van POR
  FAMILIA (`loader.ANCLAS` → `Component.anchors`); `_CATEGORY_ANCHORS` es sólo para las fijas
  por categoría. ASA (ANSI) 40 y BS 08B son de 1/2″ pero NO intercambiables: la serie va en
  `specs.serie` y quien combina piezas la compara. [plan](../../../docs/plans/cadenas-pinones.md)
- Ingletes (`miter.py`, `weldment.py`, `frame.py`): corte por el plano BISECTOR del nodo (V
  exacto = A·span, ancla de tests). Weldment = marcos sup/inf a 45° + postes a tope; frame =
  bisectriz sólo en nodos de grado 2 (colineal → recto; α > 75° o grado ≠ 2 → tope).
  `Feature.miter` → BOM/lista de corte «∠45°/45°» y `cut_length` = longitud EXTERIOR.
  [devlog § V5.8](../../../docs/devlog.md)

## Materiales (`materials.py`)

- `resolve_material`: override → catálogo → heurística por nombre → default del VERTICAL
  (`set_vertical('carpinteria')` = madera; si no, acero). Quien tiene el documento pasa
  `doc.default_material()`: con el vertical CONOCIDO la palabra de carpintería no decide (la
  guarda de BOM, masa, costeo, corte, planos vía `meta["material_vertical"]` y apariencia);
  `None` = desconocido, la heurística vieja. Polímero, caucho (rol anclado: «Engomado…»,
  «Recubrimiento del tambor») y vidrio miran el ROL. [defectos](../../../docs/defectos.md) (F6)
- `_norm` devuelve la primera clave que sea SUBCADENA: las especies van ANTES de `"madera"` en
  los dicts («madera copaiba» → copaiba).
- La heurística por nombre muerde: «larguero» es palabra de madera (`_WOOD_WORDS`). Quien
  re-resuelve el material de una pieza ya resuelta le pasa el `material` que ya tiene.
  [V7.5](../../../docs/plans/V7.5-e22-datum-funcional.md)
- Un matcher de ROL mira `piece_role(nombre)` (tras el último « · »), nunca el nombre entero: un
  super-comando nombra «Faja de banda · Pata (1)» y toda la faja contiene «banda». Rol `banda` →
  PVC salvo metal explícito. [devlog § banda PVC](../../../docs/devlog.md)
- En madera `YIELD_MPA` tabula el MOR (rotura), no un límite elástico: el «FS» es contra rotura
  y el criterio es FS ≥ 4 (σ_adm = MOR/4), no ≥ 1.5 como en acero.
- **Cómo se VE un material** (`apariencia.py`, tabla D5): fuente única de los dos
  renderizadores. Un material de catálogo o del registro nuevo necesita su acabado
  (`tests/test_apariencia.py` lo exige); tras editar la tabla, `python -B
  scripts/acabados_ui.py --escribir` regenera la copia del visor. La palabra de carpintería sólo
  pinta madera en el vertical madera (la guarda de `resolve_material`). El color asignado
  (`Document.colors`) define el albedo SÓLO en un acabado `pintable` (pintado, caucho, PVC,
  madera, cartón); en un metal manda el albedo de la tabla. Acero liso por rol: cadena →
  pavonado, eje/piñón → mecanizado, rodillo/tambor (y su tubo) → galvanizado. La `textura` es
  SÓLO del visor: `apariencia()` no la pasa a VTK. [visor-realista](../../../docs/plans/visor-realista.md)

## Chapa (`sheetmetal.py`)

- `k_factor=None` = K POR MATERIAL (`K_FACTOR_BY_MATERIAL`), resuelto en la capa API con
  `resolve_material`.
- Features en pestaña: `u` a lo largo del pliegue ALINEADA AL EJE MUNDIAL (0 = centro), `v` desde
  el BORDE LIBRE: la métrica en que 3D y desplegado coinciden sin conocer el radio. Una feature
  que invade la zona de pliegue se rechaza con el dominio válido. Al flat: offset padre =
  `BA_p + (altura − OSSB_p) − v`, hijo = `strip_total − v`.
- La vía simple (lados/altura) se NORMALIZA a `flaps`: un solo camino, flat byte-idéntico (test
  de igualdad exacta). `child` de un nivel; el pliegue hijo queda vivo (sin fillet).
  [devlog § V5.5](../../../docs/devlog.md)

## Ingeniería (`engineering/`)

- **Un cálculo NO filtra por `visible`**: ocultar es estado de vista (`Document.hidden`), no saca
  la pieza de la máquina. Las masas van con `include_hidden=True`; la puerta de entrega y la BOM
  aún filtran ([backlog](../../../docs/backlog.md) § Validación).
- Toda verificación cuantitativa lleva bloque `calc` {titulo, entradas, formula, sustitucion,
  resultado, criterio, fs, norma}. Las que tienen norma citan la norma real; sin norma aplicable
  se escribe «criterio de diseño», nunca una cita inventada. Eje: σ_adm = 0.5·σy (más estricto que
  ASME B106.1M); flecha L/240 (AISC).
  [V7.2b](../../../docs/plans/V7.2b-barrida-residuos.md) · [V7.2c](../../../docs/plans/V7.2c-fixes-re-auditoria.md)
- Fits ISO 286 (`fits.py`): tablas IT5-11 y desviaciones de eje 1–500 mm; agujeros por las reglas
  de la norma; K-P sólo grados 6-7; el bore de rodamiento es ISO 492, no 286.
  `SEAT_RECOMMENDATIONS` por montaje: inserto UC → eje h7 que DESLIZA; anillo giratorio
  prensado → k6; eje FIJO (anillo interior estacionario, p. ej. el tensor) → g6/h6. La regla
  «asiento ISO 286» (`report_ajustes.py`) detecta pares eje ↔ rodamiento (fastener/junta/mate
  concéntrico + Ø coincidente): sin fit → aviso; k6 en inserto UC → ERROR. [devlog § V5.4](../../../docs/devlog.md)
- El fit del EJE va en el NOMBRE («Eje motriz Ø35 h7») y el del taladro en `drill_hole.fit`; los
  planos los rotulan solos (mapas por pieza en [services](../services/CLAUDE.md)).
- Roscas (`threads.py`): `drill_hole.thread` taladra a la broca de machuelado PUBLICADA (M8 →
  Ø6.8; `diameter` se ignora); fit y thread son excluyentes (la rosca interior es 6H fija). Las
  roscas exteriores, fuera de alcance (por nombre, como los fits). [devlog § V5.7](../../../docs/devlog.md)
- Fijación de taller (`fijacion.py`, puro; criterios de `join_bolted` en
  [commands](../commands/CLAUDE.md)): perno DIN 933 con L ≥ agarre + tuerca + 2 pasos (el largo de
  catálogo o error, sin respaldo a 200); sin acceso por detrás (el ala de un perfil abierto SÍ lo
  tiene) → remache ciego DIN 7337 (M6→Ø4.8, M8→Ø6.4; más grande = error, no hay ciega de
  catálogo); base de madera → DIN 571 con ≥ 2/3 dentro y la punta ≥ 2 mm antes de la cara de
  atrás. Sus tablas son espejo de `112_fijacion_ciega.yaml`/`113_tirafondos_hex.yaml`. Madera =
  `materials.es_madera` sobre `resolve_material_vertical` (la guarda del vertical).
  [union-en-perfil-hueco](../../../docs/plans/union-en-perfil-hueco.md)
- Pernos (`bolts.py`): broca de paso ISO 273 serie media (M12 → Ø13.5). Par de apriete
  `tightening_torque_nm` = K·d·(0.7·A_s·R_y) con `TORQUE_K` por condición (seco/zincado/lubricado)
  + `wrench_size_mm`. [devlog § E5](../../../docs/devlog.md)
- `loads.hanging_load_kg`: la carga de una unión = la masa que pierde tierra al quitar su arista;
  redundante → None. `mass`: catálogo pesa por FICHA, a medida volumen × densidad.
- `report.structure_engineering_check` (universal: pernos, soldaduras, L10, pandeo, vuelco): las
  uniones sin dimensionar se AGREGAN en una regla-resumen; redundante + dimensionada = ok con
  nota (la redundancia es favorable y no accionable). `report.py` es orquestador y ruta vieja
  (re-exporta por identidad): una verificación nueva va a su módulo `report_*`, no a `report.py`
  ([plan](../../../docs/plans/partir-nucleo-congelado-ii.md) D3).
- Viga continua (`viga_continua.py`, Hermite con cargas consistentes = exacta, no aproximada):
  cargas y flechas + hacia ABAJO, reacciones + hacia ARRIBA (negativa = tracción, no se
  recorta). Secciones (`secciones.py`) en ejes LOCALES del builder (`i_x` = canto en Y): tabla
  de norma si los params calzan; HSS A500 con t = 0.93·t_nom y r = 2t (AISC; el `rect_tube_*`
  de `structural.py` es arista viva y nominal); perfil ranurado → `None` (`SIN_SECCION`), jamás
  la inercia del modelo macizo. La sección se busca por `Component.familia`/`params`. Un ángulo L
  flecta LIBRE por sus ejes principales (`angulo_libre`; el eje geométrico va de referencia en la
  hipótesis); criterio en `viga_bastidor.py` (vano L/240, voladizo 2·Lv/240, σ ≤ 0.6·fy).
  [flecha-de-bastidor](../../../docs/plans/flecha-de-bastidor.md)
- Instalación (`installation.anchor_loads`): reparto ELÁSTICO de grupo por apoyo; con N > 3 es
  hiperestático y la hipótesis se DECLARA; un R_i negativo se publica como TRACCIÓN, jamás se
  recorta a cero. [V7.6](../../../docs/plans/V7.6-e2-fino.md)

## Stack-up (`engineering/stackup.py`)

- Motor PURO peor caso + RSS (√Σt²) de una cadena 1D. Cada eslabón con tolerancia de UNA fuente:
  `{pm}`, `{fit: "h7"}` (banda ISO 286 asimétrica vía `fit_limits`), `{iso2768: "m"}` o
  `{lim: [lo, hi]}`; veredicto contra `{min_mm | max_mm | entre}`. `iso2768_linear` es la tabla
  ISO 2768-1 (el número del «ISO 2768-mK» del cajetín).
- Las cadenas DECLARADAS son metadato (`Document.stackups`, raíz § Metadato ≠ comando). Un
  eslabón `{id, eje}` mide el bbox VIVO; `nominal_mm: "=expr"` sigue las variables. Evaluación y
  cadenas auto de pernos: [services](../services/CLAUDE.md); el rollback del PUT,
  [api](../api/CLAUDE.md). [V7.3](../../../docs/plans/V7.3-stackup-cadenas-cotas.md)
- `bolt_pattern_budget(flotante=)`: perno + TUERCA (pasante) → holgura completa; perno fijo →
  la mitad. Declarar flotante sin tuerca sería optimista.

## Reglas de conveyor (`rules.py`) y requisitos

- `rules.py` es orquestador de `conveyor_engineering_check` y ruta vieja (re-exporta por
  identidad, `tests/test_rutas_viejas.py`). Una regla nueva va a su bloque `rules_faja_*` y se
  llama en su lugar, con el estado en `ContextoFaja` (lo que un bloque produce vuelve por
  `return`); `tests/test_reglas_faja_congeladas.py` congela tres salidas texto a texto.
  [plan](../../../docs/plans/partir-nucleo-congelado-ii.md) (F3)
- `detect_conveyor` se enriquece con VARIABLES, nombres y specs de catálogo (reconoce
  `motorreductores_sinfin`: η = 0.75 sinfín vs 0.85 helicoidal). Un transportador de rodillos a
  mano (tubo redondo de catálogo con eje, bastidor de ángulo) lo reconoce `rodillos_a_mano.py`
  por catálogo y geometría, sólo con motorreductor. Su capacidad sale de lo MEDIDO
  (`rodillos_a_mano_medida.py`: eje con el Ø que TRABAJA —el menor del vano, no el de su caja—,
  apoyos —también el ala a tope de un eje de rosca hembra con su perno DECLARADO: quien llame a
  `detect_conveyor` le pasa `doc.fasteners`—, rodamientos de catálogo o nombrados con su serie):
  L10 + σ del eje + desalineación eje↔tubo en el rodamiento (≤ 10′, el tubo sigue la cuerda), y el
  motor con el método de la plantilla («motor», no «motorización»); sin un dato real, AVISO con
  el motivo, nunca una capacidad inventada. [defectos](../../../docs/defectos.md) (F6)
- El Ø del tambor de una faja a mano (velocidad, par) es el MEDIDO de lo redondo y largo
  (`diametro_tambor.py`: lo motriz primero, sin ejes, tapas ni guardas por rol), nunca el lado
  menor de la caja de lo que se llame «tambor». (F6)
- «Ancho útil» (`ancho_util.py`): rodillos = ancho − 2 largueros; BANDA = el ancho MEDIDO de la
  banda (rol) y, si es menor, la luz entre guías laterales que suben sobre ella (los largueros de
  una faja de banda van por fuera: no se restan).
- Método de arrastre POR CONSTRUCCIÓN (`soporte` derivado del modelo): cama/mesa → CEMA
  slider-bed μ = 0.33 + par de arranque 1.6× (`engineering/belt.py`); rodillos portantes → ISO
  5048/DIN 22101 (`iso5048.py`, C(L); L < 80 m es interpolación referencial). El μ = 0.06 de
  rodadura es SÓLO para rodillos.
- Adherencia del tambor motriz (Euler-Eytelwein): μ 0.35 engomado / 0.25 liso por NOMBRE del
  tambor; FS sólo con `t2_n` declarado (no se inventa la tensión del tensor). `tiene_tensor` NO
  sale del nombre: lo pone `services/engineering_rules.inherit_tensor` con el tensor RECONOCIDO.
  [devlog § V5.10](../../../docs/devlog.md)
- **Puerta de publicación** (`calidad/`, puro; insumos en [services](../services/CLAUDE.md)): cada
  control devuelve `item.Item` (OK | FALLA | SIN_EVALUAR | NO_APLICA, con evidencia). Largos de
  perno: `largos_perno.py` (serie ISO + rango del YAML).
  [puerta-de-publicacion](../../../docs/plans/puerta-de-publicacion.md)
- `calidad/registro.py` es LA regla (D1, D14): ítems GENERALES por modo de falla
  (`transmision_flexible.tension`, `union.agarre`…), nunca de un mecanismo; una máquina nueva suma
  un detector (`services/puerta_hechos.py`) o un evaluador, no un ítem. NO_APLICA sólo por
  `aplica_si`; los ids de F2/F3 entran por el `mapa` de su `Fuente` (servicio `(doc, contexto=)`,
  UNA vez por puerta; puede dar `riesgos`: la tabla ISO 12100 del resultado). Cambiar un
  ítem, umbral o `aplica_si` sube `VERSION_REGISTRO`. Los controles de lo existente: `puerta.py`.
  Una extensión suma los suyos (`Extension.puerta`, ids «prefijo.x») en `DE_EXTENSION`: quien
  corre la puerta entera pasa `vigente()` a `reunir` y a `evaluar`, y `version(registro)` los
  firma («6+nombre.v»); `evaluar(registro=None)` sigue siendo sólo el núcleo (testigos).
  [plan](../../../docs/plans/nucleo-abierto-extensiones-privadas.md) (F1d)
- Un AVISO se corrige o se JUSTIFICA por escrito (`calidad/justificadas.py`, metadato
  `justificadas`: regla exacta de la evidencia, ≥ 20 caracteres de porqué), nunca se calla con una
  pieza; un ERROR jamás. Lo leen `semaforo_entrega`, `erc` y `vida.reglas`: un control nuevo que
  bloquee avisos lo lee igual. `diseno.sin_sobrantes` (`calidad/sobrantes.py`) juzga lo que mide
  `services/calidad_sobrantes.py`. [plan](../../../docs/plans/puerta-sin-sobrediseno.md) (D5–D11)
- La banda de `create_belt_conveyor` abraza el radio EXTERIOR de cada tambor (`diametro_mm/2 +
  lagging_mm`) y cada eje baja lo que crece su tambor (ramal de carga plano). Un choque DENTRO de
  un super-comando no lo ve `interference_report(exclude_pairs=same_command_pairs)`: el
  super-comando lo prueba él mismo SIN exclusiones (`tests/test_belt_conveyor.py`) y la puerta de
  publicación lo mira (D13b). Toda pieza nueva de `belt_conveyor_*.py` entra con su `Plan.union`
  (declara cada unión que toca y ancla los pies), y el bastidor lleva el material de ficha
  (`Feature.material`: «larguero» sería madera por el nombre). Toda pieza o cota nueva de un
  resguardo se mide con la puerta en varias variantes, también una GRANDE (> 12 M voxeles: el
  voxel crece y aparecen ventanas que el de 10 mm no ve). Una placa que cierra un tubo es
  «Placa de cierre…» (estructura, soldada); «Tapa…» sería guarda y pediría pernos.
  [defectos](../../../docs/defectos.md)
- La faja EN MARCHA (`ruta_faja_modelo.py`, puro): la cinta es la línea media de la SECCIÓN del
  sólido de la banda (el casco de `ruta_faja.py`, sólo sin lazo cerrado) y `fidelidad_faja.py` la
  prueba siempre contra el modelo (desvío ≤ comba CEMA hacia afuera; no entra en una pieza más que
  el sólido + 1 mm): una que falla no se publica. Comba = mín(CEMA 2 %, w·l²/8T de la tracción
  MEDIDA, holgura con lo de abajo) sólo en tramos rectos del retorno.
- `Document.requirements` (metadato): `/api/checks`, la memoria y la cotización CAEN a ellos (un
  param explícito gana) → `engineering_check()` funciona sin argumentos. Se validan en
  `requisitos.py` (`Document.set_requirements` delega; la CARGA no valida: un manifest viejo abre
  tal cual). Ficha del encargo: lo ASUMIDO entra `{"valor", "asumido"}` y se guarda PLANO + lista
  `asumidos`: todo lector de `requirements[k]` sigue viendo un escalar.
  [revision-de-taller](../../../docs/plans/revision-de-taller.md) (D1)

## Validación: interferencias, lints y puerta de entrega

- `interference_report`: candidata = pareja que PUEDE interferir según el prefiltro EXACTO de
  `interferencias_filtro.py` (reglas en su docstring): un descarte nuevo ahí tiene que ser exacto
  y entra con su caso en `tests/test_interferencias_escala.py` (contra la fuerza bruta). El
  chequeo GLOBAL (puerta de entrega, `verify`) pasa `tope=tope_global(scene)`, no el `MAX_PAIRS`
  fijo. [defectos](../../../docs/defectos.md) (F6)
- `check_interference` (booleanas OCCT) excluye pares de junta, `same_command_pairs` y el herraje
  `HARDWARE_CATS`; `interpenetration_report` mide el EXCESO sobre la pose de diseño en pares con
  junta. `HARDWARE_CATS` NO se amplía (semántica de interferencia, lista de corte y lints): el FEA
  usa `FEA_HARDWARE_CATS`. Revisa ≤ `MAX_PAIRS` parejas candidatas por página (`desde`, en el
  orden estable de la escena); si recorta, declara `parejas_candidatas`, `parejas_sin_revisar` y
  `desde_siguiente` (sin recorte ni `desde`, el dict de siempre) y la puerta dice cuántas
  quedaron sin revisar.
- `lints.predelivery_lints`: «barreno de paso Ø7-22 sin perno en su eje» y «pieza sin grupo NI
  unión declarada» (excluye guías, superficies y herraje). Reconoce tornillería a medida por
  NOMBRE (`_is_bolt`). Todo matcher por nombre nuevo lleva guarda de anclaje/plurales y un test
  con el nombre REAL del modelo. «Soldadura imposible» (`lint_soldadura.py`: madera, caucho, PVC…
  o acero con aluminio) es el único lint ERROR: `delivery.py` lo pone en bloqueantes (ROJO); sin
  `material_vertical`, asume acero (no inventa una madera por el nombre).
- Perfiles abiertos: `r1`/`r2`/`pendiente_ala` son datos de NORMA que el builder no lee (la
  geometría sigue prismática → sin bump); `acuerdos.py` deriva la zona plana y el lint
  «asiento fuera de la zona plana» (`lint_asiento.py`) lee los taladros de la GEOMETRÍA, no de
  los comandos (`join_bolted` corta sin `drill_hole`). Su marco sale de las ANCLAS por familia
  (`perfiles_abiertos.py`, sobreviven al taladro) y, sin ellas, del bbox. Una función de anclas
  que declara `specs` los recibe del loader (las zonas planas dependen de r1, que el builder no
  lee). [plan](../../../docs/plans/perfiles-con-acuerdo.md)
- `delivery.py` es un agregador PURO → semáforo VERDE/AMARILLO/ROJO: interferencias en diseño +
  sujeción DECLARADA (sin autodetect) + lints + integridad/suprimidos + colisión en las poses de
  REPOSO (el tránsito lo valida `scan_motion`; insumos: [services](../services/CLAUDE.md)) +
  gravedad opt-in. ERC, acceso de herramienta y escenarios de prueba (V8.3 D14) entran SÓLO si existen: sin ellos,
  la puerta da lo de siempre. Las reglas de una extensión (`Extension.entrega`,
  `entrega_extension.py`) van al final con `id` y `origen`; sólo con ellas sale `version_bateria`
  («3+nombre.v»: `VERSION_BATERIA` sube si cambia un chequeo del núcleo).
- **¿Entra la lengüeta?** (`enclavamiento.py`, puro; lectura y emparejamiento en
  `services/enclavamientos.py`): con el resguardo cerrado la lengüeta de un interruptor de
  actuador separado está en su ranura (`specs.insercion_min_mm` de la ficha ≤ profundidad ≤
  fondo, su sección dentro de la de la ranura) y, con junta, abierto está fuera; ROJO en la
  puerta si no. Marco SÓLO de las anclas `ranura`/`punta` + `fijacion_1/2` y las cotas del builder,
  nunca del bbox. [mandos-de-seguridad](../../../docs/plans/mandos-de-seguridad.md) (F2b)
  [plan](../../../docs/plans/puntos-de-extension-entregables.md)
- Lo que no puede correr va en `no_aplica`: jamás cuenta verde. Un asiento ≤ `EXCESS_TOL_MM3`
  (`checks.py`) se tolera y se DECLARA (`contactos_tolerados`). Tornillería flotante = AVISO, no
  ROJO (no es nodo estructural).
- Exclusiones UNIFICADAS diseño + pose: par con fasten declarado = contacto firmado; tornillería
  a medida = asentada (si no, un solape declarado reaparece en pose).
- **¿Entra la llave?** (`acceso_herramienta.py`): la tuerca/cabeza se reconoce por GEOMETRÍA
  (`fijadores_geom.py`: 3 pares de caras a 60°), no por catálogo; sus fantasmas
  (`fantasmas_herramienta.py`, medidas en `herramientas.py`) se cruzan con los vecinos. La pieza
  de asiento NO se excluye entera (el ala que estorba suele ser de ella): los fantasmas arrancan
  a 1 mm del asiento. Ninguna libre = ROJO en la puerta, sólo boca = aviso, sin hexágono = no
  evaluado. Un sólido con VARIOS hexágonos coaxiales (perno + tuerca fundidos) son varios
  fijadores (`reconocer_fijadores`). Sin hexágono: un remache de catálogo (`herramienta:
  remachadora`) se lee por su cilindro mayor y se le cruza la remachadora coaxial; un DIN 571
  (`llave: true`) entra como tornillería de llave. [plan](../../../docs/plans/acceso-de-herramienta.md)
- `MIN_SOLIDOS_SUJECION` también dispara la alarma ambiental `aviso_estructura` de toda mutación
  ([api](../api/CLAUDE.md)). [V6.9](../../../docs/plans/V6.9-puerta-de-entrega.md)
- **Puerta de publicación — seguridad y reparabilidad** (`seguridad/`, `reparabilidad.py`; OCCT en
  `services/calidad_*.py`): peligros ISO 12100 derivados del modelo, sondas ISO 13857 (la banda no
  es peligro ni se atraviesa; el rodillo portante liso no es peligro), guarda atornillada, desgaste
  sin soldar y desmontable, banda montable. Entran por la fuente «seguridad» (`seguridad.electrico`
  se descarta: es `riesgos.electrico`). Las sondas rectas no ven lo que se alcanza doblando el
  brazo: `alcance.py` + `services/calidad_codo.py` (la mano ≤ 230 mm, juzgada por
  `sondas.veredicto`). Umbrales y calibración: [plan](../../../docs/plans/puerta-de-publicacion.md)
  § F3 y § F6. Con el sentido de marcha conocido sólo se sondea la cuña de ENTRADA de cada
  tambor (`seguridad/cuna_entrada.py` sobre la línea media del lazo; el sentido, en
  `services/calidad_cunas.py`: escenario > requisito `sentido_transporte` > plantilla; con
  `reversible` o sin fuente, las dos): nunca del nombre ni del giro de la junta.
  [plan](../../../docs/plans/puerta-sin-sobrediseno.md) (D3–D4)
- **Distancia al borde de un agujero de perno** (`borde_agujero.py`, EN 1993-1-8 tabla 3.3): la
  MISMA medida para la puerta (`calidad/bordes.py`) y `join_bolted` criterio 5. Canto = donde la
  pieza tiene el espesor de la chapa (no la esquina de un tubo, el talón de un ángulo ni un eje);
  el agujero de otro perno es paso. La tabla es de CHAPAS: una barra maciza (eje, barra cuadrada:
  t ≥ 1,5·d0 y W ≤ 1,25·t) sale como `barra` y, roscada, se juzga por su rosca enganchada. Medir
  sobre la geometría, nunca sobre la huella de cajas. § F6.
