"""FEA estático lineal de UNA pieza (V5.6): gmsh (malla tetraédrica desde STEP)
+ scikit-fem (elasticidad lineal, elementos P2).

Análisis, no modelado: nunca muta el documento. Unidades consistentes mm + N + MPa
(E en MPa con longitudes en mm → esfuerzos en MPa directo; peso propio en N/mm³).
Dependencias opcionales (extra ``fea``): gmsh, scikit-fem, meshio — todas con wheel
de Windows (sfepy/CalculiX se descartaron por NO tener wheels, spike 2026-07-03).
"""

from __future__ import annotations


class FeaError(Exception):
    pass


def _require_fea():
    """Falla con mensaje accionable si faltan las dependencias del extra `fea`."""
    try:
        import gmsh  # noqa: F401
        import skfem  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise FeaError(
            "FEA no disponible: ejecuta `pip install gmsh scikit-fem meshio` "
            "(extra opcional [fea]) y reinicia la API"
        ) from exc
