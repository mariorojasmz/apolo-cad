"""V7.2 «último kilómetro del plano»: soldadura ISO 2553 (A), tolerancia general
ISO 2768 (B), acabados ISO 1302 + notas de proceso (C), acotado por función (D)."""

from apolo.doc import Document
from apolo.drawing import compose_sheet, sheet_set
from apolo.drawing.dimensions import weld_symbol
from apolo.drawing.process import infer_process, shop_notes
from apolo.drawing.sheet import SheetModel


# --------------------------------------------------------------- A · soldadura ISO 2553
def _two_welded_boxes() -> tuple[Document, dict]:
    doc = Document()
    a = doc.execute("create_box", {"name": "Pata A36", "width": 40, "depth": 40, "height": 800})
    b = doc.execute("create_box", {"name": "Travesaño A36", "width": 500, "depth": 40,
                                    "height": 40, "position": {"x": 260, "z": 380}})
    doc.execute("fasten", {"name": "w1", "a": a, "b": b, "kind": "soldadura",
                           "throat_mm": 3.0, "length_mm": 140.0})
    return doc, doc.fasteners


def test_weld_symbol_primitives():
    """weld_symbol dibuja directriz+flecha (dim), triángulo de filete (visible) y el texto a/L."""
    m = SheetModel(200, 200)
    weld_symbol(m, 100, 100, throat=3.0, length=140.0, count=6)
    assert any(l.kind == "dim" for l in m.lines)      # directriz + referencia + flecha
    assert any(l.kind == "visible" for l in m.lines)  # triángulo de filete
    txt = " ".join(l.text for l in m.labels)
    assert "a3" in txt and "140" in txt and "×6" in txt and "típ" in txt


def test_weld_symbols_on_conjunto():
    """compose_sheet(fasteners=...) dibuja el símbolo de soldadura en el conjunto + leyenda."""
    doc, fasteners = _two_welded_boxes()
    model = compose_sheet(doc.scene, cutlist=True, fasteners=fasteners)
    txt = " ".join(l.text for l in model.labels)
    assert "a3" in txt and "140" in txt            # cota del cordón
    assert "ISO 2553" in txt                        # leyenda general de soldadura


def test_weld_symbols_grouped_typ():
    """Cordones con misma (garganta, longitud) → UN símbolo «típ. ×N», no N flechas."""
    doc = Document()
    ids = []
    for k in range(3):
        p = doc.execute("create_box", {"name": f"Pata {k}", "width": 40, "depth": 40,
                                       "height": 800, "position": {"x": k * 600}})
        t = doc.execute("create_box", {"name": f"Trav {k}", "width": 200, "depth": 40,
                                       "height": 40, "position": {"x": k * 600, "z": 380}})
        doc.execute("fasten", {"name": f"w{k}", "a": p, "b": t, "kind": "soldadura",
                               "throat_mm": 3.0, "length_mm": 120.0})
        ids += [p, t]
    model = compose_sheet(doc.scene, cutlist=True, fasteners=doc.fasteners)
    typ = [l for l in model.labels if "típ" in l.text]
    assert len(typ) == 1 and "×3" in typ[0].text  # un solo símbolo típico para los 3 cordones


def test_weld_symbols_noop_on_isolated_piece():
    """En una lámina por pieza (a/b no están ambos en la escena) NO se dibuja soldadura."""
    doc, fasteners = _two_welded_boxes()
    only_a = {"P": next(iter(doc.scene.values()))}
    model = compose_sheet(only_a, fasteners=fasteners)
    assert "ISO 2553" not in " ".join(l.text for l in model.labels)


def test_weld_symbols_mixed_none_throat_tie():
    """Grupos empatados en conteo con throat None y float mezclados: el sort del
    agrupador NO debe comparar None < float (TypeError → 500 en el juego). El cordón
    sin dimensionar sale SIN cota a/L + nota, el dimensionado con su cota."""
    doc, _ = _two_welded_boxes()  # w1 dimensionado a3/140
    c = doc.execute("create_box", {"name": "Refuerzo", "width": 60, "depth": 40,
                                   "height": 40, "position": {"x": 0, "z": 700}})
    pata = next(fid for fid, f in doc.scene.items() if "Pata" in f.name)
    doc.execute("fasten", {"name": "w_auto", "a": pata, "b": c, "kind": "soldadura"})
    model = compose_sheet(doc.scene, cutlist=True, fasteners=doc.fasteners)  # no revienta
    txt = " ".join(l.text for l in model.labels)
    assert "a3" in txt and "140" in txt              # el dimensionado conserva su cota
    assert "sin dimensionar" in txt.lower()          # nota honesta del no-dimensionado


# --------------------------------------------------------------- B · tolerancia ISO 2768
def test_default_tolerance_iso_2768():
    doc = Document()
    doc.execute("create_box", {"name": "placa", "width": 100, "depth": 60, "height": 10})
    model = compose_sheet(doc.scene)
    assert any("ISO 2768-mK" in l.text for l in model.labels)  # celda del cajetín
    # override sigue funcionando
    m2 = compose_sheet(doc.scene, meta={"tolerance": "±0.1"})
    assert any("±0.1" in l.text for l in m2.labels)
    assert not any("ISO 2768-mK" in l.text for l in m2.labels)


def test_shop_notes_general_tolerance_note():
    doc = Document()
    doc.execute("create_box", {"name": "placa", "width": 100, "depth": 60, "height": 10})
    model = compose_sheet(doc.scene, shop_notes=True)
    txt = " ".join(l.text for l in model.labels)
    assert "ISO 2768-mK" in txt and "cotas en mm" in txt.lower()


# --------------------------------------------------------------- C · acabados / proceso
def test_infer_process_four_cases():
    doc = Document()
    # 1) torneado: nombre con ajuste ISO 286
    eje = doc.execute("create_box", {"name": "Eje motriz Ø35 h7", "width": 35, "depth": 35, "height": 400})
    assert infer_process(doc.scene[eje], None)["key"] == "torneado"
    # 2) chapa: espesor mínimo ≤6 sin catálogo
    chapa = doc.execute("create_box", {"name": "Mesa 2mm", "width": 600, "depth": 400, "height": 2})
    assert infer_process(doc.scene[chapa], None)["key"] == "laser_pliegue"
    # 3) mecanizado general: bloque grueso a-medida
    blk = doc.execute("create_box", {"name": "Soporte macizo", "width": 80, "depth": 80, "height": 80})
    assert infer_process(doc.scene[blk], None)["key"] == "mecanizado"
    # 4) perfil de catálogo → sierra
    tubo = doc.execute("insert_component", {"component": "TUBO-3X3", "position": {"x": 0, "y": 0, "z": 0}})
    from apolo.library.catalog import CATALOG
    comp = CATALOG.get(doc.scene[tubo].component)
    assert infer_process(doc.scene[tubo], comp)["key"] == "sierra"


# --------------------------------------------------- V7.2b E: proceso e inferencias
def test_infer_process_slender_box_is_sawn():
    """E1: un larguero/pata modelado como create_box (sin catálogo) es un perfil
    aserrado, no «mecanizado» (era el residuo de la faja 38)."""
    doc = Document()
    larg = doc.execute("create_box", {"name": "Larguero A36 (+Y)", "width": 4000,
                                      "depth": 40, "height": 80})
    proc = infer_process(doc.scene[larg], None)
    assert proc["key"] == "sierra" and "perfil" in proc["label"]
    # un bloque macizo NO es perfil (no lo muerde el heurístico)
    blk = doc.execute("create_box", {"name": "Dado macizo", "width": 120, "depth": 120,
                                     "height": 120, "position": {"x": 6000}})
    assert infer_process(doc.scene[blk], None)["key"] == "mecanizado"


def test_infer_process_hollow_tube_is_sawn_not_laser():
    """E1 (fix real de la faja 38): un larguero HSS HUECO a-medida tiene pared fina
    (t_eff ≤6) pero es un perfil esbelto → sierra, NO «corte láser + plegado»."""
    from build123d import Box
    doc = Document()
    # tubo 100×50×3, 4 m (como el larguero c93 de la faja): fill de bbox ~0.17
    fid = doc.execute("run_script", {"name": "Larguero A36 HSS",
                                     "code": "result = Box(4000,50,100) - Box(4001,44,94)"})
    proc = infer_process(doc.scene[fid], None)
    assert proc["key"] == "sierra" and "láser" not in proc["label"]


def test_infer_process_weldment_member_is_sawn():
    """Un miembro de weldment (perfil de catálogo) rotula sierra."""
    doc = Document()
    cid = doc.execute("create_weldment", {"ancho": 800, "fondo": 600, "alto": 700,
                                          "perfil": "PERFIL-4040", "cordones": False})
    from apolo.library.catalog import CATALOG
    member = next(f for f in doc.scene.values()
                  if f.command_id == cid and (CATALOG.get(f.component or "") is not None))
    comp = CATALOG.get(member.component)
    assert infer_process(member, comp)["key"] == "sierra"


def test_flat_plate_has_no_plegado():
    """E2: una placa plana de ≤6 mm es «corte láser», SIN «plegado» (no hay pliegue)."""
    doc = Document()
    fid = doc.execute("create_box", {"name": "Repisa 6mm A36", "width": 400,
                                     "depth": 300, "height": 6})
    proc = infer_process(doc.scene[fid], None)
    assert proc["key"] == "laser_pliegue"
    assert "plegado" not in proc["label"] and "láser" in proc["label"]


def test_bent_sheet_keeps_plegado():
    """Una chapa CON pliegue real (create_sheet_metal con pestaña) sí lleva «plegado»."""
    doc = Document()
    cid = doc.execute("create_sheet_metal", {"ancho": 300, "fondo": 200, "espesor": 2,
                                             "altura_pestana": 60, "lados": ["frente"]})
    part = next(f for f in doc.scene.values() if f.command_id == cid)
    assert "plegado" in infer_process(part, None)["label"]


def test_infer_process_has_fit_forces_turning():
    """E3: una pieza con fit ISO 286 declarado (mapa de la capa API) es torneada
    aunque su nombre no traiga el token."""
    doc = Document()
    fid = doc.execute("create_box", {"name": "Eje del tensor", "width": 35, "depth": 35,
                                     "height": 300})
    assert infer_process(doc.scene[fid], None)["key"] != "torneado"          # sin señal
    assert infer_process(doc.scene[fid], None, has_fit=True)["key"] == "torneado"


# --------------------------------------------- V7.2c: revolución no es «sierra»
def test_revolution_drum_is_turned_not_sawn():
    """V7.2c fix 2: el tambor motriz engomado (cilindro macizo, fill ≈ π/4) rotula
    torneado/fabricado, NO «corte en sierra» (era un falso positivo del heurístico
    esbelto)."""
    doc = Document()
    tid = doc.execute("run_script", {"name": "Tambor motriz engomado",
                                     "code": "from build123d import Cylinder\nresult = Cylinder(radius=57, height=650)"})
    proc = infer_process(doc.scene[tid], None)
    assert proc["key"] == "torneado" and "sierra" not in proc["label"]


def test_revolution_hollow_roller_by_name_is_turned():
    """Un rodillo HUECO (fill « π/4) no lo caza la geometría, pero el ROL en el nombre
    (rodillo) sí → torneado/fabricado, no sierra."""
    doc = Document()
    rid = doc.execute("run_script", {"name": "Rodillo de retorno",
                                     "code": "from build123d import Cylinder\nresult = Cylinder(radius=50.8, height=640) - Cylinder(radius=45, height=641)"})
    proc = infer_process(doc.scene[rid], None)
    assert proc["key"] == "torneado" and "sierra" not in proc["label"]


def test_revolution_geometry_without_name_token():
    """Un cilindro macizo SIN token de rol en el nombre igual se detecta por geometría."""
    doc = Document()
    cid = doc.execute("run_script", {"name": "Pieza cilíndrica",
                                     "code": "from build123d import Cylinder\nresult = Cylinder(radius=30, height=400)"})
    assert infer_process(doc.scene[cid], None)["key"] == "torneado"


def test_revolution_does_not_catch_bracket_named_after_roller():
    """Un SOPORTE nombrado por el rodillo que sostiene («Ménsula rodillo retorno») NO es
    de revolución — el guarda de bracket suprime el match por nombre y la geometría (una
    placa, fill ≈ 1) decide → mecanizado, no torneado (falso positivo cazado en el
    benchmark del 38)."""
    doc = Document()
    fid = doc.execute("create_box", {"name": "Ménsula rodillo retorno", "width": 120,
                                     "depth": 80, "height": 10})
    assert infer_process(doc.scene[fid], None)["key"] != "torneado"
    # el rodillo REAL (cilindro) sí es torneado
    rid = doc.execute("run_script", {"name": "Rodillo retorno Ø50",
                                     "code": "from build123d import Cylinder\nresult = Cylinder(radius=25, height=600)"})
    assert infer_process(doc.scene[rid], None)["key"] == "torneado"


def test_revolution_does_not_catch_hollow_square_tube():
    """Un tubo HSS cuadrado hueco (sección cuadrada pero fill « π/4) NO es revolución →
    sigue siendo «corte en sierra» (no se lo lleva la rama de torneado)."""
    doc = Document()
    l = doc.execute("run_script", {"name": "Larguero A36 HSS",
                                   "code": "from build123d import Box\nresult = Box(4000,50,50) - Box(4001,44,44)"})
    proc = infer_process(doc.scene[l], None)
    assert proc["key"] == "sierra"
    # y una barra maciza cuadrada (fill ≈ 1) tampoco → sierra por perfil
    b = doc.execute("create_box", {"name": "Barra 50", "width": 50, "depth": 50,
                                   "height": 600, "position": {"x": 6000}})
    assert infer_process(doc.scene[b], None)["key"] == "sierra"


def test_finish_cell_from_process():
    """El cajetín pinta el Ra del proceso en la celda «Acabado» cuando shop_notes=True."""
    doc = Document()
    doc.execute("create_box", {"name": "Eje motriz Ø35 h7", "width": 35, "depth": 35, "height": 400})
    model = compose_sheet(doc.scene, shop_notes=True)
    assert any("Ra 3.2" in l.text for l in model.labels)  # torneado → Ra 3.2


def test_surface_finish_next_to_fit_callout():
    """C3: un callout con fit ISO 286 lleva Ra 1.6 al lado."""
    doc = Document()
    cid = doc.execute("create_box", {"name": "placa", "width": 120, "depth": 80, "height": 20})
    doc.execute("drill_hole", {"feature": cid, "position": {"x": 0, "y": 0, "z": -10},
                               "axis": "z", "diameter": 20, "depth": 0, "fit": "H7"})
    model = compose_sheet(doc.scene, hole_fits={20.0: "H7"})
    txt = " ".join(l.text for l in model.labels)
    assert "H7" in txt and "Ra 1.6" in txt


def test_process_note_paint_for_steel():
    doc = Document()
    doc.execute("create_box", {"name": "Larguero A36", "width": 2000, "depth": 40, "height": 80})
    notes = shop_notes(doc.scene[next(iter(doc.scene))], None, "acero")
    joined = " ".join(notes)
    assert "primer" in joined.lower()  # acero estructural → protección
    assert any("2768" in n for n in notes) and any("aristas" in n for n in notes)


def test_process_note_no_paint_for_inox():
    doc = Document()
    fid = doc.execute("create_box", {"name": "Guarda inox", "width": 400, "depth": 300, "height": 3})
    notes = shop_notes(doc.scene[fid], None, "acero inoxidable")
    assert any("no pintar" in n.lower() for n in notes)


# ------------------------------------------ V7.2c fix 1 · fit POR PIEZA en las láminas
def _two_shafts_diff_fit() -> Document:
    """Dos ejes cilíndricos Ø35 con fits distintos en el nombre (motriz h7, tensor g6),
    como el proyecto 38 (dos ejes de igual Ø nominal)."""
    doc = Document()
    doc.execute("run_script", {"name": "Eje motriz Ø35 h7",
                               "code": "from build123d import Cylinder\nresult = Cylinder(radius=17.5, height=400)"})
    doc.execute("run_script", {"name": "Tensor de cola · Eje fijo Ø35 g6",
                               "code": "from build123d import Cylinder\nresult = Cylinder(radius=17.5, height=350)"})
    return doc


def test_feature_fit_maps_are_per_piece():
    """`_feature_fit_maps` da un mapa por feature: cada eje conserva SU clase, sin pisarse."""
    from apolo.api.main import _feature_fit_maps

    doc = _two_shafts_diff_fit()
    per = _feature_fit_maps(doc)
    fits = sorted(m[35.0] for m in per.values() if 35.0 in m)
    assert fits == ["g6", "h7"]  # los dos coexisten (antes el segundo pisaba al primero)


def test_ga_fit_map_omits_conflicting_diameter():
    """En el GA, un Ø con dos clases distintas (h7 y g6 en Ø35) se OMITE — mejor ausente
    que equivocado (antes «el último gana» mentía)."""
    from apolo.api.main import _hole_fit_map, _scene_fit_map

    doc = _two_shafts_diff_fit()
    assert 35.0 not in _hole_fit_map(doc)  # conflicto → no se rotula en el conjunto
    # aislar UN eje sí da su clase (la lámina/vista acotada no tiene conflicto)
    tensor = next(fid for fid, f in doc.scene.items() if "Tensor" in f.name)
    assert _scene_fit_map(doc, {tensor: doc.scene[tensor]}) == {35.0: "g6"}


def test_sheet_set_labels_each_shaft_with_its_own_fit():
    """Cada lámina por pieza rotula EL SUYO: la del eje motriz «h7», la del tensor «g6»
    — la regresión del fix D era que ambas decían «h7» (mapa global por Ø)."""
    from apolo.api.main import _feature_fit_maps, _hole_fit_map

    doc = _two_shafts_diff_fit()
    pages = sheet_set(doc.scene, project_name="Faja",
                      piece_fits=_feature_fit_maps(doc), hole_fits=_hole_fit_map(doc) or None)
    # solo láminas por pieza (llevan nota de taller «Proceso:»); excluye el CONJUNTO,
    # cuyo despiece lista ambos nombres «… h7»/«… g6» y confundiría el filtro
    parts = [p for p in pages if any("Proceso:" in l.text for l in p.labels)]
    motriz = next(p for p in parts if any("motriz" in l.text.lower() for l in p.labels))
    tensor = next(p for p in parts if any("tensor" in l.text.lower() for l in p.labels))
    mtxt = " ".join(l.text for l in motriz.labels)
    ttxt = " ".join(l.text for l in tensor.labels)
    assert "h7" in mtxt and "g6" not in mtxt   # la del motriz, su h7
    assert "g6" in ttxt and "h7" not in ttxt   # la del tensor, su g6


# --------------------------------------------------------------- D · acotado por función
def _placa_con_barrenos(doc: Document) -> str:
    cid = doc.execute("create_box", {"name": "Placa de anclaje A36", "width": 120,
                                     "depth": 80, "height": 12})
    for x, y in ((-40, -25), (40, -25), (-40, 25), (40, 25)):
        doc.execute("drill_hole", {"feature": cid, "position": {"x": x, "y": y, "z": -6},
                                   "axis": "z", "diameter": 13, "depth": 0})
    return cid


def test_datum_flag_on_shop_piece_sheet():
    """Una lámina de taller (shop_notes) con barrenos marca el datum «A» sobre su arista de ref."""
    doc = Document()
    _placa_con_barrenos(doc)
    # planta ve los 4 barrenos Ø13 → callout + posiciones + datum
    model = compose_sheet(doc.scene, auto_dims=True, shop_notes=True)
    txt = [l.text for l in model.labels]
    assert any("Ø13" in t for t in txt)         # callout de Ø
    # el datum añade una «A» además de las 2 de la rejilla de zonas (A–D en el marco)
    base = compose_sheet(doc.scene, auto_dims=True)
    n_base = sum(1 for l in base.labels if l.text == "A")
    n_shop = sum(1 for l in model.labels if l.text == "A")
    assert n_shop > n_base


def test_sheet_set_per_part_datum_and_pitch():
    """El juego pone datum + pitch de montaje en la lámina de una placa con patrón de barrenos."""
    doc = Document()
    _placa_con_barrenos(doc)
    pages = sheet_set(doc.scene, project_name="X")
    part = pages[1]
    txt = [l.text for l in part.labels]
    assert sum(1 for t in txt if t == "A") >= 3   # datum A (además de las 2 de la rejilla)
    assert any("Ø13" in t for t in txt)          # Ø del barreno
    # pitch de montaje (80 = separación entre columnas de barrenos)
    assert any(t == "80" for t in txt)


# --------------------------------------------------------------- sheet_set integración
def test_sheet_set_per_part_has_shop_notes():
    doc = Document()
    doc.execute("create_box", {"name": "Larguero A36", "width": 2000, "depth": 40, "height": 80})
    pages = sheet_set(doc.scene, project_name="Faja")
    part = pages[1]  # primera lámina de pieza
    txt = " ".join(l.text for l in part.labels)
    assert "ISO 2768-mK" in txt  # nota de taller en la lámina por pieza
