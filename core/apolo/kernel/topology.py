"""Introspección de topología: enumera CARAS y ARISTAS de un sólido con su
geometría descriptiva (tipo, centro, normal/eje, longitud, radio).

Pensado para que el agente IA "vea" la geometría y elija el SELECTOR declarativo
correcto (todas/direccion/cara/longitud/cerca) antes de fillet/chamfer/drill/mate
— NO introduce un modo de selección por id. Read-only: no muta nada.

Reusa el patrón probado de `assembly/mates.py::connector_of` (cara plana → normal;
cilíndrica → eje vía OCCT BRepAdaptor), pero vive en `kernel/` para respetar la
frontera de capas (assembly depende de kernel, no al revés); el lector de cilindro
se replica local. Cada lectura va en try/except → si una cara/arista no clasifica,
degrada a `{idx, tipo, center}` y nunca rompe la enumeración.
"""

from __future__ import annotations


def _r(x: float, nd: int = 3) -> float:
    return round(float(x), nd)


def _vec3(v, nd: int = 3) -> list[float]:
    return [_r(v.X, nd), _r(v.Y, nd), _r(v.Z, nd)]


def _kind(obj) -> str:
    """'GeomType.PLANE' / 'PLANE' → 'PLANE' (robusto al formato del enum)."""
    return str(getattr(obj, "geom_type", "")).rsplit(".", 1)[-1].upper()


def _cylinder_info(face):
    """(punto del eje, dirección, radio) de una cara cilíndrica vía OCCT BRepAdaptor."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface

    cyl = BRepAdaptor_Surface(face.wrapped).Cylinder()
    ax = cyl.Axis()
    p, d = ax.Location(), ax.Direction()
    return (
        [_r(p.X()), _r(p.Y()), _r(p.Z())],
        [_r(d.X(), 6), _r(d.Y(), 6), _r(d.Z(), 6)],
        _r(cyl.Radius()),
    )


def _face_entry(idx: int, face) -> dict:
    entry: dict = {"idx": idx, "tipo": _kind(face) or "desconocida"}
    try:
        entry["center"] = _vec3(face.center())
    except Exception:  # noqa: BLE001
        return entry
    try:
        entry["area"] = _r(face.area, 1)
    except Exception:  # noqa: BLE001
        pass
    tipo = entry["tipo"]
    if "PLANE" in tipo:
        try:
            n = face.normal_at()
            entry["normal"] = [_r(n.X, 6), _r(n.Y, 6), _r(n.Z, 6)]
        except Exception:  # noqa: BLE001
            pass
    elif "CYLINDER" in tipo:
        try:
            axis_pt, axis_dir, radius = _cylinder_info(face)
            entry["axis"] = axis_dir
            entry["axis_point"] = axis_pt
            entry["radius"] = radius
        except Exception:  # noqa: BLE001
            pass
    return entry


def _edge_entry(idx: int, edge) -> dict:
    entry: dict = {"idx": idx, "tipo": _kind(edge) or "desconocida"}
    try:
        entry["center"] = _vec3(edge.center())
    except Exception:  # noqa: BLE001
        return entry
    try:
        entry["length"] = _r(edge.length)
    except Exception:  # noqa: BLE001
        pass
    tipo = entry["tipo"]
    try:
        start = edge.position_at(0)
        end = edge.position_at(1)
        entry["start"] = _vec3(start)
        entry["end"] = _vec3(end)
        if "LINE" in tipo:
            dx, dy, dz = end.X - start.X, end.Y - start.Y, end.Z - start.Z
            n = (dx * dx + dy * dy + dz * dz) ** 0.5
            if n > 1e-9:
                entry["direction"] = [_r(dx / n, 6), _r(dy / n, 6), _r(dz / n, 6)]
    except Exception:  # noqa: BLE001
        pass
    if "CIRCLE" in tipo or "ELLIPSE" in tipo:
        try:
            entry["radius"] = _r(edge.radius)
        except Exception:  # noqa: BLE001
            pass
        try:
            entry["arc_center"] = _vec3(edge.arc_center)
        except Exception:  # noqa: BLE001
            pass
    return entry


def feature_topology(shape) -> dict:
    """Enumera caras y aristas del `shape` con su geometría descriptiva.

    Devuelve ``{"faces": [...], "edges": [...]}``. Los índices (``idx``) son
    estables dentro de una misma geometría y sirven solo de referencia para el
    agente; la SELECCIÓN sigue siendo declarativa (por orientación, longitud,
    proximidad), no por idx.
    """
    faces = [_face_entry(i, f) for i, f in enumerate(shape.faces())]
    edges = [_edge_entry(i, e) for i, e in enumerate(shape.edges())]
    return {"faces": faces, "edges": edges}
