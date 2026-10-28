---
estado: en curso
nota: contrato escrito por Claude con el criterio delegado (2026-10-28, vetable por número); falta F1
descripcion: La lista de corte mide la pieza que se corta (ángulo de cada extremo, largo exterior) y da la chapa por su espesor y su desarrollo, en vez de creer lo que declaró el comando
---

# La lista de corte mide la pieza, no lo que dice su comando

## Estado y origen

Re-revisión a ciegas de la «Plataforma de mantenimiento 1 m con escalera» (2026-10-28, tras la
corrección 11), dos MEDIA que no son de la máquina sino de la fábrica:

- La zanca c85 (UPN-120: `insert_component` girado con `transform` y las puntas recortadas por
  dos `add_joinery` tipo rebaje, cabeza vertical y pie horizontal) sale en `cut_list` como «corte
  recto, ángulo null, L = 854,1»: con esa lista el taller corta a escuadra y la zanca no asienta.
- Los peldaños c91/c217 y la chapa de pisada c438 (`create_sheet_metal`, chapa estriada de 3 mm
  plegada en U) salen con «espesor» 40 y 72,1 mm y el ancho de su CAJA, no con el espesor de la
  chapa y su desarrollo: no sirven para cortar ni para comprar chapa.

Causa: `library/cutlist.py` sólo sabe de ingletes por `Feature.miter` (lo que DECLARA
`create_frame`/`create_brace`) y de largos por la caja o `cut_length`; no mide la pieza ni lee la
chapa. Es el mismo modo de falla que [uniones-que-tocan](uniones-que-tocan.md): un control que cree
lo declarado. Lo mismo pasa a cualquier máquina que recorte un perfil con `add_joinery`,
`boolean_op` o `run_script`.

## Decisiones (para vetar)

- **D1. Perfil de catálogo cortable: se MIDE** (función pura sobre la forma, en `kernel` o
  `library`): el eje del perfil (la dirección de sus aristas rectas largas, la de extrusión), el
  largo EXTERIOR (la extensión de la pieza sobre ese eje) y, en cada extremo, el ángulo entre la
  cara de corte y la sección recta (0° = a escuadra), también si el corte es en dos planos
  (despunte). Lo declarado (`miter`, `cut_length`) queda como verificación: si no coincide con lo
  medido, gana lo medido. La lista agrupa por la medida.
- **D2. Un extremo que no es un plano** (una muesca, una boca de pescado, un rebaje que deja un
  escalón): «corte especial» con el detalle a plano, nunca «recto».
- **D3. Chapa** (`create_sheet_metal` y lo que el kernel reconozca como chapa del mismo espesor):
  espesor = el de la chapa; ancho × largo = el DESARROLLO (el mismo de `export_flat_pattern`, con
  su K por material); n.º de pliegues. Agrupa por material + espesor + desarrollo.
- **D4. Una fuente**: lo que lee la lista (BOM de corte, plano de despiece, CSV, cotización por
  peso o área) sale de esta misma medida; nadie vuelve a leer la caja.
- **D5. Costo**: la medida es por pieza única (las repetidas comparten firma) y se cachea por
  `id(shape)` con la regla de `core/apolo/CLAUDE.md` (referencia + `is`); medido en la clasificadora
  (480 piezas) y en la plataforma.

## Alternativas descartadas

- **Exigir que todo recorte se haga con `create_brace`**: lo cubre la guía, pero no protege lo que
  ya está ni lo hecho con `run_script`; la lista tiene que decir la verdad igual.

## Fases

- **F1 (library + kernel, M)**: D1–D5 con tests: un perfil girado y recortado con `add_joinery`
  rebaje da sus dos ángulos y el largo exterior; una riostra de `create_brace` da los mismos que
  declara; un perfil a escuadra no cambia (los testigos y las listas existentes, iguales salvo lo
  que antes mentía); una U de `create_sheet_metal` da 3 mm y su desarrollo; un extremo con muesca
  da «corte especial».

## Lo que este plan NO hace

- Nesting ni optimización de barras (`nesting` ya existe y toma estas filas).

## Riesgos

- **Perfiles cortos o casi cúbicos** (una placa de cierre de catálogo): el eje no se distingue;
  F1 decide por la ficha (el perfil se extruye en Z local) antes que por la forma.

## Bitácora
