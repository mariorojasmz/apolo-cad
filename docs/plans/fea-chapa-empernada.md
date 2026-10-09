---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: contrato aprobado (D1–D9, 2026-10-07); F1–F4 hechas; falta F5 — el E2E sobre el proyecto 72 (espera que Mario importe su base), las reglas D9 en los CLAUDE.md de fea y kernel, devlog y las notas de V7.4 y del backlog
descripcion: El FEA del bastidor malla la chapa plegada y empernada (travesaños con pestañas en las cuatro caras), acepta cargas sobre un taladro y, si gmsh no puede, responde un 400 que nombra la pieza y qué hacer
---

# El FEA del bastidor malla la chapa plegada y acepta cargas en sus taladros

## Estado y origen

Pedido de Mario (2026-10-07), sobre el proyecto 72 («faja-paqueteria-4m-chapa-c»: largueros de
chapa C con `create_sheet_metal`, travesaños de chapa cuyas pestañas se emPERNAN al alma con
taladros coincidentes). Al correr `POST /api/fea/assembly` aparecieron tres problemas:

1. Con 25 ids (4 largueros, 2 cubrejuntas, 5 travesaños, 2 mesas, 6 placas cabezal, 6 patas) a
   `mesh_size_mm` 35: **500** «Error interno: Invalid boundary mesh (overlapping facets) on
   surface 730 surface 737». Sin travesaños ni cubrejuntas (18 piezas) resolvía: FS 3.38, 455 s.
   Su sospecha: el fragment de los taladros coincidentes deja superficies cilíndricas solapadas.
2. Una carga con `{mode: 'cerca', point: [3806, 391.5, 811]}` sobre c1442 resuelve el taladro
   Ø40 en el kernel, pero el FEA responde 400 «No encontré en la malla la cara con centro
   (3786.0, 391.5, 791.0) y área 377.0 mm²». Además `cerca` elige por distancia al CENTRO de la
   cara: un punto SOBRE la cara exterior del alma eligió un taladro vecino.
3. El 500 debería ser un 400 accionable.

Pidió: (a) test mínimo; (b) que el bonded de chapas empernadas malle y el error residual sea un
400 que nombre las piezas; (c) poder cargar un taladro de chapa; (d) evaluar si `cerca` debe
medir a la superficie, con plan si cambia semántica; revisar el tope de 25 sólidos; la regla
durable en el CLAUDE.md que corresponda.

**Aprobado por Mario el 2026-10-07, sin vetos** (D1–D9).

## El problema / lo que hay hoy

Medido en la F0 (Bitácora) sobre una COPIA de `data/apolo.db`, con los STEP de las 25 piezas
volcados del proyecto 72 y gmsh 4.15.2 directo, sin la API.

- **(1) No son los taladros coincidentes: es la ESQUINA de la chapa plegada.** El travesaño c1446
  SOLO, sin ninguna otra pieza, falla con el mismo error (superficies 3 y 6: los dos radios de
  plegado de una esquina). Las 20 piezas CON cubrejuntas (6 taladros Ø11 coincidentes con el
  alma) y sin travesaños mallan (93 833 tets, 9.5 s). Las 25 juntas fallan siempre en el
  travesaño.
  - Mecanismo: el travesaño tiene pestañas en las cuatro caras (`flaps` izquierda, derecha,
    frente, atrás, `radio` 3). `library/sheetmetal.py::_fillet_bends` redondea las aristas
    cóncavas base↔pestaña y, en cada esquina, los dos cilindros de r = 3 mm se cortan en
    INGLETE. OCCT dice que el sólido es válido (`is_valid` True); gmsh, a una malla 10-100×
    mayor que el radio, discretiza cada cuarto de cilindro con 1-2 cuerdas y las facetas de los
    dos cilindros se cruzan junto al inglete.
  - Reproducción mínima: `sheet_metal_solid(60, 780, 3, flaps=[izquierda, frente], radio=3)`
    → falla a 35 mm. Con pestañas OPUESTAS (izquierda + derecha, sin esquina) malla; con
    `radio=0` malla. Falla a 35, 10, con `MeshSizeFromCurvature` 12, con `MinimumCirclePoints` 8
    y con los algoritmos 2D Delaunay y Frontal; malla a 5 mm (30 787 tets sólo el travesaño).
  - `fea_static` también falla: el travesaño solo a su malla por defecto (diag/15 ≈ 52 mm). La
    regla vigente de [fea](../../core/apolo/fea/CLAUDE.md) («la chapa fina se analiza aparte como
    placa con `fea_static`») hoy no funciona para la chapa plegada con esquinas.
  - **Tras un `generate` fallido gmsh no vuelve a mallar el MISMO modelo**: `mesh.clear()` +
    `generate(3)` devuelve 0 tets sin error. Un reintento exige reconstruir el modelo
    (`finalize` → `initialize` → importar → fragmentar).
- **(2) El descriptor de cara del FEA usa un punto que no es el centroide.**
  `fea/mesher.py:36-38` (`FaceDesc.from_face`) toma `face.center()`, y en build123d 0.10 el
  default es `CenterOf.GEOMETRY`: en una cara CURVA, el punto de la superficie en la MITAD de su
  dominio uv (en una plana build123d ya da el centroide: corregido en la Bitácora F1). gmsh
  (`occ.getCenterOfMass`) da el centroide real. En un cilindro COMPLETO difieren exactamente
  en r. Medido: en una placa con un taladro Ø40 el kernel da
  (30, 50, 1.5) y gmsh (50, 50, 1.5); en c1442 el Ø40 da 3786 (kernel) vs 3806 (gmsh) y el Ø17,
  3732.5 vs 3741.0. La tolerancia de `_match_surfaces` es 1e-3·diag (≈ 4 mm en la faja) → todo
  taladro de r > 4 mm es inencontrable, en el ensamblaje y en `fea_static`.
- **(3) `gmsh.model.mesh.generate(3)` no está envuelto** en `mesh_assembly`
  (`mesher.py:312`) ni en `mesh_step` (`mesher.py:108`): el `Exception` de gmsh sube como 500.
  El `fragment` sí lo está (`mesher.py:242-251`).
- **(d) `cerca` mide al centro uv.** `kernel/selectors.py:71-76` (aristas) y `:105-110` (caras)
  ordenan por distancia a `obj.center()` (GEOMETRY). Medido en c1442, punto sobre la cara
  EXTERIOR del alma a 28 mm del eje del Ø40: `cerca` elige el cilindro de un Ø17 vecino; por
  distancia a la superficie, la cara del alma (24 ms para 55 caras, contra 9 ms hoy). Un punto
  sobre la superficie del Ø40 (el caso de Mario) elige el Ø40 con los dos criterios.
- **Tope de 25 sólidos** (`mesher.py:25`): el `fragment` de las 25 piezas tarda 1.4 s; con 50,
  4.2 s; con 75, 10.3 s (copias desplazadas del mismo ensamblaje). La malla de las 25, 7-11 s.
  Lo que tarda minutos es el solve, que depende de los tets y ya tiene su tope (`MAX_TETS`
  150 000 + el estimador por bbox). Una estructura empernada de chapa multiplica PIEZAS (en el 72:
  5 travesaños, 2 cubrejuntas, 6 placas) sin multiplicar tets.
- **Las uniones empernadas se analizan PEGADAS sin decirlo.** La hipótesis del resumen dice
  «ensamblaje PEGADO (bonded)… sin contacto/fricción», y [fea](../../core/apolo/fea/CLAUDE.md)
  justifica el bonded para un bastidor SOLDADO. El 72 es empernado: pegado = sin deslizamiento
  ni separación en la junta, más rígido que la realidad.

## Lo que se revisó antes de escribir esto

- **Los vecinos del fragment del 72**: las 25 piezas quedan conectadas por interfaz compartida
  (cada travesaño con sus dos largueros, cada cubrejunta con los dos tramos, cada placa con su
  pata y su larguero; ninguna suelta). Arreglada la malla, la guarda de cuerpo rígido no lo
  frenaría.
- **Dos remedios para la malla, medidos en las 25 piezas** (detalle en la Bitácora):
  - *Refinar localmente*, sin tocar la geometría: un campo `Distance` + `Threshold` sobre las
    curvas donde se tocan dos radios chicos (el inglete), con SizeMin = r, DistMin = r,
    DistMax = 2r → 99 397 tets a 35 mm (+5.6 k sobre las 20 piezas sin travesaños). A 50 y a
    120 mm el inglete no alcanza (falla otro par de radios del mismo travesaño); refinando las
    curvas de TODOS los radios chicos malla a 20, 35, 50, 80 y 120 mm.
  - *Quitar los radios* (`gmsh.model.occ.defeature` de los cilindros parciales de r < size/4):
    malla a todos los tamaños con menos tets (94 312 a 35 mm), pero AGRANDA las caras vecinas
    (una pestaña de 34 mm pasa a medir 37): el match por centro + área ±1 % de una carga o un
    empotramiento sobre esas caras deja de encontrarlas, y la geometría analizada deja de ser la
    del CAD.
- **Quién usa `cerca` con logs PERSISTIDOS**: mates (`ref_a`/`ref_b`), fillet/chamfer
  (`edges`), modelado directo (`faces`), `snap_to` cara-a-cara y el clic del viewport
  (`ui/src/forms/SchemaForm.tsx:278`, que guarda `{mode: "cerca", point, count, entidad}`).
  `get_topology` publica el MISMO punto (`kernel/topology.py:48`, `face.center()`): hoy el centro
  que lee el agente y el que mide `cerca` son el mismo, por eso copiar un centro de
  `get_topology` elige exactamente esa cara. Cambiar el default re-resolvería logs viejos a
  otras caras (raíz: «un log viejo regenera igual»).
- **Los trinquetes de tamaño**: `commands/models.py` (1387), `mcp_server.py` (1429) y
  `ui/src/forms/SchemaForm.tsx` (591) están en su tope exacto (`tests/test_tamano_archivos.py`,
  `ui/src/tamanoArchivos.test.ts`). Un campo nuevo en `EdgeSelector` obliga a sacar los modelos
  de selector a su módulo; los docstrings del MCP se reescriben sin sumar líneas.
- **Los FaceDesc no se persisten**: se calculan en cada análisis (`services/fea_setup.py`) y
  mueren con él. Cambiar cómo se calcula el centro no toca ningún resultado guardado ni el log.
  `en_encastre` (`fea/assembly.py:123-126`, `fea/static.py:86-88`) usa el centro de las caras
  fijas: bases planas rectangulares, donde los dos centros coinciden.
- **Ninguna geometría del CAD cambia** en este plan: ni `sheetmetal.py` ni ningún executor. Sin
  bump de `GEOM_CACHE_EPOCH` ni de versiones.

## Decisiones (para vetar)

- **D1. Los taladros coincidentes NO se rellenan ni se tocan.** Medido: no son la causa. Una
  unión empernada queda pegada sobre su superficie de contacto, con los taladros abiertos (D8 lo
  declara).
- **D2. La malla de la chapa plegada se arregla REFINANDO localmente, sin cambiar la geometría,
  en dos etapas**, en un módulo nuevo `fea/refine.py` que usan `mesh_assembly` y `mesh_step`:
  1. Antes de mallar: radios chicos = superficies NO planas, ABIERTAS (un taladro completo no
     entra) y de radio de curvatura < size/4; se refinan las curvas que comparten dos de ellos
     (el inglete de la esquina) con SizeMin = max(r, 1 mm), DistMin = SizeMin,
     DistMax = 2·SizeMin, y `MeshSizeMin` baja a ese valor sólo si hay refinamiento.
  2. Si `generate` falla y hay radios chicos: se RECONSTRUYE el modelo (gmsh no re-malla el
     mismo tras un fallo) y se refinan las curvas de TODOS los radios chicos. *Enmienda de la
     revisión de F2*: en esta etapa «chico» es r < size/2 (no size/4), porque entre size/4 y
     size/2 la esquina también falla y la etapa 1 no tenía nada que refinar; como sólo corre
     tras un fallo, nada de lo que hoy malla cambia (Bitácora F2).
  3. Si vuelve a fallar → D3.

  Sin radios chicos no se crea ningún campo: los modelos de hoy mallan byte-idéntico. El
  resultado declara el refinamiento (`malla.refinamiento` {etapa, radios, r_min_mm} y una línea
  de hipótesis «malla refinada localmente en N radios de plegado (r = 3 mm)»).
- **D3. Todo fallo de `generate` es un 400 (`FeaError`) que nombra las piezas y da salida.**
  Las superficies que gmsh nombra → sus volúmenes → la pieza (nombre + id); el texto dice qué
  superficie (tipo y radio si es curva), con qué malla, y tres salidas: excluir la pieza del
  grupo, analizarla sola con `fea_static` a una malla del orden de unos pocos espesores (el
  travesaño solo malla a 5 mm), o cambiar `mesh_size_mm` (otro tamaño puede mallar: F0).
  Un error de gmsh sin superficies identificables → 400 con el texto de gmsh y las mismas
  salidas. `PieceMesh` gana `name` opcional para el mensaje (`fea/assembly.py` ya lo tiene).
- **D4. `FaceDesc.from_face` usa el CENTROIDE (`CenterOf.MASS`)**, el mismo que calcula gmsh.
  Sólo en `fea/`: `get_topology` y `cerca` siguen con el punto uv (D5). El mensaje «No encontré
  en la malla la cara…» suma el tipo de la cara buscada.
- **D5. `cerca` NO cambia su default; gana una clave opcional `medir`: `"centro"` (default, el
  de hoy) | `"superficie"`** (distancia del punto a la cara o arista, desempate por centro). Vale
  para caras y aristas, en todos los consumidores. Un log viejo no la trae → resuelve igual. La
  clave entra a `EdgeSelector`, que sale con los modelos de selector a
  `commands/models_selectores.py` (re-exportados por `models.py`, que baja su trinquete). Los
  docstrings de `fea_static`/`fea_assembly` dicen que para cargar un taladro o una cara grande
  junto a taladros se use `medir: "superficie"` con un punto SOBRE la cara (golden re-congelado).
- **D6. El clic del viewport guarda `medir: "superficie"` en las selecciones NUEVAS.** El punto
  del clic está sobre la cara clicada por construcción, así que con superficie gana la cara que
  la persona tocó (hoy puede ganar un taladro vecino). Las selecciones guardadas no se tocan.
  Recomendado; si se veta, queda en el [backlog](../backlog.md).
- **D7. `MAX_PIECES` sube de 25 a 50.** El costo medido del fragment con 50 piezas es 4.2 s; el
  control real del tiempo es `MAX_TETS` + el estimador por bbox, que no cambian. Se sigue
  validando ANTES de exigir gmsh.
- **D8. Las uniones empernadas se DECLARAN en la hipótesis.** `prepare_assembly` cuenta los
  fasteners `perno` cuyas dos piezas están en la malla y, si hay alguno, el resumen suma:
  «N unión(es) empernada(s) modeladas PEGADAS sobre su superficie de contacto (sin
  deslizamiento ni separación: más rígido que la junta real); el perno se verifica aparte
  (engineering_check)». Una soldadura no la suma: para ella pegado es la hipótesis correcta.
- **D9. Las reglas durables van a [fea](../../core/apolo/fea/CLAUDE.md)** (centroide del
  `FaceDesc`; esquinas de chapa = refinamiento local en dos etapas; gmsh no re-malla tras un
  fallo; todo fallo de malla = 400 con piezas), corrigiendo la línea de la chapa fina, y una
  línea en [kernel](../../core/apolo/kernel/CLAUDE.md) (`cerca` mide al punto uv que publica
  `get_topology`; `medir: "superficie"` es opt-in y el default no cambia por los logs viejos).

## Alternativas descartadas

- **Rellenar los taladros coincidentes de las uniones con perno** (la idea original): resuelve un
  problema que no existe (F0) y añadiría un booleano por unión antes del fragment.
- **Quitar los radios chicos para el FEA (`defeature`)**: menos tets (94 k contra 99 k a 35 mm)
  y sin reintentos, pero cambia la geometría analizada y rompe el match de caras vecinas a los
  radios; habría que rastrear el historial OCCT de cada cara seleccionada. Queda como respaldo si
  el refinamiento resultara caro en otra máquina.
- **Refinar siempre todos los radios chicos** (sin etapa 1): 130 k tets a 35 mm contra 99 k, al
  borde del tope de 150 k.
- **`Mesh.MeshSizeFromCurvature` global**: con el mínimo de hoy (size/3) no malla; con mínimo
  1 mm malla, pero 50 k tets y 27 s SÓLO el travesaño.
- **Cambiar la chapa (alivio de esquina en `sheetmetal.py`)**: cambia la geometría de todo
  proyecto con pestañas adyacentes (epoch, planos, desplegados) para arreglar un problema del
  mallador. Si algún día se modela el alivio, será por fabricación, no por el FEA.
- **Cambiar el default de `cerca`**: re-resolvería mates, fillets y modelado directo de logs
  viejos a otras caras.

## Fases

Cada fase la implementa un subagente en worktree (`opus`, segundo plano); la sesión principal
revisa el diff contra este contrato y re-corre las suites.

- **F0 — medir** (sólo lectura). Hecha: Bitácora.
- **F1 — el FEA encuentra la cara de un taladro y nunca da 500 por la malla** (D3, D4). `fea/`
  (`mesher.py`, `assembly.py`, `static.py`). S. Sin dependencias. Tests: placa con taladro Ø40 →
  `fea_static` con la carga sobre el cilindro del taladro resuelve (hoy 400 «No encontré»);
  `generate` que falla (el travesaño de 4 pestañas a 35 mm, antes de F2; después, un
  monkeypatch con un error de superficies reales) → `FeaError` que nombra la pieza por nombre e
  id; por la API, `POST /api/fea/assembly` → 400 (no 500).
- **F2 — la chapa plegada con esquinas malla** (D2). `fea/refine.py` nuevo + `mesher.py`
  (reconstrucción por etapas dentro del mismo `FEA_LOCK`; de paso, un grupo de UNA pieza no
  pasa por `fragment`: hallazgo de F1). M. Depende de F1. Tests: el mínimo
  pedido — una bandeja de chapa con pestañas adyacentes y r = 3 empernada con taladros
  coincidentes a una chapa C, en contacto → `mesh_assembly` + solve dan FS y flecha finitos y la
  hipótesis declara el refinamiento; `mesh_step` de la bandeja a 35 mm malla (etapa 1) y a un
  tamaño donde la etapa 1 no alcanza (lo mide F2) malla en la etapa 2; un modelo sin radios
  chicos no crea campos (mismo número de tets que antes). Los tests asertan éxito y cordura,
  no un número de tets exacto (cambia con la versión de gmsh).
- **F3 — `cerca` con `medir: "superficie"`** (D5, D6). `kernel/selectors.py`,
  `commands/models_selectores.py` (nuevo) + `models.py`, `mcp_server.py` (docstrings, sin sumar
  líneas), `ui/src/forms/SchemaForm.tsx` (D6). M. Independiente de F1-F2. Tests: el caso del
  alma de c1442 reproducido en una placa con taladros (centro → taladro vecino; superficie →
  la cara); un log con `cerca` sin `medir` resuelve igual que antes (mates, fillet, snap);
  strict acepta `medir` y rechaza un valor inválido; golden MCP re-congelado; vitest + build.
- **F4 — tope y declaración de pernos** (D7, D8). `fea/mesher.py`, `services/fea_setup.py`,
  `api/fea_runs.py` (sumar la hipótesis). S. Depende de F1. Tests: 26 piezas ya no se rechazan
  y 51 sí; un grupo con un fastener `perno` entre dos piezas mallas declara la unión y uno con
  `soldadura` no.
- **F5 — verificar y documentar** (D9). E2E sobre una COPIA de la base: el FEA de las 25 piezas
  del 72 a 35 mm (FS por pieza, tiempo, hipótesis), una carga sobre el Ø40 con
  `medir: "superficie"` y un fallo forzado que responde 400. CLAUDE.md de `fea` y `kernel`,
  `docs/devlog.md`, la `nota:` de [V7.4](V7.4-fea-firmable.md) y del
  [backlog](../backlog.md) (chapa fina en el ensamblaje), conteos de «Estado actual» en la raíz.
  El E2E por MCP en su máquina queda de Mario.

## Lo que este plan NO hace

- No modela pernos ni contacto: el bonded sigue siendo pegado; D8 sólo lo declara.
- No cambia la geometría de la chapa (sin alivios de esquina) ni el desplegado.
- No cambia el default de `cerca` ni re-escribe selecciones guardadas.
- No hace la placa/cáscara para chapa fina (elementos shell): la chapa se sigue mallando en
  sólido.
- No acelera el solve (455 s con 18 piezas): fuera de alcance.

## Riesgos

- **El refinamiento sube los tets** (99 k a 35 mm en el 72, tope 150 k) → con mallas más finas
  se llega antes al tope. Mitigación: sólo la etapa 1 en el caso normal; el error del tope ya
  pide subir `mesh_size_mm`.
- **El reintento duplica la malla** cuando la etapa 1 no alcanza (+1-3 s de reconstrucción y la
  malla otra vez). Aceptable frente a minutos de solve; el resultado declara la etapa.
- **Otra versión de gmsh malla distinto**: `pyproject` pide gmsh ≥ 4.13 y se midió con 4.15.2.
  Mitigación: los tests asertan éxito y cordura, no números exactos; F2 verifica que
  `getPrincipalCurvatures`/`getParametrizationBounds` existen desde 4.13.
- **Radios que no son cilindros** (los fillets genéricos de OCCT dejan toros, esferas o
  B-splines): la clasificación usa la curvatura, no el tipo; la etapa 2 y el 400 de D3 cubren lo
  que la etapa 1 no reconozca.
- **`medir: "superficie"` en una arista entre dos caras** da distancia 0 a ambas: desempata el
  centro, como hoy. Documentado en el docstring.

## Bitácora

### F0 — medición (2026-10-07)

Proyecto 72 cargado de una COPIA de `data/apolo.db` (268 s en frío, sin caché de geometría),
STEP de las 25 piezas volcados con `export_step_file`; gmsh 4.15.2, build123d 0.10.0.

| experimento | resultado |
|---|---|
| 25 piezas, 35 mm (lo de Mario) | fragment 1.2 s; 2D ok; 3D **falla**: superficies 730 y 737, ambas cilindros de c1446 (radio de 3637 mm² a lo largo + radio de 244 mm² de la pestaña del extremo) |
| c1446 solo, 35 mm | **falla** igual (superficies 3 y 6) |
| c1468 (cubrejunta), c1442 (larguero C), c1456 (mesa) solos | mallan (2 207 / 15 664 / 25 795 tets) |
| 20 piezas: sin travesaños, CON cubrejuntas | malla: 93 833 tets, 9.5 s |
| c1446 con opciones de gmsh | falla: 35, 10, curvatura 12, mín. 2 mm, 8 puntos por círculo, Delaunay, Frontal · malla: 5 mm (30 787 tets), curvatura 12 + mín. 1 mm (49 995 tets, 27.5 s) |
| bandeja 60×780×3, `radio` 3 | izq+der (sin esquina) malla · izq+frente **falla** · 4 lados **falla** · 4 lados con `radio` 0 malla · izq+frente con `radio` 0 malla. `is_valid` True en todas |
| 25 piezas, refinar ingletes (SizeMin r, DistMax 2r) | 35 mm: 99 397 tets · 20 mm: 215 710 (> tope) · 80 mm: 42 194 · 50 y 120 mm: **falla** en otro par de radios de cada travesaño |
| ídem, DistMax = size (35 mm) | 118 736 tets |
| 25 piezas, refinar TODOS los radios chicos | 20: 274 456 · 35: 130 417 · 50: 91 146 · 80: 57 553 · 120: 44 603 (todas mallan) |
| 25 piezas, `defeature` de los radios chicos | 20: 208 569 · 35: 94 312 · 50: 62 211 · 80: 40 048 · 120: 32 932 (todas mallan) |
| reintento sobre el MISMO modelo tras un fallo | 0 tets sin error → hay que reconstruir; reconstruyendo y sumando las superficies nombradas, 50 y 120 mm mallan al 6.º intento (una vuelta por travesaño) |
| centro de un cilindro completo Ø40 | gmsh = centroide (eje); build123d `face.center()` = punto uv sobre la cara, a r del eje. c1442: Ø40 3806 vs 3786, Ø17 3741 vs 3732.5 |
| `cerca` en c1442, punto sobre la cara exterior del alma a 28 mm del Ø40 | centro → cilindro del Ø17 vecino (9.5 ms) · superficie → cara del alma (23.8 ms, 55 caras) |
| `cerca`, punto sobre la superficie del Ø40 | centro y superficie → el Ø40 |
| fragment con copias del ensamblaje | 25 piezas 1.4 s · 50 piezas 4.2 s · 75 piezas 10.3 s |
| vecinos por interfaz tras el fragment de las 25 | todas conectadas; ninguna suelta |

**Diagnóstico equivocado y su causa**: se sospechó del fragment de los taladros coincidentes
porque el fallo apareció al SUMAR travesaños y cubrejuntas a la vez, y las dos familias tienen
taladros coincidentes con el alma. Mallar cada familia por separado (y el travesaño solo) lo
descartó: la causa estaba dentro de una pieza, no en una interfaz.

### F1 — la cara de un taladro y el 400 (2026-10-07)

Commit `efc4193`. `FaceDesc.from_face` usa `CenterOf.MASS` y lleva el tipo de cara para el
mensaje de «no encontré». El `generate(3)` de `mesh_step` y de `mesh_assembly` pasa por
`fea/fallo_malla.py::generar_3d`, que ANTES del `finalize` lee las superficies que nombra
gmsh (tipo, área, radio por curvatura, volúmenes → pieza) y lanza `FeaError` con la pieza por
nombre e id y tres salidas. `PieceMesh.name` y `mesh_step(pieza=)` llevan el nombre.
10 tests nuevos en `tests/test_fea_chapa.py` (fallos simulados con un `generate` que nombra
superficies REALES del modelo vivo: la geometría que hoy falla mallará tras F2).

- **Antes / después, medido con el código viejo**: placa con Ø40 → «No encontré… centro (30.0,
  50.0, 1.5)» (gmsh: 50, 50, 1.5); manto de un eje con un taladro transversal → no casaba (15 mm
  entre los dos centros); por la API, carga con `cerca` sobre el centro que publica
  `get_topology` → 400. Después, los tres resuelven.
- **Premisa corregida**: en una cara PLANA build123d 0.10 ya da el centroide con
  `CenterOf.GEOMETRY` (`is_planar` → `SurfaceProperties`). Lo que no casaba eran las caras
  CURVAS: taladros y mantos con agujeros. El test de la cara plana con agujero descentrado queda
  como guarda; el que fallaba de verdad es `test_carga_en_cara_curva_con_agujero`.
- **El travesaño real (c1446) a 35 mm**, antes `builtins.Exception: Invalid boundary mesh
  (overlapping facets) on surface 3 surface 6`, ahora: «gmsh no pudo mallar «Travesaño de chapa
  A36 (1)» con malla de 35 mm (…). Superficies que nombra gmsh: 3 cilindro r ≈ 3 mm, 3637 mm²;
  6 cilindro r ≈ 3 mm, 244 mm². Un radio de 3 mm frente a una malla de 35 mm queda con una o dos
  cuerdas y sus facetas pueden cruzarse. Qué hacer: …». En el ensamblaje lleva además el id
  (c1446).
- **Fuera del contrato, aceptado en la revisión**: la frase de las «cuerdas» cuando el radio es
  < size/4 (dato de la F0); en `fea_static` el mensaje nombra la pieza sin id
  (`run_static_analysis` no recibe el feature_id).
- **Hallazgo**: `gmsh.model.occ.fragment` de UN solo volumen sin herramientas devuelve
  `out = []` y `outmap = []` (el volumen sigue en el modelo) → `fea_assembly` de un grupo de una
  pieza responde «Ninguna pieza sobrevivió a la fragmentación». Verificado aparte en gmsh 4.15.2.
  Se arregla en F2, que reestructura esa misma función.
- Revisión: FEA (`test_fea_chapa` + `test_fea` + `test_fea_assembly`) 44/44; ruff limpio.

### F2 — la chapa plegada con esquinas malla (2026-10-07)

Commit `a7f4d33`. `fea/refine.py` (nuevo): radios chicos por CURVATURA (superficies abiertas
no planas, 1/κmáx en el centro uv; lo que da la vuelta completa —taladro, manto— no entra),
curvas del inglete, el campo `Distance` + `Threshold` y la línea de hipótesis. `mesher.py`:
`_mallar` corre como mucho dos intentos dentro del mismo `FEA_LOCK`, con
`_construir_pieza`/`_construir_ensamblaje` reutilizables (los errores de construcción no se
reintentan); `_fragmentar` no llama a `fragment` con un solo volumen. Ambas mallas devuelven
`refinamiento` {etapa, radios, r_min_mm} y el resumen lo declara en la hipótesis.

- **Desviación aceptada en la revisión**: la etapa 2 usa radios < size/2. Con el umbral del
  contrato (size/4), c1446 y la bandeja a 8-11 mm (r/size entre 0.27 y 0.38) fallaban sin nada que
  refinar y sin reintento — y el 400 de D3 recomienda justo «unos pocos espesores». Descartado
  size/2 también en la etapa 1: malla en un intento (c1446 a 8 mm: 13 665 tets contra 21 526),
  pero cambiaría mallas que hoy salen bien.
- **El test mínimo prueba algo**: la bandeja 60×200×3 con pestañas frente + izquierda, r = 3 y
  dos Ø11 coincidentes con un alma de 3 mm, SIN refinar a 35 y 25 mm → `FeaError` «overlapping
  facets on surface 3 surface 10»; con F2 a 35 mm → etapa 1, 1092 tets, FS 6.5, flecha 0.37 mm.
- **Los STEP reales del 72**: c1446 solo → malla por defecto (52.2 mm) etapa 2, 3121 tets; a
  35 mm etapa 1, 1497 tets; malla de 4 a 120 mm. Las 25 piezas (28 radios, r mín 3): 35 mm etapa
  1, 99 397 tets (el número de la F0), 8.6-15 s · 50 mm etapa 2, 91 146 · 80 mm etapa 1,
  42 194 · 120 mm etapa 2, 44 603 · 20 mm pasa el tope de 150 k (error del tope, como dice el
  contrato).
- **gmsh 4.13** (piso de `pyproject`): las opciones de `Distance`/`Threshold` y
  `getPrincipalCurvatures`/`getParametrizationBounds` existen en el tag `gmsh_4_13_0` (leído en
  el fuente, no ejecutado).
- **Ajuste de la revisión**: dos tests aseguraban la etapa EXACTA (medida sólo en Windows con
  gmsh 4.15.2); ahora asertan que malla refinada y la etapa admisible (1-2 para la bandeja a 35
  mm; 0 o 2 a 10 mm, donde la etapa 1 nunca refina). El camino de la etapa 2 lo fija el test
  determinista con un `generate` que falla una vez.

### F3 — `cerca` con `medir: "superficie"` (2026-10-08)

`kernel/selectors.py`: `resolve_faces`/`resolve_edges` comparten `_cerca`; sin `medir` (o con
`null`) es el código de antes línea por línea; con `"superficie"` ordena por la distancia OCCT
(`BRepExtrema_DistShapeShape` contra un vértice), redondeada al µm, y desempata por el centro de
siempre. Un `medir` inválido es `SelectorError` en todo modo (las cargas del FEA y `measure`
llegan como dict, sin pydantic). `EdgeSelector` (con `medir: Literal["centro","superficie"] |
None = None`) y `SlideUV` salen a `commands/models_selectores.py`, re-exportados por `models.py`
(1387 → 1359). El clic del viewport arma la selección en `ui/src/forms/selector.ts::
seleccionDelClic` con `medir: "superficie"`; `normalizeSelector` la conserva y no la agrega a una
selección guardada (`SchemaForm.tsx` 591 → 553). Los docstrings de `fea_static`/`fea_assembly`
piden superficie para cargar un taladro (`mcp_server.py` 1426 → 1425); en el golden sólo cambian
esas dos descripciones.

- **El schema publicado no cambia salvo `medir`**: JSON Schema de los 54 comandos y de la vista
  persona volcado antes y después; quitando `medir`, idéntico, orden de claves incluido. Con
  `None` de default, `model_dump(exclude_none=True)` de una selección vieja no gana la clave.
- **Sin bump de epoch ni de versiones**: sin la clave la ruta es la de antes, y ningún log
  guardado puede traer `medir` (los params estrictos rechazaban la clave). D11 de
  `test_contrato_comandos` no se movió (ningún executor cambió); D12 exigió declarar `*.medir` en
  los 9 comandos con selector, para que no pueda desaparecer sin upcaster.
- **Medido** (placa con taladros, Windows): 34 caras, centro 2.7 ms / superficie 5.9 ms; 108
  caras, 8.6 / 18.6 ms; aristas 96, 5.2 / 7.3 ms; 318, 17.2 / 25.6 ms. La razón ≈ 2.2× en caras
  coincide con la F0 (9.5 / 23.8 ms en c1442, 55 caras).
- **El caso del alma en chico**: placa 1000×100×6 con un Ø40 en (100, 50) y un Ø17 en (140, 50);
  punto (128, 50, 6), a 28 mm del eje del Ø40 → al centro gana el cilindro del Ø17, a la
  superficie la cara superior; un punto sobre el Ø40 da el Ø40 con los dos criterios. Mates,
  `snap_to` y fillet dan lo mismo sin la clave que con `"centro"` y algo distinto con superficie
  (el campo llega a cada consumidor); un test compara la ruta sin `medir` contra una copia del
  `cerca` viejo, en caras y aristas, con count 1 y 3.
- **Arista entre dos caras**: un punto sobre la arista +Y/superior de una caja está a 0 de las
  dos y gana +Y por centro; al centro puro habría ganado `max_x`, que el punto ni toca.
- **Intento fallido**: `golden_mcp.py --congelar` reescribió con LF `instructions.txt` y
  `llamadas.json` sin cambiar su contenido; se restauraron y sólo entra `list_tools.json`.
- Tests: 12 nuevos en pytest (`test_selector_superficie.py`, uno con FEA real por la API) y 4 en
  vitest (`selector.test.ts`).

### F4 — tope de 50 piezas y uniones empernadas declaradas (2026-10-08)

**D7**: `MAX_PIECES` 25 → 50, validado antes de `_require_fea`; el comentario da el porqué medido
en la F0 (fragment de 50 piezas 4.2 s, de 75, 10.3 s; el solve depende de los tets y lo acotan
`MAX_TETS` y el estimador por bbox, que no cambian). El mensaje del tope deja de decir que el
bonded «no resuelve en tiempo útil» y nombra lo que sí crece. **D8**:
`services/fea_setup.py::bolted_joints_in_mesh` cuenta los fasteners con `kind` `perno` (valores
`perno` | `soldadura` | `pegado` | `contacto`, default `perno`; `join_bolted` declara `jb_{cmd}`
con `kind: "perno"`) cuyas DOS piezas están en `struct_ids`: una unión contra el herraje excluido
o contra una pieza fuera del grupo no cuenta. `prepare_assembly` lo devuelve como
`uniones_empernadas` y `api/fea_runs.py::_fea_assembly_run` suma la línea de hipótesis en
singular o plural. Se cuentan fasteners, no pares: dos fasten sobre el mismo par pueden ser dos
superficies de contacto distintas (dos pestañas contra la misma alma).

- **Tests**: el tope con un `_require_fea` centinela (26 y 50 llegan a él sin mallar; 51 da el
  `FeaError` antes; el viejo `test_piece_cap_before_gmsh` usaba 26). El conteo sin gmsh (seis
  tipos de fastener y `join_bolted` con su tornillería excluida) y por la API (perno sí,
  soldadura no; ~0.9 s cada uno a 10 mm). Mutar el código (tope 25, contar cualquier `kind`,
  basta una pieza en la malla) los pone rojos.
- **Hallazgo ajeno a la fase, arreglado en la misma integración**: la suite completa daba 6
  fallos (`test_rutas_api` y `test_jobs_mutaciones`) también en `7a61bd7` sin tocar, y los 4 jobs
  de pytest del CI estaban rojos en `main`. Causa: la instalación limpia resolvía fastapi 0.143.0,
  y desde 0.137.0 `include_router` deja un `_IncludedRouter` sin `path` en `app.routes` en vez de
  copiar las rutas (bisección con un router mínimo: 0.136.3 la última plana). Se fijó
  `fastapi<0.137` en `core/pyproject.toml`; subirlo es un plan aparte.
