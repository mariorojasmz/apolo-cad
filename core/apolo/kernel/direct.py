"""Modelado directo sobre B-rep (V5.3): editar geometría SIN historia.

Un STEP de fabricante importado (o cualquier sólido nativo) se edita por sus CARAS:
- ``remove_faces``: borrar caras con CURACIÓN (OCCT Defeaturing extiende las caras
  vecinas para cerrar el hueco) — quitar fillets, barrenos o bosses del proveedor.
- ``push_pull``: empujar/jalar una cara PLANA extruyendo su propio contorno
  (prisma+booleana: el prisma comparte exactamente el borde de la cara, así la
  booleana es robusta). Semántica honesta: las paredes nuevas salen RECTAS — no
  extiende caras inclinadas vecinas como el push-pull completo de SW.
- ``expand_tangent``: expandir una selección de caras a su cadena TANGENTE (un
  fillet de fabricante suele ser varias caras encadenadas).

Wrappers OCCT puros (no conocen Scene ni Document — misma frontera que topology.py).
NO existe offset paramétrico de cara cilíndrica: ``BRepOffset_MakeOffset.
SetOffsetOnFace`` falla o devuelve sólido vacío en OCP 7.8.1 (spike 2026-07-03) —
para redimensionar un barreno: remove_faces + drill_hole nuevo.

Gotcha del Defeaturing: cuando una cara NO se puede quitar (las vecinas no cierran),
OCCT NO falla — devuelve el sólido INTACTO. Se detecta comparando nº de caras y
volumen (no-op ⇒ DirectError).
"""

from __future__ import annotations

import math


class DirectError(Exception):
    pass


def _wrap(topods):
    """TopoDS_Shape crudo (resultado OCCT) → shape de build123d."""
    from build123d import Compound, Solid
    from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_SOLID

    st = topods.ShapeType()
    if st == TopAbs_SOLID:
        return Solid(topods)
    if st == TopAbs_COMPOUND:
        return Compound(topods)
    raise DirectError("El resultado de la operación no es un sólido")


def _is_valid(shape) -> bool:
    from OCP.BRepCheck import BRepCheck_Analyzer

    return BRepCheck_Analyzer(shape.wrapped).IsValid()


def remove_faces(shape, faces: list):
    """Quita `faces` del sólido y CURA el hueco extendiendo las caras vecinas."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Defeaturing
    from OCP.TopTools import TopTools_ListOfShape

    if not faces:
        raise DirectError("No hay caras que quitar")
    lst = TopTools_ListOfShape()
    for f in faces:
        lst.Append(f.wrapped)
    d = BRepAlgoAPI_Defeaturing()
    d.SetShape(shape.wrapped)
    d.AddFacesToRemove(lst)
    d.Build()
    if not d.IsDone():
        raise DirectError(
            "OCCT no pudo curar el hueco: las caras vecinas no cierran. Selecciona el "
            "feature COMPLETO (un barreno = cilindro+cono; un fillet = cadena de caras) "
            "o menos caras a la vez"
        )
    result = _wrap(d.Shape())
    if not hasattr(result, "volume") or result.volume <= 0 or not _is_valid(result):
        raise DirectError("La curación produjo un sólido inválido: selecciona otras caras")
    # no-op silencioso de OCCT: cara imposible de quitar → devuelve el sólido intacto
    if len(result.faces()) == len(shape.faces()) and abs(result.volume - shape.volume) < 1e-9:
        raise DirectError(
            "Las caras no se pudieron quitar (las vecinas no pueden cerrar el hueco): "
            "una cara estructural del sólido no es 'defeatureable' — para recortar "
            "material usa push_face o boolean_op"
        )
    return result


def _outward_normal(shape, face):
    """Normal EXTERIOR verificada con el clasificador de sólido — nunca `normal_at`
    a ciegas: las caras de un STEP pueden venir con orientación REVERSED."""
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.TopAbs import TopAbs_OUT
    from OCP.gp import gp_Pnt

    n = face.normal_at(face.center())
    c = face.center()
    eps = 0.01
    probe = gp_Pnt(c.X + n.X * eps, c.Y + n.Y * eps, c.Z + n.Z * eps)
    cls = BRepClass3d_SolidClassifier(shape.wrapped, probe, 1e-7)
    return n if cls.State() == TopAbs_OUT else -n


def push_pull(shape, face, distance: float):
    """Empuja (distance<0, quita material) o jala (>0, añade) una cara PLANA
    extruyendo su contorno a lo largo de la normal exterior."""
    from build123d import GeomType, extrude

    if face.geom_type != GeomType.PLANE:
        raise DirectError(
            "push_face solo acepta caras PLANAS; para redimensionar un barreno usa "
            "delete_faces + drill_hole nuevo"
        )
    if abs(distance) < 1e-9:
        raise DirectError("La distancia no puede ser cero")
    n = _outward_normal(shape, face)
    prism = extrude(face, amount=abs(distance), dir=n if distance > 0 else -n)
    result = (shape + prism) if distance > 0 else (shape - prism)
    if result is None or not hasattr(result, "volume") or result.volume <= 0:
        raise DirectError("La operación eliminó todo el material: usa una distancia menor")
    if abs(result.volume - shape.volume) < 1e-9:
        raise DirectError("La operación no cambió el sólido: revisa la cara y la distancia")
    if not _is_valid(result):
        raise DirectError("El resultado no es un sólido válido: prueba una distancia menor")
    return result


def _curved_radius(face):
    """Radio característico de una cara curva (cilindro/esfera/toro-menor) o None."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Sphere, GeomAbs_Torus

    surf = BRepAdaptor_Surface(face.wrapped)
    t = surf.GetType()
    if t == GeomAbs_Cylinder:
        return surf.Cylinder().Radius()
    if t == GeomAbs_Sphere:
        return surf.Sphere().Radius()
    if t == GeomAbs_Torus:
        return surf.Torus().MinorRadius()
    return None


def expand_tangent(shape, seeds: list, tol_deg: float = 1.0, cap: int = 64) -> list:
    """Expande `seeds` a la CADENA del fillet: caras CURVAS vecinas que son
    tangentes (G1 dentro de `tol_deg`) **o del mismo radio** — dos tramos de
    fillet que se encuentran en una esquina viva NO son G1 entre sí, pero
    comparten radio. Las caras PLANAS no se agregan por expansión: un fillet es
    tangente a sus caras BASE por construcción y sin este corte la cadena se
    'fugaría' al sólido entero (los chaflanes —planos— se seleccionan a mano con
    cerca+count). Tope duro `cap`."""
    from build123d import Edge, Face, GeomType
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp, TopExp_Explorer
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
    from OCP.TopoDS import TopoDS

    amap = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape.wrapped, TopAbs_EDGE, TopAbs_FACE, amap)
    cos_tol = math.cos(math.radians(tol_deg))

    accepted: list = []

    def _has(f) -> bool:
        return any(f.wrapped.IsSame(a.wrapped) for a in accepted)

    queue = []
    for s in seeds:
        if not _has(s):
            accepted.append(s)
            queue.append(s)

    while queue:
        face = queue.pop(0)
        r_face = _curved_radius(face)
        exp = TopExp_Explorer(face.wrapped, TopAbs_EDGE)
        while exp.More():
            edge_w = exp.Current()
            exp.Next()
            if not amap.Contains(edge_w):
                continue
            mid = Edge(TopoDS.Edge_s(edge_w)).position_at(0.5)
            try:
                n_face = face.normal_at(mid)
            except Exception:
                n_face = None
            for nb_w in amap.FindFromKey(edge_w):  # TopTools_ListOfShape es iterable
                if nb_w.IsSame(face.wrapped):
                    continue
                nb_face = Face(TopoDS.Face_s(nb_w))
                if _has(nb_face) or nb_face.geom_type == GeomType.PLANE:
                    continue
                tangent = False
                if n_face is not None:
                    try:
                        n_nb = nb_face.normal_at(mid)
                        dot = abs(n_face.X * n_nb.X + n_face.Y * n_nb.Y + n_face.Z * n_nb.Z)
                        tangent = dot >= cos_tol
                    except Exception:
                        tangent = False
                r_nb = _curved_radius(nb_face)
                same_radius = (
                    r_face is not None and r_nb is not None and abs(r_face - r_nb) < 1e-6
                )
                if tangent or same_radius:
                    accepted.append(nb_face)
                    queue.append(nb_face)
                    if len(accepted) > cap:
                        raise DirectError(
                            f"La cadena tangente superó {cap} caras (se está 'fugando' "
                            "a la base): selecciona las caras a mano con cerca+count"
                        )
    return accepted
