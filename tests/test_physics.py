"""F1: drop-test de cuerpos rígidos (gravedad) vía MuJoCo. Skip si no está instalado."""
import pytest

pytest.importorskip("mujoco")  # motor físico opcional (extra `physics`)

from build123d import Box, Pos  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import apolo.api.main as api  # noqa: E402
from apolo.doc import Document  # noqa: E402
from apolo.physics import PhysicsError, drop_test  # noqa: E402
from apolo.physics.anim import render_drop_gif  # noqa: E402


class _Feat:
    """Feature mínima (lo que la sim/GIF leen: .shape y .visible)."""

    def __init__(self, shape, visible=True):
        self.shape = shape
        self.visible = visible


def _pz(frame, name="prod0"):
    return frame["poses"][name][2][3]  # traslación Z (mm) de la pose 4×4


def test_free_fall_rests_on_floor():
    # caja de h=120 soltada a z=1000 sobre el suelo (z=0) → reposa en z ≈ h/2
    res = drop_test({}, [{"w": 200, "d": 150, "h": 120, "x": 0, "y": 0, "z": 1000, "mass": 5}], seconds=2.0)
    assert res["settled"] is True
    assert abs(res["resting"]["prod0"][2] - 60.0) < 5.0


def test_rests_on_static_solid():
    # mesa cuyo tope está en z=760 → la caja reposa en z ≈ 760 + h/2
    mesa = Pos(0, 0, 755) * Box(1000, 400, 10)
    res = drop_test({"mesa": _Feat(mesa)},
                    [{"w": 200, "d": 150, "h": 120, "x": 0, "y": 0, "z": 1100, "mass": 5}], seconds=2.5)
    assert abs(res["resting"]["prod0"][2] - 820.0) < 6.0


def test_trajectory_monotonic_while_falling():
    res = drop_test({}, [{"w": 100, "d": 100, "h": 100, "x": 0, "y": 0, "z": 2000, "mass": 2}],
                    seconds=2.0, fps=20)
    frames = res["frames"]
    assert len(frames) >= 20
    # los primeros fotogramas (antes de tocar suelo) bajan en Z
    assert _pz(frames[0]) > _pz(frames[3]) > _pz(frames[6])


def test_default_mass_positive():
    res = drop_test({}, [{"w": 100, "d": 100, "h": 100, "z": 500}], seconds=0.5)
    assert res["products"][0]["mass"] > 0


def test_multiple_products_settle():
    res = drop_test(
        {},
        [{"w": 120, "d": 120, "h": 120, "x": -200, "z": 800, "mass": 3},
         {"w": 120, "d": 120, "h": 120, "x": 200, "z": 1100, "mass": 3}],
        seconds=2.5,
    )
    assert res["settled"] is True
    assert all(abs(res["resting"][n][2] - 60.0) < 6.0 for n in ("prod0", "prod1"))


def test_empty_products_errors():
    with pytest.raises(PhysicsError):
        drop_test({}, [])


def test_gif_render_header():
    res = drop_test({}, [{"w": 150, "d": 150, "h": 150, "z": 700, "mass": 4}], seconds=1.0, fps=10)
    gif = render_drop_gif({}, res["products"], res["frames"], fps=10)
    assert gif[:6] == b"GIF89a"
    assert len(gif) > 1000


def test_api_drop_and_gif():
    api.DOC = Document("physics-api")
    api.DOC.execute("create_box", {"name": "mesa", "length": 1000, "width": 400, "height": 20,
                                   "position": {"x": 0, "y": 0, "z": 740}})
    client = TestClient(api.app)
    body = {"products": [{"w": 200, "d": 150, "h": 120, "x": 0, "y": 0, "z": 1100, "mass": 5}],
            "seconds": 2.0, "fps": 15}
    r = client.post("/api/physics/drop", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["settled"] is True
    assert abs(data["resting"]["prod0"][2] - 810.0) < 8.0  # tope mesa 750 + 60

    g = client.post("/api/physics/drop.gif", json=body)
    assert g.status_code == 200
    assert g.headers["content-type"] == "image/gif"
    assert g.content[:6] == b"GIF89a"


def test_api_drop_empty_products_400():
    api.DOC = Document("physics-empty")
    client = TestClient(api.app)
    r = client.post("/api/physics/drop", json={"products": []})
    assert r.status_code == 400
