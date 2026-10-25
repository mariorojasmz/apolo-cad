"""Executors de colocación: transform, center_in, distribute, attach y snap_to, con la rígida
mundial (`_world_move`, `_world_place`) y el frame de una cara plana (`_planar_face_frame`).

Salieron de `registry.py` (plan partir-nucleo-congelado, F3) SIN cambiar su código: la huella de
`tests/test_contrato_comandos.py` es la misma. `registry` los re-exporta por IDENTIDAD (lo usan
también `exec_transmision` y `exec_modificar`); params de la fachada `.models`.
"""

from __future__ import annotations

from apolo.kernel import move_rotated_about_center

from .errors import CommandError
from .escena import Feature, Scene, _require
from .models import AttachParams, CenterInParams, DistributeParams, SnapToParams, TransformParams
from .state import ExecContext


def _world_move(feat: Feature, translate, rotate) -> None:
    """Aplica la transformación mundial `W = T·T(c)·R·T(-c)` (c = centro del bbox = el mismo
    que usa move_rotated_about_center) al shape y compone la MISMA rígida en la matriz de
    instancia y en las anclas (V6.3d Fix 1: los conectores por ancla deben viajar con el shape;
    lo usan transform/center_in/distribute/attach). REEMPLAZA los dicts, jamás los muta."""
    if feat.matrix is not None or feat.anchors:
        from apolo.kernel.matrix import (
            multiply, rotation_about_center, transform_anchors, translation,
        )

        bb = feat.shape.bounding_box()
        center = ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)
        w = translation(*translate)
        if any(rotate):
            w = multiply(w, rotation_about_center(center, rotate))
        if feat.matrix is not None:
            feat.matrix = multiply(w, feat.matrix)
        if feat.anchors:
            feat.anchors = transform_anchors(w, feat.anchors)
    feat.shape = move_rotated_about_center(feat.shape, translate, rotate)


def _world_place(feat: Feature, translate, axis, angle_deg: float, center) -> None:
    """Espejo de `_world_move` con rotación por EJE ARBITRARIO (axis-angle, mano
    derecha — la misma convención de gp_Trsf/Shape.rotate): W = T · R(eje, θ sobre
    `center`). Compone la MISMA rígida en la matriz de instancia y las anclas
    (V6.8-E: el snap cara-a-cara la necesita — euler no expresa un eje inclinado)."""
    rotating = abs(angle_deg) > 1e-9
    if feat.matrix is not None or feat.anchors:
        from apolo.kernel.matrix import (
            multiply, rotation_axis_angle_about, transform_anchors, translation,
        )

        w = translation(*translate)
        if rotating:
            w = multiply(w, rotation_axis_angle_about(center, axis, angle_deg))
        if feat.matrix is not None:
            feat.matrix = multiply(w, feat.matrix)
        if feat.anchors:
            feat.anchors = transform_anchors(w, feat.anchors)
    from build123d import Axis, Pos

    shape = feat.shape
    if rotating:
        shape = shape.rotate(Axis(center, axis), angle_deg)
    if any(translate):
        shape = Pos(*translate) * shape
    feat.shape = shape


def _exec_transform(ctx: ExecContext, cmd_id: str, p: TransformParams) -> None:
    feat = _require(ctx.scene, p.feature)
    _world_move(feat, p.translate.tuple(), p.rotate.tuple())


def _bbox_center(shape):
    bb = shape.bounding_box()
    return ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)


def _exec_center_in(ctx: ExecContext, cmd_id: str, p: CenterInParams) -> None:
    """Centra `feature` dentro de `into` en los ejes pedidos (mueve en sitio). Se reevalúa
    al regenerar → si `into` cambia, el sólido se recentra solo."""
    if p.feature == p.into:
        raise CommandError("Un sólido no puede centrarse dentro de sí mismo")
    feat = _require(ctx.scene, p.feature)
    cont = _require(ctx.scene, p.into)
    fc = _bbox_center(feat.shape)
    cc = _bbox_center(cont.shape)
    idx = {"x": 0, "y": 1, "z": 2}
    t = [0.0, 0.0, 0.0]
    for ax in p.axes:
        i = idx[ax]
        t[i] = cc[i] - fc[i]
    _world_move(feat, tuple(t), (0, 0, 0))


def _exec_distribute(ctx: ExecContext, cmd_id: str, p: DistributeParams) -> None:
    """Reparte los `features` con centros equiespaciados de `start` a `end` en `axis`
    (mueve cada uno en sitio). Colocación por intención, no por coordenadas calculadas."""
    feats = [_require(ctx.scene, fid) for fid in p.features]
    n = len(feats)
    if n < 2:
        raise CommandError("distribute necesita al menos 2 sólidos")
    i_ax = {"x": 0, "y": 1, "z": 2}[p.axis]
    span = p.end - p.start
    for i, feat in enumerate(feats):
        target = p.start + span * i / (n - 1)
        c = _bbox_center(feat.shape)[i_ax]
        t = [0.0, 0.0, 0.0]
        t[i_ax] = target - c
        _world_move(feat, tuple(t), (0, 0, 0))


def _v_sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _v_dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _v_cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _v_unit(a):
    import math

    n = math.sqrt(_v_dot(a, a))
    if n < 1e-12:
        raise CommandError("Vector nulo al construir el frame de la cara")
    return (a[0] / n, a[1] / n, a[2] / n)


def _planar_face_frame(feat, selector: dict | None, *, quien: str):
    """(cara, origen, normal, u, v) de una cara PLANA elegida con el selector
    declarativo (V6.8-E). u = eje de MAYOR extensión de la cara («eje mayor»), con
    el signo hacia su componente mundial dominante positiva; v = normal × u (terna
    derecha). Cara no plana → CommandError claro (las cilíndricas son territorio
    de los mates, no se duplican aquí)."""
    from apolo.kernel.selectors import SelectorError, resolve_faces

    try:
        faces = resolve_faces(feat.shape, selector or {"mode": "todas"})
    except SelectorError as exc:
        raise CommandError(f"Selector de {quien} inválido: {exc}") from exc
    face = faces[0]
    gt = str(getattr(face, "geom_type", "")).upper()
    if "PLANE" not in gt:
        raise CommandError(
            f"La {quien} debe ser PLANA (es {gt.lower() or 'desconocida'}); "
            "para caras cilíndricas usa add_mate concéntrico"
        )
    c = face.center()
    o = (float(c.X), float(c.Y), float(c.Z))
    nv = face.normal_at()
    n = _v_unit((float(nv.X), float(nv.Y), float(nv.Z)))
    ref = min(
        ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        key=lambda w: abs(_v_dot(w, n)),
    )
    x0 = _v_unit(_v_cross(ref, n))
    y0 = _v_cross(n, x0)
    pts = [(float(v.X), float(v.Y), float(v.Z)) for v in face.vertices()]

    def _spread(ax):
        d = [_v_dot(_v_sub(pt, o), ax) for pt in pts]
        return (max(d) - min(d)) if d else 0.0

    u = x0 if _spread(x0) >= _spread(y0) else y0
    dom = max(range(3), key=lambda i: abs(u[i]))
    if u[dom] < 0:  # signo determinista: hacia la componente mundial dominante +
        u = (-u[0], -u[1], -u[2])
    v = _v_cross(n, u)
    return face, o, n, u, v


_ANCHOR_FNS = {
    "centro": lambda bb, c: c,
    "base": lambda bb, c: (c[0], c[1], bb.min.Z),
    "tope": lambda bb, c: (c[0], c[1], bb.max.Z),
    "min_x": lambda bb, c: (bb.min.X, c[1], c[2]),
    "max_x": lambda bb, c: (bb.max.X, c[1], c[2]),
    "min_y": lambda bb, c: (c[0], bb.min.Y, c[2]),
    "max_y": lambda bb, c: (c[0], bb.max.Y, c[2]),
}


def _anchor_point(shape, anchor: str) -> tuple[float, float, float]:
    bb = shape.bounding_box()
    center = ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)
    return _ANCHOR_FNS[anchor](bb, center)


def _exec_attach(ctx: ExecContext, cmd_id: str, p: AttachParams) -> None:
    feat = _require(ctx.scene, p.feature)
    target = _require(ctx.scene, p.target)
    if p.feature == p.target:
        raise CommandError("Un sólido no puede ensamblarse consigo mismo")

    # 1 · orientación: girar sobre su centro para alinear ejes
    if p.align_my and p.align_to and p.align_my != p.align_to:
        from apolo.kernel.matrix import euler_between_axes

        _world_move(feat, (0, 0, 0), euler_between_axes(p.align_my, p.align_to))

    # 2 · traslación: ancla a ancla (con el bbox ya reorientado)
    src = _anchor_point(feat.shape, p.anchor)
    dst = _anchor_point(target.shape, p.target_anchor)
    delta = (
        dst[0] - src[0] + p.offset.x,
        dst[1] - src[1] + p.offset.y,
        dst[2] - src[2] + p.offset.z,
    )
    _world_move(feat, delta, (0, 0, 0))


def _exec_snap_face(scene: Scene, p: SnapToParams) -> None:
    """Modo CARA-A-CARA (V6.8-E): apoya la cara PLANA de la pieza contra la cara
    PLANA del target — normales anti-paralelas a `gap` mm, centros de cara alineados
    + `deslizar` {u,v} en el plano del target. Colocación CERRADA (sin solver) con
    rotación MÍNIMA: la orientación de la pieza se conserva todo lo posible (el
    listón sobre el larguero inclinado se inclina con él, no gira alrededor de la
    normal). Relacional: se reevalúa al regenerar como el modo bbox."""
    import math

    feat = _require(scene, p.feature)
    target = _require(scene, p.target)
    _f, oA, nA, _uA, _vA = _planar_face_frame(
        feat, p.cara.model_dump(exclude_none=True), quien="cara de la pieza"
    )
    _f, oB, nB, uB, vB = _planar_face_frame(
        target, p.cara_target.model_dump(exclude_none=True), quien="cara del target"
    )
    d = (-nB[0], -nB[1], -nB[2])  # la normal de la pieza debe terminar mirando al target
    dot = max(-1.0, min(1.0, _v_dot(nA, d)))
    center = _bbox_center(feat.shape)
    if dot > 1.0 - 1e-12:
        axis, angle = (0.0, 0.0, 1.0), 0.0
    elif dot < -1.0 + 1e-12:
        axis, angle = uB, 180.0  # anti-paralelas: media vuelta sobre un eje del plano
    else:
        axis = _v_unit(_v_cross(nA, d))
        angle = math.degrees(math.acos(dot))
    if angle:  # centro de la cara A tras la rotación (sobre el centro del bbox)
        from apolo.kernel.matrix import rotation_axis_angle_about

        m = rotation_axis_angle_about(center, axis, angle)
        oA = tuple(
            m[i][0] * oA[0] + m[i][1] * oA[1] + m[i][2] * oA[2] + m[i][3] for i in range(3)
        )
    du, dv = p.deslizar.u, p.deslizar.v
    destino = tuple(oB[i] + nB[i] * p.gap + uB[i] * du + vB[i] * dv for i in range(3))
    _world_place(feat, _v_sub(destino, oA), axis, angle, center)


def _exec_snap_to(ctx: ExecContext, cmd_id: str, p: SnapToParams) -> None:
    """Pega `feature` contra el `lado` del bbox de `target` a `gap` mm, opcionalmente
    centrando en los ejes de `alinear`. Relacional: se reevalúa al regenerar (mueve en
    sitio con la MISMA rígida que center_in/attach → conserva matrix/anclas).
    Con `cara`+`cara_target` despacha al modo cara-a-cara (V6.8-E)."""
    if p.feature == p.target:
        raise CommandError("Un sólido no puede colocarse junto a sí mismo")
    if p.cara is not None:  # ambos-o-ninguno lo garantiza el modelo
        return _exec_snap_face(ctx.scene, p)
    feat = _require(ctx.scene, p.feature)
    target = _require(ctx.scene, p.target)
    fb = feat.shape.bounding_box()
    tb = target.shape.bounding_box()
    fmin = [fb.min.X, fb.min.Y, fb.min.Z]
    fmax = [fb.max.X, fb.max.Y, fb.max.Z]
    tmin = [tb.min.X, tb.min.Y, tb.min.Z]
    tmax = [tb.max.X, tb.max.Y, tb.max.Z]
    sign, axis = p.lado[0], p.lado[1]
    i = {"x": 0, "y": 1, "z": 2}[axis]
    t = [0.0, 0.0, 0.0]
    if sign == "+":  # pieza en el lado +eje: su cara min queda a gap del max del target
        t[i] = (tmax[i] + p.gap) - fmin[i]
    else:            # pieza en el lado -eje: su cara max queda a gap del min del target
        t[i] = (tmin[i] - p.gap) - fmax[i]
    fc = _bbox_center(feat.shape)
    tc = _bbox_center(target.shape)
    for ax in p.alinear:
        j = {"x": 0, "y": 1, "z": 2}[ax]
        if j != i:  # no tocar el eje del snap
            t[j] = tc[j] - fc[j]
    _world_move(feat, tuple(t), (0, 0, 0))
