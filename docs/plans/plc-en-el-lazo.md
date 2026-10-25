---
estado: implementado
nota: contrato derivado de un plan aprobado por el titular el 2026-10-24 (A1–A9); las siete fases mergeadas o en revisión (F1d2, puntos de UI: chips de la barra viva, pantallas 3D y la API viva de las extensiones). Queda: el carril no sabe que un cable de red une dos PUERTOS (plan de la red de datos)
descripcion: un PLC de verdad (o el simulador de su fabricante) mueve la máquina virtual en vivo o en una corrida a la pared, y se dice que esa corrida no es determinista; una pantalla de operador o un SCADA escriben variables del programa y siguen la sesión viva; el catálogo trae un panel de operador de 7″ para la puerta del tablero
---

# Un PLC de afuera mueve la máquina virtual y una pantalla en la puerta del tablero le escribe al programa

## Estado y origen

- Una extensión que exporta el programa del PLC a un PLC real necesita puntos que el núcleo no le
  da: con ellos prueba que el PLC de verdad hace lo mismo que el programa probado en el gemelo y le
  da a la máquina una pantalla de operador y un SCADA. Los midió la F0 de un plan que vive fuera
  del núcleo (V8.8 de [V8](V8-maquina-viva.md); D2 (d) de
  [núcleo abierto](nucleo-abierto-extensiones-privadas.md)), aprobado por el titular el
  2026-10-24. Este plan cuenta sólo los ajustes GENÉRICOS (A1–A9 de aquel plan).
- Respuestas provisorias aprobadas que tocan al núcleo: el panel de operador del catálogo es uno
  genérico de 7″ (800×480, 24 VDC, montaje en puerta); el lazo se prueba con un PLC falso en otro
  proceso (no hay hardware ni simulador del fabricante en el banco).
- Misma forma que [cosim-fallas](cosim-fallas.md),
  [puntos de extensión de entregables](puntos-de-extension-entregables.md) y
  [datos de corte y acometida](datos-de-corte-y-acometida.md).
- Contrato redactado tras una medición de sólo lectura (sub-agente) sobre `833ce8e`, revisado y
  decidido por la sesión principal (al final de § Decisiones).

## Lo que hay hoy

Rutas relativas a `core/apolo/`, medidas sobre `833ce8e`.

- **Superficie (A1).** `extensiones_api.SUPERFICIE` (l. 28-78) trae de la co-simulación sólo
  `Modelo` (l. 51); `MODULOS` (l. 83-148) no trae nada de `apolo.plc`. La lectura del programa del
  documento YA es contrato: `apolo.services.electrico.modelo` (l. 135) y `Programa` (l. 139), cuyo
  `compilado` es el `apolo.plc.Compilado` (`library/electrico/modelo.py:169-183`).
- **Comentarios (A2):** el lexer los descarta (`plc/lexer.py:95-109`); `ast_st.Unidad`
  (l. 228-230) sólo tiene `globales` y `pous`.
- **Direcciones (A9):** `plc/direcciones.py:1-6` y `cosim/modelos/plc_es.py:33-40`: `%IX0.0` ↔
  `I0.0`, `%IW0` ↔ `AI0`, analógica en cuentas 0–27648. El PLC del catálogo cita como línea de
  referencia una CPU compacta (`library/data/122_maniobra_control.yaml:249`) cuyas analógicas
  integradas van por defecto en `%IW64`/`%IW66` y cuyas digitales se escriben `%I0.0`. La ficha no
  trae direcciones del fabricante (`library/electrico/ficha.py:63-65`).
- **El PLC de la corrida es una clase fija (A3).** `Corrida.__init__` arma `PLC(p.compilado, …)`
  (`cosim/corrida.py:106-110`); la corrida usa 13 miembros: `compilado.entradas`,
  `escribir_entrada`, `paso`, `salidas`, `estado`, `cortar`, `reponer`, `stop`, `run`
  (`corrida.py:38-63`), `variables`, `falla` (`:66-69`), `fallas`, `scans`
  (`planificador.py:68-69`). El snapshot (`cosim/datos.py:71-91`) no puede llevar «este PLC es de
  afuera». Un proxy fuera del núcleo anduvo en un script pero no llega al worker.
- **Ritmo (A4):** la sesión viva avanza a ráfagas de 1/30 s (`cosim/vivo.py:32`,
  `cosim/worker_vivo.py:129-131`). Medido con el PLC en otro proceso: 4–8 ms de la entrada a la
  salida con un intercambio de 2 ms por vez, 44 ms con ráfagas de 32 ms; 0 atrasos en 1500
  intercambios al ritmo de la pared en Windows. El lote (`planificador.correr`, l. 36-73) no mira
  la pared.
- **Escribir una variable (A5):** `PLC.leer(ruta)` existe (`plc/runtime.py:209-262`); escribir,
  no. `Compilado.rutas` (`plc/compilador.py:436-446`) no guarda el tipo ni si es `CONSTANT`. Las
  acciones (`cosim/escenario.py:48-49`) son de mandos y la `Agenda` sólo ve `tablero.modelos`
  (`cosim/agenda.py:63-69`, `:119-127`).
- **Sesión viva 1 a 1 (A6):** `SesionViva` tiene UNA cola hacia su WebSocket
  (`api/routers/cosim_vivo.py:91-129`, descarte pasados 60 fotogramas, l. 59); una sesión por API
  (l. 132-164); nada en proceso puede leer los fotogramas ni mandar acciones.
- **Catálogo (A7):** no hay panel de operador ni puerto de red. Los bornes tienen `rol` eléctrico
  (`ficha.py:33`) y el ERC los recorre (`library/electrico/erc.py:260,318`). La puerta coloca
  mandos en una cuadrícula de 70 × 80 mm (`library/electrico/colocacion_modelo.py:31-32`); su hueco
  es la caja del mando o un círculo (`library/electrico/armado.py:124-125,324-333`;
  `huecos_por_ref` sólo admite círculo, l. 257). 428 refs.
- **UI (A8):** una extensión de la UI sólo trae paneles (`ui/src/extensiones/tipos.ts:24-42`); la
  barra viva tiene paneles fijos (`ui/src/vivo/BarraVivo.tsx:23-27`); los mandos con pieza se tocan
  por raycast (`ui/src/vivo/mandos3d.ts`); la lectura y el envío de la sesión existen en
  `ui/src/vivo/sesion.ts:57-62,155` pero una extensión sólo llega por ruta relativa.
- **Vigencia:** `COSIM_EPOCH = 5` (`cosim/__init__.py:25`); la huella de
  `tests/test_cosim_epoch.py` cubre `cosim/**`, `plc/**` y `services/cosim_snapshot.py`;
  `CONTRATO_EXTENSIONES = 1` (`extensiones.py:65`).

## Lo que se revisó antes de escribir esto

- **La medición con el PLC en otro proceso dejó tres reglas.** El PLC externo NO se reinicia con
  la planta (la segunda corrida heredó la marcha enclavada de la primera): `cortar()`/`reponer()`
  son la ALIMENTACIÓN virtual y el conector las recibe. Sin 24 V virtuales el PLC de afuera se
  queda con las últimas entradas: el conector tiene que enterarse del corte. La huella cambió en
  9 de 9 corridas con el externo y fue idéntica con el interno: no es determinista.
- **La cara son 13 miembros**, más la construcción; para A5 la `Agenda` también necesita los PLC.
  `apolo.plc.PLC` la cumple sin cambios.
- **El lote «a la pared» también necesita ritmo**: el ritmo es un módulo compartido, no un retoque
  de `worker_vivo.py`.
- **El núcleo no puede leer el metadato de una extensión** (`ext` es opaco): el PLC externo entra
  por el pedido de la corrida (D6).
- **El chequeo de tipo de A5 necesita la tabla de símbolos**; `compilador.py` (473 líneas) no
  tiene lugar: va a `plc/simbolos.py`.
- **Un puerto de red no es un borne**: va en un bloque aparte, como los `puertos` del bloque
  neumático (`library/neumatica/ficha.py:31`).
- **El panel de 7″ ocupa 3 × 2 celdas de la puerta** y su recorte es menor que su frente: hace
  falta un hueco rectangular.
- **El bus es fan-out de la cola que ya existe**: copiar en `SesionViva._poner` (en el loop) a
  colas propias con descarte no frena a la persona ni toma `STATE_LOCK`.

## Decisiones (para vetar)

- **D1 — Superficie del PLC en `MODULOS` (A1)**, con los nombres de hoy (un test lo exige):
  `apolo.plc` (`compilar`, `PLC`, `Compilado`, `ErrorCompilacion`, `ErrorST`, `FallaPLC`, `RUN`,
  `STOP`, `SIN_TENSION`); `apolo.plc.parser` (`parsear`); `apolo.plc.ast_st` (los nodos y
  `Comentario` de D2); `apolo.plc.tipos` (`FB_ESTANDAR`, `ELEMENTALES`, `CONVERSIONES`,
  `FUNCIONES_ESTANDAR`, `DEFECTO`, `RANGO`); `apolo.plc.direcciones` (`parsear`, `Direccion`,
  `ESCALA_AI`). La lectura del programa ya es contrato. Agregar no sube `CONTRATO_EXTENSIONES`.
- **D2 — Comentarios en el AST, sin tocar lo compilado (A2).** `tokenizar(fuente,
  comentarios=None)` junta, si le dan la lista, `ast_st.Comentario(texto, linea, col, linea_fin,
  estilo)`; `parsear` los pone en `Unidad.comentarios` (vacío por defecto). Los tokens no cambian:
  `fuente_py`, `mapa_lineas` y `tags` idénticos. Lista plana con línea (los nodos sólo tienen la
  línea de inicio; quien imprime intercala por línea).
- **D3 — Direcciones del fabricante en la ficha, fuera de `modelo` (A9).** `electrico.direcciones:
  {borne: texto}` OPCIONAL; si viene, cubre TODAS las E/S de la ref, sin repetidos ni vacíos, y pide
  `fuente` (`a_confirmar` puede nombrar `direcciones`). Lo valida un módulo chico nuevo (`ficha.py`
  sólo engancha) y `ficha_payload` lo publica. En el PLC del catálogo, los valores por defecto de
  la CPU de su línea de referencia citados del manual de sistema del fabricante; si no se puede leer
  en ≈ 15 min, a `a_confirmar` sin valor. El ST de Apolo sigue con `%IX`/`%IW0` (V8.3 D4).
- **D4 — `PuertoPLC`: la corrida usa una CARA, no la clase `PLC` (A3).** `cosim/puerto_plc.py`
  (puro): el `Protocol` con los 13 miembros, la excepción `LazoCortado(motivo)` y el registro
  `CONECTORES`; opcionales `escribir(ruta, valor)` (D10), `pausar()`/`reanudar()` (D8),
  `reconectar()`, `cerrar()`. `Conector(programa, config)` con `validar_config(config) -> list[str]`
  puro. `apolo.plc.PLC` la cumple tal cual: sin externo, `Corrida` es la de hoy. `SUPERFICIE` suma
  `PuertoPLC` y `LazoCortado`.
- **D5 — `Extension.conectores_plc` (A3)**: `{"prefijo.x": clase}` o función perezosa; validado al
  cargar, todo o nada (prefijo, miembros obligatorios, `validar_config` llamable, sin repetidos);
  entra a `extensiones._registros()`; `GET /api/extensiones` lo lista. La clase viaja al worker por
  pickle como `modelos_extension`; el worker nunca busca extensiones; el módulo del conector importa
  su librería de red al conectar, no al importarse.
- **D6 — El PLC externo lo elige el PEDIDO de la corrida, no el documento.**
  `plc_externo: {"-K1": {"conector": "x.y", "config": {…}}}` en `POST /api/cosim/run` y en
  `WS /api/cosim/vivo` (query, JSON ≤ 1 KB); la UI por `abrirSesion(…, {plcExterno})`. La API valida
  ANTES del worker (conector cargado, PLC con programa en el carril, `validar_config` sin
  problemas) o 400/4400 con qué corregir. El snapshot suma `externos: {designación: (clase,
  config)}`, vacío sin externo. Si conectar falla, la corrida no arranca. Nada entra al log, a la
  firma ni al `.apolo`: probar contra un PLC de banco no cambia la máquina.
- **D7 — Con un PLC externo la corrida NO es determinista, y se dice.** El resultado suma
  `resumen.determinista: false`, `plc_externo: {designación: {conector, extension, version}}` y
  `lazo` (ida y vuelta de `paso()` medida por el NÚCLEO: mediana, p99, máximo en ms; intercambios,
  atrasados, atraso máximo). `veredicto: null` con su motivo; nunca se guarda como resultado del
  escenario (no entra a la vigencia ni a las puertas). Sin externo, el dict y la huella idénticos.
- **D8 — Lazo cortado y pausa.** `LazoCortado` de cualquier miembro: en el lote, la corrida termina
  con error «lazo cortado en t = … s: <motivo>», sin resultado parcial; en vivo, la sesión se PAUSA
  (`{"tipo": "pausa", "motivo": "lazo", "mensaje"}`) y nunca sigue con salidas viejas; `reanudar`
  llama a `reconectar()` si lo hay. La pausa manual con externo llama a `pausar()`/`reanudar()` y el
  `fin` dice que el PLC externo siguió corriendo durante la pausa.
- **D9 — Ritmo de lazo, sólo con un PLC externo (A4).** `cosim/ritmo.py`: `RitmoPared(dt,
  reloj=perf_counter, dormir=sleep)` espera hasta t₀ + k·Δt (duerme en tajadas mientras falte más de
  1,5 ms, después espera activa), cuenta atrasados y perdona una deuda de más de `REBASE_S`; reloj y
  dormir inyectables. En vivo con externo, UN intercambio por vez y el fotograma cada 1/30 s
  virtual; `ritmo` ≠ 1 es 4400. En el lote con externo, el mismo `RitmoPared`. Sin externo, byte por
  byte lo de hoy.
- **D10 — Escribir una variable del PLC (A5).** `Compilado.simbolos: {ruta: (tipo, escribible)}`
  (`plc/simbolos.py`); `PLC.escribir(ruta, valor)` resuelve la ruta como `leer`. Escribibles:
  elementales y elementos de ARRAY de las globales y de cada PROGRAM; NO `CONSTANT`, `AT %I…`/`%Q…`
  ni miembros de una instancia de FB (cada rechazo dice por qué). Valor: BOOL bool o 0/1; INT/DINT
  entero en su rango (fuera es rechazo); REAL finito; TIME ms enteros. Entra antes del próximo scan
  y el programa puede pisarla. Acción `{"accion": "escribir", "dispositivo": "-K1", "variable":
  "Main.consigna", "valor": 50}` en escenario y en vivo; la `Agenda` recibe los PLC; `validar` da
  400 al declarar una ruta mala; se graba con su hora; con externo, `escribir` del puerto o rechazo.
  El docstring de `set_scenario` la documenta (el golden cambia sólo ahí).
- **D11 — Bus de la sesión viva, en proceso (A6).** `api/vivo_bus.py`: `suscribir(nombre,
  max_fotogramas=60) -> Suscripcion` y `enviar_vivo(nombre, msg) -> bool` (en `SUPERFICIE`). Colas
  acotadas por suscripción con descarte contado, sin tocar la de la persona; mismo orden que el WS.
  `enviar_vivo` pasa la validación del WS, lleva acciones y eventos (NUNCA controles), su ack vuelve
  sólo a esa suscripción, `False` sin sesión. No abre sesiones (V8.4 D10) ni toma `STATE_LOCK`.
- **D12 — Panel de operador y puertos de datos en el catálogo (A7).** Ref `HMI-7IN-24VDC` en
  `maniobra_control` (`funcion: P`, montaje puerta, bornes `L+`/`M`/`PE`, carga 24 VDC, línea de
  referencia «del orden de» un panel de 7″ comercial, `cotas_verificadas: false`, `cost`
  referencial, `datos` con `T_max_C` o `a_confirmar`). Bloque nuevo `electrico.puertos: [{id,
  tipo}]` (`rj45`) fuera de `bornes` y de `modelo` (ni la red ni el ERC ni la firma los ven); lo
  llevan el panel y el PLC del catálogo. Los variadores no ganan puerto si su línea de referencia no
  lo trae de serie. Cable `CABLE-RJ45-CAT6` por metro con `add_cable` sin hilos (si no entra, F1d1
  lo mide y lo trae a revisión antes de ampliar un comando). Modelo `cosim/modelos/hmi.py` (tipo
  `hmi`: encendida con tensión ≥ el mínimo, falla `apagada` con gemelo sano, señal
  `-P?.encendida`, `pantalla_px`). En la puerta ocupa ⌈ancho/paso⌉ × ⌈alto/paso⌉ celdas y va
  PRIMERO, arriba; su hueco es el RECORTE (`huecos_por_ref` admite `("rect", ancho, alto)`); un
  tablero sin panel se arma idéntico.
- **D13 — Puntos de UI (A8)**, todos opcionales y validados con prefijo: (a) `Extension.chipsVivo`
  en la barra viva; (b) `Extension.pantallas3d` (`{id, tipo, dibujar(ctx, vivo), tocar?(x, y,
  vivo)}`): un plano con `CanvasTexture` sobre la cara frontal de la pieza del dispositivo de ese
  `tipo`, resolución `pantalla_px`, toques por raycast uv → px con la captura de `mandos3d.ts`
  (lógica en `.ts` puros); (c) API viva declarada `ui/src/extensiones/vivo.ts` (`useFaseVivo`,
  `valorVivo`, `inicioVivo`, `enviarVivo`, `abrirSesionViva(escenario, {plcExterno})`). Sólo tokens
  del tema y `prefers-reduced-motion`.
- **D14 — Vigencia, una decisión por cosa.** `COSIM_EPOCH` no sube en ninguna fase (sin externo,
  sin `escribir` y sin panel, el mismo documento da el mismo resultado; con externo no es vigente):
  cada fase que toca `ARCHIVOS` actualiza la huella con los escenarios del banco iguales como
  evidencia. La firma del documento no se mueve (`direcciones` y `puertos` fuera de `modelo`).
  `GEOM_CACHE_EPOCH` no. Versiones de comandos no (si `test_contrato_comandos` lo pide por la
  colocación en varias celdas, se actualiza la huella sin subir la versión de `layout_tablero`, con
  los armados del banco idénticos). `CONTRATO_EXTENSIONES` sigue en 1 (sólo se agrega). `.apolo`,
  log y SQLite iguales (`Compilado.simbolos` no se persiste). Ninguna tool MCP nueva.
- **D15 — La extensión falsa de la suite lo usa todo** (`tests/ext_prueba/`): un conector JSON por
  línea sobre TCP de stdlib con un PLC falso en otro proceso, variantes que no cargan, un suscriptor
  del bus y, en el muestrario de la UI, un chip y una pantalla de prueba.

**Decisiones de la revisión** (sesión principal, 2026-10-25): D6 tal cual (el pedido de la corrida,
nunca el documento); letra P para el panel (IEC 81346-2: presenta información) y arriba en la
puerta; queda FUERA que un conector se declare determinista para que su grabación valga en la
puerta (otro plan si alguna vez hace falta); el reparto en siete fases.

## Alternativas descartadas

- **Declarar el PLC externo en el documento**: cambiaría la firma y vencería resultados por una
  prueba de banco.
- **El PLC externo como modelo de co-simulación**: los modelos viven en el tablero y ven la red; el
  ciclo del PLC vive en `corrida.plcs`, después del tablero (V8.3 D8).
- **Seguir con un proxy fuera del núcleo**: no llega al worker ni a la sesión viva.
- **Escribir variables con mandos o `entrada_pegada`**: un mando es un borne físico; una pantalla
  escribe memoria.
- **Un segundo WebSocket para la extensión**: la sesión es 1 a 1 (V8.4) y la extensión corre en
  proceso.
- **Puertos de datos como bornes**: la red de mando y el ERC recorren bornes.
- **Cambiar el ST de Apolo a las direcciones del fabricante**: rompería todos los programas y
  V8.3 D4.
- **El ritmo de pared siempre**: espera activa sin ganancia para la máquina virtual sola.
- **Que el conector reporte su propia latencia**: el número dejaría de ser verificable.

## Fases

Orden con dos agentes como máximo: F1a → F1b1 ∥ F1c1 → F1b2 ∥ F1d1 → F1c2 ∥ F1d2. F1b1 y F1c1
tocan `corrida.py` y la huella: la segunda en mergear rebasa y re-mide. F1c2 va tras F1b2 (las dos
tocan `cosim_vivo.py`).

- **F1a — Superficie, comentarios y direcciones** (`extensiones_api.py`, `plc/lexer.py`,
  `plc/parser.py`, `plc/ast_st.py`, `library/electrico/ficha.py` + módulo de direcciones,
  `122_maniobra_control.yaml` · M · ≈ 60 min): D1, D2, D3. **Se verifica:** suite completa y `ruff`;
  el gate de `MODULOS`; los tres estilos de comentario con línea, columna y fin, uno sin cerrar con
  su error, tokens idénticos con y sin juntar; el `Compilado` idéntico con y sin comentarios en los
  programas de `test_plc_*`, del banco y del sintético; cada rechazo de `direcciones` y el PLC del
  catálogo con su mapa o en `a_confirmar`; las firmas de los 4 tableros de `tests/tablero_electrico.py`
  iguales; la huella sin subir con el banco igual.
- **F1b1 — PLC externo en el lote y ritmo de pared** (`cosim/puerto_plc.py`, `cosim/ritmo.py`,
  `corrida.py`, `planificador.py`, `datos.py`, `services/cosim_snapshot.py`, `extensiones*.py`,
  `api/routers/cosim.py`, `tests/ext_prueba/` · L · ≈ 90 min · depende de F1a): D4–D7, D8 y D9 en el
  lote, D15 del lote. **Se verifica:** `RitmoPared` con reloj falso; una corrida con el conector
  falso y el PLC falso en otro proceso (`determinista: false`, `lazo` con números, sin veredicto ni
  resultado guardado); la misma sin externo idéntica; cada 400; cada rechazo al cargar la extensión
  con el registro deshecho; matar el PLC falso a mitad da el error con su hora; el gate de imports
  del worker intacto; la huella sin subir.
- **F1b2 — PLC externo en la sesión viva** (`cosim/worker_vivo.py`, `cosim/vivo.py`,
  `api/routers/cosim_vivo.py` · M · ≈ 55 min · depende de F1b1): D6 en el WS, D8 y D9 en vivo.
  **Se verifica:** un intercambio por vez y fotogramas a 30 Hz; `ritmo=2` da 4400; matar el PLC
  falso pausa con motivo «lazo» y reanudar con el PLC de vuelta sigue; la pausa manual llama a
  `pausar()`; sin externo, el determinismo de `test_cosim_vivo.py` intacto; la huella sin subir.
- **F1c1 — Escribir una variable** (`plc/simbolos.py`, `plc/compilador.py`, `plc/runtime.py`,
  `cosim/escenario.py`, `cosim/agenda.py`, `cosim/corrida.py`, `cosim/puerto_plc.py`,
  `tools/cosim.py` y golden · M · ≈ 60 min · depende de F1a): D10. **Se verifica:** `simbolos` con
  globales, PROGRAM, FB, ARRAY y CONSTANT; `escribir` por tipo y cada rechazo; la acción en
  escenario y en vivo y la grabación vuelta escenario con la misma huella; `validar` rechaza al
  declarar; el golden con el diff sólo en `set_scenario`; `test_plc_rendimiento` en su tope; la
  huella sin subir.
- **F1c2 — Bus de la sesión viva** (`api/vivo_bus.py`, `api/routers/cosim_vivo.py`,
  `extensiones_api.py`, `tests/ext_prueba/` · S/M · ≈ 45 min · depende de F1b2): D11. **Se
  verifica:** un suscriptor recibe todo en orden; uno que no lee descarta y cuenta mientras el WS
  recibe todo; `enviar_vivo` aplica, el ack llega sólo al suscriptor y queda grabada; sin sesión
  `False`; un control y un mensaje de más de 4096 bytes, rechazados; el bus nunca toma
  `STATE_LOCK`.
- **F1d1 — Panel de operador, puertos y cable** (YAML 122 y 125, `ficha.py` + módulo de puertos,
  `colocacion_puerta.py`, `colocacion_modelo.py`, `armado.py`, `commands/tablero_geom.py`,
  `cosim/modelos/hmi.py`, `cosim/vivo_fotograma.py`, `ui/src/vivo/arbolSenales.ts` y `fallas.ts` ·
  L · ≈ 90 min · depende de F1a): D12. **Se verifica:** refs honestas (428 → 430);
  `TIPOS_MODELO == MODELOS`, gemelo sano de `apagada`, el panel con y sin tensión; cada rechazo de
  `puertos`; un tablero con panel (celdas arriba, hueco = recorte, holgura y recorrido de la puerta
  verde y rojo); los armados del banco sin panel idénticos; el cable de red; la huella sin subir;
  `npm test` y `npm run build`.
- **F1d2 — Puntos de UI** (`ui/src/extensiones/tipos.ts`, `registro.ts`, `vivo.ts`;
  `ui/src/vivo/BarraVivo.tsx`, `reproductorVivo.ts`, `pantallas3d.ts` y su lógica pura; el
  muestrario · M/L · ≈ 75 min · depende de F1d1): D13. **Se verifica:** `npm test`, `npm run build`
  y los trinquetes; el registro acepta y rechaza chips y pantallas; uv → px y la cara frontal de una
  pieza girada; la barra sin extensiones idéntica; el muestrario con una extensión de prueba que
  pinta y, al tocar, manda un `escribir`.

Al cerrar cada fase: una línea en el CLAUDE.md que toque (`plc/`, `cosim/`, `api/`, `library/`,
`ui/`) y la `nota:`. Las cifras de «Estado actual» se miden con `python scripts/conteos.py`.

## Lo que este plan NO hace

- Ningún conector a un PLC real ni dependencias de redes industriales: son de la extensión.
- No exporta el programa ni lo descarga a un PLC; no modela la red de datos (IP, switch, tiempos
  de bus); no dibuja pantallas ni define alarmas o recetas.
- No da veredicto con un PLC externo ni vuelve su grabación una prueba de las puertas.
- No abre una sesión viva para el agente (V8.4 D10).
- No cambia la semántica del PLC virtual ni sus direcciones IEC.
- No cambia el formato del `.apolo`, del log, de la SQLite ni de la entrada de la red; no suma
  tools MCP.

## Riesgos

| riesgo | mitigación |
|---|---|
| La espera activa come CPU | sólo con un PLC externo (D9) |
| Un conector lento atrasa el intercambio | el núcleo mide la ida y vuelta y los atrasos (D7) |
| El worker carga dependencias pesadas al des-pickear el conector | D5 (importar al conectar) con un test sobre los módulos del worker |
| Una corrida con PLC real se toma como prueba | `determinista: false`, sin veredicto ni resultado guardado (D7) |
| `escribir` rompe el determinismo | es una acción con hora, grabada; test de la grabación vuelta escenario |
| Un suscriptor del bus que no lee | colas acotadas con descarte contado; la de la persona no se toca |
| Archivos cerca del tope (`compilador.py` 473, `cosim/tablero.py` 451, `erc.py` 432, `escenario.py` 426, `ficha.py` 414, `armado.py` 412) | módulos nuevos; ninguno pasa de 500 |
| La dirección `%IW64` sin fuente leída | a `a_confirmar` y la ficha lo dice |
| El cable de red no entra por `add_cable` | F1d1 lo mide y lo trae a revisión |
| Una extensión vieja contra el núcleo nuevo | sólo se agrega; `CONTRATO_EXTENSIONES` sigue en 1 |

## Bitácora

### F1a — Superficie, comentarios y direcciones

**D1.** `extensiones_api.MODULOS` suma `apolo.plc` (`compilar`, `PLC`, `Compilado`,
`ErrorCompilacion`, `ErrorST`, `FallaPLC`, `RUN`, `STOP`, `SIN_TENSION`), `apolo.plc.parser`
(`parsear`), `apolo.plc.ast_st` (los 26 nodos de hoy más `Comentario`), `apolo.plc.tipos`
(`FB_ESTANDAR`, `ELEMENTALES`, `CONVERSIONES`, `FUNCIONES_ESTANDAR`, `DEFECTO`, `RANGO`) y
`apolo.plc.direcciones` (`parsear`, `Direccion`, `ESCALA_AI`). Todos los nombres del plan existían
con ese nombre: ninguno se cambió. `CONTRATO_EXTENSIONES` sigue en 1.

**D2.** `tokenizar(fuente, comentarios=None)`: con una lista le agrega
`Comentario(texto, linea, col, linea_fin, estilo)` en el orden de la fuente; `parsear` siempre los
junta en `Unidad.comentarios` (vacío por defecto). Decisiones propias (para vetar): `texto` es lo
de ADENTRO, sin delimitadores (crudo, con sus espacios y saltos), y en `//` sin el `\r` de un fin
de línea de Windows; `estilo` es el delimitador que abre (`(*`, `/*`, `//`), así quien imprime lo
re-emite tal cual; un comentario sin cerrar no se junta y da el error de siempre (línea, columna,
«falta «*)»»). Los tokens son los mismos juntando o no (todos los programas literales de
`test_plc_*`, el banco y el sintético) y el `Compilado` también (`test_plc_comentarios.py` compila
el mismo corpus juntando y sin juntar).

**D3.** `electrico.direcciones` lo valida `library/electrico/ficha_direcciones.py` (85 líneas);
`ficha.py` (424) sólo lo engancha y `ficha_payload` lo publica. Decisiones propias (para vetar):
- **E/S de una ref = los bornes que el ST alcanza por dirección** (`I<byte>.<bit>`,
  `Q<byte>.<bit>`, `AI<n>`, `AQ<n>`: la correspondencia de V8.3 D4). Así «cubre TODAS las E/S» se
  verifica sin leer `modelo`; una ref sin ninguna rechaza el bloque y no puede nombrarlo en
  `a_confirmar`. Si un aparato con otros nombres de E/S (un variador con `DI1`) quiere
  direcciones, se amplía ahí.
- **`a_confirmar` puede nombrar `direcciones`** por un keyword nuevo de
  `ficha_datos.parse_datos(extra_a_confirmar=…)` (con default; `parse_datos` no está en
  `MODULOS`); con mapa y en `a_confirmar` a la vez es error (lo que se confirma va SIN valor).
- **Una sola `fuente` por ficha**, como hoy: la del PLC queda «T_max_C: …; direcciones: …».

**El PLC del catálogo.** Direcciones de fábrica de la CPU 1214C DC/DC/DC leídas (≈ 10 min) en el
manual de sistema «S7-1200 Programmable controller» V20 (Siemens, 11/2024, edición en línea en
docs.tia.siemens.cloud, sin números de página), § Data storage, memory areas, I/O and addressing ›
Addressing the local and expansion I/O: su figura 1 (la vista de dispositivo de una CPU 1214C) da
DI14/DQ10 en las direcciones I 0…1 y Q 0…1 y AI2 en I 64…67; el texto de la misma sección dice
que las digitales van de a 8 puntos por byte y que cada analógica ocupa 2 bytes → `%I0.0`…`%I1.5`,
`%Q0.0`…`%Q1.1`, `%IW64` y `%IW66`; el «%» delante, de § Using absolute addressing to access CPU
data. Citado en la `fuente` de la ref; nada a confirmar. El PDF del manual no se pudo leer (pasa
de 10 MB): se leyó la edición en línea.

**Vigencia (D14), medida.** `COSIM_EPOCH` sigue en 5: sólo la huella de `test_cosim_epoch.py`
(`969969f993739c1e` → `2228ab30576e23a1`: lexer, parser y árbol están en `plc/**`). Contra
`833ce8e` (exportado limpio con `git archive`): 154 programas (los que compilan los `test_plc_*`,
capturados al correrlos, más el del banco y el sintético) dan el MISMO `fuente_py`,
`mapa_lineas`, `tags`, `programas`, `rutas`, `entradas`, `salidas`, `pous_py` y disposiciones (o
el mismo error); 6 escenarios del banco dan la MISMA huella (marcha y seta por variador
`91332d0a…`, seta en directo `79e6df72…`, caída de red `739e1c05…`, corte de fase `359435ee…`,
cajas con seta `175c33b4…`, atasco `2271fefb…`) y las firmas de los 4 tableros de
`tests/tablero_electrico.py` son idénticas (directo `2:7feece8f…`, variador+PLC `2:35a1fea0…`,
cat. 3 `2:5a114e45…`, relé de seguridad `2:da2c40a9…`); un test lo vigila quitando las
direcciones de todas las fichas. Sin bump de `GEOM_CACHE_EPOCH` ni de versiones de comandos.

### F1b1 — PLC externo en el lote y ritmo de pared

**D4.** `cosim/puerto_plc.py` (puro): `PuertoPLC` (`Protocol` `runtime_checkable` con los 13
miembros; `isinstance(PLC(…), PuertoPLC)` es verdadero), `MIEMBROS`/`OPCIONALES`, `LazoCortado(motivo,
t_s=None)` (picklable; con hora dice «lazo cortado en t = … s: …»), `CONECTORES` y `DE_EXTENSION`
(«prefijo.x» → (extensión, versión)), `problemas_de_clase` y `cerrar`. `SUPERFICIE` suma
`PuertoPLC` y `LazoCortado`. `Corrida` arma el conector en vez de `PLC` sólo para las designaciones
de `snap.externos`; el resto del `__init__` y el intercambio no cambian. Decisión propia (para
vetar): los DATOS de la cara (`compilado`, `estado`, `salidas`, `falla`, `fallas`, `scans`) se piden
DECLARADOS en la clase (atributo, propiedad o anotación), así se validan al cargar sin conectar.

**D5.** `Extension.conectores_plc` (valor o función perezosa) lo valida
`extensiones_puntos.sumar_conectores_plc`: prefijo, los 13 miembros, `validar_config` llamable,
opcionales llamables, sin pisar uno existente; `CONECTORES` y `DE_EXTENSION` entran a
`_registros()` (el rechazo deshace todo, también el modelo que entró antes) y `GET
/api/extensiones` lista `conectores_plc`. `CONTRATO_EXTENSIONES` sigue en 1.

**D6.** `POST /api/cosim/run` acepta `plc_externo` (tipo libre en el modelo: la forma la valida el
servicio con 400 y no FastAPI con 422). `services/cosim_externo.leer` corre dentro de
`snapshot_cosim`, justo después de juntar los programas y ANTES de las aserciones y la dinámica:
es un PLC del tablero, tiene programa (carril o encima), el conector está cargado y su
`validar_config` no se queja; todos los problemas juntos. `CosimSnapshot.externos` va vacío sin
externo. Sin tope de 1 KB en el POST (decisión para vetar: el tope del plan es de la query del WS,
F1b2; una config con mapa de etiquetas lo pasaría).

**D7.** El planificador suma `resumen.determinista: false`, `lazo` (`intercambios`, `atrasados`,
`atraso_max_ms`, `rebases` y `ida_y_vuelta` por designación: `n`, `mediana_ms`, `p99_ms`, `max_ms`,
medida por el núcleo envolviendo `paso()` en `externo.Medido`) y un aviso al frente de `avisos`;
la API suma `plc_externo` ({conector, extension, version}) y un veredicto nulo con
`veredicto_motivo`. Decisiones propias (para vetar): con externo las aserciones NO se evalúan
(`aserciones: []`: una fila «pasa/falla» sería un veredicto de hecho) y un escenario con nombre
devuelve `guardado: false` con el motivo, sin `_verificar_documento` (no escribe).

**D8 y D9 en el lote.** `cosim/ritmo.py`: `RitmoPared(dt, reloj, dormir, rebase_s)` duerme en
tajadas de ≤ 10 ms mientras falte más de 1,5 ms y espera en activo el resto; un atrasado no espera
y los que siguen se ponen al día; una deuda > `REBASE_S` = 100 ms (criterio: 50 intercambios de
2 ms; para vetar) corre t₀. `cosim/externo.correr_a_la_pared` es el bucle del lote con externo:
`LazoCortado` sale con la hora del intercambio y los conectores se cierran siempre; conectar mal
(cualquier excepción del conector) es «no se pudo conectar el PLC externo -K1: …» y la corrida no
arranca. El worker lo devuelve en un frame nuevo `L` y `proceso.LazoCortadoError` (subclase de
`CosimError`) es **502** en la API (decisión para vetar: no es una falla del núcleo).

**D15 del lote.** `tests/ext_prueba/`: `conector_plc.ConectorTCP` (`prueba.tcp`; un pedido por
miembro que cambia el PLC; `paso` lleva las entradas y trae salidas, estado, falla, scans y
variables, UNA ida y vuelta), `red_plc.py` (la «red», importada al conectar: un test lo vigila en
un proceso aparte), `plc_falso.py` (`apolo.plc.PLC` con reloj de pared tras un servidor TCP; sale
al cerrarse su stdin) y cinco variantes que no cargan. `tests/test_cosim_plc_externo.py` (16
casos) cubre todo lo de «Se verifica»; el gate de imports del worker suma `externo.py`,
`puerto_plc.py` y `ritmo.py`.

**Lazo medido** (laptop, worker real, PLC falso en otro proceso, 3 s = 1501 intercambios de 2 ms,
tres corridas): ida y vuelta de `paso()` mediana 0,20–0,24 ms, p99 0,39–0,62 ms, máx. 0,95–2,3 ms;
5–17 atrasados con atraso máximo 3,2–4,1 ms, 0 rebases, factor de tiempo real 1,0; el PLC de afuera
enclavó la marcha y el motor llegó a 1800 rpm; `modulos_pesados` vacío. Con este programa (ciclo de
10 ms, pulsación de 0,2 s) las tres huellas salieron iguales: la corrida se DECLARA no determinista
(D7) por construcción, no porque cada corrida difiera.

**Vigencia (D14), medida.** `COSIM_EPOCH` sigue en 6: sólo la huella de `test_cosim_epoch.py`
(`0da6c7ab1e440113` → `d0326bbc9bff2491`). Contra `4f669f0`, 6 escenarios del banco dan la MISMA
huella (marcha y seta por variador `6217c74d…`, seta en directo `82649515…`, caída de red
`7d30cac0…`, corte de fase `057ccaee…`, cajas con seta `aafe1f53…`, atasco `622a61f2…`) y las MISMAS
claves del resultado, de su `resumen`, del compacto y de su `resumen`. Sin bump de
`GEOM_CACHE_EPOCH` ni de versiones de comandos; ninguna tool MCP nueva (el golden no cambia).

### F1c1 — Escribir una variable

**La tabla y la regla.** `plc/simbolos.py` (217 líneas; `compilador.py` sólo engancha: 476):
`tabla` arma `Compilado.simbolos` = {ruta: (tipo, escribible)} con las MISMAS rutas que
`PLC.variables()` (la global en minúsculas, `Main.x` con el nombre del PROGRAM), más cada
instancia de bloque y sus miembros (`Main.a1`, `Main.a1.t.q`), nunca escribibles; un ARRAY entra
con su tipo (`ARRAY[1..3] OF DINT`) y se escribe por elemento. `ambito_de` es la resolución de
`leer` (sacada de `runtime.py`, que la usa igual) y `escritura(compilado, ruta, valor)` la regla
única: `KeyError` si la ruta no existe (con «¿quisiste decir…?») o el índice no va; `ValueError`
con su motivo para CONSTANT, AT de entrada («su valor lo da el borne») y de salida («la maneja el
programa»), una dirección `%…`, un bloque o su miembro, un ARRAY sin índice y un valor de otro
tipo. `PLC.escribir` la aplica a la memoria (entra antes del próximo scan y el programa la pisa)
y, sin tensión, rechaza. La agenda la corre ANTES de pasarle la escritura a un PLC de afuera, que
la recibe ya en su tipo.

**La acción.** `{"accion": "escribir", "dispositivo", "variable", "valor"}` en el escenario y en
vivo (`Accion.variable`, también la forma corta `{"escribir": "-K1", …}`); la `Agenda` recibe
`plcs` (los de la `Corrida`); `agenda.validar` corre sobre `plcs_de_prueba` (un PLC desechable por
programa, el mismo con un externo) y el snapshot da 400 al declarar. Se graba con su hora
(`variable` antes de `valor`) y la grabación vuelta escenario da la misma huella
(`tests/test_cosim_escribir.py`, 22 casos; `tests/test_plc_escribir.py`, 46).

**Decisiones propias (para vetar):**
- **Sin tensión no se atiende**: un PLC apagado no contesta la red. En el lote queda en `eventos`
  como `{"rechazo": "escribir", …, "motivo"}` SIN `accion` (no es ancla de una aserción) y la
  corrida sigue; en vivo, rechazo de esa acción. En STOP sí se atiende (la memoria responde).
- **`escribir` en t = 0 es 400**: el PLC arranca en el primer intercambio (la agenda se aplica
  antes), así que siempre se perdería; el texto pide t > 0.
- **Valores**: un entero escrito como `50.0` vale en INT/DINT/TIME (un SCADA manda REAL); `true`
  en un numérico no; en BOOL sólo `true`/`false`, `0`/`1` (no `1.0`).
- **`leer("g[2]")`** de un ARRAY GLOBAL ahora resuelve (antes, «no existe»): la misma resolución
  sirve a los dos. Ningún resultado del banco lo usa (las trazas salen de `variables()`).
- La extensión falsa NO suma `escribir` a su conector: el rechazo de un externo sin `escribir` se
  prueba con `ConectorTCP` en el snapshot (sin conectar) y el camino con `escribir`, con un puerto
  falso en la agenda (llega validado y en su tipo).

**Lo que se verificó.** `simbolos` con globales, PROGRAM, FB estándar y del usuario, ARRAY,
CONSTANT y AT; cada rechazo con su motivo y la memoria intacta tras él; el golden: la ÚNICA línea
que cambia es la descripción de `set_scenario`; `test_plc_rendimiento` (torture) verde.
`Compilado.simbolos` no se persiste: ni en las entradas del `.apolo` (`add_program` en un tablero),
ni en el blob de `geomcache.pack`, ni en la SQLite tras `ProjectStore.create` + `load` (un test).

**Vigencia (D14), medida.** `COSIM_EPOCH` sigue en 6: sólo la huella de `test_cosim_epoch.py`
(`d0326bbc9bff2491` → `5343e02e81995d98`). Contra `fc734ea` (exportado con `git archive`), 6
escenarios del banco dan la MISMA huella, claves del resultado y del `resumen` y `eventos` (marcha
y seta por variador `79ea55d0…`, seta en directo `56560dfe…`, caída de red `e7f23f08…`, corte de
fase `e03b5efc…`, cajas con seta `2446792f…`, atasco `790b11bd…`). Sin bump de `GEOM_CACHE_EPOCH`
ni de versiones de comandos; ninguna tool MCP nueva.

### F1b2 — PLC externo en la sesión viva

**D6 en el WS.** `?plc_externo=` lo lee `services/cosim_externo.de_query` DENTRO de `_preparar`
(tras la guardia del token, antes del snapshot): JSON ≤ 1024 bytes con un objeto y sin `ritmo` ≠ 1
(también `ritmo=0`), o 4400 con clave `plc_externo`; lo demás (PLC del tablero, programa,
conector cargado, `validar_config`) lo valida `leer` en el snapshot, como en el lote (4400 clave
`escenario`, con el texto del 400). El `inicio` suma `plc_externo` ({conector, extension,
version}) y `determinista: false`. Un PLC que no conecta (el frame `L` del worker) es
`{"tipo": "error", "codigo": "lazo"}`, `fin` con motivo «lazo» y cierre **4502** (decisión para
vetar: el 502 del lote, en código de WS).

**D9 y D8 en vivo.** `cosim/vivo_lazo.py` (85 líneas; `worker_vivo.py` sólo lo engancha: 203):
con `externos` el paso 2 de la ventana avanza UN intercambio por vez con `RitmoPared` y el 4 no
duerme (ya esperó el ritmo); el fotograma sale cada 1/30 s virtual. `LazoCortado` de cualquier
miembro (y cualquier excepción de `pausar`/`reanudar`/`reconectar`, envuelta) pausa con `{"tipo":
"pausa", "id", "motivo": "lazo", "t", "mensaje"}`; `reanudar` llama a `reconectar()` y, si corta
otra vez, la misma pausa con el `id` del reanudar; la pausa manual llama a `pausar()`/`reanudar()`
del conector. El `fin` suma `determinista: false`, `lazo` (el de `externo.lazo`) y, si hubo pausa,
`aviso_externo` («siguió corriendo con su propio reloj»). `correr_vivo` cierra los conectores
siempre (`Corrida.cerrar` en un `finally`). Decisiones propias (para vetar):
- **El intercambio cortado SIGUE desde el PLC que cortó** (corrección de la revisión: repetirlo
  entero integraba el tablero dos veces —temporizadores, térmicos y relés de tiempo 2 ms de más
  por corte—). `Corrida.intercambio` guarda `_reanudar = (k, índice del PLC)` al ver un
  `LazoCortado` en la etapa de los PLC y, llamado otra vez con el MISMO k, salta agenda, lectura
  de MuJoCo y `tablero.paso` y los PLC ya hechos; un corte en la agenda (un `escribir`) no deja
  marca: la agenda sigue desde su índice. Sin externo el `try` nunca salta (la huella del banco,
  igual). `test_cosim_vivo.py`: una sesión con un PLC de afuera determinista (el virtual detrás
  de la cara) que corta dos veces y reanuda da la MISMA huella que sin cortes.
- **Una acción inyectada que corta el lazo** (un `escribir` cuyo conector lanza) responde rechazo
  «el lazo con el PLC externo se cortó al aplicarla» y re-lanza (`agenda._aplicar_inyectada`): sin
  eso quedaba sin respuesta.
- **La ida y vuelta en vivo guarda los últimos 30 000 intercambios** (60 s, `IDAS_MAX`): una sesión
  de 30 min entera serían ~30 MB.
- Las acciones se siguen leyendo una vez por ventana (≤ 33 ms de espera), como sin externo.
- `abrirSesion(…, {plcExterno})` de la UI NO entra: el plan lo pone en D13 c (F1d2).

**D15 en vivo.** `ConectorTCP` suma `pausar`/`reanudar` (el PLC falso imprime `OP pausar` /
`OP reanudar`) y `reconectar` (abre de nuevo al mismo PLC); `plc_falso.py` acepta `--puerto` (el
PLC «vuelve» al puerto del que se lo mató). El lanzador del PLC falso pasó de
`test_cosim_plc_externo.py` a `tests/lazo_externo.py` (lo usan el lote y el vivo).
`test_cosim_vivo_ws.py` suma 8 casos: un intercambio por vez (`lazo.intercambios ==
intercambios == 500` en 1 s virtual), 28–31 fotogramas separados 1/30 s ± Δt y a ritmo de pared;
`ritmo=2`, `ritmo=0`, JSON roto, más de 1 KB y un conector no cargado son 4400 sin llegar al
worker; un PLC que no contesta es 4502; matar el PLC falso pausa con «lazo cortado en t = …»,
reanudar sin él vuelve a pausar en la MISMA t, con el PLC de vuelta en el mismo puerto sigue desde
ahí, la pausa manual llega al PLC falso y el `fin` trae `aviso_externo`; ni el worker ni los PLC
falsos quedan vivos. El gate de imports del worker suma `vivo_lazo.py`.

**Vigencia (D14), medida.** `COSIM_EPOCH` sigue en 6: sólo la huella de `test_cosim_epoch.py`
(`5343e02e81995d98` → `cc635ede096a7399`, ya con la corrección del intercambio). Contra `489af7d` (exportado con `git archive`), 6
escenarios del banco dan la MISMA huella, claves del resultado y del `resumen` y `eventos` (marcha
y seta por variador `98728ceb…`, seta en directo `56560dfe…`, caída de red `7d30cac0…`, corte de
fase `9d2321b3…`, cajas con seta `20d75121…`, atasco `c871063f…`) y una sesión viva sin externo
cerrada como lote, la misma huella y grabación (`20d75121…`); `test_cosim_vivo.py` (determinismo)
intacto. Sin bump de `GEOM_CACHE_EPOCH` ni de versiones de comandos; ninguna tool MCP nueva.

### F1d1 — Panel de operador, puertos y cable

**El panel.** `HMI-7IN-24VDC` en `maniobra_control` (P, puerta, `L+`/`M`/`PE`, carga 24 VDC,
`cotas_verificadas: false`, `cost` 380 referencial) con línea de referencia «orden de Weintek
cMT2078X» (el MT8071iE, primer candidato, está discontinuado). Cifras leídas (≈ 15 min) en su hoja
de datos `cMT2078X_Datasheet_ENG_20240514` (copia del distribuidor Damen CNC): 800 × 480,
24 VDC ± 20 % (→ `U_min_V` 19,2), 820 mA (→ `perdidas_W` 19,7, cota superior), frente
200,3 × 146,3 × 35, recorte 192 × 138, del plano 7,4 mm delante, 27,6 detrás y cuerpo
189,6 × 135,6, 0…55 °C (`T_max_C` 55) y LAN 1/LAN 2 10/100 Base-T. Nada a confirmar. Ocupa
⌈200,3/70⌉ × ⌈146,3/80⌉ = 3 × 2 celdas.

**Puertos.** `electrico.puertos: [{id, tipo}]` lo valida `library/electrico/ficha_puertos.py`
(`ficha.py` sólo engancha y `ficha_payload` lo publica): lista no vacía, claves `id`/`tipo`, id sin
espacios ni «:», único y distinto de todo borne, `tipo` en `TIPOS` (`rj45`) y `fuente` obligatoria.
El carril no los copia (`Dispositivo.puertos` es el del aire). El panel trae `LAN1`/`LAN2`; el PLC
gana `PN1`, leído en la hoja de datos 6ES7214-1AG40-0XB0 (Siemens, 18/02/2022, § «1. Interface»:
PROFINET, «RJ 45 (Ethernet) Yes», «Number of ports 1»). Los variadores, ninguno.

**Colocación y armado.** `colocacion_puerta.bloque(a, reglas)` = ⌈ancho/paso⌉ × ⌈alto/paso⌉; un
bloque se centra en sus celdas contiguas y lo de varias celdas va PRIMERO (arriba, lejos de la
bisagra); lo de una celda recorre las mismas celdas en el mismo orden que antes. El hueco sale de
`tablero.puerta.recorte_mm` (`ficha_tablero.py`, menor que el frente y no menor que el cuerpo):
`commands/tablero_geom.huecos_por_ref` da `("rect", ancho, alto)` y `armado.py` lo centra en la
caja del aparato. Holgura de detrás y recorrido de la puerta, como cualquier mando
(`tests/test_panel_operador.py`, 33 casos: verde, rojo con «faltan 21 mm de fondo» y el poste que
el recorrido ve chocar con el marco a 0°).

**Decisiones propias (para vetar):**
- **Builder `panel_puerta`** (`library/builders_tablero.py`, archivo fuera de la lista de la fase):
  con la caja entera el cuerpo atravesaba la chapa por un recorte menor y la interferencia del
  tablero dejaba de ser cero; el marco va delante y el cuerpo de la ficha pasa el recorte con
  1,2 mm por lado. Ref nueva: sin bump de `GEOM_CACHE_EPOCH`.
- **«Lo de varias celdas primero» es general**, no del tipo `hmi`: cualquier aparato de puerta más
  grande que una celda (antes, error «dale una `posicion`») toma su bloque antes que los demás.
- **`cosim/tablero.py` suma `SOLO_ALIMENTACION`** (fuera de la lista de la fase): sin rama, un
  modelo que no es de ninguna familia nunca avanza; la regla quedó en `cosim/CLAUDE.md`.
- **La resolución va en `modelo` como `ancho_px`/`alto_px`**: `[800, 480]` lo rechaza la ficha
  como rango [mín, máx] al revés. El modelo la publica como `pantalla_px` (y la UI la tipa en
  `DispositivoVivo`).
- **El consumo no carga la red de mando**, como la alimentación del PLC (`modo: ninguna`, hipótesis
  declarada).

**El cable de red, medido.** `CABLE-RJ45-CAT6` (orden de LAPP ETHERLINE LAN Cat.6 U/UTP
4x2xAWG24, art. 2170955, ficha en línea: Ø 6 mm, 48 V rms, 60 kg/km; 0,205 mm² de la tabla AWG)
entra por `add_cable` tal cual: el enum de `add_cable` pide hilos, así que la ficha declara los 8
pines del RJ45 SIN color (los bicolores de TIA-568 no son un código de IEC 60757) y nadie los
cablea con `add_wire`. Con `largo_m` la BOM lo compra por metro; el ERC no da ninguna fila del
panel ni del cable. Sin ampliar ningún comando. Queda como pendiente que el carril no sabe que
`-W3` une dos PUERTOS (el `desde`/`hasta` son dispositivos): eso es del plan de la red de datos,
fuera de este (§ Lo que este plan NO hace).

**Vigencia (D14), medida.** `COSIM_EPOCH` sigue en 6: sólo la huella de `test_cosim_epoch.py`
(`5343e02e81995d98` → `9584749c555b2d38`: `modelos/hmi.py`, el registro y el gancho del tablero).
Contra `489af7d` (exportado con `git archive`), 6 escenarios del banco dan la MISMA huella y las
mismas claves del resultado y del `resumen` (marcha y seta por variador `6217c74d…`, seta en
directo `82649515…`, caída de red `eb62a184…`, corte de fase `057ccaee…`, cajas con seta
`c67fb25d…`, atasco `9cd125aa…`), y los 4 tableros de `tests/tablero_electrico.py` armados con
`layout_tablero` dan IDÉNTICOS gabinete, aparatos (zona, posición, caja, fila), huecos, cajas de
todas las piezas, ids de la escena y firma del documento (directo `2:c5a76b7b…`, variador+PLC
`2:33401c66…`, cat. 3 `2:1c73aef9…`, relé de seguridad `2:89ea81ea…`; el PLC ya con su `PN1`).
`test_contrato_comandos` no pidió nada (la colocación no está en la huella de
`_exec_layout_tablero`): sin versión de `layout_tablero`, sin `GEOM_CACHE_EPOCH`, ninguna tool MCP
nueva (el golden no cambia). Catálogo 448 → 450.

### F1c2 — Bus de la sesión viva

**D11.** `api/vivo_bus.py` (245 líneas, hoja: sólo stdlib; `common` lo re-exporta a
`cosim_vivo`, `CAPAS_API` lo suma): `suscribir(nombre, max_fotogramas=60) -> Suscripcion` y
`enviar_vivo(nombre, msg) -> bool`, con `Suscripcion` en `SUPERFICIE` (`CONTRATO_EXTENSIONES`
sigue en 1). La copia vive en `SesionViva._poner` (en el loop): ahí se arma ahora lo que ve el
cliente —la tabla vuelta `inicio`, el `fin` con lo de volverla escenario, los errores `E`/`L` y el
`fin` del worker muerto— y se pone, en el mismo orden, en la cola de la persona y en cada
suscripción; `reenviar` sólo manda. Así la suscripción recibe lo mismo que el WS aunque la persona
vaya lenta (su descarte no le llega). `validar_texto` es la validación ÚNICA del WS y del bus.
`cosim_vivo.py` queda en 428 líneas. Decisiones propias (para vetar):
- **La suscripción vive más que la sesión**: sigue la abierta y las que vengan hasta `cerrar()`
  (una pantalla se suscribe una vez y espera el `inicio`); un nombre suscrito dos veces es
  `ValueError` (los acks irían a una sola) y lleva el prefijo de la extensión («prueba.scada», sin
  «:»: el `:` separa el prefijo del id).
- **La cola es una `deque` con su `Condition`, no una `queue.Queue`**: descartar el fotograma más
  VIEJO sin perder el orden con el JSON lo pide. Fotogramas: pasados `max_fotogramas` sale el más
  viejo (`descartados`; 0 = sólo JSON). JSON: pasados `MAX_JSON` = 1000 se descarta el nuevo
  (`json_descartados`), NUNCA `inicio`, `senales` ni `fin` (sin ellos los fotogramas no se leen ni
  se sabe que terminó). `recibir(timeout)` da un dict propio (el texto se parsea en el hilo del
  lector, no en el loop) o los `bytes` del fotograma.
- **La suscripción ve también los acks de la persona** (lo mismo que el WS: un SCADA sabe qué se
  pulsó); los de una acción del bus van SÓLO a su suscripción, ni a la persona ni a otra. El ruteo
  es por ids EN VUELO (`<nombre>:<id>`, sin `id` uno correlativo), no por el prefijo solo: un ack
  de una suscripción ya cerrada no se filtra a la persona. El ack lleva el id con prefijo.
- **Lo que no pasa** (control, > 4096, no JSON, no objeto) es `False` y su rechazo va a la
  suscripción, sin llegar al worker; sin sesión abierta, `False` sin rechazo.
- **El `fin` de una sesión que cerró la persona ahora también se procesa** (antes la tarea que
  enviaba ya estaba cancelada): la suscripción se entera de que terminó y la sesión queda en
  `SESIONES_GRABADAS` como cualquier otra.

**D15.** `tests/ext_prueba/suscriptor.py`: `SuscriptorPrueba` («prueba.scada») sigue la sesión
desde su hilo sólo con `apolo.extensiones_api` y escribe con `enviar_vivo`.
`tests/test_vivo_bus.py` (8 casos): el nombre; orden y descarte del fotograma viejo; el JSON de más
sin perder `inicio`/`senales`/`fin`; la validación del WS; cada rechazo sin llegar a la sesión; el
ack sólo a su suscripción; `STATE_LOCK` parchado para fallar y el AST de imports; y de punta a
punta con el worker: el suscriptor recibe la MISMA secuencia que el WS (50 mensajes, 45
fotogramas), uno que nunca lee descarta y cuenta (`descartados` = fotogramas del WS − 5) mientras
el WS recibe todos, `enviar_vivo` con `STATE_LOCK` tomado por otro hilo aplica el `pulsar`, su ack
no llega al WS, la grabación trae `girar` (persona) y `pulsar` (bus) sin ids, un `parar` del bus se
rechaza y con la sesión cerrada `enviar_vivo` es `False`.

**Vigencia (D14).** Nada de `cosim/` ni `plc/`: la huella de `test_cosim_epoch.py` no cambia;
`COSIM_EPOCH`, `GEOM_CACHE_EPOCH` y versiones de comandos igual; ninguna tool MCP nueva.

### F1d2 — Puntos de UI

**D13 a.** `Extension.chipsVivo: [{id, Componente}]` lo pinta `vivo/ChipsVivo.tsx` en `BarraVivo`
justo tras la fase y el factor (antes del aire), cada uno en un `<span class="bv-chip">` con su
límite de errores (un chip que revienta se quita y la barra sigue). Sin chips, `ChipsVivo` no
pinta nada: la barra se comparó contra la de `752a663` (el `BarraVivo.tsx` de ese commit
renderizado en el mismo test) en corriendo, pausa, fin y cerrada, byte por byte igual;
`vivo/chips.test.ts` lo deja vigilado (sin chips = sin extensiones; con un chip, quitar su `span`
devuelve la barra de antes y va tras `bv-factor`). `BarraVivo` toma `extensiones` opcional (por
defecto `EXTENSIONES`) para eso y para el muestrario.

**D13 b.** `Extension.pantallas3d: [{id, tipo, dibujar(ctx, vivo), tocar?(x, y, vivo)}]` lo instala
`vivo/pantallas3d.ts` desde `reproductorVivo.ts`: por cada dispositivo del `inicio` con ese `tipo`
y pieza en el 3D, un plano con `CanvasTexture` (`MeshBasicMaterial`, sin tonemapeo) en `ctx.group`
(`raycast` no-op), que sigue a su pieza en cada cuadro (`matrixWorld`: también si la puerta gira),
se repinta cada 100 ms y se libera al restaurar. La resolución es `pantalla_px` del dispositivo
(F1d1); el plano tiene su proporción dentro del 82 % de la cara (el vidrio dentro del marco). El
toque usa la MISMA captura que los mandos: `mandos3d.ts` exporta ahora `capturarToques(contenedor,
alApretar, alSoltar?)` y los mandos la usan (mismo comportamiento); el plano cuenta si el rayo lo
toca antes que cualquier pieza visible, uv → px y `tocar`; sin `tocar`, el clic pasa al visor.
Lo puro, en `vivo/pantallas.ts`: `caraFrontal`, `matrizDeCara`, `rectanguloPantalla`, `uvAPx`,
`pantallasDeLaSesion` y `temaDe`. Decisiones propias (para vetar):
- **La cara frontal sale de la GEOMETRÍA, sin convención de ejes**: entre las caras planas
  extremas de la pieza (triángulos agrupados por normal, el plano más afuera en ese sentido), la de
  más área. El panel de 7″ tiene el marco (200,3 × 146,3) delante y el cuerpo menor detrás, así
  que gana el frente con cualquier giro, con matriz de instancia o con la malla ya en el mundo. Si
  empatan (una placa lisa) gana la que mira más a −Y del mundo (la vista «frente», la puerta de un
  tablero sin girar). `v` es el eje de la cara que más sube en el mundo (cara horizontal: el que
  más va a +Y) y `u = v × n`: la pantalla nunca sale espejada ni de costado. No hizo falta backend.
- **`vivo` lo arma quien instala** (`VivoPantalla`: dispositivo, `inicio`, ancho y alto en px, `t`,
  `valor`, `texto`, `enviar`, `tema`, `movimientoReducido`): la extensión pinta sólo con los tokens
  del tema que le llegan (`--bg`, `--panel`, `--text`, `--muted`, `--accent`, `--border` y la letra
  del `body`, leídos una vez) y sabe de `prefers-reduced-motion`; el muestrario le pasa una sesión
  de ejemplo. Una pantalla que lanza al pintar se avisa una vez y deja de pintarse.
- **Dos pantallas para el mismo `tipo` se rechazan al cargar** (pintarían el mismo plano), como
  un id repetido.

**D13 c.** `ui/src/extensiones/vivo.ts`: `useFaseVivo`, `useValorVivo(señal)` (no estaba en la
lista: un chip necesita re-pintar con la señal; ≤ 10 Hz como el panel), `valorVivo`, `inicioVivo`
(lee `useVivo.inicio`, que la sesión pone al llegar el `inicio`), `enviarVivo(mensaje) -> boolean`
y `abrirSesionViva(escenario, {plcExterno})`, más los tipos. `abrirSesion(…, {plcExterno})` manda
`?plc_externo=` en JSON (lo valida el servidor: ≤ 1 KB, conector, programa) y reiniciar lo vuelve a
pedir; `urlSesion` quedó exportada y pura (recibe `location`). `enviarVivo` pasa por
`protocolo.problemaDeMensaje` (objeto con `accion` o `evento`, uno solo; nunca `control` ni `id`
propio; ≤ 4096 bytes), lleva id `x<n>` y su rechazo llega como el de cualquier acción. El `inicio`
tipa `plc_externo` y `determinista`; el cierre **4502** y el `fin` con motivo `lazo` tienen texto
para la persona (sin eso, abrir con un PLC que no contesta decía «se perdió la conexión»). La pausa
con `motivo: "lazo"` (D8) la dice la barra: «En pausa · se cortó el enlace con el PLC», qué hacer
(«reanuda para reintentar»: `reanudar` llama a `reconectar()`) y el `mensaje` del núcleo en
«Detalle técnico»; el botón dice «Reanudar y reintentar el enlace». `useVivo.pausa` la guarda y
`reanudar` la limpia; `barra.avisoPausa` es puro. La pausa manual dice lo de siempre (vitest en
`barra.test.ts` y `chips.test.ts`).

**Registro.** `extensiones/puntosVivo.ts` valida (lo llama `registro.ts`, todo junto en un
mensaje): listas, id con el prefijo de la extensión, componente del chip, `tipo` en minúsculas,
`dibujar` función, `tocar` función si viene; entre extensiones, ids repetidos y un tipo con dos
pantallas. Todo campo nuevo es opcional; `registro.test.ts` suma 5 casos.

**Muestrario.** La extensión de prueba (`extensionPrueba.tsx`) suma el chip «Consigna 50 %» (lee
`-K1.Main.consigna` con la API viva) y una pantalla `hmi` que pinta la consigna con «−10» y «+10»;
tocar manda `{accion: "escribir", dispositivo: "-K1", variable: "Main.consigna", valor}`.
`PantallaDemo.tsx` la instala con `instalarPantallas3D` sobre un panel con la forma de
`panel_puerta` en la puerta de un tablero girado 25° (`?giro=`); la sesión de ejemplo aplica el
`escribir` y el chip de la barra lo ve. Verificado en el navegador: el plano sobre el frente del
panel, derecho, y tocar «+10» lleva la pantalla y el chip a 60 % sin seleccionar ni girar la
cámara. Capturas en `C:\t\lazo-f1d2\` (fuera del repo).

**Lo que se verificó.** `npm test` 567 (con la pausa del lazo) (antes 542: `pantallas.test.ts` 15 —la cara del panel
suelto, en la puerta con el tablero a 0°, 25°, 90°, 180° y −137°, la malla ya en el mundo e
inclinada, la placa lisa, una cara horizontal, la matriz del plano, el rectángulo, uv → px, qué
dispositivo lleva pantalla, el tema, el toque y el pintado de la pantalla de prueba, los mensajes y
la query `plc_externo`—, `chips.test.ts` 3 y `registro.test.ts` +5), `npm run build` y los
trinquetes de texto, tuteo y tamaño (el archivo más largo tocado: `sesion.ts`, 319 líneas). Nada de
backend ni de Python: sin huella, epochs, versiones ni tools.
