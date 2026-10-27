"""Zonas de acabado de UNA pieza (plan seta-de-emergencia, D1): la unión de partes etiquetadas
y de qué zona viene cada cara.

Un builder de catálogo puede devolver sus partes como `{zona: forma}` (la seta roja, el anillo
amarillo, el collar…). La pieza sigue siendo UN sólido —la unión—, y cada cara de ese sólido
sabe de qué parte salió por la HISTORIA de la fusión (`BRepAlgoAPI_Fuse.Modified/IsDeleted`),
no por geometría adivinada.

La etiqueta es la zona de cada cara por su ÍNDICE en el orden de `faces()`: es el orden en que
`Shape.tessellate` concatena los triángulos, lo conserva una ubicación (`place`) y también la
caché de geometría (BinTools), que en cambio pierde la identidad del TShape (medido en la F0).

OCCT puro: no conoce el catálogo ni `Document`.
"""

from __future__ import annotations


def fusionar_zonas(partes: dict) -> tuple[object, tuple[str, ...]]:
    """Une las `partes` ({zona: forma}, en orden de PRIORIDAD) en un sólido y devuelve
    `(sólido, zona_por_cara)`: la zona de cada cara del sólido, en el orden de `faces()`.

    Una zona puede dar una LISTA de formas (los tornillos de una bornera, plan
    aparatos-de-tablero-realistas D5): todas entran a la MISMA fusión, una sola operación de
    OCCT en vez de una por forma; dentro de la zona, la prioridad es el orden de la lista.

    Si una cara del resultado sale de dos partes (caras coincidentes), gana la zona declarada
    antes. Lanza ValueError si no queda UN sólido (partes disjuntas o tangentes: deben solapar,
    regla de los builders) o si alguna cara queda sin zona."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopTools import TopTools_ListOfShape

    from apolo.brep_io import wrap_topods

    if not partes:
        raise ValueError("Una pieza con zonas necesita al menos una parte")
    # (zona, forma OCCT) en orden de prioridad: la zona con lista aporta cada una de sus formas
    pares = [(z, getattr(f, "wrapped", f)) for z, v in partes.items()
             for f in (v if isinstance(v, (list, tuple)) else (v,))]
    if not pares:
        raise ValueError("Una pieza con zonas necesita al menos una forma")
    if len(pares) == 1:
        solido = wrap_topods(pares[0][1])
        return solido, tuple(pares[0][0] for _ in solido.faces())

    argumentos, herramientas = TopTools_ListOfShape(), TopTools_ListOfShape()
    argumentos.Append(pares[0][1])
    for _, forma in pares[1:]:
        herramientas.Append(forma)
    fusion = BRepAlgoAPI_Fuse()
    fusion.SetArguments(argumentos)
    fusion.SetTools(herramientas)
    fusion.Build()
    if not fusion.IsDone():
        raise ValueError("OCCT no pudo unir las zonas de la pieza")
    unido = wrap_topods(fusion.Shape())
    solidos = unido.solids()
    if len(solidos) != 1:
        raise ValueError(f"Las zonas de la pieza dan {len(solidos)} sólidos: deben solapar "
                         f"(0.5–8 mm) para unirse en uno")
    solido = solidos[0]

    # imagen de cada cara de cada parte en el resultado, por TShape (sin ubicación) + IsPartner
    imagenes: dict[int, list] = {}
    for z, forma in pares:
        for cara in wrap_topods(forma).faces():
            if fusion.IsDeleted(cara.wrapped):
                continue
            for imagen in (list(fusion.Modified(cara.wrapped)) or [cara.wrapped]):
                clave = hash(imagen.Located(TopLoc_Location()))
                imagenes.setdefault(clave, []).append((imagen, z))

    por_cara = []
    for cara in solido.faces():
        clave = hash(cara.wrapped.Located(TopLoc_Location()))
        zona = next((z for imagen, z in imagenes.get(clave, ()) if imagen.IsPartner(cara.wrapped)),
                    None)
        if zona is None:
            raise ValueError("Una cara de la pieza quedó sin zona tras la unión")
        por_cara.append(zona)
    return solido, tuple(por_cara)
