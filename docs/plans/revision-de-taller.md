---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: F0–F3 en main (2026-10-19): revisor ciego 3½ de 4 con D3 reescrita, prompt generado desde `design/revision.py`, ficha del encargo en `requirements` y `docs/defectos.md`; falta F4 — una segunda máquina con ficha + modelador + revisor, y Mario cuenta sus defectos
descripcion: Antes de entregarte una máquina, un segundo agente la revisa con ojos de taller y cada error que encuentres se vuelve una regla que no se repite
---

# Un revisor de taller encuentra los errores antes que tú

## Estado y origen

Mario, al revisar la máquina piloto de [publicacion-tienda](publicacion-tienda.md) (proyecto 2,
«transportador-rodillos-cadena-2m»), encontró a ojo cuatro defectos que el agente entregó en
VERDE:

1. ««Pata (+Y, alimentación)» (c85), parece un perfil de aluminio y dice que es acero?»
2. ««Travesaño superior (alimentación)» (c88) a este podría estar entre las patas.»
3. «Y qué se supone que hace «Travesaño superior (centro)» (c89)?»: no tenía función (los 20
   ejes ya amarran los largueros).
4. «las tuercas "Tuerca del eje" están bastante cerca a la parte superior del larguero, tienen
   juego para girar?»: no entraba ninguna llave.

Preguntó «¿cómo evitar estos pequeños problemas a futuro?», aceptó la recomendación (revisor +
ficha) y pidió (2026-10-10): «por ahora no tenemos tokens para implementar, pero sí para
planificar, así que crea todos los planes necesarios».

## El problema / lo que hay hoy

- El criterio ya pide lo que falló: `design/guidelines.py:54-59` («Montaje y desmontaje… espacio
  para la herramienta») y la regla 7 (fabricabilidad). Pero nadie lo VERIFICA: `delivery_check`
  mide interferencias, sujeción declarada, lints e integridad; ninguna pregunta de taller.
- El mismo agente que modela es el que revisa: ve lo que quiso hacer, no lo que hizo. Los cuatro
  defectos se vieron en el viewport, no en un número.
- El agente modela adivinando datos del cliente: carga, ancho máximo del producto, si se desarma
  para transportarla. En la piloto el rodillo sobresale 5 mm sin que nadie lo decidiera.
- Cada corrección se quedó en ESA máquina; ninguna dejó una regla (salvo la tarea de perfiles,
  [perfiles-con-acuerdo](perfiles-con-acuerdo.md)).

## Lo que se revisó antes de escribir esto

- `Document.requirements` ya es metadato con endpoint (`set_requirements`/`get_requirements`) y
  las reglas caen a él ([library](../../core/apolo/library/CLAUDE.md) § requisitos): la ficha NO
  necesita formato nuevo, sólo claves nuevas.
- La regla raíz «Modelar una máquina por MCP también se delega» (CLAUDE.md § Planes) ya separa
  orquestadora y modelador: el revisor es un tercer rol con el mismo patrón.
- `render_view(isolate, zoom, section, measure)` alcanza para fotografiar de cerca sin mutar.

## Decisiones (para vetar)

- **D1. La ficha del encargo vive en `requirements`** con claves nuevas: `carga_kg`,
  `ancho_producto_mm`, `desarmable` (sí/no), `instalacion` (piso/anclado/móvil), `entorno`. Las
  que el cliente no dé, el agente las ASUME y las escribe con `asumido: true`: quedan a la vista.
- **D2. El revisor es un subagente de SÓLO LECTURA** (tools de lectura y render; ninguna que
  mute), con contexto fresco y sin el razonamiento del modelador. Recibe el id del proyecto y la
  ficha; devuelve hallazgos `{pieza, pregunta, evidencia (render/medida), severidad}`.
- **D3. Preguntas de taller fijas**, una lista en `design/` (fuente única, como guidelines): por
  cada pieza ¿qué función cumple? (si ninguna → sobra); ¿el material que se ve es el que dice?;
  ¿existe ese perfil así en el mercado?; ¿cómo se arma y en qué orden?; ¿entra la herramienta a
  cada fijador?; ¿lo que gira está guardado?; ¿cumple la ficha (ancho, carga, desarmable)?
  **Reescrita tras F0** (§ Bitácora; la pregunta de función falló dos veces). Dos preguntas de
  la estructura van como PASADA aparte, miembro por miembro, antes de las demás:
  - **Contrafactual de función**: listar TODOS los miembros estructurales (travesaños, riostras,
    patas, ménsulas) y, por cada uno, «si lo quitas, ¿qué carga pierde su camino o qué se
    desarma?». Si otro miembro ya hace lo mismo (p. ej. ejes atornillados que amarran los
    largueros), sobra. Proponer AGREGAR miembros sólo después de justificar los que hay.
  - **Marco de taller**: por cada nudo pata–travesaño–larguero, ¿forma un marco cerrado con
    apoyo a tope (la carga baja por contacto, no por pernos a cortante)? ¿Un miembro va
    montado ENCIMA de otro cuando iría ENTRE ellos? Comparar los dos extremos.
- **D4. Bucle defecto → regla**: cada hallazgo confirmado (del revisor o de Mario) se corrige en
  el modelo Y deja algo durable: una línea en `guidelines.py`, un lint con test, o una
  observación en el plan que corresponda. Se anota en [defectos](../defectos.md) (tabla: fecha,
  máquina, defecto, quién lo vio, regla que lo previene).
- **D5. Métrica**: defectos que Mario encuentra por máquina entregada. Meta: la segunda máquina
  con la mitad que la piloto (4).

## Alternativas descartadas

- Que el mismo modelador «se revise» con una checklist: es lo que hay hoy (guidelines) y dejó
  pasar los cuatro.
- Ficha como comando del log: es metadato (raíz § Metadato ≠ comando).
- Revisor por API Claude dentro de Apolo (chat de la app): más caro de construir; el subagente de
  Claude Code sirve ya y se puede portar después.

## Fases

- **F0 (S, sólo lectura)**: correr a mano el revisor sobre la revisión 1 del proyecto 2 (antes de
  los arreglos; la 2 ya trae las patas corregidas) con las preguntas de D3 y medir cuántos de los 4 defectos encuentra. Si < 3, las
  preguntas se reescriben antes de seguir.
- **F1 (S, `design/` + docs)**: lista de preguntas (D3) como módulo puro con test; plantilla del
  prompt del revisor en `docs/` y la regla de uso en CLAUDE.md raíz (una línea).
- **F2 (S, `library`/`services`)**: claves de la ficha en `requirements` (D1) con validación y
  `asumido`; `open_project` ya devuelve requisitos en el briefing.
- **F3 (S, docs)**: `docs/defectos.md` con los 4 de la piloto y su regla.
- **F4 (M, verificación)**: segunda máquina con ficha + modelador + revisor; contar los defectos
  que encuentra Mario (D5).

## Lo que este plan NO hace

- Los chequeos automáticos concretos: van en [acceso-de-herramienta](acceso-de-herramienta.md),
  [perfiles-con-acuerdo](perfiles-con-acuerdo.md) y [flecha-de-bastidor](flecha-de-bastidor.md).
- No cambia `delivery_check`: el revisor es un paso aparte, no un semáforo.

## Riesgos

- El revisor gasta tokens en cada máquina → render en baja resolución y sólo las piezas no
  repetidas (un rodillo, no los 20).
- Falsos hallazgos que cansan → severidad y evidencia obligatoria; lo que no trae render o medida
  no se reporta.

## Bitácora

### F0 (2026-10-19): el revisor a ciegas, dos corridas

En la laptop (Mario-LapTrab) el piloto se importó por SSH desde la PC principal: proyecto remoto 2
= local 74; revisiones remotas 1–4 = locales 122–125. Cada corrida, sobre una COPIA (75 = rev 2,
76 = rev 1). Revisor: subagente Opus en segundo plano, contexto fresco, sólo lectura (la única
mutación, `open_project`), prohibido leer `docs/`; recibió las preguntas de D3 (versión original)
y la orden de evidencia obligatoria. Ninguno conocía los defectos.

| corrida | revisión | #1 pata «acero» que es aluminio | #2 travesaño de alimentación | #3 travesaño del centro | #4 tuercas sin llave | costo |
|---|---|---|---|---|---|---|
| A | 2 (patas ya arregladas) | — (no aplica) | parcial: «bastidor incoherente entre extremos» | no: lo vio y propuso AGREGAR más | sí: 2,5 mm al ala, el dado pide ~13 | 22 llamadas, ~9 min, 168 k tokens |
| B | 1 (antes de todo) | sí, ALTA: perfil ranurado de extrusión «soldado» a acero | parcial (BAJA): mismo hallazgo de A | no | sí, ALTA | 28 llamadas, ~10 min, 162 k tokens |
| C (D3 reescrita) | 1 | sí, ALTA | parcial: ve los dos extremos distintos, pero da por bueno el caballete de alimentación y propone copiarlo en el motriz (Mario hizo lo contrario) | **sí**: «no lleva carga vertical; los 20 ejes con tuerca ya fijan el ancho» | sí, MEDIA | 22 llamadas, ~15 min |

**B = 2 + ½ de 4 → < 3: se reescribe D3** (hecho arriba). **C = 3 + ½ de 4 → pasa el umbral**:
el contrafactual de la pasada 1 encontró el travesaño que sobraba con el mismo razonamiento de
Mario. El #2 sigue a medias: «encima vs. entre» depende de qué extremo se toma como modelo; la
pregunta lo detecta pero no decide, y eso se acepta (el revisor pregunta, el cliente decide). La pregunta de función por pieza no
basta: el revisor la contesta con lo que la pieza HACE en el modelo, no con lo que pasaría sin
ella. Ojo con el sobreajuste: la reescritura sale de conocer los fallos; la corrida C la mide un
revisor nuevo, igual de ciego. El brief de B agregó «revisa una por una las piezas únicas
(patas, travesaños, soportes)», una pista general sin nombrar defectos.

**Lo que encontraron y Mario no vio** (las dos corridas coinciden; todo con medida):
- ALTA · la cadena motriz no se puede tensar: base del motor lisa, sin ranuras ni agujeros, y la
  transmisión vertical con la distancia entre centros clavada a 48 eslabones; además va a 4,5 mm
  de la caja del motorreductor.
- ALTA · guardas abiertas: la de transmisión abre hacia −Y y las 19 cadenas rodillo a rodillo
  quedan abiertas por debajo (ramal inferior a ~690 mm del piso).
- ALTA/MEDIA · el rodillo flota ~26 mm en el eje Ø12 liso (sin distanciadores) y las tuercas
  sólo por fuera deforman el alma hacia adentro.
- MEDIA · eje motriz Ø12 con el tiro de la cadena fuera del rodamiento: ~450 MPa en un atasco.
- MEDIA · uniones declaradas sin agujeros (M10 travesaño–larguero, anclajes de placa base) y una
  BOM que no sirve para comprar (sin 6201, sin tornillería, sin eslabones de unión).
- BAJA · UPN con alas paralelas (DIN 1026 las tiene al 8 %; lo toma
  [perfiles-con-acuerdo](perfiles-con-acuerdo.md)), tubos abiertos, sin seguro en tuercas, ni
  tablero eléctrico (lo cubre [V8](V8-maquina-viva.md)).

Esos hallazgos se convierten en reglas en F3 (`docs/defectos.md`), no en esta fase.

### F1 (2026-10-19): las preguntas como módulo y el prompt generado

- `core/apolo/design/revision.py` (puro, fuente única): `PASADA_ESTRUCTURAL` (contrafactual +
  marco de taller), `PREGUNTAS_POR_PIEZA` (función, material, perfil de mercado, montaje,
  herramienta, guardas, ficha), cada una con su «cómo» por tools; `CAMPOS_HALLAZGO` y
  `SEVERIDADES` de D2; `TOOLS_LECTURA` + `open_project` como única llamada que cambia algo.
- `docs/revisor-de-taller.md` es el prompt autocontenido, GENERADO por
  `scripts/plantilla_revisor.py`; `tests/test_revision_taller.py` exige que coincida con el
  módulo, que toda tool permitida esté marcada como lectura en `tools/catalogo.py` y que el
  «cómo» no nombre una tool que mute.
- Una línea en el CLAUDE.md raíz (§ Planes) dice cuándo y cómo correrlo.
- Decisiones propias: (a) `get_agent_notes` queda fuera y el prompt manda ignorar
  `notas_agente` del briefing: es el razonamiento del modelador (D2). (b) La pregunta de montaje
  suma «¿lo que se estira o se desgasta se puede tensar?»: el tensado de la cadena fue el ALTA
  que las dos corridas de F0 hallaron solas; no nombra ningún defecto de Mario. (c) La pregunta
  de herramienta trae las entrecaras ISO 4032 (M8 → 13, M10 → 16, M12 → 18) para que la medida
  tenga contra qué compararse.

### F2 (2026-10-19): la ficha en los requisitos

- `core/apolo/library/requisitos.py` (puro) valida los requisitos; `Document.set_requirements`
  delega (sale de `document.py`: 1047 → 1025 líneas en el trinquete). Ficha: `carga_kg` y
  `ancho_producto_mm` numéricos > 0, `desarmable` sí/no → bool, `instalacion` ∈ piso | anclado |
  móvil (sin distinguir tildes ni mayúsculas), `entorno` texto.
- `asumido`: entra como `{"carga_kg": {"valor": 15, "asumido": true}}` (o `asumidos` como lista
  o como texto «a,b», que es como lo reenvía el panel Requisitos) y se guarda PLANO más la lista
  `asumidos`. Así ningún lector de `requirements[k]` (reglas, FEA, memoria, cotización, video)
  cambia; una marca sin su valor se descarta.
- Briefing de `open_project`: `ficha` = `{faltan, asumidos}` y, si falta algo, `como` (la forma
  de pedirlo o asumirlo). La memoria de cálculo rotula «(asumido)» y escribe `desarmable` como
  sí/no.
- La carga no valida: un manifest viejo (sin ficha, o con texto libre en esas claves) abre tal
  cual (`tests/test_ficha_encargo.py`). Es metadato, nunca comando del log.
- Pendiente fuera de alcance: el docstring de la tool `set_requirements` (`mcp_server.py`,
  golden) no nombra todavía las claves nuevas ni la forma `asumido`; hoy el agente la aprende
  del `como` del briefing. El panel Requisitos de la UI tampoco las muestra (las conserva al
  guardar).

### F3 (2026-10-19): la tabla de defectos

- [defectos](../defectos.md): los 4 de Mario de la piloto y, en filas aparte de «revisor F0», los
  ALTOS de F0 (tensado de la cadena motriz, guardas abiertas, rodillo flotante) más el eje
  motriz Ø12 (MEDIA en F0, con fila propia porque es de rotura). La columna «regla» dice qué lo
  previene hoy (una pregunta de `design/revision.py`, o [acceso-de-herramienta](acceso-de-herramienta.md)
  para las tuercas) y qué falta: siete de las ocho filas siguen sin chequeo automático
  («pendiente»); sólo las tuercas tienen plan, el resto descansa en las preguntas del revisor o
  en nada (rodillo flotante, eje de una máquina armada a mano).
- La plantilla del revisor y la línea del CLAUDE.md raíz apuntan a la tabla.
