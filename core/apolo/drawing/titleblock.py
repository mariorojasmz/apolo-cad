"""Cajetín profesional + bloque de revisiones para la lámina (Fase C).

Dibuja un cajetín de ingeniería completo (nº de plano, material, acabado, tolerancia
general, escala, hoja N/M, símbolo de diedro, dibujó/revisó/aprobó, peso, logo) y una
tabla de revisiones, escribiendo `Line`/`Label`/`Circle` en el `SheetModel`. Es una capa
de presentación: no calcula nada del modelo (recibe `fields` ya resueltos).

Ningún texto se corta a N caracteres: se MIDE con la fuente del PDF (`tabla.ancho_mm`) y, si no
cabe en su celda, se parte en renglones o baja de tamaño hasta `TAM_MIN`; «…» sólo si ni así
(plan V8.9, pendiente 10). La celda del diedro y la de «Genix Apolo CAD» no se cruzan.
"""

from __future__ import annotations

TITLE_W, TITLE_H = 180.0, 40.0     # cajetín
REV_ROW_H = 4.5                    # alto de una fila de revisión de UN renglón
REV_W = 90.0
#: la letra más chica del cajetín (la de las filas de revisiones): ningún texto baja de aquí
TAM_MIN = 2.2
_TAM_REV = 2.2
_MAX_RENGLONES_REV = 3
_COLS_REV = (0.0, 12.0, 34.0, REV_W)   # Rev | Fecha | Descripción (desde el borde izquierdo)
_PAD = 1.0                         # mm a cada lado del texto en una fila de revisión


def _txt(model, x, y, s, val, anchor="start"):
    from .sheet import Label

    model.labels.append(Label(x, y, str(val), s, anchor=anchor))


def projection_symbol(model, x: float, y: float, s: float = 7.0,
                      first_angle: bool = True) -> tuple[float, float, float, float]:
    """Símbolo de proyección en primer diedro (cono truncado: trapecio + 2 círculos). Devuelve
    su caja (x0, y0, x1, y1): ancho 2,4·s, alto s."""
    from .sheet import Circle, Line

    # trapecio (perfil del cono)
    model.lines += [
        Line(x, y, x + s, y + s * 0.32, "frame"),
        Line(x, y + s, x + s, y + s * 0.68, "frame"),
        Line(x, y, x, y + s, "frame"),
        Line(x + s, y + s * 0.32, x + s, y + s * 0.68, "frame"),
    ]
    # vista frontal (2 círculos concéntricos) a la derecha (1er diedro)
    cx = x + s * 1.9
    model.circles.append(Circle(cx, y + s * 0.5, s * 0.5, "dim"))
    model.circles.append(Circle(cx, y + s * 0.5, s * 0.22, "dim"))
    return (x, y, cx + s * 0.5, y + s)


def _peso(kg) -> str:
    """«12.5 kg», o «— kg» si nadie lo dio (una cotización sin peso decía «None kg», V8.1 F4)."""
    return f"{kg} kg" if kg is not None else "— kg"


def _em(size: float) -> float:
    """Alto del em (mm) de una etiqueta de tamaño `size` en el PDF."""
    from .tabla import MM_POR_PT, PT_POR_MM_ETIQUETA

    return size * PT_POR_MM_ETIQUETA * MM_POR_PT


def _con_puntos(texto: str, ancho: float, size: float) -> str:
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
    return s, lineas[:caben - 1] + [_con_puntos(" ".join(lineas[caben - 1:]), ancho, s)]


def _celda(model, x: float, y_base: float, ancho: float, size: float, texto,
           max_renglones: int = 1, alto: float | None = None, y_centro: float | None = None) -> None:
    """Escribe `texto` desde `x`. Si cabe al tamaño pedido en un renglón, en `y_base` como
    siempre; si no, sus renglones centrados en `y_centro` (o desde `y_base` hacia abajo)."""
    from .tabla import alto_linea_mm

    s, lineas = encajar(texto, ancho, size, max_renglones, alto)
    if len(lineas) == 1 and s == size:
        _txt(model, x, y_base, s, lineas[0])
        return
    lh = alto_linea_mm(s)
    if y_centro is None:
        y0 = y_base
    else:  # el em de cada renglón centrado: el del medio del bloque en y_centro
        y0 = y_centro + (len(lineas) - 1) * lh / 2 - 0.26 * _em(s)
    for k, ln in enumerate(lineas):
        _txt(model, x, y0 - k * lh, s, ln)


#: El título: el tamaño de siempre si cabe en un renglón; si no, dos renglones al primer tamaño
#: que alcance (y, si ni así, el segundo termina en «…»).
_TAM_TITULO, _TAMS_PARTIDO, _GAP_NUMERO = 4.0, (3.0, 2.5), 3.0


def _titulo_partido(model, x0: float, y0: float, titulo: str, numero: str) -> None:
    """El título del cajetín a la izquierda del número, MEDIDO con la fuente del PDF: en un
    renglón a 4 mm si cabe (como siempre), si no en dos más chicos (la cotización: su título
    comercial llega a 80 caracteres y cortarlo a 34 se comía el nombre de la máquina)."""
    from .tabla import ancho_mm, partir

    ancho = max(30.0, TITLE_W - 4.0 - ancho_mm(numero, 3.4) - _GAP_NUMERO)
    if ancho_mm(titulo, _TAM_TITULO) <= ancho:
        _txt(model, x0 + 2, y0 + TITLE_H * 0.84, _TAM_TITULO, titulo)
        return
    for size in _TAMS_PARTIDO:
        lineas = partir(titulo, ancho, size)
        if len(lineas) <= 2:
            break
    else:
        lineas = [lineas[0], _con_puntos(" ".join(lineas[1:]), ancho, size)]
    for k, ln in enumerate(lineas):
        _txt(model, x0 + 2, y0 + TITLE_H * (0.89 if len(lineas) == 2 else 0.84) - 4.0 * k, size, ln)


def _nota_rev(r: dict) -> str:
    return str(r.get("note", r.get("desc", "")))


def _renglones_rev(revs: list[dict]) -> list[list[str]]:
    """Los renglones de la descripción de cada revisión, partidos por ancho medido."""
    ancho = _COLS_REV[3] - _COLS_REV[2] - 2 * _PAD
    return [encajar(_nota_rev(r), ancho, _TAM_REV, _MAX_RENGLONES_REV)[1] for r in revs]


def _alto_fila_rev(n_renglones: int) -> float:
    from .tabla import alto_linea_mm

    return REV_ROW_H + (n_renglones - 1) * alto_linea_mm(_TAM_REV)


def alto_revisiones(revisions) -> float:
    """Lo que ocupa la tabla de revisiones sobre el cajetín (mm, con su separación de 1 mm; 0 sin
    revisiones). Quien pone algo encima del cajetín (las vistas, una tabla) lo lee de aquí: una
    descripción larga hace crecer su fila."""
    revs = list(revisions or [])[-6:]
    if not revs:
        return 0.0
    return 1.0 + REV_ROW_H + sum(_alto_fila_rev(len(r)) for r in _renglones_rev(revs))


def _tabla_revisiones(model, revs: list[dict], y0: float) -> None:
    """La tabla de revisiones encima del cajetín, alineada a la derecha: la más vieja arriba, bajo
    la cabecera; cada descripción entera, en tantos renglones como pida (hasta 3)."""
    from .sheet import Line
    from .tabla import alto_linea_mm, ancho_mm

    W = model.width
    rx = W - 10.0 - REV_W
    ry = y0 + TITLE_H + 1.0
    renglones = _renglones_rev(revs)
    altos = [_alto_fila_rev(len(r)) for r in renglones]
    alto = REV_ROW_H + sum(altos)
    model.rect(rx, ry, REV_W, alto)
    cols = [rx + c for c in _COLS_REV]
    for cx in cols[1:-1]:
        model.lines.append(Line(cx, ry, cx, ry + alto, "frame"))
    techo = ry + alto - REV_ROW_H  # borde inferior de la cabecera
    _txt(model, rx + 1, techo + 1.4, 2.4, "Rev")
    _txt(model, cols[1] + 1, techo + 1.4, 2.4, "Fecha")
    _txt(model, cols[2] + 1, techo + 1.4, 2.4, "Descripción")
    model.lines.append(Line(rx, techo, rx + REV_W, techo, "frame"))
    lh = alto_linea_mm(_TAM_REV)
    for i, r in enumerate(revs):
        # el borde de arriba de cada fila (el de la primera repite el de la cabecera: el orden de
        # las primitivas es el de siempre, lo congela `tests/test_laminas_congeladas.py`)
        model.lines.append(Line(rx, techo, rx + REV_W, techo, "frame"))
        yy = techo - (REV_ROW_H - 1.3)  # base del primer renglón: la de siempre en una fila simple
        rev = str(r.get("rev", i + 1))
        if ancho_mm(rev, _TAM_REV) > cols[1] - cols[0] - 2 * _PAD:
            rev = encajar(rev, cols[1] - cols[0] - 2 * _PAD, _TAM_REV)[1][0]
        _txt(model, rx + 1, yy, _TAM_REV, rev)
        _txt(model, cols[1] + 1, yy, _TAM_REV, str(r.get("date", ""))[:10])  # la fecha, sin la hora
        for k, ln in enumerate(renglones[i]):
            _txt(model, cols[2] + 1, yy - k * lh, _TAM_REV, ln)
        techo -= altos[i]


def draw_title_block(model, fields: dict) -> None:
    """Cajetín 180×40 mm abajo-derecha + tabla de revisiones encima. `fields`:
    project, drawing_no, scale, sheet, sheet_no, n_sheets, material, finish, tolerance,
    weight_kg, drawn_by, checked_by, approved_by, date, units, revisions[{rev,date,note}].
    Opcionales (la cotización): `numero_rotulo` (lo que precede al número: «Plano» si no viene)
    y `titulo_dos_renglones` (se acepta como siempre; desde el pendiente 10 de V8.9 TODO título
    se mide y, si no cabe en un renglón, va en dos)."""
    from .sheet import Line

    W = model.width
    x0 = W - 10.0 - TITLE_W
    y0 = 10.0
    f = fields

    revs = list(f.get("revisions") or [])[-6:]
    if revs:
        _tabla_revisiones(model, revs, y0)

    # --- cajetín ---
    model.rect(x0, y0, TITLE_W, TITLE_H)
    # filas horizontales
    rows = [y0 + TITLE_H * k for k in (0.25, 0.5, 0.75)]
    for ry in rows:
        model.lines.append(Line(x0, ry, x0 + TITLE_W, ry, "frame"))
    # columnas verticales del tercio inferior (material/acabado/peso/tol/escala/hoja)
    c1 = x0 + TITLE_W * 0.30
    c2 = x0 + TITLE_W * 0.55
    c3 = x0 + TITLE_W * 0.78
    for cx in (c1, c2, c3):
        model.lines.append(Line(cx, y0, cx, y0 + TITLE_H * 0.5, "frame"))
    # columna del bloque dibujó/revisó/aprobó | empresa: SÓLO en su fila (la del título es una
    # sola celda: un título largo la cruzaba)
    cdiv = x0 + TITLE_W * 0.62
    model.lines.append(Line(cdiv, y0 + TITLE_H * 0.5, cdiv, y0 + TITLE_H * 0.75, "frame"))

    # fila 1 (arriba): título + nº de plano (o del documento que diga `numero_rotulo`)
    numero = f"{f.get('numero_rotulo') or 'Plano'} {f.get('drawing_no', '—')}"
    _titulo_partido(model, x0, y0, str(f.get("project", "Sin título")), numero)
    _txt(model, x0 + TITLE_W - 2, y0 + TITLE_H * 0.84, 3.4, numero, anchor="end")
    # fila 2: dibujó/revisó/aprobó | empresa a la izquierda y el diedro a la derecha de su celda
    izq = cdiv - x0 - 4.0
    _celda(model, x0 + 2, y0 + TITLE_H * 0.66, izq, 2.3,
           f"Dib. {f.get('drawn_by', '')}  {str(f.get('date', ''))[:10]}")
    _celda(model, x0 + 2, y0 + TITLE_H * 0.56, izq, 2.3,
           f"Rev. {f.get('checked_by', '')}   Apr. {f.get('approved_by', '')}")
    s_diedro = 5.5
    medio = y0 + TITLE_H * 0.625
    _txt(model, cdiv + 2, medio - 0.26 * _em(2.8), 2.8, "Genix Apolo CAD")
    projection_symbol(model, x0 + TITLE_W - 2 - 2.4 * s_diedro, medio - s_diedro / 2, s_diedro)
    # tercio inferior: material | acabado/peso | tol/unidades | escala/hoja; el valor, en su celda
    # de 10 mm (hasta dos renglones)
    valor = dict(alto=TITLE_H * 0.25 - 1.0, max_renglones=2, y_centro=y0 + TITLE_H * 0.125)
    _txt(model, x0 + 2, y0 + TITLE_H * 0.34, 2.3, "Material")
    _celda(model, x0 + 2, y0 + TITLE_H * 0.10, c1 - x0 - 4.0, 3.0, f.get("material", "—"), **valor)
    _txt(model, c1 + 2, y0 + TITLE_H * 0.34, 2.3, "Acabado / Peso")
    _celda(model, c1 + 2, y0 + TITLE_H * 0.10, c2 - c1 - 4.0, 2.6,
           f"{f.get('finish', '—')} · {_peso(f.get('weight_kg'))}", **valor)
    _txt(model, c2 + 2, y0 + TITLE_H * 0.34, 2.3, "Tol. gral / Unid.")
    _celda(model, c2 + 2, y0 + TITLE_H * 0.10, c3 - c2 - 4.0, 2.6,
           f"{f.get('tolerance', 'ISO 2768-mK')} · {f.get('units', 'mm')}", **valor)
    _txt(model, c3 + 2, y0 + TITLE_H * 0.34, 2.3, "Escala / Hoja")
    _celda(model, c3 + 2, y0 + TITLE_H * 0.10, x0 + TITLE_W - c3 - 4.0, 2.6,
           f"{f.get('scale', '')} · {f.get('sheet_no', 1)}/{f.get('n_sheets', 1)} {f.get('sheet', '')}",
           **valor)
