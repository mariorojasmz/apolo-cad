---
estado: en curso
nota: F1 MERGEADA 2026-10-29 (4f94c49; decisiones F1-a…F1-i vetables en la Bitácora). Pendiente fuera de F1 - chapa sin ficha (run_script) en la BOM y la lista, arandela bajo la cabeza cuando haya agujero colisado
descripcion: La BOM sirve para comprar y para cortar: cada chapa con su espesor, cada perfil con el corte medido, cada perno con su arandela y su tuerca una sola vez
---

# La BOM sirve para comprar y para cortar, sin leer el nombre de la pieza

## Estado y origen

Tanda de 6 pilotos de familia (2026-10-28/29: tolva, carro, mesa de trabajo, soporte de paneles,
rack, rodillos por cadena). Las re-revisiones de taller a ciegas, con la puerta v19 APROBADA, siguen
dejando MEDIA que NO son de cada máquina sino de la fábrica; se repiten en casi todas y ningún
modelador las puede corregir desde fuera. Regla de Mario: «defecto visto → arregla la fábrica»
(determinista, para todas las PCs).

## El problema / lo que hay hoy

Medido en los reportes de `rerevisor1` de `C:\t\maq\<slug>\` (sólo lectura):

1. **Chapa a medida sin espesor ni norma en la BOM** (tolva: «las filas A-MEDIDA de chapa sólo traen
   longitud_mm y material acero, sin espesor, grado ni norma»; rack: montante de chapa plegada «ref
   A-MEDIDA, norma vacía»). La lista de corte ya mide la chapa (`Feature.chapa`,
   [lista-de-corte-medida](lista-de-corte-medida.md) F1), la BOM no la lee.
2. **El ángulo medido no llega a la BOM** (rack: «c30 dice L=765.4 ∠33.2°/33.2° y c32_1, la misma
   pieza, L=765.4 sin ángulo»; paneles: dos filas para la misma diagonal, una con ∠17.7° y otra
   recta). Es la decisión F1-i de lista-de-corte-medida («el BOM no cambia»): las copias de un
   patrón no heredan `miter` y la BOM agrupa por lo declarado (`library/bom.py:101`).
3. **Piezas distintas en una fila** (paneles: «ANG-75X6 L=706.8, cant. 3» con taladros distintos en
   cada una): la BOM agrupa por ref + largo + ∠, no por la pieza que se fabrica.
4. **Tuerca repetida** (carro: 8 «TUERCA-M10 DIN 934 (unión declarada sin pieza modelada)» además
   de las 8 DIN 985 modeladas: la BOM compra 16 tuercas para 8 pernos): `tornilleria_declarada.py`
   no reconoce como suya la tuerca modelada de otra norma.
5. **Sin arandelas** (rack, carro, tolva, paneles: «sin ninguna arandela en la BOM», EN 1090-2 la
   pide sobre agujero sobremedida y bajo vibración): `join_bolted` no pone arandela y el catálogo no
   tiene DIN 125 (los modeladores las agregan a mano o las olvidan).
6. **Pernos de un patrón «aislados»** (paneles: `check_assembly` da 26 piezas aisladas, las de los
   comandos fuente de cada unión con perno; las copias sí tienen su contacto).

## Decisiones (para vetar)

- **D1. Chapa en la BOM por su ficha**: una pieza con `Feature.chapa` sale con espesor, material con
  su norma (la del material resuelto) y su desarrollo (el MISMO de la lista de corte, una fuente:
  `chapa_ficha`).
- **D2. Corte medido en la BOM** (revierte F1-i de lista-de-corte-medida): la fila de un perfil de
  catálogo cortable lleva el largo exterior y los ángulos MEDIDOS (`cutlist_medida`), y agrupa por
  la medida; una copia de patrón agrupa con su original. Lo declarado se contrasta como en la lista.
- **D3. Agrupar por la pieza que se fabrica**: dos piezas a medida o cortadas de la misma ref que
  difieren en sus taladros (u otra operación) no comparten fila; cada una con su marca (pieza de
  plano). Criterio de igualdad = la firma geométrica que ya comparten las instancias (`mesh_key` +
  volumen), no el nombre.
- **D4. La tornillería declarada no duplica la modelada**: si una unión perno tiene su tuerca (o
  perno) modelada, de la norma que sea, no suma la declarada. Una fila por designación, como hoy.
- **D5. `join_bolted` con arandela**: refs DIN 125 (M6–M20, acero zincado e inox A2) en el catálogo
  y `join_bolted` pone arandela bajo la tuerca (y bajo la cabeza si el agujero es sobremedida o
  colisado: ISO 273 serie gruesa o ranura) por defecto, con el largo del perno recalculado con ella;
  `arandela: false` la quita (el default de un log viejo reproduce lo de antes: campo nuevo con
  default compatible, como `add_joint(arrastrar=False)`, y sube la `version` del comando sólo si el
  executor cambia lo que ya generaba). Opción `tuerca: "din985"` (autoblocante) para lo que vibra.
- **D6. Los pernos del comando fuente de un patrón llevan su contacto** como sus copias.

## Alternativas descartadas

- **Que cada modelador nombre espesor y ángulo en el nombre**: frágil, no lo lee ningún cálculo y
  ya falló en tres máquinas.

## Fases

- **F1 (M, `library` + `commands` + catálogo)**: D1–D6 con tests sobre los `.apolo` reales de la
  tanda (sólo lectura): la tolva da el espesor de cada chapa; el rack y los paneles dan una fila por
  pieza con su ∠; el carro compra 8 tuercas, no 16; un `join_bolted` nuevo trae arandelas en la BOM;
  los pernos fuente del patrón de paneles no salen aislados. Lo que hoy ya sale bien no cambia
  (testigos y listas existentes idénticas salvo lo que mentía).

## Lo que este plan NO hace

- Planos de despiece nuevos ni marcas en los planos (la marca de D3 sale en la BOM y el CSV).

## Riesgos

- **Que D3 parta en mil filas** piezas que sólo difieren por ruido de la geometría: tolerancia de
  volumen relativa y test con las 480 piezas de la clasificadora (las filas no pueden crecer salvo
  donde hay taladros distintos de verdad).

## Bitácora

### F1 (2026-10-29)

Implementada en la rama del worktree (sin mergear). Archivos: `library/bom_compra.py` (nuevo:
D1–D3 y la marca), `library/bom.py`, `library/cutlist_medida.py` (la medida por sólido se mudó
aquí desde `cutlist.py`, que la re-exporta: una fuente para la lista y la BOM),
`library/tornilleria_declarada.py` (D4), `library/fijacion.py` + `library/builders_fijacion.py`
(`flat_washer`) + `library/data/115_arandelas.yaml` + la familia DIN 985 de
`library/data/109_tuercas.yaml` (D5), `commands/models_union.py`, `commands/exec_union.py` (sello),
`commands/union_taller.py` (D5), `library/lints.py` (`_is_bolt`), `assembly/grouping.py` y
`ui/src/panels/Tree.tsx` (la categoría `arandelas` en «Tornillería»),
`services/delivery_inputs.py` + `api/routers/assembly.py` (D6). Tests en
`tests/test_bom_compra_fiel.py`.

Decisiones tomadas en la fase (vetables por número):

- **F1-a. La norma de la chapa** (D1): la que nombra su material o su pieza (ASTM, EN 10xxx, JIS,
  AISI, SAE: «Montante … chapa e2 ASTM A1011» → ASTM A1011); si no, la del material GENÉRICO de
  `bom_compra.NORMA_CHAPA` (acero → ASTM A36 ≈ S235JR, inoxidable → ASTM A240 AISI 304, aluminio →
  ASTM B209 6061-T6: las de su σy en `materials.YIELD_MPA`); un material desconocido o con su grado
  propio que no es una norma («acero S275JR») → vacío, nunca inventada. El `material` de la fila no
  cambia (densidad y costo lo leen); `longitud_mm` pasa a ser el lado mayor del desarrollo. Sólo con
  ficha: las paredes de la tolva (`run_script`) siguen por la caja, como en la lista de corte
  (F1-j de [lista-de-corte-medida](lista-de-corte-medida.md), pendiente).
- **F1-b. Lo declarado que coincide se conserva** (D2): si `cut_length` coincide con el exterior
  medido (± 1 mm) la fila guarda el largo declarado y, si el `miter` coincide (± 0,5°), su texto:
  la BOM de siempre byte a byte. La clave agrupa por los ángulos ORDENADOS (una copia girada no
  separa). El `aviso` sólo sale si la pieza DECLARÓ otra cosa (un `miter` o un largo): la copia de
  un patrón no hereda `miter` y no declaró «a escuadra». Una pieza con varias barras sigue como antes.
- **F1-c. La pieza que se fabrica = su volumen** (D3), dentro de la misma ref + largo + corte (+
  material): ± máx(1 mm³, 1e-4 relativo; el ruido entre copias es ~1e-9 y un Ø9 en un ángulo de
  6 mm es ~6e-4). Sólo lo cortado de catálogo: lo a medida ya agrupaba por nombre + volumen + caja y
  no cambia (no se funden piezas de nombre distinto). `mesh_key` no hace falta: dos instancias
  intactas tienen el mismo volumen.
- **F1-d. La marca** (D3): las filas que quedan con la misma ref, descripción, largo y material
  llevan `marca` = la pieza representante (la de su lámina) y la descripción la nombra
  («… · marca c58 («Pata trasera»)»), así llega al CSV sin columna nueva. También marca lo a
  medida de igual nombre y geometría distinta (las 4 guardas de retorno de la clasificadora, que ya
  eran 4 filas iguales a la vista).
- **F1-e. La tuerca del carro** (D4): la causa no era la norma (la DIN 985 ya se reconocía como
  tuerca) sino la arandela: a 2 mm de la pletina no «tocaba» ninguna pieza (tolerancia 1 mm). Regla
  nueva, sumada a la de siempre: la tuerca cuyo centro cae en la caja de un fijador que cruza las
  dos piezas es de esa unión.
- **F1-f. `arandela` y `tuerca` son campos VISIBLES** de `join_bolted` (el modelador los elige):
  `arandela` default False (= log viejo) y el sello pone True al comando que nace; `tuerca`
  `din934` | `din985`. Sin `version` (la huella D11 del executor no cambia y la rama sin arandela
  es la de siempre) ni epoch (sólo refs nuevas). El acceso por detrás mide arandela + tuerca.
- **F1-g. Sin arandela bajo la cabeza**: `join_bolted` taladra siempre ISO 273 serie media y el
  criterio 6 exige ese mismo Ø en los agujeros previos: no hay agujero sobremedida ni colisa que la
  pida. Entra cuando exista esa opción.
- **F1-h. Catálogo M6–M24** (no M6–M20): `join_bolted` admite M24 y el sello pone la arandela; sin
  la ficha un M24 nuevo daría error. 9 DIN 985 (`TUERCA-AB-*`, clase 8 zincada) + 18 DIN 125-A
  (`ARANDELA-*` zincada 140 HV y `ARANDELA-*-A2`), categoría propia `arandelas`: no es fijador (no
  cubre un perno declarado en `tornilleria_declarada`) ni perno (`calidad_pernos`); `_is_bolt` sí
  la cuenta como herraje (interferencias de la puerta, «pieza sin grupo ni unión») y
  `FEA_HARDWARE_CATS` la saca de la malla (como su tuerca). `HARDWARE_CATS` no se amplía.
- **F1-i. D6 en el endpoint de `check_assembly`, no en `build_graph`**: suma las aristas pieza ↔
  a/b del `jb_<cmd>` (`aristas_tornilleria_join_bolted`). La puerta y `gravity_test` ya la trataban
  así; `build_graph` lo usan vigas, izaje y sobrantes, donde un perno colgado no debe mover cargas.

Medido sobre los `.apolo` reales (sólo lectura, `C:\t\maq`, `-correccion1`; la clasificadora,
`-correccion5`), antes = `main` en `96a5cdd`:

| máquina | antes | después |
|---|---|---|
| tolva | 4 «Placa base» A-MEDIDA, norma vacía | e = 10 mm, desarrollo 200×200, ASTM A36 |
| carro | 30 filas: + 8 «TUERCA-M10 DIN 934 (unión declarada…)» | 29 filas: sólo las 8 DIN 985 modeladas |
| paneles | «ANG-75X6 L=706.8 ×3»; diagonal ∠17.7° ×1 + recta ×2; c208 ∠5.2° ×1 + c219_1 recta ×1; 26 aisladas | 3 filas ×1 con su marca (c58, c98_1, c98_2); ∠17.7° ×3; ∠5.2° ×2; 0 pernos aislados |
| rack | 23 filas: ∠33.2° ×4 + recta ×4; 15 chapas sin espesor | 22 filas: ∠33.2° ×8; montante e = 2, 255,6×2392, 4 pliegues, ASTM A1011 |
| clasificadora (478 piezas) | 120 filas | 120 filas: −1 (∠20.4° ×1 + recta ×11 → ×12), +1 (largueros de tramo 1 y 2: 90 y 94 caras, taladros distintos), 24 contenedores de chapa con espesor |

Costo (`time.process_time()`, laptop): la BOM de la clasificadora 0,33 → 1,30 s la primera vez (la
medida de 230 perfiles, que la lista de corte ya pagaba) y 0,36 → 0,59 s la segunda (caché de la
medida por `id(shape)`).

Tests: `tests/test_bom_compra_fiel.py` (uno o más por decisión; los de `.apolo` reales se saltan
sin `C:\t\maq`). Cambian, por la arandela que ahora trae todo `join_bolted` nuevo (D5): el largo
de `test_puerta_agarre` (30 → 35, y el texto del error 213,5 → 216), las piezas de
`test_f6_revisores_fajas` (M8×20 → M8×25 + 2 arandelas), `test_union_en_perfil_hueco` D3 (la
tuerca sube 1,6 mm tras la arandela), `test_trabas_de_modelado` y `test_v65c_fixes` (las arandelas
entre la tornillería), `test_fea_uniones_empernadas` (9 piezas fuera de la malla, no 6);
`test_union_en_perfil_hueco` D2 fija `arandela: false` (prueba la regla de largo de su plan);
`test_catalog_datadriven`, `test_catalogo_electrico`, `test_extensiones` y
`test_contrato_comandos` suman las 27 refs y los 2 campos. Suite completa secuencial: 4 FAILED en
la primera corrida (los conteos del catálogo y el FEA de arriba), corregidos y re-corridos;
`ruff` limpio; `npm test` (646) y `npm run build` verdes.
