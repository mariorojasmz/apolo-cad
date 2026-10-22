"""La máquina andando CON PRODUCTO en el video de la fábrica (plan fabrica-de-publicaciones,
ajuste D10): `services/marcha_ejemplo.py` (la automática de un transportador),
`publicacion/marcha.py` (`marcha.json` o la automática, probada) y el paso `guion` de la
fábrica que la pasa al guion o se la suma al que dejó el modelador.

La automática se prueba de verdad sobre una `create_belt_conveyor` chica (MuJoCo); el resto, con
la simulación y la API reemplazadas por falsos.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from apolo.doc.document import Document
from apolo.publicacion import fabrica, flujo
from apolo.publicacion import marcha as marchas
from apolo.publicacion.fabrica import Encargo, FabricaError
from apolo.publicacion.paquete import PublicacionError
from apolo.services import marcha_ejemplo as me

ESCENARIO = {"duracion_s": 4.0, "motores": [{"junta": "j", "modo": "velocidad", "valor": 30}]}


@pytest.fixture(scope="module")
def faja():
    doc = Document("faja-ejemplo")
    doc.execute("create_belt_conveyor", {"largo": 2000, "ancho_banda": 500, "altura": 800})
    return doc


# ------------------------------------------------------------------ la automática
def test_sin_requisitos_usa_la_caja_de_ejemplo_y_lo_dice(faja):
    m = me.armar(faja, extra_s=2.0)
    cajas = m.escenario["productos"]
    assert {tuple(c["dims_mm"]) for c in cajas} == {me.PRODUCTO_DEFECTO}
    assert {c["masa_kg"] for c in cajas} == {me.MASA_DEFECTO_KG}
    assert m.escenario["motores"][0]["v_superficie_m_s"] == me.VELOCIDAD_DEFECTO_M_S
    assert set(m.asumido) >= {"largo_paquete_mm", "peso_paquete_kg", "velocidad_m_s"}
    # de la cola a la cabeza motriz: la junta virtual de la faja y la dirección hacia ella
    mot = m.escenario["motores"][0]
    assert mot["junta"] == "c1_eje_motriz"
    assert "bandas" not in m.escenario  # la de create_belt_conveyor se detecta sola
    # varias cajas ya sobre la banda desde el primer cuadro + la alimentación por la cola
    quietas = [c for c in cajas if "cada_s" not in c]
    serie = [c for c in cajas if "cada_s" in c]
    assert len(quietas) >= 2 and len(serie) == 1
    eje = [round(x) for x in mot["direccion_transporte"]]
    k = eje.index(1) if 1 in eje else eje.index(-1)
    avance = [c["posicion_mm"][k] * eje[k] for c in quietas]
    assert avance == sorted(avance) and serie[0]["posicion_mm"] == quietas[0]["posicion_mm"]
    assert m.escenario["duracion_s"] == pytest.approx(m.duracion_s + 2.0)


def test_los_requisitos_mandan_producto_peso_y_velocidad(faja, monkeypatch):
    monkeypatch.setattr(faja, "requirements", {
        "largo_paquete_mm": 400, "ancho_paquete_mm": 350, "alto_paquete_mm": 250,
        "peso_paquete_kg": 12, "velocidad_m_s": 0.5, "paquetes_por_minuto": 10})
    m = me.armar(faja)
    caja = m.escenario["productos"][0]
    assert caja["dims_mm"] == [400.0, 350.0, 250.0] and caja["masa_kg"] == 12.0
    assert m.escenario["motores"][0]["v_superficie_m_s"] == 0.5
    serie = next(c for c in m.escenario["productos"] if "cada_s" in c)
    assert serie["cada_s"] == pytest.approx(6.0)  # 10 por minuto
    assert m.asumido == []


def test_un_producto_mas_ancho_que_la_banda_se_recorta(faja, monkeypatch):
    monkeypatch.setattr(faja, "requirements", {"ancho_paquete_mm": 900})
    m = me.armar(faja)
    assert m.escenario["productos"][0]["dims_mm"][1] <= 0.9 * 500 + 1
    assert any("recortado" in a for a in m.asumido)


def test_la_marcha_crece_con_el_largo_y_baja_con_la_velocidad():
    corto, largo = me.duracion_marcha(2000, 0.3), me.duracion_marcha(8000, 0.3)
    assert me.MARCHA_MIN_S <= corto < largo <= me.MARCHA_MAX_S
    assert me.duracion_marcha(8000, 0.6) < largo
    assert me.duracion_marcha(500_000, 0.1) == me.MARCHA_MAX_S


def test_la_automatica_simula_y_las_cajas_avanzan(faja):
    pytest.importorskip("mujoco")
    m = me.armar(faja, extra_s=0.0)
    esc = dict(m.escenario, duracion_s=2.0)  # corta: basta con ver que avanzan
    r = me.probar(faja, esc)
    assert r["avance_mm"] >= 300 and r["productos"] >= 2
    # D13: la faja que dibujará el visor sale de la sección de la banda y es fiel al modelo
    assert [(f["pieza"], f["origen"]) for f in r["fidelidad"]] == [("c1_banda", "seccion")]


def test_sin_banda_no_hay_marcha_y_dice_por_que():
    doc = Document("mesa")
    doc.execute("create_box", {"name": "Tablero", "width": 500, "depth": 400, "height": 30})
    with pytest.raises(me.SinMarcha, match="rodillos sin juntas"):
        me.armar(doc)


def test_una_banda_a_mano_sin_junta_motriz_lo_dice():
    doc = Document("banda-a-mano")
    doc.execute("create_box", {"name": "Banda PVC 2 mm", "width": 2000, "depth": 500, "height": 4})
    with pytest.raises(me.SinMarcha, match="junta de giro motriz"):
        me.armar(doc)


def test_una_simulacion_donde_nada_avanza_no_vale(faja):
    pytest.importorskip("mujoco")
    quieta = {"duracion_s": 0.5, "productos": [
        {"nombre": "caja", "dims_mm": [200, 200, 100], "posicion_mm": [0, 0, 860]}]}
    with pytest.raises(me.SinMarcha, match="no avanzan"):
        me.probar(faja, quieta)
    assert me.probar(faja, quieta, minimo_mm=None)["productos"] == 1  # a mano: basta con simular


# ------------------------------------------------------------------ marcha.json o la automática
@pytest.fixture
def sin_simular(monkeypatch):
    """`probar` y `armar` falsos: anotan lo que se simularía."""
    probadas: list = []

    def probar(doc, esc, minimo_mm=200.0):
        probadas.append((esc, minimo_mm))
        return {"segundos": 0.1, "avance_mm": 900, "productos": 3, "avisos": []}

    monkeypatch.setattr(me, "probar", probar)
    monkeypatch.setattr(me, "armar", lambda doc, extra_s=14.0: me.Marcha(
        escenario={"duracion_s": 10.0 + extra_s, "productos": []}, duracion_s=10.0,
        resumen="1 banda", asumido=["peso_paquete_kg"]))
    return probadas


def test_marcha_json_de_la_version_gana_a_la_automatica(tmp_path, sin_simular):
    carpeta = tmp_path / "faja" / "1.0.0"
    carpeta.mkdir(parents=True)
    (carpeta / marchas.MARCHA_JSON).write_text(json.dumps(ESCENARIO), encoding="utf-8-sig")
    eco: list[str] = []
    m = marchas.elegir(object(), carpeta, eco=eco.append)
    assert m == {"duracion_s": marchas.MARCHA_S, "escenario": ESCENARIO}
    assert sin_simular == [(ESCENARIO, None)]  # a mano: no se exige que avance un producto


def test_marcha_json_del_slug_con_sus_segundos_y_sin_duracion_de_simulacion(tmp_path, sin_simular):
    carpeta = tmp_path / "faja" / "1.0.0"
    carpeta.mkdir(parents=True)
    esc = {"motores": ESCENARIO["motores"]}
    (carpeta.parent / marchas.MARCHA_JSON).write_text(
        json.dumps({"escenario": esc, "duracion_s": 12}), encoding="utf-8")
    m = marchas.elegir(object(), carpeta, extra_s=6.0, eco=None)
    assert m["duracion_s"] == 12.0
    assert m["escenario"]["duracion_s"] == 18.0  # la marcha + lo que sigue andando después


def test_marcha_json_false_es_sin_marcha_y_uno_roto_avisa(tmp_path, sin_simular):
    carpeta = tmp_path / "faja" / "1.0.0"
    carpeta.mkdir(parents=True)
    eco: list[str] = []
    (carpeta / marchas.MARCHA_JSON).write_text("false", encoding="utf-8")
    assert marchas.elegir(object(), carpeta, eco=eco.append) is None
    (carpeta / marchas.MARCHA_JSON).write_text('{"escenario": [1]}', encoding="utf-8")
    assert marchas.elegir(object(), carpeta, eco=eco.append) is None
    assert sin_simular == [] and "SIN la máquina andando" in eco[-1]


def test_sin_archivo_arma_la_automatica_y_dice_lo_asumido(tmp_path, sin_simular):
    eco: list[str] = []
    m = marchas.elegir(object(), tmp_path, extra_s=4.0, eco=eco.append)
    assert m == {"duracion_s": 10.0, "escenario": {"duracion_s": 14.0, "productos": []}}
    assert sin_simular[0][1] == 200.0  # la automática exige que las cajas avancen
    assert any("peso_paquete_kg" in x for x in eco) and any("automática" in x for x in eco)


@pytest.mark.parametrize("donde", ["armar", "probar"])
def test_sin_transportador_o_si_la_simulacion_falla_sigue_sin_marcha(tmp_path, sin_simular,
                                                                     monkeypatch, donde):
    def falla(*_a, **_k):
        raise me.SinMarcha("no hay una banda transportadora")

    monkeypatch.setattr(me, donde, falla)
    eco: list[str] = []
    assert marchas.elegir(object(), tmp_path, eco=eco.append) is None
    assert any("SIN la máquina andando" in x and "banda" in x for x in eco)


# ------------------------------------------------------------------ el paso guion de la fábrica
def _encargo(tmp_path, **kw) -> Encargo:
    raiz = tmp_path / "publicaciones"
    return Encargo(proyecto=7, carpeta=raiz / "faja" / "1.0.0", slug="faja", version="1.0.0",
                   raiz=raiz, tienda="https://t", eco=kw.pop("eco", None) or (lambda *_: None),
                   **kw)


@pytest.fixture
def guion_falso(monkeypatch):
    """`flujo.guion` falso: llama a la marcha que le pasa la fábrica con un documento falso."""
    llamadas: list = []

    def guion(cliente, proyecto, *, marcha=None, **kw):
        m = marcha(SimpleNamespace(nombre="doc")) if callable(marcha) else marcha
        llamadas.append({"marcha": marcha, "elegida": m})
        return {"etapas": 3, "duracion_s": 75.0}

    monkeypatch.setattr(flujo, "guion", guion)
    return llamadas


def test_la_fabrica_pasa_la_marcha_al_guion_nuevo(tmp_path, guion_falso, monkeypatch):
    elegida = {"duracion_s": 9.0, "escenario": {"productos": []}}
    monkeypatch.setattr(marchas, "elegir", lambda doc, carpeta, **kw: elegida)
    datos = fabrica.paso_guion(_encargo(tmp_path))
    assert callable(guion_falso[0]["marcha"]) and guion_falso[0]["elegida"] == elegida
    assert datos["marcha_s"] == 9.0


@pytest.mark.parametrize("kw", [{"render": "vtk"}, {"marcha": False}])
def test_con_vtk_o_sin_marcha_el_guion_va_sin_ella(tmp_path, guion_falso, kw):
    eco: list[str] = []
    datos = fabrica.paso_guion(_encargo(tmp_path, eco=eco.append, **kw))
    assert guion_falso[0]["marcha"] is None and datos["marcha_s"] is None
    assert any("Sin la máquina andando" in x for x in eco)


def _guion_del_modelador(e: Encargo, **extra) -> dict:
    g = {"modo": "montaje", "cifras": {"duracion_s": 6.0}, "orbita": {"duracion_s": 8.0},
         "etapas": [], **extra}
    e.carpeta.mkdir(parents=True, exist_ok=True)
    (e.carpeta / "guion.json").write_text(json.dumps(g), encoding="utf-8")
    return g


@pytest.fixture
def api_falsa(monkeypatch):
    """La API y el documento falsos para sumar la marcha a un guion que ya existe."""
    abiertos: list = []

    class Api:
        def __init__(self, cliente):
            pass

        def abrir(self, proyecto):
            abiertos.append(proyecto)
            return "faja"

        def apolo(self):
            return b"apolo"

    monkeypatch.setattr(flujo, "_Api", Api)
    monkeypatch.setattr(flujo, "_documento", lambda data: SimpleNamespace(commands=[]))
    monkeypatch.setattr("apolo.services.guion_video.validar_guion", lambda g, doc: None)
    return abiertos


def test_al_guion_del_modelador_se_le_suma_la_marcha(tmp_path, api_falsa, monkeypatch):
    e = _encargo(tmp_path)
    _guion_del_modelador(e)
    vistos: dict = {}

    def elegir(doc, carpeta, *, extra_s, eco):
        vistos["extra_s"] = extra_s
        return {"duracion_s": 11.0, "escenario": {"productos": []}}

    monkeypatch.setattr(marchas, "elegir", elegir)
    datos = fabrica.paso_guion(e)
    g = json.loads((e.carpeta / "guion.json").read_text(encoding="utf-8"))
    assert g["marcha"] == {"duracion_s": 11.0, "escenario": {"productos": []}}
    assert datos == {"ya_estaba": True, "marcha_s": 11.0}
    assert vistos["extra_s"] == 14.0 and api_falsa == [7]  # cifras + órbita de ESTE guion


def test_un_guion_con_marcha_o_de_diseno_no_se_toca(tmp_path, api_falsa, monkeypatch):
    monkeypatch.setattr(marchas, "elegir", lambda *a, **k: pytest.fail("no debía elegir"))
    probadas: list = []
    monkeypatch.setattr(me, "probar", lambda doc, esc, minimo_mm: probadas.append((esc, minimo_mm))
                        or {"fidelidad": [{"pieza": "b", "origen": "seccion"}]})
    e = _encargo(tmp_path)
    _guion_del_modelador(e, marcha={"duracion_s": 5.0, "escenario": {"x": 1}})
    antes = (e.carpeta / "guion.json").read_text(encoding="utf-8")
    assert fabrica.paso_guion(e)["marcha_s"] == 5.0
    assert (e.carpeta / "guion.json").read_text(encoding="utf-8") == antes
    assert probadas == [({"x": 1}, None)] and api_falsa == [7]  # D13c: se prueba contra el modelo
    _guion_del_modelador(e, modo="diseño")
    assert fabrica.paso_guion(e)["marcha_s"] is None
    assert api_falsa == [7]


INFIEL = ("la banda «c51» la cinta animada atraviesa «Guarda motriz (1)» (c210) 38 mm más que "
          "el modelo")


def _infiel(*_a, **_k):
    raise me.MarchaInfiel(INFIEL)


def test_una_marcha_infiel_no_cae_en_silencio_a_sin_marcha(tmp_path, sin_simular, monkeypatch):
    monkeypatch.setattr(me, "probar", _infiel)
    with pytest.raises(PublicacionError, match="(?s)NO es fiel al modelo.*Guarda motriz \\(1\\).*38 mm"
                                               ".*false en marcha.json"):
        marchas.elegir(object(), tmp_path, eco=None)


def test_la_fabrica_para_en_el_guion_si_la_marcha_atraviesa_una_guarda(tmp_path, guion_falso,
                                                                       sin_simular, monkeypatch):
    monkeypatch.setattr(me, "probar", _infiel)
    e = _encargo(tmp_path, llave="k")
    pasos = {p: (lambda _e: pytest.fail("no debía seguir")) for p in ("ficha", "generar", "tienda")}
    with pytest.raises(FabricaError, match="(?s)paró en «guion».*atraviesa «Guarda motriz \\(1\\)».*38 mm"):
        fabrica.fabricar(e, pasos=pasos)
    estado = fabrica.leer_estado(e.carpeta)
    assert estado["pasos"]["guion"]["estado"] == "fallo"
    assert "Guarda motriz" in estado["pasos"]["guion"]["error"]


def test_la_marcha_que_ya_traia_el_guion_tambien_se_prueba(tmp_path, api_falsa, monkeypatch):
    monkeypatch.setattr(me, "probar", _infiel)
    e = _encargo(tmp_path)
    _guion_del_modelador(e, marcha={"duracion_s": 5.0, "escenario": {}})
    with pytest.raises(PublicacionError, match="NO es fiel al modelo"):
        fabrica.paso_guion(e)


def test_si_no_hay_marcha_el_guion_del_modelador_queda_igual(tmp_path, api_falsa, monkeypatch):
    monkeypatch.setattr(marchas, "elegir", lambda *a, **k: None)
    e = _encargo(tmp_path)
    antes = _guion_del_modelador(e)
    assert fabrica.paso_guion(e)["marcha_s"] is None
    assert json.loads((e.carpeta / "guion.json").read_text(encoding="utf-8")) == antes


def test_el_reporte_dice_si_salio_andando():
    eco: list[str] = []
    estado = {"slug": "faja", "version": "1.0.0", "proyecto": 7, "pasos": {
        "guion": {"estado": "hecho", "segundos": 1.0, "datos": {"marcha_s": 9.0}},
        "tienda": {"datos": {"publicada": True, "url": "u"}}}}
    fabrica.reporte(estado, eco.append)
    assert any("9 s andando" in x for x in eco)
    estado["pasos"]["guion"]["datos"] = {"ya_estaba": True, "marcha_s": None}
    fabrica.reporte(estado, eco.append)
    assert any("ya estaba; sin la máquina andando" in x for x in eco)
