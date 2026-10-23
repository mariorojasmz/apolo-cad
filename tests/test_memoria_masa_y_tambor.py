"""Memoria de cálculo (plan puerta-de-publicacion, F6): (a) la masa que imprime es la de
`GET /api/mass-properties` (la memoria de una faja decía 252,4 kg y mass-properties 260,6: sin el
material del vertical, un «Larguero» de acero pesaba como madera); (b) la velocidad de banda sale
del Ø REAL del tambor motriz (Ø113,6 del engomado → 20,1 m/min), no del menor lado de la caja de
la «Guarda del tambor» (Ø120 → 21,2 m/min)."""

from __future__ import annotations

import pytest

from apolo.doc import Document
from apolo.drawing.calc_report import peso_memoria
from apolo.library.diametro_tambor import diametro_tambor
from apolo.library.engineering.mass import scene_mass_properties
from apolo.library.rules import band_speed_m_s, detect_conveyor
from apolo.services.engineering_rules import structure_rules


def _caja(d, nombre, w, dp, h, x=0.0, y=0.0, z=0.0):
    return d.execute("create_box", {"name": nombre, "width": w, "depth": dp, "height": h,
                                    "position": {"x": x, "y": y, "z": z}})


def _cilindro_y(d, nombre, diametro, largo, x=0.0, z=0.0):
    """Un cilindro con su eje en Y (como un tambor de faja)."""
    return d.execute("create_cylinder", {"name": nombre, "radius": diametro / 2.0,
                                         "height": largo, "rotation": {"x": 90},
                                         "position": {"x": x, "z": z}})


def test_la_memoria_pesa_lo_que_dice_mass_properties():
    d = Document("larguero")
    a = _caja(d, "Larguero (+Y)", 4000, 50, 100, z=700)
    p = _caja(d, "Pata", 50, 50, 650, z=325)
    d.execute("ground", {"name": "g", "feature": p})
    d.execute("fasten", {"name": "f", "a": a, "b": p, "kind": "soldadura", "throat_mm": 3,
                         "length_mm": 100})
    mp = scene_mass_properties(d.scene, default_material=d.default_material())["total"]
    assert peso_memoria(d.scene, d.default_material()) == pytest.approx(mp["masa_kg"])
    assert peso_memoria(d.scene) < 0.2 * mp["masa_kg"]  # sin el vertical: madera por el nombre
    (vuelco,) = [r for r in structure_rules(d, 0.0, None) if "vuelco" in str(r.get("regla"))]
    assert f"{mp['masa_kg']:g} kg" in vuelco["calc"]["entradas"]["masa total"]


def _tambor_de_cabeza(d):
    _cilindro_y(d, "Tubo del tambor de cabeza", 101.6, 550, x=2000, z=700)
    _cilindro_y(d, "Engomado del tambor motriz", 113.6, 540, x=2000, z=700)
    _cilindro_y(d, "Tambor de cabeza · Eje fijo Ø25 g6", 25, 618, x=2000, z=700)
    _cilindro_y(d, "Tapa porta-rodamiento del tambor de cabeza (+Y)", 93.6, 20, x=2000, z=700)
    _caja(d, "Guarda del tambor de cabeza", 325, 671.5, 120, x=2000, z=760)
    _cilindro_y(d, "Tambor de cola", 101.6, 550, x=0, z=700)


def test_el_diametro_es_el_del_engomado_motriz():
    d = Document("tambor")
    _tambor_de_cabeza(d)
    tambores = [f for f in d.scene.values() if "tambor" in f.name.lower()]
    assert diametro_tambor(tambores) == pytest.approx(113.6, abs=0.1)
    v = band_speed_m_s(56.333, diametro_tambor(tambores)) * 60
    assert v == pytest.approx(20.1, abs=0.05)  # no los 21,2 m/min del Ø120 de la guarda
    # sin nada «motriz», el mayor redondo y largo (ni la guarda, ni la tapa, ni el eje)
    sin_motriz = [f for f in tambores if "motriz" not in f.name]
    assert diametro_tambor(sin_motriz) == pytest.approx(101.6, abs=0.1)


def test_la_faja_a_mano_detecta_el_diametro_real():
    d = Document("faja-a-mano")
    _tambor_de_cabeza(d)
    _caja(d, "Banda", 2000, 500, 2, x=1000, z=757)
    _caja(d, "Larguero (+Y)", 2200, 50, 100, x=1000, y=300, z=650)
    c = detect_conveyor(d.scene, d.variables_resolved, d.fasteners)
    assert c is not None and c["tipo"] == "banda"
    assert c["tambor_d"] == pytest.approx(113.6, abs=0.1)
