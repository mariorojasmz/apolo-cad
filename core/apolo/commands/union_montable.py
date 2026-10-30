"""`join_bolted` criterio 8 (plan lo-fijo-que-gira-y-lo-que-cuelga, D5 y F4): la unión que se
puede MONTAR.

- **Asiento por el contacto real** (`asiento_real`): si el solape de las cajas no da una cara
  plana en el plano de contacto (un perfil en Z, cuya caja pone el contacto en el canto de un ala;
  una pieza girada 90°), la huella sale de la zona donde las dos piezas se tocan de verdad
  (`kernel/contacto.zona_de_contacto`), siempre que sea plana y ⊥ a un eje del mundo. Si las
  cajas ya daban la cara, la huella es la de siempre (la misma geometría que el 7).
- **Herraje fuera del material** (`exigir_herraje_fuera`): ya medido el eje (`union_taller._medir`),
  rechaza con un error accionable la cabeza que caería dentro del sólido de una pieza o en el hueco
  CERRADO de la pieza que se agrega (la ménsula bajo un tubo: la cabeza en la cara de ADENTRO de su
  pared de abajo), y la arandela o la tuerca que caerían dentro de la pieza que se agrega. Lo de
  detrás de la base ya lo cubre el acceso (perfil cerrado u obstáculo → remache ciego).

Como el 5 y el 7, sólo rechaza o busca el asiento donde el 7 daba error: los criterios 1–7
guardados regeneran igual (el criterio viaja en los params).
"""

from __future__ import annotations

from .errors import CommandError
from .exec_union import _AXNAME, exigir_asiento

_TOL_PLANO = 0.6  # mm: espesor máximo de la zona de contacto para tomarla como un plano
_TOL_MATERIAL = 0.05  # mm: el herraje que ROZA una cara no está dentro


def asiento_real(h: dict, a, b) -> dict:
    """La huella con cara plana de contacto: la de las cajas (`exigir_asiento` como el 7) o, si
    ahí falta, la de la zona de contacto real. Devuelve `h` (o una copia con otro eje y otra
    huella); si tampoco la zona da un plano, el error de siempre."""
    from apolo.kernel.contacto import zona_de_contacto

    st = h["stack"]
    a_abajo = (h["amin"][st] + h["amax"][st]) <= (h["bmin"][st] + h["bmax"][st])
    try:
        exigir_asiento(a.shape, h, h["amax"][st] if a_abajo else h["amin"][st], "contacto")
        exigir_asiento(b.shape, h, h["bmin"][st] if a_abajo else h["bmax"][st], "contacto")
        return h
    except CommandError as exc:
        error = exc
    try:
        zona = zona_de_contacto(a.shape, b.shape)
    except ValueError:
        zona = None
    if zona is None:
        raise error
    lo, hi = zona[:3], zona[3:]
    ext = [hi[k] - lo[k] for k in range(3)]
    st = min(range(3), key=ext.__getitem__)
    inplane = [k for k in range(3) if k != st]
    if ext[st] > _TOL_PLANO or any(ext[k] <= 1e-6 for k in inplane):
        raise error  # la zona no es un plano ⊥ a un eje del mundo (una pieza girada en ángulo)
    coord = (lo[st] + hi[st]) / 2.0
    real = dict(h)
    real["stack"], real["inplane"] = st, inplane
    real["foot_min"] = [coord if k == st else lo[k] for k in range(3)]
    real["foot_max"] = [coord if k == st else hi[k] for k in range(3)]
    real["overlap"] = [0.0 if k == st else ext[k] for k in range(3)]
    exigir_asiento(a.shape, real, coord, "contacto")
    exigir_asiento(b.shape, real, coord, "contacto")
    return real


def _dentro(pieza, st: int, pt: list[float], t0: float, t1: float) -> tuple[float, float] | None:
    """El tramo de material de `pieza` que el eje cruza dentro de (t0, t1), o None."""
    from apolo.kernel.rayo import tramos_en_eje

    lo, hi = min(t0, t1), max(t0, t1)
    for x0, x1 in tramos_en_eje(pieza.shape, st, pt, lo - 1.0, hi + 1.0):
        if min(x1, hi) - max(x0, lo) > _TOL_MATERIAL:
            return x0, x1
    return None


def _hueco_cerrado(pieza, h: dict, pt: list[float], desde: float, sentido: float) -> float | None:
    """¿El eje, saliendo de `desde` hacia `sentido`, vuelve a entrar en `pieza`? (la pared de
    enfrente de un tubo). Devuelve dónde re-entra, salvo que el hueco se abra a un costado (el ala
    de un perfil abierto, como el acceso del criterio 4)."""
    from apolo.kernel.rayo import tramos_en_eje

    from .union_taller import _abierto_al_costado

    st = h["stack"]
    bb = pieza.shape.bounding_box()
    lo, hi = (bb.min.X, bb.min.Y, bb.min.Z)[st] - 1.0, (bb.max.X, bb.max.Y, bb.max.Z)[st] + 1.0
    tramos = tramos_en_eje(pieza.shape, st, pt, lo, hi)
    vuelve = [x0 for x0, _ in tramos if x0 > desde + 1e-3] if sentido > 0 else [
        x1 for _, x1 in tramos if x1 < desde - 1e-3]
    if not vuelve:
        return None
    re = min(vuelve) if sentido > 0 else max(vuelve)
    if _abierto_al_costado(pieza, h, pt, (desde + re) / 2.0):
        return None
    return re


def exigir_herraje_fuera(h: dict, base, anadida, puntos: list, medidas: list, fij, otros: list,
                         rol: str) -> None:
    """D5: la cabeza, la arandela y la tuerca de cada punto, fuera del material y de un hueco
    cerrado. CommandError accionable con la pieza y las cotas."""
    st = h["stack"]
    eje = _AXNAME[st]
    for n, (pt, m) in enumerate(zip(puntos, medidas, strict=True), start=1):
        s = m["s"]
        cabeza = (m["cabeza"], m["cabeza"] - s * fij.cabeza_k)  # hacia afuera de la agregada
        for pieza in (anadida, base, *otros):
            if (tr := _dentro(pieza, st, pt, *cabeza)) is not None:
                raise CommandError(
                    f"La cabeza del {rol} {n} de la unión queda dentro de «{pieza.name}» ({eje} "
                    f"{min(tr):.1f}–{max(tr):.1f}): no se puede montar. Mueve las piezas para "
                    "despejar la cara de la cabeza o cambia count/patron/spacing."
                )
        re = _hueco_cerrado(anadida, h, pt, m["cabeza"], -s)
        if re is not None:
            a0, a1 = sorted((m["cabeza"], re))
            raise CommandError(
                f"La cabeza del {rol} {n} quedaría dentro del hueco cerrado de «{anadida.name}» "
                f"({eje} {a0:.1f}–{a1:.1f}, la cara de ADENTRO de su pared): no se puede meter ni "
                f"apretar. Atornilla «{anadida.name}» por una cara con acceso (una placa o "
                "ménsula a su cara de afuera, o una pieza de perfil abierto), o únelas con "
                "soldadura (fasten kind=soldadura)."
            )
        if fij.tipo == "perno":
            atras = (m["atras"], m["atras"] + s * (fij.arandela_h + fij.tuerca_m))
            if (tr := _dentro(anadida, st, pt, *atras)) is not None:
                que = "la arandela o la tuerca" if fij.arandela else "la tuerca"
                raise CommandError(
                    f"{que.capitalize()} del {rol} {n} queda dentro de «{anadida.name}» ({eje} "
                    f"{min(tr):.1f}–{max(tr):.1f}): no se puede montar. Mueve las piezas o "
                    "cambia count/patron/spacing."
                )
