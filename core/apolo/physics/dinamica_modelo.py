"""Snapshot PURO de la máquina dinámica → MJCF (V8.2 D1/D2/D6).

Todo aquí es dato horneado: cascos (vértices), cápsulas, inercias, juntas y actuadores,
ya en metros. `prepare_dynamics` lo llena bajo `STATE_LOCK` y `to_mjcf` lo vuelve XML sin
tocar OCCT.

Colisión por grupos (contype/conaffinity) — un bit por papel:
- ESTÁTICO (bastidor, piso) y MÁQUINA (cuerpos de junta) sólo chocan con PRODUCTO por
  defecto: un rodillo montado no frota el larguero que lo sostiene aunque su geometría se
  solape (V8.0: las AABB de `create_conveyor` se solapan), y dos piezas que engranan no se
  traban por sus cascos. Con `colisiones_maquina` chocan también entre sí, y entonces cada
  par padre–hijo de una junta lleva su `<exclude>` (la pieza padre estática va en un cuerpo
  propio, soldado al mundo, para poder nombrarla).
- BANDA: la superficie superior de una banda, `condim=1` + `priority=1` (sin fricción
  nativa: el arrastre lo pone `banda.py`), sólo choca con PRODUCTO.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

BIT_ESTATICO, BIT_MAQUINA, BIT_PRODUCTO, BIT_BANDA = 1, 2, 4, 8


def nombre_mj(prefijo: str, texto: str) -> str:
    return f"{prefijo}_{re.sub(r'[^A-Za-z0-9_]', '_', str(texto))}"


@dataclass
class GeomMJ:
    """Geometría de colisión. Coordenadas en METROS y en el MUNDO (pose de diseño); `to_mjcf`
    las pasa al marco del cuerpo."""
    tipo: str                         # mesh | capsule | cylinder | box
    nombre: str
    vertices: list | None = None      # mesh
    desde: tuple | None = None        # capsule/cylinder: extremos del eje
    hasta: tuple | None = None
    radio: float = 0.0
    pos: tuple | None = None          # box
    medio: tuple | None = None        # box: semilados
    xyaxes: tuple | None = None       # box: ejes x, y del marco de la caja
    extra: str = ""


@dataclass
class CuerpoMJ:
    nombre: str
    junta: str                        # nombre MJCF de la junta
    tipo: str                         # hinge | slide
    padre: str | None                 # cuerpo MJCF padre (None = mundo)
    origen: tuple                     # m, mundo (marco del cuerpo en t = 0, sin rotación)
    eje: tuple
    rango: tuple | None               # rad | m
    masa: float
    com: tuple                        # m, mundo
    inercia: tuple                    # kg·m²: ixx iyy izz ixy ixz iyz sobre el COM
    geoms: list = field(default_factory=list)
    amortiguamiento: float = 0.0
    friccion: float = 0.0
    armadura: float = 0.0


@dataclass
class EstaticoMJ:
    pieza: str
    geoms: list
    cuerpo: str | None = None         # cuerpo soldado propio (padre de una junta) o None


@dataclass
class ProductoMJ:
    nombre: str
    medio: tuple                      # m
    masa: float
    pos: tuple                        # m: donde nace el cuerpo (o su estacionamiento)
    friccion: float
    quat: tuple = (1.0, 0.0, 0.0, 0.0)  # w x y z


@dataclass
class ActuadorMJ:
    nombre: str
    junta: str                        # nombre MJCF
    tipo: str                         # velocity | motor
    kv: float = 0.0
    fuerza_max: float | None = None


@dataclass
class ModeloMJ:
    timestep: float
    gravedad: float
    estaticos: list = field(default_factory=list)
    cuerpos: list = field(default_factory=list)   # orden padre → hijo
    productos: list = field(default_factory=list)
    superficies: list = field(default_factory=list)  # GeomMJ de bandas
    actuadores: list = field(default_factory=list)
    excluir: list = field(default_factory=list)   # [(cuerpo1, cuerpo2)]
    colisiones_maquina: bool = False


def _v(xs, nd: int = 6) -> str:
    return " ".join(f"{float(x):.{nd}f}" for x in xs)


def _menos(a, b) -> tuple:
    return tuple(float(a[i]) - float(b[i]) for i in range(3))


def _grupos(papel: str, colisiones_maquina: bool) -> str:
    e, m, p, b = BIT_ESTATICO, BIT_MAQUINA, BIT_PRODUCTO, BIT_BANDA
    afin = {
        "estatico": p | (m if colisiones_maquina else 0),
        "maquina": p | ((e | m) if colisiones_maquina else 0),
        "producto": e | m | p | b,
        "banda": p,
    }[papel]
    tipo = {"estatico": e, "maquina": m, "producto": p, "banda": b}[papel]
    return f'contype="{tipo}" conaffinity="{afin}"'


def _geom_xml(g: GeomMJ, origen, papel: str, colisiones: bool, assets: list) -> str:
    grupos = _grupos(papel, colisiones)
    if g.tipo == "mesh":
        verts = [_menos(v, origen) for v in g.vertices]
        assets.append(f'<mesh name="{g.nombre}" vertex="{_v([c for v in verts for c in v], 5)}"/>')
        return f'<geom name="{g.nombre}" type="mesh" mesh="{g.nombre}" {grupos} {g.extra}/>'
    if g.tipo in ("capsule", "cylinder"):
        a, b = _menos(g.desde, origen), _menos(g.hasta, origen)
        return (f'<geom name="{g.nombre}" type="{g.tipo}" fromto="{_v(a + b)}" '
                f'size="{g.radio:.6f}" {grupos} {g.extra}/>')
    pos = _menos(g.pos, origen)
    ejes = f' xyaxes="{_v(g.xyaxes)}"' if g.xyaxes else ""
    return (f'<geom name="{g.nombre}" type="box" pos="{_v(pos)}" size="{_v(g.medio)}"{ejes} '
            f'{grupos} {g.extra}/>')


def to_mjcf(mod: ModeloMJ) -> str:
    """El XML de MuJoCo del modelo. Puro: sólo formatea datos."""
    col = mod.colisiones_maquina
    assets: list[str] = []
    mundo: list[str] = [f'<geom name="piso" type="plane" size="0 0 1" {_grupos("estatico", col)}/>']
    for est in mod.estaticos:
        geoms = "".join(_geom_xml(g, (0, 0, 0), "estatico", col, assets) for g in est.geoms)
        mundo.append(f'<body name="{est.cuerpo}">{geoms}</body>' if est.cuerpo else geoms)
    mundo.extend(_geom_xml(g, (0, 0, 0), "banda", col, assets) for g in mod.superficies)

    por_padre: dict = {}
    for c in mod.cuerpos:
        por_padre.setdefault(c.padre, []).append(c)

    def cuerpo_xml(c: CuerpoMJ, origen_padre) -> str:
        pos = _menos(c.origen, origen_padre)
        ixx, iyy, izz, ixy, ixz, iyz = c.inercia
        # tope duro: constante de tiempo mínima estable (≥ 2·Δt); la de MuJoCo (20 ms) pasa 3°
        rango = (f'limited="true" range="{c.rango[0]:.6f} {c.rango[1]:.6f}" '
                 f'solreflimit="{max(0.004, 3 * mod.timestep):.4g} 1"' if c.rango
                 else 'limited="false"')
        partes = [
            f'<body name="{c.nombre}" pos="{_v(pos)}">',
            f'<inertial pos="{_v(_menos(c.com, c.origen))}" mass="{max(c.masa, 1e-6):.6f}" '
            f'fullinertia="{ixx:.9g} {iyy:.9g} {izz:.9g} {ixy:.9g} {ixz:.9g} {iyz:.9g}"/>',
            f'<joint name="{c.junta}" type="{c.tipo}" axis="{_v(c.eje)}" {rango} '
            f'damping="{c.amortiguamiento:.6g}" frictionloss="{c.friccion:.6g}" '
            f'armature="{c.armadura:.6g}"/>',
        ]
        partes += [_geom_xml(g, c.origen, "maquina", col, assets) for g in c.geoms]
        partes += [cuerpo_xml(h, c.origen) for h in por_padre.get(c.nombre, [])]
        partes.append("</body>")
        return "".join(partes)

    mundo += [cuerpo_xml(c, (0, 0, 0)) for c in por_padre.get(None, [])]
    for p in mod.productos:
        mundo.append(
            f'<body name="{p.nombre}" pos="{_v(p.pos)}" quat="{_v(p.quat, 9)}"><freejoint/>'
            f'<geom name="g_{p.nombre}" type="box" size="{_v(p.medio)}" mass="{p.masa:.6f}" '
            f'friction="{p.friccion:.4f} 0.005 0.0001" {_grupos("producto", col)}/></body>'
        )
    actuadores = []
    for a in mod.actuadores:
        lim = (f'forcelimited="true" forcerange="{-a.fuerza_max:.6g} {a.fuerza_max:.6g}"'
               if a.fuerza_max else 'forcelimited="false"')
        if a.tipo == "velocity":
            actuadores.append(f'<velocity name="{a.nombre}" joint="{a.junta}" kv="{a.kv:.6g}" '
                              f'ctrllimited="false" {lim}/>')
        else:
            actuadores.append(f'<motor name="{a.nombre}" joint="{a.junta}" gear="1" '
                              f'ctrllimited="false" {lim}/>')
    excluir = "".join(f'<exclude body1="{a}" body2="{b}"/>' for a, b in mod.excluir)
    return (
        '<mujoco model="apolo_dinamica">'
        '<compiler angle="radian" balanceinertia="true" boundmass="1e-6" boundinertia="1e-9"/>'
        f'<option timestep="{mod.timestep:.6g}" integrator="implicitfast" '
        f'gravity="0 0 {-mod.gravedad:.6g}"><flag multiccd="enable"/></option>'
        '<default><geom friction="0.6 0.005 0.0001"/></default>'
        f'<asset>{"".join(assets)}</asset>'
        f'<worldbody>{"".join(mundo)}</worldbody>'
        f'{f"<contact>{excluir}</contact>" if excluir else ""}'
        f'{f"<actuator>{chr(10).join(actuadores)}</actuator>" if actuadores else ""}'
        '</mujoco>'
    )
