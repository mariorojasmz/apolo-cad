---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: contrato escrito el 2026-10-20 a pedido de Mario («debemos diseñar uno»); D1–D7 vetables; nada implementado
descripcion: La parada de emergencia del catálogo se ve como una de verdad —seta roja sobre fondo amarillo—, y una pieza comprada puede tener partes de distinto color sin dejar de ser UNA línea de la BOM
---

# La seta de emergencia se ve como una de verdad: roja sobre amarillo

## Estado y origen

Mario (2026-10-20): «como los botones de emergencia van a estar en todas las máquinas, debemos
diseñar uno, a menos que ya exista en catálogo».

Existe en catálogo, pero sólo en lo eléctrico. `ESTOP-40`
(`core/apolo/library/data/93_mandos.yaml:8`) tiene ficha eléctrica completa: es `S` con el
símbolo `seta_emergencia`, `parada_emergencia: true`, bornes 11-12 y un camino NC. El ERC
(`library/electrico/erc.py:368`) la exige. Su geometría, en cambio, es `builder: box` de
72×72×70: un cubo de un solo color. En el video y en los planos, la pieza que más mira un
inspector de seguridad es una caja.

## El problema / lo que hay hoy

- **Geometría de relleno.** `ESTOP-40` y los pulsadores Ø22 de `123_mandos_puerta.yaml`
  (`PULS-22-ROJO-NC`, `PULS-22-AZUL-NA`, `SEL-22-2POS-1NA`) son cajas.
- **Un componente = un color.** Lo deciden `library/apariencia.py::acabado_pieza` (`:214`), el
  payload de escena (`api/scene.py:153-193`, un `acabado` y un `albedo` por pieza), el material
  del visor, VTK y el GLB. La norma pide un actuador ROJO sobre fondo AMARILLO (ISO 13850 §4.3.6,
  IEC 60204-1 §10.7.3): con un color, o es todo rojo o todo amarillo.
- **No hay kits.** Ningún YAML del catálogo declara subpiezas. Armar la seta con 3 piezas
  sueltas daría 3 líneas en la BOM para algo que se compra como UNA referencia, y rompería la
  regla de que la BOM sirve para comprar ([revision-de-taller](revision-de-taller.md) F0).

## Lo que se revisó antes de escribir esto

- La regla «el color manual sólo pinta lo pintable»
  ([visor-realista](visor-realista.md), fix del 2026-10-19, flag `pintable` de cada acabado). Aquí
  se extiende: los colores normativos de una seta NUNCA se repintan.
- La memoria del proyecto: la biblioteca es paramétrica (builder + YAML) y no se bajan STEP en
  masa. La seta se dibuja con un builder propio y las cotas típicas de la línea de referencia,
  marcadas `cotas_verificadas: false`, como los pulsadores Ø22.
- La doctrina de la raíz: «una librería que se queda corta se reemplaza por una propia». Aquí no
  hay librería de por medio; el corto es nuestro (un color por pieza) y se arregla en general,
  no con un caso especial para la seta.

## Decisiones (para vetar)

- **D1. Zonas de acabado por componente.** Un builder puede devolver sus partes etiquetadas,
  `{zona: forma}`, y el YAML asigna un acabado a cada zona
  (`zonas: {seta: pintura_roja, base: pintura_amarilla, ...}`). La pieza sigue siendo UNA
  `Feature`, con un solo sólido (la unión), una línea de BOM y una masa. Las zonas son un dato
  DERIVADO del builder: no van al log ni al manifest.

  Por qué: sirve también para la botonera, la placa del motor o el display del variador, sin
  inventar kits.
- **D2. Las zonas viajan como rangos de triángulos.**
  - El teselado (`kernel/mesh.py`) marca de qué zona viene cada cara.
  - El payload de escena agrega `zonas: [{acabado, albedo, desde, hasta}]`, en índices de
    triángulos.
  - El visor arma `geometry.groups` con un arreglo de materiales.
  - VTK parte el polydata por zona.
  - El GLB pone una primitiva por zona en el mismo nodo.

  Una pieza sin zonas va exactamente igual que hoy, así que su payload no cambia.
- **D3. Los colores normativos no se repintan.** Una zona con `fijo: true` (la seta, el fondo
  amarillo) ignora `set_color`. El color de la pieza sólo pinta las zonas pintables (la caja de
  superficie, si el cliente la quiere en otro color).
- **D4. Dos referencias, según dónde se monta.**
  - `ESTOP-40`, para la puerta del tablero: seta roja Ø40 de retención por giro, collar, anillo
    de leyenda amarillo Ø60 «PARADA DE EMERGENCIA» y bloque de contactos detrás. Agujero de
    montaje Ø22,5.
  - `ESTOP-40-CAJA`, nueva, para la máquina: la misma cabeza sobre una caja de superficie
    amarilla de 72×72, con prensaestopa M20 abajo y 2 agujeros de fijación.

  Las dos llevan la misma ficha eléctrica. Cotas típicas de la línea Harmony XB5AS8445 + ZBY9…
  y Siemens 3SU1, con `cotas_verificadas: false`.
- **D5. Builder paramétrico `seta_emergencia`** en `library/` (diámetro de seta, tipo de
  montaje, alto de caja), con anclas `montaje` (cara de apoyo) y `agujero` (eje del Ø22,5, para
  `join_bolted` o el taladro de la puerta).
- **D6. La geometría de `ESTOP-40` cambia con los mismos params.** Es YAML + builder: se sube
  `GEOM_CACHE_EPOCH` con su motivo (regla de la raíz). Los tests que fijan su caja de 72×72×70
  (`tests/test_catalogo_electrico.py:162`) se actualizan a las cotas nuevas.
- **D7. Fuera de este plan, anotado para después:** los pulsadores Ø22, la botonera y el
  variador con zonas. Se hacen con el mismo mecanismo (D1–D3) cuando Mario los pida, o en
  V8.5 (el tablero 3D de verdad).

## Alternativas descartadas

- **Tres piezas sueltas (seta + collar + caja)**: tres líneas de BOM para una referencia
  comprada, y el ERC tendría que saber cuál de las tres es «la seta».
- **Textura pintada sobre la caja**: no da forma (la seta sobresale y se pulsa) y no la ve VTK.
- **STEP del fabricante**: contra la decisión de biblioteca paramétrica, con licencia por
  referencia y sin zonas de todos modos.
- **Un color por cara elegido a mano**: no es paramétrico y se rompe cuando cambian las caras.

## Fases

- **F0 (S, sólo lectura)**: medir antes de cambiar.
  1. Dónde se pierde la relación cara → triángulo en `kernel/mesh.py` y en el caché de
     teselado.
  2. Cuánto pesa en el payload agregar `zonas` (pieza sin zonas = 0 bytes).
  3. Cuánto cuesta en VTK partir un actor por zona.
  4. Cómo arma hoy las primitivas el GLB (`kernel/glb.py`).
- **F1 (M, `library` + `kernel`)**: D1, D5 y D6. Builder `seta_emergencia`, zonas en el loader y
  en el teselado, las dos referencias y el bump del epoch. Tests:
  - la seta da UN sólido y UNA línea de BOM;
  - las zonas cubren todos los triángulos;
  - las anclas caen donde deben.
- **F2 (M, `api` + `ui`)**: D2 y D3 en el payload y en el visor (grupos de material, calidad
  alta y normal, la sombra de contacto sin cambios). vitest de los grupos; pieza sin zonas
  idéntica a hoy.
- **F3 (S, `kernel/render_vtk` + `kernel/glb`)**: D2 en VTK y en el GLB de la tienda.
- **F4 (S, verificación)**: render del tablero de la faja 73 con la seta en la puerta y otra en
  la máquina. Pasan el video de video-realista y el GLB, y el ERC sigue verde. Lo juzga Mario.

## Lo que este plan NO hace

- No cambia la ficha eléctrica ni el ERC.
- No agrega la seta a las máquinas existentes: eso es modelado por MCP, máquina por máquina.
- No hace los pulsadores Ø22, la botonera ni el variador con zonas (D7).

## Riesgos

- **El teselado cacheado pierde la etiqueta de zona.** Mitigación: F0 lo mide; la zona va en el
  caché junto al teselado, por `id(shape)` con la referencia (regla de `core/apolo`).
- **Un payload más pesado en máquinas grandes.** Mitigación: sólo llevan `zonas` las piezas que
  tienen; F0 mide el máximo.
- **Un proyecto viejo abre con la seta nueva y cambia su geometría.** Es lo buscado (D6), con
  epoch. La interferencia con la puerta se revisa en F4.

## Bitácora
