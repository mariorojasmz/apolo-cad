---
estado: en curso
nota: contrato derivado de un plan aprobado por el titular el 2026-10-24 (A1–A9), medido sobre `833ce8e`; partido en siete fases F1a → F1b1 ∥ F1c1 → F1b2 ∥ F1d1 → F1c2 ∥ F1d2; F1a hecha (D1–D3, por revisar y mergear); sigue F1b1 ∥ F1c1
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
