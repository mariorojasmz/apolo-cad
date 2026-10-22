"""Tramos de MATERIAL a lo largo de una recta paralela a un eje del mundo.

Lo usa `join_bolted` (plan union-en-perfil-hueco, D1/D2): el largo del perno sale de lo que
el perno ATRAVIESA de verdad por el centro del taladro (el alma de 3 mm de una C, no los 50 mm
de su caja) y un perfil cerrado se reconoce porque la recta, tras salir de la primera pared,
vuelve a entrar en la MISMA pieza (la pared de enfrente del tubo).

Se mide con una varilla de sección 0,1 × 0,1 mm intersecada con el sólido (booleana de OCCT):
cada sólido del resultado es un tramo. Es robusto frente a caras curvas o inclinadas y no
depende del signo de las normales de un STEP. Puro: no muta nada.
"""

from __future__ import annotations

_LADO_VARILLA = 0.1  # mm: sección de la varilla de medición
_UNIR_MM = 1e-3      # dos tramos a menos de esto son uno (cara compartida de un compound)


def tramos_en_eje(shape, eje: int, punto, t0: float, t1: float) -> list[tuple[float, float]]:
    """Tramos [a, b] (coordenada `eje` del mundo: 0 = X, 1 = Y, 2 = Z), ordenados, donde la
    recta paralela a `eje` que pasa por `punto` está DENTRO de `shape`, entre `t0` y `t1`.
    [] si no la cruza (o si la booleana falla: el llamador lo trata como «sin material»)."""
    from build123d import Box, Pos

    lo, hi = min(t0, t1), max(t0, t1)
    if hi - lo <= 0:
        return []
    centro = [float(punto[0]), float(punto[1]), float(punto[2])]
    centro[eje] = (lo + hi) / 2.0
    medidas = [_LADO_VARILLA] * 3
    medidas[eje] = hi - lo
    varilla = Pos(*centro) * Box(*medidas)
    try:
        corte = shape & varilla
        solidos = list(corte.solids()) if corte is not None else []
    except Exception:  # noqa: BLE001 — booleana fallida = sin dato, nunca rompe al llamador
        return []
    crudos = []
    for s in solidos:
        try:
            if float(s.volume) <= 0:
                continue
            bb = s.bounding_box()
        except Exception:  # noqa: BLE001
            continue
        crudos.append(((bb.min.X, bb.min.Y, bb.min.Z)[eje], (bb.max.X, bb.max.Y, bb.max.Z)[eje]))
    crudos.sort()
    out: list[list[float]] = []
    for a, b in crudos:
        if out and a <= out[-1][1] + _UNIR_MM:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]
