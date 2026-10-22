"""fabrica-de-publicaciones, ajuste D13 — la cinta que anima el visor sale del MODELO y se prueba
contra él.

- `library/ruta_faja_modelo.py`: la línea media de la sección del sólido de la banda (D13a).
- `library/fidelidad_faja.py`: desvío respecto del modelo y cruces con otras piezas (D13b).
- `services/marcha_visual.py` + `seccion_plano.py`: la sección y los cortes con OCCT.
- `services/marcha_ejemplo.fidelidad`: lo que corre la fábrica (`MarchaInfiel`, D13c).
- D13d: la cadena animada son los rodillos de su propia geometría (exacta por construcción).

El caso testigo es un drive central en Ω (como el proyecto 4): la banda baja a abrazar el motriz
por debajo de dos desvíos; el casco convexo la cortaba en recta a través de las guardas.
"""

from __future__ import annotations

import copy
import math
from types import SimpleNamespace

import numpy as np
import pytest

from apolo.library.fidelidad_faja import verificar_faja
from apolo.library.marcha_visual import armar
from apolo.library.ruta_faja import PiezaPlano, ruta_faja
from apolo.library.ruta_faja_modelo import distancia_polilinea, linea_media, ruta_modelo
from apolo.services import marcha_ejemplo as me
from apolo.services.marcha_visual import extraer_marcha_visual

T = 3.0       # espesor de la banda (mm)
ANCHO = 500.0
#: (nombre, u, w, r, lado): +1 la banda la abraza por dentro del lazo, −1 por fuera (desvío)
OMEGA = [("H", 1000.0, 0.0, 50.0, 1), ("T", -1000.0, 0.0, 50.0, 1), ("S1", -200.0, -93.0, 40.0, -1),
         ("D", 0.0, -300.0, 80.0, 1), ("S2", 200.0, -93.0, 40.0, -1)]
#: guardas bajo el retorno, lejos de la banda real y atravesadas por la recta del casco
GUARDAS = {"guarda1": (-650.0, -450.0, -240.0, -160.0), "guarda2": (450.0, 650.0, -240.0, -160.0)}


def lazo(circulos, delta: float, paso_deg: float = 2.0) -> list[tuple[float, float]]:
    """La banda ideal en (u, w), antihoraria, desplazada `delta` de su línea media (+t/2 la cara de
    afuera, −t/2 la de adentro): tramos tangentes entre círculos de radio r + t/2, con signo."""
    n = len(circulos)
    tang = []
    for i in range(n):
        (_a, ui, wi, ri, si), (_b, uj, wj, rj, sj) = circulos[i], circulos[(i + 1) % n]
        Ri, Rj = ri + T / 2, rj + T / 2
        du, dw = uj - ui, wj - wi
        psi = math.atan2(dw, du) + math.acos((sj * Rj - si * Ri) / math.hypot(du, dw))
        nx, nw = math.cos(psi), math.sin(psi)
        # ángulo (desde el centro) del punto de salida en i y del de llegada en j
        tang.append((math.atan2(-si * nw, -si * nx), math.atan2(-sj * nw, -sj * nx)))
    pts = []
    for j in range(n):
        _nm, u, w, r, s = circulos[j]
        a_in, a_out = tang[j - 1][1], tang[j][0]
        barrido = (a_out - a_in) % (2 * math.pi) if s > 0 else -((a_in - a_out) % (2 * math.pi))
        k = max(2, int(abs(math.degrees(barrido)) / paso_deg) + 1)
        R = r + T / 2 + s * delta
        pts += [(u + R * math.cos(a_in + barrido * i / k), w + R * math.sin(a_in + barrido * i / k))
                for i in range(k + 1)]
    return pts


def _circulo(u, w, r, n=72):
    return [(u + r * math.cos(2 * math.pi * i / n), w + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _omega_plano():
    ext, inn = lazo(OMEGA, T / 2), lazo(OMEGA, -T / 2)
    us, ws = [p[0] for p in ext], [p[1] for p in ext]
    banda = PiezaPlano("banda", min(us), max(us), min(ws), max(ws), -ANCHO / 2, ANCHO / 2)
    piezas = [PiezaPlano(nm, u - r, u + r, w - r, w + r, -275, 275, redonda=True) for nm, u, w, r, _s in OMEGA]
    piezas += [PiezaPlano(nm, *caja, -270, 270) for nm, caja in GUARDAS.items()]
    regiones = {nm: [{"ext": _circulo(u, w, r), "huecos": []}] for nm, u, w, r, _s in OMEGA}
    regiones.update({nm: [{"ext": [(a, c), (b, c), (b, d), (a, d)], "huecos": []}]
                     for nm, (a, b, c, d) in GUARDAS.items()})
    seccion = {"ext": ext, "huecos": [inn]}
    cortes = [{"v": 0.0, "banda": [seccion], "piezas": regiones}]
    return banda, piezas, seccion, cortes


# ------------------------------------------------------------------ D13a + D13b, puro
def test_la_linea_media_es_la_de_la_banda_y_su_espesor():
    _b, _p, seccion, _c = _omega_plano()
    media, t = linea_media(seccion["ext"], seccion["huecos"])
    assert t == pytest.approx(T, abs=0.01)
    d, _k, _q = distancia_polilinea(media, np.asarray(lazo(OMEGA, 0.0)))
    assert d.max() < 0.05


def test_omega_el_casco_corta_las_guardas_y_la_seccion_es_fiel():
    banda, piezas, seccion, cortes = _omega_plano()
    vieja = ruta_faja(banda, piezas)                     # la regla vieja: casco convexo
    malo = verificar_faja(vieja, cortes=cortes, nombres={"guarda1": "Guarda (1)"})
    assert not malo["ok"] and {c["pieza"] for c in malo["cruces"]} == {"guarda1", "guarda2"}
    assert malo["cruces"][0]["exceso_mm"] > 30 and malo["cruces"][0]["modelo_mm"] == 0
    assert "atraviesa «Guarda (1)»" in malo["motivo"] or "atraviesa «guarda2»" in malo["motivo"]
    nueva = ruta_modelo(banda, piezas, seccion, obstaculos=None)
    assert nueva.origen == "seccion" and nueva.espesor == pytest.approx(T, abs=0.01)
    bien = verificar_faja(nueva, cortes=cortes)
    assert bien["ok"] and bien["cruces"] == [] and bien["motivo"] is None
    # la casco, medida contra el contorno del modelo, se aparta el Ω entero
    vieja.modelo, vieja.combables = nueva.modelo, nueva.combables
    assert verificar_faja(vieja)["desvio"]["exceso_mm"] > 100
    # abraza cola, cabeza y motriz por dentro; los desvíos, por fuera (giran al revés)
    assert sorted(e["pieza"] for e in nueva.envueltos) == ["D", "H", "T"]
    assert sorted(e["pieza"] for e in nueva.apoyos_fuera) == ["S1", "S2"]
    por = {e["pieza"]: e["abrazamiento_deg"] for e in nueva.envueltos + nueva.apoyos_fuera}
    assert por["T"] == pytest.approx(180, abs=2) and por["D"] == pytest.approx(142.6, abs=2)
    assert por["S1"] == pytest.approx(71.3, abs=2)
    # cuelga sólo en los dos tramos rectos del retorno (cola → desvío, desvío → cabeza)
    assert [t["limita"] for t in nueva.tramos] == ["cema", "cema"]
    assert [t["largo_mm"] for t in nueva.tramos] == pytest.approx([800, 800], abs=5)


def test_una_comba_mas_honda_que_cema_o_hacia_adentro_no_es_fiel():
    banda, piezas, seccion, cortes = _omega_plano()
    ruta = ruta_modelo(banda, piezas, seccion)
    assert verificar_faja(ruta, cortes=cortes)["desvio"]["desvio_mm"] == pytest.approx(16, abs=0.5)
    i = max(range(len(ruta.puntos)), key=lambda k: -ruta.puntos[k][1] if -700 < ruta.puntos[k][0] < -300 else -1e9)
    u, w = ruta.puntos[i]
    ruta.puntos[i] = (u, w - 30)                         # 46 mm de comba en un vano de 800
    dv = verificar_faja(ruta, cortes=cortes)
    assert not dv["ok"] and "se aparta" in dv["motivo"]
    ruta.puntos[i] = (u, w + 40)                         # hacia ADENTRO del lazo: nunca
    assert not verificar_faja(ruta)["ok"]


def test_sin_lazo_cerrado_la_seccion_cae_al_casco():
    banda, piezas, _s, _c = _omega_plano()
    assert ruta_modelo(banda, piezas, None) is None
    assert ruta_modelo(banda, piezas, {"ext": [(0, 0), (10, 0), (10, 3), (0, 3)], "huecos": []}) is None


# ------------------------------------------------------------------ con OCCT (services)
def _solido_banda():
    from build123d import Face, Pos, Wire, extrude

    def wire(pts):
        return Wire.make_polygon([(u, 0, w) for u, w in pts], close=True)

    cara = Face(wire(lazo(OMEGA, T / 2)), [wire(lazo(OMEGA, -T / 2))])
    return Pos(0, -ANCHO / 2, 0) * extrude(cara, amount=ANCHO, dir=(0, 1, 0))


@pytest.fixture(scope="module")
def omega():
    """Un documento falso con la faja en Ω: banda (eje de tambores = Y), tambores y guardas."""
    from build123d import Box, Cylinder, Pos, Rotation

    piezas = {"banda": ("Banda", _solido_banda())}
    for nm, u, w, r, _s in OMEGA:
        piezas[nm] = (f"Tambor {nm}", Pos(u, 0, w) * Rotation(90, 0, 0) * Cylinder(r, 560))
    for i, (nm, (a, b, c, d)) in enumerate(GUARDAS.items(), 1):
        piezas[nm] = (f"Guarda ({i})", Pos((a + b) / 2, 0, (c + d) / 2) * Box(b - a, 540, d - c))
    escena = {k: SimpleNamespace(id=k, name=n, shape=s, is_guide=False, mesh_key=None, matrix=None)
              for k, (n, s) in piezas.items()}
    return SimpleNamespace(scene=escena, fasteners={})


BANDA = {"pieza": "banda", "junta": "j", "d": (1.0, 0, 0), "n": (0, 0, 1.0), "a": (0, -1.0, 0),
         "e": (1.0, 0, 0), "centro_mm": [0.0, 0.0, 0.0], "radio_m": 0.0815, "masa_kg": 5.0}
RES = {"cuerpos": [{"junta": "j", "tipo": "continua", "eje": [0, -1, 0], "piezas": ["D"]}],
       "juntas": {"j": {"par": [6.0, 6.0, 6.0]}}}


@pytest.fixture(scope="module")
def vis_omega(omega):
    return extraer_marcha_visual(omega, [BANDA])


def test_omega_del_documento_sale_de_la_seccion_y_es_fiel(vis_omega):
    vis = copy.deepcopy(vis_omega)
    (f,) = vis["fajas"]
    assert f["seccion"] is not None and len(f["seccion"]["huecos"]) == 1
    assert {"guarda1", "guarda2", "D"} <= set(f["cortes"][0]["piezas"])
    out = armar(vis, RES)
    (x,) = out["fajas"]
    assert x["modelo"] == "seccion" and x["fidelidad"]["ok"], x["fidelidad"]
    assert x["espesor"] == pytest.approx(T, abs=0.05) and out["avisos"] == []
    assert sorted(x["envueltos"]) == ["D", "H", "T"] and sorted(x["apoyos"]) == ["S1", "S2"]
    # los desvíos giran con la banda, al revés que los tambores de adentro
    ejes = {r["pieza"]: r["eje"] for r in x["rodillos"]}
    assert ejes["S1"] == pytest.approx([-c for c in ejes["T"]])
    ruta = np.asarray(x["ruta"]).reshape(-1, 2)
    d, _k, _q = distancia_polilinea(ruta, np.asarray(lazo(OMEGA, 0.0)))
    assert d.max() <= 0.02 * 800 + 1                       # sólo la comba se aparta


def test_omega_con_la_regla_vieja_atraviesa_la_guarda_y_lo_dice(vis_omega):
    vis = copy.deepcopy(vis_omega)
    vis["fajas"][0]["seccion"] = None                      # sin lazo: el casco de siempre
    out = armar(vis, RES)
    fid = out["fajas"][0]["fidelidad"]
    assert out["fajas"][0]["modelo"] == "casco" and not fid["ok"]
    assert {c["nombre"] for c in fid["cruces"]} == {"Guarda (1)", "Guarda (2)"}
    assert any("NO es fiel al modelo" in a and "Guarda" in a for a in out["avisos"])


def test_la_fabrica_no_acepta_la_cinta_que_atraviesa(omega, monkeypatch):
    monkeypatch.setattr("apolo.services.seccion_plano.lazo_de_banda", lambda cortes: None)
    with pytest.raises(me.MarchaInfiel, match="«banda».*atraviesa «Guarda \\(\\d\\)».*mm"):
        me.fidelidad(omega, [BANDA], RES)


# ------------------------------------------------------------------ la faja de cabeza y cola
@pytest.fixture(scope="module")
def faja():
    from apolo.doc.document import Document

    doc = Document("faja-d13")
    doc.execute("create_belt_conveyor", {"largo": 3000, "ancho_banda": 500, "altura": 800})
    return doc


def test_la_faja_del_super_comando_sigue_igual_y_su_banda_es_un_lazo(faja):
    bb = faja.scene["c1_banda"].shape.bounding_box()
    # create_belt_conveyor v3: los tramos rectos van en su sitio (antes Polygon los centraba en
    # el origen y quedaban a la altura del piso, sueltos de los tubos: no había lazo)
    assert bb.min.Z > 600
    banda = {**BANDA, "pieza": "c1_banda", "junta": "c1_eje_motriz", "centro_mm": [0.0, 0.0, bb.max.Z - 2.0]}
    (f,) = extraer_marcha_visual(faja, [banda])["fajas"]
    assert f["seccion"] is not None
    bp, piezas = PiezaPlano(**f["banda"]), [PiezaPlano(**p) for p in f["piezas"]]
    vieja = ruta_faja(bp, piezas, volumen_mm3=f["volumen_mm3"])
    nueva = ruta_modelo(bp, piezas, f["seccion"])
    d, _k, _q = distancia_polilinea(np.asarray(vieja.puntos), np.asarray(nueva.puntos))
    assert d.max() < 0.5 and nueva.largo_mm == pytest.approx(vieja.largo_mm, abs=1)
    assert [e["pieza"] for e in nueva.envueltos] == ["c1_tambor_cola", "c1_tambor_motriz"]
    assert [e["abrazamiento_deg"] for e in nueva.envueltos] == pytest.approx(
        [e["abrazamiento_deg"] for e in reversed(vieja.envueltos)], abs=0.5)
    assert verificar_faja(nueva, cortes=f["cortes"])["ok"]


# ------------------------------------------------------------------ D13d: la cadena
def test_la_cadena_animada_es_la_de_su_solido():
    """Exacta por construcción: el visor anima `rodillos_del_lazo` con los MISMOS números con que
    `create_chain` hizo el sólido (su `mesh_key`) y en su `Feature.matrix`; cada rodillo animado
    cae dentro del sólido de la cadena."""
    from build123d import Vector

    from apolo.doc.document import Document
    from apolo.library.marcha_visual import cadena_visual

    doc = Document("cadena-d13")
    a = doc.execute("insert_component", {"component": "PINON-ASA40-1-Z15"})
    b = doc.execute("insert_component", {"component": "PINON-ASA40-1-Z30", "position": {"x": 400}})
    cid = doc.execute("create_chain", {"pinon_a": a, "pinon_b": b})
    (c,) = extraer_marcha_visual(doc, [])["cadenas"]
    v = cadena_visual(c, {a: ("jA", list(doc.scene[a].anchors["eje"]["axis"]), "continua")})
    m, pts = v["marco"], v["puntos"]
    solido = doc.scene[cid].shape
    rodillos = list(zip(pts[::2], pts[1::2]))
    assert len(rodillos) == c["eslabones"]
    i0, n = v["asentados_a"]
    muestra = sorted({*range(0, len(rodillos), 7), i0, i0 + n - 1})   # tramos rectos y piñón A
    fuera = [k for k in muestra
             if not solido.is_inside(Vector(m[0] * rodillos[k][0] + m[1] * rodillos[k][1] + m[3],
                                            m[4] * rodillos[k][0] + m[5] * rodillos[k][1] + m[7],
                                            m[8] * rodillos[k][0] + m[9] * rodillos[k][1] + m[11]))]
    assert len(muestra) >= 8 and fuera == []
