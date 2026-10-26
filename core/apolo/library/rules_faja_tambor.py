"""Bloques de `conveyor_engineering_check` (plan partir-nucleo-congelado-ii, F3, D4) del
TAMBOR MOTRIZ: par de régimen y de arranque (5, 5b) y adherencia de Euler-Eytelwein
(5c). Cada cuerpo es el del original, verbatim; el estado viaja en `ContextoFaja`. Puro.
"""

from __future__ import annotations

from .engineering.belt import belt_startup_torque_nm
from .rules_comun import _check
from .rules_faja_contexto import ContextoFaja


def verificar_par_del_motor(ctx: ContextoFaja) -> None:
    checks, pull_n, tambor_d, tipo = ctx.checks, ctx.pull_n, ctx.tambor_d, ctx.tipo
    torque_nm = ctx.torque_nm
    # 5 · par del motor en el tambor (faja con tambor motorizado)
    if torque_nm and tambor_d:
        par_req = pull_n * (tambor_d / 2.0 / 1000.0)
        calc_par = {
            "titulo": "Par en el tambor motriz",
            "entradas": {"arrastre F": f"{pull_n:.1f} N", "Ø tambor": f"{tambor_d:g} mm",
                         "par disponible": f"{torque_nm:g} N·m"},
            "formula": "T = F·r",
            "sustitucion": f"T = {pull_n:.1f}·{tambor_d / 2.0 / 1000.0:.4f}",
            "resultado": f"T requerido = {par_req:.1f} N·m",
            "criterio": "T motor ≥ T requerido",
            "fs": round(float(torque_nm) / par_req, 2) if par_req > 0 else None,
            "norma": "criterio de diseño: par en el tambor T = F·r",
        }
        if torque_nm >= par_req:
            checks.append(_check(
                "par del motor", "ok",
                f"Par disponible {torque_nm:g} N·m ≥ {par_req:.1f} N·m requeridos en el tambor Ø{tambor_d:g}.",
                calc=calc_par,
            ))
        else:
            checks.append(_check(
                "par del motor", "error",
                f"Par del motor {torque_nm:g} N·m < {par_req:.1f} N·m requeridos en el tambor Ø{tambor_d:g}.",
                "Usa un motorreductor de mayor par o un tambor de menor Ø.",
                calc=calc_par,
            ))
        # 5b · par de ARRANQUE (solo banda: vencer fricción estática + inercia)
        if tipo == "banda":
            par_arr = belt_startup_torque_nm(pull_n, tambor_d)
            calc_arr = {
                "titulo": "Par de arranque",
                "entradas": {"T régimen": f"{par_req:.1f} N·m", "factor de arranque": "1.6",
                             "par disponible": f"{torque_nm:g} N·m"},
                "formula": "T_arr = F·r · 1.6",
                "sustitucion": f"T_arr = {par_req:.1f} · 1.6",
                "resultado": f"T_arr = {par_arr:.1f} N·m",
                "criterio": "T motor ≥ T_arr",
                "fs": round(float(torque_nm) / par_arr, 2) if par_arr > 0 else None,
                "norma": "factor 1.6 — práctica industrial 1.5–2.0, coherente con "
                         "DIN 22101 (arranque)",
            }
            if torque_nm >= par_arr:
                checks.append(_check(
                    "par de arranque", "ok",
                    f"Par disponible {torque_nm:g} N·m ≥ {par_arr:.1f} N·m de arranque (factor 1.6).",
                    calc=calc_arr,
                ))
            else:
                checks.append(_check(
                    "par de arranque", "aviso",
                    f"Par {torque_nm:g} N·m < {par_arr:.1f} N·m de arranque (factor 1.6): "
                    "puede costarle arrancar a plena carga.",
                    "Sube un tamaño de motorreductor o arranca en vacío.",
                    calc=calc_arr,
                ))


def verificar_adherencia_del_tambor(ctx: ContextoFaja) -> None:
    checks, conveyor, pull_n, tambor_d = ctx.checks, ctx.conveyor, ctx.pull_n, ctx.tambor_d
    tipo = ctx.tipo
    # 5c · adherencia del tambor motriz (Euler-Eytelwein, V5.10): el tambor solo
    # transmite F_U si el ramal flojo lleva tensión T2 ≥ F_U/(e^{μα}−1) — es lo que
    # el TENSOR debe garantizar. El modelo no declara la tensión real del tensor →
    # se reporta la T2 MÍNIMA requerida (honesto, patrón hanging_load); con `t2_n`
    # explícito en el dict se calcula el FS real.
    if tipo == "banda" and tambor_d and pull_n > 0:
        from .engineering.iso5048 import (
            MU_DRUM, eytelwein_fs, eytelwein_ratio, eytelwein_t2_min_n,
        )

        engomado = bool(conveyor.get("tambor_engomado"))
        mu_t = MU_DRUM["engomado"] if engomado else MU_DRUM["liso"]
        alpha = 180.0  # abrace típico con tensor de cola
        t2_min = eytelwein_t2_min_n(pull_n, mu_t, alpha)
        t2_real = conveyor.get("t2_n")
        ratio = eytelwein_ratio(mu_t, alpha)
        # carga radial por rodamiento del eje del tambor por la TENSIÓN DE BANDA: con
        # abrace ~180° los dos ramales tiran casi paralelos → la envoltura suma T1+T2,
        # repartida entre los 2 rodamientos del eje. T2 = t2_n declarado o T2_min de
        # adherencia; T1 = T2 + F_U. Lo consume la vida L10 (structure_engineering_check),
        # que sin esto usaría solo el peso del producto (que en realidad lo lleva la mesa).
        t2_used = float(t2_real) if t2_real else t2_min
        conveyor["pull_n"] = round(pull_n, 1)
        conveyor["bearing_radial_n"] = round((pull_n + 2.0 * t2_used) / 2.0, 1)
        calc_eyt = {
            "titulo": "Adherencia del tambor motriz (Euler-Eytelwein)",
            "entradas": {"F_U (arrastre)": f"{pull_n:.1f} N",
                         "μ tambor": f"{mu_t:g} ({'engomado' if engomado else 'acero liso'})",
                         "α abrace": f"{alpha:g}°",
                         "e^(μα)": f"{ratio:.2f}"},
            "formula": "T2_min = F_U / (e^(μα) − 1)",
            "sustitucion": f"T2_min = {pull_n:.1f} / ({ratio:.2f} − 1)",
            "resultado": f"T2_min = {t2_min:.1f} N",
            "criterio": "el tensor debe garantizar T2 ≥ T2_min (si no, la banda patina)",
            "fs": (round(eytelwein_fs(pull_n + float(t2_real), float(t2_real), mu_t, alpha), 2)
                   if t2_real else None),
            "norma": "Euler-Eytelwein (ISO 5048 · DIN 22101 · CEMA)",
        }
        if conveyor.get("tiene_tensor"):
            checks.append(_check(
                "adherencia del tambor motriz", "ok",
                f"Tambor {'engomado' if engomado else 'liso'} (μ={mu_t:g}, α={alpha:g}°): "
                f"el tensor debe garantizar T2 ≥ {t2_min:.1f} N para transmitir "
                f"{pull_n:.1f} N sin patinar (hay un tensor reconocido en el modelo).",
                calc=calc_eyt,
            ))
        else:
            checks.append(_check(
                "adherencia del tambor motriz", "aviso",
                f"Sin tensor reconocido: la banda necesita T2 ≥ {t2_min:.1f} N en el ramal "
                f"flojo para no patinar (tambor {'engomado' if engomado else 'liso'}, μ={mu_t:g}).",
                "Añade un tensor reconocible (create_take_up, una unidad UCT de catálogo o el "
                "metadato `tensores` con su carrera) o verifica la tensión de montaje.",
                calc=calc_eyt,
            ))
