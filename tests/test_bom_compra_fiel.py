"""La BOM sirve para comprar y para cortar (plan bom-de-compra-fiel, F1: D1–D6).

Cada decisión con su caso mínimo de comandos y, si están en la máquina, con los `.apolo` reales de
la tanda de pilotos que la motivaron (`C:\\t\\maq\\<slug>\\<slug>-correccion1.apolo`, fuera del
repo: sólo lectura; sin ellos esos casos se saltan).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apolo.doc.document import Document
from apolo.library.bom import bom_from_scene
from apolo.library.catalog import CATALOG
from apolo.library.cutlist import cut_list
from apolo.library.fijacion import ARANDELAS_DIN125, TUERCAS_DIN985, perno_pasante
from apolo.library.tornilleria_declarada import filas_declaradas

MAQ = Path(r"C:\t\maq")


def _real(slug: str) -> Document:
    ruta = MAQ / slug / f"{slug}-correccion1.apolo"
    if not ruta.exists():
        pytest.skip(f"sin el .apolo real de {slug} (fuera del repo)")
    return Document.from_apolo_bytes(ruta.read_bytes())


def _bom(doc: Document) -> list[dict]:
    return bom_from_scene(doc.scene, doc.default_material())


def _filas(doc: Document, rep: str) -> list[dict]:
    return [r for r in _bom(doc) if r["_rep"] == rep]


# ---------------------------------------------------------------- D1: chapa por su ficha

def test_d1_la_chapa_con_ficha_sale_con_espesor_desarrollo_y_norma():
    d = Document("chapa")
    p = d.execute("create_sheet_metal", {"name": "Placa base", "ancho": 200, "fondo": 200,
                                         "espesor": 10, "lados": []})
    u = d.execute("create_sheet_metal", {"name": "Peldaño", "ancho": 118, "fondo": 600,
                                         "espesor": 3, "lados": ["izquierda", "derecha"],
                                         "altura_pestana": 37})
    (placa,) = _filas(d, p)
    assert placa["espesor_mm"] == 10.0 and placa["desarrollo_mm"] == [200.0, 200.0]
    assert placa["material"] == "acero" and placa["norma"].startswith("ASTM A36")
    assert "chapa e=10 mm, desarrollo 200×200 mm" in placa["descripcion"]
    (pel,) = _filas(d, u)
    (corte,) = [r for r in cut_list(d.scene) if r["nombre"] == "Peldaño"]
    # el MISMO desarrollo de la lista de corte (una fuente: chapa_ficha)
    assert pel["desarrollo_mm"] == [corte["ancho_mm"], corte["largo_mm"]]
    assert pel["espesor_mm"] == 3.0 and pel["pliegues"] == 2
    assert pel["longitud_mm"] == corte["largo_mm"]


def test_d1_la_norma_que_nombra_la_pieza_gana_y_sin_ficha_nada_cambia():
    d = Document("chapa-norma")
    m = d.execute("create_sheet_metal", {"name": "Montante - chapa e2 ASTM A1011 SS Gr33",
                                         "ancho": 100, "fondo": 900, "espesor": 2,
                                         "lados": ["izquierda", "derecha"], "altura_pestana": 30})
    b = d.execute("create_box", {"name": "Taco", "width": 50, "depth": 40, "height": 20})
    assert _filas(d, m)[0]["norma"] == "ASTM A1011"
    (taco,) = _filas(d, b)
    # sin ficha: sin espesor ni desarrollo; la norma del acero genérico (D3 de
    # hallazgos-del-revisor-en-la-puerta: toda pieza a medida de metal lleva la suya)
    assert taco["norma"].startswith("ASTM A36") and "espesor_mm" not in taco


def test_d1_tolva_real_cada_chapa_con_ficha_tiene_espesor_material_y_norma():
    d = _real("tolva-piramidal-05")
    con_ficha = {fid for fid, f in d.scene.items() if getattr(f, "chapa", None)}
    assert con_ficha
    filas = [r for r in _bom(d) if r["_rep"] in con_ficha]
    assert filas and all(r["espesor_mm"] > 0 and r["material"] and r["norma"] for r in filas)


# ---------------------------------------------------------------- D2: corte medido

def _riostras() -> tuple[Document, str]:
    d = Document("riostras")
    a = d.execute("insert_component", {"component": "TUBO-2X2", "name": "Poste (1)",
                                       "length": 1200, "position": {"z": 600}})
    b = d.execute("insert_component", {"component": "TUBO-2X2", "name": "Poste (2)",
                                       "length": 1200, "position": {"x": 1000, "z": 600}})
    r = d.execute("create_brace", {"name": "Riostra", "perfil": "TUBO-1X1",
                                   "a": {"pieza": a, "punto": {"z": 200}},
                                   "b": {"pieza": b, "punto": {"x": 1000, "z": 1000}}})
    d.execute("pattern_linear", {"feature": r, "count": 3, "spacing": {"y": 400}})
    return d, r


def test_d2_la_copia_de_patron_agrupa_con_su_original_con_el_angulo_medido():
    d, r = _riostras()
    copias = [f for fid, f in d.scene.items() if fid != r and f.name.startswith("Riostra")]
    assert len(copias) == 2 and all(getattr(f, "miter", None) is None for f in copias)
    filas = [x for x in _bom(d) if x["ref"] == "TUBO-1X1"]
    assert len(filas) == 1  # antes: 1 fila con ∠ (el original) y otra «recta» (las copias)
    (fila,) = filas
    assert fila["cantidad"] == 3 and "∠" in fila["descripcion"]
    a1, a2 = d.scene[r].miter
    assert fila["descripcion"].endswith(f"∠{a1:g}°/{a2:g}°")  # el texto del comando, que coincide
    assert fila["longitud_mm"] == pytest.approx(d.scene[r].cut_length)
    assert "aviso" not in fila


def test_d2_lo_declarado_que_no_es_lo_medido_cede_y_avisa():
    d = Document("zanca")
    ctx = d.execute("create_box", {"name": "Apoyo", "width": 10, "depth": 10, "height": 10,
                                   "position": {"x": 3000}})
    p = d.execute("insert_component", {"component": "UPN-120", "name": "Zanca", "length": 1200,
                                       "orientacion": {"largo": "z", "abre_hacia": "+y"}})
    d.execute("transform", {"feature": p, "rotate": {"y": 50}})
    bb = d.scene[p].shape.bounding_box()
    for pos, w, h, prof in (((bb.max.X - 150 + 500, 0, 0), 1000, 400, 2000),
                            ((0, 0, bb.min.Z + 150 - 500), 2000, 400, 1000)):
        d.execute("add_joinery", {"name": "corte", "type": "rebaje", "feature_a": ctx,
                                  "feature_b": p, "position": dict(zip("xyz", pos)),
                                  "width": w, "height": h, "depth": prof})
    (fila,) = _filas(d, p)
    (corte,) = [r for r in cut_list(d.scene) if r["nombre"] == "Zanca"]
    assert fila["longitud_mm"] == corte["largo_mm"] < 1100  # el exterior medido, no 1200
    assert "∠" in fila["descripcion"] and "aviso" in fila


def test_d2_rack_real_las_diagonales_salen_en_una_fila_con_su_angulo():
    d = _real("rack-selectivo-2400")
    diag = [r for r in _bom(d) if r["ref"] == "TUBO-1.5X1.5" and r["longitud_mm"] == 765.4]
    assert len(diag) == 1 and diag[0]["cantidad"] == 8
    assert diag[0]["descripcion"].endswith("∠33.2°/33.2°")


def test_d2_paneles_real_la_diagonal_y_sus_copias_comparten_fila():
    d = _real("soporte-paneles-4")
    diag = [r for r in _bom(d) if r["ref"] == "TUBO-1.5X1.5" and r["longitud_mm"] == 1480.7]
    assert len(diag) == 1 and diag[0]["cantidad"] == 3 and "∠17.7°" in diag[0]["descripcion"]


# ---------------------------------------------------------------- D3: la pieza que se fabrica

def test_d3_piezas_de_la_misma_ref_con_taladros_distintos_no_comparten_fila():
    d = Document("patas")
    a = d.execute("insert_component", {"component": "ANG-75X6", "name": "Pata", "length": 700})
    d.execute("pattern_linear", {"feature": a, "count": 3, "spacing": {"x": 300}})
    bb = d.scene[a].shape.bounding_box()
    v0 = d.scene[a].shape.volume
    d.execute("drill_hole", {"feature": a, "diameter": 4, "depth": 0, "axis": "-x",
                             "position": {"x": bb.max.X + 5, "y": bb.min.Y + 3, "z": 0}})
    assert d.scene[a].shape.volume < v0 - 50  # el taladro cruzó un ala
    filas = [r for r in _bom(d) if r["ref"] == "ANG-75X6"]
    assert sorted(r["cantidad"] for r in filas) == [1, 2]  # la taladrada aparte de las 2 lisas
    assert all(r.get("marca") for r in filas)  # cada fila dice qué pieza es (la de su plano)
    assert len({r["descripcion"] for r in filas}) == 2


def test_d3_las_copias_identicas_siguen_en_una_fila():
    d = Document("patas-lisas")
    a = d.execute("insert_component", {"component": "ANG-75X6", "name": "Pata", "length": 700})
    d.execute("pattern_linear", {"feature": a, "count": 4, "spacing": {"x": 300}})
    (fila,) = [r for r in _bom(d) if r["ref"] == "ANG-75X6"]
    assert fila["cantidad"] == 4 and "marca" not in fila


def test_d3_paneles_real_las_tres_patas_traseras_son_tres_piezas():
    d = _real("soporte-paneles-4")
    patas = [r for r in _bom(d) if r["ref"] == "ANG-75X6"
             and round(r["longitud_mm"], 1) == 706.8]
    assert len(patas) == 3 and all(r["cantidad"] == 1 for r in patas)
    assert {r["marca"] for r in patas} == {"c58", "c98_1", "c98_2"}


# ---------------------------------------------------------------- D4: la tuerca una sola vez

def test_d4_la_tuerca_modelada_de_otra_norma_tras_la_arandela_no_se_compra_dos_veces():
    d = Document("tuerca")
    a = d.execute("create_box", {"name": "Pletina", "width": 100, "depth": 100, "height": 10,
                                 "position": {"z": 5}})
    b = d.execute("create_box", {"name": "Ménsula", "width": 100, "depth": 100, "height": 10,
                                 "position": {"z": 15}})
    d.execute("create_cylinder", {"name": "Perno M10x35 DIN 933", "radius": 5, "height": 37,
                                  "position": {"z": 3.5}})
    d.execute("create_cylinder", {"name": "Arandela M10 DIN 125-A", "radius": 10, "height": 2,
                                  "position": {"z": -1}})
    d.execute("create_cylinder", {"name": "Tuerca autoblocante M10 DIN 985", "radius": 8.5,
                                  "height": 10, "position": {"z": -7}})  # a 2 mm de la pletina
    d.execute("fasten", {"name": "Pletina_mensula", "a": a, "b": b, "kind": "perno",
                         "size": "M10", "qty": 1, "nota": "perno M10x35 + arandela + tuerca"})
    assert filas_declaradas(d.scene, d.fasteners) == []


def test_d4_carro_real_compra_8_tuercas_para_8_pernos():
    d = _real("carro-plataforma-800")
    extra = [r for r in filas_declaradas(d.scene, d.fasteners) if r["categoria"] == "tuercas"]
    assert extra == []
    modeladas = [r for r in _bom(d) if r["categoria"] == "tuercas"
                 and "manubrio" in r["descripcion"]]
    assert sum(r["cantidad"] for r in modeladas) == 8


# ---------------------------------------------------------------- D5: arandela en join_bolted

def _placas(d: Document, t: float = 12.0) -> tuple[str, str]:
    a = d.execute("create_box", {"name": "Placa A", "width": 200, "depth": 100, "height": t,
                                 "position": {"z": t / 2}})
    b = d.execute("create_box", {"name": "Placa B", "width": 200, "depth": 100, "height": t,
                                 "position": {"z": 1.5 * t}})
    return a, b


def test_d5_el_largo_del_perno_cuenta_la_arandela_y_la_tuerca_autoblocante():
    assert perno_pasante("M10", 24).largo == 35  # 24 + 8 + 2·1,5 = 35
    assert perno_pasante("M10", 24, arandela=True).largo == 40  # + 2 de la arandela
    f = perno_pasante("M10", 24, arandela=True, tuerca="din985")
    assert f.largo == 40 and f.tuerca == "TUERCA-AB-M10" and f.arandela == "ARANDELA-M10"


def test_d5_join_bolted_nuevo_trae_arandelas_din125_en_la_bom():
    d = Document("jb-arandela")
    a, b = _placas(d)
    cid = d.execute("join_bolted", {"a": a, "b": b, "size": "M10", "count": 2})
    assert d.commands[-1]["params"]["arandela"] is True  # el sello
    bom = {r["ref"]: r for r in _bom(d)}
    assert bom["ARANDELA-M10"]["cantidad"] == 2 and bom["ARANDELA-M10"]["norma"].startswith("DIN 125")
    assert bom["PERNO-HEX-M10"]["longitud_mm"] == 40  # sin arandela serían 35
    assert bom["TUERCA-M10"]["cantidad"] == 2
    # la arandela entre la base y la tuerca, la tuerca encima: nada se solapa
    ar = d.scene[f"{cid}_arandela1"].shape.bounding_box()
    tu = d.scene[f"{cid}_tuerca1"].shape.bounding_box()
    assert ar.max.Z == pytest.approx(0.0, abs=1e-6) and ar.min.Z == pytest.approx(-2.0, abs=1e-6)
    assert tu.max.Z == pytest.approx(-2.0, abs=1e-6)
    assert filas_declaradas(d.scene, d.fasteners) == []


def test_d5_arandela_false_y_tuerca_din985():
    d = Document("jb-sin")
    a, b = _placas(d)
    d.execute("join_bolted", {"a": a, "b": b, "size": "M10", "count": 2, "arandela": False,
                              "tuerca": "din985"})
    bom = {r["ref"]: r for r in _bom(d)}
    assert "ARANDELA-M10" not in bom
    assert bom["TUERCA-AB-M10"]["cantidad"] == 2 and "TUERCA-M10" not in bom
    assert bom["PERNO-HEX-M10"]["longitud_mm"] == 40  # 24 + 10 (DIN 985) + 3


def test_d5_un_log_viejo_regenera_sin_arandelas():
    """El comando guardado SIN el campo (todo log anterior) regenera igual: sin arandela."""
    d = Document("jb-viejo")
    a, b = _placas(d)
    d.execute("join_bolted", {"a": a, "b": b, "size": "M10", "count": 2})
    cmds = [dict(c, params={k: v for k, v in c["params"].items() if k != "arandela"})
            for c in d.commands]
    viejo = Document.from_apolo_bytes(_con_comandos(d, cmds))
    refs = {r["ref"]: r for r in _bom(viejo)}
    assert "ARANDELA-M10" not in refs and refs["PERNO-HEX-M10"]["longitud_mm"] == 35


def _con_comandos(d: Document, cmds: list[dict]) -> bytes:
    d.commands = cmds
    return d.to_apolo_bytes()


def test_d5_el_catalogo_es_espejo_de_las_tablas():
    for m, (d1, d2, h) in ARANDELAS_DIN125.items():
        for ref in (f"ARANDELA-{m}", f"ARANDELA-{m}-A2"):
            p = CATALOG[ref].params
            assert (p["d1"], p["d2"], p["h"]) == (d1, d2, h)
            assert CATALOG[ref].category == "arandelas"
    for m, h in TUERCAS_DIN985.items():
        comp = CATALOG[f"TUERCA-AB-{m}"]
        assert comp.params["thickness"] == h and comp.specs["norma"].startswith("DIN 985")


# ---------------------------------------------------------------- D6: pernos no aislados

def test_d6_la_tornilleria_de_join_bolted_no_sale_aislada_en_check_assembly():
    from fastapi.testclient import TestClient

    from apolo.api import main as api

    d = Document("jb-aislados")
    a, b = _placas(d)
    d.execute("join_bolted", {"a": a, "b": b, "size": "M10", "count": 2})
    api.DOC = d
    r = TestClient(api.app).post("/api/assembly/soundness", json={})
    assert r.status_code == 200
    assert r.json()["isolated"] == []  # antes: los 2 pernos, 2 arandelas y 2 tuercas


def test_d6_paneles_real_sin_pernos_aislados():
    from fastapi.testclient import TestClient

    from apolo.api import main as api

    api.DOC = _real("soporte-paneles-4")
    rep = TestClient(api.app).post("/api/assembly/soundness", json={}).json()
    assert not [f for f in rep["isolated"] if "_perno" in f or "_tuerca" in f]
