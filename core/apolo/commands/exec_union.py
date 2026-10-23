"""Executor de `join_bolted` (salió de `registry.py`, congelado por el trinquete de tamaño, al
ganar el criterio de taller: plan `union-en-perfil-hueco`).

Dos criterios por el campo oculto `criterio` (`models_union.py`):

- **1** (V6.5b/c, el de todo log viejo): contacto y patrón por las cajas, largo = caja entera
  + tuerca + 3 filetes, cabeza en la cara alta de la caja. Se conserva TAL CUAL: un log viejo
  regenera con la misma tornillería y su firma no cambia (por eso la `version` sigue en 1).
- **2** (taller, D1–D4), en `union_taller.py`: el de los logs del 2026-10-21 al 22.
- **3** (taller + largo de catálogo, plan puerta-de-publicacion D3): igual que el 2, salvo que
  un agarre al que no le alcanza ningún largo de catálogo es un error accionable en vez del
  respaldo silencioso a 200 mm; la geometría del 2 no cambia (sin `version`).
- **4** (F6 de la puerta): el 3 con el ala de un perfil ABIERTO (UPN, IPE, L) con acceso por
  detrás → perno + tuerca, no remache ciego. Los 2 y 3 guardados regeneran igual (sin
  `version`: el criterio viaja en los params).
- **5** (el de todo comando nuevo, F6 de la puerta): el 4 que mide la distancia al canto de cada
  agujero en la geometría real (EN 1993-1-8, e ≥ 1,2·d0) y rechaza el que queda bajo el mínimo
  (`union_taller._exigir_bordes`). No cambia la geometría: sólo rechaza.

`sellar` es el sello de entrada (`CommandSpec.al_crear`): un comando NUEVO nace con el criterio
vigente y con las piezas que eran de madera al crearlo.
"""

from __future__ import annotations

from collections.abc import Callable

from .errors import CommandError
from .models_union import JoinBoltedParams
from .state import ExecContext

CRITERIO_VIGENTE = 5
_AXNAME = {0: "X", 1: "Y", 2: "Z"}


def sellar(params: dict, material_de: Callable[[str], str | None]) -> dict:
    """Sello de entrada de un join_bolted NUEVO: el criterio vigente y las piezas de madera
    (lo que `set_material` o el vertical dicen HOY: el regenerate no ve el manifest). Lo que
    el cliente ya trae se respeta (un test puede pedir el criterio 1)."""
    from apolo.library.materials import es_madera

    if "criterio" not in params:
        params["criterio"] = CRITERIO_VIGENTE
    if "madera" not in params:
        ids = [params.get("a"), params.get("b")]
        params["madera"] = [i for i in ids if isinstance(i, str) and es_madera(material_de(i))]
    return params


def huella(a_shape, b_shape, size_txt: str) -> dict:
    """Contacto por solape de cajas: eje de apilado (menor solape), huella en el plano y datos
    de la métrica. CommandError accionable si no hay huella o están separadas."""
    from apolo.library.engineering.bolts import (
        clearance_hole_mm, hex_head_mm, nominal_diameter_mm,
    )

    size = size_txt.strip().upper()
    try:
        d = nominal_diameter_mm(size)
        clear = clearance_hole_mm(size)
        af, head_h = hex_head_mm(size)
    except KeyError as exc:
        raise CommandError(str(exc)) from exc
    ab, bb = a_shape.bounding_box(), b_shape.bounding_box()
    amin, amax = [ab.min.X, ab.min.Y, ab.min.Z], [ab.max.X, ab.max.Y, ab.max.Z]
    bmin, bmax = [bb.min.X, bb.min.Y, bb.min.Z], [bb.max.X, bb.max.Y, bb.max.Z]
    overlap = [min(amax[k], bmax[k]) - max(amin[k], bmin[k]) for k in range(3)]
    stack = min(range(3), key=lambda k: overlap[k])  # eje de menor solape = normal de contacto
    inplane = [k for k in range(3) if k != stack]
    if overlap[inplane[0]] <= 1e-6 or overlap[inplane[1]] <= 1e-6:
        raise CommandError(
            "Las piezas no comparten una huella de contacto (sus cajas no se solapan en el plano): "
            "colócalas cara a cara (snap_to/attach) o únelas con add_mate."
        )
    gap = -overlap[stack]
    if gap > 0.5:
        raise CommandError(
            f"Las piezas están separadas {gap:.1f} mm en el eje {_AXNAME[stack]}: acércalas hasta el "
            "contacto (snap_to gap=0) o usa add_mate coincidente — join_bolted requiere caras en contacto."
        )
    return {
        "size": size, "d": d, "clear": clear, "af": af, "head_h": head_h,
        "amin": amin, "amax": amax, "bmin": bmin, "bmax": bmax, "overlap": overlap,
        "stack": stack, "inplane": inplane,
        "foot_min": [max(amin[k], bmin[k]) for k in range(3)],
        "foot_max": [min(amax[k], bmax[k]) for k in range(3)],
    }


def area_plana_en(shape, stack: int, coord: float, tol: float = 0.6) -> float:
    """Suma el área de caras PLANAS ⊥ al eje `stack` en el plano `coord`."""
    from build123d import GeomType

    total = 0.0
    for face in shape.faces():
        try:
            if face.geom_type != GeomType.PLANE:
                continue
            c = face.center()
            if abs((c.X, c.Y, c.Z)[stack] - coord) > tol:
                continue
            n = face.normal_at(c)
            if abs((n.X, n.Y, n.Z)[stack]) < 0.99:
                continue
            total += float(face.area)
        except Exception:
            continue
    return total


def exigir_asiento(shape, h: dict, coord: float, que: str) -> None:
    """V6.5c (Fix 2): cara PLANA ⊥ al eje en `coord` con ≥ 50 % de la huella, o error que pide
    mates (pieza rotada, curva o no prismática en el eje de apilado)."""
    stack, inplane = h["stack"], h["inplane"]
    foot_area = h["overlap"][inplane[0]] * h["overlap"][inplane[1]]
    if area_plana_en(shape, stack, coord) < 0.5 * foot_area:
        raise CommandError(
            f"join_bolted une PLACAS/perfiles cara a cara: falta cara PLANA ⊥ al eje "
            f"{_AXNAME[stack]} en el plano de {que} (pieza rotada, curva o no prismática "
            "en el eje de apilado). Usa add_mate coincidente + drill_hole/fasten manual."
        )


def patron(h: dict, p: JoinBoltedParams) -> tuple[int, int, list[float], list[float]]:
    """(u, v, us, vs): el patrón centrado en la huella con borde ≥1.5·d y paso ≥2.5·d."""
    foot_min, foot_max, size, tol = h["foot_min"], h["foot_max"], h["size"], 1e-6
    if p.patron:
        nu, nv = int(p.patron[0]), int(p.patron[1])
    else:
        nu, nv = max(1, int(p.count)), 1
    # u = eje in-plane más largo (la fila corre por ahí); v = el corto
    u, v = sorted(h["inplane"], key=lambda k: foot_max[k] - foot_min[k], reverse=True)
    edge, min_pitch = 1.5 * h["d"], 2.5 * h["d"]

    def positions(ax: int, n: int) -> list[float]:
        lo, hi = foot_min[ax] + edge, foot_max[ax] - edge
        center = (foot_min[ax] + foot_max[ax]) / 2.0
        ancho = foot_max[ax] - foot_min[ax]
        if hi < lo - tol:  # V6.5c (4a): también con n=1 debe caber el borde ≥1.5·d
            raise CommandError(
                f"La huella de solape ({ancho:.0f} mm en {_AXNAME[ax]}) no "
                f"admite ni un perno {size} con distancia al borde ≥{edge:g} mm: usa un perno menor."
            )
        if n <= 1:
            return [center]
        if p.spacing:
            pts = [center + p.spacing * (i - (n - 1) / 2.0) for i in range(n)]
            if min(pts) < lo - tol or max(pts) > hi + tol:
                raise CommandError(
                    f"El patrón {nu}×{nv} con paso {p.spacing:g} mm no cabe en la huella "
                    f"({ancho:.0f} mm en {_AXNAME[ax]}) respetando el borde ≥{edge:g} mm."
                )
            return pts
        if hi - lo < (n - 1) * min_pitch - tol:  # no cabe el borde + el paso mínimo
            raise CommandError(
                f"La huella de solape ({ancho:.0f} mm en {_AXNAME[ax]}) es muy pequeña "
                f"para {n} pernos {size} con distancia al borde ≥{edge:g} mm y paso ≥{min_pitch:g} mm: "
                "reduce count/patrón o el perno."
            )
        return [lo + (hi - lo) * i / (n - 1) for i in range(n)]

    return u, v, positions(u, nu), positions(v, nv)


def rotacion_hacia(stack: int, signo: float) -> tuple[float, float, float]:
    """Rotación que lleva el +Z local de la tornillería al eje `stack` con `signo`."""
    if signo >= 0:
        return {0: (0.0, 90.0, 0.0), 1: (-90.0, 0.0, 0.0), 2: (0.0, 0.0, 0.0)}[stack]
    return {0: (0.0, -90.0, 0.0), 1: (90.0, 0.0, 0.0), 2: (180.0, 0.0, 0.0)}[stack]


def _criterio_1(ctx: ExecContext, cmd_id: str, p: JoinBoltedParams, a, b) -> None:
    """V6.5b/c tal cual: largo = caja entera + tuerca 0.8·d + 3 filetes, cabeza en la cara
    alta de la caja (o_max), tuerca en la baja (o_min)."""
    from build123d import Pos, Rotation

    from apolo.assembly.connectivity import ConnectivityError, register_fastener
    from apolo.library.builders import hex_bolt, hex_nut
    from apolo.library.catalog import CATALOG
    from apolo.library.engineering.bolts import commercial_length, hex_nut_mm
    from apolo.library.engineering.threads import COARSE

    from .registry import Feature, _drill_tool

    h = huella(a.shape, b.shape, p.size)
    stack, size, d = h["stack"], h["size"], h["d"]
    o_min = min(h["amin"][stack], h["bmin"][stack])
    o_max = max(h["amax"][stack], h["bmax"][stack])
    grip = o_max - o_min
    a_below = (h["amin"][stack] + h["amax"][stack]) <= (h["bmin"][stack] + h["bmax"][stack])
    exigir_asiento(a.shape, h, h["amax"][stack] if a_below else h["amin"][stack], "contacto")
    exigir_asiento(b.shape, h, h["bmin"][stack] if a_below else h["bmax"][stack], "contacto")
    exigir_asiento(b.shape if a_below else a.shape, h, o_max, "asiento exterior")
    exigir_asiento(a.shape if a_below else b.shape, h, o_min, "asiento exterior")
    u, v, us, vs = patron(h, p)
    paso = COARSE.get(size, (0.125 * d, 0.0))[0]
    bolt_len = commercial_length(grip + 0.8 * d + 3.0 * paso)  # V6.5c (Fix 3)
    ref, nut_ref = f"PERNO-HEX-{size}", f"TUERCA-{size}"
    if ref not in CATALOG:
        raise CommandError(f"Perno {size} sin referencia de catálogo '{ref}': tamaños M6–M24 (DIN 933).")
    try:
        nut_af, nut_m = hex_nut_mm(size)
    except KeyError as exc:
        raise CommandError(str(exc)) from exc
    outward = [0.0, 0.0, 0.0]
    outward[stack] = 1.0
    rot = rotacion_hacia(stack, 1.0)
    bolt_base = hex_bolt(d, h["af"], h["head_h"])(bolt_len)
    nut_base = hex_nut(d, nut_af, nut_m)()
    margin, n_bolt = 5.0, 0
    for pu in us:
        for pv in vs:
            pt = [0.0, 0.0, 0.0]
            pt[u], pt[v] = pu, pv
            entry = list(pt)
            entry[stack] = o_min - margin
            tool = _drill_tool(h["clear"], grip + 2 * margin, tuple(entry), tuple(outward))
            a.shape = a.shape - tool
            b.shape = b.shape - tool
            origin = list(pt)
            origin[stack] = o_max
            n_bolt += 1
            ctx.scene[f"{cmd_id}_perno{n_bolt}"] = Feature(
                f"{cmd_id}_perno{n_bolt}", f"Perno {size}×{bolt_len:g} {p.norma}",
                Pos(*origin) * Rotation(*rot) * bolt_base, cmd_id, component=ref,
            )
            n_origin = list(pt)
            n_origin[stack] = o_min - nut_m / 2.0
            ctx.scene[f"{cmd_id}_tuerca{n_bolt}"] = Feature(
                f"{cmd_id}_tuerca{n_bolt}", f"Tuerca {size} DIN 934",
                Pos(*n_origin) * Rotation(*rot) * nut_base, cmd_id, component=nut_ref,
            )
    terminar(ctx, cmd_id, p, a, b, {"kind": "perno", "size": size, "qty": n_bolt, "nota": p.name},
             ConnectivityError, register_fastener)


def terminar(ctx, cmd_id, p, a, b, fijador: dict, error_cls, registrar) -> None:
    """Piezas taladradas (ya no son la geometría canónica) + el fijador `jb_{cmd_id}`."""
    a.make_unique()
    b.make_unique()
    for feat in (a, b):
        if getattr(feat.shape, "volume", 1.0) <= 0:
            raise CommandError("Los taladros vaciaron una pieza: revisa la métrica y el patrón")
    try:
        registrar(ctx.fasteners, cmd_id, {"name": f"jb_{cmd_id}", "a": p.a, "b": p.b, **fijador})
    except error_cls as exc:
        raise CommandError(str(exc)) from exc


def _exec_join_bolted(ctx: ExecContext, cmd_id: str, p: JoinBoltedParams) -> None:
    """Super-comando de unión atornillada (V6.5b): taladra A y B EN SITIO (conserva ids),
    inserta la fijación de catálogo y declara el fijador. Criterio 1 = el de los logs viejos;
    2 = el de taller (plan union-en-perfil-hueco)."""
    from .registry import _require

    if p.a == p.b:
        raise CommandError("join_bolted une dos piezas distintas (a ≠ b)")
    a, b = _require(ctx.scene, p.a), _require(ctx.scene, p.b)
    if p.criterio == 1:
        _criterio_1(ctx, cmd_id, p, a, b)
        return
    from .union_taller import criterio_taller

    criterio_taller(ctx, cmd_id, p, a, b)
