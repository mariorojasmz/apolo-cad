"""El bus de la sesión viva, en proceso (plan plc-en-el-lazo D11, F1c2; `api/vivo_bus.py`).

  - sin worker (una sesión falsa): el nombre y su prefijo; el orden de lo que llega; una
    suscripción que no lee descarta sus fotogramas más VIEJOS y los cuenta, y el JSON de más,
    nunca `inicio`, `senales` ni `fin`; `enviar_vivo` sin sesión es False; un control, un
    mensaje de más de 4096 bytes, uno que no es objeto o no es JSON se rechazan a la suscripción
    sin llegar a la sesión; el id lleva el prefijo y su ack vuelve SÓLO a esa suscripción; nada
    toma `STATE_LOCK` (parchado para fallar) ni lo importa;
  - con el worker y `WS /api/cosim/vivo` (el suscriptor de `tests/ext_prueba/suscriptor.py`):
    recibe lo mismo que el WebSocket y en su orden; uno que nunca lee descarta y cuenta mientras
    el WebSocket recibe todo; `enviar_vivo` aplica la acción con `STATE_LOCK` tomado por otro
    hilo, su ack no llega al WebSocket y la acción queda en la grabación como cualquier otra;
    con la sesión cerrada, False.
"""

from __future__ import annotations

import ast
import json
import threading
from pathlib import Path

import pytest

import apolo.api.common as common
import apolo.state
from apolo.api import vivo_bus as B
from apolo.api.vivo_bus import Bus, validar_texto

RAIZ = Path(__file__).resolve().parents[1]


class SesionFalsa:
    def __init__(self, acepta: bool = True):
        self.enviados: list[dict] = []
        self.acepta = acepta

    def enviar(self, msg: dict) -> bool:
        self.enviados.append(msg)
        return self.acepta


def _json(bus: Bus, msg: dict) -> bool:
    return bus.difundir_json(msg, json.dumps(msg, ensure_ascii=False, separators=(",", ":")))


def _todo(sub) -> list:
    out = []
    while (m := sub.recibir(timeout=0)) is not None:
        out.append(m)
    return out


def test_el_nombre_lleva_prefijo_y_es_uno_solo():
    bus = Bus()
    for malo in ("scada", "prueba.sca:da", "Prueba.scada", "", None, "prueba."):
        with pytest.raises(ValueError, match="prefijo"):
            bus.suscribir(malo)
    with pytest.raises(ValueError, match="entero"):
        bus.suscribir("prueba.scada", max_fotogramas=-1)
    sub = bus.suscribir("prueba.scada")
    with pytest.raises(ValueError, match="ya hay una suscripción"):
        bus.suscribir("prueba.scada")
    sub.cerrar()
    sub.cerrar()  # idempotente
    assert sub.recibir(timeout=0) is None
    with bus.suscribir("prueba.scada") as otra:  # cerrar libera el nombre
        assert not otra.cerrada
    assert otra.cerrada


def test_llega_en_orden_y_el_que_no_lee_descarta_los_fotogramas_viejos():
    bus = Bus()
    rapida, lenta = bus.suscribir("prueba.rapida", 100), bus.suscribir("prueba.lenta", 3)
    assert not _json(bus, {"tipo": "inicio", "senales": ["a"]})
    for i in range(10):
        bus.difundir_fotograma(bytes([i]))
        if i == 4:
            assert not _json(bus, {"tipo": "textos", "t": 0.1, "valores": {"x": "RUN"}})
    assert not _json(bus, {"tipo": "fin", "motivo": "tope"})
    tipos = [m if isinstance(m, bytes) else m["tipo"] for m in _todo(rapida)]
    assert tipos == ["inicio", *[bytes([i]) for i in range(5)], "textos",
                     *[bytes([i]) for i in range(5, 10)], "fin"]
    assert rapida.descartados == 0
    # la lenta guarda los 3 fotogramas más NUEVOS y todo el JSON, en su orden
    assert [m if isinstance(m, bytes) else m["tipo"] for m in _todo(lenta)] == [
        "inicio", "textos", bytes([7]), bytes([8]), bytes([9]), "fin"]
    assert lenta.descartados == 7 and lenta.pendientes == 0


def test_el_json_de_mas_se_descarta_salvo_lo_que_hace_falta_para_leer(monkeypatch):
    monkeypatch.setattr(B, "MAX_JSON", 2)
    bus = Bus()
    sub = bus.suscribir("prueba.lenta", max_fotogramas=0)
    _json(bus, {"tipo": "inicio"})
    bus.difundir_fotograma(b"\x00")      # max_fotogramas = 0: sólo JSON
    for i in range(3):
        _json(bus, {"tipo": "textos", "n": i})
    _json(bus, {"tipo": "senales", "desde": 1, "nombres": ["b"]})
    _json(bus, {"tipo": "fin", "motivo": "parada"})
    assert [m["tipo"] for m in _todo(sub)] == ["inicio", "textos", "senales", "fin"]
    assert sub.json_descartados == 2 and sub.descartados == 1


def test_validar_texto_es_la_del_websocket():
    assert validar_texto('{"pulsar": "-S1"}') == ({"pulsar": "-S1"}, None)
    assert validar_texto("x" * 4097)[1] == "mensaje de más de 4096 bytes"
    assert validar_texto("no")[1] == "el mensaje no es JSON"
    assert validar_texto("[1]")[1].startswith("se espera un objeto")
    from apolo.api.routers import cosim_vivo as R

    assert R.MAX_MENSAJE == B.MAX_MENSAJE == 4096


def test_enviar_sin_sesion_es_false_y_lo_que_no_pasa_se_rechaza_a_la_suscripcion():
    bus = Bus()
    sub = bus.suscribir("prueba.scada")
    assert bus.enviar("prueba.scada", {"pulsar": "-S1"}) is False   # sin sesión
    assert _todo(sub) == []
    ses = SesionFalsa()
    bus.abrir(ses)
    malos = [({"control": "pausa", "id": 1}, "controles"),
             ({"control": "parar"}, "controles"),
             ({"pulsar": "-S1", "nota": "x" * 4100}, "más de 4096 bytes"),
             ("[1, 2]", "se espera un objeto"),
             ("{roto", "no es JSON"),
             ({"valor": float("nan")}, "no es JSON"),
             ({"valor": object()}, "no es JSON")]
    for msg, motivo in malos:
        assert bus.enviar("prueba.scada", msg) is False
        (r,) = _todo(sub)
        assert r["tipo"] == "rechazo" and motivo in r["motivo"], (msg, r)
    assert ses.enviados == []   # nada llegó a la sesión
    with pytest.raises(ValueError):
        bus.enviar("sin-prefijo", {"pulsar": "-S1"})


def test_el_ack_vuelve_solo_a_su_suscripcion():
    bus = Bus()
    scada, hmi = bus.suscribir("prueba.scada"), bus.suscribir("prueba.hmi")
    ses = SesionFalsa()
    bus.abrir(ses)
    assert bus.enviar("prueba.scada", {"pulsar": "-S1", "id": 7})
    assert bus.enviar("prueba.scada", '{"soltar": "-S1"}')   # texto y sin id: uno correlativo
    assert [m["id"] for m in ses.enviados] == ["prueba.scada:7", "prueba.scada:1"]
    assert ses.enviados[0]["pulsar"] == "-S1"
    # la respuesta a la acción del bus: privada (la persona no la ve: True)
    assert _json(bus, {"tipo": "ack", "id": "prueba.scada:7", "t": 0.002, "accion": {}})
    assert _json(bus, {"tipo": "rechazo", "id": "prueba.scada:1", "motivo": "no"})
    # la de la persona (o un id que el bus no mandó): a todos
    assert not _json(bus, {"tipo": "ack", "id": 3, "t": 0.004, "accion": {}})
    assert not _json(bus, {"tipo": "ack", "id": "prueba.scada:7", "t": 0.006, "accion": {}})
    assert [(m["tipo"], m["id"]) for m in _todo(scada)] == [
        ("ack", "prueba.scada:7"), ("rechazo", "prueba.scada:1"), ("ack", 3), ("ack", "prueba.scada:7")]
    assert [m["id"] for m in _todo(hmi)] == [3, "prueba.scada:7"]
    # el worker que ya no escucha: False y el id no queda esperando
    bus.abrir(SesionFalsa(acepta=False))
    assert bus.enviar("prueba.scada", {"pulsar": "-S1", "id": 8}) is False
    assert not _json(bus, {"tipo": "ack", "id": "prueba.scada:8", "t": 0.0, "accion": {}})
    bus.abrir(ses)
    bus.cerrar(SesionFalsa())   # no es la abierta: no la cierra
    assert bus.enviar("prueba.scada", {"pulsar": "-S1"}) is True
    bus.cerrar(ses)
    assert bus.enviar("prueba.scada", {"pulsar": "-S1"}) is False


class _LockQueFalla:
    def __enter__(self):
        raise AssertionError("el bus tomó STATE_LOCK")

    acquire = __enter__

    def __exit__(self, *_):
        return False


def test_el_bus_nunca_toma_state_lock(monkeypatch):
    monkeypatch.setattr(apolo.state, "STATE_LOCK", _LockQueFalla())
    monkeypatch.setattr(common, "STATE_LOCK", _LockQueFalla())
    with B.suscribir("prueba.lock", 2) as sub:
        ses = SesionFalsa()
        B.BUS.abrir(ses)
        try:
            assert B.enviar_vivo("prueba.lock", {"pulsar": "-S1", "id": 1})
            assert B.enviar_vivo("prueba.lock", {"control": "pausa"}) is False
            assert _json(B.BUS, {"tipo": "ack", "id": "prueba.lock:1", "t": 0.0, "accion": {}})
            B.BUS.difundir_fotograma(b"\x01")
            assert [m if isinstance(m, bytes) else m["tipo"] for m in _todo(sub)] == ["rechazo", "ack", b"\x01"]
        finally:
            B.BUS.cerrar(ses)
    # y ni lo importa: es hoja (sin `apolo.state`, `S` ni otro módulo de la API)
    arbol = ast.parse((RAIZ / "core" / "apolo" / "api" / "vivo_bus.py").read_text(encoding="utf-8"))
    importa = {a.name for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
    importa |= {n.module or "." for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)}
    assert importa <= {"__future__", "collections", "json", "re", "threading"}, importa


# ── con el worker y el WebSocket ──────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def maquina():
    pytest.importorskip("mujoco")
    from cosim_lazo_banco import PROGRAMA, faja_variador

    doc = faja_variador()
    doc.execute("add_program", {"plc": "-K1", "fuente": PROGRAMA})
    return doc


@pytest.fixture
def c(maquina, monkeypatch):
    from cosim_lazo_banco import FOTO, MECANICA, MOTOR
    from fastapi.testclient import TestClient

    import apolo.api.main as api

    monkeypatch.setattr(api, "DOC", maquina)
    cli = TestClient(api.app)
    base = {"duracion_s": 3.0, "mecanica": MECANICA, "acoples": {"motores": MOTOR, "sensores": FOTO}}
    assert cli.put("/api/escenarios/base", json={"escenario": base}).status_code == 200
    return cli


def _url(c, **q) -> str:
    q = {"documento": c.get("/api/health").json()["documento"], "escenario": "base", **q}
    return "/api/cosim/vivo?" + "&".join(f"{k}={v}" for k, v in q.items())


def test_el_suscriptor_sigue_la_sesion_y_le_escribe(c):
    from ext_prueba.suscriptor import SuscriptorPrueba
    from starlette.websockets import WebSocketDisconnect

    from apolo.api.routers import cosim_vivo as R

    scada = SuscriptorPrueba()
    lenta = B.suscribir("prueba.lenta", max_fotogramas=5)   # nunca lee hasta el final
    ws_orden: list[str] = []
    ws_msgs: list[dict] = []
    try:
        with c.websocket_connect(_url(c, ritmo=1, max_s=1.5)) as ws:
            def siguiente() -> dict | None:
                m = ws.receive()
                assert m["type"] != "websocket.close", m
                if m.get("bytes") is not None:
                    ws_orden.append("F")
                    return None
                msg = json.loads(m["text"])
                ws_orden.append(msg["tipo"])
                ws_msgs.append(msg)
                return msg

            def hasta(pred) -> dict:
                for _ in range(2000):
                    msg = siguiente()
                    if msg is not None and pred(msg):
                        return msg
                raise AssertionError("no llegó")

            hasta(lambda m: m["tipo"] == "inicio")
            ws.send_json({"girar": "-S1", "valor": 1.0, "id": 1})
            hasta(lambda m: m["tipo"] == "ack" and m["id"] == 1)
            # D11: la acción del bus con STATE_LOCK tomado por otro hilo (el bus no lo pide)
            tomado, soltar = threading.Event(), threading.Event()

            def sostener():
                with apolo.state.STATE_LOCK:
                    tomado.set()
                    soltar.wait(30)

            hilo = threading.Thread(target=sostener, daemon=True)
            hilo.start()
            assert tomado.wait(10)
            try:
                assert scada.enviar({"pulsar": "-S1", "actuador": "marcha", "durante_s": 0.2, "id": 7})
                ack = scada.esperar(lambda m: m["tipo"] == "ack" and m["id"] == "prueba.scada:7", 30)
                assert ack["accion"]["dispositivo"] == "-S1" and ack["t"] > 0
            finally:
                soltar.set()
                hilo.join(10)
            assert scada.enviar({"control": "parar"}) is False   # los controles son de la persona
            fin = hasta(lambda m: m["tipo"] == "fin")
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()
            assert exc.value.code == 1000
        ses = R.SESIONES.ultima
        # la grabación no distingue de dónde vino la acción (sin ids)
        assert [g["accion"] for g in fin["grabacion"]] == ["girar", "pulsar"]
        assert all("id" not in g for g in fin["grabacion"])
        assert fin["escenario"]["acciones"][1]["actuador"] == "marcha"
        scada.esperar(lambda m: m["tipo"] == "fin", 10)
        # el WebSocket no vio el ack del bus; el suscriptor vio el de la persona
        assert [m["id"] for m in ws_msgs if m["tipo"] in ("ack", "rechazo")] == [1]
        assert any(m["tipo"] == "ack" and m["id"] == 1 for m in scada.jsons)
        privados = [m for m in scada.jsons if str(m.get("id")).startswith("prueba.scada:")]
        assert [m["tipo"] for m in privados] == ["ack", "rechazo"]   # el ack de la acción y el del control
        sin_privados = [t for t, m in zip(scada.orden, _con_json(scada)) if m is None or m not in privados]
        if scada.sub.descartados == 0 and ses.descartados == 0:
            assert sin_privados == ws_orden            # lo mismo y en el mismo orden
        else:  # una máquina lenta: al menos el JSON, igual y en orden
            assert [t for t in sin_privados if t != "F"] == [t for t in ws_orden if t != "F"]
        # la lenta descartó fotogramas viejos y los contó; el WebSocket los recibió todos
        assert ses.descartados == 0 and ws_orden.count("F") > 30
        assert lenta.descartados == ws_orden.count("F") - 5
        resto = _todo(lenta)
        assert resto[0]["tipo"] == "inicio" and resto[-1]["tipo"] == "fin"
        assert sum(isinstance(m, bytes) for m in resto) == 5
        # sesión cerrada: False
        assert scada.enviar({"pulsar": "-S1"}) is False
    finally:
        scada.cerrar()
        lenta.cerrar()


def _con_json(s) -> list:
    """Alinea `orden` con el mensaje de cada entrada (None para un fotograma)."""
    it = iter(s.jsons)
    return [None if t == "F" else next(it) for t in s.orden]
