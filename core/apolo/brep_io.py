"""Viaje de un ``TopoDS_Shape`` a bytes BRep (BinTools) y de vuelta.

Módulo LIVIANO a propósito: sólo build123d y OCP, importados dentro de cada función. Lo
usan la caché de geometría (``doc/geomcache.py``) y el worker del sandbox
(``sandbox_worker.py``), que corre en otro proceso y NO debe cargar ``kernel``, ``doc`` ni
``commands`` (plan sandbox-caliente, D3).
"""

from __future__ import annotations


def serialize_robust(shape) -> bytes | None:
    """Serializa un ``TopoDS_Shape`` a bytes que GARANTIZADO deserializan. BinTools es
    caprichoso por-shape: ``serialize_shape`` siempre da bytes, pero ``deserialize_shape``
    revienta (``BinTools_ShapeSet::ReadGeometry`` / ``NCollection_IndexedMap`` fuera de
    rango) para ciertos shapes — y CUÁLES depende del shape: unos round-trip-ean crudos y
    otros solo tras una copia profunda (``BRepBuilderAPI_Copy`` aplana las refs de
    geometría), pero la copia ROMPE a los primeros. Por eso: intenta crudo, VERIFICA
    deserializando (el fallo salta al LEER, no al escribir); si falla, intenta la copia y
    verifica; si ninguno round-trip-ea, None (quien llama decide el respaldo)."""
    from build123d.persistence import deserialize_shape, serialize_shape

    def _ok(candidate) -> bytes | None:
        blob = serialize_shape(candidate)
        if blob is None:
            return None
        try:
            deserialize_shape(blob)  # el fallo de BinTools ocurre al LEER, no al escribir
        except Exception:
            return None
        return blob

    blob = _ok(shape)
    if blob is not None:
        return blob
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy

    copier = BRepBuilderAPI_Copy(shape)
    copier.Perform(shape)
    return _ok(copier.Shape())


def wrap_topods(topods):
    """Envuelve un ``TopoDS_Shape`` crudo en el tipo de build123d que corresponde a su
    ShapeType (Solid/Compound/…). Todas las ops de Apolo son de ``Shape``, así que la
    subclase PRIMITIVA original (Box/Cylinder) no importa — solo la familia topológica."""
    import build123d as bd
    from OCP.TopAbs import (
        TopAbs_COMPOUND, TopAbs_COMPSOLID, TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL,
        TopAbs_SOLID, TopAbs_VERTEX, TopAbs_WIRE,
    )

    cls = {
        TopAbs_COMPOUND: bd.Compound, TopAbs_COMPSOLID: bd.Compound,
        TopAbs_SOLID: bd.Solid, TopAbs_SHELL: bd.Shell, TopAbs_FACE: bd.Face,
        TopAbs_WIRE: bd.Wire, TopAbs_EDGE: bd.Edge, TopAbs_VERTEX: bd.Vertex,
    }.get(topods.ShapeType(), bd.Shape)
    return cls(topods)
