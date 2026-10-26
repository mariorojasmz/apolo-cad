"""El calentamiento y los prensaestopas de un tablero armado (plan V8.5 F3: D6, D7, D10):
`services/tablero_calor.py`, `services/tablero_prensas.py` y sus reglas del ERC, sobre la faja
piloto (`tests/data/tablero_piloto.json`, la misma de `test_tablero_panel.py`).

- La piloto en el TABLERO-5040 cerrado SE PASA: 128 W de los aparatos + los conductores (I²R con
  la corriente de la regla 3) en Ae = 0,564 m² → ~98 °C arriba contra los 50 °C del variador y el
  seccionador. El ERC da el error con el caudal sugerido; con ese ventilador declarado
  (`ventilacion_m3h`), cumple (caso rojo y verde).
- Las caras cubiertas salen de la escena: una chapa sobre el techo lo cubre.
- Los prensaestopas: uno por cable que sale, por su Ø; la BOM los compra; un Ø que ninguno sujeta
  es aviso (rojo) y la piloto no lo tiene (verde).
- Un aparato de tablero fuera de la ubicación armada es aviso.
"""

from __future__ import annotations

import pytest

from apolo.doc.document import Document
from apolo.services import tablero_calor, tablero_prensas
from apolo.services.electrico import chequeo, filas_bom, modelo
from apolo.services.tablero import ruteos

from test_tablero_panel import _acciones


def _doc(extra: list[dict] | None = None, **layout) -> Document:
    d = Document()
    d.execute_many((extra or []) + _acciones(**layout))
    return d


@pytest.fixture(scope="module")
def piloto() -> Document:
    return _doc()


def _ev(doc):
    m = modelo(doc)
    (t,) = ruteos(doc, m)
    return tablero_calor.evaluacion(doc, m, t)


def _filas(doc, regla):
    return [r for r in chequeo(doc)["reglas"] if r["regla"] == regla]


def test_la_piloto_cerrada_se_pasa_y_el_erc_lo_dice(piloto):
    e = _ev(piloto)
    assert e["estado"] == "falla" and e["rama"].startswith("Ae ≤ 1.25")
    assert e["Ae_m2"] == pytest.approx(0.564, abs=1e-3)  # techo libre: nada lo tapa en la piloto
    assert e["perdidas"]["aparatos_W"] == 128.0           # 90 W del variador (F0 § 5)
    assert e["perdidas"]["conductores_W"] == pytest.approx(28.9, abs=0.2)
    assert e["perdidas"]["sin_dato"] == ["-S1", "-S2", "-S0", "-X0"]
    assert e["ambiente_C"] == 35.0 and not e["ambiente_dado"]
    assert e["T_media_C"] == pytest.approx(89.9, abs=0.2) and e["T_arriba_C"] == pytest.approx(98.5, abs=0.2)
    pasan = {a["designacion"] for a in e["aparatos"] if a.get("pasa")}
    assert {"-T2", "-Q1", "-K1", "conductores"} <= pasan and "-X0" not in pasan  # el borne admite 105 °C
    assert e["sin_tmax"] == ["-T1"]  # la fuente: su T_max_C está a confirmar
    assert e["peor"] == {"designacion": "-Q1", "T_C": e["T_arriba_C"], "T_max_C": 50.0}
    s = e["sugerencia"]
    assert s["dt_admisible_K"] == 15.0 and s["caudal_m3h"] == pytest.approx(32.7, abs=0.2)
    assert "gabinete" not in s  # el GAB-6040 no la contiene y el GAB-8060 también se pasa
    assert any("IEC 60890:1987" in x for x in e["supuestos"])
    (fila,) = _filas(piloto, "calentamiento del tablero")
    assert fila["estado"] == "error" and "33 m³/h" in fila["detalle"] and "ventilacion_m3h" in fila["recomendacion"]
    assert chequeo(piloto)["estado"] == "error"


def test_con_el_ventilador_sugerido_cumple():
    d = _doc(ventilacion_m3h=33)
    e = _ev(d)
    assert e["estado"] == "bien" and e["ventilacion_m3h"] == 33.0
    assert e["rama"].startswith("ventilación forzada") and e["T_arriba_C"] <= 50.0
    assert not _filas(d, "calentamiento del tablero")
    assert "calentamiento del tablero" in {r["regla"] for r in chequeo(d)["revisadas"]}


def test_sin_temperaturas_maximas_queda_sin_evaluar_y_lo_dice(piloto, monkeypatch):
    from apolo.services.tablero_panel import panel

    monkeypatch.setattr(tablero_calor, "_tmax", lambda comp: None)
    e = _ev(piloto)
    assert e["estado"] == "sin_evaluar" and e["causa"] == "sin_tmax" and "T_arriba_C" not in e
    (fila,) = _filas(piloto, "calentamiento del tablero")
    assert fila["estado"] == "aviso"
    p = panel(piloto, "+TAB1")
    calor = next(it for it in p["items"] if it["clave"] == "calentamiento")
    assert calor["severidad"] == "sin_evaluar" and "valor" not in calor  # nunca un número inventado
    assert "T_max_C" not in calor["detalle"] and "T_max_C" in calor["tecnico"]
    assert "T_max_C" not in p["detalle"]["calentamiento"]["motivo"]


def test_una_chapa_sobre_el_techo_lo_cubre():
    chapa = {"type": "create_box", "params": {"name": "Cama", "width": 600, "depth": 300, "height": 4,
                                               "position": {"x": 0, "y": 0, "z": 222}}}
    d = _doc([chapa])
    e = _ev(d)
    assert e["caras"]["techo"]["cubierta"] and e["caras"]["techo"]["fraccion"] == 1.0
    assert e["Ae_m2"] == pytest.approx(0.564 - 0.07, abs=1e-3)  # techo 0,1 m² con b 0,7 en vez de 1,4
    lejos = dict(chapa, params={**chapa["params"], "position": {"x": 0, "y": 0, "z": 300}})
    assert not _ev(_doc([lejos]))["caras"]["techo"]["cubierta"]  # a 98 mm el aire circula


def test_los_prensaestopas_de_la_piloto_y_su_compra(piloto):
    m = modelo(piloto)
    (t,) = ruteos(piloto, m)
    r = tablero_prensas.del_tablero(piloto, m, t)
    por = {p["designacion"]: p for p in r["prensas"]}
    assert set(por) == {"-W1", "-W2", "-W3", "-W4"}  # -W5 va a un mando de la puerta: es interno
    assert por["-W1"]["ref"] == "PRENSA-M16" and por["-W4"]["ref"] == "PRENSA-M20"  # Ø9,8 y Ø11,5
    pts = sorted(p["punto"][0] for p in r["prensas"])
    assert all(b - a >= 19 + 10 - 0.2 for a, b in zip(pts, pts[1:]))  # sin encimarse
    assert all(p["punto"][2] == -200.0 for p in r["prensas"])  # en la cara de abajo (z = −alto/2)
    compra = {f["ref"]: f["cantidad"] for f in filas_bom(piloto) if f["ref"].startswith("PRENSA")}
    assert compra == {"PRENSA-M16": 3, "PRENSA-M20": 1}
    assert not _filas(piloto, "prensaestopas")
    assert "prensaestopas" in {x["regla"] for x in chequeo(piloto)["revisadas"]}


def test_un_cable_que_ningun_prensaestopas_sujeta_es_aviso(piloto, monkeypatch):
    from apolo.library.electrico.prensaestopas import Opcion

    monkeypatch.setattr(tablero_prensas, "opciones", lambda: [Opcion("PRENSA-M40", "M40x1,5", 16, 28, 46)])
    filas = _filas(piloto, "prensaestopas")
    assert {f["elementos"][0] for f in filas} == {"c17", "c18", "c19", "c20"}
    assert all(f["estado"] == "aviso" and "más delgado" in f["detalle"] for f in filas)


def test_un_aparato_de_tablero_fuera_de_la_ubicacion_armada():
    extra = {"type": "add_device", "params": {"ref": "ITM-C6-3P", "designacion": "-F9", "ubicacion": "+TAB2"}}
    d = Document()
    d.execute_many(_acciones()[:-1] + [extra] + _acciones()[-1:])
    (fila,) = _filas(d, "aparato fuera del tablero armado")
    assert fila["estado"] == "aviso" and "-F9" in fila["detalle"] and "+TAB2" in fila["detalle"]
