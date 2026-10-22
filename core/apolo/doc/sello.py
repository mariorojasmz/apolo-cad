"""Sello de ENTRADA: lo que un comando NUEVO recibe del documento al anotarse en el log.

Un campo nuevo de un comando entra con un default que reproduce los logs viejos (raíz § Log de
comandos); cuando lo de HOY debe ser otro valor, el sello se lo pone al comando que nace
(`CommandSpec.al_crear`), nunca al replay ni a un edit. Así un log viejo regenera igual y con
su misma firma, y lo nuevo queda escrito en sus params (la caché lo ve).

También es el único puente EXPLÍCITO de un metadato a la geometría que no es un `set_variable`:
el material que `set_material` o el vertical dan HOY a una pieza queda copiado en los params
del comando que lo usa (`join_bolted`: plan union-en-perfil-hueco, D4). Cambiar el material
después no cambia esa unión: hay que volver a crearla.
"""

from __future__ import annotations

from apolo.commands.registry import REGISTRY


def material_de(doc, fid: str) -> str:
    """Material que el documento da hoy a la pieza `fid`: override → catálogo → nombre (con la
    guarda del vertical). Una pieza que aún no existe (creada en el mismo lote) toma el default
    del vertical."""
    from apolo.library.catalog import CATALOG
    from apolo.library.materials import resolve_material_vertical

    feat = doc.scene.get(fid)
    if feat is None:
        return doc.default_material()
    return resolve_material_vertical(feat, CATALOG, doc.default_material())


def sellar(doc, cmd_type: str, params: dict) -> dict:
    """Los params con el sello de su comando (los mismos si no tiene)."""
    spec = REGISTRY.get(cmd_type)
    if spec is None or spec.al_crear is None:
        return params
    return spec.al_crear(dict(params), lambda fid: material_de(doc, fid))
