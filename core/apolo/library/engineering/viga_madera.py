"""Flecha y flexión de una viga de MADERA que no es de catálogo (plan puerta-fuera-de-catalogo, D7).
Puro: recibe la sección medida, los apoyos, las cargas y el `Criterio` (`madera_calculo`); qué es
viga, dónde se apoya y qué le carga lo decide `services/vigas_rules.py`. Mismo formato de regla
que `viga_bastidor.regla_viga` (la memoria y la puerta la leen igual).

Cargas: `cargas` (peso propio + lo que le baja) son PERMANENTES; la carga útil (puntual móvil) es
la VARIABLE. La viga es lineal: las flechas se superponen por tramo.

**E.010** (admisibles, cargas de servicio; nunca kmod/γM):
- E = **E mínimo** del grupo (Art. 17: elemento individual; el promedio sólo en acción de conjunto).
- Flecha (Art. 18): permanente × 1,8 (deformación diferida, 18.3) + variable ≤ L/250 (18.2 a, «sin
  cielo raso de yeso»); la variable sola ≤ L/350 y ≤ 13 mm (18.2 b). En un volado, L es la
  distancia del apoyo al extremo (18.2, último párrafo).
- Flexión σ = M/W ≤ fm (Art. 19.1); corte τ = 1,5·V/A ≤ fv en la sección rectangular (Art. 19.2,
  V acotada por la mayor reacción con la carga útil junto a cada apoyo: conservador). Sin el +10 %
  de acción de conjunto (16.3).

**EN 1995-1-1** (característicos con kmod/γM; clase de servicio 1):
- E = E0,mean (§ 2.2.3(2)); w_inst = w_G + w_Q; w_fin = w_G·(1 + kdef) + w_Q·(1 + ψ2·kdef)
  (§ 2.2.3(5), ec. 2.3–2.5); límites de la tabla 7.2, el extremo MENOS exigente del rango
  recomendado (sin anexo nacional): vano w_inst ≤ L/300 y w_net,fin ≤ L/250; voladizo L/150 y
  L/125.
- Flexión: σm,d = M(1,35·G + 1,5·Q)/W ≤ fm,d = kmod·fm,k/γM (§ 2.4.1, ec. 2.14; kmod de la acción
  más corta de la combinación, § 3.1.3(2)), y 1,35·G sola con kmod permanente. Sin kh (§ 3.2(3):
  sólo subiría fm,k). El corte no se verifica (fv,k no tabulado): la regla lo declara.

Criterio de estado (el de `regla_viga`): flecha hasta 2× el límite = aviso, más = error; tensión
sobre la admisible = error (en madera la admisible ya es la de la norma).
"""

from __future__ import annotations

from dataclasses import replace

from .madera_calculo import NORMA_EC5, PSI2, Criterio
from .viga_bastidor import Envolvente, envolvente
from .viga_continua import CargaPuntual, viga_continua

FACTOR_DIFERIDA_E010 = 1.8   # Art. 18.3
RATIO_TOTAL_E010 = 250.0     # Art. 18.2 a (sin cielo raso de yeso)
RATIO_VIVA_E010 = 350.0      # Art. 18.2 b
MAX_VIVA_E010_MM = 13.0      # Art. 18.2 b
#: EN 1995-1-1 tabla 7.2, el extremo menos exigente: (w_inst, w_net,fin) por tipo de tramo
RATIOS_EC5 = {"vano": (300.0, 250.0), "voladizo": (150.0, 125.0)}
GAMMA_G, GAMMA_Q = 1.35, 1.5   # EN 1990 tabla A1.2(B)


def _escalar(cargas, k: float) -> list:
    out = []
    for c in cargas:
        out.append(replace(c, p_n=c.p_n * k) if isinstance(c, CargaPuntual)
                   else replace(c, q_n_mm=c.q_n_mm * k))
    return out


def _por_tramo(largo, ei, apoyos, cargas, util) -> list[float] | None:
    """|δ| máxima de cada tramo (la envolvente); None si no hay ninguna carga."""
    if not cargas and util <= 0:
        return None
    return [t[3] for t in envolvente(largo, ei, apoyos, cargas, util).tramos]


def _v_max(largo, ei, apoyos, cargas, util) -> float:
    """Cota del corte: la mayor reacción con la carga útil sobre cada apoyo (y sin ella)."""
    casos = [list(cargas)] + ([list(cargas) + [CargaPuntual(a.x_mm, util)] for a in apoyos]
                              if util > 0 else [])
    return max(max(abs(r) for r in viga_continua(largo, ei, apoyos, c).reacciones_n)
               for c in casos if c) if any(casos) else 0.0


def _estado(u: float, aviso_hasta: float) -> str:
    return "ok" if u <= 1.0 + 1e-9 else ("aviso" if u <= aviso_hasta + 1e-9 else "error")


def regla_viga_madera(etiqueta: str, *, largo_mm: float, apoyos, cargas, carga_util_n: float,
                      i_mm4: float, w_mm3: float, area_mm2: float, rectangular: bool,
                      crit: Criterio, seccion: str, resumen_cargas: dict,
                      hipotesis: list[str]) -> tuple[dict, Envolvente]:
    """La regla «flecha de viga · …» de una viga de madera (E.010 o EN 1995) y su envolvente total
    (la que baja sus reacciones por el bastidor)."""
    from ..rules import _check

    v = crit.valores
    e010 = crit.tipo == "e010"
    e = v["e_min"] if e010 else v["e0_mean"]
    ei = e * i_mm4
    env = envolvente(largo_mm, ei, apoyos, cargas, carga_util_n)
    d_g = _por_tramo(largo_mm, ei, apoyos, cargas, 0.0) or [0.0] * len(env.tramos)
    d_q = _por_tramo(largo_mm, ei, apoyos, [], carga_util_n) or [0.0] * len(env.tramos)
    tramos, peor = [], (-1.0, 0)
    for k, (d0, d1, tipo, _d, _l) in enumerate(env.tramos):
        luz = d1 - d0
        if e010:
            total = FACTOR_DIFERIDA_E010 * d_g[k] + d_q[k]
            lim_t, lim_q = luz / RATIO_TOTAL_E010, min(luz / RATIO_VIVA_E010, MAX_VIVA_E010_MM)
            u = max(total / lim_t if lim_t else 0.0, d_q[k] / lim_q if lim_q else 0.0)
            delta, lim = total, lim_t
        else:
            r_inst, r_fin = RATIOS_EC5[tipo]
            inst = d_g[k] + d_q[k]
            fin = d_g[k] * (1 + v["kdef"]) + d_q[k] * (1 + PSI2 * v["kdef"])
            lim_i, lim_f = luz / r_inst, luz / r_fin
            u = max(inst / lim_i if lim_i else 0.0, fin / lim_f if lim_f else 0.0)
            delta, lim = fin, lim_f
        tramos.append((d0, d1, tipo, delta, lim))
        if u > peor[0]:
            peor = (u, k)
    u_fle, crit_k = peor
    d0, d1, tipo, delta, lim = tramos[crit_k]
    if e010:
        sigma, f_adm = env.momento_nmm / w_mm3, v["fm"]
        u_sig = sigma / f_adm
        tau = 1.5 * _v_max(largo_mm, ei, apoyos, cargas, carga_util_n) / area_mm2 if rectangular else 0.0
        u_tau = tau / v["fv"] if rectangular else 0.0
        resist = (f"σ = {sigma:.2f} MPa ≤ fm {f_adm:g}"
                  + (f"; τ = 1,5·V/A = {tau:.2f} MPa ≤ fv {v['fv']:g}" if rectangular else ""))
    else:
        uls = envolvente(largo_mm, ei, apoyos, _escalar(cargas, GAMMA_G), GAMMA_Q * carga_util_n)
        kmod = v["kmod_media"] if carga_util_n > 0 else v["kmod_perm"]
        f_adm = kmod * v["fm_k"] / v["gamma_m"]
        f_perm = v["kmod_perm"] * v["fm_k"] / v["gamma_m"]
        sigma = uls.momento_nmm / w_mm3
        sig_g = GAMMA_G * (envolvente(largo_mm, ei, apoyos, cargas, 0.0).momento_nmm
                           if cargas else 0.0) / w_mm3
        u_sig = max(sigma / f_adm, sig_g / f_perm if f_perm else 0.0)
        u_tau, tau = 0.0, 0.0
        resist = (f"σm,d = {sigma:.2f} MPa ≤ fm,d = {kmod:g}·{v['fm_k']:g}/{v['gamma_m']:g} = "
                  f"{f_adm:.2f} (1,35·G sola: {sig_g:.2f} ≤ {f_perm:.2f})")
    e_fle = _estado(u_fle, 2.0)
    e_sig = "ok" if max(u_sig, u_tau) <= 1.0 + 1e-9 else "error"
    orden = {"ok": 0, "aviso": 1, "error": 2}
    estado = max(e_fle, e_sig, key=orden.get)
    u_max = max(u_fle, u_sig, u_tau)
    fs = (1.0 / u_max) if u_max > 0 else None
    norma = (f"{crit.etiqueta}: Art. 17 (E mínimo), 18 (deflexiones) y 19 (resistencia)" if e010
             else f"{NORMA_EC5} § 2.2.3, 2.4.1, 3.1.3 y 7.2 (tabla 7.2) · {crit.etiqueta}")
    criterio = (f"(1,8·δG + δQ) ≤ L/{RATIO_TOTAL_E010:.0f}; δQ ≤ L/{RATIO_VIVA_E010:.0f} y ≤ "
                f"{MAX_VIVA_E010_MM:g} mm; σ ≤ fm; τ ≤ fv" if e010 else
                "w_inst ≤ L/300 y w_net,fin ≤ L/250 (voladizo L/150 y L/125); σm,d ≤ fm,d")
    apoyos_txt = ", ".join(f"{a.x_mm:.0f}" + (" (empotr.)" if a.tipo != "apoyo" else "")
                           for a in sorted(apoyos, key=lambda a: a.x_mm))
    entradas = {
        "sección": seccion,
        "material": (f"{crit.material} — {crit.etiqueta}: E = {e:.0f} MPa ("
                     + ("E mínimo" if e010 else "E0,mean") + ")"
                     + (f", fm = {v['fm']:g}, fv = {v['fv']:g} MPa (admisibles)" if e010 else
                        f", fm,k = {v['fm_k']:g} MPa, kdef = {v['kdef']:g}, γM = {v['gamma_m']:g}")),
        "I · W": f"{i_mm4 / 1e4:.2f} cm⁴ · {w_mm3 / 1e3:.2f} cm³",
        "largo": f"{largo_mm:.0f} mm",
        "apoyos (x)": f"{apoyos_txt} mm",
        **resumen_cargas,
    }
    por_tramo = "; ".join(f"{t[2]} {t[0]:.0f}–{t[1]:.0f}: δ = {t[3]:.2f} mm (lím. {t[4]:.2f})"
                          for t in tramos)
    resultado = f"{por_tramo}. Manda el {tipo} {d0:.0f}–{d1:.0f} mm; {resist}"
    detalle = (f"{etiqueta}: δ = {delta:.2f} mm en el {tipo} de {d1 - d0:.0f} mm (límite "
               f"{lim:.2f} mm); {resist} ({crit.etiqueta}).")
    rec = None
    if e_fle != "ok":
        rec = "Acorta el vano (apoyo intermedio) o sube el canto de la pieza."
    if e_sig != "ok":
        rec = ((rec + " ") if rec else "") + "La tensión excede la de la norma: más sección o mejor clase."
    regla = _check(
        f"flecha de viga · {etiqueta}", estado, detalle, rec,
        calc={"titulo": f"Viga de madera: {etiqueta}", "entradas": entradas,
              "formula": ("viga continua Euler-Bernoulli sobre sus apoyos; δ por tramo con G "
                          "(permanente) y Q (útil, puntual móvil) superpuestas; σ = |M|máx / W"),
              "sustitucion": f"EI = {e:.0f}·{i_mm4:.4g} = {ei:.4g} N·mm²",
              "resultado": resultado, "criterio": criterio,
              "fs": round(fs, 2) if fs is not None else None, "norma": norma},
    )
    hip = [*crit.hipotesis, *hipotesis]
    if not e010:
        hip.append(f"Clase de servicio 1 (interior); ψ2 = {PSI2:g} (EN 1990 tabla A1.1, categoría "
                   "E, conservador); el corte no se verifica (fv,k no tabulado).")
    elif not rectangular:
        hip.append("Sección no rectangular: el corte (Art. 19.2) no se verifica.")
    regla["hipotesis"] = hip
    regla["viga"] = {
        "largo_mm": round(largo_mm, 1),
        "apoyos_mm": [round(a.x_mm, 1) for a in sorted(apoyos, key=lambda a: a.x_mm)],
        "flecha_mm": round(delta, 6), "limite_mm": round(lim, 4),
        "tramo": [round(d0, 1), round(d1, 1), tipo],
        "tramos": [{"desde_mm": round(t[0], 1), "hasta_mm": round(t[1], 1), "tipo": t[2],
                    "flecha_mm": round(t[3], 6), "limite_mm": round(t[4], 4)} for t in tramos],
        "momento_nmm": round(env.momento_nmm, 3), "sigma_mpa": round(sigma, 3),
        "sigma_adm_mpa": round(f_adm, 2), "i_mm4": round(i_mm4, 1), "w_mm3": round(w_mm3, 1),
        "e_mpa": e, "criterio": crit.tipo,
    }
    return regla, env


__all__ = ["regla_viga_madera"]
