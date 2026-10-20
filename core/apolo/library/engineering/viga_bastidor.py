"""Verificación de una viga del bastidor: flecha por tramo y tensión de flexión.

La detección (qué pieza es viga, dónde se apoya, qué le cuelga) la hace
`services/vigas_rules.py` sobre el documento; aquí sólo números
([flecha-de-bastidor](../../../../docs/plans/flecha-de-bastidor.md) D3): PURO, recibe la
sección del catálogo, los apoyos y las cargas, y devuelve la regla con su bloque `calc`.

Criterios (D3):
  - flecha por TRAMO (no por viga): un vano contra L/240 (AISC, como el bastidor del
    transportador, `rules.DEFLECTION_RATIO`); un voladizo contra 2·Lv/240 (la luz equivalente
    de un voladizo es el doble de su largo). Hasta 2× el límite es aviso; más, error.
  - tensión: σ = |M|max / W contra σ_adm = 0.6·fy (ASD); hasta fy es aviso; más, error. En
    madera `fy` es el MOR y el criterio de la casa es MOR/4 (library/CLAUDE.md).
  - la carga útil es UNA puntual MÓVIL: se prueba en el centro de cada tramo y en la punta de
    cada voladizo y manda la envolvente (no se reparte: un paquete no se reparte).
"""

from __future__ import annotations

from dataclasses import dataclass

from .secciones import angulo_libre, seccion_catalogo
from .viga_continua import Apoyo, CargaPuntual, ResultadoViga, viga_continua

RATIO_FLECHA = 240.0
FACTOR_VOLADIZO = 2.0
FACTOR_SIGMA_ADM = 0.6
FACTOR_MADERA = 0.25  # σ_adm = MOR/4 (library/CLAUDE.md § Materiales)
#: Canal fuera de tabla en su eje DÉBIL: el prismático queda 12–15 % sobre la tabla (ala
#: cónica, F1) → se rebaja al borde inferior medido de la razón tabla/prismático.
FACTOR_UPN_DEBIL = 0.85
NORMA = ("AISC ASD 9.ª ed. (1989) F1: F_b = 0.60·F_y · flecha L/240 (AISC, criterio de "
         "serviciabilidad, carga total)")


@dataclass(frozen=True)
class Rigidez:
    """La sección ORIENTADA en la viga: I y W del eje en que flecta bajo carga vertical."""

    i_mm4: float
    w_mm3: float
    eje: str  # texto para la memoria
    fuente: str
    norma: str
    notas: tuple[str, ...] = ()
    i_arriostrada_mm4: float | None = None  # ángulo: la del eje geométrico, de referencia


def _dims_locales(familia: str, p: dict) -> tuple[float, float] | None:
    """(extensión en X local, en Y local) de la sección del builder (los perfiles se
    extruyen en Z)."""
    try:
        if familia == "rect_tube":
            return float(p["width"]), float(p["height"])
        if familia == "round_tube":
            return float(p["od"]), float(p["od"])
        if familia == "cylinder":
            return float(p["diameter"]), float(p["diameter"])
        if familia == "angle":
            return float(p["leg"]), float(p["leg"])
        if familia in ("channel", "i_beam"):
            return float(p["b"]), float(p["h"])
    except (KeyError, TypeError, ValueError):
        return None
    return None


def orientar_seccion(familia: str, params: dict, alto_mm: float, ancho_mm: float) -> Rigidez | str:
    """Rigidez de la viga cuya sección ocupa `alto_mm` en vertical y `ancho_mm` en horizontal
    (la caja del mundo). Un texto = no evaluable, con el motivo."""
    dims = _dims_locales(familia, params or {})
    sec = seccion_catalogo(familia, params or {})
    if dims is None or sec is None:
        return "sin sección de catálogo determinable"
    bx, by = dims

    def casa(a, b):
        return abs(a - b) <= max(1.0, 0.02 * b)

    if familia == "angle":
        if not (casa(alto_mm, bx) and casa(ancho_mm, bx)):
            return "sección girada respecto a la vertical (la caja no calza con el perfil)"
        lib = angulo_libre(params["leg"], params["t"])
        return Rigidez(
            lib.i_eq_mm4, lib.w_eq_mm3,
            f"ejes principales (ángulo libre: Iu = {lib.i_u_mm4 / 1e4:.1f}, Iv = "
            f"{lib.i_v_mm4 / 1e4:.1f} cm⁴)", lib.fuente, lib.norma,
            ("Ángulo L sin arriostramiento lateral verificable: flecta por sus ejes "
             "principales (módulo del desplazamiento, I_eq = √2/√(1/Iu² + 1/Iv²); σ en "
             "talón y puntas) — conservador frente al eje geométrico.",),
            i_arriostrada_mm4=lib.i_geometrica_mm4,
        )
    if casa(alto_mm, by) and casa(ancho_mm, bx):
        i, w, eje = sec.i_x_mm4, sec.w_x_mm3, f"eje X local (canto {by:g} mm vertical)"
        debil = sec.i_x_mm4 < sec.i_y_mm4 - 1e-9
    elif casa(alto_mm, bx) and casa(ancho_mm, by):
        i, w, eje = sec.i_y_mm4, sec.w_y_mm3, f"eje Y local (canto {bx:g} mm vertical)"
        debil = sec.i_y_mm4 < sec.i_x_mm4 - 1e-9
    else:
        return "sección girada respecto a la vertical (la caja no calza con el perfil)"
    notas: tuple[str, ...] = ()
    if debil:
        eje += ", eje DÉBIL"
    if familia == "channel" and debil and sec.fuente == "geometría":
        i, w = i * FACTOR_UPN_DEBIL, w * FACTOR_UPN_DEBIL
        notas = (f"Canal fuera de tabla en su eje débil: I y W prismáticos × {FACTOR_UPN_DEBIL:g} "
                 "(el ala cónica real es 12–15 % menos rígida).",)
    return Rigidez(i, w, eje, sec.fuente, sec.norma, notas)


def posiciones_moviles(largo: float, apoyos) -> list[float]:
    """Dónde se prueba la puntal móvil: el centro de cada tramo y la punta de cada voladizo."""
    xs = sorted(a.x_mm for a in apoyos)
    tol = 1e-6 * largo
    pos: list[float] = []
    if xs[0] > tol:
        pos.append(0.0)
    pos += [(a + b) / 2.0 for a, b in zip(xs, xs[1:])]
    if largo - xs[-1] > tol:
        pos.append(largo)
    return sorted(set(pos))


@dataclass(frozen=True)
class Envolvente:
    gobernante: ResultadoViga  # caso que manda (su reacción es la que baja a los apoyos)
    tramos: tuple[tuple[float, float, str, float, float], ...]  # desde, hasta, tipo, δ, límite
    momento_nmm: float
    momento_x_mm: float
    utilizacion_flecha: float
    tramo_critico: int


def envolvente(largo: float, ei: float, apoyos, cargas, carga_util_n: float) -> Envolvente:
    """Resuelve el caso sin carga útil o, con ella, uno por posición móvil, y arma la
    envolvente: la mayor |δ| de cada tramo y la mayor |M| de la viga."""
    apoyos, cargas = list(apoyos), list(cargas)
    if carga_util_n > 0:
        casos = [cargas + [CargaPuntual(x, carga_util_n)] for x in posiciones_moviles(largo, apoyos)]
    else:
        casos = [cargas]
    resultados = [viga_continua(largo, ei, apoyos, c) for c in casos]
    base = resultados[0].tramos
    tramos = []
    peor_u, critico, gob = -1.0, 0, resultados[0]
    for k, t in enumerate(base):
        d = max((r.tramos[k] for r in resultados), key=lambda tr: abs(tr.flecha_max_mm))
        luz = t.largo_mm * (FACTOR_VOLADIZO if t.tipo == "voladizo" else 1.0)
        lim = luz / RATIO_FLECHA
        tramos.append((t.desde_mm, t.hasta_mm, t.tipo, abs(d.flecha_max_mm), lim))
        u = abs(d.flecha_max_mm) / lim if lim > 0 else 0.0
        if u > peor_u:
            peor_u, critico = u, k
            gob = max(resultados, key=lambda r, k=k: abs(r.tramos[k].flecha_max_mm))
    m = max(resultados, key=lambda r: abs(r.momento_max_nmm))
    return Envolvente(gob, tuple(tramos), abs(m.momento_max_nmm), m.momento_x_mm, peor_u, critico)


def _estado(u: float, aviso_hasta: float) -> str:
    return "ok" if u <= 1.0 + 1e-9 else ("aviso" if u <= aviso_hasta + 1e-9 else "error")


def regla_viga(etiqueta: str, *, largo_mm: float, apoyos, cargas, carga_util_n: float,
               rigidez: Rigidez, material: str, e_mpa: float, fy_mpa: float, madera: bool,
               perfil: str, resumen_cargas: dict, hipotesis: list[str]) -> tuple[dict, Envolvente]:
    """La regla «flecha de viga» (formato de `rules._check` + `hipotesis` + `viga`) y su
    envolvente (la API de las reacciones que bajan por el bastidor)."""
    from ..rules import _check

    env = envolvente(largo_mm, e_mpa * rigidez.i_mm4, apoyos, cargas, carga_util_n)
    d0, d1, tipo, delta, lim = env.tramos[env.tramo_critico]
    luz = d1 - d0
    factor = FACTOR_MADERA if madera else FACTOR_SIGMA_ADM
    sigma_adm = factor * fy_mpa
    sigma = env.momento_nmm / rigidez.w_mm3
    u_sig = sigma / sigma_adm if sigma_adm > 0 else 0.0
    e_fle = _estado(env.utilizacion_flecha, 2.0)
    e_sig = _estado(u_sig, 1.0 / factor)
    orden = {"ok": 0, "aviso": 1, "error": 2}
    estado = max(e_fle, e_sig, key=orden.get)
    fs_vals = [lim / delta if delta > 0 else None, sigma_adm / sigma if sigma > 0 else None]
    fs = min((v for v in fs_vals if v is not None), default=None)
    ratio = f"L/{(luz * (FACTOR_VOLADIZO if tipo == 'voladizo' else 1)) / delta:.0f}" if delta > 0 else "—"
    apoyos_txt = ", ".join(f"{a.x_mm:.0f}" + (" (empotr.)" if a.tipo != "apoyo" else "")
                           for a in sorted(apoyos, key=lambda a: a.x_mm))
    entradas = {
        "perfil": f"{perfil} — {rigidez.norma} ({rigidez.fuente})",
        "flexión": rigidez.eje,
        "material": f"{material}: E = {e_mpa:.0f} MPa, fy = {fy_mpa:.0f} MPa",
        "I · W": f"{rigidez.i_mm4 / 1e4:.2f} cm⁴ · {rigidez.w_mm3 / 1e3:.2f} cm³",
        "largo": f"{largo_mm:.0f} mm",
        "apoyos (x)": f"{apoyos_txt} mm",
        **resumen_cargas,
    }
    sustitucion = (f"EI = {e_mpa:.0f}·{rigidez.i_mm4:.4g} = {e_mpa * rigidez.i_mm4:.4g} N·mm²; "
                   f"σ = {env.momento_nmm:.4g} / {rigidez.w_mm3:.4g} = {sigma:.1f} MPa")
    por_tramo = "; ".join(f"{t[2]} {t[0]:.0f}–{t[1]:.0f}: δ = {t[3]:.2f} mm (lím. {t[4]:.2f})"
                          for t in env.tramos)
    resultado = (f"{por_tramo}. Manda el {tipo} {d0:.0f}–{d1:.0f} mm ({ratio}); "
                 f"|M| = {env.momento_nmm / 1e6:.3f} kN·m en x = {env.momento_x_mm:.0f} mm; "
                 f"σ = {sigma:.1f} MPa")
    criterio = (f"δ ≤ L/{RATIO_FLECHA:.0f} por vano, ≤ {FACTOR_VOLADIZO:g}·Lv/{RATIO_FLECHA:.0f} en "
                f"voladizo (aquí {lim:.2f} mm); σ ≤ {'MOR/4' if madera else '0.6·fy'} = "
                f"{sigma_adm:.0f} MPa")
    detalle = (f"{etiqueta}: δ = {delta:.2f} mm en el {tipo} de {luz:.0f} mm (límite {lim:.2f} mm, "
               f"{ratio}); σ = {sigma:.1f} MPa (admisible {sigma_adm:.0f}).")
    recomendacion = None
    if e_fle != "ok":
        recomendacion = ("Acorta el vano (apoyo intermedio), sube el canto o cambia a un perfil de "
                         "mayor inercia.")
    if e_sig != "ok":
        recomendacion = ((recomendacion + " ") if recomendacion else "") + (
            "La tensión de flexión excede la admisible: perfil de mayor módulo resistente W.")
    regla = _check(
        f"flecha de viga · {etiqueta}", estado, detalle, recomendacion,
        calc={"titulo": f"Viga continua: {etiqueta}", "entradas": entradas,
              "formula": "viga continua Euler-Bernoulli sobre sus apoyos (rigidez directa, "
                         "Hermite): δ máx por tramo; σ = |M|máx / W",
              "sustitucion": sustitucion, "resultado": resultado, "criterio": criterio,
              "fs": round(fs, 2) if fs is not None else None, "norma": NORMA},
    )
    regla["hipotesis"] = [*rigidez.notas, *hipotesis]
    regla["viga"] = {
        "largo_mm": round(largo_mm, 1),
        "apoyos_mm": [round(a.x_mm, 1) for a in sorted(apoyos, key=lambda a: a.x_mm)],
        "flecha_mm": round(delta, 6), "limite_mm": round(lim, 4),
        "tramo": [round(d0, 1), round(d1, 1), tipo],
        "tramos": [{"desde_mm": round(t[0], 1), "hasta_mm": round(t[1], 1), "tipo": t[2],
                    "flecha_mm": round(t[3], 6), "limite_mm": round(t[4], 4)} for t in env.tramos],
        "momento_nmm": round(env.momento_nmm, 3), "sigma_mpa": round(sigma, 3),
        "sigma_adm_mpa": round(sigma_adm, 1), "i_mm4": round(rigidez.i_mm4, 1),
        "w_mm3": round(rigidez.w_mm3, 1),
    }
    return regla, env


__all__ = ["Apoyo", "Envolvente", "Rigidez", "envolvente", "orientar_seccion",
           "posiciones_moviles", "regla_viga"]
