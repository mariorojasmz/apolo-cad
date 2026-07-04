"""Roscas métricas ISO 261/262 (V5.7): paso, broca de machuelado y designación.

Tablas + funciones PURAS (patrón fits.py — nunca reciben Document). Las brocas son
los valores PUBLICADOS de taller (DIN 336), no ``d − paso`` calculado: para pasos
finos difieren (M10×1.25 → 8.8, no 8.75). El área resistente reusa la tabla ISO
898-1 de ``bolts.py`` cuando la métrica existe ahí (fuente única); el resto sale de
la fórmula As = (π/4)·(d − 0.9382·p)².

La rosca INTERIOR se rotula con la clase estándar 6H (fija en V5.7). Roscas
EXTERIORES (ejes) quedan fuera de alcance — se declaran por nombre como los fits.
"""

from __future__ import annotations

import math
import re

# métrica → (paso grueso mm, broca de machuelado mm PUBLICADA)
COARSE: dict[str, tuple[float, float]] = {
    "M3": (0.5, 2.5),
    "M4": (0.7, 3.3),
    "M5": (0.8, 4.2),
    "M6": (1.0, 5.0),
    "M8": (1.25, 6.8),
    "M10": (1.5, 8.5),
    "M12": (1.75, 10.2),
    "M14": (2.0, 12.0),
    "M16": (2.0, 14.0),
    "M18": (2.5, 15.5),
    "M20": (2.5, 17.5),
    "M22": (2.5, 19.5),
    "M24": (3.0, 21.0),
    "M27": (3.0, 24.0),
    "M30": (3.5, 26.5),
    "M33": (3.5, 29.5),
    "M36": (4.0, 32.0),
}

# pasos FINOS comunes: (métrica, paso) → broca publicada
FINE: dict[tuple[str, float], float] = {
    ("M8", 1.0): 7.0,
    ("M10", 1.0): 9.0,
    ("M10", 1.25): 8.8,
    ("M12", 1.25): 10.8,
    ("M12", 1.5): 10.5,
    ("M16", 1.5): 14.5,
    ("M20", 1.5): 18.5,
    ("M20", 2.0): 18.0,
    ("M24", 2.0): 22.0,
}

_RX = re.compile(r"^\s*[mM]\s*(\d+(?:\.\d+)?)\s*(?:[x×X]\s*(\d+(?:\.\d+)?))?\s*$")


def _supported() -> str:
    finos = ", ".join(f"{m}x{p:g}" for (m, p) in sorted(FINE))
    return f"gruesas: {', '.join(COARSE)}; finas: {finos}"


def parse_thread(text: str) -> tuple[str, float, float | None]:
    """Parsea "M8" / "m8" / "M8x1.25" / "M8×1.25" → (métrica, nominal_mm, paso|None).

    Un paso explícito IGUAL al grueso se normaliza a None (la designación canónica
    ISO omite el paso grueso). Desconocida → KeyError listando lo soportado."""
    m = _RX.match(str(text or ""))
    if not m:
        raise KeyError(f"Rosca '{text}' inválida: usa 'M8' o 'M10x1.25' ({_supported()})")
    metric = f"M{m.group(1).rstrip('0').rstrip('.') if '.' in m.group(1) else m.group(1)}"
    if metric not in COARSE:
        raise KeyError(f"Métrica '{metric}' no soportada ({_supported()})")
    nominal = float(m.group(1))
    pitch = float(m.group(2)) if m.group(2) else None
    coarse_pitch, _ = COARSE[metric]
    if pitch is not None and abs(pitch - coarse_pitch) < 1e-9:
        pitch = None  # el paso grueso no se designa
    if pitch is not None and (metric, pitch) not in FINE:
        raise KeyError(
            f"Paso fino {metric}x{pitch:g} no soportado ({_supported()})"
        )
    return metric, nominal, pitch


def thread_designation(size: str) -> str:
    """Designación canónica para agrupar/mostrar: "M8" (grueso) | "M10x1.25" (fino)."""
    metric, _, pitch = parse_thread(size)
    return metric if pitch is None else f"{metric}x{pitch:g}"


def thread_spec(size: str) -> dict:
    """Ficha completa de la rosca: {designacion, nominal_mm, paso_mm, fino, broca_mm,
    area_mm2, norma}."""
    metric, nominal, pitch = parse_thread(size)
    coarse_pitch, coarse_drill = COARSE[metric]
    if pitch is None:
        paso, broca, fino, norma = coarse_pitch, coarse_drill, False, "ISO 262"
    else:
        paso, broca, fino, norma = pitch, FINE[(metric, pitch)], True, "ISO 261 fino"

    area = None
    if not fino:
        try:  # fuente única: tabla ISO 898-1 de bolts (métricas gruesas M6-M24)
            from .bolts import TENSILE_AREA_MM2

            area = TENSILE_AREA_MM2.get(metric)
        except ImportError:  # pragma: no cover
            area = None
    if area is None:
        area = round(math.pi / 4.0 * (nominal - 0.9382 * paso) ** 2, 1)

    return {
        "designacion": metric if pitch is None else f"{metric}x{pitch:g}",
        "nominal_mm": nominal,
        "paso_mm": paso,
        "fino": fino,
        "broca_mm": broca,
        "area_mm2": area,
        "norma": norma,
    }


def format_thread_label(size: str, n: int = 1) -> str:
    """Etiqueta de plano/taller: "M8 - 6H (broca Ø6.8)" · "4×M8 - 6H (broca Ø6.8)" ·
    "M10×1.25 - 6H (broca Ø8.8)" (el fino se muestra con ×)."""
    spec = thread_spec(size)
    des = spec["designacion"].replace("x", "×")
    base = f"{des} - 6H (broca Ø{spec['broca_mm']:g})"
    return f"{n}×{base}" if n > 1 else base
