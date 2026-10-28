"""La barra que se CORTA, medida (plan lista-de-corte-medida, D1/D2/D5): el eje de un perfil, su
largo EXTERIOR y cómo termina cada extremo, sobre la forma — no sobre lo que declaró su comando.

`medir_barras(shape, seccion)` → una medida por sólido de `shape` (el orden de `solids()`), o None
en el sólido que no se deja medir como barra. Una medida es
`{"eje": (x, y, z), "largo_mm", "extremos": [e0, e1]}` y cada extremo
`{"corte": "recto" | "angulo" | "dos_planos" | "especial", "angulos": [α…]}`:

- **Eje** = la dirección de las aristas RECTAS que más largo suman (las de extrusión de un perfil;
  la costura de un tubo redondo). Un perfil corto o casi cúbico no se distingue así: se valida
  con la sección de la FICHA (`seccion` = sus dos lados, la ref se extruye en Z local): si las
  extensiones de la pieza perpendiculares al eje no son esa sección, None (el llamador cae a lo
  de siempre).
- **Largo exterior** = la extensión de la pieza sobre el eje (los mismos puntos que
  `library/miembro._largo_exterior`: vértices de las rectas y 17 por curva).
- **Extremos**: las caras de corte son las que NO cruzan la mitad del largo (las que la cruzan son
  el costado del perfil) y tocan el contorno EXTERIOR de un costado: un taladro o una colisa
  cerrada viven en un hueco del costado y no son un corte. Por extremo: un solo plano → su ángulo
  α con la sección recta (0 = a escuadra: `recto`); dos planos que se cortan en una arista
  CONVEXA → `dos_planos` (despunte, los dos α); cualquier otra cosa —una cara curva (boca de
  pescado), un piso paralelo al eje o dos planos paralelos (el escalón de un rebaje), una arista
  cóncava (una muesca), tres planos— → `especial` (a plano, nunca «recto»).

Puro sobre la forma. Caché por `id(shape)` con la referencia y `is` (regla de core/apolo/CLAUDE.md):
la lista de corte, el CSV y los planos miden la misma pieza en una corrida.
"""

from __future__ import annotations

import math

_CACHE: dict = {}
_CACHE_MAX = 4096
#: |n·eje| por debajo de esto, la cara es paralela al eje (≈ 1°).
_PARALELA = math.sin(math.radians(1.0))
#: dos direcciones (o normales) son la misma si forman menos de 0,5°.
_MISMA = math.cos(math.radians(0.5))
_TOL = 0.2  # mm: tolerancia de posición (plano repetido, arista convexa)


def medir_barras(shape, seccion: tuple | None = None) -> list:
    """Ver el docstring del módulo. Nunca lanza: un sólido que OCCT no deja medir da None."""
    clave = (id(shape), tuple(seccion) if seccion else None)
    hit = _CACHE.get(clave)
    if hit is not None and hit[0] is shape:
        return list(hit[1])
    try:
        solidos = list(shape.solids()) or [shape]
    except Exception:  # noqa: BLE001 — sin sólidos: la forma misma
        solidos = [shape]
    out = []
    for s in solidos:
        try:
            out.append(_medir(s, seccion))
        except Exception:  # noqa: BLE001 — geometría que OCCT no deja leer: sin medida
            out.append(None)
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[clave] = (shape, tuple(out))
    return out


def _dot(p, q):
    return p[0] * q[0] + p[1] * q[1] + p[2] * q[2]


def _unit(p):
    n = math.sqrt(_dot(p, p))
    return (p[0] / n, p[1] / n, p[2] / n) if n > 1e-12 else None


def _canon(d):
    """La dirección con signo canónico (la primera componente no nula, positiva)."""
    for c in d:
        if abs(c) > 1e-9:
            return d if c > 0 else (-d[0], -d[1], -d[2])
    return d


def _cross(p, q):
    return (p[1] * q[2] - p[2] * q[1], p[2] * q[0] - p[0] * q[2], p[0] * q[1] - p[1] * q[0])


def _tup(v):
    return (v.X, v.Y, v.Z)


def _direcciones(rectas) -> list:
    """[[dirección, largo total]] de las aristas rectas, juntando las paralelas, de mayor a menor."""
    grupos: list = []
    for d, largo in rectas:
        for g in grupos:
            if abs(_dot(g[0], d)) > _MISMA:
                g[1] += largo
                break
        else:
            grupos.append([d, largo])
    grupos.sort(key=lambda g: -g[1])
    return grupos


def _medir(solido, seccion):
    from build123d import GeomType

    aristas = list(solido.edges())
    puntos: dict = {}  # arista → sus puntos de muestra
    rectas = []
    for e in aristas:
        if e.geom_type == GeomType.LINE:
            a, b = _tup(e.start_point()), _tup(e.end_point())
            puntos[e] = (a, b)
            d = _unit((b[0] - a[0], b[1] - a[1], b[2] - a[2]))
            if d is not None:
                rectas.append((_canon(d), e.length))
        else:
            puntos[e] = tuple(_tup(v) for v in e.positions([i / 16.0 for i in range(17)]))
    grupos = _direcciones(rectas)
    if not grupos:
        return None
    eje = grupos[0][0]
    todos = [p for ps in puntos.values() for p in ps]
    zs = [_dot(p, eje) for p in todos]
    z0, z1 = min(zs), max(zs)
    largo = z1 - z0
    if largo <= 1e-6 or (seccion and not _seccion_cuadra(todos, eje, grupos, seccion)):
        return None
    zmed = (z0 + z1) / 2.0

    def rango(cara):
        zz = [_dot(p, eje) for e in cara.edges() for p in puntos.get(e, ())]
        return (min(zz), max(zz)) if zz else (zmed, zmed)

    caras = list(solido.faces())
    rangos = [rango(c) for c in caras]
    costado = [lo < zmed - _TOL and hi > zmed + _TOL for lo, hi in rangos]
    contorno = set()  # aristas del contorno EXTERIOR de los costados
    for c, es in zip(caras, costado):
        if es:
            contorno.update(c.outer_wire().edges())
    extremos: list[list] = [[], []]
    for c, es, (lo, hi) in zip(caras, costado, rangos):
        if es or not any(e in contorno for e in c.edges()):
            continue
        if lo < zmed - _TOL and hi > zmed + _TOL:
            return None  # una cara de corte que recorre la pieza: no es una barra
        extremos[0 if (lo + hi) / 2.0 < zmed else 1].append(c)
    if not extremos[0] or not extremos[1]:
        return None
    return {"eje": eje, "largo_mm": round(largo, 1),
            "extremos": [_extremo(cs, eje) for cs in extremos]}


def _seccion_cuadra(todos, eje, grupos, seccion) -> bool:
    """Las extensiones de la pieza perpendiculares al eje son la sección de la ficha."""
    x = None
    for d, _largo in grupos[1:]:
        if abs(_dot(d, eje)) < _PARALELA:
            x = d
            break
    if x is None:
        ref = (1.0, 0.0, 0.0) if abs(eje[0]) < 0.9 else (0.0, 1.0, 0.0)
        x = _unit(_cross(eje, ref))
    else:
        x = _unit(tuple(x[i] - _dot(x, eje) * eje[i] for i in range(3)))
    y = _cross(eje, x)
    ex = [_dot(p, x) for p in todos]
    ey = [_dot(p, y) for p in todos]
    med = sorted((max(ex) - min(ex), max(ey) - min(ey)))
    ficha = sorted(float(v) for v in seccion)
    return all(abs(m - f) <= max(1.0, 0.02 * f) for m, f in zip(med, ficha))


def _angulo(n, eje) -> float:
    return round(math.degrees(math.acos(min(1.0, abs(_dot(n, eje))))), 1)


def _extremo(caras, eje) -> dict:
    from build123d import GeomType

    especial = {"corte": "especial", "angulos": []}
    planos: list = []  # [normal, distancia, [caras]]
    for c in caras:
        if c.geom_type != GeomType.PLANE:
            return especial  # boca de pescado, un taladro que llega al extremo
        n = _tup(c.normal_at())
        if abs(_dot(n, eje)) < _PARALELA:
            return especial  # el piso de un escalón
        d = _dot(n, _tup(c.vertices()[0]))
        for pl in planos:
            if _dot(pl[0], n) > _MISMA and abs(pl[1] - d) < _TOL:
                pl[2].append(c)
                break
        else:
            planos.append([n, d, [c]])
    if len(planos) == 1:
        a = _angulo(planos[0][0], eje)
        return {"corte": "recto", "angulos": [0.0]} if a < 0.1 else {"corte": "angulo", "angulos": [a]}
    if len(planos) == 2 and _convexos(planos[0], planos[1]):
        return {"corte": "dos_planos", "angulos": sorted(_angulo(p[0], eje) for p in planos)}
    return especial


def _convexos(pa, pb) -> bool:
    """Dos planos que comparten una arista CONVEXA (un despunte), no paralelos ni en escalón."""
    if abs(_dot(pa[0], pb[0])) > _MISMA:
        return False  # paralelos: un escalón
    if not any(set(fa.edges()) & set(fb.edges()) for fa in pa[2] for fb in pb[2]):
        return False
    for (n, d, _), otro in ((pa, pb), (pb, pa)):
        lados = [_dot(n, _tup(v)) - d for f in otro[2] for v in f.vertices()]
        if max(lados) > _TOL:
            return False  # la otra cara queda FUERA de este plano: arista cóncava
    return True
