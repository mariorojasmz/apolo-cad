"""La cola de cajas nace sólo con su lugar de entrada libre (plan V8.4, «Cola de cajas en vivo»).

En la 77, si la persona apretaba el verde tarde, cada caja nacía a su hora ENCIMA de la anterior
(la banda quieta), la torre se caía al arrancar y el contador contaba de menos. La regla
(`physics/dinamica_nacimiento.py`, en el `Integrador`: vale para el vivo, el lote y la dinámica):
  - con la banda quieta nace la primera y las siguientes ESPERAN (ninguna nace encima de otra);
  - al arrancar, nacen en cuanto su lugar se libera y el contador las cuenta todas;
  - por lote, la misma regla: las demoradas llevan `nacio_s` y la salida lo avisa; las que nunca
    encontraron lugar van en `productos_sin_nacer`;
  - la sesión con el verde tarde, vuelta escenario (F4), da por lote la MISMA huella.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")

from apolo.cosim.planificador import correr  # noqa: E402
from apolo.cosim.vivo import Vivo, escenario_vivo  # noqa: E402
from apolo.services.cosim_snapshot import snapshot_cosim  # noqa: E402
from apolo.services.sesion_viva import escenario_de_sesion  # noqa: E402
from cosim_lazo_banco import PROGRAMAS, escenario_variador, faja_variador  # noqa: E402

DUR = 5.0
TARDE = 1.5            # el verde, tarde: la cola (cada 0,5 s desde t = 0) ya tocaba 4 veces
Z_NACE = 850.5         # mm, la caja de la cola del banco (100 mm de alto sobre la banda)
MARCHA = {"accion": "pulsar", "dispositivo": "-S1", "actuador": "marcha", "durante_s": 0.2}


@pytest.fixture(scope="module")
def doc():
    return faja_variador()


@pytest.fixture(scope="module")
def base():
    esc = escenario_variador(DUR, cajas=True)
    esc["acciones"] = []
    return esc


@pytest.fixture(scope="module")
def sesion(doc, base):
    """La sesión en vivo con el verde a los 1,5 s: lo que se vio, intercambio a intercambio."""
    v = Vivo(snapshot_cosim(doc, escenario_vivo(base), programas=PROGRAMAS), trazas=True)
    integ = v.c.integ
    prods = integ.snap.productos
    plan = {0: [{"girar": "-S1", "valor": 1.0}], round(TARDE / v.dt): [dict(MARCHA)]}
    nacio, z_max, activas_antes, esperando_antes = {}, 0.0, None, None
    n = round(DUR / v.dt)
    while v.k < n:
        for msg in plan.get(v.k, []):
            assert v.recibir(msg) is None
        if v.k == round(TARDE / v.dt):
            activas_antes = sum(integ.activo)
            esperando_antes = len(integ.nac.esperando)
        v.avanzar(1)
        v.respuestas()
        for k, p in enumerate(prods):
            if integ.activo[k]:
                z = float(integ.d.xpos[integ.bid_prod[k]][2]) * 1000.0
                z_max = max(z_max, z)
                nacio.setdefault(p["name"], round(v.t, 3))
    final = {k: float(integ.d.xpos[integ.bid_prod[k]][0]) * 1000.0
             for k in range(len(prods)) if integ.activo[k]}
    cuenta = v.c.plcs["-K1"].variables()["Main.cuenta"]
    return {"v": v, "nacio": nacio, "z_max": z_max, "activas_antes": activas_antes,
            "esperando_antes": esperando_antes, "final_x": final, "cuenta": cuenta,
            "grabacion": list(v.grabacion), "huella": v.cerrar_lote()}


def test_con_la_banda_quieta_nace_una_y_las_demas_esperan(sesion):
    assert sesion["activas_antes"] == 1, "con la banda quieta sólo cabe la primera caja"
    assert sesion["esperando_antes"] >= 2  # las de 0,5 / 1,0 / 1,5 s esperan su lugar
    # ninguna caja nació (ni estuvo nunca) encima de otra: la torre de la 77 no se arma
    assert sesion["z_max"] < Z_NACE + 20.0, sesion["z_max"]


def test_al_arrancar_nacen_en_cuanto_se_libera_y_se_cuentan(sesion):
    nacio = sorted(sesion["nacio"].values())
    assert nacio[0] == pytest.approx(0.002, abs=1e-6)
    assert all(t > TARDE for t in nacio[1:]), nacio  # la cola se retrasó, no se perdió
    assert len(nacio) >= 5
    # la fotocelda (x = 0) cuenta cada caja cuyo frente la cortó (150 mm de largo): ninguna se
    # cayó de una torre, así que cuenta todas las que llegaron (antes, la torre contaba de menos)
    pasaron = sum(1 for x in sesion["final_x"].values() if x + 75.0 > 0.0)
    assert sesion["cuenta"] == pasaron and pasaron >= 3, (sesion["cuenta"], sesion["final_x"])


def test_la_sesion_vuelta_escenario_da_la_misma_huella(doc, base, sesion):
    v = sesion["v"]
    out = escenario_de_sesion(escenario_vivo(base), sesion["grabacion"], round(v.k * v.dt, 6),
                              base="base")
    res = correr(snapshot_cosim(doc, out["escenario"], programas=PROGRAMAS))
    assert res["resumen"]["huella"] == sesion["huella"]
    mec = res["mecanica"]
    demoradas = [n for n, p in mec["resumen"]["productos"].items() if "nacio_s" in p]
    assert len(demoradas) >= 3 and not mec["resumen"]["productos_caidos"]
    assert any("lugar de entrada" in a and "nacieron tarde" in a for a in mec["avisos"])


def test_por_lote_sin_arrancar_la_cola_no_apila_y_lo_dice(doc):
    esc = escenario_variador(2.0, cajas=True)
    esc["acciones"] = esc["acciones"][:1]  # sólo el potenciómetro: la banda nunca anda
    mec = correr(snapshot_cosim(doc, esc, programas=PROGRAMAS))["mecanica"]
    res = mec["resumen"]
    nacidas = [p for p in res["productos"].values()]
    assert len(nacidas) == 1 and nacidas[0]["posicion_final_mm"][2] < Z_NACE + 5.0
    # las de 0,5 / 1,0 / 1,5 s (la de 2,0 s no llega a tocar: la corrida termina)
    assert res["productos_sin_nacer"] == ["p_caja_1", "p_caja_2", "p_caja_3"]
    assert any("no llegaron a nacer" in a for a in mec["avisos"])
