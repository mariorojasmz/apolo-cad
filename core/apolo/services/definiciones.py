"""Las definiciones que instancian las piezas de una escena (plan teselado-rapido, D1).

Una pieza con `mesh_key` y `matrix` es una instancia: su geometría canónica vive en
`commands.registry.DEFINITIONS[mesh_key]` y la matriz la coloca en el mundo. El render
(`kernel/render_vtk`, `kernel/render_vivo`, el manual de `drawing/manual_fotos`) tesela UNA vez
la definición y la transforma por instancia, como ya hace el visor; el kernel no importa
`commands`, así que recibe estas definiciones como DATO.

Devuelve una FOTO (un dict propio, no la LRU): si `DEFINITIONS` desaloja una entrada mientras
se tesela, el render no la pierde. Una clave desalojada antes de la foto falta y esa pieza se
tesela sola (lo que hacía siempre). Sin locks: el llamador sostiene `STATE_LOCK`.
"""

from __future__ import annotations


def definiciones_de(escena: dict) -> dict:
    """{mesh_key: shape de la definición} de las instancias de `escena` (id → Feature)."""
    from apolo.commands.registry import DEFINITIONS

    claves = {f.mesh_key for f in escena.values()
              if getattr(f, "mesh_key", None) and getattr(f, "matrix", None)}
    return {k: DEFINITIONS[k] for k in claves if k in DEFINITIONS}
