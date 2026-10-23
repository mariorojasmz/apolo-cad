"""La marcha del video sin cajas encimadas (plan puerta-de-publicacion, F6). Un revisor de cuadros
rechazó el video de una faja con placa de transferencia en la descarga: las cajas se paraban en
la placa, frenaban toda la fila y la alimentación nacía DENTRO de la caja detenida en la cola
(que además nacía apoyada en el techo de la guarda de cola de la v5, quieta). Dos arreglos
generales: los SUMIDEROS de la dinámica (la caja que pasa el fin de la banda sale del mundo, como
la que se lleva la máquina siguiente) y la cola que arranca donde la banda está libre."""

from __future__ import annotations

import numpy as np
import pytest

from apolo.doc.document import Document
from apolo.physics.dinamica_peticion import parse_peticion
from apolo.physics.sim import PhysicsError
from apolo.services import marcha_ejemplo as me


@pytest.fixture(scope="module")
def faja():
    doc = Document("faja-placa")
    doc.execute("create_belt_conveyor", {"largo": 2000, "ancho_banda": 500, "altura": 800})
    return doc


def _banda(doc):
    return next(f for f in doc.scene.values() if f.id.endswith("_banda")).shape.bounding_box()


def test_la_peticion_valida_los_sumideros():
    pet = parse_peticion({"sumideros": [{"punto_mm": [1000, 0, 0], "normal": [2, 0, 0]}]})
    assert pet.sumideros[0].normal == (1.0, 0.0, 0.0)
    with pytest.raises(PhysicsError, match="sumideros\\[0\\]: clave desconocida 'punto'"):
        parse_peticion({"sumideros": [{"punto": [0, 0, 0], "normal": [1, 0, 0]}]})
    with pytest.raises(PhysicsError, match="pide 'punto_mm'"):
        parse_peticion({"sumideros": [{"normal": [1, 0, 0]}]})


def test_la_marcha_lleva_sumideros_y_la_cola_nace_libre(faja):
    m = me.armar(faja, extra_s=2.0)
    esc = m.escenario
    bb = _banda(faja)
    assert len(esc["sumideros"]) == 2
    fin, abajo = esc["sumideros"]
    # el fin del tramo plano superior: sobre el eje del tambor motriz (la banda baja por él)
    assert fin["normal"] == pytest.approx([1.0, 0.0, 0.0])
    assert bb.max.X - 100 < fin["punto_mm"][0] <= bb.max.X
    assert abajo["normal"][2] == pytest.approx(-1.0) and abajo["punto_mm"][2] < bb.max.Z - 200
    # la v5 tapa la banda junto al tambor de cola: la cola nace donde la banda ya está libre
    cola = next(p for p in esc["productos"] if p["nombre"].startswith("cola_"))
    banda = next(f for f in faja.scene if f.endswith("_banda"))
    pos, dims = cola["posicion_mm"], cola["dims_mm"]
    assert not me._choca(faja, banda, pos, dims, 0.0)
    antes = [pos[0] - me.PASO_BUSQUEDA_MM, *pos[1:]]
    assert me._choca(faja, banda, antes, dims, 0.0)  # 20 mm antes tocaba el techo de la guarda


def test_con_placa_de_transferencia_las_cajas_no_se_enciman(faja):
    pytest.importorskip("mujoco")
    from apolo.physics.dinamica import prepare_dynamics, simulate_dynamics
    from apolo.physics.dinamica_serie import serie_reproduccion

    doc = Document.from_apolo_bytes(faja.to_apolo_bytes())
    bb = _banda(doc)
    placa = doc.execute("create_box", {"name": "Placa de transferencia", "width": 500,
                                       "depth": 560, "height": 6,
                                       "position": {"x": bb.max.X + 260, "z": bb.max.Z - 3}})
    doc.execute("ground", {"name": "gp", "feature": placa})
    esc = me.armar(doc, extra_s=6.0).escenario
    snap = prepare_dynamics(doc.scene, doc.joints, doc.fasteners, doc.grounds, esc, mates=doc.mates)
    res = simulate_dynamics(snap)
    dims = {p["name"]: (p["w"], p["d"], p["h"]) for p in res["productos"]}
    peor = 0.0
    for fr in res["frames"]:
        cs = [(n, np.asarray(M)[:3, 3]) for n, M in fr["poses"].items() if n in dims]
        for i, (a, pa) in enumerate(cs):
            for _b, pb in cs[i + 1:]:
                sep = np.abs(pa - pb)
                peor = max(peor, min(dims[a][k] - sep[k] for k in range(3)))
    assert peor <= 3.0, f"cajas encimadas {peor:.1f} mm"
    retiradas = res["resumen"]["productos_retirados"]
    assert len(retiradas) >= 3  # la descarga se vacía: ninguna se queda en la placa
    r = res["resumen"]["productos"][retiradas[0]]
    assert r["retirado_s"] > 0 and r["posicion_final_mm"][0] >= bb.max.X - 100
    # el visor deja de dibujar la retirada: sus poses se acaban antes que la serie
    serie = serie_reproduccion(res, snap.bandas, hz=30)
    p = next(x for x in serie["productos"] if x["name"] == retiradas[0])
    assert p["desde"] + len(p["poses"]) // 7 < len(serie["t"])
    # concluir_prueba cuenta el avance de las retiradas
    assert me.concluir_prueba(me.preparar_prueba(doc, esc)[1], res)["avance_mm"] > 1000


def test_sin_sumideros_la_dinamica_no_cambia(faja):
    pytest.importorskip("mujoco")
    from apolo.physics.dinamica import prepare_dynamics, simulate_dynamics

    esc = me.armar(faja, extra_s=0.0).escenario
    corta = {**esc, "duracion_s": 1.0}
    sin = {k: v for k, v in corta.items() if k != "sumideros"}
    a = simulate_dynamics(prepare_dynamics(faja.scene, faja.joints, faja.fasteners, faja.grounds,
                                           sin, mates=faja.mates))
    assert "productos_retirados" not in a["resumen"]
