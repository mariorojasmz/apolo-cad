"""Las zonas de acabado en el payload de escena (plan seta-de-emergencia, F2: D2 y D3).

- Una pieza de un componente con zonas lleva `zonas: [{acabado, albedo, desde, hasta, zona}]` en
  índices de triángulo de la malla que recibe el visor (la propia o la de su definición):
  rangos contiguos que cubren todos los triángulos.
- Una pieza sin zonas va byte a byte como antes (sin `zonas` ni reordenar su malla).
- Las instancias comparten la malla de la definición y sus rangos.
- D3: el color asignado pinta sólo las zonas pintables; una `fijo` conserva su color de norma.
- La entrada `same` del delta lleva las zonas (el color cambia sin subir el rev).
- Una pieza taladrada pierde sus zonas: se ve de un solo acabado, como hoy.
"""

from __future__ import annotations

import json

import pytest

import apolo.api.main as api
import apolo.api.scene as sc
from apolo.doc import Document
from apolo.kernel.mesh import mesh_payload
from apolo.library.apariencia import ACABADOS, apariencias_de_zonas
from apolo.library.catalog import CATALOG
from apolo.library.zonas import Zona

CLAVES_DE_SIEMPRE = {"id", "name", "visible", "color", "volume_mm3", "bbox", "mesh", "mesh_key",
                     "matrix", "command_id", "command_type", "component", "cut_length", "group",
                     "is_guide", "acabado", "albedo", "rev"}


@pytest.fixture()
def doc():
    old = api.DOC
    api._GEOM_REVS.clear()
    sc._DEF_MESH_CACHE.clear()
    d = Document("seta-payload")
    d.execute_many([
        {"type": "create_box", "params": {"name": "Placa", "width": 200, "depth": 100,
                                          "height": 5}},
        {"type": "insert_component", "params": {"component": "ESTOP-40",
                                                "position": {"x": 300}}},
        {"type": "insert_component", "params": {"component": "ESTOP-40",
                                                "position": {"x": 500}}},
        {"type": "insert_component", "params": {"component": "ESTOP-40-CAJA",
                                                "position": {"x": 700}}},
        {"type": "insert_component", "params": {"component": "PERFIL-4040",
                                                "position": {"y": 300}}},
    ])
    api.DOC = d
    yield d
    api.DOC = old
    api._GEOM_REVS.clear()
    sc._DEF_MESH_CACHE.clear()


def _por_ref(payload: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for f in payload["features"]:
        out.setdefault(f.get("component") or f["name"], []).append(f)
    return out


def _malla(payload: dict, f: dict) -> dict:
    return f["mesh"] if f["mesh"] is not None else payload["definitions"][f["mesh_key"]]


def _cubre(zonas: list[dict], n_tri: int) -> bool:
    return (zonas[0]["desde"] == 0 and zonas[-1]["hasta"] == n_tri
            and all(a["hasta"] == b["desde"] for a, b in zip(zonas, zonas[1:]))
            and all(z["hasta"] > z["desde"] for z in zonas))


def test_la_seta_lleva_sus_zonas_y_cubren_la_malla(doc):
    p = api.scene_payload()
    piezas = _por_ref(p)
    for ref in ("ESTOP-40", "ESTOP-40-CAJA"):
        for f in piezas[ref]:
            assert set(f) == CLAVES_DE_SIEMPRE | {"zonas"}
            malla = _malla(p, f)
            assert "zonas" not in malla  # los rangos con nombre no viajan en la malla
            assert _cubre(f["zonas"], len(malla["indices"]) // 3)
            # `zona` = su nombre; la seta no tiene zona de color (`de_color`, la del Ø22)
            assert all(set(z) == {"acabado", "albedo", "desde", "hasta", "zona"} for z in f["zonas"])
            assert {z["acabado"] for z in f["zonas"]} <= set(ACABADOS)
    # la seta de puerta: rojo y amarillo de norma, cada uno con su albedo de la tabla
    rojo = ACABADOS["plastico_rojo_seguridad"].color
    amarillo = ACABADOS["plastico_amarillo_seguridad"].color
    albedos = {z["acabado"]: z["albedo"] for z in piezas["ESTOP-40"][0]["zonas"]}
    assert albedos["plastico_rojo_seguridad"] == rojo
    assert albedos["plastico_amarillo_seguridad"] == amarillo


def test_las_instancias_comparten_la_definicion_y_sus_rangos(doc):
    p = api.scene_payload()
    a, b = _por_ref(p)["ESTOP-40"]
    assert a["mesh"] is None and a["mesh_key"] == b["mesh_key"] in p["definitions"]
    assert a["zonas"] == b["zonas"]
    # la malla de la definición está agrupada por zona: los mismos triángulos, reordenados
    from apolo.commands.registry import DEFINITIONS

    plano = mesh_payload(DEFINITIONS[a["mesh_key"]])
    d = p["definitions"][a["mesh_key"]]
    assert d["positions"] == plano["positions"] and len(d["indices"]) == len(plano["indices"])


def test_una_pieza_sin_zonas_va_byte_a_byte_como_antes(doc, monkeypatch):
    p = api.scene_payload()
    sin = [f for f in p["features"] if f["component"] not in ("ESTOP-40", "ESTOP-40-CAJA")]
    assert len(sin) == 2
    for f in sin:
        assert set(f) == CLAVES_DE_SIEMPRE
        feat = doc.scene[f["id"]]
        malla = _malla(p, f)
        from apolo.commands.registry import DEFINITIONS

        shape = DEFINITIONS[f["mesh_key"]] if f["mesh_key"] else feat.shape
        assert malla == mesh_payload(shape)  # sin reordenar
    # con la maquinaria de zonas apagada, el payload de esas piezas es el MISMO texto
    api._GEOM_REVS.clear()
    sc._DEF_MESH_CACHE.clear()
    sc._SHAPE_CACHE.clear()
    monkeypatch.setattr(sc, "_zona_por_cara", lambda componente, shape: None)
    import apolo.services.apariencia as sa

    monkeypatch.setattr(sa, "zonas_documento", lambda d: {})
    q = api.scene_payload()
    viejo = {f["id"]: f for f in q["features"]}
    for f in sin:
        assert json.dumps(f) == json.dumps(viejo[f["id"]])
    clave = next(f["mesh_key"] for f in sin if f["mesh_key"])
    assert json.dumps(p["definitions"][clave]) == json.dumps(q["definitions"][clave])
    sc._SHAPE_CACHE.clear()


def test_el_color_asignado_no_pinta_lo_fijo(doc):
    p0 = api.scene_payload()
    known = {"revs": {f["id"]: f["rev"] for f in p0["features"]},
             "defs": list(p0["definitions"])}
    caja = _por_ref(p0)["ESTOP-40-CAJA"][0]
    zonas = {z.nombre: z for z in CATALOG["ESTOP-40-CAJA"].zonas}
    # el nombre de la zona de cada rango, en el orden del payload (la malla en caché lo guarda)
    nombres = [r["zona"] for r in sc._DEF_MESH_CACHE[caja["mesh_key"]]["zonas"]]
    assert len(nombres) == len(caja["zonas"])
    assert any(zonas[n].fijo for n in nombres)
    assert any(not zonas[n].fijo and ACABADOS[zonas[n].acabado].pintable for n in nombres)

    doc.colors[caja["id"]] = "#123456"
    d = api.scene_payload(known=known)
    f = next(x for x in d["features"] if x["id"] == caja["id"])
    assert f["same"] is True and f["rev"] == caja["rev"]
    # la entrada `same` lleva las zonas: mismos rangos, apariencia nueva
    assert [(z["desde"], z["hasta"]) for z in f["zonas"]] == [
        (z["desde"], z["hasta"]) for z in caja["zonas"]]
    for nombre, z in zip(nombres, f["zonas"]):
        zona = zonas[nombre]
        assert z["acabado"] == zona.acabado
        if not zona.fijo and ACABADOS[zona.acabado].pintable:
            assert z["albedo"] == "#123456", nombre  # la caja de superficie se repinta
        else:
            assert z["albedo"] == ACABADOS[zona.acabado].color, nombre  # norma o moldeado
    # la pieza sin zonas sigue sin `zonas` en su entrada `same`
    placa = next(x for x in d["features"] if x["name"] == "Placa")
    assert placa["same"] is True and "zonas" not in placa


def test_apariencias_de_zonas_es_pura():
    zonas = (Zona("seta", "plastico_rojo_seguridad", True),
             Zona("caja", "plastico_amarillo_seguridad", False),
             Zona("collar", "plastico_negro", False))
    sin_color = apariencias_de_zonas(zonas, None, "#5b8def")
    assert {k: v["color"] for k, v in sin_color.items()} == {
        "seta": ACABADOS["plastico_rojo_seguridad"].color,
        "caja": ACABADOS["plastico_amarillo_seguridad"].color,
        "collar": ACABADOS["plastico_negro"].color}
    pintada = apariencias_de_zonas(zonas, "#00ff00", "#5b8def")
    assert pintada["caja"]["color"] == "#00ff00"
    assert pintada["seta"]["color"] == sin_color["seta"]["color"]
    assert pintada["collar"]["color"] == sin_color["collar"]["color"]  # no pintable


def test_una_seta_taladrada_se_ve_de_un_solo_acabado(doc):
    fid = next(fid for fid, f in doc.scene.items() if f.component == "ESTOP-40-CAJA")
    doc.execute("drill_hole", {"feature": fid, "diameter": 6, "depth": 10,
                               "position": {"x": 720, "y": 0, "z": 0}, "axis": "z"})
    p = api.scene_payload()
    f = next(x for x in p["features"] if x["id"] == fid)
    assert "zonas" not in f and f["mesh"] is not None and "zonas" not in f["mesh"]
    assert set(f) == CLAVES_DE_SIEMPRE
