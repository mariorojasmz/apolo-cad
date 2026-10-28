---
estado: en curso
nota: F1 implementada (2026-10-28, decisiones F1-a…F1-j vetables en la Bitácora); falta revisarla y mergearla. Pendiente fuera de F1 - chapa plegada sin ficha (F1-j) y el ∠ medido en el BOM (F1-i)
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

### F1 (2026-10-28)

Implementada en la rama del worktree (sin mergear). Archivos: `kernel/corte_barra.py` (medida
pura, D1/D2/D5), `library/cutlist_medida.py` (qué se mide, contraste con lo declarado, textos
únicos), `library/chapa_ficha.py` (ficha + desarrollo, D3/D4), `library/cutlist.py`,
`commands/escena.py` (`Feature.chapa`), `commands/exec_biblioteca.py` (`create_sheet_metal` v2),
`commands/exec_basicos.py` (las copias heredan la ficha), `drawing/sheetset.py` y
`api/routers/drawings.py` (el desplegado sale de la misma ficha), tests en
`tests/test_lista_corte_medida.py`.

Decisiones tomadas en la fase (vetables por número):

- **F1-a. Qué se mide como barra**: sólo las familias `perfiles`, `perfiles_abiertos`,
  `tubos_circulares` y `tubos_estructurales` (`CATEGORIAS_PERFIL`). Rodillos, tambores, guías,
  bisagras, canaletas y lo demás cortable tienen otra forma (un rodillo con su eje daría
  «especial») y siguen por la caja como antes.
- **F1-b. El eje** = la dirección de las aristas rectas que más largo suman, VALIDADA con la
  sección de la ficha (riesgo del plan): si las extensiones perpendiculares no son la sección de
  la ref (± máx(1 mm, 2 %)), la pieza no se mide y cae a lo de antes. Un perfil corto o casi
  cúbico queda así protegido sin adivinar.
- **F1-c. Qué es una cara de corte**: la que no cruza la mitad del largo y comparte una arista con
  el contorno EXTERIOR de un costado. Un taladro, una colisa o una ventana cerrada viven en un
  hueco del costado y no son corte (medido: la colisa en el alma sigue «recto»).
- **F1-d. «Especial»** = cualquier extremo que no sea un plano o dos planos con arista CONVEXA:
  cara curva (boca de pescado), piso paralelo al eje, planos paralelos (escalón), arista cóncava.
  Por eso una riostra `boca_de_pescado` de `create_brace` sale ahora «especial» con el α del
  comando en `aviso`: una boca de pescado no se corta con sierra.
- **F1-e. Lo declarado se contrasta, no manda**: si `miter`/`cut_length` coinciden con lo medido
  (± 0,5° y 1 mm) la fila conserva el orden y los `None` del comando (salida idéntica a la de
  siempre); si no, la fila da lo medido y un `aviso` con lo declarado. El orden de los extremos
  medidos es canónico (no depende de hacia dónde apunte la pieza): dos copias espejadas agrupan.
- **F1-f. La ficha de chapa vive en la pieza** (`Feature.chapa`, datos planos) y no en una
  lectura del log: la lista de corte sólo recibe la escena y las copias de `pattern_*`,
  `duplicate_feature` y `mirror_feature` la heredan (los peldaños son un patrón). Caché de
  geometría: `create_sheet_metal` sube a **v2** (la firma acumulada invalida todo lo que viene
  después en los proyectos con chapa); las copias sólo cambian su huella (para lo que no es chapa
  dejan lo mismo en `RegenState`). Sin bump de `GEOM_CACHE_EPOCH`: un blob viejo sin el campo lee
  `chapa = None` (default de clase) y sólo es falso en proyectos con chapa, que la v2 invalida.
- **F1-g. Las instancias intactas comparten la medida** (`mesh_key` + `matrix`, copias rígidas:
  largo y cortes no cambian al moverlas ni al reflejarlas) dentro de una llamada; aparte, la
  caché por `id(shape)` con referencia + `is`.
- **F1-h. La sección de la ficha se construye a 1 m**: a 100 mm el largo se colaba entre los dos
  lados (el UPN-120 salía 55×**100**). Era otra mentira de la lista, corregida en el mismo paso.
- **F1-i. El BOM no cambia**: compra por ref + `cut_length` (el largo de barra que se pide, ≥ el
  exterior) y su «∠» sigue siendo el declarado. El detalle del corte vive en la lista de corte, el
  CSV y los planos, que leen esta medida (D4). Si se quiere el ∠ medido también en el BOM, es otra
  fase.
- **F1-j. Sin reconocimiento geométrico de chapa ajena**: una chapa plegada hecha con
  `run_script` o `boolean_op` (sin ficha) sigue por la caja. Medir su desarrollo sin radio ni K
  sería una aproximación; queda pendiente.

Medido sobre los `.apolo` reales (sólo lectura, `C:\t\maq`), antes = `main` en `35fbde6`:

| pieza | antes | después |
|---|---|---|
| Zanca (+Y)/(−Y), UPN-120 ×2 | 55×100×854,1, recto | 55×120×**847,5**, ∠27,5°/62,5°, `aviso` (L 854,1, ∠0°/0° declarados) |
| Peldaño superior ×2 (c91 + patrón) | 40×118×600 | **3**×182,1×600, chapa, 2 pliegues |
| Peldaño de arranque (c217) | 72,1×160×600 | **3**×288,2×600, 2 pliegues |
| Chapa de pisada de arranque (c438) | 72,1×83,8×600 | **3**×147,9×600, 1 pliegue |
| Clasificadora: Contenedor de destino inferior ×24 | 255,5×605,6×660 | **1,5**×754,2×854,2, 4 pliegues |

El resto de las filas de la plataforma (29), de la clasificadora (45), del elevador y de la
mezcladora (versiones del 2026-10-27) salen idénticas; las riostras y pasamanos de `create_brace`
de la plataforma dan lo que declaran.

Costo (D5, `time.process_time()`, laptop, una suite corriendo en paralelo): plataforma (236
piezas, 34 perfiles, 4 chapas) 0,16 s la primera lista (antes 0,11 s), 0 la segunda (caché);
clasificadora (480 piezas, 230 perfiles —204 instancias de 8 definiciones—, 24 chapas) 0,72 s la
primera (1,83 s sin compartir las instancias; antes 0,11 s) y 0,05 s la segunda.
