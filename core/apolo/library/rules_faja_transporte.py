"""Bloques de `conveyor_engineering_check` (plan partir-nucleo-congelado-ii, F3, D4) sobre
lo que ve el PAQUETE: velocidad de banda (0), apoyo (1), capacidad de rodillo (2), ancho
útil (3), velocidad del rodillo (6) y altura de trabajo (7). Cada cuerpo es el del
original, verbatim; el estado viaja en `ContextoFaja`. Puro.
"""

from __future__ import annotations

import math

from .ancho_util import regla_ancho_util
from .rules_calculo import recommend_roller
from .rules_comun import RAIL_W, _check
from .rules_faja_contexto import ContextoFaja


def verificar_velocidad_de_banda(ctx: ContextoFaja) -> None:
    checks, rpm_motor, tambor_d, v_real = ctx.checks, ctx.rpm_motor, ctx.tambor_d, ctx.v_real
    velocidad_m_s = ctx.velocidad_m_s
    # 0 · velocidad de banda (faja con tambor motorizado)
    if v_real is not None:
        calc_v = {
            "titulo": "Velocidad de banda",
            "entradas": {"rpm de salida": f"{rpm_motor:g} rpm", "Ø tambor": f"{tambor_d:g} mm",
                         "objetivo": f"{velocidad_m_s:g} m/s" if velocidad_m_s else "—"},
            "formula": "v = n·π·Ø / 60000",
            "sustitucion": f"v = {rpm_motor:g}·π·{tambor_d:g} / 60000",
            "resultado": f"v = {v_real:.3f} m/s ({v_real * 60:.1f} m/min)",
            "criterio": (f"v ≥ 0.9 × objetivo = {0.9 * velocidad_m_s:.3f} m/s"
                         if velocidad_m_s else "informativo"),
            "fs": round(v_real / velocidad_m_s, 2) if velocidad_m_s else None,
            "norma": "CEMA (velocidad de banda / unit handling)",
        }
        det = (f"El accionamiento ({rpm_motor:g} rpm × Ø{tambor_d:g}) da "
               f"{v_real:.3f} m/s ({v_real * 60:.1f} m/min).")
        if velocidad_m_s and velocidad_m_s > 0 and v_real < 0.9 * velocidad_m_s:
            checks.append(_check(
                "velocidad de banda", "aviso",
                det + f" Por debajo del objetivo {velocidad_m_s:g} m/s ({velocidad_m_s * 60:.1f} m/min).",
                "Usa un tambor de mayor Ø o un motorreductor de más rpm.",
                calc=calc_v,
            ))
        else:
            checks.append(_check("velocidad de banda", "ok", det, calc=calc_v))


def verificar_apoyo_del_paquete(ctx: ContextoFaja) -> int:
    checks, conveyor, largo_paquete_mm = ctx.checks, ctx.conveyor, ctx.largo_paquete_mm
    paso, tipo = ctx.paso, ctx.tipo
    # 1 · apoyo del paquete
    if tipo == "banda":
        checks.append(_check(
            "apoyo del paquete", "ok",
            "Soporte continuo por la banda/mesa (no aplica el paso de rodillos).",
        ))
        support_count = max(1, int(conveyor.get("n_rodillos") or 2))
    elif paso > 0:
        apoyo = math.floor(largo_paquete_mm / paso)
        support_count = max(1, apoyo)
        if apoyo >= 3:
            checks.append(_check("apoyo del paquete", "ok", f"El paquete apoya en {apoyo} rodillos (mínimo 3)."))
        elif apoyo == 2:
            checks.append(_check(
                "apoyo del paquete", "aviso",
                f"El paquete solo apoya en 2 rodillos (paso {paso:g} mm).",
                f"Reduce el paso a ≤ {largo_paquete_mm / 3:.0f} mm para 3 apoyos.",
            ))
        else:
            checks.append(_check(
                "apoyo del paquete", "error",
                f"Con paso {paso:g} mm el paquete de {largo_paquete_mm:g} mm puede caer entre rodillos.",
                f"Usa un paso ≤ {largo_paquete_mm / 3:.0f} mm.",
            ))
    else:
        support_count = 1
    return support_count


def verificar_capacidad_de_rodillo(ctx: ContextoFaja) -> None:
    carga_kg, checks, conveyor = ctx.carga_kg, ctx.checks, ctx.conveyor
    largo_paquete_mm, paso, rodillo = ctx.largo_paquete_mm, ctx.paso, ctx.rodillo
    rodillo_ref, support_count, v_eff = ctx.rodillo_ref, ctx.support_count, ctx.v_eff
    # 2 · capacidad del rodillo (uno a medida, sin ficha: `rodillos_a_mano_reglas`)
    carga_por_rodillo = carga_kg / max(1, support_count)
    capacidad = float(rodillo.specs.get("capacidad_kg") or 0.0)
    calc_rod = {
        "titulo": "Capacidad de rodillo",
        "entradas": {"carga por paquete": f"{carga_kg:g} kg", "apoyos": f"{support_count}",
                     "rodillo": f"{rodillo_ref} ({capacidad:g} kg/ud)"},
        "formula": "P = carga / n_apoyos",
        "sustitucion": f"P = {carga_kg:g} / {max(1, support_count)}",
        "resultado": f"P = {carga_por_rodillo:.1f} kg/rodillo",
        "criterio": f"P ≤ {capacidad:g} kg (capacidad de catálogo)",
        "fs": round(capacidad / carga_por_rodillo, 2) if carga_por_rodillo > 0 else None,
        "norma": "CEMA (clasificación de carga de rodillos/idlers) — ficha de fabricante",
    }
    if not capacidad:
        from .rodillos_a_mano_reglas import capacidad_a_medida
        checks.append(capacidad_a_medida(conveyor, carga_kg, support_count, v_eff))
    elif carga_por_rodillo <= capacidad:
        checks.append(_check("capacidad de rodillo", "ok", f"{carga_por_rodillo:.1f} kg/rodillo ≤ "
                             f"{capacidad:g} kg ({rodillo_ref}).", calc=calc_rod))
    else:
        sugerido = recommend_roller(carga_kg, largo_paquete_mm, paso or largo_paquete_mm / 3.0)
        checks.append(_check(
            "capacidad de rodillo", "error",
            f"{carga_por_rodillo:.1f} kg/rodillo supera los {capacidad:g} kg del {rodillo_ref}.",
            f"Usa {sugerido} o añade más rodillos.",
            calc=calc_rod,
        ))


def verificar_ancho_util(ctx: ContextoFaja) -> None:
    ancho, ancho_paquete_mm, checks = ctx.ancho, ctx.ancho_paquete_mm, ctx.checks
    conveyor = ctx.conveyor
    # 3 · ancho útil (rodillos: entre largueros; banda: la banda y sus guías, `ancho_util.py`)
    if ancho_paquete_mm is not None:
        checks.append(regla_ancho_util(conveyor, ancho, ancho_paquete_mm, RAIL_W))


def verificar_velocidad_del_rodillo(ctx: ContextoFaja) -> None:
    checks, rodillo, v_eff = ctx.checks, ctx.rodillo, ctx.v_eff
    # 6 · velocidad ↔ rodillo (informativo)
    if v_eff > 0:
        d = float(rodillo.specs.get("diametro_mm") or rodillo.specs["od"])  # rodillo o su tubo
        rpm_req = v_eff * 60000.0 / (math.pi * d)
        checks.append(_check(
            "velocidad", "ok",
            f"{v_eff:g} m/s requiere {rpm_req:.0f} rpm en rodillo Ø{d:g} (ajustable con la transmisión).",
        ))


def verificar_geometria(ctx: ContextoFaja) -> None:
    altura, checks, largo = ctx.altura, ctx.checks, ctx.largo
    # 7 · geometría (altura de trabajo)
    if altura:
        det = f"Altura de trabajo {float(altura):.0f} mm; largo {largo:.0f} mm."
        if 500 <= float(altura) <= 1100:
            checks.append(_check("geometría", "ok", det))
        else:
            checks.append(_check("geometría", "aviso", det + " Fuera del rango ergonómico 500–1100 mm."))
