"""Los COLISOS de una forma para `union.agujeros` (plan puerta-sin-sobrediseno, F3e): una ranura
alargada, de extremos redondos o rectos, es el agujero de un perno si su ANCHO es el paso de la
métrica (`library/calidad/agujeros.compatible`, el mismo rango que el Ø de un agujero redondo).

Cómo se ve en la geometría (lee shapes: el llamador sostiene STATE_LOCK):
- **candidata**: dos caras PLANAS paralelas de un mismo sólido, a ≤ 50 mm, que se enfrentan (sus
  cajas se solapan) y cuyo punto medio cae en el HUECO (no en el material: las dos caras de una
  chapa no son un coliso). El eje del perno es la arista recta MÁS CORTA de la pared (el espesor
  de la chapa): por él el coliso atraviesa la pieza; el interior de un tubo, cuya arista más
  corta va a lo ancho, queda abierto a lo largo y no pasa;
- **medida**: la de `library/borde_agujero.abertura` (los rayos OCCT de `medir_borde`, por
  sólido, en el plano ⊥ al eje): el ANCHO es el menor a(θ) + a(θ + π), el largo el de la
  dirección de la ranura (⊥ a las dos paredes y al eje), y toda
  recta tiene que tocar pared (cerrada: una muesca abierta o dos aletas no son coliso). El par
  candidato tiene que ser el angosto (ancho = su separación ± 0,5 mm);
- uno por eje y centro (las paredes largas y las cortas de un coliso recto dan el mismo); los
  medios cilindros de sus extremos redondos son el MISMO coliso, no dos agujeros (`absorbe`).
"""

from __future__ import annotations

import math

_GAP_MAX_MM = 50.0     # el mayor agujero de perno sin métrica (`agujeros.D_SIN_METRICA_MM`)
_TOL_ANCHO_MM = 0.5
_PARALELO = 1e-3


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a):
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-12 else None


def _planas(solid) -> list[dict]:
    """[{n, p, lo, hi, t}] de las caras planas: normal (sin signo), un punto, su caja y la
    dirección de su arista recta más corta."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane

    out = []
    for f in solid.faces():
        try:
            ad = BRepAdaptor_Surface(f.wrapped)
            if ad.GetType() != GeomAbs_Plane:
                continue
            pl = ad.Plane()
            dr, loc = pl.Axis().Direction(), pl.Location()
            corta = None
            for e in f.edges():
                if e.geom_type.name != "LINE":
                    continue
                a, b = e @ 0, e @ 1
                largo = (b - a).length
                if largo > 1e-6 and (corta is None or largo < corta[0]):
                    corta = (largo, _unit((b.X - a.X, b.Y - a.Y, b.Z - a.Z)))
            if corta is None:
                continue
            bb = f.bounding_box()
        except Exception:  # noqa: BLE001 — una cara rara no es pared de un coliso
            continue
        out.append({"n": (dr.X(), dr.Y(), dr.Z()), "p": (loc.X(), loc.Y(), loc.Z()),
                    "lo": (bb.min.X, bb.min.Y, bb.min.Z), "hi": (bb.max.X, bb.max.Y, bb.max.Z),
                    "t": corta[1]})
    return out


def _centro(a: dict, b: dict):
    c = []
    for i in range(3):
        lo, hi = max(a["lo"][i], b["lo"][i]), min(a["hi"][i], b["hi"][i])
        c.append((lo + hi) / 2.0)
    return tuple(c)


def _enfrentan(a: dict, b: dict, gap: float) -> bool:
    return all(a["lo"][i] - gap - 1.0 <= b["hi"][i] and b["lo"][i] - gap - 1.0 <= a["hi"][i]
               for i in range(3))


def colisos_de(shape) -> list[dict]:
    """Los colisos de `shape`: [{tipo: "coliso", d (ancho), largo, p (centro), eje, p0, p1 (los
    centros de sus extremos), lo, hi}]."""
    from apolo.kernel.rayo import Rayos
    from apolo.library.borde_agujero import abertura

    out: list[dict] = []
    for solid in shape.solids():
        planas, rayos = _planas(solid), Rayos(solid)
        for i, a in enumerate(planas):
            for b in planas[i + 1:]:
                if abs(abs(_dot(a["n"], b["n"])) - 1.0) > _PARALELO:
                    continue
                gap = abs(_dot(_sub(b["p"], a["p"]), a["n"]))
                if not 0.5 < gap <= _GAP_MAX_MM or not _enfrentan(a, b, gap):
                    continue
                t = a["t"]
                if abs(_dot(t, a["n"])) > _PARALELO:
                    continue
                c = _centro(a, b)
                if rayos.dentro(c):
                    continue  # las dos caras de una chapa: el medio es material
                largo_l = _unit(_cross(t, a["n"]))
                alcance = max(max(a["hi"][k] - a["lo"][k], b["hi"][k] - b["lo"][k])
                              for k in range(3)) + gap + 5.0
                m = abertura(rayos, c, t, largo_l, alcance)
                if m is None or not m["cerrada"] or abs(m["ancho"] - gap) > _TOL_ANCHO_MM:
                    continue
                s = (m["a0"] - m["a180"]) / 2.0  # el centro a lo largo de la ranura
                p = tuple(c[k] + s * largo_l[k] for k in range(3))
                largo = m["a0"] + m["a180"]  # a lo largo de la ranura (no la diagonal)
                medio = max(largo - m["ancho"], 0.0) / 2.0
                nuevo = {"tipo": "coliso", "d": m["ancho"], "largo": largo, "p": p, "eje": t,
                         "p0": tuple(p[k] - medio * largo_l[k] for k in range(3)),
                         "p1": tuple(p[k] + medio * largo_l[k] for k in range(3)),
                         "lo": tuple(min(a["lo"][k], b["lo"][k]) - m["ancho"] / 2.0
                                     for k in range(3)),
                         "hi": tuple(max(a["hi"][k], b["hi"][k]) + m["ancho"] / 2.0
                                     for k in range(3))}
                if not any(_mismo(x, nuevo) for x in out):
                    out.append(nuevo)
    return out


def _mismo(a: dict, b: dict) -> bool:
    if abs(abs(_dot(a["eje"], b["eje"])) - 1.0) > _PARALELO:
        return False
    w = _sub(b["p"], a["p"])
    k = _dot(w, a["eje"])
    return math.dist(w, tuple(k * a["eje"][i] for i in range(3))) < min(a["d"], b["d"]) / 2.0


def absorbe(coliso: dict, agujero: dict) -> bool:
    """¿El agujero redondo es un extremo redondo de este coliso (mismo Ø, eje paralelo, sobre su
    tramo)?"""
    from apolo.library.calidad.agujeros import distancia_a_tramo

    if abs(coliso["d"] - agujero["d"]) > 0.3:
        return False
    if abs(abs(_dot(coliso["eje"], agujero["eje"])) - 1.0) > _PARALELO:
        return False
    return distancia_a_tramo(agujero["p"], coliso["p0"], coliso["p1"], coliso["eje"]) <= 0.5
