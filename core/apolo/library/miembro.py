"""Un miembro de perfil ENTRE dos piezas, con cada extremo cortado como se une (plan
uniones-que-tocan, D3/D3b) — geometría pura, la usa `commands/miembro.py` (`create_brace`).

El eje va del punto de un extremo al del otro. Cada extremo se GENERA por su tipo de unión,
determinista:
- `a_tope`: el miembro llega a la cara PLANA de la pieza que recibe y se corta con el plano de esa
  cara (el corte de sierra: ángulo α = el del eje con la normal de la cara; 0 = a escuadra). La
  cara es la primera que corta el eje yendo del centro del miembro hacia el punto.
- `boca_de_pescado`: tubo contra tubo redondo (o cualquier cara curva): el extremo se copia a la
  pieza que recibe (se le resta su sólido y queda el tramo del centro), como lo deja una copiadora
  de tubos; α = el del eje con la normal en el punto donde el eje entra.
- `inglete`: contra otro miembro que sale del mismo nodo (`hacia` = el otro extremo de ese
  vecino): el plano BISECTOR por el nodo, el mismo de `library/miter.py` (α = 90 − θ/2, con su tope
  `MAX_MITER_DEG` y el corte recto si son colineales). El vecino se corta igual con su comando.

Solapada (chapa sobre chapa) y cartela no entran (otra fase del plan). El marco del perfil: z =
eje, x = la vertical del plano que contiene al eje (o X si el eje es vertical), girado `giro`°
sobre el eje: un tubo cuadrado de una riostra en un plano vertical queda con dos caras en ese
plano. La lista de corte lee `cut_length` (el largo EXTERIOR: la extensión del sólido sobre el
eje) y `miter` (α de cada extremo).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .miter import COLLINEAR_TOL_DEG, MAX_MITER_DEG, miter_angle

UNIONES = ("a_tope", "boca_de_pescado", "inglete")
#: Un corte más oblicuo que esto (eje casi paralelo a la cara) no asienta: la punta sería absurda.
MAX_CORTE_DEG = MAX_MITER_DEG


@dataclass
class Extremo:
    punto: tuple
    union: str = "a_tope"
    pieza: object = None   # el sólido que recibe (build123d); None sólo en `inglete`
    hacia: tuple | None = None


@dataclass
class Miembro:
    shape: object
    cut_length: float
    angulos: tuple       # (α_a, α_b) en grados desde el corte recto
    seccion: tuple       # (ancho, alto) de la sección del perfil


def _sub(p, q):
    return tuple(p[i] - q[i] for i in range(3))


def _add(p, q, s=1.0):
    return tuple(p[i] + s * q[i] for i in range(3))


def _dot(p, q):
    return sum(p[i] * q[i] for i in range(3))


def _cross(p, q):
    return (p[1] * q[2] - p[2] * q[1], p[2] * q[0] - p[0] * q[2], p[0] * q[1] - p[1] * q[0])


def _unit(p):
    n = math.sqrt(_dot(p, p))
    if n < 1e-9:
        raise ValueError("dirección nula")
    return tuple(c / n for c in p)


def marco(u, giro_deg: float = 0.0) -> tuple:
    """(x, y, z=u) del perfil: x = la vertical del plano que contiene al eje (X si es vertical),
    girada `giro_deg` sobre u."""
    ref = (0.0, 0.0, 1.0) if abs(u[2]) < 0.999 else (1.0, 0.0, 0.0)
    x = _unit(_sub(ref, tuple(_dot(ref, u) * c for c in u)))
    g = math.radians(giro_deg)
    ux = _cross(u, x)
    x = _unit(tuple(x[i] * math.cos(g) + ux[i] * math.sin(g) for i in range(3)))
    return x, _cross(u, x), u


def entrada(pieza, desde, direccion) -> tuple | None:
    """(punto, normal, plana) donde la recta desde `desde` en `direccion` entra por primera vez en
    `pieza`, o None si no la toca."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepIntCurveSurface import BRepIntCurveSurface_Inter
    from OCP.BRepLProp import BRepLProp_SLProps
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt

    it = BRepIntCurveSurface_Inter()
    it.Init(pieza.wrapped, gp_Lin(gp_Pnt(*desde), gp_Dir(*direccion)), 1e-6)
    mejor = None
    while it.More():
        w = it.W()
        if w > 1e-6 and (mejor is None or w < mejor[0]):
            mejor = (w, it.Pnt(), it.Face(), it.U(), it.V())
        it.Next()
    if mejor is None:
        return None
    _w, p, cara, uu, vv = mejor
    sup = BRepAdaptor_Surface(cara)
    props = BRepLProp_SLProps(sup, uu, vv, 1, 1e-6)
    if not props.IsNormalDefined():
        return None
    n = props.Normal()
    return (p.X(), p.Y(), p.Z()), (n.X(), n.Y(), n.Z()), sup.GetType() == GeomAbs_Plane


def _semiespacio(origen, normal, tam: float):
    """El sólido que QUITA {x : (x − origen)·normal < 0} (una caja grande del lado negativo)."""
    from build123d import Box, Location, Plane

    centro = _add(origen, normal, -tam / 2.0)
    return Location(Plane(origin=centro, z_dir=normal)) * Box(tam, tam, tam)


def _mayor(shape):
    solidos = shape.solids() if hasattr(shape, "solids") else [shape]
    if not solidos:
        raise ValueError("el corte dejó el miembro vacío")
    return max(solidos, key=lambda s: s.volume)


def _largo_exterior(shape, u) -> float:
    proy = [_dot((v.X, v.Y, v.Z), u) for e in shape.edges()
            for v in e.positions([i / 16.0 for i in range(17)])]
    return max(proy) - min(proy)


def miembro_entre(perfil: str, ea: Extremo, eb: Extremo, giro_deg: float = 0.0) -> Miembro:
    """El miembro de `perfil` (ref de catálogo cortable) de `ea.punto` a `eb.punto`, cortado en
    cada extremo según su `union`. ValueError con la corrección si no se puede."""
    from build123d import Location, Plane

    from .catalog import build_component

    for e in (ea, eb):
        if e.union not in UNIONES:
            raise ValueError(f"unión '{e.union}' desconocida: {', '.join(UNIONES)}")
    pa, pb = tuple(map(float, ea.punto)), tuple(map(float, eb.punto))
    largo0 = math.dist(pa, pb)
    base, _ = build_component(perfil, 100.0)
    bb = base.bounding_box()
    w, h = bb.max.X - bb.min.X, bb.max.Y - bb.min.Y
    diag = math.hypot(w, h)
    if largo0 <= 2.0 * diag:
        raise ValueError(f"los dos puntos están a {largo0:.0f} mm: demasiado cerca para el perfil "
                         f"{perfil} ({w:g}×{h:g})")
    u = _unit(_sub(pb, pa))
    medio = _add(pa, u, largo0 / 2.0)
    cortes, refs, angulos = [], [], []
    for nombre, e, sale in (("a", ea, tuple(-c for c in u)), ("b", eb, u)):
        adentro = tuple(-c for c in sale)  # del extremo hacia el centro del miembro
        if e.union == "inglete":
            if e.hacia is None:
                raise ValueError(f"extremo {nombre}: el inglete necesita `hacia`, el otro extremo "
                                 "del miembro vecino que sale del mismo nodo")
            vecino = _unit(_sub(tuple(map(float, e.hacia)), tuple(map(float, e.punto))))
            alfa = miter_angle(adentro, vecino)
            if alfa > MAX_MITER_DEG:
                raise ValueError(f"extremo {nombre}: el inglete daría {alfa:.0f}° (> "
                                 f"{MAX_MITER_DEG:g}°): una punta absurda; únelo a_tope")
            nodo = tuple(map(float, e.punto))
            n = adentro if alfa < COLLINEAR_TOL_DEG else _unit(_sub(adentro, vecino))
            if alfa < COLLINEAR_TOL_DEG:
                alfa = 0.0
            cortes.append(("plano", nodo, n))
            refs.append(nodo)
            angulos.append(round(alfa, 1))
            continue
        hit = entrada(e.pieza, medio, sale)
        if hit is None:
            raise ValueError(f"extremo {nombre}: el eje que va del centro del miembro hacia su punto "
                             "no toca la pieza que lo recibe: pon el punto sobre (o dentro de) ella")
        p, normal, plana = hit
        coseno = abs(_dot(u, _unit(normal)))
        alfa = math.degrees(math.acos(max(-1.0, min(1.0, coseno))))
        if alfa > MAX_CORTE_DEG:
            raise ValueError(f"extremo {nombre}: el eje llega casi paralelo a la cara ({alfa:.0f}° "
                             f"de su normal, tope {MAX_CORTE_DEG:g}°): no asienta")
        if e.union == "a_tope" and not plana:
            raise ValueError(f"extremo {nombre}: la cara que recibe es curva; usa "
                             "union='boca_de_pescado' (tubo contra tubo redondo)")
        n = _unit(normal)
        if _dot(_sub(medio, p), n) < 0:
            n = tuple(-c for c in n)
        cortes.append(("plano", p, n) if e.union == "a_tope" else ("pieza", e.pieza, None))
        refs.append(p)
        angulos.append(round(alfa, 1))
    exts = [diag / 2.0 * math.tan(math.radians(min(a, MAX_MITER_DEG))) + 2.0 for a in angulos]
    exts = [x + (diag if c[0] == "pieza" else 0.0) for x, c in zip(exts, cortes)]
    ra, rb = refs
    tramo = _dot(_sub(rb, ra), u)
    if tramo <= diag:
        raise ValueError(f"entre las caras que reciben quedan {tramo:.0f} mm: el miembro no cabe")
    ini, fin = _add(ra, u, -exts[0]), _add(rb, u, exts[1])
    l_build = math.dist(ini, fin)
    shape, _ = build_component(perfil, l_build)
    x, _y, z = marco(u, giro_deg)
    shape = Location(Plane(origin=_add(ini, u, l_build / 2.0), x_dir=x, z_dir=z)) * shape
    tam = 4.0 * (l_build + diag)
    for tipo, origen, n in cortes:
        quitar = _semiespacio(origen, n, tam) if tipo == "plano" else origen
        shape = _mayor(shape - quitar)
    return Miembro(shape, round(_largo_exterior(shape, u), 1), tuple(angulos), (round(w, 2), round(h, 2)))
