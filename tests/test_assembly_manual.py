"""Manual de ensamblaje paso a paso: derivación de la secuencia + composición de páginas."""

import importlib.util

import pytest

from apolo.doc import Document
from apolo.drawing.assembly_manual import (
    _family_head, assembly_manual, assembly_steps, order_by_support,
)
from apolo.library.catalog import CATALOG

_HAS_MPL = importlib.util.find_spec("matplotlib") is not None


def _caja(doc: Document) -> None:
    """Caja simple: base + tapa (a medida) + un tornillo de catálogo (herraje)."""
    doc.execute("create_box", {"name": "Marco base", "width": 400, "depth": 40, "height": 400})
    doc.execute("create_box", {"name": "Tapa sup", "width": 400, "depth": 40, "height": 40, "position": {"z": 220}})
    doc.execute("insert_component", {"component": "DIN912-M6", "position": {"x": 0, "y": 0, "z": 0}})


def test_assembly_steps_groups_and_orders():
    doc = Document()
    _caja(doc)
    stages = assembly_steps(doc.scene, doc.commands, CATALOG)
    labels = [s["label"] for s in stages]
    # el herraje se agrupa por familia (DIN912 → tornillería); las a medida por token de nombre
    assert any("Marco" in l for l in labels)
    assert any("Torniller" in l for l in labels)
    # orden por aparición en el log: el Marco (creado primero) va antes que el herraje (último)
    first_marco = next(i for i, s in enumerate(stages) if "Marco" in s["label"])
    first_torn = next(i for i, s in enumerate(stages) if "Torniller" in s["label"])
    assert first_marco < first_torn


def test_assembly_steps_skips_hidden():
    doc = Document()
    _caja(doc)
    cid = doc.execute("create_box", {"name": "Cruft oculto", "width": 10, "depth": 10, "height": 10})
    doc.set_visibility(cid, False)
    labels = [s["label"] for s in assembly_steps(doc.scene, doc.commands, CATALOG)]
    assert not any("Cruft" in l for l in labels)  # lo oculto no entra en el manual


def test_assembly_manual_isolate_subset():
    """Acotar a un sub-ensamblaje: solo las piezas aisladas entran en la secuencia."""
    doc = Document()
    _caja(doc)
    # aislar solo el Marco + el tornillo (excluir la Tapa)
    ids = [fid for fid, f in doc.scene.items() if "Marco" in f.name or f.component]
    sub = {fid: doc.scene[fid] for fid in ids}
    labels = [s["label"] for s in assembly_steps(sub, doc.commands, CATALOG)]
    assert any("Marco" in l for l in labels)
    assert not any("Tapa" in l for l in labels)  # la Tapa quedó fuera del sub-ensamblaje


# ------------------------------------------------- V7.2b A: orden por grafo de soporte
def _box(doc, name, w, d, h, x=0.0, y=0.0, z=0.0):
    return doc.execute("create_box", {"name": name, "width": w, "depth": d, "height": h,
                                      "position": {"x": x, "y": y, "z": z}})


def test_order_by_support_respects_stack():
    """pata→larguero→chumacera→eje→motor apilados: el orden de MONTAJE sigue el
    soporte (tierra→arriba), NO el orden del log (creados al revés)."""
    doc = Document()
    # creados en orden INVERSO al de montaje para probar que manda el soporte
    _box(doc, "Motor 1.5HP", 60, 60, 40, z=340)      # 320..360
    _box(doc, "Eje motriz", 60, 60, 40, z=300)       # 280..320
    _box(doc, "Chumacera UCP", 60, 60, 40, z=260)    # 240..280
    _box(doc, "Larguero X", 60, 60, 40, z=220)       # 200..240
    _box(doc, "Pata soporte", 60, 60, 200, z=100)    # 0..200 (piso)
    stages = order_by_support(doc.scene, assembly_steps(doc.scene, doc.commands, CATALOG))
    labels = [s["label"] for s in stages]
    assert labels == ["Pata", "Larguero", "Chumacera", "Eje", "Motor"]


def test_orphan_step_merges_into_subassembly():
    """Una pieza suelta a-medida se FUSIONA al paso del sub-ensamblaje al que se une."""
    doc = Document()
    base = _box(doc, "Placa base", 200, 200, 20, z=10)       # piso
    col = _box(doc, "Columna", 60, 60, 200, z=120)           # 20..220 sobre la base
    doc.execute("create_group", {"name": "Torre", "members": [base, col]})
    cart = _box(doc, "Cartela refuerzo", 40, 60, 60, x=50, z=140)  # soldada al costado
    stages = order_by_support(doc.scene, assembly_steps(doc.scene, doc.commands, CATALOG))
    labels = [s["label"] for s in stages]
    assert not any("Cartela" in l for l in labels)     # el huérfano ya no es paso propio
    torre = next(s for s in stages if s["label"] == "Torre")
    assert cart in torre["ids"]                        # se fusionó al sub-ensamblaje


def test_order_by_support_family_tiebreak_bearing_before_motor():
    """V7.2c fix 3: chumacera, eje y motor coextensos en z (el eje cruza el bore, el
    motor cuelga del eje → mismo_nivel, MISMO rango de soporte). El desempate por
    familia monta la chumacera ANTES que el motor — el motor de eje hueco desliza sobre
    un eje que las chumaceras ya sostienen. Creados en orden log motor→eje→chumacera
    para probar que el tie-break, no el log, decide."""
    doc = Document()
    _box(doc, "Larguero X", 400, 80, 40, x=200, y=40, z=20)          # piso
    _box(doc, "Motor NMRV sinfin", 120, 120, 120, x=250, y=40, z=100)  # cuelga del eje
    _box(doc, "Eje motriz", 300, 40, 40, x=200, y=40, z=100)          # cruza el bore
    _box(doc, "Chumacera UCP207", 80, 90, 120, x=60, y=40, z=100)     # sostiene el eje
    stages = order_by_support(doc.scene, assembly_steps(doc.scene, doc.commands, CATALOG), CATALOG)
    labels = [s["label"] for s in stages]
    assert labels == ["Larguero", "Chumacera", "Eje", "Motor"]
    assert labels.index("Chumacera") < labels.index("Motor")  # el fix explícito


def test_order_by_support_fallback_no_structure():
    """Sin estructura (piezas separadas, sin soporte) el orden del log queda intacto."""
    doc = Document()
    _box(doc, "Alpha", 50, 50, 50, x=0, z=100)
    _box(doc, "Beta", 50, 50, 50, x=500, z=300)
    _box(doc, "Gamma", 50, 50, 50, x=1000, z=500)
    base = assembly_steps(doc.scene, doc.commands, CATALOG)
    out = order_by_support(doc.scene, base)
    assert [s["label"] for s in out] == [s["label"] for s in base]  # sin reordenar


# ------------------------------------------------- V7.2c fix 4: texto por familia
def test_family_head_amedida_bolts_apretar_en_cruz():
    """V7.2c fix 4: un paso de tornillería MODELADA a-medida (no catálogo, «Perno
    anclaje M12…», como los 24 de la faja 38) NO es is_hw pero SÍ recibe la cabecera
    «apretar en cruz» — antes caía al texto genérico."""
    doc = Document()
    for i in range(4):
        doc.execute("create_box", {"name": "Perno anclaje M12 + arandela", "width": 18,
                                   "depth": 18, "height": 60, "position": {"x": i * 100}})
    stages = assembly_steps(doc.scene, doc.commands, CATALOG)
    perno = next(s for s in stages if "Perno" in s["label"])
    assert not perno["is_hw"]  # a-medida, sin componente de catálogo
    assert "apretar en cruz" in _family_head(perno, doc.scene, CATALOG).lower()


def test_family_head_catalog_bolts_still_apernado():
    """Regresión: la tornillería de CATÁLOGO (is_hw) sigue recibiendo «apretar en cruz»."""
    doc = Document()
    doc.execute("insert_component", {"component": "DIN912-M6", "position": {"x": 0}})
    stages = assembly_steps(doc.scene, doc.commands, CATALOG)
    torn = next(s for s in stages if s["is_hw"])
    assert "apretar en cruz" in _family_head(torn, doc.scene, CATALOG).lower()


def test_family_head_mixed_structure_and_bolted_adds_note():
    """Un paso estructural (soldado) que ADEMÁS trae piezas atornilladas (pies
    niveladores) conserva la instrucción de soldar y suma una línea de «apretar en
    cruz» — sin que un perno le robe la cabecera al paso mayormente soldado."""
    doc = Document()
    l = doc.execute("create_box", {"name": "Larguero A36 (+Y)", "width": 2000, "depth": 40,
                                   "height": 80, "position": {"z": 200}})
    p = doc.execute("create_box", {"name": "Pies niveladores (regulables)", "width": 40,
                                   "depth": 40, "height": 30, "position": {"x": 100}})
    doc.execute("create_group", {"name": "Bastidor base", "members": [l, p]})
    stages = assembly_steps(doc.scene, doc.commands, CATALOG)
    base = next(s for s in stages if s["label"] == "Bastidor base")
    head = _family_head(base, doc.scene, CATALOG).lower()
    assert "soldar" in head and "apretar en cruz" in head


def test_family_head_pure_structure_no_bolt_note():
    """Un paso solo estructural (sin atornillados) NO suma la nota de apriete."""
    doc = Document()
    doc.execute("create_box", {"name": "Larguero A36 (+Y)", "width": 2000, "depth": 40,
                               "height": 80})
    stages = assembly_steps(doc.scene, doc.commands, CATALOG)
    larg = next(s for s in stages if "Larguero" in s["label"])
    head = _family_head(larg, doc.scene, CATALOG).lower()
    assert "soldar" in head and "apretar en cruz" not in head


@pytest.mark.skipif(not _HAS_MPL, reason="requiere matplotlib para el render 3D")
def test_assembly_manual_pages_render():
    doc = Document()
    _caja(doc)
    pages = assembly_manual(doc.scene, commands=doc.commands, project_name="Caja", size_px=320)
    stages = assembly_steps(doc.scene, doc.commands, CATALOG)
    assert len(pages) == 1 + len(stages)  # portada + 1 lámina por paso
    # portada: título + tabla de contenidos (secuencia)
    cover = [l.text for l in pages[0].labels]
    assert "MANUAL DE ENSAMBLAJE" in cover
    assert any("SECUENCIA" in t for t in cover)
    assert pages[0].images and pages[0].images[0].png[:4] == b"\x89PNG"  # render del modelo completo
    # cada paso: render embebido + rótulo "PASO k DE n" + lista de piezas
    step = pages[1]
    assert step.images and step.images[0].png[:4] == b"\x89PNG"
    assert any(l.text == f"PASO 1 DE {len(stages)}" for l in step.labels)
    assert any("PIEZAS DE ESTE PASO" in l.text for l in step.labels)
