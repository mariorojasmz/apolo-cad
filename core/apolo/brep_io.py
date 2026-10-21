"""Viaje de un ``TopoDS_Shape`` a bytes BRep (BinTools) y de vuelta.

Módulo LIVIANO a propósito: sólo build123d y OCP, importados dentro de cada función. Lo
usan la caché de geometría (``doc/geomcache.py``) y el worker del sandbox
(``sandbox_worker.py``), que corre en otro proceso y NO debe cargar ``kernel``, ``doc`` ni
``commands`` (plan sandbox-caliente, D3).
"""

from __future__ import annotations


def serialize_robust(shape, *, cache_geometria: bool = False) -> bytes | None:
    """Serializa un ``TopoDS_Shape`` a bytes que GARANTIZADO deserializan. BinTools es
    caprichoso por-shape: ``serialize_shape`` siempre da bytes, pero ``deserialize_shape``
    revienta (``BinTools_ShapeSet::ReadGeometry`` / ``NCollection_IndexedMap`` fuera de
    rango) para ciertos shapes — y CUÁLES depende del shape: unos round-trip-ean crudos y
    otros solo tras una copia profunda (``BRepBuilderAPI_Copy`` aplana las refs de
    geometría), pero la copia ROMPE a los primeros. Por eso: intenta crudo, VERIFICA
    deserializando (el fallo salta al LEER, no al escribir); si falla, intenta la copia y
    verifica; si ninguno round-trip-ea, None (quien llama decide el respaldo).

    ``cache_geometria`` (plan teselado-rapido, F2; lo pide ``doc/geomcache.py``) cambia dos
    cosas:

    - **Sin triangulación.** BinTools guarda por defecto la malla que tenga la forma: tras un
      render, el blob de la piloto 74 pasaba de 7,8 a 19,8 MB (y ``pack`` de 1,2 a 2,2 s bajo
      ``STATE_LOCK``) para ahorrar ~1 s de teselado. La malla de render NO va a la caché (D3,
      descartado en la F2). Sin malla, los bytes son los mismos que antes.
    - **VERSION_3 de último recurso.** La fusión de copias COLOCADAS que comparten TShape (las
      cadenas de ``cadena_por_rodillos``: rodillos y placas son una plantilla repetida con
      ``Pos``/``Rotation``) sale de las versiones 1, 2 y 4 (la actual) de BinTools con un índice
      de curva que el lector no tiene (``FindKey`` fuera de rango en ``ReadGeometry``), cruda y
      copiada; la VERSION_3 la escribe y la lee bien (medido en 799 piezas de 6 proyectos, con
      las mismas caras en el mismo orden). Va al final para no cambiar un byte de lo que ya
      funcionaba; ``deserialize_shape`` lee la versión de la cabecera.

    El sandbox no lo pide: su respaldo es STEP y cambiarlo cambiaría lo que entrega
    ``run_script``."""
    from build123d.persistence import deserialize_shape
    from OCP.BinTools import BinTools_FormatVersion as _FV

    mallas = not cache_geometria

    def _ok(blob) -> bytes | None:
        if blob is None:
            return None
        try:
            deserialize_shape(blob)  # el fallo de BinTools ocurre al LEER, no al escribir
        except Exception:
            return None
        return blob

    blob = _ok(_escribir(shape, mallas, _FV.BinTools_FormatVersion_CURRENT))
    if blob is not None:
        return blob
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy

    copier = BRepBuilderAPI_Copy(shape)
    copier.Perform(shape)
    blob = _ok(_escribir(copier.Shape(), mallas, _FV.BinTools_FormatVersion_CURRENT))
    if blob is not None or not cache_geometria:
        return blob
    return _ok(_escribir(shape, mallas, _FV.BinTools_FormatVersion_VERSION_3))


def _escribir(shape, mallas: bool, version) -> bytes | None:
    """BinTools de ``shape`` (con su triangulación si ``mallas``; sin normales). Con
    ``mallas`` y la versión actual son los bytes de ``build123d.persistence.serialize_shape``
    (que tampoco atrapa un fallo al escribir)."""
    import io

    from OCP.BinTools import BinTools

    if shape is None:
        return None
    bio = io.BytesIO()
    BinTools.Write_s(shape, bio, mallas, False, version)
    return bio.getvalue()


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
