"""Fase E · juego de planos (sheet set) + BOM enriquecido."""

from apolo.doc import Document
from apolo.drawing import sheet_set, sheets_to_pdf
from apolo.library.bom import bom_from_scene


def test_sheet_set_pages_and_multipage_pdf():
    doc = Document()
    doc.execute("create_box", {"name": "larguero", "width": 100, "depth": 18, "height": 2000, "position": {"x": -300}})
    doc.execute("create_box", {"name": "larguero", "width": 100, "depth": 18, "height": 2000, "position": {"x": 300}})
    doc.execute("create_box", {"name": "travesano", "width": 500, "depth": 18, "height": 100, "position": {"z": 1000}})
    pages = sheet_set(doc.scene, project_name="Puerta")
    # conjunto + 2 piezas distintas (larguero, travesaño) + cédula
    assert len(pages) == 1 + 2 + 1
    pdf = sheets_to_pdf(pages)
    assert pdf[:4] == b"%PDF"


def test_sheet_set_per_part_dimensioned():
    doc = Document()
    doc.execute("create_box", {"name": "tabla", "width": 300, "depth": 18, "height": 1200})
    pages = sheet_set(doc.scene)
    part = pages[1]  # primera lámina de pieza
    assert any("tabla" in lab.text for lab in part.labels)
    assert any(ln.kind == "dim" for ln in part.lines)


def test_sheet_set_separates_cutlist_and_hardware():
    """El juego pro separa LISTA DE CORTE (tablas) y CÉDULA DE HERRAJE (catálogo no cortable)."""
    doc = Document()
    doc.execute("create_box", {"name": "tabla madera", "width": 300, "depth": 18, "height": 1200})
    doc.execute("insert_component", {"component": "BIS-H-75-A", "position": {"x": 0, "y": 0, "z": 0}})
    pages = sheet_set(doc.scene, template="carpinteria")
    titles = [lab.text for pg in pages for lab in pg.labels]
    assert "LISTA DE CORTE" in titles
    assert "CÉDULA DE HERRAJE" in titles
    # la bisagra es herraje no cortable → NO aparece en la lista de corte (tabla madera sí)
    corte = next(pg for pg in pages if any(l.text == "LISTA DE CORTE" for l in pg.labels))
    corte_txt = " ".join(l.text for l in corte.labels)
    assert "tabla madera" in corte_txt and "BIS-H-75-A" not in corte_txt


def test_per_part_sheet_omits_iso():
    """La lámina por pieza no lleva isométrica (3 vistas bastan) → evita el solape con el cajetín."""
    doc = Document()
    doc.execute("create_box", {"name": "tabla", "width": 300, "depth": 18, "height": 1200})
    part = sheet_set(doc.scene)[1]  # primera lámina de pieza
    texts = [l.text for l in part.labels]
    assert "ISOMÉTRICA (sin escala)" not in texts
    assert any("ALZADO" == t for t in texts) and any("PERFIL" == t for t in texts)


def test_bom_enriched_with_material():
    doc = Document()
    doc.execute("create_box", {"name": "tabla madera", "width": 200, "depth": 18, "height": 400})
    rows = bom_from_scene(doc.scene)
    assert any(r.get("material") == "madera" for r in rows)


def test_cutlist_sheet_refs_column():
    """compose_sheet(sheet_refs=...) añade la columna 'Hoja' al DESPIECE (cross-ref globo→detalle)."""
    from apolo.drawing import compose_sheet
    from apolo.library.cutlist import cut_list

    doc = Document()
    doc.execute("create_box", {"name": "tabla A", "width": 300, "depth": 18, "height": 1200})
    doc.execute("create_box", {"name": "tabla B", "width": 200, "depth": 18, "height": 600})
    rows = cut_list(doc.scene)
    refs = {rows[0]["_rep"]: 2, rows[1]["_rep"]: 7}  # nº de hoja por pieza (7 no colisiona con cantidades)
    texts = [l.text for l in compose_sheet(doc.scene, cutlist=True, sheet_refs=refs).labels]
    assert "Hoja" in texts and "2" in texts and "7" in texts
    # sin sheet_refs no hay columna Hoja
    assert "Hoja" not in [l.text for l in compose_sheet(doc.scene, cutlist=True).labels]


def test_sheet_set_cross_reference_hoja_column():
    """El conjunto del juego lleva la columna Hoja, y su nº = la lámina de detalle real de cada pieza."""
    doc = Document()
    doc.execute("create_box", {"name": "larguero", "width": 100, "depth": 18, "height": 2000})
    doc.execute("create_box", {"name": "travesano", "width": 500, "depth": 18, "height": 100, "position": {"z": 1000}})
    pages = sheet_set(doc.scene, project_name="Marco")
    texts = [l.text for l in pages[0].labels]                 # conjunto = página 0
    assert "Hoja" in texts                                    # columna de cross-reference
    assert "2" in texts and "3" in texts                      # larguero→hoja 2, travesaño→hoja 3
    # y esas son las hojas reales: pages[1] = larguero, pages[2] = travesaño
    assert any("larguero" in l.text for l in pages[1].labels)
    assert any("travesano" in l.text for l in pages[2].labels)


# --------------------------------------------- V7.1c C: compras vs fabricación + títulos
def test_purchase_items_excluded_from_cutlist_and_in_cedula():
    from apolo.library.cutlist import cut_list, hardware_schedule

    doc = Document()
    doc.execute("create_box", {"name": "Larguero A36", "width": 2000, "depth": 40,
                               "height": 80, "position": {"z": 800}})
    doc.execute("create_box", {"name": "Perno anclaje M12 + arandela", "width": 12,
                               "depth": 12, "height": 60, "position": {"x": 100}})
    doc.execute("create_box", {"name": "Pies niveladores (regulables)", "width": 40,
                               "depth": 40, "height": 30, "position": {"x": 200}})
    doc.execute("create_box", {"name": "Banda PVC 2mm 700 (lazo cerrado)", "width": 2000,
                               "depth": 600, "height": 2, "position": {"x": 300, "z": 850}})
    cl_names = " ".join(r["nombre"] for r in cut_list(doc.scene))
    assert "Larguero" in cl_names
    assert "Perno" not in cl_names and "niveladores" not in cl_names and "Banda" not in cl_names
    hw_names = " ".join(h["nombre"] for h in hardware_schedule(doc.scene))
    assert "Perno" in hw_names and "niveladores" in hw_names and "Banda" in hw_names


def test_fab_piece_that_mentions_perno_stays_in_cutlist():
    from apolo.library.cutlist import cut_list

    doc = Document()
    # el EJE se fabrica aunque su nombre MENCIONE un perno; no es compra
    doc.execute("create_box", {"name": "Tensor de cola · Eje fijo (roscado p/ perno)",
                               "width": 35, "depth": 400, "height": 35})
    assert any("Eje fijo" in r["nombre"] for r in cut_list(doc.scene))


def test_table_sheets_have_real_title():
    doc = Document()
    doc.execute("create_box", {"name": "tabla", "width": 300, "depth": 18, "height": 1200})
    pages = sheet_set(doc.scene, project_name="Faja 4m")
    corte = next(pg for pg in pages if any(l.text == "LISTA DE CORTE" for l in pg.labels))
    txt = " ".join(l.text for l in corte.labels)
    assert "Faja 4m" in txt and "Sin título" not in txt


def test_multisolid_same_name_gets_disambiguating_suffix():
    """V7.2c: varios sólidos DISTINTOS con el mismo nombre (p. ej. 3 ménsulas del
    motorreductor) → cada lámina lleva sufijo «(k/n)» para no compartir título."""
    doc = Document()
    for i, (w, d, h) in enumerate([(120, 80, 10), (140, 90, 12), (160, 100, 14)]):
        doc.execute("create_box", {"name": "Ménsula soporte motorreductor", "width": w,
                                   "depth": d, "height": h, "position": {"x": i * 300}})
    pages = sheet_set(doc.scene, project_name="Faja")
    # el título del cajetín se trunca a 34 chars → el «(» del sufijo es la marca estable
    # (el nº de hoja «k/5» no lleva paréntesis, así no colisiona)
    suffixes = {s for p in pages for l in p.labels for s in ("(1/3", "(2/3", "(3/3")
                if s in l.text}
    assert suffixes == {"(1/3", "(2/3", "(3/3"}  # las 3 láminas quedan desambiguadas


def test_single_solid_title_has_no_suffix():
    """Una pieza única NO recibe sufijo (el título queda limpio)."""
    doc = Document()
    doc.execute("create_box", {"name": "Placa única", "width": 120, "depth": 80, "height": 10})
    part = sheet_set(doc.scene)[1]
    assert not any("(1/1)" in l.text for l in part.labels)


def test_profile_section_labeled_on_part_sheet():
    doc = Document()
    doc.execute("insert_component", {"component": "TUBO-3X3", "position": {"x": 0, "y": 0, "z": 0}})
    pages = sheet_set(doc.scene)
    part_txt = " ".join(l.text for pg in pages[1:2] for l in pg.labels)
    assert "HSS" in part_txt and "76.2" in part_txt
