"""visor-realista F3 (D6) — la faja con su forma real y las cadenas que avanzan, sin física.

- `library/ruta_faja.py`: la ruta de la línea media (envolvente de los tambores de adentro, apoyos
  por afuera, comba con sus topes: CEMA, tensión y holgura con lo de abajo).
- `services/marcha_visual.py`: lo que se extrae del documento (encuadres en el marco de la faja,
  qué es redondo; el lazo de cada cadena por su `mesh_key`).
- `library/marcha_visual.py`: lo que va a la serie (qué junta mueve cada cadena, la tensión del
  ramal flojo de la tracción medida, los rodillos libres con su eje de giro).
"""

from __future__ import annotations

import math

import pytest

from apolo.doc.document import Document
from apolo.library.catalog import CATALOG
from apolo.library.marcha_visual import armar, cadena_visual, recorrido_mm
from apolo.library.ruta_faja import COMBA_CEMA, PiezaPlano, envolvente, ruta_faja
from apolo.services.marcha_visual import extraer_marcha_visual


def _banda():
    """Lazo sobre dos tambores r 50 a ±1000 (u), banda de 2 mm y 500 de ancho."""
    return PiezaPlano("banda", -1052, 1052, -52, 52, -250, 250)


def _tambor(nombre, u, r=50.0, w=0.0):
    return PiezaPlano(nombre, u - r, u + r, w - r, w + r, -275, 275, redonda=True)


def _area(puntos):
    return 0.5 * sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(puntos, puntos[1:] + puntos[:1]))


def _w_en(ruta, u, abajo=True):
    """w de la ruta en u (el ramal de abajo o el de arriba), por interpolación."""
    pts = ruta.puntos + ruta.puntos[:1]
    vals = [a[1] + (b[1] - a[1]) * (u - a[0]) / (b[0] - a[0])
            for a, b in zip(pts, pts[1:]) if min(a[0], b[0]) <= u <= max(a[0], b[0]) and a[0] != b[0]]
    return min(vals) if abajo else max(vals)


# ------------------------------------------------------------------ la ruta (pura)
def test_envolvente_de_dos_circulos_es_antihoraria_con_sus_tramos_tangentes():
    casco = envolvente([(-1000, 0, 51), (1000, 0, 51)])
    pts = [(u, w) for u, w, _ in casco]
    assert _area(pts) > 0
    assert casco[0][2] != casco[-1][2]   # empieza en un tambor después de un tramo
    assert max(w for _, w in pts) == pytest.approx(51, abs=0.05)


def test_la_banda_abraza_sus_tambores_y_cuelga_entre_los_apoyos_del_retorno():
    retorno = _tambor("retorno", 0.0, r=20, w=-72)   # su tope toca la cara de abajo (−52)
    ruta = ruta_faja(_banda(), [_tambor("cola", -1000), _tambor("motriz", 1000), retorno])
    assert ruta.espesor == pytest.approx(2.0)
    assert sorted(e["pieza"] for e in ruta.envueltos) == ["cola", "motriz"]
    assert all(e["abrazamiento_deg"] == pytest.approx(180, abs=1.5) for e in ruta.envueltos)
    assert [a["pieza"] for a in ruta.apoyos_fuera] == ["retorno"]
    assert [t["limita"] for t in ruta.tramos] == ["cema", "cema"]
    assert [t["largo_mm"] for t in ruta.tramos] == pytest.approx([1000, 1000], abs=1)
    assert ruta.tramos[0]["comba_mm"] == pytest.approx(COMBA_CEMA * 1000, abs=0.5)
    assert _w_en(ruta, -500) == pytest.approx(-51 - 20, abs=0.5)    # cuelga a la mitad del vano
    assert _w_en(ruta, 0) == pytest.approx(-51, abs=0.5)            # apoya en el rodillo
    assert _w_en(ruta, -500, abajo=False) == pytest.approx(51, abs=0.01)  # arriba, recta
    assert _area(ruta.puntos) > 0
    assert ruta.largo_mm > 2 * 2000 + 2 * math.pi * 51


def test_la_comba_no_atraviesa_lo_que_hay_debajo_ni_supera_la_de_la_tension():
    travesano = PiezaPlano("travesano", -600, -400, -62, -57, -300, 300)   # 5 mm bajo la banda
    cama = PiezaPlano("cama", -900, 900, 20, 45, -260, 260)                # adentro: no cuenta
    guarda = PiezaPlano("guarda", -900, 900, -200, -100, 260, 270)         # no cruza la banda
    ruta = ruta_faja(_banda(), [_tambor("cola", -1000), _tambor("motriz", 1000), travesano, cama, guarda])
    (vano,) = ruta.tramos
    assert vano["limita"] == "holgura"
    # la cara de afuera (línea media − 1) llega como mucho al tope del travesaño (−57)
    assert min(_w_en(ruta, u) for u in (-600, -550, -500, -450, -400)) >= -56 - 0.05
    con_tension = ruta_faja(_banda(), [_tambor("cola", -1000), _tambor("motriz", 1000)],
                            peso_n_mm=0.01, tension_n=1000.0)
    (vano,) = con_tension.tramos
    assert vano["limita"] == "tension"
    assert vano["comba_mm"] == pytest.approx(0.01 * 2000 ** 2 / (8 * 1000), rel=0.01)


def test_sin_tambores_medibles_es_un_lazo_de_pista_con_el_espesor_de_su_volumen():
    banda = _banda()
    perim = 2 * (2104 - 104) + math.pi * 104
    ruta = ruta_faja(banda, [], volumen_mm3=3.0 * 500 * perim)
    assert ruta.envueltos == [] and ruta.espesor == pytest.approx(3.0, rel=0.01)
    assert max(w for _, w in ruta.puntos) == pytest.approx(52 - 1.5, abs=0.1)


# ------------------------------------------------------------------ del documento
@pytest.fixture(scope="module")
def faja():
    doc = Document("faja-visual")
    doc.execute("create_belt_conveyor", {"largo": 3000, "ancho_banda": 500, "altura": 800})
    return doc


def _banda_fisica(doc):
    """Lo que daría la física (`BandaDatos`) para la faja del super-comando."""
    bb = doc.scene["c1_banda"].shape.bounding_box()
    return {"pieza": "c1_banda", "junta": "c1_eje_motriz", "d": (1.0, 0, 0), "n": (0, 0, 1.0),
            "a": (0, -1.0, 0), "e": (1.0, 0, 0), "centro_mm": [0.0, 0.0, bb.max.Z - 2.0],
            "radio_m": 0.055, "masa_kg": 9.0}


def test_extrae_la_banda_y_sus_tambores_redondos(faja):
    vis = extraer_marcha_visual(faja, [_banda_fisica(faja)])
    (f,) = vis["fajas"]
    por = {p["pieza"]: p for p in f["piezas"]}
    assert por["c1_tambor_motriz"]["redonda"] and por["c1_tambor_cola"]["redonda"]
    assert not por["c1_cama"]["redonda"]
    assert "c1_guarda1" not in por            # corre al costado: no cruza la banda
    assert f["banda"]["v1"] - f["banda"]["v0"] == pytest.approx(500, abs=0.5)
    assert vis["cadenas"] == []


def test_armar_la_faja_con_la_traccion_medida(faja):
    vis = extraer_marcha_visual(faja, [_banda_fisica(faja)])
    res = {"cuerpos": [{"name": "b", "junta": "c1_eje_motriz", "tipo": "continua", "eje": [0, -1, 0],
                        "piezas": ["c1_tambor_motriz"]}],
           "juntas": {"c1_eje_motriz": {"par": [9.0, 3.0, 2.2, 2.2, 2.2]}}}
    out = armar(vis, res)
    (f,) = out["fajas"]
    assert sorted(f["envueltos"]) == ["c1_tambor_cola", "c1_tambor_motriz"]
    assert f["espesor"] == pytest.approx(4.0, abs=0.05)                 # el default del comando
    assert f["signo"] == -1                                            # la cara de arriba va a +u
    assert f["tension"]["traccion_n"] == pytest.approx(2.2 / 0.055, rel=0.01)
    assert f["tension"]["t2_min_n"] > 0
    (rod,) = f["rodillos"]                                             # el motriz ya gira por la física
    assert rod["pieza"] == "c1_tambor_cola"
    # adentro del lazo: gira antihorario en (u, w) = sobre u × w = X × Z = −Y
    assert rod["eje"] == pytest.approx([0, -1, 0])
    assert out["avisos"] == []
    largo = f["largo_mm"]
    assert largo > 2 * 3000


def _pinones_con_cadena(doc):
    a = doc.execute("insert_component", {"component": "PINON-ASA40-1-Z15"})
    b = doc.execute("insert_component", {"component": "PINON-ASA40-1-Z30", "position": {"x": 400}})
    cid = doc.execute("create_chain", {"pinon_a": a, "pinon_b": b})
    return a, b, cid


def test_la_cadena_sale_de_su_mesh_key_con_los_rodillos_de_su_geometria():
    doc = Document("cadena-visual")
    a, b, cid = _pinones_con_cadena(doc)
    cadenas = extraer_marcha_visual(doc, [])["cadenas"]
    assert len(cadenas) == 1, (
        "services/marcha_visual reconoce la cadena por su mesh_key «cadena|ref|detalle|za|zb|centros|"
        f"fase_a|fase_b|eslabones» (Transmision.clave); create_chain dio {doc.scene[cid].mesh_key!r}")
    (c,) = cadenas
    assert (c["pieza"], c["pinon_a"], c["pinon_b"], c["za"], c["zb"]) == (cid, a, b, 15, 30)
    assert c["eslabones"] * c["paso"] == pytest.approx(doc.scene[cid].cut_length)
    cuerpos = {a: ("jA", list(doc.scene[a].anchors["eje"]["axis"]), "continua")}
    v = cadena_visual(c, cuerpos)
    assert (v["junta"], v["lado"], v["z"], v["signo"]) == ("jA", "a", 15, 1)
    assert v["pinones_libres"] == [{"pieza": b, "lado": "b", "z": 30}]   # gira con la cadena
    m = v["marco"]
    pts = v["puntos"]
    mundo = [(m[0] * x + m[1] * y + m[3], m[4] * x + m[5] * y + m[7], m[8] * x + m[9] * y + m[11])
             for x, y in zip(pts[::2], pts[1::2])]
    eje_a = doc.scene[a].anchors["eje"]["origin"]
    radio = CATALOG["PINON-ASA40-1-Z15"].specs["paso"] / (2 * math.sin(math.pi / 15))
    i0, n = v["asentados_a"]
    for x, y, _z in mundo[i0:i0 + n]:   # los sentados en A, en su círculo primitivo
        assert math.hypot(x - eje_a[0], y - eje_a[1]) == pytest.approx(radio, abs=0.01)
    bb = doc.scene[cid].shape.bounding_box()
    for x, y, z in mundo:               # todos dentro de la cadena del CAD
        assert bb.min.X - 1 < x < bb.max.X + 1 and bb.min.Y - 1 < y < bb.max.Y + 1
        assert bb.min.Z - 1 < z < bb.max.Z + 1
    # con el eje al revés la cadena avanza al revés
    assert cadena_visual(c, {a: ("jA", [-x for x in cuerpos[a][1]], "continua")})["signo"] == -1


def test_una_cadena_sin_pinon_que_gire_queda_quieta_y_se_avisa():
    doc = Document("cadena-quieta")
    _pinones_con_cadena(doc)
    out = armar(extraer_marcha_visual(doc, []), {"cuerpos": []})
    assert out["cadenas"] == []
    assert out["avisos"] == ["1 cadena queda quieta: ninguno de sus piñones gira en la marcha "
                             "(dales una junta que gire)"]


def test_recorrido_integra_la_velocidad():
    assert recorrido_mm([0, 1, 2], [0.5, 0.5, 1.5]) == [0, 500, 1500]
