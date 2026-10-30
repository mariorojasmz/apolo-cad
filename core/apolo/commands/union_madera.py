"""`join_bolted` criterio 7 (plan hallazgos-del-revisor-en-la-puerta, D7 y F4): en MADERA, la
distancia de cada agujero a la testa y al canto con la MISMA medida de la puerta
(`library/borde_agujero.medir_madera`: testa ≥ 4·d y canto ≥ 3·d, criterio de diseño con los
mínimos descargados de EN 1995-1-1, tabla 8.4) y el tornillo que entraría por la testa.

Las piezas de madera son las que el sello anotó al crear la unión (`madera`). Su agujero no se
juzga con la tabla de chapas del criterio 5 (`union_taller._exigir_bordes`): la madera es más
exigente y otra. Como el 5, no cambia la geometría: sólo rechaza, con un error accionable. Los
criterios 1–6 guardados regeneran igual (el criterio viaja en los params).
"""

from __future__ import annotations

from .errors import CommandError

_LADO = {"testa": ("de la testa", "4"), "canto": ("del canto", "3")}


def bordes_del_patron(h: dict, a, b, madera: list[str]) -> dict[int, float] | None:
    """El borde del patrón en la huella cuando una pieza es de madera, para que el patrón
    automático nazca dentro del mínimo que después se mide: por eje de la huella, lo que pide
    cada pieza de madera (4·d si el eje va según su veta —o no tiene veta reconocible—, 3·d de
    través) menos lo que esa pieza sigue más allá de la huella por su lado más corto. None sin
    madera (el patrón de siempre)."""
    from apolo.library.borde_agujero import CANTO_MADERA, TESTA_MADERA, veta

    piezas = [f for f in (a, b) if f.id in madera]
    if not piezas:
        return None
    d = h["d"]
    out = {ax: 0.0 for ax in h["inplane"]}
    for f in piezas:
        solidos = list(f.shape.solids())
        if not solidos:
            continue
        g = veta(max(solidos, key=lambda s: s.volume))
        bb = f.shape.bounding_box()
        mn, mx = (bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)
        for ax in h["inplane"]:
            pide = TESTA_MADERA * d if g is None or abs(g[ax]) >= 0.5 else CANTO_MADERA * d
            sigue = min(h["foot_min"][ax] - mn[ax], mx[ax] - h["foot_max"][ax])
            out[ax] = max(out[ax], pide - max(sigue, 0.0))
    return out


def _tramo(pieza_es_base: bool, fij, m: dict) -> tuple[float, float]:
    """El tramo del eje dentro de la pieza (coordenada `stack`)."""
    if not pieza_es_base:
        return tuple(sorted((m["cabeza"], m["contacto"])))
    if fij.tipo == "tornillo_madera":  # hasta la punta, sin asomar por detrás
        return tuple(sorted((m["contacto"], m["contacto"] + m["s"] * (fij.largo - m["t_add"]))))
    return tuple(sorted((m["contacto"], m["atras"])))


def exigir_madera(h: dict, base, anadida, puntos: list, medidas: list, fij,
                  madera: list[str]) -> None:
    """Criterio 7: cada agujero en una pieza de `madera` a ≥ 4·d de la testa y ≥ 3·d del canto,
    y ningún tornillo para madera que rosque en la testa. CommandError accionable."""
    from apolo.kernel.rayo import Rayos
    from apolo.library.borde_agujero import medir_madera, veta

    st = h["stack"]
    eje = [0.0, 0.0, 0.0]
    eje[st] = 1.0
    tornillo = fij.tipo == "tornillo_madera"
    for pieza, es_base in ((anadida, False), (base, True)):
        if pieza.id not in madera:
            continue
        solidos = list(pieza.shape.solids())
        vetas: dict[int, tuple | None] = {}
        for n, (pt, m) in enumerate(zip(puntos, medidas, strict=True), start=1):
            t0, t1 = _tramo(es_base, fij, m)
            origen = list(pt)
            origen[st] = 0.0
            centro = list(pt)
            centro[st] = (t0 + t1) / 2.0
            otros = [(tuple(q[:st] + [0.0] + q[st + 1:]), tuple(eje), h["clear"] / 2.0)
                     for q in puntos if q is not pt]
            for k, sol in enumerate(solidos):
                bb = sol.bounding_box()
                lo, hi = (bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)
                if not all(lo[i] - 0.05 <= centro[i] <= hi[i] + 0.05 for i in range(3)):
                    continue
                if k not in vetas:
                    vetas[k] = veta(sol)
                r = medir_madera(Rayos(sol), tuple(origen), tuple(eje), t0, t1, fij.d,
                                 vetas[k], otros, tornillo)
                if r["estado"] == "en_testa" and tornillo and es_base:
                    raise CommandError(
                        f"El tornillo {n} de la unión entraría por la testa de «{pieza.name}» "
                        "(su eje va a lo largo de la veta): ahí la rosca corta las fibras y se "
                        "arranca. Atornilla de través a la veta, o une con un perno pasante y "
                        "tuerca (también de barril) o con una escuadra."
                    )
                if r["estado"] == "medido" and not r["cumple"]:
                    donde, k_d = _LADO[r["lado"]]
                    raise CommandError(
                        f"El agujero {n} de la unión queda a {r['distancia']:g} mm "
                        f"{donde} de «{pieza.name}», que es de madera: pide ≥ "
                        f"{r['requerido']:g} mm = {k_d}·d (d = {r['d']:g} mm; criterio de diseño "
                        "con los mínimos descargados de EN 1995-1-1, tabla 8.4). Mueve las "
                        f"piezas para alejarlo {donde}, usa un perno menor o cambia "
                        "count/patron/spacing."
                    )
