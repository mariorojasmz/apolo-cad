"""Prueba pura de _scene_brief (filtro 'diff'/'summary'/'full') sin levantar el servidor."""

import pytest

pytest.importorskip("mcp")  # el cliente MCP necesita el paquete mcp

from apolo.mcp_server import _scene_brief


def _feat(fid, cmd):
    return {
        "id": fid,
        "name": fid,
        "visible": True,
        "bbox": {"min": [0, 0, 0], "max": [1, 1, 1]},
        "volume_mm3": 1.0,
        "component": None,
        "command_id": cmd,
    }


def _payload(features, affected=None, total=None):
    return {
        "document": {
            "name": "t",
            "variables": [],
            "configurations": [],
            "can_undo": True,
            "can_redo": False,
        },
        "features": features,
        "total_features": total if total is not None else len(features),
        "affected_command_ids": affected or [],
    }


def test_brief_diff_filters_to_affected():
    p = _payload([_feat("c1", "c1"), _feat("c2", "c2"), _feat("c3", "c3")], affected=["c2"])
    b = _scene_brief(p, "diff")
    assert [s["id"] for s in b["solidos"]] == ["c2"]
    assert b["total_solidos"] == 3 and b["solidos_mostrados"] == 1


def test_brief_full_keeps_all():
    p = _payload([_feat("c1", "c1"), _feat("c2", "c2")], affected=["c1"])
    assert len(_scene_brief(p, "full")["solidos"]) == 2


def test_brief_summary_omits_bbox():
    p = _payload([_feat("c1", "c1")], affected=["c1"])
    b = _scene_brief(p, "summary")
    assert b["solidos"] and set(b["solidos"][0]) == {"id", "nombre", "comando"}


def test_brief_diff_empty_affected_returns_all():
    """Consultas (sin afectados): 'diff' no oculta la escena → devuelve todos."""
    p = _payload([_feat("c1", "c1"), _feat("c2", "c2")], affected=[])
    assert len(_scene_brief(p, "diff")["solidos"]) == 2


def test_brief_variable_edit_zero_solids():
    """Editar una variable afecta a su comando, que no es ninguna feature → 0 sólidos + conteo."""
    p = _payload([_feat("c1", "c1"), _feat("c2", "c2")], affected=["cVAR"], total=2)
    b = _scene_brief(p, "diff")
    assert b["solidos"] == [] and b["total_solidos"] == 2


def _payload_cmds(features, affected, commands, variables):
    """Payload con `commands` (para detectar set_variable) y `variables`."""
    return {
        "document": {
            "name": "t",
            "variables": variables,
            "configurations": [],
            "can_undo": True,
            "can_redo": False,
            "commands": commands,
        },
        "features": features,
        "total_features": len(features),
        "affected_command_ids": affected,
    }


_CMDS = [{"id": "c1", "type": "create_box"}, {"id": "v1", "type": "set_variable"}]


def test_brief_omits_variables_on_geometry_edit():
    """Mutación de geometría (afectado NO es set_variable): se OMITE el bloque variables."""
    p = _payload_cmds([_feat("c1", "c1")], ["c1"], _CMDS, [{"name": "R"}])
    assert "variables" not in _scene_brief(p, "diff")


def test_brief_includes_variables_when_var_changed():
    """Si el afectado es un set_variable, SÍ se incluyen las variables."""
    p = _payload_cmds([_feat("c1", "c1")], ["v1"], _CMDS, [{"name": "R"}])
    assert _scene_brief(p, "diff").get("variables") == [{"name": "R"}]


def test_brief_includes_variables_on_full():
    """detail='full' siempre incluye variables."""
    p = _payload_cmds([_feat("c1", "c1")], ["c1"], _CMDS, [{"name": "R"}])
    assert "variables" in _scene_brief(p, "full")


def test_brief_includes_variables_on_query():
    """Consulta (sin afectados, p. ej. get_scene): incluye variables."""
    p = _payload_cmds([_feat("c1", "c1")], [], _CMDS, [{"name": "R"}])
    assert "variables" in _scene_brief(p, "diff")
