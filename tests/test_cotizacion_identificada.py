"""La cotización dice a quién va y qué incluye (plan cotizacion-identificada-y-ajustes-por-escenario,
F1: D1–D4), con la extensión FALSA de `tests/ext_prueba/`:

- D1: el metadato `comercial` (titulo, cliente, numero, revision) del manifest: se valida al poner,
  viaja en el `.apolo` (sólo si hay) y la cotización lo usa en el título, el bloque «Cliente / Nº /
  Rev.» y el número; sin él, el nombre del proyecto sin «(copia)» y sin bloque;
- D2: una `IdentificacionCosteo` de extensión cuando el proyecto no la trae; la fuente al pie,
  con su rótulo legible (`rotulo`; sin él, el id; el del proyecto: «datos comerciales del
  proyecto»);
- D3: `acota` reemplaza `nucleo.alcance` o `nucleo.validez` en su lugar; acotar una de honestidad,
  sin nota, una inventada o dos veces la misma no carga la extensión;
- D4: con filas de pruebas o puesta en marcha el alcance deja de decir «ni puesta en marcha».

Sin nada de esto, la hoja es la de siempre: lo congela `test_cotizacion_notas.py`.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document

EXTRA = "APOLO_EXTENSIONES_EXTRA"
META = {"date": "2026-10-25", "revisions": []}
ALCANCE_DE_SIEMPRE = "No incluye transporte, instalación ni puesta en marcha, salvo pacto expreso."


@pytest.fixture
def cargar(extensiones_aisladas, monkeypatch):
    def _cargar(*variantes: str) -> list[dict]:
        monkeypatch.setenv(EXTRA, ",".join(f"ext_prueba:{v}" for v in variantes))
        return extensiones_aisladas.cargar()

    return _cargar


def _doc(nombre: str = "faja 4m (copia) (copia)") -> Document:
    d = Document(nombre)
    d.execute("create_box", {"name": "Tablero", "width": 400, "depth": 300, "height": 20})
    return d


def _paginas(d: Document):
    from apolo.drawing.quote import quotation_pages
    from apolo.services.cobros import costeo
    from apolo.services.identificacion import identificacion

    return quotation_pages(d.scene, project_name=d.name, costeo=costeo(d), meta=META,
                           identificacion=identificacion(d))


def _textos(pagina) -> list[str]:
    return [lb.text for lb in pagina.labels]


def _notas(pagina) -> str:
    """Las notas del resumen, unidas (las del núcleo se parten a 60 caracteres)."""
    from apolo.drawing.quote import _NOTAS_Y

    return " ".join(lb.text for lb in pagina.labels if lb.x == 18 and lb.y < _NOTAS_Y)


# ── D1: el metadato y su validación ─────────────────────────────────────────────────────────

def test_titulo_limpio_quita_los_sufijos_copia():
    from apolo.library.comercial import titulo_limpio

    assert titulo_limpio("faja 4m (copia) (copia)") == "faja 4m"
    assert titulo_limpio("Mesa (Copia)") == "Mesa"
    assert titulo_limpio("Copia de seguridad") == "Copia de seguridad"
    assert titulo_limpio("(copia)") == titulo_limpio("") == "Sin título"


def test_normalizar_valida_y_limpia():
    from apolo.library.comercial import TEXTO_MAX, normalizar

    assert normalizar({"cliente": "  ACME  ", "numero": 125, "revision": "", "titulo": None}) == {
        "cliente": "ACME", "numero": "125"}
    assert normalizar({}) == {} and normalizar(None) == {}
    for malo, motivo in (({"cliente": "x", "ruc": "1"}, "campos desconocidos en `comercial`: ruc"),
                         ({"cliente": "a\nb"}, "una sola línea"),
                         ({"numero": ["1"]}, "es un texto"),
                         ({"titulo": "x" * (TEXTO_MAX + 1)}, "máximo"),
                         ("ACME", "es un objeto")):
        with pytest.raises(ValueError, match=motivo):
            normalizar(malo)


def test_el_metadato_viaja_en_el_apolo_solo_si_hay():
    from apolo.services.identificacion import poner_comercial

    d = _doc()
    manifest = json.loads(zipfile.ZipFile(io.BytesIO(d.to_apolo_bytes())).read("manifest.json"))
    assert "comercial" not in manifest  # sin identificación, el manifest de siempre
    poner_comercial(d, {"cliente": "ACME S.A.C.", "numero": "COT-2026-014", "revision": "B"})
    otro = Document.from_apolo_bytes(d.to_apolo_bytes())
    assert otro.comercial == {"cliente": "ACME S.A.C.", "numero": "COT-2026-014", "revision": "B"}
    # un .apolo viejo (sin el campo) carga igual, sin identificación
    assert Document.from_apolo_bytes(_doc().to_apolo_bytes()).comercial == {}


def test_poner_comercial_no_toca_nada_si_no_valida():
    from apolo.services.identificacion import poner_comercial

    d = _doc()
    poner_comercial(d, {"cliente": "ACME"})
    with pytest.raises(ValueError):
        poner_comercial(d, {"cliente": "ACME", "telefono": "1"})
    assert d.comercial == {"cliente": "ACME"}
    assert poner_comercial(d, {}) == {} and d.comercial == {}


# ── D1: la hoja de resumen ───────────────────────────────────────────────────────────────────

def test_sin_identificacion_titulo_limpio_y_sin_bloque():
    resumen = _paginas(_doc())[0]
    textos = _textos(resumen)
    assert "faja 4m" in textos and not any("(copia)" in t for t in textos)
    assert not any(t.startswith(("Cliente:", "Nº ", "identificación:")) for t in textos)
    assert "N° COT-001" in textos  # el número de siempre


def test_con_identificacion_del_proyecto_titulo_bloque_numero_y_fuente():
    from apolo.services.identificacion import poner_comercial

    d = _doc()
    poner_comercial(d, {"titulo": "Faja de paquetería 4 m", "cliente": "ACME S.A.C.",
                        "numero": "COT-2026-014", "revision": "B"})
    paginas = _paginas(d)
    textos = _textos(paginas[0])
    assert "Faja de paquetería 4 m" in textos and "faja 4m" not in textos
    assert "Cliente: ACME S.A.C." in textos and "Nº COT-2026-014 · Rev. B" in textos
    assert "N° COT-2026-014" in textos  # el número de la cotización, también en el cajetín
    pie_txt = "identificación: datos comerciales del proyecto"
    assert pie_txt in textos and "identificación: proyecto" not in textos
    pie = next(lb for lb in paginas[0].labels if lb.text == pie_txt)
    assert pie.y < 10  # bajo el marco, fuera de las notas y del cajetín
    # el desglose baja: el bloque no pisa el rótulo
    ys = {lb.text: lb.y for lb in paginas[0].labels}
    assert ys["Nº COT-2026-014 · Rev. B"] > ys["DESGLOSE POR CATEGORÍA"]
    assert all("COT-2026-014" in " ".join(_textos(p)) for p in paginas)  # cajetín de cada hoja


def test_un_titulo_largo_no_se_recorta():
    from apolo.services.identificacion import poner_comercial

    d = _doc()
    largo = "Transportador de banda para paquetería con tablero y variador, rev. obra"
    poner_comercial(d, {"titulo": largo})
    lb = next(lb for lb in _paginas(d)[0].labels if lb.text == largo)
    assert lb.size < 4.6


def test_la_api_pone_y_lee_la_identificacion(monkeypatch):
    d = _doc()
    monkeypatch.setattr(api, "DOC", d)
    c = TestClient(api.app)
    assert c.get("/api/requirements").json() == {"requirements": {}}  # sin ella, lo de siempre
    r = c.put("/api/project/comercial", json={"cliente": "ACME", "numero": "N-1"})
    assert r.status_code == 200 and r.json()["comercial"] == {"cliente": "ACME", "numero": "N-1"}
    js = c.get("/api/project/comercial").json()
    assert js["efectiva"] == {"cliente": "ACME", "numero": "N-1", "fuente": "proyecto",
                              "fuente_rotulo": "datos comerciales del proyecto"}
    r = c.put("/api/project/comercial", json={"cliente": "ACME", "ruc": "1"})
    assert r.status_code == 400 and "ruc" in r.json()["detail"]
    assert d.comercial == {"cliente": "ACME", "numero": "N-1"}  # el 400 no tocó nada
    # set_requirements: la llamada vieja no cambia; con `comercial` sola no toca los requisitos
    r = c.put("/api/requirements", json={"fields": {"carga_kg": 15}})
    assert r.json()["ok"] and set(r.json()) == {"ok", "requirements"}
    r = c.put("/api/requirements", json={"comercial": {"cliente": "Otro"}})
    assert r.json()["comercial"] == {"cliente": "Otro"} and d.requirements.get("carga_kg") == 15
    assert c.get("/api/requirements").json()["comercial"] == {"cliente": "Otro"}
    r = c.put("/api/requirements", json={"fields": {}, "comercial": {"x": 1}})
    assert r.status_code == 400 and d.requirements.get("carga_kg") == 15  # nada a medias
    assert c.get("/api/quote.pdf").content.startswith(b"%PDF")


def test_la_tool_set_requirements_acepta_comercial(monkeypatch):
    import apolo.mcp_server as srv

    vistos = []

    class _R:
        def json(self):
            return {"ok": True}

    def _api(metodo, ruta, **kw):
        vistos.append((metodo, ruta, kw.get("json")))
        return _R()

    monkeypatch.setattr(srv, "_api", _api)
    srv.set_requirements({"carga_kg": 15})
    srv.set_requirements(comercial={"cliente": "ACME"})
    assert vistos == [("PUT", "/api/requirements", {"fields": {"carga_kg": 15}}),
                      ("PUT", "/api/requirements", {"comercial": {"cliente": "ACME"}})]
    assert "error" in json.loads(srv.set_requirements())  # sin nada no borra los requisitos
    assert len(vistos) == 2


# ── D2: la identificación de una extensión ───────────────────────────────────────────────────

def test_la_identificacion_de_la_extension_y_su_precedencia(cargar):
    from apolo.services.identificacion import identificacion, poner_comercial

    (e,) = cargar("COSTEO_IDENTIFICADA")
    assert e["cargada"], e
    d = _doc()
    assert identificacion(d) == {"cliente": "Cliente de la extensión", "numero": "EXT-0007",
                                 "fuente": "prueba.cliente", "fuente_rotulo": "prueba.cliente"}
    textos = _textos(_paginas(d)[0])
    assert "faja 4m" in textos  # la extensión no trae título: el nombre limpio
    assert "Cliente: Cliente de la extensión" in textos and "N° EXT-0007" in textos
    assert "identificación: prueba.cliente" in textos  # sin `rotulo`, el id como antes
    poner_comercial(d, {"cliente": "ACME"})  # gana el proyecto, entero
    assert identificacion(d) == {"cliente": "ACME", "fuente": "proyecto",
                                 "fuente_rotulo": "datos comerciales del proyecto"}
    assert identificacion(_doc("mesa")) == {"fuente": "nombre"}  # la extensión no tiene: None


def test_el_pie_dice_el_rotulo_de_la_extension(cargar):
    from apolo.services.identificacion import identificacion
    from ext_prueba.costeo import ROTULO

    (e,) = cargar("COSTEO_IDENTIFICADA_CON_ROTULO")
    assert e["cargada"], e
    d = _doc()
    ident = identificacion(d)
    assert ident["fuente"] == "prueba.cliente" and ident["fuente_rotulo"] == ROTULO
    textos = _textos(_paginas(d)[0])
    assert f"identificación: {ROTULO}" in textos
    assert not any("prueba.cliente" in t for t in textos)  # el id crudo no sale en el papel


def test_una_identificacion_que_lanza_o_no_valida_se_salta(cargar):
    from apolo.services.identificacion import identificacion

    (e,) = cargar("COSTEO_IDENTIFICACION_ROTA")
    assert e["cargada"], e
    assert identificacion(_doc())["fuente"] == "prueba.cliente"


# ── D3 y D4: notas con id, acotar y el alcance calculado ─────────────────────────────────────

def test_texto_alcance():
    from apolo.drawing.quote import texto_alcance

    assert texto_alcance() == ALCANCE_DE_SIEMPRE
    assert texto_alcance(("pruebas",)) == ("No incluye transporte ni instalación, salvo pacto "
                                           "expreso. En las partidas: las pruebas de marcha.")
    assert texto_alcance(("puesta_en_marcha", "pruebas")) == (
        "No incluye transporte ni instalación, salvo pacto expreso. En las partidas: la puesta en "
        "marcha.")
    assert texto_alcance(("transporte", "instalacion", "puesta_en_marcha")) == (
        "En las partidas: el transporte, la instalación y la puesta en marcha.")


def test_las_notas_del_nucleo_tienen_id_en_su_orden():
    from apolo.drawing.quote import _notas_nucleo
    from apolo.library.costeo_extension import NOTAS_NUCLEO

    ids = [i for i, _ in _notas_nucleo(3, "fx", [{"tipo": "x"}])]
    assert tuple(ids) == NOTAS_NUCLEO
    assert [i for i, _ in _notas_nucleo(3, None, None)] == [
        "nucleo.referenciales", "nucleo.detalle", "nucleo.alcance", "nucleo.validez"]


def test_validez_acotada_en_su_lugar_y_alcance_calculado(cargar):
    from apolo.services.cobros import costeo
    from ext_prueba.costeo import NOTA_REVISION, NOTA_VALIDEZ

    (e,) = cargar("COSTEO_IDENTIFICADA")
    assert e["cargada"], e
    d = _doc()
    data = costeo(d)
    assert data["incluye"] == ["pruebas"]
    assert {n["fuente"]: n.get("acota") for n in data["notas"]} == {
        "prueba.revision": None, "prueba.validez": "nucleo.validez"}
    notas = _notas(_paginas(d)[0])
    assert f"4. {NOTA_VALIDEZ}" in notas and "15 días" not in notas  # en su lugar
    assert f"5. {NOTA_REVISION}" in notas  # la de la extensión, detrás
    assert "ni puesta en marcha" not in notas and "las pruebas de marcha" in notas
    assert notas.startswith("1. Precios de catálogo REFERENCIALES")  # honestidad intacta


def test_acotar_el_alcance_gana_al_calculado(cargar):
    from ext_prueba.costeo import NOTA_ALCANCE

    (e,) = cargar("COSTEO_ACOTA_ALCANCE")
    assert e["cargada"], e
    notas = _notas(_paginas(_doc())[0])
    assert f"3. {NOTA_ALCANCE}" in notas and "pruebas de marcha" not in notas
    assert "4. Validez de la oferta: 15 días calendario." in notas


@pytest.mark.parametrize(("variante", "motivo"), [
    ("ACOTA_HONESTIDAD", "«nucleo.referenciales»: es una nota de honestidad del núcleo y no se "
                         "acota nunca"),
    ("ACOTA_SIN_NOTA", "`acota` «nucleo.validez» sin `nota`"),
    ("ACOTA_INVENTADA", "no es una nota acotable del núcleo"),
    ("ACOTA_DOBLE", "la nota «nucleo.validez» ya la acota otra fuente suya"),
    ("INCLUYE_MALO", "`incluye` nombra 'viaticos'"),
    ("IDENTIFICACION_NO_LLAMABLE", "`de_documento` es una función"),
    ("ROTULO_DOS_LINEAS", "`rotulo` es de una sola línea"),
    ("ROTULO_LARGO", "`rotulo` tiene 61 caracteres (máximo 60)"),
    ("ROTULO_VACIO", "`rotulo` es un texto no vacío"),
])
def test_lo_que_no_carga(cargar, variante, motivo):
    from apolo.commands.registry import REGISTRY
    from apolo.library import costeo_extension

    (e,) = cargar(variante)
    assert e["cargada"] is False and motivo in e["motivo"], e
    assert costeo_extension.DE_EXTENSION == {} and "prueba.hola" not in REGISTRY  # todo o nada


def test_una_nota_del_nucleo_tiene_un_solo_dueno_entre_extensiones(cargar):
    from apolo.library import costeo_extension

    primera, otra = cargar("COSTEO_IDENTIFICADA", "OTRA_VALIDEZ")
    assert primera["cargada"] and otra["cargada"] is False
    assert "ya la acota la extensión «ext-prueba»" in otra["motivo"]
    assert list(costeo_extension.DE_EXTENSION) == ["ext-prueba"]
