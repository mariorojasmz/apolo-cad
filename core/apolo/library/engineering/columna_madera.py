"""Pandeo de una COLUMNA de madera que no es de catálogo (plan puerta-fuera-de-catalogo, D7). Puro:
recibe la sección medida, el largo, K, la carga axial y el `Criterio` (`madera_calculo`); qué es
columna y cuánto carga lo decide `services/columnas_rules.py`. Mismo formato que
`columna.regla_columna`, con `calc.fs_min` = 1: el margen ya está dentro de la norma (los
admisibles de la E.010, el kmod/γM de EN 1995), no se le pide el FS ≥ 3 de Euler a secas.

**E.010** (Art. 26–30; las fórmulas del Art. 30 son la columna equivalente articulada con la carga
admisible de Euler dividida por 2,5, la que da el Ck de las tablas 8 y 9):
- λ = lef / d (d: menor dimensión del rectángulo o el diámetro; Art. 27.1 y 28.1); lef = K·L.
- corta (λ ≤ 10; ≤ 9 circular): N_adm = fc∥·A; intermedia (hasta Ck): N_adm = fc∥·A·(1 − (λ/Ck)⁴/3);
  larga (Ck < λ < 50; < 40 circular): N_adm = π²·Emín·I / (2,5·lef²); λ ≥ 50 (40) no se usa como
  columna (Art. 27.2, 28.2). Ck: la esbeltez a la que la larga admite 2/3 de fc∥·A (Art. 27.1 b);
  para el rectángulo da 0,7025·√(Emín/fc∥) (grupo C: 18,4, como su tabla 8).
- E mínimo (Art. 29.2: columna individual).

**EN 1995-1-1 § 6.3.2** (ec. 6.21–6.29): λrel = λ/π·√(fc,0,k/E0,05), k = 0,5·(1 + βc·(λrel − 0,3)
+ λrel²), kc = 1/(k + √(k² − λrel²)) (βc = 0,2 madera maciza); σc,0,d = 1,5·N/A ≤ kc·fc,0,d con
fc,0,d = kmod·fc,0,k/γM (kmod de media duración: la carga útil manda). 1,5 sobre TODA la carga
(G y Q sin separar: conservador frente a 1,35·G).
"""

from __future__ import annotations

import math

from .madera_calculo import NORMA_EC5, Criterio

ESBELTEZ_CORTA = {"rect": 10.0, "circ": 9.0}     # E.010 Art. 27.1 a, 28.1 a
ESBELTEZ_MAX = {"rect": 50.0, "circ": 40.0}      # E.010 Art. 27.2, 28.2
BETA_C = 0.2                                     # EN 1995-1-1 ec. 6.29, madera maciza
GAMMA_CARGA = 1.5


def n_adm_e010(*, area_mm2: float, i_min_mm4: float, d_mm: float, lef_mm: float,
               circular: bool, fc: float, e_min: float) -> dict:
    """{n_adm, lam, ck, tipo («corta» | «intermedia» | «larga» | «no admisible»)}."""
    forma = "circ" if circular else "rect"
    lam = lef_mm / d_mm
    # la larga: π²·E·I/(2,5·lef²) = π²·E·(I/(A·d²))·A/(2,5·λ²); Ck donde vale 2/3·fc·A
    rho = i_min_mm4 / (area_mm2 * d_mm * d_mm)
    ck = math.sqrt(math.pi ** 2 * e_min * rho * 1.5 / (2.5 * fc))
    if lam >= ESBELTEZ_MAX[forma]:
        return {"n_adm": 0.0, "lam": lam, "ck": ck, "tipo": "no admisible"}
    if lam <= ESBELTEZ_CORTA[forma]:
        return {"n_adm": fc * area_mm2, "lam": lam, "ck": ck, "tipo": "corta"}
    if lam <= ck:
        return {"n_adm": fc * area_mm2 * (1.0 - (lam / ck) ** 4 / 3.0), "lam": lam, "ck": ck,
                "tipo": "intermedia"}
    n = math.pi ** 2 * e_min * i_min_mm4 / (2.5 * lef_mm ** 2)
    return {"n_adm": n, "lam": lam, "ck": ck, "tipo": "larga"}


def kc_ec5(*, lam: float, fc0_k: float, e0_05: float) -> dict:
    """{kc, lam_rel, k}: EN 1995-1-1 ec. 6.21–6.29 (βc = 0,2)."""
    lam_rel = lam / math.pi * math.sqrt(fc0_k / e0_05)
    if lam_rel <= 0.3:  # § 6.3.2(2): sin reducción
        return {"kc": 1.0, "lam_rel": lam_rel, "k": None}
    k = 0.5 * (1.0 + BETA_C * (lam_rel - 0.3) + lam_rel ** 2)
    return {"kc": 1.0 / (k + math.sqrt(k * k - lam_rel ** 2)), "lam_rel": lam_rel, "k": k}


def regla_columna_madera(nombre: str, *, seccion: str, area_mm2: float, i_min_mm4: float,
                         d_mm: float, circular: bool, largo_mm: float, k: float, apoyos: str,
                         carga_n: float, crit: Criterio, resumen_carga: dict,
                         hipotesis: list[str]) -> dict:
    """La regla «pandeo de columna · {nombre}» de una columna de madera, con su `calc`."""
    from ..rules import _check

    v = crit.valores
    lef = k * largo_mm
    if crit.tipo == "e010":
        r = n_adm_e010(area_mm2=area_mm2, i_min_mm4=i_min_mm4, d_mm=d_mm, lef_mm=lef,
                       circular=circular, fc=v["fc_par"], e_min=v["e_min"])
        fs = r["n_adm"] / carga_n if carga_n > 0 else math.inf
        formula = {"corta": "N_adm = fc∥·A", "intermedia": "N_adm = fc∥·A·(1 − (λ/Ck)⁴/3)",
                   "larga": "N_adm = π²·Emín·I / (2,5·lef²)",
                   "no admisible": "λ ≥ límite: no se usa como columna"}[r["tipo"]]
        sust = (f"λ = {lef:.0f}/{d_mm:.0f} = {r['lam']:.1f} (Ck = {r['ck']:.1f}, columna "
                f"{r['tipo']}); N_adm = {r['n_adm']:,.0f} N")
        norma = f"{crit.etiqueta}: Art. 26–30 (Emín, Art. 29.2)"
        mat = (f"{crit.material} — {crit.etiqueta}: fc∥ = {v['fc_par']:g} MPa, Emín = "
               f"{v['e_min']:.0f} MPa (admisibles)")
        resultado = f"N_adm = {r['n_adm']:,.0f} N → N_adm/N = {fs:.2f}"
        criterio = "N ≤ N_adm (admisible de la norma)"
    else:
        radio = math.sqrt(i_min_mm4 / area_mm2)
        lam = lef / radio
        kc = kc_ec5(lam=lam, fc0_k=v["fc0_k"], e0_05=v["e0_05"])
        fcd = v["kmod_media"] * v["fc0_k"] / v["gamma_m"]
        sigma = GAMMA_CARGA * carga_n / area_mm2
        fs = kc["kc"] * fcd / sigma if sigma > 0 else math.inf
        formula = ("σc,0,d ≤ kc·fc,0,d; λrel = λ/π·√(fc,0,k/E0,05); k = 0,5(1 + βc(λrel − 0,3) "
                   "+ λrel²); kc = 1/(k + √(k² − λrel²))")
        sust = (f"λ = {lef:.0f}/{radio:.1f} = {lam:.0f}; λrel = {kc['lam_rel']:.2f}; kc = "
                f"{kc['kc']:.3f}; σc,0,d = 1,5·{carga_n:.0f}/{area_mm2:.0f} = {sigma:.2f} MPa; "
                f"fc,0,d = {v['kmod_media']:g}·{v['fc0_k']:g}/{v['gamma_m']:g} = {fcd:.2f} MPa")
        norma = f"{NORMA_EC5} § 6.3.2 (ec. 6.21–6.29) · {crit.etiqueta}"
        mat = (f"{crit.material} — {crit.etiqueta}: fc,0,k = {v['fc0_k']:g}, E0,05 = "
               f"{v['e0_05']:.0f} MPa")
        resultado = f"kc·fc,0,d / σc,0,d = {fs:.2f}"
        criterio = "σc,0,d ≤ kc·fc,0,d"
    calc = {
        "titulo": f"Pandeo de la columna {nombre}",
        "entradas": {"sección": seccion, "material": mat, "longitud": f"{largo_mm:.0f} mm",
                     "K": f"{k:g} ({apoyos})", "carga axial": f"{carga_n:.0f} N", **resumen_carga},
        "formula": formula, "sustitucion": sust, "resultado": resultado, "criterio": criterio,
        "fs": round(fs, 2) if math.isfinite(fs) else None, "fs_min": 1.0, "norma": norma,
    }
    det = f"{nombre}: {resultado} ({crit.etiqueta}; K = {k:g}, L = {largo_mm:.0f} mm, {seccion})."
    regla = f"pandeo de columna · {nombre}"
    if fs < 1.0:
        out = _check(regla, "error", det, "Sección mayor, mejor clase o arriostra la columna.",
                     calc=calc)
    else:
        out = _check(regla, "ok", det, calc=calc)
    return {**out, "hipotesis": [*crit.hipotesis, *hipotesis]}


__all__ = ["kc_ec5", "n_adm_e010", "regla_columna_madera"]
