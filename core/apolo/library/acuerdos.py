"""Radios de acuerdo de los perfiles abiertos y la ZONA PLANA de su alma/ala (plan
perfiles-con-acuerdo, D1).

El catálogo dibuja UPN/IPE/L prismáticos (el builder NO lee r1/r2: la geometría y las firmas
no cambian), pero el perfil real tiene un acuerdo r1 entre alma y ala (y en el UPN el ala
interior con pendiente del 8 %): en un UPN-100 la parte plana del alma empieza ~18 mm debajo
del canto. Funciones PURAS sobre las `specs` del catálogo:

- `inicio_zona_plana_alma` / `zona_plana_ala_angulo`: la geometría de norma;
- `validar_acuerdo`: lo que el loader exige a una variante que declara r1/r2/pendiente_ala.

Quien las usa sobre la escena: `lint_asiento.py` (D2).
"""

from __future__ import annotations

import math


# ---------------------------------------------------------------- geometría de norma
def _num(specs: dict, key: str) -> float | None:
    v = specs.get(key)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def inicio_zona_plana_alma(specs: dict) -> float | None:
    """Distancia (mm) desde el canto exterior del ala hasta donde empieza la parte PLANA de la
    cara interior del alma de un perfil U o I. None si las specs no la definen.

    s = tf + p·(b/2 − tw) + r1·tan((90° − atan p)/2)

    tf se mide a b/2 del dorso (DIN 1026-1), así que con pendiente p el ala engrosa
    p·(b/2 − tw) hasta la cara del alma; el acuerdo r1 une dos caras a 90° + atan p y es
    tangente al alma a r1·tan((90° − α)/2) del vértice (con p = 0, IPE: exactamente r1).
    h − 2·s reproduce la altura recta del alma `d` publicada (test de datos)."""
    tf, b, tw, r1 = (_num(specs, k) for k in ("tf", "b", "tw", "r1"))
    if None in (tf, b, tw, r1) or _num(specs, "h") is None:
        return None
    p = _num(specs, "pendiente_ala") or 0.0
    alfa = math.atan(p)
    return tf + p * (b / 2.0 - tw) + r1 * math.tan((math.pi / 2.0 - alfa) / 2.0)


def zona_plana_ala_angulo(specs: dict) -> tuple[float, float] | None:
    """Zona plana de la cara INTERIOR de un ala de ángulo, medida desde el TALÓN (dorso del
    ala opuesta): [t + r1, leg − r2]. None si las specs no la definen."""
    leg, t, r1 = (_num(specs, k) for k in ("leg", "t", "r1"))
    if None in (leg, t, r1):
        return None
    return t + r1, leg - (_num(specs, "r2") or 0.0)


def validar_acuerdo(specs: dict, ref: str) -> None:
    """Lo que el loader exige a una variante que declara r1/r2/pendiente_ala: números ≥ 0, una
    pendiente creíble y una zona plana que EXISTA. Lanza ValueError con la ref."""
    claves = ("r1", "r2", "pendiente_ala")
    if not any(k in specs for k in claves):
        return
    for k in claves:
        if k in specs and (_num(specs, k) is None or _num(specs, k) < 0):
            raise ValueError(f"Componente '{ref}': '{k}' debe ser un número ≥ 0 (mm), no {specs[k]!r}")
    if "r1" not in specs:
        raise ValueError(f"Componente '{ref}': r2/pendiente_ala sin r1 (radio de acuerdo)")
    if (_num(specs, "pendiente_ala") or 0.0) >= 0.2:
        raise ValueError(f"Componente '{ref}': pendiente_ala es una fracción (UPN = 0.08), no %")
    s = inicio_zona_plana_alma(specs)
    if s is not None and 2.0 * s >= float(specs["h"]):
        raise ValueError(f"Componente '{ref}': con r1={specs['r1']} el alma no tiene zona plana "
                         f"(2·{s:.1f} ≥ h={specs['h']})")
    zona = zona_plana_ala_angulo(specs)
    if zona is not None and zona[0] >= zona[1]:
        raise ValueError(f"Componente '{ref}': con r1/r2 el ala no tiene zona plana "
                         f"({zona[0]:g} ≥ {zona[1]:g})")
    if s is None and zona is None:
        raise ValueError(f"Componente '{ref}': r1 sólo vale en perfiles con h/b/tw/tf o leg/t")
