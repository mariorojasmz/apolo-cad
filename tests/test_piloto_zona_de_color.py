"""El piloto encendido brilla sólo en su lente (pendientes de la D-a de
docs/plans/pedidos-de-extensiones-ii.md).

- Cada zona del payload de escena dice su NOMBRE (`zona`) y la que lleva el color de la ficha
  (`builders_mandos.ZONA_DE_COLOR`: el `frente` del Ø22) suma `de_color: true`; la sesión viva
  enciende sólo ésa. Campos nuevos: las claves de antes siguen iguales.
- Una sola tabla de tonos: el visor lee el color físico de un mando del acabado de su color
  (`acabado_de_color` en `acabados.json`, copia de `apariencia.ACABADO_DE_COLOR`).
"""

from __future__ import annotations

import pytest

import apolo.api.main as api
import apolo.api.scene as sc
from apolo.doc import Document
from apolo.library.apariencia import ACABADO_DE_COLOR, ACABADOS, _sin_tildes, tabla_ui
from apolo.library.catalog import CATALOG
from apolo.library.zonas import zona_de_color

REFS = ("PILOTO-24V-AMBAR", "PILOTO-24V-VERDE", "PULS-22-ROJO-NC", "SEL-22-2POS-1NA")


@pytest.fixture()
def doc():
    old = api.DOC
    api._GEOM_REVS.clear()
    sc._DEF_MESH_CACHE.clear()
    d = Document("piloto-zona-de-color")
    d.execute_many([{"type": "insert_component",
                     "params": {"component": ref, "position": {"x": 100 * i}}}
                    for i, ref in enumerate(REFS)]
                   + [{"type": "insert_component",
                       "params": {"component": "ESTOP-40", "position": {"y": 300}}}])
    api.DOC = d
    yield d
    api.DOC = old
    api._GEOM_REVS.clear()
    sc._DEF_MESH_CACHE.clear()


def _por_ref(payload: dict) -> dict[str, dict]:
    return {f["component"]: f for f in payload["features"] if f.get("component")}


def _nombres_de_la_malla(f: dict) -> list[str]:
    malla = sc._DEF_MESH_CACHE[f["mesh_key"]] if f["mesh_key"] else None
    if malla is None:  # pieza única: los rangos con nombre quedan en la caché por shape
        feat = api.DOC.scene[f["id"]]
        malla = sc._cached_render(feat.shape, want_mesh=True, componente=feat.component)["mesh"]
    return [r["zona"] for r in malla["zonas"]]


def test_la_zona_de_color_es_la_del_builder():
    for ref in REFS:
        assert zona_de_color(ref) == "frente", ref
    assert zona_de_color("ESTOP-40") is None  # la seta: dos colores de norma, ninguno de ficha
    assert zona_de_color("PERFIL-4040") is None  # sin zonas
    assert zona_de_color(None) is None and zona_de_color("NO-EXISTE") is None


def test_cada_zona_dice_su_nombre_y_solo_la_lente_es_de_color(doc):
    piezas = _por_ref(api.scene_payload())
    for ref in REFS:
        zonas = piezas[ref]["zonas"]
        assert [z["zona"] for z in zonas] == _nombres_de_la_malla(piezas[ref]), ref
        assert {z["zona"] for z in zonas} == {"frente", "bisel", "cuerpo"}, ref
        de_color = [z for z in zonas if z.get("de_color")]
        assert [z["zona"] for z in de_color] == ["frente"], ref
        assert de_color[0]["de_color"] is True
        # las demás no llevan la clave: el payload de antes más `zona`
        assert all(set(z) == {"acabado", "albedo", "desde", "hasta", "zona"}
                   for z in zonas if z is not de_color[0]), ref
        color = CATALOG[ref].specs.get("color")
        if color is not None:  # la lente es del acabado de su color de ficha
            acabado = ACABADO_DE_COLOR[_sin_tildes(color).strip()]
            assert de_color[0]["acabado"] == acabado, ref
            assert de_color[0]["albedo"] == ACABADOS[acabado].color, ref
    seta = piezas["ESTOP-40"]["zonas"]
    assert all("de_color" not in z for z in seta) and all("zona" in z for z in seta)


def test_la_entrada_same_del_delta_conserva_nombre_y_zona_de_color(doc):
    p0 = api.scene_payload()
    known = {"revs": {f["id"]: f["rev"] for f in p0["features"]},
             "defs": list(p0["definitions"])}
    antes = _por_ref(p0)["PILOTO-24V-AMBAR"]
    doc.colors[antes["id"]] = "#123456"  # la lente es `fijo`: no se repinta
    f = next(x for x in api.scene_payload(known=known)["features"] if x["id"] == antes["id"])
    assert f["same"] is True
    assert f["zonas"] == antes["zonas"]


def test_el_visor_recibe_el_acabado_de_cada_color():
    tabla = tabla_ui()
    assert tabla["acabado_de_color"] == ACABADO_DE_COLOR
    assert set(tabla["acabado_de_color"].values()) <= set(tabla["acabados"])
    # todo color de ficha de un mando o piloto Ø22 tiene su acabado (el loader ya lo exige)
    for ref, comp in CATALOG.items():
        if comp.familia == "mando_22" and comp.specs.get("color") is not None:
            assert _sin_tildes(comp.specs["color"]).strip() in tabla["acabado_de_color"], ref
