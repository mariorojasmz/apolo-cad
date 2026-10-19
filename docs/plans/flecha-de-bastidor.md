---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: Sólo el plan; nada construido. Espera saldo de tokens (Mario, 2026-10-10)
descripcion: La memoria de cálculo verifica la flecha y la tensión de cualquier viga del bastidor, aunque la máquina no salga de una plantilla
---

# La memoria calcula las vigas de cualquier bastidor

## Estado y origen

Al cambiar los largueros de la piloto (proyecto 2) a ángulo L 75×6, `engineering_check` respondió
«No hay ningún transportador»: la flecha del larguero se calculó A MANO (0.57 mm con carga
repartida, 0.82 mm con 100 kg puntual; límite L/240 = 7.1 mm). La máquina se armó pieza por pieza,
no con `create_conveyor`, y las reglas de `library/rules.py` (`detect_conveyor`) sólo reconocen
esa forma. Parte de [revision-de-taller](revision-de-taller.md).

## El problema / lo que hay hoy

- Las verificaciones universales de `report.structure_engineering_check` cubren pernos,
  soldaduras, L10, pandeo de patas y vuelco, pero no la flexión de una viga entre apoyos.
- La memoria de una máquina «a mano» queda sin la verificación más básica de su bastidor.

## Decisiones (para vetar)

- **D1. Detectar vigas por el grafo de uniones**: una pieza de perfil cortable (catálogo
  `cuttable`) con ≥ 2 uniones declaradas a piezas que llevan a tierra = viga; los apoyos son esas
  uniones, proyectadas sobre su eje longitudinal.
- **D2. Cargas**: peso propio + masas de lo que cuelga de ella (ya existe `loads.hanging_load_kg`)
  + la carga útil de `requirements` (`carga_kg`, repartida por las vigas que tocan lo portante;
  ficha de [revision-de-taller](revision-de-taller.md)). Hipótesis declaradas en el bloque `calc`.
- **D3. Modelo**: viga continua sobre sus apoyos (rigideces del catálogo: I y W por eje), flecha
  contra L/240 (AISC, como hoy en el eje) y tensión contra σ_adm = 0.6·fy; bloque `calc` con
  norma real.
- **D4. Sin duplicar**: si la máquina sí es un `create_conveyor`, manda la regla existente y esta
  se omite para esas vigas.

## Fases

- **F0 (S, sólo lectura)**: listar qué piezas del proyecto 2 detectaría D1 (deben salir los dos
  largueros y los travesaños) y comparar contra el cálculo a mano de la bitácora.
- **F1 (M, `library/engineering`)**: viga continua pura + datos de sección por familia, con tests
  de casos de libro.
- **F2 (S, `services`)**: detección D1, cargas D2 y la regla en `engineering_check` / memoria.
- **F3 (S, verificación)**: memoria del proyecto 2 con la flecha de los largueros.

## Lo que este plan NO hace

- No reemplaza al FEA (que ya existe para lo que no es viga).

## Riesgos

- Grafos con uniones raras (una pieza apoyada en sí misma, contactos) → sólo uniones
  soldadura/perno cuentan como apoyo; el resto se declara en `no_aplica`.

## Bitácora

### F1 (2026-10-19): viga continua y secciones por familia

- **`library/engineering/viga_continua.py`** (puro, stdlib): `viga_continua(largo_mm, ei_nmm2,
  apoyos, cargas) → ResultadoViga` con `Apoyo(x_mm, tipo="apoyo"|"empotramiento")`,
  `CargaPuntual(x_mm, p_n)`, `CargaRepartida(q_n_mm, desde_mm=0, hasta_mm=None)` y
  `q_peso_propio_n_mm(kg_por_m)`. Devuelve flecha y |M| máximos con su x, M+ y M−, reacciones
  por apoyo (orden de entrada, + arriba; negativa = tracción) y `tramos` (`vano`/`voladizo`,
  cada uno con su flecha máxima: el criterio L/240 de F2 va por tramo, no por viga). Método:
  rigidez directa con elementos de Hermite y cargas nodales consistentes (nodos EXACTOS en
  Euler-Bernoulli) + solución particular empotrada dentro de cada elemento → elástica y
  momento exactos; la malla (≤ L/120, 10 muestras por elemento) sólo ubica el pico. Solver de
  banda (semibanda 3): 5 ms una viga de 4 m.
- **`library/engineering/secciones.py`**: `seccion_catalogo(builder, params) → Seccion | None`
  (A, I y W por eje LOCAL del builder, `i_min` principal, `fuente`, `norma`). Ángulo, UPN e IPE:
  tabla de EN 10056-1 / DIN 1026-1 / EN 10365 cuando los params calzan con la designación
  (todas las variantes del catálogo calzan; lo prueba un test que lee los YAML); fuera de tabla,
  geometría prismática declarada. Tubos `rect_tube`/`round_tube` (ASTM A500): AISC 360-16 §B4.2
  (t = 0.93·t_nom) y radio exterior 2t; contra las tablas del AISC Manual: HSS 2×2×1/8,
  3×3×3/16, 4×4×1/4 y 6×6×1/4 a ±1 % en A, I y S. `cylinder` macizo. `profile` (ranurado de
  aluminio) y `leg` → `None` con motivo en `SIN_SECCION`: su I es de fabricante y el modelo
  es macizo (sobrestimaría). Ningún YAML tocado → sin `GEOM_CACHE_EPOCH` (y sin pisar el
  trabajo paralelo de perfiles-con-acuerdo en `13_perfiles_abiertos.yaml`).
- **Tests** (101): simplemente apoyada uniforme y puntual (centrada y excéntrica), voladizo
  (puntual y uniforme), vano + voladizo (reacción en tracción), biempotrada, continua de 2 y 3
  vanos iguales contra los coeficientes de tabla (0.375/1.25, −0.125, 0.0703, 0.00542 ·
  0.4/1.1, −0.10, 0.08, 0.025, 0.0069) y dos vanos desiguales (uniforme y puntual) contra la
  ecuación de los tres momentos + superposición. Secciones: AISC, W = I/c con el centroide
  publicado y tabla vs. prismático (las razones salen suaves en toda la serie: sin errores de
  transcripción). Capas: AST + subproceso sin OCCT/doc/catálogo (`test_capas_viga.py`).
- **Medido, para F2**: el prismático del UPN queda 12–15 % SOBRE la tabla en el eje débil (ala
  cónica); IPE 3–5 % bajo; ángulo 2–4 % sobre. Un ángulo L flecta por su eje principal débil
  si nada lo arriostra (`i_min` = Iv, ≈ 0.41·I en el L 75×6): F2 decide cuál usa y lo declara.
- Intento fallido: el primer test de UPN exigía tabla ≈ prismático a ±10 % en el eje débil y
  cayó en las 7 alturas (razón 0.867–0.890, el ala cónica) → banda medida [0.85, 0.92].
  Tolerancias: 1e-6 donde el pico cae en un nodo, 1e-5 en picos muestreados (resolución
  ≈ L/1200 → ~1e-6 relativo, demasiado justo para 1e-6).
