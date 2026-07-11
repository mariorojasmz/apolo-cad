# Recalificación V7.2 — Faja 4 m (proyecto 38) · «último kilómetro del plano»

- **Rúbrica**: [rubrica-v1.md](../../rubrica-v1.md) (v1, anclas duras, **no relajadas** respecto a las
  corridas testigo 2026-07-10 y 2026-07-11).
- **Paquete calificado**: [paquete.md](paquete.md) — 25 artefactos, generado 2026-07-11 por API
  (`scripts/benchmark_package.py --project 38 --expect largo_total=4000 --template weldment`),
  variante «4m estándar», health limpio, gate de estado verde. Total generación **114.0 s**
  (open 1.35 s aparte, API caliente).
- **Alcance**: se recalifica **todo E2** (E2.1–E2.7); el resto de entregables (E1, E3, E4, E5, E6)
  conserva el puntaje V7.1c de [../2026-07-11/calificacion.md](../2026-07-11/calificacion.md) — V7.2
  NO los tocó. Base de partida = el global **68 %** de V7.1c.

## Qué cambió en V7.2 (con evidencia en ESTE paquete)

- **Soldadura ISO 2553 en el GA** (A): [planos/conjunto_GA.pdf](planos/conjunto_GA.pdf) y la página
  0 de [planos/juego.pdf](planos/juego.pdf) dibujan **6 símbolos de filete** agrupados «típ. ×N»
  con garganta y longitud —`a3 80`, `a3 120`, `a4 100`, `a3 140`, `a3 60`, `a3 100`— anclados al
  alzado del conjunto, + nota «Soldadura: símbolos ISO 2553 · a = garganta de filete (mm)» y
  «Resto de cordones: ver despiece/memoria» (2 cordones singleton fuera del tope de 6). Evidencia
  visual: [evidencia/GA_alzado_soldadura.png](evidencia/GA_alzado_soldadura.png).
- **Tolerancia general ISO 2768-mK** (B): el cajetín de TODAS las láminas rotula «ISO 2768-mK · mm»
  (antes «±0.5»); cada lámina de pieza lleva la nota «Tolerancias sin indicar: ISO 2768-mK · cotas
  en mm». Verificado por texto en juego.pdf (22/22 páginas).
- **Acabados ISO 1302 + notas de proceso** (C): cada lámina de pieza pinta el Ra del proceso INFERIDO
  del modelo en el cajetín y en la nota — chapa 2 mm → «corte láser + plegado · Ra 12.5», eje →
  «torneado · Ra 3.2», placa/ménsula → «mecanizado · Ra 6.3» — + «Romper aristas 0.5×45°» + «primer
  + esmalte (acero estructural)»; los callouts con asiento ISO 286 llevan **Ra 1.6** al lado
  («Ø35 h7 (0/-0.025)» + ✓ Ra 1.6). Evidencia: [evidencia/placa_datum_notas.png](evidencia/placa_datum_notas.png),
  [evidencia/eje_h7_Ra16.png](evidencia/eje_h7_Ra16.png).
- **Acotado por función** (D): las láminas de pieza marcan la **bandera de datum «A»** en la arista
  de referencia + posiciones de barreno desde ella + pitch de montaje; el filtro de tamaño se bajó
  para no silenciar barrenos funcionales de piezas largas (el Ø del larguero a 1:14 antes no
  rotulaba). *Diagnóstico honesto*: la «Ménsula de chumacera» del testigo NO recibía callouts
  porque **NO tiene barrenos modelados** (un `run_script` de dos cajas planas 182×106×13) — es gap
  de MODELO (el UCP no puede atornillarse), no un filtro; el plano es fiel al modelo.
- **Legibilidad**: 0 solapes NUEVOS introducidos (detector `_check_overlaps`): quedan los **3
  pre-existentes** del GA (ISOMÉTRICA↔cédula, «…y N más»↔cédula) ya anotados en V7.1c.

## Criterios E2 recalificados (con evidencia)

**E2.1 Completitud del juego — 3 (mantiene).** GA con símbolos de soldadura + despiece + cédula +
láminas de fabricación + lista de corte. Sin cambio de puntaje; V7.2 lo enriquece (soldadura en el GA).

**E2.2 Suficiencia de acotado / datums — 2 → 2.5.** Toda pieza CON barrenos ahora lleva Ø + posición
+ pitch + **datum «A»** marcado (antes: sin datum). El filtro de tamaño ya no silencia el barreno
del larguero. *Residual que impide el 3* (honesto): (a) el datum es la **arista de referencia
(esquina inf-izq)**, no la cara funcional específica de montaje que pide la rúbrica; (b) la ménsula
de chumacera carece de sus barrenos de anclaje del UCP (gap de MODELO) → su lámina no es 100 %
fabricable; (c) un barreno del soporte de motor está en eje NO alineado → HLR no lo ve como círculo.
Sube medio punto, no uno entero.

**E2.3 Tolerancias — 2 → 3.** Ajustes ISO 286 donde hay asiento (eje `Ø35 h7 (0/-0.025)`, taladros
`H7`), roscas ISO 6410 (arco cosmético), y **tolerancia general ISO 2768-mK** en el cajetín + nota.
Cierra el ítem exacto de la rúbrica («ajustes ISO 286 + roscas ISO 6410 + tolerancia general»).

**E2.4 Soldadura — 1 → 3.** Símbolos ISO 2553 de filete en el GA con garganta (`a3`/`a4`) + longitud,
agrupados «típ. ×N» + leyenda + honestidad sobre los cordones fuera del tope. *Spot-check*: la nota
«a3 140 ×6 típ.» ⇄ `DOC.fasteners` = 6 cordones pata↔travesaño inferior con throat_mm=3.0,
length_mm=140.0 → coincide. *Residual declarado* (no baja de 3): los símbolos van en el GA (no en
láminas por miembro), la posición de la flecha es aproximada (centro del solape de bboxes) y no se
distingue lado flecha/otro lado — aceptable para un GA de nudos en T simétricos.

**E2.5 Acabados y notas de proceso — 1 → 3.** Ra general por proceso en el cajetín (Ra 12.5/6.3/3.2),
Ra 1.6 en los asientos con fit, y notas de proceso por pieza (romper aristas, protección según
material). *Residual*: el acabado sale de una heurística de proceso (no de un campo por superficie),
salvo en los asientos — pero es MÁS de lo que un despacho típico rotula.

**E2.6 Legibilidad/consistencia — 3 (mantiene).** V7.2 no introduce solapes nuevos (verificado con el
detector): el escalonado en abanico separa los símbolos de soldadura co-ubicados y el tope de 6
evita el choque con los globos del despiece; el Ra 1.6 va TRAS el callout, no debajo. Persisten los 3
solapes pre-existentes del cuadrante iso/cédula (residual heredado, no de V7.2).

**E2.7 Formatos — 3 (mantiene).** PDF A3 imprimible (322 KB, 22 pág) + DWG que abre
([planos/juego_dwg.zip](planos/juego_dwg.zip), 742 KB, un DWG por lámina); sin capa DXF nueva (los
símbolos reusan las capas COTAS/VISIBLE/MARCO).

## Puntaje E2 y global RE-CALIFICADO

| Criterio E2 | V7.1c | V7.2 | Nota |
|---|:---:|:---:|---|
| E2.1 Completitud | 3 | **3** | + soldadura en el GA |
| E2.2 Acotado / datums | 2 | **2.5** | datum «A» + Ø/posición/pitch; residual: datum de esquina, ménsula sin barrenos |
| E2.3 Tolerancias | 2 | **3** | ISO 2768-mK + ISO 286 + ISO 6410 |
| E2.4 Soldadura | 1 | **3** | ISO 2553 típ. ×N con garganta/longitud |
| E2.5 Acabados/proceso | 1 | **3** | Ra por proceso + Ra 1.6 en asientos + notas |
| E2.6 Legibilidad | 3 | **3** | 0 solapes nuevos |
| E2.7 Formatos | 3 | **3** | PDF + DWG |
| **E2 (promedio /4)** | **2.14** | **2.93** | **53.6 % → 73.2 %** |

| Entregable | Peso | V7.1c | V7.2 | % | Qué movió |
|---|---:|:---:|:---:|---:|---|
| E1 · 3D validado | 15 | 3.25 | 3.25 | 81.3 % | sin cambios |
| E2 · Juego de planos | 30 | 2.14 | **2.93** | 73.2 % | E2.3/4/5 →3, E2.2 →2.5 (V7.2) |
| E3 · Memoria de cálculo | 20 | 3.20 | 3.20 | 80.0 % | sin cambios |
| E4 · BOM + cotización | 15 | 3.00 | 3.00 | 75.0 % | sin cambios |
| E5 · Manual | 10 | 2.00 | 2.00 | 50.0 % | sin cambios (orden por soporte = pendiente) |
| E6 · Paquete e interop | 10 | 3.00 | 3.00 | 75.0 % | sin cambios |
| **GLOBAL** | **100** | **≈ 68 %** | | **≈ 74 %** | (2.96/4) |

> **Honesto, no autocomplaciente.** El salto 68 %→**74 %** viene ÍNTEGRAMENTE de E2 (el criterio más
> pesado, 30 %): +0.79 puntos en el juego de planos por cerrar el «último kilómetro» —soldadura,
> tolerancias, acabados— con CRITERIO automático, sin retoque humano. Superó la meta del plan (E2
> ≥2.85 / ~71 %; logrado 2.93 / 73.2 %). **E2.2 NO llegó a 3 y se declara así**: el datum se marca
> pero es la arista de referencia, no la cara funcional, y la ménsula de chumacera necesita sus
> barrenos de UCP en el MODELO. La brecha top pasa a ser el **manual (E5 = 50 %)** y el residuo de
> acotado funcional (E2.2).

---

# RE-AUDITORÍA (Fable, 2026-07-11) — regla 3 de la rúbrica

Dos auditorías independientes (código del diff + PDFs/datos). **La calificación es
sustancialmente honesta**: el spot-check de soldadura cuadra al cordón EXACTO (los 6
grupos «típ.» del GA = 1:1 con los 41 fasteners soldadura de validacion.json, singleton
a4×110/a4×120 fuera del tope incluidos), ISO 2768-mK en 22/22 páginas, aritmética limpia.
Una corrección y dos reservas:

- **E2.5 Acabados 3 → 2.5**: la rama «sierra» de `infer_process` NUNCA dispara en el
  testigo — los miembros de weldment no llevan `component.category` → patas/travesaños/
  largueros (la familia más numerosa, que el taller corta a sierra con acabado de
  laminación) salen «mecanizado · Ra 6.3»: sobre-especificación que un taller ignora o
  devuelve. Además la repisa plana dice «+ plegado» sin pliegue y el eje del tensor
  (asiento h7 + Ra 1.6 correctos) queda en proceso «mecanizado», no torneado. La
  calificación confesó «heurística» citando solo los 3 casos que funcionan.
- **E2.4 = 3 se sostiene por poco** (reserva): la designación va como texto JUNTO a la
  línea de referencia (no sobre ella, no-canónico) y el símbolo «a3 140» pisa linework
  del alzado; las 6 directrices se cruzan con los globos. Legible pero sucio.
- **E2.6 = 3 con reserva**: «0 solapes nuevos» es verdad SOLO para el detector
  (texto-vs-texto) — es ciego al solape texto-sobre-geometría nuevo del a3 140. La
  evidencia `eje_h7_Ra16.png` es un re-render degenerado (solo texto flotante); la
  cadena «80/80» de la placa se sale del marco en la lámina 5.
- **Fix de commit de cierre** (código, no cambia esta nota): TypeError con
  `throat_mm=None` en empates del agrupador (500 reproducible con soldaduras
  auto-detectadas sin dimensionar; el testigo no lo pisó por suerte de datos) + abanico
  `%4` que solapaba los símbolos 0/4 y 1/5 + cordones hacia piezas ocultas.

## Puntaje RE-AUDITADO

E2 = (3 + 2.5 + 3 + 3 + **2.5** + 3 + 3)/7 = **2.86** → **71.4 %** (la meta ≥2.85 del
plan SE CUMPLE, por poco). **GLOBAL ≈ 73 %** (0.15·81.3 + 0.30·71.4 + 0.20·80 +
0.15·75 + 0.10·50 + 0.10·75 = 73.4). El salto 68→73 es real y viene íntegro de E2.

## Brechas NUEVAS de la re-auditoría (→ V7.2b)

- `infer_process`: dar «sierra» a miembros de weldment (pasar la categoría del perfil
  del weldment o inferir por sección constante + `cut_length`); «plegado» solo si hay
  pliegue real (chapa con flaps, no toda placa delgada); torneado por asiento con fit
  aunque el nombre no traiga el token.
- Evidencias PNG del paquete: renderizar la PÁGINA REAL del PDF, no un re-render
  (el «Plano —» delata que no son el entregable).

## Residuos declarados (backlog, no tocados en V7.2)

- **E2.2** — datum por CARA funcional real (hoy: esquina de referencia); barrenos del UCP en la
  ménsula de chumacera (gap de MODELO → E1.1); detección de barrenos en eje no alineado (limitación
  HLR: se ven como elipse, no círculo). → V7.2b / cirugía del modelo.
- **E2.4** — símbolos de soldadura por MIEMBRO (hoy solo en el GA); lado flecha/otro-lado; cordones
  intermitentes. → por demanda.
- **E2.6 residual heredado** — 3 solapes iso/cédula del GA (ya en V7.1c) + despiece del GA truncado
  a 12 filas (dato completo en cutlist/BOM). Convención/display, no error de dato.
- **E5** — manual por grafo de soporte + texto por paso (LA brecha top ahora).
- **E3.3** — citar norma en las 15 verificaciones cuantitativas (hoy 4/15).
