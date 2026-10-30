"""Secciones planas de un sólido, como puntos (fabrica-de-publicaciones, ajuste D13): la mitad OCCT
de la prueba de fidelidad de la faja animada. Corre bajo el `STATE_LOCK` del llamador; devuelve
datos puros para `library/ruta_faja_modelo.py` y `library/fidelidad_faja.py`.

El sólido llega YA colocado en el marco de la faja (`kernel.shapes.place_matrix` con la inversa
del marco: x = u, y = w, z = v), así una sección es el corte con el plano z = v y sus puntos son
directamente (u, w). Cada cara del corte es {"ext": [[u, w]…], "huecos": [[[u, w]…]…]}; las caras
que se tocan o solapan (los tramos y los tubos de la banda del super-comando) se funden antes. Si
el corte de la banda no queda en UN lazo —tramos que sólo se tocan en una esquina, una banda
modular hueca por dentro—, `lazo_de_banda` lo cierra (`cerrar`; lo-fijo-que-gira, D4a).
"""

from __future__ import annotations

#: Flecha (mm) y ángulo (rad) máximos entre una curva y su polilínea.
FLECHA_MM = 0.05
ANGULO_RAD = 0.1
#: Lo que el rectángulo de corte sobra alrededor del encuadre de la pieza (mm).
MARGEN_MM = 10.0
#: Los cierres (mm) que se prueban, de menor a mayor, para unir el corte de una banda que no es
#: un lazo (D4a de lo-fijo-que-gira): ≤ 10 mm no cierra el hueco de un lazo (el tambor más chico
#: tiene Ø ≥ 40) y sí las dos pieles de una banda modular hueca (≈ 9 mm entre ellas).
CIERRE_MM = (0.5, 2.0, 5.0, 10.0)


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


def _cara(c: dict):
    from build123d import Face, Wire

    def wire(pts):
        return Wire.make_polygon([(u, w, 0.0) for u, w in pts], close=True)

    return Face(wire(c["ext"]), [wire(h) for h in c["huecos"]])


def _gorda(c: dict, delta: float):
    """La cara crecida `delta`: su borde hacia afuera y sus huecos hacia adentro (el hueco más
    angosto que 2·`delta` se cierra)."""
    from build123d import Face, Kind

    f = _cara(c)
    huecos = []
    for h in f.inner_wires():
        try:
            w = h.offset_2d(-delta, kind=Kind.ARC)
            if Face(w).area > 0:
                huecos.append(w)
        except Exception:  # noqa: BLE001 — el hueco se cerró
            continue
    return Face(f.outer_wire().offset_2d(delta, kind=Kind.ARC), huecos)


def cerrar(cortes_banda: list[dict], delta: float) -> dict | None:
    """Cierre morfológico de las caras del corte de una banda (lo-fijo-que-gira, D4a): crecer
    `delta` cada cara, fundir y encoger `delta` lo fundido. Une los tramos que se tocan en una
    esquina y las dos pieles de una banda hueca por dentro; nada más ancho que 2·`delta`. Devuelve
    la cara {ext, huecos: [el mayor]} si TODO el corte quedó en una sola cara con hueco; si no, None."""
    from build123d import Compound, Face, Kind

    from apolo.library.ruta_faja_modelo import area

    gordas = [_gorda(c, delta) for c in cortes_banda]
    unida = gordas[0].fuse(*gordas[1:]) if len(gordas) > 1 else gordas[0]
    if isinstance(unida, list):   # caras que no se tocan: build123d da una ShapeList
        unida = Compound(list(unida))
    fs = unida.clean().faces()
    if len(fs) != 1 or not fs[0].inner_wires():
        return None
    hueco = max(fs[0].inner_wires(), key=lambda w: Face(w).area)
    cara = Face(fs[0].outer_wire().offset_2d(-delta, kind=Kind.ARC),
                [hueco.offset_2d(delta, kind=Kind.ARC)])
    (c,) = caras(cara)
    return c if c["huecos"] and abs(area(c["huecos"][0])) > 0 else None


def lazo_de_banda(cortes_banda: list[dict]) -> dict | None:
    """La sección de la banda como UN lazo. Una sola cara con hueco: ésa. Si no —una banda
    modular hecha de tramos que se tocan en una esquina, o hueca por dentro (dos pieles)—, el
    cierre de `cerrar` con el menor `CIERRE_MM` que deja TODO el corte en una cara con hueco
    (lo-fijo-que-gira, D4a); si no se puede, la cara de más área con hueco. None si no hay
    ninguna: la ruta cae al casco convexo."""
    from apolo.library.ruta_faja_modelo import area

    lazos = [c for c in cortes_banda if c["huecos"]]
    if len(cortes_banda) == 1 and lazos:
        return lazos[0]
    unido = _cerrado(cortes_banda) if cortes_banda else None
    if unido is not None:
        return unido
    return max(lazos, key=lambda c: abs(area(c["ext"]))) if lazos else None


def _cerrado(cortes_banda: list[dict]) -> dict | None:
    for delta in CIERRE_MM:
        try:
            c = cerrar(cortes_banda, delta)
        except Exception:  # noqa: BLE001 — un offset que OCCT no resuelve: el siguiente
            c = None
        if c is not None:
            return c
    return None
