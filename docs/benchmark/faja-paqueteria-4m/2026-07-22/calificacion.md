# Calificación del paquete — faja-paqueteria-4m (V7.4/V7.4b/V7.5, 2026-07-22)

**Primera corrida bajo la [rúbrica-v2](../../rubrica-v2.md)** (v1 + E3.6 stack-up + E3.7
FEA; ninguna ancla de v1 relajada — se reporta también el global v1-comparable para no
romper la serie). Paquete generado de punta a punta por la API viva en **128.7 s**
(26/26 artefactos, open 1.89 s aparte). Servidor limpio (venv-python, sin `--reload`);
commit de código **`9c5bddb` limpio** (main == origin). Modelo 38 `health.ok=true`,
variante `largo_total=4000`, **0 avisos en 73 reglas, 0 lints**.

Base de partida = global **77.6 % ≈ 78 %** del 2026-07-20. Desde entonces: V7.4 (FEA
bonded de ensamblaje) + V7.4b (cierre de auditoría del FEA) + V7.5 (barrenos del UCP +
datum funcional) + fix del peso de cajetín multi-sólido.

## Verificación por TEXTO del artefacto (pypdf — la lección de V7.2b)

| Claim | Evidencia en el ARTEFACTO 2026-07-22 | Estado |
|---|---|---|
| **V7.5: ménsula de chumacera FABRICABLE** | juego.pdf pág 6: «2×Ø15.5», pitch «127» ×2 (el J del UCP207), posiciones 27.5 / 154.5 / 22 desde el datum «A», «1.93 kg», ISO 2768-mK. Cédula (pág 22): 4× PERNO-HEX-M14 + 4× TUERCA-M14; nota de montaje «Apretar 4× PERNO-HEX-M14 según par de norma». | ✅ NUEVO |
| **Fix peso multi-sólido** | pág 6 rotula «1.93 kg» (el testigo 2026-07-20 decía «0.125 kg» — pesaba la placa de acero como madera); lámina del motor intacta «0.402 kg». | ✅ CERRADO |
| **V7.4: FEA del bastidor en la memoria** | memoria.pdf pág 19: «FEA del bastidor (bonded)», malla «tet P2 · 35306 elem · size 35.0», tabla RESULTADO POR PIEZA (8 filas, gobernante primero), «FS gobernante = 64.61 en Larguero A36 (-Y)», flecha 0.023 ≤ L/240=16.667, sustitución «FS = 250 / 3.87». | ✅ NUEVO |
| **V7.4b: sustitución consistente** | 250 / 3.87 = 64.60 ≈ 64.61 reportado (recalculado a mano) — los DOS números de la pieza gobernante. | ✅ |
| **V7.3: cadenas de cotas** | memoria págs 20-21: «altura bastidor» peor caso [774.9, 777.1] y «asiento eje motriz» Σtol 0.046/RSS 0.033, «ISO 2768-1 + ISO 286 · peor caso y RSS». | ✅ (ya medido el 07-20) |
| Regresión V7.2c (fits por lámina) | pág 9 eje motriz: h7 sin g6; pág 10 tensor: g6 sin h7. Sufijos (1/3)(2/3)(3/3) vivos. | ✅ sin regresión |
| Lints/validación | validacion.json: `lints_pre_entrega: []`; consola «0 aviso(s) — modelo sano». | ✅ |

**Spot-checks obligatorios (regla 2), recalculados a mano**:
- *Memoria*: FS FEA = 250/3.87 = 64.60 ✓. Stack-up bastidor: 674.4 (ISO 2768-m → ±0.8) +
  101.6 (→ ±0.3) = 776 ± 1.1 → [774.9, 777.1] ✓ exacto; RSS ancho 2·√(0.8²+0.3²) = 1.708 ✓.
- *Láminas vs 3D*: placa 182 de ancho con barrenos a ±63.5 del centro → 91−63.5 = **27.5**
  y 91+63.5 = **154.5** del borde ✓; y: 357−335 = **22** ✓ (bbox vivo del modelo).
- *BOM* (≥3 filas): ménsulas 3.86 kg = 2 × (245 893 mm³ × 7.85e-6) ✓ · PERNO-HEX-M14
  0.075 kg = fórmula de ficha (7.85e-6·(0.785·14²·40 + 0.866·21²·8.8)) ✓ · TUERCA-M14
  0.02 kg = 2 508 mm³ × ρ ✓ (volumen del sólido exacto) · larguero 27.5 kg / 4 m ≈
  6.9 kg/m, coherente con HSS 4×2×3 ✓.
- *E1.4 EN VIVO*: aplicada «3.2m compacta» (long_centros 3806→3006): placa limpia (0
  interferencias), perno M14 toca el UCP (gap 0.0), tuerca a ras de placa (gap 0.0);
  vuelta a «4m estandar» → estado idéntico. **La cirugía de V7.5 es 100 % paramétrica.**

## Cambios por eje (evidencia arriba)

### E1 · 3D validado — 3.375 → **3.5** (87.5 %)
**E1.1 3→3.5**: el gap nombrado («ménsula de chumacera sin barrenos de UCP — el UCP no
puede atornillarse») quedó CERRADO con herraje de catálogo (M14×50 + tuercas) a la cota
real del UCP207 (J=127 medido de los slots del builder). Residuales que impiden 4: los 24
pernos de anclaje a-medida (D.1 diferido) y los pies niveladores a 13 mm de las patas
(soldaduras no modeladas como caras — hallazgo de V7.4). E1.2/E1.3 se sostienen (0
flotantes, 0 avisos; el servicio de chumaceras ahora es REAL: se desatornillan). E1.4
re-verificada en vivo esta corrida, incluyendo las features nuevas.

### E2 · Juego de planos — 2.93 → **2.966** (74.1 %)
**E2.2 2.5→2.75**: la pieza que motivó el criterio ya es fabricable SOLO con su lámina
(Ø, posiciones desde datum declarado, pitch de montaje, peso correcto). El datum por cara
FUNCIONAL existe como mecanismo (derivado de fasteners, lista por peso, fallback honesto)
PERO en este testigo ninguna lámina lo ejerce: las uniones de la ménsula son ⊥ a la
planta → datum de esquina (correcto, no funcional). No es 3 porque el criterio pide
«datums = caras de función» y el artefacto aún los muestra de esquina. Resto de E2 sin
cambios (fits por lámina, soldadura, sufijos verificados sin regresión).

### E3 · Memoria — v1-comparable **3.35** (83.8 %, sin cambios) · v2 **3.32** (83.0 %)
Criterios v1 (E3.1-E3.5) sin cambios. Nuevos v2, medidos:
- **E3.6 stack-up = 3**: las 2 cadenas críticas declaradas cierran con peor caso + RSS,
  fuentes citadas (ISO 2768-1/ISO 286) y veredicto; evaluación aislada + errores honestos
  (cierre V7.3). No 4: cobertura acotada a 2 cadenas (no toda interfaz ajustada) aunque
  los asientos ISO 286 y el «cerrada por construcción» de join_bolted complementan.
- **E3.7 FEA = 3.5**: pieza crítica (pata, FS 170) Y bastidor bonded 16 pza con FS POR
  PIEZA, hipótesis impresas (malla/BCs/exclusiones), vigencia, y el CONTRASTE fuerte:
  FEA del larguero **64.61** vs verificación analítica **62** — dos caminos
  independientes al mismo número (4 % de diferencia). La malla refinada (60→35 mm) movió
  la gobernante HACIA la analítica (convergencia real, documentada en devlog). No 4: la
  convergencia no está impresa EN la memoria (solo el run final) y la mesa de 2 mm queda
  fuera de la malla (declarado).

### E4 · BOM + cotización — **3.0** (75 %, sin cambios)
El herraje nuevo entra limpio (M14/tuercas con peso de ficha ✓ spot-check).

### E5 · Manual — **3.0** (75 %, se sostiene con residual NUEVO declarado)
Secuencia física correcta CON el herraje nuevo: pernos/tuercas de chumacera en pasos 5-6,
DESPUÉS de Rodamientos (paso 4) y antes del motor (paso 8) ✓. *Residual nuevo*: el
herraje sin grupo generó DOS micro-pasos («Pernos» 4 pza, «Tuercas» 4 pza) que un
despacho fusionaría con el paso de Rodamientos — cosmético, la secuencia no exige nada
no-montado; fix barato: agrupar c1130-1137 en «Rodamientos» (backlog).

### E6 · Paquete e interop — **3.0** (75 %)
26/26 artefactos, tiempo total **128.7 s** documentado (~10³× vs despacho, estimado);
reproducible por script; STEP 3.5 MB exportado.

## Puntaje

| Entregable | Peso | 2026-07-20 (v1) | 2026-07-22 v1-comp | 2026-07-22 **v2** | Qué movió |
|---|---:|:---:|:---:|:---:|---|
| E1 · 3D validado | 15 | 3.375 | **3.50** | 3.50 | barrenos UCP + herraje real (E1.1) |
| E2 · Juego de planos | 30 | 2.93 | **2.966** | 2.966 | ménsula fabricable + peso (E2.2) |
| E3 · Memoria | 20 | 3.35 | 3.35 | **3.32** | + E3.6 (3) y E3.7 (3.5) al denominador |
| E4 · BOM + cotización | 15 | 3.00 | 3.00 | 3.00 | — |
| E5 · Manual | 10 | 3.00 | 3.00 | 3.00 | micro-pasos nuevos (residual, no baja de 3) |
| E6 · Paquete e interop | 10 | 3.00 | 3.00 | 3.00 | — |
| **GLOBAL** | 100 | **77.6 %** | **≈ 78.4 %** | **≈ 78.2 %** | |

- v1-comparable = 0.15·87.5 + 0.30·74.15 + 0.20·83.75 + 0.15·75 + 0.10·75 + 0.10·75 = **78.4 %**.
- v2 = igual con E3 = 83.0 % → **78.2 %** (más criterios en E3 = vara más alta, declarado).

> **Honesto**: la meta 78-80 % deja de tocarse por el borde — 78.4 % v1-comparable con
> +0.8 pts MEDIDOS (E1.1 +0.5, E2.2 +0.25). Bajo la vara v2 (que ahora exige stack-up y
> FEA) el global es 78.2 % — la serie continúa con v2 de aquí en adelante. Los saltos
> grandes restantes están en E2 (74 %, peso 30): datum funcional EJERCIDO en el testigo,
> E2.5/E2.3 finos; y en fusionar los micro-pasos del manual.

## Cambios al proyecto 38 (declarados)

- **Cirugía V7.5** (sesión previa, ya en el log): 4 barrenos Ø15.5 en c685 + 4
  PERNO-HEX-M14×50 + 4 TUERCA-M14 (79→87 sólidos, 324→336 comandos). Los artefactos de
  esta corrida la reflejan.
- **FEA persistido** `group:Bastidor portante` re-corrido a 35 mm (V7.4b) — entra a la
  memoria con vigencia.
- Esta corrida NO mutó el modelo (la verificación E1.4 aplicó variante y VOLVIÓ; un solo
  undo por apply, estado final = inicial).

## Brechas accionables (ranking peso × distancia a 3)

1. **E2.2 → 3** (peso 30): que el datum funcional se EJERZA en el testigo — exige una
   lámina con señal lateral y círculos (p. ej. modelar los barrenos de la ménsula del
   motorreductor → su cara de apoyo daría datum en alzado). Emparenta con D.1.
2. **E5 micro-pasos** (peso 10): agrupar c1130-1137 en «Rodamientos» (1 comando) o
   enseñar a `order_by_support` a fusionar herraje suelto con su sub-ensamblaje vecino.
3. **E3.7 → 4** (peso 20): imprimir la convergencia de malla en la memoria + mallar la
   chapa fina (follow-up V7.4 vivo).
4. **E3.6 → 4**: cadenas para el resto de interfaces ajustadas (tensor, rodillos).
