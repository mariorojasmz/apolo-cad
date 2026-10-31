"""Historial de `VERSION_REGISTRO` (`registro.py`): qué cambió en cada versión de la puerta de
publicación y el plan que la subió. Salió del docstring del registro para que el archivo no
pase de 500 líneas; una versión nueva suma aquí su línea. Sólo texto: nada lo importa.

v2 F3 y riesgos; v3 brazo DOBLADO y cadena sin tensor; v4 `union.distancia_al_borde`; v5 sólo
chapas y alas; v6 `funcion.flujo_de_producto`; v7 (puerta-sin-sobrediseno) cuña de ENTRADA y tensor
en LAZO; v8 `diseno.sin_sobrantes` y el AVISO justificado; v9 (F3b) bisagra de servicio, acople,
resguardo = lo que cubre un peligro, L10 con rpm; v10 (F3c) `union.agujeros`, espárrago, factor de
servicio, `vigas`, holgura ≤ 4 mm; v11 (F3d) lo no evaluado se justifica por escrito; v12 (nombres-
por-funcion F2) `interfaz.nombres_por_funcion`; v13 (puerta-sin-sobrediseno F3e) el extremo de eje
LISO que sobresale ≤ ½·d de su apoyo no es peligro (OSHA 1910.219(c)(4)) y el COLISO del ancho del
paso es agujero de `union.agujeros`; v14 (F3f) el piso de lo ANCLADO es un sólido para las sondas
(ninguna nace ni pasa por debajo; el hueco piso ↔ panel lo decide la tabla 4), el remache declara
su Ø («Ø4.8») y se dimensiona a cortante, y `estructura.pandeo` evalúa las columnas de perfil de
catálogo (Euler/Johnson, K de AISC) y deja justificar las que no puede; v15 `riesgos.electrico` con
la regla nueva del ERC «hilo de protección sin conectar» (el PE de un cable multipolar llega a un
borne de tierra en sus dos extremos, IEC 60204-1 §8.2.1): un elevador aprobado en v14 con 13 cables
5G de PE suelto ahora falla; v16 (lo-que-se-mueve F1) `transmision_flexible.de_su_comando` (la
cadena por `insert_component` falla) y, en las poses que no son la de diseño, el `fasten` entre
piezas que mueven juntas distintas deja de tapar su choque; entra también la capacidad de la cadena
de izaje (cadena-de-izaje F2a), que dimensiona el pasador de sus amarres en `union.dimensionadas`;
v17 (lo-que-se-mueve F2) `seguridad.resguardo_abre` (un resguardo con interruptor sin una junta que
lo abra falla) y los extremos de esa junta entran como poses de la puerta de entrega, aunque no
estén en `doc.motion`; v18 (plantilla-rodillos-cadena F6) `union.largo_comercial` toma el anclaje
de expansión de catálogo por el largo de su ficha (no es un perno de la serie ISO); v19 (uniones-
que-tocan F1) `union.contacto_real` (lo declarado unido se toca: cada soldadura con un cordón
medido ≥ max(30 mm, 6·a) de EN 1993-1-8 §4.5.2, cada apoyo con área y cada perno cruzando un hueco
menor que su largo; `contacto.py`) y el dimensionado de cada soldadura con el MENOR entre el largo
declarado y el medido (una riostra a 5 mm de su poste con «100 mm de cordón» declarados daba τ en
verde); v20 (faja-compacta F1b, D12) `consumibles.reemplazables`: una banda sin fin que ATRAVIESAN
piezas además de sus tambores (cama, soportes, un travesaño) no se cambia sin desarmarlas y falla
salvo con su empalme de campo (pieza de catálogo `empalmes_banda` unida a la banda) o el empalme
mecánico en su nombre; v21 (plantilla-rodillos-cadena F9-e) `transmision.capacidad`: una cadena con
FS ≥ 1,2 cuya regla AVISA por una recomendación de desgaste (piñón < 17 dientes, centros < 30
pasos) se corrige o se JUSTIFICA por escrito; antes era FALLA sin salida (no es un modo de falla de
capacidad); v22 (hallazgos-del-revisor-en-la-puerta F5, D8) `union.retencion` cubre el EJE QUE
GIRA: el perno o pasador coaxial (± 1 mm) con una junta `giratoria`/`continua` que toca sus dos
cuerpos va trabado (tuerca autoblocante DIN 985 / ISO 7040, contratuerca, pasador de aletas o
anillo de retención) y no es un tirafondo ni un tornillo de madera (`ejes_giro.py`; los pivotes DIN
934 de una escalera de tijera aprobada en v21 ahora fallan); v23 (hallazgos-del-revisor-en-la-
puerta F1, D1) `material.conocido`: una pieza a medida con un material sin densidad tabulada falla
(se pesaba como acero: la tijera de «haya» de 6,9 kg en vez de 0,62); v24 (hallazgos-del-revisor
F3, D6) `apoyo.capacidad`: cada pie, pata, garrucha, rueda o regatón anclado que se compra resiste
su reacción × 1,5 con la carga de los requisitos (`apoyos.py`); v25 (hallazgos-del-revisor F2, D4 y
D5) `bom.comprable`: cada fila de la BOM alcanza para comprar o cortar (compra con norma, designación
o código de fabricante; varilla y perfil con largo; chapa con desarrollo; metal y madera a medida con
norma) y un grupo «(compra)» sale en UNA fila y no admite taladros de `join_bolted` hacia fuera
(`comprable.py`, `bom_comprable.py`, `compra_grupos.py`). v26 (hallazgos-del-revisor F4, D7)
`union.distancia_al_borde` mide la MADERA con su propio criterio (`borde.madera`: testa ≥ 4·d y
canto ≥ 3·d, criterio de diseño con los mínimos descargados a3,c y a4,c de EN 1995-1-1 tabla 8.4;
`borde.testa`: ningún tornillo ni tirafondo rosca a lo largo de la veta), también con los
tornillos de madera sin hexágono, y aplica con sólo esos tornillos (`tornilleria_madera`); la
madera sale de la tabla 3.3 de chapas; v27 (hallazgos-del-revisor F6, D9)
`higiene.limpiable`, sólo con el requisito `higienico`: cada soldadura con contacto lineal medido
es continua (sin largo, ISO 2553, o con un largo ≥ su línea de contacto) o declara su sellado
sanitario, y cada extremo hueco de un tubo que se fabrica queda a < 3 mm de una pieza soldada a él
en todo el borde de su hueco (`higiene.py`; la mesa inox con la repisa soldada 240 mm en 1 100 y la
pata abierta bajo la cubierta ahora falla); v28 (lo-fijo-que-gira-y-lo-que-cuelga F1, D1)
`movimiento.coherente`: un perno, soldadura o pegado entre dos piezas que mueven juntas de movimiento
distintas falla salvo que sea el eje de la junta, que las dos piezas sean coaxiales con ella
(bisagra) o que la prueba de pose (3° o 3 mm) no las separe ni las solape; la pieza coaxial que gira
unida a una quieta (alojamiento arrastrado) falla siempre, y el lazo cerrado o la junta de servicio
prismática o con la bisagra en la pieza quieta son aviso justificable (`movimiento.py`; la lavadora
con los resortes a gas quietos empernados a la puerta, la carcasa del motorreductor arrastrada y la
chumacera −Y hija del eje ahora fallan); v29 (hallazgos-del-revisor F8, tras las máquinas de la F7)
`bom.comprable` y `apoyo.capacidad` reconocen la compra declarada en sus formas naturales («(pieza de
compra)», «… de compra (ubicación)», «· compra: …», «tipo Marca código») y el rol no se pierde tras
una ESPECIFICACIÓN « · » («Pie nivelador (-X,-Y) · cuerpo AISI 304, espárrago M12×80 A2, …»: el pie
de compra salía a medida y sin apoyo; `materials.piece_role`); por lo mismo esa pieza deja de ser
tornillería (su espárrago se leía como un perno de 32 donde mide 22); `union.retencion` ve la tuerca
de un perno de cabeza más ancha que ella (el DIN 603 salía «sin tuerca»); y `borde.madera` pide la
punta de todo tornillo de madera ≥ 2 mm antes de la cara de atrás (el tirafondo 4×40 que asomaba
por el cabezal de 38); v30 (lo-fijo-que-gira-y-lo-que-cuelga F2, D2)
`union.contacto_no_cuelga`: un `contacto` del que cuelgan ≥ 0,5 kg (sin tornillería) falla si el
centro de masa de lo colgado queda más de 25 mm bajo la zona de contacto; apoya si queda sobre ella
o la zona lo abraza, lo de costado es aviso justificable y la unión de tubería roscada o tri-clamp
(DIN 32676) declarada en la nota del fasten transmite tracción (`cuelga.py`; las cuchillas de aire
y los ductos colgados del soplador de la lavadora, y la válvula de desagüe de la mesa con poza sin
su rosca declarada, ahora fallan); v31 (lo-fijo-que-gira-y-lo-que-cuelga F3, D3a y D4a)
`transmision_flexible.tension` reconoce la CATENARIA de una banda modular sin mirar su nombre
(polímero, rueda motriz accionada de eje cuadrado con ≥ 2 ruedas angostas, zona que cuelga libre
tras ella con 25,4–152 mm de comba, Intralox 2024 p. 15): carrera OK si cuelga libre hasta 152 mm
(el resto del rodaje del 1 % se retira por filas), FALLA si algo lo impide, SIN_EVALUAR con una
temperatura de operación fuera de 10–30 °C (falta el α); y `publicado.sustitutos_fieles` cierra la
sección de una banda de tramos o de dos pieles (`seccion_plano.cerrar`), apoya la cinta en todo el
largo de una zapata plana y no toma por tambor una pieza redonda sin junta que no toca la banda (la
lavadora de bandejas, que caía al casco convexo a través de un larguero, ahora es fiel); v32 (ronda
9 de una máquina real) `bom.comprable` reconoce la norma de compra de toda sigla de
`siglas_norma` en mayúscula con su número (EN, UNE, ASTM, JIS, IEC, NTP, BS…, además de DIN, ISO,
ASME y ANSI: «Bomba centrífuga EN 733 … (compra)» salía compra sin norma); AISI y SAE son el grado
del material y no designan la compra, y la «EN» mayúscula ya no corta la cabeza como preposición;
v33 (puerta-fuera-de-catalogo F1, D1 y D2) `material.conocido` y `bom.comprable` conocen los
tableros por su PRODUCTO antes que la especie (contrachapado EN 636, fenólico EN 314-2, MDF EN
622-5, OSB EN 300: «contrachapado de copaiba» es contrachapado), el poliuretano (deja de pesar
como PVC; un «sellador PU» pesaba como acero), el policarbonato, el EPDM, el cobre (Cu-ETP) y el
latón por su aleación (CW614N, EN 12164), cada uno con su fuente en `materials`; la madera acepta
el grupo de la norma peruana, «Grupo C (E.010)», además de la clase EN 338 / EN 14080, y su norma
también se lee del NOMBRE de la pieza (sólo normas de producto de madera: «Repisa (triplay
fenólico 18 mm EN 314-2)» pasa); un grupo mejor que el que la E.010 da a la especie (copaiba =
C) falla; el latón a medida pide su aleación y el cobre sin calificar es Cu-ETP.
v34 (plegables-en-la-puerta F2 y F4, D4 y D7) `movimiento.coherente` toma el pivote que CIERRA un
lazo declarado con restricciones (`distancia` + `punto_coincidente`) como un eje más: el par
coaxial con él (el brazo del compás y el buje del tablero) es bisagra si el lazo cierra en diseño
y con cada motor movido 3° o 3 mm (residuo ≤ 0,5 mm), su `axis` está declarado y cierra sobre la
pieza raíz; si no, SIN_EVALUAR con el porqué (`calidad_lazos.py`; el compás de la mesa plegable de
1,8 m con su lazo declarado deja de fallar como alojamiento arrastrado); y `agarre.retencion` falla
el REMACHE CIEGO (DIN 7337, ISO 15973–15984, ficha de remachadora) que es eje de una junta de
giro, con la salida de mercado (remache de hombro o perno de hombro ISO 7379 con autoblocante).
v35 (puerta-fuera-de-catalogo F2, D3–D5; la v33 es su F1) la tornillería a medida se clasifica por
el ROL que encabeza el nombre (`lints.es_nombre_de_tornilleria`: «Arandela de perno…», un taco o
un pie nivelador con «espárrago» en el paréntesis ya no son pernos; la tuerca, si encabeza): el
tornillo de madera a medida («Tornillo para madera…», «Tirafondo…», «autorroscante», DIN 571/96/
7997) es `madera` en `union.agarre`/`retencion`/`largo_comercial`, con la geometría de su cabeza
(avellanada: largo total, rosca del lado de la punta ≥ 6·d por EN 1995-1-1 § 8.7.2(3); hexagonal:
DIN 571 y 2/3) y la serie de largos de la ficha de su tipo (EN 14592 `TORNILLO-MADERA-*`, DIN 571),
no PERNO-M; `union.acceso_herramienta` evalúa la impronta declarada (TX, PZ, PH, ranura, Allen:
destornillador o punta en línea con el eje, hoja ISO 8764-2 y llave Allen ISO 2936 l2; Torx y
mano, criterio de diseño), la tuerca martillo, de barril y el inserto por el perno que los
atraviesa, y lo que sigue sin evaluar pasa justificado por escrito con la herramienta; un «Eje» sin
rodamiento, chumacera, rueda ni equipo unidos no es parte móvil, y la «Correa» de techo (o anclada)
no es transmisión; la norma tras un complemento de lugar («Arandela ancha del tablero DIN 9021»)
designa la compra.
v36 (puerta-fuera-de-catalogo F3, D6) `union.interferencia_declarada`: entre piezas que no son
tornillería, un par con `fasten` de cualquier tipo cuyo volumen común pasa de `EXCESS_TOL_MM3`
falla (la entrega lo excluía entero: la silla plegable aprobó con 9 903 mm³ de travesaño dentro de
la pata); la rosca engranada no cuenta, reconocida por la geometría del solape (anillo entre
cilindros coaxiales de Ø nominal y broca DIN 336 de una métrica gruesa, hasta su volumen + 5 %:
el pie M16 en su placa roscada de 12 mm, 565,5 mm³, y el espárrago M10 en su buje de 21, 457,7).
C) falla; el latón a medida pide su aleación y el cobre sin calificar es Cu-ETP;
v37 (puerta-fuera-de-catalogo F4, D7 y D8) `estructura.flecha` y `estructura.pandeo` calculan la
pieza A MEDIDA que trabaja (tablero, travesaño, montante, plancha, tubo de `run_script` o de chapa
cerrada) con su sección MEDIDA en cortes (rectángulo macizo, tubo rectangular o redondo, barra) y
el criterio de su material sin mezclarlos: metal, el de siempre (L/240, 0,6·fy, Euler/Johnson);
madera por grupo, RNE E.010 (admisibles y E mínimo, Art. 17–19 y 26–30); madera de clase EN 338 o
tablero EN, EN 1995-1-1 (§ 7.2 y § 6.3.2, kmod/γM); la que trabaja sin dos apoyos, sin sección
constante reconocible (la plancha perforada) o de madera sin clase sale SIN_EVALUAR justificable,
nunca NO_APLICA; el encolado es apoyo de la madera; `estructura.vuelco` suma las fuerzas de trabajo
de los requisitos (`fuerza_horizontal_n`, `altura_fuerza_mm`, `carga_borde_n`) con EN 1990 tabla
A1.2(A) (peso 0,9 / 1,1, variable 1,5, la favorable en 0: manda la máquina vacía); sin ellas, como
antes y lo dice.
v38 (plegables-en-la-puerta F1, D1–D3) con el requisito
`plegable` (la ficha del encargo lo pregunta aparte de `desarmable`), `plegado.posiciones` pide
al menos un estudio de movimiento con un fotograma `posicion: "uso"` y otro `"guardado"`, sus
valores dentro de los límites de cada junta y al menos una junta que cambie entre ellos (la silla
plegable sin juntas, que daba `movimiento.coherente` NO_APLICA, ahora falla «se pliega en la ficha
y no en el modelo»), y `plegado.espesor` mide la caja del guardado contra `espesor_plegado_mm`
(su dimensión menor mayor que lo pedido falla). El tránsito uso → guardado no es ítem: lo avisa
`delivery_check` (batería 9) con los choques nuevos respecto de la pose de diseño.
v39 (fix directo, lavadora y estructura solar) `bom.comprable` no le pide designación de compra a lo
EXISTENTE del sitio: la pieza cuyo rol o su complemento inmediato la declara existente, del cliente
o no suministrada («Calamina existente», «Correa delantera existente», «Mesa del cliente», «(no
suministrado)»; `library/suministro.py`) sale de la BOM, del costeo, de la lista de corte y de la
cédula y la evidencia la nombra (`no_suministradas`); sigue en la escena para apoyo, gravedad y
planos. La «Correa» de techo o de la cubierta ya no se compra como banda (`ROL_COMPRA`).
v40 (pie-nivelador F2, D1–D4 y D8) `apoyo.nivelador`: cada pie nivelador (ref de
`pies_niveladores` o pieza con rol de pie nivelador y vástago cilíndrico convexo con base coaxial;
anclado o no) engancha su rosca en la pose de diseño (rosca en la pieza + la tuerca a tope del lado
de la carga ≥ k·d de `agarre`, o una tuerca de altura normal m ≥ 0,8·d cruzada entera; material en
el eje = no se puede enroscar), va trabado (contratuerca a tope de la pila, autoblocante, tuerca de
bloqueo fundida o de su ficha, parche DIN 267-28 en la nota de la unión o la base fija soldada) y su
carrera −baja / +sube alcanza lo que pide el piso (DIN 18202 T2 f1 + T3 f3 a la diagonal entre
pies, o el requisito nuevo `nivelacion_mm`: falla si la suma no alcanza; un sentido < Δ/2 bloquea
salvo justificación); lo que tiene rol de pie nivelador y no se reconoce sale SIN_EVALUAR
justificable. El testigo `faja` pasa al criterio 7 de la plantilla (con la 5 la placa de 8 mm tenía
un agujero liso Ø12 por toda rosca).
"""
