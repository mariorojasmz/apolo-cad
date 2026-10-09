"""Regla «transmisión por cadena» (plan `docs/plans/cadenas-pinones.md`, D9): PURA, recibe los
números de un lazo (los mide `commands/exec_transmision.medir_transmision`, los junta
`services/transmision_rules.py`) y devuelve una regla con su bloque `calc`, en el formato de
`rules.py` ({regla, estado, detalle, recomendacion?, calc}) más `no_aplica`: la lista de lo
que no se pudo verificar y por qué (jamás se inventa una capacidad).

- ERROR: eslabones impares (el comando no los produce), abrazamiento del piñón chico < 120° o
  potencia de diseño mayor que la capacidad.
- AVISO: z del chico < 17, relación > 7.6, flecha del ramal flojo > 4 % del vano (lo que sobra
  de cadena por redondear a eslabones pares), centros fuera de 30–50 p SALVO en un lazo 1:1
  corto (el rodillo a rodillo va a 6–12 p por diseño) y velocidad > 4 m/s (lubricación).
- Capacidad: P·f_servicio ≤ P_nominal(z_chico, rpm_chico)·f_hileras con la tabla ACA de la
  ASA 40-1 (ASME B29.1). La 08B usa esa tabla como sustituto DECLARADO (su rotura es mayor:
  17.8 contra 13.9 kN); la 10B y la 12B, y z o rpm fuera de la tabla, van a `no_aplica`.
"""

from __future__ import annotations

import math

from ..rules import _check
from ..transmision import (
    HP_A_KW, abrazamiento_deg, camino_paso, eslabones_para_centros, factor_hileras,
    factor_servicio, potencia_nominal_asa40_1_hp, velocidad_cadena,
)

ABRAZAMIENTO_MIN_DEG = 120.0
Z_MIN_NORMAL = 17
RELACION_MAX = 7.6
CENTROS_PASOS = (30.0, 50.0)
FLECHA_MAX_PCT = 4.0
V_GRASA_MAX = 4.0
#: Series con capacidad tabulada: la propia ASA 40-1 y la 08B como sustituto declarado.
_SERIES_TABLA = {"ASA 40": False, "08B": True}


def flecha_ramal_flojo(paso: float, za: int, zb: int, centros: float, eslabones: int) -> tuple:
    """(vano mm, cadena sobrante mm, flecha mm): lo que sobra al redondear a eslabones pares
    cuelga en el ramal flojo; flecha de la parábola que alarga el vano en ese sobrante,
    ΔL = 8f²/(3s) → f = √(3·s·ΔL/8)."""
    vano = camino_paso(paso, za, zb, centros).largo_tramo
    sobra = max(0.0, (eslabones - eslabones_para_centros(paso, za, zb, centros)) * paso)
    return vano, sobra, math.sqrt(3.0 * vano * sobra / 8.0)


def regla_cadena(nombres: list[str], *, cadena: str, serie: str, paso: float, hileras: int,
                 za: int, zb: int, centros: float, eslabones: int, centros_exactos: float,
                 potencia_kw: float | None = None, rpm_a: float | None = None,
                 servicio: str = "moderado") -> dict:
    """Regla de UN lazo (o de varios idénticos: `nombres` lista sus nombres). A = motriz."""
    zc, zg = min(za, zb), max(za, zb)
    relacion = zg / zc
    pasos = centros / paso
    abraz = abrazamiento_deg(paso, za, zb, centros)
    vano, sobra, flecha = flecha_ramal_flojo(paso, za, zb, centros, eslabones)
    flecha_pct = 100.0 * flecha / vano if vano > 0 else 0.0
    errores: list[tuple[str, str]] = []
    avisos: list[tuple[str, str]] = []
    no_aplica: list[str] = []

    if eslabones % 2:
        errores.append((f"{eslabones} eslabones impares", "Usa un número par: impar exige "
                        "eslabón acodado, que desclasifica la cadena."))
    if abraz < ABRAZAMIENTO_MIN_DEG:
        errores.append((f"abrazamiento {abraz:.0f}° < {ABRAZAMIENTO_MIN_DEG:g}° en el piñón chico",
                        "Separa los centros o baja la relación (o agrega un tensor)."))
    if zc < Z_MIN_NORMAL:
        avisos.append((f"piñón chico de {zc} dientes (< {Z_MIN_NORMAL})",
                       "Con menos de 17 dientes, sólo para servicio lento y liviano."))
    if relacion > RELACION_MAX:
        avisos.append((f"relación {relacion:.2f} > {RELACION_MAX:g}",
                       "Reparte la reducción en dos etapas."))
    if flecha_pct > FLECHA_MAX_PCT:
        avisos.append((
            f"sobran {sobra:.1f} mm de cadena: flecha ≈ {flecha:.0f} mm ({flecha_pct:.1f} % del "
            f"vano, > {FLECHA_MAX_PCT:g} %)",
            f"Lleva los centros a {centros_exactos:.2f} mm (el exacto de {eslabones} eslabones) o "
            "deja recorrido de tensado (motor sobre ranuras).",
        ))
    corto_1a1 = za == zb and pasos < CENTROS_PASOS[0]
    if not corto_1a1 and not CENTROS_PASOS[0] <= pasos <= CENTROS_PASOS[1]:
        avisos.append((f"centros a {pasos:.1f} pasos (fuera de 30–50 p)",
                       "Lo recomendado son 30–50 pasos entre centros."))

    v = None
    if rpm_a:
        v = velocidad_cadena(paso, za, rpm_a)
        if v > V_GRASA_MAX:
            avisos.append((f"cadena a {v:.2f} m/s (> {V_GRASA_MAX:g} m/s con grasa)",
                           "Lubrica por goteo o en baño de aceite."))
    else:
        no_aplica.append("velocidad y potencia: falta rpm_a (rpm del piñón motriz)")

    pot = None
    if rpm_a and not potencia_kw:
        no_aplica.append("potencia: falta potencia_kw")
    elif rpm_a and potencia_kw:
        rpm_c = rpm_a * za / zc
        if serie not in _SERIES_TABLA:
            no_aplica.append(f"potencia: la {serie} no tiene tabla numérica publicada; no se "
                             "inventa una capacidad")
        else:
            hp = potencia_nominal_asa40_1_hp(zc, rpm_c)
            if hp is None:
                no_aplica.append(f"potencia: z{zc} a {rpm_c:.0f} rpm queda fuera de la tabla ACA "
                                 "(z 14–19, 10–1000 rpm); no se extrapola")
            else:
                fsv, fh = factor_servicio(servicio), factor_hileras(hileras)
                diseno = potencia_kw * fsv
                capacidad = hp * HP_A_KW * fh
                pot = {"rpm_c": rpm_c, "hp": hp, "fsv": fsv, "fh": fh, "diseno": diseno,
                       "capacidad": capacidad, "fs": capacidad / diseno,
                       "sustituto": _SERIES_TABLA[serie]}
                if diseno > capacidad:
                    errores.append((
                        f"potencia de diseño {diseno:.2f} kW > capacidad {capacidad:.2f} kW",
                        "Sube el número de dientes, pasa a cadena doble o a un paso mayor.",
                    ))

    estado = "error" if errores else ("aviso" if avisos else "ok")
    etiqueta = nombres[0] if len(nombres) == 1 else f"{nombres[0]} y {len(nombres) - 1} lazo(s) iguales"
    entradas = {
        "cadena": f"{cadena} ({serie}, paso {paso:g} mm, {hileras} hilera(s))",
        "piñones": f"A z{za} (motriz) · B z{zb} · relación {relacion:.2f}",
        "centros": f"{centros:.2f} mm = {pasos:.1f} p",
        "eslabones": f"{eslabones} (centro exacto {centros_exactos:.2f} mm, holgura "
                     f"{centros_exactos - centros:.2f} mm)",
        "abrazamiento": f"{abraz:.0f}° en el piñón chico",
        "flecha": f"{flecha:.1f} mm ({flecha_pct:.1f} % del vano de {vano:.0f} mm)",
        "velocidad": f"{v:.2f} m/s" if v is not None else "sin rpm_a",
    }
    if len(nombres) > 1:
        entradas["lazos iguales"] = f"{len(nombres)}: " + ", ".join(nombres[:5]) + (
            "…" if len(nombres) > 5 else "")
    formula = "L = (z1+z2)/2 + 2C/p + p·((z2−z1)/2π)²/C → par; v = z·p·n/60 000"
    sustitucion = (f"L = ({za}+{zb})/2 + 2·{centros:.2f}/{paso:g} + … = "
                   f"{eslabones_para_centros(paso, za, zb, centros):.2f} → {eslabones}")
    resultado = f"{eslabones} eslabones (L = {eslabones * paso:.1f} mm), abrazamiento {abraz:.0f}°"
    criterio = ("eslabones pares · abrazamiento ≥ 120° · z ≥ 17 · relación ≤ 7.6 · C 30–50 p "
                "(salvo 1:1 corto) · flecha ≤ 4 % · v ≤ 4 m/s con grasa")
    norma = "ANSI B29.1 / ISO 606 · criterio de diseño (Tsubaki «Chain Drive Selection», Renold)"
    if pot:
        entradas["potencia"] = (f"{potencia_kw:g} kW · servicio {servicio} (×{pot['fsv']:g}) · "
                                f"piñón chico a {pot['rpm_c']:.0f} rpm")
        entradas["capacidad"] = (f"{pot['hp']:.2f} HP (ACA, ASA 40-1, z{zc}) × {pot['fh']:g} por "
                                 f"hileras = {pot['capacidad']:.2f} kW")
        formula += "; P·f_s ≤ P_nom(z, n)·f_h"
        sustitucion += (f"; {potencia_kw:g}·{pot['fsv']:g} = {pot['diseno']:.2f} kW ≤ "
                        f"{pot['hp']:.2f}·{HP_A_KW:.4f}·{pot['fh']:g} = {pot['capacidad']:.2f} kW")
        resultado += f", FS de potencia {pot['fs']:.2f}"
        criterio += " · P·f_s ≤ P_nom·f_h"
        norma = "ASME B29.1 (tabla ACA)" + (
            " de la ASA 40-1 como sustituto DECLARADO de la 08B (más fuerte: 17.8 contra 13.9 kN)"
            if pot["sustituto"] else "") + " · criterio de diseño (Tsubaki, Renold)"
    if v is not None:
        resultado += f", v = {v:.2f} m/s"
    hallazgos = [t for t, _r in errores + avisos]
    detalle = (f"{etiqueta}: {cadena}, z{za}→z{zb}, C = {centros:.2f} mm, {eslabones} eslabones, "
               f"abrazamiento {abraz:.0f}°" + (f", v = {v:.2f} m/s" if v is not None else "")
               + (f", FS de potencia {pot['fs']:.2f}" if pot else "")
               + (". " + "; ".join(hallazgos) if hallazgos else "") + "."
               + (f" No aplica: {'; '.join(no_aplica)}." if no_aplica else ""))
    regla = _check(
        f"transmisión por cadena · {etiqueta}", estado, detalle,
        " ".join(r for _t, r in errores + avisos) or None,
        calc={"titulo": f"Transmisión por cadena {etiqueta}", "entradas": entradas,
              "formula": formula, "sustitucion": sustitucion, "resultado": resultado,
              "criterio": criterio, "fs": round(pot["fs"], 2) if pot else None, "norma": norma},
    )
    regla["no_aplica"] = no_aplica
    return regla
