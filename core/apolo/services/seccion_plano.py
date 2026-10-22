"""Secciones planas de un sólido, como puntos (fabrica-de-publicaciones, ajuste D13): la mitad OCCT
de la prueba de fidelidad de la faja animada. Corre bajo el `STATE_LOCK` del llamador; devuelve
datos puros para `library/ruta_faja_modelo.py` y `library/fidelidad_faja.py`.

El sólido llega YA colocado en el marco de la faja (`kernel.shapes.place_matrix` con la inversa
del marco: x = u, y = w, z = v), así una sección es el corte con el plano z = v y sus puntos son
directamente (u, w). Cada cara del corte es {"ext": [[u, w]…], "huecos": [[[u, w]…]…]}; las caras
que se tocan o solapan (los tramos y los tubos de la banda del super-comando) se funden antes.
"""

from __future__ import annotations

#: Flecha (mm) y ángulo (rad) máximos entre una curva y su polilínea.
FLECHA_MM = 0.05
ANGULO_RAD = 0.1
#: Lo que el rectángulo de corte sobra alrededor del encuadre de la pieza (mm).
MARGEN_MM = 10.0


def _puntos_wire(wire, face) -> list[list[float]]:
    """La polilínea de un wire en su orden (y el sentido de cada arista), sin el cierre."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.GCPnts import GCPnts_TangentialDeflection
    from OCP.TopAbs import TopAbs_REVERSED

    out: list[list[float]] = []
    ex = BRepTools_WireExplorer(wire, face)
    while ex.More():
        curva = BRepAdaptor_Curve(ex.Current())
        muestras = GCPnts_TangentialDeflection(curva, curva.FirstParameter(), curva.LastParameter(),
                                               ANGULO_RAD, FLECHA_MM, 2)
        pts = [muestras.Value(i) for i in range(1, muestras.NbPoints() + 1)]
        if ex.Orientation() == TopAbs_REVERSED:
            pts.reverse()
        for p in pts[:-1]:
            q = [round(p.X(), 3), round(p.Y(), 3)]
            if not out or out[-1] != q:
                out.append(q)
        ex.Next()
    if len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out


def caras(seccion) -> list[dict]:
    """Las caras de un corte como {ext, huecos} en (u, w)."""
    out = []
    for f in seccion.faces() if seccion is not None else []:
        ext = _puntos_wire(f.outer_wire().wrapped, f.wrapped)
        if len(ext) < 3:
            continue
        out.append({"ext": ext, "huecos": [h for w in f.inner_wires()
                                           if len(h := _puntos_wire(w.wrapped, f.wrapped)) >= 3]})
    return out


def cortar(local, z: float) -> list[dict]:
    """El corte del sólido `local` (en el marco de la faja) con el plano z: sus caras fundidas.
    Sin intersección, []."""
    from build123d import Compound, Face, Plane

    bb = local.bounding_box(optimal=False)
    if not bb.min.Z <= z <= bb.max.Z:
        return []
    cu, cw = (bb.min.X + bb.max.X) / 2.0, (bb.min.Y + bb.max.Y) / 2.0
    lado_u = bb.max.X - bb.min.X + 2 * MARGEN_MM
    lado_w = bb.max.Y - bb.min.Y + 2 * MARGEN_MM
    plano = Face.make_rect(lado_u, lado_w, Plane(origin=(cu, cw, z), x_dir=(1, 0, 0), z_dir=(0, 0, 1)))
    try:
        corte = local.intersect(plano)
    except Exception:  # noqa: BLE001 — una pieza que OCCT no corta no estorba la prueba
        return []
    if corte is None:
        return []
    fs = corte.faces()
    if len(fs) > 1:
        try:
            fundido = fs[0].fuse(*fs[1:])
            if isinstance(fundido, list):   # caras que no se tocan: build123d da una ShapeList
                fundido = Compound(list(fundido))
            corte = fundido.clean()
        except Exception:  # noqa: BLE001 — sin fundir quedan las caras sueltas
            pass
    return caras(corte)


def lazo_de_banda(cortes_banda: list[dict]) -> dict | None:
    """La cara de la sección de la banda que es un LAZO (la de más área con al menos un hueco),
    o None: sin lazo cerrado, la ruta cae al casco convexo."""
    from apolo.library.ruta_faja_modelo import area

    lazos = [c for c in cortes_banda if c["huecos"]]
    return max(lazos, key=lambda c: abs(area(c["ext"]))) if lazos else None
