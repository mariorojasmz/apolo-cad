"""Bloques de `conveyor_engineering_check` (plan partir-nucleo-congelado-ii, F3, D4) de la
ESTRUCTURA: flecha del bastidor (8) y flexión del eje del tambor (9). Cada cuerpo es el
del original, verbatim; el estado viaja en `ContextoFaja`. Puro.
"""

from __future__ import annotations

from .materials import yield_strength, young_modulus
from .rules_comun import DEFLECTION_RATIO, SHAFT_SAFETY, _check
from .rules_faja_contexto import ContextoFaja
from .structural import (
    beam_udl_deflection_mm, rect_tube_inertia_mm4, shaft_bending_stress_mpa,
)


def verificar_flecha_del_bastidor(ctx: ContextoFaja) -> dict | None:
    carga_kg, checks, conveyor = ctx.carga_kg, ctx.checks, ctx.conveyor
    # 8 · flecha del bastidor (larguero = viga simplemente apoyada entre patas, carga repartida)
    frame = conveyor.get("frame")
    if frame and frame.get("span_mm"):
        span = float(frame["span_mm"])
        length = float(frame.get("length_mm") or span)
        n_larg = max(1, int(frame.get("n_largueros") or 2))
        material = frame.get("material") or "acero"
        e_mpa = young_modulus(material)
        inertia = rect_tube_inertia_mm4(frame["width"], frame["depth"], frame["wall"])
        total_kg = float(frame.get("carried_kg") or 0.0) + carga_kg
        q = total_kg * 9.81 / n_larg / max(length, 1.0)  # N/mm por larguero
        defl = beam_udl_deflection_mm(q, span, e_mpa, inertia)
        allow = span / DEFLECTION_RATIO
        calc_fle = {
            "titulo": "Flecha del bastidor",
            "entradas": {"vano L": f"{span:.0f} mm",
                         "sección": f"{frame['width']:.0f}×{frame['depth']:.0f}×{frame['wall']:.0f} mm",
                         "E": f"{e_mpa:.0f} MPa ({material})",
                         "I": f"{inertia:.3g} mm⁴",
                         "carga": f"{total_kg:.0f} kg / {n_larg} larguero(s)"},
            "formula": "δ = 5·w·L⁴ / (384·E·I)",
            "sustitucion": f"δ = 5·{q:.3g}·{span:.0f}⁴ / (384·{e_mpa:.0f}·{inertia:.3g})",
            "resultado": f"δ = {defl:.2f} mm",
            "criterio": f"δ ≤ L/{DEFLECTION_RATIO:.0f} = {allow:.2f} mm",
            "fs": round(allow / defl, 2) if defl > 0 else None,
            "norma": f"criterio de serviciabilidad L/{DEFLECTION_RATIO:.0f} (AISC, carga total)",
        }
        det = (f"Flecha ≈ {defl:.2f} mm en un vano de {span:.0f} mm "
               f"(admisible L/{DEFLECTION_RATIO:.0f} = {allow:.2f} mm; {material}, sección "
               f"{frame['width']:.0f}×{frame['depth']:.0f}×{frame['wall']:.0f}, {total_kg:.0f} kg sobre {n_larg} larguero(s)).")
        if defl <= allow:
            checks.append(_check("flecha del bastidor", "ok", det, calc=calc_fle))
        elif defl <= 2 * allow:
            checks.append(_check(
                "flecha del bastidor", "aviso", det,
                "Acerca las patas (menor vano), usa un larguero de mayor canto o añade apoyos.",
                calc=calc_fle,
            ))
        else:
            checks.append(_check(
                "flecha del bastidor", "error", det,
                "Vano excesivo: añade patas intermedias o un perfil de mayor inercia.",
                calc=calc_fle,
            ))
    return frame


def verificar_flexion_del_eje(ctx: ContextoFaja) -> None:
    ancho, checks, conveyor, frame = ctx.ancho, ctx.checks, ctx.conveyor, ctx.frame
    pull_n, tambor_d = ctx.pull_n, ctx.tambor_d
    # 9 · flexión del eje del tambor motorizado (estimación: carga radial ≈ 2× fuerza de arrastre)
    eje_d = conveyor.get("eje_d")
    cuadrado = conveyor.get("eje_cuadrado")
    if (eje_d or cuadrado) and tambor_d:
        f_rad = 2.0 * pull_n
        span_eje = float(ancho)  # apoyo entre rodamientos ≈ ancho de banda
        if cuadrado:  # el vano es cuadrado (ruedas de banda modular): W = a³/6
            sigma = (f_rad * span_eje / 4.0) / (float(cuadrado) ** 3 / 6.0)
        else:
            sigma = shaft_bending_stress_mpa(f_rad, span_eje, float(eje_d))
        material = (frame or {}).get("material") or "acero"
        allow = yield_strength(material) / SHAFT_SAFETY
        calc_eje = {
            "titulo": "Flexión del eje del tambor",
            "entradas": {"carga radial": f"{f_rad:.1f} N (≈2×arrastre)",
                         "luz entre apoyos": f"{span_eje:.0f} mm",
                         ("sección cuadrada" if cuadrado else "Ø eje"):
                             f"{float(cuadrado or eje_d):.0f} mm",
                         "σy": f"{yield_strength(material):.0f} MPa ({material})"},
            "formula": "σ = 6·(F·L/4) / a³" if cuadrado else "σ = 32·(F·L/4) / (π·d³)",
            "sustitucion": (f"σ = 6·({f_rad:.1f}·{span_eje:.0f}/4) / {float(cuadrado):.0f}³"
                            if cuadrado else
                            f"σ = 32·({f_rad:.1f}·{span_eje:.0f}/4) / (π·{float(eje_d):.0f}³)"),
            "resultado": f"σ = {sigma:.1f} MPa",
            "criterio": f"σ ≤ σy/{SHAFT_SAFETY:.0f} = {allow:.0f} MPa",
            "fs": round(allow / sigma, 2) if sigma > 0 else None,
            "norma": "criterio conservador σ_adm = 0.5·σy (más estricto que ASME B106.1M — ejes)",
        }
        seccion = f"cuadrado {float(cuadrado):.0f}" if cuadrado else f"Ø{float(eje_d):.0f}"
        det = (f"Eje {seccion} a flexión ≈ {sigma:.0f} MPa entre apoyos de {span_eje:.0f} mm "
               f"(admisible σy/{SHAFT_SAFETY:.0f} = {allow:.0f} MPa, {material}). Estimación.")
        if sigma <= allow:
            checks.append(_check("flexión del eje", "ok", det, calc=calc_eje))
        else:
            checks.append(_check(
                "flexión del eje", "error", det,
                "Usa un eje de mayor Ø o acerca los rodamientos (menor luz entre apoyos).",
                calc=calc_eje,
            ))
