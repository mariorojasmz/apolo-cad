"""`RegenState`: el estado del regenerate con nombre (plan estado-regen-y-params-estrictos, D2).

Lo que se protege:
  - `copy()` aísla un checkpoint CAMPO POR CAMPO de lo que hagan los comandos posteriores
    (si compartiera por error un dict mutable, un edit corrompería el checkpoint y el
    siguiente regenerate incremental reanudaría de un estado falso);
  - el shape OCCT se COMPARTE por identidad (copiar geometría es lo caro: el checkpoint sólo
    es barato porque ningún executor muta un shape in-place);
  - un blob de la caché de geometría de formato v4 (la 8-tupla) se descarta → replay frío;
  - un typo en un campo es un error, no un atributo nuevo silencioso (`slots`).
"""

from __future__ import annotations

import pickle

import pytest

from apolo.commands.registry import Feature, execute_command
from apolo.commands.state import RegenState
from apolo.doc.document import Document
from apolo.doc.geomcache import GEOM_CACHE_EPOCH, pack, unpack
from apolo.kernel import make_box

CAMPOS_DICT = ("joints", "mates", "constraints", "fasteners", "grounds", "groups")


def _estado() -> RegenState:
    feat = Feature("c1", "Caja", make_box(10, 20, 30), "c1",
                   anchors={"centro": {"origin": [0, 0, 0], "axis": [0, 0, 1]}})
    return RegenState(
        scene={"c1": feat},
        variables={"W": "50"},
        joints={"j1": {"parent": "c1", "child": "c2", "axis": [0, 0, 1]}},
        mates={"m1": {"feature_a": "c1", "feature_b": "c2", "ref_a": {"face": "tope"}}},
        constraints={"r1": {"joint": "j1", "puntos": [[0, 0, 0]]}},
        fasteners={"f1": {"a": "c1", "b": "c2", "kind": "perno"}},
        grounds={"g1": {"feature": "c1"}},
        groups={"G": {"members": ["c1"], "parent": None}},
    )


def test_campos_con_nombre_en_el_orden_de_la_vieja_tupla():
    assert RegenState.field_names() == (
        "scene", "variables", "joints", "mates", "constraints", "fasteners", "grounds", "groups",
    )
    st = RegenState()
    assert all(getattr(st, n) == {} for n in RegenState.field_names())
    assert st.scene is not RegenState().scene  # cada estado nace con sus PROPIOS dicts


def test_un_campo_inventado_es_un_error():
    st = RegenState()
    with pytest.raises(AttributeError):
        st.scen = {}  # typo: con slots no se crea un atributo nuevo en silencio


def test_copy_aisla_cada_campo():
    orig = _estado()
    c = orig.copy()
    # escena: Feature distinta (shallow-copy) pero el MISMO shape OCCT
    assert c.scene is not orig.scene and c.scene["c1"] is not orig.scene["c1"]
    assert c.scene["c1"].shape is orig.scene["c1"].shape
    c.scene["c1"].name = "Otra"
    c.scene["c2"] = Feature("c2", "Nueva", None, "c2")
    assert orig.scene["c1"].name == "Caja" and set(orig.scene) == {"c1"}
    # variables: dict propio
    c.variables["W"] = "99"
    c.variables["H"] = "1"
    assert orig.variables == {"W": "50"}
    # el resto: copia PROFUNDA (los executors mutan juntas y restricciones en sitio)
    for nombre in CAMPOS_DICT:
        a, b = getattr(orig, nombre), getattr(c, nombre)
        assert a == b and a is not b
        clave = next(iter(b))
        assert b[clave] is not a[clave]
        b[clave]["mutado"] = True
        b["nuevo"] = {}
        assert "mutado" not in a[clave] and "nuevo" not in a, nombre
    c.joints["j1"]["axis"].append(9)
    assert orig.joints["j1"]["axis"] == [0, 0, 1]


def test_copy_de_copy_sigue_compartiendo_el_shape():
    orig = _estado()
    assert orig.copy().copy().scene["c1"].shape is orig.scene["c1"].shape


def test_plain_por_nombre_ida_y_vuelta():
    orig = _estado()
    plain = orig.to_plain()
    assert set(plain) == set(RegenState.field_names())
    assert plain["joints"] is orig.joints  # sin copiar: lo serializa el caller
    back = RegenState.from_plain(pickle.loads(pickle.dumps(plain)))
    assert back.joints == orig.joints and set(back.scene) == {"c1"}
    for malo in ((), [], {"scene": {}}, {**plain, "extra": {}}, {**plain, "mates": []}, None):
        with pytest.raises(ValueError):
            RegenState.from_plain(malo)


def test_execute_command_muta_el_estado():
    st = RegenState()
    execute_command(st, "c1", "set_variable", {"name": "W", "expression": "40"})
    execute_command(st, "c2", "create_box", {"name": "B", "width": "=W", "depth": 10, "height": 5})
    execute_command(st, "c3", "ground", {"name": "g", "feature": "c2"})
    assert st.variables == {"W": "40"}
    assert st.scene["c2"].shape.volume == pytest.approx(40 * 10 * 5)
    assert set(st.grounds) == {"g"}


def _doc() -> Document:
    d = Document("rs")
    a = d.execute("create_box", {"name": "A", "width": 40, "depth": 40, "height": 10})
    d.execute("create_box", {"name": "B", "width": 20, "depth": 20, "height": 10,
                             "position": {"x": 100}})
    d.execute("ground", {"name": "g", "feature": a})
    return d


def test_los_checkpoints_del_documento_son_regenstate():
    d = _doc()
    assert d._regen_ckpts and all(isinstance(s, RegenState) for s in d._regen_ckpts.values())
    ultimo = d._regen_ckpts[len(d.commands) - 1]
    assert ultimo.scene["c1"].shape is d.scene["c1"].shape  # el checkpoint no copia geometría
    assert ultimo.grounds == d.grounds and ultimo.grounds is not d.grounds


def test_blob_v4_con_tupla_se_descarta():
    """Un blob de la caché escrito por el código viejo (epoch 4, estado = 8-tupla) no se
    reanuda: el open cae a replay frío."""
    d = _doc()
    bueno = pack(d)
    assert GEOM_CACHE_EPOCH == 5 and unpack(bueno) is not None
    data = pickle.loads(bueno)
    st = data["state"]
    tupla = tuple(st[n] for n in RegenState.field_names())
    v4 = {**data, "epoch": 4, "state": tupla}
    assert unpack(pickle.dumps(v4)) is None
    # aun con el epoch de hoy, una tupla (o un estado al que le falta un campo) no se acepta
    assert unpack(pickle.dumps({**data, "state": tupla})) is None
    sin_grupos = {k: v for k, v in st.items() if k != "groups"}
    assert unpack(pickle.dumps({**data, "state": sin_grupos})) is None
    # y el open con un warm inservible da el documento correcto (replay frío)
    hot = Document.from_apolo_bytes(d.to_apolo_bytes(), warm=unpack(pickle.dumps(v4)))
    assert sorted(hot.scene) == sorted(d.scene) and hot.check_integrity() == []


def test_checkpoint_con_tupla_vieja_fuerza_replay():
    """Un checkpoint con la forma vieja (tupla) en memoria no revienta: replay completo."""
    d = _doc()
    d._regen_ckpts = {k: tuple(s.to_plain().values()) for k, s in d._regen_ckpts.items()}
    assert any("mal formado" in i for i in d.check_integrity())
    d.edit("c2", {"width": 25}, merge=True)
    assert d.check_integrity() == []
    bb = d.scene["c2"].shape.bounding_box()
    assert round(bb.max.X - bb.min.X) == 25
