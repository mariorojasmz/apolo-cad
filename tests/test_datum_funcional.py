"""Datum por cara FUNCIONAL (V7.5, E2.2): la lámina mide las posiciones de agujero desde
la arista de la cara de montaje derivada de los FASTENERS declarados (soldadura > perno >
contacto), con fallback honesto a la esquina inf-izq cuando no hay señal o la cara es ⊥
a la vista. PROHIBIDO inferir por nombre (lección V7.2c)."""
import pytest

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


# ------------------------------------------------- V7.6 A: GD&T (datums A-B-C + posición)
def test_datum_frame_letters_are_orthogonal():
    """A = cara funcional de mayor peso; B y C solo si son ORTOGONALES a las anteriores
    (un marco de referencia con dos datums en el mismo eje no orienta la pieza)."""
    doc = Document("t")
    placa = doc.execute("create_box", {"name": "Placa", "width": 100, "depth": 100, "height": 10})
    caja = doc.execute("create_box", {"name": "Caja", "width": 40, "depth": 40, "height": 40,
                                      "position": {"z": 25}})          # contacto +z
    lado = doc.execute("create_box", {"name": "Lado", "width": 20, "depth": 100, "height": 10,
                                      "position": {"x": 60}})          # contacto +x
    otro_z = doc.execute("create_box", {"name": "Tapa", "width": 30, "depth": 30, "height": 8,
                                        "position": {"x": -30, "z": 24}})  # OTRO contacto +z
    doc.execute("fasten", {"name": "u1", "a": placa, "b": lado, "kind": "soldadura"})
    doc.execute("fasten", {"name": "u2", "a": placa, "b": caja, "kind": "perno"})
    doc.execute("fasten", {"name": "u3", "a": placa, "b": otro_z, "kind": "contacto"})
    frame = api._piece_datum_frame(doc)[placa]
    assert [f[0] for f in frame] == ["A", "B"]        # solo 2 ejes distintos disponibles
    assert frame[0][1] == "+x" and frame[1][1] == "+z"  # soldadura primero, luego perno
    assert "soldadura" in frame[0][2] and "Lado" in frame[0][2]   # motivo trazable
    assert all(f[1][1] != frame[0][1][1] for f in frame[1:])      # ejes ortogonales


def test_datum_frame_single_face_stays_A():
    """Una pieza con UNA sola cara de montaje se queda con «A»: inventar B/C mentiría
    sobre cómo se posiciona la pieza."""
    doc = Document("t")
    a = doc.execute("create_box", {"name": "Placa", "width": 100, "depth": 100, "height": 10})
    b = doc.execute("create_box", {"name": "Caja", "width": 40, "depth": 40, "height": 40,
                                   "position": {"z": 25}})
    doc.execute("fasten", {"name": "u1", "a": a, "b": b, "kind": "perno"})
    assert [f[0] for f in api._piece_datum_frame(doc)[a]] == ["A"]


def test_pos_tol_from_bolt_budget_floating_vs_fixed():
    """La tolerancia del marco sale del presupuesto de ensamble REAL: con tuerca en el eje
    el fijador es FLOTANTE (holgura completa); sin ella, FIJO (mitad)."""
    doc = Document("t")
    placa = doc.execute("create_box", {"name": "Placa", "width": 200, "depth": 100,
                                       "height": 10, "position": {"z": 5}})
    doc.execute("drill_hole", {"feature": placa, "position": {"x": 0, "y": 0, "z": 10},
                               "axis": "-z", "diameter": 13.5})
    doc.execute("insert_component", {"component": "PERNO-HEX-M12",
                                     "position": {"x": 0, "y": 0, "z": 20}})
    # fijador FIJO (solo perno): (13.5 − 12)/2 = 0.75
    assert api._piece_pos_tols(doc)[placa][13.5] == pytest.approx(0.75)
    doc.execute("insert_component", {"component": "TUERCA-M12",
                                     "position": {"x": 0, "y": 0, "z": -5}})
    # FLOTANTE (perno + tuerca): 13.5 − 12 = 1.5
    assert api._piece_pos_tols(doc)[placa][13.5] == pytest.approx(1.5)


def test_no_bolt_no_pos_tol():
    """Sin perno identificable en el eje NO hay entrada: una tolerancia GD&T inventada es
    peor que su ausencia (el taller la fabrica)."""
    doc = Document("t")
    placa = doc.execute("create_box", {"name": "Placa", "width": 200, "depth": 100,
                                       "height": 10, "position": {"z": 5}})
    doc.execute("drill_hole", {"feature": placa, "position": {"x": 0, "y": 0, "z": 10},
                               "axis": "-z", "diameter": 13.5})
    doc.execute("insert_component", {"component": "PERNO-HEX-M12",
                                     "position": {"x": 150, "y": 0, "z": 20}})  # OTRO eje
    assert api._piece_pos_tols(doc) == {}


def test_control_frame_and_legend_on_sheet():
    """La lámina dibuja el marco de control (símbolo de posición GRÁFICO, no glifo) y la
    LEYENDA que nombra la unión de cada datum — sin leyenda el marco es decorativo."""
    doc = Document("t")
    placa = doc.execute("create_box", {"name": "Placa", "width": 200, "depth": 100, "height": 10})
    doc.execute("drill_hole", {"feature": placa, "position": {"x": -60, "y": -20, "z": 5},
                               "axis": "-z", "diameter": 13.5})
    base = compose_sheet(doc.scene, auto_dims=True, shop_notes=True)
    m = compose_sheet(doc.scene, auto_dims=True, shop_notes=True,
                      datum_frame=[("A", "+z", "soldadura a «Larguero»")],
                      pos_tols={13.5: 0.75})
    txt = " ".join(l.text for l in m.labels)
    assert "Ø0.75 M" in txt                      # tolerancia dentro del marco
    assert "Datum A: cara +Z — soldadura a «Larguero»" in txt   # leyenda trazable
    # el símbolo de posición se DIBUJA (círculo completo + cruz), no se rotula
    assert any(abs(a.a2 - a.a1) >= 359 for a in m.arcs)
    assert len(m.arcs) > len(base.arcs) and len(m.lines) > len(base.lines)


def test_pos_tol_bolt_dia_from_iso273_table():
    """El Ø del perno sale de la tabla de paso ISO 273 (Ø13.5 ES el paso de un M12) —
    fuente NORMATIVA: la tornillería a-medida del 38 no declara su métrica en el nombre
    y sin la tabla esas piezas se quedaban sin marco."""
    doc = Document("t")
    placa = doc.execute("create_box", {"name": "Placa", "width": 200, "depth": 100,
                                       "height": 10, "position": {"z": 5}})
    doc.execute("drill_hole", {"feature": placa, "position": {"x": 0, "y": 0, "z": 10},
                               "axis": "-z", "diameter": 13.5})
    # tornillería a-medida SIN métrica en el nombre (el caso «Tornillería ménsula…»)
    doc.execute("run_script", {"name": "Tornillería de la placa",
                               "code": "result = Pos(0, 0, 10)*Cylinder(6, 40)"})
    assert api._piece_pos_tols(doc)[placa][13.5] == pytest.approx(0.75)   # (13.5−12)/2


def test_legend_only_when_a_frame_was_drawn():
    """Leyenda de datums SOLO si se dibujó algún marco: una lámina cuya vista no muestra
    los barrenos (sub-sólido sin círculos) no debe rotular datums huérfanos."""
    doc = Document("t")
    doc.execute("create_box", {"name": "Placa lisa", "width": 200, "depth": 100, "height": 10})
    m = compose_sheet(doc.scene, auto_dims=True, shop_notes=True,
                      datum_frame=[("A", "+z", "soldadura a «X»")], pos_tols={13.5: 0.75})
    assert not any("Datum A" in l.text for l in m.labels)   # sin barrenos → sin leyenda
