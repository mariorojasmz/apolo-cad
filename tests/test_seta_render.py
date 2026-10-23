"""Las zonas de acabado en la foto VTK y en el GLB de la tienda (plan seta-de-emergencia, F3).

- VTK parte el actor de una pieza con zonas: la seta sale roja sobre el anillo amarillo, en su
  lugar (concéntricos, el rojo dentro). Lo `fijo` no toma el color asignado (D3); la caja de
  superficie, pintable, sí.
- El GLB (`kernel/glb.py`) recorre las caras en el orden de build123d; una pieza sin zonas, o con
  zonas que no casan con sus caras, sale EXACTAMENTE como antes. Lo que arma con eso la vista 3D
  de la tienda (una primitiva por estilo de zona, prototipos compartidos) se prueba con la fábrica
  de publicaciones, que vive fuera del núcleo.
- Sin zonas (pieza sin zonas, taladrada o cortada por una sección) la foto sale EXACTAMENTE como
  antes: el mismo PNG.
"""

from __future__ import annotations

import io

import numpy as np
import pytest

from apolo.doc import Document
from apolo.kernel import glb
from apolo.kernel.glb_resumen import leer
from apolo.library.apariencia import ACABADOS
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


def test_las_caras_del_glb_van_en_el_orden_de_build123d(doc):
    from apolo.kernel.glb_zonas import caras

    seta = doc.scene[_fid(doc, "ESTOP-40-CAJA")].shape
    nuestras = caras(seta.wrapped)
    suyas = [f.wrapped for f in seta.faces()]
    assert len(nuestras) == len(suyas)
    assert all(a.IsSame(b) for a, b in zip(nuestras, suyas))


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
