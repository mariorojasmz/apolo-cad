---
estado: en curso
nota: contrato de Claude con criterio delegado (2026-10-25), vetable por número; siguen F1 (cotización identificada y nota acotable) ∥ F2 (ajustes de aparato por escenario)
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
