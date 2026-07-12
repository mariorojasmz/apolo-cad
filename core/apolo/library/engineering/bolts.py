"""Uniones apernadas: capacidad a cortante/tracción y utilización (ISO 898-1 +
EN 1993-1-8 simplificado).

La tabla de áreas resistentes y grados vive AQUÍ (código), no en el catálogo:
es función de la métrica del perno, no de un componente — el `size="M10"` de un
fastener no referencia una ref de catálogo. Fuente única.

Unidades: N, MPa, mm².
"""

from __future__ import annotations

# Área resistente a tracción As (mm²) por métrica — ISO 898-1, paso grueso.
TENSILE_AREA_MM2 = {
    "M6": 20.1,
    "M8": 36.6,
    "M10": 58.0,
    "M12": 84.3,
    "M14": 115.0,
    "M16": 157.0,
    "M18": 192.0,
    "M20": 245.0,
    "M24": 353.0,
}

# grado → (Rm resistencia última, Rp0.2 límite elástico) en MPa — ISO 898-1.
GRADES = {
    "4.6": (400.0, 240.0),
    "8.8": (800.0, 640.0),
    "10.9": (1000.0, 900.0),
    "12.9": (1200.0, 1080.0),
}

# Ø de la broca de PASO ISO 273 (serie MEDIA) por métrica del perno (mm). Un agujero de
# paso deja holgura radial para el vástago (M12→Ø13.5): la unión atornillada la usa en
# AMBAS piezas (join_bolted, V6.5b). Serie fina/gruesa por demanda.
CLEARANCE_HOLE_MM = {
    "M6": 6.6, "M8": 9.0, "M10": 11.0, "M12": 13.5, "M14": 15.5,
    "M16": 17.5, "M18": 20.0, "M20": 22.0, "M24": 26.0,
}

# Cabeza HEXAGONAL DIN 933 / ISO 4017 por métrica: (entrecaras s, altura de cabeza k) mm.
HEX_HEAD_MM = {
    "M6": (10.0, 4.0), "M8": (13.0, 5.3), "M10": (16.0, 6.4), "M12": (18.0, 7.5),
    "M14": (21.0, 8.8), "M16": (24.0, 10.0), "M18": (27.0, 11.5), "M20": (30.0, 12.5),
    "M24": (36.0, 15.0),
}

# Tuerca HEXAGONAL DIN 934 por métrica: (entrecaras s, altura m) mm. Pareja del DIN 933
# en la unión pasante (join_bolted, V6.5c); coincide con las fichas TUERCA-* del catálogo.
HEX_NUT_MM = {
    "M6": (10.0, 5.0), "M8": (13.0, 6.5), "M10": (17.0, 8.0), "M12": (18.0, 10.0),
    "M14": (21.0, 11.0), "M16": (24.0, 13.0), "M18": (27.0, 15.0), "M20": (30.0, 16.0),
    "M24": (36.0, 19.0),
}

# Longitudes de vástago COMERCIALES (mm) para redondear el largo del perno al alza.
STD_LENGTHS = [
    10, 12, 16, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 80, 90, 100,
    110, 120, 130, 140, 150, 160, 180, 200,
]


def _norm(size: str) -> str:
    return size.strip().upper()


def nominal_diameter_mm(size: str) -> float:
    """Ø nominal del perno (M12 → 12.0)."""
    return float(_norm(size).lstrip("M"))


def clearance_hole_mm(size: str) -> float:
    """Ø de la broca de paso ISO 273 serie media, o KeyError con mensaje claro."""
    key = _norm(size)
    if key not in CLEARANCE_HOLE_MM:
        raise KeyError(f"Métrica '{size}' sin broca de paso tabulada (soportadas: {', '.join(CLEARANCE_HOLE_MM)})")
    return CLEARANCE_HOLE_MM[key]


def hex_head_mm(size: str) -> tuple[float, float]:
    """(entrecaras, altura) de la cabeza hexagonal DIN 933, o KeyError con mensaje claro."""
    key = _norm(size)
    if key not in HEX_HEAD_MM:
        raise KeyError(f"Métrica '{size}' sin cabeza tabulada (soportadas: {', '.join(HEX_HEAD_MM)})")
    return HEX_HEAD_MM[key]


def hex_nut_mm(size: str) -> tuple[float, float]:
    """(entrecaras, altura m) de la tuerca hexagonal DIN 934, o KeyError con mensaje claro."""
    key = _norm(size)
    if key not in HEX_NUT_MM:
        raise KeyError(f"Métrica '{size}' sin tuerca tabulada (soportadas: {', '.join(HEX_NUT_MM)})")
    return HEX_NUT_MM[key]


def commercial_length(min_len: float) -> float:
    """Menor longitud comercial ≥ min_len (o la mayor tabulada si se pasa)."""
    return next((L for L in STD_LENGTHS if L >= min_len), float(STD_LENGTHS[-1]))


# γM2 de EN 1993-1-8 (uniones): factor parcial de resistencia.
GAMMA_M2 = 1.25

# αv de cortante (EN 1993-1-8, tabla 3.4): 0.6 para 4.6/5.6/8.8 (el plano de
# corte pasa por la rosca); 0.5 para 10.9/12.9 (menos dúctiles).
_ALPHA_V = {"4.6": 0.6, "8.8": 0.6, "10.9": 0.5, "12.9": 0.5}


def _lookup(size: str, grade: str) -> tuple[float, float, float]:
    """(As, Rm, αv) o KeyError con mensaje claro."""
    key = size.strip().upper()
    if key not in TENSILE_AREA_MM2:
        raise KeyError(f"Métrica desconocida '{size}' (soportadas: {', '.join(TENSILE_AREA_MM2)})")
    if grade not in GRADES:
        raise KeyError(f"Grado desconocido '{grade}' (soportados: {', '.join(GRADES)})")
    return TENSILE_AREA_MM2[key], GRADES[grade][0], _ALPHA_V.get(grade, 0.6)


def bolt_shear_capacity_n(size: str, grade: str = "8.8", gamma: float = GAMMA_M2) -> float:
    """Capacidad a CORTANTE de un perno (N), plano de corte por la rosca:
    Fv = αv·Rm·As / γ (EN 1993-1-8)."""
    a_s, rm, alpha = _lookup(size, grade)
    return alpha * rm * a_s / gamma


def bolt_tension_capacity_n(size: str, grade: str = "8.8", gamma: float = GAMMA_M2) -> float:
    """Capacidad a TRACCIÓN de un perno (N): Ft = 0.9·Rm·As / γ (EN 1993-1-8)."""
    a_s, rm, _ = _lookup(size, grade)
    return 0.9 * rm * a_s / gamma


def bolt_utilization(
    load_n: float,
    size: str,
    qty: int = 1,
    grade: str = "8.8",
    mode: str = "cortante",
) -> float:
    """Utilización de la unión (carga/capacidad; >1 = sobrecargada). La carga se
    reparte pareja entre los `qty` pernos. `mode`: "cortante" o "traccion"."""
    qty = max(int(qty), 1)
    per_bolt = max(float(load_n), 0.0) / qty
    cap = (
        bolt_tension_capacity_n(size, grade)
        if mode.startswith("tracc")
        else bolt_shear_capacity_n(size, grade)
    )
    return per_bolt / cap if cap > 0 else float("inf")
