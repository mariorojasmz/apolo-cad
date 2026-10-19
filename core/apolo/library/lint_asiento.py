"""Lint pre-entrega «asiento fuera de la zona plana» (plan perfiles-con-acuerdo, D2).

Un taladro en un perfil abierto cuyo asiento (el propio agujero, o la cabeza/tuerca/arandela
coaxial) pisa el acuerdo r1 del perfil real no asienta, aunque el modelo prismático lo dé por
bueno (la piloto del proyecto 2: ejes a 20 mm del canto de un UPN-100, cuya zona plana
empieza a ~18). La geometría de norma vive en `acuerdos.py`.

Puro como `lints.py`: recibe la escena y el catálogo, nunca un `Document`. Los taladros se
leen de la GEOMETRÍA (caras cilíndricas del perfil), no de los comandos: así cubre
`drill_hole` (por punto o por cara), `join_bolted` (que corta sin `drill_hole`) y cualquier
otra vía, con las `=expresiones` ya resueltas por el regenerate. Sólo lee perfiles con ejes
paralelos a los del mundo (bbox = sección × largo); uno girado en ángulo no recto se salta.
"""

from __future__ import annotations

import math

from .acuerdos import inicio_zona_plana_alma, zona_plana_ala_angulo

# tolerancias de lectura de la geometría (mm)
_TOL_DIM = 0.5     # una cota del bbox «es» h/b/leg del catálogo
_TOL_EJE = 1.0     # un herraje está EN el eje del taladro
_HOLGURA = 0.05    # un asiento que sale de la zona plana por menos que esto no avisa
_MAX_EJEMPLOS = 6


def _bbox(shape):
    bb = shape.bounding_box()
    return (bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)


def _agujeros(shape) -> list[tuple[int, tuple, float]]:
    """Taladros del perfil: caras cilíndricas con eje paralelo a un eje del mundo, agrupadas
    por recta (un caladrillo o una cara partida por la costura son el MISMO agujero; vale el
    radio mayor). Devuelve [(índice del eje, punto del eje, radio)]."""
    from build123d import GeomType
    from OCP.BRepAdaptor import BRepAdaptor_Surface

    rectas: list[list] = []
    for face in shape.faces():
        if face.geom_type != GeomType.CYLINDER:
            continue
        cyl = BRepAdaptor_Surface(face.wrapped).Cylinder()
        d = cyl.Axis().Direction()
        comp = (abs(d.X()), abs(d.Y()), abs(d.Z()))
        k = max(range(3), key=lambda i: comp[i])
        if comp[k] < 0.999:
            continue  # eje oblicuo: no es un taladro de los que este lint sabe leer
        loc = cyl.Axis().Location()
        p = (loc.X(), loc.Y(), loc.Z())
        r = cyl.Radius()
        for recta in rectas:
            if recta[0] == k and all(abs(recta[1][i] - p[i]) < 0.05 for i in range(3) if i != k):
                recta[2] = max(recta[2], r)
                break
        else:
            rectas.append([k, p, r])
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


def _radio_asiento(k, p, r, herrajes, caja) -> tuple[float, bool]:
    """Radio del asiento de un taladro: el mayor entre el agujero y el herraje COAXIAL que toca
    el perfil (radio = media cota menor perpendicular al eje: entrecaras de un hexágono, Ø de
    una arandela). Devuelve (radio, ¿lo fija un herraje?)."""
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


def _asignar(dims, objetivos) -> tuple | None:
    """Índices de eje cuyo largo coincide con cada objetivo (en orden), o None si no hay una
    asignación ÚNICA (p. ej. un recorte de UPN-100 de 100 mm: h y L no se distinguen)."""
    from itertools import permutations

    sols = {perm[:len(objetivos)] for perm in permutations(range(3))
            if all(abs(dims[perm[j]] - v) < _TOL_DIM for j, v in enumerate(objetivos))}
    return sols.pop() if len(sols) == 1 else None


def _fallos_alma(shape, specs, herrajes) -> list[str]:
    s = inicio_zona_plana_alma(specs)
    lo, hi = _bbox(shape)
    dims = [hi[i] - lo[i] for i in range(3)]
    asig = _asignar(dims, (float(specs["h"]), float(specs["b"])))
    if asig is None:
        return []
    i_h, i_b = asig
    out = []
    for k, p, r in _agujeros(shape):
        if k != i_b:
            continue  # taladro en el ala o a lo largo: no asienta en el alma
        rho, hw = _radio_asiento(k, p, r, herrajes, (lo, hi))
        e = min(p[i_h] - lo[i_h], hi[i_h] - p[i_h])
        minimo = s + rho
        if e < minimo - _HOLGURA:
            out.append(f"Ø{2 * r:g} con eje a {e:.1f} mm del canto del ala; mínimo {minimo:.1f} "
                       f"(zona plana del alma desde {s:.1f} + radio de asiento {rho:g}"
                       f"{' de la cabeza/tuerca/arandela' if hw else ''})")
    return out


def _fallos_angulo(shape, specs, herrajes) -> list[str]:
    from build123d import CenterOf

    t_r1, fin = zona_plana_ala_angulo(specs)
    leg = float(specs["leg"])
    lo, hi = _bbox(shape)
    dims = [hi[i] - lo[i] for i in range(3)]
    c = shape.center(CenterOf.MASS)
    off = [(c.X, c.Y, c.Z)[i] - (lo[i] + hi[i]) / 2.0 for i in range(3)]
    # el largo es el eje sin desfase del centroide (las dos alas desplazan el centroide hacia
    # el talón en sus dos direcciones): distingue el largo aunque mida lo mismo que el ala
    i_l = min(range(3), key=lambda i: abs(off[i]))
    alas = [i for i in range(3) if i != i_l]
    if any(abs(dims[i] - leg) >= _TOL_DIM for i in alas) or any(abs(off[i]) < 0.5 for i in alas):
        return []
    out = []
    for k, p, r in _agujeros(shape):
        if k not in alas:
            continue
        j = alas[0] if k == alas[1] else alas[1]  # dirección a lo ANCHO del ala taladrada
        talon = lo[j] if off[j] < 0 else hi[j]
        e = abs(p[j] - talon)
        rho, hw = _radio_asiento(k, p, r, herrajes, (lo, hi))
        asiento = f"radio de asiento {rho:g}{' de la cabeza/tuerca/arandela' if hw else ''}"
        if e - rho < t_r1 - _HOLGURA:
            out.append(f"Ø{2 * r:g} con eje a {e:.1f} mm del talón; mínimo {t_r1 + rho:.1f} "
                       f"(zona plana del ala desde t + r1 = {t_r1:g} + {asiento})")
        elif e + rho > fin + _HOLGURA:
            out.append(f"Ø{2 * r:g} con eje a {e:.1f} mm del talón; máximo {fin - rho:.1f} "
                       f"(zona plana del ala hasta leg − r2 = {fin:g} − {asiento})")
    return out


def asiento_zona_plana_lint(scene, catalog) -> list[dict]:
    """AVISO por cada perfil abierto de catálogo (UPN, IPE, L con r1 en sus specs) con algún
    taladro cuyo asiento sale de la zona plana del alma (U/I) o del ala (L). Roscados y ciegos
    también cuentan: el plan no los exime y lo que asienta sobre ellos (la pieza apretada, la
    cabeza) pisa el mismo acuerdo. Un perfil girado en ángulo no recto o con cotas ambiguas se
    SALTA (no se adivina). Defensivo: una pieza ilegible jamás tumba el lint."""
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
            if "leg" in comp.specs:
                malos = _fallos_angulo(feat.shape, comp.specs, herrajes)
            else:
                malos = _fallos_alma(feat.shape, comp.specs, herrajes)
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
