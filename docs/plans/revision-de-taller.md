---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: Sólo el plan; nada construido. Espera saldo de tokens (Mario, 2026-10-10). Es el primero de la serie; dueño Mario
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
- **D4. Bucle defecto → regla**: cada hallazgo confirmado (del revisor o de Mario) se corrige en
  el modelo Y deja algo durable: una línea en `guidelines.py`, un lint con test, o una
  observación en el plan que corresponda. Se anota en `docs/defectos.md` (tabla: fecha, máquina,
  defecto, quién lo vio, regla que lo previene).
- **D5. Métrica**: defectos que Mario encuentra por máquina entregada. Meta: la segunda máquina
  con la mitad que la piloto (4).

## Alternativas descartadas

- Que el mismo modelador «se revise» con una checklist: es lo que hay hoy (guidelines) y dejó
  pasar los cuatro.
- Ficha como comando del log: es metadato (raíz § Metadato ≠ comando).
- Revisor por API Claude dentro de Apolo (chat de la app): más caro de construir; el subagente de
  Claude Code sirve ya y se puede portar después.

## Fases

- **F0 (S, sólo lectura)**: correr a mano el revisor sobre la revisión 2 del proyecto 2 (antes de
  los arreglos) con las preguntas de D3 y medir cuántos de los 4 defectos encuentra. Si < 3, las
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
