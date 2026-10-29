"""La puerta rápida (plan puerta-rapida, F1): lo que la prueba de sobrantes deja de recalcular
por candidata da EXACTAMENTE lo mismo que recalcularlo (D5: igualdad, no tolerancia).

- D1: la `BandaEmpujable` de la corrida con lo quitado enmascarado contra la rehecha sin ello;
- D2: el campo de la muñeca rehecho en las cajas S1/S2 contra el entero (con y sin piso sólido,
  sin voxeles cambiados, con un voxel que se cierra y con la caja de la máquina cambiada);
- D3: cada memo de la corrida con su caso (mismo resultado, `is` en la forma, nada fuera del
  `with`).
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import numpy as np
import pytest

from apolo.library.engineering import memo_corrida as MC
from apolo.library.seguridad.alcance import CampoAlcance
from apolo.services import calidad_sobrantes as CS
from apolo.services.calidad_codo import BandaEmpujable


# ------------------------------------------------------------------ D2: el campo por cajas
def _plano(x0, x1, z0, z1, y, paso=15.0, hueco=None):
    xs, zs = np.arange(x0, x1 + 1e-9, paso), np.arange(z0, z1 + 1e-9, paso)
    p = np.array([(x, y, z) for x in xs for z in zs])
    if hueco is not None:
        (hx0, hx1), (hz0, hz1) = hueco
        p = p[~((p[:, 0] > hx0) & (p[:, 0] < hx1) & (p[:, 2] > hz0) & (p[:, 2] < hz1))]
    return p


CAJA = ((0.0, 0.0, 0.0), (6000.0, 1200.0, 1200.0))
VENTANA = ((2800.0, 3200.0), (400.0, 800.0))


def _campos(piso_solido: bool):
    """Una pared larga con una ventana que tapa una placa: el campo con la placa, sin ella y el
    `libre` que rehace la prueba de sobrantes en su zona (`libre_sin`). Voxel de 40 mm: la caja S1
    queda menor que la grilla (el alcance son ~24 voxeles)."""
    pared = _plano(0, 6000, 0, 1200, 600.0, hueco=VENTANA)
    tapa = _plano(2780, 3220, 380, 820, 590.0)
    kw = {"paso": 40.0, "piso_solido": piso_solido}
    con = CampoAlcance(np.r_[pared, tapa], CAJA, 0.0, **kw)
    sin = CampoAlcance(pared, CAJA, 0.0, **kw)
    libre = con.libre_sin(pared, tapa.min(axis=0), tapa.max(axis=0))
    return con, sin, libre


@pytest.mark.parametrize("piso_solido", [False, True])
def test_el_campo_por_cajas_es_el_entero(piso_solido):
    con, sin, libre = _campos(piso_solido)
    s1 = con._caja_de(libre != con.libre, int(np.ceil(con.alcance / con.paso)) + 2)
    assert np.prod([s.stop - s.start for s in s1]) < np.prod(con.forma)  # de verdad local
    local = con.sin_zona(libre)
    assert local is not con
    assert np.array_equal(local.libre, sin.libre)
    assert np.array_equal(local._brazo, sin._brazo)
    assert np.array_equal(local._prof, sin._prof)
    assert (local._prof != con._prof).any()  # la ventana abierta cambia lo que se alcanza
    assert con.misma_grilla(CAJA, 0.0, piso_solido)


def test_sin_voxeles_cambiados_es_el_mismo_campo():
    con, _sin, _libre = _campos(False)
    assert con.sin_zona(con.libre.copy()) is con


def test_un_voxel_que_se_cierra_rehace_el_campo_entero():
    """Una banda que deja de empujarse (se quitó su guarda) CIERRA voxeles: el campo puede subir
    lejos y se rehace entero, igual al que sale de esos voxeles."""
    con, sin, _libre = _campos(False)
    cerrado = sin.sin_zona(con.libre)
    assert np.array_equal(cerrado._prof, con._prof)
    assert np.array_equal(cerrado._brazo, con._brazo)


def test_con_la_caja_cambiada_la_prueba_rehace_el_campo_entero():
    """Si quitar la pieza mueve la caja de la máquina, la grilla es otra: `_sin_zona` no sirve
    (None) y `Prueba._campo` cae al entero, como antes."""
    con, _sin, _libre = _campos(False)
    pr = object.__new__(CS.Prueba)
    pr.an = {"dc": {"piezas": {"t": SimpleNamespace(caja=((2780, 590, 380), (3220, 590, 820)))}}}
    otra = {"caja": ((0.0, 0.0, 0.0), (5000.0, 1200.0, 1200.0)), "z_piso": 0.0,
            "piezas": {}, "solidos": {}}
    assert pr._sin_zona(con, otra, None, {"t"}) is None


# ------------------------------------------------------------------ D1: la banda enmascarada
def _pieza(rol, nombre, categoria="estructura"):
    return SimpleNamespace(rol=rol, nombre=nombre, categoria=categoria)


def _escena_banda():
    """Una banda a lo largo de X; dos guardas sobre ella (la A más cerca y densa que la B, en el
    mismo tramo: quitada la A, el vecino es la B y la consulta tiene que buscar más allá de los
    primeros k); un tambor que la apoya en un extremo y un larguero lejos."""
    rng = np.random.default_rng(3)
    x = np.linspace(0, 400, 801)
    nubes = {
        "banda": np.c_[x, np.zeros_like(x), np.zeros_like(x)],
        "guarda_a": np.c_[rng.uniform(100, 300, 400), rng.uniform(-5, 5, 400), np.full(400, 6.0)],
        "guarda_b": np.c_[rng.uniform(50, 350, 200), rng.uniform(-5, 5, 200), np.full(200, 12.0)],
        "tambor": np.c_[rng.uniform(320, 400, 300), rng.uniform(-5, 5, 300),
                        rng.uniform(-14, -3, 300)],
        "larguero": np.c_[rng.uniform(0, 400, 300), np.full(300, 300.0), np.zeros(300)],
    }
    piezas = {"banda": _pieza("flexible", "Banda"), "guarda_a": _pieza("guarda", "Guarda A"),
              "guarda_b": _pieza("guarda", "Guarda B"), "tambor": _pieza("tambor", "Tambor"),
              "larguero": _pieza("estructura", "Larguero")}
    dc = {"piezas": piezas, "solidos": {i: [] for i in piezas}}
    q = np.r_[nubes["banda"], np.c_[rng.uniform(-20, 420, 3000), rng.uniform(-20, 20, 3000),
                                     rng.uniform(-20, 20, 3000)]]
    return dc, nubes, q


def _sin(dc, q):
    return {"piezas": {i: p for i, p in dc["piezas"].items() if i not in q},
            "solidos": {i: s for i, s in dc["solidos"].items() if i not in q}}


@pytest.mark.parametrize("q", [set(), {"guarda_a"}, {"guarda_b"}, {"guarda_a", "guarda_b"},
                               {"tambor"}, {"tambor", "larguero"}, {"larguero"},
                               {"guarda_a", "tambor"}, {"no_existe"}])
def test_la_banda_reusada_es_la_rehecha(q):
    dc, nubes, pts = _escena_banda()
    base = BandaEmpujable(dc, nubes)
    vista = base.sin(q)
    rehecha = BandaEmpujable(_sin(dc, q), nubes)
    assert vista is not None and vista._kd_guarda is base._kd_guarda
    assert np.array_equal(vista.empujable(pts), rehecha.empujable(pts))
    assert vista.bandas == rehecha.bandas
    for p in pts[::97]:
        assert vista.salta("banda", p) == rehecha.salta("banda", p)
    if not q & {"guarda_a", "guarda_b", "tambor", "larguero"}:
        assert vista is base  # nada de lo quitado tiene puntos en los árboles


def test_la_escena_de_la_banda_ejercita_la_mascara():
    """Quitar la guarda A cambia lo que se empuja (si no, la prueba de arriba no probaría nada)."""
    dc, nubes, pts = _escena_banda()
    base = BandaEmpujable(dc, nubes)
    assert not np.array_equal(base.empujable(pts), base.sin({"guarda_a", "guarda_b"}).empujable(pts))
    assert not np.array_equal(base.empujable(pts), base.sin({"tambor"}).empujable(pts))


def test_quitar_una_banda_pide_rehacerla():
    dc, nubes, _pts = _escena_banda()
    assert BandaEmpujable(dc, nubes).sin({"banda"}) is None


def test_la_prueba_reusa_la_banda_de_f3():
    dc, nubes, pts = _escena_banda()
    f3 = BandaEmpujable(dc, nubes)
    pr = object.__new__(CS.Prueba)
    pr.an, pr.compartido, pr.nubes, pr._empuje_f3 = {"dc": dc}, {"empuje": f3}, nubes, None
    v = pr.empuje({"guarda_a"}, _sin(dc, {"guarda_a"}))
    assert v._kd_guarda is f3._kd_guarda and v is not f3
    con_banda = pr.empuje({"banda"}, _sin(dc, {"banda"}))
    assert con_banda._kd_guarda is not f3._kd_guarda and not con_banda.bandas
    # la de F3 sobre OTRO dc no sirve: se arma una de la corrida, una vez
    pr2 = object.__new__(CS.Prueba)
    pr2.an, pr2.compartido, pr2.nubes, pr2._empuje_f3 = {"dc": dc}, {"empuje": BandaEmpujable(
        _sin(dc, {"larguero"}), nubes)}, nubes, None
    pr2.empuje(set(), dc)
    assert pr2._empuje_f3.dc is dc
    assert np.array_equal(pr2.empuje(set(), dc).empujable(pts), f3.empujable(pts))


# ------------------------------------------------------------------ D3: los memos de la corrida
class _Forma:
    def __init__(self, v):
        self.v, self.n = v, 0

    @property
    def volume(self):
        self.n += 1
        return self.v


def test_el_volumen_se_mide_una_vez_por_forma_y_verifica_is():
    a, b = _Forma(2.0), _Forma(3.0)
    assert MC.volumen(a) == 2.0 and MC.volumen(a) == 2.0 and a.n == 2  # sin memo: siempre
    with MC.memo_de_corrida():
        assert MC.volumen(a) == 2.0 and MC.volumen(a) == 2.0 and a.n == 3
        # un id reciclado: la entrada guarda OTRA forma → se mide de nuevo
        MC._tabla("volumen")[id(b)] = (a, 99.0)
        assert MC.volumen(b) == 3.0
    assert not MC.abierto()
    assert MC.volumen(a) == 2.0 and a.n == 4  # el memo murió con el `with`


def test_vol_safe_y_masa_de_viga_con_memo_dan_lo_mismo():
    from build123d import Box, Compound, Pos

    from apolo.library.engineering.mass import memo_de_geometria
    from apolo.library.rules_comun import _vol_safe
    from apolo.services.vigas_rules import _masa_kg

    f = SimpleNamespace(shape=Compound([Box(10, 20, 30), Pos(50, 0, 0) * Box(5, 5, 5)]),
                        name="Placa", component=None, material=None)
    roto = SimpleNamespace(shape=None, name="Roto", component=None, material=None)
    sin = (_vol_safe(f), _masa_kg(f, {}), _vol_safe(roto), _masa_kg(roto, {}))
    with memo_de_geometria():
        assert MC.abierto()
        con = (_vol_safe(f), _masa_kg(f, {}), _vol_safe(roto), _masa_kg(roto, {}))
        assert MC._tabla("volumen")[id(f.shape)][0] is f.shape
    assert sin == con and sin[0] == pytest.approx(6125.0)


def test_la_viga_continua_se_resuelve_una_vez_y_no_se_muta():
    from apolo.library.engineering.viga_continua import (Apoyo, CargaPuntual, CargaRepartida,
                                                          viga_continua)

    args = (1000.0, 2.1e11, [Apoyo(0.0), Apoyo(1000.0)], [CargaRepartida(0.5), CargaPuntual(400.0, 80.0)])
    libre = viga_continua(*args)
    with MC.memo_de_corrida():
        r1 = viga_continua(*args)
        r2 = viga_continua(args[0], args[1], tuple(args[2]), list(args[3]))
        otra = viga_continua(1000, 2.1e11, [Apoyo(0), Apoyo(1000)], args[3])  # 1 ≠ 1.0
        for _ in range(2):  # un error no se guarda: se relanza cada vez
            with pytest.raises(ValueError):
                viga_continua(1000.0, 1.0, [Apoyo(0.0)], [])
    assert r1 is r2 and r1 == libre and otra is not r1
    with pytest.raises(dataclasses.FrozenInstanceError):
        r1.flecha_max_mm = 0.0
    assert isinstance(r1.tramos, tuple) and isinstance(r1.reacciones_n, tuple)


def test_por_clave_cuenta_una_vez_por_argumentos():
    n = []

    def f(*a):
        n.append(a)
        return sum(a)

    with MC.memo_de_corrida():
        assert MC.por_clave("x", f, 1.0, 2.0) == MC.por_clave("x", f, 1.0, 2.0) == 3.0
        assert MC.por_clave("x", f, 1, 2) == 3  # otro tipo, otra entrada
        assert MC.por_clave("y", f, 1.0, 2.0) == 3.0  # otro memo, otra tabla
        with MC.memo_de_corrida():  # anidado: el de afuera manda
            assert MC.por_clave("x", f, 1.0, 2.0) == 3.0
    assert len(n) == 3


def test_lo_que_cuelga_con_lo_alcanzable_una_vez_es_lo_mismo():
    from apolo.library.engineering.loads import alcanzables, hanging_load_kg

    adj = {"piso": {"a"}, "a": {"piso", "b", "c"}, "b": {"a", "c", "d"}, "c": {"a", "b"},
           "d": {"b"}, "e": set()}
    g = {"adj": adj, "grounded_seed": ["piso"]}
    masas = {k: float(i + 1) for i, k in enumerate(adj)}
    antes = alcanzables(g)
    for a in adj:
        for b in adj[a]:
            assert hanging_load_kg(g, masas, a, b, antes) == hanging_load_kg(g, masas, a, b)
    assert hanging_load_kg(g, masas, "b", "d", antes) == masas["d"]
    assert hanging_load_kg({"adj": adj, "grounded_seed": []}, masas, "a", "b", set()) is None
