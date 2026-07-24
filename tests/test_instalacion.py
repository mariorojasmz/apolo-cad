"""V7.6 fase C (E2.1): lámina de INSTALACIÓN — la hoja que el cliente lleva a la obra
civil. Carga por apoyo con el COG real (reparto elástico de grupo), huella acotada,
holguras de servicio y suministro; hipótesis SIEMPRE declarada."""
import pytest

import apolo.api.main as api
from apolo.doc import Document
from apolo.drawing import sheet_set
from apolo.library.engineering.installation import G_M_S2, anchor_loads


def _cuatro_apoyos():
    return [{"id": f"c{i}", "name": f"Pata {i}", "x": x, "y": y}
            for i, (x, y) in enumerate([(0, 0), (1000, 0), (0, 500), (1000, 500)])]


# ------------------------------------------------------------------ motor puro
def test_uniform_when_cog_centered():
    """COG sobre el centroide → reparto uniforme exacto."""
    r = anchor_loads(_cuatro_apoyos(), 4000.0, (500.0, 250.0))
    assert [a["carga_n"] for a in r["apoyos"]] == pytest.approx([1000.0] * 4)
    assert r["excentricidad_mm"] == [0.0, 0.0] and not r["hay_traccion"]


def test_eccentric_cog_loads_the_near_supports_more():
    """COG descentrado hacia +x → los apoyos de +x cargan MÁS y la suma se conserva."""
    r = anchor_loads(_cuatro_apoyos(), 4000.0, (900.0, 250.0))
    por_x = {a["x_mm"]: a["carga_n"] for a in r["apoyos"]}
    assert por_x[1000.0] > 1000.0 > por_x[0.0]
    assert sum(a["carga_n"] for a in r["apoyos"]) == pytest.approx(4000.0)  # equilibrio
    assert r["carga_max_kg"] == pytest.approx(por_x[1000.0] / G_M_S2, rel=1e-3)


def test_tension_is_declared_not_clipped():
    """Un apoyo que LEVANTA se declara a tracción — recortarlo a cero ocultaría que el
    anclaje debe resistir arranque (dato crítico para la obra)."""
    r = anchor_loads(_cuatro_apoyos(), 1000.0, (5000.0, 250.0))  # COG muy fuera
    assert r["hay_traccion"] and any(a["carga_n"] < 0 for a in r["apoyos"])


def test_hypothesis_always_declared():
    r = anchor_loads(_cuatro_apoyos(), 4000.0, (600.0, 250.0))
    assert "reparto elástico" in r["hipotesis"] and "hiperestático" in r["hipotesis"]


def test_no_supports_raises():
    with pytest.raises(ValueError):
        anchor_loads([], 1000.0)


# ------------------------------------------------------------- capa API + lámina
def _maquina(doc):
    placas = []
    for i, (x, y) in enumerate([(0, 0), (1200, 0), (0, 600), (1200, 600)]):
        p = doc.execute("create_box", {"name": f"Placa de anclaje {i}", "width": 120,
                                       "depth": 120, "height": 10,
                                       "position": {"x": x, "y": y, "z": 5}})
        doc.execute("ground", {"name": f"g{i}", "feature": p})
        placas.append(p)
    doc.execute("create_box", {"name": "Mesa deslizante", "width": 1200, "depth": 600,
                               "height": 8, "position": {"x": 600, "y": 300, "z": 800}})
    doc.execute("create_box", {"name": "Motorreductor de la faja", "width": 200,
                               "depth": 300, "height": 200, "position": {"x": 1200, "y": 750, "z": 600}})
    return placas


def test_api_installation_data_and_sheet():
    doc = Document("inst")
    _maquina(doc)
    doc.requirements = {"carga_kg": 50.0}
    api.DOC = doc
    datos, anclada = api._installation_data(doc)
    assert len(anclada) == 4 and datos["anclaje"]["n_apoyos"] == 4
    assert datos["huella_mm"] == {"largo": 1200.0, "ancho": 600.0}
    assert datos["altura_trabajo_mm"] == pytest.approx(804.0)   # mesa: z 800±4
    assert datos["altura_total_mm"] == pytest.approx(804.0)
    assert any("Motorreductor" in s["pieza"] for s in datos["servicio"])
    # el peso repartido = masa + carga de diseño
    assert datos["anclaje"]["peso_total_n"] == pytest.approx(
        (datos["masa_kg"] + 50.0) * G_M_S2, rel=1e-3)

    pages = sheet_set(doc.scene, project_name="M", installation=(datos, anclada))
    inst = [p for p in pages
            if any("PLANTA DE INSTALACIÓN" in l.text for l in p.labels)]
    assert len(inst) == 1
    txt = " ".join(l.text for l in inst[0].labels)
    assert "DATOS DE INSTALACIÓN" in txt and "Carga máx. por apoyo" in txt
    assert "reparto elástico" in txt                     # hipótesis en la lámina
    assert "1200" in txt and "600" in txt                # cotas de la huella


def test_no_grounds_no_installation_sheet():
    """Sin apoyos anclados NO se emite la lámina (mejor ausente que inventada)."""
    doc = Document("sin")
    doc.execute("create_box", {"name": "Caja", "width": 100, "depth": 100, "height": 100})
    api.DOC = doc
    datos, anclada = api._installation_data(doc)
    assert datos == {} and anclada == {}
    pages = sheet_set(doc.scene, project_name="M", installation=(datos, anclada))
    assert not any(any("PLANTA DE INSTALACIÓN" in l.text for l in p.labels) for p in pages)


def test_anchored_bolts_are_not_supports():
    """La TORNILLERÍA con ground NO es un apoyo: contarla diluye la carga por punto (en
    el 38 daba 30 «apoyos» en vez de 6 placas → 5× menos por punto, y la obra
    dimensionaría de menos)."""
    doc = Document("inst")
    placas = _maquina(doc)
    for i, p in enumerate(placas):
        b = doc.execute("insert_component", {
            "component": "PERNO-HEX-M12", "name": f"Perno anclaje M12 ({i})",
            "position": {"x": 0 if i % 2 == 0 else 1200, "y": 0 if i < 2 else 600, "z": 0}})
        doc.execute("ground", {"name": f"gb{i}", "feature": b})
    api.DOC = doc
    datos, anclada = api._installation_data(doc)
    assert datos["anclaje"]["n_apoyos"] == 4          # las 4 placas, no los 8 grounds
    assert all("Perno" not in a["apoyo"] for a in datos["anclaje"]["apoyos"])


def test_supply_reads_catalog_case_insensitively():
    """Las claves del catálogo no son homogéneas («potencia_kW»): el suministro se lee
    case-insensitive. Sin potencia tabulada NO se inventa el dato."""
    doc = Document("inst")
    _maquina(doc)
    doc.execute("insert_component", {"component": "NMRV-090",
                                     "position": {"x": 1200, "y": 900, "z": 400}})
    api.DOC = doc
    datos, _ = api._installation_data(doc)
    assert datos["suministro"] and "2.2 kW" in datos["suministro"][0]["valor"]
