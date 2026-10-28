"""`create_roller_conveyor` F7: el eje HEXAGONAL que se calza (plan
`docs/plans/plantilla-rodillos-cadena.md`, § Bitácora F7, E6–E7).

El revisor de taller ciego vio que con el eje M12 trabado de F6 cambiar UN rodillo lleva 10–15 min
(sostener la tuerca interior y destornillar ~50 vueltas entre tubos) y que la BOM traía el eje
como «A-MEDIDA 472» liso. F7:
- E6: barra hexagonal 11 con los extremos a doble plano, calzada en una ranura abierta hacia
  arriba del ala vertical (no gira ni corre; el rodillo sale levantándolo), sobre 6202 de agujero
  hexagonal; con cadena, la misma ranura (la cuenta del tiro);
- E7: la BOM nombra la barra (entrecaras, norma, largo de corte, doble plano);
- todo entra por el campo oculto `eje` que pone el sello: un log F6 regenera igual.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from build123d import Axis, Pos

from apolo.commands.registry import REGISTRY
from apolo.doc import Document
from apolo.library import rodillos_cadena as rc
from apolo.library import rodillos_cadena_eje as hx
from apolo.library.bom import bom_from_scene
from apolo.library.catalog import CATALOG
from apolo.library.delivery import VERDE, delivery_report
from apolo.library.rodillos_cadena_reglas import reglas_rodillos_cadena
from apolo.services.delivery_inputs import delivery_inputs
from banco_guardas import interferencias_sin_tope

LIBRE = {"largo": 1500, "ancho_util": 400, "paso": 75, "motriz": "libre"}
LIBRE_3M = {"largo": 3000, "ancho_util": 400, "paso": 75, "motriz": "libre"}
CADENA_3M = {"largo": 3000, "velocidad_m_s": 0.25, "carga_kg": 200}
#: lo que da F6 (`taller` sin `eje`), congelado con el código de 10cd6be ANTES de F7: piezas,
#: uniones y anclajes (como `HUELLA_V3` de F6) y la huella geométrica (volumen y caja de cada pieza)
HUELLA_F6 = {"libre": ((252, 288, "58f80d95432486cd"), "963e10facfaa22e7"),
             "cadena": ((528, 627, "972e3287d3694b53"), "005339ede5bc434d")}
#: lo que forma el rodillo que se saca (el primero: la fuente de cada patrón)
RODILLO = ("c1_eje", "c1_tubo", "c1_tapa_m", "c1_tapa_p", "c1_rod_m", "c1_rod_p", "c1_sep_m",
           "c1_sep_p")


def _doc(params: dict) -> Document:
    doc = Document("rodillos-f7")
    doc.execute("create_roller_conveyor", dict(params))
    return doc


@pytest.fixture(scope="module")
def libre():
    return _doc(LIBRE)


@pytest.fixture(scope="module")
def libre_3m():
    return _doc(LIBRE_3M)


@pytest.fixture(scope="module")
def cadena():
    return _doc(CADENA_3M)


@pytest.fixture(params=["libre", "libre_3m", "cadena"])
def maquina(request):
    return request.getfixturevalue(request.param)


def _bb(doc, fid):
    b = doc.scene[fid].shape.bounding_box()
    return (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)


def _comun(a, b) -> float:
    """mm³ del sólido común (0 si sólo se tocan: el contacto en una arista da una ShapeList)."""
    c = a & b
    if c is None:
        return 0.0
    if isinstance(c, list):
        return sum(float(getattr(s, "volume", 0.0)) for s in c)
    return float(c.volume)


def _huella(doc) -> tuple:
    piezas = sorted([fid, f.name, f.component or ""] for fid, f in doc.scene.items())
    uniones = sorted([u["name"], u["kind"], u["a"], u["b"], u.get("nota", "")]
                     for u in doc.fasteners.values())
    anclajes = sorted([g["feature"], g.get("nota", "")] for g in doc.grounds.values())
    s = json.dumps([piezas, uniones, anclajes], ensure_ascii=False)
    return len(piezas), len(uniones), hashlib.sha256(s.encode()).hexdigest()[:16]


def _geom(doc) -> str:
    filas = []
    for fid, f in sorted(doc.scene.items()):
        b = f.shape.bounding_box()
        filas.append([fid, round(float(f.shape.volume), 1)]
                     + [round(v, 2) for v in (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)])
    return hashlib.sha256(json.dumps(filas).encode()).hexdigest()[:16]


def _disp(params: dict, eje: str):
    p = {"ancho_util": 500, "paso": 95.25, "rodillo": "TUBOR-2", "altura": 750, "carga_kg": 100,
         "motriz": "cadena", "motor": "MOTOR-037", **params}
    return rc.disposicion(p["largo"], p["ancho_util"], p["paso"], p["rodillo"], p["altura"],
                          p["carga_kg"], p["motriz"] == "cadena", p["motor"],
                          p.get("velocidad_m_s"), True, True, eje)


# ------------------------------------------------------------------ el sello
def test_el_comando_nuevo_nace_con_el_eje_hexagonal_y_el_campo_no_se_publica(libre):
    assert libre.commands[0]["params"]["eje"] == "hexagonal"
    assert libre.commands[0]["params"]["taller"] is True
    spec = REGISTRY["create_roller_conveyor"]
    assert "eje" not in spec.model.model_json_schema()["properties"]
    assert spec.version == 3  # entra por los params (cambia la firma): no hace falta subirla
    # un log F6 (con `taller`, sin `eje`) lee «roscado»; lo explícito se respeta
    assert spec.model.model_validate({**LIBRE, "taller": True}).eje == "roscado"
    assert _doc({**LIBRE, "eje": "roscado"}).commands[0]["params"]["eje"] == "roscado"
    assert "eje" not in _doc({**LIBRE, "taller": False}).commands[0]["params"]
    with pytest.raises(Exception, match="taller"):
        _doc({**LIBRE, "taller": False, "eje": "hexagonal"})


@pytest.mark.parametrize("caso, params", [("libre", LIBRE), ("cadena", CADENA_3M)])
def test_un_log_f6_regenera_las_mismas_piezas_y_cotas(caso, params):
    doc = _doc({**params, "eje": "roscado"})
    assert doc.check_integrity() == []
    assert (_huella(doc), _geom(doc)) == HUELLA_F6[caso]


# ------------------------------------------------------------------ E6: eje y ranura
def test_el_eje_es_hexagonal_y_sus_extremos_entran_en_la_ranura(maquina):
    s, r = hx.EJE_HEX, hx.r_esquinas()
    t = float(CATALOG[rc.LARGUERO].specs["t"])
    for eje in (f for f in maquina.scene if f == "c1_eje" or f.startswith("c1_ejes_")):
        b = _bb(maquina, eje)
        assert (b[3] - b[0], b[5] - b[2]) == pytest.approx((s, 2.0 * r), abs=1e-3)
        assert maquina.scene[eje].component is None  # se fabrica de la barra
    # dentro del ala, el extremo es el doble plano (8 de ancho): por eso pasa la ranura de 8,5
    e, larg = maquina.scene["c1_eje"].shape, _bb(maquina, "c1_larg_m")
    x0 = maquina.scene["c1_eje"].shape.center().X
    from build123d import Box

    ala = Pos(x0, larg[4] - t / 2.0, maquina.scene["c1_eje"].shape.center().Z) * Box(30, t - 0.2, 30)
    tramo = (e & ala).bounding_box()
    assert tramo.max.X - tramo.min.X == pytest.approx(hx.PLANOS, abs=1e-3)


def test_la_ranura_esta_abierta_hacia_arriba_con_el_ancho_del_doble_plano(libre):
    """Un prisma de RANURA − 0.02 de ancho, del fondo de la ranura hasta 50 mm sobre el canto, no
    toca el larguero; uno de RANURA + 1, sí (las paredes de la ranura están ahí)."""
    from build123d import Box

    d = rc.disposicion(1500, 400, 75, "TUBOR-2", 750, 100, False, None, None, True, True,
                       "hexagonal")
    z_fondo, z_canto = d.h_eje - hx.asiento(), d.h_eje + rc.TOPE_SOBRE_EJE
    larg = libre.scene["c1_larg_m"].shape
    y_ala = _bb(libre, "c1_larg_m")[4] - 3.0
    for x in d.xs:
        def prisma(ancho, z0=z_fondo, x=x):
            return Pos(x, y_ala, (z0 + z_canto + 50.0) / 2.0) * Box(ancho, 4.0, z_canto + 50.0 - z0)

        assert _comun(larg, prisma(hx.RANURA - 0.02)) < 1e-3
        assert _comun(larg, prisma(hx.RANURA + 1.0)) > 1.0
        # el fondo redondo: bajo el taladro Ø RANURA, el ala está entera
        assert _comun(larg, prisma(2.0, z_fondo - hx.RANURA / 2.0 - 1.0)) > 0.1


def test_el_rodillo_sale_levantandolo_sin_tocar_una_tuerca(libre):
    """El rodillo con su eje, sus tapas, rodamientos y separadores sube 30 mm (hasta sacar el eje
    por encima del canto del ala) sin tocar ninguna otra pieza en el camino. No hay tuercas."""
    rodillo = {f: libre.scene[f].shape for f in RODILLO}
    otros = {f: x.shape for f, x in libre.scene.items() if f not in rodillo}
    assert not [f for f in libre.scene if "tuerca" in f and "pie" not in f]
    for dz in (0.5, 2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0):
        for f, forma in rodillo.items():
            subida = Pos(0, 0, dz) * forma
            caja = subida.bounding_box()
            for o, otra in otros.items():
                ob = otra.bounding_box()
                if (caja.min.X > ob.max.X or caja.max.X < ob.min.X or caja.min.Y > ob.max.Y
                        or caja.max.Y < ob.min.Y or caja.min.Z > ob.max.Z or caja.max.Z < ob.min.Z):
                    continue
                assert _comun(subida, otra) < 1e-3, (dz, f, o)
    # a 30 mm el eje ya pasó el canto del larguero
    assert _bb(libre, "c1_eje")[2] + 30.0 > _bb(libre, "c1_larg_m")[5]


def test_con_cadena_tambien_sale_levantandolo_quitadas_la_guarda_y_las_cadenas(cadena):
    """Con cadena, el rodillo sube con su buje y su piñón: no toca los largueros."""
    piezas = RODILLO + ("c1_buje", "c1_pinon")
    for dz in (1.0, 5.0, 15.0, 30.0):
        for f in piezas:
            subida = Pos(0, 0, dz) * cadena.scene[f].shape
            for larg in ("c1_larg_m", "c1_larg_p"):
                assert _comun(subida, cadena.scene[larg].shape) < 1e-3, (dz, f, larg)


def test_el_eje_no_gira_ni_corre_en_su_ranura(libre):
    e = libre.scene["c1_eje"].shape
    c = e.center()
    largs = [libre.scene[f].shape for f in ("c1_larg_m", "c1_larg_p")]
    assert all(_comun(e, larg) < 1e-3 for larg in largs)  # calzado: se toca, no se mete
    girado = e.rotate(Axis((c.X, 0, c.Z), (0, 1, 0)), 3.0)
    assert sum(_comun(girado, larg) for larg in largs) > 0.1  # el doble plano no deja girar
    # el hombro: corre ± HOLGURA_HOMBRO y ahí topa con el ala
    for dy in (hx.HOLGURA_HOMBRO - 0.05, -(hx.HOLGURA_HOMBRO - 0.05)):
        assert all(_comun(Pos(0, dy, 0) * e, larg) < 1e-3 for larg in largs)
    for dy in (hx.HOLGURA_HOMBRO + 0.3, -(hx.HOLGURA_HOMBRO + 0.3)):
        assert sum(_comun(Pos(0, dy, 0) * e, larg) for larg in largs) > 0.01


def test_el_juego_axial_del_rodillo_queda_en_2_mm_o_menos(maquina):
    ym, yp = _bb(maquina, "c1_larg_m")[4], _bb(maquina, "c1_larg_p")[1]
    sep_m, sep_p = _bb(maquina, "c1_sep_m"), _bb(maquina, "c1_sep_p")
    rod_m, rod_p = _bb(maquina, "c1_rod_m"), _bb(maquina, "c1_rod_p")
    assert sep_m[1] == pytest.approx(ym) and sep_p[4] == pytest.approx(yp)  # apoyan en el ala
    juego = (rod_m[1] - sep_m[4]) + (sep_p[1] - rod_p[4])
    assert juego == pytest.approx(2.0 * rc.JUEGO_AXIAL) and juego <= 2.0
    # el eje no toca los rodamientos (agujero hexagonal deslizante) ni los separadores
    e = maquina.scene["c1_eje"].shape
    for f in ("c1_rod_m", "c1_rod_p", "c1_sep_m", "c1_sep_p"):
        assert 0.0 < e.distance_to(maquina.scene[f].shape) < 0.5, f


def test_el_6202_hexagonal_es_de_compra_y_no_entra_en_los_tensores(maquina):
    n = len([f for f in maquina.scene if f == "c1_tubo" or f.startswith("c1_tubos_")])
    filas = {f["ref"]: f for f in bom_from_scene(maquina.scene, maquina.default_material())}
    assert filas[hx.RODAMIENTO_HEX]["cantidad"] == 2 * n and "6201" not in filas
    assert "TUERCA-M12" not in filas or "pie" in json.dumps(filas["TUERCA-M12"])
    from apolo.commands.models_rodillos import _bearing_refs

    assert hx.RODAMIENTO_HEX not in _bearing_refs() and "6202" in _bearing_refs()


def test_lo_que_gira_libra_el_aro_interior_y_el_separador(cadena):
    sep = cadena.scene["c1_sep_p"].shape
    for gira in ("c1_buje", "c1_pinon", "c1_tapa_p"):
        assert sep.distance_to(cadena.scene[gira].shape) >= 1.0, gira
    assert sep.distance_to(cadena.scene["c1_buje"].shape) == pytest.approx(
        hx.HUECO_GIRA_R - hx.SEPARADOR_D / 2.0, abs=0.01)


# ------------------------------------------------------------------ E7: la BOM del eje
def test_la_bom_nombra_la_barra_con_su_largo_de_corte(maquina):
    n = len([f for f in maquina.scene if f == "c1_eje" or f.startswith("c1_ejes_")])
    filas = [f for f in bom_from_scene(maquina.scene, maquina.default_material())
             if "barra hexagonal" in f["descripcion"]]
    assert len(filas) == 1
    fila, b = filas[0], _bb(maquina, "c1_eje")
    assert fila["ref"] == "A-MEDIDA" and fila["cantidad"] == n
    assert f"barra hexagonal {hx.EJE_HEX:g} EN 10278" in fila["descripcion"]
    assert f"doble plano {hx.PLANOS:g}" in fila["descripcion"]
    # se FABRICA (la columna norma es de lo que se compra): la norma de la barra va en la descripción
    assert fila["categoria"] == "a medida"
    assert fila["longitud_mm"] == pytest.approx(b[4] - b[1], abs=0.1)


# ------------------------------------------------------------------ con cadena: la cuenta
@pytest.mark.parametrize("params", [
    {"largo": 3000, "velocidad_m_s": 0.25, "carga_kg": 200},
    {"largo": 2000},
    {"largo": 4000, "rodillo": "TUBOR-3", "paso": 107.95, "carga_kg": 400},
])
def test_con_cadena_ningun_tiro_saca_el_eje_de_su_ranura(params):
    """Las cadenas 1:1 tiran en horizontal (los dos piñones a la misma altura) y la motriz hacia
    el motor, que va DEBAJO: ninguna tracción tiene componente hacia arriba; la pared de la
    ranura toma lo horizontal. Por eso la versión con cadena lleva la misma ranura abierta."""
    tiro = hx.tiro_vertical_cadena(_disp(params, "hexagonal"))
    assert tiro["lazos"] == 0.0 and tiro["motriz"] < -0.5


def test_el_motor_va_bajo_el_ultimo_rodillo(cadena):
    assert cadena.scene["c1_pinon_m"].shape.center().Z < cadena.scene["c1_eje"].shape.center().Z


# ------------------------------------------------------------------ la ranura y el larguero
def test_las_ranuras_recortan_el_vano_del_larguero():
    k_w, k_i = hx.factores_ranura(75.0, 6.0, rc.TOPE_SOBRE_EJE + hx.asiento() + hx.RANURA / 2.0,
                                  75.0)
    assert 0.3 < k_w < 0.6 and 0.6 < k_i < 0.95
    # con poca carga manda el tope de 1,8 m; con mucha, la sección POR la ranura
    liviano = {"largo": 3000, "motriz": "libre", "paso": 75}
    assert _disp(liviano, "hexagonal").vano_max == _disp(liviano, "roscado").vano_max == 1800.0
    pesado = {**liviano, "carga_kg": 4000}
    assert _disp(pesado, "hexagonal").vano_max < _disp(pesado, "roscado").vano_max


def test_engineering_check_da_la_capacidad_con_el_eje_hexagonal():
    params = {"largo": 3000, "ancho_util": 500, "paso": 95.25, "rodillo": "TUBOR-2",
              "altura": 750, "carga_kg": 200, "motriz": "cadena", "motor": "MOTOR-037",
              "velocidad_m_s": 0.25, "taller": True}
    hexa = {r["regla"]: r for r in reglas_rodillos_cadena({**params, "eje": "hexagonal"}, 25, 400,
                                                          0.25, 400)}["capacidad de rodillo"]
    assert hexa["estado"] == "ok" and "hexagonal 11" in hexa["detalle"]
    assert hx.RODAMIENTO_HEX in hexa["calc"]["entradas"]["rodamientos"]
    f6 = {r["regla"]: r for r in reglas_rodillos_cadena(params, 25, 400, 0.25,
                                                        400)}["capacidad de rodillo"]
    assert "M12" in f6["detalle"] and "6201" in f6["calc"]["entradas"]["rodamientos"]


# ------------------------------------------------------------------ sin interferencias, puerta
@pytest.mark.parametrize("nombre", ["libre", "cadena"])
def test_sin_interferencias_ni_siquiera_con_la_tornilleria(nombre, request):
    doc = request.getfixturevalue(nombre)
    assert doc.check_integrity() == []
    formas = {f: x.shape for f, x in doc.scene.items()}
    assert interferencias_sin_tope(formas, set()) == []


def test_las_uniones_del_eje_son_de_calce(maquina):
    notas = {u["name"].rsplit("[", 1)[0]: u for u in maquina.fasteners.values()}
    for s in ("m", "p"):
        u = notas[f"c1_eje_larg_{s}"]
        assert u["kind"] == "contacto" and "levantándolo" in u["nota"]
        assert notas[f"c1_sep_{s}"]["kind"] == notas[f"c1_rod_{s}"]["kind"] == "contacto"
    # ni tuercas del eje (exterior ni interior): las únicas, las de los pies
    assert not [n for n in notas if n in ("c1_tuerca_m", "c1_tuerca_p", "c1_tuerca_im",
                                          "c1_tuerca_ip")]


def test_la_puerta_de_entrega_da_verde(libre):
    rep = delivery_report(**delivery_inputs(libre, expand=lambda v: []))
    assert rep["veredicto"] == VERDE and rep["avisos"] == [] and rep["bloqueantes"] == []
    # sin tuercas de eje: 4 soldadas + 4 contratuercas + 8 anclajes
    assert "acceso de herramienta (16 fijador(es))" in rep["resumen"]["chequeos_ok"]


@pytest.mark.torture
@pytest.mark.parametrize("params", [LIBRE, CADENA_3M])
def test_verde_con_gravedad(params):
    from fastapi.testclient import TestClient

    import apolo.api.main as api

    api.DOC = Document("rodillos-f7-gravedad")
    client = TestClient(api.app)
    r = client.post("/api/commands", json={"type": "create_roller_conveyor", "params": params})
    assert r.status_code == 200, r.text
    assert api.DOC.commands[0]["params"]["eje"] == "hexagonal"
    rep = client.post("/api/delivery-check", json={"con_gravedad": True}).json()
    assert rep["veredicto"] == VERDE and rep["avisos"] == [], rep
    assert "gravedad" in rep["resumen"]["chequeos_ok"]
