# SEGUNDO TESTIGO — informe de generalización (2026-07-24)

**Pregunta que responde este ejercicio**: el **82.8 %** medido el 2026-07-24, ¿es una
propiedad del SISTEMA o del TESTIGO? Tras diez iteraciones sobre el mismo proyecto (la
faja 38) la afirmación «las mejoras son 100 % de código, así que escalan» estaba
**presumida, no verificada**.

**Testigo elegido**: `puerta-plegable-bifold` (id 28) — deliberadamente el proyecto más
LEJANO del 38: carpintería, madera, 86 sólidos, sin soldadura, sin anclaje a piso, sin
requisitos de transportador, herraje de bisagras/correderas en vez de tornillería
métrica. Si algo no generaliza, aparece aquí.

**Este documento NO es una calificación comparable**: la rúbrica está calibrada a máquina
(E3 exige verificaciones de banda/tambor, E2.4 soldadura). Lo que se mide es
**generalización**: qué se rompe, qué se degrada en silencio y qué se comporta bien.

---

## Hallazgos

### 1 · El script de benchmark CRASHEABA con cualquier proyecto ≠ 38 — ARREGLADO
`UnicodeEncodeError` al imprimir «≠» en la consola cp1252 de Windows, en la línea del
aviso «proyecto ≠ 38 y sin --checks» — que **solo se ejecuta fuera del 38**. Diez
benchmarks no lo tocaron. Consecuencia: era imposible medir otro proyecto, o sea que la
propia herramienta de medición impedía la verificación que hoy hacemos.
*Fix*: `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` — un glifo raro
degrada, jamás aborta el paquete.

### 2 · La memoria de cálculo estaba PRESA del vertical transportadores — ARREGLADO
`GET /api/calc-report.pdf` devolvía **400** si faltaban `carga_kg` / `largo_paquete_mm`,
requisitos que **solo tienen sentido en un transportador**. Cualquier proyecto de
carpintería, estructura o layout se quedaba sin memoria de cálculo — el entregable de
peso 20 — aunque el sistema SÍ tenía verificaciones aplicables (estructura, uniones,
vuelco, FEA, cadenas de cotas), todas universales y ya calculadas por `/api/checks`.
*Fix*: sin esos requisitos se omiten las reglas de conveyor y la memoria se emite con lo
universal, **declarando en el propio documento lo que no se verificó** («alcance de la
memoria»). Verificado: el 28 pasó de 400 a una memoria de 2 páginas; el 38 conserva sus
23 páginas / 89 OK / APROBADO, sin el aviso (tiene sus requisitos).

### 3 · «APROBADO CON AVISOS» con CERO verificaciones OK — ARREGLADO
La primera memoria del 28 salió **«VEREDICTO: APROBADO CON AVISOS» con 0 OK · 2 avisos**.
Aprobar un documento que no verificó nada es aprobar el vacío: el falso positivo exacto
que la doctrina del proyecto prohíbe, y aplicaba también al 38 en cualquier caso límite.
*Fix*: `_verdict` exige al menos un `ok` para hablar de aprobación; sin ninguno el
veredicto es **NO CONCLUYENTE**. El 28 ahora lo rotula; el 38 sigue APROBADO.

### 4 · El 82.8 % depende de la CALIDAD DE DECLARACIÓN del modelo — ESTRUCTURAL
En el 28 no se activaron: marcos GD&T (0), datums (0), tolerancias de cadena (0), lámina
de instalación (no), ISO 13920 (no), par de apriete (0). **Ninguna de esas ausencias es
un bug** — al contrario, es cada regla de honestidad funcionando:

| Feature | Por qué no aparece | ¿Correcto? |
|---|---|---|
| GD&T (marco + datums) | el 28 no declara fasteners (los lints avisan: 24 piezas sin unión) → sin cara funcional ni perno en el eje | ✅ «sin señal, sin marco» |
| Tolerancia de cadena | no hay cadenas declaradas | ✅ |
| ISO 13920 | no hay cordones: es madera | ✅ el gate por soldadura funciona |
| Lámina de instalación | no hay grounds: una puerta no se ancla al piso | ✅ «sin apoyos no hay plano de obra» |
| Par de apriete | el herraje de carpintería no lleva métrica M | ✅ no se inventa |

**Conclusión honesta**: el 82.8 % **no es una nota del sistema solo — es del sistema
SOBRE un modelo bien declarado**. Los entregables de alta nota (GD&T, tolerancia
justificada, instalación, memoria completa) se alimentan de uniones, cadenas, grounds y
requisitos DECLARADOS. El 38 los tiene tras diez iteraciones de trabajo; el 28 no. En un
proyecto sin declarar, el mismo código produce un paquete honesto pero mucho más pobre.

---

## Qué SÍ generalizó sin tocar nada

25/26 artefactos en **63.4 s** sobre un vertical distinto: juego de planos (14 págs con
ISO 2768 y despiece), GA, lista de corte, nesting, BOM por grupo, costeo, cotización,
manual de 14 páginas, STEP, 3 renders y validación completa. El motor de planos, BOM,
manual e interop es **genuinamente genérico**. Los lints hicieron su trabajo: detectaron
las 24 piezas sin unión declarada del 28 — el dato que explica todo el hallazgo 4.

## Implicación de producto (la lección que vale más que la nota)

El valor del paquete es proporcional a **cuánto declara el modelo**, y hoy el sistema
premia la declaración en silencio: quien no declara uniones simplemente obtiene menos, sin
saber por qué. Los lints ya avisan de piezas sin unión; el siguiente paso natural sería un
**«informe de completitud de declaración»** al generar el paquete: «este proyecto no
declara cadenas de cotas → sin tolerancias justificadas; no declara grounds → sin lámina
de instalación». Convertiría una degradación silenciosa en una guía accionable.

## Estado

Cuatro hallazgos: **tres arreglados con tests de regresión** (1, 2 y 3) y uno estructural
documentado (4). Cero regresión en el 38 (23 págs · 89 OK · APROBADO). El paquete del
segundo testigo queda versionado en esta carpeta como línea base de generalización.
