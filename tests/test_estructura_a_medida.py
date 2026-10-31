"""La estructura que no sale del catálogo (plan puerta-fuera-de-catalogo, F4): flecha y pandeo de
la pieza a medida con la sección medida y el criterio de su material (D7), y el vuelco con las
fuerzas de trabajo declaradas (D8)."""

from __future__ import annotations

import math

import pytest

from apolo.doc.document import Document
from apolo.library.calidad.item import FALLA, OK, SIN_EVALUAR
from apolo.library.calidad.vida_util import controlar_vida_util
from apolo.library.engineering.madera_calculo import criterio
from apolo.library.engineering.mass import scene_mass_properties
from apolo.library.madera_clase import GRUPOS_E010
from apolo.library.materials import density
from apolo.library.requisitos import normalizar_requisitos, requisitos_vuelco
from apolo.services.columnas_rules import columna_rules
from apolo.services.engineering_rules import structure_rules
from apolo.services.puerta_hechos import _vigas
from apolo.services.vigas_rules import beam_rules

G = 9.81
COPAIBA_C = "copaiba, Grupo C (E.010), CH ≤ 22 %"


def _poste(doc, x, nombre, y=0.0, alto=700.0, ancho=2.0, fondo=50.0):
    fid = doc.execute("create_box", {"name": nombre, "width": ancho, "depth": fondo,
                                     "height": alto, "position": {"x": x, "y": y, "z": alto / 2}})
    doc.execute("ground", {"name": f"g_{fid}", "feature": fid})
    return fid


def _une(doc, a, b, kind="perno"):
    doc.execute("fasten", {"name": f"u_{a}_{b}", "a": a, "b": b, "kind": kind})


def _apoyada(nombre, ancho, canto, material=None, largo=1000.0, kind="perno"):
    """Una pieza a medida de `largo` en X sobre dos postes delgados anclados (apoyos en x = 0 y
    x = L), unida a cada uno con `kind`."""
    doc = Document("t")
    v = doc.execute("create_box", {"name": nombre, "width": largo, "depth": ancho,
                                   "height": canto,
                                   "position": {"x": largo / 2, "y": 0, "z": 700 + canto / 2}})
    if material:
        doc.set_material(v, material)
    for x in (1.0, largo - 1.0):
        _une(doc, _poste(doc, x, f"Poste {x:g}"), v, kind)
    return doc, v


def _regla(reglas, prefijo):
    hits = [r for r in reglas if r["regla"].startswith(prefijo)]
    assert len(hits) == 1, [r["regla"] for r in reglas]
    return hits[0]


# ── D7: el criterio por material ──────────────────────────────────────────────────────────


def test_criterio_por_material_sin_mezclar():
    assert criterio(COPAIBA_C).tipo == "e010"
    assert criterio("copaiba").valores["grupo"] == "C"  # la especie, con su hipótesis
    assert criterio("copaiba").hipotesis
    assert criterio("pino radiata C24 (EN 338)").valores["e0_mean"] == 11000.0
    assert criterio("pino radiata").tipo == "sin_clase"  # su clase depende del grado visual
    assert criterio("triplay fenólico 18 mm").tipo == "en1995"
    assert criterio("acero A36").tipo == "metal"
    assert criterio("vidrio").tipo == "no_estructural"
    # el grupo declarado manda sobre la especie; la clase EN en el nombre también vale
    assert criterio("madera", "Travesaño (pino C16 EN 338)").valores["clase"] == "C16"
    # el tablero escrito en el NOMBRE (como lo modelan: «Tablero - triplay fenolico 18 mm»)
    t = criterio("madera", "Tablero de trabajo - triplay fenolico 18 mm EN 636-2")
    assert t.tipo == "en1995" and t.valores["e0_mean"] == 10048.0


# ── D7: flecha de la viga a medida ────────────────────────────────────────────────────────


def test_tablero_copaiba_grupo_c_con_emin_y_admisibles():
    doc, v = _apoyada("Tablero", 400.0, 20.0, COPAIBA_C)
    doc.set_requirements({"carga_kg": 30})
    r = _regla(beam_rules(doc, 30.0), "flecha de viga · Tablero")
    grupo = GRUPOS_E010["C"]
    e, i = grupo["e_min"], 400.0 * 20.0 ** 3 / 12
    q = 400 * 20 * density(COPAIBA_C) * G  # N/mm
    d_g = 5 * q * 1000.0 ** 4 / (384 * e * i)
    d_q = 30 * G * 1000.0 ** 3 / (48 * e * i)
    vg = r["viga"]
    assert vg["e_mpa"] == 5394.0 and vg["criterio"] == "e010"
    assert vg["i_mm4"] == pytest.approx(i, rel=1e-3)
    assert vg["flecha_mm"] == pytest.approx(1.8 * d_g + d_q, rel=2e-3)  # E.010 Art. 18.3
    assert vg["limite_mm"] == pytest.approx(1000.0 / 250, abs=1e-3)       # Art. 18.2 a
    assert vg["sigma_adm_mpa"] == pytest.approx(grupo["fm"])               # Art. 19.1
    assert "E.010" in r["calc"]["norma"] and "E mínimo" in r["calc"]["entradas"]["material"]
    # la carga útil la recibe el tablero, que ES la cama (y no además los postes)
    assert "carga útil" in r["calc"]["entradas"]


def test_travesano_clase_en_338_con_ec5():
    doc, v = _apoyada("Travesaño", 45.0, 95.0, "pino radiata C24 (EN 338)", largo=1500.0)
    bloque = doc.execute("create_box", {"name": "Bloque", "width": 100, "depth": 45,
                                        "height": 100, "position": {"x": 750, "y": 0, "z": 845}})
    _une(doc, bloque, v)
    r = _regla(beam_rules(doc), "flecha de viga · Travesaño")
    vg = r["viga"]
    assert vg["criterio"] == "en1995" and vg["e_mpa"] == 11000.0
    assert "EN 1995-1-1" in r["calc"]["norma"] and "7.2" in r["calc"]["norma"]
    assert vg["limite_mm"] == pytest.approx(1500.0 / 250, abs=1e-3)       # w_net,fin
    # σm,d con 1,35·G y kmod permanente 0,6 (sin carga útil): fm,d = 0,6·24/1,3
    assert vg["sigma_adm_mpa"] == pytest.approx(0.6 * 24 / 1.3, abs=0.01)


def test_tubo_rectangular_de_run_script_con_el_criterio_del_metal():
    doc = Document("t")
    tubo = doc.execute("run_script", {"name": "Tubo portante", "code": (
        "result = Pos(1000, 0, 740) * (Box(2000, 40, 80) - Box(2002, 34, 74))\n")})
    for x in (1.0, 1999.0):
        _une(doc, _poste(doc, x, f"Poste {x:g}"), tubo, "soldadura")
    doc.set_requirements({"carga_kg": 50, "carga_sobre": [tubo]})
    r = _regla(beam_rules(doc, 50.0), "flecha de viga · Tubo portante")
    vg = r["viga"]
    i = 40 * 80 ** 3 / 12 - 34 * 74 ** 3 / 12
    a = 40 * 80 - 34 * 74
    assert vg["i_mm4"] == pytest.approx(i, rel=1e-3)
    q = a * density("acero") * G
    esperado = 5 * q * 2000.0 ** 4 / (384 * 200000 * i) + 50 * G * 2000.0 ** 3 / (48 * 200000 * i)
    assert vg["flecha_mm"] == pytest.approx(esperado, rel=2e-3)
    assert vg["limite_mm"] == pytest.approx(2000 / 240, abs=1e-3)
    assert "tubo rectangular 40×80×3.0" in r["calc"]["entradas"]["perfil"]
    assert "AISC" in r["calc"]["norma"]


def test_plancha_perforada_sale_sin_evaluar_justificable():
    doc = Document("t")
    mesa = doc.execute("run_script", {"name": "Mesa perforada", "code": (
        "p = Box(1000, 500, 10)\n"
        "for i in range(9):\n"
        "    for j in range(4):\n"
        "        p = p - Pos(-400 + 100 * i, -150 + 100 * j, 0) * Cylinder(14, 20)\n"
        "result = Pos(500, 0, 705) * p\n")})
    for x in (1.0, 999.0):
        _une(doc, _poste(doc, x, f"Poste {x:g}"), mesa, "soldadura")
    reglas = beam_rules(doc, 80.0)
    r = _regla(reglas, "flecha de viga · Mesa perforada")
    assert r["no_evaluada"] and r["piezas"] == [mesa] and "no evaluada" in r["detalle"]
    assert _vigas(doc).get("sin_evaluar") == 1
    item = next(i for i in controlar_vida_util(reglas) if i.id == "vida.flecha")
    assert item.estado == SIN_EVALUAR
    js = [{"regla": r["regla"], "porque": "La plancha apoya en toda su superficie sobre el bastidor."}]
    item = next(i for i in controlar_vida_util(reglas, justificadas=js) if i.id == "vida.flecha")
    assert item.estado == OK


def test_madera_sin_clase_que_trabaja_sale_sin_evaluar():
    doc, v = _apoyada("Tablero", 400.0, 20.0, "pino radiata")
    r = _regla(beam_rules(doc, 20.0), "flecha de viga · Tablero")
    assert r["no_evaluada"] and "Grupo C (E.010)" in r["detalle"]


def test_encolado_es_apoyo_de_la_madera_y_no_del_metal():
    doc, _ = _apoyada("Tablero", 400.0, 20.0, COPAIBA_C, kind="pegado")
    assert not _regla(beam_rules(doc, 10.0), "flecha de viga · Tablero").get("no_evaluada")
    doc, _ = _apoyada("Tablero", 400.0, 20.0, "acero", kind="pegado")
    r = _regla(beam_rules(doc, 10.0), "flecha de viga · Tablero")
    assert r["no_evaluada"] and "camino de carga" in r["detalle"]


def test_pieza_a_medida_que_solo_carga_su_peso_no_se_calcula():
    doc, _ = _apoyada("Placa de cierre", 400.0, 20.0)
    assert beam_rules(doc) == []


def test_placa_de_pie_en_el_suelo_no_es_viga():
    """La pata anclada sobre su placa de pie: la placa lleva la carga al suelo, no flecta."""
    doc = Document("t")
    placa = doc.execute("create_box", {"name": "Placa de pie", "width": 300, "depth": 100,
                                       "height": 10, "position": {"x": 0, "y": 0, "z": 5}})
    pata = doc.execute("create_box", {"name": "Poste", "width": 40, "depth": 40, "height": 700,
                                      "position": {"x": 0, "y": 0, "z": 360}})
    doc.execute("ground", {"name": "g", "feature": pata})
    _une(doc, placa, pata, "soldadura")
    otra = doc.execute("create_box", {"name": "Bloque", "width": 40, "depth": 40, "height": 40,
                                      "position": {"x": 120, "y": 0, "z": 30}})
    _une(doc, otra, placa, "soldadura")
    assert beam_rules(doc) == []


def test_viga_a_medida_que_apoya_su_extremo_sobre_una_pata_ancha():
    """El apoyo va en el extremo, no en el centro del solape con la pata (sin voladizo falso)."""
    doc = Document("t")
    v = doc.execute("create_box", {"name": "Tablero", "width": 1000, "depth": 400, "height": 20,
                                   "position": {"x": 500, "y": 0, "z": 710}})
    doc.set_material(v, COPAIBA_C)
    for x in (20.0, 980.0):
        _une(doc, _poste(doc, x, f"Pata {x:g}", ancho=40.0), v)
    vg = _regla(beam_rules(doc, 10.0), "flecha de viga · Tablero")["viga"]
    assert vg["apoyos_mm"] == [0.0, 1000.0] and [t["tipo"] for t in vg["tramos"]] == ["vano"]


def test_perfil_de_catalogo_da_lo_mismo_con_piezas_a_medida_al_lado():
    def _upn(doc):
        v = doc.execute("insert_component", {
            "name": "Larguero", "component": "UPN-100", "length": 2000.0,
            "rotation": {"x": 0, "y": 90, "z": 90}, "position": {"x": 1000.0, "y": 0, "z": 750.0}})
        for x in (1.0, 1999.0):
            _une(doc, _poste(doc, x, f"Poste {x:g}"), v, "soldadura")
        return v

    doc = Document("t")
    _upn(doc)
    antes = beam_rules(doc, 40.0)
    doc2 = Document("t")
    _upn(doc2)
    doc2.execute("create_box", {"name": "Placa suelta", "width": 600, "depth": 300,
                                "height": 10, "position": {"x": 0, "y": 3000, "z": 5}})
    despues = beam_rules(doc2, 40.0)
    assert [r["viga"] for r in antes] == [r["viga"] for r in despues]
    assert [r["calc"] for r in antes] == [r["calc"] for r in despues]


# ── D7: pandeo de la columna a medida ─────────────────────────────────────────────────────


def test_montante_de_madera_en_338_pandea_con_ec5():
    doc = Document("t")
    m = doc.execute("create_box", {"name": "Montante", "width": 45, "depth": 45, "height": 1200,
                                   "position": {"x": 0, "y": 0, "z": 600}})
    doc.set_material(m, "pino radiata C24 (EN 338)")
    doc.execute("ground", {"name": "g", "feature": m})
    tapa = doc.execute("create_box", {"name": "Bandeja", "width": 300, "depth": 300,
                                      "height": 20, "position": {"x": 0, "y": 0, "z": 1210}})
    _une(doc, tapa, m)
    r = _regla(columna_rules(doc, 100.0), "pandeo de columna · Montante")
    calc = r["calc"]
    assert "6.3.2" in calc["norma"] and calc["fs_min"] == 1.0
    lam = 2.1 * 1200 / (45 / math.sqrt(12))
    lam_rel = lam / math.pi * math.sqrt(21 / 7400)
    k = 0.5 * (1 + 0.2 * (lam_rel - 0.3) + lam_rel ** 2)
    kc = 1 / (k + math.sqrt(k * k - lam_rel ** 2))
    n = float(calc["entradas"]["carga axial"].split()[0])
    fs = kc * 0.8 * 21 / 1.3 / (1.5 * n / 45 ** 2)
    assert calc["fs"] == pytest.approx(fs, rel=0.02)


def test_montante_copaiba_con_las_formulas_de_la_e010():
    doc = Document("t")
    m = doc.execute("create_box", {"name": "Poste de copaiba", "width": 70, "depth": 70,
                                   "height": 1500, "position": {"x": 0, "y": 0, "z": 750}})
    doc.set_material(m, COPAIBA_C)
    doc.execute("ground", {"name": "g", "feature": m})
    tapa = doc.execute("create_box", {"name": "Bandeja", "width": 300, "depth": 300,
                                      "height": 20, "position": {"x": 0, "y": 0, "z": 1510}})
    _une(doc, tapa, m)
    r = _regla(columna_rules(doc, 200.0), "pandeo de columna · Poste de copaiba")
    lam = 2.1 * 1500 / 70  # 45 > Ck 18,4: columna larga
    n_adm = math.pi ** 2 * 5394 * (70 ** 4 / 12) / (2.5 * (2.1 * 1500) ** 2)
    assert "larga" in r["calc"]["sustitucion"] and f"{lam:.1f}" in r["calc"]["sustitucion"]
    n = float(r["calc"]["entradas"]["carga axial"].split()[0])
    assert r["calc"]["fs"] == pytest.approx(n_adm / n, rel=0.02)
    item = next(i for i in controlar_vida_util([r]) if i.id == "vida.pandeo")
    assert item.estado == (OK if n_adm / n >= 1 else FALLA)


def test_montante_que_solo_cumple_arriostrado_sale_sin_evaluar():
    """Un montante de estantería de 2 m (45×45, copaiba): con la cabeza libre λ = 93 ≥ 50
    (E.010 Art. 27.2); arriostrado (K = 1) cumple → SIN_EVALUAR justificable, no error."""
    doc = Document("t")
    m = doc.execute("create_box", {"name": "Montante", "width": 45, "depth": 45, "height": 1990,
                                   "position": {"x": 0, "y": 0, "z": 995}})
    doc.set_material(m, COPAIBA_C)
    doc.execute("ground", {"name": "g", "feature": m})
    tapa = doc.execute("create_box", {"name": "Bandeja", "width": 300, "depth": 300,
                                      "height": 20, "position": {"x": 0, "y": 0, "z": 2000}})
    _une(doc, tapa, m)
    r = _regla(columna_rules(doc, 20.0), "pandeo de columna · Montante")
    assert r["no_evaluada"] and "arriostrada (K = 1)" in r["detalle"]
    item = next(i for i in controlar_vida_util([r]) if i.id == "vida.pandeo")
    assert item.estado == SIN_EVALUAR


# ── D8: el vuelco con las fuerzas de trabajo ──────────────────────────────────────────────


def _mesa(vuelo_y=0.0):
    """Mesa de acero 1000×600 con cuatro patas en las esquinas (base 1000×600) y la cubierta a
    900 mm; `vuelo_y` hace volar la cubierta hacia +Y y −Y."""
    doc = Document("mesa")
    doc.execute("create_box", {"name": "Cubierta", "width": 1000, "depth": 600 + 2 * vuelo_y,
                               "height": 10, "position": {"x": 0, "y": 0, "z": 895}})
    for sx in (-1, 1):
        for sy in (-1, 1):
            _poste(doc, sx * 485, f"Pata {sx}{sy}", y=sy * 285, alto=890, ancho=30, fondo=30)
    return doc


def _vuelco(doc, carga=None):
    return [r for r in structure_rules(doc, carga, None)
            if r["regla"].startswith("estabilidad al vuelco")]


def test_sin_requisitos_el_vuelco_es_el_de_siempre_y_lo_dice():
    reglas = _vuelco(_mesa())
    assert [r["regla"] for r in reglas] == ["estabilidad al vuelco"]
    assert reglas[0]["estado"] == "ok" and "Sin fuerzas de trabajo declaradas" in reglas[0]["detalle"]
    assert requisitos_vuelco({"carga_kg": 50}) is None


def test_mesa_empujada_vuelca_vacia_y_no_con_carga():
    doc = _mesa()
    doc.set_requirements({"carga_kg": 60, "fuerza_horizontal_n": 200, "altura_fuerza_mm": 900})
    r = _regla(_vuelco(doc, 60.0), "estabilidad al vuelco · fuerzas de trabajo")
    props = scene_mass_properties(doc.scene, None, None, doc.default_material(),
                                  include_hidden=True)
    w = props["total"]["masa_kg"] * G
    brazo = 300.0  # COG al centro, arista de la base a y = ±300
    fs = 0.9 * w * brazo / (1.5 * 200 * 900)
    assert r["estado"] == "error" and r["calc"]["fs"] == pytest.approx(fs, abs=0.01)
    assert fs < 1.0 <= 0.9 * (w + 60 * G) * brazo / (1.5 * 200 * 900)  # con carga no volcaría
    assert f"F_h ≈ {w * brazo / 900:.0f} N" in r["detalle"]  # «se cae a partir de ≈ … N»
    assert "no se cuenta" in r["calc"]["resultado"]
    item = next(i for i in controlar_vida_util(_vuelco(doc, 60.0)) if i.id == "vida.vuelco")
    assert item.estado == FALLA


def test_carga_de_borde_en_el_canto_que_vuela():
    doc = _mesa(vuelo_y=150.0)
    doc.set_requirements({"carga_borde_n": 1000})
    r = _regla(_vuelco(doc), "estabilidad al vuelco · fuerzas de trabajo")
    assert "150 mm fuera de la arista" in r["calc"]["entradas"]["carga de borde"]
    props = scene_mass_properties(doc.scene, None, None, "acero", include_hidden=True)
    w = props["total"]["masa_kg"] * G
    assert r["calc"]["fs"] == pytest.approx(0.9 * w * 300 / (1.5 * 1000 * 150), abs=0.01)


def test_las_claves_del_vuelco_se_validan_como_numeros():
    req = normalizar_requisitos({"fuerza_horizontal_n": "200", "altura_fuerza_mm": 900,
                                 "carga_borde_n": 500})
    assert req == {"fuerza_horizontal_n": 200.0, "altura_fuerza_mm": 900.0, "carga_borde_n": 500.0}
    with pytest.raises(ValueError):
        normalizar_requisitos({"fuerza_horizontal_n": -5})
