"""Executor de `create_hoist_chain` («Cadena de izaje», plan `docs/plans/cadena-de-izaje.md`): la
cadena ABIERTA con sus dos extremos amarrados a una pieza, que pasa por uno o más piñones ya
colocados. Params en `models_izaje.py`; matemática en `apolo/library/izaje.py`; geometría en
`apolo/library/izaje_geom.py`; la pose, en `apolo/robotics/pose_izaje.py`.

MARCO DEL PLANO (el de la cadena y el de su `Feature.matrix`): origen en el ancla `hilera_1` del
PRIMER piñón, Z = su eje, X = hacia el centro del segundo piñón (o hacia A si hay uno solo), Y =
Z × X. Las dos cadenas de un elevador, una a cada lado, dan los mismos números y comparten la
geometría (`mesh_key` = `izaje_geom.clave`).

Piezas (`{id}`, `{id}_ancla_a|b`, `{id}_tuerca_a1|a2|b1|b2`) y uniones/juntas con nombres fijos:
la FK encuentra las anclas de una cadena por su unión `{id}_pasador_a|b`. La huella D11 sólo ve
`_exec_create_hoist_chain`: cambiar la geometría de `izaje*.py` con los mismos params es subir la
`version` a mano.
"""

from __future__ import annotations

import math

from .errors import CommandError
from .exec_transmision import TOL_COPLANAR_MM, TOL_PARALELO_DEG, _compatible, _dot, _pinon, _sub, _unit
from .models_izaje import CreateHoistChainParams
from .state import ExecContext

#: Lo que se busca la placa de amarre por el eje de la varilla (mm desde el pasador).
ALCANCE_VARILLA_MM = 400.0
#: Hueco mínimo (mm) entre el yugo del ancla y la placa: el mínimo de tensado.
HUECO_MIN_MM = 1.0


def _mundo(m, p2, z: float = 0.0) -> list[float]:
    return [m[i][0] * p2[0] + m[i][1] * p2[1] + m[i][2] * z + m[i][3] for i in range(3)]


def _dir_mundo(m, u2) -> list[float]:
    return [m[i][0] * u2[0] + m[i][1] * u2[1] for i in range(3)]


def _cortes_por_rayo(shape, origen, direccion) -> list[float]:
    """Distancias (mm, ordenadas) donde el rayo origen + t·dirección (t ≥ 0) cruza las caras."""
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector

    inter = IntCurvesFace_ShapeIntersector()
    inter.Load(shape.wrapped, 1e-6)
    inter.Perform(gp_Lin(gp_Pnt(*origen), gp_Dir(*direccion)), 0.0, ALCANCE_VARILLA_MM)
    return sorted(inter.WParameter(i) for i in range(1, inter.NbPnt() + 1))


def _varilla(rotura_kn: float) -> str:
    """La menor métrica cuyo límite elástico 8.8 (ISO 898-1: Rp0.2 = 640 MPa) × As ≥ la rotura."""
    from apolo.library.engineering.bolts import GRADES, TENSILE_AREA_MM2

    for m in ("M6", "M8", "M10", "M12", "M16", "M20"):
        if TENSILE_AREA_MM2[m] * GRADES["8.8"][1] >= rotura_kn * 1000.0:
            return m
    raise CommandError(f"Ninguna varilla hasta M20 aguanta la rotura de {rotura_kn:g} kN")


def medir(ctx: ExecContext, p: CreateHoistChainParams):
    """Valida el montaje y arma (marco, piñones del plano, A, B, sentido)."""
    from apolo.kernel.matrix import frame
    from apolo.library.catalog import CATALOG
    from apolo.library.izaje import Pinon, sentido_mas_corto
    from apolo.library.transmision import diametro_primitivo

    if len(set(p.pinones)) != len(p.pinones):
        raise CommandError("La cadena de izaje pasa una sola vez por cada piñón: hay ids repetidos en pinones")
    cadena = CATALOG[p.cadena]
    feats = []
    for k, fid in enumerate(p.pinones):
        f, c = _pinon(ctx.scene, fid, f"pinones[{k}]")
        _compatible(cadena, c, fid)
        feats.append((fid, f, c))
    o = list(feats[0][1].anchors["hilera_1"]["origin"])
    z = _unit(feats[0][1].anchors["eje"]["axis"])
    for fid, f, _c in feats[1:]:
        ang = math.degrees(math.acos(min(1.0, abs(_dot(z, _unit(f.anchors["eje"]["axis"]))))))
        if ang > TOL_PARALELO_DEG:
            raise CommandError(f"El eje de '{fid}' no es paralelo al de '{p.pinones[0]}' ({ang:.2f}°): dales el mismo giro.")
        dz = _dot(_sub(f.anchors["hilera_1"]["origin"], o), z)
        if abs(dz) > TOL_COPLANAR_MM:
            raise CommandError(f"La hilera de '{fid}' queda a {dz:+.2f} mm del plano de la de '{p.pinones[0]}': muévelo por su eje.")
    extremos = {"extremo_a": list(p.extremo_a.tuple()), "extremo_b": list(p.extremo_b.tuple())}
    for campo, w in extremos.items():
        dz = _dot(_sub(w, o), z)
        if abs(dz) > TOL_COPLANAR_MM:
            bien = [w[i] - dz * z[i] for i in range(3)]
            raise CommandError(
                f"{campo} queda a {dz:+.2f} mm del plano de la hilera de los piñones: ponlo en "
                f"({bien[0]:.2f}, {bien[1]:.2f}, {bien[2]:.2f}).")
    hacia = (feats[1][1].anchors["eje"]["origin"] if len(feats) > 1 else extremos["extremo_a"])
    x = _sub(hacia, o)
    x = _unit(_sub(x, [z[i] * _dot(x, z) for i in range(3)]))
    y = [z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0]]
    marco = frame(tuple(o), x, y, z)

    def plano(w) -> tuple:
        v = _sub(w, o)
        return (round(_dot(v, x), 4), round(_dot(v, y), 4))

    paso = float(cadena.specs["paso"])
    pins = tuple(Pinon(*plano(f.anchors["eje"]["origin"]), round(diametro_primitivo(paso, int(c.specs["z"])) / 2.0, 4),
                       int(c.specs["z"])) for _fid, f, c in feats)
    a, b = plano(extremos["extremo_a"]), plano(extremos["extremo_b"])
    try:
        sigma = {"antihorario": 1, "horario": -1}.get(p.sentido) or sentido_mas_corto(a, list(pins), b)
    except ValueError as exc:
        raise CommandError(f"Cadena de izaje: {exc}") from exc
    return marco, feats, pins, a, b, sigma


def _fasear(ctx: ExecContext, feats, pins, c, marco) -> None:
    """`fase: auto`: gira cada piñón libre lo justo para que un asiento caiga en su rodillo."""
    from .exec_colocacion import _world_place
    from .exec_transmision import _lleva_cadena

    x, y, z = ([marco[i][k] for i in range(3)] for k in range(3))
    for (fid, f, _c), pin, idx in zip(feats, pins, c.asentados):
        if not idx or _lleva_cadena(ctx, fid):
            continue
        q = c.puntos[idx[0]]
        theta = math.atan2(q[1] - pin.cy, q[0] - pin.cx)
        v = _sub(f.anchors["fase"]["origin"], f.anchors["eje"]["origin"])
        diente = 2.0 * math.pi / pin.z
        giro = math.fmod(theta - math.atan2(_dot(v, y), _dot(v, x)), diente)
        giro = giro - diente if giro > diente / 2 else giro + diente if giro <= -diente / 2 else giro
        if abs(giro) < 1e-7:
            continue
        eje = f.anchors["eje"]
        signo = 1.0 if _dot(_unit(eje["axis"]), z) >= 0 else -1.0
        _world_place(f, (0.0, 0.0, 0.0), tuple(_unit(eje["axis"])), signo * math.degrees(giro), tuple(eje["origin"]))


def _exec_create_hoist_chain(ctx: ExecContext, cmd_id: str, p: CreateHoistChainParams) -> None:
    """Mide, arma la cadena desde el pasador A hacia B, la coloca con la matriz del plano y, en
    cada extremo, el ancla (horquilla + varilla) con su tuerca y contratuerca, el taladro de la
    pieza de amarre, las uniones y las juntas `fija` que la FK sigue."""
    from apolo.assembly.connectivity import ConnectivityError, register_fastener
    from apolo.kernel.shapes import place_matrix
    from apolo.library import izaje_geom as geo
    from apolo.library.catalog import CATALOG
    from apolo.library.engineering.bolts import clearance_hole_mm, hex_nut_mm, nominal_diameter_mm
    from apolo.library.engineering.threads import COARSE
    from apolo.library.izaje import rodillos

    from .escena import DEFINITIONS, Feature, _require, register_definition
    from .exec_ensamblaje import _register_joint
    from .exec_modificar import _drill_tool

    specs = CATALOG[p.cadena].specs
    marco, feats, pins, a, b, sigma = medir(ctx, p)
    try:
        c = rodillos(a, list(pins), b, sigma, float(specs["paso"]), p.eslabones)
    except ValueError as exc:
        raise CommandError(f"Cadena de izaje: {exc}") from exc
    size = _varilla(float(specs["rotura_kN"]))
    d = nominal_diameter_mm(size)
    af, m = hex_nut_mm(size)
    cotas = geo.cotas_ancla(specs, d)
    zm = geo.z_medio(specs)
    piezas = {"a": p.pieza_a, "b": p.pieza_b or p.pieza_a}
    # 1) todo lo que puede fallar, ANTES de tocar la escena (una carga tolerante suprime el comando
    # entero: no puede quedar media cadena)
    amarres = []
    for lado, q, vecino in (("a", c.puntos[0], c.puntos[1]), ("b", c.puntos[-1], c.puntos[-2])):
        u = ((vecino[0] - q[0]) / math.dist(q, vecino), (vecino[1] - q[1]) / math.dist(q, vecino))
        pw, uw = _mundo(marco, q, zm), _dir_mundo(marco, u)
        cortes = _cortes_por_rayo(_require(ctx.scene, piezas[lado]).shape, pw, [-v for v in uw])
        if len(cortes) < 2:
            raise CommandError(
                f"La varilla del amarre {lado.upper()} (del pasador alejándose de la cadena por el ramal) no "
                f"atraviesa material de '{piezas[lado]}' en {ALCANCE_VARILLA_MM:g} mm: pon la placa de amarre en "
                "ese eje (si ya tiene un agujero ahí, quítalo: el comando la taladra a la medida de la varilla).")
        s0, s1 = cortes[0], cortes[1]
        hueco = s0 - cotas.cuerpo
        if hueco < HUECO_MIN_MM:
            raise CommandError(
                f"El pasador {lado.upper()} está a {s0:.1f} mm de '{piezas[lado]}' y el ancla necesita "
                f"{cotas.cuerpo + HUECO_MIN_MM:.1f} mm (mejillas + yugo + {HUECO_MIN_MM:g} de tensado): aléjalo "
                f"{cotas.cuerpo + HUECO_MIN_MM - s0:.1f} mm de la placa.")
        rosca = COARSE.get(size, (0.125 * d, 0.0))[0]
        largo = 5.0 * math.ceil((s1 - cotas.cuerpo + 2.0 * m + 2.0 * rosca) / 5.0)
        amarres.append((lado, q, u, pw, uw, s0, s1, hueco, largo))
    clave = geo.clave(geo.DatosIzaje(p.cadena, c.pasos, sigma, a, b, pins))
    base = DEFINITIONS.get(clave)
    try:
        base = base if base is not None else geo.cadena_de(specs, c)
        anclas = {lado: geo.ancla(specs, q, u, cotas, largo) for lado, q, u, *_r, largo in amarres}
    except (ValueError, RuntimeError) as exc:
        raise CommandError(f"Cadena de izaje: {exc}") from exc
    # 2) recién ahora se muta: piñones en fase, cadena, anclas, taladros, juntas y uniones
    if p.fase == "auto":
        _fasear(ctx, feats, pins, c, marco)
    register_definition(clave, base)
    ctx.scene[cmd_id] = Feature(cmd_id, p.name, place_matrix(base, marco), cmd_id, component=p.cadena,
                                cut_length=round(c.pasos * float(specs["paso"]), 3), mesh_key=clave,
                                matrix=[list(fila) for fila in marco])
    uniones = [(f"{cmd_id}_p{k + 1}", cmd_id, fid, "contacto", None, f"{p.name}: la cadena apoya en su piñón")
               for k, fid in enumerate(p.pinones)]
    for lado, q, u, pw, uw, s0, s1, hueco, largo in amarres:
        pieza = ctx.scene[piezas[lado]]
        entrada = [pw[i] - uw[i] * (s0 - 1.0) for i in range(3)]
        pieza.shape = pieza.shape - _drill_tool(clearance_hole_mm(size), s1 - s0 + 2.0, tuple(entrada),
                                                tuple(-v for v in uw))
        pieza.make_unique()
        fa = f"{cmd_id}_ancla_{lado}"
        ctx.scene[fa] = Feature(fa, f"{p.name} · Amarre {lado.upper()} (horquilla {size}×{largo:g}, ajuste "
                                f"{hueco:.0f} mm)", place_matrix(anclas[lado], marco),
                                cmd_id, material="acero")
        juntas = [fa]
        for k, s in ((1, s1 + m / 2.0), (2, s1 + 1.5 * m)):
            ft = f"{cmd_id}_tuerca_{lado}{k}"
            ctx.scene[ft] = Feature(ft, f"Tuerca {size} DIN 934" + (" (contratuerca)" if k == 2 else ""),
                                    place_matrix(geo.tuerca(q, u, s, zm, d, af, m), marco), cmd_id,
                                    component=f"TUERCA-{size}")
            juntas.append(ft)
        for fid in juntas:
            _register_joint(ctx.scene, ctx.joints, cmd_id, {
                "name": f"{cmd_id}_jf_{fid[len(cmd_id) + 1:]}", "type": "fija", "parent": piezas[lado],
                "child": fid, "origin": [0.0, 0.0, 0.0], "axis": [0.0, 0.0, 1.0], "lower": 0.0, "upper": 0.0})
        uniones += [
            (f"{cmd_id}_pasador_{lado}", cmd_id, fa, "perno", None,
             f"{p.name}: pasador del eslabón de unión con clip (perno de la cadena) en la horquilla"),
            (f"{cmd_id}_amarre_{lado}", fa, piezas[lado], "perno", size,
             f"{p.name}: varilla {size} del ancla con tuerca y contratuerca DIN 934 (ajuste de tensado {hueco:.1f} mm)"),
        ]
    for nombre, fa_, fb_, kind, sz, nota in uniones:
        spec = {"name": nombre, "a": fa_, "b": fb_, "kind": kind, "nota": nota}
        if sz:
            spec.update(size=sz, qty=1)
        try:
            register_fastener(ctx.fasteners, cmd_id, spec)
        except ConnectivityError as exc:
            raise CommandError(str(exc)) from exc
