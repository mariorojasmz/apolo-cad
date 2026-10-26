---
estado: en curso
nota: contrato de Claude con criterio delegado (2026-10-25), vetable por número; F0 medida en la escritura del contrato (base `4920db6`); F1 (`builders.py` 847 → 82), F2 (`report.py` 555 → 79) y F3 (`rules.py` 903 → 93, `conveyor_engineering_check` por extracción con corpus de 56 casos y cobertura 351/351 líneas, 172/172 ramas) en `main`; siguen F4 (`sheet.py`) → F5 cierre
descripcion: por fuera nada cambia —mismos comandos, mismas piezas de catálogo, mismas láminas y la misma memoria—; por dentro los cuatro archivos que quedaban sobre las 500 líneas se parten y salen del trinquete
---

# Partir el núcleo congelado II — catálogo, reglas de la faja, láminas y memoria por partes, sin cambiar un byte de lo que entregan

## Estado y origen

- Mario, 2026-10-24: «aborda los puntos débiles … procede según tu criterio»; 2026-10-25: «continúa
  todos los pendientes que puedas … usa siempre pensamiento crítico y buenas prácticas». El
  contrato es de Claude con ese aval; D1–D10 se vetan por número.
- Lo dejó pendiente [partir-nucleo-congelado](partir-nucleo-congelado.md) (nota: «los otros
  cuatro archivos sobre el tope … quedan para un plan aparte»). Mismo método, con una diferencia
  de fondo: dos de los cuatro son UNA función gigante, que no se parte moviendo definiciones.

## El problema / lo que hay hoy

`tests/test_tamano_archivos.py` (`EXCEPCIONES`) congela cuatro archivos sobre el tope de 500:

| archivo | líneas | forma (base `4920db6`) |
|---|---:|---|
| `core/apolo/library/rules.py` | 903 | 19 funciones chicas (`:48-454`) + **`conveyor_engineering_check` `:457-903` (447 líneas)** |
| `core/apolo/drawing/sheet.py` | 882 | 7 dataclasses de primitivas (`:45-119`), 14 auxiliares (`:122-439`) + **`compose_sheet` `:442-882` (441 líneas)** |
| `core/apolo/library/builders.py` | 847 | 43 builders de 3 a 57 líneas + el dict `BUILDERS` (`:802-847`) |
| `core/apolo/library/engineering/report.py` | 555 | 7 verificaciones (`_fastener_checks` 139, `_fit_checks` 140, …) + `structure_engineering_check` (33) |

- 114 importaciones de estos módulos en `core/`, `tests/` y `scripts/`; la extensión privada del
  titular importa las primitivas de `apolo.drawing.sheet` (`Line`, `Label`, `SheetModel`…) en
  diez módulos: la ruta vieja tiene que seguir sirviendo por identidad.
- `builders.py` lo leen el catálogo (`BUILDERS[ref.builder]`) y la caché de geometría; mover un
  builder sin cambiarlo no cambia ninguna pieza.

## Lo que se revisó antes de escribir esto

- El plan I (D1–D12 y su bitácora): el corte por script byte a byte con comparación de
  `inspect.getsource` funcionó en las cinco fases y nunca hubo que tocar la huella de
  `tests/test_contrato_comandos.py`; se repite tal cual para `builders.py` y `report.py`.
- `compose_sheet` y `conveyor_engineering_check` son secuencias de bloques (por vista, por
  sección de la lámina; por verificación de la faja) que comparten locales: partirlas exige
  EXTRAER funciones, no mover. Ahí el gate no puede ser «el código es el mismo»: es «la salida es
  la misma» sobre un corpus.

## Decisiones (para vetar)

- **D1 — `builders.py` y `report.py`: refactor PURO por script** (D1 del plan I): se mueven
  definiciones de nivel superior por nombre, en su orden y byte a byte; un script compara el
  `getsource` de cada una antes y después. Nada se renombra ni se reordena por dentro.
- **D2 — `builders.py` por familia, con `BUILDERS` en su lugar.** Módulos planos en `library/`:
  `builders_estructura.py` (perfiles, tubos, ángulo, canal, viga I, pata, nivelador),
  `builders_transmision.py` (rodillo, tambor, motor, motorreductor sinfín, poleas, tensor, take-up),
  `builders_rodamientos.py` (rodamiento, chumaceras de pie y de brida, riel y bloque lineal, tope,
  sensor), `builders_tornilleria.py` (`_hex_prism`, perno, tuerca, allen, tornillo para madera,
  tornillo), `builders_carpinteria.py` (bisagras, manija, perilla, cerradura, imán, riel y carro de
  puerta, corredera). `builders.py` queda con los imports, el re-export y `BUILDERS` con el MISMO
  texto y orden: ≈ 70 líneas. Ningún módulo nuevo pasa de 300.
- **D3 — `report.py`**: `report_uniones.py` (`_fastener_checks`, `_weaker_yield`),
  `report_ajustes.py` (`_fit_checks`), `report_estructura.py` (`_bearing_checks`,
  `_buckling_checks`, `_tipping_check`); `report.py` queda con `_name` y
  `structure_engineering_check` + re-exports: ≈ 80 líneas.
- **D4 — Las dos funciones gigantes se parten por EXTRACCIÓN, con la salida como gate.**
  - `conveyor_engineering_check` → un orquestador ≤ 80 líneas que llama, en el MISMO orden, a una
    función por verificación (`rules_faja_*.py`: potencia y motor, banda y rodillos, estructura,
    holguras…, según los bloques que muestre el código); el estado compartido viaja en un
    `dataclass` explícito (`ContextoFaja`), no en globals. Los mensajes, sus códigos, su orden y
    sus cifras salen idénticos.
  - `compose_sheet` → `sheet_compose.py` (orquestador) + `sheet_vistas.py`, `sheet_cotas.py`,
    `sheet_cajetin.py` (o el corte que muestren sus bloques), con el estado de la lámina en un
    `dataclass` (`LaminaEnCurso`). Las primitivas y auxiliares de `:45-439` se mueven por D1 a
    `sheet_primitivas.py` / `sheet_auxiliares.py`.
  - Se permite sólo: pasar locales como campos del contexto, `return` de lo que el bloque
    producía, y los imports. Ninguna condición, cifra, texto ni orden cambia.
- **D5 — El gate de salida es un corpus congelado ANTES del corte**, en la misma fase y con la
  base de la fase: (a) `rules`: el JSON completo de `conveyor_engineering_check` para cada
  escenario de los tests de reglas y para las máquinas testigo que la suite ya regenera (38 y las
  del set de pruebas), más casos que pasen por cada rama (un test de cobertura de ramas con
  `coverage` sobre el corpus: toda rama de la función original se ejecuta al menos una vez, o se
  suma un caso); (b) `sheet`: el SVG y el DXF de cada lámina que los tests de planos ya componen,
  más el juego del 38, comparados TEXTO A TEXTO (con el mismo `random`/fecha fijados que usen los
  tests). El corpus vive en el scratchpad de la fase, no se commitea; el test permanente es D7.
- **D6 — Las rutas viejas siguen sirviendo por IDENTIDAD, para siempre** (D2 del plan I):
  `builders`, `report`, `rules` y `sheet` re-exportan TODO nombre de nivel superior que hoy
  definen. Lo que un test reasigna por nombre se queda donde se lee (se audita con `grep
  monkeypatch` antes de cada corte).
- **D7 — Gate permanente**: `tests/test_rutas_viejas.py` suma una sección por archivo (lista
  cerrada de nombres, mismo objeto); `BUILDERS` conserva claves y orden (un test lo compara con la
  lista de hoy).
- **D8 — Sin bumps de vigencia.** `GEOM_CACHE_EPOCH`, `COSIM_EPOCH` y las `CommandSpec.version`
  quedan iguales; `VERSIONES`/`CAMPOS` de `test_contrato_comandos.py` no se editan: un rojo ahí es
  un corte que movió un byte y se rehace. La firma final de cada proyecto en `golden_regen` sale
  idéntica.
- **D9 — Orden**: F1 (`builders`) ∥ F2 (`report`), que son puros y no se tocan entre sí; luego
  F3 (`rules`) ∥ F4 (`sheet`), las extracciones. Se mergean en serie (chocan en `EXCEPCIONES` y en
  los CLAUDE.md). Ante un conflicto al rebasar, el script de corte se re-ejecuta sobre la base nueva.
- **D10 — Las reglas viajan con el código**: cada fase borra su archivo de `EXCEPCIONES` en el
  mismo commit y actualiza el mapa de módulos del CLAUDE.md de su paquete (`library`, `drawing`),
  dentro de sus topes.

## Alternativas descartadas

- **Subir el tope a 1000**: el trinquete existe para que dos sesiones no choquen en el mismo
  archivo; `compose_sheet` es justo donde chocan los planos de taller y los de esquema.
- **Reescribir `compose_sheet` «mejor» mientras se parte**: mezcla refactor con cambio de
  comportamiento y deja sin gate. Primero se parte idéntico; mejorar va en su plan.
- **Dejar las gigantes y partir sólo lo fácil**: no saca a `sheet.py` ni a `rules.py` del
  trinquete, que es el objetivo.

## Fases

Tiempos de la tabla medida (S/M 40–65 min, L 90–100; revisión ~35 min por lote).

- **F0 — Medir** (hecha al escribir el contrato, base `4920db6`): tabla de arriba.
- **F1 — `builders.py` por familias** (`library` · S/M · ≈ 50 min): D1, D2, D6–D8, D10. Se
  verifica con la suite completa, `getsource` idéntico y `BUILDERS` igual.
- **F2 — `report.py` partido** (`library/engineering` · S · ≈ 40 min · paralelo a F1): D1, D3,
  D6–D8, D10.
- **F3 — `conveyor_engineering_check` por extracción** (`library` · L · ≈ 100 min · tras F1): D4,
  D5 (a), D6–D10.
- **F4 — `compose_sheet` por extracción** (`drawing` · L · ≈ 100 min · paralelo a F3): D4,
  D5 (b), D6–D10. Corre también la suite de la extensión privada del titular contra la rama (lo
  hace quien mergea, fuera de este repo).
- **F5 — Cierre** (S · ≈ 30 min): `EXCEPCIONES` vacío, E2E MCP por stdio contra una API sobre una
  copia de la base, open caliente del 38 con una caché escrita antes de F1, nota del plan.

## Lo que este plan NO hace

- No cambia una lámina, una regla, una cifra ni un texto de lo que ve el usuario o el agente.
- No mejora `compose_sheet` ni las reglas de la faja (eso, con su plan y su benchmark).
- No toca los archivos del front (`ui/src/tamanoArchivos.test.ts` tiene su propio trinquete).

## Riesgos

- **Una extracción cambia el orden de un efecto** (p. ej. un texto que se agregaba antes de una
  cota): el corpus de D5 compara el SVG texto a texto, no por contenido.
- **Una rama de `conveyor_engineering_check` sin caso en el corpus** pasa el gate sin haberse
  ejecutado: D5 exige cobertura de ramas de la función original sobre el corpus antes del corte.
- **Choque con trabajo en curso sobre `sheet.py`** (planos de taller o de esquema): F4 rebasa
  justo antes de mergear y re-ejecuta su corte si hay conflicto (D9).

## Bitácora

### F1 — builders.py por familias (2026-10-25, base `5a3d6e4`)

- **Corte** (script por NOMBRE sobre el AST, re-ejecutable: cada `def` byte a byte en su orden
  original; cada familia = docstring + imports + bloques separados por dos líneas en blanco):

  | módulo | nombres | líneas |
  |---|---:|---:|
  | `builders_estructura.py` | 11 (`profile`, `rect_tube`, `cylinder`, `box`, `leg`, `guard`, `leveling_foot`, `round_tube`, `angle`, `channel`, `i_beam`) | 112 |
  | `builders_accionamiento.py` | 8 (`roller`, `drum`, `motor`, `worm_gearmotor`, `pulley`, `v_pulley`, `tensioner`, `take_up`) | 226 |
  | `builders_rodamientos.py` | 7 (`sensor`, `bearing`, `linear_rail`, `linear_block`, `pillow_block`, `flange_bearing`, `endstop`) | 182 |
  | `builders_tornilleria.py` | 6 (`screw`, `_hex_prism`, `hex_bolt`, `hex_nut`, `socket_cap`, `wood_screw`) | 102 |
  | `builders_carpinteria.py` | 12 (bisagras, tirador, pomo, cerradura, imán, riel y carro de puerta, corredera) | 228 |
  | `builders.py` (fachada) | — | 82 (era 847; sale de `EXCEPCIONES`) |

- **Fuentes**: `inspect.getsource` de las 44 definiciones, idéntico antes y después (0 distintas,
  0 perdidas); cada una nace en su familia y la fachada sirve el MISMO objeto. `BUILDERS`: el
  bloque de texto es idéntico (46 líneas) y sus 43 claves, orden y objetos, iguales; el registro
  unido de `loader.BUILDERS` (57 claves), igual y en el mismo orden. Cada familia importa sola
  en un subproceso. Sólo cambiaron líneas de import.
- **Gate D7**: `test_rutas_viejas.py` suma la sección `builders`: lista CERRADA de las 44 por
  casa, «la fachada no define funciones», `BUILDERS` empieza con las 43 claves de hoy en su
  orden (lo nuevo va al final) y un test que prueba que el gate caza una copia.
- **D6**: `grep monkeypatch` sobre `builders` en `tests/`: ningún test reasigna un nombre de
  `builders` → nada se queda por esa razón.
- **Desvíos de D2**: (1) `builders_transmision.py` YA EXISTÍA (cadena y piñones, 275 líneas, con
  registro propio): la familia de D2 se llama `builders_accionamiento.py` (juntas pasarían de
  300 y mezclarían dos registros). (2) `cylinder`, `box` y `guard`, que D2 no nombraba, van a
  estructura; `screw` (DIN 912 liso), a tornillería. (3) El comentario de sección
  «carpintería / herraje» no es definición y no viaja: lo dice el docstring de la familia.
  (4) La fachada no re-exporta lo que `builders.py` sólo IMPORTABA (`math`, `Box`, `Cylinder`,
  `Pos`, `Rotation`, `make_*`): nadie lo importa de ahí (búsqueda en `core`, `tests`,
  `scripts`). (5) `builders_fijacion.py` sigue importando `_hex_prism` de `.builders` (sirve por
  el re-export; sin tocar). (6) La fachada mide 82 y no ≈ 70: docstring + re-exports agrupados.
- **D8**: `test_contrato_comandos.py`, `geomcache.py` y toda `CommandSpec.version` sin diff.
- **Suite**: completa con xdist, exit 0 y ningún `FAILED`; `ruff check core tests scripts`
  limpio; `test_claude_md.py` verde (library 32 KB de 35).

### F2 — report.py partido (2026-10-25, base `5a3d6e4`)

- **Corte** (script por NOMBRE sobre el AST: cada bloque = los comentarios pegados encima + la
  definición, byte a byte y en su orden; cada módulo = docstring + imports + bloques):

  | módulo (`library/engineering/`) | nombres | líneas |
  |---|---|---:|
  | `report_comun.py` | `G`, `_BEARING_CATS`, `_name` | 19 |
  | `report_uniones.py` | `_weaker_yield`, `_fastener_checks` | 164 |
  | `report_estructura.py` | `_bearing_checks`, `_buckling_checks`, `_tipping_check` | 200 |
  | `report_ajustes.py` | `_SHAFT_FIT_NAME_RE`, `_fit_checks` | 157 |
  | `report.py` | docstring, re-exports, `__getattr__`, `structure_engineering_check` | 79 (era 555; sale de `EXCEPCIONES`) |

- **Fuentes**: `inspect.getsource` de las 8 funciones idéntico antes y después (y cada una nace en
  su casa); `G` y `_BEARING_CATS` iguales por valor; 0 distintas. `VERSIONES`/`CAMPOS` sin editar
  y verdes; ninguna epoch ni `version` tocada (D8).
- **Desvíos de D3** (decididos con criterio): (1) **`report_comun.py`** nuevo con `G`,
  `_BEARING_CATS` y `_name`: los usan dos o tres de los módulos nuevos y, dejados en `report.py`,
  cada módulo tendría que importar `report`, que los importa a ellos (ciclo). `report.py` los
  re-exporta. (2) **`_SHAFT_FIT_NAME_RE`** (el regex que `_fit_checks` compila perezoso con
  `global`) viaja con su función a `report_ajustes` y `report` lo sirve EN VIVO por un
  `__getattr__` de módulo, no por valor: re-exportado, `report` se quedaba con el `None` de antes
  de compilarlo. (3) Como en el plan I (F2, desvío 2), `report.py` no re-exporta lo que sólo
  IMPORTABA (`math`, `_check`, `resolve_material`…): nadie lo importa de ahí (búsqueda en `core`,
  `tests`, `scripts`: sólo `structure_engineering_check`).
- **D6**: `grep monkeypatch` sobre `report` en `tests/`: ningún test reasigna un nombre de
  `report`; no hubo nada que dejar en su sitio.
- **Gate D7**: `test_rutas_viejas.py` suma la sección `report`: lista CERRADA de las 11
  definiciones, cada una el MISMO objeto que en su casa y nacida en ella; un test del regex vivo
  (antes y después de compilar) y dos que prueban que el gate caza un nombre que falta y una copia.

### F3 — rules.py (2026-10-25, base `698a5a7`)

- **Corte** (script re-ejecutable sobre el original: D1 por NOMBRE, cada definición con los
  comentarios pegados encima; D4 por RANGO de líneas, cada bloque verbatim como cuerpo):

  | módulo (`library/`) | contenido | líneas |
  |---|---|---:|
  | `rules_comun.py` | las 14 constantes y regex + `_f`, `_parse_power_kw`, `_parse_wall`, `_parse_diam`, `_vol_safe`, `_check`, `_name`, `_bbox_safe` | 100 |
  | `rules_calculo.py` | `required_force_n`, `required_power_kw`, `band_speed_m_s`, `recommend_motor_kw`, `recommend_motor`, `recommend_roller` | 51 |
  | `rules_enriquecer.py` | `_frame_from_scene`, `_enrich_conveyor` | 179 |
  | `rules_deteccion.py` | `detect_conveyor`, `_detect_by_name`, `infer_from_solids` | 152 |
  | `rules_faja_contexto.py` | `ContextoFaja` (dataclass) | 42 |
  | `rules_faja_transporte.py` | bloques 0 (velocidad de banda), 1 (apoyo), 2 (capacidad de rodillo), 3 (ancho útil), 6 (velocidad del rodillo), 7 (geometría) | 141 |
  | `rules_faja_motor.py` | bloque 4: arrastre y motorización | 151 |
  | `rules_faja_tambor.py` | 5 + 5b (par de régimen y de arranque), 5c (adherencia) | 131 |
  | `rules_faja_estructura.py` | 8 (flecha del bastidor), 9 (flexión del eje) | 98 |
  | `rules.py` | docstring + mapa, re-exports y el orquestador (50 líneas) | 93 (era 903; sale de `EXCEPCIONES`) |

- **D1**: `inspect.getsource` de las 19 funciones idéntico al del original (0 distintas); las 14
  constantes y regex, el MISMO objeto en `rules` y en `rules_comun`.
- **D4**: el orquestador conserva verbatim el preámbulo (despacho a la plantilla de rodillos de
  cadena y a `a_mano`, los locales, `v_real`/`v_eff`) y llama a 12 funciones en el orden de
  siempre. Lo único nuevo en cada bloque: la `def`, el desempaque `x = ctx.x` de los locales que
  LEE (calculado con `symtable` sobre el texto del bloque) y el `return` de lo que un bloque
  posterior lee (`support_count`; `soporte, metodo_norma, pull_n, p_req`; `frame`), que el
  orquestador vuelve a poner en `ctx`. Ningún bloque reasigna un nombre que llegue de fuera sin
  asignarlo antes (`det`, `material`, `allow`, `sugerido` se recalculan en su bloque).
- **Corpus (D5 a)**: un plugin de pytest (scratchpad) envolvió la función durante la suite
  completa en la base (exit 0) y grabó los argumentos deep-copiados, las reglas y el dict
  `conveyor` DESPUÉS (la adherencia le escribe `pull_n` y `bearing_radial_n`): 81 llamadas, 49
  únicas, 0 inconsistentes (testigo 38 por sus tests, banda sobre cama y sobre rodillos, rodillos
  de catálogo, a mano y de cadena). Sin `coverage` en el venv: líneas con `sys.settrace` y ramas
  con una COPIA de la función instrumentada por AST (`if`, `x if c else y`, cada operando de
  `and`/`or`; la copia da las mismas 49 salidas). Sobre lo grabado: 341/351 líneas y 153/172
  ramas; 7 casos sintéticos (paso 0, motor «documento» sin potencia, velocidad negativa, carga 0,
  banda inclinada con tambor engomado y bastidor mínimo, ISO de ≥ 80 m, arrastre negativo, eje
  flaco en error) → **56 casos, 351/351 líneas y 172/172 ramas**.
- **Después del corte**: las 56 salidas idénticas TEXTO A TEXTO (JSON con `sort_keys` de las
  reglas y del `conveyor` mutado) y, por caso, el MISMO conjunto de líneas del original
  ejecutadas (las del corte mapeadas al original; el script verifica antes que cada cuerpo sea
  el del original línea a línea): 351/351.
- **D6**: `grep monkeypatch` sobre `rules` en `tests/`: ningún test reasigna un nombre de
  `rules` → nada se queda por esa razón. Los imports de `_check`, `_BANDA_RE`, `_parse_*`,
  `_LEG_RE`, `_SECTION_RE` desde `.rules` (lints, rodillos a mano y de cadena, `report_*`,
  `viga_bastidor`, `cadena`) siguen sirviendo por el re-export, sin tocarlos.
- **Gate D7**: sección `rules` en `test_rutas_viejas.py` (lista CERRADA de los 34 nombres con su
  casa, la fachada sólo define la orquestadora y ésta llama a los 12 bloques en su orden, el gate
  caza una copia) y `tests/test_reglas_faja_congeladas.py`: los 3 casos que más líneas cubren
  juntos (310/351: banda sobre rodillos ISO con eje y bastidor, banda sobre cama tipo 38 con
  tensor y 300 kg, rodillos sin motor que dejan caer el paquete), congelados texto a texto en
  `tests/data/reglas_faja_congeladas.json`, también el `conveyor` después.
- **Desvíos de D4** (decididos con criterio): (1) el bloque «4 · motorización» (125 líneas) son
  DOS funciones, `verificar_arrastre` (método y norma por construcción) y
  `verificar_motorizacion`: dos verificaciones con su propio `calc`. (2) 5 y 5b van en una
  función: el par de arranque está anidado en el `if` del par. (3) Los módulos agrupan por tema,
  no por orden de llamada (`transporte` tiene 0–3 y 6–7). (4) `rules_enriquecer` va aparte de
  `rules_deteccion`: juntos pasaban de 300. (5) `_name` y `_bbox_safe` van a `rules_comun` (los
  usan los dos de detección). (6) Las funciones de bloque no llevan docstring: D4 sólo permite
  locales, `return` e imports; el comentario numerado del original encabeza cada cuerpo. (7) Como
  en F1/F2, `rules` no re-exporta lo que sólo IMPORTABA (`math`, `re`, `Counter`,
  `resolve_material`…): nadie lo importa de ahí (búsqueda en `core`, `tests`, `scripts` y en la
  extensión privada). El docstring de `rules.py` suma el mapa; el de la función no cambia.
- **D8**: `test_contrato_comandos.py`, `geomcache.py` y toda `CommandSpec.version` sin diff.
- **Suite**: completa con xdist, exit 0 y ningún `FAILED` (también la de la base, con el plugin
  del corpus); `ruff check core tests scripts` limpio; `test_claude_md.py` verde (library 33.8 KB
  de 35).

### F4 — sheet.py (2026-10-25, base `fac06a5`)

- **Corte** (script re-ejecutable sobre el original: D1 por NOMBRE, byte a byte; D4 por RANGO de
  líneas, cada bloque verbatim como cuerpo):

  | módulo (`drawing/`) | contenido | líneas |
  |---|---|---:|
  | `sheet_primitivas.py` | las 8 constantes (el bloque de texto tal cual) + `Line`, `Label`, `Circle`, `Arc`, `Polygon`, `Image`, `SheetModel` | 107 |
  | `sheet_auxiliares.py` | `_pick_scale`, `_place_view`, `_fit_for_dia`, `_hole_callouts`, `_dim_h_at`, `_dim_h`, `_dim_v`, `_zone_grid`, `_scale_bar` | 176 |
  | `sheet_anotaciones.py` | `_draw_table_with_balloons`, `_assembly_notes_auto`, `_bbox_vol`, `_weld_anchor`, `_place_weld_symbols` | 164 |
  | `sheet_lamina.py` | `LaminaEnCurso` (dataclass: los 31 argumentos + los 22 locales que un bloque pasa a otro, con su nombre) | 71 |
  | `sheet_vistas.py` | `preparar_lamina`, `dibujar_vistas`, `dibujar_cuadrante_iso` | 232 |
  | `sheet_cotas.py` | `acotar_solidos`, `acotar_desde_datum`, `dibujar_simbolos_de_soldadura`, `dibujar_detalle_de_pieza` | 114 |
  | `sheet_tablas.py` | `dibujar_tablas` (BOM, despiece con «Hoja», cédula de herraje) | 74 |
  | `sheet_cajetin.py` | `reunir_notas_de_taller`, `dibujar_notas`, `dibujar_cajetin` | 108 |
  | `sheet.py` | docstring + mapa, re-exports y el orquestador (61 líneas: la firma de 33 es la de siempre) | 110 (era 882; sale de `EXCEPCIONES`) |

- **D1**: `inspect.getsource` de las 21 clases y funciones idéntico al del original (0 distintas);
  el bloque de las 8 constantes, el mismo texto, y cada una el MISMO objeto en `sheet` y en
  `sheet_primitivas`.
- **D4**: el orquestador arma `LaminaEnCurso` con los argumentos y llama a 11 bloques en el orden
  del original. Lo único nuevo en cada bloque: la `def`, el desempaque `x = ctx.x` de lo que LEE
  de fuera (`symtable`, también lo que leen sus lambdas) y el `return` de lo que un bloque
  posterior lee, que el orquestador vuelve a poner en `ctx`. Los nombres que un bloque asigna y
  lee y que ya existían antes (`rect`, `tx`, `feat`, `bb`, `cx`, `entries`, `dscale`…) se
  revisaron uno a uno: el bloque los asigna antes de leerlos, en todo camino.
- **Corpus (D5 b)**: un plugin de pytest (scratchpad) envolvió `compose_sheet` durante la suite
  completa de la base (exit 0) y grabó los argumentos picklados y la huella del modelo: 169
  llamadas. La suite NO compone el juego del 38: un script aparte lo compuso (plantilla
  genérica, sombreada diferida, con los mapas de `sheet_set_maps`) desde una COPIA de la base de
  `apolo-cad-pruebas`: 42 llamadas más. 211, **183 únicas**, 0 inconsistentes. Re-correr lo
  grabado da la MISMA huella que en la suite en las 183. Para el gate, la fecha de `date.today()`
  va fijada (2026-01-02) y el DXF se normaliza en lo que es reloj: las variables de cabecera
  `$TDCREATE`… y los GUID, y el sello «versión @ hora» que ezdxf escribe en sus metadatos.
- **Cobertura** (sin `coverage` en el venv: líneas con `sys.settrace`, ramas con una COPIA de la
  función instrumentada por AST: `if`, `x if c else y`, cada operando de `and`/`or` y, además de
  F3, «el `for` no itera»; la copia da las mismas salidas). Lo grabado: 316/318 líneas y
  198/235 ramas. Con 16 sintéticos (las tres láminas del test permanente y 13 chicos: cotas por
  sólido con id inexistente y tope de 3, corte que no toca la pieza, detalle fuera de la pieza,
  explosionada con oculta y de chapas planas, sombreada con ocultas, detalle de pieza ausente,
  sin nombre con escala, plano y vacío, notas de taller de una pieza de catálogo…) → **199
  casos, 317/318 líneas y 220/235 ramas**. Lo que falta es inalcanzable: la línea 673 y su rama
  (`explode_scene` sólo devuelve piezas visibles); «el `for` no itera» sobre tuplas literales
  (`517`, `532`, `630`) o sobre listas que el `if` de arriba ya exige no vacías (`576`, `593`,
  `824`); `ev`/`mv` `None` (`project_views` devuelve toda vista pedida o levanta «Escena
  vacía»); `exp` vacía en `671`/`681` (levanta antes); `mfeat` `None` con forma (`773`, `774`);
  `dscale` 0 (`786`); y el «—» del material en `866` (sin pieza visible, la proyección levanta
  antes).
- **Después del corte**: los 199 casos dan el modelo, el SVG y el DXF idénticos TEXTO A TEXTO
  (597 archivos) y, por caso, el MISMO conjunto de líneas del original ejecutadas (las del corte
  mapeadas al original; el script verifica antes que cada cuerpo sea el del original línea a
  línea y que entre bloques sólo haya líneas en blanco): 199/199.
- **D6**: `grep monkeypatch` sobre `sheet` en `tests/`: ningún test reasigna un nombre de `sheet`
  (sólo `drawing.sheets_to_pdf`/`sheet_to_pdf` del paquete). `sheet` re-exporta los 46 nombres de
  nivel superior de antes, también los que sólo importaba.
- **Gate D7**: sección `sheet` en `test_rutas_viejas.py` (lista CERRADA de las 30 definiciones con
  su casa, los 15 importados, la fachada sólo define el orquestador y éste llama a los 11 bloques
  en su orden, el gate caza una copia) y `tests/test_laminas_congeladas.py`: tres láminas armadas
  en el test (conjunto soldado con corte, despiece y cédula; pieza de taller con ajuste, rosca,
  GD&T, datum por lista y detalle; explosionada con BOM y detalle de pieza) congeladas primitiva a
  primitiva y en su orden en `tests/data/laminas_congeladas.json` (51 KB), generado con el código
  de ANTES del corte.
- **Desvíos de D4** (decididos con criterio): (1) el orquestador se queda en `sheet.py`, no en un
  `sheet_compose.py` (como F3 en `rules.py`): `compose_sheet` conserva su casa y la ruta vieja no
  depende de un re-export. (2) El corte por bloques: `sheet_vistas`, `sheet_cotas` (también la
  soldadura y el detalle de pieza, que acotan sobre las vistas), `sheet_tablas` y
  `sheet_cajetin` (notas de taller, notas y cajetín); el contexto en su propio `sheet_lamina.py`.
  (3) Las auxiliares son DOS módulos (`sheet_auxiliares` + `sheet_anotaciones`): juntas pasaban
  de 300. (4) A diferencia de F1–F3, `sheet` re-exporta también lo que sólo IMPORTABA (`date`,
  `dataclass`, `world_to_view`…): la extensión privada importa de aquí y el contrato pedía «todo
  nombre de nivel superior». (5) `return model` pasa a `return ctx.model`. (6) El test permanente
  compara el MODELO (cada primitiva y `meta`, floats a 4 decimales), no el SVG: el HLR de OCCT
  puede variar en el último bit entre Windows y el Linux del CI, y los exportadores son funciones
  puras del modelo. (7) Las funciones de bloque no llevan docstring (D4 sólo permite locales,
  `return` e imports); el comentario del original encabeza cada cuerpo. (8) El pickle de
  build123d guarda las mallas y 32 formas del 38 no se vuelven a leer (`BinTools`
  «PointRepresentation = 29»): el juego se grabó con `brep_io.serialize_robust` sin mallas.
- **D8**: `test_contrato_comandos.py`, `geomcache.py` y toda `CommandSpec.version` sin diff.
- **Suite**: completa con xdist, exit 0 y ningún `FAILED` (también la de la base, con el plugin
  del corpus); `ruff check core tests scripts` limpio; `test_claude_md.py` verde (drawing 11.9 KB
  de 35). Falta, como dice F4, la suite de la extensión privada contra la rama (quien mergea).
