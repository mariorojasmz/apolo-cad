"""Los puntos de extensión para entregables (plan puntos-de-extension-entregables), con la extensión
FALSA de `tests/ext_prueba/`:

- D1: la superficie de lectura eléctrica en `extensiones_api.MODULOS` (la extensión lee el modelo,
  sus redes, el tablero, los cables de campo, R y X de un conductor y el catálogo);
- D2: `Extension.costeo` suma filas ya costeadas al final del costeo y de la cotización, con su
  `version_costeo`; lo que no cumple no carga, una fila mala no se cobra y lo dice un aviso;
- D3: `Extension.entrega` suma reglas a la puerta de entrega (ROJO, AMARILLO, ok), con su
  `version_entrega` en `version_bateria`; sin extensiones, todo es lo de siempre.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document

EXTRA = "APOLO_EXTENSIONES_EXTRA"
ORIGEN = "extension:ext-prueba"


@pytest.fixture
def cargar(extensiones_aisladas, monkeypatch):
    """`cargar("VARIANTE")` carga `ext_prueba:VARIANTE` y devuelve su estado."""
    def _cargar(variante: str = "EXTENSION") -> dict:
        monkeypatch.setenv(EXTRA, f"ext_prueba:{variante}")
        (e,) = extensiones_aisladas.cargar()
        return e

    return _cargar


def _tablero() -> Document:
    from tablero_electrico import arranque_directo

    d = Document("tablero")
    d.execute_many(arranque_directo())
    return d


def _mesa() -> Document:
    d = Document("mesa")
    d.execute("create_box", {"name": "Tablero", "width": 400, "depth": 300, "height": 20})
    return d


# ── D1: la superficie de lectura eléctrica ───────────────────────────────────────────────────

def test_la_lectura_electrica_esta_declarada_sin_subir_el_contrato():
    from apolo import extensiones, extensiones_api

    M = extensiones_api.MODULOS
    assert {"chequeo", "modelo"} <= set(M["apolo.services.electrico"])
    assert "analizar" in M["apolo.library.electrico.redes"]
    assert {"ModeloElectrico", "Dispositivo", "Conductor", "Cable"} <= set(
        M["apolo.library.electrico.modelo"])
    assert {"ruteos", "largos", "armados"} <= set(M["apolo.services.tablero"])
    assert {"recorridos", "largos"} <= set(M["apolo.services.cables_campo"])
    assert {"resistencia", "reactancia", "r20_ohm_km"} <= set(M["apolo.cosim.red.conductores"])
    assert M["apolo.library.catalog"] == ("CATALOG",)
    assert extensiones.CONTRATO_EXTENSIONES == 1  # agregar nombres no lo sube


def test_la_extension_falsa_lee_el_tablero_por_la_superficie():
    from apolo.cosim.red import conductores as K
    from ext_prueba.electrico import resumen

    d = _tablero()
    r = resumen(d)
    m = d.electrico
    assert r["dispositivos"] == len(m.dispositivos) > 0 and r["conductores"] == len(m.conductores)
    assert r["redes"] > 0 and r["en_catalogo"] == r["dispositivos"]
    con_largo = [c for c in m.conductores if c.seccion_mm2 and c.largo_m]
    assert con_largo  # el tablero de prueba declara 1 m por conductor
    assert r["r_ohm"] == round(sum(K.resistencia(c.seccion_mm2, c.largo_m) for c in con_largo), 6)
    assert r["x_ohm"] == round(sum(K.reactancia(c.largo_m) for c in con_largo), 6)
    assert resumen(_mesa()) == {"dispositivos": 0, "conductores": 0, "redes": 0, "en_catalogo": 0,
                                "r_ohm": 0.0, "x_ohm": 0.0, "tableros": 0, "largos_tablero": 0,
                                "cables_campo": 0}


# ── D2: filas del costeo ─────────────────────────────────────────────────────────────────────

def test_sin_extensiones_el_costeo_es_byte_identico(cargar, extensiones_aisladas):
    from apolo.library import costeo_extension
    from apolo.services.cobros import costeo

    d = _tablero()
    antes = json.dumps(costeo(d))
    assert costeo_extension.DE_EXTENSION == {} and "extensiones_usd" not in antes
    assert cargar()["cargada"]
    con = costeo(d)
    assert json.dumps(con) != antes
    n = len(json.loads(antes)["rows"])
    assert json.dumps(con["rows"][:n]) == json.dumps(json.loads(antes)["rows"])  # al final


def test_las_filas_entran_al_final_ya_costeadas(cargar):
    from apolo.services.cobros import costeo

    d = _tablero()
    sin = costeo(d)
    assert cargar()["cargada"]
    data = costeo(d)
    rev, con = data["rows"][-2:]
    assert rev == {"ref": "prueba.revision", "descripcion": "Revisión de prueba",
                   "categoria": "servicios", "material": "", "norma": "", "cantidad": 1.5,
                   "unidad": "h", "longitud_mm": None, "peso_unitario_kg": None,
                   "peso_total_kg": None, "origen": ORIGEN, "costo_ud_usd": 20.0,
                   "costo_total_usd": 30.0, "costo_fuente": "criterio de prueba (20 USD/h)"}
    n = len(d.electrico.conductores)
    assert con["ref"] == "prueba.conexionado" and con["cantidad"] == n
    assert con["costo_total_usd"] == round(2.0 * n, 2) and con["categoria"] == "mano de obra"
    t, t0 = data["totales"], sin["totales"]
    assert t["extensiones_usd"] == round(30.0 + 2.0 * n, 2)
    assert (t["catalogo_usd"], t["fabricacion_usd"]) == (t0["catalogo_usd"], t0["fabricacion_usd"])
    assert t["total_usd"] == round(t0["total_usd"] + t["extensiones_usd"], 2)
    assert t["por_categoria"]["servicios"] == 30.0
    assert data["extensiones"] == {"ext-prueba": 1}
    assert costeo(_mesa())["rows"][-1]["ref"] == "prueba.revision"  # sin tablero, sin conexionado


def test_la_ruta_y_la_cotizacion_cobran_las_filas_de_la_extension(cargar, monkeypatch):
    from apolo.drawing.quote import quotation_pages
    from apolo.services.cobros import costeo

    assert cargar()["cargada"]
    d = _mesa()
    monkeypatch.setattr(api, "DOC", d)
    c = TestClient(api.app)
    assert c.get("/api/costing.json").json() == json.loads(json.dumps(costeo(d)))
    r = c.get("/api/quote.pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    paginas = quotation_pages(d.scene, costeo=costeo(d), fx=2.0, currency="PEN")
    textos = [lb.text for p in paginas for lb in p.labels]
    assert "Otros conceptos" in textos and "60.00 PEN" in textos  # 30 USD × 2
    assert "1.5 h" in textos  # la cantidad lleva su unidad


def test_sin_filas_de_extension_la_cotizacion_no_cambia():
    from apolo.drawing.quote import quotation_pages
    from apolo.services.cobros import costeo

    d = _mesa()
    textos = [lb.text for p in quotation_pages(d.scene, costeo=costeo(d)) for lb in p.labels]
    assert "Otros conceptos" not in textos


def test_la_version_del_costeo_se_publica(cargar):
    from apolo.services.cobros import costeo

    assert cargar("COSTEO_V3")["cargada"]
    assert costeo(_mesa())["extensiones"] == {"ext-prueba": 3}


def test_una_fila_mala_no_se_cobra_y_lo_dice_un_aviso(cargar):
    from apolo.services.cobros import costeo

    assert cargar("COSTEO_CON_FALLAS")["cargada"]
    data = costeo(_mesa())
    de_ext = [r for r in data["rows"] if r.get("origen") == ORIGEN]
    assert [r["descripcion"] for r in de_ext] == ["Buena"]
    assert data["totales"]["extensiones_usd"] == 1.0
    avisos = [a for a in data["avisos"] if a["tipo"] == "fila de extensión descartada"]
    textos = " | ".join(a["detalle"] for a in avisos)
    assert len(avisos) == 5 and data["monto_en_riesgo_usd"] == 0.0
    for motivo in ("`cantidad` es un número finito > 0, no inf", "sobran descuento",
                   "`costo_unit` es un número finito ≥ 0", "no True",
                   "RuntimeError: la fuente de prueba se rompió"):
        assert motivo in textos, (motivo, textos)
    assert {a["elementos"][0] for a in avisos} == {"prueba.malas", "prueba.lanza"}


@pytest.mark.parametrize(("variante", "motivo"), [
    ("COSTEO_SIN_PREFIJO", "no lleva el prefijo «prueba.»"),
    ("COSTEO_REPETIDO", "«prueba.revision» de costeo ya existe"),
    ("COSTEO_NO_FUENTE", "no es un FuenteCosteo"),
    ("COSTEO_NO_LLAMABLE", "`filas` es una función"),
    ("COSTEO_VERSION_MALA", "version_costeo «0» inválido"),
])
def test_un_costeo_que_no_cumple_no_carga_la_extension(cargar, variante, motivo):
    from apolo.commands.registry import REGISTRY
    from apolo.library import costeo_extension
    from apolo.library.calidad import registro

    e = cargar(variante)
    assert e["cargada"] is False and motivo in e["motivo"], e
    assert costeo_extension.DE_EXTENSION == {} and registro.DE_EXTENSION == {}  # todo o nada
    assert "prueba.hola" not in REGISTRY


# ── D3: reglas de la puerta de entrega ───────────────────────────────────────────────────────

def _entrega(d: Document) -> dict:
    from apolo.library.delivery import delivery_report
    from apolo.services.delivery_inputs import delivery_inputs

    return delivery_report(**delivery_inputs(d, expand=lambda ids: ids))


def test_sin_extensiones_la_puerta_de_entrega_es_identica(cargar, extensiones_aisladas):
    from apolo.services.delivery_inputs import delivery_inputs

    d = _mesa()
    assert "extensiones" not in delivery_inputs(d, expand=lambda ids: ids)
    antes = _entrega(d)
    assert "version_bateria" not in antes
    assert cargar()["cargada"]
    con = _entrega(d)
    assert con["version_bateria"] == "3+ext-prueba.1"
    assert con["resumen"]["chequeos_ok"] == [*antes["resumen"]["chequeos_ok"],
                                             "Nota de entrega de prueba"]
    assert {k: v for k, v in con.items() if k not in ("resumen", "version_bateria")} == \
        {k: v for k, v in antes.items() if k != "resumen"}


def test_una_regla_pone_el_semaforo_en_rojo_por_la_ruta(cargar, monkeypatch):
    assert cargar()["cargada"]
    d = _mesa()
    monkeypatch.setattr(api, "DOC", d)
    c = TestClient(api.app)
    out = c.post("/api/delivery-check", json={}).json()
    assert out["version_bateria"] == "3+ext-prueba.1"
    assert "extensiones" in out["tiempos_s"]["por_regla"]
    assert not [b for b in out["bloqueantes"] if b.get("origen") == ORIGEN]
    d.ext["ext-prueba"] = {"bloquea_entrega": True}
    out = c.post("/api/delivery-check", json={}).json()
    (b,) = [b for b in out["bloqueantes"] if b.get("origen") == ORIGEN]
    assert out["veredicto"] == "ROJO"
    assert b == {"regla": "Nota de entrega de prueba", "id": "prueba.nota_entrega",
                 "origen": ORIGEN, "piezas": [f"Tablero ({sorted(d.scene)[0]})"],
                 "detalle": "la nota de prueba pide bloquear la entrega"}
    d.ext["ext-prueba"] = {"avisa_entrega": True}
    out = c.post("/api/delivery-check", json={}).json()
    assert [a["id"] for a in out["avisos"] if a.get("origen") == ORIGEN] == ["prueba.nota_entrega"]
    assert "Nota de entrega de prueba" not in out["resumen"]["chequeos_ok"]


def test_una_regla_que_no_aplica_no_aparece_y_con_tablero_lee_lo_electrico(cargar):
    assert cargar()["cargada"]
    assert "Tablero de prueba leído" not in _entrega(_mesa())["resumen"]["chequeos_ok"]
    assert "Tablero de prueba leído" in _entrega(_tablero())["resumen"]["chequeos_ok"]


def test_una_regla_rota_queda_sin_verificar_nunca_verde(cargar):
    assert cargar("ENTREGA_ROTA")["cargada"]
    out = _entrega(_mesa())
    rotas = {a["id"]: a["detalle"] for a in out["avisos"] if a.get("origen") == ORIGEN}
    assert set(rotas) == {"prueba.lanza", "prueba.rara"} and out["veredicto"] != "VERDE"
    assert "RuntimeError: la regla de prueba se rompió" in rotas["prueba.lanza"]
    assert "un hallazgo es" in rotas["prueba.rara"]
    assert all("no cuenta como verde" in t for t in rotas.values())


def test_la_version_de_la_entrega_sube_la_de_la_bateria(cargar):
    assert cargar("ENTREGA_V2")["cargada"]
    assert _entrega(_mesa())["version_bateria"] == "3+ext-prueba.2"


def test_la_puerta_de_publicacion_lee_la_misma_entrega(cargar):
    from apolo.services.puerta_publicacion import reunir

    assert cargar()["cargada"]
    d = _mesa()
    d.ext["ext-prueba"] = {"bloquea_entrega": True}
    entrega = reunir(d, expand=lambda ids: ids, gravedad={"resultado": None, "motivo": "test"})["entrega"]
    assert entrega["veredicto"] == "ROJO"
    assert any(b.get("id") == "prueba.nota_entrega" for b in entrega["bloqueantes"])


@pytest.mark.parametrize(("variante", "motivo"), [
    ("ENTREGA_SIN_PREFIJO", "no lleva el prefijo «prueba.»"),
    ("ENTREGA_REPETIDA", "«prueba.nota_entrega» de entrega ya existe"),
    ("ENTREGA_SIN_TITULO", "no tiene título"),
    ("ENTREGA_NO_REGLA", "no es un ReglaEntrega"),
    ("ENTREGA_VERSION_MALA", "version_entrega «True» inválido"),
])
def test_una_entrega_que_no_cumple_no_carga_la_extension(cargar, variante, motivo):
    from apolo.library import costeo_extension, entrega_extension

    e = cargar(variante)
    assert e["cargada"] is False and motivo in e["motivo"], e
    assert entrega_extension.DE_EXTENSION == {} and costeo_extension.DE_EXTENSION == {}


def test_al_salir_los_registros_quedan_como_estaban(monkeypatch):
    from apolo import extensiones
    from apolo.library import costeo_extension, entrega_extension

    monkeypatch.delenv("APOLO_EXTENSIONES", raising=False)
    monkeypatch.setenv(EXTRA, "ext_prueba:EXTENSION")
    with extensiones.aislado():
        assert extensiones.cargar()[0]["cargada"]
        assert costeo_extension.DE_EXTENSION and entrega_extension.DE_EXTENSION
    assert costeo_extension.DE_EXTENSION == {} and entrega_extension.DE_EXTENSION == {}
