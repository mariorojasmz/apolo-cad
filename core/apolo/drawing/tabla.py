"""Tablas que no se solapan ni se cortan (plan V8.1, F4c: D-c4).

`_table_sheet` (sheetset) pone anchos FIJOS y recorta cada texto a N caracteres: en la
cotización la Ref invadía la descripción («COLSON-5X2-PU-45-A-FT») y la fuente del precio se
cortaba («se compra po»). Aquí:

  - el ancho de cada columna sale del CONTENIDO, medido con la misma fuente con que matplotlib
    escribe el PDF (`pdf.py`: tamaño de la etiqueta × 2,45 pt);
  - si no cabe en la hoja, las columnas `flexibles` ceden ancho y su texto se PARTE en líneas
    (por palabras; una palabra que no cabe, por guiones o por letras): nada se recorta;
  - la fila crece con sus líneas y la tabla se pagina por ALTURA, sobre el cajetín y su tabla de
    revisiones.

`tests/test_cotizacion_f4c.py` renderiza cada hoja y comprueba que ninguna caja de texto se sale
de su celda.
"""

from __future__ import annotations

import re
from functools import lru_cache

from .sheet import Label, Line, SheetModel

PT_POR_MM_ETIQUETA = 2.45  # `pdf.py`: fontsize = Label.size × 2.45
MM_POR_PT = 25.4 / 72.0
PAD_X = 1.4      # mm a cada lado del texto dentro de la celda
PAD_Y = 1.1      # mm arriba y abajo
INTERLINEA = 1.32  # alto de línea / tamaño de la fuente (em)
ANCHO_MIN_FLEX = 16.0  # mm: una columna flexible no baja de esto


@lru_cache(maxsize=1)
def _renderer():
    from matplotlib.backends.backend_agg import RendererAgg

    return RendererAgg(10, 10, 72.0)  # 72 dpi: píxeles = puntos


@lru_cache(maxsize=8192)
def ancho_mm(texto: str, size: float) -> float:
    """Ancho (mm) con que matplotlib escribe `texto` en una etiqueta de tamaño `size`."""
    if not texto:
        return 0.0
    from matplotlib.font_manager import FontProperties

    w, _, _ = _renderer().get_text_width_height_descent(
        texto, FontProperties(size=size * PT_POR_MM_ETIQUETA), ismath=False)
    return w * MM_POR_PT


def alto_linea_mm(size: float) -> float:
    return size * PT_POR_MM_ETIQUETA * MM_POR_PT * INTERLINEA


def _trozos(palabra: str, ancho: float, size: float) -> list[str]:
    """Una palabra más ancha que la columna: se parte tras un guión, «/» o «_» si se puede; si
    no, por letras."""
    out, resto = [], palabra
    while resto and ancho_mm(resto, size) > ancho:
        cortes = [m.end() for m in re.finditer(r"[-/_.]", resto) if m.end() < len(resto)]
        bueno = max((c for c in cortes if ancho_mm(resto[:c], size) <= ancho), default=None)
        if bueno is None:
            bueno = max(1, max((k for k in range(1, len(resto))
                                if ancho_mm(resto[:k], size) <= ancho), default=1))
        out.append(resto[:bueno])
        resto = resto[bueno:]
    return out + ([resto] if resto else [])


def partir(texto: str, ancho: float, size: float) -> list[str]:
    """Las líneas de `texto` que caben en `ancho` mm (nunca recorta: las une `" ".join`, salvo
    los cortes dentro de una palabra)."""
    lineas: list[str] = []
    for parrafo in str(texto).split("\n"):
        linea = ""
        for palabra in parrafo.split():
            prueba = f"{linea} {palabra}" if linea else palabra
            if ancho_mm(prueba, size) <= ancho:
                linea = prueba
                continue
            if linea:
                lineas.append(linea)
            trozos = _trozos(palabra, ancho, size)
            lineas += trozos[:-1]
            linea = trozos[-1] if trozos else ""
        lineas.append(linea)
    return lineas or [""]


def anchos_columnas(headers: list[str], filas: list[list[str]], disponible: float, size: float,
                    flexibles: set[int]) -> list[float]:
    """Ancho natural de cada columna (su texto más ancho + relleno); si la suma no cabe en
    `disponible`, las `flexibles` ceden en proporción a su ancho natural (nunca bajo
    `ANCHO_MIN_FLEX`). Las rígidas (números, cantidades) conservan el suyo."""
    nat = [max([ancho_mm(str(h), size)] + [ancho_mm(str(f[j]), size) for f in filas])
           + 2 * PAD_X + 0.4 for j, h in enumerate(headers)]
    exceso = sum(nat) - disponible
    if exceso <= 0:
        return nat
    flex = [j for j in range(len(nat)) if j in flexibles]
    rigido = sum(w for j, w in enumerate(nat) if j not in flexibles)
    libre = max(disponible - rigido, ANCHO_MIN_FLEX * len(flex))
    total_flex = sum(nat[j] for j in flex) or 1.0
    out = list(nat)
    for j in flex:
        out[j] = max(ANCHO_MIN_FLEX, libre * nat[j] / total_flex)
    return out


def piso_tabla(meta: dict) -> float:
    """y (mm) bajo la cual la tabla no baja: el cajetín y su tabla de revisiones."""
    from .titleblock import REV_ROW_H, TITLE_H

    revs = list(meta.get("revisions") or [])[-6:]
    tope = 10.0 + TITLE_H + (1.0 + (len(revs) + 1) * REV_ROW_H if revs else 0.0)
    return tope + 4.0


def hojas_tabla(titulo: str, headers: list[str], filas: list[list], *, W: float, H: float,
                meta_hoja, flexibles: set[int], size: float = 2.6,
                derecha: set[int] = frozenset()) -> list[SheetModel]:
    """Hojas con la tabla: [SheetModel], paginadas por altura. `meta_hoja(k, n)` da el cajetín de
    la hoja k (1..n) — se llama al final, cuando se sabe cuántas son. `derecha` = columnas
    alineadas a la derecha (montos)."""
    from .titleblock import draw_title_block

    textos = [[str(v) for v in f] for f in filas]
    x0, top = 16.0, H - 30.0
    anchos = anchos_columnas(headers, textos, W - 2 * x0, size, flexibles)
    xs = [x0]
    for w in anchos:
        xs.append(xs[-1] + w)
    lh = alto_linea_mm(size)

    def celdas(fila):
        return [partir(t, anchos[j] - 2 * PAD_X, size) for j, t in enumerate(fila)]

    cab = celdas(headers)
    alto_cab = max(len(c) for c in cab) * lh + 2 * PAD_Y
    partidas = [celdas(f) for f in textos]
    altos = [max(len(c) for c in p) * lh + 2 * PAD_Y for p in partidas]

    piso = piso_tabla(meta_hoja(1, 1))
    paginas: list[list[int]] = [[]]
    y = top - alto_cab
    for i, alto in enumerate(altos):
        if paginas[-1] and y - alto < piso:
            paginas.append([])
            y = top - alto_cab
        paginas[-1].append(i)
        y -= alto

    def fila_de_texto(m: SheetModel, lineas_por_col, y_top: float, alto: float, cab_: bool):
        m.lines.append(Line(xs[0], y_top - alto, xs[-1], y_top - alto, "frame"))
        for j, lineas in enumerate(lineas_por_col):
            for k, ln in enumerate(lineas):
                yb = y_top - PAD_Y - (k + 1) * lh + 0.28 * lh  # base: deja el descendente dentro
                if j in derecha and not cab_:
                    m.labels.append(Label(xs[j + 1] - PAD_X, yb, ln, size, anchor="end"))
                else:
                    m.labels.append(Label(xs[j] + PAD_X, yb, ln, size, anchor="start"))

    hojas = []
    n = len(paginas)
    for k, idx in enumerate(paginas, start=1):
        m = SheetModel(W, H)
        m.rect(10, 10, W - 20, H - 20, "frame")
        m.labels.append(Label(16, H - 22, titulo if n == 1 else f"{titulo} ({k}/{n})", 5.0,
                              anchor="start"))
        y = top
        fila_de_texto(m, cab, y, alto_cab, True)
        y -= alto_cab
        for i in idx:
            fila_de_texto(m, partidas[i], y, altos[i], False)
            y -= altos[i]
        m.rect(xs[0], y, xs[-1] - xs[0], top - y)
        for cx in xs[1:-1]:
            m.lines.append(Line(cx, y, cx, top, "frame"))
        draw_title_block(m, meta_hoja(k, n))
        hojas.append(m)
    return hojas
