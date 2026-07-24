# Calificación — faja-paqueteria-4m (V7.6 Fase B: tolerancia justificada, 2026-07-23)

Segunda fase del plan **V7.6 «E2 fino»**. Paquete regenerado por la API viva (26/26,
115.2 s). Se recalifica SOLO **E2.3**; base = `2026-07-23b` (**79.6 % v2**).

## La prueba que exige el plan

> «Un despacho entrega **X**; nosotros entregamos **X + Y**, y Y se ve en la página N.»

- **X** (nuestro 3 desde V7.2, y lo que hace un despacho competente): «ISO 2768-mK» en el
  cajetín, ajustes ISO 286 en los asientos (`Ø35 h7 (0/−0.025)`), roscas ISO 6410.
- **Y** (lo nuevo, verificado por texto de PDF en `planos/juego.pdf`):
  1. **La cota crítica lleva la tolerancia que el ANÁLISIS exige, no la genérica**:
     pág 16 `674.4 ±0.8` (pata) y pág 15 `101.6 ±0.3` (canto del larguero) — las dos cotas
     que suman la altura del bastidor. Cada una remite a su origen: *«Cota crítica: cadena
     «altura bastidor soldado» (ver memoria)»*, y la memoria trae esa cadena completa
     (peor caso [774.9, 777.1] ⊆ requisito). Cota → cadena → veredicto: **trazable de
     punta a punta**, que es lo que la rúbrica pide por «trazable».
  2. **ISO 13920-BF en el conjunto soldado** (pág 1): la norma de tolerancias de
     construcción SOLDADA. Las ISO 2768 son de mecanizado y no cubren el soldeo; casi
     ningún despacho de máquina la rotula, y su ausencia deja al taller sin criterio para
     escuadrado y rectitud del bastidor.

**Spot-check contra ISO 2768-1 clase m** (recalculado a mano): 674.4 mm cae en el tramo
400–1000 → **±0.8** ✓; 101.6 mm cae en 30–120 → **±0.3** ✓. Los dos valores del PDF
coinciden con la tabla, y son los mismos que la memoria usa para cerrar la cadena.

**Sin regresión**: detector de solapes **4 en 22 páginas** — idéntico a antes de las
Fases A y B (los 3 conocidos del GA + 1 de callouts del larguero). Lints `[]`.
Cobertura conservada: 5 láminas con marco GD&T (Fase A) + 2 con tolerancia de cadena.

## E2.3 → **3.75** (no 4) — residuales declarados

1. **Solo 2 láminas la ejercen**, porque el 38 tiene 2 cadenas declaradas y una es de
   asiento (bandas asimétricas, que viajan en su callout de Ø, no en la cota general).
   La cobertura la limita el MODELO, no el código — pero la rúbrica juzga el artefacto.
2. **Bandas asimétricas fuera de la cota general**: un fit ISO 286 en una cota lineal se
   omite (el formato `±t` no lo admite); es honesto, pero un GD&T completo lo rotularía
   como `+0.021/0`.
3. **ISO 13920 con clase fija BF**, no derivada del tamaño ni del proceso declarado.
4. La tolerancia se aplica a la **cota general de la vista**, no a cotas parciales entre
   features (la cadena puede referirse a un tramo, no al bbox completo).

Con la vara del plan, **3.75**: claramente más que el 3 (tolerancia justificada y trazada
a un análisis + norma de weldments), pero no el 4 redondo.

## Puntaje

| Entregable | Peso | 2026-07-23b | **2026-07-23c** | Qué movió |
|---|---:|:---:|:---:|---|
| E1 · 3D validado | 15 | 3.50 | 3.50 | — |
| E2 · Juego de planos | 30 | 3.107 (77.7 %) | **3.214 (80.4 %)** | E2.3 3 → 3.75 |
| E3 · Memoria | 20 | 3.393 (84.8 %) | 3.393 | — |
| E4 · BOM + cotización | 15 | 3.00 | 3.00 | — |
| E5 · Manual | 10 | 3.00 | 3.00 | — |
| E6 · Paquete e interop | 10 | 3.00 | 3.00 | — |
| **GLOBAL v2** | 100 | **79.6 %** | **≈ 80.4 %** | |

v2 = 0.15·87.5 + 0.30·80.36 + 0.20·84.82 + 0.15·75 + 0.10·75 + 0.10·75 = **80.43 %**.

> **La meta 78-80 % queda SUPERADA** — por primera vez en la serie (74 → 77 → 77.6 →
> 78.4 → 78.6 → 78.8 → 79.6 → **80.4**), y con la vara v2, que es más exigente que
> aquella con la que se fijó la meta. Ambas fases de V7.6 se autocalificaron 3.75 y no 4
> aplicando la advertencia del propio plan: el 80 % se cruza con dos criterios que aún
> declaran cuatro residuales cada uno.

## Cambios al proyecto 38

**Ninguno** (como la Fase A). Ambas fases son 100 % de CÓDIGO: el generador aprovecha
cadenas y uniones que ya estaban declaradas. La mejora escala a cualquier proyecto que
declare sus cadenas.

## Siguiente

Fase C (**E2.1 → 4**: lámina de instalación con huella de anclaje y carga por apoyo) —
la única de las tres que necesita una lámina nueva. Con la vara aplicada aquí, esperar
~+0.8 pts.
