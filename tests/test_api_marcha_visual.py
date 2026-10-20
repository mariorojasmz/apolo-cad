"""visor-realista F3 (D6) — la serie de la marcha trae la faja con su forma real y las cadenas
que avanzan (`GET|POST /api/physics/dynamics/serie`). Lo puro está en `test_marcha_visual.py`;
aquí, que la API lo arma en la misma adquisición del documento que la física y que sale de la
física: la tracción del motor, la junta del piñón y el sentido de la banda. Requiere MuJoCo."""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")

from fastapi.testclient import TestClient  # noqa: E402

import apolo.api.main as api  # noqa: E402
from apolo.api.session import S  # noqa: E402
from apolo.api.sims import MARCHAS  # noqa: E402
from apolo.doc.document import Document  # noqa: E402
from apolo.library.marcha_visual import recorrido_mm  # noqa: E402


@pytest.fixture
def cliente(monkeypatch):
    MARCHAS.vaciar()
    monkeypatch.setattr(S, "project_id", 74)
    monkeypatch.setattr(api._autosave_sched, "schedule", lambda: None)
    yield TestClient(api.app)
    MARCHAS.vaciar()


def test_la_faja_del_super_comando_sale_con_su_ruta_y_su_cola_girando(cliente, monkeypatch):
    doc = Document("faja-f3")
    doc.execute("create_belt_conveyor", {"largo": 3000, "ancho_banda": 500, "altura": 800})
    monkeypatch.setattr(api, "DOC", doc)
    pet = {"con_autodeteccion": True, "duracion_s": 0.6,
           "motores": [{"junta": "c1_eje_motriz", "modo": "velocidad", "v_superficie_m_s": 0.25,
                        "direccion_transporte": [1, 0, 0]}]}
    s = cliente.post("/api/physics/dynamics/serie", json=pet).json()
    (f,) = s["fajas"]
    assert f["pieza"] == "c1_banda" and f["junta"] == "c1_eje_motriz"
    assert sorted(f["envueltos"]) == ["c1_tambor_cola", "c1_tambor_motriz"]
    assert [r["pieza"] for r in f["rodillos"]] == ["c1_tambor_cola"]   # la motriz la gira la física
    assert len(f["ruta"]) >= 2 * 40 and f["largo_mm"] > 6000
    assert f["tension"]["traccion_n"] and f["tension"]["traccion_n"] > 0
    assert f["tramos"] and all(t["comba_mm"] >= 0 for t in f["tramos"])
    # la cara de arriba avanza hacia +X: el recorrido antihorario de la ruta baja
    (b,) = s["bandas"]
    avance = f["signo"] * recorrido_mm(s["t"], b["v_m_s"])[-1]
    u = f["marco"]["u"]
    assert avance * u[0] < 0 and abs(avance) == pytest.approx(0.25 * 0.6 * 1000, rel=0.25)
    assert s["cadenas"] == []
    # va en la caché como el resto de la serie
    assert cliente.get("/api/physics/dynamics/serie").json()["fajas"] == s["fajas"]


def test_la_cadena_avanza_con_la_junta_de_su_pinon(cliente, monkeypatch):
    doc = Document("cadena-f3")
    base = doc.execute("create_box", {"width": 600, "depth": 60, "height": 20,
                                      "position": {"x": 200, "y": 0, "z": -100}})
    doc.execute("ground", {"name": "piso", "feature": base})
    a = doc.execute("insert_component", {"component": "PINON-ASA40-1-Z15"})
    b = doc.execute("insert_component", {"component": "PINON-ASA40-1-Z30", "position": {"x": 400}})
    cid = doc.execute("create_chain", {"pinon_a": a, "pinon_b": b})
    eje = doc.scene[a].anchors["eje"]
    o = dict(zip("xyz", eje["origin"]))
    doc.execute("add_joint", {"name": "jA", "type": "continua", "parent": base, "child": a,
                              "origin": o, "axis": dict(zip("xyz", eje["axis"]))})
    monkeypatch.setattr(api, "DOC", doc)
    pet = {"duracion_s": 0.4, "motores": [{"junta": "jA", "modo": "velocidad", "valor": 60}]}
    r = cliente.post("/api/physics/dynamics/serie", json=pet)
    assert r.status_code == 200, r.text
    s = r.json()
    (c,) = s["cadenas"]
    assert (c["pieza"], c["junta"], c["lado"], c["z"], c["signo"]) == (cid, "jA", "a", 15, 1)
    assert len(c["puntos"]) == 2 * int(round(doc.scene[cid].cut_length / c["paso"]))
    q = s["juntas"]["jA"]["q"]
    assert q[-1] - q[0] > 0                         # gira: la cadena avanza en su orden
    assert s["fajas"] == []
