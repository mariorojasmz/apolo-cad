"""visor-realista F2 — la marcha como serie de tiempo para el reproductor del visor (D4).

`GET /api/physics/dynamics/serie` da la ÚLTIMA marcha simulada del proyecto (la del agente con
`simulate`, que pasa por `POST /api/physics/dynamics`) y `POST …/serie` la de un escenario
explícito. La serie se cachea en memoria por firma del documento + escenario (nunca entra al
`.apolo`) y se vuelve a simular si el documento cambió. Misma faja sintética que
`test_api_dinamica.py`. Requiere MuJoCo.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("mujoco")

from fastapi.testclient import TestClient  # noqa: E402

import apolo.api.main as api  # noqa: E402
from apolo.api.session import S  # noqa: E402
from apolo.api.sims import HZ_SERIE, MARCHAS, clave_escenario  # noqa: E402
from apolo.doc.document import Document  # noqa: E402
from apolo.physics.dinamica_serie import MAX_VALORES_POSE, HZ_MIN, _quat_xyzw, hz_para  # noqa: E402

V = 0.25
DURACION = 0.6
PETICION = {
    "con_autodeteccion": True, "duracion_s": DURACION, "fps": 10,
    "motores": [{"junta": "c1_eje_motriz", "modo": "velocidad", "v_superficie_m_s": V,
                 "direccion_transporte": [1, 0, 0]}],
    "productos": [{"nombre": f"caja{k}", "dims_mm": [150, 120, 100], "masa_kg": 2.0,
                   "posicion_mm": [-300.0 + 300 * k, 0, 850.5]} for k in range(2)],
}


@pytest.fixture(scope="module")
def faja():
    doc = Document("faja-marcha")
    doc.execute("create_belt_conveyor", {"largo": 3000, "ancho_banda": 500, "altura": 800})
    return doc


@pytest.fixture
def cliente(monkeypatch, faja):
    MARCHAS.vaciar()
    monkeypatch.setattr(api, "DOC", faja)
    monkeypatch.setattr(S, "project_id", 74)
    autoguardados: list = []
    monkeypatch.setattr(api._autosave_sched, "schedule", lambda: autoguardados.append(1))
    yield TestClient(api.app)
    MARCHAS.vaciar()
    assert autoguardados == [], "la serie es de lectura: no programa un autoguardado"


def _rotar(q, v):
    """Aplica el cuaternión (x, y, z, w) al vector v."""
    x, y, z, w = q
    u = np.array([x, y, z])
    v = np.asarray(v, float)
    return v + 2 * np.cross(u, np.cross(u, v) + w * v)


def test_sin_simulacion_previa_da_404_con_que_hacer(cliente):
    r = cliente.get("/api/physics/dynamics/serie")
    assert r.status_code == 404
    assert "pídele al agente que la simule" in r.json()["detail"]


def test_la_ultima_marcha_del_agente_como_serie_a_50_hz(cliente, faja):
    n_cmd, n_undo = len(faja.commands), len(faja._undo)
    assert cliente.post("/api/physics/dynamics", json=PETICION).status_code == 200  # `simulate`
    r = cliente.get("/api/physics/dynamics/serie")
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["hz"] == HZ_SERIE and not s["en_cache"]
    n = len(s["t"])
    assert n == pytest.approx(DURACION * HZ_SERIE + 1, abs=1)       # 50 Hz, no los 10 del agente
    assert s["duracion_s"] == pytest.approx(DURACION, abs=0.01)
    assert all(b > a for a, b in zip(s["t"], s["t"][1:]))
    eje = s["cuerpos"]["b_c1_eje_motriz"]
    assert eje["junta"] == "c1_eje_motriz" and "c1_tambor_motriz" in eje["piezas"]
    assert len(eje["poses"]) == 7 * n
    assert eje["poses"][:7] == pytest.approx([0, 0, 0, 0, 0, 0, 1])  # relativa: nace en la identidad
    assert {p["name"] for p in s["productos"]} == {"p_caja0", "p_caja1"}
    for p in s["productos"]:
        assert p["desde"] == 0 and p["dims_mm"] == [150, 120, 100]
        assert len(p["poses"]) == 7 * n
        x0, xf = p["poses"][0], p["poses"][-7]
        assert (xf - x0) / 1000 == pytest.approx(V * DURACION, rel=0.2)   # avanzan hacia +X
    (banda,) = s["bandas"]
    assert len(banda["v_m_s"]) == n
    assert banda["v_m_s"][-1] * banda["direccion"][0] == pytest.approx(V, rel=0.02)
    assert len(s["juntas"]["c1_eje_motriz"]["q"]) == n and s["juntas"]["c1_eje_motriz"]["unidad"] == "grados"
    assert s["resumen"]["bandas"][0]["avanza_hacia"] == "+X"
    assert (len(faja.commands), len(faja._undo)) == (n_cmd, n_undo)


def test_el_tambor_gira_sobre_su_eje(cliente):
    """T(t) = P(t)·P(0)⁻¹ de un cuerpo de junta deja quieto el eje de la junta: el visor puede
    aplicarla sobre la malla de diseño de cada pieza del cuerpo."""
    s = cliente.post("/api/physics/dynamics/serie", json=PETICION).json()
    res = cliente.post("/api/physics/dynamics", json=PETICION).json()
    (cuerpo,) = [c for c in res["cuerpos"] if c["junta"] == "c1_eje_motriz"]
    o = np.asarray(cuerpo["origen_mm"])
    poses = s["cuerpos"]["b_c1_eje_motriz"]["poses"]
    ultima = poses[-7:]
    assert np.allclose(_rotar(ultima[3:], o) + ultima[:3], o, atol=0.2)
    q_final = s["juntas"]["c1_eje_motriz"]["q"][-1]
    angulo = 2 * math.degrees(math.acos(min(1.0, abs(ultima[6]))))
    assert angulo == pytest.approx(abs(q_final) % 360 if abs(q_final) % 360 <= 180
                                   else 360 - abs(q_final) % 360, abs=0.5)


def test_la_cache_es_por_firma_del_documento_y_escenario(cliente, faja):
    a = cliente.post("/api/physics/dynamics/serie", json=PETICION).json()
    b = cliente.get("/api/physics/dynamics/serie").json()   # el POST quedó como la última
    assert not a["en_cache"] and b["en_cache"]
    assert (a["firma"], a["escenario"], a["t"]) == (b["firma"], b["escenario"], b["t"])
    # el fps del agente no es parte del escenario: la serie lleva el suyo
    c = cliente.post("/api/physics/dynamics/serie", json={**PETICION, "fps": 30}).json()
    assert c["en_cache"] and c["escenario"] == a["escenario"]
    faja.execute("create_box", {"width": 50, "depth": 50, "height": 50,
                                "position": {"x": 0, "y": 3000, "z": 25}})
    try:
        d = cliente.get("/api/physics/dynamics/serie").json()
        assert not d["en_cache"] and d["firma"] != a["firma"]   # el documento cambió: se re-simula
    finally:
        faja.undo()
    e = cliente.get("/api/physics/dynamics/serie").json()
    assert e["en_cache"] and e["firma"] == a["firma"]


def test_la_ultima_marcha_es_de_cada_proyecto(cliente, monkeypatch):
    cliente.post("/api/physics/dynamics", json=PETICION)
    monkeypatch.setattr(S, "project_id", 75)
    assert cliente.get("/api/physics/dynamics/serie").status_code == 404
    monkeypatch.setattr(S, "project_id", 74)
    assert cliente.get("/api/physics/dynamics/serie").status_code == 200


def test_productos_en_serie_nacen_en_su_muestra(cliente):
    # 40 mm de largo: a 0,25 m/s la anterior despeja la entrada antes de los 0,3 s (si no, la
    # siguiente espera su lugar: V8.4, cola en vivo)
    pet = {**PETICION, "productos": [{"nombre": "caja", "dims_mm": [40, 120, 100], "masa_kg": 2.0,
                                      "posicion_mm": [-1000.0, 0, 850.5], "cada_s": 0.3}]}
    s = cliente.post("/api/physics/dynamics/serie", json=pet).json()
    desde = {p["name"]: p["desde"] for p in s["productos"]}
    assert desde["p_caja_0"] == 0
    assert s["t"][desde["p_caja_1"]] == pytest.approx(0.3, abs=0.03)
    p1 = next(p for p in s["productos"] if p["name"] == "p_caja_1")
    assert len(p1["poses"]) == 7 * (len(s["t"]) - p1["desde"])


def test_un_escenario_malo_da_400_y_no_queda_como_ultimo(cliente):
    r = cliente.post("/api/physics/dynamics/serie", json={"motor": []})
    assert r.status_code == 400 and "¿Quisiste decir 'motores'?" in r.json()["detail"]
    assert cliente.get("/api/physics/dynamics/serie").status_code == 404


def test_nada_que_simular_no_se_cachea(monkeypatch):
    MARCHAS.vaciar()
    monkeypatch.setattr(api, "DOC", Document("vacio"))
    s = TestClient(api.app).post("/api/physics/dynamics/serie", json={}).json()
    assert s["mensaje"].startswith("Nada que simular") and s["t"] == []
    assert MARCHAS.ultimo_escenario(S.project_id) is None


def test_clave_de_escenario_ignora_fps_y_el_orden():
    assert clave_escenario({"a": 1, "b": [1, 2], "fps": 10}) == clave_escenario({"b": [1, 2], "a": 1})
    assert clave_escenario({"a": 1}) != clave_escenario({"a": 2})


def test_cuaternion_de_una_rotacion_conocida():
    ang = math.radians(70)
    r = np.array([[math.cos(ang), -math.sin(ang), 0], [math.sin(ang), math.cos(ang), 0], [0, 0, 1]])
    assert _quat_xyzw(r) == pytest.approx((0, 0, math.sin(ang / 2), math.cos(ang / 2)))
    r180 = np.diag([1.0, -1.0, -1.0])     # 180° en X: la traza es −1 (rama sin w)
    assert _quat_xyzw(r180) == pytest.approx((1, 0, 0, 0), abs=1e-9)


def test_la_frecuencia_baja_si_la_serie_no_cabe():
    assert hz_para(3.0, 12, HZ_SERIE) == HZ_SERIE
    hz = hz_para(60.0, 200, HZ_SERIE)
    assert HZ_MIN <= hz < HZ_SERIE and 60 * 200 * 7 * hz <= MAX_VALORES_POSE
