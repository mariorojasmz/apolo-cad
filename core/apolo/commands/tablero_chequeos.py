"""Lo que `layout_tablero` verifica con OCCT (plan V8.5 F1b): la bisagra en el mundo, las piezas
ligadas de A9 y los vecinos de la puerta (D5 fuera del tablero). Cada falla es `CommandError`
con la pieza y la cifra: el comando no deja un tablero que no se arma o cuya puerta no abre.

- **A9** — un dispositivo con `pieza` ya está modelado: no se redibuja. Se EXIGE que su pieza
  quede dentro del gabinete (lo de placa, en el interior; un mando de puerta, en la puerta, con
  lo que asoma delante) y que no choque con lo que el layout arma (> `MIN_VOLUME_MM3`). El
  mensaje da el lugar que le reservó la colocación (centro en el mundo) para moverla ahí.
- **Vecinos** — lo que cuelga de la puerta, girado cada `PASO_VECINOS_DEG` de 0 a 110°, contra
  el resto de la escena que ya estaba (prefiltro por cajas, booleana sólo si se cruzan): una
  puerta que pega en una pata de la máquina no abre, aunque adentro esté todo bien.
"""

from __future__ import annotations

from apolo.library.checks import MIN_VOLUME_MM3

from .errors import CommandError

PASO_VECINOS_DEG = 5.0
_TOL_DENTRO_MM = 0.5


def _aplicar(m, p) -> tuple[float, float, float]:
    return tuple(m[i][0] * p[0] + m[i][1] * p[1] + m[i][2] * p[2] + m[i][3] for i in range(3))


def bisagra_mundo(arm, m_gab, p) -> tuple[tuple, tuple]:
    """(origen, eje) de la bisagra en el mundo; el eje tiene que quedar alineado con X, Y o Z
    (la cinemática de Apolo gira sólo sobre ejes del mundo)."""
    b = arm.bisagra
    o = _aplicar(m_gab, b.origen)
    eje = tuple(sum(m_gab[i][j] * b.eje[j] for j in range(3)) for i in range(3))
    k = max(range(3), key=lambda i: abs(eje[i]))
    if any(abs(eje[i]) > 1e-6 for i in range(3) if i != k):
        raise CommandError(f"Tablero {p.ubicacion}: con rotation {p.rotation.tuple()} el eje de la "
                           f"bisagra queda en {tuple(round(x, 3) for x in eje)}, no alineado con un eje "
                           "del mundo: gira el tablero en Z, o en múltiplos de 90° en X/Y")
    exacto = [0.0, 0.0, 0.0]
    exacto[k] = 1.0 if eje[k] > 0 else -1.0
    return tuple(round(x, 6) for x in o), tuple(exacto)


def resolver_ligadas(arm, escena: dict, ubicacion: str) -> dict[str, str]:
    """{clave del armado: id del sólido} de los aparatos con `pieza` (A9)."""
    from .electrico_eval import _pieza

    out = {}
    for pz in arm.piezas:
        if pz.pieza is None:
            continue
        try:
            out[pz.clave] = _pieza(pz.pieza, pz.ref, escena)
        except ValueError as exc:
            raise CommandError(f"Tablero {ubicacion}: {pz.designacion} ({pz.ref}): {exc}") from None
    return out


def _caja_en_g(shape, m_inv) -> tuple:
    bb = shape.bounding_box()
    esquinas = [_aplicar(m_inv, (x, y, z)) for x in (bb.min.X, bb.max.X)
                for y in (bb.min.Y, bb.max.Y) for z in (bb.min.Z, bb.max.Z)]
    return tuple(min(c[i] for c in esquinas) for i in range(3)), tuple(max(c[i] for c in esquinas)
                                                                       for i in range(3))


def _solapa(a, b, margen: float = 0.0) -> bool:
    return all(a.min[i] <= b.max[i] + margen and b.min[i] <= a.max[i] + margen for i in range(3))


class _BB:
    __slots__ = ("min", "max")

    def __init__(self, lo, hi):
        self.min, self.max = lo, hi


def _bb(shape) -> _BB:
    b = shape.bounding_box()
    return _BB((b.min.X, b.min.Y, b.min.Z), (b.max.X, b.max.Y, b.max.Z))


def _comun(a, b) -> float:
    try:
        inter = a & b
        return float(inter.volume) if inter is not None else 0.0
    except Exception:  # noqa: BLE001 — una booleana que OCCT no resuelve no es un choque
        return 0.0


def piezas_ligadas(arm, ligadas: dict, escena: dict, fid: dict, m_gab, ubicacion: str) -> None:
    """A9: cada pieza ligada dentro del gabinete y sin chocar con lo que se armó."""
    from apolo.kernel.matrix import invert_rigid

    if not ligadas:
        return
    m_inv = invert_rigid(m_gab)
    g = arm.interior
    W, D, H, e = g.ancho, g.fondo, g.alto, g.espesor
    propias = [escena[f] for c, f in fid.items() if c not in ligadas]
    for clave, sid in ligadas.items():
        pz, feat = arm.pieza(clave), escena[sid]
        lo, hi = _caja_en_g(feat.shape, m_inv)
        if pz.zona == "puerta":
            caja = ((-W / 2, pz.caja.y0, -H / 2), (W / 2, D / 2 - e, H / 2))
        else:
            caja = ((-W / 2 + e, -D / 2 + g.espesor_puerta, -H / 2 + e), (W / 2 - e, D / 2 - e, H / 2 - e))
        fuera = max(max(caja[0][i] - lo[i], hi[i] - caja[1][i]) for i in range(3))
        centro = _aplicar(m_gab, pz.caja.centro)
        lugar = "(" + ", ".join(f"{x:.1f}" for x in centro) + ")"
        if fuera > _TOL_DENTRO_MM:
            raise CommandError(
                f"Tablero {ubicacion}: {pz.designacion} está ligado a la pieza {sid} «{feat.name}», "
                f"que sale {fuera:.0f} mm del gabinete {g.ref}"
                + (" (un mando de puerta va EN la puerta)" if pz.zona == "puerta" else "")
                + f": muévela a su lugar (centro {lugar} en el mundo) o quítale la `pieza` al "
                "dispositivo para que el layout lo dibuje")
        bb = _bb(feat.shape)
        for otra in propias:
            if _solapa(bb, _bb(otra.shape)) and (v := _comun(feat.shape, otra.shape)) > MIN_VOLUME_MM3:
                raise CommandError(
                    f"Tablero {ubicacion}: la pieza {sid} «{feat.name}» ({pz.designacion}) choca con "
                    f"«{otra.name}» ({v:.0f} mm³): muévela a su lugar (centro {lugar} en el mundo)")


def vecinos(arm, escena: dict, fid: dict, previas: dict, bisagra, ubicacion: str) -> None:
    """D5 afuera: lo que cuelga de la puerta, en todo su recorrido, contra lo que ya estaba."""
    from apolo.kernel.matrix import rotation_axis_angle_about
    from apolo.kernel.shapes import place_matrix

    movil_ids = [fid[p.clave] for p in arm.moviles]
    moviles = [escena[i] for i in movil_ids]
    quietos = [f for i, f in previas.items() if i not in movil_ids and getattr(f, "visible", True)
               and not getattr(f, "is_guide", False)]
    if not quietos:
        return
    cajas_q = [(f, _bb(f.shape)) for f in quietos]
    esquinas = {}
    for f in moviles:
        b = f.shape.bounding_box()
        esquinas[f.id] = [(x, y, z) for x in (b.min.X, b.max.X) for y in (b.min.Y, b.max.Y)
                          for z in (b.min.Z, b.max.Z)]
    origen, eje = bisagra
    n = int(round(110.0 / PASO_VECINOS_DEG))
    for k in range(n + 1):
        deg = k * PASO_VECINOS_DEG
        m = rotation_axis_angle_about(origen, eje, deg)
        for f in moviles:
            pts = [_aplicar(m, q) for q in esquinas[f.id]]
            bb = _BB(tuple(min(q[i] for q in pts) for i in range(3)),
                     tuple(max(q[i] for q in pts) for i in range(3)))
            for otro, bq in cajas_q:
                if not _solapa(bb, bq):
                    continue
                girada = f.shape if k == 0 else place_matrix(f.shape, m)
                if (v := _comun(girada, otro.shape)) > MIN_VOLUME_MM3:
                    raise CommandError(
                        f"Tablero {ubicacion}: la puerta no abre: «{f.name}» pega en «{otro.name}» "
                        f"({otro.id}) a {deg:g}° ({v:.0f} mm³); mueve el tablero, cambia la "
                        "`bisagra` o aparta esa pieza")
