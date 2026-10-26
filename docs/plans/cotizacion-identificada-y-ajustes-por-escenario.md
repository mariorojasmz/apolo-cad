---
estado: en curso
nota: contrato de Claude con criterio delegado (2026-10-25), vetable por número; F1 (cotización identificada, notas con id acotables, alcance calculado) en `main` (`712a9bd`; decisiones F1-a…F1-j en su bitácora); sigue F2 (ajustes de aparato por escenario), luego la extensión del titular adopta D1–D3 y D5
descripcion: la cotización dice a quién va, con qué número y qué incluye de verdad; un escenario de prueba puede cambiar un ajuste de un aparato sin dejarlo cambiado en el proyecto
---

# La cotización dice a quién va y qué incluye; un escenario prueba un ajuste sin dejarlo puesto

## Estado y origen

- Mario, 2026-10-25: «continúa todos los pendientes que puedas … usa siempre pensamiento crítico y
  buenas prácticas». Contrato de Claude con ese aval; D1–D8 se vetan por número.
- La verificación por MCP de un paquete eléctrico completo (una faja con tablero, armada sólo por
  el agente) encontró tres cosas que una extensión no puede arreglar desde fuera porque el núcleo
  no le da por dónde:
  1. la cotización se titula con el nombre interno del proyecto («… (copia) (copia)») y no trae
     cliente ni número de documento;
  2. la nota del núcleo «No incluye transporte, instalación ni puesta en marcha» sale junto a
     filas de «Prueba de marcha» que una extensión sí cobra: el papel se contradice;
  3. un escenario de co-simulación que necesita un ajuste de prueba (p. ej. el tiempo de
     sobrecarga de un variador a 5 s para provocar el disparo en un atasco) lo deja escrito en el
     `add_device` del proyecto, y el manual de puesta en marcha lo publica como umbral real (la
     placa dice 60 s).

## El problema / lo que hay hoy

- `drawing/quote.py::quotation_pages(project_name=…)`: el título es `project_name`, que la ruta
  llena con `S.doc.name`; no hay cliente ni número. `_summary_page` imprime `requirements`.
- `drawing/quote.py::_notas_nucleo` (`:158-172`): cuatro notas fijas; «una extensión no las
  quita» (`pedidos-de-extensiones` D9: las de la extensión van DESPUÉS, sólo se suman).
- `api/routers/cosim.py:160` `EscenarioIn` y la tool `set_scenario(nombre, escenario)`: un escenario
  declara entradas, fallas y aserciones, no ajustes; los ajustes viven sólo en `add_device`.
  `services/escenarios.py` firma el escenario con el modelo del documento
  (`FUERA_DE_FIRMA`, `FUERA_DE_FIRMA_MODELO`).

## Lo que se revisó antes de escribir esto

- `Extension.costeo` (`extensiones.py:97`) ya acepta `FuenteCosteo` con `nota` validada
  (`library/costeo_extension.motivo_nota`); `extensiones_puntos.sumar_costeo` las valida al cargar.
  El patrón nuevo se cuelga de ahí, no inventa otro registro.
- `set_requirements` guarda requisitos como metadato del manifest; la identificación comercial
  también es metadato (no comando: regla «Metadato ≠ comando» del CLAUDE.md raíz).
- Los ajustes de aparato se validan en `library/electrico/ajustes.py` (`OPCIONALES` y requeridos
  por tipo): el override por escenario reutiliza esa validación.

## Decisiones (para vetar)

- **D1 — Identificación comercial = metadato del proyecto.** El manifest gana `comercial`
  (`titulo`, `cliente`, `numero`, `revision`, todos texto opcional) con `GET/PUT
  /api/project/comercial` y su campo en la tool existente que ya escribe metadatos del proyecto
  más cercana (`set_requirements` acepta `comercial=`), sin tool nueva. La cotización lo usa en el
  título y en un bloque «Cliente / Nº / Rev.» de la hoja de resumen. Sin `comercial`, el título es
  el nombre del proyecto SIN los sufijos «(copia)» repetidos y el bloque no sale.
- **D2 — Una extensión puede aportar la identificación**: `Extension.costeo` acepta además una
  `IdentificacionCosteo(id, de_documento: Callable[[doc], dict | None])` (exportada en
  `extensiones_api.SUPERFICIE`); gana el metadato del proyecto si existe, luego la primera
  extensión que devuelva algo, luego el nombre limpio. La fuente queda dicha en el pie de la hoja
  («identificación: proyecto | <id de la extensión>»).
- **D3 — Las notas del núcleo tienen id y DOS son acotables.** `_notas_nucleo` pasa a una lista
  de `(id, texto)`: `nucleo.referenciales`, `nucleo.detalle`, `nucleo.alcance`, `nucleo.validez`
  (+ `nucleo.cambio` y `nucleo.avisos` cuando aplican). Una `FuenteCosteo` puede declarar
  `acota="nucleo.alcance"` o `acota="nucleo.validez"` con su texto, que REEMPLAZA a la del núcleo
  en su lugar. Las de honestidad (`referenciales`, `detalle`, `avisos`, `cambio`) no se acotan
  nunca: la carga rechaza la extensión que lo intente (`ExtensionRechazada` con el motivo).
- **D4 — El texto del alcance se calcula si nadie lo acota**: si alguna fila del costeo es de
  pruebas o puesta en marcha (categoría declarada por la fuente: `incluye=("puesta_en_marcha",…)`),
  `nucleo.alcance` deja de decir «ni puesta en marcha». El papel no se contradice ni aunque la
  extensión olvide acotarlo.
- **D5 — Ajustes de aparato por escenario.** `EscenarioIn` gana `ajustes: {designación: {campo:
  valor}}`; se validan con `ajustes.py` igual que en `add_device` (campo desconocido → 400 con la
  corrección); se aplican sólo dentro de la co-simulación de ESE escenario; el documento no
  cambia. El resultado del escenario lista los ajustes que usó.
- **D6 — Firma y vigencia**: los `ajustes` del escenario entran en SU firma (un cambio de ajuste
  vence sólo ese resultado); sin `ajustes` la firma es la de hoy, así que los resultados guardados
  siguen vigentes y `COSIM_EPOCH` no sube (lo prueba un test con un escenario de antes).
- **D7 — El manual y la memoria leen lo del proyecto**, nunca lo de un escenario: ningún cambio
  aquí, pero un test del núcleo prueba que `services` de ajustes devuelve el valor del
  `add_device` aunque un escenario lo pise.
- **D8 — Golden y catálogo**: cambian el schema de `set_requirements` y de `set_scenario`; se
  re-congela el golden MCP tras revisar el diff; `tools/catalogo.py` no cambia (sin tools nuevas).

## Alternativas descartadas

- **Pasar cliente y número como parámetros de `quotation`**: se pierden entre una cotización y la
  siguiente y no los ven los demás entregables (cajetines, memoria).
- **Dejar que una extensión borre notas del núcleo**: las de honestidad son la razón de que la
  cotización sea creíble; acotar dos con id es suficiente para el caso real.
- **Ajustes de prueba como variantes del documento**: una variante cambia el modelo entero y su
  BOM; el caso es un número de prueba dentro de un escenario.

## Fases

- **F1 — Cotización identificada y nota acotable** (`drawing`, `api`, `extensiones`, `doc`
  metadato · M · ≈ 60 min): D1–D4, D8 (la parte de `set_requirements`). Se verifica con tests de
  la hoja de resumen (título limpio, bloque de cliente, fuente de la identificación), de la carga
  de extensiones (acotar una de honestidad → rechazo) y el golden.
- **F2 — Ajustes por escenario** (`cosim`, `services/escenarios`, `api` · M · ≈ 60 min · paralelo a
  F1): D5–D7, D8 (la parte de `set_scenario`). Se verifica con un escenario de atasco que dispara
  con `ajustes` y deja el `add_device` intacto, la firma de un escenario viejo idéntica y el
  manual con el valor del proyecto.
- **F3 — Cierre** (S): nota del plan; la extensión del titular adopta D1–D3 y D5 en su repo (fuera
  de este plan).

## Lo que este plan NO hace

- No cambia precios, márgenes ni el cálculo del costeo.
- No agrega cajetín comercial a los planos de taller (podría leer `comercial` más adelante).

## Riesgos

- **Un escenario guardado cambia de firma sin querer**: D6 + test con un escenario anterior.
- **Una extensión vieja con `nota` sin `acota`** sigue igual: `acota` es opcional.

## Bitácora

### F1 (2026-10-25, base 83c3d11)

Hecho: D1–D4 y la parte de `set_requirements` de D8. Sin extensiones ni `comercial`, el costeo,
las hojas y el PDF quedan como estaban (`tests/test_cotizacion_notas.py` congela costeo y hojas y
pasa sin re-congelar): el título limpio de «mesa», «tablero» y «cot-f4c» es el mismo, y el bloque
de cliente y el pie sólo salen con identificación.

Decisiones tomadas al implementar (vetables):

- **F1-a — El setter vive en `services/identificacion.poner_comercial`, no en `Document`.** El
  `dir(Document)` está congelado (`tests/test_rutas_viejas.py`) y `funciones`/`tensores` ya siguen
  ese patrón. `Document.comercial` (atributo) se guarda en el manifest SÓLO si hay (un manifest sin
  identificación queda byte-igual) y la carga no valida (como `requirements`):
  `identificacion()` re-valida al leer y, si no vale, sigue como si no hubiera.
- **F1-b — `set_requirements(fields=None, comercial=None)`.** La llamada vieja manda el MISMO
  cuerpo (el golden de «guardar requisitos» no cambió); con `comercial` sola, los requisitos no se
  tocan (en el REST: `fields` ausente del cuerpo); sin nada, la tool devuelve un error y no llama
  (antes `fields` era obligatorio: llamar sin nada no podía borrar los requisitos, y así sigue).
  `PUT /api/requirements` valida `comercial` antes de tocar nada (un 400 no deja medio cambio).
  `GET /api/requirements` suma `comercial` sólo si hay; `GET /api/project/comercial` da además la
  `efectiva` (lo que usará la cotización, con su `fuente`). Las rutas van en el router
  `validation`, junto a los requisitos.
- **F1-c — Precedencia por diccionario ENTERO, no campo a campo**: si el proyecto trae
  `comercial`, gana completo (aunque le falte el número que la extensión sí tenía). Mezclar
  fuentes en un mismo papel haría imposible decir de dónde salió cada dato en el pie.
- **F1-d — «Sin los sufijos (copia) repetidos» = sin ninguno** (`library/comercial.titulo_limpio`,
  sin distinguir mayúsculas): una copia de proyecto es interna; el cliente no la ve.
- **F1-e — El `numero` reemplaza el «N°» de la cabecera y el `drawing_no` del cajetín de TODAS
  las hojas** (antes, el id del proyecto o «COT-001»); la `revision` va sólo en el bloque (la
  tabla de revisiones del cajetín sigue siendo la de las revisiones guardadas del proyecto).
- **F1-f — Título largo**: cada campo ≤ 80 caracteres (`TEXTO_MAX`); un título de más de 54 baja
  de 4,6 a 3,4 mm en vez de recortarse (antes se cortaba a 54 en silencio). El cliente se parte en
  líneas, nunca se recorta. El pie («identificación: proyecto | <id>») va bajo el marco (y = 6
  mm): no compite con las notas ni con el cajetín; sin identificación (fuente «nombre») no sale.
- **F1-g — `acota` exige `nota` y se aplica sólo si la fuente cobró** (como la nota de D9). Una
  nota del núcleo tiene UN dueño: una segunda fuente que la acota (de la misma extensión o de otra
  ya cargada) no carga, con el motivo en `/api/health`. Se prefirió rechazar al cargar sobre
  «gana la primera y la otra se pierde» (silencioso) o «la otra se suma como nota» (el papel diría
  dos validez distintas).
- **F1-h — D4 con `FuenteCosteo.incluye`** (de `ALCANCES`: transporte, instalacion,
  puesta_en_marcha, pruebas), contado sólo si la fuente cobró; el costeo publica `incluye` sólo si
  hay. «pruebas» basta para no decir «ni puesta en marcha», pero el texto dice «las pruebas de
  marcha», no «la puesta en marcha» (no se afirma más de lo que se cobra). La nota acotada gana a
  la calculada.
- **F1-i — Una `IdentificacionCosteo` que lanza o devuelve algo inválido se SALTA** (motivo a
  stderr) y se prueba la siguiente: la cotización nunca se cae por la extensión. `de_documento` no
  llamable sí rechaza la carga.
- **F1-j — Sin bumps**: no sube `CONTRATO_EXTENSIONES` (sólo se agregan `IdentificacionCosteo` a
  `SUPERFICIE` y dos campos opcionales a `FuenteCosteo`), ni versiones de comandos ni
  `GEOM_CACHE_EPOCH` (nada entra al log).

Tests: `tests/test_cotizacion_identificada.py` (nuevo: título limpio, validación, viaje en el
`.apolo` y `.apolo` viejo, hoja con y sin identificación, título largo, API, tool, identificación
de extensión y su precedencia, una que lanza, notas con id, validez acotada en su lugar, alcance
calculado, acotar el alcance, seis variantes que no cargan y el dueño único entre dos
extensiones); variantes nuevas en `tests/ext_prueba/` (`costeo.py`, `__init__.py`);
`tests/test_rutas_api.py` (GET/PUT de `/api/project/comercial`); golden MCP re-congelado tras
revisar el diff (docstrings de `get_requirements`, `set_requirements` y `quotation`, el schema de
`set_requirements` y dos casos nuevos en `scripts/golden_mcp_casos.py`: «identificación
comercial» y «requisitos sin nada»).

Suite completa (`-n auto`): exit 0, 0 fallas. `ruff check core tests scripts`: exit 0. Sin cambios
en `ui/`.

### F2 (2026-10-25, base 712a9bd)

Hecho: D5–D7 y la parte de `set_scenario` de D8. Un escenario declara `ajustes: {designación:
{campo: valor}}`; `services/escenario_ajustes.py` los valida contra el tablero y el snapshot
(`cosim_snapshot`) los pone encima de los del `add_device` en una COPIA del `ModeloElectrico`
(`dataclasses.replace`: el del documento es inmutable y no se toca). El snapshot con
`{"-T2": {"sobrecarga_s": 1}}` de prueba es el MISMO (dispositivos y red hacia el worker) que el de
un documento con ese ajuste en su `add_device`; el atasco parcial de 650 N·m dispara el variador
por sobrecarga a 7,4 s con el ajuste y no dispara sin él.

Decisiones tomadas al implementar (vetables):

- **F2-a — `ajustes` vive DENTRO del dict del escenario, no al lado en `EscenarioIn`.** El
  contrato decía «`EscenarioIn` gana `ajustes`»; leído el código, el escenario es UN dict que se
  guarda tal cual (`doc.escenarios[n]["escenario"]`), se firma entero (`hash_escenario`) y viaja
  igual inline (`simulate(escenario={…})`, `test_plc`, la sesión en vivo, que lo copia de su base).
  Dentro, D6 sale sola: los ajustes entran a SU hash y un escenario sin ellos es byte-igual (no se
  inserta `"ajustes": {}` al guardar). Al lado habría pedido otro campo guardado, otro hash y otro
  camino para cada uno de esos clientes. Por eso `EscenarioIn` y el schema de `set_scenario` no
  cambian: sólo su docstring (golden).
- **F2-b — Al declarar, 400 sólo si el tablero ya existe**; sin tablero, se validan al correrlo
  (el aviso «todavía no declara tablero» de siempre). Con tablero, una designación desconocida es
  400 (no aviso, como una acción): un ajuste mal dirigido no hace nada en silencio. El texto suma
  «son ajustes de PRUEBA … los del proyecto van en add_device.ajustes».
- **F2-c — Misma validación que `add_device`**: `validar_ajustes` contra la ficha `modelo` del
  aparato (rangos, tipos, opcionales del tipo como `STO_categoria`) y, en uno de aire,
  `commands/neumatica_eval._ajustes` (rangos de la ficha neumática + su lado eléctrico). Se importa
  el privado en vez de copiarlo: una sola regla.
- **F2-d — Los ajustes obligatorios que faltan se miden sobre el PROYECTO**, antes de aplicar los
  de prueba: un escenario no completa un tablero incompleto (el ERC seguiría pidiéndolos).
- **F2-e — El resultado los lista como `ajustes_de_prueba`** `[{dispositivo, ajuste, valor,
  proyecto}]` (`proyecto` = el del `add_device`, o el de la ficha si no lo fija), en la respuesta y
  en el resultado guardado, sólo si hubo (sin ellos, byte-igual), más una hipótesis por ajuste
  («… es un ajuste de PRUEBA de este escenario (el proyecto: 60); el documento no cambia»). Un
  deducido de la pieza que el escenario pisa deja de figurar como deducido.
- **F2-f — D7 tenía una fuga en el núcleo**: la memoria del aire (`neumatica.lecturas`) toma el
  tiempo de carrera del escenario NOMINAL; uno con ajustes de prueba (otra presión regulada)
  podía serlo. `_sano` lo cuenta como de falla (sólo si no hay otro). El manual de puesta en
  marcha y las cifras eléctricas que lee una extensión (`medidas_electricas.cifras`) no se tocan:
  el resultado trae `ajustes_de_prueba` para que la extensión lo salte (F3).
- **F2-g — `COSIM_EPOCH` no sube** (sólo la huella; `services/escenario_ajustes.py` entra a sus
  `ARCHIVOS`). Evidencia: 5 escenarios del banco (marcha con cajas, seta y atasco parcial por
  variador; marcha y atasco parcial en directo) corridos con el código de 712a9bd y con la rama
  dan la MISMA huella, hipótesis, finales, claves del resultado y del compacto, hash de escenario y
  firma de los dos documentos.

Tests: `tests/test_ajustes_escenario.py` (nuevo: forma, validación como `add_device` con sus
cuatro errores y sin efecto parcial, sin tablero, la copia y el valor del proyecto, el hash de un
escenario de la base como literal calculado en 712a9bd y su resultado vigente, el vencimiento sólo
del escenario cuyo ajuste cambió, la memoria del aire, el snapshot igual al del `add_device` y el
integral por la API: el atasco falla sin ajustes y pasa con ellos, `ajustes_de_prueba` en la
respuesta y en el guardado, `add_device`, modelo, circuito y firma intactos);
`tests/test_cosim_epoch.py` (huella + `ARCHIVOS`); golden MCP re-congelado tras revisar el diff
(sólo el docstring de `set_scenario`) y el caso «escenario con ajustes de prueba» en
`scripts/golden_mcp_casos.py`.
