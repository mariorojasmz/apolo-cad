"""Refinamiento LOCAL de la malla en los radios chicos (chapa plegada, redondeos).

La chapa con pestañas ADYACENTES deja en cada esquina dos radios de plegado (r ≈ 3 mm) que se
cortan en INGLETE. OCCT dice que el sólido es válido, pero con una malla 10-100× mayor que el
radio gmsh discretiza cada cuarto de cilindro con una o dos cuerdas y las facetas de los dos
cilindros se cruzan junto al inglete («Invalid boundary mesh (overlapping facets)»). El remedio
no toca la geometría: un campo ``Distance`` + ``Threshold`` que achica la malla al tamaño del
radio sólo cerca de unas curvas, en dos etapas (plan ``docs/plans/fea-chapa-empernada.md``, D2):

1. antes de mallar, las curvas del inglete (compartidas por ≥ 2 radios < size/4);
2. si la malla falla igual, las curvas de TODOS los radios < size/2 (el que reintenta es
   ``mesher``: tras un ``generate`` fallido gmsh no re-malla el mismo modelo). La red de la
   etapa 2 es más ancha porque entre size/4 y size/2 la esquina también falla (el travesaño
   del 72 a 8 y 10 mm, r = 3) y una malla que hoy sale bien no debe cambiar.

Sin radios < size/4 no se crea ningún campo antes de mallar: lo que hoy malla sale idéntico.
Sin imports pesados: gmsh llega como argumento, con el modelo vivo y sincronizado.
"""

from __future__ import annotations

import math
from collections import Counter

FRACCION = 0.25            # etapa 1: radio < size/4, el cuarto de cilindro tiene 1-2 cuerdas
FRACCION_REINTENTO = 0.5   # etapa 2: la red más ancha, sólo si la malla ya falló
SIZE_MIN_MM = 1.0          # piso del tamaño refinado (un radio de 0.3 mm no pide tets de 0.3)
_TOL_VUELTA = 1e-3         # una dirección paramétrica que barre 2π ± esto da la vuelta completa


def _radio_abierto(gmsh, tag: int) -> float | None:
    """Radio de curvatura (1/κ máx) en el centro del dominio paramétrico de una superficie
    ABIERTA; None si es plana, si da la vuelta completa (taladro, manto de un eje) o si gmsh
    no la deja evaluar. Por curvatura y no por tipo: un redondeo de OCCT puede ser cilindro,
    toro o B-spline."""
    try:
        if gmsh.model.getType(2, tag) == "Plane":
            return None
        lo, hi = gmsh.model.getParametrizationBounds(2, tag)
        if any(abs((hi[i] - lo[i]) - 2.0 * math.pi) < _TOL_VUELTA for i in range(2)):
            return None
        uv = [(lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0]
        k_max, k_min, _, _ = gmsh.model.getPrincipalCurvatures(tag, uv)
        k = max(abs(float(k_max[0])), abs(float(k_min[0])))
    except Exception:  # noqa: BLE001 — best-effort: lo que no se evalúa no se refina
        return None
    return 1.0 / k if k > 1e-9 else None


def radios_chicos(gmsh, r_max: float) -> dict[int, float]:
    """Superficies abiertas y curvas de radio < `r_max` → su radio (mm)."""
    out: dict[int, float] = {}
    for _, tag in gmsh.model.getEntities(2):
        r = _radio_abierto(gmsh, int(tag))
        if r is not None and r < r_max:
            out[int(tag)] = r
    return out


def curvas_de(gmsh, superficies) -> set[int]:
    """Curvas que bordean un conjunto de superficies."""
    curvas: set[int] = set()
    for s in superficies:
        _, abajo = gmsh.model.getAdjacencies(2, s)
        curvas |= {int(c) for c in abajo}
    return curvas


def curvas_inglete(gmsh, radios: dict[int, float]) -> set[int]:
    """Curvas compartidas por ≥ 2 radios chicos: el inglete de la esquina de la chapa."""
    cuenta: Counter[int] = Counter()
    for s in radios:
        cuenta.update(curvas_de(gmsh, [s]))
    return {c for c, n in cuenta.items() if n >= 2}


def aplicar(gmsh, curvas: set[int], *, r_min: float, size_mm: float) -> float:
    """Campo ``Distance`` + ``Threshold`` sobre `curvas` como background mesh: tamaño
    SizeMin = max(r_min, 1 mm) hasta SizeMin de distancia, `size_mm` desde 2·SizeMin. Baja
    ``Mesh.MeshSizeMin`` para que el campo pueda achicar. Devuelve SizeMin."""
    smin = max(float(r_min), SIZE_MIN_MM)
    campo = gmsh.model.mesh.field
    dist = campo.add("Distance")
    campo.setNumbers(dist, "CurvesList", sorted(curvas))
    campo.setNumber(dist, "Sampling", 20)
    umbral = campo.add("Threshold")
    campo.setNumber(umbral, "InField", dist)
    campo.setNumber(umbral, "SizeMin", smin)
    campo.setNumber(umbral, "SizeMax", float(size_mm))
    campo.setNumber(umbral, "DistMin", smin)
    campo.setNumber(umbral, "DistMax", 2.0 * smin)
    campo.setAsBackgroundMesh(umbral)
    gmsh.option.setNumber("Mesh.MeshSizeMin", min(float(size_mm) / 3.0, smin))
    return smin


def refinar(gmsh, size_mm: float, etapa: int) -> tuple[dict, bool]:
    """Detecta los radios chicos del modelo vivo y aplica el campo de la `etapa` pedida
    (1 = ingletes de los radios < size/4, 2 = todas las curvas de los radios < size/2).
    Devuelve (``{etapa, radios, r_min_mm}``, reintentable): etapa 0 si no se creó ningún
    campo (sin radios, o etapa 1 sin ingletes); `radios` cuenta los de la red de esa etapa;
    reintentable = hay radios para la etapa 2 (si la malla falla, vale reconstruir)."""
    red = radios_chicos(gmsh, size_mm * FRACCION_REINTENTO)
    radios = red if etapa == 2 else {s: r for s, r in red.items() if r < size_mm * FRACCION}
    r_min = min(radios.values()) if radios else None
    curvas = curvas_de(gmsh, radios) if etapa == 2 else curvas_inglete(gmsh, radios)
    hecha = 0
    if curvas:
        aplicar(gmsh, curvas, r_min=r_min, size_mm=size_mm)
        hecha = etapa
    return ({"etapa": hecha, "radios": len(radios),
             "r_min_mm": round(r_min, 2) if r_min is not None else None}, bool(red))


def hipotesis(refinamiento: dict | None) -> str | None:
    """La línea de hipótesis del resumen cuando la malla se refinó (etapa ≥ 1)."""
    if not refinamiento or refinamiento.get("etapa", 0) < 1:
        return None
    n, r, k = refinamiento["radios"], refinamiento["r_min_mm"], refinamiento["etapa"]
    donde = "en las esquinas (ingletes) de" if k == 1 else "en"
    return (f"malla refinada localmente {donde} {n} radio(s) de plegado/redondeo "
            f"(r mín ≈ {round(r, 1):g} mm, etapa {k}): sin cambiar la geometría")
