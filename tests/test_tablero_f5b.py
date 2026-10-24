"""Los defectos de código que encontró la verificación F5 de V8.5 (bitácora § F5b), sobre la faja
piloto de `test_cables_campo.py` (estructura mínima + tablero armado + cables de campo):

1. la co-simulación usa los largos CALCULADOS (ruteo del tablero, recorrido `por`) cuando no hay
   `largo_m`, y con todo declarado la red no cambia;
2. una pieza de seguridad en la escena sin dispositivo es ERROR del ERC → ROJO en la puerta;
3. la altura de los mandos sobre el nivel de servicio (0,6–1,7 m);
4. un cable SIN `por` con hilos ruteados cuyo `largo_m` no alcanza: aviso con las dos cifras;
5. un `create_group` no vence los escenarios (firma v2) y un resultado v1 sigue leyéndose;
6. `electrical_check` publica las reglas que corrieron sin hallazgos (`revisadas`);
7. `get_circuit` filtra por ubicación («+TAB1») y por cable («-W4»).
"""

from __future__ import annotations

import pytest
from test_cables_campo import TABLERO, _acciones

from apolo.doc.document import Document


def _doc(acc) -> Document:
    d = Document()
    d.execute_many(acc)
    return d


def _sin_largos(acc) -> list[dict]:
    """Los conductores del tablero sin su `largo_m` a mano (lo que pide el ERC de F2)."""
    for a in acc:
        if a["type"] == "add_wire":
            a["params"].pop("largo_m", None)
    return acc


@pytest.fixture(scope="module")
def piloto() -> Document:
    """La piloto con todo declarado y sin `por` (como un log de antes de F4)."""
    return _doc(_acciones(largo_w1=6.0))


@pytest.fixture(scope="module")
def calculada() -> Document:
    """La piloto sin largos a mano: -W1 con `por` y los conductores del tablero sin `largo_m`."""
    return _doc(_sin_largos(_acciones(por=["c1", "c2"])))


def _ramas(entrada) -> dict:
    return {r["id"]: r for r in entrada["ramas"]}


# ── 1. la co-simulación usa los largos calculados ───────────────────────────────────────


def test_la_red_toma_el_largo_ruteado_y_el_del_recorrido(calculada):
    from apolo.services import cables_campo
    from apolo.services.cosim_red import entrada_red, entrada_red_documento, largos_calculados
    from apolo.services.electrico import modelo
    from apolo.services.tablero import largos, ruteos

    m = modelo(calculada)
    calc = largos_calculados(calculada, m)
    tableros = ruteos(calculada, m)
    assert calc["conductores"] == largos(tableros) and len(calc["conductores"]) > 10
    w1 = next(c for c in m.cables if c.designacion == "-W1")
    assert calc["cables"] == {w1.id: cables_campo.largos(cables_campo.recorridos(calculada, m, tableros))[w1.id]}

    viejo, nuevo = entrada_red(m), entrada_red(m, largos=calc)
    assert entrada_red_documento(calculada) == nuevo
    rv, rn = _ramas(viejo), _ramas(nuevo)
    cid, largo = next(iter(calc["conductores"].items()))
    rid = next(k for k, r in rn.items() if r.get("tipo") == "conductor" and k.split("#")[0] == cid)
    assert rv[rid]["tipo"] == "union"  # antes: unión ideal, sin caída
    tramos = sum(1 for k in rn if k.split("#")[0] == cid)
    assert rn[rid]["largo_m"] == pytest.approx(largo / tramos)
    hilo = rn["-W1.1"]
    assert hilo["tipo"] == "conductor" and hilo["largo_m"] == pytest.approx(calc["cables"][w1.id])
    assert any("largo ruteado" in h for h in nuevo["hipotesis"])
    assert any("-W1" in h and "recorrido" in h for h in nuevo["hipotesis"])
    assert any("unión ideal" in h for h in viejo["hipotesis"])


def test_con_todo_declarado_la_red_es_la_de_siempre(piloto):
    """Sin `por` y con todo `largo_m` a mano, los calculados no tocan nada (la huella de un
    escenario con largos declarados no cambia: `COSIM_EPOCH` sigue)."""
    from apolo.services.cosim_red import entrada_red, largos_calculados
    from apolo.services.electrico import modelo

    m = modelo(piloto)
    assert entrada_red(m, largos=largos_calculados(piloto, m)) == entrada_red(m)


def test_el_banco_de_la_cosim_no_toma_largos_calculados():
    """D8 de cosim-fallas: los escenarios de referencia (el banco, sin tablero armado ni `por`)
    no ven ningún largo calculado, así que su huella no cambia y `COSIM_EPOCH` no sube."""
    from cosim_lazo_banco import faja_directo, faja_variador

    from apolo.services.cosim_red import largos_calculados

    assert largos_calculados(faja_directo()) == {} and largos_calculados(faja_variador()) == {}


def test_el_snapshot_pasa_los_largos_calculados():
    import inspect

    from apolo.services import cosim_snapshot

    assert "largos=largos_calculados(doc, me)" in inspect.getsource(cosim_snapshot.snapshot_cosim)


# ── 2. pieza de seguridad sin circuito ──────────────────────────────────────────────────


def _con_seta_suelta(ligar: bool = False) -> Document:
    acc = _acciones(largo_w1=6.0)
    acc.insert(4, {"type": "insert_component", "params": {"component": "ESTOP-40",
                                                          "position": {"x": 1000, "y": -360, "z": 900}}})
    if ligar:
        acc.insert(5, {"type": "add_device", "params": {"ref": "ESTOP-40", "designacion": "-S9",
                                                        "ubicacion": "+CAMPO", "pieza": "c5"}})
    return _doc(acc)


def test_una_seta_suelta_es_error_y_pone_roja_la_puerta(piloto):
    from apolo.library.delivery import delivery_report
    from apolo.services.delivery_inputs import delivery_inputs
    from apolo.services.electrico import reglas_erc

    assert not [r for r in reglas_erc(piloto) if r["regla"] == "pieza de seguridad sin circuito"]  # -S0: el layout
    d = _con_seta_suelta()
    (fila,) = [r for r in reglas_erc(d) if r["regla"] == "pieza de seguridad sin circuito"]
    assert fila["estado"] == "error" and fila["elementos"] == ["c5"]
    assert "no para nada" in fila["detalle"] and "pieza «c5»" in fila["detalle"]
    assert "remove_commands(['c5']" in fila["detalle"]
    rep = delivery_report(**delivery_inputs(d, expand=lambda v: []))
    assert rep["veredicto"] == "ROJO"
    assert any(b["regla"] == "eléctrico · pieza de seguridad sin circuito" for b in rep["bloqueantes"])
    # ligada a su dispositivo, la regla calla
    assert not [r for r in reglas_erc(_con_seta_suelta(ligar=True))
                if r["regla"] == "pieza de seguridad sin circuito"]


def test_sin_carril_la_seta_no_cambia_nada():
    from apolo.services.electrico import reglas_erc

    d = _doc([{"type": "insert_component", "params": {"component": "ESTOP-40",
                                                      "position": {"x": 0, "y": 0, "z": 900}}}])
    assert reglas_erc(d) is None


# ── 3. altura de los mandos ─────────────────────────────────────────────────────────────


def test_los_mandos_del_tablero_a_1_1_m_estan_en_la_banda(piloto):
    from apolo.services.electrico import chequeo, modelo
    from apolo.services.erc_escena import alturas_mandos

    medidos, supuesto = alturas_mandos(piloto, modelo(piloto))
    des = {d.designacion for d, *_ in medidos}
    assert {"-Q1", "-S0", "-S1", "-S2"} <= des
    assert all(600 <= h <= 1700 for *_, h in medidos)
    assert "ninguna pieza está anclada" in supuesto and "z 0 mm" in supuesto  # la pata llega al piso
    rev = {r["regla"]: r for r in chequeo(piloto)["revisadas"]}
    assert rev["altura de los mandos"]["supuesto"] == supuesto


def test_el_tablero_bajo_avisa_la_altura_del_seccionador():
    from apolo.services.electrico import reglas_erc

    acc = _acciones(largo_w1=6.0)
    lay = next(a for a in acc if a["type"] == "layout_tablero")
    lay["params"]["position"] = {**TABLERO, "z": 400}
    filas = {r["elementos"][0]: r for r in reglas_erc(_doc(acc)) if r["regla"] == "altura de los mandos"}
    q1 = filas["-Q1"]
    assert q1["estado"] == "aviso" and "§5.3.4" in q1["norma"] and "verificar" in q1["norma"]
    assert "bajo la banda de 0.6–1.7 m" in q1["detalle"] and "mando prolongado" in q1["detalle"]
    assert filas["-S0"]["norma"] == "criterio de diseño"


def test_el_nivel_de_servicio_es_lo_mas_bajo_de_lo_anclado():
    from apolo.services.erc_escena import nivel_servicio

    d = _doc([{"type": "create_box", "params": {"name": "Pata", "width": 40, "depth": 40, "height": 500,
                                                "position": {"x": 0, "y": 0, "z": 350}}},
              {"type": "create_box", "params": {"name": "Contrapeso", "width": 40, "depth": 40, "height": 40,
                                                "position": {"x": 500, "y": 0, "z": -200}}},
              {"type": "ground", "params": {"name": "piso", "feature": "c1"}}])
    z, sup = nivel_servicio(d)
    assert z == pytest.approx(100.0) and "ancladas a tierra" in sup


# ── 4. un cable sin `por` que se queda corto ────────────────────────────────────────────


def _red_por_cable(largo_w4: float, tramo: bool = False) -> Document:
    """-W4 (red → +TAB1) lleva sus hilos (c1603–c1606 de la piloto) y, con `tramo`, un tramo 3D
    de 800 mm ligado con `piezas`."""
    acc = _acciones(largo_w1=6.0)
    hilos = {"-G1:L1": "1", "-G1:L2": "2", "-G1:L3": "3", "-G1:PE": "PE"}
    for a in acc:
        p = a["params"]
        if a["type"] == "add_wire" and p["puntos"][0] in hilos:
            a["params"] = {"puntos": p["puntos"], "cable": "-W4", "hilo": hilos[p["puntos"][0]]}
        if a["type"] == "add_cable" and p["designacion"] == "-W4":
            p["largo_m"] = largo_w4
            if tramo:
                p["piezas"] = ["c5"]
    if tramo:
        acc.insert(4, {"type": "create_box", "params": {"name": "Cable de red (tramo)", "width": 800, "depth": 12,
                                                        "height": 12, "position": {"x": -1500, "y": -1500, "z": 200}}})
    return _doc(acc)


def test_un_cable_sin_por_mas_corto_que_lo_de_adentro_avisa():
    from apolo.services.tablero import ruteos

    d = _red_por_cable(0.3)
    (t,) = ruteos(d)
    adentro = max(r.largo_mm for r in t.ruteo.rutas if r.cable == "-W4")
    from apolo.services.electrico import reglas_erc

    (fila,) = [r for r in reglas_erc(d) if r["regla"] == "largo declarado vs ruteado" and "-W4" in r["detalle"]]
    assert "declarado 0.30 m" in fila["detalle"] and f"{adentro / 1000:.2f} m" in fila["detalle"]
    assert "dentro de +TAB1" in fila["detalle"] and "add_cable.por" in fila["detalle"]
    assert '{"largo_m": null}' not in fila["detalle"]  # sin recorrido no hay calculado que comprar
    assert not [r for r in reglas_erc(_red_por_cable(5.0)) if "-W4" in r.get("detalle", "")
                and r["regla"] == "largo declarado vs ruteado"]


def test_el_tramo_3d_cuenta_su_recorrido():
    from apolo.services.electrico import modelo
    from apolo.services.tablero import ruteos
    from apolo.services.tablero_reglas import cables_cortos

    d = _red_por_cable(1.0, tramo=True)
    m = modelo(d)
    ((c, minimo, partes),) = cables_cortos(d, m, ruteos(d, m))
    assert c.designacion == "-W4" and ("el tramo 3D c5", pytest.approx(800.0)) in partes
    assert minimo > 1000.0


# ── 5. un grupo no vence los escenarios ─────────────────────────────────────────────────


def _caja() -> Document:
    return _doc([{"type": "create_box", "params": {"name": "Caja", "width": 100, "depth": 100, "height": 100,
                                                   "position": {"x": 0, "y": 0, "z": 50}}}])


def _resultado(E, esc, firma) -> dict:
    from apolo.cosim import COSIM_EPOCH

    return {"veredicto": "pasa", "aserciones": [], "firma_documento": firma, "cosim_epoch": COSIM_EPOCH,
            "hash_escenario": E.hash_escenario(esc)}


def test_agrupar_no_vence_el_escenario():
    from apolo.services import escenarios as E

    d = _caja()
    esc = {"duracion_s": 1}
    d.escenarios["a"] = {"escenario": esc, "resultado": _resultado(E, esc, E.firma_documento(d))}
    antes = E.firma_documento(d)
    assert antes.startswith("2:")
    d.execute("create_group", {"name": "Todo", "members": ["c1"]})
    assert E.firma_documento(d) == antes and E.estado(d, "a") == {"estado": "pasa"}
    assert E.reglas_escenarios(d)[0]["estado"] == "ok"
    d.edit("c1", {"width": 120}, merge=True)
    assert E.estado(d, "a")["estado"] == "vencido"


def test_con_transform_group_el_grupo_si_cuenta():
    from apolo.services import escenarios as E

    d = _caja()
    d.execute("create_group", {"name": "Todo", "members": ["c1"]})
    d.execute("transform_group", {"group": "Todo", "translate": {"x": 10, "y": 0, "z": 0}})
    antes = E.firma_documento(d)
    d.edit("c2", {"members": ["c1"], "role": "otro"}, merge=True)
    assert E.firma_documento(d) != antes


def test_un_resultado_de_la_firma_vieja_sigue_vigente_si_solo_se_agrupo():
    from apolo.services import escenarios as E

    d = _caja()
    esc = {"duracion_s": 1}
    (v1,) = E.firmas_v1(d)
    assert ":" not in v1
    d.escenarios["a"] = {"escenario": esc, "resultado": _resultado(E, esc, v1)}
    assert E.estado(d, "a") == {"estado": "pasa"}
    d.execute("create_group", {"name": "Todo", "members": ["c1"]})
    assert E.estado(d, "a") == {"estado": "pasa"}  # el grupo va al final: la v1 sin él casa
    d.edit("c1", {"width": 120}, merge=True)
    st = E.estado(d, "a")
    assert st["estado"] == "vencido" and "la máquina cambió" in st["motivo"]


def test_un_resultado_viejo_vence_si_hoy_se_toman_largos_calculados(calculada):
    from apolo.services import escenarios as E

    esc = {"duracion_s": 1}
    (v1, *_) = E.firmas_v1(calculada)
    calculada.escenarios["v1"] = {"escenario": esc, "resultado": _resultado(E, esc, v1)}
    try:
        st = E.estado(calculada, "v1")
        assert st["estado"] == "vencido" and "largos calculados" in st["motivo"]
    finally:
        del calculada.escenarios["v1"]


# ── 6. las reglas que pasan también se ven ──────────────────────────────────────────────


def test_el_erc_publica_las_reglas_que_corrieron_sin_hallazgos(piloto):
    from apolo.services.electrico import chequeo

    ch = chequeo(piloto)
    rev = [r["regla"] for r in ch["revisadas"]]
    assert {"pieza de seguridad sin circuito", "layout del tablero al final", "altura de los mandos"} <= set(rev)
    assert not set(rev) & {r["regla"] for r in ch["reglas"]}
    assert all(r["revisa"] for r in ch["revisadas"])
    assert "cable de campo contra lo que gira" not in rev  # sin `por` no corrió
    sin_tablero = _doc([a for a in _acciones(largo_w1=6.0) if a["type"] != "layout_tablero"])
    rev = [r["regla"] for r in chequeo(sin_tablero)["revisadas"]]
    assert "llenado de canaleta" not in rev and "pieza sin ligar" in rev


# ── 7. get_circuit por ubicación y por cable ────────────────────────────────────────────


def test_el_circuito_filtra_por_ubicacion_y_por_cable(piloto):
    from apolo.services.electrico import circuito
    from apolo.services.errors import ServiceError

    tab = circuito(piloto, "+TAB1")
    assert tab["dispositivos"] and all(d["ubicacion"] == "+TAB1" for d in tab["dispositivos"])
    assert "-M1" not in {d["designacion"] for d in tab["dispositivos"]}
    assert [d["designacion"] for d in circuito(piloto, "+TAB1-Q1")["dispositivos"]] == ["-Q1"]
    w1 = circuito(piloto, "-W1")
    assert [c["designacion"] for c in w1["cables"]] == ["-W1"]
    assert w1["conductores"] and all(c.get("cable") == "-W1" for c in w1["conductores"])
    assert {"-T2", "-M1", "-X0"} <= {d["designacion"] for d in w1["dispositivos"]}
    with pytest.raises(ServiceError) as exc:
        circuito(piloto, "+TAB9")
    assert exc.value.status_code == 404 and "+TAB1" in exc.value.detail
