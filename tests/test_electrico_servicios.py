"""Servicios y transporte del tablero eléctrico (plan V8.1 F3: D8, D10 y D11).

- D8: `GET /api/electrico/circuito` (filtro por designación, 404 con sugerencias) y
  `GET /api/electrico/check`; el catálogo expone la ficha eléctrica (`electrico`).
- D10: la BOM y el costeo suman el tablero SIN duplicar el motor ligado a su pieza; cables y
  conductores por metro; sin largo, la fila va sin costo y con aviso (no se inventa).
- D11: sin carril la puerta de entrega da EXACTAMENTE lo de antes; con carril, un error del
  ERC la pone en ROJO y un aviso en AMARILLO. El contrato `{"erc": "sin_errores"}` revierte el
  lote que cablea mal.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from tablero_electrico import arranque_directo, wire

import apolo.api.main as api
from apolo.doc.document import Document
from apolo.library.costing import scene_costing
from apolo.library.delivery import delivery_report
from apolo.services import electrico as svc
from apolo.services.delivery_inputs import delivery_inputs


def _tablero(motor_ligado: bool = True, **kw) -> Document:
    d = Document("tablero")
    fid = None
    if motor_ligado:
        cid = d.execute("insert_component", {"component": "MOTOR-075", "name": "Motorreductor"})
        fid = next(f for f, feat in d.scene.items() if feat.command_id == cid)
    d.execute_many(arranque_directo(pieza_motor=fid, **kw))
    return d


@pytest.fixture
def cliente(monkeypatch):
    def con(doc: Document) -> TestClient:
        monkeypatch.setattr(api, "DOC", doc)
        monkeypatch.setattr(api._autosave_sched, "schedule", lambda: None)
        return TestClient(api.app)
    return con


def _filas(rows: list[dict], ref: str) -> list[dict]:
    return [r for r in rows if r["ref"] == ref]


# ------------------------------------------------------------------ D10: BOM y costeo
def test_la_bom_suma_el_tablero_sin_duplicar_el_motor_ligado():
    d = _tablero()
    filas = svc.filas_bom(d)
    assert not _filas(filas, "MOTOR-075")  # ligado a su pieza: ya cuenta en la escena
    assert not _filas(filas, "RED-3F-220V-60HZ")  # la red no se compra
    assert _filas(filas, "BORNE-PE-4")[0]["cantidad"] == 2  # una bornera, por borne
    [cond] = _filas(filas, "COND-H07VK-2.5")
    assert cond["longitud_mm"] == 11000.0 and cond["cantidad"] == 1  # 11 conductores × 1 m
    [cable] = _filas(filas, "CABLE-4G1.5")
    assert cable["longitud_mm"] == 6000.0
    costeo = scene_costing(d.scene, d.default_material(), filas)
    motores = _filas(costeo["rows"], "MOTOR-075")
    assert len(motores) == 1 and motores[0]["cantidad"] == 1  # la pieza de la escena, una vez
    assert _filas(costeo["rows"], "COND-H07VK-2.5")[0]["costo_total_usd"] == round(0.35 * 11, 2)
    assert _filas(costeo["rows"], "SECC-25A-3P")[0]["costo_ud_usd"] == 45.0
    # un motor SIN pieza entra como fila de catálogo
    suelto = svc.filas_bom(_tablero(motor_ligado=False))
    assert _filas(suelto, "MOTOR-075")[0]["cantidad"] == 1


def test_sin_largo_la_fila_no_se_costea_y_avisa():
    d = _tablero(largo_cable=None, largo=None)
    costeo = scene_costing(d.scene, d.default_material(), svc.filas_bom(d))
    [cable] = _filas(costeo["rows"], "CABLE-4G1.5")
    assert cable["costo_total_usd"] is None and "sin largo declarado" in cable["aviso"]
    assert cable["costo_fuente"] == "sin largo declarado"
    [sin_tipo] = _filas(costeo["rows"], "CONDUCTOR-SIN-TIPO")
    assert sin_tipo["cantidad"] == 14 and sin_tipo["costo_total_usd"] is None
    assert costeo["totales"]["n_filas_sin_costo"] >= 3


def test_sin_carril_bom_y_costeo_no_cambian(cliente):
    d = Document("mecánico")
    d.execute("insert_component", {"component": "MOTOR-075", "name": "Motorreductor"})
    c = cliente(d)
    assert svc.filas_bom(d) == [] and not svc.tiene_carril(d)
    assert c.get("/api/costing.json").json() == scene_costing(d.scene, d.default_material())
    assert all("origen" not in r for r in c.get("/api/bom").json())


def test_api_bom_costeo_y_cotizacion_traen_el_tablero(cliente):
    c = cliente(_tablero())
    bom = c.get("/api/bom").json()
    assert {r["ref"] for r in bom if r.get("origen") == "electrico"} >= {"SECC-25A-3P",
                                                                        "CABLE-4G1.5"}
    assert all(r.get("grupo", "x") is None for r in c.get("/api/bom?by_group=true").json()
               if r.get("origen") == "electrico")
    costeo = c.get("/api/costing.json").json()
    assert costeo["totales"]["por_categoria"]["proteccion_electrica"] > 0
    assert c.get("/api/quote.pdf").status_code == 200
    assert c.get("/api/bom.csv").status_code == 200


# ------------------------------------------------------------------ D11: puerta de entrega
def test_sin_carril_la_puerta_da_exactamente_lo_de_antes():
    d = Document("sin tablero")
    d.execute("create_box", {"name": "Base", "width": 100, "depth": 100, "height": 10})
    entradas = delivery_inputs(d, expand=lambda v: [])
    assert "electrico" not in entradas
    rep = delivery_report(**entradas)
    assert rep == delivery_report(**entradas, electrico=None)
    assert "eléctrico" not in str(rep)  # ni en ok ni en no_aplica: como si no existiera


def test_con_carril_el_erc_entra_al_semaforo(cliente):
    sano = cliente(_tablero(motor_ligado=False))
    rep = sano.post("/api/delivery-check", json={}).json()
    assert "eléctrico (ERC)" in rep["resumen"]["chequeos_ok"] and rep["veredicto"] == "VERDE"
    # un aviso (color de mando) → AMARILLO
    d = Document("aviso")
    acciones = arranque_directo()
    for a in acciones:
        if a["params"].get("puntos") == ["-S0:12", "-S1:11"]:
            a["params"]["color"] = "RD"
    d.execute_many(acciones)
    rep = cliente(d).post("/api/delivery-check", json={}).json()
    assert rep["veredicto"] == "AMARILLO"
    assert [a["regla"] for a in rep["avisos"]] == ["eléctrico · color del conductor"]
    # un error (bobina de 24 VDC en la fase) → ROJO
    d.execute_many([wire("-Q1:2", "-Q3:A1", color="BK", seccion_mm2=1)])
    rep = cliente(d).post("/api/delivery-check", json={}).json()
    assert rep["veredicto"] == "ROJO"
    assert any(b["regla"].startswith("eléctrico · ") for b in rep["bloqueantes"])


# ------------------------------------------------------------------ D11: aserción `erc`
def test_el_contrato_erc_revierte_el_lote_que_cablea_mal(cliente):
    d = Document("contrato")
    c = cliente(d)
    r = c.post("/api/commands/batch", json={"actions": arranque_directo(),
                                            "expect": [{"erc": "sin_errores"}]})
    assert r.status_code == 200, r.text
    assert r.json()["contrato"] == {"n_aserciones": 1, "ok": True}
    n, deshacer = len(d.commands), len(d._undo)
    malo = c.post("/api/commands/batch", json={
        "actions": [wire("-Q1:2", "-Q3:A1", color="BK", seccion_mm2=1)],
        "expect": [{"erc": "sin_errores"}]})
    assert malo.status_code == 400
    assert "Contrato incumplido" in malo.text and "erc" in malo.text
    assert len(d.commands) == n and len(d._undo) == deshacer  # revertido entero, sin undo


def test_la_asercion_erc_en_verify(cliente):
    c = cliente(Document("vacío"))
    [sin] = c.post("/api/verify", json={"checks": [{"erc": "sin_errores"}]}).json()["resultados"]
    assert not sin["ok"] and "no tiene tablero eléctrico" in sin["error"]
    c = cliente(_tablero())
    out = c.post("/api/verify", json={"checks": [
        {"tipo": "existe", "name": "Motorreductor"}, {"erc": "sin_errores"},
        {"erc": "sin_avisos", "nombre": "tablero limpio"}, {"erc": "verde"}]}).json()
    # V8.9 F7b: con la máquina en 3D (el motor), el gabinete -U1 sin pieza es un aviso
    assert [r["ok"] for r in out["resultados"]] == [True, True, False, False]
    sin_gab = c.post("/api/verify", json={"checks": [{"erc": "sin_avisos"}]}).json()["resultados"][0]
    assert "-U1" in str(sin_gab)
    assert out["resultados"][2]["check"] == "tablero limpio"
    assert "espera «sin_errores» o «sin_avisos»" in out["resultados"][3]["error"]


# ------------------------------------------------------------------ D8: transporte
def test_circuito_y_chequeo_por_la_api(cliente):
    c = cliente(_tablero())
    todo = c.get("/api/electrico/circuito").json()
    assert todo["resumen"]["n_dispositivos"] == 14 and len(todo["dispositivos"]) == 14
    q2 = c.get("/api/electrico/circuito", params={"designacion": "-Q2"}).json()
    assert [x["designacion"] for x in q2["dispositivos"]] == ["-Q2"]
    assert len(q2["conductores"]) == 6  # tres que entran del seccionador, tres al contactor
    assert {b["id"] for b in q2["dispositivos"][0]["bornes"]} >= {"1", "2", "3", "4", "5", "6"}
    falta = c.get("/api/electrico/circuito", params={"designacion": "-Q9"})
    assert falta.status_code == 404 and "¿Quisiste decir" in falta.json()["detail"]
    chequeo = c.get("/api/electrico/check").json()
    assert chequeo["estado"] == "aviso" and chequeo["n_dispositivos"] == 14  # -U1 sin pieza (F7b)
    assert [r["elementos"] for r in chequeo["reglas"] if r["estado"] != "ok"] == [["-U1"]]
    vacio = cliente(Document("vacío")).get("/api/electrico/check").json()
    assert vacio["estado"] == "sin_carril" and vacio["reglas"] == []


def test_el_catalogo_expone_la_ficha_electrica(cliente):
    c = cliente(Document())
    items = {i["ref"]: i for i in c.get("/api/catalog", params={"category": "proteccion_electrica"}).json()}
    gm = items["GM-2.5-4A"]["electrico"]
    assert gm["funcion"] == "Q" and {b["id"] for b in gm["bornes"]} >= {"1", "2", "5", "6"}
    assert gm["protege_motor"] is True and gm["modelo"]["Ir_A"] == [2.5, 4.0]
    perfiles = c.get("/api/catalog", params={"category": "perfiles"}).json()
    assert all("electrico" not in p for p in perfiles)
    ligero = c.get("/api/catalog", params={"category": "proteccion_electrica",
                                           "names_only": "true"}).json()
    assert all(set(i) == {"ref", "name", "category"} for i in ligero)
