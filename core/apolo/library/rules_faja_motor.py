"""Bloques de `conveyor_engineering_check` (plan partir-nucleo-congelado-ii, F3, D4): el
ARRASTRE por método según la construcción (CEMA slider-bed, ISO 5048 sobre rodillos o
rodadura) y la MOTORIZACIÓN (4). Cada cuerpo es el del original, verbatim; el estado
viaja en `ContextoFaja`. Puro.
"""

from __future__ import annotations

import math

from .catalog import CATALOG
from .engineering.belt import belt_power_kw, belt_pull_n, estimate_belt_kg
from .rules_calculo import recommend_motor_kw, required_force_n, required_power_kw
from .rules_comun import EFFICIENCY, POWER_MARGIN, _check
from .rules_faja_contexto import ContextoFaja


def verificar_arrastre(ctx: ContextoFaja) -> tuple[str, str | None, float, float]:
    ancho, carga_kg, checks, conveyor = ctx.ancho, ctx.carga_kg, ctx.checks, ctx.conveyor
    largo, largo_paquete_mm, tipo, v_eff = ctx.largo, ctx.largo_paquete_mm, ctx.tipo, ctx.v_eff
    # 4 · motorización — una BANDA sobre cama desliza (μ≈0.33, engineering/belt.py),
    # MUY distinto de la rodadura (μ=0.06) del transportador de rodillos.
    n_paq = max(1, math.floor(largo / (largo_paquete_mm * 2.0))) if largo_paquete_mm > 0 else 1
    incline = float(conveyor.get("inclinacion_deg") or 0.0)
    soporte = conveyor.get("soporte", "cama")
    metodo_norma = None  # norma del método de arrastre/potencia elegido (V5.10)
    if tipo == "banda" and soporte == "rodillos":
        # banda sobre RODILLOS (idlers) → método ISO 5048 / DIN 22101
        from .engineering.iso5048 import F_ISO, c_coefficient, effective_tension_n

        banda_kg = float(conveyor.get("banda_kg") or estimate_belt_kg(largo, ancho))
        l_m = largo / 1000.0
        q_g = n_paq * carga_kg / l_m
        q_b = banda_kg / (2.0 * l_m)  # masa de UN tramo por metro (el lazo pesa 2·q_B)
        q_ro = float(conveyor.get("q_ro_kg_m") or 0.0)  # giratorias agregadas (ida+retorno)
        h_m = l_m * math.sin(math.radians(incline))
        cc = c_coefficient(l_m)
        pull_n = effective_tension_n(F_ISO, l_m, q_ro, 0.0, q_b, q_g,
                                     delta_deg=incline, h_m=h_m)
        p_req = belt_power_kw(pull_n, v_eff, EFFICIENCY, POWER_MARGIN)
        metodo_norma = "ISO 5048 / DIN 22101"
        calc_pull = {
            "titulo": "Tensión efectiva (banda sobre rodillos)",
            "entradas": {"q_G carga": f"{q_g:.2f} kg/m", "q_B banda": f"{q_b:.2f} kg/m",
                         "q_RO giratorias": f"{q_ro:.2f} kg/m",
                         "f": f"{F_ISO} (rodadura idlers)",
                         "C(L)": f"{cc:.2f} (L={l_m:g} m"
                                 + ("; <80 m: interpolado, referencial)" if l_m < 80 else ")"),
                         "inclinación": f"{incline:g}°"},
            "formula": "F_U = C(L)·f·L·g·(q_RO + (2·q_B + q_G)·cos δ) + q_G·H·g",
            "sustitucion": (f"F_U = {cc:.2f}·{F_ISO}·{l_m:g}·9.81·({q_ro:.2f} + "
                            f"(2·{q_b:.2f} + {q_g:.2f})·cos {incline:g}°) + elevación"),
            "resultado": f"F_U = {pull_n:.1f} N",
            "criterio": "informativo (alimenta potencia y par)",
            "fs": None,
            "norma": "ISO 5048 / DIN 22101",
        }
        checks.append(_check(
            "arrastre de banda", "ok",
            f"Tensión efectiva {pull_n:.1f} N (banda sobre rodillos, método ISO 5048: "
            f"f={F_ISO}, C(L)={cc:.2f}).",
            calc=calc_pull,
        ))
    elif tipo == "banda":
        banda_kg = float(conveyor.get("banda_kg") or estimate_belt_kg(largo, ancho))
        pull_n = belt_pull_n(n_paq * carga_kg, banda_kg, incline_deg=incline)
        p_req = belt_power_kw(pull_n, v_eff, EFFICIENCY, POWER_MARGIN)
        metodo_norma = "CEMA (unit handling) — slider bed"
        calc_pull = {
            "titulo": "Arrastre de banda sobre cama (método CEMA slider-bed)",
            "entradas": {"carga simultánea": f"{n_paq} paq × {carga_kg:g} kg",
                         "peso de banda": f"{banda_kg:.1f} kg",
                         "μ banda-cama": "0.33 (PVC/acero, CEMA slider bed 0.30–0.35)",
                         "inclinación": f"{incline:g}°"},
            "formula": "F = g·(μ·(m_carga + m_banda) + m_carga·sen θ)",
            "sustitucion": (f"F = 9.81·(0.33·({n_paq * carga_kg:g} + {banda_kg:.1f}) + "
                            f"{n_paq * carga_kg:g}·sen {incline:g}°)"),
            "resultado": f"F = {pull_n:.1f} N",
            "criterio": "informativo (alimenta potencia y par)",
            "fs": None,
            "norma": "CEMA (unit handling) — slider bed, μ = 0.30–0.35",
        }
        checks.append(_check(
            "arrastre de banda", "ok",
            f"Fuerza de arrastre efectiva {pull_n:.1f} N "
            f"(banda sobre cama, μ=0.33, {n_paq} paquete(s) + {banda_kg:.1f} kg de banda).",
            calc=calc_pull,
        ))
    else:
        pull_n = required_force_n(carga_kg, largo, largo_paquete_mm)
        p_req = required_power_kw(carga_kg, largo, largo_paquete_mm, v_eff)
    return soporte, metodo_norma, pull_n, p_req


def verificar_motorizacion(ctx: ContextoFaja) -> None:
    checks, conveyor, metodo_norma = ctx.checks, ctx.conveyor, ctx.metodo_norma
    motor_ref, p_req, pull_n, soporte = ctx.motor_ref, ctx.p_req, ctx.pull_n, ctx.soporte
    tipo, v_eff = ctx.tipo, ctx.v_eff
    sugerido = recommend_motor_kw(p_req)
    p_motor = conveyor.get("motor_kW")
    if p_motor is None and motor_ref not in ("ninguno", "documento") and motor_ref in CATALOG:
        p_motor = CATALOG[motor_ref].specs.get("potencia_kW")
    motor_label = "El motor del documento" if motor_ref == "documento" else motor_ref
    if tipo == "banda":
        mu_label = "ISO 5048 f=0.02" if soporte == "rodillos" else "0.33 banda-cama (CEMA)"
    else:
        mu_label = "0.06 rodadura"
    calc_mot = {
        "titulo": "Motorización",
        "entradas": {"arrastre F": f"{pull_n:.1f} N", "velocidad": f"{v_eff:g} m/s",
                     "η": f"{EFFICIENCY}", "margen": f"{POWER_MARGIN}x", "μ": mu_label},
        "formula": "P = F·v / η · margen",
        "sustitucion": f"P = {pull_n:.1f}·{v_eff:g} / {EFFICIENCY} · {POWER_MARGIN}",
        "resultado": f"P requerida = {p_req:.2f} kW",
        "criterio": "P motor ≥ P requerida",
        "fs": round(float(p_motor) / p_req, 2) if (p_motor and p_req > 0) else None,
    }
    # el método de arrastre (CEMA / ISO 5048) fija la norma del cálculo de potencia;
    # sin él (rodillos de gravedad) el balance P = F·v/η es criterio de diseño, no norma
    calc_mot["norma"] = metodo_norma or "criterio de diseño: P = F·v/η con margen de servicio"
    if p_motor is not None:
        p_motor = float(p_motor)
        if p_motor >= p_req:
            checks.append(_check(
                "motorización", "ok",
                f"{motor_label} ({p_motor:g} kW) ≥ {p_req:.2f} kW requeridos (margen {POWER_MARGIN}x incluido).",
                calc=calc_mot,
            ))
        else:
            checks.append(_check(
                "motorización", "error",
                f"{motor_label} ({p_motor:g} kW) insuficiente: se requieren {p_req:.2f} kW.",
                f"Usa {sugerido}.",
                calc=calc_mot,
            ))
    elif motor_ref == "documento":
        checks.append(_check(
            "motorización", "aviso",
            f"Motor presente pero sin potencia legible en el nombre; para {v_eff:g} m/s se necesitan ≥ {p_req:.2f} kW.",
            "Indica la potencia en el nombre del motor (p. ej. '1.5HP' o '1.1 kW').",
            calc=calc_mot,
        ))
    elif v_eff > 0:
        checks.append(_check(
            "motorización", "aviso",
            f"Transportador sin motor; para {v_eff:g} m/s se necesitan ≥ {p_req:.2f} kW.",
            f"Añade {sugerido} ({CATALOG[sugerido].specs['potencia_kW']} kW).",
            calc=calc_mot,
        ))
    else:
        checks.append(_check("motorización", "ok", "Transportador de gravedad (sin motor)."))
