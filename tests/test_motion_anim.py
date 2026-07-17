"""GIF del estudio de movimiento: fase OCCT (fotogramas + cámara fija).

La fase VTK (`render_motion_gif`) no se testea aquí: exige contexto OpenGL, igual
que el resto del render. Lo testeable —y lo que se rompe— es el muestreo del
recorrido y el ENCUADRE ÚNICO.
"""
import numpy as np
import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.robotics.anim import extract_motion_frames


def _swinging_arm():
    """base fija + brazo largo con junta giratoria: al girar, el bbox de la escena
    CAMBIA mucho → sirve para comprobar que la cámara no 'respira'."""
    d = Document()
    base = d.execute("create_box", {"name": "base", "width": 100, "depth": 100, "height": 20})
    arm = d.execute("create_box", {"name": "brazo", "width": 400, "depth": 40, "height": 20,
                                   "position": {"x": 200}})
    d.execute("add_joint", {
        "name": "gira", "type": "giratoria", "parent": base, "child": arm,
        "origin": {"x": 0, "y": 0, "z": 0}, "axis": {"x": 0, "y": 1, "z": 0},
        "lower": -90, "upper": 90,
    })
    return d


KF = [{"t": 0, "values": {"gira": 0}}, {"t": 1, "values": {"gira": 80}}]


def test_frame_count_matches_steps():
    d = _swinging_arm()
    snaps = extract_motion_frames(d, KF, steps=6)
    assert len(snaps) == 7          # steps intervalos → steps+1 fotogramas


def test_pingpong_adds_return_without_repeating_ends():
    d = _swinging_arm()
    snaps = extract_motion_frames(d, KF, steps=4)
    ping = extract_motion_frames(d, KF, steps=4, pingpong=True)
    # 5 de ida + 3 de vuelta (no repite ni el primero ni el último) = 8
    assert len(snaps) == 5
    assert len(ping) == 8


def test_camera_is_locked_across_frames():
    """El bug que esto ataca: sin encuadre único, cada fotograma se re-encuadra a su
    propio bbox y el mecanismo 'salta'/'respira' en el GIF."""
    d = _swinging_arm()
    snaps = extract_motion_frames(d, KF, steps=8)
    first = (snaps[0].fmins, snaps[0].fmaxs)
    for s in snaps:
        assert np.allclose(s.fmins, first[0])
        assert np.allclose(s.fmaxs, first[1])
    # y ese encuadre CONTIENE a todos los fotogramas (es la unión, no el primero)
    for s in snaps:
        assert np.all(s.smins >= first[0] - 1e-6)
        assert np.all(s.smaxs <= first[1] + 1e-6)
    # el brazo se mueve de verdad → la unión es ESTRICTAMENTE mayor que el bbox de un
    # fotograma suelto (aquí crece por abajo: girar +80° sobre +Y baja el brazo)
    assert np.any(snaps[0].smins > first[0] + 1e-6) or np.any(snaps[0].smaxs < first[1] - 1e-6)


def test_fit_ids_wins_over_locked_camera():
    d = _swinging_arm()
    snaps = extract_motion_frames(d, KF, steps=3, fit_ids=["c1"])
    assert all(np.isfinite(s.fmins).all() for s in snaps)   # lo fijó extract_render_scene


def test_empty_keyframes_raises():
    d = _swinging_arm()
    with pytest.raises(ValueError):
        extract_motion_frames(d, [], steps=4)


def test_static_study_gives_single_frame():
    d = _swinging_arm()
    snaps = extract_motion_frames(d, [{"t": 0, "values": {"gira": 30}}], steps=8)
    assert len(snaps) == 1          # duración 0 → un solo fotograma, no 9 iguales


def test_api_motion_gif_404_lists_available():
    api.DOC = _swinging_arm()
    client = TestClient(api.app)
    api.DOC.set_motion("Barrido", KF)
    r = client.post("/api/motion.gif", json={"name": "NoExiste"})
    assert r.status_code == 404
    assert "Barrido" in r.json()["detail"]      # el error dice cuáles hay
