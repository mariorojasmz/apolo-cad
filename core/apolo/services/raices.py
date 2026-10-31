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
- `piezas_nombradas`: las piezas que nombra una lista de tokens de un metadato (id de pieza, grupo
  o command_id: todas las piezas que creó), la regla del requisito `carga_sobre`.
- `fuentes_de_copias` + `raiz_de`: de cada COPIA de un patrón o espejo, la pieza que copia (y,
  encadenando, la raíz): lo que se declara de la fuente vale para sus copias.
"""

from __future__ import annotations

import re

from apolo.commands.errors import CommandError
from apolo.commands.exec_uniones import es_conjunto, instancias_de_raiz, piezas_de
from apolo.doc.por_comando import piezas_del_comando

__all__ = ["es_raiz_o_conjunto", "fuentes_de_copias", "justificadas_efectivas", "piezas_de",
           "piezas_del_comando", "piezas_nombradas", "raiz_de"]

#: Los comandos que COPIAN piezas y el param que nombra lo copiado (una pieza; en
#: `pattern_group`, el comando cuyas piezas repite: `{cmd}_{i}_{k}_{sufijo}`).
_COPIAN = {"pattern_linear": "feature", "pattern_circular": "feature",
           "mirror_feature": "feature", "pattern_group": "source"}


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


def piezas_nombradas(scene: dict, grupos: dict, tokens) -> set[str]:
    """Las piezas de `scene` que nombran `tokens`: un id de pieza, un grupo (sus piezas) o un
    command_id (todas las piezas que creó, también las copias de un patrón). Lo que no resuelve
    no suma."""
    from apolo.assembly.groups import group_features, resolve_group

    out: set = set()
    for t in tokens or ():
        t = str(t)
        if t in scene:
            out.add(t)
            continue
        g = resolve_group(grupos, t)
        if g is not None:
            out |= set(group_features(scene, grupos, g))
            continue
        out |= {fid for fid, f in scene.items() if f.command_id == t}
    return out


def fuentes_de_copias(doc) -> dict[str, str]:
    """{copia: la pieza que copia} de los patrones (`pattern_linear`/`_circular`/`_group`) y
    espejos del log. Encadenado (el patrón de un patrón), `raiz_de` llega a la pieza original."""
    por_cmd: dict = {}
    for fid, f in doc.scene.items():
        por_cmd.setdefault(getattr(f, "command_id", None), []).append(fid)
    out: dict[str, str] = {}
    for c in doc.commands:
        clave = _COPIAN.get(c.get("type"))
        fuente = str((c.get("params") or {}).get(clave) or "") if clave else ""
        if not fuente:
            continue
        cid = c["id"]
        if c["type"] != "pattern_group":
            out.update({fid: fuente for fid in por_cmd.get(cid, ()) if fid != fuente})
            continue
        for src in por_cmd.get(fuente, ()):
            suf = src[len(fuente) + 1:] if src.startswith(fuente + "_") else src
            pat = re.compile(rf"{re.escape(cid)}_\d+_\d+_{re.escape(suf)}")
            out.update({fid: src for fid in por_cmd.get(cid, ()) if pat.fullmatch(fid)})
    return out


def raiz_de(fid: str, fuentes: dict[str, str]) -> str:
    """La pieza ORIGINAL de `fid` (ella misma si no es copia) siguiendo `fuentes_de_copias`."""
    vistos = {fid}
    while fid in fuentes and fuentes[fid] not in vistos:
        fid = fuentes[fid]
        vistos.add(fid)
    return fid
