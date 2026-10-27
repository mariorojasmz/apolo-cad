"""Panel «Pruebas» del visor (plan visor-para-evaluar D1–D4): cada escenario con su semáforo, la
fecha y el balance; el resumen arriba («1 de 4 pasan · 1 falla · 1 vencido · 1 sin correr»); al
abrir uno, lo que falló con su cifra y el producto trabado con su lugar (la pieza cercana) y su
hora. Sin correr la co-simulación: los resultados se escriben como los dejaría una corrida."""

from __future__ import annotations

from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.services import escenarios as E
from apolo.services.pruebas_panel import resumen


def _esc(desc: str = "") -> dict:
    return {"duracion_s": 5, "aserciones": ["flujo.cuadra al_final"], **({"descripcion": desc} if desc else {})}


def _resultado(doc, nombre, veredicto, flujo=None, firma=None):
    filas = [{"asercion": "flujo.cuadra al_final", "pasa": veredicto == "pasa",
              "detalle": "al final vale falso" if veredicto != "pasa" else "al final vale verdadero"}]
    ver = {"veredicto": veredicto, "aserciones": filas, "n_fallidas": int(veredicto != "pasa")}
    res = {"resumen": {"huella": "h", "duracion_s": 5.0, "factor_tiempo_real": 0.5},
           **({"mecanica": {"flujo": flujo}} if flujo else {})}
    comp = E.resultado_compacto(ver, res, firma=firma or E.firma_documento(doc),
                                hash_esc=E.hash_escenario(doc.escenarios[nombre]["escenario"]), simulacion="s1")
    assert E.guardar_resultado(doc, nombre, comp)


TRABADO = {"entraron": 12, "salieron": 11, "por_sumidero": {"rampa": 11},
           "trabados": [{"producto": "caja 3", "pos_mm": [100.0, 0.0, 40.0], "desde_s": 12.4}],
           "perdidos": [], "retenidos": [], "sin_entrar": []}


def _doc() -> Document:
    doc = Document("pruebas")
    doc.execute("create_box", {"name": "Banda", "width": 2000, "depth": 400, "height": 20})
    for n in ("marcha", "atasco", "vieja", "nueva"):
        doc.escenarios[n] = {"escenario": _esc("la caja entra y sale" if n == "marcha" else "")}
    _resultado(doc, "marcha", "pasa", flujo={**TRABADO, "trabados": [], "salieron": 12, "por_sumidero": {"rampa": 12}})
    _resultado(doc, "atasco", "falla", flujo=TRABADO)
    _resultado(doc, "vieja", "pasa", firma="2:otra-maquina")
    return doc


def test_resumen():
    assert resumen(["pasa"] * 15 + ["vencido"]) == "15 de 16 pasan · 1 vencido"
    assert resumen(["pasa"]) == "1 de 1 pasa"
    assert resumen(["falla", "falla", "sin_correr"]) == "0 de 3 pasan · 2 fallan · 1 sin correr"


def test_el_panel_dice_el_veredicto_y_cada_prueba_con_su_semaforo():
    api.DOC = _doc()
    out = TestClient(api.app).get("/api/pruebas").json()
    assert out["veredicto"] == {"severidad": "falla", "frase": "1 de 4 pasan · 1 falla · 1 vencido · 1 sin correr"}
    filas = {f["nombre"]: f for f in out["escenarios"]}
    assert [f["nombre"] for f in out["escenarios"]] == ["atasco", "vieja", "nueva", "marcha"]  # lo grave primero
    assert filas["marcha"]["severidad"] == "bien" and filas["marcha"]["rotulo"] == "Pasa"
    assert filas["marcha"]["balance"] == "12 entraron · 12 rampa · 0 trabados"
    assert filas["marcha"]["descripcion"] == "la caja entra y sale"
    assert filas["marcha"]["estimado_s"] == 10.0 and filas["marcha"]["fecha"]
    assert filas["atasco"]["severidad"] == "falla" and filas["atasco"]["n_fallidas"] == 1
    assert filas["vieja"]["severidad"] == "aviso" and filas["vieja"]["ultimo"] == "Pasa"
    assert "la máquina cambió" in filas["vieja"]["motivo"]
    assert filas["nueva"] == {"nombre": "nueva", "estado": "sin_correr", "rotulo": "Sin correr", "severidad": "sin_evaluar"}


def test_abrir_una_prueba_da_lo_que_fallo_y_el_producto_con_lugar_y_hora():
    api.DOC = _doc()
    c = TestClient(api.app)
    d = c.get("/api/pruebas/atasco").json()
    assert d["fallidas"] == [{"asercion": "flujo.cuadra al_final", "cifra": "al final vale falso"}]
    inc = d["incidencias"]
    assert len(inc) == 1
    assert inc[0]["producto"] == "caja 3" and inc[0]["que"] == "trabado" and inc[0]["hora_s"] == 12.4
    assert inc[0]["cerca_de"] == "Banda" and inc[0]["pieza"] in api.DOC.scene and inc[0]["punto_mm"] == [100, 0, 40]
    assert c.get("/api/pruebas/marcha").json()["incidencias"] == []
    r = c.get("/api/pruebas/marchaa")
    assert r.status_code == 404 and "marcha" in r.json()["detail"]


def test_sin_escenarios_el_panel_esta_vacio():
    api.DOC = Document("vacio")
    assert TestClient(api.app).get("/api/pruebas").json() == {"veredicto": None, "escenarios": []}
