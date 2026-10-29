"""Reglas de la faja: constantes, regex de nombres y auxiliares comunes (parseo de nombres,
formato de regla `_check`, bbox y volumen tolerantes). Sale de `rules.py` (plan
partir-nucleo-congelado-ii, F3), que lo re-exporta por identidad. Puro.
"""

from __future__ import annotations

import re


FRICTION_COEFF = 0.06  # rodadura + cojinetes
EFFICIENCY = 0.85
POWER_MARGIN = 1.3
RAIL_W = 40.0
DEFLECTION_RATIO = 240.0  # flecha admisible del bastidor = L / 240 (AISC, carga total)
SHAFT_SAFETY = 2.0        # factor de seguridad sobre el límite elástico del eje (σ_adm = σy/2)

_HP_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*hp", re.I)
_KW_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*kw", re.I)
_SECTION_RE = re.compile(r"(\d+)\s*[x×]\s*(\d+)\s*[x×]\s*(\d+)")  # 80x40x3
_DIAM_RE = re.compile(r"[øØ⌀]\s*(\d+(?:[.,]\d+)?)", re.I)
#: «cuadrado 60» en el nombre de un eje: la sección del vano (ruedas de agujero cuadrado)
_CUADRADO_RE = re.compile(r"\bcuadrado\s*(\d+(?:[.,]\d+)?)", re.I)
# ROL al inicio del nombre (convención rol-primero): distingue una PATA/LARGUERO de
# verdad de una pieza que solo MENCIONA una pata/larguero ("Ménsula … → larguero + pata").
# "zapata"/"perfil" no empiezan por el rol, así que quedan fuera.
_LEG_RE = re.compile(r"^\s*pata\b", re.I)
_LARG_RE = re.compile(r"^\s*larguero\b", re.I)
# el ROL "eje" (nombre —o su parte tras " · "— empieza por "eje"): distingue el EJE de un
# tambor/rodillo/motor que solo MENCIONAN un eje ("Tambor motriz (… eje vivo)", "Rodillo
# (eje Ø12)", "Motorreductor (eje hueco)").
_EJE_RE = re.compile(r"^\s*eje\b", re.I)
_BANDA_RE = re.compile(r"^(bandas?|cintas?|fajas?)\b", re.I)  # sobre `piece_role` (tras « · »)


def _f(x) -> float | None:
    try:
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _parse_power_kw(name: str) -> float | None:
    """Potencia del motor (kW) parseada del nombre: '1.5HP' → 1.12 kW, '1.1 kW' → 1.1."""
    m = _KW_RE.search(name or "")
    if m:
        return _f(m.group(1))
    m = _HP_RE.search(name or "")
    if m:
        hp = _f(m.group(1))
        return round(hp * 0.7457, 3) if hp else None
    return None


def _parse_wall(name: str) -> float | None:
    """Espesor de pared (mm) de una sección de tubo '80x40x3' → 3."""
    m = _SECTION_RE.search(name or "")
    return _f(m.group(3)) if m else None


def _parse_diam(name: str) -> float | None:
    """Diámetro (mm) de un 'Ø35'/'Ø 35' en el nombre."""
    m = _DIAM_RE.search(name or "")
    return _f(m.group(1)) if m else None


def _vol_safe(f) -> float:
    try:
        return float(f.shape.volume)
    except Exception:
        return 0.0


def _check(
    regla: str,
    estado: str,
    detalle: str,
    recomendacion: str | None = None,
    *,
    calc: dict | None = None,
) -> dict:
    """Una regla del reporte. `calc` (opcional, Frente A) enriquece la regla con el
    CÁLCULO detrás del veredicto — lo consume la memoria de cálculo:
    {titulo, entradas: {k: "valor unidad"}, formula, sustitucion, resultado,
    criterio, fs: float|None}. Sin `calc`, el formato queda byte-idéntico al histórico."""
    out = {"regla": regla, "estado": estado, "detalle": detalle}
    if recomendacion:
        out["recomendacion"] = recomendacion
    if calc:
        out["calc"] = calc
    return out


def _name(f) -> str:
    return (getattr(f, "name", "") or "").lower()


def _bbox_safe(f):
    try:
        return f.shape.bounding_box()
    except Exception:
        return None
