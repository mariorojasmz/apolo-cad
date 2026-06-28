"""Drop-test de cuerpos rígidos con MuJoCo (gravedad / producto cayendo).

Construye un mundo MJCF: la escena del documento como cajas ESTÁTICAS (AABB de cada
sólido) + un suelo, y los "productos" como cajas DINÁMICAS con freejoint que caen bajo
gravedad. Devuelve la trayectoria (pose 4×4 por producto y fotograma, en mm) y las
posiciones de reposo. Es análisis: no muta el documento. MuJoCo trabaja en SI → mm↔m.
"""

from __future__ import annotations

import math

MM = 0.001  # mm → m


class PhysicsError(Exception):
    pass


def _require_mujoco():
    try:
        import mujoco  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise PhysicsError(
            "MuJoCo no está instalado: ejecuta `pip install mujoco` para la simulación física"
        ) from exc
    return __import__("mujoco")


def _pose_matrix(pos_m, quat_wxyz) -> list[list[float]]:
    """Matriz rígida 4×4 (filas) con traslación en mm desde pos (m) y rotación desde
    el cuaternión MuJoCo (w, x, y, z)."""
    w, x, y, z = (float(c) for c in quat_wxyz)
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    r = [
        [1 - 2 * (yy + zz), 2 * (xy - wz), 2 * (xz + wy)],
        [2 * (xy + wz), 1 - 2 * (xx + zz), 2 * (yz - wx)],
        [2 * (xz - wy), 2 * (yz + wx), 1 - 2 * (xx + yy)],
    ]
    t = [pos_m[0] / MM, pos_m[1] / MM, pos_m[2] / MM]
    return [
        [r[0][0], r[0][1], r[0][2], t[0]],
        [r[1][0], r[1][1], r[1][2], t[1]],
        [r[2][0], r[2][1], r[2][2], t[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _static_geoms(scene) -> str:
    parts = []
    for feat in scene.values():
        if not getattr(feat, "visible", True):
            continue
        try:
            if float(feat.shape.volume) <= 0:
                continue
            bb = feat.shape.bounding_box()
        except Exception:  # noqa: BLE001
            continue
        cx, cy, cz = (bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2
        hx = max(bb.max.X - bb.min.X, 1.0) / 2
        hy = max(bb.max.Y - bb.min.Y, 1.0) / 2
        hz = max(bb.max.Z - bb.min.Z, 1.0) / 2
        parts.append(
            f'<geom type="box" pos="{cx * MM:.5f} {cy * MM:.5f} {cz * MM:.5f}" '
            f'size="{hx * MM:.5f} {hy * MM:.5f} {hz * MM:.5f}"/>'
        )
    return "\n".join(parts)


def drop_test(scene, products, seconds: float = 2.0, gravity: float = 9.81, fps: int = 20) -> dict:
    """Simula la caída de `products` sobre `scene`. Cada producto es un dict con
    w/d/h (mm), x/y/z (mm, pose inicial) y mass opcional (kg). Devuelve
    {frames:[{t, poses:{name: mat4x4 mm}}], resting:{name:[x,y,z] mm}, settled, products}."""
    mujoco = _require_mujoco()
    if not products:
        raise PhysicsError("Indica al menos un producto que dejar caer")
    seconds = max(0.1, min(float(seconds), 30.0))
    fps = max(2, min(int(fps), 60))

    named = []
    bodies = []
    for i, p in enumerate(products):
        name = f"prod{i}"
        w, d, h = float(p["w"]), float(p["d"]), float(p["h"])
        if min(w, d, h) <= 0:
            raise PhysicsError("Las dimensiones del producto deben ser > 0")
        x, y, z = float(p.get("x", 0)), float(p.get("y", 0)), float(p.get("z", 0))
        vol_m3 = (w * d * h) * (MM ** 3)
        mass = float(p.get("mass") or max(0.02, vol_m3 * 600.0))  # ~cartón/plástico ligero
        named.append((name, {"w": w, "d": d, "h": h, "x": x, "y": y, "z": z, "mass": mass}))
        bodies.append(
            f'<body name="{name}" pos="{x * MM:.5f} {y * MM:.5f} {z * MM:.5f}">'
            f'<freejoint/><geom type="box" size="{w / 2 * MM:.5f} {d / 2 * MM:.5f} {h / 2 * MM:.5f}" '
            f'mass="{mass:.4f}"/></body>'
        )

    xml = (
        f'<mujoco><option gravity="0 0 -{gravity}" timestep="0.004"/><worldbody>'
        f'<geom name="floor" type="plane" size="100 100 0.1"/>'
        f"{_static_geoms(scene)}\n{''.join(bodies)}"
        f"</worldbody></mujoco>"
    )
    try:
        model = mujoco.MjModel.from_xml_string(xml)
    except Exception as exc:  # noqa: BLE001
        raise PhysicsError(f"No se pudo construir el mundo físico: {exc}") from exc
    data = mujoco.MjData(model)

    def bid(name):
        return mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)

    ids = {name: bid(name) for name, _ in named}

    def capture(t):
        poses = {name: _pose_matrix(data.xpos[i], data.xquat[i]) for name, i in ids.items()}
        return {"t": round(t, 3), "poses": poses}

    steps = max(1, int(seconds / model.opt.timestep))
    sample_every = max(1, steps // fps)
    mujoco.mj_forward(model, data)
    frames = [capture(0.0)]
    for s in range(1, steps + 1):
        mujoco.mj_step(model, data)
        if s % sample_every == 0 or s == steps:
            frames.append(capture(s * model.opt.timestep))

    resting = {name: [round(float(data.xpos[i][k]) / MM, 1) for k in range(3)] for name, i in ids.items()}
    settled = bool(math.sqrt(sum(float(v) ** 2 for v in data.qvel)) < 0.05) if model.nv else True
    return {"frames": frames, "resting": resting, "settled": settled,
            "products": [{"name": n, **meta} for n, meta in named]}
