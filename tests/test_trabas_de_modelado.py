"""Las trabas del agente al modelar por MCP (plan trabas-de-modelado, F1: D1–D7).

Cada test es la reproducción que anotó el modelador de la faja con desviador (V8.9 F7,
correcciones 2 a 4), rojo antes del arreglo:
  1. `tan(a*pi/180)` daba 0,0009 sin decir que las trigonométricas toman GRADOS (D1);
  2. `get_connections(ids=[<join_bolted>])` salía vacío y `simulate` dejaba FUERA su tornillería (D2);
  3. `fasten` M5 «fuera de tabla» y la nota cortada a 120 caracteres (D3);
  4. una aserción no se acotaba «hasta» un instante (D4: `tests/test_cosim_aserciones_hasta.py`);
  5. `set_variable` devolvía todas las variables (D5);
  6. cambiar el componente de una pieza ligada daba un 400 sin la llamada que lo arregla (D6);
  7. «no entra en el tablero» no decía que bajar la reserva alcanzaba (D7).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc.document import Document

# ── 1. trigonométricas en grados ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("expr", "avisa"), [
    ("tan(pend_rod*pi/180)", True),
    ("=sin(pi/180*a)", True),
    ("cos(a*pi / 180) * 2", True),
    ("tan(30)", False),
    ("a*pi/180", False),             # sin trigonométrica: no se sabe para qué es
    ("sin(a*180/pi)", False),        # radianes → grados: lo correcto
    ("sin(", False),                 # mal escrita: el error es el de la evaluación
])
def test_el_aviso_de_radianes_salta_solo_con_pi_sobre_180(expr, avisa):
    from apolo.commands.expressions import avisos_expresion

    avisos = avisos_expresion(expr)
    assert bool(avisos) is avisa, avisos
    if avisa:
        assert "GRADOS" in avisos[0] and "pi/180" in avisos[0]


def test_resolve_expression_la_gramatica_y_set_variable_dicen_que_son_grados():
    d = Document("t")
    d.execute("set_variable", {"name": "pend_rod", "expression": "3"})
    api.DOC = d
    c = TestClient(api.app)
    r = c.get("/api/resolve-expression", params={"expr": "tan(pend_rod*pi/180)"}).json()
    assert r["ok"] and r["value"] == pytest.approx(0.000914, abs=1e-6) and "GRADOS" in r["aviso"]
    r = c.get("/api/resolve-expression", params={"expr": "tan(pend_rod)"}).json()
    assert "aviso" not in r and r["value"] == pytest.approx(0.0524, abs=1e-4)
    g = c.get("/api/expression-grammar").json()
    assert "GRADOS" in g["angulos"] and "pi/180" in g["angulos"]
    v = c.post("/api/variables", json={"name": "k", "expression": "tan(pend_rod*pi/180)"}).json()
    assert "GRADOS" in v["avisos_expresion"][0]
    v = c.post("/api/variables", json={"name": "k", "expression": "tan(pend_rod)"}).json()
    assert "avisos_expresion" not in v


def test_el_brief_del_mcp_pasa_el_aviso():
    from apolo.tools.recibo import job_result

    payload = {"document": {"variables": [], "commands": []}, "features": [],
               "affected_command_ids": ["c1"], "avisos_expresion": ["tan() toma GRADOS"]}
    assert job_result(payload, "diff")["avisos_expresion"] == ["tan() toma GRADOS"]


# ── 2. la tornillería de join_bolted es parte de SU unión ─────────────────────────────────────


def _placa_atornillada() -> tuple[Document, str]:
    """La repro de F7b (gravedad): Base a z 505, Placa encima, join_bolted M8 × 2, ground(Base)."""
    d = Document("jb")
    base = d.execute("create_box", {"name": "Base", "width": 400, "depth": 200, "height": 10,
                                    "position": {"x": 0, "y": 0, "z": 505}})
    placa = d.execute("create_box", {"name": "Placa", "width": 200, "depth": 100, "height": 8,
                                     "position": {"x": 0, "y": 0, "z": 514}})
    jb = d.execute("join_bolted", {"a": placa, "b": base, "size": "M8", "count": 2})
    d.execute("ground", {"name": "piso", "feature": base})
    return d, jb


def _tornilleria(jb: str) -> set[str]:
    return {f"{jb}_perno1", f"{jb}_perno2", f"{jb}_tuerca1", f"{jb}_tuerca2"}


def test_get_connections_encuentra_la_union_por_su_comando_y_su_tornilleria():
    """Antes: `get_connections(ids=["c1959"])` (el join_bolted) salía vacío."""
    d, jb = _placa_atornillada()
    api.DOC = d
    c = TestClient(api.app)
    for token in (jb, f"{jb}_perno1", f"{jb}_tuerca2", "c1"):
        r = c.get("/api/connectivity", params={"ids": token, "resumen": "no"})
        assert r.status_code == 200, r.text
        assert [f["name"] for f in r.json()["fasteners"]] == [f"jb_{jb}"], token


def test_la_dinamica_sujeta_la_tornilleria_con_su_union():
    from apolo.physics.dinamica_cuerpos import clasificar
    from apolo.services.delivery_inputs import tornilleria_join_bolted

    d, jb = _placa_atornillada()
    sujetas = tornilleria_join_bolted(d)
    assert set(sujetas) == _tornilleria(jb)
    antes = clasificar(set(d.scene), d.joints, d.fasteners, d.grounds, d.mates)
    assert _tornilleria(jb) <= set(antes.fuera)  # lo que vio el modelador: «queda FUERA»
    ahora = clasificar(set(d.scene), d.joints, d.fasteners, d.grounds, d.mates, sujetas=sujetas)
    assert _tornilleria(jb) <= ahora.estaticas and not ahora.fuera


def test_la_tornilleria_de_una_pieza_movil_viaja_con_su_cuerpo():
    from apolo.physics.dinamica_cuerpos import clasificar

    joints = {"j": {"type": "prismatica", "parent": "base", "child": "carro"},
              "jf": {"type": "fija", "parent": "carro", "child": "placa"}}
    fasteners = {"jb": {"name": "jb", "a": "placa", "b": "carro", "kind": "perno"}}
    ids = {"base", "carro", "placa", "perno"}
    grounds = {"g": {"feature": "base"}}
    sin = clasificar(ids, joints, fasteners, grounds)
    assert "perno" in sin.fuera
    con = clasificar(ids, joints, fasteners, grounds, sujetas={"perno": ("placa", "carro")})
    assert con.cuerpos["j"][0] == "carro" and "perno" in con.cuerpos["j"] and not con.fuera
    # la de una unión con una pieza estática queda estática
    est = clasificar(ids, joints, fasteners, grounds, sujetas={"perno": ("base", "carro")})
    assert "perno" in est.estaticas and "perno" not in con.estaticas


def test_la_api_de_la_dinamica_pasa_la_tornilleria(monkeypatch):
    import apolo.physics.dinamica as dinamica
    from apolo.physics.sim import PhysicsError

    d, jb = _placa_atornillada()
    visto = {}

    def falsa(*a, **k):
        visto.update(k)
        raise PhysicsError("corte del test")

    monkeypatch.setattr(dinamica, "prepare_dynamics", falsa)
    api.DOC = d
    r = TestClient(api.app).post("/api/physics/dynamics", json={})
    assert r.status_code == 400 and set(visto["sujetas"]) == _tornilleria(jb)


# ── 3. fasten M5 y la nota ───────────────────────────────────────────────────────────────────


def test_fasten_m5_se_calcula_y_la_nota_admite_el_porque():
    from apolo.library.engineering.bolts import TENSILE_AREA_MM2, bolt_shear_capacity_n
    from apolo.library.engineering.report import structure_engineering_check
    from apolo.library.engineering.threads import thread_spec

    assert TENSILE_AREA_MM2["M5"] == 14.2 and bolt_shear_capacity_n("M5", "8.8") > 0
    assert thread_spec("M5")["area_mm2"] == 14.2  # la misma que daba la fórmula
    d = Document("m5")
    a = d.execute("create_box", {"width": 100, "depth": 100, "height": 10})
    b = d.execute("create_box", {"width": 100, "depth": 100, "height": 10, "position": {"z": 10}})
    nota = "M5x16 DIN 912 cada 60 mm, rosca M5 en la barra portarriel (avellanado del riel); " * 3
    assert 120 < len(nota) <= 500
    d.execute("fasten", {"name": "riel", "a": b, "b": a, "kind": "perno", "size": "M5", "qty": 4,
                         "nota": nota})
    d.execute("ground", {"name": "piso", "feature": a})
    assert d.fasteners["riel"]["nota"] == nota
    checks = structure_engineering_check(d.scene, d.fasteners, d.grounds, d.joints, d.mates)
    textos = " ".join(str(c) for c in checks if "riel" in str(c))
    assert textos and "fuera de tabla" not in textos
    with pytest.raises(Exception, match="500"):
        d.execute("fasten", {"name": "larga", "a": a, "b": b, "nota": "x" * 501})


# ── 5. set_variable corto ────────────────────────────────────────────────────────────────────


def _vars() -> list[dict]:
    return [{"name": "largo", "expression": "4000", "value": 4000.0, "command_id": "c1"},
            {"name": "paso_rod", "expression": "66", "value": 66.0, "command_id": "c2"},
            {"name": "n_rod", "expression": "floor(largo / paso_rod)", "value": 60.0, "command_id": "c3"},
            {"name": "x_ult", "expression": "n_rod * paso_rod", "value": 3960.0, "command_id": "c4"},
            {"name": "alto", "expression": "850", "value": 850.0, "command_id": "c5"}]


def test_set_variable_devuelve_la_tocada_y_lo_que_arrastra():
    from apolo.brief import _scene_brief, variables_tocadas

    nombres = [v["name"] for v in variables_tocadas(_vars(), {"c2"})]
    assert nombres == ["paso_rod", "n_rod", "x_ult"]
    payload = {"document": {"variables": _vars(), "commands": [
        {"id": f"c{k}", "type": "set_variable"} for k in range(1, 6)]},
        "features": [], "affected_command_ids": ["c5"]}
    b = _scene_brief(payload, "diff")
    assert [v["name"] for v in b["variables"]] == ["alto"] and b["variables_omitidas"] == 4
    assert len(_scene_brief(payload, "full")["variables"]) == 5  # full: todas, sin omitidas
    assert "variables_omitidas" not in _scene_brief(payload, "full")


# ── 6. cambiar el componente de una pieza ligada ─────────────────────────────────────────────


def test_el_error_de_componente_da_la_llamada_que_lo_arregla():
    from apolo.commands.electrico_eval import _pieza

    escena = {"c1756": SimpleNamespace(component="VAL-52-MONO-G14", name="Electrovalvula 5/2 -QM2",
                                       command_id="c1756")}
    with pytest.raises(ValueError) as exc:
        _pieza("c1756", "VAL-52-MONO-G18", escena, "c1680")
    msg = str(exc.value)
    assert "liga el dispositivo a la pieza que lo representa" in msg  # el texto de siempre
    assert ('edit_batch([<tu cambio de c1756>, {"command_id": "c1680", "params": '
            '{"ref": "VAL-52-MONO-G14"}}])') in msg
    with pytest.raises(ValueError) as exc:  # sin el add_device (tablero_chequeos): lo de siempre
        _pieza("c1756", "VAL-52-MONO-G18", escena)
    assert "edit_batch" not in str(exc.value)


# ── 7. el tablero que no entra ───────────────────────────────────────────────────────────────


def test_la_reserva_que_entra():
    from apolo.library.electrico.colocacion import (
        Aparato, ColocacionError, Gabinete, Reglas, colocar, reserva_que_entra,
    )

    chico = Gabinete("CHICO", 300, 250, 160, 1.5, "izquierda")

    def aps(n):
        return [Aparato(f"-F{i}", "REF", "din", 54, 90, 75, "alimentacion", "F") for i in range(1, n + 1)]

    # 4 × 54 mm en un riel de 250: con 20 % de reserva van en dos filas y no entran en alto
    with pytest.raises(ColocacionError, match="faltan"):
        colocar(aps(4), "CHICO", [chico])
    assert reserva_que_entra(aps(4), "CHICO", [chico], None, Reglas()) == 0.10  # la mayor que entra
    colocar(aps(4), "CHICO", [chico], None, Reglas(reserva=0.10))
    assert reserva_que_entra(aps(9), "CHICO", [chico], None, Reglas()) is None  # ni con 0
