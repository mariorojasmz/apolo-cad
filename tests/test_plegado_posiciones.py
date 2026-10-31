"""Lo plegable se pliega en el MODELO (plan plegables-en-la-puerta, F1: D1–D3 con su F0).

- D1: el requisito `plegable` (sí/no) y `espesor_plegado_mm`; la ficha lo pregunta aparte de
  `desarmable`.
- D2: el fotograma acepta `posicion: "uso" | "guardado"` y sigue rechazando lo demás; un manifest
  viejo sin ella abre igual. Con `plegable`, `plegado.posiciones` pide un estudio con las dos, todo
  dentro de los límites y al menos una junta que cambie: la silla sin juntas FALLA.
- D3: la caja del guardado contra `espesor_plegado_mm` (`plegado.espesor`) y el TRÁNSITO uso →
  guardado en `delivery_check`: AVISO con un choque NUEVO, nada con los de la pose de diseño.

Fixture sintética: un asiento (raíz) con una pata que se pliega 85° alrededor de un eje de
bisagra en Y; el eje (fijo al asiento) atraviesa la pata por diseño y gira coaxial con ella: su
solape no cambia al plegar."""

from __future__ import annotations

import pytest

import apolo.services.puerta_publicacion as pp
from apolo.doc import Document
from apolo.doc.errors import DocumentError
from apolo.library.calidad.item import FALLA, NO_APLICA, OK, SIN_EVALUAR
from apolo.library.calidad.plegado import REGLA_TRANSITO, espesor, posiciones, regla_entrega
from apolo.library.calidad.registro import VERSION_REGISTRO, evaluar
from apolo.library.delivery import AMARILLO, delivery_report
from apolo.library.requisitos import FICHA, es_plegable, espesor_plegado, normalizar_requisitos
from apolo.services.calidad_plegado import plegado, transito
from apolo.services.delivery_inputs import delivery_inputs

Y = {"x": 0, "y": 1, "z": 0}
BISAGRA = {"x": -185, "y": 0, "z": 410}
USO = {"t": 0, "values": {"j_pata": 0}, "posicion": "uso"}
GUARDADO = {"t": 1, "values": {"j_pata": -85}, "posicion": "guardado"}


def _silla(juntas: bool = True) -> tuple[Document, dict]:
    doc = Document("silla")
    asiento = doc.execute("create_box", {"name": "Asiento", "width": 400, "depth": 400,
                                         "height": 20, "position": {"z": 450}})
    pata = doc.execute("create_box", {"name": "Pata", "width": 30, "depth": 30, "height": 420,
                                      "position": {"x": -185, "z": 210}})
    eje = doc.execute("create_cylinder", {"name": "Eje de la bisagra", "radius": 5, "height": 50,
                                          "position": BISAGRA, "rotation": {"x": 90}})
    if juntas:
        doc.execute("add_joint", {"name": "j_pata", "type": "giratoria", "parent": asiento,
                                  "child": pata, "origin": BISAGRA, "axis": Y,
                                  "lower": -100, "upper": 0})
    return doc, {"asiento": asiento, "pata": pata, "eje": eje}


def _plegable(doc, **extra) -> None:
    doc.set_requirements({**(doc.requirements or {}), "plegable": True, **extra})


# ------------------------------------------------------------------ D1: los requisitos
def test_el_requisito_plegable_se_valida_y_va_en_la_ficha_aparte_de_desarmable():
    assert normalizar_requisitos({"plegable": "sí", "espesor_plegado_mm": "80"}) == {
        "plegable": True, "espesor_plegado_mm": 80.0}
    with pytest.raises(ValueError, match="plegable"):
        normalizar_requisitos({"plegable": "a veces"})
    with pytest.raises(ValueError, match="espesor_plegado_mm"):
        normalizar_requisitos({"espesor_plegado_mm": 0})
    assert "plegable" in FICHA and "desarmable" in FICHA
    assert not es_plegable({}) and not es_plegable({"desarmable": True})
    assert es_plegable({"plegable": "Sí"}) and espesor_plegado({"espesor_plegado_mm": 80.0}) == 80.0
    assert espesor_plegado({"espesor_plegado_mm": "ancho"}) is None  # tolerante como la carga


# ------------------------------------------------------------------ D2: el fotograma
def test_set_motion_acepta_posicion_y_sigue_rechazando_lo_demas():
    doc, _ = _silla()
    doc.set_motion("plegado", [GUARDADO, USO])
    assert doc.motion["plegado"] == [USO, GUARDADO]  # ordenado por t, con su etiqueta
    with pytest.raises(DocumentError, match="Claves desconocidas"):
        doc.set_motion("x", [{"t": 0, "values": {"j_pata": 0}, "etiqueta": "uso"}])
    with pytest.raises(DocumentError, match="posicion"):
        doc.set_motion("x", [{"t": 0, "values": {"j_pata": 0}, "posicion": "abierto"}])
    with pytest.raises(DocumentError, match="UN solo fotograma"):
        doc.set_motion("x", [USO, {**GUARDADO, "posicion": "uso"}])
    # sin etiqueta, como siempre
    doc.set_motion("viejo", [{"t": 0, "values": {"j_pata": 0}}, {"t": 1, "values": {"j_pata": -10}}])
    assert all("posicion" not in kf for kf in doc.motion["viejo"])


def test_un_manifest_viejo_sin_posicion_abre_igual_y_la_posicion_viaja_en_el_apolo():
    doc, _ = _silla()
    doc.set_motion("viejo", [{"t": 0, "values": {"j_pata": 0}}, {"t": 1, "values": {"j_pata": -10}}])
    doc.set_motion("plegado", [USO, GUARDADO])
    doc2 = Document.from_apolo_bytes(doc.to_apolo_bytes())
    assert doc2.motion == doc.motion
    assert doc2.motion["viejo"][1] == {"t": 1.0, "values": {"j_pata": -10.0}}


# ------------------------------------------------------------------ D2: plegado.posiciones
def test_sin_el_requisito_no_se_mide():
    doc, _ = _silla(juntas=False)
    assert plegado(doc) is None and transito(doc) is None


def test_la_silla_sin_juntas_con_plegable_falla():
    doc, _ = _silla(juntas=False)
    _plegable(doc)
    r = posiciones({"plegado": plegado(doc)})
    assert r["estado"] == FALLA and "se pliega en la ficha y no en el modelo" in r["detalle"]
    assert "no tiene juntas" in r["detalle"]


@pytest.mark.parametrize("estudio, motivo", [
    ([{"t": 0, "values": {"j_pata": 0}}, {"t": 1, "values": {"j_pata": -85}}], "sin el fotograma"),
    ([USO, {**GUARDADO, "values": {"j_pata": -120}}], "fuera de los límites"),
    ([USO, {**GUARDADO, "values": {"j_pata": 0}}, {"t": 2, "values": {"j_pata": -5}}],
     "ninguna junta cambia"),
])
def test_un_estudio_sin_las_dos_posiciones_validas_falla(estudio, motivo):
    doc, _ = _silla()
    _plegable(doc)
    doc.set_motion("plegado", estudio)
    r = posiciones({"plegado": plegado(doc)})
    assert r["estado"] == FALLA and motivo in r["detalle"], r["detalle"]


def test_con_el_estudio_uso_guardado_ok_y_publica_la_caja_del_guardado():
    doc, _ = _silla()
    _plegable(doc)
    doc.set_motion("plegado", [USO, GUARDADO])
    ins = plegado(doc)
    r = posiciones({"plegado": ins})
    assert r["estado"] == OK and "j_pata" in r["detalle"], r["detalle"]
    caja = r["evidencia"]["caja_guardado"]
    assert caja["estudio"] == "plegado" and caja["t"] == 1.0
    # plegada, la pata queda casi horizontal bajo el asiento: la caja es baja (en uso, 460 mm)
    assert caja["dims_mm"][0] < 120 and caja["dims_mm"] == sorted(caja["dims_mm"]), caja


def test_el_espesor_del_guardado_mayor_que_lo_pedido_falla():
    doc, _ = _silla()
    _plegable(doc, espesor_plegado_mm=40)
    doc.set_motion("plegado", [USO, GUARDADO])
    r = espesor({"plegado": plegado(doc)})
    assert r["estado"] == FALLA and "el encargo pide ≤ 40" in r["detalle"], r["detalle"]
    _plegable(doc, espesor_plegado_mm=150)
    r = espesor({"plegado": plegado(doc)})
    assert r["estado"] == OK and r["evidencia"]["espesor_medido_mm"] < 150
    doc.set_motion("plegado", [])  # sin guardado válido no se mide: SIN_EVALUAR, nunca OK
    assert espesor({"plegado": plegado(doc)})["estado"] == SIN_EVALUAR


def test_la_puerta_publica_los_dos_items_solo_con_el_requisito():
    doc, _ = _silla()
    doc.set_motion("plegado", [USO, GUARDADO])

    def items():
        ins = pp.reunir(doc, expand=lambda x: x, gravedad={"resultado": None, "motivo": ""},
                        sobrantes=False)
        r = evaluar(ins)
        assert int(r["version_registro"]) >= 38 and r["version_registro"] == VERSION_REGISTRO  # la F1 la subió a 38
        assert "transito" not in r["tiempos_s"] and "entrega.transito" not in r["tiempos_s"]
        return {i["id"]: i for i in r["items"]}

    it = items()
    assert it["plegado.posiciones"]["estado"] == NO_APLICA
    assert "plegable" in it["plegado.posiciones"]["detalle"]
    assert it["plegado.espesor"]["estado"] == NO_APLICA
    _plegable(doc)
    it = items()
    assert it["plegado.posiciones"]["estado"] == OK
    assert it["plegado.espesor"]["estado"] == NO_APLICA  # sin espesor pedido
    _plegable(doc, espesor_plegado_mm=40)
    assert items()["plegado.espesor"]["estado"] == FALLA


# ------------------------------------------------------------------ D3: el tránsito
def test_el_transito_con_solo_los_choques_de_diseno_no_avisa():
    """El eje atraviesa la pata por diseño y gira coaxial con ella: su solape no crece."""
    doc, ids = _silla()
    _plegable(doc)
    doc.set_motion("plegado", [USO, GUARDADO])
    tr = transito(doc)
    assert tr["choques"] == [] and tr["pasos"] == 6 and tr["estudio"] == "plegado", tr
    fila = regla_entrega(tr)
    assert fila["estado"] == "ok" and "sin choques nuevos" in fila["detalle"]
    kw = delivery_inputs(doc, expand=lambda x: x)
    assert kw["transito"]["choques"] == []
    rep = delivery_report(**kw)
    assert not any(a["regla"] == REGLA_TRANSITO for a in rep["avisos"])
    assert any("tránsito del plegado" in o for o in rep["resumen"]["chequeos_ok"])


def test_el_transito_con_un_choque_nuevo_da_aviso():
    """Un travesaño fijo a media carrera de la pata: no toca en uso ni en guardado (las poses de
    reposo pasan), sólo al plegar."""
    from apolo.robotics.pose import posed_shapes

    doc, ids = _silla()
    _plegable(doc)
    doc.set_motion("plegado", [USO, GUARDADO])
    medio = posed_shapes(doc, {"j_pata": -42.5})[0][ids["pata"]].bounding_box().center()
    trav = doc.execute("create_box", {"name": "Travesaño", "width": 20, "depth": 60, "height": 20,
                                      "position": {"x": medio.X, "y": 0, "z": medio.Z}})
    tr = transito(doc)
    assert tr["choques"], tr
    c = tr["choques"][0]
    assert {c["a"], c["b"]} == {ids["pata"], trav} and c["diseno_mm3"] == 0.0
    assert 0 < c["t"] < 1 and c["volumen_mm3"] > 50
    kw = delivery_inputs(doc, expand=lambda x: x)
    rep = delivery_report(**kw)
    (aviso,) = [a for a in rep["avisos"] if a["regla"] == REGLA_TRANSITO]
    assert "choque(s) nuevo(s) al plegar" in aviso["detalle"] and rep["veredicto"] != "VERDE"
    assert not any(b["regla"] == REGLA_TRANSITO for b in rep["bloqueantes"])
    # la puerta de publicación no recorre el tránsito
    assert "transito" not in delivery_inputs(doc, expand=lambda x: x, transito=False)


def test_el_aviso_del_transito_es_amarillo_por_si_solo():
    fila = {"estudio": "plegado", "desde_t": 0.0, "hasta_t": 1.0, "pasos": 6,
            "choques": [{"t": 0.5, "a": "c2", "b": "c4", "nombre_a": "Pata",
                         "nombre_b": "Travesaño", "volumen_mm3": 900.0, "diseno_mm3": 0.0}]}
    base = dict(n_solidos=1, interferencias=[], soundness={"has_ground": False}, lints=[],
                integridad=[], suprimidos=[], poses=None)
    assert delivery_report(**base)["veredicto"] == "VERDE"
    rep = delivery_report(**base, transito=fila)
    assert rep["veredicto"] == AMARILLO and rep["avisos"][0]["piezas"] == ["c2", "c4"]
    err = delivery_report(**base, transito={"estudio": "plegado", "error": "OCCT"})
    assert err["veredicto"] == AMARILLO and "SIN verificar" in err["avisos"][0]["detalle"]
