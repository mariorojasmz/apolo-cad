"""`movimiento.coherente` (plan lo-fijo-que-gira-y-lo-que-cuelga F1, D1 y D1a–D1d de su F0): una
unión rígida no une dos piezas que se mueven distinto. El control puro sobre insumos sintéticos
(cada rama, en orden) y la medida sobre la ménsula atornillada con sus defectos sembrados (el caso
básico y el hueco de la brida cara a cara)."""

from __future__ import annotations

from pathlib import Path

from test_defectos_sembrados import _id, brazo_fijo_que_gira, brida_cara_a_cara

from apolo.doc import Document
from apolo.library.calidad.item import FALLA, OK, SIN_EVALUAR
from apolo.library.calidad.movimiento import REGLA_AVISO, coherente, juzgar
from apolo.services.calidad_movimiento import movimiento
from apolo.services.delivery_inputs import uniones_entre_juntas

TESTIGOS = Path(__file__).resolve().parent / "data" / "testigos"


def _base() -> Document:
    return Document.from_apolo_bytes((TESTIGOS / "mensula_atornillada.apolo").read_bytes())


def _pose(sigue: bool, d1: float = 0.0, c1: float = 0.0) -> dict:
    return {"dist_diseno_mm": 0.0, "comun_diseno_mm3": 0.0, "sigue": sigue,
            "poses": [{"junta": "j", "valor": 3.0, "dist_mm": d1, "comun_mm3": c1, "sigue": sigue,
                       "solapa": c1 > 5.0}]}


def _caso(**kw) -> dict:
    c = {"a": "c1", "b": "c2", "nombre_a": "Pieza que gira", "nombre_b": "Soporte",
         "uniones": ["f1"], "tipos": ["perno"], "par_de_junta": None, "juntas": ["j"],
         "quietas": ["c2"], "coaxial_mueve": [], "coaxial_quieta": [], "servicio": False,
         "pose": _pose(False, c1=600.0), "eje": None}
    c.update(kw)
    return c


# ------------------------------------------------------------------ el control, rama por rama
def test_el_eje_de_la_junta_es_el_pivote():
    assert juzgar(_caso(eje="j"))[0] == OK


def test_las_dos_coaxiales_son_una_bisagra_d1b():
    e, m = juzgar(_caso(coaxial_mueve=["c1"], coaxial_quieta=["c2"]))
    assert e == OK and m.startswith("bisagra")


def test_el_alojamiento_arrastrado_falla_aunque_la_pose_pase_d1d():
    e, m = juzgar(_caso(coaxial_mueve=["c1"], pose=_pose(True)))
    assert e == FALLA and m.startswith("alojamiento arrastrado")
    # la coaxial que gira unida a otra que también se mueve: decide la pose
    assert juzgar(_caso(coaxial_mueve=["c1"], quietas=[], pose=_pose(True)))[0] == OK


def test_la_pose_relativa_decide_d1a():
    assert juzgar(_caso(pose=_pose(True)))[0] == OK
    e, m = juzgar(_caso())
    assert e == FALLA and "de 0 a 600" in m
    assert juzgar(_caso(pose=None))[0] == SIN_EVALUAR


def test_en_junta_de_servicio_separar_o_la_bisagra_quieta_son_aviso_d1c():
    separa = _pose(False, d1=2.96)  # el compás de la mesa plegable, el aro del recipiente
    assert juzgar(_caso(servicio=True, pose=separa))[0] == "aviso"
    assert juzgar(_caso(servicio=True, coaxial_quieta=["c2"]))[0] == "aviso"  # bisagra de 1 pieza
    # servicio y la pose la mete en la otra: el resorte quieto empernado a la puerta que abre
    e, m = juzgar(_caso(servicio=True))
    assert e == FALLA and m.startswith("una pieza unida rígida"), m
    # accionada: falla aunque sólo las separe (el motor arrancaría la unión)
    assert juzgar(_caso(pose=separa))[0] == FALLA


def test_el_aviso_bloquea_hasta_justificarlo_por_escrito():
    caso = _caso(servicio=True, pose=_pose(False, d1=2.96))
    ins = {"movimiento": {"juntas": {"giratoria": 1}, "casos": [caso]}, "justificadas": []}
    r = coherente(ins)
    assert r["estado"] == SIN_EVALUAR and r["evidencia"]["avisos"][0]["regla"] == REGLA_AVISO
    ins["justificadas"] = [{"regla": REGLA_AVISO, "porque": "el compás cierra el lazo de la "
                            "rodilla: su perno es el pivote que la FK no representa"}]
    r = coherente(ins)
    assert r["estado"] == OK and r["evidencia"]["justificadas"]


def test_sin_uniones_entre_juntas_pasa_y_sin_medir_no():
    r = coherente({"movimiento": {"juntas": {"continua": 2}, "casos": []}})
    assert r["estado"] == OK and "2 junta(s)" in r["detalle"]
    assert coherente({"movimiento": None})["estado"] == SIN_EVALUAR
    assert coherente({"movimiento": {"error": "x"}})["estado"] == SIN_EVALUAR


# ------------------------------------------------------------------ la medida, sobre la ménsula
def test_el_brazo_hijo_del_eje_empernado_a_la_placa_falla_por_la_pose():
    doc = _base()
    brazo_fijo_que_gira(doc)
    ins = movimiento(doc)
    (c,) = ins["casos"]
    assert c["juntas"] == ["giro_eje"] and c["quietas"] == [_id(doc, "Placa base")]
    assert c["servicio"] is False and c["pose"]["sigue"] is False
    e, m = juzgar(c)
    assert e == FALLA and m.startswith("una pieza unida rígida"), m
    r = coherente({"movimiento": ins})
    assert r["estado"] == FALLA and _id(doc, "Brazo") in r["piezas"]
    assert ins["juntas"] == {"continua": 1}


def test_la_brida_cara_a_cara_pasa_la_pose_y_falla_como_alojamiento_arrastrado():
    """El hueco de la F0: la pose sola la deja pasar; la firma coaxial la atrapa."""
    doc = _base()
    brida_cara_a_cara(doc)
    (c,) = movimiento(doc)["casos"]
    brida = _id(doc, "Chumacera de brida")
    assert c["pose"]["sigue"] is True, c["pose"]
    assert c["coaxial_mueve"] == [brida] and c["coaxial_quieta"] == []
    e, m = juzgar(c)
    assert e == FALLA and m.startswith("alojamiento arrastrado"), m


def test_sin_la_union_rigida_no_hay_caso():
    doc = _base()
    brazo_fijo_que_gira(doc)
    doc.remove_commands([doc.commands[-1]["id"]])  # sin el fasten
    assert movimiento(doc)["casos"] == []


def test_la_entrega_sigue_quitando_el_par_que_se_toca():
    """`uniones_entre_juntas` por defecto no cambia (lo-que-se-mueve D2): el par que se toca no
    destapa su choque en pose; sólo `tocan=False` lo deja (lo que juzga este ítem)."""
    doc = _base()
    brazo_fijo_que_gira(doc)
    par = frozenset((_id(doc, "Brazo"), _id(doc, "Placa base")))
    assert par not in uniones_entre_juntas(doc)
    assert par in uniones_entre_juntas(doc, tocan=False)
