"""Filas de BOM que la ESCENA no tiene y el documento sí: las del tablero eléctrico (V8.1 D10,
`electrico.filas_bom`) y la tornillería de las uniones `perno` DECLARADAS sin pieza modelada (F6
de la puerta de publicación, `library/tornilleria_declarada.py`). La BOM, su CSV y el costeo
(cotización) las suman al final de `bom_from_scene`. El llamador sostiene `STATE_LOCK`.
"""

from __future__ import annotations


def filas_extra(doc) -> list[dict]:
    """Tablero + tornillería declarada sin modelar (vacía si no hay ninguna)."""
    from apolo.library.tornilleria_declarada import filas_declaradas

    from .electrico import filas_bom

    return filas_bom(doc) + filas_declaradas(doc.scene, doc.fasteners)
