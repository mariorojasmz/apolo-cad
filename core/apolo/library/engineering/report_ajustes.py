"""Asientos ISO 286 del chequeo estructural: pares eje ↔ rodamiento/chumacera y el
ajuste del eje contra la recomendación por tipo de montaje.

`_SHAFT_FIT_NAME_RE` se compila perezoso aquí (`global`): `report` lo sirve en vivo
por su `__getattr__`, nunca por valor. El orquestador es
`report.structure_engineering_check`.
"""

from __future__ import annotations

from ..rules import _check, _parse_diam
from .report_comun import _BEARING_CATS


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
