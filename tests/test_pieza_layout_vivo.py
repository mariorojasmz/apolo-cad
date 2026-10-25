"""La pieza de lo que dibuja el layout en la tabla del vivo (plan pedidos-de-extensiones, F7: D15).

- Un tablero armado con `layout_tablero` y un panel de operador: la tabla del `inicio` trae la
  `pieza` de cada aparato dibujado (la caja `{cmd}_d_<designación>`), la del panel incluida, junto
  a su `pantalla_px`: la pantalla 3D de una extensión se pega a esa pieza.
- Una `pieza` explícita (`add_device pieza`, A9) gana: el layout no la dibuja y la tabla trae la
  explícita.
- La regla es UNA (`services/tablero.piezas_3d`, la del panel del tablero) y no toca ni la física
  ni la firma: el `Dispositivo` del carril y lo que ve el worker siguen igual.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from tablero_electrico import arranque_variador_plc, dev, wire

from apolo.doc.document import Document

HMI = "HMI-7IN-24VDC"
BU = {"color": "BU", "seccion_mm2": 0.75}
DT = 0.002


def _con_panel(pieza_variador: str | None = None) -> list[dict]:
    cmds = arranque_variador_plc() + [
        dev(HMI, "-P2"), wire("-T1:L+", "-P2:L+", **BU), wire("-T1:M", "-P2:M", **BU),
        wire("-X0:1", "-P2:PE", color="GNYE"),
        {"type": "layout_tablero", "params": {"ubicacion": "TAB1"}}]
    if pieza_variador:
        for c in cmds:
            if c["type"] == "add_device" and c["params"]["designacion"] == "-T2":
                c["params"]["pieza"] = pieza_variador
    return cmds


def _cid(d: Document) -> str:
    return next(c["id"] for c in d.commands if c["type"] == "layout_tablero")


def _corrida(d: Document) -> SimpleNamespace:
    """Lo que `Fotograma.tabla` lee de una corrida: el tablero y los dispositivos del snapshot
    (`cosim_aire.dispositivos`, los mismos que ve el worker)."""
    from apolo.cosim.tablero import Tablero
    from apolo.services import cosim_aire
    from apolo.services.cosim_red import entrada_red

    m = d.electrico
    devs = cosim_aire.dispositivos(d, m, [])
    din = SimpleNamespace(cuerpos=[], productos=[], juntas={}, bandas=[])
    return SimpleNamespace(tab=Tablero(entrada_red(m), devs), dt=DT, snap=SimpleNamespace(dispositivos=devs),
                           integ=SimpleNamespace(snap=din, d=None, bid_cuerpo={}, giro={}))


def _inicio_de(d: Document) -> dict:
    """La tabla del worker (`Fotograma.tabla`, con los dispositivos del carril tal cual) vuelta
    `inicio` por la API, con las piezas que `_preparar` toma bajo el lock."""
    from apolo.api.routers.cosim_vivo import _inicio
    from apolo.cosim.vivo_fotograma import Fotograma
    from apolo.services.tablero import piezas_3d

    tabla = Fotograma(_corrida(d)).tabla()
    snap = SimpleNamespace(avisos=[], hipotesis=[], dinamica=SimpleNamespace(cuerpos=[]))
    prep = {"snap": snap, "vis": None, "proyecto": 1, "nombre": "marcha", "firma": "2:x",
            "piezas": piezas_3d(d)}
    return _inicio(prep, {"tipo": "tabla", **tabla}, {"max_s": 60, "ritmo": 1.0}, None)


@pytest.fixture(scope="module")
def armado() -> Document:
    d = Document()
    d.execute_many(_con_panel())
    return d


def test_la_tabla_del_inicio_trae_la_pieza_de_cada_aparato_dibujado(armado):
    from apolo.services.tablero import dibujados

    d, cid = armado, _cid(armado)
    dib = dibujados(d)
    ini = _inicio_de(d)
    # el panel de operador: su caja del layout, con su resolución (lo que lee `pantallas3d`)
    panel = next(x for x in ini["dispositivos"] if x["designacion"] == "-P2")
    assert panel == {"designacion": "-P2", "tipo": "hmi", "ref": HMI, "pieza": f"{cid}_d_P2",
                     "pantalla_px": [800, 480]}
    f = d.scene[panel["pieza"]]
    assert f.component == HMI and f.command_id == cid
    # cada fila de la tabla cuyo aparato dibujó el layout lleva ESA pieza, y está en la escena
    vistos = set()
    for lista in ("mandos", "pilotos", "dispositivos"):
        for x in ini[lista]:
            des = x["designacion"]
            if des in dib:
                assert x.get("pieza") == dib[des] and dib[des] in d.scene, (lista, des)
                vistos.add(des)
            else:
                assert "pieza" not in x, (lista, des)  # en campo y sin pieza: nada que pegar
    assert {"-P2", "-T2", "-K1", "-S0", "-P1", "-Q1"} <= vistos
    seta = next(x for x in ini["mandos"] if x["designacion"] == "-S0")
    assert list(seta)[:7] == ["designacion", "tipo", "ref", "acciones", "color", "fondo", "pieza"]


def test_el_worker_no_ve_la_pieza_del_layout_y_la_firma_no_cambia(armado):
    """La regla vive al armar el `inicio`: el `Dispositivo` (el del worker y el de la firma) sigue
    sin pieza; la tabla del worker, tal cual."""
    from apolo.cosim.vivo_fotograma import Fotograma
    from apolo.services.tablero import piezas_en_tabla

    assert all(d.pieza is None for d in armado.electrico.dispositivos)
    corrida = _corrida(armado)
    assert all(x.pieza is None for x in corrida.snap.dispositivos)
    tabla = Fotograma(corrida).tabla()
    assert all("pieza" not in x for x in tabla["dispositivos"])
    assert piezas_en_tabla(tabla, {}) is tabla  # sin piezas, la tabla tal cual


def test_una_pieza_explicita_gana(armado):
    from apolo.services.tablero import piezas_3d

    c = _cid(armado)
    centro = armado.scene[f"{c}_d_T2"].shape.bounding_box().center()
    vfd = {"type": "insert_component", "params": {
        "component": "VFD-2K2-220", "name": "Variador",
        "position": {"x": centro.X, "y": centro.Y, "z": centro.Z}}}
    d = Document()
    d.execute_many([vfd] + _con_panel(pieza_variador="$1"))
    c2, vid = _cid(d), d.commands[0]["id"]
    assert f"{c2}_d_T2" not in d.scene  # A9: el layout no la dibuja
    p = piezas_3d(d)
    assert p["-T2"] == vid and p["-P2"] == f"{c2}_d_P2"
    ini = _inicio_de(d)
    t2 = next(x for x in ini["dispositivos"] if x["designacion"] == "-T2")
    assert t2["pieza"] == vid


def test_piezas_en_tabla_no_pisa_una_pieza_que_ya_viene():
    from apolo.services.tablero import piezas_en_tabla

    tabla = {"dispositivos": [{"designacion": "-T2", "tipo": "variador", "ref": "V", "pieza": "c1"},
                              {"designacion": "-K1", "tipo": "plc", "ref": "P"}],
             "pilotos": [{"designacion": "-P1", "ref": "L", "color": "verde", "senal": "-P1.encendido"}],
             "senales": ["a"]}
    out = piezas_en_tabla(tabla, {"-T2": "c9_d_T2", "-K1": "c9_d_K1", "-P1": "c9_d_P1"})
    assert out["dispositivos"][0]["pieza"] == "c1"
    assert out["dispositivos"][1] == {"designacion": "-K1", "tipo": "plc", "ref": "P", "pieza": "c9_d_K1"}
    assert list(out["pilotos"][0]) == ["designacion", "ref", "color", "pieza", "senal"]
    assert out["senales"] is tabla["senales"] and "pieza" not in tabla["dispositivos"][1]
