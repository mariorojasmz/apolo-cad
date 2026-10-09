"""V8.2 F1 — dinámica con juntas reales: referencias físicas de mecanismos.

Péndulo en eje OBLICUO (periodo), tambor con par constante (α = T/J), motor de inducción por
velocidad bajo carga (deslizamiento, sin oscilar a 2 y 4 ms de intercambio) y exclusiones
(cuerpo sin sujeción fuera, padre–hijo sin contacto). La banda, los rodillos y la fotocelda
están en `test_dinamica_banda.py`. Requiere MuJoCo."""

import math
import re

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")

from apolo.doc.document import Document  # noqa: E402
from apolo.library.engineering.motor_induccion import kloss_linealizado  # noqa: E402
from apolo.physics.dinamica import prepare_dynamics, simulate_dynamics  # noqa: E402
from apolo.physics.sim import PhysicsError  # noqa: E402

G = 9.81


def _box(doc, name, pos, size=(100, 100, 100)):
    return doc.execute("create_box", {"name": name, "width": size[0], "depth": size[1],
                                      "height": size[2],
                                      "position": {"x": pos[0], "y": pos[1], "z": pos[2]}})


def _soporte(doc, pos=(0, 0, 50), size=(100, 100, 100)):
    s = _box(doc, "Soporte", pos, size)
    doc.execute("ground", {"name": "g_soporte", "feature": s})
    return s


def _junta(doc, name, parent, child, origin, axis, tipo="continua", lower=-180, upper=180):
    doc.execute("add_joint", {"name": name, "type": tipo, "parent": parent, "child": child,
                              "origin": dict(zip("xyz", origin)), "axis": dict(zip("xyz", axis)),
                              "lower": lower, "upper": upper})


def _run(doc, req):
    snap = prepare_dynamics(doc.scene, doc.joints, doc.fasteners, doc.grounds, req, mates=doc.mates)
    return snap, simulate_dynamics(snap)


def _cruces(t, x):
    """Instantes (interpolados) en que x cruza su media subiendo."""
    t, x = np.asarray(t), np.asarray(x) - np.mean(x)
    return [t[i] - x[i] * (t[i + 1] - t[i]) / (x[i + 1] - x[i])
            for i in range(len(x) - 1) if x[i] < 0 <= x[i + 1]]


def test_pendulo_en_eje_oblicuo_cumple_el_periodo():
    """Péndulo físico sobre un eje que no es X/Y/Z (la FK no lo admite; MuJoCo sí):
    T = 2π·√(I/(m·g_ef·d)), con g_ef la gravedad perpendicular al eje. ±2 %."""
    doc = Document("pendulo")
    sop = _soporte(doc, pos=(0, 0, 900))
    pivote = np.array([0.0, 0.0, 900.0])
    a = np.array([1.0, 1.0, 0.5])
    a /= np.linalg.norm(a)
    z = np.array([0.0, 0.0, 1.0])
    abajo = -(z - (z @ a) * a)
    abajo /= np.linalg.norm(abajo)
    d_mm, theta0 = 300.0, math.radians(5.0)
    # el COM arranca girado θ0 sobre el eje desde el equilibrio: oscila sin motor
    u = abajo * math.cos(theta0) + np.cross(a, abajo) * math.sin(theta0)
    com = pivote + d_mm * u
    lado = (80.0, 60.0, 40.0)
    bob = _box(doc, "Masa", com, lado)
    _junta(doc, "pivote", sop, bob, pivote, a)
    snap, res = _run(doc, {"duracion_s": 3.5, "fps": 120})
    assert 'type="mesh"' in snap.xml and 'type="capsule"' not in snap.xml  # una caja no gira «redonda»

    m = 1.0  # I/m no depende de la masa
    icm = np.diag([lado[1] ** 2 + lado[2] ** 2, lado[0] ** 2 + lado[2] ** 2,
                   lado[0] ** 2 + lado[1] ** 2]) * m / 12.0
    r = com - pivote
    i_eje = a @ icm @ a + m * (r @ r - (r @ a) ** 2)
    g_ef = G * math.sqrt(1 - (z @ a) ** 2)
    t_ref = 2 * math.pi * math.sqrt(i_eje * 1e-6 / (m * g_ef * d_mm * 1e-3))

    tr = res["juntas"]["pivote"]
    cruces = _cruces(tr["t"], tr["q"])
    assert len(cruces) >= 2, cruces
    t_med = float(np.mean(np.diff(cruces)))
    err = abs(t_med - t_ref) / t_ref
    print(f"péndulo: periodo {t_med:.4f} s vs {t_ref:.4f} s ({err:.3%})")
    assert err < 0.02, f"periodo {t_med:.4f} s vs {t_ref:.4f} s ({err:.2%})"
    # q = 0 es la pose de diseño (5° fuera del equilibrio): oscila entre 0 y −10° o +10°
    assert (max(tr["q"]) - min(tr["q"])) / 2 == pytest.approx(5.0, abs=0.3)
    # la pose 4×4 del cuerpo sigue a la junta: a media oscilación el COM se movió
    assert res["piezas"][0]["id"] == bob and res["piezas"][0]["name"] == res["cuerpos"][0]["name"]


def test_tambor_con_par_constante_acelera_a_t_sobre_j():
    """α = T/J con J de la geometría real (cilindro macizo: ½·m·r²). ±2 %."""
    doc = Document("tambor")
    sop = _soporte(doc)
    tam = doc.execute("create_cylinder", {"name": "Tambor", "radius": 50, "height": 400,
                                          "axis": "y", "position": {"x": 0, "y": 0, "z": 400}})
    _junta(doc, "eje", sop, tam, (0, 0, 400), (0, 1, 0))
    par = 5.0
    snap, res = _run(doc, {"duracion_s": 1.0, "fps": 50,
                           "motores": [{"junta": "eje", "modo": "par", "valor": par}]})
    masa = snap.cuerpos[0]["masa_kg"]
    j_ref = 0.5 * masa * 0.05 ** 2
    # sin ficha de catálogo, el giro se detecta por la cara cilíndrica coaxial: cápsula
    assert 'type="capsule"' in snap.xml and 'size="0.050000"' in snap.xml
    assert snap.cuerpos[0]["inercia_eje_kgm2"] == pytest.approx(j_ref, rel=0.005)
    tr = res["juntas"]["eje"]
    t, w = np.asarray(tr["t"]), np.asarray(tr["qd"]) * 2 * math.pi / 60
    alfa = float(np.polyfit(t, w, 1)[0])
    err = abs(alfa - par / j_ref) / (par / j_ref)
    print(f"tambor: α {alfa:.4f} vs {par / j_ref:.4f} rad/s² ({err:.3%})")
    assert err < 0.02, f"α {alfa:.3f} vs {par / j_ref:.3f} rad/s² ({err:.2%})"
    assert tr["par"][-1] == pytest.approx(par, rel=1e-6)
    assert tr["unidades"] == {"q": "grados", "qd": "rpm", "par": "N·m"}


@pytest.mark.parametrize("nstep", [2, 4])
def test_motor_por_velocidad_llega_al_deslizamiento_sin_oscilar(nstep):
    """Motor de inducción + reductor (Kloss linealizado, `<velocity>` nativo) con la carga
    nominal: llega a ωs·(1−s)/i y se queda quieto, con intercambio de 2 y 4 ms."""
    doc = Document("motor")
    sop = _soporte(doc)
    tam = doc.execute("create_cylinder", {"name": "Tambor", "radius": 60, "height": 300,
                                          "axis": "y", "position": {"x": 0, "y": 0, "z": 400}})
    _junta(doc, "eje", sop, tam, (0, 0, 400), (0, 1, 0))
    placa = {"potencia_kW": 1.1, "rpm": 1740, "frecuencia_hz": 60, "tk_tn": 2.6}
    i, eta = 20.0, 0.9
    k = kloss_linealizado(placa, i, eta)
    carga = k["Tn_Nm"] * i * eta
    _, res = _run(doc, {"duracion_s": 1.5, "fps": 100, "nstep": nstep, "motores": [
        {"junta": "eje", "modo": "velocidad", "placa": placa, "reduccion": i, "eta": eta},
        {"junta": "eje", "modo": "par", "valor": -carga},
    ]})
    tr = res["juntas"]["eje"]
    w = np.asarray(tr["qd"]) * 2 * math.pi / 60
    cola = w[np.asarray(tr["t"]) >= 1.0]
    w_lineal = k["omega_sinc_rad_s"] - carga / k["kv"]
    print(f"motor nstep={nstep}: ω {cola.mean():.5f} vs lineal {w_lineal:.5f} vs placa "
          f"{k['omega_nominal_rad_s']:.5f} rad/s, σ {cola.std():.2e}")
    assert float(cola.mean()) == pytest.approx(w_lineal, rel=1e-3)
    # la placa: ωs(1−sn)/i (la recta tangente a Kloss se aparta < 0,5 % en el nominal)
    assert float(cola.mean()) == pytest.approx(k["omega_nominal_rad_s"], rel=5e-3)
    assert float(cola.std()) < 1e-4 * k["omega_nominal_rad_s"], "oscila"
    assert res["motores"][0]["modelo"].startswith("motor de inducción")
    # el rotor reflejado (J·i²) entra al eje: domina la inercia de un tambor chico
    assert res["cuerpos"][0]["armadura_kgm2"] == pytest.approx(k["inercia_reflejada_kgm2"], rel=1e-4)


def test_tope_de_par_sin_inercia_suficiente_no_oscila():
    """Un `<velocity>` con tope sobre una inercia chica salta la consigna en un paso y oscila
    entre topes (medido en F1: velocidad media 0). Se suma la inercia mínima y se avisa."""
    doc = Document("tope")
    sop = _soporte(doc)
    tam = doc.execute("create_cylinder", {"name": "Polea", "radius": 40, "height": 100,
                                          "axis": "y", "position": {"x": 0, "y": 0, "z": 400}})
    _junta(doc, "eje", sop, tam, (0, 0, 400), (0, 1, 0))
    _, res = _run(doc, {"duracion_s": 1.0, "fps": 50, "motores": [
        {"junta": "eje", "modo": "velocidad", "valor": 100, "kv": 1000, "par_max": 50}]})
    assert any("inercia" in a and "oscile" in a for a in res["avisos"])
    qd = res["juntas"]["eje"]["qd"]
    assert qd[-1] == pytest.approx(100.0, rel=1e-3) and abs(qd[-1] - qd[-5]) < 0.01


def test_cuerpo_sin_sujecion_queda_fuera_con_aviso():
    doc = Document("fuera")
    sop = _soporte(doc, pos=(0, 0, 500))
    brazo = _box(doc, "Brazo", (0, 200, 500), (40, 300, 40))
    _junta(doc, "giro", sop, brazo, (0, 50, 500), (1, 0, 0), tipo="giratoria", lower=-90, upper=90)
    suelta = _box(doc, "Caja suelta", (800, 0, 600))
    snap, res = _run(doc, {"duracion_s": 1.0})
    piezas = {p for c in snap.cuerpos for p in c["piezas"]}
    assert suelta not in piezas and f'"e_{suelta}"' not in snap.xml
    assert any(suelta in a and "FUERA" in a for a in res["avisos"])
    # la junta móvil sí entra, cae por gravedad y llega a su tope (giratoria = hinge con range)
    assert brazo in piezas
    tope = res["resumen"]["juntas_en_limite"]
    assert [t["junta"] for t in tope] == ["giro"] and abs(tope[0]["limite"]) == 90
    # tope duro (solreflimit corto): la penetración del impacto queda < 1°
    assert min(res["juntas"]["giro"]["q"]) >= -91.0 and max(res["juntas"]["giro"]["q"]) <= 91.0


def test_pieza_fijada_a_un_cuerpo_movil_sin_junta_pide_arrastrar():
    doc = Document("arrastre")
    sop = _soporte(doc)
    brazo = _box(doc, "Brazo", (0, 200, 100), (40, 300, 40))
    _junta(doc, "giro", sop, brazo, (0, 50, 100), (1, 0, 0))
    peso = _box(doc, "Contrapeso", (0, 380, 100), (60, 60, 60))
    doc.execute("fasten", {"name": "f_peso", "a": brazo, "b": peso})
    snap, res = _run(doc, {"duracion_s": 0.1})
    assert any("arrastrar=true" in a for a in res["avisos"])
    # con la junta fija, el contrapeso viaja en el cuerpo del brazo
    doc.execute("add_joint", {"name": "jf_peso", "type": "fija", "parent": brazo, "child": peso})
    snap, _ = _run(doc, {"duracion_s": 0.1})
    assert snap.cuerpos[0]["piezas"] == [brazo, peso]


def test_padre_e_hijo_no_chocan_aunque_se_solapen():
    """Con `colisiones_maquina` el brazo choca con lo estático, MENOS con su padre: el
    `<exclude>` padre–hijo deja oscilar un brazo cuyo casco se mete en el soporte."""
    doc = Document("exclude")
    sop = _soporte(doc, pos=(0, 0, 600), size=(120, 120, 120))
    # el brazo arranca DENTRO del soporte (su casco lo atraviesa) y cuelga del pivote
    brazo = _box(doc, "Brazo", (0, 0, 450), (30, 30, 400))
    _junta(doc, "pivote", sop, brazo, (0, 0, 600), (1, 0, 0))
    req = {"duracion_s": 0.5, "colisiones_maquina": True}
    snap = prepare_dynamics(doc.scene, doc.joints, doc.fasteners, doc.grounds, req)
    m = mujoco.MjModel.from_xml_string(snap.xml)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    assert d.ncon == 0, "el brazo choca con su soporte"
    # sin el exclude sí chocarían: prueba de que el test no es vacío
    m2 = mujoco.MjModel.from_xml_string(re.sub(r"<contact>.*?</contact>", "", snap.xml))
    d2 = mujoco.MjData(m2)
    mujoco.mj_forward(m2, d2)
    assert d2.ncon > 0
    # y desplazado 30° de su equilibrio (sin dejar de atravesar el soporte), oscila libre
    doc2 = Document("exclude2")
    sop2 = _soporte(doc2, pos=(0, 0, 600), size=(120, 120, 120))
    b2 = _box(doc2, "Brazo", (0, 50, 600 - 86.6), (30, 30, 400))
    _junta(doc2, "pivote", sop2, b2, (0, 0, 600), (1, 0, 0))
    _, res = _run(doc2, {"duracion_s": 0.6, "colisiones_maquina": True, "fps": 60})
    q = res["juntas"]["pivote"]["q"]
    assert max(q) - min(q) > 40.0, "quedó trabado contra su soporte"


def test_peticion_rechaza_con_mensaje_accionable():
    doc = Document("peticion")
    sop = _soporte(doc)
    tam = doc.execute("create_cylinder", {"name": "Tambor", "radius": 50, "height": 300,
                                          "axis": "y", "position": {"x": 0, "y": 0, "z": 400}})
    _junta(doc, "eje", sop, tam, (0, 0, 400), (0, 1, 0))

    def falla(req, *esperado):
        with pytest.raises(PhysicsError) as exc:
            prepare_dynamics(doc.scene, doc.joints, doc.fasteners, doc.grounds, req)
        for e in esperado:
            assert e in str(exc.value), str(exc.value)

    falla({"duracion": 2}, "duracion_s")                       # sugiere la clave buena
    falla({"duracion_s": 90}, "≤ 60")
    falla({"motores": [{"junta": "ej", "modo": "par", "valor": 1}]}, "'eje'")  # lista las juntas
    falla({"motores": [{"junta": "eje", "modo": "velocidad"}]}, "UNA consigna")
    falla({"motores": [{"junta": "eje", "modo": "velocidad", "valor": 10,
                        "direccion_transporte": [0, 1, 0]}]}, "perpendicular")
    falla({"productos": [{"dims_mm": [100, 100, 100]}]}, "posicion_mm")
    falla({"sensores": [{"tipo": "laser", "origen": [0, 0, 0], "direccion": [1, 0, 0]}]}, "rayo")
    falla({"timestep": 0.01, "nstep": 5}, "20 ms")


def test_nada_que_simular_devuelve_aviso():
    doc = Document("vacio")
    _soporte(doc)
    snap = prepare_dynamics(doc.scene, doc.joints, doc.fasteners, doc.grounds, {})
    assert snap.xml is None
    assert "Nada que simular" in simulate_dynamics(snap)["mensaje"]
