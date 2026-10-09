---
estado: en curso
nota: plan marco aprobado por Mario («quiero todo… al estilo Apolo»); V8.0 (medición) es lo siguiente; cada V8.x escribe su contrato antes de implementarse; P1–P4 sin contestar (no bloquean V8.0–V8.4)
descripcion: Las máquinas de Apolo traen su tablero eléctrico real (dispositivos, cables, PLC) y, si hace falta, sus placas a la medida; el agente lo diseña por MCP, la máquina se mueve en una co-simulación eléctrica y mecánica casi real que se ve en 3D con sus datos vivos, y sale con planos eléctricos, memoria de cálculo y el programa del PLC
---

# V8 — La máquina trae su tablero de verdad y se mueve con él

## Estado y origen

Pedido de Mario (2026-10-08), en dos mensajes:

> «Necesito que apolo tambien emule electronica, he visto que tinkercad hace lo mismo, pero
> nosotros tiene que ser a nivel profesional, se puede?»

Se le propusieron dos caminos: A) electrónica de placa estilo Tinkercad (protoboard, Arduino,
SPICE) y B) electricidad y control de la máquina (motor, variador, protecciones, PLC). Respuesta:

> «mi vision es que las maquinas que se modelen en apolo y usen tableros, sean tableros de verdad,
> y muevan de verda motores, osea un emulado casi a la realidad, y entonces seria el plan B.
> Recuerda que tambien se podria usar placas personalizadas (electronica) […] quiero todas las
> funcionalidades de software profesional, pero al estilo apolo, osea gestionado para agentes ia
> por mcp. Pero no te limites, quiero todas las cosas, todo, todo, yo tambien quiero visualizar
> tableros, quiero apolo que me permita ver cada centimetro y datos.»

El CLAUDE.md raíz tenía «PCB/electrónica» en **Fuera de alcance deliberado**. Este plan lo saca
de ahí: V8 es la nueva hoja de ruta.

Este archivo es el **plan marco** de V8: fija la arquitectura y las decisiones que valen para todo,
y reparte el trabajo en versiones V8.0 … V8.13. Cada V8.x escribe su propio contrato
(`V8.x-slug.md`) antes de implementarse, con este archivo como base.

En la industria esto se llama **comisionamiento virtual**: un gemelo digital de la máquina donde
el programa del PLC mueve un modelo físico. Hoy se arma con tres a cinco productos separados. En
Siemens son NX Mechatronics Concept Designer (la física), PLCSIM Advanced (el PLC virtual), SIMIT
(el comportamiento de los dispositivos) y EPLAN aparte (los esquemas), más KiCad o Altium para las
placas. Son caros y se manejan a mano. Integrado en un solo modelo y manejado por un agente no lo
ofrece nadie: es el diferenciador de V8.

## Lo que hay hoy

Medido sobre `main` en `0592a0c`.

**Lo eléctrico del catálogo es geometría con datos sueltos, sin bornes ni comportamiento**:

| archivo | qué trae |
|---|---|
| `library/data/91_variadores.yaml` | VFD-1K5-220 y VFD-2K2-220, builder `box`; `corriente_A`, STO |
| `library/data/92_tableros.yaml` | TABLERO-5040, una caja IP54 |
| `library/data/93_mandos.yaml` | ESTOP-40 y BOTONERA-2 |
| `library/data/60_sensores.yaml` | FOTO-M18, PNP |
| `library/data/30_motorreductores.yaml` | `tension` como texto libre («230/400V») |

- Los anclajes (`Feature.anchors`, `commands/registry.py:105-110`) son marcos mecánicos sin tipo
  (origen + eje). Las plantillas son por CATEGORÍA (`library/catalog.py:78-82`) y ninguna
  categoría eléctrica publica alguno.
- Ya existen el rol de grupo `electrico` (`assembly/groups.py:21-23`) y el subsistema «Sensores y
  control» (`assembly/grouping.py:21-60`).
- No hay cables, esquemas, PLC ni PCB en el código ni en `docs/`.
- La única salida eléctrica es «Suministro eléctrico» en la lámina de instalación
  (`services/installation_data.py:83-99`): toma los kW del PRIMER motorreductor, sin sumar y sin
  tensión.

**La física sólo deja caer cosas: ninguna junta tiene motor**:
- MuJoCo se usa en `gravity_test` (`physics/stability.py:66-178`) y `drop_test`
  (`physics/sim.py:85-151`). El MJCF sólo trae geoms estáticos y cuerpos `<freejoint/>`.
- Las juntas NO se traducen a juntas de MuJoCo; sólo cuentan como aristas del grafo de
  sujeción. No hay actuadores ni `data.ctrl`.
- `timestep` fijo de 0,004 s, duración ≤ 30 s, corrida en lote que devuelve todos los fotogramas
  juntos. Ojo: el parámetro `fps` es en realidad el TOTAL de fotogramas (`sim.py:140`,
  `stability.py:158`).
- `PHYSICS_LOCK` (`api/common.py:49-54`) serializa todas las simulaciones. Una sesión viva de
  minutos bloquearía `gravity_test` y la puerta de entrega.
- El «movimiento» es cinemático: keyframes `{t, values}` interpolados en línea recta
  (`robotics/motion.py:15-36`), sin velocidad, perfil ni par. Las juntas sólo aceptan ejes X/Y/Z
  (`robotics/pose.py:24`).
- La FK existe dos veces y hay que mantenerlas iguales: `pose.py` en Python y `computePoses` en
  TS (`ui/src/viewport/Viewport.tsx:1567-1605`).

**Hay dimensionamiento mecánico del accionamiento, pero nada eléctrico**:
- `conveyor_engineering_check` (`library/rules.py:471`) ya calcula tiro de banda (ISO 5048 o
  CEMA), potencia, par en el tambor, par de arranque ×1,6 y adherencia de Euler-Eytelwein.
- No se elige ni se verifica el variador (ninguna regla lee `corriente_A`). No se calculan
  corriente, sección de conductores, caída de tensión, protecciones, cortocircuito ni
  calentamiento del tablero.
- Los anclajes `eje_motriz`/`eje_cola` (`registry.py:1880-1940`) y el `bore` del NMRV son el
  enganche natural motor → junta.

**Transporte y UI**:
- El WebSocket sólo empuja `document_changed`, `job` y `autosave_failed` (`api/ws.py`,
  `routers/core.py:41-48`): no hay streaming de simulación.
- Los jobs tienen un solo worker FIFO en memoria (`api/jobs.py`).
- La UI no tiene librería 2D, de diagramas ni de gráficas (`ui/package.json`).
- No se usa `CSS2DRenderer`, aunque viene con three. No hay color por dato: el FEA se pinta en el
  servidor como PNG (`fea/fringe.py`).
- Están congelados por tamaño `Viewport.tsx` (1631 líneas), `store.ts` (916), `SchemaForm.tsx` y
  `SketcherDialog.tsx`.
- En modo Visor no se acoplan paneles (`dock/dockApi.ts:115-120`): una vista 2D grande junto al
  3D no tiene dónde ir.
- `kernel/render_vivo.py` (publicacion-tienda F2, recién en `main`) da una ventana VTK
  persistente a 7,9 ms por fotograma. Sirve para el video de una simulación.

**Planos y entregables reutilizables**:
- Todo plano se compone con primitivas `SheetModel` (`drawing/sheet.py:44-118`) y sale gratis en
  SVG, PDF, DXF y DWG.
- La memoria (`drawing/calc_report.py:229`) imprime cualquier regla con bloque `calc`.
- BOM, costeo y cotización agrupan por categoría (`library/bom.py`, `library/costing.py`,
  `drawing/quote.py`). La cotización no tiene líneas de mano de obra.

**Topes de arquitectura que mandan dónde va el código nuevo**:
- `RegenState` tiene 8 campos (`commands/state.py`). Cambiar sus campos cambia el formato del
  blob, lo que obliga a subir `GEOM_CACHE_EPOCH`, hoy en 5 (`doc/geomcache.py:57`).
- Están congelados en `tests/test_tamano_archivos.py`: `commands/models.py` (1359),
  `commands/registry.py` (2207), `doc/document.py` (1059), `drawing/sheet.py` (893),
  `library/builders.py` (847), `library/rules.py` (928) y `mcp_server.py` (1425).
- Todo lo de V8 va en módulos y paquetes propios.

## Lo que se revisó antes de escribir esto

- **La física no mueve juntas.** Por eso «la máquina se mueve de verdad» (V8.2) es una versión
  entera y prerequisito de todo lo vivo, no un detalle de la co-simulación.
- **`PHYSICS_LOCK` serializa todo.** Por eso la co-simulación corre en un PROCESO aparte (D7),
  con el mismo patrón que el sandbox de scripts.
- **Metadato o comando.** Las cadenas de cotas (V7.3) y los estudios de movimiento son metadato
  porque se EVALÚAN sobre el estado final. El modelo eléctrico, en cambio, es diseño que se
  construye paso a paso, como `fasten` y `add_joint`: los dos son comandos, viven en
  `RegenState` y viajan en `insert_project`. Además, los dispositivos del tablero son geometría.
  Eso decide D1. Cómo entra al regenerate se mide en V8.0.
- **Licencias** (consultadas el 2026-10-08; se re-verifican en la versión que adopte cada cosa):

  | herramienta | licencia | uso en V8 |
  |---|---|---|
  | OpenPLC / matiec | GPL-3 | no se embeben: Apolo es MIT |
  | PySpice | GPL-3 | no se usa |
  | blark (parser ST) | sin licencia clara | no se usa |
  | plcforge | PolyForm Noncommercial | no se usa |
  | ngspice | núcleo BSD-3 (xspice y contrib traen partes GPL) | proceso aparte |
  | Renode | MIT | proceso aparte |
  | KiCad | GPL-3 | binario externo |
  | Freerouting | GPL-3 | binario externo |

  Lo GPL se llama sólo como **binario externo por subproceso**, igual que ffmpeg en
  [publicacion-tienda](publicacion-tienda.md) D7 (y como kicad-mcp, MIT, que llama a Freerouting
  por subproceso).
- **KiCad 9.** Exportar y correr el DRC sólo se puede con `kicad-cli`. La API IPC exige la GUI
  abierta y el modo sin GUI llega recién en KiCad 11.
- **Precedente de la industria.** Siemens parte el gemelo de una máquina en tres modelos:
  automatización (PLC + HMI), eléctrico y de comportamiento de los dispositivos, y físico. Apolo
  los junta en un solo documento.
- **Mario está en Lima.** Lo dicen [cadenas-pinones](cadenas-pinones.md) («ASA 40, que es lo que
  se vende en Lima») y el catálogo («220V 3F»). Eso decide el perfil de norma por defecto (D11).

## Decisiones (para vetar)

- **D1 — El modelo eléctrico vive en el LOG de comandos, no en el manifest.**
  - Son comandos: dispositivo (una instancia de catálogo con bornes), cable y conductor, bornera,
    puente y programa de PLC.
  - El esquema, el 3D del tablero, las listas, la memoria y la simulación se DERIVAN de esos
    comandos.
  - Ganancias: undo/redo, expresiones (`"=..."`), `edit_batch` con contrato, y que
    `insert_project` traiga el tablero de cada máquina en un layout de planta.
  - Los ESCENARIOS de prueba y los RESULTADOS de simulación sí son metadato (D9): se evalúan sobre
    el estado final.
  - Se mide en V8.0 si entra como campo nuevo de `RegenState` (bump de `GEOM_CACHE_EPOCH`) o como
    carril propio de la etapa final del regenerate (como mates y grupos, sin checkpoint). Lo
    decide el costo de editar un cable en un log de ~450 comandos sin re-ejecutar la geometría.
- **D2 — Un dispositivo es una ref de catálogo con bornes, función y modelo de comportamiento.**
  El YAML gana:
  - `bornes`: identificación IEC 60445 (L1/L2/L3, T1/T2/T3, U/V/W, A1/A2, 13/14, 21/22, PE,
    +24V/0V…), con posición 3D para el ruteo;
  - `funcion`: letra IEC 81346-2;
  - `simbolo`: IEC 60617;
  - `modelo`: clave y parámetros del comportamiento, por ejemplo contactor con bobina, tiempos y
    contactos, motor con datos de placa, variador, guardamotor con clase y rango, sensor con
    alcance y tiempo de respuesta;
  - `perdidas_W` y `montaje`: riel DIN 35 mm, puerta, placa o campo.

  Las refs llevan datos de líneas reales y `cotas_verificadas`/«verificar con el proveedor», como
  ya hace el VFD-2K2.
- **D3 — Fidelidad a nivel SISTEMA, en capas, con un solo motor de co-simulación:**
  - **Lógica**: contactos, bobinas y retardos.
  - **Control**: red de corriente continua de 24 V y de alterna de mando resuelta por nodos
    (MNA) en cada paso. Da tensiones de bobina, caídas y fusibles.
  - **Potencia**: red trifásica fasorial cuasi-estática. Da la corriente de cada cable, la caída
    de tensión, el disparo térmico I²t de clase 10/20 y el disparo magnético (curvas
    IEC 60898/60947), además de la pérdida de fase.
  - **Electromecánica**:
    - motor de inducción con su curva par-velocidad estimada de la placa;
    - variador con modelo PROMEDIO: rampas, V/f o vectorial, límite de corriente, STO, fallas de
      sobrecorriente y sobretensión al frenar;
    - reductor con relación, rendimiento e inercia reflejada;
    - todo eso entra como par a una junta de MuJoCo.
  - **Mecánica**: MuJoCo con juntas reales (V8.2).

  No se simula la conmutación de los IGBT del variador: costaría unas 1000 veces más y no cambia
  ningún entregable de una máquina. El nivel circuito (SPICE) queda para las placas (D12).
- **D4 — El PLC es nuestro: compilador IEC 61131-3 propio.**
  - Texto estructurado (ST) primero: el agente escribe texto mejor que dibujos.
  - Escalera (LD) y GRAFCET/SFC son VISTAS del mismo programa.
  - El compilador traduce ST a Python seguro por construcción: sólo genera lo que la gramática
    permite, sin acceso libre a Python.
  - Ciclo de scan real: imagen de entradas → programa → salidas.
  - Bloques estándar: TON/TOF/TP, CTU/CTD, R_TRIG/F_TRIG, SR/RS.
  - El parser usa Lark (MIT).
  - Hacia el PLC real (V8.8) se exporta en ST, SCL (TIA Portal), PLCopen XML (IEC 61131-10) y
    L5X (Rockwell).
- **D5 — El 3D del tablero se genera del modelo eléctrico** (como EPLAN Pro Panel, pero
  automático):
  - gabinete, placa de montaje, rieles DIN y canaletas;
  - dispositivos colocados por reglas, en este orden: alimentación, potencia, control,
    borneras, más la reserva;
  - mandos y pilotos en la puerta;
  - cables ruteados por las canaletas, con su largo real y el % de llenado;
  - calentamiento por IEC/TR 60890.

  Es un super-comando (`layout_tablero`) con overrides por dispositivo: se puede ver y medir cada
  centímetro, porque es geometría de verdad.
- **D6 — El esquema lo dibuja Apolo, no una persona.**
  - El agente declara la red y Apolo compone las láminas IEC 61082: fuerza multifilar, control
    con trayectorias numeradas y referencias cruzadas de contactos, E/S del PLC, borneras,
    cables y listas.
  - Se componen con `SheetModel`, así que salen en SVG, PDF, DXF y DWG.
  - En la UI se VE, se navega, se sondea y se editan propiedades (formularios schema-driven). No
    se arrastran símbolos: es la doctrina de resultados, no se porta la manipulación manual.
- **D7 — La co-simulación corre en un proceso aparte, en dos modos:**
  - **Lote**: un job que corre un escenario (D9) y devuelve trazas, eventos, fotogramas y
    resumen. Es lo del agente, de los contratos y de la memoria.
  - **En vivo**: tiempo real con los mandos en manos de la persona. El proceso empuja el estado
    a ~30 Hz por un canal WebSocket propio y recibe las acciones («presiona -S1»). Si no alcanza
    el tiempo real, lo dice («×0,6»).

  El snapshot (MJCF, red compilada, programa compilado) se toma bajo `STATE_LOCK` y después
  nada toma `STATE_LOCK` ni `PHYSICS_LOCK`. Si el documento cambia, la sesión queda «vieja» y
  ofrece reiniciar. Mismo patrón que el sandbox caliente (`subprocess.Popen`, no
  `multiprocessing`). Es determinista: el mismo escenario da el mismo resultado.
- **D8 — El agente maneja todo por el MCP fino, más lecturas nuevas.** No hay tool por comando
  (los comandos nuevos llegan por `run_command`/`run_batch`). Tools nuevas, cada una con su
  endpoint, golden y catálogo:
  - `get_circuit`: dispositivos, bornes, redes y señales;
  - `electrical_check`: ERC más los cálculos;
  - `simulate`: escenario → job → trazas, eventos y resumen; GIF o MP4 opcional;
  - `get_simulation`;
  - `test_plc`: correr un programa contra un escenario sin guardarlo, como `test_script`;
  - `get_scenarios`/`set_scenario`;
  - `export_plc`;
  - las de placas en V8.10–V8.12.
- **D9 — Escenario = prueba de la máquina, y es metadato.** Un escenario tiene:
  - acciones del operador: pulsar, girar, soltar la seta;
  - eventos del mundo: llega una caja, corte de fase, atasco, cable cortado;
  - una duración y sus aserciones, por ejemplo:
    - «al pulsar -S1, -M1 llega a 1700 rpm en < 3 s»;
    - «con la seta, el par de -M1 es 0 en < 0,5 s»;
    - «banda atascada → dispara -Q1 en < 10 s».

  Correr los escenarios ES la prueba de aceptación en fábrica (FAT) virtual. Los resultados
  llevan vigencia por firma del documento (precedente: `fea_rules`).

  Se decide en V8.3 cómo entra al `expect` de un lote: correr un escenario dentro del lote
  sostendría `STATE_LOCK` segundos.
- **D10 — La mecánica dinámica (V8.2) es general, no sólo de fajas:**
  - cada junta se traduce a una junta de MuJoCo (hinge/slide, con eje arbitrario);
  - los cuerpos rígidos se arman por `arrastrar` y fijadores;
  - actuadores sobre juntas;
  - productos sobre rodillos (fricción nativa) y sobre banda (fuerza tangencial por contacto,
    a medir en V8.0);
  - sensores por rayo (`mj_ray`) y por posición.

  `timestep` de 1 ms en la co-simulación (hoy 4 ms en gravedad): lo mide V8.0.
- **D11 — Normas: IEC como base, más un perfil de país. Por defecto, Perú.**

  | tema | norma |
  |---|---|
  | equipo eléctrico de máquinas | IEC 60204-1 |
  | conductores, protección y tierra | IEC 60364-5-52 / -5-54 / -4-41 |
  | cortocircuito | IEC 60909 |
  | aparamenta y coordinación tipo 2 | IEC 60947 |
  | tablero y calentamiento | IEC 61439-1/2 e IEC/TR 60890 |
  | identificación y colores | IEC 60445 |
  | designaciones | IEC 81346 |
  | símbolos | IEC 60617 |
  | documentación | IEC 61082 |
  | seguridad | ISO 13849-1/-2, ISO 13850 |
  | PLC | IEC 61131-3/-10 |

  - Perfil Perú: CNE-Utilización, 220 V trifásico a 60 Hz (y 380/440 V industrial).
  - Otros perfiles bajo demanda: NFPA 79, UL 508A (con SCCR) y NEC para EE.UU.;
    NOM-001-SEDE para México.
  - Toda cifra cita su norma o dice «criterio de diseño» (regla de [library](../../core/apolo/library/CLAUDE.md)).
  - Honestidad: los planos y la memoria NO reemplazan la firma de un ingeniero electricista
    colegiado. El aviso va en el cajetín y en la memoria.
- **D12 — Placas a la medida: Apolo diseña y valida; KiCad y Freerouting fabrican.**
  - La red de la placa usa el mismo modelo de D1: los pines son bornes.
  - Apolo genera `.kicad_sch` y `.kicad_pcb` (formato S-expression abierto), con huellas y una
    colocación por reglas: conectores al borde, desacoplos junto a su pin, agujeros de montaje
    donde la carcasa los pide.
  - Freerouting rutea (DSN → SES) y `kicad-cli` corre el DRC y saca Gerber, taladros, pick and
    place y STEP. El STEP vuelve a Apolo como pieza.
  - Ahí Apolo gana: la placa dentro de su caja, con interferencias, pernos y separadores.
  - SPICE con ngspice por proceso. El firmware se emula con Renode por proceso, y sus GPIO son
    señales de la co-simulación: la placa propia maneja la máquina.
  - El `.kicad_pcb` se puede abrir y terminar en KiCad a mano.
- **D13 — Criterio eléctrico por defecto**, en `design/guidelines.py`, la fuente única:
  - cada motor lleva su protección;
  - parada de emergencia según IEC 60204-1 e ISO 13850;
  - masas a tierra;
  - IP según el ambiente;
  - 20 % de reserva en el tablero;
  - designaciones IEC 81346;
  - colores IEC 60204-1: negro para potencia, rojo para mando en alterna, azul para mando en
    continua, verde-amarillo para la tierra (PE) y azul claro para el neutro.

  `delivery_check` gana su semáforo eléctrico: ROJO si un motor no tiene protección, si no hay
  seta, si el ERC da error o si un conductor está subdimensionado.
- **D14 — Plantillas = super-comandos.** `create_conveyor`/`create_belt_conveyor` ganan
  `electrico` (por defecto apagado, para que un log viejo regenere igual). Con él generan el
  tablero estándar:
  - alimentación, seccionador, guardamotor o variador, motor;
  - seta, botonera y piloto;
  - fotocelda;
  - PLC con su programa base: marcha, paro, seta, falla y conteo.

  El agente parte de ahí y lo adapta.
- **D15 — Paquetes nuevos, con sus fronteras**:

  | paquete | qué contiene | regla |
  |---|---|---|
  | `library/electrico/` | catálogo eléctrico y cálculos | puros, nunca reciben `Document` |
  | `plc/` | parser, compilador, intérprete y exportadores | puro |
  | `cosim/` | modelos de dispositivos, solver de red, acople a MuJoCo, worker | trabaja sobre el snapshot |
  | `pcb/` | KiCad, Freerouting, ngspice y Renode | puentes a binarios externos |
  | `drawing/electrico/` | las láminas | — |
  | `services/electrico_*.py` | lo que lee un `Document` | — |
  | `api/routers/electrico.py`, `cosim.py` | transporte | — |
  | `ui/src/electrico/` | la UI | — |

  Los comandos van en módulos por familia (`commands/electrico*.py`) y nunca hacen crecer
  `registry.py` ni `models.py`. Cada paquete puro lleva su test de capas, como
  `tests/test_capas_media.py`.
- **D16 — Los datos vivos se ven sobre el 3D**, en módulos nuevos y nunca en `Viewport.tsx`:
  - etiquetas `CSS2DRenderer` con designación y valor;
  - color por dato en los cables (corriente o energizado), con la paleta de la guía de dataviz;
  - pilotos que se encienden en su color FÍSICO;
  - el display del variador;
  - mandos clicables en 3D.

  `ui/CLAUDE.md` hoy prohíbe tintes emisivos y reserva el rojizo para «falló el guardado». V8.4
  agrega la excepción acotada: el color físico de un piloto y el color por dato con su leyenda,
  nunca un rojizo de estado. También agrega las filas nuevas de «un concepto, un nombre»:
  tablero, esquema, cable, borne, dispositivo, señal, escenario.

Preguntas que sólo Mario contesta (no bloquean V8.0–V8.4):
1. **Mercados.** Perú (CNE + IEC) por defecto. ¿Vas a vender máquinas a EE.UU. (UL 508A /
   NFPA 79) u otro país?
2. **Marcas del catálogo.** Recomendación: Schneider, Siemens y ABB como gama alta, más una
   económica (Chint o LS), según lo que se consiga en Lima. ¿Cuáles usas o cotizas?
3. **PLC del primer exporte.** ¿Siemens S7-1200 (TIA Portal, SCL), Schneider o Codesys (PLCopen
   XML), Delta o Allen-Bradley? Decide qué formato se hace primero en V8.8.
4. **Placas.** ¿Tienes KiCad instalado? ¿Fabricante preferido (JLCPCB, PCBWay)? Lo necesita
   V8.10.

## Alternativas descartadas

- **Embeber OpenPLC/matiec o PySpice**: son GPL-3 y Apolo es MIT (D4, D12).
- **Simular la conmutación del variador o la máquina entera en SPICE**: unas 1000 veces más caro
  y no mejora ningún entregable (D3).
- **Editor de esquemas 2D a mano como fuente de verdad** (estilo EPLAN): es manipulación humana.
  El agente declara y Apolo dibuja (D6).
- **Modelo eléctrico como metadato del manifest**: sin undo, sin contrato, no viaja en
  `insert_project` y el 3D del tablero depende de él (D1).
- **Modelica u OpenModelica como motor**: otra cadena de herramientas y licencia OSMC/GPL para un
  problema acotado (red de control + modelos promedio). FMI/FMU queda como exportación futura,
  no como núcleo.
- **Exportar a EPLAN nativo**: formato cerrado. Se exporta AutomationML (IEC 62714), DXF/DWG, PDF
  y listas en Excel.
- **Ruteador de PCB propio**: Freerouting existe; el valor de Apolo está en la integración
  mecánica (D12).
- **Emular el micro en el navegador** (avr8js): la co-simulación vive en el backend para que el
  agente, los contratos y la persona vean la MISMA verdad (D7).
- **Co-simulación dentro del proceso de la API**: `PHYSICS_LOCK` y el worker único de jobs
  congelarían Apolo (D7).

## Fases

Cada V8.x lleva su contrato propio antes de implementarse, con tamaño, dependencias y gate
(pytest + ruff; si toca `ui/`, `npm test` + `npm run build`).

**Piloto común**: una faja de banda con `create_belt_conveyor` en esta PC, con VFD-2K2-220,
TABLERO-5040, ESTOP-40, BOTONERA-2 y FOTO-M18, todos ya en el catálogo. La faja 38 entra cuando
llegue su `.apolo` de la laptop.

**V8.0 — Medir y probar los riesgos** (sólo lectura más prototipos en el scratchpad · M ·
sin dependencias). Mide:
1. **Costo de editar un cable** (D1). Prototipo de un comando que no produce geometría,
   intercalado en un log largo (~450 comandos sintéticos, con `run_script` incluido). Se mide qué
   re-ejecuta un `edit_command` en cada una de las dos opciones de D1.
2. **MuJoCo con juntas reales y actuador** (D10). Sobre la faja piloto:
   - el tambor como hinge con actuador de par y 10 cajas;
   - tiempo por segundo simulado con `timestep` de 1, 2 y 4 ms;
   - estabilidad del contacto caja-banda con fuerza tangencial;
   - el rayo de la fotocelda.
3. **PLC**: prototipo de compilador ST → Python con un programa de ~300 líneas, TON/CTU y FB.
   Mide el µs por scan.
4. **Red de control**: MNA de 60 nodos en numpy, µs por paso.
5. **Proceso vivo**: ida y vuelta por pipe más WebSocket a 30 Hz con 50 cuerpos. Mide latencia y
   ancho de banda.
6. **Binarios externos en esta PC**: `kicad-cli`, Freerouting (Java), ngspice y Renode. Sólo se
   comprueba si están y qué versión. No se instala nada sin Mario.

Se verifica con la tabla en la Bitácora, D1 y D10 cerradas y una estimación de factor de tiempo
real para el piloto.

**V8.1 — El modelo eléctrico** (`commands`, `library/electrico`, `services`, `api`, MCP · L ·
depende de V8.0):
- Comandos de dispositivo, cable, bornera, puente y programa de PLC (D1). Los dispositivos se
  pueden ligar a una pieza que ya existe, como el motor de `create_belt_conveyor`.
- Catálogo eléctrico con bornes y modelos (D2): unas 60 refs para la faja.
- Designaciones automáticas IEC 81346.
- ERC: bornes sin conectar, cortocircuitos directos, tensiones incompatibles, motor sin
  protección, PE faltante.
- `get_circuit` y `electrical_check`.
- Lista de dispositivos, lista de cables y BOM eléctrica en el costeo.
- Se verifica con tests del ERC sobre redes sintéticas y el piloto declarado por MCP con un
  `run_batch` con contrato.

**V8.2 — La máquina se mueve de verdad** (`physics`, `robotics` · L · depende de V8.0, en
paralelo con V8.1):
- Mecánica dinámica general (D10).
- `simulate_dynamics` en lote, con fotogramas por TIEMPO (se corrige la ambigüedad de `fps`).
- Se verifica con tests físicos de referencia:
  - péndulo con su periodo analítico;
  - tambor con par constante → aceleración = T/J;
  - caja sobre la banda → llega a la velocidad de la banda;
  - el rayo de la fotocelda detecta la caja en el instante esperado.

**V8.3 — La faja arranca desde su tablero** (`cosim`, `plc`, `api`, MCP · L · depende de V8.1 y
V8.2):
- Modelos de dispositivos (D3), solver de red, compilador ST (D4) y proceso aparte en lote (D7).
- Escenarios y aserciones (D9); `simulate`, `test_plc`, `get_simulation`.
- Se verifica con tests de dispositivo contra datos de catálogo:
  - el guardamotor clase 10 a 7,2 × Ir dispara en 4–10 s (IEC 60947-4-1);
  - la curva par-velocidad del motor reproduce los datos de placa;
  - la rampa del variador.
- E2E por MCP: el agente declara el tablero, escribe el programa y corre tres escenarios
  (marcha, seta, atasco) en verde.

**V8.4 — Ver la máquina viva** (`ui`, `api` · L · depende de V8.3):
- Modo en vivo (D7), mandos clicables en 3D y datos sobre el 3D (D16).
- Panel de tendencias.
- Multímetro y osciloscopio: clic en un borne o cable.
- Esquema 2D interactivo con referencia cruzada 3D ↔ esquema (como SVG en línea, no `<img>`).
- Vista en línea del programa con los valores vivos y la escalera con los peldaños energizados.
- Tratamiento propio en Visor.
- Se verifica en el preview: Mario aprieta el botón verde, el piloto se enciende, el variador
  rampa a 60 Hz, la banda arranca, la caja corta la fotocelda y suma el contador; la seta detiene
  todo.

**V8.5 — El tablero 3D de verdad** (`commands`, `library/electrico`, `kernel` · L · depende de
V8.1):
- `layout_tablero` (D5): rieles, canaletas, colocación, puerta, ruteo de cables con su largo, %
  de llenado, prensaestopas y calentamiento IEC/TR 60890 con ventilación sugerida.
- Cables de campo (tablero → motor y sensores) por puntos de paso a lo largo de la estructura.
- Se verifica con: interferencia cero dentro del tablero, largo de cada cable con ±5 % de un
  ruteo a mano y la puerta que abre (junta) sin chocar.

**V8.6 — Planos eléctricos y memoria de cálculo eléctrica** (`drawing/electrico`, `services`,
`library/electrico` · L · depende de V8.1 y V8.5):
- Juego IEC 61082 (D6), con cajetín, índice, referencias cruzadas y etiquetas para marcar cables
  y dispositivos.
- Memoria eléctrica:
  - demanda;
  - ampacidad con factores de corrección;
  - caída de tensión;
  - cortocircuito IEC 60909 y poder de corte;
  - coordinación tipo 2 y selectividad;
  - contactos indirectos y diferencial;
  - sección de PE;
  - calentamiento del tablero.
- Manual eléctrico: operación, alarmas, mantenimiento y diagnóstico por código de falla.
- Mano de obra de cableado, programación y puesta en marcha en la cotización.
- Eje nuevo del [benchmark](../benchmark/README.md): «E7 eléctrico», con su rúbrica (lo que
  entrega un despacho con EPLAN).

**V8.7 — Seguridad funcional y fallas** (`library/electrico`, `cosim` · M · depende de V8.3):
- ISO 13849-1: PLr por gráfico de riesgo, categoría, MTTFd (B10d del catálogo), DCavg, CCF y el
  PL alcanzado frente al requerido.
- Inyección de fallas: contacto soldado, cable cortado, corto, pérdida de fase, sensor pegado,
  atasco. Comprueba que la función de seguridad se mantiene ante una falla (categoría 3).
- Informe de FAT virtual: protocolo más resultados con trazas.

**V8.8 — Del gemelo al PLC real** (`plc`, `api` · L · depende de V8.3 y de P3):
- Exportes (D4) y tabla de tags.
- PLC real o virtual del fabricante en el lazo, por OPC UA y Modbus TCP: Apolo hace de planta
  (comisionamiento virtual de verdad).
- Apolo como servidor OPC UA para un SCADA.
- HMI simulada: pantallas, alarmas y recetas que el agente diseña y que se ven en la puerta del
  tablero.
- Las licencias de asyncua y pymodbus se verifican aquí.

**V8.9 — Neumática y electroneumática** (`library`, `cosim` · M · depende de V8.3):
- Cilindros ISO 15552/6432, válvulas 5/2 y 5/3, FRL y consumo de aire.
- Fuerza y velocidad por caudal.
- Esquemas ISO 1219.
- Bobinas de válvula en la red eléctrica. Caso canónico: el empujador de una faja
  clasificadora.

**V8.10 — Placas I: esquema de la placa y SPICE** (`pcb`, `drawing` · L · depende de V8.1 y de
P4):
- Red de la placa (D12) y ERC de placa.
- Símbolos y huellas: se verifica la licencia de las librerías de KiCad.
- SPICE con ngspice por proceso.

**V8.11 — Placas II: de la placa a la fábrica** (`pcb` · L · depende de V8.10):
- Colocación por reglas, ruteo con Freerouting y DRC con `kicad-cli`.
- Gerber, taladros, pick and place y BOM.
- STEP de vuelta a Apolo dentro de su caja.
- Reglas de fabricación del fabricante elegido.

**V8.12 — Placas III: el firmware mueve la máquina** (`pcb`, `cosim` · M/L · depende de V8.3 y
V8.11):
- Firmware compilado afuera (`arm-none-eabi-gcc` / `arduino-cli`), emulado en Renode, con sus GPIO
  conectados a la co-simulación.

**V8.13 — Verifica** (S · depende de todo lo anterior):
- E2E completo sobre el piloto y sobre la faja 38.
- Corrida del benchmark E7.
- Las reglas durables van a los CLAUDE.md, se actualizan los conteos y el roadmap.

Orden y paralelismo:
- V8.1 ∥ V8.2 → V8.3 → V8.4. **Hito para Mario**: la faja arranca desde su tablero y se ve viva.
- V8.5 y V8.6 corren en paralelo con V8.3 y V8.4 (sólo dependen de V8.1).
- V8.7, V8.8 y V8.9 tras V8.3.
- Las placas (V8.10 → V8.12) pueden empezar tras V8.1.

## Lo que este plan NO hace

- Conmutación del variador ni transitorios electromagnéticos finos (D3).
- PCB de alta velocidad, RF o integridad de señal; en v1, placas de más de 4 capas.
- Certificar: Apolo genera la documentación para UL, CE o la conformidad local, pero no
  certifica, y sus planos no reemplazan la firma de un ingeniero colegiado (D11).
- Formato nativo de EPLAN, TIA Portal (`.ap17`+) o Studio 5000 (`.ACD`): se exporta por formatos
  abiertos o de importación (D4, D6).
- Editor de esquemas por arrastre (D6).

## Riesgos

| riesgo | mitigación |
|---|---|
| Python no alcanza el tiempo real con MuJoCo a 1 ms, red y PLC | V8.0 lo mide. Plan B: `timestep` de 2 ms, red compilada a numpy vectorizado y PLC compilado; si aún no alcanza, el modo vivo corre más lento y lo dice (D7) |
| Contacto caja-banda inestable o irreal en MuJoCo | V8.0 prueba la fuerza tangencial por contacto; los rodillos usan fricción nativa |
| Editar un cable re-ejecuta la geometría de todo el log | Decisión medida en V8.0 (D1) |
| Datos de catálogo inventados que pasan por reales | Cada ref cita su línea de fabricante y lleva `cotas_verificadas`/«verificar con el proveedor»; los tests fijan sus valores |
| El modelo del motor estimado de la placa no se parece al real | Test contra la curva publicada de un motor IE2/IE3 real; la memoria declara la hipótesis |
| Licencias GPL contaminan el paquete MIT | Sólo binarios externos por subproceso; cada versión re-verifica la licencia de lo que adopta |
| Alcance enorme: nunca se termina | Cada V8.x entrega algo usable por sí sola; el hito de V8.4 llega antes que planos y placas |
| La UI viva hace crecer los archivos congelados | Todo en `ui/src/electrico/` y módulos nuevos; los trinquetes lo vigilan |
| Responsabilidad legal por un tablero mal diseñado | Aviso en cajetín y memoria (D11); `delivery_check` en ROJO no entrega |

## Bitácora

(vacía: V8.0 es lo siguiente)
