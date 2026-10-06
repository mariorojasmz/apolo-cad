# Library (`core/apolo/library/`)

Catálogo, builders, materiales, chapa, bastidores y cálculo de ingeniería (`engineering/`). Lo
transversal (fronteras de paquete, locks, disciplina paramétrica) está en el
[CLAUDE.md raíz](../../../CLAUDE.md); lo común del backend, en [core/apolo](../CLAUDE.md).

## Catálogo y builders

- Para agregar partes: editar/crear YAML en `data/` (el prefijo numérico ordena); builder nuevo
  sólo si la geometría no existe. `param_keys` lee del VARIANT (no de `specs_common`); el loader
  vuelca cualquier clave extra del variant a `specs`. Editar sólo YAML no recarga el worker (raíz).
- Biblioteca paramétrica > STEP de fabricante (sólo para la compra puntual). `cost`,
  `cost_por_m` y `COST_PER_KG_USD` son REFERENCIALES: actualizar con proveedor para cotizar firme.
- `position` = centro del bbox; un builder con origen propio coloca su ORIGEN LOCAL en
  `position` (p. ej. el barreno del NMRV, builder `worm_gearmotor`). Los perfiles se extruyen en
  Z (rotar 90° sobre Y → larguero en X).
- Builders: todo término empieza con `Pos(...) *` (un `Rotation(...) * shape` pelado da
  `ValueError: other must be a list of Locations`); las partes de un mismo sólido SOLAPAN
  0.5–8 mm (tangentes → Compound; disjuntas → ShapeList sin `.volume`); `build_component(ref, L)`
  ignora `L` si el componente no es `cuttable`.
- Ingletes (`miter.py`, `weldment.py`, `frame.py`): corte por el plano BISECTOR del nodo (V
  exacto = A·span, ancla de tests). Weldment = marcos sup/inf a 45° + postes a tope; frame =
  bisectriz sólo en nodos de grado 2 (colineal → recto; α > 75° o grado ≠ 2 → tope).
  `Feature.miter` → BOM/lista de corte «∠45°/45°» y `cut_length` = longitud EXTERIOR.
  [devlog § V5.8](../../../docs/devlog.md)

## Materiales (`materials.py`)

- `resolve_material`: override → catálogo → heurística por nombre → default del VERTICAL
  (`set_vertical('carpinteria')` = madera; si no, acero).
- `_norm` devuelve la primera clave que sea SUBCADENA: las especies van ANTES de `"madera"` en
  los dicts («madera copaiba» → copaiba).
- La heurística por nombre muerde: «larguero» es palabra de madera (`_WOOD_WORDS`). Quien
  re-resuelve el material de una pieza ya resuelta le pasa el `material` que ya tiene.
  [V7.5](../../../docs/plans/V7.5-e22-datum-funcional.md)
- En madera `YIELD_MPA` tabula el MOR (rotura), no un límite elástico: el «FS» es contra rotura
  y el criterio es FS ≥ 4 (σ_adm = MOR/4), no ≥ 1.5 como en acero.

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
  la pieza de la máquina (ocultar banda + tambor del 38 borraba la faja de la memoria). Las masas
  van con `include_hidden=True`; la puerta de entrega y la BOM aún filtran
  ([backlog](../../../docs/backlog.md) § Validación).
- Toda verificación cuantitativa lleva bloque `calc` {titulo, entradas, formula, sustitucion,
  resultado, criterio, fs, norma}. Las 16 con norma (10 en `rules.py`, 6 en `report.py`) citan la
  norma real; sin norma aplicable se escribe «criterio de diseño», nunca una cita inventada. Eje:
  σ_adm = 0.5·σy (más estricto que ASME B106.1M); flecha L/240 (AISC).
  [V7.2b](../../../docs/plans/V7.2b-barrida-residuos.md) · [V7.2c](../../../docs/plans/V7.2c-fixes-re-auditoria.md)
- Fits ISO 286 (`fits.py`): tablas IT5-11 y desviaciones de eje 1–500 mm; agujeros por las reglas
  de la norma; K-P sólo grados 6-7; el bore de rodamiento es ISO 492, no 286.
  `SEAT_RECOMMENDATIONS` por montaje: inserto UC → eje h7 que DESLIZA; anillo giratorio
  prensado → k6; eje FIJO (anillo interior estacionario, p. ej. el tensor) → g6/h6. La regla
  «asiento ISO 286» (`report.py`) detecta pares eje ↔ rodamiento (fastener/junta/mate concéntrico
  + Ø coincidente): sin fit → aviso; k6 en inserto UC → ERROR. [devlog § V5.4](../../../docs/devlog.md)
- El fit del EJE va en el NOMBRE («Eje motriz Ø35 h7») y el del taladro en `drill_hole.fit`; los
  planos los rotulan solos (mapas por pieza en [services](../services/CLAUDE.md)).
- Roscas (`threads.py`): `drill_hole.thread` taladra a la broca de machuelado PUBLICADA (M8 →
  Ø6.8; `diameter` se ignora); fit y thread son excluyentes (la rosca interior es 6H fija). Las
  roscas exteriores, fuera de alcance (por nombre, como los fits). [devlog § V5.7](../../../docs/devlog.md)
- Pernos (`bolts.py`): broca de paso ISO 273 serie media (M12 → Ø13.5). Par de apriete
  `tightening_torque_nm` = K·d·(0.7·A_s·R_y) con `TORQUE_K` por condición (seco/zincado/lubricado)
  + `wrench_size_mm`. [devlog § E5](../../../docs/devlog.md)
- `loads.hanging_load_kg`: la carga de una unión = la masa que pierde tierra al quitar su arista;
  redundante → None. `mass`: catálogo pesa por FICHA, a medida volumen × densidad.
- `report.structure_engineering_check` (universal: pernos, soldaduras, L10, pandeo, vuelco): las
  uniones sin dimensionar se AGREGAN en una regla-resumen; redundante + dimensionada = ok con
  nota (la redundancia es favorable y no accionable).
- Instalación (`installation.anchor_loads`): reparto ELÁSTICO de grupo por apoyo; con N > 3 es
  hiperestático y la hipótesis se DECLARA; un R_i negativo se publica como TRACCIÓN, jamás se
  recorta a cero. [V7.6](../../../docs/plans/V7.6-e2-fino.md)

## Stack-up (`engineering/stackup.py`)

- Motor PURO peor caso + RSS (√Σt²) de una cadena 1D. Cada eslabón con tolerancia de UNA fuente:
  `{pm}`, `{fit: "h7"}` (banda ISO 286 asimétrica vía `fit_limits`), `{iso2768: "m"}` o
  `{lim: [lo, hi]}`; veredicto contra `{min_mm | max_mm | entre}`. `iso2768_linear` es la tabla
  ISO 2768-1 (el número del «ISO 2768-mK» del cajetín).
- Las cadenas DECLARADAS son metadato (`Document.stackups`) con endpoint, NO comando: meterlas al
  log rompería la invariante de checkpoints (raíz). Un eslabón `{id, eje}` mide el bbox VIVO;
  `nominal_mm: "=expr"` sigue las variables. Evaluación y cadenas auto de pernos:
  [services](../services/CLAUDE.md); el rollback del PUT, [api](../api/CLAUDE.md).
  [V7.3](../../../docs/plans/V7.3-stackup-cadenas-cotas.md)
- `bolt_pattern_budget(flotante=)`: perno + TUERCA (pasante) → holgura completa; perno fijo →
  la mitad. Declarar flotante sin tuerca sería optimista.

## Reglas de conveyor (`rules.py`) y requisitos

- `detect_conveyor` se enriquece con VARIABLES, nombres y specs de catálogo (reconoce
  `motorreductores_sinfin`: η = 0.75 sinfín vs 0.85 helicoidal).
- Método de arrastre POR CONSTRUCCIÓN (`soporte` derivado del modelo): cama/mesa → CEMA
  slider-bed μ = 0.33 + par de arranque 1.6× (`engineering/belt.py`); rodillos portantes → ISO
  5048/DIN 22101 (`iso5048.py`, C(L); L < 80 m es interpolación referencial). El μ = 0.06 de
  rodadura es SÓLO para rodillos.
- Adherencia del tambor motriz (Euler-Eytelwein): μ 0.35 engomado / 0.25 liso por NOMBRE del
  tambor; FS sólo con `t2_n` declarado (no se inventa la tensión del tensor).
  [devlog § V5.10](../../../docs/devlog.md)
- `Document.requirements` (metadato): `/api/checks`, la memoria y la cotización CAEN a ellos (un
  param explícito gana) → `engineering_check()` funciona sin argumentos.

## Validación: interferencias, lints y puerta de entrega

- `check_interference` (booleanas OCCT) excluye pares de junta, `same_command_pairs` y el herraje
  `HARDWARE_CATS`; `interpenetration_report` mide el EXCESO sobre la pose de diseño en pares con
  junta. `HARDWARE_CATS` NO se amplía (semántica de interferencia, lista de corte y lints): el FEA
  usa `FEA_HARDWARE_CATS`.
- `lints.predelivery_lints`: «barreno de paso Ø7-22 sin perno en su eje» y «pieza sin grupo NI
  unión declarada» (excluye guías, superficies y herraje). Reconoce tornillería a medida por
  NOMBRE (`_is_bolt`). Todo matcher por nombre nuevo lleva guarda de anclaje/plurales y un test
  con el nombre REAL del modelo.
- `delivery.py` es un agregador PURO → semáforo VERDE/AMARILLO/ROJO: interferencias en diseño +
  sujeción DECLARADA (soundness sin autodetect) + lints + integridad/suprimidos + colisión EN POSE
  en los fotogramas de REPOSO de los estudios (extremos + dwells; el tránsito lo valida
  `scan_motion`) + gravedad opt-in.
- Lo que no puede correr va en `no_aplica`: jamás cuenta verde. Un asiento ≤ `EXCESS_TOL_MM3`
  (`checks.py`) se tolera y se DECLARA (`contactos_tolerados`). Tornillería flotante = AVISO, no
  ROJO (no es nodo estructural).
- Exclusiones UNIFICADAS diseño + pose: par con fasten declarado = contacto firmado; tornillería
  a medida = asentada. Sin unificar, un solape declarado reaparecía como «colisión nueva» en pose.
- `MIN_SOLIDOS_SUJECION` también dispara la alarma ambiental `aviso_estructura` de toda mutación
  ([api](../api/CLAUDE.md)). [V6.9](../../../docs/plans/V6.9-puerta-de-entrega.md)
