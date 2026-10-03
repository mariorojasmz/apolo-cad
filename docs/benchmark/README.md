# Benchmark de entregables — cómo madura Apolo

Apolo no persigue paridad de herramientas con SolidWorks/Inventor: la vara es el **entregable
terminado** (3D validado + juego de planos de taller + memoria de cálculo + BOM/cotización +
manual), en calidad y en tiempo, contra lo que un despacho competente termina a mano en
SW/Inventor sobre la misma máquina (doctrina de RESULTADOS, usuario 2026-07-10; ver el
[CLAUDE.md raíz](../../CLAUDE.md)). Este benchmark es el test de regresión de CALIDAD del producto.

Cuando el usuario pregunte cómo madura Apolo, se compara contra las dos tablas de abajo —la de
features y la serie medida— y contra esa doctrina. Las hojas de ruta que movieron cada número
están en [`docs/roadmap.md`](../roadmap.md).

## Cómo se corre

- `scripts/benchmark_package.py` es un **cliente HTTP puro**: no importa `apolo.*` a propósito
  (un script que importa el paquete recompila `.pyc` y, con `--reload`, recarga el worker y
  blanquea el DOC en memoria). Requiere la API arriba. Regenera el paquete completo de un proyecto
  en `docs/benchmark/<proy>/<fecha>/` cronometrando cada artefacto y escribe `paquete.md`.

  ```powershell
  .\.venv\Scripts\python.exe scripts\benchmark_package.py --project 38 --out docs\benchmark\faja-paqueteria-4m\AAAA-MM-DD --expect largo_total=4000
  ```

  Usa una carpeta **fechada nueva**: el paquete testigo commiteado no se pisa. Las aserciones
  `verify` están calibradas al 38; para otro proyecto pasa `--checks ruta.json` (sin él, la fase
  `verify` se omite, no se inventa). Sale con código ≠ 0 si algún artefacto falla.
- La **rúbrica versionada** lo califica. Vigente: [`rubrica-v2.md`](rubrica-v2.md) desde
  2026-07-22 = [v1](rubrica-v1.md) + E3.6 stack-up + E3.7 FEA, sin relajar ninguna ancla. Al
  calificar bajo v2 se reporta también el global **v1-comparable**, para no romper la serie.
- Se corre y se re-califica **tras cada V7.x**. Pesos por eje: E1 3D 15 · E2 planos 30 ·
  E3 memoria 20 · E4 BOM/cotización 15 · E5 manual 10 · E6 paquete/interop 10. Puntaje 0–4 por
  criterio con anclas duras (3 = nivel despacho, 4 = supera al despacho típico).
- Se verifica por el **TEXTO de los PDFs** (pypdf) y con spot-checks a mano, no por la ruta de
  código. La autocalificación siempre pasa por una **re-auditoría**, que en la serie corrigió
  a la baja varias autocalificaciones (67 → 62, 77 → 74, 78 → 77). La base de partida de cada
  corrida es el último global **re-auditado**, nunca el autocalificado.

## Madurez por features

Escala: incumbente maduro = 10. Veredicto: como CAD GENERAL, Apolo es ~10-15 % de SW/Inventor
(kernel nivel FreeCAD — una CUÑA, no un reemplazo); como herramienta del VERTICAL cubre ~80 % del
flujo autónomo, una categoría que los grandes no ocupan. Valores vigentes al 2026-07-24:

| eje | nota | qué la movió |
|---|---:|---|
| IA-nativa / API-first | 9.5 | el moat |
| kernel OCCT | 6.5 | |
| paramétrico | 6.5 | V6.4: condicionales + faja 38 100 % paramétrica + tablas de diseño |
| croquis | 6.5 | V6.6: PlaneGCS + spline/elipse + arrastre en vivo |
| ensamblaje | 6 | V6.3: multi-mate + conectores por ancla/arista + reporte de DOF; soundness/gravedad sigue siendo único |
| planos | 7.5 | V7.2: soldadura ISO 2553 + ISO 2768 + acabados ISO 1302 + datums · V7.2c: fit por lámina, revolución ≠ sierra, sin retoque humano |
| simulación | 5 | analítico + MuJoCo + FEA lineal de pieza y de ensamblaje bonded multi-material (V7.4); falta contacto/no-lineal |
| negocio | 6.5 | |
| interop | 6 | |
| rendimiento | 6 | V6.2 |
| robustez | 6 | V6.1 |
| CAM | 0 | deliberado |
| colaboración / ecosistema | 1 | |

## Serie medida (testigo: faja 38)

Global del paquete de `faja-paqueteria-4m` (proyecto 38). Hasta el 2026-07-20 con rúbrica-v1;
desde el 2026-07-22 con rúbrica-v2 (más exigente), con el v1-comparable al lado.

| fecha | corrida | qué movió | global | calificación |
|---|---|---|---|---|
| 2026-07-10 | V7.1 | primer paquete por API (411.9 s, 24/24 artefactos) | **62 %** re-auditado (autocalificación 67 %) | [faja38/2026-07-10](faja38/2026-07-10/calificacion.md) |
| 2026-07-11 | V7.1c | memoria lee del modelo, compras fuera de la lista de corte | **68 %** | [2026-07-11](faja-paqueteria-4m/2026-07-11/calificacion.md) |
| 2026-07-11 | V7.2 | E2 53.6 → 71.4 % (soldadura, ISO 2768, acabados, datums) | **≈73 %** re-auditado | [2026-07-11-v72](faja-paqueteria-4m/2026-07-11-v72/calificacion.md) |
| 2026-07-14 | V7.2b | manual por soporte, normas, lints, proceso, eje g6 | **74 %** re-auditado (autocalificación 77 %) | [2026-07-14](faja-paqueteria-4m/2026-07-14/calificacion.md) |
| 2026-07-18 | V7.2c | fit por pieza, revolución ≠ sierra, cola del manual | **≈77 %** re-auditado (autocalificación 78 %) | [2026-07-18](faja-paqueteria-4m/2026-07-18/calificacion.md) |
| 2026-07-20 | cierre V7.2c + V7.3 | E5 recalificado; stack-up anotado como capacidad nueva | **77.6 % ≈ 78 %** | [2026-07-20](faja-paqueteria-4m/2026-07-20/calificacion.md) |
| 2026-07-22 | V7.4 + V7.4b + V7.5 (primera bajo v2) | E1.1 3 → 3.5, E2.2 2.5 → 2.75 | **78.4 % v1 / 78.2 % v2** | [2026-07-22](faja-paqueteria-4m/2026-07-22/calificacion.md) |
| 2026-07-22 | brecha 1 (corrida `2026-07-22b/`) | E2.2 2.75 → 3.0 | **≈78.6 % v1 / ≈78.5 % v2** | addendum en [2026-07-22](faja-paqueteria-4m/2026-07-22/calificacion.md) · [paquete](faja-paqueteria-4m/2026-07-22b/paquete.md) |
| 2026-07-23 | brechas 2+3 | manual de 8 → 6 pasos; E3.7 = 4 | **v2 ≈78.8 %** (v1 78.6) | [2026-07-23](faja-paqueteria-4m/2026-07-23/calificacion.md) |
| 2026-07-23 | V7.6 fase A | GD&T funcional: E2.2 = 3.75 | **v2 ≈79.6 %** | [2026-07-23b](faja-paqueteria-4m/2026-07-23b/calificacion.md) |
| 2026-07-23 | V7.6 fase B | tolerancia justificada + ISO 13920: E2.3 = 3.75 | **v2 ≈80.4 %** — la meta 78-80 % queda superada | [2026-07-23c](faja-paqueteria-4m/2026-07-23c/calificacion.md) |
| 2026-07-23 | V7.6 fase C | lámina de instalación: E2.1 = 3.75; E2 75.0 → 83.0 % | **v2 ≈81.2 %** | [2026-07-23d](faja-paqueteria-4m/2026-07-23d/calificacion.md) |
| 2026-07-24 | E5 | par de apriete calculado + orden intra-paso: E5 3.00 → 3.625 (90.6 %) | **v2 ≈82.8 %** | [2026-07-24](faja-paqueteria-4m/2026-07-24/calificacion.md) |

Lo que dice la serie:

- **Primera corrida bajo v2 (2026-07-22)**: producida por API en 128.7 s autónoma; la métrica de
  TIEMPO es ~10³× a favor (estimado). Por eje: 3D 87.5 % · planos 74.1 % (era LA brecha, peso
  30) · memoria 83.8 % v1 / 83.0 % v2 (E3.6 stack-up = 3; E3.7 FEA = 3.5, contraste FEA 64.61 vs
  analítica 62 en el larguero, 4 %) · BOM/cotización 75 % · manual 75 % · paquete 75 % · FEA
  firmable ~70 % · render ~50 %.
- **V7.6 (fases A, B y C)**: las tres quedaron en 3.75 y ninguna en 4, con 4 residuales
  declarados cada una (nota deliberadamente conservadora). Las tres son 100 % de CÓDIGO: el
  modelo no cambió, el generador mejoró — escala a todos los proyectos, no es un testigo afinado
  a mano.
- **D.1 retirado** (2026-07-23, decisión razonada): pasar los patrones paramétricos de anclas a
  24 inserts literales DIN 933 sería una regresión de parametricidad por cosmética de BOM (la
  cédula ya los lista como COMPRA, y un ancla real no es DIN 933). Si el negocio lo pide: familia
  «anclajes» + patrón de componentes.
- **Ejes que siguen en 3.00 tras E5**: **E4 (BOM/cotización, peso 15 — el menos trabajado del
  proyecto)** y **E6 (paquete/interop)**. Otras brechas vivas: E2 fino (acabados/tolerancias;
  backlog en la `nota:` de [V7.6](../plans/V7.6-e2-fino.md)) y E3.6 → 4 (más cadenas declaradas;
  `nota:` de [V7.3](../plans/V7.3-stackup-cadenas-cotas.md)). El residual «orden intra-grupo del
  manual» lo cerró E5 (orden intra-paso por z de la base).

La narrativa de cada corrida (evidencia, spot-checks, bugs cazados) está en el
[devlog](../devlog.md), de § «Re-benchmark con rúbrica-v2» a § «SEGUNDO TESTIGO», y en cada
`calificacion.md`.

## Reserva declarada y segundo testigo

**Reserva**: la serie son diez iteraciones sobre el MISMO testigo. Que las mejoras de código
generalicen no estaba verificado, así que se corrió el paquete sobre un segundo proyecto.

**Segundo testigo (2026-07-24)**: [informe de generalización](puerta-plegable-bifold/2026-07-24/informe-generalizacion.md)
sobre el proyecto más LEJANO (puerta plegable de carpintería, id 28): 25/26 artefactos en 63 s.
Cuatro hallazgos:

1. El script de benchmark **crasheaba** con cualquier proyecto ≠ 38 (UnicodeEncodeError en
   cp1252): la herramienta de medición impedía medir.
2. La memoria estaba **presa del vertical** (400 sin `carga_kg`/`largo_paquete`: ningún proyecto
   que no fuera faja tenía memoria). Ahora emite lo UNIVERSAL y declara lo omitido.
3. «APROBADO CON AVISOS» con 0 OK aprobaba el vacío. Ahora el veredicto es **NO CONCLUYENTE**.
4. **Estructural**: el 82.8 % es del sistema **sobre un modelo bien declarado**. Sin fasteners,
   cadenas ni grounds declarados, el GD&T, la tolerancia justificada, la lámina de instalación y
   el par de apriete no se activan — correctamente: cada regla de honestidad funciona.

Los hallazgos 1-3 se arreglaron con tests, con cero regresión en el 38 (23 páginas · 89 OK ·
APROBADO). La reserva sigue en pie para el hallazgo 4: la nota mide el sistema con un modelo
bien declarado, no cualquier modelo.
