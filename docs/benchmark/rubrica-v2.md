# Rúbrica de entregables — v2 (2026-07-22)

Vara de CALIDAD del paquete Apolo bajo la **doctrina de RESULTADOS**: se mide el
ENTREGABLE terminado (3D validado + juego de planos de taller + memoria de cálculo +
BOM/cotización + manual), no la lista de features. El testigo es el criterio de un
despacho competente, codificado — **no** un documento humano fantasma.

> **Versionado — qué cambió de v1 → v2 y por qué**: v2 NO relaja ninguna ancla ni
> criterio de v1 (E1–E6 y sus pesos quedan IDÉNTICOS). Añade DOS criterios a E3
> (memoria de cálculo) porque V7.3 y V7.4 integraron a la memoria capacidades que un
> despacho valora y que v1 no podía puntuar: **E3.6 análisis de tolerancias (stack-up)**
> y **E3.7 FEA (pieza y ensamblaje) con contraste analítico**. Consecuencia DECLARADA:
> la nota de E3 pasa de promediar 5 a promediar 7 criterios — el % de E3 y el GLOBAL
> bajo v2 no son directamente comparables con v1 (se reporta la nota v1-comparable al
> lado cuando se re-califica). Los criterios nuevos exigen lo mismo que los viejos:
> integrado al ENTREGABLE, trazable y honesto — no «existe la feature».

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
- **E2.3** Tolerancias: ajustes ISO 286 donde hay asiento (eje h7, bores H7), roscas ISO 6410, tolerancia general (ISO 2768).
- **E2.4** Soldadura: símbolos ISO 2553 en uniones soldadas.
- **E2.5** Acabados y notas de proceso.
- **E2.6** Legibilidad/consistencia: 0 solapes (detector), globos↔BOM↔cédula consistentes, escalas sanas, cortes donde hacen falta.
- **E2.7** Formatos: PDF imprimible A4/A3 + DWG que abre.

### E3 · Memoria de cálculo (peso 20)
- **E3.1** Cobertura: banda/arrastre (método correcto por construcción), adherencia del tambor, pernos, soldaduras, L10 rodamientos, pandeo de patas, vuelco.
- **E3.2** Datos de entrada = requisitos REALES del proyecto (no defaults silenciosos).
- **E3.3** Trazabilidad: fórmula + sustitución + norma citada por verificación; el número se reproduce a mano (spot-check).
- **E3.4** Veredictos honestos: FS marginales marcados, supuestos declarados, nada "aprobado por defecto".
- **E3.5** ¿La firmaría un ingeniero? (juicio global con justificación).
- **E3.6** *(nuevo v2)* Análisis de tolerancias: cadenas de cotas DECLARADAS de los
  ajustes/ensambles críticos del diseño (asientos de rodamiento, alturas/luces de
  ensamble) en la memoria, con peor caso + RSS, fuentes de tolerancia citadas (ISO 286 /
  ISO 2768 / límites explícitos) y VEREDICTO contra el requisito; una cadena incompleta o
  inválida jamás da veredicto (aviso honesto). 3 = las cadenas críticas están y cierran
  con trazabilidad; 4 = además cobertura amplia (toda interfaz ajustada tiene su cadena)
  y cadenas «cerradas por construcción» distinguidas de las informativas.
- **E3.7** *(nuevo v2)* FEA integrado: análisis de la(s) pieza(s) crítica(s) Y del
  sub-ensamblaje portante (bonded) en la memoria con σ_vm/FS POR PIEZA, hipótesis
  IMPRESAS (BCs, cargas, exclusiones con su peso, malla), vigencia (aviso si la
  geometría cambió) y CONTRASTE con la verificación analítica (dos caminos independientes
  al mismo régimen — el FEA no reemplaza la analítica, la confirma). 3 = lo anterior con
  números que cuadran; 4 = además convergencia demostrada (malla refinada, gobernante
  consistente con la analítica) y limitaciones declaradas (qué NO se malló y por qué).

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
- Al re-calificar bajo v2 por primera vez, reportar TAMBIÉN el global v1-comparable
  (E3 sin E3.6/E3.7) para no romper la serie histórica.

**La meta NO es sacar buena nota — es que la nota sea VERDAD.** Toda puntuación ≤2 genera
una brecha accionable (qué falta, módulo, ítem V7, puntaje que desbloquea), ordenada por
(peso del criterio × distancia a 3). Ese ranking es el backlog priorizado de V7/V8.
