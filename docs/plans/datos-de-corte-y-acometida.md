---
estado: en curso
nota: contrato derivado de un plan aprobado por el titular el 2026-10-24 (A5–A6); F1a (datos de ficha, completitud, `T_max_C`) y F1b (el diferencial: modelo por fasores, 8 refs con sus cifras en `a_confirmar` porque las fichas no se pudieron leer, regla del ERC como criterio de diseño) mergeadas; sigue F1c (la acometida: esquema TN/TT/IT y `RA_ohm` en la co-simulación, COSIM_EPOCH 4 → 5)
descripcion: cada protección del catálogo dice cuánto corta y a qué temperatura trabaja, con su fuente; la acometida dice su esquema de tierra; el interruptor diferencial entra al catálogo y dispara en la prueba virtual
---

# La ficha dice cuánto corta cada protección, la acometida dice su esquema de tierra y el diferencial dispara en la prueba virtual

## Estado y origen

- Un plan de entregables eléctricos aprobado por el titular el 2026-10-24 pidió estos datos al
  núcleo: los ajustes A5 (datos de ficha y de acometida) y A6 (`T_max_C` por familia). Este plan
  cubre sólo lo GENÉRICO del núcleo (catálogo, ficha, co-simulación); lo que se calcula con esos
  datos (cortocircuito, poder de corte frente a Icc, coordinación, contactos indirectos) es de la
  memoria eléctrica, fuera del núcleo ([V8](V8-maquina-viva.md) § V8.6).
- Respuesta provisoria aprobada: el diferencial entra al catálogo del núcleo, genérico, con su
  modelo de co-simulación.
- Plan hermano del mismo origen: [puntos de extensión de entregables](puntos-de-extension-entregables.md)
  (su «Lo que NO hace» manda los datos de ficha a un plan propio: éste).
- Contrato redactado tras una medición de sólo lectura (sub-agente) y revisado por la sesión
  principal: decisiones de la revisión al final de § Decisiones.

## Lo que hay hoy

Rutas relativas a `core/apolo/`, medidas sobre `fc53cff`.

- **Poder de corte (A5):**
  - Los 8 ITM traen sólo `Icn_kA: 6` (IEC 60898-1), en `specs` y en `modelo`
    (`library/data/121_proteccion_electrica.yaml:70,78` … `:172,176`). Ninguno trae `Icu`/`Ics` de
    IEC 60947-2, y nadie lee `Icn_kA` en el código (grep: cero usos).
  - Guardamotores: `Icu`/`Ics` 0 de 5 (`:184-233`).
  - Seccionador: `Icw` y corriente condicional de cortocircuito 0 de 2 (`:39,50,58,62`).
  - Fusible: el portafusible `BORNE-FUS-5X20` no dice el poder de corte del cartucho ni su
    tensión (`125_conexion_electrica.yaml:80,90`).
- **Fuente y «a confirmar»:** el bloque `electrico:` no los admite (`library/electrico/ficha.py:56-57`,
  `_CLAVES`); el neumático sí (`library/neumatica/ficha.py:31`, más la completitud en
  `ficha_tipos.REQUERIDOS`). Lo único con `fuente` en lo eléctrico es `tablero.bornes`.
  `specs.cotas_verificadas: false` en todas las refs eléctricas habla de la ENVOLVENTE, no de las
  cifras eléctricas (`120_alimentacion_electrica.yaml:8-9`).
- **Acometida:**
  - Las 4 redes traen `Icc_kA` y `X_R` como números en `modelo` (`120_…yaml:56,77,95,114`). Por
    eso **ya son ajustes**: `validar_ajustes` acepta toda clave numérica que la ficha declara
    (`library/electrico/ajustes.py:56-58`) y el modelo `Red` lee primero el ajuste
    (`cosim/modelos/base.py:73`; `cosim/modelos/alimentacion.py:46-47`).
  - Hueco: con un `Icc_kA` ajustado, el resultado sigue diciendo «Icc SUPUESTA en el catálogo»
    (`alimentacion.py:54` mira la ficha, no el ajuste).
  - `esquema: TN` sale en 2 de 4 redes (`:77`, `:114`). La de 220 V 3F sin neutro (`:56`, con la
    nota de `:57`) y la de 2F (`:95`) no tienen esquema de tierra.
  - `esquema` se acepta como ajuste sólo en esas dos refs, como texto LIBRE (`ajustes.py:82`), y
    la co-simulación **no lee el ajuste**: `services/cosim_red.py:144` hace
    `pe_a_neutro = d.modelo.get("esquema") == "TN"` sobre la ficha.
  - `RA_ohm` no existe en ningún lado.
- **Tierra en la red de potencia:** el PE sólo entra a la potencia con `pe_a_neutro` (TN), como
  nodo de tierra (`cosim/red/topologia.py:116,148`). Sin TN, un corto a PE se rechaza
  (`cosim/fallas.py:66-67`).
- **Diferencial:** no hay `tipo` para él (`ficha.py:44-46`, `TIPOS_MODELO`) ni refs. Las
  protecciones reciben MÓDULOS de corriente por polo: `tablero.py:334-336` devuelve
  `abs(res.corriente(rid))` y `tablero.py:347` hace `m.paso(dt, {"I_A": [...]})`. Un diferencial
  necesita los FASORES para sumarlos. La red sí los tiene (`cosim/red/resultado_potencia.py`,
  `corriente(rama_id)` complejo).
- **`T_max_C` (A6):** V8.5 no lo trajo. F3 de [V8.5](V8.5-tablero-3d.md) está bloqueada
  (nota del frontmatter); A11 lo pedía y su § 5 midió «0 de 46». Hoy es **0 de 53** refs de
  tablero (montaje `din`/`puerta`/`placa`: 34 + 12 + 7). Grep de `T_max` en `core/`: cero.
- **Vigencia:**
  - `Dispositivo.modelo = dict(ficha.modelo)` (`library/electrico/modelo.py:235`) entra a la
    firma del documento (`services/escenarios.py:38-48`). Una clave nueva en el `modelo` de una
    ref vence los resultados de cada documento que la usa.
  - `COSIM_EPOCH = 4` (`cosim/__init__.py:21`). Su huella cubre `cosim/**` y
    `services/cosim_red.py` (`tests/test_cosim_epoch.py`, `ARCHIVOS`).
- **Gates que tocan refs nuevas:**
  - `len(CATALOG) == 420` en `tests/test_catalog_datadriven.py:146`,
    `tests/test_catalogo_electrico.py:69` y `tests/test_extensiones.py:73`;
  - la categoría `proteccion_electrica` exacta (`tests/test_catalogo_electrico.py:62-64`) y la
    honestidad de cada ref nueva (`:72-79`);
  - `TIPOS_MODELO == MODELOS` (`tests/test_cosim_modelos_catalogo.py:36-37`);
  - todo modelo salvo `red` y `motor` con `FALLAS` (`tests/test_cosim_fallas_modelos.py:36`);
  - un `tipo` sin clase de colocación cae en «control» (`library/electrico/colocacion_modelo.py:12-14,157`);
  - los nombres por tipo de la UI viva (`ui/src/vivo/arbolSenales.ts:18-23`, `ui/src/vivo/fallas.ts:46-50,62`).

## Lo que se revisó antes de escribir esto

- **La firma decide dónde van los datos.** Si `Icu`, `T_max_C` o `fuente` entran a `modelo`,
  todos los escenarios guardados con ITM o guardamotor quedan vencidos (AMARILLO) por un dato que
  la co-simulación no usa. Un campo nuevo de `FichaElectrica` no llega a `Dispositivo`
  (`modelo.py:231-239` copia campo por campo), así que no toca la firma.
- **El poder de corte depende de la tensión.** En las fichas de ITM de las líneas de referencia,
  la Icu a 230 V es del orden del doble de la de 400 V. Un solo número sería pesimista ×2 en la
  red de 220 V, o no se sabría a qué tensión es.
- **`validar_ajustes` sólo acepta lo que la ficha declara.** Para que la red de 220 V sin
  esquema acepte `esquema` o `RA_ohm` como ajuste hay dos caminos: inventar un valor en su ficha
  (prohibido) o darle ajustes OPCIONALES por `tipo`. Se elige éste.
- **`validar_ajustes` corre también al cargar** (`commands/electrico_eval.py:102`; la carga
  suprime la entrada rota). Endurecer `esquema` no puede romper un log con «TN».
- **El diferencial se puede modelar con lo que la red ya tiene.**
  - En TN el PE es el nodo de tierra, y la falla `corto` de [cosim-fallas](cosim-fallas.md) de
    una fase a PE vuelve por tierra a la estrella de la fuente (el Norton de la red), no por el N
    que pasa por el diferencial. La suma fasorial de sus polos es la corriente de falla.
  - En TT basta una estampa PE → tierra de 1/RA.
  - En IT la estrella aislada no da corriente al primer defecto: hoy el PE queda fuera, y está
    bien.
  - La conductancia mínima de cada nodo (0,1 µS, `cosim/red/mna.py:27`) da ≈ 22 µA a 220 V,
    lejos de 15 mA.
- **`redes.Llegada.via`** (`library/electrico/redes.py:234-257`) ya lista los caminos que
  atraviesa cada llegada. Una regla del ERC puede ver qué diferencial alimenta a un variador sin
  tocar `redes.py`.
- La familia de bornes por `lado` (línea arriba, carga abajo) ya cubre un aparato de polos
  (`library/electrico/bornes_pos.py`, punto 5): el diferencial no necesita patrón propio.

## Decisiones (para vetar)

- **D1 — Los datos de ficha van en un bloque nuevo, `electrico.datos`, fuera de `modelo`.**
  `modelo` es lo que EMULA la co-simulación (V8.3 D7). Estos datos los lee quien verifica:
  memoria, ERC, una extensión. Fuera de `modelo` no entran a la firma (no vencen escenarios) ni
  son ajustes. Lo valida un módulo nuevo y puro, `library/electrico/ficha_datos.py`, como
  `ficha_tablero.py`; `ficha.py` (390 líneas) sólo lo engancha. `Icn_kA` se queda donde está
  (moverlo vencería firmas).
- **D2 — Lo que depende de la tensión es un mapa `{U_V: valor}`** (`Icu_kA: {240: …, 415: …}`,
  con las tensiones que da la ficha). `ficha_datos.a_tension(mapa, U_V)` devuelve el valor de la
  MENOR tensión tabulada ≥ U_V (conservador). Si ninguna alcanza, `None`: «sin dato a esa
  tensión», nunca una extrapolación.
- **D3 — Qué datos pide cada tipo** (`ficha_datos.REQUERIDOS`, el número cita su norma en el
  comentario del YAML):

  | tipo | datos | norma |
  |---|---|---|
  | `itm` | `Icu_kA`, `Ics_kA` (mapas por tensión) | IEC 60947-2 (la `Icn_kA` de 60898-1 sigue en `modelo`) |
  | `guardamotor` | `Icu_kA`, `Ics_kA` (mapas) | IEC 60947-2 / IEC 60947-4-1 |
  | `seccionador` | `Icw_kA` + `Icw_t_s`; `Iq_kA` + `Iq_con` (texto: la protección con que se ensayó, p. ej. «fusible gG 25 A») | IEC 60947-3 |
  | `fusible` | `cartucho_U_V`, `cartucho_Icn_A`, `cartucho_Icn_x_In` (poder de corte del cartucho = máx(A, x·In)) | IEC 60127-2 |
  | `diferencial` | `Inc_kA` + `Inc_con`; `Im_A` | IEC 61008-1 |
  | toda ref de tablero (`montaje` din, puerta o placa) | `T_max_C` | la ficha del fabricante |

  Además se valida: números > 0; `Ics ≤ Icu` a la misma tensión; `Iq_con`/`Inc_con` obligatorios
  si viene su cifra; una clave que el tipo no pide es error con la parecida (la regla de
  `ficha.py`).
- **D4 — `electrico.fuente` y `electrico.a_confirmar`, como el bloque neumático.**
  - `fuente` (texto: el documento del fabricante o la norma) es obligatoria si hay `datos` o
    `a_confirmar`.
  - `a_confirmar` es una lista de claves de `datos` o de `modelo`. Nombra una clave con valor
    estimado («criterio de diseño», «del orden de») o una clave SIN valor (el dato hace falta y no
    hay fuente). **Nunca un valor inventado.**
  - **Completitud al cargar, con error:** cada dato de `REQUERIDOS` está o se nombra en
    `a_confirmar`; si no, el YAML no carga, con el mensaje de qué completar.
  - `specs.cotas_verificadas` no cambia de significado (envolvente). Cada ref sigue trayéndolo, y
    las nuevas en `false`.
  - Línea de referencia: marcas comunes (Schneider, ABB, Siemens, Eaton). Una ref de catálogo es
    un EJEMPLO que quien fabrica reemplaza por la local (`library/CLAUDE.md` § Catálogo).
- **D5 — `T_max_C` por familia** (ancla YAML de la familia) en las 53 refs de tablero de hoy y en
  las 8 nuevas. Es la temperatura máxima del aire alrededor del aparato en servicio, según su
  ficha. La desclasificación por temperatura queda fuera: la decide F3 de V8.5 con este dato.
- **D6 — La red acepta como ajustes `Icc_kA`, `X_R`, `esquema` y `RA_ohm`, con lo de hoy como
  default.**
  - `Icc_kA` y `X_R` ya lo son (medido): sólo un test que lo ata. El modelo `Red` deja de decir
    «SUPUESTA en el catálogo» cuando el `Icc_kA` viene de un ajuste.
  - `esquema` y `RA_ohm` entran como AJUSTES OPCIONALES de `tipo: red`
    (`ajustes.OPCIONALES = {"red": …}`): se aceptan aunque la ficha no los declare.
  - `esquema` va en {`TN-S`, `TN-C-S`, `TT`, `IT`}, más `TN` heredado («TN sin precisar», el de
    hoy: los logs con «TN» siguen valiendo; se normaliza a mayúsculas).
  - `RA_ohm` > 0 sólo con `TT` (ajustado o de ficha); con otro esquema es error.
  - El catálogo de redes NO cambia su `modelo`, para no vencer firmas: el «TN» queda «TN». Cada
    red suma `fuente` («criterio de diseño: …») y `a_confirmar` (`Icc_kA`, `X_R` y `esquema`
    donde falta).
  - El `esquema` de una ficha se valida con la misma lista.
- **D7 — La co-simulación lee el esquema del AJUSTE primero, y luego de la ficha.** Un helper puro
  (`library/electrico/acometida.py::esquema_de(modelo, ajustes)`) lo usa `cosim_red`:
  - `TN`, `TN-S` o `TN-C-S`: el PE es la tierra de la red (`pe_a_neutro`, como hoy). Para el
    tablero, TN-C-S y TN-S son iguales: el PEN se separa en el origen.
  - `TT` con `RA_ohm`: el PE entra a la potencia como NODO unido a tierra por una estampa de
    1/RA (`FuenteRed.R_tierra_ohm`, campo opcional: `entrada.FORMATO` sigue en 1). Hipótesis
    declarada: «RA_ohm es la resistencia del lazo de tierra, RA + RB; con sólo RA es optimista».
  - `TT` sin `RA_ohm`, o `IT`: el PE queda fuera de la potencia, como hoy. El rechazo de un
    `corto` a PE lo dice («en TT declara `RA_ohm`»; «en IT el primer defecto a masa no da
    corriente de falla»).
  - Sin esquema: exactamente lo de hoy.
- **D8 — El diferencial: `tipo: diferencial` y su modelo `cosim/modelos/diferencial.py`.**
  - **Ficha:** `modelo: {tipo: diferencial, In_A, IDn_mA, clase_residual: A|B, polos: 2|4}`.
    `clase_residual` se valida en `ficha.py` como `curva` (opciones `AC`, `A`, `F`, `B`).
  - **Lo que ve:** la corriente residual I_Δ = |Σ fasores de sus polos|, con los caminos
    `proteccion` de línea a carga, N incluido. Un polo sin cablear (N de un 4P en red sin
    neutro) no entra. El tablero lo indexa aparte de las protecciones térmicas y le pasa los
    fasores (`res.corriente(rid)`, sin `abs`). Las demás protecciones siguen recibiendo módulos:
    sin cambio de resultados.
  - **Disparo** (IEC 61008-1, tipo general): no dispara a ½ IΔn; dispara a IΔn en ≤ 0,3 s, a
    2 IΔn en ≤ 0,15 s y a 5 IΔn en ≤ 0,04 s. Se fija k = 0,75 (criterio de diseño: entre ½ y 1)
    y el tiempo de disparo en el medio de cada banda (0,15 / 0,075 / 0,02 s), sostenido por
    encima de k. Si baja, el contador vuelve a cero (criterio de diseño). Determinista con Δt
    de 2 ms.
  - **Acciones:** `rearmar`, `abrir`, `cerrar`. Rearmar con la falla presente vuelve a disparar
    en el paso siguiente.
  - **Fallas:** `no_dispara` y `abierto`, con su gemelo sano.
  - **Señales:** `-F1.cerrado`, `-F1.disparado`, `-F1.I_residual_mA`, `-F1.causa` («diferencial»).
  - **No protege de sobrecorriente** (es un RCCB): se compone con un ITM.
  - **A y B dan lo mismo en la co-simulación**, porque la red es fasorial y senoidal. Va como
    hipótesis («la componente continua lisa que ciega a un tipo A no se simula»), y el ERC lo
    señala (D10).
  - Lo que la co-simulación **no** sabe: la fuga natural o capacitiva (filtros EMC, cables
    largos). El diferencial ve sólo las fallas declaradas.
- **D9 — 8 refs nuevas en `121_proteccion_electrica.yaml`** (categoría `proteccion_electrica`,
  `funcion: F`, `montaje: din`):
  - `DIF-2P-25A-30MA-A`, `DIF-2P-25A-300MA-A`, `DIF-2P-25A-30MA-B`, `DIF-2P-25A-300MA-B`,
    `DIF-4P-40A-30MA-A`, `DIF-4P-40A-300MA-A`, `DIF-4P-40A-30MA-B`, `DIF-4P-40A-300MA-B`;
  - bornes `1`–`2` (`1`–`6` en el 4P) más `N1`/`N2`, como el ITM 1P+N, y una nota para la red 2F
    (el polo N lleva la segunda fase);
  - `specs` con `linea_referencia` «orden de …», `cotas_verificadas: false` y `cost` referencial;
  - `datos`, `fuente` y `a_confirmar` por D3–D4;
  - clase de colocación «alimentacion» (`colocacion_modelo._CLASE_POR_TIPO`).
- **D10 — Regla del ERC «tipo de diferencial»:** un variador alimentado a través de un
  diferencial `AC` o `A` (por `Llegada.via`) da AVISO: un variador trifásico puede dar corriente
  de falla continua lisa y pide tipo B. Cita: IEC 60364-5-53 §531.3.3 si quien implementa la
  confirma con el texto; si no, «criterio de diseño».
- **D11 — Vigencia, una decisión por cosa:**
  - **`GEOM_CACHE_EPOCH`: no.** No cambia la geometría de ninguna ref: los bloques `electrico`
    no los lee el builder (`120_…yaml:24-25`; `library/CLAUDE.md` § bloque `tablero:`), y una
    ref nueva no puede estar en ninguna caché.
  - **Versiones de comandos: no.** `add_device` no cambia geometría; `validar_ajustes` es un
    helper.
  - **Firma del documento: no se mueve** en F1a ni en F1b (los datos van fuera de `modelo`). En
    F1c, quien ponga un ajuste nuevo cambia su log, y eso vence sólo ese documento.
  - **`COSIM_EPOCH`:** F1a no toca `ARCHIVOS`. F1b sólo actualiza la huella «sin subir» (tipo
    nuevo, ningún documento existente lo usa, el banco da la MISMA huella). **F1c sube a 5**: con
    el MISMO documento, un `esquema` ajustado que hoy se ignora pasaría a leerse, y la hipótesis
    de Icc cambia de texto. Todo resultado guardado queda «vencido» (AMARILLO) con su motivo,
    hasta re-correrlo.
- **D12 — `MODULOS` suma `apolo.library.electrico.ficha_datos`** (`REQUERIDOS`, `a_tension`): una
  extensión lee los datos por el contrato y no por fuera. Agregar no sube `CONTRATO_EXTENSIONES`.
- **D13 — Sin formato nuevo:** `.apolo`, log, SQLite y entrada plana de la red (`FORMATO = 1`)
  quedan igual. Ninguna tool MCP nueva; el golden no cambia. `GET /api/catalog` suma `datos`,
  `fuente` y `a_confirmar` a la ficha que ya publica (`ficha_payload`).

Decisiones de la revisión (sesión principal, 2026-10-24): la F1 se parte en tres; `COSIM_EPOCH`
sube en F1c; la completitud es error al cargar (como la neumática); D10 se queda con la cita
condicionada; `cotas_verificadas` conserva su significado y lo eléctrico se declara con `fuente` +
`a_confirmar`.

## Alternativas descartadas

- **Los datos dentro de `modelo`:** mezcla lo que se emula con lo que se verifica, y vence las
  firmas de casi todo escenario guardado por un dato que la co-simulación no lee.
- **Los datos en `specs`:** el loader vuelca ahí cualquier clave sin validar. No habría
  completitud, ni `a_confirmar` que nombre una clave, ni error por una clave mal escrita.
- **Un solo `Icu_kA` (a 400 V):** pesimista ×2 en la red de 220 V, y la ficha no dice a qué
  tensión es cada número si no se escribe.
- **Migrar «TN» a «TN-S» en el catálogo:** inventaría la variante, y vencería firmas.
- **Esquema TN por defecto en las redes que no lo traen:** cambiaría resultados y diría algo que
  nadie midió.
- **Un RCBO (diferencial + ITM, IEC 61009-1) en vez de un RCCB:** duplicaría el ITM. Se compone
  con el que ya hay.
- **Simular la componente continua (tipo A frente a B):** la red es fasorial. Se señala en el ERC
  (D10), no se finge en la co-simulación.
- **Modelar la fuga capacitiva (variadores, cables):** no hay datos de catálogo; sería una cifra
  inventada.
- **Completitud con aviso en vez de error:** un aviso que nadie lee deja huecos silenciosos. El
  neumático ya valida con error al cargar.

## Fases

La F1 pedida no entra en una sesión de agente de 55–70 min: sólo la recolección de cifras con
fuente para 61 refs ya llena una, y el diferencial toca modelo, tablero, refs, ERC y UI. Se parte
en tres, en serie: F1a → F1b → F1c.

- **F1a — Datos de ficha y `T_max_C`** (`library/electrico/ficha_datos.py` nuevo, `ficha.py`
  —`_CLAVES`, campos de `FichaElectrica`, `ficha_payload`—, los YAML eléctricos,
  `extensiones_api.py` y sus tests · M · ≈ 60–65 min · sin dependencias): D1–D5, D12 y la parte
  de catálogo de D6 (`fuente` y `a_confirmar` de las redes).
  - Una cifra entra con su fuente (documento del fabricante o norma) o la clave va a
    `a_confirmar` SIN valor. No más de ≈ 20 min buscando fichas: lo que no se verifique, a
    `a_confirmar`.
  - **Se verifica:** suite completa y `ruff` limpio. Tests nuevos: cada rechazo de `ficha_datos`
    (clave que el tipo no pide, `Ics > Icu`, mapa mal formado, `Iq` sin `Iq_con`, falta `fuente`,
    completitud); `a_tension` (menor tensión ≥ U, `None` arriba); las 53 refs de tablero con
    `T_max_C` o con él en `a_confirmar`; las firmas de documento del banco iguales antes y
    después; `ficha_payload` con los bloques nuevos; el gate de `MODULOS`.
- **F1b — El diferencial** (`cosim/modelos/diferencial.py` nuevo, `cosim/modelos/__init__.py`,
  `cosim/tablero.py`, `library/electrico/ficha.py` —tipo y `clase_residual`—,
  `colocacion_modelo.py`, `erc.py`, `121_proteccion_electrica.yaml`, `ui/src/vivo/arbolSenales.ts`
  y `fallas.ts`, los gates de conteo · M · ≈ 65 min · depende de F1a): D8–D10.
  - **Se verifica:** suite completa, `ruff`, `npm test` y `npm run build`. Tests nuevos: los
    tiempos de disparo dentro de las bandas de IEC 61008-1 y el no disparo a ½ IΔn; el gemelo
    sano de cada falla; en un tablero con `RED-1F-220V-60HZ` (TN), un `corto` de 1 kΩ de la fase
    aguas abajo a PE dispara el de 30 mA y no el ITM C2, y el de 300 mA no dispara; una carga
    3F+N equilibrada tras un 4P no dispara; la regla D10, verde y roja; las 8 refs honestas.
    Conteos 420 → 428 refs. Huella de `test_cosim_epoch.py` actualizada SIN subir, con los
    escenarios del banco dando la misma huella que en la base (bitácora).
- **F1c — La acometida en la co-simulación** (`library/electrico/acometida.py` nuevo,
  `ajustes.py`, `ficha.py`, `services/cosim_red.py`, `cosim/red/entrada.py`, `topologia.py`,
  `potencia.py`, `cosim/fallas.py`, `cosim/modelos/alimentacion.py`, `cosim/__init__.py` · S/M ·
  ≈ 50 min · depende de F1b para el caso TT): D6–D7 y el `COSIM_EPOCH` de D11.
  - **Se verifica:** suite completa y `ruff`. Tests nuevos: `Icc_kA` y `X_R` ajustados cambian la
    Zk, sin «SUPUESTA»; `esquema` fuera de la lista y `RA_ohm` sin TT son error con qué corregir;
    el «TN» heredado y un log con él regeneran igual; TN-S da la misma traza que TN; TT con
    `RA_ohm` = 100 Ω y un corto franco L1 → PE: el ITM C6 no dispara y el diferencial de 30 mA sí;
    IT y TT sin RA rechazan el corto a PE con su mensaje; sin esquema, el banco da la misma
    huella. `COSIM_EPOCH` 4 → 5 con su motivo en `cosim/__init__.py` y en `test_cosim_epoch.py`.

Al cerrar cada fase: conteos de «Estado actual» del CLAUDE.md raíz; una línea en
`library/CLAUDE.md` (bloque `electrico.datos` + completitud, F1a); una línea en `cosim/CLAUDE.md`
(residual por fasores en F1b; esquema y RA en F1c).

## Lo que este plan NO hace

- No calcula cortocircuito, ni compara Icu con Icc, ni coordina o hace selectividad: sólo da los
  datos.
- No desclasifica por temperatura ni calcula el calentamiento del tablero (V8.5 F3).
- No trae RCBO, diferenciales selectivos (tipo S) ni el botón de prueba.
- No modela fugas naturales ni la componente continua de una falla.
- No cambia el `modelo` de ninguna ref existente (sin vencer firmas), salvo que F1c valida el
  `esquema` de las fichas.
- No toca `tension.py` ni el ERC de tensiones.
- No suma tools MCP ni cambia el formato del `.apolo`, del log, de la SQLite o de la entrada de
  la red.

## Riesgos

| riesgo | mitigación |
|---|---|
| Pocas fichas verificables, mucho `a_confirmar` | es lo honesto: quien calcule lo arrastra como hipótesis y la ficha dice qué falta; tope de búsqueda en F1a |
| La completitud al cargar rechaza un YAML de extensión con un `itm` o `guardamotor` sin `datos` | lo ve la CI de la extensión contra la ref fijada del núcleo; el mensaje dice qué completar o qué poner en `a_confirmar` |
| `esquema` estricto frente a logs viejos | «TN» sigue valiendo y se normalizan las mayúsculas; antes de mergear F1c se verifica que ningún proyecto de referencia (38, 53 y el banco) tenga otro valor |
| Subir `COSIM_EPOCH` vence todos los resultados guardados | quedan AMARILLO con el motivo «el motor de la co-simulación cambió»; se re-corren |
| Dirección de los fasores en el diferencial | un test exige `de` = lado línea en todo camino `proteccion` de un diferencial, y el caso 3F+N equilibrado no dispara |
| Un 4P en la red 3F sin neutro o un 2P entre dos fases | va en la nota de la ref y en `a_confirmar` |
| Archivos al tope (`tablero.py` 426, `erc.py` 390, `potencia.py` 316) | el modelo va en un archivo propio y los datos en `ficha_datos.py`; ninguno pasa de 500 |

## Bitácora

### F1a — Datos de ficha y `T_max_C` (2026-10-24)

**Qué se hizo.**
- `library/electrico/ficha_datos.py` (nuevo, puro: sólo `referencias.sugerir`): `REQUERIDOS` por
  tipo (D3, con `diferencial` ya listado para la F1b), `T_MAX`, `requeridos(tipo, montaje)`,
  `permitidas(tipo)`, `a_tension(mapa, U_V)` (D2), `parse_datos` (validación + completitud, D4)
  y `payload`. `ficha.py` sólo lo engancha: `_CLAVES` suma `datos`, `fuente`, `a_confirmar`;
  `FichaElectrica` suma los tres campos; `ficha_payload` los publica (tensiones como texto, claves
  JSON). `fusionar` (familias) fusiona `datos` clave a clave, como `modelo`.
- Los YAML 120–125, 91 y 93: `datos`/`fuente`/`a_confirmar` en las 53 refs de tablero (ancla por
  familia: `&datos_itm`, `&datos_gm`, `&datos_secc`, `&datos_contactor`, `&datos_xb5`,
  `&datos_seta`) y en las 4 redes. Comentario de convención en la cabecera de 120 y 121.
- `extensiones_api.MODULOS` suma `apolo.library.electrico.ficha_datos` (`REQUERIDOS`,
  `a_tension`, `requeridos`), sin subir `CONTRATO_EXTENSIONES` (D12).
- Tests: `tests/test_ficha_datos.py` (32: cada rechazo, completitud por tipo y montaje, la red,
  la familia, `a_tension`, las 53 refs, las cifras verificadas, el payload, la firma y el gate de
  `MODULOS`); tres fixtures de tests viejos suman su `T_max_C` o `a_confirmar` (la completitud
  los alcanzaba: `test_catalogo_electrico.BUENO`, `test_catalogo_tablero._PUERTA`,
  `test_cosim_modelos_catalogo._cargar`, este último con `requeridos(tipo, montaje)`).

**Cifras que entraron, con su fuente** (fichas de producto de Schneider Electric descargadas el
2026-10-24 de schneider-electric.cn, salvo GV2ME06/08/10, fechadas 2022-12-29; leídas con
`pypdf`, nunca de memoria):

| ref | dato | ficha |
|---|---|---|
| ITM-C10-3P | Icu {240: 20, 415: 10} kA, Ics {240: 15, 415: 7,5} kA | iC60N A9F04310 |
| ITM-C6-2P | Icu {240: 20, 415: 10} kA, Ics {240: 15, 415: 7,5} kA | iC60N A9F04206 |
| ITM-C2-2P | Icu = Ics {240: 50, 415: 50} kA | iC60N A9F04202 |
| 8 ITM | `T_max_C` 70 (−35…70 °C) | las tres iC60N de arriba (y A9F04603/04703) |
| 5 guardamotores | Icu = Ics {240: 100, 415: 100} kA; `T_max_C` 60 (−20…60 °C) | GV2ME06, 07, 08, 10, 14 |
| SECC-25A-3P | Icw 0,384 kA 1 s; Iq 10 kA con gG/aM 35 A a 400 V; `T_max_C` 50 | TeSys Vario VCF1 |
| SECC-40A-3P | Icw 0,48 kA 1 s; Iq 10 kA con gG/aM 50 A a 400 V; `T_max_C` 50 | TeSys Vario VCF2 |
| 2 relés térmicos | `T_max_C` 60 (−20…60 °C sin desclasificar) | LRD08, LRD10 |
| 6 contactores | `T_max_C` 60 (−40…60 °C; 60…70 con desclasificación) | LC1D09BD, LC1D09M7 |
| CONT-AUX-1NA1NC | `T_max_C` 60 (−5…60 °C) | LADN11 |
| 8 mandos de puerta | `T_max_C` 70 (−40…70 °C) | Harmony XB5AA31/42/61, XB5AD21/33, XB5AVB3/4 |
| 2 setas de puerta (+2 de caja que heredan el ancla) | `T_max_C` 70 | XB5AS8445, XB5AS8442 |

**Quedó en `a_confirmar`, SIN valor:**
- Icu/Ics de ITM-C6-3P, C16-3P, C20-3P, C2-1PN y C6-1PN: la Icu del iC60N cambia con In (las de
  1–3 A dan 50 kA; las de 6–10 A, 20/10 kA) y con los polos; sin la ficha exacta de esa ref no
  se infiere de la vecina. El CN no publica A9F04306/16/20 ni A9F04602/06.
- `T_max_C` de 19 refs: las 2 fuentes 24 VDC (Mean Well / Phoenix), GM-AUX-1NA1NC (la ficha
  GVAN11 no trae temperatura), los 2 relés de interfaz (Phoenix / Finder), el relé de seguridad
  (Pilz / XPSAC5121: sin ficha descargable), el PLC (S7-1200), los 5 bornes, los 5 conductores y
  los 2 variadores (V20 / MS300).
- Portafusible 5x20: `cartucho_U_V`, `cartucho_Icn_A`, `cartucho_Icn_x_In` (la hoja de norma de
  IEC 60127-2 no se pudo leer: no hay cifra de memoria) y `T_max_C`.
- Las 4 redes: `Icc_kA`, `X_R` y `esquema`, con `fuente` «criterio de diseño».

**Decisiones propias (para vetar).**
- **`T_max_C` vale en toda ref, no sólo en las de tablero**: es obligatoria dentro del tablero y
  opcional fuera. Las setas de caja (`montaje: campo`) heredan por el ancla el de su seta de
  puerta, y rechazarlo obligaba a duplicar el bloque.
- **`esquema` en `a_confirmar` también en las dos redes TN**: su TN es «supuesto y declarado»
  (lo dicen sus descripciones), o sea un valor estimado; D6 lo pedía sólo «donde falta».
- **La clave de un mapa es el TOPE del rango de tensión de la ficha** («220…240 V» → 240,
  «380…415 V» → 415): con `a_tension` (menor ≥ U) la red de 220 V lee la fila de 220…240 y la de
  380, la de 380…415.
- **`MODELO_SIN_VALOR = {"red": ("esquema",)}`**: lo único de `modelo` que `a_confirmar` puede
  nombrar sin valor. La F1c lo puede unificar con `ajustes.OPCIONALES` (`RA_ohm` no se sumó: sin
  TT no aplica).
- **`Ics ≤ Icu` sólo cuando vienen las dos**; con las dos, cada tensión de Ics tiene su Icu.
- **Una ficha por familia** para `T_max_C` cuando la línea comparte el ancla (LRD08 vale por
  LRD10; LC1D09 por los D12/D18): la serie publica la misma temperatura.
- **`linea_referencia` de los seccionadores corregida**: citaba VCF02 (Ith 12 A) para el de 25 A
  y VCF1 (32 A) para el de 40 A. Ahora VCF1 (Ithe 25 A) y VCF2 (Ith 40 A), de donde salen sus
  cifras. Es `specs`: no entra a la firma ni a la geometría.

**Vigencia (D11), medida.** Las firmas de documento de los 4 tableros del banco
(`tests/tablero_electrico.py`: directo, variador+PLC, cat. 3 y relé de seguridad) son
idénticas antes y después (`2:503cd4a3…`, `2:268d92d4…`, `2:3333d655…`, `2:26735e40…`), y un test
lo vigila quitando los datos de todas las fichas. Sin bump de `GEOM_CACHE_EPOCH`, de versiones de
comandos ni de `COSIM_EPOCH`: ningún gate lo pidió (no se tocó `cosim/` ni `services/cosim_red.py`).

**Conteos medidos.** Suite completa en el worktree (`PYTHONPATH` al `core/` propio, `-B`):
5285 tests, 5279 pasan y 6 se saltan, sin fallas (antes 5252: +32 de `test_ficha_datos.py` y +1
del gate paramétrico de `MODULOS`). `ruff check core tests scripts` limpio. Refs del catálogo:
420, sin cambio. 34 de 53 refs de tablero con
`T_max_C` de ficha, 19 a confirmar; 10 de 15 protecciones con poder de corte de ficha (3 ITM, 5
guardamotores y los 2 seccionadores), las 5 ITM restantes y el portafusible a confirmar.
Búsqueda de fichas: ≈ 25 min (el tope era ≈ 20; se pasó en la última tanda de ITM, que sí dio 3
refs exactas).

### F1b — El diferencial (2026-10-24)

**Qué se hizo.**
- `cosim/modelos/diferencial.py` (nuevo): `Diferencial` (`tipo: diferencial`) con la residual
  |Σ fasores|, el umbral `K` = 0,75 × IΔn, los tiempos en el medio de cada banda (`T_DISPARO_S`:
  0,15 s desde K, 0,075 s desde 2 IΔn, 0,02 s desde 5 IΔn; las bandas de norma en `BANDAS_S`), el
  contador que vuelve a cero si la residual baja, `rearmar`/`abrir`/`cerrar`, las fallas
  `no_dispara` y `abierto` (el patrón de `_Proteccion`) y las señales `cerrado`, `disparado`,
  `I_residual_mA`, `causa`. Cuatro hipótesis declaradas (k, tiempos, A = B, sin fuga natural).
- `cosim/tablero.py`: el diferencial se indexa aparte (`diferenciales`, con las mismas ramas de
  `_ramas_proteccion`) y recibe `I_fasores` de `_fasor` (complejo, sin `abs`); `_corriente` pasó a
  ser `abs(_fasor(…))`: el mismo número bit a bit que antes (`abs(complex(x, 0))` = |x|). Sus
  contactos se mueven con `-F1.cerrado`, como los de un ITM (`_k_prot`). 451 líneas.
- `library/electrico/ficha.py`: `diferencial` en `TIPOS_MODELO` y `CLASES_RESIDUAL` (AC, A, F, B)
  validada como `curva` (normaliza a mayúsculas). `colocacion_modelo`: clase «alimentacion».
- `121_proteccion_electrica.yaml`: las 8 refs de D9 (anclas `&diferencial_2p`/`&diferencial_4p`):
  bornes `1`–`2` (`1`–`6`) + `N1`/`N2`, TODOS los polos como camino `proteccion` de línea a carga
  (el N pasa por el toroide y se abre con el disparo), `modulos_DIN` 2 y 4, `specs` con
  `linea_referencia` «orden de», `cotas_verificadas: false` y `cost` referencial; nota de la red
  2F (el N lleva la segunda fase) y del 4P en una red sin neutro.
- `library/electrico/erc.py`: la regla «tipo de diferencial» (D10) por `Llegada.via`.
- UI viva: «Interruptor diferencial» en `arbolSenales.ts` y `fallas.ts`, y `diferencial` en
  `PROTECCIONES` (sus fallas se dicen «protección disparada sola», «protección que no dispara»).
- Tests: `tests/test_cosim_diferencial.py` (18: bandas, ½ IΔn, el umbral, el contador, el rearme,
  las hipótesis, la validación, las 8 refs con `de` = línea, el tablero 1F TN y 3F+N, el índice
  aparte y la regla D10 verde, roja y sin fila); los dos gemelos en `test_cosim_fallas_modelos.py`;
  las 8 refs en `test_catalogo_electrico` (categoría y honestidad); un caso en
  `ui/src/vivo/fallas.test.ts`.

**Cifras de ficha: ninguna verificada.** Las fichas de Schneider Acti9 iID (se.com y
schneider-electric.cn: 403 o el reto anti-robots), ABB F200 y Eaton xEffect FRCmM (se agotó el
tiempo de espera) y Siemens 5SV3 (403) no se pudieron descargar en ≈ 17 min; las cifras que se
vieron venían de distribuidores, que no son fuente. Las 8 refs llevan `Inc_kA`, `Inc_con`, `Im_A` y
`T_max_C` en `a_confirmar` SIN valor y una `fuente` que lo dice. Lo que define la ref (In, IΔn,
clase, polos) va en `modelo`: es lo que hay que respetar al reemplazarla. Peso y `cost`, como en
el resto del catálogo, referenciales.

**Lo que se midió en el tablero.**
- `RED-1F-220V-60HZ` (TN) → 2P 30 mA A → ITM C2 2P → 220 Ω: sana, residual 0,044 mA (la
  conductancia mínima de 0,1 µS por nodo de `mna.py`: el piso de la red, lejos de 15 mA); con un
  `corto` de 1 kΩ de `-Q1:2` a `-G1:PE`, el diferencial dispara (≈ 220 mA = 7,3 IΔn → 0,02 s) y el
  ITM C2 no (1,22 A). El de 300 mA no dispara: 220 mA < 0,75 × 300 = 225 mA (margen del 2 %, pero
  determinista: la residual es 220 V / 1 kΩ y la Zk de la red, 6 kA, no la mueve).
- `RED-3F-380-220V-60HZ` (TN) → 4P 30 mA A → 100 Ω de cada fase al N (equilibrada, una y dos
  fases): residual bajo el piso con 2,2 A por fase; un corto de 1 kΩ de `-F1:4` a PE dispara.

**Vigencia (D11), medida.** `COSIM_EPOCH` sigue en 4: sólo la huella de `test_cosim_epoch.py`
(`c6581877e1b42fcd`). 10 escenarios del banco (`cosim_lazo_banco`: marcha, seta, atasco parcial,
contactor soldado, `no_cierra`, piloto fundido, corte de fase, corto entre fases —el que pasa por
el `I_A` de las protecciones—, cajas con seta y sensor pegado) dan la MISMA huella en `194e119`
(exportado limpio con `git archive`) y en esta rama, p. ej. marcha `40e10dae…`, corto entre fases
`ca5eb984…`, cajas con seta `d17d7651…`. Firma del documento: no se mueve (ningún `modelo` de
una ref existente cambió). Sin bump de `GEOM_CACHE_EPOCH` (refs nuevas: ninguna caché las tiene)
ni de versiones de comandos. El ERC de un documento sin diferencial es el de siempre: la regla
nueva no da fila sin uno (no entra a `services/electrico.REVISA`).

**Decisiones propias (para vetar).**
- **D10 avisa también con clase F si la entrada del variador es trifásica** (la F es de los
  variadores monofásicos y tampoco ve la continua lisa); con entrada de dos bornes, sólo AC y A.
- **D10 sin cita de norma**: el texto de IEC 60364-5-53 §531.3.3 no se pudo leer; «criterio de
  diseño», como pide D10.
- **La regla no da fila «ok» sin diferenciales** (aplica sólo con uno): así no cambia la salida
  del ERC de ningún documento existente ni el golden del carril.
- **Rearmar con la falla presente vuelve a disparar en su tiempo de disparo** (0,02 s a ≥ 5 IΔn),
  no literalmente en el paso siguiente: abierto no ve la residual, y el aparato es de disparo libre.
- **Tolerancia relativa de 1e-9 en el borde de cada banda** (`TOL_BORDE`): 5 × IΔn armado con
  fasores llega como 4,999…; sin ella caía en la banda de 2 IΔn.
- **Todos los polos del diferencial son `proteccion`**, el N incluido (en el ITM 1P+N el N es `NA
  mano`): es lo que hace que la residual sea la suma y que el N abra con el disparo.

**Hallazgo fuera de alcance (no se tocó).** En la co-simulación el polo N de los ITM 1P+N
(`ITM-C2-1PN`, `ITM-C6-1PN`) queda ABIERTO siempre: su camino es `NA` con `accion: mano`, el
actuador `-Q1.mano` arranca en `False` (`services/cosim_red._cerrado_inicial` sólo cierra los
seccionadores) y el modelo `Itm` no lo publica. Una carga fase-neutro tras un 1P+N no recibe
tensión (medido: 0,04 mA en lugar de 1 A). Por eso los tests usan el ITM C2 2P. Va al backlog.

**Conteos medidos.** Suite completa en el escritorio (carril C, `35dc35b`): 5426 tests, 5416
pasan y 10 se saltan, EXIT 0 (antes 5388: +18 de `test_cosim_diferencial.py`, +2 gemelos, y los
parametrizados por ref del catálogo con las 8 nuevas). `ruff check core tests scripts` limpio
(laptop y escritorio). vitest 520 → 521 y `npm run build` limpio. Refs del catálogo: 420 → 428
(61 de tablero: 34 con `T_max_C` de ficha, 27 a confirmar). Búsqueda de fichas: ≈ 17 min.
