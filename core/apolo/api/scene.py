"""Payload de escena de la API: lo que ve el viewport y lo que lee el agente sin mallas.

Movido tal cual desde `main.py` (F6a del plan `docs/plans/partir-api-main.md`): el payload del
documento (variables, grupos, salud del autosave), las cachés por IDENTIDAD del shape
(`_cached_render`, `_definition_mesh`), la revisión de geometría por feature (`_GEOM_REVS`) y el
`SCENE_EPOCH` de los deltas, los briefs sin malla (`_feature_brief`, `scene_summary_dict`,
`_open_briefing`) y el color por pieza (`_feature_colors`, el mismo del viewport). Es transporte,
no dominio (D9): lee `S` y no toma locks — el llamador sostiene `STATE_LOCK`.

Zonas de acabado (plan seta-de-emergencia, D2/D3): una pieza de un componente con zonas que
conserva la forma del builder lleva `zonas: [{acabado, albedo, desde, hasta}]` (índices de
triángulo de su malla o de la de su definición), también en la entrada `same`; una pieza sin
zonas sale byte a byte como antes.

`main` re-exporta por IDENTIDAD lo que usan los tests (`scene_payload`, `_GEOM_REVS`,
`_DEF_MESH_CACHE`, `_definition_mesh`, `_cached_render`, `_open_briefing`): las cachés se
mutan en sitio, nunca se reasignan.
"""

from __future__ import annotations

from apolo.brief import brief_pieza
from apolo.kernel import bbox_payload, mesh_payload
from apolo.library.requisitos import estado_ficha

from .session import S


PALETTE = ["#5b8def", "#46b58a", "#c77d4f", "#8e6fd8", "#d8a03a", "#5fa8c9", "#c75f7c"]


def variables_payload() -> list[dict]:
    defining: dict[str, str] = {}
    expressions: dict[str, str] = {}
    for cmd in S.doc.commands:
        if cmd["type"] == "set_variable":
            defining[cmd["params"]["name"]] = cmd["id"]
            expressions[cmd["params"]["name"]] = cmd["params"]["expression"]
    return [
        {
            "name": name,
            "expression": expressions.get(name, ""),
            "value": S.doc.variables_resolved.get(name),
            "command_id": cmd_id,
        }
        for name, cmd_id in defining.items()
    ]


def groups_payload() -> list[dict]:
    """Grupos/sub-ensamblajes con sus members faltantes (integridad tolerante)."""
    from apolo.assembly.groups import missing_members

    gone = missing_members(S.doc.scene, S.doc.groups)
    return [
        {**g, "missing_members": gone.get(g["name"], [])}
        for g in S.doc.groups.values()
    ]


def document_payload() -> dict:
    return {
        "name": S.doc.name,
        "commands": S.doc.commands,
        "can_undo": S.doc.can_undo,
        "can_redo": S.doc.can_redo,
        # qué revierte cada cambio de las pilas, el más próximo primero (deshacer-con-etiqueta D5)
        "undo_labels": S.doc.undo_labels,
        "redo_labels": S.doc.redo_labels,
        "variables": variables_payload(),
        "configurations": sorted(S.doc.configurations.keys()),
        "configuration_values": {k: dict(v) for k, v in S.doc.configurations.items()},  # V6.4c: tabla
        "groups": groups_payload(),
        "project_id": S.project_id,
        # robustez (V6.1): comandos suprimidos por una carga tolerante + estado del
        # autosave (None = sano). La UI pinta un chip cuando el disco no responde.
        "suppressed_commands": S.doc.regen_suppressed,
        "autosave_failed": S.autosave_error,
    }


_DEF_MESH_CACHE: dict[str, dict] = {}


def _zona_por_cara(componente: str | None, shape) -> tuple[str, ...] | None:
    """Zona de cada cara si la pieza es de un componente con zonas y conserva la forma del
    builder (seta-de-emergencia D1); None en todo otro caso (lo de siempre)."""
    if not componente:
        return None
    from apolo.library.zonas import zona_por_cara

    return zona_por_cara(componente, shape)


def _definition_mesh(key: str, componente: str | None = None) -> dict | None:
    """Malla de la definición `key`. Con `componente` (el de las piezas que la instancian: una
    definición es de UN componente) los triángulos van agrupados por zona y el dict lleva las
    `zonas` de `mesh_payload`, que el payload saca antes de mandarlo (`_sin_zonas`)."""
    from apolo.commands.registry import DEFINITIONS, touch_definition

    if key not in DEFINITIONS:
        return None
    touch_definition(key)  # LRU: renderizar una definición la protege de la evicción (Fix A)
    if key not in _DEF_MESH_CACHE:
        if len(_DEF_MESH_CACHE) > 128:
            _DEF_MESH_CACHE.clear()
        shape = DEFINITIONS[key]
        _DEF_MESH_CACHE[key] = mesh_payload(shape,
                                            zona_por_cara=_zona_por_cara(componente, shape))
    return _DEF_MESH_CACHE[key]


def _sin_zonas(mesh: dict) -> dict:
    """La malla tal como viaja: sin los rangos por nombre de zona (van en la pieza, con su
    apariencia). Una malla sin zonas es el MISMO objeto (payload byte-idéntico)."""
    if "zonas" not in mesh:
        return mesh
    return {k: v for k, v in mesh.items() if k != "zonas"}


def _zonas_pieza(rangos: list[dict] | None, aps: dict[str, dict] | None) -> list[dict] | None:
    """`zonas` de la entrada de una pieza (seta-de-emergencia D2): `[{acabado, albedo, desde,
    hasta}]` en índices de TRIÁNGULO de su malla (o de la de su definición), contiguos y
    cubriendo todos. None si la malla no se partió o la pieza no tiene apariencias de zona."""
    if not rangos or not aps or any(r["zona"] not in aps for r in rangos):
        return None
    return [{"acabado": aps[r["zona"]]["acabado"], "albedo": aps[r["zona"]]["color"],
             "desde": r["desde"], "hasta": r["hasta"]} for r in rangos]


def _rangos_de(feat) -> list[dict] | None:
    """Rangos de zona de la malla que el payload completo le da a `feat` (la de su definición
    o la propia): los mismos que ya tiene el cliente de una entrada `same` (cachés por
    identidad; sólo re-tesela si se desalojaron)."""
    malla = None
    if feat.mesh_key and feat.matrix:
        malla = _definition_mesh(feat.mesh_key, feat.component)
    if malla is None:
        malla = _cached_render(feat.shape, want_mesh=True, componente=feat.component)["mesh"]
    return malla.get("zonas")


# Caché de datos de render por IDENTIDAD del shape OCCT (mesh/volumen/bbox). El
# regenerate incremental conserva la MISMA referencia de shape para las features que
# no cambiaron, así que solo se re-tesela/recalcula lo que cambió. La referencia fuerte
# al shape evita reutilización de id mientras está en caché.
_SHAPE_CACHE: dict[int, tuple] = {}
_SHAPE_CACHE_CAP = 2048


def _cached_render(shape, want_mesh: bool, componente: str | None = None) -> dict:
    """Volumen, bbox y (con `want_mesh`) malla del shape, por identidad. `componente` = la ref
    de catálogo de la pieza: si tiene zonas, la malla las lleva (como `_definition_mesh`)."""
    key = id(shape)
    hit = _SHAPE_CACHE.get(key)
    if hit is None or hit[0] is not shape:
        if len(_SHAPE_CACHE) > _SHAPE_CACHE_CAP:
            _SHAPE_CACHE.clear()
        hit = (shape, {"volume": round(shape.volume, 1), "bbox": bbox_payload(shape)})
        _SHAPE_CACHE[key] = hit
    data = hit[1]
    if want_mesh and "mesh" not in data:
        data["mesh"] = mesh_payload(shape, zona_por_cara=_zona_por_cara(componente, shape))
    return data


# Revisión de GEOMETRÍA por feature (V6.2b): sube cuando el shape de la feature cambia de
# IDENTIDAD. El regenerate incremental conserva la MISMA referencia de shape para lo no
# tocado → rev estable = exactamente la señal que necesita el cliente para NO reconstruir
# esa malla. Ref fuerte al shape (como _SHAPE_CACHE) evita reuso de id() estando en caché.
_GEOM_REVS: dict[str, tuple] = {}

# Epoch de PROCESO de la escena (V6.2e Fix 2): los revs viven en el proceso pero el navegador
# lo sobrevive; tras un restart del API los revs renacen en 1 y COLISIONAN con los del cliente
# → el delta respondería `same:true` con geometría vieja. Un uuid nuevo por arranque invalida
# los revs del cliente: si el `epoch` que manda en el delta no coincide, se le da el payload
# COMPLETO (known vacío). Cambiar de proyecto NO cambia el epoch (los revs se podan por fid).
SCENE_EPOCH = __import__("uuid").uuid4().hex


def _geom_rev(fid: str, shape) -> int:
    prev = _GEOM_REVS.get(fid)
    if prev is not None and prev[0] is shape:
        return prev[1]
    rev = (prev[1] + 1) if prev is not None else 1
    _GEOM_REVS[fid] = (shape, rev)
    return rev


def scene_payload(known: dict | None = None) -> dict:
    """Payload de escena. Con ``known`` (delta, V6.2b) = ``{"revs": {fid: rev}, "defs":
    [mesh_keys]}`` las features cuya geometría el cliente YA tiene (rev coincide) van con
    ``mesh=null`` + ``same=true`` (metadatos SIEMPRE: name/color/visible/group cambian sin
    tocar geometría) y las definiciones ya conocidas se omiten. ``known=None`` (default) =
    payload COMPLETO idéntico al de siempre + el campo ``rev`` por feature (aditivo)."""
    from apolo.kernel.matrix import to_column_major16
    from apolo.services.apariencia import apariencias_documento, zonas_documento

    known_revs = (known or {}).get("revs") or {}
    known_defs = set((known or {}).get("defs") or [])

    features = []
    definitions: dict[str, dict] = {}
    cmd_types = {c["id"]: c["type"] for c in S.doc.commands}
    # acabado (tabla D5 de visor-realista) y albedo por pieza: metadato VOLÁTIL (set_material y
    # set_color no cambian el rev) → viaja también en las entradas `same`. Igual el de cada zona
    # de acabado (seta-de-emergencia D2/D3), sólo en las piezas que las tienen.
    aps = apariencias_documento(S.doc)
    aps_zonas = zonas_documento(S.doc)
    live: set[str] = set()
    for i, feat in enumerate(S.doc.scene.values()):
        live.add(feat.id)
        rev = _geom_rev(feat.id, feat.shape)
        color = S.doc.colors.get(feat.id) or PALETTE[i % len(PALETTE)]
        ap = aps[feat.id]
        con_zonas = feat.id in aps_zonas
        def_mesh = None
        if known_revs.get(feat.id) == rev:
            # geometría sin cambios: el cliente conserva su malla/bbox/volumen (los mergea de
            # su estado anterior). Solo mandamos id + rev + señal + metadatos VOLÁTILES (los
            # que cambian sin tocar geometría). Ni teselar ni tocar la definición (salvo una
            # pieza con zonas: sus rangos salen de la malla en caché).
            entry = {
                "id": feat.id, "rev": rev, "same": True,
                "name": feat.name, "color": color,
                "visible": feat.visible, "group": feat.group,
                "is_guide": feat.is_guide,  # V6.2e Fix 7: toggle de guía es metadato (rev estable)
                "acabado": ap["acabado"], "albedo": ap["color"],
            }
            if con_zonas:
                zonas = _zonas_pieza(_rangos_de(feat), aps_zonas[feat.id])
                if zonas is not None:
                    entry["zonas"] = zonas
            features.append(entry)
            continue
        if feat.mesh_key and feat.matrix:
            def_mesh = _definition_mesh(feat.mesh_key, feat.component)
        rd = _cached_render(feat.shape, want_mesh=def_mesh is None, componente=feat.component)
        entry = {
            "id": feat.id,
            "name": feat.name,
            "visible": feat.visible,
            "color": color,
            "volume_mm3": rd["volume"],
            "bbox": rd["bbox"],
            "mesh": None,
            "mesh_key": None,
            "matrix": None,
            "command_id": feat.command_id,
            "command_type": cmd_types.get(feat.command_id),
            "component": feat.component,
            "cut_length": feat.cut_length,
            "group": feat.group,
            "is_guide": feat.is_guide,
            "acabado": ap["acabado"],
            "albedo": ap["color"],
            "rev": rev,
        }
        if def_mesh is not None:
            entry["mesh_key"] = feat.mesh_key
            entry["matrix"] = to_column_major16(feat.matrix)
            if feat.mesh_key not in known_defs:  # la definición solo si el cliente no la tiene
                definitions[feat.mesh_key] = _sin_zonas(def_mesh)
            malla = def_mesh
        else:
            malla = rd["mesh"]
            entry["mesh"] = _sin_zonas(malla)
        if con_zonas:
            zonas = _zonas_pieza(malla.get("zonas"), aps_zonas[feat.id])
            if zonas is not None:
                entry["zonas"] = zonas
        features.append(entry)
    # podar revs de features que ya no existen (evita crecer sin límite entre proyectos)
    for gone in [f for f in _GEOM_REVS if f not in live]:
        del _GEOM_REVS[gone]
    return {
        "features": features,
        "definitions": definitions,
        "document": document_payload(),
        "total_features": len(features),
        "epoch": SCENE_EPOCH,  # V6.2e Fix 2: el cliente lo devuelve en el delta (aditivo)
    }


def _feature_brief(fid: str, feat) -> dict:
    """Sólido SIN malla para el brief del agente (V6.5a) en la forma ÚNICA de `apolo.brief`
    (`brief_pieza`, la misma que arma el cliente MCP en `_scene_brief`): la lectura filtrada y
    la mutación se ven igual. Reusa `_cached_render` (bbox/volumen por identidad de shape, sin
    teselar)."""
    rd = _cached_render(feat.shape, want_mesh=False)
    return brief_pieza(
        fid, feat.name, feat.visible, rd["bbox"], rd["volume"], feat.command_id,
        componente=feat.component, grupo=feat.group, boceto=getattr(feat, "is_guide", False),
    )


def scene_summary_dict() -> dict:
    """Resumen por GRUPO (V6.5a): por cada grupo de nivel superior, n_piezas + masa +
    bbox conjunto (RECURSIVO, incluye sub-grupos) + nombres de sub-grupos; más un bloque
    «(sin grupo)», totales y variables. La vista con la que el agente ENTRA a un proyecto
    grande sin volcar la escena (~30 líneas para 5000 piezas)."""
    from apolo.assembly.groups import children_of, group_features
    from apolo.library.engineering.mass import scene_mass_properties

    scene, groups = S.doc.scene, S.doc.groups
    mat = S.doc.default_material()

    def agg(fids):
        if not fids:
            return {"n_piezas": 0, "masa_kg": 0.0, "bbox_mm": [0, 0, 0]}
        mp = scene_mass_properties(scene, ids=fids, default_material=mat)["total"]
        return {"n_piezas": len(fids), "masa_kg": mp["masa_kg"], "bbox_mm": mp["bbox_mm"]}

    rows = []
    for g in groups.values():
        if g.get("parent"):
            continue  # solo nivel superior; los sub-grupos se listan por nombre para drill-down
        fids = group_features(scene, groups, g["name"], recursive=True)
        rows.append({
            "grupo": g["name"], "rol": g.get("role"),
            **agg(fids), "sub_grupos": children_of(groups, g["name"]),
        })

    sin_grupo = [fid for fid, f in scene.items() if not f.group]
    total = scene_mass_properties(scene, default_material=mat)["total"]
    return {
        "proyecto": S.doc.name,
        "total_solidos": len(scene),
        "masa_total_kg": total["masa_kg"],
        "bbox_conjunto_mm": total["bbox_mm"],
        "grupos": rows,
        "sin_grupo": agg(sin_grupo),
        "variables": variables_payload(),
    }


def _open_briefing() -> dict:
    """Briefing compacto de APERTURA (V6.5b, frente D): resumen por grupo + variables (de
    scene_summary_dict) + requisitos + ficha del encargo + notas del agente + salud
    (ok/suprimidos) + variantes de diseño. Arrancar una sesión pasa de 4-5 llamadas a 1. Llamar bajo STATE_LOCK. Presupuesto:
    <10 KB en un proyecto grande (sin mallas, resumen por grupo)."""
    raw = S.doc.check_integrity()
    issues = [i for i in raw if not i.startswith("degradado")]
    notas = list(S.doc.agent_notes)
    brief = {
        "resumen": scene_summary_dict(),  # proyecto/totales/grupos/sin_grupo/variables
        "requisitos": S.doc.requirements,
        # la ficha del encargo: qué falta pedir y qué está asumido (revision-de-taller, D1)
        "ficha": estado_ficha(S.doc.requirements),
        # V6.5c: el ÚNICO campo sin techo natural — últimas 20 y recorte DECLARADO
        "notas_agente": notas[-20:],
        "salud": {
            "ok": not issues and not S.startup_error,
            "suprimidos": getattr(S.doc, "regen_suppressed", []),
        },
    }
    if len(notas) > 20:
        brief["notas_truncadas"] = len(notas) - 20  # sin caps silenciosos

    if S.doc.configurations:  # tabla de diseño: las variantes y sus columnas
        brief["configuraciones"] = sorted(S.doc.configurations.keys())
        brief["tabla_variantes"] = {k: dict(v) for k, v in S.doc.configurations.items()}
    return brief


def _feature_colors() -> dict:
    """Color por pieza IDÉNTICO al viewport web (DOC.colors asignados, o paleta por índice de
    escena) para que el sombreado del plano coincida con lo que el usuario ve en 3D."""
    return {feat.id: S.doc.colors.get(feat.id) or PALETTE[i % len(PALETTE)]
            for i, feat in enumerate(S.doc.scene.values())}
