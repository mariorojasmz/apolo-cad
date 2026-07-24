# Calificación — faja-paqueteria-4m (V7.6 Fase A: GD&T funcional, 2026-07-23)

Primera fase del plan **V7.6 «E2 fino»**: los 7 criterios de E2 estaban en 3.0, así que
esto ya no es cerrar brechas sino **entregar lo que un despacho típico no entrega**.
Paquete regenerado por la API viva (26/26, 278.1 s). Se recalifica SOLO **E2.2**; base =
2026-07-23 (**78.8 % v2 / 78.6 % v1-comp**).

## La prueba que exige el plan

> «Un despacho entrega **X**; nosotros entregamos **X + Y**, y Y se ve en la página N.»

- **X** (lo que hace un despacho de máquina competente, = nuestro 3 de ayer): Ø del
  barreno, posición acotada desde una arista, y a lo sumo una bandera de datum «A».
- **Y** (lo nuevo, verificado por texto de PDF en `planos/juego.pdf`):
  - **marco de control de POSICIÓN** con la tolerancia **derivada del presupuesto de
    ensamble real**, no de una tabla genérica: `Ø0.75 M A` (pág 4, ménsula del motor),
    `Ø1 M A` (pág 5, placa de anclaje), `Ø1.5 M A` (pág 6, ménsula de chumacera),
    `Ø0.75 M A B` (pág 15, larguero), `Ø0.75` + `Ø0.5 M A` (pág 17). **6 marcos en 5
    láminas.**
  - **sistema de referencia trazado a las uniones REALES** — el larguero llega a **A-B**
    (dos soldaduras ortogonales), y cada letra se justifica en la leyenda: «Datum A: cara
    −Y — soldadura a «Repisa apoyo mesa (+Y)»» · «Datum B: cara −Z — soldadura a
    «Ménsulas de chumacera»». Sin esa leyenda el marco sería decorativo.

**Spot-checks (los 4 valores distintos, recalculados a mano)**:
| Lámina | Ø barreno | Perno | Condición | t esperado | PDF |
|---|---:|---|---|---:|---|
| pág 17 (brida motor) | 9.0 | M8 (ISO 273) | fijo | (9−8)/2 = **0.5** | Ø0.5 ✓ |
| págs 4/15/17 | 13.5 | M12 (ISO 273) | fijo | (13.5−12)/2 = **0.75** | Ø0.75 ✓ |
| pág 5 (anclaje) | 14.0 | M12 (del sólido) | fijo | (14−12)/2 = **1.0** | Ø1 ✓ |
| pág 6 (chumacera) | 15.5 | M14 (ISO 273) | **flotante** (tuerca M14 en el eje) | 15.5−14 = **1.5** | Ø1.5 ✓ |

La última fila es la que demuestra que el número NO es cosmético: es la única unión del
38 con tuerca modelada, y por eso —y solo por eso— recibe la holgura completa en vez de
la mitad. Eso cierra además el residual declarado de V7.3 («`bolt_pattern_budget` usa la
fórmula de fijador FIJO, hasta 2× conservadora para pernos flotantes»).

**Sin regresión en E2.6**: el detector de solapes da **4 en 22 páginas CON y SIN** GD&T
(idénticos) — los 3 conocidos del GA (declarados desde V7.2) y 1 de callouts del larguero
(desde la brecha 1). Ningún solape nuevo. Lints `[]`, 73 reglas sin avisos.

## E2.2 → **3.75** (no 4) — residuales que lo impiden, declarados

El criterio supera con claridad al despacho típico, pero NO es un GD&T completo:
1. **«M» tipográfico** en el marco, no el símbolo Ⓜ circulado (la condición de máximo
   material se explica en la nota, pero el glifo normativo no está).
2. **Solo control de POSICIÓN**: no hay perpendicularidad, planitud ni coaxialidad —
   controles que una pieza mecanizada de precisión sí llevaría.
3. **Los datums llegan a A-B**: ninguna pieza del 38 tiene tres contactos ortogonales
   declarados, así que el testigo no exhibe un marco A-B-C completo (es una propiedad del
   modelo, no del código — el código lo emitiría).
4. La tolerancia se asigna **por Ø de la pieza**, no por patrón: dos patrones distintos
   del mismo Ø compartirían valor (no ocurre en el 38, pero es una limitación real).

Con la regla del plan («si no se sostiene, se declara 3 y se dice por qué»), lo honesto es
**3.75**: más que el 3 de ayer, menos que un 4 redondo.

## Puntaje

| Entregable | Peso | 2026-07-23 | **2026-07-23b** | Qué movió |
|---|---:|:---:|:---:|---|
| E1 · 3D validado | 15 | 3.50 | 3.50 | — |
| E2 · Juego de planos | 30 | 3.00 (75.0 %) | **3.107 (77.7 %)** | E2.2 3 → 3.75 (GD&T funcional) |
| E3 · Memoria | 20 | 3.393 (84.8 %) | 3.393 | — (el fix de fijador flotante no se ve en el testigo: no hay cadena de patrón declarada) |
| E4 · BOM + cotización | 15 | 3.00 | 3.00 | — |
| E5 · Manual | 10 | 3.00 | 3.00 | — |
| E6 · Paquete e interop | 10 | 3.00 | 3.00 | — |
| **GLOBAL v2** | 100 | **78.8 %** | **≈ 79.6 %** | |

v2 = 0.15·87.5 + 0.30·77.68 + 0.20·84.82 + 0.15·75 + 0.10·75 + 0.10·75 = **79.64 %**.
(v1-comparable ≈ 79.5 %: E3.6/E3.7 son criterios v2.)

## Cambios al proyecto 38

**Ninguno.** Esta fase es 100 % de CÓDIGO: los marcos y datums se derivan de fasteners y
barrenos que ya existían. El paquete cambia porque el generador es mejor, no porque el
modelo lo sea — es la clase de mejora que escala a todos los proyectos, no solo al testigo.

## Siguiente (plan V7.6)

Fase B (**E2.3 → 4**: tolerancia trazada a la cadena de cotas + ISO 13920 en el conjunto
soldado) y Fase C (**E2.1 → 4**: lámina de instalación). Cada una vale ~+1.1 pts si
alcanza el 4 redondo; con la vara de honestidad aplicada aquí, esperar ~+0.8.
