"""El panel «Neumática» del visor (plan V8.9 D12, F6): `services/neumatica_panel.py` y su ruta.

Sobre el banco del empujador de la F3 (`neumatica_escena.py`: FRL → corte con escape → 5/2
monoestable → Ø32 con empujador, ligado a su pieza):
  - sin aire, `{"hay_aire": false}` (el panel muestra su estado vacío);
  - el veredicto y los ítems salen del ERC y de la memoria del aire, en palabras de la persona
    (sin comandos, con coma decimal), con las piezas del cilindro para el vuelo de la cámara;
  - el detalle por cilindro trae fuerza, consumo y tiempo de carrera de la memoria;
  - el esquema es la lámina de la F5 recortada, con los símbolos, las cajas de cada posición de
    cada válvula y la señal de presión de cada línea;
  - la sesión viva ofrece las electroválvulas con su accionamiento manual (`valvulas` del inicio).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from neumatica_escena import empujador

from apolo.api import main as api
from apolo.doc.document import Document
from apolo.services import neumatica_panel as P
from apolo.services.neumatica_vista import _presion

SERVICIO = {"carrera_mm": 200, "velocidad_m_s": 0.5, "masa_kg": 2.0, "fuerza_N": 50, "ciclos_min": 20}


@pytest.fixture(scope="module")
def banco():
    return empujador(servicio=SERVICIO)


@pytest.fixture(scope="module")
def panel(banco):
    return P.panel(banco[0])


def test_sin_aire_el_panel_dice_que_no_hay(monkeypatch):
    api.DOC = Document("vacío")
    r = TestClient(api.app).get("/api/neumatica")
    assert r.status_code == 200 and r.json() == {"hay_aire": False}


def test_la_ruta_da_lo_mismo_que_el_servicio(banco, panel):
    api.DOC = banco[0]
    r = TestClient(api.app).get("/api/neumatica")
    assert r.status_code == 200
    assert r.json()["veredicto"] == panel["veredicto"] and len(r.json()["items"]) == len(panel["items"])


def test_veredicto_e_items_en_palabras_de_la_persona(panel):
    v = panel["veredicto"]
    assert panel["hay_aire"] is True and v["frase"] and v["nota"].startswith("Revisamos ")
    frases = [it["frase"] for it in panel["items"]]
    # sin fugas declaradas, la demanda va sin ellas: lo único que queda por revisar
    assert "Faltan las fugas de la red de aire" in frases
    assert v == {**P.veredicto(panel["items"], P.FRASE_BIEN, P.FRASE_PARCIAL), "nota": v["nota"]}
    for it in panel["items"]:
        texto = it["frase"] + " " + (it.get("detalle") or "")
        assert "`" not in texto and "add_" not in texto and "servicio." not in texto, texto
        assert not any(c.isdigit() and n == "." and m.isdigit() for c, n, m in zip(texto, texto[1:], texto[2:])), texto


def test_un_vastago_que_pandea_dice_sus_cifras_y_señala_el_cilindro(banco):
    d, cid = empujador(servicio={**SERVICIO, "largo_libre_mm": 1500})
    p = P.panel(d)
    # el cilindro por su función, en minúscula de frase (nombres-por-funcion F5b): nunca «de -MM1»,
    # ni por la parte de su pieza («Cilindro · Cuerpo» es el cilindro, no «el cuerpo»)
    it = next(i for i in p["items"] if i["frase"].startswith("El vástago del cilindro (-MM1) pandea"))
    assert not any("cuerpo (-MM1)" in i["frase"].lower() for i in p["items"])
    assert it["severidad"] == "falla" and " contra " in it["frase"]
    assert it["piezas"][0] == f"{cid}_cuerpo" and f"{cid}_vastago" in it["piezas"]
    assert it["tecnico"] and "FS" in it["tecnico"]
    assert sum(1 for i in p["items"] if "pandea" in i["frase"]) == 1  # el del ERC no se repite
    assert "corregir" in p["veredicto"]["frase"] and p["veredicto"]["severidad"] == "falla"


def test_el_aviso_de_esbeltez_sin_fy_no_dice_que_pandea():
    """Un vástago corto sin fy sale AVISO (λ < LAMBDA_SIN_FY): con FS 109 el panel decía «pandea»."""
    fila = {"regla": "pandeo del vástago", "estado": "aviso", "elementos": ["-MM1"],
            "valor": {"F_adm_N": 9000.0, "F_N": 250.0, "fs": 109.0, "lambda": 45.0, "largo_mm": 60}}
    frase, detalle = P._frase_memoria(fila)
    assert "pandea" not in frase and frase == "Falta el límite elástico del vástago de -MM1"
    assert "109" in detalle and "45" in detalle
    frase_error, _ = P._frase_memoria({**fila, "estado": "error", "valor": {**fila["valor"], "fs": 1.7}})
    assert frase_error.startswith("El vástago de -MM1 pandea")
    # con los nombres del documento, el cilindro por su función y en minúscula de frase (F5b)
    nom = {"-MM1": "cilindro de compuerta (-MM1)"}

    def nombrar(des, prep=""):
        return {"de": "del ", "a": "al ", "": "el "}[prep] + nom[des]

    assert P._frase_memoria(fila, nombrar)[0] == "Falta el límite elástico del vástago del cilindro de compuerta (-MM1)"
    energia = {"regla": "energía al fin de carrera", "estado": "aviso", "elementos": ["-MM1"],
               "valor": {"E_J": 2.0, "E_adm_J": 1.0, "v_m_s": 0.5}}
    assert P._frase_memoria(energia, nombrar)[0].startswith("El cilindro de compuerta (-MM1) llega a 0,50")


def test_el_detalle_por_cilindro(panel, banco):
    _d, cid = banco
    (c,) = panel["detalle"]["cilindros"]
    assert c["designacion"] == "-MM1" and c["carrera_mm"] == 200 and c["piezas"][0] == f"{cid}_cuerpo"
    assert c["fuerza"]["F_avance_N"] == pytest.approx(482.5, abs=1.0)   # p·A a 6 bar, Ø32
    assert c["fuerza"]["F_retroceso_N"] < c["fuerza"]["F_avance_N"]
    assert c["consumo"]["ciclo_NL"] > 1.5 and c["consumo"]["ciclos_min"] == 20
    assert c["consumo"]["NL_min"] == pytest.approx(20 * c["consumo"]["ciclo_NL"], rel=1e-6)
    assert c["tiempo"]["origen"] == "estimado" and c["tiempo"]["avance_s"] > 0
    assert panel["detalle"]["maquina"]["NL_min"] > 0


def test_el_esquema_recortado_con_simbolos_valvulas_y_lineas(panel, banco):
    _d, cid = banco
    e = panel["esquema"]
    assert "error" not in e and e["vista"][2] > 50 and e["vista"][3] > 50
    textos = [t["texto"] for t in e["textos"]]
    assert {"-MM1", "-QM2", "-AZ1", "-QM1"} <= set(textos)
    assert not any("ESQUEMA NEUM" in t for t in textos)   # sin el título, las notas ni el cajetín
    assert "Toma de aire" in textos                         # la fuente entra al recorte, con su símbolo
    x, y, w, h = e["vista"]
    assert any(c[1] > y + 0.8 * h for c in e["circulos"])   # el círculo de la fuente, abajo de todo
    sim = {s["designacion"]: s for s in e["simbolos"]}
    assert sim["-MM1"]["piezas"][0] == f"{cid}_cuerpo" and sim["-QM2"]["piezas"] == []
    # lo que es cada aparato, con unidades; los rótulos de 2 mm de la lámina quedan como detalle
    assert sim["-MM1"]["rotulo"] == "Cilindro Ø32 mm, vástago 12 mm, carrera 200 mm"
    assert sim["-QM2"]["rotulo"] == "Válvula 5/2 monoestable" and sim["-QM2"]["bornes"] == ["A1: +TAB1-S2:14"]
    clases = {t["texto"]: t["clase"] for t in e["textos"]}
    assert clases["-MM1"] == clases["Toma de aire"] == "rotulo" and clases["5/2 monoestable"] == "detalle"
    x, y, w, h = e["vista"]
    for s in sim.values():   # cada símbolo cae dentro de lo que se ve
        sx, sy, sw, sh = s["caja"]
        assert x <= sx and sx + sw <= x + w and y <= sy and sy + sh <= y + h
    val = {v["designacion"]: v for v in e["valvulas"]}
    assert val["-QM2"]["senal"] == "-QM2.posicion" and set(val["-QM2"]["cajas"]) == {"14", "12"}
    assert val["-QM1"]["senal"] == "-QM1.abierta" and set(val["-QM1"]["cajas"]) == {"abierta", "cerrada"}
    c14, c12 = val["-QM2"]["cajas"]["14"], val["-QM2"]["cajas"]["12"]
    assert c14[0] < c12[0] and c14[1] == c12[1]   # la del mando a la izquierda de la de reposo
    pres = {tuple(sorted(ln["puertos"])): ln["presion"] for ln in e["lineas"]}
    assert pres[("-MM1:A", "-QM2:4")] == {"senal": "-MM1.pA_bar"}
    assert pres[("-MM1:B", "-QM2:2")] == {"senal": "-MM1.pB_bar"}
    assert pres[("-AZ1:2", "-QM1:1")] == {"senal": "-AZ1.p_bar"}
    assert pres[("-QM1:2", "-QM2:1")] == {"senal": "-AZ1.p_bar", "si": "-QM1.abierta"}
    assert all(ln["tramos"] for ln in e["lineas"]) and e["escala_bar"] == 6.0
    toma = next(ln for ln in e["lineas"] if ln["id"] == "toma")   # la toma, a la presión de la red
    assert toma["presion"] == {"senal": "-AZ1.p_red_bar"} and toma["puertos"] == ["-AZ1:1"]


def _ap(tipo: str, **modelo):
    return SimpleNamespace(neumatico=SimpleNamespace(tipo=tipo, modelo=modelo))


def test_la_presion_de_una_via_de_trabajo_que_pasa_por_un_regulador():
    aparatos = {"-AZ1": _ap("frl"), "-QM2": _ap("valvula", vias=5, posiciones=2, mando="monoestable"),
                "-RZ1": _ap("regulador_caudal"), "-MM1": _ap("cilindro"), "-WP1": _ap("silenciador")}
    lineas = {"P1": {"puertos": ["-AZ1:2", "-QM2:1"]}, "P2": {"puertos": ["-QM2:4", "-RZ1:1"]},
              "P3": {"puertos": ["-RZ1:2", "-MM1:A"]}, "P4": {"puertos": ["-QM2:5", "-WP1:1"]}}
    linea_de = {p: k for k, ln in lineas.items() for p in ln["puertos"]}
    p2 = _presion(lineas["P2"]["puertos"], linea_de, lineas, aparatos)
    assert p2 == {"valvula": "-QM2", "tabla": {"14": "1", "12": "5"}, "alimentacion": {"senal": "-AZ1.p_bar"}}
    assert _presion(lineas["P3"]["puertos"], linea_de, lineas, aparatos) == {"senal": "-MM1.pA_bar"}
    assert _presion(lineas["P4"]["puertos"], linea_de, lineas, aparatos) == {"atmosfera": True}
    assert _presion(["-XX:1", "-YY:2"], linea_de, lineas, aparatos) == {}


def test_cifras_como_las_de_la_ui():
    assert P.n(1799.4, 0, "rpm") == "1 799 rpm" and P.n(0.287, 2, "J") == "0,29 J"
    assert P.fuerza(2400) == "2,4 kN" and P.fuerza(483.2) == "483 N"
    assert P.limpio("`servicio` de 1.5 m/s") == "servicio de 1,5 m/s"


def test_la_sesion_viva_ofrece_las_valvulas_y_su_accionamiento_manual(banco):
    pytest.importorskip("mujoco")
    from neumatica_escena import escenario

    from apolo.cosim.vivo import Vivo, escenario_vivo
    from apolo.services.cosim_snapshot import snapshot_cosim

    d, cid = banco
    v = Vivo(snapshot_cosim(d, escenario_vivo(escenario(cid, pulsar_s=0))))
    tabla = v.fot.tabla()
    assert tabla["valvulas"] == [{"designacion": "-QM2", "ref": "VAL-52-MONO-G18", "lados": ["14"], "manual": True}]
    cil = next(x for x in tabla["dispositivos"] if x["designacion"] == "-MM1")
    assert cil["carrera_mm"] == 200.0   # la nominal: la lectura no pasa del tope blando
    v.recibir({"accion": "accionar_manual", "dispositivo": "-QM2", "valor": "14"})
    v.avanzar(30)
    _nuevas, valores = v.fot.reunir()
    assert valores["-AZ1.p_red_bar"] == pytest.approx(6.0)   # la red en la entrada del FRL
    textos = v.fot.textos_cambiados()
    assert textos.get("-QM2.posicion") == "14" and textos.get("-QM2.manual") == "14"   # una fuente
