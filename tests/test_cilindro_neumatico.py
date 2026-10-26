"""`create_pneumatic_cylinder` (plan V8.9 D5, F2): el cilindro neumático en 3D con su junta
prismática, sus accesorios de montaje ISO 15552, el empujador y una fila de BOM por cilindro."""

from __future__ import annotations

import json

import pytest

from apolo.commands.registry import CommandError
from apolo.doc import Document, DocumentError
from apolo.library.bom import bom_from_scene
from apolo.library.catalog import CATALOG, build_component, refs_in_category
from apolo.library.checks import interference_report
from apolo.library.cutlist import cut_list

CILINDROS = refs_in_category("cilindros_neumaticos")
ERRORES = (CommandError, DocumentError)
EMPUJADOR = {"ancho": 200, "alto": 80, "espesor": 8}


def _doc(**p):
    params = {"ref": "CIL-ISO15552-32", "carrera": 300, "montaje": "brida_delantera",
              "empujador": EMPUJADOR, **p}
    d = Document()
    cid = d.execute("create_pneumatic_cylinder", params)
    return d, cid


def _volumen_comun(a, b) -> float:
    r = a & b
    return 0.0 if r is None else float(r.volume)


def _posadas(d, valores):
    from apolo.robotics.pose import posed_shapes

    return posed_shapes(d, valores)[0]


# ── catálogo ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ref", CILINDROS)
def test_builder_del_catalogo_es_un_solido_con_sus_anclas(ref):
    """La caja envolvente de la F1a quedó atrás: cuerpo + vástago retraídos en UN sólido, con el
    largo total de la ficha (A de [F4] en ISO 15552) y las anclas por familia."""
    c = CATALOG[ref]
    forma, _ = build_component(ref)
    assert len(forma.solids()) == 1
    assert c.familia in ("cilindro_iso15552", "cilindro_iso6432")
    assert {"eje", "A", "B", "extremo_vastago"} <= set(c.anchors)
    bb = forma.bounding_box()
    if c.familia == "cilindro_iso15552":
        assert bb.size.X == pytest.approx(c.specs["largo_total_mm"], abs=0.01)
        assert bb.size.Y == pytest.approx(c.params["E"], abs=0.01)
        assert c.params["C"] + c.params["WH"] + c.params["AM"] == c.specs["largo_total_mm"]


# ── el super-comando ───────────────────────────────────────────────────────────────────────


def test_piezas_junta_y_uniones():
    d, cid = _doc(position={"x": 0, "y": 0, "z": 100}, eje="+Y", puertos="+Z")
    assert sorted(d.scene) == sorted(f"{cid}_{s}" for s in ("cuerpo", "vastago", "brida", "empujador"))
    nombres = {fid: f.name for fid, f in d.scene.items()}
    assert nombres[f"{cid}_cuerpo"] == "Cilindro · Cuerpo"
    assert nombres[f"{cid}_brida"] == "Cilindro · Brida delantera (MF1)"
    assert d.scene[f"{cid}_cuerpo"].component == "CIL-ISO15552-32"
    j = d.joints[f"{cid}_vastago"]
    assert (j["type"], j["parent"], j["child"]) == ("prismatica", f"{cid}_cuerpo", f"{cid}_vastago")
    assert (j["lower"], j["upper"], j["axis"]) == (0, 300, [0.0, 1.0, 0.0])
    assert "arrastre" not in j  # sin arrastrar (D5)
    jf = d.joints[f"{cid}_jf_empujador"]
    assert (jf["type"], jf["parent"], jf["child"]) == ("fija", f"{cid}_vastago", f"{cid}_empujador")
    u = {f["name"]: f for f in d.fasteners.values()}
    assert (u[f"{cid}_u_brida"]["kind"], u[f"{cid}_u_brida"]["size"], u[f"{cid}_u_brida"]["qty"]) == ("perno", "M6", 4)
    assert u[f"{cid}_u_empujador"]["size"] == "M10"
    # anclas en mundo: el eje sale por la cara delantera hacia +Y; los puertos miran a +Z
    a = d.scene[f"{cid}_cuerpo"].anchors
    assert a["eje"]["origin"] == pytest.approx([0, 0, 100]) and a["eje"]["axis"] == pytest.approx([0, 1, 0])
    assert a["A"]["axis"] == pytest.approx([0, 0, 1]) and a["A"]["origin"][1] < a["B"]["origin"][1] < 0
    assert a["A"]["origin"][2] == pytest.approx(100 + 22.5)
    br = d.scene[f"{cid}_brida"].anchors
    assert br["brida"]["origin"] == pytest.approx([0, 10, 100])  # BB = 10 (TS3017, Ø32)
    assert len([k for k in br if k.startswith("brida_agujero_")]) == 4
    ext = d.scene[f"{cid}_vastago"].anchors["extremo_vastago"]["origin"]
    assert ext == pytest.approx([0, 142 - 94, 100])  # A − C de [F4]
    # el cuerpo crece con la carrera hacia atrás
    bb = d.scene[f"{cid}_cuerpo"].shape.bounding_box()
    assert bb.min.Y == pytest.approx(-(94 + 300)) and bb.max.Y == pytest.approx(0)


@pytest.mark.parametrize("montaje", ["brida_delantera", "brida_trasera", "pies", "ninguno"])
def test_sin_interferencia_en_todo_el_recorrido(montaje):
    """Cero volumen común entre TODAS las piezas del cilindro (sin exclusiones) en la pose de
    diseño y con el vástago a 0, ¼, ½, ¾ y toda la carrera: el paso del vástago tiene holgura y
    lo demás sólo APOYA (contacto intencional, de volumen nulo)."""
    d, cid = _doc(montaje=montaje, carrera=200)
    assert interference_report(d.scene)["interferencias"] == []
    ids = sorted(d.scene)
    for s in (0, 50, 100, 150, 200):
        formas = _posadas(d, {f"{cid}_vastago": s})
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                assert _volumen_comun(formas[a], formas[b]) < 1e-6, (s, a, b)


def test_la_fk_mueve_vastago_y_empujador():
    d, cid = _doc(eje="-X", puertos="+Y")
    formas = _posadas(d, {f"{cid}_vastago": 150})
    for suf in ("vastago", "empujador"):
        antes, despues = d.scene[f"{cid}_{suf}"].shape.bounding_box(), formas[f"{cid}_{suf}"].bounding_box()
        assert despues.min.X == pytest.approx(antes.min.X - 150)
    assert formas[f"{cid}_cuerpo"] is d.scene[f"{cid}_cuerpo"].shape


def test_iso6432_por_la_nariz():
    d, cid = _doc(ref="CIL-ISO6432-20", carrera=100, empujador={"ancho": 60, "alto": 40, "espesor": 5})
    assert sorted(d.scene) == sorted(f"{cid}_{s}" for s in ("cuerpo", "vastago", "empujador"))
    a = d.scene[f"{cid}_cuerpo"].anchors
    assert {"brida", "nariz", "pasador", "A", "B"} <= set(a)
    assert interference_report(d.scene)["interferencias"] == []
    with pytest.raises(ERRORES, match="NARIZ"):
        _doc(ref="CIL-ISO6432-20", carrera=100, montaje="pies")


def test_errores_accionables():
    with pytest.raises(ERRORES, match="fuera del rango de su ficha"):
        _doc(carrera=1200)  # Ø32: 10–1000 (SMC C96, pág. PDF 5)
    with pytest.raises(ERRORES, match="perpendicular"):
        _doc(eje="+X", puertos="-X")
    with pytest.raises(ERRORES, match="buje roscado"):
        _doc(empujador={"ancho": 15, "alto": 80, "espesor": 8})
    with pytest.raises(ERRORES, match="no es un cilindro"):
        _doc(ref="CIL-ISO15552-99")


def test_carrera_por_expresion_y_su_junta():
    d = Document()
    d.execute("set_variable", {"name": "carrera", "expression": "250"})
    cid = d.execute("create_pneumatic_cylinder", {"ref": "CIL-ISO15552-50", "carrera": "=carrera",
                                                   "montaje": "pies"})
    assert d.joints[f"{cid}_vastago"]["upper"] == 250
    var = next(c["id"] for c in d.commands if c["type"] == "set_variable")
    d.edit(var, {"name": "carrera", "expression": "400"})
    assert d.joints[f"{cid}_vastago"]["upper"] == 400
    assert d.scene[f"{cid}_cuerpo"].cut_length == 400


# ── BOM: una fila por cilindro ─────────────────────────────────────────────────────────────


def test_una_fila_de_bom_por_cilindro():
    d = Document()
    for x, carrera in ((0, 300), (200, 300), (400, 150)):
        d.execute("create_pneumatic_cylinder", {"ref": "CIL-ISO15552-32", "carrera": carrera,
                                                "montaje": "pies", "position": {"x": x}})
    filas = bom_from_scene(d.scene)
    cil = [f for f in filas if f["ref"] == "CIL-ISO15552-32"]
    assert sorted((f["cantidad"], f["longitud_mm"]) for f in cil) == [(1, 150.0), (2, 300.0)]
    assert all("carrera" in f["descripcion"] for f in cil)
    assert all(set(f["incluye"]) == {"Cilindro · Vástago"} for f in cil)  # viene con la ref
    assert not any("Vástago" in f["descripcion"] for f in filas)
    pies = [f for f in filas if "Pie (MS1)" in f["descripcion"]]
    assert len(pies) == 1 and pies[0]["cantidad"] == 6  # los dos pies de cada uno, una fila
    # ni se fabrica: fuera de la lista de corte (y con ella del despiece y de las láminas)
    despiece = cut_list(d.scene)
    assert not any("Vástago" in r["nombre"] for r in despiece)
    assert any("Pie (MS1)" in r["nombre"] for r in despiece)


def test_costeo_no_cobra_el_vastago():
    from apolo.services.cobros import costeo

    d, cid = _doc()
    filas = costeo(d)["rows"]
    assert sum(f["cantidad"] for f in filas if f["ref"] == "CIL-ISO15552-32") == 1
    assert not any("Vástago" in f["descripcion"] for f in filas)


# ── sujeción, dinámica y render ────────────────────────────────────────────────────────────


def _sobre_base(**p):
    d, cid = _doc(**p)
    base = d.execute("create_box", {"width": 370, "depth": 400, "height": 20,
                                    "position": {"x": -165, "y": 0, "z": -42}})
    d.execute("fasten", {"name": "pies_base", "a": f"{cid}_pie_delantero", "b": f"{base}", "kind": "perno",
                         "size": "M6", "qty": 2})
    d.execute("fasten", {"name": "pies_base2", "a": f"{cid}_pie_trasero", "b": f"{base}", "kind": "perno",
                         "size": "M6", "qty": 2})
    d.execute("ground", {"name": "piso", "feature": base})
    return d, cid, base


def test_sujeto_hasta_el_piso_por_su_montaje():
    from apolo.assembly.connectivity import build_graph, soundness_report

    d, cid, _ = _sobre_base(montaje="pies", carrera=200)
    rep = soundness_report(build_graph(d.scene, d.joints, d.mates, d.fasteners, d.grounds))
    assert rep["floating"] == [] and rep["n_grounded"] == len(d.scene)


def test_la_puerta_de_entrega_lo_da_verde_sujeto_por_sus_pies():
    """Sin choques internos, con sus uniones declaradas y sin lints: un cilindro sujeto por su
    montaje no pone nada amarillo ni rojo en la puerta."""
    from apolo.library.delivery import delivery_report
    from apolo.services.delivery_inputs import delivery_inputs

    d, _, _ = _sobre_base(montaje="pies", carrera=200)
    r = delivery_report(**delivery_inputs(d, expand=lambda ids: ids))
    assert (r["veredicto"], r["bloqueantes"], r["avisos"]) == ("VERDE", [], [])


def test_la_junta_entra_a_la_dinamica_como_slide():
    pytest.importorskip("mujoco")
    from apolo.physics.dinamica import prepare_dynamics

    d, cid, _ = _sobre_base(montaje="pies", carrera=200)
    snap = prepare_dynamics(d.scene, d.joints, d.fasteners, d.grounds, {"duracion_s": 0.1})
    cuerpo = next(c for c in snap.cuerpos if c["junta"] == f"{cid}_vastago")
    assert cuerpo["tipo"] == "prismatica"
    assert set(cuerpo["piezas"]) == {f"{cid}_vastago", f"{cid}_empujador"}
    assert 'type="slide"' in snap.xml or "slide" in snap.xml


def test_render_aislado_y_a_mitad_de_carrera(tmp_path):
    """La foto del cilindro aislado y con la junta a mitad de carrera (D5: `render_view`). Sin
    OpenGL la ruta da 503 claro; con él, dos PNG distintos."""
    from fastapi.testclient import TestClient

    import apolo.api.main as api

    d, cid = _doc(montaje="pies", carrera=200)
    api.DOC = d
    client = TestClient(api.app)
    ids = ",".join(sorted(d.scene))
    fotos = []
    for joints in (None, json.dumps({f"{cid}_vastago": 100})):
        params = {"isolate": ids, "vtk_only": True, "shade": True}
        if joints:
            params["joints"] = joints
        r = client.get("/api/render.png", params=params)
        assert r.status_code in (200, 503), r.text
        if r.status_code == 503:
            pytest.skip("sin OpenGL")
        assert r.content[:4] == b"\x89PNG"
        fotos.append(r.content)
        (tmp_path / f"cilindro_{len(fotos)}.png").write_bytes(r.content)
    assert fotos[0] != fotos[1]
