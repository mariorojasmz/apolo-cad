"""Super-comando create_take_up: tensor de cola tipo trotadora (eje fijo).

Piezas SEPARADAS y mapeadas: rodillo + eje + 2 rodamientos + 2 seeger + (por lado)
soporte en C + perno comercial de catálogo + tuerca soldada de catálogo.
"""

import pytest

from apolo.doc import Document


def _doc(**params):
    d = Document("take-up-test")
    d.execute("create_take_up", params)
    return d


def test_take_up_generates_separated_mapped_parts():
    d = _doc()
    feats = list(d.scene.values())
    names = [f.name for f in feats]
    comps = [f.component for f in feats if f.component]
    assert len(feats) == 10   # rodillo + eje + 2 rod + 2 seeger + 2 soporte + 2 perno (sin tuerca)
    # piezas comerciales MAPEADAS (cuentan en BOM, dicen qué comprar)
    assert comps.count("6207") == 2          # rodamientos (default; bore 35 = eje 3.5cm)
    assert comps.count("PERNO-M16") == 2     # perno tensor
    # SIN tuerca soldada: el perno rosca directo en el eje
    assert not any("Tuerca" in n for n in names)
    assert not any(c and c.startswith("TUERCA") for c in comps)
    # a medida
    assert any("Rodillo" in n for n in names)
    assert any("Eje fijo" in n for n in names)
    assert sum("Seeger" in n for n in names) == 2
    assert sum("Soporte en C" in n for n in names) == 2


def test_perno_choice_maps_bolt():
    d = _doc(perno="PERNO-M20")
    comps = [f.component for f in d.scene.values() if f.component]
    assert comps.count("PERNO-M20") == 2


def test_default_shaft_is_35mm():
    # default rodamiento 6207 → eje Ø35 (3.5 cm)
    eje = next(f for f in _doc().scene.values() if "Eje fijo" in f.name)
    bb = eje.shape.bounding_box()
    assert abs((bb.max.X - bb.min.X) - 35.0) < 1.0


def test_bearing_choice_sets_shaft_diameter():
    for ref, bore in [("6206", 30.0), ("6210", 50.0)]:
        d = _doc(rodamiento=ref)
        eje = next(f for f in d.scene.values() if "Eje fijo" in f.name)
        bb = eje.shape.bounding_box()
        assert abs((bb.max.X - bb.min.X) - bore) < 1.0


def test_lagging_toggles_roller_diameter():
    con = _doc(engomado=True)
    sin = _doc(engomado=False)
    r_con = next(f for f in con.scene.values() if "Rodillo" in f.name).shape.bounding_box()
    r_sin = next(f for f in sin.scene.values() if "Rodillo" in f.name).shape.bounding_box()
    assert (r_con.max.Z - r_con.min.Z) > (r_sin.max.Z - r_sin.min.Z)


def test_support_thickness_param():
    grueso = _doc(espesor_soporte=12.7)
    sop = next(f for f in grueso.scene.values() if "Soporte en C" in f.name)
    assert "12.7mm" in sop.name


def test_take_up_rejects_roller_too_small_for_bearing():
    with pytest.raises(Exception):
        _doc(diam_rodillo=50)


def test_take_up_rejects_unknown_bearing():
    with pytest.raises(Exception):
        _doc(rodamiento="NO-EXISTE")


def test_take_up_rejects_unknown_perno():
    with pytest.raises(Exception):
        _doc(perno="NO-EXISTE")


# --- rodillo motriz (create_drive_roller): take-up un lado + eje largo al motor ---

def _drive(**params):
    d = Document("drive-test")
    d.execute("create_drive_roller", params)
    return d


def test_drive_roller_parts_and_single_takeup():
    d = _drive()
    feats = list(d.scene.values())
    names = [f.name for f in feats]
    comps = [f.component for f in feats if f.component]
    assert len(feats) == 8                       # rodillo+eje+2 rod+2 seeger+1 soporte+1 perno
    assert comps.count("6207") == 2
    assert comps.count("PERNO-M16") == 1         # take-up SOLO en un lado
    assert sum("Soporte en C" in n for n in names) == 1
    assert sum("Perno tensor" in n for n in names) == 1


def test_drive_roller_shaft_is_asymmetric_long_to_motor():
    d = _drive(voladizo=60, largo_eje_motor=250)
    eje = next(f for f in d.scene.values() if "Eje motriz" in f.name)
    bb = eje.shape.bounding_box()
    # un extremo corto (take-up, voladizo) y el otro largo (al motor): muy asimétrico
    assert abs((bb.max.X - bb.min.X) - 35.0) < 1.0          # Ø35 (6207)
    assert (bb.max.Y - bb.min.Y) > 900.0                    # cara 700 + 60 + 250
    assert abs(bb.max.Y) > abs(bb.min.Y) + 100.0            # +Y (motor) mucho más largo


def test_drive_roller_rejects_short_motor_shaft():
    with pytest.raises(Exception):
        _drive(largo_eje_motor=10)


# --- tensor LONGITUDINAL: perno horizontal (a lo largo de la banda), no vertical ---

def test_perno_is_longitudinal_x():
    perno = next(f for f in _doc().scene.values() if "Perno tensor" in f.name)
    bb = perno.shape.bounding_box()
    ex, ez = bb.max.X - bb.min.X, bb.max.Z - bb.min.Z
    assert ex > 2.0 * ez   # el perno va A LO LARGO de X (banda), no vertical (Z)


def test_dir_tensor_points_to_frame_end():
    # cola (dir_tensor por defecto -1): cabeza hacia -X
    tail = next(f for f in _doc().scene.values() if "Perno tensor" in f.name)
    tb = tail.shape.bounding_box()
    assert (tb.min.X + tb.max.X) / 2.0 < 0.0
    # cabeza (drive por defecto +1): cabeza hacia +X
    drv = next(f for f in _drive().scene.values() if "Perno tensor" in f.name)
    db = drv.shape.bounding_box()
    assert (db.min.X + db.max.X) / 2.0 > 0.0


def test_perno_tensor_is_allen_socket_cap():
    # el perno tensor es Allen (cabeza cilíndrica con hexágono interior): tiene hueco removido
    import math
    from apolo.library.builders import socket_cap
    bolt = socket_cap(16)(90)
    solido = math.pi * 8.0 ** 2 * 90.0 + math.pi * 12.0 ** 2 * 16.0  # vástago Ø16 + cabeza Ø24 llena
    assert bolt.volume < solido * 0.98   # hay hueco hexagonal Allen


def test_shaft_has_transverse_hole_for_perno():
    # el eje tiene agujero (hilo) por donde pasa el perno → su volumen baja vs un cilindro lleno
    import math
    d = _doc()
    eje = next(f for f in d.scene.values() if "Eje fijo" in f.name)
    bb = eje.shape.bounding_box()
    largo = bb.max.Y - bb.min.Y
    solido = math.pi * (35.0 / 2.0) ** 2 * largo
    assert eje.shape.volume < solido * 0.99   # hay material removido (agujeros transversales)
