"""La sesión en vivo de punta a punta (plan V8.4 F1, D1–D3): el worker en su proceso y
`WS /api/cosim/vivo` con el cliente de prueba de Starlette.

  - el worker en modo vivo (`ProcesoVivo`, sin dormir): tabla, fotogramas, ack y fin con la
    grabación; al cerrarlo no queda vivo;
  - la ruta: origen ajeno rechazado sin aceptar (4403), sin token (4401), token de otro documento
    (4409), escenario que no existe (4400); una sesión: inicio con la tabla de mandos y su color,
    fotogramas binarios, ack y rechazo, sesión vieja al cambiar el documento (D3), fin con la
    grabación y el escenario para el lote;
  - UNA sesión por API: la segunda recibe 4423; con `reemplazar=1` la primera termina
    «reemplazada»; cerrar el WebSocket mata al worker (sin huérfanos);
  - con un PLC de AFUERA (plan plc-en-el-lazo F1b2, D6, D8, D9; el PLC falso de
    `lazo_externo.py` en otro proceso): un intercambio por vez a ritmo de pared y un fotograma
    cada 1/30 s; otro ritmo o un pedido malo son 4400 antes del worker; un PLC que no contesta
    no arranca la sesión (4502); matarlo pausa con motivo «lazo», reanudar sin él vuelve a pausar
    y con él de vuelta sigue; la pausa manual se la avisa al conector y el `fin` dice que el PLC
    de afuera siguió corriendo. Ningún proceso queda vivo.
"""

from __future__ import annotations

import json
import threading
import time
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from lazo_externo import entorno, pedido, plc_falso
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


# ── con un PLC de afuera (plc-en-el-lazo F1b2) ──────────────────────────────────────────────

@pytest.fixture
def cx(c, extensiones_aisladas, monkeypatch):
    """`c` con la extensión falsa cargada (su conector `prueba.tcp`) y el worker importando
    `ext_prueba` (la clase del conector viaja por pickle)."""
    monkeypatch.setenv("APOLO_EXTENSIONES_EXTRA", "ext_prueba:EXTENSION")
    assert extensiones_aisladas.cargar()[0]["cargada"]
    monkeypatch.setenv("PYTHONPATH", entorno()["PYTHONPATH"])
    return c


def _ext(puerto: int) -> str:
    return quote(json.dumps(pedido(puerto)))


def _fotogramas(ws, n: int) -> list[float]:
    """Las horas virtuales de los próximos n fotogramas (los JSON intermedios se saltan)."""
    ts = []
    while len(ts) < n:
        m = ws.receive()
        assert m["type"] != "websocket.close", m
        if m.get("bytes") is not None:
            ts.append(leer_fotograma(m["bytes"])["t"])
    return ts


def _sin_worker(ses) -> None:
    hasta = time.monotonic() + 10
    while ses.proc.vivo and time.monotonic() < hasta:
        time.sleep(0.05)
    assert not ses.proc.vivo


def test_con_plc_externo_un_intercambio_por_vez_y_un_fotograma_cada_1_30_s(cx, tmp_path):
    with plc_falso(tmp_path) as (_proc, puerto):
        with cx.websocket_connect(_url(cx, max_s=1.0, plc_externo=_ext(puerto))) as ws:
            ini = ws.receive_json()
            assert ini["tipo"] == "inicio" and ini["determinista"] is False and ini["ritmo"] == 1.0
            assert ini["plc_externo"] == {"-K1": {"conector": "prueba.tcp", "extension": "ext-prueba",
                                                  "version": "0.1.0"}}
            ws.send_json({"girar": "-S1", "valor": 1.0, "id": 1})
            ws.send_json({"pulsar": "-S1", "actuador": "marcha", "durante_s": 0.2, "id": 2})
            fotos, acks = [], []
            while True:
                m = ws.receive()
                if m.get("bytes") is not None:
                    fotos.append(leer_fotograma(m["bytes"]))
                    continue
                msg = json.loads(m["text"])
                acks += [msg["id"]] if msg["tipo"] == "ack" else []
                if msg["tipo"] == "fin":
                    break
        ses = R.SESIONES.ultima
    ts = [f["t"] for f in fotos]
    assert acks == [1, 2] and msg["motivo"] == "tope" and msg["determinista"] is False
    assert "aviso_externo" not in msg  # sin pausa
    lazo = msg["lazo"]
    # D9: cada intercambio esperó su hora de pared, uno por vez
    assert lazo["intercambios"] == msg["intercambios"] == 500
    assert lazo["ida_y_vuelta"]["-K1"]["n"] > 100  # el núcleo midió el paso() del PLC de afuera
    # A ritmo de pared, no de golpe: lo mide el WORKER (virtual/pared de su último ~1 s, en el
    # fotograma). La pared de LLEGADA al test no sirve: con la suite en paralelo los fotogramas se
    # encolan y el primero llega tarde (medido: 0,66–0,82 s de llegadas para 0,97 s virtuales).
    # Hasta ×1,25 es ponerse al día tras una deuda (< 100 ms, `ritmo.REBASE_S`); de golpe, ×N.
    # Más lento que la pared depende de la carga de la máquina: no se afirma.
    assert fotos[-1]["factor"] <= 1.25, [round(f["factor"], 2) for f in fotos]
    # un fotograma cada 1/30 s virtual (17 o 16 intercambios de 2 ms)
    assert 28 <= len(ts) <= 31
    assert all(abs((b - a) - 1 / 30) <= 0.0021 for a, b in zip(ts, ts[1:], strict=False))
    _sin_worker(ses)


@pytest.mark.parametrize("q,texto", [
    ({"ritmo": 2}, "al ritmo de la pared"),
    ({"ritmo": 0}, "quita ?ritmo o pon ritmo=1"),
    ({"plc_externo": "{no-json"}, "no es JSON"),
    ({"plc_externo": quote(json.dumps({"-K1": {"conector": "prueba.tcp", "config": {"x": "y" * 1100}}}))},
     "pasa de 1024 bytes"),
])
def test_con_plc_externo_otro_ritmo_o_un_pedido_malo_es_4400(cx, monkeypatch, q, texto):
    import apolo.cosim.proceso_vivo as pv

    monkeypatch.setattr(pv, "ProcesoVivo", lambda *a, **k: pytest.fail("llegó al worker"))
    q = {"plc_externo": _ext(5), **q}
    with cx.websocket_connect(_url(cx, **q)) as ws:
        msg = ws.receive_json()
        assert msg["tipo"] == "error" and msg["codigo"] == "plc_externo" and texto in msg["motivo"], msg
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 4400


def test_con_plc_externo_lo_que_valida_el_snapshot_es_4400(cx, monkeypatch):
    import apolo.cosim.proceso_vivo as pv

    monkeypatch.setattr(pv, "ProcesoVivo", lambda *a, **k: pytest.fail("llegó al worker"))
    malo = quote(json.dumps({"-K1": {"conector": "prueba.otro", "config": {}}}))
    with cx.websocket_connect(_url(cx, plc_externo=malo)) as ws:
        msg = ws.receive_json()
        assert "plc_externo.-K1: el conector «prueba.otro» no está cargado; conectores: prueba.tcp" in msg["motivo"]
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 4400


def test_un_plc_externo_que_no_contesta_no_arranca_la_sesion(cx):
    ext = quote(json.dumps({"-K1": {"conector": "prueba.tcp", "config": {"host": "127.0.0.1", "puerto": 9,
                                                                          "timeout_s": 1.0}}}))
    with cx.websocket_connect(_url(cx, plc_externo=ext)) as ws:
        msg = ws.receive_json()
        assert msg["tipo"] == "error" and msg["codigo"] == "lazo", msg
        assert "no se pudo conectar el PLC externo -K1: 127.0.0.1:9 no contesta" in msg["motivo"]
        fin = ws.receive_json()
        assert fin["tipo"] == "fin" and fin["motivo"] == "lazo"
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 4502
    _sin_worker(R.SESIONES.ultima)


def test_matar_el_plc_externo_pausa_y_con_el_plc_de_vuelta_sigue(cx, tmp_path):
    def control(ws):
        return _hasta(ws, lambda m: m["tipo"] in ("pausa", "reanudar", "fin"))[0]

    with plc_falso(tmp_path) as (primero, puerto):
        with cx.websocket_connect(_url(cx, max_s=60, plc_externo=_ext(puerto))) as ws:
            assert ws.receive_json()["tipo"] == "inicio"
            _fotogramas(ws, 5)
            primero.kill()  # D8: el lazo se corta
            p = control(ws)
            assert p["motivo"] == "lazo" and p["mensaje"].startswith("lazo cortado en t = "), p
            t_corte = p["t"]
            ws.send_json({"control": "reanudar", "id": "r1"})  # sin PLC: reconectar falla, sigue en pausa
            p = control(ws)
            assert p["tipo"] == "pausa" and p["motivo"] == "lazo" and p["id"] == "r1", p
            assert "no contesta" in p["mensaje"] and p["t"] == t_corte  # no avanzó con salidas viejas
            with plc_falso(tmp_path, puerto=puerto) as (segundo, _):  # el PLC vuelve al mismo puerto
                ws.send_json({"control": "reanudar", "id": "r2"})
                assert control(ws) == {"tipo": "reanudar", "id": "r2", "t": t_corte}
                assert min(_fotogramas(ws, 5)) > t_corte  # sigue desde donde se cortó
                ws.send_json({"control": "pausa", "id": "p"})  # la manual se la avisa al conector
                p = control(ws)
                assert p["tipo"] == "pausa" and "motivo" not in p
                ws.send_json({"control": "reanudar"})
                assert control(ws)["tipo"] == "reanudar"
                ws.send_json({"control": "parar"})
                fin, _ = _hasta(ws, lambda m: m["tipo"] == "fin")
                segundo.kill()
                segundo.wait(timeout=30)
                salida = segundo.stdout.read()
        ses = R.SESIONES.ultima
    assert "OP pausar" in salida and "OP reanudar" in salida
    assert fin["motivo"] == "parada" and fin["determinista"] is False
    assert "siguió corriendo" in fin["aviso_externo"]
    assert fin["t"] > t_corte and fin["lazo"]["ida_y_vuelta"]["-K1"]["n"] > 0
    _sin_worker(ses)
    assert primero.poll() is not None and segundo.poll() is not None
