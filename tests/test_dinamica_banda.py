"""V8.2 F1 — la faja se mueve: banda, sentido de marcha, fotocelda y rodillos.

Faja piloto = `create_belt_conveyor` 3000×500×800 (la de V8.0), con la estructura sujeta por
autodetección y el tambor motriz girando sobre su ancla `eje_motriz` (junta virtual) o sobre
una junta declarada. Requiere MuJoCo."""

import numpy as np
import pytest

pytest.importorskip("mujoco")

from apolo.doc.document import Document  # noqa: E402
from apolo.physics.dinamica import prepare_dynamics, simulate_dynamics  # noqa: E402

V = 0.25            # m/s, consigna de la banda
CAJA = [150, 120, 100]
Z_CAJA = 800 + 50 + 0.5   # banda arriba en z = 800


@pytest.fixture(scope="module")
def faja():
    doc = Document("faja-piloto")
    doc.execute("create_belt_conveyor", {"largo": 3000, "ancho_banda": 500, "altura": 800})
    return doc


def _run(doc, req):
    req = {"con_autodeteccion": True, **req}
    snap = prepare_dynamics(doc.scene, doc.joints, doc.fasteners, doc.grounds, req, mates=doc.mates)
    return snap, simulate_dynamics(snap)


def _cajas(n=10, x0=-1350.0, paso=200.0, **extra):
    return [{"nombre": f"caja{k}", "dims_mm": CAJA, "masa_kg": 2.0,
             "posicion_mm": [x0 + paso * k, 0, Z_CAJA], **extra} for k in range(n)]


def _vx(frames, nombre):
    """(t, vx m/s) por diferencias de las poses."""
    pts = np.array([[f["t"], f["poses"][nombre][0][3]] for f in frames if nombre in f["poses"]])
    return pts[1:, 0], np.diff(pts[:, 1]) / np.diff(pts[:, 0]) * 1e-3


@pytest.mark.parametrize("modelo,timestep", [("contacto", 0.001), ("rapido", 0.001),
                                              ("contacto", 0.002)])
def test_diez_cajas_llegan_a_la_velocidad_de_la_banda_y_quedan_estables(faja, modelo, timestep):
    """V8.0 lo midió a 1/2/4 ms; aquí, intercambio de 2 ms (default) y de 4 ms."""
    arranque = 0.3
    _, res = _run(faja, {
        "duracion_s": 1.2, "fps": 100, "modelo_banda": modelo, "timestep": timestep,
        "motores": [{"junta": "c1_eje_motriz", "modo": "velocidad", "v_superficie_m_s": V,
                     "direccion_transporte": [1, 0, 0], "desde_s": arranque}],
        "productos": _cajas(),
    })
    r = res["resumen"]
    t95 = []
    for k in range(10):
        t, vx = _vx(res["frames"], f"p_caja{k}")
        t95.append(next(tt for tt, v in zip(t, vx) if tt > arranque and v >= 0.95 * V) - arranque)
    print(f"banda {modelo} {timestep * 2000:g} ms: t95 máx {max(t95):.3f} s, "
          f"factor ×{r['factor_tiempo_real']}")
    assert max(t95) < 0.2, t95
    for p in r["productos"].values():
        assert p["velocidad_final_mm_s"][0] == pytest.approx(V * 1000, rel=0.01)
        assert abs(p["velocidad_final_mm_s"][2]) < 1.0           # |vz| < 1 mm/s
        assert abs(p["posicion_final_mm"][1]) < 1.0              # deriva lateral < 1 mm
    for k in range(10):                                          # ni guiñada ni vuelco
        rot = res["frames"][-1]["poses"][f"p_caja{k}"]
        assert abs(rot[1][0]) < 2e-3 and rot[2][2] > 0.9999
    assert r["bandas"][0]["v_final_m_s"] == pytest.approx(V, rel=0.005)
    assert not r["productos_caidos"]
    # D9: fps REAL (fotogramas por segundo simulado), poses del tambor y de cada caja
    assert len(res["frames"]) == pytest.approx(1.2 * 100 + 1, abs=2)
    assert {"b_c1_eje_motriz", "p_caja0"} <= set(res["frames"][-1]["poses"])


def test_sentido_explicito_con_el_eje_del_ancla_y_con_el_eje_invertido(faja):
    """D7: con direccion_transporte = +X las cajas van a +X, tanto con el ancla tal cual
    ([0, −1, 0], junta virtual) como con una junta declarada sobre [0, 1, 0]; sin ella, la
    banda va hacia la cola (−X) y la salida lo dice."""
    motor = {"junta": "c1_eje_motriz", "modo": "velocidad", "v_superficie_m_s": V}
    base = {"duracion_s": 0.8, "fps": 20, "productos": _cajas(3, x0=-300.0)}

    _, res = _run(faja, {**base, "motores": [{**motor, "direccion_transporte": [1, 0, 0]}]})
    assert res["resumen"]["bandas"][0]["avanza_con_giro_positivo"] == "−X"
    assert res["resumen"]["bandas"][0]["avanza_hacia"] == "+X"
    assert all(p["velocidad_final_mm_s"][0] > 240 for p in res["resumen"]["productos"].values())

    _, res = _run(faja, {**base, "motores": [motor]})        # sin dirección: la trampa
    assert all(p["velocidad_final_mm_s"][0] < -240 for p in res["resumen"]["productos"].values())
    assert any("sin direccion_transporte" in a and "−X" in a for a in res["avisos"])

    doc = Document("faja-eje-invertido")
    doc.execute("create_belt_conveyor", {"largo": 3000, "ancho_banda": 500, "altura": 800})
    o = doc.scene["c1_tambor_motriz"].anchors["eje_motriz"]["origin"]
    doc.execute("add_joint", {"name": "j_tambor", "type": "continua", "parent": "c1_rail1",
                              "child": "c1_tambor_motriz", "origin": dict(zip("xyz", o)),
                              "axis": {"x": 0, "y": 1, "z": 0}})
    _, res = _run(doc, {**base,
                        "bandas": [{"pieza": "c1_banda", "junta_motriz": "j_tambor",
                                    "direccion_transporte": [1, 0, 0]}],
                        "motores": [{"junta": "j_tambor", "modo": "velocidad", "v_superficie_m_s": V}]})
    assert res["resumen"]["bandas"][0]["avanza_con_giro_positivo"] == "+X"
    assert all(p["velocidad_final_mm_s"][0] > 240 for p in res["resumen"]["productos"].values())


def test_fotocelda_marca_el_flanco_en_el_instante_cinematico(faja):
    """La caja viaja ya a v_banda: su cara delantera cruza el rayo (x = 900) en
    t = (900 − 75 − x0)/v. El primer flanco cae a ±1 intercambio de ese instante."""
    x0 = 500.0
    _, res = _run(faja, {
        "duracion_s": 2.0, "fps": 10,
        "motores": [{"junta": "c1_eje_motriz", "modo": "velocidad", "v_superficie_m_s": V,
                     "direccion_transporte": [1, 0, 0]}],
        "productos": [{"nombre": "caja", "dims_mm": CAJA, "masa_kg": 2.0,
                       "posicion_mm": [x0, 0, Z_CAJA], "velocidad_mm_s": [V * 1000, 0, 0]}],
        "sensores": [{"nombre": "foto", "origen": [900, -400, 850], "direccion": [0, 1, 0],
                      "alcance_mm": 800}],
    })
    intercambio = res["resumen"]["intercambio_s"]
    fl = res["sensores"]["foto"]["flancos"]
    sube = (900 - CAJA[0] / 2 - x0) / (V * 1000)
    baja = (900 + CAJA[0] / 2 - x0) / (V * 1000)
    print(f"fotocelda: sube {fl[0]['t']} vs {sube:.4f} s, baja {fl[1]['t']} vs {baja:.4f} s")
    assert fl[0]["tipo"] == "sube" and fl[0]["objeto"] == "p_caja"
    assert abs(fl[0]["t"] - sube) <= intercambio + 1e-9
    assert fl[1]["tipo"] == "baja" and abs(fl[1]["t"] - baja) <= intercambio + 1e-9
    assert res["sensores"]["foto"]["cuentas"] == 1
    assert res["sensores"]["foto"]["muestras"][-1] == [2.0, 0]


def test_alimentacion_en_serie_y_conteo(faja):
    """`cada_s` alimenta cajas como una faja real: entran a su hora y la fotocelda las cuenta."""
    _, res = _run(faja, {
        "duracion_s": 3.0, "fps": 20,
        "motores": [{"junta": "c1_eje_motriz", "modo": "velocidad", "v_superficie_m_s": V,
                     "direccion_transporte": [1, 0, 0]}],
        "productos": [{"nombre": "caja", "dims_mm": CAJA, "masa_kg": 2.0, "cada_s": 0.8,
                       "posicion_mm": [-200, 0, Z_CAJA], "velocidad_mm_s": [V * 1000, 0, 0]}],
        "sensores": [{"nombre": "foto", "origen": [0, -400, 850], "direccion": [0, 1, 0]}],
    })
    entradas = [p["aparece_s"] for p in res["productos"]]
    assert entradas == pytest.approx([0.0, 0.8, 1.6, 2.4])
    # una caja no aparece antes de su hora (espera estacionada, fuera de la salida)
    assert all("p_caja_2" not in f["poses"] for f in res["frames"] if f["t"] < 1.6 - 1e-6)
    assert any("p_caja_2" in f["poses"] for f in res["frames"])
    # separación 0,8·250 = 200 mm (cajas de 150): la caja k cruza x = 0 en 0,8·k + 0,5
    fl = [f["t"] for f in res["sensores"]["foto"]["flancos"] if f["tipo"] == "sube"]
    assert fl == pytest.approx([0.5, 1.3, 2.1, 2.9], abs=0.005)
    assert res["sensores"]["foto"]["cuentas"] == 4


def test_producto_girado_nace_con_su_rotacion(faja):
    """`rotacion_deg` con la convención de `rotation` de Apolo: 90° en Z lleva X a Y."""
    _, res = _run(faja, {"duracion_s": 0.1, "fps": 10, "productos": [
        {"nombre": "girada", "dims_mm": CAJA, "posicion_mm": [0, 0, Z_CAJA + 15],
         "rotacion_deg": [0, 0, 90]}]})
    r = res["frames"][0]["poses"]["p_girada"]
    assert r[1][0] == pytest.approx(1.0, abs=1e-6) and r[0][1] == pytest.approx(-1.0, abs=1e-6)
    assert res["productos"][0]["rotacion_deg"] == [0, 0, 90]


def test_rodillos_llevan_las_cajas_a_la_velocidad_periferica():
    """D6: rodillos con hinge + `<velocity>` y fricción NATIVA caja–rodillo (cápsulas). Sin
    tocar los largueros aunque sus AABB se solapen (grupos de colisión)."""
    doc = Document("rodillos")
    doc.execute("create_conveyor", {"largo": 1100, "ancho": 600, "altura": 750, "paso": 100})
    rods = sorted((f for f in doc.scene if "_rod" in f), key=lambda s: int(s.split("rod")[1]))
    for fid in rods:
        m = np.asarray(doc.scene[fid].matrix)
        doc.execute("add_joint", {"name": f"j_{fid.split('_')[1]}", "type": "continua",
                                  "parent": "c1_rail1", "child": fid,
                                  "origin": dict(zip("xyz", m[:3, 3])), "axis": {"x": 0, "y": 1, "z": 0}})
    v = 0.2
    snap, res = _run(doc, {
        "duracion_s": 1.5, "fps": 20,
        "motores": [{"junta": f"j_{r.split('_')[1]}", "modo": "velocidad", "v_superficie_m_s": v,
                     "direccion_transporte": [1, 0, 0]} for r in rods],
        "productos": [{"nombre": f"c{k}", "dims_mm": [220, 300, 100], "masa_kg": 3.0,
                       "posicion_mm": [-400 + 230 * k, 0, 750 + 50 + 0.5]} for k in range(2)],
    })
    # el rodillo es CÁPSULA (gira sobre su eje), no casco: radio 25, sin el eje que entra al larguero
    assert 'type="capsule"' in snap.xml and 'size="0.025000"' in snap.xml
    for p in res["resumen"]["productos"].values():
        assert p["velocidad_final_mm_s"][0] == pytest.approx(v * 1000, rel=0.02)
    # un rodillo sin caja encima gira sin par: no roza el bastidor
    libres = [n for n, j in res["resumen"]["juntas"].items() if abs(j["par_final"]) < 1e-6]
    assert libres, "todos los rodillos llevan par: ¿frotan el larguero?"
    assert all(j["velocidad_final_rpm"] == pytest.approx(v / 0.025 * 60 / (2 * np.pi), rel=1e-3)
               for j in res["resumen"]["juntas"].values())
