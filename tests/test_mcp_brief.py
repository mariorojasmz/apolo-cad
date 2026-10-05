"""Prueba pura de _scene_brief (filtro 'diff'/'summary'/'full') sin levantar el servidor."""

import json

import pytest

pytest.importorskip("mcp")  # el cliente MCP necesita el paquete mcp

from apolo.mcp_server import _one_or_many, _scene_brief


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


def test_one_or_many_excluyentes():
    """Params `x`/`xs` de las tools por lote (V6.8-A): exactamente uno de los dos."""
    assert _one_or_many("c1", None) == ["c1"]
    assert _one_or_many(None, ["c1", "c2"]) == ["c1", "c2"]
    with pytest.raises(ValueError, match="exactamente uno"):
        _one_or_many(None, None)
    with pytest.raises(ValueError, match="exactamente uno"):
        _one_or_many("c1", ["c2"])


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


# ---------------------------------------------- retorno compacto de visibilidad/material
# (Frente C) Los endpoints de visibilidad/material adjuntan `affected_command_ids`
# → el cliente MCP (que ya envuelve con _scene_brief) recorta a la pieza afectada
# en vez de volcar la escena completa (~1 MB con mallas en una faja real).

from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc.document import Document


def _doc_two_boxes():
    doc = Document("brief-vis")
    a = doc.execute("create_box", {"name": "A", "width": 50, "depth": 50, "height": 50})
    b = doc.execute("create_box", {"name": "B", "width": 50, "depth": 50, "height": 50,
                                   "position": {"x": 200, "y": 0, "z": 0}})
    return doc, a, b


def test_visibility_endpoint_attaches_affected():
    api.DOC, a, b = _doc_two_boxes()
    client = TestClient(api.app)
    r = client.post(f"/api/features/{a}/visibility", json={"visible": False})
    assert r.status_code == 200
    payload = r.json()
    assert payload["affected_command_ids"] == [api.DOC.scene[a].command_id]
    brief = _scene_brief(payload, "diff")
    assert [s["id"] for s in brief["solidos"]] == [a]
    assert brief["total_solidos"] == 2


def test_visibility_bulk_endpoint_attaches_affected():
    api.DOC, a, b = _doc_two_boxes()
    client = TestClient(api.app)
    r = client.post("/api/features/visibility", json={"ids": [a, b], "visible": False})
    payload = r.json()
    assert sorted(payload["affected_command_ids"]) == sorted(
        {api.DOC.scene[a].command_id, api.DOC.scene[b].command_id}
    )
    brief = _scene_brief(payload, "diff")
    assert sorted(s["id"] for s in brief["solidos"]) == sorted([a, b])


def test_material_endpoint_attaches_affected():
    api.DOC, a, b = _doc_two_boxes()
    client = TestClient(api.app)
    r = client.post(f"/api/features/{a}/material", json={"material": "acero"})
    assert r.status_code == 200
    payload = r.json()
    assert payload["affected_command_ids"] == [api.DOC.scene[a].command_id]
    brief = _scene_brief(payload, "diff")
    assert [s["id"] for s in brief["solidos"]] == [a]  # solo la pieza, no la escena


# ---------------------------------------------- una sola forma del brief de pieza (D16)
_ORDEN_CANONICO = ["id", "nombre", "visible", "bbox", "volumen_mm3", "comando",
                   "componente", "grupo", "boceto"]


def test_una_sola_forma_del_brief_de_pieza():
    """D16 (chat-cliente-igual): para las MISMAS piezas, el brief del MCP (`_scene_brief` sobre
    el payload completo) y el del servidor (`GET /api/scene?limit=-1` → `_feature_brief`) son
    el MISMO texto: mismas claves en el mismo orden y los opcionales omitidos, nunca `null`."""
    doc = Document("brief-unico")
    lisa = doc.execute("create_box", {"name": "Lisa", "width": 50, "depth": 50, "height": 50})
    chum = doc.execute("insert_component", {"component": "UCP205",
                                            "position": {"x": 300, "y": 0, "z": 0}})
    guia = doc.execute("create_box", {"name": "Guía", "width": 10, "depth": 10, "height": 10,
                                      "position": {"x": -300, "y": 0, "z": 0}})
    doc.execute("create_group", {"name": "Soporte", "members": [chum]})
    api.DOC = doc
    client = TestClient(api.app)
    assert client.post(f"/api/features/{guia}/sketch-guide", json={"guide": True}).status_code == 200
    assert client.post(f"/api/features/{lisa}/visibility", json={"visible": False}).status_code == 200

    del_mcp = _scene_brief(client.get("/api/scene").json(), "full")["solidos"]
    del_servidor = client.get("/api/scene", params={"limit": -1}).json()["solidos"]
    assert json.dumps(del_mcp, ensure_ascii=False) == json.dumps(del_servidor, ensure_ascii=False)

    por_id = {s["id"]: s for s in del_mcp}
    assert set(por_id) == {lisa, chum, guia}
    assert por_id[chum]["componente"] == "UCP205" and por_id[chum]["grupo"] == "Soporte"
    assert por_id[guia]["boceto"] is True and por_id[lisa]["visible"] is False
    for s in del_mcp:  # orden canónico; lo que no aplica no viaja (ni `componente: null`)
        assert list(s) == [k for k in _ORDEN_CANONICO if k in s]
        assert None not in s.values()
    assert "componente" not in por_id[lisa] and "grupo" not in por_id[lisa]
    assert "boceto" not in por_id[chum]


def test_brief_pieza_es_la_forma_de_los_dos():
    """Los dos llamadores usan `brief_pieza` (la fuente única), no una copia de sus claves."""
    import inspect

    from apolo import brief
    from apolo.api import scene

    assert scene.brief_pieza is brief.brief_pieza
    for fuente in (inspect.getsource(brief._scene_brief), inspect.getsource(scene._feature_brief)):
        assert "brief_pieza(" in fuente and '"volumen_mm3"' not in fuente
