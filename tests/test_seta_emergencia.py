"""La seta de emergencia por zonas (plan seta-de-emergencia, F1: D1, D4, D5, D6).

- La pieza es UNA: un sólido, una línea de BOM y la masa de su ficha, aunque se vea en zonas.
- Las zonas cubren TODAS las caras y todos los triángulos del teselado, en rangos contiguos; una
  pieza sin zonas tesela exactamente como antes.
- La zona sobrevive a la colocación y a la caché de geometría (va por índice de cara) y se
  descarta si la forma ya no es la del builder.
- Las anclas `montaje`, `agujero` y `fijacion_*` caen donde está la geometría.
- ESTOP-40-CAJA lleva la ficha de ESTOP-40: el ERC la trata igual.
- Un proyecto con ESTOP-40 abre con la seta nueva aunque la caché guarde la caja vieja (epoch).
"""

from __future__ import annotations

import pickle
from collections import Counter

import pytest
from build123d import Box, Vector
from tablero_electrico import arranque_directo, no_ok

from apolo.brep_io import serialize_robust
from apolo.doc.document import Document
from apolo.doc.geomcache import GEOM_CACHE_EPOCH, pack, unpack
from apolo.kernel.mesh import agrupar_por_zona, mesh_payload, teselar_caras
from apolo.kernel.render_comun import teselar, teselar_zonas
from apolo.kernel.zonas import fusionar_zonas
from apolo.library.apariencia import ACABADOS
from apolo.library.bom import bom_from_scene
from apolo.library.builders_mandos import ZONAS_SETA, seta_emergencia
from apolo.library.catalog import CATALOG, build_component
from apolo.library.electrico.erc import erc, resumen
from apolo.library.engineering.mass import scene_mass_properties
from apolo.library.loader import load_catalog
from apolo.library.zonas import zona_por_cara

SETAS = {"ESTOP-40": "puerta", "ESTOP-40-CAJA": "caja"}


def _doc(*refs: str, **pose) -> Document:
    d = Document("seta")
    for k, ref in enumerate(refs):
        d.execute("insert_component", {"component": ref, "position": pose.get("position", {"x": 200 * k}),
                                       "rotation": pose.get("rotation", {})})
    return d


# ── una pieza, aunque se vea en zonas ────────────────────────────────────────────────────


@pytest.mark.parametrize("ref", SETAS)
def test_la_seta_es_un_solido_con_sus_zonas(ref):
    shape, cut = build_component(ref)
    assert cut is None and len(shape.solids()) == 1 and shape.volume > 0
    comp = CATALOG[ref]
    zonas = [z.nombre for z in comp.zonas]
    assert tuple(zonas) == ZONAS_SETA[SETAS[ref]]
    por_cara = zona_por_cara(ref, shape)
    assert len(por_cara) == len(shape.faces())
    assert set(por_cara) == set(zonas)  # cada zona del YAML tiene al menos una cara
    fijas = {z.nombre for z in comp.zonas if z.fijo}
    assert fijas == {"seta", "leyenda"}  # los colores de la norma (D3)
    assert all(z.acabado in ACABADOS for z in comp.zonas)
    assert {z.acabado for z in comp.zonas if z.nombre == "seta"} == {"plastico_rojo_seguridad"}


def test_una_linea_de_bom_y_la_masa_de_la_ficha():
    d = _doc("ESTOP-40", "ESTOP-40", "ESTOP-40-CAJA")
    assert len(d.scene) == 3 and all(len(f.shape.solids()) == 1 for f in d.scene.values())
    filas = {r["ref"]: r for r in bom_from_scene(d.scene)}
    assert set(filas) == set(SETAS)
    assert filas["ESTOP-40"]["cantidad"] == 2 and filas["ESTOP-40-CAJA"]["cantidad"] == 1
    ids = [fid for fid, f in d.scene.items() if f.component == "ESTOP-40"]
    masa = scene_mass_properties(d.scene, ids=ids[:1])["total"]["masa_kg"]
    assert masa == pytest.approx(CATALOG["ESTOP-40"].weight)


# ── las zonas cubren el teselado ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("ref", SETAS)
def test_las_zonas_cubren_todos_los_triangulos(ref):
    shape, _ = build_component(ref)
    por_cara = zona_por_cara(ref, shape)
    base = mesh_payload(shape)
    con = mesh_payload(shape, zona_por_cara=por_cara)
    n = len(con["indices"]) // 3
    assert n == len(base["indices"]) // 3 and con["positions"] == base["positions"]
    rangos = con["zonas"]
    assert rangos[0]["desde"] == 0 and rangos[-1]["hasta"] == n
    assert all(a["hasta"] == b["desde"] for a, b in zip(rangos, rangos[1:]))  # contiguos
    assert {r["zona"] for r in rangos} == set(por_cara) and len(rangos) == len(set(por_cara))
    # los mismos triángulos, sólo reordenados
    tri = lambda idx: Counter(tuple(idx[i:i + 3]) for i in range(0, len(idx), 3))  # noqa: E731
    assert tri(con["indices"]) == tri(base["indices"])
    # a resolución de render, por la misma caché que `teselar`
    v, t, rr = teselar_zonas(shape, por_cara)
    assert rr[-1]["hasta"] == len(t) == len(teselar(shape)[1]) and len(v) == len(teselar(shape)[0])


def test_cada_triangulo_de_la_seta_cae_en_la_seta():
    """El rango de la zona `seta` son los triángulos del frente rojo (z > collar)."""
    shape, _ = build_component("ESTOP-40")
    v, t, rangos = teselar_zonas(shape, zona_por_cara("ESTOP-40", shape))
    seta = next(r for r in rangos if r["zona"] == "seta")
    # la malla de render es numpy (teselado-rapido D2): v[i] = (x, y, z)
    zs = [v[i][2] for tri in t[seta["desde"]:seta["hasta"]] for i in tri]
    assert min(zs) >= 12.0 - 1e-6 and max(zs) == pytest.approx(33.0, abs=0.05)
    cuerpo = next(r for r in rangos if r["zona"] == "cuerpo")
    assert max(v[i][2] for tri in t[cuerpo["desde"]:cuerpo["hasta"]] for i in tri) <= 1.0 + 1e-6


def test_pieza_sin_zonas_tesela_igual_que_siempre():
    caja = Box(30, 20, 10)
    assert "zonas" not in mesh_payload(caja)
    vertices, triangles = caja.tessellate(0.4, 0.3)
    assert mesh_payload(caja)["indices"] == [i for tri in triangles for i in tri]
    v2, t2, por_cara = teselar_caras(Box(30, 20, 10), 0.4, 0.3)
    assert len(por_cara) == 6 and sum(por_cara) == len(t2)
    # zonas que no calzan con las caras: sale el payload sin zonas, no un error
    assert "zonas" not in mesh_payload(caja, zona_por_cara=("a", "b"))
    v3, t3, rr = teselar_zonas(caja, ("a",))
    assert rr is None and len(t3) == len(teselar(caja)[1])
    with pytest.raises(ValueError, match="no corresponden"):
        agrupar_por_zona(t2, por_cara, ("a",) * 5)


def test_la_zona_sigue_a_la_pieza_colocada_y_a_la_cache_de_geometria():
    d = _doc("ESTOP-40-CAJA", position={"x": 500, "y": -80, "z": 900},
             rotation={"x": 90, "y": 0, "z": 30})
    [feat] = d.scene.values()
    local, _ = build_component("ESTOP-40-CAJA")
    assert zona_por_cara("ESTOP-40-CAJA", feat.shape) == zona_por_cara("ESTOP-40-CAJA", local)
    # open caliente: la forma sale de BinTools (otro TShape) y la zona sigue
    hot = Document.from_apolo_bytes(d.to_apolo_bytes(), warm=unpack(pack(d)))
    [caliente] = hot.scene.values()
    assert not caliente.shape.wrapped.IsPartner(feat.shape.wrapped)
    assert zona_por_cara("ESTOP-40-CAJA", caliente.shape) == zona_por_cara("ESTOP-40-CAJA", local)


def test_una_seta_taladrada_pierde_las_zonas_sin_romperse():
    d = _doc("ESTOP-40-CAJA")
    [fid] = d.scene
    d.execute("drill_hole", {"feature": fid, "diameter": 6, "depth": 10,
                             "position": {"x": 20, "y": 0, "z": 0}, "axis": "z"})
    assert zona_por_cara("ESTOP-40-CAJA", d.scene[fid].shape) is None
    assert zona_por_cara("PERFIL-4040", d.scene[fid].shape) is None  # sin zonas en el catálogo
    assert zona_por_cara(None, d.scene[fid].shape) is None


def test_las_zonas_disjuntas_no_se_unen():
    from build123d import Pos

    with pytest.raises(ValueError, match="2 sólidos"):
        fusionar_zonas({"a": Box(10, 10, 10), "b": Pos(50, 0, 0) * Box(10, 10, 10)})
    solido, por_cara = fusionar_zonas({"a": Box(10, 10, 10)})
    assert por_cara == ("a",) * 6 and len(solido.solids()) == 1


# ── anclas ───────────────────────────────────────────────────────────────────────────────


def _dentro(shape, p) -> bool:
    return shape.is_inside(Vector(*p))


def test_anclas_de_la_seta_de_puerta():
    shape, _ = build_component("ESTOP-40")
    an = CATALOG["ESTOP-40"].anchors
    assert an["montaje"] == {"origin": [0.0, 0.0, 0.0], "axis": [0.0, 0.0, -1.0]}
    assert an["agujero"] == an["montaje"]
    # la cara de apoyo: leyenda encima de z = 0, la puerta (2 mm) libre debajo salvo el cuello
    assert _dentro(shape, (25, 0, 0.5)) and not _dentro(shape, (25, 0, -0.5))
    # el cuello Ø22 pasa por el agujero Ø22,5: material en r < 11, nada entre 11 y 11,25
    assert _dentro(shape, (10.5, 0, -1)) and not _dentro(shape, (11.1, 0, -1))
    # el portacontactos aprieta contra la cara trasera de la puerta
    assert _dentro(shape, (14, 0, -2.5)) and not _dentro(shape, (14, 0, -1.5))


def test_anclas_de_la_seta_en_caja_y_puestas_en_el_mundo():
    shape, _ = build_component("ESTOP-40-CAJA")
    an = CATALOG["ESTOP-40-CAJA"].anchors
    assert an["agujero"]["origin"] == [0.0, 0.0, 55.0]
    for k in ("fijacion_1", "fijacion_2"):
        x, y, z = an[k]["origin"]
        assert z == 0.0 and an[k]["axis"] == [0.0, 0.0, -1.0]
        # el agujero M5 atraviesa la caja; a 4 mm de su eje ya hay pared
        assert not _dentro(shape, (x, y, 1)) and not _dentro(shape, (x, y, 54))
        assert _dentro(shape, (x + 4, y, 1))
    assert _dentro(shape, (0, 0, 1)) and not _dentro(shape, (0, 0, -1))  # base en z = 0
    # la prensaestopa sale por −Y, a media altura
    assert _dentro(shape, (0, -45, 27.5)) and not _dentro(shape, (0, 45, 27.5))
    # colocada: el ancla sigue a la pose
    d = _doc("ESTOP-40-CAJA", position={"x": 100, "y": 200, "z": 300},
             rotation={"x": 90, "y": 0, "z": 0})
    [feat] = d.scene.values()
    assert feat.anchors["montaje"]["origin"] == pytest.approx([100, 200, 300], abs=1e-6)
    ag = feat.anchors["agujero"]
    assert ag["origin"] == pytest.approx([100, 200 - 55, 300], abs=1e-6)
    assert ag["axis"] == pytest.approx([0, 1, 0], abs=1e-9)


def test_parametros_imposibles_se_rechazan():
    with pytest.raises(ValueError, match="montaje 'pared'"):
        seta_emergencia(montaje="pared")
    with pytest.raises(ValueError, match="no entra en la tapa"):
        seta_emergencia(montaje="caja", d_leyenda=70)
    with pytest.raises(ValueError, match="d_seta"):
        seta_emergencia(d_seta=80)


@pytest.mark.parametrize("cambio,mensaje", [
    ({"zonas": None}, r"le falta el bloque `zonas:`"),
    ({"zonas": {"seta": "plastico_rojo_seguridad"}}, r"el builder da las zonas"),
    ({"zonas": {"seta": "rojo_bonito"}}, r"acabado «rojo_bonito» no existe"),
    ({"zonas": {"seta": {"acabado": "plastico_negro", "fijo": "si"}}}, r"fijo: se espera true"),
    ({"builder": "box", "params": {"width": 1, "depth": 1, "height": 1}}, r"sólo vale con un builder"),
])
def test_el_yaml_de_zonas_se_valida(tmp_path, cambio, mensaje):
    import yaml

    comp = {"ref": "S", "name": "Seta", "builder": "seta_emergencia", "weight": 0.1,
            "params": {"montaje": "puerta"},
            "zonas": {z: "plastico_negro" for z in ZONAS_SETA["puerta"]}}
    comp.update(cambio)
    if comp.get("zonas") is None:
        comp.pop("zonas")
    (tmp_path / "a.yaml").write_text(yaml.safe_dump({"category": "x", "components": [comp]},
                                                    allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match=mensaje):
        cat = load_catalog(str(tmp_path))
        cat["S"].builder(None)  # las zonas del builder se comparan al construir


# ── la ficha eléctrica ───────────────────────────────────────────────────────────────────


def test_la_seta_en_caja_pasa_el_erc_igual_que_la_de_puerta():
    a, b = CATALOG["ESTOP-40"].electrico, CATALOG["ESTOP-40-CAJA"].electrico
    assert b.parada_emergencia and (a.bornes, a.caminos, a.modelo, a.simbolo, a.funcion) == (
        b.bornes, b.caminos, b.modelo, b.simbolo, b.funcion)
    assert (a.montaje, b.montaje) == ("puerta", "campo")

    def reglas(ref: str, ubicacion: str = "+TAB1"):
        cmds = arranque_directo()
        for c in cmds:
            if c["type"] == "add_device" and c["params"]["ref"] == "ESTOP-40":
                c["params"].update(ref=ref, ubicacion=ubicacion)
        d = Document("tablero")
        d.execute_many(cmds)
        return erc(d.electrico)

    puerta, caja = reglas("ESTOP-40"), reglas("ESTOP-40-CAJA")
    assert not no_ok(caja), no_ok(caja)
    assert resumen(caja) == resumen(puerta) == {"estado": "ok", "errores": 0, "avisos": 0}
    assert [(r["regla"], r["estado"]) for r in caja] == [(r["regla"], r["estado"]) for r in puerta]
    assert resumen(reglas("ESTOP-40-CAJA", "+CAMPO"))["errores"] == 0  # en la máquina


# ── D6: el epoch ─────────────────────────────────────────────────────────────────────────


def test_un_proyecto_con_estop_abre_con_la_seta_nueva_tras_el_epoch():
    """Una caché escrita antes del bump guarda la CAJA de 72×72×70 con la misma firma: el epoch
    la descarta y el open replaya con la seta. Con el epoch de hoy, la misma caché serviría la
    caja: el bump es lo que lo evita."""
    d = _doc("ESTOP-40")
    [fid] = d.scene
    apolo = d.to_apolo_bytes()
    data = pickle.loads(pack(d))
    vieja = serialize_robust(Box(72, 72, 70).wrapped)
    data["scene_shapes"][fid] = vieja
    data["definitions"] = {k: vieja for k in data["definitions"]}

    antes = {**data, "epoch": GEOM_CACHE_EPOCH - 1}
    assert GEOM_CACHE_EPOCH >= 6 and unpack(pickle.dumps(antes)) is None
    abierto = Document.from_apolo_bytes(apolo, warm=unpack(pickle.dumps(antes)))
    bb = abierto.scene[fid].shape.bounding_box().size
    assert (round(bb.X), round(bb.Y), round(bb.Z)) == (60, 60, 77)
    assert zona_por_cara("ESTOP-40", abierto.scene[fid].shape) is not None

    servida = Document.from_apolo_bytes(apolo, warm=unpack(pickle.dumps(data)))
    bb = servida.scene[fid].shape.bounding_box().size
    assert (round(bb.X), round(bb.Y), round(bb.Z)) == (72, 72, 70)
