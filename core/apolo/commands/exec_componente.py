"""Executor de `insert_component` (salió de `registry.py`, congelado por el trinquete de tamaño,
cuando ganó `orientacion`: plan perfiles-con-acuerdo D3).

v2: los perfiles abiertos publican anclas por familia (D4: `cara_alma_interior`, `zona_plana`…,
`library/perfiles_abiertos.py`). La geometría no cambia, pero la Feature sí (sus anclas) y la
caché de geometría guarda Features: la versión invalida sólo los proyectos con componentes,
como el bump v3 del epoch cuando nacieron las anclas.

Criterio 2 (F6 de la puerta de publicación; campo oculto que pone `sellar` al comando NUEVO): la
tornillería de largo A MEDIDA (`largos_perno.largos_catalogo` no vacío, sin `specs.length`) se
construye con `length` (validado contra su serie de catálogo) y lo deja en `cut_length`, el
largo nominal que compra la BOM; un `length` en lo que no lo admite es error. Antes `length` se
ignoraba en silencio en todo lo no cortable y un perno M6 salía siempre de 50 (el modelador del
proyecto 6 no encontró cómo pedir M6x20). El criterio 1 (log viejo) sigue igual: sin `version`
ni epoch, como `join_bolted.criterio`.
"""

from __future__ import annotations

from .errors import CommandError
from .models_componente import InsertComponentParams
from .state import ExecContext


def _instanced(*args, **kwargs) -> None:
    """El de `registry.py`, importado al llamar: `registry` importa este módulo al cargarse."""
    from .registry import _instanced as instanciar

    instanciar(*args, **kwargs)


CRITERIO_VIGENTE = 2


def sellar(params: dict, _material_de) -> dict:
    """Sello de entrada: el criterio vigente (lo que el cliente ya trae se respeta)."""
    params.setdefault("criterio", CRITERIO_VIGENTE)
    return params


def al_editar(params: dict, previos: dict) -> dict:
    """Sello de edición: el criterio guardado no se pierde (la UI reenvía los params sin el campo
    oculto) y un comando viejo (criterio 1) al que el cliente le PIDE otro `length` pasa al
    vigente: el largo ya no se ignora en silencio (el modelador del proyecto 6 lo editó y no
    pasó nada). Sin cambio de `length`, sigue en su criterio: regenera igual."""
    if "criterio" not in params and "criterio" in previos:
        params["criterio"] = previos["criterio"]
    pide = params.get("length") is not None and params.get("length") != previos.get("length")
    if pide and int(params.get("criterio") or 1) < CRITERIO_VIGENTE:
        params["criterio"] = CRITERIO_VIGENTE
    return params


#: los sellos del CommandSpec (entrada y edición), en un solo nombre para `registry.py`
SELLOS = {"al_crear": sellar, "al_editar": al_editar}


def _a_medida(comp, length: float | None):
    """(forma, largo) de la tornillería de largo a medida con `length` (criterio 2), o None si
    va por `build_component`. CommandError si `length` no se puede aplicar."""
    from apolo.library.largos_perno import en_catalogo, largos_catalogo

    if length is None or comp.cuttable:
        return None
    fijo = (comp.specs or {}).get("length")
    largos = largos_catalogo(comp.ref)
    if fijo is not None or not largos:
        if fijo is not None and abs(float(fijo) - length) <= 0.5:
            return None
        raise CommandError(
            f"{comp.ref} no es de largo a medida: length sólo vale en cortables y en tornillería "
            f"de largo a medida (PERNO-HEX-*, PERNO-M*…)"
            + (f"; su largo es {float(fijo):g} mm" if fijo is not None else "; quita length"))
    if not en_catalogo(comp.ref, length):
        raise CommandError(
            f"{comp.ref}: {length:g} mm no es un largo que se compre; largos de catálogo: "
            + ", ".join(f"{s:g}" for s in largos))
    return comp.builder(length), float(length)


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
    hecho = _a_medida(comp, p.length) if p.criterio >= 2 else None
    try:
        base, cut = hecho if hecho is not None else build_component(p.component, p.length)
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
