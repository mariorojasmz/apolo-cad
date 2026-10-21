"""`engineering_check` del transportador de rodillos por cadena (plan
`docs/plans/plantilla-rodillos-cadena.md`, D9): la plantilla validada contra la FICHA del
encargo (`Document.requirements`). PURO: recibe los params resueltos del comando y los datos
de la ficha; lo llama `rules.conveyor_engineering_check` cuando el transportador del documento
es un `create_roller_conveyor` (`services/engineering_rules.conveyor_params_from_doc`).

En la ficha, `carga_kg` es la masa de UN paquete (como en `conveyor_engineering_check`); en la
plantilla, `carga_kg` es la carga TOTAL con que se dimensionaron vano y motor.

Reglas (formato de `rules._check`, con `calc`):
- velocidad del producto contra la de la ficha, ±10 % (criterio «0.9 × objetivo»);
- apoyo del paquete: ≥ 3 rodillos debajo;
- capacidad del rodillo: 2 × 6201 a L10 = 20 000 h (ISO 281) y eje M12 a σ ≤ 0.5·σy;
- ancho útil contra el ancho del paquete;
- carga de diseño: la ficha con el transportador LLENO de paquetes contra `carga_kg`;
- motor (P_motor / P_requerida) y cadena (tabla ACA, servicio moderado, con el par nominal
  del motor en el primer lazo): FS < 1 = error, < 1.2 = aviso;
- recorrido de tensado: el de las orejas contra el estirado de reemplazo (3 %).
"""

from __future__ import annotations

import math

from .catalog import CATALOG
from .engineering.bearings import L10_MIN_H, L10_TARGET_H, l10_hours
from .materials import YIELD_MPA
from .rules import _check
from .transmision import (
    HP_A_KW, factor_hileras, factor_servicio, potencia_nominal_asa40_1_hp,
)

FS_AVISO = 1.2
D3_M12 = 9.853             # diámetro de núcleo de la rosca M12 (ISO 724)
RODAMIENTOS_POR_RODILLO = 2
APOYOS_MIN = 3


def _fs_estado(fs: float) -> str:
    return "error" if fs < 1.0 else ("aviso" if fs < FS_AVISO else "ok")


def _velocidad(d, v_ficha: float) -> dict | None:
    if d.velocidad_m_s is None:
        return None
    v = d.velocidad_m_s
    m = d.motriz
    calc = {"titulo": "Velocidad del producto",
            "entradas": {"motor": f"{m.motor} ({m.rpm:g} rpm)",
                         "piñones": f"Z{m.z_pinon} del motor → Z15 del rodillo",
                         "Ø tubo": f"{d.d_rodillo:g} mm",
                         "ficha": f"{v_ficha:g} m/s" if v_ficha else "—"},
            "formula": "v = π·Ø·n·z_motor/z_rodillo / 60 000",
            "sustitucion": f"v = π·{d.d_rodillo:g}·{m.rpm:g}·{m.z_pinon}/15 / 60 000",
            "resultado": f"v = {v:.3f} m/s ({v * 60:.1f} m/min)",
            "criterio": "|v − v_ficha| ≤ 10 % de v_ficha" if v_ficha else "informativo",
            "fs": None, "norma": "criterio de diseño (el «0.9 × objetivo» de la velocidad de banda)"}
    if v_ficha and abs(v - v_ficha) > 0.10 * v_ficha:
        return _check("velocidad del producto", "aviso",
                      f"La plantilla da {v:.3f} m/s y la ficha pide {v_ficha:g} m/s "
                      f"({(v / v_ficha - 1) * 100:+.0f} %).",
                      f"Da velocidad_m_s={v_ficha:g} al create_roller_conveyor: elige el piñón del "
                      "motor que la da.", calc=calc)
    return _check("velocidad del producto", "ok", f"{v:.3f} m/s ({v * 60:.1f} m/min).", calc=calc)


def _apoyo(d, largo_paq: float) -> tuple[dict, int]:
    n = math.floor(largo_paq / d.paso)
    det = f"El paquete de {largo_paq:g} mm apoya en {n} rodillos (paso {d.paso:g} mm)."
    calc = {"titulo": "Apoyo del paquete", "entradas": {"paquete": f"{largo_paq:g} mm",
                                                        "paso": f"{d.paso:g} mm"},
            "formula": "n = ⌊L_paquete / paso⌋", "sustitucion": f"n = ⌊{largo_paq:g}/{d.paso:g}⌋",
            "resultado": f"n = {n}", "criterio": f"n ≥ {APOYOS_MIN}", "fs": None,
            "norma": "criterio de diseño (≥ 3 rodillos bajo el paquete)"}
    if n >= APOYOS_MIN:
        return _check("apoyo del paquete", "ok", det, calc=calc), n
    estado = "aviso" if n == 2 else "error"
    return _check("apoyo del paquete", estado, det,
                  f"Usa un paquete ≥ {APOYOS_MIN * d.paso:.0f} mm o un paso menor.", calc=calc), n


def _capacidad(d, m_paq: float, n_apoyos: int) -> dict:
    """Carga por rodillo contra 2 × 6201 (L10 ≥ 20 000 h) y el eje M12 (σ ≤ 0.5·σy), con la
    carga repartida en partes iguales entre los rodillos bajo el paquete."""
    from .rodillos_cadena import RODAMIENTO, TAPA_ESPESOR

    p_n = m_paq * 9.81 / max(1, n_apoyos)
    a2, t = d.ancho_util / 2.0, float(CATALOG["ANG-75X6"].specs["t"])
    e_m = (-a2 + TAPA_ESPESOR / 2.0) - (d.y_in_m - t / 2.0)  # rodamiento ↔ mitad del ala
    e_p = (d.y_in_p + t / 2.0) - (a2 - TAPA_ESPESOR / 2.0)
    luz = (d.y_in_p + t / 2.0) - (d.y_in_m - t / 2.0)
    # viga simplemente apoyada en las dos alas con P/2 en cada rodamiento: el momento máximo
    # está bajo el rodamiento del voladizo mayor
    f = p_n / RODAMIENTOS_POR_RODILLO
    r_m = f * (luz - e_m) / luz + f * e_p / luz
    r_p = 2.0 * f - r_m
    m_max = max(r_m * e_m, r_p * e_p)
    w = math.pi * D3_M12 ** 3 / 32.0
    sigma, sy = m_max / w, YIELD_MPA["acero"]
    c_kn = float(CATALOG[RODAMIENTO].specs["C_kN"])
    rpm = d.velocidad_m_s * 60000.0 / (math.pi * d.d_rodillo) if d.velocidad_m_s else None
    vida = l10_hours(c_kn, f / 1000.0, rpm) if rpm else None
    # carga por rodillo que deja L10 = 20 000 h y σ = 0.5·σy
    p_l10 = (c_kn * 1000.0 * RODAMIENTOS_POR_RODILLO / (L10_TARGET_H * 60.0 * rpm / 1e6) ** (1 / 3)
             if rpm else math.inf)
    p_eje = p_n * 0.5 * sy / sigma if sigma > 0 else math.inf
    capacidad = min(p_l10, p_eje)
    fs = capacidad / p_n if p_n > 0 else None
    entradas = {"paquete": f"{m_paq:g} kg sobre {n_apoyos} rodillo(s)",
                "rodamientos": f"{RODAMIENTOS_POR_RODILLO} × {RODAMIENTO} (C = {c_kn:g} kN)",
                "eje": f"M12 (núcleo Ø{D3_M12:g}), voladizos {e_m:.1f} / {e_p:.1f} mm, luz {luz:.0f} mm",
                "rpm del rodillo": f"{rpm:.0f}" if rpm else "sin velocidad (no se evalúa L10)"}
    if vida is None:
        vida_txt = "L10 no evaluada"
    else:
        vida_txt = "L10 > 10⁶ h" if vida > 1e6 else f"L10 = {vida:.0f} h"
    calc = {"titulo": "Capacidad del rodillo", "entradas": entradas,
            "formula": "P = m·g/n; L10h = (C/(P/2))³·10⁶/(60·n_rpm); σ = M/(π·d³/32)",
            "sustitucion": f"P = {p_n:.0f} N; M = {m_max:.0f} N·mm; σ = {sigma:.0f} MPa",
            "resultado": f"{vida_txt}; σ = {sigma:.0f} MPa; capacidad {capacidad / 9.81:.0f} kg/rodillo",
            "criterio": f"L10 ≥ {L10_TARGET_H:.0f} h · σ ≤ 0.5·σy = {0.5 * sy:g} MPa",
            "fs": round(fs, 2) if fs else None,
            "norma": "ISO 281 (L10) · eje σ ≤ 0.5·σy (criterio de diseño, más estricto que "
                     "ASME B106.1M)"}
    det = (f"{p_n / 9.81:.1f} kg/rodillo: {vida_txt}, eje M12 a {sigma:.0f} MPa "
           f"(capacidad {capacidad / 9.81:.0f} kg/rodillo).")
    if (vida is not None and vida < L10_MIN_H) or sigma > sy:
        return _check("capacidad de rodillo", "error", det,
                      "Reparte el paquete en más rodillos (paso menor) o pasa a un eje mayor.",
                      calc=calc)
    if (vida is not None and vida < L10_TARGET_H) or sigma > 0.5 * sy:
        return _check("capacidad de rodillo", "aviso", det,
                      "Reparte el paquete en más rodillos (paso menor) o pasa a un eje mayor.",
                      calc=calc)
    return _check("capacidad de rodillo", "ok", det, calc=calc)


def _carga_diseno(d, m_paq: float, largo_paq: float) -> tuple[dict, float]:
    n = max(1, math.floor(d.largo / largo_paq))
    total = n * m_paq
    calc = {"titulo": "Carga de diseño", "entradas": {
                "ficha": f"{m_paq:g} kg por paquete de {largo_paq:g} mm",
                "plantilla": f"carga_kg = {d.carga_kg:g} kg (vano y motor)"},
            "formula": "Q = ⌊largo / L_paquete⌋ · m_paquete (transportador lleno, sin huecos)",
            "sustitucion": f"Q = ⌊{d.largo:g}/{largo_paq:g}⌋·{m_paq:g} = {n}·{m_paq:g}",
            "resultado": f"Q = {total:g} kg", "criterio": f"Q ≤ carga_kg = {d.carga_kg:g} kg",
            "fs": round(d.carga_kg / total, 2) if total else None, "norma": "criterio de diseño"}
    det = (f"Lleno de paquetes lleva {n} × {m_paq:g} = {total:g} kg; la plantilla se dimensionó "
           f"para {d.carga_kg:g} kg.")
    if total > d.carga_kg:
        return _check("carga de diseño", "error", det,
                      f"Da carga_kg ≥ {total:g} al create_roller_conveyor (vano y motor se "
                      "recalculan).", calc=calc), total
    return _check("carga de diseño", "ok", det, calc=calc), total


def _motor(d, carga_total: float) -> dict:
    from .rodillos_cadena import _masa_rodillo, potencia_requerida

    m = d.motriz
    carga = max(d.carga_kg, carga_total)
    m_rod = len(d.xs) * _masa_rodillo(d.rodillo, d.ancho_util, d.eje_y1 - d.eje_y0, True)
    p_req = potencia_requerida(carga, m_rod, d.velocidad_m_s, len(d.xs))
    fs = m.potencia_kw / p_req
    calc = {"titulo": "Potencia del motor", "entradas": {
                "carga": f"{carga:g} kg + rodillos {m_rod:.0f} kg", "v": f"{d.velocidad_m_s:.3f} m/s",
                "motor": f"{m.motor} ({m.potencia_kw:g} kW)"},
            "formula": "P = 1.5·μ·(Q + m_rodillos)·g·v / (η_lazos·η_reductor)",
            "sustitucion": f"P = 1.5·0.05·{carga + m_rod:.0f}·9.81·{d.velocidad_m_s:.3f} / η",
            "resultado": f"P = {p_req:.3f} kW → FS {fs:.2f}",
            "criterio": f"FS ≥ 1 (aviso bajo {FS_AVISO:g})", "fs": round(fs, 2),
            "norma": "criterio de diseño (rodadura 5 %, arranque ×1.5, η lazo 0.98, reductor 0.85)"}
    return _check("motor", _fs_estado(fs), f"{m.motor}: pide {p_req:.3f} kW de {m.potencia_kw:g} kW "
                  f"(FS {fs:.2f}).", "Elige un motorreductor mayor." if fs < FS_AVISO else None,
                  calc=calc)


def _cadena(d) -> dict:
    from .rodillos_cadena import PINON_RODILLO

    m = d.motriz
    zc = min(m.z_pinon, int(CATALOG[PINON_RODILLO].specs["z"]))
    rpm_c = m.rpm * m.z_pinon / zc
    hp = potencia_nominal_asa40_1_hp(zc, rpm_c)
    if hp is None:
        return _check("cadena", "aviso", f"z{zc} a {rpm_c:.0f} rpm queda fuera de la tabla ACA: "
                      "no se verifica la capacidad.", "Verifica con el fabricante de la cadena.")
    cap = hp * HP_A_KW * factor_hileras(1)
    dis = m.potencia_kw * factor_servicio("moderado")
    fs = cap / dis
    calc = {"titulo": "Cadena (primer lazo)", "entradas": {
                "potencia": f"{m.potencia_kw:g} kW nominales del motor · servicio moderado ×1.3",
                "piñón chico": f"z{zc} a {rpm_c:.0f} rpm"},
            "formula": "FS = P_nom(z, n)·f_h / (P·f_s)",
            "sustitucion": f"FS = {hp:.2f}·{HP_A_KW:.4f} / ({m.potencia_kw:g}·1.3)",
            "resultado": f"capacidad {cap:.2f} kW, diseño {dis:.2f} kW → FS {fs:.2f}",
            "criterio": f"FS ≥ 1 (aviso bajo {FS_AVISO:g})", "fs": round(fs, 2),
            "norma": "ASME B29.1 (tabla ACA de la ASA 40-1)"}
    return _check("cadena", _fs_estado(fs), f"La cadena motriz y el primer lazo llevan el par "
                  f"nominal del {m.motor}: FS {fs:.2f}.",
                  "Pasa a cadena doble o a un paso mayor, o baja el motor." if fs < FS_AVISO else None,
                  calc=calc)


def _tensado(d) -> dict:
    from .rodillos_cadena_motriz import tensado_requerido

    m = d.motriz
    req = tensado_requerido(m.eslabones, 12.7)
    calc = {"titulo": "Recorrido de tensado", "entradas": {
                "cadena motriz": f"{m.eslabones} eslabones ({m.eslabones * 12.7:.0f} mm)",
                "ranuras": f"+{m.tensado_mm:.1f} / −{m.montaje_mm:g} mm sobre la línea de centros"},
            "formula": "Δc = 3 % · L / 2", "sustitucion": f"Δc = 0.03·{m.eslabones * 12.7:.0f}/2",
            "resultado": f"Δc = {req:.1f} mm", "criterio": "recorrido ≥ Δc", "fs": None,
            "norma": "criterio de diseño (estirado de reemplazo 3 %: Tsubaki, Renold)"}
    estado = "ok" if m.tensado_mm >= req - 1e-6 else "error"
    return _check("recorrido de tensado", estado,
                  f"El portamotor corre +{m.tensado_mm:.1f} mm (pide {req:.1f}) y −{m.montaje_mm:g} "
                  "mm para el eslabón de unión.", calc=calc)


def reglas_rodillos_cadena(params: dict, carga_kg: float, largo_paquete_mm: float,
                           velocidad_m_s: float = 0.0,
                           ancho_paquete_mm: float | None = None) -> list[dict]:
    """Las reglas de la plantilla contra la ficha (paquete de `carga_kg` y `largo_paquete_mm`)."""
    from .rodillos_cadena import disposicion

    try:
        d = disposicion(params["largo"], params["ancho_util"], params["paso"], params["rodillo"],
                        params["altura"], params["carga_kg"], params["motriz"] == "cadena",
                        params["motor"], params.get("velocidad_m_s"))
    except (ValueError, KeyError) as exc:
        return [_check("transportador de rodillos", "error", f"La plantilla no se arma: {exc}")]
    reglas = []
    if (r := _velocidad(d, velocidad_m_s)) is not None:
        reglas.append(r)
    apoyo, n = _apoyo(d, largo_paquete_mm)
    reglas += [apoyo, _capacidad(d, carga_kg, n)]
    if ancho_paquete_mm:
        holgura = d.ancho_util - ancho_paquete_mm
        estado = "ok" if holgura >= 40 else ("aviso" if holgura >= 0 else "error")
        reglas.append(_check("ancho útil", estado,
                             f"Tubo de {d.ancho_util:g} mm para un paquete de {ancho_paquete_mm:g} "
                             f"mm (holgura {holgura:.0f} mm).",
                             None if estado == "ok" else "Sube ancho_util o agrega guías laterales."))
    carga, total = _carga_diseno(d, carga_kg, largo_paquete_mm)
    reglas.append(carga)
    if d.motriz is not None:
        reglas += [_motor(d, total), _cadena(d), _tensado(d)]
    return reglas
