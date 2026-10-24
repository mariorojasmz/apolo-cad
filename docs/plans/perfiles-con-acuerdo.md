---
estado: implementado   # implementado | en curso | sin verificar | descartado
nota: sin pendientes de código: F4 verificada por MCP (2026-10-21): dos ángulos orientados con D3 a la primera y lint de asiento 0 en la piloto; fricción (schema de 11 KB, render con ejes) en el hito H
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

### F1 (2026-10-19)

- `13_perfiles_abiertos.yaml`: `r1`/`r2` en las 22 variantes (L: EN 10056-1, r2 = r1/2; UPN:
  DIN 1026-1; IPE: EN 10365, un solo radio → sólo `r1`) y `pendiente_ala: 0.08` en el
  `specs_common` del UPN. Fuentes cotejadas: tabla EN 10056-1 de roymech (los 8 ángulos) y el
  catálogo DIN 1026-1 de Kocaer (los 7 UPN con su `d`); IPE-80 y 120 cotejados en catálogos
  de fabricante, el resto de IPE de las tablas de memoria y anclados por `d = h − 2tf − 2r`.
- `library/acuerdos.py` (puro): `inicio_zona_plana_alma` = tf + p·(b/2 − tw) + r1·tan((90° −
  atan p)/2) (tf medido a b/2, DIN 1026-1; con p = 0 es tf + r1) y `zona_plana_ala_angulo` =
  [t + r1, leg − r2]. La fórmula del plan («h − 2·(tf + pendiente + r1)») es su aproximación.
  `validar_acuerdo` la llama el loader: r1/r2/pendiente numéricos ≥ 0, pendiente como
  fracción, r2 sin r1 rechazado y zona plana que exista.
- `tests/test_perfiles_acuerdo_datos.py`: las 22 variantes contra la tabla citada; h − 2·s
  reproduce la `d` publicada (UPN ±1 mm, IPE exacta); UPN-100 → 17.87 mm (los ~18 de la piloto).
- Sin bump de `GEOM_CACHE_EPOCH`: el builder no lee las claves nuevas (sólo `param_keys`) y la
  firma de `insert_component` no incluye las specs; un test fija el volumen prismático.

### F2 (2026-10-19)

- `library/lint_asiento.py` (módulo propio: `lints.py` queda en lo suyo) y una línea en
  `predelivery_lints` → regla «pre-entrega · asiento fuera de la zona plana», `aviso` →
  AMARILLO en `delivery_check` y visible en `/api/checks`. El aviso nombra pieza y ref, Ø del
  taladro, distancia del eje al canto del ala (o al talón del ángulo) y la mínima (o máxima).
- **Desvío de la letra**: los taladros se leen de la GEOMETRÍA (caras cilíndricas del perfil),
  no de los comandos `drill_hole`. `join_bolted` taladra sin `drill_hole` y `drill_hole` por
  `cara` no trae `position`: leyendo comandos ambos quedaban ciegos. Las `=expr` ya llegan
  resueltas por el regenerate.
- Marco del perfil sin la pose del comando (un taladro borra `Feature.matrix`): h/b salen del
  bbox por coincidencia ÚNICA de cotas; en el ángulo, el largo es el eje sin desfase del
  centroide (un clip de ANG-50X5 de 50 mm se lee bien) y el talón, el lado hacia el que se
  desplaza. Un perfil girado en ángulo no recto o con cotas ambiguas (UPN-100 de 100 mm de
  largo) se SALTA: no se adivina.
- Asiento = el mayor entre el agujero (o su caladrillo) y la tornillería/arandela COAXIAL que
  toca el perfil (radio = media cota menor ⟂ al eje: entrecaras, Ø de arandela).
- Decisión: roscados y ciegos TAMBIÉN avisan (el plan no los exime; lo que asienta sobre ellos
  pisa el mismo acuerdo). Taladros por el ala de U/I: fuera de alcance (este lint es del alma).
- `tests/test_lint_asiento.py`: UPN-100 Ø13.5 a 20 mm → aviso «mínimo 24.6»; a 30 → nada;
  canto inferior, perfil girado, roscado, ciego, tuerca coaxial (26 mm: sin tuerca pasa, con
  tuerca M12 → mínimo 27.4), herraje lejano, IPE, ángulo (talón y punta, y clip corto), tubo
  cerrado y placa → nunca, y AMARILLO en `delivery_report`.

### F3 (2026-10-19)

- **D4** en `library/perfiles_abiertos.py` (`loader.ANCLAS` de `channel`, `i_beam`, `angle`).
  Toda ancla de CARA lleva el origen sobre la cara y el eje = su normal saliente (lo que espera
  un mate `coincidente`). U: `cara_alma_interior` (eje hacia la abertura), `dorso_alma`; I:
  `cara_alma_interior` (+x local), `cara_alma_opuesta`; U/I: `zona_plana` (centro de la zona
  plana = centro de la cara interior, por simetría) y sus LÍMITES `zona_plana_1`/`_2` (a `s`
  de cada canto, eje a lo largo de h hacia el centro: un asiento de radio ρ cabe si queda a
  ≥ ρ de ambos). L: `talon` (eje = el largo), `cara_ala_1`/`_2` (normal interior) y
  `zona_plana_ala_1`/`_2` (centro de [t + r1, leg − r2]). Las zonas planas dependen de
  r1/pendiente (specs, no params del builder): el loader pasa `specs` a la función de anclas
  que lo declara. `Component.familia` guarda el nombre del builder.
- **D3**: `insert_component.orientacion` (`OrientacionPerfil`, default None = la `rotation`
  de siempre): U `{largo, abre_hacia}`, I `{largo, canto}`, L `{alas: [ala_1, ala_2]}`
  (`largo` opcional, se comprueba), con direcciones `±x/±y/±z`. Excluye una `rotation` ≠ 0
  (validador del modelo); sólo giros rectos (inclinar = `transform`/`snap_to` después).
  `abre_hacia` = eje del ancla `cara_alma_interior`; el ala 1 sale hacia la normal de
  `cara_ala_2`. Errores con el porqué (familia sin orientación, claves que faltan o sobran,
  ejes no perpendiculares). `InsertComponentParams` salió a `commands/models_componente.py`
  (re-export PEREZOSO desde `models.py`: aquel importa `Vec3`/`Rot3`) y el executor a
  `commands/exec_componente.py`: `models.py` y `registry.py` bajan de tamaño.
- **Versión**: `insert_component` → **v2**. La geometría no cambia (con la orientación por
  defecto la matriz es la de siempre: test), pero la Feature sí (anclas nuevas) y la caché de
  geometría guarda Features: sin subirla, un open caliente servía perfiles SIN anclas (el
  motivo del epoch v3 cuando nacieron las anclas). Acotado a los proyectos con componentes
  (y `insert_project`, compuesto); sin bump de epoch.
- **Lint de asiento por anclas**: el marco sale primero de las anclas (sobreviven al taladro,
  que borra `Feature.matrix`, y viajan con todo lo que mueve la pieza) y se valida contra la
  pieza (ancho de zona plana = h − 2s, ejes perpendiculares, centro dentro del bbox); si
  faltan o no casan (copia por `mirror_feature`, que no propaga anclas) cae al bbox de F2.
  Gana: un recorte de UPN-100 de 100 mm (cotas ambiguas, F2 lo saltaba) y un larguero
  inclinado (taladros oblicuos; ahí el radio del herraje coaxial no sale del bbox y vale el
  del agujero). `asiento_zona_plana_lint(bbox=True)` fuerza el camino de F2: los tests
  comparan ambos.
- `tests/test_perfiles_orientacion.py` (63): anclas de las tres familias, supervivencia al
  taladro y al `transform`, mate `coincidente` contra `zona_plana`, las 12 orientaciones de la
  U, las 6 de la I y las 24 del L, orientación ≡ su euler, default = la pose de siempre (y
  reabre igual), errores, y anclas = bbox en pose recta.
- **Piloto** (revisión 124, sólo lectura): 40 avisos por anclas y 40 por bbox; los dos
  largueros UPN-100 (`c9`, `c10`, taladrados → sin matrix) publican las cinco anclas, con la
  zona plana del alma en z ∈ [662.87, 727.13] (eje del larguero a 695: s = 17.87).

### F4 (2026-10-21): verificación por MCP — PASA CON OBSERVACIONES

**Cómo** (ola 5, 2026-10-21): una sesión NUEVA `claude -p --model opus` con sólo las tools `apolo-cad` + lectura del repo, contra una API de la flota en :8100 con el proyecto 78 (copia de la piloto 74). Una sesión para cinco verificaciones: 53 min, 114 turnos, USD 5,28.
- Copia del larguero `ANG-75X6` con `orientacion {alas:["-y","+z"]}`: bbox y 5 anclas idénticos a c9, a la primera; clip `ANG-50X5` también.
- Lint de asiento: 0 avisos (= rev. 4 de F2).
- Fricción: `get_command_schemas("insert_component")` pesa ~11 KB (el enum del catálogo); `render_view(show_axes=true)` encuadra el origen y la pieza queda chica. Hito H.
