"""`create_belt_conveyor` F1 de faja-compacta (D1–D6; criterio 9, v7).

- D1/D2: motorreductor sinfín de eje hueco (NMRV) calzado en el eje motriz, motor a lo largo del
  larguero, brazo de reacción a la pata de cabeza; calce, relación y potencia con su cuenta;
- D3: tensor «placa-ranurada» con la ranura de la carrera calculada;
- D4: la carrera que pide el lazo y el carro de la UCT al inicio de ella;
- D5: el sello pone el criterio 9 y lo sellado con el 8 regenera igual;
- D6: cada pieza nueva con su unión, sin interferencias (sin exclusiones) y a tierra; cuánto
  sobresale el conjunto motriz del larguero, contra el coaxial.
"""

from __future__ import annotations

import hashlib

import pytest

from apolo.commands.registry import REGISTRY
from apolo.doc import Document
from apolo.library.checks import interference_report

NMRV = {"motor": "NMRV-063", "velocidad": 0.5}


def _faja(**params):
    d = Document()
    cid = d.execute("create_belt_conveyor", params)
    return d, cid


def _plan(d):
    from apolo.library.belt_conveyor import belt_conveyor_parts

    q = REGISTRY["create_belt_conveyor"].model.model_validate(d.commands[0]["params"])
    return belt_conveyor_parts(q.largo, q.ancho_banda, q.altura, q.tambor_motriz, q.tambor_cola,
                               q.tubo, None if q.tensor == "ninguno" else q.tensor,
                               None if q.motor == "ninguno" else q.motor, q.espesor_banda,
                               q.guardas, q.cierres, q.tramo_max, q.criterio, q.lado_abierto,
                               q.velocidad)


def _armada(d) -> None:
    """Sin interferencias (sin exclusiones: un choque dentro del super-comando) y todo a tierra."""
    from apolo.assembly.connectivity import build_graph, soundness_report

    r = interference_report(d.scene)
    assert not r["truncado"]
    assert [(i["a"], i["b"], i["volumen_mm3"]) for i in r["interferencias"]] == []
    rep = soundness_report(build_graph(d.scene, d.joints, d.mates, d.fasteners, d.grounds))
    assert rep["floating"] == [] and rep["n_grounded"] == len(d.scene)


def _contacto_real(d) -> None:
    """Lo declarado se toca (`union.contacto_real`, plan uniones-que-tocan)."""
    from apolo.library.calidad import contacto as ct
    from apolo.services.calidad_contacto import uniones_medidas

    res = ct.contacto_real({"uniones": uniones_medidas(d)})
    assert res["estado"] == "OK", res.get("detalle")


@pytest.fixture(scope="module")
def nmrv():
    return _faja(**NMRV)


@pytest.fixture(scope="module")
def placa():
    return _faja(tensor="placa-ranurada")


def test_el_sello_pone_el_criterio_9():
    from apolo.commands.exec_faja import CRITERIO_NUEVO

    d, _ = _faja()
    assert CRITERIO_NUEVO == 9 and d.commands[0]["params"]["criterio"] == 9


# ------------------------------------------------------------------ D1, D2: NMRV
def test_nmrv_calzado_sin_acople_ni_base(nmrv):
    d, cid = nmrv
    motor = d.scene[f"{cid}_motor"]
    assert motor.component == "NMRV-063"
    for suf in ("acople", "base_motor", "mensula_motor", "brazo_motor1", "guarda_acople"):
        assert f"{cid}_{suf}" not in d.scene
    assert {f"{cid}_brazo_reaccion", f"{cid}_soporte_brazo"} <= set(d.scene)
    # el eje motriz entra en el eje hueco y termina antes de la tapa del reductor
    eje = d.scene[f"{cid}_tambor_motriz"].shape.bounding_box()
    caja = motor.shape.bounding_box()
    assert caja.min.Y < eje.max.Y < caja.max.Y
    # el motor, acostado hacia la cola (−X) y por fuera del larguero (+Y, «ninguno»)
    assert caja.min.X < 1650.0 and caja.min.Y > 385.8
    f = {x["name"].split(f"{cid}_", 1)[1]: x for x in d.fasteners.values()}
    assert f["motor_eje"]["kind"] == "contacto" and "chaveta 8x7x50 DIN 6885" in f["motor_eje"]["nota"]
    assert f["brazo_motor"]["kind"] == f["brazo_soporte"]["kind"] == "perno"
    assert f["soporte_pata"]["b"] == f"{cid}_leg4" and f["soporte_pata"]["kind"] == "soldadura"


def test_nmrv_la_cuenta(nmrv):
    """i = 20 de la serie (85,5 rpm → 0,509 m/s), 0,65 kW pedidos (CEMA, η 0,75) contra 1,1 kW;
    el brazo con 2 × el par nominal de salida."""
    d, _ = nmrv
    plan = _plan(d)
    m = plan.calculos["motorreductor"]
    assert m["ok"] and m["relacion"] == 20.0 and m["v_m_s"] == pytest.approx(0.509, abs=1e-3)
    assert m["p_req_kw"] == pytest.approx(0.651, abs=0.01) and m["p_motor_kw"] == 1.1
    b = plan.calculos["brazo_reaccion"]
    assert b["ok"] and b["par_arranque_nm"] == pytest.approx(2.0 * m["par_salida_nm"], abs=0.2)
    assert b["sigma_brazo_mpa"] <= b["sigma_adm_mpa"] and b["tau_soldadura_mpa"] <= b["tau_adm_mpa"]


def test_nmrv_armada_y_lo_declarado_se_toca(nmrv):
    d, _ = nmrv
    _armada(d)
    _contacto_real(d)


def test_nmrv_del_lado_opuesto_a_los_operarios():
    d, cid = _faja(lado_abierto="+y", **NMRV)
    caja = d.scene[f"{cid}_motor"].shape.bounding_box()
    assert caja.max.Y < -385.8 and caja.min.X < 1650.0
    assert d.fasteners[f"{cid}_soporte_pata"]["b"] == f"{cid}_leg3"
    _armada(d)


def test_nmrv_que_no_calza_da_error_con_los_que_calzan():
    with pytest.raises(Exception) as e:
        _faja(motor="NMRV-090", velocidad=0.5)
    assert "no calza en el eje Ø25" in str(e.value) and "NMRV-050, NMRV-063" in str(e.value)


def test_nmrv_chico_da_error_con_el_siguiente():
    with pytest.raises(Exception) as e:
        _faja(motor="NMRV-050", velocidad=0.5)
    assert "no alcanza" in str(e.value) and "usa el NMRV-063" in str(e.value)


def test_nmrv_sin_velocidad_la_pide():
    with pytest.raises(Exception) as e:
        _faja(motor="NMRV-063")
    assert "velocidad" in str(e.value)


def test_nmrv_en_una_faja_de_12_m_en_dos_tramos():
    """La de 12 m (dos tramos de 6 m) con 50 kg/m de diseño pide 0,97 kW a 0,25 m/s (i = 40)."""
    d, cid = _faja(largo=12000, motor="NMRV-063", velocidad=0.25)
    assert f"{cid}_rail1_2" in d.scene
    m = _plan(d).calculos["motorreductor"]
    assert m["relacion"] == 40.0 and m["p_req_kw"] <= 1.1
    _armada(d)
    _contacto_real(d)


def _sobresale(d, cid, sufijos) -> float:
    from apolo.library.belt_conveyor_cotas import BANDA_A_LARGUERO

    q = d.commands[0]["params"]
    y_out = q.get("ancho_banda", 600) / 2.0 + BANDA_A_LARGUERO + 50.8
    return max(abs(v) for k in sufijos if f"{cid}_{k}" in d.scene
               for v in (d.scene[f"{cid}_{k}"].shape.bounding_box().max.Y,
                         d.scene[f"{cid}_{k}"].shape.bounding_box().min.Y)) - y_out


def test_d6_cuanto_sobresale_el_conjunto_motriz(nmrv):
    """Medido sobre la escena, de la cara exterior del larguero a lo más lejano del accionamiento:
    el NMRV-063 sale 222,6 mm (meta del plan ≤ 200: lo que pasa lo explica la Bitácora) contra
    776,4 mm del coaxial MOTOR-150-EH con acople, base y guarda."""
    d, cid = nmrv
    accionamiento = ("motor", "brazo_reaccion", "soporte_brazo", "acople", "guarda_acople",
                     "base_motor", "mensula_motor", "brazo_motor1", "brazo_motor2")
    compacto = _sobresale(d, cid, accionamiento)
    dc, cc = _faja()
    coaxial = _sobresale(dc, cc, accionamiento)
    assert compacto == pytest.approx(222.6, abs=0.5)
    assert coaxial == pytest.approx(776.4, abs=0.5)
    assert compacto < 0.3 * coaxial


# ------------------------------------------------------------------ D3, D4: placa ranurada
def test_placa_ranurada_con_la_carrera_del_lazo(placa):
    """El lazo de 8351 mm pide 103,5 mm de lazo (1 % + 20) = 51,8 mm de tensor con factor 2: la
    ranura de 55 mm; la placa tapa la ranura del larguero en toda la carrera."""
    from apolo.library.belt_conveyor_placa import PLACA_T

    d, cid = placa
    calc = _plan(d).calculos["carrera_tensor"]
    assert calc["tensor"] == "placa-ranurada" and calc["carrera_mm"] == 55.0
    assert calc["pide_mm"] == pytest.approx(51.8, abs=0.05) and calc["lazo_mm"] == pytest.approx(
        8350.6, abs=0.5)
    for suf in ("chum_c1", "placa_c1", "oreja_c1", "tapa_c1"):
        assert f"{cid}_{suf}" in d.scene
    assert f"{cid}_tensor1" not in d.scene
    pb = d.scene[f"{cid}_placa_c1"].shape.bounding_box()
    assert pb.size.Y == pytest.approx(PLACA_T)
    assert pb.min.X <= -2000.0 - 55.0 - 15.5 - 10.0 + 1e-6  # tapa la ranura al inicio
    nota = d.fasteners[f"{cid}_placa_c1_larg"]["nota"]
    assert "espárragos M10x35 ISO 13918 soldados" in nota and "55 mm de carrera" in nota
    # el perno empujador, declarado con su largo (carrera + oreja + contratuerca + 2 hilos)
    emp = d.fasteners[f"{cid}_empuje_c1"]
    assert emp["kind"] == "perno" and emp["size"] == "M12"
    assert "M12x90 DIN 933" in emp["nota"] and "contratuerca" in emp["nota"]


def test_placa_ranurada_armada_y_reconocida_por_la_puerta(placa):
    from apolo.library.calidad.tensor import evaluar_lazo
    from apolo.services.calidad_tensores import lazos

    d, cid = placa
    _armada(d)
    _contacto_real(d)
    (lz,) = lazos(d, cadenas=False)
    assert {t["id"] for t in lz["tensores"]} == {f"{cid}_placa_c1", f"{cid}_placa_c2"}
    assert all(t["tipo"] == "plantilla" and t["carrera_mm"] == 55.0 for t in lz["tensores"])
    assert lz["tensores"][0]["factor_lazo"] == pytest.approx(2.0, abs=0.02)
    assert evaluar_lazo(lz)["carrera"][0] == "OK"


def test_uct_con_el_carro_al_inicio_de_su_carrera():
    """El agujero del carro (el origen del builder) en el eje del tambor de cola (−largo/2); el
    marco, corrido media carrera hacia la cola; la puerta lee el tambor en el agujero."""
    from apolo.services.calidad_tensores import lazos

    d, cid = _faja()
    t = d.scene[f"{cid}_tensor1"]
    assert t.matrix[0][3] == pytest.approx(-2000.0)
    bb = t.shape.bounding_box()
    assert (bb.min.X + bb.max.X) / 2.0 == pytest.approx(-2000.0 - 75.0, abs=0.01)
    (lz,) = lazos(d, cadenas=False)
    assert all(x["factor_lazo"] == pytest.approx(2.0, abs=0.02) for x in lz["tensores"])
    calc = _plan(d).calculos["carrera_tensor"]
    assert calc["carrera_mm"] == 150.0 and calc["pide_mm"] < 150.0
    # la ranura del larguero, con lo que pide el lazo: el soporte del carro (143 mm) la tapa
    assert calc["ranura_mm"] == 55.0
    rail = d.scene[f"{cid}_rail2"].shape
    y_pared = rail.bounding_box().max.Y - 1.0          # dentro de la pared exterior del tubo
    z_eje = d.scene[f"{cid}_tambor_cola"].shape.bounding_box().center().Z
    assert not rail.is_inside((-2000.0 - 50.0, y_pared, z_eje))   # la ranura, hasta −2070,5…
    assert rail.is_inside((-2000.0 - 80.0, y_pared, z_eje))       # …no la de ficha (−2090,5)
    soporte = 317.0 - 24.0 - 150.0
    assert 55.0 + 15.5 <= soporte / 2.0  # el soporte del carro la cubre al inicio y al final
    _armada(d)


def test_uct_que_no_alcanza_da_error_y_la_placa_si():
    """14 m: el lazo pide 151,8 mm al tensor; la UCT205-150 no da y la placa ranurada (155 mm) sí."""
    with pytest.raises(Exception) as e:
        _faja(largo=14000)
    assert "UCT205-150 tiene 150" in str(e.value) and "placa-ranurada" in str(e.value)
    d, cid = _faja(largo=14000, tensor="placa-ranurada")
    assert _plan(d).calculos["carrera_tensor"]["carrera_mm"] == 155.0


def test_el_builder_uct_sin_avance_es_el_de_siempre():
    from apolo.library.builders_rodaje import take_up_unit

    p = {"d": 25.0, "L": 317.0, "H": 199.0, "A": 50.0, "carrera": 150.0, "tm": 16.0}
    a, b = take_up_unit(**p)(), take_up_unit(**p, avance=0.0)()
    assert a.volume == pytest.approx(b.volume, rel=1e-12)
    assert a.volume == pytest.approx(1832185.952, rel=1e-9)  # el de antes de faja-compacta
    assert len(a.faces()) == len(b.faces())
    c = take_up_unit(**p, avance=75.0)()
    # el mismo soporte y el marco corrido: sólo el tornillo de ajuste es 75 mm más corto
    assert c.volume == pytest.approx(a.volume - 3.141592653589793 * 8.0 ** 2 * 75.0, rel=1e-6)
    assert c.bounding_box().min.X == pytest.approx(-75.0 - 317.0 / 2.0)


# ------------------------------------------------------------------ D6: la puerta
def test_d6_la_puerta_del_nmrv_con_placa_sin_falla_nueva():
    """La puerta entera (en proceso: gravedad y marcha reales) sobre la de 4 m con NMRV-063 y
    placa ranurada, con los requisitos y las funciones del testigo de la faja y SIN sus
    justificaciones: la única FALLA es la de la faja del criterio 8 en las mismas condiciones
    (`diseno.sin_sobrantes`, tapas que la plantilla pone y el testigo justifica), y ninguna pieza
    nueva sobra. Las demás variantes (UCT, operarios a +y, 12 m) se midieron en la Bitácora."""
    import importlib.util
    from pathlib import Path

    ruta = Path(__file__).resolve().parents[1] / "scripts" / "testigos.py"
    spec = importlib.util.spec_from_file_location("testigos_script", ruta)
    tg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tg)

    d = Document("faja-compacta")
    d.execute("create_belt_conveyor", {"tensor": "placa-ranurada", **NMRV})
    d.set_requirements(dict(tg.REQUISITOS))
    d.funciones = [dict(f) for f in tg.FUNCIONES_FAJA]
    r = tg.correr_en_proceso(d)
    est = {i["id"]: i for i in r["items"]}
    fallas = sorted(k for k, i in est.items() if i["estado"] == "FALLA")
    assert fallas == ["diseno.sin_sobrantes"], [(k, est[k].get("detalle")) for k in fallas]
    sobran = est["diseno.sin_sobrantes"]["detalle"]
    for nueva in ("Motorreductor", "Brazo de reacción", "Soporte del brazo", "Placa ranurada",
                  "Oreja del tensor"):
        assert nueva not in sobran
    for iid in ("union.contacto_real", "transmision_flexible.tension", "riesgos.partes_moviles",
                "union.acceso_herramienta", "accionamiento.factor_servicio", "entrega.semaforo",
                "entrega.gravedad"):
        assert est[iid]["estado"] == "OK", (iid, est[iid].get("detalle"))


# ------------------------------------------------------------------ D5: lo sellado antes
def _huella(doc) -> tuple:
    notas = sorted({f.get("nota") or "" for f in doc.fasteners.values()})
    return (len(doc.scene), len(doc.fasteners),
            round(sum(f.shape.volume for f in doc.scene.values()), 1),
            hashlib.sha1("|".join(notas).encode()).hexdigest()[:10])


@pytest.mark.parametrize("params, huella", [
    ({"criterio": 8}, (89, 116, 96491369.4, "ec82acaac6")),
    ({"criterio": 8, "largo": 12000, "lado_abierto": "-y"}, (224, 293, 209942916.8, "fe34cf2ded")),
    ({"criterio": 8, "tensor": "ninguno"}, (89, 116, 90553806.6, "fa26127f73")),
], ids=["8-4m", "8-12m", "8-sin-tensor"])
def test_lo_sellado_con_el_8_regenera_igual(params, huella):
    """Piezas, uniones, volumen y notas medidos con el código de antes de faja-compacta."""
    d, _ = _faja(**params)
    viejo = Document.from_apolo_bytes(d.to_apolo_bytes())
    assert _huella(viejo)[:2] == huella[:2]
    assert _huella(viejo)[2] == pytest.approx(huella[2], rel=1e-7)
    assert _huella(viejo)[3] == huella[3]
