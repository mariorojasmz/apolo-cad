"""La raíz de un patrón es ciudadana (D9 de puerta-fuera-de-catalogo): lo que el documento
nombra por la RAÍZ de un patrón (o un conjunto) se aplica a todas sus copias, también a las que
nacen al subir la variable.

- `piezas_de`: la regla de `fasten` (`commands/exec_uniones.py`): un id de pieza → None; la raíz
  de un patrón → sus copias `{raíz}_{n}` (sin la fuente); un conjunto (`c11+c57`,
  `(c15+c61)[::2]`) → sus piezas. `CommandError` con la corrección si el texto no resuelve.
- `justificadas_efectivas`: el metadato `justificadas` con cada entrada cuya `pieza` es una raíz
  o un conjunto expandida a una por pieza (misma regla y mismo porqué). El metadato GUARDA la
  raíz (así sigue a la variable); la puerta lee las piezas. Una entrada que no resuelve queda tal
  cual (la evidencia no la casa con nada, como hoy).
- `piezas_del_comando`: a quién toca el material o el color puesto a una raíz
  (`doc/por_comando.py`), re-exportado para la API.
"""

from __future__ import annotations

from apolo.commands.errors import CommandError
from apolo.commands.exec_uniones import es_conjunto, instancias_de_raiz, piezas_de
from apolo.doc.por_comando import piezas_del_comando

__all__ = ["es_raiz_o_conjunto", "justificadas_efectivas", "piezas_de", "piezas_del_comando"]


def es_raiz_o_conjunto(scene: dict, texto: str) -> bool:
    """¿`texto` nombra, en la escena de hoy, la raíz de un patrón con copias o un conjunto que
    resuelve? (False para un id de pieza o algo que no existe.)"""
    if texto in scene:
        return False
    if es_conjunto(texto):
        try:
            return bool(piezas_de(scene, texto))
        except CommandError:
            return False
    return bool(instancias_de_raiz(scene, texto))


def justificadas_efectivas(doc) -> list[dict]:
    """`doc.justificadas` con las raíces y conjuntos expandidos a una entrada por pieza."""
    out: list[dict] = []
    for j in getattr(doc, "justificadas", None) or []:
        pieza = j.get("pieza")
        if not pieza or not es_raiz_o_conjunto(doc.scene, pieza):
            out.append(j)
            continue
        out.extend({**j, "pieza": fid} for fid in piezas_de(doc.scene, pieza) or ())
    return out
