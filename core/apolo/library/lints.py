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
_BOLT_NAME_RE = re.compile(r"\b(perno|tornillo|tuerca|bulón|bulon|esp[aá]rrago|allen|tirafondo|"
                           r"bolt|screw|stud|nut)s?\b|torniller[ií]a", re.I)
# lo que sólo MENCIONA la tornillería no es tornillería: «Eje fijo de cola Ø25 g6 (roscado p/
# perno)» es un EJE que recibe el perno del tensor (plan puerta-de-publicacion D2: era el «1
# fijador no evaluado» de la faja #1). Se quitan las menciones «p/ perno», «para perno(s)»…
# y un rol que EMPIEZA por eje/árbol/shaft (o por buje/casquillo/separador: «Buje pasante de perno de
# soplador» es el tubo que recibe el perno, no un perno) no es tornillería aunque nombre un
# perno. «con» también
# (F3c de puerta-sin-sobrediseno): «Tope elástico de poliuretano Ø60x40 con espárrago M10 (compra)»
# es un tope que trae su espárrago, no tornillería suelta.
_MENCION_RE = re.compile(r"(?<!\w)(p/|para|por|con)\s+(el\s+|los\s+|un\s+|su\s+)?"
                         r"(perno|tornillo|bulón|bulon|esp[aá]rrago|allen)s?\b", re.I)
#: un CONJUNTO de tornillería: la palabra que encabeza es el juego, no la pieza
_JUEGO_RE = re.compile(r"^(juegos?|kits?|sets?|conjuntos?|lotes?)\s+(de\s+)?", re.I)
_EJE_ROL_RE = re.compile(r"^\s*(eje|árbol|arbol|shaft|bujes?|casquillos?|manguitos?|separador(es)?|"
                         r"espaciador(es)?|distanciador(es)?|bushings?|spacers?|sleeves?)\b", re.I)


def es_nombre_de_tornilleria(nombre: str | None) -> bool:
    """¿El NOMBRE dice que la pieza ES tornillería (no que la menciona)? Por su ROL: la palabra
    de tornillería ENCABEZA el rol (plan puerta-fuera-de-catalogo D3). «Arandela de perno…»,
    «Taco … para tornillo» o «Pie nivelador higiénico M10 (compra: … espárrago M10x60 …)» nombran
    tornillería sin serlo: el pie es un apoyo (lo saltaba `installation_data`)."""
    from .materials import piece_role, sin_especificacion

    # lo que la ESPECIFICACIÓN lista no es lo que la pieza es: «Pie nivelador · AISI 304,
    # espárrago M12x20 A2, …» es un pie, no un espárrago (F8 de hallazgos-del-revisor)
    rol = piece_role(sin_especificacion(nombre))
    if _EJE_ROL_RE.match(rol):
        return False
    rol = _JUEGO_RE.sub("", _MENCION_RE.sub(" ", rol).lstrip())  # «Juego de pernos M10» lo es
    return bool(_BOLT_NAME_RE.match(rol))


def _is_bolt(feat, catalog) -> bool:
    """¿La pieza es tornillería (catálogo o modelada a-medida por su nombre/rol)?"""
    comp = catalog.get(getattr(feat, "component", None) or "")
    if comp is not None and (comp.category in HARDWARE_CATS or comp.category == "arandelas"):
        return True  # la arandela de catálogo (D5 de bom-de-compra-fiel) es herraje, no pieza
    return es_nombre_de_tornilleria(getattr(feat, "name", "") or "")


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


def _de_union_declarada(fid, p0, u, dia, declarados) -> bool:
    """¿El taladro (recta p0 + t·u, Ø `dia`) es uno de los agujeros que `union.agujeros` atribuye
    a un fasten perno DECLARADO de su pieza (`declarados[fid]`: {p, eje} de la geometría)? Su eje
    paralelo y dentro del radio del taladro: es el mismo agujero. De un COLISO ({p0, p1}: los
    centros de sus extremos) basta que el taladro caiga sobre su tramo: el extremo redondo de un
    coliso hecho con dos `drill_hole` es ese coliso."""
    from .calidad.agujeros import distancia_a_tramo

    for a in declarados.get(fid) or ():
        try:
            if abs(abs(sum(a["eje"][i] * u[i] for i in range(3))) - 1.0) > 1e-3:
                continue
            if "p0" in a:
                if distancia_a_tramo(p0, a["p0"], a["p1"], u) <= dia / 2.0:
                    return True
                continue
            if _perp_dist(a["p"], p0, u) <= dia / 2.0:
                return True
        except Exception:  # noqa: BLE001 — un insumo raro no cubre nada
            continue
    return False


def _hole_bolt_lint(scene, commands, catalog, resolve, agujeros_declarados=None) -> list[dict]:
    bolts = _bolt_lines(scene, catalog)
    sin_perno: list[tuple] = []
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
            fid = cmd.get("params", {}).get("feature")
            nombre = getattr(feat, "name", None) or fid
            sin_perno.append((fid, p0, u, dia, f"{nombre} (Ø{dia:g} en x≈{p0[0]:.0f},"
                                               f"y≈{p0[1]:.0f},z≈{p0[2]:.0f})"))
        except Exception:  # noqa: BLE001 — un comando no resoluble no rompe el lint
            continue
    if sin_perno and agujeros_declarados is not None:
        # la tornillería que un fasten perno DECLARA (en su nota, sin modelar) también es «perno
        # en su eje»: los agujeros que `union.agujeros` le atribuye (perezoso: sólo si hace falta)
        try:
            declarados = agujeros_declarados() or {}
        except Exception:  # noqa: BLE001 — sin la medida, el lint de siempre
            declarados = {}
        sin_perno = [s for s in sin_perno if not _de_union_declarada(*s[:4], declarados)]
    sin_perno = [s[4] for s in sin_perno]
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
                      catalog=None, resolve=None, material_vertical=None,
                      agujeros_declarados=None) -> list[dict]:
    """Lints pre-entrega: barrenos sin perno + piezas sin grupo ni unión + asiento fuera de
    la zona plana de un perfil abierto (`lint_asiento.py`) + soldadura entre materiales que no
    se sueldan (`lint_soldadura.py`, ERROR: bloquea la puerta). Devuelve una
    lista de reglas (formato `_check`); vacía si el modelo está sano. `resolve(params)`
    (inyectado por la API) sustituye las "=expresión" de los comandos por su valor —
    los modelos paramétricos posicionan los barrenos con expresiones; sin resolver
    (default identidad) un barreno parametrizado simplemente se salta. `material_vertical` =
    `Document.default_material()` (sin él, la soldadura asume acero lo no reconocido).
    `agujeros_declarados()` (inyectado: `services/calidad_agujeros.agujeros_atribuidos`) da
    fid → los agujeros que `union.agujeros` atribuye a un fasten perno declarado: esos tienen su
    perno aunque no esté modelado; se llama sólo si queda algún barreno sin perno."""
    from .catalog import CATALOG
    from .lint_asiento import asiento_zona_plana_lint
    from .lint_soldadura import soldadura_imposible_lint

    catalog = catalog if catalog is not None else CATALOG
    resolve = resolve or (lambda p: p)
    if not scene:
        return []
    out: list[dict] = []
    out += _hole_bolt_lint(scene, commands or [], catalog, resolve, agujeros_declarados)
    out += _loose_part_lint(scene, fasteners, grounds, joints, mates, catalog)
    out += asiento_zona_plana_lint(scene, catalog)
    out += soldadura_imposible_lint(scene, fasteners or {}, catalog, default=material_vertical)
    return out
