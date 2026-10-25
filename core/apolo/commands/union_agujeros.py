"""`join_bolted` criterio 6 (V8.9 F7b, defecto 3): la unión usa los agujeros que una pieza YA trae.

Un accesorio que se compra o se fabrica con sus agujeros (los pies MS1 y la brida MF1/MF2 de
`create_pneumatic_cylinder`: anclas `pie_*_agujero_k` / `brida_agujero_k`) se atornilla por
ESOS agujeros, no por un patrón nuevo centrado en la huella: el patrón nuevo caía a 5,5 mm del
borde del agujero de fábrica (EN 1993-1-8 pide ≥ 1,2·d0) y la unión era imposible.

Reglas (las aplica `union_taller.criterio_taller` cuando `criterio >= 6`):
  - un agujero previo es un ancla cuyo nombre lleva «agujero», con eje ∥ al de la unión, dentro
    de la huella de solape y que de verdad es un hueco pasante en su pieza (rayos: su Ø se mide
    en la geometría, nunca se supone);
  - la pieza que trae los agujeros es la que se AGREGA (cabeza de su lado, tuerca detrás de la
    otra): es el accesorio que se monta sobre la máquina;
  - el perno lo fija el agujero (ISO 273): un `size` cuyo paso no es ese Ø es error con la
    métrica que sí casa; `patron`/`spacing`, o un `count` distinto del número de agujeros, son
    error (la pieza ya decide cuántos y dónde);
  - el eje de cada agujero se mide un radio + 1 mm al costado (por el agujero mismo el rayo no
    cruza material de la pieza que lo trae); el taladro va por el centro del agujero.
Sin agujeros previos en la huella, el criterio 6 es el 5 tal cual.
"""

from __future__ import annotations

from .errors import CommandError

#: mm: holgura con que un ancla cae «dentro» de la huella y con que un Ø casa con ISO 273
_TOL_HUELLA = 0.5
_TOL_DIAMETRO = 0.3


def _diametro(shape, pt: list[float], st: int, axis_sign: float, eje_lado: int) -> float | None:
    """Ø del hueco de `shape` centrado en `pt` (coordenada `st` = la cara del ancla), medido a lo
    largo del eje `eje_lado` a 0,5 mm dentro del material; None si en el centro hay material."""
    from apolo.kernel.rayo import tramos_en_eje

    p = list(pt)
    p[st] = pt[st] - axis_sign * 0.5  # el eje del ancla sale de la pieza: 0,5 mm hacia adentro
    bb = shape.bounding_box()
    lo = (bb.min.X, bb.min.Y, bb.min.Z)[eje_lado] - 1.0
    hi = (bb.max.X, bb.max.Y, bb.max.Z)[eje_lado] + 1.0
    tramos = tramos_en_eje(shape, eje_lado, p, lo, hi)
    c = p[eje_lado]
    if any(a < c < b for a, b in tramos):
        return None
    antes = [b for _a, b in tramos if b <= c]
    despues = [a for a, _b in tramos if a >= c]
    if not antes or not despues:
        return None  # abierto a un costado: es una ranura o un borde, no un agujero
    return min(despues) - max(antes)


def agujeros_previos(h: dict, a, b) -> tuple[object, list[tuple[list[float], float]]] | None:
    """(pieza que los trae, [(centro, Ø)]) de los agujeros previos en la huella, o None."""
    st = h["stack"]
    u, v = h["inplane"]
    for f in (a, b):
        hallados = []
        for nombre, an in sorted((getattr(f, "anchors", None) or {}).items()):
            if "agujero" not in nombre:
                continue
            o, ax = an.get("origin"), an.get("axis")
            if not o or not ax or abs(abs(float(ax[st])) - 1.0) > 1e-3:
                continue
            if not all(h["foot_min"][k] - _TOL_HUELLA <= o[k] <= h["foot_max"][k] + _TOL_HUELLA for k in (u, v)):
                continue
            d = _diametro(f.shape, [float(c) for c in o], st, 1.0 if ax[st] > 0 else -1.0, u)
            if d is not None:
                hallados.append(([float(c) for c in o], d))
        if hallados:
            return f, hallados
    return None


def metrica_de(diametro: float) -> str | None:
    """La métrica cuyo paso ISO 273 (serie media, la de `join_bolted`) es `diametro`."""
    from apolo.library.engineering.bolts import CLEARANCE_HOLE_MM

    return next((m for m, d in CLEARANCE_HOLE_MM.items() if abs(d - diametro) <= _TOL_DIAMETRO), None)


def exigir_compatibles(p, h: dict, pieza, agujeros: list) -> None:
    """CommandError accionable si los params piden otra cosa que los agujeros que la pieza trae."""
    n = len(agujeros)
    ds = sorted({round(d, 1) for _o, d in agujeros})
    que = f"«{pieza.name}» ya trae {n} agujero(s) Ø{'/'.join(f'{d:g}' for d in ds)} en la huella"
    puestos = p.model_fields_set
    if "patron" in puestos or "spacing" in puestos:
        raise CommandError(f"{que}: join_bolted atornilla por ellos; quita `patron`/`spacing`.")
    if "count" in puestos and int(p.count) != n:
        raise CommandError(f"{que}: join_bolted atornilla por ellos; pide count={n} o no lo pases.")
    for _o, d in agujeros:
        if abs(d - h["clear"]) > _TOL_DIAMETRO:
            m = metrica_de(d)
            casa = (f"usa size «{m}» (paso ISO 273 de Ø{round(d, 1):g})" if m
                    else "ningún perno de catálogo casa con ese paso")
            raise CommandError(f"{que}: un perno {h['size']} (paso Ø{h['clear']:g}) no casa con ellos; {casa}.")


def puntos_de_medida(h: dict, centro: list[float], d: float) -> list[list[float]]:
    """Dónde medir el eje de un agujero previo: un radio + 1 mm a cada costado, en el plano."""
    u, v = h["inplane"]
    out = []
    for k in (u, v):
        for s in (1.0, -1.0):
            q = list(centro)
            q[h["stack"]] = 0.0
            q[k] += s * (d / 2.0 + 1.0)
            out.append(q)
    return out
