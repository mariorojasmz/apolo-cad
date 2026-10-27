"""Pandeo de una COLUMNA de perfil de catálogo (F3f de puerta-sin-sobrediseno). Puro: recibe los
números (sección, material, largo, K, carga axial) y devuelve la regla con su `calc`; qué es
columna, su carga y sus apoyos los decide `services/columnas_rules.py`.

- **Euler / Johnson**: esbeltez λ = K·L / r (r = √(I_min / A)); con λ ≥ λc = π·√(2E/fy),
  Euler Pcr = π²·E·A / λ²; con λ < λc, la parábola de Johnson Pcr = A·fy·(1 − fy·λ² / (4π²E))
  (la columna corta plastifica antes de pandear: Euler la sobreestimaría).
- **K** (longitud efectiva): valores RECOMENDADOS de diseño de AISC 360-16, Comentario del
  apéndice 7, tabla C-A-7.1 (algo mayores que los teóricos: el empotramiento real no es
  perfecto). La base soldada a lo que la sostiene (o la columna anclada con `ground`) es
  empotrada; la cabeza se toma LIBRE de desplazarse (caso e, K = 2,1) aunque se una a otra pieza:
  sin saber si el conjunto está arriostrado, suponerlo sería optimista (criterio declarado).
- **Criterio**: FS = Pcr / N ≥ 3 (`buckling.BUCKLING_FS`, el mismo de las patas); < 2 es error.
"""

from __future__ import annotations

import math

from .buckling import BUCKLING_FS

#: AISC 360-16, Comentario, tabla C-A-7.1 (valor recomendado de diseño).
K_EMPOTRADA_LIBRE = 2.1
NORMA_K = "AISC 360-16, Comentario tabla C-A-7.1 (K recomendado)"
NORMA = f"Euler / Johnson · {NORMA_K} · criterio FS ≥ {BUCKLING_FS:g}"


def carga_critica_n(e_mpa: float, fy_mpa: float, area_mm2: float, i_min_mm4: float,
                    largo_mm: float, k: float) -> dict:
    """{pcr_n, metodo («Euler» | «Johnson»), esbeltez, esbeltez_limite, r_mm}."""
    r = math.sqrt(i_min_mm4 / area_mm2)
    lam = k * largo_mm / r
    lam_c = math.pi * math.sqrt(2.0 * e_mpa / fy_mpa)
    if lam >= lam_c:
        pcr, metodo = math.pi ** 2 * e_mpa * area_mm2 / lam ** 2, "Euler"
    else:
        pcr = area_mm2 * fy_mpa * (1.0 - fy_mpa * lam ** 2 / (4.0 * math.pi ** 2 * e_mpa))
        metodo = "Johnson"
    return {"pcr_n": pcr, "metodo": metodo, "esbeltez": lam, "esbeltez_limite": lam_c,
            "r_mm": r}


def regla_columna(nombre: str, *, perfil: str, area_mm2: float, i_min_mm4: float,
                  largo_mm: float, k: float, apoyos: str, carga_n: float, material: str,
                  e_mpa: float, fy_mpa: float, fuente_seccion: str, resumen_carga: dict,
                  hipotesis: list[str]) -> dict:
    """La regla «pandeo de columna · {nombre}» con su `calc` (memoria) y su `hipotesis`."""
    from ..rules import _check

    c = carga_critica_n(e_mpa, fy_mpa, area_mm2, i_min_mm4, largo_mm, k)
    pcr = c["pcr_n"]
    fs = pcr / carga_n if carga_n > 0 else float("inf")
    if c["metodo"] == "Euler":
        formula, sust = "Pcr = π²·E·A / λ², λ = K·L / r", (
            f"Pcr = π²·{e_mpa:.0f}·{area_mm2:.0f} / {c['esbeltez']:.0f}²")
    else:
        formula, sust = "Pcr = A·fy·(1 − fy·λ² / (4π²·E)), λ = K·L / r", (
            f"Pcr = {area_mm2:.0f}·{fy_mpa:.0f}·(1 − {fy_mpa:.0f}·{c['esbeltez']:.0f}² / "
            f"(4π²·{e_mpa:.0f}))")
    calc = {
        "titulo": f"Pandeo de la columna {nombre}",
        "entradas": {"perfil": perfil, "sección": f"A = {area_mm2:.0f} mm², I_min = "
                     f"{i_min_mm4 / 1e4:.1f} cm⁴, r = {c['r_mm']:.1f} mm ({fuente_seccion})",
                     "material": f"{material} (E {e_mpa:.0f} MPa, fy {fy_mpa:.0f} MPa)",
                     "longitud": f"{largo_mm:.0f} mm", "K": f"{k:g} ({apoyos})",
                     "esbeltez": f"λ = {c['esbeltez']:.0f} (λc = {c['esbeltez_limite']:.0f}: "
                                 f"{c['metodo']})",
                     "carga axial": f"{carga_n:.0f} N", **resumen_carga},
        "formula": formula,
        "sustitucion": sust,
        "resultado": f"Pcr = {pcr:,.0f} N → FS = {fs:.1f}",
        "criterio": f"FS ≥ {BUCKLING_FS:g}",
        "fs": round(fs, 2) if math.isfinite(fs) else None,
        "norma": NORMA,
    }
    det = (f"{nombre}: FS de pandeo {fs:.1f} (Pcr {pcr:,.0f} N, {c['metodo']}, vs {carga_n:.0f} N "
           f"axiales; K = {k:g}, L = {largo_mm:.0f} mm, {perfil}).")
    regla = f"pandeo de columna · {nombre}"
    if fs < 2.0:
        out = _check(regla, "error", det, "Usa una sección mayor o arriostra la columna.",
                     calc=calc)
    elif fs < BUCKLING_FS:
        out = _check(regla, "aviso", det, "Margen justo frente al pandeo: sección mayor o "
                     "arriostramiento.", calc=calc)
    else:
        out = _check(regla, "ok", det, calc=calc)
    return {**out, "hipotesis": list(hipotesis)}
