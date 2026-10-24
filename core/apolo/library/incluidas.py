"""Piezas que vienen CON una ref de catálogo y no se compran ni se fabrican aparte (plan V8.9 D5,
F2). PURO: lee la escena y el catálogo, nunca un `Document`.

- El VÁSTAGO `{cmd}_vastago` de un `create_pneumatic_cylinder` viene con la ref de su cuerpo
  `{cmd}_cuerpo`: la BOM sale con una fila por cilindro (ref + carrera, `bom_from_scene` lo pone
  en `incluye` del cuerpo) y la lista de corte (y con ella el despiece y las láminas por pieza) no
  lo manda a fabricar. Se lee por la ESCENA (no por el log): un cilindro que llegó con
  `insert_project` lleva ids `{ins}_{cmd}_…` y también cuenta.

Lo que trae el tablero armado (la puerta y la placa del gabinete) depende del documento: lo pasa
`services/tablero.incluidas` como argumento a `bom_from_scene`.
"""

from __future__ import annotations

from .catalog import CATALOG

_CUERPO, _VASTAGO = "_cuerpo", "_vastago"


def es_cilindro(feat) -> bool:
    comp = CATALOG.get(getattr(feat, "component", None) or "")
    return comp is not None and comp.neumatico is not None and comp.neumatico.tipo == "cilindro"


def vastagos_incluidos(scene: dict) -> dict[str, str]:
    """{vástago: cuerpo} de los cilindros de la escena (cuerpo con ref de cilindro + su vástago
    sin ref)."""
    out = {}
    for fid, feat in scene.items():
        if not fid.endswith(_CUERPO) or not es_cilindro(feat):
            continue
        vastago = fid[: -len(_CUERPO)] + _VASTAGO
        if vastago in scene and getattr(scene[vastago], "component", None) is None:
            out[vastago] = fid
    return out
