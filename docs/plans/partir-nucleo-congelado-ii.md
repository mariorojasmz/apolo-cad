---
estado: en curso
nota: contrato de Claude con criterio delegado (2026-10-25), vetable por número; F0 medida en la escritura del contrato (base `4920db6`); siguen F1 (`builders.py`) ∥ F2 (`report.py`) → F3 (`rules.py`) ∥ F4 (`sheet.py`) → F5 cierre
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
