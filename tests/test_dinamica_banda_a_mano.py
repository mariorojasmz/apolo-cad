"""Banda HECHA A MANO sobre tambores de distinto Ø (defecto hallado en la F4 de la fábrica de
publicaciones: faja real de 2 m, motriz engomado Ø113,6 y cola Ø101,6).

Sin el ancla `eje_cola` de `create_belt_conveyor`, la dirección de la banda salía del eje largo
del casco, inclinada respecto del tramo superior (la tangente común a los dos tambores), y la
dinámica respondía «no tiene un tramo superior plano»: el tambor giraba y la caja quedaba
quieta. La dirección sale ahora de la arista recta superior del contorno del lazo."""

import dataclasses
import math
from types import SimpleNamespace

import numpy as np
import pytest

from apolo.library.belt_conveyor import _belt_loop
from apolo.physics.banda import superficie_banda
from apolo.physics.sim import PhysicsError

Z_TOPE = 800.0
R_MOTRIZ, R_COLA = 113.6 / 2, 101.6 / 2


def _lazo(r_m=R_MOTRIZ, r_c=R_COLA, t=4.0, ancho=600.0, mitad=1000.0):
    """Lazo como lo arma una persona: ramal superior plano a Z_TOPE, ejes a ±mitad."""
    zm, zc = Z_TOPE - r_m - t, Z_TOPE - r_c - t
    return _belt_loop(mitad, zm, r_m, -mitad, zc, r_c, t, ancho), (mitad, 0.0, zm)


def _banda(shape, origen, eje=(0.0, -1.0, 0.0)):
    feat = SimpleNamespace(id="c41", shape=shape, material=None)
    junta = {"name": "j_tambor", "axis": list(eje), "origin": list(origen)}
    return superficie_banda(feat, junta, None, [1, 0, 0], 0.6, 0.33, "banda_0")


@pytest.mark.parametrize("t", [4.0, 8.0])
def test_tambores_de_distinto_diametro_dan_el_tramo_superior(t):
    shape, origen = _lazo(t=t)
    b = _banda(shape, origen)
    assert abs(b.d[0]) == pytest.approx(1.0, abs=1e-9)             # el ramal, no la recta de ejes
    assert b.centro[2] == pytest.approx((Z_TOPE - 2.0) / 1000, abs=1e-9)
    assert b.medio[1] == pytest.approx(0.3)
    # entre los puntos de tangencia: los dos tambores, casi de punta a punta
    assert b.medio[0] == pytest.approx(1.0, abs=1e-3)
    assert b.radio == pytest.approx((R_MOTRIZ + t) / 1000, abs=1e-9)  # r del eje a la cara de arriba
    assert b.e == pytest.approx((-1.0, 0.0, 0.0), abs=1e-9)         # eje −Y, giro +: hacia −X (D7)
    assert b.signo == -1.0                                           # +X pide giro negativo


def test_faja_inclinada_sigue_su_tramo_superior():
    """Un tramo levemente inclinado (faja de subida) vale: la superficie sigue la pendiente."""
    from build123d import Axis

    ang = 8.0
    shape, (x, y, z) = _lazo()
    shape = shape.rotate(Axis((0, 0, Z_TOPE), (0, 1, 0)), -ang)  # la cabeza (+X) sube
    c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    origen = (x * c - (z - Z_TOPE) * s, y, x * s + (z - Z_TOPE) * c + Z_TOPE)
    b = _banda(shape, origen)
    d = np.asarray(b.d) * np.sign(b.d[0])
    assert math.degrees(math.atan2(d[2], d[0])) == pytest.approx(ang, abs=1e-6)
    assert b.medio[0] == pytest.approx(1.0, abs=2e-3)


def test_una_pieza_sin_tramo_recto_sigue_rechazada():
    """No se acepta cualquier cosa: un tambor suelto no tiene tramo superior plano."""
    from build123d import Cylinder

    from apolo.kernel.shapes import place

    tambor = place(Cylinder(R_MOTRIZ, 600), (0, 0, 700), (90, 0, 0))
    with pytest.raises(PhysicsError, match="tramo superior plano"):
        _banda(tambor, (0, 0, 700))


def test_la_caja_avanza_sobre_la_banda_a_mano():
    """E2E: la faja de banda con su lazo convertido en pieza A MANO (otro id, otro nombre, sin
    el ancla `eje_cola` al alcance) y el tambor motriz en una junta declarada: la caja llega a
    la velocidad de la banda. Antes: «no tiene un tramo superior plano»."""
    pytest.importorskip("mujoco")
    from apolo.doc.document import Document
    from apolo.physics.dinamica import prepare_dynamics, simulate_dynamics

    doc = Document("faja-banda-a-mano")
    doc.execute("create_belt_conveyor", {"largo": 2000, "ancho_banda": 500, "altura": 800})
    o = doc.scene["c1_tambor_motriz"].anchors["eje_motriz"]["origin"]
    doc.execute("add_joint", {"name": "j_tambor", "type": "continua", "parent": "c1_rail1",
                              "child": "c1_tambor_motriz", "origin": dict(zip("xyz", o)),
                              "axis": {"x": 0, "y": 1, "z": 0}})
    escena = dict(doc.scene)
    banda = escena.pop("c1_banda")
    escena["c41"] = dataclasses.replace(banda, id="c41", name="Banda PVC 2 capas", command_id="c41")
    v = 0.25
    req = {"con_autodeteccion": True, "auto_bandas": False, "duracion_s": 0.8, "fps": 20,
           "bandas": [{"pieza": "c41", "junta_motriz": "j_tambor", "direccion_transporte": [1, 0, 0]}],
           "motores": [{"junta": "j_tambor", "modo": "velocidad", "v_superficie_m_s": v}],
           "productos": [{"nombre": "caja", "dims_mm": [150, 120, 100], "masa_kg": 2.0,
                          "posicion_mm": [-300, 0, 800 + 50 + 0.5]}]}
    snap = prepare_dynamics(escena, doc.joints, doc.fasteners, doc.grounds, req, mates=doc.mates)
    assert [b.pieza for b in snap.bandas] == ["c41"]
    res = simulate_dynamics(snap)
    caja = res["resumen"]["productos"]["p_caja"]
    assert caja["velocidad_final_mm_s"][0] == pytest.approx(v * 1000, rel=0.02)
