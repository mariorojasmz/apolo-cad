---
estado: en curso
nota: contrato escrito y aprobado por Mario (2026-10-29: «si amerita su plan para mejorar… procede»); F0 sin lanzar
descripcion: La puerta frena una pieza atornillada al bastidor que gira con un eje, un peso colgado de un simple contacto y la banda modular tensada por catenaria, y join_bolted deja de poner una cabeza dentro de un tubo
---

# La puerta ve lo fijo que gira y lo que cuelga de un contacto

## Estado y origen

Mario (2026-10-29), al ver en el visor una lavadora de bandejas de ~720 piezas simulando: «creo que
el motor está girando?, también su lado de chumacera?». Tenía razón, y la puerta de publicación
(registro v21) la había dejado pasar. Después pidió: «veo que sí amerita su plan para mejorar».

La máquina tomó 8 rondas de corrección. En ellas, lo que la puerta NO vio y vieron Mario o el
revisor a ciegas fue esto:

- **Lo fijo que gira (ronda 4).** La junta del eje motriz tenía como hija `fija` a la chumacera
  del lado opuesto, empernada a su ménsula. Además, un `contacto` chaveta ↔ reductor con
  `arrastrar` metía la carcasa del motorreductor en lo que gira. Al simular giraban motor y
  chumacera.
- **Lo que cuelga de un contacto (ronda 6).** Dos cuchillas de aire de 22 kg (56 kg con su
  ducto) colgaban sólo de una unión `contacto` (una abrazadera rápida), a ~555 mm de su centro de
  masa. La sujeción declarada las daba por sujetas.
- **La catenaria (todas las rondas).** La banda modular de acetal se tensa por su peso, con una
  zona de comba libre después de la rueda motriz, como piden los fabricantes. Sale SIN_EVALUAR en
  `transmision_flexible.tension` (tensor.reconocido / carrera / agarre: 0 de 1 lazos). Su
  animación tampoco sigue la comba modelada: `publicado.sustitutos_fieles` FALLA porque la cinta
  animada entra 50,8 mm en un larguero y el sólido de la banda, 0 mm.
- **`join_bolted` (ronda 8).** Una unión bajo un tubo cerrado dejó la cabeza del perno DENTRO
  del tubo (z 1904–1913), algo que no se puede montar. Con una chapa en Z falla con «falta cara
  PLANA ⊥ al eje X», porque el contacto se busca por solape de cajas. Y `fasten` rechaza `$k`
  dentro de un conjunto (`a: "$1+$2"`, 400).

## El problema / lo que hay hoy

- La FK mueve SÓLO los hijos declarados de cada junta (`robotics/pose.py::posed_shapes`), y
  `add_joint(arrastrar=true)` hace flood por los fijadores declarados, también los `contacto`
  (`commands/CLAUDE.md` § Juntas). Nada compara lo que mueve una junta con lo que está empernado o
  soldado a algo que no se mueve. `delivery_inputs.uniones_entre_juntas`
  (`services/delivery_inputs.py:49`) ya calcula los `fasten` cuyas piezas mueven juntas DISTINTAS,
  pero sólo para no tapar choques en pose; no lo juzga como contradicción.
- `loads.hanging_load_kg` (`library/engineering/loads.py:45`) da la masa que pierde tierra al
  quitar una unión, sin distinguir el tipo. La sujeción declarada (`check_assembly`, la puerta de
  entrega) cuenta un `contacto` como camino a tierra, igual que un perno o una soldadura. Un
  contacto transmite compresión (lo que APOYA), no tracción (lo que CUELGA).
- El tensor reconocido (`services/calidad_tensores.py`) son take-up, catálogo con `carrera_mm`,
  plantilla o metadato `tensores`. La catenaria de una banda modular no es ninguno de los cuatro.
- `join_bolted` busca el asiento por solape de cajas y exige una cara plana en el plano de apilado
  (`commands/exec_union.py:119`, `exigir_asiento`). No comprueba que la cabeza y la tuerca queden
  fuera del material.

## Lo que se revisó antes de escribir esto

- `services/calidad_ejes_giro.py` (hallazgos-del-revisor F5, mergeada hoy) ya sabe qué perno es
  EJE de una junta de giro: coaxial ± 1 mm y toca sus dos cuerpos. Ese perno no es una
  contradicción, es el pivote, así que D1 lo reusa en vez de reinventarlo.
- `services/calidad_contacto.py` y `kernel/contacto.py` miden la línea o el área de contacto de
  dos piezas: D2 toma de ahí dónde está el apoyo.
- `library/ruta_faja_modelo.py` y `fidelidad_faja.py`: la cinta animada es la línea media de la
  sección del sólido de la banda, con una comba = mín(CEMA 2 %, w·l²/8T, holgura) sólo en los
  tramos rectos del retorno. Una catenaria modelada más honda que eso queda fuera de la regla.
- `hallazgos-del-revisor-en-la-puerta` (en curso) no toca juntas, contactos colgantes ni
  catenaria: no hay solape.

## Decisiones (para vetar)

- **D1. Una unión RÍGIDA no une dos piezas que se mueven distinto.** Ítem nuevo
  `movimiento.coherente` (familia función):
  - un `fasten` perno o soldadura entre dos piezas que la FK mueve con juntas de movimiento
    distintas (`uniones_entre_juntas`, juntas giratoria/continua/prismática; las `fija` cuentan
    con su padre) FALLA con las dos piezas y la junta;
  - salvo que el perno sea el EJE de esa junta (`calidad_ejes_giro`) o el par se toque como
    pivote en la pose de diseño (la misma excepción `_se_tocan` de `uniones_entre_juntas`);
  - un `contacto` entre piezas que se mueven distinto no falla, porque es deslizamiento.

  Es el modo de falla «el modelo dice que gira algo que está atornillado al bastidor». No agrega
  piezas: se corrige la junta.
- **D2. Un `contacto` no sostiene lo que cuelga.** Ítem nuevo `union.contacto_no_cuelga`
  (familia estructura). Una unión `contacto` cuya carga colgada (`hanging_load_kg`) es > 0 y en
  la que el centro de masa de lo colgado queda DEBAJO del apoyo (zona de contacto medida, con una
  tolerancia que fija la F0) FALLA. Corrige: un apoyo debajo, una ménsula o un perno.

  Lo que apoya encima de un contacto (una bandeja sobre sus zapatas, un tanque sobre sus
  largueros) no cambia. Sin carga colgada (unión redundante) no se juzga.
- **D3. La catenaria de una banda modular es un tensado reconocido.** En
  `transmision_flexible.tension`, un lazo de banda modular (ref o designación de banda modular)
  con una zona libre después del motriz cumple si la comba modelada absorbe el alargamiento:
  térmico α·ΔT·L, más el de servicio que dé el fabricante. Necesita el α del material de la ficha
  y el ΔT de los requisitos.

  La F0 busca la fuente citable (guía de diseño de un fabricante de banda modular). Sin una
  fuente citable, la regla sigue SIN_EVALUAR justificable, como hoy: no se inventa un criterio.
- **D4. La animación sigue la comba modelada.** En `ruta_faja_modelo`, en el tramo de catenaria
  reconocido por D3, la cinta animada es la línea media del sólido (no la comba CEMA 2 %). Así
  `publicado.sustitutos_fieles` deja de fallar en una banda modular bien modelada.
- **D5. `join_bolted` no deja herraje dentro del material.** Un criterio nuevo (el 7, que el
  sello pone a todo comando nuevo):
  - rechaza con error accionable la cabeza, la tuerca o la arandela que caigan dentro del sólido
    o del hueco CERRADO de una pieza (rayo por el eje, como `union_taller`);
  - busca el asiento por la cara de contacto real (`kernel/contacto.py`) cuando el solape de
    cajas no da una cara plana (perfil Z, pieza rotada).

  Nunca cambia el criterio 6 (logs guardados).
- **D6. `fasten` acepta `$k` dentro de un conjunto** (`a: "$1+$2"`, `exec_uniones.py` y
  `apolo/batch.py`). Es un arreglo acotado, sin versión: hoy es un 400.

## Alternativas descartadas

- **Pedirle al modelador que simule y mire**: ya estaba en el brief y no lo vio en 3 rondas; lo
  vio Mario. Lo que la puerta no mide, reaparece.
- **Que `arrastrar` no siga los `contacto`**: cambia el replay de logs viejos (por eso nació en
  False) y no cubre la `fija` puesta a mano, que fue la mitad del caso.
- **Prohibir el `contacto` en toda carga**: una bandeja apoyada en zapatas ES un contacto
  correcto. El modo de falla es la tracción.

## Fases

Cada fase sube `VERSION_REGISTRO` con su línea en `calidad/historial_registro.py` y trae su
defecto sembrado.

- **F0 (S, sólo lectura): medir.**
  - Sobre los testigos públicos, los `.apolo` de máquinas reales del escritorio y la laptop
    (máquinas con juntas: mezcladora, puertas plegables, escalera de tijera, mesa plegable, la
    lavadora en sus rondas 3 y 8), contar cuántas uniones fallarían con D1 y D2 y cuáles son
    falsos positivos.
  - Para D3: la fuente citable del alargamiento y la comba de una banda modular, y cómo saber
    que una banda es modular sin nombre.
  - Para D4: por qué la cinta animada de la lavadora entra 50,8 mm en el larguero.
  - Para D5: reproducir los dos casos de `join_bolted` en un test.
- **F1 (M, `services` + `calidad`): D1.** Depende de F0. Verificación: la lavadora de la ronda 3
  falla por la chumacera −Y hija de la junta del eje y por la carcasa arrastrada; la de la ronda
  8 pasa; los testigos y una puerta plegable no cambian.
- **F2 (M, `library/engineering` + `services/calidad_contacto` + `calidad`): D2.**
  Independiente de F1. Verificación: la ronda 6 falla por las dos cuchillas y la 8 pasa; ninguna
  bandeja ni tanque apoyado falla.
- **F3 (M, `services/calidad_tensores` + `library/ruta_faja_modelo`): D3 y D4.** Depende de la
  fuente de la F0; sin fuente, sólo D4. Verificación: la banda modular de la lavadora sale con
  tensión OK (o SIN_EVALUAR justificable) y `sustitutos_fieles` OK.
- **F4 (S–M, `commands/union_taller` + `exec_union` + `exec_uniones`): D5 y D6.**
  Independiente. Verificación: un `join_bolted` bajo un tubo cerrado da error con la salida; uno
  sobre una chapa en Z atornilla; `fasten(a="$1+$2")` corre en un lote; los logs con criterio 6
  regeneran idénticos.

F1, F2 y F4 pueden ir en paralelo (máx. 3 agentes por PC); F3 tras la F0.

## Lo que este plan NO hace

- No acelera la puerta ni las tools en máquinas de ~700 piezas (`delivery_check`,
  `engineering_check` y `check_interference` acotado se cortaron por tiempo en 4 rondas): eso es
  un plan propio que se mide aparte.
- No cambia el revisor a ciegas ni la receta de la fábrica (eso vive fuera del núcleo).
- No toca el acceso de limpieza (cajón, túnel que no abre): no hay una medida general que no sea
  sobrediseño; queda para el revisor.

## Riesgos

- **D1 tumba mecanismos legítimos** (una bisagra modelada con su pasador como «perno», un brazo
  con buje): la excepción del eje de giro y del pivote que se toca los cubre. La F0 mide los
  falsos positivos antes de F1.
- **D2 confunde «cuelga» con «apoya» en piezas inclinadas o laterales**: la F0 fija la tolerancia
  y los casos (pieza colgada al costado de un poste); ante la duda, SIN_EVALUAR justificable, no
  FALLA.
- **D3 sin fuente**: queda como hoy (SIN_EVALUAR justificable), sin inventar el criterio.

## Bitácora
