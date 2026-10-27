"""Los aparatos de tablero con la forma de su familia (plan aparatos-de-tablero-realistas, F1).

- D1: un builder por familia, los mismos nombres que `ficha_tablero.FAMILIAS_APARATO` (la
  colocación los lee como una caja) y todos por zonas.
- D2: cada ref conserva EXACTAMENTE la envolvente de su ficha (bbox = width × depth × height,
  centrado), en un solo sólido; con otras medidas, también (los detalles son fracciones de la
  ficha, no coordenadas fijas).
- D4: las zonas cubren todas las caras y cada zona del YAML existe en la pieza.
- D5: la ref se construye una vez por proceso (mismo sólido); la seta, como siempre.
- El tablero de la piloto da las MISMAS cajas que antes (congeladas en main) y sus aparatos
  llegan con sus zonas.
- `fusionar_zonas` con una lista por zona: una sola fusión, mismo sólido.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apolo.kernel.mesh import mesh_payload
from apolo.kernel.zonas import fusionar_zonas
from apolo.library.builders_aparatos import BUILDERS, ZONADOS
from apolo.library.catalog import CATALOG, build_component
from apolo.library.electrico.colocacion_catalogo import aparatos_desde_catalogo
from apolo.library.electrico.ficha_tablero import APOYO_POR_FAMILIA, FAMILIAS_APARATO
from apolo.library.zonas import zona_por_cara

DATA = Path(__file__).parent / "data"
PILOTO = json.loads((DATA / "tablero_piloto.json").read_text(encoding="utf-8"))
CAJAS = json.loads((DATA / "tablero_piloto_cajas.json").read_text(encoding="utf-8"))["aparatos"]


def _una_por_forma() -> list[str]:
    """Una ref por (familia, params): las demás construyen la misma forma."""
    vistas, out = set(), []
    for ref, c in CATALOG.items():
        clave = (c.familia, json.dumps(c.params, sort_keys=True))
        if c.familia in BUILDERS and clave not in vistas:
            vistas.add(clave)
            out.append(ref)
    return out


REFS = _una_por_forma()


def _medidas(shape):
    bb = shape.bounding_box()
    c = bb.center()
    return (bb.size.X, bb.size.Y, bb.size.Z), (c.X, c.Y, c.Z)


def test_familias_registradas_y_con_cara_de_apoyo():
    assert set(BUILDERS) == set(FAMILIAS_APARATO) == set(ZONADOS)
    assert all(APOYO_POR_FAMILIA[f] == "-Y" for f in FAMILIAS_APARATO)
    familias = {c.familia for c in CATALOG.values() if c.familia in BUILDERS}
    assert familias == set(BUILDERS)  # cada familia sirve al menos a una ref del catálogo
    assert len([r for r, c in CATALOG.items() if c.familia in BUILDERS]) == 39


@pytest.mark.parametrize("ref", REFS)
def test_envolvente_de_la_ficha_y_zonas(ref):
    comp = CATALOG[ref]
    s, _ = build_component(ref)
    assert len(s.solids()) == 1
    tam, centro = _medidas(s)
    p = comp.params
    assert tam == pytest.approx((p["width"], p["depth"], p["height"]), abs=1e-6)
    assert centro == pytest.approx((0, 0, 0), abs=1e-6)
    zp = zona_por_cara(ref, s)
    assert zp is not None and len(zp) == len(s.faces())
    assert set(zp) == {z.nombre for z in comp.zonas}
    m = mesh_payload(s, zona_por_cara=zp)
    assert m["zonas"][-1]["hasta"] == len(m["indices"]) // 3  # los rangos cubren la malla


@pytest.mark.parametrize("ref", ["ITM-C16-3P", "DIF-4P-40A-30MA-A", "CONT-9A-24VDC", "GM-2.5-4A",
                                 "RELE-INT-24VDC", "BORNE-PE-4", "BORNE-FUS-5X20",
                                 "PLC-14DI-10DO-24VDC", "FUENTE-24VDC-5A", "VFD-1K5-220"])
@pytest.mark.parametrize("escala", [(1.3, 1.1, 1.2), (0.8, 0.9, 0.85)])
def test_los_detalles_siguen_a_las_medidas(ref, escala):
    comp = CATALOG[ref]
    p = dict(comp.params)
    for k, e in zip(("width", "depth", "height"), escala):
        p[k] = round(p[k] * e, 3)
    solido, por_cara = fusionar_zonas(BUILDERS[comp.familia](**p)(None))
    assert len(solido.solids()) == 1 and len(por_cara) == len(solido.faces())
    tam, centro = _medidas(solido)
    assert tam == pytest.approx((p["width"], p["depth"], p["height"]), abs=1e-6)
    assert centro == pytest.approx((0, 0, 0), abs=1e-6)


def test_una_construccion_por_proceso():
    a, _ = build_component("ITM-C2-2P")
    b, _ = build_component("ITM-C2-2P")
    assert a is b  # D5: memorizada
    s1, _ = build_component("ESTOP-40")
    s2, _ = build_component("ESTOP-40")
    assert s1 is not s2  # la seta no cambia: se construye cada vez


def test_tipo_y_medidas_invalidas():
    with pytest.raises(ValueError, match="tipo"):
        BUILDERS["borne_riel"](width=5.2, depth=47, height=42.5, tipo="doble")
    with pytest.raises(ValueError, match="tipo"):
        BUILDERS["interruptor_modular"](width=36, depth=75, height=90, tipo="seccionador")
    with pytest.raises(ValueError, match="depth"):
        BUILDERS["contactor"](width=45, depth=10, height=77)


def test_zona_con_lista_es_una_sola_fusion():
    from build123d import Box, Pos

    base = Box(20, 20, 20)
    a, b = Pos(0, 0, 10) * Box(4, 4, 4), Pos(6, 0, 10) * Box(4, 4, 4)
    s_lista, z_lista = fusionar_zonas({"cuerpo": base, "bornes": [a, b]})
    assert len(s_lista.solids()) == 1
    assert s_lista.volume == pytest.approx(20 ** 3 + 2 * 4 * 4 * 2)
    assert z_lista.count("bornes") == 2 * 5  # cada cubo asoma 5 caras
    # la misma pieza con una forma por zona da las mismas zonas
    s_sep, z_sep = fusionar_zonas({"cuerpo": base, "b1": a, "b2": b})
    assert sorted(z.replace("b1", "bornes").replace("b2", "bornes") for z in z_sep) == sorted(z_lista)


def test_la_colocacion_lee_la_envolvente_de_los_params():
    """Sin `medir` (lo que no es caja daría error): la colocación lee width × depth × height."""
    entradas = [{"designacion": "-F1", "ref": "ITM-C16-3P"}, {"designacion": "-T1", "ref": "VFD-2K2-220"},
                {"designacion": "-X1", "ref": "BORNE-PASO-2.5", "cantidad": 3}]
    aparatos, _ = aparatos_desde_catalogo(entradas, CATALOG, medir=None)
    por = {a.designacion: a for a in aparatos}
    assert (por["-F1"].ancho, por["-F1"].alto, por["-F1"].fondo) == (54, 90, 75)
    assert (por["-T1"].ancho, por["-T1"].alto, por["-T1"].fondo) == (140, 160, 145)


@pytest.fixture(scope="module")
def piloto():
    from apolo.doc.document import Document

    acciones = []
    for dv in PILOTO["dispositivos"]:
        p = {"ref": dv["ref"], "designacion": dv["designacion"], "ubicacion": "+TAB1"}
        if "cantidad" in dv:
            p["cantidad"] = dv["cantidad"]
        acciones.append({"type": "add_device", "params": p})
    acciones.append({"type": "layout_tablero", "params": {"ubicacion": "TAB1", "position": {"z": 1200}}})
    d = Document()
    d.execute_many(acciones)
    return d


def test_el_tablero_de_la_piloto_no_se_mueve(piloto):
    cid = next(c["id"] for c in piloto.commands if c["type"] == "layout_tablero")
    vistos = {}
    for fid, f in piloto.scene.items():
        if f.command_id == cid and "_d_" in fid:
            tam, centro = _medidas(f.shape)
            vistos[fid.split("_d_", 1)[1]] = (centro, tam)
    assert set(vistos) == set(CAJAS)
    for des, caja in CAJAS.items():
        centro, tam = vistos[des]
        assert centro == pytest.approx(caja["centro"], abs=1e-3), des
        assert tam == pytest.approx(caja["medidas"], abs=1e-3), des


def test_los_aparatos_del_tablero_llegan_con_sus_zonas(piloto):
    con_forma = [f for f in piloto.scene.values() if f.component and CATALOG[f.component].familia in BUILDERS]
    assert {f.component for f in con_forma} >= {"ITM-C16-3P", "ITM-C2-2P", "FUENTE-24VDC-5A",
                                                "PLC-14DI-10DO-24VDC", "BORNE-PE-4", "VFD-2K2-220"}
    for f in con_forma:
        assert zona_por_cara(f.component, f.shape) is not None, f.id
