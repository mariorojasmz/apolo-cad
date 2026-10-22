"""Video de cómo se construyó una máquina: texto sobre imagen y codificación (plan
`docs/plans/publicacion-tienda.md`, F3).

Dos módulos, sin estado y sin `Document`:
  - `composicion`: Pillow dibuja portada, rótulo inferior y miniatura (D6); `cierre`, la
    tarjeta final con la portada de la tienda (D10 de fabrica-de-publicaciones). Nada de `drawtext` de ffmpeg: escapes y fuentes distintas por sistema.
  - `codificar`: ffmpeg (binario EXTERNO, nunca una dependencia pip, D7) recibe los
    fotogramas por stdin y, en una segunda pasada, mezcla la música que elige quien publica
    (D8).

Frontera: este paquete recibe imágenes, textos y rutas; no importa `doc`, `state`, `api`,
`kernel` ni `commands` (lo exige `tests/test_capas_media.py`). Quien recorre el documento y
renderiza (F1, F2) le pasa los fotogramas ya hechos.

El `__init__` no importa nada: `codificar` no necesita Pillow y Pillow es un extra.
"""
