"""Lecturas livianas y el ERC que nombra el conductor (plan `docs/plans/pedidos-de-extensiones-ii.md`,
F2: D4–D6).

- D4: el ERC (y los avisos de la co-simulación) nombran el conductor por sus puntos y su etiqueta
  (`redes.nombre_conductor`), nunca «conductor 13»; el número queda en `conductores` de la fila.
- D5: `get_circuit(tablero=true)` resume cada tablero (≤ 1/4 de lo de antes en la piloto);
  `completo=true` da lo de siempre, byte a byte; sin `tablero`, nada cambia.
- D6: `run_batch(detail="summary")` devuelve `comandos`, el id de cada acción en orden (`$k`
  resuelta), también de lo que no crea sólidos; `edit_batch`, los editados.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import re

import pytest
from fastapi.testclient import TestClient
from test_electrico_erc import _con, _idx, arranque_directo, avisos, errores, w
from test_erc_seguridad import PE, arranque_variador
from test_tablero_panel import _doc

import apolo.api.main as api
from apolo.doc import Document
from apolo.library.electrico.erc import erc
from apolo.library.electrico.modelo import Conductor
from apolo.library.electrico.redes import Problema, analizar, nombre_conductor
from apolo.services import electrico

#: lo que el ERC ya no escribe: un índice interno del modelo
INDICE = re.compile(r"conductor \d")


# ── D4: el conductor por sus extremos ────────────────────────────────────────────────────


def test_nombre_conductor_son_sus_puntos_y_su_etiqueta():
    assert nombre_conductor(Conductor(("-T2:V", "-M1:V1"))) == "-T2:V → -M1:V1"
    assert nombre_conductor(Conductor(("-T2:V", "-M1:V1"), cable="-W1", hilo="2")) == "-T2:V → -M1:V1 [-W1.2]"
    assert nombre_conductor(Conductor(("-X0:1", "-T1:PE", "-X0:2"), potencial="PE")) == \
        "-X0:1 → -T1:PE → -X0:2 [PE]"
    assert nombre_conductor(Conductor(("-Q1:2", "-F1:1"), cable="-W4", hilo="1", potencial="L1")) == \
        "-Q1:2 → -F1:1 [-W4.1, L1]"
    assert nombre_conductor(Conductor(())) == "sin puntos"


def test_el_color_nombra_el_conductor_y_deja_su_numero_aparte():
    m = arranque_directo()
    i = _idx(m, "-T1:L+", "-S0:11")
    [a] = avisos(erc(_con(m, cambiar={i: dataclasses.replace(m.conductores[i], color="RD")})),
                 "color del conductor")
    assert a["detalle"].startswith(f"conductor {' → '.join(m.conductores[i].puntos)} es RD: ")
    assert not INDICE.search(a["detalle"]) and a["conductores"] == [i + 1]
    # verde: la fila «ok» no lleva la clave
    [ok] = [r for r in erc(m) if r["regla"] == "color del conductor"]
    assert ok["estado"] == "ok" and "conductores" not in ok


def test_el_hilo_de_un_cable_sale_en_la_etiqueta():
    m = arranque_directo()
    i = _idx(m, "-Q3:2", "-M1:U1")
    [a] = avisos(erc(_con(m, cambiar={i: w("-Q3:2", "-M1:U1", cable="-W1", hilo="PE")})), "color del conductor")
    assert a["detalle"].startswith("conductor -Q3:2 → -M1:U1 [-W1.PE] es GNYE: ") and a["conductores"] == [i + 1]


def test_una_referencia_rota_nombra_el_conductor_y_guarda_su_numero():
    m = arranque_directo()
    n = len(m.conductores)
    m = _con(m, agregar=(w("-Q3:A1", "-K9:A2"), w("-Q3:A1", "-Q3:A1", cable="-W7", hilo="1")))
    probs = analizar(m).problemas
    assert all(isinstance(p, Problema) for p in probs)
    assert [p.conductor for p in probs] == [n + 1, n + 2]
    malas = errores(erc(m), "referencias")
    k9 = next(r for r in malas if "-K9" in r["detalle"])
    assert k9["detalle"].startswith("conductor -Q3:A1 → -K9:A2: «-K9:A2»") and k9["conductores"] == [n + 1]
    w7 = next(r for r in malas if "-W7" in r["detalle"])
    assert w7["detalle"].startswith("conductor -Q3:A1 → -Q3:A1 [-W7.1]: el cable -W7 no existe")
    assert w7["conductores"] == [n + 2]
    assert not any(INDICE.search(r["detalle"]) for r in malas)
    assert all(len(r["conductores"]) == 1 for r in malas)


def test_pe_en_cadena_nombra_los_conductores_del_paso():
    m = arranque_variador()
    i = _idx(m, "-X0:1", "-K1:PE")
    m = _con(m, cambiar={i: w("-T1:PE", "-K1:PE", **PE)})
    [mala] = [r for r in erc(m) if r["estado"] != "ok"]
    assert "(conductor -T1:PE → -K1:PE)" in mala["detalle"] and not INDICE.search(mala["detalle"])
    assert mala["conductores"] == [i + 1]


@pytest.fixture(scope="module")
def piloto() -> Document:
    return _doc()


def test_el_erc_de_la_piloto_no_dice_conductor_n(piloto):
    reglas = electrico.chequeo(piloto)["reglas"]
    assert not [r["detalle"] for r in reglas if INDICE.search(r["detalle"])]
    cadena = [r for r in reglas if r["regla"] == "PE en cadena" and r["estado"] == "error"]
    assert cadena, "la piloto encadena el PE por -T1, -T2 y -K1"
    for r in cadena:
        assert "conductor -X0:1 → -T1:PE → -T2:PE → -K1:PE → -X0:2 [PE]" in r["detalle"]
        assert r["conductores"] == [13]  # el que antes salía como «conductor 13»


# ── D5 y D6: por las tools reales, contra la API en proceso ──────────────────────────────


class _SinLifespan:
    def __init__(self, cliente):
        self._cliente = cliente

    def __enter__(self):
        return self._cliente

    def __exit__(self, *exc):
        return False


@pytest.fixture
def tool():
    """`tool(nombre, **args)` → el JSON de la tool MCP real, hablando con `api.app` en proceso."""
    pytest.importorskip("mcp")
    import apolo.mcp_server as mcp_server
    from apolo.tools.destino import Destino, apuntar

    destino = Destino("http://testserver", lambda: _SinLifespan(TestClient(api.app)))

    def llamar(nombre: str, **args) -> str:
        with apuntar(destino):
            out = asyncio.run(mcp_server.mcp.call_tool(nombre, args))
        bloques = out[0] if isinstance(out, tuple) else out
        return bloques[0].text
    return llamar


def _kb(x) -> int:
    return len((x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)).encode("utf-8"))


def test_get_circuit_con_tablero_resume_la_piloto(piloto, tool):
    api.DOC = piloto
    rest = TestClient(api.app).get("/api/electrico/circuito", params={"tablero": "true"}).json()
    corto = tool("get_circuit", tablero=True)
    assert _kb(corto) * 4 <= _kb(rest), (_kb(corto), _kb(rest))  # D5: ≤ 1/4 de lo de antes
    out = json.loads(corto)
    assert set(out) == {"tableros", "resumen", "seguir"} and out["resumen"] == rest["resumen"]
    [t] = out["tableros"]
    [panel] = rest["tableros"]
    assert t["veredicto"] == panel["veredicto"] and t["comando"] == panel["comando"]
    assert t["cuentas"] == {"aparatos": 12, "conductores": 33, "canaletas": len(panel["detalle"]["canaletas"]),
                            "cables_de_campo": len(panel["detalle"]["cables"])}
    # cada ítem con su motivo y los conductores que toca; sin lo que es de la cámara del visor
    assert [it["clave"] for it in t["items"]] == [it["clave"] for it in panel["items"]]
    largos = t["items"][0]
    assert largos["conductores"] == panel["items"][0]["conductores"] and largos["detalle"]
    assert not any("piezas" in it for it in t["items"] + t["bien"])
    # el detalle entero, a pedido: lo de siempre, igual que el REST
    assert json.loads(tool("get_circuit", tablero=True, completo=True)) == rest
    assert json.loads(tool("get_circuit", completo=True)) == rest


def test_get_circuit_sin_tablero_no_cambia(piloto, tool):
    api.DOC = piloto
    rest = TestClient(api.app).get("/api/electrico/circuito").json()
    assert json.loads(tool("get_circuit")) == rest and "tableros" not in rest
    # sin tablero armado, el resumen no inventa uno
    api.DOC = Document()
    vacio = json.loads(tool("get_circuit", tablero=True))
    assert vacio["tableros"] == []


def _caja(nombre: str, x: float = 0) -> dict:
    return {"type": "create_box", "params": {"name": nombre, "width": 50, "depth": 50, "height": 50,
                                             "position": {"x": x, "y": 0, "z": 0}}}


def test_run_batch_summary_devuelve_el_comando_de_cada_accion(tool):
    api.DOC = doc = Document("d6")
    doc.execute("create_box", {"name": "previa", "width": 10, "depth": 10, "height": 10})
    acciones = [_caja("A"), {"type": "set_variable", "params": {"name": "L", "expression": "100"}},
                _caja("B", 50), {"type": "fasten", "params": {"name": "f_ab", "a": "$1", "b": "$3"}}]
    out = json.loads(tool("run_batch", actions=acciones, detail="summary"))
    comandos = out["comandos"]
    assert len(comandos) == 4 and len(set(comandos)) == 4
    tipos = {c["id"]: c["type"] for c in doc.commands}
    assert [tipos[c] for c in comandos] == ["create_box", "set_variable", "create_box", "fasten"]
    fasten = next(c for c in doc.commands if c["id"] == comandos[3])
    assert (fasten["params"]["a"], fasten["params"]["b"]) == (comandos[0], comandos[2])  # $k = comandos[k-1]
    assert {s["comando"] for s in out["solidos"]} == {comandos[0], comandos[2]}
    # edit_batch: los editados, en el orden del lote
    ed = json.loads(tool("edit_batch", edits=[{"command_id": comandos[2], "params": {"width": 60}},
                                              {"command_id": comandos[0], "params": {"width": 40}}],
                         detail="summary"))
    assert ed["comandos"] == [comandos[2], comandos[0]]


def test_sin_summary_el_lote_no_suma_comandos(tool):
    api.DOC = Document("d6")
    out = json.loads(tool("run_batch", actions=[_caja("A")]))
    assert "comandos" not in out and out["solidos_mostrados"] == 1
