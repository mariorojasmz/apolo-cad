"""La sesión en vivo de punta a punta (plan V8.4 F1, D1–D3): el worker en su proceso y
`WS /api/cosim/vivo` con el cliente de prueba de Starlette.

  - el worker en modo vivo (`ProcesoVivo`, sin dormir): tabla, fotogramas, ack y fin con la
    grabación; al cerrarlo no queda vivo;
  - la ruta: origen ajeno rechazado sin aceptar (4403), sin token (4401), token de otro documento
    (4409), escenario que no existe (4400); una sesión: inicio con la tabla de mandos y su color,
    fotogramas binarios, ack y rechazo, sesión vieja al cambiar el documento (D3), fin con la
    grabación y el escenario para el lote;
  - UNA sesión por API: la segunda recibe 4423; con `reemplazar=1` la primera termina
    «reemplazada»; cerrar el WebSocket mata al worker (sin huérfanos).
"""

from __future__ import annotations

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

pytest.importorskip("mujoco")

import apolo.api.main as api  # noqa: E402
from apolo.api.routers import cosim_vivo as R  # noqa: E402
from apolo.cosim.proceso_vivo import ProcesoVivo  # noqa: E402
from apolo.cosim.vivo import escenario_vivo  # noqa: E402
from apolo.cosim.vivo_fotograma import leer_fotograma  # noqa: E402
from apolo.services.cosim_snapshot import snapshot_cosim  # noqa: E402
from cosim_lazo_banco import FOTO, MECANICA, MOTOR, PROGRAMA, PROGRAMAS, escenario_variador, faja_variador  # noqa: E402

BASE = {"duracion_s": 3.0, "mecanica": MECANICA, "acoples": {"motores": MOTOR, "sensores": FOTO},
        "acciones": [{"t": 0.3, "accion": "pulsar", "dispositivo": "-S1", "actuador": "marcha", "durante_s": 0.2}],
        "eventos": [{"t": 0.0, "tipo": "producto", "nombre": "caja", "dims_mm": [150, 120, 100], "masa_kg": 2.0,
                     "cada_s": 1.0, "cantidad": 2, "posicion_mm": [-500, 0, 850.5]}]}


def test_el_worker_vivo_en_su_proceso():
    snap = snapshot_cosim(faja_variador(), escenario_vivo(escenario_variador(1.0, cajas=True)),
                          programas=PROGRAMAS)
    llegan: list = []
    hecho = threading.Event()

    def al_mensaje(etiqueta, cuerpo):
        llegan.append((etiqueta, cuerpo))
        if etiqueta is None:
            hecho.set()

    p = ProcesoVivo(snap, {"ritmo": 0, "max_s": 0.5}, al_mensaje)
    assert p.enviar({"girar": "-S1", "valor": 1.0, "id": 1})
    assert hecho.wait(120), p.cola_stderr()
    jsons = [json.loads(c) for e, c in llegan if e == b"J"]
    tipos = [m["tipo"] for m in jsons]
    assert tipos[0] == "tabla" and tipos[-1] == "fin" and "ack" in tipos
    fin = jsons[-1]
    assert fin["motivo"] == "tope" and abs(fin["t"] - 0.5) < 0.04
    assert [g["accion"] for g in fin["grabacion"]] == ["girar"]
    fotos = [leer_fotograma(c) for e, c in llegan if e == b"F"]
    assert len(fotos) >= 14 and fotos[-1]["t"] > fotos[0]["t"]  # ~1/30 s virtual por fotograma
    assert llegan[-1] == (None, 0) and not p.vivo
    p.cerrar()


@pytest.fixture(scope="module")
def maquina():
    doc = faja_variador()
    doc.execute("add_program", {"plc": "-K1", "fuente": PROGRAMA})
    return doc


@pytest.fixture
def c(maquina, monkeypatch):
    monkeypatch.setattr(api, "DOC", maquina)
    cli = TestClient(api.app)
    assert cli.put("/api/escenarios/base", json={"escenario": BASE}).status_code == 200
    return cli


def _token(c) -> str:
    return c.get("/api/health").json()["documento"]


def _hasta(ws, pred, limite=600):
    """Recibe hasta que `pred(msg)` (JSON) sea verdadero; devuelve (msg, n de fotogramas)."""
    fotos = 0
    for _ in range(limite):
        m = ws.receive()
        if m.get("bytes") is not None:
            fotos += 1
            continue
        if m["type"] == "websocket.close":
            raise AssertionError(f"se cerró: {m}")
        msg = json.loads(m["text"])
        if pred(msg):
            return msg, fotos
    raise AssertionError("no llegó")


def _url(c, **q) -> str:
    q = {"documento": _token(c), "escenario": "base", **q}
    return "/api/cosim/vivo?" + "&".join(f"{k}={v}" for k, v in q.items())


def test_un_origen_ajeno_no_se_acepta(c):
    with pytest.raises(WebSocketDisconnect) as exc:
        with c.websocket_connect(_url(c), headers={"origin": "https://otra-pagina.example"}):
            pass
    assert exc.value.code == 4403
    assert R.origen_permitido("http://localhost:5199", "127.0.0.1:8000")
    assert R.origen_permitido("http://127.0.0.1:8000", "127.0.0.1:8000")
    assert not R.origen_permitido("http://192.168.1.5:8000", "127.0.0.1:8000")


@pytest.mark.parametrize("q,codigo,clave", [
    ({"documento": ""}, 4401, "documento"),
    ({"documento": "otro"}, 4409, "documento"),
    ({"escenario": "no-hay"}, 4400, "escenario"),
])
def test_lo_que_no_abre_dice_por_que(c, q, codigo, clave):
    with c.websocket_connect(_url(c, **q)) as ws:
        msg = ws.receive_json()
        assert msg["tipo"] == "error" and msg["codigo"] == clave and msg["motivo"]
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == codigo


def test_una_sesion_de_punta_a_punta(c):
    with c.websocket_connect(_url(c, ritmo=0, max_s=1.5)) as ws:
        ini = ws.receive_json()
        assert ini["tipo"] == "inicio" and ini["escenario"] == "base" and ini["firma"]
        mandos = {m["designacion"]: m for m in ini["mandos"]}
        assert mandos["-S0"]["color"] == "rojo" and "presionar" in mandos["-S0"]["acciones"]
        assert {"-M1.rpm", "-K1.Main.cuenta"} <= set(ini["senales"])
        assert len(ini["productos"]) == 2 and ini["cuerpos"]
        ws.send_json({"girar": "-S1", "valor": 1.0, "id": 1})
        ws.send_json({"pulsar": "-S1", "actuador": "marcha", "durante_s": 0.2, "id": 2})
        ws.send_json({"pulsar": "-S7", "id": 3})
        ws.send_text("esto no es json")
        acks, rechazos, fotos = [], [], 0
        while len(acks) + len(rechazos) < 4:
            msg, n = _hasta(ws, lambda m: m["tipo"] in ("ack", "rechazo"))
            fotos += n
            (acks if msg["tipo"] == "ack" else rechazos).append(msg)
        assert [a["id"] for a in acks] == [1, 2]
        assert {r["id"] for r in rechazos} == {3, None}
        fin, n = _hasta(ws, lambda m: m["tipo"] == "fin")
        assert fin["motivo"] == "tope" and [g["accion"] for g in fin["grabacion"]] == ["girar", "pulsar"]
        assert fin["escenario"]["acciones"][1]["actuador"] == "marcha"
        assert fotos + n > 10
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 1000
    assert not R.SESIONES.ultima.proc.vivo


def test_la_sesion_vieja_avisa_y_sigue(c, maquina, monkeypatch):
    monkeypatch.setattr(R, "VIGILAR_FIRMA_S", 0.05)
    with c.websocket_connect(_url(c, ritmo=1, max_s=60)) as ws:
        assert ws.receive_json()["tipo"] == "inicio"
        maquina.execute("set_variable", {"name": "vivo_prueba", "expression": "2"})
        try:
            msg, _ = _hasta(ws, lambda m: m["tipo"] == "sesion_vieja")
            assert msg["vieja"] is True and "Reinicia la sesión" in msg["mensaje"]
        finally:
            maquina.undo()
        msg, _ = _hasta(ws, lambda m: m["tipo"] == "sesion_vieja")
        assert msg["vieja"] is False  # deshecho: vuelve a ser el modelo de la sesión
        ws.send_json({"control": "parar"})
        fin, _ = _hasta(ws, lambda m: m["tipo"] == "fin")
        assert fin["motivo"] == "parada"


def test_una_sesion_por_api_y_cerrar_mata_al_worker(c):
    with c.websocket_connect(_url(c, ritmo=1, max_s=60)) as primera:
        assert primera.receive_json()["tipo"] == "inicio"
        pid_primera = R.SESIONES.ultima
        with c.websocket_connect(_url(c)) as segunda:
            msg = segunda.receive_json()
            assert msg["codigo"] == "sesion_ocupada" and "reemplazar=1" in msg["motivo"]
            with pytest.raises(WebSocketDisconnect) as exc:
                segunda.receive_json()
            assert exc.value.code == 4423
        with c.websocket_connect(_url(c, ritmo=1, max_s=60, reemplazar=1)) as tercera:
            fin, _ = _hasta(primera, lambda m: m["tipo"] == "fin")
            assert fin["motivo"] == "reemplazada"
            assert tercera.receive_json()["tipo"] == "inicio"
            ultima = R.SESIONES.ultima
            assert ultima is not pid_primera and ultima.proc.vivo
        fin_espera = time.monotonic() + 10
        while ultima.proc.vivo and time.monotonic() < fin_espera:
            time.sleep(0.05)
        assert not ultima.proc.vivo  # cerrar el WebSocket terminó su worker
    assert not pid_primera.proc.vivo and R.SESIONES.actual is None
