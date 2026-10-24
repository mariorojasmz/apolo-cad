"""D5 — la puerta abre de verdad: interferencia cero entre lo que cuelga de la puerta y lo fijo del
tablero en TODO el recorrido de la bisagra (plan V8.5 F1b). PURO (sin OCCT).

Todo lo del tablero es una caja alineada con los ejes del gabinete (`armado.Caja`, marco G): la
puerta y sus mandos (lo MÓVIL) giran juntos sobre el eje vertical de la bisagra; lo FIJO (cuerpo
—fondo, laterales, techo, piso—, espárragos, placa, rieles, canaletas, topes y aparatos) no se
mueve. Una caja que gira sobre Z sigue alineada en Z, así que el choque es: los rangos en Z se
cruzan Y, en XY, el rectángulo girado y el fijo se cruzan por el teorema del eje separador (los
4 ejes de los dos rectángulos). La PENETRACIÓN es el menor solape (largo de la parte común de
las dos proyecciones) sobre esos ejes y sobre Z: 0 = se tocan
(contacto cara a cara, como la puerta cerrada contra el borde del cuerpo); > `TOL_CHOQUE_MM`,
choca. El cuerpo se descompone en sus 5 paredes: así lo de adentro no «choca» con la caja que lo
contiene. Una seta se mide por su caja (envolvente: conservador).

Se muestrea de 0 a `abre_deg` cada `paso_deg` (1°: a 500 mm del eje, 8,7 mm de arco entre
muestras) más el extremo. Devuelve el PEOR choque (más penetración; a igualdad, el primer ángulo)
o None, y cuántos ángulos se revisaron.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .armado import TOL_CHOQUE_MM, Armado, Caja

PASO_DEG = 1.0


@dataclass(frozen=True)
class Choque:
    movil: str      # rol de lo que cuelga de la puerta
    fijo: str       # rol de lo fijo
    angulo_deg: float
    penetracion_mm: float


def paredes(a: Armado) -> list[tuple[str, Caja]]:
    """El cuerpo del gabinete como sus 5 paredes (rol, caja)."""
    g, c = a.interior, a.pieza("gabinete").caja
    e = g.espesor
    return [
        ("Gabinete · fondo", Caja(c.x0, c.x1, c.y1 - e, c.y1, c.z0, c.z1)),
        ("Gabinete · lateral izquierdo", Caja(c.x0, c.x0 + e, c.y0, c.y1 - e, c.z0, c.z1)),
        ("Gabinete · lateral derecho", Caja(c.x1 - e, c.x1, c.y0, c.y1 - e, c.z0, c.z1)),
        ("Gabinete · piso", Caja(c.x0 + e, c.x1 - e, c.y0, c.y1 - e, c.z0, c.z0 + e)),
        ("Gabinete · techo", Caja(c.x0 + e, c.x1 - e, c.y0, c.y1 - e, c.z1 - e, c.z1)),
    ]


def fijas(a: Armado) -> list[tuple[str, Caja]]:
    out = paredes(a) + [(f"Espárrago de la placa ({i})", k) for i, k in enumerate(a.esparragos, 1)]
    out += [(p.rol, p.caja) for p in a.fijas if p.zona != "cuerpo"]
    return out


def moviles(a: Armado) -> list[tuple[str, Caja]]:
    return [(p.rol, p.caja) for p in a.moviles]


def _girar(c: Caja, eje_xy: tuple[float, float], s: float, ang: float) -> list[tuple[float, float]]:
    """Las 4 esquinas en XY de la caja girada `ang` (rad) con signo `s` (eje ±Z) sobre el eje."""
    ox, oy = eje_xy
    t = s * ang
    co, si = math.cos(t), math.sin(t)
    out = []
    for x, y in ((c.x0, c.y0), (c.x1, c.y0), (c.x1, c.y1), (c.x0, c.y1)):
        dx, dy = x - ox, y - oy
        out.append((ox + dx * co - dy * si, oy + dx * si + dy * co))
    return out


def _solape(a: list, b: list, eje: tuple[float, float]) -> float:
    pa = [p[0] * eje[0] + p[1] * eje[1] for p in a]
    pb = [p[0] * eje[0] + p[1] * eje[1] for p in b]
    return min(max(pa), max(pb)) - max(min(pa), min(pb))


def penetracion(rect: list, fijo: Caja, ang_rect: float) -> float:
    """El menor solape (mm) en XY entre el rectángulo girado y la caja fija; ≤ 0 = separados."""
    f = [(fijo.x0, fijo.y0), (fijo.x1, fijo.y0), (fijo.x1, fijo.y1), (fijo.x0, fijo.y1)]
    ejes = [(1.0, 0.0), (0.0, 1.0), (math.cos(ang_rect), math.sin(ang_rect)),
            (-math.sin(ang_rect), math.cos(ang_rect))]
    return min(_solape(rect, f, e) for e in ejes)


def recorrer(a: Armado, paso_deg: float = PASO_DEG) -> tuple[Choque | None, int]:
    """(el peor choque en el recorrido, n.º de ángulos revisados)."""
    b = a.bisagra
    eje_xy, s = (b.origen[0], b.origen[1]), (1.0 if b.eje[2] > 0 else -1.0)
    n = max(1, math.ceil(b.abre_deg / paso_deg))
    angulos = [min(b.abre_deg, k * paso_deg) for k in range(n + 1)]
    movs, fijos_ = moviles(a), fijas(a)
    peor: Choque | None = None
    for deg in angulos:
        ang = math.radians(deg)
        for rol_m, cm in movs:
            rect = _girar(cm, eje_xy, s, ang)
            xs, ys = [p[0] for p in rect], [p[1] for p in rect]
            for rol_f, cf in fijos_:
                en_z = min(cm.z1, cf.z1) - max(cm.z0, cf.z0)
                if en_z <= TOL_CHOQUE_MM:
                    continue
                if max(xs) <= cf.x0 or min(xs) >= cf.x1 or max(ys) <= cf.y0 or min(ys) >= cf.y1:
                    continue
                pen = min(penetracion(rect, cf, s * ang), en_z)
                if pen > TOL_CHOQUE_MM and (peor is None or pen > peor.penetracion_mm + 1e-9):
                    peor = Choque(rol_m, rol_f, deg, round(pen, 2))
    return peor, len(angulos)
