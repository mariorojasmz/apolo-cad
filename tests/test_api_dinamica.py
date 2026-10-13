"""V8.2 F2 — la dinámica por la API: `POST /api/physics/dynamics` y su `.gif` (D10).

Faja sintética = `create_belt_conveyor` 3000×500×800 con la estructura sujeta por
autodetección (como la F1), el tambor motriz por velocidad hacia +X y 3 cajas sobre la banda.
La física la prueban `test_dinamica*.py`; aquí, el transporte: velocidades finales, recorte de
`frames`, el GIF, los 400 accionables y que nada muta el documento. Requiere MuJoCo.
"""

from __future__ import annotations

import io

import pytest

pytest.importorskip("mujoco")

from fastapi.testclient import TestClient  # noqa: E402

import apolo.api.main as api  # noqa: E402
from apolo.doc.document import Document  # noqa: E402
from apolo.physics.gif_dinamica import _duraciones, _fotogramas_gif  # noqa: E402

V = 0.25
CAJA = [150, 120, 100]
PETICION = {
    "con_autodeteccion": True, "duracion_s": 0.6, "fps": 10,
    "motores": [{"junta": "c1_eje_motriz", "modo": "velocidad", "v_superficie_m_s": V,
                 "direccion_transporte": [1, 0, 0]}],
    "productos": [{"nombre": f"caja{k}", "dims_mm": CAJA, "masa_kg": 2.0,
                   "posicion_mm": [-300.0 + 300 * k, 0, 850.5]} for k in range(3)],
}


@pytest.fixture(scope="module")
def faja():
    doc = Document("faja-api")
    doc.execute("create_belt_conveyor", {"largo": 3000, "ancho_banda": 500, "altura": 800})
    return doc


@pytest.fixture
def cliente(monkeypatch, faja):
    monkeypatch.setattr(api, "DOC", faja)
    autoguardados: list = []
    monkeypatch.setattr(api._autosave_sched, "schedule", lambda: autoguardados.append(1))
    yield TestClient(api.app)
    assert autoguardados == [], "la simulación es de lectura: no programa un autoguardado"


def test_faja_con_motor_por_velocidad_da_las_velocidades_finales(cliente, faja):
    n_cmd, n_undo = len(faja.commands), len(faja._undo)
    r = cliente.post("/api/physics/dynamics", json=PETICION)
    assert r.status_code == 200, r.text
    res = r.json()
    assert "frames" not in res  # como la gravedad: las poses sólo con include_frames
    resumen = res["resumen"]
    assert set(resumen["productos"]) == {"p_caja0", "p_caja1", "p_caja2"}
    for p in resumen["productos"].values():
        assert p["velocidad_final_mm_s"][0] == pytest.approx(V * 1000, rel=0.02)
        assert not p["cayo"]
    assert resumen["bandas"][0]["avanza_hacia"] == "+X"
    assert resumen["bandas"][0]["v_final_m_s"] == pytest.approx(V, rel=0.01)
    assert resumen["juntas"]["c1_eje_motriz"]["velocidad_final_rpm"] != 0
    assert res["motores"][0]["junta"] == "c1_eje_motriz"
    assert res["juntas"]["c1_eje_motriz"]["unidades"]["qd"] == "rpm"  # trazas en la API
    assert (len(faja.commands), len(faja._undo)) == (n_cmd, n_undo)


def test_include_frames_devuelve_las_poses_por_tiempo(cliente):
    res = cliente.post("/api/physics/dynamics", json={**PETICION, "include_frames": True}).json()
    assert len(res["frames"]) == pytest.approx(0.6 * 10 + 1, abs=1)  # fps por segundo simulado
    assert {"b_c1_eje_motriz", "p_caja0"} <= set(res["frames"][-1]["poses"])


def test_el_gif_de_la_marcha(cliente):
    from PIL import Image

    r = cliente.post("/api/physics/dynamics.gif", json={**PETICION, "size_px": 320})
    if r.status_code == 503 and "VTK" in r.text:
        pytest.skip(f"VTK off-screen no disponible: {r.text[:200]}")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "image/gif"
    assert r.content[:6] == b"GIF89a"
    gif = Image.open(io.BytesIO(r.content))
    assert gif.n_frames >= 2


def test_una_clave_desconocida_da_400_con_su_correccion(cliente):
    r = cliente.post("/api/physics/dynamics", json={"motor": PETICION["motores"]})
    assert r.status_code == 400
    assert "¿Quisiste decir 'motores'?" in r.json()["detail"]
    r = cliente.post("/api/physics/dynamics.gif", json={**PETICION, "duracion_s": 61})
    assert r.status_code == 400 and "duracion_s" in r.json()["detail"]
    r = cliente.post("/api/physics/dynamics.gif", json={**PETICION, "size_px": 10})
    assert r.status_code == 422  # opción del transporte: la valida pydantic


def test_nada_que_simular(monkeypatch):
    monkeypatch.setattr(api, "DOC", Document("vacio"))
    cliente = TestClient(api.app)
    res = cliente.post("/api/physics/dynamics", json={}).json()
    assert res["mensaje"].startswith("Nada que simular")
    r = cliente.post("/api/physics/dynamics.gif", json={})
    assert r.status_code == 400 and r.json()["detail"].startswith("Nada que simular")


def test_el_gif_submuestrea_y_corre_a_tiempo_real():
    frames = [{"t": round(k / 30, 4)} for k in range(121)]   # 4 s a 30 fps
    sel = _fotogramas_gif(frames, 90)
    assert len(sel) <= 91 and sel[0] is frames[0] and sel[-1] is frames[-1]
    assert _fotogramas_gif(frames[:5], 90) == frames[:5]
    ms = _duraciones(sel)
    assert len(ms) == len(sel) and all(m % 10 == 0 and m >= 20 for m in ms)  # centésimas del GIF
    assert sum(ms[:-1]) == pytest.approx(4000, abs=10)   # el redondeo no se acumula
