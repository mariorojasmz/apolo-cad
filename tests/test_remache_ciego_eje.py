"""Un remache ciego no es eje de giro (plan plegables-en-la-puerta, F4 / D7): la mesa plegable de
1,8 m (re-revisión 2, MEDIA) pivotaba el compás en remaches ciegos DIN 7337, que prensan las
chapas (la articulación queda dura o, floja, se ovaliza). `agarre.retencion` lo falla con la
salida de mercado; el perno de hombro con tuerca autoblocante pasa. Vale para todo eje de junta."""

from __future__ import annotations

import pytest

from apolo.doc import Document
from apolo.library import ejes_giro as E
from apolo.library.calidad.agarre import controlar_agarre
from apolo.library.calidad.item import FALLA, OK
from apolo.services.calidad_ejes_giro import marcar_ejes
from apolo.services.calidad_pernos import _Escena, insumos_pernos


def _retencion(doc):
    esc = _Escena(doc.scene)
    pernos = insumos_pernos(doc, escena=esc)
    pasadores = marcar_ejes(doc, pernos, esc)
    return pernos, pasadores, {i.id: i for i in controlar_agarre(pernos, pasadores)}[
        "agarre.retencion"]


def _pivote(doc) -> tuple[str, str]:
    """Dos chapas de 4 mm con un agujero Ø5 en z, y la junta de giro en ese eje."""
    a = doc.execute("create_box", {"name": "Brazo fijo", "width": 120, "depth": 80, "height": 4,
                                   "position": {"z": 2}})
    b = doc.execute("create_box", {"name": "Brazo que gira", "width": 120, "depth": 80,
                                   "height": 4, "position": {"z": 6}})
    for f in (a, b):
        doc.execute("drill_hole", {"feature": f, "position": {"z": 20}, "axis": "-z",
                                   "diameter": 5})
    doc.execute("add_joint", {"name": "pivote", "type": "giratoria", "parent": a, "child": b,
                              "origin": {"x": 0, "y": 0, "z": 0}, "axis": {"x": 0, "y": 0, "z": 1}})
    return a, b


@pytest.mark.parametrize("como", ["a medida", "catálogo"])
def test_remache_ciego_como_eje_falla_con_la_salida_de_mercado(como):
    doc = Document("remache")
    _pivote(doc)
    if como == "a medida":  # el nombre real de la mesa de 1,8 m
        rem = doc.execute("create_cylinder", {"name": "Remache ciego 4,8x10 DIN 7337",
                                              "radius": 2.4, "height": 10, "position": {"z": 4}})
    else:
        rem = doc.execute("insert_component", {"component": "REMACHE-4.8", "position": {"z": 4}})
    pernos, (p,), it = _retencion(doc)
    assert pernos == [] and p["fid"] == rem and p["remache_ciego"] and p["giro"]["junta"] == "pivote"
    assert it.estado == FALLA and it.piezas == [rem]
    (caso,) = it.evidencia["casos"]
    txt = caso["detalle"]
    assert "remache ciego" in txt and "remache de hombro" in txt and "ISO 7379" in txt, txt
    assert "autoblocante" in txt


def test_remache_ciego_con_reten_sigue_fallando():
    """Un anillo o una tuerca no lo vuelven pivote: el remache prensa igual."""
    doc = Document("remache-reten")
    _pivote(doc)
    doc.execute("create_cylinder", {"name": "Remache pop Ø4,8 DIN 7337", "radius": 2.4,
                                    "height": 10, "position": {"z": 4}})
    doc.execute("create_box", {"name": "Anillo de retención DIN 6799 Ø4", "width": 8, "depth": 8,
                               "height": 0.6, "position": {"z": -0.4}})
    assert _retencion(doc)[2].estado == FALLA


def test_perno_de_hombro_con_autoblocante_pasa():
    """La salida de mercado: perno ISO 7379 con tuerca autoblocante (join_bolted din985 pone el
    perno pasante con su DIN 985: el mismo veredicto que el de hombro)."""
    doc = Document("hombro")
    a = doc.execute("create_box", {"name": "Brazo fijo", "width": 120, "depth": 80, "height": 10,
                                   "position": {"z": 5}})
    b = doc.execute("create_box", {"name": "Brazo que gira", "width": 120, "depth": 80,
                                   "height": 8, "position": {"z": 14}})
    doc.execute("join_bolted", {"a": a, "b": b, "size": "M10", "count": 1, "tuerca": "din985"})
    (p,) = insumos_pernos(doc)
    o = p["eje"]["asiento"]
    doc.execute("add_joint", {"name": "pivote", "type": "giratoria", "parent": a, "child": b,
                              "origin": {"x": o[0], "y": o[1], "z": o[2]},
                              "axis": {"x": 0, "y": 0, "z": 1}})
    pid = p["fid"]
    doc.scene[pid].name = "Perno de hombro ISO 7379 Ø10"
    (p,), pasadores, it = _retencion(doc)
    assert pasadores == [] and p["giro"] == {"junta": "pivote"}
    assert it.estado == OK, it.evidencia


@pytest.mark.parametrize(("nombre", "es"), [
    ("Remache ciego 4,8x10 DIN 7337", True),
    ("Remache ciego 4,8x12 DIN 7337 (rodilla)", True),
    ("Compás · Remache pop Ø4", True),
    ("Remache ISO 15977 4,8x10", True),
    ("Blind rivet 4.8x10", True),
    ("Remache de hombro Ø6x8 (pivote)", False),     # la salida de mercado
    ("Remache macizo DIN 660 Ø5", False),
    ("Remache-tuerca M6 DIN 7337", False),            # inserto roscado, no remache ciego
    ("Placa del remache ciego", False),               # sólo lo menciona
    ("Perno de hombro ISO 7379 Ø8", False),
])
def test_remache_ciego_por_rol(nombre, es):
    assert E.es_remache_ciego(nombre) is es


def test_remache_ciego_por_ficha():
    assert E.es_remache_ciego(None, {"herramienta": "remachadora"})
    assert E.es_remache_ciego(None, {"tipo": "remache ciego"})
    assert not E.es_remache_ciego(None, {"tipo": "perno hexagonal"})
