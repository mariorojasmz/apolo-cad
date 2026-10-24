"""Los símbolos ISO 1219-1 del esquema neumático (plan V8.9 F5, D11): un caso por símbolo con su
CAJA (todo lo dibujado cae dentro) y sus PUERTOS (los que pide su ficha, cada uno en el extremo
libre de un tramo, sin nada del símbolo más allá en su dirección: una línea se conecta sin cruzar
el símbolo). Los mandos, cada uno en su ancho y a los dos costados."""

from __future__ import annotations

import pytest

from apolo.drawing.esquema import ESTILOS, LLENO, PILOTAJE
from apolo.drawing.neumatica import equipos as E
from apolo.drawing.neumatica import mandos as M
from apolo.drawing.neumatica import valvulas as V
from apolo.drawing.neumatica.trazo import ABAJO, ARRIBA, Lapiz
from apolo.drawing.sheet import SheetModel

TOL = 1e-6


def _puntos(m: SheetModel) -> list[tuple[float, float]]:
    pts = []
    for ln in m.lines:
        pts += [(ln.x1, ln.y1), (ln.x2, ln.y2)]
    for c in m.circles:
        pts += [(c.x - c.r, c.y - c.r), (c.x + c.r, c.y + c.r)]
    for p in m.polygons:
        pts += list(p.rings[0])
    return pts


def _verificar(m: SheetModel, s, puertos: set[str]) -> None:
    assert m.lines or m.polygons or m.circles
    assert all(x.kind in ESTILOS for x in (*m.lines, *m.circles, *m.polygons)), "sólo trazos de esquema"
    x0, y0, x1, y1 = s.caja
    assert x1 > x0 and y1 > y0
    for x, y in _puntos(m):
        assert x0 - TOL <= x <= x1 + TOL and y0 - TOL <= y <= y1 + TOL, (x, y, s.caja)
    assert set(s.puertos) == puertos
    for via, p in s.puertos.items():
        assert p.dir in (ARRIBA, ABAJO)
        assert x0 - TOL <= p.x <= x1 + TOL and y0 - TOL <= p.y <= y1 + TOL
        # extremo libre de un tramo vertical que sale en su dirección
        tramos = [ln for ln in m.lines if ln.kind != PILOTAJE and abs(ln.x1 - ln.x2) < TOL
                  and abs(ln.x1 - p.x) < TOL and abs(min(ln.y1, ln.y2) if p.dir == ABAJO else
                                                       max(ln.y1, ln.y2)) - p.y < TOL]
        assert tramos, f"la vía {via} no es el extremo de un tramo"
        # nada del símbolo más allá del puerto en su dirección (en su corredor)
        for x, y in _puntos(m):
            if abs(x - p.x) < 0.3:
                assert (y <= p.y + TOL) if p.dir == ARRIBA else (y >= p.y - TOL), (via, x, y)


VALVULAS = {
    "5/2 monoestable": ({"vias": 5, "posiciones": 2, "mando": "monoestable", "accionamiento": "electrico",
                         "bobinas": ["14"], "manual": True}, {"bobina:14"}),
    "5/2 biestable": ({"vias": 5, "posiciones": 2, "mando": "biestable", "accionamiento": "electrico",
                       "bobinas": ["14", "12"], "manual": True}, {"bobina:14", "bobina:12"}),
    "5/3 centro cerrado": ({"vias": 5, "posiciones": 3, "mando": "centro_cerrado",
                            "accionamiento": "electrico", "bobinas": ["14", "12"]}, {"bobina:14", "bobina:12"}),
    "5/3 centro a escape": ({"vias": 5, "posiciones": 3, "mando": "centro_escape",
                             "accionamiento": "electrico", "bobinas": ["14", "12"]}, {"bobina:14", "bobina:12"}),
    "5/3 centro a presión": ({"vias": 5, "posiciones": 3, "mando": "centro_presion",
                              "accionamiento": "electrico", "bobinas": ["14", "12"]}, {"bobina:14", "bobina:12"}),
    "3/2 NC": ({"vias": 3, "posiciones": 2, "mando": "monoestable", "reposo": "NC",
                "accionamiento": "electrico", "bobinas": ["12"], "manual": True}, {"bobina:12"}),
    "3/2 NA": ({"vias": 3, "posiciones": 2, "mando": "monoestable", "reposo": "NA",
                "accionamiento": "electrico", "bobinas": ["12"]}, {"bobina:12"}),
    "5/2 pilotada": ({"vias": 5, "posiciones": 2, "mando": "monoestable", "accionamiento": "neumatico"}, set()),
    "3/2 manual": ({"vias": 3, "posiciones": 2, "mando": "monoestable", "accionamiento": "manual"}, set()),
    "2/2 NC": ({"vias": 2, "posiciones": 2, "mando": "monoestable", "accionamiento": "electrico",
                "bobinas": ["12"]}, {"bobina:12"}),
}
PUERTOS = {5: {"1", "2", "3", "4", "5"}, 3: {"1", "2", "3"}, 2: {"1", "2"}}


@pytest.mark.parametrize("nombre", sorted(VALVULAS))
def test_valvula(nombre):
    modelo, bobinas = VALVULAS[nombre]
    m = SheetModel(420, 297)
    s = V.valvula_de_ficha(m, 200.0, 150.0, modelo, stub_1=10.0)
    _verificar(m, s, PUERTOS[modelo["vias"]])
    assert {k for k in s.marcas if k.startswith("bobina:")} == bobinas
    # se conecta a la caja de REPOSO: sus vías caen dentro de la caja centrada en x = 200
    assert all(200.0 - V.S / 2 < p.x < 200.0 + V.S / 2 for p in s.puertos.values())
    # la vía 1 baja hasta debajo de los escapes (deja colgar los silenciadores)
    abajo = {v: p.y for v, p in s.puertos.items() if p.dir == ABAJO}
    assert abajo["1"] == min(abajo.values()) == 150.0 - 10.0
    # cada vía de paso lleva su punta llena
    assert any(p.kind == LLENO for p in m.polygons)


def test_una_53_sin_centro_y_una_valvula_sin_simbolo():
    with pytest.raises(ValueError, match="su centro"):
        V.valvula(SheetModel(420, 297), 0, 0, vias=5, posiciones=3, mando="biestable")
    with pytest.raises(ValueError, match="sin símbolo"):
        V.valvula(SheetModel(420, 297), 0, 0, vias=4, posiciones=2)


def test_las_vias_de_una_52_en_reposo_e_iso_5599_3():
    """En reposo (caja derecha) 1→2 y 4→5; con el mando 14 (izquierda) 1→4 y 2→3."""
    assert V.cajas(5, 2) == [V.CAJAS_5["14"], V.CAJAS_5["12"]]
    assert ("f", "1", "2") in V.CAJAS_5["12"] and ("f", "4", "5") in V.CAJAS_5["12"]
    assert ("f", "1", "4") in V.CAJAS_5["14"] and ("f", "2", "3") in V.CAJAS_5["14"]
    assert all(c[0] == "t" for c in V.CAJAS_5["centro_cerrado"])
    assert V.cajas(3, 2, reposo="NC")[1] == V.CAJAS_3["escape"]  # NC: en reposo 2 a escape


@pytest.mark.parametrize("con_escape, puertos", [(True, {"1", "2", "3"}), (False, {"1", "2"})])
def test_valvula_de_corte(con_escape, puertos):
    m = SheetModel(420, 297)
    s = V.corte_con_escape(m, 60.0, 100.0, con_escape=con_escape)
    _verificar(m, s, puertos)
    assert s.tipo == "valvula_corte"


@pytest.mark.parametrize("efecto, amort, iman, puertos", [
    ("doble", "neumatica", True, {"A", "B"}),
    ("doble", "elastica", False, {"A", "B"}),
    ("simple_muelle", "sin", False, {"A"}),
])
def test_cilindro(efecto, amort, iman, puertos):
    m = SheetModel(420, 297)
    s = E.cilindro(m, 100.0, 200.0, efecto=efecto, amortiguacion=amort, iman=iman)
    _verificar(m, s, puertos)
    assert s.puertos["A"].x < s.marcas["atras"][0] < s.marcas["adelante"][0]
    assert any(p.kind == LLENO for p in m.polygons) == (iman or amort == "neumatica")


@pytest.mark.parametrize("invertido", [False, True])
def test_regulador_de_caudal(invertido):
    m = SheetModel(420, 297)
    s = E.regulador_caudal(m, 100.0, 160.0 + (20.0 if invertido else 0.0), invertido=invertido)
    _verificar(m, s, {"1", "2"})
    p1, p2 = s.puertos["1"], s.puertos["2"]
    assert (p1.y < p2.y) != invertido and abs(p1.y - p2.y) == 20.0
    assert any(ln.kind == PILOTAJE for ln in m.lines)  # la envolvente
    assert len(m.circles) == 1  # la bola de la antirretorno


@pytest.mark.parametrize("fn, puertos", [
    (E.silenciador, {"1"}), (E.escape, {"1"}), (E.fuente, {"2"}),
])
def test_accesorios(fn, puertos):
    m = SheetModel(420, 297)
    s = fn(m, 100.0, 100.0)
    _verificar(m, s, puertos)


@pytest.mark.parametrize("lub", [False, True])
def test_frl(lub):
    m = SheetModel(420, 297)
    s = E.frl(m, 50.0, 60.0, lubricador_=lub)
    _verificar(m, s, {"1", "2"})
    assert s.puertos["1"].dir == ABAJO and s.puertos["2"].dir == ARRIBA
    rombos = 2 if lub else 1
    # 4 + filtro 8 + 2 + regulador 9 + 6 (+ lubricador 8 + 2) + 4
    assert s.caja[3] - s.caja[1] == pytest.approx(33.0 + 10.0 * (rombos - 1))


@pytest.mark.parametrize("parte, alto", [(E.filtro, 8.0), (E.regulador_presion, 9.0), (E.lubricador, 8.0)])
def test_partes_del_frl(parte, alto):
    m = SheetModel(420, 297)
    lz = Lapiz(m, 50.0, 60.0)
    assert parte(lz, 0.0) == alto
    x0, y0, x1, y1 = lz.caja()
    assert y0 == 60.0 and y1 >= 60.0 + alto and x0 < 50.0 < x1


def test_manometro():
    m = SheetModel(420, 297)
    lz = Lapiz(m, 50.0, 60.0)
    E.manometro(lz, 0.0, 0.0)
    assert len(m.circles) == 1 and lz.caja()[0] == 50.0


def test_presostato_y_detector():
    m = SheetModel(420, 297)
    s = E.presostato(m, 100.0, 100.0)
    _verificar(m, s, {"1"})
    assert any(ln.kind == PILOTAJE for ln in m.lines)
    m2 = SheetModel(420, 297)
    d = E.detector(m2, 100.0, 100.0)
    _verificar(m2, d, set())
    assert d.marcas["arriba"][1] > d.caja[3] - TOL


@pytest.mark.parametrize("mando", M.MANDOS)
@pytest.mark.parametrize("lado", [-1, 1])
def test_mandos(mando, lado):
    m = SheetModel(420, 297)
    lz = Lapiz(m, 0.0, 0.0)
    marcas = M.dibujar(lz, [mando], 100.0, lado, 50.0, V.H)
    x0, y0, x1, y1 = lz.caja()
    ancho = M.ANCHOS[mando]
    lo, hi = (100.0 - ancho, 100.0) if lado < 0 else (100.0, 100.0 + ancho)
    assert lo - TOL <= x0 and x1 <= hi + TOL, (x0, x1)
    assert 50.0 - TOL <= y0 and y1 <= 50.0 + V.H + TOL
    assert ("bobina" in marcas) == (mando == "bobina")
    with pytest.raises(ValueError, match="mando desconocido"):
        M.dibujar(lz, ["pedal"], 100.0, lado, 50.0, V.H)
