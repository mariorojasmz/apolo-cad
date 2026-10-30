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
pata abierta bajo la cubierta ahora falla).
"""
