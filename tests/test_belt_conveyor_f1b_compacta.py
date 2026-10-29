"""`create_belt_conveyor` F1b de faja-compacta (D7–D12; criterio 10, v8).

- D7: la plantilla no rechaza un sinfín por la carga SUPUESTA (aviso); sólo el calce es error;
- D8: la ranura de la placa sin el tope del perno de catálogo (varilla roscada), hasta el tope
  GEOMÉTRICO de la cola, medido y escrito; más allá, error que lo dice;
- D9: la vida L10 lee las rpm de la relación elegida (la «i = N» del nombre) y la velocidad sale
  con el radio de la simulación;
- D10: η = 0,75 como criterio de diseño (sin ficha por relación);
- D11: una estación de patas a cada lado de cada empalme y la cuenta del tramo suelto;
- D12: el empalme de campo de la banda, en la BOM y reconocido por la puerta;
- un log del criterio 9 regenera igual.
"""

from __future__ import annotations

import hashlib

import pytest

from apolo.commands.registry import REGISTRY
from apolo.doc import Document
from apolo.library.checks import interference_report

NMRV = {"motor": "NMRV-063", "velocidad": 0.5}
#: la faja de la mesa de sorteo de 36 puestos (36 × 800 + 600 mm; lazo de 59 m)
MESA_36 = {"largo": 29400, "ancho_banda": 600, "altura": 850, "tensor": "placa-ranurada",
           "motor": "NMRV-063", "velocidad": 0.254, "lado_abierto": "-y"}
#: lo que el encargo de la mesa pide (paquete de 10 kg, 500 mm, a 0,3 m/s)
ENCARGO = {"carga_kg": 10.0, "largo_paquete_mm": 500.0, "ancho_paquete_mm": 400.0,
           "velocidad_m_s": 0.3}


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
    """Sin interferencias (sin exclusiones), todo a tierra y lo declarado se toca."""
    from apolo.assembly.connectivity import build_graph, soundness_report
    from apolo.library.calidad import contacto as ct
    from apolo.services.calidad_contacto import uniones_medidas

    r = interference_report(d.scene)
    assert not r["truncado"]
    assert [(i["a"], i["b"], i["volumen_mm3"]) for i in r["interferencias"]] == []
    rep = soundness_report(build_graph(d.scene, d.joints, d.mates, d.fasteners, d.grounds))
    assert rep["floating"] == [] and rep["n_grounded"] == len(d.scene)
    res = ct.contacto_real({"uniones": uniones_medidas(d)})
    assert res["estado"] == "OK", res.get("detalle")


@pytest.fixture(scope="module")
def mesa36():
    d, cid = _faja(**MESA_36)
    return d, cid, _plan(d)


@pytest.fixture(scope="module")
def diez():
    d, cid = _faja(largo=10000)
    return d, cid, _plan(d)


def test_el_sello_pone_el_criterio_10():
    from apolo.commands.exec_faja import CRITERIO_NUEVO

    d, _ = _faja()
    assert CRITERIO_NUEVO == 10 and d.commands[0]["params"]["criterio"] == 10
    assert REGISTRY["create_belt_conveyor"].version == 8


# ------------------------------------------------------------------ D7, D9, D10: el sinfín
def test_d7_el_sinfin_chico_no_se_rechaza_por_la_carga_supuesta():
    """El NMRV-050 a 0,5 m/s en 4 m pedía 1,09 kW con 50 kg/m supuestos (error en el criterio 9):
    ahora sale, con la cuenta en `ok: False` y su aviso, también en la nota del eje."""
    d, cid = _faja(motor="NMRV-050", velocidad=0.5)
    m = _plan(d).calculos["motorreductor"]
    assert m["ok"] is False and "SUPUESTA" in m["aviso"] and "engineering_check" in m["aviso"]
    assert "AVISO" in d.fasteners[f"{cid}_motor_eje"]["nota"]
    assert "η 0,75: criterio de diseño" in m["norma"]  # D10


def test_d7_el_calce_sigue_siendo_error():
    with pytest.raises(Exception) as e:
        _faja(motor="NMRV-090", velocidad=0.5)
    assert "no calza en el eje Ø25" in str(e.value)


def test_d9_la_relacion_en_el_nombre_y_el_radio_de_la_simulacion():
    """i = 20 con el radio de la CARA de la banda (exterior + espesor: el de
    `physics.banda.superficie_banda`, del eje al tope de la banda): 85,5 rpm → 0,544 m/s."""
    import math

    from apolo.library.rules_deteccion import detect_conveyor

    d, cid = _faja(**NMRV)
    plan = _plan(d)
    m = plan.calculos["motorreductor"]
    assert d.scene[f"{cid}_motor"].name.endswith("Motorreductor (i = 20)")
    eje = d.scene[f"{cid}_tambor_motriz"].shape.bounding_box().center().Z
    tope = d.scene[f"{cid}_banda"].shape.bounding_box().max.Z
    r_sim = tope - eje
    assert m["v_m_s"] == pytest.approx(m["n_tambor_rpm"] * math.pi * 2.0 * r_sim / 60000.0,
                                       abs=1e-3)
    assert m["relacion"] == 20.0 and m["v_m_s"] == pytest.approx(0.544, abs=1e-3)
    # la vida L10 y el par leen esas rpm (antes: «sin evaluar» sin rpm_salida declarada)
    assert detect_conveyor(d.scene, d.variables_resolved, d.fasteners)["rpm_motor"] == 85.5
    # lo declarado gana: el variador a 65 Hz de la mesa de sorteo
    d.execute("set_variable", {"name": "rpm_salida", "expression": "48.5"})
    assert detect_conveyor(d.scene, d.variables_resolved, d.fasteners)["rpm_motor"] == 48.5


def test_d9_la_placa_del_reductor_se_lee_del_nombre():
    from apolo.library.catalog import CATALOG
    from apolo.library.relacion_motor import relacion_del_nombre, rpm_salida

    assert relacion_del_nombre("Mesa · Motorreductor (i = 40)") == 40.0
    assert relacion_del_nombre("Motorreductor NMRV-063 i=7,5") == 7.5
    assert relacion_del_nombre("Motorreductor") is None
    assert rpm_salida(CATALOG["NMRV-063"], "Motorreductor (i = 40)") == pytest.approx(42.75)
    assert rpm_salida(CATALOG["NMRV-063"], "Motorreductor") is None
    assert rpm_salida(CATALOG["MOTOR-150-EH"], "x") == 188.0  # la ficha, como siempre


# ------------------------------------------------------------------ D8: la mesa de 36 puestos
def test_d8_la_mesa_de_36_puestos_regenera_con_la_placa_y_varilla(mesa36):
    """Lazo de 59 m: pide 305,8 mm de carrera; la ranura sale de 310 (el perno de catálogo llegaba
    a 165) con un empujador de varilla roscada, y el tope geométrico de esta cola está escrito."""
    d, cid, plan = mesa36
    calc = plan.calculos["carrera_tensor"]
    assert calc["lazo_mm"] == pytest.approx(59150.6, abs=1.0)
    assert calc["pide_mm"] == pytest.approx(305.8, abs=0.1)
    assert calc["carrera_mm"] == calc["ranura_mm"] == 310.0
    assert calc["tope_geometrico_mm"] >= 310.0 and calc["tope_por"]
    assert calc["empujador"] == "varilla roscada M12 DIN 976-1"
    nota = d.fasteners[f"{cid}_empuje_c1"]["nota"]
    assert "varilla roscada M12x" in nota and "DIN 976-1" in nota and "contratuerca" in nota
    _armada(d)


def test_d8_el_motor_lo_juzga_la_carga_del_encargo(mesa36):
    """Con 50 kg/m supuestos la plantilla avisa (2,55 kW contra 1,1); con el encargo de la mesa
    (paquetes de 10 kg cada 1 m) la regla de motorización da el NMRV-063 por bueno."""
    from apolo.library.rules import conveyor_engineering_check
    from apolo.library.rules_deteccion import detect_conveyor

    d, _cid, plan = mesa36
    m = plan.calculos["motorreductor"]
    assert m["ok"] is False and m["relacion"] == 40.0
    cv = detect_conveyor(d.scene, d.variables_resolved, d.fasteners)
    assert cv["rpm_motor"] == pytest.approx(42.75)
    checks = conveyor_engineering_check(cv, ENCARGO["carga_kg"], ENCARGO["largo_paquete_mm"],
                                        ENCARGO["velocidad_m_s"], ENCARGO["ancho_paquete_mm"])
    mot = next(c for c in checks if c["regla"] == "motorización")
    assert mot["estado"] == "ok", mot


def test_d8_mas_alla_del_tope_geometrico_error_que_lo_dice():
    from apolo.library.belt_conveyor_cotas import cotas

    with pytest.raises(ValueError) as e:
        cotas(29400, 600, 850, "TAMBOR-102", "TAMBOR-102-RET", "TUBO-4X2", "placa-ranurada",
              "NMRV-063", 4, True, True, 1000, 10, "-y", 0.254)
    assert "la placa ranurada llega a" in str(e.value) and "mm en esta faja" in str(e.value)


# ------------------------------------------------------------------ D11: el tramo suelto
def test_d11_patas_a_los_dos_lados_del_empalme(diez):
    from apolo.library.belt_conveyor_tramos import (
        EMPALME_T,
        PATA_A_EMPALME,
        pata_de_empalme,
        pata_de_empalme_cabeza,
    )

    d, cid, plan = diez
    xs = sorted({round(f.shape.bounding_box().center().X, 1) for k, f in d.scene.items()
                 if k.startswith(f"{cid}_leg")})
    empalmes = sorted({round(f.shape.bounding_box().center().X, 1) for k, f in d.scene.items()
                       if k.startswith(f"{cid}_empalme") and k.endswith("_cola")})
    assert len(empalmes) == 1
    s = empalmes[0] + EMPALME_T / 2.0
    assert round(pata_de_empalme(s), 1) in xs and round(pata_de_empalme_cabeza(s), 1) in xs
    assert pata_de_empalme_cabeza(s) - s == pytest.approx(EMPALME_T + PATA_A_EMPALME + 25.4)
    # la pata nueva va soldada al larguero del tramo de la CABEZA
    legs = {f["a"]: f["b"] for f in d.fasteners.values() if f["name"].startswith(f"{cid}_larg_pata")}
    nuevas = [k for k in legs if abs(d.scene[k].shape.bounding_box().center().X
                                     - pata_de_empalme_cabeza(s)) < 1.0]
    assert len(nuevas) == 2 and all(legs[k].endswith("_2") for k in nuevas)


def test_d11_cada_tramo_suelto_se_sostiene(diez, mesa36):
    for _d, _cid, plan in (diez, mesa36):
        calc = plan.calculos["tramos_sueltos"]
        assert calc["ok"] and len(calc["tramos"]) >= 2
        for t in calc["tramos"]:
            assert t["margen_x"] >= 0.10 and t["margen_y"] >= 0.10, t
    assert len(mesa36[2].calculos["tramos_sueltos"]["tramos"]) == 5


def test_d11_diez_metros_armada(diez):
    _armada(diez[0])


# ------------------------------------------------------------------ D12: el empalme de campo
def test_d12_el_empalme_de_campo_en_la_escena_y_la_bom(diez):
    from apolo.library.bom import bom_from_scene

    d, cid, _ = diez
    e = d.scene[f"{cid}_empalme_banda"]
    assert e.component == "EMPALME-GRAPA-ART" and e.cut_length == 600.0
    u = d.fasteners[f"{cid}_banda_empalme"]
    assert u["kind"] == "contacto" and u["b"] == f"{cid}_banda"
    fila = next(f for f in bom_from_scene(d.scene) if f.get("ref") == "EMPALME-GRAPA-ART")
    assert fila["cantidad"] == 1


def test_d12_la_puerta_reconoce_el_empalme_y_falla_sin_el(diez):
    import copy

    from apolo.services.calidad_reparabilidad import controles_reparabilidad

    d, cid, _ = diez
    (banda,) = [i for i in controles_reparabilidad(d)["items"]
                if i["id"] == "reparabilidad.banda_montable"]
    assert banda["estado"] == "OK" and "empalme de campo" in banda["detalle"]
    sin = copy.copy(d)
    g = f"{cid}_empalme_banda"
    sin.scene = {k: f for k, f in d.scene.items() if k != g}
    sin.fasteners = {k: f for k, f in d.fasteners.items() if g not in (f.get("a"), f.get("b"))}
    (banda,) = [i for i in controles_reparabilidad(sin)["items"]
                if i["id"] == "reparabilidad.banda_montable"]
    assert banda["estado"] == "FALLA" and "es sin fin y la atraviesan" in banda["detalle"]
    cruzan = banda["evidencia"]["bandas"][0]["atraviesan"]
    assert any("_sop" in i for i in cruzan) and any("_cama" in i for i in cruzan)


# ------------------------------------------------------------------ lo sellado con el 9
def _huella(doc) -> tuple:
    notas = sorted({f.get("nota") or "" for f in doc.fasteners.values()})
    return (len(doc.scene), len(doc.fasteners),
            round(sum(f.shape.volume for f in doc.scene.values()), 1),
            hashlib.sha1("|".join(notas).encode()).hexdigest()[:10],
            hashlib.sha1("|".join(sorted(f.name for f in doc.scene.values())).encode())
            .hexdigest()[:10])


@pytest.mark.parametrize("params, huella", [
    ({"criterio": 9}, (89, 116, 97162330.5, "ec82acaac6", "a80a92daad")),
    ({"criterio": 9, "tensor": "placa-ranurada", **NMRV},
     (87, 113, 85525297.1, "be858b076e", "67e5707b45")),
    ({"criterio": 9, "largo": 12000, "motor": "NMRV-063", "velocidad": 0.25,
      "tensor": "placa-ranurada"}, (221, 289, 212735331.9, "656e260b1b", "da6a3333f9")),
], ids=["9-4m", "9-4m-nmrv-placa", "9-12m-nmrv-placa"])
def test_lo_sellado_con_el_9_regenera_igual(params, huella):
    """Piezas, uniones, volumen, notas y nombres medidos con el código de antes de la F1b."""
    d, _ = _faja(**params)
    viejo = Document.from_apolo_bytes(d.to_apolo_bytes())
    h = _huella(viejo)
    assert h[:2] == huella[:2] and h[3:] == huella[3:]
    assert h[2] == pytest.approx(huella[2], rel=1e-7)


# ------------------------------------------------------------------ la puerta de la mesa de 36
@pytest.mark.torture
def test_la_puerta_de_la_mesa_de_36_sin_falla_nueva(mesa36):
    """La puerta entera (en proceso: gravedad y marcha reales) sobre la faja de 36 puestos con el
    encargo de la mesa y las funciones del testigo de la faja, sin sus justificaciones: lo que
    falle es lo mismo que en la de 4 m (`diseno.sin_sobrantes`). Tarda: tortura (medido en la
    Bitácora de faja-compacta, § F1b)."""
    import importlib.util
    from pathlib import Path

    ruta = Path(__file__).resolve().parents[1] / "scripts" / "testigos.py"
    spec = importlib.util.spec_from_file_location("testigos_script", ruta)
    tg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tg)
    d, _cid, _ = mesa36
    # como la mesa de sorteo: el variador a 65 Hz da 48,5 rpm de salida (declaradas). Con las
    # 42,75 de la placa a 60 Hz la regla de velocidad, que desde la F1b sí las lee, da 0,254 m/s
    # contra los 0,3 del encargo: es la máquina, no la plantilla
    d.execute("set_variable", {"name": "rpm_salida", "expression": "48.5"})
    d.set_requirements(dict(ENCARGO))
    d.funciones = [dict(f) for f in tg.FUNCIONES_FAJA]
    r = tg.correr_en_proceso(d)
    est = {i["id"]: i for i in r["items"]}
    fallas = sorted(k for k, i in est.items() if i["estado"] in ("FALLA", "SIN_EVALUAR"))
    assert set(fallas) <= {"diseno.sin_sobrantes"}, [(k, est[k].get("detalle")) for k in fallas]
