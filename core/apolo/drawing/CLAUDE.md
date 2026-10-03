# Planos y entregables (`core/apolo/drawing/`)

Compositor `SheetModel` → SVG/PDF/DXF (HLR) y los entregables en papel: juego de planos, manual
de ensamblaje, memoria de cálculo, cotización, lámina de instalación y DWG. Lo transversal
(locks, log, flujo de trabajo) está en el [CLAUDE.md raíz](../../../CLAUDE.md); lo común del
backend, en [core/apolo](../CLAUDE.md).

⚠️ Los mapas por pieza que alimentan las láminas (fits, datums, GD&T, tolerancias justificadas,
datos de instalación) se calculan en `api/main.py`: sus reglas están en [api](../api/CLAUDE.md).

## Mapa

- `sheet.py::compose_sheet` (una lámina), `sheetset.py::sheet_set` (juego: conjunto con DESPIECE
  + globos + cédula de herraje + una lámina por pieza + lista de corte), `assembly_manual.py`,
  `calc_report.py` (memoria A4), `quote.py` (cotización), `installation.py`, `dwg.py`,
  `process.py`. Planos por intención: `POST /api/drawing/spec` (tool `drawing`). Detector de
  solapes de texto: `scripts/_check_overlaps.py`.
- Entregables honestos: la memoria trae fórmula, sustitución, FS y norma por verificación; el
  costeo (`library/costing.py`) declara la fuente de cada fila (specs.cost / estimación peso ×
  material × 3 / fabricación × 2.5). En el bloque «HIPÓTESIS Y ALCANCE» (tope 18 líneas) el
  alcance y la nota del analista van al FINAL para que el corte no los mate.
- DWG: DXF → DWG R2018 con ODA File Converter (`ezdxf.addons.odafc`); `_discover()` busca la
  carpeta VERSIONADA del instalador; sin ODA → 400 amable con la URL. DWG no es multipágina: el
  juego sale como ZIP con un DWG por lámina. [devlog § V5.9](../../../docs/devlog.md)

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
- Varias láminas con el mismo nombre llevan sufijo «(k/n)»; el cajetín corta a 34 caracteres, así
  que se recorta el NOMBRE para que el sufijo sobreviva (la local de ese bloque no puede llamarse
  `base`: pisa la de `page_meta`). La columna «Hoja» del despiece mapea por FILA `(_rep, dims)`:
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
  COG, holguras, suministro), `_installation_data` en [api](../api/CLAUDE.md).
