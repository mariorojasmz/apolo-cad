# Calificación del paquete — faja-paqueteria-4m (V7.2c-cierre + V7.3, 2026-07-20)

Re-benchmark **MEDIDO** tras (a) el CIERRE de la re-auditoría de V7.2c (guarda de bracket
en `_family_order` + sufijo (k/n) vivo) y (b) V7.3 (stack-up de cadenas de cotas). Paquete
generado de punta a punta por la API viva en **88.0 s** (26/26 artefactos, open 1.27 s
aparte). Servidor LIMPIO (venv-python, sin `--reload`); commit de código `d3bd91d`
**limpio**. Modelo 38 `health.ok=true`, variante `largo_total=4000`, **0 avisos**.

- **Verificado por TEXTO extraído de los PDFs** (pypdf), no por ruta de código — la lección
  de V7.2b. Base de partida = global **77 %** re-auditado del 2026-07-18.
- **Alcance**: se recalifica **solo E5** (el manual, donde el cierre de V7.2c cerró la
  regresión) + se anota V7.3 como capacidad NUEVA (no sube nota: la rúbrica-v1 no tiene
  criterio de análisis de tolerancias — se mide cuando exista).

## Verificación por TEXTO del artefacto

| Claim | Evidencia en el ARTEFACTO 2026-07-20 | Estado |
|---|---|---|
| **Regresión V7.2c: Tornillería en el paso 1 antes que Estructura** | manual: **paso 1 Estructura · 2 Tornillería · 3 Rodillos y tambores · 4 Rodamientos · 5 Banda y mesa · 6 Transmisión**. La Estructura se monta ANTES de anclarla; Rodamientos (paso 4) ANTES del motor (paso 6). | ✅ CERRADO |
| **Sufijo (k/n) moría en el corte de 34 chars** | juego.pdf: las 3 láminas de la ménsula del motorreductor rotulan **(1/3) · (2/3) · (3/3)** (verificado por regex sobre el texto). | ✅ CERRADO |
| **V7.3: sección de cadenas de cotas en la memoria** | memoria.pdf: «Cadena de cotas», ambas cadenas testigo («asiento eje motriz», «altura bastidor»), términos «peor caso» y «RSS», norma «ISO 2768-1 + ISO 286». | ✅ NUEVO |
| Lints pre-entrega serializados | validacion.json trae `lints_pre_entrega: []` (auditable, modelo sano); consola: «0 aviso(s) — modelo sano». | ✅ |

## E5 · Manual — 2.75 → 3.00 (68.8 % → 75 %)

El cierre de la re-auditoría de V7.2c eliminó la inversión que la había bajado: el manual
YA ordena **Estructura (paso 1) → Tornillería de anclaje (paso 2)** — se arma y posiciona
el bastidor antes de anclarlo al piso — y las chumaceras (Rodamientos, paso 4) van ANTES
del motorreductor (Transmisión, paso 6). El texto por familia funciona (soldar en
Estructura, «apretar en cruz» en Tornillería). **E5.1 → 3** (secuencia físicamente
correcta) y **E5.2 → 3** (paginado por sub-ensamblajes + texto por familia + sin pasos
imposibles). *Residual honesto* (no baja de 3): el orden fino intra-grupo sigue siendo
heurístico (grupos gruesos), pero ningún paso exige algo aún no montado.

## V7.3 · Stack-up de cadenas de cotas (capacidad NUEVA, no sube nota)

Apolo ahora VERIFICA que la suma de tolerancias cierra el ajuste (peor caso + RSS), algo
que SW/Inventor venden como add-in manual (TolAnalyst). Dos cadenas testigo declaradas en
el 38, ambas CIERRAN (nivel despacho: un buen diseño cierra sus cadenas):
- **asiento eje motriz Ø35**: juego bore−eje (fit ISO 286 h7) = peor caso [0, 0.046] mm ⊆
  requisito [0, 0.05] → el eje DESLIZA en el inserto UC ✓.
- **altura bastidor soldado**: pata + larguero (bbox VIVO, se re-mide solo) = 776 mm, peor
  caso [773.2, 778.8] ⊆ [770, 782] ✓.
La memoria las incluye con fórmula/sustitución/veredicto/norma. **No sube E3** (la
rúbrica-v1 no tiene criterio de stack-up); se anota como capacidad que un despacho valora
y que ningún incumbente entrega INTEGRADA a la memoria sin add-in.

## Puntaje RE-CALIFICADO (desde el 77 % del 2026-07-18)

| Entregable | Peso | 2026-07-18 (re-aud.) | 2026-07-20 | % | Qué movió |
|---|---:|:---:|:---:|---:|---|
| E1 · 3D validado | 15 | 3.375 | 3.375 | 84.4 % | sin cambios |
| E2 · Juego de planos | 30 | 2.93 | 2.93 | 73.2 % | sin cambios (fit por pieza + revolución ya cerrados en V7.2c) |
| E3 · Memoria de cálculo | 20 | 3.35 | 3.35 | 83.8 % | + sección stack-up (capacidad, sin bump de nota) |
| E4 · BOM + cotización | 15 | 3.00 | 3.00 | 75.0 % | sin cambios |
| E5 · Manual | 10 | 2.75 | **3.00** | 75.0 % | regresión de Tornillería-paso-1 CERRADA (medido) |
| E6 · Paquete e interop | 10 | 3.00 | 3.00 | 75.0 % | sin cambios |
| **GLOBAL** | **100** | **≈ 77 %** | | **≈ 78 %** | |

Global = 0.15·84.4 + 0.30·73.2 + 0.20·83.8 + 0.15·75 + 0.10·75 + 0.10·75 = **77.6 % ≈ 78 %**.

> **Honesto: la meta 78-80 % se toca por el borde inferior, esta vez LEGÍTIMO** (el 78 %
> del 2026-07-18 era autocalificación con la regresión dentro; corregido a 77 %, y AHORA el
> cierre de esa regresión —medido en el artefacto— sube E5 a 3.0 real → 77.6 %). El salto
> 77→78 viene ÍNTEGRO de E5 (manual sin la inversión). V7.3 añade una capacidad que la
> rúbrica-v1 aún no puntúa. **Brechas residuales**: E2.2 (datum de esquina, no cara
> funcional; ménsula de chumacera sin barrenos de UCP en el MODELO — gap de E1.1), el orden
> fino inter-grupo del manual, y D.1 diferido (24 pernos de anclaje a-medida vs catálogo).

## Cambios al proyecto 38 (declarados)

- **2 cadenas de cotas declaradas** (metadato, se persisten): «asiento eje motriz Ø35» y
  «altura bastidor soldado». Es la declaración de un artefacto de ingeniería real (como los
  requisitos), no una modificación de geometría. Único cambio persistente de esta corrida.
