---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: F0, F1, F2 y F3 mergeadas; falta conectar F3 al registro (la línea comentada de MAPA_SEGURIDAD) y la tabla de riesgos en el paquete, la v4 de create_belt_conveyor sin choques internos (D13b), F4, F5 y F6
descripcion: ninguna máquina llega a la tienda sin pasar una puerta de calidad determinista — construible, armable, reparable, segura y con vida útil industrial — con su ficha de calidad y su análisis de riesgos en el paquete
---

# Una máquina sólo se publica si se puede construir, armar, reparar y operar sin accidentes

## Estado y origen

Mario, 2026-10-22, tras ver la banda del video de la faja de motor central atravesar las guardas
(ajuste D13 de [fabrica-de-publicaciones](fabrica-de-publicaciones.md)) y saber que el perno del
tensor de la otra faja entra por una sola aleta:

> «Quién es el encargado de verificar esto? Tenemos que tener test y pruebas de calidad antes de
> lanzarlo… la máquina tiene que ser construida en virtual para que lo puedan construir en la
> realidad, cada pieza que agregas tiene que ser pensada para que en la realidad pueda ser
> ensamblada, reparada, evitar accidentes y funcionar con buena vida útil (son máquinas
> industriales), todo esto debe estar en piedra y no sólo depender de tu memoria o claude.md, si
> podemos crear software con código determinista ayuda… eres tú el encargado… procede a tu
> criterio, supera tus límites.» Y: «cópiate de lo que hacen las grandes industrias y mejóralo».

**El encargado es Claude** (la sesión que orquesta la fábrica): el modelador y el revisor
trabajan para él y la última palabra antes de publicar es suya. Este plan convierte esa
responsabilidad en CÓDIGO que bloquea, para que no dependa de que alguien se acuerde.

## Lo que hay hoy (medido, 2026-10-22)

Lo publicado hoy pasa por `paquete.calidad` (`publicacion/paquete.py:113-131`): exige VERDE de la
puerta de entrega (`library/delivery.py:81-317`). El VERDE dice «sin choques, sujeción declarada,
lints, salud, llave que entra»; NO dice que la máquina funcione ni que se pueda construir:

| Hueco | Evidencia |
|---|---|
| `engineering_check` (tracción, L10, ejes, pernos, soldaduras, motor, vuelco, flecha) no bloquea nada: sólo lo leen la tool, `/api/checks` y la memoria | nadie en `publicacion/` lo consume; el `NO CONFORME` de la memoria sólo se imprime (`drawing/calc_report.py:48-58`) |
| La fábrica pide la puerta CON gravedad, pero si falla la llamada cae en silencio a SIN gravedad y la gravedad queda en `no_aplica` → VERDE | `publicacion/flujo.py:73-81` |
| `no_aplica` nunca bloquea; «1 fijador no evaluado» pasa VERDE (en la faja #1 era el eje roscado, tomado por perno por su nombre) | `delivery.py:48-78`; medido con `tool_access_report` sobre el proyecto 3 |
| El tensor se reconoce por el NOMBRE de la pieza (tensor/take-up…) y con eso la adherencia sale `ok`; nadie mide la carrera | `library/rules.py:296-300, 816-830`; la única carrera es la de la plantilla de rodillos (`rodillos_cadena_reglas.py:239-253`) |
| Ningún chequeo del agarre de un perno (que cruce todas las piezas y le sobre hilo); un perno sin largo comercial cae a 200 mm SIN aviso | `library/fijacion.py:76-80`, `engineering/bolts.py:58-61,98-99` |
| Ninguna regla de guardas: sólo la pregunta del revisor | `grep guard` vacío en lints, rules, delivery, engineering |
| El revisor de taller no está en el flujo: es un agente aparte y su veredicto no se guarda ni se exige | nada en `publicacion/` lo llama |
| La cinta animada del video no se compara con el modelo | ajuste D13 (en curso) |
| No hay corrida de regresión de máquinas de referencia | `scripts/benchmark_package.py` es manual y sin pass/fail |
| Lo que se guarda con la versión es `{veredicto, resumen}`: ni reglas, ni hallazgos, ni evidencia | `paquete.py:236-244` |

Y un hecho de proceso: el hallazgo del revisor (perno M12×50 por una sola aleta) se cerró como
«asumido» porque el catálogo no tenía el largo, y se publicó igual.

## Lo que se revisó antes de escribir esto

- Las herramientas existentes (mapa con `archivo:línea` en la Bitácora F0): puerta de entrega,
  `engineering_check` (familias de reglas y severidades `ok|aviso|error`), acceso de herramienta,
  gravedad, `scan_motion`, escenarios de co-simulación, stack-up, FEA, ERC, `check_assembly`.
  Casi todo lo que hace falta YA se calcula; falta que bloquee, que no quede «no evaluado» y lo
  que no existe (agarre, tensor, guardas, reparabilidad).
- Lo que hace la industria y se copia (y se mejora):
  - **DVP&R / matriz de trazabilidad** (automotriz, modelo en V): cada requisito → su prueba → su
    evidencia. Aquí: cada ítem de la ficha de calidad cita su norma y lleva sus números.
  - **DFMEA** (AIAG-VDA): por función, sus modos de falla y el CONTROL que los detecta. Aquí: cada
    ítem dice qué modo de falla previene; un modo sin control determinista es un hueco declarado.
  - **ISO 12100** (evaluación y reducción de riesgos de máquinas) + **ISO 13857** (distancias de
    seguridad para que brazos y manos no alcancen zonas peligrosas): el análisis de riesgos se
    DERIVA del modelo y cada peligro debe tener su medida verificada.
  - **Stage-gate con revisor independiente** (aviación: quien firma no es quien hizo).
  - **Jidoka** (Toyota): ante un defecto la línea se para; aquí la fábrica no publica.
  - **8D / lecciones aprendidas**: cada defecto → regla + test; ya existe `docs/defectos.md`.
  - **La mejora**: la industria hace esto a mano, una vez, por muestreo. Aquí es código que
    re-corre entero en CADA versión de CADA máquina, con **defectos sembrados** (testigos malos)
    que prueban que la puerta los atrapa — eso la industria no lo puede pagar.

## Decisiones (para vetar)

- **D1 — Una puerta de publicación DETERMINISTA, separada de la puerta de entrega.** La de entrega
  sigue siendo la del modelador (rápida, para iterar). La de publicación es más dura: un REGISTRO
  de ítems en `library/calidad/` (puro: id, título, modo de falla que previene, norma o «criterio
  de diseño», `aplica_si`, función que evalúa insumos ya extraídos) + `services/puerta_publicacion.py`
  (lee el documento) + `POST /api/puerta-publicacion` + tool MCP `publication_gate` (el modelador
  la corre antes de terminar). Cada ítem da **OK | FALLA | SIN_EVALUAR | NO_APLICA**, con
  evidencia (números, ids, bloque `calc`). NO_APLICA sólo si `aplica_si` es falso, con el porqué
  («sin tablero eléctrico»). **Se publica sólo si TODO ítem aplicable está OK.** SIN_EVALUAR
  bloquea igual que FALLA. *Porqué*: el VERDE de hoy mezcla «no se pudo ver» con «está bien».
- **D2 — Lo que ya existe pasa a bloquear, con umbrales industriales.**
  - Puerta de entrega VERDE, **con gravedad obligatoria**: sin MuJoCo o si la simulación falla →
    SIN_EVALUAR, nunca la caída silenciosa de `flujo.py:73-81`.
  - `engineering_check`: `error` → FALLA. `aviso` → FALLA salvo las reglas que el registro marca
    *informativas* (con su porqué). Umbrales para la tienda: **L10h ≥ 20 000 h** (ISO 281;
    máquina de 8 h/día en servicio continuo, tablas de vida recomendada de SKF/FAG), **motor y
    reductor con factor de servicio ≥ 1,25** (AGMA, carga uniforme, 8–10 h/día), FS de cadena y
    transmisión ≥ 1,2 (ya en las reglas), vuelco con margen ≥ 10 % de la base, flecha ≤ L/240,
    pandeo FS ≥ 3, unión apernada utilización ≤ 0,7, uniones y soldaduras TODAS dimensionadas.
  - La memoria de cálculo en `NO CONFORME` → FALLA.
  - Acceso de herramienta: todo fijador evaluado; un «no evaluado» se resuelve (arreglar el
    reconocimiento o el modelo), no se tolera. Primer caso: un eje con «perno» en el nombre no es
    tornillería.
- **D3 — Función mecánica: lo que hoy nadie mide** (determinista, sobre la geometría):
  - **Agarre de perno**: por cada perno (catálogo, `join_bolted` o reconocido por geometría), un
    rayo por su eje: cruza TODAS las piezas que une hasta su tuerca u hoyo roscado; con tuerca le
    sobran ≥ 2 pasos de hilo; en hoyo roscado engancha ≥ 1·d en acero (≥ 1,5·d en aluminio o
    fundición; VDI 2230 / criterio de taller). El largo es de la serie comercial (ISO 4014/4017/
    4762) y **existe en el catálogo**: el respaldo silencioso a 200 mm desaparece para los comandos
    NUEVOS (sello de entrada, como `join_bolted.criterio`: un log viejo regenera igual) y la
    puerta lo marca FALLA en los viejos.
  - **Tensor**: todo lazo (banda o cadena) debe tener un mecanismo de tensado RECONOCIDO —
    `create_take_up`, chumacera tensora de catálogo (UCT) en su marco, ranuras del motor de la
    plantilla, o declarado en el metadato `tensores` `{piezas, carrera_mm, eje}` — con **carrera
    ≥ 1 % del largo del lazo + 20 mm de montaje** en banda (estiramiento de servicio de una banda
    de PVC de 2 capas: 0,5–1 %, CEMA/fabricantes) y ≥ 3 % en cadena (la regla existente). El
    perno o husillo del tensor pasa el control de agarre en TODA la carrera. Sin tensor reconocido
    → SIN_EVALUAR. La adherencia (Eytelwein) deja de dar `ok` por el nombre: usa este
    reconocimiento.
  - **Vida útil** (D2): L10h, factor de servicio, fatiga del eje (σ_adm ya es 0,5·σy).
- **D4 — Seguridad: análisis de riesgos ISO 12100 DERIVADO del modelo + guardas ISO 13857.**
  - Se identifican los peligros mecánicos desde el modelo: lo que gira (juntas giratorias,
    tambores, ejes, poleas, piñones, cadenas, acoples), los puntos de atrapamiento de entrada
    (banda ↔ tambor, cadena ↔ piñón), los extremos de eje salientes; eléctricos si hay tablero.
  - Por cada peligro, **la guarda se verifica con sondas**: rayos rectos desde una esfera de
    direcciones hacia la zona peligrosa; todo rayo que llega sin cruzar un sólido antes de la
    distancia de seguridad de ISO 13857 (tabla 2 para alcance a través de aberturas por tamaño
    de abertura; 850 mm de alcance del brazo por defecto) es una FALLA con la dirección y el punto.
    Excepción declarada: la superficie de trabajo (el tramo de carga de la banda), salvo sus
    puntos de entrada en cabeza y cola, que sí se guardan.
  - La guarda fija **se quita sólo con herramienta**: unida por perno (no soldada, no apoyada).
  - Sale una **tabla de riesgos** (peligro → medida → verificación) que va en el paquete.
- **D5 — Reparable: las piezas de desgaste se cambian sin cortar ni soldar** (MIL-HDBK-470 /
  DFMA). Piezas de desgaste por rol: banda, rodamientos y chumaceras, cadena, piñones, rodillos,
  motorreductor. Por cada una, en el grafo de uniones declaradas: entre ella y lo que la sujeta no
  hay soldadura, y su camino de salida queda libre quitando sólo piezas atornilladas. **La banda
  sin fin se puede montar**: su lazo sale por un costado (a lo largo del eje de los tambores)
  quitando sólo piezas atornilladas. Las herramientas: las del acceso de herramienta.
- **D6 — El revisor de taller entra al flujo y su veredicto se exige.** La fábrica pide
  `revision.json` (el formato de `design/revision.py`) hecho sobre la **misma firma** del modelo
  que se publica, sin hallazgos ALTA ni MEDIA abiertos. Un hallazgo se cierra sólo con una
  **re-revisión a ciegas** de la versión corregida (no lo cierra quien corrigió). «Asumido» no es
  un cierre. *Porqué*: el revisor es un LLM (no determinista), pero la exigencia de su veredicto y
  de la firma sí lo es.
- **D7 — Lo publicado se prueba contra el modelo**: el D13 de la fábrica (la cinta y las cadenas
  animadas, fieles al sólido) es un ítem de esta puerta; y la fábrica saca 3 cuadros del video
  (armado, marcha, cierre) que revisa otro agente con visión antes de subir (no determinista,
  queda como evidencia con su veredicto).
- **D8 — Ficha de calidad con la versión y en el paquete.** `calidad.json` (todos los ítems con
  estado y evidencia, la firma del modelo, versiones de Apolo y del registro) y `calidad.md`
  legible en la carpeta de la versión; la ficha de calidad y la tabla de riesgos van en el ZIP
  gratis («validado por software, no construido ni probado físicamente»: el aviso legal de la
  tienda sigue). La tienda se niega a importar un paquete sin `calidad.json` aprobado.
- **D9 — Testigos y defectos sembrados en la suite.** Los `.apolo` (logs de KB) de las máquinas de
  referencia entran a `tests/data/testigos/` con su veredicto congelado: un cambio de Apolo que
  mueve un veredicto pone roja la suite. Y por cada ítem, un **testigo malo** con el defecto
  SEMBRADO (perno corto, tensor sin carrera, eje sin guarda, cadena expuesta, rodamiento soldado,
  cinta que cruza la guarda…): la puerta tiene que atraparlo. Cada defecto nuevo que aparezca en
  producción suma su testigo malo antes de corregirse (8D).
- **D10 — Familia nueva: Mario aprueba las 2 primeras.** La ficha declara su `familia` (p. ej.
  «faja de banda», «transportador de rodillos»); con menos de 2 publicaciones aprobadas de esa
  familia, la fábrica se detiene antes del paso `tienda` hasta `publicar.py aprobar --slug`. El
  registro de familias aprobadas vive en el repo privado (`apolo-fabrica/familias.json`).
- **D11 — En piedra = código + test, no memoria.** La regla durable es el registro de ítems; el
  CLAUDE.md sólo enlaza a este plan. `--forzar` no existe en la fábrica ni en el paso `tienda`
  (sólo en `publicar generar`, para ensayos que nunca llegan a la tienda).
- **D12 — Lo ya publicado pasa por la puerta.** Las dos fajas publicadas se re-corren con la
  puerta (F6); lo que falle se corrige en una versión nueva y se re-publica. Mientras tanto no se
  publican máquinas nuevas.
- **D3b — Cadenas lazo a lazo de `create_roller_conveyor` sin tensor** (decisión del orquestador,
  2026-10-22). Los lazos rodillo a rodillo (centros fijos) se aceptan SIN tensor cuando la
  distancia entre centros es la exacta de su número de eslabones (la plantilla ya la calcula) y
  la holgura queda dentro de la tolerancia de la plantilla (`TOL_CENTROS_MM`, ±0,05 mm). El ítem
  dice «sin tensor: centros exactos; reemplazo de la cadena al 3 % de estiramiento» como OK y el
  mantenimiento lleva el criterio medible (20 pasos de 1/2″: nueva 254,0 mm, reemplazo a
  261,6 mm). El manual de ensamblaje no tiene sección de mantenimiento: la línea va en
  `calidad.md`. *Precedente*: los transportadores comerciales de rodillos vivos lazo a lazo van a
  centros fijos. Fuera de la tolerancia, SIN_EVALUAR (no hay con qué recoger la holgura).
- **D13b — La puerta de publicación revisa las interferencias DENTRO de los super-comandos.** La
  puerta de entrega las excluye (`same_command_pairs`) y eso escondió la banda de
  `create_belt_conveyor` en el piso (corregida en la v3 por el D13 de la fábrica). Ítem
  `montaje.interferencia_interna`: lo declarado (juntas, `fasten`, herraje asentado) no cuenta y
  un asiento ≤ `EXCESS_TOL_MM3` se tolera y se declara; el resto es FALLA. Los contactos reales de
  una plantilla se declaran en la plantilla (`fasten` contacto), nunca con una lista blanca.
- **D14 — Los ítems de la puerta son GENERALES; los mecanismos concretos son evaluadores que se
  enchufan debajo** (Mario, 2026-10-22: «estás poniendo en piedra cosas específicas cuando debe
  ser general; Apolo crea múltiples piezas y máquinas»). Un ítem del registro nombra un modo de
  falla general (`transmision_flexible.tension`, `union.agarre`, `elementos_rodantes.l10`,
  `publicado.sustitutos_fieles`, `riesgos.partes_moviles`, `consumibles.reemplazables`…); debajo,
  detectores y evaluadores por tipo de elemento, y la evidencia dice qué elementos evaluó
  (`elementos: {"banda": 1, "cadena": 13}`). Una familia de máquinas nueva suma un detector o un
  evaluador, nunca un ítem. Sin elementos de su tipo, NO_APLICA con el porqué («la máquina no
  tiene transmisiones flexibles»); una pieza estática suelta se puede publicar con los ítems de
  estructura, fabricabilidad y uniones. Los ids de F2/F3 no se reescriben: el registro los lleva a
  los generales con un mapa (`agarre.cruza` → `union.agarre`, `tensor.*` →
  `transmision_flexible.tension`, `vida.l10` → `elementos_rodantes.l10`…).
- **D15 — Solución declarada por función** (Mario la aprobó). Metadato `funciones: [{funcion,
  solucion, descartadas: [{solucion, motivo}], piezas}]` en el manifest (fuera del log), con
  `GET|PUT /api/funciones` y público en el `.apolo` publicado. Ítem
  `diseno.soluciones_por_funcion`: cada familia de función que el modelo tiene (transmisión
  flexible, apoyo rotativo, accionamiento, resguardo y la estructura de una máquina con ≥ 1 parte
  móvil) cubierta por una función declarada —por su nombre o por sus piezas— con ≥ 1 alternativa
  descartada y su motivo; si no, FALLA. Una pieza estática: NO_APLICA. *Porqué*: una solución
  elegida sin comparar es memoria de nadie; el registro de la alternativa y su motivo es el DFMEA
  de la decisión.

## Alternativas descartadas

- **Endurecer la puerta de entrega existente**: la usa el modelador en cada iteración y el MCP la
  congela en el golden; endurecerla rompería el flujo de diseño. Dos puertas con fines distintos.
- **Que el revisor LLM lo cubra todo con más preguntas**: no es determinista ni repetible; sirve
  para lo que el código todavía no mide, no como control principal.
- **FEA obligatorio de toda la máquina**: caro y, para estas máquinas, la flecha de viga, el
  pandeo y las uniones ya se calculan con norma; queda como ítem de una familia que lo pida.
- **Copiar la Directiva de Máquinas entera (expediente técnico CE)**: es para quien vende la
  máquina construida; aquí se vende el diseño. Se copia su núcleo técnico (ISO 12100/13857).

## Fases

Máx. 2 agentes a la vez (hoy ya corre el D13 de la fábrica).

- **F0 — Medir** (S, sólo lectura). Correr lo que ya existe (puerta con gravedad, engineering_check,
  acceso de herramienta) sobre las dos fajas publicadas (proyectos 3 y 4 del escritorio), la 38 y
  la 72; anotar qué ítems de D2 fallarían hoy y exportar sus `.apolo` para F5. Dueño: Claude.
- **F1 — Núcleo de la puerta** (M; `library/calidad/`, `services/`, `api/`, `tools/`, `publicacion/`).
  Registro, estados, `calidad.json`/`.md`, endpoint, tool MCP (golden + catálogo), paso `calidad`
  en la fábrica antes de `generar`, gravedad sin caída silenciosa, D2 (lo existente bloquea), la
  tienda exige `calidad.json`. Depende de que D13 esté mergeado (toca `fabrica.py`).
- **F2 — Función mecánica** (M/L; `library/`, `services/`, sello de `join_bolted`). Agarre de perno
  y largos comerciales, tensor reconocido y carrera, umbrales de vida útil; cada control como
  función pura que devuelve ítems del registro (interfaz de F1: `{id, estado, evidencia, piezas}`).
  Puede correr en paralelo con D13.
- **F3 — Seguridad y reparabilidad** (L; `library/`, `services/`). Peligros ISO 12100 desde el
  modelo, sondas ISO 13857, guarda que se quita con herramienta, piezas de desgaste
  reemplazables, banda montable, tabla de riesgos. Calibra con los testigos de F0.
- **F4 — Revisión y aprobación en el flujo** (M; `publicacion/`, repo privado). `revision.json`
  por firma, re-revisión, familia nueva con aprobación, cuadros del video revisados; briefs de
  orquestación en `apolo-fabrica`.
- **F5 — Testigos y defectos sembrados** (M; `tests/`). Fixtures, veredictos congelados, un
  testigo malo por ítem; `scripts/testigos.py` para correrlos a mano contra una API.
- **F6 — Verificar** (M). Las dos fajas por la puerta completa; corregir; re-publicar en versión
  nueva; Mario mira el resultado (D10: es la familia nueva).

## Lo que este plan NO hace

- No construye la máquina física: la validación es por software y el aviso legal se mantiene.
  Lo único que valida de verdad un diseño es construirlo; se recomienda a Mario construir una
  máquina piloto por familia para calibrar (fuera de este plan).
- No certifica (CE, UL, NR-12): da la evidencia técnica que un certificador pediría.
- No cubre fatiga de estructura soldada, vibraciones ni ruido.

## Riesgos

- **Falsos rojos** (sondas de guardas, agarre en piezas raras): F0 calibra con máquinas reales;
  cada falso rojo se arregla en el código con su testigo, nunca con una excepción a mano.
- **Lentitud** (gravedad + sondas + agarre en 200+ piezas): presupuesto de tiempo por ítem en
  `calidad.json`; la puerta corre una vez por versión, no por iteración.
- **El modelador se traba en la puerta**: la tool `publication_gate` le dice qué ítem y qué pieza;
  el brief le pide correrla antes de terminar.
- **Registro de familias en un solo repo** con varias PCs: es un archivo en git; con más PCs pasa
  a la tienda.

## Bitácora

### F0 — mapa de lo existente (2026-10-22)

Leído por un agente de sólo lectura (resumen en «Lo que hay hoy»). Acceso de herramienta en el
proyecto 3: 122 fijadores evaluados, 122 libres (incluidos los dos DIN 912 Allen del tensor); el
único «no evaluado» es `c223 Eje fijo de cola Ø25 g6 (roscado p/ perno)`, tomado por tornillería
por su nombre.

### F2 — función mecánica (2026-10-22, mergeada)

Construido (controles PUROS en `library/calidad/`, insumos en `services/calidad_*.py`; la F1 sólo
los registra):

- **Interfaz** (`calidad/item.py`): `Item{id, titulo, estado, modo_de_falla, norma, evidencia,
  piezas, detalle}`, estados `OK | FALLA | SIN_EVALUAR | NO_APLICA`, `peor()` y `aprobado()` (todo
  aplicable OK; SIN_EVALUAR bloquea; sin aplicables = no aprobado). Cada control agrega sus casos
  en un ítem (`evidencia.casos`, recortados a 20 con `casos_omitidos`).
  `services/calidad_mecanica.items_funcion_mecanica(doc, reglas=None)` da los 16 ítems.
- **Agarre** (`agarre.cruza|retencion|largo`): eje y cabeza por GEOMETRÍA (`fijadores_geom` +
  cilindros coaxiales), rayos de OCCT paralelos al eje (`kernel/rayo.Rayos`: seis entre vástago y
  cabeza, cuatro dentro del vástago para la rosca). Cruza lo que su `fasten` dice y no termina
  entre dos paredes de una pieza que ya cruzó; tuerca con ≥ 2 pasos fuera; rosca ≥ 1·d acero,
  1,5·d aluminio/fundición, 2/3 del largo en madera; largo de la serie ISO y del rango del YAML
  (`largo_min_mm`/`largo_max_mm`, REFERENCIAL). El eje «roscado p/ perno» ya no es tornillería
  (`lints.es_nombre_de_tornilleria`); una pieza con «roscado» en el nombre cuenta como rosca.
- **Sello**: `join_bolted` criterio 3 (vigente) = el 2 con largo de catálogo o error accionable
  (largo pedido y el mayor de catálogo); el 2 de los logs guardados conserva el respaldo a 200 mm y
  la puerta lo marca FALLA («el perno no llega a su tuerca… respaldo de 200 mm»). Sin `version` ni
  epoch: la geometría del 2 no cambió; `test_contrato_comandos` verde con la misma huella.
- **Tensor** (`tensor.reconocido|carrera|agarre`): take-up (carrera medida sobre el eje del perno
  entre las aletas), unidad de catálogo con `carrera_mm` (UCT204/205/206-150 nuevas, NSK
  take-up stretcher unit, J = 150), `tensores_trotadora` (reconocido, carrera SIN_EVALUAR: la ficha
  no la tabula), ranuras del portamotor de la plantilla y el metadato `tensores` (manifest + `GET|PUT
  /api/tensores`; la clave se escribe sólo si hay tensores: el saneo de `publicacion/` aún no la
  tiene en `MANIFEST_PUBLICO` y la F1 decide si es pública). Banda ≥ 1 %·L + 20; cadena ≥ 3 %·L/2 sobre centros (la regla de la plantilla).
  El perno tensor se evalúa con la pieza corrida a los dos extremos. Eytelwein: `tiene_tensor` sale
  de este reconocimiento (`engineering_rules.inherit_tensor`), no del nombre.
- **Vida útil** (`vida.*`, 10 ítems): L10 ≥ 20 000 h, FS del accionamiento = P_motor/P_absorbida
  ≥ 1,25 (el reductor de catálogo no publica capacidad: se toma ≥ 1 a placa), cadena FS ≥ 1,2,
  vuelco, L/240, pandeo FS ≥ 3, utilización ≤ 0,7, soldaduras, todo dimensionado; el resto
  `error`/`aviso` → FALLA salvo `INFORMATIVAS` (arrastre de banda, velocidad, geometría,
  transportador, alcance de la memoria), cada una con su porqué.

Medido: `create_belt_conveyor` por defecto da un lazo de 8 351 mm tras la v3 de D13 (pide 104 mm de carrera); su
`TENSOR-TROT-25` queda SIN_EVALUAR y un `create_take_up` corre 24 mm (12 + 12 entre aletas) →
FALLA de carrera con el agarre OK en los dos extremos. Los lazos rodillo a rodillo de
`create_roller_conveyor` (centros fijos) quedan SIN_EVALUAR: **decisión pendiente** (¿se aceptan
lazos de centros fijos sin tensor, con su criterio, o se pide un tensor?). Costo: ~0,05 s por perno
(rayos con el intersector cargado una vez por sólido). 63 tests nuevos
(`tests/test_puerta_agarre.py`, `_tensor.py`, `_vida_util.py`).

### F3 — seguridad y reparabilidad (2026-10-22)

Seis controles que devuelven ítems con el esquema de F1 (`{id, titulo, estado, modo_de_falla,
norma, evidencia, piezas, detalle}`) y la tabla de riesgos. Puro en `library/seguridad/`
(`iso13857`, `sondas`, `peligros`, `guardas`, `modelo`) y `library/reparabilidad.py`; OCCT en
`services/calidad_seguridad.py` (extracción + `controles_f3(doc)`), `calidad_sondas.py`
(trazador, cuñas) y `calidad_reparabilidad.py` (barridos). Tests: `tests/test_calidad_seguridad*.py`.

| ítem | mide | umbral |
|---|---|---|
| `seguridad.resguardo_iso13857` | sondas desde 64 direcciones (Fibonacci) a cada objetivo de cada peligro; el rayo arranca 50 mm fuera de la caja de la máquina o en el PISO; se bloquea en cualquier sólido que no sea el peligro | alcanza si la profundidad desde el contorno ≤ 850 mm y pasa el haz de 20 mm, o si, por una abertura menor (haces de 4/6/8/10/12/20 mm), la distancia a la abertura es < sr de la tabla 4 (ranura) |
| `seguridad.guarda_con_herramienta` | grafo de `fasten` del cuerpo de cada guarda (ella + lo soldado que no es estructura) | ≥ 1 perno; sin soldadura/pegado a la máquina; nada unido a lo que gira; sólo contacto = FALLA |
| `seguridad.electrico` | `services/electrico.chequeo` | sin carril → NO_APLICA; errores del ERC → FALLA |
| `reparabilidad.desgaste_sin_soldadura` | unidad soldada de cada pieza de desgaste ∩ marco soldado (grupo soldado con estructura o anclaje) | vacía |
| `reparabilidad.desgaste_desmontable` | rayos desde 160 vértices del teselado de la unidad (hundidos 0,3 mm) en ±X/±Y/±Z hasta salir | alguna dirección sin marco soldado |
| `reparabilidad.banda_montable` | rayos desde 240 vértices de la banda a lo largo del eje de sus tambores | algún lado sin marco soldado que además pase por dentro del lazo (caja de la banda −3 mm); empalme mecánico en el nombre = OK |

Peligros (ISO 12100): cuñas banda ↔ tambor (arco de contacto buscado cada 5° a r + 1 mm DENTRO
de la banda; cuña a φ = acos(r/(r+20)) del borde del arco, a radio r + 10 —separación 20 mm < 25
de ISO 13854—, en el centro y a ±15 mm de los bordes; las dos cuñas cuentan: el sentido de
marcha no se conoce), transmisiones (cadena + piñones, centro de cada pieza; ≤ 64 objetivos y
≤ 4096 sondas centrales), extremos de eje giratorio (extremos axiales del cuerpo, 3 mm adentro)
y piezas hijas de junta de giro. La banda no es peligro (zona de trabajo) y no se atraviesa, pero
tampoco estrecha el haz en su propia cuña (`forman`). Redondo = caja con dos lados iguales ±6 %
y ≥ 20 mm; «toca la banda» = unión declarada o ≤ 1,5 mm.

**Calibración** con las máquinas de la tienda (`.apolo` copiados, sólo lectura):

| máquina | piezas | peligros | resultado | ¿real? | tiempo |
|---|---|---|---|---|---|
| faja motor cabeza 1.0.5 | 228 | 2 cuñas + extremos del eje motriz | cuñas cola y motriz FALLA (13 y 6 sondas); eje OK; 8 guardas OK; desgaste 6 OK / 5 desmontables; banda FALLA | **real**: ranura de 27–30 mm entre el borde de la banda y la guarda superior / el soporte en C, sobre los extremos de los tambores, abierta desde arriba y desde el extremo de cola. Banda: la cama está soldada a los dos largueros (marco cerrado que la abraza) | 1,6 s |
| faja motor central 1.0.3 | 206 | 5 cuñas + extremos | cuñas cola y cabeza FALLA (11 y 11); desvíos y motriz OK (cajón del drive); guardas FALLA ×2; banda FALLA | **real**: extremos de los tambores alcanzables desde los extremos de la máquina. Guardas: «Tapa protectora del eje» y «Tapa del eje hueco del reductor» están declaradas `pegado` (D4 pide perno). Banda: travesaños de cama soldados a los largueros | 3,9 s |
| rodillos cadena 2 m 1.0.0 | 201 | 1 transmisión (20 cadenas, 41 ruedas) | FALLA 377/3904 sondas; 2 guardas OK; desgaste 82 OK / 62 desmontables | **real**: cadenas y piñones expuestos por abajo (la v1 no tiene bandeja) y por el extremo de alimentación | 34 s (sondas 23 s, 11 866 rayos) |

Falsas alarmas halladas y corregidas en el código, cada una con su test: el rodillo portante
liso salía peligro (cada fondo de rodillo FALLA) → no es peligro, lo es su transmisión; el eje del
rodillo atornillado al larguero salía giratorio → eje fijo; «Faja de banda · Tensor trotadora» y
«· Cama» salían «flexibles» por el nombre de la máquina → primer tramo común de un comando de
≥ 3 piezas = máquina; «Tapa porta-rodamiento» salía pieza de desgaste → sólo catálogo o nombre
que EMPIEZA por rodamiento; la tapa-cubo del tambor (gira con él) salía guarda → se excluye y se
lista. Rendimiento: el `IntCurvesFace_ShapeIntersector` del compuesto tardaba 10 ms por rayo con
las 17 800 caras de los rodillos (212 s la máquina) → cajas de cara en numpy + intersección cara a
cara en caché: 2 ms por rayo (34 s).

Hallazgos en plantillas (no publicadas): `create_belt_conveyor` deja los dos ramales rectos de la
banda a la altura del PISO (`_belt_loop`: `Polygon` centra por defecto, falta `align=None`) y los
arcos quedan como anillos completos → sus cuñas dan SIN_EVALUAR («no se encontró el arco»); el
arreglo cambia geometría (sube `version`) y queda fuera de F3 — **ya arreglado** en el ajuste D13 de la fábrica (v3, mergeado antes que F3).

**Decisiones del orquestador sobre lo que F3 dejó abierto** (2026-10-22): (1) ISO 14120 admite guardas fijas soldadas, pero una guarda soldada impide el mantenimiento de lo que cubre: se mantiene D4 (guarda fija = con perno). Las «tapas» `pegado` de la faja central se corrigen en F6. (2) Banda montable: con el marco soldado, la banda sin fin sólo se monta con empalme mecánico (grapas tipo Flexco, habitual en PVC) o con un marco que se abre por un lado; la regla queda como está y la corrección de cada faja se elige en F6. `create_roller_conveyor` v2: el
cárter del piñón motriz está SOLDADO a la base del motor (guarda FALLA y piñón motriz no
desmontable) y las cadenas se alcanzan desde la zona de trabajo entre rodillos por debajo del
borde interior de la guarda de cadenas (41 sondas).

No hecho: el cizallamiento banda ↔ estructura y carga ↔ fijo; la tabla 4 en columnas cuadrado y
círculo (se usa ranura, la más exigente); mallas finas (< 4 mm) se tratan con sr 2 mm.

### F1 — núcleo de la puerta (2026-10-22, en rama, sin mergear)

Construido:

- **Registro** (`library/calidad/registro.py`, puro): `Entrada` (un ítem evaluado sobre insumos ya
  extraídos, `library/calidad/puerta.py`) y `Fuente` (los ítems de un servicio, F2 hoy; F3 es la
  línea comentada con `MAPA_SEGURIDAD`). Cada ítem: id, título, modo de falla, norma, familia
  (estructura, función, montaje, seguridad, publicado, proceso), `aplica_si` sobre los HECHOS y su
  evaluador. Agregador `evaluar` → `{aprobado, items, por_familia, conteos, mantenimiento, firma,
  version_registro, tiempos_s}`. NO_APLICA sólo por `aplica_si`; un control que dice «no aplica»
  donde aplica → SIN_EVALUAR; un control que revienta o una fuente que no corre → SIN_EVALUAR; si
  el control evaluó algo que los hechos no esperaban, gana lo evaluado.
- **D14 (ítems generales)**, por pedido de Mario a mitad de la fase: 25 ítems con ids de modo de
  falla (lista en el docstring del registro); los 16 de F2 entran por un mapa
  (`agarre.cruza` → `union.agarre`, `tensor.*` → `transmision_flexible.tension`, `vida.l10` →
  `elementos_rodantes.l10`, `vida.cadena` → `transmision.capacidad`…) sin tocar su módulo; un ítem
  de una fuente que ningún general recoge sale tal cual (nunca se pierde). Detectores por tipo de
  elemento en `services/puerta_hechos.py` (`hechos.elementos`: {tipo: {clase: n}}); la evidencia
  de cada ítem nombra los elementos que evaluó. Nuevo `fabricabilidad`: cada pieza es de catálogo
  o un sólido válido con volumen, material y proceso (`drawing/process.infer_process`).
- **D15**: metadato `funciones` (validador puro `library/calidad/funciones.py`, setter
  `services/puerta_publicacion.poner_funciones`, `GET|PUT /api/funciones`, en el manifest sólo si
  hay y en `MANIFEST_PUBLICO`); ítem `diseno.soluciones_por_funcion` sobre las familias detectadas
  (transmisión flexible, apoyo rotativo, accionamiento, resguardo, estructura con partes móviles).
- **Insumos** (`services/puerta_publicacion.reunir`, bajo el `STATE_LOCK` del llamador): la puerta
  de entrega con la gravedad que corrió la API, sus `no_aplica` justificados por hechos
  (`entrega.no_evaluado`; lo desconocido bloquea), acceso de herramienta («no evaluado» →
  SIN_EVALUAR), los choques DENTRO de cada super-comando (`interferencia_interna`, sin
  `same_command_pairs`, paginado), el veredicto de la memoria (`services/memoria_reglas.py`, que
  ahora es también la fuente del PDF; `calc_report.veredicto`), ERC y escenarios, las fuentes y la
  firma `firma_modelo(log + hidden, materiales, vertical, estudios, requisitos, FEA, cotas,
  escenarios, tensores, funciones)`: la misma función calcula la publicación desde el `.apolo`.
- **API**: `POST /api/puerta-publicacion` (`?async=true` → `COSIM_JOBS`): (a) firma bajo
  `STATE_LOCK`; (b) gravedad con `_stability` (dos locks; sin MuJoCo o si falla → SIN_EVALUAR,
  nunca la caída silenciosa); (c) insumos y la fase OCCT de la marcha (`marcha_ejemplo.armar` +
  `preparar_prueba`) bajo `STATE_LOCK`; (d) la dinámica bajo `PHYSICS_LOCK`; (e) la fidelidad D13
  pura (`concluir_prueba`: infiel → FALLA; no simula → SIN_EVALUAR); 409 si la firma cambió entre
  las tomas. `probar` quedó partido en esas tres fases (mismo comportamiento).
- **MCP**: tool `publication_gate(completo=false)` en `tools/calidad.py` (job con recibo; resume a
  los ítems que fallan o no se evaluaron); golden con 3 casos; `FUERA_DEL_CHAT` (simula minutos).
- **Fábrica**: paso `calidad` entre `ficha` y `generar`: escribe `calidad.json` (ítems, evidencia,
  firma, registro, versión de Apolo) y `calidad.md` (para una persona, con el aviso «validado por
  software, no construido ni probado físicamente» y la sección de mantenimiento) y PARA con cada
  ítem que no pasó. `generar` se niega sin `calidad.json` aprobado o con otra firma (`--forzar`
  manual sólo para ensayos); la puerta de entrega de `generar` ya no cae a «sin gravedad» salvo
  con `--forzar`. `ficha.json` lleva `calidad` {aprobado, forzado, conteos, version_registro,
  firma}; los dos zips llevan `calidad.md`; `tienda.subir` se niega (antes de tocar la tienda)
  sin `calidad.json` aprobado, con `--forzar` o con firmas distintas. `tensores` y `funciones`
  son públicos en el `.apolo` saneado.
- **D3b** en `library/calidad/tensor.py` (`centros_fijos` en el lazo, puesto por
  `calidad_tensores.lazos_cadena` para `{cmd}_cad{k}` de un `create_roller_conveyor`).
- **Arreglado de paso**: el pandeo de patas (`engineering/report.py`) leía el NOMBRE entero, así
  que las patas de una plantilla («Transportador de rodillos · Pata …») no pandeaban nunca; ahora
  lee el rol (`piece_role`).

Medido (laptop, en proceso, requisitos 15 kg, paquete 400 × 300, 0,3 m/s):

- `create_belt_conveyor` (v3, por defecto y con `TENSOR-TROT-25`): NO aprobada, ~5 s (la marcha
  3,5 s). FALLA reales: **choques internos** (15: el motorreductor atraviesa el larguero
  392 599 mm³, la cama entra en las dos guardas laterales 34 978 mm³ c/u, el motorreductor en el
  tambor motriz 9 697 mm³, los ejes de los dos tambores y los tensores atraviesan los largueros sin
  barreno 3 700–7 100 mm³, los tambores en las guardas 444–1 422 mm³, la pata 4 en el motor
  1 038 mm³) — la plantilla necesita una v4 de geometría (fuera de F1); sin anclajes ni uniones
  (semáforo ROJO, se cae entera, vuelco sin huella, lint «pieza sin grupo ni unión»); flecha del
  bastidor 253,8 mm en 4 202 mm (madera por el nombre «larguero»: memoria NO CONFORME); sin
  funciones declaradas. SIN_EVALUAR: la carrera del tensor de catálogo (la ficha no la tabula) o
  la del take-up. OK: la marcha fiel (D13), fabricabilidad, factor de servicio, pandeo.
- `create_roller_conveyor` largo 1500: NO aprobada, 36 s (gravedad 18 s, interferencias 6 s).
  Pasan estructura, montaje (32 fijadores con llave, sin choques internos) y la tensión (14 lazos:
  13 por D3b + la motriz por sus ranuras). FALLA reales: **cadena FS 1,09 < 1,2** (piñón Z15,
  par nominal del MOTOR-037 en la motriz y el primer lazo); «velocidad del producto» 0,266 m/s
  contra los 0,3 pedidos (−11 %); sin funciones declaradas (D15). `elementos_rodantes.l10`
  NO_APLICA: los 6201 de los rodillos no son piezas de catálogo, nadie calcula su L10 (hueco).
- Tests: `tests/test_puerta_publicacion.py` (registro, cuatro estados, fuentes y mapa general,
  generalidad: un eje con chumaceras sin banda y una ménsula suelta que se aprueba, D15, controles,
  choque sembrado y la faja v3, firma, gravedad sin MuJoCo, job y 409, la puerta sobre la faja,
  tool, `calidad.md`, la fábrica que para y `generar` que se niega); `test_puerta_tensor.py` (D3b),
  `test_publicar_tienda.py` (la tienda se niega, 5 casos), e2e de publicación con la puerta.
- **Pendiente**: la v4 de `create_belt_conveyor` sin choques internos; L10 de rodamientos que no
  son piezas de catálogo (rodillos de la plantilla); los testigos de F5; F3 entra con su línea
  (`riesgos.partes_moviles`, `riesgos.resguardos_desmontables_con_herramienta`,
  `consumibles.reemplazables`; `riesgos.electrico` hoy es sólo el ERC).
