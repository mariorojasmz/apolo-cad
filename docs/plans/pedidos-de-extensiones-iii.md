---
estado: en curso
nota: contrato de Claude con el aval del titular («procede según tu criterio»); medido sobre `b9d774f`; F1–F4 hechas en la rama `wip/pedidos-ext-iii` (sin mergear; suite completa exit 0, COSIM_EPOCH 7); falta la revisión y el merge, y que la extensión adopte `preparar_corrida`/`correr_corrida` y re-mida sus casos de STO (su categoría 4 pasa a verde)
descripcion: una extensión corre un escenario de la co-simulación por la API declarada; el variador detecta la discrepancia entre los dos canales del STO y queda en falla; el banco de la co-simulación se carga desde fuera de la suite; un cilindro sin pieza pesa con su carrera y su vástago se mueve con la masa de su ficha
---

# Una extensión corre su escenario por la API y el variador nota el canal del STO pegado

## Estado y origen

Tercera tanda de pedidos que una extensión anotó en su bitácora mientras se implementaba (las
anteriores: [pedidos-de-extensiones](pedidos-de-extensiones.md) y
[pedidos-de-extensiones-ii](pedidos-de-extensiones-ii.md)), más los remates que quedaron abiertos en
la bitácora de [V8.9](V8.9-neumatica.md) § «Presostato y masa por carrera con ficha». La extensión
no toca el núcleo: anota y sigue con un parche de su lado (importa nombres sin declarar, pone un
alias en `sys.modules`, documenta un rojo esperado). Con el aval del titular para proceder según
criterio, el contrato lo escribe Claude y las decisiones quedan para vetar por número.

Los pedidos:

1. Correr un escenario de co-simulación desde una extensión por la API declarada. Hoy importa sin
   declarar `apolo.services.cosim_snapshot.snapshot_cosim`, `apolo.services.errors.ServiceError`
   y `apolo.cosim.proceso.correr_en_proceso` / `CosimError`.
2. Con un canal del STO pegado y el otro que abre, el variador real detecta la discrepancia y
   queda en falla hasta un reset. El modelo no la detecta: una función de categoría 4 sale en rojo.
3. `tests/cosim_lazo_banco.py` importa `tablero_electrico` por nombre: cargado desde fuera de la
   suite, la extensión necesitó un alias en `sys.modules`.
4. Remates: el docstring de `builders_mandos.py` cita la seta XB5AS8445 (que es 1 NA + 1 NC); y de
   V8.9, un cilindro sin pieza 3D pesa en carrera 0, el vástago se mueve con +14 % de masa y los
   subproductos de la lectura del SMC C96 siguen sin aplicar.

## Lo que hay hoy

- **La corrida de una extensión** (pedido 1): el patrón es «armar un escenario en memoria sobre la
  marcha del proyecto, tomar el snapshot bajo `STATE_LOCK` (con `leer_documento` de la fachada) y
  correrlo en el worker fuera de todo lock». La extensión lo hace en un módulo propio que llama
  `snapshot_cosim(doc, escenario)` (atrapa `ServiceError` y guarda su `detail` como el motivo del
  rechazo) y `correr_en_proceso(snap)` (atrapa `CosimError`). Ninguno de los cuatro nombres está en
  `apolo/extensiones_api.py`: un refactor del núcleo los puede mover sin aviso. El núcleo mismo
  hace lo mismo en `api/routers/cosim.py::_correr` (pasos a y b de D11 de V8.3).
- **El STO** (pedido 2): `cosim/modelos/variador.py:169-182` lee S1 y S2 con los umbrales de IEC
  61131-2; si cualquiera cae, corta el par tras `STO_reaccion_ms`. La falla `canal_sto_pegado`
  hace que un canal lea 24 V sin tenerlos y deja la hipótesis «el modelo del variador no detecta la
  discrepancia» (cosim-fallas D10: lo que el modelo no tiene no se inventa). Con la seta de dos NC
  o el relé de seguridad, un canal pegado se tolera (el otro corta) pero la marcha siguiente
  vuelve a arrancar con la falla puesta: nadie la detecta.
- **El dato del variador real**: el manual de funciones de seguridad de SINAMICS G120 (Siemens,
  «Safety Integrated — SINAMICS G110M, G120, G120C, G120D and SIMATIC ET 200pro FC-2», Function
  Manual 04/2018, FW V4.7 SP10, A5E34261271B AF; la línea de referencia CU240E-2 del catálogo)
  dice en § 5.10 que el inversor vigila que los dos canales de la entrada de seguridad tengan
  siempre el mismo estado, tolera una discrepancia breve hasta `p9650` («F-DI switchover
  discrepancy time», 500 ms de fábrica) y una discrepancia permanente es una falla del circuito; y
  en § 6.3.3 (caso 1, funciones básicas por bornes) que, vencido ese tiempo, señala la falla
  F01611/F30611 y deja la entrada en el estado seguro, sea cual sea la tensión, hasta que se la
  acusa con una señal segura (seleccionar y deseleccionar el STO: F-DI 1 → 0 → 1) o se corta y
  vuelve la alimentación; para volver a arrancar: quitar la discrepancia, acusarla, acusar el
  inversor (acuse estándar) y dar una orden de marcha nueva. El catálogo del Delta MS300 (la otra
  línea de la ref) no da el tiempo ni la reacción.
- **El banco** (pedido 3): `tests/cosim_lazo_banco.py:20` hace `from tablero_electrico import …`.
  Dentro de la suite `tests/` está en `sys.path`; una extensión que carga el banco por su ruta
  (`spec_from_file_location`) no lo tiene, y meter `tests/` del núcleo en su `sys.path` haría
  ambiguo `import conftest`.
- **El docstring** (pedido 4): `core/apolo/library/builders_mandos.py:29` «Cotas típicas de la línea
  Harmony XB5AS8445 + ZBY9140». El catálogo (`93_mandos.yaml`) ya cita XB5AS8442 (1 NC) y
  XB5AS8444 (2 NC).
- **Peso del cilindro sin pieza** (pedido 4): `library/bom_electrico.py::_fila` pesa un dispositivo
  sin pieza con `comp.weight` (el de carrera 0) y lo agrupa sólo por ref. El cilindro declara su
  carrera en `add_device.servicio.carrera_mm`.
- **La masa del vástago en la dinámica** (pedido 4): `physics/dinamica_cuerpos.masa_pieza` pesa el
  vástago (sin ref) por volumen × densidad (2,34 kg en el Ø63 × 800) y `services/cosim_aire.py::
  peticion` le suma como armadura la masa móvil en carrera 0 (0,43): 2,77 kg contra los 2,43 de la
  ficha (+14 %).
- **El C96** (pedido 4): la tabla «Basic» del catálogo SMC C96
  (https://content2.smcetech.com/pdf/C96.pdf, el PDF bajado el 2026-10-26, pág. PDF 8, leída con
  `pdftotext`) da, por Ø 32/40/50/63: A (= AM) 22/24/32/32, ØD (vástago)
  12/16/20/20, E 47/54/66/77, EE G1/8 · G1/4 · G1/4 · G3/8, KK M10×1,25 · M12×1,25 · M16×1,5 ·
  M16×1,5, L8 (= C) 94/105/106/121, R (= TG) 32,5/38/46,5/56,5, RT M6×1 · M6×1 · M8×1,25 ·
  M8×1,25 y WH 26/30/37/37; la pág. PDF 5, carrera máxima 1000 (Ø32) y 1900 (Ø40–63). Es la misma
  lectura que las notas de la bitácora de V8.9 dejaron como «subproductos sin aplicar».

## Decisiones (para vetar)

- **D1. La corrida es una API de DOS fases en `services`, declarada en `SUPERFICIE`.**
  `services/corrida_escenario.py`: `preparar_corrida(doc, escenario, *, programas=None)` bajo el
  `STATE_LOCK` del llamador (sólo EXTRAE: el snapshot) y `correr_corrida(preparada, *,
  timeout_s=None)` FUERA de todo lock (el worker; `COSIM_LOCK` los pone en fila con las demás
  corridas). Se re-exportan perezosos desde `extensiones_api` junto a sus errores. No se declaran
  los cuatro nombres de hoy: son el CÓMO (el snapshot, el error de transporte de `services`, el
  proceso), y declararlos congelaría tres módulos internos por un caso de uso. Dos fases y no una
  porque una sola función o corre el worker bajo el lock del llamador (rompe la regla de los dos
  locks: minutos con el documento bloqueado) o toma el lock ella misma (sólo sirve para el
  documento activo, y la extensión prepara varias corridas en UNA adquisición). Es el mismo corte
  que `entregable_documento` (extraer bajo el lock, componer fuera).
- **D2. El escenario es el nombre de uno guardado o el dict en memoria**, como `POST
  /api/cosim/run` (`escenarios.resolver`), con `programas=` opcional (los de `test_plc`). Lo que
  la API hace además (veredicto de las aserciones, guardar el resultado, vigencia, PLC de afuera)
  no entra: la extensión juzga con sus propias medidas y no guarda en el escenario.
- **D3. Errores propios de la API, con el texto del núcleo.** `EscenarioRechazado` (lo que el
  snapshot no toma: el `detail` exacto del `ServiceError` y su `status_code`) y `CorridaFallida` (el
  worker no devolvió resultado: el texto de `CosimError`), los dos `CorridaError` con `motivo`. Así
  la extensión no importa `ServiceError` ni `CosimError`, y el texto que pone en su informe es el
  mismo que hoy.
- **D4. El resultado es el JSON del worker tal cual** (trazas, eventos, final, hipótesis, resumen
  con la huella): lo que la extensión ya lee. Agregar nombres a `SUPERFICIE` no sube
  `CONTRATO_EXTENSIONES`.
- **D5. El variador detecta la discrepancia del STO con el comportamiento de la ficha leída**
  (SINAMICS G120, § Lo que hay hoy): S1 ≠ S2 durante `STO_discrepancia_ms` → falla
  `sto_discrepancia` (relé de falla, sin par); la marca de discrepancia se acusa sólo con los dos
  canales en el mismo estado y una selección y deselección del STO (los dos bajos y luego los dos
  altos) o con un corte de la red; recién entonces el rearme (DI o acción) borra la falla y hace
  falta una orden de marcha nueva. Con un canal pegado los dos canales nunca bajan juntos: la
  máquina no rearranca hasta reparar (o cortar la red), que es lo que la categoría 4 exige
  detectar.
- **D6. El tiempo es un AJUSTE de la ficha, con su fuente.** `STO_discrepancia_ms: 500` en el
  bloque de mando de `91_variadores.yaml` (el `p9650` de fábrica del manual de SINAMICS G120,
  citado en el comentario; el Delta MS300 no lo publica en su catálogo: dicho así), obligatorio
  cuando la ref tiene `STO` (como `STO_reaccion_ms`). La hipótesis «no detecta la discrepancia»
  se va; la reemplaza, sólo cuando el variador la detecta, una que dice de qué línea es la
  reacción modelada.
- **D7. `COSIM_EPOCH`: la discrepancia no la sube.** Un circuito sano tiene S1 = S2 (un NC a los
  dos, dos NC de una seta o las dos salidas del relé conmutan juntas): la huella de los escenarios
  sanos del banco no cambia (se mide antes y después y va a la bitácora); la huella de
  `test_cosim_epoch.py` se actualiza con el porqué. Lo que sí cambia (un escenario con una falla de
  canal o con un cableado de un solo canal) lo vence la FIRMA del documento: la ficha del variador
  gana `STO_discrepancia_ms` y el `modelo` entra a ella.
- **D8. El banco carga su vecino por su RUTA**, sin tocar `sys.path`: si `tablero_electrico` ya está
  importado desde el mismo archivo se reusa; si no, se carga de `tests/tablero_electrico.py` junto
  al banco. Dentro de la suite nada cambia. Un test lo prueba en un proceso aparte sin `tests/` en
  `sys.path`.
- **D9. El docstring cita las líneas del catálogo**: XB5AS8442 (1 NC) y XB5AS8444 (2 NC). Es texto:
  ni epoch ni `version`.
- **D10. Un cilindro sin pieza 3D pesa con la carrera de su `servicio`.** La fila de
  `bom_electrico` agrupa por (ref, carrera), dice «carrera N mm» como la de la escena, lleva
  `longitud_mm` y pesa `peso_de_ficha(comp, carrera)` (la misma función de la BOM de la escena).
  Sin `servicio.carrera_mm`, la fila sigue como hoy: el ERC ya avisa «servicio del cilindro».
- **D11. El vástago se mueve con la masa MÓVIL de la ficha.** La dinámica pesa la pieza vástago de
  un `create_pneumatic_cylinder` con `partes_de_cilindros` (base + por_mm × carrera: pistón,
  tuerca, imán y vástago) y la co-simulación ya no le suma la masa en carrera 0 como armadura (la
  contaría dos veces). Un vástago hecho a mano (sin ficha que lo cubra) sigue como hoy: volumen ×
  densidad + la armadura. Cambia el resultado de un escenario SANO con aire → **`COSIM_EPOCH` 6 →
  7**.
- **D12. Los subproductos del C96 se aplican con la tabla leída.** Nueva fuente [F9] (catálogo SMC
  C96, tabla «Basic», pág. PDF 8, y estándar de carreras, pág. PDF 5) en `130_cilindros_neumaticos.
  yaml`: salen de `a_confirmar` el Ø y la rosca del vástago del Ø40 y del Ø50, el AM, el WH y la
  rosca de las tapas de los cuatro ISO 15552, la carrera máxima del Ø40 y del Ø50 (1900) y el lado
  E del Ø40 (54). Queda a confirmar el E del Ø32 (45 en el YAML, 47 en el C96: E no es cota de
  interfaz de ISO 15552 y cambia por marca). Ningún `params` cambia: ni `GEOM_CACHE_EPOCH` ni
  `version`; el `neumatico` entra a la firma del documento, así que los resultados de un documento
  con esos cilindros quedan vencidos solos.

## Alternativas descartadas

- **Declarar en `MODULOS` los cuatro nombres que usa hoy la extensión** (D1): congela el snapshot,
  el error de `services` y el proceso del worker, tres detalles de implementación, y la siguiente
  extensión que corra un escenario repetiría el mismo armado.
- **Una función de una fase `correr_escenario(doc, esc)`** (D1): bajo el lock del llamador tendría
  el documento bloqueado durante la corrida; tomando el lock, sólo vale para el documento activo y
  una adquisición por corrida.
- **Rearmar el variador aunque persista la discrepancia** (D5): con un canal pegado el rearme
  borraría la falla en el acto y la discrepancia volvería a vencer 500 ms después: la máquina
  arrancaría medio segundo, que no es la reacción del aparato.
- **El tiempo de discrepancia como constante del código** (D6): es un parámetro programable del
  variador (`p9650`); en el código no lo vería el ERC, el manual ni una prueba con otro valor.
- **Meter `tests/` del núcleo en el `sys.path` del banco** (D8): una extensión tiene su propio
  `tests/` y su `conftest`; también mover `tablero_electrico` al paquete: es una utilidad de tests.
- **Sin carrera, pesar la fila en blanco** (D10): cambiaría el costeo de un cilindro sin servicio
  por un dato que el ERC ya pide.
- **Pesar el vástago con la masa móvil por mm y dejar la de carrera 0 como armadura** (D11): da la
  misma masa total pero el pistón no tiene sólido propio; con la pieza a la masa entera el centro
  de masa queda en el vástago, como en `scene_mass_properties` (V8.9 D-d).

## Fases

- **F1 — La corrida por la API y el banco sin alias** (`services`, `extensiones_api`, `tests`, S).
  D1–D4 y D8. Verifica: test de la API (rechazo con el texto exacto, corrida sana con la huella del
  camino de siempre, fallo del worker, las dos fases sin lock propio, re-export por identidad) y
  test del banco cargado por su ruta en un proceso aparte; suite completa.
- **F2 — La discrepancia del STO** (`cosim`, catálogo, S–M). D5–D7. Verifica: gemelos del modelo
  (discrepancia breve tolerada, larga en falla, el rearme con la discrepancia puesta no la borra,
  selección y deselección o corte de red la acusan); la pareja verde/roja sobre el banco con el
  relé de seguridad (sano: la marcha repetida arranca; con S1 pegado: no arranca y la falla queda);
  huellas sanas antes/después; suite completa.
- **F3 — Remates** (`library`, catálogo, S). D9, D10, D12. Verifica: la fila del cilindro sin pieza
  con su carrera y su peso; la ficha del C96 sin los `a_confirmar` cerrados; suite completa.
- **F4 — La masa del vástago en la dinámica** (`physics`, `services`, S). D11. Verifica: la masa del
  cuerpo móvil del Ø63 × 800 = 2,43 kg (antes 2,77 con la armadura); el empujador del banco de aire
  sigue empujando la caja; huella del escenario de aire cambia, la de los eléctricos no; suite
  completa.

F1–F4 no comparten archivos salvo `test_cosim_epoch.py` (F2 y F4) y la bitácora.

## Lo que este plan NO hace

- No toca la extensión: adopta la API después.
- No da veredicto de aserciones ni vigencia por la API de corrida (D2) ni corre un PLC de afuera.
- No modela la discrepancia de la línea Delta (su manual no se leyó) ni el filtro de pulsos de
  prueba ni el «forced dormant error detection» del G120.
- No corrige el E del Ø32 ni la fila de un cilindro sin `servicio`.
- No cambia los otros dos ayudantes de la suite que importan a un vecino por nombre
  (`lazo_externo.py`, `presostato_escena.py`): nadie los carga desde fuera.

## Riesgos

- **Un escenario guardado con un canal de STO pegado sigue «vigente» con el resultado viejo** si la
  firma no cambiara: la cambia, porque el `modelo` del variador gana una clave (D7). Medido en F2.
- **Un cableado de un canal real** (S1 puenteado a 24 V y S2 por la seta) pasa a quedar en falla al
  pisar la seta: es el comportamiento del aparato; el ERC ya marca «canales del STO» en ese caso.
- **La extensión sigue con su test rojo esperado** hasta adoptar F2: su caso de categoría 4 pasará a
  verde y el de categoría 3 dirá «detectada». Se le avisa en el informe.

## Bitácora

### F1–F4 (2026-10-26, base `b9d774f`)

Hecho en una rama, una fase por commit:

- **F1 (D1–D4, D8).** `services/corrida_escenario.py`: `preparar_corrida(doc, escenario,
  programas=)` resuelve el escenario (`escenarios.resolver`: nombre o dict) y toma el snapshot;
  `correr_corrida(preparada, timeout_s=)` corre el worker. `EscenarioRechazado` lleva el `detail` y
  el `status_code` del `ServiceError` (400 de lo que el snapshot no toma, 404 de un nombre que no
  existe); `CorridaFallida`, el texto de `CosimError`; los dos son `CorridaError` con `motivo`.
  `CorridaPreparada` es un dataclass congelado (`nombre`, `escenario`, `snapshot` opaco). Los seis
  nombres entran a `extensiones_api.SUPERFICIE` (`CONTRATO_EXTENSIONES` sigue en 1: sólo se
  agrega). El banco carga a `tablero_electrico` por su ruta (`_vecino`): reusa el módulo si ya
  está importado desde ese archivo; si no, lo carga y lo registra con su nombre (otro importador
  recibe el mismo). Medido: la huella de la corrida por la API = la del planificador en proceso.
- **F2 (D5–D7).** `cosim/modelos/variador.py`: `_vigilar_discrepancia` en el paso 5 y la
  marca re-aplicada tras el rearme (como `falla_interna`); un corte de red (`sin_red`) la acusa.
  `STO_discrepancia_ms: 500` en `_vfd_mando` de `91_variadores.yaml` con su fuente. La hipótesis
  de una falla `canal_sto_pegado` dice ahora de qué línea es la reacción modelada.
- **F3 (D9, D10, D12).** Docstring de `builders_mandos.py`; `bom_electrico._carrera` y la clave
  (ref, carrera); [F9] y los `a_confirmar` cerrados en `130_cilindros_neumaticos.yaml`. Releído el
  PDF del C96 con `pdftotext` antes de tocar el YAML: la tabla coincide con los `params` de las
  cuatro refs (AM, d, KK, WH, tapa, puerto, TG, C), así que no se movió ninguna cota.
- **F4 (D11).** `physics/dinamica_cuerpos.masas_de_ficha` (= `partes_de_cilindros`) entra a
  `geometria_movil(masa=)` desde `prepare_dynamics`; `services/cosim_aire.peticion` suma la
  armadura sólo si el hijo de la junta no pesa por ficha. Medido: el Ø63 × 800 suelto, cuerpo móvil
  2,43 kg (antes 2,34 por volumen + 0,43 de armadura en la co-simulación); el empujador del banco
  de aire (Ø32 × 200), armadura 0 y masa = 0,29 + la placa.

**Huellas de los escenarios sanos** (en proceso, `planificador.correr`, antes = `9d3bb26`):

| escenario | F2 vs antes | F4 vs antes |
|---|---|---|
| marcha por variador | igual | igual |
| seta por variador | igual | igual |
| seta y liberar por variador | igual | igual |
| seta de dos NC (`arranque_variador_plc_cat3`) | igual | igual |
| relé de seguridad, abre el resguardo | igual | igual |
| relé de seguridad, la seta | igual | igual |
| marcha en directo | igual | igual |
| empujador de aire (Ø32 × 200) | igual | CAMBIA (x_mm final −0,520 → −0,551) |

«Igual» = misma huella, mismos finales y mismas hipótesis. Por eso F2 no sube `COSIM_EPOCH` (D7)
y F4 lo sube a 7 (D11).

Decisiones propias (vetables):

- **D-a. `CorridaPreparada` lleva el escenario resuelto y el nombre**, no la firma ni el hash: la
  extensión tiene su propia clave de caché y calcular la firma por corrida (la FAT prepara varias)
  sería trabajo bajo el lock que nadie pidió. Se suma si una extensión lo pide.
- **D-b. El rearme no se bloquea: la falla se RE-APLICA** mientras la marca siga sin acusar (el
  patrón de `falla_interna`). Así el rearme sigue borrando otra falla, y la de discrepancia vuelve
  en el mismo paso.
- **D-c. El corte de red acusa la marca pero no borra la falla**: el modelo nunca borró una falla
  por un corte (ninguna otra lo hace); después hace falta el rearme, como tras una subtensión.
- **D-d. La hipótesis va sólo con la falla inyectada** (como antes): las hipótesis de un modelo se
  juntan al armar el tablero, y una que apareciera recién al detectar no llegaría al resultado. En
  un circuito sano no hay hipótesis nueva (la huella y las hipótesis de los 7 eléctricos, iguales).
- **D-e. El banco registra a su vecino con su nombre** en `sys.modules` cuando nadie lo tenía: lo
  que hace un `import`, y así el mismo módulo sirve a quien lo importe después. No mete `tests/`
  en el `sys.path`.
- **D-f. El lado E queda «a confirmar» donde difiere por marca** (Ø32 45/47, Ø50 64/66, Ø63 75/77
  Festo/SMC) y el del Ø40 sale (54 en los dos); el texto de `specs.a_confirmar` del Ø40 dice que
  ninguna cota de ISO 15552 queda abierta (el campo es obligatorio para los tests de la masa).
- **D-g. `masas_de_ficha` también pesa el CUERPO** de un cilindro que se mueve (montado en un carro):
  ficha − masa móvil, como en `scene_mass_properties`; antes contaba el vástago dos veces.

Tests nuevos: `tests/test_corrida_escenario.py` (superficie por identidad, rechazo con el texto
exacto y su 404, la huella por el worker = la del planificador, el worker que se cae, el banco
cargado por su ruta en otro proceso), `tests/test_sto_discrepancia.py` (la ficha, discrepancia
breve tolerada, larga en falla sin acusar, acuse por los dos canales y por corte de red, canal
pegado que no se acusa; en el banco con el relé de seguridad: VERDE sana rearranca, ROJO con S1
pegado la seta corta igual y no rearranca, la falla a 1,5–1,6 s; el tiempo en la firma),
`tests/test_pedidos_iii_remates.py` (la fila del Ø63 × 800 = 6,70 kg, agrupada por carrera, sin
servicio la de siempre; las cuatro fichas contra la tabla del C96; el docstring) y
`tests/test_masa_vastago_dinamica.py` (el Ø63 × 800 a 2,43 kg, el empujador sin armadura, un
vástago sin ficha con ella). Cambiados: `tests/cosim_lazo_banco.py` (el vecino por su ruta) y la
`HUELLA` de `tests/test_cosim_epoch.py` (F2 sin subir, F4 a 7, con su porqué). Re-congelado a
propósito: `tests/test_firma_dispositivo.py`, las firmas de los tres tableros con variador (la
primera corrida de la suite entera lo cazó: es D7 medido) — `arranque_variador_plc` 5171b78… →
69e6eea…, `_cat3` e3dd3c5… → aee944e…, `_rele_seguridad` c726c9f… → 0e62a99…; sin el `esquema` IT
ni `STO_discrepancia_ms` dan exactamente las de antes (el test lo comprueba quitando las dos
claves). Ningún otro test cambió de expectativa.

Vigencia: `COSIM_EPOCH` 6 → 7 (F4); `GEOM_CACHE_EPOCH` igual (ningún `params` ni builder: el
docstring es texto, `specs`/`neumatico`/`modelo` no tocan la geometría); ninguna `version` de
comando (ningún executor cambió); firmas: los documentos con un VFD-1K5/2K2-220 (el `modelo` gana
`STO_discrepancia_ms`) o con un ISO 15552 (su `neumatico` cambia de `fuente` y `a_confirmar`)
cambian de firma y sus resultados quedan vencidos solos; con el epoch 7, todos.

**Suite completa** (`-n auto`, `PYTHONPATH` al `core/` de cada árbol, una a la vez):

| árbol | tests elegidos | exit |
|---|---|---|
| base `b9d774f` (worktree aparte) | 6222 | 0 |
| rama, primera corrida | 6251 | 1 (4 FAILED de `test_firma_dispositivo.py`: las firmas con variador, D7) |
| rama, tras re-congelar esas firmas | 6251 | 0 |

`ruff check core tests scripts` limpio. No se tocó `ui/`.
