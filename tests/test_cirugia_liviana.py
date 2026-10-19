"""Cirugía liviana (plan `docs/plans/cirugia-liviana.md`, D1–D3).

- F1: `POST /api/commands/remove?detail=diff` responde SIN la escena (comandos, piezas y uniones
  que se fueron + `total_solidos`); sin `detail` la respuesta es byte-idéntica a la de antes (la
  UI). `con_dependientes` (D2) arrastra los `fasten`/`ground` que nombran las piezas borradas y
  las saca de sus grupos en el MISMO cambio (1 undo).
- F2: la tool MCP `remove_commands` va por el embudo de mutaciones (`_mutacion`: job + recibo) y
  usa el modo liviano; el resultado de un job liviano pasa tal cual por `get_job`.
"""

from __future__ import annotations

import asyncio
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import apolo.api.common as common
import apolo.api.main as api
from apolo.api.routers.commands import RemoveIn
from apolo.api.session import S
from apolo.doc import Document
from apolo.services import cirugia
from apolo.state import STATE_LOCK


def _caja(doc, nombre, x=0):
    return doc.execute("create_box", {"name": nombre, "width": 50, "depth": 50, "height": 50,
                                      "position": {"x": x, "y": 0, "z": 0}})


def _maquina() -> tuple[Document, dict]:
    """A, B y C con A↔B atornilladas, A anclada, un grupo con A y B y otro sólo con C."""
    doc = Document("cirugia")
    ids = {"A": _caja(doc, "A"), "B": _caja(doc, "B", 50), "C": _caja(doc, "C", 200)}
    ids["f"] = doc.execute("fasten", {"name": "f_ab", "a": ids["A"], "b": ids["B"]})
    ids["g"] = doc.execute("ground", {"name": "g_a", "feature": ids["A"]})
    ids["G"] = doc.execute("create_group", {"name": "Bastidor", "members": [ids["A"], ids["B"]]})
    ids["H"] = doc.execute("create_group", {"name": "Suelta", "members": [ids["C"]]})
    return doc, ids


def _activa() -> tuple[Document, dict]:
    """`_maquina()` como documento activo de la API."""
    doc, ids = _maquina()
    api.DOC = doc
    return doc, ids


def _post(client, ids, detail=None, **extra):
    params = {"detail": detail} if detail else {}
    return client.post("/api/commands/remove", params=params, json={"ids": ids, **extra})


def _await_job(client, job_id, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}", params={"wait_s": 5}).json()
        if job["estado"] in ("ok", "error"):
            return job
    raise AssertionError(f"el job {job_id} no terminó en {timeout}s")


# --------------------------------------------------------------- F1: sin detail, como antes
def _endpoint_de_antes() -> FastAPI:
    """El endpoint tal como estaba antes de F1 (copiado literal): la vara del byte-idéntico."""
    viejo = FastAPI()

    @viejo.post("/api/commands/remove")
    def remove_commands_endpoint(body: RemoveIn) -> dict:
        return common._state_or_error(lambda: S.doc.remove_commands(body.ids))

    return viejo


def test_sin_detail_la_respuesta_es_byte_identica_a_la_de_antes(monkeypatch):
    """Escena determinista (sin `rev`, que depende de la identidad del shape) con un float que
    distingue los serializadores (`1e-7` de pydantic vs `1e-07` de `jsonable_encoder`)."""
    def escena_fija():
        return {"features": [{"id": fid, "name": f.name, "vol": 1e-7, "ñ": "ü"}
                             for fid, f in sorted(S.doc.scene.items())],
                "total_features": len(S.doc.scene)}

    monkeypatch.setattr(common, "scene_payload", escena_fija)
    salidas = []
    for app in (_endpoint_de_antes(), api.app):
        _, ids = _activa()
        r = TestClient(app).post("/api/commands/remove", json={"ids": [ids["C"]]})
        assert r.status_code == 200, r.text
        salidas.append(r.content)
    assert salidas[0] == salidas[1]
    assert b"1e-7" in salidas[1] and b"comandos_borrados" not in salidas[1]


def test_sin_detail_la_ruta_sigue_sincrona_con_su_serializador():
    route = next(r for r in api.app.routes
                 if getattr(r, "path", None) == "/api/commands/remove")
    assert route.response_model is dict
    _, ids = _activa()
    r = _post(TestClient(api.app), [ids["C"]])
    assert r.status_code == 200
    assert {"features", "document", "affected_command_ids"} <= set(r.json())


def test_detail_invalido_da_400_sin_tocar_nada():
    doc, ids = _activa()
    antes = json.dumps(doc.commands)
    r = _post(TestClient(api.app), [ids["C"]], detail="full")
    assert r.status_code == 400 and "detail admite sólo 'diff'" in r.json()["detail"]
    assert json.dumps(doc.commands) == antes


# ------------------------------------------------------------------- F1: detail=diff (D1)
def test_detail_diff_responde_corto_con_piezas_y_uniones_que_se_fueron():
    client = TestClient(api.app)
    _, ids = _activa()
    completa = _post(client, [ids["B"], ids["f"]])
    doc, ids = _activa()
    r = _post(client, [ids["B"], ids["f"]], detail="diff")
    assert r.status_code == 200, r.text
    out = r.json()
    assert len(r.content) < len(completa.content) / 10
    assert "features" not in out and "document" not in out
    assert out["comandos_borrados"] == [ids["B"], ids["f"]]
    assert out["piezas_borradas"] == [{"id": ids["B"], "nombre": "B"}]
    assert out["uniones_borradas"] == [{"nombre": "f_ab", "tipo": "fijador"}]
    assert out["total_solidos"] == len(doc.scene) == 2
    assert "dependientes" not in out  # sólo con con_dependientes
    assert doc.can_undo


def test_detail_diff_no_arma_la_escena(monkeypatch):
    """El costo de la escena (teselado de todo) es lo que el modo liviano se ahorra."""
    def prohibida(*a, **k):
        raise AssertionError("detail=diff no debe armar la escena completa")

    monkeypatch.setattr(common, "scene_payload", prohibida)
    _, ids = _activa()
    assert _post(TestClient(api.app), [ids["C"]], detail="diff").status_code == 200


def test_detail_diff_con_referencia_rota_da_el_mismo_400_y_no_borra_nada():
    doc, ids = _activa()
    antes = json.dumps(doc.commands)
    r = _post(TestClient(api.app), [ids["B"]], detail="diff")
    assert r.status_code == 400
    assert "El fijador 'f_ab' referencia el sólido" in r.json()["detail"]
    assert json.dumps(doc.commands) == antes


def test_detail_diff_lista_juntas_y_grupos_que_se_fueron():
    doc, ids = _activa()
    j = doc.execute("add_joint", {"name": "bisagra", "parent": ids["A"], "child": ids["C"]})
    out = _post(TestClient(api.app), [j, ids["H"]], detail="diff").json()
    assert out["uniones_borradas"] == [{"nombre": "bisagra", "tipo": "junta"}]
    assert out["grupos_borrados"] == ["Suelta"]
    assert out["piezas_borradas"] == []


# -------------------------------------------------------------------- F1: dependientes (D2)
def test_sin_dependientes_el_fijador_estorba():
    _, ids = _activa()
    r = _post(TestClient(api.app), [ids["A"]], detail="diff")
    assert r.status_code == 400 and "elimina primero" in r.json()["detail"]


def test_con_dependientes_arrastra_fijador_anclaje_y_membresia_en_un_undo():
    doc, ids = _activa()
    antes = json.loads(json.dumps(doc.commands))
    r = _post(TestClient(api.app), [ids["A"]], detail="diff", con_dependientes=True)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["comandos_borrados"] == [ids["A"], ids["f"], ids["g"]]
    assert out["dependientes"] == [{"id": ids["f"], "tipo": "fasten", "nombre": "f_ab"},
                                   {"id": ids["g"], "tipo": "ground", "nombre": "g_a"}]
    assert out["grupos_editados"] == [{"grupo": "Bastidor", "quitados": [ids["A"]]}]
    assert out["affected_command_ids"] == [ids["G"]]
    assert {u["nombre"] for u in out["uniones_borradas"]} == {"f_ab", "g_a"}
    assert "avisos" not in out
    assert doc.groups["Bastidor"]["members"] == [ids["B"]]
    assert not doc.fasteners and not doc.grounds
    doc.undo()  # UN undo repone todo
    assert doc.commands == antes


def test_con_dependientes_un_grupo_que_quedaria_vacio_no_se_toca():
    doc, ids = _activa()
    out = _post(TestClient(api.app), [ids["C"]], detail="diff", con_dependientes=True).json()
    assert out["dependientes"] == [] and out["grupos_editados"] == []
    assert out["avisos"] == ["El grupo «Suelta» quedaría vacío: no se tocó (bórralo si sobra)"]
    assert doc.groups["Suelta"]["members"] == [ids["C"]]


def test_con_dependientes_no_arrastra_juntas():
    doc, ids = _activa()
    doc.execute("add_joint", {"name": "bisagra", "parent": ids["A"], "child": ids["C"]})
    r = _post(TestClient(api.app), [ids["C"]], detail="diff", con_dependientes=True)
    assert r.status_code == 400 and "(add_joint)" in r.json()["detail"]
    assert ids["C"] in doc.scene  # nada se borró


def test_con_dependientes_sin_detail_suma_las_listas_a_la_escena():
    _, ids = _activa()
    out = _post(TestClient(api.app), [ids["A"]], con_dependientes=True).json()
    assert "features" in out
    assert [d["id"] for d in out["dependientes"]] == [ids["f"], ids["g"]]
    assert out["grupos_editados"] == [{"grupo": "Bastidor", "quitados": [ids["A"]]}]


def test_dependientes_de_un_insert_project_por_prefijo():
    """`piezas_de` sigue la regla del brief: `{cmd}_{orig}` también es del comando."""
    doc, ids = _maquina()
    with STATE_LOCK:
        assert cirugia.piezas_de(doc, [ids["A"]]) == {ids["A"]}
        feat = doc.scene[ids["B"]]
        feat.command_id = f"{ids['A']}_c1"  # como lo emite insert_project
        assert cirugia.piezas_de(doc, [ids["A"]]) == {ids["A"], ids["B"]}


# ---------------------------------------------------------------------------- F1: async
def test_async_encola_y_el_job_trae_el_payload_liviano():
    client = TestClient(api.app)
    _, ids = _activa()
    sincrono = _post(client, [ids["A"]], detail="diff", con_dependientes=True).json()
    _, ids = _activa()
    r = client.post("/api/commands/remove", params={"detail": "diff", "async": "true"},
                    json={"ids": [ids["A"]], "con_dependientes": True})
    assert r.status_code == 202, r.text
    job = _await_job(client, r.json()["job_id"])
    assert job["estado"] == "ok" and job["tipo"] == "remove_commands", job
    assert job["resultado"] == sincrono


# ------------------------------------------------------------------------- F2: la tool MCP
@pytest.fixture
def mcp_server():
    pytest.importorskip("mcp")
    import apolo.mcp_server as mod

    return mod


class _SinLifespan:
    def __init__(self, cliente):
        self._cliente = cliente

    def __enter__(self):
        return self._cliente

    def __exit__(self, *exc):
        return False


def _texto(out) -> str:
    bloques = out[0] if isinstance(out, tuple) else out
    return bloques[0].text


def test_la_tool_borra_por_job_en_modo_liviano_contra_la_api_real(mcp_server):
    from apolo.tools.destino import Destino, apuntar

    cliente = TestClient(api.app)
    doc, ids = _activa()
    with apuntar(Destino("http://testserver", lambda: _SinLifespan(cliente))):
        out = json.loads(_texto(asyncio.run(mcp_server.mcp.call_tool(
            "remove_commands", {"ids": [ids["A"]], "con_dependientes": True}))))
    assert out["comandos_borrados"] == [ids["A"], ids["f"], ids["g"]]
    assert out["total_solidos"] == 2 and "features" not in out
    assert len(json.dumps(out)) < 5000  # F3 pide < 5 KB
    assert ids["A"] not in doc.scene


def test_la_tool_full_lista_la_escena_y_el_recibo_pasa_por_get_job(monkeypatch, mcp_server):
    from apolo.tools.destino import Destino, apuntar

    cliente = TestClient(api.app)
    _, ids = _activa()
    destino = Destino("http://testserver", lambda: _SinLifespan(cliente))
    with apuntar(destino):
        full = json.loads(_texto(asyncio.run(mcp_server.mcp.call_tool(
            "remove_commands", {"ids": [ids["C"]], "detail": "full"}))))
    assert full["total_solidos"] == 2 and len(full["solidos"]) == 2

    _, ids = _activa()
    monkeypatch.setattr(mcp_server, "APOLO_MCP_WAIT_S", 0.0)  # recibo sin esperar
    with apuntar(destino):
        recibo = json.loads(_texto(asyncio.run(mcp_server.mcp.call_tool(
            "remove_commands", {"ids": [ids["C"]]}))))
        assert set(recibo) == {"job", "estado", "seguir"}
        brief = json.loads(mcp_server.get_job(recibo["job"], wait_s=10))
    assert brief.pop("job") == recibo["job"]
    assert brief["comandos_borrados"] == [ids["C"]] and "solidos" not in brief
