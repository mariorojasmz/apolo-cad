# Defectos y la regla que los previene

Cada defecto CONFIRMADO de una máquina entregada —lo vea Mario o el
[revisor de taller](revisor-de-taller.md)— se corrige en el modelo y deja algo durable: una línea
en `core/apolo/design/guidelines.py`, un lint o chequeo con test, una pregunta del revisor
(`core/apolo/design/revision.py`) o una observación en el plan que corresponda. Aquí se anota la
fila; la columna «regla» dice qué lo previene hoy y qué lo prevendrá. «Pendiente» = todavía
nada automático: hay que abrir plan o sumarlo a uno.
Origen y métrica (defectos que Mario encuentra por máquina): [plan](plans/revision-de-taller.md)
(D4 y D5).

| fecha | máquina | defecto | quién lo vio | regla que lo previene |
|---|---|---|---|---|
| 2026-10-10 | transportador-rodillos-cadena-2m (proyecto 2) | «Pata (+Y, alimentación)» (c85): perfil ranurado de extrusión (aluminio) declarado acero y soldado a acero | Mario | Pregunta `material` del revisor (la corrida B y la C de F0 lo hallaron, ALTA). Automático: pendiente |
| 2026-10-10 | transportador-rodillos-cadena-2m (proyecto 2) | «Travesaño superior (alimentación)» (c88) montado ENCIMA de las patas cuando iría ENTRE ellas | Mario | Pregunta `marco_taller` del revisor (pasada 1; F0 lo vio a medias: detecta los dos extremos distintos, no decide cuál está bien). Automático: pendiente |
| 2026-10-10 | transportador-rodillos-cadena-2m (proyecto 2) | «Travesaño superior (centro)» (c89) sin función: los 20 ejes atornillados ya amarran los largueros | Mario | Pregunta `contrafactual` del revisor (pasada 1; la corrida C de F0 lo halló). Automático: pendiente |
| 2026-10-10 | transportador-rodillos-cadena-2m (proyecto 2) | «Tuerca del eje» a ~2,5 mm del ala del larguero: no entra llave ni dado | Mario | [acceso-de-herramienta](plans/acceso-de-herramienta.md) (ROJO en `delivery_check` si ninguna herramienta entra) + pregunta `herramienta` del revisor (las tres corridas de F0 lo hallaron) |
| 2026-10-19 | transportador-rodillos-cadena-2m (proyecto 2) | La cadena motriz no se puede tensar: base del motor lisa, sin ranuras; distancia entre centros clavada a 48 eslabones; la cadena pasa a 4,5 mm de la caja del motorreductor | revisor F0 | Pregunta `montaje` del revisor («¿se puede tensar o ajustar en servicio?»). Automático: pendiente |
| 2026-10-19 | transportador-rodillos-cadena-2m (proyecto 2) | Guardas abiertas: la de transmisión abre hacia −Y y las 19 cadenas rodillo a rodillo quedan abiertas por debajo (ramal inferior a ~690 mm del piso) | revisor F0 | Pregunta `guardas` del revisor (todos los lados, también por debajo). Automático: pendiente |
| 2026-10-19 | transportador-rodillos-cadena-2m (proyecto 2) | El rodillo flota ~26 mm en el eje Ø12 liso (sin distanciadores) y las tuercas, sólo por fuera, deforman el alma del larguero hacia adentro | revisor F0 | Pendiente |
| 2026-10-19 | transportador-rodillos-cadena-2m (proyecto 2) | Eje motriz Ø12 con el tiro de la cadena fuera del rodamiento: ~450 MPa en un atasco | revisor F0 (MEDIA) | Pendiente: la regla de eje de la memoria vive en el chequeo de la faja de plantilla (`conveyor_engineering_check`) y no ve una máquina armada a mano; [flecha-de-bastidor](plans/flecha-de-bastidor.md) cubre las vigas del bastidor, no los ejes |
| 2026-10-20 | faja de banda de `create_belt_conveyor` (y la 72/73, a mano) | El tambor motriz engomado (Ø101,6 + 2×6 = Ø113,6) atravesaba la banda, hecha con Ø101,6: ~496 cm³ de cruce y el tambor 6 mm por encima del ramal de carga. `check_interference` no lo veía: excluye los pares del mismo comando | agente de visor-realista F3 (al animar la banda) | `create_belt_conveyor` v2 (radio exterior por tambor) y su test de cruce banda–tambor. La 72/73 se corrige en el modelo, por MCP. Que el chequeo general mire dentro de un super-comando: pendiente |
| 2026-10-21 | transportador-rodillos-cadena-3m (proyecto 79, `create_roller_conveyor`) | Guarda de la transmisión abierta hacia el lado del motor: piñón Z30 y entrada cadena–piñón a la vista (franja de 72,4 mm) | revisor ciego (ALTA) | Pregunta `guardas` del revisor. Plantilla: hito I |
| 2026-10-21 | transportador-rodillos-cadena-3m (proyecto 79, `create_roller_conveyor`) | Los 29 lazos y los piñones Z15 quedan al aire por debajo en los 3 m (ramal inferior a 687 mm del piso) | revisor ciego (ALTA) | Pregunta `guardas` del revisor. Plantilla: hito I |

Los hallazgos MEDIA y BAJA restantes de F0 (uniones declaradas sin agujeros, BOM que no sirve
para comprar, tubos abiertos, tuercas sin seguro) están en la Bitácora del
[plan](plans/revision-de-taller.md); el UPN con alas paralelas lo toma
[perfiles-con-acuerdo](plans/perfiles-con-acuerdo.md) y el tablero eléctrico,
[V8](plans/V8-maquina-viva.md).
