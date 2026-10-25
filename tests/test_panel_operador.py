"""Panel de operador, puertos de datos y cable de red (plan plc-en-el-lazo, F1d1: D12, D14).

- El catálogo: el panel `HMI-7IN-24VDC` (P, puerta, L+/M/PE, 24 VDC, datos con su ficha), sus
  dos RJ45 y el del PLC; los variadores sin puerto; el cable `CABLE-RJ45-CAT6` por metro.
- `electrico.puertos` (`ficha_puertos.py`): cada rechazo; fuera de `bornes` y de `modelo` (el
  `Dispositivo` del carril no los lleva: ni la red, ni el ERC, ni la firma los ven).
- `tablero.puerta.recorte_mm`: cada rechazo; el hueco de la puerta es el RECORTE, centrado.
- La colocación en la puerta: ⌈ancho/paso⌉ × ⌈alto/paso⌉ celdas, PRIMERO y arriba; holgura de
  lo de detrás verde y roja con su cifra; demasiado grande, con lo que pide.
- `layout_tablero` con el panel: arriba en la puerta, hueco = recorte, junta fija a la puerta,
  recorrido de la puerta sin choques (y uno que la ve chocar), interferencia cero.
- El modelo `hmi`: enciende con tensión ≥ el mínimo, la falla `apagada` con su gemelo sano, en
  el tablero con y sin tensión, y su `pantalla_px` en la tabla del `inicio` del vivo.
- El cable de red entra por `add_cable` sin hilos cableados; el ERC no dice nada del panel ni
  del cable y la BOM lo compra por metro.
"""

from __future__ import annotations

import re
from dataclasses import replace
from types import SimpleNamespace

import pytest
from tablero_electrico import arranque_variador_plc, dev, wire

from apolo.cosim.modelos import MODELOS, ModeloIncompleto, crear_modelo
from apolo.doc.document import Document
from apolo.library.catalog import CATALOG
from apolo.library.electrico.colocacion import Aparato, ColocacionError, Gabinete, colocar
from apolo.library.electrico.ficha import TIPOS_MODELO, ficha_payload, parse_ficha
from apolo.library.electrico.ficha_tablero import parse_tablero

HMI, PLC, CABLE = "HMI-7IN-24VDC", "PLC-14DI-10DO-24VDC", "CABLE-RJ45-CAT6"
DT = 0.002
BU = {"color": "BU", "seccion_mm2": 0.75}


# ── el catálogo ─────────────────────────────────────────────────────────────────────────────


def test_el_panel_del_catalogo_es_honesto():
    c = CATALOG[HMI]
    e = c.electrico
    assert (e.funcion, e.montaje, e.simbolo) == ("P", "puerta", "panel_operador")
    assert [(b.id, b.rol) for b in e.bornes] == [("L+", "mando"), ("M", "mando"), ("PE", "tierra")]
    assert [(x.bornes, str(x.tension), x.tipo) for x in e.cargas] == [(("L+", "M"), "24 VDC", "alimentacion")]
    assert e.modelo == {"tipo": "hmi", "U_min_V": 19.2, "ancho_px": 800, "alto_px": 480}
    assert e.datos == {"T_max_C": 55.0} and e.a_confirmar == ()
    for cita in ("cMT2078X", "820mA@24VDC", "192 x 138", "0° ~ 55°C", "LAN 2"):
        assert cita in e.fuente, cita
    assert [(p.id, p.tipo) for p in e.puertos] == [("LAN1", "rj45"), ("LAN2", "rj45")]
    s = c.specs
    assert s["cotas_verificadas"] is False and s["cost"] > 0 and "del orden de" not in s["linea_referencia"]
    assert s["linea_referencia"].startswith("orden de ")
    assert (c.tablero.puerta.delante_mm, c.tablero.puerta.detras_mm, c.tablero.puerta.recorte_mm) == (7.4, 27.6, (192.0, 138.0))
    assert c.familia == "panel_puerta" and c.params == {"width": 200.3, "depth": 35, "height": 146.3,
                                                         "cuerpo_ancho": 189.6, "cuerpo_alto": 135.6, "marco": 7.4}


def test_el_builder_del_panel_marco_delante_y_cuerpo_que_pasa_el_recorte():
    from apolo.library.builders_tablero import panel_puerta
    from apolo.library.catalog import build_component

    forma = build_component(HMI)[0]
    bb = forma.bounding_box()
    assert (bb.size.X, bb.size.Y, bb.size.Z) == pytest.approx((200.3, 35, 146.3))
    assert (bb.center().X, bb.center().Y, bb.center().Z) == pytest.approx((0, 0, 0), abs=1e-6)
    marco, cuerpo = 200.3 * 7.4 * 146.3, 189.6 * 27.6 * 135.6
    assert forma.volume == pytest.approx(marco + cuerpo, rel=1e-6) and len(forma.solids()) == 1
    for malos, msg in (({"cuerpo_ancho": 201}, "menor que el marco"), ({"marco": 35}, "no cabe en el fondo")):
        with pytest.raises(ValueError, match=msg):
            panel_puerta(**{**CATALOG[HMI].params, **malos})


def test_el_plc_gana_su_puerto_y_los_variadores_no():
    plc = CATALOG[PLC].electrico
    assert [(p.id, p.tipo) for p in plc.puertos] == [("PN1", "rj45")]
    assert "Number of ports 1" in plc.fuente
    assert ficha_payload(plc)["puertos"] == [{"id": "PN1", "tipo": "rj45"}]
    variadores = [r for r, c in CATALOG.items() if c.electrico and (c.electrico.modelo or {}).get("tipo") == "variador"]
    assert variadores and all(CATALOG[r].electrico.puertos == () for r in variadores)
    con = sorted(r for r, c in CATALOG.items() if c.electrico is not None and c.electrico.puertos)
    assert con == [HMI, PLC]


def test_el_cable_de_red_es_por_metro_y_entra_a_add_cable():
    from apolo.commands.models_electrico import _refs_cable

    c = CATALOG[CABLE]
    k = c.electrico.conductor
    assert c.cuttable and c.specs["cost_por_m"] > 0 and c.electrico.montaje == "campo"
    assert [h.id for h in k.hilos] == [str(i) for i in range(1, 9)] and all(h.color is None for h in k.hilos)
    assert k.seccion_mm2 == pytest.approx(0.205) and "2170955" in c.electrico.fuente
    assert CABLE in _refs_cable()


# ── electrico.puertos ───────────────────────────────────────────────────────────────────────


def _ficha(**cambios) -> dict:
    base = {"funcion": "P", "simbolo": "x", "montaje": "puerta",
            "bornes": [{"id": "L+", "rol": "mando"}, {"id": "M", "rol": "mando"}],
            "datos": {"T_max_C": 50}, "fuente": "ficha de prueba",
            "puertos": [{"id": "X1", "tipo": "rj45"}]}
    base.update(cambios)
    return {k: v for k, v in base.items() if v is not None}


PUERTOS_MALOS = [
    ({"puertos": {"id": "X1"}}, r"electrico\.puertos: se espera una lista de puertos"),
    ({"puertos": []}, r"electrico\.puertos: se espera una lista de puertos"),
    ({"puertos": ["X1"]}, r"puertos\[0\]: se espera un mapa \{id, tipo\}"),
    ({"puertos": [{"id": "X1", "tipo": "rj45", "velocidad": 100}]},
     r"puertos\[0\]: clave desconocida «velocidad»; válidas: id, tipo"),
    ({"puertos": [{"tipo": "rj45"}]}, r"puertos\[0\]: falta `id`"),
    ({"puertos": [{"id": "X 1", "tipo": "rj45"}]}, r"no puede llevar espacios ni «:»"),
    ({"puertos": [{"id": "L+", "tipo": "rj45"}]}, r"«L\+» ya es un borne de la ref"),
    ({"puertos": [{"id": "X1", "tipo": "rj45"}, {"id": "X1", "tipo": "rj45"}]}, r"puertos\[1\]: puerto «X1» repetido"),
    ({"puertos": [{"id": "X1", "tipo": "rj46"}]}, r"puertos\[0\]\.tipo: «rj46» no es válido; opciones: rj45\. ¿Quisiste decir «rj45»\?"),
    ({"datos": None, "fuente": None, "montaje": "campo"}, r"electrico\.fuente: falta: con `puertos`"),
]


@pytest.mark.parametrize("cambios,mensaje", PUERTOS_MALOS)
def test_cada_rechazo_de_puertos(cambios, mensaje):
    with pytest.raises(ValueError) as exc:
        parse_ficha(_ficha(**cambios), "PRUEBA")
    assert str(exc.value).startswith("Componente 'PRUEBA': electrico")
    assert re.search(mensaje, str(exc.value)), str(exc.value)


def test_los_puertos_no_son_bornes_ni_modelo_ni_llegan_al_carril():
    f = parse_ficha(_ficha(), "PRUEBA")
    assert f.ids_bornes == ("L+", "M") and "puertos" not in f.modelo and len(f.puertos) == 1
    assert parse_ficha(_ficha(puertos=None), "PRUEBA").puertos == ()
    d = Document()
    d.execute_many([dev(PLC, "-K1"), dev(HMI, "-P2")])
    for x in d.electrico.dispositivos:  # el lado de AIRE (`puertos` del Dispositivo) queda vacío
        assert x.puertos == () and "puertos" not in x.modelo, x.designacion


# ── tablero.puerta.recorte_mm ───────────────────────────────────────────────────────────────


RECORTES_MALOS = [
    (192, r"puerta\.recorte_mm: se espera \[ancho, alto\] en mm, llegó 192"),
    ([192, 0], r"puerta\.recorte_mm\[1\]: se espera un número > 0 mm"),
    ([200.3, 138], r"el hueco 200\.3×138 no es menor que el frente de la caja \(200\.3×146\.3\)"),
    ([189, 138], r"el hueco 189×138 es menor que el cuerpo 189\.6×135\.6 que lo atraviesa"),
]


@pytest.mark.parametrize("recorte,mensaje", RECORTES_MALOS)
def test_cada_rechazo_del_recorte(recorte, mensaje):
    crudo = {"puerta": {"delante_mm": 7.4, "detras_mm": 27.6, "recorte_mm": recorte}}
    with pytest.raises(ValueError, match=mensaje):
        parse_tablero(crudo, "PRUEBA", familia="panel_puerta", params=dict(CATALOG[HMI].params), montaje="puerta")


def test_sin_recorte_el_marco_de_siempre():
    t = parse_tablero({"puerta": {"delante_mm": 20, "detras_mm": 30}}, "P", familia="box",
                      params={"width": 30, "height": 30, "depth": 50}, montaje="puerta")
    assert t.puerta.recorte_mm is None


# ── la colocación en la puerta ──────────────────────────────────────────────────────────────

MEDIO = Gabinete("MEDIO", 450, 350, 160, 1.5, "izquierda")


def _panel(des: str = "-P2") -> Aparato:
    return Aparato(des, HMI, "puerta", 200.3, 146.3, 27.6, "control", "P", "panel_operador", 7.4)


def _mando(des: str, funcion: str = "S", lado: float = 30) -> Aparato:
    return Aparato(des, "PULS", "puerta", lado, lado, 50, "control", funcion, "", 20)


def test_el_panel_toma_3x2_celdas_arriba_y_va_primero():
    from apolo.library.electrico.colocacion_puerta import bloque
    from apolo.library.electrico.colocacion_modelo import Reglas

    assert bloque(_panel(), Reglas()) == (3, 2) and bloque(_mando("-S1"), Reglas()) == (1, 1)
    lay = colocar([_mando("-Q1", "Q", 60), _mando("-H1", "P"), _panel()], "MEDIO", [MEDIO])
    p = lay.de("-P2")
    # bisagra a la izquierda: columnas desde la derecha (410, 340, 270, 200…), filas desde arriba (290, 210…)
    assert (p.u0 + p.ancho / 2, p.v0 + p.alto / 2) == pytest.approx(((410 + 340 + 270) / 3, (290 + 210) / 2))
    assert p.zona == "puerta" and p.w0 == pytest.approx(160 + 1.5 - 27.6) and p.w1 == pytest.approx(161.5 + 7.4)
    q = lay.de("-Q1")  # el seccionador, a la primera celda que el panel deja libre
    assert (q.u0 + q.ancho / 2, q.v0 + q.alto / 2) == (200, 290)
    h = lay.de("-H1")
    assert (h.u0 + h.ancho / 2, h.v0 + h.alto / 2) == (130, 290)


def test_sin_panel_la_puerta_de_siempre():
    """Lo que cabe en una celda: la misma celda que antes del plan (las de `test_colocacion_tablero`)."""
    lay = colocar([_mando("-S1"), _mando("-S2")], "MEDIO", [MEDIO])
    assert [(a.designacion, a.u0 + 15, a.v0 + 15) for a in lay.aparatos] == [("-S1", 410, 290), ("-S2", 340, 290)]


def test_la_holgura_de_detras_del_panel_verde_y_roja():
    """Detrás de la puerta (161,5) el panel ocupa 27,6: su trasera queda en 133,9 y lo de la placa
    que cae en su huella tiene que quedar ≥ 10 mm antes (holgura de la puerta)."""
    hondo = Aparato("-T1", "VFD", "placa", 400, 300, 120, "potencia", "T")
    lay = colocar([hondo, _panel()], "MEDIO", [MEDIO])
    p, t = lay.de("-P2"), lay.de("-T1")
    assert p.zona == "puerta" and t.solapa(p.u0, p.v0, p.u0 + p.ancho, p.v0 + p.alto)
    assert p.w0 - t.w1 == pytest.approx(133.9 - 120) and p.w0 - t.w1 >= 10
    tapa = Aparato("-T1", "VFD", "placa", 400, 300, 145, "potencia", "T")
    with pytest.raises(ColocacionError, match=r"-P2: no hay lugar en la puerta sin chocar con lo de la placa; "
                                              r"la mejor celda deja lo de detrás \(27\.6 mm\) sobre -T1 y "
                                              r"faltan 21 mm de fondo \(holgura 10\)"):
        colocar([tapa, _panel()], "MEDIO", [MEDIO])


def test_un_panel_que_no_cabe_dice_lo_que_pide():
    chico = Gabinete("CHICO", 150, 150, 160, 1.5, "izquierda")
    with pytest.raises(ColocacionError, match=r"-P2 \(HMI-7IN-24VDC, 200\.3×146\.3\) pide 3×2 celdas de 70×80 "
                                              r"y la puerta tiene 2×2"):
        colocar([_panel()], "CHICO", [chico])
    mini = Gabinete("MINI", 200, 150, 160, 1.5, "izquierda")  # 3×2 celdas, pero el bloque se sale
    with pytest.raises(ColocacionError, match=r"-P2: no queda celda libre en la puerta \(6 de 70×80 en "
                                              r"200×150, pide 3×2 contiguas\)"):
        colocar([_panel()], "MINI", [mini])


# ── el tablero armado con el panel ──────────────────────────────────────────────────────────


def _con_panel(*extra) -> list[dict]:
    return arranque_variador_plc() + [
        dev(HMI, "-P2"), wire("-T1:L+", "-P2:L+", **BU), wire("-T1:M", "-P2:M", **BU),
        wire("-X0:1", "-P2:PE", color="GNYE"), *extra]


@pytest.fixture(scope="module")
def armado():
    from apolo.services.tablero import armados

    d = Document()
    d.execute_many(_con_panel(
        {"type": "add_cable", "params": {"designacion": "-W3", "ref": CABLE, "desde": "-P2", "hasta": "-K1",
                                         "largo_m": 2}},
        {"type": "layout_tablero", "params": {"ubicacion": "TAB1"}}))
    (cid, _p, lay, arm), = armados(d)
    return d, cid, lay, arm


def test_el_panel_va_arriba_en_la_puerta_con_el_hueco_de_su_recorte(armado):
    d, cid, lay, arm = armado
    p = lay.de("-P2")
    puerta = [a for a in lay.aparatos if a.zona == "puerta"]
    # toma las dos filas de ARRIBA: su centro, medio paso (80/2) bajo el centro de la fila de arriba
    fila_arriba = max(a.v0 + a.alto / 2 for a in puerta if a is not p)
    assert p.zona == "puerta" and p.v0 + p.alto / 2 == pytest.approx(fila_arriba - 40)
    hueco = next(h for h in arm.huecos if h.clave == "P2")
    x0, x1, z0, z1 = hueco.medidas
    caja = arm.pieza("d_P2").caja
    assert hueco.forma == "rect" and (x1 - x0, z1 - z0) == pytest.approx((192, 138))
    assert ((x0 + x1) / 2, (z0 + z1) / 2) == pytest.approx((caja.centro[0], caja.centro[2]))
    assert arm.pieza("d_P2") in arm.moviles
    f = d.scene[f"{cid}_d_P2"]
    assert f.component == HMI and d.joints[f"{cid}_jf_d_P2"]["parent"] == f"{cid}_puerta"
    # la chapa de la puerta lleva el recorte: le falta el volumen de 192 × 138 × espesor
    from apolo.commands import tablero_geom as geom

    sin = replace(arm, huecos=tuple(h for h in arm.huecos if h.clave != "P2"))
    esp = arm.interior.espesor_puerta
    assert geom.puerta(sin).volume - geom.puerta(arm).volume == pytest.approx(192 * 138 * esp, rel=1e-6)
    assert d.joints[f"{cid}_puerta"]["recorrido"]["choques"] == 0


def test_la_puerta_con_el_panel_no_interfiere_y_su_recorrido_lo_ve(armado):
    from apolo.library.checks import interference_report
    from apolo.library.electrico.armado import Caja, Pieza
    from apolo.library.electrico.recorrido_puerta import recorrer

    d, _cid, _lay, arm = armado
    r = interference_report(d.scene)
    assert r["interferencias"] == [] and not r["truncado"]
    assert recorrer(arm) == (None, 111)
    c = arm.pieza("d_P2").caja  # un poste fijo pegado al frente de la puerta, delante del panel
    y_ext = arm.pieza("puerta").caja.y0
    poste = Pieza("poste", "Poste de prueba", "placa", Caja(c.x0 + 20, c.x0 + 40, y_ext - 5, y_ext - 1, c.z0 + 20, c.z0 + 40))
    choque, _n = recorrer(replace(arm, piezas=arm.piezas + (poste,)))
    assert choque is not None and choque.movil == "-P2" and choque.fijo == "Poste de prueba"
    assert choque.angulo_deg == 0 and choque.penetracion_mm > 0  # el marco asoma 7,4 mm


def test_el_cable_de_red_entra_sin_hilos_y_el_erc_no_dice_nada(armado):
    from apolo.services.electrico import chequeo, filas_bom

    d, *_ = armado
    assert [c.designacion for c in d.electrico.cables if c.ref == CABLE] == ["-W3"]
    malas = [r for r in chequeo(d).get("reglas", []) if r["estado"] != "ok"
             and re.search(r"-P2|-W3|HMI|RJ45", r["detalle"])]
    assert malas == []
    fila = next(f for f in filas_bom(d) if f["ref"] == CABLE)
    assert fila["longitud_mm"] == 2000.0 and fila["cantidad"] == 1


# ── el modelo de la co-simulación ───────────────────────────────────────────────────────────


def _hmi(**ajustes):
    return crear_modelo("-P2", HMI, CATALOG[HMI].electrico.modelo, ajustes)


def test_hmi_es_un_tipo_de_la_ficha_y_del_cosim():
    assert "hmi" in TIPOS_MODELO and MODELOS["hmi"].tipo == "hmi"
    assert set(TIPOS_MODELO) >= set(MODELOS) >= {"hmi"}


def test_enciende_con_tension_desde_el_minimo():
    m = _hmi()
    assert m.pantalla_px == (800, 480) and m.FALLAS == {"apagada": ""}
    for u, encendida in ((0.0, False), (19.0, False), (19.2, True), (24.0, True), (-24.0, False)):
        assert m.paso(DT, {"U_alim_V": u}) == {"encendida": encendida}, u
    assert m.senales() == {"-P2.encendida": False}


def test_la_falla_apagada_con_su_gemelo_sano():
    sano, roto = _hmi(), _hmi()
    roto.fallar("apagada")
    for _ in range(5):
        assert sano.paso(DT, {"U_alim_V": 24.0}) == {"encendida": True}
        assert roto.paso(DT, {"U_alim_V": 24.0}) == {"encendida": False}
    assert "-P2.averia" not in sano.senales() and roto.senales()["-P2.averia"] == "apagada"
    roto.reparar("apagada")
    assert roto.paso(DT, {"U_alim_V": 24.0}) == {"encendida": True} and roto.senales()["-P2.averia"] == ""


def test_sin_dato_de_ficha_no_se_simula():
    with pytest.raises(ModeloIncompleto, match=r"falta «U_min_V»"):
        crear_modelo("-P2", HMI, {"tipo": "hmi", "ancho_px": 800, "alto_px": 480})
    with pytest.raises(ModeloIncompleto, match=r"píxeles enteros"):
        crear_modelo("-P2", HMI, {"tipo": "hmi", "U_min_V": 19.2, "ancho_px": 800.5, "alto_px": 480})


def _tablero(cmds: list[dict]):
    from apolo.cosim.tablero import Tablero
    from apolo.services.cosim_red import entrada_red

    d = Document()
    d.execute_many(cmds)
    m = d.electrico
    return Tablero(entrada_red(m), list(m.dispositivos))


def test_en_el_tablero_con_y_sin_tension():
    con = _tablero(_con_panel())
    for _ in range(50):
        con.paso(DT)
    assert con.senales()["-P2.encendida"] is True
    assert any("-P2" in h and "no declara su consumo" in h for h in con.hipotesis)
    sin = _tablero(arranque_variador_plc() + [dev(HMI, "-P2")])  # declarado y sin cablear
    for _ in range(50):
        sin.paso(DT)
    assert sin.senales()["-P2.encendida"] is False


def test_la_tabla_del_vivo_lleva_la_resolucion_del_panel():
    from apolo.cosim.vivo_fotograma import Fotograma

    tab = _tablero(_con_panel())
    snap_din = SimpleNamespace(cuerpos=[], productos=[], juntas={}, bandas=[])
    corrida = SimpleNamespace(tab=tab, dt=DT, snap=SimpleNamespace(dispositivos=[]),
                              integ=SimpleNamespace(snap=snap_din, d=None, bid_cuerpo={}, giro={}))
    tabla = Fotograma(corrida).tabla()
    por_des = {x["designacion"]: x for x in tabla["dispositivos"]}
    assert por_des["-P2"] == {"designacion": "-P2", "tipo": "hmi", "ref": HMI, "pantalla_px": [800, 480]}
    assert all("pantalla_px" not in x for des, x in por_des.items() if des != "-P2")
    falla = next(x for x in tabla["fallas"] if x["designacion"] == "-P2")
    assert falla == {"designacion": "-P2", "tipo": "hmi", "fallas": [{"falla": "apagada", "pide": ""}]}
