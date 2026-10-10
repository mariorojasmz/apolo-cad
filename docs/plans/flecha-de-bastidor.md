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
