---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: contrato del 2026-10-20 (D1–D7 aprobadas por delegación de Mario); F0 medida, F1 implementada (zonas por índice de cara en library + kernel, ESTOP-40 y ESTOP-40-CAJA, epoch 6) , F2 implementada (zonas en el payload de escena y grupos de material en el visor, D3) y F3 implementada (un actor por zona en la foto VTK, una primitiva por estilo de zona en el GLB); falta F4 (verificación con Mario); el video VTK de respaldo (`render_vivo`) sigue de un acabado
descripcion: La parada de emergencia del catálogo se ve como una de verdad —seta roja sobre fondo amarillo—, y una pieza comprada puede tener partes de distinto color sin dejar de ser UNA línea de la BOM
---

# La seta de emergencia se ve como una de verdad: roja sobre amarillo

## Estado y origen

Mario (2026-10-20): «como los botones de emergencia van a estar en todas las máquinas, debemos
diseñar uno, a menos que ya exista en catálogo».

Existe en catálogo, pero sólo en lo eléctrico. `ESTOP-40`
(`core/apolo/library/data/93_mandos.yaml:8`) tiene ficha eléctrica completa: es `S` con el
símbolo `seta_emergencia`, `parada_emergencia: true`, bornes 11-12 y un camino NC. El ERC
(`library/electrico/erc.py:368`) la exige. Su geometría, en cambio, es `builder: box` de
72×72×70: un cubo de un solo color. En el video y en los planos, la pieza que más mira un
inspector de seguridad es una caja.

## El problema / lo que hay hoy

- **Geometría de relleno.** `ESTOP-40` y los pulsadores Ø22 de `123_mandos_puerta.yaml`
  (`PULS-22-ROJO-NC`, `PULS-22-AZUL-NA`, `SEL-22-2POS-1NA`) son cajas.
- **Un componente = un color.** Lo deciden `library/apariencia.py::acabado_pieza` (`:214`), el
  payload de escena (`api/scene.py:153-193`, un `acabado` y un `albedo` por pieza), el material
  del visor, VTK y el GLB. La norma pide un actuador ROJO sobre fondo AMARILLO (ISO 13850 §4.3.6,
  IEC 60204-1 §10.7.3): con un color, o es todo rojo o todo amarillo.
- **No hay kits.** Ningún YAML del catálogo declara subpiezas. Armar la seta con 3 piezas
  sueltas daría 3 líneas en la BOM para algo que se compra como UNA referencia, y rompería la
  regla de que la BOM sirve para comprar ([revision-de-taller](revision-de-taller.md) F0).

## Lo que se revisó antes de escribir esto

- La regla «el color manual sólo pinta lo pintable»
  ([visor-realista](visor-realista.md), fix del 2026-10-19, flag `pintable` de cada acabado). Aquí
  se extiende: los colores normativos de una seta NUNCA se repintan.
- La memoria del proyecto: la biblioteca es paramétrica (builder + YAML) y no se bajan STEP en
  masa. La seta se dibuja con un builder propio y las cotas típicas de la línea de referencia,
  marcadas `cotas_verificadas: false`, como los pulsadores Ø22.
- La doctrina de la raíz: «una librería que se queda corta se reemplaza por una propia». Aquí no
  hay librería de por medio; el corto es nuestro (un color por pieza) y se arregla en general,
  no con un caso especial para la seta.

## Decisiones (para vetar)

- **D1. Zonas de acabado por componente.** Un builder puede devolver sus partes etiquetadas,
  `{zona: forma}`, y el YAML asigna un acabado a cada zona
  (`zonas: {seta: pintura_roja, base: pintura_amarilla, ...}`). La pieza sigue siendo UNA
  `Feature`, con un solo sólido (la unión), una línea de BOM y una masa. Las zonas son un dato
  DERIVADO del builder: no van al log ni al manifest.

  Por qué: sirve también para la botonera, la placa del motor o el display del variador, sin
  inventar kits.

  Precisión de la F0: la etiqueta es la zona de cada CARA por su índice en el orden de
  `faces()` del sólido del builder (sale de la historia de la fusión). No va por la identidad
  del TShape, porque la caché de geometría la pierde al abrir en caliente y el orden de caras
  lo conserva. Se valida contra la forma de la pieza (mismo número de caras y volumen); si no
  calza (la pieza se taladró, por ejemplo), la pieza se ve de un solo acabado, como hoy.
- **D2. Las zonas viajan como rangos de triángulos.**
  - El teselado (`kernel/mesh.py`) marca de qué zona viene cada cara.
  - El payload de escena agrega `zonas: [{acabado, albedo, desde, hasta}]`, en índices de
    triángulos.
  - El visor arma `geometry.groups` con un arreglo de materiales.
  - VTK parte el polydata por zona.
  - El GLB pone una primitiva por zona en el mismo nodo.

  Una pieza sin zonas va exactamente igual que hoy, así que su payload no cambia.
- **D3. Los colores normativos no se repintan.** Una zona con `fijo: true` (la seta, el fondo
  amarillo) ignora `set_color`. El color de la pieza sólo pinta las zonas pintables (la caja de
  superficie, si el cliente la quiere en otro color).
- **D4. Dos referencias, según dónde se monta.**
  - `ESTOP-40`, para la puerta del tablero: seta roja Ø40 de retención por giro, collar, anillo
    de leyenda amarillo Ø60 «PARADA DE EMERGENCIA» y bloque de contactos detrás. Agujero de
    montaje Ø22,5.
  - `ESTOP-40-CAJA`, nueva, para la máquina: la misma cabeza sobre una caja de superficie
    amarilla de 72×72, con prensaestopa M20 abajo y 2 agujeros de fijación.

  Las dos llevan la misma ficha eléctrica. Cotas típicas de la línea Harmony XB5AS8445 + ZBY9…
  y Siemens 3SU1, con `cotas_verificadas: false`.
- **D5. Builder paramétrico `seta_emergencia`** en `library/` (diámetro de seta, tipo de
  montaje, alto de caja), con anclas `montaje` (cara de apoyo) y `agujero` (eje del Ø22,5, para
  `join_bolted` o el taladro de la puerta).
- **D6. La geometría de `ESTOP-40` cambia con los mismos params.** Es YAML + builder: se sube
  `GEOM_CACHE_EPOCH` con su motivo (regla de la raíz). Los tests que fijan su caja de 72×72×70
  (`tests/test_catalogo_electrico.py:162`) se actualizan a las cotas nuevas.
- **D7. Fuera de este plan, anotado para después:** los pulsadores Ø22, la botonera y el
  variador con zonas. Se hacen con el mismo mecanismo (D1–D3) cuando Mario los pida, o en
  V8.5 (el tablero 3D de verdad).

## Alternativas descartadas

- **Tres piezas sueltas (seta + collar + caja)**: tres líneas de BOM para una referencia
  comprada, y el ERC tendría que saber cuál de las tres es «la seta».
- **Textura pintada sobre la caja**: no da forma (la seta sobresale y se pulsa) y no la ve VTK.
- **STEP del fabricante**: contra la decisión de biblioteca paramétrica, con licencia por
  referencia y sin zonas de todos modos.
- **Un color por cara elegido a mano**: no es paramétrico y se rompe cuando cambian las caras.

## Fases

- **F0 (S, sólo lectura)**: medir antes de cambiar.
  1. Dónde se pierde la relación cara → triángulo en `kernel/mesh.py` y en el caché de
     teselado.
  2. Cuánto pesa en el payload agregar `zonas` (pieza sin zonas = 0 bytes).
  3. Cuánto cuesta en VTK partir un actor por zona.
  4. Cómo arma hoy las primitivas el GLB (`kernel/glb.py`).
- **F1 (M, `library` + `kernel`)**: D1, D5 y D6. Builder `seta_emergencia`, zonas en el loader y
  en el teselado, las dos referencias y el bump del epoch. Tests:
  - la seta da UN sólido y UNA línea de BOM;
  - las zonas cubren todos los triángulos;
  - las anclas caen donde deben.
- **F2 (M, `api` + `ui`)**: D2 y D3 en el payload y en el visor (grupos de material, calidad
  alta y normal, la sombra de contacto sin cambios). vitest de los grupos; pieza sin zonas
  idéntica a hoy.
- **F3 (S, `kernel/render_vtk` + `kernel/glb`)**: D2 en VTK y en el GLB de la vista web.
- **F4 (S, verificación)**: render del tablero de la faja 73 con la seta en la puerta y otra en
  la máquina. Pasan el video de video-realista y el GLB, y el ERC sigue verde. Lo juzga Mario.

## Lo que este plan NO hace

- No cambia la ficha eléctrica ni el ERC.
- No agrega la seta a las máquinas existentes: eso es modelado por MCP, máquina por máquina.
- No hace los pulsadores Ø22, la botonera ni el variador con zonas (D7).

## Riesgos

- **El teselado cacheado pierde la etiqueta de zona.** Mitigación: F0 lo mide; la zona va en el
  caché junto al teselado, por `id(shape)` con la referencia (regla de `core/apolo`).
- **Un payload más pesado en máquinas grandes.** Mitigación: sólo llevan `zonas` las piezas que
  tienen; F0 mide el máximo.
- **Un proyecto viejo abre con la seta nueva y cambia su geometría.** Es lo buscado (D6), con
  epoch. La interferencia con la puerta se revisa en F4.

## Bitácora

### F0 (2026-10-20): medición, sólo lectura

Sobre un prototipo de la seta de puerta (leyenda, collar, seta y cuerpo solapados): 1 sólido de
14 caras, 684 triángulos. Script de medición fuera del repo, en el scratchpad de la sesión.

1. **Dónde se pierde la relación cara → triángulo.**
   - `Shape.tessellate` (build123d 0.10) recorre `faces()` y concatena nodos y triángulos con
     un offset, pero no devuelve cuántos triángulos aporta cada cara.
   - `kernel/mesh.py::mesh_payload` aplana a `positions`/`indices`.
   - Las dos cachés por `id(shape)` (`_SHAPE_CACHE` de `api/scene.py`, `_RENDER_MESH_CACHE` de
     `kernel/render_comun.py`) guardan sólo ese resultado.
   - Se recupera barato: justo después de teselar, `BRep_Tool.Triangulation_s(cara)
     .NbTriangles()` en el mismo orden suma exacto el total (684 = 684, 0,7–1,5 ms). Hay que
     contar EN LA MISMA llamada: el payload (0,4/0,3) y el render (0,5/0,25) usan otra
     tolerancia angular, y un re-mallado entre medio cambiaría los conteos.
   - Identidad: `place` (la colocación de `insert_component`) comparte el TShape. La caché de
     geometría (BinTools) NO lo comparte, pero conserva el orden de caras (14 = 14, mismos
     centros) y el teselado. → La zona se guarda por ÍNDICE de cara (precisión de D1).
   - La fusión con historia (`BRepAlgoAPI_Fuse` + `Modified`/`IsDeleted`) asigna las 14 caras
     a su zona, sin huérfanas, en 42 ms.
2. **Peso del payload.** La malla de la seta pesa 26 061 B en JSON; `zonas` con 4 zonas
   (`acabado`, `albedo`, `desde`, `hasta`) suma 363 B, el 1,4 % de la pieza y unos 90 B por
   zona. Una pieza sin zonas suma 0 B. El máximo de una máquina es n.º de setas × ~360 B (una
   faja con 3 setas, ~1 KB sobre un payload de MB).
3. **VTK, partir el actor por zona.** Armar normales + aristas: 2,3 ms con 1 actor y 3,7 ms con
   4 por zona (+1,5 ms por seta). En el cuadro, 150 piezas + 4 setas dan 13,3 ms con 1 actor y
   10,8 ms con 4: ruido, no se distingue. D2 se sostiene sin colores por celda.
4. **GLB.** `glb.py` arma un prototipo por TShape, sin color, y una instancia por pieza con el
   color y el material en el componente. `SetMergeFaces(True)` da una primitiva por pieza.
   Probado: con el color por cara en sub-formas del PROTOTIPO (`AddSubShape` + `SetColor`), el
   escritor saca una primitiva por estilo (5 primitivas, 4 materiales). Para F3: el estilo
   vive entonces en el prototipo, y la regla de `glb.py` (color en el componente) se mantiene
   sólo para las piezas sin zonas. Una zona pintable repintada distinto en dos instancias
   necesita su propio prototipo.

Nada contradice D1–D7. D1 gana la precisión de arriba: la etiqueta va por índice de cara,
validada por número de caras y volumen.

### F1 (2026-10-20): zonas en `library` + `kernel`, las dos setas y el epoch

- **Kernel.** `kernel/zonas.py::fusionar_zonas` une `{zona: forma}` con `BRepAlgoAPI_Fuse` y
  da la zona de cada cara por su historia. Si quedan dos sólidos, o una cara sin zona, falla.
  `kernel/mesh.py` suma `teselar_caras`, `agrupar_por_zona` (rangos contiguos `[desde, hasta)`
  en índices de triángulo, sólo reordena) y el argumento opcional `zona_por_cara` de
  `mesh_payload`. `render_comun.teselar_zonas` usa la caché de `teselar`: su entrada guarda
  además los triángulos por cara. Sin zonas, todo sale byte a byte igual.
- **Library.** `library/zonas.py` valida el bloque `zonas:` (acabado existente, `fijo`
  booleano) y envuelve el builder: `build_component` sigue devolviendo UN sólido y queda la
  huella (caras, volumen, zona por cara). `zona_por_cara(ref, shape)` la entrega si calza.
  - El loader exige `zonas:` en un builder de `builders_mandos.ZONADOS`, la rechaza en
    cualquier otro y en una pieza cortable.
  - `Component.zonas` = las zonas del YAML.
  - 4 acabados nuevos: `plastico_rojo_seguridad` y `plastico_amarillo_seguridad` (pintables;
    los protege `fijo`), `plastico_negro` y `plastico_gris` (moldeados, no pintables).
    `ui/src/viewport/acabados.json` se regeneró con `scripts/acabados_ui.py`.
- **Builder `seta_emergencia`** (`library/builders_mandos.py`). Params: `d_seta`, `montaje`
  (puerta | caja), `d_leyenda`, `panel_mm`, `alto_caja` y `lado_caja`.
  - Origen en la cara de apoyo, +Z hacia el operador y +Y arriba.
  - Anclas `montaje` y `agujero` con eje −Z (normal saliente, como la placa de una garrucha).
  - **Decisión**: la caja agrega `fijacion_1/2`, los ejes de sus 2 agujeros M5.
- **Refs.** `ESTOP-40`: seta Ø40, collar, leyenda Ø60 y cuerpo detrás de una puerta de 2 mm.
  Mide 60 × 60 × 77, con 33 mm delante. Conserva su ficha y su peso, y gana
  `linea_referencia` y `cotas_verificadas: false`.
  - `ESTOP-40-CAJA` (nueva): caja 72 × 72 × 55 con R4, 2 agujeros M5 en diagonal y
    prensaestopa M20 por −Y. Mide 72 × 94 × 87,5, 0,3 kg y USD 45 referencial.
  - **Decisión**: la ficha es la de ESTOP-40 por ancla YAML; sólo cambia `montaje: campo`,
    porque va en la máquina. Ni el ERC ni el modelo leen `montaje`.
  - **Decisión**: la caja también lleva el anillo de leyenda amarillo FIJO. Así el fondo
    amarillo que pide la norma se mantiene aunque el cliente repinte la caja, que es pintable
    (D3).
  - Catálogo: 362 refs.
- **D6.** `GEOM_CACHE_EPOCH` 5 → 6, con su motivo. `tests/test_catalogo_electrico.py` pasa de
  la caja 72 × 72 × 70 a 60 × 60 × 77. También se ajustaron los conteos (catálogo, mandos,
  fichas, anclas por familia) y el conjunto de pintables de `tests/test_apariencia.py`.
- **Tests** (`tests/test_seta_emergencia.py`, 20):
  - un sólido, una línea de BOM y la masa de ficha;
  - las zonas cubren todos los triángulos (payload y render) y la seta roja cae en z ≥ 12;
  - una pieza sin zonas tesela igual;
  - la zona sigue a la pose y al open caliente, y se pierde si la pieza se taladra;
  - las anclas caen donde está la geometría: cuello Ø22 en el agujero Ø22,5, agujeros M5
    pasantes y pose en el mundo;
  - el YAML de zonas se valida;
  - ESTOP-40-CAJA da el mismo ERC que ESTOP-40;
  - una caché con la caja vieja y el epoch anterior se descarta, y con el epoch actual se
    serviría.
- **Para F2.** El payload llama a `zona_por_cara(feat.component, shape)` y pasa la tupla a
  `mesh_payload`. Ojo: las piezas instanciadas mandan la malla de la DEFINICIÓN (mismo orden
  de caras). `Zona.fijo` decide si el color asignado pinta.

### F2 (2026-10-20): zonas en el payload de escena y en el visor

- **Apariencia (D3).** `library/apariencia.apariencias_de_zonas(zonas, asignado, color_paleta)`
  (pura) da `{zona: apariencia}`: una zona `fijo` ignora el color asignado; las demás lo toman
  sólo si su acabado es pintable, como una pieza entera. `services/apariencia.zonas_documento(doc)`
  la aplica a las piezas cuyo componente declara zonas (las demás no aparecen).
- **Payload (D2, `api/scene.py`).**
  - `_cached_render(shape, want_mesh, componente)` y `_definition_mesh(key, componente)` teselan
    con `zona_por_cara` (la definición es de UN componente: sus instancias comparten malla y
    rangos).
  - La entrada de la pieza suma `zonas: [{acabado, albedo, desde, hasta}]` en índices de
    triángulo de la malla que recibe (la propia o la de su definición).
  - Los rangos con nombre (`mesh.zonas` de F1) no viajan: `_sin_zonas` los saca. Una malla sin
    zonas es el MISMO objeto.
  - **Decisión**: la entrada `same` del delta también lleva `zonas`. El color cambia sin subir el
    rev; los rangos salen de la malla en caché (`_rangos_de`).
  - Una pieza taladrada no calza con la huella: sale sin `zonas`, de un solo acabado.
- **Visor.**
  - `viewport/zonas.ts`: `gruposDeZonas` valida que los rangos empiecen en 0, sean contiguos y
    no vacíos, y cubran la malla; si no, la pieza va con UN material. Con un arreglo de
    materiales, un triángulo sin grupo no se dibujaría.
  - Los grupos van en vértices (×3): la geometría del visor es no indexada.
  - `meshes.ts`: un material por zona, con la misma fábrica que una pieza entera
    (`featDeZona`), así cada zona lleva el relieve y la textura procedural de su acabado. El
    boceto-guía sigue con un material. Las instancias ponen los grupos en la geometría
    COMPARTIDA; los materiales son de cada malla.
  - `applyAppearance` reusa los grupos y `appearanceSig` suma la apariencia de cada zona (sin
    zonas, la firma de siempre).
  - `mergeSceneDelta` (`zonasDelDelta`): en una `same`, los rangos son los de la geometría que
    el visor YA tiene y la apariencia, la del delta.
  - **Decisión**: lo que trataba el material como uno solo ahora acepta un arreglo:
    - el resalte del montaje de la grabación (`grabacion/montaje.ts`), que antes se saltaba los
      arreglos y la seta habría entrado sin resalte;
    - el tinte de guardado fallido;
    - los planos de sección del GTAO (`calidadVista.ts`).

    La sombra de contacto, el GTAO y la grabación no cambian: los primeros dibujan con un
    material de reemplazo, que cubre todos los grupos.
- **Tests.**
  - `tests/test_seta_payload.py` (6): zonas que cubren la malla, instancias que comparten
    definición y rangos, pieza sin zonas byte a byte igual (con la maquinaria apagada da el
    mismo texto), `set_color` no pinta lo fijo (entrada `same`), `apariencias_de_zonas` pura,
    pieza taladrada sin zonas.
  - `ui/src/viewport/zonas.test.ts` (11): los grupos cubren todos los índices; un rango malo
    se descarta; el material de cada grupo es el de su zona (color, rugosidad y metalicidad);
    la textura por zona; lo fijo no se repinta; repintado en sitio por delta; instancias con la
    geometría compartida; pieza sin zonas con un solo material y la firma de siempre.
- **Verificación en el navegador.** API de prueba en :8100 sobre una copia de la base, con el
  proyecto «seta-f2-prueba»: puerta + ESTOP-40 + ESTOP-40-CAJA.
  - Calidad alta: la seta roja sobre la leyenda amarilla y la caja amarilla.
  - Tras `set_color` azul a las dos piezas, la caja se repinta en sitio, sin reconstruir la
    malla (`builds` = 3). La seta, la leyenda y el collar no cambian.
  - Calidad normal: igual. Sin errores en la consola.

### F3 (2026-10-20): zonas en la foto VTK y en el GLB de la vista web

- **Dato, no import.** `services/apariencia.apariencias_render(doc)` = `apariencias_documento`
  más, en cada pieza que conserva sus zonas (`zona_por_cara` calza), la clave
  `zonas: {por_cara, aps}` con las apariencias de `zonas_documento` (D3 ya aplicado). El kernel
  la lee de la apariencia que ya recibía: no importa `library`. La usan `render_view`
  (`routers/render.py`), el GIF de movimiento (`routers/motion.py`) y `publicacion/vista3d.py`.
  `apariencias_documento` no cambia: el payload de escena no paga el `zona_por_cara` extra.
- **VTK.** `render_comun.teselar_con_zonas` da las `partes` `(desde, hasta, rgb, pbr)` y
  `actores_superficie` arma un actor por zona (misma opacidad; las aristas, del polydata
  entero). `render_vtk` sólo cambia el teselado y el alta de actores.
  - **Decisión**: con `section` la forma se corta y la pieza sale de un acabado (los índices de
    cara ya no son los del builder). El fantasma gris del `highlight` también va de un color;
    `xray` conserva los colores de zona.
  - **Decisión (fuera de F3)**: `render_vivo` (video VTK de respaldo y GIF de dinámica) sigue de
    un acabado: recibe `apariencias_documento` y no lee `zonas`. El video de la máquina es el del
    navegador (F2). Si Mario lo pide, se hace con `actores_superficie` en `EscenaViva._crear`
    (`resaltar` y `mover` tendrían que recorrer los actores de zona).
- **GLB** (`kernel/glb_zonas.py`). Con `SetMergeFaces`, el escritor junta caras por ESTILO, y el
  estilo de un sub-shape de cara suelta no da una primitiva por zona (F0: 5 para 4). El prototipo
  de una pieza con zonas es un COMPUESTO con un sub-compuesto de caras por zona (en el orden de
  `faces()` de build123d, replicado en `glb_zonas.caras` con su test) y cada sub-compuesto lleva
  color + material PBR (`AddSubShape`). La instancia no lleva estilo (el del prototipo lo
  pisaría). El prototipo se comparte por TShape + estilos: una caja repintada tiene el suyo.
  - **Medido**: ESTOP-40 da 4 primitivas y 4 materiales en su nodo.
  - **Decisión**: dos zonas con el mismo estilo se funden en una primitiva. ESTOP-40-CAJA da 3:
    rojo, amarillo (leyenda + caja) y negro (collar + prensaestopa). No se distinguen en un
    visor y es lo que hace el escritor. Con la caja repintada salen 4.
  - Dos `insert_component` de la misma ref NO comparten TShape (pasa igual sin zonas): cada una
    es su prototipo.
- **Sin zonas, idéntico.** Una escena sin piezas con zonas da el mismo PNG (vistas, `xray` y
  `highlight`) y el mismo GLB byte a byte en `main` (15f30e2) y en la rama (script fuera del repo,
  en el scratchpad). Una `zona_por_cara` que no calza con las caras da el mismo GLB que sin zonas.
- **Tests** (`tests/test_seta_render.py`, 10):
  - foto cenital de ESTOP-40: rojo y amarillo concéntricos, el amarillo en anillo alrededor;
  - ESTOP-40-CAJA en iso: la seta roja arriba; con `set_color` azul la seta no cambia, queda el
    anillo amarillo y la caja sale azul;
  - en ESTOP-40 el color asignado no cambia el PNG;
  - sin zonas el PNG es el de siempre; con sección o taladro, de un acabado;
  - GLB: primitivas por estilo con el color de la tabla, la roja delante, y las cotas Ø40 y Ø60;
  - en el GLB, el color asignado no pinta lo fijo;
  - el prototipo se comparte sólo con los mismos estilos;
  - pieza sin zonas, mismo GLB;
  - orden de caras igual al de build123d.
