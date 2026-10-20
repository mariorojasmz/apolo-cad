"""Lint pre-entrega «asiento fuera de la zona plana» (plan perfiles-con-acuerdo, D2).

Un taladro en un perfil abierto cuyo asiento (el propio agujero, o la cabeza/tuerca/arandela
coaxial) pisa el acuerdo r1 del perfil real no asienta, aunque el modelo prismático lo dé por
bueno (la piloto del proyecto 2: ejes a 20 mm del canto de un UPN-100, cuya zona plana
empieza a ~18). La geometría de norma vive en `acuerdos.py`.

Puro como `lints.py`: recibe la escena y el catálogo, nunca un `Document`. Los taladros se
leen de la GEOMETRÍA (caras cilíndricas del perfil), no de los comandos: así cubre
`drill_hole` (por punto o por cara), `join_bolted` (que corta sin `drill_hole`) y cualquier
otra vía, con las `=expresiones` ya resueltas por el regenerate.

Marco del perfil (F3, D3/D4): primero sus ANCLAS (`perfiles_abiertos.py`; `insert_component`
las publica, todo lo que mueve la pieza las arrastra y un taladro las conserva aunque borre
`Feature.matrix`). Con ellas el perfil se lee en cualquier pose, también inclinado, y sin
ambigüedad de cotas. Una pieza sin anclas (copia por espejo, que no las propaga) o con anclas
que no casan con su geometría cae a la lectura por el BBOX de F2: ejes paralelos a los del
mundo y coincidencia ÚNICA de cotas; si tampoco, se SALTA (no se adivina).
"""

from __future__ import annotations

import math

from .acuerdos import inicio_zona_plana_alma, zona_plana_ala_angulo

# tolerancias de lectura de la geometría (mm)
_TOL_DIM = 0.5     # una cota del bbox «es» h/b/leg del catálogo
_TOL_EJE = 1.0     # un herraje está EN el eje del taladro
_HOLGURA = 0.05    # un asiento que sale de la zona plana por menos que esto no avisa
_PARALELO = 0.999  # |cos| entre el eje de un taladro y una dirección del marco
_MAX_EJEMPLOS = 6


# ------------------------------------------------------------------------ vectores
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _unit(v):
    v = tuple(float(c) for c in v)
    n = math.sqrt(_dot(v, v))
    if n < 1e-9:
        raise ValueError("vector nulo")
    return (v[0] / n, v[1] / n, v[2] / n)


def _eje_mundo(d) -> int | None:
    """Índice del eje del mundo al que es paralela la dirección `d`, o None si es oblicua."""
    k = max(range(3), key=lambda i: abs(d[i]))
    return k if abs(d[k]) >= _PARALELO else None


def _bbox(shape):
    bb = shape.bounding_box()
    return (bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)


def _dentro(p, caja, tol: float = 1.0) -> bool:
    lo, hi = caja
    return all(lo[i] - tol <= p[i] <= hi[i] + tol for i in range(3))


# ------------------------------------------------------------------ taladros y herraje
def _agujeros(shape) -> list[tuple[tuple, tuple, float]]:
    """Taladros del perfil: caras cilíndricas agrupadas por RECTA (un caladrillo o una cara
    partida por la costura son el MISMO agujero; vale el radio mayor). Devuelve
    [(dirección unitaria del eje, punto del eje, radio)]."""
    from build123d import GeomType
    from OCP.BRepAdaptor import BRepAdaptor_Surface

    rectas: list[list] = []
    for face in shape.faces():
        if face.geom_type != GeomType.CYLINDER:
            continue
        cyl = BRepAdaptor_Surface(face.wrapped).Cylinder()
        dd, loc = cyl.Axis().Direction(), cyl.Axis().Location()
        d = _unit((dd.X(), dd.Y(), dd.Z()))
        p = (loc.X(), loc.Y(), loc.Z())
        r = cyl.Radius()
        for recta in rectas:
            if abs(_dot(recta[0], d)) < _PARALELO:
                continue
            w = _sub(p, recta[1])
            t = _dot(w, recta[0])
            if math.sqrt(max(0.0, _dot(w, w) - t * t)) < 0.05:  # p sobre esa recta
                recta[2] = max(recta[2], r)
                break
        else:
            rectas.append([d, p, r])
    return [tuple(r) for r in rectas]


def _herrajes(scene, catalog) -> list[tuple]:
    """(bbox_min, bbox_max) de cada SÓLIDO de tornillería/arandela visible: lo que asienta
    sobre el alma alrededor del taladro."""
    import re

    from .checks import HARDWARE_CATS
    from .lints import _is_bolt

    arandela = re.compile(r"\b(arandelas?|washers?)\b", re.I)
    out = []
    for feat in scene.values():
        if not getattr(feat, "visible", True):
            continue
        comp = catalog.get(getattr(feat, "component", None) or "")
        es = (_is_bolt(feat, catalog) or arandela.search(getattr(feat, "name", "") or "")
              or (comp is not None and comp.category in HARDWARE_CATS | {"tuercas"}))
        if not es:
            continue
        try:
            solidos = list(feat.shape.solids()) or [feat.shape]
        except Exception:
            continue
        for s in solidos:
            try:
                out.append(_bbox(s))
            except Exception:
                continue
    return out


def _radio_asiento(d, p, r, herrajes, caja) -> tuple[float, bool]:
    """Radio del asiento de un taladro: el mayor entre el agujero y el herraje COAXIAL que toca
    el perfil (radio = media cota menor perpendicular al eje: entrecaras de un hexágono, Ø de
    una arandela). Sólo con el eje paralelo a uno del mundo: el bbox de un herraje oblicuo no
    da su radio y queda el del agujero. Devuelve (radio, ¿lo fija un herraje?)."""
    k = _eje_mundo(d)
    if k is None:
        return r, False
    lo_p, hi_p = caja
    radio, por_herraje = r, False
    otros = [i for i in range(3) if i != k]
    for lo, hi in herrajes:
        c = [(lo[i] + hi[i]) / 2.0 for i in range(3)]
        if math.hypot(c[otros[0]] - p[otros[0]], c[otros[1]] - p[otros[1]]) > _TOL_EJE:
            continue
        if any(lo[i] > hi_p[i] + 1.0 or hi[i] < lo_p[i] - 1.0 for i in range(3)):
            continue  # en el eje, pero lejos del perfil (asienta en otra pieza)
        rh = min(hi[i] - lo[i] for i in otros) / 2.0
        if rh > radio:
            radio, por_herraje = rh, True
    return radio, por_herraje


# ------------------------------------------------------------------------ marcos
def _anclas(feat, *nombres) -> list | None:
    """(origen, eje unitario) de cada ancla pedida, o None si falta alguna."""
    a = getattr(feat, "anchors", None) or {}
    try:
        return [(tuple(float(v) for v in a[n]["origin"]), _unit(a[n]["axis"])) for n in nombres]
    except (KeyError, TypeError, ValueError):
        return None


def _marco_alma_anclas(feat, specs, s, caja):
    """(centro de la sección, dirección de h, normal del alma) desde las anclas, o None si
    faltan o no casan con la pieza (no se confía en un marco que no la describe)."""
    an = _anclas(feat, "cara_alma_interior", "zona_plana_1", "zona_plana_2")
    if an is None:
        return None
    (_, n), (z1, _), (z2, _) = an
    v = _sub(z2, z1)
    ancho = math.sqrt(_dot(v, v))
    if abs(ancho - (float(specs["h"]) - 2.0 * s)) > _TOL_DIM:
        return None
    hdir = _unit(v)
    c = tuple((z1[i] + z2[i]) / 2.0 for i in range(3))
    if abs(_dot(n, hdir)) > 1e-6 or not _dentro(c, caja):
        return None
    return c, hdir, n


def _asignar(dims, objetivos) -> tuple | None:
    """Índices de eje cuyo largo coincide con cada objetivo (en orden), o None si no hay una
    asignación ÚNICA (p. ej. un recorte de UPN-100 de 100 mm: h y L no se distinguen)."""
    from itertools import permutations

    sols = {perm[:len(objetivos)] for perm in permutations(range(3))
            if all(abs(dims[perm[j]] - v) < _TOL_DIM for j, v in enumerate(objetivos))}
    return sols.pop() if len(sols) == 1 else None


def _marco_alma_bbox(specs, caja):
    """El mismo marco leído del bbox (F2): h y b por coincidencia ÚNICA de cotas."""
    lo, hi = caja
    asig = _asignar([hi[i] - lo[i] for i in range(3)], (float(specs["h"]), float(specs["b"])))
    if asig is None:
        return None
    e = [tuple(1.0 if j == i else 0.0 for j in range(3)) for i in range(3)]
    return tuple((lo[i] + hi[i]) / 2.0 for i in range(3)), e[asig[0]], e[asig[1]]


def _marco_angulo_anclas(feat, caja):
    """(talón, dirección del ala 1, dirección del ala 2) desde las anclas: el ala 1 sale hacia
    la normal interior del ala 2 y viceversa."""
    an = _anclas(feat, "talon", "cara_ala_1", "cara_ala_2")
    if an is None:
        return None
    (t, largo), (_, n1), (_, n2) = an
    if abs(_dot(n1, n2)) > 1e-6 or abs(_dot(largo, n1)) > 1e-6 or not _dentro(t, caja):
        return None
    return t, n2, n1


def _marco_angulo_bbox(shape, specs, caja):
    """El mismo marco leído del bbox (F2): el largo es el eje sin desfase del centroide (las
    dos alas lo desplazan hacia el talón): distingue el largo aunque mida lo mismo que el ala."""
    from build123d import CenterOf

    lo, hi = caja
    leg = float(specs["leg"])
    dims = [hi[i] - lo[i] for i in range(3)]
    c = shape.center(CenterOf.MASS)
    off = [(c.X, c.Y, c.Z)[i] - (lo[i] + hi[i]) / 2.0 for i in range(3)]
    i_l = min(range(3), key=lambda i: abs(off[i]))
    alas = [i for i in range(3) if i != i_l]
    if any(abs(dims[i] - leg) >= _TOL_DIM for i in alas) or any(abs(off[i]) < 0.5 for i in alas):
        return None
    t = [(lo[i] + hi[i]) / 2.0 for i in range(3)]
    dirs = []
    for i in alas:  # el talón es el lado hacia el que se desplaza el centroide
        t[i] = lo[i] if off[i] < 0 else hi[i]
        dirs.append(tuple((1.0 if off[i] < 0 else -1.0) if j == i else 0.0 for j in range(3)))
    return tuple(t), dirs[0], dirs[1]


# ------------------------------------------------------------------------ juicio
def _fallos_alma(feat, specs, herrajes, *, bbox: bool = False) -> list[str]:
    s = inicio_zona_plana_alma(specs)
    caja = _bbox(feat.shape)
    marco = None if bbox else _marco_alma_anclas(feat, specs, s, caja)
    marco = marco or _marco_alma_bbox(specs, caja)
    if marco is None:
        return []
    c, hdir, n = marco
    mitad = float(specs["h"]) / 2.0
    out = []
    for d, p, r in _agujeros(feat.shape):
        if abs(_dot(d, n)) < _PARALELO:
            continue  # taladro en el ala o a lo largo: no asienta en el alma
        rho, hw = _radio_asiento(d, p, r, herrajes, caja)
        e = mitad - abs(_dot(_sub(p, c), hdir))
        minimo = s + rho
        if e < minimo - _HOLGURA:
            out.append(f"Ø{2 * r:g} con eje a {e:.1f} mm del canto del ala; mínimo {minimo:.1f} "
                       f"(zona plana del alma desde {s:.1f} + radio de asiento {rho:g}"
                       f"{' de la cabeza/tuerca/arandela' if hw else ''})")
    return out


def _fallos_angulo(feat, specs, herrajes, *, bbox: bool = False) -> list[str]:
    t_r1, fin = zona_plana_ala_angulo(specs)
    caja = _bbox(feat.shape)
    marco = None if bbox else _marco_angulo_anclas(feat, caja)
    marco = marco or _marco_angulo_bbox(feat.shape, specs, caja)
    if marco is None:
        return []
    talon, d1, d2 = marco
    out = []
    for d, p, r in _agujeros(feat.shape):
        # un taladro ∥ a la dirección de un ala atraviesa la OTRA: se mide a lo ancho de ésa
        if abs(_dot(d, d2)) >= _PARALELO:
            ancho = d1
        elif abs(_dot(d, d1)) >= _PARALELO:
            ancho = d2
        else:
            continue
        e = _dot(_sub(p, talon), ancho)
        rho, hw = _radio_asiento(d, p, r, herrajes, caja)
        asiento = f"radio de asiento {rho:g}{' de la cabeza/tuerca/arandela' if hw else ''}"
        if e - rho < t_r1 - _HOLGURA:
            out.append(f"Ø{2 * r:g} con eje a {e:.1f} mm del talón; mínimo {t_r1 + rho:.1f} "
                       f"(zona plana del ala desde t + r1 = {t_r1:g} + {asiento})")
        elif e + rho > fin + _HOLGURA:
            out.append(f"Ø{2 * r:g} con eje a {e:.1f} mm del talón; máximo {fin - rho:.1f} "
                       f"(zona plana del ala hasta leg − r2 = {fin:g} − {asiento})")
    return out


def asiento_zona_plana_lint(scene, catalog, *, bbox: bool = False) -> list[dict]:
    """AVISO por cada perfil abierto de catálogo (UPN, IPE, L con r1 en sus specs) con algún
    taladro cuyo asiento sale de la zona plana del alma (U/I) o del ala (L). Roscados y ciegos
    también cuentan: el plan no los exime y lo que asienta sobre ellos (la pieza apretada, la
    cabeza) pisa el mismo acuerdo. El marco sale de las anclas del perfil (cualquier pose) o,
    sin ellas, del bbox; uno ilegible se SALTA (no se adivina). `bbox=True` fuerza la lectura
    por bbox (la de F2: los tests comparan los dos caminos). Defensivo: una pieza ilegible
    jamás tumba el lint."""
    from .rules import _check

    herrajes = None
    fallos: list[str] = []
    for fid, feat in scene.items():
        comp = catalog.get(getattr(feat, "component", None) or "")
        if comp is None or comp.category != "perfiles_abiertos" or "r1" not in comp.specs:
            continue
        if not getattr(feat, "visible", True):
            continue
        try:
            if herrajes is None:
                herrajes = _herrajes(scene, catalog)
            juez = _fallos_angulo if "leg" in comp.specs else _fallos_alma
            malos = juez(feat, comp.specs, herrajes, bbox=bbox)
        except Exception:  # noqa: BLE001 — una pieza ilegible no rompe el lint
            continue
        nombre = getattr(feat, "name", None) or fid
        fallos += [f"{nombre} ({comp.ref}): {m}" for m in malos]
    if not fallos:
        return []
    ejemplo = "; ".join(fallos[:_MAX_EJEMPLOS]) + ("…" if len(fallos) > _MAX_EJEMPLOS else "")
    return [_check(
        "pre-entrega · asiento fuera de la zona plana", "aviso",
        f"{len(fallos)} taladro(s) en perfil abierto cuyo asiento pisa el acuerdo del perfil "
        f"real (el modelo es prismático): {ejemplo}.",
        "Lleva el taladro hacia el centro del alma (o lejos del talón del ángulo), usa un perno "
        "o arandela menor, o un perfil más alto; si debe quedar ahí, arandela biselada o calza.",
    )]
