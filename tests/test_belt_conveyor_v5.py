"""`create_belt_conveyor` v5: los cierres que pide la puerta con el brazo doblado (F6 de
puerta-de-publicacion, Bitácora «v5 de la plantilla»).

- guardas inferiores en L bajo la ranura borde de banda ↔ larguero, entre las guardas de los
  tambores, atornilladas al alma interior del larguero (en tramos de ≤ 3 m);
- placas de cierre soldadas en las puntas de los largueros (el tubo abierto dejaba llegar a la
  ranura del tensor);
- el techo de la guarda de cola cubre el tramo libre de la banda hasta pasar la cama, y las
  paredes de las guardas se escotan en las placas de los soportes de la cama.

Compatibilidad: el campo oculto `cierres` lo pone el SELLO de entrada a todo comando nuevo; un log
v4 no lo trae → False → regenera con la geometría de la v4.
"""

from __future__ import annotations

import pytest

from apolo.commands.registry import REGISTRY
from apolo.doc import Document
from apolo.library.checks import interference_report

#: el default, una corta y angosta, y un larguero de poco canto con tambores chicos (las
#: placas de los soportes de la cama bajan hasta las paredes de las guardas: escotes)
VARIANTES = [{}, {"largo": 1500, "ancho_banda": 300},
             {"largo": 3000, "ancho_banda": 500, "tubo": "TUBO-3X2", "tambor_motriz": "TAMBOR-80",
              "tambor_cola": "TAMBOR-80", "tensor": "ninguno"}]


def _faja(**params):
    d = Document()
    cid = d.execute("create_belt_conveyor", params)
    return d, cid


@pytest.fixture(scope="module", params=range(len(VARIANTES)), ids=["default", "corta", "3x2"])
def faja_v5(request):
    return _faja(**VARIANTES[request.param])


def _nombres(d, rol: str) -> list[str]:
    return sorted(f.id for f in d.scene.values() if f.name.split(" · ")[-1].startswith(rol))


def test_el_comando_nuevo_nace_con_cierres_y_el_campo_no_se_publica():
    d, cid = _faja()
    assert d.commands[0]["params"]["cierres"] is True  # el sello de entrada
    schema = REGISTRY["create_belt_conveyor"].model.model_json_schema()
    assert "cierres" not in schema["properties"]  # criterio de Apolo: ni la UI ni el agente
    assert REGISTRY["create_belt_conveyor"].version == 5
    # lo que el cliente trae se respeta (la v4 tal cual, a pedido)
    d4, _ = _faja(cierres=False)
    assert d4.commands[0]["params"]["cierres"] is False
    assert not _nombres(d4, "Guarda inferior") and not _nombres(d4, "Placa de cierre")


def test_un_log_v4_regenera_igual():
    """Un log v4 no trae `cierres`: regenera sin los cierres y con las mismas piezas, del mismo
    volumen y en el mismo sitio que la v4 pedida a mano; el replay no sella."""
    ref, _ = _faja(cierres=False)
    d, _ = _faja(cierres=False)
    del d.commands[0]["params"]["cierres"]
    viejo = Document.from_apolo_bytes(d.to_apolo_bytes())
    assert "cierres" not in viejo.commands[0]["params"]
    assert set(viejo.scene) == set(ref.scene) and len(ref.scene) == 58
    for fid, f in ref.scene.items():
        a, b = f.shape.bounding_box(), viejo.scene[fid].shape.bounding_box()
        assert viejo.scene[fid].shape.volume == pytest.approx(f.shape.volume, rel=1e-9), fid
        assert (b.min.X, b.max.X, b.min.Z, b.max.Z) == pytest.approx(
            (a.min.X, a.max.X, a.min.Z, a.max.Z), abs=1e-6), fid
    # editar un log v4 tampoco lo sella
    cmd = viejo.commands[0]
    viejo.edit(cmd["id"], {**cmd["params"], "altura": 950})
    assert "cierres" not in viejo.commands[0]["params"]
    assert not _nombres(viejo, "Guarda inferior")


def test_v5_sin_choques_internos(faja_v5):
    d, _ = faja_v5
    r = interference_report(d.scene)
    assert not r["truncado"]
    assert [(i["a"], i["b"], i["volumen_mm3"]) for i in r["interferencias"]] == []


def test_v5_cierres_declarados_y_con_camino_a_tierra(faja_v5):
    """Cada cierre va DECLARADO: la guarda inferior con perno al larguero (se quita con
    herramienta), la placa de cierre soldada; todo llega a tierra sin autodetección."""
    from apolo.assembly.connectivity import build_graph, soundness_report

    d, cid = faja_v5
    inferiores, cierres = _nombres(d, "Guarda inferior"), _nombres(d, "Placa de cierre")
    assert len(inferiores) >= 2 and len(inferiores) % 2 == 0 and len(cierres) == 4
    por_pieza = {}
    for f in d.fasteners.values():
        for k in ("a", "b"):
            por_pieza.setdefault(f[k], []).append(f)
    for g in inferiores:
        (u,) = por_pieza[g]
        assert u["kind"] == "perno" and u["size"] == "M6" and u["qty"] >= 2
        assert {u["a"], u["b"]} - {g} <= {f"{cid}_rail1", f"{cid}_rail2"}
        assert d.scene[g].shape.bounding_box().size.X <= 3000.0 + 1e-6  # tramo de plegadora
    for p in cierres:
        (u,) = por_pieza[p]
        assert u["kind"] == "soldadura" and u["throat_mm"] and u["length_mm"]
    rep = soundness_report(build_graph(d.scene, d.joints, d.mates, d.fasteners, d.grounds))
    assert rep["floating"] == [] and rep["n_grounded"] == len(d.scene)


def test_v5_la_guarda_inferior_cierra_la_ranura_sin_tocar_la_banda(faja_v5):
    """El ala queda bajo el ramal de retorno, por FUERA del borde de la banda, y cubre la ranura
    hasta la pared; entre las guardas de los tambores no queda hueco."""
    d, cid = faja_v5
    banda = d.scene[f"{cid}_banda"].shape.bounding_box()
    xs = []
    for g in _nombres(d, "Guarda inferior"):
        bb = d.scene[g].shape.bounding_box()
        # el ala: 10 mm bajo el ramal de retorno (3 mm de chapa), desde 1 mm fuera del borde
        assert bb.min.Z == pytest.approx(banda.min.Z - 13.0, abs=1e-6)
        assert min(abs(bb.min.Y), abs(bb.max.Y)) == pytest.approx(banda.max.Y + 1.0, abs=1e-6)
        if bb.max.Y < 0:
            xs.append((bb.min.X, bb.max.X))
    xs.sort()
    gc = d.scene[f"{cid}_guarda_c"].shape.bounding_box()
    gm = d.scene[f"{cid}_guarda_m"].shape.bounding_box()
    assert xs[0][0] - gc.max.X <= 1.0 + 1e-6 and gm.min.X - xs[-1][1] <= 1.0 + 1e-6
    assert all(b[0] - a[1] <= 1.0 + 1e-6 for a, b in zip(xs, xs[1:]))


def test_v5_sigue_la_parametrica():
    d, cid = _faja()
    n0 = len(_nombres(d, "Guarda inferior"))
    d.edit(cid, {**d.commands[0]["params"], "largo": 8000, "ancho_banda": 1000})
    assert d.commands[0]["params"]["cierres"] is True  # el edit conserva lo sellado
    assert len(_nombres(d, "Guarda inferior")) == 6 > n0  # 3 tramos por lado
    rail = d.scene[f"{cid}_rail1"].shape.bounding_box()
    tapas = [d.scene[p].shape.bounding_box() for p in _nombres(d, "Placa de cierre")]
    assert min(t.min.X for t in tapas) == pytest.approx(rail.min.X - 3.0, abs=1e-6)
    assert max(t.max.X for t in tapas) == pytest.approx(rail.max.X + 3.0, abs=1e-6)
    assert interference_report(d.scene)["interferencias"] == []
