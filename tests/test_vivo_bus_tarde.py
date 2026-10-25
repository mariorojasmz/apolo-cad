"""El bus entrega la sesión ya abierta (plan pedidos-de-extensiones D11, D13; `api/vivo_bus.py`).

  - sin worker: quien se suscribe a mitad recibe primero el `inicio` (`tarde: true`), cada
    `senales` en orden y un `textos` con lo acumulado, y después lo que siga; lo guardado vale
    aunque no hubiera nadie suscrito; otra sesión no repite la vieja (ni la reemplazada que se
    apaga borra la nueva); tras el `fin` o el `cerrar`, nada que repetir; con fotogramas y
    `senales` saliendo desde otro hilo, ningún fotograma se adelanta a su tabla; la cola de la
    persona es la misma con y sin suscriptor tardío; nada toma `STATE_LOCK`;
  - con el worker y `WS /api/cosim/vivo`: el suscriptor de `tests/ext_prueba/suscriptor.py` llega
    con la sesión en marcha, lee los fotogramas con la tabla repetida y termina con la misma tabla,
    los mismos textos y el mismo final que el WebSocket; el `inicio` trae `plcs`; tras el `fin`
    nada; la sesión siguiente no le repite la vieja.
"""

from __future__ import annotations

import json
import struct
import threading

import pytest

import apolo.api.common as common
import apolo.state
from apolo.api import vivo_bus as B
from apolo.api.vivo_bus import Bus


def _json(bus: Bus, msg: dict, sesion=None) -> bool:
    return bus.difundir_json(msg, json.dumps(msg, ensure_ascii=False, separators=(",", ":")), sesion)


def _todo(sub) -> list:
    out = []
    while (m := sub.recibir(timeout=0)) is not None:
        out.append(m)
    return out


def _tipos(msgs) -> list:
    return [m if isinstance(m, bytes) else m["tipo"] for m in msgs]


INICIO = {"tipo": "inicio", "version": 1, "senales": ["a"]}


def test_quien_llega_tarde_recibe_primero_la_sesion_abierta():
    bus = Bus()
    ses = object()
    bus.abrir(ses)
    _json(bus, INICIO, ses)                       # sin nadie suscrito: se guarda igual
    bus.difundir_fotograma(b"\x00")
    _json(bus, {"tipo": "senales", "desde": 1, "nombres": ["b"]}, ses)
    _json(bus, {"tipo": "textos", "t": 0.1, "valores": {"-K1.estado": "STOP", "-K1.falla": ""}}, ses)
    _json(bus, {"tipo": "ack", "id": 3, "t": 0.1, "accion": {}}, ses)   # no se repite
    _json(bus, {"tipo": "senales", "desde": 2, "nombres": ["c", "d"]}, ses)
    _json(bus, {"tipo": "textos", "t": 0.2, "valores": {"-K1.estado": "RUN"}}, ses)
    with bus.suscribir("prueba.tarde") as sub:
        bus.difundir_fotograma(b"\x01")
        _json(bus, {"tipo": "textos", "t": 0.3, "valores": {"-K1.falla": "watchdog"}}, ses)
        msgs = _todo(sub)
    assert _tipos(msgs) == ["inicio", "senales", "senales", "textos", b"\x01", "textos"]
    assert msgs[0] == {**INICIO, "tarde": True}
    assert [m["nombres"] for m in msgs[1:3]] == [["b"], ["c", "d"]]
    assert msgs[3] == {"tipo": "textos", "t": 0.2, "tarde": True,
                       "valores": {"-K1.estado": "RUN", "-K1.falla": ""}}
    assert "tarde" not in msgs[5]
    # la tabla que arma quien llega tarde es la de la sesión
    assert INICIO["senales"] + [n for m in msgs[1:3] for n in m["nombres"]] == ["a", "b", "c", "d"]


def test_sin_textos_no_hay_textos_y_el_suscrito_desde_antes_no_recibe_nada_repetido():
    bus = Bus()
    ses = object()
    antes = bus.suscribir("prueba.antes")
    _json(bus, INICIO, ses)
    with bus.suscribir("prueba.tarde") as sub:
        assert _tipos(_todo(sub)) == ["inicio"]
    (ini,) = _todo(antes)
    assert ini == INICIO   # lo recibió en vivo, sin `tarde`, y una sola vez


def test_otra_sesion_no_repite_la_vieja():
    bus = Bus()
    vieja, nueva = object(), object()
    bus.abrir(vieja)
    _json(bus, {**INICIO, "pid": 1}, vieja)
    # se abre la nueva (reemplazar): su `inicio` puede llegar antes que `abrir`
    _json(bus, {**INICIO, "pid": 2}, nueva)
    bus.abrir(nueva)
    _json(bus, {"tipo": "fin", "motivo": "reemplazada"}, vieja)   # la vieja se apaga después
    _json(bus, {"tipo": "senales", "desde": 1, "nombres": ["x"]}, vieja)
    bus.cerrar(vieja)
    with bus.suscribir("prueba.tarde") as sub:
        msgs = _todo(sub)
    assert _tipos(msgs) == ["inicio"] and msgs[0]["pid"] == 2
    # abrir otra sesión sin su `inicio` todavía: nada que repetir de la anterior
    otra = object()
    bus.abrir(otra)
    with bus.suscribir("prueba.tarde") as sub:
        assert _todo(sub) == []


def test_tras_el_fin_o_el_cerrar_nada_que_repetir():
    bus = Bus()
    ses = object()
    bus.abrir(ses)
    _json(bus, INICIO, ses)
    _json(bus, {"tipo": "fin", "motivo": "tope"}, ses)
    with bus.suscribir("prueba.tarde") as sub:
        assert _todo(sub) == []
    _json(bus, INICIO, ses)
    bus.cerrar(ses)
    with bus.suscribir("prueba.tarde") as sub:
        assert _todo(sub) == []


def test_ningun_fotograma_se_adelanta_a_su_tabla():
    """Otro hilo publica `senales` y fotogramas que dicen cuántas señales traen; cada suscriptor
    que llega a mitad arma la tabla con lo que recibe y todo fotograma la encuentra completa."""
    bus = Bus()
    ses = object()
    _json(bus, {"tipo": "inicio", "senales": []}, ses)
    parar = threading.Event()

    def publicar():
        n = 0
        while not parar.is_set() and n < 20000:
            if n % 7 == 0:
                k = n // 7
                _json(bus, {"tipo": "senales", "desde": k, "nombres": [f"s{k}"]}, ses)
            bus.difundir_fotograma(struct.pack("<I", n // 7 + 1))
            n += 1

    hilo = threading.Thread(target=publicar, daemon=True)
    hilo.start()
    try:
        for i in range(40):
            with bus.suscribir(f"prueba.t{i}", max_fotogramas=100000) as sub:
                tabla, vistos = None, 0
                for m in _todo(sub):
                    if isinstance(m, bytes):
                        assert tabla is not None and struct.unpack("<I", m)[0] == len(tabla)
                        vistos += 1
                    elif m["tipo"] == "inicio":
                        assert tabla is None and m["tarde"] is True
                        tabla = list(m["senales"])
                    else:
                        assert m["desde"] == len(tabla)
                        tabla += m["nombres"]
                assert tabla is not None
    finally:
        parar.set()
        hilo.join(10)


def test_la_cola_de_la_persona_es_la_misma_con_suscriptor_tardio():
    from apolo.api.routers.cosim_vivo import SesionViva

    def cola(con_tardio: bool) -> list:
        ses = SesionViva(None, 1)
        B.BUS.abrir(ses)
        try:
            ses.json({**INICIO})
            ses.json({"tipo": "textos", "t": 0.1, "valores": {"x": "RUN"}})
            sub = B.suscribir("prueba.tarde") if con_tardio else None
            ses.json({"tipo": "senales", "desde": 1, "nombres": ["b"]})
            ses.json({"tipo": "fin", "motivo": "tope"})
            if sub is not None:
                assert _tipos(_todo(sub)) == ["inicio", "textos", "senales", "fin"]
                sub.cerrar()
        finally:
            B.BUS.cerrar(ses)
        out = []
        while not ses.cola.empty():
            out.append(ses.cola.get_nowait())
        return out

    sin = cola(False)
    assert cola(True) == sin and [json.loads(t)["tipo"] for _, t in sin] == [
        "inicio", "textos", "senales", "fin"]
    assert all("tarde" not in t for _, t in sin)


class _LockQueFalla:
    def __enter__(self):
        raise AssertionError("el bus tomó STATE_LOCK")

    acquire = __enter__

    def __exit__(self, *_):
        return False


def test_repetir_no_toma_state_lock(monkeypatch):
    monkeypatch.setattr(apolo.state, "STATE_LOCK", _LockQueFalla())
    monkeypatch.setattr(common, "STATE_LOCK", _LockQueFalla())
    ses = object()
    B.BUS.abrir(ses)
    try:
        _json(B.BUS, INICIO, ses)
        _json(B.BUS, {"tipo": "textos", "t": 0.0, "valores": {"x": 1}}, ses)
        with B.suscribir("prueba.lock") as sub:
            assert _tipos(_todo(sub)) == ["inicio", "textos"]
    finally:
        B.BUS.cerrar(ses)


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


def _sesion(c, max_s: float, al_ver=None, cuando=None) -> tuple[list, list, list]:
    """Corre una sesión por WebSocket hasta el `fin`: (orden, JSON, fotogramas). `al_ver()` corre
    una vez, apenas `cuando(orden, jsons)` se cumple."""
    from starlette.websockets import WebSocketDisconnect

    orden, msgs, fotos = [], [], []
    with c.websocket_connect(_url(c, ritmo=1, max_s=max_s)) as ws:
        while True:
            m = ws.receive()
            assert m["type"] != "websocket.close", m
            if m.get("bytes") is not None:
                orden.append("F")
                fotos.append(m["bytes"])
            else:
                msg = json.loads(m["text"])
                orden.append(msg["tipo"])
                msgs.append(msg)
                if msg["tipo"] == "fin":
                    break
            if al_ver is not None and cuando(orden, msgs):
                al_ver()
                al_ver = None
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    return orden, msgs, fotos


def test_el_suscriptor_llega_tarde_y_sigue_la_sesion(c):
    from ext_prueba.suscriptor import SuscriptorPrueba

    from apolo.api.routers import cosim_vivo as R

    tarde: list = []

    def llegar():
        tarde.append(SuscriptorPrueba("prueba.tarde"))

    try:
        orden, msgs, fotos = _sesion(
            c, 1.5, llegar,
            lambda o, j: o.count("F") >= 10 and any(m["tipo"] == "textos" for m in j))
        assert tarde, "la sesión terminó antes de que llegara el suscriptor"
        sub = tarde[0]
        sub.esperar(lambda m: m["tipo"] == "fin", 30)
        ses = R.SESIONES.ultima
        ini = msgs[0]
        assert ini["tipo"] == "inicio" and "tarde" not in ini
        assert not [m for m in msgs if "tarde" in m]   # la persona recibe lo de siempre
        # lo primero: el `inicio` de ESTA sesión con `tarde`, las `senales` y los textos
        assert sub.orden[0] == "inicio" and sub.jsons[0] == {**ini, "tarde": True} and sub.tarde
        n = 1
        while sub.jsons[n]["tipo"] == "senales":
            n += 1
        assert sub.jsons[n]["tipo"] == "textos" and sub.jsons[n]["tarde"] is True
        assert sub.orden.index("F") >= n + 1   # ningún fotograma antes de la tabla y los textos
        # cada fotograma se leyó con la tabla de su momento y la tabla final es la de la persona
        tabla_ws = list(ini["senales"])
        textos_ws: dict = {}
        for m in msgs:
            if m["tipo"] == "senales":
                tabla_ws[m["desde"]:] = m["nombres"]
            elif m["tipo"] == "textos":
                textos_ws.update(m["valores"])
        assert sub.desfasados == 0 and len(sub.leidos) == len(sub.fotogramas) > 0
        assert sub.senales == tabla_ws and sub.textos == textos_ws
        # después de la repetición, lo mismo que el WebSocket (su final)
        resto = sub.jsons[n + 1:]
        assert resto == msgs[len(msgs) - len(resto):] and resto[-1]["tipo"] == "fin"
        if sub.sub.descartados == 0 and ses.descartados == 0:
            assert sub.fotogramas == fotos[len(fotos) - len(sub.fotogramas):]
        # D12: las variables del PLC, con las rutas de sus señales
        (plc,) = ini["plcs"]
        assert plc["designacion"] == "-K1"
        rutas = {v["ruta"]: v for v in plc["variables"]}
        assert rutas["Main.cuenta"] == {"ruta": "Main.cuenta", "tipo": "INT", "escribible": True}
        assert rutas["foto"]["escribible"] is False                 # AT %IX0.0
        assert not [r for r in rutas if r.startswith("Main.flanco")]  # un bloque no es señal
        senales_plc = {s[len("-K1."):] for s in [*tabla_ws, *textos_ws] if s.startswith("-K1.")}
        assert set(rutas) <= senales_plc and {"Main.cuenta", "Main.en_marcha", "foto"} <= set(rutas)
        assert set(sub.variables) == {f"-K1.{r}" for r in rutas}
    finally:
        for s in tarde:
            s.cerrar()
    # tras el `fin`, nada que repetir
    with B.suscribir("prueba.despues") as despues:
        assert despues.recibir(timeout=0.2) is None


def test_la_sesion_siguiente_no_repite_la_anterior(c):
    from ext_prueba.suscriptor import SuscriptorPrueba

    _, primera, _ = _sesion(c, 0.3)
    tarde: list = []
    try:
        _, segunda, _ = _sesion(c, 0.6, lambda: tarde.append(SuscriptorPrueba("prueba.tarde")),
                                lambda o, j: o.count("F") >= 3)
        assert tarde
        sub = tarde[0]
        sub.esperar(lambda m: m["tipo"] == "fin", 30)
        assert primera[0]["pid"] != segunda[0]["pid"]
        assert [m["tipo"] for m in sub.jsons].count("inicio") == 1
        assert sub.jsons[0]["pid"] == segunda[0]["pid"] and sub.jsons[0]["tarde"] is True
    finally:
        for s in tarde:
            s.cerrar()
