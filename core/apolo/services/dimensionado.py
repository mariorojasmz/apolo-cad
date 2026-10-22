"""La dimensión POR DEFECTO de una unión propuesta (plan mcp-sin-friccion, D8).

`declare_structure` declaraba los pernos sin métrica y las soldaduras sin garganta: la memoria y
`engineering_check` los daban «sin dimensionar» (no verificables). Ahora cada `fasten` propuesto
lleva la dimensión del criterio (`library/engineering/union_por_defecto.py`):

- perno: si una de las piezas es un EJE, su rosca —la mayor métrica normalizada que cabe en su Ø
  (la menor cota de su caja), una por lado—; si no, la del rol que manda (chumacera > equipo >
  guarda > el resto);
- soldadura: la garganta del criterio y, de longitud, el perímetro de la huella común de las dos
  cajas (la pata bajo el larguero: 4 lados); sin huella medible, la longitud del criterio.

Es un punto de partida verificable, no un cálculo: engineering_check la contrasta con la carga.
Puro: lee un `Document` explícito (las cajas de sus piezas), sin locks.
"""

from __future__ import annotations

from apolo.library.engineering.union_por_defecto import METRICAS, PERNO, SOLDADURA

#: Holgura de contacto (mm): dos cajas a tope tienen solape nulo en un eje.
_TOPE = 0.5
_ORDEN_PERNO = ("chumacera", "equipo", "guarda")


def _cotas(doc, fid: str, cache: dict) -> tuple | None:
    if fid not in cache:
        feat = doc.scene.get(fid)
        try:
            bb = feat.shape.bounding_box()
            cache[fid] = ((bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z))
        except Exception:  # noqa: BLE001 — sin forma medible: la dimensión de la tabla
            cache[fid] = None
    return cache[fid]


def _metrica_de_eje(caja) -> str:
    diametro = min(hi - lo for lo, hi in zip(*caja))
    return f"M{max((m for m in METRICAS if m <= diametro + 0.01), default=METRICAS[0])}"


def _huella_mm(ca, cb) -> float | None:
    """Perímetro de la huella común de dos cajas que se tocan (las dos cotas mayores del
    solape, con `_TOPE` de holgura), o None si no se tocan en un área."""
    solape = sorted(min(a1, b1) - max(a0, b0) + 2 * _TOPE
                    for a0, a1, b0, b1 in zip(ca[0], ca[1], cb[0], cb[1]))
    if solape[0] < 0 or solape[1] <= 2 * _TOPE:
        return None
    return round(2 * (solape[1] + solape[2] - 4 * _TOPE), 1)


def dimension(doc, a: str, b: str, kind: str, roles: dict, cache: dict | None = None) -> dict:
    """Los params de dimensión de un `fasten` {a, b, kind}: `{size, qty}` (perno), `{throat_mm,
    length_mm}` (soldadura) o `{}` (contacto, pegado). `roles` = {id: rol de unión}."""
    cache = {} if cache is None else cache
    if kind == "perno":
        eje = next((x for x in (a, b) if roles.get(x) == "eje"), None)
        caja = _cotas(doc, eje, cache) if eje else None
        if caja:
            return {"size": _metrica_de_eje(caja), "qty": 1}
        rol = next((r for r in _ORDEN_PERNO if r in (roles.get(a), roles.get(b))), "otro")
        size, qty = PERNO[rol]
        return {"size": size, "qty": qty}
    if kind == "soldadura":
        sol = SOLDADURA
        ca, cb = _cotas(doc, a, cache), _cotas(doc, b, cache)
        largo = _huella_mm(ca, cb) if ca and cb else None
        return {"throat_mm": sol["garganta_mm"], "length_mm": largo or sol["longitud_mm"]}
    return {}


def combinar(dims: list[dict]) -> dict:
    """La dimensión de UN `fasten` por conjuntos que declara varias uniones: la menor de cada
    cota (la métrica más chica, la garganta y la longitud más cortas), del lado seguro."""
    out: dict = {}
    for d in dims:
        for k, v in d.items():
            if k not in out:
                out[k] = v
            elif k == "size":
                out[k] = min(out[k], v, key=lambda s: int(s[1:]))
            else:
                out[k] = min(out[k], v)
    return out
