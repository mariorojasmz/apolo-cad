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
