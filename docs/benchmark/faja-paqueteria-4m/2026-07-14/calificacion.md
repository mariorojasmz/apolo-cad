# Calificación del paquete — faja-paqueteria-4m (V7.2b, 2026-07-14)

Re-benchmark **MEDIDO** tras cerrar V7.2b (frentes A/B/C/E de código + D live). Paquete
generado de punta a punta por la API viva en **197.5 s** (25/25 artefactos OK, open 2.6 s
aparte; ver [paquete.md](paquete.md)). Modelo 38 con `health.ok=true`, variante
`largo_total=4000`, **0 avisos/errores** en `engineering_check`.

- **Alcance**: se recalifican **solo los criterios que V7.2b tocó** — E1 (fit del eje del
  tensor), E2.5 (proceso/acabados), E3.3 (norma por verificación) y E5 (manual por soporte).
  El resto conserva la nota re-auditada de V7.2 ([../2026-07-11-v72/calificacion.md](../2026-07-11-v72/calificacion.md)).
  Base de partida = global **73 %** re-auditado.
- **Regla 3 (contrapeso)**: quien genera puntúa → anclas duras + evidencia. **Honesto, no
  autocomplaciente**: NO se pudieron rasterizar las páginas del PDF (sin `pymupdf`/`fitz` en
  el venv ni endpoint SheetModel→PNG) → E2.5 y E5 se verifican por la RUTA DE CÓDIGO
  ejercitada sobre el modelo real, no por spot-check de píxel; se declara.

## Qué cerró V7.2b (con evidencia en ESTE paquete)

**D · Fit del eje del tensor + 0 avisos.** El eje del tensor de cola es FIJO (anillo interior
estacionario, carga rotatoria en el exterior) → asiento holgado **g6** (`SEAT_RECOMMENDATIONS
["rodamiento_anillo_fijo"]`, típico g6; NO k6 de prensado). Se declaró vía el nuevo parámetro
`create_take_up.eje_fit` → el eje se llama «Tensor de cola · Eje fijo **Ø35 g6** (roscado
p/ perno)» y `report.py` detecta el eje fijo → asienta g6 como **recomendado**. Resultado:
`engineering_check` sobre el 38 = **72 reglas, 0 avisos/errores** (antes: 2 avisos «el eje no
declara ISO 286»). Evidencia: [validacion.json](validacion.json) (`engineering_check`), los
4 «asiento ISO 286» en `ok`.

**Lint pre-entrega (C) sin falsos positivos.** Los 24 pernos de anclaje del 38 son MODELADOS
a-medida («Perno anclaje M12 + arandela», no catálogo) → el lint «barreno sin perno» ahora
reconoce tornillería por NOMBRE (no solo catálogo) → **0 avisos de barreno** (un primer intento
catálogo-solo daba 8 falsos positivos). El resolvedor de expresiones evita el 500 que reventaba
`/api/checks` con las posiciones paramétricas `=larg_cy-40`.

## Criterios recalificados (con evidencia)

**E1 · 3D validado — 3.25 → 3.40 (81.3 % → 85 %).** El último asiento sin declarar (el eje del
tensor) queda cerrado (g6, verificado ok); `engineering_check` pasa de 2 avisos a **0**. E1.2
validación sigue con 0 flotantes / gravity estable (heredado de V7.1c). Techo: los 24 pernos de
anclaje son a-medida, no catálogo (D.1 diferido — ver abajo), y la ménsula de chumacera sigue
sin sus barrenos de UCP en el MODELO (gap E1.1 de V7.2). Por eso E1.1 no llega a 4.

**E2.5 · Acabados / proceso — 2.5 → 3 (E2 2.86 → 2.93 / 71.4 % → 73.2 %).** Los tres residuos
que la re-auditoría de V7.2 marcó quedan cerrados: (1) los **largueros/patas HSS** (tubos
huecos a-medida) rotulan **«corte en sierra · perfil laminado»** — el `create_box`/`run_script`
esbelto con sección compacta se asierra, NO cae a «mecanizado» ni a «láser» (el tubo hueco
tiene pared fina t_eff≈3 mm pero es perfil, no chapa: se corrigió el ORDEN perfil-antes-que-chapa
+ cota transversal mínima ≥10 mm). Verificado sobre el larguero **c93** (bbox 50.8×101.6×4000,
fill 0.17 → «corte en sierra»). (2) La repisa plana de 6 mm ya NO dice «+ plegado» (fill de
bbox → sin pliegue). (3) El eje del tensor «Ø35 g6» rotula **torneado** (antes «mecanizado»).
E2 = (3+2.5+3+3+**3**+3+3)/7 = **2.93**.

**E3.3 · Trazabilidad (norma por verificación) — sube (E3 3.20 → 3.40 / 80 % → 85 %).** Las **15
verificaciones cuantitativas** citan ahora `calc.norma` (antes 4/15): 9/9 del transportador
(CEMA velocidad/capacidad/arrastre/motorización, Euler-Eytelwein adherencia, «criterio de diseño»
para par/flecha L/250 AISC/eje 0.6·σy ASME B106.1M) + 6/6 del chequeo universal (L10→ISO 281,
perno→EN 1993-1-8·ISO 898-1, soldadura→EN 1993-1-8, pandeo→Euler EN 1993-1-1, vuelco→equilibrio
estático, asiento→ISO 286·ISO 492). Regla de honestidad respetada: donde es criterio de diseño
y no norma publicada, lo dice — nunca cita inventada. Evidencia: [validacion.json](validacion.json)
(`engineering_check`), cada `calc` con `norma` no vacía.

**E5 · Manual — 2.00 → 2.5 (50 % → 62.5 %).** El manual se ordena ahora por el GRAFO DE SOPORTE
(no por el log): la «Tornillería» (24 pernos de anclaje) sube del **paso 4 al paso 2** — se
ancla el bastidor al piso ANTES de montarle la banda/mesa y los rodillos encima (cierra el gap
«los pernos de anclaje van tarde» del plan). Texto por familia (perfiles→soldar, herraje→apretar
en cruz, chumaceras→montar sobre el eje) + fusión de huérfanos. E5.1 (secuencia) sube; E5.2
(paginado por sub-ensamblajes) ya estaba bien. Techo honesto: es una reordenación de 6 grupos
GRUESOS (el orden fino intra-grupo y la cola rodamientos/transmisión siguen siendo heurísticos),
y NO se pudo verificar el render de página del PDF (sin `fitz`) → nota conservadora.

## Puntaje RE-CALIFICADO

| Entregable | Peso | V7.2 (re-aud.) | V7.2b | % | Qué movió |
|---|---:|:---:|:---:|---:|---|
| E1 · 3D validado | 15 | 3.25 | **3.40** | 85.0 % | eje del tensor g6 → 0 avisos |
| E2 · Juego de planos | 30 | 2.86 | **2.93** | 73.2 % | E2.5 →3 (sierra en largueros, sin plegado falso, eje torneado) |
| E3 · Memoria de cálculo | 20 | 3.20 | **3.40** | 85.0 % | E3.3: 15/15 verificaciones citan norma |
| E4 · BOM + cotización | 15 | 3.00 | 3.00 | 75.0 % | sin cambios |
| E5 · Manual | 10 | 2.00 | **2.50** | 62.5 % | orden por grafo de soporte + texto por familia |
| E6 · Paquete e interop | 10 | 3.00 | 3.00 | 75.0 % | sin cambios |
| **GLOBAL** | **100** | **≈ 73 %** | | **≈ 77 %** | |

Global = 0.15·85 + 0.30·73.2 + 0.20·85 + 0.15·75 + 0.10·62.5 + 0.10·75 = **76.7 % ≈ 77 %**.

> **Honesto: el objetivo del plan (~78-80 %) NO se alcanzó por ~1-3 puntos; se declara.** El
> salto 73 %→**77 %** es real y reparte entre E3 (norma en las 15 verificaciones, +5 pts de
> E3.3), E1 (0 avisos, eje del tensor cerrado), E2.5 (sierra en la familia más numerosa) y E5
> (manual por soporte, +12.5 pts). La brecha residual: **E5 (62.5 %)** sigue siendo la más baja
> (manual auto sin pulido humano; orden de grupos grueso), **E2** se queda en 73 % por E2.2
> (datum de esquina, no cara funcional; ménsula de chumacera sin barrenos de UCP en el MODELO),
> y E4/E6 no se tocaron.

## Diferido con rationale (no se hizo, se declara)

- **D.1 · Pernos de anclaje → catálogo DIN 933**: NO ejecutado. Los 24 pernos (c147 boolean_op
  «Perno M12 + arandela», patronado c148/c149/c1114) están PRESENTES, posicionados y unidos —
  la ingeniería es correcta y el lint ya no los marca. Canjearlos por catálogo es una cirugía de
  patrón + fasteners de ALTO riesgo sobre un testigo comiteado a cambio de una mejora COSMÉTICA
  de BOM (línea «fabricación» → «compra»), no cierra ningún aviso. Se difiere como refinamiento
  de BOM de menor prioridad; el lint mejorado (reconoce a-medida) hace que su ausencia no ensucie
  el chequeo.
- **E4 · Evidencias PNG = página real del PDF**: diferido — sin `pymupdf`/`fitz` en el venv ni
  endpoint SheetModel→PNG; las verificaciones de E2.5/E5 se hicieron por ruta de código sobre el
  modelo real (larguero c93, orden del manual), no por rasterización de página.
