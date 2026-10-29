"""`create_belt_conveyor` F1b (plan faja-larga-en-tramos, D7–D9).

- D7: `lado_abierto` saca la pared de la guarda lateral del costado de los operarios: queda una
  guarda cubre-ranura a ras de la banda a lo largo de la faja y la guarda en L sólo en la cabeza;
  la puerta (sondas ISO 13857 con el brazo doblado) sigue dando los peligros resguardados, y sin
  cualquiera de las dos piezas no;
- D8 (criterio 7): la placa de la pata lleva la tuerca del pie soldada por debajo y el vástago su
  contratuerca, con llave;
- D9 (criterio 7): los brazos del motor a tope contra la pata, con la cuenta del voladizo; si no
  da, tornapuntas;
- un log v5 y uno v6 (criterio 6) regeneran como antes de la F1b (cifras medidas con ese código).
"""

from __future__ import annotations

import pytest
from build123d import Vector

from apolo.commands.registry import REGISTRY
from apolo.doc import Document
from apolo.library.belt_conveyor_plan import caja
from apolo.library.bom import bom_from_scene
from apolo.library.checks import interference_report


def _faja(**params):
    d = Document()
    cid = d.execute("create_belt_conveyor", params)
    return d, cid


def _rol(d, rol: str) -> list[str]:
    return sorted(f.id for f in d.scene.values() if f.name.split(" · ")[-1].startswith(rol))


def _bb(d, fid):
    return d.scene[fid].shape.bounding_box()


def _plan(d):
    from apolo.library.belt_conveyor import belt_conveyor_parts

    q = REGISTRY["create_belt_conveyor"].model.model_validate(d.commands[0]["params"])
    return belt_conveyor_parts(q.largo, q.ancho_banda, q.altura, q.tambor_motriz, q.tambor_cola,
                               q.tubo, None if q.tensor == "ninguno" else q.tensor,
                               None if q.motor == "ninguno" else q.motor, q.espesor_banda,
                               q.guardas, q.cierres, q.tramo_max, q.criterio, q.lado_abierto)


@pytest.fixture(scope="module")
def clasificadora():
    """La faja del piloto clasificadora-manual: 10,2 m entre tambores, banda a 850 mm, en tramos
    de 6 m y abierta del lado de los operarios (−Y; el motor va del lado +Y). Con el criterio de
    la F1b (7): el 8 parte las guardas en paños (`test_belt_conveyor_f1c.py`)."""
    return _faja(largo=10200, altura=850, lado_abierto="-y", criterio=7)


def test_el_sello_pone_el_criterio_7_y_lado_abierto_es_visible():
    d, _ = _faja()
    p = d.commands[0]["params"]
    assert p["criterio"] == 10 and p["tramo_max"] == 6000  # F1c: al 8; faja-compacta: al 9 y 10
    props = REGISTRY["create_belt_conveyor"].model.model_json_schema()["properties"]
    assert props["lado_abierto"]["enum"] == ["ninguno", "+y", "-y"]
    assert REGISTRY["create_belt_conveyor"].model.model_validate({}).lado_abierto == "ninguno"


# ------------------------------------------------------------------ D7: lado abierto
def test_lado_abierto_saca_la_pared_de_ese_lado_y_deja_la_del_otro(clasificadora):
    d, cid = clasificadora
    assert _rol(d, "Guarda cubre-ranura") == [f"{cid}_guarda1_1", f"{cid}_guarda1_2"]
    assert _rol(d, "Guarda lateral de cabeza") == [f"{cid}_guarda1_cabeza"]
    assert _rol(d, "Guarda lateral (") == [f"{cid}_guarda2_1", f"{cid}_guarda2_2"]
    # del lado abierto nada pasa la cara de la banda + el ala sobre el larguero, salvo en la cabeza
    cabeza = _bb(d, f"{cid}_guarda1_cabeza")
    for fid in _rol(d, "Guarda cubre-ranura"):
        assert _bb(d, fid).max.Z <= 850 - 4 + 3 + 3 + 1e-6  # 2 mm sobre la banda (el ala)
        assert _bb(d, fid).max.X < cabeza.min.X
    assert cabeza.max.Z == pytest.approx(849 + 150) and cabeza.size.X < 600
    assert _bb(d, f"{cid}_guarda2_1").max.Z == pytest.approx(849 + 150)
    # el labio tapa la ranura banda ↔ larguero A RAS de la banda, a 3 mm de su borde
    cubre = d.scene[f"{cid}_guarda1_1"].shape
    banda = d.scene[f"{cid}_banda"].shape
    assert cubre.is_inside(Vector(-2000, -(300 + 15), 850 - 1.5))
    sobre = cubre & caja(-4000, -1000, -333, -303, 850 + 0.01, 900)
    assert sobre.volume < 1e-6
    assert cubre.distance_to(banda) == pytest.approx(3.0, abs=0.05)
    # cada una atornillada a su larguero
    por_pieza = {f["a"]: f for f in d.fasteners.values()}
    for fid in _rol(d, "Guarda cubre-ranura") + _rol(d, "Guarda lateral"):
        lado = "rail1" if fid.startswith(f"{cid}_guarda1") else "rail2"
        assert por_pieza[fid]["kind"] == "perno" and por_pieza[fid]["b"].startswith(f"{cid}_{lado}")


def test_la_clasificadora_abierta_sin_interferencias_y_a_tierra(clasificadora):
    from apolo.assembly.connectivity import build_graph, soundness_report

    d, _ = clasificadora
    r = interference_report(d.scene)
    assert not r["truncado"]
    assert [(i["a"], i["b"], i["volumen_mm3"]) for i in r["interferencias"]] == []
    rep = soundness_report(build_graph(d.scene, d.joints, d.mates, d.fasteners, d.grounds))
    assert rep["floating"] == [] and rep["n_grounded"] == len(d.scene)


def test_la_puerta_no_alcanza_las_cunas_por_el_lado_abierto():
    """Sondas ISO 13857 (rectas y con el brazo doblado, `controles_seguridad`): abierta por −Y la
    faja de 4 m sigue con sus 5 peligros resguardados. Sin la pared de cabeza la mano empuja el
    borde de la banda hasta la cuña de entrada del motriz; sin el cubre-ranura se llega por la
    ranura a la de cola: las dos piezas son lo mínimo."""
    from apolo.services.calidad_seguridad import controles_seguridad

    d, cid = _faja(lado_abierto="-y")
    it = controles_seguridad(d, electrico=False)["items"][0]
    assert it["estado"] == "OK", it["detalle"]
    # (con el criterio 8 el cubre-ranura sale en paños: se quitan todos)
    for quita, tambor in (([f"{cid}_guarda1_cabeza"], "Tambor motriz"),
                          (_rol(d, "Guarda cubre-ranura"), "Tambor de cola")):
        sin = Document.from_apolo_bytes(d.to_apolo_bytes())
        for fid in quita:
            del sin.scene[fid]
        it = controles_seguridad(sin, electrico=False)["items"][0]
        assert it["estado"] == "FALLA" and tambor in it["detalle"], it["detalle"]


# ------------------------------------------------------------------ D8: pie roscado de verdad
def test_cada_pie_con_tuerca_soldada_y_contratuerca_con_llave():
    from apolo.library.acceso_herramienta import tool_access_report

    d, cid = _faja()
    patas = _rol(d, "Pata (")
    assert len(_rol(d, "Tuerca soldada del pie")) == len(_rol(d, "Contratuerca del pie")) == \
        len(patas)
    filas = {r["ref"]: r for r in bom_from_scene(d.scene)}
    assert filas["TUERCA-M12"]["cantidad"] == 2 * len(patas)
    # la pila: disco → contratuerca → tuerca soldada → placa (barreno de paso Ø13,5) → pata
    placa, pie = d.scene[f"{cid}_placa1"].shape, _bb(d, f"{cid}_foot1")
    tuerca, contra = _bb(d, f"{cid}_tuerca_pie1"), _bb(d, f"{cid}_contra_pie1")
    assert contra.max.Z == pytest.approx(tuerca.min.Z) and tuerca.max.Z == pytest.approx(
        placa.bounding_box().min.Z)
    assert contra.min.Z - 14.0 == pytest.approx(15.0)  # mitad del recorrido: ±15 mm
    assert pie.max.Z > placa.bounding_box().max.Z      # el vástago pasa la placa
    c = placa.bounding_box().center()
    assert not placa.is_inside(Vector(c.X + 6.6, c.Y, c.Z))  # paso Ø13,5, no un Ø12 «roscado»
    assert placa.is_inside(Vector(c.X + 7.0, c.Y, c.Z))
    notas = {f["name"].split(f"{cid}_", 1)[1]: f for f in d.fasteners.values()}
    assert notas["tuerca_placa1"]["kind"] == "soldadura"
    assert notas["pie1"]["b"] == f"{cid}_tuerca_pie1" and "±15 mm" in notas["pie1"]["nota"]
    assert "contratuerca M12" in notas["contra_pie1"]["nota"]
    rep = tool_access_report(d.scene)
    malas = {e["id"] for e in rep["sin_herramienta"] + rep["solo_boca"]}
    assert not malas & set(_rol(d, "Contratuerca del pie")), rep


# ------------------------------------------------------------------ D9: base del motor
def test_los_brazos_del_motor_a_tope_contra_la_pata_y_la_cuenta_da():
    d, cid = _faja()
    leg = d.scene[f"{cid}_leg4"].shape
    for k in (1, 2):
        brazo = d.scene[f"{cid}_brazo_motor{k}"].shape
        assert brazo.distance_to(leg) == pytest.approx(0.0, abs=1e-6)
        assert brazo.bounding_box().min.Y == pytest.approx(leg.bounding_box().min.Y)
    notas = {f["name"].split(f"{cid}_", 1)[1]: f for f in d.fasteners.values()}
    assert notas["brazo1_pata"]["kind"] == notas["brazo2_pata"]["kind"] == "soldadura"
    assert not _rol(d, "Tornapunta")
    calc = _plan(d).calculos["base_motor"]
    assert calc["ok"] and not calc["tornapuntas"]
    assert calc["corrimiento_mm"] == pytest.approx(0.216, abs=0.01)
    assert calc["tau_soldadura_mpa"] == pytest.approx(20.8, abs=0.5)
    assert calc["tau_soldadura_mpa"] < calc["tau_adm_mpa"]
    assert calc["sigma_brazo_mpa"] < calc["sigma_adm_mpa"]


def test_con_un_motor_de_mas_par_la_cuenta_pide_tornapuntas():
    d, cid = _faja(motor="MOTOR-150")
    plan = _plan(d)
    sin = plan.calculos["base_motor_sin_tornapuntas"]
    assert not sin["ok"] and sin["corrimiento_mm"] > sin["corrimiento_adm_mm"]
    calc = plan.calculos["base_motor"]
    assert calc["ok"] and calc["tornapuntas"]
    tps = _rol(d, "Tornapunta de la base del motor")
    assert len(tps) == 2
    leg = d.scene[f"{cid}_leg4"].shape
    for k, fid in enumerate(tps, start=1):
        assert d.scene[fid].shape.distance_to(leg) == pytest.approx(0.0, abs=1e-6)
        assert d.scene[fid].shape.distance_to(d.scene[f"{cid}_brazo_motor{k}"].shape) == \
            pytest.approx(0.0, abs=1e-6)
    assert interference_report(d.scene)["interferencias"] == []


@pytest.mark.parametrize("motor", ["MOTOR-037", "MOTOR-075", "MOTOR-150-EH"])
def test_la_cuenta_da_con_cada_motor_del_catalogo(motor):
    d, _ = _faja(motor=motor)
    assert _plan(d).calculos["base_motor"]["ok"]
    assert interference_report(d.scene)["interferencias"] == []


# ------------------------------------------------------------------ logs viejos
@pytest.mark.parametrize("params, piezas, uniones, volumen", [
    ({"criterio": 6}, 70, 91, 97805836.0),
    ({"criterio": 6, "largo": 10200, "altura": 850}, 148, 198, 197434378.6),
], ids=["4m", "10m"])
def test_un_log_v6_criterio_6_regenera_igual(params, piezas, uniones, volumen):
    """Una faja sellada con el criterio 6 (la F1, antes de la F1b): mismas piezas, uniones y
    volumen que con el código de antes (medidos), sin las tuercas del pie ni la base nueva."""
    d, cid = _faja(**params)
    viejo = Document.from_apolo_bytes(d.to_apolo_bytes())
    assert "lado_abierto" not in viejo.commands[0]["params"]
    assert len(viejo.scene) == piezas and len(viejo.fasteners) == uniones
    assert sum(f.shape.volume for f in viejo.scene.values()) == pytest.approx(volumen, rel=1e-7)
    assert not _rol(viejo, "Tuerca soldada") and not _rol(viejo, "Tornapunta")
    (u,) = [f for f in viejo.fasteners.values() if f["name"] == f"{cid}_pie1"]
    assert u["nota"] == "vástago M12 roscado en la placa: girarlo nivela ±20 mm"
    assert _bb(viejo, f"{cid}_placa1").min.Z == pytest.approx(34.0)
    assert _bb(viejo, f"{cid}_brazo_motor1").min.Y == pytest.approx(386.8, abs=0.01)


V5_4M = (66, 85, 94985066.5)  # piezas, uniones, volumen: la de 4 m v5 con el código de antes


def test_un_log_v5_regenera_igual():
    """Sin `tramo_max`, `criterio` ni `lado_abierto` (log v5): la v5 tal cual (cifras medidas con
    el código de antes de la F1b)."""
    d, cid = _faja()
    for k in ("tramo_max", "criterio"):
        del d.commands[0]["params"][k]
    viejo = Document.from_apolo_bytes(d.to_apolo_bytes())
    assert len(viejo.scene) == V5_4M[0] and len(viejo.fasteners) == V5_4M[1]
    assert sum(f.shape.volume for f in viejo.scene.values()) == pytest.approx(V5_4M[2], rel=1e-7)
    assert _rol(viejo, "Guarda lateral (") == [f"{cid}_guarda1", f"{cid}_guarda2"]

