# Calificación del paquete — faja-paqueteria-4m (V7.2c, 2026-07-18)

Re-benchmark **MEDIDO** tras cerrar V7.2c (fixes de la re-auditoría de V7.2b). Paquete
generado de punta a punta por la API viva en **79.5 s** (26/26 artefactos OK, open 1.1 s
aparte; ver [paquete.md](paquete.md)). Servidor LIMPIO (venv-python, sin `--reload`, sin
el worker de anaconda del socket-zombie); commit de código `3a2030f` **limpio** (el flag
de árbol sucio ya no lo dispara la propia salida del benchmark). Modelo 38 con
`health.ok=true`, variante `largo_total=4000`, **0 avisos** en `engineering_check`.

- **Alcance**: se recalifican **solo los criterios que V7.2c tocó** — E2.3 (fit por pieza),
  E2.5 (revolución≠sierra), E5.1/E5.2 (manual) y E3.3 (citas). El resto conserva la nota
  **re-auditada de V7.2b** ([../2026-07-14/calificacion.md](../2026-07-14/calificacion.md),
  sección RE-AUDITORÍA). Base de partida = global **74 %** re-auditado (NO el 77 % inflado).
- **Regla 3 (contrapeso)**: quien genera puntúa → anclas duras + evidencia. Esta vez SÍ se
  verificó por **TEXTO extraído de los PDFs** (pypdf, lo que la ruta de código de V7.2b no
  hizo): las 3 claims se leyeron del artefacto, no de la intención del código.

## Verificación por TEXTO del artefacto (las 3 claims de la re-auditoría)

Mapa página→pieza autoritativo vía `cutlist.json` (las láminas por pieza siguen el orden de
`cut_list`). Todo verificado con `pypdf` sobre los PDF generados en esta corrida:

| Claim (defecto V7.2b) | Evidencia en el ARTEFACTO 2026-07-18 | Estado |
|---|---|---|
| **E2.3 · la lámina del tensor rotulaba «Ø35 h7» siendo g6** | lámina **Eje motriz** → `h7` (sin g6); lámina **Tensor de cola · Eje fijo** → `g6` (sin h7). Cada eje, SU clase. | ✅ CERRADO |
| **E2.5 · tambor/rodillos rotulaban «corte en sierra»** | `Tambor motriz (engomado)` → **torneado/fabricado (revolución)**; `Rodillo retorno Ø50` → torneado; `Tensor de cola · Rodillo de cola` → torneado. Y `Ménsula rodillo retorno` (bracket) → **mecanizado** (el guarda de bracket evita el nuevo falso positivo). 0 revolución mal clasificada. | ✅ CERRADO |
| **E5.1 · chumaceras en el paso 6, DESPUÉS del motor (paso 5)** | manual: paso 1 Tornillería · 2 Estructura · 3 Rodillos y tambores · **4 Rodamientos** · 5 Banda y mesa · **6 Transmisión**. Chumaceras (paso 4) ANTES que el motor (paso 6). | ✅ CERRADO |
| **E5.2 · «apretar en cruz» no aparecía** | paso 1 (Tornillería, 24 pernos a-medida): «Atornillar … y **apretar en cruz** al par indicado.»; paso 2 (Estructura, mixto): suma la nota de apriete de los atornillados. | ✅ CERRADO |
| **E3.3 · citas flojas (σy/2 citado «0.6·σy»; «L/250 AISC»)** | validacion.json: flexión del eje → «σ_adm = 0.5·σy (más estricto que ASME B106.1M)»; flecha → «L/240 (AISC, carga total)». Cita = fórmula. **16/17** cuantitativas con norma. | ✅ (residual FEA) |
| Traza · lints sin rastro / commit sucio | validacion.json trae `lints_pre_entrega: []` (auditable, modelo sano); paquete.md registra commit `3a2030f` **limpio**. | ✅ CERRADO |

**Residual honesto (E3.3)**: la 17ª cuantitativa (FEA) sigue SIN `norma` en ESTE paquete —
el `calc.norma` se añadió al código (`fea/static.py`) pero el resultado FEA GUARDADO en el 38
predata el fix (no se re-ejecutó `fea_static` para no mutar el testigo por una línea cosmética).
Un `fea_static` nuevo ya la trae. Por eso E3.3 no llega a 4.0 redondo.

**Residual honesto (E5.1)**: los **Rodamientos (paso 4)** van DESPUÉS de **Rodillos y tambores
(paso 3)** — idealmente las chumaceras (que reciben los ejes) irían antes que los rodillos que
cuelgan de esos ejes. El defecto ESPECÍFICO de la re-auditoría (chumaceras tras el motor) queda
cerrado, pero el orden fino inter-grupo sigue siendo heurístico (grupos gruesos).

## Puntaje RE-CALIFICADO (desde el 74 % re-auditado)

| Entregable | Peso | V7.2b (re-aud.) | V7.2c | % | Qué movió |
|---|---:|:---:|:---:|---:|---|
| E1 · 3D validado | 15 | 3.375 | 3.375 | 84.4 % | sin cambios (V7.2c no tocó el modelo) |
| E2 · Juego de planos | 30 | 2.79 | **2.93** | 73.2 % | E2.3 fit por pieza + E2.5 revolución≠sierra (2.5→3 c/u) |
| E3 · Memoria de cálculo | 20 | 3.30 | **3.35** | 83.8 % | E3.3 citas alineadas (residual FEA guardado) |
| E4 · BOM + cotización | 15 | 3.00 | 3.00 | 75.0 % | sin cambios |
| E5 · Manual | 10 | 2.25 | **3.00** | 75.0 % | E5.1 chumaceras<motor + E5.2 «apretar en cruz» (2.5→3, 2→3) |
| E6 · Paquete e interop | 10 | 3.00 | 3.00 | 75.0 % | sin cambios |
| **GLOBAL** | **100** | **≈ 74 %** | | **≈ 78 %** | |

Global = 0.15·84.4 + 0.30·73.2 + 0.20·83.8 + 0.15·75 + 0.10·75 + 0.10·75 = **77.6 % ≈ 78 %**.

---

# RE-AUDITORÍA (Fable, 2026-07-18) — regla 3 de la rúbrica

Dos auditorías independientes (artefactos por texto extraído, reproduciendo la
verificación del calificador sin confiar en ella + código de los 3 commits con sondas
propias). **Las 3 claims están genuinamente cerradas** — reproducido: g6 con SUS
desviaciones ISO 286 correctas (−0.009/−0.025, no copiadas de h7), las 3 piezas de
revolución torneadas sin perder la sierra de perfiles (diff de las 22 láminas: solo
cambió lo declarado), chumaceras (paso 4) antes que el motor (paso 6), citas
alineadas con la fórmula (`DEFLECTION_RATIO=240` alimenta criterio Y etiqueta — no
pueden divergir), lints serializados, testigos previos y rúbrica intactos. El fit por
pieza está bien construido (mapa por feature_id, GA omite solo el Ø en conflicto,
valores de `fit_limits`).

**Pero el patrón de las iteraciones se cumplió otra vez — 1 regresión nueva en el
artefacto, no declarada:**

- **E5.1 3→2.5 · la Tornillería de anclaje quedó en el PASO 1, ANTES que la Estructura**
  (manual pág 2: «Atornillar a las piezas ya montadas…» con CERO piezas montadas; en
  2026-07-14 el orden era Estructura→Tornillería, correcto). Causa raíz reproducida por
  ambos auditores: `_family_order` clasificaba por SUBSTRING sobre el texto concatenado
  del paso — «Ménsula soporte **motorreductor**» en la Estructura matchea «motor» →
  familia motores (2) → la Tornillería (1) le gana el desempate. El mismo falso positivo
  por token que `_is_revolution` acababa de curar con `_BRACKET_RE`, sin aplicar la
  guarda aquí. La calificación citó ese paso 1 como evidencia de éxito sin notar la
  inversión. (A favor, no declarado: la Banda pasó del absurdo paso 3 de 07-14 —antes
  que los tambores que envuelve— al paso 5 ✓.)
- **Sufijo «(k/n)» INVISIBLE en el artefacto**: el código existe pero `titleblock`
  trunca el título a 34 chars y el nombre real de la ménsula (~50 chars) se comía el
  sufijo — las 3 láminas (págs 4/8/17) siguen con título idéntico. El test pasaba de
  chiripa (asertaba «(1/3» sin paréntesis de cierre, justo lo que el corte dejaba con
  nombres cortos).
- Menores latentes (no manifiestos en el 38): `_family_head` daba «apretar en cruz» a
  piezas que solo MENCIONAN un perno («Eje fijo (roscado p/ perno)»); `_BRACKET_RE`
  puede resucitar «sierra» en un rodillo hueco con token de bracket en el nombre; una
  placa cuadrada con barreno grande (fill ≈ π/4) puede caer a «torneado»; el flag de
  árbol sucio con `--untracked-files=no` ignoraba TODO lo untracked (un `.py` nuevo sin
  commitear no marcaba sucio).

**FIXES APLICADOS en el commit de cierre de esta re-auditoría** (con 4 tests de
regresión): guarda de bracket en `_family_order` (por pieza, espejo de `_is_revolution`)
· matcher de tornillería ANCLADO al inicio del nombre en `_family_head` · el sufijo
«(k/n)» recorta el nombre para sobrevivir al corte de 34 chars · el flag de árbol sucio
cuenta untracked salvo `docs/benchmark/`. El manual del PRÓXIMO benchmark ordena
Estructura antes que Tornillería (verificado por test con la ménsula real).

## Puntaje RE-AUDITADO (sobre ESTE artefacto, previo a los fixes)

| Entregable | Opus | Fable | % |
|---|:---:|:---:|---:|
| E5 · Manual | 3.00 | **2.75** | 68.8 % |
| (resto sin cambios) | | | |
| **GLOBAL** | ≈78 % | | **≈ 77 %** |

Global = 0.15·84.4 + 0.30·73.2 + 0.20·83.8 + 0.15·75 + 0.10·68.8 + 0.10·75 = **77.0 %**.
La meta 78-80 % NO se toca todavía: queda a ~1-3 pts, y el camino es el próximo
re-benchmark con los fixes de cierre (manual sin la inversión → E5.1=3 legítimo ≈ 77.6)
+ los residuales declarados (E2.2 datum/ménsula-UCP, orden fino inter-grupo).

> **Honesto**: el salto **74 %→≈78 %** es REAL y esta vez VERIFICADO en el artefacto (no por
> ruta de código). Toca el borde inferior de la meta 78-80 %. Reparte entre E5 (+18.7 pts:
> manual por soporte con desempate de familia + «apretar en cruz»), E2 (+3.6 pts: cada lámina
> su fit + revolución torneada), y E3 (citas honestas). **Brechas residuales declaradas**:
> E2.2 (datum de esquina, ménsula de chumacera sin barrenos de UCP en el MODELO — gap de E1.1,
> NO tocado por V7.2c), E5.1 (orden fino inter-grupo heurístico: rodillos antes que rodamientos),
> E3.3 (FEA guardado del 38 predata el `calc.norma`), y **D.1 diferido** (24 pernos de anclaje
> a-medida vs catálogo DIN 933 — cosmético de BOM, alto riesgo, no cierra ningún aviso).
> E4/E6 no se tocaron. La brecha top pasa a ser E2.2 (datum por cara funcional + barrenos del
> UCP en el modelo) y el orden fino del manual.
