"""Qué es estático, qué se mueve y qué queda fuera en la simulación dinámica (V8.2 D2).

Dos partes:
- `clasificar` (pura, sobre los dicts del documento): las piezas sujetas a tierra son
  ESTÁTICAS (como en `gravity_test`, pero el grafo de sujeción NO cruza una junta móvil); cada
  junta móvil arma un CUERPO con su hijo más todo lo colgado de él por juntas `fija` (incluidas
  las `jf_*` de `arrastrar`); lo que no es ni una cosa ni la otra queda FUERA, con aviso.
- `geometria_movil` (OCCT, bajo `STATE_LOCK`): masa (peso de catálogo si lo hay; el vástago de
  un cilindro, la masa móvil de su ficha, `masas_de_ficha`; si no, `_link_physics`), centro de masas e inercia del sólido REAL (GProp de OCCT, escalado a esa
  masa) y la colisión: CÁPSULA para lo
  que gira sobre su eje (rodillos y tambores del catálogo primero; si no, un sólido con una
  cara cilíndrica coaxial a la junta) y casco convexo para el resto.

La inercia sale del sólido y no de la geometría de colisión: el casco de un tubo es un
cilindro macizo (la mitad de inercia) y la cápsula de un rodillo suma casquetes. Así la
colisión puede simplificarse sin cambiar la dinámica.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from apolo.physics.hull import cascos, hull_vertices
from apolo.robotics.model import _link_physics

MOVILES = ("giratoria", "continua", "prismatica")
GIRATORIAS = ("giratoria", "continua")
_CATEGORIAS_GIRATORIAS = ("rodillos", "tambores")


@dataclass
class Clasificacion:
    estaticas: set = field(default_factory=set)
    cuerpos: dict = field(default_factory=dict)     # junta → [piezas] (hijo primero)
    padre_cuerpo: dict = field(default_factory=dict)  # junta → junta padre | None (mundo)
    orden: list = field(default_factory=list)       # juntas en orden padre → hijo
    fuera: dict = field(default_factory=dict)       # pieza → motivo
    avisos: list = field(default_factory=list)


def clasificar(ids, joints: dict, fasteners: dict, grounds: dict, mates: dict | None = None,
               extra_edges=(), extra_grounds=(), quitar=()) -> Clasificacion:
    """Reparte las piezas `ids` entre estáticas, cuerpos móviles y fuera. `quitar` son las
    piezas que ya tienen otro rol (la banda: superficie, no cuerpo). Una junta con
    `parent=None` cuelga del mundo (las virtuales de `banda.detectar_bandas`)."""
    ids = set(ids) - set(quitar)
    out = Clasificacion()
    juntas = {n: j for n, j in joints.items()
              if (j["parent"] in ids or (j["parent"] is None and j["type"] in MOVILES))
              and j["child"] in ids}
    hijos_fija: dict[str, list[str]] = {}
    for j in juntas.values():
        if j["type"] == "fija":
            hijos_fija.setdefault(j["parent"], []).append(j["child"])

    def cierre(raiz: str) -> list[str]:
        vistos, pila = [], [raiz]
        while pila:
            n = pila.pop()
            if n in vistos:
                continue
            vistos.append(n)
            pila.extend(sorted(hijos_fija.get(n, ())))
        return vistos

    moviles = {n: j for n, j in juntas.items() if j["type"] in MOVILES}
    miembros = {n: cierre(j["child"]) for n, j in moviles.items()}
    pieza_cuerpo = {p: n for n, ps in miembros.items() for p in ps}

    # sujeción a tierra SIN cruzar lo que se mueve
    nodos = ids - set(pieza_cuerpo)
    ady: dict[str, set] = {n: set() for n in nodos}

    def unir(a, b):
        if a in nodos and b in nodos and a != b:
            ady[a].add(b)
            ady[b].add(a)

    for j in juntas.values():
        if j["type"] == "fija":
            unir(j["parent"], j["child"])
    for m in (mates or {}).values():
        unir(m.get("feature_a"), m.get("feature_b"))
    for f in fasteners.values():
        unir(f.get("a"), f.get("b"))
    for a, b in extra_edges:
        unir(a, b)
    semilla = {g.get("feature") for g in grounds.values()} | set(extra_grounds)
    pila = [s for s in semilla if s in nodos]
    while pila:
        n = pila.pop()
        if n in out.estaticas:
            continue
        out.estaticas.add(n)
        pila.extend(ady[n])

    # cuerpos: un cuerpo vale si su padre es estático o pertenece a otro cuerpo que vale
    pendientes = dict(moviles)
    while pendientes:
        avance = False
        for n, j in sorted(pendientes.items()):
            padre = j["parent"]
            if padre is None or padre in out.estaticas:
                out.padre_cuerpo[n] = None
            elif padre in pieza_cuerpo and pieza_cuerpo[padre] in out.cuerpos:
                out.padre_cuerpo[n] = pieza_cuerpo[padre]
            elif padre in pieza_cuerpo and pieza_cuerpo[padre] in pendientes:
                continue
            else:
                out.avisos.append(
                    f"La junta '{n}' cuelga de '{padre}', que no está sujeta a tierra ni se mueve "
                    "con otra junta: su cuerpo queda fuera de la simulación"
                )
                del pendientes[n]
                avance = True
                break
            out.cuerpos[n] = miembros[n]
            out.orden.append(n)
            del pendientes[n]
            avance = True
            break
        if not avance:  # sólo quedan cuerpos colgados de cuerpos descartados
            for n in sorted(pendientes):
                out.avisos.append(f"La junta '{n}' cuelga de un cuerpo excluido: queda fuera")
            break

    en_cuerpo = {p for ps in out.cuerpos.values() for p in ps}
    vecinos_fijador: dict[str, set] = {}
    for f in fasteners.values():
        vecinos_fijador.setdefault(f.get("a"), set()).add(f.get("b"))
        vecinos_fijador.setdefault(f.get("b"), set()).add(f.get("a"))
    for p in sorted(ids - out.estaticas - en_cuerpo):
        movil = sorted(vecinos_fijador.get(p, set()) & en_cuerpo)
        if p in pieza_cuerpo:
            out.fuera[p] = f"su junta '{pieza_cuerpo[p]}' quedó fuera"
        elif movil:
            out.fuera[p] = (f"está unida por fijadores a la pieza móvil '{movil[0]}' pero no por una "
                            "junta: declárala con add_joint(arrastrar=true) o una junta 'fija'")
        else:
            out.fuera[p] = "no está sujeta a tierra ni cuelga de una junta"
    return out


# ------------------------------------------------------------------ geometría (OCCT)
@dataclass
class PiezaMovil:
    id: str
    masa: float                 # kg
    com: np.ndarray             # mm (mundo)
    inercia: np.ndarray         # kg·mm² sobre el COM, ejes del mundo (3×3)
    vertices: list              # casco convexo (mm, mundo)
    giro: dict | None = None    # {centro, eje, radio, s0, s1} si gira sobre su eje (mm)
    cascos: list | None = None  # un casco por SÓLIDO para la colisión (V8.9 F7b; None = `vertices`)


def _masa_occt(shape):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, props)
    vol = props.Mass()
    c = props.CentreOfMass()
    m = props.MatrixOfInertia()
    tensor = np.array([[m.Value(i, j) for j in (1, 2, 3)] for i in (1, 2, 3)])
    return vol, np.array([c.X(), c.Y(), c.Z()]), tensor


def _radial(verts: np.ndarray, centro, eje):
    rel = verts - np.asarray(centro)
    s = rel @ eje
    rho = np.linalg.norm(rel - np.outer(s, eje), axis=1)
    return s, rho


def _giro_desde_eje(verts: np.ndarray, centro, eje) -> dict | None:
    eje = np.asarray(eje, float) / np.linalg.norm(eje)
    s, rho = _radial(verts, centro, eje)
    r = float(rho.max()) if len(rho) else 0.0
    if r <= 1e-6:
        return None
    casco = rho >= r - max(1.0, 0.03 * r)
    return {"centro": np.asarray(centro, float), "eje": eje, "radio": r,
            "s0": float(s[casco].min()), "s1": float(s[casco].max())}


def _cara_coaxial(shape, origen, eje, radio: float) -> bool:
    """¿Tiene el sólido una cara cilíndrica coaxial a la junta con el radio exterior?"""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_SurfaceType

    o = np.asarray(origen, float)
    for face in shape.faces():
        try:
            ad = BRepAdaptor_Surface(face.wrapped)
            if ad.GetType() != GeomAbs_SurfaceType.GeomAbs_Cylinder:
                continue
            cyl = ad.Cylinder()
            ax = cyl.Axis()
            d = np.array([ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z()])
            p = np.array([ax.Location().X(), ax.Location().Y(), ax.Location().Z()])
        except Exception:  # noqa: BLE001 — una cara rara no decide nada
            continue
        if abs(float(d @ eje)) < 0.999:
            continue
        off = (p - o) - ((p - o) @ eje) * eje
        if np.linalg.norm(off) > max(0.5, 0.01 * radio):
            continue
        if abs(cyl.Radius() - radio) <= max(0.5, 0.02 * radio):
            return True
    return False


def detectar_giro(feat, junta: dict | None) -> dict | None:
    """Geometría de revolución de una pieza que gira sobre su eje, o None.

    1. Rodillo o tambor de catálogo con instancia: su eje canónico (Z local) en el mundo.
    2. Si cuelga de una junta de giro: una cara cilíndrica coaxial a la junta cuyo radio es el
       exterior del sólido (un `run_script` o un `create_cylinder` también valen)."""
    from apolo.library.catalog import CATALOG

    verts = np.asarray(hull_vertices(feat.shape), float)
    if len(verts) < 4:
        return None
    comp = CATALOG.get(getattr(feat, "component", None) or "")
    if comp is not None and comp.category in _CATEGORIAS_GIRATORIAS:
        mat = getattr(feat, "matrix", None)
        if mat is not None:
            m = np.asarray(mat, float)
            return _giro_desde_eje(verts, m[:3, 3], m[:3, 2])
        if junta is not None and junta["type"] in GIRATORIAS:
            return _giro_desde_eje(verts, junta["origin"], junta["axis"])
    if junta is None or junta["type"] not in GIRATORIAS:
        return None
    eje = np.asarray(junta["axis"], float)
    eje = eje / np.linalg.norm(eje)
    giro = _giro_desde_eje(verts, junta["origin"], eje)
    if giro and _cara_coaxial(feat.shape, junta["origin"], eje, giro["radio"]):
        return giro
    return None


def masa_pieza(feat) -> float:
    """kg: el peso de CATÁLOGO cuando lo hay (la ficha es más fiel que el volumen del modelo
    simplificado: un tambor macizo pesaría 43 kg contra 8 de ficha); si no, `_link_physics`
    (volumen OCCT × densidad del material resuelto)."""
    from apolo.library.engineering.mass import feature_mass

    if getattr(feat, "component", None):
        fm = feature_mass(feat)
        if fm["fuente"] == "catálogo" and fm["masa_kg"] > 0:
            return float(fm["masa_kg"])
    return float(_link_physics(feat)[0])


def masas_de_ficha(scene: dict) -> dict[str, float]:
    """{id: kg} de las piezas que pesan por su FICHA y no por su volumen aunque no lleven ref: el
    vástago de un cilindro pesa la masa MÓVIL (pistón + vástago) y su cuerpo el resto
    (`library/peso_ficha.partes_de_cilindros`, la misma cuenta de `scene_mass_properties`; plan
    pedidos-de-extensiones-iii D11). Sin cilindros, vacío."""
    from apolo.library.peso_ficha import partes_de_cilindros

    return partes_de_cilindros(scene)


def geometria_movil(feat, junta: dict | None, masa: float | None = None) -> PiezaMovil:
    """Masa, centro de masas, inercia y colisión de una pieza que se mueve. La inercia es la
    del sólido real con densidad uniforme escalada a la masa de `masa_pieza`, o a `masa` si el
    llamador la sabe mejor (el vástago de un cilindro: la masa móvil de su ficha)."""
    masa = masa_pieza(feat) if masa is None else float(masa)
    verts = hull_vertices(feat.shape)
    try:
        vol, com, tensor = _masa_occt(feat.shape)
    except Exception:  # noqa: BLE001 — sin GProp: caja del bbox
        vol, com, tensor = 0.0, None, None
    if tensor is None or vol <= 0 or not np.all(np.isfinite(tensor)):
        bb = feat.shape.bounding_box()
        sx, sy, sz = (max(v, 1.0) for v in (bb.size.X, bb.size.Y, bb.size.Z))
        inercia = np.diag([masa / 12 * (sy**2 + sz**2), masa / 12 * (sx**2 + sz**2),
                           masa / 12 * (sx**2 + sy**2)])
        com = np.array([(bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2])
    else:
        inercia = tensor * (masa / vol)
    giro = detectar_giro(feat, junta)
    return PiezaMovil(feat.id if hasattr(feat, "id") else "", float(masa), np.asarray(com, float),
                      inercia, verts, giro, cascos(feat.shape))


def combinar_inercia(piezas: list[PiezaMovil]) -> tuple[float, np.ndarray, np.ndarray]:
    """Masa total, COM (mm) e inercia (kg·mm², sobre el COM conjunto) por Steiner."""
    m = sum(p.masa for p in piezas)
    if m <= 0:
        return 0.0, piezas[0].com.copy(), np.eye(3) * 1e-3
    com = sum(p.masa * p.com for p in piezas) / m
    tot = np.zeros((3, 3))
    for p in piezas:
        r = p.com - com
        tot += p.inercia + p.masa * (float(r @ r) * np.eye(3) - np.outer(r, r))
    return m, com, tot


def inercia_eje(masa: float, com_mm, inercia_kgmm2, origen_mm, eje) -> float:
    """Momento de inercia (kg·m²) sobre la recta (origen, eje)."""
    e = np.asarray(eje, float) / np.linalg.norm(eje)
    r = np.asarray(com_mm, float) - np.asarray(origen_mm, float)
    d2 = float(r @ r - (r @ e) ** 2)
    return (float(e @ inercia_kgmm2 @ e) + masa * d2) * 1e-6


def normal_arriba(eje) -> np.ndarray:
    """La «superficie de transporte» de un rodillo es su generatriz superior: normal +Z
    proyectada fuera del eje (si el eje es vertical no hay arriba: se usa X)."""
    e = np.asarray(eje, float) / np.linalg.norm(eje)
    z = np.array([0.0, 0.0, 1.0])
    n = z - (z @ e) * e
    if np.linalg.norm(n) < 1e-6:
        n = np.array([1.0, 0.0, 0.0]) - e[0] * e
    return n / np.linalg.norm(n)


def signo_transporte(eje, normal, direccion) -> float:
    """Signo del giro para que la superficie de normal `normal` avance hacia `direccion`
    (D7): con ω > 0 sobre `eje` (mano derecha) la superficie va hacia eje × normal."""
    avance = np.cross(np.asarray(eje, float), np.asarray(normal, float))
    p = float(avance @ np.asarray(direccion, float))
    if abs(p) < 0.2 * np.linalg.norm(avance):
        return 0.0
    return math.copysign(1.0, p)
