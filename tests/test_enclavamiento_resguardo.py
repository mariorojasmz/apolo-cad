"""¿Entra la lengüeta en su interruptor de resguardo? (plan mandos-de-seguridad, F2b).

Dos máquinas modeladas por MCP el 2026-10-27 dejaron la lengüeta `RESG-LENGUETA` fuera de la
ranura del `RESG-2NC` con el resguardo cerrado (3,5 mm por encima; o en la boca, sin entrar) y el
ERC, la puerta de entrega y la FAT dieron verde. Aquí: el cálculo puro
(`library/enclavamiento.py`), la lectura del documento (`services/enclavamientos.py`) y su
sección en la puerta de entrega."""

import pytest

from apolo.doc import Document
from apolo.library import enclavamiento as E
from apolo.library.delivery import AMARILLO, ROJO, VERDE, delivery_report
from apolo.services.delivery_inputs import delivery_inputs
from apolo.services.enclavamientos import regla


def _mover(doc, fid, delta):
    cmd = next(c for c in doc.commands if c["id"] == doc.scene[fid].command_id)
    pos = dict(cmd["params"].get("position") or {})
    nuevo = {k: float(pos.get(k, 0.0)) + delta[i] for i, k in enumerate("xyz")}
    doc.edit(cmd["id"], {"position": nuevo}, merge=True)


def _poner(doc, cuerpo, lengueta, prof, dx=0.0):
    """Deja la punta de la lengüeta `prof` mm adentro de la boca (negativo: afuera) y `dx` mm
    corrida por el ancho de la ranura (el X del mundo con el interruptor sin girar)."""
    boca = doc.scene[cuerpo].anchors["ranura"]["origin"]
    punta = doc.scene[lengueta].anchors["punta"]["origin"]
    meta = (boca[0] + dx, boca[1], boca[2] - prof)  # la ranura entra por −Z
    _mover(doc, lengueta, [meta[i] - punta[i] for i in range(3)])


def _par(prof=14.0, dx=0.0, nombres=("Interruptor de tapa", "Lengüeta de tapa"), x0=0.0, doc=None):
    doc = doc or Document("enclavamiento")
    c = doc.execute("insert_component", {"component": "RESG-2NC", "name": nombres[0],
                                         "position": {"x": x0}})
    lg = doc.execute("insert_component", {"component": "RESG-LENGUETA", "name": nombres[1],
                                          "rotation": {"x": 180}})
    _poner(doc, c, lg, prof, dx)
    return doc, c, lg


def _estados(filas):
    return [f["estado"] for f in filas]


# ── el par sin junta ──────────────────────────────────────────────────────────────────────────


def test_bien_puesta_entra_y_sin_junta_la_apertura_no_aplica():
    doc, c, lg = _par(14.0)
    filas = regla(doc)
    assert _estados(filas) == ["ok", "no_aplica"]
    assert filas[0]["medida"]["profundidad_mm"] == pytest.approx(14.0, abs=0.01)
    assert filas[0]["medida"]["estado"] == E.INSERTADA
    assert "no tiene junta" in filas[1]["detalle"]


@pytest.mark.parametrize("prof, texto", [
    (-3.5, "3.5 mm fuera de la boca"),      # la de la noche: 3,5 mm por encima del cabezal
    (0.0, "en la boca de la ranura, sin entrar"),  # la otra: terminaba justo en la boca
    (8.0, "entra 8.0 mm de los 12 mm"),
    (17.0, "choca con el fondo"),
])
def test_con_el_resguardo_cerrado_la_lengueta_que_no_entra_es_rojo(prof, texto):
    doc, c, lg = _par(prof)
    filas = regla(doc)
    assert _estados(filas) == ["error"]
    assert texto in filas[0]["detalle"] and "no entra en la ranura" in filas[0]["detalle"]
    assert filas[0]["piezas"] == [c, lg]


def test_corrida_de_lado_no_cabe_aunque_entre_hondo():
    doc, _c, _lg = _par(14.0, dx=1.5)  # la holgura de ancho es ±1 mm (ranura 20, lengüeta 18)
    filas = regla(doc)
    assert _estados(filas) == ["error"] and "no cabe en la ranura" in filas[0]["detalle"]
    doc, _c, _lg = _par(14.0, dx=0.9)
    assert _estados(regla(doc))[0] == "ok"


def test_inclinada_lo_dicen_las_esquinas_de_la_boca():
    boca, ez, ex, ey = (0.0, 0.0, 0.0), (0.0, 0.0, -1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
    recta = ((0.0, 0.0, -14.0), ez, ex, (0.0, -1.0, 0.0))
    assert E.insercion((boca, ez, ex, ey), recta, 12)["estado"] == E.INSERTADA
    import math
    a = math.radians(5)  # 5° por el canto: la boca la corre 14·tan 5° = 1,2 mm > 0,5 de holgura
    t = (0.0, math.sin(a), -math.cos(a))
    inclinada = ((0.0, 0.0, -14.0), t, ex, (0.0, -math.cos(a), -math.sin(a)))
    assert E.insercion((boca, ez, ex, ey), inclinada, 12)["estado"] == E.DESALINEADA


# ── con la junta de la hoja ──────────────────────────────────────────────────────────────────


def test_con_junta_cerrada_entra_y_abierta_sale():
    doc, c, lg = _par(14.0)
    boca = doc.scene[c].anchors["ranura"]["origin"]
    doc.execute("add_joint", {"name": "j_tapa", "type": "giratoria", "parent": c, "child": lg,
                              "origin": {"x": 0, "y": boca[1] + 60, "z": boca[2] + 20},
                              "axis": {"x": 1}, "lower": 0, "upper": 90})
    filas = regla(doc)
    assert _estados(filas) == ["ok", "ok"]
    assert "abierto (junta j_tapa = 90)" in filas[1]["detalle"]


def test_modelada_abierta_vale_el_extremo_en_que_entra():
    doc, c, lg = _par(-30.0)  # la hoja dibujada abierta: la punta 30 mm sobre la boca
    doc.execute("add_joint", {"name": "j_hoja", "type": "prismatica", "parent": c, "child": lg,
                              "axis": {"z": -1}, "lower": 0, "upper": 44})
    filas = regla(doc)
    assert _estados(filas) == ["ok", "ok"]
    assert "(junta j_hoja = 44)" in filas[0]["detalle"] and "= 0" in filas[1]["detalle"]


def test_una_junta_que_no_la_saca_es_rojo():
    doc, c, lg = _par(14.0)
    doc.execute("add_joint", {"name": "j_mal", "type": "prismatica", "parent": c, "child": lg,
                              "axis": {"x": 1}, "lower": 0, "upper": 0.5})
    filas = regla(doc)
    assert _estados(filas) == ["ok", "error"]
    assert "sigue en la ranura" in filas[1]["detalle"]


def test_unida_a_la_hoja_que_gira_sin_colgar_de_su_junta_es_aviso():
    doc, c, lg = _par(14.0)
    hoja = doc.execute("create_box", {"name": "Tapa", "width": 60, "depth": 60, "height": 3,
                                      "position": {"z": doc.scene[lg].anchors["montaje"]["origin"][2] + 1.5}})
    doc.execute("add_joint", {"name": "j_tapa", "type": "giratoria", "parent": c, "child": hoja,
                              "axis": {"x": 1}, "lower": 0, "upper": 90})
    doc.execute("fasten", {"name": "f_lengueta", "a": lg, "b": hoja})
    filas = regla(doc)
    assert _estados(filas) == ["ok", "aviso"]
    assert "no cuelga de ella" in filas[1]["detalle"] and "j_tapa" in filas[1]["detalle"]


# ── emparejamiento ───────────────────────────────────────────────────────────────────────────


def test_sin_lengueta_modelada_es_aviso_y_sin_resguardos_no_hay_seccion():
    doc = Document("solo-cuerpo")
    c = doc.execute("insert_component", {"component": "RESG-2NC"})
    filas = regla(doc)
    assert _estados(filas) == ["aviso"] and "no tiene su lengüeta RESG-LENGUETA" in filas[0]["detalle"]
    assert filas[0]["piezas"] == [c]
    vacio = Document("sin-resguardo")
    vacio.execute("create_box", {"width": 10, "depth": 10, "height": 10})
    assert regla(vacio) is None
    assert "enclavamientos" not in delivery_inputs(vacio, expand=lambda ids: ids)


def test_dos_pares_cerca_sin_designacion_avisan_y_con_ella_no():
    doc, c1, l1 = _par(14.0)
    doc, c2, l2 = _par(14.0, x0=30.0, doc=doc)
    _poner(doc, c2, l2, 14.0)
    filas = regla(doc)
    assert _estados(filas) == ["ok", "no_aplica", "ok", "no_aplica", "aviso"]
    assert {(f["piezas"][0], f["piezas"][1]) for f in filas[:4]} == {(c1, l1), (c2, l2)}
    assert "emparejamiento ambiguo" in filas[-1]["detalle"]
    doc, c1, l1 = _par(14.0, nombres=("Interruptor -B1", "Lengüeta -B1"))
    doc, c2, l2 = _par(14.0, nombres=("Interruptor -B2", "Lengüeta -B2"), x0=30.0, doc=doc)
    _poner(doc, c2, l2, 14.0)
    assert "aviso" not in _estados(regla(doc))


def test_la_designacion_gana_a_la_cercania():
    # la lengüeta «-B2» quedó en la ranura de -B1: el par por designación la juzga contra -B2
    doc, c1, l_b2 = _par(14.0, nombres=("Interruptor -B1", "Lengüeta -B2"))
    doc, c2, l_b1 = _par(14.0, nombres=("Interruptor -B2", "Lengüeta -B1"), x0=200.0, doc=doc)
    _poner(doc, c2, l_b1, 14.0)
    filas = regla(doc)
    assert [f["estado"] for f in filas if f["piezas"][:2] == [c1, l_b1]] == ["error"]
    assert [f["estado"] for f in filas if f["piezas"][:2] == [c2, l_b2]] == ["error"]


# ── en la puerta de entrega ──────────────────────────────────────────────────────────────────


def _reporte(**kw):
    base = dict(n_solidos=2, interferencias=[], soundness={"has_ground": False}, lints=[],
                integridad=[], suprimidos=[], poses=None, gravedad=None)
    return delivery_report(**{**base, **kw})


def test_la_puerta_bloquea_lo_que_no_entra_y_declara_lo_que_no_verifica():
    sin = _reporte()
    assert not any("enclavamiento" in x for x in sin["resumen"]["chequeos_ok"] + sin["no_aplica"])
    doc, _c, _lg = _par(-3.5)
    mal = _reporte(enclavamientos=regla(doc))
    assert mal["veredicto"] == ROJO
    assert [b["regla"] for b in mal["bloqueantes"]] == ["enclavamiento del resguardo"]
    doc, _c, _lg = _par(14.0)
    bien = _reporte(enclavamientos=regla(doc))
    assert bien["veredicto"] == VERDE
    assert "enclavamiento del resguardo (1 interruptor(es), la lengüeta entra)" in bien["resumen"]["chequeos_ok"]
    assert any(x.startswith("enclavamiento del resguardo:") for x in bien["no_aplica"])
    solo = Document("solo")
    solo.execute("insert_component", {"component": "RESG-2NC"})
    assert _reporte(enclavamientos=regla(solo))["veredicto"] == AMARILLO


def test_la_apertura_sin_junta_se_justifica_por_escrito_en_la_puerta():
    """Defecto sembrado de `entrega.no_evaluado` (puerta-sin-sobrediseno F3d): la lengüeta en una
    pieza suelta (sin junta) deja la apertura sin verificar; la puerta de publicación lo pide
    verificado o justificado, por la regla o por el par interruptor + lengüeta."""
    from apolo.library.calidad.item import OK, SIN_EVALUAR
    from apolo.library.calidad.justificadas import validar_justificadas
    from apolo.library.calidad.puerta import no_aplica_justificado

    doc, c, lg = _par(14.0)
    rep = _reporte(enclavamientos=regla(doc))
    assert rep["no_aplica_piezas"] == [{"no_aplica": rep["no_aplica"][-1],
                                        "regla": "enclavamiento del resguardo", "piezas": [c, lg]}]

    def item(js):
        hechos = {"pocos_solidos": True, "sin_estudios": True}  # lo demás que no evaluó
        return no_aplica_justificado({"entrega": rep, "hechos": hechos,
                                      "justificadas": validar_justificadas(js)})

    porque = "la hoja es un aro suelto sin bisagra: la apertura la prueba la FAT"
    sin = item([])
    assert sin["estado"] == SIN_EVALUAR and sin["evidencia"]["sin_justificar"] == rep["no_aplica"][-1:]
    assert item([{"regla": "enclavamiento del resguardo", "porque": porque}])["estado"] == OK
    par = [{"regla": "enclavamiento del resguardo", "pieza": x, "porque": porque} for x in (c, lg)]
    assert item(par)["estado"] == OK and item(par[:1])["estado"] == SIN_EVALUAR
    assert "no_aplica_piezas" not in _reporte(enclavamientos=regla(_par(-3.5)[0]))


def test_delivery_inputs_lleva_la_seccion_con_resguardos():
    doc, _c, _lg = _par(0.0)
    kw = delivery_inputs(doc, expand=lambda ids: ids)
    assert _estados(kw["enclavamientos"]) == ["error"]
    assert delivery_report(**kw)["veredicto"] == ROJO
