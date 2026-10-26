"""Estructura del chequeo estructural: vida L10 de rodamientos (ISO 281), pandeo de
Euler de las patas y estabilidad al vuelco (COG vs huella de apoyo).

El orquestador es `report.structure_engineering_check`.
"""

from __future__ import annotations

import math

from ..materials import piece_role, resolve_material, young_modulus
from ..rules import _check, _LEG_RE, _parse_wall, _SECTION_RE
from .bearings import L10_MIN_H, L10_TARGET_H, l10_hours
from .buckling import BUCKLING_FS, euler_critical_load_n, rect_tube_min_inertia_mm4
from .mass import scene_mass_properties
from .report_comun import _BEARING_CATS, G, _name
from .stability import convex_hull_2d, hull_margin_mm


def _bearing_checks(scene, catalog, carga_kg: float, rpm: float | None,
                    belt_radial_n: float | None = None) -> list[dict]:
    from ..catalog import CATALOG

    catalog = catalog if catalog is not None else CATALOG
    bearings = []
    for fid, f in scene.items():
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
    candidatas = [(fid, f) for fid, f in scene.items() if _LEG_RE.match(piece_role(_name(f)))]
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


def _tipping_check(scene, grounds, catalog, carga_kg: float, default_material=None) -> list[dict]:
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
    props = scene_mass_properties(scene, catalog, None, default_material, include_hidden=True)
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
