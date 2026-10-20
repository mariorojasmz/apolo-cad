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

### F2 (2026-10-19): detección, cargas y la regla en `engineering_check` / memoria

- **`services/vigas_rules.py`** (`beam_rules(doc, carga_kg)`, llamada desde `structure_rules`:
  la comparten `/api/checks` y la memoria). **D1**: perfil de catálogo cortable con sección
  (`seccion_catalogo`), HORIZONTAL (eje largo X o Y del mundo; las verticales son columnas y se
  omiten en silencio), con ≥ 2 uniones perno/soldadura a vecinos de MENOR nivel (saltos BFS desde
  los `ground`: así un travesaño soldado entre largueros se apoya en ellos y los largueros no se
  apoyan en el travesaño). Una sola soldadura = empotramiento. Apoyo = centro del solape de cajas
  proyectado en el eje (a ≤ 2 mm de un extremo se pega a él). Contacto/pegado/mate/junta no son
  apoyo → `no_aplica` con motivo, igual que lo inclinado, lo girado y el perfil ranurado.
  **D2**: peso propio (kg/m del catálogo) + lo que cuelga: el grafo se recorre de arriba abajo;
  cada pieza baja su peso + lo recibido repartido POR IGUAL entre sus vecinos de nivel inferior,
  en el solape (puntual; repartida si el solape cubre ≥ 20 % de la viga); una viga baja sus
  REACCIONES reales. Carga útil: UNA puntual móvil (`carga_kg` / nº de vigas portantes) probada
  en el centro de cada tramo y la punta de cada voladizo (envolvente); portantes = vigas que tocan
  `roles.BED_RE` o, sin cama, las más altas (± 10 mm). Sin `carga_kg`, se declara. **D4**: pieza
  de un `create_conveyor` → `no_aplica`. Vigas con los mismos números → una regla que las nombra.
  Sin vigas → `[]` (test: la memoria de siempre).
- **`library/engineering/viga_bastidor.py`** (puro): orientación de la sección por la caja del
  mundo (eje fuerte/débil), envolvente, regla con `calc` + `hipotesis` + `viga` (números).
  **D3**: flecha por TRAMO contra L/240 (vano) y 2·Lv/240 (voladizo); hasta 2× aviso, más error;
  σ = |M|máx/W contra 0.6·fy (AISC ASD 9.ª ed. F1), hasta fy aviso; en madera MOR/4.
- **Pendientes de F1, decididos**: (1) el ángulo L flecta LIBRE por sus ejes principales
  (`secciones.angulo_libre`): I_eq = √2/√(1/Iu² + 1/Iv²) da el MÓDULO del desplazamiento (no
  sólo Iv, que ignora que la carga va a 45° de v) y σ = M/√2·(|n|/Iu + |s|/Iv) en talón y puntas
  (manda la punta interior: W_eq 6.52 cm³ en el L 75×6 contra 8.41 geométrico); la flecha con el
  eje geométrico (arriostrado) va de referencia en la hipótesis. (2) UPN fuera de tabla en su eje
  débil: I y W × 0.85 (borde inferior medido en F1), declarado; con tabla, la tabla.
- `Component.familia` / `params` (loader): el nombre del builder y sus params del YAML, para
  buscar la sección. Metadato: no cambia geometría → sin `GEOM_CACHE_EPOCH`.
- **Piloto real (proyecto 74, revisiones 124 y 125, lectura sola)**: salen los dos largueros y
  los tres travesaños (superior e inferior de alimentación, agrupados por iguales, y el
  portamotor); los 20 tubos de rodillo van a `no_aplica` (sus apoyos son contacto). Largueros:
  vano 200–1905 (1705 mm) + voladizos de 200 y 95 mm; cuelgan 35.2 kg (−Y: 20 ejes) y 40.4 kg
  (+Y: 20 ejes + 3 separadores de guarda); carga útil 100 kg → 50 kg móvil por larguero.

  | rev | larguero | δ vano | L/δ | δ voladizo 95 | \|M\| | σ |
  |---|---|---|---|---|---|---|
  | 124 UPN-100 (I 206 cm⁴) | −Y / +Y | 0.197 / 0.202 mm | L/8650 | 0.03 mm | 0.311 / 0.319 kN·m | 7.5 / 7.7 MPa |
  | 125 L 75×6 libre (I_eq 25.9 cm⁴) | −Y / +Y | 1.50 / 1.54 mm | L/1140 | 0.26 mm | 0.298 / 0.306 kN·m | 45.7 / 46.9 MPa |

  A mano (simplemente apoyada en 1705 mm, sin el alivio de los voladizos, lo colgado como
  uniforme 35.2 kg / 2000 mm + 50 kg al centro): 124 → δ = 0.074 + 0.123 = 0.197 mm, M =
  0.310 kN·m; 125 → δ = 0.509 + 0.979 = 1.49 mm, M = 0.296 kN·m, σ = 45.4 MPa. Coincide (los
  voladizos alivian < 1 %). Arriostrado (eje geométrico, 45.8 cm⁴) el L 75×6 daría ≈ 0.85 mm,
  del orden del 0.82 mm a mano de la bitácora original. Todo verde: manda el voladizo de 95 mm
  (0.26 / 0.79 mm, utilización 0.33; el vano está en 0.21). Travesaños: portamotor (17.8 kg
  del motor y su base) δ 0.015 mm, σ 2.3 MPa. 0.4–1.0 s por revisión.
- Fuera de alcance, declarado: la faja que `detect_conveyor` reconoce POR NOMBRE (sin
  `create_conveyor`) y con requisitos recibe las dos reglas (la vieja «flecha del bastidor» y
  ésta); D4 sólo excluye `create_conveyor`, como dice el plan.
