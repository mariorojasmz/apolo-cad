"""Del catálogo a la colocación (plan V8.5 D2): `Aparato` y `Gabinete` desde las fichas
`electrico` + `tablero` de cada ref. No importa el catálogo: lo recibe (`catalogo` = un mapa
ref → `Component`), así la colocación sigue pura y testeable con fichas de prueba.

Cotas: la caja de la ref en el marco de su builder, leída de los params de una `box`
(width = X, depth = Y, height = Z) o, en otra familia, de `medir(ref) -> (dx, dy, dz)` (quien
tiene OCCT pasa el bbox del catálogo). La cara de apoyo (`ficha_tablero.apoyo_de`) dice cuál
de los tres ejes es el fondo: −Y (la caja) → ancho X, alto Z; −Z (la seta) → ancho X, alto Y.
En un mando de puerta el fondo es lo de DETRÁS (`tablero.puerta.detras_mm`). D2: lo que no
tiene cotas es error con la lista de refs a completar, nunca una caja inventada.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from .colocacion_modelo import Acople, Aparato, ColocacionError, Gabinete, clase_de
from .ficha_tablero import apoyo_de
from .referencias import sufijo_sugerencia

Medir = Callable[[str], tuple[float, float, float]]


def _caja(ref: str, comp, medir: Medir | None) -> tuple[float, float, float] | None:
    p = comp.params or {}
    if comp.familia == "box" and all(isinstance(p.get(k), (int, float)) for k in ("width", "depth", "height")):
        return float(p["width"]), float(p["depth"]), float(p["height"])
    return tuple(float(x) for x in medir(ref)) if medir is not None else None


def _ejes(apoyo: str, caja: tuple[float, float, float]) -> tuple[float, float, float]:
    """(ancho, alto, fondo) según el eje de la cara de apoyo."""
    dx, dy, dz = caja
    eje = apoyo[1]
    if eje == "Y":
        return dx, dz, dy
    if eje == "Z":
        return dx, dy, dz
    return dy, dz, dx


def aparatos_desde_catalogo(dispositivos: list[Mapping], catalogo: Mapping, *,
                            medir: Medir | None = None) -> tuple[list[Aparato], list[str]]:
    """Los `Aparato` de los dispositivos de UNA ubicación (`{designacion, ref, cantidad?,
    pieza?}`, p. ej. lo que lee el layout del carril) y los avisos. El gabinete declarado como
    dispositivo (símbolo `gabinete`) no se coloca: es la caja (aviso). Un aparato de campo es
    error; las refs sin cotas o sin su fondo de puerta, un error que las lista todas."""
    aparatos: list[Aparato] = []
    avisos: list[str] = []
    sin_cotas: list[str] = []
    for d in dispositivos:
        des, ref = str(d.get("designacion") or ""), str(d.get("ref") or "")
        comp = catalogo.get(ref)
        if comp is None or comp.electrico is None:
            electricos = [r for r, c in catalogo.items() if c.electrico is not None]
            raise ColocacionError(f"{des}: «{ref}» no es una ref eléctrica del catálogo."
                                  f"{sufijo_sugerencia(ref, electricos)}")
        e, t = comp.electrico, comp.tablero
        if e.simbolo == "gabinete":
            avisos.append(f"{des} ({ref}) es el gabinete: no se coloca dentro de sí mismo")
            continue
        if e.montaje == "campo" or e.conductor is not None:
            raise ColocacionError(f"{des} ({ref}) es de campo (montaje «{e.montaje}»): no va dentro "
                                  "del tablero; cámbiale la `ubicacion`")
        apoyo = apoyo_de(comp.familia, t)
        caja = _caja(ref, comp, medir)
        puerta = t.puerta if t is not None else None
        if apoyo is None or caja is None or (e.montaje == "puerta" and puerta is None):
            sin_cotas.append(ref)
            continue
        ancho, alto, fondo = _ejes(apoyo, caja)
        delante = 0.0
        if e.montaje == "puerta":
            fondo, delante = puerta.detras_mm, puerta.delante_mm
        n = int(d.get("cantidad") or 1) if e.bornera else 1
        acople = None
        if t is not None and t.acopla_a is not None:
            acople = Acople(t.acopla_a.simbolos, t.acopla_a.cara, t.acopla_a.orden)
        aparatos.append(Aparato(
            designacion=des, ref=ref, montaje=e.montaje, ancho=ancho * n, alto=alto, fondo=fondo,
            clase=clase_de((e.modelo or {}).get("tipo"), e.bornera), funcion=e.funcion,
            simbolo=e.simbolo, delante=delante, acopla=acople, pieza=d.get("pieza") or None))
    if sin_cotas:
        refs = sorted(set(sin_cotas))
        raise ColocacionError(f"sin cotas para colocar ({len(refs)}): {', '.join(refs)}; completa "
                              "en su YAML la caja del builder (o su medida) y, en un mando de puerta, "
                              "`tablero.puerta` {delante_mm, detras_mm}")
    return aparatos, avisos


def gabinetes_del_catalogo(catalogo: Mapping) -> list[Gabinete]:
    """Los gabinetes con su interior declarado (`tablero.gabinete`), de menor a mayor placa."""
    out = []
    for ref, c in catalogo.items():
        g = c.tablero.gabinete if c.tablero is not None else None
        if g is not None:
            out.append(Gabinete(ref, g.placa_ancho_mm, g.placa_alto_mm, g.fondo_util_mm,
                                g.espesor_puerta_mm, g.bisagra))
    return sorted(out, key=lambda g: (g.area, g.ref))
