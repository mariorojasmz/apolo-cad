"""La posición INICIAL de una junta en un escenario (plan motor-a-eje-lineal F4).

`mecanica.juntas.<junta>.inicial` (mm o grados desde la pose de diseño) es dónde ARRANCA la junta:
el qpos inicial de MuJoCo, y con él los sensores por junta y el aire. Bancos: el elevador mínimo de
`elevador_escena.py` (prismática), un brazo en una junta giratoria (la dinámica suelta) y el
empujador de `neumatica_escena.py` con los tubos cruzados (en reposo la válvula lo saca, como la
compuerta de la mezcladora que cierra en reposo).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("mujoco")

from elevador_escena import JUNTA, NIVEL_MM, PROGRAMAS, elevador, escenario, transmision  # noqa: E402
from neumatica_escena import CARRERA, empujador  # noqa: E402
from neumatica_escena import escenario as escenario_aire  # noqa: E402

from apolo.cosim.corrida import Corrida  # noqa: E402
from apolo.cosim.escenario import EscenarioInvalido, leer_escenario  # noqa: E402
from apolo.cosim.planificador import correr  # noqa: E402
from apolo.cosim.vivo_fotograma import Fotograma  # noqa: E402
from apolo.doc.document import Document  # noqa: E402
from apolo.physics.dinamica import prepare_dynamics, simulate_dynamics  # noqa: E402
from apolo.physics.dinamica_serie import serie_reproduccion  # noqa: E402
from apolo.physics.sim import PhysicsError  # noqa: E402
from apolo.services import escenarios as E  # noqa: E402
from apolo.services.aire_resultado import _carreras, resumen_aire  # noqa: E402
from apolo.services.cosim_snapshot import snapshot_cosim  # noqa: E402
from apolo.services.errors import ServiceError  # noqa: E402


def _inicial(esc: dict, junta: str, q: float) -> dict:
    esc["mecanica"] = {"juntas": {junta: {"inicial": q}}}
    return esc


def _en(serie_t, serie, t):
    return next(v for tt, v in zip(serie_t, serie) if tt >= t - 1e-9)


@pytest.fixture(scope="module")
def doc():
    return elevador()


# ── prismática: el elevador arranca arriba ───────────────────────────────────────────────────


def test_la_prismatica_arranca_en_su_inicial_y_el_sensor_la_ve_al_bajar(doc):
    """Reversible y sin marcha, desde 700 mm: la gravedad la baja y -B1 (500 ± 10 mm sobre la
    junta) la ve al pasar; la hipótesis lo dice."""
    snap = snapshot_cosim(doc, _inicial(escenario(3.5, marcha=False), JUNTA, 700.0), programas=PROGRAMAS)
    assert snap.dinamica.inicial == {JUNTA: pytest.approx(0.7)}
    assert any(h.startswith(f"{JUNTA} arranca en 700 mm") for h in snap.hipotesis)
    r = correr(snap)
    j = r["mecanica"]["juntas"][JUNTA]
    assert j["q"][0] == pytest.approx(700.0, abs=0.01)
    disc = r["trazas"]["discretas"]["-B1.activo"]
    assert disc[0][1] is False  # a 700 mm el sensor de 500 no la ve
    t_b1 = next(t for t, v in disc if v)
    assert _en(j["t"], j["q"], t_b1) == pytest.approx(NIVEL_MM + 10, abs=8)
    assert j["q"][-1] < NIVEL_MM


def test_irreversible_queda_donde_arranca(doc):
    r = correr(snapshot_cosim(doc, _inicial(escenario(1.0, marcha=False, tr=transmision(irreversible=True)),
                                            JUNTA, 700.0), programas=PROGRAMAS))
    q = r["mecanica"]["juntas"][JUNTA]["q"]
    assert max(abs(x - 700.0) for x in q) < 0.5


def test_el_visor_dibuja_desde_la_pose_de_diseno(doc):
    """La malla es la de diseño: el vivo y la serie toman P(0) = la pose de DISEÑO, no la de
    arranque (si no, la plataforma se vería en la cota 0 al empezar)."""
    snap = snapshot_cosim(doc, _inicial(escenario(0.2, marcha=False, tr=transmision(irreversible=True)),
                                        JUNTA, 700.0), programas=PROGRAMAS)
    c = Corrida(snap)
    nombre = snap.dinamica.cuerpos[0]["name"]
    rel = np.asarray(c.integ.frames[0]["poses"][nombre], float) @ np.linalg.inv(
        np.asarray(c.integ.poses_diseno[nombre], float))
    assert rel[2, 3] == pytest.approx(700.0, abs=1e-6)       # 700 mm arriba de la de diseño
    f = Fotograma(c)
    assert np.allclose(np.linalg.inv(f.p0_inv[0]), c.integ.poses_diseno[nombre])


# ── giro: la dinámica suelta ─────────────────────────────────────────────────────────────────


def _brazo():
    doc = Document("brazo")
    sop = doc.execute("create_box", {"name": "Soporte", "width": 100, "depth": 100, "height": 100,
                                     "position": {"x": 0, "y": 0, "z": 500}})
    doc.execute("ground", {"name": "g_soporte", "feature": sop})
    brazo = doc.execute("create_box", {"name": "Brazo", "width": 40, "depth": 300, "height": 40,
                                       "position": {"x": 0, "y": 200, "z": 500}})
    doc.execute("add_joint", {"name": "giro", "type": "giratoria", "parent": sop, "child": brazo,
                              "origin": {"x": 0, "y": 50, "z": 500}, "axis": {"x": 1, "y": 0, "z": 0},
                              "lower": -90, "upper": 90})
    return doc


def _dinamica(doc, juntas=None, duracion=0.5):
    req = {"duracion_s": duracion, "fps": 50, **({"juntas": juntas} if juntas is not None else {})}
    snap = prepare_dynamics(doc.scene, doc.joints, doc.fasteners, doc.grounds, req, mates=doc.mates)
    return snap, simulate_dynamics(snap)


def test_la_giratoria_arranca_en_su_inicial_y_la_serie_parte_girada():
    doc = _brazo()
    snap, res = _dinamica(doc, {"giro": {"inicial": 45}})
    tr = res["juntas"]["giro"]
    assert tr["q"][0] == pytest.approx(45.0, abs=1e-6)
    assert tr["q"][-1] < 45.0 - 5        # cae por gravedad desde ahí
    assert "poses_diseno" in res
    serie = serie_reproduccion(res, snap.bandas, hz=50)
    qx, _qy, _qz, qw = serie["cuerpos"][snap.cuerpos[0]["name"]]["poses"][3:7]
    assert qw == pytest.approx(math.cos(math.radians(22.5)), abs=1e-4)   # 45° sobre X desde diseño
    assert abs(qx) == pytest.approx(math.sin(math.radians(22.5)), abs=1e-4)


def test_inicial_cero_es_la_corrida_de_siempre():
    """Un escenario sin `inicial` no cambia (ni la clave nueva en la salida); con `inicial` = 0 la
    física es la misma muestra a muestra."""
    doc = _brazo()
    snap0, sin = _dinamica(doc)
    assert snap0.inicial == {} and "poses_diseno" not in sin
    _snap, cero = _dinamica(doc, {"giro": {"inicial": 0}})
    assert cero["juntas"]["giro"]["q"] == sin["juntas"]["giro"]["q"]
    assert [f["poses"] for f in cero["frames"]] == [f["poses"] for f in sin["frames"]]


def test_la_continua_acepta_cualquier_angulo_y_la_fuera_de_limites_no():
    doc = _brazo()
    with pytest.raises(PhysicsError, match=r"fuera de los límites de 'giro' \[-90, 90\]"):
        _dinamica(doc, {"giro": {"inicial": 120}})
    with pytest.raises(PhysicsError, match="¿Quisiste decir 'giro'"):
        _dinamica(doc, {"gir0": {"inicial": 10}})
    tambor = Document("tambor")
    sop = tambor.execute("create_box", {"name": "Soporte", "width": 100, "depth": 100, "height": 100,
                                        "position": {"x": 0, "y": 0, "z": 50}})
    tambor.execute("ground", {"name": "g", "feature": sop})
    tam = tambor.execute("create_cylinder", {"name": "Tambor", "radius": 50, "height": 300, "axis": "y",
                                             "position": {"x": 0, "y": 0, "z": 400}})
    tambor.execute("add_joint", {"name": "eje", "type": "continua", "parent": sop, "child": tam,
                                 "origin": {"x": 0, "y": 0, "z": 400}, "axis": {"x": 0, "y": 1, "z": 0},
                                 "lower": -180, "upper": 180})
    _snap, res = _dinamica(tambor, {"eje": {"inicial": 400}}, duracion=0.1)
    assert res["juntas"]["eje"]["q"][0] == pytest.approx(400.0, abs=1e-6)


# ── al declarar ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("op, texto", [
    ({"incial": 300}, "¿Quisiste decir «inicial»?"),
    ({"inicial": "arriba"}, "número finito"),
    ({"friccion": -1}, "fuera de"),
])
def test_la_forma_se_revisa_al_leer(op, texto):
    esc = escenario(1.0)
    esc["mecanica"] = {"juntas": {JUNTA: op}}
    with pytest.raises(EscenarioInvalido, match=texto):
        leer_escenario(esc)


@pytest.mark.parametrize("junta, q, texto", [
    (JUNTA, 2000, r"fuera de los límites de 'j_plataforma' \[-250, 1600\] mm"),
    ("j_plataform", 300, "¿Quisiste decir 'j_plataforma'"),
])
def test_fuera_de_limites_se_rechaza_al_declarar(doc, junta, q, texto):
    with pytest.raises(ServiceError, match=texto) as exc:
        E.poner(doc, "arriba", _inicial(escenario(1.0), junta, q))
    assert exc.value.status_code == 400 and "arriba" not in doc.escenarios
    assert str(exc.value.detail).startswith(f"mecanica.juntas.{junta}.inicial")


# ── el aire de un cilindro que arranca extendido ─────────────────────────────────────────────


@pytest.fixture(scope="module")
def cruzado():
    return empujador(avanza_en_reposo=True)


def _aire(doc_cid, inicial=None, **kw):
    d, cid = doc_cid
    esc = escenario_aire(cid, caja=False, **kw)
    if inicial is not None:
        _inicial(esc, f"{cid}_vastago", inicial)
    return correr(snapshot_cosim(d, esc))


def test_un_cilindro_que_arranca_cerrado_no_da_el_golpe_del_arranque_abierto(cruzado):
    """En reposo la válvula alimenta la A: dibujado retraído (x = 0) el vástago sale de golpe al
    arrancar (la cámara B a la atmósfera, sin colchón); arrancando extendido está en equilibrio
    contra su tope, con la A a la presión de la línea y la B a la atmósfera."""
    abierto = _aire(cruzado, duracion=0.6, pulsar_s=0)
    va = abierto["trazas"]["analogicas"]["senales"]["-MM1.v_m_s"]
    assert max(abs(v) for v in va) > 3.0
    cerrado = _aire(cruzado, CARRERA, duracion=0.6, pulsar_s=0)
    a = cerrado["trazas"]["analogicas"]
    s = a["senales"]
    assert max(abs(v) for v in s["-MM1.v_m_s"]) < 0.01
    assert s["-MM1.x_mm"][0] == pytest.approx(CARRERA, abs=0.01)
    assert s["-MM1.pA_bar"][0] == pytest.approx(6.0, abs=0.01) and abs(s["-MM1.pB_bar"][0]) < 0.01
    assert min(s["-MM1.x_mm"]) > CARRERA - 0.5


def test_el_retroceso_de_un_cilindro_que_arranca_extendido_se_mide(cruzado):
    """-S2 lo retrae (0,2 s) y al soltar sale otra vez: la memoria lee su retroceso (el primero,
    desde donde arrancó) y su avance."""
    r = _aire(cruzado, CARRERA, duracion=2.5, pulsar_s=1.0)
    fila = resumen_aire(r)["cilindros"]["-MM1"]
    assert 0 < fila["t_retroceso_s"] < 0.5 and 0 < fila["t_avance_s"] < 0.5


def test_carreras_desde_arriba_y_desde_abajo():
    t = [0.1 * k for k in range(8)]
    # desde abajo: lo de siempre (avance y el retroceso que le sigue)
    assert _carreras(t, [0, 0, 100, 200, 200, 100, 0, 0]) == {
        "x_max_mm": 200, "t_avance_s": pytest.approx(0.192, abs=1e-3), "t_retroceso_s": pytest.approx(0.192, abs=1e-3)}
    # desde arriba (el golpe del tope lleva el máximo a 204): el retroceso, del 98 % de donde
    # arrancó (196) al 2 % del máximo (4,08), y el avance que hace después
    out = _carreras(t, [200, 200, 100, 0, 0, 100, 204, 200])
    assert out["t_retroceso_s"] == pytest.approx(0.2959 - 0.104, abs=1e-3)
    assert out["t_avance_s"] == pytest.approx(0.59608 - 0.40408, abs=1e-3)
