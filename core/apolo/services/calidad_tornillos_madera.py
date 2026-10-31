"""Los tornillos de MADERA sin hexágono, para medir sus distancias en la madera (plan
hallazgos-del-revisor-en-la-puerta, D7 y F4). El llamador sostiene STATE_LOCK.

`calidad_pernos` no los mide: sin cabeza hexagonal ni cilíndrica no reconoce su eje, y la F0
dejó 128 sin medir (la estantería entera va con ellos). Aquí entran:

- la ref de catálogo `tornilleria_madera` sin `llave` (el tornillo avellanado, `wood_screw`);
- un sólido a medida cuyo ROL es de tornillo de madera (`ejes_giro.es_tirafondo`: «Tirafondo…»,
  «Tornillo para madera…», DIN 571/96/7997) que `calidad_pernos` no midió (desde la D3 de
  puerta-fuera-de-catalogo, `calidad_pernos` los mide como `madera` con esta misma geometría:
  aquí queda el que no reconoció).

Su eje es el de su cilindro más largo (el vástago) y la CABEZA, el extremo más ancho (la cabeza
avellanada; la punta es un cono que cierra en el eje): `t` = 0 en la cara alta de la cabeza. Lo
que el eje cruza se mide con los rayos de `calidad_pernos` (`insumo_perno` con esa geometría).
Sólo los usa la distancia en madera (`calidad_bordes`): ni el agarre ni el paso los juzgan, y un
tornillo sin cabeza reconocible se cuenta, nunca bloquea.
"""

from __future__ import annotations


def es_tornillo_de_madera(feat, catalog) -> bool:
    """¿Tornillo de madera sin llave (catálogo) o tornillo de madera a medida por su rol?"""
    from apolo.library.ejes_giro import es_tirafondo

    comp = catalog.get(getattr(feat, "component", None) or "")
    if comp is not None:
        return comp.category == "tornilleria_madera" and not (comp.specs or {}).get("llave")
    return es_tirafondo(getattr(feat, "name", "") or "")


def geometria_avellanado(solid) -> dict | None:
    """{asiento, dir (hacia la punta), cabeza, d, s, largo, tuercas: []} del tornillo de
    cabeza avellanada (formato de `calidad_pernos.geometria_perno`) o None. La cabeza la lee
    `library/cabeza_revolucion.py` (también el acceso por impronta)."""
    from apolo.library.cabeza_revolucion import cabeza_de_revolucion

    c = cabeza_de_revolucion(solid)
    if c is None:
        return None  # sin un extremo más ancho que el vástago: no se sabe dónde está la cabeza
    a = c["afuera"]
    return {"asiento": c["tope"], "dir": (-a[0], -a[1], -a[2]), "cabeza": "avellanada",
            "d": c["d"], "s": c["s"], "largo": c["largo"], "tuercas": []}


def cabeza_conica(solid, g: dict) -> bool:
    """¿La cabeza de `g` (`geometria_avellanado`) es AVELLANADA? (`cabeza_revolucion.es_avellanada`)"""
    from apolo.library.cabeza_revolucion import es_avellanada

    d = g["dir"]
    return es_avellanada(solid, {"tope": g["asiento"], "afuera": (-d[0], -d[1], -d[2]), "d": g["d"]})


def insumos_tornillos_madera(doc, esc, medidos: set[str]) -> tuple[list[dict], int]:
    """(insumos con el formato de `calidad_pernos` y `madera_screw`, cuántos no se reconocen)
    de los tornillos de madera que `calidad_pernos` no midió (`medidos` = sus fids evaluables)."""
    from apolo.library.catalog import CATALOG

    from .calidad_pernos import insumo_perno

    out, sin_geometria = [], 0
    for fid, feat, solid, _mn, _mx, _r in list(esc.solidos):
        if fid in medidos or getattr(feat, "is_guide", False):
            continue
        if not es_tornillo_de_madera(feat, CATALOG):
            continue
        try:
            g = geometria_avellanado(solid)
        except Exception:  # noqa: BLE001 — geometría rara: se cuenta, nunca rompe la puerta
            g = None
        if g is None:
            sin_geometria += 1
            continue
        out.append(insumo_perno(esc, fid, feat, solid, "madera", [], CATALOG, geometria=g))
    return out, sin_geometria
