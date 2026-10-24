"""El panel «Tablero» del visor (plan V8.5 F3b: D13, D15): `services/tablero_panel.py`, la única
fuente del panel (`GET /api/tablero/{ubicacion}`) y de `get_circuit tablero=true`.

- La faja piloto (`tests/data/tablero_piloto.json`) armada: un veredicto, los ítems de lo que
  pide atención (los mismos hallazgos que el ERC, en palabras de la persona y agrupados), lo que
  está bien, la junta de la puerta y el detalle.
- El recorrido de cada conductor en el MUNDO: mide lo mismo que el ruteo (menos las reservas) y
  sigue al gabinete cuando se mueve o gira.
- La regla del veredicto es la de `ui/src/diseno/atencion.ts::veredictoDe`.
- El calentamiento sale SIN EVALUAR (F3 espera la norma), con las pérdidas declaradas.
"""

from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from apolo.doc.document import Document
from apolo.services.errors import ServiceError
from apolo.services.tablero_panel import FRASE_BIEN, _items, panel, paneles, tableros, veredicto

PILOTO = json.loads((Path(__file__).parent / "data" / "tablero_piloto.json").read_text(encoding="utf-8"))


def _acciones(**layout) -> list[dict]:
    acc = []
    for d in PILOTO["dispositivos"]:
        p = {"ref": d["ref"], "designacion": d["designacion"], "ubicacion": "+TAB1"}
        if "cantidad" in d:
            p["cantidad"] = d["cantidad"]
        acc.append({"type": "add_device", "params": p})
    acc += [{"type": "add_device", "params": d} for d in PILOTO["campo"]]
    acc += [{"type": "add_cable", "params": {k: v for k, v in c.items() if k != "id"}} for c in PILOTO["cables"]]
    acc += [{"type": "add_wire", "params": {k: v for k, v in c.items() if k != "id"}} for c in PILOTO["conductores"]]
    acc.append({"type": "layout_tablero", "params": {"ubicacion": "TAB1", **layout}})
    return acc


def _doc(**layout) -> Document:
    d = Document()
    d.execute_many(_acciones(**layout))
    return d


@pytest.fixture(scope="module")
def piloto() -> Document:
    return _doc()


@pytest.fixture(scope="module")
def girado() -> Document:
    return _doc(position={"x": 1000, "y": -300, "z": 800}, rotation={"x": 0, "y": 0, "z": 90})


def _largo(polilinea) -> float:
    return sum(math.dist(a, b) for a, b in zip(polilinea, polilinea[1:]))


def test_el_panel_de_la_piloto(piloto):
    p = panel(piloto, "+TAB1")
    assert p["armado"] and p["ubicacion"] == "+TAB1"
    assert p["veredicto"]["severidad"] == "aviso"
    assert p["veredicto"]["frase"] == "2 cosas por revisar"
    assert p["veredicto"]["nota"] == "Gabinete de 500 × 400 mm · 12 aparatos · 33 conductores"
    assert [it["clave"] for it in p["items"]] == ["largos", "sin-cable", "calentamiento"]
    largos, sueltos, calor = p["items"]
    # los mismos hallazgos que el ERC (F2): 10 largos a mano y los 4 hilos sueltos de la red
    assert largos["valor"] == 10 and largos["unidad"] == "conductores" and len(largos["conductores"]) == 10
    assert sueltos["valor"] == 4 and len(sueltos["conductores"]) == 4
    assert all(f.startswith(p["comando"] + "_") for f in largos["piezas"] + sueltos["piezas"])
    assert calor["severidad"] == "sin_evaluar" and "valor" not in calor  # nunca un número inventado
    assert p["puerta"] == {"junta": f"{p['comando']}_puerta", "pieza": f"{p['comando']}_puerta",
                           "min_deg": 0.0, "max_deg": 110.0, "bisagra": "izquierda"}
    bien = {it["clave"]: it for it in p["detalle"]["bien"]}
    assert bien["puerta"]["valor"] == 110.0 and "111 ángulos" in bien["puerta"]["detalle"]
    assert bien["canaletas"]["valor"] == 13  # F2: la piloto llega a 13,5 %
    assert bien["largo"]["valor"] == pytest.approx(28.3, abs=0.05)  # F2: 28,3 m dentro del tablero
    det = p["detalle"]
    assert len(det["aparatos"]) == 12 and len(det["conductores"]) == 33
    assert len(det["canaletas"]) == 8 and all(c["pieza"] for c in det["canaletas"])
    assert {c["nombre"] for c in det["canaletas"]} >= {"Canaleta de arriba", "Canaleta de abajo",
                                                       "Canaleta de la izquierda", "Canaleta de la derecha"}
    assert det["calentamiento"]["estado"] == "sin_evaluar"
    assert det["calentamiento"]["perdidas_W"] > 90  # el variador solo pierde 90 W (F0 § 5)
    assert "-S1" in det["calentamiento"]["sin_dato"]
    for it in p["items"] + det["bien"]:  # todas las piezas que se señalan existen
        assert all(f in piloto.scene for f in it["piezas"]), it


def test_cada_pieza_y_conductor_existen(piloto):
    p = panel(piloto, "TAB1")
    for a in p["detalle"]["aparatos"]:
        assert a["pieza"] in piloto.scene
    ids = {c["id"] for c in p["detalle"]["conductores"]}
    for it in p["items"]:
        assert set(it["conductores"]) <= ids


def test_el_recorrido_mide_lo_que_el_ruteo(piloto):
    p = panel(piloto, "+TAB1")
    c = next(c for c in p["detalle"]["conductores"] if c["puntos"] == ["-F1:2", "-T2:L1"])
    (tramo,) = c["recorrido"]
    assert _largo(tramo) + 100.0 == pytest.approx(c["ruteado_m"] * 1000, abs=0.5)  # + reservas
    assert c["origen"] == "declarado" and c["declarado_m"] == 0.5  # el declarado manda en la compra
    for i in range(len(tramo) - 1):
        assert tramo[i] != tramo[i + 1]  # sin puntos repetidos seguidos


def test_el_recorrido_sigue_al_gabinete(piloto, girado):
    a = panel(piloto, "+TAB1")["detalle"]["conductores"]
    b = panel(girado, "+TAB1")["detalle"]["conductores"]
    for ca, cb in zip(a, b):
        for ta, tb in zip(ca["recorrido"], cb["recorrido"]):
            for (x, y, z), q in zip(ta, tb):
                # Rz(90°): (x, y) → (−y, x), más la posición del gabinete
                assert q == pytest.approx([1000 - y, -300 + x, 800 + z], abs=0.15)


def test_get_circuit_tablero_lee_lo_mismo_sin_recorridos(piloto):
    from apolo.services.electrico import circuito

    (t,) = paneles(piloto)
    assert t["veredicto"] == panel(piloto, "+TAB1")["veredicto"]
    assert all("recorrido" not in c for c in t["detalle"]["conductores"])
    assert "tableros" not in circuito(piloto)


def test_canaleta_llena_y_que_no_entra(piloto):
    from apolo.services.tablero import dibujados, ruteos

    (t,) = ruteos(piloto)
    llena = replace(t, ruteo=replace(t.ruteo, criterio={**t.ruteo.criterio, "llenado_tope": 0.125}))
    atender, bien = _items(piloto, llena, dibujados(piloto))
    canal = [it for it in atender if it["clave"].startswith("canaleta-")]
    assert canal and all(it["severidad"] == "aviso" and it["unidad"] == "%" for it in canal)
    assert any(it["frase"] == "La canaleta horizontal 2 desde arriba va muy llena" for it in canal)
    assert all(it["piezas"] and it["conductores"] for it in canal)
    assert "canaletas" not in {it["clave"] for it in bien}
    chica = replace(t.ruteo.llenados[0], util_mm2=10.0)
    no_entra = replace(t, ruteo=replace(t.ruteo, llenados=(chica, *t.ruteo.llenados[1:])))
    falla = next(it for it in _items(piloto, no_entra, {})[0] if it["severidad"] == "falla")
    assert falla["frase"].startswith("Los conductores no entran en la canaleta") and falla["valor"] > 100


def test_la_regla_del_veredicto_es_la_de_la_ui():
    def it(*sev):
        return [{"severidad": s} for s in sev]
    assert veredicto([]) == {"severidad": "bien", "frase": FRASE_BIEN}
    assert veredicto(it("bien")) == {"severidad": "bien", "frase": FRASE_BIEN}
    assert veredicto(it("aviso", "falla", "aviso")) == {"severidad": "falla", "frase": "1 cosa por corregir y 2 por revisar"}
    assert veredicto(it("falla", "falla")) == {"severidad": "falla", "frase": "2 cosas por corregir"}
    assert veredicto(it("sin_evaluar", "aviso")) == {"severidad": "aviso", "frase": "1 cosa por revisar"}
    assert veredicto(it("sin_evaluar")) == {"severidad": "sin_evaluar", "frase": "1 cosa sin evaluar"}


def test_un_layout_suprimido_se_ve_sin_armar():
    doc = SimpleNamespace(commands=[{"id": "c9", "type": "layout_tablero", "params": {"ubicacion": "TAB2"}}],
                          scene={}, joints={},
                          regen_suppressed=[{"command_id": "c9", "type": "layout_tablero", "error": "no entra"}])
    assert tableros(doc) == [{"ubicacion": "+TAB2", "comando": "c9", "armado": False}]
    p = panel(doc, "TAB2")
    assert p["armado"] is False and p["veredicto"] == {"severidad": "falla", "frase": "1 cosa por corregir"}
    assert p["items"][0]["detalle"] == "no entra"


def test_sin_tablero_404_con_las_validas(piloto):
    with pytest.raises(ServiceError) as e:
        panel(piloto, "+TAB9")
    assert e.value.status_code == 404 and "+TAB1" in e.value.detail
    with pytest.raises(ServiceError) as e:
        panel(Document(), "+TAB1")
    assert "pídele al agente que lo arme" in e.value.detail


def test_las_rutas(piloto, monkeypatch):
    from apolo.api import main as api

    c = TestClient(api.app)
    api.DOC = Document()
    assert c.get("/api/tablero").json() == {"tableros": []}
    assert c.get("/api/tablero/TAB1").status_code == 404
    api.DOC = piloto
    (fila,) = c.get("/api/tablero").json()["tableros"]
    assert fila["ubicacion"] == "+TAB1" and fila["armado"]
    for u in ("TAB1", "%2BTAB1"):
        r = c.get(f"/api/tablero/{u}")
        assert r.status_code == 200 and r.json()["ubicacion"] == "+TAB1"
        assert r.json()["detalle"]["conductores"][0]["recorrido"]
    t = c.get("/api/electrico/circuito", params={"tablero": "true"}).json()["tableros"]
    assert t[0]["ubicacion"] == "+TAB1"
    assert "tableros" not in c.get("/api/electrico/circuito").json()
