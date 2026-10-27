"""El metadato `justificadas` sin trampas (puerta-sin-sobrediseno D11, arreglo del 2026-10-27):
dos modeladores perdieron justificaciones con `set_justifications` —la llamaron con `[]` para
VERLAS, y reescribieron las 6 previas para sumar una—, el `porque` se recortaba a 300 sin aviso y
una designación eléctrica («-MM1») que la puerta muestra como pieza daba «pieza inexistente»."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.library.calidad import justificadas as J
from apolo.library.calidad.puerta import erc
from apolo.library.electrico.modelo import Cable, Dispositivo, ModeloElectrico
from apolo.services import puerta_publicacion as pp
from apolo.services.errors import ServiceError

PORQUE = "la guía del producto pide este cierre contra el polvo del galpón"


def _doc():
    d = Document("t")
    a = d.execute("create_box", {"name": "Guarda A", "width": 10, "depth": 10, "height": 10})
    b = d.execute("create_box", {"name": "Guarda B", "width": 10, "depth": 10, "height": 10})
    return d, a, b


# ------------------------------------------------------------------ el porque, entero o rechazado
def test_el_porque_largo_se_guarda_entero_y_el_excesivo_se_rechaza_sin_recortar():
    cuenta = "M = F·d = 1200 N × 0,35 m = 420 N·m < 0,8 × 610 N·m; " * 8  # ~450 caracteres
    assert 300 < len(cuenta.strip()) <= J.MAX_PORQUE
    assert J.validar_justificadas([{"regla": "x", "porque": cuenta}])[0]["porque"] == cuenta.strip()
    with pytest.raises(ValueError, match=r"601 caracteres, el tope es 600.*no se recorta"):
        J.validar_justificadas([{"regla": "x", "porque": "y" * 601}])


# ------------------------------------------------------------------ agregar por (regla, pieza)
def test_fusionar_agrega_o_reemplaza_por_par_sin_tocar_el_resto():
    previas = [{"regla": "a", "porque": "1"}, {"regla": "b", "pieza": "c1", "porque": "2"},
               {"pieza": "c9", "porque": "3"}]
    nuevas = [{"regla": "b", "pieza": "c1", "porque": "nuevo"}, {"regla": "b", "pieza": "c2",
                                                                  "porque": "4"}]
    out, agregadas, reemplazadas = J.fusionar(previas, nuevas)
    assert (agregadas, reemplazadas) == (1, 1)
    assert [J.clave(j) for j in out] == [("a", None), ("b", "c1"), (None, "c9"), ("b", "c2")]
    assert out[1]["porque"] == "nuevo" and previas[1]["porque"] == "2"  # no muta las previas


def test_el_endpoint_lee_agrega_y_cuenta_lo_que_borra():
    d, a, b = _doc()
    api.DOC = d
    c = TestClient(api.app)
    r = c.put("/api/justificadas", json={"justificadas": [
        {"pieza": a, "porque": PORQUE}, {"regla": "lint pre-entrega", "porque": PORQUE}]}).json()
    assert r["quedaron"] == 2 and r["borradas"] == 0
    # agregar: suma b y reemplaza la de la regla, sin tocar la de a
    r = c.put("/api/justificadas", json={"modo": "agregar", "justificadas": [
        {"pieza": b, "porque": PORQUE}, {"regla": "lint pre-entrega", "porque": PORQUE + " (2)"}]})
    assert r.status_code == 200
    r = r.json()
    assert (r["quedaron"], r["agregadas"], r["reemplazadas"]) == (3, 1, 1)
    leidas = c.get("/api/justificadas").json()["justificadas"]
    assert [j.get("pieza") for j in leidas] == [a, None, b] and leidas[1]["porque"].endswith("(2)")
    # reemplazar dice cuántas se fueron; `[]` también
    r = c.put("/api/justificadas", json={"justificadas": [{"pieza": a, "porque": PORQUE}]}).json()
    assert (r["quedaron"], r["borradas"]) == (1, 2)
    r = c.put("/api/justificadas", json={"justificadas": []}).json()
    assert (r["quedaron"], r["borradas"]) == (0, 1) and d.justificadas == []
    r = c.put("/api/justificadas", json={"modo": "sumar", "justificadas": []})
    assert r.status_code == 400 and "agregar" in r.json()["detail"]


def test_agregar_valida_lo_nuevo_y_no_toca_nada_si_falla():
    d, a, _b = _doc()
    pp.cambiar_justificadas(d, [{"pieza": a, "porque": PORQUE}])
    antes = list(d.justificadas)
    with pytest.raises(ServiceError, match="c99"):
        pp.cambiar_justificadas(d, [{"pieza": "c99", "porque": PORQUE}], "agregar")
    with pytest.raises(ServiceError, match="al menos 20"):
        pp.cambiar_justificadas(d, [{"regla": "x", "porque": "corto"}], "agregar")
    assert d.justificadas == antes


# ------------------------------------------------------------------ la designación que la puerta muestra
def test_una_designacion_del_tablero_se_justifica_tal_como_la_muestra_la_puerta():
    """La puerta muestra las `elementos` del ERC (designaciones) como piezas de `riesgos.electrico`;
    la justificación por (regla, «-MM1») tiene que aceptarse y cubrir ese aviso."""
    d, _a, _b = _doc()
    d.electrico = ModeloElectrico(
        dispositivos=(Dispositivo(designacion="-MM1", ref="cil", funcion="cilindro", bornes=()),),
        cables=(Cable(designacion="-W4", ref="cable"),))
    js = pp.cambiar_justificadas(d, [
        {"regla": "calentamiento", "pieza": "-MM1", "porque": PORQUE},
        {"regla": "cable", "pieza": "-W4", "porque": PORQUE}])["justificadas"]
    assert [j["pieza"] for j in js] == ["-MM1", "-W4"]
    reglas = [{"regla": "calentamiento", "estado": "aviso", "elementos": ["-MM1"]}]
    assert erc({"electrico": reglas, "justificadas": js})["estado"] == "OK"
    with pytest.raises(ServiceError, match=r"-MM9.*designación de un aparato"):
        pp.cambiar_justificadas(d, [{"regla": "x", "pieza": "-MM9", "porque": PORQUE}])
