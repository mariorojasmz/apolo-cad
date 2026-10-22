"""El guion vencido de la fábrica (plan puerta-de-publicacion, F6 · punto 1): un `guion.json`
armado sobre otra versión del log se rehace en el paso `guion` conservando su marcha, título,
subtítulo y lema; `generar` (de una corrida anterior) para con la instrucción exacta.

La API y `flujo.guion` son falsos; la firma sale del `commands.json` real del `.apolo` falso.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from apolo.publicacion import fabrica, flujo, guion_vigente
from apolo.publicacion import marcha as marchas
from apolo.publicacion.fabrica import Encargo, FabricaError

COMANDOS_HOY = [{"id": "c1", "type": "create_box", "params": {"width": 20}}]


def _apolo(comandos) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("commands.json", json.dumps(comandos))
    return buf.getvalue()


FIRMA_HOY = flujo._firma_de(_apolo(COMANDOS_HOY))


def _guion(firma: str, **extra) -> dict:
    g = {"version": 1, "idioma": "es",
         "documento": {"nombre": "faja", "comandos": 1, "firma": firma},
         "titulo": "Faja", "subtitulo": "Así se construyó en Apolo CAD",
         "video": {"ancho": 1920, "alto": 1080, "fps": 30}, "portada": {"duracion_s": 4.0},
         "etapas": [{"titulo": "Bastidor", "texto": "2 largueros de 3 000 mm", "pasos": [1],
                     "duracion_s": 5.0}],
         "cifras": {"titulo": "En cifras", "items": [], "duracion_s": 0.0},
         "orbita": {"duracion_s": 8.0},
         "cierre": {"texto": "Máquinas listas para fabricar", "url": "https://t/maquinas/faja",
                    "duracion_s": 4.0}}
    g.update(extra)
    return g


def _encargo(tmp_path, **kw) -> Encargo:
    raiz = tmp_path / "publicaciones"
    return Encargo(proyecto=7, carpeta=raiz / "faja" / "1.0.0", slug="faja", version="1.0.0",
                   raiz=raiz, tienda="https://t", eco=kw.pop("eco", None) or (lambda *_: None),
                   **kw)


def _escribir(e: Encargo, g: dict) -> None:
    e.carpeta.mkdir(parents=True, exist_ok=True)
    (e.carpeta / "guion.json").write_text(json.dumps(g), encoding="utf-8")


def _leer(e: Encargo) -> dict:
    return json.loads((e.carpeta / "guion.json").read_text(encoding="utf-8"))


@pytest.fixture
def api(monkeypatch):
    """API falsa (el `.apolo` de hoy) y `flujo.guion` falso que arma uno nuevo de ESTA firma."""
    vistos: dict = {"abiertos": 0, "guion": []}

    class Api:
        def __init__(self, cliente):
            pass

        def abrir(self, proyecto):
            vistos["abiertos"] += 1
            return "faja"

        def apolo(self):
            return _apolo(COMANDOS_HOY)

    def guion(cliente, proyecto, *, raiz, slug, version, tienda, eco, titulo=None, modo="montaje",
              marcha=None, **kw):
        carpeta = raiz / slug / version
        assert not (carpeta / "guion.json").exists()  # flujo.guion no pisa uno existente
        m = marcha(object()) if callable(marcha) else marcha
        vistos["guion"].append({"titulo": titulo, "modo": modo, "marcha": m})
        nuevo = _guion(FIRMA_HOY, titulo=titulo or "faja",
                       etapas=[{"titulo": "Bastidor", "texto": "2 largueros de 3 500 mm",
                                "pasos": [1], "duracion_s": 6.0}])
        if m:
            nuevo["marcha"] = {"duracion_s": m["duracion_s"], "escenario": m.get("escenario")}
        (carpeta / "guion.json").write_text(json.dumps(nuevo), encoding="utf-8")
        return {"etapas": 1, "duracion_s": 30.0}

    monkeypatch.setattr(flujo, "_Api", Api)
    monkeypatch.setattr(flujo, "guion", guion)
    monkeypatch.setattr(flujo, "_documento", lambda data: object())
    return vistos


def test_un_guion_vigente_no_se_rehace(tmp_path, api):
    e = _encargo(tmp_path, render="vtk")
    _escribir(e, _guion(FIRMA_HOY))
    assert fabrica.paso_guion(e) == {"ya_estaba": True, "marcha_s": None}
    assert api["guion"] == [] and not (e.carpeta / guion_vigente.VENCIDO).exists()


def test_un_guion_vencido_se_rehace_conservando_lo_que_vale(tmp_path, api, monkeypatch):
    probadas: list = []
    monkeypatch.setattr(marchas, "verificar", lambda doc, m, eco: probadas.append(m))
    monkeypatch.setattr(marchas, "elegir", lambda *a, **k: pytest.fail("traía su marcha"))
    marcha = {"duracion_s": 9.0, "escenario": {"productos": [{"nombre": "caja"}]}}
    viejo = _guion("firma-de-ayer", titulo="Faja de paquetería 4 m", subtitulo="Hecha a medida",
                   modo="diseño", marcha=marcha,
                   cierre={"texto": "Lema editado", "url": "https://t/x", "duracion_s": 4.0})
    eco: list[str] = []
    e = _encargo(tmp_path, eco=eco.append)
    _escribir(e, viejo)
    datos = fabrica.paso_guion(e)
    g = _leer(e)
    assert g["documento"]["firma"] == FIRMA_HOY
    assert (g["titulo"], g["subtitulo"], g["cierre"]["texto"]) == (
        "Faja de paquetería 4 m", "Hecha a medida", "Lema editado")
    assert g["marcha"] == marcha and probadas == [marcha]  # D13c: probada contra el modelo
    assert api["guion"][0]["modo"] == "diseño" and api["guion"][0]["marcha"] == marcha
    assert datos["rehecho"] and datos["marcha_s"] == 9.0 and datos["firma_vieja"] == "firma-de-ayer"
    assert json.loads((e.carpeta / guion_vigente.VENCIDO).read_text(encoding="utf-8")) == viejo
    texto = "\n".join(eco)
    assert "otra versión del proyecto" in texto and "lo rehago" in texto
    assert "«Bastidor»" in texto and guion_vigente.VENCIDO in texto  # el rótulo cambió: avisa


def test_vencido_sin_marcha_elige_la_automatica_o_va_sin_ella(tmp_path, api, monkeypatch):
    elegida = {"duracion_s": 7.0, "escenario": {"productos": []}}
    monkeypatch.setattr(marchas, "elegir", lambda doc, carpeta, **kw: elegida)
    e = _encargo(tmp_path)
    _escribir(e, _guion("vieja", modo="montaje"))
    assert fabrica.paso_guion(e)["marcha_s"] == 7.0
    e2 = _encargo(tmp_path / "otra", marcha=False)
    _escribir(e2, _guion("vieja", marcha={"duracion_s": 5.0, "escenario": {}}))
    assert fabrica.paso_guion(e2)["marcha_s"] is None and "marcha" not in _leer(e2)


def test_si_rehacer_falla_el_vencido_vuelve(tmp_path, api, monkeypatch):
    def roto(*_a, **_k):
        raise flujo.PublicacionError("la API se cayó")

    monkeypatch.setattr(flujo, "guion", roto)
    e = _encargo(tmp_path, render="vtk")
    viejo = _guion("vieja")
    _escribir(e, viejo)
    with pytest.raises(flujo.PublicacionError, match="se cayó"):
        fabrica.paso_guion(e)
    assert _leer(e) == viejo and not (e.carpeta / guion_vigente.VENCIDO).exists()


def test_desde_guion_rehace_el_vencido(tmp_path, api):
    e = _encargo(tmp_path, render="vtk", llave="k")
    _escribir(e, _guion("vieja"))
    hechos: list = []
    pasos = {p: (lambda _e, p=p: hechos.append(p) or {}) for p in fabrica.PASOS if p != "guion"}
    fabrica.fabricar(e, pasos=pasos, desde="guion")
    assert _leer(e)["documento"]["firma"] == FIRMA_HOY and hechos[0] == "ficha"


def test_generar_con_un_guion_vencido_para_con_la_instruccion(tmp_path, api, monkeypatch):
    monkeypatch.setattr(flujo, "generar", lambda *a, **k: pytest.fail("no debía grabar"))
    e = _encargo(tmp_path, candado=tmp_path / "render.lock")
    _escribir(e, _guion("vieja"))
    with pytest.raises(FabricaError, match="(?s)otra versión del proyecto.*--desde guion"):
        fabrica.paso_generar(e)
