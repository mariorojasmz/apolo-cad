"""Lo que se compra CON otra pieza y no sale en fila propia de la BOM de compra (`bom_from_scene`
y `scene_costing`, argumento `incluidas`): {id de la pieza: id de la pieza que la trae}. Una
fuente para todo consumidor de la BOM de compra (el llamador sostiene `STATE_LOCK`):

- el tablero armado (`tablero.incluidas`, V8.5 F2): la puerta y, si la ficha lo dice, la placa;
- el cilindro neumático (V8.9 D5): el VÁSTAGO `{cmd}_vastago` de cada `create_pneumatic_cylinder`
  viene con la ref de su cuerpo `{cmd}_cuerpo` (una fila por cilindro, ref + carrera), como lo
  que dibuja `layout_tablero`. Se lee por la ESCENA (no por el log): un cilindro que llegó con
  `insert_project` lleva ids `{ins}_{cmd}_…` y también cuenta.
"""

from __future__ import annotations

_CUERPO, _VASTAGO = "_cuerpo", "_vastago"


def cilindros(doc) -> dict[str, str]:
    """{vástago: cuerpo} de los cilindros de la escena (cuerpo con ref de cilindro + su vástago)."""
    from apolo.library.catalog import CATALOG

    out = {}
    for fid, feat in doc.scene.items():
        if not fid.endswith(_CUERPO):
            continue
        comp = CATALOG.get(getattr(feat, "component", None) or "")
        if comp is None or comp.neumatico is None or comp.neumatico.tipo != "cilindro":
            continue
        vastago = fid[: -len(_CUERPO)] + _VASTAGO
        if vastago in doc.scene and getattr(doc.scene[vastago], "component", None) is None:
            out[vastago] = fid
    return out


def incluidas(doc) -> dict[str, str]:
    from .tablero import incluidas as del_tablero

    return {**del_tablero(doc), **cilindros(doc)}
