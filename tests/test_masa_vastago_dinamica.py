"""El vástago se mueve con la masa MÓVIL de su ficha (plan pedidos-de-extensiones-iii F4, D11).

Antes la dinámica pesaba el vástago de `create_pneumatic_cylinder` por volumen × densidad (2,34 kg
en el Ø63 × 800) y la co-simulación le sumaba la masa móvil en carrera 0 como armadura (0,43):
2,77 kg contra los 2,43 de la ficha. Ahora la pieza pesa la masa móvil (`partes_de_cilindros`, la
misma de `scene_mass_properties`) y la armadura no se suma; un vástago sin ficha que lo cubra sigue
con la armadura.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("mujoco")

from apolo.doc.document import Document  # noqa: E402
from apolo.library.peso_ficha import partes_de_cilindros  # noqa: E402
from apolo.physics.dinamica import prepare_dynamics  # noqa: E402
from apolo.physics.dinamica_cuerpos import masa_pieza  # noqa: E402
from apolo.services import cosim_aire  # noqa: E402
from apolo.services.cosim_snapshot import snapshot_cosim  # noqa: E402
from neumatica_escena import empujador, escenario  # noqa: E402


def test_el_vastago_del_o63_x_800_pesa_la_masa_movil_de_la_ficha():
    d = Document("o63")
    cid = d.execute("create_pneumatic_cylinder", {"ref": "CIL-ISO15552-63", "carrera": 800, "montaje": "pies",
                                                   "eje": "+X", "puertos": "+Z"})
    d.execute("ground", {"name": "piso", "feature": f"{cid}_cuerpo"})
    (c,) = prepare_dynamics(d.scene, d.joints, d.fasteners, d.grounds, {"duracion_s": 0.1}, mates=d.mates).cuerpos
    assert c["piezas"] == [f"{cid}_vastago"]
    assert c["masa_kg"] == pytest.approx(0.430 + 0.0025 * 800) == partes_de_cilindros(d.scene)[f"{cid}_vastago"]
    assert c["masa_kg"] < masa_pieza(d.scene[f"{cid}_vastago"]) + 0.430  # antes: volumen + armadura


def test_en_la_cosimulacion_el_vastago_no_suma_la_armadura():
    d, cid = empujador()
    snap = snapshot_cosim(d, escenario(cid))
    (c,) = [x for x in snap.dinamica.cuerpos if x["junta"] == f"{cid}_vastago"]
    movil = 0.110 + 0.0009 * 200  # la ficha del Ø32 con carrera 200
    assert c["armadura_kgm2"] == 0.0 and c["inercia_eje_kgm2"] == pytest.approx(c["masa_kg"], abs=1e-4)
    assert c["masa_kg"] == pytest.approx(movil + masa_pieza(d.scene[f"{cid}_empujador"]), abs=1e-4)


def test_un_vastago_sin_ficha_sigue_con_la_armadura():
    doc = SimpleNamespace(scene={}, joints={"j": {"child": "vastago_a_mano", "axis": [1.0, 0.0, 0.0]}})
    esc = SimpleNamespace(cilindros={"-MM1": {"junta": "j"}}, mecanica={})
    tab = SimpleNamespace(modelos={"-MM1": SimpleNamespace(friccion_junta_N=5.0, masa_base=0.43)})
    _, juntas = cosim_aire.peticion(doc, None, esc, tab)
    assert juntas["j"] == {"friccion": 5.0, "armadura": 0.43}
