"""Puerta de publicación F2 — control del TENSOR (plan puerta-de-publicacion D3, D9): todo lazo
con un mecanismo de tensado RECONOCIDO (no por el nombre de una pieza), su carrera contra el
estiramiento del lazo y el perno tensor con agarre en toda la carrera. También el metadato
`tensores` (manifest + API) y la adherencia de Eytelwein que ahora lee el reconocimiento."""

import pytest
from fastapi.testclient import TestClient

from apolo.doc import Document
from apolo.library.calidad.item import FALLA, NO_APLICA, OK, SIN_EVALUAR
from apolo.library.calidad.tensor import (
    agarre_en_carrera,
    carrera_requerida,
    controlar_tensores,
    evaluar_lazo,
    validar_tensores,
)
from apolo.services.calidad_tensores import lazos, tensores_reconocidos, tiene_tensor_reconocido
from apolo.services.engineering_rules import inherit_tensor

COLA = {"x": -2000, "z": 845}  # el tambor de cola de la faja por defecto (largo 4000)


def _faja(tensor: str = "ninguno") -> Document:
    doc = Document("faja")
    doc.execute("create_belt_conveyor", {"tensor": tensor})
    return doc


def _items(doc):
    return {i.id: i for i in controlar_tensores(lazos(doc))}


def test_banda_sin_tensor_queda_sin_evaluar():
    doc = _faja()
    (lz,) = lazos(doc)
    assert lz["tipo"] == "banda" and lz["tensores"] == []
    # el lazo de pista: 2·4000 entre ejes + la vuelta a cada tambor (medido de la geometría)
    assert 8500 < lz["largo_mm"] < 8900
    items = _items(doc)
    assert {i.estado for i in items.values()} == {SIN_EVALUAR}
    assert items["tensor.reconocido"].piezas == ["c1_banda"]


def test_tensor_trotadora_de_catalogo_se_reconoce_pero_sin_carrera():
    items = _items(_faja("TENSOR-TROT-25"))
    assert items["tensor.reconocido"].estado == OK
    assert items["tensor.carrera"].estado == SIN_EVALUAR
    assert "no tabula su carrera" in items["tensor.carrera"].evidencia["casos"][0]["detalle"]


def test_take_up_con_carrera_insuficiente_falla():
    """create_take_up: el eje corre 12 mm a cada lado entre las aletas (24 mm), la banda de
    ~8,7 m pide 1 % + 20 ≈ 107 mm. El perno tensor agarra en los dos extremos."""
    doc = _faja()
    doc.execute("create_take_up", {"position": COLA})
    (lz,) = lazos(doc)
    (t,) = lz["tensores"]
    assert t["tipo"] == "take_up" and t["carrera_mm"] == pytest.approx(24, abs=0.1)
    assert [(p["antes"], p["despues"]) for p in t["pernos"]] == [
        pytest.approx((12, 12), abs=0.1)] * 2
    items = _items(doc)
    assert items["tensor.reconocido"].estado == OK
    assert items["tensor.carrera"].estado == FALLA
    caso = items["tensor.carrera"].evidencia["casos"][0]
    assert caso["pide_mm"] == pytest.approx(0.01 * lz["largo_mm"] + 20, abs=0.1)
    assert items["tensor.agarre"].estado == OK


def test_unidad_uct_de_catalogo_cubre_la_carrera():
    doc = _faja()
    doc.execute("insert_component", {"component": "UCT205-150",
                                     "position": {**COLA, "y": 420}})
    items = _items(doc)
    assert items["tensor.carrera"].estado == OK
    assert items["tensor.agarre"].estado == NO_APLICA  # tornillo integrado en la unidad


def test_metadato_tensores_declarado():
    doc = _faja()
    doc.tensores = validar_tensores([{"piezas": ["c1_tambor_cola"], "carrera_mm": 150,
                                      "eje": "x", "nota": "carro tensor a medida"}])
    (lz,) = lazos(doc)
    assert lz["tensores"][0]["tipo"] == "declarado"
    assert _items(doc)["tensor.carrera"].estado == OK
    # viaja en el manifest
    otra = Document.from_apolo_bytes(doc.to_apolo_bytes())
    assert otra.tensores == doc.tensores


@pytest.mark.parametrize(("valor", "texto"), [
    ({"piezas": ["a"]}, "lista"),
    ([{"piezas": [], "carrera_mm": 10, "eje": "x"}], "piezas"),
    ([{"piezas": ["a"], "carrera_mm": 0, "eje": "x"}], "> 0"),
    ([{"piezas": ["a"], "carrera_mm": 10, "eje": "w"}], "eje"),
    ([{"piezas": ["a"], "carrera_mm": 10, "eje": "x", "otro": 1}], "no reconocida"),
])
def test_validar_tensores_rechaza_con_la_correccion(valor, texto):
    with pytest.raises(ValueError, match=texto):
        validar_tensores(valor)


def test_api_tensores_get_put():
    from apolo.api import main as api

    api.DOC = _faja()
    client = TestClient(api.app)
    assert client.get("/api/tensores").json() == {"tensores": []}
    r = client.put("/api/tensores", json={"tensores": [
        {"piezas": ["c1_tambor_cola"], "carrera_mm": 120, "eje": [1, 0, 0]}]})
    assert r.status_code == 200 and r.json()["tensores"][0]["eje"] == [1.0, 0.0, 0.0]
    assert client.get("/api/tensores").json()["tensores"][0]["carrera_mm"] == 120
    malo = client.put("/api/tensores", json={"tensores": [
        {"piezas": ["no-existe"], "carrera_mm": 120, "eje": "x"}]})
    assert malo.status_code == 400 and "no-existe" in malo.json()["detail"]
    assert api.DOC.tensores[0]["carrera_mm"] == 120  # el rechazo no tocó lo guardado


def test_cadenas_de_la_plantilla_de_rodillos():
    """La cadena motriz se tensa con las ranuras del portamotor (carrera de la plantilla); los
    lazos rodillo a rodillo, de centros fijos, no tienen tensor: SIN_EVALUAR."""
    doc = Document("rodillos")
    doc.execute("create_roller_conveyor", {"largo": 1000})
    por_id = {lz["id"]: lz for lz in lazos(doc)}
    motriz = por_id["c1_cad_m"]
    (t,) = motriz["tensores"]
    assert t["tipo"] == "plantilla"
    assert t["carrera_mm"] >= carrera_requerida("cadena", motriz["largo_mm"]) - 1e-6
    r = evaluar_lazo(motriz)
    assert r["carrera"][0] == OK and r["agarre"][0] == NO_APLICA
    otros = [lz for i, lz in por_id.items() if i != "c1_cad_m"]
    assert otros and all(not lz["tensores"] for lz in otros)
    assert _items(doc)["tensor.reconocido"].estado == SIN_EVALUAR


def _perno_tensor(largo: float) -> dict:
    """Insumo de un perno tensor que cruza aleta (6–15,5), eje roscado (27,5–62,5) y aleta
    (74,5–84) — la geometría del take-up de serie."""
    tramos = [{"fid": "sop", "nombre": "Soporte en C", "t0": 6.0, "t1": 15.5, "rol": "pieza",
               "material": "acero", "rosca": []},
              {"fid": "eje", "nombre": "Eje roscado", "t0": 27.5, "t1": 62.5, "rol": "pieza",
               "material": "acero", "rosca": [(27.5, 62.5)]},
              {"fid": "sop", "nombre": "Soporte en C", "t0": 74.5, "t1": 84.0, "rol": "pieza",
               "material": "acero", "rosca": []}]
    dentro = [t for t in tramos if t["t0"] < largo]
    return {"fid": "perno", "nombre": "Perno tensor", "ref": "PERNO-M16", "cabeza": "allen",
            "d": 16.0, "paso": 2.0, "largo": largo, "evaluable": True, "esperadas": [],
            "tramos": dentro, "mas_alla": [{"fid": t["fid"], "t0": t["t0"], "rol": "pieza"}
                                           for t in tramos if t["t0"] >= largo]}


def test_perno_tensor_que_pierde_el_agarre_en_un_extremo_de_la_carrera():
    bien = {"tipo": "take_up", "id": "t", "nombre": "t", "carrera_mm": 24,
            "pernos": [{"insumo": _perno_tensor(90), "movil": "eje", "antes": 12, "despues": 12}]}
    assert agarre_en_carrera(bien)[0] == OK
    # M16×40: cruza una sola aleta y, con el eje corrido hacia la punta, engancha 0,5 mm
    corto = {**bien, "pernos": [{**bien["pernos"][0], "insumo": _perno_tensor(40)}]}
    e, _txt, casos = agarre_en_carrera(corto)
    assert e == FALLA
    assert {c["extremo"] for c in casos} == {"hacia la cabeza", "hacia la punta"}
    assert any("engancha 0.5" in c["detalle"] for c in casos)


def test_sin_lazos_no_aplica():
    items = controlar_tensores([])
    assert {i.estado for i in items} == {NO_APLICA}


def test_requisitos_de_carrera():
    assert carrera_requerida("banda", 8000) == pytest.approx(100)
    assert carrera_requerida("cadena", 2000) == pytest.approx(30)


# ── la adherencia de Eytelwein ya no sale del NOMBRE de una pieza ───────────────────────


def test_eytelwein_lee_el_tensor_reconocido_no_el_nombre():
    doc = _faja()
    doc.execute("create_box", {"name": "Tensor de cola", "width": 50, "depth": 50,
                               "height": 50, "position": COLA})
    assert not tiene_tensor_reconocido(doc)
    conveyor = {"tipo": "banda"}
    inherit_tensor(doc, conveyor)
    assert conveyor["tiene_tensor"] is False
    doc.execute("create_take_up", {"position": COLA})
    assert tiene_tensor_reconocido(doc)
    assert [t["tipo"] for t in tensores_reconocidos(doc, medir=False)] == ["take_up"]
    explicito = {"tipo": "banda", "tiene_tensor": False}
    inherit_tensor(doc, explicito)
    assert explicito["tiene_tensor"] is False  # lo explícito del cliente gana
