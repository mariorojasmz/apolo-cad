"""Auto-agrupación en sub-ensamblajes: propone GRUPOS desde la heurística de
subsistemas (V5.2, Fase 4).

Es la MISMA heurística del árbol de la UI (super-comando → categoría de catálogo →
palabra clave del nombre) portada a backend como fuente única; propone-no-impone
(el endpoint tiene dry_run). Los comandos YA agrupados se excluyen; lo que ninguna
señal reconoce se deja SIN agrupar (mejor sin grupo que un grupo basura).
"""

from __future__ import annotations

import re

# super-comando → subsistema (anula los demás criterios)
CMD2SUB = {
    "create_take_up": "Rodillos y tambores", "create_drive_roller": "Rodillos y tambores",
    "create_weldment": "Estructura", "create_frame": "Estructura",
}

# categoría de catálogo → subsistema
CAT2SUB = {
    "perfiles": "Estructura", "tubos_circulares": "Estructura",
    "perfiles_abiertos": "Estructura", "tubos_estructurales": "Estructura",
    "patas": "Estructura", "pies_niveladores": "Estructura", "topes": "Estructura",
    "guias_lineales": "Estructura",
    "motorreductores": "Transmision", "motorreductores_sinfin": "Transmision",
    "transmision": "Transmision", "tensores_trotadora": "Transmision",
    "variadores": "Transmision",
    "rodillos": "Rodillos y tambores", "tambores": "Rodillos y tambores",
    "rodamientos": "Rodamientos", "chumaceras": "Rodamientos",
    "tornilleria": "Tornilleria", "tornilleria_madera": "Tornilleria",
    "pernos": "Tornilleria", "tuercas": "Tornilleria",
    "guardas": "Guardas",
    "sensores": "Sensores y control", "tableros": "Sensores y control",
    "mandos": "Sensores y control",
    "bisagras": "Carpinteria", "tiradores": "Carpinteria", "correderas": "Carpinteria",
    "cerraduras": "Carpinteria", "imanes_topes": "Carpinteria",
    "rieles_corredera": "Carpinteria", "correderas_colgantes": "Carpinteria",
}

# palabra clave del NOMBRE → subsistema (el orden importa: lo específico primero)
NAME2SUB: list[tuple[re.Pattern, str]] = [
    (re.compile(r"rodamiento|chumacera|balero"), "Rodamientos"),
    (re.compile(r"perno|tornillo|tuerca|seeger|arandela|clavija|esp[aá]rrago|allen|tirafondo|\bm\d|v[aá]stago|shank"), "Tornilleria"),
    (re.compile(r"motor|reductor|acople|pi[ñn][oó]n|cadena|correa|transmisi|variador|borne|cuna"), "Transmision"),
    (re.compile(r"rodillo|tambor|polea|\beje\b"), "Rodillos y tambores"),
    (re.compile(r"banda|cama|mesa|faja|desliz|repisa"), "Banda y mesa"),
    (re.compile(r"guarda|cubierta|protec|tapa|carcasa"), "Guardas"),
    (re.compile(r"sensor|fotoc[eé]l|tablero|bot[oó]n|paro|estop|hongo"), "Sensores y control"),
    (re.compile(r"bisagra|tirador|pomo|cerradura|vidrio|cristal"), "Carpinteria"),
    (re.compile(r"pata|larguero|travesa|viga|perfil|bastidor|marco|poste|columna|\bbase\b|placa|m[eé]nsula|soporte|escuadra|[aá]ngulo|canal|tubo|nivelad|\bpie"), "Estructura"),
]

# subsistema → rol de grupo (vocabulario de assembly/groups.py)
SUB2ROLE = {
    "Estructura": "estructura", "Transmision": "transmision",
    "Rodillos y tambores": "rodillos", "Rodamientos": "rodillos",
    "Banda y mesa": "banda", "Guardas": "guardas", "Tornilleria": "tornilleria",
    "Sensores y control": "electrico", "Carpinteria": "otro",
}


def _subsystem(feat, cmd_type: str | None, catalog: dict) -> str | None:
    if cmd_type and cmd_type in CMD2SUB:
        return CMD2SUB[cmd_type]
    comp = catalog.get(getattr(feat, "component", None) or "")
    if comp is not None and comp.category in CAT2SUB:
        return CAT2SUB[comp.category]
    name = (getattr(feat, "name", "") or "").lower()
    for pat, sub in NAME2SUB:
        if pat.search(name):
            return sub
    return None  # sin señal → mejor sin grupo que un grupo basura


def propose_groups(scene: dict, commands: list[dict], catalog: dict,
                   groups: dict | None = None) -> list[dict]:
    """Propone grupos por subsistema para los comandos AÚN sin grupo. Idempotente:
    los subsistemas cuyo nombre ya existe como grupo se OMITEN (re-correr no duplica
    ni falla). Devuelve [{name, role, members: [command_ids]}]."""
    existing = set((groups or {}).keys())
    cmd_types = {c["id"]: c.get("type") for c in commands}
    members_by_sub: dict[str, list[str]] = {}
    seen_cmds: set[str] = set()
    for feat in scene.values():
        cmd = feat.command_id
        if cmd in seen_cmds or getattr(feat, "group", None):
            continue
        seen_cmds.add(cmd)
        sub = _subsystem(feat, cmd_types.get(cmd), catalog)
        if sub is None:
            continue
        members_by_sub.setdefault(sub, []).append(cmd)
    return [
        {"name": sub, "role": SUB2ROLE.get(sub, "otro"), "members": cmds}
        for sub, cmds in members_by_sub.items()
        if sub not in existing
    ]
