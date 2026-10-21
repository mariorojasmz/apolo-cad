"""Apariencia de las piezas de un documento: la tabla de acabados D5 de
[visor-realista](../../../docs/plans/visor-realista.md) aplicada a SU escena.

La usan todos los que pintan el documento —el payload de escena del visor, la foto de
`render_view`, los GIF de movimiento y de dinámica y el video de la tienda— para que se vean
igual. La tabla y las reglas viven en `library/apariencia.py`; aquí sólo se leen del `doc` los
colores asignados y el material por defecto de su vertical.
"""

from __future__ import annotations

from apolo.library.apariencia import PALETTE, apariencias_de_zonas, apariencias_escena


def apariencias_documento(doc) -> dict:
    """{fid: {acabado, color, metalness, roughness, opacidad}} de cada pieza de `doc.scene`
    (el llamador sostiene `STATE_LOCK` si el documento es el de la API)."""
    return apariencias_escena(doc.scene, getattr(doc, "colors", None) or {},
                              default_material=doc.default_material())


def zonas_documento(doc) -> dict[str, dict[str, dict]]:
    """{fid: {zona: apariencia}} de las piezas cuyo componente de catálogo declara zonas de
    acabado (plan seta-de-emergencia, D3: una zona `fijo` no toma el color asignado). Las demás
    piezas no aparecen. No dice si la forma de la pieza conserva sus zonas (una taladrada las
    pierde): eso lo decide quien tesela, con `library.zonas.zona_por_cara`."""
    from apolo.library.catalog import CATALOG

    colores = getattr(doc, "colors", None) or {}
    out: dict[str, dict[str, dict]] = {}
    for i, feat in enumerate(doc.scene.values()):
        comp = CATALOG.get(feat.component) if getattr(feat, "component", None) else None
        if comp is None or not getattr(comp, "zonas", None):
            continue
        out[feat.id] = apariencias_de_zonas(comp.zonas, colores.get(feat.id),
                                            PALETTE[i % len(PALETTE)])
    return out


def apariencias_render(doc) -> dict:
    """`apariencias_documento` más, en cada pieza que conserva sus zonas de acabado, la clave
    `zonas` = {"por_cara": (zona de cada cara, en el orden de `faces()`), "aps": {zona:
    apariencia}}: lo que leen la foto VTK (`kernel/render_vtk`) y el GLB de la tienda para
    partirla por zona (plan seta-de-emergencia, F3). El kernel la recibe como DATO: no importa
    `library`. Una pieza sin zonas, o taladrada (no calza con la huella), va igual que en
    `apariencias_documento`."""
    from apolo.library.zonas import zona_por_cara

    aps = apariencias_documento(doc)
    for fid, por_zona in zonas_documento(doc).items():
        feat = doc.scene[fid]
        por_cara = zona_por_cara(feat.component, feat.shape) if feat.shape is not None else None
        if por_cara is not None:
            aps[fid] = {**aps[fid], "zonas": {"por_cara": por_cara, "aps": por_zona}}
    return aps
