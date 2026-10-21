# Física (`core/apolo/physics/`)

MuJoCo para gravedad, caída y la dinámica de la máquina. Lo común del backend (cachés por
`id(shape)`, cinemática) está en [core/apolo](../CLAUDE.md); los locks, en el
[CLAUDE.md raíz](../../../CLAUDE.md).

## Común

- Dos fases: `prepare_*` (OCCT → MJCF horneado, bajo `STATE_LOCK`) y `simulate_*` (bucle
  `mj_step` sobre datos puros, bajo `PHYSICS_LOCK`); `stability_test`/`drop_test` son wrappers
  de compatibilidad. [V6.2](../../../docs/plans/V6.2-rendimiento.md)
- `gravity_test`: piezas sujetas = estáticas, el resto cae, con casco CONVEXO por sólido.
  `drop_test` usa AABB. Su `fps` es el TOTAL de fotogramas (lo usa la puerta de entrega: no se
  toca); el de la dinámica es por segundo simulado.

## Dinámica (`dinamica*.py`, `banda.py`, `sensores.py`)

[V8.2](../../../docs/plans/V8.2-maquina-se-mueve.md) · medido en [V8.0](../../../docs/plans/V8-maquina-viva.md)

- No importa `api`, `doc` ni `state` (`tests/test_capas_dinamica.py`): recibe escena y dicts.
- El bucle es el `Integrador` (`dinamica_integrador.py`: `intercambio(control, fuerzas)` /
  `salida()`); `simulate_dynamics` = su `correr()`, igual bit a bit a V8.2
  (`tests/dinamica_v82_referencia.py`). Lo que corre en el bucle (`dinamica_integrador`,
  `_arrastre`, `_control`, `_datos`, `sensores`, `sim`) NO importa OCCT ni `library`: lo carga el
  worker de la co-simulación ([cosim](../cosim/CLAUDE.md)); la preparación con OCCT queda en
  `dinamica.py`, `banda.py` y `dinamica_motores.py`, que re-exportan lo que se movió.
- Sujeción SIN cruzar juntas móviles: lo móvil sale del grafo antes de buscar tierra (un
  tambor fijado a su chumacera sigue girando). Un cuerpo = hijo + juntas `fija`, como la FK;
  lo fijado por `fasten` a una pieza móvil sin junta queda FUERA y el aviso pide `arrastrar`.
- La inercia sale del SÓLIDO (GProp de OCCT, escalada a la masa: catálogo si hay ficha, si no
  `_link_physics`), nunca de la colisión: el casco de un tubo es macizo y la cápsula suma
  casquetes. La colisión simplifica libre: cápsula para rodillos/tambores, casco el resto.
- Grupos: máquina y bastidor NO chocan salvo `colisiones_maquina` (las piezas montadas se
  solapan: ejes en largueros, lagging sobre la banda); entonces cada padre–hijo lleva
  `<exclude>` y la pieza padre estática va en un cuerpo soldado propio para poder nombrarla.
- Fuerza explícita retenida un intercambio ⇒ su zona lineal escala con Δt: la banda usa
  ε = máx(0,02, 3·μ·g·Δt); con 0,02 fijo, a 4 ms la caja derivaba en guiñada (ciclo límite).
- `<velocity>` CON tope necesita J ≥ kv·Δt o salta la consigna y oscila entre topes (velocidad
  media 0). La inercia del rotor reflejada (J·i²) DOMINA una faja: con placa se suma siempre;
  si aún falta, se completa y se avisa.
- Signo de juntas = mano derecha sobre el eje, igual que la FK (`Rotation` de build123d es
  dextrógira). D7: el sentido de marcha se FIJA con `direccion_transporte`; sin ella se avisa
  (el ancla `eje_motriz` tal cual lleva la banda a la cola).
- El GIF de la dinámica (`gif_dinamica.py`) pinta con `kernel/render_vivo.EscenaViva` (el
  aspecto de `render_view`, una ventana, poses con `mover`, ~40 ms por fotograma a 640 px), no
  con matplotlib como `drop_test`: medido, ~2 s por fotograma con 2600 triángulos. Se tesela en
  la MISMA adquisición de `STATE_LOCK` que `prepare_dynamics`.
- Sólo se autodetecta la banda de `create_belt_conveyor`. Un lazo hecho a mano va en `bandas`
  con una junta giratoria/continua del tambor; sin ella queda FUERA por sus contactos con el
  tensor y el aviso pide `arrastrar`, que NO es la cura. Tambor en eje vivo tocando sus
  chumaceras: `arrastrar` no lo lleva (todo en `frontera`): continua al eje + `fija` eje→tambor.
  Sin mesa de recepción las cajas descargadas se apilan en la cabeza y frenan a las que siguen:
  para contar con la fotocelda, alimenta en serie (`cada_s`).
  [F3](../../../docs/plans/V8.2-maquina-se-mueve.md)
- La serie del visor (`dinamica_serie.py`) manda cada cuerpo RELATIVO a su pose inicial
  (T(t) = P(t)·P(0)⁻¹, como el GIF): el origen del cuerpo MuJoCo no es el de la malla. La
  velocidad de banda sale del `BandaDatos` del snapshot (`e`, `radio`), no de la salida D9.
  [visor-realista](../../../docs/plans/visor-realista.md) (F2)
- Productos con `cada_s`: nacen en su hora; antes esperan estacionados lejos (MuJoCo no crea
  cuerpos en marcha) y no salen en los fotogramas.
