"""Las reglas de ingeniería en corto (plan mcp-sin-friccion, D1 y D2).

`services/reglas_cortas.py` filtra por familia (`grupo`) y por estado (`solo_fallas`) y agrupa
las reglas repetidas por patrón en UNA línea con el conteo y su peor caso; `POST /api/checks`
lo aplica sólo si se lo piden (sin esos campos, byte-idéntico: la UI) y la tool
`engineering_check` lo pide por defecto.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.services import reglas_cortas as rc


def _perno(nombre: str, estado: str = "ok", fs=None) -> dict:
    r = {"regla": f"unión apernada · {nombre}", "estado": estado, "detalle": f"{nombre}: 1× M12"}
    if fs is not None:
        r["calc"] = {"fs": fs, "formula": "F ≤ Fadm"}
    return r


VIGA = {"regla": "flecha de viga · Larguero (+Y)", "estado": "ok", "detalle": "δ = 0.3 mm",
        "calc": {"fs": 3.0}, "hipotesis": ["apoyos simples"]}
ERROR = {"regla": "pandeo de patas", "estado": "error", "detalle": "FS 0.8",
         "recomendacion": "sube la sección", "calc": {"fs": 0.8}}


def test_agrupa_por_patron_con_el_peor_caso():
    reglas = [_perno(f"r{k}_eje_larguero_my", fs=4.0 + k) for k in range(19)]
    reglas[7] = _perno("r7_eje_larguero_my", "aviso", fs=1.2)
    reglas += [_perno(f"c1_eje_larg_m[{k}]") for k in range(3)] + [VIGA, ERROR]
    out = rc.reglas_cortas(reglas)
    assert [r["regla"] for r in out] == [
        "unión apernada · r*_eje_larguero_my", "unión apernada · c*_eje_larg_m[*]",
        "flecha de viga · Larguero (+Y)", "pandeo de patas"]
    linea = out[0]
    assert linea["n"] == 19 and linea["estado"] == "aviso"
    assert linea["peor"] == "unión apernada · r7_eje_larguero_my"
    assert "calc" not in linea and out[1]["n"] == 3
    # una sola: sin `calc` ni `hipotesis` si está ok; el error conserva su evidencia
    assert out[2] == {k: VIGA[k] for k in ("regla", "estado", "detalle")}
    assert out[3]["calc"] == {"fs": 0.8} and out[3]["recomendacion"] == "sube la sección"


def test_a_igual_estado_el_peor_es_el_de_menor_fs():
    reglas = [_perno("r1_x", fs=5.0), _perno("r2_x", fs=2.5), _perno("r3_x")]
    assert rc.reglas_cortas(reglas)[0]["peor"] == "unión apernada · r2_x"


def test_filtros_y_conteo():
    reglas = [_perno("r1_x"), _perno("r2_x", "aviso"), VIGA, ERROR]
    assert rc.filtrar_reglas(reglas, grupo="FLECHA") == [VIGA]
    assert rc.filtrar_reglas(reglas, grupo="apernada", solo_fallas=True) == [reglas[1]]
    assert rc.filtrar_reglas(reglas, solo_fallas=True) == [reglas[1], ERROR]
    assert rc.filtrar_reglas(None, grupo="x") is None and rc.reglas_cortas(None) is None
    assert rc.conteo(reglas) == {"ok": 2, "aviso": 1, "error": 1}


# ------------------------------------------------------------------ POST /api/checks
def _cliente() -> TestClient:
    doc = Document("reglas-cortas")
    doc.execute("create_box", {"name": "Placa", "width": 300, "depth": 300, "height": 10})
    doc.execute("create_box", {"name": "Ménsula", "width": 50, "depth": 50, "height": 50,
                               "position": {"z": 30}})
    doc.execute("pattern_linear", {"feature": "c2", "count": 4, "spacing": {"x": 60}})
    doc.execute("ground", {"name": "piso", "feature": "c1"})
    for k, m in enumerate(["c2", "c3_1", "c3_2", "c3_3"]):
        doc.execute("fasten", {"name": f"m{k}_placa", "a": m, "b": "c1", "kind": "perno",
                               "size": "M10", "qty": 2})
    api.DOC = doc
    return TestClient(api.app)


def test_checks_sin_campos_nuevos_no_cambia_y_con_resumen_agrupa():
    client = _cliente()
    completo = client.post("/api/checks", json={}).json()
    assert "conteo" not in completo
    pernos = [r for r in completo["estructura"] if r["regla"].startswith("unión apernada")]
    assert len(pernos) == 4
    corto = client.post("/api/checks", json={"resumen": True}).json()
    assert corto["conteo"]["estructura"] == rc.conteo(completo["estructura"])
    lineas = [r for r in corto["estructura"] if r["regla"].startswith("unión apernada")]
    assert len(lineas) == 1 and lineas[0]["n"] == 4 and lineas[0]["regla"].endswith("m*_placa")
    assert corto["interferencias"] == completo["interferencias"]
    solo = client.post("/api/checks", json={"grupo": "apernada", "solo_fallas": True}).json()
    assert all(r["estado"] != "ok" and "apernada" in r["regla"] for r in solo["estructura"])


def test_la_tool_pide_el_resumen_y_el_detalle_completo_a_pedido(monkeypatch):
    pytest.importorskip("mcp")
    from apolo import mcp_server

    client = _cliente()
    cuerpos: list[dict] = []

    def por_la_api(method, path, **kw):
        cuerpos.append(kw.get("json"))
        return client.request(method, path, **kw)

    monkeypatch.setattr(mcp_server, "_api", por_la_api)
    corto = json.loads(mcp_server.engineering_check())
    assert set(corto) == {"ingenieria", "estructura", "conteo"}
    assert cuerpos[-1]["resumen"] is True and cuerpos[-1]["grupo"] is None
    completo = json.loads(mcp_server.engineering_check(detail="full", grupo="apernada"))
    assert set(completo) == {"ingenieria", "estructura"} and cuerpos[-1]["resumen"] is False
    assert len(completo["estructura"]) == 4 and cuerpos[-1]["grupo"] == "apernada"
