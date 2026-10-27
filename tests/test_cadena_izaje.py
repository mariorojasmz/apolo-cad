"""Cadena de IZAJE (`create_hoist_chain`, plan `docs/plans/cadena-de-izaje.md`, F1).

Un elevador mínimo: un bastidor fijo con un piñón motriz arriba y uno loco abajo (08B-1 Z15, eje
X), y una plataforma con dos placas de amarre que sube por una junta prismática. La cadena va del
amarre A (sobre la placa superior) al motriz, baja por el ramal de retorno, da la vuelta al loco y
sube al amarre B (bajo la placa inferior). Se prueba en la pose de diseño y subida: sin choques,
largo constante, uniones perno en los amarres y el lazo cerrado de `create_chain` intacto.
"""

from __future__ import annotations

import math

import pytest

from apolo.commands import CommandError
from apolo.doc import Document, DocumentError
from apolo.library.izaje import Pinon, rodillos, sentido_mas_corto
from apolo.library.izaje_geom import datos_de_clave
from apolo.library.transmision import diametro_primitivo
from apolo.robotics.pose import posed_shapes

ERRORES = (DocumentError, CommandError)
R = diametro_primitivo(12.7, 15) / 2.0
Z_SUP, Z_INF = 1500.0, 300.0
Z_A, Z_B = 735.0, 570.0          # pasadores: A sobre la placa superior, B bajo la inferior
SUBIDA = 400.0


def _elevador(doc: Document, **extra) -> dict:
    ids = {}
    ids["bastidor"] = doc.execute("create_box", {"name": "Columna", "width": 40, "depth": 40, "height": 1400,
                                                 "position": {"x": 0, "y": 200, "z": 900}})
    for clave, z in (("motriz", Z_SUP), ("loco", Z_INF)):
        ids[clave] = doc.execute("insert_component", {
            "component": "PINON-08B-1-Z15", "name": f"Piñón {clave}",
            "position": {"x": 0, "y": 0, "z": z}, "rotation": {"y": 90}})
    ids["plataforma"] = doc.execute("create_box", {"name": "Plataforma", "width": 200, "depth": 100,
                                                   "height": 200, "position": {"x": 0, "y": -R - 70, "z": 650}})
    ids["placa_a"] = doc.execute("create_box", {"name": "Placa de amarre superior", "width": 60, "depth": 40,
                                                "height": 10, "position": {"x": 0, "y": -R, "z": 700}})
    ids["placa_b"] = doc.execute("create_box", {"name": "Placa de amarre inferior", "width": 60, "depth": 40,
                                                "height": 10, "position": {"x": 0, "y": -R, "z": 600}})
    for k in ("placa_a", "placa_b"):
        doc.execute("fasten", {"name": f"sol_{k}", "a": ids[k], "b": ids["plataforma"], "kind": "soldadura",
                               "throat_mm": 4, "length_mm": 100})
    doc.execute("add_joint", {"name": "j_plataforma", "type": "prismatica", "parent": ids["bastidor"],
                              "child": ids["plataforma"], "origin": {"x": 0, "y": 0, "z": 0},
                              "axis": {"x": 0, "y": 0, "z": 1}, "lower": -100, "upper": 600, "arrastrar": True})
    ids["cadena"] = doc.execute("create_hoist_chain", {
        "name": "Cadena de izaje", "pinones": [ids["motriz"], ids["loco"]],
        "pieza_a": ids["placa_a"], "pieza_b": ids["placa_b"],
        "extremo_a": {"x": 0, "y": -R, "z": Z_A}, "extremo_b": {"x": 0, "y": -R, "z": Z_B}, **extra})
    return ids


@pytest.fixture(scope="module")
def elevador():
    doc = Document("elevador")
    return doc, _elevador(doc)


def _comun(s1, s2) -> float:
    try:
        r = s1.intersect(s2)
    except Exception:  # noqa: BLE001
        return 0.0
    if r is None:
        return 0.0
    return float(getattr(r, "volume", 0.0) or 0.0)


def _rodillos_posados(doc, fid, valores):
    from apolo.library.catalog import CATALOG
    from apolo.library.izaje_geom import cadena_posada, diseno

    d = datos_de_clave(doc.scene[fid].mesh_key)
    c0 = diseno(d, 12.7)
    if not valores:
        return c0
    dz = valores["j_plataforma"]
    # el marco: x = del motriz al loco (−Z mundo); subir dz es correr los amarres −dz en x
    a = (c0.puntos[0][0] - dz, c0.puntos[0][1])
    b = (c0.puntos[-1][0] - dz, c0.puntos[-1][1])
    return cadena_posada(d, CATALOG[d.cadena].specs, a, b)[1]


# ------------------------------------------------------------------ la matemática
def test_la_cadena_abierta_va_a_paso_exacto_y_asienta_en_los_dos_pinones():
    pins = [Pinon(0, 0, R, 15), Pinon(Z_SUP - Z_INF, 0, R, 15)]
    a, b = (Z_SUP - Z_A, -R), (Z_SUP - Z_B, -R)
    s = sentido_mas_corto(a, pins, b)
    c = rodillos(a, pins, b, s, 12.7)
    assert c.pasos % 2 == 1
    seps = [math.dist(c.puntos[i], c.puntos[i + 1]) for i in range(c.pasos)]
    assert max(abs(x - 12.7) for x in seps) < 1e-6
    for pin, idx in zip(pins, c.asentados):
        assert len(idx) >= 7  # media vuelta de un Z15
        assert all(abs(math.dist(c.puntos[i], (pin.cx, pin.cy)) - R) < 1e-6 for i in idx)
    # ningún rodillo entra al círculo de paso de un piñón
    for pin in pins:
        assert min(math.dist(q, (pin.cx, pin.cy)) for q in c.puntos) > R - 1e-6
    assert 0.0 <= c.falta_mm < 2 * 12.7
    with pytest.raises(ValueError, match="IMPAR"):
        rodillos(a, pins, b, s, 12.7, pasos=c.pasos + 1)
    with pytest.raises(ValueError, match="sobra cadena"):
        rodillos(a, pins, b, s, 12.7, pasos=c.pasos + 4)


# ------------------------------------------------------------------ el comando
def test_arma_cadena_anclas_tuercas_y_declara_las_uniones(elevador):
    doc, ids = elevador
    cid = ids["cadena"]
    f = doc.scene[cid]
    d = datos_de_clave(f.mesh_key)
    assert f.component == "CADENA-08B-1" and d.pasos % 2 == 1
    assert f.cut_length == pytest.approx(d.pasos * 12.7)
    for k in ("ancla_a", "ancla_b", "tuerca_a1", "tuerca_a2", "tuerca_b1", "tuerca_b2"):
        assert f"{cid}_{k}" in doc.scene
    assert doc.scene[f"{cid}_tuerca_a1"].component == "TUERCA-M8"
    fz = doc.fasteners
    assert fz[f"{cid}_pasador_a"]["kind"] == "perno" and fz[f"{cid}_pasador_a"]["b"] == f"{cid}_ancla_a"
    # el amarre es perno/pasador, nunca contacto
    for lado in "ab":
        assert fz[f"{cid}_pasador_{lado}"]["kind"] == fz[f"{cid}_amarre_{lado}"]["kind"] == "perno"
        assert fz[f"{cid}_amarre_{lado}"]["size"] == "M8"
    assert fz[f"{cid}_amarre_b"]["b"] == ids["placa_b"]
    assert {fz[f"{cid}_p1"]["b"], fz[f"{cid}_p2"]["b"]} == {ids["motriz"], ids["loco"]}
    assert fz[f"{cid}_p1"]["kind"] == fz[f"{cid}_p2"]["kind"] == "contacto"
    assert doc.joints[f"{cid}_jf_ancla_a"]["parent"] == ids["placa_a"]
    assert doc.joints[f"{cid}_jf_tuerca_b2"]["parent"] == ids["placa_b"]


def _sin_choques(doc, ids, shapes) -> dict:
    cid = ids["cadena"]
    cadena = shapes[cid]
    otros = [ids["placa_a"], ids["placa_b"], ids["plataforma"], ids["bastidor"], f"{cid}_ancla_a", f"{cid}_ancla_b"]
    vol = {o: _comun(cadena, shapes[o]) for o in otros}
    for lado, placa in (("a", "placa_a"), ("b", "placa_b")):
        vol[f"ancla_{lado}↔placa"] = _comun(shapes[f"{cid}_ancla_{lado}"], shapes[ids[placa]])
    return vol


@pytest.mark.parametrize("valores", [{}, {"j_plataforma": SUBIDA}], ids=["diseño", "subida"])
def test_sin_choques_en_diseno_y_en_pose(elevador, valores):
    doc, ids = elevador
    shapes, avisos = posed_shapes(doc, valores)
    assert not avisos
    vol = _sin_choques(doc, ids, shapes)
    assert all(v < 1e-3 for v in vol.values()), vol
    # los piñones ruedan con la cadena: los rodillos siguen en sus asientos (fase auto en el diseño)
    for k in ("motriz", "loco"):
        assert _comun(shapes[ids["cadena"]], shapes[ids[k]]) < 1.0, k


def test_la_cadena_sigue_a_la_junta_con_el_largo_constante(elevador):
    doc, ids = elevador
    cid = ids["cadena"]
    diseno_bb = doc.scene[cid].shape.bounding_box()
    shapes, _ = posed_shapes(doc, {"j_plataforma": SUBIDA})
    posada = shapes[cid]
    assert posada is not doc.scene[cid].shape
    c0, c1 = _rodillos_posados(doc, cid, {}), _rodillos_posados(doc, cid, {"j_plataforma": SUBIDA})
    assert c1.pasos == c0.pasos
    assert abs(c1.falta_mm) < 0.2  # el efecto poligonal: centésimas, el último tramo lo cierra
    assert c1.puntos[-1] == pytest.approx((c0.puntos[-1][0] - SUBIDA, c0.puntos[-1][1]), abs=1e-3)
    # el amarre A subió SUBIDA y el largo de la cadena es el mismo (N pasos de 12.7)
    assert max(abs(math.dist(c1.puntos[i], c1.puntos[i + 1]) - 12.7) for i in range(c1.pasos)) < 0.01
    ancla_a = shapes[f"{cid}_ancla_a"].bounding_box()
    assert ancla_a.min.Z == pytest.approx(doc.scene[f"{cid}_ancla_a"].shape.bounding_box().min.Z + SUBIDA)
    # la cadena posada no es la del diseño corrida: sigue envolviendo los dos piñones (el bbox en Z,
    # del motriz al loco, cambia sólo por la fase de los rodillos sobre el diente: R·(1 − cos 12°))
    bb = posada.bounding_box()
    assert bb.max.Z == pytest.approx(diseno_bb.max.Z, abs=1.0)
    assert bb.min.Z == pytest.approx(diseno_bb.min.Z, abs=1.0)


def test_en_pose_un_lazo_cerrado_no_se_toca():
    doc = Document("lazo")
    a = doc.execute("insert_component", {"component": "PINON-ASA40-1-Z15"})
    b = doc.execute("insert_component", {"component": "PINON-ASA40-1-Z15", "position": {"x": 95.25}})
    base = doc.execute("create_box", {"name": "Base", "width": 10, "depth": 10, "height": 10,
                                      "position": {"x": 0, "y": 200, "z": 0}})
    doc.execute("add_joint", {"name": "j", "type": "continua", "parent": base, "child": a,
                              "origin": {"x": 0, "y": 0, "z": 0}, "axis": {"x": 0, "y": 0, "z": 1}})
    cid = doc.execute("create_chain", {"pinon_a": a, "pinon_b": b})
    assert doc.scene[cid].mesh_key.startswith("cadena|")
    shapes, _ = posed_shapes(doc, {"j": 30.0})
    assert shapes[cid] is doc.scene[cid].shape


# ------------------------------------------------------------------ errores accionables
def test_errores_dicen_que_corregir():
    doc = Document("errores")
    with pytest.raises(ERRORES, match="IMPAR"):
        _elevador(doc, eslabones=200)
    doc = Document("errores2")
    with pytest.raises(ERRORES, match="plano de la hilera"):
        _elevador(doc, extremo_a={"x": 5, "y": -R, "z": Z_A})
    doc = Document("errores3")
    with pytest.raises(ERRORES, match="aléjalo"):
        _elevador(doc, extremo_a={"x": 0, "y": -R, "z": 712})


def test_fase_auto_asienta_los_dientes(elevador):
    """Con fase auto, el ancla `fase` de cada piñón cae (módulo un diente) en un rodillo."""
    doc, ids = elevador
    from apolo.library.izaje_geom import diseno

    f = doc.scene[ids["cadena"]]
    d = datos_de_clave(f.mesh_key)
    c = diseno(d, 12.7)
    m = f.matrix
    for k, pid in enumerate((ids["motriz"], ids["loco"])):
        fase = doc.scene[pid].anchors["fase"]["origin"]
        q = c.puntos[c.asentados[k][0]]
        mundo_q = [m[i][0] * q[0] + m[i][1] * q[1] + m[i][3] for i in range(3)]
        centro = doc.scene[pid].anchors["eje"]["origin"]
        v1 = [fase[i] - centro[i] for i in range(3)]
        v2 = [mundo_q[i] - centro[i] for i in range(3)]
        cosang = sum(v1[i] * v2[i] for i in range(3)) / (math.hypot(*v1) * math.hypot(*v2))
        ang = math.degrees(math.acos(max(-1.0, min(1.0, cosang))))
        paso_ang = 360.0 / 15
        assert min(ang % paso_ang, paso_ang - ang % paso_ang) < 1e-3
