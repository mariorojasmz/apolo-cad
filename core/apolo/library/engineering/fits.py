"""Ajustes y tolerancias ISO 286 (V5.4): límites de agujero/eje y criterio de asientos.

TABLAS, no fórmulas: `IT_UM` (grados 5–11) y `SHAFT_DEV_UM` (desviaciones
fundamentales de eje) transcritas de ISO 286-1 para nominales 1–500 mm; los
AGUJEROS se derivan con las reglas exactas de la norma (H→EI=0; G/F→espejo de
g/f; JS→±IT/2; K/M/N/P grados 6–7 → ES = −ei(eje) + Δ, con Δ = ITn − IT(n−1)).
Los valores se verifican en tests contra límites PUBLICADOS (Ø20 H7 = +21/0,
Ø25 K7 = +6/−15, …). Letra/grado fuera de soporte → KeyError claro (patrón
bolts.py). El bore de un rodamiento/inserto NO es ISO 286: usa ISO 492 clase
Normal (`BEARING_BORE_TOL_UM`, Δdmp 0/−t).

Unidades: mm para nominales/límites, µm para desviaciones. Funciones PURAS
(jamás Document). Convención: desviación = medida − nominal; juego = agujero −
eje (negativo = apriete).
"""

from __future__ import annotations

import re

# rangos nominales ISO 286 ("más de a, hasta b incluido"), 1–500 mm
_RANGES = (3, 6, 10, 18, 30, 50, 80, 120, 180, 250, 315, 400, 500)

# IT en µm por grado, en el orden de _RANGES
IT_UM: dict[int, tuple[float, ...]] = {
    5: (4, 5, 6, 8, 9, 11, 13, 15, 18, 20, 23, 25, 27),
    6: (6, 8, 9, 11, 13, 16, 19, 22, 25, 29, 32, 36, 40),
    7: (10, 12, 15, 18, 21, 25, 30, 35, 40, 46, 52, 57, 63),
    8: (14, 18, 22, 27, 33, 39, 46, 54, 63, 72, 81, 89, 97),
    9: (25, 30, 36, 43, 52, 62, 74, 87, 100, 115, 130, 140, 155),
    10: (40, 48, 58, 70, 84, 100, 120, 140, 160, 185, 210, 230, 250),
    11: (60, 75, 90, 110, 130, 160, 190, 220, 250, 290, 320, 360, 400),
}

# desviación FUNDAMENTAL de eje en µm: para g/f/h es la SUPERIOR (es, ≤0);
# para k/m/n/p es la INFERIOR (ei, ≥0). js se calcula (±IT/2).
SHAFT_DEV_UM: dict[str, tuple[float, ...]] = {
    "g": (-2, -4, -5, -6, -7, -9, -10, -12, -14, -15, -17, -18, -20),
    "f": (-6, -10, -13, -16, -20, -25, -30, -36, -43, -50, -56, -62, -68),
    "h": (0,) * 13,
    "k": (0, 1, 1, 1, 2, 2, 2, 3, 3, 4, 4, 4, 5),  # válida en grados 4–7
    "m": (2, 4, 6, 7, 8, 9, 11, 13, 15, 17, 20, 21, 23),
    "n": (4, 8, 10, 12, 15, 17, 20, 23, 27, 31, 34, 37, 40),
    "p": (6, 12, 15, 18, 22, 26, 32, 37, 43, 50, 56, 62, 68),
}

# grados soportados por letra (fuera de esto → KeyError con mensaje claro)
_SHAFT_GRADES = {
    "h": range(5, 12), "g": range(5, 8), "f": range(6, 8), "js": range(5, 7),
    "k": range(5, 8), "m": range(5, 7), "n": range(5, 7), "p": range(5, 7),
}
_HOLE_GRADES = {
    "H": range(6, 12), "G": range(6, 8), "F": range(7, 9), "JS": range(6, 10),
    "K": range(6, 8), "M": range(6, 8), "N": range(6, 8), "P": range(6, 8),
}

# ISO 492 clase Normal: tolerancia del bore de rodamiento/inserto (Δdmp = 0/−t µm),
# por diámetro nominal del bore
_BEARING_BORE_RANGES = (10, 18, 30, 50, 80, 120, 180)
BEARING_BORE_TOL_UM = (8, 8, 10, 12, 15, 20, 25)

# recomendación de ajuste de EJE por TIPO DE MONTAJE (criterio, no fabricante)
SEAT_RECOMMENDATIONS: dict[str, dict] = {
    "chumacera_inserto": {
        "ok": {"h6", "h7", "g6", "js6"}, "tipico": "h7",
        "nota": "el eje debe DESLIZAR en el inserto UC; la fijación la dan los prisioneros/collar",
    },
    "rodamiento_anillo_giratorio": {
        "ok": {"k5", "k6", "m5", "m6"}, "tipico": "k6",
        "nota": "anillo interior GIRATORIO con carga normal → montaje a presión",
    },
    "rodamiento_anillo_fijo": {
        "ok": {"g6", "h6", "js6", "f6"}, "tipico": "g6",
        "nota": "anillo interior ESTACIONARIO → deslizante/juego",
    },
}

_FIT_RE = re.compile(r"^\s*(?:(\d+(?:\.\d+)?)\s*)?(JS|js|[HGFKMNP]|[hgfkmnp])\s*(\d{1,2})\s*$")


def _range_idx(nominal_mm: float) -> int:
    if not 1.0 <= nominal_mm <= 500.0:
        raise KeyError(f"Nominal {nominal_mm:g} mm fuera de la tabla ISO 286 (1–500 mm)")
    for i, hi in enumerate(_RANGES):
        if nominal_mm <= hi:
            return i
    raise KeyError(f"Nominal {nominal_mm:g} mm fuera de rango")  # inalcanzable


def parse_fit(text: str) -> tuple[float | None, str, int]:
    """Parsea "20 H7", "H7" o "h7" → (nominal|None, letra, grado). La CAJA de la
    letra decide agujero (mayúscula) vs eje (minúscula)."""
    m = _FIT_RE.match(str(text))
    if not m:
        raise KeyError(
            f"Ajuste ISO 286 inválido: '{text}' (formato: 'H7', 'g6' o '20 H7')"
        )
    nominal = float(m.group(1)) if m.group(1) else None
    return nominal, m.group(2), int(m.group(3))


def it_um(nominal_mm: float, grade: int) -> float:
    """Intervalo de tolerancia IT (µm) para el nominal y grado dados."""
    if grade not in IT_UM:
        raise KeyError(f"Grado IT{grade} no soportado (IT5–IT11)")
    return IT_UM[grade][_range_idx(nominal_mm)]


def _shaft_devs_um(nominal_mm: float, letter: str, grade: int) -> tuple[float, float]:
    """(ei, es) en µm de un EJE."""
    if letter not in _SHAFT_GRADES or grade not in _SHAFT_GRADES[letter]:
        raise KeyError(
            f"Eje '{letter}{grade}' no soportado (ejes: "
            + ", ".join(f"{k}{min(v)}–{k}{max(v)}" for k, v in sorted(_SHAFT_GRADES.items()))
            + ")"
        )
    it = it_um(nominal_mm, grade)
    if letter == "js":
        return (-it / 2.0, it / 2.0)
    idx = _range_idx(nominal_mm)
    fund = SHAFT_DEV_UM[letter][idx]
    if letter in ("g", "f", "h"):  # fundamental = es (superior)
        return (fund - it, fund)
    return (fund, fund + it)  # k/m/n/p: fundamental = ei (inferior)


def _hole_devs_um(nominal_mm: float, letter: str, grade: int) -> tuple[float, float]:
    """(EI, ES) en µm de un AGUJERO, derivado por las reglas de ISO 286-1."""
    if letter not in _HOLE_GRADES or grade not in _HOLE_GRADES[letter]:
        raise KeyError(
            f"Agujero '{letter}{grade}' no soportado (agujeros: "
            + ", ".join(f"{k}{min(v)}–{k}{max(v)}" for k, v in sorted(_HOLE_GRADES.items()))
            + ")"
        )
    it = it_um(nominal_mm, grade)
    idx = _range_idx(nominal_mm)
    if letter == "H":
        return (0.0, it)
    if letter == "JS":
        return (-it / 2.0, it / 2.0)
    if letter in ("G", "F"):  # EI = −es(eje homólogo) > 0
        ei = -SHAFT_DEV_UM[letter.lower()][idx]
        return (ei, ei + it)
    # K/M/N/P grados 6–7: ES = −ei(eje homólogo) + Δ, Δ = ITn − IT(n−1)
    delta = it - it_um(nominal_mm, grade - 1)
    es = -SHAFT_DEV_UM[letter.lower()][idx] + delta
    return (es - it, es)


def fit_limits(nominal_mm: float, fit: str) -> dict:
    """Límites de un ajuste ("H7" agujero / "h7" eje) sobre el nominal.

    Devuelve {fit, ei_um, es_um, lo_mm, hi_mm} (ei/es = desviación inferior/superior)."""
    _, letter, grade = parse_fit(fit)
    if letter[0].isupper():
        ei, es = _hole_devs_um(nominal_mm, letter, grade)
    else:
        ei, es = _shaft_devs_um(nominal_mm, letter, grade)
    return {
        "fit": f"{letter}{grade}",
        "ei_um": round(ei, 2),
        "es_um": round(es, 2),
        "lo_mm": round(nominal_mm + ei / 1000.0, 4),
        "hi_mm": round(nominal_mm + es / 1000.0, 4),
    }


def fit_check(nominal_mm: float, hole_fit: str, shaft_fit: str) -> dict:
    """Analiza el ajuste agujero/eje: juego = agujero − eje (negativo = apriete)."""
    hole = fit_limits(nominal_mm, hole_fit)
    shaft = fit_limits(nominal_mm, shaft_fit)
    juego_min = hole["ei_um"] - shaft["es_um"]
    juego_max = hole["es_um"] - shaft["ei_um"]
    if juego_min >= 0:
        tipo = "juego"
    elif juego_max <= 0:
        tipo = "apriete"
    else:
        tipo = "transicion"
    return {
        "nominal_mm": nominal_mm,
        "hole": hole,
        "shaft": shaft,
        "juego_min_um": round(juego_min, 2),
        "juego_max_um": round(juego_max, 2),
        "tipo": tipo,
    }


def bearing_bore_tol_um(bore_mm: float) -> float:
    """Tolerancia t del bore de rodamiento/inserto (ISO 492 Normal: Δdmp = 0/−t)."""
    for hi, t in zip(_BEARING_BORE_RANGES, BEARING_BORE_TOL_UM):
        if bore_mm <= hi:
            return float(t)
    raise KeyError(f"Bore Ø{bore_mm:g} mm fuera de la tabla ISO 492 (≤180 mm)")


def bearing_seat_check(nominal_mm: float, shaft_fit: str, mount: str) -> dict:
    """Verifica el asiento de un rodamiento/inserto sobre el eje.

    El bore va con ISO 492 clase Normal (0/−t); el criterio de aceptación sale de
    SEAT_RECOMMENDATIONS por tipo de montaje."""
    if mount not in SEAT_RECOMMENDATIONS:
        raise KeyError(
            f"Montaje '{mount}' desconocido ({', '.join(sorted(SEAT_RECOMMENDATIONS))})"
        )
    rec = SEAT_RECOMMENDATIONS[mount]
    shaft = fit_limits(nominal_mm, shaft_fit)
    t = bearing_bore_tol_um(nominal_mm)
    juego_min = -t - shaft["es_um"]  # bore_lo − eje_hi
    juego_max = 0.0 - shaft["ei_um"]  # bore_hi − eje_lo
    if juego_min >= 0:
        tipo = "juego"
    elif juego_max <= 0:
        tipo = "apriete"
    else:
        tipo = "transicion"
    return {
        "nominal_mm": nominal_mm,
        "shaft": shaft,
        "bore_tol_um": t,
        "juego_min_um": round(juego_min, 2),
        "juego_max_um": round(juego_max, 2),
        "tipo": tipo,
        "montaje": mount,
        "recomendados": sorted(rec["ok"]),
        "tipico": rec["tipico"],
        "nota": rec["nota"],
        "recomendado": shaft["fit"].lower() in rec["ok"],
    }


def _dev_txt(um: float) -> str:
    """Desviación µm → texto en mm ("+0.021", "0", "−0.025")."""
    if abs(um) < 1e-9:
        return "0"
    mm = um / 1000.0
    txt = f"{mm:+.4f}".rstrip("0").rstrip(".")
    return txt


def format_fit_label(nominal_mm: float, fit: str) -> str:
    """Etiqueta de plano: "Ø20 H7 (+0.021/0)"."""
    lim = fit_limits(nominal_mm, fit)
    return f"Ø{nominal_mm:g} {lim['fit']} ({_dev_txt(lim['es_um'])}/{_dev_txt(lim['ei_um'])})"
