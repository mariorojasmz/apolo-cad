"""Sub-ensamblajes de primera clase: GRUPOS con nombre, anidables, declarados por
COMMAND_IDs (V5.2).

Por qué por comandos y no por piezas: los feature_ids derivan del command_id y pueden
DESAPARECER al editar el count de un patrón — la unidad estable del log es el comando.
Un grupo declara comandos; TODAS las features presentes y futuras de esos comandos
pertenecen (editar un count o añadir instancias no rompe la membresía).

Espejo estructural de ``assembly/connectivity.py``: error propio + ``register_group``
(validación al registrar durante el replay) + funciones puras de consulta. Integridad
TOLERANTE (≠ fasten): un member cuyo comando ya no existe NO falla el regenerate — se
expone en ``missing_members`` para que el agente/UI lo curen. Lo que SÍ es error al
registrar: nombre duplicado, member ya en otro grupo, `parent` no declarado ANTES en el
log (así los ciclos son imposibles por construcción).
"""

from __future__ import annotations

# vocabulario SUGERIDO de roles (abierto: se admite cualquier texto corto). Las reglas
# de ingeniería lo consumirán en V5.2b para dejar de inferir subsistemas por nombre.
GROUP_ROLES = (
    "estructura", "transmision", "rodillos", "banda", "guardas",
    "tornilleria", "electrico", "otro",
)


class GroupError(Exception):
    pass


def register_group(groups: dict, cmd_id: str, spec: dict) -> None:
    """Valida y registra un grupo durante el replay del log."""
    name = str(spec["name"]).strip()
    if not name:
        raise GroupError("El grupo necesita un nombre")
    if name in groups:
        raise GroupError(f"Ya existe un grupo llamado '{name}'")
    members = [str(m) for m in (spec.get("members") or []) if str(m).strip()]
    if not members:
        raise GroupError(f"El grupo '{name}' necesita al menos un comando miembro")
    if len(set(members)) != len(members):
        raise GroupError(f"El grupo '{name}' repite comandos en members")
    for other in groups.values():
        dup = set(members) & set(other["members"])
        if dup:
            raise GroupError(
                f"El comando '{sorted(dup)[0]}' ya pertenece al grupo '{other['name']}' "
                "(un comando vive en UN solo grupo; anida con parent si quieres jerarquía)"
            )
    parent = spec.get("parent") or None
    if parent is not None and parent not in groups:
        raise GroupError(
            f"El grupo padre '{parent}' no existe (declara el padre ANTES que el hijo)"
        )
    groups[name] = {
        "name": name,
        "parent": parent,
        "role": (spec.get("role") or None),
        "members": members,
        "command_id": cmd_id,
    }


def children_of(groups: dict, name: str) -> list[str]:
    return [g["name"] for g in groups.values() if g.get("parent") == name]


def group_command_ids(groups: dict, name: str, recursive: bool = True) -> set[str]:
    """Command_ids del grupo (y de sus descendientes si recursive)."""
    g = groups.get(name)
    if g is None:
        return set()
    cmds = set(g["members"])
    if recursive:
        for child in children_of(groups, name):
            cmds |= group_command_ids(groups, child, recursive=True)
    return cmds


def group_features(scene: dict, groups: dict, name: str, recursive: bool = True) -> list[str]:
    """Feature_ids que pertenecen al grupo (incluye descendientes si recursive)."""
    cmds = group_command_ids(groups, name, recursive)
    return [fid for fid, f in scene.items() if f.command_id in cmds]


def assign_feature_groups(scene: dict, groups: dict) -> None:
    """Setea el campo DERIVADO ``feat.group`` (membresía DIRECTA, sin heredar la del
    padre: en el árbol un hijo se muestra dentro de su grupo, que a su vez cuelga del
    padre). Se llama al final de cada regenerate."""
    by_cmd: dict[str, str] = {}
    for g in groups.values():
        for cmd in g["members"]:
            by_cmd[cmd] = g["name"]
    for feat in scene.values():
        feat.group = by_cmd.get(feat.command_id)


def missing_members(scene: dict, groups: dict) -> dict[str, list[str]]:
    """Members declarados cuyo comando ya no produce NINGUNA feature en la escena
    (comando borrado/editado). Integridad tolerante: se reporta, no se falla."""
    present = {f.command_id for f in scene.values()}
    out: dict[str, list[str]] = {}
    for g in groups.values():
        gone = [m for m in g["members"] if m not in present]
        if gone:
            out[g["name"]] = gone
    return out
