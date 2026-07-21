"""Stack-up de cadenas de cotas 1D (V7.3): peor caso + estadístico (RSS).

El ingeniero digital declara una CADENA de eslabones dirigidos (cada uno con su
nominal, sentido ±1 y tolerancia) y un REQUISITO de cierre; el motor verifica que la
suma de tolerancias cierra el requisito por PEOR CASO y por RSS (√Σt²). Análogo
automático a TolAnalyst, acotado HONESTAMENTE a cadenas LINEALES 1D — nada de zonas
3D ni GD&T matemático.

La tolerancia de cada eslabón sale de UNA fuente declarada:
  - ``{"pm": 0.2}``       ± explícito (mm)
  - ``{"fit": "h7"}``     banda ISO 286 (asimétrica) sobre el nominal
  - ``{"iso2768": "m"}``  tolerancia general por rango (clase f/m/c)
  - ``{"lim": [lo, hi]}`` límites ABSOLUTOS (mm) → banda relativa al nominal

Unidades: mm. Funciones PURAS (jamás Document/escena): la resolución de nominales
``=expr`` y de eslabones por id (bbox vivo) la hace la capa API antes de llamar aquí.
Convención: desviación = medida − nominal; cierre = Σ sentido·medida.
"""

from __future__ import annotations

import math

from .fits import fit_limits

# ISO 2768-1 (tolerancias generales lineales, mm) — ± por clase (f/m/c/v) y rango nominal.
# Rangos: 0.5–3, 3–6, 6–30, 30–120, 120–400, 400–1000, 1000–2000, 2000–4000 mm.
_ISO2768_RANGES = (3.0, 6.0, 30.0, 120.0, 400.0, 1000.0, 2000.0, 4000.0)
ISO2768_LINEAR: dict[str, tuple[float, ...]] = {
    "f": (0.05, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, None),      # fina
    "m": (0.1, 0.1, 0.2, 0.3, 0.5, 0.8, 1.2, 2.0),          # media
    "c": (0.2, 0.3, 0.5, 0.8, 1.2, 2.0, 3.0, 4.0),          # grosera
    "v": (None, 0.5, 1.0, 1.5, 2.5, 4.0, 6.0, 8.0),         # muy grosera
}


def iso2768_linear(dim_mm: float, clase: str = "m") -> float:
    """Tolerancia general lineal ± (mm) para el nominal y la clase ISO 2768-1.

    El cajetín (V7.2) declara «ISO 2768-mK»; esta tabla es su NÚMERO. Fuente única."""
    clase = str(clase).strip().lower()
    if clase not in ISO2768_LINEAR:
        raise KeyError(f"Clase ISO 2768 '{clase}' no soportada (f/m/c/v)")
    d = abs(float(dim_mm))
    if d < 0.5 or d > 4000.0:
        raise KeyError(f"Nominal {d:g} mm fuera de ISO 2768-1 lineal (0.5–4000 mm)")
    for hi, tol in zip(_ISO2768_RANGES, ISO2768_LINEAR[clase]):
        if d <= hi:
            if tol is None:
                raise KeyError(f"ISO 2768-{clase} no cubre la cota {d:g} mm en ese rango")
            return float(tol)
    raise KeyError(f"Nominal {d:g} mm fuera de rango")  # inalcanzable


def _resolve_tol(nominal_mm: float, tol: dict) -> tuple[float, float, str]:
    """Resuelve la tolerancia de un eslabón → (dev_lo, dev_hi, fuente) en mm, RELATIVOS
    al nominal (dev = límite − nominal). Una sola fuente por eslabón."""
    if not isinstance(tol, dict) or len(tol) != 1:
        raise ValueError(
            "cada eslabón declara UNA tolerancia: pm | fit | iso2768 | lim "
            f"(recibido: {tol!r})"
        )
    (kind, val), = tol.items()
    if kind == "pm":
        t = abs(float(val))
        if t == 0.0:  # tol ausente/cero: cota de REFERENCIA — se declara, no se esconde
            return (0.0, 0.0, "±0 (referencia, sin tolerancia declarada)")
        return (-t, t, f"±{t:g}")
    if kind == "fit":
        lim = fit_limits(nominal_mm, str(val))
        return (lim["ei_um"] / 1000.0, lim["es_um"] / 1000.0, f"{lim['fit']} ISO 286")
    if kind == "iso2768":
        t = iso2768_linear(nominal_mm, str(val))
        return (-t, t, f"ISO 2768-{str(val).lower()}")
    if kind == "lim":
        lo, hi = float(val[0]), float(val[1])
        if hi < lo:
            lo, hi = hi, lo
        return (lo - nominal_mm, hi - nominal_mm, f"límites [{lo:g}, {hi:g}]")
    raise ValueError(f"tolerancia '{kind}' desconocida (pm | fit | iso2768 | lim)")


def _verdict(lo: float, hi: float, requisito: dict) -> tuple[bool, str]:
    """¿El intervalo [lo, hi] de cierre CUMPLE el requisito? Devuelve (ok, detalle)."""
    if requisito.get("entre") is not None and (
            requisito.get("min_mm") is not None or requisito.get("max_mm") is not None):
        # V7.3 auditoría: min_mm/max_mm PISABAN los límites de `entre` en silencio
        raise ValueError("requisito contradictorio: usa `entre` O `min_mm`/`max_mm`, no ambos")
    req_lo = req_hi = None
    if requisito.get("entre") is not None:
        req_lo, req_hi = float(requisito["entre"][0]), float(requisito["entre"][1])
    if requisito.get("min_mm") is not None:
        req_lo = float(requisito["min_mm"])
    if requisito.get("max_mm") is not None:
        req_hi = float(requisito["max_mm"])
    ok = True
    partes = []
    if req_lo is not None:
        ok = ok and lo >= req_lo - 1e-9
        partes.append(f"min {req_lo:g}")
    if req_hi is not None:
        ok = ok and hi <= req_hi + 1e-9
        partes.append(f"max {req_hi:g}")
    if req_lo is None and req_hi is None:
        return (True, "sin requisito (solo informativo)")
    return (ok, " · ".join(partes))


def stack_up(eslabones: list[dict], requisito: dict | None = None) -> dict:
    """Verifica una cadena de cotas 1D. Cada eslabón: ``{nombre, nominal_mm, sentido:±1,
    tol}``. Devuelve el nominal de cierre, el intervalo por PEOR CASO y por RSS, el
    veredicto contra el requisito y la contribución de cada eslabón (para la memoria).

    Peor caso: cada eslabón toma su extremo desfavorable. RSS (hipótesis: tolerancias
    independientes y normales, ±3σ ≈ banda) suma las medias-tolerancias en cuadratura."""
    if not eslabones:
        raise ValueError("la cadena necesita al menos un eslabón")
    nominal_close = 0.0
    wc_lo = wc_hi = 0.0
    mean_close = 0.0
    sum_sq = 0.0
    detalle: list[dict] = []
    for e in eslabones:
        nom = float(e["nominal_mm"])
        sen = 1 if int(e.get("sentido", 1)) >= 0 else -1
        dev_lo, dev_hi, fuente = _resolve_tol(nom, e.get("tol") or {"pm": 0.0})
        # contribución al cierre = sentido · valor, valor ∈ [nom+dev_lo, nom+dev_hi]
        c_lo, c_hi = sen * (nom + dev_lo), sen * (nom + dev_hi)
        if c_lo > c_hi:
            c_lo, c_hi = c_hi, c_lo
        half = (dev_hi - dev_lo) / 2.0            # media-tolerancia (para RSS)
        mid = (dev_hi + dev_lo) / 2.0             # sesgo del centro (fits asimétricos)
        nominal_close += sen * nom
        wc_lo += c_lo
        wc_hi += c_hi
        mean_close += sen * (nom + mid)
        sum_sq += half * half
        detalle.append({
            "nombre": str(e.get("nombre", "eslabón")),
            "nominal_mm": round(nom, 4), "sentido": sen, "fuente": fuente,
            "dev_lo_mm": round(dev_lo, 4), "dev_hi_mm": round(dev_hi, 4),
            "half_tol_mm": round(half, 4),
        })
    rss = math.sqrt(sum_sq)
    rss_lo, rss_hi = mean_close - rss, mean_close + rss
    out = {
        "nominal_close_mm": round(nominal_close, 4),
        "peor_caso": {"min_mm": round(wc_lo, 4), "max_mm": round(wc_hi, 4),
                      "tol_total_mm": round(wc_hi - wc_lo, 4)},
        "rss": {"min_mm": round(rss_lo, 4), "max_mm": round(rss_hi, 4),
                "tol_total_mm": round(2 * rss, 4)},
        "n_eslabones": len(eslabones),
        "eslabones": detalle,
    }
    if requisito:
        ok_wc, det = _verdict(wc_lo, wc_hi, requisito)
        ok_rss, _ = _verdict(rss_lo, rss_hi, requisito)
        out["requisito"] = requisito
        out["ok_peor_caso"] = ok_wc
        out["ok_rss"] = ok_rss
        out["veredicto"] = det
    return out


def stackup_rule(name: str, report: dict) -> dict:
    """Convierte un reporte de `stack_up` en una REGLA de memoria (misma forma que las
    de engineering_check: {regla, estado, detalle, calc{…, norma}}) para que fluya por
    `calc_report` como una verificación más. Puro."""
    wc, rss = report["peor_caso"], report["rss"]
    req = report.get("requisito")
    ok = report.get("ok_peor_caso", True)
    estado = "ok" if ok else ("aviso" if report.get("ok_rss") else "error")
    sub = " ".join(
        f"{'+' if e['sentido'] > 0 else '−'}{e['nominal_mm']:g}({e['fuente']})"
        for e in report["eslabones"]
    )
    req_txt = report.get("veredicto", "sin requisito")
    if not report.get("ok_peor_caso", True) and report.get("ok_rss"):
        detalle = (f"Cierre nominal {report['nominal_close_mm']:g} mm; peor caso "
                   f"[{wc['min_mm']:g}, {wc['max_mm']:g}] NO cierra pero RSS "
                   f"[{rss['min_mm']:g}, {rss['max_mm']:g}] sí — aceptable con proceso capaz.")
    elif not ok:
        detalle = (f"Peor caso [{wc['min_mm']:g}, {wc['max_mm']:g}] y RSS "
                   f"[{rss['min_mm']:g}, {rss['max_mm']:g}] incumplen el requisito.")
    else:
        detalle = (f"Cierre nominal {report['nominal_close_mm']:g} mm; peor caso "
                   f"[{wc['min_mm']:g}, {wc['max_mm']:g}] dentro del requisito.")
    return {
        "regla": f"cadena de cotas · {name}",
        "estado": estado,
        "detalle": detalle,
        "calc": {
            "titulo": f"Cadena de cotas — {name}",
            "entradas": {
                "eslabones": f"{report['n_eslabones']} (Σ tol peor caso "
                             f"{wc['tol_total_mm']:g} mm · RSS {rss['tol_total_mm']:g} mm)",
                "requisito": req_txt if req else "—",
            },
            "formula": "cierre = Σ sentido·cota ; peor caso = Σ extremos ; RSS = √Σ(t/2)²",
            "sustitucion": sub,
            "resultado": (f"peor caso [{wc['min_mm']:g}, {wc['max_mm']:g}] mm · "
                          f"RSS [{rss['min_mm']:g}, {rss['max_mm']:g}] mm"),
            "criterio": req_txt if req else "informativo (sin requisito declarado)",
            "norma": "ISO 2768-1 + ISO 286 · método peor caso y RSS",
        },
    }


def bolt_pattern_budget(clearance_hole_mm: float, bolt_dia_mm: float,
                        pos_tols_mm: list[float]) -> dict:
    """Cadena de un PATRÓN de pernos que debe ensamblar (V7.3 C): el presupuesto de
    posición por lado es ``(Ø_paso − Ø_perno)/2`` (holgura radial del barreno de paso);
    debe cubrir la suma de tolerancias de POSICIÓN de los barrenos que se enfrentan
    (peor caso) — o la raíz cuadrada de su suma (RSS). Puro.

    HIPÓTESIS declarada: fórmula de fijador FIJO (el perno se centra en un solo barreno).
    Para pernos FLOTANTES en ambas placas (perno + tuerca, el caso de join_bolted) el
    presupuesto real es hasta 2× → este veredicto es CONSERVADOR, nunca optimista."""
    budget = (float(clearance_hole_mm) - float(bolt_dia_mm)) / 2.0
    wc = float(sum(abs(t) for t in pos_tols_mm))
    rss = math.sqrt(sum(t * t for t in pos_tols_mm))
    return {
        "presupuesto_mm": round(budget, 4),
        "demanda_peor_caso_mm": round(wc, 4),
        "demanda_rss_mm": round(rss, 4),
        "ok_peor_caso": wc <= budget + 1e-9,
        "ok_rss": rss <= budget + 1e-9,
    }
