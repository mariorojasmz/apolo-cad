# Calificación del paquete — faja-paqueteria-4m (brechas 2+3, 2026-07-23)

Cierre de las brechas restantes del ranking del 2026-07-22 (rúbrica-v2). Paquete
regenerado por la API viva (26/26 artefactos, 101.4 s en la corrida final). Se
recalifica SOLO lo tocado: **E5 (micro-pasos)** y **E3.7 (convergencia + chapa fina)**;
base = addendum del 2026-07-22 (**≈78.6 % v1-comp / ≈78.5 % v2**).

## Verificación por TEXTO del artefacto

| Claim | Evidencia (2026-07-23) | Estado |
|---|---|---|
| **Brecha 2: micro-pasos eliminados** | manual.pdf: **6 pasos** (antes 8) — «Paso 4. Rodamientos (11 pza)» absorbe los 4 M14 + 4 tuercas (su cédula los lista); secuencia Estructura → Tornillería → Rodillos → Rodamientos → Banda → Transmisión intacta. Fix de MODELO: los 8 herrajes agregados al grupo «Rodamientos» (edit del create_group c700, contrato 2/2). | ✅ CERRADO |
| **Brecha 3a: CONVERGENCIA impresa en la memoria** | memoria.pdf pág 19: «CONVERGENCIA DE MALLA (runs previos → vigente)»: «size 60 mm · FS 93.44 (Pata A36) · δ 0.0213» → «size 35 mm · FS 66.49 (Larguero A36 (+Y)) · δ 0.0231 ← VIGENTE». Serie generada EN VIVO (dos solves, 74 s + 176 s); el vigente deduplica su malla del historial. Gobernante consistente con la analítica del larguero (FS 62, 7 %). | ✅ NUEVO |
| **Brecha 3a: hipótesis/limitaciones EN el PDF** | pág 19, bloque «HIPÓTESIS Y ALCANCE»: bonded/lineal/malla/sin-pandeo/concentración + «alcance: análisis acotado a los 16 sólidos declarados…» + «nota del analista: la mesa de chapa 2 mm se analiza APARTE como placa…». Antes las hipótesis solo vivían en el JSON. | ✅ NUEVO |
| **Brecha 3b: chapa fina ANALIZADA** | Regla 19 «FEA estático lineal · Mesa desliz. 2mm OK»: la sección de mesa (c351, 901×600×2) como placa apoyada en las repisas (caras ±y), carga 75/4 kg + banda/4 + peso propio → **σ_vm 21.2 MPa · FS 11.78 · δ 1.43 mm**, máx NO en el encastre. Spot-check a mano (franja apoyada, q≈400 N/m², b=0.56 m, t=2 mm): σ ≈ 0.75·q·b²/t² ≈ 23.5 MPa — el FEA (21.2) al 10 %. ✓ | ✅ NUEVO |
| Nota FEA 35 mm post-cirugía | FS gobernante 66.49 (antes 64.61): la geometría ganó los 16 barrenos de la brecha 1 — coherente. Sustitución «FS = 250 / 3.76» = 66.5 ✓. | ✅ |

## Re-puntaje (solo lo tocado)

- **E5 · Manual = 3.0 (se SOSTIENE)** — el residual de los micro-pasos quedó cerrado y
  el manual vuelve al estado limpio del 2026-07-20 (6 pasos, herraje correcto por paso).
  Honesto: arreglar un residual que no bajaba de 3 no sube de 3; el residual que SÍ
  queda es el orden fino intra-grupo (heurístico).
- **E3.7 · FEA = 3.5 → 4** — el ancla de 4 exige «convergencia demostrada (malla
  refinada, gobernante consistente con la analítica) y limitaciones declaradas (qué NO
  se malló y por qué)»: la serie 60→35 mm está IMPRESA con la gobernante moviéndose
  hacia la analítica; el alcance, la nota del analista y las exclusiones están EN el
  PDF; y la chapa fina que no entra al bonded tiene SU análisis aparte (regla 19,
  contrastado a mano). E3 v2 = (5·3.35 + 3 + 4)/7 = **3.393** (84.8 %).

| GLOBAL | v1-comparable | v2 |
|---|:---:|:---:|
| 2026-07-22 + addendum | 78.6 % | 78.5 % |
| **2026-07-23 (brechas 2+3)** | **≈ 78.6 %** (sin cambio: E3.6/7 son v2) | **≈ 78.8 %** |

v2 = 0.15·87.5 + 0.30·75.0 + 0.20·84.82 + 0.15·75 + 0.10·75 + 0.10·75 = **78.8 %**.

## D.1 — decisión razonada: RETIRADO del backlog (no se ejecuta)

Los 24 pernos de anclaje a-medida viven en PATRONES PARAMÉTRICOS anidados (c147→c148→
c149/c1114) que siguen a las patas en las variantes. Sustituirlos por 24
`insert_component` de catálogo con posiciones literales sería una **regresión de
parametricidad** (el patrón sistémico que V6.4b purgó) a cambio de cosmética de BOM — y
la cédula YA los lista como COMPRA con peso (1.8 kg), la memoria los verifica por los
`fasten` declarados, y el lint los reconoce. Un perno de anclaje real (expansión/cuña)
además NO es un DIN 933: modelarlo como tal sería MENOS fiel. Si el negocio pide ref de
catálogo para anclas: familia nueva «anclajes» en YAML + patrón de componentes — proyecto
propio, no una cirugía cosmética. Con esto, la familia D.1 queda CERRADA por decisión.

## Cambios al proyecto 38 (declarados)

- 8 herrajes de chumacera agregados al grupo «Rodamientos» (edit de c700).
- FEA del bastidor re-corrido 60 mm → 35 mm (misma geometría post-brecha-1) para generar
  la serie de convergencia en vivo; persiste el 35 mm como vigente con historial.
- FEA nuevo persistido: mesa c351 (placa 2 mm, fea_static).

## Brechas restantes (backlog vivo)

1. **E2 fino** (74.1 %→, peso 30): E2.5 acabados/proceso y E2.3 tolerancias finas; el
   datum funcional visible espera un modelo cuyo contacto no coincida con la esquina.
2. **Orden fino intra-grupo del manual** (heurístico — E5 a 3.25+).
3. **E3.6 → 4**: cadenas de cotas para el resto de interfaces ajustadas (tensor,
   rodillos de retorno).
