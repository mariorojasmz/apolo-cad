---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: F1 implementada y revisada (suites verdes); falta que Mario revise y mergee el código, y F3 (cirugía del proyecto 38 con COLSON-5X2-PU-45-A-FT)
descripcion: El catálogo trae garruchas industriales de placa con ficha real (Blickle LH-ALTH y Colson Colombia serie 44/45, la que se vende en Lima) y el proyecto 38 las usa en vez de las hechas a mano
---
# Garruchas de catálogo: el agente pone garruchas reales en vez de modelarlas a mano

## 1. Estado y origen

Mario (2026-10-06): en el proyecto 38 (`faja-paqueteria-4m`) las 6 «Garrucha Ø125 freno
total» se modelaron a mano como `run_script`; quiere **catálogo con datos reales si existen
en internet**, priorizando marcas que se consigan en su zona (**Lima, Perú**). Por defecto, Ø125
giratoria con freno total.

## 2. Lo que hay hoy

- El catálogo (231 refs, `core/apolo/library/data/*.yaml`) **no tiene garruchas ni ruedas**:
  `grep -il "caster\|garrucha\|rueda"` sobre `library/` sólo encuentra las ruedas del carro de
  puerta corrediza (`107_correderas_colgantes.yaml`).
- Proyecto 38 (medido por MCP, sólo lectura):
  - `c32` `set_variable h_garrucha` (160): altura desde el piso hasta la cara inferior de la placa
    base de la pata.
  - `c1223`–`c1228`: 6 `run_script` «Garrucha Ø125 freno total (±Y, n)»: placa 100×85×4,
    4 agujeros Ø11 a 80×60, pista de giro Ø72, horquilla, rueda Ø125×37 con **avance 38 hacia −X**,
    pedal de freno. Origen de facto: cara superior de la placa en z = `h_garrucha`.
  - `c1229`: `run_script` con los 24 juegos perno M10×25 + tuerca, en el patrón 80×60.
  - Placas base: `c58` (+Y) y `c64` (−Y), `create_box` 110×110×`placa_thk` en
    z = `h_garrucha + placa_thk/2`, con sus taladros Ø11 `c59`–`c62` / `c65`–`c68` a ±40 × ±30;
    `c63`/`c69` las repiten en X con paso `(long_centros-600)/2` (→ `c63_1`, `c63_2`, `c69_1`, `c69_2`).
  - Uniones: `garrucha_{pY,nY}{1,2,3}_placa` (`c1230`…`c1240`, perno M10 qty 4),
    `piso_garrucha_*` (`c1231`…`c1241`, grounds), `tornilleria_garruchas` (`c1242`, contacto
    `c1229`↔`c58`) y el grupo «Rodaje».

## 3. Lo que se revisó antes de escribir esto

- **`library/builders.py` está congelado en 847 líneas** por el trinquete
  `tests/test_tamano_archivos.py` (sólo puede bajar). Un builder nuevo NO cabe ahí: ni siquiera
  la línea de registro. El único consumidor de `BUILDERS` es `library/loader.py:19,36`.
- `insert_component` (`commands/registry.py:1748`) coloca el **origen local** del builder en
  `position` (`kernel/shapes.py::place` = `Pos * Rotation * shape`), así que un builder con
  origen propio funciona sin tocar el executor (como el `worm_gearmotor`).
- La caché de geometría (`doc/geomcache.py`) se indexa por los params de cada comando y
  `GEOM_CACHE_EPOCH`, **no por el contenido del catálogo**: una ref nueva no tiene entradas
  previas y no cambia la geometría de ninguna existente.
- Las categorías aparecen en tres lugares: `library/catalog.py::CATEGORIES` (orden de la UI),
  `assembly/grouping.py::CAT2SUB` y `ui/src/panels/Tree.tsx::CAT2SUB` (subsistema), más
  `library/checks.py::FEA_HARDWARE_CATS` (lo que el FEA no malla). → El cambio toca
  `library`, `assembly` y `ui`: por eso este plan.
- `costing.py:33-49`: sin `specs.cost`, el costeo estima `peso × costo/kg × HW_FACTOR` y lo
  DECLARA como fuente. Un `cost` inventado sería peor que la estimación declarada.
- Las cuentas que hay que actualizar: `tests/test_catalog_datadriven.py:130`
  (`len(CATALOG) == 231`) y «catálogo 231 refs» del CLAUDE.md raíz. Los README los sincroniza
  `scripts/release.py`.

### Investigación (2026-10-06, dos agentes + verificación puntual)

**Blickle LH-ALTH / LH-ALTH-ST / BH-ALTH** (serie pesada; banda poliuretano Extrathane 92 Shore A
sobre núcleo de aluminio inyectado, rodamiento de bolas, horquilla de chapa de acero zincada;
`-ST` = «stop-top», freno total de rueda y giro). Misma placa 140×110 y agujeros 105 × 75–80
(ranurados) Ø11 en los 4 Ø y las 3 variantes; misma altura entre variantes de un Ø. Fichas
`https://www.blickle.us/en-us/product/<slug>`; **verificadas a mano** la LH-ALTH 125K-3-ST
(`…-279000`) y la BH-ALTH 125K-3 (`…-266064`).

| Ø×ancho | H | avance (gir · ST) | carga 4 km/h / estática | peso gir · ST · fija |
|---|---|---|---|---|
| 100×40 | 140 | 45 · 45 | 350 / 875 | 2.1 · 2.3 · 1.3 |
| 125×40 | 165 | 45 · 45 | 550 / 1375 | 2.3 · 2.5 · 1.6 |
| 150×50 | 197 | 65 · 65 | 650 / 1625 | 3.5 · 4.1 · 2.3 |
| 200×50 | 245 | 70 · 67 | 800 / 2000 | 4.1 · 4.7 · 2.8 |

No publica: espesor de placa ni radio de giro.

**Colson Colombia (ex-IMSA) serie 45 (giratoria) / 44 (fija), PU galvanizada.** Es la
nomenclatura que usa **Ruedas y Garruchas Industriales SAC** (Jr. Julio C. Tello 1121, Lince;
`ruedasygarruchas.com.pe`, «6X2 PU 45 A», «Serie 44 fija»). Fichas del fabricante archivadas
en Wayback (2023-10-21; el sitio vivo da 403). Banda PU 90±5 Shore A sobre rin de
polipropileno, balinera de precisión; «disponibles con o sin freno total».

| | 4" | 5" | 6" | 8" |
|---|---|---|---|---|
| placa / agujeros c-c | 5"×4" / 3 3/4"×3" | igual | igual | igual |
| H giratoria 045 · fija 044 | 5 13/16" · 5 13/16" | 6 11/16" · 6 9/16" | 7 11/16" · 7 5/8" | 9 9/16" (neumática) · 9 9/16" |
| radio de giro | 3 11/16" | 4 3/16" | 4 7/8" | 6 11/16" (neumática) |
| carga PU (kg) | 200 | 250 | 400 | 400 |
| ancho de banda PU | — | 1 3/4" | 1 3/4" | — |

No publica: Ø de agujero, espesor de placa, avance, peso, ni la altura de la variante con
freno total. La tienda de Lima anuncia la 4X2 PU 45 A con freno a 350 kg (la ficha dice 200).

**Descartadas como familia** (quedan citadas en el YAML): Tente Alpha 3470/3477/3478 (no hay
Ø150, usa 160; no hay freno total Ø100 con placa P63; la fija cambia de placa), Colson USA
serie 4 (sin avance ni peso; agujeros sólo de distribuidor), Hamilton (fichas 403), Blickle
L-ALTH (la placa cambia entre 125 y 150).

**Precios publicados**: ninguno del MISMO modelo. Referencias cercanas: Barron Equipment,
Blickle LH-ALTH 150K-16 (otra placa) USD 198.29; Lima (Sodimac/Promart, 2026-10-06) genérica
SERRATURE 150 mm PU: S/ 89.60 giratoria · S/ 115.26 freno · S/ 82.17 fija.

## 4. Decisiones (para vetar)

- **D1. Categoría `garruchas`, archivo `110_garruchas.yaml`.** «Garrucha» es la palabra de
  Mario y de las tiendas de Lima. El prefijo 110 la carga AL FINAL: no reordena las refs
  existentes ni el enum de `insert_component`.
- **D2. Dos familias, 24 refs (231 → 255).** Blickle LH-ALTH (12: giratoria, `-ST`, fija ×
  Ø100/125/150/200) por ser la ficha más completa y consistente; Colson Colombia serie 44/45 PU
  (12: giratoria, freno total, fija × 4"/5"/6"/8") por ser **la que se compra en Lima**. Las
  refs son el código comercial: `LH-ALTH-125K-3-ST`, `BH-ALTH-150K`…;
  `COLSON-5X2-PU-45-A`, `COLSON-5X2-PU-45-A-FT`, `COLSON-5X2-PU-44-A` (la nomenclatura de la
  tienda + `-FT` para freno total, porque el código exacto de freno del fabricante no quedó
  verificado).
- **D3. Lo no publicado se declara, no se disimula.** Cada variante lleva `no_publicado: "…"`
  en specs (lo ven el agente, la BOM y quien cotiza) y el YAML comenta de dónde sale cada valor:
  - `placa_t` (ambas marcas): representativo, 5 mm LH-ALTH, 4 mm Colson.
  - Colson `agujero_d`: Ø11 representativo (perno 3/8").
  - Colson `avance`: DERIVADO del radio de giro publicado,
    `e = √(R² − (b/2)²) − D/2` (4" ≈ 40, 5" ≈ 41, 6" ≈ 46; 8" desde el radio de la neumática).
  - Colson `weight`: estimado por analogía con Blickle de igual Ø y clase.
  - Colson ancho de banda 4"/8": 1 3/4" por analogía; altura 8" giratoria = la de la fija
    044 publicada; altura `-FT` = la de la giratoria (la ficha nylon 6" con freno la iguala).
  - Blickle `radio_giro`: no se publica → no se escribe.
  Cuando Mario cotice en Lince, los estimados se reemplazan y se borra su mención.
- **D4. `cost` sólo con precio publicado del MISMO modelo: hoy ninguno → sin `cost`.** El costeo
  cae a su estimación por peso y la declara. Los precios cercanos (Barron, Sodimac/Promart)
  quedan en el comentario del YAML como referencia para cotizar.
- **D5. Builder `caster` en un módulo nuevo, `library/builders_rodaje.py`**, porque
  `builders.py` está congelado. `loader.py` une los registros (`{**BUILDERS, **BUILDERS_RODAJE}`)
  y **rechaza un nombre repetido** (un builder no puede pisar a otro en silencio). Línea en
  `library/CLAUDE.md`: «builder nuevo → módulo propio; `builders.py` no crece».
  - **Marco canónico**: origen en el **centro de la cara SUPERIOR de la placa** (la cara que se
    atornilla), Z hacia arriba; placa `placa_l` a lo largo de X y `placa_w` a lo largo de Y, en
    z ∈ [−placa_t, 0]; agujeros (o ranuras si `agujeros_y_min ≠ agujeros_y_max`) a
    ±`agujeros_x`/2 × ±`agujeros_y`/2; eje de la rueda paralelo a Y; en la giratoria la rueda
    queda **detrás, a x = −avance** (como en el modelo a mano); la fija, bajo el centro; el
    punto de apoyo al piso en **z = −altura**. → `position` de `insert_component` = el centro
    de la cara inferior de la placa base de la pata.
  - Geometría: placa con agujeros/ranuras REALES (lo que se taladra), rueda Ø×ancho reales,
    altura y avance reales; pista de giro, horquilla, eje y pedal REPRESENTATIVOS (escalados del
    espacio libre entre placa y rueda). Un solo sólido (partes solapadas 0.5–8 mm, regla de
    `library`). El builder rechaza `tipo` desconocido y una altura que no deja lugar a la
    horquilla (`altura − rueda_d < placa_t + 6`).
- **D6. Ancla `placa`** en `_CATEGORY_ANCHORS["garruchas"]`: origen (0,0,0), eje +Z. Le da al
  agente la cara de montaje sin calcularla.
- **D7. Subsistema «Estructura»** para `garruchas` en `grouping.py` y `Tree.tsx`, igual que
  `pies_niveladores` y `patas` (apoyos al piso).
- **D8. `garruchas` entra a `FEA_HARDWARE_CATS`, NO a `HARDWARE_CATS`.** La horquilla y la
  rueda son representativas: mallarlas mentiría rigidez y peso (su peso entra como carga
  sustituta declarada). `HARDWARE_CATS` tiene semántica de interferencia/lints y no se amplía
  (regla de `library`).
- **D9. Sin bump de `GEOM_CACHE_EPOCH` ni de `version` de executor.** Sólo se agregan refs y un
  builder que ninguna ref existente usa; `_exec_insert_component` no cambia (el trinquete D11
  lo confirma).
- **D10. Proyecto 38: `COLSON-5X2-PU-45-A-FT`** (elegida por Mario, 2026-10-06): es
  la que compras en Lince, y lo que importa para fabricar (altura y patrón de agujeros) está
  publicado; lo estimado (avance, peso) sólo mueve geometría representativa y masa. Alternativa:
  `LH-ALTH-125K-3-ST` (ficha 100 % publicada, importada). Con la elegida:
  - `h_garrucha` = su altura (Colson 5" 169.9 · Blickle 165).
  - Placas base `c58`/`c64` crecen a placa de garrucha + ~5 mm por lado (Colson 127×101.6 →
    140×110; Blickle 140×110 → 150×120) y sus taladros `c59`–`c62`/`c65`–`c68` pasan al patrón
    real (Colson 95.25×76.2; Blickle 105×77.5, centro de la ranura).
  - `c1223`–`c1228` y sus uniones `c1230`–`c1241` se borran juntos (`POST /api/commands/remove`,
    atómico) y se recrean con `insert_component` y los MISMOS nombres de unión y ground; los
    sólidos se llaman por rol: «Garrucha (+Y, 1)»…
  - `c1229` (pernos) se EDITA en sitio al patrón nuevo (conserva id y `tornilleria_garruchas`).
  - El grupo «Rodaje» recibe los comandos nuevos.

## 5. Alternativas descartadas

- **Builder en `builders.py`**: rompe el trinquete. Partir `builders.py` por familias sería lo
  correcto a la larga, pero es un plan propio, no algo de pasada.
- **STEP del fabricante**: la regla es biblioteca paramétrica; el STEP sólo para la compra.
- **Modelar la ranura como agujero redondo**: la placa Blickle admite 75 u 80 entre filas; con
  agujero redondo el agente no ve el juego y taladraría la base en un solo valor sin saberlo.
- **Una familia Tente**: es la única que publica radio de giro, pero sin Ø150 y con placa
  distinta en la fija; no aporta sobre Blickle y no se vende en Lima.
- **`cost` desde las genéricas de Sodimac**: es otro producto; la estimación del costeo es más
  honesta porque se declara como estimación.

## 6. Fases

| fase | qué | paquete | tamaño | depende de | se verifica con |
|---|---|---|---|---|---|
| F0 | (hecha) investigación + lectura del proyecto 38 | — | S | — | este documento |
| F1 | YAML + `builders_rodaje.py` + loader + `CATEGORIES` + ancla + `CAT2SUB` (backend y UI) + `FEA_HARDWARE_CATS` + tests + conteos (`test_catalog_datadriven`, CLAUDE.md raíz) + línea en `library/CLAUDE.md`. Re-verifica en el navegador las fichas Colson (Wayback) y corrige el YAML si algo difiere | `library`, `assembly`, `ui`, `tests` | M | aprobación | pytest completo, `ruff check core tests scripts`, `npm test`, `npm run build` |
| F2 | revisión del diff contra el contrato, re-correr las suites, revisión de Mario y merge `--ff-only` | — | S | F1 | suites verdes en `main` |
| F3 | proyecto 38 (API reiniciada desde el árbol principal): medir línea base (`check_interference`, `delivery_check(con_gravedad=true)`, FEA «Bastidor portante» con las 6 patas fijas) → `save_revision` → cirugía de D10 → re-medir → `save_revision` | datos (MCP/REST) | M | F2 + elección de D10 | mismas tres mediciones sin regresión; render aislado de una garrucha |
| F4 | bitácora con los números, `nota:` y estado | docs | S | F3 | — |

**Tests de F1** (en `tests/test_catalog_garruchas.py`, más el conteo):
- las 24 refs cargan, son `garruchas`, `weight > 0`, construyen con `volume > 0`, no cortables;
- bbox: `max.Z == 0` (cara de montaje en el origen), `min.Z == −altura`, huella ≥ placa;
- el apoyo al piso (franja z ∈ [−altura, −altura+3]) está centrado en x = −avance en la giratoria
  y en x = 0 en la fija;
- los 4 centros de agujero (y los dos extremos de la ranura) quedan FUERA del sólido a media placa;
- la variante con freno se extiende más en −X que la giratoria del mismo Ø (pedal);
- el builder rechaza `tipo` desconocido y una altura sin lugar para la horquilla;
- `loader` rechaza un builder repetido entre registros;
- `component_anchors` de una garrucha da `placa`; `CAT2SUB["garruchas"] == "Estructura"`;
  `"garruchas" in FEA_HARDWARE_CATS` y `not in HARDWARE_CATS`;
- un `insert_component` con `position` (x, y, h) deja la cara superior de la placa en z = h.

## 7. Lo que este plan NO hace

- No agrega una verificación «carga por garrucha vs capacidad» a la memoria de cálculo (el dato
  `carga_kg` queda listo para eso; va al [backlog](../backlog.md)).
- No modela la garrucha articulada (giro de la horquilla como junta); la pose es la canónica.
- No parte `builders.py`.
- No toca precios firmes: los cotiza Mario.

## 8. Riesgos

- **Datos Colson incompletos** → declarados en `no_publicado` y en el YAML; se corrigen al
  cotizar. F1 re-verifica las fichas en el navegador.
- **El 38 es el testigo del benchmark**: la cirugía cambia masa, BOM y planos → la bitácora
  registra los números antes/después y la revisión previa permite volver.
- **Placa base más grande choca con travesaños o patas vecinas** → `check_interference` antes
  y después; si choca, se ajusta el tamaño hacia el lado libre y se anota.
- **Llave sobre la tuerca junto a la pata** (agujero a ~13 mm de la cara del tubo 50×50 en Y):
  hoy es peor (5 mm con 80×60); se anota en la bitácora.
- **Reinicio de la API**: verificar el dueño real del :8000 (zombie-socket, raíz) antes de dar
  por cargado el código nuevo.

## 9. Bitácora

### F1 + F2 (2026-10-06): código implementado y revisado

- Implementó un subagente en worktree (commit original `4bf4e2d`, traído por cherry-pick sobre el
  `main` del día). 24 refs (231 → 255), `builders_rodaje.py` (193 líneas), `merge_builders` en
  `loader.py`, ancla `placa`, «Estructura» en backend y UI, `garruchas` en `FEA_HARDWARE_CATS`,
  88 tests en `tests/test_catalog_garruchas.py`. Sin bump de epoch ni de versiones:
  `test_contrato_comandos` verde (D9 confirmado).
- **Lo que reveló medir**: con una booleana por parte, la Blickle (ranura = cilindro + caja +
  cilindro) tardaba ~0.8 s en construirse; un solo `fuse` + un solo `cut` y la ranura como
  estadio extruido la bajan a ~0.3 s (la UCP tarda ~1 s).
- **Fichas Colson re-verificadas en el navegador** (Wayback): alturas, placa 5"×4", patrón
  3 3/4"×3", radios de giro, banda 1 3/4" y cargas PU de 5" (250) y 6" (400) coinciden; no se
  corrigió ningún número. Hallazgo: la serie 45 codifica el freno como **FTR**, no FTO (queda en el
  YAML; la ref sigue con `-FT`). El listado PDF no se pudo paginar: las cargas PU de 4" (200) y 8"
  (400) quedan sin re-verificar.
- Desviaciones aceptadas en la revisión: `radio_giro` sólo en las que giran (en la fija confunde);
  validaciones extra del builder (medidas > 0, `y_max ≥ y_min`, `avance ≥ 0`) que hacen fallar un
  YAML malo al CARGAR el catálogo; tests extra (avance Colson = fórmula de D3; el mapeo de
  `Tree.tsx` leído como texto).
- Revisión visual: render offline de `COLSON-5X2-PU-45-A-FT`, `LH-ALTH-125K-3-ST` y
  `BH-ALTH-125K-3`: placa con agujeros, rueda detrás en −X en las giratorias, pedal atrás.
- Suites re-corridas por la sesión principal sobre el código del worktree: pytest **1922 passed,
  1 skipped**; ruff verde; vitest 159; `npm run build` OK. (La corrida del subagente dio 4
  timeouts en `test_drawing_v72.py` con otras dos suites en paralelo; solo, verde.)
- **Hallazgo para F3**: en el 38, el `run_script` de los 24 pernos (`c1229`) está SUPRIMIDO
  («superó el límite de 60 s» al recargar con la máquina cargada) y arrastra al fijador
  `tornilleria_garruchas` (`c1242`). Causa: 24 fusiones acumuladas (`res + b`). En F3 se edita
  al patrón nuevo construyendo UN juego y copiándolo en un `Compound`, sin booleanas acumuladas.
