"""Cables de campo (plan V8.5 F4): `add_cable.por`, el recorrido del prensaestopas del tablero al
aparato, su largo en la BOM y que no toque lo que gira.

- La faja piloto (`tests/data/tablero_piloto.json`) con una estructura mínima: una pata, un
  larguero, un tambor motriz con su junta giratoria y el motorreductor NMRV-090 ligado a -M1. El
  cable del motor -W1 sale del tablero armado, baja a la pata, corre por el larguero y llega al
  motor; su largo se arma A MANO con las cotas de la escena.
- Sin `por`, nada cambia (un log viejo regenera igual y la BOM es la de siempre).
- El ERC: el cable que toca el tambor es error; el declarado que difiere, aviso (la regla de F2);
  el extremo sin pieza, aviso.
- D12: el recorrido se calcula al LEER: editar `por` no re-ejecuta el layout.
- F4b: el panel «Tablero» lista el cable con su largo y avisa lo que toca lo que gira o quedó
  incompleto, leyendo la misma `vista`.
"""

from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import pytest

from apolo.doc.document import Document
from apolo.doc.errors import DocumentError
from apolo.library.electrico.cable_campo import Caja, CriterioCampo, Fijo, acercar, recorrido

PILOTO = json.loads((Path(__file__).parent / "data" / "tablero_piloto.json").read_text(encoding="utf-8"))
TABLERO = {"x": 200, "y": -440, "z": 1100}  # TABLERO-5040 (500 × 200 × 400) junto a la pata
EJE_TAMBOR = {"x": 3950, "y": 0, "z": 800}


def _estructura() -> list[dict]:
    return [
        {"type": "create_box", "params": {"name": "Pata (-X)", "width": 40, "depth": 40, "height": 760,
                                          "position": {"x": 200, "y": -300, "z": 380}}},
        {"type": "create_box", "params": {"name": "Larguero (-Y)", "width": 4000, "depth": 40, "height": 80,
                                          "position": {"x": 2000, "y": -300, "z": 800}}},
        {"type": "create_cylinder", "params": {"name": "Tambor motriz", "radius": 50, "height": 520,
                                               "axis": "y", "position": EJE_TAMBOR}},
        {"type": "insert_component", "params": {"component": "NMRV-090",
                                                "position": {"x": 3950, "y": -450, "z": 800}}},
    ]


def _acciones(por=None, pieza_motor: bool = True, largo_w1: float | None = None) -> list[dict]:
    """La piloto: estructura (c1–c4), su carril y el layout al final. `por` del cable -W1 (None =
    sin el campo, como un log viejo)."""
    acc = _estructura()
    for d in PILOTO["dispositivos"]:
        p = {"ref": d["ref"], "designacion": d["designacion"], "ubicacion": "+TAB1"}
        if "cantidad" in d:
            p["cantidad"] = d["cantidad"]
        acc.append({"type": "add_device", "params": p})
    for d in PILOTO["campo"]:
        p = dict(d)
        if d["designacion"] == "-M1" and pieza_motor:
            p["pieza"] = "c4"
        acc.append({"type": "add_device", "params": p})
    for c in PILOTO["cables"]:
        p = {k: v for k, v in c.items() if k != "id"}
        if p["designacion"] == "-W1":
            p.pop("largo_m")
            if largo_w1 is not None:
                p["largo_m"] = largo_w1
            if por is not None:
                p["por"] = por
        acc.append({"type": "add_cable", "params": p})
    acc += [{"type": "add_wire", "params": {k: v for k, v in c.items() if k != "id"}}
            for c in PILOTO["conductores"]]
    acc.append({"type": "add_joint", "params": {"name": "giro_tambor", "type": "giratoria", "parent": "c2",
                                                "child": "c3", "origin": EJE_TAMBOR,
                                                "axis": {"x": 0, "y": 1, "z": 0}}})
    acc.append({"type": "layout_tablero", "params": {"ubicacion": "TAB1", "position": TABLERO}})
    return acc


def _doc(**kw) -> Document:
    d = Document()
    d.execute_many(_acciones(**kw))
    return d


@pytest.fixture(scope="module")
def piloto() -> Document:
    return _doc(por=["c1", "c2"])


def _w1(doc):
    from apolo.services.cables_campo import recorridos

    return next(c for c in recorridos(doc) if c.designacion == "-W1")


def _caja(doc, fid):
    bb = doc.scene[fid].shape.bounding_box()
    return ((bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z))


def _centro(caja):
    return tuple((caja[0][i] + caja[1][i]) / 2 for i in range(3))


# ── la piloto: el cable del motor ───────────────────────────────────────────────────────


def test_el_cable_del_motor_sale_del_prensaestopas_y_llega_al_motor(piloto):
    """El recorrido a mano: la cara interior del pasacables bajo la vertical izquierda (u 12,5 →
    x = 12,5 − 225 + 200), la pared (1,5) y 50 recto; la pata (entra por su punto más cercano y
    sale hacia el larguero), el larguero (sale frente al motor) y la caja del motor."""
    from apolo.services.tablero import ruteos

    c = _w1(piloto)
    assert c.calculado and not c.sin_extremo and c.diametro_mm == 9.8
    y = TABLERO["y"] + (-100 + 1.5 + 160) - 20  # y_placa − w (el eje de la canaleta)
    z0 = TABLERO["z"] - 200 + 1.5               # la cara interior del piso del gabinete
    salida = [(-12.5, y, z0), (-12.5, y, z0 - 1.5), (-12.5, y, z0 - 1.5 - 50)]
    pata, larguero, motor = (_caja(piloto, f) for f in ("c1", "c2", "c4"))
    p3 = acercar(pata, salida[-1])
    p4 = acercar(pata, _centro(larguero))
    p5 = acercar(larguero, _centro(motor))
    p6 = acercar(motor, p5)
    mano = [*salida, p3, p4, p5, p6]
    assert [tuple(round(x, 3) for x in p) for p in c.polilinea] == \
           [tuple(round(x, 3) for x in p) for p in mano]
    afuera = sum(math.dist(a, b) for a, b in zip(mano, mano[1:]))
    (t,) = ruteos(piloto)
    adentro = max(r.largo_mm for r in t.ruteo.rutas if r.cable == "-W1")
    assert c.afuera_mm == pytest.approx(afuera, abs=0.1)
    assert c.adentro_mm == pytest.approx(adentro, abs=0.1)
    assert c.reserva_mm == CriterioCampo().reserva_campo_mm
    assert c.largo_mm == pytest.approx(adentro + afuera + 300.0, abs=0.2)
    assert 4.4 < c.largo_mm / 1000 < 4.8  # la 77 declaraba 6 m


def test_no_choca_con_lo_que_gira_y_si_pasa_por_el_tambor_es_error(piloto):
    from apolo.services.cables_campo import choques, moviles, recorridos
    from apolo.services.electrico import reglas_erc

    assert "c3" in moviles(piloto)  # el tambor, hijo de su junta giratoria
    assert not any(f.startswith(next(c["id"] for c in piloto.commands if c["type"] == "layout_tablero"))
                   for f in moviles(piloto))  # la puerta del tablero no cuenta
    assert choques(piloto, recorridos(piloto)) == {}
    assert not [r for r in reglas_erc(piloto) if r["regla"].startswith("cable de campo")]
    # el mismo cable con un punto de paso en el eje del tambor: lo atraviesa
    d = _doc(por=["c1", "c2", EJE_TAMBOR])
    filas = [r for r in reglas_erc(d) if r["regla"] == "cable de campo contra lo que gira"]
    assert len(filas) == 1 and filas[0]["estado"] == "error"
    assert "-W1" in filas[0]["detalle"] and "c3" in filas[0]["elementos"] and "\"por\"" in filas[0]["detalle"]
    # por encima del tambor a 6 mm de su cara (r = 50, el cable Ø9,8): aviso, no error
    z = 800 + 50 + 4.9 + 6
    d = _doc(por=["c1", "c2", {"x": 3600, "y": -200, "z": z}, {"x": 3950, "y": -200, "z": z}])
    filas = [r for r in reglas_erc(d) if r["regla"] == "cable de campo contra lo que gira"]
    assert filas and filas[0]["estado"] == "aviso" and "pasa a 6 mm" in filas[0]["detalle"]


def test_la_bom_y_la_cotizacion_compran_el_calculado(piloto):
    from apolo.services.cobros import costeo
    from apolo.services.electrico import filas_bom

    c = _w1(piloto)
    f = next(x for x in filas_bom(piloto) if x["ref"] == "CABLE-4G2.5")
    assert f["longitud_mm"] == pytest.approx(c.largo_mm, abs=0.5) and "aviso" not in f
    assert f["largo_origen"]["n_ruteados"] == 1
    from apolo.library.catalog import CATALOG

    fila = next(r for r in costeo(piloto)["rows"] if r.get("ref") == "CABLE-4G2.5")
    por_m = float(CATALOG["CABLE-4G2.5"].specs["cost_por_m"])
    assert fila["costo_total_usd"] == pytest.approx(por_m * c.largo_mm / 1000, abs=0.02)


def test_el_declarado_manda_y_el_erc_avisa_si_difiere():
    from apolo.services.electrico import filas_bom, reglas_erc

    d = _doc(por=["c1", "c2"], largo_w1=6.0)
    f = next(x for x in filas_bom(d) if x["ref"] == "CABLE-4G2.5")
    assert f["longitud_mm"] == 6000.0 and "largo_origen" not in f
    (fila,) = [r for r in reglas_erc(d) if r["regla"] == "largo declarado vs ruteado" and "-W1" in r["detalle"]]
    assert "declarado 6.00 m" in fila["detalle"] and "recorrido de campo" in fila["detalle"]
    assert '{"largo_m": null}' in fila["detalle"]


def test_el_circuito_y_el_visor_publican_el_recorrido(piloto):
    from apolo.services.cables_campo import vista
    from apolo.services.electrico import circuito

    c = _w1(piloto)
    w1 = next(x for x in circuito(piloto)["cables"] if x["designacion"] == "-W1")
    assert w1["largo_calculado_m"] == pytest.approx(c.largo_mm / 1000, abs=1e-3)
    (v,) = vista(piloto)
    assert v["designacion"] == "-W1" and v["diametro_mm"] == 9.8 and len(v["puntos"]) == len(c.polilinea)
    assert v["partes_mm"]["reserva"] == 300.0 and "choques" not in v
    assert v["extremos"][0]["tipo"] == "tablero" and v["extremos"][1]["designacion"] == "-M1"


def test_el_panel_del_tablero_lista_el_cable_con_su_largo(piloto):
    """F4b: el panel lee `vista` (no recalcula): el largo y sus partes, el recorrido como UN tramo
    y, sin choques, «no tocan lo que gira» en lo que cumple; sin recorridos (get_circuit), sin él."""
    from apolo.services.cables_campo import vista
    from apolo.services.tablero_panel import panel, paneles

    (v,) = vista(piloto)
    p = panel(piloto, "+TAB1")
    (w1,) = p["detalle"]["cables"]
    assert w1["id"] == v["comando"] and w1["designacion"] == "-W1" and w1["largo_m"] == v["largo_m"]
    assert sum(w1["partes_m"].values()) == pytest.approx(w1["largo_m"], abs=2e-3)
    assert w1["partes_m"]["reserva"] == 0.3 and w1["recorrido"] == [v["puntos"]] and w1["piezas"] == []
    assert not any(it["clave"].startswith("cable") for it in p["items"])
    giro = next(it for it in p["detalle"]["bien"] if it["clave"] == "cables-giro")
    assert giro["conductores"] == [v["comando"]] and "10 mm" in giro["detalle"]
    assert p["veredicto"]["frase"] == "2 cosas por revisar"  # lo de la piloto, sin sumar nada
    (sin,) = paneles(piloto)
    assert "recorrido" not in sin["detalle"]["cables"][0]


def test_el_panel_avisa_el_cable_que_toca_o_roza_lo_que_gira():
    """Un ítem por cable, con las piezas que gira (la cámara vuela) y el cable como conductor (se
    dibuja); la frase es para la persona y el texto del ERC va en `tecnico`."""
    from apolo.services.tablero_panel import panel

    p = panel(_doc(por=["c1", "c2", EJE_TAMBOR]), "+TAB1")
    it = next(x for x in p["items"] if x["clave"].startswith("cable-giro-"))
    assert it["severidad"] == "falla" and it["frase"] == "El cable -W1 toca una pieza que gira"
    assert it["piezas"] == ["c3"] and it["conductores"] == [p["detalle"]["cables"][0]["id"]]
    assert "valor" not in it and "edit_command" in it["tecnico"] and "edit_command" not in it["detalle"]
    assert p["detalle"]["cables"][0]["piezas"] == ["c3"]
    assert p["veredicto"]["severidad"] == "falla" and p["items"][0] is it
    z = 800 + 50 + 4.9 + 6
    p = panel(_doc(por=["c1", "c2", {"x": 3600, "y": -200, "z": z}, {"x": 3950, "y": -200, "z": z}]), "+TAB1")
    it = next(x for x in p["items"] if x["clave"].startswith("cable-giro-"))
    assert it["severidad"] == "aviso" and (it["valor"], it["unidad"]) == (6.0, "mm")
    assert "Pasa a 6 mm de «Tambor motriz»" in it["detalle"]
    assert not any(x["clave"] == "cables-giro" for x in p["detalle"]["bien"])


def test_un_extremo_sin_pieza_termina_en_el_ultimo_paso_y_avisa():
    from apolo.services.electrico import reglas_erc
    from apolo.services.tablero_panel import panel

    d = _doc(por=["c1", "c2"], pieza_motor=False)
    c = _w1(d)
    assert c.calculado and c.sin_extremo and c.reserva_mm == 0.0
    assert any("termina en el paso" in s for s in c.supuestos)
    (fila,) = [r for r in reglas_erc(d) if r["regla"] == "cable de campo incompleto"]
    assert "-M1 no está ligado a una pieza" in fila["detalle"]
    # el panel: UN ítem con la cuenta, el mismo texto del ERC en `tecnico`
    p = panel(d, "+TAB1")
    it = next(x for x in p["items"] if x["clave"] == "cables-incompletos")
    assert it["valor"] == 1 and it["conductores"] == [c.id] and it["tecnico"] == fila["detalle"]
    assert "add_device" not in it["frase"] + it["detalle"]
    assert p["detalle"]["cables"][0]["incompleto"]


def test_el_panel_cuenta_solo_los_cables_de_su_tablero():
    from apolo.services.tablero_cables import del_tablero, filas_detalle, items

    filas = [{"comando": "c9", "designacion": "-W9", "ref": "CABLE-5G1", "calculado": False, "motivo": "interno",
              "extremos": [{"lado": "desde", "tipo": "tablero", "ubicacion": "+TAB1"}]},
             {"comando": "c8", "designacion": "-W8", "ref": "CABLE-5G1", "calculado": False, "motivo": "x",
              "extremos": [{"lado": "desde", "tipo": "aparato", "designacion": "-B1"}]}]
    (f,) = del_tablero(filas, "+TAB1")
    assert f["comando"] == "c9" and del_tablero(filas, "+TAB2") == []
    atender, bien = items([f])
    assert [x["clave"] for x in atender] == ["cables-incompletos"] and bien == []
    (fila,) = filas_detalle([f], recorridos=True)
    assert fila.pop("nombre")  # el nombre de catálogo, para la persona
    assert fila == {"id": "c9", "designacion": "-W9", "ref": "CABLE-5G1", "calculado": False, "piezas": [],
                    "incompleto": True}


def test_un_cable_interno_no_se_calcula():
    from apolo.services.cables_campo import recorridos

    acc = _acciones()
    w5 = next(a for a in acc if a["type"] == "add_cable" and a["params"]["designacion"] == "-W5")
    w5["params"]["por"] = [{"x": 0, "y": -500, "z": 1000}]
    d = Document()
    d.execute_many(acc)
    (c,) = recorridos(d)
    assert not c.calculado and "cable interno" in c.motivo
    assert [e["ubicacion"] for e in c.extremos] == ["+TAB1", "+TAB1"]  # el panel de su tablero lo ve


# ── sin `por`, lo de siempre; D12; el carril ────────────────────────────────────────────


def test_sin_por_nada_cambia():
    from apolo.services.cables_campo import recorridos, vista
    from apolo.services.electrico import circuito, filas_bom

    d = _doc(largo_w1=6.0)
    assert recorridos(d) == [] and vista(d) == []
    assert not any("largo_calculado_m" in x for x in circuito(d)["cables"])
    f = next(x for x in filas_bom(d) if x["ref"] == "CABLE-4G2.5")
    assert f["longitud_mm"] == 6000.0 and "largo_origen" not in f
    cmd = next(c for c in d.commands if c["type"] == "add_cable" and c["params"]["designacion"] == "-W1")
    assert "por" not in cmd["params"]  # el log no gana el campo


def test_editar_por_no_rearma_el_tablero_y_el_recorrido_lo_ve():
    d = _doc(por=["c1", "c2"])
    gab = next(k for k in d.scene if k.endswith("_gabinete"))
    antes, largo = d.scene[gab].shape, _w1(d).largo_mm
    cid = next(c["id"] for c in d.commands if c["type"] == "add_cable" and c["params"]["designacion"] == "-W1")
    d.edit(cid, {"por": ["c1", "c2", {"x": 3700, "y": -400, "z": 600}]}, merge=True)
    assert d.scene[gab].shape is antes
    assert _w1(d).largo_mm > largo


def test_una_pieza_de_por_que_no_existe_se_rechaza():
    d = _doc(por=["c1"])
    cid = next(c["id"] for c in d.commands if c["type"] == "add_cable" and c["params"]["designacion"] == "-W1")
    with pytest.raises(DocumentError, match="no existe"):
        d.edit(cid, {"por": ["c999"]}, merge=True)


def test_por_acepta_expresiones_y_rechaza_un_paso_vacio():
    from apolo.commands.errors import CommandError
    from apolo.commands.registry import validate_params

    p = validate_params("add_cable", {"ref": "CABLE-4G2.5", "por": [{"x": "=a * 2", "y": 0, "z": 1}, "c1"]},
                        {"a": "5"})
    assert p.por[0].tuple() == (10.0, 0.0, 1.0) and p.por[1] == "c1"
    with pytest.raises(CommandError):
        validate_params("add_cable", {"ref": "CABLE-4G2.5", "por": [" "]}, {})
    with pytest.raises(CommandError):
        validate_params("add_cable", {"ref": "CABLE-4G2.5", "por": [{"x": 1, "y": 2}]}, {})


def test_un_proyecto_insertado_prefija_las_piezas_de_por():
    from apolo.commands.electrico import prefijar

    p = prefijar("add_cable", {"designacion": "-W1", "ref": "CABLE-5G1", "por": ["c4", {"x": 1, "y": 2, "z": 3}]},
                 "=Faja1", "c9")
    assert p["por"] == ["c9_c4", {"x": 1, "y": 2, "z": 3}]


# ── lo puro ─────────────────────────────────────────────────────────────────────────────


def test_el_recorrido_puro_entra_y_sale_de_cada_caja():
    larguero = ((0, 0, 0), (1000, 40, 80))
    pts = recorrido([Fijo(((-100, 20, 200),)), Caja(larguero), Fijo(((1200, 20, 40),))])
    assert pts == ((-100, 20, 200), (0, 20, 80), (1000, 20, 40), (1200, 20, 40))
    # una caja al final: llega a su punto más cercano; al principio, sale hacia el siguiente
    assert recorrido([Caja(larguero), Fijo(((500, 100, 40),))]) == ((500, 40, 40), (500, 100, 40))


def test_el_recorrido_es_puro():
    fuente = (Path(__file__).parents[1] / "core" / "apolo" / "library" / "electrico" / "cable_campo.py").read_text(
        encoding="utf-8")
    mods = {n.module or "" for n in ast.walk(ast.parse(fuente)) if isinstance(n, ast.ImportFrom)}
    mods |= {a.name for n in ast.walk(ast.parse(fuente)) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m.startswith(("OCP", "build123d", "apolo")) for m in mods), mods
