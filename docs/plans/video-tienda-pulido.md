---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: F0–F1 en main (2026-10-19); F1b implementada (2026-10-20): manual y video siguen la secuencia de montaje del grafo de uniones (piloto: 10 pasos, video de 65 s en 3 etapas); faltan F2–F4, la música de Mario y decidir si se muestra el FS 1,09 de la cadena motriz
descripcion: El video de la tienda explica la máquina con sus datos de ingeniería, corta las etapas con ritmo parejo y se ve como un producto terminado
---

# El video de la tienda se ve y se lee como un producto

## Estado y origen

Primera corrida real de [publicacion-tienda](publicacion-tienda.md) F5 sobre la piloto (proyecto
2, revisión 4), el 2026-10-10: `publicar guion` + `publicar generar` sin música → video de 75 s
(2250 fotogramas), zips de 2.9 y 4.3 MB, puerta VERDE. Tiempos: abrir y validar 15.7 s, puerta
25.2 s, entregables 429.7 s, video 138.6 s. Mario: «ya vi y me gustó, y también acepto tus
recomendaciones, pero encárgate tú, el sonido lo voy a encontrar yo. Crea planes, cuando
tengamos tokens, implementamos cambios».

## El problema / lo que hay hoy

Revisado cuadro por cuadro (fotogramas 150, 750, 1350 y 2100):

1. **Los rótulos cuentan piezas, no explican**: «Se suman 2 largueros, «Eje del rodillo», «Tubo
   del rodillo» y 4 piezas más» (`services/rotulos.py:117` `texto_etapa`). No dicen nada que
   le sirva a quien va a fabricar o comprar.
2. **Etapas mal cortadas**: 3 etapas para 99 pasos visuales; la primera dura 29 s y sólo muestra
   dos largueros y un rodillo; un título se corta («Patas y travesaños, Motorreductor y 2…»).
   Capítulos: 00:00, 00:29, 00:43, 00:56 (`services/construccion.py:252` `etapas`).
3. **Aristas rojas en todas las piezas**: el render vivo dibuja las aristas de feature con el
   color de acento (`kernel/render_vivo.py:287`, `actor_aristas` de `render_comun`). Parece CAD
   en depuración, no un producto.
4. **Cierre ilegible**: «Descarga los planos y el modelo 3D» en blanco sobre fondo claro y
   encima de la máquina.
5. **Sin DWG**: el export pide ODA File Converter (gratuito); los PDF sí salen.
6. **Entregables lentos**: 430 s de 610; el video sólo 139 s.

## Decisiones (para vetar)

- **D1. Rótulos con datos de ingeniería**: cada etapa dice QUÉ y POR QUÉ con cifras del modelo:
  catálogo (perfil, Ø de rodillo, serie de cadena, motor kW/rpm), variables (paso, largo, altura)
  y cálculos ya hechos (factor de seguridad de la cadena, flecha). Plantillas por rol en
  `services/rotulos.py` (p. ej. rodillos → «20 rodillos Ø2″ cada 95 mm sobre ejes fijos M12»);
  sin plantilla, el texto de hoy. Máximo 2 líneas.
- **D2. Ritmo parejo**: etapas por GRUPO del documento (Bastidor, Rodillos, Cadenas, Patas,
  Motorreductor, Guardas), con mínimo 6 s y máximo 15 s por etapa; un patrón (20 rodillos)
  aparece en un solo paso con crecimiento rápido, no 20 pasos lentos. Títulos ≤ 32 caracteres,
  sin «y 2 más»: si no caben, se nombra el grupo.
- **D3. Aspecto de producto**: aristas gris oscuro y finas (o ninguna) en el video; el acento de
  color queda sólo para la pieza que entra. Los materiales salen de la tabla única de
  [visor-realista](visor-realista.md) D5 cuando exista; mientras, colores del documento. Desde
  que exista, TODO video (diseño, montaje y la máquina andando) usa esa tabla siempre: no hay un
  «modo realista» aparte que haya que acordarse de prender.
- **D4. Cierre legible**: el texto final va en el panel inferior (el mismo del rótulo), con
  contraste mínimo 4.5:1, y la máquina gira completa en la parte superior.
- **D5. DWG como requisito chequeado**: `publicar guion` avisa al empezar si falta ODA (no al
  final, tras 7 minutos) con el enlace de descarga; sin ODA el zip sale sin DWG y lo dice.
- **D6. Entregables en paralelo con el video** si el lock lo permite (el render es fuera de
  `STATE_LOCK`); medir primero qué entregable se lleva los 430 s.
- **D8. Secuencia de MONTAJE real, una sola para el video y el manual**. Mario preguntó (2026-10-10)
  si el video trae el procedimiento de ensamblado. Hoy no: el video sigue el orden del log
  (cómo se DISEÑÓ) y `drawing/assembly_manual.py` también deriva su secuencia «del log de
  comandos + familias de catálogo» (línea 426). El taller arma en otro orden: primero lo soldado
  (bastidor + patas + travesaños), después lo atornillado en orden de acceso (ejes y rodillos,
  piñones, cadenas, base del motor, motor, guardas al final). Se deriva una secuencia de montaje
  del GRAFO de uniones (soldadura antes que perno; una pieza entra después de aquella a la que se
  fija; lo que tapa el acceso a un fijador va después, con el chequeo de
  [acceso-de-herramienta](acceso-de-herramienta.md) si ya existe) en un módulo puro de
  `services`, y la usan el manual y el video (`--modo montaje`; `--modo diseño` = el de hoy).
  Para la tienda, el video por defecto es el de montaje: le sirve a quien fabrica.
- **D7. La música la pone Mario** con `--musica` y sus datos de licencia en `ficha.yaml`; el plan
  no busca pistas.

## Fases

- **F0 (S, sólo lectura)**: perfilar los 430 s de entregables; contar pasos por grupo de la
  piloto para fijar los topes de D2.
- **F1 (M, `services`)**: D1 y D2 con tests sobre la piloto (títulos ≤ 32, ninguna etapa > 15 s,
  rótulo de rodillos con Ø y paso).
- **F1b (M, `services` + `drawing` + script)**: D8, la secuencia de montaje desde el grafo de
  uniones, usada por `assembly_manual` y por `publicar --modo montaje`; test con la piloto
  (soldado antes que atornillado; guardas al final; cada pieza después de su soporte).
- **F2 (S, `kernel/media`)**: D3 y D4, con captura comparada.
- **F3 (S, `publicacion` + script)**: D5 y D6.
- **F4 (S, verificación)**: regenerar el video de la piloto con la música de Mario; lo juzga él.

## Lo que este plan NO hace

- La máquina andando al final del video: es [visor-realista](visor-realista.md) F4.
- Voz en off, subtítulos en otros idiomas y subida automática a YouTube (D15 de
  publicacion-tienda: manual).

## Riesgos

- Rótulos con cifras equivocadas → sólo cifras leídas del documento o del catálogo, nunca
  escritas a mano; test que compara cada cifra con su fuente.

## Bitácora

### F0/F1 (2026-10-19)

Implementó un subagente en un worktree; la piloto se leyó en sólo lectura de la base local
(proyecto 74, 341 comandos, 201 sólidos) y del `generacion.json` de su F5.

**F0 — dónde se van los 430 s de entregables** (los `registros` de la F5):

| entregable | s |
|---|---|
| manual de ensamblaje (PDF) | 126,7 |
| juego de planos (PDF) | 81,5 |
| juego de planos (DWG): **falló sin ODA** | 69,6 |
| hoja de conjunto GA (PDF) | 59,5 |
| memoria de cálculo (PDF) | 43,2 |
| render iso + lateral + planta | 32,1 + 6,9 + 6,9 |
| STEP, BOM, lista de corte, nesting | 3,3 |

El manual, los planos y la GA son el 62 %; el DWG gastó 70 s para fallar al final (lo que D5
ataja avisando al empezar). Datos para D6 (F3).

**F0 — pasos por grupo de la piloto**: cargar 10,2 s, `pasos_visuales` 11,9 s, 99 pasos
visuales. Bastidor 42 (2 largueros + **40 `drill_hole` seguidos**), Rodillos 18 (6 piezas, 8
patrones, 4 tuercas), Cadenas 19 (**un `create_chain` por lazo**), Patas y travesaños 11 (7 +
las 4 placas base, k 334–337, al final del log), Motorreductor 5, Guardas 4. En el orden del log
son 10 tramos de grupo (Bastidor y Rodillos se alternan dos veces). Los topes de D2 (6 y 15 s)
quedan como se vetaron: con 52 s de presupuesto (75 − 23 fijos) caben 5 etapas.

**F1 — lo construido** (`services/rotulos.py` 395 líneas, `services/datos_rotulos.py` 98,
`services/construccion.py` 401; `tests/test_video_pulido.py`, 35 casos):

- **Compactar** (D2): los pasos seguidos del mismo grupo que agregan piezas de la misma
  *familia* (primera palabra del rol sin paréntesis: «Pata (-Y, alimentación)» → pata) son UN
  paso del video, el último `k`; los retoques (taladros) se juntan entre sí o con el paso que
  puso la pieza. La piloto baja de 99 pasos a 23. Un patrón crece en hasta 8 oleadas parejas
  (`revelado`) y pesa 1 (`peso_roles`, por familias; retoque 0,5), peso que ahora comparte
  `publicacion/video.py` en vez de duplicar la fórmula.
- **Ritmo** (D2): `etapa_min_s` 6 (antes 10, el mínimo de un capítulo de YouTube: los capítulos
  ya se funden aparte en `guion_video.capitulos`) y `etapa_max_s` 15. La duración se reparte por
  nivel entre 6 y 15 s; con poco que mostrar el video sale **más corto** que el objetivo, no más
  lento: una etapa larga se topa en 15 s en vez de partirse en «Rodillos (1/2)».
- **Títulos** (D2): ≤ 32 caracteres generados; varios grupos → «A y B» (« · » si un nombre ya
  lleva «y»), sin contar los grupos que sólo se retocaron; si no cabe, el grupo que más pesa.
  Nunca «y 2 más». La validación del guion editado a mano sigue en 60/280: un guion viejo vale.
- **Rótulos** (D1): `datos_rotulos(doc)` lee una vez el documento regenerado (catálogo, largo de
  corte, espesor de chapa resuelto, centro y medidas, requisitos y FS de cada cadena desde
  `chain_rules`, el mismo de la memoria). Las plantillas son por TIPO de dato antes que por
  nombre —rodillos (Ø nominal, paso medido entre centros, Ø del eje y el porqué del paquete),
  motorreductor (kW, rpm), cadena (serie y FS), piñón (serie y Z), tornillería (M), perfil del
  catálogo (nombre y largo o rango) y chapa (espesor)—, porque así sirven a máquinas que no se
  llaman como la piloto. Cada una dispara UNA vez, en la etapa que más piezas de su base agrega.
  Dos líneas = 100 caracteres (en la piloto, 103 caben y 111 no; el test lo mide con
  `maquetar_rotulo`); si no cabe, cae primero el detalle, después lo genérico y al final el porqué.

**Guion de la piloto con 75 s** (total 75,0 s; capítulos 0:00, 0:19, 0:31, 0:56):

| etapa | s | rótulo |
|---|---|---|
| Bastidor y Rodillos | 15,0 | Se suman 2 largueros de ángulo L 75x6 de 2 000 mm, «Eje del rodillo» y «Tubo del rodillo». |
| Rodillos | 11,6 | Se suman 19 rodillos Ø2" cada 95,25 mm. Cada paquete de 400 mm apoya en 4 rodillos o más. |
| Cadenas · Patas y travesaños | 6,9 | Se suman 19 cadenas rodillo a rodillo ASA 40, 4 patas de tubo HSS 2"x2" de 660 mm y 3 piezas más. |
| Motorreductor | 9,3 | Se suman «Motorreductor» de 0,37 kW a 50 rpm. Cadena motriz con factor de seguridad 1,09. |
| Guardas | 9,3 | Se suman 40 tuercas del eje M12, «Guarda de cadenas» de chapa de 2 mm y 8 piezas más. |

Antes: 3 etapas de 25, 14 y 13 s y un título cortado. Con 50 s salen 3 etapas (7,8 / 6 / 13,2) y
con 90 s, 5 (15 / 15 / 10,1 / 13,5 / 13,5).

**Pendiente y avisos**:
- El FS de la cadena motriz (1,09) sale tal cual de la memoria: cumple (≥ 1) pero se ve justo en
  un video de venta; decidir si un FS bajo se calla o se muestra (hoy, siempre la cifra real).
- La flecha (D1) no entra: `services` todavía no expone la del bastidor (flecha-de-bastidor F1
  vive en `library`). Cuando una regla la exponga, es un `Frase.porque` más en `rotulos.py`.
- El material de cada pieza (tabla de visor-realista D5) queda como punto de enganche en
  `datos_rotulos`; hoy no se usa.
- Los rótulos se juzgan en el video de la F4; la piloto no se regeneró (sin música todavía).

### F1b (2026-10-20)

Implementó un subagente en un worktree; la piloto se leyó en sólo lectura de la base local
(proyecto 74, 341 comandos, 201 sólidos, 264 uniones y 4 anclajes declarados).

**Lo construido**:

- `services/montaje.py` (puro, ≤ 0,3 s en la piloto): `secuencia(doc, scene=)` → `PasoMontaje`
  (título, ids, unión, nivel, grupo, texto «Se atornilla (M12) a «Larguero (-Y)» y …»). Reglas en
  su docstring: (1) soldadura/pegado = conjunto de taller que entra entero; (2) cada conjunto
  después de TODOS sus vecinos de nivel menor (BFS de uniones desmontables desde los `ground`) y,
  a igual nivel, `a` después de `b`; (2b) **la tuerca cierra**: después de lo montado sobre su eje;
  (3) **lo que tapa va después**: pieza plana (medida menor ≤ 0,3 de la siguiente) que cubre ≥ 50 %
  de otra en la proyección de su cara y queda por fuera; los soportes ganan (restricción que haría
  ciclo, descartada); (4) prioridad grupo del log → nivel → log, y **se termina lo empezado**
  (primero lo listo de la misma clase grupo + familia que el último). Pasos = conjuntos seguidos
  de igual unión, grupo y familia. `pasos_manual` lo da con la forma de `assembly_manual`.
- Manual: `assembly_manual(stages=)` y `_instruction` suma el texto de la unión; el endpoint pasa
  la secuencia cuando `hay_grafo(doc)` (uniones o anclajes declarados); sin ellos,
  `order_by_support` de siempre. Docstring de la tool MCP y golden re-congelado.
- Video: `services/montaje_video.py` arma `construccion.Paso` SINTÉTICOS (k = lugar en la
  secuencia, agregados = piezas de la escena final) y reusa `etapas` (compactado, títulos,
  duraciones y rótulos D1/D2 sin duplicar nada). El guion lleva `"modo": "montaje"` (clave
  OPCIONAL: un guion sin ella es de diseño y sigue valiendo) y cada paso es una TANDA de ids, que
  `validar_guion` revisa (lista no vacía, cada pieza una vez, que existan). `publicacion/video.py`
  las suma con `_Tandas` sobre `doc.scene`: no regenera prefijos.
- `publicar guion --modo montaje|diseño` (por defecto montaje: D8, el de la tienda);
  `flujo.guion(modo=)` rechaza un modo desconocido antes de abrir el proyecto.

**Piloto** — la secuencia (10 pasos, 201 piezas):

| paso | unión | piezas |
|---|---|---|
| Conjunto soldado · Bastidor | soldado (18 uniones), anclado al piso | 17 |
| Eje del rodillo | perno M12 a los dos largueros | 20 |
| Tapa con rodamiento | contacto con los ejes | 40 |
| Conjunto soldado · Rodillos (tubo + buje + piñón) | soldado, sobre las tapas | 60 |
| Tuerca del eje | se enrosca en los ejes | 40 |
| Cadena rodillo a rodillo | contacto con los 20 piñones | 19 |
| Motorreductor · Piñón motriz · Cadena motriz | perno M8 · perno M6 · contacto | 1 + 1 + 1 |
| Guardas | perno M6 a separadores y portamotor | 2 |

Antes (`order_by_support`, autodetectado): Patas y travesaños 11, Motorreductor 4 (con el motor
ANTES que los largueros), Bastidor 2, Rodillos 160 de un golpe, Cadenas 19, Guardas 5.

Video de montaje con 75 s de objetivo: **3 etapas, 65 s** (Bastidor 12 s, Rodillos 15 s,
«Cadenas, Motorreductor y Guardas» 15 s; capítulos 0:00, 0:16, 0:31, 0:46). Con 50 s, 3 etapas
de 6,2 / 10,4 / 10,4 s. Sale más corto que el de diseño (5 etapas, 75 s) porque los topes de
D2 cortan: tres pasos de una pieza (motor, piñón, cadena motriz) no llegan a 6 s y se funden.
Los rótulos son los de F1 (el del motor, 0,37 kW, no cabe en la etapa de las cadenas).

Manual: 11 láminas (antes 7). Cada lámina renderiza lo montado hasta ahí: 1,9 s con 17 piezas,
19,6 s con 137. El manual entero tardó 1 221 s, pero con dos suites completas de pytest de otra
sesión corriendo a la vez: no es comparable con los 127 s de la F5. Entra a D6 (F3): medir ahí.

**Intentos fallidos**:

1. El rango de grupo salía recorriendo los CONJUNTOS: el bastidor soldado trae la base del motor
   y los separadores, así que Motorreductor y Guardas quedaban 2.º y 3.º y el motor entraba antes
   que los ejes. Se ordena por la primera PIEZA de cada grupo en el log.
2. Cobertura por caja contenida: la guarda de cadenas es una tapa por ENCIMA (z 754–770) y las
   cadenas quedan debajo (688–762): ninguna caja contiene a la otra. Quedó la proyección sobre la
   cara de la pieza plana más la cara exterior más lejos del centro de la máquina.
3. Sin 2b, las tuercas entraban antes que el rodillo (el «contacto» no dice el sentido de
   inserción). La primera 2b usaba «la caja del eje corta la de la pieza»: la cadena abraza el
   piñón y corta la caja del eje → tuercas y cadenas intercaladas, 47 pasos. Quedó «el centro
   de la pieza cae dentro de la caja del eje» (lo coaxial).
4. Con 2b, la prioridad por nivel intercalaba rodillo, tuercas, rodillo… (la tuerca es nivel 2 y
   el rodillo 3): 48 pasos. Lo arregló «se termina lo empezado».

**Pendiente y avisos**:

- El acceso de herramienta no entra a propósito: si la llave entra con la máquina terminada
  (si no, la puerta ya está en ROJO), con menos piezas también.
- Las tapas entran antes que el tubo porque el grafo dice eje → tapa → tubo; en el taller el
  rodillo se presenta con sus tapas a presión y el eje lo atraviesa. Sin un dato de sentido de
  inserción en el `fasten` no se distingue; queda para el revisor de taller.
- El video de montaje no se renderizó sobre la piloto (sin música todavía): se juzga en la F4. El
  e2e de la publicación sí lo renderiza en modo montaje (mesa de 5 piezas).
- Tests: `tests/test_montaje.py` (18: la piloto en cajas con su mismo grafo —orden, soldado antes
  que atornillado, cada pieza después de su soporte, guardas al final, tuercas al cierre—, tapa que
  sostiene algo, tapa suelta, mismo nivel, sin grafo, sin anclajes, ocultas, parte acotada,
  manual, endpoint, etapas, guion validado, tandas) y 1 en `tests/test_publicacion_e2e.py`
  (montaje por defecto, diseño a pedido, modo desconocido).
