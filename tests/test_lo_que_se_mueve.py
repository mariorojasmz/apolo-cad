"""Plan lo-que-se-mueve, D2: en una pose que no es la de diseño, el `fasten` entre piezas que
mueven juntas DISTINTAS deja de excluir su choque de la puerta de entrega. Una unión «artefacto»
(la plataforma del elevador «unida» a los tramos de cadena que atravesaba en la pose de +1500 mm)
deja ver el choque; un tope legítimo que toca en la pose de diseño y la bisagra que toca en todo el
recorrido siguen excluidos (no dan falso positivo); los `fasten` de un super-comando de cadena
también."""

from __future__ import annotations

from apolo.doc import Document
from apolo.library.delivery import delivery_report
from apolo.services.assertions import delivery_poses
from apolo.services.delivery_inputs import (
    delivery_inputs,
    exclusiones_declaradas,
    liberadas_en_pose,
    uniones_entre_juntas,
)


def _sin_grupos(x):
    return x


def _caja(d, nombre, w, dp, h, x=0.0, y=0.0, z=0.0) -> str:
    return d.execute("create_box", {"name": nombre, "width": w, "depth": dp, "height": h,
                                    "position": {"x": x, "y": y, "z": z}})


def _elevador(tope: bool = True) -> tuple[Document, dict]:
    """Un bastidor anclado, una plataforma que sube por una prismática en X (−50..50 en diseño) y
    un tramo de cadena FIJO en x = 270..330: en diseño no se tocan; a 300 mm la plataforma lo
    atraviesa. Y un tope fijo que solapa la plataforma 1 mm en diseño (su fin de carrera)."""
    d = Document()
    ids = {"base": _caja(d, "Bastidor", 100, 100, 100, z=-200),
           "plataforma": _caja(d, "Plataforma", 100, 60, 200),
           "tramo": _caja(d, "Tramo de cadena", 60, 60, 60, x=300)}
    if tope:
        ids["tope"] = _caja(d, "Tope de fin de carrera", 20, 60, 200, x=-59)
    d.execute("ground", {"name": "g", "feature": ids["base"]})
    d.execute("add_joint", {"name": "sube", "type": "prismatica", "parent": ids["base"],
                            "child": ids["plataforma"], "axis": {"x": 1}, "lower": 0,
                            "upper": 400})
    for k in ("tramo", "tope")[:2 if tope else 1]:
        d.execute("fasten", {"name": f"f_{k}", "a": ids[k], "b": ids["base"], "kind": "soldadura",
                             "throat_mm": 3, "length_mm": 50})
    d.set_motion("subir", [{"t": 0, "values": {"sube": 0}}, {"t": 1, "values": {"sube": 300}}])
    return d, ids


def _poses(d) -> list[dict]:
    pares, pernos = exclusiones_declaradas(d)
    return delivery_poses(d, pares, pernos, expand=_sin_grupos)


def _par(c) -> frozenset:
    return frozenset((c["a"], c["b"]))


def test_la_union_artefacto_ya_no_tapa_el_choque_en_la_pose():
    d, ids = _elevador(tope=False)
    choque = {ids["plataforma"], ids["tramo"]}
    (p,) = _poses(d)
    (c,) = p["colisiones"]  # sin la unión, el choque se ve (como siempre)
    assert _par(c) == choque and "union_declarada" not in c
    d.execute("fasten", {"name": "artefacto", "a": ids["plataforma"], "b": ids["tramo"],
                         "kind": "contacto"})
    (p,) = _poses(d)  # antes de D2 la unión lo tapaba: 0 colisiones
    (c,) = p["colisiones"]
    assert _par(c) == choque and c["volumen_mm3"] > 50
    assert c["union_declarada"] == "artefacto" and "juntas distintas" in c["porque"]
    rep = delivery_report(**delivery_inputs(d, expand=_sin_grupos), gravedad=None)
    b = next(b for b in rep["bloqueantes"] if b["regla"] == "colisión en pose declarada")
    assert "subir" in b["detalle"]
    # en la pose de diseño la unión sigue excluyendo el par (no se tocan: nada que excluir)
    assert not any(b["regla"] == "interferencias en diseño" for b in rep["bloqueantes"])


def test_el_tope_que_solo_toca_en_diseno_no_da_falso_positivo():
    d, ids = _elevador()
    d.execute("fasten", {"name": "tope", "a": ids["plataforma"], "b": ids["tope"],
                         "kind": "contacto"})
    assert uniones_entre_juntas(d) == {}  # se toca en diseño: su unión no es un artefacto
    # a 200 mm no llega al tramo de cadena (x ≥ 270): sólo cuenta el tope
    d.set_motion("subir", [{"t": 0, "values": {"sube": 0}}, {"t": 1, "values": {"sube": 200}}])
    ins = delivery_inputs(d, expand=_sin_grupos)
    assert ins["interferencias"] == []  # en diseño el solape del tope lo firma su unión
    (p,) = ins["poses"]
    assert p["colisiones"] == [] and "contactos_tolerados" not in p, p  # se separó del tope


def test_la_union_sigue_excluyendo_si_la_pose_no_mueve_sus_juntas():
    """Un estudio de DOS juntas: en la pose que sólo mueve la otra, el tope sigue tocando la
    plataforma como en diseño y su unión lo sigue firmando."""
    d, ids = _elevador()
    d.execute("fasten", {"name": "tope", "a": ids["plataforma"], "b": ids["tope"],
                         "kind": "contacto"})
    brazo = _caja(d, "Brazo", 40, 40, 100, x=0, y=400)
    d.execute("add_joint", {"name": "gira", "type": "giratoria", "parent": ids["base"],
                            "child": brazo, "axis": {"z": 1}, "lower": -90, "upper": 90})
    d.execute("fasten", {"name": "artefacto", "a": ids["plataforma"], "b": ids["tramo"],
                         "kind": "contacto"})
    uniones = uniones_entre_juntas(d)
    assert set(uniones) == {frozenset((ids["plataforma"], ids["tramo"]))}
    assert liberadas_en_pose(uniones, {"sube": 0, "gira": 30}) == set()
    assert liberadas_en_pose(uniones, {"sube": 300, "gira": 30}) == set(uniones)
    d.set_motion("subir", [{"t": 0, "values": {"sube": 0, "gira": 0}},
                           {"t": 1, "values": {"sube": 0, "gira": 30}}])
    (p,) = _poses(d)
    assert p["colisiones"] == [], p


def test_los_fasten_de_una_cadena_no_cuentan():
    """La cadena de `create_chain` se declara en contacto con sus piñones (`{id}_a`, `{id}_b`):
    el piñón gira con su junta y la cadena no tiene junta, pero esa unión no es rígida y sigue
    excluida en las poses."""
    d = Document()
    base = _caja(d, "Bastidor", 600, 40, 40, x=200, y=300, z=500)
    a, b = (d.execute("insert_component", {"component": "PINON-ASA40-1-Z15",
                                           "rotation": {"x": 90},
                                           "position": {"x": x, "y": 300, "z": 600}})
            for x in (0, 400))
    d.execute("add_joint", {"name": "motriz", "type": "continua", "parent": base, "child": a,
                            "origin": {"x": 0, "y": 300, "z": 600}, "axis": {"y": 1}})
    cad = d.execute("create_chain", {"name": "Cadena", "pinon_a": a, "pinon_b": b})
    nombres = {n for n, f in d.fasteners.items() if cad in (f["a"], f["b"])}
    assert nombres == {f"{cad}_a", f"{cad}_b"}
    assert uniones_entre_juntas(d) == {}
    # el piñón con el padre de su junta: lo excluye `joint_pairs`, no esta regla
    d.execute("fasten", {"name": "a_mano", "a": a, "b": base, "kind": "contacto"})
    assert [u["union"] for u in uniones_entre_juntas(d).values()] == []
    # una unión a mano del piñón que gira con una pieza fija, sí cuenta
    otro = _caja(d, "Soporte", 40, 40, 40, x=0, y=360, z=600)
    d.execute("fasten", {"name": "a_mano_2", "a": a, "b": otro, "kind": "contacto"})
    assert [u["union"] for u in uniones_entre_juntas(d).values()] == ["a_mano_2"]


def test_la_bisagra_que_se_toca_en_todo_el_recorrido_no_da_falso_positivo():
    """Las dos mitades de una bisagra, unidas por su pasador, giran una contra otra y se tocan en
    diseño: la tapa abierta no las hace «chocar» (falso positivo de la mezcladora a 95°)."""
    d = Document()
    base = _caja(d, "Bastidor", 200, 200, 20, z=-10)
    d.execute("ground", {"name": "g", "feature": base})
    tapa = _caja(d, "Tapa", 200, 200, 4, z=12)
    fija = _caja(d, "Media bisagra fija", 40, 10, 20, y=105, z=0)
    movil = _caja(d, "Media bisagra móvil", 40, 10, 20, y=105, z=20)
    d.execute("fasten", {"name": "sold_fija", "a": fija, "b": base, "kind": "soldadura",
                         "throat_mm": 3, "length_mm": 40})
    d.execute("add_joint", {"name": "abre", "type": "giratoria", "parent": base, "child": tapa,
                            "origin": {"x": 0, "y": 105, "z": 10}, "axis": {"x": 1},
                            "lower": 0, "upper": 95, "arrastrar": False})
    d.execute("add_joint", {"name": "jf_movil", "type": "fija", "parent": tapa, "child": movil})
    d.execute("fasten", {"name": "pasador", "a": fija, "b": movil, "kind": "contacto"})
    assert uniones_entre_juntas(d) == {}
