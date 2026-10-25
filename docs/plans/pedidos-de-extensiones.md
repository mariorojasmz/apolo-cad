---
estado: en curso
nota: contrato de Claude derivado de pedidos de extensiones, con el aval del titular (2026-10-24: «procede según tu criterio»); medido sobre `97d93c3`; F1 (superficie), F2 (dispositivo: símbolo y acople fuera de la firma) y F4 (cifras eléctricas medidas: ΔU de motores, disparos; el diferencial por su residual) mergeadas; F3 (entregable como job: `entregable_documento`) implementada, en revisión; F6 (el bus repite la sesión abierta a quien llega tarde; `plcs` en el `inicio`) implementada, en revisión; siguen F5 (notas de cotización) y F7 (la pieza de lo que dibuja el layout)
descripcion: una extensión lee el circuito, la prueba virtual y la sesión viva por el contrato declarado (con las cifras eléctricas medidas, los tipos de las variables del PLC y la sesión ya abierta), entrega sus archivos lentos como job y suma notas a la cotización
---

# Una extensión lee el circuito, la prueba virtual y la sesión viva por el contrato, y sus entregables lentos van como job

## Estado y origen

- Dos extensiones pidieron ajustes al núcleo mientras se implementaban y los anotaron en su
  bitácora: una de entregables eléctricos (esquemas, memoria de cálculo, manual; V8.6 de
  [V8](V8-maquina-viva.md)) y una que expone la sesión viva a un SCADA (V8.8 de V8). Este plan
  cuenta sólo lo GENÉRICO.
- Ninguna tocó el núcleo: cada pedido lo resolvieron con una copia de una regla, una lectura no
  declarada o una ruta síncrona, expuestas a que un refactor las rompa sin aviso.
- Misma forma que [puntos de extensión de entregables](puntos-de-extension-entregables.md),
  [datos de corte y acometida](datos-de-corte-y-acometida.md) y [PLC en el lazo](plc-en-el-lazo.md).
- Contrato de Claude con el aval del titular («procede según tu criterio», 2026-10-24), redactado
  tras una medición de sólo lectura (sub-agente) y decidido por la sesión principal (al final de
  § Decisiones). Se veta por número.

## Lo que hay hoy

Rutas relativas a `core/apolo/`, medidas sobre `97d93c3`.

- **Superficie.** `extensiones_api.MODULOS` (l. 90-169) no declara cosas que existen: `PILOTAJE`,
  `pilotaje`, `trazos_mm` de `drawing/esquema.py:33,58,65` (la entrada llega hasta
  `SIMBOLO`/`LLENO`); `library/electrico/redes.resolver` (l. 121-150, «-K1:A1» → (designación,
  borne)); `drawing/dwg.py` (`DwgError` l. 31, `disponible` l. 63, `sheet_to_dwg` l. 97);
  `services/escenarios.listar`/`estado` (l. 249, 220), la lectura de la prueba virtual; y el
  formato del fotograma vivo (`cosim/vivo_fotograma.py`: `FORMATO` l. 39, `CABECERA` l. 40,
  `leer_fotograma` l. 200-215).
- **El dispositivo del carril.** `library/electrico/modelo.Dispositivo` (l. 74-115) no copia
  `simbolo` de su ficha (`ficha.py:87`). Un bloque de contactos auxiliares (caminos `accion:
  acople`) no dice qué aparato lo mueve, y hay DOS reglas: la co-simulación busca el maestro por el
  sufijo de letras (`services/cosim_red.py:37,50-63,106-116`: «-Q3A» → «-Q3»); la colocación del
  tablero usa otra (`library/electrico/colocacion.py:112-142`: prefijo sin dígito, si no el único
  aparato de ese símbolo, si no el override `acopla` de `layout_tablero`).
- **La firma del documento hace `asdict` de cada `Dispositivo`** (`services/escenarios.py:39-49`):
  cualquier campo nuevo cambia la firma de todo documento con tablero y vence todos los resultados
  guardados (por eso `datos` de ficha quedó fuera, `tests/test_ficha_datos.py:225-247`).
- **Lecturas largas.** La fachada (`api/fachada.py:43-61`) da `leer_documento` (síncrono) y
  `mutar_documento(asincrono=)`; no hay job de LECTURA. El núcleo tiene la cola de entregables con
  archivo (`ENTREGABLES_JOBS`, `ARCHIVOS`, `_job_entregable`, `_mismo_proyecto`:
  `api/common.py:83-84,279-308`) y la tool `tools/entregable.pedir` (l. 55-62). Medido por la
  extensión: un ZIP de láminas con DWG tarda 2–14 s, una memoria 1,5 s, un manual 2,1 s, todo
  síncrono.
- **Cotización.** Las notas son una lista FIJA (`drawing/quote.py:120-131`); una fila de extensión
  que cobra un servicio cercano no puede aclararlo. La columna «Fuente del precio» mide con la
  fuente del PDF a 720 ppp + 2 % (`drawing/tabla.py:33-34`); el test la verifica a 600 ppp
  (`tests/test_cotizacion_f4c.py:235`); la extensión la vio rozar el borde en una imagen a 100 ppp.
  Hay sitio para más notas a la izquierda del cajetín (≈ 19 líneas; las del núcleo ocupan 6–9).
- **El resultado guardado de un escenario** (`services/escenarios.resultado_compacto`, l. 286-303)
  no trae trazas; del aire guarda un resumen medido (`services/aire_resultado.py`), de lo eléctrico
  nada. El motor no publica la tensión que recibe (`cosim/modelos/motor.py:22-23`, la usa en
  l. 159); la protección no publica la corriente con que disparó (`cosim/modelos/protecciones.py:14,140-142`).
- **Bus de la sesión viva** (`api/vivo_bus.py`): `suscribir` entrega desde que uno se suscribe
  (l. 139-150): quien llega con la sesión abierta no recibe el `inicio` ni las `senales`. El
  `inicio` (`api/routers/cosim_vivo.py:276-286`) no dice el tipo ni si se puede escribir cada
  variable del PLC; `Compilado.simbolos` (`plc/simbolos.py:69-92`) lo sabe.
- **Vigencia:** `COSIM_EPOCH = 6` (huella de `tests/test_cosim_epoch.py`: `cosim/**`, `plc/**`,
  `services/cosim_red.py`, `cosim_snapshot.py`, `cosim_aire.py`, `cosim_bandas.py`);
  `GEOM_CACHE_EPOCH = 7`; `CONTRATO_EXTENSIONES = 1`.

## Lo que se revisó antes de escribir esto

- Todo lo de superficie, salvo el job, ya existe con el nombre que se pide: declararlo no sube
  `CONTRATO_EXTENSIONES`.
- La firma manda el diseño del dispositivo: un campo que no es física (`simbolo`) o que se deriva
  de lo que el log ya firma (`acoplado_a`) tiene que quedar FUERA de la firma de forma explícita.
- La regla de la co-simulación es la que mueve los contactos: el campo nuevo usa ESA regla. La de
  la colocación decide dónde se MONTA el bloque y puede diferir con un override (§ Riesgos).
- El job de lectura no necesita cola nueva: es `_job_entregable` con dos fases (extraer bajo el
  lock, componer fuera), el patrón de la memoria y del manual del núcleo.
- Medir lo eléctrico exige trazar algo nuevo (la tensión del motor): cambia la huella de un
  escenario con motores, pero no el valor de lo que ya se publica ni ningún veredicto (D8). La
  corriente de disparo puede quedar retenida y publicarse sólo DESPUÉS de disparar, como `averia`.
- La FAT del núcleo es correr los escenarios: su resultado vive en el manifest y se lee con
  `escenarios.listar`. El informe de FAT de OTRA extensión no es del núcleo.

## Decisiones (para vetar)

- **D1 — Superficie de lo que ya existe.** `MODULOS` suma, con los nombres de hoy (un test lo
  exige): `apolo.drawing.esquema` (`PILOTAJE`, `pilotaje`, `trazos_mm`, `TRAZO_X_GROSOR`,
  `HUECO_X_GROSOR`); `apolo.library.electrico.redes` (`resolver`); `apolo.drawing.dwg` (`DwgError`,
  `disponible`, `sheet_to_dwg`); `apolo.services.escenarios` (`listar`, `estado`,
  `firma_documento`, `SIN_CORRER`, `VENCIDO`); `apolo.cosim.vivo_fotograma` (`FORMATO`,
  `CABECERA`, `leer_fotograma`). `SUPERFICIE` suma `pedir_entregable` (`apolo.tools.entregable:pedir`).
  Agregar no sube `CONTRATO_EXTENSIONES`.
- **D2 — El fotograma y el `inicio` como contrato.** La disposición del docstring de
  `vivo_fotograma.py` es contrato: cambiar la cabecera, el orden de los bloques o el tipo (float32
  LE) sube `FORMATO`; un test congela la cabecera y lee un fotograma sintético. El `inicio`
  conserva `version: 1`: agregar claves no la sube; quitar o renombrar, sí.
- **D3 — `Dispositivo.simbolo`** (texto, `""` por defecto), copiado de la ficha eléctrica por
  `dispositivo_desde_ficha` (`modelo.py:252-270`); un aparato de aire sin ficha eléctrica lo toma
  de su ficha neumática (`commands/neumatica_eval.py:78-86`).
- **D4 — `Dispositivo.acoplado_a`** (designación o `None`): UNA regla pura en
  `library/electrico/acoples.py`, la de hoy de la co-simulación (la designación sin el sufijo de
  letras, si existe y tiene bobina, protección o manija); la aplica el carril al cerrar el modelo
  (`commands/electrico_eval.py:312`, `dataclasses.replace`); `services/cosim_red.py` la LEE en vez
  de calcularla (su aviso «contacto auxiliar sin aparato que lo mueva» sigue con `None`). Refactor
  sin efecto: huella actualizada con el banco idéntico, `COSIM_EPOCH` no sube. La colocación
  conserva su regla de montaje.
- **D5 — La firma no ve lo que no es física.** `services/escenarios._fichas_electricas` saca de
  cada dispositivo `FUERA_DE_FIRMA = ("simbolo", "acoplado_a")`. Trinquete: todo campo de
  `Dispositivo` está en la firma o en `FUERA_DE_FIRMA` (un campo futuro obliga a decidir). Las
  firmas de los cuatro tableros de `tests/tablero_electrico.py` quedan IGUALES.
- **D6 — El entregable de una extensión como job:** `entregable_documento(extraer, componer, *,
  tipo, asincrono=False)` en `api/fachada.py`, en `SUPERFICIE`. `extraer(doc)` corre bajo
  `STATE_LOCK` con `_mismo_proyecto` (409 si cambió el proyecto) y sólo EXTRAE datos puros;
  `componer(datos) -> (bytes, media_type, nombre)` corre fuera de todo lock. Sin `asincrono`, la
  `Response` con el archivo; con `asincrono`, 202 + recibo en `ENTREGABLES_JOBS` (resultado
  `{archivo, bytes, tipo, nombre}`, como `_job_entregable`). `CommandError`/`DocumentError` → 400;
  una `HTTPException` de la extensión pasa tal cual. Sin cola nueva.
- **D7 — Cifras eléctricas medidas en el resultado de un escenario.** El motor publica
  `<motor>.U_V` (la tensión de línea en sus bornes, la que ya usa su `paso`); cada protección
  publica `<des>.I_disparo_A` (la mayor corriente de sus polos en el paso del disparo, retenida
  hasta rearmar, SÓLO tras disparar). `services/medidas_electricas.py` (puro, como
  `aire_resultado.py`) arma `resultado["electrico"]` sólo si hay motores o un disparo: por motor
  `U_ref_V`, `U_min_arranque_V`, `U_regimen_V`, `dU_arranque_pct`, `dU_regimen_pct`; por disparo
  `t_s`, `I_A`, `causa`; y `medicion` con el criterio (arranque: desde que U pasa de 0 hasta que
  `I_A` baja de 1,5·In de placa; régimen: mediana de U en el último 0,5 s alimentado; resolución
  `analogicas_hz`). Un motor tras un variador lleva `tras_variador: true` y no lleva ΔU. Las
  referencias salen del documento en la API, nunca del worker. Sin motores ni disparos, el
  resultado de siempre.
- **D8 — `COSIM_EPOCH` no sube por D7.** Lo que ya se publicaba conserva su valor y ningún
  veredicto cambia (se prueba en el banco: trazas sin las señales nuevas idénticas, aserciones
  iguales); ninguna aserción guardada pudo nombrar `-M1.U_V` (antes era 400); un resultado viejo
  sin `electrico` sigue vigente y quien lo lea dice «córrelo de nuevo para tener las cifras».
- **D9 — Notas de la cotización desde una extensión:** `FuenteCosteo.nota: str | None = None`
  (default: el contrato sigue en 1); validada al cargar (no vacía, una línea, ≤ 300 caracteres; si
  no, la extensión no carga); sale sólo si su fuente cobró al menos una fila, DESPUÉS de las notas
  del núcleo (que no se quitan); el costeo suma `notas: [{texto, fuente, origen}]` sólo si hay; lo
  que no cabe a la izquierda del cajetín sigue en una hoja «NOTAS (continuación)», nunca encima del
  cajetín; la extensión sube su `version_costeo` si cambia la nota.
- **D10 — El margen de «Fuente» se mide antes de tocarlo**: el detalle de una cotización con
  fuentes largas a 96 y 100 ppp; si alguna caja sale de su celda, `partir` corta a
  `ancho − 2·PAD_X − HOLGURA_TRAMA_MM` (la cifra medida) y el test de celdas suma esa resolución;
  si no sale, se descarta con la medida en la bitácora.
- **D11 — El bus entrega la sesión ya abierta.** Guarda, de la sesión abierta, el `inicio`, cada
  `senales` en orden y el último valor de cada texto (en `difundir_json`, bajo el lock que elige
  los destinos, aunque no haya suscriptores). `suscribir` con una sesión abierta pone primero, en
  orden, el `inicio` con `tarde: true`, las `senales` y un `textos` con lo acumulado, todo bajo el
  lock del bus (ningún fotograma se adelanta). Se olvida al abrir otra sesión, al `fin` y al
  `cerrar`.
- **D12 — El `inicio` dice las variables de cada PLC:** `plcs: [{designacion, variables: [{ruta,
  tipo, escribible}]}]`, de `Compilado.simbolos` de los programas del snapshot
  (`services/variables_plc.py`), cada `ruta` con la MISMA escritura que la señal del fotograma
  (`PLC.variables()`). Sin PLC, sin clave. No toca `cosim/**` ni `plc/**`.
- **D13 — La extensión falsa lo usa todo** (`tests/ext_prueba/`): lee con los nombres de D1;
  una ruta suya va por `entregable_documento` en directo y como job; su fuente de costeo lleva nota
  (y una variante con nota mala no carga); su suscriptor llega tarde a una sesión y la sigue.
- **D14 — Vigencia.** La firma del documento no se mueve (D5); `COSIM_EPOCH` sigue en 6 (D4 y D8:
  F2 y F4 actualizan la huella con el banco igual); `GEOM_CACHE_EPOCH` y versiones de comandos, no;
  `CONTRATO_EXTENSIONES` sigue en 1; ninguna tool MCP nueva; `.apolo`, log y SQLite iguales salvo
  la clave opcional `electrico` en el resultado guardado de un escenario (metadato).

- **D15 — Lo que dibuja `layout_tablero` lleva su `pieza` en el modelo vivo** (pedido posterior al
  contrato, de la extensión que dibuja una pantalla sobre el panel de la puerta): hoy un aparato
  colocado por el layout no figura como `pieza` en la tabla del `inicio` del vivo, así que nada se
  puede pegar a él (ni la pantalla 3D de `pantallas3d`, ni abrirlo desde un clic en la pieza). Si
  el layout ya da a cada caja un id estable (`{cmd}_d_<designación>` o el que sea), la tabla del
  vivo lo publica como `pieza` del dispositivo; si un dispositivo tiene `pieza` explícita
  (`add_device pieza`), gana la explícita. Sin cambio de firma (la pieza no es física del
  circuito: va a `FUERA_DE_FIRMA` si toca `Dispositivo`) ni de geometría; `COSIM_EPOCH` sólo si la
  huella lo pide, con el banco igual.

**Se descarta:** el informe de FAT de otra extensión por API del núcleo (la FAT del núcleo son los
escenarios, ya declarados en D1); que una extensión reemplace las notas de honestidad comercial
del núcleo (sólo aclara, D9); los puntos resueltos de cada conductor dentro de `Analisis` (D1
declara la regla).

**Decisiones de la revisión** (sesión principal, 2026-10-25): D8 sin bump, con la evidencia del
banco como condición (si una señal nueva cambia un veredicto, la época sube en la misma fase); D5
con su trinquete; queda FUERA el aviso del ERC que compare las dos reglas de acople (cambiaría el
semáforo de documentos existentes: plan propio si hace falta); el DWG de varias láminas en un solo
proceso del conversor (`api/routers/drawings.py:230`, probable causa de los 5–14 s) se mide aparte.

## Alternativas descartadas

- **Subir `COSIM_EPOCH` por D7**: vencería todos los resultados guardados sin que cambie un
  veredicto.
- **Trazar sólo las tensiones de borne que pide el escenario** (`senales_extra`): cada escenario
  tendría que nombrar cada motor para tener la memoria.
- **Unificar ya la regla de acople con la de la colocación**: cambiaría el resultado de la
  co-simulación en los documentos donde difieren.
- **Un `leer_documento(asincrono=True)` que devuelva JSON**: lo lento son archivos, y su job ya
  tiene forma en el núcleo.
- **`simbolo` con `compare=False`**: `asdict` lo incluiría igual; la exclusión explícita con
  trinquete es la que se ve.
- **Cambiar la holgura del 2 % de todas las tablas sin medir**: movería la paginación de toda tabla
  del núcleo por un síntoma visto en una imagen.

## Fases

Dos carriles, como mucho dos agentes a la vez: **F1 ∥ F2 → F3 ∥ F4 → F5 ∥ F6** (carril A: F1 →
F3 → F5; carril B: F2 → F4 → F6). Ningún par simultáneo toca los mismos archivos; F1 y F3 tocan
`extensiones_api.py` y F2 y F4 la huella de `test_cosim_epoch.py`: van en serie en su carril.

- **F1 — Superficie de lo que ya existe** (S · ≈ 45 min): D1, D2 y D13 de lectura
  (`extensiones_api.py`, `tests/test_extensiones_api.py`, `tests/ext_prueba/contrato.py`, una
  prueba del formato del fotograma). **Se verifica:** suite completa y `ruff`; un caso por módulo y
  nombre nuevos; el gate de imports de la extensión falsa; «importar la superficie no carga OCCT»
  verde; la cabecera congelada y un fotograma sintético leído; `CONTRATO_EXTENSIONES == 1`.
- **F2 — El dispositivo dice su símbolo y quién lo mueve** (M · ≈ 60 min): D3, D4, D5
  (`library/electrico/modelo.py`, `acoples.py` nuevo, `commands/electrico_eval.py`,
  `commands/neumatica_eval.py`, `services/cosim_red.py`, `services/escenarios.py` —sólo
  `_fichas_electricas`—, `tests/test_cosim_epoch.py`). **Se verifica:** `acoplado_a` «-Q3A» →
  «-Q3» en el tablero de prueba, `None` y el mismo aviso sin maestro; las firmas de los cuatro
  tableros iguales; el trinquete de campos; la entrada de red de la co-simulación idéntica y el
  banco con la misma huella; `carril_v81_golden.json` sin cambios; `ruff`.
- **F3 — El entregable de una extensión como job** (S/M · ≈ 50 min · depende de F1): D6 y D13 del
  job (`api/fachada.py`, `extensiones_api.py`, `tests/ext_prueba/rutas.py`). **Se verifica:** en
  directo, el archivo con su nombre; con `?async=true`, 202 + recibo y el archivo por
  `GET /api/jobs/{id}`; otro proyecto abierto da 409 sin generar; `componer` corre con
  `STATE_LOCK` libre (parche que falla si se toma); error de dominio = 400; una tool de la
  extensión falsa con `pedir_entregable` + `get_job` guarda el archivo; el golden sin cambios.
- **F4 — Cifras eléctricas en el resultado** (M/L · ≈ 70 min · depende de F2): D7, D8, D14
  (`cosim/modelos/motor.py`, `protecciones.py`, `services/medidas_electricas.py` nuevo,
  `services/escenarios.py` —`resultado_compacto`—, `api/routers/cosim.py`,
  `tests/test_cosim_epoch.py`). **Se verifica:** en un arranque directo del banco, ΔU de arranque y
  de régimen contra la cuenta a mano con la R y la X de `cosim/red/conductores`; un disparo con su
  hora, corriente y causa; un motor tras variador sin ΔU; sin motores ni disparos, el compacto de
  siempre; en el banco, trazas sin las señales nuevas idénticas y veredicto igual (evidencia de
  D8); `set_scenario` acepta una aserción sobre `-M1.U_V`; vivo y lote con la misma huella.
- **F5 — Notas de la cotización y margen de «Fuente»** (M · ≈ 55 min): D9, D10 y D13 del costeo
  (`library/costeo_extension.py`, `extensiones_puntos.py`, `services/cobros.py`,
  `drawing/quote.py`, `drawing/tabla.py` sólo si D10 lo confirma). **Se verifica:** la nota sale
  tras las del núcleo sólo si su fuente cobró; una nota mala rechaza la extensión con el registro
  deshecho; el peor caso (avisos + tipo de cambio + notas largas de dos fuentes) no pisa el cajetín
  y sigue en la hoja de continuación; sin extensiones, costeo y PDF byte-idénticos; la medida de
  D10 en la bitácora.
- **F6 — El bus entrega la sesión abierta y el `inicio` dice las variables** (M · ≈ 55 min): D11,
  D12, D13 del bus (`api/vivo_bus.py`, `api/routers/cosim_vivo.py`, `services/variables_plc.py`
  nuevo). **Se verifica:** un suscriptor a mitad recibe primero `inicio` (`tarde: true`), las
  `senales` y los textos, y después los fotogramas, que se leen con esa tabla; otra sesión no le
  repite la vieja; tras el `fin`, nada que repetir; el WebSocket de la persona recibe lo de
  siempre; el bus nunca toma `STATE_LOCK`; `plcs` con globales, PROGRAM, CONSTANT, `AT` y FB con la
  misma escritura que las señales; sin PLC, sin clave; la huella sin cambios.

- **F7 — La pieza de lo que dibuja el layout** (S · ≈ 40 min · después de F2; independiente del
  resto): D15. **Se verifica:** un tablero armado con `layout_tablero` y un panel de operador: la
  tabla del `inicio` trae la `pieza` de cada aparato dibujado; una `pieza` explícita gana; las
  firmas de los cuatro tableros iguales; la huella sin subir.

Al cerrar cada fase: una línea en el CLAUDE.md que toque y la `nota:`. Las cifras se miden con
`python scripts/conteos.py`.

## Lo que este plan NO hace

- No implementa ningún entregable ni servidor de una extensión: sólo los puntos por donde los
  enganchan.
- No unifica la regla de acople de la colocación con la eléctrica ni suma un aviso del ERC que las
  compare.
- No trae datos de ficha nuevos (Icc mínima, factor de potencia de arranque, I²t, poderes de corte
  «a confirmar», temperatura del tablero): son datos, de [datos de corte y acometida](datos-de-corte-y-acometida.md)
  o de un plan propio.
- No toca la UI (lista de atención con línea secundaria, desplazamiento del cajón, muestrario para
  extensiones: otro plan).
- No convierte varias láminas a DWG en un solo proceso del conversor: se mide aparte.
- No cambia el formato del `.apolo`, del log ni de la SQLite más allá de la clave opcional de D14;
  no suma tools MCP.

## Riesgos

| riesgo | mitigación |
|---|---|
| Un campo nuevo de `Dispositivo` vence todos los resultados sin que la máquina cambie | `FUERA_DE_FIRMA` + trinquete (D5); firmas de los cuatro tableros congeladas en F2 |
| El bloque auxiliar va pegado (colocación) a un aparato y lo mueve otro (regla eléctrica) | `acoplado_a` dice cuál lo mueve y el armado (ya declarado) dónde va; un aviso del ERC que los compare es otra decisión |
| D8 mal juzgado: una señal nueva sí cambia un veredicto | evidencia de F4 en el banco; si no, la época sube en la misma fase |
| ΔU de arranque mal muestreado | `medicion` declara la resolución; la cuenta a mano de F4 lo acota |
| Las notas de extensión llenan la hoja del resumen | tope por nota y hoja de continuación (D9), con el peor caso probado |
| El `inicio` crece con programas grandes | sólo `{ruta, tipo, escribible}` |
| Una extensión vieja contra el núcleo nuevo | sólo se agrega; `CONTRATO_EXTENSIONES` sigue en 1 |
| Archivos cerca del tope (`cosim_vivo.py` 428, `colocacion.py` 412, `extensiones_puntos.py` 375) | módulos nuevos; ninguno pasa de 500 |

## Bitácora

### F1 — Superficie de lo que ya existe

**D1.** Todos los nombres del plan existen hoy con ese nombre (ninguno se cambió). `MODULOS` suma
a `apolo.drawing.esquema` `PILOTAJE`, `pilotaje`, `trazos_mm`, `TRAZO_X_GROSOR` y `HUECO_X_GROSOR`;
a `apolo.library.electrico.redes`, `resolver`; y entran `apolo.drawing.dwg` (`DwgError`,
`disponible`, `sheet_to_dwg`), `apolo.services.escenarios` (`listar`, `estado`, `firma_documento`,
`SIN_CORRER`, `VENCIDO`) y `apolo.cosim.vivo_fotograma` (`FORMATO`, `CABECERA`, `leer_fotograma`).
`SUPERFICIE` suma `pedir_entregable` → `apolo.tools.entregable:pedir` (perezoso: importar la
superficie sigue sin cargar OCCT). `tests/test_extensiones_api.py` lleva un caso por módulo y
nombre nuevos (`PEDIDOS_MODULOS`) y el de `pedir_entregable` por identidad;
`CONTRATO_EXTENSIONES` sigue en 1.

**D2.** `tests/test_fotograma_contrato.py` (sin MuJoCo): congela `FORMATO = 1`, `CABECERA = 8` y
la línea de la cabecera del docstring; lee un fotograma SINTÉTICO armado con `struct` en `<f`
(no con el empacador: una regresión de uno no la tapa el otro), bloque por bloque, con un producto
sin nacer (NaN) y una señal sin valor; y llama `_inicio` con un `prep` mínimo para fijar
`version: 1` y sus claves. La regla, en `cosim/CLAUDE.md` (al final de «Planificador y worker»).
`vivo_fotograma.py` no se tocó: la huella de `test_cosim_epoch.py` no cambia.

**D13 de lectura.** `tests/ext_prueba/contrato.py` lee sólo con esos nombres (el gate de imports
la acepta): `bornes` con `resolver` sobre los dispositivos del modelo, `envolvente` con
`pilotaje`/`trazos_mm` (4,2 / 1,05 mm), `dwg` con `disponible`/`sheet_to_dwg`/`DwgError` (sin ODA,
el aviso del núcleo), `fat` con `listar`/`estado`/`firma_documento` (vigente = ni `SIN_CORRER` ni
`VENCIDO`) y `fotograma` con `leer_fotograma` y los nombres de la tabla (rechaza otro `FORMATO`).

### F2 — El dispositivo dice su símbolo y quién lo mueve

**D3.** `Dispositivo.simbolo` (`""` por defecto, al final de los campos: ningún constructor
posicional cambia) lo copia `dispositivo_desde_ficha` de `FichaElectrica.simbolo`; un aparato sólo
de aire (el FRL) toma el de su ficha neumática y una electroválvula, el de su ficha eléctrica, como
todo aparato con bornes (`commands/neumatica_eval.py`).

**D4.** `library/electrico/acoples.py` (65 líneas, puro) es la regla: `es_bloque_auxiliar`,
`maestro_buscado`, `actuador_maestro` (bobina > protección > manija), `acoplado_a` y
`cerrar_acoples`, que el carril aplica al devolver el `ModeloElectrico`
(`commands/electrico_eval.py`). `services/cosim_red.py` lee `d.acoplado_a` y pide a la misma regla
qué actuador del maestro nombrar y la designación buscada del aviso; ya no tiene su `_SUFIJO`,
`_maestro` ni `_actuador_maestro`. Si el `acoplado_a` nombra un aparato que no está en el modelo
(un modelo armado a mano y recortado), la red da el aviso de siempre en vez de un `KeyError`. La
colocación (`colocacion.resolver_acoples`) no se tocó. `tests/test_electrico_erc.py` arma sus dos
tableros A MANO: ahora los cierra con `cerrar_acoples`, como el carril (sin eso, -Q3A quedaba en
reposo en `test_cosim_red_adaptador`/`_mando`, que lo usan).

**D5.** `escenarios.FUERA_DE_FIRMA = ("simbolo", "acoplado_a")`, que `_fichas_electricas` saca de
cada dispositivo. El trinquete (`tests/test_firma_dispositivo.py`): `EN_FIRMA` (los 20 campos que
firman) ∪ `FUERA_DE_FIRMA` = los campos de `Dispositivo`, disjuntos, y un dispositivo firmado trae
exactamente `EN_FIRMA`.

**Vigencia (D14), medida** contra `ec4ac9b` exportado con `git archive`, con un banco ad hoc (la
misma salida byte a byte en los dos árboles):
- las firmas de los cuatro tableros de `tablero_electrico.py` iguales y congeladas en el test:
  directo `2:7feece8f…`, variador con PLC `2:35a1fea0…`, cat. 3 `2:5a114e45…`, relé de seguridad
  `2:da2c40a9…`;
- `entrada_red_documento` de los cuatro, idéntica (hash del JSON entero, de `ramas`, de
  `actuadores` y los `avisos`);
- 7 escenarios del banco con la MISMA huella, claves del resultado y del `resumen` y `eventos`:
  en directo marcha `47d4dc2b…`, seta `9eece16b…`, caída de red `7d30cac0…`, atasco parcial
  `790b11bd…`; por variador seta `c64baeaa…`, corte de fase `057ccaee…` y cajas con seta `39d34fb5…`.

`COSIM_EPOCH` sigue en 6: `acoples.py` entra a `ARCHIVOS` de `test_cosim_epoch.py` (decide el
resultado) y sólo cambia la huella (`5878df434dc6a50c` → `da527a5307f6c246`).
`tests/data/carril_v81_golden.json` sin cambios; sin bump de `GEOM_CACHE_EPOCH` ni de versiones de
comandos (el carril no es un executor de escena); ninguna tool MCP nueva. Sin aviso del ERC que
compare con la regla de la colocación (fuera, decisión de la revisión).

### F3 — El entregable de una extensión como job

**D6.** `fachada.entregable_documento(extraer, componer, *, tipo, asincrono=False)`, en
`SUPERFICIE` (agregar: `CONTRATO_EXTENSIONES` sigue en 1). Es `_job_entregable` con un `trabajo`
de dos fases: bajo `STATE_LOCK`, `_mismo_proyecto` y `extraer(doc)`; fuera de todo lock,
`componer(datos) -> (bytes, media_type, nombre)` y la `Response` con `Content-Disposition:
attachment; filename="<nombre>"` (la forma de las rutas del núcleo, que `_job_entregable` lee para
el `nombre` del recibo). Sin cola nueva ni nada de `common` abierto a las extensiones.
`CommandError`/`DocumentError` de CUALQUIERA de las dos fases → 400 con su texto (en el job,
`http_status` 400 y el mismo texto); una `HTTPException` propia pasa tal cual. Decisión a vetar: un
`nombre` que no cabe en la cabecera (vacío, con comillas o saltos, fuera de latin-1) es error de la
extensión (`ValueError`, 500), no se recorta: el recibo diría otro nombre que el pedido. La guardia
del documento no aplica (es una lectura, como las del núcleo).

**D13 del job.** La extensión falsa suma `GET /api/prueba/informe.txt` (extrae los nombres de las
piezas, compone un texto; modelo vacío → `CommandError`) y la tool `prueba_informe(path)` con
`pedir_entregable`. Sube lo que la extensión publica: `test_extensiones.py` (92 tools por stdio, las
dos al final) y `test_extensiones_coherencia.py` (la tool y la ruta en `/api/extensiones`).
`tests/test_extensiones_entregable_job.py`: en directo el archivo con su nombre; con `?async=true`,
202, `GET /api/jobs/{id}` con `{archivo, bytes, tipo, nombre}` y el archivo se baja igual; otro
proyecto abierto mientras espera → 409 sin llamar a `extraer` ni `componer`; `componer` con
`STATE_LOCK` libre en directo y como job (el lock de la fachada parcheado por un vigía que cuenta,
más otro hilo que lo toma sin esperar) y `extraer` bajo el lock; error de dominio 400 al extraer y
al componer; una `HTTPException` 422 pasa en directo y en el job; la tool guarda el archivo cuando
el job llega a tiempo y, con `APOLO_MCP_WAIT_S = 0`, da el recibo y `get_job` lo guarda en el
`path` pedido. Trampa: el test importa `apolo.mcp_server` ANTES de cargar la extensión (al
importarse registra en su `mcp` las tools de las cargadas y las dejaría para el golden). Golden
MCP sin cambios; `api/` no está en ninguna huella de época.

### F4 — Cifras eléctricas en el resultado

**D7, modelos.** `Motor` publica `U_V`: la U que recibe su `paso` (la media de las tensiones de
línea vivas en sus bornes; 0 con menos de dos fases; tras un variador, la de su salida). Las
protecciones (`Itm`, `Guardamotor`, `ReleTermico`, `Fusible`) comparten
`protecciones.CorrienteDeDisparo`: `I_disparo_A` NO existe hasta el primer disparo; en el paso del
disparo vale la mayor corriente de sus polos, se retiene, y al rearmar (o reponer todos los
cartuchos) queda en 0.0 sin desaparecer, como `averia` queda en «». Con la falla `abierto` es la
del último paso cerrado. El `Diferencial` usa la misma mezcla con otra señal,
`I_residual_disparo_mA` (la RESIDUAL con que disparó), y su disparo sale en `electrico` con
`I_residual_mA` (revisión de la sesión principal: un RCCB dispara por la residual; publicar la de
fase haría decir a una memoria que un 30 mA disparó con 3,2 A). `cosim/tipos.py` tipa las dos
(número) para `set_scenario`.

**D7, medida.** `services/medidas_electricas.py` (216 líneas): `referencias(doc)` (la U nominal de
la red que alimenta cada motor, su In en su conexión y `tras_variador`, con las llegadas de
`redes.analizar`) y `resumen_electrico(res, refs)`, puro. La API arma las referencias en la toma
del snapshot (`_correr` y la sesión viva vuelta escenario) y `resultado_compacto` guarda
`electrico` sólo con motores o un disparo. `cifras(resultado, motores)` es la lectura: sin
`electrico` y con motores devuelve el aviso «córrelo de nuevo» (D8). Decisiones de la medida, a
vetar: el régimen es la mediana del último 0,5 s alimentado **con I < 1,5·In** (si no, un motor
trabado antes de que dispare su protección contaba como régimen); un motor que nunca recibió
tensión lleva `alimentado: false`; `tras_variador` si ALGUNA fase le llega de un variador (un
bypass mixto no da ΔU); la causa de un fusible, que no publica `causa`, es «fusión» o «avería».

**Cuenta a mano** (arranque directo del banco, `faja_directo`, red 220 V 60 Hz, Icc 10 kA, X/R 1,5;
`test_la_caida_del_arranque_directo_contra_la_cuenta_a_mano`). Por fase: la red, 0,0070456 + j
0,0105685 Ω; tres tramos de 2,5 mm² × 1 m a 70 °C, 3 × 0,00954807 Ω (7,98 Ω/km · 1,1965) y
3 × j 0,00008 Ω; tres contactos cerrados, 3 × R_ON = 0,03 Ω; el hilo de -W1, 1,5 mm² × 6 m,
0,0954807 + j 0,00048 Ω. Total **Z = 0,1611705 + j 0,0112885 Ω**.

| | a mano | simulación (500 Hz) | ΔU |
|---|---|---|---|
| rotor bloqueado (1.er paso): S = √3·230·5,5·3,18 = 6967,5 VA a FP 0,4, estampada a 220 V (Z_Y = 220²/S*) | 217,611 V | 217,610 V | 1,09 % |
| mínimo del arranque (girando: potencia constante con la U·I del paso anterior, cos φ 0,76) | 216,373 V | 216,373 V | **1,65 %** |
| régimen (I = 1,844 A, cos φ 0,76) | 219,585 V | 219,585 V | **0,19 %** |

Las diferencias son < 0,5 mV (la carga de la fuente de 24 V en L1–L2). A 50 Hz, lo de siempre,
el arranque de este motor (~70 ms) cae entre muestras: `U_min_arranque_V` = 217,185 V (1,28 %),
del lado alto; `medicion` declara la resolución y con `trazas.analogicas_hz: 500` se ve cada paso.
Disparos: atasco de 500 N·m, -Q2 a 15,468 s con 16,135 A (la del hilo -W1.1; el modelo del motor
dice 16,150) y «térmico»; corto en bornes del motor, -Q2 a 1,0 s, 679,8 A, «magnético»; corto en
la entrada de la fuente de 24 V, -F1, 2298 A, «magnético»; -Q2 `abierto`, 1,844 A, «avería». Por
variador: `{"tras_variador": true}`, sin ΔU.

**D8, evidencia** (la condición de la revisión), contra `1ff0679` exportado aparte, con un banco
ad hoc: 11 escenarios —en directo marcha, seta, caída de red, atasco que dispara, atasco parcial,
corto en el motor, corto en la fuente de 24 V y guardamotor `abierto`; por variador seta, corte de
fase y cajas con seta— dan trazas discretas y analógicas SIN `-M1.U_V` ni `*.I_disparo_A`,
eventos, finales, claves del resultado y del `resumen` y veredicto aserción por aserción
IDÉNTICOS; cada huella cambia sólo por las trazas nuevas (corte de fase `057ccaee` → `f7557715`,
marcha en directo `dc083266` → `060499a1`). Con el cambio del diferencial (revisión), los dos
tableros de `test_cosim_diferencial.py` con su corto de 1 kΩ a PE (1F con el de 30 mA y 3F+N
con el 4P), rearmados a 0,24 s, dan las mismas señales paso a paso sin `I_residual_disparo_mA`
(que retiene 220,0 y 219,3 mA y vuelve a 0.0 al rearmar). `COSIM_EPOCH` sigue en 6: la huella de
`test_cosim_epoch.py` pasa de `da527a5307f6c246` a `ae1f815f83441ea9`. `medidas_electricas.py`
no entra a `ARCHIVOS` (como `aire_resultado.py`: no decide el resultado ni el veredicto, sólo lo
que se guarda de él). `test_cosim_vivo.py` verde (vivo y lote con la misma huella). La UI lee la
unidad por sufijo (`_V`, `_A`): sin cambios, sin `npm test`.

### F6 — El bus entrega la sesión abierta y el `inicio` dice las variables

**D11.** `vivo_bus.Bus` guarda una `_Memoria` de la sesión: el texto de su `inicio` (ya con
`,"tarde":true}` al final, sin re-serializar), cada `senales` en orden y el último valor de cada
texto con la `t` del último `textos`. La escribe `difundir_json` bajo el MISMO lock que elige los
destinos, antes de ver si hay suscriptores. `suscribir` llena la cola de la suscripción nueva con la
repetición (`inicio`, `senales`, y un `textos` sólo si hay alguno) bajo el lock del bus y
registra la suscripción en esa misma sección crítica: un fotograma o un JSON que el loop difunde
después cae detrás. Es el único anidado bus → suscripción, y la suscripción todavía no es de nadie.
Decisión de la implementación: `difundir_json(msg, texto, sesion=None)` recibe la sesión que
emite (`SesionViva.json` pasa `self`). El `inicio` sale del worker mientras la API todavía espera
a `ProcesoVivo` y `BUS.abrir` llega después, así que la memoria no puede atarse a `abrir`. La
memoria es de la sesión que la escribió: un `inicio` la reemplaza; el `fin`, las `senales` o los
`textos` de OTRA sesión (la reemplazada que se apaga después de que la nueva mandó su tabla) no la
tocan; `abrir` de otra sesión y `cerrar` de la suya la olvidan. El `textos` sintetizado lleva
también `tarde: true` (lo distingue del vivo; agregar claves no sube `version`). La cola de la
persona no cambia (mismo `put_nowait`). `vivo_bus.py` sigue sin importar `apolo.state`.

**D12.** `services/variables_plc.py` (puro, sin documento ni locks): `rutas_de_senal(compilado)`
replica `PLC.variables()` sin correr el PLC (las entradas sin bloque de `rutas["<global>"]` y de
cada PROGRAM como `Prog.x`, en su orden). Cada ruta lleva `tipo` y `escribible` de
`Compilado.simbolos`, que es la tabla de `simbolos.escritura`; con eso `plcs(programas)` arma
`[{designacion, variables}]`, un PLC por designación (el último, como `Corrida`). `_inicio` la suma
como `plcs` sólo si hay alguna. Decisión: un bloque (`Main.t1`) y sus miembros NO salen, porque no
son señal del fotograma (D12 dice «la misma escritura que la señal»). Un ARRAY sale con su tipo
`ARRAY[a..b] OF T` y `escribible` por elemento; su señal viaja en `textos` (lista). Con un PLC
externo la tabla sale del programa que el núcleo compiló, el mismo con que la agenda valida lo que
se le escribe. `cosim/**` y `plc/**` no se tocaron: la huella de `test_cosim_epoch.py` no cambia.

**D13 del bus.** `tests/ext_prueba/suscriptor.py` arma la tabla con lo que recibe (`senales`,
`textos`, `variables` de `plcs`, `tarde`) y lee cada fotograma con la tabla de ese momento con
`leer_fotograma` (`leidos`; `desfasados` si el número de señales no coincide).
`tests/test_vivo_bus_tarde.py`, sin worker: el orden de la repetición y lo guardado sin nadie
suscrito; la sesión reemplazada no borra la nueva; tras el `fin` o el `cerrar`, nada; 40
suscriptores que llegan mientras otro hilo publica `senales` y fotogramas que dicen cuántas señales
traen, y ninguno ve un fotograma antes que su tabla; la cola de `SesionViva` igual con y sin
suscriptor tardío; con `STATE_LOCK` parchado para fallar. Con el worker (faja con variador y PLC):
el suscriptor llega tras 10 fotogramas y un `textos`, recibe el `inicio` de la persona más
`tarde`, ningún fotograma desfasado, la tabla y los textos finales iguales a los del WebSocket y,
tras la repetición, el mismo final (JSON y fotogramas); `plcs` de -K1 con `Main.cuenta` escribible,
`foto` (`AT %IX0.0`) no y sin `Main.flanco`; tras el `fin` nada, y la sesión siguiente repite sólo
la suya. `tests/test_variables_plc.py`: rutas = `PLC.variables()`; globales, ARRAY, `AT %IX`/`%QX`,
CONSTANT global y del PROGRAM, dos PROGRAM y un FB propio y uno estándar; `escribible` = lo que
acepta `PLC.escribir`; sin PLC, sin clave.
