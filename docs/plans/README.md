# Cómo se escribe un plan

Cuándo hace falta un plan y el reparto contrato / implementación están en el
[CLAUDE.md raíz](../../CLAUDE.md) § Planes. Aquí, la forma y las reglas del archivo.

## Forma

`docs/plans/V<versión>-slug.md` (p. ej. `V7.6-e2-fino.md`). La versión del roadmap ES el número
del plan: ya está citada en commits, benchmarks y [docs/roadmap.md](../roadmap.md). Un plan fuera
del roadmap va con slug solo (`harness-automejora.md`). Frontmatter:

```yaml
---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: una línea con lo que falta DE VERDAD (una fase, una medición, un clic de Mario) o «sin pendientes»
descripcion: una línea con lo que cambia para quien usa Apolo
---
```

Título `# V<versión> — <el resultado, dicho como lo diría el usuario>` («El agente valida el
lote antes de aplicarlo», no «Refactor de verify»). Secciones en este orden; la que no
aplica se omite:

1. **Estado y origen**: quién lo pidió, con su frase textual, y qué evidencia lo disparó.
2. **El problema / lo que hay hoy**: medido, con `archivo:línea` o la consulta. Sin evidencia no entra.
3. **Lo que se revisó antes de escribir esto**: lo que se leyó del código y cambió la solución.
4. **Decisiones (para vetar)**: D1…Dn, cada una en negrita con su porqué. Mario veta por número.
5. **Alternativas descartadas** y por qué.
6. **Fases**: F0 mide (sólo lectura) … Fn verifica. Cada una: qué hace, qué paquete, tamaño
   S/M/L, de qué depende y cómo se verifica.
7. **Lo que este plan NO hace.**
8. **Riesgos**: riesgo y su mitigación.
9. **Bitácora**, al cerrar cada fase: qué se hizo, qué reveló cada intento fallido, la causa
   raíz del diagnóstico equivocado y los números medidos.

## Reglas

- **La versión se reserva mergeando el archivo a `main` apenas se aprueba**: dos planes con la
  misma versión mergean limpio y git no avisa. Tras cada rebase, verificar que siga única;
  tomada ⇒ renombrar. Quien detecta el choque con su plan ya implementado no renumera: los
  duplicados se citan por slug.
- **El estado es el frontmatter, nunca la carpeta**: nada se mueve a `done/`.
- **Sin commits en tres semanas, se decide**: `implementado` con nota de qué quedó fuera,
  `descartado` apuntando a quién lo cubrió, o `en curso` con dueño escrito.
- **Se documenta el razonamiento, no sólo el cambio**: en la bitácora del plan, en el CLAUDE.md
  que corresponda (la regla durable, en una línea) y en el commit (qué se creía, qué pasó, qué
  se aprendió; no un changelog).
- Si algún día hay un índice de planes, se GENERA del frontmatter con un script y jamás se
  edita a mano.
