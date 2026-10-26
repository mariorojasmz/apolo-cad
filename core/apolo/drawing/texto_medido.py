"""Texto de los entregables en papel que se MIDE en vez de cortarse a N caracteres (plan V8.9,
pendiente 10 y «cortes fijos fuera del cajetín»).

Un texto se mide con la fuente del PDF (`tabla.ancho_mm`) y, si no cabe en su lugar, se parte en
renglones (`tabla.partir`) o baja de tamaño hasta `TAM_MIN`; «…» sólo cuando ni así cabe. Dos
formas, según lo que rodea al texto:

- `encajar` / `celda`: un lugar de alto FIJO (una celda de tabla, una fila del cajetín, un rótulo
  entre dos líneas): renglones hasta `max_renglones` dentro de `alto`.
- `Parrafo` + `columna`: texto CORRIDO de arriba abajo hasta un `piso` (lo de abajo baja con él):
  si no entra, toda la columna baja de escala hasta que su letra más chica llegue a `TAM_MIN`; si
  ni así, el último renglón que entra termina en «…».
"""

from __future__ import annotations

from dataclasses import dataclass

#: la letra más chica de los papeles (la de las filas de revisiones del cajetín): nada baja de aquí
TAM_MIN = 2.2


def em(size: float) -> float:
    """Alto del em (mm) de una etiqueta de tamaño `size` en el PDF."""
    from .tabla import MM_POR_PT, PT_POR_MM_ETIQUETA

    return size * PT_POR_MM_ETIQUETA * MM_POR_PT


def con_puntos(texto: str, ancho: float, size: float) -> str:
    """El último recurso: `texto` recortado por la derecha hasta que quepa con «…»."""
    from .tabla import ancho_mm

    resto = texto
    while resto and ancho_mm(resto + "…", size) > ancho:
        resto = resto[:-1]
    return resto.rstrip() + "…"


def encajar(texto: str, ancho: float, size: float, max_renglones: int = 1,
            alto: float | None = None) -> tuple[float, list[str]]:
    """(tamaño, renglones) con que `texto` cabe en `ancho` mm: al tamaño pedido en un renglón si
    cabe; si no, partido en hasta `max_renglones` (que entren en `alto` mm, si se da) al primer
    tamaño que alcance, bajando de a 0,1 hasta `TAM_MIN`; si ni así, el último renglón a
    `TAM_MIN` termina en «…»."""
    from .tabla import alto_linea_mm, ancho_mm, partir

    texto = str(texto)
    if ancho_mm(texto, size) <= ancho:
        return size, [texto]
    s = size
    while s >= TAM_MIN - 1e-9:
        lineas = partir(texto, ancho, s)
        if len(lineas) <= max_renglones and (alto is None or len(lineas) * alto_linea_mm(s) <= alto):
            return s, lineas
        s = round(s - 0.1, 2)
    s = min(size, TAM_MIN)
    lineas = partir(texto, ancho, s)
    caben = max_renglones if alto is None else max(1, min(max_renglones, int(alto // alto_linea_mm(s))))
    return s, lineas[:caben - 1] + [con_puntos(" ".join(lineas[caben - 1:]), ancho, s)]


def celda(model, x: float, y_base: float, ancho: float, size: float, texto,
          max_renglones: int = 1, alto: float | None = None, y_centro: float | None = None) -> None:
    """Escribe `texto` desde `x`. Si cabe al tamaño pedido en un renglón, en `y_base` como
    siempre; si no, sus renglones centrados en `y_centro` (o desde `y_base` hacia abajo)."""
    from .sheet import Label
    from .tabla import alto_linea_mm

    s, lineas = encajar(texto, ancho, size, max_renglones, alto)
    if len(lineas) == 1 and s == size:
        model.labels.append(Label(x, y_base, lineas[0], s, anchor="start"))
        return
    lh = alto_linea_mm(s)
    if y_centro is None:
        y0 = y_base
    else:  # el em de cada renglón centrado: el del medio del bloque en y_centro
        y0 = y_centro + (len(lineas) - 1) * lh / 2 - 0.26 * em(s)
    for k, ln in enumerate(lineas):
        model.labels.append(Label(x, y0 - k * lh, ln, s, anchor="start"))


def celda_fila(model, x: float, y_base: float, ancho: float, size: float, texto,
               fila_abajo: float, alto_fila: float) -> None:
    """La celda de una tabla de filas de alto FIJO (`alto_fila` mm, borde inferior `fila_abajo`):
    en un renglón en `y_base` al tamaño de siempre si cabe; si no, dos renglones centrados en la
    fila (a 2,2 entran dos en una fila de 5,6). La tabla no crece: lo de abajo no se mueve."""
    celda(model, x, y_base, ancho, size, texto, max_renglones=2, alto=alto_fila - 0.4,
          y_centro=fila_abajo + alto_fila / 2)


@dataclass(frozen=True)
class Parrafo:
    """Un párrafo de una `columna`: `texto` a `size`, un renglón cada `paso` mm (a escala 1), en
    `x` + `sangria` (los renglones 2.. en `sangria_sig`, si se da); `antes` = aire previo (mm)."""

    texto: str
    size: float
    paso: float
    sangria: float = 0.0
    sangria_sig: float | None = None
    antes: float = 0.0


def _renglones(parrafos, ancho: float, f: float) -> list[tuple[float, float, str, float]]:
    """[(dx, caída desde arriba hasta la base, texto, tamaño)] de los párrafos a escala `f`."""
    from .tabla import ancho_mm, partir

    out, y = [], 0.0
    for p in parrafos:
        y += p.antes * f
        s = round(p.size * f, 3)
        sig = p.sangria if p.sangria_sig is None else p.sangria_sig
        if "\n" not in p.texto and ancho_mm(p.texto, s) <= ancho - p.sangria:
            primera = [p.texto]  # cabe: tal cual (`partir` junta los espacios dobles)
        else:
            primera = partir(p.texto, ancho - p.sangria, s)
        resto = " ".join(primera[1:])
        lineas = primera[:1] + (partir(resto, ancho - sig, s) if resto and sig != p.sangria
                                else primera[1:])
        for k, ln in enumerate(lineas):
            out.append((p.sangria if k == 0 else sig, y, ln, s))
            y += p.paso * f
    return out


def alto_columna(parrafos, ancho: float, f: float = 1.0) -> float:
    """Lo que baja la columna (mm) a escala `f`: de la base del primer renglón al siguiente libre."""
    rs = _renglones(parrafos, ancho, f)
    if not rs:
        return 0.0
    ultimo = parrafos[-1]
    return rs[-1][1] + ultimo.paso * f


def escala_columna(parrafos, ancho: float, disponible: float) -> float:
    """La escala con que los `parrafos` entran en `disponible` mm (de la base del primer renglón a
    la del último): 1 si entran; si no, la mayor que alcance bajando de a 0,02 sin que la letra
    más chica pase de `TAM_MIN` (si ni así entran, esa: `columna` corta con «…»)."""
    chica = min(p.size for p in parrafos)
    f, f_min = 1.0, min(1.0, TAM_MIN / chica)

    def ultima_base(f):
        rs = _renglones(parrafos, ancho, f)
        return rs[-1][1] if rs else 0.0

    while ultima_base(f) > disponible + 1e-9 and f > f_min:
        f = max(f_min, round(f - 0.02, 4))
    return f


def columna(model, x: float, y_top: float, parrafos, ancho: float, piso: float) -> float:
    """Escribe los `parrafos` desde la base `y_top` hacia abajo; ninguna base baja del `piso`. Si
    no entran a escala 1, toda la columna baja de escala (`escala_columna`); si ni así, el último
    renglón que entra termina en «…» (último recurso). Devuelve la y libre debajo."""
    from .sheet import Label

    if not parrafos:
        return y_top
    disponible = y_top - piso
    f = escala_columna(parrafos, ancho, disponible)
    rs = _renglones(parrafos, ancho, f)
    caben = [r for r in rs if r[1] <= disponible + 1e-9]
    if len(caben) < len(rs) and caben:  # último recurso
        dx, dy, ln, s = caben[-1]
        caben[-1] = (dx, dy, con_puntos(ln + " " + rs[len(caben)][2], ancho - dx, s), s)
    for dx, dy, ln, s in caben:
        model.labels.append(Label(x + dx, y_top - dy, ln, s, anchor="start"))
    return y_top - alto_columna(parrafos, ancho, f)
