# Calificación — faja-paqueteria-4m (V7.6 Fase C: lámina de instalación, 2026-07-23)

Tercera y última fase del plan **V7.6 «E2 fino»**. Paquete regenerado por la API viva
(26/26, 113.0 s; el juego pasa de 22 a **23 páginas**). Se recalifica SOLO **E2.1**;
base = `2026-07-23c` (**80.4 % v2**).

## La prueba que exige el plan

> «Un despacho entrega **X**; nosotros entregamos **X + Y**, y Y se ve en la página N.»

- **X** (nuestro 3, y lo que entrega un despacho competente): GA + una lámina por pieza
  fabricada + cédula de herraje + lista de corte.
- **Y** (pág 21, **PLANTA DE INSTALACIÓN Y ANCLAJE**): la hoja que el cliente separa y
  lleva a la obra civil ANTES de que llegue la máquina —
  - **huella de anclaje** dibujada en planta y acotada entre ejes extremos
    (3206 × 830.8 mm), con una marca de centro por apoyo;
  - **carga por apoyo calculada con el COG real** (reparto elástico de grupo, no división
    a partes iguales): **39.6 · 51.6 · 63.6 · 72.3 · 84.3 · 96.3 kg**, rotuladas sobre su
    apoyo en la planta;
  - alturas de interfaz (transporte 848 mm, total 889 mm), **holguras de servicio**
    (660 mm para extraer tambor motriz y tensor de cola) y **suministro eléctrico**
    (2.2 kW, del catálogo del NMRV-090);
  - notas de obra con la **hipótesis del reparto declarada** («reparto elástico de grupo
    con el peso en el COG…; apoyos de igual rigidez sobre piso rígido»).

**Spot-check (equilibrio y criterio), recalculado a mano**: Σ cargas = 407.7 kg vs
masa + carga = 332.5 + 75 = **407.5 kg** ✓ (equilibrio, diferencia = redondeo). Uniforme =
67.9 kg/apoyo; **máximo 96.3 kg = 1.42× el uniforme** — exactamente el dato que un reparto
a partes iguales habría ocultado y con el que la obra dimensionaría de menos.

**Defecto de criterio cazado y corregido en esta fase** (el más valioso del día): la
primera corrida daba **30 «apoyos»** porque el 38 declara `ground` también sobre los 24
pernos de anclaje → la carga por punto salía diluida 5× (19.6 kg en vez de 96.3). Un
plano de instalación con ese número lleva a un anclaje subdimensionado. La tornillería
queda ahora excluida de los apoyos, con test de regresión.

## E2.1 → **3.75** (no 4) — residuales declarados

1. **No hay vista de ALZADO de instalación**: las alturas van en tabla, no acotadas sobre
   un dibujo (un plano de obra completo las cota).
2. **Las cotas son de la huella global** (entre ejes extremos), no la posición individual
   de cada apoyo desde un origen de máquina declarado — suficiente para replantear un
   patrón regular, escaso si la huella fuera irregular.
3. **Sin recomendación de fundación**: ni tipo de anclaje (expansión/químico), ni espesor
   mínimo de losa, ni par de apriete — el «qué» está, el «con qué» no.
4. La holgura de servicio se deriva del **ancho de la pieza** (extracción lateral), no de
   una trayectoria de desmontaje real.

Con la vara del plan, **3.75**: muy por encima del 3 (ninguna de estas hojas existía), sin
llegar al plano de instalación completo de un proyecto de planta.

## Puntaje

| Entregable | Peso | 2026-07-23c | **2026-07-23d** | Qué movió |
|---|---:|:---:|:---:|---|
| E1 · 3D validado | 15 | 3.50 | 3.50 | — |
| E2 · Juego de planos | 30 | 3.214 (80.4 %) | **3.321 (83.0 %)** | E2.1 3 → 3.75 |
| E3 · Memoria | 20 | 3.393 (84.8 %) | 3.393 | — |
| E4 · BOM + cotización | 15 | 3.00 | 3.00 | — |
| E5 · Manual | 10 | 3.00 | 3.00 | — |
| E6 · Paquete e interop | 10 | 3.00 | 3.00 | — |
| **GLOBAL v2** | 100 | **80.4 %** | **≈ 81.2 %** | |

v2 = 0.15·87.5 + 0.30·83.04 + 0.20·84.82 + 0.15·75 + 0.10·75 + 0.10·75 = **81.24 %**.

## Cierre de V7.6 (las tres fases)

| Fase | Criterio | Antes | Después | Global v2 |
|---|---|:---:|:---:|:---:|
| A · GD&T funcional | E2.2 | 3 | 3.75 | 78.8 → 79.6 % |
| B · Tolerancia justificada + ISO 13920 | E2.3 | 3 | 3.75 | 79.6 → 80.4 % |
| C · Lámina de instalación | E2.1 | 3 | 3.75 | 80.4 → **81.2 %** |

**E2 pasa de 75.0 % a 83.0 %** — el entregable más pesado (30) y el que llevaba tres
benchmarks siendo la brecha. Las tres fases se autocalificaron **3.75 y no 4**, cada una
declarando cuatro residuales: el 81.2 % es deliberadamente conservador. Serie completa
medida: 74 → 77 → 77.6 → 78.4 → 78.6 → 78.8 → 79.6 → 80.4 → **81.2**.

**Ninguna de las tres tocó el modelo 38**: son 100 % de código, así que el salto se
aplica a cualquier proyecto — no es un testigo afinado a mano.

## Brechas vivas (backlog)

1. **E2.4 soldadura → 4** (símbolos por lámina de miembro, lado flecha/otro lado) y
   **E2.5/E2.6/E2.7** (acabado por superficie, vistas auxiliares, PDF/A) — fuera del
   alcance declarado de V7.6.
2. Los cuatro residuales de cada fase A/B/C (ver arriba): el camino de 3.75 → 4.
3. **E5 orden intra-grupo** y **E3.6 → 4** (más cadenas declaradas).
