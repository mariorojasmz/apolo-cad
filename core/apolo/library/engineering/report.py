"""Chequeo estructural UNIVERSAL del ensamblaje (Frente A, Fase 4).

A diferencia de `rules.conveyor_engineering_check` (que exige una faja y una
carga), estas reglas aplican a CUALQUIER ensamblaje con uniones declaradas:
- uniones apernadas (utilización del perno vs su capacidad ISO 898-1),
- cordones de soldadura (tensión en garganta vs 0.6·σy del material base),
- vida L10 de rodamientos/chumaceras (C_kN del catálogo),
- pandeo de Euler de las patas,
- estabilidad al vuelco (COG vs huella de apoyo).

La CARGA de cada unión sale del grafo de conectividad (`hanging_load_kg`:
masa que pierde tierra al quitar la arista) — honesto: una unión DIMENSIONADA en
camino redundante se reporta "ok" con nota (la redundancia es favorable y no es
accionable; el reparto exacto exigiría FEA), nunca con un número inventado. Mismo
formato de regla que rules.py ({regla, estado, detalle, recomendacion?, calc?}).

Orquestador puro: recibe dicts (scene/fasteners/grounds/joints/mates), nunca
`Document` — frontera library ⟂ doc.
"""

from __future__ import annotations

import math

from ..materials import resolve_material, yield_strength, young_modulus
from ..rules import _check, _LEG_RE, _parse_diam, _parse_wall, _SECTION_RE
from .bearings import L10_MIN_H, L10_TARGET_H, l10_hours
from .bolts import TENSILE_AREA_MM2, bolt_shear_capacity_n
from .buckling import BUCKLING_FS, euler_critical_load_n, rect_tube_min_inertia_mm4
from .loads import hanging_load_kg
from .mass import feature_mass, scene_mass_properties
from .stability import convex_hull_2d, hull_margin_mm
from .welds import weld_allowable_mpa, weld_throat_stress_mpa

G = 9.81

# categorías de catálogo con rodamiento interno (llevan C_kN en specs)
_BEARING_CATS = {"rodamientos", "chumaceras"}


def _name(f) -> str:
    return (getattr(f, "name", "") or "").lower()


def _weaker_yield(fa, fb, catalog) -> tuple[float, str]:
    """σy del material BASE más débil de la unión (para soldadura)."""
    ma = resolve_material(fa, catalog)
    mb = resolve_material(fb, catalog)
    ya, yb = yield_strength(ma), yield_strength(mb)
    return (ya, ma) if ya <= yb else (yb, mb)


def _fastener_checks(scene, graph, masses, fasteners, catalog) -> list[dict]:
    checks: list[dict] = []
    # varios `fasten` tipo perno sobre el MISMO par de piezas = UNA unión con los
    # pernos combinados (en el grafo colapsan a una arista): se suman las cantidades
    from collections import defaultdict

    pair_bolts: dict[frozenset, int] = defaultdict(int)
    for f in fasteners.values():
        if f.get("kind", "perno") == "perno" and f.get("size"):
            pair_bolts[frozenset((f.get("a"), f.get("b")))] += int(f.get("qty") or 1)

    # las uniones SIN dimensionar se agregan en UNA regla-resumen por tipo (una faja
    # real declara >100 uniones; un aviso por cada una ahogaría el reporte)
    sin_size: list[str] = []
    sin_cordon: list[str] = []

    for f in fasteners.values():
        kind = f.get("kind", "perno")
        a, b = f.get("a"), f.get("b")
        if a not in scene or b not in scene or kind not in ("perno", "soldadura"):
            continue
        label = f"{f.get('name')} ({scene[a].name} ↔ {scene[b].name})"
        load_kg = hanging_load_kg(graph, masses, a, b)

        if kind == "perno":
            size, qty = f.get("size"), int(f.get("qty") or 1)
            if not size:
                sin_size.append(str(f.get("name")))
                continue
            if size.upper() not in TENSILE_AREA_MM2:
                checks.append(_check(
                    f"unión apernada · {f.get('name')}", "aviso",
                    f"{label}: métrica '{size}' fuera de tabla (M6–M24).",
                ))
                continue
            if load_kg is None:
                # la redundancia es FAVORABLE estructuralmente (camino de carga
                # múltiple) y no es accionable — un aviso debe serlo
                checks.append(_check(
                    f"unión apernada · {f.get('name')}", "ok",
                    f"{label}: {qty}× {size} en camino de carga redundante — favorable "
                    "estructuralmente; el reparto no es determinable sin FEA, se asume "
                    "compartida entre caminos.",
                ))
                continue
            load_n = load_kg * G
            cap = bolt_shear_capacity_n(size, "8.8")
            qty_par = max(pair_bolts[frozenset((a, b))], qty)
            util = load_n / (qty_par * cap) if cap > 0 else float("inf")
            extra = f" ({qty_par} pernos totales en el par)" if qty_par > qty else ""
            calc = {
                "titulo": f"Unión apernada {f.get('name')}",
                "entradas": {"masa colgante": f"{load_kg:.1f} kg (grafo de conectividad)",
                             "carga": f"{load_n:.0f} N", "pernos": f"{qty_par}× {size} 8.8{extra}",
                             "capacidad/ud": f"{cap:.0f} N (0.6·Rm·As/1.25, EN 1993-1-8)"},
                "formula": "u = F / (n · Fv)",
                "sustitucion": f"u = {load_n:.0f} / ({qty_par}·{cap:.0f})",
                "resultado": f"u = {util:.2f} ({util * 100:.0f}% de la capacidad a cortante)",
                "criterio": "u ≤ 0.7 holgado · 0.7–1.0 justo · >1.0 sobrecargada",
                "fs": round(1.0 / util, 2) if util > 0 else None,
                "norma": "EN 1993-1-8 · ISO 898-1 (capacidad a cortante del perno)",
            }
            det = (f"{label}: {load_kg:.1f} kg cuelgan de {qty_par}× {size} → "
                   f"utilización {util * 100:.0f}% a cortante.")
            if util > 1.0:
                checks.append(_check(
                    f"unión apernada · {f.get('name')}", "error", det,
                    "Sube la métrica, añade pernos o reparte la carga por otro camino.",
                    calc=calc,
                ))
            elif util > 0.7:
                checks.append(_check(
                    f"unión apernada · {f.get('name')}", "aviso", det,
                    "Margen justo: considera un perno más o una métrica mayor.",
                    calc=calc,
                ))
            else:
                checks.append(_check(f"unión apernada · {f.get('name')}", "ok", det, calc=calc))

        else:  # soldadura
            throat, length = f.get("throat_mm"), f.get("length_mm")
            if not throat or not length:
                sin_cordon.append(str(f.get("name")))
                continue
            if load_kg is None:
                checks.append(_check(
                    f"soldadura · {f.get('name')}", "ok",
                    f"{label}: cordón a={throat:g}/L={length:g} en camino de carga "
                    "redundante — favorable estructuralmente; reparto no determinable "
                    "sin FEA, se asume compartido.",
                ))
                continue
            load_n = load_kg * G
            tau = weld_throat_stress_mpa(load_n, throat, length)
            y_base, mat = _weaker_yield(scene[a], scene[b], catalog)
            allow = weld_allowable_mpa(y_base)
            calc = {
                "titulo": f"Soldadura {f.get('name')}",
                "entradas": {"masa colgante": f"{load_kg:.1f} kg", "carga": f"{load_n:.0f} N",
                             "garganta a": f"{throat:g} mm", "longitud": f"{length:g} mm",
                             "material base": f"{mat} (σy {y_base:.0f} MPa)"},
                "formula": "τ = F / (a·L)",
                "sustitucion": f"τ = {load_n:.0f} / ({throat:g}·{length:g})",
                "resultado": f"τ = {tau:.1f} MPa",
                "criterio": f"τ ≤ 0.6·σy = {allow:.0f} MPa",
                "fs": round(allow / tau, 2) if tau > 0 else None,
                "norma": "EN 1993-1-8 (tensión en la garganta del cordón)",
            }
            det = f"{label}: τ = {tau:.1f} MPa en la garganta vs {allow:.0f} MPa admisibles."
            if tau > allow:
                checks.append(_check(
                    f"soldadura · {f.get('name')}", "error", det,
                    "Aumenta la garganta o la longitud de cordón.", calc=calc,
                ))
            elif tau > 0.7 * allow:
                checks.append(_check(
                    f"soldadura · {f.get('name')}", "aviso", det,
                    "Margen justo en el cordón.", calc=calc,
                ))
            else:
                checks.append(_check(f"soldadura · {f.get('name')}", "ok", det, calc=calc))

    if sin_size:
        ejemplo = ", ".join(sin_size[:5]) + ("…" if len(sin_size) > 5 else "")
        checks.append(_check(
            "uniones apernadas sin dimensionar", "aviso",
            f"{len(sin_size)} unión(es) apernada(s) declaradas sin métrica ({ejemplo}) — "
            "no verificables.",
            "Declara size ('M10') y qty en el fasten de las uniones que cargan peso.",
        ))
    if sin_cordon:
        ejemplo = ", ".join(sin_cordon[:5]) + ("…" if len(sin_cordon) > 5 else "")
        checks.append(_check(
            "soldaduras sin dimensionar", "aviso",
            f"{len(sin_cordon)} soldadura(s) declaradas sin garganta/longitud ({ejemplo}) — "
            "no verificables.",
            "Declara throat_mm (garganta a = 0.707·cateto) y length_mm en las que cargan peso.",
        ))
    return checks


def _bearing_checks(scene, catalog, carga_kg: float, rpm: float | None,
                    belt_radial_n: float | None = None) -> list[dict]:
    from ..catalog import CATALOG

    catalog = catalog if catalog is not None else CATALOG
    bearings = []
    for fid, f in scene.items():
        if not getattr(f, "visible", True):
            continue
        comp = catalog.get(getattr(f, "component", None) or "")
        if comp is not None and comp.category in _BEARING_CATS and (comp.specs or {}).get("C_kN"):
            bearings.append((fid, f, comp))
    if not bearings:
        return []
    if not rpm:
        return [_check(
            "vida L10 de rodamientos", "aviso",
            f"Hay {len(bearings)} rodamiento(s) con C_kN pero sin rpm de giro conocidas — "
            "L10 no calculable.",
            "Pasa rpm (o declara rpm_salida en las variables del proyecto).",
        )]
    checks: list[dict] = []
    n = len(bearings)
    if belt_radial_n and belt_radial_n > 0:
        # en una faja la carga radial DOMINANTE del rodamiento es la TENSIÓN DE BANDA
        # (T1+T2)/2 por eje — el peso del producto lo lleva la mesa/cama, no los
        # rodamientos. Ignorarla daba una L10 fantasiosa (cientos de millones de horas).
        p_kn = belt_radial_n / 1000.0
        carga_P_txt = (f"{p_kn:.3f} kN (= (T1+T2)/2 de la banda, repartida entre los 2 "
                       f"rodamientos del eje del tambor)")
        det_reparto = "carga = tensión de banda (T1+T2)/2 por eje"
    else:
        p_kn = max(carga_kg, 0.0) * G / 1000.0 / n  # hipótesis: carga repartida pareja
        carga_P_txt = (f"{p_kn:.3f} kN (= {carga_kg:g} kg / {n} rodamientos — "
                       f"hipótesis reparto parejo)")
        det_reparto = f"{n} rodamiento(s), reparto parejo — estimación"
    worst = None
    for fid, f, comp in bearings:
        c_kn = float(comp.specs["C_kN"])
        hours = l10_hours(c_kn, p_kn, rpm)
        if worst is None or hours < worst[3]:
            worst = (fid, f, comp, hours, c_kn)
    fid, f, comp, hours, c_kn = worst
    hours_txt = "∞" if math.isinf(hours) else f"{hours:,.0f} h"
    calc = {
        "titulo": "Vida L10 del rodamiento más cargado",
        "entradas": {"rodamiento": f"{comp.ref} (C = {c_kn:g} kN)",
                     "carga P": carga_P_txt,
                     "velocidad": f"{rpm:g} rpm"},
        "formula": "L10h = (C/P)³ · 10⁶ / (60·n)",
        "sustitucion": f"L10h = ({c_kn:g}/{p_kn:.3f})³ · 10⁶ / (60·{rpm:g})",
        "resultado": f"L10 = {hours_txt}",
        "criterio": f"≥ {L10_TARGET_H:,.0f} h objetivo (≥ {L10_MIN_H:,.0f} h mínimo)",
        "fs": None if math.isinf(hours) else round(hours / L10_TARGET_H, 2),
        "norma": "ISO 281 (vida nominal L10 del rodamiento)",
    }
    det = (f"{comp.ref} ({f.name}): L10 ≈ {hours_txt} con P = {p_kn:.3f} kN a {rpm:g} rpm "
           f"({det_reparto}).")
    if hours < L10_MIN_H:
        checks.append(_check(
            "vida L10 de rodamientos", "error", det,
            "Usa un rodamiento de mayor capacidad (serie 63xx) o reparte la carga.", calc=calc,
        ))
    elif hours < L10_TARGET_H:
        checks.append(_check(
            "vida L10 de rodamientos", "aviso", det,
            "Por debajo de las 20 000 h objetivo para servicio industrial.", calc=calc,
        ))
    else:
        checks.append(_check("vida L10 de rodamientos", "ok", det, calc=calc))
    return checks


def _buckling_checks(scene, masses, catalog, carga_kg: float) -> list[dict]:
    # una PATA de verdad lleva el rol "pata" al inicio del nombre (convención rol-primero):
    # así no cuentan piezas que solo la MENCIONAN ("Ménsula … → larguero + pata", "Disco …
    # a la pata"), que inflaban el reparto de carga (n patas). "zapata" no empieza por "pata".
    candidatas = [(fid, f) for fid, f in scene.items()
                  if getattr(f, "visible", True) and _LEG_RE.match(_name(f))]
    if not candidatas:
        return []
    # solo las COLUMNAS verticales (largo ≥ 50 mm) reparten la carga axial y pandean;
    # las placas/pies que comparten el rol quedan fuera del conteo
    columns = []
    for fid, f in candidatas:
        try:
            bb = f.shape.bounding_box()
        except Exception:
            continue
        w = bb.max.X - bb.min.X
        d = bb.max.Y - bb.min.Y
        length = bb.max.Z - bb.min.Z
        if length < 50:  # placa/pie, no columna
            continue
        columns.append((fid, f, w, d, length))
    if not columns:
        return []
    total_kg = sum(masses.values()) + max(carga_kg, 0.0)
    n = len(columns)
    p_leg = total_kg * G / n
    worst = None
    for fid, f, w, d, length in columns:
        m = _SECTION_RE.search(getattr(f, "name", "") or "")
        if m:
            w, d = float(m.group(1)), float(m.group(2))
        wall = _parse_wall(getattr(f, "name", "")) or 3.0
        inertia = rect_tube_min_inertia_mm4(w, d, wall)
        e_mpa = young_modulus(resolve_material(f, catalog))
        pcr = euler_critical_load_n(e_mpa, inertia, length, k=2.0)
        fs = pcr / p_leg if p_leg > 0 else float("inf")
        if worst is None or fs < worst[2]:
            worst = (fid, f, fs, pcr, w, d, wall, length)
    fid, f, fs, pcr, w, d, wall, length = worst
    calc = {
        "titulo": "Pandeo de la pata más esbelta",
        "entradas": {"pata": f.name, "sección": f"{w:.0f}×{d:.0f}×{wall:g} mm",
                     "longitud": f"{length:.0f} mm", "K": "2.0 (empotrada-libre, conservador)",
                     "carga/pata": f"{p_leg:.0f} N (= {total_kg:.0f} kg / {n} patas)"},
        "formula": "Pcr = π²·E·I / (K·L)²",
        "sustitucion": f"Pcr = π²·E·I_min / (2·{length:.0f})²",
        "resultado": f"Pcr = {pcr:,.0f} N → FS = {fs:.1f}",
        "criterio": f"FS ≥ {BUCKLING_FS:g}",
        "fs": round(fs, 2),
        "norma": "pandeo de Euler (EN 1993-1-1 §6.3 como marco)",
    }
    det = (f"{f.name}: FS de pandeo {fs:.1f} (Pcr {pcr:,.0f} N vs {p_leg:.0f} N/pata; "
           f"K=2 conservador, sección {w:.0f}×{d:.0f}×{wall:g}).")
    if fs < 2.0:
        return [_check("pandeo de patas", "error", det,
                       "Usa una sección mayor o arriostra las patas.", calc=calc)]
    if fs < BUCKLING_FS:
        return [_check("pandeo de patas", "aviso", det,
                       "Margen justo frente a Euler (que ignora imperfecciones).", calc=calc)]
    return [_check("pandeo de patas", "ok", det, calc=calc)]


def _tipping_check(scene, grounds, catalog, carga_kg: float) -> list[dict]:
    footprint: list[tuple[float, float]] = []
    for g in grounds.values():
        f = scene.get(g.get("feature"))
        if f is None:
            continue
        try:
            bb = f.shape.bounding_box()
        except Exception:
            continue
        footprint += [(bb.min.X, bb.min.Y), (bb.max.X, bb.min.Y),
                      (bb.max.X, bb.max.Y), (bb.min.X, bb.max.Y)]
    if not footprint:
        return [_check(
            "estabilidad al vuelco", "aviso",
            "Sin anclajes a tierra declarados — la huella de apoyo es desconocida.",
            "Declara los apoyos con `ground` (o declare_structure) para verificar el vuelco.",
        )]
    hull = convex_hull_2d(footprint)
    props = scene_mass_properties(scene, catalog)
    com = props["total"]["com_mm"]
    margin = hull_margin_mm((com[0], com[1]), hull)
    xs = [p[0] for p in hull]
    ys = [p[1] for p in hull]
    base_min = min(max(xs) - min(xs), max(ys) - min(ys)) if len(hull) >= 2 else 0.0
    need = 0.10 * base_min
    calc = {
        "titulo": "Estabilidad al vuelco",
        "entradas": {"masa total": f"{props['total']['masa_kg']:g} kg (sin producto)",
                     "COG": f"({com[0]:.0f}, {com[1]:.0f}, {com[2]:.0f}) mm",
                     "base de apoyo": f"{len(hull)} vértices, dim. menor {base_min:.0f} mm"},
        "formula": "margen = dist(COG_xy, borde de la base de apoyo)",
        "sustitucion": f"margen({com[0]:.0f}, {com[1]:.0f}) sobre el casco convexo de los apoyos",
        "resultado": f"margen = {margin:.0f} mm",
        "criterio": f"≥ 10% de la base menor = {need:.0f} mm",
        "fs": round(margin / need, 2) if need > 0 else None,
        "norma": "criterio de diseño: equilibrio estático (COG dentro de la huella de apoyo)",
    }
    det = (f"COG a {margin:.0f} mm del borde de la base de apoyo "
           f"(mínimo requerido {need:.0f} mm; producto no incluido).")
    if margin <= 0:
        return [_check("estabilidad al vuelco", "error",
                       f"El COG cae FUERA de la base de apoyo ({margin:.0f} mm) — vuelca.",
                       "Ensancha la base, añade apoyos o reubica el peso.", calc=calc)]
    if margin < need:
        return [_check("estabilidad al vuelco", "aviso", det,
                       "Margen de vuelco justo: ensancha la base o baja el COG.", calc=calc)]
    return [_check("estabilidad al vuelco", "ok", det, calc=calc)]


_SHAFT_FIT_NAME_RE = None  # compilado perezoso


def _fit_checks(scene, fasteners, joints, mates, catalog) -> list[dict]:
    """Asientos ISO 286 (V5.4): detecta pares eje↔rodamiento/chumacera montados
    (fastener ∪ junta ∪ mate concéntrico + Ø nominal coincidente) y verifica el
    ajuste del EJE contra la recomendación por tipo de montaje. Sin fit declarado
    en el nombre del eje → aviso con recomendación (honesto, no error)."""
    import re

    from .fits import SEAT_RECOMMENDATIONS, bearing_seat_check

    global _SHAFT_FIT_NAME_RE
    if _SHAFT_FIT_NAME_RE is None:
        _SHAFT_FIT_NAME_RE = re.compile(r"\b((?:js|[gfhkmnp]))(\d{1,2})\b")

    def bore_of(comp) -> float | None:
        specs = comp.specs or {}
        d = specs.get("d") or specs.get("bore_d")
        try:
            return float(d) if d else None
        except (TypeError, ValueError):
            return None

    def shaft_diam(feat) -> float | None:
        d = _parse_diam(getattr(feat, "name", "") or "")
        if d:
            return d
        try:  # fallback geométrico: eje = dos extensiones menores casi iguales
            bb = feat.shape.bounding_box()
            dims = sorted((bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z))
            if dims[1] > 0 and abs(dims[0] - dims[1]) / dims[1] < 0.05:
                return round(dims[0], 1)
        except Exception:
            pass
        return None

    def shaft_fit(feat) -> str | None:
        name = getattr(feat, "name", "") or ""
        if _parse_diam(name) is None:
            return None  # exigir Ø en el mismo nombre: evita falsos positivos
        m = _SHAFT_FIT_NAME_RE.search(name)
        return f"{m.group(1)}{m.group(2)}" if m else None

    # candidatos: fasteners (a,b) ∪ juntas (parent,child) ∪ mates concéntricos
    edges: list[tuple[str, str]] = [(f["a"], f["b"]) for f in fasteners.values()]
    edges += [(j["parent"], j["child"]) for j in joints.values()]
    edges += [
        (m["feature_a"], m["feature_b"])
        for m in mates.values() if m.get("type") == "concentrico"
    ]

    seen: set[frozenset] = set()
    checks: list[dict] = []
    for a_id, b_id in edges:
        key = frozenset((a_id, b_id))
        if key in seen:
            continue
        fa, fb = scene.get(a_id), scene.get(b_id)
        if fa is None or fb is None:
            continue
        for bearing, shaft in ((fa, fb), (fb, fa)):
            comp = catalog.get(getattr(bearing, "component", None) or "")
            if comp is None or comp.category not in _BEARING_CATS:
                continue
            bore = bore_of(comp)
            if not bore:
                continue
            d = shaft_diam(shaft)
            if d is None or abs(d - bore) > 0.6:
                continue
            seen.add(key)
            # hipótesis de montaje DECLARADA (nunca silenciosa): por categoría y por el
            # ROL del eje. Un eje FIJO (nombre «eje fijo») lleva el anillo interior
            # ESTACIONARIO y la carga rotatoria en el exterior → asiento holgado g6/h6
            # (no k6 de prensado): es el caso del tensor de cola trotadora.
            if comp.category == "chumaceras":
                mount = "chumacera_inserto"
            elif re.search(r"\beje\s+fijo\b|\bfij[oa]\b", getattr(shaft, "name", "") or "", re.I):
                mount = "rodamiento_anillo_fijo"
            else:
                mount = "rodamiento_anillo_giratorio"
            rec = SEAT_RECOMMENDATIONS[mount]
            fit = shaft_fit(shaft)
            regla = f"asiento ISO 286 · {comp.ref}"
            if fit is None:
                checks.append(_check(
                    regla, "aviso",
                    f"{comp.ref} montado en '{shaft.name}' (Ø{bore:g}): el eje no declara "
                    f"ajuste ISO 286 (hipótesis de montaje: {mount.replace('_', ' ')}).",
                    f"Añade la clase al NOMBRE del eje (p. ej. «Ø{bore:g} {rec['tipico']}»); "
                    f"aceptables: {', '.join(sorted(rec['ok']))} — {rec['nota']}.",
                ))
                break
            try:
                seat = bearing_seat_check(bore, fit, mount)
            except KeyError as exc:
                checks.append(_check(regla, "aviso", f"Ajuste '{fit}' no evaluable: {exc}"))
                break
            sh = seat["shaft"]
            calc = {
                "titulo": f"Asiento ISO 286: {comp.ref} en eje Ø{bore:g}",
                "entradas": {
                    "eje": f"Ø{bore:g} {sh['fit']} ({sh['es_um']:+g}/{sh['ei_um']:+g} µm)",
                    "bore": f"Ø{bore:g} +0/−{seat['bore_tol_um']:g} µm (ISO 492 clase Normal)",
                    "montaje": f"{mount.replace('_', ' ')} — {rec['nota']}",
                },
                "formula": "juego = bore − eje",
                "sustitucion": (f"juego = (−{seat['bore_tol_um']:g}…0) − "
                                f"({sh['ei_um']:+g}…{sh['es_um']:+g}) µm"),
                "resultado": (f"juego {seat['juego_min_um']:+g}…{seat['juego_max_um']:+g} µm "
                              f"({seat['tipo']})"),
                "criterio": f"clases aceptables: {', '.join(seat['recomendados'])} (típico {seat['tipico']})",
                "fs": None,
                "norma": "ISO 286 · ISO 492 (asiento de rodamiento, clase Normal)",
            }
            det = (f"{comp.ref} montado en '{shaft.name}': eje {sh['fit']}, juego "
                   f"{seat['juego_min_um']:+g}…{seat['juego_max_um']:+g} µm ({seat['tipo']}).")
            if seat["recomendado"]:
                checks.append(_check(regla, "ok", det, calc=calc))
            elif mount == "chumacera_inserto" and seat["tipo"] == "apriete":
                checks.append(_check(
                    regla, "error",
                    det + " El inserto UC debe DESLIZAR sobre el eje (la fijación la dan los prisioneros).",
                    f"Cambia el eje a {rec['tipico']} (aceptables: {', '.join(seat['recomendados'])}).",
                    calc=calc,
                ))
            elif mount != "chumacera_inserto" and seat["tipo"] == "juego":
                checks.append(_check(
                    regla, "error",
                    det + " Un anillo interior GIRATORIO con juego patina sobre el eje (desgaste).",
                    f"Cambia el eje a {rec['tipico']} (aceptables: {', '.join(seat['recomendados'])}).",
                    calc=calc,
                ))
            else:
                checks.append(_check(
                    regla, "aviso",
                    det + f" Fuera de las clases recomendadas para {mount.replace('_', ' ')}.",
                    f"Preferible {rec['tipico']} (aceptables: {', '.join(seat['recomendados'])}).",
                    calc=calc,
                ))
            break
    return checks


def structure_engineering_check(
    scene: dict,
    fasteners: dict,
    grounds: dict,
    joints: dict,
    mates: dict,
    *,
    catalog: dict | None = None,
    carga_kg: float = 0.0,
    rpm: float | None = None,
    belt_radial_n: float | None = None,
    default_material: str = "acero",
) -> list[dict]:
    """Chequeo estructural del ensamblaje completo (no exige que sea una faja).
    Devuelve reglas en el MISMO formato que conveyor_engineering_check."""
    from ..catalog import CATALOG
    from apolo.assembly.connectivity import build_graph

    catalog = catalog if catalog is not None else CATALOG
    if not scene:
        return []
    graph = build_graph(scene, joints, mates, fasteners, grounds)
    masses = {
        fid: feature_mass(f, catalog, default_material)["masa_kg"]
        for fid, f in scene.items()
        if getattr(f, "visible", True)
    }
    checks: list[dict] = []
    checks += _fastener_checks(scene, graph, masses, fasteners, catalog)
    checks += _bearing_checks(scene, catalog, carga_kg, rpm, belt_radial_n)
    checks += _fit_checks(scene, fasteners, joints, mates, catalog)
    checks += _buckling_checks(scene, masses, catalog, carga_kg)
    checks += _tipping_check(scene, grounds, catalog, carga_kg)
    return checks
