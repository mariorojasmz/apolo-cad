"""Material y color POR COMANDO (D9 de puerta-fuera-de-catalogo): la raíz de un patrón es
ciudadana.

`Document.materials`/`colors` guardan el metadato POR PIEZA (`{fid: valor}`). Las copias de un
patrón nacen y mueren con su variable (`{raíz}_{n}`), así que el material puesto a mano a cada
copia no sigue a N: al subirla, las nuevas nacían sin él. `materiales_por_comando` y
`colores_por_comando` (`{command_id: valor}`) guardan el de la RAÍZ y lo hereda toda pieza que
ese comando crea, también la que nace al subir la variable.

Precedencia (de más a menos): el de la pieza (una copia con material propio lo conserva) → el de
su comando → el que puso el executor (`insert_project` importa los del origen). Se escribe por
comando sólo cuando el id NO es una pieza de la escena y sí es el comando de alguna (la raíz de
un patrón, de un `pattern_group`…); un id de pieza sigue siendo por pieza, como siempre.

Manifest: `materiales_por_comando` y `colores_por_comando`, presentes sólo si hay datos. Un
`.apolo` viejo no los trae: dicts vacíos y todo se comporta como antes (byte-idéntico al
guardar). Metadato de manifest, fuera del log y de los checkpoints (raíz § «Metadato ≠ comando»).
"""

from __future__ import annotations


def piezas_del_comando(scene: dict, cmd_id: str) -> list[str]:
    """Las piezas que creó el comando `cmd_id` si NO es él mismo una pieza ([] si lo es, o si
    no creó ninguna): a quién se aplica un metadato por comando."""
    if cmd_id in scene:
        return []
    return [fid for fid, f in scene.items() if getattr(f, "command_id", None) == cmd_id]


def de_la_pieza(fid: str, command_id: str | None, por_pieza: dict, por_comando: dict):
    """El valor que rige a la pieza (`None` si ni ella ni su comando tienen uno)."""
    v = por_pieza.get(fid)
    if v is None and command_id is not None:
        v = por_comando.get(command_id)
    return v


def colores_efectivos(doc) -> dict[str, str]:
    """{fid: color} asignado a cada pieza: el suyo o el de su comando. Lo que leen el visor, la
    foto y los planos en vez de `doc.colors` (sin colores por comando, es `doc.colors`)."""
    por_comando = getattr(doc, "colores_por_comando", None) or {}
    colores = getattr(doc, "colors", None) or {}
    if not por_comando:
        return colores
    out = dict(colores)
    for fid, f in doc.scene.items():
        if fid not in out and f.command_id in por_comando:
            out[fid] = por_comando[f.command_id]
    return out


def al_manifest(doc) -> dict:
    """Las claves del manifest, sólo si hay datos (sin ellas, el manifest de siempre)."""
    out = {}
    if getattr(doc, "materiales_por_comando", None):
        out["materiales_por_comando"] = doc.materiales_por_comando
    if getattr(doc, "colores_por_comando", None):
        out["colores_por_comando"] = doc.colores_por_comando
    return out


def de_manifest(doc, manifest: dict) -> None:
    doc.materiales_por_comando = dict(manifest.get("materiales_por_comando") or {})
    doc.colores_por_comando = dict(manifest.get("colores_por_comando") or {})


def para_firma(doc) -> dict:
    """Lo que suma a una firma (puerta, marcha, escenarios): el material por comando decide la
    masa y el material; sin él, nada (la firma de siempre). El color no cuenta."""
    m = getattr(doc, "materiales_por_comando", None)
    return {"materiales_por_comando": m} if m else {}
