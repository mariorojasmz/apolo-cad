---
estado: en curso
nota: contrato de Claude derivado de pedidos de extensiones, con el aval del titular (2026-10-24: «procede según tu criterio»); medido sobre `97d93c3`; dos carriles F1 ∥ F2 → F3 ∥ F4 → F5 ∥ F6; F2 implementada en su rama (sin mergear; `simbolo`, `acoplado_a`, `FUERA_DE_FIRMA`); sigue F1 y después F3 ∥ F4
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
