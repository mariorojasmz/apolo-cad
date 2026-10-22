"""Transportador de rodillos HECHO A MANO (sin `create_roller_conveyor`): rodillos de tubo
redondo de catálogo (`tubos_circulares`, como el TUBOR) con su eje, bastidor de ÁNGULO L, cadenas
rodillo a rodillo y motorreductor. `detect_conveyor` sólo conocía rodillos de la categoría
«rodillos» sobre perfiles de la categoría «perfiles»: ninguna regla calculaba la carga del motor y
la puerta dejaba `vida.factor_servicio` SIN_EVALUAR (F6 de puerta-de-publicacion,
`library/rodillos_a_mano.py`). Modelo SINTÉTICO (D16: el testigo de la tienda es privado).
"""

from __future__ import annotations

import pytest

from apolo.doc import Document
from apolo.library import rodillos_a_mano
from apolo.library.rules import detect_conveyor
from apolo.services.calidad_mecanica import items_funcion_mecanica, reglas_de_ingenieria

_EN_Y = {"x": 90, "y": 180, "z": 0}  # componente extruido en Z → a lo largo de +Y
PASO = 95.25
N = 6
H = 725.0
REQUISITOS = {"carga_kg": 30, "largo_paquete_mm": 300, "ancho_paquete_mm": 400,
              "velocidad_m_s": 0.3}


def _transportador(motor: bool = True, tubo: str = "Tubo del rodillo", eje: bool = True,
                   cadenas: bool = True) -> Document:
    d = Document("rodillos-a-mano")
    largo = 2 * 100 + (N - 1) * PASO
    for y, rot in ((-285.0, "-Y"), (285.0, "+Y")):
        d.execute("insert_component", {"name": f"Larguero ({rot})", "component": "ANG-75X6",
                                       "length": largo, "rotation": {"y": 90},
                                       "position": {"x": largo / 2.0, "y": y, "z": H - 20}})
    pinones = []
    for k in range(N):
        x = 100 + k * PASO
        if eje:
            d.execute("create_cylinder", {"name": f"Eje del rodillo ({k + 1})", "radius": 6,
                                          "height": 600, "axis": "y",
                                          "position": {"x": x, "y": 20, "z": H}})
        d.execute("insert_component", {"name": f"{tubo} ({k + 1})", "component": "TUBOR-2",
                                       "length": 500, "rotation": _EN_Y,
                                       "position": {"x": x, "y": 0, "z": H}})
        if cadenas:
            pinones.append(d.execute("insert_component", {
                "name": f"Piñón doble-simple ({k + 1})", "component": "PINON-ASA40-DS-Z15",
                "rotation": _EN_Y, "position": {"x": x, "y": 270, "z": H}}))
    for k in range(len(pinones) - 1):
        h = 1 if k % 2 == 0 else 2
        d.execute("create_chain", {"name": f"Cadena rodillo a rodillo ({k + 1})",
                                   "pinon_a": pinones[k + 1], "pinon_b": pinones[k],
                                   "hilera_a": h, "hilera_b": h, "fase": "auto"})
    if motor:
        d.execute("insert_component", {"name": "Motorreductor", "component": "MOTOR-037",
                                       "position": {"x": largo - 100, "y": 0, "z": 450}})
    d.set_requirements(dict(REQUISITOS))
    return d


def _item(doc, iid):
    return next(i for i in items_funcion_mecanica(doc) if i.id == iid)


@pytest.fixture(scope="module")
def con_motor():
    return _transportador()


def test_detecta_el_transportador_de_tubos_sobre_angulo(con_motor):
    conv = detect_conveyor(con_motor.scene, con_motor.variables_resolved)
    assert conv is not None and conv["tipo"] == "rodillos"
    assert conv["n_rodillos"] == N and conv["rodillo"] == "TUBOR-2"
    assert conv["paso"] == pytest.approx(PASO, abs=0.1)
    assert conv["largo"] == pytest.approx((N - 1) * PASO, abs=0.2)
    assert conv["ancho"] == pytest.approx(500.0, abs=0.5) == conv["ancho_util_mm"]
    assert conv["motor"] == "MOTOR-037" and conv["tambor_d"] is None
    assert conv["altura"] == pytest.approx(H + 25.4, abs=0.5)


def test_el_factor_de_servicio_se_calcula_con_los_requisitos(con_motor):
    reglas = {r["regla"]: r for r in reglas_de_ingenieria(con_motor)}
    # el motor con el método de la plantilla (`rodillos_a_mano_reglas.motor_a_mano`)
    assert "motorización" not in reglas
    mot = reglas["motor"]
    assert mot["estado"] == "ok" and mot["calc"]["fs"] > 1.0
    # sin rodamiento reconocible la capacidad no se inventa: aviso con el motivo
    cap = reglas["capacidad de rodillo"]
    assert cap["estado"] == "aviso" and cap["calc"]["fs"] is None
    assert "a medida" in cap["detalle"] and "ningún rodamiento reconocible" in cap["detalle"]
    assert reglas["ancho útil"]["estado"] == "ok"  # 500 mm de tubo para 400 de paquete
    item = _item(con_motor, "vida.factor_servicio")
    assert item.estado == "OK"
    assert item.evidencia["valores"][0]["factor_servicio"] == pytest.approx(
        mot["calc"]["fs"] * 1.5, abs=0.02)  # el arranque ×1.5 de la plantilla


def test_antes_quedaba_sin_evaluar(con_motor, monkeypatch):
    """Sin el detector (lo de antes) el motor queda sin carga calculada: SIN_EVALUAR."""
    monkeypatch.setattr(rodillos_a_mano, "detectar_rodillos_a_mano", lambda scene: None)
    assert detect_conveyor(con_motor.scene, con_motor.variables_resolved) is None
    assert _item(con_motor, "vida.factor_servicio").estado == "SIN_EVALUAR"


def test_sin_motor_sigue_igual():
    d = _transportador(motor=False)
    assert detect_conveyor(d.scene, d.variables_resolved) is None
    assert _item(d, "vida.factor_servicio").estado == "NO_APLICA"


def test_el_rodillo_se_reconoce_por_su_eje_no_por_el_nombre():
    d = _transportador(tubo="Tubo 2in", cadenas=False)
    conv = detect_conveyor(d.scene, d.variables_resolved)
    assert conv is not None and conv["n_rodillos"] == N
    # tubos redondos paralelos SIN eje ni rol de rodillo (una baranda, un enrejado) no son lecho
    d = _transportador(tubo="Tubo 2in", eje=False, cadenas=False)
    assert detect_conveyor(d.scene, d.variables_resolved) is None
