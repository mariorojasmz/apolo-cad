---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: Sólo el plan; nada construido. Espera saldo de tokens (Mario, 2026-10-10). Va después de revision-de-taller, perfiles-con-acuerdo y acceso-de-herramienta
descripcion: Un transportador de rodillos por cadena sale completo con una sola orden, ya con las correcciones de la piloto
---

# Un transportador de rodillos por cadena con una sola orden

## Estado y origen

Mario quiere sacar muchas máquinas para su tienda ([publicacion-tienda](publicacion-tienda.md)).
La piloto (proyecto 2, transportador de rodillos motorizado por cadena, 2 m) costó ~1 h 10 min y
~60 M tokens leídos, y aun así tuvo 4 defectos que vio Mario
([revision-de-taller](revision-de-taller.md)). Recomendación aceptada el 2026-10-10: lo que se
repite va en una plantilla, para que cada lección quede dentro una sola vez.

## El problema / lo que hay hoy

- Las plantillas de máquina son super-comandos (raíz § Arquitectura): existe `create_conveyor`
  (faja), no uno de rodillos.
- `create_chain` (cadenas-pinones F2) no resuelve dos cosas que la piloto hizo a mano: en lazos
  1:1 con piñones de dientes impares, desfasar medio diente (12° en Z15) los alternos para que la
  cadena no se abulte; y elegir la distancia entre centros exacta para un número par de
  eslabones (159.034 en vez de 159.035 hacía saltar de 48 a 50 eslabones).

## Decisiones (para vetar)

- **D1. `create_roller_conveyor`**: largo, ancho útil, paso, Ø de rodillo, altura, carga y
  `motriz: cadena | libre`. Genera bastidor de ÁNGULO con ala abajo hacia afuera (lección de la
  tuerca), patas en H soldadas con travesaño entre patas (lección de c88), SIN travesaños sin
  función (c89), ejes con tuerca accesible, piñones dobles, cadenas 1:1, motorreductor,
  guardas con separadores entre rodillos, uniones y tierra declaradas.
- **D2. `create_chain` aprende las dos cosas**: `fase: "auto"` (medio diente en impares 1:1) y
  `eslabones: N` → calcula y publica la distancia exacta (o la recomienda si los piñones ya
  están puestos).
- **D3. La plantilla pasa sus propios chequeos**: test que la genera con 3 tamaños y exige
  `delivery_check` VERDE con gravedad + [acceso-de-herramienta](acceso-de-herramienta.md) +
  [perfiles-con-acuerdo](perfiles-con-acuerdo.md) sin avisos.

## Fases

- **F0 (S, sólo lectura)**: inventario del log del proyecto 2 (qué comandos y qué variables lo
  arman) como receta de la plantilla.
- **F1 (S, `commands`)**: D2 en `create_chain` (sube su `version`).
- **F2 (L, `commands` + `library`)**: D1 como super-comando con sus tests.
- **F3 (S, verificación)**: generar por MCP un transportador de 3 m y medir tiempo y tokens
  contra la piloto.

## Lo que este plan NO hace

- Transportadores por faja o por gravedad sin motor (otra plantilla, si hace falta).

## Riesgos

- Plantilla rígida que no sirve para variaciones → todo por variables y con piezas editables
  después (como `create_conveyor`).

## Bitácora
