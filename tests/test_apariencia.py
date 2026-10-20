"""Tabla de acabados D5 (docs/plans/visor-realista.md, F1): `library/apariencia.py`.

Una sola tabla para los dos renderizadores: el visor three.js la lee de
`ui/src/viewport/acabados.json` (copia generada, vigilada aquí) y el render VTK del kernel la
recibe por pieza (`services/apariencia.apariencias_documento`). Se prueba la tabla (rango,
cobertura del catálogo y del registro de materiales), las reglas de color y que los dos lados
usen los MISMOS valores, con una captura VTK comparada.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import apolo.api.main as api
from apolo.doc import Document
from apolo.kernel.render import PALETTE
from apolo.library.apariencia import (
    ACABADOS,
    POR_DEFECTO,
    TIPOS_RELIEVE,
    acabado_de,
    apariencia,
    apariencias_escena,
    json_ui,
)
from apolo.library.catalog import CATALOG
from apolo.library.materials import DENSITY_KG_MM3
from apolo.services.apariencia import apariencias_documento

RAIZ = Path(__file__).resolve().parents[1]
JSON_UI = RAIZ / "ui" / "src" / "viewport" / "acabados.json"
HEX = re.compile(r"^#[0-9a-f]{6}$")

#: Materiales de catálogo que SON acero estructural/pintado: caen al acabado por defecto a
#: propósito. Cualquier otro material que caiga ahí es un hueco de la tabla.
ACERO_PINTADO_A_PROPOSITO = {"acero", "acero pintado", "acero s275jr", "acero astm a500",
                             "acero astm a500 gr.b"}


# ── la tabla ──────────────────────────────────────────────────────────────────────────────


def test_json_del_visor_es_copia_exacta_de_la_tabla():
    actual = JSON_UI.read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert actual == json_ui(), (
        "ui/src/viewport/acabados.json desfasado: python -B scripts/acabados_ui.py --escribir")


@pytest.mark.parametrize("clave", sorted(ACABADOS))
def test_valores_en_rango(clave):
    ac = ACABADOS[clave]
    assert ac.nombre and not ac.nombre.islower()          # rótulo para la persona
    assert 0.0 <= ac.metalness <= 1.0
    assert 0.0 <= ac.roughness <= 1.0
    assert 0.0 < ac.opacidad <= 1.0
    assert ac.color is None or HEX.match(ac.color)
    if ac.relieve is not None:
        assert ac.relieve.tipo in TIPOS_RELIEVE
        assert ac.relieve.escala_mm > 0 and 0.0 < ac.relieve.intensidad <= 1.0


def test_plausibilidad_fisica():
    """Los metales brillan como metal y los dieléctricos no; sólo el vidrio es translúcido."""
    for clave in ("inox_cepillado", "aluminio", "galvanizado", "cromado", "laton", "bronce"):
        assert ACABADOS[clave].metalness >= 0.85, clave
    for clave in ("caucho", "pvc_banda", "madera", "carton", "vidrio"):
        assert ACABADOS[clave].metalness == 0.0, clave
    assert ACABADOS["cromado"].roughness < ACABADOS["inox_cepillado"].roughness
    assert ACABADOS["caucho"].roughness > 0.8
    assert [k for k, a in ACABADOS.items() if a.opacidad < 1.0] == ["vidrio"]
    assert ACABADOS[POR_DEFECTO].color is None   # lo pintado toma el color de la pieza


def test_d5_cubre_los_acabados_del_plan():
    for clave in ("acero_pintado", "galvanizado", "inox_cepillado", "aluminio", "caucho",
                  "pvc_banda", "pavonado", "bronce"):
        assert clave in ACABADOS


def test_cada_material_del_catalogo_tiene_acabado():
    huecos = []
    for ref, comp in CATALOG.items():
        mat = (comp.specs or {}).get("material")
        if not mat:
            continue
        clave = acabado_de(mat, comp.name, componente=ref, categoria=comp.category)
        assert clave in ACABADOS, (ref, mat)
        if clave == POR_DEFECTO and mat.lower() not in ACERO_PINTADO_A_PROPOSITO:
            huecos.append((ref, mat))
    assert not huecos, f"materiales de catálogo que caen al acabado por defecto: {huecos}"


@pytest.mark.parametrize("material", sorted(DENSITY_KG_MM3))
def test_cada_material_del_registro_tiene_acabado(material):
    clave = acabado_de(material)
    assert clave in ACABADOS
    if material != "acero":
        assert clave != POR_DEFECTO, material


@pytest.mark.parametrize("material, nombre, ref, categoria, esperado", [
    ("acero", "Eje motriz Ø35 h7", None, None, "acero_mecanizado"),
    ("acero", "Tensor de cola · Eje fijo (roscado p/ perno)", None, None, "acero_mecanizado"),
    ("acero", "Faja de banda · Larguero (1)", None, None, "acero_pintado"),
    ("acero", "Ejecutivo", None, None, "acero_pintado"),          # «eje» anclado: no por prefijo
    ("acero", "Cadena ASA 40-1", "CADENA-ASA40-1", "transmision", "pavonado"),
    ("acero", "Piñón ASA 40-1 Z15 (tipo B)", "PINON-ASA40-1-Z15", "transmision",
     "acero_mecanizado"),
    ("acero templado", "Riel de guía", "X", "guias_lineales", "acero_mecanizado"),  # no vidrio
    ("acero 12.9", "Tornillo allen", None, "tornilleria", "pavonado"),
    ("acero grado 8.8", "Perno M12", None, "pernos", "zincado"),
    ("hierro fundido", "Chumacera UCP207", None, "chumaceras", "hierro_fundido"),
    ("níquel satinado", "Bisagra", None, None, "niquelado"),
    ("latón", "Tirador", None, None, "laton"),
    ("aluminio/acero", "Polea", None, "transmision", "aluminio"),
    ("madera copaiba", "Listón del asiento", None, None, "madera"),
    ("pvc", "Faja de banda · Banda", None, None, "pvc_banda"),
])
def test_acabado_por_material_rol_y_catalogo(material, nombre, ref, categoria, esperado):
    assert acabado_de(material, nombre, componente=ref, categoria=categoria) == esperado


# ── color (albedo) ────────────────────────────────────────────────────────────────────────


def test_color_asignado_gana_luego_el_propio_y_al_final_la_paleta():
    assert apariencia("caucho", "#ff0000", asignado=True)["color"] == "#ff0000"
    assert apariencia("caucho", PALETTE[0])["color"] == ACABADOS["caucho"].color
    assert apariencia("acero_pintado", PALETTE[3])["color"] == PALETTE[3]
    desconocido = apariencia("kriptonita", PALETTE[1])
    assert desconocido["acabado"] == POR_DEFECTO and desconocido["color"] == PALETTE[1]


def _doc():
    doc = Document("apariencia")
    doc.execute_many([
        {"type": "create_box", "params": {"name": "Larguero (+Y)", "width": 400, "depth": 40,
                                          "height": 40}},
        {"type": "create_box", "params": {"name": "Faja · Banda", "width": 400, "depth": 300,
                                          "height": 3, "position": {"z": 60}}},
        {"type": "create_cylinder", "params": {"name": "Eje motriz Ø35 h7", "radius": 17.5,
                                               "height": 400, "position": {"z": 150}}},
        {"type": "create_box", "params": {"name": "Vidrio de la guarda", "width": 200,
                                          "depth": 4, "height": 120, "position": {"z": 260}}},
    ])
    return doc


def test_apariencias_de_un_documento():
    doc = _doc()
    fids = list(doc.scene)
    doc.set_material(fids[0], "acero inoxidable")
    doc.set_color(fids[2], "#123456")
    aps = apariencias_documento(doc)
    assert [aps[f]["acabado"] for f in fids] == ["inox_cepillado", "pvc_banda",
                                                 "acero_mecanizado", "vidrio"]
    assert aps[fids[0]]["color"] == ACABADOS["inox_cepillado"].color
    assert aps[fids[2]]["color"] == "#123456"                  # asignado por el usuario
    assert aps[fids[3]]["opacidad"] < 1.0
    sin_nombre = SimpleNamespace(id="x", name="Pieza", component=None, material=None)
    assert apariencias_escena({"x": sin_nombre}, default_material="madera")["x"]["acabado"] \
        == "madera"


def test_palabra_de_carpinteria_solo_pinta_madera_en_el_vertical_madera():
    larguero = SimpleNamespace(id="l", name="Faja de banda · Larguero (1)", component=None,
                               material=None)
    escena = {"l": larguero}
    assert apariencias_escena(escena)["l"]["acabado"] == "acero_pintado"
    assert apariencias_escena(escena, default_material="madera")["l"]["acabado"] == "madera"
    larguero.material = "copaiba"                               # el override manda
    assert apariencias_escena(escena)["l"]["acabado"] == "madera"


# ── los dos renderizadores leen la MISMA tabla ────────────────────────────────────────────


@pytest.fixture()
def doc_api():
    old = api.DOC
    api._GEOM_REVS.clear()
    doc = _doc()
    api.DOC = doc
    yield doc
    api.DOC = old
    api._GEOM_REVS.clear()


def _known(payload):
    return {"revs": {f["id"]: f["rev"] for f in payload["features"]},
            "defs": list(payload["definitions"])}


def test_el_payload_del_visor_lleva_acabado_y_albedo_tambien_en_el_delta(doc_api):
    full = api.scene_payload()
    aps = apariencias_documento(doc_api)
    for f in full["features"]:
        assert f["acabado"] == aps[f["id"]]["acabado"]
        assert f["albedo"] == aps[f["id"]]["color"]
    fid = full["features"][0]["id"]
    doc_api.set_material(fid, "caucho")      # metadato: no cambia la geometría
    delta = api.scene_payload(known=_known(full))
    f = next(x for x in delta["features"] if x["id"] == fid)
    assert f.get("same") is True
    assert f["acabado"] == "caucho" and f["albedo"] == ACABADOS["caucho"].color


def test_el_render_vtk_usa_los_valores_de_la_tabla(doc_api):
    from apolo.kernel.render_comun import hex_a_rgb
    from apolo.kernel.render_vtk import extract_render_scene

    aps = apariencias_documento(doc_api)
    snap = extract_render_scene(doc_api.scene, apariencias=aps)
    for item in snap.items:
        ap = aps[item.label_text]
        ac = ACABADOS[ap["acabado"]]
        assert item.color == pytest.approx(hex_a_rgb(ap["color"]))
        assert item.pbr == (ac.metalness, ac.roughness)
        assert item.opacity == ac.opacidad


def test_phong_de_pbr_conserva_el_acero_pintado_de_siempre():
    from apolo.kernel import render_comun as rc

    ac = ACABADOS["acero_pintado"]
    ph = rc.phong_de_pbr(ac.metalness, ac.roughness, (0.5, 0.5, 0.5))
    assert ph["especular"] == pytest.approx(rc.ESPECULAR, abs=0.02)
    assert ph["potencia"] == pytest.approx(rc.POTENCIA_ESPECULAR, abs=3)
    cromo = rc.phong_de_pbr(1.0, ACABADOS["cromado"].roughness, (0.8, 0.8, 0.8))
    caucho = rc.phong_de_pbr(0.0, ACABADOS["caucho"].roughness, (0.1, 0.1, 0.1))
    assert cromo["especular"] > ph["especular"] > caucho["especular"]
    assert caucho["color_especular"] == (1.0, 1.0, 1.0)       # dieléctrico: brillo blanco


def test_captura_vtk_comparada_con_la_tabla():
    """Captura VTK: cada pieza sale con el tono de su acabado (el caucho oscuro, el
    galvanizado claro y gris, el pintado con el color de su paleta), como en el visor."""
    pytest.importorskip("vtk")
    import numpy as np
    from build123d import Box, Pos

    from apolo.kernel.render_vivo import EscenaViva

    def caja(fid, nombre, x, material=None):
        return SimpleNamespace(id=fid, name=nombre, material=material, component=None,
                               visible=True, shape=Pos(x, 0, 0) * Box(100, 100, 100))

    escena = {p.id: p for p in (caja("a", "Rodillo · Engomado", 0),
                                caja("b", "Placa de la garrucha", 150, "acero galvanizado"),
                                caja("c", "Larguero (+Y)", 300))}
    aps = apariencias_escena(escena, {})
    assert [aps[k]["acabado"] for k in "abc"] == ["caucho", "galvanizado", "acero_pintado"]
    try:
        viva = EscenaViva.para(escena, {}, ancho=320, alto=240, aristas=False,
                               apariencias=aps)
    except Exception as exc:  # noqa: BLE001 — sin contexto OpenGL en este entorno
        pytest.skip(f"VTK off-screen no disponible: {exc}")
    with viva:
        viva.actualizar(escena)
        viva.orbitar(-90, 0)          # de frente: las tres caras frontales a la vista
        frame = viva.fotograma()
        tonos = {}
        for k, x in zip("abc", (0, 150, 300)):
            col, fila = viva.proyectar((x, -50, 0))
            tonos[k] = frame[int(fila), int(col)].astype(int)
    luz = {k: int(v.mean()) for k, v in tonos.items()}
    assert luz["a"] < 70 < luz["b"]                         # caucho negro, galvanizado claro
    gris = tonos["b"]
    assert int(gris.max()) - int(gris.min()) < 30           # galvanizado: gris, sin matiz
    pintada = tonos["c"]                                      # PALETTE[2] = cobrizo #c77d4f
    paleta = [int(PALETTE[2][i:i + 2], 16) for i in (1, 3, 5)]
    assert int(np.argmax(pintada)) == int(np.argmax(paleta))  # conserva el matiz de su paleta
