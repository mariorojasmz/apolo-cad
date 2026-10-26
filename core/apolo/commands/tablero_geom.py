"""La geometría del tablero (plan V8.5 F1b): las formas OCCT de lo que `library/electrico/armado.py`
describe en cajas. Sólo arma formas NUEVAS (ningún shape se muta en sitio): el cuerpo hueco del
gabinete con sus espárragos, la puerta con sus huecos (la forma de cada uno, `huecos_por_ref`), la
placa, y la matriz que lleva una ref del catálogo (centrada en su caja) a su caja del armado.
"""

from __future__ import annotations

from apolo.library.electrico.armado import Armado, Caja, Pieza
from apolo.library.electrico.ficha_tablero import agujero_mm

from .errors import CommandError

_SOLAPE = 0.5  # lo que una herramienta de corte sobresale (regla de library/CLAUDE.md)


def huecos_por_ref(refs, catalogo) -> dict[str, tuple]:
    """Lo que la puerta NO recorta con la huella de la caja de una ref: la que da su agujero de
    montaje en la ficha (`specs.agujero`: la seta y la serie Ø22), ese Ø («circulo», d); un mando
    con `tablero.puerta.recorte_mm` (el panel de operador), su recorte («rect», ancho, alto). Las
    demás refs no van: su hueco es su caja (plan pedidos-de-extensiones-ii D1)."""
    out: dict[str, tuple] = {}
    for r in sorted(refs):
        comp = catalogo[r]
        marco = comp.tablero.puerta if comp.tablero is not None else None
        d = agujero_mm(comp.specs, r)
        if d is not None:
            out[r] = ("circulo", d)
        elif marco is not None and marco.recorte_mm is not None:
            out[r] = ("rect", *marco.recorte_mm)
    return out


def _caja_solida(c: Caja):
    from build123d import Box, Pos

    dx, dy, dz = c.medidas
    return Pos(*c.centro) * Box(dx, dy, dz)


def cuerpo(a: Armado):
    """El cuerpo hueco (abierto al frente, donde va la puerta) con los 4 espárragos de la placa."""
    from build123d import Cylinder, Pos, Rotation

    c = a.pieza("gabinete").caja
    e = a.interior.espesor
    hueco = Caja(c.x0 + e, c.x1 - e, c.y0 - _SOLAPE, c.y1 - e, c.z0 + e, c.z1 - e)
    forma = _caja_solida(c) - _caja_solida(hueco)
    for k in a.esparragos:
        largo = k.y1 - k.y0 + _SOLAPE  # entra medio mm en el fondo: un solo sólido
        cx, _, cz = k.centro
        espiga = Pos(cx, k.y0 + largo / 2, cz) * (Rotation(90, 0, 0) * Cylinder((k.x1 - k.x0) / 2, largo))
        forma = forma + espiga
    return forma


def puerta(a: Armado):
    """La chapa de la puerta con un hueco por mando (la huella de su caja, su recorte o el Ø de su
    ficha)."""
    from build123d import Box, Cylinder, Pos, Rotation

    c = a.pieza("puerta").caja
    forma = _caja_solida(c)
    alto = c.y1 - c.y0 + 2 * _SOLAPE
    yc = (c.y0 + c.y1) / 2
    for h in a.huecos:
        if h.forma == "circulo":
            x, z, d = h.medidas
            herramienta = Pos(x, yc, z) * (Rotation(90, 0, 0) * Cylinder(d / 2, alto))
        else:
            x0, x1, z0, z1 = h.medidas
            herramienta = Pos((x0 + x1) / 2, yc, (z0 + z1) / 2) * Box(x1 - x0, alto, z1 - z0)
        forma = forma - herramienta
    return forma


def placa(a: Armado):
    return _caja_solida(a.pieza("placa").caja)


def matriz_catalogo(p: Pieza, base, m_gab) -> list:
    """La rígida 4×4 que lleva la forma de catálogo `base` (en su marco) a la caja de `p` en G y,
    con `m_gab`, al mundo: centro de su bbox → centro de la caja, con el giro del armado. Error
    si las medidas giradas no son las de la caja (la ref no es la que midió la colocación)."""
    from apolo.kernel.matrix import multiply, translation

    bb = base.bounding_box()
    c_l = ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)
    med_l = (bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)
    cols = p.giro  # columnas = imagen en G de los ejes locales x, y, z
    girado = [sum(abs(cols[j][i]) * med_l[j] for j in range(3)) for i in range(3)]
    if any(abs(g - m) > 0.5 for g, m in zip(girado, p.caja.medidas)):
        raise CommandError(
            f"{p.rol} ({p.ref}): su forma de catálogo mide {' × '.join(f'{x:.1f}' for x in girado)} "
            f"mm y su lugar en el tablero {' × '.join(f'{x:.1f}' for x in p.caja.medidas)}: revisa "
            "la cara de apoyo de la ref (`tablero.apoyo`) o sus cotas")
    rot = [[float(cols[j][i]) for j in range(3)] + [0.0] for i in range(3)] + [[0.0, 0.0, 0.0, 1.0]]
    local = multiply(multiply(translation(*p.caja.centro), rot), translation(*(-x for x in c_l)))
    return multiply(m_gab, local)
