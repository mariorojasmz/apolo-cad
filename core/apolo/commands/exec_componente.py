"""Executor de `insert_component` (salió de `registry.py`, congelado por el trinquete de tamaño,
cuando ganó `orientacion`: plan perfiles-con-acuerdo D3).

v2: los perfiles abiertos publican anclas por familia (D4: `cara_alma_interior`, `zona_plana`…,
`library/perfiles_abiertos.py`). La geometría no cambia, pero la Feature sí (sus anclas) y la
caché de geometría guarda Features: la versión invalida sólo los proyectos con componentes,
como el bump v3 del epoch cuando nacieron las anclas.
"""

from __future__ import annotations

from .errors import CommandError
from .models_componente import InsertComponentParams
from .state import ExecContext


def _instanced(*args, **kwargs) -> None:
    """El de `registry.py`, importado al llamar: `registry` importa este módulo al cargarse."""
    from .registry import _instanced as instanciar

    instanciar(*args, **kwargs)


def _exec_insert_component(ctx: ExecContext, cmd_id: str, p: InsertComponentParams) -> None:
    from apolo.library.catalog import CATALOG, build_component, component_anchors
    from apolo.library.perfiles_abiertos import rotacion_por_orientacion

    comp = CATALOG[p.component]
    rotation = p.rotation.tuple()
    if p.orientacion is not None:  # D3: ejes del mundo → rotación (None = la de siempre)
        try:
            rotation = rotacion_por_orientacion(comp.familia, p.orientacion.model_dump())
        except ValueError as exc:
            raise CommandError(f"{p.component}: {exc}") from exc
    try:
        base, cut = build_component(p.component, p.length)
    except ValueError as exc:
        raise CommandError(str(exc)) from exc
    key = f"comp|{p.component}|{cut if cut is not None else 'std'}"
    _instanced(
        ctx.scene, cmd_id, p.name or comp.name, base, key,
        p.position.tuple(), rotation, component=p.component, cut_length=cut,
    )
    # anclas de conexión con nombre (V6.3b): frame LOCAL del builder → mundo por la pose
    local = component_anchors(comp)
    feat = ctx.scene[cmd_id]
    if local and feat.matrix is not None:
        from apolo.kernel.matrix import transform_anchors
        feat.anchors = transform_anchors(feat.matrix, local)
