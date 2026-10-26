# Backlog — pendientes vivos, por demanda

Lo que falta hacer y no tiene plan en curso. Nada de esto bloquea: se toma cuando el negocio o un
proyecto real lo pide, y lo que crece de una línea pasa a un plan en [`plans/`](plans/).

Reglas del archivo:

- Un pendiente de una versión cerrada vive en la `nota:` de su plan. Aquí van **sólo los que no
  caben en esa nota** (con link al plan de origen) y los que no tienen plan.
- Al hacer un ítem se borra su línea; la historia queda en el commit y, si amerita, en el
  [devlog](devlog.md).
- Antes de tomar uno, verifícalo contra el código: el backlog envejece.

## Distribución (urgente)

- **Publicar 0.1.1 en PyPI con los topes de dependencias** (`mcp<2`, `build123d<0.11`,
  `ocp_gordon<0.3`, commit `265bab5`). Medido el 2026-10-03 en un venv limpio: la 0.1.0 publicada
  resuelve `mcp` 2.x (quitó `mcp.server.fastmcp` → `apolo-mcp` no arranca) y `build123d` 0.13 /
  OCP 8 (quitó `TopTools_ListOfShape` → falla modelado directo). Necesita las credenciales de
  Mario: `scripts/release.py --version 0.1.1`.
- **Migrar a `mcp` 2.x y a `build123d` ≥ 0.11 / OCP 8** para poder levantar esos topes (plan
  aparte: toca el cliente MCP y el kernel).

## Comandos, log y caché de geometría

Origen de todos: [estado-regen-y-params-estrictos](plans/estado-regen-y-params-estrictos.md)
(§ Lo que este plan NO hace).

- **Decidir si `pattern_linear` gana `name` y `create_box` gana `material`.** El agente los manda
  creyendo que nombran las copias o asignan el material: 114 `pattern_linear.name` en 18
  documentos (el 38 entre ellos) y 2 `create_box.material` en el 65. Hoy se rechazan al entrar
  (con puntero a `set_material`) y el replay los ignora (D13). Declararlos hace que esos logs
  viejos cambien al regenerar (las copias de patas del 38 cambiarían de nombre): o un upcaster
  que los descarte en los logs viejos, o aceptar el cambio y subir la `version` del comando.
- **Las refs del catálogo no se borran ni se renombran.** La validación de `component`
  (`_known_ref` en `commands/models.py`) y el executor (`CATALOG[p.component]` en
  `_exec_insert_component`) leen el catálogo VIVO: quitar una ref rompe el replay de todo log
  que la use (la carga tolerante suprime el comando). Retirar una exige alias o upcaster.
- **Caché de geometría más fina que por proyecto.** `geom_cache` guarda UNA fila por proyecto
  (el checkpoint del último comando) y el open caliente exige que sus firmas sean PREFIJO del
  log: subir la `version` de un comando invalida el proyecto entero (replay frío completo,
  aunque el comando esté al final). Varios checkpoints por proyecto permitirían reanudar del
  último anterior al cambio. Tampoco hay hash del catálogo en `_versions()`: tocar un YAML
  sigue siendo bump de `GEOM_CACHE_EPOCH`.

## Ensamblaje y cinemática

- **Master-slider «Apertura %»**.
- **MP4 del estudio de movimiento**. El GIF (`POST /api/motion.gif`) y la tool MCP `motion_gif`
  ya existen.
- **Anclas en más familias de catálogo** (hoy: chumacera, NMRV, faja).
- **Grupos (V5.2b)**: que las reglas consuman el `role` del grupo, y drag&drop en el árbol.
- **V6.3d (3) tolerancia angular ×L** en hijos muy grandes (~4 m): el residuo angular escala con
  el brazo → afinar el peso relativo posición/ángulo del `least_squares` por tamaño del sólido.
  Origen: [V6.3d](plans/V6.3d-fixes-revision.md) Fix 3.
- **V6.3d (4) `EdgeSelector` compartido**: los modos `ancla`/`entidad` (conectores de mate)
  aparecen en el schema de `fillet`/`chamfer`/etc. donde no aplican. Hoy dan error claro, no
  silencioso; separar el schema por demanda. Origen: [V6.3d](plans/V6.3d-fixes-revision.md) Fix 3.

## Lectura MCP a escala

- **Fricción chica de union-en-perfil-hueco F2** ([plan](plans/union-en-perfil-hueco.md) § F2):
  `$0` en lotes (3 de 3 modeladores; aceptar `$0` como alias o decirlo en el docstring de
  `run_batch`); la jamba sin material tratada como acero en una puerta de carpintería; `measure`
  no acepta «+Y»; `render_view(zoom=2.5)` en blanco.
Origen de todos: revisión de [V6.5](plans/V6.5-mcp-a-escala.md) y de
[V6.5e](plans/V6.5e-mcp-jobs-asincronos.md).

- **V6.5 (3)** `get_topology(only=...)` con un `only` inválido devuelve un dict vacío en silencio,
  no un error.
- **V6.5 (4)** MCP `get_scene(ids=[])` (lista VACÍA, falsy) cae al brief completo en vez de
  devolver cero piezas.
- **V6.5 (5)** el bucle de `focus` en `interference_report` (`library/checks.py`) itera O(n²) en
  Python con un skip barato: reestructurar a focus × resto cuando duela a miles de piezas.
- **V6.5 (6)** no hay índice espacial: `near` e interferencia son barridos O(n) sobre AABBs.
  Medir antes de construir un R-tree.
- **`undo` por MCP devuelve la escena completa**: caro en contexto en una máquina grande (visto en
  [V8.2](plans/V8.2-maquina-se-mueve.md) F3); que devuelva el brief como las mutaciones.
- **V6.5e — límites declarados, no deuda**: los jobs no se cancelan (no se puede interrumpir OCCT
  a media regeneración de forma segura) ni se persisten (son recibos, no datos), y no hay
  porcentaje de progreso (el regenerate no tiene uno honesto que medir).

## Tools del agente al modelar (trabas medidas el 2026-10-26)

Las reportaron los modeladores por MCP al corregir la faja con desviador neumático (V8.9 F7,
correcciones 3 y 4); cada una con la llamada que la reproduce. Ninguna bloqueó: se esquivaron.

- `resolve_expression("tan(a*pi/180)")` da 0,0009: las trigonométricas toman GRADOS (la convención
  del proyecto) y el agente las usó en radianes. Decirlo en `get_expression_grammar` o avisar
  cuando el argumento lleva `pi/180`.
- `join_bolted` sobre agujeros de fábrica no declara su tornillería: `get_connections(ids=[…])`
  vacío y `simulate` no la incluye.
- `fasten(size="M5")` → 400; la nota de `fasten` admite ≤ 120 caracteres.
- Una aserción no se acota «hasta» un instante: el ancla «pulsar -S1 + 6 s y antes» → 400.
- `set_variable` devuelve ~6 kB por llamada (pesa en el contexto del agente).
- `servicio.velocidad_m_s` del cilindro sirve a la vez al caudal de la válvula y a la energía de
  impacto: con el pico falla «caudal de la válvula» y la energía se aprueba con la de régimen.
  Separar la velocidad de régimen de la de llegada a la tapa; tampoco hay aserción para la
  velocidad del vástago AL LLEGAR a la tapa (sólo «siempre»).
- `edit_command(<cilindro>, {"component": …})` → 400 si no se religa el dispositivo en el mismo lote.
- Los escenarios guardan coordenadas fijas de los sensores: mover la variable de posición de una
  fotocelda obligó a reescribir 13 escenarios. Acoplar por designación del sensor.
- Las cajas en cola se llaman `caja_0…`, no desde 1.
- Un túnel de tres sólidos en UN comando frena la caja en la boca (casco convexo por sólido del
  comando: `hull.cascos`); el agente lo esquivó con una pieza por comando.
- `add_device` al tablero falla con «faltan N mm de placa» si no se baja la reserva en el mismo
  lote: el error podría sugerirlo.

## Rendimiento y concurrencia

Origen: revisión de [V6.2e](plans/V6.2e-fixes-revision.md) (§ Bajas).

- `RenderSnapshot` guarda `Vector` de build123d: convertir a `np.ndarray` por pureza y perf.
- El wrapper `render_scene_vtk` toma `RENDER_LOCK` sosteniendo `STATE_LOCK`: footgun sin call
  sites (sólo lo usan los tests).
- **`undo`, `redo` y `open_project` por MCP siguen síncronos** (httpx a 120 s): las mutaciones
  que regeneran ya encolan ([sandbox-caliente](plans/sandbox-caliente.md) D8), pero un open en
  frío de un proyecto grande sin caché de geometría, o un `undo` cuyo checkpoint se desalojó,
  todavía puede dar «timed out» sin recibo. Medir antes: hoy el open frío del 38 tarda ~7–19 s.

## Paramétrico y modelo testigo 38

Origen: revisión de [V6.4](plans/V6.4-parametrico-profundo.md) y remate
[V6.4d](plans/V6.4d-remate-revision.md).

- **`ancho_banda` < ~540 rompe `c339`** (ménsula del rodillo de retorno): su `depth` se vuelve
  ≤ 0. Es un límite del modelo anterior a V6.4; parametrizar la ménsula con un piso mínimo.
- **Cotas que quedan LITERALES a propósito** (la regla «resolver exacto antes de atar» lo exige;
  detalle en el devlog § V6.4d): `j_mesa1..4` x (550/1452/2354/3255 son centros de sección
  REDONDEADOS; la fórmula da 550.75/1452.25/… → literal; benigno, porque la x de una junta
  prismática-z es un ancla cinemática que no mueve pieza), y `c120/c121` z=707 (rodillo de
  retorno) con `c339-342` z=737.5 (su ménsula): alturas constantes entre las dos variantes, sin
  expresión limpia para la ménsula. Atarlas si se parametriza la altura.

## Validación

- Agrupar las mitades A/B de una bisagra.
- Voladizo real del eje motriz.
- **Par en la tornillería**: el manual ya CALCULA el par de apriete por paso (E5,
  `tightening_torque_nm`); falta llevarlo a la unión declarada como dato/verificación.
- Coherencia `fasten size` ↔ taladro roscado cercano.
- **Decidir qué más deja de filtrar por `visible`.** La visibilidad es estado de VISTA
  (`Document.hidden`); las reglas de ingeniería, la instalación y la memoria ya leen TODA la
  escena (commit «las reglas de ingeniería ignoran la visibilidad», 2026-10-06). Siguen
  filtrando, y ocultar una pieza las cambia: la PUERTA DE ENTREGA (`checks.py` interferencias,
  `lints.py`, `physics/stability.py` gravedad → un verde falso con piezas ocultas),
  `assembly/autodetect.py`, la BOM/lista de corte/peso (`cutlist.py`: la cotización pierde lo
  oculto), `scene_mass_properties` sin ids (tool `get_mass_properties`, totales del brief) y
  `drawing_maps.py` (pernos). Se quedan (son vistas): render, pick, `measure`, las láminas
  (`projection`/`sheet`/`explode`), el manual y el GIF. Toca library + physics + assembly +
  drawing + api → plan; la duda es si alguien oculta A PROPÓSITO para sacar algo de la BOM o del
  plano.

## Geometría y catálogo

- Cola de milano e ingletes de CARPINTERÍA; canteado.
- Chapa: hijo de más de un nivel, hem 180°, alivios, editor de flaps.
- Coping/notching en nodos de grado ≥ 3.
- Chaveta en bores.
- Más familias de catálogo.
- **`create_extrude_poly` con puntos en sentido horario sale descentrado**: con h = 40, Z en
  [−60, −20] en vez de [−20, 20] (su schema dice «centrado en el origen»);
  `_exec_create_extrude_poly` no normaliza el sentido. Hoy lo cubre la guía («ANTIHORARIO»,
  [chat-cliente-igual](plans/chat-cliente-igual.md) F6); el arreglo es normalizar en el ejecutor
  (cambia la geometría de logs viejos con polígonos horarios: revisar antes).

## Física

- Cascos convexos en `drop_test` (hoy cajas AABB, `core/apolo/physics/sim.py`; `gravity_test` ya
  usa cascos).
- Export SDF.
- Simulación en tiempo real.
- **`simulate` con una banda hecha a mano** (origen: [V8.2](plans/V8.2-maquina-se-mueve.md)
  § Bitácora F3): sin `bandas` el lazo queda FUERA y el aviso pide `arrastrar`, que no la cura
  (debe nombrar `bandas` + la junta del tambor); y con motor y productos pero ninguna banda las
  cajas quedan quietas sin aviso.
- **`simulate`: radio de la banda a la cara superior** (59 mm en la 72), no a la línea de paso
  (58 mm): la velocidad sale 1,7 % alta. Decidir cuál es la referencia física.
- **`simulate`: una prismática sin motor sale en `juntas_en_limite` a t = 0** (el tensor): ruido
  en el resumen; reportar sólo las que llegan al límite durante la marcha.
- **Cascos de las cadenas en frío** (origen: [visor-realista](plans/visor-realista.md) § Bitácora
  F2): en el piloto 74 la primera dinámica tarda ~60 s en `hull_vertices`. Las 20 cadenas
  (`create_chain`) suman 23 s de 29, entre 1,2 y 2 s cada una. Después quedan en caché. Cura
  posible: el casco de la cadena por su lazo o por su bbox.
- **El N de un ITM 1P+N queda abierto en la co-simulación** (origen:
  [datos-de-corte-y-acometida](plans/datos-de-corte-y-acometida.md) § Bitácora F1b): su camino
  es `NA` con `accion: mano`, `-Q1.mano` arranca en `False` (`services/cosim_red._cerrado_inicial`)
  y el modelo `Itm` no lo publica: una carga fase-neutro tras él no recibe tensión. Cura posible:
  que el N siga al aparato (`-Q1.cerrado`), con su vigencia (`COSIM_EPOCH`).

## Fábrica de publicaciones: lo que halló la F4 (2026-10-22, fajas 3 y 4 en el escritorio)

- La BOM no lleva el largo de los pernos «no cortables» del catálogo, ni con `join_bolted`, ni el espesor
  de plancha: la BOM no sirve para comprar tornillería (`insert_component`/`join_bolted` deben guardar el largo).
- `join_bolted` no acepta el ala de un canal UPN (la toma por perfil cerrado), ni chumaceras con agujeros
  propios, ni un patrón que no cabe con borde mínimo; en una guarda eligió remache ciego (una guarda se desmonta).
- `engineering_check`: «ancho útil» descuenta 40 mm genéricos por lado en vez de medir las guías reales;
  «capacidad de rodillo» se dispara en cama deslizante si una polea se llama «rodillo».
- El material heurístico por nombre tiñó los «largueros» como madera (ver memoria de material por rol) y eso
  disparó un error de flexión del eje.
- El guion rotula «apoya en rodillos» en un drive central por sus tambores de desvío.
- Falta seeger (DIN 471/472) y prisioneros DIN 916 en el catálogo.

## Ingeniería y negocio

- `funcion`/rol por pieza.
- Explosionada 3D (la explosionada 2D del plano ya existe).
- L10 con reparto real.
- **Memoria de cálculo: carga por garrucha vs `carga_kg` del catálogo** (dato ya en el YAML de
  garruchas, `110_garruchas.yaml`). Origen: [garruchas-catalogo](plans/garruchas-catalogo.md) § 7.
- **Cotización eléctrica, lo que F4c no ve** ([V8.1](plans/V8.1-modelo-electrico.md) § F4d,
  < 50 USD cada uno):
  - conductores sueltos que repiten un cable declarado (la acometida -G1 → -Q1 y -W4);
  - el número de setas del 3D contra el circuito cuando la ref difiere (ESTOP-40 ×5 vs -S0 +
    ESTOP-40-CAJA);
  - un cable 3D «4x1» ligado a un 5G1 sin aviso de hilos distintos;
  - la pieza «sin precio» con material acero en la BOM.

## UI

- Refactor de `Viewport.tsx`: picking, medición, sección y gizmo a módulos propios.
- Picker de 2 sólidos para `add_joinery`.
- Editar sweep/loft/chapa/mate desde Propiedades.
- Snap-back del preview optimista cuando el guardado falla. Origen:
  [V6.2e](plans/V6.2e-fixes-revision.md).
- Borrar `isAxisAligned` (`ui/src/viewport/handles.ts`): código muerto, sin llamadas desde que
  los tiradores salen de `boxDimsFromBbox` (hallazgo del inventario de la
  [poda](plans/poda-claude-md-inventario.md)).

## En la nota de su plan

Estos pendientes viven en la `nota:` del plan (fuente única); aquí sólo el link.

- [V6.2](plans/V6.2-rendimiento.md): exportar STL y generar planos todavía bloquean la edición.
- [V6.2e](plans/V6.2e-fixes-revision.md): tinte de guardado fallido vs cambio de apariencia, GIF
  de física compuesto bajo el lock, `duplicate_project` sin lock.
- [V6.3](plans/V6.3-ensamblaje-pro.md): lazos cerrados de mates (A↔B, hoy rechazados como ciclo)
  y residuo del solver no guardado en el reporte de DOF.
- [V6.3d](plans/V6.3d-fixes-revision.md): `mirror` no propaga anclas; divergencia anti-paralela
  del multi-mate (borrar un mate puede girar la pieza 180°).
- [V6.4](plans/V6.4-parametrico-profundo.md): el arrastre del visor graba `transform` con
  literales; CSV de la tabla de diseño; el motriz no sigue el ancho de banda.
- [V6.5](plans/V6.5-mcp-a-escala.md): masa por grupo vs total; `near` con `limit` no declara
  `truncado`.
- [V6.5e](plans/V6.5e-mcp-jobs-asincronos.md): `?async` para `run_command` suelto e
  `insert_project`.
- [V6.6](plans/V6.6-croquis-vivo.md): prueba manual de la UI del croquis vivo.
- [V7.2](plans/V7.2-ultimo-kilometro-plano.md): doble datum «A», «Ø13 H7» rotulado torneado,
  soldadura sin lado de flecha.
- [V7.3](plans/V7.3-stackup-cadenas-cotas.md): más cadenas en el testigo para que E3.6 llegue a 4.
- [V7.4](plans/V7.4-fea-firmable.md): chapa fina dentro del FEA de ensamblaje, ν por material,
  huella real del herraje excluido.
- [V7.6](plans/V7.6-e2-fino.md): soldadura por lámina de miembro, vistas auxiliares, PDF/A,
  perpendicularidad y planitud en el GD&T.
- [Harness de auto-mejora](plans/harness-automejora.md): sólo existe el plan.

Las brechas del benchmark de entregables (E4 BOM/cotización y E6 paquete en 3.00) están en
[`benchmark/README.md`](benchmark/README.md).
