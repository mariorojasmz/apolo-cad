"""`union.contacto_no_cuelga` (plan lo-fijo-que-gira-y-lo-que-cuelga F2, D2 y D2a–D2c de su F0): un
`contacto` no sostiene lo que cuelga. El control puro sobre insumos sintéticos (cada rama, en orden)
y la medida sobre la ménsula atornillada: la caja colgada bajo la placa (el defecto sembrado), la
apoyada encima, la de costado, la roscada declarada y lo que no se juzga."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_defectos_sembrados import _caja, _id, caja_colgada_de_un_contacto

from apolo.assembly.connectivity import build_graph
from apolo.doc import Document
from apolo.library.calidad.cuelga import REGLA_AVISO, juzgar, no_cuelga, traccion_declarada
from apolo.library.calidad.item import FALLA, OK, SIN_EVALUAR
from apolo.library.engineering.loads import hanging_load_kg, piezas_colgadas
from apolo.services.calidad_cuelga import cuelga, uniones_contacto

TESTIGOS = Path(__file__).resolve().parent / "data" / "testigos"


def _base() -> Document:
    return Document.from_apolo_bytes((TESTIGOS / "mensula_atornillada.apolo").read_bytes())


def _caso(cm, zona=(0.0, 0.0, 0.0, 100.0, 100.0, 10.0), **kw) -> dict:
    c = {"union": "f1", "colgada": "c9", "apoyo": "c1", "nombre_colgada": "Cuchilla",
         "nombre_apoyo": "Ducto", "piezas": 1, "kg": 22.1, "cm": list(cm),
         "zona": None if zona is None else list(zona), "traccion": False}
    c.update(kw)
    return c


# ------------------------------------------------------------------ el control, rama por rama
def test_cuelga_si_el_centro_de_masa_queda_bajo_la_zona_mas_que_la_tolerancia():
    e, m = juzgar(_caso((50, 50, -26)))
    assert e == FALLA and "26 mm bajo el contacto" in m, m
    assert juzgar(_caso((50, 50, -24)))[0] == "aviso"  # dentro de la tolerancia (D2b): costado


def test_apoya_si_el_centro_de_masa_esta_sobre_la_zona():
    assert juzgar(_caso((50, 50, 40)))[0] == OK
    assert juzgar(_caso((500, 50, 10)))[0] == OK  # sobre la cota más alta, aunque esté al lado


def test_la_zona_que_abraza_el_centro_de_masa_es_apoyo_d2b():
    e, m = juzgar(_caso((50, 50, 5)))  # una rueda en su eje, un resguardo en su boca
    assert e == OK and "abraza" in m
    assert juzgar(_caso((150, 50, 5)))[0] == "aviso"  # a su altura pero al costado


def test_la_union_de_tuberia_declarada_transmite_traccion_d2c():
    assert juzgar(_caso((50, 50, -300), traccion=True))[0] == OK
    # las notas REALES de la lavadora (válvula, unión americana, rebose y barras de rociado)
    for nota in ("valvula roscada 2in NPT en cupla soldada al fondo: se desenrosca para sacar",
                 "union americana 1/2in inox roscada BSP (no es perno)", "se enrosca a la cupla",
                 "rebose con abrazadera tri-clamp DIN 32676 2in + junta EPDM",
                 "abrazadera sanitaria ISO 2852 + junta EPDM", "NPT", "rosca BSP 1/2"):
        assert traccion_declarada(nota), nota
    # la abrazadera de ducto de las cuchillas (el defecto) no
    for nota in ("abrazadera de union rapida inox para ducto (anillo de cierre; no es perno)",
                 "abrazadera rápida", "", None, "Ø 12 mm"):
        assert not traccion_declarada(nota), nota


def test_sin_zona_no_se_pudo_medir():
    assert juzgar(_caso((50, 50, -300), zona=None))[0] == SIN_EVALUAR


def test_el_aviso_bloquea_hasta_justificarlo_por_escrito():
    ins = {"cuelga": {"contactos": 3, "casos": [_caso((150, 50, 5))]}, "justificadas": []}
    r = no_cuelga(ins)
    assert r["estado"] == SIN_EVALUAR and r["evidencia"]["avisos"][0]["regla"] == REGLA_AVISO
    ins["justificadas"] = [{"regla": REGLA_AVISO, "pieza": "c9",
                            "porque": "la barra entra roscada en el colector: la rosca la sostiene"}]
    r = no_cuelga(ins)
    assert r["estado"] == OK and r["evidencia"]["justificadas"]


def test_falla_nombra_lo_que_cuelga_y_como_corregir():
    r = no_cuelga({"cuelga": {"contactos": 2, "casos": [_caso((50, 50, -60)),
                                                        _caso((50, 50, 40), union="f2")]}})
    assert r["estado"] == FALLA and r["piezas"] == ["c9", "c1"]
    assert "Cuchilla (c9) de Ducto (c1)" in r["detalle"] and "apoyo" in r["detalle"]
    assert r["evidencia"]["con_carga"] == 2


def test_sin_casos_pasa_y_sin_medir_no():
    r = no_cuelga({"cuelga": {"contactos": 4, "casos": [], "no_juzgadas": {"tornilleria": 4}}})
    assert r["estado"] == OK and r["evidencia"]["no_juzgadas"] == {"tornilleria": 4}
    assert no_cuelga({"cuelga": None})["estado"] == SIN_EVALUAR
    assert no_cuelga({"cuelga": {"error": "x"}})["estado"] == SIN_EVALUAR


# ------------------------------------------------------------------ la medida, sobre la ménsula
def test_la_caja_colgada_bajo_la_placa_falla():
    doc = _base()
    caja_colgada_de_un_contacto(doc)
    ins = cuelga(doc)
    (c,) = ins["casos"]
    caja = _id(doc, "Caja colgada")
    assert c["colgada"] == caja and c["apoyo"] == _id(doc, "Placa base") and c["piezas"] == 1
    assert c["kg"] == pytest.approx(2.26, abs=0.05) and c["cm"][2] == pytest.approx(-40, abs=0.5)
    assert c["zona"][2] == pytest.approx(0, abs=0.5) and c["zona"][5] == pytest.approx(0, abs=0.5)
    r = no_cuelga({"cuelga": ins})
    assert r["estado"] == FALLA and caja in r["piezas"], r
    assert uniones_contacto(doc) == {"contacto": 1}


@pytest.mark.parametrize("como, estado", [
    ("encima", OK),       # una bandeja sobre sus zapatas: apoya
    ("costado", "aviso"),  # al costado de la placa, con el CM a la altura del contacto
    ("roscada", OK),      # bajo la placa, pero unión roscada declarada en la nota (D2c)
])
def test_apoya_costado_y_roscada(como, estado):
    doc = _base()
    if como == "encima":
        caja = _caja(doc, "Caja", 60, 60, 80, 100, 0, 52)
    elif como == "costado":
        caja = _caja(doc, "Caja", 60, 60, 80, 180, 0, 6)
    else:
        caja = _caja(doc, "Valvula de drenaje", 60, 60, 80, 100, 0, -40)
    doc.execute("fasten", {"name": "f_caja", "a": caja, "b": _id(doc, "Placa base"),
                           "kind": "contacto", "nota": "roscada 2in NPT" if como == "roscada"
                           else ""})
    (c,) = cuelga(doc)["casos"]
    assert juzgar(c)[0] == estado, (c, juzgar(c))
    if como == "roscada":
        assert c["traccion"] and c["zona"] is None  # no se mide la zona


def test_no_se_juzgan_la_tornilleria_lo_liviano_ni_el_par_con_otra_union():
    doc = _base()
    liviana = _caja(doc, "Placa de rotulo", 30, 30, 10, 100, 0, -5)  # 0,07 kg
    perno = _caja(doc, "Perno M12x80 DIN 933", 20, 20, 80, -100, 0, -40)
    doble = _caja(doc, "Soporte", 60, 60, 80, 0, 70, -40)
    for n, x in (("f1", liviana), ("f2", perno), ("f3", doble)):
        doc.execute("fasten", {"name": n, "a": x, "b": _id(doc, "Placa base"), "kind": "contacto"})
    doc.execute("fasten", {"name": "f4", "a": doble, "b": _id(doc, "Placa base"),
                           "kind": "soldadura"})
    ins = cuelga(doc)
    assert ins["casos"] == [] and ins["contactos"] == 3
    assert ins["no_juzgadas"] == {"liviana": 1, "tornilleria": 1, "con_otra_union": 1}


def test_piezas_colgadas_es_lo_que_pesa_hanging_load_kg():
    doc = _base()
    caja_colgada_de_un_contacto(doc)
    g = build_graph(doc.scene, doc.joints, doc.mates, doc.fasteners, doc.grounds)
    caja, placa = _id(doc, "Caja colgada"), _id(doc, "Placa base")
    assert piezas_colgadas(g, caja, placa) == {caja}
    assert hanging_load_kg(g, {caja: 2.0}, caja, placa) == 2.0
    assert piezas_colgadas(g, _id(doc, "Ménsula"), "nada") == set()  # arista que no existe
