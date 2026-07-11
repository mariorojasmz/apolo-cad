# Recalificación V7.1c — Faja 4 m (proyecto 38)

- **Rúbrica**: [rubrica-v1.md](../../rubrica-v1.md) (v1, anclas duras, **no relajadas** respecto a la
  corrida testigo del 2026-07-10).
- **Paquete calificado**: [paquete.md](paquete.md) — 25 artefactos, generado 2026-07-11 por API
  (`scripts/benchmark_package.py --project 38 --expect largo_total=4000`), variante «4m estandar»,
  health limpio, gate de estado verde. Total generación 455.1 s.
- **Alcance**: se recalifican **solo los criterios que V7.1c tocó** (E1.1, E1.2, E2.1, E2.6, E3.2,
  E3.5); el resto conserva el puntaje **re-auditado** (Fable) de
  [../../faja38/2026-07-10/calificacion.md](../../faja38/2026-07-10/calificacion.md). Base de partida
  = el global re-auditado **62 %**, no la autocalificación 67 %.

## Qué cambió en V7.1c (con evidencia en ESTE paquete)

- **Memoria lee del MODELO, no defaults** (A): [memoria.pdf](memoria.pdf) verificada por texto —
  «407 kg / **6 patas**» (era 8), «239 kg / **2 larguero(s)**» (era 4), «**Ø eje: 35 mm**» (era 30,
  FS de flexión sube 1.43 → **2.27**), y L10 con «**(T1+T2)/2 de la banda**: 0.771 kN» (era 0.184 kN
  solo-producto → L10 baja de ~761 M h a ~10.3 M h, honesto). Recomputado también por `/api/checks`.
- **Cirugía del modelo 38** (B): patrón de anclaje completado a **24 pernos M12** (comando `c1114`
  paramétrico = c147 replicado por el mismo 3×2 de las placas → sigue `long_centros`/`larg_cy`);
  `c704` declarado (`fasten` contacto→c703 + grupo **Transmision**). `validacion.json`:
  **soundness 0 flotantes** (era 1), **gravity no cae ninguna pieza** (c704 caía 452.5 mm),
  `get_bom` = **24** pernos, c704 con grupo. Revisión guardada (id 80).
- **Compras vs fabricación + títulos** (C): [planos/juego.pdf](planos/juego.pdf) baja de **32 → 22
  páginas** (los ~10 planos de fabricación de pernos/pies/banda desaparecen — ya no reciben lámina ni
  fila de corte); la LISTA DE CORTE y la CÉDULA ya **no dicen «Sin título»**; la cédula lista las
  compras a-medida (banda, pies ×1, pernos ×24) y coincide con el BOM.
- **Consistencia BOM↔cédula** (C4): la cédula cuenta como el BOM (nombre base + por feature) →
  **Perno anclaje ×24**, **Pies niveladores ×1** (era ×16 por sólido), banda ×1 — sin fragmentación.
- **Script endurecido** (D): exit≠0 ante fallos, gate `--expect largo_total=4000`, `--out` por slug
  del proyecto, `validacion.json` con fila y bytes propios (25 filas), cédula de fallos honesta.

## Criterios recalificados (con evidencia)

**E1.1 Completitud física — 2 → 3.** Las 6 placas de anclaje llevan ahora sus **4 pernos** (24 en
total, `get_scene(name="Perno anclaje")`=24, BOM=24). `c704` deja de estar suelto. *Residual honesto*
(no bloquea el 3): pernos de anclaje modelados a-medida en vez de catálogo DIN 933; el eje fijo del
tensor sigue sin declarar ISO 286 para sus 6207 (aviso de E3.4). Evidencia: [bom.json](bom.json),
[validacion.json](validacion.json).

**E1.2 Validación — 2 → 3.** [validacion.json](validacion.json): **soundness declarada = 0
flotantes** (79/79 con camino a tierra), **gravity declarada = 0 caídas**. Las **20 interferencias**
(`truncado:false`) siguen siendo TODAS intencionales; las **4 que involucran c704** ya son pares de
unión atornillada legítimos (c704 declarado como tornillería solidaria a la ménsula). `verify` 10/10,
DOF 214. Cumple «0 flotantes» → 3.

**E2.1 Completitud del juego — 2 → 3.** El juego ya **no manda fabricar compras**: pernos M12, pies
niveladores y banda PVC salieron de la LISTA DE CORTE y de las láminas por pieza (juego 32→22 pág);
van a la CÉDULA/BOM como compra. GA + láminas de fabricación reales + LISTA DE CORTE + CÉDULA
coherentes. *Residual*: el despiece del GA aún se trunca a 12 filas (tope de display; el dato completo
está en cutlist/BOM) — no vuelve a bajar el puntaje pero se anota.

**E2.6 Legibilidad/consistencia — 2 → 3.** Resueltos los defectos que citó la re-auditoría: **las
hojas 21-22 llevan título real** (verificado en el PDF, «Sin título»=False) y la inconsistencia de
cantidades entre entregables desaparece (pies niveladores: **1 en BOM = 1 en cédula**, ya no 5/16/1;
pernos 24 en todos). *Residual DECLARADO* (no es error de dato): «Ménsulas de chumacera» = **2 en la
lista de corte** (2 brácketes físicos a cortar, correcto para el taller) vs **1 en el BOM** (línea de
conjunto) — convención pieza-física vs ítem-de-lista, con TOTAL de masa idéntico; y el truncado del
despiece del GA. Ambos anotados, no maquillados.

**E3.2 Datos de entrada — 2 → 3.** La memoria ya **no contradice el modelo**: pandeo entre 6 patas,
flecha entre 2 largueros, flexión con Ø35 (los tres LEÍDOS de la escena, no defaults). La hipótesis
«3 paquetes simultáneos» sigue siendo un default **declarado** (no un requisito), coherente con el
criterio de E3.2.

**E3.5 ¿La firmaría un ingeniero? — 2 → 3.** Con los datos de entrada corregidos (6 patas, 2
largueros, Ø35) y la **L10 que ya usa la tensión de banda** que la propia memoria calcula (T2≥385 N,
F_U=771.8 N → carga radial (T1+T2)/2 = 0.771 kN/rodamiento), desaparecen los números que un despacho
tacharía (L10 de 761 M h, Ø30 fantasma). Un ingeniero competente la revisa y firma tras validar la
hipótesis de carga. *No sube más de 3* porque E3.3 sigue en 3 (norma citada solo en 4/15
cuantitativas — no se añadieron normas en V7.1c).

## Puntaje global RE-CALIFICADO

| Entregable | Peso | Re-audit (Fable) | V7.1c | % | Qué movió |
|---|---:|:---:|:---:|---:|---|
| E1 · 3D validado | 15 | 2.75 | **3.25** | 81.3 % | E1.1 2→3 (24 pernos), E1.2 2→3 (0 flotantes) |
| E2 · Juego de planos | 30 | 1.86 | **2.14** | 53.6 % | E2.1 2→3, E2.6 2→3; E2.3/4/5 (ISO 2553/2768/acabados) siguen bajos → **V7.2** |
| E3 · Memoria de cálculo | 20 | 2.80 | **3.20** | 80.0 % | E3.2 2→3, E3.5 2→3 (lee del modelo + L10 con tensión); E3.3 sigue 3 |
| E4 · BOM + cotización | 15 | 3.00 | 3.00 | 75.0 % | sin cambios |
| E5 · Manual | 10 | 2.00 | 2.00 | 50.0 % | sin cambios (orden por soporte = pendiente) |
| E6 · Paquete e interop | 10 | 3.00 | 3.00 | 75.0 % | sin cambios |
| **GLOBAL** | **100** | **≈ 62 %** | | **≈ 68 %** | (2.72/4) |

> **Honesto, no autocomplaciente.** El salto 62 %→**68 %** viene de dos frentes baratos y verificados:
> la memoria dejó de contradecir su propio modelo (E3, +10 pt) y el 3D quedó completo y sin flotantes
> (E1, +6.5 pt). La conclusión estratégica NO cambia: **los planos (E2 = 53.6 %) siguen siendo LA
> brecha** — ISO 2553 (soldadura), ISO 2768 (tolerancia general), acabados y acotado-por-función son
> el «último kilómetro» de **V7.2**, no de V7.1c.

## Residuos declarados (backlog, no tocados en V7.1c)

- **E2.3/E2.4/E2.5** (ISO 2768 · ISO 2553 · acabados) — V7.2 «último kilómetro del plano».
- **E2.2** — datums por función + espesor de pared en tubos (C3 ya rotula la SECCIÓN de catálogo en
  la lámina; falta el acotado por cara de montaje) — V7.2.
- **E2.6 residual** — «Ménsulas de chumacera» 2 (cutlist, físico) vs 1 (BOM, ítem) y despiece del GA
  truncado a 12 filas. Convención/display, no error de dato.
- **E5** — manual por grafo de soporte + texto por paso.
- **E3.3** — citar norma en las 15 verificaciones cuantitativas (hoy 4/15).
