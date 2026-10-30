"""lo-fijo-que-gira F3 (D3a y D4a): la catenaria de una banda modular es un tensado reconocido, y la
cinta animada sigue la banda modelada aunque su sección no sea un lazo de una pieza.

- D3a (`library/catenaria_banda.py`, `library/calidad/catenaria.py`,
  `services/calidad_catenaria.py`): una banda de acetal sobre ruedas angostas de un eje cuadrado
  accionado, con una comba libre tras la motriz de 25,4–152 mm, se tensa con su peso (Intralox
  2024, p. 15). OK si cuelga libre hasta 152 mm; FALLA si algo lo impide (el defecto sembrado);
  SIN_EVALUAR a una temperatura de operación fuera de 10–30 °C (falta el α); fuera del rango o
  sin las ruedas, como antes (sin tensor reconocido).
- D4a (`services/seccion_plano.py`, `library/ruta_faja.py`): el corte de una banda hecha de
  tramos que se tocan en una esquina, o hueca por dentro (dos pieles), se cierra en un lazo; la
  cinta apoya en todo el largo de una zapata plana; una pieza redonda que ni tiene junta ni toca la
  banda no es su tambor.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import pytest

from apolo.library import catenaria_banda as cb
from apolo.library.calidad.item import FALLA, NO_APLICA, OK, SIN_EVALUAR
from apolo.library.calidad.tensor import controlar_tensores
from apolo.library.ruta_faja import PiezaPlano, _vano, clasificar
from apolo.library.ruta_faja_modelo import linea_media

T = 6.0         # espesor de la banda (mm)
R = 80.0        # radio de la línea media en las ruedas
ANCHO = 600.0
RD = 8.0        # radio del desvío (una varilla: la comba llega a él en pendiente)
L_TRAMO = 2000.0
X_DESVIO = 600.0


def _arco(cx, cz, r, a0, a1, n=48):
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / n), cz + r * math.sin(a0 + (a1 - a0) * i / n))
            for i in range(n + 1)]


def media_lazo(comba: float) -> list[tuple[float, float]]:
    """La línea media antihoraria (x, z): rueda motriz en (0, 0), conducida en (L_TRAMO, 0), y en el
    retorno, tras la motriz, una comba parabólica de `comba` mm hasta el desvío en X_DESVIO."""
    pts = [(x, R) for x in np.linspace(L_TRAMO, 0.0, 41)][:-1]                  # ida, hacia −x
    pts += _arco(0.0, 0.0, R, math.pi / 2, 3 * math.pi / 2)[:-1]              # abraza la motriz
    for s in np.linspace(0.0, 1.0, 31)[:-1]:                                   # la comba
        pts.append((X_DESVIO * s, -R - 4.0 * comba * s * (1.0 - s)))
    pts += [(x, -R) for x in np.linspace(X_DESVIO, L_TRAMO, 29)][:-1]          # retorno
    pts += _arco(L_TRAMO, 0.0, R, -math.pi / 2, math.pi / 2)[:-1]             # la conducida
    return pts


def _normales(p: np.ndarray) -> np.ndarray:
    t = np.roll(p, -1, axis=0) - np.roll(p, 1, axis=0)
    t /= np.hypot(*t.T)[:, None]
    return np.stack([t[:, 1], -t[:, 0]], axis=1)


def _solido_banda(media, pieles: bool = False):
    """La banda: la línea media ± T/2, extruida a lo ancho (Y). Con `pieles`, hueca por dentro:
    dos pieles de T/3 (como la banda modular de la lavadora, cerrada sólo en los cantos)."""
    from build123d import Face, Pos, Wire, extrude

    p = np.asarray(media, float)
    n = _normales(p)

    def wire(q):
        return Wire.make_polygon([(float(u), 0.0, float(w)) for u, w in q], close=True)

    def anillo(d0, d1):
        return Face(wire(p + n * d1), [wire(p + n * d0)])

    if not pieles:
        return Pos(0, -ANCHO / 2, 0) * extrude(anillo(-T / 2, T / 2), amount=ANCHO, dir=(0, 1, 0))
    caras = [anillo(-T / 2, -T / 6), anillo(T / 6, T / 2)]
    return [Pos(0, -ANCHO / 2, 0) * extrude(c, amount=ANCHO, dir=(0, 1, 0)) for c in caras]


def _pieza(i, nombre, shape, **kw):
    return SimpleNamespace(id=i, name=nombre, shape=shape, is_guide=False, component=None,
                           material=kw.get("material"), matrix=None, mesh_key=None)


def doc_modular(comba: float = 110.0, *, piso_z: float | None = None, eje: str = "cuadrado",
                temperatura: float | None = None, ruedas: tuple = (-200.0, 0.0, 200.0)):
    """Un documento falso: la banda de acetal, la motriz (eje + 3 ruedas angostas, junta continua),
    la conducida (una rueda en el plano medio), el rodillo de desvío y, si `piso_z`, una chapa
    bajo la comba."""
    from build123d import Box, Cylinder, Pos, Rotation

    media = media_lazo(comba)
    rueda = R - T / 2
    escena = {"banda": _pieza("banda", "Banda modular", _solido_banda(media), material="acetal (POM)")}
    eje_m = (Box(60, ANCHO + 200, 60) if eje == "cuadrado"
             else Rotation(90, 0, 0) * Cylinder(30, ANCHO + 200))
    escena["eje"] = _pieza("eje", "Eje motriz", eje_m)
    for k, y in enumerate(ruedas):
        escena[f"rueda{k}"] = _pieza(f"rueda{k}", "Rueda motriz",
                                     Pos(0, y, 0) * Rotation(90, 0, 0) * Cylinder(rueda, 40))
    for k, y in enumerate((-30.0, 30.0)):   # anillos de retención: angostos y coaxiales, no ruedas
        escena[f"anillo{k}"] = _pieza(f"anillo{k}", "Anillo de retención",
                                      Pos(0, y, 0) * Rotation(90, 0, 0) * Cylinder(45, 12))
    escena["conducida"] = _pieza("conducida", "Rueda conducida",
                                 Pos(L_TRAMO, 0, 0) * Rotation(90, 0, 0) * Cylinder(rueda, 40))
    escena["desvio"] = _pieza("desvio", "Rodillo de desvío",
                              Pos(X_DESVIO, 0, -R - T / 2 - RD) * Rotation(90, 0, 0) * Cylinder(RD, ANCHO + 40))
    escena["base"] = _pieza("base", "Base", Pos(-500, 0, -600) * Box(100, 100, 100))
    if piso_z is not None:
        escena["piso"] = _pieza("piso", "Bandeja de goteo", Pos(X_DESVIO / 2, 0, piso_z - 2) * Box(500, ANCHO + 40, 4))
    juntas = {"j_motriz": {"name": "j_motriz", "type": "continua", "parent": "base", "child": "eje",
                           "axis": [0.0, 1.0, 0.0], "origin": [0.0, 0.0, 0.0]}}
    for hija in [f"rueda{k}" for k in range(len(ruedas))] + ["anillo0", "anillo1"]:
        juntas[f"jf_{hija}"] = {"name": f"jf_{hija}", "type": "fija", "parent": "eje", "child": hija,
                                "axis": [0, 0, 1.0], "origin": [0, 0, 0]}
    req = {} if temperatura is None else {"temperatura_c": temperatura}
    return SimpleNamespace(scene=escena, joints=juntas, fasteners={}, grounds={}, commands=[],
                           variables_resolved={}, tensores=[], requirements=req, escenarios={},
                           default_material=lambda: None)


def _items(doc) -> dict:
    from apolo.services.calidad_tensores import lazos

    return {i.id: i for i in controlar_tensores(lazos(doc))}


# ------------------------------------------------------------------ D3a, puro
def test_la_zona_tras_la_motriz_es_la_comba_y_no_la_ida():
    media = np.asarray(media_lazo(110.0))
    # lo que la toca: la rueda conducida (la ida termina ahí) y la varilla de desvío
    caras = [{"ext": _arco(L_TRAMO, 0.0, R - T / 2, 0, 2 * math.pi, 72)[:-1], "huecos": []},
             {"ext": _arco(X_DESVIO, -R - T / 2 - RD, RD, 0, 2 * math.pi, 36)[:-1], "huecos": []}]
    apoyo = cb.apoyos(media, T, caras)
    z = cb.zona_tras_motriz(media, (0.0, 0.0), apoyo)
    assert z is not None and z["fin"] in ("desvio", "apoyo")
    assert 95 <= z["comba_mm"] <= 115 and z["vano_mm"] == pytest.approx(X_DESVIO, abs=40)
    assert z["desde"][0] == pytest.approx(0, abs=1) and z["bajo"][1] < -R - 100
    # lo que guarda crecer de 110 a 152 mm sobre 600 mm: 8·(152² − 110²)/(3·600)
    assert cb.absorbe_mm(110.0, 600.0) == pytest.approx(8 * (152 ** 2 - 110 ** 2) / 1800)
    # sin comba (un retorno recto) no hay zona colgante
    recto = cb.zona_tras_motriz(np.asarray(media_lazo(0.0)), (0.0, 0.0))
    assert recto is None or recto["comba_mm"] < cb.COMBA_MIN_MM


def test_la_parabola_del_tope_cuelga_hacia_afuera():
    p = cb.parabola((0.0, 0.0), (100.0, 0.0), 10.0)
    assert p[len(p) // 2][1] == pytest.approx(-10.0, abs=0.1)   # antihorario: afuera = abajo


# ------------------------------------------------------------------ D3a, con OCCT
def test_la_catenaria_de_una_banda_modular_es_un_tensor_reconocido():
    it = _items(doc_modular())
    assert it["tensor.reconocido"].estado == OK and it["tensor.carrera"].estado == OK
    assert it["tensor.agarre"].estado == NO_APLICA
    assert "catenaria" in str(it["tensor.reconocido"].evidencia) or it["tensor.reconocido"].detalle


def test_defecto_sembrado_lo_que_estorba_la_comba_del_tope_falla():
    """El defecto sembrado de D3a: una bandeja de goteo 20 mm bajo la comba modelada (no la toca,
    pero la comba de 152 mm sí): la banda se apoyaría antes de llegar a la comba en que se retiran
    filas."""
    it = _items(doc_modular(piso_z=-R - 110.0 - T / 2 - 20.0))
    assert it["tensor.carrera"].estado == FALLA
    assert "Bandeja de goteo" in str(it["tensor.carrera"].evidencia)


def test_en_caliente_falta_el_alfa_y_queda_sin_evaluar():
    it = _items(doc_modular(temperatura=65.0))
    assert it["tensor.reconocido"].estado == OK and it["tensor.carrera"].estado == SIN_EVALUAR
    (caso,) = it["tensor.carrera"].evidencia["casos"]
    assert "α" in caso["detalle"] and caso["temperatura_c"] == 65.0
    # el rodaje es el 1 % de la línea media (≈ 4,6 m), no del largo por área de la banda
    assert caso["rodaje_mm"] == pytest.approx(0.01 * (2 * L_TRAMO + 2 * math.pi * R + 60), rel=0.03)


@pytest.mark.parametrize("cambio", [{"comba": 200.0}, {"comba": 10.0}, {"eje": "redondo"},
                                    {"ruedas": (0.0,)}],
                         ids=["comba_de_mas", "comba_de_menos", "eje_redondo", "una_rueda_y_anillos"])
def test_fuera_del_rango_o_sin_ruedas_de_eje_cuadrado_sigue_como_antes(cambio):
    it = _items(doc_modular(**cambio))
    assert it["tensor.reconocido"].estado == SIN_EVALUAR


# ------------------------------------------------------------------ D4a
def test_la_seccion_de_dos_pieles_se_cierra_en_un_lazo():
    from build123d import Compound

    from apolo.kernel.shapes import place_matrix
    from apolo.services.seccion_plano import cortar, lazo_de_banda

    pieles = Compound(_solido_banda(media_lazo(110.0), pieles=True))
    # al marco de la faja (u = x, w = z, v = −y, diestro) y cortada en su plano medio v = 0
    inv = [[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]]
    caras = cortar(place_matrix(pieles, inv), 0.0)
    assert len(caras) == 2      # dos anillos concéntricos: antes se tomaba sólo la piel de afuera
    lazo = lazo_de_banda(caras)
    assert lazo is not None and len(lazo["huecos"]) == 1
    media, t = linea_media(lazo["ext"], lazo["huecos"])
    assert t == pytest.approx(T, abs=0.3)   # el espesor entero, no el de una piel


def test_la_seccion_de_tramos_que_se_tocan_en_una_esquina_se_cierra():
    """Un lazo hecho de dos tramos que sólo se tocan en las esquinas (como los tramos de la
    catenaria a mano): sin cerrar no hay hueco; cerrado, sí, con el espesor del tramo."""
    from apolo.services.seccion_plano import lazo_de_banda

    a = [(0, 0), (100, 0), (100, 3), (3, 3), (3, 100), (0, 100)]
    b = [(100, 3), (103, 3), (103, 103), (3, 103), (3, 100), (100, 100)]
    caras = [{"ext": a, "huecos": []}, {"ext": b, "huecos": []}]
    lazo = lazo_de_banda(caras)
    assert lazo is not None and len(lazo["huecos"]) == 1


def test_la_cinta_apoya_en_todo_el_largo_de_una_zapata_plana():
    """El retorno sobre una zapata de 40 mm: la comba nace en sus dos bordes, no en el primero."""
    zapata = [(x, -T / 2 - 0.0) for x in np.linspace(480, 520, 9)] + [(480, -20), (520, -20)]
    interior, vanos, _u = _vano((0.0, 0.0), (1000.0, 0.0), T, ["z"], None, None, [zapata])
    sobre = [p for p in interior if 480 <= p[0] <= 520]
    assert sobre and all(abs(p[1]) < 0.5 for p in sobre)
    assert [v["largo_mm"] for v in vanos] == pytest.approx([480, 40, 480], abs=1)


def test_lo_redondo_sin_junta_que_no_toca_la_banda_no_es_tambor():
    banda = PiezaPlano("banda", -1000, 1000, -200, 0, -300, 300)
    barra = dict(pieza="barra", u0=500, u1=521, w0=-80, w1=-59, v0=-300, v1=300, redonda=True)
    dentro, _fuera = clasificar(banda, [PiezaPlano(**barra)])
    assert [p.pieza for p in dentro] == ["barra"]                     # lo de antes
    dentro, fuera = clasificar(banda, [PiezaPlano(**barra, tambor=False)])
    assert dentro == [] and [p.pieza for p in fuera] == ["barra"]
