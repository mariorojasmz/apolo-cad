"""Lints PRE-ENTREGA (V7.2b, frente C): comprobaciones baratas de MODELO que un
despacho competente haría antes de soltar los planos. No son cálculo estructural
(eso vive en `engineering/report.py`) sino olvidos de MODELADO que delatan un
paquete a medio hacer: un barreno pasante sin su perno, una pieza que no está ni
agrupada ni unida a nada (flotaría). Ambos defectos aparecieron en el benchmark de
la faja 38 (5 pernos faltantes, la pieza `c704` suelta) y estos lints los habrían
cazado ANTES.

Función PURA estilo `verify.py`/`report.py`: recibe dicts (scene/commands/
fasteners/grounds/joints/mates), nunca un `Document`. Devuelve reglas en el mismo
formato que `_check` ({regla, estado, detalle, recomendacion?}); lista vacía = sano.
"""

from __future__ import annotations

import math
import re

from apolo.kernel.shapes import is_surface

from .checks import HARDWARE_CATS
from .rules import _check

# barrenos de PASO en rango de perno estructural (M6→Ø6.5 … M20→Ø22, serie media)
_HOLE_MIN_MM, _HOLE_MAX_MM = 7.0, 22.0
_AXIS_VEC = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
# tornillería MODELADA a-medida (no catálogo): un perno hecho a mano lleva el rol en el
# nombre — un barreno con un perno así NO está «sin perno» (falso positivo en la faja 38).
# `s?` cubre plurales («pernos») y «tornillería» va aparte: la c704 del 38 se llama
# «Tornillería ménsula soporte motor» y el \b de «tornillo» no la muerde (brecha 1).
_BOLT_NAME_RE = re.compile(r"\b(perno|tornillo|tuerca|bulón|bulon|esp[aá]rrago|allen|"
                           r"bolt|screw|stud|nut)s?\b|torniller[ií]a", re.I)


def _is_bolt(feat, catalog) -> bool:
    """¿La pieza es tornillería (catálogo o modelada a-medida por su nombre/rol)?"""
    comp = catalog.get(getattr(feat, "component", None) or "")
    if comp is not None and comp.category in HARDWARE_CATS:
        return True
    return bool(_BOLT_NAME_RE.search(getattr(feat, "name", "") or ""))


def _bbox_center(feat) -> tuple[float, float, float] | None:
    try:
        bb = feat.shape.bounding_box()
        return ((bb.min.X + bb.max.X) / 2.0, (bb.min.Y + bb.max.Y) / 2.0,
                (bb.min.Z + bb.max.Z) / 2.0)
    except Exception:
        return None


def _perp_dist(c, p0, u) -> float:
    """Distancia del punto `c` a la recta (p0, dirección unitaria `u`)."""
    d = (c[0] - p0[0], c[1] - p0[1], c[2] - p0[2])
    proj = d[0] * u[0] + d[1] * u[1] + d[2] * u[2]
    perp = (d[0] - proj * u[0], d[1] - proj * u[1], d[2] - proj * u[2])
    return math.sqrt(perp[0] ** 2 + perp[1] ** 2 + perp[2] ** 2)


def _bolt_lines(scene, catalog) -> list[tuple]:
    """Centros (mundo) de la tornillería presente (catálogo O a-medida por nombre): un
    perno/tuerca en el eje de un barreno lo deja a distancia perpendicular ~0 de la recta.
    La tornillería puede venir en COMPOUND (c704 del 38: 10 pernos en UN feature) — el
    centro del conjunto no cae en el eje de NINGÚN barreno (16 falsos positivos en la
    auditoría de la brecha 1) → se expande POR SÓLIDO (cada perno da su centro)."""
    out = []
    for feat in scene.values():
        if not getattr(feat, "visible", True):
            continue
        if not _is_bolt(feat, catalog):
            continue
        solids = []
        try:
            solids = list(feat.shape.solids())
        except Exception:
            solids = []
        if len(solids) > 1:
            for s in solids:
                try:
                    bb = s.bounding_box()
                    out.append(((bb.min.X + bb.max.X) / 2.0, (bb.min.Y + bb.max.Y) / 2.0,
                                (bb.min.Z + bb.max.Z) / 2.0))
                except Exception:
                    continue
        else:
            c = _bbox_center(feat)
            if c is not None:
                out.append(c)
    return out


def _hole_bolt_lint(scene, commands, catalog, resolve) -> list[dict]:
    bolts = _bolt_lines(scene, catalog)
    sin_perno: list[str] = []
    for cmd in commands:
        if cmd.get("type") != "drill_hole":
            continue
        try:
            # el modelo puede tener Ø/posición/profundidad por "=expresión" → resolver
            # contra las variables (inyectado); todo el cuerpo es defensivo: un comando
            # raro se SALTA, jamás tumba el lint (ni /api/checks)
            p = resolve(cmd.get("params", {}) or {})
            if p.get("thread"):
                continue  # roscado = para machuelo, no perno pasante
            dia = float(p.get("diameter", 0))
            depth = float(p.get("depth", 0) or 0)
            if depth > 0:
                continue  # taladro CIEGO: no es de paso de perno
            if not (_HOLE_MIN_MM <= dia <= _HOLE_MAX_MM):
                continue
            feat = scene.get(cmd.get("params", {}).get("feature"))
            if feat is None or not getattr(feat, "visible", True):
                continue
            pos = p.get("position") or {}
            p0 = (float(pos.get("x", 0)), float(pos.get("y", 0)), float(pos.get("z", 0)))
            # el eje puede venir con signo ("-y"): para una RECTA el sentido no importa —
            # sin el strip, "-y" caía al default z y medía contra la recta equivocada
            u = _AXIS_VEC.get(str(p.get("axis", "z")).lstrip("+-"), _AXIS_VEC["z"])
            tol = max(dia, 6.0)
            if any(_perp_dist(c, p0, u) <= tol for c in bolts):
                continue
            nombre = getattr(feat, "name", None) or cmd.get("params", {}).get("feature")
            sin_perno.append(f"{nombre} (Ø{dia:g} en x≈{p0[0]:.0f},y≈{p0[1]:.0f},z≈{p0[2]:.0f})")
        except Exception:  # noqa: BLE001 — un comando no resoluble no rompe el lint
            continue
    if not sin_perno:
        return []
    ejemplo = "; ".join(sin_perno[:6]) + ("…" if len(sin_perno) > 6 else "")
    return [_check(
        "pre-entrega · barreno sin perno", "aviso",
        f"{len(sin_perno)} barreno(s) de paso (Ø{_HOLE_MIN_MM:g}–{_HOLE_MAX_MM:g}) sin "
        f"tornillería en su eje: {ejemplo}.",
        "Inserta el perno/tuerca (o usa join_bolted) — un barreno sin perno es un olvido "
        "de modelado (posición del taladro aproximada a coords. de comando).",
    )]


def _loose_part_lint(scene, fasteners, grounds, joints, mates, catalog) -> list[dict]:
    connected: set = set()
    for j in joints.values():
        connected.add(j.get("parent"))
        connected.add(j.get("child"))
    for m in mates.values():
        connected.add(m.get("feature_a"))
        connected.add(m.get("feature_b"))
    for f in fasteners.values():
        connected.add(f.get("a"))
        connected.add(f.get("b"))
    for g in grounds.values():
        connected.add(g.get("feature"))

    sueltas: list[str] = []
    for fid, feat in scene.items():
        if not getattr(feat, "visible", True) or getattr(feat, "is_guide", False):
            continue
        if getattr(feat, "group", None) or fid in connected:
            continue
        if _is_bolt(feat, catalog):
            continue  # tornillería (catálogo o a-medida): la cubre su fasten/super-comando
        try:
            if is_surface(feat.shape):
                continue  # superficie de construcción: fuera de BOM/masa/unión
        except Exception:
            pass
        sueltas.append(getattr(feat, "name", None) or fid)
    if not sueltas:
        return []
    ejemplo = ", ".join(sueltas[:6]) + ("…" if len(sueltas) > 6 else "")
    return [_check(
        "pre-entrega · pieza sin grupo ni unión", "aviso",
        f"{len(sueltas)} pieza(s) sin grupo NI unión declarada ({ejemplo}) — flotarían "
        "(no tienen camino de carga a tierra ni pertenecen a un sub-ensamblaje).",
        "Agrúpalas (create_group), decláralas ground/fasten, o quítalas si son escombro.",
    )]


def predelivery_lints(scene, commands, fasteners, grounds, joints, mates, *,
                      catalog=None, resolve=None) -> list[dict]:
    """Lints pre-entrega: barrenos sin perno + piezas sin grupo ni unión. Devuelve una
    lista de avisos (formato `_check`); vacía si el modelo está sano. `resolve(params)`
    (inyectado por la API) sustituye las "=expresión" de los comandos por su valor —
    los modelos paramétricos posicionan los barrenos con expresiones; sin resolver
    (default identidad) un barreno parametrizado simplemente se salta."""
    from .catalog import CATALOG

    catalog = catalog if catalog is not None else CATALOG
    resolve = resolve or (lambda p: p)
    if not scene:
        return []
    out: list[dict] = []
    out += _hole_bolt_lint(scene, commands or [], catalog, resolve)
    out += _loose_part_lint(scene, fasteners, grounds, joints, mates, catalog)
    return out
