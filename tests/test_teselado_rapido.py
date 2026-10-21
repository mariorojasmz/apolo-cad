"""La malla de render se tesela por DEFINICIÓN y se extrae sin build123d (plan teselado-rapido, F1).

- D2: `malla_render.triangular` da los mismos vértices y triángulos que `Shape.tessellate`, en
  el mismo orden de caras, y cuenta los triángulos de cada cara (las zonas de la seta).
- D1: una instancia (`mesh_key` + `matrix`) toma la malla de su definición, teselada UNA vez y
  llevada al mundo con la matriz; un espejo invierte los triángulos (normales hacia afuera).
- La foto de `render_view` y la del manual (EscenaViva) salen como en main (PNG con tolerancia
  de píxel medida) en una escena con instancias, también tras un open caliente, donde la
  definición y la pieza ya no comparten el TShape y `BRepMesh` puede elegir otra diagonal.
- Las zonas de la seta siguen partiendo el actor de cada instancia.
"""

from __future__ import annotations

import io

import numpy as np
import pytest

from apolo.commands.registry import DEFINITIONS
from apolo.doc import Document
from apolo.doc.geomcache import pack, unpack
from apolo.kernel import malla_render, render_comun
from apolo.kernel.malla_render import definicion_de, malla_instancia, triangular
from apolo.kernel.mesh import triangulos_por_cara
from apolo.services.apariencia import apariencias_render
from apolo.services.definiciones import definiciones_de


def _b123d(shape):
    """La malla de main: `Shape.tessellate` a resolución de render, en numpy."""
    v, t = shape.tessellate(0.5, 0.25)
    return (np.array([(p.X, p.Y, p.Z) for p in v], dtype=float).reshape(-1, 3),
            np.asarray(t, dtype=np.int64).reshape(-1, 3))


def _formas():
    from build123d import Box, Compound, Cylinder, Pos, Rotation, Sphere

    caja = Box(30, 20, 10)
    hueca = Box(40, 40, 40) - Cylinder(8, 60)            # caras REVERSED (el agujero)
    esfera = Pos(5, 0, 0) * Sphere(12)
    # compuesto de copias colocadas: caras con ubicación propia (TopLoc no identidad)
    pieza = Box(10, 10, 4).fuse(Cylinder(3, 12))
    copias = Compound([Pos(25 * k, 0, 0) * Rotation(0, 0, 30 * k) * pieza for k in range(3)])
    return {"caja": caja, "hueca": hueca, "esfera": esfera, "copias": copias}


@pytest.mark.parametrize("nombre", ["caja", "hueca", "esfera", "copias", "seta"])
def test_d2_da_lo_mismo_que_build123d_en_el_mismo_orden_de_caras(nombre):
    if nombre == "seta":
        from apolo.library.catalog import build_component

        forma, _ = build_component("ESTOP-40")
    else:
        forma = _formas()[nombre]
    ref_v, ref_t = _b123d(forma)
    xyz, tri, por_cara = triangular(forma)
    assert xyz.shape == ref_v.shape and np.allclose(xyz, ref_v, atol=1e-9)
    assert np.array_equal(tri, ref_t)                       # mismos triángulos, mismo orden
    assert por_cara == triangulos_por_cara(forma) and len(por_cara) == len(forma.faces())
    assert sum(por_cara) == len(tri)
    assert not xyz.flags.writeable and not tri.flags.writeable   # se comparten entre cachés


def test_d2_sobre_una_forma_ya_mallada_mas_fina_usa_esa_malla():
    """Como `Shape.tessellate`: si el payload ya malló más fino (0,4), el render la reutiliza."""
    from build123d import Cylinder

    forma = Cylinder(30, 80)
    forma.mesh(0.4, 0.3)
    ref_v, ref_t = _b123d(forma)
    xyz, tri, _ = triangular(forma)
    assert np.allclose(xyz, ref_v) and np.array_equal(tri, ref_t)


# ── D1: la malla de la definición ────────────────────────────────────────────


def _con_instancias() -> Document:
    d = Document("instancias")
    d.execute_many([
        {"type": "create_box", "params": {"name": "Placa A", "width": 120, "depth": 60,
                                          "height": 10}},
        {"type": "create_box", "params": {"name": "Placa B", "width": 120, "depth": 60,
                                          "height": 10, "position": {"x": 200, "z": 50},
                                          "rotation": {"x": 30, "y": 0, "z": 70}}},
        {"type": "create_box", "params": {"name": "Placa C", "width": 120, "depth": 60,
                                          "height": 10, "position": {"y": 160, "z": 120},
                                          "rotation": {"x": 0, "y": 90, "z": 0}}},
        {"type": "create_cylinder", "params": {"name": "Eje 1", "radius": 15, "height": 200,
                                               "position": {"x": -150}}},
        {"type": "create_cylinder", "params": {"name": "Eje 2", "radius": 15, "height": 200,
                                               "position": {"x": -150, "y": 120},
                                               "rotation": {"x": 90, "y": 0, "z": 0}}},
        {"type": "insert_component", "params": {"component": "ESTOP-40",
                                                "position": {"x": 60, "y": -120, "z": 40}}},
        {"type": "insert_component", "params": {"component": "ESTOP-40",
                                                "position": {"x": 160, "y": -120, "z": 40},
                                                "rotation": {"x": 0, "y": 0, "z": 45}}},
    ])
    return d


def _limpiar_cachés():
    render_comun._RENDER_MESH_CACHE.clear()
    malla_render._LOCAL_CACHE.clear()


def test_d1_cada_definicion_se_tesela_una_vez(monkeypatch):
    d = _con_instancias()
    defs = definiciones_de(d.scene)
    assert len(defs) == 3                                   # placa, eje y seta
    _limpiar_cachés()
    llamadas = []
    original = malla_render.triangular
    monkeypatch.setattr(malla_render, "triangular",
                        lambda forma, *a: llamadas.append(forma) or original(forma, *a))
    from apolo.kernel.render_vtk import extract_render_scene

    snap = extract_render_scene(d.scene, "iso", apariencias=apariencias_render(d),
                                definiciones=defs)
    assert len(snap.items) == 7 and len(llamadas) == 3
    assert {id(f) for f in llamadas} == {id(s) for s in defs.values()}
    # la instancia es la definición llevada al mundo: los mismos nodos que la malla de la pieza
    # y la misma superficie (con otro TShape, `BRepMesh` puede elegir otra diagonal: F0)
    def area(v, t):
        return float(np.linalg.norm(np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]]),
                                    axis=1).sum() / 2)

    for feat in d.scene.values():
        v, t = render_comun.teselar(feat.shape)
        ref_v, ref_t = _b123d(feat.shape)
        assert np.allclose(v, ref_v, atol=1e-6) and len(t) == len(ref_t)
        assert area(v, t) == pytest.approx(area(ref_v, ref_t), rel=1e-3)


def test_d1_no_aplica_a_una_pose_ni_a_una_definicion_que_no_esta():
    d = _con_instancias()
    feat = next(f for f in d.scene.values() if f.name == "Placa B")
    defs = definiciones_de(d.scene)
    assert definicion_de(feat, defs) == (defs[feat.mesh_key], feat.matrix)
    from build123d import Pos

    assert definicion_de(feat, defs, Pos(1, 0, 0) * feat.shape) == (None, None)  # pose/corte
    assert definicion_de(feat, {}) == (None, None)                               # desalojada
    assert definicion_de(feat, None) == (None, None)
    feat_unica = next(f for f in d.scene.values() if f.name == "Placa A")
    d.execute("drill_hole", {"feature": feat_unica.id, "diameter": 8, "depth": 20,
                             "position": {"x": 0, "y": 0, "z": 0}, "axis": "z"})
    taladrada = d.scene[feat_unica.id]
    assert taladrada.mesh_key is None and definicion_de(taladrada, DEFINITIONS) == (None, None)


def test_d1_un_espejo_invierte_los_triangulos_y_las_normales_siguen_afuera():
    from build123d import Box, Cylinder

    definicion = Box(40, 20, 10).fuse(Cylinder(4, 30))   # un sólido cerrado de volumen conocido
    volumen = definicion.volume

    def volumen_firmado(xyz, tri):
        a, b, c = xyz[tri[:, 0]], xyz[tri[:, 1]], xyz[tri[:, 2]]
        return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)

    recta = [[1, 0, 0, 100], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    espejo = [[-1, 0, 0, 100], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    xyz, tri, _ = malla_instancia(definicion, recta)
    assert volumen_firmado(xyz, tri) == pytest.approx(volumen, rel=0.02)
    xyz_e, tri_e, _ = malla_instancia(definicion, espejo)
    assert xyz_e[:, 0] == pytest.approx(200 - xyz[:, 0])
    assert volumen_firmado(xyz_e, tri_e) == pytest.approx(volumen, rel=0.02)   # hacia afuera
    assert np.array_equal(tri_e, tri[:, [0, 2, 1]])


def test_las_zonas_de_la_seta_siguen_en_cada_instancia():
    d = _con_instancias()
    aps = apariencias_render(d)
    defs = definiciones_de(d.scene)
    setas = [f for f in d.scene.values() if f.component == "ESTOP-40"]
    assert len(setas) == 2 and all(aps[f.id].get("zonas") for f in setas)
    _limpiar_cachés()
    from apolo.kernel.render_vtk import extract_render_scene

    snap = extract_render_scene({f.id: f for f in setas}, "iso", apariencias=aps,
                                definiciones=defs)
    for item, feat in zip(snap.items, setas):
        assert item.partes and item.partes[-1][1] == len(item.triangles)
        _limpiar_cachés()
        v, t, partes = render_comun.teselar_con_zonas(feat.shape, aps[feat.id]["zonas"])
        assert [p[:2] for p in partes] == [p[:2] for p in item.partes]   # mismos rangos


# ── el PNG, como en main ─────────────────────────────────────────────────────


def _como_main(monkeypatch):
    """Teselado de main: `Shape.tessellate` pieza por pieza, sin definiciones."""
    from apolo.kernel.mesh import teselar_caras

    def triangular_main(forma, *_a):
        v, t, por_cara = teselar_caras(forma, 0.5, 0.25)
        xyz, tri = (np.array([(p.X, p.Y, p.Z) for p in v], dtype=float).reshape(-1, 3),
                    np.asarray(t, dtype=np.int64).reshape(-1, 3))
        return xyz, tri, por_cara

    monkeypatch.setattr(malla_render, "triangular", triangular_main)


def _rgb(png: bytes):
    from PIL import Image

    return np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).astype(int)


def _distintos(a, b, umbral: int = 16) -> float:
    """Fracción de píxeles en que algún canal difiere más que `umbral` (de 255)."""
    return float((np.abs(_rgb(a) - _rgb(b)).max(axis=2) > umbral).mean())


def _foto(escena, aps, defs):
    from apolo.kernel.render_vtk import extract_render_scene, render_snapshot_vtk

    _limpiar_cachés()
    snap = extract_render_scene(escena, "iso", size_px=600, apariencias=aps, definiciones=defs)
    try:
        return render_snapshot_vtk(snap)
    except Exception as exc:  # noqa: BLE001 — sin contexto OpenGL en este entorno
        pytest.skip(f"VTK off-screen no disponible: {exc}")


@pytest.mark.parametrize("caliente", [False, True])
def test_el_png_de_render_view_es_el_de_main(monkeypatch, caliente):
    d = _con_instancias()
    if caliente:   # open caliente: la definición y la pieza ya no comparten el TShape
        d = Document.from_apolo_bytes(d.to_apolo_bytes(), warm=unpack(pack(d)))
        feat = next(f for f in d.scene.values() if f.name == "Placa B")
        assert not feat.shape.wrapped.IsPartner(DEFINITIONS[feat.mesh_key].wrapped)
    aps = apariencias_render(d)
    nuevo = _foto(d.scene, aps, definiciones_de(d.scene))
    with monkeypatch.context() as m:
        _como_main(m)
        de_main = _foto(d.scene, aps, None)
    # medido: ≤ 0,009 % de píxeles distintos y en 1 nivel de 255 (ninguno pasa de 16)
    assert _distintos(nuevo, de_main) <= 0.001


def test_la_foto_del_manual_es_la_de_main(monkeypatch):
    from apolo.kernel.render_vivo import EscenaViva, colores_fijos, extraer_piezas

    d0 = _con_instancias()   # open caliente: otra malla posible en la instancia (F0)
    d = Document.from_apolo_bytes(d0.to_apolo_bytes(), warm=unpack(pack(d0)))
    aps = apariencias_render(d)

    def foto(defs):
        _limpiar_cachés()
        piezas = extraer_piezas(d.scene, aps, zonas=True, definiciones=defs)
        lo = np.min([p.vertices.min(axis=0) for p in piezas], axis=0)
        hi = np.max([p.vertices.max(axis=0) for p in piezas], axis=0)
        try:
            with EscenaViva((lo, hi), colores_fijos(d.scene), ancho=600, alto=468,
                            apariencias=aps) as esc:
                esc.aplicar(piezas)
                return esc.png()
        except Exception as exc:  # noqa: BLE001 — sin contexto OpenGL en este entorno
            pytest.skip(f"VTK off-screen no disponible: {exc}")

    nuevo = foto(definiciones_de(d.scene))
    with monkeypatch.context() as m:
        _como_main(m)
        de_main = foto(None)
    assert _distintos(nuevo, de_main) <= 0.001   # medido: 0,009 % en 1 nivel


def test_render_view_por_la_api_tesela_cada_definicion_una_vez(monkeypatch):
    from fastapi.testclient import TestClient

    import apolo.api.main as api

    api.DOC = _con_instancias()
    _limpiar_cachés()
    llamadas = []
    original = malla_render.triangular
    monkeypatch.setattr(malla_render, "triangular",
                        lambda forma, *a: llamadas.append(forma) or original(forma, *a))
    r = TestClient(api.app).get("/api/render.png",
                                params={"shade": "true", "vtk_only": "true", "size_px": 300})
    if r.status_code == 503:
        pytest.skip("VTK off-screen no disponible")
    assert r.status_code == 200
    assert len(llamadas) == 3                      # placa, eje y seta: 7 piezas, 3 mallas
