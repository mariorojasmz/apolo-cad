"""Plan union-en-perfil-hueco (F1): `join_bolted` con el criterio de TALLER (D1–D6) sobre
piezas reales: tubo HSS cerrado de catálogo, C de chapa de 3 mm, tablero de madera y la placa
de identificación de 1,5 mm de la F4 de varias-maquinas. Un log viejo regenera igual."""

import pytest

from apolo.batch import execute_batch
from apolo.commands.registry import CommandError
from apolo.doc import Document
from apolo.library import fijacion as fj
from apolo.library.acceso_herramienta import tool_access_report
from apolo.library.catalog import CATALOG
from apolo.services.delivery_inputs import delivery_inputs

PLACA = 1.5


def _caja(f):
    b = f.shape.bounding_box()
    return b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z


def _de(doc, cid):
    return {fid: f for fid, f in doc.scene.items() if f.command_id == cid}


def _tubo(doc):
    """Larguero HSS 2″×2″×3,2 a lo largo de X (z ∈ ±25,4) + la placa encima."""
    t = doc.execute("insert_component", {"component": "TUBO-2X2", "length": 600,
                                         "name": "Larguero (+Y)", "rotation": {"y": 90}})
    p = doc.execute("create_box", {"name": "Placa de identificación", "width": 120, "depth": 40,
                                   "height": PLACA, "position": {"z": 25.4 + PLACA / 2}})
    return t, p


def _c_chapa(doc, y=0.0):
    """C de chapa de 3 mm: alma en z ∈ [0, 3], alas de 50 hacia +Z; la placa bajo el alma."""
    c = doc.execute("create_sheet_metal", {"name": "Larguero C", "ancho": 600, "fondo": 150,
                                           "espesor": 3, "lados": ["frente", "atras"],
                                           "altura_pestana": 50, "position": {"y": y}})
    p = doc.execute("create_box", {"name": "Placa", "width": 120, "depth": 60, "height": PLACA,
                                   "position": {"y": y, "z": -PLACA / 2}})
    return c, p


def _tablero(doc):
    w = doc.execute("create_box", {"name": "Tablero", "width": 600, "depth": 400, "height": 18,
                                   "position": {"z": 9}})
    p = doc.execute("create_box", {"name": "Placa", "width": 120, "depth": 60, "height": PLACA,
                                   "position": {"z": 18 + PLACA / 2}})
    return w, p


def _acceso_ok(doc):
    rep = tool_access_report(doc.scene, catalog=CATALOG)
    assert rep is not None and rep["evaluados"] >= 1
    assert rep["ok"] == rep["evaluados"], rep
    assert not rep["sin_herramienta"] and not rep["solo_boca"] and not rep["no_evaluados"], rep
    return rep


# ── D1: sin acceso por detrás → fijación ciega ──────────────────────────────────────────


def test_d1_tubo_cerrado_lleva_remache_ciego_que_no_toca_la_pared_de_enfrente():
    doc = Document("d1")
    t, p = _tubo(doc)
    vol0 = doc.scene[t].shape.volume
    cid = doc.execute("join_bolted", {"a": t, "b": p, "size": "M6", "count": 2})
    piezas = _de(doc, cid)
    assert sorted(piezas) == [f"{cid}_remache1", f"{cid}_remache2"]  # sin tuerca
    r = piezas[f"{cid}_remache1"]
    assert r.component == "REMACHE-4.8" and r.name == "Remache ciego Ø4.8×10 DIN 7337"
    x0, _, z0, x1, _, z1 = _caja(r)
    assert z1 == pytest.approx(25.4 + PLACA + 1.5, abs=0.05)  # cabeza sobre la placa
    assert -25.4 + 3.2 < z0 < 25.4 - 3.2  # la cabeza ciega queda DENTRO del tubo
    # sólo se taladró la pared de arriba: 2 agujeros Ø4.9 × 3,2 mm, no 4
    quitado = vol0 - doc.scene[t].shape.volume
    assert quitado == pytest.approx(2 * 3.14159 * 2.45 ** 2 * 3.2, rel=0.08)
    f = doc.fasteners[f"jb_{cid}"]
    # el remache declara su Ø de cuerpo: la unión se dimensiona (puerta-sin-sobrediseno F3f)
    assert f["kind"] == "perno" and f["size"] == "Ø4.8" and f["qty"] == 2
    assert f["fijacion"] == "Remache ciego Ø4.8×10 DIN 7337"
    _acceso_ok(doc)


def test_d1_obstaculo_detras_tambien_pide_fijacion_ciega():
    """Una C con acceso, pero con otra pieza a 7 mm detrás del alma: sin sitio para la llave
    (sí para la cabeza ciega). Pegada al alma, ni eso: error accionable."""
    doc = Document("d1-obst")
    c, p = _c_chapa(doc)
    r = doc.execute("create_box", {"name": "Refuerzo", "width": 200, "depth": 100, "height": 10,
                                   "position": {"z": 3 + 7 + 5}})
    cid = doc.execute("join_bolted", {"a": c, "b": p, "size": "M6", "count": 2})
    assert {f.component for f in _de(doc, cid).values()} == {"REMACHE-4.8"}
    doc.undo()
    doc.edit(r, {"name": "Refuerzo", "width": 200, "depth": 100, "height": 10,
                 "position": {"z": 3 + 5}})
    with pytest.raises(Exception, match="libres"):
        doc.execute("join_bolted", {"a": c, "b": p, "size": "M6", "count": 2})


def test_d1_sin_ciega_para_la_metrica_da_error_que_dice_que_hacer():
    doc = Document("d1-m10")
    t, p = _tubo(doc)
    with pytest.raises(Exception) as exc:
        doc.execute("join_bolted", {"a": t, "b": p, "size": "M10", "count": 2})
    assert "M8" in str(exc.value) and "acceso por detrás" in str(exc.value)


# ── D2 y D3: largo por el espesor real; la tuerca detrás de la base ─────────────────────


def test_d2_c_de_3mm_mas_placa_de_1_5_da_m6x12():
    doc = Document("d2")
    c, p = _c_chapa(doc)
    cid = doc.execute("join_bolted", {"a": c, "b": p, "size": "M6", "count": 2})
    pernos = [f for f in _de(doc, cid).values() if f.component == "PERNO-HEX-M6"]
    assert len(pernos) == 2 and all(f.name == "Perno M6×12 DIN 933" for f in pernos)
    assert fj.largo_perno("M6", 3 + PLACA) == 12  # 2,5 hilos fuera de la tuerca
    _acceso_ok(doc)  # la copa entra en la C por dentro


@pytest.mark.parametrize("a_es_placa", [False, True])
def test_d3_cabeza_del_lado_de_la_placa_y_tuerca_detras_del_alma(a_es_placa):
    doc = Document("d3")
    c, p = _c_chapa(doc)
    a, b = (p, c) if a_es_placa else (c, p)
    cid = doc.execute("join_bolted", {"a": a, "b": b, "size": "M6", "count": 2})
    piezas = _de(doc, cid)
    perno, tuerca = piezas[f"{cid}_perno1"], piezas[f"{cid}_tuerca1"]
    assert _caja(perno)[2] == pytest.approx(-PLACA - 4.0, abs=0.05)  # cabeza bajo la placa
    _, _, tz0, _, _, tz1 = _caja(tuerca)
    assert tz0 == pytest.approx(3.0, abs=0.05) and tz1 == pytest.approx(8.0, abs=0.05)
    assert doc.fasteners[f"jb_{cid}"]["size"] == "M6"


# ── D4: madera → tornillo para madera ───────────────────────────────────────────────────


@pytest.mark.parametrize("como", ["vertical", "set_material"])
def test_d4_tablero_de_madera_lleva_tornillo_din_571_sin_tuerca(como):
    doc = Document("d4")
    w, p = _tablero(doc)
    if como == "vertical":
        doc.set_vertical("carpinteria")
    else:
        doc.set_material(w, "madera copaiba")
    cid = doc.execute("join_bolted", {"a": p, "b": w, "size": "M6", "count": 2})
    params = next(c for c in doc.commands if c["id"] == cid)["params"]
    assert w in params["madera"] and params["criterio"] == 6  # vigente (V8.9 F7b: agujeros previos)
    piezas = _de(doc, cid)
    assert sorted(piezas) == [f"{cid}_tornillo1", f"{cid}_tornillo2"]  # sin tuerca
    t = piezas[f"{cid}_tornillo1"]
    assert t.component == "TIRAFONDO-HEX-6" and t.name == "Tornillo para madera Ø6×16 DIN 571"
    _, _, z0, _, _, z1 = _caja(t)
    largo, penetracion = 16.0, 16.0 - PLACA
    assert penetracion >= 2 / 3 * largo
    assert z0 == pytest.approx(18 - penetracion, abs=0.05) and z0 > 0  # no asoma por detrás
    assert z1 == pytest.approx(18 + PLACA + 4.0, abs=0.05)
    _acceso_ok(doc)


def test_d4_metalmecanica_sin_set_material_no_es_madera():
    """La palabra «Tablero» no vuelve madera una pieza en una máquina de acero (guarda)."""
    doc = Document("d4-acero")
    w, p = _tablero(doc)
    cid = doc.execute("join_bolted", {"a": p, "b": w, "size": "M6", "count": 2})
    assert next(c for c in doc.commands if c["id"] == cid)["params"]["madera"] == []
    assert any(f.component == "TUERCA-M6" for f in _de(doc, cid).values())


def test_d4_tornillo_reglas_puras():
    t = fj.tornillo_madera("M8", 3.0, 100.0)
    assert t.largo - 3.0 >= 6 * 8 and t.largo - 3.0 >= 2 / 3 * t.largo  # prefiere ≥ 6·d
    with pytest.raises(ValueError, match="no admite"):
        fj.tornillo_madera("M6", 10.0, 12.0)


# ── D5: la puerta no avisa lo que join_bolted declaró ───────────────────────────────────


@pytest.mark.parametrize("caso", ["tubo", "c", "madera"])
def test_d5_la_puerta_no_avisa_tornilleria_sin_union_de_join_bolted(caso):
    doc = Document("d5")
    if caso == "madera":
        doc.set_vertical("carpinteria")
    base, p = {"tubo": _tubo, "c": _c_chapa, "madera": _tablero}[caso](doc)
    doc.execute("ground", {"name": "piso", "feature": base})
    doc.execute("join_bolted", {"a": base, "b": p, "size": "M6", "count": 2})
    kw = delivery_inputs(doc, expand=lambda ids: ids)
    assert kw["tornilleria_flotante"] == []
    assert kw["soundness"]["floating"] == []
    _acceso_ok(doc)


def test_d5_un_perno_suelto_a_mano_sigue_avisando():
    doc = Document("d5-mano")
    c, p = _c_chapa(doc)
    doc.execute("ground", {"name": "piso", "feature": c})
    doc.execute("join_bolted", {"a": c, "b": p, "size": "M6", "count": 2})
    suelto = doc.execute("insert_component", {"component": "PERNO-HEX-M8", "name": "Perno M8",
                                              "position": {"x": 250, "z": 100}})
    assert delivery_inputs(doc, expand=lambda ids: ids)["tornilleria_flotante"] == [suelto]


# ── D6: '$k' dice desde dónde numera ────────────────────────────────────────────────────


def test_d6_dollar_cero_dice_que_se_numera_desde_1():
    doc = Document("d6")
    with pytest.raises(CommandError) as exc:
        execute_batch(doc, [{"type": "create_box", "params": {}},
                            {"type": "transform", "params": {"feature": "$0"}}])
    assert "se numeran desde $1 (el primer comando del lote)" in str(exc.value)
    with pytest.raises(CommandError, match=r"el lote tiene 1 acción\(es\), \$1…\$1"):
        execute_batch(doc, [{"type": "transform", "params": {"feature": "$4"}}])
    assert doc.commands == [] and doc.scene == {}


# ── El log viejo, el sello y la vista previa ────────────────────────────────────────────


def test_log_viejo_regenera_con_la_misma_tornilleria():
    """Un join_bolted guardado antes de F1 (sin `criterio`) regenera con el criterio 1: el
    M6×65 por la caja del tubo y de la C (lo que halló varias-maquinas F4), byte a byte."""
    doc = Document("legado")
    doc.commands = [
        {"id": "c1", "type": "insert_component", "params": {
            "component": "TUBO-2X2", "length": 600, "name": "Larguero", "rotation": {"y": 90}}},
        {"id": "c2", "type": "create_box", "params": {
            "name": "Placa", "width": 120, "depth": 40, "height": 1.5, "position": {"z": 26.15}}},
        {"id": "c3", "type": "join_bolted", "params": {"a": "c1", "b": "c2", "size": "M6",
                                                       "count": 2}},
    ]
    doc._seq = 3
    doc.regenerate()
    assert "criterio" not in doc.commands[2]["params"]  # el replay no sella
    nombres = sorted((fid, f.name) for fid, f in _de(doc, "c3").items())
    assert nombres == [("c3_perno1", "Perno M6×65 DIN 933"), ("c3_perno2", "Perno M6×65 DIN 933"),
                       ("c3_tuerca1", "Tuerca M6 DIN 934"), ("c3_tuerca2", "Tuerca M6 DIN 934")]
    assert _caja(doc.scene["c3_tuerca1"])[2] == pytest.approx(-30.4, abs=0.01)
    assert doc.scene["c1"].shape.volume == pytest.approx(365130.1, abs=0.5)  # dos paredes
    assert doc.fasteners["jb_c3"] == {"name": "jb_c3", "a": "c1", "b": "c2", "kind": "perno",
                                      "size": "M6", "qty": 2, "nota": "Unión atornillada",
                                      "command_id": "c3"}
    # editar un comando viejo NO lo pasa al criterio nuevo (el edit no sella)
    doc.edit("c3", {"a": "c1", "b": "c2", "size": "M6", "count": 3})
    assert "criterio" not in doc.commands[2]["params"]
    assert len([f for f in _de(doc, "c3").values() if f.component == "PERNO-HEX-M6"]) == 3


def test_el_criterio_queda_fuera_del_schema():
    from apolo.commands.models_union import JoinBoltedParams

    props = JoinBoltedParams.model_json_schema()["properties"]
    assert "criterio" not in props and "madera" not in props


def test_la_vista_previa_sella_igual_que_la_ejecucion():
    doc = Document("preview")
    doc.set_vertical("carpinteria")
    w, p = _tablero(doc)
    escena, nuevos = doc.preview([{"type": "join_bolted",
                                   "params": {"a": p, "b": w, "size": "M6", "count": 2}}])
    assert {f.component for fid, f in escena.items() if f.command_id == nuevos[0]} == {
        "TIRAFONDO-HEX-6"}
    assert doc.commands[-1]["type"] == "create_box"  # el documento no cambió
