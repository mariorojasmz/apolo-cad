"""Uniones del chequeo estructural: pernos (cortante, EN 1993-1-8) y cordones de
soldadura (tensión en garganta vs 0.6·σy del material base más débil).

La carga de cada unión sale del grafo de conectividad (`hanging_load_kg`); el
orquestador es `report.structure_engineering_check`.
"""

from __future__ import annotations

from ..materials import resolve_material, yield_strength
from ..rules import _check
from .bolts import TENSILE_AREA_MM2, bolt_shear_capacity_n
from .loads import hanging_load_kg
from .report_comun import G
from .welds import weld_allowable_mpa, weld_throat_stress_mpa


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
                    f"{label}: métrica '{size}' fuera de tabla (M3–M24).",
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
