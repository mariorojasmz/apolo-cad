"""Datum por cara FUNCIONAL (V7.5, E2.2): la lámina mide las posiciones de agujero desde
la arista de la cara de montaje derivada de los FASTENERS declarados (soldadura > perno >
contacto), con fallback honesto a la esquina inf-izq cuando no hay señal o la cara es ⊥
a la vista. PROHIBIDO inferir por nombre (lección V7.2c)."""
import apolo.api.main as api
from apolo.doc import Document
from apolo.drawing.sheet import compose_sheet


def _placa_con_barreno(doc):
    """Placa 200×100×10 (bounds y ∈ [-50, 50]) con UN barreno en (x=-60, y=-20)."""
    placa = doc.execute("create_box", {"name": "Placa base", "width": 200, "depth": 100,
                                       "height": 10})
    doc.execute("drill_hole", {"feature": placa, "position": {"x": -60, "y": -20, "z": 5},
                               "axis": "-z", "diameter": 12})
    return placa


# ------------------------------------------------------- derivación pura (capa API)
def test_piece_datum_sides_from_fasteners():
    doc = Document("t")
    placa = doc.execute("create_box", {"name": "Placa", "width": 100, "depth": 100, "height": 10})
    caja = doc.execute("create_box", {"name": "Caja", "width": 40, "depth": 40, "height": 40,
                                      "position": {"z": 25}})   # z 5..45: apoya sobre la placa
    doc.execute("fasten", {"name": "u1", "a": placa, "b": caja, "kind": "perno"})
    sides = api._piece_datum_sides(doc)
    # la placa MIRA a la caja hacia +z; la caja a la placa hacia -z
    assert sides[placa] == ["+z"] and sides[caja] == ["-z"]


def test_weld_outweighs_bolt_and_no_signal_stays_out():
    doc = Document("t")
    placa = doc.execute("create_box", {"name": "Placa", "width": 100, "depth": 100, "height": 10})
    caja = doc.execute("create_box", {"name": "Caja", "width": 40, "depth": 40, "height": 40,
                                      "position": {"z": 25}})
    lado = doc.execute("create_box", {"name": "Lado", "width": 20, "depth": 100, "height": 10,
                                      "position": {"x": 60}})   # x 50..70: pegado al costado +x
    doc.execute("fasten", {"name": "u1", "a": placa, "b": caja, "kind": "perno"})
    doc.execute("fasten", {"name": "u2", "a": placa, "b": lado, "kind": "soldadura"})
    suelta = doc.execute("create_box", {"name": "Suelta", "width": 10, "depth": 10,
                                        "height": 10, "position": {"x": 300}})
    sides = api._piece_datum_sides(doc)
    # la soldadura (peso 3) le gana al perno (peso 2): "+x" primero, "+z" de respaldo —
    # la vista que no pueda proyectar "+x" como borde probará "+z"
    assert sides[placa] == ["+x", "+z"]
    assert suelta not in sides           # sin unión declarada → fallback de esquina


# ------------------------------------------------- autodim: medir desde el borde funcional
def test_autodim_measures_from_functional_edge():
    """El barreno en y=-20 dista 30 del borde -y (fallback) y 70 del borde +y (funcional):
    con datum_side='+y' la escalera Y debe rotular 70, no 30."""
    doc = Document("t")
    _placa_con_barreno(doc)
    m_fallback = compose_sheet(doc.scene, auto_dims=True, shop_notes=True)
    m_funcional = compose_sheet(doc.scene, auto_dims=True, shop_notes=True, datum_side="+y")
    t_fb = [l.text for l in m_fallback.labels]
    t_fn = [l.text for l in m_funcional.labels]
    assert "30" in t_fb and "70" not in t_fb
    assert "70" in t_fn and "30" not in t_fn


def test_view_picks_first_side_projectable_as_edge():
    """Lista por peso: si el lado dominante es ⊥ a la vista (el de un perno siempre lo es
    en la vista de sus círculos), la vista usa el SIGUIENTE lado que proyecte como borde.
    ["+z","+x"] en planta → +z no da borde → mide X desde el borde derecho (funcional)."""
    doc = Document("t")
    _placa_con_barreno(doc)
    m_fb = compose_sheet(doc.scene, auto_dims=True, shop_notes=True)
    m = compose_sheet(doc.scene, auto_dims=True, shop_notes=True, datum_side=["+z", "+x"])
    # barreno x=-60: 160 desde el borde derecho (maxx) — solo con el datum funcional.
    # OJO: «40» (la distancia desde minx) NO sirve de testigo negativo: coincide con un
    # tick de la barra de escala presente en TODAS las láminas.
    assert "160" not in [l.text for l in m_fb.labels]
    assert "160" in [l.text for l in m.labels]


def test_perpendicular_face_falls_back_to_corner():
    """La cara funcional +z es ⊥ a la planta (se proyecta como el plano, no un borde) →
    fallback al comportamiento de esquina, byte-igual en las cotas."""
    doc = Document("t")
    _placa_con_barreno(doc)
    m_fallback = compose_sheet(doc.scene, auto_dims=True, shop_notes=True)
    m_perp = compose_sheet(doc.scene, auto_dims=True, shop_notes=True, datum_side="+z")
    assert [l.text for l in m_perp.labels] == [l.text for l in m_fallback.labels]
