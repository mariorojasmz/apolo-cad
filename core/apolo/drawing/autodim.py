"""Acotado AUTOMÁTICO de una pieza (Fase 2 de planos pro).

Deriva cotas sin que el usuario liste ids: `auto_hole_dims` acota la POSICIÓN (x,y) de cada
agujero desde la esquina datum de la pieza, leída de la GEOMETRÍA (los círculos que
`_collect_circles` ya detecta en la vista por HLR). El Ø lo rotula `_hole_callouts` aparte →
juntos dan "Ø + dónde". Cubre taladros, clavijas y tornillos (todo lo circular).
"""

from __future__ import annotations


def auto_hole_dims(model, view, rect, tx, *, max_unique: int = 6) -> int:
    """Acota la posición (x,y) de los agujeros de `view` desde la esquina inferior-izquierda de la
    pieza: una escalera de cotas X por debajo (más allá de la cota general) y otra Y a la izquierda.
    Dedup por valor para no apilar cotas repetidas. Devuelve nº de agujeros vistos."""
    from .dimensions import baseline_dims

    if not view.circles:
        return 0
    rx, ry, rw, rh = rect
    minx, miny = view.bounds[0], view.bounds[1]
    dx_paper, dy_paper = tx((minx, miny))  # esquina datum en papel
    holes = sorted(view.circles, key=lambda c: (c[0], c[1]))

    # X: posiciones horizontales únicas, escalera por DEBAJO (tras la cota general)
    seen_x: set[float] = set()
    ex: list[tuple[float, float, str]] = []
    for cx, cy, _r in holes:
        v = round(cx - minx, 1)
        if v in seen_x or v <= 0:
            continue
        seen_x.add(v)
        px, _ = tx((cx, cy))
        ex.append((px, v, ""))
        if len(ex) >= max_unique:
            break
    if ex:
        baseline_dims(model, dx_paper, ex, vertical=False, along=ry, base_offset=20.0, offset_step=5.0)

    # Y: posiciones verticales únicas, escalera a la IZQUIERDA (tras la cota general)
    seen_y: set[float] = set()
    ey: list[tuple[float, float, str]] = []
    for cx, cy, _r in holes:
        v = round(cy - miny, 1)
        if v in seen_y or v <= 0:
            continue
        seen_y.add(v)
        _, py = tx((cx, cy))
        ey.append((py, v, ""))
        if len(ey) >= max_unique:
            break
    if ey:
        baseline_dims(model, dy_paper, ey, vertical=True, along=rx, base_offset=20.0, offset_step=5.0)
    return len(holes)


def _cluster(values: list[float], tol: float) -> list[float]:
    """Colapsa centros casi coincidentes: agrupa valores ordenados cuyo salto sea < tol y los
    sustituye por la media del grupo (evita pitches espurios de círculos solapados en la vista)."""
    out: list[float] = []
    group: list[float] = []
    for v in sorted(values):
        if group and v - group[-1] >= tol:
            out.append(sum(group) / len(group))
            group = []
        group.append(v)
    if group:
        out.append(sum(group) / len(group))
    return out


def mounting_pattern_dims(model, view, rect, tx, *, base_offset: float = 20.0, max_dims: int = 6,
                          merge_tol: float = 3.0, min_pitch: float = 6.0, min_paper: float = 4.0) -> int:
    """Acota el PATRÓN DE MONTAJE: el PITCH (centro a centro) entre agujeros consecutivos + la
    LUZ TOTAL del patrón — lo que un montador necesita para taladrar la placa de acople.

    Distinto de `auto_hole_dims` (posición desde el datum, para FABRICAR la pieza): aquí es
    centro→centro (para MONTAR). La cadena X va bajo la vista y la Y a la izquierda; la luz total
    en una segunda línea más afuera. `base_offset` se eleva cuando `auto_dims` también está activo.

    Robustez en vistas cargadas / a escala pequeña: agrupa centros casi coincidentes (`merge_tol`),
    descarta pitches minúsculos en mm (`min_pitch`) Y, sobre todo, los que en PAPEL caen más juntos
    que `min_paper` (a 1:25 un pitch de 25 mm = 1 mm de lámina → la etiqueta no cabe y se solaparía):
    en ese caso se omite el pitch y se deja solo la luz total. Devuelve el nº de cotas de pitch
    emitidas."""
    from .dimensions import linear_dim

    if not view.circles or len(view.circles) < 2:
        return 0
    rx, ry, rw, rh = rect
    emitted = 0

    def _chain(coords: list[float], make_pts, paper_idx: int, offset: float) -> int:
        n = 0
        pos = _cluster(coords, merge_tol)
        if len(pos) < 2:
            return 0
        paper = [make_pts(p)[paper_idx] for p in pos]
        # pitch solo si separa en mm Y en lámina lo suficiente para que la etiqueta NO se pise
        for i in range(len(pos) - 1):
            if n >= max_dims:
                break
            if pos[i + 1] - pos[i] < min_pitch or abs(paper[i + 1] - paper[i]) < min_paper:
                continue
            p1, p2 = make_pts(pos[i]), make_pts(pos[i + 1])
            linear_dim(model, p1, p2, vertical=(p1[0] == p2[0]), offset=offset,
                       value=round(pos[i + 1] - pos[i], 1))
            n += 1
        # luz total del patrón (primer↔último centro), una línea más afuera
        s1, s2 = make_pts(pos[0]), make_pts(pos[-1])
        linear_dim(model, s1, s2, vertical=(s1[0] == s2[0]), offset=offset + 9.0,
                   value=round(pos[-1] - pos[0], 1))
        return n

    # X: pitch entre columnas (cadena bajo la vista) + luz total
    emitted += _chain([c[0] for c in view.circles], lambda a: (tx((a, 0))[0], ry), 0, base_offset)
    # Y: pitch entre filas (cadena a la izquierda) + luz total
    emitted += _chain([c[1] for c in view.circles], lambda a: (rx, tx((0, a))[1]), 1, base_offset)
    return emitted
