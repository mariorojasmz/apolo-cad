# Calificación — faja-paqueteria-4m (E5: manual con par calculado, 2026-07-24)

Tras cerrar V7.6, el tablero cambió: E2 dejó de ser la brecha y los criterios en 3.00
pasaron a ser **E4, E5 y E6**. Se ataca **E5 · Manual** por ser el de mejor ratio (solo 2
criterios, peso 10). Paquete regenerado por la API viva (26/26, 125.1 s). Base =
`2026-07-23d` (**81.2 % v2**).

## La prueba

> «Un despacho entrega **X**; nosotros entregamos **X + Y**, y Y se ve en la página N.»

- **X**: un manual con pasos, render por paso, y la lista de piezas/herraje de cada uno
  (nuestro 3.0 desde V7.2c) — que ya es más de lo que muchos despachos entregan.
- **Y**, verificado por texto de PDF en `manual.pdf`:
  1. **Par de apriete CALCULADO y llave por paso** — pág 3: «M12 → 91 N·m (llave 18 mm)»,
     pág 4: «M16 → 225 N·m (llave 24 mm)», pág 5: «M14 → 144 N·m (llave 21 mm)». No es una
     tabla copiada: sale de `T = K·d·(0.7·A_s·R_y)` con la condición de rosca DECLARADA
     («8.8, rosca seca»), del mismo módulo que dimensiona las uniones en la memoria.
  2. **Orden intra-paso de abajo hacia arriba** — cierra el residual «orden fino
     intra-grupo» que el manual arrastraba declarado desde V7.2b. Paso 1, antes vs ahora:

     | | Orden de montaje del paso 1 |
     |---|---|
     | antes | Placa (z 0) → **Disco anti-giro (z 692)** → **Ménsula motor (z 652)** → Pata (z 70) → Travesaño inf. (z 100) |
     | ahora | Placa (z 0) → Pies niveladores (z 10) → Pata (z 70) → Travesaño inf. (z 100) → Ménsula motor (z 652) → Disco (z 692) |

     El montador ya no ve «coloque el disco anti-giro» antes que las patas que lo sostienen.

**Spot-check del par (recalculado a mano contra tablas comerciales 8.8 en seco)**:

| Métrica | A_s (mm²) | F_pre = 0.7·A_s·640 | T = 0.2·d·F_pre | PDF | Tabla comercial |
|---|---:|---:|---:|---:|---:|
| M8 | 36.6 | 16 397 N | 26.2 N·m | 26 | ~25 |
| M12 | 84.3 | 37 766 N | 90.6 N·m | 91 | ~87 |
| M14 | 115 | 51 520 N | 144.3 N·m | 144 | ~137 |
| M16 | 157 | 70 336 N | 225.1 N·m | 225 | ~214 |

Todos dentro del ~5 % de las tablas de taller — la fórmula y sus constantes son correctas.

## E5.1 → **3.5** · E5.2 → **3.75** (E5 = 3.625, 90.6 %)

- **E5.1 Secuencia (3 → 3.5)**: la secuencia entre pasos ya era correcta; ahora el orden
  DENTRO del paso también respeta la física del montaje. *Residuales*: el criterio
  intra-paso es la z de la base (heurística correcta pero más simple que un grafo de
  soporte intra-paso), y el manual sigue sin **criterio de verificación por paso**
  («comprobar escuadría», «debe girar a mano») ni tiempos estimados.
- **E5.2 Herraje por paso (3 → 3.75)**: el paso ya no dice «apretar los pernos» sino con
  qué llave y a qué par, trazado al mismo motor que dimensiona la unión.
  *Residuales*: sin vista explosionada por paso, el grado se asume 8.8 (no se lee de la
  ficha), la condición de rosca es fija «seco» (conservadora: lubricada necesitaría 30 %
  menos par) y no hay secuencia de apriete gráfica para patrones grandes.

## Puntaje

| Entregable | Peso | 2026-07-23d | **2026-07-24** | Qué movió |
|---|---:|:---:|:---:|---|
| E1 · 3D validado | 15 | 3.50 | 3.50 | — |
| E2 · Juego de planos | 30 | 3.321 (83.0 %) | 3.321 | — |
| E3 · Memoria | 20 | 3.393 (84.8 %) | 3.393 | — |
| E4 · BOM + cotización | 15 | 3.00 | 3.00 | — |
| **E5 · Manual** | 10 | 3.00 (75 %) | **3.625 (90.6 %)** | par + llave calculados · orden intra-paso |
| E6 · Paquete e interop | 10 | 3.00 | 3.00 | — |
| **GLOBAL v2** | 100 | **81.2 %** | **≈ 82.8 %** | |

v2 = 0.15·87.5 + 0.30·83.04 + 0.20·84.82 + 0.15·75 + 0.10·90.63 + 0.10·75 = **82.81 %**.

Serie medida: 74 → 77 → 77.6 → 78.4 → 78.6 → 78.8 → 79.6 → 80.4 → 81.2 → **82.8**.

## Cambios al proyecto 38

**Ninguno** — como las tres fases de V7.6, es 100 % de código.

## Brechas vivas

Los dos criterios que quedan en 3.00 son ahora **E4 · BOM + cotización** (peso 15, el eje
que menos trabajo ha recibido en todo el proyecto: cotización con margen/impuesto planos,
sin alternativas de proveedor ni plazos) y **E6 · Paquete e interop** (peso 10). Más los
residuales de E5 (verificación por paso, explosionada) y los 3.75 → 4 de V7.6.

**Reserva metodológica**: son diez iteraciones sobre el MISMO testigo. Todas las mejoras
recientes son de código y se presume que generalizan, pero **eso no está verificado** —
el siguiente paso acordado es correr el paquete completo sobre un proyecto distinto.
