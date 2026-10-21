"""Las zonas de acabado en la foto VTK y en el GLB de la tienda (plan seta-de-emergencia, F3).

- VTK parte el actor de una pieza con zonas: la seta sale roja sobre el anillo amarillo, en su
  lugar (concéntricos, el rojo dentro). Lo `fijo` no toma el color asignado (D3); la caja de
  superficie, pintable, sí.
- El GLB lleva una primitiva por estilo de zona en el nodo de la pieza, cada una con su
  material (dos zonas con el mismo acabado y color se funden: no se distinguen).
- Sin zonas (pieza sin zonas, taladrada o cortada por una sección) todo sale EXACTAMENTE como
  antes: mismo PNG y mismo GLB.
"""

from __future__ import annotations

import io

import numpy as np
import pytest

from apolo.doc import Document
from apolo.kernel import glb
from apolo.kernel.glb_resumen import leer
from apolo.library.apariencia import ACABADOS
from apolo.publicacion import vista3d
from apolo.services.apariencia import apariencias_documento, apariencias_render

ROJO = ACABADOS["plastico_rojo_seguridad"].color
AMARILLO = ACABADOS["plastico_amarillo_seguridad"].color
NEGRO = ACABADOS["plastico_negro"].color
GRIS = ACABADOS["plastico_gris"].color
AZUL = "#1030e0"


@pytest.fixture(scope="module")
def doc():
    d = Document("seta-render")
    d.execute_many([
        {"type": "create_box", "params": {"name": "Puerta", "width": 300, "depth": 200,
                                          "height": 2, "position": {"x": 100, "z": -1}}},
        {"type": "insert_component", "params": {"component": "ESTOP-40"}},
        {"type": "insert_component", "params": {"component": "ESTOP-40",
                                                "position": {"y": 80}}},
        {"type": "insert_component", "params": {"component": "ESTOP-40-CAJA",
                                                "position": {"x": 160}}},
    ])
    return d


def _fid(doc, ref, k=0):
    return [fid for fid, f in doc.scene.items() if f.component == ref][k]


# ── VTK ───────────────────────────────────────────────────────────────────────


def _foto(doc, aps, ids, **kw):
    from apolo.kernel.render_vtk import extract_render_scene, render_snapshot_vtk

    escena = {fid: doc.scene[fid] for fid in ids}
    snap = extract_render_scene(escena, kw.pop("view", "iso"), size_px=500, apariencias=aps,
                                **kw)
    try:
        return snap, render_snapshot_vtk(snap)
    except Exception as exc:  # noqa: BLE001 — sin contexto OpenGL en este entorno
        pytest.skip(f"VTK off-screen no disponible: {exc}")


def _pixeles(png: bytes):
    from PIL import Image

    rgb = np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).astype(float)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    rojo = (r > 90) & (r > 2.2 * g) & (r > 2.2 * b)
    amarillo = (r > 110) & (g > 0.45 * r) & (g < 0.95 * r) & (b < 0.35 * g)
    azul = (b > 90) & (b > 2.0 * r) & (b > 1.5 * g)
    return rojo, amarillo, azul


def _centro_y_radio(mascara):
    filas, cols = np.nonzero(mascara)
    centro = np.array([filas.mean(), cols.mean()])
    radio = np.hypot(filas - centro[0], cols - centro[1])
    return centro, radio


def test_la_seta_de_puerta_sale_roja_sobre_el_anillo_amarillo(doc):
    aps = apariencias_render(doc)
    snap, png = _foto(doc, aps, [_fid(doc, "ESTOP-40")], elevation=90)
    (item,) = snap.items
    assert item.partes is not None and len(item.partes) == 4
    # las partes cubren todos los triángulos, contiguas
    assert item.partes[0][0] == 0 and item.partes[-1][1] == len(item.triangles)
    assert all(a[1] == b[0] for a, b in zip(item.partes, item.partes[1:]))
    rojo, amarillo, _ = _pixeles(png)
    assert rojo.sum() > 2000 and amarillo.sum() > 1000
    # de frente (+Z hacia el operador): la seta Ø40 al centro del anillo de leyenda Ø60
    c_rojo, r_rojo = _centro_y_radio(rojo)
    c_amar, r_amar = _centro_y_radio(amarillo)
    assert np.linalg.norm(c_rojo - c_amar) < 3.0           # concéntricos
    assert r_amar.max() > 1.3 * r_rojo.max()               # el amarillo rodea al rojo
    assert np.percentile(r_amar, 10) > 0.8 * np.percentile(r_rojo, 90)  # anillo, no disco


def test_la_seta_en_caja_y_el_color_asignado_no_pinta_lo_fijo(doc):
    fid = _fid(doc, "ESTOP-40-CAJA")
    _, png = _foto(doc, apariencias_render(doc), [fid])
    rojo, amarillo, azul = _pixeles(png)
    assert rojo.sum() > 1000 and amarillo.sum() > 5000 and azul.sum() == 0
    # la seta (rojo) queda ARRIBA de la caja amarilla en la vista iso (+Z hacia el operador)
    assert np.nonzero(rojo)[0].mean() < np.nonzero(amarillo)[0].mean()

    doc.colors[fid] = AZUL
    try:
        _, pintado = _foto(doc, apariencias_render(doc), [fid])
    finally:
        doc.colors.pop(fid)
    rojo2, amarillo2, azul2 = _pixeles(pintado)
    # la seta no se repinta (fijo): los mismos píxeles, salvo el suavizado de su borde
    assert (rojo2 & rojo).sum() >= 0.99 * rojo.sum() and rojo2.sum() <= 1.01 * rojo.sum()
    assert 0 < amarillo2.sum() < amarillo.sum()  # queda el anillo de leyenda (fijo)
    assert azul2.sum() > 3000                    # la caja de superficie (pintable) sí


def test_el_color_asignado_no_cambia_la_seta_de_puerta(doc):
    fid = _fid(doc, "ESTOP-40")
    _, antes = _foto(doc, apariencias_render(doc), [fid])
    doc.colors[fid] = AZUL
    try:
        _, despues = _foto(doc, apariencias_render(doc), [fid])
    finally:
        doc.colors.pop(fid)
    assert despues == antes  # seta y leyenda fijas; collar y cuerpo moldeados (no pintables)


def test_sin_zonas_la_foto_es_la_de_siempre(doc):
    ids = list(doc.scene)
    # la pieza sin zonas lleva la apariencia de siempre (sin la clave `zonas`)
    aps = apariencias_render(doc)
    puerta = _fid(doc, None)
    assert aps[puerta] == apariencias_documento(doc)[puerta]
    snap, png = _foto(doc, aps, [puerta], view="iso")
    _, png_viejo = _foto(doc, apariencias_documento(doc), [puerta], view="iso")
    assert snap.items[0].partes is None and png == png_viejo
    # con las apariencias de siempre, la seta sale de un solo acabado (como antes de F3)
    snap, _ = _foto(doc, apariencias_documento(doc), ids, view="iso")
    assert all(it.partes is None for it in snap.items)


def test_una_seccion_o_un_taladro_dejan_la_seta_de_un_solo_acabado(doc):
    fid = _fid(doc, "ESTOP-40")
    snap, _ = _foto(doc, apariencias_render(doc), [fid], view="iso", section="x")
    assert snap.items and all(it.partes is None for it in snap.items)

    d = Document("seta-taladrada")
    caja = d.execute("insert_component", {"component": "ESTOP-40-CAJA"})
    d.execute("drill_hole", {"feature": caja, "diameter": 6, "depth": 10,
                             "position": {"x": 20, "y": 0, "z": 0}, "axis": "z"})
    assert apariencias_render(d) == apariencias_documento(d)


# ── GLB ───────────────────────────────────────────────────────────────────────


def _lineal(hexa: str):
    c = np.array([int(hexa[k:k + 2], 16) for k in (1, 3, 5)], dtype=float) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _glb(doc, ruta):
    inf = glb.escribir_glb(vista3d.piezas(doc), ruta, titulo="seta")
    return inf, leer(ruta)


def _primitivas(js, nodo_mesh):
    """[(hex más cercano, accessor de posición)] de las primitivas de la malla."""
    out = []
    for p in js["meshes"][nodo_mesh]["primitives"]:
        color = np.array(js["materials"][p["material"]]["pbrMetallicRoughness"]
                         ["baseColorFactor"][:3])
        hexa = min((ROJO, AMARILLO, NEGRO, GRIS, AZUL),
                   key=lambda h: np.abs(_lineal(h) - color).max())
        assert np.abs(_lineal(hexa) - color).max() < 2e-3
        out.append((hexa, js["accessors"][p["attributes"]["POSITION"]]))
    return out


def _mallas_por_ref(doc, js):
    """{ref: [índice de malla]} en el orden de la escena (el GLB nombra por grupo, no por
    pieza: las instancias salen en el orden de `vista3d.ids_glb`)."""
    con_malla = [n for n in js["nodes"] if "mesh" in n]
    refs = [doc.scene[fid].component for fid in vista3d.ids_glb(doc)]
    assert len(con_malla) == len(refs)
    out: dict = {}
    for ref, n in zip(refs, con_malla):
        out.setdefault(ref, []).append(n["mesh"])
    return out


def test_el_glb_lleva_una_primitiva_por_zona_con_su_material(doc, tmp_path):
    inf, js = _glb(doc, tmp_path / "seta.glb")
    mallas = _mallas_por_ref(doc, js)
    assert len(js["meshes"][mallas[None][0]]["primitives"]) == 1   # la puerta: como siempre
    puerta = _primitivas(js, mallas["ESTOP-40"][0])
    assert sorted(h for h, _ in puerta) == sorted((ROJO, AMARILLO, NEGRO, GRIS))
    acc = dict(puerta)
    # la seta, roja, es lo que más sale hacia el operador (+Z local: el nodo lleva el Y arriba)
    assert acc[ROJO]["max"][2] > acc[AMARILLO]["max"][2] + 0.01
    assert acc[ROJO]["max"][0] - acc[ROJO]["min"][0] == pytest.approx(0.040, abs=2e-3)
    assert acc[AMARILLO]["max"][0] - acc[AMARILLO]["min"][0] == pytest.approx(0.060, abs=2e-3)
    assert inf.piezas == 4
    # la de caja: la leyenda y la caja (mismo amarillo) se funden, igual el negro
    caja = _primitivas(js, mallas["ESTOP-40-CAJA"][0])
    assert sorted(h for h, _ in caja) == sorted((ROJO, AMARILLO, NEGRO))


def test_el_color_asignado_en_el_glb_no_pinta_lo_fijo(doc, tmp_path):
    fid = _fid(doc, "ESTOP-40-CAJA")
    puerta = _fid(doc, "ESTOP-40")
    doc.colors[fid] = AZUL
    doc.colors[puerta] = AZUL
    try:
        _, js = _glb(doc, tmp_path / "pintada.glb")
    finally:
        doc.colors.pop(fid)
        doc.colors.pop(puerta)
    mallas = _mallas_por_ref(doc, js)
    caja = _primitivas(js, mallas["ESTOP-40-CAJA"][0])
    assert sorted(h for h, _ in caja) == sorted((ROJO, AMARILLO, NEGRO, AZUL))
    acc = dict(caja)
    assert acc[AZUL]["max"][0] - acc[AZUL]["min"][0] == pytest.approx(0.072, abs=2e-3)
    # la seta de puerta repintada no cambia: nada en ella es pintable
    assert sorted(h for h, _ in _primitivas(js, mallas["ESTOP-40"][0])) == sorted(
        (ROJO, AMARILLO, NEGRO, GRIS))


def test_el_prototipo_se_comparte_solo_con_los_mismos_estilos(doc, tmp_path):
    from build123d import Location

    seta = doc.scene[_fid(doc, "ESTOP-40-CAJA")].shape
    base = apariencias_render(doc)[_fid(doc, "ESTOP-40-CAJA")]

    def pieza(x, color=None):
        kw = vista3d._zonas(base)
        if color:  # la caja (pintable) repintada en esta instancia
            kw["zonas"] = tuple(glb.ZonaGlb(z.nombre, color) if z.nombre == "caja" else z
                                for z in kw["zonas"])
        return glb.PiezaGlb("Seta", seta.moved(Location((x, 0, 0))), "#808080", **kw)

    iguales = glb.escribir_glb([pieza(0), pieza(100)], tmp_path / "a.glb", titulo="t")
    assert iguales.prototipos == 1
    distintas = glb.escribir_glb([pieza(0), pieza(100, AZUL)], tmp_path / "b.glb", titulo="t")
    assert distintas.prototipos == 2
    js = leer(tmp_path / "b.glb")
    assert sorted(len(m["primitives"]) for m in js["meshes"]) == [3, 4]


def test_una_pieza_sin_zonas_sale_igual_en_el_glb(doc, tmp_path):
    seta = doc.scene[_fid(doc, "ESTOP-40")].shape
    simple = glb.PiezaGlb("Seta", seta, "#808080")
    glb.escribir_glb([simple], tmp_path / "a.glb", titulo="t")
    # zonas que no corresponden a las caras (otra cantidad): la pieza va como si no tuviera
    mala = glb.PiezaGlb("Seta", seta, "#808080", zona_por_cara=("seta",) * 3,
                        zonas=(glb.ZonaGlb("seta", ROJO),))
    glb.escribir_glb([mala], tmp_path / "b.glb", titulo="t")
    assert (tmp_path / "a.glb").read_bytes() == (tmp_path / "b.glb").read_bytes()
    js = leer(tmp_path / "a.glb")
    assert [len(m["primitives"]) for m in js["meshes"]] == [1]


def test_las_caras_del_glb_van_en_el_orden_de_build123d(doc):
    from apolo.kernel.glb_zonas import caras

    seta = doc.scene[_fid(doc, "ESTOP-40-CAJA")].shape
    nuestras = caras(seta.wrapped)
    suyas = [f.wrapped for f in seta.faces()]
    assert len(nuestras) == len(suyas)
    assert all(a.IsSame(b) for a, b in zip(nuestras, suyas))
