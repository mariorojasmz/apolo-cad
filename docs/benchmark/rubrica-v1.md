# Rúbrica de entregables — v1 (2026-07-10)

Vara de CALIDAD del paquete Apolo bajo la **doctrina de RESULTADOS**: se mide el
ENTREGABLE terminado (3D validado + juego de planos de taller + memoria de cálculo +
BOM/cotización + manual), no la lista de features. El testigo es el criterio de un
despacho competente, codificado — **no** un documento humano fantasma.

> **Versionado**: los criterios y las anclas NO se relajan entre corridas. Si cambian,
> sube de versión (v2, v3…) y se anota por qué. Correr `scripts/benchmark_package.py`
> tras cada V7.x y re-calificar con ESTA rúbrica = el test de regresión de calidad.

## Escala por criterio (anclas DURAS)

| Puntaje | Ancla |
|:---:|---|
| **0** | Ausente. |
| **1** | Presente pero un taller lo devolvería (errores/faltantes graves). |
| **2** | Usable con retoque de un ingeniero (el retoque se DESCRIBE). |
| **3** | Nivel despacho: se entrega a taller/cliente sin vergüenza. |
| **4** | Supera lo que un despacho típico entrega (más completo/consistente/trazable). |

**Reglas de puntuación** (no negociables):
1. **Evidencia por puntaje**: ningún número sin cita (archivo/página del entregable + qué
   se miró). Los puntajes sin evidencia no valen.
2. **Spot-checks numéricos obligatorios**: recalcular a mano ≥3 filas del BOM, ≥1
   verificación completa de la memoria, ≥2 cotas de láminas contra el 3D. Cualquier
   discrepancia = hallazgo aunque el documento "se vea bien".
3. **Autocalificación con contrapeso**: quien genera también puntúa → anclas duras +
   evidencia + re-auditoría posterior. El usuario (CLIENTE) tiene la última palabra.

## Criterios y pesos

### E1 · 3D validado (peso 15)
- **E1.1** Completitud física: toda pieza fabricable con proceso real; catálogo/medidas comerciales donde toca.
- **E1.2** Validación: interferencias solo intencionales (cada una justificada por escrito), 0 flotantes en soundness, gravity estable, DOF sin sobre-restricciones inexplicadas.
- **E1.3** Criterio de montaje/servicio: ¿se puede tensar la banda, cambiarla, dar servicio a chumaceras/motor?
- **E1.4** Parametricidad: aplicar «3.2m compacta» y volver — sin roturas ni desalineados.

### E2 · Juego de planos de taller (peso 30 — el más pesado, es donde perdemos)
- **E2.1** Completitud del juego: GA + 1 lámina/pieza fabricada + cédula de herraje + lista de corte; nada que el taller tenga que "deducir".
- **E2.2** Suficiencia de acotado: CADA pieza fabricable SOLO con su lámina. Datums = caras de FUNCIÓN/montaje.
- **E2.3** Tolerancias: ajustes ISO 286 donde hay asiento (eje h7, bores H7), roscas ISO 6410, tolerancia general (ISO 2768 — brecha esperada).
- **E2.4** Soldadura: símbolos ISO 2553 en uniones soldadas (brecha esperada 0-1).
- **E2.5** Acabados y notas de proceso (esperado bajo, brecha).
- **E2.6** Legibilidad/consistencia: 0 solapes (detector), globos↔BOM↔cédula consistentes, escalas sanas, cortes donde hacen falta.
- **E2.7** Formatos: PDF imprimible A4/A3 + DWG que abre.

### E3 · Memoria de cálculo (peso 20)
- **E3.1** Cobertura: banda/arrastre (método correcto por construcción), adherencia del tambor, pernos, soldaduras, L10 rodamientos, pandeo de patas, vuelco.
- **E3.2** Datos de entrada = requisitos REALES del proyecto (no defaults silenciosos).
- **E3.3** Trazabilidad: fórmula + sustitución + norma citada por verificación; el número se reproduce a mano (spot-check).
- **E3.4** Veredictos honestos: FS marginales marcados, supuestos declarados, nada "aprobado por defecto".
- **E3.5** ¿La firmaría un ingeniero? (juicio global con justificación).

### E4 · BOM + cotización (peso 15)
- **E4.1** Completitud vs escena (sólidos → filas; agrupación correcta; nada fantasma ni faltante).
- **E4.2** Pesos/cantidades correctos (spot-check ≥3 filas).
- **E4.3** Fuentes de costo DECLARADAS por fila; los referenciales marcados como tales.
- **E4.4** Cotización: margen/impuesto/moneda/fx explícitos, precio de venta defendible, notas honestas.

### E5 · Manual de ensamblaje (peso 10)
- **E5.1** Secuencia FÍSICAMENTE posible (¿el paso N no exige haber montado antes lo del paso N+2?).
- **E5.2** Paginado por sub-ensamblajes reales, herraje correcto por paso, imágenes legibles.

### E6 · Paquete e interop (peso 10)
- **E6.1** STEP re-importable (round-trip en un Apolo limpio o visor externo).
- **E6.2** Índice del paquete completo, versionado, reproducible (regenerable con un script).
- **E6.3** Tiempo total de producción documentado (la métrica de los ~100×).

## Cómputo del puntaje

- Por criterio: 0-4 con evidencia.
- Por entregable: promedio ponderado de sus criterios, normalizado sobre 4 → %.
- Global: suma ponderada de los entregables (pesos E1=15, E2=30, E3=20, E4=15, E5=10, E6=10).

**La meta NO es sacar buena nota — es que la nota sea VERDAD.** Toda puntuación ≤2 genera
una brecha accionable (qué falta, módulo, ítem V7, puntaje que desbloquea), ordenada por
(peso del criterio × distancia a 3). Ese ranking es el backlog priorizado de V7.
