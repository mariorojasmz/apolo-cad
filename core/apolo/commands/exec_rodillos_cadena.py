"""Executor de `create_roller_conveyor` (plan `plantilla-rodillos-cadena`, D1): el super-comando
que arma un transportador de rodillos motorizado por cadena con los executors del registro.

Es COMPUESTO (`composite=True`, como `insert_project`): corre `insert_component`,
`create_chain`, `drill_hole`, `fasten`… con ids `{cmd_id}_{sufijo}`, así que su firma de caché
lleva las versiones ≠ 1 de todo el registro. La huella de D11 cubre SÓLO esta función: si
cambian las cotas (`library/rodillos_cadena*.py`) o la receta (`receta_rodillos_*.py`) con
los mismos params, sube la `version` de su `CommandSpec` (regla D10, `commands/CLAUDE.md`).
"""

from __future__ import annotations

from pydantic import ValidationError

from .errors import CommandError
from .models_rodillos_cadena import CreateRollerConveyorParams
from .spec import CommandSpec, run_executor
from .state import ExecContext


def _grupos(ctx: ExecContext, cmd_id: str, raiz: str, grupos: dict) -> None:
    """Grupo raíz `raiz` (sin miembros directos: todo vive en sus subgrupos, como la raíz de
    `insert_project`) y un subgrupo `raiz/Grupo` por subsistema."""
    from apolo.assembly.groups import GroupError, register_group

    from .receta_rodillos_cadena import GRUPOS

    ctx.groups[raiz] = {"name": raiz, "parent": None, "role": None, "members": [],
                        "command_id": cmd_id}
    try:
        for nombre, rol in GRUPOS:
            if nombre in grupos:
                register_group(ctx.groups, cmd_id, {"name": f"{raiz}/{nombre}", "parent": raiz,
                                                    "role": rol, "members": grupos[nombre]})
    except GroupError as exc:
        raise CommandError(f"Transportador de rodillos: {exc}") from exc


def disposicion_de(p: CreateRollerConveyorParams):
    """La `Disposicion` (cotas puras) de unos params ya validados."""
    from apolo.library.rodillos_cadena import disposicion

    return disposicion(p.largo, p.ancho_util, p.paso, p.rodillo, p.altura, p.carga_kg,
                       p.motriz == "cadena", p.motor, p.velocidad_m_s, p.anclaje, p.taller, p.eje,
                       p.pie)


def sellar(params: dict, material_de) -> dict:
    """Sello de entrada (`CommandSpec.al_crear`, como `cierres` de `create_belt_conveyor`): todo
    transportador NUEVO nace con `taller=True` (F6: eje trabado, 6201 de compra, contratuerca y
    anclajes accesibles) y, con él, `eje="hexagonal"` (F7: el eje se calza en ranuras del ala y el
    rodillo sale levantándolo) y `pie="base"` (F8: con `anclaje`, pie de base de anclaje
    atornillado al concreto, sin placa de piso ni soldadura). Un log v3 no trae los campos → False
    / «roscado» / «disco» → la geometría de siempre; uno F6 trae `taller` sin `eje` → el eje M12
    trabado; uno F7 trae `eje` sin `pie` → el disco soldado a la placa de piso. El replay y los
    edits no sellan y lo explícito se respeta (`taller=False` deja el eje roscado y el disco:
    hexagonal y base piden `taller`)."""
    params.setdefault("taller", True)
    if params.get("taller") is True:
        params.setdefault("eje", "hexagonal")
        params.setdefault("pie", "base")
    return params


def _exec_create_roller_conveyor(ctx: ExecContext, cmd_id: str,
                                 p: CreateRollerConveyorParams) -> None:
    from .receta_rodillos_cadena import receta
    from .registry import REGISTRY

    if p.name in ctx.groups:  # antes de emitir: el nombre ES el grupo raíz
        raise CommandError(f"Ya existe un grupo llamado '{p.name}': el transportador necesita "
                           "un nombre único (name)")
    try:
        d = disposicion_de(p)
    except (ValueError, KeyError) as exc:
        raise CommandError(f"Transportador de rodillos: {exc}") from exc
    pasos, grupos = receta(d, cmd_id, p.name, p.position.tuple())
    for tipo, sufijo, params in pasos:
        spec = REGISTRY[tipo]
        try:
            modelo = spec.model.model_validate(params, extra="forbid")
            run_executor(spec, ctx, f"{cmd_id}_{sufijo}", modelo)
        except (ValidationError, CommandError) as exc:
            raise CommandError(f"Transportador de rodillos ({tipo} {sufijo}): {exc}") from exc
    _grupos(ctx, cmd_id, p.name, grupos)


def subcomandos(cmd: dict, variables: dict) -> list[dict]:
    """Las entradas de log (`{id, type, params}`) que corre un `create_roller_conveyor`, para
    las reglas que recorren el log buscando un tipo (la «transmisión por cadena» mide así las
    cadenas de la plantilla). [] si sus params no resuelven: el regenerate ya lo rechazó."""
    from .expressions import ExpressionError, resolve_params
    from .receta_rodillos_cadena import receta

    try:
        p = CreateRollerConveyorParams.model_validate(
            resolve_params(cmd.get("params") or {}, variables), extra="ignore")
        d = disposicion_de(p)
    except (ExpressionError, ValidationError, ValueError, KeyError):
        return []
    pasos, _ = receta(d, cmd["id"], p.name, p.position.tuple())
    return [{"id": f"{cmd['id']}_{suf}", "type": tipo, "params": params}
            for tipo, suf, params in pasos]


def comandos_efectivos(commands, variables: dict):
    """El log con cada `create_roller_conveyor` reemplazado por los comandos que corre."""
    for cmd in commands:
        if cmd.get("type") == "create_roller_conveyor":
            yield from subcomandos(cmd, variables)
        else:
            yield cmd


SPECS_RODILLOS_CADENA = [
    CommandSpec(
        "create_roller_conveyor", "Transportador de rodillos por cadena", "biblioteca",
        CreateRollerConveyorParams, _exec_create_roller_conveyor, composite=True,
        # v2 (F4): guardas cerradas, bandeja, tensado sobre la línea de centros y travesaños a
        # una altura; rodillos, cadenas y motor de un log v1 quedan donde estaban.
        # v3 (F5): pie nivelador en cada pata (las patas se acortan) y placa de piso aparte.
        # F6 NO sube la versión: lo nuevo entra por el campo oculto `taller` que pone el sello
        # (los params cambian → la firma también); un log v3 regenera idéntico. F7 tampoco: el
        # campo oculto `eje` («hexagonal» por el sello); un log F6 regenera idéntico. F8 tampoco:
        # el oculto `pie` («base» por el sello); un log F7 regenera idéntico.
        # v4 (uniones-que-tocan F1): la pared interior de la guarda fija se suelda a sus dos
        # extremos, no a la exterior (77 mm de luz: soldadura fantasma). Misma geometría, pero
        # el checkpoint guarda los fasteners: todo log la corrige y la caché vieja vence.
        version=4, al_crear=sellar,
    ),
]
