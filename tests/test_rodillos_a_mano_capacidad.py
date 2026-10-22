"""Capacidad y motor del transportador de rodillos HECHO A MANO (F6 de puerta-de-publicacion,
`library/rodillos_a_mano_medida.py` y `rodillos_a_mano_reglas.py`): la capacidad del rodillo sale
de SUS rodamientos (L10, ISO 281) y de SU eje (σ y desalineación del rodamiento) medidos en el
modelo, y el motor con el método de la plantilla. Modelos SINTÉTICOS (D16: el testigo de la
tienda es privado) con las medidas del de la tienda: tubo TUBOR-2 de 500, eje Ø12, 2 × 6201 en
tapas, ángulo L 75×6 y motorreductor.
"""

from __future__ import annotations

import math

import pytest

from apolo.doc import Document
from apolo.library.rodillos_a_mano_reglas import (
    THETA_MAX, THETA_OK, capacidad_a_medida, motor_a_mano, viga_apoyada,
)
from apolo.library.rules import detect_conveyor
from apolo.services.calidad_mecanica import items_funcion_mecanica, reglas_de_ingenieria

_EN_Y = {"x": 90, "y": 180, "z": 0}  # componente extruido en Z → a lo largo de +Y
PASO = 95.25
N = 6
H = 725.0
LARGO = 2 * 100 + (N - 1) * PASO


def _maquina(apoyo: str = "corto", tapa: str = "Tapa con rodamiento 6201",
             carga_kg: float = 100.0) -> Document:
    """`corto`: pletinas de 6 mm a 13.5 mm de cada rodamiento, eje de 530; `largo`: como la
    máquina de la tienda (ángulos 75×6 con el eje de 608 y su tuerca por fuera, piñón dentro: el
    rodamiento del lado del piñón queda a ~72 mm de su apoyo)."""
    d = Document("rodillos-a-mano-capacidad")
    if apoyo == "corto":
        for y, rot in ((-256.0, "-Y"), (256.0, "+Y")):
            d.execute("create_box", {"name": f"Pletina lateral ({rot})", "width": LARGO,
                                     "depth": 6, "height": 60,
                                     "position": {"x": LARGO / 2.0, "y": y, "z": H}})
        eje_y, eje_l, tuercas = 0.0, 530.0, (-264.0, 264.0)
    else:
        for y, rot in ((-297.5, "-Y"), (349.5, "+Y")):
            d.execute("insert_component", {"name": f"Larguero ({rot})", "component": "ANG-75X6",
                                           "length": LARGO, "rotation": {"y": 90},
                                           "position": {"x": LARGO / 2.0, "y": y, "z": 707.5}})
        eje_y, eje_l, tuercas = 26.0, 608.0, (-271.0, 323.0)
    for k in range(N):
        x = 100 + k * PASO
        d.execute("create_cylinder", {"name": f"Eje del rodillo ({k + 1})", "radius": 6,
                                      "height": eje_l, "axis": "y",
                                      "position": {"x": x, "y": eje_y, "z": H}})
        d.execute("insert_component", {"name": f"Tubo del rodillo ({k + 1})", "component": "TUBOR-2",
                                       "length": 500, "rotation": _EN_Y,
                                       "position": {"x": x, "y": 0, "z": H}})
        for s, lado in ((-242.5, "-Y"), (242.5, "+Y")):
            d.execute("create_cylinder", {"name": f"{tapa} ({lado}) ({k + 1})", "radius": 22.4,
                                          "height": 15, "axis": "y",
                                          "position": {"x": x, "y": s, "z": H}})
        for s, lado in zip(tuercas, ("-Y", "+Y")):
            d.execute("insert_component", {"name": f"Tuerca del eje ({lado}) ({k + 1})",
                                           "component": "TUERCA-M12", "rotation": _EN_Y,
                                           "position": {"x": x, "y": s, "z": H}})
        if apoyo != "corto":
            d.execute("insert_component", {"name": f"Piñón ({k + 1})",
                                           "component": "PINON-ASA40-DS-Z15", "rotation": _EN_Y,
                                           "position": {"x": x, "y": 285, "z": H}})
    d.execute("insert_component", {"name": "Motorreductor", "component": "MOTOR-037",
                                   "position": {"x": LARGO - 100, "y": 0, "z": 400}})
    d.set_requirements({"carga_kg": carga_kg, "largo_paquete_mm": 400, "ancho_paquete_mm": 400,
                        "velocidad_m_s": 0.27})
    return d


def _regla(doc, nombre):
    return next(r for r in reglas_de_ingenieria(doc) if r["regla"] == nombre)


@pytest.fixture(scope="module")
def corto():
    return _maquina()


@pytest.fixture(scope="module")
def largo():
    return _maquina("largo")


def test_mide_eje_apoyos_y_rodamientos(corto, largo):
    conv = detect_conveyor(corto.scene, corto.variables_resolved)
    (m,) = conv["rodillos_medidos"]  # los 6 rodillos iguales: una entrada
    assert m["n"] == N and "motivo" not in m
    assert m["eje"]["d"] == pytest.approx(12.0) and m["eje"]["material"] == "acero"
    assert m["apoyos"] == [pytest.approx(-256.0), pytest.approx(256.0)]
    assert [(r["ref"], r["s"]) for r in m["rodamientos"]] == [("6201", -242.5), ("6201", 242.5)]
    assert m["nombres"]["apoyos"] == ["Pletina lateral (-Y)", "Pletina lateral (+Y)"]
    # gira el tubo con sus tapas, no el eje ni las tuercas de afuera
    tubo_y_tapas = 3.541 * 0.5 + 2 * math.pi * 22.4 ** 2 * 15 * 7.85e-6
    assert m["masa_kg"] == pytest.approx(tubo_y_tapas, rel=0.02)
    assert conv["masa_rodillos_kg"] == pytest.approx(N * m["masa_kg"], abs=0.02)
    # el ángulo abarca también la tuerca de afuera: el apoyo es el ala (el tramo libre)
    (m,) = detect_conveyor(largo.scene, largo.variables_resolved)["rodillos_medidos"]
    assert m["apoyos"] == [pytest.approx(-263.0), pytest.approx(315.0)]
    assert m["nombres"]["apoyos"] == ["Larguero (-Y)", "Larguero (+Y)"]


def test_rodillo_corto_con_6201_cumple(corto):
    cap = _regla(corto, "capacidad de rodillo")
    assert cap["estado"] == "ok", cap["detalle"]
    assert cap["calc"]["fs"] > 1.0 and "6201" in cap["calc"]["entradas"]["rodamientos"]
    assert cap["calc"]["norma"].startswith("ISO 281")
    items = {i.id: i for i in items_funcion_mecanica(corto)}
    casos = items["vida.reglas"].evidencia.get("casos") or []
    assert not any(c["regla"] == "capacidad de rodillo" for c in casos)


@pytest.mark.parametrize("carga, estado", [(180.0, "aviso"), (300.0, "error")])
def test_carga_alta_desalinea_el_rodamiento(carga, estado):
    cap = _regla(_maquina(carga_kg=carga), "capacidad de rodillo")
    assert cap["estado"] == estado, cap["detalle"]
    assert cap["calc"]["fs"] < 1.0 and "desalineación" in cap["detalle"]


def test_vano_largo_con_voladizo_es_error(largo):
    """Como la máquina de la tienda: el rodamiento del lado del piñón a ~72 mm de su apoyo."""
    cap = _regla(largo, "capacidad de rodillo")
    assert cap["estado"] == "error", cap["detalle"]
    assert "Larguero (-Y) / Larguero (+Y)" in cap["calc"]["entradas"]["apoyos"]
    items = {i.id: i for i in items_funcion_mecanica(largo)}
    casos = items["vida.reglas"].evidencia["casos"]
    assert any(c["regla"] == "capacidad de rodillo" for c in casos)


def test_sin_rodamiento_reconocible_es_aviso_con_motivo():
    cap = _regla(_maquina(tapa="Tapa del rodillo"), "capacidad de rodillo")
    assert cap["estado"] == "aviso" and cap["calc"]["fs"] is None
    assert "ningún rodamiento reconocible" in cap["detalle"]


def test_sin_velocidad_o_sin_medida_no_inventa():
    medido = {"od": 50.8, "masa_kg": 2.0, "eje": {"d": 12, "material": "acero", "sy": 250,
                                                  "E": 200000}, "apoyos": [-256, 256],
              "rodamientos": [{"ref": "6201", "s": -242.5}, {"ref": "6201", "s": 242.5}], "n": 6}
    conv = {"rodillo": "TUBOR-2", "rodillos_medidos": [medido]}
    assert "sin rpm" in capacidad_a_medida(conv, 100, 4, 0.0)["detalle"]
    assert capacidad_a_medida(conv, 100, 4, 0.27)["estado"] == "ok"
    sin_eje = {**medido, "motivo": "ningún eje lo atraviesa: no hay eje que verificar"}
    cap = capacidad_a_medida({**conv, "rodillos_medidos": [medido, sin_eje]}, 100, 4, 0.27)
    assert cap["estado"] == "aviso" and "ningún eje" in cap["detalle"]


def test_motor_con_el_metodo_de_la_plantilla():
    conv = {"n_rodillos": 20, "paso": 95.25, "largo": 1809.75, "masa_rodillos_kg": 63.0,
            "motor_kW": 0.37, "motor": "MOTOR-037"}
    alto = motor_a_mano(conv, 100, 400, 0.27)  # 4 paquetes de 100 kg + 63 kg de rodillos
    assert alto["regla"] == "motor" and alto["estado"] == "ok"
    assert alto["calc"]["fs"] == pytest.approx(2.75, abs=0.05)
    bajo = motor_a_mano({**conv, "motor_kW": 0.12}, 100, 400, 0.27)
    assert bajo["estado"] == "error" and bajo["calc"]["fs"] < 1.0
    justo = motor_a_mano({**conv, "motor_kW": 0.15}, 100, 400, 0.27)
    assert justo["estado"] == "aviso"
    assert motor_a_mano({**conv, "motor_kW": None}, 100, 400, 0.27)["estado"] == "aviso"


def test_viga_contra_las_formulas_cerradas():
    e, d, l_ = 200000.0, 12.0, 600.0
    ei = e * math.pi * d ** 4 / 64.0
    # carga central: flecha PL³/48EI y pendiente nula bajo la carga
    v = viga_apoyada((0.0, l_), [(300.0, 100.0)], d, e)
    assert v["flecha"] == pytest.approx(100.0 * l_ ** 3 / (48 * ei), rel=1e-3)
    assert v["m_max"] == pytest.approx(100.0 * l_ / 4.0)
    assert abs(v["pendientes"][0]) < 1e-6
    # flexión a cuatro puntos: θ en la carga = F·a·(L/2 − a)/EI
    a = 20.0
    v = viga_apoyada((0.0, l_), [(a, 100.0), (l_ - a, 100.0)], d, e)
    assert abs(v["pendientes"][0]) == pytest.approx(100.0 * a * (l_ / 2 - a) / ei, rel=1e-3)
    assert THETA_OK < THETA_MAX
