"""Zonas de acabado en el GLB de la tienda (plan seta-de-emergencia, F3 · D2).

Una pieza con zonas (la seta roja sobre el anillo amarillo) sale en el MISMO nodo con una
primitiva glTF por zona, cada una con su material. Cómo (medido en la F0 y la F3 del plan):

- El escritor de OCCT con `SetMergeFaces` junta en una primitiva las caras SEGUIDAS con el mismo
  estilo. Las caras de una zona no son seguidas en `faces()` (la seta las intercala), así que el
  prototipo de una pieza con zonas no es una copia del sólido sino un COMPUESTO con un
  sub-compuesto de caras por zona: cada zona queda contigua y da una sola primitiva.
- El estilo (color + material PBR) va en cada sub-compuesto, como sub-forma del PROTOTIPO
  (`AddSubShape`). El estilo del prototipo pisa el de la instancia (docstring de `glb.py`): por
  eso la instancia de una pieza con zonas no lleva color, y dos piezas con la misma forma pero
  otras apariencias de zona (una caja repintada) tienen cada una su prototipo.
- La zona de cada cara llega como dato (`PiezaGlb.zona_por_cara`, por índice en el orden de
  `faces()` de build123d, el de `library/zonas.py`). Si no corresponde a las caras de la forma,
  la pieza sale de un solo color, como hoy.
"""

from __future__ import annotations


def caras(forma) -> list:
    """Las caras de un TopoDS_Shape en el orden de `faces()` de build123d 0.10
    (`_topods_entities`: el explorador, sin repetir la misma cara)."""
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer

    vistas: dict = {}
    exp = TopExp_Explorer(forma, TopAbs_FACE)
    while exp.More():
        cara = exp.Current()
        vistas[hash(cara)] = cara
        exp.Next()
    return list(vistas.values())


def zonas_de(pieza, base) -> tuple | None:
    """Las `ZonaGlb` de la pieza en el orden en que aparecen en sus caras (sólo las que tienen
    alguna cara), o None si la pieza va de un solo color: sin zonas, una zona sin estilo o una
    `zona_por_cara` que no corresponde a las caras de `base`."""
    por_cara = getattr(pieza, "zona_por_cara", None)
    if not por_cara or not pieza.zonas:
        return None
    estilos = {z.nombre: z for z in pieza.zonas}
    if len(caras(base)) != len(por_cara) or any(n not in estilos for n in por_cara):
        return None
    return tuple(estilos[n] for n in dict.fromkeys(por_cara))


def compuesto_por_zona(base, zona_por_cara, zonas) -> object:
    """Compuesto de `base` con un sub-compuesto de caras por zona, en el orden de `zonas`."""
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    constructor = BRep_Builder()
    raiz = TopoDS_Compound()
    constructor.MakeCompound(raiz)
    lista = caras(base)
    for zona in zonas:
        sub = TopoDS_Compound()
        constructor.MakeCompound(sub)
        for cara, nombre in zip(lista, zona_por_cara):
            if nombre == zona.nombre:
                constructor.Add(sub, cara)
        constructor.Add(raiz, sub)
    return raiz


def estilar(st, ct, etiqueta, copia, zonas, poner_material) -> None:
    """Pone el color y el material de cada zona en su sub-compuesto del prototipo `etiqueta`.
    `poner_material(sub_etiqueta, zona)` asigna el material PBR (el de `glb._material`)."""
    from OCP.TopoDS import TopoDS_Iterator
    from OCP.XCAFDoc import XCAFDoc_ColorType

    from .glb import _color

    it = TopoDS_Iterator(copia)
    for zona in zonas:
        sub = st.AddSubShape(etiqueta, it.Value())
        ct.SetColor(sub, _color(zona.color), XCAFDoc_ColorType.XCAFDoc_ColorSurf)
        poner_material(sub, zona)
        it.Next()
