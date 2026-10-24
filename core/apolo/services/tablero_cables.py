"""Los cables de CAMPO en el panel «Tablero» (plan V8.5 F4b): lo que el panel de UN tablero dice de
los cables que salen de él. No calcula nada: lee las filas de `cables_campo.vista` (la ÚNICA cuenta
del recorrido, el largo y los choques, D15) y las cuenta en palabras de la persona; el texto crudo
del ERC (`cables_campo.detalle_choque` / `detalle_incompleto`) va plegado en `tecnico`.

- Un cable es de un tablero si uno de sus extremos sale de su ubicación (`extremos[].ubicacion`).
- `items`: cada cable que toca lo que gira (falla) o pasa a menos de la holgura (aviso, con la
  distancia como cifra) es UN ítem, porque cada uno señala un lugar distinto de la máquina; los
  cables con el recorrido incompleto (un extremo sin resolver, o sin calcular) son UN ítem con la
  cuenta, como los hallazgos por conductor de `tablero_panel`.
- `bien`: si hay cables calculados y ninguno toca lo que gira, lo dice (es lo que se revisó).
- `filas`: el detalle de cada cable (largo = dentro + afuera + reserva, el puesto a mano si lo hay,
  sus supuestos y, con `recorridos`, la polilínea en mm de mundo como UN tramo).
"""

from __future__ import annotations

from .cables_campo import detalle_choque, detalle_incompleto


def del_tablero(filas: list[dict], ubicacion: str) -> list[dict]:
    """Las filas de `vista` con un extremo en `ubicacion`."""
    return [f for f in filas if any(e.get("ubicacion") == ubicacion for e in f.get("extremos") or [])]


def _plural(n: int, uno: str, varios: str) -> str:
    return uno if n == 1 else varios


def _item(clave, severidad, frase, **kw) -> dict:
    from .tablero_panel import item  # la forma del ítem es del panel (que importa este módulo)

    return item(clave, severidad, frase, **kw)


def _holgura(f: dict) -> float:
    return float((f.get("criterio") or {}).get("holgura_giro_mm", 10.0))


def _choque(f: dict) -> dict:
    xs = f["choques"]
    x, holgura = xs[0], _holgura(f)
    toca = x["distancia_mm"] <= 0.0
    mas = f" y {len(xs) - 1} {_plural(len(xs) - 1, 'pieza', 'piezas')} más" if len(xs) > 1 else ""
    if toca:
        frase = f"El cable {f['designacion']} toca una pieza que gira"
        donde = f"Atraviesa «{x['nombre']}»{mas}"
        extra = {}
    else:
        frase = f"El cable {f['designacion']} pasa muy cerca de una pieza que gira"
        d = x["distancia_mm"]
        donde = f"Pasa a {d:g} mm de «{x['nombre']}»{mas}"
        extra = {"valor": d, "unidad": "mm", "decimales": 0 if d == round(d) else 1}
    return _item(
        f"cable-giro-{f['comando']}", "falla" if toca else "aviso", frase, **extra,
        piezas=[y["pieza"] for y in xs], conductores=[f["comando"]],
        detalle=(f"{donde}; pedimos al menos {holgura:g} mm. Pídele al agente que lo lleve por la "
                 "estructura, lejos de lo que gira."),
        tecnico="\n".join(detalle_choque(f, y, holgura) for y in xs))


def items(filas: list[dict]) -> tuple[list[dict], list[dict]]:
    """(lo que pide atención, lo que está bien) de los cables de un tablero."""
    atender = [_choque(f) for f in filas if f.get("choques")]
    incompletos = [f for f in filas if not f.get("calculado") or f.get("sin_extremo")]
    if incompletos:
        n = len(incompletos)
        atender.append(_item(
            "cables-incompletos", "aviso",
            _plural(n, "Cable de campo con el recorrido incompleto", "Cables de campo con el recorrido incompleto"),
            valor=n, conductores=[f["comando"] for f in incompletos],
            detalle=("Su largo no cuenta lo que falta. Pídele al agente que ligue cada aparato de campo a su "
                     "pieza 3D y que revise de dónde a dónde va el cable."),
            tecnico="\n".join(detalle_incompleto(f["designacion"], f["ref"], f.get("sin_extremo"), f.get("motivo"))
                              for f in incompletos)))
    calculados = [f for f in filas if f.get("calculado")]
    bien = []
    if calculados and not any(f.get("choques") for f in filas):
        holgura = _holgura(calculados[0])
        bien.append(_item("cables-giro", "bien", "Los cables de campo no tocan lo que gira",
                          conductores=[f["comando"] for f in calculados],
                          detalle=f"Ninguno pasa a menos de {holgura:g} mm de una pieza que gira."))
    return atender, bien


def filas_detalle(filas: list[dict], *, recorridos: bool) -> list[dict]:
    """El detalle de cada cable para el panel (m; el recorrido, en mm de mundo, como un tramo)."""
    from apolo.library.catalog import CATALOG

    out = []
    for f in filas:
        comp = CATALOG.get(f["ref"])
        fila = {"id": f["comando"], "designacion": f["designacion"], "ref": f["ref"],
                **({"nombre": comp.name} if comp is not None and comp.name else {}),
                "calculado": bool(f.get("calculado")),
                "piezas": [x["pieza"] for x in f.get("choques") or []]}
        if f.get("calculado"):
            p = f["partes_mm"]
            fila |= {"largo_m": f["largo_m"],
                     "partes_m": {k: round(p[k] / 1000.0, 3) for k in ("adentro", "afuera", "reserva")},
                     **({"declarado_m": f["declarado_m"]} if "declarado_m" in f else {}),
                     **({"supuestos": list(f["supuestos"])} if f.get("supuestos") else {}),
                     **({"recorrido": [f["puntos"]]} if recorridos and len(f.get("puntos") or []) > 1 else {})}
        if not f.get("calculado") or f.get("sin_extremo"):
            fila["incompleto"] = True
        out.append(fila)
    return out
