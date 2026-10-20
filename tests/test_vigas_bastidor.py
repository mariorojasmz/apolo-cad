"""Flecha de las vigas de cualquier bastidor (plan flecha-de-bastidor, F2): detección por el
grafo de uniones (D1), cargas (D2), criterio L/240 + 0.6·fy (D3) y sin duplicar la faja (D4)."""

from __future__ import annotations

import dataclasses

import pytest

from apolo.doc.document import Document
from apolo.library.catalog import CATALOG
from apolo.library.engineering.secciones import angulo_libre
from apolo.library.engineering.viga_bastidor import orientar_seccion
from apolo.library.materials import density, resolve_material
from apolo.services.engineering_rules import structure_rules
from apolo.services.vigas_rules import beam_rules

G = 9.81
E = 200000.0
I_UPN100 = 206e4
Q_UPN100 = CATALOG["UPN-100"].weight * G / 1000.0  # N/mm
CANTO_VERTICAL = {"x": 0, "y": 90, "z": 90}  # UPN extruido en Z → eje en X, canto (h) en Z


def _viga(doc, nombre="Larguero", largo=2000.0, y=0.0, z=750.0, ref="UPN-100"):
    doc.execute("insert_component", {
        "name": nombre, "component": ref, "length": largo, "rotation": CANTO_VERTICAL,
        "position": {"x": largo / 2.0, "y": y, "z": z}})
    return doc.commands[-1]["id"]


def _poste(doc, x, nombre, y=0.0, ancho=2.0, alto=700.0, tierra=True):
    doc.execute("create_box", {"name": nombre, "width": ancho, "depth": 50, "height": alto,
                               "position": {"x": x, "y": y, "z": alto / 2.0}})
    fid = doc.commands[-1]["id"]
    if tierra:
        doc.execute("ground", {"name": f"g_{fid}", "feature": fid})
    return fid


def _une(doc, a, b, kind="soldadura"):
    doc.execute("fasten", {"name": f"u_{a}_{b}", "a": a, "b": b, "kind": kind})


def _apoyada(largo=2000.0, xs=(1.0, None), kind="soldadura"):
    """Viga UPN-100 sobre postes delgados (2 mm) anclados: x = 1 y x = L−1 → apoyos en los
    extremos (el solape se pega al extremo)."""
    doc = Document("t")
    v = _viga(doc, largo=largo)
    for k, x in enumerate(xs):
        p = _poste(doc, largo - 1.0 if x is None else x, f"Poste {k}")
        _une(doc, p, v, kind)
    return doc, v


def _ss(q, largo, p=0.0, ei=E * I_UPN100):
    return 5 * q * largo**4 / (384 * ei) + p * largo**3 / (48 * ei)


def _una(reglas):
    assert len(reglas) == 1, [r["regla"] for r in reglas]
    return reglas[0]


# ── D1: detección ──────────────────────────────────────────────────────────────────────────


def test_viga_apoyada_en_dos_patas_peso_propio():
    doc, _ = _apoyada()
    r = _una(beam_rules(doc))
    v = r["viga"]
    assert r["regla"] == "flecha de viga · Larguero" and r["estado"] == "ok"
    assert v["apoyos_mm"] == [0.0, 2000.0]
    assert v["i_mm4"] == pytest.approx(I_UPN100)
    assert v["flecha_mm"] == pytest.approx(_ss(Q_UPN100, 2000.0), rel=1e-4)
    assert v["momento_nmm"] == pytest.approx(Q_UPN100 * 2000.0**2 / 8, rel=1e-4)
    assert v["limite_mm"] == pytest.approx(2000.0 / 240, abs=1e-3)
    calc = r["calc"]
    assert "DIN 1026-1" in calc["entradas"]["perfil"] and "0.60·F_y" in calc["norma"]
    assert r["hipotesis"] and r["no_aplica"] == []


def test_voladizos_por_tramo_y_su_limite():
    doc, _ = _apoyada(xs=(400.0, 1600.0))
    v = _una(beam_rules(doc))["viga"]
    assert v["apoyos_mm"] == [400.0, 1600.0]
    tipos = [(t["tipo"], t["desde_mm"], t["hasta_mm"], t["limite_mm"]) for t in v["tramos"]]
    assert tipos == [("voladizo", 0.0, 400.0, pytest.approx(2 * 400 / 240, abs=1e-3)),
                     ("vano", 400.0, 1600.0, pytest.approx(1200 / 240, abs=1e-3)),
                     ("voladizo", 1600.0, 2000.0, pytest.approx(2 * 400 / 240, abs=1e-3))]


def test_una_sola_soldadura_es_voladizo_empotrado():
    doc, _ = _apoyada(xs=(1.0,))
    v = _una(beam_rules(doc))["viga"]
    assert v["tramos"][0]["tipo"] == "voladizo"
    assert v["flecha_mm"] == pytest.approx(Q_UPN100 * 2000.0**4 / (8 * E * I_UPN100), rel=1e-4)


def test_un_solo_perno_no_es_viga():
    doc, _ = _apoyada(xs=(1.0,), kind="perno")
    assert beam_rules(doc) == []


def test_contacto_no_cuenta_como_apoyo():
    doc, _ = _apoyada(kind="contacto")
    assert beam_rules(doc) == []


def test_pieza_que_no_es_viga():
    doc = Document("t")
    doc.execute("insert_component", {"name": "Columna", "component": "UPN-100", "length": 700,
                                     "position": {"x": 0, "y": 0, "z": 350}})
    col = doc.commands[-1]["id"]
    doc.execute("ground", {"name": "g", "feature": col})
    caja = _poste(doc, 500.0, "Caja", tierra=False)
    _une(doc, caja, col)
    assert beam_rules(doc) == []  # vertical = columna (pandeo), caja = no es perfil


def test_maquina_sin_vigas_da_la_memoria_de_siempre():
    doc = Document("t")
    a = _poste(doc, 0.0, "Base")
    b = _poste(doc, 0.0, "Encima", tierra=False)
    _une(doc, a, b, "perno")
    assert beam_rules(doc, 100.0) == []
    assert not any(r["regla"].startswith("flecha de viga") for r in structure_rules(doc, 100.0, None))


# ── D2: cargas ─────────────────────────────────────────────────────────────────────────────


def test_lo_que_cuelga_es_puntual_en_su_solape():
    doc, v = _apoyada()
    doc.execute("create_box", {"name": "Bloque de lastre", "width": 20, "depth": 200,
                               "height": 200, "position": {"x": 1000, "y": 0, "z": 900}})
    bloque = doc.commands[-1]["id"]
    _une(doc, bloque, v)
    f = doc.scene[bloque]
    p = 20 * 200 * 200 * density(resolve_material(f)) * G
    r = _una(beam_rules(doc))
    assert r["viga"]["flecha_mm"] == pytest.approx(_ss(Q_UPN100, 2000.0, p), rel=1e-4)
    assert "1 puntual" in r["calc"]["entradas"]["lo que cuelga"]


def test_travesano_baja_sus_reacciones_a_los_largueros():
    doc = Document("t")
    a = _viga(doc, "Larguero A", y=-275.0)
    b = _viga(doc, "Larguero B", y=275.0)
    for y, lar in ((-275.0, a), (275.0, b)):
        for x in (1.0, 1999.0):
            _une(doc, _poste(doc, x, f"Pata {x:g} {y:g}", y=y), lar)
    doc.execute("insert_component", {
        "name": "Travesaño", "component": "UPN-100", "length": 600,
        "rotation": {"x": 90, "y": 0, "z": 0}, "position": {"x": 1000, "y": 0, "z": 850}})
    trav = doc.commands[-1]["id"]
    bb = doc.scene[trav].shape.bounding_box()
    assert round(bb.max.Y - bb.min.Y) == 600 and round(bb.max.Z - bb.min.Z) in (50, 100)
    _une(doc, trav, a)
    _une(doc, trav, b)
    reglas = {r["regla"]: r for r in beam_rules(doc)}
    assert "flecha de viga · Travesaño" in reglas
    t = reglas["flecha de viga · Travesaño"]["viga"]
    assert t["apoyos_mm"] == [25.0, 575.0]
    # los dos largueros son iguales → una sola regla que los nombra
    lar = reglas["flecha de viga · Larguero A y 1 igual(es)"]["viga"]
    assert lar["piezas"] == ["Larguero A", "Larguero B"]
    r_trav = CATALOG["UPN-100"].weight * 0.6 * G / 2
    assert lar["flecha_mm"] == pytest.approx(_ss(Q_UPN100, 2000.0, r_trav), rel=1e-4)


def test_carga_util_puntual_movil_en_el_centro():
    doc, _ = _apoyada()
    v = _una(beam_rules(doc, 50.0))["viga"]
    assert v["flecha_mm"] == pytest.approx(_ss(Q_UPN100, 2000.0, 50.0 * G), rel=1e-4)


# ── D3: criterio ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("carga, estado", [(None, "ok"), (287.0, "aviso"), (800.0, "error")])
def test_verde_aviso_error_segun_l240(carga, estado):
    doc, _ = _apoyada(largo=6000.0)
    r = _una(beam_rules(doc, carga))
    v = r["viga"]
    assert r["estado"] == estado
    u = v["flecha_mm"] / v["limite_mm"]
    assert {"ok": u <= 1, "aviso": 1 < u <= 2, "error": u > 2}[estado]
    if estado == "aviso":  # la flecha manda: la tensión sigue bajo 0.6·fy
        assert v["sigma_mpa"] < v["sigma_adm_mpa"] and r.get("recomendacion")


def test_orientar_seccion_upn_y_angulo():
    p = CATALOG["UPN-100"].params
    fuerte = orientar_seccion("channel", p, 100.0, 50.0)
    debil = orientar_seccion("channel", p, 50.0, 100.0)
    assert fuerte.i_mm4 == pytest.approx(206e4) and debil.i_mm4 == pytest.approx(29.3e4)
    assert "DÉBIL" in debil.eje and not debil.notas  # de tabla: sin rebaja
    fuera = orientar_seccion("channel", {"h": 100, "b": 50, "tw": 5, "tf": 8}, 50.0, 100.0)
    assert fuera.notas and "0.85" in fuera.notas[0]
    assert isinstance(orientar_seccion("channel", p, 80.0, 80.0), str)  # girada
    ang = orientar_seccion("angle", {"leg": 75, "t": 6}, 75.0, 75.0)
    assert ang.i_arriostrada_mm4 == pytest.approx(45.8e4)
    assert ang.i_mm4 < 45.8e4 and "principales" in ang.eje


def test_angulo_libre_contra_ejes_principales():
    lib = angulo_libre(75, 6)
    iu, iv = 2 * 45.8e4 - 18.9e4, 18.9e4
    assert lib.i_u_mm4 == pytest.approx(iu) and lib.i_v_mm4 == pytest.approx(iv)
    assert lib.i_eq_mm4 == pytest.approx(2**0.5 / (1 / iu**2 + 1 / iv**2) ** 0.5)
    assert 25.8e4 < lib.i_eq_mm4 < 26.0e4
    # σ manda en la punta interior del ala: w_eq < W geométrico (8.41 cm³)
    assert 6.4e3 < lib.w_eq_mm3 < 6.6e3
    geo = angulo_libre(75, 6.5)  # fuera de tabla → prismático, del mismo orden
    assert geo.fuente == "geometría" and 0.9 < geo.i_eq_mm4 / lib.i_eq_mm4 < 1.25


# ── D4: sin duplicar la regla de la faja ───────────────────────────────────────────────────


def test_las_vigas_de_create_conveyor_las_verifica_su_regla():
    acero = dataclasses.replace(CATALOG["PERFIL-4080"], familia="rect_tube",
                                params={"width": 40, "height": 80, "wall": 3})
    catalogo = {**CATALOG, "PERFIL-4080": acero}
    doc = Document("t")
    doc.execute("create_conveyor", {"largo": 2000})
    for k in (1, 2, 3, 4):
        doc.execute("ground", {"name": f"g{k}", "feature": f"c1_leg{k}"})
    for leg, rail in (("c1_leg1", "c1_rail1"), ("c1_leg3", "c1_rail1"),
                      ("c1_leg2", "c1_rail2"), ("c1_leg4", "c1_rail2")):
        _une(doc, leg, rail)
    assert beam_rules(doc, catalog=catalogo) == []
    # con una viga propia al lado, la de la faja aparece en `no_aplica` por D4
    v = _viga(doc, "Viga suelta", y=2000.0)
    for x in (1.0, 1999.0):
        _une(doc, _poste(doc, x, f"Pie {x:g}", y=2000.0), v)
    r = _una(beam_rules(doc, catalog=catalogo))
    assert r["regla"] == "flecha de viga · Viga suelta"
    assert any("create_conveyor" in n and "Larguero" in n for n in r["no_aplica"])
