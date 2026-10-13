"""`insert_project` trae el tablero del origen con el aspecto de función (plan V8.1 F3, D9).

Un layout con DOS fajas iguales: cada una trae su arranque directo con sus designaciones
prefijadas por el nombre de la instancia («=Faja1-Q1» y «=Faja2-Q1» conviven), su pieza ligada
con el prefijo de ids `{cmd}_{orig}` y sus `=expr` resueltos contra las variables del ORIGEN
con los `overrides` de cada instancia. El anfitrión puede cablear entre instancias con la
referencia completa; la corta es ambigua. Un layout insertado en otra planta anida el aspecto
(«=Linea.Faja1-Q1»).
"""

from __future__ import annotations

import pytest
from tablero_electrico import arranque_directo, no_ok

from apolo.doc.document import Document, DocumentError
from apolo.doc.geomcache import pack, unpack
from apolo.library.electrico.erc import erc


def _faja() -> tuple[Document, str]:
    """El origen: un motorreductor de catálogo + su tablero, la sección de mando por variable."""
    d = Document("faja con tablero")
    d.execute("set_variable", {"name": "S_MANDO", "expression": "0.75"})
    motor = d.execute("insert_component", {"component": "MOTOR-075", "name": "Motorreductor"})
    fid = next(f for f, feat in d.scene.items() if feat.command_id == motor)
    d.execute_many(arranque_directo(pieza_motor=fid, seccion_mando="=S_MANDO"))
    return d, fid


@pytest.fixture(scope="module")
def faja():
    return _faja()


def _layout(faja_bytes: bytes) -> tuple[Document, str, str]:
    lay = Document("layout")
    digest = lay.add_attachment(faja_bytes)
    c1 = lay.execute("insert_project", {"attachment": digest, "name": "Faja 1"})
    c2 = lay.execute("insert_project", {"attachment": digest, "name": "Faja2",
                                        "overrides": {"S_MANDO": 1},
                                        "position": {"x": 3000}})
    return lay, c1, c2


def _por_designacion(doc: Document) -> dict:
    return {d.designacion: d for d in doc.electrico.dispositivos}


def test_dos_fajas_traen_su_tablero_con_el_aspecto_de_funcion(faja):
    origen, fid = faja
    lay, c1, c2 = _layout(origen.to_apolo_bytes())
    disp = _por_designacion(lay)
    assert len(disp) == 28
    assert {"=Faja1-Q1", "=Faja2-Q1", "=Faja1-M1", "=Faja2-M1"} <= set(disp)
    # la pieza ligada sigue el prefijo de ids de la instancia y existe en la escena
    assert disp["=Faja1-M1"].pieza == f"{c1}_{fid}" and f"{c1}_{fid}" in lay.scene
    assert disp["=Faja2-M1"].pieza == f"{c2}_{fid}" and f"{c2}_{fid}" in lay.scene
    # ids de comando prefijados como las piezas; el `=S_MANDO` con el override de cada una
    assert disp["=Faja1-Q1"].id.startswith(f"{c1}_") and disp["=Faja2-Q1"].id.startswith(f"{c2}_")
    mando = {c.puntos[0].split("-")[0] + "-": c.seccion_mm2
             for c in lay.electrico.conductores if c.color == "BU"}
    assert mando == {"=Faja1-": 0.75, "=Faja2-": 1.0}
    # los conductores nombran los bornes con su aspecto
    assert ("=Faja1-G1:L1", "=Faja1-Q1:1") in [c.puntos for c in lay.electrico.conductores]
    reglas = erc(lay.electrico)
    assert not no_ok(reglas), no_ok(reglas)
    assert lay.regen_suppressed == [] and lay.check_integrity() == []


def test_el_anfitrion_cablea_entre_instancias_y_la_referencia_corta_es_ambigua(faja):
    lay, _, _ = _layout(faja[0].to_apolo_bytes())
    lay.execute("add_wire", {"puntos": ["=Faja1-X0:2", "=Faja2-X0:2"], "color": "GNYE"})
    assert not [r for r in erc(lay.electrico) if r["estado"] == "error"]
    with pytest.raises(DocumentError, match=r"es ambiguo: -Q1 existe como =Faja1-Q1, =Faja2-Q1"):
        lay.execute("add_wire", {"puntos": ["-Q1:2", "=Faja2-Q1:1"]})
    # y un dispositivo propio del anfitrión con la designación corta no choca
    lay.execute("add_device", {"ref": "ESTOP-40", "designacion": "-S0", "ubicacion": "+PUPITRE"})
    assert "-S0" in _por_designacion(lay) and "=Faja1-S0" in _por_designacion(lay)


def test_deshacer_el_insert_se_lleva_su_tablero_y_reabrir_lo_trae(faja):
    lay, _, c2 = _layout(faja[0].to_apolo_bytes())
    lay.undo()
    assert not any(d.startswith("=Faja2") for d in _por_designacion(lay))
    lay.redo()
    datos, warm = lay.to_apolo_bytes(), unpack(pack(lay))
    frio = Document.from_apolo_bytes(datos)
    caliente = Document.from_apolo_bytes(datos, warm=warm)
    assert frio.electrico == caliente.electrico == lay.electrico


def test_un_layout_insertado_anida_el_aspecto(faja):
    lay, _, _ = _layout(faja[0].to_apolo_bytes())
    planta = Document("planta")
    cid = planta.execute("insert_project", {"attachment": planta.add_attachment(lay.to_apolo_bytes()),
                                            "name": "Linea"})
    disp = _por_designacion(planta)
    assert {"=Linea.Faja1-Q1", "=Linea.Faja2-Q1"} <= set(disp) and len(disp) == 28
    assert disp["=Linea.Faja1-Q1"].id.startswith(f"{cid}_")
    assert not no_ok(erc(planta.electrico))
