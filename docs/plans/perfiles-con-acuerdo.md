---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: Sólo el plan; nada construido. Espera saldo de tokens (Mario, 2026-10-10)
descripcion: Los perfiles del catálogo saben dónde es plana el alma y cómo se orientan, así que un taladro mal puesto ya no sale en VERDE
---

# Los perfiles se portan como los reales

## Estado y origen

En la piloto (proyecto 2), Mario propuso pernos Allen («el rodillo tiene hueco hembra y por el
otro lado un perno allen, su cabeza es más pequeña») y el análisis mostró que tampoco asentaban:
en un UPN-100 real la parte plana del alma empieza ~18 mm debajo del borde (acuerdo r1 = 8.5 y
ala con pendiente 8 %) y el eje estaba a 20 mm. El modelo no lo veía porque
`library/data/13_perfiles_abiertos.yaml` dibuja los perfiles «SIN radios de acuerdo ni
conicidad de ala» (su propio comentario). Después, el subagente que cambió los largueros a
ángulo tuvo que probar rotaciones a ciegas para orientar la L. Parte de
[revision-de-taller](revision-de-taller.md). Reemplaza la tarea sugerida «Lint: barreno o
asiento sobre el acuerdo del perfil».

## El problema / lo que hay hoy

- Los variantes de UPN, IPE y L sólo tienen h, b, tw, tf (o leg, t): falta r1 y la pendiente.
- Un `drill_hole` o un eje que cruza el alma sobre el acuerdo pasa interferencias y lints.
- La orientación de un perfil abierto sólo se da con `rotation`; el builder `angle` no publica
  cuál ala queda dónde (el agente dedujo con probetas: (0, −90, −90) pone el material en
  +y/−z).

## Decisiones (para vetar)

- **D1. Datos de norma en el YAML**: `r1` (y `r2`, pendiente) por variante, de DIN 1026-1,
  EN 10365 y EN 10056-1. La geometría sigue prismática (no cambia ninguna firma → sin bump); los
  datos sirven a lints y planos.
- **D2. Lint «asiento fuera de la zona plana»**: un taladro, o la arandela/cabeza/tuerca coaxial,
  cuyo radio sale de la zona plana del alma (h − 2·(tf + pendiente + r1)) o del ala de un ángulo
  → AVISO con la distancia que falta. Va en `library/lints.py` (o módulo propio si pasa de 500
  líneas).
- **D3. Orientación declarativa**: param opcional de `insert_component` para perfiles abiertos,
  p. ej. `orientacion: {alma: "+y", alas: "-y"}` (canal) o `{ala_vertical: "+y",
  ala_horizontal: "abajo-afuera"}` (ángulo), que se traduce a rotación. Default = la rotación de
  hoy → un log viejo regenera igual.
- **D4. Anclas por familia** (`loader.ANCLAS`): `cara_alma_interior`, `zona_plana` para que
  `place`/mates puedan colgar de ellas.

## Alternativas descartadas

- Modelar los acuerdos en 3D: cambia volumen, peso y todas las firmas (bump de epoch) para un
  beneficio que el lint da sin tocar la geometría.

## Fases

- **F0 (S, sólo lectura)**: con la revisión 3 del proyecto 2 (UPN), contar qué taladros caerían
  sobre el acuerdo con D2 (deben ser los 40).
- **F1 (S, `library` YAML + test de datos)**: D1.
- **F2 (S, `library/lints.py`)**: D2 con tests (UPN-100 a 20 mm → aviso; a 30 mm → sin aviso).
- **F3 (M, `commands` + `library`)**: D3 y D4; sube la `version` de `insert_component` sólo si
  cambia su executor (contrato de comandos).
- **F4 (S, verificación)**: por MCP, orientar un ángulo con D3 sin probetas.

## Lo que este plan NO hace

- No revisa el acceso de la llave: [acceso-de-herramienta](acceso-de-herramienta.md).

## Riesgos

- Datos de norma mal copiados → test que compara 3 variantes por familia contra la tabla citada.

## Bitácora
