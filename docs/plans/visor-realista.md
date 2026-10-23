---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: F1–F3 en main (2026-10-20): acabados, piso con sombra, reproductor de la marcha (Física → «Ver la marcha», probado en el navegador con el 73) y la banda y las cadenas que avanzan; F4 quedó reemplazada por [video-realista](video-realista.md) F3 (2026-10-20: la máquina andando en el video del navegador, `publicar generar --render navegador`; D8, vetable); faltan F0 y F5 (clip de 20 s de la piloto andando, lo juzga Mario)
descripcion: Prendes la máquina y la ves andar en 3D como en la realidad: rodillos y tambores girando por su motor, la faja con su forma real corriendo, las cadenas eslabón por eslabón y las cajas viajando con física
---

# Ver la máquina andar como en la realidad

## Estado y origen

Mario (2026-10-10): «Quiero llevar a Apolo a un siguiente nivel 3D… quiero una emulación real,
por ejemplo ver fajas reales, no un pedazo rígido doblado, quiero que una máquina al prenderse se
mueva cada pieza según la física, quiero verlo en 3D en buen diseño o lo más parecido a la
realidad posible… podemos reemplazar el motor 3D actual y crear uno mejor». Se le recomendó NO
reemplazar el motor ni escribir una física propia, y poner el esfuerzo en el realismo visual y en
terminar V8.2; respondió «sí» al plan.

## El problema / lo que hay hoy

- **Física**: [V8.2](V8.2-maquina-se-mueve.md) F1 está en `main` (`physics/dinamica*.py`,
  `physics/banda.py`): MuJoCo con juntas, motores, banda como superficie que arrastra, productos y
  sensores, en lote. Faltan F2 (endpoint + tool `simulate`) y F3; pausado el 2026-10-09.
- **Visor**: three.js ya usa PBR (`ui/src/viewport/materials.ts`, `MeshStandardMaterial`), luz de
  ambiente sin assets (`environment.ts`, `RoomEnvironment`), tono ACES y sombras suaves
  (`scene-setup.ts:19-22`). Lo que falta para «parecer real» no es el motor: materiales por tipo
  (todo es un color + metalness/roughness genérico), sombra de contacto con el piso, y que la
  máquina SE MUEVA.
- **Dos renderizadores**: el visor (three.js) y el video de la máquina
  (VTK en `kernel/render_vivo.py`) no comparten
  materiales: hoy se verían distintos.
- La faja se dibuja como un sólido rígido; las cadenas, como sólidos del CAD que no avanzan.

## Lo que se revisó antes de escribir esto

- Las herramientas del mercado (NVIDIA Omniverse/Isaac Sim, Rockwell Emulate3D, Siemens Process
  Simulate, Visual Components) modelan la faja transportadora como SUPERFICIE CON VELOCIDAD más
  una animación: la banda flexible con física completa es lenta y casi nunca cambia el resultado.
  Es la misma decisión que V8.2 D5.
- MuJoCo 3 trae cuerpos flexibles (`flexcomp`): la banda flexible real queda disponible para un
  estudio puntual (comba, tracking) sin cambiar de motor.

## Decisiones (para vetar)

- **D1. No hay motor de física propio**: MuJoCo (V8.2) calcula. La ventaja de Apolo es juntar
  CAD + física + tablero + PLC + IA, no el motor.
- **D2. No se reemplaza three.js**: lo que da realismo (materiales, luz, sombras) se logra con él;
  Unreal/Unity/Omniverse romperían «corre en el navegador, liviano, MIT». WebGPU se evalúa cuando
  three.js lo dé estable, sin cambiar de motor.
- **D3. Física donde cambia el resultado, animación donde sólo se ve**: cajas, torque, patinaje y
  sensores = física (V8.2). La piel de la faja, las cadenas, los engranajes y los rodillos que
  giran por su eje = animación CINEMÁTICA que se deriva del resultado físico (velocidad de la
  banda, ángulo de cada junta), así nunca contradice a la física.
- **D4. Calcular ≠ mirar**: el servidor simula y entrega una serie de tiempo (poses por cuerpo a
  50 Hz + velocidad de bandas y cadenas); el visor la reproduce a 60 fps interpolando, con línea
  de tiempo (play, pausa, velocidad, saltar). El resultado no entra al `.apolo` (se regenera) y
  se cachea por firma del documento + escenario.
- **D5. Una tabla de materiales para los dos renderizadores**: material/rol → parámetros PBR
  (acero pintado con el color del usuario, galvanizado, inoxidable cepillado, aluminio, caucho,
  PVC de banda, cadena pavonada, bronce). Fuente única en `library`, la leen el visor y VTK. Los
  mapas de relieve son PROCEDURALES (sin descargar texturas: CSP y licencias).
- **D6. Faja con su forma real**: la ruta sale de la geometría (tambores, rodillos, tensor) con
  envolvente en cada tambor y comba entre apoyos según la tensión de V8.2; la textura corre a la
  velocidad de la banda. Cadenas: eslabones instanciados (`InstancedMesh`) a lo largo de su lazo
  (`library/transmision`), avanzando con el ángulo del piñón.
- **D7. Presupuesto**: 60 fps con la piloto (≈ 200 piezas, 21 cadenas ≈ 1000 eslabones) en una
  laptop media; se mide en F0 y se respeta en cada fase.
- **D8. Módulos nuevos en `ui/src/viewport/`** (reproductor, faja, cadena): `Viewport.tsx` no
  crece (trinquete de tamaño).

## Alternativas descartadas

- Motor 3D propio o motor de juegos (Unreal/Unity con pixel streaming): años de trabajo o
  servidor con GPU por usuario; rompe la distribución por PyPI y el navegador.
- Banda flexible con física completa siempre encendida: lenta y sin cambio en lo que se decide.
- MuJoCo en el navegador (WASM) desde el inicio: atractivo para «empujar una caja con el mouse»,
  pero duplica la física; queda como opción después de D4.

## Fases

- **F0 (S, sólo lectura)**: capturas de la piloto (proyecto 2) en el visor y en VTK; medir fps
  con 1000 eslabones instanciados en un prototipo del scratchpad; listar qué juntas y motores le
  faltan a la piloto para que V8.2 la mueva (hoy no tiene juntas declaradas).
- **F1 (M, `library` + `ui` + `kernel`)**: tabla de materiales D5 usada por los dos
  renderizadores; piso con sombra de contacto.
- **F2 (M, `api` + `ui`)**: reproductor D4 sobre el resultado de `simulate` (requiere V8.2 F2).
- **F3 (M, `library` + `ui`)**: faja con forma real y cadenas que avanzan (D6).
- **F4 (S, `publicacion`)**: el video de la máquina cierra con «la máquina andando» (mismo
  resultado y mismos materiales, renderizado por VTK).
- **F5 (S, verificación)**: clip de 20 s de la piloto andando, cajas incluidas; lo juzga Mario.

## Lo que este plan NO hace

- Datos vivos sobre el 3D (cables, pilotos, tableros): es [V8](V8-maquina-viva.md) V8.4.
- Deformación de la estructura (eso es FEA estático, ya existe) ni fluidos.

## Riesgos

- Que el visor y VTK se vean distintos → D5 + una captura comparada en el test de F1.
- Que la animación contradiga a la física (caja que avanza más rápido que la banda) → D3: todo
  lo animado se deriva de la serie de tiempo física.
- Rendimiento con máquinas grandes → instancias, nivel de detalle y D7 como gate.

## Bitácora

### F1 (2026-10-19)

Hecha la tabla D5; el piso con sombra de contacto queda PENDIENTE (ver abajo).

- **Fuente única**: `core/apolo/library/apariencia.py` (`ACABADOS`, 17 acabados PBR
  metálico-rugoso: acero pintado, mecanizado, pavonado —la «cadena pavonada» de D5—, galvanizado,
  zincado, inox cepillado, cromado, aluminio, hierro fundido, bronce, latón, niquelado, caucho,
  PVC de banda, madera, vidrio, cartón). `acabado_de` decide por el material resuelto
  (`resolve_material`) y, en acero liso, por el ROL (eje/pasador/piñón/polea → mecanizado,
  cadena → pavonado) y la categoría de catálogo. Albedo: color asignado por el usuario > color
  propio del acabado > paleta (lo pintado se sigue distinguiendo por pieza).
- **Los dos lados**: `services/apariencia.apariencias_documento(doc)` aplica la tabla a un
  documento. El payload de escena manda `acabado` + `albedo` por pieza (también en las entradas
  `same` del delta: `set_material`/`set_color` no suben el rev) y el visor lee los parámetros de
  `ui/src/viewport/acabados.json`, copia GENERADA (`scripts/acabados_ui.py --escribir`) que
  `tests/test_apariencia.py` compara byte a byte. VTK recibe las apariencias como dato
  (`extract_render_scene(apariencias=)`, `EscenaViva(apariencias=)`, el kernel no importa
  `library`) en la foto de `render_view`, el GIF de movimiento, el GIF de dinámica y el video de
  la máquina. Como el render VTK no tiene luz por imagen, `render_comun.phong_de_pbr` traduce PBR
  → Phong, calibrado para que el acero pintado quede como el Phong de antes.
- **Relieves procedurales** (`ui/src/viewport/relieve.ts`): 6 tipos (pintura, cepillado,
  moteado, fundición, veta, tejido) generados con semilla fija, como `bumpMap`; las piezas no
  traen UV, así que `uvCaja` las proyecta en mm por la cara dominante. VTK no pinta relieve.
- **Guarda decidida aquí**: la palabra de carpintería del nombre («Larguero (+Y)») sólo pinta
  madera en el vertical madera; si no, los largueros de una faja de acero se veían de madera.
  La BOM y la masa siguen con la heurística de `resolve_material` (no se tocó: es de otra fase).
- **Captura comparada** (riesgo «el visor y VTK se ven distintos»): un test renderiza con VTK
  caucho, galvanizado y acero pintado y comprueba el tono de cada uno contra la tabla; otro
  comprueba que cada ítem del snapshot VTK lleva el color y el (metalness, roughness) del
  payload del visor.
- **Pendiente de F1 — piso con sombra de contacto**: el piso actual (`scene-setup.ts`) recibe la
  sombra de la luz direccional, que cae desplazada; una sombra de contacto de verdad necesita un
  pase propio (render desde abajo + desenfoque) dentro del bucle de render de `Viewport.tsx`,
  que está congelado en el trinquete de tamaño (1631 líneas). Va con su propio paso: sacar
  primero el bucle de render a un módulo y luego sumar el pase.

### Fix (2026-10-19): rodillo galvanizado y color sólo en acabados pintables

Visto en el piloto (proyecto 74): el «Tubo del rodillo» salía acero pintado con su color
asignado `#c3c9d1` y parecía plástico blanco, y los piñones mecanizados se veían dorados
(`#b07d2b`, color que puso el agente que modeló).

- **Rol rodillo/tambor → galvanizado** (`apariencia._ROL_RODILLO`, más las categorías de catálogo
  `rodillos`/`tambores`): «Rodillo…», «Tambor…» y «Tubo/camisa del rodillo», anclado al inicio
  del rol y DESPUÉS de las reglas de cadena y eje: «Eje del rodillo» sigue mecanizado, «Cadena
  rodillo a rodillo» pavonada y «Tapa con rodamiento 6201» pintada. Un material declarado manda
  (el `RODILLO-50` del catálogo es «acero zincado» → zincado; un tambor engomado → caucho).
- **`pintable` es atributo del acabado** (viaja en `acabados.json`): acero pintado, caucho, PVC
  de banda, madera (teñida) y cartón (impreso). Sólo en ellos el color asignado define el albedo;
  en los metales (mecanizado, pavonado, galvanizado, zincado, inox, cromado, aluminio, hierro
  fundido, bronce, latón, niquelado) y en el vidrio manda el albedo de la tabla. El color asignado
  NO se borra del manifest: sólo deja de pintar. Las muestras del árbol, Propiedades y la ficha
  ya leían `albedo`, así que muestran el color efectivo sin tocar la UI.
- Piloto antes → después (acabado, albedo): tubo del rodillo `acero_pintado #c3c9d1` →
  `galvanizado #b4bac0`; piñones `acero_mecanizado #b07d2b` → `#a3a8ae`; ejes y bujes
  `#8d949e` → `#a3a8ae`; cadenas `#4b5058` → `#3b3e43`; tuercas zincadas `#8d949e` →
  `#c8cdd2`. Bastidor `#2b5c9e`, motorreductor `#2f7d5b`, guardas `#f2c200` y tapas `#3b4047`
  (acero pintado) siguen con su color.
- Pendiente (fuera de este fix): elegir un color en Propiedades para una pieza metálica guarda el
  color pero no cambia nada a la vista; falta decirlo en la ficha. `publicacion/vista3d.py`
  (GLB de la vista web) todavía no lee la tabla (su enganche D6).

### F2 (2026-10-20): reproductor de la marcha

**Servidor** (`api` + `physics`):
- `physics/dinamica_serie.py` (puro, entra solo al gate de capas por su nombre `dinamica*`)
  convierte la salida de `simulate_dynamics` en la serie D4:
  - `t` real de cada muestra;
  - por cuerpo de junta, T(t) = P(t)·P(0)⁻¹ como `x, y, z, qx, qy, qz, qw` aplanados (el visor
    la aplica sobre la malla de diseño, como el GIF, sin depender de dónde puso MuJoCo el origen
    del cuerpo);
  - por producto, la pose absoluta desde su muestra `desde` (con `cada_s` nacen en su hora);
  - `q` por junta (de ahí F3 saca el avance de las cadenas);
  - por banda, la velocidad de la cara superior por muestra con su `direccion`, sacada del
    `BandaDatos` del snapshot (`v = q̇·r`). La salida del MCP no cambió (golden intacto).
- `GET /api/physics/dynamics/serie` da la ÚLTIMA marcha simulada del proyecto activo;
  `POST …/serie` la de un escenario explícito (y pasa a ser la última). Router `assembly`;
  `test_rutas_api.py` anota el par GET → POST.
- **Caché** (`sims.MARCHAS`, en memoria, nunca en el `.apolo`): series por (firma, escenario),
  tope 4, y el último escenario de cada proyecto, tope 16; lock HOJA.
  - Firma = sha256 del log + los materiales (la masa). Color y ocultos no cuentan.
  - Escenario = la petición sin `fps` (la serie fuerza 50 Hz).
  - Toda dinámica exitosa registra su escenario como el último del proyecto: también la tool
    `simulate`, que pasa por `POST /api/physics/dynamics`. Si el documento cambió, el GET
    simula otra vez sobre el actual (D4 «se regenera»).
  - Locks: firma, búsqueda en caché y `prepare_dynamics` en UNA adquisición de `STATE_LOCK`;
    `simulate_dynamics` bajo `PHYSICS_LOCK`; la conversión fuera de los dos.
- Tope de tamaño: si cuerpos + productos × duración × 7 pasa de 2 M números (≈ 16 MB de JSON),
  la frecuencia baja (mínimo 10 Hz) y un aviso lo dice. Con 200 cajas × 60 s quedarían 23 Hz.

**Visor** (`ui/src/viewport/marcha/`, `Viewport.tsx` 429 → 438 líneas):
- `serie.ts`: tipos y lo puro (tramo por búsqueda binaria —60 s son 3000 muestras—, lerp + slerp,
  nacimiento de las cajas).
- `estado.ts`: store propia (`state/store.ts` está en su tope). Tiene la serie y la línea de
  tiempo: reproducir, pausa, velocidad ×0,25 a ×2 y saltar. En el final, reproducir vuelve a
  empezar.
- `reproductor.ts`: mueve las mallas reales (`T(t)·baseMatrix`) y cajas de cartón (acabado
  `carton` de la tabla D5) en la tarea `antesDeComponer`, antes del tinte y la sombra. Publica el
  tiempo a la barra a 10 Hz como máximo, sin re-render por fotograma. Cada pose marca sucia la
  sombra de contacto (el programador la deja en ≤ 10 Hz).
- `enVista.ts`: el hook que lo arma tras los efectos de mallas y pose cinemática y lo rearma en
  el mismo instante si cambian las mallas. Se quita con el proyecto, con la caída por gravedad o
  con el drop-test: mueven las mismas mallas.
- `BarraMarcha.tsx`: la línea de tiempo abajo al centro, en los dos modos.
- En el panel Física, «Máquina en marcha» (`panels/SeccionMarcha.tsx`): «Ver la marcha» trae la
  última y la reproduce. El 404 «todavía no hay simulación» se muestra en el panel y NO va a
  `logs/errors.log` (no usa `runTracked`); los avisos de la física van en `<VerDetalle>`.

**Medido en el piloto** (proyecto 74, copia de la base, por TestClient, sin guardar nada). Hoy
no tiene juntas: se le agregaron EN MEMORIA 20 continuas eje → tubo del rodillo, más 20 motores
por velocidad a 0,3 m/s hacia +X y cajas de 250×300×150 mm y 5 kg en serie cada 1,2 s, 12 s.

| qué | resultado |
|---|---|
| serie | 601 muestras (50 Hz), 20 cuerpos (los 20 tubos), 10 cajas; 0,82 MB de JSON |
| primera llamada (en frío) | 61,7 s: la preparación son ~60 s de cascos convexos; la física, ~6 s (×1,85 del tiempo real) y la conversión, 0,3–0,5 s |
| misma petición otra vez | 0,19 s (caché, `en_cache: true`) |
| preparación con los cascos ya en caché | 1,7 s; la física, 2,0–2,8 s |
| cajas | 7 viajan sobre los rodillos; 3 cayeron por la descarga (sin mesa de recepción, como en V8.2 F3) |

**Hallazgo** (fuera de F2, no se tocó): de los cascos en frío del 74, las 20 cadenas
(`create_chain`, «Cadena rodillo a rodillo») suman 23 s de 29 s, entre 1,2 y 2 s cada una. Va al
backlog de física: casco de la cadena por su lazo o por su bbox.

**Lo que no se verificó**: el 3D en un navegador. La API de :8000 es de Mario y desde el worktree
no se levanta. La reproducción a 60 fps, la barra en los dos modos y la sombra mientras corre
quedan para la verificación con la UI servida (la de F5 o antes). Tests: 11 de API
(`tests/test_api_marcha.py`) y 17 de vitest (`viewport/marcha/serie.test.ts`,
`reproductor.test.ts`).

### F3 (2026-10-20): la faja con su forma real y las cadenas que avanzan

Todo vive en la serie de la marcha (`cadenas` y `fajas`, sólo en marcha: la vista quieta del CAD
no cambia). Nada entra al `.apolo` ni cambia geometría (sin versión ni epoch).

**Servidor**:
- `services/marcha_visual.py` (OCCT, bajo el `STATE_LOCK` de `_serie_dinamica`, en la MISMA
  adquisición que `prepare_dynamics`):
  - la cadena se reconoce por su `mesh_key` (`Transmision.clave`: za, zb, centros, fases y
    eslabones, los números exactos de su geometría) y sus piñones por las uniones `{cadena}_a|_b`.
    No lee las anclas ni `medir_transmision`: así no depende de los params de `create_chain` (otra
    rama lo pasa a v2); si su clave cambia de formato, `tests/test_marcha_visual.py` lo dice;
  - de cada banda de la física, el encuadre de la banda y de las piezas que cruzan su ancho en el
    marco de la faja (u = marcha, w = normal, v = u × w), y si son redondas (encuadre cuadrado que
    no crece girado 45°).
- `library/ruta_faja.py` (puro): la línea media abraza el casco de los tambores redondos de adentro
  (+ espesor/2); lo de afuera que toca la cara (≤ 1 mm) parte el ramal de retorno; cada vano cuelga
  una parábola con comba = mín(CEMA 2 %, w·l²/8T, holgura con lo de abajo) y `limita` dice cuál
  mandó. El ramal de arriba no cuelga (va sobre la cama o los rodillos).
- `library/marcha_visual.py` (puro, fuera de los locks): qué junta mueve cada cadena (la del primer
  piñón que gira; signo = eje de la junta · Z del lazo), el piñón que la física no gira (el del
  motor sin junta) para que gire con ella, la tensión del ramal flojo y los rodillos libres (cola,
  retorno) con su eje de giro.
- **Decisión sobre «la comba según la tensión de V8.2»**: V8.2 no modela la pretensión del tensor.
  Se usa la MÍNIMA que transmite la tracción medida sin patinar, T2 = F_U/(e^{μα} − 1) (F_U = par
  del motor en régimen / radio, μ 0,25 acero liso, α = abrazamiento del motriz en la ruta). Con
  ella la comba pasaría del 2 %: en los dos pilotos manda CEMA (el tensor debe dar al menos esa
  tensión), y la serie lo publica (`tension`, `tramos[].limita`).

**Visor** (`ui/src/viewport/marcha/`):
- `cadena.ts`: eslabones instanciados (rodillo, perno, placa interior y exterior). El rodillo
  físico m va en la posición m + n(t) del lazo, n = signo·(q − q₀)/360·z; entre dos rodillos
  sentados gira sobre el eje del piñón, en los tramos va en recta; las placas interiores unen
  (2k, 2k+1). Las cadenas de igual norma y ASPECTO comparten un juego de cuatro mallas.
- `faja.ts`: la cinta (afuera, adentro y cantos) con UV en mm. No se mueve: corren su relieve
  (clonado del material de la banda) y un empalme más oscuro en s = 0, el recorrido s(t) = ∫v de
  la serie. `giroRodillo`: recorrido / radio.
- `transmision.ts`: oculta la banda y la cadena del CAD, pone lo nuevo en `ctx.group` (sombra de
  contacto, encuadre; `raycast` no-op) y gira lo arrastrado componiendo sobre la pose del cuerpo
  (un tensor que se desliza). Una pieza oculta por el usuario sigue oculta. El reproductor lo llama
  después de los cuerpos; `Viewport.tsx` no cambió.

**Medido** (copia de la base, TestClient, sin guardar):

| qué | resultado |
|---|---|
| 73 (faja de chapa, `j_eje_motriz` 0,37 m/s, cajas cada 1,5 s, 6 s) | ruta de 246 puntos, 7980 mm, espesor 2,0, ancho 600; abraza `c412_rodillo` y `c669`; apoyan los dos rodillos de retorno; 3 vanos de 1268,7 mm con 25,4 mm de comba (CEMA) |
| 73, tensión | tracción 86 N → T2 mín 72 N (180°): la comba por tensión sería ~45 mm, manda CEMA |
| 73, giran con la banda | la cola y los dos de retorno (el motriz ya lo gira la física) |
| 73, extracción bajo el lock | 0,3–0,6 s; serie 0,06 MB |
| 74 (20 continuas eje→tubo + 20 fijas tubo→piñón y 20 motores, en memoria, 3 s) | 20 de 20 cadenas animadas (19 por su piñón A; la motriz por B, `j_rod20`, con el piñón del motor `c94` girando con ella); serie 0,19 MB |
| 74 en el visor | 2472 instancias en 8 mallas (2 aspectos), 0,36 ms por pose con los 20 cuerpos |

**Verificación visual** en un arnés temporal (vite + los módulos reales de `marcha/` sobre las
mallas teseladas de los pilotos; no se commitea): la banda apoya en los rodillos de retorno y
cuelga entre ellos, abraza la cola; en 1 s el empalme del retorno corrió ~370 mm hacia −X mientras
las cajas iban a +X a 0,37 m/s; en t = 0 la cadena animada cae sobre la del CAD (superpuesta en
alambre) y en t = 0,53 s los asientos del piñón (los rodillos sentados del CAD movidos con la pose
de su cuerpo) caen sobre los rodillos animados.

**Intentos fallidos**:
- El marco (d, n, a) de `BandaDatos` puede ser zurdo: `gp_Trsf` rechaza la matriz («Moving with
  scaling transformation is forbidden») → v = u × w.
- El espesor del tope de la banda al del tambor más alto daba negativo en el super-comando: su
  tambor motriz engomado (Ø113,6) se mete en la banda, dimensionada con Ø102 → el menor candidato
  válido por tambor (tope y fondo) y, si no hay, volumen / (ancho · largo).
- El abrazamiento medido entre las muestras de los extremos del arco daba 176°: se mide lo que gira
  la banda entre el tramo que llega y el que sale.
- Compartir instancias por objeto de material daba 80 mallas para 20 cadenas (cada pieza trae su
  material) → por aspecto, 8.
- El piñón del motor sin junta (`c94`) quedaba quieto bajo la cadena que corría → gira con ella.

**Lo que no se verificó**: el viewport real con la API servida (`Viewport.tsx`, la sombra de
contacto y la barra mientras corre la cinta); queda para F5 o antes, como F2. Tests: 9 puros +
2 de API (`tests/test_marcha_visual.py`, `tests/test_api_marcha_visual.py`) y 19 de vitest
(`cadena.test.ts`, `faja.test.ts`, `transmision.test.ts`).
