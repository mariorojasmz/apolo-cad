"""Motion study: interpolación de fotogramas clave y escaneo de colisiones a lo
largo del recorrido. Reutiliza el FK (posed_shapes) y el reporte de
interferencias, igual que la comprobación de colisión en pose.

Un keyframe es {"t": segundos, "values": {nombre_junta: valor}}.
"""

from __future__ import annotations


def duration(keyframes: list[dict]) -> float:
    return max((float(k["t"]) for k in keyframes), default=0.0)


def values_at(keyframes: list[dict], t: float) -> dict[str, float]:
    """Valores de junta interpolados linealmente en el instante t."""
    if not keyframes:
        return {}
    kfs = sorted(keyframes, key=lambda k: float(k["t"]))
    if t <= float(kfs[0]["t"]):
        return dict(kfs[0].get("values", {}))
    if t >= float(kfs[-1]["t"]):
        return dict(kfs[-1].get("values", {}))
    for lo, hi in zip(kfs, kfs[1:]):
        t0, t1 = float(lo["t"]), float(hi["t"])
        if t0 <= t <= t1:
            span = t1 - t0
            f = 0.0 if span <= 1e-9 else (t - t0) / span
            v0, v1 = lo.get("values", {}), hi.get("values", {})
            out: dict[str, float] = {}
            for name in set(v0) | set(v1):
                a = float(v0.get(name, v1.get(name, 0.0)))
                b = float(v1.get(name, v0.get(name, 0.0)))
                out[name] = a + (b - a) * f
            return out
    return dict(kfs[-1].get("values", {}))


def scan_collisions(doc, keyframes: list[dict], steps: int = 24) -> list[dict]:
    """Muestrea el recorrido en `steps` instantes y reporta los que colisionan.
    Devuelve [{t, interferencias:[{a,b,nombre_a,nombre_b,volumen_mm3}]}]."""
    from apolo.library.checks import (
        hardware_ids,
        interference_report,
        interpenetration_report,
        joint_pairs,
        same_command_pairs,
    )
    from apolo.robotics.pose import posed_shapes

    dur = duration(keyframes)
    if dur <= 0 or not keyframes:
        return []
    steps = max(2, min(int(steps), 200))
    jpairs = joint_pairs(doc)
    pairs = jpairs | same_command_pairs(doc)
    hw = hardware_ids(doc)
    solve = None
    if getattr(doc, "constraints", None):
        from apolo.assembly.constraints import solve_constraints

        solve = solve_constraints
    out: list[dict] = []
    for i in range(steps + 1):
        t = dur * i / steps
        vals = values_at(keyframes, t)
        if solve is not None:
            vals = solve(doc.joints, doc.constraints, vals)
        override = None
        if any(v != 0 for v in vals.values()):
            override, _ = posed_shapes(doc, vals)
        report = interference_report(
            doc.scene, shapes_override=override, exclude_pairs=pairs, exclude_ids=hw
        )
        inter = report["interferencias"]
        if override is not None:  # interpenetración de cuerpos que comparten junta
            inter = inter + interpenetration_report(doc.scene, override, jpairs)
        if inter:
            out.append({"t": round(t, 3), "interferencias": inter})
    return out
