"""Dos-locks render/física (V6.2c): la extracción OCCT (teselado/cascos) corre bajo
STATE_LOCK y produce datos PUROS; el render VTK y la simulación MuJoCo corren fuera.

Aquí: equivalencia de resultado (el split reproduce el monolito) + caché de teselado. Las
pruebas de CONCURRENCIA (que STATE_LOCK queda libre durante render/sim) van en
test_torture.py (usan hilos + Event).
"""

from __future__ import annotations

import pytest

from apolo.doc.document import Document


def _model(n: int = 6) -> Document:
    d = Document("2l")
    for i in range(n):
        d.execute("create_box", {"name": f"b{i}", "width": 40 + i, "depth": 30,
                                 "height": 20, "position": {"x": i * 80}})
    return d


# ---------------------------------------------------------------- render (extract)


def test_extract_render_scene_metadata():
    from apolo.kernel.render_vtk import RenderSnapshot, extract_render_scene

    snap = extract_render_scene(_model(6).scene, "iso", size_px=400)
    assert isinstance(snap, RenderSnapshot)
    assert len(snap.items) == 6  # una por pieza visible
    for it in snap.items:
        assert len(it.vertices) > 0 and len(it.triangles) > 0
        assert it.opacity == 1.0  # opacas por defecto
    assert not snap.any_translucent


def test_extract_empty_scene_raises():
    from apolo.kernel.render_vtk import extract_render_scene

    with pytest.raises(ValueError):
        extract_render_scene({}, "iso")


def test_extract_highlight_xray_opacity():
    from apolo.kernel.render_vtk import extract_render_scene

    d = _model(3)
    ids = list(d.scene)
    snap = extract_render_scene(d.scene, "iso", highlight_ids=[ids[0]], xray=True)
    ops = {round(it.opacity, 2) for it in snap.items}
    assert 1.0 in ops    # la resaltada, sólida
    assert 0.16 in ops   # el contexto, translúcido en xray
    assert snap.any_translucent


def test_render_mesh_cache_reused():
    import apolo.kernel.render_vtk as rv

    d = _model(3)
    rv._RENDER_MESH_CACHE.clear()
    first = {}
    for feat in d.scene.values():
        v, _t = rv._cached_tessellate(feat.shape)
        first[id(feat.shape)] = v
    assert len(rv._RENDER_MESH_CACHE) == 3
    # segunda pasada: HIT → mismos objetos, la caché no crece
    for feat in d.scene.values():
        v, _t = rv._cached_tessellate(feat.shape)
        assert v is first[id(feat.shape)]
    assert len(rv._RENDER_MESH_CACHE) == 3


@pytest.mark.skipif(True, reason="render VTK real necesita contexto OpenGL; el byte-exacto se verifica aparte")
def test_render_snapshot_vtk_smoke():  # pragma: no cover
    from apolo.kernel.render_vtk import extract_render_scene, render_snapshot_vtk

    png = render_snapshot_vtk(extract_render_scene(_model(2).scene, "iso", size_px=200))
    assert png[:4] == b"\x89PNG"


# ---------------------------------------------------------------- física (split)


def test_stability_prepare_simulate_equivalence():
    from apolo.physics.stability import prepare_stability, simulate_stability, stability_test

    d = _model(4)  # todas dinámicas (sin grounds) → caen
    args = (d.scene, d.joints, d.mates, d.fasteners, d.grounds)
    snap = prepare_stability(*args, seconds=0.4, fps=6)
    assert snap.xml is not None and snap.products
    res = simulate_stability(snap)
    res2 = stability_test(*args, seconds=0.4, fps=6)  # wrapper prepare+simulate
    assert {r["id"] for r in res["fell"]} == {r["id"] for r in res2["fell"]}
    assert res["n_dynamic"] == res2["n_dynamic"] == 4


def test_stability_no_dynamic_early_return():
    from apolo.physics.stability import prepare_stability, simulate_stability

    d = Document("grounded")
    a = d.execute("create_box", {"width": 100, "depth": 100, "height": 10, "position": {"z": 0}})
    d.execute("ground", {"name": "g", "feature": a})
    snap = prepare_stability(d.scene, d.joints, d.mates, d.fasteners, d.grounds, seconds=0.4)
    assert snap.xml is None and snap.early is not None
    res = simulate_stability(snap)  # no toca MuJoCo
    assert res["n_dynamic"] == 0 and res["fell"] == []


def test_drop_prepare_simulate_equivalence():
    from apolo.physics.sim import drop_test, prepare_drop, simulate_drop

    d = _model(2)
    products = [{"w": 50, "d": 50, "h": 50, "x": 0, "y": 0, "z": 500}]
    snap = prepare_drop(d.scene, products, seconds=0.4, fps=6)
    assert snap.xml and snap.named
    res = simulate_drop(snap)
    res2 = drop_test(d.scene, products, seconds=0.4, fps=6)
    assert set(res["resting"]) == set(res2["resting"])
    assert len(res["products"]) == 1
