# Planos y entregables (`core/apolo/drawing/`)

Compositor `SheetModel` → SVG/PDF/DXF (HLR) y los entregables en papel: juego de planos, manual
de ensamblaje, memoria de cálculo, cotización, lámina de instalación y DWG. Lo transversal
(locks, log, flujo de trabajo) está en el [CLAUDE.md raíz](../../../CLAUDE.md); lo común del
backend, en [core/apolo](../CLAUDE.md).

⚠️ Los mapas por pieza que alimentan las láminas (fits, datums, GD&T, tolerancias justificadas,
datos de instalación) se calculan en `services/` (`drawing_maps.py`, `installation_data.py`): sus
reglas están en [services](../services/CLAUDE.md).

## Mapa

- **`sheet.py` es fachada + orquestador** ([partir-nucleo-congelado-ii](../../../docs/plans/partir-nucleo-congelado-ii.md)
  F4): primitivas y constantes en `sheet_primitivas`, auxiliares en `sheet_auxiliares` /
  `sheet_anotaciones`; `compose_sheet` llama EN ORDEN a bloques de `sheet_vistas`, `sheet_cotas`,
  `sheet_tablas` y `sheet_cajetin`, con el estado en `LaminaEnCurso` (`sheet_lamina`). Lo nuevo
  va a su bloque (un local que lee otro bloque = campo + `return`); el orden de las primitivas
  es parte del contrato (`tests/test_laminas_congeladas.py`). `apolo.drawing.sheet` sirve por
  identidad todo nombre de antes (`tests/test_rutas_viejas.py`: lo importa la extensión privada).
- `sheet.py::compose_sheet` (una lámina), `sheetset.py::sheet_set` (juego: conjunto con DESPIECE
  + globos + cédula de herraje + una lámina por pieza + lista de corte), `assembly_manual.py`,
  `calc_report.py` (memoria A4), `quote.py` (cotización), `installation.py`, `dwg.py`,
  `process.py`. Planos por intención: `POST /api/drawing/spec` (tool `drawing`). Detector de
  solapes de texto: `scripts/_check_overlaps.py`.
- El veredicto de la memoria (`calc_report.veredicto`) lo lee también la puerta de publicación
  sin componer el PDF: «NO CONFORME» bloquea la publicación; las reglas, de `services/memoria_reglas.py`.
- Entregables honestos: la memoria trae fórmula, sustitución, FS y norma por verificación; el
  costeo (`library/costing.py`) declara la fuente de cada fila (specs.cost / estimación peso ×
  material × 3 / fabricación × 2.5). En el bloque «HIPÓTESIS Y ALCANCE» el alcance y la nota
  del analista van al FINAL: si la columna no entra, baja de escala antes que cortarlos.
- **Una tabla nueva de un entregable va por `tabla.py`** (`hojas_tabla`), no por `_table_sheet`
  (anchos y filas fijos: la celda que no cabe va en dos renglones más chicos): ancho de columna
  por CONTENIDO medido con la fuente del PDF, texto partido en líneas (nunca recortado) y
  paginación por altura sobre el cajetín. La
  cotización la usa (detalle y «AVISOS DE COBRO», con el costeo de `services/cobros.py`); su test
  renderiza cada hoja y exige que ningún texto salga de su celda.
  [V8.1](../../../docs/plans/V8.1-modelo-electrico.md) (F4c)
- **Notas de la cotización**: las del núcleo (`quote._notas_nucleo`, con id) no se quitan ni
  cambian de partición; una fuente sólo ACOTA `nucleo.alcance`/`nucleo.validez` (en su lugar, un
  dueño por nota; las de honestidad nunca) y el alcance sin acotar sale de lo que `incluye` lo
  cobrado. Título y bloque de cliente: `services/identificacion.py` (proyecto → extensión →
  nombre sin «(copia)»; la fuente al pie). Nada interno al papel: la «Ref» de una fila de
  extensión es su `rotulo` (sin él, el id), el cajetín de la cotización pasa `numero_rotulo`
  (los planos no: «Plano») y el producto sale por `requisitos.producto_legible`.
  [cotizacion-identificada](../../../docs/plans/cotizacion-identificada-y-ajustes-por-escenario.md)
  Las de una extensión (`costeo["notas"]`) van detrás, partidas por ancho medido y
  ENTERAS, por `notas_cotizacion.py`: lo que no cabe a la izquierda del cajetín sigue en «NOTAS
  (continuación)», tras los avisos (que el núcleo nombra «hoja 2») y antes del detalle.
  `tests/test_cotizacion_notas.py` congela costeo y hojas sin extensiones.
  [pedidos-de-extensiones](../../../docs/plans/pedidos-de-extensiones.md) (F5)
- **Cajetín común** (`titleblock.py`): ningún texto se corta a N caracteres; se mide
  (`titleblock.encajar`: renglones o tamaño, nunca bajo `TAM_MIN`; «…» sólo de último recurso) y
  quien apoya algo encima lee la tabla de revisiones de `alto_revisiones` (una descripción larga
  hace crecer su fila). `tests/test_cajetin.py` exige que nada se pise ni cruce una línea.
  [V8.9](../../../docs/plans/V8.9-neumatica.md) (pendiente 10)
- **Ningún `[:N]` sobre texto visible en un papel** (`texto_medido.py`): celda de alto fijo →
  `celda`/`celda_fila` (un renglón o dos más chicos; la fila no crece); texto corrido →
  `Parrafo` + `columna` hasta el `piso` (`tabla.piso_tabla`: el cajetín y sus revisiones); lo que
  no entra en la hoja sigue en otra o dice «… y N más». Un texto que cabe sale tal cual (`partir`
  junta los espacios dobles). `tests/test_cortes_fijos.py`. [V8.9](../../../docs/plans/V8.9-neumatica.md)
  (cortes fijos). Tampoco lo corta quien da el dato (`library/`, `services/`: `installation_rows`,
  el título de `montaje.secuencia`): va entero y cada papel o el video lo encaja.
- **El SVG escribe la letra del PDF**: `font-size` = `tabla.em_mm(size)` (el em de los `size ×
  2,45 pt` de `pdf.py`) con DejaVu Sans (Verdana de respaldo); `tests/test_letra_svg.py` mide el
  ancho en los dos. [V8.9](../../../docs/plans/V8.9-neumatica.md) (letra del SVG)
- **Trazos de esquema** (`esquema.py`, para una extensión que dibuja esquemas): `kind`
  `simbolo` (negro sin relleno) y `simbolo_lleno` (punto de unión, flecha) en `Line`, `Circle` y
  `Polygon`, con un solo grosor (0,35 mm, criterio declarado); en DXF, capa `ESQUEMA` sólo si se
  usa. Un estilo nuevo en un exportador no puede cambiar lo de antes: `tests/test_trazos_esquema.py`
  congela la firma de SVG, PDF y DXF de una lámina mecánica.
  [puntos-de-extension-entregables](../../../docs/plans/puntos-de-extension-entregables.md) (D6)
- **Esquema neumático ISO 1219** (`neumatica/`, tool `drawing` con `esquema: "neumatico"`): recibe
  datos puros (`CircuitoAire`, los arma `services/neumatica_esquema.py`); un símbolo nuevo dibuja con
  el `Lapiz` de `trazo.py` y devuelve su caja y sus puertos (extremo libre de un tramo, con su
  dirección), con su caso en `tests/test_simbolos_iso1219.py`; las líneas las traza `rutas.py`
  (carril por franja), nunca el símbolo. La línea de pilotaje va con el tercer estilo, `simbolo_trazos`
  (sólo `Line`). Lo «a confirmar» de la norma: [V8.9](../../../docs/plans/V8.9-neumatica.md) (F5)
- DWG: DXF → DWG R2018 con ODA File Converter (`ezdxf.addons.odafc`); `_discover()` busca la
  carpeta VERSIONADA del instalador; sin ODA → 400 amable con la URL, ANTES de componer láminas
  (`require_odafc` al entrar al endpoint: el juego gastaba ~70 s de HLR bajo `STATE_LOCK` para
  fallar). `dwg.disponible()` va en `GET /api/health` → `dwg`. DWG no es multipágina: el juego
  sale como ZIP con un DWG por lámina. [devlog § V5.9](../../../docs/devlog.md) ·
  [video-montaje-pulido](../../../docs/plans/video-montaje-pulido.md) (D5)

## Láminas por pieza: el último kilómetro

- Todo lo de taller (ISO 2768-mK, Ra, notas, datum, GD&T, cotas críticas) va SÓLO en las láminas
  por pieza del juego (`shop_notes=True`); la soldadura, sólo en el conjunto.
  [V7.2](../../../docs/plans/V7.2-ultimo-kilometro-plano.md)
- Soldadura ISO 2553: `compose_sheet(fasteners=…)` dibuja `weld_symbol` agrupando cordones por
  (garganta, longitud) → «típ. ×N», tope 6 símbolos (el resto a nota), anclados al centro del
  solape de bboxes. `DOC.fasteners` tiene que llegar por cada camino (`_sheet_model`,
  `drawing_spec`, `sheet_set`, drawingset). `throat_mm` puede ser None: el orden de grupos usa
  CENTINELAS (comparar None con float era un 500).
- ISO 2768-mK es el default de `meta["tolerance"]` + nota general por pieza; el conjunto soldado
  declara ISO 13920-BF (2768 es de mecanizado, no cubre el soldeo).
- En láminas de taller `compose_sheet` baja el `min_r_paper` de `_hole_callouts` (no silenciar un
  barreno funcional de una pieza larga a escala chica); con fit o rosca se rotula siempre. Ra 1.6 tras
  cada callout con fit ISO 286. Rosca: «4×M8 - 6H (broca Ø6.8)» + arco cosmético ISO 6410 (3/4
  de vuelta al Ø nominal); la cédula suma filas de machuelos aunque no haya herraje.
- Sin barrenos MODELADOS no hay callouts: el plano es fiel al modelo (es un gap de modelo, no un
  filtro que ajustar).
- Datum: `auto_hole_dims(datum_edges=…)` mide desde el borde de la cara FUNCIONAL y pone el «A» en
  la esquina-origen; sin cara funcional que proyecte como borde, cae a la esquina.
- GD&T: el símbolo de posición se DIBUJA (círculo + cruz): la fuente del PDF/DXF no garantiza el ⌖
  (U+2316). `_hole_callouts` devuelve cuántos marcos dibujó y la leyenda de datums sale sólo si
  hubo alguno (una leyenda huérfana confunde al taller). [V7.6](../../../docs/plans/V7.6-e2-fino.md)
- `_dim_h`/`_dim_v(tol=…)` rotulan la tolerancia de la cadena + nota «Cota crítica: cadena «…»
  (ver memoria)»: cota → cadena → veredicto, trazable.
- La Feature SINTÉTICA de cada lámina (`{"P": feat}`) lleva `material=` de la fila: sin él, el peso
  del cajetín re-resuelve por NOMBRE (una placa de acero «larguero» pesaba como madera).
  [V7.5](../../../docs/plans/V7.5-e22-datum-funcional.md)
- Varias láminas con el mismo nombre llevan sufijo «(k/n)» pegado al nombre (en `sheet_set`, una
  local no puede llamarse `base`: pisa la de `page_meta`). La columna «Hoja» del despiece mapea por FILA `(_rep, dims)`:
  un comando multi-sólido comparte `_rep`. [V7.2c](../../../docs/plans/V7.2c-fixes-re-auditoria.md)

## Proceso y acabado (`process.py`)

- `infer_process` decide por señales en orden (ver su docstring); las trampas: REVOLUCIÓN
  (`_is_revolution`: tambor/rodillo/polea por nombre, o sección ~cuadrada con fill ≈ π/4 ± 10 %)
  va ANTES de la rama de perfil esbelto; PERFIL (también un tubo hueco a medida, cota transversal
  ≥ 10 mm) va ANTES de chapa; chapa por espesor efectivo `2·V/A` (no bbox-min) y «+ plegado» sólo
  con pliegue real (fill < 0.75). «eje» no entra al regex de revolución (un eje real trae fit).
- Los matchers por nombre muerden con brackets: «Ménsula rodillo retorno» no es un rodillo
  (`_BRACKET_RE`). Todo matcher nuevo lleva guarda de bracket/anclaje y un test con el nombre REAL.
  [V7.2b](../../../docs/plans/V7.2b-barrida-residuos.md)

## Manual de ensamblaje (`assembly_manual.py`)

- Fases (`manual_fotos.py`): `extraer_manual` (bajo `STATE_LOCK`: secuencia, textos, cajetín y
  la foto id/shape de cada pieza), `teselar_manual(ex, STATE_LOCK)` (toma el lock PIEZA POR
  PIEZA; las instancias usan la malla de su definición, que `extraer_manual(definiciones=)`
  toma en la fase 1: [teselado-rapido](../../../docs/plans/teselado-rapido.md)), `fotos_manual` (fuera: UNA
  `EscenaViva` bajo `RENDER_LOCK`, cada paso sólo cambia `mostrar`; sin OpenGL, matplotlib sobre
  las MISMAS mallas con aviso en el log) y `componer_manual` (puro). Un dato nuevo de una lámina
  se extrae en la fase 1: la composición no lee la escena. `assembly_manual` es el atajo para
  quien es dueño del documento; el endpoint no lo usa.
  [manual-rapido](../../../docs/plans/manual-rapido.md)
- UNA foto 3D en una lámina (la portada de la memoria) va por `foto_escena.py`, las mismas fases:
  `extraer_foto` bajo el lock, `teselar_foto(ex, STATE_LOCK)` y `dibujar_foto` fuera; lo que la
  composición lee de OCCT (el peso, `calc_report.peso_memoria`) se calcula bajo el lock y llega
  en `meta`. Nunca `render_scene_png` bajo `STATE_LOCK` en un entregable nuevo.
- La isométrica SOMBREADA de un plano (`compose_sheet(shaded=True)`) va por `fotos_planos.py`:
  con `foto_diferida=True` (los endpoints) la lámina sólo RESERVA su lugar (`model.hueco_iso`);
  `extraer` en la misma toma del lock, `revelar(…, STATE_LOCK)` fuera: todas las fotos del juego
  en UNA `EscenaViva` (fondo blanco, recortada). Sin diferir, las tres fases de corrido.
- Con estructura DECLARADA el endpoint pasa `stages` = la secuencia de montaje de
  `services/montaje.py` (la misma del video; [services](../services/CLAUDE.md)) y `_instruction`
  suma su `union` («Se atornilla (M12) a…»). Sin ella, lo de abajo.
- `order_by_support` ordena los pasos por `detect_structure` (tierra → arriba) y fusiona los pasos
  HUÉRFANOS al sub-ensamblaje vecino; sin estructura → orden del log. Pagina por grupos si existen.
- Empate al mismo rango de soporte → `_family_order` (rodamientos/chumaceras < neutro <
  motores/reductores), con guarda de bracket POR PIEZA: una «Ménsula soporte motorreductor» no
  vuelve «motores» a toda la Estructura.
- `_family_head` (texto por familia: perfiles → soldar, herraje → apretar en cruz, chumaceras →
  montar sobre el eje) detecta tornillería a medida con un matcher ANCLADO al inicio
  (`_BOLT_START_RE`): un nombre que MENCIONA un perno no es tornillería.
- `_step_rows` ordena dentro del paso por z de la BASE (abajo → arriba).
- `_torque_note` pone par + llave por paso con la condición declarada (cálculo en
  [library](../library/CLAUDE.md)); sin métrica identificable NO emite nota: un par inventado
  rompe la unión. [devlog § E5](../../../docs/devlog.md)

## Lámina de instalación (`installation.py`)

- Compone planta de la huella, cotas entre ejes, carga por apoyo y tabla de datos de obra. La
  carga la calcula `library/engineering/installation.py`; los datos (apoyos sin tornillería,
  COG, holguras, suministro), `installation_data` en [services](../services/CLAUDE.md).
