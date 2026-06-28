"""Simulación de gravedad de TODA la máquina: ¿qué pieza se cae?

A diferencia del drop-test (productos cayendo sobre la máquina estática), aquí la
MÁQUINA es el sujeto. Las piezas con sujeción declarada hasta el piso (grafo de
conectividad de `assembly/connectivity.py`) se modelan ESTÁTICAS; las demás son
cuerpos rígidos DINÁMICOS que caen bajo gravedad, con colisión por CASCO CONVEXO.
Reporta qué piezas se desplazan (caen) y cuánto, y deja las poses por fotograma
para animarlo. Read-only: no muta el documento. MuJoCo trabaja en SI → mm↔m.

Esto resuelve lo que el chequeo estático no podía: una pieza no sujeta que REPOSA
sobre algo firme NO cae (la física lo decide), mientras que una pieza sin nada
debajo (un rodillo de retorno colgando, un motor solo colocado) SÍ cae.

`with_autodetect` superpone el grafo de contacto geométrico (efímero) para no
exigir declarar toda la estructura; `exclude` fuerza a tratar ciertas piezas como
NO sujetas ("¿y si a esta le falta el tornillo?") aunque la conectividad las
sujetara.
"""

from __future__ import annotations

import math

from apolo.physics.sim import MM, PhysicsError, _pose_matrix, _require_mujoco
from apolo.robotics.model import _link_physics, _safe_name

_FELL_MM = 15.0  # desplazamiento del centro de masa que cuenta como "se cayó/movió"


def _grounded_set(scene, joints, mates, fasteners, grounds, with_autodetect, exclude):
    from apolo.assembly.connectivity import build_graph, soundness_report

    extra_edges: list = []
    extra_grounds: set = set()
    if with_autodetect:
        from apolo.assembly.autodetect import detect_connections

        det = detect_connections(scene)
        extra_edges = [(c["a"], c["b"], "contacto", "") for c in det["fasteners"]]
        extra_grounds = {g["feature"] for g in det["grounds"]}
    graph = build_graph(
        scene, joints, mates, fasteners, grounds,
        extra_edges=extra_edges, extra_grounds=extra_grounds,
    )
    grounded = set(soundness_report(graph)["grounded"]) - set(exclude or [])
    return grounded


def stability_test(
    scene, joints, mates, fasteners, grounds, *,
    seconds: float = 2.0, gravity: float = 9.81, fps: int = 12,
    with_autodetect: bool = False, exclude=None,
) -> dict:
    """Simula la gravedad sobre la máquina. Devuelve {fell, estables, products,
    frames, settled, n_grounded, n_dynamic}. `products`/`frames` tienen el formato
    de drop_test → se reusa `anim.render_drop_gif` (con la escena estática de fondo)."""
    mujoco = _require_mujoco()
    from apolo.physics.hull import hull_vertices

    seconds = max(0.1, min(float(seconds), 30.0))
    fps = max(2, min(int(fps), 60))
    grounded = _grounded_set(scene, joints, mates, fasteners, grounds, with_autodetect, exclude)

    assets: list[str] = []
    statics: list[str] = []
    bodies: list[str] = []
    products: list[dict] = []
    initial: dict[str, tuple] = {}  # name -> com (mm)
    names: dict[str, str] = {}      # name -> id

    for fid, feat in scene.items():
        if not getattr(feat, "visible", True):
            continue
        try:
            if float(feat.shape.volume) <= 0:
                continue
        except Exception:  # noqa: BLE001
            continue
        verts = hull_vertices(feat.shape)
        if len(verts) < 4:
            continue
        name = _safe_name(f"{fid}")
        if fid in grounded:
            v = " ".join(f"{x * MM:.5f} {y * MM:.5f} {z * MM:.5f}" for x, y, z in verts)
            assets.append(f'<mesh name="m_{name}" vertex="{v}"/>')
            statics.append(f'<geom type="mesh" mesh="m_{name}"/>')
        else:
            mass, com, size = _link_physics(feat)
            cx, cy, cz = com
            v = " ".join(
                f"{(x - cx) * MM:.5f} {(y - cy) * MM:.5f} {(z - cz) * MM:.5f}" for x, y, z in verts
            )
            assets.append(f'<mesh name="m_{name}" vertex="{v}"/>')
            bodies.append(
                f'<body name="{name}" pos="{cx * MM:.5f} {cy * MM:.5f} {cz * MM:.5f}">'
                f'<freejoint/><geom type="mesh" mesh="m_{name}" mass="{max(mass, 0.01):.4f}"/></body>'
            )
            products.append({"name": name, "id": fid, "nombre": getattr(feat, "name", fid),
                             "w": size[0], "d": size[1], "h": size[2],
                             "com": [round(cx, 3), round(cy, 3), round(cz, 3)]})
            initial[name] = com
            names[name] = fid

    if not products:
        return {"n_grounded": len(grounded), "n_dynamic": 0, "fell": [], "estables": [],
                "settled": True, "products": [], "frames": [],
                "mensaje": "Ninguna pieza dinámica: todo está sujeto a tierra."}

    xml = (
        f'<mujoco><option gravity="0 0 -{gravity}" timestep="0.004"/>'
        f'<asset>{"".join(assets)}</asset><worldbody>'
        f'<geom name="floor" type="plane" size="100 100 0.1"/>'
        f'{"".join(statics)}{"".join(bodies)}</worldbody></mujoco>'
    )
    try:
        model = mujoco.MjModel.from_xml_string(xml)
    except Exception as exc:  # noqa: BLE001
        raise PhysicsError(f"No se pudo construir el mundo físico: {exc}") from exc
    data = mujoco.MjData(model)

    ids = {name: mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name) for name in initial}

    def capture(t):
        return {"t": round(t, 3),
                "poses": {n: _pose_matrix(data.xpos[i], data.xquat[i]) for n, i in ids.items()}}

    steps = max(1, int(seconds / model.opt.timestep))
    sample_every = max(1, steps // fps)
    mujoco.mj_forward(model, data)
    frames = [capture(0.0)]
    for s in range(1, steps + 1):
        mujoco.mj_step(model, data)
        if s % sample_every == 0 or s == steps:
            frames.append(capture(s * model.opt.timestep))

    fell, estables = [], []
    for name, i in ids.items():
        cx, cy, cz = initial[name]
        nx, ny, nz = (float(data.xpos[i][k]) / MM for k in range(3))
        drop = math.sqrt((nx - cx) ** 2 + (ny - cy) ** 2 + (nz - cz) ** 2)
        row = {"id": names[name], "nombre": next(p["nombre"] for p in products if p["name"] == name),
               "caida_mm": round(drop, 1)}
        (fell if drop > _FELL_MM else estables).append(row)
    fell.sort(key=lambda r: -r["caida_mm"])
    settled = bool(math.sqrt(sum(float(v) ** 2 for v in data.qvel)) < 0.05) if model.nv else True
    return {"n_grounded": len(grounded), "n_dynamic": len(products),
            "fell": fell, "estables": estables, "settled": settled,
            "products": products, "frames": frames}
